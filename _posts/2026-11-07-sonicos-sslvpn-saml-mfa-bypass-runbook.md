---
title: "SonicOS SSLVPN SAML/MFA 우회가 드러낸 인증 경계 붕괴"
description: "CVE-2026-19868 실제 악용을 alt auth + SAML 강제 관점에서 해부하고 SSLVPN/IdP/MFA 운영 체크리스트로 정리합니다."
date: 2026-11-07 14:07:14 +0900
categories: ["News", "Security"]
tags: ["sonicwall", "sonicos", "sslvpn", "saml", "mfa-bypass", "incident-response"]
render_with_liquid: false
---

## 무슨 일이 있었나: 공지·CVE·실제 악용 신호가 한 번에 들어온 날

2026-11-06 전후로 SonicWall 쪽에서 Gen7/Gen8 SonicOS 보안 업데이트 묶음이 올라왔고, 그 안에 SSLVPN SAML 인증 강제를 우회할 수 있는 취약점(CVE-2026-19868)이 포함됐습니다. SonicWall의 지원 공지(노티스) 기준으로는 Gen7은 SonicOS 7.3.3-7015 이하가 영향 범위이고, 수정 버전은 7.3.4-7013 이상으로 제시돼 있습니다. Gen8은 SonicOS 8.2.2-8015 이하가 영향 범위이며 수정 버전은 8.2.3-8015로 안내돼 있습니다. 공지에는 SNWLID-2026-0014가 해당 PSIRT advisory로 연결돼 있고, “Planned Advisory Date”가 2026-11-06으로 표시돼 있습니다.[^1]

CVE-2026-19868의 설명은 요약하면 다음 한 문장으로 떨어집니다. SonicOS의 SSLVPN 서비스에서 authentication enforcement에 결함이 있어, **대체 인증 방식(alternate authentication method)** 에 대한 유효한 자격 증명을 가진 사용자가 SAML 인증 제어를 우회할 수 있고, 그 결과 SAML로 강제된 MFA까지 우회될 수 있다는 내용입니다. GitHub Advisory Database는 이 문장을 거의 그대로 싣고 있습니다.[^2]

이번 이슈가 주말 런북 가치가 있는 이유는 “패치 나왔습니다”에서 끝나지 않기 때문입니다.

* SonicWall PSIRT가 실제 악용 가능성을 조사했고(“potential exploitation” 표현), 고객에게 즉시 업그레이드를 강하게 권고했다는 보도가 나왔습니다.[^3]
* 캐나다 사이버센터(Canadian Centre for Cyber Security)가 2026-11-06자 advisory(AV26-1133)에서 “SonicWall indicates that CVE-2026-19868 is being exploited.”라고 못 박았고, 같은 날 CISA가 KEV Catalog에 추가했다고 적었습니다.[^4]
* SonicOS 8.2.3 릴리스 노트의 fixed issues에 “SSLVPN Authentication Enforcement Vulnerability via Alternate Authentication Methods (SNWLID-2026-0014)”가 들어가 있습니다. 즉, 이건 단순 문서상의 CVE가 아니라 제품 릴리스 레벨에서 “대체 인증 방식 경로”를 손대서 고친 이슈라는 뜻입니다.[^5]

정리하면 2026-11-06을 기점으로 “실제 악용 신호 + KEV급 긴급도 + 엣지 장비의 인증 경계”가 한꺼번에 쏟아진 케이스입니다.

## ‘취약점 하나’가 아니라 ‘alt auth + SAML 강제’가 깨지는 구조

이 이슈를 “SSLVPN에서 MFA bypass가 됐다”로만 읽으면, 대응이 너무 단선적으로 흘러갑니다. 실제 운영 현실은 VPN 장비가 인증을 딱 한 가지로만 처리하는 경우가 거의 없습니다.

SonicOS SSL VPN 문서만 봐도, 사용자 인증 방식은 RADIUS 또는 “RADIUS + Local Users”, LDAP 또는 “LDAP + Local Users”처럼 애초에 합성(composition) 형태로 들어갈 수 있습니다. 그리고 SSLVPN 접속 권한은 결국 장비의 로컬 그룹(예: SSLVPN Services 그룹)과 매핑되는 구조입니다.[^6]

한편 SAML을 붙이면 운영팀의 기대는 대개 이렇게 바뀝니다.

* VPN은 더 이상 password를 검증하지 않는다.
* IdP(Entra ID, Okta 등)가 1차 인증 + MFA(Conditional Access/Policy)를 수행한다.
* VPN은 SAML assertion을 받아서 “그 사용자가 누구인지”와 “어떤 그룹인지”만 확인한다.

SonicWall의 SAML 설정 가이드도 “SSLVPN의 Authentication Type을 SAML로 설정하면 Virtual Office Portal에서 username/password 입력이 없어지고 IdP 로그인 화면으로 리다이렉트된다”는 흐름을 전제로 설명합니다.[^7]

