---
title: "Arista VeloCloud Orchestrator SQLi와 오케스트레이터 방어 설계"
description: "Arista Advisory 0199의 VCO On-Prem SQLi는 ‘활발 악용’이 확인됐고 고정 버전이 명확합니다. 웹 노출면 축소와 로그 기반 탐지를 우선순위로 재정렬합니다."
date: 2026-10-25 10:06:40 +0900
categories: ["News", "Networking"]
tags: ["arista", "velocloud", "sd-wan", "sqli", "cve-2026-114625", "incident-response"]
render_with_liquid: false
---

## 사건: Advisory 0199가 말한 것(그리고 말하지 않은 것)

Arista는 2026년 10월 22일에 Security Advisory 0199를 공개하면서 **CVE-2026-114625**를 다뤘습니다. 요약하면 VeloCloud Orchestrator(VCO) On-Prem에서 SQL injection(CWE-89)로 인해, 원격 공격자가 “privileged internal functionality”에 접근하고 VCO host에 영향을 줄 수 있다는 내용입니다. CVSS v3.1 9.9로 매우 높게 잡혔고, Arista가 “**known to be actively exploited**”라고 명시했습니다.[^1]

이 공지에서 특히 중요한 문장은 2개입니다.

1) “어떤 인증 사용자든(operator가 아니라 테넌트 사용자 포함) operator privilege로 상승할 수 있다”

- Arista는 “any authenticated user can gain operator privileges and masquerade as a local ‘superuser operator’ user”라고 씁니다. 즉, 취약점의 본질이 단순 데이터 탈취가 아니라 권한 경계가 무너지는 형태입니다.[^1]

2) “공격 성공 조건이 생각보다 낮다”

- “성공 조건은 VCO web interface에 대한 네트워크 접근 + 유효한 인증 세션”이고, 최소 역할이 **Enterprise Read Only**(내장된 테넌트 역할 중 최저)라고 박아 둡니다. 그리고 “VCO is exposed by default”, “There is no configuration that can prevent the exposure”까지 같이 나옵니다. 여기서 운영자가 얻어야 하는 결론은 단순합니다. 설정으로 피해갈 수 있는 종류가 아니고, 노출면이 넓은 배치가 많을 수 있다는 경고입니다.[^1]

패치 고정 버전도 명확합니다.

- 5.2.x: 5.2.3.18 미만 영향
- 6.1.x: 6.1.3.10 미만 영향
- 6.4.x: 6.4.2.12 미만 영향[^1]

“내 버전이 목록에 없으면 취약하지 않다”는 문장도 있습니다. 다만 Arista는 “End of support software versions have not been assessed”라고 덧붙입니다. 즉, EoS train을 쓰고 있으면 ‘취약/비취약’ 판정을 공지에서 못 받는 상태가 될 수 있습니다.[^1]

캐나다 Cyber Centre는 2026년 10월 23일자 경보(AV26-1080 Update 1)에서 영향을 받는 버전 범위와 “exploited in the wild”를 재확인했고, 같은 날 CISA가 KEV Database에 추가했다고도 적었습니다.[^2]

(부연) 내 환경에서는 cisa.gov의 KEV 상세 페이지가 403으로 열리지 않았습니다. 그래서 CISA 원문을 직접 인용하진 않고, 캐나다 Cyber Centre가 명시한 “추가되었다”는 사실까지만 확정으로 취급하는 편이 안전합니다.[^2]

---

## SD-WAN에서 ‘오케스트레이터 계층’이 뚫리면 피해가 커지는 이유

SD-WAN은 흔히 Edge 장비(브랜치 박스) 쪽이 전면에 보이지만, 실제로는 Orchestrator가 관리 plane의 단일 진입점(single pane of glass)이 되는 배치가 많습니다. Arista 문서도 “Orchestrator powers the management plane in the VeloCloud SD-WAN solution”이라고 표현합니다.[^3]

Orchestrator Portal은 네트워크/디바이스 설정을 관리하고, 현재/과거 상태를 조회할 수 있으며, API 클라이언트는 JSON-RPC 또는 REST-like 인터페이스로 같은 기능을 호출할 수 있다고 설명합니다. 특히 “문서에 나온 메서드는 어느 인터페이스로도 호출 가능”이라고 돼 있어, web UI와 자동화 API가 사실상 같은 기능 경계에 있다는 뜻입니다.[^3]

