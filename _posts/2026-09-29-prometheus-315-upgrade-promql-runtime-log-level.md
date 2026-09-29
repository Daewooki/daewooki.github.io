---
title: "Prometheus 3.15.0 업그레이드 포인트: PromQL과 런타임 로그 레벨"
description: "PromQL peakSamples 변화와 runtime.log_level 전환을 쿼리 비용·limit·로그 기반 관측 공백 관점에서 점검합니다."
date: 2026-09-29 13:38:37 +0900
categories: ["Data", "Prometheus"]
tags: ["prometheus", "promql", "query-cost", "runtime-log-level", "upgrade-checklist"]
render_with_liquid: false
---

## 3.15.0의 CHANGE를 운영 리스크로 번역하면

Prometheus 3.15.0은 2026-09-24에 릴리스됐고, 릴리스 노트의 `CHANGE` 항목에 운영자가 민감해할 만한 두 축이 같이 들어 있습니다. 하나는 PromQL 쿼리 엔진이 `peakSamples`/`query.max-samples`와 맞물리는 방식이 바뀌는 항목이고, 다른 하나는 `--log.level`을 deprecate 하고 `runtime.log_level`로 기본 로그 레벨과 런타임 변경을 재설계한 항목입니다.[^1]

릴리스 노트 텍스트만 읽으면 대체로 긍정적인 변화처럼 보입니다. 실제로도 버그 픽스/기능 개선 성격이 강합니다. 문제는 운영에서는 버그 픽스가 곧바로 “행동이 바뀌는 변화”가 되고, 그 변화가 쿼리 비용, limit 차단, 로그 기반 알림/분석 파이프라인에 연쇄 반응을 일으킨다는 점입니다.

여기서는 3.15.0의 `CHANGE`를 다음의 실패 모드로 재해석합니다.

- 쿼리 비용 폭증: 특정 대시보드/탐색 쿼리가 업그레이드 전에는 limit에 걸려 실패하던 것이 업그레이드 후 성공하면서 CPU/IO가 늘어나는 경우
- limit 차단의 의미 변화: `query.max-samples`가 “가드레일”로서 우연히 담당하던 역할이 약해지는 경우
- 로그 레벨 변경으로 인한 관측 공백: config reload가 로그 레벨까지 바꾸게 되면서, 로그 기반의 탐지/감사/디버깅 루틴이 끊기는 경우

추가로, Prometheus는 API 안정성 문서에서 “로그의 포맷은 안정성 보장 대상이 아니다”라고 못 박아 둡니다. 로그 기반 운영을 하고 있다면, 로그는 원래부터 쉽게 흔들릴 수 있는 레이어였고 3.15.0은 그 흔들림을 더 눈에 띄게 만들 수 있습니다.[^2]

## CHANGE 1: range query의 end/step 정렬과 peakSamples가 왜 운영 이슈가 되는가

3.15.0 릴리스 노트의 첫 번째 `CHANGE`는 요약하면 다음입니다.

- `query_range`에서 `end`가 `step`에 정렬되지 않은 경우, range query 내부의 subquery가 부모 쿼리의 마지막 실제 step 이후까지 평가되는 문제가 있었고
- 그 결과 `peakSamples`가 부풀고, `query.max-samples` 제한에도 불필요하게 걸릴 수 있었고
- 실제 결과에 쓰이지도 않는 샘플을 읽으면서 storage I/O를 낭비했다

이 내용은 릴리스 노트에 그대로 적혀 있습니다.[^1]

여기서 운영자가 신경 써야 하는 키워드는 `peakSamples` 자체가 아닙니다. `peakSamples`는 결과에 붙는 통계치일 뿐입니다. 운영 이슈는 “쓸모 없는 샘플을 더 읽고(limit에도 더 세고) 있었다”는 사실이 더 중요합니다.

### 왜 end/step 정렬이 자주 깨지는가

Grafana 같은 UI가 호출하는 `query_range`를 생각하면 `end=now` 형태가 흔합니다. `step`은 패널 해상도/최소 간격으로 정해지는데, `now`의 epoch seconds가 `step`의 배수일 가능성은 낮습니다. 즉 **정렬되지 않은 end는 정상적인 흔한 입력**입니다.

Prometheus HTTP API 문서에서 `query_range`는 `start`, `end`, `step`을 받고, `stats=all`로 쿼리 통계를 포함시킬 수 있습니다.[^3]

정렬이 깨진 end가 들어오는 자체는 문제가 아닙니다. 문제는 그 상황에서 subquery가 부모의 마지막 step을 넘어 평가되는 버그가 있었고, 그 버그가 (1) 샘플 로드/읽기, (2) 메모리 피크(`peakSamples`), (3) `query.max-samples` 제한에 영향을 줬다는 점입니다.[^1]

### `peakSamples`와 `query.max-samples`가 어떤 관계인지 다시 정리

