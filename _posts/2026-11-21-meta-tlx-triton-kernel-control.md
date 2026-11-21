---
title: "Meta TLX: Triton 생산성과 하드웨어 네이티브 커널 제어 사이 메우기"
description: "TLX가 추가하는 저수준 제어 포인트와 Triton 코드베이스에 점진 도입하는 방법, 성능 회귀를 막는 벤치 계약을 정리합니다."
date: 2026-11-21 12:28:31 +0900
categories: ["Performance", "TLX"]
tags: ["tlx", "triton", "gpu-kernel", "performance", "profiling", "benchmarking"]
render_with_liquid: false
---

## Triton이 빨라진 속도만큼, GPU 최적화의 단위가 바뀌었다

Meta가 2026-11-10에 공개한 TLX(Triton Low-level Language Extensions)는 Triton을 대체하는 새 DSL이라기보다, Triton이 원래 강점으로 삼던 생산성을 유지한 채로 최신 GPU의 실행 모델을 코드에 드러내는 쪽을 택한 확장입니다. Meta 쪽 설명은 요약하면 명확합니다. 최근 GPU에서 중요한 건 thread/block 수준의 병렬화 자체가 아니라, warp group 단위의 역할 분담(예: load 전담 vs tensor core 전담)과 비동기 실행(메모리 이동, tensor core op, barrier)을 어떻게 오케스트레이션하느냐로 옮겨갔고, Triton의 blocked programming model만으로는 그 실행 구조가 소스에 충분히 노출되지 않는 순간이 잦아졌다는 겁니다. 그래서 TLX가 “explicit warp-group and cluster-level orchestration”을 제공해 그 간극을 메우겠다는 방향을 제시합니다.[^1]

이건 LLM 서빙/학습 최적화를 현장에서 해 본 입장에서도 체감이 큽니다. 모델이 커지면 커질수록, 그리고 GPU 세대가 바뀔수록(특히 Hopper/Blackwell처럼) 병목이 단순히 GEMM/attention 하나가 아니라 다음으로 이동합니다.

- kernel 간 경계에서 발생하는 메모리 왕복과 launch overhead
- persistent kernel로 갈 때 스케줄링/로드밸런싱 문제
- async copy / TMA / tensor memory 같은 하드웨어 기능을 쓰느냐 마느냐가 cost model을 바꿔버리는 지점

이때 “커널을 한 번 신의 손으로 튜닝”해서 끝내는 접근은 재현도 어렵고, 회귀도 자주 나고, 무엇보다 다음 세대 GPU에서 다시 비용을 치르게 됩니다. TLX를 볼 때도 peak 성능 숫자보다 다음 3가지를 중심에 놓는 편이 실전적입니다.

- **TLX가 추가하는 저수준 제어 포인트가 정확히 무엇인지**
- **기존 Triton 코드베이스에 어떻게 점진 도입할지**
- **성능 회귀를 막기 위한 벤치/프로파일링 계약을 어떻게 만들지**

## TLX의 핵심: MIMW로 실행 오케스트레이션을 코드에 올린다

Meta는 TLX의 프로그래밍 모델을 MIMW(Multi-Instruction, Multi-Warp)라고 부릅니다. thread(SIMT)도 아니고 block(SIMB)도 아닌, warp group 단위에서 여러 실행 에이전트가 협력/동기화/핸드오프하는 구조를 1급으로 올리는 관점입니다. 논문 초록에서도 TLX는 “warp-group granularity에서 orchestration을 표현하면서 Triton의 blocked model은 유지”하고, multi-warp execution, local-memory orchestration, async ops, cluster-aware control을 노출한다고 요약합니다.[^2]

이 관점이 중요한 이유는 TLX를 쓰면 “Triton 코드가 더 복잡해진다”가 아니라, 원래 implicit하게 컴파일러가 알아서 해주길 기대하던 실행 구조를 코드로 명시하게 된다는 데 있습니다.

- Triton만으로도 많은 memory-bound workload는 fusion과 compiler-managed access 최적화로 잘 나옵니다.
- 하지만 warp specialization, async memory movement, tensor memory, cluster-level execution 같은 기능은 그냥 인스트럭션 몇 개 추가한다고 해결되는 게 아니라, producer/consumer 역할 분리와 barrier phase 같은 실행 관계 자체가 성능을 좌우합니다.[^1]

결국 TLX의 가치가 생기는 구간은 “계산을 어떻게 하느냐”보다 “어떤 실행자들이 어떤 타이밍으로 협력하느냐”가 병목이 되는 커널입니다.

## TLX가 여는 저수준 제어 포인트: 어디까지 내려갈 수 있나

TLX 문서의 개요는 TLX를 “low-level, warp-aware, hardware-near extension”이라고 정의하고, 하드웨어 지향 primitive와 명시적 async control flow를 제공한다고 설명합니다.[^3]

실제로 코드에 영향을 주는 제어 포인트를 묶어보면 대략 아래 5종입니다.

### 1) Local buffer를 명시적으로 잡고 돌리는 모델