여기서 기대하는 보안 속성은 명확합니다. **SAML 강제** 상태라면, 장비가 갖고 있는 다른 인증 경로(로컬 유저, LDAP, RADIUS 등)는 SSLVPN에 대해선 사실상 죽어 있어야 합니다.

그런데 CVE-2026-19868의 본질은 “SAML 강제 상태에서도 alt auth 경로 중 하나가 살아남아 우회가 가능해진다”입니다. 이건 취약점의 버그 자체도 문제지만, 운영 구조 관점에선 더 큰 메시지를 던집니다.

* VPN 장비는 종종 “SSO를 붙여도 기존 인증 레이어를 완전히 제거하지 못한” 상태로 운영됩니다.
* 운영팀은 SAML/MFA를 켰다는 사실만으로 “모든 로그인은 IdP로 간다”고 가정하기 쉽습니다.
* 공격자는 그 가정이 깨지는 지점을 노립니다.

즉 이번 건은 “MFA가 뚫렸다”가 아니라, **SSO 경계** 를 VPN 장비 바깥(IdP)으로 넘겼다고 믿는 순간, 장비 내부에 남아 있는 인증 레이어가 어떤 식으로든 복원(fallback)되면 전체 설계가 무너진다는 사건입니다.

## 공격 시나리오를 운영 언어로 다시 쓰기

공식 설명은 “alternate authentication method에 대한 valid credentials가 필요하다”입니다. 여기서 많은 팀이 안도합니다. “그럼 자격 증명 탈취가 선행돼야 하네, 난 MFA라 괜찮아” 같은 식입니다.

하지만 이 문장을 운영 언어로 바꾸면 이렇게 됩니다.

1) 공격자는 IdP MFA를 통과할 필요가 없다.

2) 공격자는 VPN 장비가 받아주는 다른 인증 소스(로컬/LDAP/RADIUS 등) 중 하나의 자격 증명만 확보하면 된다.

3) 그 자격 증명은 조직에서 흔히 다음 경로로 새어 나옵니다.

* password spraying으로 걸린 계정(특히 “VPN 접속이 가능한 그룹”에 묶인 계정)
* 과거 침해 사고에서 유출된 password 재사용
* helpdesk/협력사 계정처럼 정책이 느슨한 계정
* 장비에 남아 있던 로컬 계정(퇴사자/프로젝트성 계정 포함)

4) 정상이라면 “SAML 강제”가 이 경로를 차단해야 하는데, 이번 취약점은 그 enforcement를 무너뜨립니다. (SonicOS 8.2.3 릴리스 노트의 문구가 바로 이 지점입니다.)[^5]

여기서 가장 위험한 후속 효과는 “IdP 쪽 로그가 남지 않는 원격 접속”입니다. VPN 접속이 성공했는데 Entra/Okta의 sign-in 흔적이 없으면, SOC는 보통 두 가지 중 하나로 오해합니다.

* (오탐) 로그 수집이 누락됐나?
* (정탐 놓침) 사용자가 다른 경로로 로그인했나?

이게 반복되면, 팀은 결국 “VPN은 IdP로 통제되고 있다”는 전제를 유지한 채, 침해 지표를 놓치게 됩니다.

## 영향 범위 판단: 버전만 보지 말고 ‘구성’을 먼저 본다

이번 건은 “취약한 버전이면 무조건 뚫린다” 타입의 단순 공식이 아닙니다. BleepingComputer 보도에서 “SAML로 구성된 SSL-VPN 서비스에만 영향을 준다”는 문장이 들어가 있습니다.[^3]

즉, 영향 범위는 최소 두 조건의 교집합으로 보는 게 맞습니다.

* SonicOS 버전이 영향 범위(Gen7 7.3.3-7015 이하, Gen8 8.2.2-8015 이하) 안에 있다.[^1]
* SSLVPN 인증을 SAML로 쓰고 있다.[^3]

여기까지는 다들 체크합니다. 문제는 그 다음입니다.

### SAML을 켜도 “장비가 인정하는 계정 집합”은 넓게 남아 있을 수 있다

SAML 구성 가이드를 보면, IdP 그룹을 “SSLVPN Services” 같은 로컬 그룹명으로 매핑하고, 그 그룹이 있어야 접속할 수 있다고 설명합니다.[^7]

이 구조는 편리하지만, 장비의 관점에서 “SSLVPN 접속 권한이 있는 사용자”의 정의가 생각보다 넓어질 여지가 있습니다.

* 로컬 유저로든
* LDAP로든
* RADIUS로든

어떤 방식으로든 그 로컬 그룹에 들어오면, SSLVPN은 허용합니다. SonicOS SSL VPN 문서에서도 RADIUS/LDAP 사용자들을 기본 그룹(SSLVPN Services)에 넣는 절차가 나오고, 인증 방식 자체가 “LDAP + Local Users”처럼 혼합될 수 있다고 되어 있습니다.[^6]

