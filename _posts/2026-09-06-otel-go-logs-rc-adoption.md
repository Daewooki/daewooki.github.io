---
title: "OpenTelemetry Go Logs RC로 시작하는 로그 표준화"
description: "Go Logs API/SDK가 RC에 진입했습니다. 브리지 전략, 글로벌 API 마이그레이션, correlation 설계, 14일 검증 체크리스트를 정리합니다."
date: 2026-09-06 10:01:42 +0900
categories: ["Tools", "OpenTelemetry"]
tags: ["opentelemetry", "golang", "logging", "observability", "otel-logs"]
render_with_liquid: false
---

2026년 8월 31일 OpenTelemetry가 Go Logs API/SDK를 **RC**(v1.47.0-rc.1)로 올렸습니다. 여기서 중요한 건 새 기능 소개가 아니라, “이 API가 v1 호환성 보장을 걸고 고정되기 직전”이라는 점입니다. 공식 발표는 “게시 후 최소 14일 피드백을 기다린 뒤 안정화로 진행”한다고 명시합니다. 즉 2026-08-31 이후 최소 14일이면 2026-09-14부터는 안정화(또는 다음 RC로 재시작) 경로로 들어갈 수 있습니다. 2026-09-06 KST 시점이면 남은 시간은 많지 않습니다.[^1]

기존에 zap/logrus/slog로 안정적으로 운영하던 로깅을 버리고 OTel 로그로 갈아타는 얘기가 아닙니다. 내가 지금 이 RC를 보는 이유는 더 단순합니다.

- 로그 수집 파이프라인이 아니라 **애플리케이션 로깅 API 표준화**가 고정되면, 앞으로 2~3년은 그 모양대로 생태계가 쌓입니다.
- 고정되기 전 마지막 창구에서, “브리지/어댑터의 비용”, “글로벌 LoggerProvider 전파 모델”, “trace/metric/log correlation이 실제로 성립하는지”를 서비스 코드에 대입해 확인할 수 있습니다.

이 타이밍을 놓치면, 깨달은 문제를 해결하는 비용이 프로젝트 단위가 아니라 조직 단위로 커집니다. 예전에 AI API/정책이 조용히 바뀌면서 운영 비용이 튀는 패턴을 다뤘는데, observability 쪽에서도 본질은 같습니다. 바뀌는 게 문제가 아니라, 고정된 다음에 알게 되는 게 문제입니다: [빅테크 AI “발표”보다 더 무서운 건 API/정책의 조용한 변경이다](https://daewooki.github.io/posts/2026-3-ai-api-1/).

## RC가 확정하려는 범위: API/SDK는 v1, exporter는 그대로 실험

이번 RC가 커버하는 모듈은 두 개입니다.

- `go.opentelemetry.io/otel/log`
- `go.opentelemetry.io/otel/sdk/log`

이 둘이 기존 `v0.22.0`(beta)에서 `v1.47.0-rc.1`로 올라가며, 안정화되면 v1 호환성 보장을 제공한다고 설명합니다.[^1]

여기서 실무적으로 한 번 더 걸러야 합니다. 발표문은 “log exporters와 logtest는 experimental이며 RC 안정성 범위에 포함되지 않는다”고 선을 긋습니다.[^1]

즉, 애플리케이션 관점에서 API/SDK는 고정되지만, OTLP logs exporter 쪽은 앞으로도 흔들릴 수 있습니다. Go 공식 문서에서도 console log exporter와 OTLP logs exporter가 (Experimental)로 표시됩니다.[^2]

내 결론은 이겁니다.

- 지금 검증의 중심은 exporter가 아니라 “앱 내부 로깅 모델”이다.
- exporter는 바뀔 수 있으니, 검증할 때도 exporter를 교체 가능한 구성으로 두고(예: env 기반 팩토리), 앱 코드가 exporter에 종속되지 않게 봐야 합니다.

## Logs API의 설계 의도: 애플리케이션이 아니라 브리지를 위한 API

OpenTelemetry Logs API 문서가 처음부터 못 박는 전제가 있습니다. Logs API는 로깅 라이브러리 작성자가 기존 로깅 라이브러리와 OpenTelemetry log data model 사이를 잇는 “log appender/bridge”를 만들 수 있게 제공된다는 점입니다.[^3]

이 관점이 중요한 이유는, 많은 팀이 OTel Logs를 “새 로거를 또 하나 도입하는 일”로 오해하기 때문입니다. 실제로는 다음 두 개를 분리하는 게 더 자연스럽습니다.

- 애플리케이션 코드가 호출하는 로깅 인터페이스(zap/logrus/slog 등)
- 로그가 최종적으로 표현/전송되는 표준 데이터 모델(OTel LogRecord)

OTel이 노리는 건 두 번째입니다. 표준 데이터 모델이 고정되면, 로그를 파일로 남기든 OTLP로 보내든, 특정 벤더 백엔드로 보내든, “변환의 대상”이 통일됩니다.

OTel 로그 데이터 모델은 LogRecord가 어떤 필드를 가져야 하는지를 명확히 정의합니다. Timestamp/ObservedTimestamp/Severity/Body/Attributes/Resource/InstrumentationScope가 있고, correlation을 위해 TraceId/SpanId/TraceFlags가 최상위 필드로 존재합니다.[^4]

여기서 실무적으로 의미 있는 변화는 두 가지입니다.

1) trace id/span id를 attributes로 우겨 넣는 시대가 끝납니다. 표준 상 “최상위 필드”입니다.[^4]

