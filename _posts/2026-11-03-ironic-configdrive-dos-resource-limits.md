---
title: "OpenStack Ironic configdrive gzip bomb DoS를 막는 운영 패턴"
description: "configdrive/메타데이터를 파일이 아니라 리소스로 보고, 해제 한도·입력 검증·Conductor 격리로 DoS를 줄이는 운영 설계."
date: 2026-11-03 11:40:27 +0900
categories: ["Cloud", "OpenStack"]
tags: ["openstack", "ironic", "security", "dos", "configdrive", "operations"]
render_with_liquid: false
---

## OSSA-2026-049이 말해주는 것: configdrive는 곧 리소스 청구서입니다

2026년 10월 29일(미국 태평양 시간 기준, oss-sec 메일 본문 시각 표기) OpenStack Security Advisory **OSSA-2026-049**가 공개됐습니다. Ironic Conductor가 `/v1/nodes/provision_state`(문서/구현에 따라 `/v1/nodes/{node_ident}/states/provision`로도 표기)로 제출되는 base64-encoded, gzipped configdrive를 추출하는 과정에서 **OOM(out of memory)** 또는 **disk full** 상태로 떨어질 수 있다는 내용이고, CVE는 [CVE-2026-115638](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2026-115638)로 트래킹됩니다.[^1]

핵심은 gzip bomb 자체가 새롭지 않다는 점이 아닙니다. 이번 케이스가 운영 조직에 주는 신호는 명확합니다.

- configdrive/메타데이터는 기능적으로는 “편의 파일”이지만, 보안/운영 관점에서는 **테넌트 입력이 리소스를 무제한으로 소비하게 만드는 트리거**입니다.
- 문제가 발생하는 위치가 “인스턴스 내부(cloud-init)”가 아니라 “컨트롤 플레인(Conductor)”이라는 점이 치명적입니다. Conductor가 뻗으면 bare metal 프로비저닝 전체가 멈춥니다.
- Advisory 본문도 “Ironic을 직접 호출해 배포 가능한 사용자(테넌트)가 있는 환경”을 직접적으로 지목합니다. 즉, 멀티테넌트 운영 조직이라면 이건 기능 버그가 아니라 운영 리스크입니다.[^1]

오늘이 2026-11-03(KST)라면, 공개(2026-10-29) 이후 5일이 채 지나지 않은 시점입니다. 이 정도 타이밍이면 패치 적용과 별개로 런북에 리소스 한도 패턴을 넣기 좋은 계기입니다.

## configdrive가 흐르는 경로: “작아 보이는 입력”이 어디서 터지나

Ironic standalone 배포 기준으로 configdrive는 보통 두 형태로 들어옵니다.

1) **클라이언트가 ISO9660 configdrive를 만들어 gzip + base64로 제출**
2) **클라이언트가 JSON(meta_data/user_data/network_data/vendor_data)을 제출하고, Ironic이 서버 사이드에서 configdrive를 생성**

Ironic 문서는 “Bare Metal service expects a `gzipped` and `base64` encoded ISO 9660 file with a `config-2` label”이라고 명시합니다. 또한 최신 python-ironicclient에서는 JSON을 주면 서버 사이드 빌드를 할 수 있다고 안내합니다.[^2]

문제는 (1)에서 특히 두드러집니다. gzip bomb는 ‘압축된 입력 크기’가 아니라 ‘**해제 이후의 출력 크기**’로 리소스를 때리기 때문입니다.

이 입력이 Conductor까지 도달하면서, 대체로 다음 비용을 연쇄적으로 발생시킵니다.

- API 레이어: HTTP request body 수신(메모리/버퍼)
- 인증/정책: 요청 처리 비용
- RPC/내부 큐: (구성에 따라) 메시지 페이로드 증가
- Conductor: base64 decode → gzip decompress → 임시 파일 쓰기 → ISO 파일 파싱/수정(재생성)

특히 OSSA-2026-049에서 말하는 “extract a base64-encoded, gzipped configdrive image”는 구현 상 대충 이런 형태의 코드로 연결됩니다. Ironic의 `check_and_patch_configdrive()`는 configdrive를 `gzip.decompress(base64.b64decode(configdrive))`로 한 번에 풀어서 temp file에 씁니다. 이 패턴은 gzip bomb에 정면으로 취약합니다.[^3]