HTTP API 문서의 Query statistics 정의를 보면 다음 항목들이 구분됩니다.

- `totalQueryableSamples`: 쿼리가 로드한 샘플 수(범위 함수의 경우 step마다 윈도우 전체가 카운트될 수 있음)
- `samplesRead`: 실제로 I/O로 읽은 샘플 수(범위 함수 range query에서는 step마다 새로 읽은 포인트만 카운트되는 성격)
- `peakSamples`: 평가 중 메모리에 올라간 샘플의 피크

그리고 서버 메트릭으로 `prometheus_engine_query_samples_total`(loaded)과 `prometheus_engine_query_samples_read_total`(read)를 제공한다고 적혀 있습니다.[^3]

여기서 `query.max-samples` 플래그는 “단일 쿼리가 메모리에 로드할 수 있는 샘플 수 상한”으로 설명됩니다.[^4]

즉, range query/subquery가 “마지막 step 이후까지 불필요하게 평가”되면:

1) `samplesRead`가 증가할 수 있고(storage read가 늘 수 있음)
2) 특정 순간의 in-memory 샘플 셋이 커져 `peakSamples`가 증가할 수 있고
3) 그 `peakSamples` 증가가 `query.max-samples` 차단으로 이어질 수 있습니다

릴리스 노트는 2)와 3)를 명시하고, 1)도 “storage I/O 낭비”로 명시합니다.[^1]

## 이 CHANGE가 “쿼리 비용을 줄이는 좋은 픽스”로만 끝나지 않는 이유

운영 관점에서는 이 CHANGE가 두 방향으로 사고를 만들 수 있습니다.

### A. 업그레이드 후 부하가 줄어드는 방향(직관적인 기대)

- 같은 쿼리를 날렸을 때 불필요한 샘플을 덜 읽는다
- `peakSamples`가 낮아지고, `query.max-samples` 초과 실패가 줄어든다
- 대시보드가 더 잘 뜨고, 탐색 쿼리 UX가 좋아진다

이건 순수하게 긍정입니다.

### B. 업그레이드 후 부하가 늘어나는 방향(운영자가 놓치기 쉬운 역효과)

여기가 핵심입니다. 업그레이드 전에는 버그로 인해 `peakSamples`가 더 크게 잡히면서 `query.max-samples`에 걸려 실패하던 쿼리가 있었을 수 있습니다. 그 실패는 사용자 입장에서는 불편하지만, 운영 입장에서는 일종의 가드레일처럼 작동했을 가능성이 있습니다.

3.15.0으로 올라가면 그 쿼리가 “실제로 필요했던 만큼만 샘플을 로드/읽고” limit 아래로 내려오면서 성공할 수 있습니다. 성공 자체는 좋은데, 그 순간부터 해당 쿼리가 CPU/IO를 실사용하게 됩니다.

정리하면, **버그가 우연히 limit 차단을 강하게 만들던 환경**에서는 3.15.0 업그레이드가 곧바로 “막혀 있던 쿼리가 풀려서 부하가 늘어나는 이벤트”가 될 수 있습니다.[^1]

내 경우 Prometheus 업그레이드에서 제일 위험한 순간은 “대시보드가 더 잘 뜨게 된 직후”입니다. 장애는 대개 그때부터 시작합니다. 잘 뜨는 만큼 더 많이 눌리고, 더 많은 사람이 더 자주 새로고침하면서, 이전에는 실패로 자연스럽게 억제되던 트래픽이 정상 트래픽으로 바뀝니다.

## CHANGE 2: start timestamp reset 판정 변경이 알림을 바꿀 수 있다

3.15.0 릴리스 노트의 두 번째 `CHANGE`는 다음 한 줄입니다.

- subsequent samples 사이에서 start timestamp가 바뀌지 않았으면 start timestamp reset으로 등록하지 않는다

릴리스 노트 텍스트는 짧지만, 실제 영향 범위는 `use-start-timestamps`를 켠 환경에서 `rate()`, `increase()`, `resets()` 같은 함수의 reset 감지 로직과 연결됩니다. 3.x에서 start timestamp(ST) 관련 기능들이 계속 확장되고 있어서, 이 변경은 생각보다 운영 신호에 영향을 줄 수 있습니다.[^1]

### start timestamp가 무엇이고, 왜 reset 판단에 들어오는가

Prometheus feature flag 문서에는 `--enable-feature=use-start-timestamps`가 다음을 가능하게 한다고 적혀 있습니다.

- start timestamps(ST)를 `rate()`, `irate()`, `increase()`, `start_timestamp()` 같은 PromQL 함수에서 사용한다
- 다만 extended range selectors와는 현재 같이 안 맞는다

[^5]

