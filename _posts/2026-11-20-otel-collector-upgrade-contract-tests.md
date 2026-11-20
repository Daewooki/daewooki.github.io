---
title: "OpenTelemetry Collector 업그레이드를 계약 테스트로 바꾸기"
description: "Collector YAML·processor 동작·semantic conventions 변화를 계약으로 고정해 업그레이드를 반복 가능한 리허설로 만든다."
date: 2026-11-20 15:50:00 +0900
categories: ["Data", "OpenTelemetry"]
tags: ["opentelemetry", "otel-collector", "contract-testing", "observability", "golden-tests", "cardinality"]
render_with_liquid: false
---

## Collector YAML이 왜 API가 되는가
Collector를 한 번이라도 운영해 본 팀은 결국 같은 결론으로 수렴합니다. Collector의 안정성은 바이너리 자체보다, 그 바이너리에 주입되는 YAML과 파이프라인 조합에서 결정됩니다. 수집 에이전트라기보다, 데이터 파이프라인 런타임에 가깝습니다. 그래서 업그레이드가 쌓이면 어느 시점에 ingestion이 조용히 새고, cardinality가 늘고, 대시보드가 특정 위젯부터 흔들립니다.

Collector를 API로 만든 요소는 크게 셋입니다.

- 설정 스키마: YAML의 키/타입/기본값/폐기 규칙이 버전마다 바뀝니다. `validate`는 통과했는데 `default`가 바뀌어 의미가 달라지는 경우가 더 무섭습니다.
- 동작 의미론: processor는 입력을 어떻게 변형하고, 실패를 어떻게 전파하며, context를 어디까지 보존하는지(심지어 SDK trace context가 아니라 Go `context.Context` 수준도 포함)까지 사실상 계약입니다.
- exporter 호환성: exporter는 Collector 외부 세계와의 wire contract입니다. 여기서 깨지면 데이터는 0이 되거나 재시도 폭탄이 됩니다.

운영 관점에서 “업그레이드”는 버전을 올리는 행위가 아니라, 이 계약들이 바뀌지 않았음을 증명하는 작업입니다. 여기까지를 자동화해서, 업그레이드를 릴리스 이벤트가 아니라 정기 리허설로 만드는 게 목표입니다.

## v0.165.0에서 계약이 변하는 지점
2026-11-07(UTC 기준 릴리스 페이지 표기상 07 Nov 05:02)에 `opentelemetry-collector-releases`에 v0.165.0이 게시됐습니다.[^1]

Collector core(v1.71.0/v0.165.0) 릴리스 노트에서 눈에 걸리는 것은 `pkg/confighttp`의 deprecated 설정 필드 제거입니다. `IdleConnTimeout`, `MaxIdleConns`, `MaxIdleConnsPerHost`, `DisableKeepAlives`가 제거되면서, 해당 필드를 쓰는 설정은 로드 단계에서 깨지는 쪽으로 이동합니다.[^2] 이건 단순한 “기능 삭제”가 아니라, **설정 스키마 계약이 깨지는** 전형적인 사례입니다.

contrib(v1.4.0/v0.165.0) 쪽은 더 직접적으로 운영 파이프라인을 건드립니다.

- SignalFx receiver 제거: deprecated였던 SignalFx receiver가 제거되었고, OTLP receiver 사용으로 이동하라고 명시되어 있습니다.[^3]
- Elasticsearch exporter deprecated 옵션 제거: `mapping::mode`, `retry::max_requests`, `*_dynamic_index` 같은 deprecated 옵션을 제거했고, 해당 옵션이 설정돼 있으면 config 로드가 실패합니다.[^3]
- `processor/transform`의 `flatten_data` 제거: deprecated 옵션이 제거되었고, `flatten.log`를 쓰라고 합니다. 역시 설정 스키마가 바로 깨지는 케이스입니다.[^3]
- Prometheus receiver 속성 변화: `__scheme__`, `__metrics_path__` 라벨을 더 이상 drop하지 않아 datapoint attributes에 남는다고 되어 있습니다. 이건 비용(시계열 수)과 대시보드 그룹핑이 같이 흔들릴 수 있습니다.[^3]