`tlx.local_alloc(shape, dtype, NUM_BUFFERS)`는 thread block마다 local buffer를 여러 개 잡습니다. 문서상 “layout은 consumer로부터 inferred”된다고 되어 있고, SMEM뿐 아니라 Blackwell 계열에서는 TMEM(tensor memory) 쪽 할당도 별도로 노출됩니다.[^4]

중요한 건 이게 단순히 scratchpad를 만든다는 얘기가 아니라, software pipeline에서 rotating buffer를 커널이 직접 굴릴 수 있다는 의미입니다. Triton의 `num_stages`는 compiler pipelining 힌트에 가깝지만, TLX는 “어떤 버퍼 인덱스를 지금 쓰고, 몇 stage ahead를 prefetch하고, 언제 재사용하는지”가 소스에 남습니다.

또 하나 실전 포인트는 reuse/alias입니다. TLX는 `reuse=`를 통해 서로 다른 논리 버퍼가 같은 저장소를 공유하는 형태도 지원합니다. TMEM을 쓰는 커널에서는 용량 제약이 바로 병목이 되기 때문에, 이런 alias/reuse 모델이 곧 튜닝 포인트가 됩니다.[^4]

### 2) Async memory movement를 “토큰 + 그룹” 단위로 다룬다

PyTorch 쪽 Triton Plugin Extensions 글에서 TLX의 core op로 `tlx.async_load`, `tlx.async_load_commit_group`, `tlx.async_load_wait_group`를 직접 나열합니다.[^5]

이 조합은 커널 작성자에게 2가지를 요구합니다.

- load를 언제 issue하고
- 그 load들의 completion을 어떤 granularity로 기다릴지

Triton만 사용할 때는 이런 모델이 대부분 컴파일러 내부 스케줄러로 감춰졌고, 그래서 어떤 세대에서는 잘 나오던 kernel이 다른 세대/드라이버/컴파일러 조합에서 성능이 흔들리는 경우가 있었습니다. TLX는 그 스케줄을 코드 레벨 계약으로 바꿉니다.

Hopper/Blackwell에서는 descriptor 기반(TMA)도 노출됩니다. 예를 들어 `tlx.make_tensor_descriptor`로 descriptor를 만들고, 이후 `tlx.async_descriptor_load` 같은 API로 descriptor 기반 async load를 수행하는 식입니다.[^6]

이 지점이 일반적인 `tl.load` 대비 의미가 큰 이유는, 메모리 이동이 단순한 “load instruction”이 아니라 별도의 하드웨어 엔진 및 barrier completion과 엮이는 구조로 바뀌기 때문입니다.

### 3) Tensor core compute도 async로 쌓고 기다린다

TLX는 tensor core 작업을 `tlx.async_dot`로 issue하고, `tlx.async_dot_wait(pendings, acc)`로 in-flight 개수를 기준으로 completion을 기다리는 모델을 제공합니다. 문서에서도 `async_dot` / `async_dot_wait`를 분리된 API로 다루고 있습니다.[^7]

이 모델이 주는 실전상의 변화는 단순합니다.

- compute를 issue하는 타이밍과
- 다음 stage의 load를 issue하는 타이밍이

Triton의 “for loop 한 바퀴”라는 단일 구조에 묶이지 않습니다. 커널이 제대로 파이프라이닝 되면, 한 iteration은 (1) 이전 stage compute의 tail을 정리하고 (2) 현재 stage compute를 발사하고 (3) 미래 stage load를 발사하는 형태가 됩니다.

### 4) barrier와 fence가 “코드의 correctness boundary”로 바뀐다

TLX는 `tlx.alloc_barriers`로 mbarrier를 할당하고, `tlx.barrier_wait(bar, phase)`, `tlx.barrier_arrive(...)` 같은 API를 제공합니다.[^8]

여기서 중요한 건 두 가지입니다.

- barrier init의 scope(`scope="cta"`/`"cluster"`)는 “arrive_count/expected bytes/wait”를 대신해주지 않습니다. 문서도 initialization scope가 handoff를 대체하지 않는다고 못 박고 있습니다.[^8]
- cluster shared memory에서는 memory proxy ordering 같은 하드웨어 레벨 제약이 있고, 이를 위해 `tlx.fence("async_shared_cluster")` 같은 fence의 책임 범위가 존재합니다. 문서가 proxy fence와 cluster rendezvous가 서로 다른 책임을 가진다고 분리해서 설명하는 이유가 있습니다.[^8]

즉 TLX로 내려가면, 성능만이 아니라 correctness가 “배리어/펜스의 사용 계약”에 의해 좌우됩니다. 이건 장점이자 비용입니다.

### 5) Warp specialization과 task 병렬을 언어로 올린다

`tlx.async_tasks()` 영역을 열고, 그 안에서 `tlx.async_task("default")` 같은 trunk task와 `tlx.async_task(num_warps=4)` 같은 warp-specialized task를 선언할 수 있습니다. 문서가 말하듯 각 task는 thread block 내에서 전용 warp subset으로 병렬 실행됩니다.[^9]

이건 “커널 안에서 producer/consumer를 concurrent하게 돌린다”를 Python 소스에서 표현하게 해줍니다. CUDA에서 하면 PTX 레벨 bookkeeping이 훨씬 커지는 구조를, TLX는 Triton 문법 틀 안에서 흡수하려고 합니다.

