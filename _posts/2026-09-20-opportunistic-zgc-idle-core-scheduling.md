---
title: "OppZGC: 유휴 코어를 쓰는 ZGC 스케줄링의 실전성"
description: "유휴 CPU를 GC에 투입하는 OppZGC 설계를 뜯어보고, 컨테이너 제약과 SLO·비용 채택 기준을 정리합니다."
date: 2026-09-20 10:01:16 +0900
categories: ["Performance", "JVM"]
tags: ["zgc", "hotspot", "tail-latency", "kubernetes", "cgroups", "performance"]
render_with_liquid: false
---

## OppZGC가 겨냥하는 역설: CPU를 더 쓰면 느려지는데, 더 쓰면 빨라진다

GC 튜닝의 기본 직관은 단순합니다. GC가 CPU를 더 쓰면 애플리케이션 스레드(mutator)가 쓸 CPU가 줄고, 처리량이 떨어지며 tail latency가 나빠집니다. 특히 동시(concurrent) collector는 stop-the-world 시간을 줄이는 대신, 애플리케이션과 같은 시간대에 CPU와 cache/memory bandwidth를 공유합니다. 그래서 “동시 GC는 throughput을 조금 희생하고 pause를 산다”가 보통의 프레임입니다.

[OppZGC 논문](https://arxiv.org/abs/2609.15558) (arXiv 공개: 2026-09-14)은 이 프레임을 정면으로 비틉니다. 핵심 가정은 **유휴 코어**가 실제 운영 환경에 자주 존재한다는 점입니다. 오토스케일링이 완벽하지 않거나, 안전 마진 때문에 과프로비저닝 되어 있거나, 워크로드가 bursty해서 평균 CPU는 낮지만 순간 피크가 있는 경우가 흔합니다. 이런 상황에서 기본 ZGC 스케줄러가 “최대한 늦게 GC를 돌려서 CPU 간섭을 최소화”하는 쪽으로만 움직이면, 메모리를 과하게 잡아먹거나(heap이 필요 이상으로 커지거나), locality/paging 측면에서 손해를 보거나, 결과적으로 tail latency가 흔들리는 여지가 생깁니다. OppZGC는 “CPU가 남는 구간에 더 자주, 더 동시적으로 GC를 돌려서 heap occupancy를 낮게 유지하면 tail이 오히려 좋아질 수 있다”는 쪽을 실험합니다.[^1]

이 접근은 GC 알고리즘 자체를 갈아엎는 게 아니라, ZGC의 스케줄링(언제 cycle을 시작할지)을 바꾸는 방식입니다. 그래서 실전 관점에서는 다음 세 가지가 바로 질문이 됩니다.

- 어떤 워크로드에서 진짜로 득이 나는가
- 컨테이너/코어 제한(cgroup quota)에서 OppZGC의 “idle” 판정이 왜곡되지 않는가
- SLO와 비용(메모리 vs CPU, 스케일링 정책) 관점에서 채택 여부를 어떻게 결정할 것인가

## ZGC가 원래 보수적인 이유: ZDirector 규칙과 heap을 키우는 전략

논문은 baseline으로 JDK 24의 generational ZGC를 기준으로 설명합니다. generational ZGC는 JDK 21에 들어왔고, JDK 24에서는 ZGC가 generational 모드만 제공된다고 정리합니다.[^1]

ZGC 내부에서 “언제 minor/major GC를 시작할지”를 결정하는 구성요소로 ZDirector를 설명하고, baseline 규칙들을 표로 정리합니다. 예를 들어 minor는 allocation rate로 “지금 시작하지 않으면 young collection이 끝나기 전에 heap이 고갈(stall)될 것” 같은 상황을 막는 규칙이 있고, 또 하나의 backstop으로 soft max의 5% 미만으로 free가 떨어지면 시작하는 규칙이 있습니다. major도 비슷하게 timer/warmup/proactive 같은 트리거가 있습니다.[^1]

이 보수성은 이유가 있습니다.

1) ZGC의 동시성은 공짜가 아닙니다. barrier slow path 빈도가 올라가거나, 동시 스레드들이 allocator/metadata 등의 공유 지점에서 경쟁하면 애플리케이션의 실제 request latency가 흔들립니다. 논문도 “frequent and excessive collections can still harm performance”를 전제로 깔고 들어갑니다.[^1]

2) 그래서 ZGC는 기본적으로 heap을 최대 허용치(-Xmx) 쪽으로 키우는 방향으로 움직이고, “지금 더 미루면 stall 위험”이 보일 때에만 cycle을 시작하는 쪽으로 설계됩니다. 논문 초반의 설명이 이 점을 정확히 못 박습니다.[^1]

3) 그 결과, -Xmx가 실제 live set 대비 과하게 크면 메모리를 불필요하게 점유하거나, locality가 악화되거나, paging과 같은 OS 레벨 비용까지 건드릴 수 있습니다. OppZGC는 바로 이 구간을 “idle CPU로 메워서 heap을 얇게 유지하자”로 바꿉니다.[^1]

