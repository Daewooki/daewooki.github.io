---
title: "Copilot MAI Code 2 Flash 장애와 업스트림 전파"
description: "모델 선택과 자동 라우팅이 들어온 뒤, 업스트림 모델 제공자 장애가 Copilot·IDE·에이전트로 전파되는 방식을 설계 관점에서 정리합니다."
date: 2026-11-19 15:22:35 +0900
categories: ["News", "Tools"]
tags: ["github-copilot", "statuspage", "incident-response", "model-routing", "governance", "agent-harness"]
render_with_liquid: false
---

## 34분짜리 모델 가용성 저하: 무엇이 깨졌나

2026-11-18에 GitHub Copilot에서 **MAI Code 2 Flash**의 가용성 저하가 발생했습니다. GitHub Status API의 `incidents.json` 기준으로 사건의 시작과 종료는 다음처럼 기록되어 있습니다.

- Incident: `Degraded Availability for MAI Code 2 Flash in Copilot` (id: `891rm8181xdf`)
- Impact: `minor`
- Affected component: `Copilot AI Model Providers`
- Started: 2026-11-18 09:00:12 UTC
- Resolved: 2026-11-18 09:34:15 UTC
- Duration: 약 34분

Status API 타임라인을 KST(UTC+9)로 환산하면 2026-11-18 18:00:12~18:34:15 KST 구간입니다. (오늘이 2026-11-19 KST라는 전제에서, 사건은 어제 KST 저녁에 해당합니다.)  
GitHub Status의 incident update에는 원인이 명확히 적혀 있습니다.

- 09:00:42 UTC 업데이트에서 “upstream model provider 이슈”로 인해 MAI Code 2 Flash 모델 가용성이 저하되었고, 완화 전까지 “다른 모델 선택 또는 Copilot Fusion 선택”을 권고했습니다. 이후 09:13 UTC 무렵 개선, 09:34 UTC 무렵 upstream 이슈 해결 및 복구로 마무리됩니다.[^1]

여기서 중요한 지점은 장애 설명이 Copilot 서버 자체의 단일 장애라기보다, Copilot이 붙어 있는 외부 모델 제공 레이어의 장애로 분류되어 있고, 그에 맞는 사용자 행동(모델 전환, Fusion)이 즉시 안내된다는 점입니다.[^2]

그리고 이 사건이 더 흥미로운 이유가 하나 더 있습니다. MAI Code 2 / MAI Code 2 Flash는 GitHub Copilot에 2026-11-17에 추가된 신모델입니다. 신모델 추가 직후(다음 날)에 그 모델 단위로 장애가 공지된 셈입니다. 물론 “신모델이라서 장애가 났다”는 인과는 이 데이터만으로 말할 수 없지만, 제품이 점점 더 빠르게 모델을 추가하고(그리고 교체하는) 방향으로 가는 건 확실합니다.[^3]

## Copilot AI Model Providers: 모델 단위 장애를 분리해 공지하려는 의도

GitHub은 2026-04-17에 상태 페이지를 개편하면서, Copilot의 모델 제공 관련 이슈를 더 잘 드러내기 위해 `Copilot AI Model Providers`라는 전용 컴포넌트를 추가했다고 밝혔습니다. 모델 가용성 사건은 앞으로 `Copilot` 일반 컴포넌트가 아니라 이 컴포넌트 아래에서 보고하겠다는 방향입니다.[^4]

이 결정은 단순히 상태 페이지 UI를 바꾼 정도가 아니라, 제품 설계에서의 경계(boundary)를 바꿉니다.

- 예전에는 “Copilot이 느리다/안 된다”가 하나의 사건으로 뭉개지기 쉬웠습니다.
- 지금은 “Copilot이 제공하는 모델 풀 중 특정 모델 또는 특정 provider가 흔들렸다”를 구분해 운영하겠다는 뜻입니다.

이 전제가 성립하려면, Copilot이 실제로 멀티 벤더 모델을 제공하고 있어야 합니다. GitHub Docs의 supported models 표는 Copilot이 OpenAI, Anthropic, Google, Microsoft, Moonshot AI, xAI 등 여러 provider 모델을 지원한다고 명시합니다.[^5]

