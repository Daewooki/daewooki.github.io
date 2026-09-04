---
title: "Docker 멀티스테이지 빌드 활용법: 이미지 크기와 보안을 동시에 잡기"
description: "Docker image는 배포 단위이자 운영 환경 그 자체라서, 크기와 보안 수준이 곧 비용과 장애 확률로 이어집니다."
date: 2025-12-21 09:00:00 +0900
categories: [Infrastructure, Docker]
tags: [infrastructure, docker]
---

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
## 들어가며
Docker image는 배포 단위이자 운영 환경 그 자체라서, 크기와 보안 수준이 곧 비용과 장애 확률로 이어집니다. Multi-stage build는 build toolchain은 버리고 runtime만 남겨 이미지 용량을 줄이고, attack surface까지 함께 줄이는 가장 실용적인 패턴입니다.

---

## 🎯 멀티스테이지 빌드 핵심 개념
Multi-stage build는 하나의 Dockerfile 안에서 여러 개의 `FROM`을 사용해 stage를 나누고, 최종 stage에는 필요한 산출물만 `COPY --from=...`로 가져오는 방식입니다. 핵심은 “컴파일/빌드에 필요한 것”과 “실행에 필요한 것”을 분리해, 최종 image에 compiler, package manager, dev dependency가 남지 않게 만드는 데 있습니다.

주로 아래 상황에서 효과가 큽니다.

- **Go/Java/Node/Python** 등 빌드 과정에서 dependency가 많고 결과물은 상대적으로 단순할 때
- **보안 요구사항**이 있어 runtime image에 shell, build tool, credential이 남는 것을 피해야 할 때
- CI에서 build cache를 잘 활용해 **빌드 시간 단축**까지 노릴 때 (`--mount=type=cache` 등)

또한 stage에 이름을 붙이면(`AS builder`) 의도가 명확해지고, 특정 stage만 빌드/디버깅하기도 쉬워집니다(`--target builder`).

---

## 💻 코드 예제 (실제 동작)
아래 예제들은 각각 독립적으로 동작하며, 멀티스테이지 빌드의 대표 패턴(compile → minimal runtime, dependency install → runtime only, static asset build → serve)을 보여줍니다.

### 1. Go: 정적 바이너리만 남기는 최소 이미지
설명: builder stage에서 Go binary를 만들고, 최종 stage는 `scratch`로 두어 실행에 필요한 파일만 포함합니다. 결과적으로 image가 매우 작고, 불필요한 toolchain이 제거됩니다.

```dockerfile
# Dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /src

# 의존성 캐시 최적화
COPY go.mod go.sum ./
RUN go mod download

COPY . .
# 정적 링크 바이너리 생성
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o app ./...

FROM scratch
COPY --from=builder /src/app /app
EXPOSE 8080
ENTRYPOINT ["/app"]
```

```go
// main.go
package main

import (
	"fmt"
	"net/http"
)

func main() {
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, "hello multi-stage")
	})
	_ = http.ListenAndServe(":8080", nil)
}
```

빌드/실행:

```bash
docker build -t go-multistage .
docker run --rm -p 8080:8080 go-multistage
```

---

### 2. Node.js: devDependencies 제거 + production 런타임만 유지
설명: 첫 stage에서 `npm ci`로 의존성을 설치하고 build까지 수행한 뒤, 두 번째 stage에서는 `npm ci --omit=dev`로 production 의존성만 설치합니다. 최종 image에는 `node_modules`가 남지만 devDependencies와 build tool은 제거됩니다.

```dockerfile
# Dockerfile
FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY --from=builder /app/dist ./dist
EXPOSE 3000
CMD ["node", "dist/server.js"]
```

```json
// package.json
{
  "name": "node-multistage",
  "version": "1.0.0",
  "type": "commonjs",
  "scripts": {
    "build": "node build.js"
  },
  "dependencies": {
    "express": "^4.19.2"
  },
  "devDependencies": {
    "typescript": "^5.6.3"
  }
}
```

```js
// build.js (간단한 빌드 산출물 생성)
const fs = require("fs");
fs.mkdirSync("dist", { recursive: true });
fs.writeFileSync(
  "dist/server.js",
  `
const express = require("express");
const app = express();
app.get("/", (req, res) => res.send("hello multi-stage node"));
app.listen(3000, () => console.log("listening on 3000"));
`.trim()
);
console.log("build done");
```

빌드/실행:

```bash
docker build -t node-multistage .
docker run --rm -p 3000:3000 node-multistage
```

---

## 💡 실전 팁 (Best Practices)
### 1. stage 이름과 `--target`으로 디버깅 생산성 올리기
CI에서 실패 원인 추적 시, 최종 stage만 보지 말고 builder stage를 직접 실행해 확인하면 빠릅니다.

```bash
docker build --target builder -t myapp:builder .
docker run --rm -it myapp:builder sh
```

---

### 2. dependency 캐시를 먼저 고정해 빌드 시간을 줄이기
`COPY . .` 전에 lockfile만 복사해 `npm ci`, `go mod download` 등을 수행하면, 소스 변경이 잦아도 dependency layer cache가 유지됩니다.

```dockerfile
# Dockerfile snippet
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
```

---

### 3. 최종 stage는 가능한 한 minimal base로 줄이기
runtime에 shell이 필요 없고 정적 바이너리라면 `scratch`, 동적 라이브러리가 필요하면 `distroless`나 `alpine` 등으로 타협합니다. “작게 만들기”는 곧 “업데이트/스캔 대상 줄이기”로 이어집니다.

```dockerfile
# Dockerfile snippet
FROM gcr.io/distroless/base-debian12 AS runtime
COPY --from=builder /src/app /app
USER 65532:65532
ENTRYPOINT ["/app"]
```

---

## 🚀 마무리
Multi-stage build는 빌드 환경과 실행 환경을 분리해 image size를 줄이고, 불필요한 toolchain을 제거해 보안과 운영 안정성을 함께 끌어올리는 패턴입니다. 언어와 프레임워크가 달라도 “builder에서 만들고, runtime에는 결과물만 남긴다”는 원칙만 지키면 대부분의 Dockerfile을 개선할 수 있습니다. 다음 글에서는 Docker BuildKit 캐시 최적화와 `--mount=type=cache` 활용법을 다뤄보겠습니다!