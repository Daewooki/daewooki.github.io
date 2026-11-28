---
title: "Go 1.28 composite literal 타입 생략이 팀에 미치는 영향"
description: "Go 1.28의 composite literal 타입 생략이 gofmt, 리뷰 규칙, 생성 코드, linter, 점진적 적용 전략에 미치는 영향을 정리합니다."
date: 2026-11-28 16:07:58 +0900
categories: ["Languages", "Go"]
tags: ["go", "go1-28", "composite-literal", "gofmt", "static-analysis", "refactoring"]
render_with_liquid: false
---

## 규칙이 바뀌는 지점: 문법보다 타입 흐름

Go 팀은 2026-11-10에 공개한 글에서, Go 1.28이 composite literal에서 컨텍스트로 타입이 추론되면 중복 타입을 생략할 수 있게 해 오랜 요구를 해결한다고 밝혔습니다.[^1]  
이 변화는 문법 설탕으로 끝나지 않습니다. 팀 코드베이스 관점에서는 타입 정보가 “어디에 남아 있고”, “어디에서 사라질 수 있는지”의 경계가 달라집니다.

이미 Go는 slice/array/map literal 안쪽에서 요소 타입을 생략하는 규칙이 오래 전부터 있었습니다. Go 1.28은 그 규칙을 **assignment context** 전반으로 확장합니다. 즉, 바깥이 다른 composite literal이냐 아니냐가 아니라, “이 위치에서 컴파일러가 목표 타입(target type)을 갖고 있느냐”가 핵심이 됩니다.[^2]

이 글의 초점은 새 문법 자체의 예제가 아니라, 팀이 실제로 겪게 되는 운영 이슈들입니다.

- gofmt가 자동으로 바꿔서 PR이 터지느냐
- 리뷰어가 무엇을 금지/허용해야 코드가 덜 흐려지느냐
- protobuf/openapi 등 코드 생성기가 이 문법을 언제부터 써야 하느냐
- linter/gopls/staticcheck 같은 툴링이 어디까지 따라오느냐
- 파일/패키지 단위로 점진 적용을 어떻게 설계하느냐

결론부터 정리하면, Go 1.28 도입이 팀에 주는 가장 큰 영향은 “코드가 갑자기 짧아진다”가 아니라 “짧게 쓸 수 있는 영역을 팀이 통제하지 않으면, 읽기 비용이 들쭉날쭉해진다”입니다.

## 확정된 스펙: 어디까지 타입을 생략할 수 있나

Go 1.28 draft release notes는 다음을 명시합니다.

- Go 1.28부터 composite literal 타입은, assignment context로부터 타입이 추론 가능하면 생략할 수 있습니다.
- 이전에는 array/slice/map literal 안에서만 제한적으로 가능했습니다.[^2]

이 내용은 language spec(Go 1.28 버전)에도 동일하게 반영돼 있습니다. 특히 spec에는 map value/key, pointer 기대 타입까지 예제가 들어가 있어 팀 정책을 만들 때 기준점으로 쓰기 좋습니다.[^3]

핵심 규칙을 팀 문서로 옮기면 다음과 같은 형태가 됩니다.

1) 어떤 위치에서 컴파일러가 목표 타입 T를 알고 있다면, `T{...}` 대신 `{...}`를 쓸 수 있습니다.[^3]  
2) 목표 타입이 `*T`라면, `&T{...}` 대신 `{...}`를 쓸 수 있습니다(주소 연산자도 생략 가능).[^3]  
3) 반대로 목표 타입이 없으면 `{...}`는 여전히 불법입니다(예: `q := {1,2}`).[^3]

이 규칙이 실제 코드에 미치는 파급이 큰 케이스는 대체로 네 군데입니다.

