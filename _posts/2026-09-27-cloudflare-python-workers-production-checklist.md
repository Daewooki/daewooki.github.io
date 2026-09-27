---
title: "Cloudflare Python Workers를 실서비스로 운영하기 위한 체크리스트"
description: "Python Workers GA 이후에는 데모를 넘어서 의존성·콜드스타트·관측성·데이터 분리 전략을 운영 관점에서 검증해야 합니다."
date: 2026-09-27 13:52:37 +0900
categories: ["Backend", "Cloudflare Workers"]
tags: ["cloudflare-workers", "python", "serverless", "packaging", "observability", "durable-objects"]
render_with_liquid: false
---

Cloudflare가 2026-09-21에 Python Workers GA를 발표하면서, Python이 Workers에서 “지원되는 언어”가 아니라 “지원되는 제품”의 지위로 올라왔습니다[^1]. 다만 GA는 결승점이 아니라 출발점에 가깝습니다. 이제부터는 기능 데모가 아니라 비용·성능·운영(릴리스/롤백)까지 포함해, Python을 Workers에 올려도 된다는 근거를 제품 수준으로 쌓아야 합니다.

Python Workers는 CPython을 그대로 호스팅하는 형태가 아닙니다. Workers의 V8 isolate 안에서 Pyodide(= CPython을 WebAssembly로 포팅한 런타임)로 Python을 실행합니다[^2][^1]. 이 사실 하나로 운영 체크리스트의 성격이 달라집니다. wheels/네이티브 모듈 제약, 런타임 경계(파일시스템/스레드/소켓), 관측성 파이프라인, 그리고 Worker와 데이터스토어의 분리 방식이 모두 “WASM+edge compute”에 맞게 재정의되어야 합니다.

아래는 내 기준으로, Python Workers를 운영 가능한 서버리스로 만들기 위해 실제로 확인해야 하는 항목들입니다.

## GA가 바꾼 것과 바꾸지 못한 것

GA 발표에서 제일 중요한 변화는 “언어 지원”이 아니라 “플랫폼 바인딩이 Python 우선으로 재구성됐다”는 점입니다. GA 이전에는 Cloudflare 바인딩(KV/Queues 등)을 Python에서 쓰려면 JS 경계에서 타입 변환을 직접 해야 했고, 그게 흔한 오류 지점이었다고 합니다. GA 이후에는 이 변환을 런타임과 Python SDK 내부로 캡슐화해서, Python에서 Python스럽게 바인딩을 호출하게 만들었다는 게 발표의 핵심 중 하나입니다[^1].

반대로 GA가 곧바로 해결해주지 않는 현실도 분명합니다.

* 실행은 Pyodide 기반이므로, 네이티브 확장(C/C++/Rust)을 가진 패키지는 WebAssembly로 크로스 컴파일된 형태로만 동작합니다[^1].
* Python 표준 라이브러리라 해도 전부 동일하게 동작하지 않습니다. 일부 모듈은 제외되거나, WASM VM 한계로 동작하지 않습니다. 특히 `threading`, `multiprocessing`는 import는 가능하지만 기능하지 않는다고 명시되어 있습니다[^2].
* 파일은 쓸 수 있지만 isolate가 파괴되면 사라지는 in-memory filesystem입니다. 즉 로컬 디스크를 가정하는 코드/라이브러리는 운영에서 바로 깨집니다[^2].

GA 이후의 실전 전략은 “Workers의 장점(배포/확장/관측/롤백)을 가져오되, 런타임 경계는 이식 비용으로 받아들이는 것”에 가깝습니다.

## 패키징/의존성: wheels와 네이티브 모듈을 제품 리스크로 취급하기

Python Workers에서 의존성 리스크는 기능 리스크가 아니라 공급망 리스크에 가깝습니다. 운영 중 장애는 결국 “어제까지 되던 패키지가 오늘 배포에서 깨졌다” 같은 형태로 터집니다. 그래서 패키징 체크리스트는 CI에서 자동화될수록 가치가 큽니다.

### 지원되는 패키지의 범주를 먼저 정의하기

Cloudflare 문서 기준으로, Python Workers가 지원하는 건 크게 3가지 범주입니다.

1) pure Python 패키지
2) PyPI에 PyEmscripten wheels가 올라와 있는 패키지
3) Pyodide에 포함된 패키지

이를 공식 문서가 그대로 못박고 있습니다[^3]. 그리고 WebAssembly 환경에서의 패키지 지원은 아직 초기 단계라서, PyEmscripten wheels가 없는 패키지는 동작하지 않을 수 있다고도 명시합니다[^3].

