---
title: "프랑스 슈퍼마켓 냉장 설비 사이버공격: IT 장애가 식품 손실로 바뀌는 OT/IoT 패턴"
description: "Defrost·온도 파라미터 조작이 폐기·침수·재고공백으로 이어지는 경로와, 벤더 의존·망 분리·Fail-safe 체크리스트를 정리합니다."
date: 2026-10-17 09:34:26 +0900
categories: ["News", "Infrastructure"]
tags: ["ot-security", "retail", "cold-chain", "iot", "incident-response", "network-segmentation"]
render_with_liquid: false
---

## 사건을 숫자와 설정값으로 다시 읽기

2026년 10월 11일~12일(프랑스 현지 야간)에 프랑스 여러 리테일 체인의 냉장/냉동 설비가 원격으로 조작되면서, 매장 단위의 OT 장애가 즉시 상품 폐기와 운영 중단으로 전환됐습니다. *Le Monde*는 Intermarché 한 점주 인터뷰를 통해 “약 23시 공격 시작 추정 → 04시경 현장 발견”, 냉장실 온도 50°C 상승, 스프링클러 작동(침수)까지 이어졌다고 전했습니다. 또 공격자가 냉동/냉장 설비의 Defrost 관련 온도 목표를 50°C로 올리고, Defrost 사이클을 1시간에서 8시간으로 늘려 알람 발생을 늦췄다는 정황을 같이 적었습니다[^1].[^1]

영향 범위는 “한 체인의 일부 매장”이 아니라, 여러 체인이 같은 계열의 냉장 제어/감시 솔루션에 기대고 있다는 산업 구조가 그대로 노출된 형태에 가깝습니다. *Le Monde*는 Intermarché/Netto 약 300개 매장에 더해 Coopérative U(약 100), Carrefour(80), E.Leclerc 일부, Monoprix 약 30 등 다양한 네트워크가 영향을 받았다고 적었습니다[^1].[^1]

AP는 프랑스 사이버 보안 당국이 공격이 “여전히 진행 중일 가능성”을 경고했고, 냉장고(정확히는 냉장 설비의 원격 관리 경로)를 재연결할 때 secure VPN 또는 보호된 네트워크를 사용하라고 촉구했다고 전했습니다. 동일 기사에서 “수백 개 매장”의 설비가 원격 조작되었고, 약 6시간 동안 50°C까지 상승했으며, Intermarché가 “하루만에 수천만 유로 규모”의 손실을 언급했다고 보도했습니다[^2].[^2]

기술 관점에서 이번 사건이 중요한 이유는, 공격자가 랜섬웨어처럼 IT를 멈춰 세우지 않아도 “설정값 몇 개”로 물리계(온도·제상·수분)와 운영계(폐기·재주문·진열 공백)를 동시에 흔들 수 있다는 점이 확인됐기 때문입니다. 더 나아가 CERT-FR(ANSSI) 경보가 Danfoss 계열뿐 아니라 Copeland xweb, Dixell xweb까지 “다수의 compromise”를 인지했다고 명시하면서, 특정 벤더 1곳의 문제를 넘어 “인터넷에 노출된 냉장 원격 컨트롤러”라는 공통된 취약 운영 패턴이 드러났습니다[^3].[^4]

## 온도·Defrost 파라미터 변경이 손실로 이어지는 메커니즘

냉장/냉동 설비에서 Defrost는 얼음(서리) 제거를 위한 정상 운전 절차입니다. 증발기(evaporator) 표면이 결빙되면 열교환이 떨어지고, 공기 흐름이 막히면서 케이스 내부 온도가 서서히 상승합니다. 그래서 일정 주기로 히터(전기 히터)나 hot-gas, 혹은 off-cycle 방식으로 제상을 수행합니다.

문제는 Defrost가 정상 운전일 때도 **냉각을 잠시 멈추고(또는 효율을 떨어뜨리고) 온도를 올리는 작업**이라는 점입니다. 공격자가 손대기 쉬운 파라미터는 대략 아래 부류로 묶입니다.

- 온도 setpoint(목표 온도): 냉장 케이스(예: 2~4°C), 냉동 케이스(예: -18°C 이하)
- Defrost 스케줄: 하루 몇 회/몇 시간 간격으로 제상을 돌릴지
- Defrost 종료 조건: 시간 종료(time termination) vs 온도 종료(temp termination) vs 둘의 조합
- Defrost 목표 온도/히터 제어: 제상 중 어느 온도까지 올릴지, 안전 제한이 무엇인지
- 알람 설정: 알람 threshold(경보 기준), 알람 지연(delay), 알람 전달 경로(메일/SMS/센터)

*Le Monde*가 전한 “Defrost 온도 목표 50°C”와 “Defrost 1시간→8시간”은, 이 중에서 가장 직접적으로 물리계를 망가뜨리는 조합입니다[^1].[^1]

왜 이게 바로 손실로 변환되는지, 냉동 케이스를 기준으로 과정을 쪼개보면 다음과 같습니다.