그리고 TLX만이 답은 아닙니다. fbtriton 쪽은 TLX 외에도 AutoWS(compiler가 자동 warp specialization을 시도)를 별도로 제공합니다. `tl.range(..., warp_specialize=True)` 같은 마커를 달면, 컴파일러가 loop 내부를 partition하려고 시도한다고 문서에 나옵니다.[^10]

## 점진 도입의 기본 전략: “더 낮게”가 아니라 “더 좁게”

fbtriton README는 같은 목표(현대 GPU에서 warp-level 제어)를 3단계로 나눠 설명합니다. AutoWS(코드 변경 거의 없음), TorchTLX(Inductor 템플릿 경유), TLX(커널을 직접 작성)입니다.[^11]

이 구분이 좋은 이유는, TLX 도입을 “전사적으로 TLX로 갈아탄다” 같은 프로젝트로 만들지 않게 해주기 때문입니다. 나는 TLX를 다음 순서로 접근하는 게 합리적이라고 봅니다.

### 1) baseline Triton을 유지한 채로 AutoWS를 먼저 태워본다

AutoWS는 `warp_specialize=True` 같은 마커로 compiler가 파티션을 만들도록 요청하는 모델입니다.[^10]

여기서 얻는 건 2가지입니다.

- warp specialization이 성능에 영향을 주는 workload인지 빠르게 감을 잡는다
- correctness/벤치 harness를 그대로 유지한 채 “실행 구조 변화”를 작은 폭으로 주입한다

AutoWS는 “요청이지 결정이 아니다”라서, 컴파일러가 파티션을 만들지 못하면 그냥 warp specialization 없이 컴파일되는 식으로 빠져나갈 수 있습니다.[^10]

이 단계가 중요한 이유는 TLX의 비용이 “코드 작성량”이 아니라 “디버깅과 회귀 대응 비용”이기 때문입니다. AutoWS에서 그 비용을 일부 선행 측정할 수 있습니다.

### 2) 특정 hotspot에만 TLX를 넣되, kernel boundary를 유지한다

TLX는 Triton 확장이라, 커널 전체를 TLX로 재작성하기보다 “스케줄/메모리 이동/동기화가 필요한 좁은 구간”에만 투입하는 방식이 자연스럽습니다. Meta 글 자체도 TLX를 Triton 위에 “두 번째 레이어”로 얹는다고 설명합니다.[^1]

이때 커널 경계를 유지한다는 건,

- 입력/출력 tensor contract를 바꾸지 않고
- dispatch 로직(autotune, config space)을 크게 흔들지 않으면서
- 내부 구현만 TLX로 낮춘다

는 뜻입니다. 특히 프로덕션에서는 이 방식이 회귀를 줄입니다.

### 3) 배포 경로를 2가지로 나눠 둔다: fbtriton fork vs uTLX plugin

fbtriton README에는 설치 경로가 두 가지로 정리돼 있습니다.

- `pip install fbtriton` (Triton fork 자체 사용)
- `pip install triton-utlx` 후 `TRITON_PLUGIN_PATHS`로 plugin 로드(uTLX)[^11]

uTLX 경로는 “fork를 채택하는 부담”을 줄여줍니다. 대신 plugin이 로드될 Triton 빌드가 `TRITON_EXT_ENABLED`여야 하는 제약이 있고, README는 PyTorch 배포에 포함된 Triton은 기본적으로 이 옵션이 켜져 있다고 설명합니다.[^11]

프로덕션에선 대체로 다음 식으로 의사결정하게 됩니다.

- 연구/실험/프로토타입: fbtriton으로 빠르게 TLX 커널을 확인
- 제품 배포/호환성: PyTorch 배포 Triton + uTLX plugin으로 범위를 통제

### 4) TorchInductor 경로로 가져가야 하면 TorchTLX를 고려한다

TorchTLX는 TLX 커널을 Inductor 템플릿으로 가져와서, 템플릿 선택과 epilogue fusion 로직까지 바꾸는 접근입니다. 문서에는 `TORCHINDUCTOR_TLX_MODE`라는 knob가 있고 `allow`/`force` 같은 모드가 정의돼 있습니다.[^12]

내 경험상 이 단계는 “커널 하나를 잘 만들었다”보다 “그 커널이 전체 그래프에서 의미 있게 호출되게 만들었다”가 더 어렵습니다. TorchTLX는 그 접점을 건드립니다.

## 실행 가능한 예제: TLX pipelined GEMM을 벤치 계약에 넣는 방법

여기서는 TLX 문서의 기능 소개를 반복하기보다, 실제로 돌아가는 커널 형태가 어떤지, 그리고 그것을 성능 계약(benchmark contract)으로 감싸는 방법을 같이 둡니다.

예제는 fbtriton 저장소의 `hopper_gemm_pipelined.py` 튜토리얼 커널을 기반으로, (1) correctness 검증 (2) 반복 가능한 벤치 측정 (3) 결과 출력까지 포함하는 형태로 정리했습니다. 튜토리얼 커널이 사용하는 핵심 TLX API는 `tlx.local_alloc`, `tlx.async_load`, `tlx.async_load_commit_group`, `tlx.async_load_wait_group`, `tlx.async_dot`, `tlx.async_dot_wait`입니다.[^13]

