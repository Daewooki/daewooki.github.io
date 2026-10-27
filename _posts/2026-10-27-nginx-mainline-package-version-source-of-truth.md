---
title: "NGINX 1.31.8 업그레이드: 패키지 기준으로 버전 진실 맞추기"
description: "tarball·리포지토리 패키지·문서·Windows 배포판에서 엇갈리는 nginx 버전을 하나의 기준선으로 합치는 운영 플로우를 정리합니다."
date: 2026-10-27 13:27:38 +0900
categories: ["Web", "NGINX"]
tags: ["nginx", "debian", "windows", "package-management", "release-engineering", "vulnerability-response"]
render_with_liquid: false
---

nginx를 운영에서 다루다 보면 버전이 한 가지가 아니라는 사실부터가 작업 난이도를 올립니다. `nginx -v`가 찍는 숫자, Debian/Ubuntu에서 `apt`가 보는 버전 문자열, nginx.org 패키지 풀의 `orig.tar.gz` 타임스탬프, 그리고 공식 문서에 적힌 “latest”가 서로 어긋나는 순간이 반드시 옵니다.

2026-10-21에 nginx.org news에 `nginx-1.31.8` mainline 릴리스가 공지됐고, 같은 날 nginx.org의 Debian mainline 패키지 풀에 `nginx_1.31.8.orig.tar.gz`와 `nginx_1.31.8-1~bookworm_*`가 올라온 게 인덱스에서 보입니다.[^1] 이 타이밍에 “우리 조직에서 nginx 버전의 기준선이 무엇인가”를 문서화해 두면, 다음 보안 공지나 긴급 패치가 왔을 때 커뮤니케이션 비용이 급격히 줄어듭니다.

아래는 내가 운영팀 관점에서 정리해 둔 기준선과 검증 플로우입니다. 결론은 단순합니다. 배포는 패키지로 하고, 버전의 진실은 패키지 메타데이터와 실행 바이너리를 기준으로 맞추고, 문서는 참고 자료로만 둡니다.

## 1.31.8을 둘러싼 세 가지 타임라인

이번 케이스를 “버전이 갈라지는 지점” 관찰용으로 보면, 근거를 확보하기가 쉽습니다.

- 릴리스 공지: nginx.org news에 2026-10-21자로 `nginx-1.31.8 mainline version has been released.`가 올라와 있습니다.[^1]
- 공식 다운로드 엔트리: nginx.org download 페이지는 mainline 버전으로 `nginx-1.31.8`과 `nginx/Windows-1.31.8`을 같은 줄에 둡니다.[^2]
- Debian mainline 패키지 풀: `/packages/mainline/debian/pool/nginx/n/nginx/` 인덱스에 `nginx_1.31.8.orig.tar.gz`, `nginx_1.31.8-1~bookworm.dsc`, `nginx_1.31.8-1~bookworm_amd64.deb`가 2026-10-21 18:26로 표시됩니다(인덱스 표기 기준).[^3]

여기서 이미 운영상 중요한 사실 하나가 나옵니다.

- upstream 버전(1.31.8)과 Debian 패키지 버전(`1.31.8-1~bookworm`)은 같은 릴리스를 가리키지만 문자열이 다릅니다.
- Windows 배포판은 파일/디렉터리 이름에 upstream 버전만 넣습니다.
- 문서(Windows 문서 포함)는 “latest mainline”을 권장하지만, 문서는 버전 문자열을 정규화해 주지 않습니다.

즉, 같은 1.31.8이라도 “어느 채널에서 무엇을 설치했는지”를 함께 말하지 않으면 운영 커뮤니케이션이 깨집니다.

## nginx에서 말하는 stable/mainline과 운영에서의 의미

mainline/stable은 단순히 “실험/안정”의 감정적 구분이 아니라, 배포 스트림과 백포트 정책의 차이로 이해해야 합니다.

공식 nginx GitHub 저장소는 stable과 mainline을 이렇게 구분합니다. stable은 stable 브랜치에서 빌드되고 mainline에서 critical fix를 백포트해 담고, mainline은 master에서 빌드되며 최신 기능과 버그픽스를 포함한다고 설명합니다.[^4]

