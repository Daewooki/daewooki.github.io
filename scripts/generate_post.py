#!/usr/bin/env python3
"""
최신 IT 뉴스/기술 블로그 포스트 자동 생성 (OpenAI Responses API + web_search)

흐름
1. discover_topics : 웹 검색으로 최근 며칠간 IT 전반의 후보 주제를 수집 (JSON)
2. select_topics   : 최근 글(post_history.json)과 겹치는 주제 제외, 도메인 편중 완화, 뉴스/기술 번갈아 선택
3. write_post      : 주제별로 웹 검색 + 장문 작성 (JSON: title/slug/description/category/tags/body)
4. postprocess     : 추적 파라미터 제거, 인용 정리, 마무리 제안문 제거, 제목 정리
5. create_post_file: front matter + 본문 저장, history 갱신

환경 변수
- OPENAI_API_KEY (필수)
- OPENAI_MODEL   (기본 gpt-5.2)
- NUM_POSTS      (기본 2; 뉴스/기술을 번갈아 선택)
- POSTS_DIR      (기본 <repo>/_posts; 로컬 테스트용)
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import openai
from openai import OpenAI


MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2")
KST = timezone(timedelta(hours=9), name="KST")  # 한국은 DST가 없어 고정 오프셋으로 충분 (tzdata 불필요)
ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = Path(os.environ.get("POSTS_DIR") or (ROOT / "_posts"))
HISTORY_PATH = Path(__file__).resolve().parent / "post_history.json"

DEDUP_DAYS = 90          # 이 기간 안에 다룬 주제와 겹치면 제외
DOMAIN_BALANCE_DAYS = 14 # 이 기간의 도메인 분포를 보고 편중 완화
HISTORY_KEEP_DAYS = 400  # history 파일 보관 기간
KEYWORD_OVERLAP_LIMIT = 0.4  # Jaccard 유사도가 이 이상이면 같은 주제로 간주

SITE_URL = "https://daewooki.github.io"

GA_TAG = """<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
"""

# 블로그 카테고리(1단계). 뉴스 글은 [News, <도메인>], 기술 글은 [<도메인>, <세부>] 로 저장.
DOMAINS = [
    "Backend", "Frontend", "Mobile", "Languages", "Database", "Cloud", "DevOps",
    "Infrastructure", "Security", "AI", "Data", "Networking", "Systems",
    "OpenSource", "Tools", "Architecture", "Testing", "Performance", "Web", "Hardware",
]

# ---------------------------------------------------------------------------
# 프롬프트
# ---------------------------------------------------------------------------

BLOG_PROFILE = """이 블로그는 백엔드·인프라·AI 프로토타이핑을 주로 하는 10년차 개발자 권대욱의 개인 기술 블로그입니다.
주제 범위는 IT 전반입니다: 프로그래밍 언어, 프레임워크, 백엔드, 프론트엔드, 모바일, 데이터베이스, 클라우드,
DevOps, 인프라, 보안, AI/ML, 데이터, 네트워크, OS/시스템, 오픈소스, 개발 도구, 아키텍처, 테스트, 성능, 하드웨어."""

DISCOVER_INSTRUCTIONS = f"""당신은 한국어 개발자 기술 블로그의 편집자입니다.
{BLOG_PROFILE}

당신의 일은 오늘 쓸 만한 글감을 찾는 것입니다. 반드시 web_search 도구를 여러 번(최소 6회, 서로 다른 분야로) 사용해
실제로 최근에 일어난 일과, 지금 깊게 다룰 가치가 있는 기술 주제를 찾으세요. 기억에 의존해 지어내지 마세요.
검색 예시: "this week in programming", "release notes <언어/프레임워크>", "GitHub trending", "Hacker News top",
"security advisory CVE", "postgres release", "kubernetes release", "rust blog", "engineering blog", "AI model release",
한국어 검색("개발자 뉴스", "기술 블로그")도 섞어서."""

WRITER_INSTRUCTIONS = f"""당신은 이 블로그의 주인입니다.
{BLOG_PROFILE}

당신은 남의 글을 요약하는 기자가 아니라, 직접 써 보고 판단한 것을 정리하는 현업 개발자입니다.
아래 규칙은 반드시 지킵니다.

