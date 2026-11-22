---
title: "RFC 10069 멀티패스 QUIC 구현 체크리스트와 운영 설계"
description: "RFC 10069 멀티패스 QUIC을 L4 LB·관측·혼잡제어 관점에서 구현/운영 체크리스트로 정리합니다."
date: 2026-11-22 14:49:29 +0900
categories: ["Networking", "QUIC"]
tags: ["quic", "multipath", "rfc10069", "quic-lb", "observability", "congestion-control"]
render_with_liquid: false
---

## RFC 10069이 규정한 범위: multipath는 스케줄러가 아닙니다

RFC 10069는 QUIC v1 위에 multipath extension을 얹어 “동시에 여러 path를 쓰는 단일 connection”을 가능하게 합니다. 여기서 중요한 전제가 두 가지 있습니다.

첫째, 문서가 해결하는 문제의 범위가 좁습니다. RFC 10069는 여러 path를 **동시에** 열고 유지하기 위한 식별자와 프레임(생성/폐기/상태/자원 제어)을 정의하지만, address discovery나 address 관리, 그리고 애플리케이션/전송이 “어떤 데이터를 어떤 path로 보낼지” 결정하는 스케줄링은 규정하지 않습니다. 표준이 된 순간부터 바로 운영 설계가 필요한 이유가 여기 있습니다. (스케줄링을 잘못하면 성능이 오히려 나빠질 수 있다는 경고도 문서에 직접 들어가 있습니다.) [RFC 10069 본문](https://www.rfc-editor.org/rfc/rfc10069.html)

둘째, 이 extension은 기존 QUIC handshake를 바꾸지 않습니다. 즉, 중간 장비(L4 LB, 패시브 관측)는 multipath 여부를 handshake에서 바깥으로 읽어내기 어렵고, endpoint 구현과 관측/운영이 서로 발목을 잡기 쉽습니다. [RFC 10069 정보 페이지](https://www.rfc-editor.org/info/rfc10069/)

2026년 11월 RFC Editor에 RFC 10069가 Standards Track로 게시되었고[^1], IETF 127 QUIC WG 회의록(세션 날짜 2026-11-18)에도 “RFC 10069 has been published!”가 명시적으로 들어갔습니다. 다만 그 회의록은 AI generated이며 오류 가능성을 전제로 읽어야 합니다. [IETF 127 QUIC minutes](https://datatracker.ietf.org/doc/minutes-127-quic/00/)

표준이 확정된 직후는 보통 PoC를 “성능”으로만 달리는 시기인데, multipath QUIC은 그 접근이 실패하기 쉽습니다. 나는 다음 3가지를 먼저 잡아야 한다고 봅니다.

- path ID와 connection ID의 수명/재사용 불가 제약을 코드 구조에 박는다.
- per-path packet number space가 암호 처리(AEAD nonce), loss detection, CC를 어떻게 쪼개는지 구현 단위로 쪼개서 검증한다.
- L4 LB/관측이 “암호화 때문에 볼 수 없는 것”을 인정하고, 대신 무엇을 강제(예: QUIC-LB CID)해야 운영이 가능한지 결정한다.

이 글은 그 결정을 돕기 위한 구현/운영 질문을 체크리스트로 바꿔놓는 데 목적을 둡니다.

## 협상과 활성화: initial_max_path_id가 들어오는 순간부터 설계가 갈립니다

RFC 10069는 multipath 지원 여부를 transport parameter 하나로 협상합니다. 양쪽 endpoint가 `initial_max_path_id`를 광고하지 않으면, 이 RFC에서 정의한 어떤 프레임/메커니즘도 쓰면 안 됩니다. 반대로 양쪽이 모두 광고하면, handshake 완료 이후 1-RTT부터 새로운 동작이 시작됩니다. [RFC 10069 정보 페이지](https://www.rfc-editor.org/info/rfc10069/)

이 단순한 협상 방식이 운영을 어렵게 만드는 지점이 있습니다.

- L4 LB는 `initial_max_path_id`를 볼 수 없습니다(1-RTT 이후에만 의미가 커지고, 프레임은 암호화됩니다).
- 패시브 관측도 동일합니다. multipath 동작의 대부분이 1-RTT 암호화 안에서 일어나기 때문에, “multipath인지 아닌지”를 중간에서 단정하면 쉽게 틀립니다.

따라서 서버/클라이언트 엔드포인트 구현에서 다음을 강제하는 게 출발점입니다.

1) multipath가 협상되면 로깅/메트릭의 primary key가 바뀝니다.

- 단일 path QUIC은 보통 connection 단위로만 봐도 됩니다.
- multipath는 connection 안에 path가 늘어나므로, connection 메트릭이 의미를 잃는 순간이 옵니다(예: RTT가 섞여버림).

2) multipath 프레임은 1-RTT에서만 보내야 합니다.

RFC 10069는 문서가 정의한 multipath 전용 프레임은 반드시 1-RTT에서만 전송되어야 하고, 다른 패킷 타입에서 받으면 `PROTOCOL_VIOLATION`로 연결을 닫아야 한다고 명시합니다. 구현에서 “프레임 파서 레벨”에서 막는 편이 안전합니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

3) ACK 체계가 바뀝니다.

RFC 10069는 1-RTT에서 path별 packet number space를 도입하기 때문에, ACK도 path ID를 포함해야 합니다. 그래서 ACK 확장인 `PATH_ACK` 프레임을 정의합니다. 다만 handshake 중에는 multipath 협상이 끝나지 않았으므로 Initial/Handshake에 대해서는 기존 ACK 프레임을 그대로 쓰고, 협상 완료 후에는 `PATH_ACK` 사용을 권장합니다(하지만 ACK도 계속 처리해야 합니다). [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

여기서부터 구현 체크리스트가 시작됩니다.

- [ ] transport parameter 협상 결과가 “런타임에 토글”될 수 있는 구조인가? (handshake 완료 시점에 on/off가 확정)
- [ ] 프레임 파서가 1-RTT가 아니면 multipath 프레임을 거부하는가?
- [ ] ACK 입력 경로가 ACK/PATH_ACK를 동시에 처리하고, path 0과 그 외 path를 혼동하지 않는가?

## Path ID 수명: 단조 증가·미재사용이 강제하는 상태 모델

RFC 10069에서 path는 4-tuple 자체가 아니라 path ID로 정의됩니다. 같은 4-tuple에 대해서도 여러 path ID를 가질 수 있다고 문서가 명시합니다. 그리고 path ID는 0부터 시작하며 단조 증가하고, 재사용할 수 없습니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

이 미재사용 제약은 단순한 “정책”이 아니라 암호 설계의 일부입니다. RFC 10069는 1-RTT에서 per-path packet number space를 쓰기 때문에, nonce 유일성을 위해 path ID를 nonce 계산에 포함시키고, 그 결과 path ID는 32비트 범위(최대 2^32-1)로 제한되며 재사용하면 안 된다고 명시합니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

구현 관점에서 이 요구사항은 자료구조를 바꿉니다.

- path ID는 “현재 열린 path 목록의 인덱스”가 아닙니다.
- path ID는 connection lifetime 동안 유일한 monotonic identifier입니다.
- path를 닫아도 ID 슬롯이 비지 않습니다.

나는 이걸 `Vec<PathState>` 같은 구조로 관리하면 언젠가 사고 난다고 봅니다. `HashMap<PathID, PathState>` + 별도 monotonic allocator가 보수적입니다.

### Path를 누가 여나: 클라이언트만 path를 열 수 있다는 제약

RFC 10069는 QUIC migration과 같은 틀을 유지하며, 새로운 path를 여는 주체를 클라이언트로 제한합니다. 서버는 path ID를 “받아들이고 관리”하지만, path initiation 자체는 클라이언트 시작입니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

운영 질문으로 바꾸면 다음과 같습니다.

- 서버는 path 수를 “요청받는 쪽”으로서 방어적으로 제한해야 합니다.
- 클라이언트가 path를 많이 열면 서버는 메모리/CPU(암호, loss detection 상태)를 path 수만큼 들고 있어야 합니다.

RFC 10069는 이를 제어하기 위해 `MAX_PATH_ID`, `PATHS_BLOCKED`, `PATH_CIDS_BLOCKED` 같은 흐름 제어 프레임을 정의합니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

IANA의 QUIC 레지스트리에도 이 프레임 타입들이 RFC 10069를 근거로 영구 할당된 것이 확인됩니다. 특히 `PATH_ACK`, `MAX_PATH_ID`, `PATHS_BLOCKED`, `PATH_CIDS_BLOCKED` 등이 코드포인트로 고정됐다는 점은 구현 시 상호운용성을 위해 중요합니다. [IANA QUIC 레지스트리](https://www.iana.org/assignments/quic)

### connection ID 발급 연속성: path ID 불일치가 만들어내는 교착

멀티패스에서 path를 열기 위해서는 “양쪽이 같은 path ID에 대해 사용 가능한 CID를 이미 발급해 둔 상태”여야 합니다. RFC 10069는 구현이 path ID 발급에 discontinuity를 만들지 말 것을 강하게 권고합니다. 예를 들어 최대 path ID가 2인데 2만 먼저 발급하면, 반대쪽이 1부터 발급하는 구현과 path를 열지 못할 수 있습니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

이건 실무적으로 이런 의미입니다.

- path ID는 로컬에서 증가시키는 숫자지만, “양쪽이 같은 숫자를 같은 의미로 써야” path가 열린다.
- endpoint 한쪽이 path ID 5용 CID를 발급해도, 반대쪽이 5를 준비하지 않았으면 아무 일도 일어나지 않는다.

따라서 구현 체크리스트는 다음이 됩니다.

- [ ] path ID allocator는 단조 증가하며 재사용이 불가능한가?
- [ ] per-path CID 발급은 0..N 범위에서 가능한 한 연속적으로 채우는가?
- [ ] path 생성이 실패했을 때(상대의 limit 또는 CID 부족) `MAX_PATH_ID` / `PATHS_BLOCKED` / `PATH_CIDS_BLOCKED`를 어떤 조건으로 내보내는가?
- [ ] path를 abandon할 때, 남아 있는 in-flight 패킷과 ACK 처리(특히 PATH_ACK의 경로)를 어떻게 정리하는가?

## CID 설계와 L4 LB: multipath에서 연결 affinity가 깨지는 방식부터 막습니다

멀티패스 QUIC이 운영을 흔드는 지점은 “서버에 도달하기 전에” 발생합니다.

- 단일 path에서는 connection ID 로테이션이 있더라도, 대개 LB가 DCID 기반으로 같은 backend로 보내기만 하면 됩니다.
- multipath에서는 path마다 별도의 CID 풀(그리고 sequence number space)이 필요해지고, “새로 발급되는 CID들”이 계속 생깁니다.

RFC 10069는 connection ID가 path ID에 바인딩된다고 명시합니다(각 CID는 정확히 하나의 path ID에 속함). 구현은 path별로 CID를 관리해야 합니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

그런데 L4 LB는 대개 암호 키가 없고, 1-RTT 암호화 안에서 오가는 `PATH_NEW_CONNECTION_ID`를 해석할 수 없습니다. LB가 할 수 있는 건 “패킷의 DCID를 보고 어디로 보낼지 결정”하는 것뿐입니다.

즉, multipath를 제대로 쓰려면 endpoint가 발급하는 CID 자체가 LB 친화적이어야 합니다.

### QUIC-LB가 필요한 이유: path ID가 아니라 “서버 ID”가 라우팅 키여야 합니다

QUIC WG의 QUIC-LB 문서는 connection ID에 server ID를 인코딩해서 L4 LB가 복호화 없이 라우팅할 수 있도록 하는 구조를 정의합니다. 서버가 server ID를 CID에 넣고, LB가 CID에서 server ID를 추출해 backend로 라우팅합니다. [QUIC-LB 문서](https://quicwg.org/load-balancers/draft-ietf-quic-load-balancers.html)

IETF 127 QUIC minutes에서도 QUIC-LB가 WGLC를 향해 가고 있고, Plaintext mode가 AWS NLB와 Envoy에 배포되었다는 언급이 있습니다. 이 회의록은 AI generated라서 단정은 금물이지만, 적어도 WG 레벨에서 운영 관점(배포 상태)이 같이 논의되고 있다는 힌트로는 충분합니다. [IETF 127 QUIC minutes](https://datatracker.ietf.org/doc/minutes-127-quic/00/)

QUIC-LB가 multipath에 주는 핵심 이점은 간단합니다.

- path가 늘어나면서 CID가 늘어나도, 모든 CID가 같은 server ID로 decode되게 만들 수 있습니다.
- LB는 per-path라는 개념이 없어도 됩니다. backend affinity만 맞으면 endpoint가 알아서 path를 굴립니다.

### QUIC-LB의 first octet과 길이 self-description: short header에서 CID 길이를 “추론”하려는 본능을 버립니다

QUIC-LB는 CID 첫 바이트를 특별하게 씁니다.

- 상위 3비트는 config rotation(어떤 설정/키로 CID를 decode할지)입니다.
- 하위 5비트는 선택적으로 “first octet 뒤에 이어지는 CID 길이”를 나타내는 데 예약되어 있습니다. 이 기능을 쓰지 않으면 랜덤처럼 보이는 비트여야 한다고 문서가 명시합니다. [QUIC-LB 문서](https://quicwg.org/load-balancers/draft-ietf-quic-load-balancers.html)

여기서 오해하기 쉬운 점이 하나 있습니다.

- 이 길이 self-description은 “LB를 위한 기능”이 아니라 서버의 로컬 오프로드(키 lookup) 같은 목적이 먼저입니다.
- LB는 오히려 길이 기능을 몰라도 라우팅이 가능해야 합니다.

그러면 LB 구현/운영 체크리스트는 이렇게 정리됩니다.

- [ ] DCID만으로 backend를 결정할 수 있는가? (server ID decode)
- [ ] decode 실패(Unknown config id, CID too short, mapping 없음) 시 baseline fallback(4-tuple 기반)로 안정적으로 보낼 수 있는가?
- [ ] fallback 상태 테이블을 얼마나 유지할 것인가? (메모리, NAT rebinding 대응)

QUIC-LB 문서는 LB가 반드시 baseline fallback algorithm(4-tuple만 입력으로 받아 routing decision을 내는 방식)을 구현해야 한다고 명시합니다. decode 불가 CID가 존재하는 환경에서는 unroutable DCID를 본 4-tuple을 테이블로 유지해 연결 생존성을 높이는 것도 권고합니다. [QUIC-LB 문서](https://quicwg.org/load-balancers/draft-ietf-quic-load-balancers.html)

### CID linkability와 multipath: 서버 ID를 넣는 순간 관측이 쉬워지고, 프라이버시가 깨집니다

QUIC-LB는 server ID와 nonce 구조를 정의하면서, nonce 재사용 금지 및 관측 가능한 상관관계 금지를 강하게 이야기합니다. nonce가 linkable하면 migration/다중 경로에서 관측자가 연결을 쉽게 따라붙을 수 있기 때문입니다. [QUIC-LB 문서](https://quicwg.org/load-balancers/draft-ietf-quic-load-balancers.html)

multipath는 본질적으로 “여러 경로에서 동일 연결을 쓰는 것”이라 linkability 리스크가 더 커집니다. 운영 상 관측을 위해 CID에 더 많은 힌트를 넣고 싶은 유혹이 있는데, 나는 다음 원칙을 추천합니다.

- server ID 외에 per-path 정보를 CID에 encode하지 않는다.
- per-connection nonce는 충분히 랜덤이며 재사용하지 않는다.
- 서버 내부에서 path ID ↔ CID 매핑은 endpoint 내부 상태로만 들고 간다.

LB/관측 요구를 CID로 해결하려고 하면 프라이버시와 운영이 충돌합니다. 이 충돌은 multipath에서 더 자주 터집니다.

## per-path packet number space: 암호와 손실 탐지의 기준선이 바뀝니다

RFC 10069에서 가장 구현 비용이 큰 변화는 per-path packet number space입니다.

- path ID별로 1-RTT packet number space가 분리됩니다.
- 각 path의 PN space는 0부터 시작합니다.
- 이 구조 덕분에 QUIC recovery의 loss detection과 congestion control을 path별로 적용할 수 있다고 문서가 설명합니다.
- 대신, PN만으로 nonce 유일성이 깨지므로 AEAD nonce 계산에 path ID를 포함하도록 바꿉니다.

이걸 코드 구조로 바꾸면 “connection 단위의 송수신 상태”가 “path 단위의 송수신 상태”로 내려갑니다.

### AEAD nonce 계산이 바뀌는 이유: PN 충돌을 path ID로 막습니다

RFC 10069는 handshake 이후 1-RTT에서 nonce를 `IV xor PPN`으로 만들고, PPN은 96비트로 구성되며 상위 32비트가 path ID, 그 다음 2비트는 0, 하위 62비트는 reconstructed packet number로 구성된다고 정의합니다. 그리고 nonce 길이가 12바이트보다 짧은 AEAD는 multipath extension과 같이 쓸 수 없다고 못 박습니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

이게 운영/구현에 주는 함정은 다음과 같습니다.

- QUIC 키 업데이트/AEAD 패킷 수 제한은 “path별”이 아니라 “connection 전체”로 누적됩니다. path가 늘면 패킷 수가 더 빨리 쌓일 수 있고, 키 업데이트 전략이 영향을 받습니다. [RFC 10069 정보 페이지](https://www.rfc-editor.org/info/rfc10069/)
- path ID 재사용을 허용하면 nonce 재사용으로 바로 암호 안전성이 깨집니다.

### Go로 AEAD nonce(IV xor PPN) 구현 및 테스트

아래 코드는 RFC 10069의 nonce 계산을 그대로 구현한 것입니다. 라이브러리 내부에서 path별 packet protector를 만들 때, “path ID를 잊지 말고 nonce에 섞었는지”를 유닛 테스트로 고정하는 용도입니다. RFC 10069는 IV, path ID, packet number 예시를 숫자까지 제공하므로 그대로 테스트 벡터로 쓸 수 있습니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

`go test`로 바로 검증할 수 있게 작성했습니다.

```bash
# Go 1.22+ 권장
mkdir -p mpnonce
cd mpnonce
go mod init example.com/mpnonce

cat > nonce.go <<'EOF'
package mpnonce

import "encoding/binary"

// Nonce12 computes the QUIC packet protection nonce for multipath QUIC after
// handshake completion, as specified by RFC 10069 Section 2.4.
//
// For a 96-bit IV (12 bytes):
//   PPN = PathID(32) || 0b00(2) || PacketNumber(62)
//   Nonce = IV xor PPN
//
// PathID is limited to 32 bits by the RFC; packetNumber must fit in 62 bits.
func Nonce12(iv [12]byte, pathID uint32, packetNumber uint64) [12]byte {
	var ppn [12]byte
	binary.BigEndian.PutUint32(ppn[0:4], pathID)

	// Put packet number into the low 62 bits of the last 8 bytes.
	// The top 2 bits of this 64-bit word must be zero.
	pn62 := packetNumber & ((uint64(1) << 62) - 1)
	binary.BigEndian.PutUint64(ppn[4:12], pn62)

	// Ensure the top 2 bits are zero explicitly (defensive).
	ppn[4] &= 0x3f

	var out [12]byte
	for i := 0; i < 12; i++ {
		out[i] = iv[i] ^ ppn[i]
	}
	return out
}
EOF

cat > nonce_test.go <<'EOF'
package mpnonce

import (
	"encoding/hex"
	"testing"
)

func mustHex12(t *testing.T, s string) [12]byte {
	t.Helper()
	b, err := hex.DecodeString(s)
	if err != nil {
		t.Fatalf("hex decode: %v", err)
	}
	if len(b) != 12 {
		t.Fatalf("want 12 bytes, got %d", len(b))
	}
	var out [12]byte
	copy(out[:], b)
	return out
}

func TestNonce12_RFC10069Example(t *testing.T) {
	// Example values from RFC 10069 Section 2.4.
	iv := mustHex12(t, "6b26114b9cba2b63a9e8dd4f")
	got := Nonce12(iv, 3, 54321) // 0xd431
	want := mustHex12(t, "6b2611489cba2b63a9e8097e")

	if got != want {
		t.Fatalf("nonce mismatch\n got: %x\nwant: %x", got, want)
	}
}
EOF

go test ./...
```

예상 출력은 다음처럼 단순히 PASS여야 합니다.

```text
ok  	example.com/mpnonce	0.00s
```

이 유닛 테스트 하나만으로도 “per-path PN space를 도입했는데 nonce는 예전 방식으로 계산하는” 종류의 치명적인 버그를 초기에 잡을 수 있습니다.

## per-path loss detection / congestion control: 구현은 쉬워 보이고, 운영이 어렵습니다

RFC 10069는 path별 PN space를 통해 QUIC recovery를 per-path로 적용할 수 있다고 설명합니다. 또한 PTO 만료 처리에서 각 path별로 QUIC recovery 메커니즘을 따르라고 직접 언급합니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

하지만 실제 운영에서 문제는 “공정성”과 “스케줄링”입니다.

- path마다 독립 CC를 돌리면, 합산 전송률이 단일 path보다 커져서 네트워크에 공격적으로 보일 수 있습니다.
- 반대로 path를 coupling하면 구현 난이도가 크게 올라갑니다.
- path 간 RTT 차이가 큰 환경에서 스트림 데이터를 여러 path로 섞어 보내면 reordering이 폭발하고, 손실 탐지가 흔들릴 수 있습니다.

이 지점에서 연구 결과가 참고가 됩니다. multipath QUIC에서 “packet number space를 path별로 분리할지/단일로 둘지”가 성능에 미치는 영향을 비교한 논문도 있고, 결국 표준은 per-path PN space 쪽으로 정리됐습니다. [The Packet Number Space Debate in Multipath QUIC](https://arxiv.org/abs/2112.01068)

### QUIC recovery와 multipath의 접점: PTO는 per PN space이고, CC는 path 특성입니다

기본 QUIC의 loss detection은 packet number space마다 별도로 동작하고, PTO도 PN space마다 계산/동작합니다. 반면 RTT 측정과 CC는 path의 성질이라고 RFC 9002가 설명합니다. [RFC 9002](https://www.rfc-editor.org/rfc/rfc9002.html)

RFC 10069는 아예 path마다 PN space를 분리했기 때문에, 구현자는 “PTO 타이머/ACK 상태”를 path마다 들고 가는 게 자연스러워집니다. 동시에 CC도 path마다 들고 가야 설계가 깔끔해집니다.

여기서 운영 질문은 이렇게 바뀝니다.

- path별 cwnd, bytes_in_flight를 따로 메트릭으로 뽑는가?
- connection 레벨에서 “총 전송률/총 in-flight”도 같이 보나?
- retransmission을 다른 path로 넘길지(재스케줄링) 정책이 있는가?

RFC 10069는 PTO 만료 시 다른 path로 재전송할 수 있다는 방향성을 “구현 선택”으로 언급합니다. 하지만 이 기능은 모바일 네트워크에서 비용(셀룰러 데이터)과 성능(대체 경로 RTT) 트레이드오프를 크게 만듭니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

나는 다음 순서로 접근하는 편이 현실적이라고 봅니다.

1) PoC 1단계: path별 CC는 분리하되, scheduling은 보수적으로 한다.

- 기본은 primary path 하나에 몰고, backup path는 failover/일시적 burst 흡수에만 쓴다.
- 이때 `PATH_STATUS_AVAILABLE` / `PATH_STATUS_BACKUP` 같은 상태 프레임이 운영적으로 의미가 생깁니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

2) PoC 2단계: 스케줄링을 켠다. 대신 관측을 먼저 만든다.

- per-path RTT 분포
- per-path reordering 징후(ACK range 패턴)
- per-path PTO 발생률
- per-path 손실률 추정(ACK 기반)

관측이 없으면, scheduling 개선이든 퇴보든 판단이 불가능합니다.

## NAT/모바일 네트워크 실패 모드: “path를 늘리면 안정적일 것”이라는 가정이 자주 깨집니다

멀티패스가 필요한 대표 케이스는 Wi-Fi + LTE/5G 동시 사용, 혹은 DC 내부에서 ECMP로 path diversity를 기대하는 경우입니다. 그런데 실제 필드에서는 NAT rebinding, 방화벽 정책, symmetric NAT, 라디오 전환이 같이 엉켜서 실패 모드가 더 많아집니다.

RFC 10069는 NAT rebinding, CID rotation, migration이 path ID를 바꾸지 않는다고 설명하면서도, multipath 메커니즘(새 path 열고 old path abandon)이 더 부드러운 handover가 될 수 있다고 언급합니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

여기서 구현/운영 체크리스트를 실패 모드 중심으로 정리하면 다음과 같습니다.

### 1) PATH_CHALLENGE/RESPONSE가 “같은 path”로 돌아오지 않는 문제

QUIC 기본에서 path validation은 `PATH_CHALLENGE`/`PATH_RESPONSE`로 합니다. 수신자는 받은 challenge의 Data를 그대로 echo 하는 response를 생성해야 합니다. [RFC 9000](https://www.rfc-editor.org/rfc/rfc9000.html)

RFC 10069는 multipath 환경에서 `PATH_RESPONSE`는 challenge를 보낸 패킷과 같은 path에서, 같은 path ID에 연결된 CID를 사용해 보내야 한다고 명시합니다. 구현이 이 규칙을 어기면 path validation이 흔들리고, NAT/방화벽 환경에서 디버깅이 거의 불가능해집니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

- [ ] PATH_CHALLENGE를 받은 tuple/path context를 저장하고, PATH_RESPONSE 송신 시 그 context로 강제하는가?
- [ ] path validation 중 CID 교체(로테이션)가 겹칠 때, “path ID에 속한 CID”를 엄격하게 선택하는가?

### 2) PMTU 차이: path마다 MTU가 다르면 coalescing/패딩 전략이 깨집니다

RFC 10069는 path마다 PMTU가 다를 수 있음을 implementation considerations로 따로 다룹니다. path별 packetization을 분리하지 않으면 특정 path에서만 fragmentation/손실이 늘고, 그 손실이 스케줄링/CC를 오염시킵니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

- [ ] path별 PMTU 추정/저장을 분리했는가?
- [ ] 특정 path에서만 지속 손실이 발생할 때(예: 터널/셀룰러), 그 path를 backup으로 내리는 정책이 있는가?

### 3) preferred_address의 착시: 주소가 두 개니까 multipath가 되겠지

RFC 10069는 서버가 `preferred_address` transport parameter를 쓰는 경우, 클라이언트가 “초기 서버 주소”와 preferred_address에 들어있는 주소를 multipath로 동시에 쓸 수 있다고 가정하면 안 된다고 명시합니다. 운영에서 흔히 하는 착각을 표준이 직접 막아둔 셈입니다. [RFC 10069](https://datatracker.ietf.org/doc/html/rfc10069)

- [ ] 주소 후보가 여러 개여도 실제로 동시에 쓰는 건 별도 정책(스케줄러)이라는 점을 명확히 했는가?

### 4) path abandon의 의미를 관측에 반영했는가

RFC 10069는 path를 abandon하는 프레임과, 그 이유를 나타내는 error code를 정의합니다. IANA 레지스트리에도 `PATH_UNSTABLE_OR_POOR`, `NO_CID_AVAILABLE_FOR_PATH` 같은 코드가 고정돼 있습니다. 이 값은 운영에서 “왜 path가 줄었는지”를 알려주는 거의 유일한 힌트가 됩니다. [IANA QUIC 레지스트리](https://www.iana.org/assignments/quic)

- [ ] PATH_ABANDON 송수신 이벤트를 로그/메트릭으로 남기는가?
- [ ] error code를 태깅해서 집계하는가? (unstable/poor vs resource limit vs cid 부족)

## 관측 설계: qlog는 힌트가 있지만, core 스키마에 multipath가 자동으로 들어오지 않습니다

qlog 메인 스키마는 이벤트를 여러 path로 나눠 기록할 필요가 있다는 문제의식을 이미 담고 있고, `PathID` 같은 필드도 언급합니다. [qlog main schema 초안](https://www.ietf.org/archive/id/draft-ietf-quic-qlog-main-schema-10.html)

하지만 IETF 127 minutes에 따르면 “core qlog 문서에는 multipath events나 path IDs를 추가하지 않는다”는 방향이 공유됐고, 별도의 multipath qlog draft를 자원자들이 작업하기로 했다는 내용이 있습니다. [IETF 127 QUIC minutes](https://datatracker.ietf.org/doc/minutes-127-quic/00/)

이 말은 즉시 실무로 번역됩니다.

- 당분간은 구현체별로 multipath 관측 이벤트가 제각각일 가능성이 높습니다.
- 표준 qlog만 붙여서는 path별 RTT/CC/손실 상태를 충분히 못 뽑을 수 있습니다.

나는 그래서 multipath PoC의 관측을 “표준 로그 1개”에 걸지 않고, 최소 두 레이어로 분리하는 걸 선호합니다.

1) 전송 스택 내부 메트릭(필수)

- path별: smoothed_rtt, rttvar, min_rtt
- path별: cwnd, bytes_in_flight, pacing_rate(있는 구현이라면)
- path별: pto_count, loss_event_count, ack_delay 관측
- path별: validated 여부, last_path_challenge_ts
- path별: current DCID sequence, spare CID 개수

2) 외부(LB/edge) 관측(보조)

- QUIC-LB server ID 기반 트래픽 분포
- 4-tuple 변경 빈도(= NAT rebinding 징후)
- DCID decode 실패율(unroutable 비율)

특히 2)는 multipath인지 아닌지 모르더라도, 운영을 안정화하는 지표가 됩니다. multipath는 결국 CID를 더 많이 쓰게 되므로, DCID decode 실패가 늘면 바로 장애로 이어질 수 있습니다.

이 부분은 내가 예전에 “트래픽 계측부터 잡고 단계적으로 종료/전환”하는 글을 썼던 이유와 결이 같습니다. 다만 여기서는 TLS 차단이 아니라 multipath 기능 도입이므로, 관측을 먼저 깔아야 합니다. [App Engine(Go)의 TLS 1.1 이하 차단에 대비한 트래픽 계측과 단계적 종료](https://daewooki.github.io/posts/app-engine-tls11-cutoff-traffic-audit/)

## 구현/운영 체크리스트: path ID, CID, PN space, CC를 한 장으로 묶기

여기까지 내용을 실제 작업 항목으로 압축하면 아래처럼 정리됩니다. 이 체크리스트는 “표준이 나왔다”가 아니라 “구현이 어느 지점에서 깨지는지”를 기준으로 뽑았습니다.

### A. 프로토콜 협상 / 호환성

- [ ] `initial_max_path_id` 미협상 시 RFC 10069 관련 프레임 송신을 전부 금지했는가? [RFC 10069 정보 페이지](https://www.rfc-editor.org/info/rfc10069/)
- [ ] multipath 전용 프레임은 1-RTT에서만 송신/수신 처리하는가? 다른 패킷 타입에서 수신 시 `PROTOCOL_VIOLATION`로 닫는가? [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)
- [ ] 협상 이후 ACK ↔ PATH_ACK 전환을 처리하고, ACK도 계속 수용하는가? [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

### B. Path ID 관리

- [ ] path ID allocator가 단조 증가하며 재사용이 불가능한가? (abandon 후에도) [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)
- [ ] path ID가 nonce 계산에 포함된다는 사실을 코드/테스트로 고정했는가? [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)
- [ ] “같은 4-tuple에서 여러 path ID”를 허용할 수 있는 자료구조인가? [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

### C. CID 설계 / CID 재고 관리

- [ ] per-path CID pool을 분리했는가? sequence number space도 per-path로 분리했는가? [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)
- [ ] peer가 새 path를 열 수 있도록 “연속적인 path ID 범위”로 CID를 선발급하는가? [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)
- [ ] CID 부족 시 `PATH_CIDS_BLOCKED`/`PATHS_BLOCKED`를 적절히 내보내는가? [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

### D. L4 LB / edge와의 결합

- [ ] QUIC-LB 같은 routable CID 체계를 전제로 설계했는가? (server ID decode) [QUIC-LB 문서](https://quicwg.org/load-balancers/draft-ietf-quic-load-balancers.html)
- [ ] LB fallback(4-tuple 기반)을 구현했고, unroutable DCID/4-tuple 테이블로 연결 생존성을 확보했는가? [QUIC-LB 문서](https://quicwg.org/load-balancers/draft-ietf-quic-load-balancers.html)
- [ ] CID에 관측 편의를 위해 per-path 정보를 encode하려는 요구를 프라이버시 관점에서 거부/제한했는가? [QUIC-LB 문서](https://quicwg.org/load-balancers/draft-ietf-quic-load-balancers.html)

### E. packet number space / 손실 탐지 / CC

- [ ] path별 PN space(송신/수신 상태)를 분리했는가? PN은 path마다 0부터 시작하도록 초기화했는가? [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)
- [ ] AEAD nonce 계산에 path ID를 포함했는가? nonce 길이 제약을 만족하는가? [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)
- [ ] loss detection과 PTO를 path별로 돌리는가? [RFC 9002](https://www.rfc-editor.org/rfc/rfc9002.html)
- [ ] retransmission을 다른 path로 넘길지 정책이 있으며, 비용/지연 트레이드오프를 운영 변수로 노출했는가? [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

### F. 실패 모드 및 관측

- [ ] PATH_CHALLENGE/RESPONSE를 같은 path context로 강제하는가? [RFC 9000](https://www.rfc-editor.org/rfc/rfc9000.html)
- [ ] PATH_ABANDON과 error code를 메트릭화했는가? [IANA QUIC 레지스트리](https://www.iana.org/assignments/quic)
- [ ] qlog만으로 부족할 수 있음을 가정하고, 구현체 내부 메트릭을 per-path로 뽑는가? [IETF 127 QUIC minutes](https://datatracker.ietf.org/doc/minutes-127-quic/00/)

## 결론: 멀티패스 QUIC은 “전송 기능”이 아니라 “운영 모델 변경”입니다

RFC 10069가 Standards Track로 확정됐다는 사실 자체보다 중요한 건, 이 문서가 QUIC의 상태 분해 단위를 connection에서 path로 쪼갰다는 점입니다. path ID가 nonce에 들어가면서 “path ID 미재사용”은 구현 선택이 아니라 보안 요구가 됐고, per-path packet number space는 ACK, loss detection, PTO, CC, 관측까지 연쇄적으로 구조를 바꿉니다. [RFC 10069](https://www.rfc-editor.org/rfc/rfc10069.html)

운영 측면에서는 L4 LB가 multipath 프레임을 볼 수 없다는 현실 때문에 CID 설계(예: QUIC-LB)를 사실상 전제로 깔게 됩니다. 그 전제가 없으면, path가 늘어날수록 backend affinity가 깨질 확률이 올라가고, 그 순간 multipath는 성능 기능이 아니라 장애 유발 기능이 됩니다. [QUIC-LB 문서](https://quicwg.org/load-balancers/draft-ietf-quic-load-balancers.html)

그래서 나는 multipath QUIC 도입의 첫 작업 항목을 스케줄러가 아니라 체크리스트(경로 ID 관리, CID 재고, PN space 분리, per-path CC/손실 탐지, 실패 모드, 관측 지표)로 두는 편이 맞다고 봅니다.

## 참고 자료

- [RFC 10069: Managing Multiple Paths for a QUIC Connection](https://www.rfc-editor.org/rfc/rfc10069.html)
- [IETF 127 QUIC WG Session Minutes (minutes-127-quic-00, 2026-11-18)](https://datatracker.ietf.org/doc/minutes-127-quic/00/)
- [QUIC-LB: Generating Routable QUIC Connection IDs](https://quicwg.org/load-balancers/draft-ietf-quic-load-balancers.html)
- [IANA QUIC Registry](https://www.iana.org/assignments/quic)
- [RFC 9000: QUIC: A UDP-Based Multiplexed and Secure Transport](https://www.rfc-editor.org/rfc/rfc9000.html)
- [RFC 9002: QUIC Loss Detection and Congestion Control](https://www.rfc-editor.org/rfc/rfc9002.html)
- [qlog main schema (draft-ietf-quic-qlog-main-schema-10)](https://www.ietf.org/archive/id/draft-ietf-quic-qlog-main-schema-10.html)
- [The Packet Number Space Debate in Multipath QUIC (arXiv:2112.01068)](https://arxiv.org/abs/2112.01068)
- [NGINX HTTP/3 구성 의존 CVE 대응 체크리스트](https://daewooki.github.io/posts/nginx-http3-quic-cve-mitigation-checklist/)
- [App Engine(Go)의 TLS 1.1 이하 차단에 대비한 트래픽 계측과 단계적 종료](https://daewooki.github.io/posts/app-engine-tls11-cutoff-traffic-audit/)

[^1]: <https://www.rfc-editor.org/rfc/rfc10069.html>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