즉 ST를 쓰는 환경에서는, 단순히 값이 떨어졌는지(전통적인 counter reset 힌트)만 보는 게 아니라 “ST가 어떻게 변했는지”도 reset 판단 재료가 됩니다.

### 3.15.0이 바꾼 핵심: ST가 동일하면 reset이 아니다

Prometheus 코드(`promql/functions.go`)의 `isStartTimestampReset` 함수 주석/조건을 보면, 3.15.0에서는 다음 조건에서 reset이 아니라고 처리합니다.

- `prevStartTimestamp == currStartTimestamp`면 reset이 아니다
- `currStartTimestamp == 0`이면(미설정) reset이 아니다
- `currStartTimestamp >= currTimestamp`면(잘못된 값 또는 unknown start time 처리) reset이 아니다

이 취지는 코드에 직접 드러납니다.[^6]

운영 관점에서 이 변경이 중요한 이유는 하나입니다. reset 판정은 곧 `rate()/increase()` 결과의 튐(spike) 여부와 연결되고, 그 튐은 SLO burn alert나 오류율/트래픽 알림의 false positive로 연결되기 때문입니다.

### 어떤 환경에서 영향이 큰가

- OTLP 기반으로 들어온 cumulative series를 Prometheus가 ST와 함께 저장/활용하는 구성
- remote write 2.0 / ST 관련 기능을 이미 실험적으로 켠 구성
- `resets()`를 알림 조건에 직결시키는 구성

이때 업그레이드 후에는 “이전에는 reset으로 찍혔던 경계 케이스”가 reset이 아닌 것으로 처리될 수 있습니다. 튐이 줄어드는 방향이 대부분이겠지만, 운영에서는 “알림이 조용해졌다”가 항상 좋은 소식은 아닙니다. 조건 자체가 바뀐 결과라면, 조용해진 만큼 감지가 누락될 가능성도 같이 검토해야 합니다.

## CHANGE 3: `--log.level` deprecate와 `runtime.log_level` 도입이 만드는 관측 공백

3.15.0의 로그 관련 변화는 두 줄이 같이 붙어 있습니다.

- `--log.level`을 deprecate 하고, 기본 레벨은 config의 `runtime.log_level`로 공급한다
- config reload 시에 `runtime.log_level`로 프로세스 로그 레벨을 바꿀 수 있게 한다

[^1]

### 커맨드라인 관점: `--log.level`이 “deprecated지만 아직 동작”

Prometheus 공식 command-line 문서에도 `--log.level` 옆에 deprecated 문구가 들어가 있습니다. “config file의 `runtime.log_level`을 쓰라”는 형태입니다.[^4]

즉 3.15.0 업그레이드 직후에 당장 부팅이 안 되거나 하진 않을 가능성이 큽니다. 운영 리스크는 “계속 동작하니까 나중으로 미룸” 쪽에서 더 자주 생깁니다.

### 설정 파일 관점: `runtime.log_level`은 reload 가능한 값

Prometheus configuration 문서에 `runtime:` 블록이 있고, 그 아래에 `log_level`이 있으며 “이 설정은 config reload로 바꿀 수 있다”고 적혀 있습니다.[^7]

config reload 자체는 SIGHUP 또는 `/-/reload`로 트리거할 수 있고, `/-/reload`는 `--web.enable-lifecycle`가 필요합니다.[^7]

이 조합이 의미하는 운영 변화는 단순합니다.

- 예전: config reload는 스크레이프/룰/리라벨 등만 바꾼다(로그 레벨은 재시작이 필요)
- 이제: config reload는 **로그 레벨까지 바꿀 수 있다**

### PR 설명에서 드러나는 운영 포인트

3.15.0에 포함된 PR(#19511) 설명에 운영자가 알아야 할 디테일이 몇 가지 나옵니다.

- `runtime.log_level`의 기본값은 `info`
- 기존 `--log.level`은 “startup logging을 제어”하고, config에 `runtime.log_level`이 없을 때 기본값으로도 쓰인다(하지만 deprecated)
- live log level 변경은 “모든 component reloader가 성공한 뒤”에만 적용된다
- invalid reload는 HTTP 500을 반환하고, 이전 레벨이 유지된다

이 내용은 PR 본문에 직접 적혀 있습니다.[^8]

이 설계는 꽤 합리적입니다. reload 실패로 로그 레벨이 반쯤 바뀌는 것 같은 최악의 상태를 피하기 때문입니다. 그럼에도 운영에서는 다음의 새로운 실패 모드가 생깁니다.

1) config 템플릿/머지 과정에서 `runtime.log_level`이 의도치 않게 바뀌어, incident 직전에 debug 로그가 사라짐
2) “로그 레벨은 배포 파이프라인이 관리한다”라는 전제가 깨져서, 재현이 어려운 관측 공백이 생김
3) 로그 기반 알림(예: reload 실패/TSDB 경고)을 info 레벨에 의존하고 있으면, 레벨 다운으로 알림이 사라짐

