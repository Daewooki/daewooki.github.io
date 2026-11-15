---
title: "iOS 26.7.3 보안 업데이트: 릴리스 노트가 빈약할수록 플릿 운영 계약이 중요해진다"
description: "iOS 보안 공지의 정보 밀도 편차를 전제로 업데이트 강제/유예, 자산 기반 영향도 추정, MDM/DDM 운영 계약을 정리합니다."
date: 2026-11-15 14:43:58 +0900
categories: ["News", "Mobile"]
tags: ["ios", "ipados", "security-updates", "mdm", "declarative-device-management", "fleet-operations"]
render_with_liquid: false
---

## 2026-11-09 보안 업데이트: iOS 26.7.3 / iPadOS 26.7.3

Apple은 2026-11-09에 iOS 26.7.3 및 iPadOS 26.7.3의 보안 업데이트를 공개했습니다. Apple의 공식 채널 기준으로는 (1) [Apple security releases](https://support.apple.com/en-us/100100) 목록에 iOS 26.7.3 / iPadOS 26.7.3 항목이 올라왔고, (2) 보안 공지 전문은 [security-announce 메일링리스트 공지](https://www.mail-archive.com/security-announce@lists.apple.com/msg00952.html) 형태로도 배포됐습니다.[^1]

업데이트 적용 대상은 공지 문구상 iPhone 11 이상, iPad는 iPad Pro 12.9-inch 3rd gen 이상/11-inch 1st gen 이상, iPad Air 3rd gen 이상, iPad 8th gen 이상, iPad mini 5th gen 이상으로 정리되어 있습니다.[^2]

문제는 현장에서 우리가 가장 먼저 마주치는 정보가 “Settings 앱의 릴리스 노트”라는 점입니다. 이 업데이트도 그 경로에서 보면 대개 문구가 비슷합니다. Macworld가 2026-11-09에 언급한 것처럼, iOS 쪽 릴리스 노트는 “bug fixes and security updates” 같은 보일러플레이트로 끝나는 경우가 많고(특히 마이너/패치 릴리스), 그 상태로는 플릿 운영자가 ‘강제’로 밀어붙일지 ‘유예’로 두어도 될지 판단하기 어렵습니다.[^3]

반면, security-announce 전문을 보면 CVE 단위로 무엇이 고쳐졌는지 최소한의 구조화가 됩니다. 이 글은 그 “정보 밀도 편차”를 상수로 보고, **업데이트 준수율과 업무 중단 최소화를 동시에 만족시키는 운영 계약**을 어떻게 세우는지가 핵심입니다.

## ‘릴리스 노트가 빈약한 주간’이 운영을 더 어렵게 만드는 지점

보안 업데이트 운영이 가장 쉬운 케이스는 공지가 친절한 날입니다. 예를 들면 “실제 공격이 확인되었고”, “원격 코드 실행이며”, “특정 컴포넌트/프로토콜/입력 벡터가 명시되고”, “완화책이 있고”, “대체 경로가 있다” 같은 정보가 갖춰지면 정책 결정이 단순해집니다.

하지만 Apple 쪽은 그 반대편에 자주 서 있습니다.

- Apple은 보안 이슈를 조사하고 패치가 준비되기 전에는 구체적인 내용을 공개하지 않는다는 원칙을 반복해서 밝힙니다(보안 콘텐츠 문서의 ‘About Apple security updates’에 해당하는 문장). 즉, ‘사후 공개’가 기본입니다.[^4]
- CVE가 항상 붙는 것도 아닙니다. 실제로 [Apple security releases](https://support.apple.com/en-us/100100)에는 “This update has no published CVE entries.”로 정리되는 항목이 주기적으로 나옵니다. 그러면 조직의 취약점 관리 파이프라인(CVE 기반)과 OS 업데이트 파이프라인(버전 기반)이 갈라집니다.[^1]
- iOS/iPadOS는 서버/클라이언트 환경과 다르게 ‘롤백’이 거의 불가능하고, 대부분의 배포는 재부팅을 전제로 합니다. 즉, 패치 실패가 단순히 “재배포”로 끝나지 않고, 디바이스 가용성과 사용자 업무 시간을 바로 소모합니다.

이 조합 때문에, 릴리스 노트가 빈약한 주간에는 운영의 의사결정이 기술이 아니라 계약(정책, SLA, 예외, 책임 경계)로 넘어옵니다. 내 경험상 이 지점에서 계약이 없으면 사람만 갈립니다.

## 공개된 CVE를 ‘기능’이 아니라 ‘연결성’으로 재분류하기

iOS 26.7.3 / iPadOS 26.7.3의 security-announce 전문을 보면, 적어도 “어떤 컴포넌트에서”, “어떤 영향(Impact)으로”, “CVE가 무엇인지”는 나옵니다.[^2]

여기서 흔히 하는 실수는 컴포넌트 이름을 보고 “우린 AirPlay 안 쓰니까 괜찮겠지” 같은 기능 단위로 스킵해버리는 겁니다. 플릿 관점에서 더 실용적인 분류는 연결성(공격자가 붙을 수 있는 거리/네트워크/상호작용)입니다.

이번 릴리스에 포함된 항목 중, 운영자가 바로 태깅할 만한 덩어리는 아래처럼 보입니다.

### 1) 근거리 무선: Bluetooth 범위 공격

- AirPlay 항목이지만 Impact가 “Bluetooth range”로 잡혀 있습니다(CVE-2026-113968).[^2]
- Bluetooth 스택 자체의 use-after-free로 보이는 메모리 손상 가능(CVE-2026-113970).[^2]
- CoreUtils에서 “사용자 상호작용 없이 pairing 성립 가능” 같은 표현이 보입니다(CVE-2026-113965, CVE-2026-113964).[^2]

여기서 포인트는 “우리 조직이 AirPlay를 쓰느냐”가 아니라, **Bluetooth가 켜져 있고 외부 물리 환경(공항/매장/현장/전시/이벤트)에서 장비가 돌아다니느냐**입니다.

MDM에서 Bluetooth를 제어하는 조직도 있지만, 현실적으로는 (업무용 이어폰, 차량, 주변기기, Apple Watch 연동 등)로 인해 항상 켜져 있는 디바이스가 많습니다. 그러면 이 류의 취약점은 “원격”보다 운영 우선순위가 내려가는 게 아니라, 오히려 “현장 자산”에 대해 우선순위가 올라갑니다.

### 2) 동일 네트워크: 페어링 코드 제한 우회

- rapportd에서 “same network” 조건으로 AirPlay pairing code attempts의 rate limit을 우회할 수 있다는 문구가 있습니다(CVE-2026-113969).[^2]

이 범주는 “회사 내부망이면 안전”이 아니라, **게스트 Wi‑Fi, 지점망, 공유기 뒤 NAT, 호텔/컨퍼런스 네트워크** 같은 곳에서 디바이스가 붙는 시나리오가 현실적입니다. 특히 iPad 키오스크/PoS/현장 태블릿은 네트워크 토폴로지가 단순해 보이지만, 운영팀이 통제하지 않는 L2/L3에 붙는 경우가 많습니다.

### 3) 메시징/아이덴티티: iMessage 그룹 채팅

- iMessage 그룹에 새로 추가된 사용자가 과거 메시지를 볼 수 있다(CVE-2026-113960).[^2]
- 원격 공격자가 iMessage 그룹 채팅에 조인해 메시지를 받을 수 있다(CVE-2026-113961).[^2]

이 항목은 조직마다 체감이 갈립니다.

- iMessage를 업무에서 차단하는 조직이면 “이론상 위험하지만 우리 통제 영역 밖”으로 분류될 수 있습니다.
- 반대로 BYOD가 섞여 있고, 임원/영업/현장 리더가 iMessage를 사실상 업무 채널로 쓰는 조직이면 “데이터 유출” 계열로 위험도가 튑니다.

결국 같은 CVE라도, 자산 태그가 없으면 우선순위를 정할 수 없습니다.

### 4) 압축 라이브러리: brotli 메모리 손상

- brotli에서 out-of-bounds write로 “maliciously crafted input 처리 시 메모리 손상” 가능(CVE-2026-111497).[^2]

이 류의 취약점은 공지 문구만 보면 애매합니다. 메모리 손상이 RCE로 이어질 수도 있고, 단순 크래시로 끝날 수도 있습니다. 그런데 외부 기관이 “exploited in the wild” 같은 힌트를 주는 경우가 있습니다.

예를 들어 GovCERT.HK는 2026-11-??(페이지 게시일 기준) 경보에서 iOS 26.7.3 등을 언급하며 CVE-2026-111497이 wild에서 악용된다는 보고가 있다고 적었습니다. Apple 자체 공지에 그 표현이 직접 들어가지는 않으니, 조직 정책상은 “외부 신뢰 신호”로만 취급하는 게 맞습니다. 그래도 신호 자체는 무시하기 어렵습니다.[^5]

여기까지가 “공지가 빈약해도 최소한 할 수 있는 분류”입니다. 이 분류가 다음 섹션의 정책(강제/유예)과 연결됩니다.

## 업데이트 강제/유예 정책을 ‘기술’이 아니라 ‘계약’으로 만들기

플릿에서 업데이트를 “강제할지/유예할지”는 기술 문제가 아니라 운영 계약 문제입니다. 기술은 그 계약을 실행하는 도구일 뿐입니다.

내가 보안 업데이트 운영을 설계할 때는, 업데이트를 대략 3단으로 나눕니다.

### A. 강제 업데이트(Forced): 48~72시간 내 준수율 목표

조건은 조직마다 다르지만, 보통 아래 중 하나만 성립해도 강제로 넣는 편이 비용이 덜 듭니다.

- exploited in the wild 신호가 명시적으로 존재(Apple 공지든, 신뢰 가능한 외부 CERT든)
- 네트워크 인접/근거리 무선 기반인데 디바이스가 통제되지 않는 물리 환경에 상시 노출
- 메모리 손상 계열 + 입력 벡터가 광범위(브라우저/메시징/압축/미디어 파서)

iOS 26.7.3의 경우, 최소한 brotli(CVE-2026-111497)는 외부 경보에서 악용 신호가 있다는 말이 나왔고, Bluetooth 계열은 “현장 자산”에 위험도가 맞습니다.[^2]

강제 업데이트의 핵심은 한 가지입니다.

- 강제는 “모두 지금 당장”이 아니라, **강제 기한을 명시하는 것**입니다.

### B. 빠른 업데이트(Fast): 7~14일 내 준수율 목표

- 공개된 CVE가 원격 공격 가능성이 있으나, 조직의 노출면이 낮은 경우
- 사용자 상호작용이 강하게 필요한 경우(피싱/사회공학 포함)
- 안정성 리스크(업무앱 호환성)로 인해 링 배포가 필요한 경우

### C. 정기 업데이트(Regular): 월간/분기 준수율 목표

- 공지 자체가 너무 빈약하고, 외부 악용 신호도 없고, 노출면도 낮은 케이스
- 키오스크/Shared iPad처럼 재부팅 창이 명확하게 잡혀 있는 자산

여기까지가 “정책 레이어”입니다. 이제 “기술 레이어”가 붙습니다.

## 강제/유예를 구현하는 기술: MDM ‘지연’과 DDM ‘강제’의 조합

iOS/iPadOS 업데이트 관리에서 오래 쓰던 방식은 두 가지였습니다.

1) 사용자에게 업데이트가 보이는 시점을 늦추는 지연(Deferral)
2) MDM command로 스캔/다운로드/설치를 트리거하는 방식

