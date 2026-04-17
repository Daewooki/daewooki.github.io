#!/usr/bin/env python3
"""
LLM 웹 검색을 이용한 최신 트렌드 기반 블로그 포스트 자동 생성
- OpenAI GPT-5.2 + Web Search 도구 활용
- 월·목: 뉴스 1 + 기술 1, 그 외: 기술 2
- 최근 DEDUP_DAYS일 내 사용된 카테고리는 제외하여 중복 방지
"""

import json
import os
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

from openai import OpenAI


GA_TAG = """<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>

"""

# 카테고리 풀
# - id: 고유/고정값 (중복 방지 로직에서 참조)
# - type: "news" = 뉴스/트렌드 분석, "tech" = 기술 심층/튜토리얼
# - {date} 플레이스홀더는 실행 시 현재 년월로 치환
SEARCH_CATEGORIES = [
    # ===================== News (10) =====================
    {"id": "news-llm-models", "category": "AI", "subcategory": "News", "type": "news",
     "search_query": "{date} LLM 신규 모델 출시 발표 GPT Claude Gemini",
     "focus": "LLM 신규 모델 출시, 성능 비교, 업계 반응"},
    {"id": "news-ai-invest", "category": "AI", "subcategory": "News", "type": "news",
     "search_query": "{date} AI 스타트업 투자 인수합병 뉴스",
     "focus": "AI 스타트업 동향, 투자 유치, 인수합병 소식"},
    {"id": "news-bigtech-updates", "category": "AI", "subcategory": "News", "type": "news",
     "search_query": "{date} OpenAI Anthropic Google AI API 발표 업데이트",
     "focus": "빅테크 AI 기업 신규 발표, API 업데이트, 정책 변화"},
    {"id": "news-ai-regulation", "category": "AI", "subcategory": "News", "type": "news",
     "search_query": "{date} AI 규제 법안 정책 윤리 뉴스",
     "focus": "AI 규제 동향, 각국 정책, 윤리적 이슈"},
    {"id": "news-opensource", "category": "AI", "subcategory": "News", "type": "news",
     "search_query": "{date} 오픈소스 AI 모델 공개 Llama Mistral Qwen",
     "focus": "오픈소스 LLM/VLM 공개, 파생 모델, 라이선스 이슈"},
    {"id": "news-ai-hardware", "category": "AI", "subcategory": "News", "type": "news",
     "search_query": "{date} AI 반도체 GPU NVIDIA Rebellions Furiosa 칩 뉴스",
     "focus": "AI 가속기/GPU/NPU 소식, 공급망, AI 칩 기업 동향"},
    {"id": "news-dev-tools", "category": "AI", "subcategory": "News", "type": "news",
     "search_query": "{date} AI 개발자 도구 새 출시 IDE 에이전트",
     "focus": "새 출시된 개발자 도구, AI IDE/CLI, 에이전트 기반 툴"},
    {"id": "news-ai-security", "category": "AI", "subcategory": "News", "type": "news",
     "search_query": "{date} AI 보안 취약점 prompt injection jailbreak 이슈",
     "focus": "AI 보안 이슈, 모델 탈옥, 프롬프트 인젝션 사례"},
    {"id": "news-enterprise-adoption", "category": "AI", "subcategory": "News", "type": "news",
     "search_query": "{date} 기업 AI 도입 사례 케이스 스터디",
     "focus": "엔터프라이즈 AI 도입 사례, ROI, 실패담/성공담"},
    {"id": "news-ai-research", "category": "AI", "subcategory": "News", "type": "news",
     "search_query": "{date} AI 논문 연구 결과 주요 발표 arxiv",
     "focus": "주목할 AI 연구 논문, 새로운 기법, 벤치마크 결과"},

    # ===================== Tech: Agent (6) =====================
    {"id": "tech-agent-frameworks", "category": "AI", "subcategory": "Agent", "type": "tech",
     "search_query": "{date} AI Agent 개발 방법 LangGraph AutoGen CrewAI",
     "focus": "AI 에이전트 프레임워크 비교, 멀티 에이전트 구현"},
    {"id": "tech-agent-tool-use", "category": "AI", "subcategory": "Agent", "type": "tech",
     "search_query": "{date} AI Agent tool use function calling 구현",
     "focus": "에이전트 도구 사용, Function Calling 패턴"},
    {"id": "tech-agent-agentic-rag", "category": "AI", "subcategory": "Agent", "type": "tech",
     "search_query": "{date} Agentic RAG 자율 에이전트 구현 방법",
     "focus": "Agentic RAG, 자율적 정보 검색 에이전트"},
    {"id": "tech-agent-mcp", "category": "AI", "subcategory": "Agent", "type": "tech",
     "search_query": "{date} Model Context Protocol MCP 서버 구현 Claude",
     "focus": "MCP 프로토콜, 에이전트 확장 서버 구축"},
    {"id": "tech-agent-memory", "category": "AI", "subcategory": "Agent", "type": "tech",
     "search_query": "{date} AI Agent memory long-term 상태 관리 구현",
     "focus": "에이전트 장단기 메모리, 상태 관리 전략"},
    {"id": "tech-agent-orchestration", "category": "AI", "subcategory": "Agent", "type": "tech",
     "search_query": "{date} multi-agent orchestration supervisor worker 패턴",
     "focus": "멀티 에이전트 오케스트레이션, supervisor/worker 패턴"},

    # ===================== Tech: RAG (6) =====================
    {"id": "tech-rag-advanced", "category": "AI", "subcategory": "RAG", "type": "tech",
     "search_query": "{date} RAG 고급 기법 HyDE Reranking Query Expansion",
     "focus": "RAG 성능 최적화, 고급 검색 기법"},
    {"id": "tech-rag-vectordb", "category": "AI", "subcategory": "RAG", "type": "tech",
     "search_query": "{date} 벡터DB 비교 Pinecone Weaviate Qdrant Chroma",
     "focus": "벡터 데이터베이스 선택 가이드, 성능 비교"},
    {"id": "tech-rag-graph", "category": "AI", "subcategory": "RAG", "type": "tech",
     "search_query": "{date} GraphRAG knowledge graph RAG 구현",
     "focus": "GraphRAG, 지식 그래프 기반 검색 증강"},
    {"id": "tech-rag-hybrid", "category": "AI", "subcategory": "RAG", "type": "tech",
     "search_query": "{date} hybrid search BM25 vector search RAG",
     "focus": "하이브리드 검색(BM25+벡터), 랭킹 병합 전략"},
    {"id": "tech-rag-chunking", "category": "AI", "subcategory": "RAG", "type": "tech",
     "search_query": "{date} RAG chunking strategy document splitting 전략",
     "focus": "문서 청킹 전략, 오버랩/semantic chunking"},
    {"id": "tech-rag-embedding", "category": "AI", "subcategory": "RAG", "type": "tech",
     "search_query": "{date} embedding model 비교 OpenAI Cohere BGE",
     "focus": "임베딩 모델 비교, 도메인별 선택 가이드"},

    # ===================== Tech: Coding (6) =====================
    {"id": "tech-coding-assist", "category": "AI", "subcategory": "Coding", "type": "tech",
     "search_query": "{date} AI 코딩 어시스턴트 Cursor Copilot Windsurf 활용법",
     "focus": "AI 코딩 도구 활용, 생산성 향상 팁"},
    {"id": "tech-coding-vibe", "category": "AI", "subcategory": "Coding", "type": "tech",
     "search_query": "{date} Vibe Coding AI 프로토타이핑 빠른 개발 방법",
     "focus": "AI 활용 빠른 프로토타이핑, MVP 개발"},
    {"id": "tech-coding-ui-gen", "category": "AI", "subcategory": "Coding", "type": "tech",
     "search_query": "{date} AI 코드 생성 프론트엔드 v0 bolt.new 활용",
     "focus": "AI 기반 UI 생성, 프론트엔드 자동화 도구"},
    {"id": "tech-coding-cli-agents", "category": "AI", "subcategory": "Coding", "type": "tech",
     "search_query": "{date} Claude Code Codex CLI 에이전트 활용",
     "focus": "CLI 기반 AI 코딩 에이전트, 자동화 워크플로"},
    {"id": "tech-coding-review", "category": "AI", "subcategory": "Coding", "type": "tech",
     "search_query": "{date} AI 코드 리뷰 자동화 테스트 생성",
     "focus": "AI 기반 코드 리뷰/테스트 자동화, PR 봇"},
    {"id": "tech-coding-debug", "category": "AI", "subcategory": "Coding", "type": "tech",
     "search_query": "{date} AI 디버깅 에러 분석 LLM 활용",
     "focus": "LLM을 활용한 디버깅, 에러 분석 워크플로"},

    # ===================== Tech: LLM (7) =====================
    {"id": "tech-llm-prompt-cot", "category": "AI", "subcategory": "LLM", "type": "tech",
     "search_query": "{date} 프롬프트 엔지니어링 고급 기법 Chain of Thought",
     "focus": "프롬프트 최적화, 고급 프롬프팅 기법"},
    {"id": "tech-llm-finetune", "category": "AI", "subcategory": "LLM", "type": "tech",
     "search_query": "{date} LLM Fine-tuning LoRA QLoRA 방법 튜토리얼",
     "focus": "LLM 파인튜닝, 효율적 학습 방법"},
    {"id": "tech-llm-eval", "category": "AI", "subcategory": "LLM", "type": "tech",
     "search_query": "{date} LLM 평가 방법 벤치마크 MMLU HumanEval",
     "focus": "LLM 성능 평가, 벤치마크 해석"},
    {"id": "tech-llm-structured", "category": "AI", "subcategory": "LLM", "type": "tech",
     "search_query": "{date} LLM structured output JSON mode schema 제약",
     "focus": "구조화된 출력, JSON 스키마 강제, 함수 호출"},
    {"id": "tech-llm-caching", "category": "AI", "subcategory": "LLM", "type": "tech",
     "search_query": "{date} LLM prompt caching 비용 절감 Anthropic OpenAI",
     "focus": "프롬프트 캐싱, 캐시 히트율 최적화, 비용 절감"},
    {"id": "tech-llm-context", "category": "AI", "subcategory": "LLM", "type": "tech",
     "search_query": "{date} LLM long context window 활용 compaction",
     "focus": "긴 컨텍스트 활용, compaction/summary, lost in the middle"},
    {"id": "tech-llm-cost", "category": "AI", "subcategory": "LLM", "type": "tech",
     "search_query": "{date} LLM API 비용 최적화 토큰 절약 routing",
     "focus": "LLM 비용 최적화, 모델 라우팅, 토큰 절약"},

    # ===================== Tech: MLOps (5) =====================
    {"id": "tech-mlops-serving", "category": "AI", "subcategory": "MLOps", "type": "tech",
     "search_query": "{date} LLM 서빙 vLLM TGI Ollama 배포 방법",
     "focus": "LLM 서빙 인프라, 로컬 배포, 최적화"},
    {"id": "tech-mlops-monitor", "category": "AI", "subcategory": "MLOps", "type": "tech",
     "search_query": "{date} AI 애플리케이션 모니터링 LangSmith Langfuse",
     "focus": "LLM 앱 모니터링, 디버깅, 비용 추적"},
    {"id": "tech-mlops-tracing", "category": "AI", "subcategory": "MLOps", "type": "tech",
     "search_query": "{date} LLM observability OpenTelemetry tracing",
     "focus": "LLM 앱 observability, OpenTelemetry 트레이싱"},
    {"id": "tech-mlops-gpu", "category": "AI", "subcategory": "MLOps", "type": "tech",
     "search_query": "{date} GPU LLM 서빙 최적화 quantization 추론 가속",
     "focus": "GPU 활용 최적화, 양자화, 추론 가속 기법"},
    {"id": "tech-mlops-batch", "category": "AI", "subcategory": "MLOps", "type": "tech",
     "search_query": "{date} LLM batch inference API 대량 처리 비용",
     "focus": "배치 추론, 대량 요청 처리, 비동기 파이프라인"},

    # ===================== Tech: Multimodal (4) =====================
    {"id": "tech-multimodal-vlm", "category": "AI", "subcategory": "Multimodal", "type": "tech",
     "search_query": "{date} 멀티모달 AI Vision Language Model 활용법",
     "focus": "비전-언어 모델 활용, 이미지 분석 AI"},
    {"id": "tech-multimodal-voice", "category": "AI", "subcategory": "Multimodal", "type": "tech",
     "search_query": "{date} AI 음성 TTS STT 실시간 음성 에이전트",
     "focus": "음성 AI, 실시간 음성 대화 구현"},
    {"id": "tech-multimodal-ocr", "category": "AI", "subcategory": "Multimodal", "type": "tech",
     "search_query": "{date} OCR document AI 문서 이해 LLM 추출",
     "focus": "문서 OCR/이해, 구조화 추출, 표·PDF 처리"},
    {"id": "tech-multimodal-video", "category": "AI", "subcategory": "Multimodal", "type": "tech",
     "search_query": "{date} 비디오 AI video understanding generation",
     "focus": "비디오 이해/생성 AI, 프레임 분석 파이프라인"},

    # ===================== Tech: Backend (5) =====================
    {"id": "tech-backend-api", "category": "Backend", "subcategory": "API", "type": "tech",
     "search_query": "{date} FastAPI LLM API 서버 구축 스트리밍",
     "focus": "LLM API 서버 구축, 스트리밍 응답 처리"},
    {"id": "tech-backend-arch", "category": "Backend", "subcategory": "Architecture", "type": "tech",
     "search_query": "{date} AI 애플리케이션 아키텍처 설계 패턴",
     "focus": "AI 앱 설계 패턴, 확장 가능한 구조"},
    {"id": "tech-backend-queue", "category": "Backend", "subcategory": "Architecture", "type": "tech",
     "search_query": "{date} LLM 백엔드 queue worker Celery Redis 비동기",
     "focus": "LLM 비동기 처리, 큐/워커 아키텍처"},
    {"id": "tech-backend-rate-limit", "category": "Backend", "subcategory": "API", "type": "tech",
     "search_query": "{date} LLM API rate limit retry backoff 패턴",
     "focus": "LLM API 호출 안정화, rate limit/retry 패턴"},
    {"id": "tech-backend-prompt-injection", "category": "Backend", "subcategory": "Security", "type": "tech",
     "search_query": "{date} prompt injection 방어 LLM 보안 guardrail",
     "focus": "프롬프트 인젝션 방어, guardrail 설계"},

    # ===================== Tech: Infra (2) =====================
    {"id": "tech-infra-k8s", "category": "Infra", "subcategory": "Kubernetes", "type": "tech",
     "search_query": "{date} Kubernetes LLM 배포 GPU 오토스케일링",
     "focus": "쿠버네티스 GPU 워크로드, LLM 서빙 오토스케일"},
    {"id": "tech-infra-serverless", "category": "Infra", "subcategory": "Serverless", "type": "tech",
     "search_query": "{date} serverless LLM 배포 Modal Runpod AWS Lambda",
     "focus": "서버리스 LLM 배포, cold start 대응"},

    # ===================== Tech: Prototyping (2) =====================
    {"id": "tech-prototype-rapid-ui", "category": "AI", "subcategory": "Prototyping", "type": "tech",
     "search_query": "{date} Streamlit Gradio 빠른 AI 데모 UI 구현",
     "focus": "Streamlit/Gradio 기반 빠른 AI 데모 UI"},
    {"id": "tech-prototype-fullstack", "category": "AI", "subcategory": "Prototyping", "type": "tech",
     "search_query": "{date} Next.js AI 앱 Vercel AI SDK fullstack",
     "focus": "Next.js + Vercel AI SDK 기반 fullstack AI 앱"},

    # ===================== Tech: Data (2) =====================
    {"id": "tech-data-synth", "category": "AI", "subcategory": "Data", "type": "tech",
     "search_query": "{date} 합성 데이터 생성 LLM synthetic data 활용",
     "focus": "LLM 합성 데이터 생성, 파인튜닝용 데이터 구축"},
    {"id": "tech-data-curation", "category": "AI", "subcategory": "Data", "type": "tech",
     "search_query": "{date} 데이터 큐레이션 dedup dataset quality 전처리",
     "focus": "학습 데이터 큐레이션, 중복 제거, 품질 평가"},
]