Windows 문서는 더 노골적으로 운영 기준을 흔듭니다. nginx/Windows 설치 설명에서 “latest mainline version distribution (1.31.8)”을 받으라고 쓰고, 그 이유를 “mainline branch contains all known fixes”로 적습니다.[^5]

내 운영 결론은 이렇습니다.

- 보안/취약점 대응 속도를 KPI로 잡는 조직이면 mainline이 기본값이 됩니다. upstream이 알려주는 “known fixes”가 mainline에 먼저/빠르게 모이는 구조를 인정해야 합니다.[^5]
- 반대로, 외부 모듈 의존성이 크거나(예: 서드파티 dynamic module), 패키지 채널을 단일화하기 어려운 조직이면 stable이 아니라 “배포판 제공 패키지”가 기본값이 되는 경우가 많습니다. Debian bookworm은 nginx가 1.22.1 계열로 유지되고 있음을 sources.debian.org에서 바로 확인할 수 있습니다.[^6]

mainline이든 stable이든 중요한 건 일관성입니다. 버전을 맞추는 작업에서 가장 비용이 큰 건 “버전 숫자”가 아니라 “출처가 섞인 상태”입니다.

## 버전 진실을 쪼개서 정의하기: upstream / package / running

운영에서 버전 진실을 한 문장으로 정의하려고 하면 항상 실패합니다. 대신 세 가지로 나눠서 기록하는 게 안전합니다.

1) upstream version
- nginx가 릴리스한 소스 버전입니다. 1.31.8 같은 숫자가 여기에 해당합니다.
- 릴리스 공지(news), CHANGES, tarball 이름이 이 버전을 중심으로 움직입니다.[^1]

2) package version
- 패키징이 붙는 순간 upstream 버전 뒤에 distro/packaging revision이 붙습니다.
- nginx.org Debian mainline은 bookworm에서 `1.31.8-1~bookworm` 형태를 씁니다.[^3]

3) running binary identity
- 실제로 실행 중인 바이너리가 자신을 뭐라고 보고하는지, 어떤 옵션으로 빌드됐는지, 어떤 모듈이 로드되는지가 최종 진실입니다.
- nginx는 `-v`로 버전, `-V`로 빌드 파라미터까지 출력합니다.[^7]
- 설정 검증은 `-t`, 전체 설정 덤프는 `-T`로 합니다.[^7]

이렇게 쪼개면 “문서에서는 1.31.8이라는데 우리 서버는 1.31.8-1~bookworm이 찍힌다” 같은 대화가 헛바퀴를 덜 탑니다. upstream version은 같고 package version이 다르다고 말하면 됩니다.

## 패키지 버전 문자열이 운영에 중요한 이유: `~bookworm`의 의미

nginx.org 패키지에서 자주 보게 되는 `1.31.8-1~bookworm` 같은 표기는 단순 장식이 아닙니다. 업그레이드/다운그레이드 가능성과 직결됩니다.

Debian Policy는 패키지 버전 포맷을 `[epoch:]upstream_version[-debian_revision]`로 정의합니다.[^8] 그리고 버전 비교 규칙에서 `~`가 “끝 문자열보다도 앞서는(가장 작은)” 정렬을 갖는다고 명시합니다.[^9] Ubuntu 문서도 같은 맥락에서 `~`가 모든 것보다 먼저 정렬된다고 설명합니다.[^10]

운영 관점에서 이게 중요한 이유는 두 가지입니다.

- 같은 upstream(1.31.8)이라도 `-1~bookworm`과 `-1`은 버전 정렬 결과가 달라질 수 있습니다.
- repo가 여러 개 섞였을 때, “내가 의도한 패키지”가 우선순위에서 밀리면 `apt upgrade`가 예상치 못한 방향으로 움직일 수 있습니다.

그래서 nginx.org가 공식 설치 문서에서 apt pinning을 강하게 권장하는 흐름이 자연스럽습니다. Debian 설치 예시는 `Pin: origin nginx.org`, `Pin-Priority: 900`로 nginx.org 패키지를 우선시키는 설정을 넣습니다.[^11]

이 지점부터가 버전 진실 맞추기의 핵심입니다. “버전 숫자를 1.31.8로 맞춘다”가 아니라 “버전 출처를 nginx.org mainline로 고정한다”가 기준선이 됩니다.

## 기준선을 어디에 둘 것인가: 레포 / orig.tar.gz / 문서

