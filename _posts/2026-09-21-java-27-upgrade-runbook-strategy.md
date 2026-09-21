---
title: "Java 27 GA: PQC·성능·프리뷰가 섞인 릴리스에서 업그레이드 전략을 나누는 법"
description: "Java 27의 디폴트 변경(보안·관측성·GC/메모리)과 preview·incubator를 분리해 팀별 업그레이드 런북으로 정리합니다."
date: 2026-09-21 09:51:17 +0900
categories: ["News", "Languages"]
tags: ["java", "jdk27", "pqc", "observability", "ci-matrix", "upgrade-runbook"]
render_with_liquid: false
---

## 2026-09-15 Java 27 GA에서 실제로 일어난 일

Java 27은 2026-09-15에 GA로 릴리스됐고, Oracle 발표 기준으로 9개의 JEP를 포함합니다. 핵심 메시지는 새 문법을 대대적으로 넣는 릴리스가 아니라, **TLS/암호(PQC 포함)·런타임 디폴트·진단** 쪽 변화가 많다는 점입니다. 발표문에 나온 9개 JEP는 다음으로 정리됩니다. [Oracle 보도자료](https://www.oracle.com/news/announcement/oracle-releases-java-27-and-strengthens-post-quantum-cryptography-support-2026-09-15/)

- 보안/암호
  - JEP 527: TLS 1.3 Post-Quantum Hybrid Key Exchange
  - JEP 538: PEM Encodings of Cryptographic Objects (Third Preview)
- 관측성/진단
  - JEP 536: JFR In-Process Data Redaction
- 런타임/성능
  - JEP 523: G1을 모든 환경에서 default GC로
  - JEP 534: Compact Object Headers by Default
- 프리뷰/인큐베이터
  - JEP 531: Lazy Constants (Third Preview)
  - JEP 532: Primitive Types in Patterns/instanceof/switch (Fifth Preview)
  - JEP 533: Structured Concurrency (Seventh Preview)
  - JEP 537: Vector API (12th Incubator)

이 중 운영에 바로 영향을 주는 것은 “새 API를 써야만 효과가 나는 변화”가 아니라 “업그레이드만 하면 기본값이 달라지는 변화”입니다. Oracle 기술 블로그도 ‘javax.net.ssl를 쓰는 애플리케이션은 기본적으로 이득을 본다’고 못 박습니다. 특히 JEP 527은 기존 코드 변경 없이 기본으로 적용된다는 점을 강조합니다. [The Arrival of Java 27](https://blogs.oracle.com/java/the-arrival-of-java-27)

그리고 Java 27은 비-LTS이지만 “어차피 나중에”라고 미루는 쪽이 더 위험해질 수 있는 이유가 하나 더 있습니다. 릴리스 후 6개월 단위로 다음 버전이 나오고, Oracle은 Java 27 업데이트 제공 시점을 2027-03로 명시합니다. 즉, 2026-09-15 GA 이후 2027-03까지가 ‘27을 운영에서 써볼 수 있는 창’이고, 이 창에서 보안/운영 이점을 얻거나(혹은 문제를 겪고) 다음 의사결정으로 넘어가게 됩니다. [The Arrival of Java 27](https://blogs.oracle.com/java/the-arrival-of-java-27)

## 이 릴리스가 어려운 이유: “기능 도입”이 아니라 “기본값 이동”이 섞여 있습니다

Java 릴리스마다 업그레이드 난이도를 결정하는 건 JEP 숫자가 아니라, 다음 두 가지가 동시에 존재하느냐입니다.

1) 디폴트가 바뀌어 운영이 달라짐(암호 협상, GC 선택, 메모리 레이아웃, 진단 데이터의 내용)

2) preview/incubator가 계속 누적돼 “다음 LTS에 들어갈 것 같은데 아직은 아닌 기능”이 팀별로 유혹을 만듦

Java 27은 1)과 2)가 강하게 섞여 있습니다. JetBrains 글도 Java 27의 포지션을 사실상 이렇게 정리합니다. “9개 JEP 중 4개가 final, 4개는 preview, 1개는 incubator.” 그리고 IntelliJ IDEA는 Java 27을 day-one으로 지원하되, preview는 ‘현재 JDK에서만’ 지원한다고 선을 그습니다. [Java 27 in IntelliJ IDEA](https://blog.jetbrains.com/idea/2026/09/java-27-in-intellij-idea/)

내 경험상 이런 릴리스에서 가장 흔한 실패는 다음 둘 중 하나로 귀결됩니다.

- 전사 공통 정책으로 “그냥 다 올리자” → toolchain/서드파티에서 깨지고, 롤백이 늦어지면서 조직 전체가 27을 불신
- 전사 공통 정책으로 “그냥 다 미루자” → 디폴트 변경(특히 보안/관측성)에서 얻을 수 있는 이점을 버리고, 다음 릴리스 때 한꺼번에 폭발

그래서 이번에는 (1) 즉시 적용군(보안/관측성/런타임 디폴트), (2) 실험군(프리뷰/인큐베이터), (3) 보류군(툴체인/서드파티)로 나눠서 ‘팀이 다르게 움직일 수 있게’ 런북 형태로 정리하는 게 맞습니다.

## (1) 즉시 적용군: 보안/관측성/런타임 디폴트 변화

### 1) TLS 1.3에 PQC hybrid key exchange가 들어옵니다 (JEP 527)

JEP 527은 “TLS 1.3의 key exchange에 hybrid(named group)를 추가”하는 변화입니다. Oracle 기술 블로그는 이 변화가 `javax.net.ssl` 기반 애플리케이션에 기본으로 적용된다고 설명합니다. [The Arrival of Java 27](https://blogs.oracle.com/java/the-arrival-of-java-27)

Oracle의 Java 27 통합 릴리스 노트는, 3개의 hybrid key exchange 알고리즘을 새로 지원한다고 적습니다.

- `X25519MLKEM768`
- `SecP256r1MLKEM768`
- `SecP384r1MLKEM1024`

그리고 이 중 `X25519MLKEM768`을 default named groups 리스트의 맨 앞에 둬서 가장 선호되는 그룹이 되도록 합니다. [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)

여기서 운영 리스크는 “우리 앱이 PQC API를 쓰지 않는다”가 아닙니다. **우리가 TLS 1.3을 쓰고 있으면 협상 패턴이 바뀔 수 있다**가 리스크입니다. 실제로 Inside.java 글도 “기본값에서는 TLS client가 key share를 2개(하나는 `X25519MLKEM768`, 하나는 `x25519`) 제공한다”고 못 박습니다. [Post-Quantum Hybrid Key Exchange for TLS 1.3](https://inside.java/2026/02/17/tls-post-quantum-hybrid-key-exchange/)

즉시 적용군에 넣는 이유는 단순합니다.

- 조직이 TLS를 이미 운영하고 있다면, “업그레이드만으로” 보안 posture가 바뀌는 영역입니다.
- 반대로 업그레이드를 미루면, hybrid가 들어온 뒤의 실전 호환성(미들박스/프록시/구형 TLS terminate 장비)을 검증할 시간을 잃습니다.

그리고 이 기능은 끄거나 우회할 방법이 명확합니다. Inside.java는 hybrid key exchange 지원을 커스터마이즈하는 방법을 두 가지로 제시합니다.

- `jdk.tls.namedGroups` system property 설정
- `SSLParameters::setNamedGroups`로 socket 단위 제어

예시 코드까지 제공합니다. [Post-Quantum Hybrid Key Exchange for TLS 1.3](https://inside.java/2026/02/17/tls-post-quantum-hybrid-key-exchange/)

이 “명확한 우회/롤백 스위치가 있다”는 점 때문에, 나는 JEP 527을 즉시 적용군으로 분류하는 쪽이 맞다고 봅니다.

### 2) TLS 관련 non-JEP 디폴트도 같이 봐야 합니다

PQC만 보고 들어가면 놓치는 지점이 있습니다. Java 27 통합 릴리스 노트에는 TLS 관련 디폴트 변화가 더 있습니다.

- TLS certificate compression이 default로 켜집니다.
  - 끄려면 `jdk.tls.client.disableExtensions`와 `jdk.tls.server.disableExtensions`에 `compress_certificate`를 추가합니다. [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
- TLS 1.3 key agreement 구현 디테일이 바뀝니다.
  - Diffie-Hellman shared secret에서 `TlsPremasterSecret` 대신 `Generic` key algorithm을 쓰도록 바뀌었고, 일부 JCE provider가 `Generic`을 지원하지 않으면 핸드셰이크가 실패할 수 있다고 경고합니다.
  - 이때는 system property `jdk.tls.t13KeyDerivationAlgorithm`을 `TlsPremasterSecret`으로 설정해서 원래 동작으로 되돌릴 수 있다고 적혀 있습니다. [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)

이 두 개는 PQC와 결합될 때 “TLS 쪽에서 뭔가 이상하다”라는 장애 형태로 뭉쳐서 나타날 수 있습니다. 그래서 런북에는 반드시 TLS 관련 롤백 스위치를 한곳에 모아둬야 합니다.

### 3) JFR이 비밀 값을 기본으로 redaction합니다 (JEP 536)

JEP 536은 운영팀 입장에서 이번 릴리스의 가장 즉각적인 수확입니다. Java 27부터 JFR이 기본적으로 다음을 redaction합니다.

- command-line arguments
- environment variables의 초기값
- system properties의 초기값

그리고 이 redaction은 “레코딩 파일이 만들어진 뒤에 지우는 방식”이 아니라, 프로세스 안에서 빠져나가기 전에 redaction하는 방식이라고 요약됩니다. [Oracle Java 27 보도자료](https://www.oracle.com/news/announcement/oracle-releases-java-27-and-strengthens-post-quantum-cryptography-support-2026-09-15/) / [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)

Oracle의 “Important Changes” 릴리스 노트는, 기본 redaction을 끄는 방법과 커스텀 필터를 추가하는 방법을 구체적으로 제공합니다.

- 커스텀 필터 추가: `-XX:FlightRecorderOptions:redact-key=+<filter>`, `-XX:FlightRecorderOptions:redact-argument=+<filter>`
- 기본 redaction 비활성화: `-XX:FlightRecorderOptions:redact-key=none,redact-argument=none` [JDK 27 Release Notes (Important Changes)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

이건 “보안 기능”이면서 동시에 “관측성 품질”에도 영향을 줍니다. 예를 들어 지금까지는 JFR을 공유할 때 민감정보가 포함될 수 있어 조직에서 JFR 사용을 꺼리는 경우가 있었는데, 기본 redaction이 들어오면 JFR을 더 넓게 배포할 수 있습니다.

### 4) 실행 중 보안 프로퍼티를 `jcmd`로 확인할 수 있습니다

Java 27 릴리스 노트에는 `jcmd`에 `VM.security_properties` 커맨드가 추가됐다고 적혀 있습니다. 이 커맨드는 실행 중 JVM이 어떤 Java security property를 활성화하고 있는지 출력합니다. [JDK 27 Release Notes (Important Changes)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

보안 쪽에서 흔한 장애가 “설정이 먹었는지”를 확인하는 데서 시작합니다.

- 컨테이너 이미지에 들어간 `java.security`
- `-Djava.security.properties` 또는 include 체인
- vendor 이미지가 추가한 security property
- 런타임에서 주입된 프로퍼티

이걸 프로세스 안을 뒤져서 맞춰보는 대신, `jcmd` 한 번으로 확인할 수 있게 되면 운영 런북이 단순해집니다.

추가로, Sean Mullan의 정리 글에는 `jdk.security.password.allowSystemIn` 같은 새 보안 프로퍼티 언급도 있습니다. 이런 종류의 변화는 애플리케이션 코드가 아니라 운영 환경(표준 입력 존재 여부, 패스워드 입력 경로)에 영향을 주기 때문에 “즉시 적용군”의 체크리스트에 넣어두는 게 안전합니다. [JDK 27 Security Enhancements](https://seanjmullan.org/blog/2026/09/15/jdk27)

### 5) GC/메모리 디폴트가 운영 비용을 건드립니다 (JEP 523, JEP 534)

보안/관측성만큼 직접적인 취약점 대응은 아니지만, Java 27의 런타임 디폴트 변화는 비용과 안정성을 동시에 건드립니다.

- JEP 523: “모든 환경에서 G1이 default GC”
  - JetBrains 글은 기존 예외를 구체적으로 적습니다. Java 9부터 G1이 default였지만, CPU 1개 또는 RAM 1792MB 미만 환경에서는 Serial GC로 fallback 했고, JEP 523이 이를 제거해서 모든 환경에서 G1을 default로 만든다는 설명입니다. [Java 27 in IntelliJ IDEA](https://blog.jetbrains.com/idea/2026/09/java-27-in-intellij-idea/)
  - Oracle 기술 블로그는 “이전에는 Serial을 선택하던 시나리오에서도 throughput/latency/memory footprint/startup time이 크게 나빠지지 않아야 한다”는 목표를 명시합니다. [The Arrival of Java 27](https://blogs.oracle.com/java/the-arrival-of-java-27)

- JEP 534: Compact Object Headers가 default
  - JetBrains는 64-bit 아키텍처에서 object header를 96-bit에서 64-bit로 줄인다고 적습니다. [Java 27 in IntelliJ IDEA](https://blog.jetbrains.com/idea/2026/09/java-27-in-intellij-idea/)
  - Java 27 통합 릴리스 노트는 이 기능을 끄는 플래그를 명시합니다: `-XX:-UseCompactObjectHeaders`. 그리고 이 플래그는 향후 deprecate/remove 예정이라고도 적습니다. [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)

GC와 object header는 애플리케이션 팀이 기능 단위로 도입할 수 있는 게 아닙니다. 플랫폼/인프라 팀이 “런타임을 올리는 순간” 같이 들어옵니다. 그래서 나는 이 두 개를 즉시 적용군으로 분류하되, **항상 롤백 플래그를 같이 묶어** 배포하는 쪽으로 정리합니다.

ZGC 같은 다른 GC를 적극적으로 튜닝해온 팀은 “default가 바뀐다” 자체가 큰 의미가 없을 수도 있습니다. 다만 이 경우에도 배포 스펙에 `-XX:+UseZGC` 같은 명시를 유지하고 있는지, 혹은 어딘가에서 default 의존이 있었는지를 확인하는 계기가 됩니다. GC를 운영에서 적극적으로 만져온 케이스는 예전 글에서 따로 다뤘고, 여기서는 런북 관점만 적습니다. [OppZGC: 유휴 코어를 쓰는 ZGC 스케줄링의 실전성](https://daewooki.github.io/posts/opportunistic-zgc-idle-core-scheduling/)

## 즉시 적용군 런북: “실행 환경만 27”로 먼저 분리합니다

즉시 적용군의 목적은 단순합니다.

- 코드 변경 없이 얻는 보안/관측성/비용 이점을 먼저 가져옵니다.
- preview/incubator는 끼워 넣지 않습니다.
- toolchain을 한 번에 흔들지 않습니다.

여기서 가장 중요한 운영 기술은 “컴파일 JDK”와 “런타임 JDK”를 분리하는 겁니다. Java 27에는 “새 언어 기능이 없다”고 JetBrains 문서가 명시합니다. 즉, 언어 레벨 변화로 인해 빌드 체인이 흔들리는 타입의 업그레이드가 아닙니다. [Supported Java versions and features](https://www.jetbrains.com/help/idea/supported-java-versions.html)

내가 운영에서 추천하는 1차 목표 상태는 다음입니다.

- 빌드/테스트 실행(JUnit, Gradle/Maven daemon 등)은 기존 안정 구간의 JDK 유지
- 프로덕션 런타임(컨테이너 이미지, VM 설치본)은 Java 27로 올려서 JEP 527/536/523/534를 실제 트래픽에서 검증

이게 가능한 이유는 Java 27이 “새 문법”이 아니라 “런타임/보안/진단”이 중심이기 때문입니다.

### 단계 0: 릴리스 노트 기반의 영향도 표를 먼저 만듭니다

이 릴리스에서 운영 장애를 부를 수 있는 지점은 “우리 코드”가 아니라 “우리 런타임 옵션/주변 인프라”에 있습니다.

- TLS: hybrid key exchange 선호, certificate compression default, TLS 1.3 shared secret key algorithm 변경(`Generic`), 롤백 프로퍼티 존재
  - [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
- JFR: redaction default, 비활성화 옵션/커스텀 필터 옵션 존재
  - [JDK 27 Release Notes (Important Changes)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- HotSpot 옵션: `UseCompressedClassPointers`가 obsolete가 되어 warning이 발생
  - [JDK 27 Release Notes (Important Changes)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- Compact Object Headers: default, 비활성화 플래그 존재(향후 제거 예정)
  - [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)

이 표를 만든 뒤, “바뀐 디폴트는 무엇이고, 롤백 스위치는 무엇인가”를 한 줄씩 붙입니다. 이 작업이 끝나면 업그레이드는 절반이 끝납니다.

### 단계 1: CI 매트릭스를 ‘기능 테스트’가 아니라 ‘디폴트 변경 검증’ 중심으로 설계합니다

Java 27 업그레이드 CI는 “우리 서비스가 정상 동작한다”보다 “디폴트 변경이 실제로 발동했고, 발동했을 때 장애가 없는지”를 보는 쪽이 유효합니다.

다음은 즉시 적용군에 권하는 최소 매트릭스입니다.

| 축 | 값 | 목적 |
|---|---|---|
| 런타임 JDK | 기존(예: 21/25/26 중 조직 표준) + 27 | 27로 실행했을 때만 터지는 문제를 잡음 |
| TLS 경로 | (a) 내부 서비스 간 mTLS, (b) 외부 API 호출, (c) 프록시 경유 | hybrid/압축/키 파생 변화가 어디서 깨지는지 분리 |
| JFR 수집 | on/off + 레코딩 공유 경로 | redaction이 실제로 민감정보 유출을 줄이는지 확인 |
| GC | default(G1) + 기존 명시 옵션(ZGC/Parallel 등) | default 변화에 의한 예기치 않은 튜닝 회귀 확인 |
| 플래그 롤백 | TLS/COH/JFR 각각 롤백 | 장애 시 즉시 복구 가능한지 확인 |

이 매트릭스는 “모든 테스트를 2배로 돌리자”가 아니라, **딱 바뀐 디폴트만 스모크 테스트로 찌른다**에 초점이 있습니다.

### 단계 2: 런타임 플래그 정책을 ‘기본값 + 핫픽스 스위치’로 가져갑니다

즉시 적용군에서 중요한 건 “운영 플래그를 늘리지 않는 것”과 “필요할 때만 켤 스위치를 준비하는 것”을 동시에 달성하는 겁니다.

내가 보통 두는 운영 원칙은 이렇습니다.

- 평소에는 Java 27 default를 그대로 둡니다.
- 장애 시에만 롤백 스위치를 넣고, 복구 후 스위치를 제거합니다.

Java 27은 롤백 스위치가 비교적 명확하게 문서화돼 있습니다.

- COH 비활성화: `-XX:-UseCompactObjectHeaders` [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
- JFR redaction 비활성화: `-XX:FlightRecorderOptions:redact-key=none,redact-argument=none` [JDK 27 Release Notes (Important Changes)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- TLS 1.3 key derivation 롤백: `-Djdk.tls.t13KeyDerivationAlgorithm=TlsPremasterSecret` [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
- TLS certificate compression 비활성화: `-Djdk.tls.client.disableExtensions=compress_certificate` 및 server도 동일 [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
- hybrid named groups 제어: `jdk.tls.namedGroups` 또는 socket 단위 `SSLParameters::setNamedGroups` [Post-Quantum Hybrid Key Exchange for TLS 1.3](https://inside.java/2026/02/17/tls-post-quantum-hybrid-key-exchange/)

즉시 적용군 런북에는 이 값을 “운영 위키”에 흩뿌려놓지 말고, 배포 레포지토리 안의 `runbooks/java27.md` 같은 한 파일에 박아두는 게 낫습니다.

### 단계 3: 롤백 플랜은 ‘JDK 버전 롤백’과 ‘플래그 롤백’을 둘 다 준비합니다

Java 업그레이드의 흔한 착각이 “버전만 내리면 된다”입니다. 이번 릴리스는 TLS/JFR/메모리의 디폴트가 바뀌기 때문에, 장애 양상이 다양합니다.

- 어떤 문제는 `-Djdk.tls...` 하나로 바로 복구됩니다.
- 어떤 문제는 런타임 이미지 자체를 내리는 게 더 빠릅니다(예: 서드파티 agent가 27에서만 깨질 때).

그래서 런북에는 롤백 경로를 두 겹으로 둡니다.

1) 런타임 이미지 롤백
   - 이전 JDK 기반 이미지 태그를 상시 보관
   - canary에서만 27 태그를 사용하도록 배포 파이프라인 분기

2) 런타임 플래그 롤백
   - TLS/COH/JFR 롤백 스위치 세트는 환경변수 한 덩어리로 주입 가능하게 구성(예: `JAVA_TOOL_OPTIONS`)

이렇게 해두면 장애 대응에서 “JDK를 내릴지, 옵션만 바꿀지”를 그때그때 선택할 수 있습니다.

## (2) 실험군: preview·incubator는 ‘기능’이 아니라 ‘연구 개발 장비’로 취급합니다

Java 27의 preview/incubator는 양이 많습니다. 그리고 반복 프리뷰가 섞여 있습니다.

- JEP 532: primitive types in patterns/instanceof/switch (5th preview)
- JEP 531: lazy constants (3rd preview)
- JEP 533: structured concurrency (7th preview)
- JEP 538: PEM encodings (3rd preview)
- JEP 537: Vector API (12th incubator)

JetBrains는 preview를 IDE에서 실험할 수 있게 적극 지원하지만, 동시에 “preview는 바뀔 수 있고, 현재 JDK에 대해서만 지원한다”는 운영 철학을 분명히 합니다. [Java 27 in IntelliJ IDEA](https://blog.jetbrains.com/idea/2026/09/java-27-in-intellij-idea/)

Vector API는 incubator이기 때문에 더 강하게 선을 긋습니다. 쓰려면 `--add-modules jdk.incubator.vector`를 명시해야 한다고 적고, production use 목적이 아니라고 재확인합니다. [Java 27 in IntelliJ IDEA](https://blog.jetbrains.com/idea/2026/09/java-27-in-intellij-idea/)

이걸 팀 전략으로 번역하면 결론이 나옵니다.

- preview/incubator는 “전사 업그레이드”에 포함시키면 안 됩니다.
- 대신 “실험을 하는 팀”이 “실험을 하는 레포/모듈”에서만 다룰 수 있게 만들면, Java 27 자체의 이점(즉시 적용군)을 방해하지 않습니다.

### 실험군의 운영 원칙 3개

1) `--enable-preview`를 빌드/런 모두에서 요구합니다

preview는 컴파일 플래그만 켜고 런타임에서 빼먹는 순간, CI에서는 통과하고 실행에서 터집니다. preview를 쓰는 모듈은 “preview 전용 실행 프로파일”을 강제해야 합니다.

2) preview 타입이 public API 경계를 넘지 못하게 막습니다

preview 기능은 바뀔 수 있고 없어질 수도 있습니다. 따라서 외부로 공개되는 API(다른 모듈이 의존하는 interface, 라이브러리 공개 타입, gRPC/REST 계약 DTO 등)에 preview 타입/패턴이 스며들면 나중에 철수 비용이 폭발합니다.

3) incubator는 classpath가 아니라 module flag로 격리합니다

Vector API는 `--add-modules`가 있어야 동작합니다. 이건 오히려 좋은 격리 수단입니다. 런타임 플래그가 빠진 환경에서는 아예 실행이 안 되기 때문에, “실험 코드가 프로덕션에 우연히 섞여 들어가는 사고”를 줄입니다.

## (3) 보류군: 툴체인/서드파티 호환성은 지금은 ‘선 긋기’가 이득입니다

즉시 적용군과 실험군을 분리해도, 실제 전사 업그레이드에서 가장 자주 발목을 잡는 건 toolchain입니다. Java 27에서는 이게 꽤 명확하게 드러납니다.

### Gradle: ‘빌드 도구 런타임’에서 27이 아직 막힙니다

Gradle 공식 compatibility matrix는 “Gradle을 실행하려면 JVM 17~26이 필요하며, JVM 27 이상은 아직 지원하지 않는다”고 적습니다. [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)

이 한 줄이 의미하는 바는 큽니다.

- 개발자 로컬에서 Gradle daemon을 Java 27로 올리면 깨질 수 있습니다.
- CI에서 Gradle을 Java 27로 실행하려는 시도는 멈춰야 합니다.

즉, 전사 정책으로 “개발 머신도 27로 올리자”는 지금 시점에서는 비용이 큽니다. Java 27을 런타임에 적용하는 건 가능하지만, toolchain 실행 환경은 분리해야 합니다.

### Spring Boot: Java 27은 ‘호환 범위 밖’일 수 있습니다

Spring Boot 문서의 system requirements는 “현재 릴리스가 Java 26까지 호환”이라고 적습니다(최소는 17). [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)

이건 Spring Boot가 Java 27에서 무조건 깨진다는 뜻이 아닙니다. 다만 다음은 사실입니다.

- 프레임워크/서드파티는 “지원한다고 말한 범위” 안에서만 장애 대응이 빨라집니다.
- 지원 범위 밖은 결국 조직이 비용을 지불합니다(원인 분석, 패치 대기, 임시 롤백 등).

그래서 Spring Boot 기반 서비스는 Java 27 런타임을 도입할 때도 더 강한 canary, 더 촘촘한 SLO 모니터링, 더 명확한 롤백 스위치를 붙이는 쪽이 맞습니다.

### IntelliJ IDEA: 개발 도구는 오히려 빨리 따라옵니다

개발자 체감 관점에서 IDE는 빠른 게 이득입니다. JetBrains는 “IntelliJ IDEA가 Java 27을 day one으로 지원”한다고 명시합니다. [Java 27 in IntelliJ IDEA](https://blog.jetbrains.com/idea/2026/09/java-27-in-intellij-idea/)

또한 JetBrains 문서는 “Java 27 표준 언어 기능은 새 기능이 없다”와 “preview는 primitive patterns 5th preview”를 구분해 표시합니다. [Supported Java versions and features](https://www.jetbrains.com/help/idea/supported-java-versions.html)

즉, IDE 업그레이드는 상대적으로 리스크가 적고, 오히려 preview 실험을 할 팀이 있다면 IDE가 발목을 잡지 않게 해줍니다.

## 팀을 어떻게 나눌까: (1) 즉시 적용군, (2) 실험군, (3) 보류군

여기서부터는 “조직도”로 내려갑니다. Java 27 같은 릴리스는 기술 이슈가 아니라 협업 이슈로 실패하는 경우가 많습니다.

### (1) 즉시 적용군: 보안/관측성 + 런타임 디폴트 검증 팀

이 그룹은 보통 다음 팀이 맡는 게 맞습니다.

- 플랫폼/인프라(SRE 포함)
- 보안/컴플라이언스
- 관측성(성능 엔지니어링 포함)

이 팀들의 산출물은 코드가 아니라 **런북과 운영 안전장치**입니다.

- TLS 변화 검증과 롤백 스위치 확립
  - hybrid named group 제어 (`jdk.tls.namedGroups`/`SSLParameters::setNamedGroups`) [Post-Quantum Hybrid Key Exchange for TLS 1.3](https://inside.java/2026/02/17/tls-post-quantum-hybrid-key-exchange/)
  - TLS certificate compression disable 프로퍼티 [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
  - TLS 1.3 key derivation 롤백 프로퍼티 [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)

- JFR redaction 운영 표준화
  - 기본 redaction을 끌지 말고, 커스텀 필터를 추가하는 방향으로 표준을 만듭니다.
  - disabling 옵션은 “장애 대응용 임시 스위치”로만 남깁니다. [JDK 27 Release Notes (Important Changes)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

- HotSpot 디폴트 변경 확인
  - COH는 default, 필요 시 `-XX:-UseCompactObjectHeaders`로 복구 [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
  - GC는 default가 바뀌므로, 기존에 Serial 의존이 있었던 경량 워크로드/사이드카를 집중 점검 [Java 27 in IntelliJ IDEA](https://blog.jetbrains.com/idea/2026/09/java-27-in-intellij-idea/)

이 즉시 적용군은 “전사 업그레이드”를 하지 않습니다. 대신 “런타임 27 canary lane”을 만들고, 여기서 안전장치가 확인된 서비스부터 점진적으로 올립니다.

### (2) 실험군: preview/incubator를 다루는 R&D/핵심 서비스 팀

이 그룹은 다음 성향의 팀이 맡는 게 맞습니다.

- concurrency/latency가 핵심 경쟁력인 팀(Structured Concurrency 관심)
- 라이브러리/플랫폼 개발 팀(PEM encoding, lazy constants 관심)
- 수치 연산/미디어/ML inference 팀(Vector API 관심)

여기서 중요한 건 “프로덕션에 적용하라”가 아니라 “피드백 루프를 돌린다”입니다. JetBrains가 말한 것처럼 preview는 변합니다. [Java 27 in IntelliJ IDEA](https://blog.jetbrains.com/idea/2026/09/java-27-in-intellij-idea/)

실험군의 산출물은 다음이 되어야 합니다.

- preview/incubator로 얻는 실익(코드 단순화, 오류 감소, 성능 향상)이 실제로 있는지
- 철수 비용이 얼마인지
- 다음 릴리스에서 final이 되기 전까지 어떤 운영 안전장치가 필요한지

### (3) 보류군: toolchain/서드파티를 책임지는 빌드 플랫폼 팀

이 그룹이 필요한 이유는 간단합니다.

- Gradle은 JVM 27에서 아직 실행이 지원되지 않습니다. [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- 프레임워크는 “지원 범위”가 존재합니다(예: Spring Boot는 Java 26까지). [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)

따라서 빌드 플랫폼 팀은 다음을 해야 합니다.

- 빌드/테스트 도구 런타임 JDK를 당분간 26 이하로 유지
- 런타임 JDK만 27로 올리는 배포 파이프라인(컨테이너 base image 분리 등) 제공
- 서드파티 agent/bytecode instrumentation(관측성 agent 등)의 27 대응 여부를 별도 트랙에서 검증

이렇게 팀을 나눠야 “런타임 업그레이드의 이득”이 “툴체인 업그레이드의 비용”에 발목 잡히지 않습니다.

## CI 매트릭스 제안: Build JVM과 Runtime JVM을 분리한 2-layer 테스트

아래는 내가 실제로 많이 쓰는 형태를 Java 27에 맞게 변형한 매트릭스입니다.

### Layer A: Build/Unit Test lane (보류군 영역)

- 목적: 개발 생산성 유지, toolchain 리스크 회피
- JVM: 17~26 중 조직 표준(Gradle 지원 범위 안)
- 산출물: 동일 artifact

여기서 중요한 건 “artifact는 동일하게 만들되, 실행은 Layer B에서 한다”입니다.

### Layer B: Runtime smoke lane (즉시 적용군 영역)

- 목적: Java 27의 디폴트 변경이 실제 운영 조건에서 문제 없는지 확인
- JVM: 27
- 테스트: 다음 4가지만 우선 돌립니다.

1) TLS outbound 호출 스모크
   - 프록시/게이트웨이/외부 API를 반드시 하나 이상 포함

2) TLS inbound(mTLS 포함) 스모크
   - 서비스 메시나 LB가 TLS terminate를 하면 그 경로를 포함

3) JFR 레코딩 생성/수집/공유 스모크
   - 레코딩 파일이 생성되고, 민감정보가 포함되지 않는지 확인

4) 메모리/GC 기본 동작 스모크
   - 힙 크기 변화, GC 로그 패턴, p99 latency의 큰 변동 유무

이 lane에서 실패하면 “전사 업그레이드 중단”이 아니라 “해당 서비스는 플래그 롤백 또는 런타임 롤백”으로 처리합니다.

## 런타임 플래그·롤백 플랜: Java 27에서 실제로 쓸 스위치 모음

운영에서 가장 가치 있는 건 ‘완벽한 설정’이 아니라, 장애 순간에 바로 적용할 수 있는 “정해진 조치”입니다.

### TLS 계열

- hybrid named groups를 제한(예: 기존 ECDHE만 사용)하고 싶을 때
  - `-Djdk.tls.namedGroups=...`로 제어하거나, 코드에서 `SSLParameters::setNamedGroups`로 제어 [Post-Quantum Hybrid Key Exchange for TLS 1.3](https://inside.java/2026/02/17/tls-post-quantum-hybrid-key-exchange/)

- TLS certificate compression을 끄고 싶을 때
  - `-Djdk.tls.client.disableExtensions=compress_certificate`
  - `-Djdk.tls.server.disableExtensions=compress_certificate` [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)

- TLS 1.3 shared secret key algorithm 변화로 provider 호환 문제가 의심될 때
  - `-Djdk.tls.t13KeyDerivationAlgorithm=TlsPremasterSecret` [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)

### JFR 계열

- 기본 redaction을 끄고 싶을 때(권장하지 않지만, 비교/디버깅 용도)
  - `-XX:FlightRecorderOptions:redact-key=none,redact-argument=none` [JDK 27 Release Notes (Important Changes)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

- 커스텀 redaction 필터를 추가하고 싶을 때
  - `-XX:FlightRecorderOptions:redact-key=+<filter>`
  - `-XX:FlightRecorderOptions:redact-argument=+<filter>` [JDK 27 Release Notes (Important Changes)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

### 메모리/HotSpot 계열

- Compact Object Headers를 끄고 싶을 때
  - `-XX:-UseCompactObjectHeaders` (향후 제거 예정이라고 릴리스 노트에 명시) [Consolidated JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)

- `UseCompressedClassPointers` 관련 warning 정리
  - Java 27에서 obsolete로 처리되어, 옵션이 있으면 warning이 납니다.
  - 배포 스펙/헬름 차트/런처 스크립트에서 해당 옵션을 제거하는 게 맞습니다. [JDK 27 Release Notes (Important Changes)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

### 진단/운영

- 실행 중 보안 프로퍼티 확인
  - `jcmd <pid> VM.security_properties` [JDK 27 Release Notes (Important Changes)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

## 스모크 테스트 예제: PQC TLS + JFR redaction + 보안 프로퍼티 확인

아래 예제는 장난감 수준의 “Hello World”가 아니라, 업그레이드 런북에서 바로 재사용할 수 있는 형태를 목표로 잡았습니다.

- 로컬에서 TLS 1.3 서버/클라이언트를 띄워서 hybrid named group을 명시적으로 넣고 핸드셰이크를 발생
- JFR 레코딩을 생성하고, secret 문자열이 레코딩 출력에 포함되지 않는지(혹은 옵션으로 포함되게 만들 수 있는지)를 확인
- 프로세스에 붙어서 `VM.security_properties`를 호출

### 1) 준비: JDK 27 설치 확인

```bash
java -version
```

예상 결과(포함되어야 하는 조건)

- 출력에 `"27"` 또는 `27` 버전이 포함됩니다.

### 2) TLS 테스트용 인증서 생성

서버 keystore(PKCS12)와 클라이언트 truststore를 만들고, 로컬에서만 씁니다.

```bash
# server keystore
keytool -genkeypair \
  -alias server \
  -keyalg EC \
  -keystore server.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -dname "CN=localhost"

# export cert
keytool -exportcert \
  -alias server \
  -keystore server.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -rfc \
  -file server.crt

# truststore
keytool -importcert \
  -alias server \
  -file server.crt \
  -keystore trust.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -noprompt
```

예상 결과(포함되어야 하는 조건)

- 현재 디렉터리에 `server.p12`, `trust.p12`, `server.crt`가 생성됩니다.

### 3) Maven 프로젝트 생성

디렉터리 구조

```text
java27-smoke/
  pom.xml
  src/main/java/dev/daewook/Java27Smoke.java
```

`pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>dev.daewook</groupId>
  <artifactId>java27-smoke</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>27</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.15.0</version>
      </plugin>

      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
        <configuration>
          <mainClass>dev.daewook.Java27Smoke</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

- `maven-compiler-plugin` 버전 표기는 Kotlin 문서 예시에 포함된 값을 그대로 썼습니다. [Kotlin Maven configure project](https://kotlinlang.org/docs/maven-configure-project.html)

### 4) 코드: TLS hybrid named groups 지정 + JFR 대상 값 준비

`src/main/java/dev/daewook/Java27Smoke.java`

```java
package dev.daewook;

import javax.net.ssl.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.cert.CertificateException;
import java.time.Duration;

public class Java27Smoke {

    public static void main(String[] args) throws Exception {
        int port = 8443;

        // 1) TLS server in background
        SSLContext serverCtx = buildServerSslContext("server.p12", "changeit".toCharArray());
        Thread serverThread = Thread.ofPlatform().start(() -> runTlsServer(serverCtx, port));

        // give the server a moment
        Thread.sleep(300);

        // 2) TLS client handshake with explicit named groups
        SSLContext clientCtx = buildClientSslContext("trust.p12", "changeit".toCharArray());
        runTlsClient(clientCtx, port);

        // 3) Hold process for jcmd attachment / JFR duration
        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Sleep 10s...");
        Thread.sleep(Duration.ofSeconds(10));

        // stop server thread (best-effort)
        serverThread.interrupt();
    }

    static void runTlsServer(SSLContext ctx, int port) {
        try {
            SSLServerSocketFactory ssf = ctx.getServerSocketFactory();
            try (SSLServerSocket server = (SSLServerSocket) ssf.createServerSocket()) {
                server.setReuseAddress(true);
                server.bind(new InetSocketAddress("127.0.0.1", port));

                SSLParameters p = server.getSSLParameters();
                p.setProtocols(new String[]{"TLSv1.3"});

                // Keep this simple: allow both hybrid and classical groups.
                // The exact hybrid group names are documented in Inside.java.
                // See: params.setNamedGroups(...) snippet.
                p.setNamedGroups(new String[]{
                        "X25519MLKEM768",
                        "x25519",
                        "secp256r1"
                });
                server.setSSLParameters(p);

                try (SSLSocket sock = (SSLSocket) server.accept()) {
                    sock.startHandshake();

                    SSLSession s = sock.getSession();
                    System.out.println("[server] protocol=" + s.getProtocol());
                    System.out.println("[server] cipher=" + s.getCipherSuite());

                    // simple echo
                    BufferedReader br = new BufferedReader(new InputStreamReader(sock.getInputStream(), StandardCharsets.UTF_8));
                    BufferedWriter bw = new BufferedWriter(new OutputStreamWriter(sock.getOutputStream(), StandardCharsets.UTF_8));
                    String line = br.readLine();
                    bw.write("echo:" + line + "\n");
                    bw.flush();
                }
            }
        } catch (Exception e) {
            System.err.println("[server] error: " + e);
        }
    }

    static void runTlsClient(SSLContext ctx, int port) throws IOException {
        SSLSocketFactory sf = ctx.getSocketFactory();
        try (SSLSocket sock = (SSLSocket) sf.createSocket("127.0.0.1", port)) {
            SSLParameters p = sock.getSSLParameters();
            p.setProtocols(new String[]{"TLSv1.3"});

            // Hybrid + classical; code style matches Inside.java guidance.
            // https://inside.java/2026/02/17/tls-post-quantum-hybrid-key-exchange/
            p.setNamedGroups(new String[]{
                    "X25519MLKEM768",
                    "x25519",
                    "secp256r1"
            });
            sock.setSSLParameters(p);

            sock.startHandshake();
            SSLSession s = sock.getSession();
            System.out.println("[client] protocol=" + s.getProtocol());
            System.out.println("[client] cipher=" + s.getCipherSuite());

            BufferedWriter bw = new BufferedWriter(new OutputStreamWriter(sock.getOutputStream(), StandardCharsets.UTF_8));
            BufferedReader br = new BufferedReader(new InputStreamReader(sock.getInputStream(), StandardCharsets.UTF_8));
            bw.write("hello\n");
            bw.flush();
            System.out.println("[client] got=" + br.readLine());
        }
    }

    static SSLContext buildServerSslContext(String keystorePath, char[] pass)
            throws KeyStoreException, IOException, NoSuchAlgorithmException, CertificateException,
            UnrecoverableKeyException, KeyManagementException {

        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream is = new FileInputStream(keystorePath)) {
            ks.load(is, pass);
        }

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(ks, pass);

        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(kmf.getKeyManagers(), null, new SecureRandom());
        return ctx;
    }

    static SSLContext buildClientSslContext(String truststorePath, char[] pass)
            throws KeyStoreException, IOException, NoSuchAlgorithmException, CertificateException,
            KeyManagementException {

        KeyStore ts = KeyStore.getInstance("PKCS12");
        try (InputStream is = new FileInputStream(truststorePath)) {
            ts.load(is, pass);
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(ts);

        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(null, tmf.getTrustManagers(), new SecureRandom());
        return ctx;
    }
}
```

- hybrid group 이름과 `SSLParameters::setNamedGroups` 방식은 Inside.java 문서에 근거합니다. [Post-Quantum Hybrid Key Exchange for TLS 1.3](https://inside.java/2026/02/17/tls-post-quantum-hybrid-key-exchange/)

### 5) 실행: TLS 핸드셰이크에서 hybrid 그룹이 등장하는지 확인

TLS 쪽은 세션 API에서 “어떤 named group이 최종 선택됐는지”를 바로 뽑기 애매한 경우가 많아서, 운영 검증에서는 디버그 로그를 함께 봅니다.

```bash
mvn -q -DskipTests exec:java \
  -Dexec.args="" \
  -Djavax.net.debug=ssl:handshake
```

예상 결과(포함되어야 하는 조건)

- 표준 출력에 `[client] protocol=TLSv1.3`과 같은 라인이 찍힙니다.
- 표준 에러(디버그 로그)에서 `X25519MLKEM768` 같은 문자열이 나타나는지 확인합니다.

문자열 확인용으로는 이런 형태가 실전에서 더 안전합니다.

```bash
mvn -q -DskipTests exec:java -Djavax.net.debug=ssl:handshake 2>&1 | grep -E "X25519MLKEM768|MLKEM"
```

- grep 결과가 비어 있으면(0줄) “로컬 핸드셰이크에서 hybrid가 전혀 협상 후보로 올라오지 않았다”는 뜻이라서, 운영 환경에서는 더 보수적으로 봐야 합니다.

### 6) 실행: JFR redaction이 ‘secret 문자열을 남기지 않는지’ 확인

JFR은 값이 “어떤 문자열로 redaction되었는지”보다, 더 실전적인 검증 기준이 있습니다.

- 레코딩/수집/공유 파이프라인 어디에도 secret 원문이 남지 않는다.

Important Changes 릴리스 노트는 Java 27부터 기본 redaction이 켜진다고 적고, 끄는 방법도 제공합니다. [JDK 27 Release Notes (Important Changes)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

다음은 “secret이 레코딩에 남지 않는지”만 확인하는 스모크입니다.

```bash
export API_TOKEN=supersecret

# 10초는 위 프로그램이 sleep하는 시간과 맞춥니다.
java \
  -Dapp.password=supersecret \
  -XX:StartFlightRecording=filename=java27-smoke.jfr,duration=10s \
  -cp target/classes dev.daewook.Java27Smoke

# secret 원문이 남았는지 검색 (남으면 실패)
jfr print java27-smoke.jfr | grep supersecret && echo "LEAK" || echo "OK"
```

예상 결과(포함되어야 하는 조건)

- 마지막 줄이 `OK`로 끝나야 합니다.

만약 비교 목적으로 redaction을 끄고 싶으면(운영에서는 권장하지 않지만, 테스트에서는 유용합니다) 릴리스 노트에 나온 옵션을 그대로 씁니다.

```bash
export API_TOKEN=supersecret

java \
  -Dapp.password=supersecret \
  -XX:FlightRecorderOptions:redact-key=none,redact-argument=none \
  -XX:StartFlightRecording=filename=java27-smoke-noredact.jfr,duration=10s \
  -cp target/classes dev.daewook.Java27Smoke

jfr print java27-smoke-noredact.jfr | grep supersecret && echo "RECORDED" || echo "NOT_FOUND"
```

- 이 비교 테스트가 의미 있는 이유는, “우리 조직의 JFR 수집 경로가 민감정보를 담고 있었는지”를 역으로 보여주기 때문입니다.

### 7) 실행: `jcmd VM.security_properties`로 런타임 보안 프로퍼티 확인

Important Changes 릴리스 노트는 `VM.security_properties` 추가를 설명합니다. [JDK 27 Release Notes (Important Changes)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

실행 방법은 단순합니다.

1) 프로그램을 백그라운드로 실행
2) PID를 받아서 `jcmd` 호출

```bash
java -cp target/classes dev.daewook.Java27Smoke &
PID=$!

jcmd $PID VM.security_properties | head -n 30

kill $PID
```

예상 결과(포함되어야 하는 조건)

- 출력에 `jdk.`로 시작하는 보안 관련 프로퍼티 라인이 다수 포함됩니다.

이 커맨드가 런북에 들어가면 “보안 설정이 먹었냐”류의 장애 대응이 체계화됩니다.

## 정리: Java 27은 ‘팀별로 다른 속도’가 정답인 릴리스입니다

Java 27은 프리뷰가 많아서 미루고 싶은 마음이 들지만, 실제 운영 리스크/이점은 프리뷰가 아니라 보안·관측성·런타임 디폴트에 있습니다. JEP 527(PQC hybrid TLS)과 JEP 536(JFR in-process redaction)은 업그레이드만으로 기본 동작이 바뀌고, 그 변화는 보안/운영 프로세스를 직접 건드립니다. [Oracle 보도자료](https://www.oracle.com/news/announcement/oracle-releases-java-27-and-strengthens-post-quantum-cryptography-support-2026-09-15/) / [The Arrival of Java 27](https://blogs.oracle.com/java/the-arrival-of-java-27)

반면 preview/incubator는 조직의 핵심 팀이 실험군으로 가져가되, 전사 공통 기반에는 섞지 않는 편이 비용이 낮습니다. 그리고 toolchain(특히 Gradle 실행 JVM)처럼 지금 당장 막혀 있는 구간은 보류군으로 선을 긋는 게 오히려 전체 업그레이드 속도를 올립니다. [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)

즉시 적용군/실험군/보류군으로 분리하고, CI 매트릭스와 롤백 스위치를 런북에 고정해두면 Java 27은 “올릴지 말지”가 아니라 “어디까지 올릴지”의 문제로 바뀝니다.

## 참고 자료

- [Oracle 보도자료: Java 27 GA 및 PQC 강화 발표](https://www.oracle.com/news/announcement/oracle-releases-java-27-and-strengthens-post-quantum-cryptography-support-2026-09-15/)
- [Oracle 기술 블로그: The Arrival of Java 27](https://blogs.oracle.com/java/the-arrival-of-java-27)
- [Oracle JDK 27 Important Changes 릴리스 노트](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Oracle JDK 27 통합 릴리스 노트](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
- [Inside.java: Post-Quantum Hybrid Key Exchange for TLS 1.3](https://inside.java/2026/02/17/tls-post-quantum-hybrid-key-exchange/)
- [Inside.java: JDK 27 Runtime Updates Release Notes](https://inside.java/2026/09/12/jdk-27-runtime-updates/)
- [JetBrains: Java 27 in IntelliJ IDEA](https://blog.jetbrains.com/idea/2026/09/java-27-in-intellij-idea/)
- [JetBrains 문서: Supported Java versions and features](https://www.jetbrains.com/help/idea/supported-java-versions.html)
- [Gradle 문서: Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Spring Boot 문서: System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Sean Mullan: JDK 27 Security Enhancements](https://seanjmullan.org/blog/2026/09/15/jdk27)
- [기존 글: OppZGC: 유휴 코어를 쓰는 ZGC 스케줄링의 실전성](https://daewooki.github.io/posts/opportunistic-zgc-idle-core-scheduling/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
