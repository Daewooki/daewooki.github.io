---
title: "Android Security Bulletin 패치 레벨로 플릿 업데이트 운영하기"
description: "Android ASB의 2단계 패치 레벨을 MDM 플릿 운영 관점에서 해석하고, OEM 지연을 전제로 위험 분류·롤아웃 링·검증 항목을 재정의합니다."
date: 2026-10-07 11:20:16 +0900
categories: ["News", "Mobile"]
tags: ["android-security", "security-bulletin", "mdm", "fleet-ops", "patch-management", "android-enterprise"]
render_with_liquid: false
---

## 2026-10 보안 공지가 던진 운영 이벤트: 달력에 적는 날짜가 먼저입니다

AOSP는 2026-10-05에 *Android Security Bulletin—October 2026*를 게시했습니다. 공지 본문은 “Security patch levels of 2026-10-01 or higher address all of these issues”라고 못 박고, 가장 심각한 항목을 System 컴포넌트의 Critical 취약점(로컬 EoP, 추가 실행 권한 불필요, 사용자 상호작용 불필요)로 요약합니다.[^1]

여기서 플릿 운영 관점의 첫 번째 포인트는 “취약점의 내용”보다도 **SPL(Security Patch Level) 발표일이 ‘운영 캘린더의 Day 0’**라는 점입니다.

- Android Security Bulletin은 원칙적으로 매달 첫 번째 월요일에 게시되며(공휴일이면 다음 영업일), 2026년 10월도 2026-10-05에 게시됐습니다.[^2]
- ASB overview 페이지는 2026년 10월 항목에 보안 패치 레벨을 2026-10-01과 2026-10-05, 두 단계로 표기합니다.[^2]
- 공지 본문은 파트너에게 최소 한 달 전에 알린다고 명시합니다. 즉, OEM은 이슈 자체는 적어도 2026-09 초~중순 이전에 알고 있었다고 보는 편이 운영적으로 맞습니다.[^1]

이 세 가지를 합치면, “공지 읽기”는 2026-10-05에 시작되지만 “플릿 업데이트 운영”은 실제로는 그보다 앞에서 이미 진행 중이었다는 결론이 나옵니다. 공지를 보는 이유는 OEM 지연을 탓하려는 게 아니라, 내부 정책의 기준점을 매달 재설정하기 위해서입니다.