CVE-2026-19868의 “alternate authentication method”가 정확히 무엇인지는 advisory 본문을 열어봐야 더 명확해지는데(현재 PSIRT 페이지는 도구로는 렌더링이 잘 안 잡힙니다), 적어도 제품 문서 레벨에서 “혼합/대체 인증 경로”가 자연스러운 기능으로 존재한다는 사실이 중요합니다.

### 캐나다 사이버센터 advisory의 버전 표기는 그대로 믿지 않는 편이 낫다

캐나다 사이버센터 AV26-1133에는 Gen7 “prior to 7.3.4-7013”, Gen8 “prior to 8.2.2-8015”로 적혀 있습니다. 그런데 SonicWall 노티스와 BleepingComputer는 Gen8 영향 범위를 “8.2.2-8015 and earlier”로 보고 있습니다.[^4][^1][^3]

이런 불일치는 실제 현장에서 자주 봅니다. 정부/기관 경보는 “조치 우선순위”를 주는 데는 탁월하지만, 버전 매트릭스는 벤더 1차 문서가 최종 기준입니다. 이번 건은 특히 “fixed build가 8.2.3-8015”로 명시돼 있으니, Gen8은 8.2.3-8015 미만을 모두 잠정 위험으로 묶는 게 운영적으로 안전합니다.[^1]

## 왜 중요한가: MFA를 ‘붙였다’가 아니라 ‘경계를 옮겼다’로 봐야 한다

SAML을 SSLVPN에 붙이는 이유는 대개 세 가지입니다.

1) MFA를 VPN 장비에서 직접 구현하지 않고 IdP에서 중앙집중으로 강제

2) 계정 라이프사이클(입사/퇴사/권한 변경)을 IdP/Directory에서 일원화

3) Conditional Access 같은 맥락 기반 통제(디바이스, 위치, 리스크)

이 중 1)만 놓고 보면 “MFA bypass 취약점”이지만, 2)와 3)까지 포함하면 이건 보안 아키텍처의 경계 재배치입니다.

* 기존: VPN 장비가 authentication boundary였다.
* SAML 도입 후: IdP가 authentication boundary가 됐다.

여기서 boundary를 옮기는 순간, VPN 장비에는 “인증을 직접 하지 않는다”는 전제가 생깁니다. 운영팀은 장비 로컬 계정의 정책 강도를 낮추거나, 장비 내부의 인증 기능(로컬/LDAP/RADIUS) 점검 주기를 느슨하게 가져가기도 합니다.

CVE-2026-19868은 그 전제가 깨질 때 어떤 일이 나는지 보여줍니다. IdP가 아무리 엄격해도, 장비가 다른 인증 경로를 받아주는 순간 IdP의 통제는 관측 불가능한 형태로 무력화됩니다.

이번 케이스에서 “실제 악용 중”이라는 신호가 특히 무거운 이유도 같습니다. 공격자는 보통 가장 약한 경계를 노립니다. IdP MFA가 강하면, alt auth를 파고드는 것이 비용 대비 효율이 좋습니다. 캐나다 사이버센터가 “exploited”를 명시했고, SonicWall PSIRT가 “potential exploitation”을 언급한 보도가 함께 붙은 상황이면, 이미 이 경계 균열이 공격자 플레이북에 올라갔다고 보는 편이 맞습니다.[^4][^3]

## 반론과 회의론: “대체 인증 자격 증명이 있으면 어차피 끝난 것 아닌가?”

이 반론은 절반만 맞습니다.

*맞는 부분*: 공격자가 어떤 형태로든 유효한 자격 증명을 들고 있다는 건 이미 위험 신호입니다. 특히 VPN은 네트워크 경계 안으로 들어오는 키이기 때문에 치명적일 수 있습니다.

*틀린 부분*: SAML 강제 + IdP MFA를 설계한 이유가 바로 “자격 증명 단독”으로는 못 들어오게 만들기 위해서입니다. 다시 말해, 설계가 의도한 위협 모델은 “password는 새어 나갈 수 있다”에 가깝습니다. 그래서 MFA와 조건부 정책으로 단일 요소 인증을 무력화합니다.

CVE-2026-19868은 그 위협 모델을 다시 과거로 되돌립니다. ‘IdP에서 MFA를 강제하는 구조’가 ‘VPN 장비가 password를 받아주는 구조’로 순간 이동합니다. GitHub Advisory의 설명이 굳이 “SAML-enforced MFA bypass”까지 써 둔 이유가 여기에 있습니다.[^2]

따라서 우선순위는 “자격 증명 탈취 방지”와 별개로, “SAML 강제가 실제로 강제되는지”를 검증하는 쪽에 둬야 합니다.

## 앞으로 지켜볼 것: IoC보다 먼저 봐야 하는 업데이트 지점

이번 공지 흐름에서 답답한 부분은, 현재 공개된 1차 문서만으로는 공격 디테일과 IoC가 거의 없다는 점입니다. BleepingComputer도 SonicWall이 악용 상세를 공유하지 않았다고 적고 있습니다.[^3]