### 환경 가정

- NVIDIA Hopper(sm90) 이상에서만 TLX path를 실행하도록 가드합니다.
- 설치는 fbtriton 기준으로 적습니다.

fbtriton 설치는 README가 제시하는 그대로 갑니다.[^11]

```bash
# (권장) 기존 triton 패키지 제거: 두 배포판이 같은 triton/ 디렉터리를 소유
pip uninstall -y triton

# fbtriton 설치
pip install fbtriton

# torch는 환경에 맞게 설치되어 있다고 가정
python -c "import torch; print(torch.__version__)"
```

### 벤치 스크립트: `bench_tlx_gemm.py`

아래 코드는 Hopper에서 TLX GEMM을 실행하고, 동일한 입력으로 `torch.matmul`과 시간을 비교합니다. 측정은 Triton이 제공하는 `triton.testing.do_bench`를 사용합니다. 이 함수는 warmup/rep(측정 윈도우)와 quantile을 받을 수 있습니다.[^14]

```python
import argparse
import math

import torch
import triton
import triton.language as tl

try:
    # fbtriton / TLX
    import triton.language.extra.tlx as tlx
    HAS_TLX = True
except Exception:
    tlx = None
    HAS_TLX = False

def is_hopper_or_newer() -> bool:
    if not torch.cuda.is_available():
        return False
    major, minor = torch.cuda.get_device_capability()
    return major >= 9

@triton.autotune(
    configs=[
        triton.Config(
            {
                "BLOCK_SIZE_M": 128,
                "BLOCK_SIZE_N": 256,
                "BLOCK_SIZE_K": 64,
                "GROUP_SIZE_M": 8,
                "NUM_STAGES": 3,
            },
            num_warps=8,
        ),
    ],
    key=["M", "N", "K"],
)
@triton.jit
def tlx_gemm_pipelined_hopper(
    a_ptr,
    b_ptr,
    c_ptr,
    M,
    N,
    K,
    stride_am,
    stride_ak,
    stride_bk,
    stride_bn,
    stride_cm,
    stride_cn,
    BLOCK_SIZE_M: tl.constexpr,
    BLOCK_SIZE_N: tl.constexpr,
    BLOCK_SIZE_K: tl.constexpr,
    GROUP_SIZE_M: tl.constexpr,
    NUM_STAGES: tl.constexpr,
):
    # 프로그램 ID를 1D로 잡고 (pid_m, pid_n)로 매핑
    pid = tl.program_id(axis=0)
    num_pid_m = tl.cdiv(M, BLOCK_SIZE_M)
    num_pid_n = tl.cdiv(N, BLOCK_SIZE_N)

    num_pid_in_group = GROUP_SIZE_M * num_pid_n
    group_id = pid // num_pid_in_group
    first_pid_m = group_id * GROUP_SIZE_M
    group_size_m = tl.minimum(num_pid_m - first_pid_m, GROUP_SIZE_M)

    pid_m = first_pid_m + ((pid % num_pid_in_group) % group_size_m)
    pid_n = (pid % num_pid_in_group) // group_size_m

    offs_am = (pid_m * BLOCK_SIZE_M + tl.arange(0, BLOCK_SIZE_M)) % M
    offs_bn = (pid_n * BLOCK_SIZE_N + tl.arange(0, BLOCK_SIZE_N)) % N
    offs_k = tl.arange(0, BLOCK_SIZE_K)

    a_ptrs = a_ptr + (offs_am[:, None] * stride_am + offs_k[None, :] * stride_ak)
    b_ptrs = b_ptr + (offs_k[:, None] * stride_bk + offs_bn[None, :] * stride_bn)

    # NUM_STAGES개의 rotating buffer를 잡고
    buffers_A = tlx.local_alloc((BLOCK_SIZE_M, BLOCK_SIZE_K), tlx.dtype_of(a_ptr), NUM_STAGES)
    buffers_B = tlx.local_alloc((BLOCK_SIZE_K, BLOCK_SIZE_N), tlx.dtype_of(b_ptr), NUM_STAGES)

    # 파이프라인을 채우기 위해 NUM_STAGES-1개를 미리 프리페치
    for i in tl.range(0, NUM_STAGES - 1, loop_unroll_factor=NUM_STAGES - 1):
        a = tlx.local_view(buffers_A, i)
        b = tlx.local_view(buffers_B, i)

        token_a = tlx.async_load(a_ptrs, a, mask=offs_k[None, :] < K - i * BLOCK_SIZE_K)
        token_b = tlx.async_load(b_ptrs, b, mask=offs_k[:, None] < K - i * BLOCK_SIZE_K)
        a_ptrs += BLOCK_SIZE_K * stride_ak
        b_ptrs += BLOCK_SIZE_K * stride_bk
        tlx.async_load_commit_group([token_a, token_b])

    acc = tl.zeros((BLOCK_SIZE_M, BLOCK_SIZE_N), dtype=tl.float32)

    # Triton의 자동 파이프라이닝은 끄고(num_stages=1), TLX 파이프라인을 직접 굴림
    for k in tl.range(0, tl.cdiv(K, BLOCK_SIZE_K), num_stages=1):
        buf = k % NUM_STAGES
        a_k = tlx.local_view(buffers_A, buf)
        b_k = tlx.local_view(buffers_B, buf)

        tlx.async_load_wait_group(NUM_STAGES - 2)
        acc = tlx.async_dot(a_k, b_k, acc)

        # NUM_STAGES-1 ahead 프리페치
        i = k + NUM_STAGES - 1
        a_next = tlx.local_view(buffers_A, i % NUM_STAGES)
        b_next = tlx.local_view(buffers_B, i % NUM_STAGES)

        # 같은 버퍼를 재사용하기 전, 이전 async_dot의 일부 completion을 보장
        acc = tlx.async_dot_wait(1, acc)

        token_a = tlx.async_load(a_ptrs, a_next, mask=offs_k[None, :] < K - i * BLOCK_SIZE_K)
        token_b = tlx.async_load(b_ptrs, b_next, mask=offs_k[:, None] < K - i * BLOCK_SIZE_K)
        tlx.async_load_commit_group([token_a, token_b])

        a_ptrs += BLOCK_SIZE_K * stride_ak
        b_ptrs += BLOCK_SIZE_K * stride_bk

    acc = tlx.async_dot_wait(0, acc)

    c = acc.to(tlx.dtype_of(c_ptr))
    offs_cm = pid_m * BLOCK_SIZE_M + tl.arange(0, BLOCK_SIZE_M)
    offs_cn = pid_n * BLOCK_SIZE_N + tl.arange(0, BLOCK_SIZE_N)

    c_ptrs = c_ptr + stride_cm * offs_cm[:, None] + stride_cn * offs_cn[None, :]
    c_mask = (offs_cm[:, None] < M) & (offs_cn[None, :] < N)
    tl.store(c_ptrs, c, mask=c_mask)

def tlx_gemm(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    assert a.is_cuda and b.is_cuda
    assert a.dtype == torch.float16 and b.dtype == torch.float16
    assert a.is_contiguous() and b.is_contiguous()
    assert a.shape[1] == b.shape[0]

    M, K = a.shape
    _, N = b.shape
    c = torch.empty((M, N), device=a.device, dtype=torch.float16)

    grid = lambda META: (
        triton.cdiv(M, META["BLOCK_SIZE_M"]) * triton.cdiv(N, META["BLOCK_SIZE_N"]),
    )

    tlx_gemm_pipelined_hopper[grid](
        a,
        b,
        c,
        M,
        N,
        K,
        a.stride(0),
        a.stride(1),
        b.stride(0),
        b.stride(1),
        c.stride(0),
        c.stride(1),
    )
    return c

def tflops(M: int, N: int, K: int, ms: float) -> float:
    # GEMM: 2*M*N*K FLOP
    return (2.0 * M * N * K) / (ms * 1e-3) / 1e12

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--M", type=int, default=4096)
    p.add_argument("--N", type=int, default=4096)
    p.add_argument("--K", type=int, default=4096)
    p.add_argument("--warmup_ms", type=int, default=200)
    p.add_argument("--rep_ms", type=int, default=1000)
    args = p.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA not available")

    torch.manual_seed(0)

    M, N, K = args.M, args.N, args.K
    a = torch.randn((M, K), device="cuda", dtype=torch.float16)
    b = torch.randn((K, N), device="cuda", dtype=torch.float16)

    # correctness (참고: PyTorch는 비동기 실행이라 결과를 읽는 시점에 sync가 걸릴 수 있음)
    c_ref = a @ b

    if not (HAS_TLX and is_hopper_or_newer()):
        print(f"TLX disabled (HAS_TLX={HAS_TLX}, hopper_or_newer={is_hopper_or_newer()}).")
        print("Only torch.matmul baseline will run.")
        # torch benchmark
        ms_torch = triton.testing.do_bench(lambda: a @ b, warmup=args.warmup_ms, rep=args.rep_ms, return_mode="median")
        print(f"torch.matmul: {ms_torch:.3f} ms, {tflops(M,N,K,ms_torch):.2f} TFLOPS")
        return

    c_tlx = tlx_gemm(a, b)
    max_abs = (c_tlx - c_ref).abs().max().item()
    print(f"max_abs_error(fp16): {max_abs}")

    # 벤치: median 기준(분산이 크면 quantiles로 p20/p50/p80 같이 보는 편이 안전)
    ms_tlx = triton.testing.do_bench(lambda: tlx_gemm(a, b), warmup=args.warmup_ms, rep=args.rep_ms, return_mode="median")
    ms_torch = triton.testing.do_bench(lambda: a @ b, warmup=args.warmup_ms, rep=args.rep_ms, return_mode="median")

    print(f"TLX GEMM:      {ms_tlx:.3f} ms, {tflops(M,N,K,ms_tlx):.2f} TFLOPS")
    print(f"torch.matmul:  {ms_torch:.3f} ms, {tflops(M,N,K,ms_torch):.2f} TFLOPS")

if __name__ == "__main__":
    main()
```

