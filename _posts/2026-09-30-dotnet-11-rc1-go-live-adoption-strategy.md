---
title: ".NET 11 RC1 채택 전략: Go-live RC와 업그레이드 링 설계"
description: ".NET 11 RC1의 Go-live 지원을 전제로, 프로덕션 투입 조건과 링/롤백/CI SDK 고정·런타임 분리 배포 체크리스트를 정리합니다."
date: 2026-09-30 10:49:28 +0900
categories: ["Languages", "NET"]
tags: ["dotnet", "release-management", "upgrade-strategy", "ci-cd", "global-json", "containers"]
render_with_liquid: false
---

## Go-live RC가 의미하는 것: “프로덕션에서 돌아가도 된다”는 말의 범위

2026-09-30 KST 시점에 [Download .NET](https://dotnet.microsoft.com/en-us/download/dotnet) 페이지 상단에는 “.NET Release Candidate (RC)” 섹션이 있고, **.NET 11.0.0-rc.1**이 노출되어 있습니다. 이 화면에서 “Support phase”가 “Go-live”로 표시되고, 툴팁에는 “Go-live releases are supported by Microsoft in production”이라고 명시돼 있습니다.[^1]

또한 [Download .NET 11.0](https://dotnet.microsoft.com/en-us/download/dotnet/11.0) 페이지에서도 “11.0.0-rc.1 Go-live”와 동일한 툴팁 문구가 반복됩니다.[^2]

여기서 중요한 해석 포인트는 두 가지입니다.

1) Go-live는 “품질이 GA에 준한다”가 아니라 “지원 창구가 열린다”에 가깝습니다. Microsoft가 RC에 대해 지원을 제공한다는 의미(케이스 오픈 가능, 재현/우회/핫픽스 검토 가능)이지, RC를 장기간 고정해도 된다는 의미는 아닙니다.

2) Go-live의 실체는 “유통기한이 있는 프로덕션 허용”입니다. .NET 지원 정책 문서에는 Go-live pre-release의 별도 표가 있고, **.NET 11 RC1의 End of Support가 2026-10-13**으로 박혀 있습니다. 지금(2026-09-30) 기준으로는 2주가 채 안 남습니다.[^3]

RC를 프로덕션에 넣는 전략을 세울 때, 흔히 “RC니까 실험적으로 잠깐 써보자”에서 멈추는데, Go-live로 표시되는 순간부터는 ‘운영 중인 소프트웨어’로 분류해야 합니다. 운영 중인 소프트웨어는 “돌아가느냐”보다 “장애가 났을 때 누구에게 무엇을 근거로 기대할 수 있느냐”가 본질입니다. Go-live는 그 기대의 근거가 됩니다.[^4]

## 지원 정책이 RC 채택을 강제하는 지점: latest patch 원칙과 RC의 EOS

.NET의 지원 정책 문서는 2026-09-08에 업데이트됐고, 그 안에서 “지원받으려면 patch를 최신으로 유지해야 한다”가 원칙으로 들어가 있습니다. 구체적으로 “Within a release's support lifecycle, systems must remain current on released patch updates.”라고 적습니다.[^5]

이 원칙은 GA에서야 늘 하던 얘기처럼 들립니다. 문제는 Go-live RC에 적용했을 때 운영 의미가 달라진다는 점입니다.

- GA의 “latest patch”는 월간 Patch Tuesday 흐름을 따라갑니다. 지원 문서가 “Patch updates are released monthly on the second Tuesday…”라고 명시합니다.[^5]
- Go-live RC의 “latest patch”는 사실상 “최신 RC/최신 pre-release”로 해석되는 순간이 생깁니다. 지원 표에 RC1의 EOS가 2026-10-13으로 들어가 있다는 건, 그 날짜(패치 화요일) 이후에는 RC1로는 지원을 기대하기 어렵다는 뜻입니다.[^3]

즉 RC를 프로덕션에 넣는다는 행위는, “업그레이드가 가능한 상태로 운영한다”까지 포함하는 계약입니다. 업그레이드 불가능(업그레이드 윈도우가 없거나, 롤백 플랜이 없거나, 배포가 느리거나, SDK/런타임을 섞어놔서 재빌드가 필요해지는 구조)이면 Go-live를 근거로 RC를 넣는 게 아니라, Go-live를 근거로 **업그레이드를 강제당하는** 그림이 됩니다.

