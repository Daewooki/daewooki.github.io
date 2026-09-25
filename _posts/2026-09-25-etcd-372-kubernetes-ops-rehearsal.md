---
title: "etcd v3.7.2 운영 리허설: 업그레이드·백업·복구·이미지 전략까지"
description: "etcd v3.7.2 릴리스 변경을 ‘클러스터 운영 작업’으로 번역해 업그레이드·멤버 교체·스냅샷/복구·defrag·성능 회귀·Docker 태그 변화 대응을 리허설합니다."
date: 2026-09-25 13:27:09 +0900
categories: ["Infrastructure", "Etcd"]
tags: ["etcd", "kubernetes", "upgrade", "backup-restore", "docker-images", "operations"]
render_with_liquid: false
---

## v3.7.2를 운영 일정으로 해석하면 먼저 보이는 것들

2026-09-22에 etcd v3.7.2가 릴리스되었습니다. 패치 릴리스 공지와 릴리스 날짜는 SIG etcd 블로그/CHANGELOG에서 교차로 확인됩니다.[^1]

v3.7.2 CHANGELOG 자체는 비교적 짧습니다. 핵심은 다음 3가지 축으로 정리하는 편이 운영에 유리합니다.[^2]

1) “복구 가능성”에 영향을 주는 서버 측 변경 2건
- `MinimalEtcdVersion`이 WAL에서 “latest snapshot entry”를 읽도록 업데이트
- “received snapshot db” 저장 시 snap 디렉터리 fsync 관련 수정

2) 운영 스크립트가 깨질 수 있는 etcdctl 출력 변경 1건
- `etcdctl endpoint status --write-out=fields` 출력에서 `RaftTerm` 중복 필드 수정

3) 보안/런타임 기반 변경
- Go 1.26.8로 빌드
- OpenTelemetry, gRPC 의존성 업데이트(CHANGELOG에 CVE 번호가 같이 기재됨)

패치 릴리스에서 기능 플래그나 스토리지 포맷이 크게 흔들리지는 않지만, “복구에 가까운 코드 경로(recovery-path)”와 “배포 산출물(artifact) 정책”은 패치에서도 운영 리스크가 커질 수 있습니다. 특히 Kubernetes에서 etcd는 장애 시점에만 손대는 부품이 아니라, 업그레이드/노드 교체/공간 관리/성능 회귀 측정까지 한 덩어리로 붙어 움직입니다.

그리고 사용자가 짚은 ‘개별 아키텍처 Docker 이미지 태그를 더 이상 릴리스하지 않음’은 v3.7.2 섹션이 아니라, 같은 CHANGELOG 파일의 v3.7.0-rc.0 Breaking Changes(2026-06-01) 항목에 명시되어 있습니다. 운영적으로는 “이게 v3.7.2에서 갑자기 생긴 변화인가?”를 먼저 바로잡아야 합니다.[^2]

이 글은 CHANGELOG 한 줄을 “클러스터 운영 작업”으로 번역하는 방식으로, 업그레이드/멤버 교체/스냅샷-복구/compaction-defrag/성능 회귀/이미지 태그 전략까지 한 번에 리허설하는 체크리스트로 정리합니다.

## 업그레이드 전제조건: v3.7.2 이전에 확인해야 하는 것

### 3.6 → 3.7 롤링 업그레이드 조건
etcd 공식 업그레이드 가이드는 v3.6에서 v3.7로 올라갈 때 롤링 업그레이드가 가능하다고 전제하면서도, 조건을 명시합니다.

- 업그레이드는 “한 마이너 버전씩”이 원칙
- 3.6 클러스터라면 멤버들이 3.6.11 이상이어야 롤링 업그레이드 호환이 보장됨
- 업그레이드 전에 클러스터가 healthy 상태여야 함
- 업그레이드 시작 전에 스냅샷을 떠서 “복구로 롤백 가능한 상태”를 만들어 두라는 문구가 꽤 강하게 반복됨

이 내용은 etcd v3.7 업그레이드 문서에 명확히 들어있습니다.[^3]

### v3.7에서 사라진 것(운영 측면)
v3.7은 내부 리팩터링도 있지만, 운영 측면에서 더 위험한 건 “예전 플래그가 남아 있으면 프로세스가 아예 안 뜨는” 종류입니다. 업그레이드 가이드는 deprecated `--experimental-*` 플래그가 v3.7에서 제거되었다고 명시합니다.[^3]

Kubernetes control plane의 etcd는 종종 kubeadm, distro, managed 제품이 생성한 systemd unit 또는 static Pod manifest를 그대로 들고 운영합니다. 이때 “내가 직접 넣은 플래그가 없는데?”라고 생각해도, 과거에 한 번 커스터마이징한 흔적이 남아 있으면 업그레이드 순간에 즉시 장애로 튑니다. 따라서 리허설에서는 다음 2가지를 반드시 합니다.

- 실행 중인 etcd의 실제 argv 덤프 확보(프로세스 cmdline, systemd unit, static Pod manifest)
- upgrade 대상 버전에서 제거된 플래그 존재 여부를 grep로 자동 검출

