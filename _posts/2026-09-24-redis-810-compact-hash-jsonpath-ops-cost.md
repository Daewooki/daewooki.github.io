---
title: "Redis 8.10: Compact Hash·JSONPath가 운영비를 흔드는 지점"
description: "Redis 8.10의 Compact Hash·JSONPath 확장을 메모리/CPU/지연시간 관점에서 해석하고, 업그레이드 전 벤치마크 시나리오를 제안합니다."
date: 2026-09-24 13:12:52 +0900
categories: ["News", "Database"]
tags: ["redis", "compact-hash", "jsonpath", "benchmarking", "performance", "operations"]
render_with_liquid: false
---

## Redis 8.10 발표에서 확인된 사실과 날짜 정리
사용자 입장에서 중요한 건 “8.10이 나왔다”보다, **언제부터 어떤 형태로 운영에 들어올 수 있나**입니다. 이번 건은 날짜가 여러 층으로 갈립니다.

- Redis 공식 블로그의 8.10 소개 글은 `September 14, 2026`로 게시되어 있습니다.[^1]  
- Redis 공식 문서의 릴리스 노트에서는 `Redis Open Source 8.10.0 (July 2026)`가 GA로 정리되어 있고, 그 이후 `8.10.1 (August 2026)`는 security urgency로 표기되어 있습니다.[^2]  
- Docker official image 문서에는 `8.10.2-alpine`, `8.10.2-alpine3.23` 같은 태그가 언급됩니다.[^3]  
- 외부 릴리스 인덱스 기준으로는 2026-09-24 시점에 8.10.2가 2026-09-17에 잡혀 있습니다(인덱스이므로 최종 판단은 Redis 릴리스 노트/태그가 기준입니다).[^4]

정리하면, “공지 글 날짜(9/14)”와 “GA 릴리스(7월)”와 “운영에서 실제로 쓰게 될 patch(8.10.1, 8.10.2)”가 분리되어 있습니다. 업그레이드 판단에서 실무적으로 중요한 건 대체로 마지막입니다. 특히 8.10.1은 문서에서 security fix가 명시되어 있어, 8.10.0을 건너뛰고 patch로 가는 흐름이 자연스럽습니다.[^2]

## 운영 비용 관점에서 8.10이 커 보이는 이유
Redis 8.10 소개에서 눈에 띄는 키워드는 세 가지입니다.

- Compact Hash: 동일한 field-name schema를 공유하는 hash의 메모리 사용을 줄이는 내부 인코딩[^5]
- JSONPath 확장: JSONPath 표현력 증가 + 일부 파싱/동작 변화[^6]
- 성능 개선: hash/streams 중심의 throughput 개선 및 메모리 효율 개선(문서/블로그에 수치가 나옵니다)[^1]

여기서 운영 비용의 축을 메모리/CPU/지연시간으로 두면, 8.10은 “명령이 몇 개 늘었다”가 아니라 “데이터 레이아웃과 서버 내부 핫패스가 바뀔 수 있다”에 가깝습니다.

- 메모리 비용: 동일한 필드명을 가진 hash가 매우 많으면 메모리 효율이 좋아질 여지가 큽니다.[^5]
- CPU 비용: 메모리를 줄이는 인코딩은 보통 CPU와 트레이드오프를 만듭니다. Redis 문서도 compact hash가 특정 패턴에서만 적합하다고 명시합니다.[^5]
- 지연시간 비용: 평균 throughput이 좋아져도 P99 tail latency가 나빠지는 형태가 자주 나옵니다. 특히 replication/slot migration/persistence 경로에서 “blob 단위 전송” 같은 특성이 tail을 건드릴 수 있습니다.[^5]

내 경우 Redis는 큐/세션/캐시를 같이 얹어 쓰는 경우가 많아서(특히 Celery + Redis 구조를 다룰 때), tail latency와 persistence 이벤트가 겹칠 때 장애가 확대되는 패턴을 자주 봤습니다. 관련 맥락은 예전에 쓴 글들에서 큐 backlog와 Redis 의존성을 길게 정리해 둔 바 있습니다.