여기서 현실적인 연결고리는 ZGC의 SoftMaxHeapSize입니다. Oracle의 GC tuning 가이드는 SoftMaxHeapSize를 “heuristics가 목표로 삼는 soft limit”로 설명하면서, 필요하면 stall을 막기 위해 -Xmx까지 넘어갈 수 있다고 명시합니다.[^2]

즉, 운영자가 수동으로 할 수 있는 건 대략 두 가지입니다.

- (메모리 우선) SoftMaxHeapSize를 내려서 더 자주 GC를 유도하고 heap occupancy를 낮춘다.
- (CPU 우선) ConcGCThreads를 낮춰서 동시 GC가 가져가는 CPU 총량을 제한한다. Oracle 문서도 ConcGCThreads가 “GC에 줄 CPU time을 사실상 결정한다”고 설명합니다.[^3]

OppZGC는 이 수동 튜닝을 “idle CPU가 있을 때만 자동으로 더 공격적으로” 하려는 시도에 가깝습니다.

## OppZGC의 핵심 규칙: α(성장 비율) + δ(판정 윈도우) + idle CPU 조건

OppZGC는 ZDirector에 규칙 두 개를 추가합니다.

- major_opportunistic
- minor_opportunistic

이 규칙들은 기존 규칙들이 모두 실패했을 때(즉, stall 위험이나 proactive 기준이 아직 아닐 때) 마지막에 체크됩니다.[^1]

무작정 “idle이면 매번 GC”를 하지 않는 이유도 명확히 적습니다. 너무 자주 cycle을 시작하면 STW pause 횟수 자체가 늘고, barrier slow path 등 간접 비용이 쌓여 mutator throughput을 갉아먹을 수 있습니다.[^1]

그래서 OppZGC는 2단계 게이트를 둡니다.

### 1) heap 성장 게이트(α): “최근에 치운 쓰레기 대비 얼마나 다시 더러워졌나”

규칙은 먼저 “이전 opportunistic collection 이후 heap occupancy가 충분히 증가했는지”를 봅니다. 증가량을 “직전 opportunistic GC가 reclaim한 양”으로 정규화한 뒤, configurable growth ratio α를 넘는지 체크합니다. α < 1.0이면 더 공격적으로(아래로 압력) heap을 누르고, α ≈ 1.0이면 “최근 reclaim 수준 근처에서 cap”하는 성격으로 설명합니다.[^1]

이 부분이 실전에서 중요한 이유는, OppZGC가 **메모리 회수 효율이 낮아지는 구간**(live set이 커서 reclaim이 잘 안 되는 구간)에서는 자연스럽게 자주 못 돌게 만들 수 있다는 점입니다. reclaim이 적으면 “분모”가 작아져서 α 게이트를 넘기 어렵고, 결국 opportunistic cycle이 줄어듭니다. GC가 애플리케이션을 망치기 쉬운 구간에서 스스로 조심해질 여지가 생깁니다.

### 2) idle CPU 게이트(δ + 예측식): “이 GC를 돌릴 만큼의 남는 core-time이 있었나”

OppZGC는 세 가지 런타임 메트릭을 사용합니다.[^1]

- idle_cores: 현재 idle CPU capacity(코어 단위)
  - 계산: active processor count − (이전 δ 동안 소모한 CPU)
  - 예시까지 논문에 적혀 있습니다.
- gc_duration: GC cycle의 wall clock duration 예측
  - 계산: serial GC time + (parallelizable GC time / GC worker count)
- gc_cpu_cost: GC cycle의 total CPU time 예측
  - 계산: serial GC time + parallelizable GC time

그리고 조건식은 다음 하나입니다.

- idle_cores × gc_duration ≥ gc_cpu_cost[^1]

해석은 단순합니다.

- gc_cpu_cost는 “총 CPU time이 이만큼 든다”입니다.
- idle_cores는 “동시에 쓸 수 있는 CPU 코어 수”의 근사입니다.
- 그러면 idle_cores로 나눴을 때, 이 GC를 끝내는 데 필요한 시간은 대략 gc_cpu_cost / idle_cores입니다.
- 그 값이 “예상 cycle duration”인 gc_duration보다 작거나 같으면, 그 정도 idle capacity로 cycle을 소화할 수 있다고 보는 겁니다.

여기서 δ는 “직전 δ 시간 동안의 CPU 사용량”을 통해 idle_cores를 추정하는 윈도우입니다. 논문이 제시하는 설정 예시는 δ=20ms를 많이 씁니다.[^1]

추가로 구현 세부사항이 실전 함정과 직결됩니다.

- 구현은 getrusage로 “프로세스 CPU utilization”을 가져옵니다.
- 논문은 이 방식이 “JVM이 otherwise idle machine에서 돌 때만 적절”하다고 못 박고, multi-tenant에서는 /proc/schedstat(시스템 전체)나 cgroup cpu.stat(그 cgroup만) 같은 다른 소스를 쓰라고 적습니다.[^1]
- stale information으로 연속적으로 여러 번 시작하는 걸 막기 위해 “δ 기간당 최대 1회만 cycle을 시작”합니다.[^1]

