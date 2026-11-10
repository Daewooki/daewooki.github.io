---
title: "Cloudflare targeted zone builds에서 배우는 Kafka 커밋과 스케줄러 분리"
description: "이벤트 의미 기반 부분 빌드와 soft committing을 분리해 tail latency를 깎는 설정 전파 파이프라인 패턴을 정리합니다."
date: 2026-11-10 15:51:05 +0900
categories: ["Networking", "Kafka"]
tags: ["cloudflare", "dns", "kafka", "offset-commit", "scheduler", "config-propagation"]
render_with_liquid: false
---

## 왜 DNS zone build는 느려지기 쉬운가

Cloudflare가 2026년 11월 2일에 공개한 글에서 재미있었던 지점은, 문제의 중심이 단순한 처리량이 아니라 “어떤 이벤트가 어떤 규모의 작업을 강제하는가”였다는 점입니다. Zone Builder가 받는 이벤트 수는 늘었지만(2022년 대비 record change 기준 약 250/s → 약 700/s, 그 외 이벤트 약 100/s), 더 중요한 건 일부 이벤트가 zone 전체를 다시 읽고 다시 인코딩하게 만드는 구조였습니다. 게다가 일부 zone이 2천만 레코드를 넘고, 장기적으로 수억 레코드까지 커질 수 있다는 전제가 붙으면서, “가끔 full build가 느린 것”이 아니라 “full build라는 개념 자체가 특정 규모 이상에서 불가능해지는 것”으로 바뀝니다.[^1]

대규모 설정 전파 파이프라인에서도 비슷한 문제가 자주 나옵니다.

- 이벤트가 의미를 잃고 “뭔가 바뀜”만 전달되면, 안전을 위해 full recompute로 후퇴합니다.
- full recompute가 느려지면, Kafka partition의 committed offset이 오래 막히고, tail latency가 폭발합니다.
- tail이 폭발하면 운영팀은 buffer를 늘리고, batching을 넣고, backoff를 늘리는데, 이게 다시 latency를 키웁니다.

Cloudflare의 글은 이 악순환을 **부분 빌드**와 **soft committing**을 각각 독립된 책임으로 분리해 끊어냈다는 점이 핵심입니다.[^1]

내 블로그에서 Cloudflare 장애/복원력 이야기를 다뤘던 글들(예: [Cloudflare IAD 성능 이슈가 전 서비스 에러로 번지는 패턴](https://daewooki.github.io/posts/cloudflare-iad-incident-resilience/), [Cloudflare R2 503 장애 대응: 객체 스토리지 의존성 분해](https://daewooki.github.io/posts/r2-503-outage-app-resilience-patterns/))은 “터질 때 어떻게 전파되나”에 더 가까웠는데, 이번 건 “평시에 어떻게 tail을 깎아두나” 쪽이라 운영 체감이 다릅니다.

## 이벤트 의미를 복원해서 작업 범위를 증명하기

Cloudflare가 먼저 건드린 건 planner입니다. 기존 Zone Builder는 “왜 바뀌었는지 몰라도 DB에서 desired state를 다시 만들면 된다”는 장점이 있었지만, 그 장점이 규모가 커지면 그대로 비용 폭탄이 됩니다. 그래서 이벤트 생산자를 바꿔서 “무엇이 바뀌었는지”를 가능한 한 이벤트에 포함시키고, 그 변경이 Quicksilver 출력에 어떤 영향을 주는지 tracing해서 분류했다고 합니다.[^1]

여기서 중요한 운영 감각이 하나 있습니다. 이벤트가 충분히 구체적이지 않으면 planner는 결코 일을 줄여주지 않습니다. Cloudflare 글에서도 timestamp-only update(사실상 “뭔가 바뀜”)는 끝까지 full build로 간다고 명시합니다. “불확실성을 비용 절감으로 바꾸지 않는다”는 원칙이 correctness를 지키는 쪽으로 강하게 기울어 있습니다.[^1]

이 원칙을 내 시스템에 적용하면, 이벤트 스키마는 보통 다음 두 가지를 분리해서 갖게 됩니다.

- change set: 어떤 필드/어떤 리소스 key가 바뀌었는가
- provenance: 어떤 호출자/어떤 경로에서 바뀌었는가(의미가 달라지는 경우가 많습니다)

Cloudflare는 “호출자를 아직 식별할 수 없으면 full build”로 후퇴한다고 했는데, 이건 이벤트 기반 시스템에서 특히 중요합니다. 같은 DB row update라도, 어떤 서비스가 왜 건드렸는지에 따라 전파해야 하는 edge state가 달라지는 경우가 실제로 많습니다.

## Record key와 metadata key를 분리하면 planner가 단순해진다

Cloudflare의 targeted build가 작동하는 구조적 이유는 Quicksilver 출력이 두 층으로 나뉘어 있기 때문입니다.

- record keys: (zone, name)에 대한 DNS answer
- shared metadata key: authoritative server가 zone을 어떻게 해석할지에 대한 디렉터리성 정보(예: nameserver, wildcard 등)[^1]

이 구분 덕분에 planner는 “가장 작은 안전한 빌드 타입”을 5개 중 하나로 선택할 수 있습니다.

1) Resources only: 특정 DNS name(resource)만 rebuild
2) Resources and metadata: 특정 name + metadata
3) Apex and metadata: apex + metadata
4) Purge: zone 제거
5) Full zone: 전체 rebuild