그래서 더 현실적인 관점에서 지켜볼 것은 아래입니다.

1) SNWLID-2026-0014의 advisory 본문이 갱신되면서 “workaround/mitigation”이 추가되는지

SonicWall 노티스에는 CVE 묶음에 대해 “no workarounds are available”로 보도됐고, 당장은 패치 외 선택지가 약합니다.[^3]

2) SonicOS 7.3.4 계열/8.2.3 계열에서 SSLVPN 인증 로직 변화가 릴리스 노트/KB로 구체화되는지

SonicOS 8.2.3 릴리스 노트에는 “Alternate Authentication Methods”가 명시돼 있어, 후속 문서에서 더 구체적인 운영 가이드가 나올 가능성이 있습니다.[^5]

3) “SAML인데도 IdP 로그가 없다”는 현장 징후가 다른 채널로 집계되는지

공격이 확산되면 PoC/스캐너가 따라오고, 그때부터는 alt auth 자격 증명 획득(스프레이/크리덴셜 스터핑)과 결합되면서 훨씬 넓게 번집니다. 주말/월요일 패치 윈도우를 놓치면 위험도가 확 커지는 패턴입니다.

## 지금 할 수 있는 일: 주말/월요일 패치 윈도우용 런북

여기서부터는 “벙커에 들어가서 점검할 것”을 순서대로 적습니다. 벤더가 workaround를 제공하지 않는다고 했으니, 패치 계획 수립과 동시에 “구성 검증 + 탐지 보강”을 같이 묶는 게 핵심입니다.[^3]

### 1) 자산/버전/구성 3종 인벤토리(30분 안에 끝내는 기준)

1. 외부 노출 SSLVPN 엔드포인트 목록
   * 공인 IP, FQDN, 포트, Virtual Office 사용 여부
2. SonicOS 세대/버전
   * Gen7: 7.3.3-7015 이하인지
   * Gen8: 8.2.2-8015 이하인지
   * 수정 버전 목표: Gen7 7.3.4-7013 이상, Gen8 8.2.3-8015[^1]
3. SSLVPN 인증 방식
   * “SAML을 쓰고 있다”가 아니라 “SSLVPN Authentication Type이 SAML로 설정돼 있다”를 확인해야 합니다. 가이드에도 이 단계가 명확히 들어가 있습니다.[^7]

여기서 **중요한 분기** 는 “SAML을 쓰는지”입니다. 이번 CVE는 “SAML로 구성된 SSL-VPN 서비스”가 조건으로 붙어 있습니다. 하지만 같은 묶음에 다른 CVE들도 함께 들어가 있으므로, SAML을 안 쓴다고 해서 패치 우선순위가 사라지는 건 아닙니다. BleepingComputer 보도 기준으로는 총 7개 취약점이 함께 수정됐고, 그 중 2개는 management interface 관련 8.8 severity로 언급됩니다.[^3]

### 2) 패치 적용 원칙(다운타임 설계)

SonicWall 노티스는 수정 버전을 명확히 제시합니다. Gen7은 7.3.4-7013 이상, Gen8은 8.2.3-8015입니다.[^1]

운영 원칙은 간단합니다.

* SSLVPN을 외부에 열어두는 장비는 “패치 전까지는 침해 가능 상태”로 취급
* HA 구성이 있으면 failover 시나리오까지 포함해 윈도우를 잡고, 패치 후에는 실제로 SAML 리다이렉트가 기대대로 동작하는지(사용자 경험)까지 확인

패치 후 검증은 기능 테스트와 보안 테스트를 분리하는 편이 낫습니다.

* 기능: Virtual Office가 IdP로 리다이렉트되는지, NetExtender 경로가 정상인지
* 보안: IdP 로그 없이 VPN 로그인 성공이 가능한지(아래 탐지 섹션의 상관분석으로 확인)

### 3) 패치 전 임시 완화(Workaround가 ‘없다’는 말의 해석)

BleepingComputer 보도에는 “no workarounds are available”가 명시돼 있습니다. 이건 “버그를 우회하는 공식 설정이 없다”는 뜻에 가깝습니다.[^3]

운영팀이 실제로 할 수 있는 임시 완화는 보통 아래 범주입니다(이 부분은 벤더가 보증하는 workaround라기보다는, 엣지 노출면을 줄이는 일반론입니다).

* SSLVPN을 일시 중단(가장 확실)
* SSLVPN 접근 소스 IP를 강하게 제한(사내 egress/NAT, ZTNA POP 등)
* 로그인 시도에 대한 rate limit/lockout 정책 점검(장비/IdP 양쪽)

다만 이번 건은 “valid credentials” 전제이므로, 단순 lockout만으로 해결되지는 않습니다. 이미 계정이 털렸다면 정상 로그인으로 보일 수 있습니다.

## SSLVPN/IdP/MFA 운영 체크리스트: alt auth가 숨어들 틈을 지우는 쪽으로