정리하면 RC 채택은 다음을 전제합니다.

- RC1을 넣는 날에 “RC2/GA로 가는 승격 루트”가 이미 있어야 합니다.
- RC1에 문제가 생기면 “이전 런타임(.NET 10 등)으로 되돌리는 루트”가 있어야 합니다.
- 이 두 루트가 CI/CD의 산출물 구조(artifact, image, runtime binding)에 의해 막히면 RC는 운영에 부적합합니다.

## Go-live RC를 프로덕션에 넣어도 되는 조건: 리스크를 ‘기술’이 아니라 ‘운영 메커니즘’으로 고정

기능이 좋아서 RC를 넣는 게 아니라, 운영 메커니즘이 성숙해서 RC를 넣을 수 있는지부터 봐야 합니다. 나는 조건을 세 묶음으로 자릅니다.

### 1) 지원(EOS)과 배포 빈도를 맞출 수 있는가

.NET 11 RC1의 EOS가 2026-10-13이면, 늦어도 그 전까지는 다음 단계로 이동해야 합니다.[^3]

- 배포가 주 1회 이하인 조직은 RC를 넣는 순간 EOS 리스크가 곧바로 현실화합니다.
- 배포가 하루 수회여도 “런타임 변경 배포”가 별도 승인/점검을 요구하면 현실적으로 막힙니다.

RC는 기능 문제가 아니라 시간 문제가 먼저 터집니다.

### 2) 런타임을 ‘주입 가능한 요소’로 취급하는가

프로덕션에 들어가는 실행 파일이 “런타임(.NET Runtime/ASP.NET Core Runtime)에 강하게 결합”되어 있으면, RC 전환은 곧 재빌드/재패키징/재테스트를 요구합니다. 반대로 런타임이 컨테이너 베이스 이미지나 호스트 런타임 패치로 주입 가능한 형태이면, 같은 빌드 산출물을 가지고도 런타임만 교체하는 운영이 가능합니다.

지원 정책 문서에서도 Framework Dependent Deployment(FDD)는 OS 업데이트로 자동 패치를 받을 수 있고, Self-Contained Deployment(SCD)는 앱이 런타임 업데이트 책임을 진다고 구분합니다.[^3]

RC를 넣으려면 이 구분을 선택이 아니라 운영 전제로 만들어야 합니다.

### 3) 실패를 “런타임 레벨”에서 격리할 수 있는가

RC 장애는 보통 코드 버그보다 아래에서 옵니다.

- JIT/GC 변화로 인한 latency tail
- TLS/HTTP stack 변화로 인한 특정 upstream과의 호환성
- container base image/OS 레이어 변화로 인한 libc/openssl 영향

따라서 롤백의 단위가 “앱 코드”가 아니라 “런타임”이어야 합니다. 런타임 롤백을 하려면 배포 링(ring)과 승격 규칙이 먼저 있어야 합니다.

## 업그레이드 링을 서비스별로 설계하기: Preview→RC→GA는 환경이 아니라 ‘대상 서비스’의 분류

많은 팀이 Preview/RC/GA를 dev/stage/prod 환경에 매핑합니다. 이 방식은 “모든 서비스가 같은 속도로 움직인다”는 가정이 깔려서, 모노리스/단일 제품 조직에서는 통하지만 마이크로서비스나 다수의 워크로드를 가진 조직에서는 깨집니다.

내 쪽에서 더 잘 맞았던 방식은 환경이 아니라 **서비스 클래스별 링**을 두는 것입니다. 서비스마다 링에 올라가는 속도가 다르고, 어떤 서비스는 RC를 절대 허용하지 않을 수도 있습니다.

### 링 모델(예시)

- Ring 0: 개발자 로컬 + ephemeral preview 환경. Preview 허용.
- Ring 1: CI build/test. Preview는 옵션, RC는 기본 검증.
- Ring 2: 내부 트래픽(직원용), 배치/워커 중 재시도가 쉬운 작업. RC canary.
- Ring 3: 외부 트래픽 중 low blast radius(기능 플래그로 끊을 수 있고, 장애 시 우회 경로가 있는 API). RC 제한적 허용.
- Ring 4: 결제/인증/계정/코어 데이터 저장 등. GA만 허용.

핵심은 “prod=Ring 4”가 아니라 “prod 안에도 Ring 2/3/4가 공존한다”로 보는 겁니다. RC는 prod라는 단어가 아니라 blast radius가 작은 서비스에만 들어갑니다.

