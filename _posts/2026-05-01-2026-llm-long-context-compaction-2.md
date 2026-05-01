---
title: "컨텍스트는 길어졌는데 정답은 왜 가운데서 사라질까? — 2026년 LLM Long Context Compaction 실전 설계서"
date: 2026-05-01 04:03:19 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-05]
---

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>

## 들어가며
2026년의 LLM은 “128k+ long context”가 더 이상 특별한 스펙이 아닙니다. 문제는 **컨텍스트를 많이 넣을수록 성능이 선형으로 좋아지지 않는다**는 점입니다. 오히려 입력이 길어지면 (1) 비용/지연이 커지고, (2) 중요한 단서가 프롬프트 “가운데”에 묻히는 **lost in the middle**로 정답률이 떨어지며, (3) 에이전트/코딩 세션처럼 턴이 길어질수록 품질이 급격히 무너집니다. ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))

이때 필요한 게 **compaction(문맥 압축)** 입니다. 목적은 단순 요약이 아니라, **다음 턴에서 모델이 실제로 ‘필요한 정보에’ 더 높은 확률로 접근하도록** 컨텍스트를 재구성하는 것입니다. OpenAI Responses API는 장기 대화에서 컨텍스트를 줄이기 위한 `/responses/compact`를 공식 가이드로 제공하고 있고(“long-running conversations → compact”), 에이전트 루프에서도 compaction이 핵심 최적화 축으로 언급됩니다. ([platform.openai.com](https://platform.openai.com/docs/guides/conversation-state?api-mode=responses&utm_source=openai))

**언제 쓰면 좋나**
- 30~200턴짜리 에이전트/코딩 세션(계획/의사결정/도구로그가 누적)
- RAG로 문서를 많이 붙이는데 “정답 근거가 중간에 묻혀” 누락되는 케이스
- 비용(입력 토큰)과 latency가 병목인 서비스

**언제 쓰면 안 되나**
- 법무/의료/감사 로그처럼 “원문 보존(Verbatim)”이 필수인 경우(요약 왜곡 리스크)
- 정답이 원문 특정 구절의 정확한 재현에 달린 경우(요약이 손실을 만든다)
- 컨텍스트가 짧고(수천 토큰) 현재도 정확도가 충분한 경우(복잡도만 증가)

---

## 🔧 핵심 개념
### 1) Compaction = “요약”이 아니라 “컨텍스트 재배치 + 정보 밀도 최적화”
단순 요약은 대개 **의도/근거/제약**을 섞어 뭉개고, “나중에 필요할지도 모르는 예외”를 잘라냅니다. 2026년에 실무에서 통하는 compaction은 보통 아래 3층 구조로 설계합니다.

- **Pinned(절대 보존)**: 시스템 규칙, 안전/정책, 프로젝트 불변 제약, API 계약, 스키마
- **Working set(최근 작업 기억)**: 최근 N턴의 대화/도구 결과(“지금 하고 있는 일”)
- **Compressed memory(압축 장기 기억)**: 오래된 턴을 “결정/근거/미해결/리스크/다음 액션” 형태로 구조화

이 구조를 쓰는 이유는 lost in the middle이 “길이”만의 문제가 아니라 **위치 편향(position bias)** 과 결합되기 때문입니다. 연구들은 긴 컨텍스트에서 중요한 정보가 **맨 앞/맨 끝에 있을 때 성능이 높고 중간에서 급락하는 U자 형태**를 반복적으로 관측합니다. ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))

즉, compaction의 본질은:
- 토큰 수 절감(비용/속도) +
- **중요 정보를 ‘끝단’이나 ‘질의 근접부’로 끌어올려** 접근 확률을 올리는 것

### 2) 접근 방식 비교: “압축”에도 계열이 있다
실무 관점에서 크게 3계열입니다.

1) **Rolling summarization(대화 요약 누적)**  
   가장 흔하지만, 잘못하면 “요약의 요약”이 되면서 드리프트가 생깁니다. 대신 구조화 템플릿(결정/근거/오픈이슈)을 강제하면 꽤 견고해집니다.

