---
title: "Chrome 157 Stable 승격 후 48시간 배포 리듬 재설계"
description: "2주 Stable 사이클에서 정책·확장·자동업데이트 이슈를 업데이트 링+강제 재시작+버전 진실로 흡수하는 운영 패턴."
date: 2026-11-06 12:04:17 +0900
categories: ["News", "Web"]
tags: ["chrome", "enterprise", "release-management", "patching", "policy", "extension-management"]
render_with_liquid: false
---

## Chrome 157 Stable 승격에서 확인해야 할 사실

2026-11-03(화) Chrome 157이 데스크톱 Stable 채널로 승격됐습니다. Chrome Releases 공지의 표기 기준으로는 2026-11-03이며, KST로는 시차 때문에 2026-11-04(수)로 보일 수 있지만, 운영 기준일은 공지에 찍힌 날짜를 쓰는 편이 혼선이 적습니다.[^1]

이번 승격에서 운영 관점으로 먼저 고정해야 하는 값은 3개입니다.

1) 플랫폼별 Stable 버전 문자열
- Linux: 157.0.8103.38
- Windows/Mac: 157.0.8103.38 / 157.0.8103.39

Chrome Releases 공지가 버전 범위를 이렇게 적어놓는 순간, 현장에선 “정답 버전이 2개”가 됩니다. 이걸 버그로 취급하면 배포 준수율 지표가 깨지고, 이걸 자연스럽게 받아들이면 버전 진실이 ‘범위’가 됩니다.[^1]

2) 보안 수정량
이번 데스크톱 Stable 업데이트는 “213 security fixes”로 공지됐습니다. 이 숫자 자체가 배포 압력을 만드는 트리거가 됩니다.[^1]

3) 롤아웃 방식
공지에 “roll out over the coming days/weeks”가 적혀 있습니다. 즉, 승격일=전사 동일 시점 배포가 아니라, 승격일 이후에도 구간별로 서로 다른 버전이 공존하는 것이 정상 상태입니다.[^1]

이 3개를 고정하지 않고 “157로 올리자”라고 말하면, 첫 48시간 동안은 대부분 커뮤니케이션/측정/판단이 어긋납니다.

## 2주 Stable 사이클이 링 설계를 망가뜨리는 지점

Chrome의 Stable이 2주 주기로 major milestone을 내보내는 흐름은 이미 문서로 박혀 있습니다.
- Chromium의 release_cycle 문서: Stable에 major milestone이 2주마다 나간다고 명시합니다.[^2]
- Chrome Enterprise 문서: Stable은 major releases가 2주마다라고 적어놓습니다.[^3]
- Chrome for Developers 블로그: 2026-09-08에 2주 사이클 시작(Chrome 153)과 Extended Stable의 포지션을 다시 못 박았습니다.[^4]

여기서 엔터프라이즈 배포 링이 깨지는 이유는 단순합니다.

- 과거: “Stable 승격 → 1주 파일럿 → 1주 확산” 같은 2주짜리 설계가 그럭저럭 말이 됐습니다.
- 지금: Stable major가 2주마다 나오면, 그 구조는 ‘다음 버전이 나오기 전에 겨우 끝나는’ 리듬이 됩니다.

이 상황에서 기존 링 설계는 두 가지로 분기합니다.

- 링을 유지하려면: 각 링의 검증 윈도우를 ‘일 단위’로 줄여야 합니다.
- 링을 유지하지 않으려면: Extended Stable(8주 major)로 일부를 보내야 합니다.

Extended Stable은 “2주 사이클을 수용할 수 없는 고객”을 위한 채널로 문서에 반복해서 등장합니다.[^5]

내 경우 이걸 ‘느린 채널’이라기보다는 “배포 리듬에서 예외를 수용하는 별도 레인”으로 봅니다. 느리게 가는 대신, 예외 레인의 입장 조건(업무 중요도/호환성/대체 브라우저/VDI 여부)을 엄격하게 정의하지 않으면 결국 Stable 링이 계속 뚫립니다.

