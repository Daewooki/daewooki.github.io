---
title: "Spring Boot 4 마이그레이션 실전: 진짜 깨지는 지점들"
description: "Jakarta EE 11/Servlet 6.1 이후 실제 깨짐을 분류하고 리허설→OpenRewrite→검증 파이프라인으로 표준화합니다."
date: 2026-09-17 13:26:48 +0900
categories: ["Backend", "Spring Boot"]
tags: ["spring-boot", "jakarta-ee", "servlet", "openrewrite", "mockmvc", "multimodule"]
render_with_liquid: false
---

## Jakarta EE 11/Servlet 6.1 베이스라인이 만드는 강제 전제

Spring Boot 4는 Jakarta EE 11 기반이고 Servlet 6.1 베이스라인을 요구합니다. 이 문장은 단순한 스펙 상향이 아니라, 운영과 테스트, 그리고 서드파티 생태계까지 같이 끌려 올라간다는 뜻입니다. Spring Boot 공식 Migration Guide가 이 요구사항을 명시합니다. 또한 non-Servlet 6.1 컨테이너에 배포하는 것을 권장하지 않는다고 못 박습니다.[^1]

Servlet 6.1 자체는 2024-03-28 Final로 릴리스되었고, Jakarta EE 11의 Servlet 스펙입니다.[^2][^3]

여기에 Spring Framework 7이 Servlet 6.1/WebSocket 2.2를 웹 애플리케이션 베이스라인으로 채택합니다. Boot 4는 Spring Framework 7 위에 서기 때문에, 결국 Servlet 6.1을 팀 전체가 받아들이는 구조가 됩니다.[^4]

임베디드 서버도 현실적으로 고정됩니다. Spring Boot 4.0 Release Notes에는 Jetty 12.1과 Tomcat 11.0으로의 업그레이드가 포함되어 있고, System Requirements에는 Tomcat 11.0.x/Jetty 12.1.x가 Servlet 6.1을 구현한다고 정리되어 있습니다.[^5][^6]

그리고 이 베이스라인 때문에 **Undertow가 Boot 4에서 드롭됩니다.** Migration Guide에 이유가 그대로 나옵니다. Undertow가 아직 Servlet 6.1과 호환되지 않아서 Undertow starter와 embedded Undertow 사용 자체가 제거되었습니다.[^1]

이 정도가 스펙 레벨 이야기입니다. 팀이 실제로 체감하는 깨짐은 여기서부터 다른 층에서 터집니다.

## 2026-09-17 시점에서 왜 지금 레시피가 필요해졌나

Spring Boot 4.0.0 GA는 2025-11-20에 공지되었습니다.[^7]

한편 Spring Boot 3.5.x는 2026-06-25에 3.5.16이 공개되면서 “last OSS release”로 공지되었습니다. 문장 그대로 해석하면, 2026-06-25 이후로 3.5.x는 더 이상 커뮤니티 패치가 나오지 않는 상태입니다.[^8]

따라서 오늘(2026-09-17 KST) 기준으로는, Boot 3.5 라인에 머무르는 전략이 점점 설득력을 잃습니다. 올릴지 말지의 논쟁이 아니라, 올리는 방식이 팀 생산성을 좌우하는 구간으로 넘어왔습니다.

내 경우, 이런 상황에서 가장 손해 보는 패턴은 다음 두 가지였습니다.

- 각 서비스 팀이 제각각 부딪혀서, 같은 깨짐을 다른 방식으로 땜질하고 끝내는 패턴
- 자동 마이그레이션 도구를 돌린 뒤 “컴파일만 되면 끝”으로 착각하고, 런타임/테스트 슬라이스에서 뒤늦게 불이 나는 패턴

그래서 깨짐을 분류하고, 리허설 브랜치에서 한 번에 수습한 다음, 자동 수정(OpenRewrite)을 끼워 넣고, 마지막에 검증을 고정된 체크리스트로 굳히는 파이프라인이 필요합니다.

## 깨짐을 네 덩어리로 나누는 이유

Spring Boot 4 Migration Guide가 제공하는 기준선은 중요하지만, 팀이 실제로 겪는 깨짐은 “내가 어떤 레이어를 커스터마이즈했는가”에 따라 달라집니다. 나는 다음 4개로 나눠서 다루는 것이 가장 재현성이 높았습니다.

1) **Servlet/Filter chain**

2) **테스트/MockMvc**

3) **서드파티 스타터/오토컨피그**

4) **멀티모듈/플러그인 구조**

이 분류는 책임 범위가 깔끔합니다.

- (1)은 런타임 트래픽의 첫 관문
- (2)는 CI를 깨뜨리는 가장 큰 원인
- (3)은 classpath가 얇아지면서 생기는 의존성/오토컨피그 불연속
- (4)는 조직 단위 표준(사내 스타터, 공통 모듈, Gradle convention plugin)이 먼저 깨지기 때문에 “한 번에 넓게” 해결해야 하는 영역