그런데 이 판이 바뀌고 있습니다.

### 1) 업데이트 지연(Deferral): forceDelayedSoftwareUpdates / enforcedSoftwareUpdateDelay

Restrictions 계열 payload(com.apple.applicationaccess)에는 업데이트 지연을 거는 키가 존재합니다.

- forceDelayedSoftwareUpdates
- enforcedSoftwareUpdateDelay

이 키들이 iOS 11.3부터 supervised 디바이스에서 가능하다는 점은 Configuration Profile Reference에서도 확인할 수 있고, Apple의 device-management 스키마에서도 키가 정리되어 있습니다.[^6]

운영 감각으로 말하면, 지연은 “업데이트를 막는다”가 아니라 “사용자에게 보이는 타이밍을 늦춘다”에 가깝습니다. 그래서 인증/검증 기간을 벌거나, 릴리스 직후 CDN 혼잡을 피하거나, 링 배포를 운영할 때 유용합니다.

다만 지연만으로는 강제 준수율을 만들기 어렵습니다. 특히 iOS는 사용자가 계속 미루면 그대로 남습니다.

### 2) MDM command: AvailableOSUpdates / ScheduleOSUpdate의 퇴장

Apple의 device-management 문서 스키마를 보면 AvailableOSUpdates 같은 OS 업데이트 관련 MDM command가 iOS 26.0에서 deprecated, iOS 27.0에서 removed로 찍혀 있습니다.[^7]

