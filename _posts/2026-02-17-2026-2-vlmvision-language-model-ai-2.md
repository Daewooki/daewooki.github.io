---
title: "2026년 2월, VLM(Vision Language Model)로 “이미지 분석 AI”를 제품에 넣는 법: 멀티모달 설계부터 비용/정확도 최적화까지"
date: 2026-02-17 02:47:53 +0900
categories: [AI, Multimodal]
tags: [ai, multimodal, trend, 2026-02]
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
2026년 2월 기준 멀티모달 AI(Vision Language Model, VLM)는 “이미지 → 텍스트”를 넘어서, **UI 스크린샷 디버깅**, **문서/차트 이해**, **상품/결함 검사**, **장면 기반 QA**, **간단한 object detection/segmentation 보조**까지 제품 요구사항을 빠르게 채우는 범용 엔진이 됐습니다. 특히 최신 상용 VLM들은 별도 CV 파이프라인(전처리+모델+후처리)을 전부 만들기 전에, **프롬프트+구조화 출력(JSON)**만으로 “일단 동작하는” 기능을 매우 빠르게 뽑아낼 수 있습니다.

다만 실무에서 바로 마주치는 문제는 뻔합니다:  
1) **출력이 들쭉날쭉**(형식이 깨짐) 2) **비용 폭발**(큰 이미지/다중 이미지) 3) **정확도 저하**(텍스트/회전/해상도) 4) **검증 불가**(근거 없이 그럴듯한 말).  
이 글은 2026년 2월 시점의 공식 문서 기반으로, VLM을 “이미지 분석 AI”로 안전하게 쓰는 설계를 심층적으로 정리합니다. (OpenAI/Google Gemini/Anthropic Claude를 예로 듭니다.) ([platform.openai.com](https://platform.openai.com/docs/guides/images-vision?utm_source=openai))

---

## 🔧 핵심 개념
### 1) VLM 활용의 본질: “이미지를 토큰화한 프롬프트”다
VLM은 이미지를 내부 표현으로 바꿔 텍스트 프롬프트와 **같은 컨텍스트**에서 추론합니다. 즉, 이미지 입력도 결국 **비용/지연/컨텍스트**를 먹습니다. OpenAI는 이미지 입력이 텍스트처럼 토큰으로 과금되며, 모델에 따라 이미지가 패치(예: 32px) 단위로 토큰화된다고 명시합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/images-vision?utm_source=openai))  
Gemini도 큰 이미지를 타일링하여 토큰 비용이 증가하는 구조를 문서로 공개합니다(예: 768x768 타일, 타일당 비용). ([ai.google.dev](https://ai.google.dev/gemini-api/docs/vision?utm_source=openai))

**실무적 결론**:  
- “큰 원본 1장”은 생각보다 비싸고 느립니다.  
- ROI가 높은 방식은 **필요 영역만 crop**하거나, **저해상도→고해상도 2단계**로 나누는 것입니다.

### 2) 구조화 출력(JSON)이 멀티모달을 “제품 기능”으로 만든다
이미지 분석을 서비스에 넣으려면 자연어가 아니라 **스키마가 있는 결과**(라벨, 좌표, 신뢰도, 이슈 리스트)가 필요합니다. Gemini 문서는 object detection/segmentation 결과를 JSON으로 받는 패턴(예: `response_mime_type="application/json"`)을 예시로 제공합니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/vision?utm_source=openai))  
이 패턴을 따라가면, VLM을 “대화 모델”이 아니라 **비전 분석 엔진**으로 다루게 됩니다.

### 3) “모델이 잘하는 일/못하는 일”을 설계에 반영
OpenAI 비전 가이드에는 파노라마/어안에서 약함, 메타데이터 미사용, 리사이즈로 원본 차원 영향, counting은 근사치, CAPTCHA 차단 같은 제한이 명시되어 있습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/images-vision?utm_source=openai))  
따라서 **정답이 ‘좌표/수량’처럼 엄밀해야 하는 기능**은:
- VLM 단독으로 끝내지 말고
- (가능하면) CV 모델과의 하이브리드, 또는
- VLM 결과를 “초안/후보 생성”으로 쓰고 후처리로 검증
이 안전합니다.

### 4) 입력 방식의 선택: base64 vs URL/File API
Claude는 이미지 입력을 **base64**, **URL 참조**, **Files API**로 넣는 방법을 공식 문서로 정리합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/vision?utm_source=openai))  
대량/반복 처리 파이프라인에서는 base64는 전송량/CPU 오버헤드가 커서, “업로드 후 재사용(File API)” 또는 “사내 오브젝트 스토리지 URL” 형태가 운영에 유리합니다.

---

## 💻 실전 코드
아래는 “제품 사진 1장을 넣으면, 결함 의심 영역을 **bounding box 후보**로 JSON 반환”하는 예제입니다.  
(정밀 detection은 전용 CV가 낫지만, VLM로 **검수/라벨링/사전분류**를 빠르게 구성할 때 유용합니다.)  
Gemini 문서의 object detection JSON 패턴과 좌표 정규화(0~1000)를 그대로 활용합니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/vision?utm_source=openai))