운영팀이 합의해야 하는 건 “무엇이 1차 진실인가”입니다. 내 경험상 아래 순서가 가장 사고가 적었습니다.

1) running binary(현장 증거)
- 장애/취약점 대응에서 “지금 무엇이 떠 있냐”가 0순위입니다.
- `nginx -v`, `nginx -V`, systemd unit 상태, 실제 로드된 모듈 목록이 여기에 포함됩니다.[^7]

2) package manager(배포 증거)
- Debian/Ubuntu면 `dpkg -s nginx`의 Version, `apt-cache policy nginx`의 Candidate, 그리고 `/etc/apt/sources.list.d` 구성이 진실입니다.
- Windows면 “어떤 zip을 어디서 받았는지”가 패키지 매니저 역할을 대신합니다.

3) repository pool과 source artifacts(감사/재현 증거)
- nginx.org Debian pool에는 `.dsc`, `.debian.tar.xz`, `.orig.tar.gz`가 함께 올라옵니다.[^3]
- 이 조합은 “이 바이너리가 어떤 upstream 소스(1.31.8) 위에 어떤 packaging 변경을 얹었는지”를 재현하는 기반입니다.

4) 문서(의도/권장사항)
- 문서는 최신 상태가 아닐 수 있고, 버전 문자열을 운영에서 바로 쓰기엔 정보가 부족합니다.
- 다만 Windows 문서처럼 “mainline을 받아라, known fixes는 mainline에 있다” 같은 정책성 문장은 기준선 합의에 도움이 됩니다.[^5]

이 우선순위로 잡으면, 문서와 레포의 표기가 조금 흔들려도 “현장 증거 → 배포 증거 → 재현 증거”로 역추적이 됩니다.

## Debian/Ubuntu에서 nginx.org mainline 1.31.8로 맞추는 절차

여기서는 Debian 12 bookworm을 기준으로 씁니다. 같은 구조로 Ubuntu도 거의 그대로 갑니다(키링 패키지 이름 정도만 다름). nginx.org 공식 Linux packages 문서가 Debian/Ubuntu 설치 절차, 서명키 지문, mainline 레포 URL, pinning까지 한 번에 제공합니다.[^11]

### 1) 레포와 키를 먼저 고정합니다

```bash
# Debian 12 bookworm
sudo apt update
sudo apt install -y curl gnupg2 ca-certificates lsb-release debian-archive-keyring

# nginx 서명키를 키링으로 저장
curl https://nginx.org/keys/nginx_signing.key | gpg --dearmor \
  | sudo tee /usr/share/keyrings/nginx-archive-keyring.gpg >/dev/null

# 지문 확인(문서에 나온 fingerprint가 보여야 함)
gpg --dry-run --quiet --no-keyring --import --import-options import-show \
  /usr/share/keyrings/nginx-archive-keyring.gpg
```

nginx.org 문서는 fingerprint `573BFD6B3D8FBC641079A6ABABF5BD827BD9BF62`가 출력에 포함돼야 한다고 명시합니다.[^11]

다음으로 mainline 레포를 설정합니다.

```bash
# mainline 레포를 명시적으로 사용
echo "deb [signed-by=/usr/share/keyrings/nginx-archive-keyring.gpg] \
  https://nginx.org/packages/mainline/debian $(lsb_release -cs) nginx" \
  | sudo tee /etc/apt/sources.list.d/nginx.list

# pinning으로 nginx.org 우선
echo -e "Package: *\nPin: origin nginx.org\nPin: release o=nginx\nPin-Priority: 900\n" \
  | sudo tee /etc/apt/preferences.d/99nginx

sudo apt update
```

이 pinning 블록은 nginx.org 문서에 그대로 있는 형태입니다.[^11]

여기까지를 “버전 진실의 기준선 공사”라고 봅니다. 업그레이드 자체보다 이 단계가 더 중요합니다.

### 2) Candidate가 실제로 1.31.8-1~bookworm인지 확인합니다

```bash
apt-cache policy nginx | sed -n '1,120p'
```

예상 출력의 형태는 이런 식입니다(버전 숫자만 확인하면 됩니다).

```text
nginx:
  Installed: 1.31.7-1~bookworm
  Candidate: 1.31.8-1~bookworm
  Version table:
     1.31.8-1~bookworm 900
        900 https://nginx.org/packages/mainline/debian bookworm/nginx amd64 Packages
 *** 1.31.7-1~bookworm 100
        100 /var/lib/dpkg/status
```