이 구조에서 Orchestrator 계층은 대략 이런 것들을 한 지점에 모읍니다.

- 구성 변경 권한(세그먼트, 라우팅/정책, 보안 정책 등)
- 토폴로지/상태 데이터(링크 품질, 터널 상태, 이벤트)
- 운영자 행위 로그(누가 어떤 설정을 바꿨는지)
- 여러 테넌트/파트너 모델(서비스 프로바이더 운영 모델)

취약점이 Edge 장비의 data plane에서 터진 게 아니라, Orchestrator의 web/API 계층에서 터졌다는 점이 무서운 이유는, “한 번 뚫리면 운영자가 하는 일을 그대로 공격자가 하게 된다”는 형태로 이어지기 때문입니다.

---

## 피해 모델: Read Only → operator 권한 상승 → 내부 기능 접근 → host impact

Advisory 0199는 “SQL injection”이라는 취약점 분류(CWE-89)를 말하지만, 실제 운영 관점에서 더 중요한 것은 권한 경계가 무너진다는 결과입니다. Arista 표현을 그대로 가져오면, 공격자는 operator privilege를 얻고 로컬 “superuser operator”로 가장할 수 있습니다.[^1]

여기서 피해 모델을 단계로 쪼개면, 방어 우선순위가 더 명확해집니다.

### 1) 초기 발화점: “인증이 필요한 취약점”의 착시

이 취약점은 pre-auth RCE처럼 보이진 않습니다. Arista도 “유효한 authenticated session이 필요”하다고 씁니다.[^1]

그런데 SD-WAN Orchestrator의 인증은 현실에서 다음 이유로 깨지기 쉽습니다.

- Read Only 계정은 만드는 심리적 저항이 낮아, 계정 수가 늘어나기 쉽습니다.
- 자동화/운영 연동(API client) 때문에 토큰/크레덴셜이 여러 시스템에 퍼집니다.
- 테넌트/파트너 모델에서는 외부 조직 인력에게도 포털 접근이 열릴 수 있습니다.

즉, “인증이 필요하니 덜 급하다”는 판단은 관리 plane에서 특히 위험합니다. 인증은 경계가 아니라 공격 표면의 한 부분이고, 낮은 권한 계정이 곧바로 고권한으로 도약하는 취약점이라면 이야기가 달라집니다.

### 2) 권한 상승: 최소 역할이 Enterprise Read Only

Arista가 최소 역할을 **Enterprise Read Only**라고 못 박았다는 게 중요합니다. “관리자는 아니고 보기만 하는 계정” 정도로 생각하기 쉬운 역할이, 취약점 체인에서는 ‘공격 버튼을 누를 수 있는 자격’이 됩니다.[^1]

이 유형은 내부자 위협뿐 아니라 “계정 하나만 새면 끝”이라는 성격을 띱니다. 공격자는 굳이 operator 계정을 얻을 필요가 없습니다.

### 3) 내부 기능 접근: Orchestrator가 제공하는 기능의 범위 자체가 넓다

Arista 문서 기준으로 Orchestrator Portal은 네트워크/디바이스 구성을 관리하고 상태를 질의합니다. API도 JSON-RPC/REST-like로 동일 기능을 호출 가능하며, 모두 HTTP POST로 들어온다고 명시돼 있습니다.[^3]

이 말은 곧 “권한이 올라간 계정이 할 수 있는 일의 반경(radius of blast)”이 매우 넓다는 뜻입니다. 오케스트레이터가 가진 힘은 개별 장비 쉘 접근보다 덜 위험한 게 아니라, 종종 더 위험합니다.

- 설정 변경은 여러 사이트/여러 Edge에 동시 전파가 가능합니다.
- 문제를 숨기기 위한 상태/모니터링 교란까지 같은 면에서 일어납니다.
- 운영자가 평소 하는 변경(정상 변경)과 공격자의 변경(악성 변경)이 같은 채널을 타므로, 탐지가 어려워집니다.

### 4) host impact: 단순 권한 상승을 넘는 침해 가능성

Advisory 0199는 “impact the VCO host”를 직접 언급합니다. 또 방어 권고에 “backdoor daemons”, “webshells” 모니터링이 들어가 있습니다. 이 조합은 실무적으로 이렇게 해석합니다.

