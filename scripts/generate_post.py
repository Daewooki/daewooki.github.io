#!/usr/bin/env python3
"""
LLM 웹 검색을 이용한 최신 트렌드 기반 블로그 포스트 자동 생성
- OpenAI GPT-5.2 + Web Search 도구 활용
- 매일 2개 카테고리의 최신 트렌드 포스트 생성
"""

import os
import re
from datetime import datetime
from openai import OpenAI

# 포스트 본문에 삽입될 조회수 위젯(정적 사이트용)
# - 페이지 진입 시 페이지별/전체 조회수를 카운트하고 숫자를 표시합니다.
PAGEVIEWS_WIDGET = """<div class="pageviews" style="margin: 0.25rem 0 1rem; opacity: 0.8;">
  <span style="font-weight: 600;">조회수</span>: <span id="pv-post">-</span>
</div>
<script defer src="/assets/js/pageviews.js"></script>

"""

# 검색할 카테고리 정의
# type: "news" = 뉴스/트렌드 (시사점 중심), "tech" = 기술 심층 (코드/구현 중심)
SEARCH_CATEGORIES = [
    {
        "category": "AI",
        "subcategory": "News",
        "type": "news",
        "search_query": "2025년 12월 AI 인공지능 LLM 최신 뉴스 발표 출시",
        "focus": "AI/LLM 업계 최신 뉴스, 신규 모델 출시, 기업 발표"
    },
    {
        "category": "AI",
        "subcategory": "Tutorial",
        "type": "tech",
        "search_query": "2025년 LLM RAG 에이전트 구현 방법 튜토리얼",
        "focus": "LLM 활용 개발, RAG 구현, AI 에이전트 개발 기술"
    },
    {
        "category": "Backend",
        "subcategory": "Tutorial",
        "type": "tech",
        "search_query": "2025년 FastAPI Python 백엔드 개발 베스트 프랙티스",
        "focus": "FastAPI, Django, 백엔드 아키텍처, API 설계"
    },
    {
        "category": "DevOps",
        "subcategory": "News",
        "type": "news",
        "search_query": "2025년 12월 쿠버네티스 Docker 클라우드 최신 뉴스",
        "focus": "Kubernetes, Docker, 클라우드 네이티브 업계 동향"
    },
    {
        "category": "DevOps",
        "subcategory": "Tutorial",
        "type": "tech",
        "search_query": "2025년 GitHub Actions CI/CD 파이프라인 구축 방법",
        "focus": "CI/CD 파이프라인, GitHub Actions, 자동화 구현"
    },
    {
        "category": "Infrastructure",
        "subcategory": "News",
        "type": "news",
        "search_query": "2025년 12월 AWS 클라우드 신규 서비스 발표",
        "focus": "AWS, GCP, Azure 신규 서비스, 클라우드 업계 동향"
    },
]

# 뉴스/트렌드 글 프롬프트 (시사점, 업계 영향 중심)
NEWS_PROMPT = """당신은 10년 경력의 시니어 개발자이자 기술 블로거입니다.
웹 검색 결과를 바탕으로 **뉴스/트렌드 분석 글**을 작성합니다.

## 글 구조 (반드시 이 순서로 작성)

1. **## 들어가며** - 무슨 일이 있었는지 핵심 요약 (2-3문장)

2. **---**

3. **## 📰 무슨 일이 있었나** - 뉴스의 구체적 내용
   - 날짜, 기업명, 제품명 등 팩트 중심
   - 검색 결과에서 얻은 구체적 정보
   
4. **---**

5. **## 🔍 왜 중요한가** - 이 뉴스가 개발자에게 미치는 영향
   - 기존 대비 무엇이 달라지는지
   - 개발자가 주목해야 할 포인트
   
6. **---**

7. **## 💡 시사점과 전망** - 업계 전체에 미치는 영향
   - 경쟁사/업계 반응
   - 앞으로의 예상 시나리오
   
8. **---**

9. **## 🚀 마무리** - 핵심 요약 + 개발자에게 권장 액션

## 작성 규칙
- 한국어로 작성, 기술 용어는 영어 그대로
- **팩트 중심**: 날짜, 버전, 수치, 기업명 명시
- **분석 중심**: 단순 전달이 아닌 "왜 중요한지" 해석
- 글 분량: 1200-2000자
- 이모지는 헤더에만 사용

## 금지 사항
- 인사말 금지, Front matter 금지, # 제목 금지
- 검색 결과에 없는 내용 지어내기 금지
"""

# 기술 딥다이브 프롬프트 (코드, 구현 방법 중심)
TECH_PROMPT = """당신은 10년 경력의 시니어 개발자이자 기술 블로거입니다.
웹 검색 결과를 바탕으로 **기술 심층 분석/튜토리얼 글**을 작성합니다.

## 글 구조 (반드시 이 순서로 작성)

1. **## 들어가며** - 이 기술이 왜 필요한지 배경 설명

2. **---**

3. **## 🔧 핵심 개념** - 기술의 핵심 원리 설명
   - 주요 개념 정의
   - 어떻게 작동하는지
   
4. **---**

5. **## 💻 실전 코드** - 실제 구현 예제
   - 기본 사용법 코드
   - 주석으로 설명 포함
   
```언어
# 코드 예제
```

6. **---**

7. **## ⚡ 실전 팁** - 실무에서 유용한 팁
   - Best Practice
   - 주의사항, 함정 피하기
   
8. **---**

9. **## 🚀 마무리** - 핵심 정리 + 다음 학습 추천

## 작성 규칙
- 한국어로 작성, 기술 용어는 영어 그대로
- **코드 필수**: 실행 가능한 예제 코드 포함
- **깊이 있게**: 표면적 설명이 아닌 원리까지
- 글 분량: 1500-2500자
- 코드 블록: ```언어명 형식

## 금지 사항
- 인사말 금지, Front matter 금지, # 제목 금지
- 너무 기초적인 내용만 다루기 금지
"""