- 설정 struct: `Config{TLS: &tls.Config{...}}` 같은 패턴
- 요청/응답 struct: REST/gRPC 요청을 struct로 조립하는 코드
- table-driven test: 케이스 struct 안에 struct가 중첩되는 형태
- generated builder 제거 후 평범한 struct literal로 회귀하는 코드

이 변화가 “오래된 요구”였다는 역사적 근거는 proposal 이슈에서 확인 가능합니다. 2015-10-06에 올라온 `spec: type inferred composite literals`(#12854)가 그 출발점입니다.[^4]

## gofmt가 자동으로 바꾸지 않는다는 사실이 더 중요하다

팀 운영 관점에서 가장 먼저 확인해야 할 건 gofmt입니다. 많은 팀이 “새 문법이 추가되면 gofmt가 -s로 싹 줄이겠지, 그럼 대규모 PR이 터지겠지”를 먼저 걱정합니다.

현재 tip의 gofmt `simplify.go`를 보면, composite literal 타입 생략은 여전히 기존 규칙(바깥 array/slice/map literal의 element type과 정확히 일치할 때)만 대상으로 합니다. 코드상으로도 `outer literal`의 element type과 `inner composite literal`의 타입이 매칭되면 `inner.Type = nil`로 떨어뜨리는 방식입니다.[^5]

즉, Go 1.28이 `{...}`를 더 넓은 위치에서 허용하더라도,

- gofmt는 단순히 포맷팅을 맞추는 역할이고
- gofmt의 `-s`는 제한적인 범위의 rewrite만 수행합니다

라는 전제가 유지됩니다.

이게 왜 중요하냐면, Go 1.28 도입이 곧바로 **대규모 PR 폭탄**으로 이어질 가능성은 생각보다 낮습니다. 자동 변환이 없으면, 변화는 “사람이 쓰는 코드”에서 천천히 발생합니다. 반대로 말하면, 팀이 정책을 세우지 않으면, 어느 날부터 PR마다 `{...}`가 조금씩 섞이기 시작하고 코드 스타일의 일관성이 깨지는 쪽이 더 흔한 실패 모드입니다.

여기서 팀이 자주 착각하는 포인트가 하나 더 있습니다.

- “새 문법이 들어오면 gofmt 결과가 달라진다”

이건 절반만 맞습니다. gofmt 출력은 문법 트리를 동일한 스타일로 출력할 뿐이고, 코드를 자동으로 `{...}`로 바꾸지 않는 이상, 기존 코드의 gofmt 결과가 크게 바뀌지는 않습니다. 바뀌는 건 보통 두 가지입니다.

- 개발자가 새 문법을 쓰기 시작하면서 diff의 스타일이 달라짐
- gopls/code action이나 팀 내부 codemod가 `{...}`를 도입하면서 diff가 커짐

그래서 팀 전략은 gofmt가 아니라 “새 문법을 누가, 어디서, 어떤 규칙으로 쓰게 할 것인가”로 잡는 편이 맞습니다.

## 리뷰 규칙: 읽기 비용을 낮추는 최소 원칙

이 문법은 타입을 생략하기 때문에, 읽는 사람이 타입을 복원하는 비용을 지불합니다. 문제는 그 비용이 균일하지 않다는 겁니다. 같은 `{...}`라도,

- 바로 옆 필드명이 타입을 강하게 암시하면 부담이 적고
- 선언이 다른 파일/패키지에 있으면 부담이 커집니다.

그래서 팀 레벨의 리뷰 규칙은 “무조건 쓰자/무조건 쓰지 말자”가 아니라, 타입 복원 비용이 낮은 지점만 허용하는 방식이 실전적으로 안전합니다.

내가 코드베이스에 적용한다면, 최소 원칙은 다음처럼 가져갑니다.

### 원칙 1: outermost composite literal은 typed로 유지

Go 1.28은 `var origin Point = {}` 같은 형태를 허용합니다.[^2]  
하지만 팀 규칙으로는 outermost는 typed를 유지하는 편이 낫습니다.

- 함수 인자/리턴/필드 값으로 `{...}`는 허용할 수 있지만
- “이 값이 어떤 타입인지”를 알려주는 앵커(anchor)는 남겨야 합니다.

예를 들어 이런 형태는 유지합니다.

- `req := CreateOrderRequest{ ... }`
- `cfg := Config{ ... }`

그리고 이 안쪽에서만 `{...}`를 허용합니다.

이 원칙은 코드 리뷰에서 논쟁을 줄여줍니다. “여기까지는 무조건 타입이 보인다”가 합의되면, 나머지는 생략 여부가 취향이 아니라 규칙이 됩니다.

### 원칙 2: struct field value에서는 적극 허용

가장 효과가 큰 곳이 여기입니다.

- `TLS: &tls.Config{...}` → `TLS: {...}`
- `Retry: RetryPolicy{...}` → `Retry: {...}`

필드 이름이 타입의 의미를 대부분 설명하는 경우가 많아서 타입 복원 비용이 낮습니다. 게다가 Go 1.27에서 struct literal key가 nested/embedded selector를 허용하면서, composite literal의 중첩 깊이가 실제로 더 늘어나는 경향이 있습니다.[^6]

이 상황에서 Go 1.28 `{...}`는 “깊어지는 중첩을 더 읽기 쉽게 만들 수 있는” 방향으로 작동합니다.

### 원칙 3: function argument로 `{...}`를 넘기는 건 제한

스펙상 `draw({1,2})` 같은 형태도 가능합니다.[^3]  
하지만 팀 룰에서는 금지하거나, 아주 제한적으로만 허용하는 게 낫습니다.

이유는 간단합니다.

- 함수 시그니처를 보지 않으면 타입을 모름
- 오버로드가 없는 Go에서는 호출이 간단해 보여도, 타입은 호출부만 보고는 복원하기 어렵다

호출부에서 타입이 명시되는 편이 읽기 비용이 낮습니다.

- `client.Do(http.Request{...})`는 호출부만 봐도 명확
- `client.Do({ ... })`는 `Do`의 시그니처를 찾아가야 함

특히 패키지 경계를 넘는 호출에서 `{...}`는 리뷰 비용을 올립니다.

### 원칙 4: interface/any 컨텍스트에서는 어차피 못 쓴다

스펙에도 나오지만 `{...}`는 컨텍스트가 타입을 제공하지 못하면 불법입니다. 예를 들어 `q := {1,2}`는 불법이고, `var a any = {1,2}` 같은 형태도 불가능합니다.[^3]

이건 팀 규칙으로 해결할 문제가 아니라, 컴파일러가 막는 영역입니다. 그래서 실제로는 `{...}`가 폭발적으로 퍼지는 지점이 “any 기반 DSL” 같은 곳은 아닙니다. 오히려 강타입 struct를 많이 쓰는 설정/요청 코드에서만 퍼집니다.

### 원칙 5: pointer 기대 타입에서 `{...}`는 효과가 크지만, escape를 의식

spec은 pointer 컨텍스트에서 `{...}`가 `&T{...}`로 해석된다고 명시합니다.[^3]  
이건 기존에도 `&T{...}`를 쓰던 코드라면 의미상 변화는 없습니다. 다만 팀 내 합의로 “이건 heap으로 갈 가능성이 높다”는 감각을 잃지 않는 편이 좋습니다.

성능 최적화가 중요한 코드에서는 `&T{...}`라는 형태가 눈에 띄는 경고 역할을 하기도 했습니다. `{...}`로 바뀌면 그 시각적 신호가 약해집니다. 이런 코드(allocator pressure를 직접 다루는 hot path)에서는 타입 생략을 더 보수적으로 가져가는 편이 안전합니다.

## 생성 코드와 DSL: 옵션 플래그 없이는 도입하지 않는다

대규모 설정/요청 struct는 사람이 손으로만 쓰지 않습니다.

- protobuf / grpc-gateway
- OpenAPI generator
- internal DSL
- 사내 SDK의 request builder

이런 생성 코드가 `{...}`를 쓰기 시작하면 팀에 두 가지 일이 동시에 일어납니다.

1) 생성 결과물이 갑자기 “새 Go 버전”을 전제하기 시작함
2) 생성 코드 diff가 의미 없이 커져서, 실제 변경점 리뷰가 어려워짐

