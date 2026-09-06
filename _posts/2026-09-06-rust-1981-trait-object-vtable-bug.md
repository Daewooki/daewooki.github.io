---
title: "Rust 1.98.1: trait object vtable 미스컴파일의 파급"
description: "1.98.0에서 trait object vtable에 null 함수 포인터가 들어가던 버그의 런타임 경로와 팀 대응 기준을 정리합니다."
date: 2026-09-06 12:57:42 +0900
categories: ["News", "Languages"]
tags: ["rust", "rustc", "compiler-bug", "trait-objects", "vtable", "ci"]
render_with_liquid: false
---

## 2026-09-03에 나온 Rust 1.98.1이 실제로 고친 것

2026-09-03에 공개된 Rust 1.98.1은 point release인데, 변경점이 사실상 하나입니다. rustc가 trait object vtable을 생성하는 과정에서, 특정 상황에서 함수 포인터 슬롯에 null을 써 버리던 **miscompilation**을 수정했습니다. 공식 발표문에서도 “null pointer where a function pointer should be”라고 못 박고, 그 결과가 UB이며 어떤 경우에는 segfault로 끝나지만 UB 특성상 임의의 효과로도 정당화될 수 있다고 설명합니다.[^1]

공식 릴리스 노트도 1.98.1의 변경을 “rustc: fix miscompilation in generating vtables” 한 줄로만 기록합니다.[^2]

이 이슈가 특히 까다로운 이유는, (1) 소스가 틀린 게 아니라 컴파일러가 틀린 기계어를 내고, (2) 그 결과가 타입/borrow checker가 보장해 주는 안전성 바깥에서 터지며, (3) 재현은 런타임에서만 “운 좋게” 드러나는 전형적인 경로를 그대로 밟기 때문입니다.

같은 주에 툴체인을 주간 단위로 올리는 팀이라면 “patch니까 안전”이라는 전제를 그대로 두고 갈 수 있는 타이밍이 아니었습니다. 1.98.0(2026-08-20)에서 1.98.1(2026-09-03)으로 단 2주 만에 P-critical급 미스컴파일이 patch로 수정됐다는 사실 자체가, 업그레이드 프로세스의 안전장치를 어디에 둬야 하는지 다시 보게 만듭니다.[^2]

## trait object vtable이 깨질 때 런타임까지 번지는 경로

Rust에서 `dyn Trait`는 동적 디스패치를 위해 vtable을 사용합니다. Rust Reference도 “trait object 호출은 런타임에 vtable에서 함수 포인터를 로드해 간접 호출한다”라고 설명합니다.[^3]

여기서 핵심은, 안전한 Rust 코드가 vtable의 무결성(특히 메서드 엔트리가 유효한 함수 포인터라는 점)을 전제로 최적화/코드 생성을 한다는 사실입니다. 이 전제가 깨지면, 안전한 코드의 표면을 유지한 채로도 런타임에서 바로 크래시나 UB로 이어집니다.

이번 1.98.0 버그가 보여준 경로는 다음 흐름으로 정리됩니다.

1. 컴파일 타임
   - 특정 concrete type `T`에 대해 `dyn Trait`를 만들 때, 컴파일러가 `T as Trait` 구현을 기준으로 vtable을 생성합니다.
   - vtable에는 drop glue, size/alignment 같은 메타데이터와, 메서드별 함수 포인터(혹은 shim)가 들어갑니다.
2. 링크/런타임
   - 프로그램은 `&dyn Trait` / `Box<dyn Trait>` / `Arc<dyn Trait>` 등을 통해 데이터 포인터 + vtable 포인터(메타데이터)를 들고 다닙니다.
   - 메서드 호출 시점에 vtable에서 “해당 메서드 슬롯의 함수 포인터”를 읽어 간접 호출합니다.[^3]