여기서 중요한 점은, “breaking change 목록에 없으면 안전”이 아니라는 겁니다. 릴리스 노트에 명시된 건 최악을 피하는 최소치이고, 운영에서 진짜 비용/대시보드/알람에 영향을 주는 변화는 기본값 변경, attribute 추가/이름 변경, processor 순서의 미세한 효과 같은 곳에서 터집니다.

v0.165.0 자체에서도, core 릴리스 노트에 파이프라인 조합에 대해 경고를 추가합니다. `batch processor`와 exporterhelper batching을 같이 쓰면 startup 경고를 내도록 바뀌었습니다.[^2] 이건 “동작 계약을 문서로만 두지 말고 런타임 경고로 밀어 넣는다”는 방향이고, 업그레이드 계약 테스트에서도 로그/경고를 검증 대상으로 편입할 이유가 됩니다.

## 스키마 계약: validate·components·print-config를 CI에 고정
스키마 계약은 “설정이 로드된다”로 끝내면 부족합니다. 업그레이드에서 스키마 계약은 3층으로 나누는 게 실전에서 안정적이었습니다.

1) parse/validate
2) 배포판에 컴포넌트가 존재하는지
3) 최종 config가 어떤 값으로 확정되는지(기본값 포함)

Collector 공식 문서는 `otelcol validate --config=...`를 config 검증 방법으로 안내합니다.[^4] 그리고 같은 문서에서 `otelcol components`로 해당 배포판에서 사용 가능한 컴포넌트를 확인할 수 있다고 설명합니다.[^4]

또한 `print-config`로 최종 config를 출력하는 방법을 제공합니다. 이 기능은 실험적일 수 있고 feature gate가 필요하다고 문서에 적혀 있습니다.[^4] 운영에서는 이 “실험적”이라는 딱지를 그대로 받아들이는 게 맞습니다. 다만 업그레이드 리허설 환경에서만 쓰는 “정규화 도구”로는 가치가 큽니다.

### CI에서 스키마 계약을 어떻게 고정할지
내가 쓰는 최소 구성은 다음 세 가지 아티팩트를 버전별로 저장하는 방식입니다.

- `validate` 결과(성공/실패, 에러 문자열)
- `components` 출력(배포판에 어떤 receiver/processor/exporter/extension이 있는지)
- `print-config` 출력(가능하면 JSON 포맷으로)

여기서 `components`는 특히 “컴포넌트 제거/이름 변경/배포판 차이”를 가장 빠르게 잡아냅니다. v0.165.0에서 SignalFx receiver가 제거되었다는 변화는, 내 YAML이 해당 receiver를 참조하는 순간 `validate` 이전에 이미 `components` diff에서 빨간불이 켜지는 쪽이 운영적으로 더 낫습니다.[^3]

### Docker로 버전별 validate를 돌리는 방법
OpenTelemetry 공식 문서는 Docker 설치 경로로 GHCR 이미지를 예시로 듭니다. 예를 들어 `opentelemetry-collector:0.165.0` 이미지를 `docker pull` 하도록 안내합니다.[^5]

contrib 배포판을 쓰는 팀이 더 많으니, 스키마 계약은 contrib 이미지를 기준으로 돌리는 게 현실적입니다.

```bash
# macOS/Linux 예시
export OTELCOL_VER=0.165.0

docker run --rm \
  -v "$PWD/collector.yaml:/etc/otelcol-contrib/config.yaml:ro" \
  ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:${OTELCOL_VER} \
  validate --config=/etc/otelcol-contrib/config.yaml

docker run --rm \
  ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:${OTELCOL_VER} \
  components > .artifacts/components-${OTELCOL_VER}.txt
```

이 레이어에서 v0.165.0 core의 `pkg/confighttp` deprecated 필드 제거 같은 변경은, 설정에서 해당 필드가 쓰이는 순간 바로 걸립니다.[^2] 여기서 걸리는 건 오히려 좋은 신호입니다. 운영에서 “조용히 다른 기본값으로 해석돼 비용이 바뀌는” 것보다, CI에서 크게 깨지는 게 싸게 끝납니다.