이 단계는 기술적으로는 간단하지만, 실제 장애 대부분이 여기서 납니다.

## 배포 산출물 정책 변화: **per-arch Docker tag 폐지**를 파이프라인 작업으로 번역하기

CHANGELOG-3.7에는 v3.7.0-rc.0 Breaking Changes로 “개별 아키텍처 Docker image tag를 더 이상 릴리스하지 않는다. multi-arch manifest를 사용하라”가 들어 있습니다.[^2]

이 한 줄이 의미하는 운영 작업은 크게 4갈래입니다.

### 1) ‘태그가 곧 아키텍처’라는 가정이 깨짐
기존에 다음 패턴을 썼다면 바로 점검 대상입니다.

- `...:v3.7.2-amd64`, `...:v3.7.2-arm64` 같은 per-arch tag에 의존
- 이미지 미러링 시 “tag rewrite 규칙”에 `-amd64`를 붙이도록 고정
- admission policy나 IaC 템플릿이 `*-amd64` 패턴 매칭에 의존

이제는 “하나의 태그 = manifest list(멀티 아키텍처 인덱스)”가 기본이 됩니다. Docker CLI에서도 manifest list를 multi-arch 이미지라고 부르며, `docker manifest inspect`로 확인하는 흐름이 문서화되어 있습니다.[^4]

확인 명령은 리허설에 넣어 두는 편이 좋습니다.

```bash
# 멀티 아키텍처(manifest list/index)인지 확인
# (레지스트리/이미지 경로는 환경에 맞춰 조정)
docker manifest inspect gcr.io/etcd-development/etcd:v3.7.2 | head

# 더 자세히 플랫폼별로 보고 싶으면 verbose
# (Docker CLI 실험 기능/환경에 따라 옵션 동작은 다를 수 있습니다.)
docker manifest inspect -v gcr.io/etcd-development/etcd:v3.7.2 | head
```

`docker manifest` 자체가 “manifest / manifest list 관리” 용도라는 점은 Docker 공식 문서의 커맨드 설명에서 확인할 수 있습니다.[^4]

### 2) 미러링 도구가 ‘인덱스’를 보존하는지 검증해야 함
레지스트리 미러링은 이제 “단일 이미지 복사”가 아니라 “인덱스 + 하위 manifest들” 복사가 됩니다.

Kubernetes의 공식 이미지 레지스트리(registry.k8s.io) 문서도 태그 확인 도구로 `crane`/`oras` 사용을 안내합니다.[^5]

내 경험상(특히 air-gapped) 문제가 자주 나는 지점은 두 가지입니다.

- 미러링 결과가 “인덱스는 복사됐는데 하위 플랫폼 manifest가 빠진” 불완전 상태
- 사내 레지스트리 UI가 multi-arch를 제대로 표시하지 못해서, 운영자가 “복사 실패”로 오판

리허설에서는 `crane copy`로 “기본값이 모든 플랫폼 복사인지”를 확인하고, 실제로는 “복사 후 다시 manifest inspect”로 검증합니다.

`crane copy` 문서는 `--platform` 옵션이 있고, 기본값이 “all”임을 명시합니다.[^6]

```bash
# 1) 원본 → 사내 미러로 복사 (기본: 모든 플랫폼)
crane copy \
  registry.k8s.io/etcd:3.7.0-0 \
  mirror.internal.example/etcd:3.7.0-0

# 2) 복사된 대상이 인덱스인지 확인
crane manifest mirror.internal.example/etcd:3.7.0-0 | head

# 3) 특정 플랫폼만 ‘의도적으로’ 가져오려면 --platform으로 제한
crane copy \
  --platform linux/amd64 \
  registry.k8s.io/etcd:3.7.0-0 \
  mirror.internal.example/etcd:3.7.0-0-amd64
```

(위 예시는 “플랫폼 하나만 쓰는 클러스터”에서 저장공간/전송량을 줄이려는 선택지입니다. 다만 Kubernetes control plane 이미지/etcd는 대개 multi-arch를 그대로 유지하는 편이 장기적으로 덜 고통스럽습니다.)

추가로, `oras repo tags` 같은 “태그 나열” 커맨드도 리허설에 유용합니다. ORAS 문서에서 `oras repo tags`는 태그를 출력하는 용도임이 분명합니다.[^7]

```bash
oras repo tags mirror.internal.example/etcd | head
```

### 3) tag pin에서 digest pin으로 넘어갈지 결정해야 함
이미지 태그는 정책상 언제든지 재사용될 수 있고(특히 `latest`), 실제로 etcd 이미지에서 `:latest`가 낡은 버전으로 남아 혼란을 만든 이슈가 과거에 있었습니다.[^8]

따라서 “표준 이미지 핀/미러링”을 강하게 하는 팀이라면, 이번 기회에 태그 pin을 유지할지, **digest pin**으로 옮길지 선택이 필요합니다.

