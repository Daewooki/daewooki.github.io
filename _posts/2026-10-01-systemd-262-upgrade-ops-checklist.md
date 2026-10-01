---
title: "systemd 262 업그레이드 실전 가이드: fscrypt v2·TPM 강화·빌드 옵션 변화가 운영 계약을 깨는 지점"
description: "261.x에서 262로 올릴 때 이미지 빌드·TPM/UKI·homed·저널·롤백 호환에서 깨지는 계약을 체크리스트로 정리합니다."
date: 2026-10-01 14:02:20 +0900
categories: ["Systems", "Systemd"]
tags: ["systemd", "linux-ops", "tpm2", "fscrypt", "debian-unstable", "image-build"]
render_with_liquid: false
---

## 262가 배포권에 들어온 시점과, 지금 업그레이드를 계획해야 하는 이유

systemd v262는 2026-09-22 전후로 릴리스되었고, Debian에서는 2026-09-22에 unstable에 `262-1`이 accept 되었으며 2026-09-29에 testing으로 migrate 되었습니다. 운영팀 입장에서는 “조만간 누군가의 apt upgrade가 맞는 순간”이 이미 왔다는 뜻입니다.[^1]

여기서 중요한 포인트는 v262가 단순히 새 기능을 추가한 릴리스가 아니라, 배포 표준(이미지/부트/암호화/TPM 정책)을 바꾸는 성격이 강하다는 점입니다. 예전 글에서 systemd stable을 백포트할지, 기능 릴리스를 자체 업그레이드로 받아들일지의 운영 기준을 정리한 적이 있는데, v262는 그 기준표에서 “기능 릴리스를 업그레이드 창에 태워야 하는” 쪽으로 무게가 실립니다.

- [systemd 안정 릴리스와 운영 기준: 백포트 vs 자체 업그레이드](https://daewooki.github.io/posts/systemd-stable-backport-vs-upgrade-policy/)

이번 글은 새 옵션 소개가 아니라 261.x → 262로 넘어갈 때 운영 계약이 깨지는 지점을 체크리스트로 정리합니다. 특히 다음 축을 우선순위로 봅니다.

- 이미지 빌드(정적 PID 1, 빌드 옵션, 링크/의존성 변화)
- 커널/LSM/파일시스템 의존성(fscrypt v2, 네임스페이스, 컨테이너)
- systemd-homed 데이터 호환과 마이그레이션 불가 구간
- TPM 정책(Argon2id PIN, SRK pinning, NvPCR/UKI, crypttab 변화)
- 롤백(구버전 systemd와의 호환 경계가 어디서 끊기는지)

## 261.x → 262에서 “깨지는 계약” 요약

운영에서 계약이 깨진다는 말은, 기존에 성립하던 전제가 더 이상 자동으로 성립하지 않는다는 뜻입니다. v262에서 특히 눈에 띄는 건 다음입니다.

1) **systemd-homed + fscrypt: 신규 홈의 기본 정책이 fscrypt v2로 바뀜**
- 새로 만드는 fscrypt-backed home은 fscrypt v2 policy가 기본값입니다.
- v1 home은 계속 unlock/rekey/deactivate를 지원하지만 v1 → v2 in-place 업그레이드는 없습니다.[^2]
- v2의 의도는 “filesystem keyring에 master key를 설치해서 mount namespace/container에서도 보이게 한다”는 동작 변화입니다.[^2]

2) TPM bound artifacts의 롤백 호환 경계가 더 명확해짐
- TPM-sealed credentials가 TPM의 SRK에 pinning 됩니다.
- 이 변경 이후에 mint된 TPM-bound credential은 **구버전 systemd가 인식하지 못합니다**. 반대로 새 systemd는 변경 이전에 만들어진 credential을 계속 받아들입니다.[^2]
- 즉, “롤백 가능한가?”를 묻는다면 ‘바이너리/패키지’의 롤백뿐 아니라 ‘새 버전이 생성한 상태 파일/토큰/credential’을 구버전이 읽을 수 있느냐로 질문을 바꿔야 합니다.