여기서 “PyEmscripten wheels가 있어야 한다”는 제약은 앞으로 장기전이 됩니다. Cloudflare는 GA 발표에서, 네이티브 확장 패키지들이 WebAssembly로 크로스 컴파일되어야 하고, 이를 위해 PyEmscripten 표준화를 추진했다고 설명합니다[^1]. 실제로 PEP 783은 Accepted 상태이며, wheel platform tag 규칙까지 정의합니다[^4].

패키지 유지보수 관점에서는, 내가 쓰려는 의존성이 다음 중 어디에 속하는지 분류하는 순간부터 전략이 갈립니다.

* pure Python: 비교적 안전. 다만 런타임/stdlib 차이로 런타임 에러는 날 수 있습니다.
* PyEmscripten wheel: 빌드가 존재한다는 의미이므로 가능성이 생깁니다. 하지만 wheel이 최신 버전까지 따라오는지, 보안 패치가 따라오는지까지 봐야 합니다.
* Pyodide 내장: 동작 가능성은 높지만, Workers의 compatibility_date가 Pyodide 버전을 어떤 방식으로 고정하는지까지 이어서 봐야 합니다.

### “네이티브 모듈=금지”가 아니라 “네이티브 모듈=릴리스 게이트”

내 경우는 네이티브 모듈을 무조건 피하기보다, “네이티브 모듈이 들어오는 순간부터 배포 파이프라인이 달라져야 한다”로 정리합니다.

Cloudflare는 Python Workers가 WASM sandbox에서 동작하기 때문에 C/C++/Rust 확장을 가진 패키지는 WASM으로 크로스 컴파일되어야 한다고 명시합니다[^1]. 즉, `pip install`이 성공한다고 해서 안전한 게 아니라, **배포 번들에 들어갈 때까지** 확인해야 합니다.

운영 체크리스트는 이렇게 가져갑니다.

* 의존성 변경 PR마다 “Workers 번들 생성까지”를 CI에서 실행합니다.
  * 문서가 권장하는 흐름은 `pywrangler`를 쓰는 것입니다. `pywrangler`는 Python Workers 패키징을 위해 wrangler를 감싸고, 배포 시 의존성을 Worker 번들로 묶어준다고 설명합니다[^3].
  * `pywrangler`는 wrangler의 모든 커맨드를 지원한다고도 명시되어 있어서, CI에서 배포/버전 관리 커맨드까지 한 경로로 통일할 여지가 있습니다[^3].

* “의존성은 되도록 lockfile로 고정”을 기본으로 둡니다.
  * Cloudflare 문서 예시는 `uv` 기반 워크플로우를 전제로 합니다(예: `uv run pywrangler dev/deploy`)[^3]. `uv.lock`를 함께 커밋하는 구조가 자연스럽습니다.

* 번들 크기(Worker size 64 MiB)도 릴리스 게이트로 둡니다.
  * Workers limits 문서에 Worker size가 64 MiB라고 명시되어 있습니다[^5]. Python 의존성은 생각보다 쉽게 번들 크기를 터뜨립니다.

### python_modules 폴더와 “불필요한 파일” 제거

Python Workers는 기본적으로 `python_modules` 디렉터리 아래 파일/폴더를 번들에 포함시키며, 이 디렉터리는 `pywrangler`가 패키지를 복사해 넣는 위치라고 Wrangler 문서가 설명합니다[^6].

실무에서 제일 흔한 실패는 기능이 아니라 크기입니다. 테스트/타입힌트/캐시 파일까지 같이 말려 들어가면서 64 MiB에 접근합니다.

Wrangler는 `python_modules.exclude`로 번들에서 제외할 수 있는 옵션을 제공합니다[^6]. 최소한 아래는 기본으로 깔고 가는 편이 낫습니다.

* `**/*.pyc`
* `**/__pycache__`

이건 성능 최적화라기보다 “운영 가능하게 만드는 위생”에 가깝습니다.

### 표준 라이브러리 제약이 의존성 선택을 바꾼다

의존성 문제가 wheels만이 아닙니다. Python stdlib도 동일하지 않습니다.

* 제외된 모듈 목록이 있고(`curses`, `fcntl`, `syslog`, `venv` 등)[^2]
* `threading`, `multiprocessing`는 기능하지 않는다고 명시합니다[^2]

즉, pure Python 패키지라도 내부에서 `threading`을 “성능 개선용으로만” 슬쩍 쓰는 순간, 런타임에서 조용히 비정상 동작으로 빠질 수 있습니다. Workers에서 Python을 쓰는 이유가 대개 I/O 중심의 API이기 때문에, 나는 스레드 기반 병렬화에 기대는 라이브러리는 처음부터 후보에서 제외합니다.

