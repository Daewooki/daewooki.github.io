---
title: "OTLP JSON 엄격 파싱이 Collector 파이프라인을 깨는 방식"
description: "OTLP/JSON에서 unknown field를 에러로 바꾸는 순간, 버전 혼재·중간 변환·커스텀 ingester에서 드롭이 발생합니다."
date: 2026-09-28 10:16:22 +0900
categories: ["DevOps", "OpenTelemetry"]
tags: ["opentelemetry", "otel-collector", "otlp", "otlp-json", "schema-validation", "upgrade-strategy"]
render_with_liquid: false
---

## unknown field를 무시하라는 OTLP/JSON 규칙과, 이를 뒤집는 옵션의 의미

OTLP/JSON은 “Protobuf 메시지를 JSON으로 인코딩한 것”이지만, 일반적인 JSON API와는 목적이 다릅니다. 사람이 읽는 로그 포맷이 아니라, Protobuf 스키마를 전송하기 위한 표현입니다. 그래서 수신기 구현의 기본 목표는 관대함(lenient)입니다.

OTLP 스펙은 OTLP/JSON 수신기가 **unknown field를 무시해야 한다**고 명시합니다. 이유도 같이 적혀 있습니다. Binary Protobuf 언마샬러가 새로운 필드를 만나도 깨지지 않는 특성(forward compatibility)을 JSON에서도 유지해야 하기 때문입니다. 즉, 새로운 exporter가 필드를 하나 추가해도, 오래된 receiver가 전체 요청을 거절하면 파이프라인이 끊깁니다.[^1]

이 규칙이 의미하는 운영 상의 결론은 단순합니다.

- 파이프라인 경계(Agent → Gateway → Backend)에서 OTLP/JSON을 쓰는 순간, “수신기는 unknown을 무시한다”가 사실상 계약(contract)입니다.
- 그 계약을 어기는 ‘엄격 파싱(strict parsing)’은 기술적으로 가능하더라도, **업그레이드 호환성을 비용으로 지불하는 선택**입니다.

그럼에도 strict가 필요해지는 순간이 있습니다. 내 경험상, 관대함이 “성공처럼 보이는 실패”를 만든다는 점 때문입니다. 파이프라인에서 가장 위험한 장애는 에러가 아니라 조용한 유실입니다. 이 문제의 결은 예전에 LLM Structured Output에서 다뤘던 “JSON은 맞는데 스키마가 안 맞는 상황”과 비슷합니다. JSON 파서가 성공해버리면, 운영자는 안심하고 데이터는 이미 깨진 상태로 흘러갑니다.

- [LLM Structured Output의 진짜 난관: “JSON은 맞는데 스키마는 왜 안 맞지?”를 끝내는 Schema 제약 실전 가이드](https://daewooki.github.io/posts/2026-8-llm-structured-output-json-schema-2/)

OTLP/JSON에서도 같은 일이 일어납니다. JSON 문법은 맞지만 OTLP 스키마가 아닌 값(또는 OTLP처럼 보이지만 실제론 다른 포맷)을 넣으면, 일부 구현은 부분적으로만 읽고 나머지를 버리거나, 아예 에러 없이 빈 데이터로 끝날 수 있습니다.

## Collector v0.161.0 구간에서 확인해야 하는 변화: JSONUnmarshaler의 DisallowUnknownFields

opentelemetry-collector 계열 모듈의 `pdata` 패키지(로그/트레이스/메트릭/프로파일)의 JSON 언마샬링 API에 **DisallowUnknownFields** 옵션이 들어가 있습니다. 이 옵션은 “OTLP 스키마에 없는 JSON 필드를 만나면 에러로 처리”하도록 강제합니다.

핵심 포인트는 3가지입니다.

1) 기본값은 false(unknown 무시)입니다. 즉, 아무 설정을 안 하면 기존처럼 동작합니다.

2) true로 켜는 순간, forward compatibility를 포기합니다. 미래 버전의 OTLP가 새로운 필드를 추가하면, 최신 exporter가 보낸 데이터를 현재 receiver가 거부합니다.

3) 이 옵션이 Collector 설정(YAML)에 직접 노출되어 있는 개념이라기보다, Collector/Contrib 내부 컴포넌트나 커스텀 코드에서 `pdata`의 JSONUnmarshaler를 직접 쓸 때 “선택할 수 있는 스위치”에 가깝습니다.