1) Defrost 강제 진입 또는 주기 과도화
- 정상이라면 Defrost는 “필요할 때만” 짧게 돌아야 합니다.
- 공격으로 Defrost가 계속 켜지거나(강제), 지나치게 자주 실행되면, 그 시간만큼 냉각 사이클이 줄어듭니다.

2) Defrost 목표 온도 상승 + 종료 지연
- 제상은 열을 넣습니다. 목표 온도가 50°C 같은 수준으로 올라가면, 냉각 대상 공간이 사실상 히터에 노출됩니다.
- 종료를 시간으로 잡아두고 8시간으로 늘리면, “서서히 망가지는” 게 아니라 밤 사이에 한 번에 끝이 나버립니다.

3) 코일에서 녹은 물 증가 → 배수/트레이/배관이 감당 못함
- 얼음이 녹으면서 물이 생깁니다. 제상이 길어지고 온도가 높아질수록 물은 더 많이 생깁니다.
- 배수 라인이 얼어 있거나(다른 구간 결빙), 트레이 용량이 작거나, 펌프가 있는 경우 펌프가 정지하면 물이 넘칩니다.

4) 침수는 OT 고장을 IT 고장으로 확장시킴
- 냉장실 바닥 침수는 전기 설비(분전반, 센서, 누전차단기)에 영향을 줍니다.
- 재고 공간 침수는 포장 파손/오염으로 폐기 범위를 키웁니다.

5) 스프링클러/화재 감지 계통과 결합되면 피해가 기하급수적으로 증가
- *Le Monde*는 냉장실 50°C로 스프링클러가 작동했고, 일부 장비가 80°C까지 올라가 녹았다는 Facebook 게시물을 인용했습니다[^1].[^1]
- BleepingComputer는 파리 검찰/AFP를 인용해 식품 손실과 더불어 화재 발생 신고까지 언급하며 수사를 전했습니다[^4].[^4]

여기에 “식품 안전 기준”이 운영 손실을 확정해버리는 역할을 합니다. 냉장·냉동 상품은 품질 이슈 이전에 안전/규정 이슈가 먼저 옵니다. USDA FSIS의 일반 가이드만 보더라도 냉장고는 40°F(약 4.4°C) 이하 유지가 권고되고, 40°F 초과 상태가 2시간 이상이면 폐기를 권장합니다[^5].[^5]

프랑스의 식품 규정은 프랑스·EU 체계로 따로 확인해야 하지만, 리테일 운영의 현실은 국가를 크게 가리지 않습니다. 온도가 한 번 올라가면 “다시 내리면 된다”가 아니라, 그 시간 구간에 노출된 SKU를 추적해서 과감하게 폐기해야 리스크를 닫을 수 있습니다. 그래서 IT 관점에서 “일부 컨트롤러가 이상 동작”이었더라도, 물류/매장 관점에서는 곧바로 “수많은 SKU 폐기 + 재주문 + 진열 공백”이 됩니다.

## ‘식품 공급망 손실’로 변환되는 운영 경로

냉장 설비 사고가 공급망 손실이 되는 경로는 단순히 “상품이 상한다”가 아닙니다. 손실이 커지는 지점은 대체로 세 갈래입니다.

### 1) 폐기(shrink)가 재고 정확도를 무너뜨리는 속도

리테일은 재고 장부(inventory ledger)와 현물 간 오차를 늘 관리합니다. 그런데 냉장/냉동 사고는 한 번에 큰 덩어리의 폐기를 강제합니다. 폐기가 빠르게 이뤄지면 장부는 따라가겠지만, 현실에서는 새벽 시간대 인력, 폐기 승인 프로세스, 증빙(사진/온도 로그) 때문에 “폐기 확정”이 늦어집니다.

그 사이에 발생하는 문제는 다음입니다.

- POS/주문 시스템은 아직 재고가 있다고 판단해서 프로모션/주문을 이어감
- 온라인 장보기/픽업은 주문을 받았는데 피킹할 재고가 없음
- 대체 SKU로 치환하면서 고객 불만과 환불이 발생

AP가 언급한 “Intermarché 하루 손실 수천만 유로”는, 냉장 상품이 가진 회전율과 매장 수를 고려하면 과장이라기보다 구조적 결과에 가깝습니다[^2].[^2]

### 2) 매장 단위 사고가 DC까지 전파되는 방식

매장 여러 곳에서 동시다발 폐기가 발생하면, DC는 평소 수요 예측과 다르게 급격한 보충 주문을 받습니다. 냉장/냉동은 상온과 다르게 다음 조건이 붙습니다.

- 냉장/냉동 트럭·도크 용량 제한
- 팔레트 단위 출고(케이스 단위가 안 되는 경우)
- 유통기한/FEFO 정책(First-Expire-First-Out) 재계산

“어느 매장이 얼마나 버렸는지”가 빨리 정리되지 않으면 DC는 보충을 과잉으로 내보내거나, 반대로 부족으로 보내게 됩니다. 여기서부터는 IT 복구가 끝나도 손실 곡선이 계속 이어집니다.