이 관점은 내가 예전에 정리한 업그레이드 운영 글들과 결이 같습니다. systemd나 Linux stable kernel처럼 ‘안정 릴리스’라도 결국 조직이 롤아웃 기준을 만들어야 하고, Discourse처럼 월간 릴리스가 오히려 운영 메커니즘을 강제해서 안정성을 끌어올리기도 합니다.

- [systemd 안정 릴리스와 운영 기준: 백포트 vs 자체 업그레이드](https://daewooki.github.io/posts/systemd-stable-backport-vs-upgrade-policy/)
- [Linux stable 커널 롤아웃 체크리스트: 7.2.4](https://daewooki.github.io/posts/linux-stable-kernel-rollout-checklist-724/)
- [Discourse 월간 릴리스에 맞춘 셀프호스팅 업그레이드 운영](https://daewooki.github.io/posts/discourse-monthly-release-selfhost-upgrade-automation/)

## 롤백 설계: “RC를 넣는다”가 아니라 “런타임을 교체 가능하게 만든다”

RC를 프로덕션에 넣을 수 있는 조직은, 대개 이미 GA에서도 런타임 교체가 빠릅니다. RC 때문에 새로 하는 게 아니라, RC가 그 필요성을 폭발적으로 드러냅니다.

### FDD vs SCD를 운영의 언어로 다시 정리

- FDD: 앱이 특정 major/minor 런타임을 요구하고, host는 설치된 런타임 중 최신 patch를 선택합니다. “최신 patch 유지” 정책과 궁합이 좋습니다.[^6]
- SCD: 앱이 런타임을 포함해 배포되므로, 운영 패치 속도가 곧바로 앱 재배포 속도에 종속됩니다. runtime patch가 나오면 앱을 다시 publish해야 합니다.[^7]

RC는 “짧은 EOS + 빠른 승격”이 핵심이므로, 운영 관점에서는 FDD가 더 유리한 경우가 많습니다. 컨테이너에서도 마찬가지로, 런타임을 베이스 이미지로 분리해두면 런타임 교체가 단순해집니다.

### 런타임 선택(roll-forward)을 손대기 전에 알아야 하는 것

.NET host는 기본적으로 patch를 롤포워드합니다. 그리고 roll-forward는 project 설정, runtimeconfig, 환경변수, 커맨드라인 순으로 override됩니다.[^6]

RC를 넣을 때 흔히 하는 실수가, “예상치 못한 런타임으로 떠버릴까봐” roll-forward를 disable로 잠가버리는 겁니다. 이건 운영에서 보통 역효과가 납니다.

- patch roll-forward를 막으면 “latest patch 유지” 원칙과 충돌합니다.
- GA에서는 보안 패치가 들어와도 런타임을 못 올려서 지원 조건을 깨기 쉽습니다.

따라서 나는 roll-forward를 막는 대신, 런타임 공급 경로(컨테이너 베이스 이미지/호스트 설치/노드 풀 교체)를 통제하는 쪽으로 갑니다.

## CI에서 SDK 고정: global.json은 ‘버전 파일’이 아니라 ‘업그레이드 규칙’이다

RC 채택에서 실제로 더 자주 터지는 건 런타임보다 SDK입니다.

- 로컬 개발자가 RC SDK를 설치해 버리고 새 언어 기능이나 analyzer 변화가 섞임
- CI runner에 새 SDK가 깔리면서 MSBuild/NuGet 동작이 달라짐
- lock file이 의도치 않게 갱신

.NET은 global.json으로 “어떤 SDK를 쓸지”를 지정할 수 있고, 이 선택은 “타깃 runtime”과 독립이라고 문서가 명확히 말합니다.[^8]

### global.json을 RC 채택에 맞게 쓰는 패턴

RC를 쓰는 팀은 보통 두 선택지 중 하나를 택합니다.

- 완전 고정(재현성 최우선): exact RC SDK 버전을 적고 rollForward=disable
- 밴드 고정(보안/버그픽스 수용): RC의 feature band까지만 고정하고 latestPatch/patch를 허용

RC1 자체가 짧은 기간(2026-10-13 EOS)을 갖는 구조라면, 나는 “완전 고정”을 더 선호합니다. RC를 프로덕션에 넣는 목적이 ‘조기 기능 활용’이 아니라 ‘GA 업그레이드 리허설’이라면, 변수를 줄이는 편이 낫습니다.

예시(global.json):

```json
{
  "sdk": {
    "version": "11.0.100-rc.1.26425.128",
    "rollForward": "disable"
  }
}
```

여기서 버전 문자열은 [Download .NET 11.0](https://dotnet.microsoft.com/en-us/download/dotnet/11.0) 페이지에 “Full version”으로 표기된 값(11.0.100-rc.1.26425.128)을 그대로 쓰는 게 안전합니다.[^2]

rollForward 옵션은 global.json 문서에 정의돼 있고, CI에서는 acceptable range를 만들 때 쓴다고 설명합니다.[^8]

또 하나 실무에서 중요했던 포인트는 “SDK 버전을 고정하면 Visual Studio가 알아서 맞춰주겠지”라는 기대를 버리는 겁니다. global.json 문서는 Visual Studio가 SDK를 단일 버전만 유지하거나 제거할 수 있음을 경고합니다(stand-alone SDK 설치 권장, 단 자동 업데이트 부재로 보안 리스크 가능). 이건 RC 운영에서는 특히 민감합니다.[^8]

## SDK 설치 전략: setup-dotnet vs dotnet-install, 그리고 prerelease를 다루는 규칙

GitHub Actions를 쓰는 경우, SDK 설치는 보통 [actions/setup-dotnet](https://github.com/actions/setup-dotnet)로 갑니다. 이 액션은 prerelease 설치를 위해 `dotnet-quality` 입력을 제공하고, `preview`/`daily`/`ga`를 지원한다고 문서에 적혀 있습니다.[^9]

중요한 제약도 같이 봐야 합니다.

- `global.json`에서 prerelease를 지정한 경우에는 “정확히 pinned된 버전이 설치된다”는 식의 규칙이 README에 적혀 있습니다.[^9]
- prerelease 제어에서 `allowPrerelease`는 setup-dotnet에선 사실상 쓰이지 않고 `dotnet-quality`가 중심이라는 설명도 들어 있습니다.[^9]

즉, “global.json으로 SDK를 완전 고정”하고 “setup-dotnet은 그 버전을 설치만 해준다”로 역할을 분리하는 게 제일 깔끔합니다.

대신 self-hosted runner나 폐쇄망 CI처럼 “액션이 aka.ms/builds.dotnet.microsoft.com로 나가면 안 되는” 환경이면, dotnet-install 스크립트를 직접 써서 내부 미러/아티팩트 캐시로 돌리는 편이 낫습니다.

dotnet-install 스크립트는 Microsoft Learn 문서에서 CI 시나리오를 intended use로 박아두고 있고, 비관리자 설치, 임시 설치에 맞는다고 설명합니다.[^10]

문서에서 특히 유용했던 문장은 두 가지입니다.

- 스크립트는 `DOTNET_ROOT`를 세팅해주지 않는다(직접 세팅해야 함).[^10]
- `--runtime` 인자로 SDK가 아니라 runtime만 설치할 수 있다.[^10]

이게 곧 “CI에는 SDK를, 런타임 노드에는 런타임만”이라는 분리 전략으로 이어집니다.

## 런타임 분리 배포: 빌드 이미지와 런타임 이미지를 다른 릴리스 사이클로 둔다

컨테이너 기반 운영에서 RC 채택을 안전하게 만드는 핵심은 **런타임 분리**입니다. 나는 원칙을 이렇게 둡니다.

- 빌드 컨테이너(dotnet/sdk)는 CI에서만 사용하고, 프로덕션 노드에는 절대 들어가지 않게 합니다.
- 런타임 컨테이너(dotnet/aspnet 또는 dotnet/runtime)는 프로덕션에 들어가며, patch/RC 교체의 단위가 됩니다.

Microsoft Artifact Registry에는 .NET SDK/ASP.NET 이미지 태그가 공개돼 있고, 11.0.100-rc.1 SDK 태그도 확인됩니다.[^11]

ASP.NET 런타임 쪽도 태그 목록에서 11.0.0-rc.1 계열을 확인할 수 있습니다.[^12]

### 현실적인 시나리오: 내부 백오피스 API를 RC로 먼저 올려서 “승격 루트”를 검증

여기서는 “백오피스 주문 조회 API”처럼, 외부 고객 트래픽이 아니라 내부 사용자 트래픽이고 장애 시 read-only degraded mode가 가능한 서비스를 가정합니다.

리포지토리 구조:

```
repo/
  global.json
  src/
    Backoffice.Orders.Api/
      Backoffice.Orders.Api.csproj
      Program.cs
      appsettings.json
  docker/
    Dockerfile
  .github/workflows/
    ci.yml
```

`src/Backoffice.Orders.Api/Backoffice.Orders.Api.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net11.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
```

`src/Backoffice.Orders.Api/Program.cs` (minimal API지만 운영에서 흔히 필요한 것들을 넣었습니다: health, readiness, downstream call timeout, structured logging):

```csharp
using System.Diagnostics;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddHealthChecks();

builder.Services.AddHttpClient("inventory", client =>
{
    client.BaseAddress = new Uri(builder.Configuration["Inventory:BaseUrl"]!);
    client.Timeout = TimeSpan.FromSeconds(2);
});

var app = builder.Build();

app.MapGet("/healthz", () => Results.Ok(new { status = "ok" }));
app.MapHealthChecks("/readyz");

app.MapGet("/orders/{orderId:long}", async (long orderId, IHttpClientFactory factory, CancellationToken ct) =>
{
    // DB 조회가 있다고 가정하고, 여기서는 downstream 조회로 대체
    var sw = Stopwatch.StartNew();

    var http = factory.CreateClient("inventory");
    using var resp = await http.GetAsync($"/inventory/reserve-status/{orderId}", ct);

    sw.Stop();

    return Results.Ok(new
    {
        orderId,
        inventoryStatus = resp.StatusCode.ToString(),
        elapsedMs = sw.ElapsedMilliseconds
    });
});

app.Run();
```

로컬 실행(개발자가 RC SDK를 설치했다고 가정):

```bash
cd src/Backoffice.Orders.Api

dotnet --info | head -n 20

dotnet run
```

예상 출력(버전은 환경에 따라 다르지만, 적어도 net11.0 타깃과 SDK 11.0.100-rc.1 계열이 표시돼야 합니다):

```
Now listening on: http://localhost:5xxx
Application started.
```

이 예제의 목적은 기능 데모가 아니라, “런타임/SDK가 바뀌었을 때 우리 서비스의 기본 동작과 관측 포인트가 유지되는가”를 보는 것입니다.

### Dockerfile: 빌드 stage는 SDK, 런타임 stage는 aspnet

`docker/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1

ARG SDK_IMAGE=mcr.microsoft.com/dotnet/sdk:11.0.100-rc.1
ARG RUNTIME_IMAGE=mcr.microsoft.com/dotnet/aspnet:11.0.0-rc.1

FROM ${SDK_IMAGE} AS build
WORKDIR /src

COPY ./global.json ./global.json
COPY ./src/Backoffice.Orders.Api/ ./src/Backoffice.Orders.Api/

RUN dotnet restore ./src/Backoffice.Orders.Api/Backoffice.Orders.Api.csproj
RUN dotnet publish ./src/Backoffice.Orders.Api/Backoffice.Orders.Api.csproj -c Release -o /out --no-restore

FROM ${RUNTIME_IMAGE} AS runtime
WORKDIR /app
COPY --from=build /out ./

ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080

ENTRYPOINT ["dotnet", "Backoffice.Orders.Api.dll"]
```

여기서 RC를 운영에 넣을 때의 이점은 단순합니다.

- 앱 코드가 바뀌지 않아도 `RUNTIME_IMAGE`만 바꾸면 런타임 교체 이미지 빌드가 가능합니다.
- RC1 → RC2 → GA 승격 루트가 “코드 변경이 아니라 베이스 이미지 변경”으로 단순화됩니다.

물론 이미지 digest가 변하므로 완전히 “동일 artifact 승격”은 아니지만, 적어도 변경면을 런타임 레이어로 좁힐 수 있습니다. 이 구조가 없으면 RC는 곧바로 “재빌드가 필요한 대규모 릴리스”로 변질됩니다.

## 링별 롤아웃과 롤백을 체크리스트로 고정

링 전략은 문서로는 다들 비슷하게 씁니다. 실제로 차이를 만드는 건 ‘체크리스트의 구체성’입니다. 나는 아래 항목이 하나라도 비어 있으면 RC는 prod 링에 넣지 않습니다.

### (A) RC를 prod(Ring 2/3)에 넣기 전 체크

1. EOS 확인
   - .NET 11 RC1 EOS(2026-10-13)를 캘린더에 박고, 그 전 주에 승격 작업이 예약돼 있어야 합니다.[^3]

2. 지원 근거 링크 고정
   - 다운로드 페이지의 Go-live 툴팁, 지원 정책의 Go-live 정의/표를 내부 런북에 링크합니다.[^2]

3. 런타임 교체 시간이 SLO를 만족하는지
   - 배포 1회당 리드타임(빌드+푸시+롤링업데이트)이 “EOS 전 2회 이상의 반복”을 감당할 만큼 짧아야 합니다.

4. 관측 가능성(최소)
   - p95/p99 latency, error rate, CPU throttling, GC pause time을 링 승격 게이트로 둡니다.

5. 다운스트림 호환성
   - TLS/HTTP stack 변화는 외부 시스템과의 조합에서 터지므로, prod와 동일한 outbound path에서 canary를 먼저 태웁니다.

### (B) RC 롤아웃 중 체크

1. canary의 트래픽 비율을 “시간”이 아니라 “지표”로 올립니다.
   - 예: error budget 소모가 일정 이하일 때만 1%→5%→25%로 승격

2. 장애 시 롤백 버튼이 ‘한 단계’인지 확인
   - 쿠버네티스면 이전 ReplicaSet으로 되돌리기
   - 서비스 메시가 있으면 라우팅 비율 0으로 내리기

3. 롤백이 코드 롤백인지 런타임 롤백인지 구분
   - RC에서 주로 필요한 건 런타임 롤백입니다.

### (C) RC를 GA로 승격할 때 체크

1. SDK 고정 유지
   - GA SDK로 올릴 때까지 global.json은 RC SDK를 유지하고, 승격 작업을 PR로 남깁니다.

2. 런타임 교체가 베이스 이미지 교체로 끝나는지
   - Dockerfile에 런타임 태그가 하드코딩돼 있으면 매번 수정이 퍼집니다. build arg로 좁히는 편이 낫습니다.

3. “latest patch” 원칙을 깨지 않는지
   - FDD에서는 host가 최신 patch를 선택하는 기본 동작을 유지해야 합니다.[^6]

이 체크리스트는 예전에 Terraform/etcd 업그레이드 리허설에서 내가 사용했던 방식과 동일합니다. 버전 고정은 출발점일 뿐이고, 롤백과 복구 동선이 없으면 업그레이드는 운영 이벤트가 아니라 사고 이벤트가 됩니다.

- [Terraform 1.16.2 업그레이드 체크리스트: 버전 고정만으로는 부족하다](https://daewooki.github.io/posts/terraform-1-16-2-upgrade-window-checklist/)
- [etcd v3.7.2 운영 리허설: 업그레이드·백업·복구·이미지 전략까지](https://daewooki.github.io/posts/etcd-372-kubernetes-ops-rehearsal/)

## CI 구성 예시: global.json 고정 + setup-dotnet 설치 + 런타임은 컨테이너로 분리

GitHub Actions 기준으로, RC를 운영에 넣는 팀은 “CI에서만이라도 결정론적으로 RC SDK를 설치”할 수 있어야 합니다.

`.github/workflows/ci.yml` 예시:

```yaml
name: ci

on:
  push:
    branches: [ main ]
  pull_request:

jobs:
  build_test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Setup .NET SDK (from global.json)
        uses: actions/setup-dotnet@v6
        with:
          global-json-file: global.json

      - name: Show SDK
        run: dotnet --info

      - name: Restore
        run: dotnet restore ./src/Backoffice.Orders.Api/Backoffice.Orders.Api.csproj

      - name: Build
        run: dotnet build ./src/Backoffice.Orders.Api/Backoffice.Orders.Api.csproj -c Release --no-restore

      - name: Test (if any)
        run: dotnet test -c Release --no-build
```

setup-dotnet은 `global-json-file`을 읽어 SDK 버전을 설치할 수 있고, prerelease/rollForward 처리에 대한 제약도 README에 명시돼 있습니다.[^9]

RC 채택 관점에서 이 구성의 장점은 명확합니다.

- runner에 어떤 SDK가 사전 설치돼 있든 global.json으로 통제합니다.
- RC SDK를 설치하는 책임은 CI에 있고, 개발자 로컬은 따라올 수도 있고 안 따라올 수도 있습니다(로컬 강제는 별도 정책).

여기서 한 단계 더 가면, dotnet-install 스크립트를 써서 완전히 고립된 .NET 설치를 만들 수 있습니다. 스크립트 문서는 CI 사용을 intended use로 박아두고 있고, runtime만 설치하는 옵션도 제공합니다.[^10]

## 결론: Go-live는 조기 채택 허가가 아니라 ‘업그레이드 체계가 있는 팀’에 대한 옵션

.NET 11 RC1이 다운로드 페이지에서 Go-live로 표시되고, 공식 지원 정책이 “최신 patch 유지가 지원 조건”임을 더 또렷하게 못 박은 시점(문서 업데이트 2026-09-08)은, RC를 기능 평가의 문제가 아니라 운영 체계의 문제로 바꿔버립니다.[^1]

내 기준에서 RC를 프로덕션에 넣어도 되는 조건은 요약하면 이렇습니다.

- RC의 EOS(이번 RC1은 2026-10-13) 전에 다음 단계(RC2 또는 GA)로 이동할 수 있는 배포 역량이 이미 있다.[^3]
- 서비스별 링을 가지고 있고, prod 안에서도 low blast radius 워크로드를 분리해 canary를 태울 수 있다.
- SDK는 global.json으로 고정하고, 런타임은 컨테이너 베이스 이미지/호스트 런타임으로 분리해 교체 가능하게 만들어놨다.[^8]

이 조건이 충족되지 않으면 RC는 ‘조기 채택’이 아니라 ‘운영 부채의 선결제’가 됩니다. 반대로 이 조건이 충족된 팀에게 Go-live RC는, 기능 프리뷰가 아니라 GA 업그레이드의 리허설을 prod에서 수행할 수 있게 만드는 보험에 가깝습니다.

## 참고 자료

- [.NET 다운로드 페이지](https://dotnet.microsoft.com/en-us/download/dotnet)[^1]
- [.NET 11 다운로드 페이지](https://dotnet.microsoft.com/en-us/download/dotnet/11.0)[^2]
- [.NET 11 RC1 발표(.NET Blog)](https://devblogs.microsoft.com/dotnet/dotnet-11-rc-1/)[^4]
- [.NET Support Policy](https://dotnet.microsoft.com/en-us/platform/support/policy)[^5]
- [.NET and .NET Core Support Policy (Go-live/EOS 표 포함)](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core)[^3]
- [global.json overview (Microsoft Learn)](https://learn.microsoft.com/en-us/dotnet/core/tools/global-json)[^8]
- [Select which .NET version to use (roll-forward)](https://learn.microsoft.com/en-us/dotnet/core/versions/selection)[^6]
- [Self-contained deployment runtime roll forward](https://learn.microsoft.com/en-us/dotnet/core/deploying/runtime-patch-selection)[^7]
- [dotnet-install scripts reference](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-install-script)[^10]
- [actions/setup-dotnet README](https://github.com/actions/setup-dotnet)[^9]
- [Microsoft Artifact Registry: .NET SDK 11.0.100-rc.1 태그](https://mcr.microsoft.com/en-us/artifact/mar/dotnet/sdk/tag/11.0.100-rc.1)[^11]
- [Microsoft Artifact Registry: dotnet/aspnet tags](https://mcr.microsoft.com/en-us/product/dotnet/aspnet/tags)[^12]

[^1]: <https://dotnet.microsoft.com/en-us/download/dotnet>
[^2]: <https://dotnet.microsoft.com/en-us/download/dotnet/11.0>
[^3]: <https://dotnet.microsoft.com/platform/support/policy/dotnet-core>
[^4]: <https://devblogs.microsoft.com/dotnet/dotnet-11-rc-1/>
[^5]: <https://dotnet.microsoft.com/en-us/platform/support/policy>
[^6]: <https://learn.microsoft.com/en-us/dotnet/core/versions/selection>
[^7]: <https://learn.microsoft.com/en-us/dotnet/core/deploying/runtime-patch-selection>
[^8]: <https://learn.microsoft.com/en-us/dotnet/core/tools/global-json>
[^9]: <https://github.com/actions/setup-dotnet>
[^10]: <https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-install-script>
[^11]: <https://mcr.microsoft.com/en-us/artifact/mar/dotnet/sdk/tag/11.0.100-rc.1>
[^12]: <https://mcr.microsoft.com/en-us/product/dotnet/aspnet/tags>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