- 공격 결과가 포털 내 권한 상승에 그치지 않고, OS/프로세스 레벨 지속성(persistence)까지 이어질 수 있다는 것을 vendor가 염두에 두고 있다.

물론 Arista는 “어떻게 host까지 가는지”를 상세히 공개하지는 않았습니다. 하지만 운영자가 해야 할 일은 “상세가 없으니 기다리자”가 아니라, host 침해 가정 하에 로그/포렌식 보존과 네트워크 egress 관측을 우선순위에 올리는 것입니다.[^1]

---

## 우선순위 1: web interface 노출면 축소(Internet에서 치우기)

Advisory 0199는 공격 성립 조건을 “VCO web interface에 대한 네트워크 접근”이라고 매우 노골적으로 적었습니다. 이 문장 하나로, 네트워크 팀이 당장 할 수 있는 방어의 80%가 결정됩니다.[^1]

여기서 말하는 노출면 축소는 단순히 “WAF 붙이자”가 아닙니다. 관리 plane의 접근 경로를 설계 수준에서 줄이는 게 핵심입니다.

### 1) 관리 plane 접속 경로를 한 군데로 접기

가장 현실적인 패턴은 아래 중 하나입니다.

- 사내 VPN(또는 ZTNA) → jump host → VCO web UI
- 사내 VPN(또는 ZTNA) → 내부 L7 proxy → VCO web UI

핵심은 “브라우저로 직접 VCO에 닿는 네트워크”가 관리망으로만 제한되게 만드는 것입니다. Arista도 mitigation 첫 줄이 “trusted administrative networks로 web interface 접근 제한”입니다.[^1]

이 단계에서 중요한 건 allowlist 사고방식입니다.

- 0.0.0.0/0에서 관리 UI를 볼 수 있는 상태는, 장기적으로는 결국 뚫립니다.
- ‘필요할 때만 열고 닫는다’는 운영은 사람 실수로 무너집니다.

### 2) Bastion Orchestrator로 공용/사설 Orchestrator 경계를 나누는 설계

VeloCloud 쪽 문서에는 Bastion Orchestrator(Public Orchestrator) 개념이 들어 있습니다. 문서가 말하는 취지는 명확합니다.

- Orchestrator가 고객과 네트워크에 대한 민감 정보를 저장/내보내며(API 포함), 이를 외부 공격으로부터 보호하고 API 접근을 제한하기 위해 Internet-facing DMZ에 Bastion Orchestrator를 둘 수 있다.
- 목적은 Edge의 staging/activation이다.[^4]

이건 이번 취약점 대응에서도 그대로 적용됩니다.

- Edge activation 같은 이유로 “외부에서 Orchestrator로 들어와야만 하는” 요구가 있다면, 그 요구를 Production Orchestrator가 직접 받게 두지 않는 쪽이 낫습니다.
- Public(DMZ)에는 기능이 제한된 Bastion, Private에는 Production을 두고, 둘 사이에 최소한의 연결만 허용하는 방식이 공격면을 줄입니다.

문서는 Bastion/Production 워크플로우를 분리하고, 제한사항도 적습니다. 예를 들어 Bastion 구성에서 stage할 수 있는 Operator Super user 계정은 1개이며, 이 계정은 emergency 용도로 Bastion 설정 페이지만 접근 가능한 식으로 설명돼 있습니다. 이런 제약은 불편하지만, 보안 관점에서는 의도적으로 blast radius를 줄이는 설계입니다.[^4]

추가로, 문서는 Bastion이 stateless이고 Production에서 지시를 받는다고 설명하면서 Bastion에는 DR을 지원하지 않는다고도 밝힙니다. DMZ에 놓는 시스템이 ‘상태를 덜 갖는’ 방향인 것도 방어에 유리합니다.[^4]

### 3) reverse proxy/NGINX 앞단의 오해: “앞에 하나 더 둔다고 해결되진 않는다”

Arista Orchestrator 문서에는 Portal 프로세스가 “NGINX downstream의 internal HTTP server”로 동작한다고 적혀 있습니다. 즉, 제품 자체가 이미 NGINX 계층을 갖고 있고, 그 뒤에 Portal이 있습니다.[^3]

여기서 흔히 나오는 오해는 이겁니다.

- “그럼 NGINX 앞에 또 NGINX/WAF를 붙이면 안전해지지 않나?”

