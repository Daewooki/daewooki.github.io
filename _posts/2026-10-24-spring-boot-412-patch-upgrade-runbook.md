---
title: "Spring Boot 4.1.2 업그레이드 운영 템플릿: 패치도 릴리스다"
description: "Renovate/Dependabot로 유입되는 Spring Boot 4.1.2 같은 패치 업그레이드를 릴리스 노트→smoke test→롤백 가능한 배포 링으로 운영 계약화합니다."
date: 2026-10-24 09:43:33 +0900
categories: ["Backend", "Spring Boot"]
tags: ["spring-boot", "patch-upgrade", "smoke-test", "renovate", "dependabot", "rollout-rings"]
render_with_liquid: false
---

Spring Boot `4.1.2`는 2026-10-23에 공지됐고 Maven Central에서도 바로 설치 가능한 상태입니다[^1]. 공지 자체는 “1 min read”인데, 프로덕션 입장에선 텍스트 분량과 위험이 전혀 비례하지 않습니다. 특히 Spring Boot는 BOM과 auto-configuration으로 런타임 표면적을 넓게 쥐고 있고, Renovate/Dependabot이 자동 PR로 끌고 들어오기 쉬워서, 패치 릴리스라도 운영 루틴이 없으면 주말·야간에 합쳐진 뒤 월요일 아침 장애로 돌아오기 딱 좋습니다.

이 글은 Spring Boot 4.1.2를 예시로, 팀 표준으로 재사용 가능한 패치 릴리스 운영 템플릿을 정리한 것입니다. 구성은 세 가지를 강제합니다.

- 릴리스 노트를 읽는 행위를 “읽기”로 끝내지 않고 위험 영역으로 매핑합니다.
- 앱이 실제로 밟는 경로(Actuator/HTTP client/template/DB)를 smoke test로 자동화합니다.
- 배포 링(rings)과 롤백을 같은 문서·같은 파이프라인에 묶어서, 패치 릴리스도 릴리스로 취급합니다.