`go.opentelemetry.io/collector/pdata/xpdata`의 문서에서도 동일한 경고를 합니다. unknown field는 기본적으로 무시되고, strict를 켜면 앞으로 추가될 필드까지 unknown으로 거부하게 된다고 적혀 있습니다.[^2]

또, Go 표준 `encoding/json`도 기본 동작은 unknown field를 무시하고, `Decoder.DisallowUnknownFields()`를 쓰면 에러로 바꿀 수 있다고 문서에 적혀 있습니다.[^3]

Collector 릴리스 자체로 보면, Linux 설치 문서가 `v0.161.0` 아티팩트 다운로드(예: `otelcol_0.161.0_linux_amd64.tar.gz`)를 명시하고 있어서, 운영 환경에서 “0.161.0 업그레이드”가 현실적으로 일어나는 구간입니다.[^4]

여기서 중요한 건, 많은 팀이 Collector 업그레이드를 “바이너리 교체”로만 생각한다는 점입니다. 그런데 telemetry 파이프라인은 바이너리 교체가 곧 스키마 해석기(parser)의 교체입니다. JSON strictness가 켜져 있거나, 중간에 커스텀 ingester가 이 옵션을 적용하기 시작하면, 업그레이드는 곧 계약의 해석 방식 변경입니다.

## 장애 패턴 1: 커스텀 exporter/ingester가 strict를 켜는 순간 생기는 ‘정상적인 장애’

### 흔한 아키텍처

- A팀: 브라우저/엣지에서 OTLP/HTTP로 JSON을 보냅니다(프록시를 두기 쉬움).
- B팀: 내부 Ingestion API(Go/Rust/Java)가 JSON을 받아서 `pdata`로 파싱한 뒤, 내부 큐(Kafka 등)에 넣고, 이후 Collector Gateway가 큐에서 읽어 백엔드로 보냅니다.

이때 B팀 Ingestion API는 대체로 두 부류입니다.

- “불완전한 OTLP/JSON”을 최대한 받아서 살리는 부류 (lenient)
- “계약 위반이면 빨리 실패시키자” 부류 (strict)

strict를 선호하는 동기도 이해는 됩니다.

- 포맷이 조금만 깨져도, 나중에 디버깅 비용이 기하급수적으로 커집니다.
- OTLP/JSON은 중첩이 깊어서, 한 군데만 타입이 틀려도 전체 의미가 변합니다.

문제는 strict를 켠 순간부터 장애가 ‘정상 동작’이 된다는 점입니다. 스키마 밖 필드 하나가 들어오면, 파서가 에러를 내고 요청 전체를 실패로 처리합니다.

### 장애가 운영에서 어떻게 보이느냐

OTLP/HTTP(JSON) 경로에서 이 에러는 흔히 아래 형태로 관측됩니다.

- HTTP 400 (Bad Request)
- gRPC status로는 INVALID_ARGUMENT(code=3)에 해당하는 메시지

과거 Collector에서도 JSON 요청에 extra key가 들어가면 400으로 떨어졌던 사례가 있습니다. 예시로, `extraKey`가 `InstrumentationScope`에 들어가면 `unknown field "extraKey" ...` 형태로 응답이 내려가는 보고가 있었습니다.[^5]

이게 무서운 이유는, 많은 SDK/exporter가 “INVALID_ARGUMENT 계열은 non-retryable”로 판단하고 버리기 때문입니다. 즉, 네트워크 장애처럼 재시도해서 복구되지 않습니다. 관측 데이터가 조용히 끊기고, 애플리케이션은 멀쩡합니다.

### 재현 가능한 최소 예제(Go): strict/lenient 비교

아래는 “OTLP/JSON을 받아서 `pdata`로 언마샬링”하는 커스텀 ingester가 strict를 켰을 때 어떤 식으로 깨지는지 확인하는 최소 예제입니다.

- 현실적인 시나리오: Kafka나 S3에 쌓인 OTLP/JSON 배치를 사후 검증하거나, 인제스터 앞단에서 방화벽처럼 검증하고 싶을 때
- 중요한 점: 이 코드는 Collector를 대체하지 않습니다. strict가 파이프라인을 깨는 지점을 ‘눈으로 확인’하는 용도입니다.