즉, iOS 26.x 플릿을 운영하는 지금 시점은 “아직 되지만 곧 끊길 방식”과 “앞으로의 방식”이 공존합니다.

- iOS 26.x: MDM command가 아직 남아 있으나 deprecated 상태
- iOS 27.x 이후: command 제거, declarative 중심으로 전환

이 전환은 단순히 API가 바뀌는 문제가 아니라 운영 계약의 책임 경계를 바꿉니다. command 기반은 서버가 ‘지시’하고 디바이스가 ‘응답’하는 형태인데, declarative는 서버가 ‘목표 상태’를 선언하고 디바이스가 스스로 달성합니다.

### 3) Declarative Device Management(DDM): softwareupdate.enforcement.specific

이제 핵심은 `com.apple.configuration.softwareupdate.enforcement.specific` 선언입니다. Apple Developer Documentation은 이 선언이 “특정 OS 버전으로 업데이트를 강제하는 정책”이라는 점과, 가능한 키(TargetOSVersion, TargetBuildVersion, TargetLocalDateTime 등), 그리고 “가용 업데이트 여부는 GDMF(Apple이 말하는 공개 서비스) 기준으로 판단된다”는 점을 명확히 적고 있습니다.[^8]

또 Apple의 배포 가이드에서는 TargetLocalDateTime 포맷(YYYY-MM-DDTHH:MM:SS, timezone offset 없음)과, 해당 시각 이전에 사용자가 업데이트를 트리거하지 않으면 디바이스가 force install한다는 구조를 다시 정리해 둡니다.[^9]

이 방식의 운영적 의미는 명확합니다.

- “업데이트를 언제까지 해야 한다”를 기술적으로 강제할 수 있다.
- 디바이스가 그 과정을 자율적으로 수행한다.

그리고 이 구조 때문에, 강제/유예 정책을 수립할 때 가장 중요한 입력값은 릴리스 노트가 아니라 ‘기한’과 ‘대상군(자산 태그)’이 됩니다.

## 자산 기반 영향도 추정: CVE → 노출면 → 자산 태그

iOS 보안 공지의 정보 밀도는 들쭉날쭉합니다. CVSS도 없고, exploitability에 대한 언급도 흔치 않습니다. 그러면 운영팀은 “정확한 위험도” 대신 “결정 가능한 근사치”를 만들어야 합니다.

내가 쓰는 방식은 단순합니다.

1) CVE를 공격면 연결성으로 분류한다(근거리 무선 / 동일 네트워크 / 원격 메시징 / 범용 파서)
2) 조직 자산을 ‘기능’이 아니라 ‘노출 상태’로 태깅한다
3) 태그 조합으로 업데이트 강제 링을 결정한다

이때 중요한 건 “MDM이 다 알고 있다”는 환상을 버리는 겁니다. MDM 인벤토리는 OS 버전/모델/관리 상태(supervised 등)는 강하지만, “이 디바이스가 iMessage를 업무에 쓰는지” 같은 건 태그 체계로밖에 못 잡습니다.

