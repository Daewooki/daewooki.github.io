---
title: "Deno 팀의 Cloudflare 합류: 런타임 종료가 남기는 리스크"
description: "Deno runtime은 오픈소스로 남지만, 1년 뒤 개발 종료가 예고된 순간부터 보안 패치와 릴리스 운영의 책임이 사용자에게 넘어옵니다."
date: 2026-10-11 11:05:19 +0900
categories: ["News", "Backend"]
tags: ["deno", "cloudflare-workers", "workerd", "durable-objects", "oss-maintenance", "migration"]
render_with_liquid: false
---

## 발표 내용: 2026-10-09 공지의 ‘세 개의 시계’

2026-10-09(금) Deno와 Cloudflare가 동시에 “Deno is joining Cloudflare”를 공식 발표했습니다. Deno 쪽 공지는 문장 수가 많지 않고, 종료/전환 조건이 글 중간에 아주 간결하게 정리돼 있습니다.[^1]

정리하면 시계가 세 개가 돌아갑니다.

첫째, Deno runtime은 **앞으로 1년 동안 월간 릴리스**로 버그 수정과 보안 업데이트를 제공한 뒤, “우리(기존 Deno 팀)의 Deno runtime 개발을 종료”하겠다고 명시했습니다. “Deno는 오픈소스로 남고, 누군가가 계속 개발하길 환영한다”까지가 한 문단에 붙어 있습니다. 즉, 저장소가 사라진다는 의미가 아니라, 현재의 개발 주체가 빠진다는 의미입니다.[^1]

둘째, Deno Deploy는 “6개월 동안 운영한 뒤 종료”를 예고했습니다. 그리고 “Cloudflare Workers로 옮기는 유료 고객에 대해서는 마이그레이션 지원을 제공”한다고 밝혔습니다. 6개월은 날짜가 박혀 있지 않으므로, 공지일 2026-10-09 기준이면 2027-04-09 전후로 해석하는 게 자연스럽지만(캘린더 기준 오차가 생길 수 있음), 공식적으로는 ‘6개월’만 확정입니다.[^1]

셋째, JSR은 계속 운영되며, 인프라가 Cloudflare로 이전한다고 했습니다. Deno 생태계에서 package registry가 런타임/호스팅과 분리돼 생존하는 모양새입니다.[^1]

Cloudflare 쪽 발표는 인수(acquisition)라는 표현을 쓰기보다는 “팀 합류(joining)”에 가깝게 쓰고, 대신 핵심 포인트를 하나 더 강하게 박습니다. 

* workerd와 celld를 “merge”하겠다는 선언
* workerd self-hosting을 “first-class supported way”로 만들겠다는 로드맵
* 그 일을 Ryan Dahl과 Bert Belder가 리드한다는 조직 선언

이건 Cloudflare 발표문 내에서 “The Plan” 아래에 명시돼 있습니다.[^2]

외부 보도는 사실상 인수로 해석합니다. TechCrunch는 “Cloudflare acquires Deno”라고 제목을 뽑았고, 금액은 비공개라고 적었습니다.[^3]

요약하면, 2026-10-11(KST) 시점에서 실무자가 봐야 할 건 “Deno가 오픈소스로 남는다/죽는다” 같은 감정적 구도가 아니라, **개발 주체가 사라지는 순간부터 발생하는 운영 리스크**와, 그 리스크를 흡수할 대체 경로(Workers/workerd)가 얼마나 실제로 작동하느냐입니다.

## 배경: Deno → Deploy → celld가 향한 방향과 Cloudflare의 욕심

Deno 공지에서 의외로 중요한 문장은 “야망이 runtime을 넘어서 있었다”는 대목입니다. Deno는 compute·storage·communication이 함께 가는 형태를 오래 전부터 이야기했고, Deploy는 그 야망의 상용화 실험이었는데, Deploy를 운영하면서 밑단 인프라 복잡도가 여전히 크다는 걸 체감했다는 흐름입니다. 그래서 ‘더 아래’를 단순화하려고 만든 결과물이 celld라는 서사로 연결됩니다.[^1]

Cloudflare 쪽은 이 지점에서 더 노골적입니다.

* workerd는 이미 오픈소스지만, Durable Objects가 단일 인스턴스(local testing 수준)에 머물러서 “scale”이 안 된다
* Cloudflare 프로덕션의 Durable Objects 라우팅/운영 방식은 self-hosting에 적합하지 않고 의존성이 많다
* 그 문제를 풀려고 했지만 Cloudflare만으로는 제대로 못 했고, celld가 그 빈칸을 메웠다

Cloudflare 발표문에서 workerd의 Durable Objects가 갖는 ‘프로덕션 갭’을 직접 인정하면서, celld의 방향(자체 호스팅/분산/호환성)에 기대는 논리가 전개됩니다.[^2]