[목소리]
- 한국어로 쓰되 기술 용어는 영어 그대로 씁니다. 존댓말 서술체("~합니다", "~입니다")를 기본으로 하고, 가끔 1인칭("내 경우", "나는 ~로 결정했다")으로 경험과 판단을 드러냅니다.
- 인사말, 자기소개, "이 글에서는 ~를 다룹니다" 같은 메타 문장, 광고 톤, 과장은 쓰지 않습니다.
- 글의 마지막은 판단이나 정리로 끝냅니다. 독자에게 무언가를 제안하거나("원하시면 ~해 드릴게요"), 질문을 던지거나, 추가 요청을 유도하는 문장은 절대 쓰지 않습니다.
- 이모지를 쓰지 않습니다. 굵은 글씨(**)는 글 전체에서 5번 이하로만 씁니다. 따옴표로 단어를 감싸 강조하는 습관("진짜", "제대로")을 쓰지 않습니다.
- 영어 단어를 괄호로 병기하는 습관("계약(Contract)", "경계(Boundary)")을 쓰지 않습니다. 필요한 용어는 영어로만 씁니다.
- 같은 문장 구조나 같은 접속사를 반복하지 않습니다. 목록만 나열하지 말고, 문단으로 근거와 트레이드오프를 설명합니다.

[제목]
- 60자 이내. 연도·월·"기준"·"~판"·"~형"·"~식" 같은 시점 표기를 넣지 않습니다. 따옴표 훅, 클릭베이트, 느낌표를 쓰지 않습니다. 콜론은 최대 1개.
- 무엇을 다루는지 한눈에 보이는 담백한 기술 블로그 제목으로 씁니다. 예: "PostgreSQL 18의 비동기 I/O가 바꾸는 것", "Stripe가 OpenRouter를 인수한 이유".