3. 버그 발생
   - vtable의 “함수 포인터여야 하는 슬롯”이 0이면, CPU는 사실상 `pc=0`으로 branch합니다.
   - 보통은 null call로 segfault가 나지만, 언어 의미론 관점에서는 이미 UB라서, 이 지점 이후의 관측 가능한 현상은 무엇이든 가능해집니다(컴파일러가 그 가정을 이용해 다른 최적화를 해도 정당화되기 때문). 공식 발표문도 이 점을 그대로 언급합니다.[^1]

이게 무서운 이유는, “null pointer deref 같은 C스러운 실수”가 아니라 “컴파일러가 safe 코드에서 호출 가능한 vtable 엔트리를 null로 만들어 버린 것”이라, 코드 리뷰/Clippy/Miri 같은 일반적인 방어막이 개입할 틈이 거의 없다는 점입니다. 결과적으로 마지막 방어선은 통합 테스트나 e2e 테스트의 실제 실행이 됩니다.

## 이번 버그가 터진 코드 패턴: boxed async service + 커스텀 async-erasure

공식 발표문은 “some circumstances”라고만 말하지만, 실제로 어떤 조건에서 폭발했는지는 rust-lang/rust 이슈에 꽤 구체적으로 남아 있습니다. 사건의 중심은 `rama` 프로젝트에서 보고한 #161441입니다.[^4]

이 이슈는 다음 특징을 함께 갖습니다.

- 관측 환경: aarch64-apple-darwin에서 관측되었고 CI에서도 재현된다고 명시합니다.[^4]
- 버전 비교: 같은 소스가 Rust 1.97.1에서는 정상, 1.98.0에서는 크래시, nightly-2026-07-16에서는 다시 정상이라고 보고합니다.[^4]
- 증상: “Rust 1.98 emits a zero method entry in a compiler-generated vtable. Safe Rust dispatches through that entry and the process segfaults at address zero.”라고 정리합니다.[^4]
- 더 구체적인 기계 수준 관찰: 호출자가 vtable + 0x18(= 24) 오프셋에서 메서드 포인터를 로드해 그 값으로 branch하는데, 거기가 0이라 `pc=0`으로 떨어진다는 설명이 있습니다.[^4]

여기서 “0x18에 있는 첫 번째 메서드 슬롯”이라는 관찰은 매우 실전적입니다. 흔히 Rust vtable을 (단순화해) `[drop_in_place, size, align, method0, method1, ...]` 형태로 설명하는데, 앞의 3개 포인터/워드 다음이 첫 메서드 포인터라서 24바이트 오프셋이 자연스럽습니다. 이슈에서도 drop/size/alignment 필드는 정상인데 첫 메서드 슬롯만 0이라고 했습니다.[^4]

그리고 “왜 0이 들어갔나”에 대한 추정이 이슈에 남습니다.

- `-Zprint-mono-items` 기준으로 1.98에서는 erased caller는 수집되는데, concrete `Service::serve` 메서드는 수집되지 않았다고 합니다.
- 반면 nightly-2026-07-16에서는 메서드와 async closure까지 모두 수집됐다고 비교합니다.
- 그 결과 “predicate가 impossible로 잘못 판정되어 VtblEntry::Vacant로 갔을 수 있다”는 추정이 붙습니다.[^4]

`VtblEntry::Vacant` 자체는 rustc 내부에서 “bounds가 만족되지 않을 때 vacant slot을 둘 수 있다”는 맥락으로 등장합니다. rustc 소스의 vtable 관련 코드에도 “Vacant slots when bounds aren't satisfied”라는 코멘트가 남아 있습니다.[^5]

즉 이번 버그를 “vtable이 깨졌다”로만 보면 너무 뭉뚱그려지고, 실제로는 다음과 같은 조합에서 발화한 것으로 읽는 편이 유용합니다.

- async를 반환하는 `Service` 계열 추상화
- `Arc<dyn ...>` 또는 `Box<dyn ...>`로 경계를 세워 동적 디스패치로 넘기는 패턴
- associated type + generic predicate가 복잡해지는 순간
- 컴파일러가 “이 메서드는 호출 불가능한 경로”라고 잘못 증명해 버리면, vtable 메서드 엔트리를 Vacant 처리(= 사실상 null 엔트리) 할 가능성