```python
# requirements:
#   pip install google-genai pillow
#
# 환경변수:
#   export GOOGLE_API_KEY="..."

from google import genai
from google.genai import types
from PIL import Image
import json

def analyze_defect_candidates(image_path: str):
    client = genai.Client()  # GOOGLE_API_KEY 사용

    # 핵심: "무엇을 JSON으로 뽑을지"를 스키마처럼 강하게 지시
    prompt = """
너는 제조 품질검사(QA) 보조 시스템이다.
이미지에서 결함(스크래치, 크랙, 오염, 찍힘)으로 의심되는 영역을 찾아라.

출력은 JSON 배열만 반환해라. 마크다운/설명 금지.
각 원소는 다음 필드를 포함:
- label: 결함 유형( scratch | crack | stain | dent | other )
- box_2d: [ymin, xmin, ymax, xmax] (0~1000 정규화 좌표)
- reason: 한 문장 근거(관찰 기반)
- severity: 1~5

가능하면 1~5개 후보만 반환하고, 확신이 낮으면 severity를 낮춰라.
"""

    image = Image.open(image_path)

    # Gemini 문서 패턴: response_mime_type을 JSON으로 지정하면 파싱 안정성이 크게 올라간다.
    config = types.GenerateContentConfig(
        response_mime_type="application/json"
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[image, prompt],  # 문서 권장: 이미지 다음에 프롬프트
        config=config
    )

    # response.text는 JSON 문자열(배열)이어야 한다.
    candidates = json.loads(response.text)

    # 후처리 예시: 정규화 좌표(0~1000)를 픽셀 좌표로 변환
    w, h = image.size
    for c in candidates:
        y0, x0, y1, x1 = c["box_2d"]
        c["box_px"] = [int(x0/1000*w), int(y0/1000*h), int(x1/1000*w), int(y1/1000*h)]

    return candidates

if __name__ == "__main__":
    result = analyze_defect_candidates("sample.jpg")
    print(json.dumps(result, ensure_ascii=False, indent=2))
```

이 접근의 포인트:
- VLM에게 “탐지”를 시키되, **제품 로직은 JSON 스키마로 고정**한다.
- 좌표는 정규화로 받고, **UI 오버레이/검수툴**에서 픽셀 변환하여 활용한다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/vision?utm_source=openai))

---

## ⚡ 실전 팁
1) **Two-pass 전략(저비용→고정밀)**
- 1차: 저해상도/썸네일로 “뭘 봐야 하는지” 후보 추출
- 2차: 후보 영역만 crop해서 재질문(ROI 기반 확대)  
이미지는 토큰 비용을 먹기 때문에, 전체 이미지를 매번 고해상도로 넣는 설계는 금방 한계가 옵니다(타일/패치 증가). ([platform.openai.com](https://platform.openai.com/docs/guides/images-vision?utm_source=openai))

2) **회전/왜곡/메타데이터 함정**
OpenAI 문서에서 이미지가 리사이즈되고 메타데이터/파일명은 보지 않는다고 명시합니다. 촬영 기기 EXIF 회전 정보에 의존하면, 사람이 보는 방향과 모델이 보는 방향이 어긋날 수 있습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/images-vision?utm_source=openai))  
→ 업로드 전에 서버에서 **EXIF 회전 보정**을 강제하는 게 안전합니다.

3) **Counting/정밀 좌표는 “정답”이 아니라 “후보”로**
OpenAI는 counting이 근사치가 될 수 있다고 명시합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/images-vision?utm_source=openai))  
→ “불량 개수=정산”처럼 돈/정책에 연결되는 지표는  
- (a) 전용 CV 모델로 최종 확정  
- (b) VLM은 라벨링/검수 보조  
로 역할을 분리하세요.

4) **여러 이미지 입력은 “컨텍스트 설계”가 전부**
Claude는 한 요청에 여러 이미지를 넣을 수 있고(API 최대 100장)라고 안내합니다. ([docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/vision?utm_source=openai))  
하지만 실무에서는 “그냥 다 넣기”가 아니라:
- 이미지마다 ID를 부여하고(예: img_01, img_02)
- 질문도 “img_02에서만 결함 후보”처럼 **참조 범위를 좁히기**
가 품질과 비용을 동시에 잡습니다.

5) **프롬프트는 ‘관찰 기반’으로 강제**
환각을 줄이는 가장 싼 방법은 “추정 금지, 관찰한 것만, 불확실하면 낮은 severity” 같은 **출력 규칙**을 JSON 스키마와 함께 박아두는 것입니다.  
(추가로, 결과를 바로 신뢰하지 말고 **원본 이미지에 오버레이 렌더링**해서 사람이 빠르게 검수할 수 있게 만드세요.)

---

## 🚀 마무리
2026년 2월의 VLM 활용은 “이미지 캡션”이 아니라, **구조화된 분석 결과(JSON) + 비용 최적화(타일/패치 절감) + 제한사항을 전제로 한 제품 설계**가 핵심입니다. 공식 문서가 말하는 것처럼 이미지 입력은 토큰으로 과금되고, 큰 이미지는 타일링/패치로 비용이 커지며, 리사이즈/카운팅/왜곡 같은 한계가 존재합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/images-vision?utm_source=openai))

다음 학습으로는:
- (1) JSON schema를 더 엄격히(필드/enum/범위) 고정해서 “깨지지 않는 출력 계약” 만들기
- (2) ROI crop + 2-pass 파이프라인으로 비용/정확도 벤치마킹
- (3) VLM 결과를 CV(예: segmentation 모델)와 결합해 “후보 생성→검증” 구조로 고도화
를 추천합니다.

원하시면, 위 예제를 **OpenAI/Claude 버전**으로도 동일한 JSON 계약으로 바꿔서(입력: URL/File, 출력: schema) 비교 벤치마크 템플릿까지 만들어드릴게요.