2) severity가 문자열이 아니라 숫자 범위(1~24)로 정규화됩니다. TRACE/DEBUG/INFO/WARN/ERROR/FATAL이 각 4단계로 쪼개지고, 이 범위를 어떻게 매핑해야 하는지까지 규정합니다.[^4]

이게 고정되면, 브리지 구현체가 일관되게 동작하고, 운영자는 로그 레벨/필터링 규칙을 cross-language로 맞추기가 쉬워집니다.

## zap/logrus/slog와의 접점: 브리지 전략을 잘 잡으면 갈아엎지 않는다

브리지의 목적은 하나입니다. 기존 로깅 호출 지점을 건드리지 않으면서, 출력 경로를 OTel LogRecord로 하나 더 늘리거나(dual-write), 또는 점진적으로 교체할 수 있게 만드는 겁니다.

Go 생태계에서 이미 “브리지 형태”가 다 나와 있습니다.

- `otelslog`: `slog.Handler` 구현[^5]
- `otelzap`: `zapcore.Core` 구현[^6]
- `otellogrus`: `logrus.Hook` 구현[^7]

이게 왜 좋냐면, 기존 로깅 라이브러리가 제공하는 확장 포인트(Handler/Core/Hook)에 붙는 형태라 “내 코드에 OTel 로거를 새로 주입”하는 방식보다 침투가 쉽습니다.

### slog: 표준 로거(slog)를 OTel로 보내되, stdout도 유지하기

slog는 Go 표준이고, 최근 Go 서비스들은 JSON 로깅을 slog로 가는 흐름이 많습니다. `otelslog`는 `slog.Handler`로 구현돼서, slog의 `InfoContext/ErrorContext`처럼 context를 받는 호출을 그대로 살릴 수 있습니다.[^8]

여기서 내가 실서비스에 대입할 때의 핵심은 “dual-write를 먼저 만들 수 있느냐”입니다.

- 기존 stdout(JSON) 로깅은 그대로 남긴다.
- 동일한 slog Record를 OTel Handler에도 전달한다.

이렇게 하면 RC 검증이 훨씬 현실적입니다. OTLP 파이프라인이 불안정해도 운영 로그는 계속 남고, OTel로 나간 로그는 별도로 비교할 수 있습니다.

또 하나, `otelslog.WithSource(true)`는 source location을 code.* attributes로 넣는 옵션이 추가된 것으로 changelog에 언급됩니다.[^9]

source location은 디버깅엔 도움이 되지만, 비용도 증가할 수 있습니다(문자열/경로/함수명). 이 부분은 RC 기간에 실제 볼륨에서 확인해야 하는 지점입니다.

### zap: 기존 zap.Core 체인을 끊지 않고 OTel Core를 티로 붙이기

`otelzap`는 `zapcore.Core`로 구현돼서, 기존 zap logger가 있으면 `zapcore.NewTee`로 “기존 Core + OTel Core”를 합칠 수 있습니다. 브리지 문서가 기록 변환 규칙도 꽤 구체적으로 적고 있습니다(Time→Timestamp, Message→Body, Level→Severity, Fields→Attributes, error 타입은 SetErr 등).[^6]

내가 중요하게 보는 포인트는 context 전달 방식입니다. `otelzap`는 “Field 값이 context.Context 타입이면 그 값을 Emit에 사용한다”고 명시합니다.[^6]