앞단 proxy는 도움이 됩니다. 다만 ‘취약점이 SQLi’이고, 게다가 vendor가 “설정으로 노출을 막는 방법은 없다”고까지 말하는 상황에서는, 앞단 proxy가 취약점을 없애주지 않습니다. 앞단 proxy가 줄일 수 있는 건 대략 아래입니다.

- 접근 주체를 강하게 제한(allowlist, VPN 종단)
- rate limit / anomaly 기반 차단(특히 짧은 시간 burst)
- 표준 로그 통합(탐지 효율)

즉, proxy는 완화책이고 본질 대응은 patch입니다.

### 4) egress 통제는 ‘사후 방어’가 아니라 ‘침해 가정 방어’다

Arista는 defense-in-depth 목록에 “unexpected outbound network activity 모니터링”, “필요 없는 outbound 포트 차단 고려”를 넣었습니다. 이 문장은 오케스트레이터가 뚫렸을 때, 공격자가 외부 C2로 나가거나 데이터 유출을 시도할 가능성을 vendor도 전제하고 있다는 뜻입니다.[^1]

내 경우 SD-WAN Orchestrator 같은 관리 plane 서버는 egress를 기본 deny로 놓기 어렵더라도, 최소한 이 원칙을 잡습니다.

- 제품 문서상 필요한 외부 목적지(업데이트, 인증, SMS, GeoIP 등)가 뭐든 간에, 그 외의 outbound는 관측 가능해야 하고, 차단은 단계적으로 가능해야 한다.

(Arista 문서에도 외부 서비스 연동 예시가 꽤 많이 등장합니다. 운영 환경마다 egress 요구는 달라질 수 있습니다. 그래서 일괄 deny를 조언하기보다는 “관측 → 축소” 순서가 맞습니다.)[^3]

### 5) 방화벽 정책 예시(nftables): ‘관리 UI는 관리망만’

아래는 Linux 기반 환경에서 흔히 쓰는 nftables 예시입니다. 실제 포트/프로토콜은 환경에 맞게 조정해야 하고, 핵심은 ‘UI 포트는 관리망 allowlist’입니다.

```bash
# Ubuntu 24.04 기준 예시
sudo apt-get update
sudo apt-get install -y nftables

# /etc/nftables.conf (예시)
cat <<'EOF' | sudo tee /etc/nftables.conf
flush ruleset

table inet filter {
  set admin_nets {
    type ipv4_addr
    flags interval
    elements = { 10.10.0.0/16, 192.168.100.0/24 }
  }

  chain input {
    type filter hook input priority 0;
    policy drop;

    iif lo accept

    # established/related
    ct state established,related accept

    # SSH (관리망만)
    tcp dport 22 ip saddr @admin_nets accept

    # VCO Web UI / API (관리망만)
    tcp dport 443 ip saddr @admin_nets accept

    # ICMP는 운영 정책에 맞게
    ip protocol icmp accept

    # 나머지는 드랍
  }
}
EOF

sudo systemctl enable --now nftables
sudo nft -f /etc/nftables.conf
sudo nft list ruleset
```

이 정책의 의도는 단순합니다.

- 취약점이 무엇이든, 관리 plane UI/API가 인터넷에 열려 있는 한 스캐닝/브루트포스/계정탈취의 압력을 계속 받습니다.
- 반대로 UI를 관리망으로 접으면, 취약점 악용은 ‘관리망 침해’라는 더 큰 선행 조건을 요구하게 됩니다.

그리고 이번 건은 Arista가 공격 성립 조건으로 “web interface 네트워크 접근”을 직접 적었기 때문에, 이 통제가 특히 직접적인 효과를 냅니다.[^1]

---

## 우선순위 2: 로그 기반 탐지(이미 들어왔는지 먼저 확인)

패치가 최우선이지만, “활발 악용”이 걸린 시점에서는 패치만으로 끝내면 운영 리스크가 남습니다. 이미 침해됐는지 확인하지 않으면, 고쳐도 공격자가 남긴 계정/지속성 때문에 다시 터질 수 있습니다.

Advisory 0199는 IoC 섹션에서 굉장히 구체적인 가이드를 줍니다.