이 패턴이 흔한 이유는, Rust 생태계에서 “async trait을 object-safe처럼 쓰고 싶다”는 요구를 만족시키기 위해, boxed future를 돌려주는 커스텀 erasure trait을 직접 만들거나(tower의 `Service` 류 추상화도 결국 같은 축), async closure를 `Pin<Box<dyn Future + Send + '_>>`로 감싸는 쪽으로 현실적인 절충을 하기 때문입니다.

#161441에서도 workaround가 매우 시사적입니다. 요지는 “erased value의 vtable에 중요한 dispatch를 담지 말고, dispatch를 별도의 함수 포인터로 분리해 두자”입니다. 이슈에 올라온 workaround 코드 조각도 “Keep dispatch separate from the erased value's vtable”이라고 주석을 달고, `dyn Any`에 값을 넣고 `serve`는 별도 함수 포인터로 유지하는 형태로 바꿉니다.[^4]

이 workaround는 성능/구조 면에서 항상 최선은 아니지만, “vtable 엔트리 생성에 대한 컴파일러의 판단”을 우회해 “내가 가진 함수 포인터는 최소한 non-null이며, 타입 `T`에 대한 downcast가 성공한다는 불변식을 내가 관리한다”로 책임을 옮깁니다. 컴파일러 버그가 다시 터져도 공격 면적이 줄어드는 방향입니다.

## 크래시가 safe 코드에서 보이는 이유: 잘못된 vtable은 이미 안전성 경계 밖

Rust에서 “UB는 unsafe에서만 나온다”는 직관이 깨지는 순간이 몇 가지 있는데, 컴파일러 미스컴파일이 그중 대표적인 케이스입니다.

공식 발표문이 “safe Rust가 그 엔트리를 통해 dispatch한다”고 강조한 이유도 여기 있습니다. 개발자는 unsafe를 작성하지 않았고, trait object를 정상적으로 구성했으며, 메서드 호출도 정상적인 문법으로 했는데, 컴파일러가 생성한 vtable이 그 호출을 지탱하지 못한 겁니다.[^1]

이 지점에서 중요한 운영 관점의 결론은 하나입니다.

- “우리는 안전한 Rust만 쓰니까 런타임에서 이런 종류의 크래시는 없다”가 아니라,
- “우리는 unsafe를 줄여서 크래시 확률을 낮췄지만, toolchain이 보장하는 하부 계약(ABI/vtable/codegen)이 깨지면 런타임 크래시는 여전히 나온다”가 맞습니다.

그래서 팀 차원의 대응은 코드 레벨의 lint 추가가 아니라, toolchain 업데이트와 CI 검증 전략 쪽으로 가야 합니다.

## CI에서 잡는 최소 재현 전략: 재현 코드를 ‘내 코드’로 만들지 않는 방법

미스컴파일 대응에서 늘 부딪히는 현실은 이겁니다.

- “우리 서비스 코드에서만 재현되는” 문제가 터졌다.
- 그런데 MCVE로 줄이면 증상이 사라진다.
- CI는 기본적으로 `cargo test` 수준이고, e2e는 느려서 자주 못 돌린다.

이번 건은 그 전형을 그대로 따릅니다. #161441 보고도 “boxed service를 다른 데서도 많이 쓰고, async dynamic dispatch 트릭도 다른 trait에서 쓰지만, 이상하게 이 예제에서만 터진다”라고 적혀 있습니다.[^4]

그래서 최소 재현 전략을 “내 코드에서 최소 재현을 만들자”로 시작하면 보통 시간만 잃습니다. 대신, 재현을 ‘표준화된 외부 시나리오’로 고정해 툴체인 검증에 쓰는 편이 효과적입니다.

### 1) upstream 재현을 toolchain canary로 고정하기 (Rama 케이스)

