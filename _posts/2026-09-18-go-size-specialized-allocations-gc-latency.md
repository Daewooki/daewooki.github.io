---
title: "Go 1.27 size-specialized allocations 이후 GC·지연시간 튜닝 관점"
description: "80B 이하 작은 heap allocation이 빨라진 뒤, 작은 객체가 많은 서비스에서 pprof/trace로 무엇을 비교해야 하는지 정리합니다."
date: 2026-09-18 10:03:57 +0900
categories: ["Performance", "Go"]
tags: ["go", "performance", "gc", "pprof", "runtime-trace", "allocator"]
render_with_liquid: false
---

Go 1.27은 작은 heap allocation을 더 싸게 만드는 방향으로 런타임·컴파일러 경로를 바꿨습니다. Go 팀이 2026-09-16에 이 변경을 별도 글로 풀어 썼고, 릴리스 노트에도 수치(최대 30%, <80B)와 opt-out(빌드 타임 GOEXPERIMENT)이 명시됐습니다.[^1]

여기서 중요한 건 “이제 allocation이 빨라졌다”가 아니라, 작은 객체가 많은 서비스에서 **GC/지연시간 회귀 테스트 항목이 바뀐다**는 점입니다. 예전엔 mallocgc가 CPU 상단에 뜨면 “alloc 줄이자”가 거의 유일한 결론이었는데, 이제는 “alloc은 그대로인데 alloc 경로가 바뀌어서 tail이 달라질 수 있는가”를 확인해야 합니다.

## size-specialized allocations가 바꾼 것은 ‘전략’이 아니라 ‘호출 경로’입니다

Go 런타임 allocator가 갑자기 다른 방식으로 메모리를 관리하기 시작한 건 아닙니다. size class, span, pointer scan 여부에 따라 다른 free list를 쓰는 구조는 원래 있었습니다. 이번 변경의 핵심은 다음 두 가지입니다.

1) 런타임에 있는 일반 경로 `mallocgc`가 하던 판단(특히 작은 사이즈에서 반복되는 분기/테이블 조회)을 줄이기 위해, span class(= size class + pointer 포함 여부)에 따라 특화된 `mallocgc` 변형 함수를 생성합니다. Go 블로그 글은 “span class별로 specialized `mallocgc` variant를 만든다”고 명시합니다.[^1]

2) 컴파일러가 allocation 크기와 pointer 포함 여부를 컴파일 타임에 알 수 있으면, 일반 경로(`newobject`→`mallocgc`) 대신 특화 함수로 바로 호출을 박아 넣습니다. 이게 “size-specialized”의 체감 효과를 만드는 구간입니다. (크기를 모르면 결국 런타임에서 결정해야 하니 이득이 제한됩니다.)[^1]

Go 블로그 글은 80B 이하에서 멈춘 이유를 instruction cache(특화 함수가 늘수록 icache 경쟁이 생김)까지 포함해서 설명합니다. 즉, allocator가 더 똑똑해진 게 아니라, hot path에서 반복되던 잔 일을 컴파일러/코드 생성으로 밀어 넣어서 “자주 할당하는 작은 것”에 한해 실행 비용을 깎았습니다.[^1]

릴리스 노트가 말하는 범위도 이 철학과 일치합니다. “<80 byte small allocation 최대 30% 절감, real allocation-heavy program 전체 ~1%, 바이너리 ~60KB 증가, GOEXPERIMENT로 opt-out 가능(1.28에 제거 예정)”이 한 문단에 같이 박혀 있습니다.[^2]

여기서 서비스 튜닝 관점으로 중요한 결론이 하나 나옵니다.

- 이전에도 “작은 heap allocation이 많으면 느려진다”는 건 같았습니다.
- 이제는 “작은 heap allocation이 많아도, 그중 ‘컴파일 타임에 크기가 고정된’ 것들은 더 싸졌다”로 바뀝니다.
- 따라서, (1) 서비스의 alloc size 분포와 (2) escape 패턴을 같이 봐야 합니다.

## 어떤 워크로드가 이득을 보나: alloc size 분포 + escape + 고정 크기 여부

