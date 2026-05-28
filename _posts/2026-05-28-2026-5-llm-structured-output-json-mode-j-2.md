---
title: "2026년 5월 기준: LLM Structured Output에서 “JSON mode + JSON Schema 강제”를 제대로 쓰려면 알아야 할 제약들"
date: 2026-05-28 04:18:21 +0900
categories: [AI, LLM]
tags: [ai, llm, trend, 2026-05]
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
LLM을 서비스에 붙일 때 JSON은 “있으면 좋은 출력 형식”이 아니라 **시스템 경계(contract)** 입니다. 한 번이라도 `"` 하나 빠진 출력, enum 오타, 필드 누락이 발생하면 파이프라인 전체가 연쇄적으로 깨지죠. 그래서 2026년에는 대부분의 팀이 아래 중 하나로 수렴합니다.

- **JSON mode**: “유효한 JSON”까지만 보장
- **Structured Outputs (schema 강제 / strict)**: “내가 준 JSON Schema에 맞는 JSON”을 **디코딩 단계에서** 강제
- **Function calling(tool use)**: 모델이 “행동(도구 호출)”을 선택하고, 그 인자를 스키마로 제한

이 글은 특히 **2026년 5월 시점의 ‘스키마 제약’**에 초점을 맞춥니다. 즉 “JSON Schema를 줬는데 왜 안 지키지?” 같은 운영 이슈를 줄이기 위한 판단 기준입니다.

언제 쓰면 좋나?
- **ETL/정규화 파이프라인**, 티켓/리뷰/계약서 등 **문서 → 구조화** 작업
- 멀티스텝 agent에서 step 간 인터페이스를 JSON으로 고정해야 할 때
- 프론트(UI 생성)나 워크플로우 엔진이 JSON을 바로 소비할 때

언제 쓰면 안 되나?
- 출력이 길고 자유서술이 핵심인 경우(보고서 본문 등): 스키마 강제는 종종 **토큰/형식 제약 비용**을 키웁니다.
- “정답이 없고 탐색이 중요한 작업”: 스키마로 과도하게 조이면 모델이 **빈 값/무난한 값**으로 도망가 품질이 떨어질 수 있습니다.
- “의미 제약(semantic constraint)”이 핵심인 도메인: JSON Schema는 구조/타입은 강하지만, `end_date > start_date` 같은 규칙은 별도 검증이 필요합니다. ([respan.ai](https://www.respan.ai/articles/openai-structured-outputs-vs-json-mode?utm_source=openai))

---

## 🔧 핵심 개념
### 1) JSON mode vs Structured Outputs(strict)의 차이
- **JSON mode**는 “파싱 가능한 JSON”을 목표로 합니다. 스키마 준수는 *프롬프트/후처리*에 의존합니다. OpenAI 문서도 “스키마 일치 보장은 아니다”라고 명확히 분리합니다. ([platform.openai.com](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat&utm_source=openai))  
- **Structured Outputs(strict)**는 “JSON Schema에 맞는 토큰만 생성”하도록 **constrained decoding**을 걸어버리는 방식입니다. 즉, 모델이 마음대로 필드를 빼거나 enum을 추가하기가 구조적으로 어려워집니다. ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))

여기서 중요한 오해 2가지:
1) **“strict면 검증 라이브러리 필요 없다”** → 운영 관점에선 *여전히 필요*합니다. 공급자 버그/엣지케이스 대비 + 의미 검증을 위해서요. ([respan.ai](https://www.respan.ai/articles/openai-structured-outputs-vs-json-mode?utm_source=openai))  
2) **“스키마면 의미까지 보장”** → 스키마는 구조/타입/열거/패턴 같은 **형식 제약**에 강하지만, 의미 제약은 별도 로직이 필요합니다. ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))