그리고 이 로직은 “모든 배포에서 항상” 호출되는 게 아니라, 릴리스 노트 기준으로는 다음 조건에서 특히 문제가 됐다고 정리돼 있습니다.

- Anaconda deploy interface
- `redfish-virtual-media` boot interface
- Ironic이 network metadata(network_data.json)를 업데이트/검증하는 배포 흐름

릴리스 노트는 “Ironic updates network metadata (network_data.json)”를 명시적으로 언급합니다. 즉, “configdrive 내용을 들여다보고 고쳐주는 편의 기능”이 DoS surface를 넓힐 수 있습니다.[^4]

또 하나의 운영 포인트는 configdrive 저장 경로입니다. 오래된 문서이긴 하지만 Ironic은 configdrive를 Swift(object store)에 저장하는 옵션을 지원하며, 64KB보다 큰 configdrive는 object store를 쓰는 시나리오를 설명합니다. 저장을 Swift로 넘겨도 “추출 과정”은 Conductor에서 일어날 수 있고, bomb가 disk full을 유발하면 Swift 여부와 상관없이 Conductor 호스트의 로컬 디스크가 먼저 죽을 수 있습니다.[^5]

## 패치가 해결한 것: “출력 64MiB”를 운영 경계로 고정하기

OpenStack Ironic 2026.1 릴리스 노트(시리즈 릴리스 노트의 security issue 섹션)는 이번 문제의 수정 방향을 꽤 명확히 적어두고 있습니다.

- “bounded chunks로 decompress한다”
- “**64MiB를 초과하도록 expand되는 configdrive는 reject한다**”
- 64MiB는 “Ironic Python Agent가 강제하는 동일한 제한이며, partition 크기와도 맞는다”

이 문장 하나가 운영자에게는 굉장히 큽니다. “입력 크기 제한”이 아니라 “**출력 크기 제한**”이 들어갔기 때문입니다.[^4]

여기서 64MiB가 왜 자연스러운지 근거도 같이 맞춰볼 수 있습니다.

- Ironic Python Agent 쪽에는 `MAX_CONFIG_DRIVE_SIZE_MB = 64` 상수가 존재합니다.[^6]
- ironic-lib의 disk_utils에서도 configdrive 최대 크기를 64MiB로 강제하며, 초과 시 `InstanceDeployFailure`를 던지는 코드가 보입니다.[^7]
- 문서에서도 configdrive는 “maximum size of 64MB”라고 반복해서 언급됩니다.[^5]

즉, 이번 패치는 “원래 존재하던 64MiB 경계(에이전트/파티션/문서)”를 Conductor의 decompress 단계로 끌어올려서, 컨트롤 플레인을 방어한 셈입니다.

다만 운영 패턴 관점에서는 여기서 끝내면 부족합니다.

- 패치는 “configdrive gzip bomb”라는 특정 class를 막습니다.
- 그러나 운영자가 실제로 지켜야 하는 것은 “특정 CVE”가 아니라 “테넌트 입력이 리소스를 무한히 쓰지 못하게 만드는 시스템”입니다.

같은 릴리스 노트 안에 “oversized / deeply nested JSON이 RecursionError로 API worker를 크래시시킬 수 있어서, JSON body size/depth를 제한하는 미들웨어와 설정이 추가됐다”는 내용이 같이 들어가 있습니다. configdrive만의 문제가 아니라, 입력을 리소스 공격으로 바라보는 방향이 이미 프로젝트 전체로 확장되는 흐름입니다.[^4]

## 운영 패턴 1: 압축 해제 한도(크기/시간)를 파이프라인에 겹겹이 넣기

패치(업그레이드)는 당연히 최우선입니다. 하지만 운영 런북에 남겨야 하는 건 “업그레이드했다”가 아니라 “업그레이드 실패/지연/회귀가 있어도 컨트롤 플레인이 버틴다”입니다.

여기서는 “크기”와 “시간” 두 축을 동시에 잡는 패턴을 씁니다.

### API/Proxy 레벨에서 1차 차단: request body는 읽기 전에 자릅니다

Ironic은 `[api]max_json_body_size_provision` 같은 별도 제한을 둡니다. 샘플 설정은 “node provision state endpoint는 configdrive data를 실을 수 있으니 기본 64MiB(65536 KiB)”라고 설명합니다.[^8]