아래부터는 각 영역에서 무엇이 왜 깨지는지, 그리고 파이프라인에서 어디서 잡아야 하는지로 정리합니다.

## (1) Servlet/Filter chain: 컨테이너/체인/서버 선택이 먼저 갈린다

### Undertow 사용 팀은 부팅 전에 이미 끝난다

Boot 4에서 Undertow 지원이 제거된 것은 Migration Guide에 직접적으로 적혀 있습니다. 이유도 명확합니다. Boot 4가 Servlet 6.1 베이스라인을 요구하고 Undertow가 아직 그 베이스라인과 호환되지 않으므로 embedded Undertow 지원을 드롭했다는 내용입니다.[^1]

여기서 실무적으로 문제는 “서버를 바꿔야 한다”가 아닙니다.

- 사내 표준이 Undertow로 굳어져 있었거나
- Undertow 기반으로 튜닝된 thread/IO 모델을 전제로 필터/로그/메트릭을 구성했거나
- Undertow 핸들러 레벨 확장을 얹어 둔 경우

서블릿/필터 체인 관점에서 **초기화 단계부터 다르게 동작할 수 있습니다.** 이건 코드 수정이 아니라, 서버 교체 프로젝트에 가깝습니다.

Boot 4 기준으로는 Tomcat 11.0과 Jetty 12.1이 기본 선택지로 정리됩니다(Release Notes와 System Requirements가 같은 방향을 가리킵니다).[^5][^6]

### 배포형 컨테이너를 쓰는 팀은 “Servlet 6.1+”를 계약서처럼 다뤄야 한다

Boot 4 Migration Guide는 non-Servlet 6.1 컨테이너에 배포하지 말라고까지 표현합니다.[^1]

WAR 배포 모델(외부 Tomcat/WAS)에 익숙한 조직은 여기서 흔히 “우리 컨테이너는 Jakarta니까 괜찮겠지”라고 넘어갑니다. Boot 4는 Servlet 6.1이라는 아주 구체적인 베이스라인을 요구합니다. “Jakarta 기반” 같은 추상 문구는 통과 기준이 아닙니다.

운영 환경 점검에서 내가 강제하는 체크는 딱 두 개였습니다.

- 운영 컨테이너가 Servlet 6.1 구현체인지(제품 문서/버전으로 확인)
- 실제 배포 artifact가 Boot 4의 의존성(Tomcat 11/Jetty 12.1)과 충돌하지 않는지

후자는 서버가 제공하는 servlet-api와 애플리케이션 classpath에 섞인 servlet-api가 충돌하면서 이상한 ClassCastException/NoSuchMethodError로 변질될 수 있습니다. 이런 건 CI에서 잡기 어렵고, staging에서만 재현되기 쉽습니다.

### Servlet 6.1의 “작지만 의미 있는” 변경이 필터/컨트롤러의 전제를 흔든다

Jakarta Servlet 6.1에는 server push 관련 요구사항 완화가 들어갑니다. 스펙 문서에 “containers are not required to support server push”로 명시되어 있고, `HttpServletRequest.newPushBuilder()`가 항상 null을 반환할 수 있다고 적혀 있습니다.[^2]

HTTP/2 server push를 직접 쓰는 경우는 흔치 않지만, 다음 같은 코드가 남아 있는 조직은 봤습니다.

- 특정 CDN/프록시 환경에서만 server push를 켜는 레거시 코드
- 내부 프레임워크가 pushBuilder 존재를 전제로 최적화를 걸어둔 경우

이 경우 Boot 4로 올렸을 때 “갑자기 null이 더 많이 나온다”가 아니라, **원래부터 null을 반환할 수 있는 API**라는 사실을 이제는 정말로 받아들여야 합니다. 즉, 코드가 더 방어적으로 바뀌어야 합니다.

### Filter chain은 Boot가 아니라 Spring/Security/컨테이너 조합에서 깨진다

서블릿 필터 체인은 스펙 자체가 단순합니다. 요청이 들어오면 컨테이너가 필터 리스트의 첫 필터부터 `doFilter`를 호출하면서 `FilterChain`을 전달합니다. 이 호출 모델은 Jakarta Servlet spec에 그대로 정리되어 있습니다.[^9]

문제는 스펙이 아니라, 우리가 **Filter를 어떤 dispatch에 걸었는지**입니다.

- `REQUEST`만으로 충분한데 `FORWARD`/`ERROR`/`ASYNC`까지 걸어 버린 필터
- 반대로 async 상황에서 반드시 한 번 실행되어야 하는데 기본 동작에 기대는 필터