여기서 Candidate가 배포판 기본 nginx(예: 1.22.x)로 보이면, 소스 리스트가 섞였거나 pinning이 적용되지 않은 상태입니다. Debian bookworm의 nginx가 1.22.1 계열이라는 건 공개 소스 목록에서도 확인됩니다.[^6]

### 3) 업그레이드는 버전을 명시해서 합니다

운영에서는 “최신으로 올려”가 아니라 “이 버전으로 올려”가 안전합니다.

```bash
sudo apt install -y nginx=1.31.8-1~bookworm

# 버전 확인(패키지 버전)
dpkg -s nginx | grep -E '^Version:'

# 버전 확인(upstream 버전)
nginx -v

# 빌드 옵션 확인(모듈/컴파일 옵션 차이 때문에 -V를 남기는 게 좋음)
nginx -V 2>&1 | sed -n '1,80p'
```

`nginx -v`와 `dpkg -s`가 서로 다른 문자열을 찍는 건 정상입니다. `nginx -v`는 upstream 버전(1.31.8)을 말하고, `dpkg`는 패키지 버전(`1.31.8-1~bookworm`)을 말합니다. 둘 다 기록해야 “버전 진실”이 됩니다.

### 4) 업그레이드 검증은 `-t`, `-T`를 자동화 포인트로 삼습니다

nginx의 커맨드라인 스위치는 `-t`(config test), `-T`(config dump 포함), `-v`, `-V`를 공식 문서에서 정의합니다.[^7]

```bash
# 설정 문법 + 참조 파일 open까지 확인
sudo nginx -t

# 운영에서 자주 필요한 것: 실제 include까지 펼친 결과를 아카이빙
sudo nginx -T 2>/tmp/nginx-T.stderr | tee /tmp/nginx-T.stdout >/dev/null

sha256sum /tmp/nginx-T.stdout /tmp/nginx-T.stderr
```

내 경우, 업그레이드 검증의 “최소 증거 묶음”을 아래 4개로 잡습니다.

- `dpkg -s nginx` 출력
- `nginx -V` 출력
- `nginx -T` 출력(표준출력/표준에러)
- `/var/log/nginx/error.log`의 업그레이드 직후 5분 구간

이 정도면 장애가 났을 때 재현/역추적이 됩니다.

## nginx 1.31.8에서 놓치기 쉬운 변경: `working_directory` 상대 경로

버전 진실만 맞추고 넘어가면 안 되는 게 “작동 방식 변경”입니다. 이번 1.31.8 CHANGES에는 `working_directory`의 해석이 바뀌었다는 항목이 있습니다.

- 1.31.8: `working_directory`가 “현재 디렉터리”가 아니라 “nginx prefix 디렉터리” 기준 상대 경로가 됐다고 적혀 있습니다.[^12]
- 그리고 잘못된 디렉터리를 지정했을 때 worker가 start/reconfigure 시점에 종료할 수 있는 버그픽스도 같은 덩어리로 들어가 있습니다.[^12]

운영에서 이게 왜 중요하냐면, 다음 패턴이 있기 때문입니다.

- systemd unit이나 container entrypoint가 어떤 작업 디렉터리에서 nginx를 띄우는지 사람마다 다르게 이해하는 경우
- `working_directory`를 상대 경로로 쓰고 “어차피 여기서 실행하니까”라고 생각해 둔 설정

이 변경은 “버전 숫자만 올리면 되는” 작업이 아니라 “설정 의미가 바뀌는” 업그레이드입니다. 따라서 업그레이드 검증 플로우에 `nginx -T` 결과에서 prefix/working_directory 관련 라인을 점검하는 단계를 넣는 게 맞습니다.

예를 들면:

```bash
sudo nginx -T 2>&1 | grep -nE '^(# )?(prefix|working_directory)'
```

이건 기능 추가보다 더 위험한 유형의 변경입니다. 릴리스 노트를 자동으로 파싱해서 “의미 변경(Change)” 항목이 있으면 검증 티켓에 자동으로 링크를 붙이는 쪽이 낫습니다. CHANGES는 nginx.org에서 텍스트로 제공됩니다.[^12]

