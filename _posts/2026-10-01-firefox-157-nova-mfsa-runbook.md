---
title: "Firefox 157 Nova와 MFSA 동시 배포 런북"
description: "Firefox 157의 Nova UI 변화와 MFSA 보안 권고를 분리하지 못할 때, 조직 배포·정책·헬프데스크를 한 런북으로 묶는 방법."
date: 2026-10-01 11:25:20 +0900
categories: ["News", "Web"]
tags: ["firefox", "enterprise-deployment", "mfsa", "nova-ui", "runbook", "gpo"]
render_with_liquid: false
---

## 2026-09-29에 동시에 벌어진 일: Firefox 157.0 릴리스와 MFSA 2026-97

Firefox 157.0은 2026년 9월 29일에 Release 채널에 제공됐습니다. 릴리스 노트의 톤을 보면, 이번 릴리스는 기능 추가보다 **UI 리프레시**가 중심입니다. Mozilla는 Nova를 “최근 몇 년 사이 가장 큰 시각적 변화”로 소개했고, 툴바·sidebar·메뉴·기능 전반의 디자인 시스템 업데이트, 새 테마, Compact mode 등을 함께 내놨습니다. 동시에 sidebar revamp가 전체 사용자에게 기본 적용되면서, 설정 화면에서 “Show sidebar” 옵션이 제거됐고, 예전 sidebar로 되돌리는 경로로 `about:config`의 `sidebar.revamp=false`를 명시했습니다. 이 preference는 2027년 말까지 유지된다고 못 박았습니다.

- [Firefox 157.0 Release Notes](https://www.firefox.com/en-US/firefox/157.0/releasenotes/)

같은 날, Firefox 157에서 수정된 보안 취약점 목록이 [MFSA 2026-97](https://www.mozilla.org/en-US/security/advisories/mfsa2026-97/)로 공지됐습니다. Impact는 high로 분류되어 있고, advisory 자체도 “이제 내부적으로 식별된 memory safety 취약점을 한 CVE로 뭉뚱그리지 않고, 개별 버그 단위로 advisory를 발행한다”는 방식 변경을 함께 알립니다.

- [MFSA 2026-97: Security Vulnerabilities fixed in Firefox 157](https://www.mozilla.org/en-US/security/advisories/mfsa2026-97/)

2026-10-01 KST 기준(릴리스 이틀 뒤) 조직 입장에서 문제는 단순합니다.

1) Nova UI는 사용자 경험을 크게 바꿉니다.
2) MFSA는 high impact를 포함합니다.
3) 둘이 157이라는 단일 바이너리에 같이 실려 왔습니다.

즉 “UI는 나중에, 보안만 먼저” 같은 분리 배포가 현실적으로 불가능해졌습니다. 여기서 배포 운영의 단위는 ‘패치’가 아니라 ‘릴리스 버전’이기 때문에, 조직은 기능·UX·보안을 한 변경 묶음으로 취급하는 런북을 갖고 있어야 합니다.

## 왜 이 타이밍에 더 험해졌나: 2주 릴리스 리듬과 동시 공지

Mozilla는 2026년 9월부터 4주에서 2주 릴리스로 바꾸는 흐름을 공개적으로 커뮤니케이션해왔습니다. SUMO(지원) 블로그 글에서는 Firefox 155(2026-09-01)가 새 cadence의 첫 릴리스라고 명시하고, Nova가 157에서 본격 롤아웃될 가능성이 큰 “첫 메이저 테스트”가 될 것이라고도 언급합니다.

