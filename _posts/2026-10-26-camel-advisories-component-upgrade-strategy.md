---
title: "Apache Camel 보안 권고 38건 한 번에 소화하기: 컴포넌트별 영향도 기반 전략"
description: "Camel 보안 권고가 한꺼번에 쏟아질 때, 서비스별 사용 컴포넌트를 먼저 확정하고 설정 안전화와 LTS/신규 라인 업그레이드를 분리해 의사결정을 만든다."
date: 2026-10-26 09:53:29 +0900
categories: ["Backend", "Apache Camel"]
tags: ["apache-camel", "security-advisory", "cve-triage", "dependency-inventory", "upgrade-strategy", "lts"]
render_with_liquid: false
---

## 38건 ‘일괄 공지’의 핵심은 Camel이 아니라 컴포넌트입니다

Apache Camel PMC는 2026-10-15에 38개 security advisory를 공개했고, 다음날(2026-10-16) 이를 한 번에 묶어 공지했습니다. 고정 버전은 4.18.5(4.18.x LTS), 4.22.1(4.22.x LTS), 4.23.0이며, 13건이 HIGH, 25건이 MEDIUM으로 분류되어 있습니다. 또한 4.14.x LTS는 4.14.9 이후 EOL이라 이번 수정의 대부분(공지 기준 35/38)에 포함되어도 더 이상 패치가 내려오지 않는다고 못 박았습니다.[^1]

이 유형의 사건에서 조직이 흔히 하는 실수는 “Camel을 올리자/말자”로 바로 점프하는 것입니다. Camel은 프레임워크이지만 운영에서 부딪히는 취약점의 현실은 **컴포넌트별로 터지고**, 서비스는 그 컴포넌트의 일부만 쓰며, 취약점의 전제조건도 제각각입니다.

예를 들어 이번 묶음만 봐도 성격이 완전히 다릅니다.

- HTTP producer 계열에서 `CamelHttpUri`/`CamelRestHttpUri` override header에 대해 property placeholder를 풀어버리던 문제(CVE-2026-78164)는 “헤더/플레이스홀더/secret function/registry bean method”가 얽힌 설정 실행 문제입니다.[^2]
- `camel-spring-redis` 기본 serializer가 Redis payload를 `ObjectInputFilter` 없이 Java deserialization 하던 문제(CVE-2026-78165)는 “메시지 도착 직후, 라우트 로직 이전”에 sink가 열려 있던 케이스입니다.[^3]
- `camel-ftp`, `camel-mina-sftp`, `camel-smb`, `camel-azure-files`의 path traversal(CVE-2026-79983~79986)은 “remote directory listing을 신뢰하면 안 된다”는 파일/스토리지 계열 취약점입니다.[^4]
- `camel-oauth`의 fail-open 인증 우회(CVE-2026-80312)나 `camel-netty-http` security constraint bypass(CVE-2026-80343)는 경계(consumer 앞단) 설계가 그대로 드러납니다.[^5]

같은 “Camel 보안 이슈”로 묶였지만, 서비스에 미치는 영향도, 긴급도, 테스트 범위, 즉시 가능한 차단책이 다릅니다. 그래서 우선순위를 정하려면 CVE를 서비스에 투영하는 ‘인벤토리 → 노출 경로 → 업그레이드/차단’ 파이프라인이 필요합니다.

## ‘서비스별 컴포넌트 인벤토리’를 먼저 확정해야 하는 이유

Camel의 보안 공지는 컴포넌트 단위로 나옵니다. 예를 들어 공지 표에서 CVE-2026-78164는 `camel-http`, `camel-netty-http`, `camel-undertow`, `camel-vertx-http`에 걸려 있습니다.[^1]

이때 “우리 서비스는 Camel 쓰니까 영향 있음”이 아니라 다음을 분리해야 합니다.

1. **빌드 타임 포함 여부**: 실제로 `camel-netty-http` 같은 artifact가 classpath에 있나?
2. **라우트에서 사용 여부**: artifact가 있어도 해당 엔드포인트를 안 쓰면 노출면이 줄어든다.
3. **신뢰 경계(Trust boundary)**: 라우트로 들어오는 메시지가 외부/내부/파트너/멀티테넌트인지.
4. **취약점 전제조건 충족 여부**: 예를 들어 CVE-2026-83531은 `dynamic-router-control:`로 메시지가 들어갈 수 있어야 의미가 있습니다.[^6]

Camel이 자체적으로 “보안 모델/보고 범위/신뢰 경계”를 문서화한 것도 같은 맥락입니다. 무엇이 프레임워크 취약점이고 무엇이 운영자/라우트 작성자 책임인지 분리해 triage에 쓰라는 의도입니다.[^7]

조직 관점에서 내가 제일 먼저 고정하는 산출물은 아래 2개입니다.

- 서비스별 Camel 컴포넌트 인벤토리(artifact 기준, endpoint scheme 기준)
- CVE별 “노출 경로 타입” 라벨링(placeholder, header, deserialize, path, authz/authn, management/control message 등)

이 두 개가 있어야 “업그레이드가 곧 정답”이 아니라 “업그레이드 전 즉시 차단”과 “업그레이드 후 회귀 테스트”를 같이 설계할 수 있습니다.