### 1) 디렉터리 구조

```bash
otlpjsonlint/
  go.mod
  cmd/otlpjsonlint/main.go
  samples/
    metrics.valid.json
    metrics.unknown-field.json
```

### 2) go.mod (Collector v0.161.0에 맞춰 고정)

```go
module otlpjsonlint

go 1.22

require (
  go.opentelemetry.io/collector/pdata/pmetric v0.161.0
)
```

### 3) cmd/otlpjsonlint/main.go

```go
package main

import (
	"flag"
	"fmt"
	"os"

	"go.opentelemetry.io/collector/pdata/pmetric"
)

func main() {
	strict := flag.Bool("strict", false, "fail on unknown JSON fields")
	flag.Parse()

	if flag.NArg() != 1 {
		fmt.Fprintln(os.Stderr, "usage: otlpjsonlint [--strict] <file.json>")
		os.Exit(2)
	}

	path := flag.Arg(0)
	buf, err := os.ReadFile(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read failed: %v\n", err)
		os.Exit(1)
	}

	u := &pmetric.JSONUnmarshaler{}
	// v0.161.0 계열 pdata JSONUnmarshaler에 들어간 옵션.
	// (default false: unknown 무시 / true: unknown 에러)
	u.DisallowUnknownFields = *strict

	md, err := u.UnmarshalMetrics(buf)
	if err != nil {
		fmt.Fprintf(os.Stderr, "unmarshal failed: %v\n", err)
		os.Exit(1)
	}

	rmCount := md.ResourceMetrics().Len()
	smTotal := 0
	mTotal := 0
	for i := 0; i < rmCount; i++ {
		sm := md.ResourceMetrics().At(i).ScopeMetrics()
		smTotal += sm.Len()
		for j := 0; j < sm.Len(); j++ {
			mTotal += sm.At(j).Metrics().Len()
		}
	}

	fmt.Printf("OK: resourceMetrics=%d scopeMetrics=%d metrics=%d\n", rmCount, smTotal, mTotal)
}
```

### 4) samples/metrics.valid.json

OTLP/JSON의 최소 형태로, `resourceMetrics → scopeMetrics → metrics → sum.dataPoints`만 넣습니다. 64-bit 정수는 스펙 상 JSON에서 문자열로도 올 수 있고(또는 number도 허용) 디코딩 시 number/string을 둘 다 받아야 한다는 규칙이 있어, 여기서는 문자열로 작성합니다.[^1]

```json
{
  "resourceMetrics": [
    {
      "resource": {
        "attributes": [
          {"key": "service.name", "value": {"stringValue": "checkout"}}
        ]
      },
      "scopeMetrics": [
        {
          "scope": {"name": "manual"},
          "metrics": [
            {
              "name": "http.server.request.count",
              "unit": "1",
              "sum": {
                "aggregationTemporality": 2,
                "isMonotonic": true,
                "dataPoints": [
                  {
                    "startTimeUnixNano": "1730000000000000000",
                    "timeUnixNano": "1730000001000000000",
                    "asInt": "1",
                    "attributes": [
                      {"key": "http.method", "value": {"stringValue": "GET"}}
                    ]
                  }
                ]
              }
            }
          ]
        }
      ]
    }
  ]
}
```

### 5) samples/metrics.unknown-field.json

위 JSON에 `scope` 아래 `extraKey`를 하나 추가합니다. 이 필드는 OTLP 스키마 밖이라고 가정합니다.

```json
{
  "resourceMetrics": [
    {
      "resource": {
        "attributes": [
          {"key": "service.name", "value": {"stringValue": "checkout"}}
        ]
      },
      "scopeMetrics": [
        {
          "scope": {"name": "manual", "extraKey": "should-fail-in-strict"},
          "metrics": [
            {
              "name": "http.server.request.count",
              "unit": "1",
              "sum": {
                "aggregationTemporality": 2,
                "isMonotonic": true,
                "dataPoints": [
                  {
                    "startTimeUnixNano": "1730000000000000000",
                    "timeUnixNano": "1730000001000000000",
                    "asInt": "1"
                  }
                ]
              }
            }
          ]
        }
      ]
    }
  ]
}
```

### 6) 실행