즉 zap 쪽은 호출마다 ctx를 넘기지 못하는 구조를, 필드로 주입하는 방식으로 해결합니다. 이건 깔끔한 해결이긴 한데, 서비스 코드에서 ctx가 어떤 방식으로 흘러가야 하는지(로그 호출 지점마다 ctx가 있나?)를 다시 보게 만듭니다.

### logrus: Hook으로 최소 침투

logrus는 구식이 됐다고 해도, 레거시 서비스에서는 여전히 많습니다. `otellogrus`는 Hook 형태이고, 변환 규칙과 severity 매핑을 문서에 명시합니다. 예를 들어 logrus.DebugLevel→SeverityDebug, PanicLevel→SeverityFatal4 같은 식입니다.[^7]

여기서 중요한 건 “Hook이 실행되는 시점에 context를 어디서 가져오냐”입니다. logrus.Entry는 기본적으로 context를 들고 있지 않습니다. 결국 correlation을 하려면 Entry에 ctx를 넣거나(커스텀 필드), middleware에서 logger를 wrapping하는 등의 추가 설계가 필요합니다. Hook은 접점이지만, correlation까지 자동으로 해결해주진 않습니다.

### 브리지에서 공통으로 생기는 함정: 필드/속성 매핑과 cardinality

OTel LogRecord는 Attributes가 map 형태로 가고, 값 타입은 AnyValue처럼 제한이 있습니다. 브리지가 어떤 타입을 어떻게 바꾸는지가 운영 비용으로 직결됩니다.

- zap/logrus 필드에 slice/map/struct를 많이 넣어왔던 서비스는 브리지에서 변환 비용이 발생합니다.
- 변환이 안 되는 타입은 fmt.Sprintf로 문자열화될 수 있는데, 이건 데이터 품질이 흔들립니다(검색/집계가 불리해짐).[^7]

RC 기간에 해야 하는 검증은 “잘 되는지”가 아니라 “잘 안 될 때 어떤 꼴로 망가지는지”입니다.

- 어느 타입이 string으로 강제 변환되는지
- 변환 실패/패닉이 존재하는지
- 변환 결과가 백엔드에서 제대로 인덱싱되는지

이게 확인되지 않은 상태에서 표준화에 올라타면, 나중에 로그 스키마 정리 작업이 instrumentation보다 더 큰 프로젝트가 됩니다.

## LoggerProvider 전파: global 패턴이 바뀌는 지점이 마이그레이션의 핵심

이번 RC에서 실제로 “서비스 코드가 바뀔 가능성이 큰 부분”은 글로벌 API입니다.

발표문과 릴리스 노트는 공통으로 이렇게 말합니다.

- `go.opentelemetry.io/otel` 루트 패키지에 `Logger`, `GetLoggerProvider`, `SetLoggerProvider`를 추가했다.
- 기존 `go.opentelemetry.io/otel/log/global`의 동등 API는 deprecated 처리했다.[^1]

기존 `log/global` 패키지 문서도 “log 패키지가 stable이 되면 deprecated 및 제거될 것이고, 기능은 go.opentelemetry.io/otel로 migrate된다”고 이미 써놨습니다.[^10]

### 왜 글로벌이 중요한가: 브리지는 기본적으로 global LoggerProvider를 바라본다

`otelslog`/`otelzap`/`otellogrus`는 옵션으로 LoggerProvider를 주입할 수 있지만, 기본값은 global provider를 사용합니다.[^5]

따라서 실서비스 마이그레이션은 다음 순서를 강제합니다.

1) 프로세스 부팅 초기에 LoggerProvider를 구성한다.
2) global provider를 설정한다.
3) 브리지를 붙인다.
4) shutdown에서 flush/shutdown을 보장한다.

이 순서가 흐트러지면, 로그가 no-op로 드랍되거나(초기화 전), batch processor에 쌓인 채로 종료될 수 있습니다.

### global provider의 “프록시 업데이트” 동작을 이해해야 한다

`go.opentelemetry.io/otel/log/global` 문서는 “provider 설정 전에는 No-Op를 반환하지만, 최초 provider 등록 시 기존에 반환된 LoggerProvider/Logger가 in-place로 업데이트된다”고 설명합니다.[^10]