## 인벤토리 만들기 1: 의존성에서 Camel 컴포넌트 추출하기(Maven 기준)

운영에서 가장 싸고 빠른 인벤토리는 빌드 산출물에서 나옵니다. Camel 컴포넌트는 보통 `org.apache.camel:camel-xxx` 혹은 Spring Boot를 쓰면 `org.apache.camel.springboot:camel-xxx-starter` 형태로 들어옵니다.

### 1) Maven dependency:list로 Camel artifact만 뽑기

아래 커맨드는 “런타임 스코프 기준으로, groupId가 org.apache.camel/org.apache.camel.springboot 인 것만” 파일로 뽑습니다.

```bash
# 서비스 리포지토리 루트에서
mvn -q \
  -DincludeScope=runtime \
  -DincludeGroupIds=org.apache.camel,org.apache.camel.springboot \
  dependency:list \
  -DoutputFile=target/camel-deps.txt

sed -n '1,120p' target/camel-deps.txt
```

이 파일은 포맷이 단순해서 스크립트로 파싱하기 좋습니다.

### 2) 파싱 스크립트: camel component set 만들기

아래는 `camel-deps.txt`에서 Camel 컴포넌트 후보를 정규화해 `components.json`으로 저장하는 예시입니다. (starter면 `-starter`를 떼고, `camel-core` 같은 코어 모듈은 별도 처리)

```python
# tools/camel_inventory_from_maven.py
import json
import re
import sys
from pathlib import Path

COMP_RE = re.compile(r"\borg\.apache\.camel(\.springboot)?:camel-([a-z0-9-]+)(-starter)?:")

CORE_LIKE = {
    "core",
    "base",
    "api",
    "main",
    "management",
    "util",
    "support",
    "dsl-modeline",
    "dsl-support",
    "core-languages",
}

inp = Path(sys.argv[1])
components = set()
core_modules = set()

for line in inp.read_text(encoding="utf-8", errors="ignore").splitlines():
    m = COMP_RE.search(line)
    if not m:
        continue
    name = m.group(2)
    # camel-ftp -> ftp, camel-netty-http -> netty-http
    if name in CORE_LIKE:
        core_modules.add(name)
    else:
        components.add(name)

out = {
    "components": sorted(components),
    "core_modules": sorted(core_modules),
}
print(json.dumps(out, indent=2, ensure_ascii=False))
```

실행:

```bash
python3 tools/camel_inventory_from_maven.py target/camel-deps.txt > target/camel-components.json
cat target/camel-components.json
```

여기서 주의할 점이 있습니다.

- Spring Boot starter는 transitive dependency로 실제 `camel-xxx`를 당겨옵니다. “starter만 있다/없다”보다 “실제 컴포넌트 모듈이 무엇이냐”를 봐야 합니다.
- BOM(`camel-bom`, `camel-spring-boot-bom`)로 버전을 고정하면 artifact 목록은 명확해지지만, 모듈이 많아져도 취약점 노출이 늘어난다고 단정하면 안 됩니다. 노출은 ‘사용/경계’가 좌우합니다.

## 인벤토리 만들기 2: 라우트 정의에서 endpoint scheme를 추출하기

의존성 인벤토리는 “포함된 칼”을 세는 것이고, 라우트 인벤토리는 “실제로 휘두르는 칼”을 세는 것입니다.

Camel은 URI scheme가 곧 컴포넌트인 경우가 많습니다.

- `ftp://...` → `camel-ftp`
- `smb://...` → `camel-smb`
- `spring-redis://...` → `camel-spring-redis`
- `netty-http:http://...` → `camel-netty-http`

라우트가 Java DSL, XML DSL, YAML DSL로 섞여 있으면 정적 분석이 완벽하지는 않습니다. 그래도 “업그레이드 우선순위 산정” 용도로는 충분히 쓸 만합니다.

### 1) ripgrep으로 scheme 후보 모으기

```bash
rg -n --hidden --no-ignore-vcs \
  -g'!**/target/**' \
  -g'!**/build/**' \
  -e '"[a-z][a-z0-9+.-]*:' \
  -e "'[a-z][a-z0-9+.-]*:" \
  -e 'uri:\s*"[a-z][a-z0-9+.-]*:' \
  -e 'to:\s*"[a-z][a-z0-9+.-]*:' \
  . > target/camel-uri-hits.txt

head -n 50 target/camel-uri-hits.txt
```

이 결과에서 `direct:`, `log:`, `timer:` 같은 내부용 scheme는 제외하고, `ftp`, `netty-http`, `undertow`, `vertx-http`, `spring-redis`, `hazelcast` 같은 외부 I/O 혹은 보안 경계 컴포넌트만 우선 태깅합니다.

### 2) 왜 정적 분석이 불완전한가

- `toD()`/`enrich()`/`recipientList()` 같은 dynamic endpoint는 런타임에 URI가 조합됩니다.
- `CamelHttpUri`처럼 헤더로 URI override가 가능한 컴포넌트는 라우트 코드만 봐서는 실제 outbound target을 확정할 수 없습니다. CVE-2026-78164가 바로 이 경로를 악용합니다.[^2]