릴리스 노트/블로그의 숫자(<80B)가 말하는 건 단순히 “작다”가 아닙니다. Go allocator의 size class 경계(그리고 해당 size class에 대응하는 span class)가 실제로 의미가 있습니다. Go 블로그는 80B 이하에서 size class 구간(예: 1–8, 9–16, …)을 표로 보여 주며, span class가 `sizeClass<<1 | noPointers`로 encoding된다고 설명합니다.[^1]

서비스에서 체감이 크게 나는 전형적인 조건을 정리하면 이렇습니다.

### 1) “작은데 많다”가 아니라 “작고, 고정 크기고, heap으로 간다”

컴파일러가 특화 함수를 직접 호출하려면 (대략) 아래가 만족돼야 합니다.

- allocation size가 컴파일 타임에 결정됨
- pointer 포함 여부가 타입으로 결정됨
- escape analysis 결과 heap allocation이 됨

Go 컴파일러 SSA 단계 코드를 보면, `specializedMallocMax = 80`을 넘으면 특화 심볼을 선택하지 않고, size class는 size를 나눠서 table lookup으로 구한 다음(hasPointers 여부에 따라) `MallocGCSmallNoScan[sizeClass]` 또는 `MallocGCSmallScanNoHeader[sizeClass]`를 고르는 형태입니다.[^3]

이 말은 곧 이런 해석으로 이어집니다.

- `new(T)`, `&T{...}` 같은 “타입 크기 고정” heap allocation은 이득 후보입니다.
- `make([]byte, n)`에서 `n`이 런타임 값이면(요청 크기, JSON 길이, header 길이 등) 컴파일러가 span class를 못 박기 어렵습니다. 이 경우 특화 경로의 이득은 제한됩니다(런타임에서 다시 결정해야 함).[^1]

### 2) escape를 못 하면(=stack으로 가면) 이 변경은 의미가 없습니다

Go GC/allocator 최적화의 가장 큰 레버는 여전히 “heap에 안 올리기”입니다. Go GC 가이드도 allocation rate가 GC frequency의 핵심 요인이라고 반복해서 말합니다.[^4]

size-specialized allocation은 heap allocation 비용을 깎는 거라서, stack에 머무는 값에는 원천적으로 영향이 없습니다.

따라서 “Go 1.27로 올리면 빨라진다”를 확인하려면, 단순히 allocs/op가 큰지보다 다음이 더 중요합니다.

- alloc site가 escape 때문에 heap으로 가는지
- 그 heap allocation이 <80B인지
- 그 <80B allocation이 고정 크기인지

이건 pprof 하나로는 완벽히 못 잡습니다. 보통은 다음 조합이 현실적입니다.

- `-gcflags=all=-m=2`로 escape 이유를 텍스트로 확인(어느 값이 왜 heap으로 갔는지)
- `pprof`의 `alloc_space`, `alloc_objects`로 “어디서 얼마나 할당하는지” 확인
- 필요하면 trace로 “GC assist / STW / mark phase와 tail latency 상관” 확인

### 3) 포인터 없는 작은 객체는 특히 해석이 까다롭습니다

포인터가 없는 no-scan 객체는 GC가 스캔하지 않으니, “GC 때문에 느려진다”와 “allocator/zeroing 때문에 느려진다”가 분리됩니다.

Go 블로그는 specialized 함수가 더 빨라지는 가장 큰 이유로 “작은 clear를 상수 크기로 보고 memclr 호출을 없애거나 더 단순한 instruction sequence로 바꿀 수 있다”를 들고 있습니다.[^1]

즉, 포인터 없는 16B/24B/32B 같은 allocation이 폭발하는 서비스(짧은 struct, slice backing array, 작은 byte buffer 등)는 GC보다 allocator/zeroing의 비중이 커서 이득이 더 또렷할 수 있습니다.

반대로, 포인터가 있는 객체는 스캔 비용이 뒤따르니 “할당 자체가 빨라졌는데 GC mark가 더 눈에 띄는” 역전 현상이 생길 수 있습니다(상대적으로 더 보이기 시작하는 것).

## 전후 비교에서 제일 좋은 기준선: Go 1.27 내부에서 opt-out로 가르기