3) TPM2 PIN이 Argon2id로 강화되면서, 무심코 선택한 정책이 운영 리스크가 됨
- `systemd-cryptenroll --tpm2-with-pin=yes`가 Argon2id 기반 hardening을 수행합니다.[^2]
- Dictionary attack lockout(글로벌 TPM 속성)과 상호작용하므로, 잘못된 PIN 입력이 반복되면 장시간 잠김 상태가 될 수 있습니다.[^3]

4) TPM/부트 측면에서 UKI를 전제하는 구성요소가 한 단계 더 늘어남
- NvPCR anchoring 방식이 바뀌었고, NvPCR definition이 UKI에 포함되어야 하며, initrd phase에 바인딩된 signed PCR policy가 UKI에 embed 되어야 한다는 요구가 들어왔습니다. 기존 NvPCR은 자동 업그레이드되지만, 이 과정에서 “anchor secret”은 제거됩니다.[^2]

5) crypttab 옵션의 의미가 바뀌거나 무력화되는 구간이 있음
- 예를 들어 `tpm2-measure-bank=`는 deprecated 되었고 더 이상 효과가 없습니다(은행을 볼륨 단위로 제한할 수 없음).[^2]

6) 저널 sealing 구현이 libgcrypt → OpenSSL로 이동
- Journal sealing/FSS가 OpenSSL로 옮겨갔고, libsystemd가 더 이상 libgcrypt에 링크되지 않습니다. 또한 sealing 지원이 없어도 sealed journal file을 읽을 수는 있는데(검증만 skip) 이 동작을 전제로 삼는 최소 이미지가 많습니다.[^4]

7) tmpfiles 규칙이 “경고 후 무시”에서 “거부”로 바뀌는 구간
- tmpfiles.d에서 argument field를 사용하지 않는 line type에 비어있지 않은 argument가 있으면, 이전에는 경고 후 무시되던 것이 이제는 설정 자체가 reject 됩니다.[^2]

이 7개는 전부 “운영 계약”입니다. 업그레이드 작업의 핵심은 기능을 쓰느냐가 아니라, 이 계약 변화가 내 배포 파이프라인/이미지/롤백과 충돌하는지 확인하는 데 있습니다.

## 이미지 빌드 관점: 정적 PID 1 옵션이 생겼을 때의 함정

v262에서 운영적으로 제일 먼저 건드리게 되는 건 이미지 빌드입니다. “systemd를 정적으로 빌드해서 컨테이너 PID 1로 넣자”는 유혹이 생기기 때문입니다.

systemd는 Meson 옵션을 조합해서 정적 빌드를 만들 수 있고, 문서에 명시된 조합은 다음입니다.

- `--default-library=static --prefer-static -Dbuild-static=true -Dsystemd-multicall-binary=true`
- 이 조합은 정적 `systemd` 바이너리를 만들고, 컨테이너에서 PID1로 쓸 수 있다고 설명합니다.[^5]

다만 같은 문서에서 다음을 경고합니다.

- dlopen(3)을 사용하지 않으므로 optional library를 동적으로 로딩해서 기능을 늘리는 방식이 작동하지 않습니다.
- NSS를 지원하지 않고, static passwd/group 파일만으로 유저를 해석하는 단순화된 구현을 사용합니다.[^5]

이 두 줄은 운영적으로는 다음 의미입니다.

- “minimal image에서 systemd가 잘 뜬다”는 것을 “기능 호환이 유지된다”로 착각하면 안 됩니다.
- 특히 NSS 비활성화는 LDAP/SSSD 같은 외부 ID 소스가 있는 환경에서 컨테이너 내부 도구가 깨지는 원인이 됩니다.

### 체크리스트: 정적 PID 1을 쓰는 이미지와, 쓰지 않는 이미지의 경계를 분리

내 경우 이 지점에서 정책을 이렇게 갈랐습니다.

- 호스트 OS(서버/VM): 배포판 패키지의 동적 링크 systemd를 사용(평소대로)
- 앱 컨테이너: PID 1이 필요한 경우에도 systemd를 넣지 않거나, 넣더라도 “정적 PID 1”은 실험용/특정 베이스 이미지에서만

정적 PID 1을 도입하려면 다음 질문에 답이 있어야 합니다.