이 패턴은 tracer/meter 쪽 global과 유사합니다. 장점은 초기화 순서에 덜 민감해지는 것이고, 단점은 팀이 “그럼 아무 때나 Set 해도 되겠네”로 오해하기 쉽다는 겁니다. 업데이트가 된다고 해도, 초기화 전에 찍힌 로그는 이미 버려졌습니다.

### 마이그레이션의 실제 작업 단위: import 경로 정리 + 초기화 함수 계약

내가 RC 기간에 보는 마이그레이션 체크 포인트는 세 가지입니다.

1) 코드베이스에서 `go.opentelemetry.io/otel/log/global` import를 얼마나 쓰고 있나
2) 공통 telemetry 초기화 패키지가 있나(예: internal/telemetry)
3) init order가 안정적인가(main에서 한 번만 호출되는가)

특히 monorepo/멀티서비스 환경에서는 telemetry 초기화 코드를 공통 모듈로 뽑아두는 경우가 많고, 그 모듈이 tracer/meter는 이미 global로 설정하고 있을 겁니다. 이제 logger도 같은 레벨의 “전역 계약”으로 들어오니, 초기화 함수 시그니처/라이프사이클을 다시 정리해야 합니다.

이건 단순히 코드 몇 줄 바꾸는 문제가 아니라, 플랫폼 팀(또는 인프라 팀)이 제공하는 표준 부트스트랩의 책임이 늘어나는 변화입니다.

## trace/metric과의 correlation 설계: ‘필드가 있다’와 ‘검색이 된다’는 다르다

OTel 로그가 표준화를 이야기할 때 항상 따라오는 단어가 correlation인데, 실제 시스템에서는 correlation이 세 층으로 나뉩니다.

1) 데이터 모델 레벨: TraceId/SpanId 필드가 존재한다.
2) SDK/브리지 레벨: context에서 span context를 읽어 LogRecord에 채운다.
3) 백엔드/인덱싱 레벨: trace와 logs를 같은 키로 조인하거나 링크 UI를 제공한다.

이번 RC에서 우리가 직접 컨트롤 가능한 건 1)과 2)입니다.

### LogRecord의 TraceId/SpanId는 “표준 최상위 필드”다

OTel Logs Data Model은 TraceId/SpanId/TraceFlags를 최상위 필드로 정의합니다. SpanId가 있으면 TraceId도 있어야 한다는 권고까지 포함합니다.[^4]

이 점은 레거시 JSON 로그를 운영하던 팀에도 의미가 있습니다. “비-OTLP 포맷에서 trace context를 어떻게 기록할지”에 대한 호환 문서는 trace_id/span_id/trace_flags라는 필드명을 권장합니다.[^11]

즉 지금까지 팀마다 request_id, traceId, trace_id, x-trace-id로 제각각 찍던 것을, OTel 표준으로는 하나로 모을 수 있습니다.

### ctx 전달이 correlation의 단위가 된다: slog는 인자로, zap는 field로

- slog는 `InfoContext(ctx, ...)`처럼 ctx를 호출 인자로 받습니다.
- zap는 `otelzap`가 “context.Context 타입 field를 Emit context로 사용”합니다.[^6]

이 차이는 서비스 코드의 스타일에 직접 영향을 줍니다.

- slog 기반이면, handler/DAO까지 ctx를 내려보내는 게 자연스러워집니다.
- zap 기반이면, 로거를 ctx에 넣는 패턴(또는 logger.With로 ctx 바인딩)이 필요해집니다.

내 경험상 correlation 설계는 observability 기능이 아니라 코드베이스의 context 전파 품질을 테스트하는 리트머스입니다. ctx가 깨지는 구간(고루틴, 콜백, async 큐 처리)에서 로그와 trace가 끊어지면, 결국 사람들이 다시 request_id를 만들고, 표준화는 실패합니다.

### metrics와의 correlation은 ‘trace id’가 아니라 ‘리소스/속성’이 핵심

metrics는 기본적으로 trace id를 갖지 않습니다. 따라서 metric↔log correlation은 보통 이런 방식으로 설계합니다.

- 공통 Resource: service.name, deployment 환경, cluster 같은 origin 정보가 동일하게 들어간다.
- 공통 Attributes: endpoint, error.type, db.system 같은 key가 일관된다.
- trace 기반 링크: 특정 trace를 pivot으로 logs↔metrics를 찾아간다.

OTel 문서도 correlation의 축으로 “시간”, “trace context”, “Resource”를 명시합니다.[^12]