여기까지 오면 장애 전파의 기본 단위가 “서비스”가 아니라 “서비스가 선택/라우팅하는 업스트림 모델”이 됩니다. 오늘 사건 제목 자체가 그 단위 변경을 노골적으로 드러냅니다.

## 모델 선택 UI가 생기는 순간: 의존성이 사용자 경험으로 노출된다

모델 선택은 기술적으로는 routing 레이어의 도입인데, 제품적으로는 책임 분배의 변화입니다.

GitHub Copilot 앱의 문서에는 사용자가 세션 중 언제든 모델을 바꾸고, Fusion을 켜거나 끌 수 있으며, Fusion이 켜져 있으면 Copilot이 작업별로 모델을 선택해 “execution patterns”로 여러 모델을 오케스트레이션한다고 설명합니다.[^6]

Copilot CLI도 구조가 유사합니다.

- `/model`로 현재 세션 모델을 바꿀 수 있고
- Copilot이 idle이면 즉시, 아니라면 “current turn completes” 이후에 적용된다고 명시합니다.[^7]

이 문구 하나가 장애 전파 UX에서 꽤 큰 의미를 가집니다.

- 모델 장애가 나면 사용자는 보통 “취소하고 다시 시도”를 합니다.
- 그런데 “모델 변경이 current turn 이후 적용”이면, 이미 불안정한 모델로 들어간 turn이 끝나야(혹은 타임아웃/취소돼야) 모델 변경이 적용됩니다.

문서가 말하는 동작을 그대로 받아들이면, 모델 장애 시점의 UX는 대개 다음처럼 갈립니다.

1) 지금 turn이 빨리 실패하면 → 모델 스위치가 즉시 의미가 생깁니다.
2) 지금 turn이 애매하게 오래 걸리면(대기/재시도/stream 끊김) → 모델 스위치는 사용자가 기대하는 즉시성이 나오지 않을 수 있습니다.

결국 “모델 선택 UI/자동 라우팅”이 있는 제품은, 장애를 감추는 대신 장애를 다루는 레버도 제공합니다. 오늘 GitHub의 가이드(다른 모델, Fusion)가 바로 그 레버를 전제로 나옵니다.[^2]

## 장애 시 사용자 가이드의 품질: 다른 모델 vs Copilot Fusion은 같은 말이 아니다

GitHub가 제시한 대응은 두 갈래입니다.

- “choose another model”
- “select Copilot Fusion”[^2]

겉으로는 둘 다 fallback이지만, 설계 관점에서는 서로 다른 실패 모델을 갖습니다.

### 다른 모델을 고르는 fallback: 결정권은 사용자에게, 결과는 세션에 고정

모델을 명시적으로 바꾸는 방식의 장점은 단순합니다.

- 무엇을 쓰는지 명확합니다(감사/재현/비용 추적이 상대적으로 쉽습니다).
- 특정 provider 장애를 피하기 위해 “다른 provider 모델”로 점프할 수 있습니다.

반대로 단점도 뚜렷합니다.

- 같은 프롬프트라도 모델별 출력 차이가 커서, 팀 표준 작업 흐름(예: 코드리뷰 코멘트 스타일, 리팩토링 규칙)을 맞추기 어려워집니다.
- 에이전트 작업은 turn이 길고, tool call이 많습니다. 모델을 바꾸면 작업 중간의 추론/계획 일관성이 깨질 수 있습니다.

그래서 실전에서는 “장애가 나면 다른 모델”이 항상 정답이 아니라, 어떤 유형의 작업인지에 따라 달라집니다. 내 경우 장시간 에이전트 작업(다중 파일 변경 + 테스트 실행)이 들어간 세션은, 중간에 모델을 바꾸기보다 세션을 새로 시작하고 작업 범위를 더 작게 쪼개는 쪽이 결과가 깔끔했습니다. (이건 Copilot 제품 전체라기보다, 일반적인 agent loop의 특성에 가깝습니다.)

### Copilot Fusion fallback: 모델 선택을 제품이 가져가고, 비용/정책/캐시로 최적화한다

Fusion은 “auto mode”의 변형이 아니라, GitHub 문서 표현대로 “orchestrating multiple models through execution patterns”입니다.[^8]

그리고 Fusion의 운영적 특성이 문서에 꽤 구체적으로 박혀 있습니다.