이 주제는 예전 글에서 Stable 2주 릴리스가 링 운영을 어떻게 바꾸는지를 길게 정리한 적이 있어, 여기서는 반복하지 않고 결론만 씁니다.
- [Chrome Stable 2주 릴리스가 바꾸는 업데이트 운영](https://daewooki.github.io/posts/chrome-two-week-stable-ring-design/)

## 첫 48시간에 터지는 3종류 사고: 정책·확장·자동업데이트

Stable 승격 직후(특히 0~48시간)에 반복해서 터지는 패턴은 크게 3가지입니다. 이건 “이번 버전에 무슨 기능이 들어갔나”와 별개로, 배포 파이프라인이 가지고 있는 구조적 부채에서 나옵니다.

### 1) 정책 사고: 정책은 적용됐는데, 그 정책이 ‘언제부터/어디서’ 유효한지 다르다

정책은 다양한 경로로 내려갑니다(GPO, MDM, Chrome Enterprise Core 등). 그런데 Chromium Updater(Windows의 Google Update / macOS의 Google Software Update) 계열 정책은 “관리 상태”에 따라 존중 여부가 갈립니다.

Updater functional spec 문서에는 정책이 존중되는 조건을 “domain-joined”, Chrome Enterprise Core enrolled, macOS는 MDM managed 같은 형태로 적어놓습니다.[^6]

즉, 같은 레지스트리/플리스트 키가 있어도:
- 어떤 기기에서는 강하게 먹고
- 어떤 기기에서는 무시되며
- 어떤 기기에서는 “low-trust/unmanaged” 취급으로 제품 내부의 방어 로직이 다른 결과를 냅니다

정책 사고의 본질은 “정책 키가 존재하느냐”가 아니라, **정책 소스의 신뢰 등급**과 **적용 타이밍(재시작 필요 여부)**입니다.

### 2) 확장 사고: 확장 업데이트는 Chrome 앱 업데이트와 다른 세계선이다

확장(force-install 포함)은 운영자가 통제한다고 생각하기 쉬운데, 실제로는 정책/업데이트 URL/스토어 상태/사용자 프로필 상태가 겹칩니다.

- Chrome Enterprise Help 문서도 ExtensionSettings가 ExtensionInstallForcelist를 덮을 수 있고, update_url / override_update_url 같은 값이 어떻게 동작하는지 구체적으로 적고 있습니다.[^7]
- Chromium의 “Pre-installed Extensions” 문서도 정책 배포가 가장 스케일이 좋다고 하면서도, 레지스트리 기반 프리인스톨은 전혀 다른 키를 쓴다고 못 박습니다.[^8]

첫 48시간에 확장 사고가 터지는 이유는 대부분 다음 중 하나입니다.
- Stable이 올라가면서 확장 API/권한/정책 precedence가 바뀌었는데, 조직 내부 문서가 그걸 못 따라감
- 확장 업데이트가 지연되거나(스토어, 네트워크, 프록시), 특정 확장 버전과 Chrome 버전 조합이 깨짐
- “정책으로 깔려 있어야 하는 확장”이 특정 조건에서 제거되거나 비활성화됨

### 3) 자동업데이트 사고: 승격은 됐는데 내 PC는 아직 안 올라간다

Chrome Releases 공지는 승격 사실을 말할 뿐, 모든 PC가 같은 날 같은 빌드가 되는 것을 보장하지 않습니다(rollout).[^1]

여기서 운영이 꼬이는 지점은 2개입니다.

- ‘최신’의 정의가 흔들립니다. 최신이 “major 157”인지, “157.0.8103.39”인지, “CVE fix가 포함된 최소 버전 이상”인지가 섞입니다.
- 재시작 부채가 측정에서 사라집니다. 업데이트 파일은 받았는데 프로세스가 떠 있는 동안은 구버전이 계속 살아있고, 보안팀은 “패치 적용”을 묻는데 클라이언트는 “업데이트 완료”라고 착각합니다.

Google도 보안 관점에서 “사용자 재시작 대기 시간이 N-day risk의 큰 구성 요소”라고 언급합니다.[^9]

이 3종류 사고를 한 번에 흡수하는 운영 패턴이 ‘업데이트 링 + 강제 재시작 + 버전 진실(source of truth)’입니다.

## 운영 패턴 1: 업데이트 링을 ‘검증’이 아니라 ‘의사결정’으로 쪼갠다

2주 사이클에서 링을 “검증 시간 확보”로만 설계하면 거의 항상 실패합니다. 시간이 없어서가 아니라, “승격 직후의 불확실성(롤아웃/버전 공존/정책 변경)”이 검증의 입력을 흔들기 때문입니다.

링 설계를 ‘검증’에서 ‘의사결정’으로 바꾸면 형태가 달라집니다.

- 링0 (IT/관측용): 빠르게 받는 링. 여기서 하는 일은 “문제 찾기”가 아니라 “버전 진실을 확정하는 데 필요한 데이터 확보”입니다.
- 링1 (업무 핵심 파일럿): 조직에서 가장 비싼 워크플로(ERP, 결제, 컨택센터, 콜/회의, 내부 SSO)를 가진 사용자 중 극히 일부. 여기서는 기능 테스트보다도 “확장/정책/재시작”이 정상인지 봅니다.
- 링2 (대다수 Stable): 보안 SLO를 맞추는 구간. 링2는 지연이 길어질수록 ‘다음 버전과 겹치기’ 때문에 비용이 기하급수로 올라갑니다.
- 링3 (예외): Extended Stable 또는 TargetVersionPrefix로 잠깐 묶어두는 구간. 이 링은 규모가 커지면 운영 모델이 붕괴합니다.

Chrome Enterprise 문서는 Stable/Extended Stable의 추천 비율을 “대부분 Stable, 일부 Extended Stable, 5% Beta” 같은 형태로 제안합니다.[^3]

하지만 이 비율은 조직마다 다를 수 있고, 중요한 건 비율이 아니라 “링3의 최대 크기”를 정해놓는 것입니다. 링3는 운영팀의 능력이 아니라 조직의 부채를 담는 통이기 때문에, 무제한으로 키우면 결국 전체가 링3가 됩니다.

## 운영 패턴 2: 강제 재시작을 보안 SLO로 다룬다

Chrome 패치 운영에서 가장 현실적인 함정은 “업데이트 배포”와 “업데이트 적용”을 같은 이벤트로 취급하는 것입니다.

- Windows에서 Google Update는 주기적으로 실행되며(시간 단위로 작업 평가), 정책에 따라 체크 주기/억제 구간/업데이트 정책이 달라집니다.[^10]
- 그렇다고 해서 사용자의 Chrome 프로세스가 즉시 바뀌는 건 아닙니다. 재시작이 필요합니다.

Google은 엔터프라이즈에서 업데이트 적용을 빠르게 하기 위해 RelaunchNotification 정책 적용을 권장한다고 명시적으로 말합니다.[^9]

여기서 운영 관점의 핵심은 “강제 재시작을 어떻게 ‘기술 설정’이 아니라 ‘SLO’로 표현하느냐”입니다.

### 재시작 정책은 3개의 축으로 쪼갠다

1) 알림 방식: RelaunchNotification
2) 유예 기간: RelaunchNotificationPeriod
3) 강제 적용 시간대: RelaunchWindow