Spring의 `OncePerRequestFilter`는 이 dispatch/async 맥락을 이미 문서화하고 있고, async dispatch에서 별도 스레드로 실행될 수 있다는 점을 명확히 씁니다.[^10]

Boot 4로 올라가면 Spring Framework 7/Spring Security 7 조합으로 같이 올라가고, 이때 필터 등록/자동 구성의 경계가 더 모듈화됩니다. 필터 체인에서 깨지는 대부분은 “필터가 두 번 돈다/안 돈다” 같은 단순 문제라기보다, 필터가 기대하던 downstream bean/infra(예: Security 관련, 관찰성 관련)가 classpath에서 빠지면서 간접적으로 발생합니다. 이건 (3)과 연결됩니다.

결론적으로 (1) 영역은 코드 몇 줄이 아니라, 서버/컨테이너/모듈 선택과 운영 점검이 핵심입니다.

## (2) 테스트/MockMvc: Boot 4에서 CI가 가장 먼저 죽는 지점

Boot 4 마이그레이션에서 테스트가 깨지는 이유는 단순합니다. Boot 3까지 “편의로 자동 제공”되던 것들을 Boot 4는 더 이상 제공하지 않습니다.

### @SpringBootTest가 더 이상 MockMvc를 제공하지 않는다

Migration Guide에 명확히 적혀 있습니다.

- `@SpringBootTest`는 더 이상 MockMvc 지원을 제공하지 않는다
- MockMvc를 쓰려면 테스트 클래스에 `@AutoConfigureMockMvc`를 명시해야 한다
- HtmlUnit 관련 속성도 `htmlUnit` 속성으로 이동했다

[^1]

이 변화는 테스트 코드의 의미를 더 정확하게 만듭니다.

- “이 테스트는 진짜로 MVC 레이어를 AutoConfigure 하겠다”라는 선언이 필요해졌고
- 반대로 “나는 단순히 전체 context만 띄우는 통합 테스트다”라는 상태가 기본이 됩니다.

문제는 기존 코드베이스가 이 둘을 섞어 쓴다는 점입니다. `@SpringBootTest` 한 줄로 모든 테스트 도구를 끌어다 쓰던 코드가 많으면 많을수록, Boot 4로 올린 첫날 CI는 거의 확정적으로 깨집니다.

### @SpringBootTest가 WebClient/TestRestTemplate도 제공하지 않는다

Migration Guide는 `@SpringBootTest`가 더 이상 `WebClient`나 `TestRestTemplate` bean을 제공하지 않는다고도 적고, 대안으로 다음을 제시합니다.

- `TestRestTemplate`가 필요하면 `@AutoConfigureTestRestTemplate`
- 그리고 `org.springframework.boot:spring-boot-resttestclient`, `org.springframework.boot:spring-boot-restclient` 의존성이 필요

또한 `TestRestTemplate`의 패키지가 `org.springframework.boot.resttestclient.TestRestTemplate`로 옮겨가므로, 컴파일 실패 시 테스트 스코프 의존성으로 `spring-boot-resttestclient`를 추가하라고 안내합니다.[^1]

여기서 중요한 실전 포인트는 이것입니다.

- “의존성 추가 + 애노테이션 추가 + import 변경”이 한 번에 필요
- 팀이 테스트를 어떤 층으로 나누고 있는지(슬라이스/통합/계약 테스트)에 따라 영향이 달라짐

이걸 자동 변환에만 맡기면, 테스트가 통과하도록 assertion만 바뀌고, 테스트 의도가 흐려지는 부작용을 본 적이 있습니다.

### MockitoTestExecutionListener 제거: @Mock/@Captor가 조용히 죽는다

Migration Guide는 Spring Boot 3.4에서 deprecated 되었던 `MockitoTestExecutionListener`가 Boot 4에서 제거되었다고 쓰고, `@Mock`/`@Captor`가 기대대로 동작하지 않으면 Mockito의 `MockitoExtension`을 쓰라고 안내합니다.[^1]

이 변화가 악질인 이유는 “컴파일 에러”가 아니라 “테스트가 다른 의미로 동작”하기 때문입니다.

- mock이 주입되지 않아 실제 구현이 호출되거나
- captor가 null로 남아서 검증이 무의미해지거나
- NPE로 터져서 그제서야 알아차리는 경우

이건 리허설 단계에서 테스트 실패 유형으로 분류해 두는 편이 낫습니다.

### @MockBean/@SpyBean deprecation: @MockitoBean/@MockitoSpyBean로 이사

Boot 4에서 `@MockBean`/`@SpyBean` 지원이 deprecated 되었고, `@MockitoBean`/`@MockitoSpyBean`를 쓰라고 Migration Guide가 명시합니다. 또한 새 애노테이션은 테스트 클래스의 field로는 가능하지만 `@Configuration` 클래스에서는 쓸 수 없다는 차이도 같이 설명합니다.[^1]