- Fusion 사용 시, 사용된 모델 각각에 대해 과금되며 별도의 Fusion surcharge는 없습니다.
- Fusion High/Max는 한 작업에 여러 모델을 쓸 수 있어 AI credits 소비가 늘 수 있습니다.
- Fusion은 메인 대화를 가능한 한 같은 모델에 유지해 cached tokens의 이점을 보려 하고, 보조 역할 모델은 필요한 컨텍스트만 받습니다.
- 실행 패턴과 모델 풀은 시간이 지나며 바뀔 수 있습니다.
- draft를 버리면 이미 워크스페이스에 반영된 변경은 자동으로 되돌리지 않습니다.
- subagents를 시작하지는 않습니다(별개로 동작).[^8]

이걸 장애 대응으로 번역하면, Fusion은 “당장 살아있는 모델을 알아서 고르는 스위치”가 아닙니다. 캐시, 비용, 정책, 컨텍스트 전달량을 포함한 runtime 전략입니다.

즉, 오늘 같은 “특정 모델(=MAI Code 2 Flash)만 불안정” 사건에서는 Fusion이 꽤 합리적일 수 있습니다.

- 사용자가 MAI Code 2 Flash를 꼭 고집할 이유가 없으면, Fusion이 다른 모델로 우회할 여지가 생깁니다.
- 다만 Fusion이 어떤 모델을 선택할지, 선택이 왜 그렇게 됐는지는 사용자가 100% 통제하지 못합니다.

이 지점이 조직 정책 설계로 연결됩니다. 모델 선택을 개인의 UI 기능으로 풀어놓으면, 장애 때는 빨리 우회하겠지만 평상시에는 표준화가 깨집니다. 반대로 조직이 모델을 너무 꽉 쥐면, 장애 때는 우회가 막힙니다.

## 조직 차원의 IDE/에이전트 사용 정책: fallback/차단/관측을 어디에 심을까

Copilot이 멀티모델이 된 시점부터, “개발자 도구”는 사실상 작은 production dependency가 됩니다. 특히 VS Code의 에이전트 구조가 바뀌면서 이 성격이 더 강해졌습니다.

VS Code 팀은 2026-11-18에 Copilot harness가 Copilot SDK 기반으로 VS Code의 새 에이전트 세션 기본값이 되었고, Copilot CLI/ Copilot 앱 등 Copilot 제품군과 runtime을 공유한다고 밝혔습니다. Local harness는 deprecated이며 2027-02에 제거될 계획(전환 기간 존재)이라고도 적어 두었습니다.[^9]

runtime 공유의 의미는 간단합니다.

- 어떤 모델이든, 어떤 라우팅이든, 어떤 정책이든 “여러 클라이언트가 같은 실패 모드로 묶일” 가능성이 커집니다.
- 반대로 고쳐도 같이 고쳐집니다. 문제는 장애 대응에서는 이 결합도가 종종 리스크로 나타난다는 점입니다.

그래서 조직 정책은 최소 3개의 층으로 나누는 편이 운영이 쉽습니다.

### 1) 허용 모델 정책: 기본은 allowlist, 그리고 ‘신모델 자동 노출’을 통제

GitHub Docs에 따르면 엔터프라이즈는 모델별로 다음을 설정할 수 있습니다.

- 모든 사용자/agent app에 대해 Enabled
- 모든 사용자/agent app에 대해 Disabled
- 조직/enterprise team 및 앱으로 결정을 위임[^10]

여기서 놓치기 쉬운 함정이 “Default availability for released models”입니다.

- GA 모델 중 엔터프라이즈에서 아직 설정하지 않은 모델은 “Delegate to Default Policy”로 표시될 수 있고
- Default availability 정책이 Enabled이면 새 모델이 자동으로 조직 전체에 풀릴 수 있습니다.[^10]

MAI Code 2 Flash는 2026-11-17에 Copilot에 추가된 모델이고, 그 다음날 모델 단위 가용성 저하가 공지됐습니다.[^3]

이 조합은 운영자 관점에서 메시지가 분명합니다.

- 모델은 앞으로도 자주 추가될 것이고
- 모델은 곧바로 조직 사용자 경험(IDE/모바일/CLI/클라우드 에이전트)에 노출될 수 있으며
- 노출된 모델은 곧바로 장애 단위가 될 수 있습니다.