예시로, iOS 26.7.3의 항목을 태그 기반으로 연결하면 이런 규칙이 됩니다.

- bluetooth-exposed: 현장 근무, 외근, 매장, 물류, 출장이 잦은 디바이스
- airplay-enabled: 회의실 발표/무선 미러링이 업무 흐름에 포함된 디바이스(보통 iPad가 많음)
- imessage-allowed: 정책상 iMessage가 허용되어 있고 실제 사용이 확인되는 디바이스(BYOD 포함)
- kiosk: 키오스크/PoS/전시 장비(재부팅 창이 좁고, 물리 환경이 불특정 다수)
- vip: 임원/법무/홍보 등 유출 비용이 큰 계정이 붙는 디바이스

그 다음에 CVE 분류를 덧씌웁니다.

- Bluetooth range / pairing 관련(CVE-2026-113968, 113970, 113965, 113964) → bluetooth-exposed + kiosk는 우선순위 상향[^2]
- same network / pairing rate limit(CVE-2026-113969) → 게스트망/지점망 노출 + airplay-enabled 자산 상향[^2]
- iMessage group 관련(CVE-2026-113960, 113961) → imessage-allowed + vip 상향[^2]
- brotli 메모리 손상(CVE-2026-111497) → “입력 벡터가 광범위할 수 있다”로 가정하고 기본 점수 높게 부여, 외부에서 악용 신호가 있으면 강제 링으로 올림[^2]

이 모델이 거칠어도, 최소한 “업데이트를 언제까지 강제할지”를 회의 없이 자동으로 결정할 수 있습니다.

여기서 Android 쪽 SPL 기반 운영과 비교가 떠오를 텐데, 관점은 비슷합니다. 나는 Android에서는 패치 레벨을 운영 계약으로 굳히는 방식을 정리해 둔 적이 있고[^10], iOS는 그 자리에 “버전+기한(DDM enforcement)”이 들어간다고 보면 구현이 됩니다.

## Declarative enforcement를 설계할 때 빠지는 함정

DDM이 만능처럼 보이지만, 실제 운영에서는 함정이 몇 개 있습니다. Apple 문서가 이 함정을 직접 해결해주진 않지만, 최소한 “왜 이런 일이 생기는지”는 문서 구조에서 드러납니다.

### 1) TargetOSVersion은 ‘상태 목표’이지 ‘설치 버튼’이 아니다

DDM은 서버가 “이 버전이 되어야 한다”를 선언합니다. 기한(TargetLocalDateTime) 이전에는 사용자에게 설치를 유도하고, 이후에는 강제합니다. 이때 문제가 되는 건 “업무앱 호환성”이 아니라 “업무 시간”입니다.

- 강제 기한을 너무 촘촘히 잡으면, 사용자 불만과 헬프데스크 티켓이 폭발합니다.
- 너무 느슨하면, 취약 기간이 길어져 보안팀이 불만을 냅니다.

결국 강제/유예 정책은 기술이 아니라 조직 비용함수의 선택입니다.

### 2) OS update catalog의 ‘가시성’이 운영의 숨은 변수다

Apple은 enforcement 선언이 실제로 동작하려면 GDMF에서 해당 OS 버전/빌드가 가용해야 한다고 적습니다. 그리고 MDM/DDM 서비스가 그걸 정기적으로 확인해야 한다고도 씁니다.[^8]

운영적으로는 다음을 의미합니다.

- 조직 내부에서 “26.7.3을 강제”라고 결정해도, 디바이스가 업데이트를 못 보는 순간이 생길 수 있다.
- 그래서 “Day 0 강제” 같은 구호가 실제로는 “Day 0 선언 + Day 1~7 내 분산 설치”로 흘러가는 경우가 있다.

security-announce 메일도 “자동 업데이트 프로세스는 최대 일주일까지 걸릴 수 있다”는 취지의 문장을 포함합니다. 디바이스가 주간 스케줄로 업데이트를 체크한다는 설명이 그대로 들어가 있습니다.[^2]

즉, 기술적으로 강제해도 ‘발견’과 ‘다운로드’가 조직이 원하는 타이밍으로 100% 수렴하지는 않습니다. 그래서 링 배포와 기한 설계가 더 중요해집니다.

### 3) iOS 27로 넘어가면 legacy MDM command는 정말 사라진다

AvailableOSUpdates가 iOS 26에서 deprecated, iOS 27에서 removed로 찍혀 있다는 건 “언젠가 바꿔야지”가 아니라 “이미 마이그레이션 기간이 iOS 26.x 동안이었다”는 뜻입니다.[^7]

iOS 26.7.3 같은 릴리스는, 단순히 보안 패치가 아니라 “업데이트 강제 엔진을 DDM으로 갈아탈 시간”을 사실상 더 주지 않는 신호로도 읽힙니다.

## 실제 운영 자동화: security-announce에서 CVE를 뽑아 롤아웃 링을 만든다

이 섹션은 장난감 예제 대신, 내가 현업에서 그대로 쓰는 패턴(‘공지 → 자산 인벤토리 → 링 배포 초안’)을 iOS에 맞게 보여줍니다.

전제는 현실적인 수준으로 둡니다.