- [LLM 백엔드 “Queued Forever”를 끝내는 법: Celery + Redis 비동기 워커 아키텍처 심층 분석](https://daewooki.github.io/posts/llm-queued-forever-celery-redis-2026-4-1/)

## Compact Hash: 메모리 절감이 만들어내는 새로운 “분포 문제”
Compact Hash의 핵심은 “field name을 key마다 저장하지 않고, 공유 가능한 field-name set을 템플릿으로 묶어서 한 번만 저장한다”입니다. Redis 문서에서 compact hash를 내부 인코딩으로 설명하고, 많은 키가 비슷한 field set을 공유할수록 이득이 커진다고 못 박습니다.[^5]

문제는 이 기능이 **키 분포(key distribution)**를 운영 관점에서 두 방향으로 바꾼다는 점입니다.

1) “키가 많을수록 이득”이므로, 팀이 자연스럽게 더 많은 객체를 hash로 쪼개고 싶어집니다. 예를 들어 user/session 객체를 string(JSON 직렬화) 대신 hash로 풀어 저장하는 유인이 커집니다.

2) 하지만 “field set의 안정성”이 전제입니다. field가 자주 늘었다 줄었다 하면 템플릿이 쪼개지고(혹은 템플릿 재해석 비용이 든다고 문서가 설명합니다), 결과적으로 템플릿 레지스트리가 분산되어 오히려 이득이 줄어들 수 있습니다.[^5]

운영 비용으로 바꿔 말하면 아래 같은 분포 리스크가 생깁니다.

- 같은 논리 도메인(user/session/order)인데도 서비스별로 필드가 미묘하게 달라 템플릿 수가 과도하게 늘어나는 경우
- A/B 실험이나 feature flag가 hash field로 직접 들어가면서(예: `ff_xxx=1`) field set이 자주 변하는 경우
- TTL churn(짧은 TTL의 세션 키가 대량 생성/만료)과 결합되어, 템플릿 이득이 나기 전에 키가 사라지는 경우

이런 조건에서는 “메모리 50% 절감” 같은 숫자가 나오는 대신, 템플릿 레지스트리 오버헤드 + 변경 비용으로 CPU가 올라가고 tail latency가 흔들리는 형태가 나올 수 있습니다. Redis 문서도 field name이 고유하거나 동적으로 변하면 오히려 불리할 수 있다고 직접 경고합니다.[^5]

## Compact Hash 내부 동작을 운영 관점으로 해석하기
Redis 문서만 봐도 충분히 위험 신호를 읽을 수 있지만, 운영 관점에서 replication/RDB를 이해하려면 구현 힌트가 필요합니다. Redis 소스(t_hash.c)에는 템플릿 레지스트리와 값 저장 방식이 어떻게 설계됐는지 요약 주석이 들어 있습니다.[^7]

핵심만 운영 관점으로 풀면 이렇습니다.

- 템플릿은 “정렬된 field set”을 key로 하여 레지스트리에 저장됩니다. field lookup은 이 정렬된 이름들에서 index를 찾고, 같은 index의 value를 읽는 방식입니다.[^7]
- 값 저장은 두 형태가 있는데(작은 hash는 더 compact한 형태, 큰 hash는 배열/다른 구조로), 공통은 “템플릿 id를 참조한다”는 점입니다. 이 id가 key마다 붙는 오버헤드이면서, 동시에 공유를 가능하게 합니다.[^7]
- RDB save 시 템플릿을 한 번 쓰고, 각 key는 템플릿 id로 참조할 수 있도록 설계되어 있습니다(주석에 명시).[^7]

이 설계는 운영 비용으로 바로 연결됩니다.

- 메모리: field name이 중복 저장되지 않으니 used_memory가 줄어드는 방향이 맞습니다. 다만 템플릿이 “충분히 공유되느냐”가 관건입니다.[^5]
- CPU: field를 추가/삭제하며 field set이 변할 때, “템플릿 재해석/새 템플릿 생성” 비용이 생깁니다. Redis 문서가 이 워크로드를 부적합으로 분류합니다.[^5]
- 지연시간: hot path(HGET/HSET overwrite)는 영향이 적다고 문서가 말하지만, schema가 변하는 write 패턴이나 persistence 이벤트, replication/migration 이벤트의 꼬리는 별개입니다.[^5]