Go 1.27을 올린 뒤 Go 1.26과 단순 비교하면, allocator 외 변수(표준 라이브러리 변화, 코드젠/인라이닝 변화, 다른 GOEXPERIMENT 기본값 변화 등)가 섞여서 결론이 흐려집니다.

이 변경은 릴리스 노트가 opt-out을 제공하고, 제거 시점(Go 1.28)을 예고합니다.[^2]

따라서 회귀 테스트 설계는 다음이 가장 깔끔합니다.

- 기준 A: Go 1.27 (기본)
- 기준 B: Go 1.27 + `GOEXPERIMENT=nosizespecializedmalloc`

이렇게 하면 “Go 1.27로 올라가며 생긴 변화 중, size-specialized allocation만” 최대한 분리해서 볼 수 있습니다. Go 블로그도 동일한 opt-out을 안내합니다.[^1]

주의할 점이 하나 더 있습니다.

- `-race`, sanitizer, instrumentation 계열에서는 컴파일러가 이 경로를 꺼버릴 수 있습니다. 컴파일러 코드가 `Instrumenting`이면 sizeSpecializedMalloc을 false로 본다고 되어 있습니다.[^3]

즉, “프로덕션(비-race)에서 빨라졌는데 CI의 -race 벤치에서는 변화가 없다”는 게 이상 현상이 아닙니다. 같은 바이너리 타입끼리 비교해야 합니다.

## 실측용 워크로드: 작은 heap 객체가 요청당 많이 생기는 HTTP 처리

아래 코드는 내가 서비스에서 자주 보는 패턴(요청당 context/value 체인, request-scoped metadata, 작은 buffer 생성)을 의도적으로 넣었습니다.

- 작은 struct(no pointer) heap allocation: request meta(24B)
- 작은 slice backing array(고정 크기 make): 32B, 64B
- pointer 포함 heap allocation: context 노드(32B~)
- 각 allocation이 escape하도록 “결과를 sink로 흘려서” 제거 최적화를 피함

### 디렉터리 구조

```text
sizespecialdemo/
  go.mod
  svc/
    handler.go
    handler_test.go
```

### go.mod

```go
module example.com/sizespecialdemo

go 1.27
```

### svc/handler.go

```go
package svc

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"time"
)

// 24B (8+8+4+4 padding). no pointers.
type ReqMeta struct {
	TraceID uint64
	UserID  uint64
	Flags   uint32
	_       uint32
}

// pointer-heavy request context object.
type ReqCtx struct {
	ctx  context.Context
	meta *ReqMeta
	// 작은 값이지만 포인터 포함 구조를 하나 더 둬서 스캔 비용을 현실적으로 만듭니다.	
	deadline *time.Time
}

// 외부로 새는 sink. 벤치에서 dead-code elimination을 막는 용도.
var Sink any

func Handle(ctx context.Context, traceID, userID uint64, payload []byte) []byte {
	// 요청당 메타는 흔히 heap으로 갑니다(로깅/미들웨어/비동기 처리).
	meta := &ReqMeta{TraceID: traceID, UserID: userID, Flags: uint32(len(payload))}

	// context 체인은 실제 서비스에서 꽤 자주 등장하는 작은 객체의 대표입니다.
	ctx = context.WithValue(ctx, ctxKey("trace"), meta.TraceID)
	ctx = context.WithValue(ctx, ctxKey("user"), meta.UserID)
	ctx = context.WithValue(ctx, ctxKey("flags"), meta.Flags)

	// 작은 고정 크기 버퍼를 요청마다 만드는 경우(서명/해시/encoding 등)가 많습니다.
	// make([]byte, 32/64)는 backing array가 heap으로 갈 수 있고, 80B 이하라면 후보입니다.
	buf32 := make([]byte, 32)
	binary.LittleEndian.PutUint64(buf32[0:8], traceID)
	binary.LittleEndian.PutUint64(buf32[8:16], userID)

	buf64 := make([]byte, 64)
	copy(buf64, payload)

	// 포인터 포함 객체 하나 더.
	dl := time.Now().Add(50 * time.Millisecond)
	rc := &ReqCtx{ctx: ctx, meta: meta, deadline: &dl}

	// 실제론 서명/토큰/캐시 키 계산처럼 작은 작업이 반복됩니다.
	sum := sha256.Sum256(append(buf32, buf64...))
	out := make([]byte, 32)
	copy(out, sum[:32])

	// escape를 강제.
	Sink = rc
	return out
}

type ctxKey string
```