추가로 Prometheus는 로그 포맷의 안정성을 보장하지 않는다고 명시합니다. 로그 기반 파이프라인(파싱/정규식/필드 기반 알림)은 원래도 깨지기 쉬운 구조이고, log level이 reload 가능해지면 “운영자가 의도하지 않았지만 깨지는 경우”가 더 늘어납니다.[^2]

## 업그레이드 전: 쿼리 비용/limit 관점에서 반드시 남겨야 하는 베이스라인

3.15.0의 PromQL 변경은 결과값을 바꾸는 변화라기보다는 “평가 과정과 비용을 바꾸는 변화”에 가깝습니다. 이런 변경은 결과 비교만 하면 놓치기 쉽습니다. 그래서 업그레이드 전에 비용 관련 베이스라인을 남겨야 합니다.

여기서 베이스라인은 두 가지 레이어로 잡는 게 안전합니다.

- API 응답 기반(쿼리 단위): `stats=all`의 `samplesRead`, `totalQueryableSamples`, `peakSamples`, `timings`
- 서버 메트릭 기반(전체 트래픽): `prometheus_engine_query_samples_total`, `prometheus_engine_query_samples_read_total` 같은 엔진 카운터

Query statistics의 각 필드 정의는 공식 API 문서에 정리되어 있습니다.[^3]

### 1) 업그레이드 대상으로 “살아 있는 쿼리 목록”을 어떻게 잡을 것인가

가장 현실적인 목록은 보통 이 셋에서 나옵니다.

- Grafana 대시보드의 PromQL 패널 expr
- Prometheus recording/alerting rules expr
- 장애 때 사람들이 직접 치는 ad-hoc 탐색 쿼리(이건 조직마다 다르고 로그가 없으면 잡기 어렵다)

세 번째를 잡으려면 query log가 가장 편합니다. Prometheus에는 query log 가이드가 별도로 있고, 파일에 모든 쿼리를 로깅하는 형태로 설명합니다.[^9]

다만 “query log를 항상 켜둘 것인가”는 또 다른 비용/개인정보/보안 이슈가 됩니다. 여기서는 업그레이드 리허설 기간에만 제한적으로 켜고 상위 N개 쿼리만 추출하는 방식이 그나마 부담이 덜합니다.

### 2) `stats=all`로 peakSamples를 수집하는 최소 커맨드

Prometheus HTTP API 문서에 따라 `stats=all`을 주면 `stats` 객체가 내려옵니다.[^3]

아래는 range query를 날리고 `samples`를 뽑는 최소 예시입니다.

```bash
# 필요 도구: curl, jq
# PROM_URL 예: http://prometheus:9090
# 주의: stats=all은 결과 payload가 커질 수 있습니다.

PROM_URL="http://localhost:9090"
Q='sum by (job) (rate(prometheus_http_requests_total[5m]))'
START='2026-09-29T00:00:00Z'
END='2026-09-29T01:00:07Z'   # 일부러 step과 정렬되지 않게 7초를 더함
STEP='15s'

curl -sG "$PROM_URL/api/v1/query_range" \
  --data-urlencode "query=$Q" \
  --data-urlencode "start=$START" \
  --data-urlencode "end=$END" \
  --data-urlencode "step=$STEP" \
  --data-urlencode 'stats=all' \
| jq '.data.stats.samples'
```

예상 출력 형태는 대략 이런 구조입니다(숫자는 환경에 따라 다릅니다).

```json
{
  "totalQueryableSamples": 1234567,
  "samplesRead": 234567,
  "peakSamples": 345678,
  "totalQueryableSamplesPerStep": [ ... ],
  "samplesReadPerStep": [ ... ]
}
```

per-step 통계는 `promql-per-step-stats` feature flag와 결합될 수 있고, 이는 API 문서에서 별도로 언급합니다.[^3]

운영에서는 per-step이 있으면 분석이 쉬워지지만, 그만큼 응답이 커지고 비용이 늘 수 있습니다. 업그레이드 리허설에서는 켜 볼 가치가 있지만, 상시 운영에 넣을지는 분리해서 판단하는 편이 낫습니다.

## 업그레이드 후: “쿼리가 성공했는가” 말고 “가드레일이 바뀌었는가”를 확인

3.15.0에서 range query/subquery 평가가 바로잡히면, 다음과 같은 변화가 나올 수 있습니다.

- 같은 대시보드/룰이 더 적은 `peakSamples`를 보고함
- `query.max-samples`에 걸리던 쿼리가 풀려서 성공함
- 쿼리 실패율이 떨어지는데, 동시에 전체 엔진의 samples read/load가 증가하거나 감소할 수 있음(조합 가능)

여기서 “성공률이 오른 것”은 좋은데, 성공으로 인해 실제 자원 사용이 늘었는지 같이 봐야 합니다.