Chrome Enterprise Help의 ‘pending updates 적용을 위한 재시작 알림’ 문서는 세 값을 함께 예시로 제시하고, chrome://policy에서 확인하라고 안내합니다.[^11]

RelaunchWindow 정책 문서는 “RelaunchNotification이 Required일 때, notification period의 끝에서 강제 재시작이 발생한다”는 모델을 설명합니다.[^12]

즉, 유예 기간을 48시간으로 줄이는 것만으로는 부족합니다. 실제 강제 적용이 사용자의 업무 시간에 떨어지지 않게 ‘window’를 같이 잡아야, 재시작 정책이 조직 저항을 덜 받습니다.

### Chrome 157에서의 변화: ‘동적 패칭’이 재시작 부담을 줄이지만 없애진 않는다

Chrome Enterprise release notes에는 Chrome 157부터 Windows에서 “child processes에 대한 dynamic patching”이 들어갔고, DynamicPatchingEnabled 정책으로 제어 가능하다고 적혀 있습니다. 또한 이 기능은 ComponentUpdatesEnabled가 꺼져 있으면 동작을 기대하기 어렵다고 설명합니다.[^13]

보안 블로그에서도 동적 패칭을 “브라우저 전체 재시작 필요성을 줄이기 위한 투자”로 설명합니다.[^9]

여기서 운영자가 기대하면 안 되는 포인트가 있습니다.
- 동적 패칭은 ‘일부 보안 수정의 적용 시간’을 줄여줄 수 있지만, fleet을 “최신 버전 문자열”로 정렬하는 문제(컴플라이언스/감사/취약점 스캐너 입력)는 여전히 재시작과 앱 업데이트에 묶여 있습니다.
- 정책 변경은 여전히 재시작을 요구하는 경우가 많고, Help 문서도 정책 적용 후 relaunch가 필요하다고 반복해서 말합니다.[^11]

그래서 강제 재시작은 Chrome 157에서도 운영의 중심입니다.