- [Firefox new release cadence and what to expect](https://blog.mozilla.org/sumo/2026/08/19/firefox-new-release-cadence-and-what-to-expect/)
- [MozillaWiki: The Firefox release process](https://wiki.mozilla.org/Release_Management/Release_Process)

2주 cadence가 의미하는 바는 테스트 시간이 절반으로 줄었다는 얘기가 아닙니다. 실제로는 다음이 동시에 발생합니다.

- 조직 내부의 검증 파이프라인은 예전 속도로 그대로인데 외부 릴리스가 더 자주 들어옵니다.
- dot release(예: 156.0.1 같은)로 위험을 늦춰주던 완충이 줄고, 사용자들은 더 자주 ‘큰 번호 변화’를 경험합니다.
- 보안 공지(MFSA)와 기능/UX 변경이 같은 날, 같은 버전 번호로 결박되는 일이 더 흔해집니다.

이번 157은 그 압축된 리듬 위에 Nova라는 대형 UI 변경이 얹힌 형태라서, 엔터프라이즈 배포 관점에서는 “브라우저 업데이트”가 아니라 “업무 도구 UI 개편 + high impact 보안 패치 + 운영 정책 변화”가 한꺼번에 들어온 사건으로 취급하는 편이 맞습니다.

## Nova UI가 엔터프라이즈/조직 배포에서 위험한 지점

Nova UI 자체가 좋은지 나쁜지는 조직 배포 런북의 관심사가 아닙니다. 런북에서 중요한 건 ‘사용자 행동이 바뀌는 지점’과 ‘조직 표준이 깨지는 지점’입니다.

### 1) sidebar/vertical tabs는 단순한 스킨이 아니라 작업 동선 변경입니다

Firefox 157 릴리스 노트는 sidebar 업데이트가 전 사용자에게 활성화됐다고 명시합니다. 그리고 설정에서 sidebar를 보여주는 옵션이 제거되었다고 적어, 사용자가 “원래대로 돌리는 설정”을 UI에서 찾을 수 없게 되었음을 인정합니다. 되돌리는 방법은 `about:config`에서 `sidebar.revamp=false`로 내리라는 식입니다. 더 중요한 건 “이 preference는 2027년 말까지 유지”라는 문장입니다. Mozilla가 이 값을 임시 레버로 보고 있다는 신호입니다.

- [Firefox 157.0 Release Notes](https://www.firefox.com/en-US/firefox/157.0/releasenotes/)

엔터프라이즈 환경에서 sidebar/vertical tabs가 위험한 이유는 이게 UI 취향 문제가 아니라 **업무 절차와 헬프데스크 스크립트가 깨지는 문제**이기 때문입니다.

- 내부 포털/그룹웨어/SSO 공지에서 “브라우저 오른쪽 위 … 메뉴 → 설정” 같은 안내가 들어가 있는데, 메뉴 구조·위치가 달라지면 그대로 문의가 터집니다.
- 원격 지원 도구를 켜고 “주소창 옆의 아이콘”을 누르라고 가이드하던 콜센터 플로우가 어긋납니다.
- vertical tabs는 탭 관리 습관(대량 탭을 가로로 흘려보내던 습관)을 바꿉니다. 교육 없이 기본값이 바뀌면, 사용자 입장에서는 ‘브라우저가 갑자기 이상해졌다’로 해석합니다.

이걸 UX팀이 설문으로 풀 문제가 아니라, 배포팀이 사전에 흡수해야 하는 운영 이슈로 보는 게 안전합니다.

### 2) 테마/색/배경은 사용자 커스터마이징이 아니라 지원 부담입니다

Mozilla Add-ons 커뮤니티 블로그는 “Firefox 157에서 Nova가 shipped 되었고, Proton(2021) 이후 가장 큰 리프레시”라고 말하면서, theme에서 달라지는 지점을 꽤 구체적으로 설명합니다. 요지는 “동작은 유지되지만 보이는 위치/조합이 달라져서 예상과 다르게 보일 수 있다”입니다. vertical tabs가 first-class 레이아웃이 되면서 theme의 색 적용 위치도 달라질 수 있고, 일부 property는 더 이상 눈에 띄는 효과가 없다고 정리합니다.

- [Nova is here: what changes for your Firefox theme](https://blog.mozilla.org/addons/2026/09/29/nova-is-here-what-changes-for-your-firefox-theme/)

조직 배포에서 이것이 왜 중요하냐면, 테마는 개인 취향으로 보이지만 다음과 같은 경로로 표준화되곤 합니다.

- VDI/공용 PC/키오스크에서 일괄 테마 적용(브랜딩/가독성/접근성 목적)
- 특정 부서(예: 트레이딩/관제/CS)가 Compact mode를 사실상 업무 표준처럼 쓰는 상황
- userChrome.css 같은 비공식 커스터마이징이 팀 단위로 퍼진 상태

Mozilla Connect의 Nova 공지 글은 “userChrome.css는 공식 지원이 아니며, 업데이트로 깨질 수 있다”는 점을 명시적으로 언급합니다. 이 문장은 엔터프라이즈 운영자가 내부 표준으로 userChrome.css를 허용하고 있었다면, 그 순간부터 운영 책임이 조직으로 완전히 넘어왔다는 의미입니다.

- [Mozilla Connect: The new Firefox design lands in today](https://connect.mozilla.org/t5/discussions/the-new-firefox-design-lands-in-today-this-is-what-you-can/td-p/139524)

이 부분을 런북에서 분리하면, 결국 배포가 끝난 뒤 helpdesk가 “왜 UI가 바뀌었냐/원래대로 못 돌리냐”를 개별 대응하게 됩니다. 그 비용이 배포팀으로 다시 역류합니다.

### 3) 커뮤니티 반응은 ‘기술적 진실’이 아니라 ‘티켓 폭증 지표’입니다

Reddit 같은 커뮤니티 반응은 공식 스펙이 아닙니다. 그렇지만 엔터프라이즈 배포 관점에서는 “어떤 질문이 helpdesk로 들어올지”를 미리 보여주는 지표로는 쓸모가 있습니다.

특히 이번 Nova 롤아웃은 커뮤니티 스레드에서 아래 질문이 반복됩니다.

- Nova를 끄는 about:config preference가 무엇인지
- 업데이트 후 preference가 원복되는지
- padding/색/gradient/rounded corners 같은 UI 디테일 불만

- [r/firefox: The new UX design (Nova) lands in Firefox today](https://www.reddit.com/r/firefox/comments/1wt9ig4/the_new_ux_design_nova_lands_in_firefox_today/)

이걸 ‘불평’으로만 보면 런북 품질이 떨어집니다. 오히려 “helpdesk FAQ에 어떤 키워드를 넣어야 하는지”를 정하는 데이터로 보고 흡수하는 편이 비용이 적습니다.

## MFSA 2026-97을 기능 릴리스와 분리할 수 없을 때의 보안 의사결정

MFSA 2026-97은 Impact high이고, Firefox 157에서 수정됐다고 명시합니다. advisory 안에는 use-after-free, sandbox escape 같은 유형이 포함되어 있습니다.

- [MFSA 2026-97: Security Vulnerabilities fixed in Firefox 157](https://www.mozilla.org/en-US/security/advisories/mfsa2026-97/)

조직 배포에서 여기서 중요한 결론은 하나입니다.

- 157 배포를 미루는 건 “UI 변경을 미루는 것”이 아니라 “high impact 취약점 수정 적용을 미루는 것”이 됩니다.

여기서 흔히 생기는 오해는 다음입니다.

- “UI가 큰 릴리스니까 보안팀이 싫어한다”

실제로는 반대입니다.

- 보안팀은 대형 UI 변경이 싫어서가 아니라, 배포가 미뤄질 때 보안 노출 기간이 길어지는 것이 싫습니다.
- 배포팀은 보안 패치는 빨리 해야 하지만 UX 변경 때문에 helpdesk 부하가 걱정됩니다.

이 충돌을 풀려면 ‘누가 더 급하냐’ 싸움이 아니라, 배포 단위를 바꾸는 게 아니라 “런북의 출력물”을 바꿔야 합니다. 즉 157 배포를 결정했다면, 동시에 helpdesk 흡수 플랜(FAQ/스크립트/임시 완화책/롤백 경로)을 같은 티켓/같은 change window에 포함해야 합니다.

## 156 → 157 업데이트에서 런북에 들어가야 하는 변화 목록

여기서는 “사용자가 체감하는 변화”, “엔터프라이즈 정책 변화”, “운영자가 놓치기 쉬운 변화” 순서로 정리합니다.

### 1) 사용자 체감: Nova + sidebar/vertical tabs + Compact mode

Firefox 157 릴리스 노트에서 조직 배포 관점으로 체크리스트화할 만한 문장은 다음입니다.

- “biggest visual refresh in years”
- built-in themes(라이트/다크)
- Compact mode(공식 지원, 공간 축소)
- sidebar 업데이트 전면 활성화
- Settings에서 “Show sidebar” 옵션 제거
- `about:config`의 `sidebar.revamp=false`로 복구 가능(단, vertical tabs도 같이 꺼짐)
- 해당 preference는 2027년 말까지 유지

- [Firefox 157.0 Release Notes](https://www.firefox.com/en-US/firefox/157.0/releasenotes/)

이 항목들은 배포 공지문에 반드시 들어가야 합니다. 공지문에 “UI가 바뀔 수 있음” 정도로 퉁치면, 변화가 “사이드바가 어디 갔냐”처럼 구체적 문의로 들어왔을 때 helpdesk가 참조할 문장이 없습니다.

그리고 Nova가 UI만 바꾸는 게 아니라 key navigation에도 영향을 줍니다. 예를 들어 157에서 “Tab 키를 눌렀을 때 address bar/search bar의 텍스트 필드로 바로 focus가 이동”하도록 변경되었다고 적혀 있습니다. 조직 내에서 접근성/키보드 내비게이션 교육 자료가 있었다면, 이 한 줄 때문에 QA가 깨질 수 있습니다.

- [Firefox 157.0 Release Notes](https://www.firefox.com/en-US/firefox/157.0/releasenotes/)

### 2) 엔터프라이즈 정책/릴리스 노트: 157은 생각보다 변화가 작지만, 하나가 큽니다

Firefox Administrator Reference의 엔터프라이즈 릴리스 노트는 “Firefox 157과 Firefox ESR 153.4.0에 적용되는 변화”를 정리합니다.

여기서 156 → 157에 들어갈 만한 건 크게 세 갈래입니다.

1) `AIControls`에 `SpeechRecognition` 옵션 추가(온디바이스 음성 인식의 허용/차단 및 Locked 제공)
2) `about:policies`에서 “부분 적용 실패”를 active로 뭉개지 않고 실패한 entry를 명시하는 에러로 보여주도록 변경
3) 정책 처리 관련 fixes(`Homepage`의 `|` separator 재허용, `Handlers`에서 invalid 엔트리 하나 때문에 뒤가 통째로 버려지던 문제 수정)

그리고 Notes로 “Firefox ESR 140이 이 릴리스로 지원 종료이며, ESR 140.17.0이 마지막”이라고 명시합니다. 이 문장은 157 배포 런북에 반드시 들어가야 합니다. 이유는 단순합니다.

- 조직이 아직 ESR 140 라인에 남아 있으면, 157이라는 사건은 “Stable UI가 바뀐다”가 아니라 “ESR 마이그레이션을 더 이상 미룰 수 없다”로 읽어야 하기 때문입니다.

- [Firefox Release Notes for Enterprise](https://firefox-admin-docs.mozilla.org/release-notes/)

개인적으로는 2)번이 배포 운영에 꽤 도움이 됩니다. 정책이 부분 실패했을 때 현장 엔지니어가 `about:policies`를 열고도 “active”로 오해하는 일이 잦습니다. 앞으로는 실패 entry가 드러나니, endpoint에서 원인 추적 시간이 줄어듭니다.

### 3) 개발자/웹 플랫폼 변화: 내부 웹앱 호환성 체크는 좁고 깊게

MDN의 Firefox 157 개발자 릴리스 노트에는 CSS `@supports`에서 `at-rule()` 함수 지원 같은 웹 플랫폼 변화가 들어가 있습니다.

- [MDN: Firefox 157 release notes for developers](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/157)

엔터프라이즈 배포에서 이건 “대규모 회귀 테스트”가 아니라 “내부 표준 CSS 도구체인/폴리필이 있는지”만 확인하는 쪽이 효율적입니다. 예를 들어 회사 디자인 시스템이 `@supports`를 동적으로 생성하는 빌드 스텝이 있거나, 특정 at-rule 지원 여부를 토대로 CSS를 분기하는 코드가 있다면 영향을 받을 수 있습니다. 반대로 일반적인 사내 웹앱이라면 157의 웹 플랫폼 변화는 UI 리프레시나 MFSA에 비해 우선순위가 낮습니다.

## 동시 배포를 흡수하는 단일 런북: 입력 → 판단 → 배포 → 지원

내가 156을 배포 파이프라인에 넣을 때는 “릴리스는 계약(contract)이고, 파이프라인은 그 계약을 검증한다”는 관점으로 정리했습니다.

- [Firefox 156을 배포 파이프라인에 넣는 계약 설계](https://daewooki.github.io/posts/firefox-release-pipeline-contracts/)

157은 그 계약을 그대로 가져오되, 런북 산출물을 “보안/UX/helpdesk”까지 포함하는 형태로 확장해야 하는 릴리스입니다.

여기서 말하는 단일 런북은 문서 한 장이 아니라, 같은 change ticket 아래에 묶이는 일련의 산출물을 의미합니다.

### 1) 입력(신호) 수집: ‘릴리스 감지’만으로는 부족합니다

157 같은 케이스에서는 다음 세 가지 소스를 항상 묶어서 가져와야 합니다.

- 제품 릴리스 노트(사용자 체감 변화와 official workaround)
- MFSA(보안 긴급도와 유형)
- 엔터프라이즈 릴리스 노트(정책 변화, ESR 지원 종료 같은 운영 이슈)

소스 링크는 아래가 기본 세트입니다.

- [Firefox 157.0 Release Notes](https://www.firefox.com/en-US/firefox/157.0/releasenotes/)
- [MFSA 2026-97](https://www.mozilla.org/en-US/security/advisories/mfsa2026-97/)
- [Firefox Release Notes for Enterprise](https://firefox-admin-docs.mozilla.org/release-notes/)

그리고 Nova 관련해서는 사용자 공지문에 쓸 표현을 Mozilla Connect 공지에서 빌려오는 편이 조직 커뮤니케이션 품질이 좋습니다. “Compact mode가 공식 지원으로 들어왔다”, “Nightly에서 7월부터 테스트했다” 같은 배경을 간단히 적으면, ‘왜 갑자기 이렇게 바뀌냐’ 류의 반발을 줄이는 데 도움이 됩니다.

- [Mozilla Connect: The new Firefox design lands in today](https://connect.mozilla.org/t5/discussions/the-new-firefox-design-lands-in-today-this-is-what-you-can/td-p/139524)

### 2) 판단: 보안 긴급도와 UX 위험도를 같은 표에 올립니다

조직 배포에서 흔한 실패는 “보안 점수”와 “지원 비용”을 서로 다른 문서로 분리해 의사결정 테이블에 같이 못 올리는 것입니다.

157에서는 다음처럼 단순화하는 게 낫습니다.

- Security urgency: MFSA 2026-97 Impact = high → 기본적으로 fast-track(예: 72시간 내 broad rollout) 후보
- UX disruption: Nova + sidebar revamp 전면 활성화 → helpdesk capacity 확충 없이는 fast-track이 위험

결론은 “fast-track을 포기”가 아니라 “fast-track을 유지하기 위해 helpdesk 흡수책을 같이 배포”입니다.

### 3) 배포: ring 설계는 버전 핀과 ‘다음 릴리스’ 대비까지 포함해야 합니다

2주 cadence에서는 157을 배포하는 순간 158의 접근도 같이 시작됩니다. 이때 ring 설계를 제대로 못하면, 157을 겨우 안정화하는 타이밍에 158이 일부 단말로 새어 들어가면서 장애가 재현 불가능한 상태가 됩니다.

Firefox 정책 템플릿은 업데이트 제어와 관련된 여러 정책을 제공합니다. 예를 들어 `AppUpdatePin`, `ManualAppUpdateOnly`, `DisableAppUpdate` 같은 이름이 목록에 보입니다.

- [Policy Templates for Firefox](https://mozilla.github.io/policy-templates/)
- [mozilla/policy-templates (GitHub)](https://github.com/mozilla/policy-templates)

여기서 운영 선택지는 보통 셋입니다.

1) 브라우저 자체 auto-update를 꺼두고(MDM/SCCM/Intune로만 배포) 링을 조직이 완전히 통제
2) auto-update를 유지하되 pin으로 상한 버전을 막고, 검증 완료 시 pin을 올리는 방식
3) 일부 집단만 auto-update 허용(개발자/파워유저), 나머지는 중앙 배포

나는 157 같은 “보안 급 + UX 변동” 릴리스에서 2)번을 선호합니다. 완전 차단은 운영이 단순해 보이지만, 실제로는 배포팀이 병목이 되어 MFSA 대응이 늦어지는 경우가 많습니다.

### 4) 지원(Helpdesk): 공지문보다 먼저 ‘복구 경로’를 확정합니다

157의 지원 플로우에서 중요한 건 “불만을 설득”이 아닙니다. 사용자 입장에서 생산성을 즉시 회복시키는 경로를 마련해야 합니다.

이번 릴리스 노트가 제공하는 공식 복구 경로는 `sidebar.revamp=false`입니다.

- [Firefox 157.0 Release Notes](https://www.firefox.com/en-US/firefox/157.0/releasenotes/)

그리고 조직이 추가로 제공할 수 있는 경로는 두 가지 레벨로 나뉩니다.

- 레벨 A: 공식/지원되는 구성 메커니즘으로 설정을 강제(가능한 범위)
- 레벨 B: about:config 같은 사용자 조작을 KB에 적되, 지원 범위를 명확히 제한

레벨 A에서 핵심이 AutoConfig입니다. Mozilla는 AutoConfig를 “group policy나 policies.json으로 커버되지 않는 preference를 설정/lock하기 위한 방법”으로 설명합니다.

- [Customize Firefox using AutoConfig](https://support.mozilla.org/en-US/kb/customizing-firefox-using-autoconfig)

이 문서가 중요한 이유는, `sidebar.revamp` 같은 pref가 정책 시스템으로는 제어가 어려울 수 있기 때문입니다. 정책의 `Preferences`는 지원되는 pref prefix가 제한됩니다. `browser.` 같은 prefix는 지원되지만, `sidebar.`는 목록에 보이지 않습니다.

- [Preferences policy (Firefox Admin Docs)](https://firefox-admin-docs.mozilla.org/reference/policies/preferences/)
- [policy-templates 문서의 Preferences 항목](https://mozilla.github.io/policy-templates/)

결국 “조직이 sidebar revamp를 기본값으로 강제할지” 같은 결정을 정책만으로 끝내기 어렵고, AutoConfig/패키징/배포 스크립트까지 런북에 포함해야 합니다.

## 자동화 예시: 릴리스 노트 + MFSA + 엔터프라이즈 노트를 한 문서로 합치기

157처럼 기능/UX/보안이 같이 묶인 릴리스는 사람이 링크 세 개를 열어 읽고 요약하는 방식으로는 매번 품질이 흔들립니다. 그래서 나는 배포 파이프라인에서 “런북 초안”을 기계적으로 만들어두고, 사람이 최종 문장만 손보는 형태를 선호합니다.

아래는 현실적인 형태의 초안 생성기입니다.

- 입력: Firefox 버전(157), 릴리스 노트 URL, MFSA URL
- 처리: 주요 섹션을 긁어오고(CVE 목록/enterprise 변화/UX 복구 레버)
- 출력: helpdesk 공지 템플릿과 change ticket에 붙일 Markdown

### 실행 환경

- Python 3.12+
- Windows/macOS/Linux 어디서나 동작(배포 파이프라인 컨테이너에 넣는 용도)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows는 .venv\\Scripts\\activate
pip install -U pip
pip install requests beautifulsoup4 lxml
```

### 스크립트

```python
# ff157_runbook_builder.py
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Iterable

import requests
from bs4 import BeautifulSoup

CVE_RE = re.compile(r"CVE-\\d{4}-\\d+")

@dataclass
class RunbookInputs:
    version: str
    release_notes_url: str
    mfsa_url: str
    enterprise_release_notes_url: str

def fetch_html(url: str) -> str:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text

def extract_text_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    # 화면용 텍스트를 넓게 잡되, 과도한 공백은 정리
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]

def extract_cves(lines: Iterable[str]) -> list[str]:
    found: list[str] = []
    for ln in lines:
        for m in CVE_RE.finditer(ln):
            found.append(m.group(0))
    # 중복 제거(원문에 반복 표기가 있을 수 있음)
    return sorted(set(found))

def pick_lines_containing(lines: list[str], needles: list[str], limit: int = 40) -> list[str]:
    out: list[str] = []
    for ln in lines:
        if any(n in ln for n in needles):
            out.append(ln)
            if len(out) >= limit:
                break
    return out

def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python ff157_runbook_builder.py 157", file=sys.stderr)
        return 2

    version = sys.argv[1]

    inputs = RunbookInputs(
        version=version,
        release_notes_url=f"https://www.firefox.com/en-US/firefox/{version}.0/releasenotes/",
        mfsa_url="https://www.mozilla.org/en-US/security/advisories/mfsa2026-97/",
        enterprise_release_notes_url="https://firefox-admin-docs.mozilla.org/release-notes/",
    )

    rn_lines = extract_text_lines(fetch_html(inputs.release_notes_url))
    mfsa_lines = extract_text_lines(fetch_html(inputs.mfsa_url))
    ent_lines = extract_text_lines(fetch_html(inputs.enterprise_release_notes_url))

    cves = extract_cves(mfsa_lines)

    # UX 복구 레버는 릴리스 노트에 명시된 키워드로만 잡습니다.
    ux_levers = pick_lines_containing(
        rn_lines,
        needles=["sidebar.revamp", "about:config", "Compact", "vertical tabs", "Show sidebar"],
        limit=30,
    )

    # Enterprise 변화는 버전 문자열(157)과 정책 키워드로 좁힙니다.
    ent_hits = [ln for ln in ent_lines if f"Firefox {version}" in ln or "AIControls" in ln or "about:policies" in ln]

    print(f"# Firefox {version} 동시 배포 런북 초안")
    print()
    print("## 보안 요약")
    print(f"- MFSA: {inputs.mfsa_url}")
    print(f"- CVE count (unique): {len(cves)}")
    print("- CVEs (first 10): " + ", ".join(cves[:10]))
    print()

    print("## UX/설정 변화(원문에서 발췌된 키워드 라인)")
    for ln in ux_levers:
        print(f"- {ln}")
    print()

    print("## Enterprise 노트(필터링 결과)")
    for ln in ent_hits[:30]:
        print(f"- {ln}")
    print()

    print("## 배포 공지 초안")
    print(f"Firefox {version} 업데이트가 적용됩니다. 이번 업데이트는 보안 수정(MFSA)과 UI 업데이트(Nova/Sidebar)가 함께 포함됩니다.")
    print("UI가 달라 보이거나 sidebar 동작이 바뀐 경우, 내부 KB의 'sidebar 복구 절차'를 참고합니다.")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

### 실행

```bash
python ff157_runbook_builder.py 157 | tee runbook_draft_ff157.md
```

### 예상 출력(요약)

환경에 따라 HTML 구조가 바뀌면 라인 추출 결과는 달라질 수 있습니다. 아래는 형태를 보여주기 위한 요약 예시입니다.

```text
# Firefox 157 동시 배포 런북 초안

## 보안 요약
- MFSA: https://www.mozilla.org/en-US/security/advisories/mfsa2026-97/
- CVE count (unique): (숫자)
- CVEs (first 10): CVE-2026-100756, CVE-2026-100757, CVE-2026-100758, ...

## UX/설정 변화(원문에서 발췌된 키워드 라인)
- The updated sidebar is now enabled for everyone.
- ... “Show sidebar” option has been removed from Settings.
- ... restored by setting `sidebar.revamp` to `false` in `about:config`.
- ... preference will remain available until the end of 2027.

## Enterprise 노트(필터링 결과)
- Firefox 157
- `AIControls`: Added a `SpeechRecognition` option ...
- about:policies now shows an error for a policy that only partially applied ...
- Notes: Firefox ESR 140 goes out of support with this release ...
```

이 정도 자동화만 있어도, 배포 담당자가 매번 “보안 공지 링크 어디였지 / 엔터프라이즈 노트 어디였지 / 되돌리는 pref가 뭐였지” 같은 작업을 반복하지 않게 됩니다.

## helpdesk 폭증을 줄이는 핵심: ‘되돌리기 레버’를 조직 표준 메커니즘으로 제공

157에서 가장 위험한 장면은 배포 당일입니다.

- UI가 갑자기 바뀐 단말이 생김
- 사용자들은 “업데이트가 됐는지”도 모른 채 불편함만 체감
- helpdesk는 스크린샷을 받고 나서야 Nova/Sidebar를 인지
- 보안팀은 MFSA 때문에 배포 중단을 원하지 않음

즉, 배포팀이 기술적으로 할 수 있는 최선은 “되돌릴 수 있는 레버”를 미리 준비해두는 것입니다.

### 1) `sidebar.revamp=false`는 공식 문서에 있는 레버이지만, 중앙 강제가 애매합니다

릴리스 노트는 `sidebar.revamp=false`를 명시합니다.

- [Firefox 157.0 Release Notes](https://www.firefox.com/en-US/firefox/157.0/releasenotes/)

하지만 정책 시스템의 `Preferences`는 지원하는 pref prefix가 제한됩니다.

- [Preferences policy (Firefox Admin Docs)](https://firefox-admin-docs.mozilla.org/reference/policies/preferences/)

`sidebar.revamp`는 prefix가 `sidebar.`라서, 정책으로는 막히는 가능성이 높습니다. 이때 선택지가 AutoConfig입니다.

Mozilla는 AutoConfig가 “정책으로 커버되지 않는 preference를 set/lock”하기 위한 수단이라고 설명하고, `lockPref()` 같은 함수까지 문서에 정리해 둡니다.

- [Customize Firefox using AutoConfig](https://support.mozilla.org/en-US/kb/customizing-firefox-using-autoconfig)

### 2) AutoConfig로 sidebar를 구형으로 잠그는 구성 예시

다음은 Windows 기준으로, 설치 디렉터리 하위에 두 파일을 배포하는 방식입니다(경로는 Firefox Enterprise 문서 기준).

- `defaults/pref/autoconfig.js`
- 설치 디렉터리 최상위의 `firefox.cfg`

`autoconfig.js`는 LF 줄바꿈이어야 한다는 제약이 있습니다.

- [Customize Firefox using AutoConfig](https://support.mozilla.org/en-US/kb/customizing-firefox-using-autoconfig)

#### 2-1) `defaults/pref/autoconfig.js`

```js
pref("general.config.filename", "firefox.cfg");
pref("general.config.obscure_value", 0);
```

#### 2-2) 설치 디렉터리의 `firefox.cfg`

```js
// IMPORTANT: Start your code on the 2nd line

// Firefox 157에서 sidebar/vertical tabs 변화가 업무에 직접 타격이 있는 집단만 임시로 적용
lockPref("sidebar.revamp", false);
```

이 방식의 운영 포인트는 두 가지입니다.

- “전체 조직”이 아니라 “업무 영향이 큰 집단”에게만 제한적으로 적용하는 게 현실적입니다.
- Mozilla가 `sidebar.revamp`를 2027년 말까지 유지한다고 했으니, 임시 완화책으로서의 수명은 비교적 길어 보입니다.

다만 이건 어디까지나 Nova 전체를 되돌리는 레버가 아닙니다. sidebar/vertical tabs 동선 문제를 줄이기 위한 조치입니다.

### 3) Nova 자체를 되돌리는 about:config 레버는 런북에 넣을 수는 있지만, ‘지원 범위’를 제한해야 합니다

커뮤니티 스레드에서는 `browser.nova.enabled` 같은 preference로 되돌리는 이야기가 반복됩니다.

- [r/firefox: The new UX design (Nova) lands in Firefox today](https://www.reddit.com/r/firefox/comments/1wt9ig4/the_new_ux_design_nova_lands_in_firefox_today/)

이 값은 prefix가 `browser.`라서 정책 `Preferences`의 지원 prefix에 들어가며, 기술적으로는 lock 가능할 여지가 있습니다.

- [Preferences policy (Firefox Admin Docs)](https://firefox-admin-docs.mozilla.org/reference/policies/preferences/)

그렇지만 Mozilla의 공식 릴리스/Connect 공지의 뉘앙스는 “새 디자인이 기본값이 되었고, opt-out이라기보다는 Compact mode/테마/커스터마이징으로 조정하라”에 가깝습니다.

- [Mozilla Connect: The new Firefox design lands in today](https://connect.mozilla.org/t5/discussions/the-new-firefox-design-lands-in-today-this-is-what-you-can/td-p/139524)

그래서 런북에 넣더라도 다음처럼 취급하는 편이 맞습니다.

- 조직 표준 레버: `sidebar.revamp=false` (공식 릴리스 노트에 있음)
- 조건부 레버: `browser.nova.enabled` (커뮤니티 기반, 향후 제거/동작 변경 가능)

이 구분을 문서에서 흐리면, 나중에 158/159에서 preference가 사라졌을 때 helpdesk가 “지난번엔 됐는데 이번엔 왜 안 되냐”를 그대로 떠안게 됩니다.

## 반론과 회의론: 보안 패치에 UI 리프레시를 얹는 방식의 비용

이번 릴리스 흐름에 대해 조직 배포 관점에서 나올 수 있는 반론은 대략 두 가지입니다.

### 1) “보안 패치만 따로 내면 되지 않나”

조직 배포자가 보기엔 당연한 요구입니다. 하지만 Firefox의 배포 단위가 버전이고, MFSA도 “Firefox 157에서 fixed”라고 명시하는 구조라면, 엔터프라이즈 입장에서는 사실상 선택지가 제한됩니다.

- [MFSA 2026-97](https://www.mozilla.org/en-US/security/advisories/mfsa2026-97/)

대안은 dot release(예: 156.0.1)에 백포트된 보안 픽스가 나오는지 기다리는 것인데, 그건 조직이 통제할 수 있는 변수가 아닙니다. 그래서 런북은 “보안만 따로 배포”가 아니라 “동시 배포를 흡수”하는 형태가 되어야 합니다.

### 2) “UI 변경은 사용자 반발이 심해서 배포를 늦춰야 한다”

157은 UI 변경이 크기 때문에, 배포를 늦추고 싶어지는 게 정상입니다. 그러나 MFSA가 high impact로 묶여 있는 이상, 배포를 늦추는 순간 보안 리스크를 감수하는 시간이 늘어납니다.

결국 현실적인 절충은 다음입니다.

- 보안 패치 적용 속도는 유지
- 대신 helpdesk 부하를 운영적으로 선제 흡수
  - FAQ 문장(어디가 바뀌었는지)
  - 복구 레버(공식: `sidebar.revamp=false`)
  - 표준 커스터마이징(Compact mode를 기본 안내로 포함)

즉 “배포 속도”를 늦추는 게 아니라 “배포 산출물”을 늘려서 비용을 앞단에서 지불하는 쪽이 맞습니다.

## 앞으로 지켜볼 것: 158 이후의 안정화 포인트와 advisory 방식 변화

157을 런북으로 흡수했다고 끝이 아닙니다. 다음 관찰 포인트가 남습니다.

### 1) `sidebar.revamp`의 수명과 정책화 가능성

Mozilla는 2027년 말까지 preference를 유지한다고 말했습니다.

- [Firefox 157.0 Release Notes](https://www.firefox.com/en-US/firefox/157.0/releasenotes/)

이 문장은 “그 이후에는 제거될 수 있다”는 의미이기도 합니다. 조직은 2027년 말이 오기 전에, sidebar/vertical tabs 기반의 표준 가이드로 문서를 업데이트하거나, 해당 집단의 작업 동선을 Nova 기준으로 다시 설계해야 합니다.

### 2) 테마/vertical tabs에서 생길 수 있는 후속 수정

Add-ons 블로그 글에는 “Firefox 157에서 hover로 확장되는 sidebar가 theme background를 표시하지 않을 수 있고, 158에서 fix 된다” 같은 후속 수정 언급이 있습니다.

- [Nova is here: what changes for your Firefox theme](https://blog.mozilla.org/addons/2026/09/29/nova-is-here-what-changes-for-your-firefox-theme/)

이런 종류의 이슈는 배포 직후에 “왜 우리 조직 테마가 깨졌냐” 티켓으로 들어오기 쉬우니, 157 런북에 “158에서 수정될 수 있는 known issue 후보”를 섹션으로 따로 두는 게 좋습니다.

### 3) MFSA 발행 방식 변경이 의미하는 것

MFSA 2026-97에는 advisory 발행 방식을 바꿨다는 문장이 들어가 있습니다.

- [MFSA 2026-97](https://www.mozilla.org/en-US/security/advisories/mfsa2026-97/)

이게 운영에 미치는 영향은, 앞으로 CVE 수가 더 잘게 쪼개져 보이면서 “이번 버전은 CVE가 왜 이렇게 많지”라는 오해가 생길 수 있다는 점입니다. 보안팀과 배포팀 사이 커뮤니케이션에서는 ‘개수’가 아니라 ‘impact’와 ‘유형(예: sandbox escape)’을 중심으로 요약하는 템플릿이 필요합니다.

## 결론: 157은 ‘브라우저 업데이트’가 아니라 ‘동시 배포 운영 능력’ 테스트입니다

Firefox 157(2026-09-29)은 Nova UI 리프레시와 MFSA 2026-97 high impact 보안 수정이 한 버전으로 결박된 릴리스입니다. 조직 배포 관점에서 이 조합은 피할 수 없고, 분리 배포도 어렵습니다.

따라서 156 → 157 런북은 릴리스 노트와 MFSA 링크를 나열하는 수준을 넘어서야 합니다.

- 엔터프라이즈 정책 변화(AIControls, about:policies 관찰성 개선, ESR 140 지원 종료)를 change ticket에 포함시키고
- 사용자 경험 변화(sidebar/vertical tabs/Compact mode)를 helpdesk FAQ와 복구 레버로 구체화하고
- 정책으로 해결되지 않는 pref는 AutoConfig까지 포함해 운영 표준 메커니즘으로 제공하는 형태로 묶는 게 비용이 가장 덜 듭니다.

이렇게 묶으면, 157 같은 릴리스에서 “보안 때문에 빨리 해야 하지만 UX 때문에 무섭다”는 갈등이 문서/절차 차원에서 정리되고, 배포는 사건이 아니라 반복 가능한 운영으로 수렴합니다.

## 참고 자료

- [Firefox 157.0 Release Notes](https://www.firefox.com/en-US/firefox/157.0/releasenotes/)
- [MFSA 2026-97: Security Vulnerabilities fixed in Firefox 157](https://www.mozilla.org/en-US/security/advisories/mfsa2026-97/)
- [Firefox Release Notes for Enterprise](https://firefox-admin-docs.mozilla.org/release-notes/)
- [Mozilla Connect: The new Firefox design lands in today](https://connect.mozilla.org/t5/discussions/the-new-firefox-design-lands-in-today-this-is-what-you-can/td-p/139524)
- [Nova is here: what changes for your Firefox theme](https://blog.mozilla.org/addons/2026/09/29/nova-is-here-what-changes-for-your-firefox-theme/)
- [Firefox new release cadence and what to expect](https://blog.mozilla.org/sumo/2026/08/19/firefox-new-release-cadence-and-what-to-expect/)
- [MDN: Firefox 157 release notes for developers](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/157)
- [Customize Firefox using Group Policy (Windows)](https://support.mozilla.org/en-US/kb/customizing-firefox-using-group-policy-windows)
- [Configuring policies (Firefox Admin Docs)](https://firefox-admin-docs.mozilla.org/guides/policies-configuration/)
- [Preferences policy (Firefox Admin Docs)](https://firefox-admin-docs.mozilla.org/reference/policies/preferences/)
- [Policy Templates for Firefox](https://mozilla.github.io/policy-templates/)
- [Customize Firefox using AutoConfig](https://support.mozilla.org/en-US/kb/customizing-firefox-using-autoconfig)
- [r/firefox: The new UX design (Nova) lands in Firefox today](https://www.reddit.com/r/firefox/comments/1wt9ig4/the_new_ux_design_nova_lands_in_firefox_today/)
- [Firefox 156을 배포 파이프라인에 넣는 계약 설계](https://daewooki.github.io/posts/firefox-release-pipeline-contracts/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