## `orig.tar.gz`로 upstream과 패키지를 연결하는 방법(재현 가능한 증거 만들기)

nginx.org Debian pool이 유용한 이유는, 바이너리 `.deb`만 주는 게 아니라 Debian 소스 패키지의 3종 세트를 같이 주기 때문입니다.

- `nginx_1.31.8.orig.tar.gz`
- `nginx_1.31.8-1~bookworm.debian.tar.xz`
- `nginx_1.31.8-1~bookworm.dsc`

이 파일들이 실제로 2026-10-21 18:26로 올라와 있는 걸 인덱스에서 확인할 수 있습니다.[^3]

운영팀 관점에서 이걸 왜 확인하냐면, 취약점 대응에서 자주 이런 질문이 나오기 때문입니다.

- “패키지에 포함된 소스가 정말 upstream 1.31.8이 맞나?”
- “우리 패키지에는 downstream 패치가 얼마나 들어가 있나?”
- “감사/포렌식 때 재현 가능한가?”

Debian 계열이라면 아래처럼 로컬에서 소스 패키지를 풀어볼 수 있습니다.

```bash
sudo apt install -y dpkg-dev

WORK=/tmp/nginx-src-1.31.8
mkdir -p "$WORK" && cd "$WORK"

# nginx.org pool에서 소스 패키지 3종을 받는다
curl -fsSLO https://nginx.org/packages/mainline/debian/pool/nginx/n/nginx/nginx_1.31.8.orig.tar.gz
curl -fsSLO https://nginx.org/packages/mainline/debian/pool/nginx/n/nginx/nginx_1.31.8-1~bookworm.debian.tar.xz
curl -fsSLO https://nginx.org/packages/mainline/debian/pool/nginx/n/nginx/nginx_1.31.8-1~bookworm.dsc

# dsc를 기준으로 소스를 전개한다
rm -rf nginx-1.31.8
DPKG_COLORS=never dpkg-source -x nginx_1.31.8-1~bookworm.dsc

# 어떤 파일이 들어왔는지 확인
ls -al
ls -al nginx-1.31.8 | head
```

예상 결과는 이런 형태입니다.

```text
nginx_1.31.8-1~bookworm.dsc
nginx_1.31.8-1~bookworm.debian.tar.xz
nginx_1.31.8.orig.tar.gz
nginx-1.31.8/
```

여기서 한 단계 더 들어가면, upstream tarball(`nginx-1.31.8.tar.gz`)과 Debian source의 `orig.tar.gz`가 동일한지 해시로 비교할 수 있습니다. nginx.org download 페이지가 mainline tarball 엔트리를 제공한다는 사실은 확인 가능하지만, 실제 해시 비교는 운영 환경에서 직접 다운로드해 수행해야 합니다.[^2]

```bash
# upstream tarball을 따로 받아서(운영 환경에서) 비교한다고 가정
sha256sum nginx_1.31.8.orig.tar.gz nginx-1.31.8.tar.gz
```

두 해시가 같으면 “upstream 소스와 packaging orig가 동일”하다는 증거가 됩니다. 다르면 그 차이를 먼저 이해해야 합니다(재패키징, 압축 옵션 차이, 또는 완전히 다른 소스).

추가로, nginx.org는 패키징 소스가 별도의 GitHub 저장소에 있고, mainline은 `master` 브랜치가 현재 mainline 패키징을 담는다고 문서에 적습니다.[^11] 이건 “패키지 빌드 옵션이 upstream 기본값과 다를 수 있다”는 경고이기도 합니다.

## Windows 배포판에서의 버전 진실: beta라는 전제가 먼저입니다

Windows에서 nginx를 운영에 쓰는 팀을 종종 봤고, 대개는 레거시 이유로 어쩔 수 없는 케이스였습니다. 그럴수록 버전 진실을 더 엄격하게 잡아야 합니다.

공식 Windows 문서는 다음을 분명히 합니다.

- Win32 API 기반이며 `select()`와 `poll()`만 쓴다고 적습니다.
- 고성능/확장성을 기대하지 말라고 쓰고, Windows 버전은 beta로 간주된다고 명시합니다.[^5]