### 3) 손실이 ‘품질’이 아니라 ‘컴플라이언스/책임’으로 고정되는 순간

냉장/냉동 사고는 고객에게 판매되기 전에 내부에서 대부분 폐기로 끝나야 합니다. 판매가 발생하면 식중독·리콜·소송 리스크로 성격이 변합니다. 그래서 현장 관리자 입장에서는 “의심되면 폐기”가 기본이 됩니다.

이 지점에서 공격자는 아주 저렴한 비용으로 비싼 손실을 일으킵니다. 랜섬웨어처럼 복호화 협상을 하지 않아도, ‘물리 운영’을 때리면 기업이 알아서 돈을 태웁니다.

## 외부 벤더/관리 서비스 의존성: 원격 운영의 비용

이번 사건을 OT/IoT 교차 영역에서 봐야 하는 핵심은, “누가 냉장 설비를 관리하는가”입니다. 매장 직원이 냉동기 제어를 직접 보지 않는 구조가 이미 일반적입니다.

- *Le Monde*는 Metro(도매)가 “external service provider”가 공격 표적이었다고 말하며 즉시 제품 보관 상태를 점검했다고 전했습니다[^1].[^1]
- BleepingComputer는 Intermarché 대변인 발언으로 “매장 냉장 시스템을 관리하는 service provider가 영향을 받았다”는 표현을 인용했습니다[^4].[^4]
- *Le Monde Pixels*는 Système U 측이 “U 매장은 Danfoss 솔루션을 제공하는 refrigeration specialist의 고객”이라고 말하며, 슈퍼마켓이 그 IT 시스템을 직접 관리하지 않는 구조를 다시 확인시켰습니다[^6].[^6]

이 구조는 운영 효율을 올립니다.

- 24/7 원격 모니터링
- 야간 장애 탐지 및 출동 최적화
- 에너지 최적화(전력 피크 대응)

대신 보안의 실패 모드가 바뀝니다. “매장 LAN이 털린다”가 아니라, 벤더·유지보수 업체·원격 포털·northbound 연동(XML, API) 중 한 군데가 뚫리면 여러 매장이 동시에 맞습니다.

Danfoss가 문서에서 원격 인터페이스를 StoreView Browser/StoreView Web/Alsense/3rd-party XML로 명시하는데, 이런 구성이 바로 운영 현장의 현실입니다[^7].[^7]

여기서 중요한 건 “원격이 나쁘다”가 아닙니다. 원격 운영이 필요한 이유는 명확합니다. 다만 원격의 구현이 종종 다음 형태로 흘러갑니다.

- 공인 IP에 관리 UI(HTTP/HTTPS)를 직접 노출
- 협력사 IP allowlist 정도로 해결(그리고 IP가 바뀌면 귀찮아서 결국 0.0.0.0/0)
- 장비는 10년 이상 쓰는데 펌웨어 업데이트/교체는 미뤄짐

CERT-FR이 경보에서 “인터넷에 관리 인터페이스 노출은 best practice에 반한다”고 못 박고, 장비가 compromise되지 않았더라도 “구성 전체(특히 Defrost 스케줄)를 점검”하라고 강조한 이유가 여기에 있습니다[^3].[^8]

또 하나 놓치기 쉬운 포인트가 경보에 들어 있습니다. 인터넷 노출을 끊을 때 “보험 계약 조건을 확인하라”는 문구입니다. 기술적으로는 당장 끊는 게 맞아도, 산업 현장에서는 사고 대응이 곧바로 책임/보상 체계와 연결됩니다[^3].[^8]

## 이번 사건이 보여준 OT/IoT 사고 패턴

### 패턴 1: Internet-exposed controller는 결국 언젠가 조작된다

CERT-FR이 Danfoss AK-SM/AK-SC, Copeland xweb, Dixell xweb까지 영향을 언급한 것은, 단일 CVE의 문제가 아니라 “노출된 원격 컨트롤러”라는 운영 패턴을 문제 삼는 쪽에 가깝습니다[^3].[^8]

BleepingComputer는 공격이 “구버전 Danfoss control software”를 쓰는 컨트롤러를 하이재킹했고, 자동 Defrost 기능을 악용해 온도를 올렸다고 전했습니다[^4].[^4]

핵심은 “컨트롤러가 인터넷에 보인다”는 사실 자체가 공격 난이도를 바닥으로 떨어뜨린다는 점입니다. IT 서버라면 WAF/EDR/로그/패치 파이프라인이 어느 정도라도 돌아가지만, 이런 장비는 그 기대치를 충족하기 어렵습니다.

### 패턴 2: 설정 변경은 탐지가 어렵고, 결과는 물리적으로 확정된다

Claroty Team82가 Danfoss AK-SM 800A 취약점 분석에서 강조한 부분은, 취약점 자체(CVE-2025-41450/41451/41452)도 있지만 “컨트롤러가 중앙 감시/조정(supervisory) 역할을 한다”는 구조적 리스크입니다. Danfoss는 펌웨어 R4.3.1에서 이를 수정했고, Team82는 관리 인터페이스를 인터넷에 직접 노출하지 말고 VPN/segmentation을 권고했습니다[^9].[^9]