이 값은 “gzip bomb”를 막기엔 부족합니다. bomb는 작은 입력이 큰 출력으로 바뀌기 때문입니다. 그럼에도 이 값이 중요한 이유는 다음입니다.

- 최소한 **아주 큰 입력(base64 자체가 거대)** 을 Conductor로 전달하기 전에 API에서 잘라낼 수 있습니다.
- deploy steps 등 다른 필드로 payload가 커지는 경우도 관리 가능합니다.

추가로, Ironic 앞단에 NGINX 같은 reverse proxy를 두고 있다면 `client_max_body_size`는 반드시 맞춰둡니다. 이건 아주 고전적인 방어인데, “일단 받아놓고 413 주기”가 아니라 “Content-Length가 크면 읽기 전에 413”로 끝내는 방향으로 시스템이 움직이기 때문입니다. NGINX 공식 문서는 `client_max_body_size`가 요청 바디 최대 크기를 제한하고 초과 시 413을 반환한다고 설명합니다.[^9]

정리하면 이렇게 가져갑니다.

- (권장) Ironic `[api]max_json_body_size_provision`을 운영 요구에 맞게 낮추거나(필요하면) 유지
- (필수) Proxy `client_max_body_size`로 더 앞단에서 1차 컷

여기서 중요한 운영 원칙은 “Ironic 설정이 있으니 proxy는 안 해도 된다”가 아니라, “둘 다 한다”입니다. OpenStack 운영에서 장애는 대개 단일 방어선이 깨졌을 때가 아니라, 단일 방어선에만 의존했을 때 커집니다.

### decompress 단계에서 2차 차단: 출력 바이트와 시간 예산을 동시에 강제합니다

이번 OSSA의 본질은 “decode+decompress가 무제한”이었다는 점입니다. Conductor에서 base64 decode 후 gzip decompress를 할 때 다음 두 가지를 반드시 강제해야 합니다.

- **출력(해제 결과) 최대 크기**
- **해제 작업 시간 제한(대략적인 CPU 예산)**

Ironic은 패치를 통해 “bounded chunks + 64MiB 초과 시 reject”로 이 방향을 채택했습니다.[^4]

운영자 관점에서 이 패턴을 내부 런북/사내 가이드로 일반화하면 다음처럼 정리됩니다.

- gzip/zip/tar 같은 압축 포맷은 “입력 크기 제한”과 “출력 크기 제한”이 별개입니다.
- 출력 크기는 보통 서비스의 **자연스러운 상한**(여기서는 64MiB)을 기준으로 삼습니다.
- 시간 제한은 “정상적인 configdrive는 금방 풀려야 한다”는 경험칙을 코드로 박습니다.

아래는 “운영 도구”로 바로 쓸 수 있는 형태의 Python 스크립트 예시입니다. Ironic에 패치를 넣는 목적이 아니라, 

- 사내 자동화(프로비저닝 파이프라인)
- 운영자가 수동으로 수행하는 deploy
- 배포 전 검증(예: change 승인 전)

같이 “신뢰되는 주체가 요청을 만들 때” configdrive 자체를 미리 안전하게 검증하는 데 유용합니다.

#### 실행 가능한 예제: base64+gzip 스트리밍 해제 가드

- Python 3.11 이상 가정(표준 라이브러리만 사용)
- 입력: base64 string(파일 또는 stdin)
- 검증: gzip 스트리밍 해제 중 출력이 `--max-bytes` 초과하면 실패
- 검증: 해제 시간이 `--timeout-sec` 초과하면 실패