따라서 이번 RC에서 확인해야 하는 건 “로그가 trace_id를 포함하냐” 하나가 아니라, Resource/Attributes의 규칙이 trace/metric/log에서 동일하게 먹히는지입니다.

### Baggage를 어디까지 쓸 건지: correlation 키의 통제권

OTel spec overview는 trace propagation 외에 name/value 쌍을 전파하는 메커니즘으로 Baggage를 언급합니다.[^13]

Baggage는 correlation에 유용하지만, 동시에 비용 폭탄이 될 수 있는 지점입니다.

- 요청 헤더로 들어오니 신뢰 경계(trust boundary) 문제가 생깁니다.
- 사용자 입력이 baggage로 들어오면 PII/보안 리스크가 생깁니다.
- 무엇보다 cardinality가 폭발하기 쉽습니다.

RC 기간에는 “baggage에서 특정 키만 뽑아서 log attributes로 승격하는 규칙”까지 포함해 설계를 점검하는 게 좋습니다. 로그 표준화는 결국 키 정책입니다.

## RC 피드백 14일 창에서 해야 할 검증 체크리스트

공식 발표는 “RC에서 문제를 발견하면 지금 이슈를 올려 달라”고 말합니다.[^1]

이 기간에 의미 있는 피드백을 만들려면, 단순히 빌드가 되는지를 넘어서 “내 서비스의 제약 조건”을 정리해서 부딪혀야 합니다. 아래는 내가 실제로 돌려보는 체크리스트입니다.

### 1) 브리지/어댑터 검증

- (slog) `otelslog`로 dual-write가 가능한가 (stdout JSON + OTel)
- (zap) 기존 zap.Core 체인에 `otelzap` Core를 추가했을 때 레벨/필드가 기대대로 변환되는가[^6]
- (logrus) Hook 기반으로 context 없는 코드에서 correlation을 어떻게 할지 설계가 가능한가[^7]
- error 타입/stacktrace 같은 “관측에 중요한 필드”가 어떤 key로 어디에 들어가는가

### 2) LoggerProvider 전파와 글로벌 API 마이그레이션

- `go.opentelemetry.io/otel/log/global` 사용 지점을 얼마나 빨리 제거할 수 있나 (deprecated)[^14]
- 공통 telemetry 초기화 함수에서 LoggerProvider까지 관리할 준비가 됐나
- 전역 provider를 설정하지 않았을 때 no-op로 떨어지는 구간이 어디인지, 부팅 로그가 누락되지 않는지[^10]

### 3) correlation: trace_id/span_id가 실제로 채워지는지

- slog.InfoContext / zap context field 주입이 실제로 TraceId/SpanId를 채우는지
- trace 없는 background job 로그가 어떤 형태로 나가는지(빈 TraceId, 또는 누락)
- 비-OTLP(JSON)로도 trace_id/span_id를 표준 키로 남길지, 아니면 OTel logs로만 보낼지 결정[^11]

여기서 중요한 건 “빈 값이면 누락”인지 “0000…으로 채움”인지 같은 구현 디테일입니다. 이런 건 백엔드에서 필터링/인덱싱 전략에 영향을 줍니다.

### 4) 성능/비용: Enabled와 attribute limit, batch flush

Logs API는 `Enabled`를 성능 최적화로 제공하며, 로그 레코드 구성 비용이 큰 경우 먼저 Enabled를 확인하고 스킵할 수 있다고 설명합니다.[^3]

RC 기간에 확인할 포인트는 이런 것들입니다.

- 고QPS 핫패스에서 log record 구성 비용이 어느 정도인지
- attributes count/value length limit를 걸었을 때 드랍/트렁케이션이 어떻게 나타나는지 (SDK 옵션에 존재)[^15]
- BatchProcessor를 쓸 때 종료 시점에 Flush/Shutdown을 빼먹으면 손실이 나는지

특히 “종료 시 flush”는 실무에서 매번 터지는 문제입니다. 과거 이슈에서도 batch processor에 queued된 로그가 종료 전에 전송되지 않는 원인을 “provider shutdown을 안 해서”라고 짚습니다.[^16]

### 5) exporter/파이프라인: env 기반 구성과 프로토콜/엔드포인트

RC 범위 밖이라고 해도, 운영은 결국 exporter로 결정됩니다.