Copeland XWEB Pro에 대해서도 Claroty는 23개 취약점을 공개하면서, Internet-exposed XWEB에서 시작해 실제 냉장 시스템을 조작하는 물리 데모를 수행했다고 적었습니다. 그리고 Copeland가 firmware 1.13 업데이트를 올렸다고 명시했습니다[^10].[^10]

설정 변경 기반 공격이 무서운 이유는 간단합니다.

- 서비스가 “죽지” 않을 수 있습니다.
- 그래프가 그럴듯할 수 있습니다.
- 알람을 늦추거나 끌 수 있습니다.

결과적으로 탐지 포인트는 IT의 가용성/지표가 아니라, OT의 상태 변화를 직접 감시하는 쪽으로 이동해야 합니다.

### 패턴 3: 벤더가 보안 모드를 강화해도, 현장은 backward-compatible로 되돌린다

Danfoss는 AK-SM 800A에서 Session Control(Backward compatible / Permissive / Strict)을 제공하고, 4.0.x 이상에서 Strict를 기본값으로 둔다고 안내합니다[^7].[^7]

또 AK-SM 800A User Guide는 장비가 “secure network와 firewall 뒤”에 설치되어야 하며, 공개/비보호 네트워크에 두지 말고 HTTPS와 Strict 설정을 권고하는 문구를 상당히 직접적으로 넣고 있습니다[^11].[^11]

그런데 현실에서는 다음 일이 일어납니다.

- 오래된 3rd-party XML 연동이 username/password 평문을 기대함
- 협력사 포털이 HTTP만 지원하는 구간이 남아 있음
- 현장 유지보수 인력이 “업데이트 후 접속이 안 된다”를 가장 싫어함

그래서 Strict가 “권고”로 머물면, 결국 공격 표면이 유지됩니다. 문서가 있어서 해결되는 문제가 아니라, 아키텍처에서 강제되어야 닫힙니다.

## 방어 체크리스트: 분리·모니터링·Fail-safe 설계

여기서는 냉장/냉동 설비를 “Purdue Model 교과서”로만 보지 않고, 리테일/물류 운영의 제약을 포함한 체크리스트로 정리합니다. NIST SP 800-82는 ICS에서 VPN 같은 안전한 원격 접근과 접근 통제를 강조합니다[^12].[^12]

### 1) 네트워크 분리: ‘냉장 OT’를 매장 IT에서 떼어내는 수준 정의

목표는 단순 VLAN 분리가 아니라, “침해가 일어나도 blast radius를 매장 1개 이하”로 줄이는 것입니다.

- **Zone 정의**
  - Store IT(포스, 직원 Wi‑Fi, CCTV, 키오스크)
  - Refrigeration OT(컨트롤러, PLC/IO, 케이스 센서)
  - Remote Access Zone(점프 서버, VPN 종단)
  - Vendor/Service Provider Zone(협력사 NOC)

- **Conduit 정의(통신 경로)**
  - Vendor → Jump host/VPN → OT 관리망 단일 경로만 허용
  - OT → 외부(telemetry 업링크)는 최소화(가능하면 단방향에 가까운 모델)

IEC 62443의 zone-and-conduit 모델은 이런 식의 분리를 설명하는 언어를 제공합니다. 표준 원문은 유료 접근이 많은 편이라, 최소한의 공통 용어로라도 팀 내에 모델을 고정해두는 게 효과가 큽니다[^13][^14].[^13]

실무에서 자주 실패하는 지점은 “냉장 컨트롤러가 매장 공유 회선의 공인 IP로 바로 나간다”입니다. 매장 수가 많아질수록 이 유혹이 커집니다. 초기 설치 비용이 가장 싸기 때문입니다. 대신 운영비(사고 비용)가 폭발합니다.

### 2) 외부 벤더 접근 설계: ‘가능한가’가 아니라 ‘어떻게 강제할 것인가’

CERT-FR이 제시한 방향은 명확합니다.

- 인터넷 노출 제거
- 접근은 secure VPN 또는 보호 네트워크로만
- 펌웨어 업데이트, 패스워드 변경
- Defrost 스케줄 포함한 구성 무결성 점검

[^3][^8]

이를 리테일 현장에 맞추면 다음 통제 포인트가 됩니다.

- 협력사 계정은 개인 계정으로 발급(공용 계정 금지)
- MFA는 “포털 로그인”이 아니라 “OT 접근 경로”에 강제(VPN/jump)
- IP allowlist는 응급 수단으로만 두고, 장기 대안으로 삼지 않기
- 점프 호스트에서만 세션을 열고, 그 세션의 커맨드/파일 이동을 기록
- 원격 접속 창구(변경 작업)는 시간 창(maintenance window)으로 제한