```bash
# lenient: unknown을 무시하고 통과할 가능성이 큼
go run ./cmd/otlpjsonlint -strict=false ./samples/metrics.unknown-field.json

# strict: unknown을 에러로 처리
go run ./cmd/otlpjsonlint -strict=true ./samples/metrics.unknown-field.json
```

이 실험이 운영에 주는 메시지는 명확합니다.

- strict를 켜는 건 “데이터를 더 정확히 받겠다”가 아니라 “계약 위반이면 드롭하겠다”입니다.
- 드롭은 대부분 non-retryable이라, 순간적인 장애가 아니라 관측 공백을 만듭니다.

## 장애 패턴 2: 중간 변환(JSON) 구간이 ‘스키마 외 필드’를 만들어내는 방식

OTLP/JSON을 중간 포맷으로 쓰는 경우는 생각보다 많습니다.

- 브라우저 → Collector Gateway: CORS/프록시/방화벽 때문에 HTTP JSON을 선호
- (준)실시간 파이프라인: Collector → Kafka(OTLP/JSON) → Stream processor → Collector
- 저장/재처리: S3에 JSON으로 적재 → 재처리

여기서 strict가 파이프라인을 깨는 방식은 2갈래입니다.

### (A) enrichment가 상위 레벨에 필드를 주입하는 순간

현장에서 자주 보는 실수는 “OTLP 안에 테넌트나 클러스터 정보를 넣자”입니다. 가장 쉬운 구현은 JSON object 최상단에 다음을 추가하는 겁니다.

- `tenantId`
- `cluster`
- `receivedAt`

문제는 OTLP 스키마는 최상단에 그런 필드가 없다는 점입니다. lenient 파서는 이를 무시하고 지나갈 수 있고, strict는 즉시 에러가 납니다.

이때 운영자가 겪는 현상은 단순합니다.

- 중간 변환을 도입한 날부터, 특정 테넌트만 0% 수집
- 재처리 작업에서만 실패(실시간은 통과)

실시간은 통과하는데 재처리만 실패하는 케이스는, 실시간 경로는 protobuf(4317)로 보내고, 재처리는 JSON을 쓰는 혼합 구성에서 자주 터집니다.

### (B) “OTLP처럼 보이는 JSON”이 섞여 들어오는 순간

OTLP/JSON 파서는 의외로 “입력이 정말 OTLP/JSON인지”를 강하게 검증하지 않을 수 있습니다. 실제로 `pdata`의 JSONUnmarshaler가 OTLP JSON인지 감지하지 못해, 포맷이 다르면 조용히 드롭될 수 있다는 문제 제기가 있었습니다.[^6]

이 케이스는 특히 위험합니다.

- strict unknown-field는 ‘에러’를 만들지만,
- lenient + 약한 감지는 ‘성공처럼 보이는 실패’를 만듭니다.

중간 변환 구간에서 JSON이 섞이는 이유는 다양합니다.

- 로그 파이프라인이 “JSON line”을 모두 OTLP/JSON이라고 오해
- protobuf JSON mapping과 OTLP JSON deviations를 혼동(예: enum을 문자열로 넣는 등)
- snake_case로 필드명이 변환됨

이런 장애는 재현도 어렵고, 장애 감지도 늦습니다. 그래서 내 경우엔 JSON을 중간 포맷으로 쓰는 순간부터 “계약 검증”을 별도의 라인으로 넣는 편이 낫다고 결론냈습니다.

관련해서, 이전에 정리했던 OTLP metrics 파이프라인 체크리스트의 관점(어디서 드롭이 나오는지 계측을 먼저 박아두는 방식)이 이런 구간에서 특히 유효합니다.