즉, 이번 합류는 Deno의 runtime 자체를 Cloudflare가 계속 키워 주겠다는 이야기가 아니라,

* (Cloudflare 관점) Workers programming model을 온프레미스/타 클라우드까지 밀어 넣기 위한 self-hosting 현실화
* (Deno 관점) runtime/hosting을 별도로 끌고 가기보다 Workers 모델이라는 더 큰 플랫폼으로 수렴

이 합의에 가깝습니다. Deno 공지에서 “shared platform에 미래 개발을 집중하고 separate runtime과 hosting service는 계속 개발하지 않겠다”고 선을 긋는 문장이 결정적입니다.[^1]

## ‘오픈소스 런타임’에서 ‘개발 주체’가 사라질 때의 운영 리스크

오픈소스가 남는다고 해서, 운영 리스크가 남지 않는 건 아닙니다. 오히려 보안/릴리스/에코시스템의 축이 ‘누가 책임지느냐’로 이동합니다. 이번 건은 그 이동이 날짜로 고정된 사례입니다.

### 1) 보안 패치: CVE가 터졌을 때 “누가 리드타임을 소유하는가”

Deno runtime은 V8, Rust crates, OS별 배포 파이프라인을 모두 끌고 갑니다. 런타임은 애플리케이션보다 훨씬 낮은 레이어에 있고, 취약점 대응은 보통 아래 형태로 굴러갑니다.

* 이슈 인지(보안 메일/리포트/업스트림 공지)
* 영향 평가(어떤 버전/플래그/플랫폼에 해당하는지)
* 패치 백포트(특히 LTS나 특정 minor를 유지할 때)
* 릴리스/서명/배포
* 하위 사용자(기업/프로덕트)의 업그레이드 창 관리

Deno는 원래 patch 릴리스를 “as needed”로 내고, minor 사이에 여러 patch가 나오며, release schedule 문서에는 patch가 “weekly”로 진행된다고까지 적혀 있습니다.[^4]

그런데 2026-10-09 공지는 ‘1년간 월간 릴리스’로 cadence를 못 박았습니다.[^1]

여기서 중요한 건 빈도 자체보다도, 사건 대응 방식이 바뀐다는 점입니다.

* 월간 릴리스로 묶이면, 긴급 보안 패치가 “월간에 포함”되는지 “out-of-band로 따로 나오는지”가 불명확해집니다.
* 공지는 “bug fixes and security updates”를 약속하지만, “심각도별 SLA”나 “out-of-band 정책”은 제시하지 않습니다.

실무적으로는 2027-10-09 전후(1년 경과 시점)부터는 더 직접적입니다. Deno 팀이 Deno runtime 개발을 끝낸다고 했으니, 다음 질문이 남습니다.

* V8 쪽에서 보안 이슈가 터질 때 Deno runtime 쪽 통합/릴리스는 누가 하나?
* 기업이 요구하는 backport(예: 특정 배포판/특정 minor 고정)는 누가 하나?
* 보안 공지 채널과 triage는 누가 운영하나?

“커뮤니티가 한다”는 문장은 가능성이 아니라 희망에 가깝고, 특히 런타임은 유지보수 비용이 커서 더 그렇습니다.

### 2) 릴리스 cadence 변화: 컴플라이언스/운영 창이 역으로 커진다

런타임 릴리스가 촘촘하면 업그레이드 피로가 생기지만, 너무 듬성하면 반대로 운영 리스크가 올라갑니다.

* 보안 핫픽스가 늦어질수록, WAF나 규칙으로 덮을 수 없는 런타임 레벨 이슈가 장기 노출됩니다.
* 고객사/사내 보안팀이 “patch 가능 시점”을 예측하기 어려워지고, 결국 “런타임 업그레이드 = 분기 프로젝트”로 비대해집니다.

