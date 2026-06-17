---
title: "프레임을 “어떻게 볼지”가 성능을 갈라먹는다: 2026년 6월 Video AI(Understanding/Generation) 프레임 분석 파이프라인 심층 분석"
date: 2026-06-17 04:56:34 +0900
categories: [AI, Multimodal]
tags: [ai, multimodal, trend, 2026-06]
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

2026년 현재 비디오 이해(video understanding)·생성(video generation) AI를 실제 제품에 붙일 때 가장 자주 부딪히는 문제는 모델 자체보다 **“프레임을 어떤 규칙으로 뽑아 모델에 먹일지”**입니다. 긴 영상(수십 분)에서 균일 샘플링만 하면 중요한 순간을 놓치고, 반대로 FPS를 올리면 토큰/비용/지연이 터집니다. 그래서 최근 흐름은 **query(사용자 의도) 기반으로 ‘중요 구간을 먼저 찾고, 그 구간만 고해상도로 재샘플링’**하는 쪽으로 수렴합니다. 이 흐름을 잘 정리한 대표 예가 *Instructed Temporal Grounding* 기반의 VideoITG/VidThinker 파이프라인입니다. ([github.com](https://github.com/NVlabs/VideoITG))

언제 쓰면 좋나?
- 사용자 질문이 명확하고(“몇 분에 무슨 일이?”), **특정 이벤트/행동/상태 변화**를 찾아야 하는 제품(콘텐츠 검수, 스포츠 하이라이트, 공정 모니터링, 리테일 CCTV 검색)
- 모델 호출 비용이 크고, **프레임 수를 강하게 제어**해야 하는 시스템

언제 쓰면 안 되나?
- 질문 없이 “그냥 요약”처럼 **의도가 없는 범용 분석**만 필요하고, 영상도 짧은 경우(굳이 복잡한 2-stage가 과함)
- 법/컴플라이언스상 원본 프레임을 외부로 내보내기 어렵고, 온프레미스 모델도 준비 안 된 경우(파이프라인이 결국 외부 LMM 호출에 기대는 구간이 생김)

---

## 🔧 핵심 개념

### 1) 주요 개념 정의
- **Frame sampling**: 비디오를 일정 규칙으로 프레임(또는 clip) 단위로 추출하는 전략. 단순 uniform(예: 1 FPS)부터 query-aware(질문 기반)까지.
- **Temporal grounding**: “언제(시간축) 어떤 일이 일어났는가”를 **구간(start/end) 또는 keyframe**으로 특정.
- **Two-stage / multi-stage pipeline**: (1) 싸게 거칠게 훑기 → (2) 후보 구간만 비싸게 정밀 분석.

Google Gemini API 문서도 기본은 **1 FPS 샘플링**이며, 정밀한 시간 분석이 필요하면 FPS를 올리거나 클리핑 구간을 지정하라고 가이드합니다. 즉, “FPS=정답”이 아니라 **워크로드 특성에 따라 샘플링을 설계**하라는 메시지입니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/video-understanding))

### 2) 내부 작동 방식(구조/흐름)
실무에서 제일 재사용하기 좋은 형태로, 2026년식 프레임 분석 파이프라인을 “표준 형태”로 정리하면 아래입니다.

**A. Ingest/Normalize**
- 입력 영상 표준화(코덱/해상도/가변 FPS 정리), 오디오 분리, 샷 경계(shot boundary) 같은 cheap feature 계산
- 이 단계가 허술하면 이후 모델이 “프레임 누락/시간축 왜곡”에 취약해집니다(가변 FPS 영상에서 timestamp가 어긋나는 케이스가 흔함).

**B. Coarse pass (저비용 탐색)**
- 낮은 FPS(예: 0.2~1 FPS) + 간단한 caption/scene tag 생성
- 목적: “질문과 무관한 구간”을 최대한 빨리 버리기

Gemini 쪽도 “긴 영상엔 낮은 FPS(<1)”, “빠른 액션엔 높은 FPS”를 권장합니다. 결국 coarse pass에서 **낮은 FPS로 전체를 스캔**하는 설계가 자연스럽습니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/video-understanding))

**C. Candidate retrieval (구간 후보 검색)**
- coarse 결과(프레임별 caption/태그/임베딩)를 인덱싱해, query로 top-k 구간을 뽑음
- 여기서부터가 “파이프라인이 모델 문제를 흡수”하는 지점: retrieval 품질이 곧 비용/성능을 좌우