그리고 규칙을 하나로 고정합니다. **byte-for-byte 동치**: targeted build가 쓰는 모든 key는 full build가 썼을 결과와 바이트 단위로 동일해야 한다. 증명할 수 없으면 full build로 간다.[^1]

이 “동치” 규칙은 설계의 나침반 역할을 합니다. 최적화가 아니라 증명 게임으로 바뀌기 때문입니다.

- 최적화 관점: “아마 이 정도면 되겠지”
- 증명 관점: “full build와 같다는 것을 어떻게 확인할 수 있나”

대규모 설정 전파에서 planner를 안정적으로 만들려면, 보통 여기까지 밀어붙여야 합니다. 그렇지 않으면 운영 중에 예외가 쌓일수록 planner는 복잡해지고, 결국 특정 이벤트는 영원히 full rebuild로 남습니다.

## 같은 이름이 여러 zone ID를 가질 때: 공유 메타데이터의 위험 구간

Cloudflare가 흥미롭게 다룬 코너 케이스는 “같은 domain name에 여러 zone object가 잠시 공존할 수 있다”는 점입니다. 온보딩/오프보딩/라이프사이클 변화 동안 내부적으로 여러 zone ID가 존재하고, shared metadata key가 “현재 publish할 후보 zone ID 목록”을 디렉터리처럼 담는다고 설명합니다.[^1]

이런 구조에서는 targeted build가 쉬워 보이는 리소스 변경도, 메타데이터와의 순서 관계를 잘못 다루면 edge가 잘못된 zone을 참조할 수 있습니다. Cloudflare는 실행 시점에 최신 후보 목록을 다시 읽고, metadata key를 patch가 아니라 fresh view에서 재구성하며, “records를 먼저 쓰고 metadata를 나중에 쓴다”고 명시합니다.[^1]

설정 전파 파이프라인에서 자주 등장하는 패턴으로 바꾸면 이렇게 됩니다.

- per-tenant keyspace(레코드)
- shared directory key(라우팅/선택/우선순위)

이때 디렉터리 key 업데이트는 대부분 원자적 patch가 아니라 “지금 시점의 전체 재계산”이 안전합니다. 이유는 레이스가 너무 많기 때문입니다(후보가 늘고 줄고, 우선순위가 바뀌고, 일부 환경에만 publish되고 등). Cloudflare는 “planning을 두 번 한다”는 형태로 이를 흡수합니다.[^1]

## DB replica lag와 Kafka 전달은 독립이다

이 문장은 Kafka 기반 전파 파이프라인을 운영하는 팀이 반드시 가져가야 합니다.

> Kafka delivery and database replication move independently.

Cloudflare는 이벤트가 replica에 반영되기 전에 도착할 수 있다고 명시하고, DNS Kafka Aggregator가 이벤트를 지연시켜 정상적인 lag를 커버한 뒤, 마지막에 replica가 여전히 뒤처졌으면 read를 reject한다고 설명합니다.[^1]

이건 “이벤트가 truth가 아니다”를 시스템적으로 박는 방식입니다.

- 이벤트는 트리거
- truth는 DB snapshot
- snapshot이 준비되지 않았으면 실패/재시도

이 구조를 넣지 않으면, targeted build는 오히려 위험해집니다. 작업 범위를 줄였는데 읽은 데이터는 이전 버전이면, 잘못된 부분만 빠르게 전파하는 꼴이 됩니다.

## 스케줄러 통합: 작업 병합과 tail latency의 관계