## 운영 패턴 3: 버전 진실(source of truth)을 하나로 고정한다

2주 사이클에서 배포가 흔들리는 이유는, 대부분 조직 내에 ‘버전 진실’이 여러 개 존재하기 때문입니다.

- 보안팀: CVE 기준 최소 버전
- IT 운영: “major 157로 올렸다” 같은 milestone 기준
- 헬프데스크: 사용자 화면의 “업데이트 완료” 문구 기준
- 취약점 스캐너: exe file version 또는 레지스트리 기준
- 확장팀: 특정 extension과의 호환성 기준

Chrome 157처럼 Windows/Mac에 .38과 .39가 공존하면, 이 진실들이 즉시 충돌합니다.[^1]

내가 쓰는 운영 패턴은 버전 진실을 “정규화된 정책 객체”로 만드는 쪽입니다.

- 각 링에 대해
  - 허용 채널(Stable/Extended Stable)
  - 최소 허용 버전(min_version)
  - 허용 버전 집합(allowlist, 예: 157.0.8103.38/.39)
  - 강제 재시작 유예 시간
  - 강제 재시작 window
  - 롤백 가능 여부

을 하나의 JSON/YAML로 고정합니다.

그 다음, 배포 파이프라인(GPO/MDM/Chrome Enterprise Core, 그리고 모니터링/준수율 계산)은 모두 이 파일만 바라보게 만듭니다. 현장에선 이걸 문서라고 부르지만, 실제론 “운영 시스템의 데이터 모델”입니다.

Chrome Enterprise 쪽 문서도 릴리스 노트/정책 템플릿 업데이트를 강조합니다. 업데이트 옵션 문서 PDF는 “새 정책을 쓰려면 템플릿을 업데이트해야 한다”와 “릴리스 노트를 가이드로 보라”를 추천합니다.[^14]

버전 진실이 없으면, 템플릿 업데이트/정책 반영/확장 예외 처리 같은 조치가 모두 임시방편으로 흩어집니다.

## Chrome 157에서 특히 신경 쓸 변경: 확장 프로그램 오버라이드 차단

Chrome 157의 엔터프라이즈 release notes에는, 정책으로 설치된 확장 중 Default search engine 또는 New tab page를 수정하는 확장을 “unmanaged/low-trust” 환경에서 무시(제거/차단)하는 동작이 들어갔다고 적혀 있습니다. 그리고 이를 위해 ExtensionForceInstallWithSearchOrNewTabOverridesEnabled라는 새 정책을 8주 동안 제공한다고 설명합니다.[^13]

여기서 중요한 운영 포인트는 4개입니다.

1) 영향 범위는 “확장”이 아니라 “정책 설치된 확장”입니다.
- 일반 사용자 설치는 남기고, 정책 설치를 제한하는 모델입니다.[^13]

2) 영향 범위는 “Windows/macOS의 unmanaged/low-trust”로 한정됩니다.
- release notes는 AD domain-joined, Azure AD-joined, Chrome Enterprise Core enrolled, macOS MDM managed 같은 경우는 영향이 없다고 적습니다.[^13]

3) 8주라는 시간 제한은 “유예”이지 “안전”이 아닙니다.
- 2주 사이클에서는 8주가 길어 보이지만, milestone 기준으로는 4개 버전이 지나갑니다. 이 기간에 정리 못 하면 다음 분기엔 갑자기 정책이 제거되는 식으로 운영이 망가질 수 있습니다.

4) 이 변경은 ‘확장 사고’를 아주 전형적으로 만들 수 있습니다.
- 조직에서 BYOD/VDI/이미지 기반으로 로컬 정책을 얹어 쓰는 구간이 있다면, 그 구간이 관리 상태 판정에서 흔들릴 때 확장이 갑자기 제거된 것처럼 보일 수 있습니다.
- 이런 류의 이슈는 헬프데스크에선 “확장이 사라졌다”로 보고되지만, 운영 관점에선 “정책 소스 신뢰 등급이 바뀌었다”로 해석해야 복구가 빠릅니다.