## 파이프라인 계약 테스트 베드 설계
스키마 계약만 통과하면 업그레이드가 끝나는 것처럼 보이지만, 운영 장애는 그 다음에서 생깁니다.

- processor 순서/기본값 변경으로 attribute가 추가/삭제
- batch/queue 정책이 바뀌면서 export 패턴이 변하고 backpressure 지점이 달라짐
- receiver가 라벨/속성을 더 보존하면서 cardinality가 증가

이걸 잡아내려면 “파이프라인을 실제로 흘려보고 출력물을 비교”해야 합니다. 여기서 나는 업그레이드 테스트를 두 종류로 쪼갭니다.

- golden dataset 기반 회귀 테스트: 입력(telemetry) → Collector → 출력(telemetry)을 정규화해서 diff
- 비용/카디널리티 테스트: 출력 telemetry에서 series/attribute 조합 수를 세어 threshold로 제어

Collector의 file output은 `fileexporter`가 가장 싸고 확실합니다. contrib의 `fileexporter`는 로컬 파일로 OTLP JSON을 쓸 수 있고, 문서에서 docker run 예시도 제공합니다.[^6] OTLP JSON을 line-delimited로 쓰는 것은 OTLP File Exporter 스펙에서도 `jsonl` 확장자를 선호한다고 명시합니다.[^7]

fileexporter를 택하면 vendor backend까지 붙이지 않아도 되고, exporter 호환성 테스트는 별도 레이어로 분리할 수 있습니다.

### 테스트 입력을 무엇으로 생성할지
`telemetrygen`은 Collector 테스트용으로 빠르게 traces/metrics/logs를 발생시키는 도구이고, contrib repo에 README가 있습니다.[^8] OpenTelemetry Collector quick start에서도 `telemetrygen traces --otlp-insecure ...`로 trace를 생성하는 예시를 제공합니다.[^9]

다만 golden 테스트 관점에서는 무작위 trace/span id와 timestamp가 늘 문제입니다. 나는 입력 생성은 telemetrygen을 쓰되, 출력 비교는 “전체 동일”이 아니라 “정규화 후 동일 + 핵심 필드 단언(assert)” 조합으로 맞춥니다. 전체 동일을 목표로 하면, 테스트가 깨지는 이유가 업그레이드 때문인지 단순 타임스탬프 때문인지 분간이 안 됩니다.

## Golden dataset: OTLP JSONL 정규화와 diff
여기부터는 실제로 굴러가는 형태로 정리합니다. 로컬에서도 돌고, CI에서도 그대로 돌아가야 합니다.

### 디렉터리 구성
```text
collector-contract/
  collector.yaml
  docker-compose.yml
  out/
    (여기에 결과가 생성됨)
  tools/
    normalize_otlp_jsonl.py
    diff_golden.py
  golden/
    0.164.0/
      traces.jsonl
      metrics.jsonl
      logs.jsonl
      stats.json
  requirements.txt
  Makefile
```

`golden/0.164.0`는 “현재 운영에서 쓰는 Collector 버전”의 기준 출력물입니다. 업그레이드 PR에서는 “새 버전에서 나온 정규화 출력물”과 diff를 보고, 의도한 변화만 golden을 갱신합니다.

### collector.yaml (테스트용 파이프라인)
아래 설정은 핵심만 넣습니다.

- `otlp` receiver로 telemetrygen 입력 받기
- `prometheus` receiver로 scrape를 하나 넣어, v0.165.0의 `__scheme__`, `__metrics_path__` attribute 변화를 잡아내기[^3]
- traces/metrics/logs 각각 fileexporter로 분리해서 파일을 쓰기

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

  prometheus:
    config:
      scrape_configs:
        - job_name: "contract-prom"
          scrape_interval: 1s
          static_configs:
            - targets: ["prom-target:9464"]

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 256

  batch:
    timeout: 1s
    send_batch_size: 128