Danfoss가 Session Control의 Strict 모드에서 HTTPS와 session token 기반 인증(AKSM-auth header)을 요구하는 것도 결국 같은 목적을 향합니다[^7][^11].[^7]

여기서 중요한 운영 팁이 하나 있습니다. “원격 접속을 막으면 장애 대응이 늦어진다”는 반론은 사실입니다. 그래서 정답은 원격을 없애는 게 아니라, 원격을 ‘단일화’하는 쪽입니다. 한 곳으로 모으면 기록과 통제가 생깁니다.

### 3) 모니터링: 온도 그래프가 아니라 ‘설정값 드리프트’를 본다

냉장 설비는 일반적인 IT 서비스처럼 CPU/메모리로 건강을 판단하기 어렵습니다. 특히 설정 변경 기반 공격은 시스템이 멀쩡해 보일 수 있습니다.

권장하는 감시 신호는 두 축입니다.

- **Process 변수(결과)**
  - 케이스/룸 공기 온도, 제품 온도(가능하면 별도 프로브)
  - Defrost 실행 횟수/누적 시간
  - 컴프레서 duty cycle

- **Configuration 변수(원인)**
  - setpoint, defrost schedule, defrost termination, alarm delay
  - 변경 이력(audit log) + 변경 주체(계정/원격 IP/작업 티켓)

*Le Monde*가 언급한 “Defrost 1시간→8시간”은 결과가 나오기 전까지는 단지 ‘설정값’입니다. 그렇기 때문에 설정값이 바뀌는 순간을 잡으면 피해를 크게 줄일 수 있습니다[^1].[^1]

특히 리테일은 야간에 사람이 없습니다. 알람이 3시간 지연되는 순간 게임이 끝납니다.

### 4) Fail-safe: ‘컨트롤러가 적’이 됐을 때도 최소 피해로 멈추는 장치

Fail-safe는 여기서 기계적 안전(압력, 온도 릴리프)만 말하는 게 아닙니다. 식품 손실을 제한하는 안전도 포함해야 합니다.

- Defrost 최대 지속 시간 hard limit(장비/현장 정책으로 상한)
- Defrost 목표 온도 상한(물리적으로 50°C 같은 값이 들어가도 무시)
- 알람 지연 상한(지연은 하되 상한을 둠)
- 원격 설정 변경이 감지되면 자동으로 “현장 확인 모드”로 전환(승인 없이는 반영 지연)
- 인터넷/VPN이 끊겨도 냉각은 로컬 루프로 계속 수행(원격 의존성을 냉각 루프 밖으로)

이런 Fail-safe는 보안팀 단독으로 못 합니다. 냉동기 업체/설비 엔지니어/QA(식품 안전)/물류 운영까지 같이 테이블에 올라와야 합니다.

## 운영 관점 IR 체크리스트: ‘복구’가 아니라 ‘폐기 경계 확정’

이번 사건을 IT incident로만 다루면 항상 뒤집니다. 온도는 시간이 지나면 원상복구되지만, 상품은 원상복구되지 않습니다. 그래서 초기 1~3시간에 해야 할 일이 IT 복구보다 “손실 경계 확정”일 때가 많습니다.

### 0) 전제: 증거 보존보다 더 급한 건 ‘물리 피해 확장 중지’

CERT-FR은 노출 제거를 우선하라고 씁니다. 먼저 위험 구역에서 빠져나오고(인터넷 노출 제거), 다음에 복구(VPN 통한 재연결, 펌웨어 업데이트)로 넘어갑니다[^3].[^8]

이 순서는 OT에서 특히 중요합니다. 공격이 진행 중일 수 있고, 조작이 반복될 수 있기 때문입니다.

### 1) 첫 30분: “어느 매장/어느 존이 흔들렸는지”를 물류 언어로 번역

- 영향을 받은 매장 리스트(확정/의심)
- 매장별 냉장 존(냉동 케이스, 육류, 유제품, 냉장 창고, 백룸) 매핑
- 존별 안전 기준(온도·시간)을 내부 정책으로 선언
- 폐기 승인 권한(현장 vs 본사)과 증빙 포맷 확정

이 단계에서 도움이 되는 사고 대응 문서 형태는, 예전에 내가 썼던 “외부 노출 인스턴스 런북”이나 “IoC 기반 조사/격리 런북” 쪽과 가깝습니다. 다만 대상이 GitLab/FortiMail이 아니라 냉장 OT로 바뀌었을 뿐입니다.

