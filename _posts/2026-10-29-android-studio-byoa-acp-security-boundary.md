---
title: "Android Studio Rabbit 2 BYOA/ACP: IDE 내 에이전트 권한 경계 설계"
description: "BYOA는 에이전트를 IDE에 붙이는 편의 기능이 아니라, 권한·비밀키·기업 정책을 한 번에 재정의하는 통합 지점입니다."
date: 2026-10-29 14:19:08 +0900
categories: ["Mobile", "Android Studio"]
tags: ["android-studio", "byoa", "acp", "ide-security", "agentic-dev", "policy-proxy"]
render_with_liquid: false
---

## Rabbit 2에서 BYOA가 의미하는 것: ‘AI 기능’이 아니라 권한 재배치
Android Studio Rabbit 2(2026.2.2)에서 **BYOA**가 안정 채널로 들어오면서, IDE 안의 에이전트는 “추천 모델 하나 더 붙였다” 수준을 넘어섰습니다. 공식 릴리스 노트는 BYOA를 Agent Client Protocol(ACP) 기반으로, 외부 코딩 에이전트를 Android Studio에 연결하는 방식으로 소개하고, 그 대가로 에이전트가 IDE-native 정보/도구에 직접 접근할 수 있다고 명시합니다. 특히 “full project graph, build diagnostics, emulator controls”를 에이전트에 전달한다고 적어 둔 문장이 핵심입니다. 

- [Android Studio Rabbit 2 릴리스 노트](https://developer.android.com/studio/releases?skip_cache=false)는 BYOA가 ACP로 Claude Agent, OpenAI Codex, Google Antigravity 같은 에이전트를 연결하고, 프로젝트 그래프/빌드 진단/에뮬레이터 제어를 에이전트에 패스한다고 씁니다.[^1]
- 2026년 10월 28일(UTC)에 게시된 [Android Developers Blog의 Rabbit 2 안정 릴리스 글](https://developer.android.com/blog/posts/ai-agents-android-studio-integration)도 Android Emulator, Build Systems, Logcat 같은 “Android Studio tools”에 에이전트가 접근한다고 재확인합니다.[^2]

여기서 관점을 바꾸면 빠르게 정리가 됩니다.

1) IDE는 원래도 강력한 권한을 가진 로컬 애플리케이션이었습니다(프로젝트 파일, 빌드, 디바이스, 인증서, 네트워크까지). 
2) BYOA는 그 권한을 “모델에게 문장으로 위임”하는 게 아니라 “프로토콜로 노출된 API를 통해 에이전트가 호출 가능”한 형태로 정리합니다.
3) 그러면 BYOA/ACP는 UX 기능이 아니라, 보안/감사/정책을 걸 수 있는 새 경계가 됩니다.

내가 이전 글에서 IDE가 “자동완성”을 넘어 “에이전트 OS”처럼 변한다고 정리했는데[^3], Rabbit 2의 BYOA는 그 변화를 “표준 연결점(ACP)”으로 못 박았다는 데 의미가 있습니다. 이제는 “누가 어떤 모델 쓰는지”만 관리하는 단계가 아니라, “IDE가 제공하는 실행 권한을 어떤 정책으로 에이전트에게 열어줄지”를 설계해야 합니다.

## ACP를 ‘채팅 연결’이 아니라 IDE 권한 API로 읽어야 한다
ACP는 JSON-RPC 2.0 기반으로 Client(IDE)와 Agent(에이전트 프로세스)가 세션을 만들고, 프롬프트를 주고받고, 파일/터미널 같은 기능을 요청하는 형태로 구성됩니다. ACP 스펙의 큰 특징은 “세션”과 “도구 호출(tool call)”을 1급 객체로 다룬다는 점입니다.

