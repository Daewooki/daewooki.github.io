---
title: "Spring AI 2.1.0: Session과 MCP, Responses가 바꾸는 운영 계약"
description: "2.1.0은 ChatMemory·세션 기반 MCP·Chat Completions 중심 사고를 흔들고, 운영 가능한 에이전트 계약과 회귀 테스트 포인트를 강제합니다."
date: 2026-11-21 15:28:31 +0900
categories: ["News", "AI"]
tags: ["spring-ai", "session-api", "mcp", "openai-responses", "tool-calling", "regression-testing"]
render_with_liquid: false
---

## 2026-11-20에 무슨 일이 있었나: 2.1.0 GA의 델타를 숫자로 확인

Spring AI 2.1.0 GA는 2026-11-20에 공개됐고, Spring Boot 4.2 기반으로 정리됐습니다. 공식 발표문은 2.0.0 GA 이후 5개월, 86명의 기여자와 430+ 커밋을 강조합니다. 기능 목록만 보면 늘 하던 “모델 추가”로 보이지만, 실제로는 **Session API**와 MCP 2026-07-28, 그리고 OpenAI Responses API 지원이 엮이면서 “에이전트 기능”의 운영 단위가 바뀌는 릴리스입니다. [Spring AI 2.1.0 GA 발표](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/)에 그 방향성이 비교적 명확하게 드러납니다.

내가 이번 GA를 “에이전트 프레임워크 업데이트”가 아니라 “운영 계약 업데이트”로 보는 이유는 다음 세 가지가 한 번에 들어왔기 때문입니다.

1) MCP가 2026-07-28 개정으로 프로토콜 레벨에서 stateless로 재설계됐고(세션·handshake 제거), Spring AI가 클라이언트/서버 양쪽을 같이 따라갑니다. [Spring AI 2.1.0 GA 발표](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/)