1) 컨테이너 내부에서 `getent passwd`가 NSS를 통해 기대한 결과를 내야 하는가?
2) optional library(dl opening)로 활성화되던 기능(예: 암호화/압축/TPM 관련 라이브러리 등)이 빠져도 되는가?
3) 디버깅 때 동적 링크 기반으로 추적하던 방식이 사라져도 운영이 가능한가?

### 재현 가능한 빌드 예시(컨테이너 PID 1 타겟)

아래는 “정적 PID 1을 만들어 컨테이너에서만 쓰겠다”는 전제의 예시입니다. 실제 배포판 패키지 빌드 플래그와 충돌할 수 있으므로, CI에서는 별도 job으로 분리하는 게 낫습니다.

```bash
# Debian/Ubuntu 계열 예시: 빌드 환경 준비
sudo apt-get update
sudo apt-get install -y \
  build-essential meson ninja-build pkg-config \
  libssl-dev libzstd-dev liblz4-dev libcap-dev \
  libmount-dev libpam0g-dev libaudit-dev \
  git

# 소스 준비 (태그는 v262로 고정)
git clone https://github.com/systemd/systemd.git
cd systemd
git checkout v262

# 정적 PID1/멀티콜 바이너리 빌드
meson setup build \
  --default-library=static \
  --prefer-static \
  -Dbuild-static=true \
  -Dsystemd-multicall-binary=true

ninja -C build

# 결과물 확인
./build/systemd --version
```

예상 출력은 최소한 다음을 만족해야 합니다.

- `systemd 262`로 버전이 표기될 것
- 빌드 옵션 summary에서 static 관련 플래그가 기대대로 적용되었을 것

정적 빌드 자체를 Meson 옵션으로 제공한다는 사실과, 그 부작용(dlopen 미사용/NSS 미지원)은 upstream README에 명시돼 있습니다.[^5]

## 저널과 크립토 의존성: libgcrypt가 빠질 때 최소 이미지가 깨지는 방식

운영에서 저널은 “로그 저장소”이면서 동시에 “장애 시 증거”입니다. 저널 sealing을 쓰는 환경은 흔치 않더라도, 저널 파일을 읽는 경로는 거의 항상 씁니다.

v262에서 저널 sealing/FSS가 libgcrypt에서 OpenSSL로 이동했고, libsystemd는 더 이상 libgcrypt에 링크되지 않습니다. 또한 sealing 지원이 unavailable이더라도 sealed journal file은 읽히며, 검증만 skip 됩니다.[^4]

여기서 깨지는 계약은 두 가지입니다.

1) “minimal rootfs에 넣어야 하는 crypto 라이브러리”의 기준이 바뀜
- 과거 이미지가 libgcrypt를 넣고 OpenSSL을 빼는 구성을 했을 수 있습니다.
- v262 이후 sealing 경로를 쓰려면 OpenSSL이 더 우선순위가 됩니다.

2) “검증이 실패하면 읽기 자체가 실패한다”는 가정이 깨짐
- sealing 지원이 없으면 검증이 skip 되면서 읽히는 동작이 생깁니다.[^4]
- 보안팀이 sealing을 “읽기 시 강제 검증”으로 간주했다면, 런타임에 sealing 지원이 빠진 이미지가 들어오지 않게 보장해야 합니다.

### 체크리스트: 빌드 산출물에서 libsystemd 링크 대상 확인

패키지 기반이면 배포판이 결정하지만, 자체 이미지(특히 initrd/UKI, 컨테이너 base)를 만들 때는 다음을 CI에서 확인하는 편이 낫습니다.

```bash
# systemd/journalctl이 기대한 라이브러리에 링크되는지 확인
ldd /usr/bin/journalctl | egrep 'ssl|crypto|gcrypt' || true

# seal 옵션을 실제로 쓰는 환경이라면, seal 동작을 smoke test로 강제
journalctl --verify --file=/var/log/journal/*/system.journal || true
```

출력은 환경에 따라 다르지만, 중요한 건 실패 시나리오를 “업그레이드 창에서” 확인하는 겁니다. 이 변화는 릴리스 노트(NEWS)에 명시된 호환성 변화입니다.[^4]