정리하면, OppZGC는 GC 알고리즘을 바꾸기보다 “언제 더 자주 돌려도 안전한지”를 수식 하나로 판정하는 스케줄러라고 보는 게 가장 정확합니다.

## 어느 워크로드에서 유리한가: idle이 만들어지는 방식이 핵심

OppZGC는 전제부터 워크로드 의존적입니다. “idle 코어가 있다”는 사실은 애플리케이션 특성만이 아니라 배치 방식, 오토스케일러 반응 속도, CPU limit 정책, 노드 혼잡도까지 포함한 합성 결과입니다.

논문이 사용하는 벤치마크 축은 DaCapo Chopin과 SPECjbb입니다.[^1] DaCapo Chopin은 latency-sensitive 애플리케이션의 tail latency 퍼센타일을 보고하고, 동시 collector가 종종 throughput collector보다 tail이 나쁜 이유를 문제 제기로 던진 바 있습니다.[^4]

OppZGC가 유리해질 가능성이 큰 패턴을 실전 언어로 다시 쓰면 아래와 같습니다.

### 1) 평균 CPU는 낮고, 순간적으로 치솟는 서비스

예를 들어 요청 기반 API 서버가 “트래픽이 들쭉날쭉”하고, 오토스케일이 p95/p99을 따라가기 위해 여유를 남겨두는 상황이라면 idle window가 자주 생깁니다. 이때 baseline ZGC는 heap을 비교적 크게 가져가며 cycle 빈도를 낮추려 하고, 그로 인해 heap occupancy가 필요 이상으로 높아질 수 있습니다. OppZGC는 idle window에 minor(혹은 조건에 따라 major)를 더 돌려 heap을 낮춰 둡니다.

이 시나리오에서 기대할 수 있는 효익은 크게 두 가지입니다.

- (메모리) peak heap occupancy가 내려가면, 같은 -Xmx에서도 실제 사용하는 heap이 낮아져 메모리 footprint가 줄어듭니다.
- (지연시간) live set이 더 작아지고 relocation/marking의 압력이 낮아지면, barrier slow path 등 간접 비용이 줄어 tail에 이득이 날 수 있습니다.

### 2) live set은 작지만 allocation rate가 큰 서비스

live set이 작아도 allocation rate가 크면 collector는 자주 돌아야 합니다. baseline은 “heap을 더 키워서 빈도를 줄이기”를 택할 수 있는데, 이는 메모리로 CPU를 사는 형태입니다. idle CPU가 있는 환경이라면 OppZGC는 반대로 “CPU를 더 써서 heap을 얇게 유지”할 수 있습니다.

이때 α 게이트가 꽤 중요해집니다. reclaim이 잘 되는 구간에서는 opportunistic collection이 자주 가능하고, reclaim 효율이 떨어지면 자연히 줄어듭니다.[^1]

### 3) 시스템이 단계적으로 포화되는 워크로드

논문은 SPECjbb 실행 타임라인에서, 초기 고강도 구간에서도 idle capacity가 남아 opportunistic collection이 동작해 heap을 특정 수준 이하로 유지하다가, CPU가 완전히 포화되면 opportunistic이 멈추고 baseline과 같은 규칙만 남는 흐름을 설명합니다.[^1]

이건 실전에서도 자주 보는 곡선입니다.

- 캐시 warmup / 트래픽 ramp-up / 배치 시작 등으로 CPU가 점점 차오름
- 포화 직전까지는 “남는 코어”가 있고, 그 구간에 뒷정리를 해두면 이후가 안정됨

OppZGC는 그 중간 구간을 노립니다.

### 4) 유리하지 않은 케이스도 명확하다

OppZGC 조건식은 결국 idle_cores가 있어야만 발화합니다. CPU가 꾸준히 포화된(혹은 quota로 포화가 강제되는) 서비스라면, opportunistic rule은 대부분 발화하지 않습니다. 논문에서도 2코어로 제한하면 두 코어가 mutator로 거의 항상 포화되어 opportunistic이 잘 안 켜진다고 설명합니다.[^1]

즉, “CPU가 남는 환경에서만” 이득을 기대해야 합니다.

## 컨테이너/코어 제한 환경의 함정: idle 판정이 깨지는 방식들

OppZGC 자체가 “idle CPU”라는 관측값에 100% 기대는 구조이기 때문에, 컨테이너 환경에서는 두 겹의 함정이 생깁니다.

- (A) JVM이 보는 active processor count가 무엇으로 결정되는가
- (B) idle로 보이는 시간이 실제로는 “throttling으로 멈춰 있는 시간”이 아닌가

### active processor count는 cgroup quota/period로 깎일 수 있다