[구조]
- 소제목(##, ###)은 주제에 맞게 직접 정합니다. "들어가며", "핵심 개념", "실전 코드", "실전 팁", "마무리" 같은 상투적 소제목은 쓰지 않습니다.
- 최소 5개 이상의 섹션. 본문에 # 제목, front matter, 날짜 스탬프를 넣지 않습니다.
- 뉴스 글: 무슨 일이 있었는지(날짜·수치·이름을 정확히) → 배경과 맥락 → 왜 중요한지(개발자·아키텍처·비용에 미치는 영향) → 반론과 회의론 → 앞으로 지켜볼 것 → 지금 할 수 있는 일.
- 기술 글: 어떤 문제를 푸는지와 언제 쓰면 안 되는지 → 원리와 내부 동작 → 실제로 동작하는 코드(의존성·버전·실행 명령·예상 출력 포함, 장난감 예제 금지, 현실적인 시나리오) → 함정과 트레이드오프 → 도입 판단 기준.

[분량과 깊이]
- 길수록 좋습니다. 코드를 제외하고 최소 8,000자, 목표 10,000~15,000자. 다만 내용 없는 반복으로 늘리지 않습니다.
- 깊이 우선: "왜 그렇게 동작하는지", 수치, 비교, 실패 사례, 한계까지 씁니다.

[출처]
- 사실 주장에는 링크를 답니다. 앵커 텍스트는 문맥에 맞는 표현으로 씁니다. 예: [PostgreSQL 18 릴리스 노트](https://...), [Stripe 공식 발표](https://...).
- 도메인 이름을 앵커로 쓰는 "([example.com](url))" 형식은 금지합니다. URL에 utm 같은 추적 파라미터를 붙이지 않습니다.
- 본문 끝에 "## 참고 자료" 섹션을 두고 "- [제목](URL)" 형식으로 출처를 정리합니다.
- 검색 결과에 없는 사실을 지어내지 않습니다. 확실하지 않으면 확실하지 않다고 씁니다."""


# ---------------------------------------------------------------------------
# JSON 스키마 (Structured Outputs)
# ---------------------------------------------------------------------------

CANDIDATES_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["news", "tech"]},
                    "domain": {"type": "string", "enum": DOMAINS},
                    "topic": {"type": "string", "description": "한국어 한 줄 주제"},
                    "angle": {"type": "string", "description": "이 글이 취할 관점/차별점 (한국어)"},
                    "why_now": {"type": "string", "description": "지금 다뤄야 하는 이유: 날짜, 버전, 사건 (한국어)"},
                    "search_queries": {"type": "array", "items": {"type": "string"}},
                    "keywords": {"type": "array", "items": {"type": "string"},
                                 "description": "영문 소문자 키워드 5개 (제품/기술명 위주)"},
                    "sources": {"type": "array", "items": {"type": "string"},
                                "description": "근거가 된 실제 URL"},
                },
                "required": ["type", "domain", "topic", "angle", "why_now",
                             "search_queries", "keywords", "sources"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}

POST_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "slug": {"type": "string", "description": "영문 소문자 kebab-case, 3~7단어"},
        "description": {"type": "string", "description": "글의 핵심 1~2문장, 120자 이내, 부제처럼"},
        "category": {"type": "string", "enum": DOMAINS},
        "subcategory": {"type": "string", "description": "짧은 영문 세부 분류: 제품/기술명 (예: PostgreSQL, Kubernetes, API, Rust)"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "3~6개, 영문 소문자 kebab-case"},
        "body_markdown": {"type": "string"},
    },
    "required": ["title", "slug", "description", "category", "subcategory", "tags", "body_markdown"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def load_history() -> list[dict]:
    """history 파일이 깨져 있으면 빈 목록으로 덮어쓰지 않고 실행을 중단한다."""
    if not HISTORY_PATH.exists():
        return []
    data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{HISTORY_PATH.name}: JSON 배열이어야 합니다")
    return data


def save_history(history: list[dict], today: datetime) -> None:
    cutoff = today.date() - timedelta(days=HISTORY_KEEP_DAYS)
    kept = []
    for h in history:
        try:
            d = datetime.strptime(h["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            continue
        if d >= cutoff:
            kept.append(h)
    HISTORY_PATH.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def recent_entries(history: list[dict], today: datetime, days: int) -> list[dict]:
    cutoff = today.date() - timedelta(days=days)
    out = []
    for h in history:
        try:
            d = datetime.strptime(h["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            continue
        if d >= cutoff:
            out.append(h)
    return out


def existing_slugs(posts_dir: Path) -> set[str]:
    slugs = set()
    for p in posts_dir.glob("*.md"):
        slugs.add(re.sub(r"^\d{4}-\d{2}-\d{2}-", "", p.stem))
    return slugs


# ---------------------------------------------------------------------------
# OpenAI 호출
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("응답에서 JSON 객체를 찾지 못했습니다")
    return json.loads(text[start:end + 1])


class ResponseIncomplete(RuntimeError):
    """max_output_tokens 초과, 실패, 거부 등으로 쓸 수 있는 본문이 없는 경우."""


def _response_text(resp) -> str:
    """마지막 message 아이템의 텍스트를 돌려준다 (output_text는 모든 message를 이어붙이므로)."""
    status = getattr(resp, "status", None)
    if status == "incomplete":
        reason = getattr(getattr(resp, "incomplete_details", None), "reason", "unknown")
        raise ResponseIncomplete(f"응답이 잘렸습니다 (reason={reason})")
    if status == "failed":
        err = getattr(resp, "error", None)
        raise ResponseIncomplete(f"응답 실패: {getattr(err, 'message', err)}")
    last_text = None
    for item in getattr(resp, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", None) or []:
            ptype = getattr(part, "type", None)
            if ptype == "refusal":
                raise ResponseIncomplete(f"모델이 거부했습니다: {getattr(part, 'refusal', '')[:200]}")
            if ptype == "output_text":
                last_text = getattr(part, "text", None)
    if last_text is None:
        last_text = getattr(resp, "output_text", "") or ""
    if not last_text.strip():
        raise ResponseIncomplete("응답 본문이 비어 있습니다")
    return last_text


def call_json(client: OpenAI, *, instructions: str, prompt: str, schema_name: str,
              schema: dict, max_output_tokens: int, effort: str = "medium",
              max_tool_calls: int = 12, verbosity: str | None = None) -> dict:
    """Structured Outputs(json_schema) 로 호출하고, 스키마/JSON 문제일 때만 자유 출력으로 한 번 더 시도한다.

    max_output_tokens 에는 reasoning 토큰도 포함되므로 본문 목표보다 넉넉히 잡는다.
    네트워크/인증/한도 오류는 그대로 올려서 (SDK 재시도 후) 워크플로우가 실패하게 둔다.
    """
    base = dict(
        model=MODEL,
        instructions=instructions,
        tools=[{"type": "web_search"}],
        max_output_tokens=max_output_tokens,
        max_tool_calls=max_tool_calls,
        reasoning={"effort": effort},
    )
    text_cfg: dict = {"format": {"type": "json_schema", "name": schema_name,
                                 "schema": schema, "strict": True}}
    if verbosity:
        text_cfg["verbosity"] = verbosity
    try:
        resp = client.responses.create(input=prompt, text=text_cfg, **base)
        _log_usage(resp)
        return json.loads(_response_text(resp))
    except ResponseIncomplete as e:
        # 잘린 경우 같은 예산으로 다시 부르면 또 잘린다 → 예산을 두 배로 늘려 구조화 출력으로 한 번 더
        if "max_output_tokens" not in str(e):
            raise
        base["max_output_tokens"] = min(max_output_tokens * 2, 120000)
        print(f"⚠️ 출력이 잘렸습니다 → max_output_tokens={base['max_output_tokens']} 로 재시도")
        resp = client.responses.create(input=prompt, text=text_cfg, **base)
        _log_usage(resp)
        return json.loads(_response_text(resp))
    except (openai.BadRequestError, json.JSONDecodeError) as e:
        # 400: text.format/verbosity 조합 미지원 등 요청 형식 문제, JSONDecodeError: 출력이 JSON이 아님
        print(f"⚠️ structured output 실패 ({type(e).__name__}: {str(e)[:200]}) → 자유 출력으로 재시도")
    resp = client.responses.create(
        input=prompt + "\n\n출력은 코드펜스 없이, 위에서 요구한 필드를 가진 JSON 객체 하나만 작성하세요.",
        **base,
    )
    _log_usage(resp)
    return _extract_json(_response_text(resp))


def _log_usage(resp) -> None:
    """CI 로그에서 예산을 조정할 수 있도록 토큰 사용량을 남긴다."""
    u = getattr(resp, "usage", None)
    if not u:
        return
    details = getattr(u, "output_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", None)
    print(f"   ↳ tokens: input={getattr(u, 'input_tokens', '?')} output={getattr(u, 'output_tokens', '?')}"
          + (f" (reasoning={reasoning})" if reasoning is not None else ""))


# ---------------------------------------------------------------------------
# 1) 후보 주제 수집
# ---------------------------------------------------------------------------

def discover_topics(client: OpenAI, today: datetime, history: list[dict]) -> list[dict]:
    recent = recent_entries(history, today, DEDUP_DAYS)
    recent_lines = []
    for h in sorted(recent, key=lambda x: x.get("date", ""), reverse=True)[:150]:
        kw = ", ".join(h.get("keywords") or [])
        recent_lines.append(f"- {h.get('date')} [{h.get('domain') or h.get('category', '')}] "
                            f"{h.get('title') or h.get('id', '')}" + (f" (keywords: {kw})" if kw else ""))
    recent_block = "\n".join(recent_lines) if recent_lines else "- (없음)"

    prompt = f"""오늘: {today:%Y-%m-%d} ({'월화수목금토일'[today.weekday()]}) KST

할 일: 웹 검색을 충분히 수행해서 아래 두 종류의 글감 후보를 찾으세요.

- news 6개: 최근 7일 이내에 실제로 일어난 일. 예: 언어/프레임워크/DB/커널/브라우저의 주요 릴리스, 보안 사고나 취약점,
  인수합병·투자, 대규모 서비스 장애, 정책·규제, 빅테크 발표, 인기 오픈소스 프로젝트의 큰 변화, 개발자 커뮤니티에서 크게 논의된 글.
- tech 6개: 지금 깊게 다룰 가치가 있는 기술 주제. 최근 릴리스·변경·논쟁 같은 "지금 다룰 이유"가 분명해야 합니다.
  예: 새 버전에서 바뀐 API 사용법, 새로 주류가 된 패턴, 실측 기반 성능 비교, 마이그레이션 가이드, 운영에서 겪는 문제의 해법.

조건:
- 후보 12개가 서로 다른 도메인을 최소 6개 이상 포함해야 합니다. AI 도메인은 최대 4개.
- 아래 "최근 다룬 주제"와 같은 주제, 같은 제품의 같은 이슈는 제외합니다. 같은 제품이라도 새로운 사건(새 버전, 새 사고)이면 됩니다.
- 각 후보의 sources에는 검색으로 확인한 실제 URL을 넣습니다. 확인되지 않은 것은 후보에 넣지 않습니다.
- topic/angle/why_now는 한국어, keywords는 영문 소문자 5개(제품명·기술명 위주), search_queries는 그 글을 쓸 때 다시 검색할 질의 2~3개.

최근 다룬 주제 (최근 {DEDUP_DAYS}일, 제외 대상):
{recent_block}
"""
    data = call_json(client, instructions=DISCOVER_INSTRUCTIONS, prompt=prompt,
                     schema_name="topic_candidates", schema=CANDIDATES_SCHEMA,
                     max_output_tokens=40000, effort="medium", max_tool_calls=16)
    cands = []
    for c in data.get("candidates", []) or []:
        if not isinstance(c, dict) or not c.get("topic"):
            continue
        cands.append({
            "type": c.get("type") if c.get("type") in ("news", "tech") else "tech",
            "domain": c.get("domain") if c.get("domain") in DOMAINS else "Tools",
            "topic": str(c.get("topic")).strip(),
            "angle": str(c.get("angle") or "").strip(),
            "why_now": str(c.get("why_now") or "").strip(),
            "search_queries": [str(q) for q in (c.get("search_queries") or []) if q],
            "keywords": normalize_keywords(c.get("keywords") or []),
            "sources": [str(s) for s in (c.get("sources") or []) if s],
        })
    return cands


# ---------------------------------------------------------------------------
# 2) 주제 선택 (중복 제거 + 도메인 균형)
# ---------------------------------------------------------------------------

def normalize_keywords(words) -> list[str]:
    out = []
    for w in words:
        w = re.sub(r"[^a-z0-9.+#-]", "", str(w).lower().strip().replace(" ", "-"))
        if w and w not in out:
            out.append(w)
    return out[:8]


def title_tokens(title: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9][a-z0-9.+#-]{1,}", (title or "").lower()) if len(t) > 2}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def is_duplicate(cand: dict, recent: list[dict]) -> tuple[bool, str]:
    ck = set(cand.get("keywords") or [])
    ct = title_tokens(cand.get("topic", "")) | ck
    for h in recent:
        hk = set(h.get("keywords") or [])
        ht = title_tokens(h.get("title", "")) | hk
        if hk and jaccard(ck, hk) >= KEYWORD_OVERLAP_LIMIT:
            return True, h.get("title") or h.get("id", "")
        if ct and ht and jaccard(ct, ht) >= KEYWORD_OVERLAP_LIMIT:
            return True, h.get("title") or h.get("id", "")
    return False, ""


def select_topics(cands: list[dict], today: datetime, history: list[dict], num_posts: int) -> list[dict]:
    recent = recent_entries(history, today, DEDUP_DAYS)
    balance = recent_entries(history, today, DOMAIN_BALANCE_DAYS)
    domain_load: dict[str, int] = {}
    for h in balance:
        d = h.get("domain") or h.get("category")
        if d:
            domain_load[d] = domain_load.get(d, 0) + 1

    fresh = []
    for c in cands:
        dup, why = is_duplicate(c, recent)
        if dup:
            print(f"   ⏭️  중복 제외: {c['topic'][:60]}  ≈  {why[:60]}")
            continue
        fresh.append(c)

    # 도메인 편중이 적은 순서 → 모델이 제시한 순서 (안정 정렬)
    fresh.sort(key=lambda c: domain_load.get(c["domain"], 0))

    # 뉴스/기술을 번갈아 선택. 한쪽이 모자라면 다른 쪽으로 채움.
    order = ["news", "tech"] if today.toordinal() % 2 == 0 else ["tech", "news"]
    selected: list[dict] = []
    used_domains: set[str] = set()
    i = 0
    while len(selected) < num_posts and fresh:
        want = order[i % 2]
        pool = [c for c in fresh if c["type"] == want and c["domain"] not in used_domains] \
            or [c for c in fresh if c["type"] == want] \
            or [c for c in fresh if c["domain"] not in used_domains] \
            or fresh
        pick = pool[0]
        fresh.remove(pick)
        # 같은 실행 안에서 같은 사건을 두 번 고르지 않도록
        dup, why = is_duplicate(pick, [{"title": s["topic"], "keywords": s["keywords"]} for s in selected])
        if dup:
            print(f"   ⏭️  오늘 선택분과 중복: {pick['topic'][:60]}  ≈  {why[:60]}")
            continue
        selected.append(pick)
        used_domains.add(pick["domain"])
        i += 1
    return selected


# ---------------------------------------------------------------------------
# 3) 글 작성
# ---------------------------------------------------------------------------

def related_posts(cand: dict, history: list[dict], limit: int = 5) -> list[dict]:
    ck = set(cand.get("keywords") or []) | title_tokens(cand.get("topic", ""))
    scored = []
    for h in history:
        if not h.get("slug") or not h.get("title"):
            continue
        hk = set(h.get("keywords") or []) | title_tokens(h.get("title", ""))
        s = jaccard(ck, hk)
        if s > 0:
            scored.append((s, h))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in scored[:limit]]


def write_post(client: OpenAI, cand: dict, history: list[dict], today: datetime) -> dict:
    kind = "뉴스 분석" if cand["type"] == "news" else "기술 심층 분석"
    rel = related_posts(cand, history)
    rel_block = "\n".join(f"- [{h['title']}]({SITE_URL}/posts/{h['slug']}/)" for h in rel) or "- (없음)"
    queries = "\n".join(f"- {q}" for q in cand.get("search_queries") or []) or "- (직접 정하세요)"
    sources = "\n".join(f"- {s}" for s in cand.get("sources") or []) or "- (없음)"

    prompt = f"""오늘: {today:%Y-%m-%d} KST
글 종류: {kind}
도메인: {cand['domain']}
주제: {cand['topic']}
관점: {cand['angle']}
지금 다루는 이유: {cand['why_now']}

추천 검색어:
{queries}

후보 수집 단계에서 확인한 URL (반드시 다시 열어 내용을 확인하고 쓸 것):
{sources}

이 블로그에서 예전에 다룬 관련 글 (내용을 반복하지 말 것. 문맥에 맞으면 본문에서 자연스럽게 링크해도 됨):
{rel_block}

작성 절차:
1. web_search를 최소 5회 수행해 1차 소스(공식 문서, 릴리스 노트, 발표문, 논문, 원문 블로그)를 확보합니다.
2. 확인된 사실만으로, 위 규칙에 맞는 장문의 글을 씁니다. 코드가 들어가는 글은 실제로 실행 가능한 수준으로 씁니다.
3. JSON 필드로 출력합니다: title, slug, description, category, subcategory, tags, body_markdown.
   body_markdown에는 front matter나 # 제목을 넣지 않습니다. 마지막 섹션은 "## 참고 자료"입니다.
"""
    return call_json(client, instructions=WRITER_INSTRUCTIONS, prompt=prompt,
                     schema_name="blog_post", schema=POST_SCHEMA,
                     max_output_tokens=64000, effort="medium", max_tool_calls=12,
                     verbosity="high")


# ---------------------------------------------------------------------------
# 4) 후처리 (기존 글 정리 스크립트에서도 재사용)
# ---------------------------------------------------------------------------

TRACKING_PARAMS = re.compile(r"(?:utm_[a-z]+|ref_src|fbclid|gclid|mc_cid|mc_eid)=[^&#\s)]*", re.I)
CITATION_GROUP = re.compile(
    r"\(\s*(\[[^\]\n]+\]\(https?://[^)\s]+\)\s*(?:[,;、]\s*\[[^\]\n]+\]\(https?://[^)\s]+\)\s*)*)\)"
)
MD_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
OFFER_TRIGGER = re.compile(r"(원하시면|원하면|원하신다면|필요하시면|필요하면|말씀해\s*주시면|알려\s*주시면|알려주면|요청하시면|댓글로)")
# 문장 끝에 오는 제안형 종결어미만 (본문 속 "~를 권해 드립니다" 같은 일반 문장은 남긴다)
OFFER_VERB = re.compile(r"(드릴게요|드리겠습니다|드릴\s*수\s*있(?:습니다|어요)|해\s*드릴게|해드릴게|드릴게|드릴까요|드려요)\s*[.!]?\s*$")
# 제목의 시점 표기: "(2026년 9월 기준)" 같은 괄호형과 "2026년 9월 기준: " 같은 선행형만 (문장 속 연도는 건드리지 않음)
TITLE_STAMP = re.compile(
    r"\s*[\(（]\s*20\d\d\s*년\s*(?:\d{1,2}\s*월)?\s*(?:기준|현재|판|버전)?\s*[\)）]"
    r"|^\s*20\d\d\s*년\s*\d{1,2}\s*월\s*(?:기준|현재)?\s*[:：,，]?\s+"
    r"|\s*[:：,，]\s*20\d\d\s*년\s*\d{1,2}\s*월\s*(?:기준|현재)?\s*$"
)


def strip_tracking(url: str) -> str:
    if "?" not in url:
        return url
    base, _, rest = url.partition("?")
    frag = ""
    if "#" in rest:
        rest, _, frag = rest.partition("#")
    params = [p for p in rest.split("&") if p and not TRACKING_PARAMS.fullmatch(p)]
    out = base + ("?" + "&".join(params) if params else "")
    return out + ("#" + frag if frag else "")


def strip_tracking_in_text(text: str) -> str:
    return MD_LINK.sub(lambda m: f"[{m.group(1)}]({strip_tracking(m.group(2))})", text)


def citations_to_footnotes(body: str) -> str:
    """'문장 ([site.com](url))' 형태의 인용을 kramdown 각주 [^n] 로 바꾼다."""
    if not CITATION_GROUP.search(body):
        return body
    numbers: dict[str, int] = {}
    defs: list[str] = []
    # 모델이 이미 [^n] 각주를 썼다면 그 다음 번호부터
    existing = [int(n) for n in re.findall(r"\[\^(\d+)\]", body)]
    offset = max(existing) if existing else 0

    def ref_for(url: str) -> str:
        url = strip_tracking(url)
        if url not in numbers:
            numbers[url] = offset + len(numbers) + 1
            defs.append(f"[^{numbers[url]}]: <{url}>")
        return f"[^{numbers[url]}]"

    def repl(m: re.Match) -> str:
        refs = [ref_for(u) for _, u in MD_LINK.findall(m.group(1))]
        return "".join(dict.fromkeys(refs))  # 같은 그룹 안의 중복 제거

    # 앞 공백 + 인용 그룹 → 각주 (문장 부호 바로 뒤에 붙도록)
    new_body = re.sub(r"[ \t]*" + CITATION_GROUP.pattern, repl, body)
    if defs:
        new_body = new_body.rstrip() + "\n\n" + "\n".join(defs) + "\n"
    return new_body


def _split_sentences(paragraph: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+(?=\S)", paragraph.strip())
    return [p for p in parts if p]


def remove_closing_offers(body: str) -> str:
    """글 끝부분의 '원하시면 … 해 드릴게요' 류 문장을 제거한다 (마지막 3개 문단만 검사)."""
    lines = body.rstrip().split("\n")
    # 각주 정의 블록은 건드리지 않도록 분리
    tail_defs: list[str] = []
    while lines and re.match(r"^\[\^\d+\]:", lines[-1]):
        tail_defs.insert(0, lines.pop())
    while lines and not lines[-1].strip():
        lines.pop()
    text = "\n".join(lines)
    paras = text.split("\n\n")
    checked = 0
    for i in range(len(paras) - 1, -1, -1):
        p = paras[i]
        if not p.strip():
            continue
        if "```" in p:
            break
        checked += 1
        if checked > 6:
            break
        if OFFER_TRIGGER.search(p) and OFFER_VERB.search(p):
            if p.lstrip().startswith(("-", "*", "#", ">", "|")) or "\n" in p.strip():
                kept_lines = [ln for ln in p.split("\n")
                              if not (OFFER_TRIGGER.search(ln) and OFFER_VERB.search(ln))]
                paras[i] = "\n".join(kept_lines)
            else:
                kept = [s for s in _split_sentences(p)
                        if not (OFFER_TRIGGER.search(s) and OFFER_VERB.search(s))]
                paras[i] = " ".join(kept)
    text = "\n\n".join(p for p in paras if p.strip())
    if tail_defs:
        text = text.rstrip() + "\n\n" + "\n".join(tail_defs)
    return text.rstrip() + "\n"


def clean_title(title: str) -> str:
    t = title.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        t = t[1:-1].strip()
    t = re.sub(r"^#+\s*", "", t)
    t = TITLE_STAMP.sub(" ", t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([:：,，])", r"\1", t)          # "만들기 : SSE" → "만들기: SSE"
    t = re.sub(r"([:：,，])\s*([:：,，])", r"\1", t)  # 중복 구두점 정리
    return t.strip(" :：,，-–—")


def clean_body(body: str) -> str:
    b = body.replace("\r\n", "\n").strip()
    # 모델이 front matter를 넣었으면 제거 (수평선 '---' 과 구분: key: value 줄이 있어야 front matter)
    if b.startswith("---\n"):
        end = b.find("\n---", 4)
        block = b[4:end] if end != -1 else ""
        if end != -1 and end < 800 and re.search(r"^\w+:\s", block, re.M):
            b = b[end + 4:].lstrip()
    b = re.sub(r"^#\s+[^\n]+\n+", "", b, count=1)
    b = re.sub(r"^```(?:markdown|md)\s*\n(.*)\n```\s*$", r"\1", b, flags=re.S)
    b = strip_tracking_in_text(b)
    b = citations_to_footnotes(b)
    b = remove_closing_offers(b)
    b = re.sub(r"\n{3,}", "\n\n", b)
    return b.strip() + "\n"


def sanitize_slug(slug: str, fallback: str = "post") -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (slug or "").lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)[:60].strip("-")
    return s or fallback


def sanitize_tags(tags) -> list[str]:
    out: list[str] = []
    for t in tags or []:
        t = re.sub(r"[^a-z0-9.+#-]", "", str(t).lower().strip().replace(" ", "-")).strip("-")
        if t and t not in out and t != "trend":
            out.append(t)
    return out[:6]


KNOWN_CASING = {
    "api": "API", "rag": "RAG", "llm": "LLM", "mlops": "MLOps", "devops": "DevOps", "ci/cd": "CI/CD",
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL", "mysql": "MySQL", "sql": "SQL", "nosql": "NoSQL",
    "kubernetes": "Kubernetes", "k8s": "Kubernetes", "graphql": "GraphQL", "grpc": "gRPC", "ios": "iOS",
    "javascript": "JavaScript", "typescript": "TypeScript", "nodejs": "Node.js", "node.js": "Node.js",
    "aws": "AWS", "gcp": "GCP", "azure": "Azure", "oss": "OSS", "ai": "AI", "ml": "ML", "ui": "UI", "ux": "UX",
    "mcp": "MCP", "sdk": "SDK", "cli": "CLI", "os": "OS", "http": "HTTP", "http/3": "HTTP/3", "tls": "TLS",
}


def sanitize_subcategory(sub: str, fallback: str) -> str:
    s = re.sub(r"[^A-Za-z0-9 .+/-]", "", (sub or "")).strip()
    s = re.sub(r"\s+", " ", s)[:30].strip(" .-/")
    if not s:
        return fallback
    if s.lower() in KNOWN_CASING:
        return KNOWN_CASING[s.lower()]
    return s if any(ch.isupper() for ch in s) else s[:1].upper() + s[1:]


def yaml_str(s: str) -> str:
    """YAML 큰따옴표 스칼라 (JSON 문자열은 YAML의 부분집합)."""
    return json.dumps(s, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 5) 파일 생성
# ---------------------------------------------------------------------------

def post_timestamp(now: datetime, index: int, num_posts: int) -> datetime:
    """같은 날 여러 글이 1분 간격으로 몰리지 않도록 앞선 글을 몇 시간 앞으로 배치."""
    rng = random.Random(f"{now:%Y-%m-%d}-{index}")
    hours_back = (num_posts - 1 - index) * 3 + rng.randint(0, 45) / 60
    ts = now - timedelta(hours=hours_back)
    if ts.date() != now.date():
        ts = now.replace(hour=0, minute=rng.randint(5, 50), second=rng.randint(0, 59))
    return ts


def create_post_file(post: dict, cand: dict, ts: datetime, taken_slugs: set[str]) -> tuple[str, dict]:
    title = clean_title(post.get("title") or cand["topic"])
    description = re.sub(r"\s+", " ", (post.get("description") or "")).strip()
    body = clean_body(post.get("body_markdown") or "")
    if len(body.strip()) < 500:
        raise ValueError("본문이 비어 있거나 너무 짧습니다")

    slug = sanitize_slug(post.get("slug"),
                         fallback=sanitize_slug("-".join(cand.get("keywords") or [])[:60]))
    base, n = slug, 2
    while slug in taken_slugs:
        slug = f"{base}-{n}"
        n += 1
    taken_slugs.add(slug)

    domain = post.get("category") if post.get("category") in DOMAINS else cand["domain"]
    if cand["type"] == "news":
        categories = ["News", domain]
    else:
        categories = [domain, sanitize_subcategory(post.get("subcategory"), fallback=domain)]
    tags = sanitize_tags(post.get("tags")) or sanitize_tags(cand.get("keywords"))

    date_str = ts.strftime("%Y-%m-%d")
    lines = ["---", f"title: {yaml_str(title)}"]
    if description:
        lines.append(f"description: {yaml_str(description)}")
    lines += [
        f"date: {ts:%Y-%m-%d %H:%M:%S %z}",
        f"categories: [{', '.join(yaml_str(c) for c in categories)}]",   # 숫자/불리언처럼 보이는 값도 문자열로
        f"tags: [{', '.join(yaml_str(t) for t in tags)}]",
        "render_with_liquid: false",
        "---",
        "",
    ]
    front_matter = "\n".join(lines)

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{date_str}-{slug}.md"
    (POSTS_DIR / filename).write_text(front_matter + "\n" + body.rstrip() + "\n\n" + GA_TAG,
                                      encoding="utf-8")

    entry = {
        "date": date_str,
        "type": cand["type"],
        "domain": domain,
        "title": title,
        "slug": slug,
        "keywords": normalize_keywords((cand.get("keywords") or []) + tags),
    }
    print(f"✅ 포스트 생성: {filename}")
    print(f"   제목: {title}")
    print(f"   분류: {categories} / tags: {tags} / 본문 {len(body):,}자")
    return filename, entry


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        return 1

    # 장문 생성은 수 분이 걸린다. 타임아웃 재시도는 전체 호출을 다시 하므로 1회로 제한.
    client = OpenAI(api_key=api_key, timeout=1800, max_retries=1)
    num_posts = max(1, int(os.environ.get("NUM_POSTS", "2") or 2))
    now = datetime.now(KST)
    try:
        history = load_history()
    except (ValueError, OSError) as e:
        print(f"❌ post_history.json 을 읽을 수 없습니다 (덮어쓰기 방지를 위해 중단): {e}")
        return 1

    print("🚀 최신 IT 뉴스/기술 포스트 생성 시작")
    print("=" * 60)
    print(f"📅 {now:%Y-%m-%d %H:%M} KST / model={MODEL} / posts={num_posts}")

    print("\n🔎 [1/3] 글감 후보 수집 (web search)")
    try:
        cands = discover_topics(client, now, history)
    except Exception as e:  # noqa: BLE001
        print(f"❌ 후보 수집 실패: {type(e).__name__}: {e}")
        return 1
    if not cands:
        print("❌ 후보가 없습니다.")
        return 1
    for c in cands:
        print(f"   - [{c['type']:4}] [{c['domain']:<14}] {c['topic'][:70]}")

    print("\n🎯 [2/3] 주제 선택")
    selected = select_topics(cands, now, history, num_posts)
    if not selected:
        print("❌ 선택 가능한 주제가 없습니다.")
        return 1
    for c in selected:
        print(f"   ✔ [{c['type']}] [{c['domain']}] {c['topic'][:70]}")

    print("\n✍️  [3/3] 글 작성")
    taken = existing_slugs(POSTS_DIR)
    generated: list[str] = []
    for i, cand in enumerate(selected):
        print(f"\n📝 [{i + 1}/{len(selected)}] {cand['topic'][:70]}")
        try:
            post = write_post(client, cand, history, now)
            ts = post_timestamp(now, i, len(selected))
            filename, entry = create_post_file(post, cand, ts, taken)
            generated.append(filename)
            history.append(entry)
        except Exception as e:  # noqa: BLE001
            print(f"❌ 오류 발생: {type(e).__name__}: {str(e)[:300]}")
            continue

    save_history(history, now)
    print("\n" + "=" * 60)
    print(f"🎉 완료! {len(generated)}개 포스트 생성됨:")
    for f in generated:
        print(f"   - {f}")
    return 0 if generated else 1


if __name__ == "__main__":
    sys.exit(main())