## systemd-homed + fscrypt v2: 컨테이너/네임스페이스가 섞인 환경에서의 의미

v262에서 homed 관련 핵심 변경은 명확합니다.

- 새 fscrypt-backed home은 fscrypt v2 policy가 기본값
- v1 home은 계속 지원
- v1 → v2 in-place 업그레이드 없음
- v2의 효과: master key가 filesystem keyring에 설치되어 mount namespace/container에서도 visible[^2]

운영에서 이게 중요한 이유는 “fscrypt v2가 더 좋다”가 아니라, 홈 디렉터리의 잠금/해제 경로가 네임스페이스 경계를 넘을 수 있다는 점이기 때문입니다. 컨테이너 런타임이나 systemd-nspawn, 혹은 mount namespace를 활용하는 격리 전략에서 v1과 v2의 체감 차이가 여기서 납니다.

### 커널 의존성: fscrypt v2는 커널 5.4+ 전제

fscrypt v2 policy는 커널 5.4 이상에서만 사용 가능하다고 fscrypt 툴 문서에 명시돼 있습니다.[^6]

대부분의 서버/클라우드 환경에서는 이미 5.4+가 일반적이지만, 중요한 건 “내가 지원하는 가장 오래된 커널/커스텀 커널/특수 장비 커널”입니다. homed를 쓰지 않더라도, 조직 표준 이미지에서 homed를 “허용”해두면 언젠가 누군가가 신규 홈을 fscrypt로 만들 수 있습니다. 그 순간 커널 제약이 운영 제약으로 바뀝니다.

### 호환성 결론: v262로 신규 홈을 만들면, 롤백은 사실상 홈 재생성 수준이 됨

in-place 마이그레이션이 없다는 건 단순히 불편한 정도가 아닙니다. 운영 절차가 이렇게 바뀝니다.

- 이전: homed 홈을 만들고, 문제가 생기면 패키지 롤백 + 재부팅으로 해결할 수 있다는 기대
- 이후: v262에서 fscrypt v2 홈을 생성했다면, 구버전으로 되돌리는 순간 “홈을 다시 만들고 데이터 복구”까지 고려해야 함

이건 배포 단위가 호스트냐, 사용자 머신이냐에 따라 폭발력이 다릅니다. 서버에서는 homed 자체를 잘 안 쓰지만, VDI/개발자 워크스테이션/교육장 이미지 같은 곳에서는 꽤 치명적일 수 있습니다.

### 체크리스트: 261.x에서 이미 fscrypt v1 홈을 운영 중인 경우

- v262 업그레이드 자체는 “기존 v1 홈을 계속 쓸 수 있음” 범주입니다.[^2]
- 다만 신규 생성/재생성 흐름이 v2로 바뀌므로, 계정 프로비저닝 자동화가 “어떤 타입의 home을 만들지”를 명시해야 합니다.

내 경우는 이 자동화 레이어에서 “homectl create가 fscrypt를 선택하는 조건”을 제거하거나, 최소한 환경별로 명시적으로 분기했습니다.

### recovery key 취급 변경: 파일로 안전하게 쓰는 옵션 추가

homectl에 `--recovery-key-file=` 옵션이 추가됐고, recovery key를 원자적으로 비교적 안전하게 파일로 기록할 수 있다고 릴리스 노트에 명시돼 있습니다.[^2]

운영적으로는 다음이 바뀝니다.

- 예전에는 recovery key를 사람이 복사/보관하는 흐름이 섞이기 쉬웠습니다.
- 이제는 “키를 파일로 만들고, 그 파일을 시크릿 스토리지로 이관하는 자동화”로 깔끔하게 정리할 수 있습니다.

하지만 이것도 롤백 관점에서는 ‘새 버전 도구로 생성한 아티팩트(키 보관 방식)가 이전 운영 절차와 충돌할 수 있음’을 의미합니다.

## TPM 강화: Argon2id PIN, SRK pinning, NvPCR/UKI 요구사항

v262의 TPM 관련 변경은 “보안 강화”로만 읽으면 안 됩니다. 운영팀에게는 부트 체인, 복구 절차, 롤백, 그리고 이미지 표준을 건드립니다.