그리고 설치 단계에서 mainline 최신 배포판(현재 문서에서는 1.31.8)을 받으라고 안내합니다.[^5] download 페이지도 Windows 엔트리를 `nginx/Windows-1.31.8`로 제공합니다.[^2]

Windows에서 버전 진실을 맞출 때는 “문서에 적힌 숫자”가 아니라 “내가 받은 zip 파일의 출처 + unzip된 디렉터리 + 실행 바이너리 출력”을 세트로 남겨야 합니다.

### Windows 업그레이드 예시(현실적인 기록 포맷)

```powershell
# 작업 디렉터리
$Work = "$env:TEMP\nginx-1.31.8"
New-Item -ItemType Directory -Force -Path $Work | Out-Null
Set-Location $Work

# 다운로드(공식 download 엔트리에 대응)
Invoke-WebRequest -Uri "https://nginx.org/download/nginx-1.31.8.zip" -OutFile "nginx-1.31.8.zip"

# 압축 해제
Expand-Archive -Path "nginx-1.31.8.zip" -DestinationPath "C:\" -Force
Set-Location "C:\nginx-1.31.8"

# 버전 확인(실행 바이너리 기준)
.\nginx.exe -v
.\nginx.exe -V

# 기동 및 프로세스 확인(공식 문서 예시와 동일한 흐름)
Start-Process -FilePath ".\nginx.exe"
tasklist /fi "imagename eq nginx.exe"
```

Windows 문서는 `tasklist`로 master/worker 프로세스를 확인하는 예시를 그대로 싣고 있고, 경로 prefix 동작(실행 위치가 prefix가 됨), 설정 파일 경로 표기(슬래시) 같은 함정도 같이 적습니다.[^5] 이 문서의 존재 이유가 “Windows는 UNIX와 동일하게 생각하면 안 된다”는 경고라고 봅니다.

Windows의 버전 진실은 특히 단순합니다.

- upstream version: zip 파일명에 들어있는 `1.31.8`
- running binary identity: `nginx.exe -v/-V`
- package manager가 없으니, 다운로드 URL과 해시를 남겨서 대체

zip을 어디서 받았는지와 파일 해시가 없으면, 같은 1.31.8이라도 재현이 안 됩니다.

## 업그레이드 검증 플로우: 운영팀이 합의해야 하는 최소 단계

버전 진실을 맞춘다는 건 결국 “업그레이드 검증이 반복 가능하다”는 뜻이어야 합니다. 내가 쓰는 플로우를 nginx에 맞게 정리하면 아래입니다.

### 1) 인벤토리 단계(현재 상태를 먼저 증거화)

Linux(Debian/Ubuntu):

```bash
set -euo pipefail

echo "== package =="
dpkg -s nginx | sed -n '1,120p'

echo "== binary version =="
nginx -v
nginx -V 2>&1 | sed -n '1,120p'

echo "== config test =="
sudo nginx -t

echo "== config dump hash =="
sudo nginx -T 2>/dev/null | sha256sum
```

Windows:
- `nginx.exe -v/-V` 출력 저장
- `nginx-*.zip` 해시 저장
- `C:\nginx-*\conf\nginx.conf`와 include 파일들 해시 저장

여기까지가 없으면 업그레이드는 “변경”이 아니라 “도박”이 됩니다.

### 2) 타깃 정의 단계(업stream/패키지/채널을 함께 고정)

예시(이번 케이스):

- upstream: 1.31.8
- channel: nginx.org mainline
- Debian package: 1.31.8-1~bookworm
- Windows artifact: nginx-1.31.8.zip

이 4개가 한 문장으로 말해지면, 운영 커뮤니케이션이 안정됩니다.

### 3) 아티팩트 검증 단계(서명/출처)

- Debian/Ubuntu: apt는 repo 메타데이터와 패키지 서명을 검증합니다. nginx.org는 서명키를 키링으로 설치하고 지문을 확인하라고 절차에 포함합니다.[^11]
- pinning: nginx.org는 배포판 제공 패키지보다 자기 패키지를 우선하라고 pinning까지 제공합니다.[^11]

Windows:
- 패키지 매니저 서명 검증이 없으니, 다운로드 URL(공식 도메인), 파일 해시, 내부 파일 목록을 남기는 것으로 대체합니다.

### 4) 설정/런타임 검증 단계