예전 글인 [Spring Boot 4 마이그레이션 실전: 진짜 깨지는 지점들](https://daewooki.github.io/posts/spring-boot-4-migration-real-breakages/)은 3.x→4.x의 큰 변곡점을 다뤘고, 여기서는 4.1.x 내부에서 “자동으로 들어오는 패치”를 운영 계약으로 만드는 쪽에 집중합니다.

## 자동 PR이 만드는 실패 모드: 패치인데 왜 위험해지나

Renovate/Dependabot을 켜면 패치 업데이트는 거의 확정적으로 유입됩니다. 운영에서 위험한 지점은 두 가지입니다.

첫째, 패치 업데이트는 “내가 의식적으로 선택한 변화”가 아니라 “봇이 정기적으로 밀어 넣는 변화”로 변합니다. Renovate는 automerge까지 걸어두면 CI만 통과하면 특정 시간대에 자동 merge가 될 수 있고[^2], 주말에 사람이 없는 시간대에 메인 브랜치가 바뀌는 일이 생깁니다. Dependabot도 구성에 따라 주기적으로 PR이 생기고, ignore/allow로 세밀하게 조절할 수 있지만[^3], 기본값대로 두면 “매일 조금씩”이 “항상 어딘가 바뀌는 상태”가 됩니다.

둘째, Spring Boot 패치 릴리스는 Boot 코드만 바뀌는 게 아니라 런타임을 구성하는 핵심 dependency가 같이 올라갑니다. 4.1.2만 봐도 Spring Framework, Spring Security, Reactor BOM, Tomcat, Jackson BOM, HttpClient5 같은 것들이 한꺼번에 움직입니다[^4]. 패치라고 해서 “API가 안 바뀔 것”만 기대하면, 실제로는 TLS/HTTP stack, graceful shutdown, JSON serialization, thread scheduling 같이 장애가 잘 나는 층이 같이 흔들립니다.

그래서 팀 표준을 “패치니까 빠르게 머지”가 아니라 “패치니까 자동화로 더 빠르게 검증”으로 바꿔야 합니다.

## 4.1.2 릴리스 노트 → 위험 영역 매핑

Spring Boot 4.1.2 공지는 “126 bug fixes… and dependency upgrades” 수준으로 짧게 끝납니다[^1]. 실제 판단 근거는 공지 글이 아니라 GitHub release notes의 항목들입니다[^4].

여기서 중요한 건 “다 읽는다”가 아니라 “위험 영역을 고정된 카테고리로 나눈 뒤, 릴리스 노트 항목을 거기에 끼워 넣는다”입니다. 나는 아래 카테고리를 고정 템플릿으로 씁니다.

- Config/Property loading
- Security/Auth
- Web server & shutdown
- Observability/Logging
- Packaging/Build/Image
- External integration (Docker Compose, clients)
- Data access

Spring Boot 4.1.2의 실제 항목을 예로 매핑하면 다음처럼 됩니다.

### Config/Property loading

- `OriginTrackedPropertiesLoader`가 이름이 `#` 또는 `!`로 시작하는 properties를 누락시키는 문제[^4]

이건 대다수 서비스에선 당장 안 터질 수 있지만, “특수한 키를 쓰는 시스템”에서 터지면 디버깅 비용이 커집니다. 예를 들어 레거시 `.properties`에서 `\#`로 escape된 키를 쓰거나, 외부 시스템에서 생성하는 properties에 특수 키가 섞이면 환경 로딩이 조용히 바뀔 수 있습니다.

### Security/Auth

- `issuer-uri`가 비어 있고 `jwk-set-uri`만 설정된 경우 JWT가 거절되는 문제[^4]
- dependency upgrade로 Spring Security가 `7.1.2`로 올라감[^4]

이 영역은 조직에서 가장 흔한 실패 패턴이 “로컬/스테이징에서는 되는 것처럼 보이는데 prod에서만 401이 터지는” 형태입니다. smoke test에서 “서명된 토큰을 만들어 실제로 보호된 endpoint를 통과시키는” 테스트가 있어야 합니다.

### Web server & shutdown

- Tomcat/Jetty graceful shutdown 직후 stop 호출 시 callback 상태가 이상해질 수 있는 문제[^4]
- NettyWebServer stop이 특정 타이밍에서 hang할 수 있는 문제[^4]
- Tomcat이 `11.0.27`로 업그레이드됨[^4]

여기는 “패치인데 장애가 난다”가 가장 자연스럽게 나오는 지점입니다. readiness/liveness가 정상이어도, shutdown이 꼬이면 deploy 시점에 connection drain이 안 되고 5xx가 튈 수 있습니다.

### Observability/Logging

- Logback `ColorConverter`가 매 로그 이벤트마다 옵션을 파싱하는 비효율이 수정됨[^4]
- SLF4J `2.0.20`으로 업그레이드됨[^4]

성능 개선은 환영이지만, logging stack 변경은 “로그가 깨졌다/색이 이상하다” 같은 피상적 문제부터, “로그가 유실돼서 사고 수습이 안 된다” 같은 본질적 문제까지 만들 수 있습니다.

### Packaging/Build/Image

- nested jar에서 directory entry가 없을 때 manifest attributes가 누락되는 문제[^4]

이건 특히 build pipeline이 fat jar를 내부에서 다시 감싸거나, 특정 아카이빙 도구를 섞는 환경에서 터질 수 있습니다. “우리 서비스는 컨테이너로만 배포하니 상관없다”라고 치부하면 안 되는 게, 컨테이너 안에서도 결국 jar 로딩과 manifest는 진단/운영 도구에서 활용됩니다.

### External integration / clients

- HttpClient5 `5.6.5` 업그레이드[^4]
- Docker Compose 프로세스 runner hang/orphan 가능성 수정[^4]
- MongoDB/Elasticsearch URI credential edge case 수정[^4]

내 경우 운영 장애의 절반은 “나가는 요청”에서 터졌습니다. 그래서 HTTP client smoke test는 우선순위가 높습니다.

### dependency upgrades의 의미

Spring Boot는 “특정 조합을 테스트했다”는 전제를 깔고 dependency를 관리합니다[^5]. 반대로 말하면, 버전 override를 많이 쓰는 팀일수록 패치 업그레이드가 더 위험해집니다. 패치 업그레이드 루틴에서 `dependencyInsight`나 `dependency:tree`로 override된 핵심 라이브러리를 먼저 확인해야 합니다.

## 패치 릴리스 smoke test의 범위: 무엇을 포함하고, 언제 쓰면 안 되나

패치 릴리스 smoke test는 통합 테스트 전체를 대체하지 않습니다. 목적은 한 가지입니다.

- 릴리스 노트에서 위험하다고 판정한 영역이 “우리 서비스의 실제 실행 경로에서” 아직 살아 있는지 확인한다.

이 접근이 특히 유효한 케이스가 있습니다.

- Renovate/Dependabot PR을 자동으로 받는 팀
- 서비스가 많고, 각 서비스의 기능 테스트를 사람 손으로 매번 돌릴 수 없는 팀
- 릴리스가 잦고, 패치 업데이트를 늦추면 보안/운영 리스크가 더 커지는 팀

반대로, smoke test만으로는 부족한 케이스도 명확합니다.

- 데이터 모델이 크게 움직이는 스키마 변경이 포함된 릴리스
- 외부 파트너 API 계약이 바뀐 릴리스
- 트래픽이 낮지만 금액/정산 같은 high-stakes 도메인

Spring Boot 4.1.2는 “패치”라서 스키마가 바뀌진 않겠지만, Web server/HTTP client/Security 같은 운영 표면적이 넓은 층이 움직입니다. smoke test의 투자 대비 효과가 큰 유형입니다.

## 실행 가능한 smoke test 스위트: Actuator/HTTP client/template/DB/JWT

여기서는 실제로 레포에 넣을 수 있는 형태로 예시를 구성합니다. 전형적인 내부 API 서버를 가정합니다.

- Spring MVC + Actuator
- RestClient로 upstream 호출
- Thymeleaf로 내부 운영 페이지 렌더링
- PostgreSQL + Flyway
- Resource Server(JWT)로 보호된 endpoint

Spring Boot는 Java 17+가 필요합니다[^6]. 4.1.2 릴리스 노트에도 Java 27 지원 문서 업데이트가 들어갔고[^4], 실제로는 팀 표준 JDK를 무엇으로 고정할지와 smoke test JVM을 무엇으로 돌릴지가 분리돼야 합니다. 여기서는 예시로 JDK 27 toolchain을 씁니다(실서비스가 21/25를 쓰더라도 smoke test를 27로 한 번 더 돌리는 식의 방어가 가능합니다).

### Gradle 프로젝트 구성

```kotlin
// settings.gradle.kts
rootProject.name = "patch-release-smoke"
```

```kotlin
// build.gradle.kts
plugins {
    java
    id("org.springframework.boot") version "4.1.2"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "io.github.daewooki"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")

    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.springframework.boot:spring-boot-starter-thymeleaf")
    implementation("org.flywaydb:flyway-core")

    testImplementation("org.springframework.boot:spring-boot-starter-test")

    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")

    testRuntimeOnly("org.postgresql:postgresql")
}

tasks.withType<Test> {
    useJUnitPlatform()
}

tasks.register<Test>("smokeTest") {
    description = "Runs smoke tests (fast, production-path focused)."
    group = "verification"

    useJUnitPlatform {
        includeTags("smoke")
    }

    // hang 방지용: graceful shutdown/stop 관련 회귀를 빨리 잡기 위해 강하게 제한
    timeout.set(java.time.Duration.ofMinutes(5))

    shouldRunAfter(tasks.test)
}
```

### 애플리케이션 코드

```java
// src/main/java/io/github/daewooki/patchsmoke/PatchSmokeApplication.java
package io.github.daewooki.patchsmoke;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PatchSmokeApplication {
    public static void main(String[] args) {
        SpringApplication.run(PatchSmokeApplication.class, args);
    }
}
```

```java
// src/main/java/io/github/daewooki/patchsmoke/web/ProductController.java
package io.github.daewooki.patchsmoke.web;

import io.github.daewooki.patchsmoke.web.client.PricingClient;
import io.github.daewooki.patchsmoke.web.db.ProductRepository;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductRepository repository;
    private final PricingClient pricingClient;

    public ProductController(ProductRepository repository, PricingClient pricingClient) {
        this.repository = repository;
        this.pricingClient = pricingClient;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> create(@RequestBody Map<String, Object> body) {
        String name = (String) body.get("name");
        repository.insert(name);
        return Map.of("ok", true);
    }

    @GetMapping(path = "/{name}", produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> get(@PathVariable String name) {
        int basePrice = pricingClient.fetchBasePrice(name);
        return Map.of(
                "name", name,
                "exists", repository.exists(name),
                "basePrice", basePrice
        );
    }
}
```

```java
// src/main/java/io/github/daewooki/patchsmoke/web/client/PricingClient.java
package io.github.daewooki.patchsmoke.web.client;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.Map;

@Component
public class PricingClient {

    private final RestClient restClient;

    public PricingClient(
            RestClient.Builder builder,
            @Value("${pricing.base-url}") String baseUrl
    ) {
        this.restClient = builder.baseUrl(baseUrl).build();
    }

    public int fetchBasePrice(String name) {
        Map<?, ?> res = restClient.get()
                .uri("/pricing/{name}", name)
                .retrieve()
                .body(Map.class);
        Object v = res.get("basePrice");
        return (v instanceof Number n) ? n.intValue() : Integer.parseInt(String.valueOf(v));
    }
}
```

```java
// src/main/java/io/github/daewooki/patchsmoke/web/db/ProductRepository.java
package io.github.daewooki.patchsmoke.web.db;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRepository {

    private final JdbcTemplate jdbcTemplate;

    public ProductRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void insert(String name) {
        jdbcTemplate.update("insert into products(name) values (?) on conflict do nothing", name);
    }

    public boolean exists(String name) {
        Integer cnt = jdbcTemplate.queryForObject(
                "select count(*) from products where name = ?",
                Integer.class,
                name
        );
        return cnt != null && cnt > 0;
    }
}
```

```java
// src/main/java/io/github/daewooki/patchsmoke/web/AdminPageController.java
package io.github.daewooki.patchsmoke.web;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

import java.time.Instant;

@Controller
public class AdminPageController {

    @GetMapping("/admin")
    public String admin(Model model) {
        model.addAttribute("now", Instant.now().toString());
        model.addAttribute("message", "ok");
        return "admin";
    }
}
```

```html
<!-- src/main/resources/templates/admin.html -->
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>admin</title>
</head>
<body>
<h1 th:text="${message}"></h1>
<p th:text="${now}"></p>
</body>
</html>
```

```yaml
# src/main/resources/application.yml
management:
  endpoints:
    web:
      exposure:
        include: health,info

pricing:
  base-url: http://localhost:18080

spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/app
    username: app
    password: app
  flyway:
    enabled: true

server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 10s
```

```sql
-- src/main/resources/db/migration/V1__init.sql
create table if not exists products(
    name text primary key
);
```

운영에서는 `application.yml`의 datasource를 환경별로 분리하겠지만, smoke test는 Testcontainers로 datasource를 대체할 것이므로 여기선 형태만 잡습니다.

### smoke test 1: Actuator + 부팅 확인

부팅이 된다는 건 당연한 것 같지만, auto-configuration과 dependency upgrade가 엮이면 부팅 실패는 언제든 납니다. 게다가 4.1.2는 속성 로더, 로깅, 서버 shutdown 같은 “부팅 후반부/종료 시점” 계층에 수정이 있습니다[^4].

```java
// src/test/java/io/github/daewooki/patchsmoke/smoke/ActuatorSmokeTest.java
package io.github.daewooki.patchsmoke.smoke;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("smoke")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ActuatorSmokeTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void health_endpoint_is_up() {
        ResponseEntity<String> res = rest.getForEntity("/actuator/health", String.class);
        assertThat(res.getStatusCode().value()).isEqualTo(200);
        assertThat(res.getBody()).contains("UP");
    }
}
```

### smoke test 2: RestClient 경로(업스트림 호출)

여기서는 외부 dependency 없이 JDK HttpServer로 upstream을 흉내냅니다. 목표는 “RestClient + HttpClient5 업그레이드”가 걸리는 경로를 실제로 태워 보는 겁니다[^4].

```java
// src/test/java/io/github/daewooki/patchsmoke/smoke/HttpClientSmokeTest.java
package io.github.daewooki.patchsmoke.smoke;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.boot.test.web.client.TestRestTemplate;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("smoke")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ContextConfiguration(initializers = HttpClientSmokeTest.Init.class)
class HttpClientSmokeTest {

    static HttpServer upstream;
    static int upstreamPort;

    static class Init implements ApplicationContextInitializer<ConfigurableApplicationContext> {
        @Override
        public void initialize(ConfigurableApplicationContext applicationContext) {
            try {
                upstream = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
                upstreamPort = upstream.getAddress().getPort();

                upstream.createContext("/pricing/widget", exchange -> {
                    byte[] body = "{\"basePrice\":123}".getBytes(StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().add("Content-Type", "application/json");
                    exchange.sendResponseHeaders(200, body.length);
                    try (OutputStream os = exchange.getResponseBody()) {
                        os.write(body);
                    }
                });

                upstream.start();

                TestPropertyValues.of(
                        "pricing.base-url=http://127.0.0.1:" + upstreamPort
                ).applyTo(applicationContext.getEnvironment());
            }
            catch (Exception e) {
                throw new RuntimeException(e);
            }
        }
    }

    @Autowired
    TestRestTemplate rest;

    @AfterAll
    static void shutdown() {
        if (upstream != null) upstream.stop(0);
    }

    @Test
    void restclient_path_works_end_to_end() {
        ResponseEntity<String> res = rest.getForEntity("/api/products/widget", String.class);
        assertThat(res.getStatusCode().value()).isEqualTo(200);
        assertThat(res.getBody()).contains("\"basePrice\":123");
    }
}
```

이 테스트는 “우리 서비스가 upstream을 호출하고 응답을 해석하는 경로”를 밟습니다. 실제 운영에서 TLS/프록시/타임아웃 같은 변수가 더 붙겠지만, 패치 업그레이드에서 가장 먼저 깨지는 건 이런 기본 경로입니다.

### smoke test 3: template 렌더링(Thymeleaf)

Spring Boot 패치에서 template 엔진이 직접 언급되지 않아도, Jackson/Servlet 컨테이너/리소스 로딩이 흔들리면 template 렌더링이 같이 흔들립니다. 나는 internal admin 페이지가 있으면 무조건 넣습니다.

```java
// src/test/java/io/github/daewooki/patchsmoke/smoke/TemplateSmokeTest.java
package io.github.daewooki.patchsmoke.smoke;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("smoke")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TemplateSmokeTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void thymeleaf_page_renders() {
        ResponseEntity<String> res = rest.getForEntity("/admin", String.class);
        assertThat(res.getStatusCode().value()).isEqualTo(200);
        assertThat(res.getBody()).contains("<h1>ok</h1>");
    }
}
```

### smoke test 4: DB + migration + transaction 경로(Testcontainers)

DB 경로는 “driver 버전이 바뀌었다” 같은 단순 문제 말고도, 부트 스트랩 과정(Flyway, connection pool, transaction manager)이 얽혀 있어서 패치 업그레이드 때 회귀가 자주 나옵니다.

```java
// src/test/java/io/github/daewooki/patchsmoke/smoke/DatabaseSmokeTest.java
package io.github.daewooki.patchsmoke.smoke;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.test.context.ContextConfiguration;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("smoke")
@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ContextConfiguration(initializers = DatabaseSmokeTest.Init.class)
class DatabaseSmokeTest {

    @Container
    static PostgreSQLContainer<?> pg = new PostgreSQLContainer<>("postgres:17")
            .withDatabaseName("app")
            .withUsername("app")
            .withPassword("app");

    static class Init implements ApplicationContextInitializer<ConfigurableApplicationContext> {
        @Override
        public void initialize(ConfigurableApplicationContext ctx) {
            TestPropertyValues.of(
                    "spring.datasource.url=" + pg.getJdbcUrl(),
                    "spring.datasource.username=" + pg.getUsername(),
                    "spring.datasource.password=" + pg.getPassword(),
                    "spring.flyway.enabled=true"
            ).applyTo(ctx.getEnvironment());
        }
    }

    @Autowired
    DataSource dataSource;

    @Test
    void flyway_migration_applied_and_basic_query_works() throws Exception {
        try (Connection c = dataSource.getConnection();
             Statement st = c.createStatement()) {

            ResultSet rs = st.executeQuery("select count(*) from products");
            assertThat(rs.next()).isTrue();
            assertThat(rs.getInt(1)).isEqualTo(0);
        }
    }
}
```

테스트가 단순해 보이지만, 여기에는 실제 운영에서 중요한 두 가지가 들어 있습니다.

- Flyway가 migration을 적용할 수 있는가
- datasource/driver/connection 초기화가 정상인가

### smoke test 5: issuer-uri 공백 + jwk-set-uri 케이스(JWT)

4.1.2 bug fix 중 가장 운영 친화적으로 터지는 게 JWT 경로입니다[^4]. 특히 `issuer-uri`가 환경 변수 치환 과정에서 빈 문자열이 되는 경우가 많습니다. `issuer-uri`를 설정하라고 가이드가 말해도, 현실에서는 인프라 템플릿이 잘못돼서 공백이 들어가고 `jwk-set-uri`만 살아 있는 경우가 생깁니다.

테스트는 “실제로 JWK Set endpoint를 띄우고, 토큰을 서명해서, 보호된 endpoint를 통과”시키는 방식으로 구성합니다.

```java
// src/main/java/io/github/daewooki/patchsmoke/web/SecureHelloController.java
package io.github.daewooki.patchsmoke.web;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class SecureHelloController {

    @GetMapping("/api/secure/hello")
    public Map<String, Object> hello(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
                "sub", jwt.getSubject(),
                "iss", String.valueOf(jwt.getIssuer())
        );
    }
}
```

```java
// src/main/java/io/github/daewooki/patchsmoke/web/SecurityConfig.java
package io.github.daewooki.patchsmoke.web;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(reg -> reg
                        .requestMatchers("/actuator/**", "/admin").permitAll()
                        .requestMatchers("/api/secure/**").authenticated()
                        .anyRequest().permitAll()
                )
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

```java
// src/test/java/io/github/daewooki/patchsmoke/smoke/JwtEdgeCaseSmokeTest.java
package io.github.daewooki.patchsmoke.smoke;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.SignedJWT;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.http.*;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.boot.test.web.client.TestRestTemplate;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("smoke")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ContextConfiguration(initializers = JwtEdgeCaseSmokeTest.Init.class)
class JwtEdgeCaseSmokeTest {

    static RSAKey rsaJwk;
    static HttpServer jwkServer;
    static String jwkSetUri;

    static class Init implements ApplicationContextInitializer<ConfigurableApplicationContext> {
        @Override
        public void initialize(ConfigurableApplicationContext ctx) {
            try {
                rsaJwk = new RSAKeyGenerator(2048)
                        .keyID("k1")
                        .generate();

                jwkServer = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
                int port = jwkServer.getAddress().getPort();

                jwkServer.createContext("/.well-known/jwks.json", exchange -> {
                    byte[] body = new JWKSet(rsaJwk.toPublicJWK()).toJSONObject().toJSONString()
                            .getBytes(StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().add("Content-Type", "application/json");
                    exchange.sendResponseHeaders(200, body.length);
                    try (OutputStream os = exchange.getResponseBody()) {
                        os.write(body);
                    }
                });

                jwkServer.start();
                jwkSetUri = "http://127.0.0.1:" + port + "/.well-known/jwks.json";

                // 여기서 핵심: issuer-uri를 빈 문자열로 명시
                TestPropertyValues.of(
                        "spring.security.oauth2.resourceserver.jwt.issuer-uri=",
                        "spring.security.oauth2.resourceserver.jwt.jwk-set-uri=" + jwkSetUri
                ).applyTo(ctx.getEnvironment());
            }
            catch (Exception e) {
                throw new RuntimeException(e);
            }
        }
    }

    @Autowired
    TestRestTemplate rest;

    @AfterAll
    static void shutdown() {
        if (jwkServer != null) jwkServer.stop(0);
    }

    @Test
    void jwt_is_accepted_when_issuer_uri_is_empty_but_jwk_set_uri_is_set() throws Exception {
        Instant now = Instant.now();

        var claims = new com.nimbusds.jwt.JWTClaimsSet.Builder()
                .subject("user-123")
                .issueTime(Date.from(now))
                .expirationTime(Date.from(now.plusSeconds(300)))
                .build();

        SignedJWT jwt = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .type(JOSEObjectType.JWT)
                        .keyID(rsaJwk.getKeyID())
                        .build(),
                claims
        );
        jwt.sign(new RSASSASigner(rsaJwk.toPrivateKey()));

        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(jwt.serialize());

        ResponseEntity<String> res = rest.exchange(
                "/api/secure/hello",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );

        assertThat(res.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(res.getBody()).contains("user-123");
    }
}
```

이 테스트는 “Boot 패치에서 보안 경로 회귀가 없었는지”를 가장 짧은 시간에 확인하는 장치입니다.

### smoke test 6: graceful shutdown이 멈추지 않는지(회귀 탐지)

4.1.2는 graceful shutdown과 관련된 bug fix가 있습니다[^4]. 이건 통합 테스트로 완벽하게 재현하기는 어렵지만, “즉시 종료를 걸었을 때 테스트가 hang하지 않게” 만드는 것만으로도 충분히 가치가 있습니다.

```java
// src/test/java/io/github/daewooki/patchsmoke/smoke/GracefulShutdownSmokeTest.java
package io.github.daewooki.patchsmoke.smoke;

import io.github.daewooki.patchsmoke.PatchSmokeApplication;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import org.springframework.boot.SpringApplication;
import org.springframework.context.ConfigurableApplicationContext;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;

@Tag("smoke")
class GracefulShutdownSmokeTest {

    @Test
    void context_start_and_immediate_close_does_not_hang() {
        assertTimeoutPreemptively(Duration.ofSeconds(15), () -> {
            SpringApplication app = new SpringApplication(PatchSmokeApplication.class);
            app.setDefaultProperties(java.util.Map.of(
                    "server.port", "0",
                    "server.shutdown", "graceful",
                    "spring.lifecycle.timeout-per-shutdown-phase", "5s"
            ));

            try (ConfigurableApplicationContext ctx = app.run()) {
                // 바로 종료
            }
        });
    }
}
```

이런 테스트는 “원인을 알려주진 못해도” 패치 업그레이드 직후 가장 치명적인 형태의 회귀(종료 hang)를 CI에서 즉시 잡아냅니다.

### 실행 명령과 예상 결과

```bash
./gradlew clean smokeTest
```

성공하면 smokeTest task가 green입니다. 실패하면 “어느 경로(Actuator/HTTP client/template/DB/JWT/shutdown)”가 깨졌는지가 바로 나옵니다. 이게 릴리스 노트 기반 위험 매핑의 핵심 효과입니다.

## Upgrading 가이드가 말하는 것: properties migrator는 패치에선 덜 중요하지만, 루틴은 같아야 한다

Spring Boot 공식 upgrading 문서는 새 feature release로 넘어갈 때 `spring-boot-properties-migrator`를 이용해 properties 변경을 진단/완화할 수 있다고 안내합니다[^7]. 4.1.2 같은 maintenance release에서 properties migrator가 직접 필요하진 않을 가능성이 큽니다.

그래도 이 문서가 주는 메시지는 하나입니다.

- 업그레이드는 “릴리스 노트 → 진단 도구 → 제거”의 루틴으로 해야 한다.

patch upgrade 템플릿에서도 같은 구조를 유지하는 게 좋습니다. properties migrator 대신 smoke test가 그 자리를 차지합니다. 즉, 패치도 “잠깐 끼워 넣고, 검증하고, 루틴을 없애지 않는다”가 팀 표준이 됩니다.

## 배포 링(rings) + 롤백을 템플릿에 포함시키는 이유

CI가 green이어도 배포는 항상 다르게 터집니다. 그래서 패치 릴리스를 운영 계약으로 만들려면 smoke test까지만으로는 부족합니다. 최소한 다음이 같이 있어야 합니다.

- 배포가 단계적으로 진행된다(링)
- 각 단계에서 관측할 지표가 정의돼 있다
- 실패 시 자동/수동 롤백 경로가 문서화돼 있고 실제로 동작한다

### Kubernetes Deployment만으로도 필요한 롤백 계약

Kubernetes Deployment는 revision history를 유지하고 `kubectl rollout undo`로 롤백할 수 있습니다[^8]. 여기서 가장 실무적인 함정은 `revisionHistoryLimit`을 줄이다가 0으로 만들어 롤백 자체를 불가능하게 만드는 경우입니다. Kubernetes 문서도 `revisionHistoryLimit`을 0으로 하면 rollback이 사실상 비활성화된다고 명시합니다[^8].

패치 릴리스 템플릿에는 다음을 강제하는 게 좋습니다.

- `revisionHistoryLimit`는 최소 2 이상
- 배포 파이프라인에 “이전 revision으로 롤백 명령이 성공한다”를 확인하는 dry-run 단계 포함

이건 도구 문제가 아니라 습관 문제입니다. 평소엔 아무도 롤백을 안 해 보다가, 장애가 난 순간에만 롤백을 시도하면 그때는 이미 늦습니다.

### Argo Rollouts를 쓰는 조직이라면: 링/자동 롤백을 표준화하기 쉽다

링 운영은 결국 progressive delivery로 갑니다. Argo Rollouts는 Rollout CRD로 canary/blue-green을 제공하고, AnalysisTemplate/AnalysisRun으로 지표 기반 자동 promote/rollback을 연결할 수 있습니다[^9].

또 하나 중요한 기능이 rollback window입니다. Argo Rollouts는 기본적으로 과거 spec을 다시 apply하면 “업데이트”처럼 step/analysis를 다시 실행할 수 있는데, rollback은 보통 즉시 복구가 목적이라 그 동작이 오히려 방해가 됩니다. rollback window를 설정하면 특정 revision 범위에서는 step을 건너뛰고 빠른 롤백을 하게 만들 수 있습니다[^10].

이 기능이 패치 릴리스 운영 템플릿에 잘 맞는 이유는 간단합니다.

- 패치 업그레이드는 변화가 작다고 믿고 싶지만, 실제 장애는 빨리 복구해야 한다.
- 롤백은 “검증된 안정 버전으로 즉시 복귀”가 목적이지, 롤백 과정에서 canary를 다시 하자는 게 아니다.

아래는 “링0(내부/카나리) → 링1(전체)”로 단순화한 예시입니다. 실제로는 5%/25%/100% 같은 단계로 늘리면 됩니다.

```yaml
# k8s/rollout.yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: patch-smoke
spec:
  replicas: 10
  revisionHistoryLimit: 5
  rollbackWindow:
    revisions: 3
  selector:
    matchLabels:
      app: patch-smoke
  template:
    metadata:
      labels:
        app: patch-smoke
    spec:
      containers:
        - name: app
          image: ghcr.io/your-org/patch-smoke:4.1.2
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health
              port: 8080
  strategy:
    canary:
      steps:
        - setWeight: 10
        - pause: { duration: 2m }
        - setWeight: 50
        - pause: { duration: 5m }
        - setWeight: 100
```

여기서 핵심은 “canary steps가 있다”가 아니라, **rollbackWindow**와 **revisionHistoryLimit** 같은 롤백 계약이 명시돼 있다는 점입니다. canary를 아무리 잘해도 롤백이 느리면 운영 템플릿으로는 실패입니다.

Argo Rollouts는 `kubectl argo rollouts undo`로 롤백 커맨드도 제공합니다[^11]. Kubernetes Deployment의 `kubectl rollout undo`와 동작/대상이 다르기 때문에, 팀 표준을 하나로 고정해야 합니다.

## Renovate/Dependabot 유입을 전제로 한 운영 규칙

패치 릴리스 운영 템플릿이 팀에 붙으려면 “봇이 들어오는 걸 막자”가 아니라 “봇이 들어오는 것을 전제로, 안전장치를 자동화하자”가 돼야 합니다.

### Renovate: automerge를 쓰면 시간대가 곧 리스크가 된다

Renovate는 automerge schedule을 설정할 수 있고[^2], schedule preset도 제공합니다[^12].

문제는 많은 조직에서 automerge를 켠 뒤 “주말 포함 non-office hours” 같은 preset을 무심코 붙인다는 점입니다. 그러면 Spring Boot 패치가 금요일 밤/토요일 새벽에 merge될 수 있습니다.

내 결론은 단순합니다.

- 패치 automerge를 쓸 거면, smokeTest가 PR 단위로 통과해야 하고
- automerge schedule은 “사람이 대응 가능한 시간대”로 고정돼야 합니다.

### Dependabot: ignore/allow로 패치도 통제할 수 있지만, 운영 템플릿이 먼저다

Dependabot은 `ignore`에 `update-types`를 써서 특정 semver 레벨을 무시할 수 있습니다[^13]. 이걸로 패치 유입을 줄일 수는 있습니다.

다만 패치를 무시하면 결국 패치가 쌓이고, 어느 순간 한 번에 크게 터집니다. 그래서 나는 “유입량을 줄이는 구성”보다 “유입된 패치가 안전하게 통과하는 자동 검증”이 먼저라고 봅니다.

## 4.1.2에서 특히 주목한 변경과, smoke test로 묶는 방식

4.1.2 릴리스 노트 항목을 운영 관점에서 다시 보면, smoke test가 커버해야 할 포인트가 명확해집니다.

- JWT edge case: 위의 `JwtEdgeCaseSmokeTest`로 직접 고정
- server shutdown hang/타이밍 이슈: `GracefulShutdownSmokeTest`로 회귀 감지
- HttpClient/RestClient 경로: `HttpClientSmokeTest`로 upstream 호출 경로 고정
- Tomcat 업그레이드: Actuator/HTTP 경로 + graceful shutdown 조합으로 간접 커버
- Jackson 업그레이드: controller 응답 JSON 파싱, upstream JSON 파싱 경로로 간접 커버
- properties loader: 조직에서 특수 키를 쓰는 서비스라면 별도 테스트 추가

여기서 중요한 건 “각 smoke test가 릴리스 노트 항목과 연결돼 있어야 한다”는 점입니다. smoke test 파일 상단에 “릴리스 노트 링크”를 주석으로 박아두는 것만으로도, 시간이 지나서 누가 봐도 왜 존재하는지 이해가 됩니다.

## 이 템플릿을 프로덕션 운영에 붙일 때의 함정과 트레이드오프

### smoke test는 빠르게 설계해야 하고, 느려지면 아무도 안 돈다

패치 업그레이드의 현실은 “자주 들어온다”입니다. smokeTest가 20분 걸리기 시작하면, 패치 PR은 쌓이고 결국 한 번에 올립니다. 그러면 smoke test의 목적이 무너집니다.

- DB는 1개(Testcontainers 1개)로 끝냅니다.
- upstream 호출은 외부 dependency 없이 in-process로 구성합니다.
- JWT는 최소한의 토큰 발급/검증만 확인합니다.

### 링 배포는 조직 문화에 맞게 최소 단계부터 시작해야 한다

Argo Rollouts가 있으면 좋지만, 없다고 해서 못 하는 건 아닙니다. 다만 “링”이란 용어만 도입하고 실제로 트래픽 분리/관측/롤백이 없으면 오히려 혼란만 생깁니다.

- Kubernetes Deployment만 쓰는 조직이라면, 최소한 `revisionHistoryLimit`과 `kubectl rollout undo` 절차를 템플릿에 넣는 것으로 시작합니다[^8].
- progressive delivery 컨트롤러가 있는 조직이라면, rollback window 같은 기능을 먼저 표준화합니다[^10].

### dependency override가 많은 팀일수록 패치 릴리스가 더 위험해진다

Spring Boot는 curated dependency set을 전제로 테스트합니다[^5]. override가 많으면 smoke test에서 커버하지 못한 조합이 나오기 쉽습니다.

이 경우 템플릿에 “override 목록 출력”을 넣는 게 좋습니다.

- Gradle: `./gradlew dependencyInsight --dependency jackson-bom` 같은 식으로 핵심만 추적
- Maven: `mvn dependency:tree`로 override 확인

## 도입 판단 기준: 패치 릴리스 운영 템플릿이 성공하는 조건

내 기준에서 성공 조건은 세 가지입니다.

1) 패치 PR이 들어왔을 때 사람이 읽어야 하는 정보가 “릴리스 노트 → 위험 영역 매핑 표” 한 장으로 압축돼야 합니다.

2) smokeTest는 PR마다 자동으로 돌고, 실패했을 때 “어느 운영 경로가 깨졌는지”를 5분 안에 말해줘야 합니다.

3) 배포는 링으로 나뉘고, 롤백은 커맨드가 아니라 계약이어야 합니다. Kubernetes든 Argo Rollouts든, 되돌릴 수 있는 길이 실제로 열려 있어야 합니다[^8][^11].

Spring Boot 4.1.2처럼 패치 릴리스가 짧게 공지되는 날(2026-10-23)에 팀이 해야 할 일은 “이번 건은 괜찮겠지”가 아니라, 다음 주말에도 같은 방식으로 처리할 수 있는 템플릿을 고정하는 것입니다.

## 참고 자료
- [Spring Boot 4.1.2 available now](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/)
- [Spring Boot v4.1.2 GitHub release](https://github.com/spring-projects/spring-boot/releases/tag/v4.1.2)
- [Upgrading Spring Boot](https://docs.spring.io/spring-boot/upgrading.html)
- [Installing Spring Boot](https://docs.spring.io/spring-boot/installing.html)
- [Managing Dependencies](https://docs.spring.io/spring-boot/4.1-SNAPSHOT/gradle-plugin/managing-dependencies.html)
- [Renovate configuration options: automergeSchedule](https://docs.renovatebot.com/configuration-options/#automergeschedule)
- [Renovate schedule presets](https://docs.renovatebot.com/presets-schedule/)
- [Controlling which dependencies are updated by Dependabot](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependency-security/controlling-dependencies-updated)
- [Dependabot options reference](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference?learn=dependency_version_updates)
- [Update a Deployment Without Downtime](https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/)
- [Argo Rollouts architecture](https://argoproj.github.io/argo-rollouts/architecture/)
- [Argo Rollouts rollback window](https://argoproj.github.io/argo-rollouts/features/rollback/)
- [kubectl argo rollouts undo](https://argoproj.github.io/argo-rollouts/generated/kubectl-argo-rollouts/kubectl-argo-rollouts_undo/)
- [Spring Boot 4 마이그레이션 실전: 진짜 깨지는 지점들](https://daewooki.github.io/posts/spring-boot-4-migration-real-breakages/)
- [Grafana 패치 업그레이드 검증 자동화 설계](https://daewooki.github.io/posts/grafana-patch-upgrade-automation/)
- [ClickHouse 패치도 릴리스처럼 다루는 롤링 업그레이드 설계](https://daewooki.github.io/posts/clickhouse-patch-rolling-upgrade-contract-tests/)
- [Kubernetes 1.35.10 패치 릴리스: 정기 패치를 운영 계약으로 바꾸는 법](https://daewooki.github.io/posts/kubernetes-patch-release-ops-contract/)
- [Java 27 GA: PQC·성능·프리뷰가 섞인 릴리스에서 업그레이드 전략을 나누는 법](https://daewooki.github.io/posts/java-27-upgrade-runbook-strategy/)

[^1]: <https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/>
[^2]: <https://docs.renovatebot.com/configuration-options/#automergeschedule>
[^3]: <https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependency-security/controlling-dependencies-updated>
[^4]: <https://github.com/spring-projects/spring-boot/releases/tag/v4.1.2>
[^5]: <https://docs.spring.io/spring-boot/4.1-SNAPSHOT/gradle-plugin/managing-dependencies.html>
[^6]: <https://docs.spring.io/spring-boot/installing.html>
[^7]: <https://docs.spring.io/spring-boot/upgrading.html>
[^8]: <https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/>
[^9]: <https://argoproj.github.io/argo-rollouts/architecture/>
[^10]: <https://argoproj.github.io/argo-rollouts/features/rollback/>
[^11]: <https://argoproj.github.io/argo-rollouts/generated/kubectl-argo-rollouts/kubectl-argo-rollouts_undo/>
[^12]: <https://docs.renovatebot.com/presets-schedule/>
[^13]: <https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference?learn=dependency_version_updates>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