나는 예전에 Python 3.10 EOL과 보안-only 전환을 계기로, 멀티 런타임 운영이 강제되는 이유를 정리한 적이 있는데(런타임의 lifecycle이 팀의 배포 체계를 바꾸는 문제), 이번 Deno 이슈는 그보다 더 급격한 형태입니다. [Python 3.10 EOL과 보안-only 전환이 멀티 런타임 운영을 강제한다](https://daewooki.github.io/posts/python-multi-runtime-lifecycle-upgrade/)

### 3) 에코시스템 의존성: Deno의 강점이었던 “완결된 툴체인”의 균열

Deno의 매력은 runtime만이 아니라,

* 기본 제공 tooling(포맷, 린트, 테스트)
* Node.js & npm 호환성
* Deploy 같은 실행 플랫폼

이 묶음이었습니다. 그런데 공식 공지는 앞으로의 투자 방향을 Workers/workerd 쪽으로 옮긴다고 말합니다.[^1]

이 상황에서 생기는 실제 리스크는 다음입니다.

* Deno runtime 자체는 계속 빌드 가능하지만, “새로운 웹 표준/새로운 Node API 호환 요구/새로운 TLS 정책 변화” 같은 변화가 누적될 때 누가 결정을 내리는가
* JSR이 살아남아도, 런타임이 유지되지 않으면 레지스트리는 ‘배포 대상의 기반’이 약해진다

물론 JSR은 계속 운영하고 인프라를 Cloudflare로 옮긴다고 했기 때문에, 공급망 측면에서는 오히려 안정성이 올라갈 여지도 있습니다.[^1] 다만 그 안정성은 ‘registry의 가용성’이지 ‘런타임의 진화’는 아닙니다.

## Deno Deploy 6개월 종료: 런타임보다 급한 일정

런타임 종료는 1년 유예가 있지만, Deploy는 6개월입니다. 여기가 실무 타임라인의 병목입니다.[^1]

게다가 Deno Deploy는 이미 2026년 중반에 한 차례 큰 종료 공지가 있었습니다. Deno Docs에는 Deploy Classic(dash.deno.com)과 subhosting v1 API가 2026-07-20에 shutdown된다고 명시돼 있습니다.[^5] 즉, Deploy는 제품군 자체가 이동/정리 중이었고, 이번 공지는 그 흐름의 종착점에 가깝습니다.

Deploy가 종료되면, 단순히 “호스팅을 옮긴다”가 끝이 아닙니다. Deploy를 쓰던 팀은 보통 아래 기능을 함께 쓰고 있었을 가능성이 높습니다.

* edge 배포/롤백(프리뷰 URL 포함)
* WebSocket/실시간 기능
* 간단한 KV 성격의 저장소
* cron, webhook, background 작업

이걸 다른 플랫폼으로 옮길 때, 언어가 같은 JS/TS라도 실행 모델이 바뀝니다. 특히 실시간과 상태가 끼면(채팅, 협업, 세션), 옮기는 순간 설계가 바뀝니다.

Cloudflare가 이번 합류에서 Durable Objects를 계속 전면에 내세우는 이유도 여기랑 맞닿아 있습니다. Deno 공지는 “Durable Objects가 agent harness에 유용하다”는 문장으로 마무리하고, Cloudflare 공지는 아예 Durable Objects의 ‘분산 self-hosting’이 workerd의 핵심 갭이었다고 씁니다.[^1]

## 대체 경로(관리형): Cloudflare Workers로 옮길 때 바뀌는 것

Deno Deploy에서 Cloudflare Workers로 옮기는 건, “비슷한 edge serverless”로 갈아타는 수준이 아니라, programming model의 중심이 달라지는 변화입니다.

Cloudflare는 Workers가 전 세계 네트워크에서 isolate 기반으로 실행된다고 설명하고, VM 스타일의 cold start 모델과 다르다고 강조합니다.[^6] 이 구조는 latency/scale에 유리하지만, 반대로 런타임과 OS 사이를 직접 만질 수 있는 범위가 좁습니다.

마이그레이션 관점에서 부딪히는 지점은 대략 네 가지입니다.

### 1) 파일 시스템, 프로세스, 소켓 같은 “서버스러움”이 빠진다

Deno 쪽은 `deno compile`로 단일 바이너리 배포를 쉽게 만들고, 로컬 실행도 간단합니다. 반면 Workers는 코드/바인딩 중심이고, runtime이 제공하는 API 범위 내에서 움직입니다.

이 차이는 단순한 DX 차이가 아니라, 운영과 장애 대응 방식 차이로 이어집니다. 예를 들어 “R2가 흔들릴 때 애플리케이션이 어떻게 넘어지는가” 같은 문제는, edge 런타임 위에서는 더 민감해집니다. 이 주제는 예전에 R2 장애 대응 글에서 ‘객체 스토리지 의존성 분해’ 패턴으로 정리한 적이 있습니다. [Cloudflare R2 503 장애 대응: 객체 스토리지 의존성 분해](https://daewooki.github.io/posts/r2-503-outage-app-resilience-patterns/)

### 2) 상태(state)를 어디에 둘지 결정이 먼저 온다

Cloudflare는 storage 옵션을 문서로 정리하면서, stateful 워크로드에는 Durable Objects를 전면에 둡니다. Durable Objects는 강한 일관성을 전제로 하고, 요청은 해당 Object를 소유한 데이터센터로 라우팅된다고 설명합니다.[^7]

그리고 Durable Objects의 SQLite storage backend를 권장하고, `ctx.storage.sql` 같은 SQL API를 제공하는 쪽으로 문서가 정리돼 있습니다.[^8]

Deploy에서 “그냥 돌아가던” 상태ful 기능은, Workers로 오면 Durable Objects/D1/KV/R2 중 어디에 둘지부터 결정해야 하고, 그 결정이 아키텍처 결정을 강제합니다.

### 3) 로컬 개발은 wrangler + workerd로 수렴한다

workerd는 Cloudflare Workers와 같은 코드베이스 기반의 오픈소스 런타임이라고 GitHub README에서 명시하고, Wrangler(v3+)가 로컬에서 workerd를 사용한다고 안내합니다.[^9]

즉, “Deploy 같은 관리형 실행”이 빠지더라도, 개발/테스트 런타임은 workerd로 수렴할 가능성이 큽니다. 이번 합류가 workerd self-hosting을 first-class로 만들겠다는 선언과 맞물리는 이유입니다.[^2]

### 4) 보안 모델이 ‘권한(prompt)’이 아니라 ‘격리/플랫폼 방어’에 기댄다

Deno는 권한 모델이 제품 정체성 중 하나였고, Workers는 isolate 기반 멀티테넌시에서 defense-in-depth를 강조합니다. Workers 보안 모델 문서는 V8 bugs와 Spectre까지 직접 다룹니다.[^10]

이건 장단이 있습니다.

* 장점: 플랫폼 운영자가 보안 방어를 계속 투자하는 한, 개별 애플리케이션 팀이 저수준 이슈를 직접 끌어안지 않아도 된다.
* 단점: 그 방어가 ‘플랫폼 구현’에 속하므로, 이식성은 API 호환과 별개로 제한된다.

Cloudflare가 lock-in 비판에 대해 “차라리 다 똑같이 호환되면 좋겠지만, 혁신은 다르게 만드는 걸 요구한다”고 정면으로 써 둔 것도 이 맥락입니다.[^2]

## 현실적인 마이그레이션 예제: Deno Deploy WebSocket 룸을 Durable Objects로 옮기기

Deploy를 쓰는 팀에서 가장 자주 등장하는 패턴 중 하나가 “간단한 API + WebSocket + 룸 단위 상태”입니다. 채팅, 협업 커서, 라이브 상태 동기화가 전형적입니다.

여기서는 아래 요구를 가진 서비스를 Workers로 옮기는 예를 듭니다.

* `/rooms/:name`로 WebSocket 접속
* 룸별로 최근 메시지 50개를 저장(서버 재시작 후에도 유지)
* 룸은 다수이며, 룸별로 요청 순서를 강제(동시성 버그를 피함)

Durable Objects가 정확히 이 케이스를 겨냥한 모델이고, Cloudflare 문서에서도 Durable Objects는 “chat rooms, games, whiteboards” 같은 예시를 반복합니다.[^7]

### 프로젝트 구성

```bash
mkdir deno-deploy-exit-room
cd deno-deploy-exit-room

npm init -y
npm i -D wrangler typescript @cloudflare/workers-types

npx wrangler init --yes
```

Wrangler가 로컬에서 workerd로 개발 서버를 띄운다는 점은 공식 문서에 명시돼 있습니다.[^11]

`tsconfig.json` (핵심만)

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "Bundler",
    "lib": ["ES2022", "WebWorker"],
    "types": ["@cloudflare/workers-types"],
    "strict": true
  }
}
```

`wrangler.toml`

```toml
name = "deno-deploy-exit-room"
main = "src/worker.ts"
compatibility_date = "2026-10-11"