## 콜드스타트/런타임 경계: “콜드스타트가 없다”는 말을 믿지 않는 법

Cloudflare Workers는 전통적 서버리스(Lambda)와 달리 “isolates 기반이라 콜드스타트가 작다”는 이미지가 강합니다. Python Workers는 여기에 한 겹이 더 있습니다. Pyodide 초기화, 패키지 로딩, 그리고 Python import 비용이 얹힙니다.

### Python Workers의 콜드스타트 최적화 메커니즘을 알아야 한다

Cloudflare 문서는 Python Workers의 배포 라이프사이클에서, 배포 시점에 entrypoint 모듈과 top-level import를 실행하고 WebAssembly linear memory snapshot을 떠서 네트워크에 함께 배포한다고 설명합니다. 즉 비싼 초기화 작업을 런타임이 아니라 deploy time에 수행한다는 얘기입니다[^7].

이 최적화는 운영 전략을 이렇게 바꿉니다.

* top-level import 비용은 “첫 요청”으로 미뤄지지 않고 “배포 작업”으로 이동할 수 있습니다.
* 대신 배포 시간이 길어질 수 있고, 배포 실패가 곧 장애가 됩니다. CI에서 배포 번들 생성 단계가 더 중요해집니다.

### Worker startup time 1초는 “대부분의 Python이 가볍다”는 가정이 아니다

Workers limits 문서에 Worker startup time이 1초로 표기되어 있습니다[^5]. 이 수치는 무시하면 안 됩니다. 특히 Python은 import 그래프가 커지는 순간, 해석기 초기화+모듈 로딩으로 예산을 태우기 쉽습니다.

GA 이후에도, 내가 보는 런타임 경계는 3개입니다.

1) CPU time
2) 메모리(128MB)
3) “요청은 오래 걸려도 되지만, CPU는 오래 쓰면 죽는다”는 모델

CPU time은 Workers가 아주 명확히 정의합니다. 네트워크 대기 시간(fetch, KV read, DB query 등)은 CPU time에 포함되지 않고, 실제로 CPU가 코드를 실행하는 시간이 비용/리밋에 걸립니다[^5].

Python Workers는 해석 실행이므로, 같은 로직이라도 CPU time이 커지기 쉽습니다. 그 결과, 다음 종류의 코드는 조심해야 합니다.

* 큰 JSON 파싱
* 큰 정규식
* 복잡한 템플릿 렌더링
* 암호학적 반복 연산

여기서 중요한 건 최적화를 “빠르게”가 아니라 “CPU time 예산 안에”로 정의하는 것입니다.

### 메모리 128MB에 WebAssembly 할당이 포함된다

Workers는 isolate당 메모리가 128MB이고, 이 안에 JavaScript heap 뿐 아니라 WebAssembly allocations도 포함된다고 명시합니다[^5]. Python Workers는 Pyodide 자체가 WebAssembly 쪽 메모리를 적극적으로 사용합니다. 즉, Python 메모리 사용량을 “그냥 Python 프로세스 메모리”로 추정하면 계속 틀립니다.

이 조건에서 흔히 깨지는 패턴은 2가지입니다.

* 요청/응답 바디를 통째로 `text()`/`arrayBuffer()`로 버퍼링
* 큰 객체를 전역에 캐시했다가 isolate 재사용 기대

전자는 즉시 OOM으로 터지고, 후자는 트래픽 패턴에 따라 “가끔 빠르고 가끔 느린” 형태로 운영 난이도를 올립니다.

### 파일시스템은 임시다: 캐시와 스풀을 로컬에 쓰면 운영이 불가능해진다

Python Workers는 표준 Python file I/O로 파일을 읽고 쓸 수 있지만, isolate가 파괴되면 데이터가 사라지고 isolate 간 공유도 안 된다고 명시합니다[^2].

운영에서 의미 있는 디스크는 없다고 보는 편이 맞습니다. 임시 파일이 필요하면 “한 요청 안에서만 의미 있는 작업(예: 포맷 변환)”에만 쓰고, 지속성은 KV/R2/Durable Objects로 빼야 합니다.

## 관측성·에러 처리: 로그/트레이스는 “나중에 붙이는 기능”이 아니다

Python Workers가 GA가 되었다는 건, 이제 Python도 Workers의 운영 모델(버전/배포/관측/롤백)을 그대로 적용할 수 있다는 뜻입니다. 이 중에서도 관측성은 제일 먼저 굳혀야 합니다. 이유는 단순합니다. 패키지 제약이나 런타임 경계 문제는 “재현이 어려운 형태”로 나타나기 때문입니다.