확장 배포/정책 precedence에 대한 기본 운영은 예전에 다뤘고, 이번 글에서는 위 변경이 “첫 48시간 운영 이슈로 터질 수 있는 지점”만 연결했습니다.
- [Chrome 제로데이 주간에 브라우저 업데이트를 배포 파이프라인으로 굴리는 방법](https://daewooki.github.io/posts/chrome-zero-day-rollout-pipeline/)

## 롤백은 마지막 수단이 아니라 ‘링의 일부’가 된다

2주 사이클에서 롤백을 “사고 대응용”으로만 두면, 실제로는 더 위험해집니다.

- Stable이 빠르게 돌아가면, 롤백을 미루는 동안 다음 버전이 나와서 “원래 돌아가려던 버전”이 이미 보안팀 기준에서 금지되는 상황이 생깁니다.
- 그래서 롤백은 ‘불가피한 경우의 임시 격리 링(링3)’로 설계해야 합니다.

Windows에서 Chrome을 특정 버전으로 pin하거나 rollback하는 방법은 Chrome Enterprise Help 문서가 TargetVersionPrefix override, Rollback to Target version 등을 구체적으로 안내합니다.[^10]

macOS에서도 TargetVersionPrefix와 RollbackToTargetVersion을 같이 쓰는 예시를 문서가 제공합니다.[^15]

그리고 엔터프라이즈 업데이트 기술 문서 쪽에서는 롤백이 무제한이 아니라 “최근 3개 major” 같은 제약이 있음을 언급합니다.[^16]

운영 결론은 단순합니다.
- 링3(예외)는 “3개 major 안에서만 생존 가능”한 구간으로 설계해야 합니다.
- 링3에 들어가는 순간, 빠져나오는 계획(대체 앱/확장 수정/사이트 핫픽스)이 같이 있어야 합니다.

## 실제 구현 예시: truth.json + 수집 스크립트 + 준수율 계산

아래 코드는 “버전 진실(source of truth)을 범위로 표현하고”, “링별 최소 버전 + 허용 버전 집합”을 기준으로 준수율을 계산하는 최소 구현입니다.

의도는 세 가지입니다.
- Chrome 157처럼 Windows/Mac에 .38/.39가 공존하는 경우를 정상 케이스로 흡수
- “업데이트 받음”이 아니라 “재시작까지 끝나서 실제 실행 중 버전이 기준 이상”인지를 판단
- 링이 2주마다 재조정되더라도 운영 데이터 모델은 그대로 유지

### 1) truth.json (버전 진실)

```json
{
  "as_of": "2026-11-03",
  "product": "chrome-desktop",
  "milestone": 157,
  "stable_rollout": {
    "note": "Chrome 157 promoted to Stable; rollout over coming days/weeks",
    "linux": {
      "min_version": "157.0.8103.38",
      "allowed_versions": ["157.0.8103.38"]
    },
    "win_mac": {
      "min_version": "157.0.8103.38",
      "allowed_versions": ["157.0.8103.38", "157.0.8103.39"]
    }
  },
  "rings": {
    "ring0-it": {
      "target_channel": "stable",
      "target_version_prefix": "157.",
      "relaunch_notification_period_ms": 86400000,
      "relaunch_window": {"start_hhmm": "23:30", "duration_mins": 240}
    },
    "ring1-pilot": {
      "target_channel": "stable",
      "target_version_prefix": "157.",
      "relaunch_notification_period_ms": 172800000,
      "relaunch_window": {"start_hhmm": "23:30", "duration_mins": 240}
    },
    "ring2-broad": {
      "target_channel": "stable",
      "target_version_prefix": "157.",
      "relaunch_notification_period_ms": 432000000,
      "relaunch_window": {"start_hhmm": "02:00", "duration_mins": 180}
    },
    "ring3-exception": {
      "target_channel": "extended_stable",
      "target_version_prefix": "156.",
      "relaunch_notification_period_ms": 604800000,
      "relaunch_window": {"start_hhmm": "02:00", "duration_mins": 240}
    }
  }
}
```

- `target_version_prefix`를 `157.`처럼 prefix로 두는 이유는, dot-release(.40, .41 같은 refresh)가 나와도 같은 milestone 내에서 흡수하기 위해서입니다.
- `min_version`과 `allowed_versions`는 ‘준수율 측정’에 쓰고, prefix는 ‘배포 제어’에 씁니다. 둘을 같은 값으로 만들면 운영이 깨집니다.

### 2) truth_server.py (표준 라이브러리만으로 truth 제공)

```python
#!/usr/bin/env python3
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

class Handler(BaseHTTPRequestHandler):
    truth_path: Path = Path("truth.json")

    def do_GET(self):
        if self.path not in ("/", "/truth", "/truth.json"):
            self.send_response(404)
            self.end_headers()
            return

        data = self.truth_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "max-age=30")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--truth", default="truth.json")
    args = ap.parse_args()

    Handler.truth_path = Path(args.truth)
    # fail fast
    json.loads(Handler.truth_path.read_text(encoding="utf-8"))

    httpd = HTTPServer((args.bind, args.port), Handler)
    print(f"serving {Handler.truth_path} on http://{args.bind}:{args.port}/truth")
    httpd.serve_forever()

if __name__ == "__main__":
    main()
```

실행:

```bash
python3 truth_server.py --truth truth.json --port 8080
curl -s http://127.0.0.1:8080/truth | python3 -m json.tool | head
```

이 서버는 ‘내부 운영 데이터’를 배포 파이프라인과 모니터링이 같이 소비하도록 만드는 가장 단순한 접점입니다. FastAPI 같은 걸 올려도 되지만, 핵심은 프레임워크가 아니라 “진실이 하나로 고정되느냐”입니다.

### 3) collect_chrome_version.ps1 (Windows 버전 수집 예시)

```powershell
param(
  [string]$Out = "chrome-inventory.json"
)

$chromePaths = @(
  "$Env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "$Env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe",
  "$Env:LocalAppData\Google\Chrome\Application\chrome.exe"
)

$chromeExe = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1

$version = $null
if ($chromeExe) {
  $version = (Get-Item $chromeExe).VersionInfo.ProductVersion
}

$machineName = $env:COMPUTERNAME

$obj = [ordered]@{
  collected_at = (Get-Date).ToString("o")
  host = $machineName
  os = "windows"
  chrome_exe = $chromeExe
  chrome_version = $version
}

$obj | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 $Out
Write-Host "wrote $Out"
```

실행:

```powershell
powershell -ExecutionPolicy Bypass -File .\collect_chrome_version.ps1 -Out .\inventory\WIN-001.json
type .\inventory\WIN-001.json
```

여기서 중요한 건 “업데이트 배포 상태”가 아니라 “현재 실행 파일 버전”을 수집하는 것입니다. 브라우저 업데이트의 체감 사고는 대부분 재시작 부채에서 터지기 때문에, exe 버전이 준수율 지표의 기준이 되는 편이 낫습니다.

### 4) collect_chrome_version.sh (macOS/Linux 수집 예시)

```bash
#!/usr/bin/env bash
set -euo pipefail

OUT="${1:-chrome-inventory.json}"
HOST="$(hostname)"
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"

VERSION=""
if command -v /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome >/dev/null 2>&1; then
  VERSION="$(/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --version | awk '{print $3}')"
elif command -v google-chrome >/dev/null 2>&1; then
  VERSION="$(google-chrome --version | awk '{print $3}')"
elif command -v google-chrome-stable >/dev/null 2>&1; then
  VERSION="$(google-chrome-stable --version | awk '{print $3}')"i

python3 - <<PY > "$OUT"
import json, datetime
print(json.dumps({
  "collected_at": datetime.datetime.utcnow().isoformat() + "Z",
  "host": "${HOST}",
  "os": "${OS}",
  "chrome_version": "${VERSION}"
}, indent=2))
PY

echo "wrote $OUT"
```

### 5) fleet_check.py (준수율 계산)

```python
#!/usr/bin/env python3
import json
import sys
from pathlib import Path

def parse_version(v: str):
    # very small parser: 157.0.8103.39 -> (157,0,8103,39)
    parts = v.strip().split(".")
    if len(parts) != 4:
        return None
    try:
        return tuple(int(x) for x in parts)
    except ValueError:
        return None

def ge(a: str, b: str) -> bool:
    pa, pb = parse_version(a), parse_version(b)
    if pa is None or pb is None:
        return False
    return pa >= pb

def main():
    if len(sys.argv) != 3:
        print("usage: fleet_check.py truth.json inventory_dir", file=sys.stderr)
        raise SystemExit(2)

    truth = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    inv_dir = Path(sys.argv[2])

    min_win_mac = truth["stable_rollout"]["win_mac"]["min_version"]
    allowed_win_mac = set(truth["stable_rollout"]["win_mac"]["allowed_versions"])

    total = 0
    ok_allowed = 0
    ok_min = 0
    unknown = 0

    for p in sorted(inv_dir.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        ver = (data.get("chrome_version") or "").strip()
        total += 1

        if not ver:
            unknown += 1
            continue

        if ver in allowed_win_mac:
            ok_allowed += 1

        if ge(ver, min_win_mac):
            ok_min += 1

    print(f"total={total}")
    print(f"ok(min_version>={min_win_mac})={ok_min}")
    print(f"ok(allowed_versions)={ok_allowed}")
    print(f"unknown(no_version)={unknown}")

if __name__ == "__main__":
    main()
```

실행:

```bash
python3 fleet_check.py truth.json ./inventory
```

이 계산은 일부러 단순하게 만들었습니다. 현장에선 여기에 링 정보(AD OU, MDM smart group, Chrome Enterprise Core OU 등)를 붙이고, “링2는 min_version 준수율 95%를 48시간 내 달성” 같은 SLO로 바꿉니다.

## 회의론: 2주마다 이걸 반복할 수 있나

반론은 보통 두 갈래입니다.

1) 2주마다 major가 나오면 링 운영은 불가능하다
2) 그러니 자동업데이트를 끄고 분기/월 단위로 모아서 올리자

