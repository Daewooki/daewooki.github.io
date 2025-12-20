#!/usr/bin/env python3
"""
LLM을 이용한 자동 블로그 포스트 생성 스크립트
"""

import os
import random
from datetime import datetime
from openai import OpenAI

# 주제 목록 - 원하는 주제를 추가/수정하세요
TOPICS = [
    # Vibe Coding & AI 개발
    {"category": "AI", "subcategory": "VibeCoding", "topics": [
        "바이브코딩으로 생산성 10배 올리는 방법",
        "Cursor IDE 완벽 활용 가이드",
        "AI와 함께 코딩하는 시대의 개발자 역할",
        "프롬프트 엔지니어링으로 더 나은 코드 만들기",
        "AI 코딩 어시스턴트 비교 분석 (Cursor vs Copilot vs Claude)",
        "바이브코딩 시대의 코드 리뷰 전략",
        "AI로 레거시 코드 리팩토링하기",
    ]},
    # Backend
    {"category": "Backend", "subcategory": "Python", "topics": [
        "Python 비동기 프로그래밍 패턴",
        "FastAPI 성능 최적화 팁",
        "Python 메모리 관리와 가비지 컬렉션",
        "Pydantic v2 마이그레이션 가이드",
        "SQLAlchemy 2.0 새로운 기능들",
        "Python 타입 힌트 완벽 가이드",
        "Poetry로 Python 프로젝트 관리하기",
    ]},
    {"category": "Backend", "subcategory": "Database", "topics": [
        "PostgreSQL 쿼리 최적화 기법",
        "Redis 캐싱 전략",
        "데이터베이스 인덱싱 베스트 프랙티스",
        "MongoDB vs PostgreSQL 선택 기준",
        "데이터베이스 트랜잭션 격리 수준 이해하기",
    ]},
    # Infrastructure
    {"category": "Infrastructure", "subcategory": "AWS", "topics": [
        "AWS Lambda 콜드 스타트 최적화",
        "ECS vs EKS 비교 분석",
        "AWS 비용 모니터링 자동화",
        "S3 버킷 보안 설정 가이드",
        "AWS IAM 권한 관리 베스트 프랙티스",
    ]},
    {"category": "Infrastructure", "subcategory": "Docker", "topics": [
        "Docker 이미지 사이즈 최적화",
        "Docker 보안 베스트 프랙티스",
        "멀티스테이지 빌드 활용법",
        "Docker Compose 고급 활용법",
    ]},
    {"category": "Infrastructure", "subcategory": "Kubernetes", "topics": [
        "Kubernetes 리소스 관리 전략",
        "Helm 차트 작성 가이드",
        "K8s Ingress 설정 패턴",
        "Kubernetes 모니터링 스택 구축",
    ]},
    # AI
    {"category": "AI", "subcategory": "LLM", "topics": [
        "프롬프트 엔지니어링 기법",
        "RAG 시스템 성능 향상 방법",
        "LLM 파인튜닝 vs RAG 선택 기준",
        "LangChain Expression Language 활용",
        "Vector DB 비교 분석",
        "LLM 애플리케이션 평가 방법",
    ]},
    {"category": "AI", "subcategory": "MLOps", "topics": [
        "ML 모델 버전 관리 전략",
        "모델 서빙 인프라 구축",
        "A/B 테스트로 모델 성능 비교",
        "Feature Store 구축 가이드",
    ]},
    # DevOps
    {"category": "DevOps", "subcategory": "CICD", "topics": [
        "GitHub Actions 고급 활용법",
        "ArgoCD로 GitOps 구현하기",
        "테스트 자동화 전략",
        "배포 롤백 전략",
        "모노레포 CI/CD 구성하기",
    ]},
    # Career
    {"category": "Career", "subcategory": "Growth", "topics": [
        "시니어 개발자로 성장하는 방법",
        "효율적인 코드 리뷰 문화",
        "개발자 번아웃 예방법",
        "기술 면접 준비 가이드",
        "사이드 프로젝트 시작하기",
        "개발자의 효과적인 문서화 방법",
    ]},
]

# 기존 블로그 포스트 스타일에 맞춘 시스템 프롬프트
SYSTEM_PROMPT = """당신은 10년 경력의 시니어 백엔드/인프라 개발자입니다.
기술 블로그 글을 작성하는 전문가로, 아래 형식과 스타일을 정확히 따라야 합니다.

## 글 구조 (반드시 이 순서로 작성)

1. **## 들어가며** - 주제 소개와 왜 중요한지 2-3문장으로 설명

2. **---** (구분선)

3. **## 📁 또는 🎯 메인 섹션** - 핵심 개념 설명 (이모지 + 제목)

4. **---** (구분선)

5. **## 🔑 또는 💻 코드 섹션** - 실제 동작하는 코드 예제
   - ### 1. 첫 번째 예제
   - ### 2. 두 번째 예제
   - 각 예제마다 설명 + 코드 블록

6. **---** (구분선)

7. **## 💡 실전 팁** 또는 **Best Practices**
   - 번호 매기기 (### 1. xxx)
   - 짧은 코드 스니펫 포함

8. **---** (구분선)

9. **## 🚀 마무리**
   - 핵심 요약 2-3문장
   - "다음 글에서는 [관련 주제]를 다뤄보겠습니다!" 로 끝내기

## 작성 규칙

1. 한국어로 작성하되, 기술 용어는 영어 그대로 사용
2. 코드 블록에는 반드시 언어 명시 (```python, ```yaml 등)
3. 코드는 실제 동작하는 완전한 코드로 작성
4. 각 섹션 사이에 반드시 **---** 구분선 넣기
5. 이모지는 헤더에만 사용 (📁, 🔑, 💡, 🚀, 🎯, 💻, ⚙️, 📋 등)
6. 글 분량: 1500-2500자 (코드 제외)
7. 최소 3개 이상의 코드 블록 포함

## 금지 사항
- "안녕하세요", "감사합니다" 등 인사말 금지
- Front matter (---로 시작하는 메타데이터) 금지 - 본문만 작성
- 마크다운 제목에 # 하나짜리 사용 금지 (## 부터 시작)
"""