# 중복 방지 윈도우 (일)
DEDUP_DAYS = 14

# 뉴스를 생성할 요일 (0=월 ... 6=일)
NEWS_WEEKDAYS = {0, 3}  # 월, 목

HISTORY_PATH = Path(__file__).parent / "post_history.json"


NEWS_PROMPT = """당신은 10년 경력의 시니어 개발자이자 기술 블로거입니다.
웹 검색 결과를 바탕으로 **뉴스/트렌드 분석 글**을 작성합니다.
독자는 실무 개발자이며, 단순 사실 전달이 아닌 "내 일에 어떤 영향을 주는지" 해석을 원합니다.

## 글 구조 (반드시 이 순서로 작성)

1. **## 들어가며** - 무슨 일이 있었는지 핵심 요약 (2-3문장)

2. **---**

3. **## 📰 무슨 일이 있었나** - 뉴스의 구체적 내용
   - 날짜, 기업명, 제품명, 수치 등 팩트 중심
   - 1차 소스(공식 발표/논문/보도자료) 우선

4. **---**

5. **## 🔍 왜 중요한가** - 개발자 관점의 영향
   - 기존 대비 구체적으로 무엇이 달라지는지
   - API/도구/아키텍처 선택에 미치는 영향

6. **---**

7. **## 💡 시사점과 전망** - 업계 흐름 해석
   - 경쟁사/대안과의 비교
   - 3-6개월 내 예상 시나리오
   - 반대 의견/회의론도 함께 제시

8. **---**

9. **## 🚀 마무리** - 핵심 요약 + 개발자가 지금 할 수 있는 구체적 액션 1-2가지

## 작성 규칙
- 한국어로 작성, 기술 용어는 영어 그대로
- **팩트 중심**: 날짜, 버전, 수치, 기업명 명시
- **분석 중심**: 단순 전달이 아닌 "왜 중요한지" 해석
- **균형감**: 장단점, 리스크도 함께
- 글 분량: 1500-2200자
- 이모지는 헤더에만 사용

## 금지 사항
- 인사말 금지, Front matter 금지, # 제목 금지
- 검색 결과에 없는 내용 지어내기 금지
- PR/광고 톤 금지
"""