이 코드가 “진짜 서비스”는 아니지만, 다음 점에서 장난감 예제와 다르게 동작합니다.

- context/value 체인 때문에 pointerful small allocation이 섞입니다.
- 고정 크기 byte buffer 때문에 no-scan small allocation이 섞입니다.
- sha256 때문에 약간의 CPU work가 있고, allocation이 전부는 아닙니다.

### svc/handler_test.go (bench + 프로파일 수집 플래그)

```go
package svc

import (
	"context"
	"crypto/rand"
	"testing"
)

func BenchmarkHandle(b *testing.B) {
	ctx := context.Background()
	payload := make([]byte, 256)
	_, _ = rand.Read(payload)

	b.ReportAllocs()
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		_ = Handle(ctx, uint64(i), uint64(i*7), payload)
	}
}

func BenchmarkHandleParallel(b *testing.B) {
	ctx := context.Background()
	payload := make([]byte, 256)
	_, _ = rand.Read(payload)

	b.ReportAllocs()
	b.ResetTimer()

	b.RunParallel(func(pb *testing.PB) {
		var i uint64
		for pb.Next() {
			i++
			_ = Handle(ctx, i, i*7, payload)
		}
	})
}
```

## 실측 절차 1: benchstat로 “진짜 차이”를 먼저 고정합니다

Go 1.27.1이 2026-09-01 릴리스됐다는 기록이 release history에 있습니다.[^5]

로컬에 Go 1.27이 설치되어 있다는 가정에서, 같은 머신/같은 governor로 아래처럼 수집합니다.

### 1) size-specialized allocation ON

```bash
go test -run=^$ -bench='BenchmarkHandle' -benchmem -count=10 ./svc | tee on.txt
```

### 2) size-specialized allocation OFF (기준선)

```bash
GOEXPERIMENT=nosizespecializedmalloc \
  go test -run=^$ -bench='BenchmarkHandle' -benchmem -count=10 ./svc | tee off.txt
```

### 3) benchstat

```bash
benchstat off.txt on.txt
```

예상 출력 형태는 아래처럼 나옵니다(수치는 환경에 따라 달라져서 여기서는 형태만 고정합니다).

```text
name                 old time/op    new time/op    delta
Handle-16              ...            ...          -X.XX%
HandleParallel-16      ...            ...          -X.XX%

name                 old alloc/op   new alloc/op   delta
Handle-16              ...            ...           ~0%

name                 old bytes/op   new bytes/op   delta
Handle-16              ...            ...           ~0%
```

여기서 기대하는 패턴은 이렇습니다.

- allocs/op, bytes/op는 거의 같아야 정상입니다(전략이 바뀐 게 아니라 경로가 바뀐 것).
- time/op가 줄면, 그 차이가 allocator 경로에서 온 게 맞는지(pprof)로 확인합니다.
- Parallel에서 개선이 더 크거나/작을 수 있습니다. 개선이 “per allocation CPU 절감”이라면, contention이 큰 워크로드에서는 체감이 더 선명해질 때도 있습니다(반대로 다른 병목에 묻힐 수도 있습니다).

## 실측 절차 2: pprof로 ‘시간이 어디서 빠졌는지’를 확인합니다

Go 성능 측정에서 흔히 하는 실수는 “벤치 숫자가 좋아졌다”에서 멈추는 것입니다. allocator 변경은 특히 위험합니다. tail latency가 바뀌는 건 대부분 “평균 CPU”가 아니라 “rare path, GC assist, scheduling” 쪽에서 일어나기 때문입니다.

### CPU 프로파일 수집