지난 9월 공지 기반 운영 프레임은 이미 정리했으니, 이번 달은 그 프레임을 10월 공지 내용으로 갱신하는 데만 집중합니다. (이전 글: [Android Security Bulletin 2026-09로 다시 짜는 모바일 보안 업데이트 운영](https://daewooki.github.io/posts/android-security-bulletin-patch-level-ops/))

## 2026-10-01: Framework/System/Mainline을 운영 언어로 번역하기

10월 ASB(2026-10-01 레벨) 테이블은 Framework, System, 그리고 “Google Play system updates(Project Mainline)”로 묶여 있습니다.[^1]

테이블을 전부 읽는 대신, 운영 관점에서는 “어떤 공격 경로가 열려 있는가”로만 다시 묶습니다.

### 1) System의 Critical EoP: 사내 단말에서 제일 싫은 형태

System 섹션에 Critical EoP가 여러 건 있습니다. 대표적으로 CVE-2026-55269 / CVE-2026-55280 / CVE-2026-58835 / CVE-2026-58880가 Critical EoP로 표기돼 있고(영향 버전은 16, 16-qpr2, 17), 공지 서문이 말한 “가장 심각한 이슈”도 System의 로컬 EoP 범주입니다.[^1]

플릿 운영에서 이 유형이 난감한 이유는 간단합니다.

- 원격에서 바로 터지는 RCE가 아니라서 위기감이 덜하게 보입니다.
- 하지만 업무 단말 현실에서는 “악성 앱/오염된 앱이 설치될 가능성”이 항상 존재합니다. 업무용 스토어만 쓰더라도 공급망 사고는 0이 아닙니다.
- 사용자 상호작용 불필요(또는 낮음) 케이스는 내부 공격 시나리오에서 대응 비용이 급격히 올라갑니다.

결국 이 범주는 “공지 발표 후 며칠 내에 전체 단말을 다 올린다”가 아니라, **업무 리소스 접근 정책과 결합해 ‘노출 기간’을 관리**해야 합니다.

### 2) Framework의 Critical DoS: 보안보다 가용성 사고로 터집니다

Framework 섹션에는 CVE-2026-58865가 Critical DoS로 올라와 있습니다.[^1]

DoS는 보안팀에서 우선순위가 밀리는 경우가 많지만, 현업 운영에서는 반대로 중요합니다.

- 패치 미적용 상태에서 특정 입력(파일/인텐트/IPC 조합 등)으로 system_server가 죽는 계열은, 공격이 아니라도 “업무앱 크래시/OS 불안정”으로 관측됩니다.
- 그래서 DoS는 보안 사건이 아니라 “Helpdesk 티켓 폭증 → MDM 강제 업데이트/강제 리부팅” 같은 운영 사건으로 이어집니다.

따라서 Framework DoS는 배포 우선순위를 올리는 게 아니라, **롤아웃 링에서 검증 항목에 반드시 넣는 쪽**이 효과가 좋습니다.

### 3) Project Mainline(Telephonycore/WiFi): OTA만 보지 말라는 신호

10월 공지는 Project Mainline 컴포넌트로 Telephonycore, WiFi를 명시합니다.[^1]

또한 공지는 Android 10 이상에서 “security updates as well as Google Play system updates”를 받을 수 있다고 계속 강조합니다.[^1]

이 문장을 플릿 운영으로 번역하면 이렇게 됩니다.

- **OS OTA만으로 컴플라이언스를 평가하면 거짓 음성/거짓 양성이 동시에 늘어난다.**
- Mainline 패치가 들어간 달에는 “OS SPL은 오래됐지만 Mainline은 최신” 같은 상태가 생깁니다.
- 반대로 “OS SPL은 최신인데 Mainline 업데이트가 지연/실패”하는 케이스도 있습니다(특히 사용자 상호작용이 남아 있는 기기/정책 구성).

즉 2026-10 공지는 단순히 CVE 리스트가 아니라, “단일 날짜(SPL)로 단말 건강상태를 판정하는 방식은 한계가 있다”는 운영 신호에 가깝습니다.

## 2026-10-05: 두 번째 패치 레벨을 ‘완료’로 부르면 운영이 꼬입니다

ASB 본문은 “왜 두 개의 security patch level이 있나?”에 대해, 파트너가 공통 이슈를 더 빨리 고칠 수 있게 하기 위한 유연성이라고 설명합니다.[^1]

현장에서 흔히 나오는 단순화는 이겁니다.

- 2026-10-01 = “부분 패치”
- 2026-10-05 = “완전 패치”

이 말 자체는 크게 틀리지 않지만, 그대로 정책에 박아 넣으면 사고가 납니다. 이유는 두 가지입니다.

### 1) -01 / -05는 “보안 수준”이라기보다 “공급망 경계”에 가깝습니다

FTC에 올라온 연구(ASB 기반 대규모 분석)는 SPL이 두 단계로 나뉘며, partial SPL(-01)은 Android system 컴포넌트 위주, complete SPL(-05)은 제품/폐쇄형 컴포넌트(예: Qualcomm 등)까지 포함하는 성격을 설명합니다.[^3]

운영 관점에서는 이렇게 받아들이는 편이 안전합니다.

- -01: AOSP/공통 플랫폼 영역 중심(대부분의 OEM이 같은 코드 기반에서 따라갈 수 있음)
- -05: OEM/SoC/커널/드라이버/펌웨어 등 “각 OEM이 최종 조립하는 영역”까지 포함될 가능성이 높음

즉, -05는 “더 높은 보안”이라기보다 **업데이트 공급망에서 OEM이 책임지는 구간이 늘어난 상태**입니다.

### 2) 이번 달(2026-10) 기준, -05의 추가분은 Pixel bulletin에서 더 명확히 보입니다

Pixel 쪽은 별도 공지인 *Pixel Update Bulletin—October 2026*를 2026-10-06에 게시했고, Google 기기는 2026-10-05 SPL로 업데이트된다고 명시합니다.[^4]

Pixel bulletin에는 AOSP ASB 본문에 없던 항목이 등장합니다.

- Kernel components: CVE-2026-56906, CVE-2026-56936 (High EoP)[^4]
- Pixel 섹션: Bluetooth, GDMC, GSA 등 Pixel 단말/Google 구성요소 범주에서 Critical EoP/ID가 추가[^4]

여기서 중요한 건 “Pixel이 더 안전하다”가 아닙니다. **-05라는 날짜가 ‘AOSP의 공통 테이블’만으로 설명되지 않는다는 사실**입니다.

게다가 10월 ASB 본문(2026-10-01 페이지)은 실제로 2026-10-05 레벨의 별도 vulnerability details 섹션을 노출하지 않습니다(최소한 공개 테이블 기준으로는 -01 세트만 확인됩니다).[^1]

따라서 플릿 정책을 이렇게 바꾸는 게 낫습니다.

- “-05를 받으면 완전 패치” 같은 단일 문장 정책을 버립니다.
- -01은 “공통 기반 최소선”으로, -05는 “기기군별 추가 델타가 붙는 상위선”으로 취급합니다.
- 델타는 OEM/파트너 공지(예: Pixel bulletin, Samsung/Motorola 등)로 구체화하고, 우리 조직은 그 델타를 **단말군별 위험 모델**에 끼워 넣습니다.

## 공지 기반 플릿 운영의 핵심 축: PSPL / DSPL / ASPL로 생각하기

Android 쪽도 이제 “단일 SPL 문자열”을 넘어서려는 흐름이 보입니다.

Android Developers 문서는 디바이스 보안 상태를 평가할 때, System / System Mainline Modules / Kernel을 분리해 보라고 가이드합니다. 또한 Published SPL(PSPL), Device SPL(DSPL), Available SPL(ASPL)을 구분합니다.[^5]

- System: 일반적으로 우리가 설정 앱에서 보는 SPL(날짜 기반)[^5]
- System Mainline Modules: Google Play system updates(모듈 업데이트)로 올라가는 영역[^5]
- Kernel: 커널 버전 문자열 기반으로 별도 평가(이 문서가 “커널 fix는 primary SPL string에 완전히 반영되지 않을 수 있다”는 뉘앙스를 깔고 갑니다)[^5]

기업 운영 문서에서도 “Published patch level은 Google이 패치를 만들었다는 뜻이고, OEM/Carrier가 안 풀면 내 기기는 못 받는다”는 식의 간극을 명시합니다. Device Trust from Android Enterprise 문서가 이 차이를 Note로 박아 둡니다.[^6]

이제 플릿 운영은 다음 질문으로 바뀝니다.

- PSPL: Google이 발표한 기준선은 어디까지 올라왔나? (이번 달이면 2026-10-01 / 2026-10-05)[^2]
- DSPL: 우리 기기군은 실제로 어디까지 올라왔나? (MDM/단말 텔레메트리)
- ASPL: 업데이트가 “available”인데 사용자가 미루는 상태인가, 아니면 OEM이 아직 배포하지 않아 “available” 자체가 아닌가?

공지 읽기는 PSPL 확인이고, 플릿 운영은 DSPL/ASPL 관리입니다.

## OEM 배포 지연을 전제로 한 위험 분류: 이번 달 테이블을 이렇게 나눕니다

2026-10 공지는 “가장 심각한 이슈는 System의 로컬 EoP”라고 요약합니다.[^1]  
여기서 나는 이번 달 위험 분류를 세 덩어리로 쪼갭니다.

### A. System Critical(EoP/DoS): 내부 공격(앱 기반) 관점 최상위

- 사용자 상호작용이 불필요하거나 낮은 로컬 EoP는 “악성 앱 1단계”와 결합되기 쉽습니다.
- MDM 환경에서도 100% 앱 설치를 통제하기 어렵고(특히 BYOD/COPE), 완전한 앱 검증 체계가 없으면 결국 “단말 자체를 올리는 것”이 비용 대비 가장 싼 방어입니다.

따라서 System의 Critical은 정책적으로 “월간 업데이트 KPI”의 1순위가 아니라, **업무 리소스 접근의 조건**으로 봅니다.

- 예: 사내 SSO/메일/VPN 접근 정책에서 “SPL >= 2026-10-01”을 최소선으로 둠
- 더 민감한 그룹은 “SPL >= 2026-10-05 또는 동등 수준(기기별 기준)”로 상향

### B. Mainline(Telephonycore/WiFi): 업데이트 경로가 2개이므로 관측도 2개

이번 달 ASB는 Mainline 컴포넌트를 따로 적었습니다.[^1]

- Telephonycore/WiFi는 네트워크 경계에 걸려 있어서 공격면이 넓습니다.
- 동시에 Mainline 업데이트는 OS OTA와 달리 “사용자/정책/스토어 상태”에 따라 성공률이 변동합니다.

그래서 나는 이 영역을 “보안 업데이트”라기보다 **업데이트 파이프라인 신뢰성**으로 분류합니다.

- OTA는 정상인데 Play system update가 밀리는 단말군이 있으면, 그 단말군은 다음 달에도 반복해서 밀릴 가능성이 높습니다.
- 반대로 Mainline이 빠르게 올라가는 단말군은, OS OTA가 조금 늦어도 일부 공격면이 줄어듭니다.

### C. -05 델타(커널/드라이버/벤더/Pixel 특화): 단말군별로만 의미가 있습니다

Pixel bulletin의 Kernel components 항목은, -05가 커널/드라이버 쪽 델타를 실제로 포함할 수 있음을 보여줍니다.[^4]

하지만 이 델타는 OEM/모델마다 완전히 다릅니다.

- Pixel은 2026-10-05로 업데이트된다고 공지합니다.[^4]
- 다른 OEM은 같은 날짜 문자열을 찍더라도, 커널/드라이버 구성과 backport 범위가 다를 수 있습니다(이건 ASB 테이블만으로 판정이 불가능합니다).

따라서 -05는 “모든 단말이 동일하게 따라야 하는 목표”라기보다, **우리가 통제 가능한 단말군(예: COPE Pixel, AER 기반 기기)**에서 먼저 달성 가능한 상위 목표로 놓는 편이 운영 비용이 낮습니다.

## 롤아웃 링 설계: SPL 2단계는 링도 2단계를 요구합니다

플릿 운영에서 가장 큰 비용은 “업데이트 배포”가 아니라 “업데이트 이후의 회복”입니다. 그래서 나는 보안 공지를 다음처럼 링 설계로 즉시 치환합니다.

### Ring 0: Canary (Pixel / 테스트 디바이스)

Pixel bulletin은 2026-10-05 패치 레벨로 전체 지원 Pixel이 업데이트된다고 말합니다.[^4]

그래서 Pixel은 단순히 “빠르다”가 아니라, **이달 공지의 상위선(-05)을 가장 먼저 밟는 링 0**로 쓰기 좋습니다.

- 목표: 2026-10-07(KST) 기준 당일~48시간 내에 소량 반영
- 관측: OS SPL, 커널 버전, Mainline 업데이트 상태, 그리고 업무 핵심 앱 회귀

링 0에서 보는 지표는 CVE 재현이 아닙니다. “업무 플릿이 죽지 않는지”가 먼저입니다.

### Ring 1: Early adopters (IT/보안/현장 지원 인력)

여기는 사용자가 업데이트에 협조적이며, 문제가 나도 해결 속도가 빠릅니다.

- 목표(예시): 2026-10-19(= 2026-10-05 + 14일)까지 SPL 2026-10-01 달성
- 가능하면 2026-11 초까지 2026-10-05 달성(단, OEM 배포가 있는 모델에 한함)

절대적인 날짜는 조직의 위험 허용치에 따라 달라지지만, 중요한 건 “-01과 -05를 같은 마감일로 보지 않는 것”입니다.

### Ring 2: Broad (대부분의 지식근로자/업무 단말)

여기는 품질/가용성 우선입니다.

- 목표: 2026-10-26(= 2026-10-05 + 21일)까지 SPL 2026-10-01
- 2026-10-05는 목표로 잡지 않되, OEM이 배포하는 모델은 따라가게 두는 정도가 현실적입니다.

### Ring 3: Lagging / exception (레거시, 현장 특수기기)

- 모델/캐리어 조합으로 업데이트가 느린 단말
- 특수 앱(바코드 스캐너, 결제 단말, 의료 기기 등) 호환성 리스크가 큰 단말

여기는 “업데이트 지연” 자체가 리스크가 되므로, 업데이트가 느린 OEM을 택한 비용을 운영으로 지불하는 구간입니다.

## MDM/컴플라이언스 정책에 SPL을 넣을 때 생기는 함정과 우회

Android Enterprise 쪽 문서는 컴플라이언스 엔진이 OS version, security patch details 같은 다양한 시그널로 컴플라이언스를 평가할 수 있고, 비준수 시 unenroll이나 리소스 차단 같은 액션을 걸 수 있다고 설명합니다.[^7]

Intune 같은 MDM 문서도 “Minimum security patch level”을 설정할 수 있다고 명시합니다.[^8]

문제는 여기서 발생합니다.

- “Minimum security patch level = 2026-10-05”로 걸면, OEM 지연을 그대로 조직 정책 위반으로 바꿔버립니다.
- 반대로 너무 느슨하게 잡으면(예: -60일), 보안팀이 원하는 정책 효과가 사라집니다.

내가 선호하는 해법은 하나입니다.

- **기기군을 먼저 나누고(링/모델/소유 형태), 기기군마다 최소 SPL을 다르게 둡니다.**

예시로, COPE Pixel과 BYOD를 같은 기준으로 묶는 순간 정책은 실패합니다. Device Trust 문서가 말하듯 published patch level이 존재해도 OEM/Carrier가 안 풀면 기기는 못 받습니다.[^6]  
그러니 정책은 “공급 가능한 집단”과 “공급 지연 집단”을 분리한 다음에야 의미가 생깁니다.

## 검증 항목을 3조각으로 쪼개야 하는 이유: System / Kernel / Modules

이번 달 주제는 “공지 읽기”가 아니라 “검증 가능한 운영 항목”을 만드는 것입니다.

Android Developers 문서가 제시하는 컴포넌트 분해(System, System Mainline Modules, Kernel)는 그대로 플릿 검증 체크리스트로 가져오는 게 효율적입니다.[^5]

### 1) System 검증: ro.build.version.security_patch는 여전히 중심축

ASB는 제조사가 패치를 포함하면 `ro.build.version.security_patch`를 2026-10-01로 설정하라고 적습니다.[^1]

이 값은 “업데이트가 들어갔는가”의 1차 판정으로는 여전히 유효합니다.

다만 여기서 끝내면 안 됩니다.

- 같은 SPL 문자열을 찍더라도 OEM별 backport 범위가 다를 수 있고
- 커널/벤더 영역은 이 값만으로 표현이 부족합니다.

### 2) Kernel/벤더 검증: vendor SPL과 커널 버전은 별도로 봅니다

AOSP 빌드 시스템 레벨에서 `ro.vendor.build.security_patch`가 생성되는 흔적이 있습니다.[^9]

현장에서는 다음을 같이 수집합니다.

- System SPL: `ro.build.version.security_patch`
- Vendor SPL(가능한 경우): `ro.vendor.build.security_patch` 또는 `ro.vendor.build.version.security_patch`(기기/빌드에 따라 다름)
- Kernel version: `uname -r` 또는 `/proc/version`

AndroidX Security State 라이브러리도 System은 `ro.build.version.security_patch` 기반, Kernel은 “kernel version string” 기반으로 별도 컴포넌트로 다룹니다.[^10]

10월 Pixel bulletin에 Kernel components 취약점이 따로 있는 걸 감안하면, 링 0/1에서는 커널 버전 관측을 기본으로 넣는 편이 좋습니다.[^4]

### 3) System Mainline Modules 검증: Play system update를 따로 KPI로 둡니다

10월 ASB는 Telephonycore, WiFi를 Mainline 컴포넌트로 명시합니다.[^1]

따라서 플릿 KPI를 최소 2개로 나눕니다.

- OS SPL(OTA): 2026-10-01 이상
- Play system update(Modules): 업데이트 성공률/지연률

OS SPL은 OEM이 쥐고 있고, Modules는 Google Play 업데이트 경로(정책/스토어/네트워크)의 영향을 받습니다. 실패 모드가 다르니 운영 지표도 분리해야 합니다.

### 4) 단말 무결성(운영 안전장치): Verified Boot 상태도 같이 본다

로컬 EoP가 무섭다고 해서 모든 단말을 보안팀이 직접 만질 수는 없습니다. 대신 “패치가 적용된 정상 이미지”라는 전제 자체를 흔들 수 있는 단말을 걸러야 합니다.

AOSP 코드 레벨에서도 `ro.boot.vbmeta.device_state`, `ro.boot.verifiedbootstate` 같은 프로퍼티를 읽는 흐름이 확인됩니다.[^11]

MDM 환경에서 root/bootloader unlock을 완벽히 막지 못하는 구성(BYOD 등)이면, 최소한 링 0/1 검증에서는 다음을 같이 수집해두는 편이 사고 대응이 빠릅니다.

- `ro.boot.vbmeta.device_state`
- `ro.boot.verifiedbootstate`

## 자동화 예시 1: MDM CSV에서 ‘SPL 2단계’ 컴플라이언스를 계산하는 스크립트

현장에서 가장 흔한 형태는 “MDM에서 CSV 내보내기 → 내부 파이프라인에서 재가공”입니다. 여기서는 Intune/Workspace ONE/기타 EMM 상관없이 쓸 수 있게 CSV 기반으로 예시를 잡습니다.

### 입력 CSV 포맷(현실적인 최소 컬럼)

`fleet.csv`

- `device_id`: 사내 디바이스 식별자
- `model`: 모델명
- `oem`: OEM
- `ownership`: `COPE|BYOD|COSU` 등
- `system_spl`: 예 `2026-10-01`
- `vendor_spl`: 예 `2026-09-05` (없으면 공란)
- `play_system_date`: 예 `2026-09-01` (없으면 공란)
- `kernel_version`: 예 `5.15.148`
- `last_checkin`: 예 `2026-10-07`

이 정도면 “정책 적용”이 아니라 “운영 의사결정”에는 충분합니다.

### 정책(2026-10 공지 기준) 정의

- PSPL(-01): `2026-10-01`
- PSPL(-05): `2026-10-05`[^2]
- 마감일 예시
  - Broad(링 2) -01 준수: 2026-10-26
  - Early(링 1) -01 준수: 2026-10-19
  - Canary/High-sensitivity(링 0/특정 그룹) -05 목표: “가능한 기기군(Pixel)만”

### 실행 가능한 Python 코드

`requirements.txt`

```txt
pandas==2.2.3
python-dateutil==2.9.0.post0
```

`plan_oct_2026.py`

```python
import sys
from dataclasses import dataclass
from datetime import date, datetime
from dateutil.parser import isoparse
import pandas as pd

@dataclass(frozen=True)
class Policy:
    pspl_01: date
    pspl_05: date
    due_ring1_01: date
    due_ring2_01: date

POLICY = Policy(
    pspl_01=date(2026, 10, 1),
    pspl_05=date(2026, 10, 5),
    due_ring1_01=date(2026, 10, 19),
    due_ring2_01=date(2026, 10, 26),
)

def parse_date(s: str | float) -> date | None:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = str(s).strip()
    if not s:
        return None
    return isoparse(s).date()

def spl_status(system_spl: date | None) -> str:
    if system_spl is None:
        return "unknown"
    if system_spl >= POLICY.pspl_05:
        return "gte_05"
    if system_spl >= POLICY.pspl_01:
        return "gte_01"
    return "lt_01"

def assign_ring(row) -> str:
    # 예시 규칙:
    # - Pixel(또는 테스트 OEM)은 canary
    # - COPE는 early
    # - BYOD는 broad(정책 강제보다 접근제어 중심)
    oem = (row.get("oem") or "").lower()
    ownership = (row.get("ownership") or "").upper()

    if oem == "google":
        return "ring0_canary"
    if ownership in ("COPE", "COSU"):
        return "ring1_early"
    return "ring2_broad"

def compliance_action(ring: str, status: str, last_checkin: date | None) -> str:
    today = date(2026, 10, 7)  # 작성일(KST) 기준을 고정

    if status == "unknown":
        return "investigate_telemetry"

    if ring == "ring0_canary":
        # canary는 -05를 가능한 빨리 목표로 삼되, 못 올리면 링 자체가 성립하지 않으니
        # 여기서는 -01 이상이면 통과로 두고, -05 미달은 경고로만 표기
        if status in ("gte_05",):
            return "ok"
        if status in ("gte_01",):
            return "warn_missing_05_delta"
        return "block_or_quarantine"

    if ring == "ring1_early":
        if status in ("gte_01", "gte_05"):
            return "ok"
        if today > POLICY.due_ring1_01:
            return "enforce_update_or_block_access"
        return "nag_update"

    # ring2_broad
    if status in ("gte_01", "gte_05"):
        return "ok"
    if today > POLICY.due_ring2_01:
        return "enforce_update_or_block_access"
    return "nag_update"

def main(path: str):
    df = pd.read_csv(path)

    # Parse dates
    df["system_spl_d"] = df["system_spl"].apply(parse_date)
    df["vendor_spl_d"] = df.get("vendor_spl", pd.Series([None]*len(df))).apply(parse_date)
    df["play_system_date_d"] = df.get("play_system_date", pd.Series([None]*len(df))).apply(parse_date)
    df["last_checkin_d"] = df.get("last_checkin", pd.Series([None]*len(df))).apply(parse_date)

    df["spl_status"] = df["system_spl_d"].apply(spl_status)
    df["ring"] = df.apply(assign_ring, axis=1)
    df["action"] = df.apply(lambda r: compliance_action(r["ring"], r["spl_status"], r["last_checkin_d"]), axis=1)

    out_cols = [
        "device_id", "oem", "model", "ownership",
        "system_spl", "vendor_spl", "play_system_date", "kernel_version",
        "spl_status", "ring", "action",
    ]
    for c in out_cols:
        if c not in df.columns:
            df[c] = ""

    df[out_cols].sort_values(["ring", "spl_status", "oem", "model"]).to_csv(sys.stdout, index=False)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python plan_oct_2026.py fleet.csv", file=sys.stderr)
        raise SystemExit(2)
    main(sys.argv[1])
```

### 실행 명령

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python plan_oct_2026.py fleet.csv > plan_out.csv
```

### 예상 출력(일부 예시)

```csv
device_id,oem,model,ownership,system_spl,vendor_spl,play_system_date,kernel_version,spl_status,ring,action
A-1001,google,Pixel 10 Pro,COPE,2026-10-05,2026-10-05,2026-10-01,5.15.148,gte_05,ring0_canary,ok
A-1002,samsung,Galaxy S26,COPE,2026-09-01,,2026-09-01,5.10.210,lt_01,ring1_early,nag_update
A-1003,xiaomi,Mi XX,BYOD,2026-08-01,,2026-09-01,5.4.268,lt_01,ring2_broad,nag_update
```

이 스크립트는 “정답”이 아니라, 10월 공지를 반영해 **-01과 -05를 같은 정책 값으로 취급하지 않는 뼈대**를 코드로 고정한 예시입니다.

## 자동화 예시 2: ADB로 링 0/1 단말에서 시스템/커널/무결성 시그널을 수집하기

MDM이 주는 텔레메트리만으로는, “정말 그 빌드가 올라갔는지”를 확신하기 어렵습니다. 특히 링 0/1에서 OS 업데이트 품질을 확인할 때는, 몇 대라도 ADB로 붙여서 스냅샷을 남기는 편이 사고 대응이 빠릅니다.

아래 스크립트는 사용자 빌드에서도 읽을 수 있는 범위(시스템 프로퍼티, 커널 버전, 보안 패치 레벨, verified boot 관련 상태)를 최소한으로 모읍니다.

`collect_device_posture.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

serial="${1:-}"

adb_args=()
if [[ -n "$serial" ]]; then
  adb_args+=("-s" "$serial")
fi

getprop() {
  local k="$1"
  adb "${adb_args[@]}" shell getprop "$k" 2>/dev/null | tr -d '\r'
}

uname_r() {
  adb "${adb_args[@]}" shell uname -r 2>/dev/null | tr -d '\r'
}

now_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

json_escape() {
  python3 - <<'PY'
import json,sys
print(json.dumps(sys.stdin.read().rstrip('\n')))
PY
}

system_spl="$(getprop ro.build.version.security_patch)"
vendor_spl="$(getprop ro.vendor.build.security_patch)"
if [[ -z "$vendor_spl" ]]; then
  vendor_spl="$(getprop ro.vendor.build.version.security_patch)"
fi

cat <<JSON
{
  "collected_at_utc": $(printf "%s" "$(now_utc)" | json_escape),
  "build_fingerprint": $(printf "%s" "$(getprop ro.build.fingerprint)" | json_escape),
  "android_release": $(printf "%s" "$(getprop ro.build.version.release)" | json_escape),
  "system_spl": $(printf "%s" "$system_spl" | json_escape),
  "vendor_spl": $(printf "%s" "$vendor_spl" | json_escape),
  "kernel_version": $(printf "%s" "$(uname_r)" | json_escape),
  "vbmeta_device_state": $(printf "%s" "$(getprop ro.boot.vbmeta.device_state)" | json_escape),
  "verifiedbootstate": $(printf "%s" "$(getprop ro.boot.verifiedbootstate)" | json_escape)
}
JSON
```

실행:

```bash
chmod +x collect_device_posture.sh
./collect_device_posture.sh > posture.json
```

이 결과는 “취약점이 패치됐다”를 증명하지는 못하지만, 최소한 다음을 빠르게 확인합니다.

- SPL이 기대치(예: 2026-10-01 또는 2026-10-05)에 올라왔는지
- 커널 버전이 업데이트로 바뀌었는지(모델별로 기대치가 다름)
- unlocked/비정상 verified boot 상태 단말이 테스트 링에 섞였는지

특히 verified boot 관련 프로퍼티는 AOSP 코드에서도 직접 읽는 값들이라(예: `ro.boot.vbmeta.device_state`), 사내 도구/정책에서 참조하기에 근거가 있습니다.[^11]

## 반론과 회의론: SPL 중심 운영은 결국 속일 수 있고, 놓칠 수 있습니다

SPL로 운영하는 접근은 실무에서 가장 널리 쓰이지만, 나는 한계를 분명히 적어두는 편입니다.

1) SPL은 “결과 문자열”이라 조작 가능성이 이론상 존재합니다. 그래서 무결성 시그널(verified boot, device integrity, attestation)과 결합하지 않으면 신뢰가 약합니다.

2) Android Developers 쪽도 커널 fix가 primary SPL 문자열에 완전히 반영되지 않을 수 있음을 전제하고, Kernel을 별도 컴포넌트로 평가하라고 문서에서 구분합니다.[^5]

3) Published patch level과 device patch level 사이에는 OEM/Carrier 지연이라는 구조적 간극이 있고, Android Enterprise 문서도 “published가 있다고 해서 기기가 받을 수 있는 건 아니다”라고 적습니다.[^6]

그렇다고 SPL 운영을 버리지는 않습니다. 대신 판단을 바꿉니다.

- SPL은 “최소선”이자 “관측 지표”로 두고
- 커널/모듈/무결성은 링 0/1에서부터 계측을 시작해
- 기기군별로 지표 신뢰도를 다르게 둡니다

SPL은 완벽한 보안 지표가 아니라, 불완전하지만 비용 대비 효과가 큰 운영 지표입니다.

## 앞으로 지켜볼 것: ASB 포맷 변화와 ‘2단계 SPL’의 실질 의미

10월 ASB는 -01 테이블만 확인되는 형태로 보이고, -05 델타는 Pixel bulletin처럼 파트너/디바이스 공지에서 더 직접적으로 드러납니다.[^1]

이 흐름이 계속되면, “-05를 공통 체크리스트로 강제”하는 운영은 점점 더 비용 대비 효과가 나빠집니다.

대신 다음을 지켜보게 됩니다.

- ASB overview가 말하는 것처럼, 패치 소스가 AOSP/업스트림 커널/SoC 벤더로 나뉘는 구조가 더 명시적으로 운영 도구에 반영될지[^2]
- PSPL/DSPL/ASPL 같은 개념이 MDM/Zero Trust 제품에서 기본 모델로 정착할지[^5]
- OEM이 제공하는 “update plan”의 신뢰도가 실제 컴플라이언스에 반영될지(Android Enterprise Recommended 요구사항이 이런 방향을 시사합니다)[^12]

## 2026-10 공지 기준으로 갱신한 플릿 운영 플랜

정리하면 이번 달(2026-10) 공지로 나는 플릿 운영 플랜을 이렇게 갱신합니다.

- 기준점은 2026-10-05(공지 게시일)이며, 2026-10-01은 공통 기반 최소선으로 취급합니다.[^1]
- 2026-10-05는 상위선이지만, 전 단말 강제 목표로 두지 않습니다. Pixel처럼 -05를 명시적으로 밟는 기기군은 링 0에서 canary로 삼고, 그 델타(커널/블루투스 등)를 관측 가능한 형태로 남깁니다.[^4]
- 컴플라이언스 정책은 “단일 최소 SPL”이 아니라 링/소유형태/모델군 단위로 분리합니다. published patch level과 available 여부의 간극은 구조적이므로, 정책으로 OEM 지연을 사용자 탓으로 바꾸지 않습니다.[^6]
- 검증은 System / Kernel / Modules로 나눠서 계측합니다. 이번 달처럼 Mainline 항목이 명시된 달에는 Play system update 관측을 KPI로 올립니다.[^1]

결국 2단계 패치 레벨은 “두 번 업데이트하라”가 아니라, **업데이트 공급망 경계를 분리해서 운영하라**는 신호로 읽는 편이 덜 실패합니다.

## 참고 자료

- [Android Security Bulletin—October 2026](https://source.android.com/docs/security/bulletin/2026/2026-10-01?hl=en)
- [Android Security Bulletins overview(게시 주기, 2026-10 패치 레벨 표기)](https://source.android.google.cn/docs/security/bulletin/asb-overview?hl=en)
- [Pixel Update Bulletin—October 2026](https://source.android.com/docs/security/bulletin/pixel/2026/2026-10-01)
- [Android security advisory – October 2026 monthly rollup (AV26-1003)](https://www.cyber.gc.ca/en/alerts-advisories/android-security-advisory-october-2026-monthly-rollup-av26-1003)
- [Google System updates on devices enrolled using Android Enterprise](https://support.google.com/work/android/answer/13791272?hl=en)
- [Device Trust from Android Enterprise](https://support.google.com/work/android/answer/16166663?hl=en)
- [Device compliance settings for Android Enterprise in Intune (Minimum security patch level)](https://learn.microsoft.com/en-us/intune/device-security/compliance/ref-android-enterprise-settings)
- [Understand device security state (PSPL/DSPL/ASPL, System/Mainline/Kernel 분리)](https://developer.android.com/privacy-and-security/understand-device-security-state)
- [SecurityPatchState API reference (androidx.security.state)](https://developer.android.com/reference/androidx/security/state/SecurityPatchState)
- [50 Shades of Support: A Device-Centric Analysis of Android Security Updates (FTC PDF)](https://www.ftc.gov/system/files/ftc_gov/pdf/16-Acar-A-Device-Centric-Analysis-of-Android-Security-Updates.pdf)
- [AOSP code: keymint에서 ro.boot.vbmeta.device_state 등을 읽는 흐름](https://android.googlesource.com/platform/hardware/interfaces/+/2abea7829464def1fb871ca368c78e3084875694/security/keymint/aidl/default/hal/lib.rs)
- [AOSP build Makefile 스니펫(ro.vendor.build.security_patch 생성)](https://android.git.googlesource.com/platform/build/+/9c4bacfd42a032f2fa883c241568623f0ba09a5e/core/Makefile)
- [이전 글: Android Security Bulletin 2026-09로 다시 짜는 모바일 보안 업데이트 운영](https://daewooki.github.io/posts/android-security-bulletin-patch-level-ops/)

[^1]: <https://source.android.com/docs/security/bulletin/2026/2026-10-01?hl=en>
[^2]: <https://source.android.google.cn/docs/security/bulletin/asb-overview?hl=en>
[^3]: <https://www.ftc.gov/system/files/ftc_gov/pdf/16-Acar-A-Device-Centric-Analysis-of-Android-Security-Updates.pdf>
[^4]: <https://source.android.com/docs/security/bulletin/pixel/2026/2026-10-01?authuser=56>
[^5]: <https://developer.android.com/privacy-and-security/understand-device-security-state?authuser=8>
[^6]: <https://support.google.com/work/android/answer/16166663?hl=en>
[^7]: <https://support.google.com/work/android/answer/13791272?hl=en>
[^8]: <https://learn.microsoft.com/en-us/intune/device-security/compliance/ref-android-enterprise-settings>
[^9]: <https://android.git.googlesource.com/platform/build/%2B/9c4bacfd42a032f2fa883c241568623f0ba09a5e/core/Makefile>
[^10]: <https://developer.android.com/reference/androidx/security/state/SecurityPatchState?authuser=0000>
[^11]: <https://android.googlesource.com/platform/hardware/interfaces/%2B/2abea7829464def1fb871ca368c78e3084875694/security/keymint/aidl/default/hal/lib.rs>
[^12]: <https://support.google.com/work/android/answer/16751490?hl=en>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