그래도 “무슨 컴포넌트가 서비스에 들어있고, 대충 어느 지점에서 쓰이는지”를 확보하면 CVE 묶음 triage가 훨씬 싸집니다.

## advisory 데이터셋 만들기: 공지 표를 그대로 ‘머신이 읽게’ 바꾸기

Camel 쪽 공지에는 38건의 CVE/컴포넌트/Severity/요약이 표로 정리돼 있습니다.[^1]

조직 내부에서 실제로 필요한 것은 다음 형태입니다.

- `CVE-XXXX-YYYYY` → 영향 컴포넌트 리스트
- Severity(HIGH/MEDIUM)
- 전제조건(가능하면)
- 조치(업그레이드/설정 변경/차단)

### 1) 공지 페이지에서 표를 추출하는 스크립트

```python
# tools/fetch_camel_38_advisories.py
import json
import re

import requests
from bs4 import BeautifulSoup

URL = "https://camel.apache.org/blog/2026/10/camel-security-advisories-4.23.0/"

def split_components(text: str):
    # 예: "camel-http, camel-netty-http, camel-undertow, camel-vertx-http"
    parts = [p.strip() for p in text.split(",")]
    # camel- 접두 제거 없이 유지 (Camel 측 표와 맞추기)
    return [p for p in parts if p]

resp = requests.get(URL, timeout=30)
resp.raise_for_status()

soup = BeautifulSoup(resp.text, "lxml")

# 본문 첫 번째 표가 advisory 표인 형태(페이지가 변하면 selector 조정 필요)
table = soup.find("table")
if table is None:
    raise SystemExit("advisory table not found")

rows = []
for tr in table.find_all("tr"):
    tds = tr.find_all(["td", "th"])
    if len(tds) != 4:
        continue

    cve = tds[0].get_text(strip=True)
    if not re.match(r"CVE-\d{4}-\d+", cve):
        continue

    component = tds[1].get_text(" ", strip=True)
    severity = tds[2].get_text(strip=True)
    desc = tds[3].get_text(" ", strip=True)

    rows.append({
        "cve": cve,
        "components": split_components(component),
        "severity": severity,
        "summary": desc,
        "source": URL,
    })

print(json.dumps({"advisories": rows}, indent=2, ensure_ascii=False))
```

실행:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests beautifulsoup4 lxml

python tools/fetch_camel_38_advisories.py > target/camel-38.json
jq '.advisories[0:5]' target/camel-38.json
```

조직에서는 이 JSON을 기반으로 “서비스 인벤토리와 join”하는 단계를 붙이면 됩니다.

### 2) 서비스 컴포넌트와 CVE를 join해서 ‘영향도 리스트’ 만들기

- 서비스에서 나온 컴포넌트 목록: `ftp`, `spring-redis`, `netty-http` 같은 형태
- advisory에서 나온 컴포넌트: `camel-ftp`, `camel-spring-redis`, `camel-netty-http`

이 둘을 join할 때는 prefix만 맞추면 됩니다.

- 서비스 컴포넌트 `ftp` ↔ advisory 컴포넌트 `camel-ftp`

여기서부터는 조직 상황에 맞게 점수화를 합니다.

- Severity(HIGH=3, MEDIUM=2)
- 외부 입력 경계면(인터넷=3, 파트너=2, 내부=1)
- 전제조건 난이도(무인증 reachable=3, 인증 필요=2, 내부-only=1)
- 데이터/권한 영향(RCE=3, auth bypass=3, SSRF/secret leak=2, path traversal=2…)

이 점수표는 정답이 아니라 “테스트/업그레이드 순서를 합의하는 언어”입니다.

## 노출 경로 타입별로 설정 안전화를 분리하는 방식

Camel의 security advisory 묶음을 읽으면, 꽤 많은 케이스가 “취약점이 발생한 코드의 성격이 반복된다”는 느낌이 있습니다.

- control header / internal header가 외부 입력과 섞이는 문제
- property placeholder가 message content에 적용되는 문제
- default serializer/deserializer가 안전장치 없이 열려 있는 문제
- path/redirect/case normalization 불일치 문제

이런 유형은 “특정 CVE만 막자”보다 “경계에서 공통으로 안전화하자”가 비용 대비 효과가 좋습니다.

아래는 이번 38건 중 대표적인 것들을 중심으로, 내가 실제 운영에서 잡는 공통 안전화 레이어입니다.

### HTTP producer override header + placeholder: CVE-2026-78164

CVE-2026-78164의 설명은 꽤 직설적입니다.

- HTTP producer 계열은 inbound message가 `CamelHttpUri`, `CamelRestHttpUri` 헤더로 endpoint URI를 override할 수 있습니다.
- 그런데 이 헤더 값을 `CamelContext.resolvePropertyPlaceholders()`에 태워버렸고,
- placeholder resolution은 단순 치환이 아니라 env var, system property, classpath의 `PropertiesFunction`(AWS/Azure/GCP/Vault/Kubernetes secret function 포함), 심지어 registry bean의 no-arg method 호출까지 닿습니다.
- 즉, message content가 “설정/secret 평가 컨텍스트”로 승격되는 형태였습니다.[^2]

여기서 중요한 포인트는 두 가지입니다.

1) 라우트 작성자가 opt-in 하지 않아도 노출됩니다. 정적인 `.to("http://backend/api")`만 있어도, 앞단 어딘가에서 해당 헤더에 영향을 줄 수 있으면 게임이 시작됩니다.[^2]

2) `bridgeEndpoint=true` 같은 익숙한 설정이 “경계를 닫는다”로 직관적으로 읽히지만, 실제로는 그렇지 않았습니다. advisory는 `bridgeEndpoint`가 URL 생성 경로 일부만 막고, method/query 처리 경로는 막지 못했다고 설명합니다.[^2]

#### 즉시 차단(업그레이드 전): 신뢰 경계에서 헤더 제거

업그레이드를 당장 못 하는 경우 advisory가 제시하는 현실적인 방법은 “producer로 보내기 전에 헤더를 제거”하는 것입니다.[^2]

Camel Route 레벨에서 내가 주로 쓰는 패턴은 다음입니다.

```java
// Java DSL 예시: HTTP producer로 보내기 전에 override 헤더를 무조건 제거
from("platform-http:/api/proxy")
  // inbound가 인터넷이라면 여기부터가 trust boundary
  .removeHeader("CamelHttpUri")
  .removeHeader("CamelRestHttpUri")
  .to("netty-http:http://internal-backend/service")
  .to("log:proxy?level=INFO");