ACP v1 문서의 [Prompt Turn](https://agentclientprotocol.com/protocol/v1/prompt-turn)은 한 번의 상호작용이 `session/prompt`로 시작해서 `session/update` 스트림으로 진행되며, 업데이트 타입(`sessionUpdate`)에 `tool_call`, `tool_call_update`, `plan` 같은 항목이 포함된다고 설명합니다. 또한 Client가 `session/cancel`로 턴을 취소할 수 있고, 취소 이후에도 tool call 업데이트를 받을 수 있다고 명시합니다.[^4]

이 구조를 IDE 통합 관점에서 보면 ACP는 “대화”보다 “행동”을 잘 표현합니다.

- 에이전트가 어떤 행동을 시작했는지(tool call)
- 그 행동이 진행 중인지/끝났는지(tool_call_update)
- 진행 중인 동안 어떤 출력이 발생했는지(스트리밍)
- 계획이 무엇인지(plan)

즉, ACP는 모델 출력 텍스트만 중계하는 프로토콜이 아니라, IDE가 권한을 가진 작업(파일/터미널/기타 도구)을 에이전트가 요청하고, 상태가 추적되며, 취소/감사가 가능한 구조를 제공합니다. 이게 바로 “통합 지점”이 되는 이유입니다.

## (1) 프로젝트 그래프·빌드 진단·에뮬레이터 제어는 어떤 권한 묶음인가
릴리스 노트와 블로그 글이 공통으로 강조하는 것은 “Android Studio가 가진 정보를 에이전트에 직접 넘기고, Android Studio tools를 에이전트가 쓸 수 있다”는 점입니다. 

- [Android Studio Rabbit 2 릴리스 노트](https://developer.android.com/studio/releases?skip_cache=false)는 프로젝트 그래프/빌드 진단/에뮬레이터 제어를 패스한다고 적습니다.[^1]
- [Your favorite agents are now integrated in Android Studio](https://developer.android.com/blog/posts/ai-agents-android-studio-integration)는 Android Emulator, Build Systems, Logcat에 접근할 수 있다고 씁니다.[^2]
- 2026년 9월 24일에 게시된 [Build your way: Use any AI agent of your choice in Android Studio](https://android-developers.googleblog.com/2026/09/build-your-way-use-any-ai-agent-in-android-studio.html)도 “full project graph, build setup, platform details”를 ACP로 제공한다고 말합니다.[^5]

여기서 “프로젝트 그래프”는 단순히 파일 목록이 아닙니다. Android 프로젝트는 Gradle 빌드, 모듈 의존성, variant, productFlavor, buildType, sourceSet, generated sources, AndroidManifest merge 결과, 리소스 병합 결과까지 포함해서 ‘의미 있는 그래프’가 됩니다. 이 정보가 에이전트에 전달되면 어떤 일이 일어나냐면:

- 코드베이스 이해가 빨라지는 정도가 아니라, “빌드가 왜 깨졌는지”를 기계적으로 재현할 수 있는 입력이 생깁니다.
- 특정 모듈/variant에서만 발생하는 문제를 에이전트가 구분할 수 있습니다.
- IDE가 알고 있는 진단(린트/인스펙션/Gradle sync 에러/stacktrace)을 근거로 수정안을 만들게 됩니다.

“에뮬레이터 제어”도 가볍게 보면 안 됩니다. Android Emulator 제어 권한은 곧 실행 환경 제어 권한입니다.

- 테스트 대상 APK 설치/실행
- 디바이스 상태(네트워크, 센서, 로케일 등) 변화
- 로그(Logcat) 접근

이 권한 묶음은 CI에서의 권한(빌드/테스트/패키징)과 로컬 개발 환경에서의 권한을 한데 묶습니다. 개발자가 명시적으로 요청하지 않아도 에이전트가 스스로 “재현을 위해 실행”을 선택할 수 있는 길이 열립니다.

정리하면 BYOA가 제공하는 건 “똑똑한 답변”이 아니라 “IDE-권한 기반 자동 실행”의 표준화입니다. 그리고 그 표준화가 ACP로 들어오면서 권한 경계도 ACP 레이어에서 설계할 수 있게 됩니다.

## (2) 비밀키·구독 인증: ‘에이전트 로그인’이 IDE 보안의 일부가 된다
BYOA는 사용자가 기존에 쓰던 에이전트/구독을 IDE로 가져오게 해 줍니다. 릴리스 노트는 개인 API key와 소비자 구독을 지원한다고 적고, “personal or enterprise subscriptions”로 인증할 수 있다고 설명합니다.[^1]

여기서부터가 진짜 문제입니다.

- IDE는 프로젝트 폴더에 `local.properties`, `keystore`, `.env`, CI 토큰, 사내 레포 접근 토큰 등이 섞여 있을 수 있습니다.
- 반대로 에이전트는 provider 구독(예: OpenAI/Anthropic/기타) 인증 토큰을 쥐고 있을 수 있습니다.

이 두 세계가 BYOA에서 만나면, “개발자 개인 키 관리” 문제가 “조직의 지적재산/공급망/감사” 문제로 확장됩니다.

ACP 스펙도 인증을 1급으로 다룹니다. [Authentication](https://agentclientprotocol.com/protocol/v1/authentication)은 에이전트가 `authMethods`를 광고하고, Client가 `authenticate`를 호출하는 “프로토콜 주도 인증” 흐름이 있음을 설명합니다. 또한 `terminal` 타입 인증 메서드(에이전트를 인터랙티브로 실행해 로그인)를 별도로 다루며, Client가 `clientCapabilities.auth.terminal`을 광고해야만 terminal login을 사용할 수 있다고 명시합니다.[^6]

이게 왜 중요하냐면, 인증이 ‘채팅 창 밖’으로 튀어나가는 순간이 생기기 때문입니다.

- browser/device-code 로그인
- terminal에서 로그인 실행
- IDE가 에이전트 프로세스를 재시작해야 토큰이 반영되는 케이스

이런 흐름은 전통적인 IDE 플러그인 보안 모델(권한은 IDE 내부에서 끝난다)과 다릅니다. 에이전트는 별도 프로세스이며, 그 프로세스가 어떤 credential store를 쓰는지, 어떤 디렉터리에 토큰을 저장하는지, 토큰이 어떤 scope를 갖는지가 IDE 통제 밖으로 나가기 쉽습니다.

여기서 내가 선호하는 방향은 “키를 에이전트 프로세스에 직접 주지 않는 것”입니다. Google AI 쪽 문서인 [Credentials in managed agents](https://ai.google.dev/gemini-api/docs/agent-credentials?hl=en)는 credential을 서버 관리 비밀로 저장하고, 네트워크 allowlist 규칙에 credential을 붙여 egress proxy가 요청 시점에 주입하는 패턴을 권장합니다. 이 접근은 “에이전트 환경에 secret이 들어가지 않는다”는 점을 명시합니다.[^7]

Android Studio BYOA가 당장 이 모델을 그대로 제공한다고 단정할 수는 없지만, 최소한 기업 환경에서 “에이전트 프로세스가 로컬 디스크/환경변수에서 평문 키를 읽는 구조”는 빨리 끝내야 합니다. BYOA가 표준이 되는 순간, 그 방식은 가장 흔한 유출 경로가 됩니다.

## (3) 기업 정책: 허용 모델/네트워크/로깅을 IDE 안에서 끝내면 안 된다
Android Studio 자체도 이미 에이전트 권한을 UI로 노출하기 시작했습니다.

- [Manage agent permissions](https://developer.android.com/studio/gemini/permissions)는 에이전트가 파일 읽기/쓰기, shell command 실행, 웹 도메인 접근, MCP 서버 상호작용 같은 권한을 요청하고 “Allow / Always allow”로 제어할 수 있다고 설명합니다. 또 `.aiexclude`, SSH key, password file은 별도 명시적 승인이 필요하다고 적습니다.[^8]
- [Configure context sharing with .aiexclude files](https://developer.android.com/studio/gemini/aiexclude)는 `.aiexclude`로 Gemini 컨텍스트 공유에서 제외할 파일을 정의하며, AI 기능이 프로젝트 및 VCS root 밖 파일에는 접근할 수 없다고 명시합니다.[^9]

여기까지는 “개발자 개인 통제”에 가깝습니다. 기업 정책 관점에서는 더 많은 것이 필요합니다.

1) 허용되는 에이전트/모델/provider 정의(조직 계약, 데이터 처리 위치, 법무 조건)
2) 네트워크 egress 제어(어떤 도메인/리포지토리/패키지 레지스트리에 접근 가능한지)
3) 로깅과 감사(누가 어떤 권한으로 어떤 파일/명령을 실행하려 했는지, 차단/승인 기록)

그리고 중요한 건, 이 3가지는 UI 토글로 끝나지 않는다는 사실입니다. UI는 “현재 머신의 현재 사용자”만 다룹니다. 기업 정책은 “조직 단위의 일관성”과 “감사 가능한 기록”이 목표입니다.

Android Studio가 제공하는 Agent Shell Sandbox는 여기서 힌트가 됩니다. 공개된 searchable options 데이터에는 Agent Shell Sandbox에 Bubblewrap(Linux), macOS sandbox-exec, Docker container, custom wrapper command 같은 런타임 옵션이 등장합니다. 즉, Android Studio 자체도 “에이전트 실행을 OS 레벨 샌드박스/컨테이너/래퍼 명령으로 감쌀 수 있다”는 전제를 깔고 있습니다.[^10]

나는 이 기능을 “보안 옵션 하나”로 보지 않습니다. 기업 정책을 구현할 수 있는 가장 현실적인 레이어가 여기입니다.

- OS/컨테이너로 프로세스 권한을 강제
- 네트워크를 프록시로 강제(deny-by-default)
- 파일시스템 mount를 read-only로 기본값 설정
- 실행 가능한 파일 생성/수정 같은 위험 행위를 별도 정책으로 분리

모바일 쪽 운영 경험으로 비유하면, 이건 Android 기기 플릿에서 Android Security Bulletin 패치 레벨을 강제하고(내 블로그의 [Android Security Bulletin 패치 레벨로 플릿 업데이트 운영하기](https://daewooki.github.io/posts/android-spl-fleet-operations/)), 네트워크 로깅을 켜고, allowlist로 앱 설치를 제한하는 것과 같은 계열의 문제입니다. 실제로 Android Enterprise 쪽에는 네트워크 활동 로깅[^11]이나 정책 스코프[^12] 같은 도구가 이미 존재합니다. 개발자 도구의 에이전트 통합도 결국 이 방향으로 갈 수밖에 없습니다.[^13]

## ACP 보안 모델이 말하는 함정: “권한 승인”은 샌드박스가 아니다
ACP 스펙의 [Security Considerations](https://agentclientprotocol.com/protocol/v1/security)는 신뢰 모델을 매우 직설적으로 적습니다.

- 에이전트는 “프로세스에 주어진 권한”으로 실행되며, ACP 자체는 샌드박싱을 제공하지 않습니다.
- permission request는 advisory이고, 에이전트가 사용자의 결정을 존중해야 합니다.
- 반면 Client가 file system과 terminal 오퍼레이션을 직접 수행합니다.
- `clientInfo`/`agentInfo`는 self-reported이며 보안 결정에 쓰면 안 되고, Client는 “자기 런치 설정”으로 에이전트를 식별해야 한다고 씁니다.[^14]

이게 현실에서 의미하는 바는 다음과 같습니다.

- 승인 UI가 있어도, 그 자체로 “에이전트가 악성 행동을 못 한다”는 보장이 아닙니다.
- 에이전트 바이너리가 손상되거나 supply-chain 공격을 받으면, ACP는 그걸 막지 못합니다.
- 반대로 Client(IDE)가 수행하는 작업(fs/terminal)을 “어떤 정책으로 허용/거부할지”는 Client 구현과 그 위의 래퍼/프록시/샌드박스에 달립니다.

또 하나의 현실적인 함정은 “승인 피로도”입니다. Android Studio Panda 3 시기의 글에서도 approval fatigue를 언급하며 권한을 세분화하고 샌드박스를 옵션으로 제공한다고 설명합니다. 결국 권한 프롬프트만 늘리면 사용자는 빠르게 Always allow를 눌러 버립니다.[^15]

그래서 나는 “승인 UI를 정교하게”보다 “승인해야 하는 일을 줄이는 설계”를 먼저 둡니다.

- 기본적으로 write 권한은 닫아 둔다.
- 에이전트가 손대면 위험한 파일(예: 실행/승인/훅을 바꾸는 파일)은 별도 승인을 요구한다.
- 네트워크는 allowlist-first이고, 프록시를 강제한다.

ACP의 [File System](https://agentclientprotocol.com/protocol/v1/file-system)은 Client가 세션의 root set을 기준으로 path를 검사하고, root 밖이면 거부하거나 사용자에게 물어보라고 권고합니다. 또한 `fs/write_text_file`이 “실행/승인에 영향을 주는 파일(vcs hook, editor/agent settings, MCP config 등)”을 바꾸려 할 때는 사용자를 확인시키라고 적습니다.[^16]

이 문장들은 BYOA/ACP를 붙일 때 어디에 정책을 걸어야 하는지 직접 가리킵니다. 즉, 에이전트의 자연어 출력이 아니라 fs/terminal 같은 권한 API 호출을 ‘입구’로 보고 통제해야 합니다.

## 설계: BYOA/ACP를 ‘통합 지점’으로 만들기 위한 레퍼런스 아키텍처
Android Studio Rabbit 2 BYOA는 “원하는 에이전트를 IDE 안으로” 끌어옵니다. 이때 조직이 선택할 수 있는 아키텍처는 크게 3개입니다.

### 1) IDE 단독 통제(개발자 로컬 UI에 의존)
- 장점: 도입 비용 최소, 개발자 만족도 최대
- 단점: 조직 단위 일관성/감사/정책 집행이 약함

Android Studio의 Agent Permissions / `.aiexclude` / Shell Sandbox만으로 해결하려는 접근입니다. 개인 개발 환경 수준에서는 충분할 수 있지만, BYOA가 “개인 API key/개인 구독”을 끌고 들어오는 순간, 회사 기준으로는 구멍이 생깁니다.[^8]

### 2) 에이전트 실행을 샌드박스/컨테이너로 강제(프로세스 경계)
- 장점: OS 레벨 강제력이 생김
- 단점: IDE와의 통합(파일/디바이스/로그)에서 운영 난이도 상승

Agent Shell Sandbox가 제공하는 옵션(Bubblewrap, sandbox-exec, Docker, custom wrapper)을 활용해 프로세스 권한을 강제하는 방식입니다. 이 레이어는 “에이전트 바이너리가 무엇을 할 수 있는지”를 직접 줄일 수 있다는 점에서 강력합니다.[^10]

### 3) ACP 레이어에 Policy Proxy를 두고, 위험 RPC를 차단/감사(프로토콜 경계)
- 장점: fs/terminal 같은 권한 호출을 ‘입구에서’ 통제 가능, 중앙 로깅/정책화에 유리
- 단점: 프록시가 프로토콜 변화(ACP v2 등)에 따라 유지보수 대상이 됨

내 결론은 “2 + 3 조합”이 장기적으로 이깁니다.

- 2는 “프로세스가 뚫려도 못 나가게” 만드는 물리적 경계이고,
- 3은 “IDE가 수행하는 권한 작업을 어떤 규칙으로 허용할지”를 정의하는 논리적 경계입니다.

여기서 중요한 사실 하나. Android 쪽 가이드 문서[^17]는 Android Studio가 ACP로 에이전트를 연결할 때 “이미 떠 있는 에이전트에 붙는 게 아니라, Android Studio가 ACP를 통해 에이전트 인스턴스를 시작한다”고 명시합니다.[^17]

즉, IDE가 에이전트를 ‘런치’하는 구조라면, 우리가 끼워 넣을 수 있는 위치도 선명해집니다.

- Android Studio가 실행하는 커맨드를 “실제 에이전트”가 아니라 “Policy Proxy(래퍼)”로 바꾼다.
- Proxy가 실제 에이전트를 다시 실행한다.
- Proxy가 agent→client 방향의 RPC를 검사해서 `fs/write_text_file` 같은 위험 요청을 차단한다.
- Proxy가 결정(허용/차단/리다이렉트)을 감사 로그로 남긴다.

ACP 스펙이 말하는 “Client가 fs/terminal을 수행한다”는 구조와도 잘 맞습니다. agent가 던지는 요청을 client에게 넘기기 전에, proxy가 admission control을 할 수 있습니다.

## 구현: `fs/write_text_file`을 정책으로 차단하는 ACP Policy Proxy (Rust)
아래 코드는 “Android Studio(ACP Client) ↔ (Proxy) ↔ (실제 ACP Agent)” 사이에 끼워 넣는 프록시의 최소 구현입니다. 핵심 목적은 두 가지입니다.

1) `fs/write_text_file`을 특정 경로 규칙으로 차단
2) 차단 사유를 stderr 로그로 남겨 감사 가능하게 만들기

주의할 점을 먼저 적습니다.

- ACP는 JSON-RPC 2.0 over stdio입니다. 메시지 프레이밍(한 줄에 JSON 1개인지 등)은 구현체/SDK에 따라 달라질 수 있습니다. 아래 코드는 “newline-delimited JSON” 가정으로 동작합니다. production에서는 실제 에이전트가 사용하는 ACP transport에 맞춰 프레이밍을 확정해야 합니다.
- 그래도 이 접근이 유효한 이유는, ACP에서 `fs/write_text_file` 같은 권한 요청이 명시적 JSON-RPC method로 표현되고, Client가 이를 수행한다는 사실 자체는 스펙에 박혀 있기 때문입니다.[^16]

### 빌드 환경
- Rust: 1.78+ (tokio 사용)
- OS: macOS/Linux/WSL 모두 가능

### 프로젝트 구조
```text
acp-policy-proxy/
  Cargo.toml
  src/
    main.rs
```

### `Cargo.toml`
```toml
[package]
name = "acp-policy-proxy"
version = "0.1.0"
edition = "2021"

[dependencies]
tokio = { version = "1", features = ["rt-multi-thread", "macros", "process", "io-util"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
anyhow = "1"
regex = "1"
```

### `src/main.rs`
```rust
use anyhow::{anyhow, Context, Result};
use regex::Regex;
use serde_json::Value;
use std::{env, path::PathBuf};
use tokio::{
    io::{self, AsyncBufReadExt, AsyncWriteExt, BufReader},
    process::{ChildStdin, Command},
};

#[derive(Clone, Debug)]
struct Policy {
    allowed_roots: Vec<PathBuf>,
    deny_path: Vec<Regex>,
}

impl Policy {
    fn from_env() -> Result<Self> {
        // 예: /repo,/repo2 처럼 콤마로 구분
        let roots = env::var("ACP_ALLOWED_ROOTS")
            .unwrap_or_else(|_| "".to_string())
            .split(',')
            .filter(|s| !s.trim().is_empty())
            .map(|s| PathBuf::from(s.trim()))
            .collect::<Vec<_>>();

        if roots.is_empty() {
            return Err(anyhow!(
                "ACP_ALLOWED_ROOTS is empty. Set allowed repo roots, e.g. /path/to/repo"
            ));
        }

        // 기본 deny: 실행/승인/배포 경계에 가까운 파일들
        // (조직에 맞게 추가/수정)
        let deny = vec![
            r"(^|/)\.git/" ,
            r"(^|/)\.idea/" ,
            r"(^|/)\.gradle/" ,
            r"(^|/)gradle\.properties$" ,
            r"(^|/)local\.properties$" ,
            r"(^|/)\.github/workflows/" ,
            r"(^|/)keystore(s)?/" ,
            r"\.(jks|keystore|pem|p12)$" ,
        ]
        .into_iter()
        .map(|p| Regex::new(p).context("invalid deny regex"))
        .collect::<Result<Vec<_>>>()?;

        Ok(Self {
            allowed_roots: roots,
            deny_path: deny,
        })
    }

    fn is_under_allowed_root(&self, abs_path: &PathBuf) -> bool {
        self.allowed_roots
            .iter()
            .any(|root| abs_path.starts_with(root))
    }

    fn is_denied(&self, abs_path: &PathBuf) -> bool {
        let s = abs_path.to_string_lossy();
        self.deny_path.iter().any(|re| re.is_match(&s))
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    let policy = Policy::from_env()?;

    // Proxy가 실제 ACP agent를 어떻게 실행할지 정의합니다.
    // 예:
    //   ACP_TARGET_CMD=/usr/local/bin/codex
    //   ACP_TARGET_ARGS=acp
    let target_cmd = env::var("ACP_TARGET_CMD")
        .context("ACP_TARGET_CMD is required")?;
    let target_args = env::var("ACP_TARGET_ARGS").unwrap_or_default();
    let args = shell_words::split(&target_args).unwrap_or_else(|_| vec![]);

    eprintln!("[proxy] allowed_roots={:?}", policy.allowed_roots);
    eprintln!("[proxy] spawning target agent: {} {:?}", target_cmd, args);

    let mut child = Command::new(target_cmd)
        .args(args)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::inherit())
        .spawn()
        .context("failed to spawn target agent")?;

    let child_stdin = child.stdin.take().context("child stdin")?;
    let child_stdout = child.stdout.take().context("child stdout")?;

    let mut ide_in = BufReader::new(io::stdin()).lines();
    let mut ide_out = io::stdout();

    let mut agent_in = BufReader::new(child_stdout).lines();
    let mut agent_out = child_stdin;

    // 1) IDE -> Agent : 그대로 전달
    let ide_to_agent = async {
        while let Some(line) = ide_in.next_line().await? {
            agent_out.write_all(line.as_bytes()).await?;
            agent_out.write_all(b"\n").await?;
            agent_out.flush().await?;
        }
        Result::<()>::Ok(())
    };

    // 2) Agent -> IDE : fs/write_text_file 차단
    let agent_to_ide = async {
        while let Some(line) = agent_in.next_line().await? {
            // JSON 파싱 실패 시에도 일단 통과(프레이밍/형식 이슈를 깨닫기 위해 stderr 로그)
            let v: Value = match serde_json::from_str(&line) {
                Ok(v) => v,
                Err(e) => {
                    eprintln!("[proxy] WARN: failed to parse json: {e}; passthrough");
                    ide_out.write_all(line.as_bytes()).await?;
                    ide_out.write_all(b"\n").await?;
                    ide_out.flush().await?;
                    continue;
                }
            };

            // JSON-RPC request 객체에서 method 확인
            let method = v.get("method").and_then(|m| m.as_str()).unwrap_or("");

            if method == "fs/write_text_file" {
                let path = v
                    .get("params")
                    .and_then(|p| p.get("path"))
                    .and_then(|p| p.as_str())
                    .ok_or_else(|| anyhow!("fs/write_text_file without params.path"))?;

                let abs = PathBuf::from(path);

                let denied = !policy.is_under_allowed_root(&abs) || policy.is_denied(&abs);

                if denied {
                    let id = v.get("id").cloned().unwrap_or(Value::Null);

                    eprintln!("[proxy] BLOCK fs/write_text_file path={}", abs.display());

                    // Agent에게 JSON-RPC error response를 돌려줘야 대화가 멈추지 않습니다.
                    // 여기서는 에이전트(요청자)에게 에러를 반환하는 형태로 agent 쪽으로 써야 하지만,
                    // Proxy는 단순 파이프 구조라 IDE 방향/Agent 방향을 분리했습니다.
                    // 실환경에서는 '요청을 보낸 쪽'으로 에러를 라우팅해야 합니다.
                    //
                    // 이 샘플은 IDE가 수행하는 write 요청을 원천 차단하는 목적이라,
                    // IDE로는 해당 요청을 전달하지 않고, 대신 IDE에 상태를 알리는 notice를 보냅니다.
                    // (notice 지원은 initialize clientCapabilities에 달려 있으며, 여기서는 text로 통지)

                    let notice = serde_json::json!({
                        "jsonrpc": "2.0",
                        "method": "session/update",
                        "params": {
                            "sessionId": v.get("params").and_then(|p| p.get("sessionId")).cloned().unwrap_or(Value::String("".to_string())),
                            "update": {
                                "sessionUpdate": "agent_message_chunk",
                                "text": format!("[policy] BLOCKED: fs/write_text_file {}", abs.display())
                            }
                        }
                    });

                    ide_out.write_all(notice.to_string().as_bytes()).await?;
                    ide_out.write_all(b"\n").await?;
                    ide_out.flush().await?;

                    // 그리고 원래 요청은 버립니다.
                    // (완전한 프록시라면 agent에게 error response를 반환해야 함)
                    let _ = id;
                    continue;
                }
            }

            // 기본: 그대로 전달
            ide_out.write_all(line.as_bytes()).await?;
            ide_out.write_all(b"\n").await?;
            ide_out.flush().await?;
        }
        Result::<()>::Ok(())
    };

    // 동시 실행
    tokio::select! {
        r = ide_to_agent => { r?; }
        r = agent_to_ide => { r?; }
    }

    Ok(())
}

// shell_words는 Cargo.toml에 추가해야 합니다.
// 위 예시는 본문 길이 관계로 의존성 선언을 생략했습니다.
```

위 코드에는 의도적으로 “불완전한” 부분이 있습니다. 

- 프록시가 `fs/write_text_file` 요청을 차단할 때, 원래는 “요청을 보낸 에이전트”에게 JSON-RPC error response를 돌려줘야 프로토콜적으로 깔끔합니다.
- 샘플은 “IDE가 수행할 write를 막는다”에 집중해 IDE로만 안내 메시지를 보내고 요청을 드롭합니다.

실전에서는 다음 중 하나로 정리해야 합니다.

- Proxy가 “양방향 JSON-RPC 라우팅”을 구현해서, request/response를 id로 매칭하여 정확히 요청자에게 error를 반환
- 또는 Proxy 자체를 “ACP Agent”로 만들고(IDE 입장에서는 agent가 Proxy), 내부에서 진짜 agent를 호출하는 구조로 전환

그래도 이 샘플이 의미 있는 이유는 정책의 위치가 선명하기 때문입니다. 파일 쓰기를 막고 싶은 이유가 무엇이든(비밀키, 빌드 스크립트 변조, 승인 프로세스 우회), 그 제어점이 `fs/write_text_file` 같은 ACP 메서드라는 사실은 변하지 않습니다.[^16]

## 운영 설계: 로깅/감사/재현성은 IDE 로그(idea.log)만으로 부족하다
정책을 만들었다면, 다음은 “누가 무엇을 시도했고, 왜 막혔는지”를 남기는 일입니다.

Android Studio 자체 로그 위치는 공식 troubleshooting 문서에 정리되어 있습니다. 예를 들어 macOS는 `~/Library/Logs/Google/AndroidStudioVERSION` 형태이고, Windows/Linux도 각각 경로가 명시되어 있습니다.[^18]

하지만 BYOA/ACP의 감사 요구는 단순히 IDE 크래시를 조사하는 것과 다릅니다.

- 에이전트가 어떤 파일을 쓰려 했는지
- 어떤 도메인으로 나가려 했는지
- 어떤 shell command를 실행하려 했는지
- 그게 Agent Permissions에서 허용된 것인지, Shell Sandbox에서 제한된 것인지, 프록시 정책에 의해 막힌 것인지

이걸 idea.log만 보고 재구성하기는 어렵습니다. 결론은 명확합니다.

- 정책 프록시/래퍼는 자체적으로 구조화 로그(JSON)를 남겨야 합니다.
- 이 로그는 개발자 로컬 디스크가 아니라 중앙 로깅으로 수집 가능한 형태가 되어야 합니다.
- “차단 이벤트”는 보안 이벤트로 취급해야 하고, 단순 디버그 로그로 취급하면 안 됩니다.

모바일 앱 운영에서 보안 이벤트를 볼 때도, 앱 로그(Logcat)만으로는 부족하고 서버/MDM/네트워크 계층 로그와 합쳐야 의미가 생깁니다. BYOA도 정확히 같은 문제가 IDE에서 반복됩니다.

## 도입 판단: BYOA/ACP는 ‘편의 기능’이 아니라 경계면이다
Rabbit 2에서 BYOA가 안정 채널 기능이 된 시점(릴리스 게시가 2026년 10월 28일 UTC인 점까지 포함해서)을 기준으로, “IDE 내 에이전트”는 예외 기능이 아니라 기본 가정이 됐습니다.[^2]

이 상태에서 BYOA/ACP를 단순히 “원하는 모델로 갈아끼우는 UI”로만 다루면, 실제 권한은 아무도 소유하지 않습니다.

- 에이전트는 프로젝트 그래프/빌드 진단/에뮬레이터 같은 IDE 권한을 호출할 수 있고, 
- 인증은 개인/기업 구독과 API key를 IDE 워크플로우로 끌고 들어오며,
- 조직은 허용 모델/네트워크/로깅 정책을 기존 엔드포인트/MDM/프록시 체계와 연결해야 합니다.

ACP 스펙 자체가 “ACP는 샌드박스가 아니다”라고 말하고 있는 만큼, IDE 권한 API를 호출하는 입구를 정책적으로 소유하는 쪽이 결국 안정적으로 운영합니다.[^14]

## 참고 자료
- [Android Studio Rabbit 2 릴리스 노트](https://developer.android.com/studio/releases?skip_cache=false)
- [Android Studio Rabbit 2 Closed Issues (2026.2.2)](https://developer.android.google.cn/studio/releases/fixed-bugs/studio/2026.2.2)
- [Your favorite agents are now integrated in Android Studio (2026-10-28)](https://developer.android.com/blog/posts/ai-agents-android-studio-integration)
- [Build your way: Use any AI agent of your choice in Android Studio (2026-09-24)](https://android-developers.googleblog.com/2026/09/build-your-way-use-any-ai-agent-in-android-studio.html)
- [Choose the right tools for your agentic workflow (Android Studio with BYOA 언급)](https://developer.android.google.cn/ai-tools/guides/quickstart)
- [Manage agent permissions (Android Studio)](https://developer.android.com/studio/gemini/permissions)
- [Configure context sharing with .aiexclude files](https://developer.android.com/studio/gemini/aiexclude)
- [Agent Client Protocol v1: Prompt Turn](https://agentclientprotocol.com/protocol/v1/prompt-turn)
- [Agent Client Protocol v1: File System](https://agentclientprotocol.com/protocol/v1/file-system)
- [Agent Client Protocol v1: Authentication](https://agentclientprotocol.com/protocol/v1/authentication)
- [Agent Client Protocol v1: Terminals](https://agentclientprotocol.com/protocol/v1/terminals)
- [Agent Client Protocol v1: Security Considerations](https://agentclientprotocol.com/protocol/v1/security)
- [ACP v1 JSON Schema (GitHub)](https://github.com/agentclientprotocol/agent-client-protocol/blob/main/schema/v1/schema.json)
- [Android Studio Agent Shell Sandbox searchable options (AOSP)](https://android.googlesource.com/platform/tools/adt/idea/%2B/45b10792cacda8aeba49b070d2875b78a45483a5/studio/searchable-options/android-studio/canary-searchable-options/p-com.google.tools.ij.aiplugin-searchableOptions.json)
- [Troubleshoot Android Studio: 로그 디렉터리](https://developer.android.com/studio/troubleshoot)
- [Credentials in managed agents (Gemini API)](https://ai.google.dev/gemini-api/docs/agent-credentials?hl=en)
- [Android Management API: enterprises.policies](https://developers.google.com/android/management/reference/rest/v1/enterprises.policies)
- [Network activity logging (Android Enterprise)](https://developer.android.com/work/dpc/logging)
- [IDE가 자동완성을 넘어 에이전트 OS로 변한 한 달](https://daewooki.github.io/posts/2026-8-ide-os-1/)
- [AI IDE/CLI ‘에이전트’ 전쟁, 2026년 4월에 실무가 바뀌는 지점들](https://daewooki.github.io/posts/ai-idecli-2026-4-1/)
- [에이전트가 IDE를 집어삼키는 2026년 5월: Kiro·Copilot·Codex·Cursor](https://daewooki.github.io/posts/ide-2026-5-kirocopilotcodexcursor-1/)
- [Android Security Bulletin 패치 레벨로 플릿 업데이트 운영하기](https://daewooki.github.io/posts/android-spl-fleet-operations/)
- [Android Security Bulletin 2026-09로 다시 짜는 모바일 보안 업데이트 운영](https://daewooki.github.io/posts/android-security-bulletin-patch-level-ops/)

[^1]: <https://developer.android.com/studio/releases?skip_cache=false>
[^2]: <https://developer.android.com/blog/posts/ai-agents-android-studio-integration>
[^3]: <https://daewooki.github.io/posts/2026-8-ide-os-1/>
[^4]: <https://agentclientprotocol.com/protocol/v1/prompt-turn>
[^5]: <https://android-developers.googleblog.com/2026/09/build-your-way-use-any-ai-agent-in-android-studio.html>
[^6]: <https://agentclientprotocol.com/protocol/v1/authentication>
[^7]: <https://ai.google.dev/gemini-api/docs/agent-credentials?hl=en>
[^8]: <https://developer.android.com/studio/gemini/permissions?authuser=1>
[^9]: <https://developer.android.com/studio/gemini/aiexclude>
[^10]: <https://android.googlesource.com/platform/tools/adt/idea/%2B/45b10792cacda8aeba49b070d2875b78a45483a5/studio/searchable-options/android-studio/canary-searchable-options/p-com.google.tools.ij.aiplugin-searchableOptions.json>
[^11]: <https://developer.android.com/work/dpc/logging>
[^12]: <https://developers.google.com/android/management/reference/rest/v1/enterprises.policies>
[^13]: <https://developer.android.com/work/dpc/logging?authuser=102>
[^14]: <https://agentclientprotocol.com/protocol/v1/security>
[^15]: <https://android-developers.googleblog.com/2026/04/Increase-Guidance-and-Control-over-Agent-Mode-with-Android-Studio-Panda-3.html>
[^16]: <https://agentclientprotocol.com/protocol/v1/file-system>
[^17]: <https://developer.android.google.cn/ai-tools/guides/quickstart>
[^18]: <https://developer.android.com/studio/troubleshoot?authuser=7>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