Cloudflare는 record work와 full-zone work가 서로 다른 scheduler에 있었고, 서로의 작업을 합칠 수 없었다고 합니다. planner는 “무엇을”을, scheduler는 “언제”를 결정한다는 경계도 명확히 잡습니다.[^1]

통합 스케줄러는 (zone 기준으로) 큐에 쌓인 이벤트들을 병합합니다. 예시로 A record 변경과 wildcard 변경이 같이 오면 name set과 metadata update를 합쳐 하나의 build로 만든다고 설명합니다.[^1]

여기서 안전장치가 하나 있습니다.

- merging은 “work를 줄이지 않는다”, 오직 추가만 한다.
- 어떤 이벤트라도 full zone이 필요하면 합쳐진 작업은 full로 escalates.
- purge는 모든 rebuild를 덮어쓴다.[^1]

이 형태는 대규모 설정 전파에서 흔한 “coalescing”과 유사하지만, 중요한 차이가 있습니다. Cloudflare는 **작업(work)**과 **Kafka 메시지 ack 대기열**을 따로 추적한다고 못 박습니다. 재시도는 둘 다 보존하고, 결과가 안전하게 쓰일 때까지 메시지는 작업에 붙어 있다고 합니다.[^1]

즉, 병합은 “메시지를 버리거나 덮어쓰기”가 아니라 “여러 메시지가 하나의 실행 결과로 귀결되도록 연결”하는 설계입니다.

## full build를 없애지 않은 이유, 그리고 ‘불가능한 full build’의 예외 처리

Cloudflare는 2022년에 full build를 제거하겠다고 했지만, 2026년 시점에서는 “비현실적이고 유용하지 않다”고 결론 내립니다. 최초 publish 같은 경우는 full이 필요합니다.[^1]

그런데 더 중요한 문장이 따로 있습니다.

- 특정 record-count threshold를 넘으면 full build로 escalate하지 않겠다고 합니다.
- 이유는 단순합니다. full build가 메모리에 안 올라가서 끝나지 못하고 retry하면서 Kafka partition을 오래 막기 때문입니다.
- 그래서 그 구간에서는 apex, metadata, queued events가 가리킨 name만 rebuild하는 쪽을 선택합니다.[^1]

이건 correctness 관점에서 불편한 선택입니다. 원칙(증명할 수 없으면 full)에서 벗어나는 예외이기 때문입니다. Cloudflare는 그 예외를 “full이 물리적으로 불가능한 상황에서의 tradeoff”로 설명합니다.[^1]

대규모 전파 파이프라인에서 이 구간은 생각보다 자주 옵니다.

- full recompute가 비싸서 느린 게 아니라 아예 끝나지 못함
- 끝나지 못하니 커밋이 막힘
- 커밋이 막히니 replay 비용이 기하급수로 증가

이 단계로 가기 전에 targeted build로 넘어가는 게 이상적이지만, 이미 늦었다면 Cloudflare처럼 “예외를 설계하고 운영적으로 커버”해야 합니다.

## Kafka offset 커밋을 correctness로 묶는 법: 완료는 out-of-order, 커밋은 in-order

Cloudflare가 말하는 “Keeping Kafka moving”의 요점은 아주 단순합니다.

- Kafka는 partition별로 ordered이고, committed offset은 “이 지점 이전의 메시지는 모두 완료”라는 의미입니다.[^1]
- 완료되지 않은 일을 건너뛰고 offset을 앞으로 당기면, 재시작 후 그 메시지가 영원히 재처리되지 않아 변경이 유실될 수 있습니다.[^1]

Cloudflare는 이를 soft committing이라고 부르고, out-of-order로 끝난 작업은 메모리에 완료 표시만 하고, committed position은 “가장 오래된 미완료가 끝날 때까지” 전진하지 않는다고 설명합니다.[^1]

이 패턴은 Cloudflare의 Secondary DNS deep dive에서 더 구체적입니다. offset 정렬된 리스트를 유지하고, 작업이 끝나도 즉시 commit하지 않으며, 리스트에서 가장 오래된(가장 낮은 offset) 메시지가 끝났을 때만 그 offset을 커밋하라는 알고리즘을 제시합니다.[^2]

그리고 이 방식이 분산 환경에서 성립하려면 메시지가 zone id로 keying되어 같은 zone이 같은 consumer로 가야 한다고까지 조건을 답니다.[^2]

### 왜 이게 “스케줄러 분리”로 읽혀야 하나

겉으로 보면 soft committing은 Kafka consumer 쪽 구현 디테일인데, 실제로는 scheduler 설계입니다.