이번 건은 이슈에 재현 스크립트가 실전 수준으로 들어 있습니다. 특정 커밋을 checkout하고, 1.98.0에서 빌드한 뒤 바이너리를 띄우고 curl로 CONNECT를 때려서 죽는지 확인하는 방식입니다.[^4]

그 내용을 요약하면 다음과 같은 “toolchain 검증용 e2e”가 됩니다.

- repo: `plabayo/rama`
- commit: `0b4aa58e33e9d07db2718a3886c05b673ba9a70e`
- build: `cargo +<toolchain> build -p rama-examples --features=... --bin http_mitm_proxy_boring`
- run + curl: proxy를 띄우고 `curl --proxy ... https://127.0.0.1:1/`를 실행
- 기대 결과:
  - 1.97.1: proxy alive + 502
  - 1.98.0: SIGSEGV pc=0
  - nightly-2026-07-16: proxy alive + 502[^4]

이걸 내 서비스 코드에 이식할 필요가 없습니다. “compiler canary job”로 별도로 두면 됩니다.

- 장점: 내 코드가 아니라도, 이번 종류의 버그(특정 vtable 메서드 슬롯이 Vacant/null로 생성됨)를 강하게 때리는 테스트가 된다.
- 단점: 네트워크/외부 repo 의존성이 생기고, 특정 플랫폼(aarch64 macOS)에서만 강하게 재현될 수 있다.

운영적으로는 “canary는 빨리 깨지는 게 목적”이라서, 외부 의존성은 단점이면서도 장점입니다. 내가 모르는 복잡도를 가진 코드베이스가 내 툴체인을 대신 흔들어 주기 때문입니다.

### 2) 내 코드베이스에서의 최소 전략: ‘동적 디스패치 경계’ 테스트를 release로 강제

이번 버그가 보여준 건 “debug에서만 돌리는 단위 테스트”로는 놓칠 수 있다는 점입니다. #161441의 재현도 `cargo build` 후 실행이고, 런타임 크래시라 결국 실행 경로가 중요합니다.[^4]

그래서 내 코드에서 최소로 할 일은 단순합니다.

- trait object를 건너는 경계(예: `Arc<dyn Service<...>>`, `Box<dyn Handler>`, `dyn Fn(...) -> Pin<Box<dyn Future...>>`)를 지나는 코드를,
- `--release` 바이너리/테스트로,
- 실제로 호출되게 만들기

아래는 현실적인 “boxed async service” 구조를 가진 샘플입니다. 이 코드는 이번 버그를 재현하기 위한 코드가 아니라, CI에서 “vtable 기반 호출이 실제로 실행되는 경로”를 항상 밟게 하기 위한 skeleton입니다.

`Cargo.toml`:

```toml
[package]
name = "vtable-smoke"
version = "0.1.0"
edition = "2024"

[dependencies]
anyhow = "1"
tokio = { version = "1", features = ["rt-multi-thread", "macros", "time"] }
```

`src/main.rs`:

```rust
use anyhow::Result;
use std::{
    future::Future,
    pin::Pin,
    sync::{Arc, atomic::{AtomicU64, Ordering}},
    time::Duration,
};

// 현실에서 tower::Service 같은 축을 단순화한 형태
pub trait Service<Request>: Send + Sync + 'static {
    type Response: Send + 'static;
    type Error: Send + 'static;

    fn serve(
        &self,
        req: Request,
    ) -> Pin<Box<dyn Future<Output = std::result::Result<Self::Response, Self::Error>> + Send + '_>>;
}

// async-erasure를 위한 object-safe trait
trait DynService<Request>: Send + Sync + 'static {
    type Response: Send + 'static;
    type Error: Send + 'static;

    fn serve_box(
        &self,
        req: Request,
    ) -> Pin<Box<dyn Future<Output = std::result::Result<Self::Response, Self::Error>> + Send + '_>>;
}

impl<Request, T> DynService<Request> for T
where
    Request: Send + 'static,
    T: Service<Request>,
{
    type Response = T::Response;
    type Error = T::Error;

    fn serve_box(
        &self,
        req: Request,
    ) -> Pin<Box<dyn Future<Output = std::result::Result<Self::Response, Self::Error>> + Send + '_>> {
        self.serve(req)
    }
}

#[derive(Clone)]
struct BoxService<Request, Response, Error> {
    inner: Arc<dyn DynService<Request, Response = Response, Error = Error>>,
}

impl<Request, Response, Error> BoxService<Request, Response, Error>
where
    Request: Send + 'static,
    Response: Send + 'static,
    Error: Send + 'static,
{
    fn new<T>(svc: T) -> Self
    where
        T: Service<Request, Response = Response, Error = Error>,
    {
        Self { inner: Arc::new(svc) }
    }

    fn serve(
        &self,
        req: Request,
    ) -> Pin<Box<dyn Future<Output = std::result::Result<Response, Error>> + Send + '_>> {
        // 이 한 줄이 결국 vtable dispatch 경계를 강제로 밟습니다.
        self.inner.serve_box(req)
    }
}

#[derive(Clone)]
struct CounterService {
    hits: Arc<AtomicU64>,
}

impl Service<u64> for CounterService {
    type Response = u64;
    type Error = anyhow::Error;

    fn serve(
        &self,
        req: u64,
    ) -> Pin<Box<dyn Future<Output = std::result::Result<Self::Response, Self::Error>> + Send + '_>> {
        let hits = self.hits.clone();
        Box::pin(async move {
            hits.fetch_add(1, Ordering::Relaxed);
            tokio::time::sleep(Duration::from_millis(1)).await;
            Ok(req + 1)
        })
    }
}

#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() -> Result<()> {
    let svc = BoxService::new(CounterService {
        hits: Arc::new(AtomicU64::new(0)),
    });

    // 동시성 + 다회 호출로, 컴파일러가 "호출 불가능" 같은 잘못된 결론을 내기
    // 어려운 실전 경로를 만들어 둡니다.
    let mut tasks = Vec::new();
    for i in 0..1000u64 {
        let svc = svc.clone();
        tasks.push(tokio::spawn(async move {
            let v = svc.serve(i).await.unwrap();
            v
        }));
    }

    let mut sum = 0u64;
    for t in tasks {
        sum += t.await?;
    }

    println!("sum={sum}");
    Ok(())
}
```

실행:

```bash
cargo run --release
```

예상 출력:

```text
sum=500500
```

이 정도로는 컴파일러 버그를 “증명”할 수 없습니다. 하지만 내 코드가 trait object vtable을 통해 실제로 호출되는 경로를 release에서 항상 밟게 만들 수는 있습니다. 이번 사건에서 가장 중요한 건 “그 경로가 테스트에서 실행됐느냐”였고, #161441도 결국 안전한 dispatch가 null 엔트리를 타면서 죽었습니다.[^4]

### 3) toolchain differential 테스트: stable vs beta, stable vs N-1

공식 발표문도 “beta/nightly를 로컬과 CI에서 테스트하고 버그를 리포트해 달라”고 말합니다.[^1]

이건 커뮤니티 기여를 부탁하는 문장처럼 보이지만, 팀 운영 관점에서는 “내가 stable로 올리기 전에 beta로 미리 맞아 보라”는 조언입니다.

CI 최소 형태는 보통 둘 중 하나입니다.

- (가벼운 형태) `cargo test --release`를 `stable`과 `beta` 두 축에서 돌린다.
- (좀 더 보수적) `stable`, `beta`에 더해 “N-1 stable”(직전 stable minor 혹은 직전 known-good toolchain)을 한 축 더 둔다.

이번 사건처럼 “stable-to-stable regression”이고, 1.98.0이 깨졌는데 nightly(2026-07-16)가 정상인 케이스는, beta가 그 중간 어딘가에서 이미 정상이었을 가능성이 큽니다(이건 추정이며, 실제로 beta에서 언제 고쳐졌는지는 이슈/PR 타임라인을 더 봐야 합니다). 다만, 팀이 얻고 싶은 것은 원인 규명보다 “업그레이드 직후에 CI에서 빨리 깨지기”입니다.