TECH_PROMPT = """당신은 10년 경력의 시니어 개발자이자 기술 블로거입니다.
웹 검색 결과를 바탕으로 **기술 심층 분석/튜토리얼 글**을 작성합니다.
독자는 이미 개발 경력이 있으며, 표면적 소개가 아닌 "내 프로젝트에 어떻게 적용할지" 판단 기준을 원합니다.

## 글 구조 (반드시 이 순서로 작성)

1. **## 들어가며** - 이 기술이 해결하는 구체적 문제 + 언제 쓰면 좋고 언제 쓰면 안 되는지

2. **---**

3. **## 🔧 핵심 개념** - 기술의 핵심 원리
   - 주요 개념 정의
   - 내부 작동 방식 (단순 요약이 아닌 구조/흐름)
   - 다른 접근과의 차이점

4. **---**

5. **## 💻 실전 코드** - 실행 가능한 예제
   - 기본 사용법 + 현실적인 시나리오 코드 (toy 예제 X)
   - 설정/의존성, 예상 출력 포함
   - 필요하면 2-3단계로 빌드업 (초기 셋업 → 기본 동작 → 확장)

```언어
# 코드 예제
```

6. **---**

7. **## ⚡ 실전 팁 & 함정** - 실무에서 놓치기 쉬운 포인트
   - Best Practice 2-3가지
   - 흔한 함정/안티패턴
   - 비용/성능/안정성 트레이드오프

8. **---**

9. **## 🚀 마무리** - 핵심 정리 + 도입 판단 기준 + 다음 학습 추천

## 작성 규칙
- 한국어로 작성, 기술 용어는 영어 그대로
- **코드 필수**: 실행 가능하고 현실적인 예제 (toy 예제 금지)
- **깊이 우선**: "왜 이렇게 작동하는지"와 트레이드오프까지
- **실무 가치**: 읽은 뒤 자기 프로젝트에 바로 적용 가능
- 글 분량: 2000-3000자
- 코드 블록: ```언어명 형식 (python, typescript, bash 등)

## 금지 사항
- 인사말 금지, Front matter 금지, # 제목 금지
- 너무 기초적인 내용만 다루기 금지
- 한계/단점 생략하고 과장하기 금지
"""