여기서 중요한 포인트는, compact hash는 애플리케이션 코드가 직접 “인코딩을 선택”하는 모델이 아니라는 점입니다. HIMPORT로 로드하면 힌트를 줄 수 있고, 또는 서버 설정으로 자동 전환을 켤 수 있습니다.[^5]

## Compact Hash가 replication·slot migration·RDB/AOF에 주는 영향
### replication/slot migration: “single blob 전송”이 만드는 tail
Redis hash 문서에는 compact hash가 부적합한 케이스로 “hash가 매우 큰 경우”를 들면서, 이유를 replication과 slot migration에서 “single blob”으로 전송되기 때문이라고 씁니다.[^5]

운영 관점에서 이 문장 하나가 의미하는 게 큽니다.

- single blob은 수신 측에서 한 번에 처리해야 하는 덩어리라는 뜻이고, 이는 네트워크 버퍼링, 이벤트 루프, replica apply 지연에 tail을 만들 수 있습니다.
- Redis Cluster에서 resharding(슬롯 이동)이나 failover 직후 키 이동이 겹치면, 특정 대형 hash가 이동을 지연시키는 병목이 될 수 있습니다.

“큰 hash를 만들지 말자”는 일반론으로 끝내기 어렵습니다. compact hash로 이득을 보려면 애초에 “많은 hash”를 만들 가능성이 높고, 그 중 일부가 커지는 순간이 꼭 생깁니다(예: user profile에 feature map이 늘어난다든지, 세션에 디버그 필드가 누적된다든지).

따라서 compact hash를 쓰는 팀은 `hash key 크기 분포`를 이전보다 더 중요하게 봐야 합니다.

- 최대 필드 수(혹은 최대 value 총합) 기준으로 “이 이상은 hash로 저장하지 않는다” 같은 데이터 모델 규칙이 필요해집니다.
- 또는 “큰 객체는 string(JSON)로 두고, 읽기 핫한 일부만 hash로 분리한다”는 하이브리드 모델로 가는 게 더 안전할 때가 많습니다.

### RDB: 업그레이드 직후 메모리 이득을 ‘로드 시점’에 당겨올 수 있다
Redis hash 문서에는 RDB 로드 시점에 plain hash를 compact hash로 바꿔치기하는 설정이 별도로 소개됩니다. 즉, 업그레이드하자마자(재저장 없이) 메모리 이득을 얻도록 설계한 옵션입니다.[^5]

여기서 운영 비용 변수는 두 가지입니다.

- 첫 재시작(load) 시간이 늘어날 수 있습니다. 변환 작업이 로드 경로에 들어가기 때문입니다.
- 변환 결과가 “내 데이터셋에 맞는가”를 로드 중간에 판정하는 가드가 존재합니다(문서에 1,000개 이상 변환 이후 poor fit이면 변환 중단 로직이 설명됩니다).[^5]

즉, 업그레이드 직후 “왜 메모리가 확 줄었지?”만 보고 끝내면 안 되고, “로드 시간이 늘었는지”, “poor fit 판정으로 중간부터 변환이 멈췄는지”도 같이 봐야 합니다.

### AOF/MP-AOF/backup: compact hash 자체보다 ‘fork 이벤트’와 결합이 문제
Compact hash 자체는 내부 인코딩이고, AOF는 논리 명령을 기록합니다. 그래서 AOF 파일이 갑자기 compact hash 전용 포맷으로 바뀐다 같은 식의 변화는(적어도 문서상으로는) 직접 언급되지 않습니다.

다만 8.10에는 `BACKUP` 커맨드 패밀리가 들어왔고, MP-AOF 기반으로 online incremental backup/restore를 제공합니다.[^8]

운영 비용 관점에서는 다음 조합이 중요합니다.

- compact hash로 메모리가 줄면 fork 시점의 CoW 비용이 줄어드는 긍정 효과가 기대됩니다(일반론). 그러나 이건 데이터셋, allocator, dirty page 패턴에 따라 다릅니다.
- 반대로, compact hash 전환/템플릿 레지스트리 관리가 CPU를 올려서 backup window에 tail latency를 만들 수도 있습니다.

이건 문서만으로 결론을 낼 수 없고, 실제 워크로드로 “backup 시점의 P99”를 재야 합니다. 8.10은 오히려 backup을 기능으로 공식화했기 때문에, backup이 운영의 정식 이벤트로 더 자주 호출될 가능성도 높습니다.