- worker는 out-of-order로 완료할 수 있습니다(동시성).
- scheduler는 out-of-order 완료를 수용하면서도, commit은 순서를 유지해야 합니다(correctness).
- commit이 막힌 상태가 길어지면 partition replay 비용이 늘어나므로, scheduler는 “가장 오래된 미완료를 빨리 끝내는 방향”으로 시스템 전체를 압박합니다.

Cloudflare 글에서도 targeted plans가 “oldest message가 unfinished로 남는 시간을 줄인다”고 직접 연결합니다.[^1]

결국 planner(작업 범위 축소)가 commit 막힘을 줄이고, scheduler(통합/공정성)가 commit 막힘의 tail을 줄입니다.

### Kafka 트랜잭션/Exactly-once와의 관계

여기서 흔히 나오는 질문은 “그럼 Kafka transaction으로 offset commit과 결과 쓰기를 묶으면 되지 않나”입니다.

Kafka 설계 문서에서도 consumer position(커밋된 offset)을 internal topic에 쓰고, output topic write와 같은 transaction에 묶을 수 있다는 설명이 있습니다.[^3]

다만 Cloudflare의 케이스는 output이 Kafka topic이 아니라 Quicksilver(별도 KV store)입니다. 그러면 Kafka transaction이 제공하는 원자성 범위 밖으로 나갑니다. 이때 현실적인 선택지는 보통 셋 중 하나입니다.

1) 외부 저장소에 idempotency key를 두고 at-least-once를 운영한다.
2) 외부 저장소 write-ahead / compare-and-swap 기반으로 효과적 exactly-once를 만든다.
3) Kafka commit을 늦추고 replay를 허용해서 “유실 대신 중복”을 선택한다.

Cloudflare는 명시적으로 3)을 택합니다. Zone Builder가 재시작되면 in-memory completion이 사라져 메시지 2..n을 replay하고, 변경 유실 대신 반복 작업을 택한다고 설명합니다.[^1]

이게 맞는 선택인 이유는 DNS 전파의 본질 때문입니다.

- “같은 desired state를 한 번 더 쓰는 것”은 대체로 안전합니다(멱등).
- “한 번 써야 할 desired state를 영원히 안 쓰는 것”은 장애입니다.

## 대규모 설정 전파 파이프라인 패턴으로 추출하기

Cloudflare의 targeted zone builds를 일반화하면, 설정 전파 파이프라인은 보통 3계층으로 나뉩니다.

1) Event normalization + Planner
- 이벤트에서 의미를 끄집어내고(work item으로 정규화)
- uncertainty가 있으면 비용이 아니라 correctness를 택해 full로 후퇴[^1]

2) Work Scheduler
- zone(또는 tenant, shard key) 단위로 coalescing
- 공정성: 한 zone이 worker를 독점하지 못하게 제약
- backlog와 commit 막힘을 고려해 “오래된 미완료를 방치하지 않기”[^1]

3) Executor + Commit gate
- build 실행은 out-of-order 허용
- commit은 in-order로만 전진(soft committing)
- crash/restart 시 replay를 허용하고, 유실을 금지[^1]

이때 시스템이 지켜야 할 불변조건을 문장으로 고정해두면 설계가 단단해집니다.

- (동치) targeted build 결과는 full build 결과와 동일해야 한다.[^1]
- (순서) committed offset k는 “<=k인 메시지의 효과가 모두 반영됨”을 의미해야 한다.[^1]
- (복구) crash 후 replay가 생겨도 변경 유실은 없어야 한다.[^1]
- (공유키) shared metadata key는 patch가 아니라 최신 스냅샷으로 재구성해야 한다.[^1]

Cloudflare가 릴리스 안전장치로 mirror Zone Builder를 운영한 것도(프로덕션 Kafka/DB를 읽되 별도 Quicksilver로 쓰고 diff) 결국 첫 번째 불변조건(동치)을 운영 환경에서 지속 검증하기 위한 장치입니다.[^1]

## 동작하는 예시 코드: Soft-commit 스케줄러와 부분 빌드 플래너

아래 코드는 Kafka 클러스터 없이도 “offset commit correctness”와 “작업 병합”이 어떻게 붙는지 재현할 수 있게 만든 로컬 시뮬레이터입니다.

- 언어: Go 1.23+ (표준 라이브러리만 사용)
- 실행 결과: out-of-order 완료가 발생해도 commit은 연속 구간만 전진
- crash 시나리오: in-memory completion이 사라지면 replay가 발생(유실 대신 중복)