```

이건 “해당 라우트만” 보호합니다. 서비스가 크면 매번 넣기 싫어집니다.

그래서 실제 운영에서는 아래 둘 중 하나로 정리합니다.

- (권장) **경계 라우트 앞단**에서 전역적으로 `Camel*Uri`류 헤더를 제거하는 Processor를 만들어서 공통으로 붙인다.
- 서비스별로 인터넷 facing consumer(`platform-http`, `servlet`, `netty-http` consumer 등) 라우트에 “경계 템플릿”을 적용한다.

어느 쪽이든 “Camel 내부 control header는 외부 입력에 섞이면 안 된다”를 코드 레벨 규칙으로 만드는 게 목적입니다.

#### 업그레이드 후 변화: per-message placeholder resolution 제거

4.23 업그레이드 가이드에도 동일 변경이 명시돼 있습니다. HTTP producer는 더 이상 message-supplied override header에서 `{{...}}` placeholder를 풀지 않고, 라우트에 적힌 endpoint URI의 placeholder만 기존처럼 해석합니다.[^8]

이 변화는 보안상 이득이 크지만, 일부 레거시 라우트가 “헤더에 placeholder를 넣어 동적 확장”을 했을 수 있습니다. 그런 라우트는 업그레이드 직후에 “기능이 바뀐 것처럼” 보일 가능성이 높고, 테스트 포인트가 됩니다.

### Redis deserialization: CVE-2026-78165

CVE-2026-78165는 “default가 unsafe였다”는 케이스입니다.

- `camel-spring-redis`는 serializer 옵션이 없으면 `JdkSerializationRedisSerializer`를 기본으로 만들었고
- 이 serializer가 `ObjectInputFilter` 없이 deserialize 했으며
- 특히 consumer는 subscribed channel에 publish된 메시지를 **Exchange 생성 이전**에 deserialize 했기 때문에, 라우트에서 검증할 기회가 없었다고 설명합니다.[^3]

#### 즉시 차단(업그레이드 전): serializer를 Java serialization이 아닌 것으로 고정

advisory는 업그레이드가 최선이지만, 당장 못 하면 두 가지를 제시합니다.

- JVM-wide `-Djdk.serialFilter=...` 설정(해당 경로가 `ObjectInputStream`을 타기 때문에 적용됨)
- endpoint 옵션 `serializer`를 Java serialization이 아닌 serializer로 지정[^3]

운영에서는 두 번째가 더 선명합니다. Redis pub/sub payload를 굳이 Java serialization으로 주고받을 이유가 거의 없습니다.

업그레이드 전/후를 가리지 않고 내가 선호하는 형태는 “String/JSON/bytes로 고정”입니다.

예시(개념을 보여주는 수준이 아니라, 실제로 돌아가는 구성으로 잡는 형태):

```java
// Spring Boot에서 RedisSerializer 빈을 등록하고
@Bean
public org.springframework.data.redis.serializer.RedisSerializer<String> safeStringSerializer() {
    return new org.springframework.data.redis.serializer.StringRedisSerializer();
}

// Camel URI에서 serializer 옵션으로 지정
from("spring-redis://redis.internal:6379"
    + "?command=SUBSCRIBE"
    + "&channels=events"
    + "&serializer=#safeStringSerializer")
  .process(e -> {
      // 이 시점에는 body가 String으로 들어온다
      String payload = e.getMessage().getBody(String.class);
      // JSON이면 여기서 Jackson으로 파싱
  })
  .to("direct:handleEvent");