새 애노테이션 자체의 동작은 Spring Framework 문서에 정리되어 있습니다. 테스트 ApplicationContext의 bean을 Mockito mock/spy로 override하는 용도라는 점, 적용 가능한 위치(필드/타입 레벨 등)가 나옵니다.[^11]

실무에서는 다음 패턴이 자주 깨집니다.

- 여러 테스트에서 공유하려고 `@TestConfiguration`에 `@MockBean`을 몰아넣은 패턴

Migration Guide가 말하는 것처럼, Boot 4에서는 이 패턴을 그대로 옮길 수 없습니다. 나는 이걸 오히려 좋은 계기로 봅니다.

- 공유 mock은 “테스트 설계의 부채”일 확률이 높고
- mock override가 전역 설정처럼 퍼지면, 테스트가 brittle 해집니다.

Boot 4로 올리면서 mock override를 테스트 클래스 단위로 국소화하는 것이 장기적으로 비용이 줄었습니다.

### 모듈화로 인한 테스트 슬라이스의 classpath 단절

Spring Boot 4의 모듈화는 테스트에도 그대로 적용됩니다. Spring이 직접 쓴 글에서도 `spring-boot-test-autoconfigure`가 분리되어 기술별 test module이 생겼고, 예를 들어 `spring-boot-starter-webmvc`를 쓰면 테스트 스코프로 `spring-boot-starter-webmvc-test`를 추가하는 흐름을 권장합니다.[^12]

결국 테스트는 두 단계로 깨집니다.

- 1차: import/package 변경으로 컴파일이 깨짐
- 2차: 컴파일은 되지만 필요한 auto-configuration이 classpath에 없어서 context 로딩/슬라이스가 깨짐

이걸 파이프라인에서 “리허설→자동수정→검증”으로 분리하는 이유가 여기에 있습니다.

### 실제로 돌아가는 예시(Gradle 멀티모듈)로 재현하기

아래 예시는 Boot 4에서 팀이 흔히 겪는 테스트 깨짐을 한 번에 재현하도록 구성했습니다.

- WebMvc 기반 REST
- 커스텀 Filter
- `@WebMvcTest` + `@MockitoBean`
- `@SpringBootTest` + `@AutoConfigureMockMvc`
- 멀티모듈 구조(공통 모듈 분리)

#### 디렉터리 구조

```text
billing-platform/
  settings.gradle.kts
  build.gradle.kts
  apps/
    billing-api/
      build.gradle.kts
      src/main/java/... 
      src/test/java/...
  libs/
    security-filters/
      build.gradle.kts
      src/main/java/...
```

#### settings.gradle.kts

```kotlin
rootProject.name = "billing-platform"

include(":apps:billing-api")
include(":libs:security-filters")
```

#### 루트 build.gradle.kts

```kotlin
plugins {
    id("java")
}

allprojects {
    repositories {
        mavenCentral()
    }
}

subprojects {
    plugins.withType<JavaPlugin> {
        the<JavaPluginExtension>().toolchain {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    }
}
```

#### apps/billing-api/build.gradle.kts

```kotlin
plugins {
    id("org.springframework.boot") version "4.1.1"
    id("io.spring.dependency-management") version "1.1.7"
    id("java")
}

dependencies {
    implementation(project(":libs:security-filters"))

    implementation("org.springframework.boot:spring-boot-starter-webmvc")

    testImplementation("org.springframework.boot:spring-boot-starter-test")

    // Boot 4 모듈화 이후, MVC 테스트 슬라이스/MockMvc를 안정적으로 쓰려면 명시적으로 붙입니다.
    testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")
}

tasks.test {
    useJUnitPlatform()
}
```

#### libs/security-filters/build.gradle.kts

```kotlin
plugins {
    id("java-library")
}

dependencies {
    api("jakarta.servlet:jakarta.servlet-api:6.1.0")
}
```

Servlet API 6.1.0 좌표는 Jakarta EE 페이지에도 명시되어 있습니다.[^3]

#### Filter 구현

```java
package com.example.security;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;

import java.io.IOException;

public class RequestIdFilter implements Filter {

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {
        // 실무에서는 여기서 MDC, trace, auth context 같은 걸 엮습니다.
        chain.doFilter(request, response);
    }
}
```

#### Boot 애플리케이션에서 필터 등록

```java
package com.example.billing;

import com.example.security.RequestIdFilter;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BillingApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(BillingApiApplication.class, args);
    }

    @Bean
    FilterRegistrationBean<RequestIdFilter> requestIdFilter() {
        FilterRegistrationBean<RequestIdFilter> bean = new FilterRegistrationBean<>();
        bean.setFilter(new RequestIdFilter());
        bean.setOrder(10);
        return bean;
    }
}
```