HotSpot은 Linux에서 cgroup을 읽어 “active processor count”를 계산합니다. 코드 레벨로 보면 cpu_quota와 cpu_period가 있으면 quota/period를 ceil해서 quota_count를 만들고, cpu_shares도 고려하는 경로가 있으며, PreferContainerQuotaForCPUCount 같은 플래그에 따라 quota와 shares를 어떻게 섞을지 분기합니다.[^5]

Red Hat 문서도 컨테이너 환경에서 유용한 옵션으로 `-XX:ActiveProcessorCount`(강제 오버라이드)와 `-XX:-UseContainerSupport`(컨테이너 감지 끄기)를 명시합니다.[^6]

OppZGC의 idle_cores는 “active processor count − (이전 δ 동안 CPU consumed)”입니다.[^1]

그래서 CPU limit이 강하게 걸려 active processor count가 1~2로 깎여 있으면, idle_cores 자체가 커질 여지가 줄어듭니다. 이 경우 OppZGC는 크게 작동하지 않거나, 작동하더라도 제한적으로만 작동합니다.

이건 단점이기도 하고 장점이기도 합니다.

- 단점: “노드에는 CPU가 남는데 우리 cgroup에는 quota가 낮아서 못 쓰는” 경우, OppZGC가 활용할 idle이 애초에 생기지 않습니다.
- 장점: 잘못된 낙관(“코어 많네, GC 돌리자”)이 줄어듭니다.

### Kubernetes CPU limit은 throttling으로 집행된다

Kubernetes 공식 문서는 CPU limit이 Linux cgroups로 enforced 되고, CPU limit은 CPU throttling으로 집행된다고 설명합니다.[^7]

이때 중요한 포인트는 “노드 전체 CPU가 한가해도, limit이 걸린 cgroup은 그 순간 멈춘다”는 점입니다. OppZGC가 기대하는 “idle core를 쓰는 GC”는, 실제로는 “idle core가 남아도 못 쓰는 환경”에서 의미를 잃습니다.

더 나쁜 케이스는 관측이 왜곡될 때입니다.

- getrusage 기반으로 “프로세스가 소비한 CPU time”만 보면,
- throttling으로 강제 sleep 당한 시간은 CPU consumed로 잡히지 않습니다.

즉, 프로세스가 실행을 못 하고 멈춰 있는 시간이 길수록 “CPU를 덜 썼다”로 보일 수 있고, δ 윈도우의 계산 결과가 “idle이 있네”로 착시될 여지가 생깁니다. 논문도 getrusage 방식이 idle 머신 가정에서만 적절하다고 선을 긋는 이유가 여기와 연결됩니다.[^1]

OppZGC 구현이 cgroup cpu.stat 같은 per-cgroup 소스로 바뀌지 않는다면, (특히) 다음 조합에서 위험해집니다.

- 여러 pod가 같은 노드에서 경쟁하는 multi-tenant
- CPU limit이 낮아서 throttling이 자주 발생
- 그 와중에 OppZGC가 opportunistic cycle을 자주 시작(예측 실패)

이 경우 GC 자체가 원인이 아니라도 tail latency가 나빠질 수 있습니다. CPU throttling이 tail을 망치는 건 JVM 바깥에서도 관측되는 현상이고, 실험/증명 자료도 많이 쌓여 있습니다. 예를 들어 [k8s-cpu-limits-analyzed 리포지토리](https://github.com/inevolin/k8s-cpu-limits-analyzed/)는 throttling이 latency를 어떻게 왜곡하는지 실험 스크립트와 함께 정리합니다.[^8]

### “CPU limit을 없애면 idle을 쓸 수 있다”도 단순하지 않다

그럼 반대로 CPU limit을 제거하면 어떨까요. cgroup quota가 없으면 active processor count가 노드 코어 수로 잡힐 가능성이 커지고, idle_cores가 크게 계산될 여지가 생깁니다. 하지만 그 idle은 “내가 독점 가능한 idle”이 아닙니다. 다른 워크로드가 같은 노드에서 그 CPU를 쓰기 시작하면, OppZGC의 idle 예측은 즉시 깨집니다.

즉, OppZGC의 실전성은 “idle CPU가 존재”만으로 결정되지 않고, “idle을 신뢰할 수 있는가(격리/전용성)”까지 포함합니다.

- dedicated node pool
- CPU Manager static policy로 core pinning
- request=limit로 Guaranteed QoS + 타이트한 노드 운영

같은 조건에서 OppZGC가 더 설득력이 있습니다.

## 수동 튜닝 대비 OppZGC의 의미: SoftMaxHeapSize의 실패 모드가 힌트

논문 중간에는 “soft max를 줄여서 더 자주 GC를 돌리면 heap을 줄일 수 있지만, CPU가 부족하면 오히려 성능이 망가진다”는 실패 모드를 정리합니다. 예를 들어 2코어 제한에서 soft max를 2×로 두고 더 공격적으로 하면 startup/steady-state slowdown이 15%/20%까지 커지고 tail latency는 70% 이상 악화되는 경우를 언급합니다.[^1]

이 대목은 OppZGC의 실전 가치를 가장 현실적으로 보여줍니다.

- SoftMaxHeapSize를 내리는 건 강제 정책에 가깝습니다.
- CPU가 바빠도 GC를 더 돌리게 만들 수 있습니다.
- 즉 “메모리를 아끼려다가 SLO를 태우는” 실패가 나옵니다.

OppZGC는 적어도 설계상으로는 “CPU가 바쁠 때는 opportunistic을 멈춘다(self-modulating)”고 주장합니다.[^1]

실전 관점에서 이 차이는 큽니다.

- 수동 정책(soft max 조정)은 workload shift에 약합니다.
- OppZGC는 workload shift에 따라 발화 빈도를 바꾸려 합니다.

다만, 앞서 말했듯 “idle 관측”이 정확해야 이 장점이 성립합니다.

## 실험을 위한 현실적인 코드: tail latency + GC/컨테이너 신호를 같이 보기

OppZGC 패치가 메인라인 OpenJDK에 아직 들어갔다고 확인할 근거는 이 글에서 제시하지 않겠습니다. 논문은 JDK 24+2(mainline commit 50bed6c) 기반으로 구현했다고만 적고, 이 대화에서 추가로 아티팩트/패치 링크를 확인하지는 못했습니다.[^1]

대신 “OppZGC가 먹힐 조건인지”를 지금 가진 도구로 빠르게 판별하는 실험틀을 만드는 게 더 실용적입니다. 아래 코드는 세 가지를 한 번에 보려고 만든 형태입니다.

1) 요청 path의 p50/p90/p99/p99.9를 자체적으로 출력
2) ZGC를 켜고(gc log/JFR로) concurrent phase 비용을 관측
3) 컨테이너(cpu.stat)에서 usage/throttling 신호를 같이 수집