- VCO web access log를 보라.
- unusual URL-like path components, encoded characters, local/internal service reference, high request rate를 조사하라.
- 공격에 관측된 IP 2개를 차단하고, 로그에 있었는지 확인하라.
- 침해가 의심되면 remediation 전에 web access log / backend app log / system log / database log / filesystem timestamp를 보존하라.[^1]

이 섹션이 좋은 이유는, vendor가 취약점 세부를 공개하지 않아도 탐지 관측점을 제공한다는 점입니다.

### 1) Arista가 공개한 관측 공격 IP

Advisory 0199에 실린 공격 IP는 아래 2개입니다.

- **74.82.197.86 / 38.54.50.151**

이 2개는 “이 IP가 보이면 100% 침해” 같은 단정의 근거가 되진 않습니다. 다만 triage에서는 매우 쓸모가 있습니다.

- 이 IP가 내 VCO access log에 있으면, 최소한 사건 대응 티켓은 즉시 P1로 격상하는 편이 맞습니다.
- 이 IP가 없다고 해서 안전한 것도 아닙니다. 공격자가 더 많을 수 있기 때문입니다.

하지만 ‘활발 악용’ + ‘관측 IP 제공’ 조합은, 로그 확인의 ROI가 높다는 뜻입니다.[^1]

### 2) access log에서 보는 신호: 패턴 기반 + 속도 기반

Advisory 0199가 제시한 힌트는 2종류입니다.

- 패턴 기반
  - encoded characters(특히 과한 percent-encoding)
  - local/internal 서비스 참조
  - URL path가 정상 UI 동작에서 보기 힘든 모양
- 속도 기반
  - high request rates

SQLi라고 해서 꼭 `' OR 1=1` 같은 교과서 문자열이 찍히는 건 아닙니다. 오히려 실제 공격 트래픽은 제품 내부 경로를 찌르기 위해 path/encoding이 비정상인 경우가 많고, 공격자 자동화는 request rate를 밀어 올립니다.

### 3) 실제로 돌려서 쓰는 로그 스캐너(Python 3.11)

VCO가 어떤 포맷으로 access log를 남기는지는 배치마다 다를 수 있습니다(내장 NGINX, 외부 LB/proxy 등). 그래서 아래 코드는 NGINX combined log 형식을 기본 가정으로 하고, 파싱에 실패하면 “원문 라인 그대로”라도 의심 신호를 찾게 만들었습니다.

- 의존성: Python 표준 라이브러리만 사용
- 입력: access.log
- 출력: 의심 라인과 간단한 요약