### 내가 보는 핵심 지표(서버 레벨)

공식 API 문서에 엔진 메트릭 두 개가 명시되어 있습니다.[^3]

- `prometheus_engine_query_samples_total`
- `prometheus_engine_query_samples_read_total`

여기에 현실적으로는 latency/timeout/failure도 같이 봐야 합니다. Prometheus 쿼리 엔진 관련 메트릭은 더 많지만, 최소한 이 두 카운터만으로도 “업그레이드 전후의 쿼리 비용 방향”은 잡힙니다.

### 쿼리 단위 비교(이게 없으면 결론이 안 난다)

서버 레벨 카운터는 전체 트래픽의 합이라, 어떤 쿼리가 변화를 만들었는지 추적하기 어렵습니다. 그래서 upgrade rehearsal에서는 반드시 “중요 쿼리 묶음”을 뽑고, 그 쿼리들을 구버전/신버전에 동일하게 재생해서 `stats=all`을 비교해야 합니다.

아래는 그 비교를 자동화하는 현실적인 스크립트 예시입니다.

## (실행 가능한 예시) 두 Prometheus에 동일 쿼리 재생하고 stats 비교하기

Prometheus 업그레이드를 할 때 내가 선호하는 방식은 “새 버전을 옆에 띄우고, 읽기 트래픽만 미러링하거나 리플레이해서 비교”입니다. 쓰기 경로까지 미러링하는 건 보통 비용이 크고 리스크가 큽니다.

여기서는 “쿼리 리플레이”만 다룹니다.

### 파일 구성

- `queries.txt`: 한 줄에 하나의 PromQL(이름이 필요하면 prefix를 붙이거나 CSV로 바꿔도 됨)
- `prom_diff.py`: old/new Prometheus에 `query_range?stats=all`로 호출하고 samples/timings를 CSV로 떨굼

#### queries.txt

```text
sum by (job) (rate(prometheus_http_requests_total[5m]))
max_over_time(prometheus_engine_queries[5m])
# subquery가 포함된 예시(환경에 맞는 metric으로 바꾸는 편이 낫습니다)
sum_over_time(rate(prometheus_http_requests_total[5m])[30m:15s])
```

### requirements.txt

```text
requests==2.32.3
```

### prom_diff.py

```python
#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import os
import sys
import time

import requests

def rfc3339(ts: dt.datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts.astimezone(dt.timezone.utc).isoformat().replace('+00:00', 'Z')

def query_range(base_url: str, promql: str, start: str, end: str, step: str, timeout_s: int):
    url = base_url.rstrip('/') + '/api/v1/query_range'
    params = {
        'query': promql,
        'start': start,
        'end': end,
        'step': step,
        'stats': 'all',
    }
    r = requests.get(url, params=params, timeout=timeout_s)
    return r.status_code, r.json()

def pick_stats(resp_json: dict) -> dict:
    data = (resp_json or {}).get('data') or {}
    stats = data.get('stats') or {}
    samples = stats.get('samples') or {}
    timings = stats.get('timings') or {}

    # 없는 키는 None으로 두고 CSV에 남깁니다.
    return {
        'peakSamples': samples.get('peakSamples'),
        'totalQueryableSamples': samples.get('totalQueryableSamples'),
        'samplesRead': samples.get('samplesRead'),
        'evalTotalTime': timings.get('evalTotalTime'),
        'execQueueTime': timings.get('execQueueTime'),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--old', required=True, help='예: http://prom-old:9090')
    ap.add_argument('--new', required=True, help='예: http://prom-new:9090')
    ap.add_argument('--queries', required=True, help='queries.txt 경로')
    ap.add_argument('--start', required=False)
    ap.add_argument('--end', required=False)
    ap.add_argument('--range-minutes', type=int, default=60)
    ap.add_argument('--step', default='15s')
    ap.add_argument('--timeout', type=int, default=120)
    ap.add_argument('--out', default='prom-315-diff.csv')
    args = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    end = args.end or rfc3339(now)
    start = args.start or rfc3339(now - dt.timedelta(minutes=args.range_minutes))

    with open(args.queries, 'r', encoding='utf-8') as f:
        queries = []
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            queries.append(line)

    if not queries:
        print('no queries', file=sys.stderr)
        return 2

    fieldnames = [
        'query',
        'old_status', 'new_status',
        'old_peakSamples', 'new_peakSamples',
        'old_totalQueryableSamples', 'new_totalQueryableSamples',
        'old_samplesRead', 'new_samplesRead',
        'old_evalTotalTime', 'new_evalTotalTime',
        'old_execQueueTime', 'new_execQueueTime',
    ]

    with open(args.out, 'w', newline='', encoding='utf-8') as out:
        w = csv.DictWriter(out, fieldnames=fieldnames)
        w.writeheader()

        for q in queries:
            old_status, old_json = query_range(args.old, q, start, end, args.step, args.timeout)
            new_status, new_json = query_range(args.new, q, start, end, args.step, args.timeout)

            old_s = pick_stats(old_json) if old_status == 200 else {}
            new_s = pick_stats(new_json) if new_status == 200 else {}

            w.writerow({
                'query': q,
                'old_status': old_status,
                'new_status': new_status,
                'old_peakSamples': old_s.get('peakSamples'),
                'new_peakSamples': new_s.get('peakSamples'),
                'old_totalQueryableSamples': old_s.get('totalQueryableSamples'),
                'new_totalQueryableSamples': new_s.get('totalQueryableSamples'),
                'old_samplesRead': old_s.get('samplesRead'),
                'new_samplesRead': new_s.get('samplesRead'),
                'old_evalTotalTime': old_s.get('evalTotalTime'),
                'new_evalTotalTime': new_s.get('evalTotalTime'),
                'old_execQueueTime': old_s.get('execQueueTime'),
                'new_execQueueTime': new_s.get('execQueueTime'),
            })

    print(f'written: {args.out}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
```

