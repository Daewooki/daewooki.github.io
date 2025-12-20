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
    # Backend
    {"category": "Backend", "subcategory": "Python", "topics": [
        "Python 비동기 프로그래밍 패턴",
        "FastAPI 성능 최적화 팁",
        "Python 메모리 관리와 가비지 컬렉션",
        "Pydantic v2 마이그레이션 가이드",
        "SQLAlchemy 2.0 새로운 기능들",
    ]},
    {"category": "Backend", "subcategory": "Database", "topics": [
        "PostgreSQL 쿼리 최적화 기법",
        "Redis 캐싱 전략",
        "데이터베이스 인덱싱 베스트 프랙티스",
        "MongoDB vs PostgreSQL 선택 기준",
    ]},
    # Infrastructure
    {"category": "Infrastructure", "subcategory": "AWS", "topics": [
        "AWS Lambda 콜드 스타트 최적화",
        "ECS vs EKS 비교 분석",
        "AWS 비용 모니터링 자동화",
        "S3 버킷 보안 설정 가이드",
    ]},
    {"category": "Infrastructure", "subcategory": "Docker", "topics": [
        "Docker 이미지 사이즈 최적화",
        "Docker 보안 베스트 프랙티스",
        "멀티스테이지 빌드 활용법",
    ]},
    {"category": "Infrastructure", "subcategory": "Kubernetes", "topics": [
        "Kubernetes 리소스 관리 전략",
        "Helm 차트 작성 가이드",
        "K8s Ingress 설정 패턴",
    ]},
    # AI
    {"category": "AI", "subcategory": "LLM", "topics": [
        "프롬프트 엔지니어링 기법",
        "RAG 시스템 성능 향상 방법",
        "LLM 파인튜닝 vs RAG 선택 기준",
        "LangChain Expression Language 활용",
        "Vector DB 비교 분석",
    ]},
    {"category": "AI", "subcategory": "MLOps", "topics": [
        "ML 모델 버전 관리 전략",
        "모델 서빙 인프라 구축",
        "A/B 테스트로 모델 성능 비교",
    ]},
    # DevOps
    {"category": "DevOps", "subcategory": "CICD", "topics": [
        "GitHub Actions 고급 활용법",
        "ArgoCD로 GitOps 구현하기",
        "테스트 자동화 전략",
        "배포 롤백 전략",
    ]},
    # Career
    {"category": "Career", "subcategory": "Growth", "topics": [
        "시니어 개발자로 성장하는 방법",
        "효율적인 코드 리뷰 문화",
        "개발자 번아웃 예방법",
        "기술 면접 준비 가이드",
        "사이드 프로젝트 시작하기",
    ]},
]

SYSTEM_PROMPT = """당신은 10년 경력의 시니어 백엔드/인프라 개발자입니다.
기술 블로그 글을 작성하는 전문가로, 다음 원칙을 따릅니다:

1. 실무에서 바로 적용 가능한 내용 위주로 작성
2. 코드 예제는 실제 동작하는 코드로 제공
3. 초보자도 이해할 수 있도록 친절하게 설명
4. 단순 나열이 아닌 Why와 How를 설명
5. 이모지를 적절히 사용하여 가독성 향상
6. 한국어로 작성하되, 기술 용어는 영어 병기

글의 구조:
- 도입부: 왜 이 주제가 중요한지
- 본문: 핵심 내용 (코드 예제 포함)
- 실전 팁: 실무에서 주의할 점
- 마무리: 요약 및 다음 단계 안내
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
    
    user_prompt = f"""다음 주제로 기술 블로그 포스트를 작성해주세요:

주제: {topic_data['topic']}
카테고리: {topic_data['category']} > {topic_data['subcategory']}

요구사항:
1. 마크다운 형식으로 작성
2. 1500~2500자 분량
3. 최소 2개 이상의 코드 예제 포함
4. 실무 경험을 바탕으로 한 팁 포함
5. Front matter는 제외하고 본문만 작성

글 제목도 함께 제안해주세요. (첫 줄에 # 제목 형식으로)
"""

    # OpenAI 최신 모델 사용 (2025년 12월)
    # https://platform.openai.com/docs/models/gpt-5.2
    response = client.chat.completions.create(
        model="gpt-5.2",  # 최신 GPT-5.2 모델
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=4000,
        temperature=0.7
    )
    
    return response.choices[0].message.content

def create_post_file(topic_data: dict, content: str):
    """마크다운 파일 생성"""
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    time_str = today.strftime("%Y-%m-%d %H:%M:%S +0900")
    
    # 제목 추출 (첫 번째 # 헤더에서)
    lines = content.strip().split('\n')
    title = topic_data['topic']
    body = content
    
    for i, line in enumerate(lines):
        if line.startswith('# '):
            title = line[2:].strip()
            body = '\n'.join(lines[i+1:]).strip()
            break
    
    # 파일명 생성 (한글 제거, 공백을 하이픈으로)
    import re
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', title.lower())
    slug = re.sub(r'\s+', '-', slug).strip('-')[:50]
    
    if not slug:
        slug = f"post-{date_str}"
    
    filename = f"{date_str}-{slug}.md"
    
    # 태그 생성
    tags = [
        topic_data['category'].lower(),
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
    filepath = os.path.join(posts_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(front_matter + body)
    
    print(f"✅ 포스트 생성 완료: {filename}")
    return filename

def main():
    # API 키 확인
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        return
    
    print("🚀 블로그 포스트 자동 생성 시작...")
    
    # 1. 랜덤 주제 선택
    topic_data = get_random_topic()
    print(f"📝 선택된 주제: {topic_data['topic']}")
    print(f"   카테고리: {topic_data['category']} > {topic_data['subcategory']}")
    
    # 2. LLM으로 내용 생성
    print("🤖 LLM으로 내용 생성 중...")
    content = generate_post_content(topic_data)
    
    # 3. 파일 저장
    filename = create_post_file(topic_data, content)
    
    print(f"🎉 완료! 새 포스트가 생성되었습니다: {filename}")

if __name__ == "__main__":
    main()