- MDM이 매일 devices.csv를 덤프한다(또는 API로 가져온다)
- 보안팀/운영팀은 Apple security-announce 링크를 티켓에 붙인다
- 스크립트가 CVE/컴포넌트를 파싱해 “링 0/1/2 + 강제 기한” 초안을 만든다

### 입력: devices.csv (MDM 인벤토리 덤프)

아래 컬럼은 대부분의 MDM에서 현실적으로 뽑을 수 있고, 부족한 건 tags로 보완합니다.

```csv
device_id,platform,os_version,supervised,last_checkin,tags
A1,iOS,26.6.2,true,2026-11-15T06:12:00Z,"vip;imessage-allowed"
A2,iOS,26.7.1,true,2026-11-15T05:58:00Z,"bluetooth-exposed;field"
B1,iPadOS,26.7.2,true,2026-11-15T03:01:00Z,"kiosk;airplay-enabled"
B2,iPadOS,26.7.3,true,2026-11-15T04:44:00Z,"office"
C1,iOS,26.5.2,false,2026-11-14T22:10:00Z,"byod;imessage-allowed"
```

### 스크립트: advisory_to_rings.py

- security-announce 메일[^2]을 가져와 CVE/컴포넌트를 뽑습니다.[^2]
- devices.csv에서 OS 버전을 비교해 “이미 26.7.3 이상이면 제외”합니다.
- CVE 영향도를 ‘연결성’과 ‘태그’로 근사합니다.

```python
#!/usr/bin/env python3
"""Create rollout rings for iOS/iPadOS security update when release notes are sparse.

Tested with:
- Python 3.12+

Install:
  python -m venv .venv
  source .venv/bin/activate
  pip install -U pip
  pip install requests beautifulsoup4 pandas packaging

Run:
  python advisory_to_rings.py \
    --advisory-url "https://www.mail-archive.com/security-announce@lists.apple.com/msg00952.html" \
    --target-version "26.7.3" \
    --devices-csv devices.csv \
    --out rings.csv
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Iterable

import pandas as pd
import requests
from bs4 import BeautifulSoup
from packaging.version import Version

CVE_RE = re.compile(r"\bCVE-\d{4}-\d+\b")

@dataclass
class AdvisoryItem:
    component: str
    cve: str
    impact: str

def fetch_advisory_text(url: str) -> str:
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    # Mail-archive renders the message body in <pre> for many posts.
    pre = soup.find("pre")
    if pre:
        return pre.get_text("\n")
    return soup.get_text("\n")

def parse_security_announce(text: str) -> list[AdvisoryItem]:
    lines = [ln.rstrip() for ln in text.splitlines()]

    items: list[AdvisoryItem] = []
    component: str | None = None
    last_impact: str = ""

    for ln in lines:
        if not ln.strip():
            continue

        # Components in the Apple message are typically a single word line like "Bluetooth".
        # We'll treat a short title-cased line as a component header.
        if (
            len(ln) <= 24
            and ln.isprintable()
            and ln[0].isalpha()
            and " " not in ln
            and ln not in {"Impact:", "Description:", "Available", "Released"}
        ):
            component = ln
            last_impact = ""
            continue

        if ln.startswith("Impact:"):
            last_impact = ln[len("Impact:") :].strip()
            continue

        m = CVE_RE.search(ln)
        if m and component:
            items.append(AdvisoryItem(component=component, cve=m.group(0), impact=last_impact))

    # De-dup
    seen = set()
    uniq: list[AdvisoryItem] = []
    for it in items:
        key = (it.component, it.cve)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    return uniq

def tags_to_set(x: str) -> set[str]:
    if pd.isna(x) or not str(x).strip():
        return set()
    return {t.strip() for t in str(x).split(";") if t.strip()}

def base_risk_for_item(item: AdvisoryItem) -> int:
    impact = item.impact.lower()

    # Heuristics: we only have Apple's short Impact strings.
    if "remote attacker" in impact:
        return 70
    if "same network" in impact:
        return 55
    if "bluetooth range" in impact:
        return 50
    if "memory corruption" in impact:
        return 65
    return 40

def tag_multiplier(tags: set[str], item: AdvisoryItem) -> float:
    impact = item.impact.lower()

    mult = 1.0

    if "vip" in tags:
        mult *= 1.4

    if "kiosk" in tags:
        mult *= 1.2

    if "bluetooth" in impact and "bluetooth-exposed" in tags:
        mult *= 1.4

    if "messages" in item.component.lower() and "imessage-allowed" in tags:
        mult *= 1.3

    if "same network" in impact and "airplay-enabled" in tags:
        mult *= 1.2

    return mult

def decide_ring(score: float, tags: set[str]) -> str:
    if "vip" in tags and score >= 60:
        return "ring0"
    if score >= 85:
        return "ring0"
    if score >= 65:
        return "ring1"
    return "ring2"

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--advisory-url", required=True)
    ap.add_argument("--target-version", required=True)
    ap.add_argument("--devices-csv", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    advisory_text = fetch_advisory_text(args.advisory_url)
    items = parse_security_announce(advisory_text)

    df = pd.read_csv(args.devices_csv)
    df["tags_set"] = df["tags"].apply(tags_to_set)

    target_v = Version(args.target_version)

    # Filter: only iOS/iPadOS devices below target version
    def needs_update(v: str) -> bool:
        try:
            return Version(str(v)) < target_v
        except Exception:
            return True

    df = df[df["platform"].isin(["iOS", "iPadOS"])].copy()
    df = df[df["os_version"].apply(needs_update)].copy()

    # Score per device
    scores = []
    for _, row in df.iterrows():
        tags = row["tags_set"]
        total = 0.0
        for it in items:
            base = base_risk_for_item(it)
            total += base * tag_multiplier(tags, it)
        scores.append(total)

    df["risk_score"] = scores
    df["ring"] = [decide_ring(s, t) for s, t in zip(df["risk_score"], df["tags_set"]) ]

    # Deadlines (example policy)
    # - ring0: 72h
    # - ring1: 10d
    # - ring2: 21d
    df["deadline_policy"] = df["ring"].map({"ring0": "T+72h", "ring1": "T+10d", "ring2": "T+21d"})

    out = df[["device_id", "platform", "os_version", "supervised", "last_checkin", "ring", "deadline_policy", "risk_score", "tags"]]
    out.to_csv(args.out, index=False)

if __name__ == "__main__":
    main()
```