### 실행

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

python prom_diff.py \
  --old http://prom-old:9090 \
  --new http://prom-new:9090 \
  --queries ./queries.txt \
  --range-minutes 180 \
  --step 15s \
  --out ./prom-315-diff.csv
```

결과 CSV를 보면 업그레이드 후에 `peakSamples`가 내려갔는지, `samplesRead`가 내려갔는지, 혹은 (더 위험한 케이스로) status가 `old!=200`에서 `new=200`으로 바뀐 쿼리가 무엇인지 바로 드러납니다.

특히 `old_status != 200` → `new_status == 200`이 된 쿼리는 “예전에는 limit/timeout 등으로 억제되던 쿼리”였을 가능성이 높고, 이게 바로 업그레이드 후 부하를 갑자기 만드는 트리거가 됩니다.

## 부하 테스트를 “대시보드 새로고침” 수준으로 끝내면 안 되는 이유

3.15.0의 PromQL 변경은 엔진이 불필요하게 더 평가하던 부분을 고치는 성격이라, 1회 실행에서 대체로 비용이 줄어드는 방향을 기대하게 됩니다. 그런데 운영에서 문제는 “동시성”과 “반복”입니다.

- 동시성: Grafana가 여러 패널을 병렬로 때리면 `--query.max-concurrency`에 걸리거나, 큐잉이 생기면서 latency가 변합니다. 이 플래그는 공식 문서에 존재합니다.[^4]
- 반복: 패널 refresh interval이 짧으면 같은 쿼리를 계속 실행합니다.

따라서 업그레이드 리허설에서는 “단일 쿼리의 stats 비교”와 “동시 부하에서의 거동(큐잉/timeout/limit)”을 분리해서 봐야 합니다.

### 간단한 동시 부하 재생(vegeta 예시)

`vegeta` 같은 도구로 `/api/v1/query_range`에 QPS를 주는 방식은 빠르게 경향을 보기에 좋습니다. 여기서는 예시만 적습니다.

```text
# targets.txt 예시 (query 파라미터는 URL encoding이 필요합니다)
GET http://prom-new:9090/api/v1/query_range?query=sum%20by%20(job)%20(rate(prometheus_http_requests_total%5B5m%5D))&start=2026-09-29T00:00:00Z&end=2026-09-29T01:00:07Z&step=15s&stats=all
```

```bash
vegeta attack -rate 10 -duration 2m -targets targets.txt | vegeta report -type=text
```

이 부하는 어디까지나 API 서버/쿼리 엔진/TSDB read path에만 압력을 줍니다. Grafana의 패널 조합(instant + range, 다양한 label cardinality 조합)을 제대로 재현하려면 targets를 여러 개로 늘려야 합니다.

이 작업을 하는 이유는 하나입니다. “업그레이드 후에 풀리는 쿼리(이전에는 실패하던 쿼리)”가 존재할 때, 그 쿼리가 동시성 상황에서 어떤 비용을 실제로 지불하는지를 확인해야 하기 때문입니다.

## 로그 레벨 마이그레이션: 사고를 막으려면 config에 명시적으로 박는 게 낫다

3.15.0의 로그 레벨 변화는 “기능이 늘었다”가 아니라 “제어면(control plane)이 바뀌었다”에 가깝습니다.

- `--log.level`을 계속 쓰면 당장 죽지는 않겠지만 deprecated이고, 도움말도 `runtime.log_level`로 옮기라고 말합니다.[^4]
- config 파일에 `runtime.log_level`을 넣으면 reload로도 레벨이 바뀝니다.[^7]

운영에서 가장 위험한 상태는 “기본값에 기대는 상태”입니다. `--log.level`과 `runtime.log_level`이 동시에 존재할 때 기본값 우선순위가 어떻게 되는지 모호해지기 쉽고, 템플릿 누락/리로드 타이밍에 따라 레벨이 미끄러질 수 있습니다.

그래서 내 결론은 단순합니다.

- config에 `runtime.log_level`을 **명시적으로** 넣는다
- `--log.level`은 제거할 수 있을 때 제거한다(다만 바로 못 빼는 배포 환경도 많으니, 제거 자체가 목표가 아니라 “기준을 config로 옮기는 것”이 목표다)

### prometheus.yml 예시

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

runtime:
  # debug/info/warn/error 중 하나
  log_level: info

rule_files:
  - /etc/prometheus/rules/*.yml

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ["localhost:9090"]
```