def search_and_generate_post(client: OpenAI, category_info: dict) -> tuple[str, str]:
    """웹 검색 후 블로그 포스트 생성"""
    
    post_type = category_info.get('type', 'news')
    type_label = "뉴스/트렌드 분석" if post_type == "news" else "기술 심층 분석"
    prompt = NEWS_PROMPT if post_type == "news" else TECH_PROMPT
    
    print(f"🔍 [{type_label}] '{category_info['search_query']}' 검색 중...")
    
    # GPT-5.2 + 웹 검색 도구로 최신 정보 검색 및 글 작성
    response = client.responses.create(
        model="gpt-5.2",
        tools=[{"type": "web_search"}],
        input=f"""다음 주제에 대해 웹 검색을 수행하고, 검색 결과를 바탕으로 블로그 포스트를 작성해주세요.

글 유형: {type_label}
검색 주제: {category_info['search_query']}
집중 분야: {category_info['focus']}

요구사항:
1. 먼저 웹 검색으로 최신 정보를 수집하세요
2. 검색 결과에서 가장 흥미롭고 중요한 내용을 선별하세요
3. 아래 지침의 구조에 맞게 블로그 글을 작성하세요
4. 첫 줄에 매력적인 제목을 작성하세요

{prompt}
""",
        max_output_tokens=6000,
    )
    
    content = response.output_text
    
    # 제목 추출
    lines = content.strip().split('\n')
    title = category_info['focus']
    body = content
    
    first_line = lines[0].strip()
    if first_line and not first_line.startswith('#'):
        title = first_line.strip('"').strip("'").strip()
        body = '\n'.join(lines[1:]).strip()
    elif first_line.startswith('# '):
        title = first_line[2:].strip()
        body = '\n'.join(lines[1:]).strip()
    
    return title, body


def create_post_file(category_info: dict, title: str, body: str, suffix: str = "") -> str:
    """마크다운 파일 생성"""
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    time_str = today.strftime("%Y-%m-%d %H:%M:%S +0900")
    
    # 파일명 생성
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', title.lower())
    slug = re.sub(r'\s+', '-', slug).strip('-')[:40]
    
    if not slug:
        slug = f"{category_info['category'].lower()}-trend"
    
    filename = f"{date_str}-{slug}{suffix}.md"
    
    # 태그 생성
    tags = [
        category_info['category'].lower(),
        category_info['subcategory'].lower(),
        "trend",
        date_str[:7]  # 2025-12 형식
    ]
    
    # Front matter
    front_matter = f"""---
title: "{title}"
date: {time_str}
categories: [{category_info['category']}, {category_info['subcategory']}]
tags: [{', '.join(tags)}]
---

"""
    
    # 파일 저장
    posts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '_posts')
    os.makedirs(posts_dir, exist_ok=True)
    filepath = os.path.join(posts_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(front_matter + PAGEVIEWS_WIDGET + body)
    
    print(f"✅ 포스트 생성: {filename}")
    return filename


def main():
    # API 키 확인
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        return
    
    client = OpenAI(api_key=api_key)
    
    print("🚀 최신 트렌드 기반 블로그 포스트 생성 시작!")
    print("=" * 50)
    
    # 환경변수에서 카테고리 수 확인 (기본값: 2)
    num_posts = int(os.environ.get("NUM_POSTS", "2"))
    
    # 뉴스와 기술 글을 분리
    news_categories = [c for c in SEARCH_CATEGORIES if c.get('type') == 'news']
    tech_categories = [c for c in SEARCH_CATEGORIES if c.get('type') == 'tech']
    
    # 오늘 날짜 기반으로 카테고리 선택 (매일 다른 조합)
    today = datetime.now()
    day_of_year = today.timetuple().tm_yday
    
    # 뉴스 1개 + 기술 1개 조합 (2개인 경우)
    selected_categories = []
    
    if num_posts >= 1 and news_categories:
        news_idx = day_of_year % len(news_categories)
        selected_categories.append(news_categories[news_idx])
    
    if num_posts >= 2 and tech_categories:
        tech_idx = day_of_year % len(tech_categories)
        selected_categories.append(tech_categories[tech_idx])
    
    # 추가 포스트가 필요하면 순환
    remaining = num_posts - len(selected_categories)
    all_categories = news_categories + tech_categories
    for i in range(remaining):
        idx = (day_of_year + i + 2) % len(all_categories)
        if all_categories[idx] not in selected_categories:
            selected_categories.append(all_categories[idx])
    
    generated_files = []
    
    for i, category_info in enumerate(selected_categories[:num_posts]):
        print(f"\n📝 [{i+1}/{num_posts}] {category_info['category']} 카테고리 글 생성 중...")
        
        try:
            title, body = search_and_generate_post(client, category_info)
            suffix = f"-{i+1}" if num_posts > 1 else ""
            filename = create_post_file(category_info, title, body, suffix)
            generated_files.append(filename)
        except Exception as e:
            print(f"❌ 오류 발생: {e}")
            continue
    
    print("\n" + "=" * 50)
    print(f"🎉 완료! {len(generated_files)}개 포스트 생성됨:")
    for f in generated_files:
        print(f"   - {f}")


if __name__ == "__main__":
    main()