- 태그 pin 장점: 사람이 이해하기 쉽고, kubeadm / 매니페스트에서 다루기 쉬움
- digest pin 장점: 배포 재현성과 공급망 측면에서 강함(같은 digest는 같은 바이트)
- digest pin 단점: 운영 가독성이 떨어지고, 업데이트 자동화가 없으면 관리 비용이 증가

어느 쪽이든 “인덱스(digest)가 멀티아키텍처 인덱스인지”까지 고려해 pin해야 합니다.

### 4) ‘etcd 이미지는 어디서 받는가’가 다시 흔들릴 수 있음
공식 릴리스 페이지는 여전히 Docker 예시로 `gcr.io/etcd-development/etcd` 및 `quay.io/coreos/etcd`를 언급합니다.[^9]

한편 v3.7부터 이미지 배포 레지스트리 변경을 공지해 달라는 이슈에서는 “registry.k8s.io/etcd에 이미지가 있다”, “gcr.io/etcd-development와 quay.io/etcd가 deprecated” 같은 제안이 나옵니다(확정 정책이라기보다는 ‘알려달라’는 요청 성격).[^10]

운영 체크리스트 관점에서는 “어차피 바뀔 수 있는 레지스트리”로 보고 다음을 리허설 항목으로 넣습니다.

- (a) 현재 프로덕션이 쓰는 image reference 전체 목록 추출
- (b) 해당 이미지들이 multi-arch 인덱스인지 검사
- (c) 레지스트리 변경 시에도 동일한 digest로 미러가 가능한지 시험
- (d) kubeadm 사용 시 `imageRepository` / etcd 별도 `imageTag` 오버라이드 경로 확인

kubeadm은 기본적으로 `registry.k8s.io`에서 이미지를 받고, 커스텀 레포를 쓸 수 있으며, etcd/CoreDNS는 별도 설정이 가능하다고 문서화되어 있습니다.[^11]

## 리허설 시나리오를 ‘장애 모드’까지 포함해 설계하기

리허설을 “업그레이드 한 번 해본다”로 끝내면, 실제 장애에서 쓸 근육이 안 생깁니다. etcd 운영 리허설은 최소한 다음 3개의 모드를 다뤄야 합니다.

1) 정상 롤링 업그레이드(가장 흔함)
2) 멤버 1개 교체(디스크/호스트 교체, control plane 노드 교체와 동일)
3) 쿼럼 상실 후 전체 복구(진짜 재난 복구)

etcd 공식 문서도 “쿼럼을 잃으면 합의가 안 돼서 업데이트를 못 받는다”를 DR 문서에서 분명히 전제합니다.[^12]

이 글에서는 3노드(odd) 클러스터를 기준으로 다음 목표를 둡니다.

- 업그레이드 중 mixed-version 상태를 안전하게 유지했다는 증거 남기기
- 멤버 교체 시 snapshot 전송/적용 경로를 실제로 타게 하기(= v3.7.2가 손댄 코드 경로를 밟기)
- 스냅샷/복구 시 Kubernetes 특유의 watch/informer 캐시 문제를 피하는 옵션을 반드시 사용하기
- defrag/compaction이 실제로 지연을 만들고, 그 지연이 API server에 어떤 형태로 드러나는지 관찰하기
- 이미지 태그 정책 변화가 파이프라인에서 어떤 실패로 나타나는지 재현하기

## 멤버 교체 리허설: ‘노드 교체’를 etcd 멤버십 작업으로 번역하기

멤버 교체는 업그레이드보다 흔합니다. 디스크 불량, OS 재설치, control plane 노드 교체, VM 스케일링 등으로 인해 “동일한 역할의 새 노드”를 넣어야 하는 순간이 더 자주 옵니다.

etcd는 runtime reconfiguration을 지원하고, 기본 원칙은 “순차적으로(sequentially) 변경한다”입니다. 문서에는 건강한 멤버 교체 시 “remove 후 add” 같은 패턴과 learner로 안전하게 추가할 수 있다는 언급이 있습니다.[^13]

### 교체 작업 전 체크(클러스터 상태 스냅샷)

리허설에서 가장 먼저 남길 로그는 아래 3개입니다.

- endpoint health
- endpoint status(raft term/index/applied index 포함)
- member list

`etcdctl endpoint status`가 어떤 정보를 보여주는지는 etcdctl README에서 확인할 수 있습니다.[^14]

예시는 kubeadm 기반 로컬 etcd(static Pod)에서 자주 쓰는 TLS 경로 형태로 적었습니다(환경에 맞게 수정해야 합니다).

```bash
export ETCDCTL_API=3
export ETCDCTL_ENDPOINTS="https://127.0.0.1:2379"
export ETCDCTL_CACERT=/etc/kubernetes/pki/etcd/ca.crt
export ETCDCTL_CERT=/etc/kubernetes/pki/etcd/healthcheck-client.crt
export ETCDCTL_KEY=/etc/kubernetes/pki/etcd/healthcheck-client.key

# 1) 상태
etcdctl endpoint health --cluster -w table
etcdctl endpoint status --cluster -w table

# 2) 멤버
etcdctl member list -w table
```