## JSONPath 확장: 표현력이 늘면 캐시 키 설계가 먼저 흔들린다
Redis 8.10 블로그는 JSONPath 확장을 “필터링/계산/집계를 Redis 안으로 옮겨 데이터 전송을 줄이고 앱 코드를 단순화할 수 있다”는 톤으로 소개합니다.[^1]

그런데 운영 비용 관점에서는 장점보다 먼저 리스크가 보입니다.

1) CPU: JSONPath가 강해질수록 “원래 앱에서 하던 연산”을 Redis가 대신 하게 됩니다. 네트워크 I/O와 앱 CPU가 줄어드는 대신, Redis 단일 스레드(또는 제한된 I/O thread 구조) 위에 CPU가 쌓입니다.

2) 지연시간: JSONPath는 쿼리 문자열 하나로도 실행 시간이 급격히 달라집니다. 예를 들어 “상위 1개 필드 접근”과 “배열 전체를 순회하며 필터 적용”은 다른 종류의 부하입니다.

3) 캐시 키 설계: JSONPath 쿼리를 결과 캐시로 다시 감싸는 경우가 많습니다.

- 이전에는 `JSON.GET user:123 $.profile`처럼 path가 단순해서 cache key를 `(object_key, path)`로 안정적으로 만들 수 있었습니다.
- 표현력이 늘면 `(object_key, query)`가 사실상 “쿼리 문자열 전체”가 됩니다. 공백, 따옴표, bracket 표기, reserved word 회피 표기 등 미묘한 차이가 cache hit ratio를 갈라 먹습니다.

운영 비용으로 환산하면, cache miss가 늘어 Redis QPS가 증가하고(또는 upstream DB로 빠지는 비율이 바뀌고), 결국 CPU/지연시간이 요동칠 수 있습니다.

## JSONPath 확장이 만드는 호환성 리스크: reserved words·파싱·multi-match
Redis 문서는 8.10부터 JSONPath가 “더 풍부한 문법”을 지원한다고 쓰면서, 동시에 **기존 쿼리에 영향을 줄 수 있는 변경**을 경고합니다.[^6]

특히 운영에서 문제를 만드는 건 아래 두 가지입니다.

### 1) reserved words가 늘어난다
문서에 따르면 `in`, `nin`, `subsetof`, `anyof`, `noneof`, `size`, `sizeof`, `empty` 등이 operator로 예약되어, 같은 이름의 field에 접근하려면 bracket 표기 등을 써야 합니다.[^6]

실제로 JSON 스키마에 `size` 같은 필드는 흔합니다.

- payload 크기
- 페이지 사이즈
- 파일 사이즈

이런 필드를 dot notation으로 접근하던 코드가 있으면, “업그레이드 후 일부 쿼리만 깨지는” 형태의 장애가 가능합니다. 단위 테스트가 빈약한 곳에서 특히 위험합니다.

### 2) multi-match 동작과 응답 형태가 달라질 수 있다
문서는 “JSONPath query가 여러 location으로 resolve될 수 있고, 이 경우 JSON 커맨드가 가능한 모든 location에 operation을 적용한다”는 식으로 설명합니다. 그리고 “응답 구조가 legacy path query와 달라질 수 있다”고도 경고합니다.[^6]

운영에서 이게 왜 중요하냐면, “응답 형태”는 곧 애플리케이션 파서와 직결되기 때문입니다.

- 같은 쿼리라도 반환이 scalar였는데 array로 바뀌면, downstream의 JSON decode 비용이 늘거나(혹은 예외가 발생하거나) 리트라이가 폭증할 수 있습니다.
- 예외가 발생하지 않더라도, 반환 데이터 크기가 커지면 네트워크 비용이 늘고 tail latency가 상승합니다.

표현력 확장은 좋은데, 결과 shape가 바뀌는 순간 “성능 개선”이 아니라 “대규모 캐시 미스/리트라이/타임아웃”으로 바뀝니다.

## HIMPORT/자동 전환: 도입 방식 자체가 운영 비용을 갈라먹는다
Compact hash는 두 가지 방식으로 “켜질 수” 있습니다.