둘 다 반은 맞고 반은 틀립니다.

- 2주마다 링 운영은 ‘검증’ 모델로는 불가능하지만, ‘의사결정’ 모델로 쪼개면 가능합니다. 여기서 의사결정이란 “문제 없음을 증명”이 아니라 “어떤 위험을 어떤 링에 얼마나 담을지 결정”입니다.
- 자동업데이트를 끄고 모아서 올리면, 그 조직은 사실상 Extended Stable 없이 자체 ESR을 만드는 셈입니다. 그런데 Chrome의 보안 수정량/패치갭 전략은 주간 단위로 계속 압축되는 방향이고(weekly refresh, 더 빠른 cadence 시도 등), 재시작 지연이 공격면이 된다고 Google도 말합니다.[^2]

내 결론은 “자동업데이트를 끄는 조직은 결국 업데이트 엔지니어링을 제품 수준으로 키워야 한다”는 쪽입니다. 그게 가능하면 해도 되지만, 대부분 조직은 그 인력을 브라우저 업데이트에 쓸 수 없습니다.

그래서 현실적인 해법은 다음 중 하나로 귀결됩니다.
- Stable을 기본으로 유지하되, 링3를 작게 유지하고(예외 최소화) 재시작 SLO를 강하게 걸거나
- Stable을 유지 못 하는 일부를 Extended Stable로 분리해 ‘예외를 격리’하거나