내 경우라면 “Default availability를 Disabled로 두고, 신모델은 최소 1주일 관찰 + 비용/데이터 정책 검토 후 enable” 쪽으로 기웁니다. 모든 조직에 동일한 강도로 적용하기 어렵다면, 문서가 제공하는 targeted model rules(특정 조직만 허용)로 롤아웃 폭을 조절하는 식이 현실적입니다.[^10]

### 2) Fusion 정책: Fusion을 켜는 것과 Fusion이 쓸 모델 풀은 분리된다

Fusion은 켜고 끄는 토글 같지만, 엔터프라이즈 문서상으로는 “Fusion이 사용할 모델 풀”을 별도로 구성할 수 있습니다.[^10]

또한 Fusion은 관리자 정책을 강하게 탑니다.

- plan에서 사용할 수 없는 모델
- 관리자 정책으로 제외된 모델
- data-resident / FedRAMP 정책에 의해 제외되는 모델
- evaluation models 정책에 의해 제외되는 모델[^8]

즉 장애 대응 관점에서 Fusion을 “만능 자동 우회”로 기대하면 곤란합니다. 조직이 정책으로 모델 풀을 좁혀 두면, 장애 시 우회로도 같이 좁아집니다. 그 자체는 나쁜 게 아니고, 의도한 보안/컴플라이언스 경계일 수 있습니다.

문제는 그 경계를 설계할 때 장애를 함께 고려하느냐입니다. 보안/컴플라이언스 정책과 장애 정책은 결국 같은 라우팅 테이블을 공유합니다.

### 3) 에이전트/IDE 표준 사용 계약: ‘우회’를 허용하는 대신, 기록을 남기게 만든다

모델 우회가 허용된 조직은 보통 다음 질문이 바로 옵니다.

- 장애 때 누가 어떤 모델로 우회했는가
- 비용이 얼마나 튀었는가
- 결과(코드 변경)가 어느 세션에서 생성됐는가

이건 툴 기능만으로는 다 해결이 안 되고, 운영 계약이 됩니다. 예전에 정리했던 “에이전트 PR 운영 계약”이나, 에이전트/CLI의 장애 전파 경로를 다룬 글이 이 지점에서 연결됩니다.