#### 컨트롤러 + WebMvcTest

```java
package com.example.billing.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {

    @GetMapping("/health")
    public String health() {
        return "ok";
    }
}
```

```java
package com.example.billing.web;

import org.junit.jupiter.api.Test;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(HealthController.class)
class HealthControllerWebMvcTest {

    private final MockMvc mvc;

    HealthControllerWebMvcTest(MockMvc mvc) {
        this.mvc = mvc;
    }

    @Test
    void health_returns_ok() throws Exception {
        mvc.perform(get("/health"))
           .andExpect(status().isOk())
           .andExpect(content().string("ok"));
    }
}
```

`@WebMvcTest`의 패키지는 Boot 4 API 문서 기준 `org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest`입니다.[^13]

#### 실행

```bash
./gradlew :apps:billing-api:test
```

예상 결과는 다음 형태입니다.

```text
> Task :apps:billing-api:test

BUILD SUCCESSFUL in 12s
```

이 예제는 Boot 4에서 “왜 `spring-boot-starter-webmvc-test`를 명시해야 하는지”를 가장 짧은 경로로 보여줍니다. `spring-boot-starter-test`만 두고 넘어가면, 코드베이스에 따라 슬라이스가 불안정하게 깨지는 순간이 옵니다.

## (3) 서드파티 스타터/오토컨피그: classpath가 얇아진 대가

Boot 4에서 팀이 가장 많이 착각하는 포인트는 “Jakarta EE 11 때문에 깨진다”입니다. 실제로는 Jakarta 패키지 이슈는 Boot 3에서 이미 큰 고비를 넘겼고, Boot 4에서 더 흔한 깨짐은 **모듈화로 인한 의존성/오토컨피그 위치 변화**입니다.

### spring-boot-autoconfigure가 더 이상 ‘하나의 큰 jar’가 아니다

Spring이 직접 쓴 모듈화 글에서 가장 핵심을 정확히 설명합니다.

- Boot 4에서 monolithic `spring-boot-autoconfigure` jar를 기술별 작은 모듈로 쪼갠다
- `spring-boot-test-autoconfigure`도 마찬가지로 쪼개져서 기술별 test module이 생긴다
- 커스텀 스타터/조직 내 공통 라이브러리가 `spring-boot-autoconfigure`에 직접 의존하거나, auto-configuration 클래스를 수동으로 import하는 형태였다면 교체가 필요하다

[^12]

Migration Guide도 같은 흐름을 더 실무적인 문장으로 정리합니다.

- Starter/Module 네이밍 규칙이 바뀌고
- Flyway/Liquibase처럼 “그동안은 서드파티 dependency만 있으면 되던 것”도 이제는 starter로 바꾸라고 안내합니다.

[^1]

즉, Boot 4에서의 깨짐은 다음 질문으로 결정됩니다.

- Boot가 원래 제공하던 편의 오토컨피그/테스트 오토컨피그에 “무임승차”하고 있었나?
- 서드파티 스타터가 Boot 내부 패키지에 직접 붙어 있었나?

### Deprecated starter rename은 ‘검색으로 끝나는’ 작업이지만, 누락되면 늦게 터진다

Migration Guide는 deprecated starter와 replacement를 표로 줍니다.

- `spring-boot-starter-web` → `spring-boot-starter-webmvc`
- `spring-boot-starter-web-services` → `spring-boot-starter-webservices`
- OAuth 관련 starter들도 security 하위로 이동

[^1]

여기서 자주 겪는 함정은 “빌드는 된다”입니다. deprecated starter가 당장 사라진 것은 아니기 때문에, 빌드가 통과하고 운영에서 천천히 기술 부채가 됩니다. 나는 이걸 리허설 단계에서 강제로 정리합니다.

- `spring-boot-starter-web` 같은 deprecated starter가 남아 있으면 PR을 막는 규칙

### 오토컨피그 클래스는 더 이상 공용 API가 아니다(그리고 더 강하게 막는다)

Spring Boot 4.0 Release Notes에는 “auto-configuration classes의 public members(상수 제외)를 제거했다”는 항목이 있습니다. 오토컨피그는 원래 공용 API가 아니고, 이제 Java 메커니즘으로 더 강하게 강제한다는 설명입니다.[^5]

이 변화는 서드파티 스타터/사내 공통 모듈에서 다음 패턴이 있으면 바로 깨집니다.

- Boot의 auto-configuration 클래스를 상속해서 일부 메서드를 override
- auto-configuration 내부 필드/메서드에 reflection으로 접근

Boot 3에서도 권장되지 않던 방식이지만, Boot 4에서는 더 빨리 폭발합니다. 이건 OpenRewrite가 잘 고치기 어렵고, 설계를 바꿔야 합니다.