이 둘을 섞습니다. Chrome Enterprise도 Extended Stable을 “수용 불가 조직의 대안”으로 문서화합니다.[^5]

## 앞으로 8주 동안 지켜볼 것

Chrome 157 시점에서 8주라는 시간축을 가진 이슈는 이미 하나가 보입니다.

- ExtensionForceInstallWithSearchOrNewTabOverridesEnabled가 “8주 동안 제공”된다고 release notes가 명시합니다.[^13]

이건 운영 관점에서 “8주 뒤에 정책이 사라질 수 있다”는 뜻이고, 2주 사이클에선 4개 milestone 이후를 의미합니다. 즉, 지금 링/확장 운영이 unmanaged/low-trust 구간을 포함하고 있다면, 8주 안에 다음을 끝내야 합니다.

- 그 구간이 왜 unmanaged 판정을 받는지 정리(AD/Azure AD/MDM/Chrome Enterprise Core enrollment 상태)
- 확장이 search/NTP override를 쓰는지 식별
- 그 override가 정말로 필요한지 판단(내부 포털/검색 가로채기/보안 제품/레거시 리다이렉션 등)
- 대체 설계(브라우저 설정 정책으로 대체 가능 여부, 확장 업데이트 계획)

그리고 Chrome 157의 또 다른 축은 “dynamic patching을 운영에서 어떻게 계량화하느냐”입니다. release notes는 DynamicPatchingEnabled와 ComponentUpdatesEnabled의 결합을 언급합니다.[^13]

동적 패칭이 ‘재시작 없는 보안 적용’을 얼마나 현실적으로 줄여주는지는, 결국 조직의 워크로드(탭 상주 시간, VDI 세션 길이, kiosk/사이니지 등)에 의해 결정됩니다. 이건 기능 출시가 아니라 운영 데이터로 판단해야 합니다.

## 결론: 2주 사이클에서 버전은 범위가 되고 운영은 데이터 모델이 된다

Chrome 157 승격 직후 48시간은 “업데이트를 더 빨리 돌리자” 같은 구호로는 해결되지 않습니다. 버전이 .38/.39처럼 범위로 공존하고, 롤아웃이 days/weeks로 퍼지며, 정책은 관리 상태에 따라 존중 여부가 갈리고, 확장 업데이트는 별도 세계선으로 움직입니다.[^1]