def load_history() -> list[dict]:
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_history(history: list[dict]) -> None:
    # DEDUP_DAYS * 3 보다 오래된 기록은 잘라내 파일 크기 관리
    cutoff = datetime.now() - timedelta(days=DEDUP_DAYS * 3)
    kept = []
    for h in history:
        try:
            d = datetime.strptime(h["date"], "%Y-%m-%d")
        except (KeyError, ValueError):
            continue
        if d >= cutoff:
            kept.append(h)
    HISTORY_PATH.write_text(
        json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def recent_ids(history: list[dict], days: int) -> set[str]:
    cutoff = datetime.now() - timedelta(days=days)
    used: set[str] = set()
    for h in history:
        try:
            d = datetime.strptime(h["date"], "%Y-%m-%d")
        except (KeyError, ValueError):
            continue
        if d >= cutoff:
            cid = h.get("id")
            if cid:
                used.add(cid)
    return used


def pick_categories(today: datetime, num_posts: int, history: list[dict]) -> list[dict]:
    used = recent_ids(history, DEDUP_DAYS)

    news_pool = [c for c in SEARCH_CATEGORIES if c["type"] == "news" and c["id"] not in used]
    tech_pool = [c for c in SEARCH_CATEGORIES if c["type"] == "tech" and c["id"] not in used]

    # pool 고갈 시 전체 풀에서 다시 샘플링 (비상용)
    if not news_pool:
        news_pool = [c for c in SEARCH_CATEGORIES if c["type"] == "news"]
    if not tech_pool:
        tech_pool = [c for c in SEARCH_CATEGORIES if c["type"] == "tech"]

    # 날짜 기반 결정적 셔플 (같은 날 재실행 시 동일 결과)
    rng = random.Random(today.toordinal())
    rng.shuffle(news_pool)
    rng.shuffle(tech_pool)

    is_news_day = today.weekday() in NEWS_WEEKDAYS
    selected: list[dict] = []

    if is_news_day and num_posts >= 1 and news_pool:
        selected.append(news_pool.pop(0))

    while len(selected) < num_posts and tech_pool:
        selected.append(tech_pool.pop(0))

    # 뉴스 요일이 아닌데 num_posts가 많아 기술 풀이 모자라면 뉴스로 보충
    while len(selected) < num_posts and news_pool:
        selected.append(news_pool.pop(0))

    return selected[:num_posts]


def get_dynamic_date_str() -> str:
    today = datetime.now()
    return f"{today.year}년 {today.month}월"


def search_and_generate_post(client: OpenAI, category_info: dict) -> tuple[str, str]:
    post_type = category_info.get("type", "tech")
    type_label = "뉴스/트렌드 분석" if post_type == "news" else "기술 심층 분석"
    prompt = NEWS_PROMPT if post_type == "news" else TECH_PROMPT

    date_str = get_dynamic_date_str()
    search_query = category_info["search_query"].replace("{date}", date_str)

    print(f"🔍 [{type_label}] '{search_query}' 검색 중...")

    response = client.responses.create(
        model="gpt-5.2",
        tools=[{"type": "web_search"}],
        input=f"""다음 주제에 대해 웹 검색을 수행하고, 검색 결과를 바탕으로 블로그 포스트를 작성해주세요.

글 유형: {type_label}
검색 주제: {search_query}
집중 분야: {category_info['focus']}

요구사항:
1. 먼저 웹 검색으로 최신 정보를 수집하세요
2. 검색 결과에서 가장 흥미롭고 중요한 내용을 선별하세요
3. 아래 지침의 구조에 맞게 블로그 글을 작성하세요
4. 첫 줄에 매력적인 제목을 작성하세요

{prompt}
""",
        max_output_tokens=7000,
    )

    content = response.output_text

    lines = content.strip().split("\n")
    title = category_info["focus"]
    body = content

    first_line = lines[0].strip()
    if first_line and not first_line.startswith("#"):
        title = first_line.strip('"').strip("'").strip()
        body = "\n".join(lines[1:]).strip()
    elif first_line.startswith("# "):
        title = first_line[2:].strip()
        body = "\n".join(lines[1:]).strip()

    return title, body


def create_post_file(category_info: dict, title: str, body: str, suffix: str = "") -> str:
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    time_str = today.strftime("%Y-%m-%d %H:%M:%S +0900")

    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", title.lower())
    slug = re.sub(r"\s+", "-", slug).strip("-")[:40]

    if not slug:
        slug = f"{category_info['category'].lower()}-trend"

    filename = f"{date_str}-{slug}{suffix}.md"

    tags = [
        category_info["category"].lower(),
        category_info["subcategory"].lower(),
        "trend",
        date_str[:7],
    ]

    front_matter = f"""---
title: "{title}"
date: {time_str}
categories: [{category_info['category']}, {category_info['subcategory']}]
tags: [{', '.join(tags)}]
---

"""

    posts_dir = Path(__file__).parent.parent / "_posts"
    posts_dir.mkdir(exist_ok=True)
    filepath = posts_dir / filename

    filepath.write_text(front_matter + GA_TAG + body, encoding="utf-8")

    print(f"✅ 포스트 생성: {filename}")
    return filename


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        return

    client = OpenAI(api_key=api_key)

    print("🚀 최신 트렌드 기반 블로그 포스트 생성 시작!")
    print("=" * 50)

    num_posts = int(os.environ.get("NUM_POSTS", "2"))
    today = datetime.now()

    history = load_history()
    selected = pick_categories(today, num_posts, history)

    weekday_kr = "월화수목금토일"[today.weekday()]
    print(f"📅 {today:%Y-%m-%d} ({weekday_kr})")
    print(f"📋 선택된 카테고리: {[c['id'] for c in selected]}")

    generated_files = []
    for i, category_info in enumerate(selected):
        print(f"\n📝 [{i+1}/{len(selected)}] {category_info['id']} 글 생성 중...")

        try:
            title, body = search_and_generate_post(client, category_info)
            suffix = f"-{i+1}" if len(selected) > 1 else ""
            filename = create_post_file(category_info, title, body, suffix)
            generated_files.append(filename)

            history.append({
                "date": today.strftime("%Y-%m-%d"),
                "id": category_info["id"],
            })
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
            continue

    save_history(history)

    print("\n" + "=" * 50)
    print(f"🎉 완료! {len(generated_files)}개 포스트 생성됨:")
    for f in generated_files:
        print(f"   - {f}")


if __name__ == "__main__":
    main()