### 파일 1) `go.mod`

```go
module example.com/softcommit

go 1.23
```

### 파일 2) `main.go`

```go
package main

import (
	"context"
	"fmt"
	"math/rand"
	"sort"
	"sync"
	"time"
)

type ZoneID string

type EventKind int

const (
	EventDNSRecordChanged EventKind = iota
	EventWildcardChanged
	EventSettingChanged
	EventUnknown // forces full
)

type Event struct {
	Partition int
	Offset    int64
	Zone      ZoneID
	Kind      EventKind
	Names     []string // resources
}

type BuildType int

const (
	BuildResourcesOnly BuildType = iota
	BuildResourcesAndMetadata
	BuildApexAndMetadata
	BuildPurge
	BuildFull
)

type Work struct {
	Zone      ZoneID
	BuildType BuildType
	Names     map[string]struct{}
	NeedMeta  bool
	// Messages (offsets) attached to this work. We must not "lose" them.
	Offsets []int64
}

func (w *Work) mergeFrom(other Work) {
	// Merging only adds work. Purge overrides everything.
	if other.BuildType == BuildPurge {
		*w = other
		return
	}
	if w.BuildType == BuildPurge {
		return
	}

	// If any side is full, result is full.
	if w.BuildType == BuildFull || other.BuildType == BuildFull {
		w.BuildType = BuildFull
		w.NeedMeta = true
		w.Names = map[string]struct{}{}
	}

	// Otherwise widen: metadata requirement sticks.
	w.NeedMeta = w.NeedMeta || other.NeedMeta
	for n := range other.Names {
		w.Names[n] = struct{}{}
	}

	w.Offsets = append(w.Offsets, other.Offsets...)
	sort.Slice(w.Offsets, func(i, j int) bool { return w.Offsets[i] < w.Offsets[j] })
}

// Planner: "smallest provably safe" in real systems means
// falling back to full when uncertain.
func plan(e Event) Work {
	w := Work{
		Zone:    e.Zone,
		Names:   map[string]struct{}{},
		Offsets: []int64{e.Offset},
	}

	switch e.Kind {
	case EventDNSRecordChanged:
		w.BuildType = BuildResourcesOnly
		for _, n := range e.Names {
			w.Names[n] = struct{}{}
		}
		w.NeedMeta = false
	case EventWildcardChanged:
		w.BuildType = BuildResourcesAndMetadata
		for _, n := range e.Names {
			w.Names[n] = struct{}{}
		}
		w.NeedMeta = true
	case EventSettingChanged:
		w.BuildType = BuildApexAndMetadata
		w.Names["@"]=struct{}{}
		w.NeedMeta = true
	case EventUnknown:
		w.BuildType = BuildFull
		w.NeedMeta = true
	default:
		w.BuildType = BuildFull
		w.NeedMeta = true
	}

	return w
}

type SoftCommit struct {
	mu sync.Mutex

	// The next offset we want to commit ("committed position" in Kafka terms is next-1).
	next int64

	// completed offsets >= next, may be sparse.
	completed map[int64]struct{}
}

func NewSoftCommit(startOffset int64) *SoftCommit {
	return &SoftCommit{next: startOffset, completed: map[int64]struct{}{}}
}

func (sc *SoftCommit) MarkDone(offset int64) (advancedTo int64, advanced bool) {
	sc.mu.Lock()
	defer sc.mu.Unlock()

	sc.completed[offset] = struct{}{}

	// Advance only contiguous segment.
	for {
		if _, ok := sc.completed[sc.next]; !ok {
			break
		}
		delete(sc.completed, sc.next)
		sc.next++
		advanced = true
	}
	return sc.next, advanced
}

func (sc *SoftCommit) Committed() int64 {
	sc.mu.Lock()
	defer sc.mu.Unlock()
	return sc.next - 1
}

type Scheduler struct {
	mu sync.Mutex

	queued map[ZoneID]Work
	inflight map[ZoneID]struct{}

	soft *SoftCommit
}

func NewScheduler(startOffset int64) *Scheduler {
	return &Scheduler{
		queued:   map[ZoneID]Work{},
		inflight: map[ZoneID]struct{}{},
		soft:     NewSoftCommit(startOffset),
	}
}

func (s *Scheduler) Enqueue(w Work) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if old, ok := s.queued[w.Zone]; ok {
		old.mergeFrom(w)
		s.queued[w.Zone] = old
		return
	}
	s.queued[w.Zone] = w
}

func (s *Scheduler) PickNext() (Work, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	// naive policy: pick any zone not inflight, prefer "older" by min offset attached.
	var (
		pickedZone ZoneID
		picked     Work
		found      bool
		bestMin    int64
	)

	for zid, w := range s.queued {
		if _, busy := s.inflight[zid]; busy {
			continue
		}
		minOff := w.Offsets[0]
		if !found || minOff < bestMin {
			pickedZone = zid
			picked = w
			bestMin = minOff
			found = true
		}
	}
	if !found {
		return Work{}, false
	}

	delete(s.queued, pickedZone)
	s.inflight[pickedZone] = struct{}{}
	return picked, true
}

func (s *Scheduler) Done(w Work) (committed int64, advanced bool) {
	s.mu.Lock()
	delete(s.inflight, w.Zone)
	s.mu.Unlock()

	// Mark all offsets attached to the work as done.
	// In real systems, we might want to mark only when the external write is durable.
	for _, off := range w.Offsets {
		if next, adv := s.soft.MarkDone(off); adv {
			committed = next - 1
			advanced = true
		}
	}
	if !advanced {
		committed = s.soft.Committed()
	}
	return committed, advanced
}

func simulateBuild(w Work) {
	// Make "full" slower.
	sleep := 30 * time.Millisecond
	if w.BuildType == BuildFull {
		sleep = 250 * time.Millisecond
	}
	if w.BuildType == BuildPurge {
		sleep = 10 * time.Millisecond
	}
	// Add jitter.
	sleep += time.Duration(rand.Intn(80)) * time.Millisecond
	time.Sleep(sleep)
}

func main() {
	rand.Seed(7)
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	events := []Event{
		{Partition: 0, Offset: 1, Zone: "zoneA", Kind: EventDNSRecordChanged, Names: []string{"www"}},
		{Partition: 0, Offset: 2, Zone: "zoneB", Kind: EventUnknown},                // slow full
		{Partition: 0, Offset: 3, Zone: "zoneA", Kind: EventWildcardChanged, Names: []string{"*"}},
		{Partition: 0, Offset: 4, Zone: "zoneC", Kind: EventDNSRecordChanged, Names: []string{"api"}},
		{Partition: 0, Offset: 5, Zone: "zoneA", Kind: EventSettingChanged},
		{Partition: 0, Offset: 6, Zone: "zoneC", Kind: EventDNSRecordChanged, Names: []string{"app"}},
	}

	s := NewScheduler(1)

	for _, e := range events {
		s.Enqueue(plan(e))
	}

	var wg sync.WaitGroup
	workers := 3

	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			for {
				select {
				case <-ctx.Done():
					return
				default:
				}

				w, ok := s.PickNext()
				if !ok {
					time.Sleep(5 * time.Millisecond)
					continue
				}

				fmt.Printf("worker=%d start zone=%s type=%v offsets=%v names=%d meta=%v\n",
					id, w.Zone, w.BuildType, w.Offsets, len(w.Names), w.NeedMeta)
				simulateBuild(w)
				committed, adv := s.Done(w)
				if adv {
					fmt.Printf("worker=%d done  zone=%s committed_offset=%d\n", id, w.Zone, committed)
				} else {
					fmt.Printf("worker=%d done  zone=%s committed_offset=%d (no-advance)\n", id, w.Zone, committed)
				}
			}
		}(i)
	}

	wg.Wait()
	fmt.Printf("final committed offset=%d\n", s.soft.Committed())
}
```