여기서 `endpoint status`를 `--write-out=fields`로 파싱하는 자동화가 있다면, v3.7.2에서 RaftTerm 중복 출력 버그가 수정되었기 때문에(= 출력이 달라짐) 파서가 “필드가 2개일 거라고 기대”하는 경우 깨질 수 있습니다. 버그 리포트 자체도 존재합니다.[^15]

### 리더를 먼저 옮기고 defrag/교체를 진행하는 이유
실제로 교체 작업을 하다 보면 “교체하려는 노드가 현재 leader”인 경우가 자주 걸립니다. 리더에서 defrag나 재시작을 하면 tail latency가 더 크게 튈 수 있습니다.

etcdctl에는 `move-leader`가 있고, 이는 “리더십을 다른 멤버로 옮긴다”는 커맨드입니다(코드/문서 레벨로 확인 가능).[^16]

또한 defrag를 큰 데이터에서 수행할 때 “리더를 다른 멤버로 옮기고, follower에서 defrag를 하라”는 운영 가이던스가 discussions 형태로 공유되어 있습니다.[^17]

```bash
# endpoint status에서 follower의 member ID 하나를 골라 move-leader
# (ID는 16진수로 출력되는 경우가 흔합니다.)
etcdctl endpoint status --cluster -w table

# 예: 89b0... 멤버로 리더 이동
etcdctl move-leader 89b0cafe1234abcd
```

### learner로 신규 멤버를 붙여 “클러스터 진행을 막지 않게” 만들기
새 멤버를 붙일 때 learner를 쓰면, 동기화가 끝나기 전까지 쿼럼에 영향이 덜합니다(개념은 learner 문서에 설명되어 있고, `etcdctl member add --learner` 플래그가 존재함이 CHANGELOG/문서에 나타납니다).[^18]

교체 절차를 “리허설 스크립트”로 만들면 아래 순서가 기본형입니다.

1) (기존 클러스터에서) 교체 대상 멤버를 `member remove`
2) 새 노드를 `member add --learner`로 추가
3) 새 노드에서 etcd 프로세스를 “existing” 클러스터로 부팅
4) 동기화가 끝나면 promote

추상적으로 쓰면 의미가 없으니, 명령 형태로 남깁니다.

```bash
# 0) 교체 대상 멤버 ID 확인
etcdctl member list -w table

# 1) 멤버 제거 (예: dead member ID)
DEAD_ID=278c654c9a6dfd3b
etcdctl member remove ${DEAD_ID}

# 2) 신규 멤버 추가(learner)
# peer-urls는 신규 노드가 다른 멤버들에게 노출할 peer endpoint
NEW_NAME=etcd-4
NEW_PEER_URL=https://10.0.1.14:2380
etcdctl member add ${NEW_NAME} --learner --peer-urls=${NEW_PEER_URL}

# 출력으로 ETCD_INITIAL_CLUSTER 같은 환경변수를 안내해 주는 경우가 많습니다.
```

runtime reconfiguration이 “2단계(add 후 start)”라는 점은 runtime configuration 문서에 명시되어 있습니다.[^13]

이후 신규 노드에서 etcd를 띄울 때는 `--initial-cluster-state existing`으로 시작해야 하고, 데이터 디렉터리는 반드시 빈 상태여야 합니다(이 부분은 membership 관련 문서에도 경고로 반복됩니다).[^19]

리허설에서는 신규 노드가 “정상적으로 catch up”했는지 아래로 확인합니다.

- `endpoint status`에서 `raftIndex` / `raftAppliedIndex`가 다른 멤버와 수렴하는지
- learner 상태가 해제되었는지(promote 후 `IS LEARNER=false`)

## 스냅샷 백업 리허설: 업그레이드보다 ‘복구 가능성’을 먼저 확보하기

etcd 업그레이드 문서는 업그레이드 시작 전에 snapshot backup을 받아 두라고 강조합니다. mixed-version 상태에서는 바이너리만 되돌려 롤백할 여지가 있지만, “모든 멤버가 v3.7로 올라가면” 복구 옵션이 사실상 snapshot restore 또는 downgrade 가이드뿐이라고 선을 긋습니다.[^3]

Kubernetes 관점에서는 snapshot이 단순 백업이 아니라 “클러스터를 다시 세울 수 있는 유일한 재료”가 됩니다.

### snapshot을 어디서 뜰 것인가: 리더에서 뜨는 이유
업그레이드 문서의 예시는 “leader가 최신 application data를 보장하므로 leader에서 snapshot을 받아라”는 흐름으로 작성되어 있습니다.[^3]

리허설에서는 다음을 함께 확인합니다.

- 어떤 endpoint가 leader인지 확인(메트릭/endpoint status)
- leader로 스냅샷을 받는 경로가 실제로 동작