- `HIMPORT`를 통해 bulk import를 하고, field set을 connection-local로 준비해 값만 반복 전송[^9]
- 서버 설정으로 auto conversion을 켜서, 기존 `HSET` 워크로드를 건드리지 않고도 compact hash로 전환[^5]

### HIMPORT의 함정: fieldset은 connection-local 상태다
HIMPORT 문서는 fieldset이 “client connection에 스코프가 묶이고 연결이 닫히면 사라진다”고 명확히 씁니다.[^9]

이 문장 하나가 운영 비용을 결정합니다.

- connection pool을 쓰는 클라이언트는, PREPARE/SET이 같은 커넥션에서 실행된다는 보장이 없으면 망가집니다.
- 그래서 클라이언트 라이브러리 차원의 지원이 사실상 필수입니다.

Jedis 문서는 이 문제를 “풀링 환경에서 raw HIMPORT를 그대로 노출하면 안전하지 않다”는 관점으로 설명하고, 라이브러리가 템플릿 라이프사이클을 관리하는 방식을 소개합니다.[^10]

즉, HIMPORT는 서버 기능이라기보다 “서버 + 클라이언트 동시 업그레이드” 성격이 강합니다.

### 자동 전환의 함정: 바뀌는 건 ‘메모리’만이 아니다
Redis 문서는 auto conversion 설정들이 기본 0(off)이며 런타임에 CONFIG SET으로 바뀔 수 있다고 말합니다.[^5]

여기서 운영 리스크는 “조용히 켤 수 있다”에 있습니다.

- staging에서 메모리 절감이 좋아 보여 prod에서 켰는데, prod만 field set 다양성이 더 커서 템플릿 레지스트리가 폭증할 수 있습니다.
- prod에서는 replica, backup, resharding이 실제로 돌아가고 있어서 single blob 전송 tail이 더 쉽게 드러납니다.[^5]

## 업그레이드 전 벤치마크 시나리오: 무엇을 재야 ‘운영 비용’을 예측하나
내가 업그레이드 사전 검증을 설계할 때는, “기능 검증”과 “비용 검증”을 분리합니다. 기능은 깨지면 티가 나는데, 비용은 조용히 새는 경우가 많기 때문입니다.

아래는 Redis 8.10에서 특히 의미가 큰 시나리오들입니다.

### 1) hash schema 안정성별 메모리/CPU/지연시간
- A: 동일 field set(예: `user_id`, `email`, `country`, `last_login`)을 가진 hash 1,000만 개
- B: A에서 5% 키는 field 하나 추가(예: `debug_flag`)
- C: 필드 추가/삭제가 계속 발생(실험 플래그/동적 속성)

측정값
- `used_memory`, `used_memory_rss`, allocator fragmentation
- P50/P99 latency (HGET/HSET overwrite vs HSET new-field)
- 템플릿 관련 카운터

Redis 8.10 문서에는 compact hash 템플릿 수/키 수/메모리 관련 지표가 추가되었다고 되어 있습니다.[^11]

또한 `MEMORY USAGE <key>`가 compact hash에서는 템플릿 비용의 share까지 포함해 보고한다고 문서에 명시되어 있어, 8.8과 8.10의 수치 비교에서 기준을 맞춰야 합니다.[^12]

### 2) replication/cluster resharding tail
- primary에 write load를 걸고 replica lag 추이 관찰
- 특정 크기 이상 hash를 일부러 만들어 “single blob 전송” tail 여부 확인[^5]

측정값
- replica offset/lag
- `INFO`의 replication 섹션
- 애플리케이션 레벨 P99(특히 timeout/retry가 있는 클라이언트)

### 3) persistence 이벤트와 동시 부하
- `BGSAVE` / AOF rewrite / 8.10 `BACKUP START/SEAL`를 부하와 겹쳐 실행[^8]

측정값
- fork 시점 latency spike
- CoW 관련 메모리 급증
- backup artifact 크기와 소요시간

### 4) JSONPath 쿼리 호환성과 결과 shape
- 기존 쿼리에서 field name에 reserved words가 섞였는지 검사 (`size`, `empty` 등)[^6]
- multi-match가 발생하는 JSONPath를 일부러 만들어 응답 구조가 바뀌는지 확인[^6]