```bash
# ON
go test -run=^$ -bench='BenchmarkHandleParallel' -count=5 \
  -cpuprofile cpu.on.pprof ./svc

# OFF
GOEXPERIMENT=nosizespecializedmalloc \
  go test -run=^$ -bench='BenchmarkHandleParallel' -count=5 \
  -cpuprofile cpu.off.pprof ./svc
```

분석은 보통 top/cum부터 봅니다.

```bash
go tool pprof -top -cum cpu.off.pprof
go tool pprof -top -cum cpu.on.pprof
```

여기서 내가 보는 포인트는 다음입니다.

- `runtime.mallocgc`의 cum이 줄었는가
- 줄어든 시간이 “특화 malloc 함수들” 또는 “사용자 코드”로 어떻게 이동했는가
- `runtime.gcAssistAlloc` 비중이 상대적으로 커졌는가(이건 절대값이 아니라 비율의 착시일 수도 있습니다)

Go GC 가이드는 CPU 프로파일에서 `runtime.mallocgc` 누적 시간이 크면 allocation이 많다는 신호로 보고, `runtime.gcAssistAlloc` 누적 시간이 크면 mutator가 GC를 앞지르고 있다는 신호로 봅니다.[^4]

size-specialized allocation 이후에는 `runtime.mallocgc`가 줄어드는 대신 다른 이름(특화 함수)이 뜰 수도 있습니다. Go 블로그는 예시 이름으로 `mallocgcSmallNoScanSC3` 같은 형태를 직접 언급합니다.[^1]

### 메모리 프로파일: alloc_space / alloc_objects를 기준으로 봅니다

메모리 프로파일은 “현재 살아있는 힙(inuse)”만 보면 allocator 변경을 놓치기 쉽습니다. 작은 객체가 많은 서비스는 보통 live set보다 allocation rate가 문제입니다.

Go 위키는 heap 프로파일을 `--inuse_space`(기본)와 `--alloc_space`(누적 할당)로 볼 수 있다고 설명합니다.[^6]

Go GC 가이드도 “GC 비용을 줄이는 목적”에서는 `alloc_space`가 allocation rate에 대응하니 유용하다고 못 박습니다.[^4]

수집은 다음처럼 합니다.

```bash
# ON
go test -run=^$ -bench='BenchmarkHandleParallel' -count=3 \
  -memprofile mem.on.pprof ./svc

# OFF
GOEXPERIMENT=nosizespecializedmalloc \
  go test -run=^$ -bench='BenchmarkHandleParallel' -count=3 \
  -memprofile mem.off.pprof ./svc
```

분석은 보통 아래 순서가 깔끔합니다.

```bash
# 누적 할당량 관점(alloc_space)
go tool pprof -top -alloc_space mem.off.pprof
go tool pprof -top -alloc_space mem.on.pprof

# 할당 ‘개수’ 관점(alloc_objects)
go tool pprof -top -alloc_objects mem.off.pprof
go tool pprof -top -alloc_objects mem.on.pprof

# 현재 점유(inuse_space)
go tool pprof -top -inuse_space mem.off.pprof
go tool pprof -top -inuse_space mem.on.pprof
```

여기서 중요한 해석은 다음입니다.

- alloc_space/alloc_objects의 **순위가 바뀌지 않는데 time/op만 좋아졌다**면, “같은 일을 더 싸게 한다” 쪽에 가까운 변화입니다(이번 변경의 의도와 일치).
- alloc_space가 증가했다면, 그건 allocator가 바뀌어서가 아니라 “벤치가 더 많은 일을 하게 됐거나(처리량 증가)”, “코드 경로가 달라져서 실제로 더 할당하게 됐거나”, “프로파일링 샘플링이 달라져서 착시가 생겼거나” 중 하나입니다.

### MemProfileRate를 낮춰서 ‘작은 객체가 안 보이는 문제’를 피합니다

작은 객체가 수백만 개 생겨도 heap 프로파일은 샘플링이라서 잘 안 잡힐 수 있습니다. Go 위키는 기본 샘플링이 “512KB당 1 샘플”이고, `--memprofilerate` 또는 `runtime.MemProfileRate`로 조정할 수 있다고 설명합니다.[^6]

벤치에서만이라면 아래처럼 올-샘플에 가까운 값을 쓰는 게 유효합니다(단, 실행이 느려질 수 있습니다).