### snapshot save / snapshot status / 무결성 보관
DR 문서는 스냅샷을 `etcdctl snapshot save`로 뜨고, restore는 `etcdutl snapshot restore`로 한다는 흐름을 설명합니다(특히 v3.6부터 restore는 etcdutl 권장/필수로 흘러온다고 명시).[^12]

```bash
export ETCDCTL_API=3

SNAP_DIR=/var/backups/etcd
mkdir -p ${SNAP_DIR}
SNAP=${SNAP_DIR}/snapshot-$(date -u +%Y%m%dT%H%M%SZ).db

# 1) live snapshot
etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt \
  --key=/etc/kubernetes/pki/etcd/healthcheck-client.key \
  snapshot save ${SNAP}

# 2) snapshot 메타 확인 (오프라인)
etcdutl snapshot status ${SNAP} -w table

# 3) 파일 무결성(운영체제 레벨) 보관
sha256sum ${SNAP} > ${SNAP}.sha256
ls -lh ${SNAP} ${SNAP}.sha256
```

여기서 중요한 건 “스냅샷 파일만 있으면 된다”가 아니라, 복구 리허설에서 요구되는 입력(멤버 이름, peer URL, token, data-dir, bump 옵션 등)을 한 묶음으로 저장하는 것입니다.

나는 실제 운영에서 snapshot 파일만 남기고, restore 명령의 파라미터(초기 클러스터 문자열, token, URL)만 위키/런북에 흩어져 있던 팀이 DR 때 며칠을 태우는 걸 여러 번 봤습니다.

## 복구 리허설: Kubernetes에서 반드시 지켜야 하는 **bump-revision + mark-compacted**

etcd DR 문서는 Kubernetes를 직접 언급하면서, “restore로 revision이 과거로 돌아가면 watchers/informers 캐시가 꼬여서 예측 불가능한 동작이 나올 수 있다”는 점을 경고합니다. 그래서 revision regression을 피하는 방법으로 `--bump-revision`과 `--mark-compacted`를 권장합니다.[^12]

이건 단순 권고가 아니라, Kubernetes control plane을 생각하면 사실상 필수입니다.

### 복구는 ‘기존 클러스터를 살리는 작업’이 아니라 새 클러스터를 만드는 작업
DR 문서가 강조하는 핵심 중 하나는 “restore는 member ID/cluster ID를 덮어써서, 기존 클러스터에 잘못 붙는 걸 막는다”는 점입니다. 즉, **restore는 새 논리 클러스터를 만드는 작업**으로 보는 게 맞습니다.[^12]

따라서 리허설에서는 아래 2가지를 강제합니다.

- 복구용 `--initial-cluster-token`은 항상 새 값
- 기존 데이터 디렉터리를 절대 재사용하지 않음(완전 삭제 후 restore)

### 3노드 전체 복구 리허설 절차(개념)

1) 모든 API server / controller / scheduler / etcd 프로세스가 쓰기를 멈춘 상태 보장
2) snapshot 1개를 기준으로 3노드 각각에서 `etcdutl snapshot restore` 수행
3) 각 노드의 etcd를 같은 initial cluster 구성으로 부팅
4) health / status / member list 확인
5) Kubernetes가 올라오는지 확인(이 단계에서 informer/watch 문제는 뒤늦게 폭발할 수 있어 관찰 시간이 필요)

Kubernetes 환경별로 “정지 방법”은 다릅니다. kubeadm static Pod이면 매니페스트를 임시로 다른 디렉터리로 옮겨 kubelet이 pod를 내리게 하는 방식이 흔하고, managed 제품이면 vendor 문서를 따라야 합니다. Kubernetes 문서는 etcd를 운영/업그레이드하는 큰 그림과 defrag 관련 리소스를 제공합니다.[^20]

### 복구 명령 예시(현실적인 파라미터 포함)

아래는 “각 노드에서” 실행하는 restore 예시입니다. 핵심은 `--bump-revision`과 `--mark-compacted`를 함께 쓰는 것입니다.[^12]

```bash
SNAP=/var/backups/etcd/snapshot-20260925T000000Z.db

# 노드별로 name, peer url, data-dir은 다르게
NAME=cp-1
DATA_DIR=/var/lib/etcd-restored
PEER_URL=https://10.0.1.10:2380

# 3노드 공통으로 동일해야 하는 값들
TOKEN=etcd-restore-20260925
INITIAL_CLUSTER=cp-1=https://10.0.1.10:2380,cp-2=https://10.0.1.11:2380,cp-3=https://10.0.1.12:2380

rm -rf ${DATA_DIR}

etcdutl snapshot restore ${SNAP} \
  --name ${NAME} \
  --data-dir ${DATA_DIR} \
  --initial-advertise-peer-urls ${PEER_URL} \
  --initial-cluster ${INITIAL_CLUSTER} \
  --initial-cluster-token ${TOKEN} \
  --bump-revision 1000000000 \
  --mark-compacted
```

`--bump-revision`의 값은 “얼마나 bump할지”인데, DR 문서는 예시로 1,000,000,000을 들면서 “초당 쓰기량으로 일주일치 정도를 덮는다” 같은 감을 제공합니다.[^12]