### Workers Logs: 운영 기본값으로 켜고, 샘플링을 설계한다

Workers Logs는 invocation logs, custom logs, errors, uncaught exceptions까지 수집해 대시보드에서 쿼리할 수 있다고 설명합니다[^8]. 또한 third-party로 보내려면 OpenTelemetry export를 추천한다고도 명시합니다[^8].

Wrangler 설정으로 `observability.enabled = true`를 켜고, `head_sampling_rate`로 샘플링 비율을 조정합니다[^8]. 로그는 비용이 아니라 운영 복잡도를 폭발시키는 자원이라서, 나는 보통 아래 규칙으로 시작합니다.

* staging: 1.0
* production: 0.01 ~ 0.1에서 시작(트래픽에 따라)
* 에러/리트라이 경로는 별도 로깅(샘플링과 별개로 남겨야 할 핵심 이벤트)

Wrangler 최소 버전 요구사항도 체크리스트에 넣어야 합니다. Workers Logs 문서는 최소 Wrangler 3.78.6을 요구합니다[^8].

### Traces와 OTel export: “파이프라인”을 먼저 만들고, 샘플링을 나중에 고친다

Workers observability 문서는 Workers가 fetch, KV/R2/Durable Objects 같은 바인딩, handler invocation에 대해 자동 instrumentation을 제공하고, OTel-compliant traces/logs export를 지원한다고 설명합니다[^9].

Traces 문서는 `observability.traces.enabled = true`로 켜고 `head_sampling_rate`를 설정할 수 있다고 합니다[^10].

OTel export는 “지금은 무료” 같은 문장만 믿고 들어가면 운영에서 피봇 비용이 커집니다. Exporting OpenTelemetry Data 문서는 2026-10-01부터 트레이싱이 Workers Paid usage로 과금된다고 명시합니다. Workers Paid 기준으로 월 1,000만 이벤트 포함, 초과 시 million당 $0.05라고 표를 제공합니다[^11]. 오늘이 2026-09-27(KST)이므로, 가격 정책이 며칠 뒤에 바뀌는 셈입니다.

여기서 운영 체크리스트는 명확합니다.

* trace/log event volume 예측치를 만든다.
* sampling rate를 “장애 분석 가능”과 “비용”의 균형점으로 잡는다.
* `persist=false`를 쓸지(Cloudflare 대시보드 저장 비용을 줄일지) 결정한다. export 문서는 `persist` 설정을 통해 export만 하고 대시보드 저장을 끌 수 있다고 설명합니다[^11].

내 블로그에서 LLM 관측성을 OpenTelemetry 기준으로 정리한 글은 Workers의 OTel export 설계와 결이 맞습니다. 다만 내용을 반복할 필요는 없어서, 여기서는 연결만 걸어 둡니다.