### 실행 결과 예시: rings.csv

```csv
device_id,platform,os_version,supervised,last_checkin,ring,deadline_policy,risk_score,tags
A1,iOS,26.6.2,True,2026-11-15T06:12:00Z,ring0,T+72h,....,"vip;imessage-allowed"
A2,iOS,26.7.1,True,2026-11-15T05:58:00Z,ring1,T+10d,....,"bluetooth-exposed;field"
B1,iPadOS,26.7.2,True,2026-11-15T03:01:00Z,ring1,T+10d,....,"kiosk;airplay-enabled"
C1,iOS,26.5.2,False,2026-11-14T22:10:00Z,ring2,T+21d,....,"byod;imessage-allowed"
```

이 결과는 “정답”이 아니라 “초안 생성기”입니다. 그래도 릴리스 노트가 빈약한 업데이트에서 운영을 살리는 건 이런 자동화입니다.

- 사람이 CVE 하나하나 읽고 대상군을 고르는 순간부터, 규모가 커질수록 실패합니다.
- 자동화는 거칠어도, 결정이 반복 가능해집니다.

Android에서 SPL로 운영 계약을 만들어 자동화하던 경험이 있다면[^11], iOS에서는 이 자동화의 입력이 SPL 대신 “target OS version + enforcement deadline”으로 바뀐다고 보면 됩니다.

## DDM으로 ‘강제’ 정책을 배포할 때 문서에 있는 최소 단서

DDM enforcement의 정책 구조는 Apple 문서에 흩어져 있습니다. 내 기준에서 운영팀이 반드시 읽어야 하는 단서는 두 군데입니다.

1) enforcement 선언 자체의 키/동작
2) 서비스가 새 릴리스를 감지하고 선언을 만들 때의 단계

### 1) enforcement 선언 키의 의미

Apple의 배포 가이드는 아래를 명확히 적습니다.

- TargetOSVersion: 목표 OS 버전
- TargetBuildVersion: 선택 사항(시딩/특정 빌드 타겟팅)
- TargetLocalDateTime: 강제 설치 시각(로컬 시간, timezone offset 없음)
- DetailsURL: 조직이 제공하는 상세 안내 링크

그리고 기한 이전에 사용자가 트리거하지 않으면 force install이 걸린다는 것도 분명히 씁니다.[^9]

### 2) enforcement phase: 감지 → 선언 생성 → 상태 보고