### 4) 크래시를 UB로 확장시키지 않는 CI 옵션: sanitizer/ASan은 보조 수단

vtable 엔트리가 null인 경우는 운 좋으면 바로 segfault로 끝납니다. #161441의 관측도 macOS에서 `pc=0`으로 명확히 떨어집니다.[^4]

이런 케이스는 AddressSanitizer 같은 도구가 “더 잘 잡아준다”기보다는, 그냥 OS가 바로 죽여 주는 편이라 오히려 눈에 잘 띕니다.

문제는 공식 발표문이 말한 대로, 이게 UB라서 “항상 segfault로만 보장되지 않는다”는 점입니다.[^1]

그래서 sanitizer는 다음 역할로 두는 게 현실적입니다.

- “재현이 애매하게 비결정적일 때” 런타임 진단을 강화해 로그/스택을 더 얻는다.
- “null call로 즉사하지 않고 이상한 값이 섞이는 형태”로 변형될 때 탐지력을 올린다.

그러나 이번 1.98.0처럼 vtable 엔트리가 0으로 박혀 바로 죽는 계열은, sanitizer가 본질적인 해답이 아니라, release 실행 경로를 CI에서 더 자주 밟는 게 해답입니다.

## 릴리스 직후 팀이 취해야 할 핀/업그레이드 정책: patch를 운영 관점에서 다루기

이번 사건은 “최신 stable patch로 올리면 끝”인 동시에, “patch조차도 배포 체계에서는 변경”이라는 사실을 다시 보여줍니다.

정리하면 1.98.0을 쓴 팀의 선택지는 두 가지뿐입니다.

- 1.98.1로 올리고 전량 재빌드
- 1.97.1로 내리고 전량 재빌드

“툴체인만 업데이트하고 이미 만들어 둔 바이너리를 그대로”는 선택지가 아닙니다. 문제는 소스가 아니라 컴파일 결과물의 기계어에 들어 있으므로, 1.98.0으로 만들어진 artifact는 그대로 UB 가능성을 안고 갑니다. 공식 발표문이 “emitted code”가 UB라고 표현한 이유가 여기 있습니다.[^1]

### 1) rust-toolchain.toml로 ‘정확한 버전’을 고정하는 이유

주간 업데이트 팀일수록 `rustup update stable`을 CI 이미지에 그냥 적용하고 끝내는 경우가 많습니다. 하지만 이번처럼 stable의 patch가 “실행 결과를 바꾸는” 사건을 낼 수 있다면, 최소한 다음은 고정돼 있어야 합니다.

- 어떤 커밋이 어떤 rustc로 빌드됐는지 추적 가능
- 롤백이 가능
- 재현이 가능

가장 단순한 형태는 repository에 `rust-toolchain.toml`을 넣고 channel을 **pin** 하는 것입니다.

```toml
[toolchain]
channel = "1.98.1"
profile = "minimal"
components = ["rustfmt", "clippy"]
```

이렇게 두면 개발자 로컬과 CI가 같은 버전을 바라보게 만들 수 있고, 문제가 생기면 PR revert로 toolchain을 바로 되돌릴 수 있습니다.

### 2) 업그레이드를 ‘모든 브랜치’가 아니라 ‘한 브랜치’에서만 먼저 맞기

주간 업데이트의 함정은 “모든 PR이 동시에 새 컴파일러로 깨지기”입니다. 특히 미스컴파일은 build는 통과하고 런타임에서 깨지므로, PR 단위로 원인을 추적하기가 더 어려워집니다.

운영적으로는 업그레이드 PR을 별도로 두고, 아래 순서로 흘리는 편이 낫습니다.