`runtime.log_level`의 의미(프로세스 로거의 최소 심각도, reload로 변경 가능)는 configuration 문서에 정의되어 있습니다.[^7]

### reload 경로도 함께 정리

`runtime.log_level`을 reload로 바꿀 수 있다는 말은, 곧 “reload 경로를 통제해야 한다”는 뜻입니다.

- SIGHUP로 reload
- 또는 `--web.enable-lifecycle`을 켠 뒤 `POST /-/reload`

이 reload 메커니즘은 configuration 문서와 management API 문서에 명시되어 있습니다.[^7]

여기서 운영 리스크는 “누가 /-/reload를 칠 수 있나”로도 번집니다. 이건 보안/권한 설계 영역이지만, 로그 레벨까지 바뀌는 시대에는 더 민감해집니다.

## 대시보드·알림 체크리스트: 쿼리/limit/로그 공백을 한 번에 잡기

체크리스트는 나열보다도 “무슨 실패를 막기 위한 항목인가”가 중요합니다. 3.15.0의 CHANGE를 기준으로 보면 실패는 세 가지였습니다.

1) 업그레이드 후 쿼리 비용이 변해 전체 부하가 흔들림
2) `query.max-samples` 가드레일의 실효가 바뀜(막히던 쿼리가 풀림)
3) 로그 레벨 제어면이 바뀌면서 로그 기반 관측이 끊김

아래 체크는 이 세 실패를 각각 막기 위한 최소 셋입니다.

### 1) 쿼리 비용 폭증을 잡는 체크

- (사전) 중요 쿼리 목록을 `stats=all`로 수집하고, 업그레이드 후 동일 조건으로 재수집해서 `samplesRead`, `peakSamples`, `evalTotalTime`를 비교
  - `stats=all`의 필드 의미는 API 문서의 Query statistics 섹션을 기준으로 본다.[^3]
- (사후) 엔진 카운터의 기울기(분당 증가량)가 바뀌었는지 확인
  - API 문서에 명시된 `prometheus_engine_query_samples_total`, `prometheus_engine_query_samples_read_total`를 최소로 둔다.[^3]

여기서 중요한 건 “업그레이드가 비용을 줄였는가”보다 “비용 패턴이 바뀌었는가”입니다. 줄어도 문제고 늘어도 문제입니다. 줄었다면 limit 정책이 느슨해져서 더 많은 쿼리가 살아날 수 있고, 늘었다면 그대로 장애로 갑니다.

### 2) limit 차단의 의미 변화를 잡는 체크

- (사전) `query.max-samples`에 걸려 실패하던 쿼리의 목록을 확보
  - UI에서 보이던 에러/로그만으로는 놓칠 수 있으니, 업그레이드 리허설에서 “실패→성공 전환 쿼리”를 CSV로 뽑는 게 빠르다
- (사후) 실패율이 줄어든 것이 “좋아진 것”인지 “가드레일이 풀린 것”인지 구분
  - 위에서 만든 `prom_diff.py` 같은 리플레이가 실용적이다

이 체크의 목적은 한 문장으로 정리됩니다. **막혀 있던 쿼리가 풀리면서 부하가 늘어나는 시나리오**를 업그레이드 전에 발견하는 것입니다.[^1]

### 3) 로그 레벨 변경으로 인한 관측 공백을 잡는 체크

- (사전) 현재 배포에서 로그 레벨이 어디서 결정되는지(플래그 vs config)를 명확히 한 뒤, config에 `runtime.log_level`을 명시
  - `--log.level`이 deprecated라는 사실과 대체 경로는 command-line 문서에 적혀 있습니다.[^4]
  - `runtime.log_level`이 reload 가능하다는 사실은 configuration 문서에 적혀 있습니다.[^7]
- (사후) config reload 실패를 “로그가 아니라 메트릭/상태 API”로 본다
  - Prometheus mixin의 alert rule도 `prometheus_config_last_reload_successful`를 기준으로 `PrometheusBadConfig`를 정의합니다.[^10]
  - 또한 `/api/v1/status/config` 응답에 `reloadConfigSuccess`, `lastConfigTime` 같은 필드가 포함되는 예시가 API 문서에 있습니다.[^3]