여기서부터는 “SAML을 켰으니 됐다”라는 착각을 깨는 항목들입니다. 체크리스트는 길어야 가치가 생기는데, 대신 항목마다 의도를 붙입니다.

### SSLVPN(장비) 체크리스트

1) SSLVPN 인증 소스가 SAML 단일 경로인지 재검증

SonicWall의 SAML 가이드는 SSLVPN Server Settings에서 Authentication Type을 SAML로 설정한다고 적습니다. 이 설정 하나가 “사용자 포털에서는 password 입력이 사라진다”는 UX를 만들지만, CVE-2026-19868은 바로 그 enforcement가 흔들릴 수 있다는 뜻입니다.[^7][^2]

따라서 “포털이 리다이렉트된다”는 사실만 확인하지 말고, 실제로 장비가 어떤 인증 경로를 받아들이는지(로컬/LDAP/RADIUS)까지 함께 점검해야 합니다.

2) “+ Local Users” 혼합 옵션이 의미하는 바를 다시 보기

SonicOS SSL VPN 문서에는 RADIUS + Local Users, LDAP + Local Users 같은 조합이 명시돼 있습니다. 이 모델은 편하지만, alt auth가 들어오는 길을 남깁니다.[^6]

SAML을 붙인 환경에서 이 조합이 직접적으로 어떻게 작동하는지는 구성에 따라 다를 수 있지만, 원칙은 하나입니다.

*SSLVPN을 SAML로 강제하려면, SSLVPN에 대해선 장비 내부의 다른 인증 소스가 사실상 의미가 없어야 합니다.*

3) SSLVPN Services 같은 “권한 부여 그룹”의 구성 방식 점검

SonicWall 가이드는 IdP에서 “SSLVPN Services”라는 그룹을 만들고, 그 그룹 이름을 assertion에 실어 보내는 흐름을 설명합니다.[^7]

이 구조에서 취약해지는 지점은 “그 그룹이 SAML 사용자만을 위한 그룹이 아니라, 다른 경로(LDAP/RADIUS/Local Users)에서도 동일한 그룹에 들어올 수 있다”는 점입니다. 그룹이 “접속 권한” 그 자체라면, 그룹으로 들어오는 모든 경로가 공격면이 됩니다.

4) 로컬 유저/로컬 그룹에 남아 있는 유령 계정 정리

SAML 도입 이후에도 로컬 계정이 남는 경우가 꽤 있습니다.

* 초기 PoC 때 만든 테스트 계정
* 장애 대응용 break-glass 계정
* 특정 협력사 접속용 계정

이번 취약점 설명에는 “alternate authentication method credentials”만 있으면 SAML/MFA를 우회할 수 있다고 되어 있으므로, 로컬 계정은 가장 먼저 의심 대상이 됩니다.[^2]

5) 패치 적용이 곧 “정책이 맞아졌다”를 의미하지 않는다는 점을 문서화

SonicOS 8.2.3 릴리스 노트에 이 이슈가 “fixed issues”로 들어갔다고 해서, 기존에 구성해 둔 인증/그룹 매핑이 자동으로 가장 안전한 형태로 재구성되는 건 아닙니다. 릴리스 노트는 “버그가 고쳐졌다”의 신호일 뿐입니다.[^5]

### IdP(Entra ID / Okta 등) 체크리스트

IdP는 이번 취약점의 직접 원인은 아니지만, “우회 탐지”의 기준면을 제공합니다.

1) VPN(SAML 앱) sign-in 이벤트가 정상적으로 쌓이는지

Microsoft Graph signIn 리소스에는 createdDateTime(UTC), userPrincipalName, ipAddress, conditionalAccessStatus 같은 필드가 포함됩니다. 이 데이터는 “VPN 접속 성공”과 “IdP 인증 성공”을 시간 상관분석할 때 기준이 됩니다.[^8]

2) Okta 계열이라면 user.session.start / policy.evaluate_sign_on 등을 함께 본다

Okta 쪽은 이벤트 타입 자체가 탐지 기준이 됩니다. Support 문서와 Developer 문서에서 user.session.start가 로그인(세션 시작)과 관련된 핵심 이벤트 타입으로 반복해서 등장합니다.[^9][^10]

3) Conditional Access / sign-on policy를 “통제”만이 아니라 “관측”으로 사용

우회가 생기면 IdP 정책은 적용되지 않습니다. 따라서 IdP 정책을 강화하는 것만으로는 해결이 안 됩니다. 대신 IdP 이벤트가 “없다”는 사실을 탐지 룰의 조건으로 만들어야 합니다.

### MFA 운영 체크리스트

이번 건은 “MFA가 약했다”가 아니라 “MFA가 적용되는 경로 자체가 우회됐다”가 핵심입니다.

따라서 MFA 운영 체크리스트도 질문이 바뀝니다.

* MFA를 켰나? → 이미 켰다.
* MFA가 적용되지 않는 로그인 경로가 존재하나? → 이게 이번 이슈의 본질이다.