### 실행 명령과 예상 출력 형태

```bash
python bench_tlx_gemm.py --M 4096 --N 4096 --K 4096
```

예상 출력은 장비마다 다르지만 형태는 대략 아래처럼 나옵니다.

```text
max_abs_error(fp16): 0.5
TLX GEMM:      1.234 ms, 110.00 TFLOPS
torch.matmul:  1.180 ms, 115.00 TFLOPS
```

여기서 중요한 건 숫자 자체가 아니라, 이 스크립트가 “내가 커널을 어떻게 수정하든” 동일한 입력/동일한 측정 윈도우/동일한 비교 baseline을 유지하도록 고정돼 있다는 점입니다. TLX는 튜닝 폭이 커서, 이 계약이 없으면 성능 개선과 회귀를 구분하기가 금방 어려워집니다.

## 벤치/프로파일링 계약: TLX를 숫자 1개로 평가하면 망한다

TLX 도입에서 가장 흔한 실패는, 커널 최적화를 “코드 변경 → TFLOPS 증가/감소”만으로 판단하는 겁니다. 이유는 3가지입니다.

1) 측정 자체가 흔들린다. GPU 실행은 비동기이고, PyTorch도 기본적으로 커널 launch 후 CPU가 기다리지 않습니다. 정확한 측정은 `torch.cuda.synchronize()`를 쓰거나, `torch.cuda.Event`로 타이밍을 찍어야 한다고 PyTorch 문서가 명시합니다.[^15]

