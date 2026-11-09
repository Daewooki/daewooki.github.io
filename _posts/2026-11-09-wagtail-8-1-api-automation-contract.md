---
title: "Wagtail 8.1 업그레이드 포인트: API·자동화 변화가 계약을 흔드는 지점"
description: "Wagtail 8.1의 v3 API·워크플로·캐시 변화가 API 응답/권한/인덱싱 계약을 어떻게 바꾸는지 운영 관점에서 정리합니다."
date: 2026-11-09 11:24:58 +0900
categories: ["Backend", "Wagtail"]
tags: ["wagtail", "django", "cms", "api-contract", "workflow", "caching"]
render_with_liquid: false
---

## CMS가 아니라 API 서버로 보기 시작하면 업그레이드 난이도가 달라집니다

Wagtail 업그레이드가 어려운 이유는 코드 변경량이 많아서가 아닙니다. 운영 중인 서비스에서 Wagtail은 이미 Admin UI만 제공하는 CMS가 아니라, 콘텐츠 모델을 정의하고 권한과 워크플로를 강제하며, 캐시와 서치 인덱싱을 흔드는 백엔드 서버이기 때문입니다. 그래서 Wagtail의 기능 추가는 곧 백엔드 계약(API contract)의 재정의로 이어집니다.

Wagtail 8.1(릴리스 노트 날짜: 2026-11-02)은 그 성격이 더 강합니다. 릴리스 노트와 가이드에서 반복되는 메시지가 “API로 더 많은 CMS 작업을 자동화하고, agent-ready한 도구(CLI/skills)로 운영을 바꾼다” 쪽으로 기울어져 있습니다. 특히 v3 API 개선, 워크플로 작업의 API 노출, Accept 헤더 기반 콘텐츠 협상(같은 URL의 다중 표현), 그리고 캐시/사이트맵/리다이렉트 동작 변경이 한 덩어리로 묶여 있습니다. 각각은 개별 기능처럼 보이지만, 실제 운영에서는 한 번에 연쇄 반응을 만듭니다.

이 글은 Wagtail 8.1을 **Django 기반 CMS**가 아니라 **백엔드 API 서버**로 놓고, 업그레이드 시 계약이 흔들리는 지점을 (1) API 응답 스키마, (2) 권한/워크플로, (3) 캐시/서치 인덱싱 관점으로 재구성한 운영 가능한 업그레이드 가이드입니다.  
근거는 전부 1차 소스(공식 문서/릴리스 노트/공식 블로그/코어 저장소 릴리스/공식 가이드)로 제한했습니다.

## 8.1에서 “계약”이 바뀌는 지점만 추려보면

### 날짜/지원 범위가 먼저 체크포인트입니다

- Wagtail 8.1 릴리스 노트 기준 날짜는 **2026-11-02**입니다. [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)  
- Python 지원도 움직였습니다. 8.1은 Python 3.15를 공식 지원으로 추가했고, 동시에 Python 3.10 지원을 제거했습니다. 즉, 업그레이드 순서가 “Wagtail 먼저”가 아니라 “런타임 먼저”가 됩니다. [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]

여기서 이미 계약 변화가 하나 나옵니다. 운영 환경의 Python minor 업그레이드가 가능한지(빌드 이미지, 런타임 보안 스캔, native dependency 호환성)가 먼저고, 그 다음에 Wagtail이 됩니다.

### v3 API가 “자동화의 API”로 더 커졌습니다

릴리스 노트에 명시된 v3 API 개선 항목 자체가 “어떤 콘텐츠 모델이 API로 편집 가능한가”를 바꾸는 리스트입니다.

- TypedTableBlock의 write 요청 지원
- Nested inline relations의 write 요청 지원
- v3용 `ImageRenditionField`
- 페이지/`WorkflowMixin` 스니펫에 대한 워크플로 작업 API 지원
- StreamField block schemas, 관계/Redirects까지 포함한 더 많은 스키마 디테일
- rich text의 `markdown` 출력 품질 개선(링크 주변 스타일, 줄바꿈, 인용/리스트 등)

출처: [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]