### 구성

- JDK: 21+ (ZGC 사용)
- 빌드: Maven
- 서버: Undertow
- 히스토그램: HdrHistogram

#### pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>io.daewook</groupId>
  <artifactId>latency-service</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>io.undertow</groupId>
      <artifactId>undertow-core</artifactId>
      <version>2.3.12.Final</version>
    </dependency>
    <dependency>
      <groupId>org.hdrhistogram</groupId>
      <artifactId>HdrHistogram</artifactId>
      <version>2.2.2</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.5.0</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <createDependencyReducedPom>false</createDependencyReducedPom>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <mainClass>io.daewook.latency.LatencyService</mainClass>
                </transformer>
              </transformers>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
```

#### LatencyService.java

```java
package io.daewook.latency;

import io.undertow.Undertow;
import io.undertow.server.HttpHandler;
import io.undertow.server.HttpServerExchange;
import io.undertow.util.Headers;
import org.HdrHistogram.Recorder;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Deque;
import java.util.Optional;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class LatencyService {

  // 1us ~ 10s 범위를 3자리 정밀도로 기록
  private static final long HIGHEST_TRACKABLE_VALUE_MICROS = Duration.ofSeconds(10).toMillis() * 1000;
  private static final Recorder RECORDER = new Recorder(HIGHEST_TRACKABLE_VALUE_MICROS, 3);

  // 요청 처리 중 “할당 + CPU”를 만들기 위한 파라미터(현실적인 서비스에서도 흔한 패턴)
  private static int bytesPerRequest = Integer.parseInt(System.getProperty("bytesPerRequest", "262144")); // 256KiB
  private static int cpuRounds = Integer.parseInt(System.getProperty("cpuRounds", "400"));

  public static void main(String[] args) {
    int port = Integer.parseInt(Optional.ofNullable(System.getenv("PORT")).orElse("8080"));

    ScheduledExecutorService ses = Executors.newSingleThreadScheduledExecutor();
    ses.scheduleAtFixedRate(() -> {
      var h = RECORDER.getIntervalHistogram();
      long p50 = h.getValueAtPercentile(50.0);
      long p90 = h.getValueAtPercentile(90.0);
      long p99 = h.getValueAtPercentile(99.0);
      long p999 = h.getValueAtPercentile(99.9);
      long max = h.getMaxValue();
      long count = h.getTotalCount();
      System.out.printf("latency_us count=%d p50=%d p90=%d p99=%d p99.9=%d max=%d%n",
          count, p50, p90, p99, p999, max);
    }, 1, 1, TimeUnit.SECONDS);

    HttpHandler handler = exchange -> {
      long start = System.nanoTime();
      try {
        if (exchange.getRequestPath().equals("/health")) {
          exchange.getResponseHeaders().put(Headers.CONTENT_TYPE, "text/plain");
          exchange.getResponseSender().send("ok");
          return;
        }

        int bytes = queryInt(exchange, "bytes").orElse(bytesPerRequest);
        int rounds = queryInt(exchange, "rounds").orElse(cpuRounds);

        byte[] payload = new byte[bytes];
        // 실제 서비스에서도 종종 하는 초기화(압축/암호화/serialize 전처리 등)
        for (int i = 0; i < payload.length; i += 4096) {
          payload[i] = (byte) (i & 0xFF);
        }

        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] d = payload;
        for (int i = 0; i < rounds; i++) {
          d = md.digest(d);
        }

        // 응답 크기는 작게 유지(요청 path CPU/GC 영향만 보려는 의도)
        exchange.getResponseHeaders().put(Headers.CONTENT_TYPE, "application/json");
        String body = "{\"hash\":\"" + toHex(d) + "\"}";
        exchange.getResponseSender().send(body);
      } finally {
        long micros = (System.nanoTime() - start) / 1000;
        RECORDER.recordValue(Math.min(micros, HIGHEST_TRACKABLE_VALUE_MICROS));
      }
    };

    Undertow server = Undertow.builder()
        .addHttpListener(port, "0.0.0.0")
        .setHandler(handler)
        .build();

    server.start();
  }

  private static Optional<Integer> queryInt(HttpServerExchange ex, String key) {
    Deque<String> values = ex.getQueryParameters().get(key);
    if (values == null || values.isEmpty()) return Optional.empty();
    try {
      return Optional.of(Integer.parseInt(values.getFirst()));
    } catch (Exception e) {
      return Optional.empty();
    }
  }

  private static String toHex(byte[] bytes) {
    char[] hex = new char[bytes.length * 2];
    final char[] alphabet = "0123456789abcdef".toCharArray();
    for (int i = 0; i < bytes.length; i++) {
      int v = bytes[i] & 0xFF;
      hex[i * 2] = alphabet[v >>> 4];
      hex[i * 2 + 1] = alphabet[v & 0x0F];
    }
    return new String(hex);
  }
}
```

### 빌드/실행

```bash
mvn -q -DskipTests package