2) host sync를 섞으면 벤치가 의미가 바뀐다. CUDA Best Practices Guide에서도 stream/event synchronize는 타이밍 코드에 부적절할 수 있음을 분리해서 설명합니다.[^16]

3) 커널이 빨라져도 end-to-end가 느려질 수 있다. TLX는 종종 persistent/cluster 협력 같은 구조로 가면서 launch 패턴과 리소스 점유 형태 자체가 변합니다.

그래서 TLX를 다룰 때는 “벤치/프로파일링 계약”을 명시적으로 만들어야 합니다. 나는 아래 항목을 계약으로 고정합니다.

### 1) 입력 분포와 shape 세트가 고정돼야 한다

- 단일 shape 벤치만 있으면, 그 shape에만 과최적화하기 쉽습니다.
- LLM 서빙은 batch, seq_len, head_dim이 섞여서 들어오므로 최소한 3~5개 대표 shape이 필요합니다.

### 2) warmup/rep 윈도우는 ms 단위로 고정한다

`triton.testing.do_bench`는 warmup/rep를 “반복 횟수”가 아니라 “시간(ms)”로 받습니다. 이게 좋은 이유는 커널이 빨라져도 느려져도, 측정의 통계적 안정성을 어느 정도 유지하기 쉽기 때문입니다.[^14]

또 median만 보지 말고, 분산이 보이면 quantile을 같이 봅니다. do_bench는 `quantiles=[0.2, 0.5, 0.8]` 같은 형태를 지원합니다.[^14]

### 3) correctness 계약을 “float tolerance”로만 두지 않는다

TLX로 내려가면 barrier/fence 실수로 data race가 나도 결과가 항상 깨지지 않습니다. 특정 shape, 특정 seed, 특정 scheduling에서만 깨지는 경우가 있습니다.

- 고정 seed
- adversarial shape(타일 경계가 많이 걸리는 값)
- mask가 자주 활성화되는 케이스

같은 보호 케이스가 필요합니다.

### 4) 프로파일링은 Nsight Compute에서 roofline/occupancy까지 같이 본다

Nsight Compute Profiling Guide는 roofline chart를 arithmetic intensity(Work/Memory Traffic) 기반으로 설명하고, ridge point를 기준으로 memory-bound/compute-bound 영역을 나눠 해석하라고 안내합니다.[^17]

또 Nsight Compute 문서는 occupancy가 높다고 항상 빠른 건 아니지만, 낮은 occupancy는 latency hiding에 불리하다고 정리합니다.[^18]

TLX 커널은 특히 다음 지표를 같이 봐야 판단이 됩니다.

- DRAM/L2/L1 중 어디 ceiling에 붙어 있는지(roofline)
- achieved occupancy vs theoretical occupancy가 왜 벌어지는지
- async stage를 늘렸더니 register pressure가 올라가서 occupancy가 죽는지

TFLOPS 하나로는 이런 트레이드오프가 안 보입니다.

## 성능 회귀를 막는 운영: TLX Agent가 제시하는 형태가 현실적이다

TLX를 실전에 넣으면 튜닝 자체보다 회귀 방지가 더 어렵습니다. Meta 쪽은 이 문제를 tooling으로 풀려는 흔적이 강하고, 그 중 TLX Agent 문서의 관점이 프로덕션 친화적입니다.

TLX Agent는 “harness-driven optimization loop”로 설명되고, 핵심 문장은 “The harness owns truth”입니다. 즉, 최적화 루프가 correctness 기준을 발명하거나 벤치를 바꾸면 안 되고, 고정된 harness API(build/verify/benchmark/profile) 경계 안에서만 실험을 반복해야 한다는 겁니다.[^19]

이걸 사람 프로세스로 번역하면 다음입니다.

- 커널 PR은 반드시 harness 업데이트와 함께 간다
- harness는 (1) correctness cases.json (2) benchmark repetition/quantile (3) 프로파일링 요청(spec)을 고정한다
- 커널 변경은 benchmark contract를 바꾸는 변경과 분리한다