가이드 문서도 “테이블 블록과 nested inline relation을 Admin 없이 API로 생성/업데이트 가능”을 하이라이트로 뽑습니다. [New in Wagtail 8.1](https://guide.wagtail.org/en/releases/new-in-wagtail-8-1/)[^2]

이게 왜 계약을 흔드냐면, 기존에는 “Wagtail은 사람이 Admin에서 편집하고, API는 읽기 전용”이라는 전제가 꽤 단단했습니다. 8.x에서 그 선이 빠르게 옅어지고 있고, 8.1은 그 변화가 실제 업무 흐름(워크플로 승인/반려)까지 들어왔습니다.

### 내부 Admin API가 사실상 끊겼습니다

Wagtail 8.1은 문서에 이렇게 박아 놓습니다.

- `/admin/api/main/` 기반의 internal API가 교체되었고
- 새 API는 `/admin/api/explorer/<id>/` 단일 엔드포인트만 제공
- 기존의 listing/detail/actions(예: `/admin/api/main/pages/<id>/action/publish/`) 및 `construct_admin_api` hook 제거
- 필요하면 v3 API를 쓰라고 명시

출처: [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]

이건 “문서화되지 않은 내부를 썼으니 네 탓”으로 끝나는 문제가 아닙니다. 많은 팀이 Admin UI를 대체하려는 게 아니라, **편집기 편의를 위해 페이지 트리를 외부 도구에서 탐색**하거나, **사내 운영툴이 페이지 publish를 간접 호출**하는 형태로 `/admin/api/main/`을 슬쩍 얹어둡니다. 8.1은 그 길을 닫고 v3 API로 이동시키는 릴리스입니다.

### 캐시/사이트맵/리다이렉트: SEO·인덱싱 계약이 바뀝니다

8.1의 캐시/인덱싱 관련 변경은 “기능 개선”이라기보다 **운영 중 KPI(유입/색인/캐시 적중률)**에 직접 영향을 주는 종류입니다.

- `ajax_template`를 쓰는 페이지의 응답에 `Vary: X-Requested-With`가 추가됩니다. 캐시가 AJAX fragment와 full page를 분리 저장하게 되며, `Vary`를 존중하는 shared cache는 엔트리가 늘어 히트율/용량이 변할 수 있다고 문서에 명시합니다. [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]
- 다국어 사이트에서 sitemap이 모든 locale의 트리를 포함하도록 바뀝니다(`WAGTAIL_I18N_ENABLED=True`). sitemap 엔트리 수가 늘 수 있다고 명시합니다. [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]
- sitemap 문서에는 sitemap 뷰를 `cache_page()`로 감싸 캐싱하는 방법이 공식적으로 들어갔고, 다국어에서 alternate link(hreflang)가 자동 추가된다고 설명합니다. [Sitemap generator](https://docs.wagtail.org/en/v8.1/reference/contrib/sitemaps.html)[^3]
- 페이지 이동/slug 변경 시 frontend cache purge가 들어갔습니다. [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]
- 리다이렉트 자동 생성이 “draft 이동/이름 변경”에는 더 이상 발생하지 않고, live 페이지에 대해서만 동작하도록 바뀝니다. 이전 동작을 원하면 `WAGTAILREDIRECTS_AUTO_CREATE = 'always'`로 되돌릴 수 있다고 명시합니다. [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]

이 조합은 “업그레이드 후 API만 정상”이 아니라 “업그레이드 후 색인이 깨졌다/캐시 비용이 튀었다/리다이렉트가 누락됐다” 같은 형태로 사고가 납니다.

## (1) API 응답 스키마: v3 API 개선이 만드는 계약 변화

### v3는 고정 스키마로 가고, v2는 시간표가 생겼습니다

8.1에서 v2 API는 당장 바뀌지 않지만, 공식적으로 deprecation 플랜이 잡혔습니다.

- Wagtail 8.2부터 built-in v2 API 사용 시 deprecation warning
- Wagtail 8.3(LTS)에서도 포함되지만 warning 유지
- Wagtail 9.0에서 v2 API가 Wagtail 본체에서 제거, 별도 패키지로 유지 예정
- 다만 `APIField`/`api_fields`는 v2/v3가 공유하며 deprecated가 아니라고 명시

출처: [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html), [Migrating from the v2 API](https://docs.wagtail.org/en/v8.1/advanced_topics/api/v3/migration.html)[^1]

운영 관점에서 중요한 건 “언젠가 바뀐다”가 아니라 “계약을 언제부터 이중으로 유지해야 하냐”입니다. 내 경험상 모바일 앱/외부 파트너가 물고 있는 API는 릴리스 1~2번으로는 못 치웁니다. v2와 v3를 당분간 병행한다는 판단이 현실적일 수 있습니다.

### v2 vs v3: 계약이 깨지는 지점을 문서가 대놓고 짚습니다

공식 migration 문서에서 v2와 v3 차이를 표로 비교하는데, 계약 관련해서 특히 위험한 항목은 다음입니다.

- Pagination envelope: v2는 `{"meta": {"total_count": N}, "items": [...]}`, v3는 `{"count": N, "items": [...]}`
- v3는 `?fields=`(rich projection) 미지원, 고정/generated schema
- 에러 포맷이 DRF 메시지 딕셔너리에서 Problem Details로 바뀜
- Unknown query: v2는 거부, v3는 “알 수 없는 임의 필터를 종종 skip”
- 인증/가시성: v3에서 bearer-authenticated 요청은 권한에 따라 draft-only 페이지까지 보일 수 있음

출처: [Migrating from the v2 API](https://docs.wagtail.org/en/v8.1/advanced_topics/api/v3/migration.html)[^4]

이건 단순히 “응답 JSON 모양이 다르다”가 아닙니다.

- envelope가 바뀌면 클라이언트 pagination 로직이 깨집니다.
- `?fields=` 미지원은 API gateway에서 필드 단위 비용 최적화나 backward compatible response shaping을 하던 팀에 타격입니다.
- unknown filter skip은 가장 위험합니다. v2에서는 잘못된 필터를 보내면 실패해서 빨리 발견되는데, v3에서 조용히 무시되면 “데이터가 줄지 않는다/필터가 안 먹는다”가 조용히 운영 장애가 됩니다.

나는 이런 케이스를 AI API 정책 변경에서도 많이 봤습니다. 스펙이 깨지는 변경보다 더 무서운 건 조용히 동작 의미가 바뀌는 변경입니다. 이 관점은 예전에 쓴 글[^5]과도 결이 같습니다.

### 8.1의 “v3 개선”은 스키마를 더 구체화합니다

8.1 릴리스 노트가 v3 개선으로 “StreamField block schemas”, “ForeignKey/ManyToMany/GenericRelation/Redirects 스키마 디테일”을 명시합니다. 즉, API가 자기 자신을 더 자세히 설명하기 시작합니다. [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]

이 변화는 긍정적으로 보면 OpenAPI 기반 계약 테스트(contract test) 작성이 쉬워지는 방향입니다. 하지만 팀이 이미 자체적으로 “우리가 원하는 형태의 JSON schema”를 별도로 운영해왔다면, 이제는 Wagtail generated schema가 더 강한 기준점이 됩니다.

내 경우에는 여기서 선택지가 두 개로 갈립니다.

1) Wagtail schema를 진실의 원천(source of truth)으로 삼고, 외부 계약은 이를 wrapping한다.
2) 외부 계약을 진실의 원천으로 두고, Wagtail API는 내부 자동화/편집 파이프라인 전용으로 제한한다.

8.1처럼 API가 워크플로까지 커지면, (2)를 선택해도 결국 내부 자동화의 사용자가 늘어나 “내부 API도 사실상 공용 API”가 됩니다. 그래서 (1)에 가까운 운영이 필요해지는 팀이 많아질 겁니다.

### 같은 URL에서 JSON/Markdown을 내보내는 기능이 생기면, API 계약이 페이지 서빙까지 올라옵니다

8.1의 “Varying page responses”는 Accept 헤더 기반으로 같은 URL을 서로 다른 representation으로 응답할 수 있다고 설명합니다. 예시로 JSON(“API clients”)과 Markdown(“AI agents”)을 직접 언급합니다. [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]

이 기능이 들어오면, 페이지 렌더링이 더 이상 “HTML 한 가지 계약”이 아닙니다.

- CDN 캐시 키는 Accept/Vary 정책을 어떻게 가져가야 하는지
- 검색 봇/프리뷰 봇이 어떤 Accept를 보내는지
- 내부 링크 프리뷰(슬랙/디스코드/카카오워크)가 어떤 representation을 받는지

이걸 대충 처리하면 HTML 페이지 계약이 깨지고, 반대로 HTML만 생각하면 JSON/Markdown 계약이 깨집니다.

## (2) 권한/워크플로: API 자동화가 RBAC를 다시 정의합니다

### 워크플로 작업이 API로 열리면 “승인”이 백엔드 기능이 됩니다

Wagtail 8.1은 v3 API에서 워크플로 작업을 공식적으로 노출합니다. 가이드가 기능 설명을 아주 직설적으로 씁니다.

- pages 및 `WorkflowMixin` 스니펫에 대해
- workflow submit/approve/reject/resume/cancel
- status/history read

출처: [New in Wagtail 8.1](https://guide.wagtail.org/en/releases/new-in-wagtail-8-1/), [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^2]

워크플로 API 문서는 엔드포인트를 명시합니다.

- `POST /pages/{page_id}/actions/workflow/submit/`
- `POST /pages/{page_id}/actions/workflow/approve/` (body: `comment`, `task_state_id`)
- `POST /pages/{page_id}/actions/workflow/reject/` (body: `comment`, `task_state_id`)
- `POST /pages/{page_id}/actions/workflow/resume/`
- `POST /pages/{page_id}/actions/workflow/cancel/`
- `GET /pages/{page_id}/workflow/`
- `GET /pages/{page_id}/workflow/history/`

출처: [Workflows (v3 API)](https://docs.wagtail.org/en/stable-8.1.x/advanced_topics/api/v3/workflows.html)[^6]

이제 “승인 UI를 어디서 제공하냐”가 선택지로 열립니다.

- Admin UI에서만 승인한다 → 기존과 동일
- 사내 Slack bot이 승인/반려한다 → 승인 이벤트가 백엔드 API 호출로 바뀜
- 외부 시스템(Jira, ServiceNow)이 승인/반려를 트리거한다 → 권한 모델/감사 로그/토큰 운영이 백엔드 책임

### permission 모델이 미묘하게 넓습니다: approve/reject가 모델 권한 없이 가능할 수 있습니다

워크플로 API 문서는 approve/reject에 대해 “페이지/스니펫 모델 권한이 필요하지 않다”고 명시합니다. `GroupApprovalTask` 기준으로는 승인 그룹 멤버십이면 된다고 설명합니다. 또한 reads(`/workflow/`, `/workflow/history/`)도 외부 moderation UI를 위해 Admin보다 넓게 설계되었다고 말합니다. [Workflows (v3 API)](https://docs.wagtail.org/en/stable-8.1.x/advanced_topics/api/v3/workflows.html)[^6]

이게 운영에서 왜 중요하냐면, 많은 팀이 “편집 권한 없는 승인자”를 별도 시스템으로 분리합니다.

- 승인자는 콘텐츠 내용을 수정할 권한은 없고
- 승인/반려만 가능하며
- 어떤 경우에는 draft 본문 전체를 외부로 노출하면 안 됩니다

그런데 v3 API는 “승인 그룹만으로 status를 읽고 approve/reject 가능”한 모델을 열어 둡니다. 즉, API 토큰/계정 설계를 잘못하면, 생각보다 넓은 가시성을 열 수 있습니다.

여기서 계약은 API 스키마가 아니라 **인증 주체의 의미**입니다.

- “automation token”이 사람을 대표하는가
- “moderator token”이 어떤 페이지 타입까지 접근 가능한가
- workflow history가 외부 시스템으로 나가도 되는가(개인정보/코멘트 포함 가능)

### action layer가 Admin과 동일하다는 말은 “부작용까지 동일”이라는 뜻입니다

페이지 액션 문서는 v3 API의 actions가 Admin UI와 동일한 action layer를 타고 실행되며, permissions/revisions/audit logs/hooks/signals가 보존된다고 명시합니다. [Pages (v3 API)](https://docs.wagtail.org/en/stable-8.1.x/advanced_topics/api/v3/pages.html)[^7]

워크플로 문서도 워크플로 작업이 동일한 action layer를 통해 실행되어 locking/revisions/audit logs/hooks/signals/notification emails가 Admin과 동일하게 동작한다고 설명합니다.[^6]

이건 좋은 소식이면서 위험한 소식입니다.

- 좋은 점: API 자동화가 Admin과 불일치하는 “유령 상태”를 만들 가능성이 줄어듭니다.
- 위험한 점: API 호출이 곧바로 이메일/웹훅/서치 인덱싱/캐시 purge 같은 부작용을 발생시킬 수 있습니다.

즉, v3 API는 “쓰기 API”라는 이유만으로 별도 샌드박스 취급하기 어렵고, 운영 이벤트 파이프라인 전체에 붙어 있는 진짜 백엔드 엔드포인트로 봐야 합니다.

## (3) 캐시/서치 인덱싱: 8.1에서 사고가 나는 패턴

### `ajax_template`의 `Vary: X-Requested-With`는 CDN 비용과 히트율을 흔듭니다

8.1 업그레이드 고려사항에 다음이 명시됩니다.

- `ajax_template`를 정의한 페이지의 응답에 `Vary: X-Requested-With`가 포함
- 캐시가 AJAX fragment와 full page를 분리 저장
- 이전에는 같은 키로 저장되어 fragment가 일반 요청에 잘못 제공될 수 있었음
- `Vary`를 존중하는 shared cache는 페이지당 엔트리가 하나 더 생겨 cache size/hit ratios가 바뀔 수 있음

출처: [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]

이 변경은 기능적으로는 “정합성 개선”인데, 운영에서는 다음 리스크가 큽니다.

- CDN이 `Vary`를 존중하는데, 캐시 용량을 빠듯하게 잡아둔 경우 eviction이 빨라져 히트율이 떨어집니다.
- 반대로 CDN이 `Vary`를 무시하도록 설정되어 있으면(커스텀 캐시 정책) 8.1의 의도대로 분리되지 않아 예전과 같은 오염이 계속됩니다.
- WAF/프록시에서 `X-Requested-With` 헤더를 삭제하거나 normalize하는 경우, 분리 키가 의미가 없어집니다.

여기서 중요한 건 “Wagtail이 Vary를 붙인다”가 아니라, 이제는 페이지 서빙이 API 계약처럼 **헤더 계약**까지 포함하게 됐다는 점입니다.

### slug 이동 시 frontend cache purge가 들어오면, purge 쿼터/속도가 병목이 됩니다

릴리스 노트의 other features에 “페이지 이동/slug 변경 시 frontend cache purge”가 포함됩니다. [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]

frontend cache invalidator 문서는 WAGTAILFRONTENDCACHE 설정과 다국어 purge를 위한 `WAGTAILFRONTENDCACHE_LANGUAGES`를 설명합니다. [Frontend cache invalidator](https://docs.wagtail.org/en/v8.1/reference/contrib/frontendcache.html)[^8]

또 8.1에서 Cloudflare backend에 `PURGE_BATCH_SIZE` 파라미터가 추가되었고(Added in version 8.1), 기본 30 URL batch를 바꿀 수 있다고 명시합니다. [Frontend cache invalidator](https://docs.wagtail.org/en/v8.1/reference/contrib/frontendcache.html)[^8]

여기서 실제 사고 패턴은 이렇습니다.

- 콘텐츠 팀이 slug를 대량으로 손보는 이벤트를 한다(연말 개편, 캠페인 페이지 리네이밍 등)
- purge가 연쇄로 발생한다
- Cloudflare/Varnish/CloudFront purge API limit에 걸린다
- 방문자는 오래된 URL을 보거나, redirect가 늦게 반영되거나, 새 페이지가 404처럼 보인다

8.1에서 purge가 더 “잘” 일어나게 된 만큼, purge를 **얼마나 자주/얼마나 많이** 보낼지에 대한 운영 파라미터가 중요해집니다. `PURGE_BATCH_SIZE` 같은 항목은 단순 설정이 아니라 비용/지연/limit의 트레이드오프입니다.

### sitemap이 모든 locale을 포함하면, 색인 계약이 바뀝니다

업그레이드 고려사항에 `WAGTAIL_I18N_ENABLED=True`일 때 sitemap이 모든 locale의 page tree를 포함하도록 바뀐다고 명시돼 있습니다. [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]

sitemap 문서는 더 구체적으로:

- `wagtail.contrib.sitemaps.views.sitemap`를 써야 하며
- sitemap은 요청마다 생성되고
- `cache_page()`로 감싸 캐싱할 수 있고
- i18n 활성화 시 모든 locale을 포함하며 번역 페이지의 alternate link(hreflang)가 자동 추가된다고 설명합니다.

출처: [Sitemap generator](https://docs.wagtail.org/en/v8.1/reference/contrib/sitemaps.html)[^3]

여기서 계약은 “검색 엔진이 무엇을 본다고 가정할 것이냐”입니다.

- 기존에는 기본 locale만 sitemap에 나가고, 나머지는 내부 링크로만 발견되던 사이트가
- 8.1 이후에는 모든 번역 페이지가 sitemap에서 직접 노출될 수 있습니다.

좋은 변화처럼 보이지만, locale별로 공개 정책이 다르거나(예: 일본어는 일부만 공개), 번역이 incomplete한 상태가 운영에 존재한다면, sitemap이 그 상태를 외부에 노출합니다. 색인 품질이 흔들리면 트래픽 KPI가 흔들립니다.

또 하나는 성능입니다.

- sitemap이 요청마다 생성되면 DB load가 올라가고
- 그래서 `cache_page()` 캐싱을 넣으면
- 이제는 캐시 TTL 동안 sitemap이 늦게 갱신됩니다.

즉, 8.1은 sitemap에서 “정확성 vs 비용” 선택을 강요합니다. 운영 가능한 절충안을 잡아야 합니다.

### 리다이렉트 자동 생성 정책 변화는 링크 보존 정책을 흔듭니다

8.1에서는 페이지 이동/이름 변경 시 redirect 자동 생성이 live 페이지에 대해서만 동작하도록 바뀌고, 예전 동작은 `WAGTAILREDIRECTS_AUTO_CREATE = 'always'`로 복구 가능하다고 명시합니다. [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]

운영에서는 보통 draft 상태에서 구조 개편을 준비합니다.

- draft로 디렉터리 구조를 옮기고
- 검수/승인을 받고
- go-live 시점에 publish

이 과정에서 redirect가 자동으로 쌓여야 “예전 링크가 깨지지 않는” 운영을 기대하는 팀이 많습니다. 8.1 기본 동작은 그 기대를 깨뜨릴 수 있습니다.

여기서 계약은 두 가지입니다.

- 유입 계약: 과거 URL이 얼마나 오래 살아야 하는가
- 운영 계약: redirect 생성은 누가 언제 책임지는가(사람 vs 자동)

만약 redirect를 API로 외부 시스템에서 관리한다면(v2 기준으로 redirects endpoint를 붙이는 패턴이 문서에 있습니다), 이 변경은 그 시스템과의 책임 경계를 다시 그리게 합니다. [Redirects](https://docs.wagtail.org/en/stable-8.1.x/reference/contrib/redirects.html)[^9]

## 업그레이드 절차를 “운영 가능한” 형태로 바꾸기

### 1) 런타임 게이트: Python 3.10이면 먼저 멈춥니다

8.1은 Python 3.10 지원을 제거했습니다. 이건 CI가 깨지는 정도가 아니라, 배포 파이프라인 전체를 먼저 손봐야 한다는 의미입니다. [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]

나는 보통 다음 순서로 갑니다.

- base image/빌드팩에서 Python 업그레이드
- native dependency(wheels, libjpeg, libmagic 등) 재검증
- 테스트 환경에서 Wagtail upgrade

Wagtail 업그레이드 PR이 런타임 변경 PR과 합쳐지면 리뷰가 지옥이 됩니다.

### 2) v2 API 의존도 측정: 제거가 아니라 ‘언제까지 유지할지’를 결정합니다

8.1 시점에서 v2는 즉시 폐기 대상은 아닙니다. 하지만 8.2/8.3/9.0 타임라인이 생겼기 때문에, 지금은 “이 API는 몇 년 갈 거다” 같은 막연한 감이 아니라 릴리스 기반 계획을 세울 수 있습니다. [Migrating from the v2 API](https://docs.wagtail.org/en/v8.1/advanced_topics/api/v3/migration.html)[^4]

내가 체크하는 항목은 다음입니다.

- 외부 클라이언트가 v2 envelope(`meta.total_count`)에 결합돼 있는가
- `?fields=` 같은 projection 기능을 적극 활용하고 있는가(v3는 미지원)[^4]
- 잘못된 필터를 보내면 실패하는 것을 전제로 에러 핸들링이 구성돼 있는가(v3는 skip 가능)[^4]

이걸 보면 “v3로 갈 수 있다/없다”가 아니라 “v3로 갈 때 계약을 어디서 흡수할지”가 나옵니다.

### 3) `/admin/api/main/` 사용 여부: 쓰고 있으면 8.1은 곧바로 breaking입니다

릴리스 노트에 internal admin API 교체가 박혀 있습니다. [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]

여기서 중요한 건 “내가 직접 안 쓴다”가 아니라:

- 사내 운영툴이 쓰는지
- 프론트엔드가 page explorer 데이터를 끌어다 쓰는지
- 과거 외주/이전 팀이 남긴 JS가 호출하는지

운영에서 이런 류는 보통 모니터링에 안 잡힙니다. 8.1 업그레이드 전 staging에 붙여놓고 네트워크 로그를 떠야 합니다.

### 4) 캐시/인덱싱 계약 테스트: 기능 테스트보다 먼저 둡니다

8.1은 페이지 응답 representation과 sitemap/redirect/cache purge까지 건드립니다. 그래서 나는 단순 “페이지가 뜬다”보다 아래를 먼저 봅니다.

- 특정 페이지의 response header에 `Vary`가 어떻게 붙는지(특히 `ajax_template`)[^1]
- slug 변경/페이지 이동 시 purge가 어떤 URL들을 날리는지(다국어 purge 포함)[^8]
- sitemap 엔트리 수가 locale별로 얼마나 늘어나는지, alternate link가 잘 붙는지[^3]

이걸 보고 나서야 기능 QA가 의미가 있습니다.

## 코드로 검증하는 업그레이드: “콘텐츠 모델 → API 쓰기 → 워크플로”까지 연결

여기서는 장난감 예제 대신, 실제로 팀에서 흔히 필요한 시나리오를 잡았습니다.

- 마케팅/PR 팀이 캠페인 랜딩 페이지를 Wagtail에서 관리합니다.
- 개발팀은 외부 시스템(사내 캠페인 관리 툴)에서 초안을 자동 생성합니다.
- 초안은 Wagtail workflow로 제출되고, 승인 그룹이 approve/reject를 합니다.
- 프론트는 headless로 v3 API를 통해 콘텐츠를 읽습니다.

Wagtail 8.1에서 핵심은 “workflow가 API로 열린다”는 점입니다.

### 환경 준비(로컬)

다음은 최소 단계입니다. Python은 3.11 이상이어야 합니다(8.1에서 Python 3.10 지원 제거). [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)[^1]

```bash
# 1) 가상환경
python -m venv .venv
source .venv/bin/activate

# 2) Wagtail 설치
pip install "wagtail==8.1"

# 3) 프로젝트 생성
wagtail start cmsdemo
cd cmsdemo

# 4) 실행
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

여기까지는 Wagtail 표준 플로우입니다.

### v3 API가 전제하는 페이지 쓰기 모델: `meta.type` + union payload

v3 API의 page create는 request body가 discriminated union이라고 문서에 설명돼 있습니다. `meta.type`이 concrete page type을 선택하고, 나머지 필드가 writable fields가 됩니다. 최소 create request 예시도 문서에 있습니다. [Pages (v3 API)](https://docs.wagtail.org/en/v8.1/advanced_topics/api/v3/pages.html)[^10]

문서의 예시를 그대로 쓰면:

```bash
export TOKEN="<YOUR_BEARER_TOKEN>"

curl -X POST "https://example.com/api/v3/pages/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "meta": {"type": "blog.BlogPage", "parent_id": 3, "action": "publish"},
    "title": "Example",
    "slug": "example"
  }'
```

성공 시 201을 반환하고 type-specific page detail이 온다고 명시합니다. [Pages (v3 API)](https://docs.wagtail.org/en/v8.1/advanced_topics/api/v3/pages.html)[^10]

여기서 업그레이드 관점의 포인트는 두 가지입니다.

1) 스키마가 고정/generated이기 때문에, page type의 `api_fields` 구성 변화가 곧바로 API 계약 변화가 됩니다.
2) `meta.action=publish` 같은 동작 제어가 body에 들어오면서, API 호출 한 번이 곧 publish side-effect를 만듭니다.

### workflow submit/approve/reject: 이제 “승인”은 API 호출입니다

워크플로 엔드포인트는 문서에 명시되어 있습니다. [Workflows (v3 API)](https://docs.wagtail.org/en/stable-8.1.x/advanced_topics/api/v3/workflows.html)[^6]

페이지를 workflow로 제출:

```bash
curl -X POST "https://example.com/api/v3/pages/3/actions/workflow/submit/" \
  -H "Authorization: Bearer $TOKEN"
```

approve/reject는 body로 `comment`와 `task_state_id`를 받습니다. [Workflows (v3 API)](https://docs.wagtail.org/en/stable-8.1.x/advanced_topics/api/v3/workflows.html)[^6]

```bash
curl -X POST "https://example.com/api/v3/pages/3/actions/workflow/approve/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"comment": "LGTM", "task_state_id": 123}'
```

status/history 조회:

```bash
curl -X GET "https://example.com/api/v3/pages/3/workflow/" \
  -H "Authorization: Bearer $TOKEN"

curl -X GET "https://example.com/api/v3/pages/3/workflow/history/" \
  -H "Authorization: Bearer $TOKEN"
```

이 흐름이 중요한 이유는, 이제 워크플로를 외부에서 호출할 수 있기 때문에 “승인 프로세스”가 백엔드 통합 과제가 됩니다.

- 누가 어떤 토큰으로 submit하는지
- approve/reject 권한을 어떤 그룹에 주는지(문서는 모델 권한 없이도 가능할 수 있음을 명시)[^6]
- comment가 외부 시스템 로그로 복제되어도 되는지

이걸 정리하지 않으면, 자동화가 늘수록 권한 사고 가능성이 늘어납니다.

### v2에서 v3로 갈 때, 계약 깨짐을 코드로 잡는 포인트

migration 문서가 “high-risk migration areas”를 정리해 둔 게 실전적입니다. 나는 아래를 테스트로 박아버립니다.

- list envelope가 v2/v3에서 다른지(`meta.total_count` vs `count`)[^4]
- `?fields=` 의존이 있는지(v3 미지원)[^4]
- 에러 포맷이 DRF vs Problem Details로 바뀌는지[^4]
- unknown filter가 실패하는지/무시되는지(v3에서 skip 가능)[^4]

여기서 중요한 건 “v3가 더 낫다/나쁘다”가 아니라, 계약 검증을 QA가 아니라 테스트로 옮겨야 한다는 점입니다.

## 도입 판단 기준: 8.1을 ‘올릴지 말지’가 아니라 ‘어디까지 올릴지’

Wagtail 8.1은 업그레이드 항목이 기능 몇 개 추가된 정도가 아니라, 다음 축을 동시에 움직입니다.

- API가 읽기에서 쓰기/액션/워크플로로 확장됨(자동화의 표면적 확대)
- 페이지 서빙이 Accept 기반 다중 표현으로 확장됨(헤더 계약/캐시 계약 변화)
- sitemap/redirect/cache purge 변경이 SEO/인덱싱 KPI로 직결됨
- 내부 Admin API가 교체되어, “조용히 쓰고 있던 운영툴”이 깨질 수 있음

그래서 내 결론은 단순합니다.

- Wagtail을 Admin UI 중심으로만 쓰는 팀이라도, 8.1은 캐시/사이트맵/리다이렉트 때문에 운영 체크가 필요합니다.
- Wagtail을 headless/v2 API로 쓰는 팀은 8.1에서 곧바로 v3 전환을 강요받지는 않지만(8.1에서는 v2 변경 없음), 8.2/8.3/9.0 타임라인이 생겼기 때문에 지금부터 계약을 이중화하거나 마이그레이션 계획을 세워야 합니다.[^1]
- 워크플로 자동화를 하려는 팀에게 8.1은 의미가 큽니다. 다만 approve/reject/read 권한 범위가 넓을 수 있으므로 토큰/그룹 설계를 먼저 확정해야 합니다.[^6]

8.1 업그레이드는 기능을 얻는 작업이 아니라, 콘텐츠 모델/권한/캐시/인덱싱을 포함한 백엔드 계약을 다시 쓰는 작업입니다.

## 참고 자료

- [Wagtail 8.1 release notes](https://docs.wagtail.org/en/v8.1/releases/8.1.html)
- [New in Wagtail 8.1](https://guide.wagtail.org/en/releases/new-in-wagtail-8-1/)
- [Migrating from the v2 API](https://docs.wagtail.org/en/v8.1/advanced_topics/api/v3/migration.html)
- [Pages (v3 API)](https://docs.wagtail.org/en/v8.1/advanced_topics/api/v3/pages.html)
- [Workflows (v3 API)](https://docs.wagtail.org/en/stable-8.1.x/advanced_topics/api/v3/workflows.html)
- [Sitemap generator](https://docs.wagtail.org/en/v8.1/reference/contrib/sitemaps.html)
- [Frontend cache invalidator](https://docs.wagtail.org/en/v8.1/reference/contrib/frontendcache.html)
- [Redirects](https://docs.wagtail.org/en/stable-8.1.x/reference/contrib/redirects.html)
- [How to vary page responses](https://docs.wagtail.org/en/v8.1/advanced_topics/varying_page_responses.html)
- [Wagtail release schedule (GitHub Wiki)](https://github.com/wagtail/wagtail/wiki/Release-schedule)
- [wagtail/wagtail GitHub releases](https://github.com/wagtail/wagtail/releases?after=v2.6)

[^1]: <https://docs.wagtail.org/en/v8.1/releases/8.1.html>
[^2]: <https://guide.wagtail.org/en/releases/new-in-wagtail-8-1/>
[^3]: <https://docs.wagtail.org/en/v8.1/reference/contrib/sitemaps.html>
[^4]: <https://docs.wagtail.org/en/v8.1/advanced_topics/api/v3/migration.html>
[^5]: <https://daewooki.github.io/posts/2026-3-ai-api-1/>
[^6]: <https://docs.wagtail.org/en/stable-8.1.x/advanced_topics/api/v3/workflows.html>
[^7]: <https://docs.wagtail.org/en/stable-8.1.x/advanced_topics/api/v3/pages.html>
[^8]: <https://docs.wagtail.org/en/v8.1/reference/contrib/frontendcache.html>
[^9]: <https://docs.wagtail.org/en/stable-8.1.x/reference/contrib/redirects.html>
[^10]: <https://docs.wagtail.org/en/v8.1/advanced_topics/api/v3/pages.html>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