```bash
GOEXPERIMENT=nosizespecializedmalloc \
  go test -run=^$ -bench='BenchmarkHandleParallel' -count=1 \
  -memprofile mem.off.pprof -memprofilerate=1 ./svc

go test -run=^$ -bench='BenchmarkHandleParallel' -count=1 \
  -memprofile mem.on.pprof -memprofilerate=1 ./svc
```

프로덕션에서 이걸 켜는 건 별개의 이야기입니다. 벤치/스테이징에서 “분포를 보기 위해” 단기적으로 낮추는 게 현실적입니다.

## trace로 ‘지연시간’ 관점에서 비교합니다: GC assist / STW / mark phase

pprof가 “총합”이라면, trace는 “짧은 구간에서 무엇이 언제 일어났나”를 보여 줍니다. Go GC 가이드는 latency 원인으로 STW 전환, mark phase에서 GC가 CPU 25%를 가져가는 scheduling delay, high allocation rate에서의 GC assist 등을 열거하고, 이런 것들이 execution trace에서 보인다고 안내합니다.[^4]

### trace 수집

```bash
# ON
go test -run=^$ -bench='BenchmarkHandleParallel' -count=1 \
  -trace trace.on.out ./svc

# OFF
GOEXPERIMENT=nosizespecializedmalloc \
  go test -run=^$ -bench='BenchmarkHandleParallel' -count=1 \
  -trace trace.off.out ./svc
```

열어보는 방법은 다음입니다.

```bash
# Go 1.27부터 -http=:6060 같은 형태는 localhost로 제한됩니다.
# 외부 바인딩이 필요하면 0.0.0.0을 명시해야 합니다.
go tool trace -http=:0 trace.on.out
```

이 `-http` 동작(포트만 주면 localhost 제한)은 Go 1.27 릴리스 노트에 명시돼 있습니다.[^2]

### trace에서 보는 포인트

size-specialized allocation은 “GC 사이클 자체를 바꾸는” 류의 변경이 아니라, allocation hot path 비용을 깎습니다. 그래서 trace에서 기대하는 변화는 보통 다음 중 하나입니다.

- 같은 QPS/부하에서, GC assist 구간의 분포가 줄어들거나(특히 allocation이 바쁜 goroutine이 GC assist로 빨려 들어가는 시간)
- mark phase에서의 scheduling 영향이 줄어들거나(간접 효과)
- STW pause가 줄어들기보다는 “STW가 요청의 tail과 겹치는 빈도”가 달라지는 형태

여기서 중요한 건 “trace 한 번”으로 결론 내지 않는 것입니다. tail은 노이즈가 크고, trace는 짧은 창만 보므로 다음을 같이 맞춥니다.

- 벤치/부하 테스트에서 p99/p999(또는 SLO 구간)
- trace에서 GC 관련 이벤트가 그 tail과 겹치는지
- pprof에서 `gcAssistAlloc`/`mallocgc` 비중이 어떻게 변했는지

## “성능이 좋아졌는데 메모리가 늘어나는” 케이스를 어떻게 해석하나

이 현상은 Go 1.27 allocator 변경과 무관하게도 자주 보이지만, 이번 변경 이후엔 더 자주 “회귀로 오해”받을 수 있습니다. 해석을 몇 가지로 나눠야 합니다.

### 1) 처리량이 늘어났다면, ‘초당 할당량’이 늘어 GC가 더 자주 돕습니다

Go GC 가이드는 allocation rate(초당 바이트)가 GC frequency(주기)를 좌우하고, allocation rate가 커지면 더 자주 GC 사이클이 돈다고 설명합니다.[^4]

size-specialized allocation이 time/op를 줄이면, 같은 CPU에서 더 많은 요청을 처리하게 되고(부하가 QPS를 따라 올라가는 구조라면), 결과적으로 초당 할당량이 늘어날 수 있습니다. 이때 메모리가 늘어나는 건 allocator가 “더 낭비해서”가 아니라, 시스템이 더 많은 일을 하기 시작한 결과일 수 있습니다.