측정값
- 응답 payload 크기 변화
- 애플리케이션 파서 예외율
- Redis CPU 사용률

## 벤치마크 구현 예시: Docker Compose + memtier + HIMPORT 로더
아래는 “업그레이드 전 비용 비교”를 위한 최소 구성입니다.

- Redis 8.8.3 vs Redis 8.10.2를 같은 머신에서 번갈아 띄움(동일 리소스)
- memtier_benchmark로 steady-state read/write 부하를 만들어 P99를 봄
- 데이터 로드는 HSET 버전과 HIMPORT 버전을 둘 다 준비해 “도입 방식 차이”를 비교

Redis Docker 태그는 공식 이미지의 tags 페이지에서 8.8.3과(예: `redis:8.8.3`) 8.10.2 계열이 확인됩니다.[^13]

### docker-compose.yml

```yaml
services:
  redis88:
    image: redis:8.8.3
    ports:
      - "6388:6379"
    command: ["redis-server", "--save", "", "--appendonly", "no"]

  redis810:
    image: redis:8.10.2
    ports:
      - "6810:6379"
    command: ["redis-server", "--save", "", "--appendonly", "no"]

  memtier:
    image: redislabs/memtier_benchmark:2.5.1
    entrypoint: ["sleep", "infinity"]
```

memtier_benchmark는 Docker 이미지로 단독 실행이 가능하다고 Redis 측 FAQ/이미지 문서에서 안내합니다.[^14]

실행:

```bash
docker compose up -d
```

### 데이터 로더: HSET vs HIMPORT
#### 1) gen_hash_load.py

```python
#!/usr/bin/env python3
import argparse
import random
import string

def randid(n: int) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["hset", "himport"], required=True)
    ap.add_argument("--keys", type=int, required=True)
    ap.add_argument("--prefix", default="sess")
    ap.add_argument("--ttl", type=int, default=3600)
    args = ap.parse_args()

    # session-like schema: stable fields
    fields = ["uid", "email", "country", "last_login", "flags"]

    if args.mode == "himport":
        # fieldset name: u
        print("HIMPORT PREPARE u " + " ".join(fields))

    for i in range(1, args.keys + 1):
        key = f"{args.prefix}:{i}"
        uid = str(i)
        email = f"u{i}@example.com"
        country = random.choice(["US", "KR", "JP", "DE", "FR", "GB"])
        last_login = str(1720000000 + (i % 100000))
        flags = randid(16)

        if args.mode == "hset":
            # single HSET with multiple field/value pairs
            cmd = ["HSET", key]
            for f, v in zip(fields, [uid, email, country, last_login, flags]):
                cmd += [f, v]
            print(" ".join(cmd))
        else:
            # HIMPORT SET key fieldset values...
            values = [uid, email, country, last_login, flags]
            cmd = ["HIMPORT", "SET", key, "u"] + values
            print(" ".join(cmd))

        if args.ttl > 0:
            print(f"EXPIRE {key} {args.ttl}")

if __name__ == "__main__":
    main()
```

#### 2) 로드 실행

Redis 8.8.3(6388):

```bash
python3 gen_hash_load.py --mode=hset --keys=1000000 \
  | docker exec -i $(docker compose ps -q redis88) redis-cli --pipe
```

Redis 8.10.2(6810), HSET 로드:

```bash
python3 gen_hash_load.py --mode=hset --keys=1000000 \
  | docker exec -i $(docker compose ps -q redis810) redis-cli --pipe
```

Redis 8.10.2(6810), HIMPORT 로드:

```bash
python3 gen_hash_load.py --mode=himport --keys=1000000 \
  | docker exec -i $(docker compose ps -q redis810) redis-cli --pipe
```

HIMPORT는 문서에서 “shared field names를 connection-local로 준비하고 값만 전송한다”는 모델로 설명되어 있습니다.[^9]

#### 3) compact hash 적용 여부 확인(관찰용)
compact hash는 내부 인코딩이라, 확인은 간접적으로 합니다.

- Redis 8.10에서 `INFO`/`MEMORY`에 템플릿 관련 지표가 추가됩니다.[^11]
- `MEMORY USAGE`는 compact hash일 때 템플릿 share까지 포함한다고 문서에 명시돼 있어, 키 단위 메모리 점검에 유용합니다.[^12]

