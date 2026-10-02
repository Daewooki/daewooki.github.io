---
title: "Rust 1.99.0 릴리스: C-ABI variadics와 raw pointer 레이아웃 API가 FFI/unsafe 계약을 바꾼다"
description: "Rust 1.99.0의 FFI·unsafe 관련 안정화가 바인딩 크레이트의 암묵적 파손 지점을 어디로 옮겼는지 점검합니다."
date: 2026-10-02 14:13:04 +0900
categories: ["News", "Languages"]
tags: ["rust", "ffi", "unsafe", "c-abi", "variadics", "memory-layout"]
render_with_liquid: false
---

## 2026-10-01에 실제로 바뀐 것

Rust 1.99.0이 2026-10-01에 공식 배포됐습니다. 릴리스 노트에서 눈에 띄는 변화는 세 가지가 한 덩어리로 묶인다는 점입니다. (1) `extern "C"` variadic 함수 정의의 안정화, (2) raw pointer에서 레이아웃 정보를 꺼내는 API의 안정화, (3) `Box::leak` 문서가 “나중에 다시 회수하는 패턴”을 피하라는 방향으로 업데이트된 것. 셋 다 공통점은 FFI 경계에서 **어떤 순간에 reference를 ‘만들었다고 간주되는지’**와, 그로 인해 컴파일러가 얻는 최적화 전제(=unsafe 코드 계약)가 어디까지인지를 더 명시적으로 만들었다는 점입니다.  

공식 발표문은 아래입니다.