### 1) TPM2 PIN hardening: Argon2id가 기본이 되는 순간

릴리스 노트에 따르면 TPM2 PIN enrollment에서 Argon2id hardening이 추가됐고, `--tpm2-with-pin=yes` 모드가 Argon2id로 키 material을 유도합니다. `--tpm2-with-pin=direct`는 레거시 direct/PBKDF2 호환 모드로 남습니다.[^2]

운영에서 체크할 포인트는 세 가지입니다.

- PIN 입력 실패가 TPM dictionary attack lockout을 트리거할 수 있음(전역 TPM 속성)[^3]
- Argon2 파라미터(메모리/iterations/parallelism 등)를 조정할 수 있음[^3]
- 헤드리스/자동화 환경을 위한 `--unlock-empty`, `--unlock-headless`가 들어옴[^2]

특히 lockout은 보안팀이 좋아하는 기능이기도 하지만, 운영팀이 싫어하는 장애 모드이기도 합니다. “장애가 났을 때 사람이 여러 번 틀리면 더 오래 장애가 지속되는” 성격이기 때문입니다.

#### 체크리스트: PIN을 도입하기 전에 먼저 확정할 것

1) PIN을 반드시 요구할 것인가, TPM 단독 unlock을 허용할 것인가
2) PIN은 어느 조직 단위가 알고 관리하는가(개인/팀/보안팀)
3) lockout 설정을 어디서 가시화하고, 장애 시 어떤 runbook으로 해제할 것인가

이 결론이 없는 상태에서 `--tpm2-with-pin=yes`를 표준으로 박아버리면, 보안은 좋아졌는데 운영이 깨지는 형태가 됩니다.

#### 재현 가능한 리허설(가상 TPM 또는 테스트 장비)

테스트 장비에서 LUKS2 볼륨(`/dev/nvme0n1p3` 가정)에 TPM2 + PIN을 enroll 하는 예시입니다.

```bash
# 현재 TPM2 디바이스 확인
systemd-cryptenroll --tpm2-device=list

# TPM2 + PIN(Argon2id hardening) enroll
sudo systemd-cryptenroll \
  --tpm2-device=auto \
  --tpm2-with-pin=yes \
  /dev/nvme0n1p3

# Argon2 파라미터를 고정하고 싶다면(예: unlock 시간이 너무 길거나 짧을 때)
sudo systemd-cryptenroll \
  --tpm2-device=auto \
  --tpm2-with-pin=yes \
  --tpm2-argon2id-memory=256M \
  --tpm2-argon2id-iterations=4 \
  /dev/nvme0n1p3
```

예상 결과는 다음의 성질로 확인합니다.

- 커맨드가 0 exit code로 끝날 것
- LUKS2 헤더에 TPM2 token이 추가되었을 것(`cryptsetup luksDump`로 확인)

Argon2id hardening과 관련 옵션은 systemd-cryptenroll(1)에 v262 추가로 명시돼 있습니다.[^3]

### 2) TPM-sealed credentials: SRK pinning이 만드는 롤백 경계

릴리스 노트에 따르면 TPM-sealed credentials가 TPM의 SRK에 pinning 됩니다. 목적은 MITM interposer 공격을 막고, TPM owner hierarchy가 PIN으로 보호되는 경우에도 TPM-sealed credentials를 사용할 수 있게 하는 것입니다.[^2]

그리고 운영에서 가장 중요한 한 줄이 바로 이겁니다.

- 이 변경 이후 minted된 TPM-bound credential은 구버전 systemd가 인식하지 못함
- 새 systemd는 변경 이전 credential도 계속 인식[^2]

이건 롤백의 정의를 바꿉니다.

- 패키지/커널 롤백만으로 “원래대로 돌아간다”가 더 이상 보장되지 않음
- 업그레이드 창에서 새 버전으로 credential을 발급/갱신/재생성하는 순간, 롤백 시 구버전이 그 상태를 못 읽을 수 있음

#### 체크리스트: 롤백 가능한 업그레이드 창을 만들려면

- 업그레이드 기간 동안 TPM-bound credential을 새로 mint하지 않게 통제할 것(가능하다면)
- 또는 mint가 필요하다면, “구버전에서 읽을 수 없는 상태가 생성됨”을 롤백 불가 조건으로 문서화할 것