- `OTEL_LOGS_EXPORTER` (none/otlp/console) 같은 env 기반 구성 지원을 쓰면, 배포 환경에서 exporter 교체가 쉬워집니다.[^17]
- OTLP logs는 HTTP/protobuf 또는 gRPC가 가능하고, logs 전용 프로토콜 env도 따로 있습니다.[^17]

이 검증은 “잘 된다/안 된다”로 끝내면 의미가 없습니다.

- Collector 앞에서 backpressure가 오면 앱의 로깅 경로가 어떻게 버티는지
- OTLP endpoint 장애 시 드랍/재시도/메모리 증가가 어떤 형태로 나타나는지
- dual-write일 때 중복 비용(인덱싱/스토리지)이 얼마나 생기는지

## 실행 가능한 예제: slog + otelslog로 dual-write, trace와 함께 굴리기

아래 코드는 목표를 명확히 잡았습니다.

- HTTP 요청마다 trace span을 만들고
- slog 로그를 남기되
- stdout(JSON)과 OTel logs(stdoutlog exporter)로 동시에 보냅니다.

stdoutlog exporter는 “테스트/디버깅용이며 production용이 아니다”라고 문서에 명시합니다. 대신 형태를 확인하기에는 가장 빠릅니다.[^18]

### 의존성 버전

- Logs API/SDK: `v1.47.0-rc.1`[^1]
- stdoutlog exporter: `v0.22.0` (experimental)[^18]

### 프로젝트 생성

```bash
mkdir otel-go-logs-rc-demo
cd otel-go-logs-rc-demo

go mod init example.com/otel-go-logs-rc-demo

# Logs API/SDK RC
go get go.opentelemetry.io/otel@v1.47.0-rc.1
go get go.opentelemetry.io/otel/log@v1.47.0-rc.1
go get go.opentelemetry.io/otel/sdk/log@v1.47.0-rc.1

# Bridges
go get go.opentelemetry.io/contrib/bridges/otelslog@latest

# Exporter (experimental)
go get go.opentelemetry.io/otel/exporters/stdout/stdoutlog@v0.22.0

# Traces (콘솔 exporter는 안정)
go get go.opentelemetry.io/otel/sdk/trace@v1.47.0-rc.1
go get go.opentelemetry.io/otel/exporters/stdout/stdouttrace@latest
```

### telemetry/logging 초기화 (telemetry.go)

```go
package main

import (
	"context"
	"log/slog"
	"os"
	"time"

	"go.opentelemetry.io/contrib/bridges/otelslog"
	"go.opentelemetry.io/otel"
	oteltrace "go.opentelemetry.io/otel/trace"

	"go.opentelemetry.io/otel/exporters/stdout/stdoutlog"
	stdouttrace "go.opentelemetry.io/otel/exporters/stdout/stdouttrace"

	sdklog "go.opentelemetry.io/otel/sdk/log"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

type Telemetry struct {
	Tracer oteltrace.Tracer
	Shutdown func(context.Context) error
}

func initTelemetry() (*Telemetry, error) {
	ctx := context.Background()

	// --- Logs ---
	logExp, err := stdoutlog.New(stdoutlog.WithPrettyPrint())
	if err != nil {
		return nil, err
	}
	logProcessor := sdklog.NewBatchProcessor(logExp)
	logProvider := sdklog.NewLoggerProvider(
		sdklog.WithProcessor(logProcessor),
	)

	// RC 변경점: root otel 패키지로 global LoggerProvider가 올라옵니다.
	// (기존 go.opentelemetry.io/otel/log/global 은 deprecated)
	otel.SetLoggerProvider(logProvider)

	// --- Traces ---
	traceExp, err := stdouttrace.New(stdouttrace.WithPrettyPrint())
	if err != nil {
		return nil, err
	}
	traceProvider := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(traceExp),
	)
	otel.SetTracerProvider(traceProvider)

	// --- slog dual-write ---
	jsonHandler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})
	otelHandler := otelslog.NewHandler(
		"example.com/otel-go-logs-rc-demo",
		otelslog.WithLoggerProvider(logProvider),
		otelslog.WithSource(true),
	)
	tee := NewTeeHandler(jsonHandler, otelHandler)
	slog.SetDefault(slog.New(tee))

	shutdown := func(ctx context.Context) error {
		ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
		defer cancel()

		// 로그 flush/shutdown을 빼먹으면 BatchProcessor 큐에 남고 종료될 수 있습니다.
		// 실제로 과거 이슈에서도 원인이 이거였습니다.
		// https://github.com/open-telemetry/opentelemetry-go/issues/5590
		if err := logProvider.Shutdown(ctx); err != nil {
			return err
		}
		if err := traceProvider.Shutdown(ctx); err != nil {
			return err
		}
		return nil
	}

	return &Telemetry{
		Tracer: otel.Tracer("example.com/otel-go-logs-rc-demo"),
		Shutdown: shutdown,
	}, nil
}
```