- (1단계) toolchain upgrade PR을 올린다.
- (2단계) canary job(외부 재현 + 내 release e2e)을 충분히 돌린다.
- (3단계) main에 merge한다.

이 과정은 “patch는 무조건 바로 올린다”와 충돌하지 않습니다. 오히려 “바로 올리되, 올리는 행위를 추적 가능한 단위로 만들자”에 가깝습니다.

### 3) N-1 stable을 CI에 남겨 두는 이유

이번 #161441은 stable-to-stable regression으로 분류되어 있고, 이슈 라벨에도 regression-from-stable-to-stable이 붙어 있습니다.[^4]

이런 종류의 사고를 겪고 나면, “stable 하나만 테스트하는 CI”는 툴체인 문제를 코드 문제로 오인할 가능성이 커집니다.

- stable에서만 크래시 → 내 코드 버그로 오해
- N-1 stable에서는 정상 → toolchain regression으로 바로 분류

특히 동적 디스패치 경계는 “테스트에서 호출되기만 하면 거의 무조건 터진다” 같은 형태가 많아서, 한 번이라도 N-1 비교가 되면 triage 속도가 급격히 빨라집니다.

### 4) 즉시 적용해야 하는 운영 규칙: 1.98.0 artifact는 폐기하는 게 맞다

이번 사건의 실무적 결론은 강합니다.

- 1.98.0으로 빌드된 프로덕션 바이너리가 있다면, 그 바이너리를 “신뢰 가능한 safe Rust 결과물”로 취급하기 어렵습니다.
- 특히 `dyn Trait` 기반으로 async service/handler를 넘기는 경계가 많은 서버라면, 발화 조건이 내 코드에 없다고 단정할 근거가 없습니다.

따라서 팀 정책 문서에는 최소한 다음 문장이 들어가야 합니다.

- “컴파일러 미스컴파일이 포함된 버전으로 빌드된 artifact는, 소스 변경이 없더라도 toolchain 변경만으로 재빌드 대상으로 분류한다.”

이건 보안 이슈처럼 CVE로 떨어지지 않아도, 운영 안전성 관점에서는 동일한 강도로 다뤄야 하는 분류입니다.

## 반론과 회의론: 과잉 대응인가, 아니면 기본값을 바꿔야 하나

이번 사건을 두고 흔히 나오는 반론은 대략 이렇습니다.

### “macOS aarch64에서만 보이는데, 우리랑 상관없다”

#161441에 “Observed on aarch64-apple-darwin”라고 적혀 있는 건 사실입니다.[^4]

다만 이걸 “그 플랫폼 전용”으로 결론 내리기에는 정보가 부족합니다.

- 같은 버전의 rustc가 다른 target에서도 동일한 논리 오류(불가능 predicate 판정)를 내릴 수 있습니다.
- 재현이 쉬운 환경이 macOS aarch64였을 뿐, 다른 환경에서는 “운 좋게 다른 코드 배치로 안 터지거나”, “다른 형태의 UB로 더 늦게 터질” 수도 있습니다.

따라서 플랫폼 제한을 근거로 대응을 안 하는 건, 정보 부족을 낙관으로 메우는 쪽에 가깝습니다.

### “safe Rust만 쓰면 UB는 없다”

공식 발표문이 이미 safe dispatch가 null 엔트리를 타는 케이스를 인정합니다.[^1]

safe/unsafe 구분은 “컴파일러가 계약을 지킨다”는 전제 위에서만 유효합니다. 컴파일러가 잘못된 vtable을 만들면, 그 순간 경계는 무너집니다.

### “그럼 매번 컴파일러를 의심해야 하나”

결론은 “매번 의심”이 아니라 “의심하지 않아도 되도록 프로세스를 만든다”입니다.

- canary
- N-1
- beta
- release e2e

이 네 가지가 있으면, 컴파일러를 의심하는 건 개발자의 감이 아니라, CI가 주는 diff 기반의 사실이 됩니다.

## 앞으로 지켜볼 것: vtable/trait solver 주변의 ‘불가능 판정’이 만드는 위험