- [GitLab CVE-2026-85706 야생 악용: 외부 노출 인스턴스 운영 런북](https://daewooki.github.io/posts/gitlab-cve-2026-85706-ops-runbook/)
- [FortiMail CVE-2026-104286 제로데이: IoC 기반 조사·격리·업데이트 런북](https://daewooki.github.io/posts/fortimail-cve-2026-104286-ops-runbook/)

### 2) 첫 2시간: 온도 텔레메트리로 ‘폐기 대상 후보’를 자동 산출

냉장 설비 컨트롤러 로그만 보면 조작 여부를 놓칠 수 있습니다. 별도 센서(독립 프로브) 또는 스토어 데이터 레이크에 들어오는 온도 텔레메트리를 활용해서, 폐기 후보 SKU를 빠르게 뽑아두는 게 현실적인 방어입니다.

아래 코드는 “매장별 존 온도 로그 + 존 타입(chilled/frozen) + 내부 임계치 정책”을 넣으면, 임계치 초과 구간을 뽑아서 폐기/점검 우선순위를 출력합니다. 법적/규정 기준을 대신하는 코드는 아니고, 운영상 triage를 위한 자동화입니다. 냉장 보관 안전 온도에 대한 일반 가이드는 USDA FSIS 문서를 기준으로 삼아(냉장 40°F 이하 권장), 내부 정책 임계치를 구성하는 방식을 권합니다[^5].[^5]

#### 실행 환경

- Python 3.12+
- pandas 2.2+

```bash
python -m venv .venv
source .venv/bin/activate
pip install pandas
python coldchain_excursions.py --temps temps.csv --zones zones.csv
```

#### 입력 데이터 예시

`zones.csv`
```csv
store_id,zone_id,zone_type
FR-IM-001,FREEZER-1,frozen
FR-IM-001,CHILL-DAIRY,chilled
FR-U-014,FREEZER-2,frozen
FR-U-014,CHILL-MEAT,chilled
```

`temps.csv`
```csv
ts,store_id,zone_id,temp_c
2026-10-12T01:00:00+02:00,FR-IM-001,FREEZER-1,-20.5
2026-10-12T01:10:00+02:00,FR-IM-001,FREEZER-1,-3.0
2026-10-12T01:20:00+02:00,FR-IM-001,FREEZER-1,12.0
2026-10-12T02:00:00+02:00,FR-IM-001,CHILL-DAIRY,3.0
2026-10-12T02:30:00+02:00,FR-IM-001,CHILL-DAIRY,18.0
2026-10-12T03:00:00+02:00,FR-U-014,CHILL-MEAT,6.0
2026-10-12T03:40:00+02:00,FR-U-014,CHILL-MEAT,12.5
```

#### 코드

`coldchain_excursions.py`
```python
import argparse
import pandas as pd

DEFAULT_THRESHOLDS = {
    # 운영 triage용 예시 임계치
    # chilled: 4.4C(40F) 초과 시 위험 신호
    "chilled": {"warn_above_c": 4.4, "critical_above_c": 10.0},
    # frozen: -18C(0F) 이상(따뜻해짐)부터 품질/안전 리스크 신호
    "frozen": {"warn_above_c": -18.0, "critical_above_c": -10.0},
}

def load_inputs(temps_path: str, zones_path: str) -> pd.DataFrame:
    temps = pd.read_csv(temps_path)
    zones = pd.read_csv(zones_path)

    temps["ts"] = pd.to_datetime(temps["ts"], utc=True)
    df = temps.merge(zones, on=["store_id", "zone_id"], how="left")

    if df["zone_type"].isna().any():
        missing = df[df["zone_type"].isna()][["store_id", "zone_id"]].drop_duplicates()
        raise SystemExit(f"zone_type 매핑 누락: {missing.to_dict(orient='records')}")

    return df.sort_values(["store_id", "zone_id", "ts"]).reset_index(drop=True)

def classify(df: pd.DataFrame) -> pd.DataFrame:
    def label_row(row):
        th = DEFAULT_THRESHOLDS[row["zone_type"]]
        t = row["temp_c"]
        if t > th["critical_above_c"]:
            return "critical"
        if t > th["warn_above_c"]:
            return "warn"
        return "ok"

    df = df.copy()
    df["level"] = df.apply(label_row, axis=1)
    return df

def excursions(df: pd.DataFrame) -> pd.DataFrame:
    # 동일 store/zone에서 level이 ok->warn/critical로 바뀌는 구간을 묶음
    out = []

    for (store_id, zone_id), g in df.groupby(["store_id", "zone_id"], sort=False):
        g = g.sort_values("ts")
        # 구간 id 생성
        change = (g["level"] != g["level"].shift(1)).cumsum()
        g = g.assign(segment=change)

        for _, seg in g.groupby("segment"):
            level = seg["level"].iloc[0]
            if level == "ok":
                continue
            out.append(
                {
                    "store_id": store_id,
                    "zone_id": zone_id,
                    "zone_type": seg["zone_type"].iloc[0],
                    "level": level,
                    "start_ts": seg["ts"].min(),
                    "end_ts": seg["ts"].max(),
                    "max_temp_c": seg["temp_c"].max(),
                    "samples": len(seg),
                }
            )

    return pd.DataFrame(out).sort_values(["level", "max_temp_c"], ascending=[False, False])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--temps", required=True)
    ap.add_argument("--zones", required=True)
    args = ap.parse_args()

    df = load_inputs(args.temps, args.zones)
    df = classify(df)
    ex = excursions(df)

    if ex.empty:
        print("NO EXCURSIONS")
        return

    # 사람이 보는 출력
    ex_print = ex.copy()
    ex_print["start_ts"] = ex_print["start_ts"].dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    ex_print["end_ts"] = ex_print["end_ts"].dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    print(ex_print.to_string(index=False))

if __name__ == "__main__":
    main()
```

#### 예상 출력 예시

```text
store_id   zone_id zone_type    level               start_ts                 end_ts  max_temp_c  samples
FR-IM-001 FREEZER-1    frozen critical 2026-10-11 23:10:00 UTC 2026-10-11 23:20:00 UTC       12.0        2
FR-IM-001 CHILL-DAIRY   chilled critical 2026-10-12 00:30:00 UTC 2026-10-12 00:30:00 UTC       18.0        1
FR-U-014  CHILL-MEAT   chilled     warn 2026-10-12 01:00:00 UTC 2026-10-12 01:00:00 UTC        6.0        1
FR-U-014  CHILL-MEAT   chilled critical 2026-10-12 01:40:00 UTC 2026-10-12 01:40:00 UTC       12.5        1
```

이 결과를 SKU 매핑(존↔진열대↔상품)과 결합하면, “어느 점포의 어떤 카테고리를 우선 폐기/격리할지”가 IT 복구보다 먼저 정리됩니다.

### 3) 24시간 내: 재발 방지 조치의 우선순위를 ‘패치’보다 ‘도달성 제거’로 둔다

CERT-FR은 reset factory만으로는 충분하지 않다고 경고합니다. 취약 상태로 인터넷에 다시 노출되면 다시 compromise될 가능성이 높다고 적습니다[^3].[^8]

이 말은 OT에서 굉장히 실무적입니다.

- 패치는 몇 주/몇 달 걸릴 수 있습니다.
- 회선/방화벽에서 internet exposure를 끊는 건 당일 가능합니다.

그래서 우선순위를 바꾸는 게 맞습니다.

1) Public exposure 제거(라우팅/포트포워딩/NAT 정리)
2) 원격은 VPN/Jump로 단일화
3) 구성 무결성 점검(Defrost 포함)
4) 그 다음에 펌웨어 업데이트 계획