# 사용자 프롬프트 템플릿
USER_PROMPT_TEMPLATE = """다음 주제로 기술 블로그 포스트를 작성해주세요:

**주제**: {topic}
**카테고리**: {category} > {subcategory}

위 시스템 프롬프트의 구조와 스타일을 정확히 따라서 작성하세요.
특히:
1. "## 들어가며"로 시작
2. 각 섹션 사이에 --- 구분선
3. 이모지 헤더 사용
4. 실제 동작하는 코드 예제 3개 이상
5. "## 🚀 마무리"로 끝내고 다음 글 예고

**첫 줄에 글 제목을 작성하세요** (예: "FastAPI 성능 최적화 완벽 가이드")
제목 다음 줄부터 바로 "## 들어가며" 시작
"""


def get_random_topic():
    """랜덤 주제 선택"""
    category_data = random.choice(TOPICS)
    topic = random.choice(category_data["topics"])
    return {
        "category": category_data["category"],
        "subcategory": category_data["subcategory"],
        "topic": topic
    }


def generate_post_content(topic_data: dict) -> str:
    """OpenAI API를 사용하여 포스트 내용 생성"""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    user_prompt = USER_PROMPT_TEMPLATE.format(
        topic=topic_data['topic'],
        category=topic_data['category'],
        subcategory=topic_data['subcategory']
    )

    # OpenAI GPT-5.2 API 호출
    # https://platform.openai.com/docs/models/gpt-5.2
    response = client.chat.completions.create(
        model="gpt-5.2",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        max_completion_tokens=6000,  # 충분한 토큰으로 완성도 높은 글 생성
        temperature=0.7,  # 적당한 창의성 (0.5-0.8 권장)
    )
    
    return response.choices[0].message.content


def create_post_file(topic_data: dict, content: str):
    """마크다운 파일 생성"""
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    time_str = today.strftime("%Y-%m-%d %H:%M:%S +0900")
    
    # 제목 추출 (첫 번째 줄에서)
    lines = content.strip().split('\n')
    title = topic_data['topic']
    body = content
    
    # 첫 줄이 제목인 경우 추출
    first_line = lines[0].strip()
    if first_line and not first_line.startswith('#'):
        title = first_line.strip('"').strip("'").strip()
        body = '\n'.join(lines[1:]).strip()
    elif first_line.startswith('# '):
        title = first_line[2:].strip()
        body = '\n'.join(lines[1:]).strip()
    
    # 파일명 생성 (한글 제거, 공백을 하이픈으로)
    import re
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', title.lower())
    slug = re.sub(r'\s+', '-', slug).strip('-')[:50]
    
    if not slug:
        slug = f"post-{date_str}"
    
    filename = f"{date_str}-{slug}.md"
    
    # 태그 생성 (소문자, 하이픈으로 연결)
    tags = [
        topic_data['category'].lower().replace(' ', '-'),
        topic_data['subcategory'].lower().replace(' ', '-')
    ]
    
    # Front matter 생성
    front_matter = f"""---
title: "{title}"
date: {time_str}
categories: [{topic_data['category']}, {topic_data['subcategory']}]
tags: [{', '.join(tags)}]
---

"""
    
    # 파일 저장
    posts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '_posts')
    os.makedirs(posts_dir, exist_ok=True)
    filepath = os.path.join(posts_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(front_matter + body)
    
    print(f"✅ 포스트 생성 완료: {filename}")
    return filename


def get_topic_by_keyword(keyword: str) -> dict:
    """키워드로 관련 주제 찾기 또는 직접 주제로 사용"""
    keyword_lower = keyword.lower()
    
    # 키워드가 포함된 주제 찾기
    for category_data in TOPICS:
        for topic in category_data["topics"]:
            if keyword_lower in topic.lower():
                return {
                    "category": category_data["category"],
                    "subcategory": category_data["subcategory"],
                    "topic": topic
                }
    
    # 못 찾으면 입력값을 직접 주제로 사용 (AI > Custom 카테고리)
    return {
        "category": "AI",
        "subcategory": "Insight",
        "topic": keyword
    }


def main():
    # API 키 확인
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        return
    
    print("🚀 블로그 포스트 자동 생성 시작...")
    
    # 환경변수에서 특정 주제 확인 (없으면 랜덤)
    custom_topic = os.environ.get("POST_TOPIC", "").strip()
    
    if custom_topic:
        # 특정 주제로 생성
        topic_data = get_topic_by_keyword(custom_topic)
        print(f"📝 지정된 주제: {topic_data['topic']}")
    else:
        # 랜덤 주제 선택
        topic_data = get_random_topic()
        print(f"📝 랜덤 선택된 주제: {topic_data['topic']}")
    
    print(f"   카테고리: {topic_data['category']} > {topic_data['subcategory']}")
    
    # 2. LLM으로 내용 생성
    print("🤖 LLM으로 내용 생성 중...")
    content = generate_post_content(topic_data)
    
    # 3. 파일 저장
    filename = create_post_file(topic_data, content)
    
    print(f"🎉 완료! 새 포스트가 생성되었습니다: {filename}")


if __name__ == "__main__":
    main()