VideoITG의 VidThinker는 이 단계를 **instruction-conditioned caption 생성 → instruction-guided retrieval → fine-grained frame localization**으로 명시적으로 구조화합니다. ([github.com](https://github.com/NVlabs/VideoITG))

**D. Fine pass (고비용 정밀 분석)**
- 후보 구간에만 FPS를 올려(예: 4~8 FPS) 모델에 넣고, temporal grounding/정답 생성
- 이 단계에서 “정밀 Q&A”, “근거 프레임 제시”, “이상행동 구간 timestamp” 같은 제품 요구를 만족

**E. (옵션) Generation**
- 이해 결과를 바탕으로 “하이라이트 생성”, “설명용 재구성 영상”, “가이드 영상 자동 생성”으로 연결
- OpenAI 쪽은 **Videos API**로 video generation job 생성/편집/extension 같은 워크플로우를 API 레벨에서 제공합니다(생성은 비동기 job 형태). ([platform.openai.com](https://platform.openai.com/docs/api-reference/videos/object?lang=go))

### 3) 다른 접근과의 차이점
- **Uniform sampling(단일 패스)**: 구현은 쉽지만 긴 영상에서 정보 손실/비용 폭발 둘 중 하나를 피하기 어렵습니다.
- **Learned adaptive sampling**: VideoBrain 같은 작업은 “한 번 잘못 뽑으면 복구 불가” 문제를 줄이려는 방향(적응적 샘플링을 학습)으로 가고 있습니다. ([catalyzex.com](https://www.catalyzex.com/paper/videobrain-learning-adaptive-frame-sampling?utm_source=openai))  
- **Instruction-aware temporal grounding(VideoITG)**: “사용자 의도에 따라 샘플링 자체를 바꾼다”를 전면에 둡니다. 즉 **질문이 곧 샘플링 정책**이 됩니다. ([github.com](https://github.com/NVlabs/VideoITG))

---

## 💻 실전 코드

아래 예제는 “보안 카메라(또는 매장 CCTV) 2시간 영상에서 **‘현금 결제대에서 물건을 가방에 넣고 결제 없이 나간 순간’** 같은 이벤트를 찾아 timestamp로 리포트”하는 시나리오입니다.

구성:
1) ffmpeg로 **coarse 프레임(1 FPS)** 추출  
2) (가정) Gemini Video Understanding로 coarse 분석(프레임 대신 video+sampling 옵션을 쓰는 형태로도 가능) ([ai.google.dev](https://ai.google.dev/gemini-api/docs/video-understanding))  
3) coarse 결과에서 후보 구간을 뽑고, 그 구간만 **8 FPS로 재추출**  
4) fine 분석으로 timestamp 확정

> 주의: 아래 코드는 “실제로 돌아가는” 형태로 작성했지만, API 키/모델명/요청 포맷은 각 제공사 SDK 버전에 따라 조금씩 다를 수 있습니다. 핵심은 **프레임 파이프라인 구조**입니다.

### 0) 의존성/셋업

```bash
# 시스템 의존성
brew install ffmpeg  # macOS 예시
# 또는 Ubuntu: sudo apt-get install -y ffmpeg

# Python
python -m venv .venv
source .venv/bin/activate
pip install google-genai==1.* pydantic==2.* numpy==1.* opencv-python==4.*
export GEMINI_API_KEY="YOUR_KEY"
```

### 1) Coarse pass: 전체를 1 FPS로 훑기(cheap)

```python
# coarse_pass.py
import os, json, subprocess
from pathlib import Path
from typing import List, Tuple
from pydantic import BaseModel

VIDEO = "cctv_2hours.mp4"
OUTDIR = Path("artifacts/coarse")
OUTDIR.mkdir(parents=True, exist_ok=True)

def extract_frames(video: str, fps: float, out_dir: Path):
    # %06d.jpg로 타임라인 정렬 쉽게
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", video,
        "-vf", f"fps={fps}",
        str(out_dir / "%06d.jpg")
    ]
    subprocess.check_call(cmd)

class CoarseHit(BaseModel):
    # coarse 단계에서는 대충 "의심 구간"만 잡습니다.
    start_sec: int
    end_sec: int
    reason: str

def heuristic_candidate_windows(total_seconds: int, window_sec: int = 60, stride_sec: int = 30) -> List[Tuple[int,int]]:
    # 실제로는 caption/embedding 기반 retrieval을 해야 하지만,
    # 예제에서는 "윈도우 단위로 묶어 LMM에 질의"하는 형태로 단순화합니다.
    out = []
    t = 0
    while t < total_seconds:
        out.append((t, min(t + window_sec, total_seconds)))
        t += stride_sec
    return out

def main():
    # 1) coarse frames
    extract_frames(VIDEO, fps=1.0, out_dir=OUTDIR)

    # 2) (여기서는 예제로) 영상 길이 추정: ffprobe로 얻는 게 정석
    total_seconds = 2 * 60 * 60  # 2h 가정

    windows = heuristic_candidate_windows(total_seconds)

    # 3) 실제 운영에서는:
    # - 각 window 대표 프레임 몇 장 + query를 LMM에 넣어 coarse 필터링
    # - 혹은 Gemini API의 video-understanding에서 fps/clipping 지정 (권장) ([ai.google.dev](https://ai.google.dev/gemini-api/docs/video-understanding))
    hits = [
        CoarseHit(start_sec=3720, end_sec=3780, reason="checkout area crowding + hand-to-bag motion suspected"),
        CoarseHit(start_sec=6150, end_sec=6210, reason="person near register + occluded hands"),
    ]

    with open("artifacts/coarse_hits.json", "w") as f:
        json.dump([h.model_dump() for h in hits], f, ensure_ascii=False, indent=2)

    print("coarse hits:", hits)

if __name__ == "__main__":
    main()
```

예상 출력:
- `artifacts/coarse/000001.jpg ...`
- `artifacts/coarse_hits.json`에 의심 구간 2개 기록

### 2) Fine pass: 후보 구간만 8 FPS로 재추출 + 정밀 temporal grounding

```python
# fine_pass.py
import json, subprocess
from pathlib import Path
from pydantic import BaseModel

VIDEO = "cctv_2hours.mp4"
HITS = "artifacts/coarse_hits.json"
OUT = Path("artifacts/fine")
OUT.mkdir(parents=True, exist_ok=True)

class FineResult(BaseModel):
    start_sec: float
    end_sec: float
    confidence: float
    evidence: str  # 어떤 근거(프레임/행동)인지 요약

def extract_clip_frames(video: str, start: int, end: int, fps: float, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    # -ss/-to로 구간 자르고 fps 올려 추출
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", str(start), "-to", str(end),
        "-i", video,
        "-vf", f"fps={fps}",
        str(out_dir / "%06d.jpg")
    ]
    subprocess.check_call(cmd)

def main():
    hits = json.load(open(HITS))
    results = []

    for i, h in enumerate(hits):
        clip_dir = OUT / f"clip_{i}_{h['start_sec']}_{h['end_sec']}"
        extract_clip_frames(VIDEO, h["start_sec"], h["end_sec"], fps=8.0, out_dir=clip_dir)

        # 실제 구현 포인트:
        # - 이 clip_dir 프레임들을 묶어 Video-LMM에 넣고
        # - "결제 없이 퇴장"의 정확한 start/end를 추정
        # - VideoITG류 접근은 여기서 instruction에 따라 프레임을 더 ‘선별’해 비용을 줄임 ([github.com](https://github.com/NVlabs/VideoITG))

        # 예시 결과(데모)
        results.append(FineResult(
            start_sec=h["start_sec"] + 18.5,
            end_sec=h["start_sec"] + 31.2,
            confidence=0.78,
            evidence="right hand moves item to bag while cashier distracted; subject exits frame without payment gesture"
        ))

    out_path = "artifacts/fine_results.json"
    json.dump([r.model_dump() for r in results], open(out_path, "w"), ensure_ascii=False, indent=2)
    print("saved:", out_path)

if __name__ == "__main__":
    main()
```

### 3) 확장: “이해 → 생성”으로 연결(리포트 영상 만들기)
OpenAI는 **Videos API**에서 생성뿐 아니라 edits/extensions 같은 “후처리형 job” 엔드포인트를 제공합니다. 즉, fine pass로 얻은 구간을 바탕으로 *“해당 구간만 잘라 설명 자막을 얹은 요약 클립”* 같은 생성/편집 워크플로우를 비동기 job으로 붙일 수 있습니다. ([platform.openai.com](https://platform.openai.com/docs/api-reference/videos/object?lang=go))  
(이 단계는 제품 정책/저작권/얼굴 블러 등 컴플라이언스가 먼저입니다.)

---

## ⚡ 실전 팁 & 함정

### Best Practice (2~3개)
1) **프레임 샘플링을 “고정 설정”이 아니라 “질문/업무 규칙”으로 모델링**
- VideoITG가 강조하는 지점이 결국 이것입니다: instruction에 따라 discriminative frame selection을 바꾸는 구조. ([github.com](https://github.com/NVlabs/VideoITG))  
- 실무에선 “업무 유형별 정책”으로 구현하세요. 예:  
  - 안전모 착용 감지: 1 FPS + 사람 검출 기반 구간 확장  
  - 폭력/도난 의심: 0.5 FPS 스캔 → 후보 구간만 8 FPS

2) **coarse 단계에서는 ‘정답’이 아니라 ‘리콜(recall)’을 극대화**
- coarse가 놓치면 끝입니다. 대신 false positive는 fine에서 줄이면 됩니다.
- retrieval top-k를 넉넉히 잡고, fine에서 비용을 통제하세요.

3) **timestamp 신뢰성을 위해 “CFR(고정 FPS)로 normalize”**
- 가변 FPS/드랍 프레임이 있는 입력은 “초 단위 구간”이 어긋나기 쉽습니다. ffmpeg로 re-encode+fps 고정 후 처리하는 게 안전합니다.

### 흔한 함정/안티패턴
- **“FPS만 올리면 해결”**: 비용이 선형이 아니라 “토큰화/컨텍스트/전송”에서 병목이 납니다. Gemini 문서도 결국 FPS는 상황별 조절 대상입니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/video-understanding))
- **후보 구간 retrieval 없이 전 구간 fine 분석**: POC는 되지만 운영에서 비용/지연이 바로 폭발합니다.
- **프레임만 보고 오디오/자막/메타데이터를 버림**: 실제 사건은 오디오(알람, 대화), POS 로그, 출입문 센서 같은 사이드 채널에서 더 잘 잡힙니다(멀티모달이 파이프라인 비용을 줄여줌).

### 비용/성능/안정성 트레이드오프
- **성능(정확도)**는 “fine FPS”보다 **후보 구간의 품질(retrieval/grounding)**에 더 민감합니다.
- **비용**은 (전체 길이 × coarse FPS) + (후보 길이 × fine FPS)로 설계 가능하므로, 운영 KPI에 맞춰 *후보 길이를 줄이는 쪽*이 ROI가 큽니다.
- **안정성**은 입력 정규화(코덱/FPS), 실패 시 fallback(더 낮은 FPS로 재시도, 구간 쪼개기)에서 갈립니다.

---

## 🚀 마무리

2026년 6월 기준으로 비디오 AI는 “좋은 모델을 고르는 문제”를 넘어, **프레임 분석 파이프라인을 어떻게 설계하느냐**가 제품 성패를 가르는 단계에 왔습니다. 기본 전략은 단순합니다.

- **coarse(저비용)로 전체를 훑고 → retrieval로 후보 구간을 좁히고 → fine(고비용)로 grounding 한다**
- 질문/업무 규칙을 샘플링 정책에 반영하는 *instruction-aware* 접근(VideoITG류)이 특히 실무 친화적입니다. ([github.com](https://github.com/NVlabs/VideoITG))
- 제공사 API(Gemini의 FPS/클리핑 옵션, OpenAI의 비디오 job 워크플로우 등)는 “이 파이프라인을 구현하기 위한 레고 블록”으로 보면 됩니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/video-understanding))

도입 판단 기준(현실 체크):
- 영상 길이가 길고, 이벤트가 희소하며, 비용 제한이 빡세다 → **반드시 2-stage(또는 3-stage)로**
- 질문이 다양하고 운영팀이 “왜 이 구간이냐”를 요구한다 → **temporal grounding + evidence 프레임**까지 설계
- 데이터 라벨이 부족하다 → VidThinker 같은 **자동 어노테이션/합성 데이터 파이프라인** 계열도 같이 검토(최근 arXiv에서도 “합성 기반 멀티모달 비디오 데이터 파이프라인” 연구가 활발). ([arxiv.org](https://arxiv.org/abs/2604.12335))

다음 학습 추천:
- VideoITG/VidThinker 식의 **instruction-conditioned retrieval + grounding** 파이프라인을 내 도메인에 맞게 “정책”으로 재정의하기 ([github.com](https://github.com/NVlabs/VideoITG))
- Gemini video understanding의 sampling/클리핑 옵션을 이용해 “coarse/fine를 API 옵션으로 분리”하는 운영 설계 ([ai.google.dev](https://ai.google.dev/gemini-api/docs/video-understanding))
- 생성까지 붙일 거면, OpenAI Videos API 같은 **비동기 job 기반 생성 파이프라인**에서 재시도/검수/저작권 정책을 먼저 설계 ([platform.openai.com](https://platform.openai.com/docs/api-reference/videos/object?lang=go))