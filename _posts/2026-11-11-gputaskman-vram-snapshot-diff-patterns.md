---
title: "gputaskman으로 프로세스 단위 VRAM 누수를 재현 가능하게 만들기"
description: "스냅샷(JSON)→diff→원인 프로세스 식별→지표화까지, LLM·그래픽 혼합 머신에서 VRAM 사용처를 고정하는 패턴을 정리합니다."
date: 2026-11-11 11:01:11 +0900
categories: ["Hardware", "GPU"]
tags: ["gputaskman", "vram-observability", "llm-serving", "windows-wddm", "kv-cache"]
render_with_liquid: false
---

## gputaskman이 필요한 순간: VRAM이 찼는데 범인이 안 보일 때

LLM 추론/서빙과 그래픽 워크로드가 한 머신에서 공존하면, VRAM 문제는 대개 다음 형태로 나타납니다.

- 추론 서버를 내렸는데도 VRAM이 줄지 않습니다.
- 브라우저 탭 몇 개 열었을 뿐인데 Dedicated GPU memory가 튀어 오릅니다.
- WSL에서 돌린 학습/추론이 끝났는데도 Windows 쪽 VRAM이 남습니다.
- 게임(또는 렌더러)을 켰더니 LLM이 갑자기 느려지고, system RAM 쪽으로 GPU 메모리가 흘러간 흔적이 보입니다.

이런 상황에서 대부분의 도구가 해주는 일은 “GPU memory total used” 같은 합계 숫자를 보여주는 것뿐입니다. 합계는 원인을 재현하는 데 거의 도움이 되지 않습니다. 원인을 재현하려면 최소한 아래 두 가지가 필요합니다.

1) **프로세스 단위로** VRAM을 계측할 수 있어야 합니다.
2) 그 계측을 “지금 이 순간의 화면”이 아니라 “비교 가능한 시점의 기록”으로 남겨야 합니다.

gputaskman은 그 두 축을 처음부터 제품 형태로 잡고 들어간 도구입니다. README의 첫 문제의식이 “Task Manager says 15 GB used. This tries to answer: by what? Model weights? KV cache? Your browser? The desktop compositor?”로 시작합니다.[^1]

그리고 릴리스 속도가 비정상적으로 빠릅니다. GitHub Releases 기준으로 v0.1.0과 v0.2.0, v0.3.0이 2026-11-03 하루에 연달아 올라왔고, v0.3.1~v0.3.3이 2026-11-07, v0.3.4가 2026-11-09, v0.3.5가 2026-11-10에 배포되었습니다.[^2]

동시에 매체/커뮤니티로 확산되는 속도도 빠릅니다. Windows Central은 이 도구가 “GPU memory가 어디로 갔는지”를 더 잘 설명하기 위해 만들어졌고, AI 모델/브라우저/데스크톱 렌더링 등 범주를 구분해 보여준다고 요약합니다.[^3] Tom’s Hardware는 2026-11-03에 공개(트윗 언급 포함)된 흐름 자체를 기사로 다뤘습니다.[^4]

문제는 도구를 “깔아보면 된다”에서 끝내면, 결국 다시 합계 그래프만 보게 된다는 점입니다. 이 글에서 목표로 잡는 것은 gputaskman을 단발성 UI가 아니라, VRAM 문제를 재현 가능하게 만드는 디버깅 루프로 쓰는 것입니다.

## 숫자의 출처부터 고정: Windows에서 VRAM은 어떻게 프로세스에 귀속되는가

혼합 워크로드 머신에서 VRAM을 추적할 때, 가장 먼저 부딪히는 장애물은 숫자의 정의가 휘청거린다는 점입니다.

Windows에서 특히 그렇습니다. WDDM 환경에서는 GPU 메모리를 OS가 적극적으로 관리합니다. 그래서 같은 GPU에서도 NVML이 프로세스별 메모리를 `N/A`로 내놓는 경우가 생깁니다. gputaskman README가 “GeForce under WDDM에서는 NVML이 per-process memory를 `N/A`로 보고할 수 있고, 대신 Windows GPU counters가 Direct3D/Vulkan/OpenGL/CUDA 전반에 대해 프로세스별로 memory와 activity를 귀속한다”고 적어둔 이유가 여기에 있습니다.[^1]