```bash
python3 --version
# Python 3.11+ 권장

cat > vco_access_triage.py <<'PY'
import re
import sys
from collections import defaultdict, deque
from datetime import datetime

# NGINX combined log 대략 형태:
# 1.2.3.4 - - [25/Oct/2026:12:34:56 +0900] "POST /path HTTP/1.1" 200 123 "-" "UA"
LOG_RE = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<ts>[^\]]+)\]\s+'
    r'"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+(?P<proto>[^"]+)"\s+'
    r'(?P<status>\d{3})\s+(?P<size>\S+)\s+"(?P<ref>[^"]*)"\s+"(?P<ua>[^"]*)"'
)

# Arista Advisory 0199에서 제공한 관측 공격 IP
ARISTA_OBSERVED_IPS = {"74.82.197.86", "38.54.50.151"}

SUSPICIOUS_SUBSTRINGS = [
    "%2f", "%2F", "%5c", "%5C",  # /, \\ 인코딩
    "%252f", "%255c",              # 이중 인코딩 흔적
    "..%2f", "..%2F", "../", "..\\",  # traversal
    "localhost", "127.0.0.1", "::1",
    "169.254.",  # link-local
    "http://", "https://",
]

# 너무 단정적인 SQLi 키워드는 오탐이 많아서 '가중치'로만 처리
SQLI_HINTS = ["'", '"', "--", "/*", "*/", ";", " or ", " and ", " union ", " select ", " information_schema "]

# request rate: 60초 window 내 120회 초과면 의심(환경에 맞게 조정)
WINDOW_SECS = 60
RATE_THRESHOLD = 120

# ts 파싱: [25/Oct/2026:12:34:56 +0900]
def parse_ts(ts: str):
    # timezone offset은 여기서는 버리고 naive로 처리
    # 포렌식용으로는 원문 보존이 더 중요
    return datetime.strptime(ts.split()[0], "%d/%b/%Y:%H:%M:%S")

def score_path(path: str):
    p = path.lower()
    score = 0
    reasons = []

    for s in SUSPICIOUS_SUBSTRINGS:
        if s.lower() in p:
            score += 3
            reasons.append(f"substr:{s}")

    # percent-encoding 비율이 과도하면 가중치
    pct = p.count("%")
    if pct >= 6:
        score += 2
        reasons.append("many-percent")

    # SQLi 힌트: 단독으론 약하므로 가중치 낮게
    hint_hits = 0
    for h in SQLI_HINTS:
        if h in p:
            hint_hits += 1
    if hint_hits >= 3:
        score += 2
        reasons.append(f"sqli-hints:{hint_hits}")

    return score, reasons

def main():
    if len(sys.argv) != 2:
        print("usage: python3 vco_access_triage.py /path/to/access.log", file=sys.stderr)
        sys.exit(2)

    path = sys.argv[1]

    # IP별 요청 시각 window
    windows = defaultdict(deque)  # ip -> deque[datetime]

    suspicious = []
    totals = 0
    parse_fail = 0

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            totals += 1

            m = LOG_RE.match(line)
            if not m:
                parse_fail += 1
                # 파싱 실패 라인에서도 힌트만 탐지
                lower = line.lower()
                if any(s.lower() in lower for s in SUSPICIOUS_SUBSTRINGS):
                    suspicious.append(("?", "?", "?", 5, ["unparsed-but-has-suspicious-substr"], line))
                continue

            ip = m.group("ip")
            ts_raw = m.group("ts")
            method = m.group("method")
            req_path = m.group("path")
            status = m.group("status")

            try:
                ts = parse_ts(ts_raw)
            except Exception:
                ts = None

            score, reasons = score_path(req_path)

            # Arista 관측 IP는 바로 가중치
            if ip in ARISTA_OBSERVED_IPS:
                score += 6
                reasons.append("arista-observed-ip")

            # request rate 의심
            if ts is not None:
                dq = windows[ip]
                dq.append(ts)
                cutoff = ts.timestamp() - WINDOW_SECS
                while dq and dq[0].timestamp() < cutoff:
                    dq.popleft()
                if len(dq) >= RATE_THRESHOLD:
                    score += 4
                    reasons.append(f"high-rate:{len(dq)}/{WINDOW_SECS}s")

            if score >= 6:
                suspicious.append((ip, ts_raw, f"{method} {req_path}", score, reasons, line))

    suspicious.sort(key=lambda x: x[3], reverse=True)

    print(f"total_lines={totals} parse_fail={parse_fail} suspicious={len(suspicious)}")
    print("top suspicious lines:")

    for ip, ts_raw, req, score, reasons, raw in suspicious[:50]:
        print("-")
        print(f"  ip: {ip}")
        print(f"  ts: {ts_raw}")
        print(f"  req: {req}")
        print(f"  score: {score}")
        print(f"  reasons: {', '.join(reasons)}")
        print(f"  raw: {raw}")

if __name__ == "__main__":
    main()
PY

python3 vco_access_triage.py ./access.log
```

예상 출력 형태는 다음과 같습니다(샘플).

```text
total_lines=182934 parse_fail=0 suspicious=3
top suspicious lines:
-
  ip: 74.82.197.86
  ts: 25/Oct/2026:03:12:01 +0900
  req: POST /...%252f... HTTP/1.1
  score: 14
  reasons: substr:%252f, many-percent, arista-observed-ip
  raw: 74.82.197.86 - - [25/Oct/2026:03:12:01 +0900] "POST /...%252f... HTTP/1.1" 200 123 "-" "Mozilla/5.0"
```

이 스크립트는 “침해 여부 판정기”가 아닙니다. triage를 자동화해 사람이 봐야 할 로그의 양을 줄이는 도구입니다. vendor가 말한 힌트(encoding/path/internal reference/high rate)를 그대로 점수화했고, 관측 IP 2개는 우선순위만 올려 둔 형태입니다.[^1]

### 4) 로그 보존: patch 전에 할 일도 있다

침해가 의심되면 “고치기 전에” 보존해야 하는 로그가 있습니다. Arista는 web access log, backend application log, system log, database log, 파일시스템 timestamp까지 구체적으로 나열합니다. 내가 좋아하는 문장입니다. vendor가 ‘증거를 남기라’고 직접 말하는 건 흔치 않습니다.[^1]

