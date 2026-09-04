---
title: "LLM RAG Agent 구현 튜토리얼: “검색”을 도구로 쓰는 Agentic RAG 아키텍처 완전 정복"
description: "2023~2024년의 RAG는 “질문 → retrieve(top-k) → LLM 답변”으로 끝나는 단일 패스가 주류였습니다. 그런데 2025년 실무에서는 이 구조가 자주 깨집니다."
date: 2025-12-26 02:11:48 +0900
categories: [AI, Tutorial]
tags: [ai, tutorial]
render_with_liquid: false
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
2023~2024년의 RAG는 “질문 → retrieve(top-k) → LLM 답변”으로 끝나는 단일 패스가 주류였습니다. 그런데 2025년 실무에서는 이 구조가 자주 깨집니다. 사용자가 던지는 질문이 **복합적**(여러 하위 질문), **불완전**(용어가 애매/오타), **데이터 범위가 불명확**(내부 문서에 없는 것)하기 때문입니다.  
그래서 최신 튜토리얼/프레임워크 흐름은 RAG를 “파이프라인”이 아니라 **Agent가 필요할 때 Retrieval을 ‘도구(tool)’로 호출하는 방식(Agentic RAG)**으로 옮겨가고 있습니다. Haystack은 RAG 결과가 부족하면 **조건부 라우팅으로 web search fallback**을 붙이는 형태를 “agentic behavior”로 설명하고, LlamaIndex는 Agent 프레임워크/Workflows로 Agentic RAG를 확장하는 방향을 강조합니다.[^1]

---

## 🔧 핵심 개념
### 1) Agentic RAG란?
**Agentic RAG = LLM이 (1)계획/판단을 하고 (2)필요 시 Tool을 호출해서 (3)증거 기반으로 답을 합성**하는 패턴입니다. 여기서 Tool은 보통 `retriever`, `reranker`, `web_search`, `db_query`, `calculator` 같은 것들입니다. LlamaIndex 문서도 agent를 “자동화된 reasoning/decision engine”으로 정의하며, tool 선택/파라미터 생성/플래닝/메모리 등을 핵심 구성요소로 봅니다.[^2]

### 2) 왜 “단일 RAG”가 아니라 “도구 호출 RAG”가 필요한가?
단일 RAG는 실패 시 복구 루트가 없습니다. 반면 Agentic RAG는 다음을 할 수 있습니다.

- **Self-check & fallback**: 내부 문서로 답이 안 나오면 “NO_ANSWER” 같은 신호를 내고 web search로 전환(조건부 라우팅)[^1]  
- **Multi-step retrieval**: “하위 질문 분해 → 각 질문별 검색 → 병합 요약”
- **Multi-agent 확장**: 문서군/도메인별 “서브 에이전트”를 두고 상위 에이전트가 필요한 서브 에이전트를 선택(오케스트레이션)[^3]

### 3) 2025년 구현 포인트(실전에서 갈리는 지점)
- **Routing**: “내부 RAG로 충분한가?”를 판단하는 게 핵심. Haystack 예시는 LLM이 답을 못 만들면 `NO_ANSWER`를 내도록 프롬프트를 바꾸고, `ConditionalRouter`로 web search 브랜치를 태웁니다.[^1]  
- **Rerank & evidence discipline**: Agent가 여러 번 검색하면 “그럴듯한 조합”이 나오기 쉬워서, 각 스텝에서 **근거 문서와 인용(citation)**을 강제하는 프롬프트/출력 스키마가 중요합니다.
- **Memory는 최소부터**: 세션 메모리를 과하게 넣으면 “이전 대화의 착각”이 Retrieval 근거를 오염시킵니다. 먼저 stateless에 가깝게 만들고 점진적으로 확장하는 편이 안전합니다.

---

## 💻 실전 코드
아래 예제는 **(1)로컬 문서 RAG → (2)부족하면 web search fallback → (3)최종 답변 합성**을 “Agentic Routing” 관점으로 구현한 최소 실행 코드입니다.  
프레임워크는 개념을 잘 드러내기 위해 Haystack(파이프라인/라우팅) 스타일로 구성했습니다. Haystack이 조건부 라우팅으로 agentic fallback을 구성하는 방식은 2025년 튜토리얼에서 명확히 제시됩니다.[^1]