- [Copilot Cloud agent sessions 장애가 드러낸 에이전트 IDE/CLI의 장애 전파 경로](https://daewooki.github.io/posts/copilot-agent-sessions-failure-propagation/)
- [Octoverse 2026이 굳힌 에이전트 PR 운영 계약](https://daewooki.github.io/posts/octoverse-2026-agent-pr-contract/)

핵심은 단순합니다.

- 장애 시 우회는 허용하되
- 우회는 관측 가능해야 하고
- 관측은 개인의 선의가 아니라 기본값이어야 합니다.

## 관측을 제품 밖으로 끌어내기: Status API를 내부 신호로 만드는 방법

GitHub Status는 Atlassian Statuspage 기반이고, public status API로 `api/v2/incidents.json`, `api/v2/summary.json`, `api/v2/components.json` 같은 엔드포인트를 제공합니다.[^1]

또한 Statuspage는 웹훅 알림 자체를 지원합니다(incident 업데이트나 component 상태 변화 시 POST). 다만 이건 “해당 Statuspage에서 웹훅 구독을 열어뒀는지” 여부가 실제 수신 가능성을 좌우합니다. Statuspage 기능 스펙으로는 웹훅의 응답 제한(30초, 2xx 요구) 같은 운영 제약도 명시되어 있습니다.[^11]

나는 status 페이지를 “참고용 웹사이트”로만 두지 않고, 내부 ChatOps/온콜 시스템이 소비하는 신호로 취급하는 편이 낫다고 봅니다. 특히 오늘 사건처럼 component가 `Copilot AI Model Providers`로 분리된 이후에는, “GitHub 전체 장애”와 “특정 모델 provider 장애”를 분리해 알릴 수 있습니다.[^4]

아래는 `incidents.json`을 폴링해서, `Copilot AI Model Providers` 컴포넌트의 incident 업데이트를 Slack Incoming Webhook으로 전달하는 최소 구현입니다.

### 실행 가능한 예시 코드: Copilot 모델 장애 감시 봇

#### 1) 의존성과 실행

- Python: 3.11+ (예시는 3.12 기준)
- 패키지: `requests`

```bash
python -m venv .venv
source .venv/bin/activate
pip install requests==2.32.3

export SLACK_WEBHOOK_URL='https://hooks.slack.com/services/...'
python copilot_status_watch.py --once
```

#### 2) 코드

```python
# copilot_status_watch.py
# Python 3.11+

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

GITHUB_STATUS_INCIDENTS_URL = "https://www.githubstatus.com/api/v2/incidents.json"

STATE_FILE_DEFAULT = ".copilot-status-state.json"
TARGET_COMPONENT_NAME = "Copilot AI Model Providers"

@dataclass(frozen=True)
class IncidentEvent:
    incident_id: str
    incident_name: str
    incident_status: str
    incident_impact: str
    updated_at: str
    url: str
    latest_update_status: str | None
    latest_update_body: str | None

def http_get_json(url: str, timeout_sec: int = 10) -> dict[str, Any]:
    r = requests.get(url, timeout=timeout_sec)
    r.raise_for_status()
    return r.json()

def load_state(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"last_seen_incident_update_at": None}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(path: str, state: dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def parse_iso8601(ts: str) -> datetime:
    # examples: 2026-11-18T09:34:15.907Z
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)

def incident_affects_target_component(incident: dict[str, Any]) -> bool:
    # incidents.json includes incident_updates[].affected_components but not always per update.
    # We'll check the top-level components list under incident.
    for c in incident.get("components", []):
        if c.get("name") == TARGET_COMPONENT_NAME:
            return True
    # fallback: scan updates
    for u in incident.get("incident_updates", []):
        for ac in u.get("affected_components", []):
            if ac.get("name") == TARGET_COMPONENT_NAME:
                return True
    return False

def extract_latest_update(incident: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    updates = incident.get("incident_updates", [])
    if not updates:
        return None, None, None
    # API order is newest-first on some pages, but do not assume. Sort by created_at.
    updates_sorted = sorted(updates, key=lambda u: parse_iso8601(u["created_at"]))
    latest = updates_sorted[-1]
    return latest.get("created_at"), latest.get("status"), latest.get("body")

def find_relevant_events(payload: dict[str, Any]) -> list[IncidentEvent]:
    events: list[IncidentEvent] = []

    for inc in payload.get("incidents", []):
        if not incident_affects_target_component(inc):
            continue

        latest_created_at, latest_status, latest_body = extract_latest_update(inc)

        events.append(
            IncidentEvent(
                incident_id=inc["id"],
                incident_name=inc.get("name", ""),
                incident_status=inc.get("status", ""),
                incident_impact=inc.get("impact", ""),
                updated_at=inc.get("updated_at", ""),
                url=inc.get("shortlink") or inc.get("url") or "https://www.githubstatus.com/",
                latest_update_status=latest_status,
                latest_update_body=latest_body,
            )
        )

    # newest first by updated_at
    return sorted(events, key=lambda e: parse_iso8601(e.updated_at), reverse=True)

def post_to_slack(webhook_url: str, text: str) -> None:
    r = requests.post(webhook_url, json={"text": text}, timeout=10)
    r.raise_for_status()

def render_event_message(e: IncidentEvent) -> str:
    return (
        f"[GitHub Status] {TARGET_COMPONENT_NAME}\n"
        f"- incident: {e.incident_name} ({e.incident_id})\n"
        f"- status: {e.incident_status} / impact: {e.incident_impact}\n"
        f"- updated_at: {e.updated_at}\n"
        f"- link: {e.url}\n"
        + (f"- latest_update: {e.latest_update_status}\n" if e.latest_update_status else "")
        + (f"- note: {truncate(e.latest_update_body, 400)}\n" if e.latest_update_body else "")
    )

def truncate(s: str, n: int) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    if len(s) <= n:
        return s
    return s[: n - 3] + "..."

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=STATE_FILE_DEFAULT)
    ap.add_argument("--once", action="store_true", help="run once and exit")
    ap.add_argument("--interval-sec", type=int, default=60)
    ap.add_argument("--slack", action="store_true", help="send to Slack via SLACK_WEBHOOK_URL")

    args = ap.parse_args()

    slack_url = os.environ.get("SLACK_WEBHOOK_URL")
    if args.slack and not slack_url:
        print("SLACK_WEBHOOK_URL is required when --slack is set", file=sys.stderr)
        return 2

    state = load_state(args.state_file)
    last_seen = state.get("last_seen_incident_update_at")
    last_seen_dt = parse_iso8601(last_seen) if last_seen else None

    while True:
        payload = http_get_json(GITHUB_STATUS_INCIDENTS_URL)
        events = find_relevant_events(payload)

        if not events:
            print(f"No incidents affecting {TARGET_COMPONENT_NAME} found.")
        else:
            newest = events[0]
            newest_dt = parse_iso8601(newest.updated_at)

            should_notify = (last_seen_dt is None) or (newest_dt > last_seen_dt)

            msg = render_event_message(newest)
            print(msg)

            if should_notify and args.slack:
                post_to_slack(slack_url, msg)

            # update state regardless; this script is about notifications, not retention
            state["last_seen_incident_update_at"] = newest.updated_at
            save_state(args.state_file, state)

        if args.once:
            return 0
        time.sleep(args.interval_sec)

if __name__ == "__main__":
    raise SystemExit(main())
```

#### 3) 예상 출력 예시

(실행 시점에 따라 달라지며, 아래는 형태 예시입니다.)

```text
[GitHub Status] Copilot AI Model Providers
- incident: Degraded Availability for MAI Code 2 Flash in Copilot (891rm8181xdf)
- status: resolved / impact: minor
- updated_at: 2026-11-18T09:34:15.907Z
- link: https://stspg.io/3sbmvyy2ctyx
- latest_update: resolved
- note: This incident has been resolved. Thank you for your patience and understanding as we addressed this issue. A detailed root cause analysis will be shared as soon as it is available.
```

이 정도만 붙여도, “개발자가 체감으로 느린 것”이 아니라 “공식 incident 신호로 모델 provider 레이어가 흔들린 것”을 내부에서 동일한 언어로 재현할 수 있습니다.

## 장애 대응을 제품 동작과 맞추는 방법: CLI는 비교적 명확한 우회로가 있다

IDE 내부의 Copilot 모델 스위치는 UI/세션 상태에 묶여 있어서 자동화가 까다롭지만, Copilot CLI는 문서에 “programmatic control”이 꽤 명확히 나와 있습니다.

- `COPILOT_MODEL` 환경변수로 모델을 지정할 수 있고
- `--model` 옵션으로 단발 실행에 모델을 지정할 수 있고
- `fusion`을 모델로 쓰면서 `--fusion-tier standard|high|max`로 effort level을 선택할 수 있습니다.
- 영구 설정은 `~/.copilot/settings.json`의 `model` 키로 저장할 수 있습니다.[^12]

이건 곧 “장애 시 우회를 셸 레벨에서 강제할 수 있다”는 뜻입니다.

예를 들어, 상태 페이지에 특정 모델 장애 incident가 떠 있으면 일시적으로 Fusion Standard로 몰아버리는 wrapper를 만들 수 있습니다.

```bash
# copilot-safe.sh
# 상태 신호에 따라 COPILOT_MODEL을 강제하는 초간단 예시(컨셉)

set -euo pipefail

python copilot_status_watch.py --once >/tmp/copilot-status.txt

if grep -q "MAI Code 2 Flash" /tmp/copilot-status.txt && grep -q "status: investigating\|status: identified\|status: monitoring" /tmp/copilot-status.txt; then
  echo "Detected MAI Code 2 Flash incident. Falling back to Fusion Standard." >&2
  exec copilot --model fusion --fusion-tier standard "$@"
else
  exec copilot "$@"
fi
```

이 방식은 완벽하지 않습니다.

- incident 텍스트 파싱은 취약합니다(정석은 `incidents.json`을 파싱해 상태를 보아야 합니다).
- 엔터프라이즈 정책이 Fusion을 제한할 수 있습니다.
- 무엇보다 IDE 쪽은 별도 제어가 필요합니다.

그럼에도 “업스트림 모델 제공자 장애”가 반복될 패턴이라면, 최소한 CLI/자동화 구간부터 우회 레버를 갖는 건 비용 대비 효과가 큽니다. Copilot CLI 문서가 아예 CI/CD, automation workflow를 전제로 쓰여 있다는 점도 힌트입니다.[^12]

## 회의론: 자동으로 다 해주면 되지 않나, 왜 사용자가 모델을 알아야 하나

이 주제에서 자주 나오는 반론은 두 갈래입니다.

1) 사용자는 모델을 모르고 싶다. Copilot이 알아서 fallback해라.
2) 34분짜리 minor incident면 무시해도 된다.