### 2) Function calling은 “포맷팅”이 아니라 “행동 선택” 프리미티브
요즘도 “추출(extraction)을 tool call로 시키면 JSON이 잘 나와요”라는 구현이 많습니다. 그런데 2026년 기준으로는 **추출은 Structured Outputs로**, tool call은 **모델이 실제 액션을 결정해야 할 때**에 쓰는 게 비용/신뢰성 면에서 유리하다는 정리가 많이 나옵니다. ([flowverify.co](https://www.flowverify.co/blog/llm-function-calling-vs-structured-outputs?utm_source=openai))

- 추출만 필요한데 tool call을 쓰면: tool 정의/arguments 래핑 등으로 토큰 오버헤드가 생기고, “모델이 굳이 도구를 호출할지” 같은 변수가 추가됩니다. ([flowverify.co](https://www.flowverify.co/blog/llm-function-calling-vs-structured-outputs?utm_source=openai))

### 3) “JSON Schema 제약”은 공급자별로 다르게 동작한다 (2026년에도 포터블하지 않다)
이게 2026년 5월의 현실적인 함정입니다.

- OpenAI는 `strict: true`를 켜면 스키마 준수를 강하게 보장하는 방향으로 문서화돼 있고, 스키마 미지원이면 요청 자체가 에러가 날 수 있습니다. ([platform.openai.com](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat&utm_source=openai))  
- Gemini는 문서에서 **“JSON Schema의 subset 지원”**을 명시합니다. 즉 “표준 JSON Schema를 그대로 들고 가면” 일부 키워드/조합이 안 먹을 수 있습니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/structured-output?utm_source=openai))  
- Anthropic 툴 스키마도 “JSON Schema draft 2020-12”를 받더라도, 실제로 출력이 문법적으로 강제되는 파이프라인은 **subset**만 안정적으로 동작한다는 현장 디버깅 글이 있습니다. ([startdebugging.net](https://startdebugging.net/2026/05/fix-tool-call-arguments-did-not-match-schema-in-anthropic-tool-use/?utm_source=openai))

결론: “우리 스키마는 JSON Schema 2020-12니까 어디서나 되겠지”는 위험합니다. (멀티벤더/폴백 전략이면 특히)

### 4) strict가 해결 못 하는 것: truncation(중간 잘림)과 semantic correctness
형식이 완벽해도 운영에서 가장 많이 터지는 건 **길이/토큰 한계로 JSON이 ‘중간까지만’ 생성**되는 케이스입니다. 심지어 constrained decoding이어도 “완성 전에 토큰이 끝나면” 계약은 깨집니다(혹은 ‘부분만 나온’ 상태가 됩니다). 커뮤니티 테스트에서도 truncation이 “killer”로 언급됩니다. ([reddit.com](https://www.reddit.com/r/Python/comments/1tagc2g/i_tested_structured_output_from_288_llm_calls_and/?utm_source=openai))  
그리고 OpenAI도 “값 자체의 정답성(예: 수학 단계)”은 별개라고 선을 긋습니다. ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))

---

## 💻 실전 코드
시나리오: **고객지원 티켓(이메일/채팅 로그) → CRM에 저장할 “정규화된 케이스 JSON” 생성**  
요구사항:
- downstream은 이 JSON만 믿고 자동 분류/라우팅/우선순위 SLA를 건다
- “형식 오류로 파이프라인 중단”이 최악이므로 **schema 강제 + 검증 + 부분 실패 전략**이 필요

아래 예시는 OpenAI 스타일(Structured Outputs)로 설명하되, **Zod/Pydantic 검증을 한 번 더** 걸어 “의미 제약”까지 마무리합니다. (strict가 있어도 방어적 설계)

### 1) 의존성/환경
```bash
npm i openai zod
export OPENAI_API_KEY="..."
```

### 2) 스키마 정의 + 호출 + 2단계 검증(구조/의미)
```typescript
import OpenAI from "openai";
import { z } from "zod";

const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

// 1) 운영에서 바로 쓰는 "계약" (downstream이 의존)
const TicketSchema = z.object({
  ticket_id: z.string().min(8),
  language: z.enum(["ko", "en", "ja", "zh", "other"]),
  customer: z.object({
    email: z.string().email().nullable(),
    name: z.string().min(1).nullable(),
  }),
  product: z.enum(["mobile", "web", "billing", "login", "other"]),
  severity: z.enum(["sev1", "sev2", "sev3"]),
  summary: z.string().min(10).max(240),
  tags: z.array(z.string().min(2)).max(10),
  // 의미 제약(semantic) 후보: 날짜/금액/우선순위 등은 후술 validator로 강화
  needs_human: z.boolean(),
});

type Ticket = z.infer<typeof TicketSchema>;

// 2) JSON Schema로 변환(현실에서는 zod-to-json-schema 사용 권장)
// 여기서는 핵심만: "additionalProperties: false" 같은 강제도 중요
const ticketJsonSchema = {
  name: "normalized_ticket",
  strict: true,
  schema: {
    type: "object",
    additionalProperties: false,
    required: ["ticket_id","language","customer","product","severity","summary","tags","needs_human"],
    properties: {
      ticket_id: { type: "string", minLength: 8 },
      language: { type: "string", enum: ["ko","en","ja","zh","other"] },
      customer: {
        type: "object",
        additionalProperties: false,
        required: ["email","name"],
        properties: {
          email: { type: ["string","null"], format: "email" },
          name: { type: ["string","null"], minLength: 1 },
        },
      },
      product: { type: "string", enum: ["mobile","web","billing","login","other"] },
      severity: { type: "string", enum: ["sev1","sev2","sev3"] },
      summary: { type: "string", minLength: 10, maxLength: 240 },
      tags: { type: "array", items: { type: "string", minLength: 2 }, maxItems: 10 },
      needs_human: { type: "boolean" },
    },
  },
};

export async function normalizeTicket(rawText: string): Promise<Ticket> {
  // 3) Structured output 요청: "응답 형식"을 요청 바디로 고정
  const resp = await client.responses.create({
    model: "gpt-5.4-mini",
    input: [
      {
        role: "system",
        content:
          "You are a support ops assistant. Extract a normalized ticket object strictly matching the provided JSON schema. No extra keys.",
      },
      {
        role: "user",
        content: rawText,
      },
    ],
    // OpenAI 문서 흐름: response_format에 json_schema + strict ([platform.openai.com](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat&utm_source=openai))
    response_format: { type: "json_schema", json_schema: ticketJsonSchema },
    max_output_tokens: 700, // truncation 리스크를 낮추되, 무작정 크게만 잡지 말 것(비용)
  });

  // SDK/응답 포맷에 따라 추출 위치는 달라질 수 있음
  // 여기서는 "출력이 JSON object"라고 가정하고 파싱
  const obj = resp.output_parsed ?? JSON.parse(resp.output_text ?? "{}");

  // 4) 1차: 구조/타입 검증 (방어적)
  const parsed = TicketSchema.safeParse(obj);
  if (!parsed.success) {
    // 운영 팁: 여기서 바로 재시도하기보다, 오류 요약 + 1회 "수정 요청"이 더 싸게 먹히는 경우 많음
    throw new Error("Schema validation failed: " + parsed.error.message);
  }

  // 5) 2차: 의미(semantic) 검증/정책
  // 예: sev1인데 needs_human=false 같은 조직 정책 위반을 잡아내기
  const t = parsed.data;
  if (t.severity === "sev1" && t.needs_human === false) {
    // fail-closed: 자동화 파이프라인에서 sev1은 반드시 사람 확인
    return { ...t, needs_human: true, tags: Array.from(new Set([...t.tags, "policy_override"])) };
  }

  return t;
}

// 실행 예시
(async () => {
  const raw = `
[채팅 로그]
고객: 결제했는데 프로 플랜이 활성화가 안 돼요. 영수증 메일은 받았고요.
email: user@example.com
앱: web
긴급: 오늘 데모가 있습니다. 지금 당장 필요해요.
`;
  const ticket = await normalizeTicket(raw);
  console.log(ticket);
})();
```

### 예상 출력(예)
```json
{
  "ticket_id": "tmp_93af21c0",
  "language": "ko",
  "customer": { "email": "user@example.com", "name": null },
  "product": "billing",
  "severity": "sev1",
  "summary": "결제 완료(영수증 수신)했지만 프로 플랜이 활성화되지 않아 긴급 조치가 필요한 상황",
  "tags": ["billing", "activation", "urgent"],
  "needs_human": true
}
```

핵심은 “JSON을 프롬프트로 부탁”이 아니라, **API 레벨에서 response_format + strict로 계약을 걸고**, 그래도 **앱 레벨에서 의미 검증을 닫는(fail-closed)** 구조입니다. OpenAI는 strict로 스키마 일치 방향을 강조하지만, 값의 정합성은 별도라고 밝힙니다. ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))

---

## ⚡ 실전 팁 & 함정
### Best Practice (2~3개)
1) **additionalProperties: false + required를 적극적으로**
   - “모델이 친절하게 설명 필드 추가” 같은 drift를 막습니다.
   - 특히 멀티스텝 agent에서 다음 스텝이 `obj.foo`에 의존하면, 스키마가 곧 API 계약입니다.

2) **strict를 켰어도 ‘의미 검증’을 별도로**
   - JSON Schema는 형식 제약에는 강하지만, “도메인 규칙”은 못 담는 경우가 많습니다. 그래서 Zod refine / Pydantic validator로 2차 방어를 두는 게 일반적입니다. ([respan.ai](https://www.respan.ai/articles/openai-structured-outputs-vs-json-mode?utm_source=openai))

3) **길이(토큰) 설계를 스키마 설계만큼 중요하게**
   - 배열 maxItems, 문자열 maxLength를 적당히 잡지 않으면 truncation/비용 문제가 바로 옵니다.
   - 커뮤니티에서도 “중간 잘림”이 운영에서 가장 치명적이라고 반복 보고됩니다. ([reddit.com](https://www.reddit.com/r/Python/comments/1tagc2g/i_tested_structured_output_from_288_llm_calls_and/?utm_source=openai))

### 흔한 함정/안티패턴
- **“추출인데도” tool call을 남발**
  - 도구 호출은 모델이 “행동을 선택”해야 하는 상황에 적합합니다. 추출만 필요하면 Structured Outputs가 더 단순하고 안정적이라는 비교 글들이 많습니다. ([flowverify.co](https://www.flowverify.co/blog/llm-function-calling-vs-structured-outputs?utm_source=openai))

- **벤더 간 스키마 이식(Portability) 가정**
  - Gemini는 subset 지원을 명시합니다. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/structured-output?utm_source=openai))  
  - Anthropic도 “받는 스키마”와 “실제로 안정적으로 강제되는 subset” 간 간극이 문제로 언급됩니다. ([startdebugging.net](https://startdebugging.net/2026/05/fix-tool-call-arguments-did-not-match-schema-in-anthropic-tool-use/?utm_source=openai))  
  → 멀티벤더 전략이면 “공통 subset 스키마”를 정의하거나, 벤더별 스키마 컴파일 레이어를 두세요.

### 비용/성능/안정성 트레이드오프
- **strict/constrained decoding**은 신뢰성을 크게 올리지만, 스키마가 복잡해질수록:
  - 생성 자유도가 줄어 품질(표현 다양성)이 떨어지거나
  - 스키마를 만족시키기 위한 “무난한 값”으로 채워질 수 있고
  - max_output_tokens를 키우게 되어 비용이 증가하기 쉽습니다.
- 반대로 JSON mode + 후처리(retry/repair)는:
  - 초기 구현은 빠르지만,
  - 운영에서 “5% 실패”가 장애 비용으로 돌아옵니다(재시도 폭증, 큐 지연 등).  
  결국 **엄격한 계약이 필요한 구간만 strict**, 나머지는 자유 출력로 분리하는 하이브리드가 실무적으로 가장 많이 이깁니다.

---

## 🚀 마무리
정리하면, 2026년 5월 기준 LLM structured output의 핵심은 “JSON을 예쁘게 받기”가 아니라 **시스템 계약을 어디에 두느냐**입니다.

- **정말 JSON이 계약이라면**: Structured Outputs(strict)로 “형식”을 디코딩 단계에서 잠그고, 앱에서 Zod/Pydantic로 “의미”를 잠그세요. ([openai.com](https://openai.com/index/introducing-structured-outputs-in-the-api/?utm_source=openai))  
- **행동(외부 API 호출/DB write 등)을 모델이 결정해야 한다면**: Function calling(tool use)을 쓰되, 인자 스키마는 가능한 단순하게 유지하세요.
- **멀티벤더/폴백이면**: “JSON Schema면 어디서나 된다”를 버리고, 공급자별 subset/제약을 전제로 설계하세요. ([ai.google.dev](https://ai.google.dev/gemini-api/docs/structured-output?utm_source=openai))

다음 학습 추천(바로 실무에 도움되는 순서):
1) OpenAI Structured Outputs 가이드에서 `strict: true` / `response_format: json_schema` 패턴 정리 ([platform.openai.com](https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat&utm_source=openai))  
2) Gemini Structured Outputs의 “subset 제약” 확인(지원 키워드/타입/정렬 특성) ([ai.google.dev](https://ai.google.dev/gemini-api/docs/structured-output?utm_source=openai))  
3) “truncation 대응”을 재시도만으로 풀지 말고, maxLength/maxItems 설계 + 부분 실패 전략(수정 1회, fail-closed)을 팀 표준으로 만들기 ([reddit.com](https://www.reddit.com/r/Python/comments/1tagc2g/i_tested_structured_output_from_288_llm_calls_and/?utm_source=openai))

원하면, 당신이 쓰는 스키마(또는 Pydantic/Zod 모델) 일부를 주면 “OpenAI/Gemini/Anthropic 공통 subset으로 컴파일”하는 기준과, 운영에서 자주 깨지는 제약(예: oneOf/anyOf, nullable, format, pattern 등)을 어떻게 피할지까지 스키마 리뷰 형태로 구체화해드릴게요.