```bash
cat > configdrive_guard.py <<'PY'
#!/usr/bin/env python3
import argparse
import base64
import binascii
import gzip
import io
import sys
import time

DEFAULT_MAX = 64 * 1024 * 1024  # 64MiB

class LimitExceeded(Exception):
    pass

class TimeoutExceeded(Exception):
    pass

def guarded_gzip_decompress(b64_text: str, *, max_bytes: int, timeout_sec: float, chunk_size: int = 1024 * 128) -> bytes:
    start = time.monotonic()

    try:
        raw = base64.b64decode(b64_text, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError(f"invalid base64: {e}")

    # Stream decompress: avoid gzip.decompress(raw) which materializes full output.
    bio = io.BytesIO(raw)
    out = bytearray()

    with gzip.GzipFile(fileobj=bio, mode="rb") as gz:
        while True:
            if time.monotonic() - start > timeout_sec:
                raise TimeoutExceeded(f"decompression timed out after {timeout_sec}s")

            chunk = gz.read(chunk_size)
            if not chunk:
                break

            out.extend(chunk)
            if len(out) > max_bytes:
                raise LimitExceeded(f"decompressed size {len(out)} exceeds limit {max_bytes}")

    return bytes(out)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", "-i", default="-", help="base64 text file path, or '-' for stdin")
    p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX)
    p.add_argument("--timeout-sec", type=float, default=2.0)
    p.add_argument("--chunk-size", type=int, default=1024 * 128)
    args = p.parse_args()

    if args.input == "-":
        b64_text = sys.stdin.read()
    else:
        b64_text = open(args.input, "r", encoding="utf-8").read()

    b64_text = "".join(b64_text.split())  # remove whitespace/newlines

    try:
        out = guarded_gzip_decompress(
            b64_text,
            max_bytes=args.max_bytes,
            timeout_sec=args.timeout_sec,
            chunk_size=args.chunk_size,
        )
    except (ValueError, LimitExceeded, TimeoutExceeded) as e:
        print(f"REJECT: {e}", file=sys.stderr)
        return 2

    print(f"OK: decompressed_bytes={len(out)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
PY

chmod +x configdrive_guard.py
```

이제 gzip bomb의 핵심인 “고압축 데이터(반복 바이트)”로 테스트를 만듭니다. 데모는 시스템에 부담을 주지 않기 위해 2MiB 정도로만 합니다.

```bash
python3 - <<'PY'
import base64, gzip
payload = b'\x00' * (2 * 1024 * 1024)  # 2MiB of zeros compresses very well
b64 = base64.b64encode(gzip.compress(payload)).decode()
open('bomb.b64','w').write(b64)
print('written bomb.b64, base64_len=', len(b64))
PY

# limit to 1MiB => reject
./configdrive_guard.py -i bomb.b64 --max-bytes $((1*1024*1024)) --timeout-sec 1

echo $?

# limit to 4MiB => accept
./configdrive_guard.py -i bomb.b64 --max-bytes $((4*1024*1024)) --timeout-sec 1
```

예상 출력은 대략 이런 형태입니다.

- 제한 1MiB:
  - `REJECT: decompressed size ... exceeds limit ...`
- 제한 4MiB:
  - `OK: decompressed_bytes=2097152`

이 스크립트가 말해주는 운영 포인트는 단순합니다.

- “gzip을 푸는 코드”는 구현이 쉬워 보이지만, **안전한 gzip 해제는 기본값이 아니라 추가 기능**입니다.
- 스트리밍/청킹과 상한을 넣는 것이 방어의 출발점입니다.
- timeout은 완벽한 CPU 제어가 아니라 “최악의 케이스가 무한정 늘어나지 않게” 만드는 브레이크입니다.

### tmpdir/파일시스템을 마지막 방어선으로 만들기: disk full의 blast radius 줄이기

OSSA 본문은 “OOM 또는 disk full”을 같이 언급합니다.[^1]

Ironic의 configdrive patch 로직은 temp file에 decompress 결과를 씁니다. 그리고 그 파일은 `tempfile.NamedTemporaryFile(dir=CONF.tempdir, ...)`처럼 Ironic의 tempdir 아래에 놓입니다.[^3]

이 구조에서는 “출력 크기 제한이 없다면” disk full이 시스템 전체로 번지는 게 너무 쉽습니다.

운영 패턴은 간단합니다.

- Conductor 노드에서 Ironic의 tempdir이 위치한 파일시스템을 **OS 루트와 분리**합니다.
- 그 파일시스템의 크기를 “정상 configdrive 최대치 × 동시 작업 수 + 여유”로 잡고, 그 이상은 애초에 쓸 수 없게 만듭니다.
- 가능하면 이 영역은 컨테이너/VM 격리 또는 별도 mount로 “가득 차도 호스트가 죽지 않게” 합니다.

패치가 들어가도, 운영자는 “리소스 상한을 코드가 지켜준다”에만 기대지 않는 쪽이 안전합니다. 코드 상한이 깨지는 순간(회귀, 설정 실수, 경로 변경)에도 파일시스템 상한이 마지막으로 버티기 때문입니다.