```python
# requirements (예시)
# pip install haystack-ai haystack-integrations
# export OPENAI_API_KEY=...
# export SERPERDEV_API_KEY=...  # web search를 쓴다면

from haystack import Pipeline
from haystack.components.generators import OpenAIGenerator
from haystack.components.builders import PromptBuilder
from haystack.components.routers import ConditionalRouter

# 문서 검색(내부 RAG)용 컴포넌트들은 프로젝트마다 다릅니다.
# 여기서는 "retriever가 documents를 준다"는 전제만 두고 최소 형태로 보여줍니다.
# 실제로는 InMemoryDocumentStore/Elasticsearch/Weaviate + Retriever/BM25/EmbeddingRetriever 등을 연결하세요.

from haystack.dataclasses import Document

class DummyRetriever:
    """
    데모용: 내부 문서에서 찾았다고 가정하고 documents를 반환.
    실제로는 Vector DB + Retriever로 대체하세요.
    """
    def run(self, query: str):
        docs = [
            Document(content="RAG는 Retrieval Augmented Generation의 약자이며, 검색 결과를 근거로 답한다."),
            Document(content="Agentic RAG는 LLM이 필요 시 tool을 호출하여 multi-step으로 검색/판단한다.")
        ]
        return {"documents": docs}

# (선택) 웹 검색 컴포넌트: Haystack에는 SerperDevWebSearch 같은 통합 컴포넌트가 있습니다.
# 튜토리얼에서도 web search fallback을 동일한 아이디어로 구성합니다.[^1]
class DummyWebSearch:
    def run(self, query: str):
        web_docs = [
            Document(content=f"[WEB] {query} 관련 최신 글에서 요약된 내용(데모).")
        ]
        return {"documents": web_docs}

# 1) 내부 RAG 답변: 못 찾으면 "NO_ANSWER"를 출력하도록 강제
internal_prompt = PromptBuilder(
    template=
"""You are a technical expert.
Answer ONLY using the provided documents.
If the documents cannot answer the question, output exactly: NO_ANSWER

Documents:
{% for d in documents %}
- {{ d.content }}
{% endfor %}

Question: {{ question }}
Answer:"""
)

internal_llm = OpenAIGenerator(model="gpt-4o")  # 예시

# 2) 라우팅: NO_ANSWER면 web search로, 아니면 종료
router = ConditionalRouter(
    routes=[
        {
            "condition": "{{ 'NO_ANSWER' in replies[0] }}",
            "output": "{{question}}",
            "output_name": "go_to_web",
            "output_type": str,
        },
        {
            "condition": "{{ 'NO_ANSWER' not in replies[0] }}",
            "output": "{{ replies[0] }}",
            "output_name": "final_answer",
            "output_type": str,
        },
    ]
)

# 3) 웹 검색 브랜치에서 최종 답 합성
web_prompt = PromptBuilder(
    template=
"""You are a technical expert.
Use the web documents to answer. Mention that it was derived from web search.
Keep it precise.

Web Documents:
{% for d in documents %}
- {{ d.content }}
{% endfor %}

Question: {{ question }}
Answer:"""
)
web_llm = OpenAIGenerator(model="gpt-4o")

# 파이프라인 구성
pipe = Pipeline()
pipe.add_component("retriever", DummyRetriever())
pipe.add_component("internal_prompt", internal_prompt)
pipe.add_component("internal_llm", internal_llm)
pipe.add_component("router", router)

pipe.add_component("web_search", DummyWebSearch())
pipe.add_component("web_prompt", web_prompt)
pipe.add_component("web_llm", web_llm)

# 내부 RAG 흐름
pipe.connect("retriever.documents", "internal_prompt.documents")
pipe.connect("internal_prompt.prompt", "internal_llm.prompt")
pipe.connect("internal_llm.replies", "router.replies")

# web fallback 흐름
pipe.connect("router.go_to_web", "web_search.query")
pipe.connect("web_search.documents", "web_prompt.documents")
pipe.connect("router.go_to_web", "web_prompt.question")
pipe.connect("web_prompt.prompt", "web_llm.prompt")

# 실행
result = pipe.run(data={"retriever": {"query": "Agentic RAG가 뭐야?"}, "internal_prompt": {"question": "Agentic RAG가 뭐야?"}})
print(result)
```

핵심은 “Agent(혹은 LLM)가 실패를 명시하는 출력(예: `NO_ANSWER`)을 하게 만들고 → 라우터가 다음 tool을 호출”하는 구조입니다. Haystack의 Agentic RAG 예제가 사실상 이 패턴을 가장 명료하게 보여줍니다.[^1]

---

## ⚡ 실전 팁
- **프롬프트에 ‘근거 강제’ 규칙을 넣어라**: “주어진 documents 외 사용 금지”, “모르면 NO_ANSWER” 같은 규칙이 라우팅 품질을 결정합니다. (라우팅이 흔들리면 Agent 전체가 흔들립니다)[^1]
- **Retriever를 Tool로 만들 때는 ‘입력/출력 스키마’를 고정**: `{query, filters, top_k}` 같은 입력과 `{documents: [ {content, meta, score} ]}` 같은 출력을 고정하면, Agent가 여러 tool을 오케스트레이션해도 디버깅이 가능합니다.
- **멀티 에이전트는 “확장 전략”이지 “기본값”이 아니다**: LlamaIndex가 소개하는 문서별 sub-agent + 상위 agent 구조는 대규모/다도메인에서 강력하지만, 운영 복잡도도 같이 증가합니다. 먼저 단일 agent + routing부터 안정화하세요.[^3]
- **관측(Observability) 없이는 운영 불가**: 최소한 “각 단계에서 어떤 문서가 선택됐는지, 왜 fallback 됐는지”를 로그로 남기세요. Agentic RAG는 성공/실패가 확률적이라 재현 가능한 추적이 생명입니다.

---

## 🚀 마무리
2025년의 RAG 구현에서 차이를 만드는 건 “벡터 DB를 붙였냐”가 아니라 **LLM이 Retrieval을 ‘필요할 때 호출하는 도구’로 다루도록 설계했느냐**입니다.  
오늘 글의 핵심은 세 가지입니다.

1) **NO_ANSWER 같은 실패 신호를 설계**하고  
2) **Conditional Routing으로 fallback tool(web search 등)을 호출**하며[^1]  
3) 규모가 커지면 **멀티 에이전트 오케스트레이션**으로 확장한다[^3]

다음 학습 추천은 (1) Router/Rerank/Hybrid retrieval 튜닝, (2) Agent 평가(Eval)와 회귀 테스트, (3) LlamaIndex Workflows 같은 이벤트 기반 오케스트레이션으로의 확장입니다.[^2]

[^1]: <https://haystack.deepset.ai/blog/agentic-rag-in-deepset-studio>
[^2]: <https://docs.llamaindex.ai/en/latest/use_cases/agents/>
[^3]: <https://www.llamaindex.ai/blog/agentic-rag-with-llamaindex-2721b8a49ff6>