예:

```bash
docker exec -it $(docker compose ps -q redis810) redis-cli INFO memory | egrep 'used_memory|hash'

docker exec -it $(docker compose ps -q redis810) redis-cli MEMORY USAGE sess:1
```

### steady-state 부하: memtier_benchmark
로드가 끝난 후, 읽기/쓰기 비율을 고정하고 P99가 흔들리는지 봅니다.

```bash
# Redis 8.8.3
docker exec -it $(docker compose ps -q memtier) \
  memtier_benchmark -s redis88 -p 6379 \
  --ratio=1:9 --command="HGET __key__ uid" --command-ratio=9 \
  --command="HSET __key__ flags __data__" --command-ratio=1 \
  --key-pattern=R:R --key-maximum=1000000 \
  --data-size=16 -t 4 -c 25 --test-time=60 \
  --print-percentiles 50,90,99,99.9

# Redis 8.10.2
docker exec -it $(docker compose ps -q memtier) \
  memtier_benchmark -s redis810 -p 6379 \
  --ratio=1:9 --command="HGET __key__ uid" --command-ratio=9 \
  --command="HSET __key__ flags __data__" --command-ratio=1 \
  --key-pattern=R:R --key-maximum=1000000 \
  --data-size=16 -t 4 -c 25 --test-time=60 \
  --print-percentiles 50,90,99,99.9
```

여기서 기대하는 관찰 포인트는 아래입니다.

- compact hash가 “읽기와 overwrite 업데이트는 영향이 적다”고 문서에 적혀 있으므로, steady-state overwrite가 대부분인 워크로드에서는 큰 차이가 없을 가능성이 있습니다.[^5]
- 반대로, `HSET`으로 새로운 field를 추가하는 패턴이 섞이면(예: flags가 아니라 `new_feature_flag` 같은 신규 필드 추가), 템플릿 분해/재해석 비용이 tail에 반영될 수 있습니다. 문서가 “field name이 자주 바뀌면 부적합”이라고 직접 경고합니다.[^5]

### JSONPath 호환성 체크(최소)
Redis 8에 JSON이 포함되는 구성인지부터 확인이 필요합니다. 가장 단순한 확인은 `COMMAND INFO JSON.SET`입니다.

```bash
docker exec -it $(docker compose ps -q redis810) redis-cli COMMAND INFO JSON.SET
```

그 다음 reserved words/tilde 파싱 변화가 있는 쿼리들을 regression 목록에 올려야 합니다. 문서가 8.10에서 tilde 접근과 reserved words를 명시적으로 경고합니다.[^6]

## 반론과 회의론: 비용은 줄지만 복잡도는 늘 수 있다
### “메모리 50% 줄면 무조건 이득 아닌가?”
compact hash의 메모리 절감은 “동일 field set 공유”가 전제입니다. field set 다양성이 높으면 오히려 템플릿 메타데이터가 오버헤드가 될 수 있고, Redis 문서가 그 케이스를 부적합으로 분류합니다.[^5]

또한 대형 hash가 존재하는 데이터셋에서 replication/slot migration blob 전송이 tail을 만들 수 있다는 경고도 문서에 들어 있습니다.[^5]

결국 “메모리 절감”은 확률적으로 맞지만, “운영 비용 절감”은 워크로드 특성을 더 많이 탑니다.

### “JSONPath를 Redis로 옮기면 앱이 단순해진다”
앱이 단순해지는 건 맞을 수 있는데, 운영비는 다르게 움직일 수 있습니다.

- 네트워크 왕복/전송량이 줄어드는 대신, Redis CPU가 올라가고 latency tail이 늘어날 수 있습니다.
- JSONPath 확장에는 파싱/예약어/응답 형태 변화 같은 호환성 리스크가 동반됩니다.[^6]

그리고 JSONPath의 표준화(RFC 9535)는 “이식성과 합의를 위해 backwards compatibility가 항상 보장되지 않는다”는 문제의식을 배경으로 깔고 있습니다. 즉, JSONPath는 원천적으로 구현체별 차이를 품고 있고, Redis가 확장을 통해 기능을 늘릴수록 팀이 감당해야 하는 회귀 테스트 범위가 커집니다.[^15]