여기서 중요한 건 기술 문제가 아니라, 변경 통제(change control)입니다.

### 3) NvPCR anchoring: UKI 파이프라인을 운영 표준으로 끌어올리는 압력

v262 릴리스 노트는 NvPCR anchoring 방식 변경을 꽤 구체적으로 말합니다.

- NvPCR은 initrd 환경에서만 초기 extend가 가능하도록 write policy가 바뀜
- 더 이상 anchor secret(TPM에 sealed 된 secret)에 의존하지 않음
- NvPCR가 동작하려면 `/usr/lib/nvpcr/*.nvpcr` 정의가 UKI에 포함돼야 함
- UKI는 initrd boot phase에 바인딩된 signed PCR policy를 embed 해야 하고, `ukify --sign-initrd-pcrs`로 생성할 수 있다고 명시[^2]

이 요구사항은 “TPM을 쓰는 measured boot 체계”를 운영하는 팀에게는 배포 포맷 변경에 가깝습니다.

#### 체크리스트: UKI를 아직 표준화하지 않은 조직의 경우

- measured boot, TPM 정책, NvPCR를 적극적으로 쓰는 팀이라면 UKI 전환이 더 미뤄지기 어렵습니다.
- 반대로 UKI를 안 쓰는 환경에서 NvPCR 관련 유닛이 실패하는 로그가 올라오기 시작하면, 그때는 “기능을 끄고 지나간다”가 답일 수도 있습니다. 다만 끌 때는 왜 끄는지(표준 부트 포맷 미정)를 문서화해야 재등장 시 혼란이 없습니다.

## crypttab/운영 자동화: deprecated 옵션이 ‘조용히 무시’될 때 생기는 장애

운영 자동화에서 가장 위험한 변화는 “예전 설정이 여전히 존재하지만 효과가 없어지는” 타입입니다. 사람은 설정 파일이 있으니 적용되고 있다고 믿기 때문입니다.

v262 릴리스 노트에는 `tpm2-measure-bank=`가 deprecated 되었고 더 이상 효과가 없다는 내용이 명시돼 있습니다. 이제 volume key measurement는 `systemd-pcrextend`로 varlink 호출을 통해 수행되며, “적합한 PCR bank를 자동 선택”하므로 볼륨 단위로 bank를 제한할 수 없다고 합니다.[^2]

### 체크리스트: fleet에 crypttab 템플릿이 있는 경우

1) 코드 검색으로 `tpm2-measure-bank=` 사용 여부를 찾음
2) 발견되면 두 갈래 중 하나로 결론
   - 정책이 더 이상 필요 없고 삭제한다
   - 정책이 필요하다면, bank 제한을 다른 계층(부트 정책/TPM 정책)에서 달성할 수 있는지 재설계한다

이 지점은 “옵션이 deprecated 됐으니 나중에 치우자”가 아니라, 지금 당장 치워야 하는 부류입니다. 남겨두면 감사/점검 때 오해를 만들고, 사고가 나면 원인 분석 시간을 늘립니다.

## tmpfiles 변화: 경고가 에러로 승격될 때의 배포 사고 패턴

릴리스 노트에 따르면 systemd-tmpfiles가 tmpfiles.d line type 중 argument field를 쓰지 않는 타입에 대해 non-empty argument가 있으면 구성을 reject 하도록 바뀌었습니다. 이전에는 경고 후 무시하던 동작이었습니다.[^2]

이건 실제로 배포 사고를 잘 만드는 변화입니다.

- 배포판/벤더의 tmpfiles snippet이 경고를 내고도 시스템이 계속 부팅되던 환경
- 운영팀이 그 경고를 무시해왔던 환경
- v262 업그레이드 이후에는 해당 snippet 때문에 tmpfiles 처리가 실패하고, 부팅 후 정리 작업/디렉터리 생성 등이 어긋날 수 있음

### 체크리스트: 업그레이드 전 사전 감사

아래는 업그레이드 창에서 최소한 한 번은 돌리고 싶은 커맨드들입니다.