## 반론과 불확실성: 아직 확인되지 않은 것들

이번 사건을 정리할 때 주의해야 할 점도 분명합니다.

- 침투 벡터는 확정되지 않았습니다. BleepingComputer도 “어떻게 compromise됐는지 정보가 없다”고 전제합니다[^4].[^4]
- Danfoss의 특정 CVE가 실제로 쓰였는지(예: CVE-2025-41450/41451)도 사건 시점에서는 단정하기 어렵습니다. 취약점 연구/패치/노출 장비 수는 강한 정황이지만, 포렌식 결과가 나오기 전에는 “가능한 경로”로만 두는 게 맞습니다.
- *Le Monde Pixels*의 “-22에서 150으로 변경” 같은 표현은 단위(°C/°F), 특정 장비의 표시 방식 등 해석 리스크가 있습니다. 다만 핵심은 숫자 자체보다 “Defrost/온도 regulation 설정을 초당 2~3개씩 바꾸는 자동화된 조작이 관측됐다”는 운영 징후입니다[^6].[^6]

이 불확실성은 오히려 결론을 단단하게 만듭니다. 특정 취약점 하나를 막는다고 끝날 문제가 아니라, “인터넷에서 만져지는 냉장 컨트롤러”라는 구조를 고치지 않으면 같은 형태가 반복됩니다.

## 앞으로 지켜볼 것: 조사 결과가 나와도 남는 과제

AP는 프랑스 사이버 보안 당국이 공격이 계속될 수 있다고 경고하고, VPN을 통한 재연결과 펌웨어 업데이트, 패스워드 변경을 권고했다고 전했습니다[^2].[^2]

여기서부터는 “누가 했다”가 밝혀져도, 실무적으로는 아래가 더 중요합니다.

- 리테일 체인들이 원격 운영을 어떤 형태로 재설계하는가(서비스 provider 단일화, Jump/VPN 강제, 계정 체계)
- EOL 장비(업데이트 불가)를 어떤 속도로 교체할 수 있는가
- 냉장/냉동 OT를 ‘매장 IT’에서 떼어내는 비용을 누가 부담하는가(본사/가맹/벤더)
- 보험/컴플라이언스가 기술 의사결정(인터넷 차단)을 방해하는 지점이 어떻게 정리되는가

내가 보는 결론은 단순합니다. 냉장 설비는 더 이상 백룸의 기계가 아니라, 중앙에서 원격으로 관리되는 cyber-physical 시스템입니다. 그래서 공격자에게는 설정값 몇 개로 손실을 확정할 수 있는 표적이고, 운영자에게는 “가용성”보다 “무결성(설정/알람/온도 경계)”이 더 중요한 OT가 됐습니다.

## 참고 자료