exporters:
  file/traces:
    path: /out/traces.jsonl
  file/metrics:
    path: /out/metrics.jsonl
  file/logs:
    path: /out/logs.jsonl

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [file/traces]

    metrics:
      receivers: [otlp, prometheus]
      processors: [memory_limiter, batch]
      exporters: [file/metrics]

    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [file/logs]
```

여기서 `batch processor`는 업그레이드에 따라 exporterhelper batching과의 조합 경고가 생길 수 있다는 걸 염두에 둔 구성입니다. v0.165.0 core는 이 조합을 탐지해 startup warning을 출력하도록 개선했습니다.[^2] 운영에서는 이런 경고가 “업그레이드 리허설에서만 먼저 보게 되는” 게 이상적입니다.

### docker-compose.yml
Prometheus scrape target은 가장 단순한 HTTP 서버로 충분합니다.

```yaml
services:
  collector:
    image: ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:${OTELCOL_VERSION}
    command: ["--config=/etc/otelcol-contrib/config.yaml"]
    volumes:
      - ./collector.yaml:/etc/otelcol-contrib/config.yaml:ro
      - ./out:/out
    ports:
      - "4317:4317"
      - "4318:4318"

  prom-target:
    image: python:3.12-slim
    working_dir: /app
    command: ["python", "-u", "server.py"]
    volumes:
      - ./tools/prom_target_server.py:/app/server.py:ro
    ports:
      - "9464:9464"

  telemetrygen:
    image: ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:latest
    depends_on:
      - collector
    entrypoint: ["/bin/sh", "-lc"]
    command:
      - |
        telemetrygen traces --otlp-endpoint collector:4317 --otlp-insecure --duration 3s --rate 5 \
          --service contract-svc --telemetry-attributes "deployment.environment=contract,route=/checkout";
        telemetrygen metrics --otlp-endpoint collector:4317 --otlp-insecure --duration 3s --rate 5 \
          --service contract-svc --telemetry-attributes "deployment.environment=contract";
        telemetrygen logs --otlp-endpoint collector:4317 --otlp-insecure --duration 3s --rate 5 \
          --service contract-svc --telemetry-attributes "deployment.environment=contract";
```

`telemetrygen` 사용법은 contrib의 README에 옵션 예시가 있고, OpenTelemetry 문서에서도 quick start에서 traces 생성 예시를 보여줍니다.[^8]

`telemetrygen:latest`는 재현성 측면에서 최선은 아닙니다. 하지만 이 글에서 핵심은 “Collector 업그레이드 시 Collector 쪽 계약을 고정하는 방법”이고, 입력 생성 도구는 정규화 레이어로 흡수합니다. 운영에서는 telemetrygen 이미지를 digest로 고정하는 편이 낫습니다.

### tools/prom_target_server.py (Prometheus scrape target)
```python
from http.server import BaseHTTPRequestHandler, HTTPServer

METRICS = """
# HELP contract_requests_total Total requests
# TYPE contract_requests_total counter
contract_requests_total{path="/checkout"} 1
""".lstrip()

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(METRICS.encode("utf-8"))

HTTPServer(("0.0.0.0", 9464), H).serve_forever()
```

Prometheus receiver 관련 계약 변화는 v0.165.0 contrib 릴리스 노트에 명시되어 있고, `__scheme__`, `__metrics_path__` 라벨을 drop하지 않는다는 점이 핵심입니다.[^3] 이 테스트 타깃은 그 변화를 “metrics.jsonl에 실제로 attribute가 추가되는지”로 환원해 확인합니다.

### tools/normalize_otlp_jsonl.py (정규화)
fileexporter 출력은 OTLP JSON 기반이고 `jsonl` 포맷으로 저장하는 것이 스펙에도 부합합니다.[^7] 따라서 정규화는 line-by-line JSON을 읽어 동적 필드를 제거/치환하는 방식이 깔끔합니다.

```python
import json
import sys
from typing import Any

DYNAMIC_KEYS = {
    "timeUnixNano",
    "startTimeUnixNano",
    "endTimeUnixNano",
    "observedTimeUnixNano",
}

ID_KEYS = {"traceId", "spanId", "parentSpanId"}