2) **Extractive / Selective compression(원문 일부를 선택적으로 남김)**  
   Selective Context는 입력에서 중복을 제거해 효율을 높이는 계열로 알려져 있고, LLMLingua-2는 prompt compression을 token classification으로 보고 “faithful(충실)”하게 줄이려는 방향입니다. ([arxiv.org](https://arxiv.org/abs/2310.06201?utm_source=openai))  
   장점: 사실 왜곡이 상대적으로 적음(“있는 문장 중에서 고름”)  
   단점: 길이가 충분히 줄지 않을 수 있고, “왜 중요한지” 메타정보가 부족

3) **RAG + Compression(검색 후 압축, RECOMP류)**  
   RECOMP는 retrieval된 문서를 그대로 붙이지 말고 “압축 + 선택적 증강”으로 컨텍스트 품질을 올리자는 계열입니다. ([arxiv.org](https://arxiv.org/abs/2310.04408?utm_source=openai))  
   장점: 문서가 많은 도메인에서 가장 비용 대비 효과가 큼  
   단점: 파이프라인 복잡도 상승(검색/랭킹/압축/검증)

### 3) 2026년 “API 레벨 compaction”의 의미
OpenAI는 Responses API에서 **stateful context**와 함께, 장기 세션을 줄이기 위한 `/responses/compact`를 문서화했습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/conversation-state?api-mode=responses&utm_source=openai))  
여기서 포인트는 “클라이언트가 직접 요약 프롬프트를 굴리는 것” 대비:
- 모델/릴리즈에 맞춰 compaction 품질이 진화할 수 있고 ([openai.com](https://openai.com/index/equip-responses-api-computer-environment?utm_source=openai))
- 에이전트 루프에서 latency/토큰을 운영 관점으로 다루기 쉬워진다는 점입니다

---

## 💻 실전 코드
아래는 “고객 지원 티켓 + 엔지니어링 에이전트”를 가정한 예시입니다.

- 매 턴: 티켓 업데이트 + 로그/에러 + 사용자가 추가 질문
- 20~50턴 넘어가면 품질이 흔들리고 비용이 급증
- 목표: **오래된 대화는 구조화 memory로 접고**, 최신 작업은 유지하면서, **질의에 필요한 핵심 근거를 끝단에 고정**  

### 0) 의존성/환경
```bash
pip install openai==1.* tiktoken
export OPENAI_API_KEY="..."
```

### 1) “세션 아이템”을 누적하고, 임계치에서 `/responses/compact` 실행
```python
from openai import OpenAI
import tiktoken
from typing import List, Dict, Any

client = OpenAI()

MODEL = "gpt-5"  # 예시: 실제 사용 가능 모델로 교체

enc = tiktoken.get_encoding("o200k_base")

def approx_tokens(items: List[Dict[str, Any]]) -> int:
    # 러프 추정: text만 센다(실전에서는 item type별로 더 정확히)
    total = 0
    for it in items:
        if it.get("type") == "input_text":
            total += len(enc.encode(it.get("text", "")))
    return total

def compact_if_needed(previous_response_id: str, items: List[Dict[str, Any]], threshold_tokens=90_000):
    """
    전략:
    - Responses API state를 쓰는 경우: previous_response_id 체인을 유지
    - 임계치 도달 시: /responses/compact로 server-side compaction 수행
    """
    if approx_tokens(items) < threshold_tokens:
        return previous_response_id, items

    compacted = client.responses.compact(
        # 문서상 /responses/compact 엔드포인트
        previous_response_id=previous_response_id,
        # 압축 목표를 '대화 요약'이 아니라 '작업 메모리 재구성'으로 명시
        instructions=(
            "You are compacting a long-running engineering support session.\n"
            "Produce a compacted conversation state that preserves:\n"
            "1) Non-negotiable constraints (SLO, security, API contracts)\n"
            "2) Decisions made + rationale\n"
            "3) Open issues / next actions\n"
            "4) Key evidence (error codes, stack traces excerpts, configs) as short verbatim snippets\n"
            "Drop pleasantries and redundant back-and-forth.\n"
            "Format as structured bullets with headings: Pinned, Working Set, Memory.\n"
        ),
    )
    # compact 결과는 새로운 response_id/state를 갖는다(이후 체인에 사용)
    return compacted.id, []  # items는 비워도 됨: 이후는 previous_response_id로 이어감

def ask(previous_response_id: str, user_text: str):
    # 입력은 "최근 턴"만 items로 보내고, 과거는 previous_response_id로 이어간다
    resp = client.responses.create(
        model=MODEL,
        previous_response_id=previous_response_id,
        input=[
            {"type": "input_text", "text": user_text}
        ],
        # 출력 폭주 방지(비용/지연)
        max_output_tokens=800,
    )
    return resp.id, resp.output_text

# ---- 현실적 시나리오: 장애 분석 세션 ----
seed = client.responses.create(
    model=MODEL,
    input=[{"type": "input_text", "text": "You are a senior support engineer. We will troubleshoot incidents."}],
    max_output_tokens=200,
)

previous_id = seed.id
buffer_items: List[Dict[str, Any]] = []

# 턴 누적(예시)
turns = [
    "Incident: p95 latency spikes after deploying v2.3.1. SLO: p95 < 300ms. Region: us-east-1.",
    "Here is an excerpt from logs: ERROR pool timeout after 30s, db connections exhausted.",
    "Config diff: maxPoolSize changed 200->50; timeout 30s unchanged.",
    "Hypothesis? Provide next steps and what evidence to gather."
]

for t in turns:
    buffer_items.append({"type": "input_text", "text": t})
    previous_id, buffer_items = compact_if_needed(previous_id, buffer_items, threshold_tokens=2_000)  # 데모용 낮게
    # 질문은 buffer를 합쳐 한 번에 보내도 되고, 턴별로 보내도 됨
    joined = "\n\n".join([it["text"] for it in buffer_items if it["type"] == "input_text"])
    previous_id, out = ask(previous_id, joined)
    buffer_items = []
    print("\n---\n", out)
```

### 예상 출력(요지)
- 풀 사이즈 변경(200→50)이 병목 유발 가능
- DB connection exhaustion 근거 유지
- 다음 수집 증거: DB max connections, app concurrency, pool wait time metric, 배포 전후 트래픽 변화
- 롤백/핫픽스 기준

### 2) “lost in the middle” 대응: 중요한 근거를 끝단에 ‘증거 카드’로 재주입
Compaction만으로도 좋아지지만, 실제 장애/코드 리뷰는 “증거 조각”이 중간에 묻히기 쉽습니다. 그래서 compaction 결과(구조화 Memory)에서 **Evidence 카드만 따로 뽑아 매 턴 입력의 끝에 붙이는 패턴**이 효과적입니다(질의 근접 + 끝단 배치).

```python
def build_turn_input(question: str, evidence_cards: List[str]) -> str:
    cards = "\n".join([f"- {c}" for c in evidence_cards][-8:])  # 최근/중요 8개만
    return (
        f"{question}\n\n"
        "EVIDENCE (highest priority, do not ignore):\n"
        f"{cards}\n"
    )
```

이건 논문식 “정답률 곡선”을 몰라도, 현장에서 체감되는 패턴(중간 무시)을 직접 완화합니다. ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **Compaction 트리거는 “컨텍스트 한계”가 아니라 “품질 저하 지점”으로 잡기**  
   많은 팀이 128k 같은 하드 리밋 근처에서만 요약하는데, 실제로는 “길어지면 성능이 먼저 나빠진다”는 경험/가이드가 반복됩니다. 즉, 토큰이 남아도 compaction이 필요할 수 있습니다. ([morphllm.com](https://www.morphllm.com/prompt-compression?utm_source=openai))  
   실무적으로는 “최근 10턴에서 오답/반복/규칙 위반” 같은 신호를 트리거로 씁니다.

2) **요약은 자유서술이 아니라 ‘스키마’를 강제**  
   `Decisions[]`, `Constraints[]`, `OpenQuestions[]`, `Evidence[]`처럼 필드를 고정하면 드리프트가 줄고, 나중에 재주입/검증도 쉬워집니다.

3) **RAG를 쓰면 ‘검색 후 그대로 붙이기’ 대신 ‘압축 후 붙이기’를 기본값으로**  
   RECOMP류가 말하는 핵심은 “retrieved context의 품질”이 모델 정확도를 좌우한다는 점입니다. ([arxiv.org](https://arxiv.org/abs/2310.04408?utm_source=openai))  
   특히 중복 문단/서론/광고성 문구는 lost in the middle을 악화시키는 노이즈입니다.

### 흔한 함정/안티패턴
- **요약이 원문을 “대체”해버리는 설계**: 나중에 근거가 필요할 때 복구 불가  
  → 원문은 외부 저장소(Blob/DB)에 남기고, 컨텍스트에는 “주소 + 핵심 발췌 + 왜 중요한지”만 둡니다.
- **요약을 매 턴 수행**: 비용이 더 커지고, 누적 요약 오류가 쌓임  
  → 토큰/품질 신호 기반으로 배치 처리(예: 10턴마다, 또는 임계치 초과 시)
- **중요 제약을 요약본 ‘중간’에 넣기**: compaction 했는데도 다시 lost in the middle  
  → 제약/정책은 Pinned로 올리고, 매 턴 끝단에 짧게 재주입

### 비용/성능/안정성 트레이드오프
- **Extractive(선택) 압축**은 안정적이지만 압축률이 낮을 수 있음(비용 절감 한계)
- **Abstractive(요약) 압축**은 압축률이 높지만 사실 왜곡/누락 리스크
- **API-native compaction**은 운영이 쉬운 대신, “압축 결과의 형태/정확성”을 100% 통제하긴 어렵습니다(그래서 스키마 강제 + evidence 카드 재주입 같은 가드레일이 필요). ([openai.com](https://openai.com/index/equip-responses-api-computer-environment?utm_source=openai))

---

## 🚀 마무리
정리하면, 2026년 long context 활용의 승부처는 “얼마나 많이 넣나”가 아니라 **어떻게 접고(compact) 어디에 배치하나**입니다.

- lost in the middle은 여전히 유효하고(중간 성능 저하), ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))
- compaction은 비용 최적화 도구이면서 동시에 **정답률/안정성 최적화 도구**입니다.
- 도입 판단 기준은 간단합니다:
  1) 세션이 길어질수록 품질이 떨어지나?
  2) “중간에 있는 근거”를 자주 놓치나?
  3) 입력 토큰 비용/지연이 KPI를 압박하나?  
  → 하나라도 “예”면 compaction을 설계 단계에 넣을 가치가 큽니다.

다음 학습 추천(바로 실무에 도움되는 순서)
- OpenAI Responses API의 conversation state + `/responses/compact` 운용 패턴 ([platform.openai.com](https://platform.openai.com/docs/guides/conversation-state?api-mode=responses&utm_source=openai))
- Lost in the Middle 원 논문을 기준으로 “중요 정보의 위치/재주입” 실험하기 ([arxiv.org](https://arxiv.org/abs/2307.03172?utm_source=openai))
- LLMLingua-2 / Selective Context / RECOMP로 “요약 vs 추출 vs 검색+압축”을 케이스별로 A/B ([arxiv.org](https://arxiv.org/abs/2403.12968?utm_source=openai))

원하시면, 당신의 프로젝트 유형(RAG 기반 QA / 코딩 에이전트 / 고객지원 챗봇 / 데이터 분석 에이전트)에 맞춰 **compaction 스키마(필드 설계), 트리거 신호, 평가 지표(needle-in-haystack + 회귀 테스트)**까지 포함한 적용 체크리스트로 구체화해드릴게요.