로그 기반으로 reload 성공 여부를 감지하던 시스템은, log level이 내려가는 순간 침묵합니다. 이 침묵은 장애 때 가장 치명적입니다. 반면 `prometheus_config_last_reload_successful` 같은 신호는 log level과 무관하게 남습니다.

## 회의론: 이 정도 CHANGE가 실제로 장애를 만들까

이런 종류의 CHANGE는 보통 “버그 픽스인데 장애가 나겠냐”로 정리되기 쉽습니다. 내 경험상 실제 장애를 만드는 지점은 결과값 변화가 아니라, 비용/실패 모드가 바뀌는 순간입니다.

- range query의 평가 범위가 깔끔해지면 비용이 내려가고, 그래서 더 많은 쿼리가 성공한다
- 성공하는 쿼리는 결국 자원을 쓴다
- 자원을 쓰는 쿼리는 동시성에서 서로 간섭한다

그리고 로그 레벨 제어면 변경은 기능 추가처럼 보이지만, config reload가 곧 운영 제어plane인 조직에서는 “작은 config 변경이 로그를 끊어버리는 사건”으로 이어질 수 있습니다. PR 설명에서 “reload 실패 시 HTTP 500, 이전 로그 레벨 유지”처럼 안전장치를 넣은 이유 자체가 운영 이슈를 인지했기 때문입니다.[^8]

결국 3.15.0 업그레이드는 PromQL 문법 변화보다도 “Prometheus를 운영하는 방식”을 바꾸는 쪽에 더 가깝습니다.

## 결론: 3.15.0은 쿼리 가드레일과 로그 운영을 다시 정의한다

Prometheus 3.15.0의 `CHANGE`는 겉으로는 작은 문장 두세 줄이지만, 운영에서는 다음 두 가지를 강하게 요구합니다.

- 쿼리 비용을 결과값이 아니라 `stats=all`/엔진 카운터로 계측하고, 업그레이드 전후를 쿼리 단위로 비교해야 한다
- 로그 레벨은 `--log.level`에서 `runtime.log_level`로 기준을 옮기고, config reload 경로를 관측 공백 없이 통제해야 한다

3.15.0은 쿼리 엔진의 불필요한 평가를 줄이는 방향으로 개선하면서도, 그 개선이 우연히 유지되던 가드레일을 느슨하게 만들 수 있고, 동시에 로그 레벨의 control plane을 재배치합니다. 업그레이드 자체는 권장되는 변화지만, 안전한 업그레이드는 “버전만 올리는 일”이 아니라 “운영 기준선을 다시 그리는 일”로 끝나야 합니다.[^1]

## 참고 자료

- [Prometheus 3.15.0 릴리스 노트](https://github.com/prometheus/prometheus/releases/tag/v3.15.0)
- [Prometheus command-line flags 문서](https://prometheus.io/docs/prometheus/latest/command-line/prometheus/)
- [Prometheus configuration 문서](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [Prometheus Management API 문서](https://prometheus.io/docs/prometheus/latest/management_api/)
- [Prometheus HTTP API 문서(query_range, stats, Query statistics)](https://github.com/prometheus/prometheus/blob/main/docs/querying/api.md)
- [config: make log level reloadable PR #19511](https://github.com/prometheus/prometheus/pull/19511)
- [Prometheus feature flags 문서(use-start-timestamps)](https://prometheus.io/docs/prometheus/latest/feature_flags/)
- [Prometheus API stability guarantees](https://prometheus.io/docs/prometheus/3.15/stability/)
- [Prometheus query log 가이드](https://next.prometheus.io/docs/guides/query-log/)
- [Prometheus mixin alerts 정의(PrometheusBadConfig)](https://github.com/prometheus/prometheus/blob/main/documentation/prometheus-mixin/alerts.libsonnet)

[^1]: <https://github.com/prometheus/prometheus/releases/tag/v3.15.0>
[^2]: <https://prometheus.io/docs/prometheus/3.15/stability/>
[^3]: <https://github.com/prometheus/prometheus/blob/main/docs/querying/api.md>
[^4]: <https://prometheus.io/docs/prometheus/latest/command-line/prometheus/>
[^5]: <https://prometheus.io/docs/prometheus/latest/feature_flags/>
[^6]: <https://github.com/prometheus/prometheus/blob/main/promql/functions.go>
[^7]: <https://prometheus.io/docs/prometheus/latest/configuration/configuration/>
[^8]: <https://github.com/prometheus/prometheus/pull/19511>
[^9]: <https://next.prometheus.io/docs/guides/query-log/>
[^10]: <https://github.com/prometheus/prometheus/blob/main/documentation/prometheus-mixin/alerts.libsonnet>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
