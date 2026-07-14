---
title: "토큰 예산이 병목인 시대: 2026년 7월 Video AI(understanding+generation)에서 “Frame Analysis Pipeline”이 승부를 가른다"
date: 2026-07-14 03:15:54 +0900
categories: [AI, Multimodal]
tags: [ai, multimodal, trend, 2026-07]
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
2026년 7월의 비디오 AI는 모델 성능 자체도 중요하지만, **“어떤 프레임(혹은 구간)을 모델에 먹일지”를 결정하는 파이프라인**이 실제 품질/비용을 좌우합니다. 긴 영상(회의 녹화, 강의, CCTV, 스포츠, 게임 리플레이)을 “그냥 1fps로 샘플링”하면 **토큰/비용은 줄지만** 질의에 필요한 근거 프레임을 놓쳐서 답이 틀리거나, 반대로 **모든 프레임을 다 넣으면** 비용·지연이 감당이 안 됩니다.

- **언제 쓰면 좋은가**
  - 긴 영상에서 **질의 기반 QA / 하이라이트 탐지 / 이벤트 타임라인 추출 / 근거 프레임 리트리벌**이 필요한 경우
  - 사용자 질문이 들어올 때마다 “동적으로” 봐야 할 장면이 달라지는 제품(예: 고객이 “그때 누가 문을 열었지?” 같은 질문을 하는 보안 영상)
- **언제 쓰면 안 되는가**
  - 전수 분석이 필수인 규제/포렌식 영역(프레임 누락 자체가 리스크)
  - 모델이 아니라 **클래식 CV 트래킹/액션 인식**이 더 확실한 단일 과업(예: 단일 객체 카운팅만 정확히)