def normalize(obj: Any, id_map: dict[str, str]) -> Any:
    if isinstance(obj, list):
        # 리스트는 내부가 dict면 key를 기준으로 정렬 가능한 경우 정렬
        norm = [normalize(x, id_map) for x in obj]
        if all(isinstance(x, dict) for x in norm):
            def k(x: dict):
                # 자주 나오는 케이스: attributes: [{key, value}, ...]
                if "key" in x:
                    return ("attr", x.get("key"))
                if "name" in x:
                    return ("name", x.get("name"))
                return ("z", json.dumps(x, sort_keys=True))
            norm.sort(key=k)
        return norm

    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in DYNAMIC_KEYS:
                out[k] = "0"
                continue

            if k in ID_KEYS and isinstance(v, str):
                if v not in id_map:
                    id_map[v] = f"id{len(id_map)+1}"
                out[k] = id_map[v]
                continue

            out[k] = normalize(v, id_map)

        # dict key 정렬 효과를 위해 dump 단계에서 sort_keys를 사용
        return out

    return obj

def main(inp: str, outp: str):
    id_map: dict[str, str] = {}
    with open(inp, "r", encoding="utf-8") as f, open(outp, "w", encoding="utf-8") as w:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            n = normalize(obj, id_map)
            w.write(json.dumps(n, sort_keys=True))
            w.write("\n")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

정규화 전략은 “동적 필드를 버리고, 나머지 구조를 안정적으로 비교”하는 데 집중합니다. trace/span id는 완전히 제거하면 관계를 추적하기 어렵기 때문에, 등장 순서대로 `id1`, `id2`처럼 매핑만 고정합니다.

내 경험상 이 정도면 업그레이드에서 중요한 변화(새 attribute 추가/삭제, processor에 의한 값 변화, receiver 동작 변화)는 대부분 diff로 드러납니다.

### tools/diff_golden.py (golden 비교 + 단언)
아래는 단순 diff가 아니라, **계약으로 삼고 싶은 규칙**을 같이 박아두는 형태입니다.

- prometheus receiver가 만든 datapoint attributes에 `__scheme__`, `__metrics_path__`가 들어오는지(업그레이드로 바뀌는 지점이므로)
- config에서 의도한 resource attribute가 유지되는지

```python
import json
import sys

def load_lines(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]

def assert_prometheus_contract(metrics):
    # 매우 거친 탐색이지만, 계약 테스트에서는 이 정도가 유지보수성이 좋았습니다.
    # datapoint attributes는 OTLP JSON에서 구조가 깊습니다.
    serialized = "\n".join(json.dumps(x, sort_keys=True) for x in metrics)
    # v0.165.0 contrib 릴리스 노트에 이 라벨들이 drop되지 않는다고 명시되어 있음
    # 그래서 업그레이드 시점부터는 존재하는 것을 '기대'로 고정할 수도 있습니다.
    if "__scheme__" not in serialized or "__metrics_path__" not in serialized:
        raise AssertionError("prometheus labels __scheme__/__metrics_path__ not found; check receiver/prometheus behavior")

def main(golden: str, candidate: str):
    g = load_lines(golden)
    c = load_lines(candidate)

    # 1) 핵심 단언
    if golden.endswith("metrics.norm.jsonl"):
        assert_prometheus_contract(c)

    # 2) 라인 단위 diff (정규화 결과는 문자열 비교가 가장 싸고 단단함)
    with open(golden, "r", encoding="utf-8") as f:
        gs = [x.strip() for x in f if x.strip()]
    with open(candidate, "r", encoding="utf-8") as f:
        cs = [x.strip() for x in f if x.strip()]

    if gs != cs:
        # CI에서 보기 좋게 일부만 출력
        for i, (a, b) in enumerate(zip(gs, cs)):
            if a != b:
                print("DIFF at line", i+1)
                print("golden:", a)
                print("cand  :", b)
                break
        raise SystemExit(1)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

이 단언의 근거는 v0.165.0 contrib 릴리스 노트에서 prometheus receiver가 해당 라벨들을 더 이상 drop하지 않는다고 명시한 부분입니다.[^3] 이걸 “변화로 감지”할지 “변화 이후의 기대값으로 고정”할지는 팀의 선택입니다. 내 쪽에서는 비용에 민감한 환경이면 감지 대상으로 두고, 업그레이드 PR에서 승인된 뒤 golden을 갱신하는 편을 택합니다.

## 비용 계약: cardinality를 테스트 케이스로 만들기
Collector 업그레이드로 가장 자주 터지는 건 ingestion 자체가 아니라 비용입니다. cardinality는 보통 아래 경로로 증가합니다.

- receiver가 기존에 drop하던 라벨/속성을 보존
- processor가 attribute를 새로 붙이거나(특히 k8s, cloud, resource detection)
- semantic conventions migration으로 기존 키를 새 키로 바꾸면서, 양쪽이 공존하는 기간이 생김

v0.165.0에서 prometheus receiver의 `__scheme__`, `__metrics_path__`는 이 비용 경로를 아주 전형적으로 보여줍니다. 릴리스 노트에 명시되어 있고, 이제 datapoint attributes에 남습니다.[^3]

이런 변화는 “출력 JSON diff”에서도 잡히지만, 운영에서 중요한 건 “시계열 수가 몇 % 늘어나는지”입니다. 그래서 golden 계약에 다음 같은 통계를 같이 저장합니다.

- metric name 별 unique attribute-set 수
- 전체 unique series 수
- 상위 N개의 attribute key(가장 cardinality를 밀어 올리는 키)

테스트는 대충 아래처럼 구현합니다.

```python
# tools/metrics_cardinality.py
import json
import sys
from collections import defaultdict