운영적으로는 다음 리스크 때문에 선보존이 필요합니다.

- 업그레이드/재시작 과정에서 volatile 로그가 날아갈 수 있습니다.
- 공격자가 이미 webshell/백도어를 심었다면, patch 후에도 흔적은 남습니다. 다만 시간 정보가 바뀌면 조사 난도가 올라갑니다.

---

## 패치 우선순위: 버전 고정이 명확할 때는 ‘지금’이 답이다

이번 건은 “패치 고정 버전이 명확하다”는 점에서 대응 가치가 큽니다.

- fixed: 5.2.3.18 / 6.1.3.10 / 6.4.2.12[^1]

Arista는 해결책을 “가능한 한 빨리 fixed release로 업그레이드”라고만 단순하게 말합니다. 그리고 지원되지 않는 release train이면 TAC에 연락해서 업그레이드 옵션을 논의하라고 합니다.[^1]

여기서 실무적으로는 다음과 같이 정리하는 편이 맞습니다.

1) 인터넷/광역망에서 VCO web interface로 접근 가능한지부터 확인
- Arista 표현 그대로 “성공 공격은 web interface 네트워크 접근을 요구”합니다. 그게 된다면, 지금 이 순간에도 공격 표면이 열려 있는 셈입니다.[^1]

2) 버전 확인 후 즉시 업그레이드 창을 잡기
- 버전이 영향 범위면, 우선순위를 바꿀 이유가 없습니다.

3) 업그레이드 전/후로 최소한의 침해 징후 확인
- 관측 IP가 있는지, access log에서 encoding/path 이상이 있는지.

4) 업그레이드가 바로 안 되면 defense-in-depth를 ‘체크리스트’로 실행
- Arista가 제시한 항목은 하나씩 그대로 실행 가능한 작업입니다(관리망 제한, 악성 IP 모니터링, outbound 관측/차단 검토, webshell/daemon 모니터링, 관리자 활동 리뷰).[^1]

또 하나의 사실: Hosted(전용 포함) VCO는 영향을 받았지만 이미 패치됐다고 공지에 적혀 있습니다. on-prem 운영자가 상대적으로 더 위험한 구간에 남는 구조입니다.[^1]

---

## 반론과 회의론: “인증 필요면 CVSS가 과한 것 아닌가?”

실제 현장에서 가장 많이 나오는 반론은 이겁니다.

- “인증이 필요한데 CVSS 9.9가 맞나?”

나는 CVSS 점수 자체를 논쟁할 필요가 없다고 봅니다. vendor가 이 사건에서 이미 중요한 사실을 다 깔아줬습니다.

- actively exploited
- 최소 권한(Enterprise Read Only)으로 operator privilege 획득
- 내부 기능 접근 + host impact

즉, 이 취약점은 “인증 필요”라는 단점(공격 난이도 증가)을 “권한 상승 + 관리 plane 장악”으로 상쇄하고 남습니다.[^1]

또 다른 회의론도 있습니다.

- “우린 관리 UI를 인터넷에 안 열어뒀다.”

이 경우에도 끝이 아닙니다. Arista가 말한 성공 조건은 “네트워크 접근 + 인증 세션”입니다. 인터넷이 아니라 사내망에서 노려도 조건은 충족됩니다. SD-WAN 운영 환경에서는 지사/협력사/운영 대행/관제망 등 네트워크 경계가 단순하지 않은 경우가 흔합니다. 관리 UI를 관리망으로 접는 것은 기본이고, 그 관리망 자체가 공격 경계임을 다시 설계해야 합니다.

마지막으로 가장 위험한 오해는 이겁니다.

- “제품 설정으로 어느 정도 막을 수 있지 않을까?”

Advisory 0199는 “There is no configuration that can prevent the exposure”라고 말합니다. 설정 knob로 우회하는 순간, 대응은 늦어집니다. 이번 건은 upgrade가 답입니다.[^1]

---

## 앞으로 지켜볼 것: 추가 IoC, 침해 후 행동, 그리고 재발 패턴

Advisory 0199는 revision 1.0(초기 공개)이고, IoC도 IP 2개와 로그 관측 포인트 정도만 제공합니다.[^1]

앞으로 더 나올 수 있는(그리고 운영팀이 기다려야 하는) 정보는 보통 이런 것들입니다.