여기서 가장 중요한 사실은, Go 1.28 문법은 “컴파일러가 언어 버전으로 게이트”한다는 점입니다. types2 구현을 보면 `{...}`를 처리할 때 `go1_28` 버전 체크를 걸고, 언어 버전이 낮으면 `missing type in composite literal` 같은 에러를 내도록 되어 있습니다.[^7]

즉 생성기가 `{...}`를 출력하려면, 적어도 아래 중 하나가 선행되어야 합니다.

- 모듈의 `go` directive를 1.28 이상으로 올림
- 생성 코드가 포함된 모듈/서브모듈만 먼저 1.28로 올림

그래서 생성기 전략은 다음처럼 가져가는 편이 현실적입니다.

- 기본값: 기존과 동일하게 typed literal을 출력
- 옵션 플래그: `--go=1.28` 또는 `--complit=elide` 같은 형태로 명시적 opt-in
- golden file 테스트: generator 업그레이드 시 스타일 변화로 인한 diff 폭발을 조기에 감지

특히 protobuf 같은 생태계에서는 “팀 내부 서비스는 1.28인데, 외부 공개 라이브러리는 1.27을 유지해야 한다” 같은 상황이 자주 생깁니다. 생성기가 기본값으로 `{...}`를 뿌리면, 라이브러리 사용자가 도구체인을 강제로 올려야 해서 호환성 문제가 됩니다.