- [Le Monde: A disastrous day for French supermarkets after massive cyberattack targets refrigeration systems](https://www.lemonde.fr/en/economy/article/2026/10/13/a-disastrous-day-for-french-supermarkets-after-massive-cyberattack-targets-refrigeration-systems_6758535_19.html)
- [Le Monde Pixels: After Danfoss, hackers strike other refrigeration systems used in France](https://www.lemonde.fr/en/pixels/article/2026/10/13/after-danfoss-hackers-strike-other-refrigeration-systems-used-in-france_6758565_13.html)
- [AP News: France’s cybersecurity authority warns supermarket refrigeration attack may be ongoing](https://apnews.com/article/81c2d5721f4df77f601f71741ef7c291)
- [BleepingComputer: Cyberattack shuts down refrigerators at French supermarkets](https://www.bleepingcomputer.com/news/security/cyberattack-shuts-down-refrigerators-at-french-supermarkets/)
- [CERT-FR: CERTFR-2026-ALE-012 Incident de sécurité ciblant les contrôleurs à distance des installations de réfrigération](https://cert.cyber.gouv.fr/alerte/CERTFR-2026-ALE-012)
- [Claroty Team82: Freeze the Controller, Defrost the Food (Danfoss AK-SM 800A)](https://claroty.com/team82/research/freeze-the-controller-defrost-the-food-uncovering-vulnerabilities-in-danfoss-refrigeration-controllers)
- [Claroty Team82: Chilling Discoveries (Copeland XWEB Pro)](https://claroty.com/team82/research/chilling-discoveries-unpacking-vulnerabilities-in-copeland-xweb-pro-controllers)
- [Danfoss: AK-SM 800A Series 다운로드/보안 안내(Session Control, Strict 모드)](https://www.danfoss.com/en/service-and-support/downloads/dcs/adap-kool-software/ak-sm-800a)
- [Danfoss: DSA-2025-03-01 (CVE-2025-41450) 보안 권고](https://www.danfoss.com/en/service-and-support/coordinated-vulnerability-disclosure/danfoss-security-advisories/dsa-2025-03-01)
- [Danfoss: AK-SM 800A User Guide (보안 권고, 포트 테이블, HTTPS/Strict)](https://assets.danfoss.com/documents/latest/471013/BC337629891709en-000901.pdf)
- [Copeland: XWEB-PRO Security update Product Bulletin (firmware 1.13)](https://webapps.copeland.com/dixell/Content/Pages/SystemSoftwareUpdate/XWEB-PRO/Security%20update%20%20XWEB-PRO%20-%20Product_Bulletin_February_2026.pdf)
- [USDA FSIS: Refrigeration & Food Safety](https://www.fsis.usda.gov/food-safety/safe-food-handling-and-preparation/food-safety-basics/refrigeration)
- [NIST SP 800-82r3: Guide to Operational Technology (OT) Security](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-82r3.pdf)
- [GitLab CVE-2026-85706 야생 악용: 외부 노출 인스턴스 운영 런북](https://daewooki.github.io/posts/gitlab-cve-2026-85706-ops-runbook/)
- [FortiMail CVE-2026-104286 제로데이: IoC 기반 조사·격리·업데이트 런북](https://daewooki.github.io/posts/fortimail-cve-2026-104286-ops-runbook/)
- [Cloudflare IAD 성능 이슈가 전 서비스 에러로 번지는 패턴](https://daewooki.github.io/posts/cloudflare-iad-incident-resilience/)

[^1]: <https://www.lemonde.fr/en/economy/article/2026/10/13/a-disastrous-day-for-french-supermarkets-after-massive-cyberattack-targets-refrigeration-systems_6758535_19.html>
[^2]: <https://apnews.com/article/81c2d5721f4df77f601f71741ef7c291>
[^3]: <https://cert.cyber.gouv.fr/alerte/CERTFR-2026-ALE-012>
[^4]: <https://www.bleepingcomputer.com/news/security/cyberattack-shuts-down-refrigerators-at-french-supermarkets/>
[^5]: <https://www.fsis.usda.gov/food-safety/safe-food-handling-and-preparation/food-safety-basics/refrigeration>
[^6]: <https://www.lemonde.fr/en/pixels/article/2026/10/13/after-danfoss-hackers-strike-other-refrigeration-systems-used-in-france_6758565_13.html>
[^7]: <https://www.danfoss.com/en/service-and-support/downloads/dcs/adap-kool-software/ak-sm-800a>
[^8]: <https://www.cert.ssi.gouv.fr/alerte/CERTFR-2026-ALE-012?trk=public_post_comment-text>
[^9]: <https://claroty.com/team82/research/freeze-the-controller-defrost-the-food-uncovering-vulnerabilities-in-danfoss-refrigeration-controllers>
[^10]: <https://claroty.com/team82/research/chilling-discoveries-unpacking-vulnerabilities-in-copeland-xweb-pro-controllers>
[^11]: <https://assets.danfoss.com/documents/latest/471013/BC337629891709en-000901.pdf>
[^12]: <https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-82r3.pdf>
[^13]: <https://en.wikipedia.org/wiki/IEC_62443>
[^14]: <https://www.cisco.com/c/en/us/products/collateral/security/isaiec-62443-3-3-wp.html>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