- `nginx -t`는 반드시 자동화합니다.[^7]
- `nginx -T` 결과를 저장하고 diff 포인트로 씁니다.[^7]
- CHANGES의 “Change” 항목은 설정 의미 변경으로 취급합니다. 1.31.8의 `working_directory`가 대표 사례입니다.[^12]

이 부분은 내가 예전에 정리했던 HTTP/3 구성 의존 CVE 대응 체크리스트의 관점(“기능을 켠 부분이 취약점 경계가 된다”)과도 연결됩니다. 설정 의미가 바뀌면 보안 경계도 바뀝니다.

- [NGINX HTTP/3 구성 의존 CVE 대응 체크리스트](https://daewooki.github.io/posts/nginx-http3-quic-cve-mitigation-checklist/)

### 5) 롤백 가능성 확보(가장 자주 빠지는 부분)

패키지 기반 운영에서 롤백이 어려운 이유는 보통 하나입니다.

- “이전 버전 .deb가 로컬에 남아 있지 않다”

nginx.org repo는 fast-moving이고, 운영 환경에 따라서는 과거 버전을 계속 제공한다고 가정하면 위험합니다. 따라서 업그레이드 직전에 “지금 설치된 버전”과 “올릴 버전”의 `.deb`를 둘 다 별도 아티팩트 저장소에 보관하는 게 안전합니다.

Debian/Ubuntu에서는 최소한 아래 정도는 해둡니다.

```bash
# 현재 설치된 버전을 파일로 확보
apt-get download nginx

# 타깃 버전을 명시해서 확보(예: 1.31.8-1~bookworm)
apt-get download nginx=1.31.8-1~bookworm
```

이걸 안 하면, 긴급 롤백이 “가능한지 불가능한지”부터 확인해야 합니다.

## 함정과 트레이드오프: 버전 진실을 무너뜨리는 패턴

### 1) 배포판 nginx와 nginx.org nginx를 섞는 순간 모듈이 무너집니다

Debian bookworm은 nginx가 1.22.1 계열이고, nginx.org mainline은 1.31.8 계열입니다.[^6] 이 차이는 단순히 기능 차이가 아니라 “빌드 옵션, 패치, 모듈 ABI” 차이로 이어질 수 있습니다.

nginx.org는 dynamic module을 별도 패키지로 배송한다고 문서에 적고, 어떤 모듈이 분리되는지도 나열합니다.[^11] 즉, nginx를 nginx.org에서 받으면 모듈도 nginx.org 쪽 패키지 세트로 맞추는 게 기본입니다.

이걸 섞으면 버전 진실이 무너집니다. `nginx -v`는 1.31.8을 찍는데, 로드된 `.so`는 배포판 빌드 기준으로 빌드된 것일 수 있습니다. 장애는 보통 업그레이드 당일이 아니라 “다음 reload 시점”에 터집니다.

### 2) `nginx -v`만 믿으면 보안 티켓이 잘못 닫힙니다

취약점 공지는 대개 upstream 버전 기준으로 나옵니다(예: “1.31.7에서 수정”). news도 stable/mainline을 같이 언급하며 CVE를 연결해 공지합니다.[^1]

그런데 패키지 기반 운영에서는 실제로는 `1.31.7-1~bookworm`인지 `1.31.7-2~bookworm`인지가 중요할 때가 있습니다(패키징 수정만 들어갔을 수도 있고, 빌드 플래그가 바뀌었을 수도 있음). 이때 `nginx -v`는 둘을 구분 못 합니다.

그래서 보안 대응 티켓의 닫힘 조건을 다음처럼 분리해 두는 게 낫습니다.

- upstream fix boundary 충족 여부: `nginx -v`로 확인
- 배포 아티팩트 동일성/재현성: `dpkg -s nginx` + repo origin + `.deb` 해시로 확인

### 3) Windows는 “문서의 1.31.8”과 “실제 zip”을 분리해야 합니다

Windows 문서가 1.31.8을 예시로 드는 건 “작성 시점의 최신”을 의미할 뿐, 그 숫자가 규격은 아닙니다.[^5] download 페이지가 실제 배포 엔트리를 갖고 있고, 결국 거기에 있는 파일을 받는 게 배포 진실입니다.[^2]

Windows 운영에서 가장 자주 보는 실수는 이겁니다.

- 사내 위키에는 “Windows nginx는 1.31.8”이라고만 적혀 있고
- 실제 서버는 누군가 예전에 받아둔 zip을 재사용해서 1.31.6이 떠 있는 상태

이건 사람이 나쁜 게 아니라, 패키지 매니저가 없으면 자연스럽게 벌어지는 일입니다. 그래서 Windows는 “다운로드 URL + 파일 해시 + `nginx.exe -V` 출력”을 한 묶음으로 남기는 규칙이 필요합니다.

## 도입 판단 기준: 우리 조직의 기준선은 무엇이어야 하나

여기까지를 기반으로 운영팀 기준선을 결정할 때 나는 아래처럼 정리합니다.

- mainline을 쓰기로 했다면, 버전 기준선은 문서가 아니라 nginx.org 패키지 레포가 됩니다. 레포 설정(mainline URL)과 pinning이 곧 정책입니다.[^11]
- 배포판 패키지를 쓰기로 했다면, upstream 버전 최신 여부는 포기하고, 대신 배포판 security advisory와 backport 정책을 추적하는 게 정책이 됩니다. Debian bookworm이 nginx 1.22.1 계열이라는 사실은 “우리가 upstream 숫자에 맞춰 움직이기 어렵다”는 신호입니다.[^6]
- Windows는 beta라는 전제를 깔고, 설치 편의성 때문에 쓰는 범위(개발/테스트/로컬 프록시)와 운영 범위를 분리해야 합니다. 문서가 beta를 명시합니다.[^5]
- 취약점 대응 속도를 올리고 싶다면, 버전 진실을 “upstream/package/running” 3분할로 강제하고, 증거 묶음(`dpkg -s`, `nginx -V`, `nginx -T`, 아티팩트 해시)을 자동 수집하게 만들어야 합니다.

내 경우 1.31.8 같은 mainline 업그레이드는 “버전 숫자를 올리는 작업”으로 취급하지 않고 “배포 채널의 정합성을 유지하는 작업”으로 취급합니다. 이 관점으로 바꾸면, tarball/문서/윈도우 zip이 서로 다르게 보이는 문제는 대부분 소음으로 내려가고, 실제 운영 리스크(설정 의미 변경, 모듈 호환성, 롤백 불가능)가 전면으로 올라옵니다.

## 참고 자료
- [nginx news](https://nginx.org/news.html)
- [nginx: download](https://nginx.org/en/download.html)
- [nginx CHANGES](https://nginx.org/en/CHANGES)
- [Debian mainline pool index (nginx.org)](https://nginx.org/packages/mainline/debian/pool/nginx/n/nginx/)
- [nginx: Linux packages](https://nginx.org/en/linux_packages.html)
- [nginx for Windows](https://nginx.org/en/docs/windows.html)
- [Command-line parameters](https://nginx.org/en/docs/switches.html)
- [Debian Sources: Package nginx](https://sources.debian.org/src/nginx/)
- [Debian Policy Manual (Version fields and ordering rules)](https://www.debian.org/doc/debian-policy/ch-controlfields)
- [Ubuntu documentation: Version string format](https://ubuntu.com/project/docs/how-ubuntu-is-made/concepts/version-strings/)
- [nginx/nginx GitHub repository (Stable and Mainline binaries 설명)](https://github.com/nginx/nginx)
- [NGINX 1.16 and 1.17 소개 글(메인라인/스테이블 운영 관점 참고)](https://www.unitserver.org/blog.nginx.com/content/nginx-1-16-1-17-released.html)

[^1]: <https://nginx.org/news.html>
[^2]: <https://nginx.org/en/download.html>
[^3]: <https://nginx.org/packages/mainline/debian/pool/nginx/n/nginx/>
[^4]: <https://github.com/nginx/nginx>
[^5]: <https://nginx.org/en/docs/windows.html>
[^6]: <https://sources.debian.org/src/nginx/>
[^7]: <https://nginx.org/en/docs/switches.html>
[^8]: <https://www.debian.org/doc/debian-policy/policy.pdf>
[^9]: <https://www.debian.org/doc/debian-policy/ch-controlfields>
[^10]: <https://ubuntu.com/project/docs/how-ubuntu-is-made/concepts/version-strings/>
[^11]: <https://nginx.org/en/linux_packages.html>
[^12]: <https://nginx.org/en/CHANGES>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