첫 번째는 절반만 맞습니다. Fusion 같은 기능이 그 방향(자동 라우팅)을 강화하고 있고, GitHub도 실제 incident 중에 Fusion을 우회로로 안내했습니다.[^2]

다만 “자동 fallback”이 항상 좋은 사용자 경험으로 끝나지 않는 이유가 있습니다.

- 비용: Fusion High/Max는 복수 모델 사용으로 AI credits 소모가 늘 수 있습니다.[^8]
- 정책: data residency / FedRAMP 같은 제한이 있으면 자동 fallback 풀은 좁아집니다.[^8]
- 재현성/감사: 특정 PR/커밋이 어떤 모델 조합으로 만들어졌는지 조직이 추적해야 하는 순간이 옵니다.
- 운영 리스크: Fusion은 실행 패턴/모델 풀이 바뀔 수 있고, draft discard 시 워크스페이스 변경이 자동 롤백되지 않는 제약도 있습니다.[^8]

두 번째(34분이면 무시)는, IDE가 “대화형 보조 도구”일 때는 맞았는데, 에이전트가 “비동기 작업자”가 되면서 점점 틀려집니다.

VS Code는 Agent Host를 도입해 세션을 editor window 밖에서 지속시키는 방향으로 가고, Copilot harness를 shared runtime으로 묶어서 Copilot 제품군 전체에 같은 에이전트 실행 기반을 쓰고 있습니다.[^13]