TLX는 성능 최적화의 자유도가 큰 대신, 한 번 계약이 무너지면 “어느 시점부터 성능이 나빠졌는지”가 안 잡힙니다. kernel 최적화가 아니라 운영 문제로 망하는 케이스가 흔합니다.

## TLX에서 흔히 터지는 함정: barrier/fence/cluster는 디버그 비용을 선불로 요구한다

TLX를 쓰면 반드시 늘어나는 디버깅 비용이 있습니다. 특히 cluster/DSM 쪽은 “성능 최적화”보다 “정의되지 않은 동작”을 피하는 게 먼저입니다.

### cluster에서의 원칙: Arrive Remote, Wait Local

TLX cluster 문서는 multi-CTA mode에서 “remote mbarrier에 wait 하면 undefined behavior”이고, 대신 remote에는 arrive만 하고 wait는 local에서 하라는 원칙을 표로 박아둡니다.[^20]

이건 TLX가 제공하는 API가 충분히 high-level하지 않다는 뜻이 아니라, 하드웨어 스펙의 제한을 그대로 노출한다는 뜻입니다. 성능 최적화는 그 위에서만 가능합니다.

### initialization scope와 fence의 책임이 섞이면, 가끔만 깨지는 race가 나온다

`synchronization` 문서는 cluster-scoped barrier를 prologue에서 초기화하라고 강하게 제한하고, initialization scope가 later pipeline phase의 publication을 보장하지 않는다고 말합니다.[^8]

이 영역을 잘못 다루면, 테스트에서는 통과하지만 실제 트래픽에서만 터지는 종류의 버그가 나옵니다. 커널이 더 빨라지는 건 중요하지만, 프로덕션 ML에서는 “몇 주 동안 계속 돌아간다”가 더 중요합니다. Meta도 LLM pretraining에서 TLX 커널을 장기간 fleet에서 운영했다고 강조하면서, peak throughput 외에 reliability/maintainability/perf stability를 같이 언급합니다.[^1]

## 언제 TLX를 쓰고, 언제 Triton에 남아야 하나

나는 TLX의 포지션을 “최적화의 끝판왕”이라기보다 “하드웨어 세대가 바뀔 때 컴파일러가 따라오길 기다리지 않는 선택지”로 봅니다. 그래서 도입 기준도 그 관점이 맞습니다.

### Triton만으로 충분한 경우

- bandwidth-bound이고, fusion/tiling/autotune만으로도 roofline 근처를 찍는다
- 커널 하나의 peak보다 end-to-end에서 graph break/CPU overhead가 더 크다

이때는 커널 내부를 TLX로 내리기보다, 상위에서 torch.compile/Inductor 쪽을 먼저 만지는 편이 효과가 큽니다.

### AutoWS로 먼저 볼 가치가 있는 경우

- 특정 커널이 load/compute overlap이 안 돼서 bubble이 눈에 보인다
- 하지만 barrier/task/cluster를 직접 쓰는 디버깅 비용을 당장 지불하기 싫다

AutoWS는 `warp_specialize=True`로 compiler가 파티션을 시도하게 하는 경로라서, 최소 비용으로 “warp specialization이 의미가 있는 워크로드인지”를 확인하기 좋습니다.[^10]

### TLX가 실질적으로 필요한 경우

- async pipeline distance, rotating buffer 개수, barrier phase를 커널이 직접 통제해야 한다
- persistent kernel / cluster cooperation / CLC 같은 하드웨어 기능이 성능을 결정한다

Blackwell의 CLC(Cluster Launch Control)를 TLX로 노출한 글은, host에서 grid를 크게 던져도 SM이 runtime에 work stealing을 하게 만드는 구조를 설명하고, TLX가 이를 위한 API(`tlx.clc_create_context`, `tlx.clc_producer`, `tlx.clc_consumer`)를 제공한다고 정리합니다.[^21]

이 영역은 “Triton의 생산성”만으로는 접근이 어렵고, CUDA로 가면 생산성을 잃기 쉬운데, TLX는 그 가운데를 노립니다.

## 정리: TLX는 커널을 더 어렵게 만드는 도구가 아니라, 최적화를 계약으로 바꾸는 도구다

TLX를 도입하면 커널은 분명 더 저수준이 됩니다. 하지만 그 저수준화가 곧바로 생산성 손실로 이어지지는 않습니다. 오히려 TLX의 포인트는, 최신 GPU 최적화에서 핵심이 된 오케스트레이션을 컴파일러의 추측이 아니라 코드의 계약으로 끌어올리는 데 있습니다.[^1]

그래서 TLX를 실전에 들이려면, 커널 튜닝 자체보다 먼저 해야 할 일이 있습니다.

- 저수준 제어 포인트를 “필요한 만큼만” 쓰는 점진 도입
- correctness/벤치/프로파일링을 고정하는 계약 설계
- 회귀를 사람이 감으로 막는 게 아니라 harness로 막는 운영

이 3가지를 먼저 세우면, TLX는 한 번의 튜닝 이벤트가 아니라 지속 가능한 최적화 루프로 들어옵니다.

## 참고 자료