생성 코드는 사람이 읽지 않으니 짧을수록 좋다는 주장도 있는데, 내 경험상 생성 코드는 결국 사람이 읽습니다. 장애 대응이나 payload 확인을 할 때, 그리고 사람이 만든 코드를 생성 코드 스타일에 맞추려고 할 때 특히 그렇습니다. 예전에 [OpenTelemetry Go Logs RC로 시작하는 로그 표준화](https://daewooki.github.io/posts/otel-go-logs-rc-adoption/) 같은 작업을 할 때도, 설정 struct를 사람이 직접 다루는 구간과 자동 생성/자동 변환 구간이 섞이면서 스타일 일관성이 생각보다 큰 비용으로 돌아왔습니다.

## linters와 IDE: 권고가 아니라 정책으로 만들기

툴링은 크게 세 층으로 나뉩니다.

- 컴파일러/언어 스펙: 무엇이 가능한지
- 포맷터/리라이터: 무엇이 자동으로 바뀌는지
- 정적 분석/리뷰 룰: 팀이 무엇을 허용하는지

앞에서 말했듯 gofmt는 자동 대변환을 해주지 않습니다. 그러면 남는 건 정적 분석과 리뷰 자동화입니다.

### gopls가 제공하는 기존 simplifycompositelit의 한계

gopls에는 `simplifycompositelit` 같은 분석기가 있는데, 현재 구현을 보면 array/slice/map composite literal 내부에서만 “중복 타입 제거”를 다룹니다.[^8]  
이건 Go 1.28의 “assignment context 전반”과는 범위가 다릅니다.

즉 Go 1.28 도입 직후에는 이런 상태가 되기 쉽습니다.

- 개발자는 `{...}`를 점점 많이 쓰고
- gofmt는 바꾸지 않으며
- gopls도 팀 정책을 대신해주지 못한다

그래서 팀이 원하면, 팀 정책은 별도의 체크로 만들어야 합니다.

### Go 1.28의 go/analysis 편입이 의미하는 것

Go 1.28 release notes에는 Go analysis framework API가 표준 라이브러리로 들어온다고 적혀 있습니다. (드라이버와 analyzer의 인터페이스가 사실상 표준화되는 방향입니다.)[^2]

이건 두 가지 측면에서 중요합니다.

- 사내 linters를 `go vet` 파이프라인에 붙이기가 쉬워질 가능성
- 도구체인 업그레이드와 함께 정적 분석 파이프라인도 같이 정리할 타이밍

다만 “표준 라이브러리에 들어왔으니 자동으로 해결된다”로 해석하면 안 됩니다. 표준화는 기반이고, 어떤 정책을 enforce할지는 여전히 팀 몫입니다.

## 점진적 적용: 파일/패키지 단위로 들어가는 운영 시나리오

Go 1.28 도입을 PR 폭탄으로 만들지 않으려면, 도입 순서를 명확히 해야 합니다. 내가 선호하는 순서는 다음입니다.

### 1) 도구체인 업그레이드와 스타일 도입을 분리

- 1단계: Go 1.28로 빌드/테스트/배포가 되는지 확인
- 2단계: 스타일을 바꾸는 건 별도의 정책과 함께 제한적으로 시작

이걸 분리하지 않으면, “도구체인 업그레이드 PR”이 스타일 변경까지 끌고 가면서 리뷰가 지옥이 됩니다.

Go 팀이 2026-11-10 글에서 `go fix`와 정적 분석 투자를 강조한 것도, 팀 코드베이스 운영에서 이런 분리를 지원하려는 방향으로 읽힙니다.[^1]

### 2) go directive(`go 1.28`)를 언제 올릴지 결정

실무에서 `{...}` 문법은 “컴파일 가능한가”라는 제약을 만들기 때문에, 결국 `go.mod`의 `go` directive를 올리는 순간부터 코드 스타일이 갈라질 수 있습니다.

- `go 1.27`인 모듈: `{...}`를 쓰면 컴파일 에러
- `go 1.28`인 모듈: `{...}`를 쓸 수 있음

이 특성 때문에 점진 적용의 단위는 보통 아래 둘 중 하나로 고정됩니다.

- 모노레포 + 멀티 모듈: 모듈 단위로 `go 1.28` 승격
- 단일 모듈: 승격 이후에는 “어디서부터 쓸지”를 정책으로 통제

### 3) 패키지 단위 허용 영역을 정하고, 그 밖은 금지

내 경우는 보통 이런 구획을 씁니다.

- 허용: `internal/config`, `internal/api`, `*_test.go`
- 제한: `pkg/...` (외부 공개), `cmd/...` (엔트리포인트)

특히 외부에 노출되는 `pkg` 계층은 읽기 명확성이 더 중요해지는 경향이 있어서, 타입 생략을 더 보수적으로 가져갑니다.

### 4) codemod는 늦게, 아주 작게

Go 1.28이 들어오자마자 “전부 `{...}`로 바꾸자”는 거의 항상 실패합니다.

- 의미 없는 diff 폭발
- blame 오염
- 리뷰/충돌 비용 증가

대신 원칙을 잡고, 새로 쓰는 코드부터 제한적으로 `{...}`를 허용하고, 장기적으로 “자연스럽게” 섞이게 두는 편이 운영 비용이 낮았습니다.

## 실행 가능한 예제: deeply nested request를 1.28 스타일로 만들기

아래 예제는 네트워크 호출 없이도 재현 가능한 형태로, 요청 payload를 deeply nested struct로 조립하는 상황을 가정합니다.

- outermost는 typed composite literal
- 내부 필드에서만 `{...}`를 사용
- pointer 필드는 `{...}`로 `&T{...}`를 대체
- map value에서도 `{...}` 사용

Go 1.28 draft 스펙/릴리스 노트가 말하는 동작(assignment context에서 타입 생략)을 그대로 밟습니다.[^2]

### 파일 구성

```text
complit-demo/
  go.mod
  main.go
```

### go.mod

```go
module example.com/complit-demo

go 1.28
```

### main.go

```go
package main

import (
	"encoding/json"
	"fmt"
	"time"
)

type Money struct {
	Currency string `json:"currency"`
	Amount   int64  `json:"amount"`
}

type Address struct {
	Line1 string `json:"line1"`
	City  string `json:"city"`
	Zip   string `json:"zip"`
}

type Shipping struct {
	Method  string   `json:"method"`
	Address *Address `json:"address"`
}

type Customer struct {
	ID    string `json:"id"`
	Email string `json:"email"`
}

type Item struct {
	SKU string `json:"sku"`
	Qty int    `json:"qty"`
	Pay Money  `json:"pay"`
}

type CreateOrderRequest struct {
	RequestID string            `json:"request_id"`
	At        time.Time         `json:"at"`
	Customer  Customer          `json:"customer"`
	Items     []Item            `json:"items"`
	Shipping  *Shipping         `json:"shipping"`
	Metadata  map[string]string `json:"metadata"`
}

func main() {
	// Go 1.28: struct field, return/assignment context에서 { ... } 사용 가능.
	// - Customer: Customer 타입이 필드로부터 추론
	// - Items: []Item의 element type으로부터 추론
	// - Shipping: *Shipping이 기대 타입이므로 { ... }는 &Shipping{ ... }
	// - Address: *Address가 기대 타입이므로 { ... }는 &Address{ ... }
	req := CreateOrderRequest{
		RequestID: "req-20261128-0001",
		At:        time.Date(2026, 11, 28, 0, 0, 0, 0, time.UTC),
		Customer: {
			ID:    "cust_123",
			Email: "cust@example.com",
		},
		Items: {
			{
				SKU: "sku_basic",
				Qty: 2,
				Pay: {Currency: "USD", Amount: 1999},
			},
			{
				SKU: "sku_addon",
				Qty: 1,
				Pay: {Currency: "USD", Amount: 499},
			},
		},
		Shipping: {
			Method: "UPS",
			Address: {
				Line1: "1 Main St",
				City:  "Springfield",
				Zip:   "00000",
			},
		},
		Metadata: map[string]string{
			"source": "cli",
			"tier":   "free",
		},
	}

	b, err := json.MarshalIndent(req, "", "  ")
	if err != nil {
		panic(err)
	}
	fmt.Println(string(b))
}
```

### 실행 방법

Go 1.28이 아직 정식 릴리스가 아니라면, tip에서 실험하는 쪽이 안전합니다. (draft 상태에서 빠질 가능성은 남아 있습니다.)[^9]

대표적으로는 `gotip`을 설치해 사용하는 방식이 널리 쓰입니다. 실제 환경마다 도구 설치 방식이 다르니, 팀 표준(ASDF, gimme, devcontainer 등)에 맞춰 통일하는 편이 낫습니다.

실행 후 출력은 아래처럼 JSON이 찍히면 정상입니다.

```json
{
  "request_id": "req-20261128-0001",
  "at": "2026-11-28T00:00:00Z",
  "customer": {
    "id": "cust_123",
    "email": "cust@example.com"
  },
  "items": [
    {
      "sku": "sku_basic",
      "qty": 2,
      "pay": {
        "currency": "USD",
        "amount": 1999
      }
    },
    {
      "sku": "sku_addon",
      "qty": 1,
      "pay": {
        "currency": "USD",
        "amount": 499
      }
    }
  ],
  "shipping": {
    "method": "UPS",
    "address": {
      "line1": "1 Main St",
      "city": "Springfield",
      "zip": "00000"
    }
  },
  "metadata": {
    "source": "cli",
    "tier": "free"
  }
}
```

이 예제는 의도적으로 “짧아지는 부분”보다 “팀이 통제하기 쉬운 형태”를 보여줍니다.

- outermost는 타입이 남아 있어서 코드 스캔이 쉽고
- 내부는 필드명이 타입을 설명하므로 `{...}`가 읽기 난도를 크게 올리지 않습니다.

## 정책 체크 도구 예제: elided composite literal을 통제하기

새 문법이 들어오면, 결국 팀 정책은 자동화가 필요해집니다. 특히 다음 상황에서 문제가 커집니다.

- PR마다 `{...}`가 조금씩 섞이기 시작함
- 리뷰어마다 허용 기준이 다름
- 어느 순간 코드베이스에 “짧은 스타일”과 “긴 스타일”이 무질서하게 공존

여기서는 아주 단순한 정책을 강제하는 예제를 듭니다.

- 규칙: `{...}`(타입 생략 composite literal)는 struct field value 위치에서만 허용
- 그 외(함수 인자, return, assignment 등)에서는 금지

이 규칙이 절대적으로 옳아서가 아니라, “정책을 코드로 만들면 이런 식으로 점진 적용이 가능해진다”는 감을 잡기 위한 예시입니다.

### 파일 구성

```text
complit-policy/
  go.mod
  cmd/
    complitpolicy/
      main.go
```

### cmd/complitpolicy/main.go

```go
package main

import (
	"flag"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"strings"
)

func main() {
	var dir string
	flag.StringVar(&dir, "dir", ".", "directory containing .go files")
	flag.Parse()

	fset := token.NewFileSet()

	var files []*ast.File
	err := filepath.WalkDir(dir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			base := filepath.Base(path)
			if base == "vendor" || strings.HasPrefix(base, ".") {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(path, ".go") {
			return nil
		}
		if strings.HasSuffix(path, "_test.go") {
			return nil
		}

		f, err := parser.ParseFile(fset, path, nil, parser.ParseComments)
		if err != nil {
			return err
		}
		files = append(files, f)
		return nil
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}

	// parent stack을 이용해서 “struct field value 위치”만 허용한다.
	var bad int
	for _, f := range files {
		var stack []ast.Node
		ast.Inspect(f, func(n ast.Node) bool {
			if n == nil {
				stack = stack[:len(stack)-1]
				return false
			}
			stack = append(stack, n)

			cl, ok := n.(*ast.CompositeLit)
			if !ok {
				return true
			}
			if cl.Type != nil {
				return true
			}

			// Type이 nil이면: Go 1.28의 { ... } 형태.
			// 허용: KeyValueExpr의 Value로 직접 등장하며, 그 KeyValueExpr가 StructLit 내부 element인 경우
			if !isStructFieldValue(stack) {
				pos := fset.Position(cl.Lbrace)
				fmt.Fprintf(os.Stderr, "%s:%d:%d: untyped composite literal is not allowed here\n",
					pos.Filename, pos.Line, pos.Column)
				bad++
			}
			return true
		})
	}

	if bad > 0 {
		os.Exit(1)
	}
}

func isStructFieldValue(stack []ast.Node) bool {
	// stack 끝이 CompositeLit
	// ... KeyValueExpr(Value == CompositeLit)
	// ... CompositeLit(Struct)
	if len(stack) < 3 {
		return false
	}
	cl, _ := stack[len(stack)-1].(*ast.CompositeLit)
	kv, _ := stack[len(stack)-2].(*ast.KeyValueExpr)
	outer, _ := stack[len(stack)-3].(*ast.CompositeLit)
	if cl == nil || kv == nil || outer == nil {
		return false
	}
	if kv.Value != cl {
		return false
	}
	// struct literal인지 확인(outer.Type가 *ast.StructType일 수도 있지만, 대부분 Ident/SelectorExpr로 온다)
	// 여기서는 “KeyValueExpr를 쓰는 composite literal” 정도로만 좁혀도 효과가 있다.
	return true
}
```

이 툴은 의도적으로 단순합니다.

- 타입 체크를 하지 않기 때문에 오탐 가능성이 있고
- `{...}` 허용 범위가 아주 거칩니다

그럼에도 팀에 주는 메시지는 분명합니다.

- 문법이 허용하는 범위와
- 팀이 허용하는 범위는

같지 않아야 합니다. 그리고 그 차이는 리뷰어의 감이 아니라 자동화로 고정하는 편이 운영 비용이 낮습니다.

## 도입 판단: 스타일 논쟁을 피하는 가장 현실적인 결론

Go 1.28의 composite literal 타입 생략은 분명히 유용합니다. 스펙 예제 자체가 설정, API 요청, 테스트의 시각적 노이즈를 줄이겠다는 문제의식을 직접 언급합니다.[^1]

다만 팀 코드베이스에서의 성패는 “짧아지느냐”가 아니라, “짧아질 수 있는 지점을 팀이 어디까지 통제하느냐”에 달려 있습니다.

- gofmt는 자동으로 바꿔주지 않습니다.[^5]
- 대신 개발자가 조금씩 도입하면서 스타일이 자연스럽게 섞입니다.
- 그래서 도입 초기에 스타일 가이드(outermost는 typed 유지, field value 중심 허용, call arg 제한 같은 최소 규칙)를 확정하는 쪽이 비용이 적습니다.
- 생성 코드/DSL은 기본값을 유지하고, 명시적 opt-in 플래그로만 `{...}`를 도입하는 편이 호환성 리스크를 줄입니다.
- 점진 적용 단위는 파일/패키지보다 먼저 `go.mod`의 `go 1.28` 승격 타이밍에 의해 결정됩니다.[^7]

새 문법을 “더 Go답게” 쓰는 방법은, 가능한 곳에서 최대한 생략하는 게 아니라, 타입 복원 비용이 낮은 곳에서만 제한적으로 생략하는 쪽에 가깝습니다. 그 통제가 되는 팀만이, Go 1.28 도입을 대규모 스타일 PR이 아니라 생산성 개선으로 끝낼 수 있습니다.

## 참고 자료

- [Go Turns 17](https://go.dev/blog/17years)
- [Go 1.28 Release Notes (draft)](https://tip.golang.org/doc/go1.28)
- [The Go Programming Language Specification (tip, go1.28)](https://tip.golang.org/ref/spec)
- [spec: type inferred composite literals (Issue #12854)](https://github.com/golang/go/issues/12854)
- [cmd/gofmt simplify.go (tip)](https://tip.golang.org/src/cmd/gofmt/simplify.go)
- [gopls simplifycompositelit analyzer implementation](https://go.googlesource.com/tools.git/+/4653e48eb85159eef93c4634029cd73b0430f1e0/gopls/internal/analysis/simplifycompositelit/simplifycompositelit.go)
- [Go 1.27 is released](https://go.dev/blog/go1.27)
- [Release History](https://go.dev/doc/devel/release)
- [OpenTelemetry Go Logs RC로 시작하는 로그 표준화](https://daewooki.github.io/posts/otel-go-logs-rc-adoption/)

[^1]: <https://go.dev/blog/17years>
[^2]: <https://tip.golang.org/doc/go1.28>
[^3]: <https://tip.golang.org/ref/spec>
[^4]: <https://github.com/golang/go/issues/12854>
[^5]: <https://tip.golang.org/src/cmd/gofmt/simplify.go>
[^6]: <https://go.dev/blog/go1.27>
[^7]: <https://tip.golang.org/src/cmd/compile/internal/types2/literals.go>
[^8]: <https://go.googlesource.com/tools.git/%2B/4653e48eb85159eef93c4634029cd73b0430f1e0/gopls/internal/analysis/simplifycompositelit/simplifycompositelit.go>
[^9]: <https://rednafi.com/shards/2026/11/go-untyped-composite-literals/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