## 운영 패턴 2: 테넌트 입력 검증을 ‘정상 포맷’이 아니라 ‘최대 비용’으로 정의하기

Ironic 문서는 configdrive 입력을 두 가지 스타일로 열어둡니다.

- gzip+base64 ISO9660 그대로 제출
- JSON(meta_data/user_data/network_data/vendor_data)로 제출하고 서버 사이드에서 생성[^2]

운영 관점에서 “입력 검증”을 포맷 검증으로 끝내면, gzip bomb 같은 공격은 항상 남습니다. 포맷은 정상인데 비용이 비정상인 입력이 있기 때문입니다.

그래서 검증 기준을 다음처럼 바꿉니다.

1) **입력 1바이트가 만들 수 있는 출력/작업량의 상한을 제한한다**
2) 상한을 넘는 입력은 “에러”가 아니라 “정책 위반”으로 거부한다
3) 거부는 최대한 앞단(API/Proxy/Ingress)에서 발생시킨다

구체적으로는 다음 체크가 런북에 들어가야 합니다.

- base64 decode 전 단계에서 길이/문자셋(whitespace 제거 포함) 검증
- gzip 해제 시 출력 상한(이번 이슈의 본질)
- ISO9660 파싱 시 파일 엔트리 수/경로 길이/중복 경로 같은 “파서 비용” 상한
- JSON 입력 스타일을 허용한다면, JSON body size뿐 아니라 depth 제한도 함께 적용

Ironic 자체도 이 방향으로 가고 있습니다. 2026.1 릴리스 노트는 깊게 중첩된 JSON이 `json.loads()`에서 `RecursionError`로 worker를 죽일 수 있어, JSON body size/depth 제한 옵션을 넣었다고 설명합니다.[^4]

내 경우라면, 멀티테넌트에서 “테넌트가 Ironic API를 직접 호출할 수 있는” 구조라면 다음을 기본값으로 가져갑니다.

- raw ISO9660 configdrive 제출은 허용하지 않고(또는 극히 제한된 역할에만 허용), 가능하면 JSON 기반 server-side build를 유도
- 그래도 raw ISO 제출을 열어야 한다면, 사내 gateway(얇은 API wrapper)를 두고 “출력 상한/시간 상한/감사 로그”를 강제

이건 기능 제한처럼 보이지만, 실제로는 “컨트롤 플레인 리소스 청구서를 누가 쓸 수 있나”를 재정의하는 작업입니다.

## 운영 패턴 3: Conductor를 보호하는 방법: 격리·쿼터·워커 제한을 ‘리소스 공격’으로 묶기

OSSA-2026-049는 Conductor DoS입니다. 즉, 공격이 성공했을 때 영향 범위는 “해당 노드 배포 실패”가 아니라 “배포 서비스 중단”이 됩니다.[^10]

그래서 Conductor는 애초에 “테넌트 입력을 직접 먹는 서비스”로 취급하면 안 됩니다. 운영 패턴을 세 레벨로 나눠 가져갑니다.

### (1) 격리: 테넌트 입력이 곧장 공유 Conductor를 때리지 않게 만들기

가장 좋은 격리는 “Ironic API 직접 노출을 하지 않는다”입니다. Advisory가 말하는 영향 범위도 결국 “users have access to deploy instances directly via Ironic”인 환경입니다.[^1]

조직 구조상 Ironic API를 테넌트에 직접 열어야 한다면, 적어도 다음 중 하나는 필요합니다.

- Ironic API 앞단에 요청 검증 계층(gateway) 배치
- 테넌트/프로젝트별로 Conductor 풀을 분리(운영 복잡도는 증가하지만 blast radius가 줄어듭니다)

여기서 포인트는 “공격을 막는다”가 아니라 “공격이 성공해도 피해를 분리한다”입니다.

### (2) 프로세스 리소스 상한: systemd/cgroup로 Memory/CPU를 하드 캡

코드에 상한이 들어가도, 리소스 공격 관점에서는 OS 레벨 상한이 마지막 안전장치입니다. 특히 OOM은 한 번 나면 그 순간부터 장애 대응 자체가 어려워집니다.