이 관점으로 보면, VPN뿐 아니라 다른 엣지 컴포넌트(ZTNA 커넥터, 프록시, bastion)에도 동일한 질문을 적용할 수 있습니다.

## 탐지와 포렌식: “IdP 이벤트 없는 SSLVPN 성공 로그인”을 잡는 방법

IoC가 없는 상황에서 가장 실용적인 탐지는 상관분석입니다.

1) SonicWall SSLVPN 로그인 성공 이벤트
2) IdP(Entra/Okta)에서 해당 사용자에 대한 SAML sign-in 이벤트
3) 둘 사이가 시간상으로 매칭되지 않으면 의심

### SonicWall SSLVPN 로그에서 뽑아야 하는 최소 필드

SonicWall SSLVPN syslog는 보통 key=value 형태로 떨어집니다. 예시로는 “SSLVPN: id=” 문자열로 식별된다고 정리된 문서가 있고, msg 필드에 “User login failed” 같은 메시지가 들어갑니다. user/usr, src 같은 필드도 같이 나옵니다.[^11]

즉 최소한 아래 필드는 확보해야 합니다.

* timestamp (가능하면 time="..." 또는 vp_time="..." 같은 장비가 찍어준 시간)
* usr 또는 user (사용자 식별자)
* src (소스 IP)
* msg (성공/실패 판별)

### Okta 쪽 기준(예시)

Okta는 System Log에서 user.session.start / user.session.end 같은 이벤트 타입으로 로그인/로그아웃을 조회할 수 있고, Support 문서에 쿼리 예시까지 들어가 있습니다.[^9]

### Entra 쪽 기준(예시)

Entra는 signIn 이벤트에 userPrincipalName, createdDateTime(UTC), ipAddress, conditionalAccessStatus 같은 필드를 포함합니다.[^8]

이 필드로 “VPN 인증이 정말로 IdP를 거쳤는지”를 확인할 수 있습니다.

### 실행 가능한 상관분석 스크립트(파일 기반)

현장에서 로그는 SIEM에 있지만, 주말 런북에서는 보통 24시간치만 뽑아서 빠르게 확인하는 흐름이 많습니다. 아래는 그 상황을 가정한 스크립트입니다.

입력 파일 2개를 받습니다.

* `sonicwall_sslvpn.log`: SonicWall syslog(텍스트)
* `idp_signins.csv`: IdP sign-in 로그(UTC 기준 CSV)
  * 최소 컬럼: `createdDateTime,userPrincipalName,ipAddress,appDisplayName,result`

CSV 스키마는 Entra/Okta 어느 쪽이든 “내가 가진 로그를 일단 이 컬럼으로 정규화해서 넣는다”는 현실적인 타협입니다. 여기서 중요한 건 도구가 아니라 “상관분석 기준”입니다.