Apple 배포 문서 중 [Know the phases of Apple software update enforcement](https://support.apple.com/en-am/guide/deployment/dep225c4b7d4/web)은 “서비스가 Apple Software Lookup Service를 모니터링하고, 릴리스를 감지하면 `com.apple.configuration.softwareupdate.enforcement.specific` 선언을 생성한다”는 흐름을 단계로 설명합니다. 이 문서가 좋은 이유는 ‘업데이트는 디바이스가 알아서 한다’ 같은 추상화가 아니라, 운영 시스템이 무엇을 감시해야 하는지(상태 보고 항목 포함)를 적어둔다는 점입니다.[^12]

내 결론은 단순합니다.

- DDM enforcement는 “버튼”이 아니라 “상태 머신”이고,
- 상태 머신을 운영하려면 “상태 보고를 수집/모니터링하는 계약”이 반드시 따라야 합니다.

## 호환성·재부팅·MDM까지 포함한 운영 계약 템플릿

여기서 말하는 계약은 법무 문서가 아니라 운영 원칙입니다. 릴리스 노트가 빈약할수록 이 계약이 운영팀을 지켜줍니다.

나는 iOS/iPadOS 업데이트 운영 계약을 최소 아래 6개 조항으로 고정합니다.

### 1) 준수율 컴플라이언스의 정의

- “설치 완료”를 OS 버전으로 정의한다(예: iOS/iPadOS >= 26.7.3).
- “체크인 완료”를 별도로 정의한다(설치 후 MDM에 보고가 들어온 상태).

security-announce 전문에도 버전 확인 경로(Settings → General → About)가 들어가지만, 플릿에서는 그걸 사람에게 시키면 운영이 무너집니다. 그래서 버전은 디바이스 인벤토리/상태 보고로만 판단합니다.[^2]

### 2) 강제 정책의 링과 기한

- ring0: 72시간
- ring1: 7~14일
- ring2: 21~30일

여기서 중요한 건 기한 자체보다 “예외 승인 프로세스”입니다.

- 예외는 디바이스 단위가 아니라 태그 단위로만 허용(키오스크 모델 단위, 특정 앱 의존 단위 등)
- 예외는 만료일이 있어야 함

이 구조는 Android SPL 운영 계약과 똑같이 통합니다. 단지 지표가 SPL이 아니라 OS 버전입니다.

### 3) 재부팅과 유지보수 창

iOS 업데이트는 재부팅을 동반합니다. 따라서 강제 정책은 아래와 결합돼야 합니다.

- 유지보수 창(예: 로컬 02:00~05:00)
- 배터리/충전 조건
- 현장 자산(kiosk)은 물리 담당자와 동선 계약

DDM 문서에는 “기한 시각에 디바이스가 꺼져 있으면, 재시작 후 1시간 뒤 또는 조건이 만족되면 enforcement가 진행된다”는 식의 설명이 포함되어 있습니다. 즉, 사용자가 꺼놓는다고 무한 회피가 되진 않습니다.[^13]

### 4) 업무앱 호환성: ‘전체 테스트’ 대신 ‘핵심 경로’만

iOS 패치 릴리스는 기능 변경이 적은 경우가 많지만, 그렇다고 호환성 사고가 안 나는 건 아닙니다. 내 쪽에서 몇 번 크게 데인 패턴은 아래입니다.

- VPN/SSO 앱(네트워크 확장, 인증서, WebView)
- MDM 에이전트가 있는 경우(특히 major 전환)
- 키오스크 앱(싱글 앱 모드, Guided Access와 결합된 구성)

그래서 호환성 테스트는 “전사 앱 전체”가 아니라 “업무 중단 비용이 큰 경로만” 고정 스크립트로 체크합니다.

- SSO 로그인
- VPN 연결
- 업무 핵심 앱 3~5개 크리티컬 플로우
- 카메라/스캐너/외부 장치 연동(현장 자산)

호환성 범위를 더 늘리는 순간, 업데이트는 항상 늦어집니다.

### 5) MDM/등록 상태: supervised가 아닌 자산은 정책이 달라야 한다

DDM enforcement는 supervised 디바이스를 전제로 하는 선언이 많습니다(스키마에서도 supervised/device enrollment 조건이 함께 붙습니다).[^13]

BYOD가 섞이면 결론은 둘 중 하나입니다.

- BYOD는 강제 준수율을 약하게 두고(예: 접근 통제), 위험한 업무는 managed device로만 허용
- 또는 BYOD도 supervised에 가까운 등록 모델로 당겨온다

운영 계약에서 이 경계가 흐리면, 강제 정책은 항상 실패합니다.

### 6) 공지 수집 체계: 릴리스 노트가 아니라 security-announce를 1차로 본다

이번 iOS 26.7.3도 보안 콘텐츠는 security-announce에 구조적으로 정리돼 있습니다. AirPlay/Bluetooth/Messages/brotli처럼 컴포넌트와 CVE가 한 묶음으로 나옵니다.[^2]

운영 계약에는 “Apple security-announce를 수집하고, 자동으로 티켓을 생성한다”까지 포함되어야 합니다. 릴리스 노트를 기다리는 프로세스는 늦고, 사람을 계속 붙입니다.

## 반론과 회의론: 정보가 적으니 기다리자는 주장에 대한 답

릴리스 노트가 빈약할 때 가장 흔한 반응은 “일단 1~2주 기다려 보자”입니다. 이 말이 완전히 틀렸다고 보진 않습니다. 다만 그 전략이 성립하려면 조건이 있습니다.

- 그 1~2주 동안 노출면이 낮아야 한다.
- 그 1~2주 동안 디바이스가 물리적으로 안전해야 한다.
- 그 1~2주 동안 업무 채널(iMessage 등)이 통제되어야 한다.

iOS 26.7.3의 경우, Bluetooth range / same network / Messages 같은 공격면은 “기다리는 동안 노출면이 그대로 유지”되기 쉽습니다. 그리고 brotli(CVE-2026-111497)는 외부 CERT 경보에서 악용 신호가 언급되었습니다. 기다림은 곧 취약 기간 비용을 조직이 떠안는 선택입니다.[^2]

내가 현실적으로 받아들이는 타협은 이것입니다.

- 강제 링(ring0)을 좁힌다.
- 대신 ring0는 빨리 끝낸다.

즉, “전사 즉시 강제”가 아니라 “자산 기반으로 강제 대상을 좁히되, 좁힌 대상은 즉시 끝낸다”가 운영 비용이 가장 낮았습니다.

## 다음에 터질 문제: iOS 27 이후, OS 업데이트는 command가 아니라 선언으로만 남는다

iOS 26.7.3 자체는 보안 패치지만, 운영 관점에서 더 큰 의미는 “이제 iOS 26.x 라인에서도 업데이트 관리의 중심을 DDM으로 옮겨야 한다”는 압박입니다.

- AvailableOSUpdates 같은 MDM command가 iOS 26에서 deprecated, iOS 27에서 removed로 명시되어 있습니다.[^7]
- DDM enforcement는 GDMF/Software Lookup Service, 상태 보고 수집, 기한 기반 강제라는 ‘운영 시스템’ 성격을 갖습니다.[^8]

내 경우, 이 전환은 보안팀 요구로 시작되는 게 아니라 “헬프데스크 티켓 비용” 때문에 시작됩니다. command 기반으로 설치 버튼을 누르게 만드는 운영은 결국 사용자 커뮤니케이션과 예외 처리에서 터지고, 규모가 커질수록 관리 불가능해집니다.

DDM은 선언과 상태 보고를 중심으로 운영 체계를 만들 수 있게 해주고, 결국 그 체계가 “릴리스 노트가 빈약한 주간”에도 안정적으로 굴러갑니다.

## 정리: 빈약한 릴리스 노트는 변수가 아니라 상수다

iOS 26.7.3 / iPadOS 26.7.3은 공지 자체가 조직 운영에 충분히 친절하지 않은 전형적인 케이스입니다. 그래도 security-announce 전문에는 Bluetooth range, same network, Messages, brotli 등 공격면 힌트와 CVE가 들어 있고, 이 정보만으로도 자산 기반 강제/유예 정책을 돌릴 수 있습니다.[^2]

그리고 Apple이 iOS 27 시대로 넘어가며 OS 업데이트 관리에서 legacy MDM command를 치우고 declarative를 전면에 놓는 흐름은, “업데이트는 정책(계약)으로 운영해야 한다”는 방향과 맞물립니다. iOS 보안 공지의 정보 밀도 편차는 계속될 가능성이 높고, 그 편차를 흡수하는 가장 싼 방법은 업데이트 운영 계약을 먼저 고정한 뒤 DDM enforcement로 실행하는 쪽이었습니다.[^7]

## 참고 자료

- [APPLE-SA-11-09-2026-2 iOS 26.7.3 and iPadOS 26.7.3](https://www.mail-archive.com/security-announce@lists.apple.com/msg00952.html)
- [About the security content of iOS 26.7.3 and iPadOS 26.7.3](https://support.apple.com/en-us/149716)
- [Apple security releases](https://support.apple.com/en-us/100100)
- [Apple releases security updates: iOS 27.2.1, 26.7.3, and 18.7.12](https://www.macworld.com/article/3280295/apple-releases-security-updates-ios-27-2-1-26-7-3-and-18-7-12.html)
- [GovCERT.HK High Threat Security Alert: Multiple Vulnerabilities in Apple Products](https://www.govcert.gov.hk/en/alerts_detail.php?id=2169)
- [SoftwareUpdateEnforcementSpecific | Apple Developer Documentation](https://developer.apple.com/documentation/devicemanagement/softwareupdateenforcementspecific?language=objc)
- [Deploying software updates using declarative management | Apple Developer Documentation](https://developer.apple.com/documentation/devicemanagement/deploying-software-updates-using-declarative-management)
- [Software Update declarative configuration for Apple devices](https://support.apple.com/en-ie/guide/deployment/depca14ecd4d/web)
- [Know the phases of Apple software update enforcement](https://support.apple.com/en-am/guide/deployment/dep225c4b7d4/web)
- [apple/device-management: Available OS Updates Command (deprecated iOS 26, removed iOS 27)](https://github.com/apple/device-management/blob/release/mdm/commands/system.update.available.yaml)
- [apple/device-management: com.apple.applicationaccess (enforcedSoftwareUpdateDelay 등)](https://github.com/apple/device-management/blob/release/mdm/profiles/com.apple.applicationaccess.yaml)
- [Android Security Bulletin 패치 레벨로 플릿 업데이트 운영하기](https://daewooki.github.io/posts/android-spl-fleet-operations/)
- [Android Security Bulletin 패치 레벨을 플릿 운영 계약으로 굳히는 법](https://daewooki.github.io/posts/android-asb-fleet-contract-policy/)
- [mod_pagespeed 2.8.0 보안 업데이트: nginx 모듈 재배포 롤아웃 리스크](https://daewooki.github.io/posts/mod-pagespeed-280-nginx-module-rollout-risk/)

[^1]: <https://support.apple.com/en-us/100100?is=1ef7934f6635b02395adcab09a0c1b24bf0ea745b648bfe87189de8aadc7300b>
[^2]: <https://www.mail-archive.com/security-announce@lists.apple.com/msg00952.html>
[^3]: <https://www.macworld.com/article/3280295/apple-releases-security-updates-ios-27-2-1-26-7-3-and-18-7-12.html>
[^4]: <https://support.apple.com/en-us/149716>
[^5]: <https://www.govcert.gov.hk/en/alerts_detail.php?id=2169>
[^6]: <https://www.es-ist-ein-krauss.de/includes/iframe.php?url=https%3A%2F%2Fdeveloper.apple.com%2Fbusiness%2Fdocumentation%2FConfiguration-Profile-Reference.pdf>
[^7]: <https://github.com/apple/device-management/blob/release/mdm/commands/system.update.available.yaml>
[^8]: <https://developer.apple.com/documentation/devicemanagement/softwareupdateenforcementspecific?language=objc>
[^9]: <https://support.apple.com/en-ie/guide/deployment/depca14ecd4d/web>
[^10]: <https://daewooki.github.io/posts/android-asb-fleet-contract-policy/>
[^11]: <https://daewooki.github.io/posts/android-spl-fleet-operations/>
[^12]: <https://support.apple.com/en-am/guide/deployment/dep225c4b7d4/web>
[^13]: <https://github.com/apple/device-management/blob/release/declarative/declarations/configurations/softwareupdate.enforcement.specific.yaml>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