systemd의 `MemoryHigh=`/`MemoryMax=`/`CPUQuota=` 같은 설정은 Conductor를 cgroup으로 묶어서 리소스 한도를 줄 수 있습니다. `MemoryMax`는 절대 상한이며 초과 시 unit 내부에서 OOM killer가 동작한다고 문서가 명시합니다. `CPUQuota`도 마찬가지로 unit의 CPU 시간 상한을 설정합니다.[^11]

예시는 다음과 같습니다(서비스 이름은 배포판/배포 도구에 따라 다를 수 있어, drop-in 개념만 가져갑니다).

```bash
sudo systemctl edit ironic-conductor.service
```

```ini
# /etc/systemd/system/ironic-conductor.service.d/10-resource-guard.conf
[Service]
# 정상 트래픽 기준으로 튜닝 필요: 여기 숫자는 예시입니다.
MemoryHigh=3G
MemoryMax=4G
CPUQuota=200%

# 프로세스 폭주(스레드/프로세스 생성)도 리소스 공격의 일부로 봅니다.
TasksMax=2048
```

운영 경험상 여기서 흔히 하는 실수는 MemoryMax를 너무 낮게 잡아 “정상 배포도 실패”하게 만드는 것입니다. 그래서 나는 보통 이렇게 잡습니다.

- MemoryHigh: 평상시 상한(스로틀)
- MemoryMax: 최악을 막는 마지막 방어선(좀 더 여유)

이렇게 해야 리소스 공격이 와도 호스트 전체가 죽는 것을 막으면서, 정상 부하에서의 안정성도 챙길 수 있습니다.

### (3) 큐/메시징 상한: RabbitMQ는 ‘큰 메시지’ 자체를 정책으로 막을 수 있습니다

OpenStack 컨트롤 플레인은 메시징 계층(RabbitMQ 등)을 지나가면서 증폭됩니다. “압축 해제 폭탄” 자체는 작은 입력이므로 메시지 크기 제한으로 완전히 막을 수는 없지만, 다음 이유로 여전히 유효한 운영 가드입니다.

- 실수/오작동으로 base64 자체가 과도하게 커진 요청을 차단
- 한 번에 큰 payload를 던져 컨트롤 플레인의 메모리/디스크를 갉아먹는 타입의 장애를 감소

RabbitMQ 문서는 `max_message_size`가 “largest allowed message payload size”이며 초과 메시지는 reject된다고 설명합니다. 최대 허용 값이 512MiB라는 점도 문서에 적혀 있습니다.[^12]

여기서도 원칙은 동일합니다.

- Ironic API에서 제한
- Proxy에서 제한
- 메시징에서 제한
- Conductor 프로세스에서 제한

서로 다른 레이어의 제한이 겹칠수록, 단일 설정 실수로 전체가 무너질 가능성이 줄어듭니다.

## 런북에 바로 옮길 수 있는 체크리스트

여기서는 “OSSA-2026-049 대응”을 넘어, “압축 입력을 리소스 공격으로 다루는” 런북 항목만 남깁니다.

### 1) 업그레이드/패치 적용(최우선)

- OSSA-2026-049 영향 버전 범위를 기준으로, 현재 Ironic이 취약 범위에 있는지 먼저 확인합니다. Advisory는 영향을 받는 범위를 `>=16.2.0 <29.1.1, >=30.0.0 <32.1.1, >=33.0.0 <35.1.1, >=36.0.0 <39.0.1`로 명시합니다.[^1]
- 패치의 핵심 동작(청킹 해제 + 64MiB 초과 reject)이 릴리스 노트에 있는지 확인합니다.[^4]

### 2) 입력 크기 제한을 “API 설정 + Proxy”로 이중화

- Ironic `[api]max_json_body_size_provision` 값 점검(기본 64MiB)[^8]
- 앞단 NGINX(또는 Ingress) `client_max_body_size`로 한 번 더 제한[^9]

### 3) 출력 크기 제한을 “반드시 decompress 단계”에 둔다

- 입력(base64/gzip)의 크기 제한만으로는 gzip bomb 방어가 되지 않습니다.
- 출력 크기 제한의 기준은 “업무적으로 의미 있는 상한”으로 둡니다. Ironic에서는 64MiB가 자연스러운 경계입니다(IPA/partition 제한과 일치).[^4]

### 4) Conductor 호스트를 시스템 단위로 보호