### Classic starter는 도피처가 아니라 ‘리허설용 안전모’다

Migration Guide는 classic starter를 “빨리 띄우기 위해” 쓸 수 있다고 정리합니다.

- `spring-boot-starter` → `spring-boot-starter-classic`
- `spring-boot-starter-test` → `spring-boot-starter-test-classic`

그리고 classic starter는 모든 모듈을 제공해서 예전 세대와 유사한 classpath를 만든다고 설명합니다. 또한 결국에는 classic starter를 제거하고 선택적 starter로 옮기라고 권고합니다.[^1]

Spring이 모듈화 글에서 설명하는 classic starter의 의도도 완전히 동일합니다. “get up and running”하고, import를 고친 다음, 점진적으로 선택적 의존성으로 가라는 접근입니다.[^12]

내 기준에서는 classic starter는 운영에 남기면 안 됩니다. 리허설 브랜치에서만 허용하고, 본 브랜치로 머지하기 전에 반드시 제거합니다. classic을 운영에 남기는 순간, Boot 4의 모듈화가 주는 이득(경량화/명확성)도 잃고, 다음 마이너 업그레이드에서 또 다른 지뢰를 밟습니다.

## (4) 멀티모듈/플러그인 구조: 사내 공통물이 가장 먼저 무너진다

Boot 4 마이그레이션을 어렵게 만드는 주범은 보통 “서비스 코드”가 아니라, 사내 공통 모듈입니다.

- 사내 스타터(관찰성, 인증, 공통 예외 처리, 설정 로딩)
- Gradle convention plugin(의존성 표준, 테스트 표준)
- 멀티모듈 monorepo의 공통 BOM/버전 카탈로그

Migration Guide는 “모듈화 때문에 Boot 3과 Boot 4를 같은 artifact에서 동시에 지원하는 것을 강하게 비권장한다”고 씁니다.[^1]

이건 실무에서 의미가 큽니다.

- 사내 공통 스타터를 하나 만들어서 여러 서비스가 물고 있으면
- Boot 3 서비스와 Boot 4 서비스가 혼재하는 과도기가 생기는데
- “공통 스타터는 하나만 유지” 전략이 사실상 깨집니다.

나는 여기서 선택지를 세 개로 정리합니다.

1) 공통 스타터를 Boot 4로만 올리고, Boot 3 서비스는 공통 스타터 버전을 고정(동결)

2) 공통 스타터를 Boot 3 라인과 Boot 4 라인으로 분기(artifactId를 분리하거나 major version을 분리)

3) 공통 스타터가 Boot 내부에 너무 깊게 붙어 있다면, 스타터의 역할을 축소하고 “서비스 레벨 구성 템플릿”으로 바꾸기

Boot 4의 모듈화는 공통 스타터의 설계 품질을 강제하는 방향으로 작동합니다. 내부 패키지에 기대는 순간 깨지고, 기술별 starter/test-starter를 정확히 선언하지 않으면 슬라이스가 흔들립니다.

### BootstrapRegistry/EnvironmentPostProcessor 같은 ‘부팅 훅’이 깨지는 케이스

사내 공통 모듈에서 자주 쓰는 확장 포인트가 `EnvironmentPostProcessor` 같은 부팅 훅입니다. Migration Guide는 다음 변경을 명시합니다.

- `BootstrapRegistry` 관련 클래스는 `org.springframework.boot`에서 `org.springframework.boot.bootstrap`으로 이동
- `EnvironmentPostProcessor` 인터페이스가 `org.springframework.boot.env`에서 `org.springframework.boot`로 이동
- deep integration을 했다면 코드와 `spring.factories`를 업데이트해야 한다

[^14]

추가로, Boot 4.1.1 API 문서에서 `org.springframework.boot.env.EnvironmentPostProcessor`는 deprecated(forRemoval=true)로 표시됩니다. 즉, “옛 패키지로 남겨둔 호환 레이어”는 결국 제거됩니다.[^15]

멀티모듈 환경에서는 이런 변경이 서비스보다 공통 모듈에서 먼저 터지고, 공통 모듈이 깨지면 모든 서비스가 연쇄적으로 막힙니다. 그래서 리허설의 첫 대상은 서비스가 아니라 공통 모듈이어야 합니다.

## 리허설→자동 수정(OpenRewrite)→검증: 팀 표준 파이프라인

이 파이프라인의 목적은 두 가지입니다.

- 깨짐을 한 번에 재현하고(리허설)
- 반복 작업을 기계에게 맡기되(OpenRewrite)
- 마지막 품질 기준은 사람이 합의한 체크리스트로 고정(검증)

### 1) 리허설 브랜치: Boot 3.5 최신으로 정렬하고, classic으로 한 번 숨을 고른다