```

이 방식은 “취약점 회피”뿐 아니라 운영 사고를 줄입니다.

- Java serialization payload는 언어/버전 결합도가 너무 높습니다.
- Redis는 멀티 프로듀서/멀티 컨슈머 구조가 흔하고, 채널 publish 권한이 넓게 열리는 순간이 자주 생깁니다.

#### 업그레이드 후 변화: default serializer가 deserialization filter를 적용

4.23 업그레이드 가이드는 `camel-spring-redis` 기본 serializer가 JEP-290 기반 `ObjectInputFilter`를 적용하고, `deserializationFilter` 옵션으로 allow-list를 확장할 수 있다고 명시합니다. 또한 serializer를 커스텀으로 바꾸면 Camel이 읽는 과정을 제어하지 못하니 필터가 우회된다고도 적혀 있습니다.[^8]

여기서 운영 판단이 갈립니다.

- Redis payload가 애초에 Java serialization이면, 업그레이드 후 필터로 인해 “기존에 통과하던 타입이 막혀” 장애가 날 수 있습니다.
- 반대로 payload를 String/JSON로 바꾸면 필터 이슈 자체가 사라지고, 장기적으로 더 건강합니다.

내 경우는 “취약점 대응”을 계기로 payload 타입을 바꾸는 쪽을 택하는 편입니다. 업그레이드로 얻는 안전장치가 ‘추가’라면, 운영 설계 자체는 더 단순해지게 만드는 게 맞습니다.

### Hazelcast deserialization: CVE-2026-78162

CVE-2026-78162는 “이전 CVE의 incomplete fix” 성격이고, `camel-hazelcast`가 자체 생성하는 인스턴스의 특정 구성 경로에서 JavaSerializationFilterConfig가 적용되지 않아 RCE sink가 남았다는 내용입니다. Hazelcast 자체도 default로 auth/TLS가 꺼져 있다는 설명이 붙어 있습니다.[^9]

#### 즉시 차단(업그레이드 전): HazelcastInstance/Config를 명시적으로 주입

advisory의 미티게이션은 꽤 실용적입니다.

- Camel이 “자체 생성하는” 경로가 문제이므로, 사용자가 **명시적 Hazelcast config/instance를 주면 Camel은 덮어쓰지 않는다**
- 대안으로 JVM-wide `-Djdk.serialFilter=...`를 줄 수 있다[^9]

운영에서 내가 잡는 기본은 다음입니다.

- Hazelcast를 외부 클러스터로 쓸 거면 auth/TLS를 먼저 잡고,
- Camel 쪽에서는 “자동 생성”을 최대한 피한다.

### remote file consumer path traversal: CVE-2026-79983~79986

`camel-ftp` advisory(CVE-2026-79983)는 설명이 매우 구체적입니다.

- remote-file consumer가 directory listing의 “파일명”을 신뢰하고 경로를 이어붙였고
- lexical normalization/containment check가 없어서
- listing entry에 traversal segment가 섞이면 poll 디렉터리 밖으로 탈출한 remote path로 retrieve/delete/rename을 수행할 수 있었다
- FTP control channel은 무결성 보호가 없어서, on-path 공격자가 LIST 응답을 변조할 수 있다고도 명시합니다.[^4]

`camel-smb`, `camel-azure-files`도 기본 구조는 동일하며, 결국 “listing name은 라우트가 제어하는 데이터가 아니다”가 핵심입니다.[^10]

이 부류는 설정만으로 완벽히 막기 어렵습니다. listing 자체가 공격 데이터가 될 수 있고, Camel이 그 값을 operand로 삼아 서버 측 파일 연산을 해버리기 때문입니다.

그래서 운영 triage에서는 아래처럼 단순화합니다.

- `ftp/sftp/smb/azure-files` consumer를 쓰는 서비스는 “가급적 최우선 업그레이드”로 올린다.
- 업그레이드 전까지는 
  - remote 서버 신뢰도를 재점검하고(멀티테넌트/파트너 제공/네트워크 경유)
  - 가능하면 “읽기 전용 계정 + 최소 권한 디렉터리”로 격리하고
  - `delete=true`, `move=` 같은 파괴적 옵션을 꺼서 피해 반경을 줄인다.

이건 기술적으로는 소극적이지만, 실제 운영에서는 업그레이드가 늦어질 때 피해 반경을 줄이는 데 의미가 있습니다.

### OAuth fail-open / netty-http constraint bypass: CVE-2026-80312, CVE-2026-80343

두 CVE는 종류가 다르지만 운영 대응 방식은 닮았습니다.

- `camel-oauth`는 인증 실패 시 exchange를 멈추지 않고 라우트에 제어권을 돌려줘서 보호 구간이 실행되는 fail-open이었다고 설명합니다. 업그레이드 전에는 OAuth processor 뒤에 명시적 authorization check를 넣고 실패 시 라우트를 멈추라고 안내합니다.[^5]
- `camel-netty-http`는 dispatch는 case-insensitive로 가는데 constraint match는 case-sensitive로 가서, path segment의 case를 바꾸면 constraint가 빠지고 라우트가 도달했다고 설명합니다. 업그레이드 전 workaround로는 “Camel consumer 앞단(리버스 프록시 등)에서 path normalization 후 authorization”을 둡니다.[^11]

이 둘은 “Camel이 뭔가 잘못했네”로 끝나지 않습니다. 보안 경계를 어디에 두는지에 따라 피해가 달라집니다.

- Camel 자체의 인증/인가 컴포넌트를 신뢰하는 아키텍처면 Camel의 fail-open이 곧 서비스 전체 fail-open이 됩니다.
- 프록시 레이어(Envoy/nginx/ALB/API Gateway)에서 이미 authz/authn을 끝내고 Camel은 내부용이면, Camel 쪽 버그의 직접 영향은 줄어듭니다.

그래서 나는 이번 유형의 CVE를 “패치 이벤트”로만 보지 않고, 아키텍처 원칙을 다시 확인하는 계기로 씁니다. 예전에 [Apache httpd 2.4.69: HTTP/2 패치가 프록시 체인에 미치는 영향](https://daewooki.github.io/posts/apache-httpd-2469-proxy-chain-security/)을 정리할 때도 같은 결론으로 갔습니다. 프록시 체인이 복잡해질수록, 경계의 책임을 명확히 하고 normalization을 한 지점에서 끝내야 합니다.

### dynamic-router-control predicate code execution: CVE-2026-83531

CVE-2026-83531은 전제조건이 비교적 명확합니다.

- `dynamic-router-control:` 엔드포인트로 들어가는 control message가 predicate expression과 expression language를 같이 들고 오고
- Camel이 allow-list/opt-in 없이 그 language를 resolve해 predicate를 컴파일해 등록했기 때문에
- 외부 transport에서 control endpoint로 메시지가 흘러들 수 있으면 프로세스 내 code execution으로 이어질 수 있다는 내용입니다.[^6]

이 CVE는 “우리 서비스는 dynamic-router 안 쓰는데?”로 끝나는 게 아니라, 라우트가 커지면서 다음 패턴이 나오기 쉬운지 점검하게 만듭니다.

- 내부/외부 이벤트 버스에서 control message를 받아 dynamic subscription을 제어
- 멀티테넌트 환경에서 특정 테넌트가 구독 규칙을 업데이트

업그레이드 후에는 message에서 predicate/language를 받는 동작이 기본으로 거부되고, `allowPredicateFromMessage` 옵션을 켰을 때만 허용된다고 advisory에 적혀 있습니다. 즉, “기능을 계속 쓰려면 명시적으로 위험을 승인”하게 바뀝니다.[^6]

업그레이드 전에는 더 단순합니다.

- untrusted/shared transport에서 `dynamic-router-control:`로 메시지를 포워딩하지 않는다.
- 어쩔 수 없다면, 해당 라우트에서 predicate/language 관련 헤더/필드를 제거하고, 구독 규칙은 라우트가 정한 고정값으로만 세팅한다.[^6]

## LTS 라인 유지(4.18.x/4.22.x) vs 4.23.0 이동: 의사결정을 만드는 기준

Camel 공지는 업그레이드 표를 아주 명확하게 줍니다.

- 4.22.x(LTS) → 4.22.1
- 4.18.x(LTS) → 4.18.5
- 그 외 → 4.23.0(또는 LTS 라인으로 이동)[^1]

그리고 릴리스 노트는 4.23.0을 LTS 릴리스라고 명시합니다.[^12]

여기서 조직 내 합의가 갈리는 지점은 이겁니다.

- “우리는 당장 패치만 하고 싶다(변경 최소화)”
- “어차피 갈아엎는 김에 새 LTS로 간다(장기 유지)”

나는 이 결정을 감정/취향으로 안 하고, 아래 질문으로 쪼갭니다.

### 1) 이번 38건이 ‘설정 기본값 변화’를 동반하는가

Camel 공지 자체가 “일부 수정은 default behavior를 바꾼다”라고 경고합니다.[^1]

실제로 4.23 업그레이드 가이드에 “보안성 강화를 위한 기본 동작 변화”가 들어 있습니다.

- HTTP producer override header에서 placeholder를 더 이상 풀지 않음(CVE-2026-78164 연관)[^8]
- `camel-spring-redis` 기본 serializer가 deserialization filter를 적용하고, allow-list를 `deserializationFilter`로 확장[^8]

이런 변화는 보안에는 이득이지만 기능 호환성에는 비용이 됩니다. 업그레이드 테스트 범위를 줄이려면 “변경이 적은 라인에서 패치만”이 유리합니다.

### 2) 서비스가 ‘어느 라인을 이미 쓰고 있는가’가 비용을 지배한다

- 이미 4.22.x를 쓰는 서비스는 4.22.1로 가는 게 가장 저렴합니다.
- 이미 4.18.x를 쓰는 서비스는 4.18.5가 가장 저렴합니다.

이건 기술적으로 당연한데, 조직에서는 “한 번에 통일”이라는 욕망이 종종 튀어나옵니다. 통일은 장점도 있지만, 보안 패치 사건에서 통일을 1순위로 두면 테스트/릴리즈 병목이 더 커져 전체 대응이 느려지는 경우가 많았습니다.

### 3) 4.14.x 이하가 남아 있으면 결론은 빠르다

Camel은 4.14.x가 EOL이고 이번 수정 대부분이 4.14.x에도 해당한다고까지 말했습니다.[^1]

이건 사실상 “남아 있으면 빨리 탈출”입니다. LTS든 뭐든, 패치가 더 이상 안 나오면 취약점 대응 비용이 계속 누적됩니다.

### 4) Java 버전/런타임 정책을 같이 묶어야 한다

4.23.0 릴리스 노트는 Java 17, 21, 25를 지원한다고 씁니다.[^12]

조직에서 Java 업그레이드가 병행되는 구간이면, Camel 업그레이드 라인 선택이 Java 정책과 충돌하지 않는지 확인해야 합니다. “보안 패치”만 보다가, 런타임 정책이 발목을 잡는 게 흔한 비용입니다.

## 업그레이드/차단 전략을 ‘컴포넌트별 영향도’로 정리하는 템플릿

내가 내부적으로 정리할 때는 아래 6열로 끝냅니다.

1) Service
2) Entry trust boundary(인터넷/파트너/내부)
3) Camel component(artifact + scheme)
4) CVE list(Severity)
5) Immediate mitigation(차단/설정 안전화)
6) Upgrade path(4.18.5/4.22.1/4.23.0) + Test scope

여기서 “Immediate mitigation”은 업그레이드 전용이 아닙니다. 업그레이드 이후에도 남겨야 하는 공통 방어선이 많습니다.

- control header는 신뢰 경계에서 제거(이번 CVE 묶음이 아니어도 계속 유효)
- deserialization payload 타입을 JSON/String/bytes로 정규화(필터에 기대지 않게)
- authz/authn 결정을 Camel consumer 안이 아니라 앞단 경계에서 끝내기

이런 걸 먼저 깔아두면, 다음에 또 “다건 CVE 묶음”이 와도 영향도 산정이 빨라집니다.

## ‘한 번에 소화’할 때 테스트 범위를 줄이는 방법

테스트 범위 설계는 컴포넌트별로 갈라야 합니다. 이번 묶음처럼 취약점 유형이 서로 다른데도 “통합 테스트 한 세트”로 뭉치면 시간이 폭발합니다.

내가 쓰는 방식은 다음입니다.

### 1) 취약점 유형별로 회귀 테스트를 만든다

- placeholder/header 관련: 경계에서 `CamelHttpUri`류 제거가 항상 적용되는지, override header가 남아도 placeholder가 확장되지 않는지(업그레이드 후) 확인
- deserialization 관련: Redis/Hazelcast/JGroups 등에서 Java serialization이 들어오면 필터로 차단되는지, 혹은 애초에 serializer를 바꿔서 Java serialization이 안 들어오게 했는지 확인
- path traversal 관련: remote-file consumer를 쓰는 서비스는 “업그레이드 전에는 격리/권한 최소화”가 적용됐는지, 업그레이드 후에는 취약점 경로가 차단됐는지(가능하면 재현 테스트)
- auth bypass 관련: 인증 실패 케이스가 실제로 라우트를 중단시키는지(특히 `camel-oauth`는 advisory가 업그레이드 전에도 명시적 check를 권합니다)[^5]

### 2) 컴포넌트별로 테스트 우선순위를 분리한다

대체로 우선순위는 아래처럼 잡는 편입니다.

- 인터넷-facing HTTP consumer + `camel-netty-http`/`camel-oauth` 같이 인증/제약이 붙는 컴포넌트
- 메시지 기반 deserialization sink(`camel-spring-redis`, `camel-hazelcast` 등)
- 파일/스토리지 consumer(`camel-ftp`, `camel-smb`, `camel-azure-files` 등)

### 3) SBOM을 ‘패치 증거’로 남긴다

Camel은 4.0.3부터 모든 릴리스에 PGP-signed CycloneDX SBOM을 제공한다고 공식 문서에 적어두었습니다.[^7]

이건 “Camel을 올렸습니다”보다 더 강한 증거가 됩니다.

- 릴리스 버전이 바뀌었고
- 그 버전의 dependency 구성이 무엇인지
- 공급망 관점에서 무엇이 들어왔는지

CVE 대응 보고/감사에서 특히 유용합니다. “업그레이드 완료”를 증명하기 위한 자료를, 보안팀/플랫폼팀/개발팀이 같은 포맷으로 공유할 수 있습니다.

## 반론과 회의론: ‘우린 그 컴포넌트 안 써서 괜찮다’가 위험해지는 지점

이 말이 틀린 건 아닙니다. 실제로 컴포넌트 기반 인벤토리의 목적은 “안 써도 되는 업그레이드”를 줄이는 것입니다.

그런데 다음 조건이 겹치면 위험해집니다.

- build에는 포함돼 있다(누군가 starter를 추가했다)
- 라우트는 동적이다(toD/recipientList 등)
- 메시지는 여러 시스템을 거치며 헤더/바디가 섞인다

특히 CVE-2026-78164처럼 “헤더로 URI override + placeholder resolution”이 엮이면, 어떤 라우트는 정적으로 안전해 보여도 경계가 흐려지는 순간 바로 노출됩니다.[^2]

또한 remote-file consumer 취약점(CVE-2026-79983 등)은 “우린 상대 서버를 신뢰한다”가 전제입니다. FTP는 control channel 무결성이 없다는 사실이 advisory 자체에 적혀 있고, on-path 공격 가능성까지 언급합니다.[^4]

즉, “컴포넌트 안 쓴다”는 말은 (1) artifact가 없고, (2) 라우트에 스킴이 없고, (3) 동적으로도 생성되지 않으며, (4) 경계에서 control header를 제거한다는 게 같이 성립해야 안전합니다.

## 정리

2026-10-16 Camel의 38건 advisory 일괄 공지는 “패치를 하자”에서 끝나지 않고, 조직이 업그레이드 우선순위 산정과 테스트 범위 설계를 다시 하게 만드는 이벤트였습니다.[^1]

이때 의사결정의 단위는 Camel이 아니라 컴포넌트입니다.

- 서비스별 컴포넌트 인벤토리를 의존성과 라우트 양쪽에서 만든다.
- CVE를 노출 경로 타입으로 다시 분류해, 업그레이드 전에도 가능한 차단/안전화 조치를 먼저 적용한다.
- 업그레이드는 4.18.x/4.22.x LTS 패치로 빠르게 닫을지, 4.23.0 LTS로 장기 유지 전략을 가져갈지 “기본값 변화와 테스트 비용”으로 판단한다.

결국 이 방식이 다건 CVE 묶음을 반복적으로 맞아도 대응 속도와 품질을 동시에 유지하는 쪽으로 수렴합니다.

## 참고 자료

- [Apache Camel 보안 권고 38건 공지(4.18.5/4.22.1/4.23.0)](https://camel.apache.org/blog/2026/10/camel-security-advisories-4.23.0/)
- [Apache Camel 4.23 업그레이드 가이드](https://camel.apache.org/manual/camel-4x-upgrade-guide-4_23.html)
- [CVE-2026-78164 advisory: HTTP producer override header에서 placeholder 해석](https://camel.apache.org/security/CVE-2026-78164.html)
- [CVE-2026-78165 advisory: camel-spring-redis deserialization](https://camel.apache.org/security/CVE-2026-78165.html)
- [CVE-2026-78162 advisory: camel-hazelcast deserialization filter 누락](https://camel.apache.org/security/CVE-2026-78162.html)
- [CVE-2026-79983 advisory: camel-ftp path traversal](https://camel.apache.org/security/CVE-2026-79983.html)
- [CVE-2026-79984 advisory: camel-mina-sftp path traversal](https://camel.apache.org/security/CVE-2026-79984.html)
- [CVE-2026-79985 advisory: camel-smb path traversal](https://camel.apache.org/security/CVE-2026-79985.html)
- [CVE-2026-79986 advisory: camel-azure-files path traversal](https://camel.apache.org/security/CVE-2026-79986.html)
- [CVE-2026-80312 advisory: camel-oauth authentication bypass](https://camel.apache.org/security/CVE-2026-80312.html)
- [CVE-2026-80343 advisory: camel-netty-http security constraint bypass](https://camel.apache.org/security/CVE-2026-80343.html)
- [CVE-2026-83531 advisory: dynamic-router-control predicate code execution](https://camel.apache.org/security/CVE-2026-83531.html)
- [Apache Camel Security 페이지(보안 모델, SBOM, advisory 목록)](https://camel.apache.org/security/)
- [Apache Camel Security Model](https://camel.apache.org/manual/security-model.html)
- [Apache Camel 4.23.0 릴리스 노트](https://camel.apache.org/releases/release-4.23.0/)
- [Apache Camel SBOM 관련 글](https://camel.apache.org/blog/2026/06/camel-sbom-supply-chain/)
- [ASF: Foundation 규모 보안 스캔(Project Glasswing)](https://news.apache.org/foundation/entry/security-scanning-at-foundation-scale)
- [Apache httpd 2.4.69: HTTP/2 패치가 프록시 체인에 미치는 영향](https://daewooki.github.io/posts/apache-httpd-2469-proxy-chain-security/)
- [mod_pagespeed 2.2 운영: nginx에서 optimizer worker 붙이고 안전하게 업데이트하기](https://daewooki.github.io/posts/mod-pagespeed-22-nginx-worker-ops/)

[^1]: <https://camel.apache.org/blog/2026/10/camel-security-advisories-4.23.0/>
[^2]: <https://camel.apache.org/security/CVE-2026-78164.html>
[^3]: <https://camel.apache.org/security/CVE-2026-78165.html>
[^4]: <https://camel.apache.org/security/CVE-2026-79983.html>
[^5]: <https://camel.apache.org/security/CVE-2026-80312.html>
[^6]: <https://camel.apache.org/security/CVE-2026-83531.html>
[^7]: <https://camel.apache.org/security/>
[^8]: <https://camel.apache.org/manual/camel-4x-upgrade-guide-4_23.html>
[^9]: <https://camel.apache.org/security/CVE-2026-78162.html>
[^10]: <https://camel.apache.org/security/CVE-2026-79985.html>
[^11]: <https://camel.apache.org/security/CVE-2026-80343.html>
[^12]: <https://camel.apache.org/releases/release-4.23.0/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