- 더 넓은 IoC: URL path 패턴, User-Agent, 세션/파라미터 형태
- 침해 후 행동: 계정 생성/권한 변경 흔적, 설정 변경 흔적, 특정 기능 호출 흔적
- host impact의 구체화: webshell 위치, 프로세스/서비스 이름, 파일 해시

다만 이런 정보는 늦게 나오거나 끝까지 공개되지 않을 수도 있습니다. 그래서 나는 “추가 정보 기다리기”를 대응 플랜에 넣지 않고, 이미 나온 사실만으로 우선순위를 정합니다.

- 관리 UI 노출면을 접는다.
- 로그에서 이상을 찾는다.
- 고정 버전으로 올린다.

관리 plane 보안은 결국 trust boundary 설계 문제로 귀결됩니다. 예전에 LLM guardrail 글에서 trust boundary를 설계하지 않으면 기술로 막을 수 없다고 썼는데, 관리 UI도 똑같습니다.

- [프롬프트 인젝션은 신뢰 경계를 설계하는 문제다: LLM Guardrail 심층 분석](https://daewooki.github.io/posts/trust-boundary-2026-6-llm-guardrail-1/)

또, web/API 노출면을 줄이는 사고방식은 NGINX Control API/njs 리스크를 다룰 때와 같은 결입니다. “기능을 끄는 것”보다 “누가 어디서 접근할 수 있는지”가 먼저입니다.

- [NGINX 1.31.5: Control API와 njs 리스크가 만나는 지점](https://daewooki.github.io/posts/nginx-control-api-njs-security/)

---

## 정리: **노출면 축소 + 로그 기반 탐지**가 먼저다

CVE-2026-114625는 SQL injection이라는 라벨보다, “최저 권한 인증 사용자 → operator privilege → 내부 기능 접근 → host impact 가능”이라는 형태가 본질입니다. 오케스트레이터 계층은 SD-WAN에서 관리 plane의 권한과 데이터를 한 곳에 모으기 때문에, 이 체인이 완성되면 네트워크 운영권 자체가 넘어갈 수 있습니다.[^1]

이번 Arista Advisory 0199는 대응 방향도 같이 줍니다.

- web interface 접근을 trusted administrative networks로 제한
- access log 기반으로 encoding/path/internal reference/high rate를 조사
- 관측 IP 2개 차단/로그 확인
- 필요하면 로그/타임스탬프를 보존한 뒤 remediation[^1]

패치 고정 버전이 분명하니(5.2.3.18/6.1.3.10/6.4.2.12), 더 복잡한 판단을 할 이유가 없습니다. 네트워크 관점에서는 관리 plane의 노출면을 먼저 접고, 보안 관점에서는 로그로 이미 들어왔는지부터 확인하는 순서가 맞습니다.

---

## 참고 자료

- [Arista Security Advisory 0199](https://www.arista.com/en/support/advisories-notices/security-advisory/24838-security-advisory-0199)
- [Canadian Centre for Cyber Security AV26-1080 Update 1](https://www.cyber.gc.ca/en/alerts-advisories/arista-networks-security-advisory-av26-1080)
- [CVE Record: CVE-2026-114625](https://www.cve.org/CVERecord?id=CVE-2026-114625)
- [VeloCloud SD-WAN Bastion Orchestrator Configuration Guide (Version 5.2)](https://www.arista.com/assets/data/pdf/qsg/VC-SD-WAN-5.2-Configuration-Guide.pdf)
- [VeloCloud Orchestrator Deployment and Monitoring Guide (SD-WAN 7.0)](https://www.arista.com/en/orchestrator-guide-vc-7-0/sd-wan-7-0-velocloud-orchestrator-deployment-and-monitoring-guide)

[^1]: <https://www.arista.com/en/support/advisories-notices/security-advisory/24838-security-advisory-0199>
[^2]: <https://www.cyber.gc.ca/en/alerts-advisories/arista-networks-security-advisory-av26-1080>
[^3]: <https://www.arista.com/en/orchestrator-guide-vc-7-0/sd-wan-7-0-velocloud-orchestrator-deployment-and-monitoring-guide>
[^4]: <https://www.arista.com/assets/data/pdf/qsg/VC-SD-WAN-5.2-Configuration-Guide.pdf>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