[durable_objects]
bindings = [
  { name = "ROOM", class_name = "Room" }
]

[[migrations]]
tag = "v1"
new_sqlite_classes = ["Room"]
```

Durable Objects에서 SQLite backend를 쓰는 설정 예시는 Cloudflare 문서에 `new_sqlite_classes`로 안내돼 있습니다.[^8]

### Worker 코드

`src/worker.ts`

```ts
export interface Env {
  ROOM: DurableObjectNamespace<Room>;
}

type WsMsg =
  | { t: "hello"; room: string }
  | { t: "history"; items: Array<{ id: number; ts: number; text: string }> }
  | { t: "say"; text: string }
  | { t: "event"; ts: number; text: string };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // health
    if (url.pathname === "/health") {
      return new Response("ok", { status: 200 });
    }

    // ws: /rooms/:name
    const m = url.pathname.match(/^\/rooms\/([^/]+)$/);
    if (!m) return new Response("not found", { status: 404 });

    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("expected websocket", { status: 426 });
    }

    const roomName = decodeURIComponent(m[1]);
    const id = env.ROOM.idFromName(roomName);
    const stub = env.ROOM.get(id);

    // Durable Object로 WebSocket을 위임하면 룸 단위 직렬성이 생깁니다.
    return stub.fetch(new Request(url.toString(), request));
  },
};