여기서 더 까다로운 부분이 Desktop Window Manager입니다.

Windows의 per-process `Dedicated Usage`는 프로세스 간 공유 리소스까지 포함해서 잡히고, 동일 surface가 앱 프로세스, `csrss.exe`, `dwm.exe`에 중복 집계될 수 있습니다. 그래서 단순히 `Dedicated Usage` 행을 더하면 “합계가 실제 adapter total을 넘는” 상황이 빈번하게 발생합니다. gputaskman은 이 문제를 명시하고, 가능한 경우 `Local Usage`와 `Non Local Usage`를 우선하고, 그게 안 될 때만 `Dedicated Usage`/`Shared Usage`로 fallback한다고 설명합니다.[^1]

이게 중요해지는 이유는 간단합니다.

- VRAM “누수처럼 보이는 것”의 상당수가 사실은 double counting이거나, OS/드라이버의 공유 메모리 회계 방식 때문입니다.
- 반대로, 진짜로 특정 프로세스가 local memory를 계속 쥐고 있으면 `Local Usage`가 꾸준히 올라가거나 내려오지 않는 패턴이 남습니다.

gputaskman을 쓰기 전에 “어떤 카운터를 기준으로 leak을 말할 것인가”를 정해야 하고, gputaskman이 그 기준을 코드에 박아놓은 쪽에 가깝습니다.

Spill과 Paged 같은 열도 정의를 정확히 잡아야 합니다.

- gputaskman에서 Spill은 GPU-accessible system RAM(GTT 같은 영역)을 의미하며, overflow가 증명된다는 뜻이 아닙니다.[^1]
- Paged는 “eviction trace”가 아니라 커밋 수치에서 local/non-local을 빼서 추정하는 값이며, 입력 카운터가 불완전하면 신뢰도가 내려갑니다.[^1]

이 정도를 전제로 깔지 않으면, 스냅샷을 뜨고 diff를 해도 “이 숫자가 의미하는 게 뭐였지?”에서 다시 멈춥니다.

## LLM 관점에서 VRAM이 커지는 이유: weights와 KV cache를 분리해서 봐야 한다

LLM 워크로드는 VRAM을 쓰는 방식이 그래픽과 다릅니다. 그래픽은 프레임/리소스 단위로 자주 교체되고, 캐싱이 일어나도 작업 단위가 비교적 분명한 편입니다. LLM은 아래 두 덩어리가 압도적으로 큽니다.

- weights
- KV cache

NVIDIA는 LLM inference 최적화 글에서 “두 main contributor는 weights와 KV cache”라고 못 박고, KV cache 크기 계산식을 따로 제시합니다.[^5]

KV cache는 본질적으로 sequence length에 선형으로 늘어납니다. 컨텍스트를 늘리면 요청이 한 번만 들어와도 서버 프로세스가 잡아놓는 VRAM이 확 커질 수 있습니다. 내가 예전에 정리했던 KV cache/quantization 이야기는 그 자체로 최적화 주제이고, 이 글에서는 “관측/회계”에만 초점을 두기 때문에 디테일은 아래 글로 넘기는 편이 낫습니다.