Migration Guide는 Boot 4로 넘어가기 전에 최신 3.5.x로 먼저 올리라고 시작부터 적습니다. deprecated API를 제거하기 위한 단계입니다.[^1]

Boot 3.5 라인은 2026-06-25의 3.5.16이 마지막 OSS 릴리스였습니다. 리허설 기준선은 사실상 이 버전이 됩니다.[^8]

그 다음 리허설에서는 classic starter를 적극적으로 씁니다.

- Boot 4로 버전만 올린 다음
- `spring-boot-starter-classic`, `spring-boot-starter-test-classic`로 “예전처럼 다 있는 classpath”를 만들고
- 컴파일/import 깨짐을 먼저 정리합니다.

classic 사용 방식은 Migration Guide에 표로 정리되어 있습니다.[^1]

여기서 핵심은 classic을 오래 끌지 않는 것입니다.

- classic은 리허설에서만
- 기능별 starter/test-starter로 옮길 때 classic을 제거

이 규칙이 없으면 “Boot 4는 올렸는데 classpath는 Boot 3 시절 사고방식”이라는 최악의 혼종이 됩니다.

### 2) 자동 수정(OpenRewrite): 기계가 잘하는 것만 맡기고, 레시피를 고정한다

OpenRewrite는 Boot 4 마이그레이션 레시피를 제공합니다. Boot 4 recipes 목록과 composite recipe 구성이 문서에 정리되어 있습니다.[^16]

가장 실무적으로 유용한 점은 “우산 레시피”가 있다는 것입니다.

- `org.openrewrite.java.spring.boot4.UpgradeSpringBoot_4_0`는 Boot 4로 올리기 위한 composite recipe이고
- 내부에서 Spring Framework 7/Spring Security 7/Spring Batch 6 같은 포트폴리오 업그레이드, `@MockBean` 교체, web server 클래스 relocation 등을 엮습니다.

[^17]

다만 현실적인 제약도 같이 봐야 합니다. OpenRewrite 문서는 rewrite-spring 아티팩트/플러그인이 Code Genome Project 저장소를 통해 배포되고 인증이 필요하다고 밝힙니다. 즉, CI에서 무작정 돌릴 수 있는 형태가 아닐 수 있습니다.[^17]

내 결론은 단순합니다.

- 조직에 Moderne/OpenRewrite 구독이 있으면 CI 파이프라인에 바로 넣고
- 없다면 “한 번의 자동 변환은 개발자 로컬에서” 수행하되, 변환 결과(diff)는 반드시 팀 표준으로 리뷰합니다.

OpenRewrite가 특히 강한 영역은 이런 것들입니다.

- 패키지 이동/리네이밍
- starter 이름 변경에 따른 build file 수정
- `@MockBean`/`@SpyBean` 교체 같은 대량 편집

반대로 OpenRewrite가 약한 영역은 이런 것들입니다.

- Undertow 제거 같은 “아키텍처 선택”
- 테스트 의미(무엇을 검증해야 하는가) 자체가 바뀌는 지점
- 서드파티 스타터의 런타임 불일치

그래서 자동 수정 단계는 “대량 편집을 표준화”하는 용도로만 씁니다.

### 3) 검증: 테스트 통과가 아니라, 의존성/슬라이스/운영조건을 체크리스트로 고정한다

Boot 4로 올리면 테스트 통과만으로는 부족합니다. 내가 강제로 고정하는 검증은 다음처럼 계층을 나눕니다.

#### A. classpath 검증(빌드 단계)

- deprecated starter가 남아 있지 않다(`spring-boot-starter-web` 등)
- `spring-boot-starter-*-test`가 슬라이스에 맞게 선언되어 있다
- Undertow 의존성이 남아 있지 않다

#### B. 테스트 슬라이스 검증(CI 단계)

- `@SpringBootTest` 기반 테스트는 `@AutoConfigureMockMvc`, `@AutoConfigureTestRestTemplate` 같은 의도를 명시했는가
- `@MockBean`/`@SpyBean`가 남아 있다면 왜 남겨야 하는가(단기 억제인지, 제거 계획이 있는지)

`@MockBean`/`@SpyBean` deprecation과 대체 애노테이션의 차이는 Migration Guide에 자세히 정리되어 있으므로, 이 문서가 곧 체크리스트의 근거가 됩니다.[^1]

#### C. 운영환경 검증(staging)

- 배포 컨테이너가 Servlet 6.1+인지
- 임베디드 서버로 운영한다면 Tomcat 11/Jetty 12.1 계열 조합이 맞는지

System Requirements는 Boot 4.1.1 기준으로 Tomcat 11.0.x/Jetty 12.1.x가 Servlet 6.1을 구현한다고 정리하고, “Servlet 6.1+ compatible container 어디든 배포 가능”이라고도 씁니다. 이 문장을 staging의 최소 조건으로 둡니다.[^6]