java \
  -XX:+UseZGC \
  -Xms1g -Xmx1g \
  -XX:SoftMaxHeapSize=768m \
  -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -XX:StartFlightRecording=settings=profile,filename=app.jfr,maxsize=250m \
  -DbytesPerRequest=262144 \
  -DcpuRounds=400 \
  -jar target/latency-service-1.0.0.jar
```

- ZGC에서 heap size와 soft limit의 관계는 Oracle 문서에 정리되어 있습니다.[^2]
- ZGC에서 concurrent GC thread 개수(ConcGCThreads)는 “GC에 줄 CPU-time”을 의미한다고 설명합니다.[^3]

### 부하 생성(wrk 예시)

```bash
wrk -t4 -c128 -d60s --latency http://127.0.0.1:8080/
```

출력 예시는 형태가 이렇게 나옵니다.

```text
latency_us count=10234 p50=850 p90=2400 p99=9500 p99.9=28000 max=110000
```

여기서 중요한 건 “수치”보다 변화 방향입니다.

- SoftMaxHeapSize를 내려서 더 자주 GC가 돌게 만들 때 p99.9가 좋아지는지
- ConcGCThreads를 올렸을 때 p50은 유지되는데 tail만 흔들리는지
- gc.log에서 cycle이 잦아질수록 barrier/slow path 비용이 커지는 패턴이 있는지

이 실험틀은 OppZGC 없이도 “idle CPU를 GC에 쓰는 게 득이 될 워크로드인지”를 간접적으로 판별하는 데 도움이 됩니다.

## 컨테이너에서 꼭 같이 봐야 할 신호: cpu.stat과 active processor count

OppZGC가 메인라인에 들어오든 아니든, 이 주제는 결국 “idle이 진짜 idle인가”를 검증하는 게 절반입니다.

### 1) HotSpot이 컨테이너 CPU를 어떻게 인식했는지

- `-Xlog:os+container=trace`로 cgroup 판독 로그를 남기고
- `Runtime.getRuntime().availableProcessors()`를 앱 로그로 찍어
- 실제 active processor count가 얼마로 잡혔는지 확인하는 게 시작점입니다.

active processor count 계산이 quota/period에 영향을 받는 건 HotSpot 코드에도 드러납니다.[^5]

### 2) cgroup cpu.stat에서 throttling을 확인

Kubernetes에서 CPU limit은 throttling으로 집행됩니다.[^7]

그래서 평균 CPU 사용률 그래프가 낮아도 p99이 튈 수 있습니다. limit은 “평균”이 아니라 “대역폭(bandwidth) 제어”로 동작하기 때문입니다.

간단히는 컨테이너 안에서 아래 파일을 보게 됩니다.

- `/sys/fs/cgroup/cpu.stat` (cgroup v2)

값의 키는 환경마다 조금 다르지만, 최소한 usage 계열과 throttling 계열(횟수/시간)이 같이 보이는지 확인해야 합니다. OppZGC 논문도 multi-tenant에서는 cgroup cpu.stat 같은 per-cgroup utilization 소스를 쓰라고 직접 언급합니다.[^1]

만약 throttling이 의미 있게 관측되는 환경이라면, “idle 코어에 GC를 더 돌려 tail을 줄이자”는 접근보다 먼저 CPU limit 정책 자체가 tail의 1차 원인인지 의심해야 합니다.

## SLO/비용 관점에서의 채택 기준: 메모리를 얼마에 살 것인가, CPU를 얼마에 팔 것인가

OppZGC는 “GC를 더 돌려 heap을 줄이고, 그 결과 성능(특히 tail)을 지킨다/좋게 한다”를 목표로 합니다. 논문은 DaCapo에서 최대 heap 사용량을 평균 61%~90% 줄였다고 보고합니다(구성에 따라).[^9]

이 수치가 실전에 의미 있으려면, 조직의 비용 모델에서 메모리가 실제로 병목/비용 드라이버여야 합니다.

### 1) 메모리 비용이 지배적인 서비스

- 노드당 pod packing이 memory request에 의해 결정되는 경우
- “heap이 필요 이상으로 커서” JVM RSS가 커지고, 그 때문에 노드를 더 써야 하는 경우

이 경우 heap occupancy를 낮추는 건 곧바로 비용으로 연결됩니다. 다만 ZGC는 uncommit을 통해 OS에 메모리를 반납할 수 있고, 이를 위해서는 -Xms를 -Xmx와 같게 두지 말아야 합니다. Oracle 문서도 -Xms==-Xmx이면 uncommit이 암묵적으로 비활성화된다고 설명합니다.[^3]

즉, 이미 “고정 heap(-Xms=-Xmx) + AlwaysPreTouch”로 tail을 지키는 운영을 하고 있다면, OppZGC의 ‘heap 점유를 낮춰 footprint를 줄인다’는 가치가 바로 실현되기 어렵습니다. 이 경우 OppZGC가 주는 가치는 “같은 고정 heap에서 더 안정적인 tail” 쪽이 되어야 하는데, 그건 워크로드 의존성이 큽니다.

### 2) CPU가 지배적인 서비스

CPU가 이미 빡빡한 서비스는 OppZGC의 공간이 없습니다. 논문도 2코어 제한에서는 mutator가 거의 항상 포화라 opportunistic rule이 잘 발화하지 않으며, 그럴 때 OppZGC가 더 보수적으로 변한다고 설명합니다.[^1]

여기서 실전 기준은 간단합니다.

- p99이 SLO를 위협할 때, CPU 사용률이 70~80% 이상으로 안정적으로 높으면 OppZGC 계열은 기대치가 낮습니다.
- 반대로 p99이 튀는데 평균 CPU가 30~50%라면 “idle을 어디에 쓰고 있었나”가 질문이 됩니다.

### 3) CPU limit이 있는 Kubernetes 환경

CPU limit이 강하게 걸린 환경에서는 OppZGC의 전제(유휴 코어 활용)가 구조적으로 약해집니다. 게다가 limit은 throttling으로 집행되며, throttling은 tail에 직접 악영향을 줍니다.[^7]

따라서 채택 기준을 SLO/비용으로 쓰면 이렇게 정리됩니다.

- (SLO 우선) p99.9가 흔들리는 원인이 throttling이면, OppZGC 이전에 limit 정책을 정리하는 편이 효과가 크다.
- (비용 우선) 메모리 절감이 곧 노드 절감으로 이어지고, 동시에 CPU headroom이 실제로 존재하며, idle 관측이 신뢰 가능한 배치(전용 노드/강한 격리)라면 OppZGC는 실험 가치가 높다.

## 반론과 회의론: “idle 코어”는 운영에서 가장 불안정한 자원이다

OppZGC는 스케줄링을 잘하면 깔끔해 보이지만, 실전에서는 idle이 가장 변덕스럽습니다.

- 노이즈가 있는 멀티테넌트 노드에서는 idle이 20ms 단위로 튈 수 있습니다.
- 오토스케일 이벤트(새 pod 생성)처럼 시스템 레벨 변동이 생기면, 과거 δ 윈도우가 미래를 예측하지 못합니다.
- 논문도 past CPU utilization이 future behavior를 항상 예측하진 못하고, 그로 인해 잘못된 예측이 성능을 해칠 수 있다고 인정합니다.[^1]

또 하나는 “GC를 더 자주 돌리면 locality가 좋아진다”가 항상 성립하는 것도 아닙니다. 어떤 서비스는 heap을 크게 두고 collection 빈도를 낮추는 편이 오히려 cache/memory bandwidth 측면에서 안정적일 수 있습니다. DaCapo Chopin 쪽 연구에서도 “latency-sensitive collector가 오히려 더 나쁘다” 같은 역설이 반복적으로 등장합니다.[^4]

그래서 OppZGC는 ‘만능 튜닝’이 아니라, 실험하기 좋은 가설 생성기로 보는 편이 맞습니다.

## 도입 판단 기준: 벤치/카나리에서 무엇을 확인해야 하는가

OppZGC를 “바로 운영 적용”으로 보지 않고, “다음 주 카나리에서 검증할 수 있는 체크리스트”로 바꾸면 판단이 쉬워집니다.

1) CPU headroom의 실재
- 노드 관점: 다른 워크로드까지 포함한 실제 idle이 있는가
- cgroup 관점: throttling 없이 그 idle을 내가 쓸 수 있는가

2) tail latency의 원인 분해
- GC pause 자체(ZGC는 보통 작음)보다, concurrent interference가 tail을 흔드는가
- 혹은 CPU throttling/네트워크/락 경합이 더 큰가

3) 메모리 절감이 비용으로 연결되는 구조인지
- memory request/limit이 실제로 노드 수를 결정하는가
- heap을 줄이면 sidecar/page cache/native memory 등 다른 항목이 병목이 되지 않는가

4) 수동 튜닝으로 이미 충분히 해결되는지
- SoftMaxHeapSize 조정으로 heap occupancy를 낮추되, CPU 제한 구간에서 tail이 악화되는지(논문이 지적한 실패 모드)[^1]
- ConcGCThreads 조정으로 GC CPU를 제한했을 때 stall/throughput 손실이 생기는지[^3]

이 네 가지를 통과하면 OppZGC 같은 정책이 실제로 도움이 될 확률이 올라갑니다.

내 결론은 단순합니다. OppZGC는 “GC를 더 동시적으로” 만든 게 아니라, “동시 GC를 더 자주 돌려도 되는 순간을 찾아내는” 스케줄러입니다. 그래서 실전성의 상한은 GC가 아니라 배치/격리/limit 정책이 결정합니다. dedicated에 가까운 환경에서 메모리 비용이 아프고 CPU가 남는 서비스라면 바로 벤치/카나리 주제로 연결될 만하고, CPU quota가 빡빡하거나 멀티테넌트 노이즈가 큰 환경에서는 관측/제어부터 다시 잡아야 합니다.

## 참고 자료

- [Opportunistic ZGC: Leveraging Idle Cores for More Effective Concurrent Garbage Collection (arXiv:2609.15558)](https://arxiv.org/abs/2609.15558)
- [Opportunistic ZGC 논문 PDF](https://arxiv.org/pdf/2609.15558.pdf)
- [The Z Garbage Collector (Oracle Java SE 문서, SoftMaxHeapSize 설명)](https://docs.oracle.com/en/java/javase/11/gctuning/z-garbage-collector4.html)
- [The Z Garbage Collector (Oracle Java SE 20 문서, ConcGCThreads 및 uncommit)](https://docs.oracle.com/en/java/javase/20/gctuning/z-garbage-collector.html)
- [java Command Man Page (ConcGCThreads 옵션)](https://docs.oracle.com/en/java/javase/22/docs/specs/man/java.html)
- [HotSpot cgroupSubsystem_linux.cpp (active_processor_count 계산)](https://cr.openjdk.org/~sgehwolf/webrevs/JDK-8230305/05/webrev/src/hotspot/os/linux/cgroupSubsystem_linux.cpp.html)
- [Java 17: What’s new in OpenJDK's container awareness (Red Hat)](https://developers.redhat.com/articles/2022/04/19/java-17-whats-new-openjdks-container-awareness)
- [Resource Management for Pods and Containers (Kubernetes 공식 문서)](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [k8s-cpu-limits-analyzed: CPU throttling 실험 리포지토리](https://github.com/inevolin/k8s-cpu-limits-analyzed/)
- [Rethinking Java Performance Analysis (DaCapo Chopin, ASPLOS 2025)](https://www.dacapobench.org/assets/pdf/dacapo-asplos-2025.pdf)
- [Low-Latency, High-Throughput Garbage Collection (LXR, PLDI 2022)](https://www.steveblackburn.org/pubs/papers/lxr-pldi-2022.pdf)
- [Go 1.27 size-specialized allocations 이후 GC·지연시간 튜닝 관점](https://daewooki.github.io/posts/go-size-specialized-allocations-gc-latency/)

[^1]: <https://arxiv.org/pdf/2609.15558.pdf>
[^2]: <https://docs.oracle.com/en/java/javase/11/gctuning/z-garbage-collector4.html>
[^3]: <https://docs.oracle.com/en/java/javase/20/gctuning/z-garbage-collector.html>
[^4]: <https://www.dacapobench.org/assets/pdf/dacapo-asplos-2025.pdf>
[^5]: <https://cr.openjdk.org/~sgehwolf/webrevs/JDK-8230305/05/webrev/src/hotspot/os/linux/cgroupSubsystem_linux.cpp.html>
[^6]: <https://developers.redhat.com/articles/2022/04/19/java-17-whats-new-openjdks-container-awareness>
[^7]: <https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/>
[^8]: <https://github.com/inevolin/k8s-cpu-limits-analyzed/>
[^9]: <https://arxiv.org/abs/2609.15558>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