export class Room extends DurableObject {
  private sessions = new Set<WebSocket>();
  private roomName: string;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.roomName = "unknown";

    // DO가 살아있을 때 메모리 상태 복원 (재시작/eviction 대비)
    ctx.blockConcurrencyWhile(async () => {
      // SQLite 테이블 준비
      ctx.storage.sql.exec(
        `CREATE TABLE IF NOT EXISTS messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts INTEGER NOT NULL,
          text TEXT NOT NULL
        );`
      );
    });
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const m = url.pathname.match(/^\/rooms\/([^/]+)$/);
    if (!m) return new Response("not found", { status: 404 });
    this.roomName = decodeURIComponent(m[1]);

    const pair = new WebSocketPair();
    const client = pair[0];
    const server = pair[1];

    server.accept();
    this.sessions.add(server);

    // 접속 직후 인사 + 히스토리 전송
    this.send(server, { t: "hello", room: this.roomName });
    this.send(server, { t: "history", items: await this.loadRecent(50) });

    server.addEventListener("message", (evt) => {
      void this.onMessage(server, evt);
    });

    server.addEventListener("close", () => {
      this.sessions.delete(server);
    });

    server.addEventListener("error", () => {
      this.sessions.delete(server);
    });

    return new Response(null, { status: 101, webSocket: client });
  }

  private send(ws: WebSocket, msg: WsMsg) {
    try {
      ws.send(JSON.stringify(msg));
    } catch {
      // ignore
    }
  }

  private broadcast(msg: WsMsg) {
    const payload = JSON.stringify(msg);
    for (const ws of this.sessions) {
      try {
        ws.send(payload);
      } catch {
        this.sessions.delete(ws);
      }
    }
  }

  private async onMessage(ws: WebSocket, evt: MessageEvent) {
    const text = typeof evt.data === "string" ? evt.data : "";
    if (!text) return;

    let parsed: WsMsg | null = null;
    try {
      parsed = JSON.parse(text);
    } catch {
      // plain text를 say로 취급
      parsed = { t: "say", text };
    }

    if (!parsed || parsed.t !== "say") return;

    const ts = Date.now();
    const clean = parsed.text.slice(0, 2000);

    // SQLite에 저장
    const r = this.ctx.storage.sql.exec(
      "INSERT INTO messages (ts, text) VALUES (?, ?)",
      ts,
      clean
    );

    // exec()는 cursor 형태를 반환합니다. 방금 insert한 id는 별도 조회.
    // 여기서는 단순히 최근 메시지를 다시 읽어오는 비용을 감수합니다.
    // (실서비스라면 insert id를 얻는 패턴을 더 깔끔하게 잡는 편이 낫습니다.)

    this.broadcast({ t: "event", ts, text: clean });

    // keep last 200
    this.ctx.storage.sql.exec(
      "DELETE FROM messages WHERE id NOT IN (SELECT id FROM messages ORDER BY id DESC LIMIT 200)"
    );
  }

  private async loadRecent(limit: number) {
    const out: Array<{ id: number; ts: number; text: string }> = [];

    const cursor = this.ctx.storage.sql.exec(
      "SELECT id, ts, text FROM messages ORDER BY id DESC LIMIT ?",
      limit
    );

    for (const row of cursor) {
      // row는 array-like
      out.push({ id: row[0] as number, ts: row[1] as number, text: row[2] as string });
    }

    out.reverse();
    return out;
  }
}
```

Durable Objects에서 SQLite API(`ctx.storage.sql`)를 통해 테이블을 만들고 쿼리하는 방식은 Cloudflare Durable Objects 문서의 방향성과 일치합니다.[^12]

### 실행

```bash
npx wrangler dev
```

예상 출력(형태)

```text
⛅️ wrangler 3.x
Your Worker has access to the following bindings:
- Durable Objects:
  - ROOM: Room

Listening on http://127.0.0.1:8787
```

헬스 체크:

```bash
curl -i http://127.0.0.1:8787/health
```

```text
HTTP/1.1 200 OK
...