이 검증을 통과하면, Boot 4 마이그레이션은 “버전 업”이 아니라 “운영 표준 상향”으로 끝납니다.

## 도입 판단: Boot 4에서 진짜 비용이 드는 팀과, 의외로 빨리 끝나는 팀

Boot 4는 Jakarta EE 11/Servlet 6.1이라는 문구 때문에 크게 보이지만, 실제 비용은 다른 곳에서 갈립니다.

- Undertow를 쓰고 있었다면, 비용의 대부분은 서버 전환과 운영 튜닝에서 발생합니다(거의 별도 프로젝트).
- 테스트가 `@SpringBootTest` 만능 패턴으로 굳어져 있었다면, 비용의 대부분은 테스트 설계 정리로 갑니다.
- 사내 공통 스타터/플러그인이 Boot 내부에 깊게 붙어 있었다면, 비용의 대부분은 공통 모듈 재설계/분기 전략에서 발생합니다.
- 반대로, 표준 starter 사용 + 얕은 확장 + 슬라이스 테스트가 명확한 팀은 classic starter를 잠깐 쓰고 빠르게 정상화할 수 있습니다.

결국 Boot 4 마이그레이션은 기술 선택이 아니라, 코드베이스가 얼마나 Boot 내부에 기대고 있었는지의 감사(audit)입니다. 나는 그 감사 결과를 리허설 브랜치에서 숫자로 만들고(OpenRewrite로 기계적 변경량을 정량화), 검증 체크리스트로 운영 조건까지 고정하는 쪽이 가장 효율적이라고 결론 내렸습니다.

## 참고 자료

- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide/65a1e19f912ee1d51ccdcfa3339fc387f37195be)
- [Spring Boot 4.0 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Release-Notes)
- [Spring Boot 4.0.0 available now](https://spring.io/blog/2025/11/20/spring-boot-4-0-0-available-now/)
- [Spring Boot 3.5.16 available now](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
- [System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Modularizing Spring Boot](https://spring.io/blog/2025/10/28/modularizing-spring-boot/)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes/4484060dfa7d3d3e7a95f76f202ceed22923dc7e)
- [Jakarta Servlet 6.1](https://jakarta.ee/zh/specifications/servlet/6.1/)
- [Jakarta Servlet 6.1 Specification](https://redesign-2025--jakartaee.netlify.app/specifications/servlet/6.1/jakarta-servlet-spec-6.1)
- [OncePerRequestFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.9/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html)
- [OpenRewrite Spring Boot 4.x Recipes](https://docs.openrewrite.org/recipes/java/spring/boot4)
- [OpenRewrite: UpgradeSpringBoot_4_0](https://docs.openrewrite.org/recipes/java/spring/boot4/upgradespringboot_4_0-community-edition)
- [Spring Framework: @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Support Policy](https://spring.io/support-policy)
- [Supported Versions (Spring Boot Wiki)](https://github.com/spring-projects/spring-boot/wiki/Supported-Versions)
- [How to Migrate to Spring Boot 4: Step-by-Step Guide](https://bell-sw.com/blog/how-to-migrate-a-spring-boot-3-project-to-spring-boot-4/)

[^1]: <https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide/65a1e19f912ee1d51ccdcfa3339fc387f37195be>
[^2]: <https://redesign-2025--jakartaee.netlify.app/specifications/servlet/6.1/jakarta-servlet-spec-6.1>
[^3]: <https://jakarta.ee/zh/specifications/servlet/6.1/>
[^4]: <https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes/4484060dfa7d3d3e7a95f76f202ceed22923dc7e>
[^5]: <https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Release-Notes>
[^6]: <https://docs.spring.io/spring-boot/system-requirements.html>
[^7]: <https://spring.io/blog/2025/11/20/spring-boot-4-0-0-available-now/>
[^8]: <https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/>
[^9]: <https://jakarta.ee/specifications/servlet/6.1/jakarta-servlet-spec-6.1.pdf>
[^10]: <https://docs.spring.io/spring-framework/docs/6.1.9/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html>
[^11]: <https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html>
[^12]: <https://spring.io/blog/2025/10/28/modularizing-spring-boot/>
[^13]: <https://docs.spring.io/spring-boot/api/java/org/springframework/boot/webmvc/test/autoconfigure/WebMvcTest.html>
[^14]: <https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide/b0bbdf47fb8e72225bd50d801957e9cf75198b98>
[^15]: <https://docs.spring.io/spring-boot/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html>
[^16]: <https://docs.openrewrite.org/recipes/java/spring/boot4>
[^17]: <https://docs.openrewrite.org/recipes/java/spring/boot4/upgradespringboot_4_0-community-edition>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