```bash
# tmpfiles 구성이 깨지는지 사전 확인
systemd-tmpfiles --cat-config > /tmp/tmpfiles.all

# dry run 성격으로 create/clean을 돌려 로그를 확보
sudo systemd-tmpfiles --create --prefix=/var --boot --no-pager || true
sudo systemd-tmpfiles --clean --prefix=/tmp --no-pager || true

# 실패/경고를 journal에서 수집
journalctl -u systemd-tmpfiles-setup.service -u systemd-tmpfiles-clean.service --no-pager -b || true
```

여기서 목표는 “완벽히 고친다”가 아니라, 어떤 노드/어떤 이미지/어떤 레이어(벤더, 사내 베이스 이미지, 애플리케이션 패키지)가 문제의 snippet을 포함하는지 식별하는 것입니다.

## 롤백 전략: 패키지 롤백이 아니라 ‘상태 롤백’이 막히는 지점

261.x → 262에서 가장 위험한 롤백 실패는 다음 두 축에서 발생합니다.

1) homed/fscrypt: 신규 홈이 fscrypt v2로 생성된 이후
- 구버전으로 롤백해도 홈 정책을 v1로 되돌릴 수 있는 in-place 경로가 없습니다.[^2]
- 즉, “업그레이드 후 홈을 새로 만들지 않는다”가 롤백 가능성의 조건이 됩니다.

2) TPM-sealed credentials: SRK pinning 이후 minted된 credential
- 구버전 systemd가 인식하지 못하므로, 업그레이드 창에서 credential을 새로 mint하면 롤백이 사실상 불가능해집니다.[^2]

### 운영적으로 유효했던 롤백 단위(내 기준)

나는 롤백 단위를 세 단계로 나눠서 문서화하는 편입니다.

- Level 1: 패키지 롤백(apt/yum downgrade) + 재부팅
- Level 2: 패키지 롤백 + 커널/부트아티팩트(UKI/initrd) 롤백
- Level 3: 상태 롤백(홈/TPM/credential/토큰/키슬롯)까지 포함

v262는 Level 1, 2만으로 해결된다는 가정을 깨기 쉬운 릴리스입니다. 따라서 업그레이드 윈도우에서 “새 상태를 생성하는 작업”을 통제해야 합니다.

### 체크리스트: 업그레이드 윈도우에서 금지하거나, 별도 플래그로 격리할 작업

- `homectl create`로 신규 fscrypt home 생성
- TPM-bound credential 재발급/재생성(자동화가 있다면 특히)
- cryptenroll을 통한 TPM 토큰 추가/갱신(정책 변경)

이걸 금지하라는 얘기가 아니라, 업그레이드와 분리하자는 얘기입니다. 업그레이드가 실패했을 때 원인 범위를 좁히는 게 목적입니다. 예전에 Terraform/etcd/커널 롤아웃 체크리스트를 정리하면서 공통 패턴이 “변경 원인을 한 번에 하나로” 만드는 거였는데, v262 업그레이드도 구조는 같습니다.