```bash
# Ubuntu 24.04 / Debian 계열 가정
python3 -V
# Python 3.11+ 권장

mkdir -p /tmp/sslvpn-hunt
cd /tmp/sslvpn-hunt

cat > sslvpn_saml_gap_detector.py << 'PY'
#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import ipaddress
import json
import re
from dataclasses import dataclass
from typing import Iterable, Optional

# SonicWall SSLVPN syslog 예시(문서/현장 관측 기반):
#   ... SSLVPN: id=sslvpn ... time="2013-02-02 11:36:44" ... src=24.176.55.122 ... usr="Sgreen" msg="User login failed" ...
# 또는 msg가 "... login allowed" 형태로 찍히는 케이스가 있음.

KV_RE = re.compile(r'(\w+)=(("[^"]*")|([^\s]+))')
IPV4_RE = re.compile(r'(?P<ip>(?:\d{1,3}\.){3}\d{1,3})')

@dataclass(frozen=True)
class VpnEvent:
    ts: dt.datetime
    user: str
    src_ip: str
    msg: str

@dataclass(frozen=True)
class IdpEvent:
    ts: dt.datetime
    user: str
    ip: str
    app: str
    result: str

def parse_sonicwall_time(value: str) -> Optional[dt.datetime]:
    # time="YYYY-MM-DD HH:MM:SS" (timezone 표기가 없는 경우가 많아 UTC로 가정하지 않고 naive 유지)
    value = value.strip().strip('"')
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return dt.datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None

def kv_parse(line: str) -> dict:
    out = {}
    for m in KV_RE.finditer(line):
        k = m.group(1)
        v = m.group(2)
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        out[k] = v
    return out

def looks_like_success(msg: str) -> bool:
    s = (msg or "").lower()
    # 환경마다 달라서 보수적으로: failed/denied 없고 login 키워드가 있으면 성공으로 분류
    if "fail" in s or "deny" in s:
        return False
    if "login" in s and ("allow" in s or "success" in s):
        return True
    # 일부 로그는 "SSL VPN zone remote user login allowed" 형태
    if "login allowed" in s:
        return True
    return False

def extract_src_ip(src_field: str) -> Optional[str]:
    if not src_field:
        return None
    m = IPV4_RE.search(src_field)
    if not m:
        return None
    ip = m.group("ip")
    try:
        ipaddress.ip_address(ip)
        return ip
    except ValueError:
        return None

def parse_vpn_events(lines: Iterable[str]) -> list[VpnEvent]:
    events: list[VpnEvent] = []
    for line in lines:
        if "SSLVPN" not in line:
            continue
        kv = kv_parse(line)
        msg = kv.get("msg", "")
        if not looks_like_success(msg):
            continue

        # timestamp 우선순위: time -> vp_time -> syslog prefix(미지원)
        ts = None
        if "time" in kv:
            ts = parse_sonicwall_time(kv["time"])
        if ts is None and "vp_time" in kv:
            # vp_time="... UTC" 같은 케이스
            ts = parse_sonicwall_time(kv["vp_time"].replace(" UTC", ""))
        if ts is None:
            continue

        user = (kv.get("usr") or kv.get("user") or "").strip()
        if not user:
            continue

        src_ip = extract_src_ip(kv.get("src", "")) or ""

        events.append(VpnEvent(ts=ts, user=user, src_ip=src_ip, msg=msg))

    return events

def parse_idp_csv(path: str) -> list[IdpEvent]:
    events: list[IdpEvent] = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            ts_raw = (row.get("createdDateTime") or "").strip()
            user = (row.get("userPrincipalName") or "").strip()
            ip = (row.get("ipAddress") or "").strip()
            app = (row.get("appDisplayName") or "").strip()
            result = (row.get("result") or "").strip()

            if not (ts_raw and user):
                continue

            # createdDateTime은 UTC ISO8601을 가정: 2026-11-07T01:23:45Z
            try:
                ts = dt.datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                continue

            events.append(IdpEvent(ts=ts, user=user, ip=ip, app=app, result=result))

    return events

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--vpn-log", required=True)
    p.add_argument("--idp-csv", required=True)
    p.add_argument("--window-minutes", type=int, default=5)
    p.add_argument("--out-json", default="suspects.json")
    args = p.parse_args()

    with open(args.vpn_log, encoding="utf-8", errors="replace") as f:
        vpn_events = parse_vpn_events(f)

    idp_events = parse_idp_csv(args.idp_csv)

    # 사용자 기준으로 인덱싱
    idp_by_user: dict[str, list[IdpEvent]] = {}
    for e in idp_events:
        idp_by_user.setdefault(e.user.lower(), []).append(e)

    for u in idp_by_user:
        idp_by_user[u].sort(key=lambda x: x.ts)

    window = dt.timedelta(minutes=args.window_minutes)

    suspects = []
    matched = 0

    for v in vpn_events:
        ukey = v.user.lower()
        candidates = idp_by_user.get(ukey, [])

        ok = False
        for c in candidates:
            if abs(c.ts - v.ts) <= window:
                ok = True
                matched += 1
                break

        if not ok:
            suspects.append({
                "vpnTime": v.ts.isoformat(sep=" "),
                "vpnUser": v.user,
                "vpnSrcIp": v.src_ip,
                "vpnMsg": v.msg,
                "reason": f"No IdP sign-in within ±{args.window_minutes}m",
            })

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump({
            "vpnSuccessEvents": len(vpn_events),
            "idpEvents": len(idp_events),
            "matched": matched,
            "suspects": suspects,
        }, f, ensure_ascii=False, indent=2)

    print(f"VPN success events: {len(vpn_events)}")
    print(f"IdP events:        {len(idp_events)}")
    print(f"Matched:           {matched}")
    print(f"Suspects:          {len(suspects)}")
    print(f"Wrote:             {args.out_json}")

if __name__ == "__main__":
    main()
PY

chmod +x sslvpn_saml_gap_detector.py

# 실행 예시
./sslvpn_saml_gap_detector.py \
  --vpn-log ./sonicwall_sslvpn.log \
  --idp-csv ./idp_signins.csv \
  --window-minutes 5 \
  --out-json ./suspects.json
```

예상 출력 형태는 대략 아래처럼 떨어집니다.

```text
VPN success events: 128
IdP events:        141
Matched:           120
Suspects:          8
Wrote:             ./suspects.json
```

이 스크립트는 완벽한 탐지기를 목표로 하지 않습니다. 의도는 하나입니다.

*“SAML 강제 SSLVPN인데, IdP 흔적 없이 성공하는 로그인”* 을 빠르게 표면으로 끌어올리는 것.

여기서 suspects가 0이 나오면, (1) 정말 우회가 없었거나 (2) 로그 수집/정규화가 실패했거나 둘 중 하나입니다. 0이 나왔다고 안전하다고 결론내리면 안 되고, 샘플 계정을 잡아 수동으로도 교차 확인하는 게 맞습니다.

## 결론: alt auth를 방치한 SAML 강제는 설계가 아니라 희망에 가깝다