## 앞으로 지켜볼 것: 템플릿 레지스트리와 patch 릴리스 흐름
1) compact hash의 핵심 지표는 “절감률”이 아니라 `template 수 대비 key 수`입니다.
- template 수가 키 수에 비해 너무 빨리 늘면, 데이터 모델이 compact hash에 안 맞을 가능성이 큽니다.
- Redis 8.10 문서에 템플릿 관련 metrics가 추가된 것도 이 관찰을 공식화한 신호로 읽힙니다.[^11]

2) patch 버전 흐름이 security 중심으로 갈 가능성이 높습니다.
- 8.10.1이 security urgency로 표기된 상태라면, 프로덕션은 8.10.0에서 멈추기 어렵습니다.[^2]

3) 클라이언트 라이브러리 대응이 업그레이드 성공의 일부입니다.
- HIMPORT는 connection-local state를 쓰는 구조라, pooling/cluster 환경에서는 클라이언트 지원이 사실상 필요합니다.[^9]

결론적으로 Redis 8.10은 기능 소개만 보면 “메모리 효율과 표현력 개선”인데, 운영 비용 관점에서는 “데이터 레이아웃과 쿼리 패턴이 바뀌는 순간 tail latency와 장애 양상이 달라지는 릴리스”에 가깝습니다.

## 참고 자료
- [Announcing Redis 8.10: Compact Hash, JSONPath extensions, performance improvements, & more](https://redis.io/blog/announcing-redis-810-compact-hash-jsonpath-extensions-performance-improvements-and-more/)
- [Redis 8.10 문서(What’s new)](https://redis.io/docs/latest/develop/whats-new/8-10/)
- [Redis Open Source 8.10 release notes](https://redis.io/docs/latest/operate/oss_and_stack/stack-with-enterprise/release-notes/redisce/redisos-8.10-release-notes/)
- [Redis Hashes 문서의 Compact hashes 섹션](https://redis.io/docs/latest/develop/data-types/hashes/)
- [HIMPORT 커맨드 문서](https://redis.io/docs/latest/commands/himport/)
- [Redis JSONPath 문서(Path)](https://redis.io/docs/latest/develop/data-types/json/path/)
- [MEMORY USAGE 커맨드 문서](https://redis.io/docs/latest/commands/memory-usage/)
- [Redis Docker official image 개요](https://hub.docker.com/_/redis)
- [redis Docker tags](https://hub.docker.com/_/redis/tags)
- [redis-py(PyPI redis 패키지)](https://pypi.org/project/redis/)
- [RFC 9535: JSONPath: Query Expressions for JSON](https://www.rfc-editor.org/rfc/rfc9535.html)
- [Redis 소스: compact hash 템플릿 주석(t_hash.c)](https://github.com/redis/redis/blob/unstable/src/t_hash.c)
- [memtier_benchmark Docker 이미지](https://hub.docker.com/r/redislabs/memtier_benchmark/)

[^1]: <https://redis.io/blog/announcing-redis-810-compact-hash-jsonpath-extensions-performance-improvements-and-more/>
[^2]: <https://redis.io/docs/latest/operate/oss_and_stack/stack-with-enterprise/release-notes/redisce/redisos-8.10-release-notes/>
[^3]: <https://hub.docker.com/_/redis?trk=article-ssr-frontend-pulse_little-text-block>
[^4]: <https://releases.sh/redis>
[^5]: <https://redis.io/docs/latest/develop/data-types/hashes/>
[^6]: <https://redis.io/docs/latest/develop/data-types/json/path/>
[^7]: <https://github.com/redis/redis/blob/unstable/src/t_hash.c>
[^8]: <https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/>
[^9]: <https://redis.io/docs/latest/commands/himport/>
[^10]: <https://redis.github.io/jedis/hash-import/>
[^11]: <https://redis.io/docs/latest/develop/whats-new/8-10/>
[^12]: <https://redis.io/docs/latest/commands/memory-usage/>
[^13]: <https://hub.docker.com/_/redis/tags>
[^14]: <https://hub.docker.com/r/redislabs/memtier_benchmark/>
[^15]: <https://www.rfc-editor.org/rfc/rfc9535.html>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