### slog tee handler 구현 (tee_handler.go)

```go
package main

import (
	"context"
	"log/slog"
)

type TeeHandler struct {
	a slog.Handler
	b slog.Handler
}

func NewTeeHandler(a, b slog.Handler) *TeeHandler {
	return &TeeHandler{a: a, b: b}
}

func (h *TeeHandler) Enabled(ctx context.Context, level slog.Level) bool {
	return h.a.Enabled(ctx, level) || h.b.Enabled(ctx, level)
}

func (h *TeeHandler) Handle(ctx context.Context, r slog.Record) error {
	// 둘 중 하나가 실패해도 다른 쪽은 계속 흘리게 만들고 싶으면,
	// 여기서 에러 처리 정책을 분리해야 합니다.
	if err := h.a.Handle(ctx, r); err != nil {
		return err
	}
	if err := h.b.Handle(ctx, r); err != nil {
		return err
	}
	return nil
}

func (h *TeeHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return &TeeHandler{a: h.a.WithAttrs(attrs), b: h.b.WithAttrs(attrs)}
}

func (h *TeeHandler) WithGroup(name string) slog.Handler {
	return &TeeHandler{a: h.a.WithGroup(name), b: h.b.WithGroup(name)}
}
```

### HTTP 서버 (main.go)

```go
package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"time"
)

func main() {
	tel, err := initTelemetry()
	if err != nil {
		panic(err)
	}
	defer func() {
		if err := tel.Shutdown(context.Background()); err != nil {
			panic(err)
		}
	}()

	mux := http.NewServeMux()
	mux.HandleFunc("/pay", func(w http.ResponseWriter, r *http.Request) {
		ctx, span := tel.Tracer.Start(r.Context(), "POST /pay")
		defer span.End()

		// slog는 context를 인자로 받기 때문에 correlation 설계가 직관적입니다.
		slog.InfoContext(ctx, "payment accepted",
			slog.String("order_id", "o_123"),
			slog.Int("amount", 4200),
		)

		time.Sleep(30 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
		_, _ = fmt.Fprintln(w, "ok")
	})

	srv := &http.Server{Addr: ":8080", Handler: mux}
	slog.Info("listening", slog.String("addr", srv.Addr))

	if err := srv.ListenAndServe(); err != nil {
		panic(err)
	}
}
```

### 실행

```bash
go run .

# 다른 터미널에서
curl -sS localhost:8080/pay
```

### 예상 출력(형태)

stdout(JSONHandler) 쪽은 대략 이런 로그가 찍힙니다.

```json
{"time":"2026-09-06T...","level":"INFO","msg":"payment accepted","order_id":"o_123","amount":4200}
```

stdoutlog exporter(OTel logs) 쪽은 LogRecord를 JSON으로 내보내며, OTel 데이터 모델의 필드(Severity, Body, Attributes 등)가 구조화되어 나옵니다. exporter마다 출력 형태는 다르지만, 최소한 Severity/Body/Attributes/TraceId/SpanId 같은 축을 확인하는 게 목적입니다. OTel 로그 데이터 모델 자체는 어떤 필드가 있어야 하는지 정의돼 있습니다.[^4]

이 데모에서 RC 기간에 실제로 확인할 건 이겁니다.

- `/pay` 요청에서 찍힌 OTel log record에 TraceId/SpanId가 채워지는지
- `otelslog.WithSource(true)`를 켰을 때 code.*가 어떤 key로 추가되는지[^9]
- 로그 볼륨이 늘었을 때 BatchProcessor 큐/flush가 문제를 만들지 않는지

## 무엇을 피드백으로 올릴 것인가: “이상한데요”가 아니라 재현 가능한 실패

OTel 측이 RC에서 원하는 건 감상이 아니라 재현 가능한 문제입니다. 공식 글도 “RC 버전/Go 버전/최소 재현/기대 동작”을 포함해 이슈를 올려달라고 안내합니다.[^1]

내가 이 기간에 실제로 올릴만한 피드백은 보통 아래 부류입니다.