복구 리허설에서 중요한 건 값 자체보다도, 팀이 “이 값은 운영 정책으로 고정한다”는 합의를 가지는 것입니다. 나는 보통 아래처럼 고정합니다.

- bump 값은 고정 상수(예: 1e9)
- 복구 시각/사고 티켓/훈련 회차가 token에 들어가게 함

이 두 줄이 실제 DR에서 사고 후 2시간을 줄입니다.

## compaction/defrag 리허설: 공간 문제는 ‘천천히 오다가 갑자기 터지는’ 형태로 온다

Kubernetes의 etcd는 workload가 커질수록 “삭제”가 “공간 반환”으로 이어지지 않는 구조 때문에 공간이 천천히 차오릅니다. etcd는 MVCC 히스토리를 유지하고, compaction으로 과거 revision을 정리하더라도, 파일 시스템 레벨의 공간 반환은 defrag가 필요합니다.

etcd 운영 문서는 compaction/defrag/스페이스 쿼터/알람을 하나의 maintenance 흐름으로 묶어 설명합니다. 특히 defrag는 아래 두 가지가 운영에서 가장 중요합니다.

- live member에서 defrag는 read/write를 block할 수 있음
- defrag 요청은 클러스터에 복제되지 않고, 멤버 로컬 작업임

이 문구는 etcd 문서/etcdctl 문서에 반복됩니다.[^21]

여기서 리허설 포인트는 “defrag를 실행해본다”가 아니라, defrag가 실제로 장애처럼 보이는 순간(지연/타임아웃)을 관찰하고, 이를 완화하는 운영 순서를 몸에 익히는 것입니다.

### 운영적으로 안전한 defrag 순서

1) (가능하면) 리더를 다른 멤버로 이동
2) follower에서 defrag
3) 다음 멤버로 이동

큰 데이터에서 defrag가 10~20초 이상 걸릴 수 있다는 사례와, 리더 이동 후 follower에서 defrag 하라는 조언은 discussions 형태로도 확인됩니다.[^17]

```bash
# 1) 리더 이동
etcdctl endpoint status --cluster -w table
etcdctl move-leader <target-member-id>

# 2) 특정 endpoint에만 defrag(멤버 로컬)
etcdctl --endpoints=https://10.0.1.11:2379 defrag

# 3) 다음 멤버로 반복
etcdctl --endpoints=https://10.0.1.12:2379 defrag
```

### compaction은 ‘정책’이고, defrag는 ‘작업’이다
compaction은 자동 정책(`--auto-compaction-mode`, `--auto-compaction-retention`)으로 들어가는 경우가 많고, defrag는 스케줄 작업(cronjob 등)으로 들어가는 경우가 많습니다.

etcd 설정 플래그는 문서에서 확인할 수 있습니다.[^22]

Kubernetes 문서도 defragmentation을 얘기하면서 etcd-defrag 같은 도구를 언급합니다.[^20]

리허설에서는 아래를 확인합니다.

- compaction retention이 너무 짧아 watch가 끊기는 패턴은 없는지
- defrag가 API server에 주는 영향(특히 list/watch 부하) 관찰
- defrag 윈도우(업무 시간 vs 새벽) 의사결정

## 성능 회귀 측정 리허설: “업그레이드 전/후 비교”를 숫자로 남기는 방법

업그레이드를 안전하게 하려면 “업그레이드 전 baseline”과 “업그레이드 후 baseline”이 있어야 합니다. 대부분의 팀은 지표 대시보드(Prometheus/Grafana)로 간접 확인만 하고 끝내는데, 나는 etcd 쪽은 `etcdctl check perf` 같은 도구를 함께 쓰는 걸 선호합니다.

`etcdctl check perf`는 etcdctl 커맨드 스펙(Go doc)에도 등재되어 있고, `--load` 모델(s/m/l/xl), `--auto-compact`, `--auto-defrag` 같은 옵션이 있음을 확인할 수 있습니다.[^23]

### 측정의 목표: “절대 성능”이 아니라 “회귀(regression) 탐지”

- 목표는 초당 몇 TPS를 달성하는 게 아니라
- 같은 환경에서 v3.7.1 → v3.7.2 업그레이드가 throughput/tail latency를 악화시키는지 보는 것입니다.

리허설에서는 다음 2가지를 고정합니다.

- 측정 시각과 cluster 상태(리더/팔로워 구성, 알람 여부)
- 측정 key prefix(기존 데이터와 섞지 않기)

### 실행 예시

```bash
export ETCDCTL_API=3
export ETCDCTL_ENDPOINTS="https://127.0.0.1:2379"
export ETCDCTL_CACERT=/etc/kubernetes/pki/etcd/ca.crt
export ETCDCTL_CERT=/etc/kubernetes/pki/etcd/healthcheck-client.crt
export ETCDCTL_KEY=/etc/kubernetes/pki/etcd/healthcheck-client.key

# 작은 부하 모델로 baseline을 잡고, 결과를 파일로 남깁니다.
etcdctl check perf \
  --load=s \
  --prefix="rehearsal/20260925/perf/" \
  --auto-compact=true \
  --auto-defrag=true | tee /var/log/etcd-perf-$(date -u +%Y%m%dT%H%M%SZ).log
```