- [Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다](https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/)
- [etcd v3.7.2 운영 리허설: 업그레이드·백업·복구·이미지 전략까지](https://daewooki.github.io/posts/etcd-372-kubernetes-ops-rehearsal/)
- [Linux stable 커널 롤아웃 체크리스트: 7.2.4](https://daewooki.github.io/posts/linux-stable-kernel-rollout-checklist-724/)

## 업그레이드 실행 계획(체크리스트 형태)

아래는 261.x → 262 업그레이드를 “기능 시험”이 아니라 “계약 시험”으로 보는 체크리스트입니다. 실제로는 전부를 다 할 필요가 없고, 조직에서 쓰는 기능만 골라서 깊게 하면 됩니다.

### A. 릴리스 유입 확인(배포권 체크)

- Debian을 기준으로 한다면, unstable accept(2026-09-22)와 testing migration(2026-09-29)을 확인합니다.[^1]
- fleet이 Debian unstable/testing을 그대로 쓰지 않더라도, 베이스 이미지/빌드 컨테이너가 영향을 받는지 확인합니다.

### B. 빌드/이미지 계약

- systemd를 정적으로 빌드할지 여부 결정
  - 정적 PID 1은 dlopen을 쓰지 않고 NSS도 비활성화된다는 제한을 감당할 수 있는 범위에서만[^5]
- 저널 sealing을 사용하는지 여부 확인
  - sealing/FSS가 OpenSSL로 이동했으므로 최소 이미지의 crypto 라이브러리 세트를 재검토[^4]

### C. 커널/파일시스템 계약

- homed + fscrypt를 쓰는지 여부 확인
- fscrypt v2를 허용할 커널 최소 버전을 정함
  - fscrypt v2는 커널 5.4+ 전제[^6]

### D. homed 데이터 호환 계약

- 기존 home이 v1인지 확인
- v262 이후 신규 홈 생성을 허용할지 결정
- v1 → v2 in-place 업그레이드가 없다는 사실을 runbook에 박아둠[^2]
- recovery key 파일 아카이빙 자동화가 필요하면 `--recovery-key-file=` 기반으로 정리[^2]

### E. TPM 정책 계약

- Argon2id PIN을 표준으로 삼을지, direct(PBKDF2 호환)로 둘지 결정[^2]
- PIN 도입 시 lockout 운영(runbook, 모니터링, 권한)을 설계[^3]
- SRK pinning으로 인해 “새로 mint된 credential은 구버전이 못 읽음”을 롤백 정책에 반영[^2]
- NvPCR을 쓰는 환경이면 UKI 파이프라인 요구사항(NvPCR 정의/서명된 PCR policy embed)을 충족하는지 확인[^2]

### F. tmpfiles/부팅 시퀀스 계약

- tmpfiles.d snippet을 사전 스캔하고, v262에서 reject 될 구문이 있는지 확인[^2]

## 판단: v262는 ‘올릴지 말지’가 아니라 ‘올릴 때 무엇을 금지할지’를 정하는 릴리스

v262의 변화는 성격이 제각각이지만, 운영 관점에서 공통 결론은 하나입니다.

- 업그레이드 자체보다, 업그레이드 이후 새 버전이 생성하는 상태(fscrypt v2 home, SRK pinned credential, NvPCR/UKI 전제 아티팩트)가 구버전과 비대칭 호환을 만든다는 점이 핵심입니다.[^2]

그래서 261.x → 262는 “새 기능을 언제 쓰지?”가 아니라, “업그레이드 윈도우에서 상태 생성 작업을 어디까지 허용하지?”를 먼저 결정해야 사고가 적습니다.

## 참고 자료

- [systemd v262 릴리스 노트(GitHub Releases)](https://github.com/systemd/systemd/releases/tag/v262)
- [systemd-262 NEWS(Fossies 미러)](https://fossies.org/linux/misc/systemd-262.tar.gz/systemd-262/NEWS)
- [systemd README의 STATIC BINARIES 섹션(Fossies 미러)](https://fossies.org/linux/misc/systemd-262.tar.gz/systemd-262/README)
- [Debian systemd 패키지 뉴스(unstable accept/testing migration 타임라인)](https://tracker.debian.org/pkg/systemd/news/)
- [Debian unstable에 systemd 262-1 accept 메일 아카이브](https://www.mail-archive.com/debian-devel-changes%40lists.debian.org/msg992955.html)
- [systemd-cryptenroll(1) man page(Argon2id PIN/lockout 설명, v262 추가 표기)](https://man.archlinux.org/man/systemd-cryptenroll.1.en)
- [fscrypt 프로젝트 문서(policy v2의 커널 요구사항)](https://git.hodgden.net/cgit.cgi/fscrypt.git/about/)
- [LWN: Systemd v262 released](https://lwn.net/Articles/1096204/)

[^1]: <https://tracker.debian.org/pkg/systemd/news/>
[^2]: <https://github.com/systemd/systemd/releases/tag/v262>
[^3]: <https://man.archlinux.org/man/systemd-cryptenroll.1.en>
[^4]: <https://fossies.org/linux/misc/systemd-262.tar.gz/systemd-262/NEWS>
[^5]: <https://fossies.org/linux/misc/systemd-262.tar.gz/systemd-262/README>
[^6]: <https://git.hodgden.net/cgit.cgi/fscrypt.git/about/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
