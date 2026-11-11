---
title: ".NET 11 GA 이후 메이저 런타임 업그레이드를 연 1회로 운영하는 법"
description: "SDK 고정, 롤아웃 링, 컨테이너 베이스 이미지까지 한 번에 흔들리지 않게 분리하는 업그레이드 운영 모델."
date: 2026-11-11 14:12:11 +0900
categories: ["News", "Languages"]
tags: ["dotnet-11", "sdk-pinning", "rollout-rings", "aspnet-core", "ef-core", "containers"]
render_with_liquid: false
---

## 2026-11-10 .NET 11 GA: 이번 릴리스가 ‘이벤트’가 된 이유

2026년 11월 10일에 .NET 11이 general availability(GA)로 공지됐고, GitHub의 dotnet/announcements에도 릴리스 이슈가 올라왔습니다. 해당 이슈는 “general availability”를 명시하고, SDK/Runtime/EF Core/ASP.NET Core 등 각 구성요소의 “Full Release Notes”로 갈 수 있는 관문 역할을 합니다. [“.NET 11 - Release” 공지 이슈](https://github.com/dotnet/announcements/issues/497) 자체가 조직 내부 커뮤니케이션에 그대로 쓰일 만한 1차 소스입니다.[^1]

공식 다운로드 페이지도 11.0.0의 “Latest release date”를 2026년 11월 10일로 표시하고, SDK 버전이 11.0.100임을 함께 보여 줍니다. 런타임/SDK 업그레이드 계획을 세울 때 “정확히 어떤 빌드가 GA인가”를 박아 넣는 데 이 페이지가 가장 편합니다. [“.NET 11 다운로드” 페이지](https://dotnet.microsoft.com/en-us/download/dotnet/11.0).[^2]

그리고 .NET 쪽은 매년 11월에 메이저 릴리스를 내는 리듬을 계속 유지하고 있습니다. “연 1회 업그레이드 이벤트”라는 운영 관점을 잡기 쉬운 이유가 여기서 생깁니다. [dotnet/core의 Releases 문서](https://github.com/dotnet/core/blob/main/releases.md?plain=1)는 “Major .NET versions are released annually in November”를 명시합니다.[^3]

여기까지는 흔한 릴리스 소식인데, 이번 .NET 11은 조직 입장에서는 업그레이드가 더 쉽게 이벤트화됩니다.

- Runtime, SDK, ASP.NET Core, EF Core가 같은 메이저 넘버로 동시에 움직입니다(대부분이 같은 날 같은 번호로 올라옵니다). [“.NET 11 - Release” 공지 이슈](https://github.com/dotnet/announcements/issues/497)는 구성요소별 릴리스 노트 링크를 한 화면에 묶습니다.[^1]
- RC 단계가 “Go-live”로 운영되다가 GA로 넘어가며, 조직 내 의사결정 포인트가 2단으로 분리됩니다. “Go-live releases are supported by Microsoft in production”은 지원 정책 문서와 다운로드 페이지에 같이 노출됩니다. [지원 정책의 Go-live 섹션](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core)과 [다운로드 페이지의 Go-live 설명](https://dotnet.microsoft.com/en-us/download/dotnet/latest)에서 확인됩니다.[^4]

이 글의 핵심은 “.NET 11로 올린다”가 아니라, **메이저 런타임 업그레이드를 연 1회 배포 이벤트로 운영할 때 ‘결합된 것들을 어떻게 분리해 안정적으로 굴릴 것인가’**입니다.

## Go-live RC에서 GA로: 운영 모델 관점에서 달라지는 경계

.NET 쪽의 Go-live는 “프리릴리스지만 프로덕션에 써도 지원한다”는 메시지를 명확하게 내는 장치입니다. 지원 정책 문서는 RC1/RC2/RC3의 Go-live 지원 기간을 표로 박아 두고, “Go-live releases are supported by Microsoft in production.”을 명시합니다. [“.NET과 .NET Core 지원 정책(Go-live releases)”](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core).[^4]

그리고 .NET 11 릴리스 타임라인은 release-notes 쪽에 RC1(2026-09-08) → RC2(2026-10-13) → RC3(2026-10-25) → GA(2026-11-10)로 정리돼 있습니다. 업그레이드 링을 설계할 때 이 날짜들을 그냥 캘린더에 박아 넣는 편이 낫습니다. [dotnet/core의 .NET 11 릴리스 노트 인덱스](https://github.com/dotnet/core/blob/main/release-notes/11.0/README.md).[^5]

여기서 운영 관점의 경계는 대략 이렇게 정리됩니다.

- Go-live RC: “지원은 받되, 런타임/SDK/도구 체인의 변동성을 조직이 흡수할 수 있어야 하는 구간”
- GA: “조직 내 표준 런타임 후보가 된 시점. 업그레이드를 늦추려면 ‘왜 늦추는지’를 설명해야 하는 구간”

내 경험상, Go-live RC를 프로덕션에 넣는 조직은 이미 업그레이드 링(rollout ring) 설계가 되어 있는 경우가 많았습니다. 링 설계 자체는 예전에 정리해 둔 [“.NET 11 RC1 채택 전략: Go-live RC와 업그레이드 링 설계”](https://daewooki.github.io/posts/dotnet-11-rc1-go-live-adoption-strategy/)와 겹치는 부분이 있어서 반복하지 않겠습니다. 여기서는 GA 직후에 더 아픈 포인트, 즉 “연 1회 이벤트”를 만들 때 생기는 결합 문제를 더 파고듭니다.

## ‘연 1회 메이저 업그레이드 이벤트’가 실패하는 지점: 4개 축이 한 덩어리로 움직인다

조직에서 .NET 메이저 업그레이드를 이벤트로 만들면, 보통 한 번에 이런 것들을 모두 바꾸려다가 사고가 납니다.

1) Runtime
- 서버에 설치된 runtime, 혹은 컨테이너 베이스 이미지의 runtime

2) TargetFramework
- 애플리케이션이 실제로 타겟팅하는 TFM(예: net10.0 → net11.0)

3) Framework / Packages
- Microsoft.AspNetCore.App(공유 프레임워크)와 NuGet 패키지(EF Core 등)

4) Toolchain
- SDK, MSBuild, analyzer, test runner, IDE(Visual Studio), CI 이미지/에이전트

이 네 축이 한 덩어리로 보이는 이유는 .NET 쪽이 “런타임+SDK+웹+ORM”을 같은 메이저 번호로 같이 내기 때문입니다. [“.NET 11 - Release” 공지 이슈](https://github.com/dotnet/announcements/issues/497)는 SDK/EF Core/ASP.NET Core를 한 화면에 같이 보여 줍니다.[^1]

하지만 운영은 반대로 가야 합니다. 이벤트를 만들려면 “한 번에 바꿀 수 있는 것”과 “절대 같이 묶으면 안 되는 것”을 분리해야 합니다.

- SDK는 ‘빌드 재현성’을 위해 고정 대상입니다.
- Runtime은 ‘런타임 패치 정책(매월)’과 같이 움직여야 해서 고정이 아니라 “채널 관리”에 가깝습니다.
- TargetFramework는 ‘코드 변경’이므로 링을 가장 촘촘히 쪼개야 합니다.
- EF/ASP.NET Core는 TargetFramework와 강하게 결합되지만, 패키지/프레임워크 레벨에서 부분적 분리가 가능합니다.

이 글의 나머지는 “연 1회 이벤트”를 하려면 이 결합을 어디까지 풀 수 있는지를 체크리스트로 정리한 것입니다.

## SDK 고정: global.json은 시작일 뿐이고, rollForward/AnalysisLevel까지 같이 본다

SDK 고정은 ‘개발자 PC에서만’ 하는 게 아니라 CI에서 같은 방식으로 강제돼야 의미가 있습니다. Microsoft 문서도 “global.json으로 SDK를 pin할 수 있고 runtime 버전과 독립적”이라고 분명히 씁니다. [“Upgrade to a new .NET version - Version pinning”](https://learn.microsoft.com/dotnet/core/install/upgrade).[^6]

### global.json: 메이저 업그레이드를 ‘의도된 커밋’으로 만든다

GA 직후라면, 조직이 표준으로 삼는 SDK를 딱 한 줄로 고정하는 커밋부터 시작하는 편이 좋습니다.

```json
{
  "sdk": {
    "version": "11.0.100",
    "rollForward": "latestFeature"
  }
}
```

- version: 11.0.100을 GA SDK로 고정합니다. [“.NET 11 다운로드” 페이지](https://dotnet.microsoft.com/en-us/download/dotnet/11.0)가 SDK 11.0.100을 보여 줍니다.[^2]
- rollForward: exact 버전이 없을 때 어디까지 허용할지 정책입니다. 예시는 문서에서 `latestFeature`를 사용합니다. [“Upgrade to a new .NET version - Control SDK version with global.json”](https://learn.microsoft.com/dotnet/core/install/upgrade).[^6]

운영 관점에서 중요한 건 “개발자 PC에 여러 SDK가 깔려 있어도, 이 리포지토리는 이 SDK를 쓰도록 강제된다”는 점입니다. 이걸 업그레이드 이벤트의 시작점으로 잡아야 커뮤니케이션이 깔끔해집니다.

### AnalysisLevel: SDK는 올렸는데 경고가 폭발하는 문제를 뒤로 미룬다

메이저 SDK 업그레이드는 analyzer 룰이 슬쩍 바뀌면서 빌드를 깨뜨리는 경우가 흔합니다. Microsoft 문서도 AnalysisLevel로 analyzer behavior를 고정할 수 있다고 설명합니다. [“Upgrade to a new .NET version - Control analyzer behavior”](https://learn.microsoft.com/dotnet/core/install/upgrade).[^6]

내 결론은 단순합니다.

- 연 1회 이벤트로 “런타임/TFM 변경”을 하고 싶으면, analyzer 업그레이드는 같은 이벤트에 묶지 않는 편이 낫습니다.
- 그래서 global.json과 함께 `Directory.Build.props`에 AnalysisLevel을 같이 고정합니다.

예를 들어 조직이 아직 net10 기반이고, 이번 이벤트에서는 “SDK만 11로 올리고 코드/TFM은 유지”하는 링을 먼저 굴리고 싶다면:

```xml
<Project>
  <PropertyGroup>
    <!-- SDK는 11로 올라가도 analyzer rule-set은 10 기준으로 유지 -->
    <AnalysisLevel>10.0</AnalysisLevel>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
  </PropertyGroup>
</Project>
```

이렇게 하면 “SDK 업그레이드”를 첫 번째 링에서 흡수하고, “경고/룰 변화 대응”은 다음 스프린트로 밀어낼 수 있습니다.

### CI에서 SDK 고정 강제: 설치 경로까지 통제한다

개발자 PC는 IDE 업데이트로 SDK가 같이 바뀌기도 합니다. CI는 더 심합니다. 호스티드 러너 이미지가 업데이트되면, 갑자기 더 최신 SDK가 기본으로 잡힙니다.

이 문제를 피하려면 CI에서 SDK를 명시 설치하고, 설치 버전이 global.json과 일치하는지 검증 로그를 남겨야 합니다.

GitHub Actions 예시입니다.

```yaml
name: ci
on:
  push:
    branches: [ main ]
  pull_request:

jobs:
  build-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup .NET SDK (pinned)
        uses: actions/setup-dotnet@v4
        with:
          global-json-file: global.json

      - name: Show dotnet info
        run: dotnet --info

      - name: Restore
        run: dotnet restore

      - name: Build
        run: dotnet build -c Release --no-restore

      - name: Test
        run: dotnet test -c Release --no-build
```

이렇게 해 두면, 업그레이드 이벤트 동안 “CI에서만 깨짐” 같은 변수를 많이 줄일 수 있습니다.

## 롤아웃 링: ‘빌드 링’과 ‘런타임 링’을 분리해야 연 1회 이벤트가 성립한다

업그레이드 링을 말하면 보통 서비스 배포 링(카나리, 내부, 전체)을 떠올립니다. .NET 메이저 업그레이드는 링을 두 겹으로 봐야 합니다.

- 빌드 링: SDK/툴체인/패키지 restore를 먼저 바꿔서 빌드 재현성을 만든다
- 런타임 링: 실제 프로덕션 실행 환경(runtime, base image)을 바꾸고 관찰한다

Go-live RC를 쓰는 조직은 이미 링을 운영하는 경우가 많지만, GA 직후 이벤트에서는 “한 번에 다 바꾸자”가 튀어나오면서 링이 무너집니다.

특히 .NET은 “SDK만 올리고 TFM은 유지”가 가능하기 때문에, 빌드 링을 먼저 굴릴 수 있습니다. 반대로 “TFM만 올리고 SDK는 유지”는 거의 불가능에 가깝습니다. 이 비대칭성을 이용해야 합니다.

- Ring 0 (빌드): global.json을 올리고, 기존 net10 코드를 그대로 빌드/테스트한다
- Ring 1 (런타임 비프로덕션): 컨테이너 base image를 11로 올리되 앱은 여전히 net10으로 유지한다(가능하면)
- Ring 2 (코드/TFM): net11.0으로 멀티타겟을 시작하고, 서비스 일부부터 net11 실행을 시작한다

여기서 “런타임을 11로 올렸는데 net10 앱이 돌아가느냐”는 질문이 나오는데, 이건 단순히 yes/no가 아닙니다.

- framework-dependent deployment(FDD)로 `net10.0` 타겟 앱은 보통 .NET 10 runtime을 요구합니다.
- major roll-forward 정책을 조직이 허용하지 않는다면, 런타임 링은 “애플리케이션도 함께 올리는 링”이 됩니다.

그래서 실무적으로는 런타임 링을 이렇게 정의하는 게 안전합니다.

- “node에 .NET 11 runtime을 설치/탑재할 수 있는 상태를 만든다”(side-by-side)
- “컨테이너에서는 base image를 서비스별로 분리해, net11 서비스만 11 base image로 보낸다”

컨테이너가 이 문제를 가장 깔끔하게 분리해 줍니다.

## 런타임/프레임워크/패키지의 결합을 어디까지 풀 수 있나

.NET 11 업그레이드가 이벤트화되는 이유 중 하나는, ASP.NET Core와 EF Core가 같은 메이저 번호로 동시에 올라가면서 팀들이 한 번에 다 올리려 하기 때문입니다.

하지만 실제로는 “같은 날 릴리스됐다”와 “같은 PR에서 올려야 한다”는 다릅니다.

### ASP.NET Core: shared framework를 타면 NuGet 패키지 업그레이드 압력이 줄어든다

ASP.NET Core는 shared framework(Microsoft.AspNetCore.App)에 많은 것들이 들어가 있어서, 웹 앱은 NuGet 패키지 참조를 억지로 끌고 가지 않는 편이 낫습니다. 다만 Blazor/WebAssembly, OpenAPI, 일부 구성요소는 패키지 업데이트가 필요할 수 있고, 이게 메이저 업그레이드 때 가장 많이 흔들리는 지점입니다.

ASP.NET Core 11의 변경점/브레이킹 변경점은 문서가 따로 있고, “Microsoft.OpenApi upgraded to 3.x”처럼 개발/빌드 단계에서 바로 체감되는 항목이 있습니다. [“Breaking changes in ASP.NET Core 11”](https://learn.microsoft.com/en-us/aspnet/core/breaking-changes/11/overview).[^7]

또한 공식 migration 문서가 “10.0 to 11.0” 형태로 별도로 제공됩니다. IDE 외 사용 시 주의 같은 현실적인 이야기도 들어 있습니다. [“Migrate from ASP.NET Core in .NET 10 to ASP.NET Core in .NET 11”](https://learn.microsoft.com/en-us/aspnet/core/migration/100-to-110?view=aspnetcore-10.0).[^8]

조직 운영 관점에서는 이 문서가 “업그레이드 PR의 체크리스트”로 거의 그대로 쓰입니다.

### EF Core: 런타임/SDK와 강결합이므로, ‘업그레이드 링’이 더 촘촘해야 한다

EF Core는 역사적으로도 메이저 업그레이드 때 브레이킹 체감이 큰 편입니다. EF Core 11 문서 자체가 “EF11 requires the .NET 11 SDK to build and requires the .NET 11 runtime to run.”을 명시합니다. 즉, EF는 사실상 TFM 업그레이드와 같이 가게 됩니다. [“What’s New in EF Core 11”](https://learn.microsoft.com/en-us/ef/core/what-is-new/ef-core-11.0/whatsnew).[^9]

브레이킹 변경점 페이지는 “Impact”를 High/Medium/Low로 나눠 주는데, 조직에서 연 1회 이벤트로 운영하려면 High-impact 항목을 먼저 빨리 스캔해야 합니다. [“Breaking changes in EF Core 11”](https://learn.microsoft.com/en-us/ef/core/what-is-new/ef-core-11.0/breaking-changes).[^10]

예를 들어 SQL Server 쪽은 기본 compatibility level이 160(SQL Server 2022)으로 바뀌는 내용이 들어 있습니다. 레거시 SQL Server를 쓰는 조직이면 “업그레이드 이벤트”의 핵심 리스크가 런타임이 아니라 DB 호환성으로 넘어갑니다. 같은 문서에 완화책도 같이 적혀 있습니다.[^10]

EF Core NuGet 패키지 자체도 11.0.0이 2026-11-10에 올라온 것으로 확인됩니다. [NuGet의 Microsoft.EntityFrameworkCore 11.0.0](https://www.nuget.org/packages/Microsoft.EntityFrameworkCore/11.0.0).[^11]

이런 강결합 때문에, EF Core 업그레이드는 “전체 서비스 동시”가 아니라 “DB 스키마 영향 범위별 링”으로 나눠야 현실적입니다.

## 컨테이너 베이스 이미지: 태그 업그레이드가 아니라 ‘재빌드 정책’ 업그레이드다

런타임 업그레이드를 연 1회 이벤트로 운영할 때, 컨테이너는 도와주는 동시에 발목도 잡습니다.

- 도와주는 점: 서비스 단위로 base image를 분기할 수 있습니다.
- 발목 잡는 점: base image는 .NET만 바뀌는 게 아니라 OS, OpenSSL, CA cert, tzdata 등도 같이 변합니다.

그래서 컨테이너 업그레이드는 “태그 바꾸기”가 아니라 “재빌드 정책 바꾸기”에 가깝습니다.

### 공식 이미지에서 .NET 11 태그 확인

dotnet/dotnet-docker 리포지토리는 SDK 이미지의 대표 태그로 `mcr.microsoft.com/dotnet/sdk:11.0`를 문서에 명시합니다. [“.NET SDK container image (dotnet-docker README.sdk.md)”](https://github.com/dotnet/dotnet-docker/blob/main/README.sdk.md).[^12]

ASP.NET Core runtime 이미지도 마찬가지로 `11.0` 계열 태그가 존재하고, rc.3/resolute/chiseled 같은 variant 태그 목록까지 문서로 제공합니다. [“.NET ASP.NET Core container image 태그 목록(README.aspnet.md)”](https://github.com/dotnet/dotnet-docker/blob/main/README.aspnet.md?plain=1).[^13]

그리고 Microsoft Artifact Registry 쪽에서는 `11.0-azurelinux3.0` 같은 태그가 실제로 발행된 것을 확인할 수 있습니다(artifact/digest까지 조회 가능). [ASP.NET Core runtime의 11.0-azurelinux3.0 계열 태그](https://mcr.microsoft.com/en-us/product/dotnet/aspnet/).[^14]

여기서 실무 포인트는 “어떤 태그를 조직 표준으로 삼을 것인가”입니다.

- `:11.0`처럼 추상화된 태그는 매월 패치/리빌드로 내용이 바뀝니다.
- `:11.0-azurelinux3.0`처럼 OS까지 고정하면 변동성이 줄어듭니다.
- digest로 고정하면 재현성은 최대가 되지만, 보안 패치 반영이 이벤트(사람의 작업)가 됩니다.

연 1회 이벤트를 하겠다는 조직은 보통 “digest 고정”에 끌리는데, 내 기준에서는 추천하지 않습니다. 이유는 간단합니다.

- .NET 지원 정책은 “지원 수명 내에서는 released patch updates에 최신을 유지해야 한다”를 요구합니다. [“.NET Support Policy”](https://dotnet.microsoft.com/en-us/platform/support/policy).[^15]
- dotnet/runtime 컨테이너 문서는 base image 업데이트, 월간 리빌드 같은 정책을 명시합니다. 즉 태그가 같은데 이미지가 바뀌는 건 정상 동작입니다. [“.NET Runtime container image about: Image Update Policy”](https://mcr.microsoft.com/en-us/artifact/mar/dotnet/runtime/about).[^16]

결국 조직이 “연 1회 이벤트”로 가져가야 하는 건 digest 고정이 아니라, 태그 업그레이드를 자동화하고 재빌드를 파이프라인으로 흡수하는 구조입니다.

### Dockerfile 예시: 빌드/런타임 이미지를 의도적으로 분리

아래는 net11으로 넘어가는 동안 가장 무난하게 쓰는 형태입니다.

```dockerfile
# syntax=docker/dockerfile:1

FROM mcr.microsoft.com/dotnet/sdk:11.0 AS build
WORKDIR /src

COPY . .
RUN dotnet restore
RUN dotnet publish ./src/Orders.Api/Orders.Api.csproj -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:11.0 AS runtime
WORKDIR /app
COPY --from=build /app/publish .

ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080

ENTRYPOINT ["dotnet", "Orders.Api.dll"]
```

이미지 태그 `sdk:11.0`는 dotnet-docker 문서에서 대표 태그로 제시됩니다.[^12]

운영에서 더 중요한 건 이 Dockerfile을 “연 1회”만 건드리는 게 아니라, 매월 Patch Tuesday 리빌드가 들어와도 서비스가 자연스럽게 따라가도록 만들 수 있느냐입니다.

- 연 1회: `:10.0` → `:11.0`로 major 태그를 변경(메이저 이벤트)
- 매월: 같은 major 태그에서 base image가 갱신되며 재빌드(정기 운영)

이 두 리듬이 합쳐져야 ‘이벤트’가 아니라 ‘프로세스’가 됩니다.

## IDE·CI·툴체인: Visual Studio, MSBuild, dotnet CLI의 결합을 끊는 선

업그레이드 이벤트에서 항상 뒤늦게 터지는 게 도구 체인입니다.

- 개발자들은 Visual Studio 업데이트를 하고 싶어합니다.
- 인프라/플랫폼 팀은 CI 재현성을 원합니다.
- 보안팀은 “최신 패치 강제”를 원합니다.

이 셋의 요구를 동시에 만족시키는 가장 현실적인 분리선이 global.json입니다. Microsoft도 global.json이 “SDK version selection”의 핵심이라고 문서에 씁니다. [“Select which .NET version to use”](https://learn.microsoft.com/en-us/dotnet/core/versions/selection).[^17]

그리고 .NET 11 릴리스 공지 이슈는 “Windows에서 Visual Studio를 쓴다면 .NET 11을 지원하는 up-to-date Visual Studio 2026을 사용하라”고 직접 말합니다. 즉, IDE도 업그레이드 이벤트의 구성요소로 포함됩니다. [“.NET 11 - Release” 공지 이슈의 Get started 섹션](https://github.com/dotnet/announcements/issues/497).[^1]

Visual Studio 버전 자체는 2026 릴리스 히스토리 문서로 추적 가능합니다. 배포 이벤트 운영에서는 “이벤트 당시 조직 표준 VS 버전”을 박아야 나중에 재현이 됩니다. [“Visual Studio 2026 release history”](https://learn.microsoft.com/en-us/visualstudio/releases/2026/release-history).[^18]

여기서 내가 정하는 원칙은 이렇습니다.

- IDE 업그레이드는 ‘강제’가 아니라 ‘지원 범위 선언’으로 운영합니다.
- 빌드/테스트는 dotnet CLI + global.json으로 강제합니다.
- CI에서는 “호스티드 러너의 기본 SDK”를 절대 신뢰하지 않습니다.

이 원칙이 있어야 연 1회 이벤트가 매년 반복 가능합니다.

## 브레이킹 변경점: 릴리스 노트보다 ‘compatibility 문서’가 체크리스트에 더 맞다

릴리스 노트는 “좋은 점”이 먼저 보이고, 브레이킹 변경점은 “해야 할 일”이 먼저 보입니다.

.NET 11 브레이킹 변경점 문서는 영역별로 나누고, binary/source/behavioral로 분류합니다. 아직 work in progress라고 밝히고 있어서, 조직에서는 이 페이지를 ‘완전한 목록’으로 믿으면 안 됩니다. 그렇다고 안 보면 더 위험합니다. [“Breaking changes in .NET 11”](https://learn.microsoft.com/dotnet/core/compatibility/11).[^19]

특히 이번 .NET 11에서 운영 관점으로 바로 보이는 건 두 가지입니다.

### (1) 최소 하드웨어 요구사항 변화는 런타임 링에서 먼저 검증해야 한다

.NET 11 runtime 문서는 x86/x64/Arm64에서 더 현대적인 instruction set을 요구하도록 바뀐다고 설명합니다. 이건 코드가 아니라 실행 환경 이슈라서, 코드 링보다 런타임 링에서 먼저 터집니다. [“.NET 11 runtime - Minimum hardware requirements updated”](https://learn.microsoft.com/dotnet/core/whats-new/dotnet-11/runtime).[^20]

레거시 VM, 오래된 온프레미스 서버, 특정 embedded 환경을 끌고 있는 조직은 “업그레이드 이벤트”의 리스크가 여기로 쏠릴 수 있습니다.

### (2) ASP.NET Core / EF Core의 브레이킹은 코드 링에서 ‘서비스별로’ 흡수해야 한다

ASP.NET Core 11은 ConcurrencyLimiter middleware 제거처럼 아예 사라지는 구성요소가 있고, OpenAPI 버전/동작도 바뀝니다. [“Breaking changes in ASP.NET Core 11”](https://learn.microsoft.com/en-us/aspnet/core/breaking-changes/11/overview).[^7]

EF Core 11은 Cosmos DB provider 같은 특정 기능 축에서 High-impact 변경이 있고, SQL Server 기본 호환성 레벨 같은 변경도 있습니다. [“Breaking changes in EF Core 11”](https://learn.microsoft.com/en-us/ef/core/what-is-new/ef-core-11.0/breaking-changes).[^10]

이런 브레이킹은 “조직 공통 PR”로는 흡수할 수 없고, 서비스/DB별로 다르게 대응해야 합니다.

## 반론과 회의론: ‘연 1회 업그레이드 이벤트’가 오히려 위험해지는 조건

연 1회 이벤트는 듣기 좋지만, 특정 조건에서는 위험해집니다.

1) 컨테이너를 쓰면서 base image를 수동 digest로 고정해 둔 조직
- 보안 패치 반영이 매월 이벤트가 됩니다.
- 결국 이벤트 피로도가 올라가고, 다음 메이저 이벤트는 더 미뤄집니다.

2) EF Core/DB 스키마 변경이 잦은 조직
- 메이저 런타임 업그레이드와 스키마 이벤트가 충돌합니다.
- 업그레이드를 “변경이 없는 시기”로 미루는데, 그런 시기는 영원히 오지 않습니다.

3) 개발자 도구(IDE) 업데이트를 강제하는 조직
- Visual Studio 업데이트 주기와 .NET 릴리스 주기가 엇갈리면, 개발자들이 업그레이드 이벤트를 우회하기 시작합니다.

이 반론들을 피하려면 결론은 하나로 모입니다.

- 연 1회 이벤트로 운영할 대상은 “메이저(TFM) 전환”이어야 하고,
- 나머지(패치/리빌드/툴링)는 이벤트가 아니라 상시 운영으로 흡수해야 합니다.

## 앞으로 지켜볼 것: 문서/레퍼런스의 ‘동기화 지연’ 자체가 리스크가 된다

이번 .NET 11 GA에서도 확인되는 현상이 하나 있습니다. “What’s new in .NET 11” 문서는 마지막 업데이트가 RC2 기준이라고 적혀 있습니다. GA가 났는데 overview 문서가 RC 기준이면, 조직 내부에서는 이게 혼선을 만듭니다. [“What’s new in .NET 11”](https://learn.microsoft.com/dotnet/core/whats-new).[^21]

반대로 다운로드 페이지는 11.0.0 GA를 바로 가리킵니다. 같은 날, 같은 제품인데 “권장 레퍼런스”가 다르게 보이는 시기가 생깁니다. [“.NET 11 다운로드(Release date 2026-11-10)”](https://dotnet.microsoft.com/en-us/download/dotnet/latest).[^22]

이건 단순한 문서 버그가 아니라, 업그레이드 이벤트에서 의사결정을 지연시키는 요인이 됩니다.

- 보안/컴플라이언스 팀은 GA를 근거로 최신화를 요구합니다.
- 개발팀은 RC 문서를 근거로 “아직 불안정한 것 아니냐”고 반박합니다.

그래서 업그레이드 이벤트의 1차 소스는 “공지/다운로드/지원정책/릴리스노트” 네 가지를 세트로 고정하는 편이 낫습니다.

- 공지: [“.NET 11 - Release”](https://github.com/dotnet/announcements/issues/497)[^1]
- 다운로드: [“.NET 11 다운로드”](https://dotnet.microsoft.com/en-us/download/dotnet/11.0)[^2]
- 지원정책: [“.NET Support Policy”](https://dotnet.microsoft.com/en-us/platform/support/policy)[^15]
- 릴리스노트 인덱스: [“.NET 11 release notes index”](https://github.com/dotnet/core/blob/main/release-notes/11.0/README.md)[^5]

## GA 직후에 실제로 하는 일: SDK 고정 → 빌드 링 → 컨테이너 링 → 코드 링 순서

여기부터는 체크리스트 형태로 정리합니다. 핵심은 “한 PR에서 다 하지 않는다”입니다.

### 0) 사실 확정: 우리가 업그레이드하는 기준점 고정

- .NET 11 GA 날짜: 2026-11-10
  - 근거: 다운로드 페이지에 Latest release date가 2026-11-10으로 표시됩니다.[^2]
- 지원 기간: STS로 2026-11-10부터 2028-11-14까지
  - 근거: dotnet/core 릴리스 노트 인덱스에 명시돼 있습니다.[^5]
- 메이저 릴리스 주기: 매년 11월
  - 근거: dotnet/core Releases 문서에 명시돼 있습니다.[^3]

이 세 개는 업그레이드 이벤트 티켓/문서의 첫 페이지에 그대로 복사해 둡니다.

### 1) SDK 고정 PR (빌드 링의 시작)

- global.json 추가/업데이트
- CI에서 global.json 사용 강제
- `dotnet --info` 출력 로그 남기기

이 PR의 acceptance criteria는 단 하나입니다.

- “코드 변경 없이도 main이 계속 빌드된다”

이 단계에서 브레이킹 변경점은 주로 SDK/MSBuild/analyzer에서 터집니다. 이걸 먼저 빼내야 다음 단계가 편해집니다.

추가로 .NET 11 브레이킹 변경점 문서의 SDK/MSBuild 섹션을 훑습니다. 예를 들어 global.json SDK selection이 특정 스크립트 경로에서 우회되는 식의 변경점이 들어갈 수 있습니다. [“Breaking changes in .NET 11 - SDK and MSBuild”](https://learn.microsoft.com/dotnet/core/compatibility/11).[^19]

### 2) 컨테이너 베이스 이미지 PR (런타임 링을 서비스 단위로 만든다)

- Dockerfile의 build stage를 `sdk:11.0`으로 올릴지 결정
- runtime stage를 `aspnet:11.0`으로 올릴지 결정
- OS variant 정책 결정(예: `11.0` vs `11.0-azurelinux3.0`)

이 단계에서 근거로 삼을 문서는 두 개면 충분합니다.

- 태그 존재/의미: [dotnet/dotnet-docker의 SDK 이미지 문서](https://github.com/dotnet/dotnet-docker/blob/main/README.sdk.md)[^12]
- 실제 발행된 태그/변형: [Microsoft Artifact Registry의 ASP.NET Core runtime 태그 목록](https://mcr.microsoft.com/en-us/product/dotnet/aspnet/)[^14]

이 PR의 acceptance criteria는 다음처럼 잡는 편이 현실적입니다.

- “이미지는 빌드된다”
- “개발/스테이징에서 떠서 헬스체크가 통과한다”
- “프로덕션은 카나리 1개 서비스만 먼저 간다”

메이저 런타임 업그레이드를 연 1회 이벤트로 운영하려면, 이 컨테이너 PR이 서비스별로 쪼개져야 합니다. 한 번에 전 서비스의 base image를 바꾸면, 결국 업그레이드 이벤트가 아니라 장애 이벤트가 됩니다.

### 3) 패키지/프레임워크 PR (EF/ASP.NET Core 동시 업그레이드의 폭발 반경을 줄인다)

여기서 중요한 건 “모든 패키지를 최신으로”가 아니라, 결합도를 낮추는 방향으로 정리하는 것입니다.

- 웹 앱: 가능한 한 shared framework에 맡기고, 불필요한 Microsoft.AspNetCore.* 패키지 직접 참조를 줄입니다.
- EF Core: 중앙 관리로 버전을 통일합니다.

예를 들어 Central Package Management를 쓰는 조직이면 `Directory.Packages.props`에 EF Core를 먼저 박아 두는 방식이 좋습니다.

```xml
<Project>
  <PropertyGroup>
    <ManagePackageVersionsCentrally>true</ManagePackageVersionsCentrally>
  </PropertyGroup>

  <ItemGroup>
    <PackageVersion Include="Microsoft.EntityFrameworkCore" Version="11.0.0" />
    <PackageVersion Include="Microsoft.EntityFrameworkCore.Sqlite" Version="11.0.0" />
    <PackageVersion Include="Microsoft.EntityFrameworkCore.Design" Version="11.0.0" />
  </ItemGroup>
</Project>
```

버전 근거는 NuGet에 올라온 11.0.0 게시 날짜(2026-11-10)로 잡을 수 있습니다.[^11]

이 단계에서는 반드시 EF Core/ASP.NET Core 브레이킹 변경점 문서를 같이 엽니다.

- EF Core: [EF Core 11 브레이킹 변경점](https://learn.microsoft.com/en-us/ef/core/what-is-new/ef-core-11.0/breaking-changes)[^10]
- ASP.NET Core: [ASP.NET Core 11 브레이킹 변경점](https://learn.microsoft.com/en-us/aspnet/core/breaking-changes/11/overview)[^7]

이 PR의 acceptance criteria는 통상 다음입니다.

- “빌드는 된다”가 아니라 “통합 테스트가 돌아간다”
- EF가 붙은 서비스는 마이그레이션/쿼리 플랜/호환성 레벨 리스크를 별도 점검한다

### 4) TargetFramework PR (연 1회 이벤트의 본체)

마지막이 `net11.0` 전환입니다. 이건 서비스별로 링을 가장 잘게 쪼개야 합니다.

- 공통 라이브러리: 멀티타겟(`net10.0;net11.0`)으로 안전지대를 만들고
- 실행 서비스: 먼저 `net11.0`으로 올린 뒤, 의존 라이브러리/툴이 따라오게 합니다.

이 단계의 체크리스트는 “.NET 11 브레이킹 변경점” 문서의 분류를 그대로 따라가는 게 효율적입니다. [“Breaking changes in .NET 11”](https://learn.microsoft.com/dotnet/core/compatibility/11).[^19]

## 정리: 연 1회 이벤트를 하려면 ‘한 번에 바꾸는 양’을 줄이는 게 아니라 ‘결합’을 풀어야 한다

.NET 11은 2026-11-10에 GA로 전환됐고, RC 단계에서 Go-live로 운영되던 흐름이 GA로 마무리됐습니다. 이 구조는 조직이 업그레이드를 이벤트로 만들기 쉬운 환경을 제공합니다.[^1]

하지만 메이저 업그레이드를 연 1회 배포 이벤트로 운영하려면, “런타임/SDK/프레임워크/툴체인”을 한 덩어리로 취급하는 순간부터 이벤트는 실패합니다.

- SDK는 global.json으로 고정해 빌드 재현성을 확보하고, analyzer 변화는 AnalysisLevel로 분리합니다.[^6]
- 컨테이너 base image는 태그 변경만으로 끝내지 않고, 월간 리빌드/패치 반영을 흡수하는 운영 정책으로 가져갑니다.[^16]
- EF Core/ASP.NET Core는 같은 메이저로 같이 오르지만, 조직의 배포 링에서는 영향 범위를 기준으로 분리해야 합니다.[^10]

결국 업그레이드 이벤트를 성공시키는 방법은 빠른 올인(one-shot)이 아니라, 빌드 링과 런타임 링을 분리한 뒤 서비스별 코드 링으로 좁혀 들어가는 운영 모델로 귀결됩니다.

## 참고 자료

- [.NET 11 - Release (dotnet/announcements #497)](https://github.com/dotnet/announcements/issues/497)
- [Announcing .NET 11 (.NET Blog)](https://devblogs.microsoft.com/dotnet/announcing-dotnet-11/)
- [Download .NET 11.0](https://dotnet.microsoft.com/en-us/download/dotnet/11.0)
- [.NET 11 release notes index (dotnet/core)](https://github.com/dotnet/core/blob/main/release-notes/11.0/README.md)
- [.NET Support Policy](https://dotnet.microsoft.com/en-us/platform/support/policy)
- [.NET and .NET Core official support policy (Go-live releases)](https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core)
- [Breaking changes in .NET 11](https://learn.microsoft.com/dotnet/core/compatibility/11)
- [What’s new in .NET 11](https://learn.microsoft.com/dotnet/core/whats-new)
- [What’s new in .NET 11 runtime](https://learn.microsoft.com/dotnet/core/whats-new/dotnet-11/runtime)
- [Migrate from ASP.NET Core in .NET 10 to ASP.NET Core in .NET 11](https://learn.microsoft.com/en-us/aspnet/core/migration/100-to-110?view=aspnetcore-10.0)
- [Breaking changes in ASP.NET Core 11](https://learn.microsoft.com/en-us/aspnet/core/breaking-changes/11/overview)
- [What’s New in EF Core 11](https://learn.microsoft.com/en-us/ef/core/what-is-new/ef-core-11.0/whatsnew)
- [Breaking changes in EF Core 11](https://learn.microsoft.com/en-us/ef/core/what-is-new/ef-core-11.0/breaking-changes)
- [Upgrade to a new .NET version (version pinning, AnalysisLevel)](https://learn.microsoft.com/dotnet/core/install/upgrade)
- [global.json overview](https://learn.microsoft.com/en-us/dotnet/core/tools/global-json)
- [.NET SDK container image (dotnet/dotnet-docker README.sdk.md)](https://github.com/dotnet/dotnet-docker/blob/main/README.sdk.md)
- [.NET ASP.NET Core container image tags (dotnet/dotnet-docker README.aspnet.md)](https://github.com/dotnet/dotnet-docker/blob/main/README.aspnet.md?plain=1)
- [Microsoft Artifact Registry: ASP.NET Core runtime images](https://mcr.microsoft.com/en-us/product/dotnet/aspnet/)
- [Microsoft Artifact Registry: .NET Runtime image update policy](https://mcr.microsoft.com/en-us/artifact/mar/dotnet/runtime/about)
- [.NET Releases (dotnet/core releases.md)](https://github.com/dotnet/core/blob/main/releases.md?plain=1)
- [Visual Studio 2026 release history](https://learn.microsoft.com/en-us/visualstudio/releases/2026/release-history)
- [Select which .NET version to use](https://learn.microsoft.com/en-us/dotnet/core/versions/selection)
- [이전 글: .NET 11 RC1 채택 전략: Go-live RC와 업그레이드 링 설계](https://daewooki.github.io/posts/dotnet-11-rc1-go-live-adoption-strategy/)

[^1]: <https://github.com/dotnet/announcements/issues/497>
[^2]: <https://dotnet.microsoft.com/en-us/download/dotnet/11.0>
[^3]: <https://github.com/dotnet/core/blob/main/releases.md?plain=1>
[^4]: <https://dotnet.microsoft.com/en-us/platform/support/policy/dotnet-core>
[^5]: <https://github.com/dotnet/core/blob/main/release-notes/11.0/README.md>
[^6]: <https://learn.microsoft.com/dotnet/core/install/upgrade>
[^7]: <https://learn.microsoft.com/en-us/aspnet/core/breaking-changes/11/overview>
[^8]: <https://learn.microsoft.com/en-us/aspnet/core/migration/100-to-110?view=aspnetcore-10.0>
[^9]: <https://learn.microsoft.com/en-us/ef/core/what-is-new/ef-core-11.0/whatsnew>
[^10]: <https://learn.microsoft.com/en-us/ef/core/what-is-new/ef-core-11.0/breaking-changes>
[^11]: <https://www.nuget.org/packages/Microsoft.EntityFrameworkCore/11.0.0>
[^12]: <https://github.com/dotnet/dotnet-docker/blob/main/README.sdk.md>
[^13]: <https://github.com/dotnet/dotnet-docker/blob/main/README.aspnet.md?plain=1>
[^14]: <https://mcr.microsoft.com/product/dotnet/aspnet/>
[^15]: <https://dotnet.microsoft.com/en-us/platform/support/policy>
[^16]: <https://mcr.microsoft.com/en-us/artifact/mar/dotnet/runtime/about>
[^17]: <https://learn.microsoft.com/en-us/dotnet/core/versions/selection>
[^18]: <https://learn.microsoft.com/en-us/visualstudio/releases/2026/release-history>
[^19]: <https://learn.microsoft.com/dotnet/core/compatibility/11>
[^20]: <https://learn.microsoft.com/dotnet/core/whats-new/dotnet-11/runtime>
[^21]: <https://learn.microsoft.com/dotnet/core/whats-new>
[^22]: <https://dotnet.microsoft.com/en-us/download/dotnet/latest>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