- systemd `MemoryHigh/MemoryMax/CPUQuota`로 컨트롤 플레인 폭주가 호스트 전체로 번지지 않게 합니다.[^11]
- Ironic tempdir이 놓인 파일시스템을 OS 루트에서 분리하고 크기를 제한합니다(코드상 temp file 생성 경로가 `CONF.tempdir` 아래임을 확인).[^3]

### 5) “편의 기능”이 공격면을 넓히는지 점검

- Ironic이 configdrive 내부를 파싱/패치하는 기능(예: network metadata 검증/재생성)은 편리하지만, 그만큼 컨트롤 플레인이 untrusted input을 깊게 처리합니다.
- `disable_configdrive_check` 같은 옵션은 “완화책”이 될 수 있으나, 릴리스 노트가 지적한 것처럼 영향을 받는 경로가 여러 가지이므로(Anaconda, redfish-virtual-media, metadata update) 이것만으로 충분하다고 가정하지 않습니다.[^4]

이 체크리스트의 결론은 단순합니다. configdrive/metadata 입력은 “파일 업로드”가 아니라 “컨트롤 플레인 리소스 요청”이고, 운영자는 이를 **리소스 상한이 있는 프로토콜**로 다뤄야 합니다.

## 참고 자료

- [OSSA-2026-049 원문(oss-sec 아카이브)](https://seclists.org/oss-sec/2026/q4/433)
- [OpenStack Security Advisory: OSSA-2026-049](https://security.openstack.org/ossa/OSSA-2026-049.html)
- [Ironic 2026.1 릴리스 노트(보안 이슈 섹션)](https://docs.openstack.org/releasenotes/ironic/2026.1.html)
- [Ironic 샘플 설정: max_json_body_size_provision 등](https://docs.openstack.org/ironic/2025.1/configuration/sample-config.html)
- [Ironic 사용자 문서: configdrive 포맷과 제출 방식](https://docs.openstack.org/ironic/latest/user/deploy.html)
- [Ironic 코드: check_and_patch_configdrive의 gzip.decompress 사용](https://docs.openstack.org/ironic/latest/_modules/ironic/conductor/configdrive_utils.html)
- [Ironic conductor 설정: disable_configdrive_check 옵션 정의](https://docs.openstack.org/ironic/latest/_modules/ironic/conf/conductor.html)
- [Ironic Python Agent 코드: MAX_CONFIG_DRIVE_SIZE_MB = 64](https://docs.openstack.org/ironic-python-agent/latest/_modules/ironic_python_agent/partition_utils.html)
- [ironic-lib 코드: configdrive 64MiB 제한](https://docs.openstack.org/ironic-lib/ussuri/_modules/ironic_lib/disk_utils.html)
- [NGINX 문서: client_max_body_size](https://nginx.org/en/docs/http/ngx_http_core_module.html)
- [systemd 문서: systemd.resource-control (MemoryMax/CPUQuota)](https://www.freedesktop.org/software/systemd/man/249/systemd.resource-control.html)
- [RabbitMQ 문서: max_message_size 등 Configurable Limits](https://www.rabbitmq.com/docs/limits)

[^1]: <https://seclists.org/oss-sec/2026/q4/433>
[^2]: <https://docs.openstack.org/ironic/latest/user/deploy.html>
[^3]: <https://docs.openstack.org/ironic/latest/_modules/ironic/conductor/configdrive_utils.html>
[^4]: <https://docs.openstack.org/releasenotes/ironic/2026.1.html>
[^5]: <https://docs.openstack.org/ironic/xena/install/configdrive.html>
[^6]: <https://docs.openstack.org/ironic-python-agent/latest/_modules/ironic_python_agent/partition_utils.html>
[^7]: <https://docs.openstack.org/ironic-lib/ussuri/_modules/ironic_lib/disk_utils.html>
[^8]: <https://docs.openstack.org/ironic/2025.1/configuration/sample-config.html>
[^9]: <https://nginx.org/en/docs/http/ngx_http_core_module.html?amp_ga=1.114984391.1509956953.1490042234>
[^10]: <https://security.openstack.org/ossa/OSSA-2026-049.html>
[^11]: <https://www.freedesktop.org/software/systemd/man/249/systemd.resource-control.html>
[^12]: <https://www.rabbitmq.com/docs/limits>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
