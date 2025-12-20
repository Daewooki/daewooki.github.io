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

# 검색할 카테고리 정의
SEARCH_CATEGORIES = [
    {
        "category": "AI",
        "subcategory": "Trend",
        "search_query": "2025년 AI 인공지능 LLM 최신 뉴스 트렌드 기술 발표",
        "focus": "AI, LLM, 머신러닝, 딥러닝 관련 최신 소식"
    },
    {
        "category": "Backend",
        "subcategory": "Trend",
        "search_query": "2025년 백엔드 개발 최신 기술 트렌드 프레임워크",
        "focus": "백엔드 개발, API, 데이터베이스, 서버 관련 최신 기술"
    },
    {
        "category": "DevOps",
        "subcategory": "Trend",
        "search_query": "2025년 DevOps 클라우드 쿠버네티스 최신 트렌드",
        "focus": "DevOps, CI/CD, 클라우드, 컨테이너 관련 최신 소식"
    },
    {
        "category": "Infrastructure",
        "subcategory": "Trend",
        "search_query": "2025년 클라우드 AWS 인프라 최신 기술 발표",
        "focus": "AWS, GCP, Azure 클라우드 인프라 최신 소식"
    },
]

# 블로그 글 작성 프롬프트
BLOG_WRITER_PROMPT = """당신은 10년 경력의 시니어 개발자이자 기술 블로거입니다.
웹 검색 결과를 바탕으로 기술 블로그 포스트를 작성합니다.

## 글 구조 (반드시 이 순서로 작성)

1. **## 들어가며** - 이 주제가 왜 지금 핫한지 2-3문장으로 설명

2. **---** (구분선)

3. **## 🔍 핵심 내용** - 검색 결과에서 얻은 주요 정보 정리
   - 구체적인 수치, 날짜, 이름 포함
   - 출처 명시 (가능한 경우)

4. **---** (구분선)

5. **## 💻 실무 적용** - 개발자가 알아야 할 점, 코드 예제 (해당되는 경우)

6. **---** (구분선)

7. **## 💡 인사이트** - 이 트렌드가 의미하는 바, 앞으로의 전망

8. **---** (구분선)

9. **## 🚀 마무리**
   - 핵심 요약 2-3문장
   - 독자에게 액션 아이템 제안

## 작성 규칙
1. 한국어로 작성, 기술 용어는 영어 그대로
2. 검색 결과의 **구체적인 정보**를 인용 (날짜, 버전, 수치 등)
3. 단순 나열이 아닌 **분석과 인사이트** 포함
4. 이모지는 헤더에만 사용
5. 글 분량: 1500-2500자
6. 코드 블록은 ```언어명 형식으로

## 금지 사항
- "안녕하세요", "감사합니다" 인사말 금지
- Front matter 금지 (본문만 작성)
- # 하나짜리 제목 금지 (## 부터 시작)
- 검색 결과에 없는 내용 지어내기 금지
"""


def search_and_generate_post(client: OpenAI, category_info: dict) -> tuple[str, str]:
    """웹 검색 후 블로그 포스트 생성"""
    
    print(f"🔍 '{category_info['search_query']}' 검색 중...")
    
    # GPT-5.2 + 웹 검색 도구로 최신 정보 검색 및 글 작성
    response = client.responses.create(
        model="gpt-5.2",
        tools=[{"type": "web_search"}],
        input=f"""다음 주제에 대해 웹 검색을 수행하고, 검색 결과를 바탕으로 기술 블로그 포스트를 작성해주세요.

검색 주제: {category_info['search_query']}
집중 분야: {category_info['focus']}

요구사항:
1. 먼저 웹 검색으로 최신 정보를 수집하세요
2. 검색 결과에서 가장 흥미롭고 중요한 내용을 선별하세요
3. 위 시스템 프롬프트의 구조에 맞게 블로그 글을 작성하세요
4. 첫 줄에 매력적인 제목을 작성하세요 (예: "OpenAI GPT-5 출시, 개발자가 알아야 할 5가지")

{BLOG_WRITER_PROMPT}
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
        f.write(front_matter + body)
    
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
    
    # 오늘 날짜 기반으로 카테고리 선택 (매일 다른 조합)
    today = datetime.now()
    day_of_year = today.timetuple().tm_yday
    
    # 2개의 다른 카테고리 선택
    selected_categories = []
    for i in range(num_posts):
        idx = (day_of_year + i) % len(SEARCH_CATEGORIES)
        if SEARCH_CATEGORIES[idx] not in selected_categories:
            selected_categories.append(SEARCH_CATEGORIES[idx])
    
    # 부족하면 추가
    for cat in SEARCH_CATEGORIES:
        if len(selected_categories) >= num_posts:
            break
        if cat not in selected_categories:
            selected_categories.append(cat)
    
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