이건 회귀가 아니라 “성능 향상이 load를 끌어올린 부작용”입니다. 결론을 내려면 기준을 “동일 QPS”로 고정해야 합니다.

- 동일 QPS에서 RSS/HeapInUse가 늘면 원인을 따져야 합니다.
- 최대 처리량을 올려서 생긴 메모리 증가는 capacity planning 문제입니다.

### 2) internal fragmentation이 바뀐 게 아니라 ‘보이기 시작한’ 것일 수 있습니다

특화 함수 생성은 바이너리 크기를 늘립니다(릴리스 노트: 약 60KB).[^2]

이건 heap 메모리와 다르지만, 컨테이너 환경에서 “메모리 증가”로 뭉뚱그려 관측될 때가 있습니다(특히 RSS 기준). heap이 아닌 코드 세그먼트/페이지 단위 정렬 때문에 미세하게 튀는 경우를 먼저 분리해야 합니다.

### 3) heap 프로파일은 샘플링이라서, 작은 객체는 “추정 오차”가 큽니다

작은 객체가 많은 서비스는 heap 프로파일에서 오차가 커지기 쉽습니다. Go 위키가 말하듯 샘플링은 크기에 비례하고 기본이 512KB당 1샘플이라, tiny allocation은 그냥 안 보입니다.[^6]

따라서 “메모리가 늘었다”를 heap 프로파일 하나로 결론 내리면 위험합니다.

- `runtime.MemStats`(HeapAlloc/HeapInuse/HeapIdle/NextGC 등)
- 컨테이너 cgroup 메모리(RSS, cache 포함 여부)
- `pprof`의 inuse_space(살아있는 것) vs alloc_space(흘러간 것)

이 조합으로 “진짜로 live set이 커졌는지”를 먼저 확정해야 합니다.

### 4) GC assist debt/fragmentation 보정이 ‘다르게 관측’될 수 있습니다

size-specialized malloc 스텁을 보면, GC mark가 켜져 있을 때 assist credit을 차감하고(`deductAssistCredit(size)`), 실제 할당한 elemsize와 요청 size 차이만큼 assist debt를 조정하는 로직이 들어 있습니다. 즉, 내부 단편화(요청보다 큰 size class 슬롯을 받는 것)가 GC assist 바이트에 반영됩니다.[^7]

이 부분은 “메모리가 늘어났다/줄었다”를 직접 만들기보다는, GC가 mutator에 부과하는 assist 양의 관측(프로파일/트레이스에서 보이는 양)을 바꿔서 tail이 달라지는 식으로 나타날 수 있습니다. 그래서 나는 다음 순서로 해석합니다.

1) 동일 QPS에서 HeapInUse가 실제로 늘었는지
2) 늘었다면, live 객체가 늘었는지(캐시/큐/맵 성장) vs 단편화/arena 차이인지
3) live 객체가 늘지 않았는데 tail이 변했다면, trace에서 assist/mark phase 겹침을 봄

## “무엇을 측정해야 하나”를 체크리스트로 고정합니다

작은 객체가 많은 서비스에서 Go 1.27 이후 회귀 테스트 항목을 나는 이렇게 바꿉니다.

### A. allocator/GC 비용(throughput 관점)

- `benchstat` 기준: time/op, allocs/op, bytes/op
- CPU pprof: `runtime.mallocgc`(또는 특화 malloc 함수들), `runtime.gcAssistAlloc` cum 비율[^4]
- heap pprof:
  - alloc_space / alloc_objects 상위 callsite (allocation rate 관점)[^6]
  - inuse_space 상위 callsite (live set 관점)[^6]

### B. tail latency(지연시간 관점)

- 서비스 레벨 p95/p99/p999 (동일 QPS에서)
- trace에서 GC 이벤트와 tail의 겹침
  - mark phase 시간대
  - STW 전환 이벤트
  - assist 구간(“요청 처리 중간에 멈칫”하는 패턴)

Go GC 가이드가 나열한 latency 요인(brief STW, mark phase에서의 scheduling, high allocation rate에서의 assist 등)을 그대로 항목으로 씁니다.[^4]

### C. escape/alloc site의 구조(왜 그 alloc이 heap으로 가는지)