이 구조에서는 30분 장애가 단순히 타이핑 지연이 아니라,

- 백그라운드에서 돌던 에이전트 작업이 멈추거나
- 툴 실행이 중간에 끊기고
- 재시도가 폭증해 비용과 rate limit을 밀어 올리며
- 작업 결과가 시간 의존적으로 흔들리는

식으로 번질 수 있습니다. 장애의 절대 시간보다 “어떤 작업이 그 시간에 걸려 있었는지”가 중요해집니다.

## 앞으로 반복될 패턴: 지켜볼 것

이번 사건에서 내가 가져가는 핵심은 “MAI Code 2 Flash가 한 번 흔들렸다”가 아닙니다. 멀티모델/멀티provider 시대의 고장 패턴이, 제품의 기능(모델 선택 UI, Fusion, shared harness, 정책 엔진)을 통해 어떤 형태로 사용자/조직에 전파되는지를 한 번에 보여줬다는 점입니다.

특히 체크 포인트는 다음입니다.

- Status incident update에는 “상세 RCA를 가능한 빨리 공유하겠다”가 적혀 있습니다. 이런 유형의 사건은 RCA에서 재발 방지책이 어떤 레이어(업스트림 provider, Copilot 라우터, 캐시/큐잉, 클라이언트 재시도)에 걸리는지에 따라, 조직이 설계해야 할 fallback 위치가 달라집니다.[^1]
- GitHub은 이미 모델 provider 가용성을 별도 컴포넌트로 분리했습니다. 다음 단계는 모델별/벤더별 신호를 더 세분화하는지, 혹은 Copilot Fusion 같은 라우팅 레이어의 상태를 별도로 드러내는지입니다.[^4]
- VS Code는 Copilot harness를 default로 굳히는 중이고 Local harness 제거 시점을 2027-02로 잡았습니다. 로컬 대체 경로(예: 로컬 모델, 오프라인 작업)를 조직이 어디까지 표준으로 인정할지, 지금부터 정리해야 뒤가 편합니다.[^9]

결론적으로, Copilot을 포함한 IDE/에이전트 도구는 이제 “모델을 붙여 쓰는 UI”가 아니라, 모델 라우팅·정책·비용·장애를 함께 먹는 runtime입니다. 업스트림 모델 제공자 의존이 생기는 순간부터 장애는 제품 밖에서 시작해 제품 안으로 전파되고, 그 전파는 모델 선택 UI와 자동 라우팅 기능을 통해 사용자와 조직의 설계 문제로 바뀝니다.