2026-11-07(KST) 시점에서 확인 가능한 사실만 놓고 보면, CVE-2026-19868은 “SAML을 붙여 MFA를 강제했다”는 운영팀의 자신감을 정면으로 겨냥합니다. GitHub Advisory의 문장 그대로, alt auth 자격 증명만으로 SAML 인증 제어가 우회될 수 있고 SAML-enforced MFA까지 건너뛸 수 있습니다.[^2]

여기에 캐나다 사이버센터가 “being exploited”를 명시했고, SonicWall PSIRT가 exploitation 보고를 조사했다는 보도까지 붙었습니다.[^4][^3]

이 조합이면 대응의 정답은 단순합니다.

* 패치(Gen7 7.3.4-7013+, Gen8 8.2.3-8015)를 최우선으로 적용한다.[^1]
* 그 다음은 “SAML을 켰다”가 아니라 “alt auth 경로가 SSLVPN에 대해 존재하지 않는다”를 증명한다.
* 마지막은 “IdP 이벤트 없는 VPN 로그인”을 상시 탐지 룰로 박아 넣는다.

이 세 가지를 묶어야, 이번 이슈를 ‘취약점 하나’가 아니라 ‘인증 경계 설계의 결함’으로 처리하게 됩니다.

## 참고 자료

- [SonicOS 7.3.4 and 8.2.3 Security Advisory — Gen 7 and Gen 8 Firewalls](https://www.sonicwall.com/support/notices/kA1VN000002eBLN0A2)
- [SonicWall security advisory (AV26-1133) - Canadian Centre for Cyber Security](https://www.cyber.gc.ca/en/alerts-advisories/sonicwall-security-advisory-av26-1133)
- [GitHub Advisory Database: GHSA-mq8w-j7h6-7q9w (CVE-2026-19868)](https://github.com/advisories/ghsa-mq8w-j7h6-7q9w)
- [SonicWall warns of new SSL-VPN MFA bypass flaw exploited in attacks (BleepingComputer)](https://www.bleepingcomputer.com/news/security/sonicwall-warns-of-new-ssl-vpn-mfa-bypass-flaw-exploited-in-attacks/)
- [SonicOS 8.2.3-8015 Release Notes](https://www.sonicwall.com/support/technical-documentation/docs/sonicos8-release_notes/Content/SonicOS-8-2-3-8015.htm)
- [SonicOS/X 7 SSL VPN 문서](https://www.sonicwall.com/support/technical-documentation/docs/sonicos-7-0-0-0-ssl_vpn/Content/ssl-vpn-about.htm)
- [How to configure SAML SSO on firewall for SSLVPN login using Azure AD as IdP? (SonicWall KB)](https://www.sonicwall.com/support/knowledge-base/kA1VN0000000NSr0AM)
- [SonicWall SSLVPN syslog 예시 정리(“SSLVPN: id=” 패턴 포함)](https://prophecyinternational.atlassian.net/wiki/spaces/SCV8/pages/786694167/Log%2BTypes%3A%2BSonicWallSSLVPN)
- [Microsoft Graph signIn resource type (createdDateTime, userPrincipalName, ipAddress 등)](https://learn.microsoft.com/en-us/graph/api/resources/signIn?preserve-view=true&view=graph-rest-beta)
- [Okta System Log에서 로그인/로그아웃 리포트 생성 가이드(user.session.start)](https://support.okta.com/help/s/article/Generate-a-User-LoginLogout-Report-via-System-Log)
- [Okta Event Types: user.session.start 설명(성공 세션을 ‘증명’하진 않는다는 주의 포함)](https://developer.okta.com/docs/reference/api/event-types/?q=device_logout)

[^1]: <https://www.sonicwall.com/support/notices/kA1VN000002eBLN0A2>
[^2]: <https://github.com/advisories/ghsa-mq8w-j7h6-7q9w>
[^3]: <https://www.bleepingcomputer.com/news/security/sonicwall-warns-of-new-ssl-vpn-mfa-bypass-flaw-exploited-in-attacks/>
[^4]: <https://www.cyber.gc.ca/en/alerts-advisories/sonicwall-security-advisory-av26-1133>
[^5]: <https://www.sonicwall.com/support/technical-documentation/docs/sonicos8-release_notes/Content/SonicOS-8-2-3-8015.htm>
[^6]: <https://www.sonicwall.com/support/technical-documentation/docs/sonicos-7-0-0-0-ssl_vpn/Content/ssl-vpn-about.htm>
[^7]: <https://www.sonicwall.com/support/knowledge-base/kA1VN0000000NSr0AM>
[^8]: <https://learn.microsoft.com/en-us/graph/api/resources/signIn?preserve-view=true&view=graph-rest-beta>
[^9]: <https://support.okta.com/help/s/article/Generate-a-User-LoginLogout-Report-via-System-Log>
[^10]: <https://developer.okta.com/docs/reference/api/event-types/?q=device_logout>
[^11]: <https://prophecyinternational.atlassian.net/wiki/spaces/SCV8/pages/786694167/Log%2BTypes%3A%2BSonicWallSSLVPN>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
