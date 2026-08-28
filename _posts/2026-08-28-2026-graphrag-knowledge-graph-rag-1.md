---
title: "2026년형 GraphRAG 구현 가이드: Knowledge Graph로 “멀티홉 질문”을 깨끗하게 푸는 RAG 아키텍처"
date: 2026-08-28 11:03:15 +0900
categories: [AI, RAG]
tags: [ai, rag, trend, 2026-08]
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
Vector RAG를 실무에 붙여보면 금방 한계가 옵니다. “정답이 문서 여러 곳에 흩어져 있고, 그 사이의 관계를 따라가야 하는 질문”에서요. 예를 들어 **“A 서비스 장애가 났을 때 영향을 받는 고객군은 누구고, 그 고객들의 계약 조항 중 SLA 예외는 뭐야?”** 같은 질문은, chunk top-k만으로는 관계(고객↔계약↔서비스↔장애)를 못 타서 컨텍스트가 산개하거나 누락됩니다.

GraphRAG는 여기서 **텍스트를 (entity, relation)로 구조화해 Knowledge Graph를 만들고**, 질의 시에는 **벡터 유사도 + 그래프 traversal**로 “관계 있는 근거”를 모아서 LLM에 넣는 패턴입니다. Microsoft의 오픈소스 GraphRAG는 “문서→그래프 추출→커뮤니티 요약→local/global retrieval” 흐름을 파이프라인으로 제공하지만, 현재는 **maintenance mode**라서(기능 추가보단 CVE/의존성 업데이트 중심) “그대로 프로덕션 채택”보단 “패턴/설계 참고 후 내 스택에 맞게 구현”이 현실적입니다. ([github.com](https://github.com/microsoft/graphrag?utm_source=openai))

**언제 쓰면 좋나**
- 질문이 **multi-hop**(두 단계 이상 관계 추론)이고, **엔티티 중심**(사람/조직/시스템/계약/계정/자산 등)이며,
- “왜 그 답이 맞는지”를 **관계 기반으로 설명**해야 하고(감사/컴플라이언스/보안/금융),
- 문서가 자주 변하거나(재임베딩 비용 문제), “관계” 자체가 제품 가치인 경우

**언제 쓰면 안 되나**
- 단순 FAQ/매뉴얼 검색처럼 “한 덩어리 chunk에 답이 대부분 들어있는” 문제
- 그래프 스키마 합의/운영(정규화, ID, 중복 제거)을 감당할 팀/시간이 없을 때
- Graph extraction 비용(LLM 호출)과 품질(오추출)을 관리할 예산/관측이 없을 때  
GraphRAG 인덱싱은 비용이 클 수 있다는 경고가 공식 문서에도 반복됩니다. ([github.com](https://github.com/microsoft/graphrag?utm_source=openai))

---

## 🔧 핵심 개념
### 1) 주요 개념 정의
- **Entity**: 그래프의 node. “Customer”, “Service”, “Incident”, “Contract” 같은 도메인 객체.
- **Relation**: edge. “OWNS”, “AFFECTS”, “DEPENDS_ON”, “HAS_SLA”처럼 의미 있는 연결.
- **Graph extraction**: 문서에서 entity/relation을 LLM으로 추출해 그래프에 적재.
- **Graph-guided retrieval**: 질의에서 씨앗(seed) 노드를 찾고(보통 벡터 검색/키워드), 그 주변을 traversal 하며 증거를 확장.
- **Local / Global / Hybrid**: Microsoft GraphRAG 논문/구현은 “로컬 서브그래프 근거”와 “커뮤니티(클러스터) 요약 기반 전역 근거”를 분리해 다룹니다. ([arxiv.org](https://arxiv.org/abs/2404.16130?utm_source=openai))

### 2) 내부 작동 방식(흐름 관점)
실무 구현을 “Index time / Query time”으로 나누면 판단이 쉬워집니다.

**(A) Index time**
1. **Ingest**: 문서(위키/티켓/계약 PDF 텍스트화 등)를 단위별로 저장
2. **Extraction**: 각 문서에서 entity/relation 후보를 추출(LLM, 규칙, NER 혼합 가능)
3. **Canonicalization**: “ACME Corp.” vs “Acme” 중복/동일성 해소(이 단계가 성패를 가릅니다)
4. **Store**
   - Graph store(Neo4j/TigerGraph/MongoDB GraphStore 등)
   - Vector store(문서 chunk/엔티티 설명/관계 설명 임베딩)
5. (선택) **Community detection + 요약**: 큰 그래프를 커뮤니티로 묶고 요약을 만들어 “전역 컨텍스트”로 쓰는 전략(=global). ([arxiv.org](https://arxiv.org/abs/2404.16130?utm_source=openai))

**(B) Query time**
1. 질의에서 핵심 엔티티/의도를 추출
2. **Seed retrieval**: 벡터로 유사한 chunk 또는 엔티티를 top-k로 찾음
3. **Traversal**: seed에서 1~N hop 확장(가중치/타입 제한/시간 필터)
4. **Evidence packing**: “서브그래프 트리플 + 원문 근거 스니펫”을 묶어 LLM에 전달
5. **Answer + provenance**: 어떤 노드/엣지/문서에서 근거를 가져왔는지 함께 반환(설명가능성)

LangChain 쪽에는 “기존 vector store 메타데이터를 엣지로 보고 traversal을 섞는 GraphRetriever”도 있습니다. 즉, GraphRAG가 꼭 ‘대형 그래프DB’만을 의미하진 않고, **그래프를 retrieval 전략으로 끌어오는 것**이 핵심입니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/integrations/retrievers/graph_rag?utm_source=openai))  
또한 MongoDB도 LangChain 통합에서 Graph store로 쓰는 GraphRAG 패턴을 문서화하고 있습니다. ([mongodb.com](https://www.mongodb.com/docs/atlas/ai-integrations/langchain/graph-rag/?utm_source=openai))

### 3) 다른 접근과의 차이점(실무 판단 포인트)
- **Vector RAG**: “비슷한 텍스트 조각”을 모음 → 관계/경로는 LLM이 프롬프트 내에서 추론(불안정)
- **GraphRAG**: “관계가 있는 근거”를 먼저 모음 → LLM은 **이미 구조화된 컨텍스트**에서 생성  
Neo4j 쪽도 GraphRAG가 flat retrieval이 놓치는 관계(멀티홉, 소유/의존/연결 등)를 잡는다고 강조합니다. ([neo4j.com](https://neo4j.com/blog/auradb/neo4j-virtual-graph-is-now-in-public-preview/?utm_source=openai))

---

## 💻 실전 코드
아래는 “사내 장애(Incident) + 서비스 의존성 + 고객 영향도”를 묻는 질문을 GraphRAG로 푸는 현실적인 예시입니다.

- Graph store: **Neo4j**
- Vector store: **Qdrant**
- Flow: (1) 문서 적재 → (2) 엔티티/관계 추출 → (3) seed 벡터 검색 → (4) Neo4j 2-hop 확장 → (5) 근거 패킹 → (6) LLM 답변

> 주의: extraction 품질은 도메인/프롬프트에 크게 좌우됩니다. Microsoft GraphRAG도 “prompt tuning”을 강하게 권장합니다. ([github.com](https://github.com/microsoft/graphrag?utm_source=openai))

### 1) 초기 셋업
```bash
# 1) infra
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/testpassword \
  neo4j:5

docker run -d --name qdrant \
  -p 6333:6333 \
  qdrant/qdrant:latest

# 2) python deps
python -m venv .venv && source .venv/bin/activate
pip install neo4j qdrant-client openai pydantic tiktoken python-dotenv
```

`.env`
```bash
OPENAI_API_KEY=...
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=testpassword
QDRANT_URL=http://localhost:6333
```

### 2) 인덱싱(문서→그래프 + 벡터)
```python
# file: index_graphrag.py
import os, json, hashlib
from typing import List, Literal
from pydantic import BaseModel
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

NEO4J_URI = os.environ["NEO4J_URI"]
NEO4J_USER = os.environ["NEO4J_USER"]
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]
QDRANT_URL = os.environ["QDRANT_URL"]

COLL = "docs"

class Triple(BaseModel):
    head: str
    head_type: str
    rel: str
    tail: str
    tail_type: str
    evidence: str  # 원문 스니펫(짧게)

class Extraction(BaseModel):
    doc_id: str
    triples: List[Triple]

def sha_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]

def embed(text: str) -> List[float]:
    r = client.embeddings.create(model="text-embedding-3-large", input=text)
    return r.data[0].embedding

EXTRACT_PROMPT = """You extract a small, high-precision knowledge graph from SRE/incident docs.
Return JSON only.

Rules:
- Prefer precision over recall.
- Normalize entity names (e.g., "Payments API" not "payment api").
- Use these node types only: Service, Incident, Customer, Contract, Component.
- Use these relations only: DEPENDS_ON, AFFECTS, CAUSED_BY, HAS_SLA, OWNED_BY.
- evidence must be a short verbatim snippet (<= 160 chars) from the text.

Output schema:
{ "doc_id": "...", "triples": [ { "head":"", "head_type":"", "rel":"", "tail":"", "tail_type":"", "evidence":"" } ] }
"""

def extract(doc_id: str, text: str) -> Extraction:
    r = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role":"system","content":EXTRACT_PROMPT},
            {"role":"user","content":f"doc_id={doc_id}\nTEXT:\n{text}"}
        ],
    )
    return Extraction.model_validate_json(r.choices[0].message.content)

def neo4j_upsert(ex: Extraction):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    cypher = """
    UNWIND $triples AS t
    MERGE (h:Entity {name: t.head, type: t.head_type})
    MERGE (ta:Entity {name: t.tail, type: t.tail_type})
    MERGE (h)-[r:REL {name: t.rel}]->(ta)
    SET r.evidence = t.evidence
    """
    with driver.session() as s:
        s.run(cypher, triples=[t.model_dump() for t in ex.triples])
    driver.close()

def qdrant_upsert(doc_id: str, text: str):
    q = QdrantClient(url=QDRANT_URL)
    if not q.collection_exists(COLL):
        q.create_collection(
            collection_name=COLL,
            vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
        )
    vec = embed(text)
    q.upsert(
        collection_name=COLL,
        points=[PointStruct(
            id=sha_id(doc_id),
            vector=vec,
            payload={"doc_id": doc_id, "text": text[:4000]}  # payload는 적당히
        )]
    )

if __name__ == "__main__":
    # 현실적인 입력: incident postmortem + 서비스 맵 일부(예시)
    docs = [
        ("INC-2026-08-11", """Incident: INC-2026-08-11
Payments API latency increased due to Redis cluster saturation.
Checkout Service depends on Payments API.
Impact: 37 enterprise customers affected, including ACME Corp.
Root cause: Redis component misconfigured.
SLA: ACME Corp contract has 99.9% with exception for scheduled maintenance."""),
        ("SVC-CATALOG", """Service Catalog
Checkout Service depends on Payments API.
Payments API depends on Redis Cluster.
Owner: Platform Team owns Payments API."""),
    ]

    for doc_id, text in docs:
        ex = extract(doc_id, text)
        neo4j_upsert(ex)
        qdrant_upsert(doc_id, text)

    print("Indexed docs into Neo4j (graph) and Qdrant (vectors).")
```

예상 출력:
```text
Indexed docs into Neo4j (graph) and Qdrant (vectors).
```

### 3) 질의(Seed 검색 → 2-hop 그래프 확장 → 답변)
```python
# file: query_graphrag.py
import os
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

NEO4J_URI = os.environ["NEO4J_URI"]
NEO4J_USER = os.environ["NEO4J_USER"]
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]
QDRANT_URL = os.environ["QDRANT_URL"]
COLL = "docs"

def embed(text: str):
    r = client.embeddings.create(model="text-embedding-3-large", input=text)
    return r.data[0].embedding

def seed_docs(question: str, k=3):
    q = QdrantClient(url=QDRANT_URL)
    hits = q.search(collection_name=COLL, query_vector=embed(question), limit=k)
    return [h.payload for h in hits]

def expand_graph(seed_terms):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    cypher = """
    MATCH (e:Entity)
    WHERE any(term IN $terms WHERE toLower(e.name) CONTAINS toLower(term))
    MATCH p=(e)-[r:REL*1..2]->(x:Entity)
    RETURN e.name AS seed, [rel IN relationships(p) | {rel: rel.name, evidence: rel.evidence}] AS edges,
           [n IN nodes(p) | {name:n.name, type:n.type}] AS nodes
    LIMIT 30
    """
    with driver.session() as s:
        rows = [dict(r) for r in s.run(cypher, terms=seed_terms)]
    driver.close()
    return rows

def answer(question: str, docs, graph_paths):
    context = {
        "seed_docs": docs,
        "graph_paths": graph_paths
    }
    r = client.chat.completions.create(
        model="gpt-4.1",
        temperature=0.2,
        messages=[
            {"role":"system","content":(
                "You are an SRE assistant. Answer using only the provided evidence. "
                "If evidence is insufficient, say what is missing. Provide bulletproof provenance."
            )},
            {"role":"user","content":f"QUESTION:\n{question}\n\nEVIDENCE(JSON):\n{context}"}
        ],
    )
    return r.choices[0].message.content

if __name__ == "__main__":
    q = "INC-2026-08-11에서 ACME Corp이 왜 영향을 받았고, SLA 예외가 적용되는지 근거와 함께 설명해줘."
    docs = seed_docs(q, k=2)

    # seed term은 실무에선 NER/LLM로 뽑되, 여기선 간단히 키워드만
    graph_paths = expand_graph(["INC-2026-08-11", "ACME", "Payments API", "Checkout Service"])

    print(answer(q, docs, graph_paths))
```

예상 출력(형태 예시):
- “Checkout Service DEPENDS_ON Payments API” 경로 + “Payments API … Redis …” 근거
- “Impact: … ACME Corp” 문서 스니펫
- “SLA … exception … scheduled maintenance” 스니펫  
즉, **‘문서 한 조각’이 아니라 ‘관계 경로’가 답변 구조를 강제**하게 만드는 게 포인트입니다.

---

## ⚡ 실전 팁 & 함정
### Best Practice (현업에서 체감 큰 것 3가지)
1) **스키마를 작게 고정하고, relation 타입을 제한**
- extraction 자유도를 높이면 “17 node types, 34 relationships” 같은 과잉 스키마가 나오고 운영이 망가집니다(중복/불일치 폭발). 실제 커뮤니티 경험에서도 “너무 복잡한 프레임워크/스키마가 비즈니스 가치를 못 만든다”는 반성이 반복됩니다. ([reddit.com](https://www.reddit.com/r/AI_Agents/comments/1sc5zpf/5_documents_17_node_types_34_relationships_thats/?utm_source=openai))
- 처음엔 5~8개 node type, 8~12개 relation type 정도로 **엄격히 제한**하세요.

2) **Canonicalization(동일 엔티티 정규화)을 파이프라인의 ‘주요 기능’으로 취급**
- GraphRAG 실패 원인의 상당수는 retrieval이 아니라 “ACME/Acme/ACME Corp”가 다른 노드로 생기는 데이터 품질입니다.
- 실무 팁: (a) source-of-truth ID(고객ID/서비스ID)를 가능한 빨리 부여 (b) alias 테이블 운영 (c) merge 규칙(정확 매칭→휴리스틱→LLM 판정) 단계화.

3) **Hybrid retrieval을 기본값으로**
- 그래프만으로는 원문 근거 텍스트가 부족해지고, 벡터만으로는 멀티홉이 깨집니다.
- Microsoft GraphRAG도 local/global/hybrid 모드를 이야기하며 “전역 요약 + 로컬 근거”를 함께 쓰는 방향을 제시합니다. ([arxiv.org](https://arxiv.org/abs/2404.16130?utm_source=openai))

### 흔한 함정/안티패턴
- **Extraction을 recall 위주로 돌리기**: 그래프가 커질수록 traversal이 노이즈를 증폭합니다. “정확한 소수 트리플”이 “애매한 다수 트리플”보다 낫습니다.
- **Traversal hop 수를 고정(예: 3-hop 무조건)**: 질의 유형마다 다릅니다. hop이 늘수록 컨텍스트가 급팽창하고, 비용/환각 위험이 커집니다.
- **그래프DB 도입이 ‘목표’가 되는 것**: 그래프는 수단입니다. LangChain의 GraphRetriever처럼 “기존 vector store 메타데이터”를 그래프처럼 연결해 traversal하는 접근도 있습니다. ([docs.langchain.com](https://docs.langchain.com/oss/python/integrations/retrievers/graph_rag?utm_source=openai))

### 비용/성능/안정성 트레이드오프
- **비용**: 인덱싱(=extraction LLM 호출)이 가장 비쌉니다. GraphRAG 프로젝트도 인덱싱 비용을 경고합니다. ([github.com](https://github.com/microsoft/graphrag?utm_source=openai))  
  → 대응: 변경분만 재추출(증분), 고가 모델은 어려운 문서에만, 나머지는 규칙/저가 모델.
- **성능**: 그래프 traversal은 빠를 수 있지만, “seed 품질”이 나쁘면 쓸모없는 서브그래프만 뽑습니다.  
  → 대응: seed를 “엔티티 벡터(엔티티 설명 임베딩)”와 “문서 벡터”로 이중화.
- **안정성**: 스키마가 흔들리면 downstream 프롬프트/쿼리가 연쇄 붕괴합니다.  
  → 대응: 스키마 버저닝, relation type 추가는 RFC처럼 관리.

---

## 🚀 마무리
GraphRAG는 “더 똑똑한 검색”이라기보다, **검색 결과를 ‘관계 중심의 컨텍스트’로 재구성하는 아키텍처**입니다. 멀티홉/의존성/영향도/소유권처럼 관계가 핵심인 도메인에서는, vector RAG 대비 답변의 일관성과 설명가능성을 크게 끌어올릴 수 있습니다. ([neo4j.com](https://neo4j.com/blog/auradb/neo4j-virtual-graph-is-now-in-public-preview/?utm_source=openai))

도입 판단 기준(간단 체크리스트):
- 질문의 30% 이상이 “A와 B의 관계/경로/영향”을 묻나?
- “근거 경로”를 사용자에게 보여줘야 하나(감사/보안/금융)?
- 엔티티 ID/정규화를 운영할 준비가 있나?
- 인덱싱 비용(LLM extraction)을 감당하거나, 증분 파이프라인으로 줄일 수 있나?

다음 학습 추천:
- Microsoft GraphRAG의 CLI/문서로 **local/global retrieval 개념과 파이프라인 설계**를 먼저 체득하고, ([microsoft.github.io](https://microsoft.github.io/graphrag/cli/?utm_source=openai))
- LangChain의 GraphRetriever 같은 “그래프 traversal + 벡터” 결합 방식을 참고해 **내 스택의 최소 변경으로 PoC**를 만든 뒤, ([docs.langchain.com](https://docs.langchain.com/oss/python/integrations/retrievers/graph_rag?utm_source=openai))
- 필요할 때 Neo4j/MongoDB/TigerGraph 등 그래프 스토어 선택을 확장하는 순서가 가장 안전합니다. ([mongodb.com](https://www.mongodb.com/docs/atlas/ai-integrations/langchain/graph-rag/?utm_source=openai))