- 브리지에서 특정 타입(예: time.Duration, net.IP, custom error type)이 기대와 다르게 string으로 뭉개짐
- ctx를 주입했는데도 TraceId/SpanId가 비어 있거나 0으로 채워짐(특히 goroutine 경계)
- attribute limit가 걸린 상황에서 drop이 조용히 일어나고, 진단 포인트가 부족함
- BatchProcessor shutdown semantics가 애매해서 로그 손실이 쉬움(문서/예제 개선 포함)

이런 건 안정화 이후엔 “호환성 때문에” 고치기 더 어렵습니다.

## 참고 자료

- [OpenTelemetry Go Logs API and SDK reach release candidate status](https://opentelemetry.io/blog/2026/go-logs-api-sdk-rc/)
- [opentelemetry-go v1.47.0-rc.1 릴리스 노트](https://github.com/open-telemetry/opentelemetry-go/releases/tag/v1.47.0-rc.1)
- [OpenTelemetry Logs API 스펙](https://opentelemetry.io/docs/specs/otel/logs/api/)
- [OpenTelemetry Logs SDK 스펙](https://opentelemetry.io/docs/specs/otel/logs/sdk/)
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [Trace Context in non-OTLP Log Formats](https://opentelemetry.io/docs/specs/otel/compatibility/logging_trace_context/)
- [go.opentelemetry.io/otel/log/global 패키지 문서](https://pkg.go.dev/go.opentelemetry.io/otel/log/global)
- [go.opentelemetry.io/otel/log 패키지 문서](https://pkg.go.dev/go.opentelemetry.io/otel/log)
- [go.opentelemetry.io/otel/sdk/log 패키지 문서](https://pkg.go.dev/go.opentelemetry.io/otel/sdk/log)
- [stdoutlog exporter 문서](https://pkg.go.dev/go.opentelemetry.io/otel/exporters/stdout/stdoutlog)
- [Go exporter 공식 문서](https://opentelemetry.io/docs/languages/go/exporters/)
- [autoexport: OTEL_LOGS_EXPORTER 등 env 기반 exporter 구성](https://pkg.go.dev/go.opentelemetry.io/contrib/exporters/autoexport)
- [otelslog bridge 문서](https://pkg.go.dev/go.opentelemetry.io/contrib/bridges/otelslog)
- [otelzap bridge 문서](https://pkg.go.dev/go.opentelemetry.io/contrib/bridges/otelzap)
- [otellogrus bridge 문서](https://pkg.go.dev/go.opentelemetry.io/contrib/bridges/otellogrus)
- [batch processor 종료로 인한 로그 미전송 사례](https://github.com/open-telemetry/opentelemetry-go/issues/5590)
- [빅테크 AI “발표”보다 더 무서운 건 API/정책의 조용한 변경이다](https://daewooki.github.io/posts/2026-3-ai-api-1/)

[^1]: <https://opentelemetry.io/blog/2026/go-logs-api-sdk-rc/>
[^2]: <https://opentelemetry.io/docs/languages/go/exporters/>
[^3]: <https://opentelemetry.io/docs/specs/otel/logs/api/>
[^4]: <https://opentelemetry.io/docs/specs/otel/logs/data-model/>
[^5]: <https://pkg.go.dev/go.opentelemetry.io/contrib/bridges/otelslog>
[^6]: <https://pkg.go.dev/go.opentelemetry.io/contrib/bridges/otelzap%40v0.19.0>
[^7]: <https://pkg.go.dev/go.opentelemetry.io/contrib/bridges/otellogrus>
[^8]: <https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/bridges/otelslog/handler.go>
[^9]: <https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md>
[^10]: <https://pkg.go.dev/go.opentelemetry.io/otel/log/global>
[^11]: <https://opentelemetry.io/docs/specs/otel/compatibility/logging_trace_context/>
[^12]: <https://opentelemetry.io/docs/specs/otel/logs/>
[^13]: <https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/overview.md>
[^14]: <https://github.com/open-telemetry/opentelemetry-go/releases/tag/v1.47.0-rc.1>
[^15]: <https://pkg.go.dev/go.opentelemetry.io/otel/sdk/log>
[^16]: <https://github.com/open-telemetry/opentelemetry-go/issues/5590>
[^17]: <https://go.opentelemetry.io/contrib/exporters/autoexport>
[^18]: <https://pkg.go.dev/go.opentelemetry.io/otel/exporters/stdout/stdoutlog>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