- [Telemetry API 이후 Cloud Monitoring OTLP 메트릭 파이프라인 체크리스트](https://daewooki.github.io/posts/otlp-metrics-cloud-monitoring-checklist/)

## 장애 패턴 3: 버전 혼재(Agent/Gateway/Backend)에서 strict가 폭발하는 지점

OTel 생태계는 “버전이 혼재되는 게 정상”인 시스템입니다.

- 앱 SDK/Agent는 서비스 별로 배포 주기가 다릅니다.
- Gateway Collector는 플랫폼팀이 관리합니다.
- Backend(벤더 SaaS 또는 사내 저장소)는 또 다른 업그레이드 주기를 가집니다.

이때 strict parsing은 업그레이드 순서를 강제합니다. 구체적으로는 “가장 오래된 receiver가 전체 호환성을 결정”합니다.

### (1) exporter가 새 필드를 추가하는 순간

스펙은 unknown field를 무시하라고 했습니다. 이는 새 필드가 추가되는 걸 전제로 합니다.[^1]

하지만 strict receiver는 새 필드를 ‘오류’로 취급합니다. 따라서 업그레이드 전략이 이렇게 바뀝니다.

- lenient 세계: exporter부터 올려도 된다(새 필드는 무시됨)
- strict 세계: receiver부터 올려야 한다(아니면 exporter가 보낸 요청이 거절됨)

여기서 파이프라인이 깨지는 패턴은 보통 아래처럼 나타납니다.

- 일부 서비스만 최신 SDK로 업그레이드
- 그 서비스만 관측이 끊김
- Gateway는 정상(프로세스 살아있음)인데, 특정 요청만 400

장애가 “부분 실패”로 나타나기 때문에 탐지 난이도가 올라갑니다.

### (2) JSON 경로만 별도로 깨지는 순간

Collector는 OTLP receiver에서 gRPC(4317)와 HTTP(4318)를 같이 받습니다. HTTP는 protobuf와 JSON을 둘 다 받으며, URL path는 `/v1/traces`, `/v1/metrics`, `/v1/logs` 같은 기본값을 씁니다.[^7]

그래서 실제 운영에서는 이런 조합이 생깁니다.

- 서버 앱/Agent: gRPC(프로토)로 보냄 → 안정적
- 브라우저/엣지: HTTP/JSON으로 보냄 → 변환/프록시 때문에 변형 가능성이 큼

strict는 보통 브라우저 쪽 JSON에서 먼저 터집니다. 서버 쪽은 protobuf라 unknown field도 구조적으로 덜 문제가 되기 때문입니다.

### (3) “업그레이드 중간 상태”가 가장 위험하다

업그레이드가 진행되는 1~2주 동안이 가장 위험합니다.

- A 서비스: 새 SDK, 새 필드 포함
- B 서비스: 구 SDK, 필드 없음
- Gateway: strict

이 상태에서 strict는 A 서비스만 드롭합니다. 모니터링은 전체 집계라서 B 서비스가 정상이라 “전체는 정상”으로 보일 수 있습니다.

내가 운영에서 제일 싫어하는 장애가 이겁니다. 알람이 울리지 않는 데이터 손실.

## Collector 바이너리로 확인하는 OTLP/HTTP(JSON) 경계

Collector를 업그레이드하면서 가장 먼저 해야 하는 확인은 “내 경계가 어디인지”입니다.

- 어떤 구간이 OTLP/HTTP(JSON)을 받는가?
- 그 구간에 프록시/변환기가 있는가?
- 누가 그 변환기를 소유하고, 언제 배포되는가?

Linux 환경에서 `v0.161.0` Collector는 공식 문서에 DEB/RPM/Manual 설치 방법이 있고, tar.gz로 받아서 압축을 풀 수 있습니다.[^4]

```bash
curl --proto '=https' --tlsv1.2 -fOL \
  https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.161.0/otelcol_0.161.0_linux_amd64.tar.gz

tar -xvf otelcol_0.161.0_linux_amd64.tar.gz

./otelcol --help
```

OTLP receiver에서 HTTP/JSON을 받는 기본 동작과 URL path 기본값은 OTLP receiver 문서에 정리되어 있습니다.[^7]

이 섹션의 요지는 설치 자체가 아니라, 업그레이드 시점에 “경계(특히 HTTP/JSON)”를 빠르게 재현할 수 있는 환경을 만들라는 겁니다. 파이프라인 장애는 대부분 경계에서 터집니다.

## 안전한 단계적 업그레이드 전략: strict를 ‘차단 스위치’가 아니라 ‘검증 라인’으로 쓴다

이 옵션을 진짜로 운영에서 쓰려면 결론은 하나입니다.

- main ingestion 경로에서 strict를 켜서 차단하면, 업그레이드 호환성을 잃습니다.
- 대신 strict를 별도의 검증 라인으로 두고, “드롭 없이 계약 위반을 관측”해야 합니다.

여기서는 내가 권하는 단계적 전략을 정리합니다.

### 1) strict를 켜면 잃는 것부터 문서화한다

`pdata` 문서 자체가 경고하듯, strict는 forward compatibility를 깨뜨립니다.[^2]

따라서 아래 항목을 먼저 내부 문서에 박아야 합니다.

- strict 모드는 “OTLP 버전이 더 최신인 exporter”를 받아들일 수 없을 수 있다.
- strict 에러는 대부분 non-retryable로 처리되어 데이터 공백이 생긴다.
- strict가 필요한 이유는 ‘보안’이 아니라 ‘계약 위반 탐지’다.

이게 정리되지 않으면, 운영 중 누군가 “데이터 품질 올리자” 한마디로 strict를 main 경로에 켰다가, 업그레이드 주간에 관측이 끊깁니다.

### 2) main 경로는 lenient 유지, strict는 shadow로 붙인다

구성 아이디어는 단순합니다.

- (A) Production pipeline: lenient로 수집해 백엔드로 전송
- (B) Validation pipeline: 동일 입력을 strict로 파싱해 에러를 metric/log로만 남김

Collector 단독으로 입력을 2갈래로 분기하는 건 쉬운데(파이프라인을 두 개 두거나 connector를 이용), 문제는 “strict 파싱 자체가 Collector 설정만으로 켜지지 않을 수 있다”는 점입니다. 그래서 현실적인 방법은 아래 둘 중 하나입니다.

- 방법 1: 커스텀 receiver/extension을 만들어 strict 파서를 붙이고, 그것을 validation용 Collector distro에만 포함
- 방법 2: Collector 앞단(ingress)에서 트래픽을 미러링해서 별도 validator 서비스로 보냄(앞서 만든 `otlpjsonlint` 같은 코드를 HTTP server 형태로 확장)

둘 다 장단이 있습니다.

- 커스텀 컴포넌트는 배포/업그레이드 책임이 생깁니다.
- 미러링은 인프라 의존(Envoy/Nginx/LB)과 개인정보/보안 이슈가 생깁니다.

내 경우엔 “validation은 운영 경로를 절대 멈추면 안 된다”는 조건이 더 중요해서, 미러링 기반 shadow validator를 선호합니다.

### 3) shadow에서 먼저 잡아야 하는 위반 유형을 정한다

strict validator를 붙이면 에러가 꽤 많이 나옵니다. 전부를 동일 심각도로 보면 결국 무시하게 됩니다. 우선순위를 나눠야 합니다.

- P0: 아예 OTLP/JSON이 아닌 입력이 섞임(조용한 드롭 가능성)[^6]
- P1: unknown field(스키마 진화/팀별 enrichment/프록시 변형)[^1]
- P2: 타입 불일치(정수/문자열, enum 문자열 등)

P0/P1은 업그레이드 전략과 직결되고, P2는 구현체/언어별 차이까지 들어가서 처리 비용이 커집니다.

### 4) 업그레이드 순서를 ‘버전 혼재 최악 조건’ 기준으로 잡는다

버전 혼재에서 strict가 깨지는 핵심은 “새 exporter → old receiver”입니다. 따라서 업그레이드 순서는 아래를 기본으로 잡는 편이 안전합니다.

- Gateway/Receiver 계층을 먼저 올린다(가능하면 lenient로 유지)
- 그 다음 Agent/SDK를 올린다
- 마지막으로 strict validation의 기준을 업데이트한다

여기서 중요한 건, strict validation의 기준이 곧 “허용 스키마”라는 점입니다. OTLP는 앞으로도 필드가 추가될 수 있고(스펙이 그렇게 설계됨), strict는 그 추가를 장애로 바꿉니다.[^1]

그래서 strict를 main 경로에 넣는 순간, 업그레이드의 자유도가 확 줄어듭니다. 플랫폼팀이 모든 팀의 SDK 업그레이드 타이밍을 강제할 수 있을 때만 선택해야 합니다.

### 5) strict를 main에 넣어야 한다면, 적용 범위를 기술적으로 쪼갠다

조직 사정상 “계약 위반은 차단”이 필요할 수 있습니다. 예를 들어 외부 파트너가 OTLP/JSON을 직접 쏘는 구조라면, 수신기 입장에서 관대함은 공격 표면이 됩니다.

이 경우에도 전면 strict는 위험합니다. 아래처럼 범위를 분리하는 방식이 그나마 현실적입니다.

- 외부 입력 endpoint만 strict
- 내부 입력(자사 SDK/Agent) endpoint는 lenient
- 또는 strict는 canary(특정 헤더/특정 토큰/특정 테넌트)에만 적용

OTLP receiver는 HTTP path를 커스터마이즈할 수 있습니다. 내부/외부를 다른 리스너로 분리하면, strict 적용 범위를 분리하기가 쉬워집니다.[^7]

### 6) 최종 판단 기준: strict는 품질 도구이지 호환성 도구가 아니다

정리하면, **DisallowUnknownFields**는 “OTLP를 더 잘 지원”하기 위한 옵션이 아니라 “내 파이프라인을 더 폐쇄적으로 만들기 위한 옵션”에 가깝습니다. `pdata` 문서의 경고 그대로, 이 옵션은 미래 OTLP 진화를 거부합니다.[^2]

내 결론은 이렇습니다.

- OTLP/JSON을 외부에 열어야 하거나, 중간에 JSON 변환이 많다면: strict는 main이 아니라 shadow validator로 두는 게 맞습니다.
- 팀/서비스가 많아서 버전 혼재가 상수라면: strict는 업그레이드 주간의 장애를 만들 확률이 높습니다.
- 모든 exporter/agent 버전을 강제할 수 있고, 데이터 품질이 최우선인 폐쇄망이라면: strict를 부분적으로(외부만/테넌트별) 도입할 수 있습니다.

관측 파이프라인에서 가장 비싼 장애는 “정확히 언제부터, 무엇이, 얼마나 유실됐는지 모르는 상태”입니다. strict는 그 상태를 줄이는 도구가 될 수도 있고, 반대로 유실을 만들어내는 스위치가 될 수도 있습니다. 업그레이드 구간에서는 후자에 더 가깝게 동작한다고 보는 편이 안전합니다.

## 참고 자료

- [OpenTelemetry Collector v1.67.0/v0.161.0 릴리스 태그](https://github.com/open-telemetry/opentelemetry-collector/releases/tag/v0.161.0)
- [Install the Collector on Linux](https://opentelemetry.io/docs/collector/install/binary/linux/)
- [OTLP Specification: JSON Protobuf Encoding(unknown field 무시 규칙)](https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding)
- [OTLP receiver README: HTTP/JSON 엔드포인트와 URL path](https://github.com/open-telemetry/opentelemetry-collector/blob/main/receiver/otlpreceiver/README.md)
- [OTLP receiver config reference(HTTP는 Proto와 JSON 지원)](https://github.com/open-telemetry/opentelemetry-collector/blob/main/receiver/otlpreceiver/config.md)
- [go.opentelemetry.io/collector/pdata/xpdata JSONUnmarshaler 문서(DisallowUnknownFields 경고 포함)](https://pkg.go.dev/go.opentelemetry.io/collector/pdata/xpdata)
- [Collector CHANGELOG-API: JSONUnmarshaler에 DisallowUnknownFields 옵션 추가](https://github.com/open-telemetry/opentelemetry-collector/blob/main/CHANGELOG-API.md)
- [GitHub 이슈: http receiver가 extra key가 있는 JSON 요청을 400으로 드롭하는 사례](https://github.com/open-telemetry/opentelemetry-collector/issues/5312)
- [GitHub 이슈: OTLP JSON이 아닌 입력을 pdata가 조용히 드롭할 수 있다는 문제 제기](https://github.com/open-telemetry/opentelemetry-collector/issues/15279)
- [Go encoding/json 문서(unknown field 기본 무시, DisallowUnknownFields 언급)](https://go.dev/pkg/encoding/json/)

[^1]: <https://opentelemetry.io/docs/specs/otlp/>
[^2]: <https://pkg.go.dev/go.opentelemetry.io/collector/pdata/xpdata>
[^3]: <https://go.dev/pkg/encoding/json/?m=old>
[^4]: <https://opentelemetry.io/docs/collector/install/binary/linux/>
[^5]: <https://github.com/open-telemetry/opentelemetry-collector/issues/5312>
[^6]: <https://github.com/open-telemetry/opentelemetry-collector/pull/15279>
[^7]: <https://github.com/open-telemetry/opentelemetry-collector/blob/main/receiver/otlpreceiver/README.md?plain=1>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