### 실행

```bash
go run .
```

### 예상 출력(형태)

실행할 때마다 worker 스케줄링이 약간 달라질 수 있지만 핵심 패턴은 같습니다.

- offset=2(unknown → full)가 느리게 끝나서 commit이 1에서 오래 멈춥니다.
- offset=3,4,5,6이 먼저 끝나도 “완료 표시만” 되고 commit은 안 움직입니다.
- offset=2가 끝나는 순간 commit이 연속 구간으로 한 번에 전진합니다.

예를 들어 아래처럼 보입니다.

```text
worker=0 start zone=zoneA type=0 offsets=[1] names=1 meta=false
worker=1 start zone=zoneB type=4 offsets=[2] names=0 meta=true
worker=2 start zone=zoneC type=0 offsets=[4] names=1 meta=false
worker=0 done  zone=zoneA committed_offset=1
worker=0 start zone=zoneA type=1 offsets=[3] names=1 meta=true
worker=2 done  zone=zoneC committed_offset=1 (no-advance)
worker=2 start zone=zoneA type=2 offsets=[5] names=1 meta=true
...
worker=1 done  zone=zoneB committed_offset=6
final committed offset=6
```

이 시뮬레이터는 Cloudflare가 말한 “완료는 out-of-order 가능, commit은 앞의 미완료가 끝나야 전진”이라는 soft committing의 본질을 그대로 보여줍니다.[^1]