def iter_datapoints(metrics_doc):
    # OTLP JSON 구조를 정확히 전부 다루려면 길어지므로,
    # 계약 테스트에 필요한 범위만 느슨하게 탐색합니다.
    s = json.dumps(metrics_doc)
    return s

def main(inp_jsonl: str):
    series = set()
    with open(inp_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            # 매우 러프하지만, 계약 테스트에서는 '증가 감지'가 목적이라 이 정도도 쓸만합니다.
            flat = json.dumps(obj, sort_keys=True)
            if "contract_requests_total" in flat:
                series.add(flat)

    print(json.dumps({"series_like_count": len(series)}, indent=2))

if __name__ == "__main__":
    main(sys.argv[1])
```

정교한 cardinality 카운터는 팀별로 확장하면 됩니다. 중요한 건, 비용 변화를 “리뷰 가능한 숫자”로 PR에 남기는 구조입니다.

## Exporter 계약: 호환성은 연결이 아니라 설정에서 먼저 깨진다
Exporter 호환성은 흔히 “백엔드가 응답하나”로만 생각합니다. 실제로는 그 전에 깨지는 경우가 많습니다.

- deprecated 옵션 제거로 config 로드가 실패
- 기본 timeout/keepalive 변화로 retry 패턴이 바뀌고, backpressure가 생김

v0.165.0 core의 `pkg/confighttp` deprecated 필드 제거는 exporter/receiver 양쪽에 영향을 줄 수 있는 대표 케이스입니다.[^2] 업그레이드 계약 테스트에서 exporter 호환성은 아래처럼 분리하는 게 실전에서 깔끔합니다.

1) 설정 호환성: `validate`로 잡기
2) 런타임 호환성: 최소한의 mock backend로 “요청이 실제로 나가는지” 확인

설정 호환성은 이미 스키마 계약 레이어에서 끝났습니다.

런타임 호환성은 여기서 깊게 파고들면 금방 vendor별 지옥이 됩니다. 나는 최소한의 smoke로만 고정합니다.

- exporter endpoint에 TCP connect가 되고
- 일정 시간 내에 exporter retry 폭주/queue 폭증이 없고
- Collector 로그에 exporter 에러가 없다

이 정도만 통과해도 “업그레이드로 exporter가 아예 멈추는” 상황은 크게 줄어듭니다.

## 업그레이드 리허설을 월간 작업으로 만드는 방법
Collector 업그레이드 리허설을 일회성 이벤트로 끝내면, 결국 큰 버전 점프로 돌아가고 비용이 폭발합니다. 나는 리허설 자체를 파이프라인으로 고정합니다.

- (매주/격주) 새 버전 태그 감지 → 리허설 브랜치 생성
- 스키마 계약 테스트(`validate`, `components`, `print-config`) 실행
- golden dataset 테스트 실행
- cardinality 통계 계산
- diff와 숫자를 PR에 붙이고, 승인된 변화만 golden 갱신

여기서 릴리스 노트의 breaking changes는 “테스트가 실패했을 때 참고하는 힌트”로만 취급합니다. 예를 들어 v0.165.0 contrib에서는 `processor/transform`의 `flatten_data` 제거가 명시되어 있으니, config validation이 깨지면 바로 원인을 찾을 수 있습니다.[^3]

또한 Prometheus receiver의 라벨 보존 변화처럼 “비용”에 직결되는 변화도 릴리스 노트에 들어 있습니다.[^3] 이 변화는 diff만으로도 잡히지만, 실제로는 cardinality 통계를 PR에 같이 올려야 리뷰가 쉬워집니다.

정리하면, 업그레이드를 릴리스 노트 독해로 처리하지 않고, 계약 테스트로 처리해야 팀 내 지식 격차가 줄어듭니다. Collector는 YAML과 processor 동작이 API이고, API는 결국 테스트로만 안정화됩니다.

예전에 정리한 [OTLP JSON 엄격 파싱이 Collector 파이프라인을 깨는 방식](https://daewooki.github.io/posts/otlp-json-strict-parsing-breaks-pipeline/)처럼, 파이프라인은 생각보다 쉽게 깨지고 깨진 뒤에야 비용과 공백이 보입니다. 나는 업그레이드를 정기 리허설로 돌리는 쪽이 총비용이 낮다고 결론 내렸습니다.

## 참고 자료
- [opentelemetry-collector-releases v0.165.0 릴리스](https://github.com/open-telemetry/opentelemetry-collector-releases/releases/tag/v0.165.0)
- [OpenTelemetry Collector core v1.71.0/v0.165.0 릴리스 노트](https://github.com/open-telemetry/opentelemetry-collector/releases/tag/v0.165.0)
- [OpenTelemetry Collector contrib v1.4.0/v0.165.0 릴리스 노트](https://github.com/open-telemetry/opentelemetry-collector-contrib/releases/tag/v0.165.0)
- [Collector configuration 문서(Validate, Components, Print-config)](https://github.com/open-telemetry/opentelemetry.io/blob/main/content/en/docs/collector/configuration.md)
- [Collector Feature Gates 문서](https://github.com/open-telemetry/opentelemetry-collector/blob/main/featuregate/README.md)
- [Collector Docker 설치 문서(GHCR 이미지)](https://opentelemetry.io/docs/collector/install/docker/)
- [telemetrygen README](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/cmd/telemetrygen/README.md)
- [OTLP File Exporter 스펙(OTLP JSON, jsonl)](https://opentelemetry.io/docs/specs/otel/protocol/file-exporter/)
- [fileexporter README](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/exporter/fileexporter/README.md)
- [Collector quick start(telemetrygen 예시)](https://opentelemetry.io/docs/collector/quick-start/)

[^1]: <https://github.com/open-telemetry/opentelemetry-collector-releases/releases/tag/v0.165.0>
[^2]: <https://github.com/open-telemetry/opentelemetry-collector/releases/tag/v0.165.0>
[^3]: <https://github.com/open-telemetry/opentelemetry-collector-contrib/releases/tag/v0.165.0>
[^4]: <https://github.com/open-telemetry/opentelemetry.io/blob/main/content/en/docs/collector/configuration.md>
[^5]: <https://opentelemetry.io/docs/collector/install/docker/>
[^6]: <https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/exporter/fileexporter/README.md>
[^7]: <https://opentelemetry.io/docs/specs/otel/protocol/file-exporter/>
[^8]: <https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/cmd/telemetrygen/README.md>
[^9]: <https://opentelemetry.io/docs/collector/quick-start/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