- `-gcflags=all=-m=2`로 “이 값은 왜 heap으로 갔나”를 텍스트로 남김
- hotspot callsite는 코드 리뷰에서 “stack으로 돌릴 수 있나 / pooling 할 건가”를 결정

여기서 중요한 변화는, 예전엔 “heap이면 무조건 나쁘다”에 가까웠다면, 이제는 “heap이 unavoidable한데 size가 고정이고 작으면 Go 1.27에서 덜 나쁘다”라는 옵션이 생긴 정도입니다. 결국 근본 레버는 escape/alloc 자체를 줄이는 쪽에 남아 있습니다.

## 도입 판단: 내 기준은 ‘평균 개선’이 아니라 ‘회귀 탐지 비용’입니다

Go 1.27 릴리스 노트는 현실적인 기대치를 ~1%로 못 박고, 대신 작은 allocation에서 최대 30%라고 범위를 제한합니다.[^2]

이 숫자만 보면 “올릴 가치가 있나?”로 보이지만, 나는 반대로 봅니다.

- 이 변경은 런타임 hot path에 들어갔고, opt-out이 1.28에서 사라질 예정입니다.[^2]
- 즉, 올릴지 말지의 문제가 아니라, 결국 올라가게 될 확률이 높고, 그때 회귀를 잡기 위한 관측 항목을 지금 정해야 합니다.

내 경우, 작은 객체가 많은 시스템은 AI 프로토타이핑 단계에서도 쉽게 만들어집니다(토큰/문자열/컨텍스트/트레이스 태그가 요청당 쌓임). 다만 이 블로그에서 다룬 아키텍처 레벨 이야기는 다른 글에 이미 써 둔 게 있어서 여기서는 반복하지 않습니다: [확장 가능한 AI 앱 아키텍처 설계 패턴: “단발성 Prompt”에서 “Durable Agent Runtime”으로](https://daewooki.github.io/posts/2026-3-ai-prompt-durable-agent-runtime-2/)

결국 Go 1.27의 size-specialized allocations은 “튜닝의 방향을 바꾸는 기능”이라기보다, “튜닝/회귀 테스트에서 확인해야 할 런타임 이벤트가 하나 늘어난 변경”입니다. 작은 고정 크기 heap allocation이 지배적인 서비스라면, pprof/trace 기준선을 Go 1.27 내부 opt-out으로 먼저 고정해 두는 쪽이 운영 비용이 제일 적습니다.

## 참고 자료

- [Size-Specialized Memory Allocation](https://go.dev/blog/size-specialized-allocations)
- [Go 1.27 Release Notes](https://go.dev/doc/go1.27)
- [Release History](https://go.dev/doc/devel/release)
- [Go Wiki: Debugging performance issues in Go programs](https://go.dev/wiki/Performance)
- [Go Garbage Collector Optimization Guide](https://go.dev/doc/gc-guide)
- [Diagnostics](https://go.dev/doc/diagnostics)
- [cmd/compile/internal/ssagen/ssa.go (Go compiler source)](https://go.dev/src/cmd/compile/internal/ssagen/ssa.go)
- [src/runtime/malloc_stubs.go (specialized malloc generator stub)](https://go.googlesource.com/go/+/50128a21541e3fd712ad717a223aaa109cb86d43/src/runtime/malloc_stubs.go)
- [runtime: sizespecializedmalloc experiment (issue tracker)](https://github.com/golang/go/issues/79286)

[^1]: <https://go.dev/blog/size-specialized-allocations>
[^2]: <https://go.dev/doc/go1.27>
[^3]: <https://go.dev/src/cmd/compile/internal/ssagen/ssa.go>
[^4]: <https://go.googlesource.com/website/%2B/a45e5bbd5d1b59477672cd8e94a4ba30909b789f/_content/doc/gc-guide.html>
[^5]: <https://go.dev/doc/devel/release>
[^6]: <https://go.dev/wiki/Performance>
[^7]: <https://go.googlesource.com/go/%2B/50128a21541e3fd712ad717a223aaa109cb86d43/src/runtime/malloc_stubs.go>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