- [Rust 1.99.0 공식 발표](https://blog.rust-lang.org/2026/10/01/Rust-1.99.0/)

발표문에는 “언어 의미론 변화는 없다”고 적혀 있지만, 이런 종류의 릴리스는 내 경험상 업그레이드 이슈로 바로 바뀝니다. API가 바뀌어서가 아니라, 문서·Reference·표준 라이브러리가 “이건 UB였고 앞으로도 UB로 취급할 거다”를 더 분명히 적는 순간, 기존에 우연히 동작하던 바인딩이 조용히 깨집니다. 내 블로그에서 예전에 썼던 [발표보다 더 무서운 건 조용한 변경](https://daewooki.github.io/posts/2026-3-ai-api-1/)과 결이 같습니다.

이 글은 기능 소개가 아니라, Rust 1.99.0 업그레이드가 기존 C 연동 코드/바인딩 크레이트에 만드는 암묵적 파손 포인트를 체크리스트 형태로 정리하는 데 초점을 둡니다.

## extern "C" variadics: 이제 Rust가 C-ABI variadic을 “정의”한다

Rust는 이전에도 외부 C 라이브러리의 variadic 함수를 “호출”할 수는 있었습니다(대표적으로 `printf`). Rust 1.99.0에서 바뀐 점은 C-ABI variadic 함수를 Rust 쪽에서 직접 “정의”할 수 있게 됐다는 것입니다. 공식 발표문은 `"C"`와 `"C-unwind"` ABI에서 C-variadic 함수 정의가 안정화됐다고 명시합니다. 또한 `...`의 타입이 `VaList`이며, 플랫폼 전반에서 C의 `va_list`와 layout/ABI가 맞도록 설계됐다고 설명합니다.  

- [Rust 1.99.0: extern "C" variadics 섹션](https://blog.rust-lang.org/2026/10/01/Rust-1.99.0/)
- [VaList 문서](https://doc.rust-lang.org/core/ffi/struct.VaList.html)

Rust Reference도 문법 차원에서 `...` 파라미터를 C-variadic으로 정의하고, `extern` 블록 선언뿐 아니라 `extern "C" fn` 정의에서도 패턴이 필수라는 점까지 명시합니다.

- [Rust Reference: Functions / C-variadic 파라미터](https://doc.rust-lang.org/reference/items/functions.html)

여기서 중요한 관찰 하나. Rustonomicon의 FFI 챕터는 오랫동안 “일반 Rust 함수는 variadic일 수 없다”는 예제를 담고 있었는데, 이제 그 문장은 더 이상 “항상 참”이 아닙니다. Rustonomicon이 틀렸다고 공격할 일이 아니라, 팀 내 문서/위키/레거시 가이드가 비슷한 문장을 들고 있을 확률이 높다는 쪽이 더 실전적입니다.

- [Rustonomicon: Variadic functions 섹션(과거 서술 포함)](https://doc.rust-lang.org/nomicon/ffi.html)

이 변화는 단순히 “Rust에서도 variadic 쓸 수 있다”가 아니라, FFI 설계 패턴이 바뀐다는 뜻입니다. 그동안은 Rust에서 C API를 구현하려면 variadic 부분 때문에 C shim을 두는 경우가 많았습니다. 이제는 shim을 제거할 수 있고, 그 제거가 또 다른 파손 포인트를 만들 수 있습니다.

## variadic/va_list 경계에서 생기는 암묵적 파손 체크리스트

아래 항목은 “코드가 컴파일되느냐”보다 “계약이 바뀌는 순간 UB로 떨어질 수 있느냐” 중심입니다.

### 1) Default argument promotions를 계약으로 올려야 합니다

C variadic의 핵심 함정은 argument type이 호출 시점에 “그대로” 전달되지 않는다는 점입니다. C는 variadic에 전달되는 값에 대해 promotion 규칙을 적용합니다(예: `float` → `double`, 작은 정수 → `int` 계열). Rust 쪽에서 `VaList::next_arg::<T>()`로 읽을 때, 호출자가 실제로 어떤 타입으로 전달했는지와 `T`가 ABI 상 compatible해야 하며, 이건 `unsafe` 계약입니다.

`VaArgSafe`는 “이 플랫폼에서 variadic ABI로 읽을 수 있는 타입”을 제한하는 장치로 소개됩니다. 특히 문서가 강조하는 포인트가 두 가지입니다.

- `c_int`, `c_long`, `c_longlong`, `c_uint`, `c_ulong`, `c_ulonglong`, `c_double`, 그리고 raw pointer는 항상 가능
- `i32`/`usize` 같은 Rust primitive 구현은 플랫폼별로 달라질 수 있으니 직접 의존하지 말 것

- [VaArgSafe 문서](https://doc.rust-lang.org/core/ffi/trait.VaArgSafe.html)
- [VaList::next_arg 안전 조건](https://doc.rust-lang.org/core/ffi/struct.VaList.html)

**체크리스트**

- variadic로 전달되는 정수/부동소수점은 Rust 타입(`i32`, `f32`)이 아니라 `std::ffi`의 C 타입(`c_int`, `c_double`) 기준으로 계약을 작성했는지 확인합니다.
- “C에서는 `short`를 넘겼는데 Rust에서 `i16`로 읽는다” 같은 코드가 있으면, promotion 때문에 이미 UB였을 가능성이 큽니다. 1.99.0에서 API가 생겼다고 UB가 갑자기 생기는 건 아니지만, 이제 팀이 그 코드를 더 쉽게 작성하게 되고(=리스크가 퍼짐), 최적화가 더 공격적으로 바뀌는 순간 갑자기 발화합니다.

### 2) 인자 개수/종료 조건을 반드시 API에 노출해야 합니다

C variadic은 호출자가 “몇 개를 넘겼는지”를 callee가 추론할 방법이 없습니다. `printf`는 format string이 그 역할을 합니다. Rust에서 variadic 함수를 정의할 수 있게 되면서, 그동안 C shim이 암묵적으로 갖고 있던 계약(예: 첫 번째 인자가 count)을 Rust로 옮겨야 합니다.

- count 기반 API면 “최소 count개의 `c_int`가 전달된다” 같은 안전 조건을 Rust 함수 docstring에 명시해야 합니다.
- sentinel 기반 API면 sentinel 타입의 promotion/ABI까지 포함해서 종료 조건을 문서화해야 합니다.

공식 발표문 예제도 안전 조건을 doc comment로 올립니다.

- [Rust 1.99.0 발표문 예제 코드](https://blog.rust-lang.org/2026/10/01/Rust-1.99.0/)

### 3) `VaList`를 저장하거나 재사용하는 패턴을 금지해야 합니다

`VaList`는 C의 `va_list`와 동일하게 “커서”이며, drop 시점이 `va_end`에 대응됩니다. `VaList`가 FFI boundary를 넘을 수 있다는 점은 강력하지만, 그만큼 위험한 패턴(저장, 지연 처리, 멀티스레드 공유)이 자연스럽게 나오기 쉽습니다.

VaList 문서는 다음을 명시합니다.

- clone은 `va_copy`
- drop은 `va_end`
- FFI boundary를 넘을 수 있으며 platform의 `va_list`와 layout/ABI가 fully match

- [VaList 문서의 설명(va_copy/va_end, FFI boundary)](https://doc.rust-lang.org/core/ffi/struct.VaList.html)

**체크리스트**

- `VaList`를 struct field로 저장하거나, 콜백에 넘겨 비동기로 소비하는 코드가 생기지 않도록 API 형태를 강제합니다.
- C 쪽에서 `va_list`는 구현에 따라 array type일 수 있습니다. Rust가 ABI를 맞춘다고 해도, “어떤 함수 시그니처로 넘기는지”가 맞지 않으면 즉시 깨집니다. 바인딩 헤더/시그니처를 단일 소스로 관리하고(자동 생성 포함), 플랫폼별 CI에서 확인합니다.

### 4) unwind 경계를 의도적으로 선택해야 합니다

Rust 1.99.0 발표문은 variadic 함수 정의가 `"C"`와 `"C-unwind"`에서 안정화됐다고 말합니다. 이건 단순 옵션이 아니라 “패닉/예외가 경계를 넘을 때 무엇이 정의되는지”의 선택입니다.

- [Rust 1.99.0: "C"와 "C-unwind" 언급](https://blog.rust-lang.org/2026/10/01/Rust-1.99.0/)
- [Rust Reference: ABI와 -unwind 동작](https://doc.rust-lang.org/reference/items/functions.html)

**체크리스트**

- C가 Rust로 들어오는 콜백/플러그인 API라면, Rust 내부에서 panic이 발생할 수 있는 경로가 있는지부터 확인합니다.
- “절대 panic 안 난다”가 조직적으로 유지되지 않는 코드베이스라면, `"C"` 경계에서 abort/UB로 떨어질 여지가 커집니다. `"C-unwind"` 채택 여부를 아키텍처 결정으로 다뤄야 합니다.

## raw pointer 레이아웃 API: reference를 만들지 않고 size/align/Layout를 얻는다

Rust 1.99.0에서 안정화된 두 번째 축은 레이아웃 정보 접근입니다. 안정화된 항목은 아래 세 가지입니다.

- `core::alloc::Layout::for_value_raw`
- `core::mem::size_of_val_raw`
- `core::mem::align_of_val_raw`

공식 발표문이 “raw pointer로 `Sized`뿐 아니라 `?Sized`까지 포함해 size/alignment를 가져오는 안전 요구사항을 정리(settle)했다”고 표현하는 이유는, 기존 패턴이 너무 자주 “reference를 만들기 위해” UB를 밟았기 때문입니다.

- [Rust 1.99.0: Layout information from raw pointers 섹션](https://blog.rust-lang.org/2026/10/01/Rust-1.99.0/)
- [`size_of_val_raw` 문서](https://doc.rust-lang.org/core/mem/fn.size_of_val_raw.html)
- [`align_of_val_raw` 문서](https://doc.rust-lang.org/core/mem/fn.align_of_val_raw.html)
- [`Layout::for_value_raw` 문서](https://doc.rust-lang.org/stable/core/alloc/struct.Layout.html)

핵심은 이겁니다.

- `size_of_val(&*ptr)` 같은 코드는 “ptr이 `&T`로 reborrow 가능하다”는 강한 전제를 암묵적으로 선언합니다.
- 그런데 FFI에서는 ptr이 dangling이거나(소유권 불명), aliasing이 깨져 있거나(공유/변경 동시), 심지어 메타데이터가 초기화되지 않았을 수도 있습니다(DST의 slice length, trait object vtable 등).
- 그럼에도 “그냥 레이아웃만 알고 싶은데…” 때문에 reference를 만들고, 그 순간 UB가 됩니다.

Rust 1.99.0의 raw pointer 레이아웃 API는 그 구멍을 메우는 쪽으로 설계됐고, 대신 안전 조건을 `unsafe` 함수 문서에 박아 넣었습니다.

### 안전 조건이 의미하는 실전 포인트

문서에서 반복적으로 등장하는 조건이 있습니다.

- pointer를 `&T`로 reborrow할 수 있으면(=reference로 만들어도 sound하면) raw API도 안전
- 그렇지 않다면, `T: Sized`는 항상 OK
- `T: ?Sized`의 경우 unsized tail이 slice/`str`/trait object인 경우에 한해 “전체 크기가 `isize`에 fit” 같은 조건이 붙음

- [`size_of_val_raw` Safety 섹션(unsized tail, isize fit)](https://doc.rust-lang.org/core/mem/fn.size_of_val_raw.html)
- [`Layout::for_value_raw` Safety 섹션](https://doc.rust-lang.org/stable/core/alloc/struct.Layout.html)

여기서 `isize` 제한은 단순한 형식 조건이 아니라, “이 메타데이터를 신뢰하고 포인터 산술을 해도 된다”의 상한선을 의미합니다. 바인딩에서 외부 입력을 길이로 받아 DST 포인터를 만들고, 그 메타데이터로 레이아웃을 계산한 다음 dealloc까지 가는 경로라면, 이제부터는 길이 검증이 안전성의 일부가 됩니다.

## 레이아웃 API가 기존 바인딩의 ‘암묵적 파손’을 어디로 옮기나

raw pointer 레이아웃 API가 안정화되면, 레거시 바인딩 크레이트는 두 갈래로 나뉩니다.

1) 이미 잘못된 reference materialization을 하고 있었고, 이제 그걸 고칠 수 있게 된 코드
2) 이제 “reference 안 만들었으니 안전하겠지”라는 오해로 raw API를 아무 포인터에나 적용하는 코드

둘 다 업그레이드 시점에 정리하지 않으면 사고가 납니다.

### 1) `&*ptr`로 레이아웃만 뽑던 코드가 이제 바로 교체 대상입니다

전형적인 레거시 패턴은 아래입니다.

- `Layout::for_value(&*ptr)`
- `size_of_val(&*ptr)`
- `align_of_val(&*ptr)`

이 코드가 “그동안은 잘 됐다”는 말은 “컴파일러가 아직 그 UB를 최적화로 활용하지 않았다”는 말과 동치인 경우가 많습니다. Rust 팀이 1.99.0에서 굳이 이 API를 안정화한 배경 자체가 이런 패턴이 너무 흔하기 때문이고, tracking issue도 꽤 오래 이어져 왔습니다.

- [Tracking issue: layout information behind pointers #69835](https://github.com/rust-lang/rust/issues/69835)

**체크리스트**

- 레이아웃/정렬 계산 목적으로 `&*ptr`을 만든 곳이 있는지 grep합니다.
- 목적이 “read/write”가 아니라 “layout 계산”이라면, raw API로 옮길 수 있는지부터 봅니다.
- raw API로 옮긴 다음에도, unsized tail과 `isize` fit 조건을 만족하는지 검증 코드를 붙입니다(특히 외부 입력 길이).

### 2) DST 포인터 메타데이터가 초기화됐다는 사실이 이제 안전 계약의 한 줄이 됩니다

DST는 fat pointer입니다. slice는 (data pointer + length), trait object는 (data pointer + vtable)처럼 메타데이터를 포함합니다. `Layout::for_value_raw`는 이 메타데이터를 읽어서 레이아웃을 계산합니다.

- slice tail: 길이가 “initialized integer”라는 요구사항이 문서에 명시됩니다.
- trait object: vtable이 “valid vtable”이어야 한다고 명시됩니다.

- [`Layout::for_value_raw` Safety: slice tail/trait object vtable 조건](https://doc.rust-lang.org/stable/core/alloc/struct.Layout.html)

이 조건이 왜 중요하냐면, FFI에서는 종종 “헤더 + 바이트 배열” 구조를 C 스타일로 만들어놓고 Rust에서 DST로 해석하려는 욕구가 생깁니다. 그 구조 자체는 가능하지만, 길이 필드가 아직 쓰이지 않았거나(초기화 전), 공격자가 임의로 만든 길이(오버플로 유도)일 수 있습니다. 이제는 그 시나리오가 문서로 박혔기 때문에, 바인딩 설계에서 길이 검증을 안전 조건으로 승격시키는 게 맞습니다.

### 3) `repr(C)`라고 해서 “C flexible array member와 1:1”로 생각하면 위험합니다

FFI에서 DST를 쓰는 흔한 이유는 C의 flexible array member 패턴을 Rust로 옮기기 위해서입니다. 하지만 Rust의 `repr(C)`는 “C ABI와의 호환을 위한 최소한”이지, 모든 레이아웃 결정을 고정하겠다는 약속이 아닙니다. tracking issue #69835에서도 `repr(C)`에서의 trailing padding 같은 미묘한 포인트가 논의됩니다.

- [Tracking issue #69835 (repr(C) trailing padding 언급 포함)](https://github.com/rust-lang/rust/issues/69835)

**체크리스트**

- C와 Rust 사이에서 “동일한 allocation layout으로 dealloc할 수 있다”는 가정이 있다면, 그 가정을 명시적으로 문서화합니다.
- 가능하면 “Rust에서 allocate한 것은 Rust에서 free”로 소유권 경계를 단순화합니다. 반대로 “C에서 allocate한 것은 C에서 free”로 고정하는 것도 방법입니다.

## Box::leak 언리크(round-trip) 패턴: 문서 변화가 의미하는 것

Rust 1.99.0 발표문은 `Box::leak`에 대해, “나중에 그 메모리를 deallocate하는 패턴을 권장하지 않는다”는 방향으로 문서가 업데이트됐다고 명시합니다. 이유는 “현재와 미래의 컴파일러 최적화와 상호작용이 문제를 일으킬 수 있고, 특히 custom allocator의 (예정된) 안정화와 맞물리면 더 위험하다”는 것입니다.

- [Rust 1.99.0: Box::leak round-trip 언급](https://blog.rust-lang.org/2026/10/01/Rust-1.99.0/)

표준 문서의 `Box::leak` 항목도 더 노골적으로 말합니다.

- leak은 “프로그램 종료까지 살릴 메모리”에 유용
- 나중에 free해야 한다면 `Box::into_raw`나 `Box::into_non_null`을 선호
- leak으로 만든 `&mut T`에서 다시 `Box`를 복원하는 것은(Global allocator일 때만 가능하고) 그때도 grey area이며, 많은 seemingly harmless한 방식이 UB라서 피해야 한다

- [`Box::leak` 문서(언리크 회피 권고)](https://doc.rust-lang.org/alloc/boxed/struct.Box.html#method.leak)

여기서 “암묵적 파손” 포인트는 바인딩 크레이트에 실제로 흔한 패턴이기 때문입니다.

- Rust에서 `Box::new(T)`로 상태를 만들고
- C API가 `void*` userdata를 받으니 `Box::leak`으로 `'static`처럼 만들어 넘기고
- 언젠가 callback의 destroy에서 `Box::from_raw`로 복원해서 drop

이 패턴은 직관적으로는 합리적이지만, leak이 반환하는 것은 reference이고, reference 기반으로 round-trip을 하는 순간 aliasing/유효성 전제가 엮이기 시작합니다. 문서가 회피를 권고하는 건 “지금 당장 전부 폭발한다”가 아니라, 최적화가 더 똑똑해질수록 위험해진다는 신호로 읽는 게 맞습니다.

대체로 권장되는 형태는 “leak로 reference를 만들지 말고, 아예 raw pointer/NonNull로 소유권을 옮겨라”입니다.

- [`Box::into_raw`](https://doc.rust-lang.org/alloc/boxed/struct.Box.html#method.into_raw)
- [`Box::from_raw`](https://doc.rust-lang.org/alloc/boxed/struct.Box.html#method.from_raw)
- [`Box::into_non_null`](https://doc.rust-lang.org/alloc/boxed/struct.Box.html#method.into_non_null)
- [`Box::from_non_null`](https://doc.rust-lang.org/alloc/boxed/struct.Box.html#method.from_non_null)

이 변화는 “새 API가 추가됐다” 정도가 아니라, FFI에서 userdata 소유권을 넘기는 기본 패턴을 reference 기반에서 pointer 기반으로 옮기라는 압력으로 읽힙니다.

## 앞으로의 논쟁 포인트와 회의론

### “문서만 바뀌었는데 왜 호들갑이냐”

Rust 1.99.0 발표문은 명시적으로 “언어 의미론 변화는 없다”고 적습니다. 그 자체는 사실입니다.  
다만 unsafe/FFI에서 의미론 변화보다 더 위험한 건 “이전까지는 최적화가 우연히 못 잡아먹던 UB가, 어느 날부터는 최적화의 먹이가 되는 순간”입니다. raw pointer 레이아웃 API 안정화나 `Box::leak` 문서 강화는, Rust 팀이 앞으로 그 영역을 더 적극적으로 최적화하겠다는 시그널로 읽힙니다.

### “C-variadic을 Rust에서 정의하면 안전해지는 것 아니냐”

정의할 수 있게 되면 C shim을 줄여서 전체 표면적은 줄어듭니다. 그건 명백히 이점입니다.  
하지만 variadic 자체가 호출자-피호출자 사이 계약을 타입 시스템 밖으로 밀어내는 구조라서, shim이 사라진 만큼 “계약을 문서/테스트로 올려야 할 부담”이 Rust 쪽으로 이동합니다. `VaList::next_arg`는 `unsafe`이고, 안전 조건이 꽤 길게 적혀 있습니다.

- [VaList::next_arg의 Safety 조건](https://doc.rust-lang.org/core/ffi/struct.VaList.html)

내 결론은 “shim을 없애는 건 좋지만, 없앤 shim이 원래 암묵적으로 해주던 타입/promotion/개수 체크를 Rust에서 다시 명문화해야 한다”입니다.

## 지금 당장 터질 수 있는 업그레이드 이슈를 체크리스트로 묶기

여기부터는 실제로 Rust 1.99.0으로 올리는 순간(또는 올린 직후) 레포에서 확인할 항목입니다.

### A. 바인딩/FFI 레이어에서 `...` 또는 `va_list`가 등장하는가

- C API를 Rust로 구현하면서 variadic 때문에 C shim을 둔 곳이 있는지 찾습니다. 이제 shim을 없앨 수 있지만, 없애기 전에 계약이 문서화돼 있는지부터 확인합니다.
- Rust 쪽에서 `printf`류를 호출할 때, 전달 타입이 promotion 규칙을 만족하는지 확인합니다(특히 `f32`/작은 정수).
- variadic에서 읽는 타입을 `i32`/`u64` 같은 Rust primitive로 고정해 둔 코드가 있다면, `c_int`/`c_double`/pointer로 정리할 여지가 큽니다.

근거 문서는 `VaArgSafe`가 promotion과 타입 선택을 직접 언급한다는 점입니다.

- [VaArgSafe 문서(promotion, C 타입 권장)](https://doc.rust-lang.org/core/ffi/trait.VaArgSafe.html)

### B. 레이아웃 계산을 위해 `&*ptr`을 만들고 있는가

- `Layout::for_value(&*ptr)`
- `size_of_val(&*ptr)`
- `align_of_val(&*ptr)`

이런 코드가 있다면, 레이아웃만 필요했는지 / 실제 접근도 했는지 분리해서 봅니다. 레이아웃만 필요했다면 1.99.0부터는 아래로 교체 가능한 구간이 생겼습니다.

- `Layout::for_value_raw(ptr)`
- `size_of_val_raw(ptr)`
- `align_of_val_raw(ptr)`

- [`size_of_val_raw` 문서](https://doc.rust-lang.org/core/mem/fn.size_of_val_raw.html)
- [`Layout::for_value_raw` 문서](https://doc.rust-lang.org/stable/core/alloc/struct.Layout.html)

### C. `Box::leak` 후에 나중에 free하는 코드가 있는가

- `Box::leak`로 `&'static mut T`를 만든 다음
- 그 포인터를 저장했다가
- 나중에 `Box::from_raw`로 복원하는 패턴

이건 1.99.0에서 “권장하지 않는다/grey area/UB 가능”로 문서가 강화됐습니다.

- [`Box::leak` 문서](https://doc.rust-lang.org/alloc/boxed/struct.Box.html#method.leak)
- [Rust 1.99.0 발표문(Box::leak 언급)](https://blog.rust-lang.org/2026/10/01/Rust-1.99.0/)

대신 소유권 전달을 `Box::into_raw`/`Box::into_non_null` 기반으로 바꿔 “pointer로 round-trip”하는 형태가 더 정직합니다.

- [`Box::into_non_null`](https://doc.rust-lang.org/alloc/boxed/struct.Box.html#method.into_non_null)
- [`Box::from_non_null`](https://doc.rust-lang.org/alloc/boxed/struct.Box.html#method.from_non_null)

## 재현 가능한 예제: Rust에서 C-variadic 정의 + C에서 호출

아래는 “Rust가 C ABI variadic 함수를 직접 정의하고, C 코드가 그 함수를 호출”하는 예제입니다. 또한 `VaList`를 별도 함수로 분리해서 C의 `va_list` wrapper가 Rust로 넘어오는 형태까지 확인합니다.

테스트 환경은 Linux x86_64 기준으로 서술합니다. macOS도 큰 흐름은 같지만 shared library 로딩 경로(`DYLD_LIBRARY_PATH`)가 다르고, Windows는 ABI/툴체인이 더 달라 별도 정리가 필요합니다.

### 프로젝트 구성

```bash
mkdir rust199-variadic-demo
cd rust199-variadic-demo
cargo new --lib rust_variadic
```

`rust_variadic/Cargo.toml`:

```toml
[package]
name = "rust_variadic"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]
```

`rust_variadic/src/lib.rs`:

```rust
use core::ffi::{c_int, VaList};

#[no_mangle]
pub unsafe extern "C" fn rust_sum_i32(count: c_int, ap: ...) -> c_int {
    // Safety: `ap`는 호출자가 제공한 variadic 리스트이며,
    // 이 함수의 계약은 "count개의 c_int가 뒤따른다"입니다.
    unsafe { rust_vsum_i32(count, ap) }
}

#[no_mangle]
pub unsafe extern "C" fn rust_vsum_i32(count: c_int, mut ap: VaList<'_>) -> c_int {
    if count < 0 {
        return 0;
    }

    let mut sum: c_int = 0;
    for _ in 0..(count as usize) {
        // SAFETY: rust_sum_i32 / rust_vsum_i32의 계약상
        // 뒤따르는 인자는 c_int로 읽을 수 있어야 합니다.
        sum = sum.wrapping_add(unsafe { ap.next_arg::<c_int>() });
    }
    sum
}
```

여기서 핵심은 두 가지입니다.

- `...`는 `VaList`로 desugar되며, Rust 문서가 C의 `va_start`/`va_arg`/`va_end`에 대응되는 동작을 명시합니다.
- 읽는 타입은 `i32`가 아니라 `c_int`로 고정합니다. 이 선택은 `VaArgSafe` 문서가 “C 타입을 기준으로 삼아라”에 가깝게 쓰여 있기 때문입니다.

- [VaList 설명(va_start/va_arg/va_end 대응)](https://doc.rust-lang.org/core/ffi/struct.VaList.html)
- [VaArgSafe 문서(C 타입, promotion)](https://doc.rust-lang.org/core/ffi/trait.VaArgSafe.html)

### C 테스트 코드

루트 디렉터리에 `ctest.c`를 둡니다.

```c
#include <stdarg.h>
#include <stdio.h>

// Rust에서 export한 심볼
int rust_sum_i32(int count, ...);
int rust_vsum_i32(int count, va_list ap);

static int c_wrap_sum_i32(int count, ...) {
    va_list ap;
    va_start(ap, count);
    int result = rust_vsum_i32(count, ap);
    va_end(ap);
    return result;
}

int main(void) {
    printf("rust_sum_i32: %d\n", rust_sum_i32(3, 10, 20, 30));
    printf("c_wrap_sum_i32: %d\n", c_wrap_sum_i32(3, 10, 20, 30));
    return 0;
}
```

### 빌드 및 실행

```bash
# 1) Rust cdylib 빌드
cd rust_variadic
cargo build --release
cd ..

# 2) C 코드 컴파일 (Linux 기준)
cc -O2 -o ctest ctest.c -L rust_variadic/target/release -lrust_variadic

# 3) 런타임에 so를 찾도록 경로 지정
LD_LIBRARY_PATH=rust_variadic/target/release ./ctest
```

예상 출력:

```text
rust_sum_i32: 60
c_wrap_sum_i32: 60
```

이 예제가 “장난감”으로 끝나지 않는 이유는, 실제 현업에서도 다음 패턴이 흔하기 때문입니다.

- C SDK가 callback을 받는데, signature가 variadic인 경우(로그 훅, 포맷터 훅)
- 기존에는 C shim을 둬서 Rust로 고정된 구조로 넘겼는데
- 이제 Rust가 직접 variadic callback을 구현할 수 있게 되면서 shim을 빼고 싶어짐

shim을 빼는 순간 promotion/인자 개수/종료 조건이 모두 Rust 쪽 계약으로 올라옵니다.

## 재현 가능한 예제: DST를 raw pointer로 free하면서 레이아웃을 계산하기

FFI에서 자주 필요한 작업은 “C 쪽에서 넘어온 포인터를 Rust에서 해제한다” 또는 그 반대입니다. 여기서 DST(flexible array member 유사)를 쓰는 순간, 레이아웃 계산을 위해 reference를 만들고 싶어집니다. Rust 1.99.0의 `Layout::for_value_raw`는 그 유혹을 덜 위험한 형태로 바꿉니다.

아래 코드는 같은 `rust_variadic` 크레이트에 추가할 수 있는 예시입니다. 단, 이 예시는 `alloc`을 사용하므로 `std` 환경을 가정합니다(기본 설정이면 문제 없습니다).

```rust
use core::alloc::Layout;
use core::ffi::c_uchar;
use core::ptr;

#[repr(C)]
pub struct DynBuf {
    len: usize,
    data: [c_uchar],
}

#[no_mangle]
pub unsafe extern "C" fn dynbuf_new(len: usize) -> *mut DynBuf {
    // 외부 입력이면 상한 검증이 필요합니다. 여기서는 예제라 간단히 제한만 둡니다.
    if len > (isize::MAX as usize) {
        return ptr::null_mut();
    }

    // header는 usize 하나. repr(C)에서 필드 순서를 고정해 둡니다.
    let header = core::mem::size_of::<usize>();
    let size = match header.checked_add(len) {
        Some(v) => v,
        None => return ptr::null_mut(),
    };

    // 단순화를 위해 align은 usize 정렬을 사용합니다.
    let layout = match Layout::from_size_align(size, core::mem::align_of::<usize>()) {
        Ok(v) => v,
        Err(_) => return ptr::null_mut(),
    };

    // std 환경 가정
    let raw = unsafe { std::alloc::alloc(layout) };
    if raw.is_null() {
        return ptr::null_mut();
    }

    // len 초기화
    unsafe { (raw as *mut usize).write(len) };

    // DST fat pointer 생성: (data ptr, metadata=len)
    let base: *mut () = raw.cast();
    let fat: *mut DynBuf = ptr::from_raw_parts_mut(base, len);

    // data 0으로 초기화
    unsafe { std::ptr::write_bytes(raw.add(header), 0u8, len) };

    fat
}

#[no_mangle]
pub unsafe extern "C" fn dynbuf_free(p: *mut DynBuf) {
    if p.is_null() {
        return;
    }

    // Safety 계약의 핵심은 "p의 메타데이터(len)가 초기화되어 있고
    // 전체 크기가 isize에 fit"입니다.
    // (예제에서는 dynbuf_new가 만들어준 포인터만 free된다고 가정)
    let layout = unsafe { Layout::for_value_raw(p) };

    unsafe {
        std::alloc::dealloc(p.cast::<u8>(), layout);
    }
}
```

이 코드에서 Rust 1.99.0 이전과 이후의 차이는 “가능/불가능”이 아니라 “실전에서 흔히 하던 UB를 표준 API로 대체할 수 있느냐”입니다.

- 이전: `Layout::for_value(&*p)`로 reference를 만들고 레이아웃을 계산하는 유혹
- 이후: `Layout::for_value_raw(p)`로 메타데이터 기반 레이아웃을 계산할 수 있음

물론 `for_value_raw`도 `unsafe`이고 조건이 붙습니다. 중요한 건 조건이 “문서로 고정되었다”는 점입니다.

- [`Layout::for_value_raw` 안전 조건](https://doc.rust-lang.org/stable/core/alloc/struct.Layout.html)

이제부터는 바인딩 코드 리뷰에서 “레이아웃 계산하려고 reference 만들지 말자”가 실천 가능한 규칙이 됩니다.

## 결론: Rust 1.99.0은 FFI에서 ‘reference를 만들지 않는 쪽’으로 설계를 밀어붙인다

Rust 1.99.0에서 발표된 변화는 겉으로 보면 세 가지 조각입니다.

- Rust가 C-variadic 함수를 직접 정의 (`extern "C"` variadics)
- raw pointer에서 레이아웃 정보를 안전 조건과 함께 제공 (`*_raw`)
- `Box::leak`의 언리크 패턴을 사실상 금지에 가깝게 문서화

하지만 이 셋을 한 문장으로 묶으면 “FFI/unsafe에서 reference가 만들어지는 순간의 의미를 더 엄격히 하고, 그 엄격함을 우회하던 관행을 표준 API로 치환하라”는 방향입니다. variadic은 계약을 타입 시스템 밖으로 내보내는 기능이지만, Rust는 그 계약을 `unsafe`와 문서로 끌어올리는 방식으로 통제하려고 합니다. 레이아웃 API와 `Box::leak` 문서 강화는 “reference 기반 우회”의 비용이 앞으로 더 커진다는 경고에 가깝습니다.  

업그레이드 관점에서 보면, Rust 1.99.0은 새 기능 추가가 아니라 기존 바인딩 코드의 안전 계약을 재작성하게 만드는 릴리스입니다.

## 참고 자료

- [Rust 1.99.0 공식 발표](https://blog.rust-lang.org/2026/10/01/Rust-1.99.0/)
- [Rust Reference: Functions / C-variadic 파라미터](https://doc.rust-lang.org/reference/items/functions.html)
- [VaList 문서](https://doc.rust-lang.org/core/ffi/struct.VaList.html)
- [VaArgSafe 문서](https://doc.rust-lang.org/core/ffi/trait.VaArgSafe.html)
- [`size_of_val_raw` 문서](https://doc.rust-lang.org/core/mem/fn.size_of_val_raw.html)
- [`align_of_val_raw` 문서](https://doc.rust-lang.org/core/mem/fn.align_of_val_raw.html)
- [`Layout::for_value_raw` 문서](https://doc.rust-lang.org/stable/core/alloc/struct.Layout.html)
- [`Box::leak` 문서](https://doc.rust-lang.org/alloc/boxed/struct.Box.html#method.leak)
- [`Box::into_non_null` 문서](https://doc.rust-lang.org/alloc/boxed/struct.Box.html#method.into_non_null)
- [`Box::from_non_null` 문서](https://doc.rust-lang.org/alloc/boxed/struct.Box.html#method.from_non_null)
- [Tracking issue: layout information behind pointers #69835](https://github.com/rust-lang/rust/issues/69835)
- [Rustonomicon: Variadic functions 섹션](https://doc.rust-lang.org/nomicon/ffi.html)
- [빅테크 AI “발표”보다 더 무서운 건 API/정책의 조용한 변경이다](https://daewooki.github.io/posts/2026-3-ai-api-1/)

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