- [How We Built TLX: A Hardware-Native GPU Compiler for Production ML at Scale](https://engineering.fb.com/2026/11/10/open-source/tlx-a-hardware-native-gpu-compiler-for-production-ml/)
- [TLX: Hardware-Native, Evolvable MIMW GPU Compiler for Large-scale Production Environments (arXiv:2605.10905)](https://arxiv.org/abs/2605.10905)
- [fbtriton README (AutoWS / TorchTLX / TLX, uTLX 설치)](https://github.com/facebookexperimental/triton/blob/main/README.md)
- [TLX 문서: Overview](https://facebookexperimental.github.io/triton/website/tlx.html)
- [TLX 문서: Memory (local_alloc, TMEM, reuse)](https://facebookexperimental.github.io/triton/website/buffers.html)
- [TLX 문서: Async memory access (descriptor/TMA 포함)](https://facebookexperimental.github.io/triton/website/async-memory.html)
- [TLX 문서: Tensor core operations (async_dot/async_dot_wait)](https://facebookexperimental.github.io/triton/website/async-compute.html)
- [TLX 문서: Synchronization (alloc_barriers, barrier_wait, fence)](https://facebookexperimental.github.io/triton/website/synchronization.html)
- [TLX 문서: Warp specialization (async_tasks/async_task)](https://facebookexperimental.github.io/triton/website/warp-specialization.html)
- [TLX 문서: Clusters and Cluster Launch Control (ctas_per_cga, CLC)](https://facebookexperimental.github.io/triton/website/clusters.html)
- [TLX 튜토리얼: Pipelined GEMM on Hopper (소스)](https://github.com/facebookexperimental/triton/blob/main/third_party/tlx/tutorials/hopper_gemm_pipelined.py)
- [Triton Plugin Extensions: Enabling TLX and Custom Compiler Passes Out of the Box](https://pytorch.org/blog/triton-plugin-extensions-enabling-tlx-and-custom-compiler-passes-out-of-the-box/)
- [Enabling Cluster Launch Control with TLX](https://pytorch.org/blog/enabling-cluster-launch-control-with-tlx/)
- [TLX Agent 문서](https://facebookexperimental.github.io/triton/website/tlx-agent.html)
- [triton.testing.do_bench 문서](https://triton-lang.org/main/python-api/generated/triton.testing.do_bench.html)
- [PyTorch CUDA semantics (비동기 실행과 이벤트 타이밍)](https://docs.pytorch.org/docs/2.15/notes/cuda.html)
- [Nsight Compute Profiling Guide (Roofline Charts)](https://docs.nvidia.com/nsight-compute/ProfilingGuide/)
- [CUDA C++ Best Practices Guide (동기화와 측정 관련)](https://docs.nvidia.com/cuda/archive/13.4.3/pdf/CUDA_C_Best_Practices_Guide.pdf)
- [Blackwell 이후의 판이 바뀐다: AI 반도체(GPU/NPU) 뉴스로 읽는 공급망·개발자 전략](https://daewooki.github.io/posts/blackwell-2026-6-ai-gpunpu-1/)
- [GPU가 병목인 LLM 서빙, Kubernetes에서 “제대로” 오토스케일링하는 법](https://daewooki.github.io/posts/gpu-llm-kubernetes-2026-6-2/)

[^1]: <https://engineering.fb.com/2026/11/10/open-source/tlx-a-hardware-native-gpu-compiler-for-production-ml/>
[^2]: <https://arxiv.org/abs/2605.10905>
[^3]: <https://facebookexperimental.github.io/triton/website/tlx.html>
[^4]: <https://facebookexperimental.github.io/triton/website/buffers.html>
[^5]: <https://pytorch.org/blog/triton-plugin-extensions-enabling-tlx-and-custom-compiler-passes-out-of-the-box/>
[^6]: <https://facebookexperimental.github.io/triton/website/async-memory.html>
[^7]: <https://facebookexperimental.github.io/triton/website/async-compute.html>
[^8]: <https://facebookexperimental.github.io/triton/website/synchronization.html>
[^9]: <https://facebookexperimental.github.io/triton/website/warp-specialization.html>
[^10]: <https://facebookexperimental.github.io/triton/website/compiler.html>
[^11]: <https://github.com/facebookexperimental/triton/blob/main/README.md>
[^12]: <https://facebookexperimental.github.io/triton/website/torchtlx.html>
[^13]: <https://github.com/facebookexperimental/triton/blob/main/third_party/tlx/tutorials/hopper_gemm_pipelined.py>
[^14]: <https://triton-lang.org/main/python-api/generated/triton.testing.do_bench.html>
[^15]: <https://docs.pytorch.org/docs/2.15/notes/cuda.html>
[^16]: <https://docs.nvidia.com/cuda/archive/13.4.3/pdf/CUDA_C_Best_Practices_Guide.pdf>
[^17]: <https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html?highlight=instance>
[^18]: <https://docs.nvidia.com/nsight-compute/ProfilingGuide/>
[^19]: <https://facebookexperimental.github.io/triton/website/tlx-agent.html>
[^20]: <https://facebookexperimental.github.io/triton/website/clusters.html>
[^21]: <https://pytorch.org/blog/enabling-cluster-launch-control-with-tlx/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