2) ChatMemory가 deprecate 되고(3.0에서 제거 예정), Session API가 “대화 기록 저장”을 이벤트 로그 기반으로 바꿉니다. 이 변화는 단순히 “메모리 구현체 교체”가 아니라, 장애/재시작/멀티 인스턴스에서 대화의 일관성을 어디에 두는지(=어떤 계약을 테스트해야 하는지)를 바꿉니다. [Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html), [Session Memory 문서](https://docs.spring.io/spring-ai/reference/api/session.html)

3) OpenAI 쪽은 Chat Completions 중심의 메시지 모델로는 더 이상 “reasoning 모델/에이전트 워크플로우”를 깔끔하게 다루기 어렵고, Responses API가 그 대체로 굳어지는 흐름인데, Spring AI 2.1이 이를 정식으로 흡수합니다. [OpenAI Responses API (Spring AI)](https://docs.spring.io/spring-ai/reference/api/chat/openai-responses-chat.html), [Spring AI Message Parts 블로그](https://spring.io/blog/2026/10/28/spring-ai-message-parts-reasoning-replay/)

여기에 “운영” 관점에서 더 중요한 보강이 같이 들어왔습니다.

- tool loop에 호출 한도(기본 per-tool 40, turn total 150)를 도입해서 runaway loop를 비용 사고로 보기 전에 차단합니다. [Tool Calling 문서](https://docs.spring.io/spring-ai/reference/api/tools.html), [Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)
- tool call을 사람 승인으로 gating 할 수 있는 Tool Call Confirmation이 들어왔고, pause/resume이 framework stateless로 설계돼서, 애플리케이션이 대화 상태를 책임지는 구조가 더 노골적으로 드러납니다. [Tool Call Confirmation 문서](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)
- Redis semantic cache 등 CVE 수정이 GA에 포함됐고(2.0.3에도 포함), 마일스톤/RC를 운영에 그대로 들고 가면 안 되는 이유를 다시 확인시킵니다. [Spring AI 2.1.0 GA 발표](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/)

이 글의 관점은 “데모용 AI”가 아니라 운영 가능한 애플리케이션 계약으로, 어디에 회귀 테스트 포인트를 박아야 하는지를 중심으로 정리합니다. (Tool use / function calling 운영 패턴 자체는 예전에 정리해 둔 글이 있고, 그 내용을 반복하진 않습니다: [Tool use + function calling 프로덕션 구현 패턴](https://daewooki.github.io/posts/2026-5-ai-agent-tool-use-function-callin-1/))

## 운영 단위가 바뀐다는 말의 의미: ChatMemory의 대화 ID에서 Session의 이벤트 로그로

Spring AI 2.0까지 “운영 가능한 대화”를 만든다고 하면 보통 ChatMemory에 conversationId를 키로 메시지 리스트를 저장하고, 윈도우 사이즈로 자르고, 필요하면 VectorStore에서 RAG로 보강하는 식이었습니다. 이 방식은 단순해서 좋지만, 에이전트가 되면 금방 깨집니다.

- tool call/결과가 들어오면 메시지 수 기준 eviction은 턴을 쪼갭니다.
- 모델 공급자별로 “reasoning block”, “tool call delta”, “provider-specific block”이 섞이는데, 텍스트만 저장하면 round trip에서 정보가 소실됩니다.
- “승인 대기(pause)”가 들어오면, 대화의 어느 지점에서 멈췄는지, 그때 모델이 어떤 tool call을 요청했는지, 그 결과를 어떤 형식으로 다시 투입해야 하는지가 애매해집니다.

Spring AI 2.1의 Session은 이 문제를 “대화 = 메시지 배열”이 아니라 “대화 = append-only 이벤트 로그”로 바꿉니다. 문서가 명시하듯 Session은 다음을 핵심으로 내세웁니다.

- 모든 메시지/이벤트가 `SessionEvent`로 기록되는 구조(커스텀 이벤트 타입도 가능)
- compaction이 로그를 rewrite 하지 않고 boundary 이벤트를 append 해서 “active view”만 바꾸는 구조
- recall(키워드 검색)로 view에서 빠진 내용을 다시 찾아오는 API 및 tool 제공
- 저장소 SPI와 contract tests(`spring-ai-test`)로 저장소 구현이 계약 기반으로 검증되는 구조

이 포인트는 문서에 구체적으로 적혀 있습니다. [Session Memory 문서](https://docs.spring.io/spring-ai/reference/api/session.html), [Compaction 문서](https://docs.spring.io/spring-ai/reference/api/session/compaction.html), [JDBC Repository 문서](https://docs.spring.io/spring-ai/reference/api/session/jdbc.html)

여기서 “운영 단위가 바뀐다”는 말은, 대화 상태를 프레임워크가 암묵적으로 들고 있는 게 아니라 애플리케이션이 명시적으로 책임지는 방향으로 한 단계 더 이동했다는 뜻입니다.

- Session에는 “기본 세션”이 없고, 공유 세션을 만들어 주지도 않습니다. 잘못하면 사용자 간 히스토리가 섞이기 때문입니다. GA 발표문이 이 점을 의도적으로 강조합니다. [Spring AI 2.1.0 GA 발표](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/)
- Session advisors 자체는 상태를 들고 있지 않아서(=stateless), 어떤 인스턴스가 어떤 턴을 실행해도 된다는 가정으로 설계됩니다. 장애/롤링 배포/스케일 아웃에서 이게 의미가 큽니다. [ChatClient Integration (Session)](https://docs.spring.io/spring-ai/reference/api/session/chat-client.html)

ChatMemory는 deprecate 되었고 3.0에서 제거 예정입니다. 바꿔 말하면 2.1부터는 “운영 가능한 메모리”의 정답을 Session에 두겠다는 선언에 가깝습니다. [Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html), [Migrating to Session Memory](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/upgrading/session-memory.html)

이 전환은 단순 migration으로 끝나지 않습니다. 운영 계약이 바뀌기 때문에 테스트 포인트가 바뀝니다.

- “메모리가 잘 붙었는지”를 content() 몇 번 찍어보는 수준에서 끝내면 실패합니다.
- compaction이 턴 경계에서만 발생한다는 보장, compaction 이후에도 covered events가 로그에 남는다는 보장, recall이 synthetic 이벤트를 제외하고 검색한다는 보장 같은 것을 회귀 테스트로 박아야 합니다.

Session이 event-sourcing 스타일을 택한 순간, 메모리는 기능이 아니라 데이터 모델이 됩니다.

## Session의 compaction/recall을 운영 계약으로 만들기: 메모리·압축·리콜의 테스트 포인트

Session compaction은 “요약해서 줄인다”가 아니라, active view를 어떻게 구성할지를 결정하는 정책 엔진에 가깝습니다. 문서에 따르면 compaction은 두 축으로 움직입니다.

- Trigger: 언제 줄일지
- Strategy: 무엇을 view에서 제외할지(윈도우/토큰 예산/요약 등)

그리고 가장 중요한 보장은 “항상 턴 경계로만 자른다”입니다. tool call과 tool result가 분리돼서 모델이 tool call만 보고 결과 없이 이어지는 상황을 만들지 않겠다는 뜻입니다. [Compaction 문서](https://docs.spring.io/spring-ai/reference/api/session/compaction.html), [Session Concepts (Turn)](https://docs.spring.io/spring-ai/reference/api/session/concepts.html)

recall은 compaction이 view에서 뺀 이벤트가 로그에 남아 있기 때문에 가능한 기능입니다. `SessionService.searchEvents`가 있고, 이를 모델이 직접 호출할 수 있도록 `conversation_search` tool을 제공하는 `SessionRecallTools`가 있습니다. [Recall 문서](https://docs.spring.io/spring-ai/reference/api/session/recall.html)

운영 계약으로 만들 때 내가 잡는 테스트 포인트는 대략 이런 형태입니다.

### 1) compaction이 로그를 rewrite 하지 않는지

- compaction 전/후 전체 이벤트 수가 줄지 않아야 합니다(경계 + summary 이벤트가 늘어날 뿐).
- covered events는 여전히 조회돼야 합니다(다만 active view에서는 제외).

문서가 “log is never modified, boundary is appended”를 반복해서 강조하는 이유가 여기에 있습니다. [Compaction 문서](https://docs.spring.io/spring-ai/reference/api/session/compaction.html)

### 2) compaction이 턴 경계를 지키는지

- view window를 lastEvents로 자르는 전략을 써도, 실제로는 턴 시작(`SessionEvent.isTurnStart()`)을 기준으로 확장되어 mid-turn start가 되지 않아야 합니다.

이건 “에이전트가 tool을 쓰는 순간부터” 비용/정확도를 좌우합니다. tool이 한 번 끼면 턴당 메시지 수가 급증하는데, mid-turn 절단은 결국 잘못된 재호출/재도구 호출로 이어집니다.

### 3) recall tool이 view 밖 이벤트를 다시 가져오는지, 그리고 bound가 있는지

`conversation_search`는 pageSize, maxTextLength로 “prompt 폭발”을 제한하는 옵션이 있고, 검색 결과는 oldest-first로 페이지됩니다. 이건 그대로 테스트해 두는 편이 낫습니다. 모델이 search tool을 남발하면 비용이 튀는데, 결과 텍스트 길이가 무제한이면 compaction 의미가 사라집니다. [Recall 문서](https://docs.spring.io/spring-ai/reference/api/session/recall.html)

### 4) session id가 tool context로 흘러가는 경로를 통제했는지

문서가 친절하게 경고하듯 `sessionIdInToolContext(true)`를 켜면, session id가 모든 tool(심지어 MCP tool)로 전달됩니다. MCP 서버로 넘어가면 그건 또 다른 PII/식별자입니다. [Recall 문서](https://docs.spring.io/spring-ai/reference/api/session/recall.html)

이 지점은 단순 기능 테스트가 아니라 보안/개인정보 회귀 테스트 포인트가 됩니다.

## Tool call 승인(confirmation)은 “기능”이 아니라 장애 복구 모델이다

Spring AI 2.1의 Tool Call Confirmation은 “승인 UI를 붙인다”가 아니라, tool loop를 중간에 끊어도 시스템이 깨지지 않게 만드는 계약입니다.

문서가 반복해서 말하는 핵심은 이것입니다.

- pause는 “일반적인 response”이고
- resume은 “일반적인 request”이며
- framework는 그 사이에 아무 상태도 들고 있지 않는다

즉, 재시작/스케일 아웃/요청 재시도 같은 운영 이벤트가 일어나도, 애플리케이션이 대화를 보존하기만 하면 이어갈 수 있도록 설계됐습니다. [Tool Call Confirmation 문서](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)

이게 왜 중요한가 하면, 운영 환경에서 “승인 대기”는 흔히 다음의 형태로 터집니다.

- 모델이 “환불 처리하겠다”고 tool call을 만들어냈다
- 백오피스 승인자가 10분 뒤에 승인한다
- 그 사이에 서버가 롤링 배포로 재시작되거나, 세션이 다른 인스턴스로 라우팅된다

이때 framework가 상태를 들고 있었다면 무조건 sticky session이나 공유 스토리지가 필요합니다. Spring AI는 반대로, pause/resume을 프로토콜로 풀어서 stateless로 만듭니다. 이 방식은 MCP 2026-07-28이 handshake/session을 제거한 방향과도 닮아 있습니다. [Tool Call Confirmation 문서](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html), [MCP 2026-07-28 스펙 글](https://blog.modelcontextprotocol.io/posts/2026-07-28/)

또 하나, tool call 승인과 함께 들어온 tool call limits는 “통제 없는 에이전트”가 가장 먼저 만드는 비용 사고를 예방하는 안전장치입니다. 기본값은 per-tool 40, total 150이며, 한도를 넘으면 예외를 던지거나(기본) 모델에게 에러 tool result를 돌려 계속 진행하도록 선택할 수 있습니다. [Tool Calling 문서](https://docs.spring.io/spring-ai/reference/api/tools.html), [Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)

이건 “모델이 가끔 헛돈을 쓴다” 수준이 아니라, 운영에서 장애 등급을 한 단계 올리는 문제입니다.

- loop가 무한히 돌면 단일 요청이 분당 과금 단위를 먹어 치웁니다.
- token usage 집계가 loop 전체로 누적되도록 바뀌었기 때문에, 예전처럼 “마지막 round usage만 테스트에서 본다”는 방식은 더 이상 현실을 반영하지 못합니다. [Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)

### 승인 플로우에서 내가 회귀 테스트로 박는 것

- paused reply를 `content()`만 보고 판단하지 않는다. 문서는 `content()`가 빈 문자열일 수 있고 pause 여부를 알려주지 않는다고 경고합니다. `chatResponse()`를 봐야 하고, `ToolCallDecisions.awaitingDecision(response)`로 pause 여부를 감지해야 합니다. [Tool Call Confirmation 문서](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)
- key가 tool call id가 아닐 수도 있다(`#0` 같은 position key). 승인 저장소는 “tool call 목록의 순서”를 깨면 안 됩니다. [Tool Call Confirmation 문서](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)
- 승인 정책은 재개(resume) 시점에 다시 평가하지 않는다. 문서가 명시하듯 재개는 “모든 call에 대한 decision”을 요구합니다. 중간에 정책이 바뀌어도 슬쩍 실행되면 안 되기 때문입니다. [Tool Call Confirmation 문서](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)

이 지점이 바로 운영 계약입니다.

## OpenAI Responses API 지원은 “엔드포인트 추가”가 아니라 메시지 모델 변경이다

Spring AI 2.1의 큰 변화 중 하나는 메시지가 ordered parts를 가지는 richer message model로 바뀌었다는 점입니다. reasoning/tool call/provider-specific block이 round trip에서 보존되는 구조를 목표로 합니다. [Spring AI 2.1.0 GA 발표](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/), [Spring AI Message Parts 블로그](https://spring.io/blog/2026/10/28/spring-ai-message-parts-reasoning-replay/)

그리고 이 변화의 실전 수혜자가 OpenAI Responses API입니다. Spring AI 문서는 Responses API를 Chat Completions와 나란히 지원한다고 못 박고, 설정으로 `spring.ai.openai.chat.api=responses`를 안내합니다. [OpenAI Responses API (Spring AI)](https://docs.spring.io/spring-ai/reference/api/chat/openai-responses-chat.html)

여기서 중요한 운영 포인트는 “Responses API로 바꾸면 더 좋아진다”가 아니라, 바꾸는 순간 애플리케이션 계약이 바뀐다는 사실입니다.

### 1) Responses API는 Spring AI 쪽에서도 stateless 모드 전제를 강하게 건다

Spring AI Responses 문서는 `store`를 항상 `false`로 보낸다고 명시합니다(구성 불가). 이유는 stored response는 reasoning replay에 필요한 정보를 돌려주지 않기 때문이라고 설명합니다. [OpenAI Responses API (Spring AI)](https://docs.spring.io/spring-ai/reference/api/chat/openai-responses-chat.html)

OpenAI 문서 역시, stateless 모드(ZDR 포함)에서는 reasoning item이 `encrypted_content`로 제공되고 이를 다음 턴에 재전송해야 reasoning continuity가 유지된다고 설명합니다. [OpenAI reasoning guide](https://developers.openai.com/api/docs/guides/reasoning?api-mode=responses&site_locale=en), [OpenAI cookbook: reasoning items](https://developers.openai.com/cookbook/examples/responses_api/reasoning_items)

여기서 현실적인 결론은 하나입니다.

- “대화 상태를 누가 갖고, 어떻게 replay 하느냐”가 비용/품질을 좌우합니다.

Session API와 맞물리면 더 그렇습니다. Session이 이벤트 로그로 상태를 갖고, 모델 호출은 stateless로 간다는 방향이 일관됩니다.

### 2) 메타데이터의 위치/형태가 바뀐다

Spring AI Responses 문서는 metadata를 assistant message metadata가 아니라 `response.getResult().getMetadata()` 쪽으로 읽으라고 안내합니다. 그리고 streaming aggregation 과정에서 일부 `openai.responses.*` 키는 최종 aggregated response에서 사라질 수 있다는 제약도 문서화돼 있습니다. [OpenAI Responses API (Spring AI)](https://docs.spring.io/spring-ai/reference/api/chat/openai-responses-chat.html)

운영에서는 이것이 그대로 회귀 테스트 포인트가 됩니다.

- streaming으로 UI를 만들 때 “마지막 chunk에서만 확인 가능한 것”이 있다면, 집계 로직이 바뀌는 순간 장애가 납니다.

### 3) “Chat Completions와 동일한 옵션”이라는 착각이 깨진다

Spring AI Responses 문서는 `n`, stop sequences, penalty, seed, logit_bias 등은 Responses에 대응이 없어서 무시된다고 명시합니다. 마이그레이션 가이드는 “그 설정은 버려라”라고 말합니다. [OpenAI Responses API (Spring AI)](https://docs.spring.io/spring-ai/reference/api/chat/openai-responses-chat.html)

즉, 운영 중인 서비스가

- 다중 후보(n)
- seed 고정 기반의 결정론적 회귀 테스트

같은 패턴에 의존했다면, Responses 전환은 기능 제거에 가깝습니다.

### 4) OpenAI strict mode 기본값 변화와 MCP tool schema

Spring AI 2.1의 Upgrade Notes는 OpenAI tool schema strict mode 기본값이 `false`로 바뀌었다고 명시합니다(예전 기본 strict(true)에서 optional parameter가 있는 schema가 400으로 거절되는 문제가 있었다는 설명 포함). 필요하면 `OpenAiChatOptions#strict(true)`로 되돌릴 수 있습니다. [Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)

동시에 2.1 라인에서는 strict mode를 켰을 때 Spring AI가 JSON schema를 `additionalProperties: false` 형태로 backfill 해서, Spring AI 밖에서 온 schema(예: MCP tool schema)도 strict mode에 맞게 동작하도록 고쳤다는 릴리스 노트가 있습니다. [Spring AI 2.1.0-M1 발표](https://spring.io/blog/2026/09/25/spring-ai-2-1-0-M1-available-now/)

운영 관점에서 이건 다음을 의미합니다.

- tool schema가 “프롬프트 문자열”이 아니라, 실제 계약 문서가 됩니다.
- schema drift는 곧바로 400 장애나 tool-call 실패로 나타납니다.

이 주제는 예전에 “조용한 변경이 더 무섭다”는 관점으로 정리한 적이 있는데, Responses API/strict schema 쪽은 특히 그 경향이 강합니다. [API/정책의 조용한 변경 리스크](https://daewooki.github.io/posts/2026-3-ai-api-1/)

## MCP 2026-07-28: 세션이 빠진 프로토콜이 Spring 앱 구조를 바꾼다

MCP 2026-07-28은 프로토콜 레벨에서 세션과 handshake를 제거합니다.

- `initialize`/`initialized` 교환이 사라지고
- `Mcp-Session-Id`도 retire 되며
- 각 요청이 프로토콜 버전과 client capabilities를 `_meta`로 싣고 갑니다

이 내용은 MCP 공식 블로그가 명확히 적고 있습니다. [MCP 2026-07-28 스펙 글](https://blog.modelcontextprotocol.io/posts/2026-07-28/)

Spring AI 쪽도 이 개정판을 “stateless revision”으로 요약하면서, modern/legacy를 병행 지원하고, modern에서는 `subscriptions/listen`으로 변화 알림을 받는 구조를 문서화합니다. [Spring AI 2.1.0 GA 발표](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/), [MCP overview (Spring AI)](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-overview.html), [MCP Modern Servers (Spring AI)](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/mcp/server/modern.html)

MCP Java SDK 역시 2.2 라인에서 modern(2026-07-28)과 legacy(이전 리비전)를 동일 모듈에서 side-by-side로 제공한다고 설명합니다. [MCP Java SDK 2.2.0 문서](https://java.sdk.modelcontextprotocol.io/v2.2.0/)

여기서 애플리케이션 아키텍처에 직접 영향을 주는 포인트는 두 가지입니다.

### 1) 로드밸런서/스케일 전략이 단순해진다

handshake/session이 사라졌다는 것은 sticky session이 없어도 된다는 뜻입니다. MCP 블로그는 “plain round-robin LB 뒤에 어떤 인스턴스로 가도 된다”고까지 표현합니다. [MCP 2026-07-28 스펙 글](https://blog.modelcontextprotocol.io/posts/2026-07-28/)

에이전트 서버는 대개 tool server를 여러 개 붙이는데, 이 구조에서 sticky session은 운영 복잡도를 급격히 올립니다. MCP가 그 부담을 프로토콜에서 빼 버린 셈입니다.

### 2) 상태는 “연결”이 아니라 “메시지”로 이동한다

세션이 없어졌다고 해서 애플리케이션이 stateless가 되는 건 아닙니다. 상태는 남습니다. 다만 상태가 연결에 묶이지 않고, 요청/응답 페이로드(혹은 애플리케이션이 발급한 handle)로 이동합니다.

이건 Session API의 방향과 닮았습니다.

- Session API: framework는 stateless, 상태는 session log
- MCP 2026-07-28: 프로토콜은 stateless, 상태는 각 request의 metadata와 애플리케이션 데이터

운영 관점에서는 “상태의 위치를 어디에 둘지”가 다시 설계 대상이 됩니다.

## (실행 가능한) 최소 구성 코드: Session + Tool 승인 + Responses API 설정을 한 프로젝트에 묶기

뉴스 분석 글이라도, 이번 변화는 코드 없이 이해하면 실제 도입에서 틀어질 확률이 높습니다. 아래 예시는 다음을 한 번에 확인하는 목적입니다.

- Spring AI 2.1.0 / Spring Boot 4.2.x 전제
- Session JDBC repository
- Tool Call Confirmation(승인 대기 → decision → 재개)
- OpenAI Responses API로 엔드포인트 전환(설정)

OpenAI 호출은 비용과 키가 필요하니, 테스트에서는 모델을 fake로 대체할 수 있게 구조를 잡습니다.

### 프로젝트 전제(버전/요구사항)

- Spring Boot 4.2.0은 최소 Java 17을 요구합니다. [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- Spring AI 2.1.0도 Java 17+ 및 Spring Boot 4를 요구합니다. [Spring AI Reference index](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/index.html)
- Spring AI BOM 2.1.0을 import 해서 의존성 버전 결합을 고정합니다. [Spring AI Project Setup](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/get-started/project-setup.html)

### pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
  </parent>

  <groupId>io.github.daewooki</groupId>
  <artifactId>spring-ai-2-1-session-ops</artifactId>
  <version>0.1.0</version>

  <properties>
    <java.version>21</java.version>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-bom</artifactId>
        <version>2.1.0</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <!-- OpenAI model (ChatClient/ChatModel). We will switch it to Responses API by property. -->
    <dependency>
      <groupId>org.springframework.ai</groupId>
      <artifactId>spring-ai-starter-model-openai</artifactId>
    </dependency>

    <!-- Session API + JDBC repository auto-config -->
    <dependency>
      <groupId>org.springframework.ai</groupId>
      <artifactId>spring-ai-starter-model-session-jdbc</artifactId>
    </dependency>

    <dependency>
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
      <scope>runtime</scope>
    </dependency>

    <!-- tests -->
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>

    <!-- Session repository contract tests live here -->
    <dependency>
      <groupId>org.springframework.ai</groupId>
      <artifactId>spring-ai-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

### docker-compose.yml (PostgreSQL)

```yaml
services:
  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: agent
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: agent
    ports:
      - "5432:5432"
```

### application.yml

`spring.ai.session.repository.jdbc.initialize-schema=always`는 Session JDBC 스키마를 개발 환경에서 자동으로 깔기 위한 설정입니다. 문서에서 PostgreSQL/MySQL 개발 환경은 always를 권장합니다. [JDBC Repository 문서](https://docs.spring.io/spring-ai/reference/api/session/jdbc.html)

그리고 Responses API 전환은 `spring.ai.openai.chat.api=responses`입니다. [OpenAI Responses API (Spring AI)](https://docs.spring.io/spring-ai/reference/api/chat/openai-responses-chat.html)

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/agent
    username: agent
    password: agent

  ai:
    openai:
      api-key: ${OPENAI_API_KEY}
      chat:
        api: responses

    session:
      repository:
        jdbc:
          initialize-schema: always

logging:
  level:
    org.springframework.ai: INFO
```

### Tool 정의: 승인 필요한 작업을 명시적으로 표시

승인 대상 tool을 `@Tool(requiresConfirmation = true)`로 표시할 수 있습니다. [Tool Call Confirmation 문서](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)

```java
package io.github.daewooki.agent.tools;

import org.springframework.ai.tool.annotation.Tool;
import org.springframework.stereotype.Component;

@Component
public class BillingTools {

    @Tool(description = "Find an invoice by id")
    public String findInvoice(String invoiceId) {
        // demo: pretend we queried DB
        return "{\"invoiceId\":\"" + invoiceId + "\",\"status\":\"ISSUED\",\"amount\":42000}";
    }

    @Tool(description = "Issue a refund for an invoice", requiresConfirmation = true)
    public String issueRefund(String invoiceId, int amount) {
        // demo: pretend we called payment gateway
        return "{\"invoiceId\":\"" + invoiceId + "\",\"refunded\":" + amount + "}";
    }
}
```

### ChatClient 구성: SessionAdvisors + recall tool + 업무 tool

SessionAdvisors는 turn advisor + memory advisor를 기본 순서로 등록합니다. [ChatClient Integration (Session)](https://docs.spring.io/spring-ai/reference/api/session/chat-client.html)

recall은 `SessionRecallTools`로 `conversation_search` tool을 모델에게 제공합니다. [Recall 문서](https://docs.spring.io/spring-ai/reference/api/session/recall.html)

```java
package io.github.daewooki.agent.config;

import io.github.daewooki.agent.tools.BillingTools;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.session.SessionService;
import org.springframework.ai.session.advisor.SessionAdvisors;
import org.springframework.ai.session.compaction.TurnCountTrigger;
import org.springframework.ai.session.compaction.WindowCompactionStrategy;
import org.springframework.ai.session.tool.SessionRecallTools;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AgentConfig {

    @Bean
    ChatClient chatClient(ChatModel chatModel, SessionService sessionService, BillingTools billingTools) {
        return ChatClient.builder(chatModel)
            .defaultAdvisors(SessionAdvisors.builder(sessionService)
                .compaction(new TurnCountTrigger(20), WindowCompactionStrategy.builder().lastTurns(10).build())
                .sessionIdInToolContext(false)
                .build())
            .defaultTools(
                SessionRecallTools.builder(sessionService).build(),
                billingTools
            )
            .build();
    }
}
```

### HTTP API: session 생성 → 메시지 전송 → 승인 대기 감지

Tool Call Confirmation 문서가 안내하는 감지 방법은 `ToolCallDecisions.awaitingDecision(reply)`입니다. [Tool Call Confirmation 문서](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)

```java
package io.github.daewooki.agent.web;

import java.util.List;
import java.util.Map;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.model.tool.ToolCallDecisions;
import org.springframework.ai.session.Session;
import org.springframework.ai.session.SessionService;
import org.springframework.ai.session.advisor.SessionAdvisors;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
public class AgentController {

    private final ChatClient chatClient;
    private final SessionService sessionService;

    public AgentController(ChatClient chatClient, SessionService sessionService) {
        this.chatClient = chatClient;
        this.sessionService = sessionService;
    }

    @PostMapping("/sessions")
    public Map<String, Object> createSession() {
        Session session = sessionService.create();
        return Map.of("sessionId", session.id());
    }

    @PostMapping("/sessions/{sessionId}/messages")
    public Map<String, Object> send(@PathVariable String sessionId, @RequestBody Map<String, String> body) {
        String user = body.get("message");

        ChatResponse reply = chatClient.prompt()
            .user(user)
            .advisors(SessionAdvisors.session(sessionId))
            .call()
            .chatResponse();

        List<String> awaiting = ToolCallDecisions.awaitingDecision(reply);
        if (!awaiting.isEmpty()) {
            // paused: return tool call list + keys
            return Map.of(
                "paused", true,
                "awaitingKeys", awaiting,
                "toolCalls", reply.getResult().getOutput().getToolCalls()
            );
        }

        return Map.of(
            "paused", false,
            "answer", reply.getResult().getOutput().getText()
        );
    }
}
```

여기까지는 “승인 대기 감지”까지만 됩니다. 승인 후 재개(resume)는 `ToolCallingManager.executeToolCalls(prompt, reply, decisions)`가 필요한데, 이 부분은 애플리케이션이 “paused reply”와 “해당 reply를 만든 prompt”를 보존해야 합니다. 문서가 명시하는 대로, 프레임워크는 pause 동안 아무 상태도 들고 있지 않습니다. [Tool Call Confirmation 문서](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)

내 경우에는 승인 워크플로우가 들어가는 순간, 대화를 Session에만 저장한다고 끝이 아니고 “승인 대기 턴”을 별도 테이블로 저장하는 설계를 같이 가져가야 했습니다. 그래야 재시작/재배포에서 승인 상태가 유실되지 않습니다.

## 회의론과 반론: 변화가 크면 운영 비용도 늘어난다

이번 릴리스의 방향이 마음에 들어도, 회의적으로 봐야 하는 지점이 있습니다.

### 1) Session은 강력하지만, 애플리케이션 설계 부담을 프레임워크 밖으로 밀어낸다

Session에 기본 세션이 없고(공유 금지), advisors는 stateless이며, pause/resume도 framework stateless입니다. 운영에 적합한 선택이지만, 그만큼 애플리케이션이 책임져야 할 것이 명확해집니다. [Spring AI 2.1.0 GA 발표](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/), [ChatClient Integration (Session)](https://docs.spring.io/spring-ai/reference/api/session/chat-client.html)

- session id 발급/전달/보안
- session TTL
- session id가 tool context로 새는 문제
- 승인 대기 턴의 저장/복구

이런 것들을 “프레임워크가 알아서 해주겠지”로 접근하면 도입 비용이 오히려 늘어납니다.

### 2) Responses API는 좋아 보이지만, 제약이 명시돼 있다

Spring AI Responses 문서의 Limitations는 꽤 냉정합니다.

- 일부 옵션은 무시
- audio in/out 미지원
- server-side conversation state 미구현
- store는 항상 false

그리고 “reasoning continuity”가 어떤 저장소에서는 잃을 수 있다고도 적어 둡니다. 이건 실제로 도입 전에 재현 테스트가 필요합니다. [OpenAI Responses API (Spring AI)](https://docs.spring.io/spring-ai/reference/api/chat/openai-responses-chat.html)

### 3) MCP 2026-07-28은 아키텍처 단순화이면서도, 생태계 마이그레이션 비용이다

스펙이 stateless로 바뀌면 서버가 단순해지지만, 기존 클라이언트/서버가 혼재하는 과도기가 길어질 수 있습니다. MCP Java SDK가 modern/legacy를 side-by-side로 지원하는 것도 그 과도기를 전제로 합니다. [MCP Java SDK 2.2.0 문서](https://java.sdk.modelcontextprotocol.io/v2.2.0/)

프로토콜 churn이 잦은 구간에서는, 표준화의 혜택을 누리기 전에 “호환성 비용”이 먼저 옵니다.

## 앞으로 지켜볼 것: Spring AI Agent, 그리고 세션 저장소의 확장

Spring AI 2.1 GA 발표는 “early December”에 Spring AI Agent(별도 프로젝트)가 incubating을 시작한다고 예고합니다. Session/Tool confirmation/tool limits 같은 harness 기능을 2.1에 먼저 밀어 넣은 이유가 여기서 설명됩니다. [Spring AI 2.1.0 GA 발표](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/)

또 하나는 Session 저장소의 확장입니다.

- 2.1 기준 JDBC store는 PostgreSQL/MySQL/MariaDB/SQL Server/H2를 지원합니다. [JDBC Repository 문서](https://docs.spring.io/spring-ai/reference/api/session/jdbc.html)
- ChatMemory repository들은 deprecate 되었고, Cassandra/Neo4j/MongoDB/Redis용 Session store는 3.0 전에 제공 계획이라고 Upgrade Notes가 말합니다. [Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)

운영에서 중요한 질문은 결국 이것입니다.

- “내가 쓰는 persistence tier에서 Session이 first-class가 되는 시점이 언제인가”

RDB를 쓰면 지금 당장 갈 수 있고, NoSQL 중심이면 과도기가 생깁니다.

## 지금 할 수 있는 일: 회귀 테스트 포인트를 ‘계약’으로 못 박기

2.1.0 GA를 바로 올리느냐는 팀마다 다르지만, “연말/연초 에이전트 제품화” 흐름을 대비한다면 다음 작업들은 선행해 두는 편이 낫습니다.

1) ChatMemory 기반 기능을 “동작”이 아니라 “언제 깨지는지” 기준으로 재점검하고, Session으로 옮겼을 때의 계약을 정의합니다. ChatMemory는 3.0에서 제거될 예정입니다. [Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)

2) Session compaction/recall의 계약을 테스트로 고정합니다.

- 턴 경계 보장
- boundary append-only 보장
- recall의 bound(pageSize/maxTextLength) 보장

관련 API/동작은 문서에 비교적 상세합니다. [Compaction 문서](https://docs.spring.io/spring-ai/reference/api/session/compaction.html), [Recall 문서](https://docs.spring.io/spring-ai/reference/api/session/recall.html)

3) tool call 승인 플로우는 UI 문제가 아니라 장애 복구 모델이므로, pause/resume을 “재시작 후에도 된다” 수준으로 재현합니다. 문서가 pause 동안 framework stateless임을 명시합니다. [Tool Call Confirmation 문서](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)

4) Responses API 전환은 단순 toggle이 아니라 옵션/메타데이터/스트리밍 계약이 바뀌는 변경이므로, 기존 회귀 테스트(usage/token, streaming metadata, finish reason)에 영향을 주는 포인트를 뽑아냅니다. [OpenAI Responses API (Spring AI)](https://docs.spring.io/spring-ai/reference/api/chat/openai-responses-chat.html)

5) MCP는 2026-07-28 stateless 리비전이 “프로덕션 스케일링 비용”을 깎아주는 방향이지만, 혼재 구간의 호환성 비용이 발생하므로, 서버/클라이언트가 modern/legacy 중 무엇을 말하는지 명시적으로 설정하고 관측 가능하게 만듭니다. [MCP 2026-07-28 스펙 글](https://blog.modelcontextprotocol.io/posts/2026-07-28/), [MCP Modern Servers (Spring AI)](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/mcp/server/modern.html)

정리하면, Spring AI 2.1.0 GA는 “에이전트 데모를 더 그럴듯하게 만드는” 업데이트가 아니라, 운영에서 실패 모드를 계약으로 끌어올리는 업데이트입니다.

## 참고 자료

- [Spring AI 2.1.0 GA 발표](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/)
- [Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)
- [Migrating to Session Memory](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/upgrading/session-memory.html)
- [Session Memory 문서](https://docs.spring.io/spring-ai/reference/api/session.html)
- [Session Concepts (Turn)](https://docs.spring.io/spring-ai/reference/api/session/concepts.html)
- [Compaction 문서](https://docs.spring.io/spring-ai/reference/api/session/compaction.html)
- [Recall 문서](https://docs.spring.io/spring-ai/reference/api/session/recall.html)
- [JDBC Repository 문서](https://docs.spring.io/spring-ai/reference/api/session/jdbc.html)
- [Tool Call Confirmation 문서](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)
- [Tool Calling 문서](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [OpenAI Responses API (Spring AI)](https://docs.spring.io/spring-ai/reference/api/chat/openai-responses-chat.html)
- [Spring AI Message Parts 블로그](https://spring.io/blog/2026/10/28/spring-ai-message-parts-reasoning-replay/)
- [MCP 2026-07-28 스펙 글](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [MCP Java SDK 2.2.0 문서](https://java.sdk.modelcontextprotocol.io/v2.2.0/)
- [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring AI Project Setup](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/get-started/project-setup.html)
- [OpenAI reasoning guide](https://developers.openai.com/api/docs/guides/reasoning?api-mode=responses&site_locale=en)
- [OpenAI cookbook: reasoning items](https://developers.openai.com/cookbook/examples/responses_api/reasoning_items)
- [Tool use + function calling 프로덕션 구현 패턴](https://daewooki.github.io/posts/2026-5-ai-agent-tool-use-function-callin-1/)
- [API/정책의 조용한 변경 리스크](https://daewooki.github.io/posts/2026-3-ai-api-1/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