#161441에는 이 현상이 과거 이슈(#152735, #153596)와 관련이 있을 수 있고, #158148과도 가깝다고 적혀 있습니다.[^4]

여기서 중요한 포인트는 “vtable 엔트리를 Vacant로 두는 메커니즘”이 실제로 존재한다는 사실입니다. rustc 내부는 bounds가 만족되지 않으면 vacant slot을 만들 수 있다는 설계를 갖고 있습니다.[^5]

그 자체는 합리적입니다. 문제는 “만족되는 bounds를 만족되지 않는다”고 판정하면, 그 순간 vacant slot은 단순한 내부 최적화가 아니라 런타임 UB 트리거가 됩니다.

Rust의 trait system, 특히 async/closure/associated type이 엮인 지점에서 “불가능” 판정은 컴파일러 내부 추론의 깊은 부분을 타고 들어가고, 이번 이슈 라벨에도 A-async-await, A-closures, A-impossible-bounds, A-dyn-trait 같은 태그가 동시에 붙어 있습니다.[^4]

이건 특정 버그 하나가 끝났다고 안심하기보다는, “이 계열의 버그는 앞으로도 비슷한 모양으로 다시 나올 수 있다” 쪽이 더 현실적인 관측입니다.

## 2026-09-06 KST 기준으로 정리되는 대응 기준

- 1.98.1은 1.98.0의 vtable 생성 미스컴파일을 patch로 수정했고, 공식 발표문이 UB 가능성을 명시합니다.[^1]
- 보고된 재현은 `rama` 프로젝트의 boxed async service 경계에서, vtable의 첫 메서드 슬롯(오프셋 0x18)이 0이 되어 safe dispatch가 `pc=0`으로 떨어지는 형태입니다.[^4]
- 이 계열을 CI에서 잡는 최소 전략은 “내 코드에서 MCVE를 만들기”가 아니라, (1) 외부 재현을 canary로 두고, (2) 내 코드의 동적 디스패치 경계를 release에서 강제로 밟게 만들고, (3) stable/beta/N-1 differential을 유지하는 것입니다.[^1]
- 업그레이드 정책은 “patch는 안전하니까 자동”이 아니라 “patch도 artifact 의미론을 바꿀 수 있으니 pin + canary + 재빌드 기준”이 기본값이 되어야 합니다.

이 사건을 겪은 뒤에도 “툴체인은 자주 올리되, 올리는 행위는 통제 가능한 단위로 만들고, 결과물은 재현 가능하게 남긴다”가 가장 비용 대비 효과가 큰 결론입니다.

## 참고 자료

- [Announcing Rust 1.98.1](https://blog.rust-lang.org/2026/09/03/Rust-1.98.1/)
- [Rust Release Notes](https://doc.rust-lang.org/releases.html)
- [rust-lang/rust#161441: rustc emits a vacant vtable slot for a callable boxed async service (Rust 1.98)](https://github.com/rust-lang/rust/issues/161441)
- [Trait object types - The Rust Reference](https://doc.rust-lang.org/reference/types/trait-object.html)
- [Rust Release Announcements 목록](https://blog.rust-lang.org/releases/)

최종적으로는, 이번 1.98.1을 단순한 버그 픽스가 아니라 “컴파일러도 운영 리스크의 일부”라는 전제를 문서와 CI에 박아 넣게 만든 사건으로 보는 편이 맞습니다.

[^1]: <https://blog.rust-lang.org/2026/09/03/Rust-1.98.1/>
[^2]: <https://doc.rust-lang.org/releases.html>
[^3]: <https://doc.rust-lang.org/beta/reference/types/trait-object.html>
[^4]: <https://github.com/rust-lang/rust/issues/161441>
[^5]: <https://chromium.googlesource.com/external/github.com/rust-lang/rust/%2B/865518d1f2c2139a78043780f6b76020b98e5beb/compiler/rustc_middle/src/ty/vtable.rs>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