* [LLM 호출 내부까지 끝까지 보이게: OpenTelemetry GenAI Tracing으로 LLM Observability 구축하기](https://daewooki.github.io/posts/llm-2026-7-opentelemetry-genai-tracing-l-2/)
* [OpenTelemetry Go Logs RC로 시작하는 로그 표준화](https://daewooki.github.io/posts/otel-go-logs-rc-adoption/)

### Python에서의 에러 처리: uncaught exception을 운영 이벤트로 정의하기

Workers Logs가 uncaught exceptions를 포함한다고 명시한 이상[^8], Python Workers에서 uncaught exception이 발생하는 경로를 “버그”가 아니라 “운영 이벤트”로 보는 편이 좋습니다.

내 기준 체크리스트는 다음입니다.

* 요청 핸들러 최상단에 예외를 모아 HTTP status를 일관되게 맵핑한다.
* 클라이언트 오류(400/401/403)와 서버 오류(500)를 분리한다.
* 서버 오류는 반드시 로그에 stack trace와 함께 남긴다.
* 재시도 가능한 오류(일시적 외부 API 장애, 데이터스토어 타임아웃)는 별도 error code로 식별한다.

이건 프레임워크 유무와 무관하게, 운영에서의 “분석 가능성”을 만드는 작업입니다.

## Worker-데이터스토어 분리 전략: 데이터의 일관성 모델을 설계로 고정하기

Python Workers를 운영 가능한 제품으로 만들려면, 결국 상태를 어디에 둘지 결정해야 합니다. Workers 자체는 stateless에 가깝고, isolate 메모리는 캐시로만 취급해야 합니다.

여기서 중요한 건 단순히 “KV 쓰고 D1 쓰자”가 아니라, 각 저장소의 일관성/지연/비용 모델을 코드 구조에 각인시키는 것입니다.

### KV: 결국 consistent cache로 써야 한다

Workers KV는 eventually consistent라고 명시합니다. 변경은 작성된 위치에서는 보통 즉시 보이지만 보장되지 않고, 다른 location에서는 캐시 타임아웃 때문에 60초 이상 걸릴 수 있다고도 구체적으로 씁니다[^12].

문서가 친절하게도, write-after-write consistency가 필요하면 특정 키에 대한 writes를 Durable Object를 통해 직렬화한 뒤 KV를 읽는 패턴을 제안합니다[^12]. 이게 운영 관점에서 아주 중요합니다.

* KV는 “DB”가 아니라 “글로벌 캐시”다.
* KV 쓰기 경합/원자성/트랜잭션을 기대하면 언젠가 깨진다.

운영 체크리스트 관점에서는 KV의 역할을 한 문장으로 못 박는 게 좋습니다.

* 기능 플래그, 설정, 리드헤비 캐시, 세션처럼 약한 일관성으로 버틸 수 있는 것

### Durable Objects: 강한 일관성이 필요한 경계에만 둔다

Durable Objects는 stateful 애플리케이션을 위한 빌딩 블록이라고 하고[^13], SQLite-backed storage가 GA로 올라왔고 `sql.exec` 같은 Storage API도 beta에서 GA로 이동했다고 명시합니다[^13].

SQLite-backed Durable Objects는 Cloudflare가 “새로 만들 거면 SQLite backend를 쓰라”고 권장합니다[^14]. 이건 실무에서 그대로 따르는 편이 낫습니다. 이유는 간단합니다.

* SQL API를 쓸 수 있고
* 트랜잭션/인덱스/테이블 모델링이 가능하며
* Point In Time Recovery 같은 운영 기능이 붙기 때문입니다[^14].

다만 Durable Objects는 비용 모델을 이해하고 써야 합니다. pricing 문서에서 Durable Objects는 active 상태거나, 메모리에 있지만 hibernate되지 못하는 idle 상태에서 compute duration(wall-clock time)으로 과금된다고 명시합니다[^15]. 즉 “일관성”을 얻는 대신 “항상 켜져 있는 상태”를 만들면 비용이 생깁니다.

내 기준으로 Durable Objects는 다음처럼 씁니다.

* idempotency(중복 처리 방지)
* per-user/per-tenant state
* 강한 일관성이 필요한 카운터/락
* 외부 데이터스토어로 가기 전에 edge에서 트래픽을 정리하는 게이트

### D1: 쿼리 비용이 Workers CPU/메모리 예산에 들어온다

D1 limits 문서가 아주 중요한 문장을 씁니다. D1에서의 query execution과 result serialization은 Workers platform의 CPU/memory limits 안에서 돌아간다고 명시합니다[^16].

이 말은 곧, Python Workers에서 D1을 쓰면 “Python 해석 비용 + D1 결과 직렬화 비용”이 같은 CPU 예산에서 경쟁한다는 뜻입니다.

그래서 나는 D1을 “핫패스의 primary datastore”로 두기 전에, 아래를 먼저 검증합니다.

* 결과가 작은가(직렬화 비용)
* 인덱스로 충분히 커버되는가
* 읽기 트래픽을 KV로 흡수할 수 있는가

### Hyperdrive: 연결 풀링만이 아니라 캐시의 일관성 모델까지 같이 온다

Hyperdrive는 Workers에서 기존 DB(PostgreSQL/MySQL 등)를 빠르게 붙이기 위한 제품인데, 실제 운영에서 중요한 포인트는 “연결 비용을 누가 부담하느냐”입니다.

Hyperdrive 문서는 connection setup을 edge에서 수행하고, origin DB 근처에 connection pool을 유지하며, 쿼리 캐시까지 제공한다고 설명합니다[^17]. 그리고 더 중요한 경고가 하나 있습니다. Hyperdrive는 write가 발생해도 cached read query 결과를 자동으로 invalidate하지 않는다고 명시합니다. read-after-write consistency가 필요하면 캐시 비활성 Hyperdrive 구성을 별도로 쓰라고 합니다[^17].

즉, Hyperdrive를 도입하는 순간 “DB 연결 최적화”만이 아니라 “캐시 일관성 모델”도 시스템 설계에 들어옵니다.

## 릴리스/롤백: GA 이후에야 진짜로 중요해지는 운영 기능

언어 지원이 GA가 되면, 배포 전략이 곧 제품 안정성입니다. Workers는 이 부분이 오히려 강점입니다.

### Versions & deployments를 분리해서 생각하기

Workers는 코드/설정이 바뀔 때마다 version을 만들고, deployment가 어떤 version이 트래픽을 받는지 결정한다고 설명합니다[^18]. 그리고 storage 리소스(KV/R2/Durable Objects/D1)의 상태 변화는 versions에 추적되지 않는다고 명시합니다[^18].

이 문장은 운영 체크리스트에서 아주 무겁습니다.

* 코드 롤백이 데이터 롤백이 아니다.
* 마이그레이션/스키마 변경이 들어가면 롤백 절차가 별도로 필요하다.

### Gradual deployments: Python 런타임 변화의 리스크를 “트래픽 비율”로 분산

Gradual deployments는 두 버전에 트래픽을 나눠서 점진적으로 올리는 기능입니다[^19]. Python Workers처럼 런타임 경계가 큰 환경에서는 특히 유효합니다.

다만 문서가 경고하듯, 두 버전이 동시에 트래픽을 받으면 version skew로 인해 클라이언트/서비스가 서로 다른 버전과 상호작용하면서 불일치가 발생할 수 있습니다[^19].

그래서 나는 점진 배포를 “무조건 좋다”로 보지 않고, 아래 조건이 갖춰질 때만 켭니다.

* 요청이 버전 간 섞여도 안전한 API 계약(가능하면 idempotent)
* 데이터 스키마가 backwards compatible
* 관측성(로그/에러율/트레이스)로 버전별 차이를 볼 수 있음

### Rollback: 가능하다고 해서 언제나 가능한 게 아니다

Workers는 Wrangler나 대시보드로 롤백할 수 있고, 롤백은 즉시 새 deployment를 만들어 active로 만든다고 설명합니다[^20].

하지만 롤백이 막히는 조건도 명시합니다.

* 바인딩된 리소스가 삭제/변경되었거나
* Durable Object class lifecycle change가 일어났거나
* 과거 버전이 참조하던 KV/R2/queue가 더 이상 존재하지 않는 경우

이 경우 롤백이 허용되지 않는다고 합니다[^20].

즉 운영 체크리스트는 “롤백 버튼이 있다”가 아니라 “롤백이 가능한 상태를 유지한다”입니다.

## 실전 예제: Python Workers로 idempotent webhook 엔드포인트 운영하기

패키지 의존성을 최소화하고(표준 라이브러리 + `workers` SDK), Durable Objects(SQLite)로 강한 일관성을 확보하면서, KV를 read-mostly cache로 쓰는 형태입니다. 의도는 명확합니다.

* Worker는 얇게: 인증/검증/라우팅
* Durable Object는 상태를 담당: 중복 방지 + 감사 로그
* KV는 캐시/조회 최적화: eventually consistent를 허용하는 영역에만 사용

구조는 아래처럼 둡니다.

```
webhook-worker/
  pyproject.toml
  uv.lock
  wrangler.toml
  src/
    main.py
    idempotency_do.py
```

### pyproject.toml

Cloudflare 문서의 권장 방식대로 `pywrangler`를 `uv run`으로 실행하는 구성을 따릅니다[^3].

```toml
[project]
name = "webhook-worker"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = []

[dependency-groups]
dev = [
  "workers-py",
  "workers-runtime-sdk",
]
```

의존성을 비워 둔 이유는 단순합니다. 운영 체크리스트를 설명하는 글에서, 네이티브 모듈 문제가 섞이면 본질이 흐려집니다. 실제 서비스에서는 여기서부터 의존성 분류 작업(pure/PyEmscripten/Pyodide)을 시작하면 됩니다.

### wrangler.toml

Python Workers는 `python_workers` compatibility flag가 필요하다고 문서가 못박고 있습니다[^21].

또한 Worker의 관측성 설정은 처음부터 켭니다[^8][^10].

```toml
name = "webhook-worker"
main = "src/main.py"
compatibility_date = "2026-09-27"
compatibility_flags = ["python_workers"]

[vars]
# 운영에서는 secret으로 두는 편이 낫습니다.
# 여기서는 예제를 단순화합니다.
WEBHOOK_HMAC_KEY = "change-me"

[observability]
enabled = true
head_sampling_rate = 0.1

[observability.traces]
enabled = true
head_sampling_rate = 0.05

[[kv_namespaces]]
binding = "CACHE"
id = "<KV_NAMESPACE_ID>"

[durable_objects]
bindings = [
  { name = "IDEMPOTENCY", class_name = "IdempotencyDO" }
]

[[migrations]]
tag = "v1"
new_sqlite_classes = ["IdempotencyDO"]
```

Durable Objects를 SQLite backend로 쓰기 위해 `new_sqlite_classes` 마이그레이션을 설정하는 패턴은 Cloudflare가 반복적으로 안내하는 방식입니다[^14].

### Durable Object: IdempotencyDO

SQLite-backed Durable Object storage의 `sql.exec(query, ...bindings)`는 `?` placeholder 바인딩을 지원합니다[^14]. 이걸 이용해 중복 이벤트 처리를 강한 일관성으로 막습니다.

```python
# src/idempotency_do.py

import time
from workers import DurableObject

class IdempotencyDO(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.sql = ctx.storage.sql

        # 테이블 생성은 최초 인스턴스 구성 시 실행됩니다.
        # Durable Objects의 SQL API는 동기적으로 실행됩니다.
        self.sql.exec(
            """
            CREATE TABLE IF NOT EXISTS seen_events (
              event_id TEXT PRIMARY KEY,
              received_at INTEGER NOT NULL
            );
            """
        )

    async def mark_once(self, event_id: str) -> bool:
        now = int(time.time())

        # 이미 존재하면 무시
        self.sql.exec(
            "INSERT OR IGNORE INTO seen_events(event_id, received_at) VALUES(?, ?)",
            event_id,
            now,
        )

        # SQLite changes()로 방금 INSERT가 적용됐는지 확인
        row = self.sql.exec("SELECT changes() AS c").one()
        return row.c == 1
```

이 Durable Object는 저장소가 강한 일관성을 보장하는 단일 경계가 됩니다. KV의 eventual consistency 문제를 여기에 끌고 오지 않습니다.

### Worker 엔드포인트: webhook 수신 + idempotency + KV 캐시

Python Workers에서 `request.json()`이 Python dict를 돌려준다는 예제가 공식 문서에 있습니다[^22]. 여기서는 HMAC 검증을 위해 `request.text()`로 원문을 읽은 뒤 파싱합니다.

```python
# src/main.py

import hashlib
import hmac
import json
from urllib.parse import urlparse

from workers import WorkerEntrypoint, Response

def _hmac_hex(key: str, body_text: str) -> str:
    mac = hmac.new(key.encode("utf-8"), body_text.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest()

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        url = urlparse(request.url)

        if url.path == "/healthz":
            return Response.json({"ok": True})

        if url.path != "/webhook" or request.method != "POST":
            return Response("Not Found", status=404)

        body_text = await request.text()

        signature = request.headers.get("x-webhook-signature")
        expected = _hmac_hex(self.env.WEBHOOK_HMAC_KEY, body_text)

        if signature is None or not hmac.compare_digest(signature, expected):
            return Response.json({"error": "invalid signature"}, status=401)

        try:
            payload = json.loads(body_text)
            event_id = payload["id"]
        except Exception:
            return Response.json({"error": "invalid json"}, status=400)

        # 강한 일관성이 필요한 중복 방지는 Durable Object에서 처리
        stub = self.env.IDEMPOTENCY.getByName(event_id)
        first_time = await stub.mark_once(event_id)

        if not first_time:
            # 멱등 응답: 이미 처리된 이벤트
            return Response.json({"status": "duplicate", "id": event_id}, status=200)

        # eventual consistency가 허용되는 영역만 KV로
        await self.env.CACHE.put(
            f"seen:{event_id}",
            "1",
            expirationTtl=3600,
        )

        return Response.json({"status": "accepted", "id": event_id}, status=202)
```

이 코드가 보여주는 운영 포인트는 다음입니다.

* request 파싱/검증은 Worker에서 한다.
* 중복 방지 같은 강한 일관성 경계는 Durable Objects로 보낸다.
* KV는 “빠른 조회/캐시”로만 쓴다.

### 로컬 실행과 배포

패키지 문서에서 제시하는 방식은 아래입니다.

* 로컬 실행: `uv run pywrangler dev`
* 배포: `uv run pywrangler deploy`

이는 Cloudflare 공식 문서에 그대로 나옵니다[^3].

운영에서는 여기에 “점진 배포/롤백”까지 같은 흐름으로 넣습니다.

* Gradual deployments로 트래픽 1% → 10% → 100%[^19]
* 문제가 있으면 롤백[^20]

## 도입 판단 기준: Python을 Workers에 올릴 때의 합리적인 선

정리하면, Python Workers GA 이후의 도입 기준은 언어 선호가 아니라 “제약을 운영비로 전환할 수 있느냐”입니다.

나는 아래 조건이 맞으면 Python Workers를 제품 선택지로 올립니다.

* 핫패스가 I/O 중심이고, CPU가 큰 연산이 아니며(Workers CPU time 모델과 맞음)[^5]
* 의존성 그래프를 통제할 수 있고, 네이티브 모듈이 들어오면 PyEmscripten wheel 유무로 릴리스 게이트를 세울 수 있으며[^3][^4]
* 강한 일관성이 필요한 상태는 Durable Objects로 격리하고, KV의 eventual consistency는 설계로 받아들일 수 있고[^12]
* Workers Observability를 기준으로 로그/트레이스를 설계하고, 2026-10-01 이후의 이벤트 과금까지 포함해 샘플링 전략을 정할 수 있을 때[^11]

반대로 다음 조건이면 Python Workers를 “운영 가능한 서버리스”로 만들기 전에 다른 선택지가 먼저입니다.

* 특정 네이티브 의존성을 대체할 수 없고, PyEmscripten wheels 생태계에 스스로 투자할 여력이 없을 때
* 스레드/프로세스 병렬화가 제품의 성능 요구사항에 직접 들어갈 때(`threading`이 동작하지 않는다는 제약을 피하기 어렵습니다)[^2]
* 대형 payload를 자주 버퍼링해야 하는 워크로드(128MB 메모리 한계 + WASM 메모리 포함)[^5]

GA는 출발점입니다. 출발선에서 필요한 건 “작동한다”가 아니라 “계속 작동하게 만들 수 있다”는 체크리스트이고, 이 체크리스트를 CI/배포/관측/데이터 모델에 박아 넣는 순간부터 Python Workers는 운영 가능한 제품이 됩니다.

## 참고 자료

- [Python Workers GA 발표](https://blog.cloudflare.com/python-workers-ga/)
- [How Python Workers Work](https://developers.cloudflare.com/workers/languages/python/how-python-workers-work/)
- [Python stdlib (Python Workers)](https://developers.cloudflare.com/workers/languages/python/stdlib/)
- [Python packages supported in Cloudflare Workers](https://developers.cloudflare.com/workers/languages/python/packages/)
- [Write Cloudflare Workers in Python](https://developers.cloudflare.com/workers/languages/python/)
- [Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
- [Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
- [Traces (Workers Observability)](https://developers.cloudflare.com/workers/observability/traces/)
- [Exporting OpenTelemetry Data](https://developers.cloudflare.com/workers/observability/exporting-opentelemetry-data/)
- [How KV works](https://developers.cloudflare.com/kv/concepts/how-kv-works/)
- [SQLite-backed Durable Object Storage API](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/)
- [Durable Objects Pricing](https://developers.cloudflare.com/durable-objects/platform/pricing/)
- [Versions & deployments](https://developers.cloudflare.com/workers/versions-and-deployments/)
- [Gradual deployments](https://developers.cloudflare.com/workers/versions-and-deployments/gradual-deployments/)
- [Rollbacks](https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/)
- [PEP 783 – Emscripten Packaging](https://peps.python.org/pep-0783/)
- [cibuildwheel 문서](https://cibuildwheel.pypa.io/en/stable/)

[^1]: <https://blog.cloudflare.com/python-workers-ga/>
[^2]: <https://developers.cloudflare.com/workers/languages/python/stdlib/>
[^3]: <https://developers.cloudflare.com/workers/languages/python/packages/>
[^4]: <https://peps.python.org/pep-0783/>
[^5]: <https://developers.cloudflare.com/workers/platform/limits/>
[^6]: <https://developers.cloudflare.com/workers/wrangler/configuration/>
[^7]: <https://developers.cloudflare.com/workers/languages/python/how-python-workers-work/>
[^8]: <https://developers.cloudflare.com/workers/observability/logs/workers-logs/>
[^9]: <https://developers.cloudflare.com/workers/observability/>
[^10]: <https://developers.cloudflare.com/workers/observability/traces/>
[^11]: <https://developers.cloudflare.com/workers/observability/exporting-opentelemetry-data/>
[^12]: <https://developers.cloudflare.com/kv/concepts/how-kv-works/>
[^13]: <https://developers.cloudflare.com/durable-objects/>
[^14]: <https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/>
[^15]: <https://developers.cloudflare.com/durable-objects/platform/pricing/>
[^16]: <https://developers.cloudflare.com/d1/platform/limits/>
[^17]: <https://developers.cloudflare.com/hyperdrive/concepts/how-hyperdrive-works/>
[^18]: <https://developers.cloudflare.com/workers/versions-and-deployments/>
[^19]: <https://developers.cloudflare.com/workers/versions-and-deployments/gradual-deployments/>
[^20]: <https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/>
[^21]: <https://developers.cloudflare.com/workers/languages/python/>
[^22]: <https://developers.cloudflare.com/workers/languages/python/examples/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