## out-of-order 완료/재시도/롤백을 어떻게 테스트할 것인가

Cloudflare는 테스트 전략을 상당히 공격적으로 잡습니다.

- targeted vs full을 같은 DB state에서 실행하고, time-dependent 값을 pinning한 뒤, Quicksilver key를 byte-for-byte 비교합니다.[^1]
- 롤아웃 중에는 targeted build 옆에 full build를 붙여서 비교(비싸지만 의도적으로)합니다.[^1]
- 그 다음 단계로 mirror Zone Builder(프로덕션 Kafka/DB를 읽고 별도 Quicksilver로 씀)로 지속 검증합니다.[^1]

이 접근을 “내 시스템”으로 가져오려면, 테스트를 3겹으로 나누는 게 현실적이었습니다.

### 1) 단위 테스트: soft commit 불변조건을 상태 기계로 고정

soft commit 로직은 분산 시스템 전체에서 가장 치명적인 버그(변경 유실)를 유발할 수 있는데, 반대로 입력/출력이 단순해서 단위 테스트로 상당 부분 막을 수 있습니다.

체크해야 하는 건 간단합니다.

- committed offset은 절대 감소하면 안 됩니다.
- committed offset이 k가 됐으면, 1..k는 모두 완료된 상태여야 합니다.
- out-of-order 완료를 넣어도 “가장 낮은 미완료 offset”이 막는 동안은 commit이 전진하면 안 됩니다.

내 경험상, 이 레벨에서 실패하는 구현이 생각보다 많습니다. 특히 “작업 병합”을 하면서 offset을 여러 개 한 번에 처리할 때 실수합니다(일부 offset만 완료됐는데 묶어서 commit해버리는 형태).

### 2) 시뮬레이션 테스트: crash/restart를 인위적으로 섞기

Cloudflare가 말한 위험은 명확합니다.

- in-memory completion이 사라지면 replay가 된다.
- replay는 괜찮지만, commit을 앞질러 유실이 나면 끝이다.[^1]

그래서 시뮬레이터에는 다음 fault를 주기적으로 주입합니다.

- worker goroutine 강제 종료(실제론 pod kill에 해당)
- scheduler가 들고 있던 completed set 초기화(메모리 상태 소실)
- 마지막 committed offset부터 이벤트를 다시 enqueue(replay)

그리고 아래를 assertion으로 둡니다.

- replay 후에도 최종 state가 같아야 함(멱등성/동치성)
- replay 과정에서 commit이 건너뛰지 않아야 함

Cloudflare가 “반복 작업을 의도적으로 선택”했다는 문장은, 이 테스트가 통과할 때만 의미가 있습니다.[^1]

### 3) 분산 검증 프레임워크: Jepsen과 선형화 검사 도구를 빌려쓰기

이 단계는 시스템이 커질수록 비용이 올라가지만, “운 좋게 지나간다”를 막아줍니다.

- Jepsen은 실제 바이너리를 대상으로 fault injection을 걸고, operation history를 수집/검증하는 프레임워크입니다.[^4]
- Porcupine은 Go로 작성된 빠른 linearizability checker로, concurrent history가 선형화 가능한지 검사하는 도구입니다.[^5]

설정 전파 파이프라인에 linearizability를 그대로 요구하긴 어렵지만, 최소한 다음 같은 “부분 선형화”는 적용할 수 있습니다.

- (commit gate) offset commit 연산이 “완료된 작업들의 prefix만 커밋”한다는 사양을 만족하는가
- (directory key) metadata key 업데이트가 “항상 최신 후보 집합을 기반으로 재구성”된 것으로 설명 가능한가

Jepsen을 곧바로 적용하기 어렵다면, Cloudflare가 했던 mirror 검증이 사실상 “production traffic 기반의 differential testing”이라서 상당히 좋은 대체재가 됩니다.[^1]

## 반론과 회의론: targeted build가 어려운 이유

Cloudflare 글을 그대로 따라 하면 된다는 이야기는 아닙니다. 오히려 targeted build는 시스템을 더 복잡하게 만들 가능성이 큽니다.