이 커맨드는 “운영 클러스터에서 돌려도 되나?”라는 질문으로 이어지는데, 내 결론은 “프로덕션에서는 신중”입니다.

- 체크 자체가 write workload를 발생시키고
- auto-compact/auto-defrag는 실제 maintenance 작업을 트리거합니다

따라서 실제 프로덕션에서는 (a) staging에 최대한 비슷한 디스크/CPU/네트워크를 갖추거나, (b) 프로덕션에서는 피크 외 시간에 아주 작은 load로만 회귀 여부를 보는 방향이 안전합니다.

## v3.7.2 CHANGELOG 항목을 ‘운영 작업’으로 번역한 체크리스트

여기부터가 실제로 팀 런북에 붙일 수 있는 형태입니다.

### 1) `MinimalEtcdVersion`이 WAL에서 최신 snapshot entry를 읽도록 변경
CHANGELOG 문구만으로 “무엇이 어떻게 고쳐졌는지”까지 단정하기는 어렵습니다. 다만 이 변경이 recovery-path와 맞닿아 있다는 점은 분명합니다.[^2]

운영 작업으로 번역하면 다음입니다.

- 멤버 교체(learner 추가/동기화) 리허설을 반드시 포함해 “received snapshot / WAL” 경로를 실제로 밟아보기
- 업그레이드 전후로 snapshot save/restore를 수행해 “복구가 실제로 되는지”를 확인

여기서 중요한 건 “업그레이드 성공”이 아니라, 업그레이드 후에 snapshot/restore 리허설이 성공해야 한다는 점입니다.

### 2) “received snapshot db 저장 시 snap 디렉터리 fsync” 수정
이 변경도 정확히 어떤 장애를 막는지는 PR을 읽어야 하지만(이 글에서는 PR을 해석해 단정하지 않음), 운영 관점에서는 “스냅샷 수신/적용 시 durability 관련 버그 픽스일 가능성”을 염두에 둡니다.[^2]

운영 작업으로는 아래가 현실적입니다.

- 멤버 교체 시 learner 동기화가 스냅샷으로 넘어가는 시나리오를 일부러 만들어보기
  - 예: 신규 멤버를 느린 디스크/네트워크(traffic shaping) 환경에서 붙여 catch up을 어렵게 만들기
- 교체 중간에 프로세스 kill/restart로 “수신 중 스냅샷”의 실패 모드를 관찰

이 리허설은 staging에서만 하는 게 맞습니다.

### 3) `endpoint status --write-out=fields`의 `RaftTerm` 중복 수정
이건 운영 자동화에 즉시 영향이 있을 수 있습니다.

- fields 출력 파싱이 “RaftTerm이 2번 나온다”를 전제로 되어 있으면 깨짐
- 반대로 “중복이 사라져서” 더 정상화되는 방향이므로, 파서를 고치는 게 바람직

버그 리포트/CHANGELOG에 근거가 있습니다.[^15]

운영 작업으로 번역하면 아래 2가지입니다.

- `--write-out=fields`를 파싱하는 스크립트를 grep/jq 기반으로 재검증
- 가능하면 `-w json` 또는 `-w table` 기반으로 표준화(사람/머신 소비 분리)

`endpoint status`가 JSON 출력도 제공한다는 점은 etcdctl README에 포함됩니다.[^14]

### 4) Go 1.26.8, OTel/gRPC 의존성 업데이트(CVE 언급)
CHANGELOG에 CVE 번호가 붙은 의존성 업데이트가 들어갑니다. 이는 “지금 당장 기능이 필요해서”가 아니라 “보안/공급망 리스크를 줄이기 위해” 업그레이드가 필요한 트리거가 됩니다.[^2]

운영 작업으로 번역하면 다음입니다.

- 사내 보안 정책상 CVE 대응 SLA가 있으면, etcd 업그레이드가 SLA 항목에 들어가는지 확인
- 커스텀 빌드(임베드 등)를 하는 팀이면 Go toolchain 업데이트/재빌드 파이프라인 확인

### 5) per-arch Docker tag 폐지(CHANGELOG v3.7.0-rc.0)
이건 v3.7.2 변경이라기보다 v3.7 라인 전체의 artifact 정책입니다. 하지만 “패치 릴리스로 올라가다가 이미지 태그가 없어서 처음 깨지는 순간”은 v3.7.2 같은 시점에서 자주 옵니다.[^2]

운영 작업으로는 아래가 정답입니다.

- 이미지 참조에서 `-amd64` 같은 suffix tag 제거
- multi-arch manifest 기반 미러링으로 전환
- 미러 레지스트리/프록시가 manifest list를 제대로 다루는지 사전 검증