## 참고 자료

- [GitHub Status API: incidents.json](https://www.githubstatus.com/api/v2/incidents.json)
- [GitHub Community Incident Thread #213428](https://github.com/orgs/community/discussions/213428)
- [Bringing more transparency to GitHub’s status page](https://github.blog/news-insights/company-news/bringing-more-transparency-to-githubs-status-page/)
- [MAI Code 2 and MAI Code 2 Flash in GitHub Copilot (GitHub Changelog)](https://github.blog/changelog/2026-11-17-mai-code-2-and-mai-code-2-flash-in-github-copilot/)
- [Supported AI models in GitHub Copilot (GitHub Docs)](https://docs.github.com/en/copilot/reference/ai-models/supported-models)
- [Choosing a model in the Copilot app (GitHub Docs)](https://docs.github.com/en/copilot/how-tos/github-copilot-app/choose-a-model)
- [About GitHub Copilot Fusion (GitHub Docs)](https://docs.github.com/en/copilot/concepts/models/copilot-fusion)
- [Managing availability of models in your enterprise (GitHub Docs)](https://docs.github.com/en/copilot/how-tos/administer-copilot/manage-for-enterprise/manage-availability-of-default-models)
- [About default availability of Copilot features and models (GitHub Docs)](https://docs.github.com/en/copilot/concepts/enterprise/default-availability)
- [GitHub Copilot CLI programmatic reference (GitHub Docs)](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference)
- [Choosing a model in GitHub Copilot CLI (GitHub Docs)](https://docs.github.com/en/enterprise-cloud@latest/copilot/how-tos/copilot-cli/use-copilot-cli/choose-a-model)
- [The Copilot harness: Building on a shared foundation (VS Code Blog)](https://code.visualstudio.com/blogs/2026/11/18/copilot-harness)
- [Introducing the Agent Host for persistent, portable agent sessions (VS Code Blog)](https://code.visualstudio.com/blogs/2026/08/26/agent-host-architecture/)
- [Atlassian Status API documentation](https://status.atlassian.com/api)
- [Enable webhook notifications (Atlassian Statuspage Support)](https://support.atlassian.com/statuspage/docs/enable-webhook-notifications/)
- [MAI Code 2 and MAI Code 2 Flash Model Card (Microsoft PDF)](https://microsoft.ai/pdf/MAI-Code-2-And-MAI-Code-2-Flash-Model-Card.pdf)
- [Copilot Cloud agent sessions 장애가 드러낸 에이전트 IDE/CLI의 장애 전파 경로](https://daewooki.github.io/posts/copilot-agent-sessions-failure-propagation/)
- [Octoverse 2026이 굳힌 에이전트 PR 운영 계약](https://daewooki.github.io/posts/octoverse-2026-agent-pr-contract/)

[^1]: <https://www.githubstatus.com/api/v2/incidents.json>
[^2]: <https://github.com/orgs/community/discussions/213428>
[^3]: <https://github.blog/changelog/2026-11-17-mai-code-2-and-mai-code-2-flash-in-github-copilot/>
[^4]: <https://github.blog/news-insights/company-news/bringing-more-transparency-to-githubs-status-page/?trk=article-ssr-frontend-pulse_little-text-block>
[^5]: <https://docs.github.com/en/copilot/reference/ai-models/supported-models>
[^6]: <https://docs.github.com/en/copilot/how-tos/github-copilot-app/choose-a-model>
[^7]: <https://docs.github.com/en/enterprise-cloud@latest/copilot/how-tos/copilot-cli/use-copilot-cli/choose-a-model>
[^8]: <https://docs.github.com/en/copilot/concepts/models/copilot-fusion>
[^9]: <https://code.visualstudio.com/blogs/2026/11/18/copilot-harness>
[^10]: <https://docs.github.com/en/copilot/how-tos/administer-copilot/manage-for-enterprise/manage-availability-of-default-models>
[^11]: <https://support.atlassian.com/statuspage/docs/enable-webhook-notifications/>
[^12]: <https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference>
[^13]: <https://code.visualstudio.com/blogs/2026/08/26/agent-host-architecture/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