최근 연구 흐름은 공통적으로 “**uniform sampling → (가끔 CLIP 점수로 keyframe)**”에서 벗어나, **query-adaptive(질문 적응형) / multi-modal routing(모달리티 노이즈 억제) / bandit/agentic selection(탐색-활용)**으로 이동 중입니다. 예: FOCUS(멀티암드 밴딧 기반 keyframe selection) ([iclr.cc](https://iclr.cc/virtual/2026/poster/10011835?utm_source=openai)), Q-Gate(질의 의도에 따라 visual/subtitle 등 expert를 가변 가중) ([arxiv.org](https://arxiv.org/abs/2604.17422?utm_source=openai)), VideoITG(temporal grounding으로 긴 영상에서 근거 구간 탐색) ([nvlabs.github.io](https://nvlabs.github.io/VideoITG/?utm_source=openai)), Video-MTR(멀티턴으로 구간을 반복 선택하는 agentic 접근) ([openreview.net](https://openreview.net/forum?id=UhPwL6LYOc&utm_source=openai)).

---

## 🔧 핵심 개념
### 1) “Frame selection”은 압축이 아니라 **증거 수집(evidence gathering)**
긴 영상 이해에서 실패 원인의 상당수는 모델 지능 부족이 아니라 **정답 근거가 되는 프레임이 컨텍스트에 없어서** 발생합니다. 그래서 최근 방법들은 frame selection을 “요약”이 아니라 **질의에 대한 증거 수집**으로 봅니다.

### 2) Query-adaptive keyframe selection: 왜 uniform sampling이 지는가
- uniform sampling(예: 1fps)은 “평균적으로”는 괜찮지만,
  - **짧게 발생하는 핵심 이벤트(문 열림 0.5초)**를 놓치거나
  - plot-driven 질문(“왜 싸우기 시작했어?”)처럼 **visual만으로 부족한 질의**에서 자막/대사 같은 텍스트 신호를 무시합니다.

Q-Gate는 여기서 한 발 더 나가서, keyframe scoring을 한 가지 기준으로 고정하지 않고 **세 개의 lightweight expert stream(로컬 디테일, 글로벌 장면 의미, 자막/내러티브 정렬)을 두고** 질의 의도를 LLM이 판단해 **가중치를 동적으로 배분**합니다. 이때 핵심은 “멀티모달을 무조건 합치면 좋다”가 아니라, **관계없는 모달리티는 modal noise가 되니 ‘mute’해야 한다**는 주장입니다. ([arxiv.org](https://arxiv.org/abs/2604.17422?utm_source=openai))

### 3) Bandit/agentic selection: “잘 모르니 더 봐야 한다”를 수학적으로 다루기
FOCUS는 프레임/클립 선택을 **multi-armed bandit의 pure-exploration 문제**로 모델링합니다. 짧은 temporal clip을 arm으로 보고, 점수의 불확실성(신뢰반경)을 유지하며 탐색→활용 2단계로 **2% 미만 프레임만 보고도 정확도를 올리는** 방향을 제시합니다. ([iclr.cc](https://iclr.cc/virtual/2026/poster/10011835?utm_source=openai))  
즉, “초반에 대충 훑고(cheap), 애매한 구간을 더 보고(expensive), 마지막에 top-K 프레임을 뽑는다”가 정교해지고 있습니다.

### 4) Temporal grounding이 파이프라인의 ‘중간 표현’이 된다
VideoITG류는 단순 keyframe이 아니라, 질의에 대해 **시간 구간(temporal segment)을 먼저 찾고** 그 안에서 프레임을 뽑는 식으로 “근거 구간”을 구조화합니다. ([nvlabs.github.io](https://nvlabs.github.io/VideoITG/?utm_source=openai))  
이 구조는 실무적으로도 유리합니다:
- UI에 “근거 타임라인”을 노출 가능(설명가능성)
- 캐시 단위가 frame이 아니라 **segment**가 되어 재사용이 쉬움

### 5) 제품 관점: API도 결국 “샘플링/클리핑” knobs가 핵심
Gemini(Cloud) 쪽 video understanding 가이드는 **clipping interval / custom frame-rate sampling / media_resolution** 같은 파라미터로 입력 비디오 처리 전략을 조절하도록 명시합니다. “granular temporal analysis면 FPS를 올려라” 같은 권고도 문서에 들어가 있습니다. ([docs.cloud.google.com](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/video-understanding?hl=en&utm_source=openai))  
결국 연구 트렌드와 제품 knobs가 같은 곳(프레임/구간 선택)으로 수렴 중입니다.

---

## 💻 실전 코드
아래는 “**긴 MP4(예: 1~2시간 회의 녹화)**에서 비용을 통제하면서도 질의 정확도를 올리는” 현실적인 파이프라인 예시입니다.

- 1단계: ffmpeg로 **저해상도 proxy + 1fps 프레임 + 오디오** 추출(cheap pass)
- 2단계: Gemini Video Understanding로 **저비용 coarse 분석**(타임라인/장면 후보)
- 3단계: 후보 구간만 **고FPS로 재샘플링**해 정밀 QA(heavy pass)
- (선택) 결과를 DB에 저장해 같은 영상 재질의 시 비용 절감

> 전제: Google Cloud/Gemini 쪽은 문서에서 비디오 이해 시 샘플링/클리핑을 조절할 수 있음 ([docs.cloud.google.com](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/video-understanding?hl=en&utm_source=openai))  
> 또한 Veo 3.1은 Gemini API로 영상 생성(4/6/8초, 720p~4k, referenceImages 등)을 제공하니, 이해 결과를 기반으로 “짧은 요약 클립 생성” 같은 후처리도 가능 ([ai.google.dev](https://ai.google.dev/gemini-api/docs/veo?hl=en&utm_source=openai))

### 0) 의존성/환경
```bash
# 시스템
brew install ffmpeg  # macOS 예시 (Linux는 apt/yum)

# Python
python -m venv .venv
source .venv/bin/activate
pip install google-genai pydantic python-dotenv
export GEMINI_API_KEY="YOUR_KEY"
```

### 1) 초기 셋업: proxy/프레임 추출(cheap pass)
```bash
# 1) 긴 원본을 proxy로 (네트워크/업로드 비용 절감)
ffmpeg -y -i meeting.mp4 -vf "scale=640:-2" -c:v libx264 -preset veryfast -crf 28 -an meeting_proxy.mp4

# 2) 1fps 프레임 추출 (coarse 탐색용)
mkdir -p frames_1fps
ffmpeg -y -i meeting_proxy.mp4 -vf "fps=1" frames_1fps/%06d.jpg

# 3) 오디오 추출 (있으면 자막/ASR 파이프라인과 결합)
ffmpeg -y -i meeting.mp4 -vn -ac 1 -ar 16000 meeting.wav
```

### 2) 기본 동작: coarse 타임라인 + 후보 구간 뽑기
아래 코드는 “질문”을 받고, 먼저 **낮은 fps(=적은 비용)로 개략적 후보 구간**을 추정한 뒤, 그 구간만 정밀 분석 단계로 넘기는 형태입니다. (실무에서 이 구조가 캐시/재시도/관측 가능성 측면에서 가장 안정적입니다.)

```python
# video_pipeline.py
import os
from typing import List, Tuple
from pydantic import BaseModel
from google import genai

class Segment(BaseModel):
    start_sec: int
    end_sec: int
    reason: str

class CoarseResult(BaseModel):
    segments: List[Segment]

def chunk_indices(total_frames: int, chunk_size: int) -> List[Tuple[int, int]]:
    out = []
    for s in range(1, total_frames + 1, chunk_size):
        e = min(total_frames, s + chunk_size - 1)
        out.append((s, e))
    return out

def run_coarse_selection(question: str, frame_dir: str, chunk_size: int = 120) -> CoarseResult:
    """
    1fps 프레임(=초당 1장) 기준으로 chunk(예: 2분 단위)마다 대표 프레임 몇 장만 넣고,
    모델에게 '이 질문에 중요할 가능성이 큰 구간'을 고르게 한다.
    """
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    frames = sorted([f for f in os.listdir(frame_dir) if f.endswith(".jpg")])
    total = len(frames)
    chunks = chunk_indices(total, chunk_size)

    # chunk마다 중앙 프레임 1장만 써도 되고, 3장(초반/중앙/후반)으로 늘려도 됨.
    # 여기서는 3장으로 "짧은 이벤트" 누락 확률을 줄임.
    prompt = f"""
You are a senior video analyst.
Given sampled frames from a long video (1 fps), pick candidate time segments likely relevant to the question.

Question: {question}

Return JSON with:
segments: [{{
  "start_sec": int, "end_sec": int, "reason": string
}}]

Rules:
- segments should be coarse (60~300 seconds each)
- pick up to 5 segments
- if uncertain, include the segment but say why
"""

    # 프레임 업로드 방식은 환경에 따라 다르지만, 핵심은 "chunk 대표 프레임만" 넣는 것.
    # (실 서비스에서는 File API / GCS URI 등을 사용)
    # 여기서는 개념 코드로 '텍스트로 프레임 인덱스'를 함께 넘겨 디버깅 가능하게 구성.
    evidence = []
    for (s, e) in chunks:
        mid = (s + e) // 2
        picks = [s, mid, e]
        evidence.append(f"chunk {s}-{e} sec representative frames: {picks}")

    resp = client.models.generate_content(
        model="gemini-2.5-pro",  # 예시
        contents=[prompt + "\n\n" + "\n".join(evidence)],
        config={"response_mime_type": "application/json"},
    )

    return CoarseResult.model_validate_json(resp.text)

if __name__ == "__main__":
    q = "결정된 액션 아이템과 담당자는 누구인지, 해당 논의가 나온 시점을 알려줘."
    result = run_coarse_selection(q, "frames_1fps")
    print(result.model_dump_json(indent=2, ensure_ascii=False))
```

**예상 출력(형태 예시)**  
```json
{
  "segments": [
    { "start_sec": 840, "end_sec": 1020, "reason": "화이트보드/슬라이드 전환이 잦고 결정 사항 요약 슬라이드로 보임" },
    { "start_sec": 1860, "end_sec": 2100, "reason": "참석자들이 노트북을 닫고 결론/정리 발화 가능성이 높음" }
  ]
}
```

### 3) 확장: 후보 구간만 고FPS 재샘플링 → 정밀 QA
Gemini 문서가 말하는 것처럼, **FPS를 올리는 건 ‘필요한 구간에만’** 적용하는 게 핵심입니다. ([docs.cloud.google.com](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/video-understanding?hl=en&utm_source=openai))

```bash
# 예: 840~1020초 구간만 6fps로 재추출 (정밀 분석용)
mkdir -p frames_6fps_seg1
ffmpeg -y -ss 840 -to 1020 -i meeting_proxy.mp4 -vf "fps=6" frames_6fps_seg1/%06d.jpg
```

그 다음, 고FPS 프레임(또는 원본 클립)을 넣고 “근거 포함 답변”을 생성합니다. 실무에서는 결과에 **근거 프레임 번호/타임코드**를 반드시 포함시켜 QA/디버깅이 가능하게 하세요.

---

## ⚡ 실전 팁 & 함정
### Best Practice
1) **2-pass(cheap→heavy) 구조를 고정**하라  
처음부터 고FPS/고해상도로 넣는 팀은 비용이 폭발합니다. “coarse segment selection → segment-only refine”는 연구 트렌드(FOCUS, VideoITG, Video-MTR류)와도 잘 맞습니다. ([iclr.cc](https://iclr.cc/virtual/2026/poster/10011835?utm_source=openai))

2) **질문 유형별로 라우팅(visual vs narrative)**
Q-Gate가 지적하듯, 내러티브/자막 기반 질문에 visual metric만 쓰면 망하고, 반대로 순수 시각 질문에 텍스트를 과하게 섞으면 노이즈가 됩니다. 따라서 실무에서도:
- “누가/무엇을/어디서” → visual-heavy
- “왜/어떻게/결론” → subtitle/ASR-heavy  
같은 룰을 최소한으로라도 도입하세요. ([arxiv.org](https://arxiv.org/abs/2604.17422?utm_source=openai))

3) **segment를 캐시 키로 삼아라**
프레임 단위 캐시는 너무 세분화되어 관리 지옥이 됩니다. “(video_id, start_sec, end_sec, fps)”를 키로 캐시하면 재질의/재생성 비용이 확 줄어듭니다.

### 흔한 함정/안티패턴
- **“1fps면 충분하겠지” 고정관념**: 문서도 fast-action/정밀 temporal 분석은 FPS를 올리라고 합니다. ([docs.cloud.google.com](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/video-understanding?hl=en&utm_source=openai))  
- **한 번 뽑은 keyframe을 모든 질문에 재사용**: query-adaptive의 반대. 질문이 바뀌면 봐야 할 장면도 바뀝니다.
- **근거 없는 답변을 허용**: 모델이 그럴듯하게 말해도, 영상 QA는 “근거 타임코드/프레임”이 없으면 운영에서 터집니다.

### 비용/성능/안정성 트레이드오프
- FPS↑/해상도↑: 정확도는 오르지만 **비용·지연↑**, 그리고 “중요 프레임을 더 잘 찾는 문제”가 아니라 “그냥 더 많이 보는 문제”가 되어 확장성이 떨어집니다.
- bandit/agentic selection(FOCUS/Video-MTR류): 프레임 수를 크게 줄이지만, 구현이 복잡하고(상태/보상/루프) 디버깅 포인트가 늘어납니다. ([iclr.cc](https://iclr.cc/virtual/2026/poster/10011835?utm_source=openai))
- 모델 생성(Veo 3.1 등)과 결합: 이해 결과로 “요약 클립/하이라이트 생성”까지 가능하지만, 생성은 보통 **고정 길이(예: 4/6/8초)** 같은 제약이 있어 편집/스토리보드 로직이 필요합니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/veo?hl=en&utm_source=openai))

---

## 🚀 마무리
2026년 7월 기준 비디오 AI에서 가장 실무적인 경쟁력은 “더 큰 모델”보다 **프레임/구간 선택 파이프라인**입니다. 연구는 Q-Gate처럼 **질의 의도에 따른 multimodal routing**으로 “modal noise”를 줄이고 ([arxiv.org](https://arxiv.org/abs/2604.17422?utm_source=openai)), FOCUS처럼 **탐색-활용 기반**으로 “적게 보고도 맞추는” 쪽으로 진화 중입니다 ([iclr.cc](https://iclr.cc/virtual/2026/poster/10011835?utm_source=openai)). 제품 API도 결국 clipping/fps 같은 knobs를 제공하며 같은 방향을 지원합니다. ([docs.cloud.google.com](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/video-understanding?hl=en&utm_source=openai))

**도입 판단 기준(현실적인 체크리스트)**  
- 우리 문제의 병목이 “모델이 멍청함”인가, 아니면 “근거 프레임을 못 넣음”인가?
- 질문이 다양하게 들어오는가(=query-adaptive 필요)? 아니면 고정 과업인가?
- 운영에서 근거 타임코드/재현 가능한 캐시가 필수인가?

**다음 학습 추천**
- long-video QA 벤치마크/방법: FOCUS, VideoITG, Video-MTR 논문/코드로 “selection loop” 감각 익히기 ([iclr.cc](https://iclr.cc/virtual/2026/poster/10011835?utm_source=openai))  
- 실제 API 입력 최적화: Gemini video understanding의 clipping/FPS 조절 가이드 정독 후, 비용-정확도 실험표 만들기 ([docs.cloud.google.com](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/video-understanding?hl=en&utm_source=openai))

원하시면, 위 파이프라인을 **(1) GCS 업로드 + (2) segment 캐시를 위한 Postgres 스키마 + (3) 재시도/관측(Logging/Tracing) 포함** 형태로 “바로 서비스에 붙는” 템플릿으로 확장해 드릴게요.