1) 이벤트 의미를 복원하는 비용
- “무엇이 바뀌었는지”를 이벤트로 보내려면, 호출자와 데이터 경로를 정리해야 합니다.
- 레거시 시스템에서는 DB trigger처럼 의미가 증발한 이벤트가 많습니다.
- Cloudflare도 timestamp-only update를 끝까지 full로 보냅니다.[^1]

2) 공유 메타데이터의 존재
- record만 바뀌는 세계에서는 targeted build가 단순합니다.
- shared directory key가 있으면 planner와 scheduler가 같은 shard key로 정렬되어야 합니다(Cloudflare도 zone name hash로 롤아웃해, 같은 이름은 같은 scheduler로 묶었다고 설명).[^1]

3) “동치” 검증의 비용
- byte-for-byte 비교는 구현 난이도가 아니라 운영 비용이 문제입니다.
- Cloudflare는 비교를 위해 mirror 환경까지 만들고 20% 샘플을 돌립니다.[^1]

이 정도까지 못 가면, targeted build는 오히려 위험합니다. 부분만 바꾸는 시스템에서 가장 무서운 건 “조금씩 틀린 상태가 오래 남는 것”입니다.

## 이 패턴을 적용할지 판단할 때 보는 지표

내 경우, Kafka 기반 전파 파이프라인에서 아래 3개가 동시에 관측되면 “planner/scheduler/commit gate 분리”를 진지하게 고려합니다.

- partition별 lag가 평균이 아니라 p99에서 급격히 튄다(느린 작업이 commit을 막는 구조).
- full recompute가 더 이상 안정적인 fallback이 아니다(메모리/시간 상한을 넘는다).
- 이벤트가 의미를 잃고 “변경됨”만 남아, safe를 이유로 full로 계속 후퇴한다.

Cloudflare의 수치도 이 조합을 잘 보여줍니다.

- build completion delay의 중앙값이 약 7.7s → 약 3.3s로 감소했고, p99 tail은 대체로 27s 근처에 남아있다고 합니다.[^1]
- 더 결정적으로 24시간 구간에서 p99 스파이크가 14.6분 → 1.21분으로 줄었다고 제시합니다(로그 스케일 차트).[^1]
- working-set 메모리가 평균 49GiB → 7GiB로 줄고, peak도 79GiB → 12GiB로 줄었다고 합니다.[^1]

이 숫자들은 “조금 더 빠른 최적화”가 아니라, 운영 모드 자체가 바뀐 결과로 읽히는 게 맞습니다.

- full build 비중을 줄여 oldest unfinished message가 오래 남지 않게 만들고[^1]
- unified scheduler로 병합/공정성을 잡아 tail을 깎고[^1]
- soft committing으로 correctness를 지키면서도 Kafka를 멈추지 않게 합니다.[^1]

이 조합은 DNS가 아니라도(Feature flag, WAF 룰, 라우팅 정책, edge config 등) 대규모 설정 전파라면 대부분 재사용 가능합니다.

## 참고 자료

- [How we halved DNS build delay and cut memory use by 85%](https://blog.cloudflare.com/dns-targeted-zone-builds/)
- [Secondary DNS - Deep Dive](https://blog.cloudflare.com/secondary-dns-deep-dive/)
- [Introducing Quicksilver: Configuration Distribution at Internet Scale](https://blog.cloudflare.com/introducing-quicksilver-configuration-distribution-at-internet-scale/)
- [Apache Kafka Design: Exactly-once semantics](https://kafka.apache.org/44/design/design/)
- [KafkaConsumer Javadoc (manual commit 설명 포함)](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html)
- [Porcupine: A fast linearizability checker written in Go](https://github.com/anishathalye/porcupine)
- [Jepsen: A framework for distributed systems verification, with fault injection](https://github.com/jepsen-io/jepsen)
- [Cloudflare engineers optimize DNS build services for twice the speed and 85% lower RAM usage](https://www.tomshardware.com/networking/cloudflare-engineers-optimize-dns-build-services-for-twice-the-speed-and-85-percent-lower-ram-usage-finer-grained-processes-only-do-work-and-data-movement-thats-needed)

[^1]: <https://blog.cloudflare.com/dns-targeted-zone-builds/>
[^2]: <https://blog.cloudflare.com/secondary-dns-deep-dive/>
[^3]: <https://kafka.apache.org/44/design/design/>
[^4]: <https://github.com/jepsen-io/jepsen>
[^5]: <https://github.com/anishathalye/porcupine>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