## 지금 시점(2026-09-25 KST)에 v3.7.2 리허설을 하는 이유를 운영 언어로 정리

- v3.7.2는 2026-09-22 릴리스된 패치이며, 서버의 recovery-path 관련 수정과 보안 의존성 업데이트를 포함합니다.[^2]
- per-arch Docker tag 폐지는 v3.7 라인의 artifact 정책 변화로, 표준 이미지 pin/미러링을 강하게 하는 팀의 CI/CD 파이프라인 실패 형태로 표면화됩니다.[^2]
- Kubernetes는 etcd 위에 강하게 결합된 컨트롤러/인포머 생태계를 얹고 있어서, 복구 시 revision regression을 피하기 위한 bump/mark 작업이 사실상 필수 운영 절차가 됩니다.[^12]

내 결론은 간단합니다. etcd v3.7.2 업그레이드를 “버전만 올리는 작업”으로 취급하면 사고가 나고, “멤버 교체 + 스냅샷/복구 + maintenance + 이미지 공급망”을 한 세트로 리허설하면 업그레이드 자체는 일상 작업이 됩니다.

## 참고 자료

- [CHANGELOG-3.7 (v3.7.2 포함)](https://github.com/etcd-io/etcd/blob/main/CHANGELOG/CHANGELOG-3.7.md)[^2]
- [etcd 패치 릴리스 공지(v3.7.2/v3.6.15/v3.5.34)](https://etcd.io/blog/2026/sep-21-patch-release/)[^1]
- [etcd v3.6 → v3.7 업그레이드 가이드](https://etcd.io/docs/v3.7/upgrades/upgrade_3_7/)[^3]
- [etcd Disaster recovery(스냅샷/복구, bump/mark 권고)](https://etcd.io/docs/v3.7/op-guide/recovery/)[^12]
- [Kubernetes: Operating etcd clusters for Kubernetes](https://kubernetes.io/docs/tasks/administer-cluster/configure-upgrade-etcd/)[^20]
- [Docker CLI: docker manifest](https://docs.docker.com/reference/cli/docker/manifest/)[^4]
- [etcd v3.7 Docker image deprecations 이슈(레지스트리/태그 정책 논의)](https://github.com/etcd-io/etcd/issues/20928)[^10]
- [registry.k8s.io 디버깅: crane/oras로 태그 확인](https://github.com/kubernetes/registry.k8s.io/blob/main/docs/debugging.md)[^5]
- [crane copy 문서(--platform 기본 all)](https://github.com/google/go-containerregistry/blob/main/cmd/crane/doc/crane_copy.md)[^6]
- [etcd runtime reconfiguration(멤버 추가/제거, learner 추가 언급)](https://etcd.io/docs/v3.4/op-guide/runtime-configuration/)[^13]
- [예전에 쓴 업그레이드 압박 관련 글](https://daewooki.github.io/posts/2025-12-kubernetesdocker-1/)

[^1]: <https://etcd.io/blog/2026/sep-21-patch-release/>
[^2]: <https://github.com/etcd-io/etcd/blob/main/CHANGELOG/CHANGELOG-3.7.md>
[^3]: <https://etcd.io/docs/v3.7/upgrades/upgrade_3_7/>
[^4]: <https://docs.docker.com/reference/cli/docker/manifest/>
[^5]: <https://github.com/kubernetes/registry.k8s.io/blob/main/docs/debugging.md>
[^6]: <https://github.com/google/go-containerregistry/blob/main/cmd/crane/doc/crane_copy.md>
[^7]: <https://oras.land/docs/commands/oras_repo_tags/>
[^8]: <https://github.com/etcd-io/etcd/issues/13606>
[^9]: <https://github.com/etcd-io/etcd/releases>
[^10]: <https://github.com/etcd-io/etcd/issues/20928>
[^11]: <https://kubernetes.io/docs/reference/setup-tools/kubeadm/kubeadm-init/>
[^12]: <https://etcd.io/docs/v3.7/op-guide/recovery/>
[^13]: <https://etcd.io/docs/v3.4/op-guide/runtime-configuration/>
[^14]: <https://github.com/etcd-io/etcd/blob/main/etcdctl/README.md?plain=1>
[^15]: <https://github.com/etcd-io/etcd/issues/22207>
[^16]: <https://github.com/etcd-io/etcd/blob/main/etcdctl/ctlv3/command/move_leader_command.go>
[^17]: <https://github.com/etcd-io/etcd/discussions/20961>
[^18]: <https://etcd.io/docs/v3.3/learning/learner/>
[^19]: <https://etcd.io/docs/v3.8/tasks/operator/how-to-deal-with-membership/>
[^20]: <https://kubernetes.io/docs/tasks/administer-cluster/configure-upgrade-etcd/>
[^21]: <https://etcd.io/docs/v3.3/op-guide/maintenance/>
[^22]: <https://etcd.netlify.app/docs/v3.7/op-guide/configuration/>
[^23]: <https://pkg.go.dev/go.etcd.io/etcd/etcdctl/v3>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