그래서 운영 패턴은 세 가지로 수렴합니다.

- 업데이트 링은 검증 창이 아니라 의사결정 레인으로 쪼개고
- 강제 재시작은 UX 문제가 아니라 보안 SLO로 끌어올리며
- 버전 진실(source of truth)은 단일 JSON/레코드로 고정해 모든 파이프라인이 같은 숫자를 보게 만든다

이 세 가지를 동시에 잡았을 때만, 2주 Stable 사이클이 ‘빠르다’가 아니라 ‘예측 가능하다’로 바뀝니다.

## 참고 자료

- [Stable Channel Update for Desktop (2026-11-03)](https://chromereleases.googleblog.com/2026/11/stable-channel-update-for-desktop.html)
- [Chrome Release Cycle (Chromium docs)](https://chromium.googlesource.com/chromium/src/%2B/HEAD/docs/process/release_cycle.md)
- [Chrome browser release channels (Chrome Enterprise Help)](https://support.google.com/chrome/a/answer/9027636)
- [Fresher features, faster fixes: The two-week release cycle is here (Chrome for Developers, 2026-09-08)](https://developer.chrome.com/blog/chrome-two-week-start)
- [Chrome Enterprise Release Notes](https://chromeenterprise.google/intl/en-US/resources/release-notes/)
- [Notify users to restart to apply pending updates (Chrome Enterprise Help)](https://support.google.com/chrome/a/answer/7679871)
- [RelaunchWindow policy (Chrome Enterprise policy documentation)](https://chromeenterprise.google/policies/relaunch-window/)
- [Manage Chrome updates (Windows) (Chrome Enterprise Help)](https://support.google.com/chrome/a/answer/6350036)
- [Manage Chrome updates (Mac) (Chrome Enterprise Help)](https://support.google.com/chrome/a/answer/7591084)
- [Chromium Updater Functional Specification](https://chromium.googlesource.com/chromium/src/%2B/HEAD/docs/updater/functional_spec.md)
- [Stronger with every update: How we’re making Chrome and the web safer in the AI Era (Google Security Blog)](https://blog.google/security/chrome-stronger-with-every-update/)
- [Set Chrome app and extension policies (Windows) (Chrome Enterprise Help)](https://support.google.com/chrome/a/answer/7532015)
- [Pre-installed Extensions (Chromium administrators)](https://www.chromium.org/administrators/pre-installed-extensions/)
- [Chrome enterprise policies.yaml (Chromium source)](https://chromium.googlesource.com/chromium/src/%2B/main/components/policy/resources/templates/policies.yaml)
- [ComponentUpdatesEnabled (policy-list-3 index)](https://chromium.googlesource.com/playground/chromium-org-site/%2Bshow/refs/heads/main/administrators/policy-list-3/index.md)

[^1]: <https://chromereleases.googleblog.com/2026/11/stable-channel-update-for-desktop.html>
[^2]: <https://chromium.googlesource.com/chromium/src/%2B/HEAD/docs/process/release_cycle.md>
[^3]: <https://support.google.com/chrome/a/answer/9027636?hl=en-AI>
[^4]: <https://developer.chrome.com/blog/chrome-two-week-start>
[^5]: <https://support.google.com/chrome/a/answer/16942104?hl=en-cy>
[^6]: <https://chromium.googlesource.com/chromium/src/%2B/HEAD/docs/updater/functional_spec.md?pli=1%2F%2F>
[^7]: <https://support.google.com/chrome/a/answer/7532015?hl=EN>
[^8]: <https://www.chromium.org/administrators/pre-installed-extensions/>
[^9]: <https://blog.google/security/chrome-stronger-with-every-update/>
[^10]: <https://support.google.com/chrome/a/answer/6350036?hl=EN>
[^11]: <https://support.google.com/chrome/a/answer/7679871?hl=en>
[^12]: <https://chromeenterprise.google/policies/relaunch-window/>
[^13]: <https://chromeenterprise.google/intl/en-US/resources/release-notes/>
[^14]: <https://services.google.com/fh/files/misc/understanding_your_chrome_browser_update_options_in_windows_environments.pdf>
[^15]: <https://support.google.com/chrome/a/answer/7591084?hl=en-1>
[^16]: <https://services.google.com/fh/files/misc/chrome_browser_enterprise_updates_technical_document-september-2021.pdf>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
