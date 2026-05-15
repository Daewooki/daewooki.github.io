---
title: "프레임을 “샘플링”하던 시대는 끝났다: 2026년 5월 비디오 AI(Understanding/Generation)와 프레임 분석 파이프라인 설계법"
date: 2026-05-15 04:07:29 +0900
categories: [AI, Multimodal]
tags: [ai, multimodal, trend, 2026-05]
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
2026년 5월 기준, 비디오 AI는 크게 두 축으로 갈립니다.

- **Video Understanding(이해)**: “이 영상에서 무슨 일이 일어났는가?”를 검색/요약/하이라이트/정합성 검증까지 **프로덕션 워크플로우에 붙이는 기술**
- **Video Generation(생성)**: “이런 장면을 만들어라”를 넘어, **길이/일관성/오디오/비용**이 의사결정 포인트가 된 기술

이번 달에 특히 실무 관점에서 중요한 변화는:
- **비용 효율형 video generation API가 본격적으로 ‘개발자용 제품’ 형태로 정리**되고(예: Google의 Veo 3.1 Lite를 Gemini API/AI Studio로 제공) ([blog.google](https://blog.google/innovation-and-ai/technology/ai/veo-3-1-lite/?utm_source=openai))
- **엔터프라이즈 비디오 이해 플랫폼이 “모델 + 인프라”에서 “편집/제작 파이프라인 통합”으로 진화**한다는 점입니다(예: TwelveLabs의 NAB 2026 발표). ([prweb.com](https://www.prweb.com/releases/twelvelabs-unveils-the-next-era-of-video-intelligence-at-nab-show-2026-302746715.html?utm_source=openai))
- 연구 측면에서는 **Long video generation의 병목을 ‘attention 비용’이 아니라 ‘내부 retrieval(기억 검색)’ 문제로 재정의**하며, 길이를 늘리는 기법이 구체화되고 있습니다(Mixture of Contexts, ICLR 2026). ([openreview.net](https://openreview.net/forum?id=y6XJZlEC2x&utm_source=openai))

### 언제 쓰면 좋나
- **사내 영상(교육/세일즈콜/회의/제조/물류/매장 CCTV)**에서 “찾기/요약/근거 프레임 제시”가 필요할 때
- UGC/광고/커머스에서 **대량 생성(variation)**이 필요하고, 1개 퀄리티보다 **단가와 회전율**이 중요한 경우(Veo 3.1 Lite 같은 cost-effective 모델) ([blog.google](https://blog.google/innovation-and-ai/technology/ai/veo-3-1-lite/?utm_source=openai))
- 생성 결과의 **정합성(brand safety / factual consistency)**을 이해 모델로 “검증”하는 **closed-loop**를 만들 때

### 언제 쓰면 안 되나(혹은 조건부)
- “영상 전체를 매 프레임 정밀 분석”하려는 접근: 비용/지연/저장(특히 egress)이 바로 병목
- 모델/엔드포인트 라이프사이클이 빠른 공급자 의존을 감당 못하는 경우: **preview→deprecate→shutdown** 같은 일정이 실제 운영 리스크가 됩니다(예: 모델 단계 전환/디프리케이션 공지와 커뮤니티 반응). ([blog.google](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-flash-lite/?utm_source=openai))  
- 규제/법무 상 “영상 원본 외부 반출 불가”인데 클라우드 API만 고려하는 경우(온프렘/프라이빗 옵션까지 포함해 설계해야 함)

---

## 🔧 핵심 개념
### 1) “프레임 분석”에서 “이벤트/샷 단위”로: 파이프라인의 단위가 바뀜
전통적인 파이프라인은 `N fps로 프레임 추출 → 각 프레임에 image caption/embedding → 합치기`였는데,
이 방식은 다음 문제가 있습니다.

- **중복 계산 폭발**: 인접 프레임은 정보가 거의 동일
- **시간 정보 손실**: motion/action의 핵심은 “프레임 간 변화”
- **검색 품질 저하**: “사람이 뛰어감”과 “사람이 서 있음”이 비슷한 frame embedding으로 뭉개짐

2026년의 실무형 파이프라인은 보통 다음 3단으로 갑니다.

1) **Temporal segmentation(shot/scene/event)**  
   - 샷 전환(컷) + 음성 구간 + 움직임 변화량으로 “의미 단위”를 먼저 잡습니다.
2) **Sparse keyframe + low-rate clip features**  
   - 각 세그먼트에서 1~3장의 keyframe만 고해상도로, 나머지는 저해상도/저fps로 motion feature를 뽑습니다.
3) **멀티모달 증거화(evidence)**  
   - 요약/QA 답변을 낼 때 “근거 타임코드/프레임”을 같이 반환하도록 설계합니다. (이게 제품 신뢰도를 좌우)

### 2) Video Understanding의 실전 내부 흐름(권장 아키텍처)
현장에서 잘 먹히는 구조는 “**2계층 인덱스**”입니다.

- **L0: segment-level index (cheap, recall 높게)**
  - segment embedding(비디오+오디오+텍스트)
  - 목적: “관련 구간 후보 top-k” 빠르게 좁히기
- **L1: evidence extractor (expensive, precision 높게)**
  - 후보 구간에 대해서만 고정밀 caption/ASR alignment/object/action query 수행
  - 목적: 사용자에게 납득 가능한 결과(근거) 만들기

여기서 최신 트렌드 중 하나는 “**텍스트/이미지/비디오를 같은 임베딩 공간에 매핑**”하려는 시도입니다(예: Google의 Gemini Embedding 2가 text/image/video를 함께 매핑한다고 소개). ([gadgets360.com](https://www.gadgets360.com/ai/news/google-gemini-embedding-2-first-natively-multimodal-ai-model-map-text-images-videos-released-11198672/amp?utm_source=openai))  
이 방향은 **“텍스트 질의로 비디오를 찾는”** 제품에서 특히 강력합니다.

### 3) Video Generation: 길이를 늘리는 싸움의 본질이 바뀜
Long video generation에서 가장 큰 병목은 DiT류에서 **self-attention 비용이 길이에 대해 quadratic**으로 터지는 것입니다.  
ICLR 2026의 *Mixture of Contexts(MoC)*는 이를 “긴 컨텍스트를 전부 보지 말고, **현재 생성에 필요한 과거를 retrieval로 고르자**”로 재정의합니다. ([openreview.net](https://openreview.net/forum?id=y6XJZlEC2x&utm_source=openai))

실무 적용 관점의 함의:
- 길이를 늘릴수록 중요한 건 “더 큰 모델”이 아니라  
  **(a) 어떤 과거를 기억할지, (b) 어떻게 identity/action/scene을 유지할지**입니다.
- 그래서 생성 파이프라인도 점점 “한 번에 끝”이 아니라  
  **plan → generate → check → repair** 같은 루프로 제품화됩니다.

### 4) 2026년 5월에 ‘개발자가 바로 쓰는’ 생성 모델 포지션
Google은 Veo 3.1 Lite를 **비용 효율형 video generation**으로 밀고, **Gemini API/AI Studio에서 접근** 가능하다고 공식 블로그와 모델 카드로 설명합니다. ([blog.google](https://blog.google/innovation-and-ai/technology/ai/veo-3-1-lite/?utm_source=openai))  
즉 “고퀄 원툴”보다 “대량 생성 + 빠른 iteration”이 필요한 팀에 현실적인 선택지가 됐다는 뜻입니다.

---

## 💻 실전 코드
아래 예제는 “사내 QA 팀이 **제품 데모/버그 리포트 영상**을 올리면, 자동으로 (1) 구간을 나누고 (2) 검색 인덱스를 만들고 (3) 사용자가 질문하면 관련 구간을 찾아 (4) 그 구간만 생성 모델로 ‘짧은 요약 데모 클립’을 만드는” 현실 시나리오입니다.

- Understanding: **로컬 파이프라인(FFmpeg + OpenCV + Whisper)**로 비용 통제
- Generation: **Veo 3.1 Lite (Gemini API)**로 “요약 클립”을 생성(예: 핵심 장면을 재구성한 짧은 안내 영상)

> 주의: Veo/Gemini API의 정확한 SDK/엔드포인트는 수시로 바뀔 수 있습니다. 여기서는 **구조(파이프라인/데이터 계약)** 중심으로 작성하고, 호출부는 공식 문서에 맞게 교체 가능하도록 어댑터로 분리합니다. (Veo 3.1 Lite가 Gemini API로 제공된다는 점은 공식 안내에 근거) ([blog.google](https://blog.google/innovation-and-ai/technology/ai/veo-3-1-lite/?utm_source=openai))

### 0) 설치/의존성
```bash
# 시스템 의존성
brew install ffmpeg  # macOS 예시
# ubuntu: sudo apt-get install ffmpeg

python -m venv .venv
source .venv/bin/activate

pip install opencv-python numpy pydub openai-whisper fastapi uvicorn faiss-cpu sentence-transformers
# Veo/Gemini SDK는 공식 문서 기준으로 설치(아래는 예시)
# pip install google-genai
```

### 1) 영상 → 세그먼트(샷 유사) 분할 + keyframe 추출 + 텍스트(ASR) 생성
```python
# video_indexer.py
import os, json, subprocess
from dataclasses import dataclass, asdict
from typing import List, Tuple
import cv2
import numpy as np
import whisper

@dataclass
class Segment:
    start_s: float
    end_s: float
    keyframe_path: str
    asr_text: str

def extract_audio(video_path: str, wav_path: str):
    subprocess.check_call([
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", wav_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def detect_shots(video_path: str, threshold: float = 25.0, min_len_s: float = 2.0) -> List[Tuple[float, float, int]]:
    """
    간단한 shot boundary: 프레임 히스토그램 차이 기반.
    반환: (start_s, end_s, keyframe_frame_idx)
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    prev_hist = None
    start_frame = 0
    keyframe_idx = 0

    shots = []
    frame_idx = 0

    best_score = -1.0
    best_frame = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([gray],[0],None,[64],[0,256])
        hist = cv2.normalize(hist, hist).flatten()

        if prev_hist is not None:
            score = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA) * 100.0)
            # keyframe: shot 내에서 변화량이 큰 프레임을 대표로 잡는(단순 휴리스틱)
            if score > best_score:
                best_score = score
                best_frame = frame_idx

            if score > threshold:
                end_frame = frame_idx
                dur = (end_frame - start_frame) / fps
                if dur >= min_len_s:
                    shots.append((start_frame / fps, end_frame / fps, best_frame))
                start_frame = frame_idx
                best_score = -1.0
                best_frame = frame_idx

        prev_hist = hist
        frame_idx += 1

    # tail
    end_frame = frame_idx - 1
    dur = (end_frame - start_frame) / fps
    if dur >= min_len_s:
        shots.append((start_frame / fps, end_frame / fps, best_frame))

    cap.release()
    return shots

def save_keyframe(video_path: str, frame_idx: int, out_path: str):
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ok, frame = cap.read()
    if not ok:
        raise RuntimeError("Failed to read keyframe")
    cv2.imwrite(out_path, frame)
    cap.release()

def transcribe(wav_path: str) -> List[dict]:
    model = whisper.load_model("base")  # 실무는 small/medium + GPU 권장
    result = model.transcribe(wav_path, fp16=False)
    return result["segments"]

def build_segments(video_path: str, workdir: str) -> List[Segment]:
    os.makedirs(workdir, exist_ok=True)
    wav_path = os.path.join(workdir, "audio.wav")
    extract_audio(video_path, wav_path)

    asr_segments = transcribe(wav_path)
    shots = detect_shots(video_path)

    # asr를 shot 구간에 대충 매핑(실무는 alignment 정교화 권장)
    def asr_text_for_range(s: float, e: float) -> str:
        texts = []
        for seg in asr_segments:
            if seg["end"] < s or seg["start"] > e:
                continue
            texts.append(seg["text"].strip())
        return " ".join(texts).strip()

    segments: List[Segment] = []
    for i, (s, e, kf) in enumerate(shots):
        kf_path = os.path.join(workdir, f"kf_{i:04d}.jpg")
        save_keyframe(video_path, int(kf), kf_path)
        segments.append(Segment(
            start_s=s, end_s=e,
            keyframe_path=kf_path,
            asr_text=asr_text_for_range(s, e)
        ))

    with open(os.path.join(workdir, "segments.json"), "w", encoding="utf-8") as f:
        json.dump([asdict(x) for x in segments], f, ensure_ascii=False, indent=2)

    return segments

if __name__ == "__main__":
    segs = build_segments("demo_bugreport.mp4", workdir="./_index/demo_bugreport")
    print("segments:", len(segs))
    print("sample:", segs[0])
```

**예상 출력(예):**
- `segments: 18`
- `sample: Segment(start_s=0.0, end_s=6.4, keyframe_path='./_index/.../kf_0000.jpg', asr_text='...')`

### 2) 세그먼트 인덱싱(검색) + 질문 시 top-k 구간 반환
```python
# segment_search.py
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

class SegmentSearchIndex:
    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        self.enc = SentenceTransformer(model_name)
        self.index = None
        self.meta = []

    def build(self, segments_json_path: str):
        segs = json.load(open(segments_json_path, "r", encoding="utf-8"))
        # 텍스트만으로도 “대충” 검색이 되지만, 실무는 (caption + asr + tags) 결합 권장
        corpus = [
            f"[ASR]{s['asr_text']} [T]{s['start_s']:.2f}-{s['end_s']:.2f}"
            for s in segs
        ]
        emb = self.enc.encode(corpus, normalize_embeddings=True).astype("float32")
        self.index = faiss.IndexFlatIP(emb.shape[1])
        self.index.add(emb)
        self.meta = segs

    def search(self, query: str, k: int = 5):
        q = self.enc.encode([query], normalize_embeddings=True).astype("float32")
        scores, ids = self.index.search(q, k)
        out = []
        for score, idx in zip(scores[0].tolist(), ids[0].tolist()):
            s = self.meta[idx]
            out.append({
                "score": score,
                "start_s": s["start_s"],
                "end_s": s["end_s"],
                "keyframe_path": s["keyframe_path"],
                "asr_text": s["asr_text"]
            })
        return out

if __name__ == "__main__":
    ix = SegmentSearchIndex()
    ix.build("./_index/demo_bugreport/segments.json")
    hits = ix.search("checkout 버튼을 누르면 화면이 멈추는 구간", k=3)
    print(json.dumps(hits, ensure_ascii=False, indent=2))
```

### 3) (확장) top-k 구간만 Veo로 “짧은 요약 클립” 생성하기(어댑터)
여기서 핵심은 **생성 모델을 ‘원본 그대로 생성’에 쓰지 말고**, “설명/재현/가이드 클립”처럼 *product-safe*한 용도로 제한하는 겁니다. 비용도 줄고 리스크도 줄어듭니다. (Veo 3.1 Lite는 비용 효율형 포지션을 명확히 함) ([blog.google](https://blog.google/innovation-and-ai/technology/ai/veo-3-1-lite/?utm_source=openai))

```python
# veo_adapter.py
from dataclasses import dataclass

@dataclass
class GenerateRequest:
    prompt: str
    # optional: reference_image_path, duration_s, fps, aspect_ratio ...

class VeoClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        # TODO: 공식 Gemini API SDK에 맞게 초기화

    def generate(self, req: GenerateRequest) -> bytes:
        """
        반환: 생성된 비디오 바이너리(mp4)
        실제 구현은 Google의 Gemini API/Veo 문서에 맞게 교체.
        """
        raise NotImplementedError("Implement with official Gemini API SDK")

def build_demo_prompt(issue: str, segment_start: float, segment_end: float, asr: str) -> str:
    return f"""
You are generating a short support clip for developers.
Goal: Recreate the bug scenario as an instructional demo (NOT a photorealistic copy of user footage).
Scene: A web app checkout flow on desktop.
Bug: {issue}

Constraints:
- Duration: ~6 seconds
- Clear cursor movement and UI transitions
- Include an on-screen text overlay showing timestamps {segment_start:.2f}s–{segment_end:.2f}s
- Narration is optional; if used, keep it concise

Context from the original report (ASR excerpt, may be noisy):
{asr}
""".strip()
```

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **샷/이벤트 segmentation을 “가장 먼저”**  
   프레임을 많이 뽑기 전에 “구간”을 나누면, 이후 모든 단계(ASR 매핑, embedding, evidence 추출, 재처리)가 싸집니다.  
   특히 운영에서 “재색인” 비용이 압도적으로 줄어듭니다.

2) **2계층 인덱스(L0 recall / L1 precision)로 비용을 통제**  
   L0에서 대충 넓게 찾고, L1에서만 비싼 모델(혹은 멀티모달)을 씁니다.  
   이 구조는 공급자/모델이 바뀌어도 유지되는 “아키텍처 자산”입니다.

3) **Generation은 ‘최종 콘텐츠’가 아니라 ‘보조 산출물’로 시작**  
   예: 요약 데모 클립, 하이라이트 시안, A/B용 variation 등.  
   Veo 3.1 Lite처럼 cost-effective API가 나올수록 “대량 보조 산출물”이 ROI가 좋습니다. ([blog.google](https://blog.google/innovation-and-ai/technology/ai/veo-3-1-lite/?utm_source=openai))

### 흔한 함정/안티패턴
- **안티패턴: 전 프레임 captioning**  
  “나중에 쓸 수도” 때문에 다 처리하면, 비용·지연·저장 모두 터집니다.  
  대신 “필요 시 L1 재처리”로 설계하세요.
- **안티패턴: preview 엔드포인트를 프로덕션에 고정**  
  모델 lifecycle이 빠른 곳은 preview deprecation/shutdown이 실제 장애로 이어집니다(커뮤니티에서도 운영 적합성 이슈가 반복 제기). ([reddit.com](https://www.reddit.com/r/GoogleGeminiAI/comments/1taf464/gemini_model_lifecycle_is_incompatible_with/?utm_source=openai))
- **함정: ASR 텍스트만 믿고 검색 품질을 평가**  
  소음/억양/도메인 용어 때문에 recall이 떨어집니다. keyframe caption(가벼운 VLM)이나 도메인 사전 기반 keyword boosting을 섞는 편이 낫습니다.

### 비용/성능/안정성 트레이드오프
- **비용 ↓**: segmentation + sparse keyframe + L0/L1 분리
- **성능(정확도) ↑**: L1에서만 멀티모달/고해상도/정교한 alignment 적용
- **안정성 ↑**: 모델 호출부를 어댑터로 분리 + 결과를 evidence(타임코드/프레임)로 저장  
  → 모델이 바뀌어도 “왜 그렇게 판단했는지”를 유지

---

## 🚀 마무리
- 2026년 5월의 핵심은 “비디오 AI가 좋아졌다”가 아니라, **파이프라인 단위가 프레임에서 세그먼트/이벤트로 이동**했고, **생성은 장편화를 retrieval/메모리 문제로 풀기 시작**했다는 점입니다. ([openreview.net](https://openreview.net/forum?id=y6XJZlEC2x&utm_source=openai))  
- 개발자 관점에서는 **비용 효율형 video generation API(예: Veo 3.1 Lite)**가 “실험용”을 넘어 “운영 설계에 넣어볼 만한” 단계로 내려왔습니다. ([blog.google](https://blog.google/innovation-and-ai/technology/ai/veo-3-1-lite/?utm_source=openai))  
- 도입 판단 기준:
  1) 영상 데이터가 꾸준히 쌓이고 “찾기/요약/근거” 요구가 있는가?
  2) 전 프레임 분석 없이도 해결 가능한가? (가능해야 ROI가 나옵니다)
  3) 모델 라이프사이클(Preview→GA→Deprecation)에 대응할 운영 체계를 갖출 수 있는가?

다음 학습 추천:
- Long video generation의 메모리/일관성 관점: *Mixture of Contexts(MoC), ICLR 2026* ([openreview.net](https://openreview.net/forum?id=y6XJZlEC2x&utm_source=openai))  
- 상용 API로 “단가/지연/품질” 비교 실험: Veo 3.1 Lite의 모델 카드/가이드 ([deepmind.google](https://deepmind.google/models/model-cards/veo-3-1-lite/?utm_source=openai))  
- 제작 워크플로우 통합 사례(understanding의 제품화 방향): TwelveLabs의 NAB 2026 발표 흐름 ([prweb.com](https://www.prweb.com/releases/twelvelabs-unveils-the-next-era-of-video-intelligence-at-nab-show-2026-302746715.html?utm_source=openai))