- [FP8 KV-Cache부터 NVFP4까지: GPU LLM 서빙 최적화(quantization + 추론 가속) 실전 가이드](https://daewooki.github.io/posts/fp8-kv-cache-nvfp4-2026-4-gpu-llm-quanti-2/)
- [LoRA/QLoRA 파인튜닝: VRAM 한계를 설계로 이기는 실전 튜토리얼](https://daewooki.github.io/posts/2026-4-loraqlora-vram-1/)

여기서 필요한 결론은 하나입니다.

- “VRAM이 늘었다”는 사실만으로는 leak인지 정상인지 판별이 안 됩니다.
- 최소한 “weights가 늘었는지, KV cache가 늘었는지, 다른 프로세스가 늘었는지”로 쪼개져야 합니다.

gputaskman은 이 분해를 “GPU 메모리를 스캔해서 찾는 방식”이 아니라, WDDM/NVML/DRM 카운터 + 프로세스가 매핑한 파일/로드 로그/로컬 API 같은 근거를 결합하는 쪽으로 설계했습니다.[^1]

또 한 가지가 더 있습니다. KV cache는 생각보다 단순히 계산한 예상치와 실제 증가량이 다를 수 있습니다.

README에는 RTX 4080 SUPER에서 Docker Model Runner의 llama-server(Vulkan)와 gemma-3-270m 조합으로 `-c 4096`에서 `-c 32768`로 바꿨을 때 KV cache가 +504MB로 추정되지만, 측정된 dedicated memory 증가는 +83MB였고, gemma 3의 sliding-window attention 때문에 추정치가 upper bound가 된다고 적혀 있습니다.[^1]

즉, LLM 워크로드에서 VRAM을 디버깅할 때는 “추정치”와 “계측치”가 둘 다 필요합니다. 그래야 실제로는 컨텍스트를 늘렸는데도 VRAM이 덜 늘어나는 이유(모델 아키텍처, attention 방식, runtime 구현)를 설명할 수 있고, 반대로 “추정치보다 훨씬 더 늘었다” 같은 이상 신호도 잡힙니다.

## 설치/실행 경로를 두 갈래로 나누기: portable exe와 source run

gputaskman은 실행 경로가 두 종류입니다.

- portable 빌드(Windows는 ZIP 안에 `gputaskman.exe`)
- Python/uv로 소스에서 실행

현장에서 내가 선호하는 건 portable 빌드입니다. “관측 도구”는 대상 머신의 Python 환경을 더럽히지 않는 쪽이 운영적으로 편합니다.

README는 Releases 페이지에서 Windows x64/ARM64용 portable ZIP을 제공하고, `_internal` 폴더를 옆에 둔 채 `gputaskman.exe`를 실행하라고 적어둡니다. 또 현재 배포는 unsigned이고, ZIP 옆에 `.zip.sha256` 체크섬 파일을 함께 올린다고 되어 있습니다.[^1]

Chocolatey에도 패키지가 올라와 있습니다. 0.3.5가 2026-11-10에 업데이트되었고, 작성자는 Scott Hanselman으로 표기되어 있으며, 패키지 검증 안내에서 GitHub Releases의 ZIP과 `.sha256`를 참조하도록 연결돼 있습니다.[^6]

릴리스가 빠르게 돌고 있는 초반에는, 실행 경로를 다음처럼 정리해두는 게 사고를 줄입니다.

- 팀/운영 머신: GitHub Releases에서 받은 portable + sha256 검증
- 개발/기여 목적: uv/pip로 소스 실행

## 스냅샷(JSON) → diff: leak을 재현 가능한 사건으로 바꾸는 루프

VRAM 문제를 “한 번 봤다”에서 “다시 만들 수 있다”로 바꾸려면, 재현 단위를 명확하게 잘라야 합니다.

내가 쓰는 기본 단위는 이렇습니다.

- before: 모델 로드 직후, 혹은 정상 상태
- stimulus: 한 가지 변화만 주기
  - 컨텍스트 길이 변경
  - 다른 runtime(CUDA↔Vulkan)로 서버 재기동
  - 브라우저에서 WebGPU/Video decode 켜기
  - 게임 실행/종료
- after: 변화가 적용된 뒤, 실제로 한 번 요청/프레임을 태운 후

gputaskman은 이 루프에 맞춘 명령을 이미 Usage 섹션에 넣어놨습니다.

- `--once`: 한 번만 텍스트 스냅샷
- `--json`: 한 번만 JSON 스냅샷(`--once`를 암시)
- `diff before.json after.json`: 두 JSON 스냅샷 비교

README의 예시는 uv 기반이지만, portable exe도 동일한 CLI로 동작하는 형태입니다.

```powershell
# (Windows, portable ZIP을 푼 폴더에서)
.gputaskman.exe --json > before.json

# 여기서 변화(stimulus)를 줍니다.
# 예: LLM 서버를 다른 -c로 재시작하고 요청 1개를 보냄

.gputaskman.exe --json > after.json
.gputaskman.exe diff before.json after.json
# 필요하면 diff에도 --json을 붙여 machine-readable output을 받음
```

`--json` 출력에는 시스템 섹션이 추가되며, 값이 불명확하면 `null`, 샘플링 실패 시 `{"error": "<reason>"}` 같은 형태로 들어간다고 되어 있습니다. 그리고 `gputaskman diff`는 GPU memory만 비교하고 시스템 섹션은 무시한다고 명시돼 있습니다.[^1]

diff가 “진짜로 실전형”인 부분은 프로세스 매칭 규칙입니다.

- 기본은 PID
- PID가 바뀌는 서버 재시작을 고려해 이름/리스닝 포트 등을 추가로 써서 짝을 맞춤
- 한쪽 스냅샷에만 있으면 0이 아니라 `not listed`로 처리
- 작은 변화(16MB 미만)는 텍스트 출력에서 숨기되 JSON에는 포함

이게 왜 중요한지 예를 들면, Ollama나 llama-server를 restart하는 순간 PID가 바뀌는 것은 정상입니다. 그런데 VRAM 문제를 보는 입장에서는 “서버가 잡고 있는 VRAM이 어느 정도로 바뀌었는지”가 핵심이지, PID가 바뀐 사실이 핵심이 아닙니다. gputaskman은 이 현실을 diff 설계에 반영했습니다.[^1]

또 하나. CUDA/Vulkan allocator는 lazy allocation과 caching을 합니다. README도 after 스냅샷을 “요청을 한 번 처리한 뒤” 찍으라고 강조합니다. shrink가 늦게 나타날 수 있기 때문입니다.[^1]

이 루프를 돌리면, 합계 VRAM 그래프에서 절대 얻을 수 없는 결론이 생깁니다.

- 늘어난 주체가 프로세스인지(DWM/브라우저/LLM 서버/게임)
- local memory인지(system RAM 쪽 spill인지)
- 예상된 KV cache 증가와 계측된 증가가 얼마나 다른지

## record(JSONL)로 바꾸면: “밤새 돌린 뒤 아침에 원인 찾기”가 가능해진다

스냅샷→diff는 짧은 실험에는 충분하지만, 운영/개발 머신의 VRAM 문제는 대개 “언제부터인지 모르게” 생깁니다. 이때 필요한 게 record입니다.

gputaskman은 `record` 서브커맨드를 제공합니다. 지정한 interval마다 `--json` 스냅샷을 JSON Lines 형식으로 append-only로 쌓습니다.[^1]

```powershell
# 5분 동안 5초 간격으로 기록
.gputaskman.exe record --gpu 0 --interval 5 --duration 300 -o session.jsonl

# Ctrl+C로 중단할 수도 있음
.gputaskman.exe record -o session.jsonl
```

record의 운영 관점 디테일도 README에 꽤 구체적으로 적혀 있습니다.

- 파일은 append-only
- 각 라인은 완전한 `--json` 스냅샷
- 매 라인을 flush
- GPU가 disable/re-enable되는 구간은 `null`과 이유를 기록하고, 돌아오면 다시 재개

그리고 현실적인 수치가 있습니다. “52 프로세스 스냅샷이 약 27KB”이며 “1초 간격이면 한 시간에 대략 100MB”라고 적어두었습니다. 장시간 기록은 `--interval 5` 이상을 권장합니다.[^1]

JSONL이 쌓이면 “처음 상태 vs 마지막 상태”를 diff할 수 있습니다. README는 PowerShell과 Linux 계열에서 첫 줄/마지막 줄을 뽑아 diff에 넣는 예시를 제공합니다.[^1]

```powershell
Get-Content session.jsonl -TotalCount 1 | Set-Content first.json
Get-Content session.jsonl -Tail 1 | Set-Content last.json
.gputaskman.exe diff first.json last.json
```

이 흐름의 핵심은 “이상 상황이 일어난 타이밍에 터미널을 보고 있지 않아도 된다”입니다.

- 밤새 학습/서빙/게임이 섞여 돌아감
- 아침에 `session.jsonl`을 가지고 last-first diff
- 어떤 프로세스가 어느 bucket을 키웠는지 고정

이게 되면 VRAM 이슈가 티켓으로 올라왔을 때, 재현 장비를 잡고 하루를 태우지 않아도 됩니다.

다만 record 파일에는 경로/커맨드라인/모델 이름/로컬 포트가 들어갈 수 있고, 공유 전에 검토/레닥션이 필요하다고 README가 경고합니다.[^1]

## WSL과 native Linux에서의 계측: 같은 목적, 다른 원천

혼합 워크로드 머신에서 빈번히 등장하는 조합이 Windows host + WSL입니다. 이때 문제가 되는 건 “WSL에서 돈 LLM이 먹은 VRAM이 Windows 쪽에서 어떻게 보이는가”입니다.

gputaskman은 WSL interop이 켜져 있으면, WSL 내부에서 long-lived `powershell.exe`를 하나 띄워 Windows GPU counters를 PDH array API로 읽고, 그 스트림을 초당 한 번 WSL로 넘겨온다고 설명합니다.[^1]

이 구조를 이해하면 WSL에서 겪는 이상 현상(예: Linux 프로세스 행은 `n/a`인데 Windows 쪽 합계는 늘어남)을 “도구 버그”로 오해할 확률이 줄어듭니다. 계측 원천이 Windows host counters이기 때문입니다.

native Linux로 가면 이야기가 달라집니다.

- NVIDIA는 NVML 기반으로 per-process memory를 잡는 경로가 비교적 정석입니다.
- AMD/Intel은 DRM 쪽으로 넘어갑니다.

gputaskman README의 모듈 맵에 Linux DRM 백엔드가 명시돼 있습니다. “AMD and Intel on native Linux: … per-process VRAM/GTT/engine time from DRM fdinfo”라고 적혀 있습니다.[^1]

DRM fdinfo는 최근 몇 년간 “표준화된 메모리 통계”를 드라이버가 출력하도록 진화 중이고, 실제로 amdgpu 쪽 패치에서는 `/proc/<pid>/fdinfo/*`에 `drm-memory-vram`, `drm-memory-gtt`를 찍는 코드가 들어가 있습니다.[^7]

i915 쪽은 fdinfo를 통해 client engine utilization을 노출하는 커밋이 문서로 남아 있고, 예시 출력에 `drm-client-id`와 `drm-engine-*` 항목이 등장합니다.[^8]

즉, Linux에서 “프로세스 단위 GPU 메모리”를 회계하려면 결국 fdinfo 계열로 내려가게 됩니다. NVML처럼 단일 벤더 라이브러리로 퉁치기 어렵고, 드라이버/커널 버전 영향도 큽니다.

여기서 중요한 운영 판단은 이겁니다.

- Windows/WSL 혼합 머신에서 gputaskman은 WDDM 카운터를 기준으로 “프로세스별 VRAM”을 고정한다.
- Linux native에서는 NVML 또는 DRM fdinfo로 “프로세스별 VRAM/GTT”를 고정한다.

둘은 같은 목적을 향하지만, 숫자의 근원이 다릅니다. 그래서 동일한 임계치/알림 규칙을 양쪽에 그대로 이식하면 사고가 납니다.

## 운영 지표화: gputaskman은 디버거, performance counter는 시계열

스냅샷→diff 루프는 원인 규명에 강하지만, 24/7 관측에는 몇 가지 부담이 있습니다.

- record JSONL은 빠르게 커집니다(README의 100MB/hour 같은 수치).[^1]
- JSON에는 민감 정보(경로/모델 이름/포트)가 섞일 수 있습니다.[^1]
- 무엇보다 “상시로 gputaskman을 돌려서 해결”하려는 접근은 도구의 본래 철학과도 다릅니다.

내 결론은 이렇습니다.

- 상시는 OS가 제공하는 카운터 기반으로 시계열을 쌓는다.
- 이상 구간이 나오면 그때 gputaskman record/snapshot/diff로 사건을 재현하고 해석한다.

Windows에서는 이미 Prometheus 커뮤니티 쪽에서 GPU 퍼포먼스 카운터를 긁어오는 구현이 있습니다. windows_exporter의 GPU collector 문서는 `GPU Process Memory` 같은 카운터를 포함하고, 메트릭으로 `windows_gpu_process_memory_dedicated_bytes`를 per-process gauge로 노출한다고 적습니다.[^9]

이런 시계열 메트릭이 있으면, 운영적으로는 아래 같은 형태가 가능합니다.

- 전체 VRAM 압박(예: adapter total 대비 local usage 비율)이 일정 시간 지속되면 경고
- 특정 process_id가 dedicated bytes를 특정 임계치 이상으로 오래 유지하면 경고
- “LLM 서버 프로세스”는 정상적으로 큰 값이므로 예외 처리

그리고 진짜로 원인을 붙잡아야 할 때(예: 특정 시간대에 VRAM이 6GB 튀고 다시 안 내려옴), 그 구간만 잘라 gputaskman record를 붙이면 됩니다.

이 방식이 특히 잘 먹히는 케이스가 “LLM/그래픽이 같이 도는 개발 머신”입니다.

- 낮에는 IDE/브라우저/Teams/Zoom이 GPU를 조금씩 씁니다.
- 밤에는 로컬 LLM이 돌아갑니다.
- 중간에 게임을 켜거나, 영상 인코딩이 섞입니다.

이런 환경에서 진짜로 필요한 것은 “정밀한 원인 규명 1회”와 “상시 탐지”의 조합이지, 정밀 도구를 상시로 돌리는 게 아닙니다.

## 함정과 트레이드오프: 누수처럼 보이는 것들의 정체

### DWM이 VRAM을 다 먹는 것처럼 보이는 현상

앞서 말했듯이 Windows의 `Dedicated Usage`는 공유 리소스 때문에 중복 집계가 발생할 수 있습니다. gputaskman이 `Local Usage`/`Non Local Usage` 선호 전략을 취한 이유가 바로 이것입니다.[^1]

따라서 DWM이 크다고 해서 바로 “DWM leak”으로 몰고 가면 안 됩니다. 먼저 어떤 카운터를 보고 있는지부터 확인해야 합니다.

### Spill은 overflow 증명이 아니다

Spill은 GPU-accessible system RAM일 수 있고, intentionally allocated/pinned host buffer일 수 있습니다. VRAM이 꽉 찬 상황에서 함께 커지면 성능 저하의 간접 신호일 수 있지만, 그 자체로 원인 증명이 되지 않습니다.[^1]

LLM 쪽에서는 특히 “host에 pinned buffer를 잡는 것이 정상인 runtime”이 존재합니다. spill을 leak으로 단정하면 대응이 틀어집니다.

### allocator caching vs leak

CUDA/Vulkan allocator는 freed memory를 캐시에 잡아둘 수 있습니다. 그래서 요청이 끝났는데도 VRAM이 바로 내려오지 않는 것이 정상일 때가 있습니다. README가 after 스냅샷 타이밍을 신경 쓰라고 적은 것도 같은 맥락입니다.[^1]

여기서 내가 쓰는 판단 기준은 단순합니다.

- 동일한 stimulus를 여러 번 반복했을 때, 특정 프로세스의 local usage가 계단형으로 누적된다면 leak 가능성이 커집니다.
- stimulus 없이 idle인데도 local usage가 단조 증가한다면, 그때는 거의 leak로 봅니다.

그리고 그 결론을 재현 가능하게 만드는 장치가 snapshot→diff입니다.

### gputaskman이 해주지 않는 것

gputaskman README는 “어떤 texture/tensor/kernel인가” 수준은 이 도구의 범위가 아니고, PIX/Nsight 같은 툴을 쓰라고 선을 긋습니다.[^1]

즉, gputaskman은 “범인 프로세스”와 “메모리 bucket 변화”를 고정하는 도구이고, 프로세스 내부에서 어떤 할당이 남았는지까지 파고드는 도구는 아닙니다.

## 도입 판단: 혼합 워크로드 머신에서의 최적 사용 위치

gputaskman은 실험실 도구라기보다, 혼합 워크로드가 일상인 머신에서 VRAM 문제를 사건화하는 데 강합니다. 특히 다음 조건이 맞으면 효과가 큽니다.

- Windows WDDM 환경에서 `nvidia-smi`가 per-process VRAM을 제대로 못 보여준다.[^1]
- DWM/브라우저/LLM이 얽혀서 double counting과 진짜 증가를 구분해야 한다.[^1]
- 컨텍스트 길이 변경, 모델 교체 같은 실험을 before/after로 자르고, KV cache 추정과 계측치의 간극까지 같이 봐야 한다.[^1]
- 밤새 돌린 뒤 아침에 원인을 찾아야 해서 append-only record(JSONL)가 필요하다.[^1]

다만 이 도구 하나로 “상시 관측”까지 끝내려는 욕심은 버리는 편이 낫습니다. 상시는 performance counter 기반 메트릭(예: windows_exporter GPU collector)로 시계열을 만들고, 이상 구간을 특정한 뒤 gputaskman snapshot/record/diff로 원인을 고정하는 편이 운영 비용이 낮습니다.[^9]

결국 gputaskman의 가치가 가장 크게 나오는 지점은, VRAM 문제를 재현 가능한 diff로 바꿔서 원인 프로세스를 고정해주는 순간입니다.

## 참고 자료

- [gputaskman GitHub 저장소](https://github.com/shanselman/gputaskman)
- [gputaskman Releases](https://github.com/shanselman/gputaskman/releases)
- [Chocolatey의 gputaskman 패키지 페이지](https://community.chocolatey.org/packages/gputaskman)
- [Windows Central 기사: GPU memory 사용처를 설명하는 무료 앱(gputaskman)](https://www.windowscentral.com/hardware/gpus/this-free-app-explains-where-your-gpu-memory-actually-goes-and-it-comes-from-a-microsoft-engineer)
- [windows_exporter GPU collector 문서](https://github.com/prometheus-community/windows_exporter/blob/main/docs/collector.gpu.md)
- [NVIDIA Technical Blog: Inference Optimization에서 weights/KV cache 언급](https://developer.nvidia.com/blog/mastering-llm-techniques-inference-optimization)
- [Linux kernel 문서: AMDGPU driver](https://www.kernel.org/doc/html/v5.14/gpu/amdgpu.html)
- [Linux kernel 문서: DRM Memory Management](https://dri.freedesktop.org/docs/drm/gpu/drm-mm.html)
- [linux-kernel 메일링리스트 패치: amdgpu fdinfo에 drm-memory-vram/gtt 출력](https://lists.openwall.net/linux-kernel/2023/05/24/1137)
- [i915 fdinfo engine utilization 커밋(예시 출력 포함)](https://git.zx2c4.com/wireguard-linux/commit/Documentation/gpu?id=055634e4b62f109a47727c2c50586e2e318595a9)
- [Tom’s Hardware 기사: gputaskman 확산 맥락](https://www.tomshardware.com/pc-components/gpus/open-source-gpu-task-manager-reveals-exactly-whats-eating-your-vram-microsoft-vps-new-gpu-taskman-tool-reveals-every-process-using-your-gpu-how-much-memory-each-uses-and-breaks-down-ai-and-llm-workloads)
- [BetaNews 기사: README에서 early/experimental 언급](https://betanews.com/article/gpu-memory-monitoring-tool/)
- [FP8 KV-Cache부터 NVFP4까지: GPU LLM 서빙 최적화(quantization + 추론 가속) 실전 가이드](https://daewooki.github.io/posts/fp8-kv-cache-nvfp4-2026-4-gpu-llm-quanti-2/)
- [GPU가 병목인 LLM 서빙, Kubernetes에서 오토스케일링하는 법](https://daewooki.github.io/posts/gpu-llm-kubernetes-2026-6-2/)

[^1]: <https://github.com/shanselman/gputaskman>
[^2]: <https://github.com/shanselman/gputaskman/releases>
[^3]: <https://www.windowscentral.com/hardware/gpus/this-free-app-explains-where-your-gpu-memory-actually-goes-and-it-comes-from-a-microsoft-engineer>
[^4]: <https://www.tomshardware.com/pc-components/gpus/open-source-gpu-task-manager-reveals-exactly-whats-eating-your-vram-microsoft-vps-new-gpu-taskman-tool-reveals-every-process-using-your-gpu-how-much-memory-each-uses-and-breaks-down-ai-and-llm-workloads>
[^5]: <https://developer.nvidia.com/blog/mastering-llm-techniques-inference-optimization>
[^6]: <https://community.chocolatey.org/packages/gputaskman>
[^7]: <https://lists.openwall.net/linux-kernel/2023/05/24/1137>
[^8]: <https://git.zx2c4.com/wireguard-linux/commit/Documentation/gpu?id=055634e4b62f109a47727c2c50586e2e318595a9>
[^9]: <https://github.com/prometheus-community/windows_exporter/blob/main/docs/collector.gpu.md>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