ok
```

WebSocket 테스트는 `wscat` 같은 도구를 쓰면 됩니다.

```bash
npx wscat -c ws://127.0.0.1:8787/rooms/general
```

처음 접속하면 다음과 같은 메시지를 받습니다.

```json
{"t":"hello","room":"general"}
{"t":"history","items":[]}
```

그리고 클라이언트에서 `{"t":"say","text":"hi"}`를 보내면 다른 세션에도 브로드캐스트됩니다.

이 예제의 포인트는 코드가 멋있어 보이는 게 아니라, 마이그레이션의 본질이 “HTTP 서버를 옮기는 것”이 아니라 “상태를 어디에 둘지 바꾸는 것”이라는 점입니다. Deploy에서 로컬 메모리나 단순 KV로 어찌저찌 됐던 기능이, Workers에서는 Durable Objects로 정리되는 순간 서비스 설계가 고정됩니다.

## 대체 경로(자체 호스팅): workerd와 celld가 의미하는 ‘탈출구’의 형태

Cloudflare가 lock-in 논쟁을 정면으로 다루면서 반복하는 메시지가 하나 있습니다.

* “Workers Runtime(workerd)는 오픈소스이며, 프로덕션과 같은 코드다”
* “탈출구를 주는 게 비즈니스에도 좋다”

Cloudflare 발표문에는 workerd가 오픈소스이고 프로덕션과 동일 코드라고 직접 적혀 있습니다.[^2]

workerd GitHub README도 “Cloudflare Workers를 구동하는 것과 같은 코드 기반의 JavaScript/Wasm 서버 런타임”이라고 명시합니다.[^9]

문제는 여기서부터입니다. 오픈소스 런타임이 있다는 사실과, 실서비스를 다른 곳에서 굴릴 수 있다는 사실은 다릅니다. Cloudflare는 workerd의 Durable Objects가 단일 인스턴스에 머물러 self-host production readiness의 큰 갭이라고 인정했고, 그 갭을 메우는 데 celld가 결정적이었다고 썼습니다.[^2]

celld는 Deno가 만든 “self-hosted, distributed Durable Objects”를 표방합니다. 저장소 설명에는 각 object가 SQLite DB를 갖고, 장기 상태는 S3-compatible/GCS/Azure Blob 같은 object storage에 둔다고 적혀 있습니다.[^13]

그리고 Cloudflare는 “workerd와 celld를 merge”하겠다고 밝혔고, Ryan과 Bert가 workerd self-hosting을 first-class로 만들 노력의 리더가 된다고 했습니다.[^2]

이 조합이 의미하는 현실적인 선택지는 세 갈래입니다.

1) Cloudflare Workers(관리형)로 이동해서 플랫폼 방어와 운영을 Cloudflare에 위임한다.
2) workerd 기반으로 로컬/테스트를 표준화하고, 장기적으로 self-host 가능한 포터블 아키텍처를 만든다.
3) celld 같은 구현을 통해 “Workers 모델 자체를 온프레미스에 들여온다”는 목표를 잡는다(다만 이 경로는 구현 성숙도/운영 난이도 리스크가 존재).

### workerd 최소 실행 예시(로컬 단일 노드)

workerd 샘플은 Bazel 빌드로 설명되는 경우가 많지만, README에는 `npx workerd ...`로 실행할 수 있다고도 적혀 있습니다.[^9]

(환경에 따라 동작이 다를 수 있으니, 이 경로는 팀 표준으로 삼기 전에 반드시 CI에서 재현성을 확인해야 합니다.)

### celld가 주는 메시지

celld는 “one binary + object storage” 형태를 목표로 했다고 Cloudflare 발표문에서 소개됩니다.[^2] 그리고 celld 문서/저장소에도 Docker run, S3-compatible bucket 기반 운영, Cloudflare API 호환성 범위 등이 비교적 자세히 정리돼 있습니다.[^14]

다만 이건 ‘탈출구’가 생긴다는 의미이지, 곧바로 ‘낮은 비용으로 이탈’이 된다는 뜻은 아닙니다.

* Workers 모델로 설계된 서비스가 많을수록, 다른 플랫폼으로 옮길 때 아키텍처 변경이 커진다(특히 Durable Objects 의존).
* self-hosting은 결국 플랫폼 운영이며, 툴이 좋아져도 SRE/관측/배포/복구가 필요해진다.

나는 Cloudflare PoP 장애가 SLO를 깨는 방식을 따로 분석한 적이 있는데, edge 플랫폼은 “내 서버가 죽었다”보다 “구간/라우팅/의존 서비스가 흔들렸다”가 더 흔합니다. 그걸 self-host로 가져오면, 그 책임이 고스란히 팀으로 내려옵니다. [Cloudflare Ashburn(IAD) 구간 5xx 급증이 SLO를 깨는 방식](https://daewooki.github.io/posts/cloudflare-iad-pop-outage-slo/)

## 반론과 회의론: ‘오픈소스면 누군가가 이어받는다’가 항상 성립하지 않는다

이번 건을 두고 가장 흔한 낙관론은 이겁니다.

* Deno runtime은 오픈소스이니, 누군가가 계속 유지보수할 것이다.

그런데 런타임은 일반 라이브러리와 다르게 “유지보수의 비용 구조”가 다릅니다.

* 릴리스 파이프라인(서명/아티팩트/멀티 OS)
* V8 업데이트/패치 통합
* 성능 회귀 대응
* 취약점 비공개 리포트 채널 운영

이게 개인/소수 자원으로 장기 지속되기 어렵습니다. 그래서 “누군가의 포크”가 아니라 “새로운 주체(재단/기업/대규모 커뮤니티)가 유지보수 책임을 공식적으로 가져가는가”가 핵심인데, 2026-10-11 기준으로 그 부분은 공지에 없습니다.[^1]

다른 한편으로는 Cloudflare가 Deno 팀을 데려갔으니 결과적으로 runtime에도 도움이 될 거라는 기대가 있는데, 공지는 정반대의 메시지를 담고 있습니다.

* Deno 팀은 Workers/workerd 쪽 shared platform에 미래 개발을 집중한다.
* 별도의 runtime/hosting은 더 이상 개발하지 않는다.

이 구조에서는 “Deno runtime이 Cloudflare 내부에서 전략적으로 필요해져서 다시 투자 대상이 된다” 같은 반전이 일어나지 않는 한, 런타임은 자연스럽게 동결되는 게 기본 시나리오입니다.

## 앞으로 지켜볼 것: 2027-10-09 이후 ‘책임의 이름’이 드러나는 지점

2027-10-09 전후에 Deno runtime 개발이 종료된다고 했을 때(1년 지원), 그 이후를 예측하려면 추상적인 전망보다 관측 가능한 신호를 봐야 합니다.[^1]

### 1) Deno release/LTS 정책과 공지의 정합성

Deno 문서에는 LTS 채널이 존재하고, 예를 들어 Deno 2.9 LTS 라인이 2027-01-31까지 유지된다고 적혀 있습니다(문서 최종 업데이트 2026-07-16).[^4]

여기서 현실적인 질문이 생깁니다.

* 2027-01-31까지의 LTS 유지가 이번 “1년 월간 릴리스” 약속과 어떻게 합쳐지는가?
* 2027-10-09 이후 LTS는 누가 유지하는가?

문서/릴리스 노트/실제 GitHub 릴리스 주기를 통해 정합성을 확인해야 합니다.

### 2) workerd+celld merge가 실제로 “분산 Durable Objects”를 표준화하는가

Cloudflare는 workerd의 Durable Objects가 단일 인스턴스라는 갭을 인정했고, celld 아이디어를 workerd로 merge하겠다고 말했습니다.[^2]

그런데 merge는 선언이지 완료가 아닙니다. 관건은 아래입니다.

* self-host에서 운영 가능한 라우팅/스토리지/복제 모델이 공식 문서로 내려오는가
* 버전 호환성(Cloudflare Workers와 bug-for-bug 호환)을 어떻게 검증/보증할 것인가

celld 문서에 “workerd를 reference output으로 삼아 동일 출력이 나와야 한다”는 식의 테스트 철학이 이미 적혀 있습니다.[^15] 이 접근이 workerd 본체로 흡수될 때 어떤 형태로 제도화되는지가 중요합니다.

### 3) `rusty_v8`의 역할 변화

Deno 공지는 `rusty_v8`를 계속 지원하고 workerd로 통합하는 방향을 언급합니다.[^1]

이건 단순 기여가 아니라, 런타임 레벨의 핵심 부품을 Workers 생태계로 옮기는 작업입니다. 만약 이 통합이 진척되면, Deno runtime이 아니라 workerd가 Deno 팀의 ‘주력 런타임’이 된다는 해석이 더 강해집니다.

## 지금 할 수 있는 일: 마이그레이션을 프로젝트가 아니라 리스크 모델로 분해

2026-10-11(KST) 기준으로 적절한 대응은 “지금 당장 전부 옮긴다”가 아니라, 시스템적으로 리스크를 측정 가능한 형태로 만드는 것입니다.

### 1) Deno 의존성 인벤토리와 등급화

* Deno runtime을 쓰는 실행 단위를 전부 수집: API 서버, 배치, CLI, 내부 도구, edge 함수
* 외부 노출 여부로 1차 분류: Internet-facing / 내부망 / 개발환경
* 업그레이드 윈도우로 2차 분류: 무중단 가능 / 정기 점검 필요 / 장기 동결

여기서 “인터넷에 열려 있고, 런타임 취약점이 곧 RCE/정보유출로 이어질 수 있는 서비스”부터 별도의 탈출 경로를 준비하는 게 비용 대비 효과가 큽니다.

### 2) Deno runtime 유지 전략을 ‘포크 가능성’까지 포함해 작성

1년 뒤 공식 개발이 종료된다고 했기 때문에, 2027-10-09 이후를 가정한 운영 문서가 필요합니다.[^1]

* 내부 빌드 재현성: 소스에서 빌드 가능한가, 아티팩트 검증은 가능한가
* 취약점 대응 루트: 업스트림이 없을 때 누가 triage하고, 어떤 기준으로 업그레이드/패치할 것인가
* 대체 런타임 후보: Node.js, Workers/workerd, Bun 등(서비스 성격별)

이건 기술 선택의 문제가 아니라, “보안 패치를 누가 보장하는가”라는 조직 설계 문제에 가깝습니다.

### 3) Deploy 종료(6개월)에 맞춘 ‘기능별 분리’

Deploy에서 옮길 때는 애플리케이션을 통째로 옮기기보다 기능을 쪼개는 편이 안전합니다.

* 정적 자산/SSR
* API
* WebSocket/실시간
* 크론/큐/백그라운드
* 저장소

특히 저장소는 일찍 분리할수록 좋습니다. 실행 환경을 바꿔도 데이터 경로가 고정되면, 마이그레이션은 훨씬 단순해집니다.

### 4) Workers/workerd로 갈 경우, “상태ful 설계의 잠금(lock)”을 의식적으로 다룬다

Cloudflare가 lock-in 논의를 전면에 올린 건 이유가 있습니다. Durable Objects는 강력하지만 아키텍처를 규정합니다.[^2]

내 경우라면 아래 원칙을 세웁니다.

* Durable Objects는 coordination과 세션/룸 같은 강한 순서가 필요한 곳에만 쓴다.
* 장기 데이터는 가능한 한 표준 DB(PostgreSQL 등)로 빼고, Workers는 접근 계층으로 둔다.

Workers가 커질수록 데이터와 런타임을 분리하는 습관이 더 중요해지는데, 이건 예전에 Python Workers를 실서비스로 운영할 때 체크리스트 형태로 정리해 둔 것과 결이 같습니다. [Cloudflare Python Workers를 실서비스로 운영하기 위한 체크리스트](https://daewooki.github.io/posts/cloudflare-python-workers-production-checklist/)

결론적으로, 이번 “Deno 팀의 Cloudflare 합류”는 런타임의 존속 여부 논쟁이 아니라, 2027-10-09 이후 Deno runtime을 쓰는 조직이 보안 패치와 릴리스 운영의 주체가 되느냐, 아니면 Workers/workerd라는 다른 주체로 책임을 이전하느냐를 강제하는 사건입니다.

## 참고 자료

- [Deno 공식 발표: Deno is joining Cloudflare](https://deno.com/blog/cloudflare)
- [Cloudflare 공식 발표: Deno is joining Cloudflare](https://blog.cloudflare.com/deno-joins-cloudflare/)
- [TechCrunch 보도: Cloudflare acquires Deno to improve its Workers programming model](https://techcrunch.com/2026/10/10/cloudflare-acquires-deno-to-improve-its-workers-programming-model/)
- [Deno Docs: Stability and releases](https://docs.deno.com/runtime/fundamentals/stability_and_releases/)
- [Deno Docs: Release Schedule](https://docs.deno.com/runtime/contributing/release_schedule/)
- [Cloudflare Workers docs: How Workers works](https://developers.cloudflare.com/workers/reference/how-workers-works/)
- [Cloudflare Workers docs: Security model](https://developers.cloudflare.com/workers/reference/security-model/)
- [Cloudflare Durable Objects docs: Getting started](https://developers.cloudflare.com/durable-objects/get-started/)
- [Cloudflare Durable Objects docs: SQLite storage API](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/)
- [Cloudflare Durable Objects docs: Access Durable Objects Storage](https://developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-storage/)
- [workerd GitHub README](https://github.com/cloudflare/workerd/blob/main/README.md)
- [celld GitHub](https://github.com/denoland/celld)
- [celld Cloudflare API compatibility 문서](https://github.com/denoland/celld/blob/main/docs/cloudflare-compat.md)

[^1]: <https://deno.com/blog/cloudflare>
[^2]: <https://blog.cloudflare.com/deno-joins-cloudflare/>
[^3]: <https://techcrunch.com/2026/10/10/cloudflare-acquires-deno-to-improve-its-workers-programming-model/>
[^4]: <https://docs.deno.com/runtime/fundamentals/stability_and_releases/>
[^5]: <https://docs.deno.com/deploy/>
[^6]: <https://developers.cloudflare.com/workers/reference/how-workers-works/?ref=davidgomes.com>
[^7]: <https://developers.cloudflare.com/workers/platform/storage-options/>
[^8]: <https://developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-storage/>
[^9]: <https://github.com/cloudflare/workerd/blob/main/README.md?plain=1>
[^10]: <https://developers.cloudflare.com/workers/reference/security-model/>
[^11]: <https://developers.cloudflare.com/workers/wrangler/commands/workers/>
[^12]: <https://developers.cloudflare.com/durable-objects/get-started/>
[^13]: <https://github.com/denoland/celld?aid=recl9Ax7Mp7YFhks1>
[^14]: <https://celld.dev/>
[^15]: <https://celld.dev/docs/testing/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
