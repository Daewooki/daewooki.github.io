---
title: "Grafana의 운영 단위를 대시보드에서 Notebooks로 옮기는 법"
description: "Grafana 13.3의 cross-dashboard variables와 Notebooks를 운영 자산으로 다루기 위한 표준화·재현성·교육 관점의 실전 전환기."
date: 2026-11-04 14:33:31 +0900
categories: ["Data", "Grafana"]
tags: ["grafana", "observability", "dashboards", "notebooks", "terraform"]
render_with_liquid: false
---

## 릴리스 노트가 말하는 변화의 방향: 화면 기능이 아니라 자산의 단위
Grafana 13.3.0은 2026-10-27에 릴리스됐고, 공식 다운로드 페이지에도 릴리스 날짜가 명시돼 있습니다. 이 버전에서 운영자 관점으로 가장 큰 변화는 패널이 몇 개 추가됐다가 아니라, 관측성 자산을 쪼개는 기준이 바뀐다는 점입니다.[^1]

공식 블로그는 13.3의 하이라이트를 세 가지로 잡았습니다. cross-dashboard variables, Notebooks, 그리고 시각적 UI refresh입니다.[^2] 이 셋은 서로 독립 기능처럼 보이지만, 운영 모델 관점에서는 한 묶음으로 읽히는 지점이 있습니다.

- 대시보드의 재사용성은 결국 variables의 재사용성(표준화)에서 시작합니다. cross-dashboard variables는 이를 조직 단위에서 강제할 수 있는 첫 장치입니다.[^2]
- 조사/트러블슈팅의 결과물을 대시보드 링크 모음으로 남기는 대신, 쿼리와 근거와 판단을 한 문서로 고정해두는 artifact가 필요합니다. Notebooks는 그 artifact를 Grafana 안으로 끌어옵니다.[^2]
- UI refresh는 겉모습 이야기처럼 들리지만, 실제로는 운영자가 만들어둔 교육 자료, 런북 스크린샷, 온보딩 문서의 유효기간을 줄입니다. 또한 feature toggle 기반으로 점진 롤아웃되는 기능이 늘어날수록, “우리 조직에서 지금 켜져 있는 UX”를 전제로 한 문서화가 더 중요해집니다.[^3]

여기에 더해서, Grafana의 “What’s next”는 13.3 시점의 deprecation/breaking change를 여러 개 올려두고 있습니다. 플러그인 보안 격리 기능(Plugin Frontend Sandbox) deprecation, 보안 헤더 관련 설정(x_xss_protection) deprecation, 그리고 모바일 폰에서의 대시보드 edit mode 제거 예고가 대표적입니다.[^4]

결론적으로 13.3은 “대시보드를 더 잘 그리는 버전”이 아니라, 관측성 운영의 저장 형식이 **Dashboard 중심에서 Question/Investigation 중심으로 이동**하기 시작한 버전으로 보는 편이 더 설명력이 좋습니다. 그 이동의 마찰 지점이 (1) 변수 관리/표준화, (2) 조사 재현성, (3) UI/디프리케이션에 따른 교육 비용으로 정리됩니다.

## cross-dashboard variables: 변수는 더 이상 대시보드 내부 설정이 아니다
Grafana가 문서에서 정의하는 variables는 원래 “대시보드 안에서 쓰는 placeholder”였습니다. 값을 바꾸면 그 변수를 참조하는 모든 요소(쿼리, 제목, 링크 등)가 바뀌는 구조입니다.[^5]

13.3에서 추가된 cross-dashboard variables는 그 전제를 뒤집습니다. 변수의 정의가 대시보드 JSON 안에 들어있지 않아도 되고, 조직(또는 폴더) 스코프의 공유 자산이 됩니다. 공식 문서는 이를 “dashboard-scoped variables”와 “cross-dashboard variables”로 구분합니다.[^5]

### 글로벌/폴더 스코프가 의미하는 것
cross-dashboard variables는 스코프를 두 가지로 제공합니다.

- Global: 조직의 모든 대시보드에서 사용할 수 있음[^6]
- Folder: 같은 폴더에 있는 대시보드에서만 사용할 수 있음[^6]

운영에서 이 구분이 중요한 이유는 “표준화”의 레벨을 나눌 수 있기 때문입니다.

- Global로 만들 변수는, 조직 전체에서 의미가 변하지 않는 축이어야 합니다. 예를 들면 env(prod/staging), region, tenant 같은 축은 글로벌 후보입니다.
- Folder 변수는, 조직 전체 표준이라고 하기엔 과하지만 팀/서비스 단위로 반복되는 축을 흡수할 때 유용합니다. 예를 들면 cluster, namespace, service는 팀 폴더 범위에서만 공유하는 편이 관리가 편합니다.

여기서 핵심은 “공유가 곧 중앙집중”이라는 점입니다. 중앙집중은 drift를 줄이는 대신 blast radius를 키웁니다. 한 변수를 잘못 수정하면 폴더 내/조직 내의 모든 대시보드가 동시에 흔들립니다. 그래서 cross-dashboard variables는 기능 자체보다, 변경 관리 모델(리뷰/승인/롤백)을 함께 설계해야 쓸만해집니다.

### 변수 정의를 표준화할 때 생기는 구체적인 이득
cross-dashboard variables가 주는 실익은 문서에서 말하듯 “duplicate work, configuration drift” 제거입니다.[^2] 다만 운영에서 더 크게 체감하는 지점은 따로 있습니다.

1) 링크와 런북이 안정화됩니다.
- 대시보드 URL에 var- 파라미터로 변수 값을 넣어 컨텍스트를 전달하는 패턴이 널리 쓰이는데, 변수 이름이 대시보드마다 다르면 링크가 깨집니다. URL 변수 규칙은 var- 접두사를 쓰는 방식입니다.[^7]
- cross-dashboard variables로 이름을 강제하면, “어디서든 var-env, var-cluster” 같은 링크 규칙을 런북에 박아둘 수 있습니다.

2) 온콜이 기억해야 할 UI 동작이 줄어듭니다.
- 이전에는 대시보드마다 env 변수가 query variable인지 custom variable인지, includeAll이 켜져 있는지, refresh 정책이 어떤지 전부 달랐습니다.
- 중앙에서 변수 정의를 고정하면, 사용자는 값만 바꾸면 됩니다. 설정은 관리 대상이 됩니다.

3) 데이터 소스 레벨의 naming까지 끌어올릴 수 있습니다.
- 변수는 쿼리/제목/링크/transformations에 쓰일 수 있습니다.[^5] 즉, naming 표준은 단순히 드롭다운 UX가 아니라 데이터 모델의 표준화입니다.

### 디스플레이 옵션이 바뀌면 교육도 바뀐다
cross-dashboard variables 문서에는 Display 옵션이 구체적으로 나옵니다. 변수를 상단에 노출할지, label을 숨길지, controls menu로 넣을지, 완전히 숨길지 선택 가능합니다.[^6]

이 옵션이 운영자 교육에 미치는 영향은 꽤 큽니다.

- controls menu를 쓰면 대시보드 상단이 덜 복잡해지는 대신, “변수는 상단에 있다”는 교육 전제를 버려야 합니다.
- hidden을 쓰면 기본값이 사실상 정책이 됩니다. 특히 변수가 hidden인데 includeAll 등과 상호작용하면, 사용자가 의도치 않게 first value를 선택하는 식의 함정이 생길 수 있습니다. Grafana 변수 일반 문서에서도 hidden과 selection 옵션의 상호작용을 경고합니다.[^8]

운영 문서/교육은 스크린샷 중심으로 만들기 쉽습니다. 그런데 변수가 controls menu로 이동하면 기존 자료가 무너집니다. 이건 기능 추가가 아니라 “사용자 동작 경로”가 바뀌는 문제입니다.

## Notebooks: 조사 결과를 ‘대시보드 즐겨찾기’ 대신 ‘재현 가능한 기록’으로 남긴다
Notebooks는 public preview이며, self-managed에서는 `dashboard.notebooks` feature toggle을 켜야 합니다.[^9] Grafana는 Notebooks를 “notes + queries + visualizations를 한 문서로 묶는 artifact”로 정의합니다.[^9]

### 대시보드가 아닌 Notebook이 운영 자산이 될 때의 변화
대시보드는 상태를 보여주기엔 좋지만, 조사 과정을 보존하기에는 구조적으로 약합니다.

- 대시보드는 결과 화면이지, 질문의 흐름이 아닙니다.
- Explore에서 쿼리를 바꾸고, 대시보드로 돌아가고, 다시 로그로 점프하고… 이런 맥락이 탭과 스크린샷으로 흩어집니다.

Notebooks는 이 흩어진 맥락을 “문서”로 고정합니다. 대시보드 패널/Explore 쿼리/Grafana Assistant의 findings를 노트에 끌어오고, 그 옆에 사람이 이유를 씁니다.[^2]

운영 관점에서 나는 이걸 “런북의 새로운 최소 단위”로 봅니다.

- 기존 런북: 특정 대시보드 링크 + 특정 패널을 보라 + 특정 로그 쿼리를 실행하라
- Notebook 런북: 이 패널과 이 쿼리를 왜 봤는지 + 어떤 분기에서 어떤 가설을 버렸는지 + 다음 사람이 그대로 재실행할 수 있는 형태

대시보드는 팀이 공유하는 지도(map)에 가깝고, Notebook은 사건 단위의 리플레이(replay)입니다.

### 재현성의 핵심은 ‘시간’과 ‘쿼리’인데, Notebooks는 둘 다를 다룬다
Notebooks 문서에는 중요한 제약이 하나 명확히 적혀 있습니다. time lock을 걸어도 쿼리 결과 스냅샷을 저장하는 건 아니라는 점입니다. 즉 “그때의 화면”을 완전히 고정하진 못합니다.[^9]

그럼에도 Notebooks가 재현성에 유리한 이유는 다음이 합쳐지기 때문입니다.

- 쿼리 자체가 문서 안에 남고, 블록 단위로 편집 가능합니다.[^9]
- 특정 패널에 대해 notebook time range와 별개로 time lock을 걸 수 있고, 절대 시간(absolute start/end)을 쓰라고 문서가 가이드합니다. 조사 윈도우를 보존하려면 상대 시간(last 30m)이 아니라 절대 시간을 써야 한다는 이야기입니다.[^9]

운영에서는 “장애 당시”가 언제였는지가 가장 중요합니다. 상대 시간은 시간이 지나면 의미가 변하고, 절대 시간은 시간이 지나도 의미가 유지됩니다. 그래서 Notebook 기반 운영을 한다면, 장애/사고 조사 Notebook에는 절대 시간을 기본으로 강제하는 편이 낫습니다.

### export가 의미하는 것: Grafana 밖으로도 지식을 내보낼 수 있다
Notebooks는 공유 링크 복사, Markdown(raw/.md) export, PDF export를 지원합니다.[^9]

여기서 Markdown export의 동작이 운영적으로 중요합니다.

- Markdown으로 export하면 패널이 시각화가 아니라 JSON code block으로 떨어집니다.[^9]
- PDF export는 렌더된 시각화를 유지합니다.[^9]

즉, Markdown export는 “사람이 읽는 보고서”라기보다는 “구성/쿼리의 이식성”에 더 가깝습니다. 내 경우에는 다음 방식이 가장 깔끔했습니다.

- 사고 대응 중에는 Notebook을 사실상의 사건 타임라인/증거 모음으로 사용
- 종료 후에는 Markdown export를 Git 레포에 넣어 변경 이력과 함께 관리
- PDF는 외부 공유(비기술 이해관계자)용으로만 생성

다만 Notebook 링크를 공유한다고 해서 권한이 전달되지는 않습니다. 수신자는 Notebook과 데이터 소스에 대한 권한이 있어야 합니다.[^9] 권한 모델을 무시하고 “링크 던지기”로 운영하면, 결국 스크린샷 문화로 회귀합니다.

## UI refresh는 기능이 아니라 운영 비용이다
Grafana 13.3은 “Grafana’s biggest visual refresh since v7”을 public preview로 제공합니다.[^10] 그리고 이 UI refresh는 토글로 켜고 끌 수 있습니다. `grafana.visualDesignRefresh`를 enable하라고 명시합니다.[^3]

공식 설명에서 주목할 만한 포인트는 “visual refresh이지 redesign이 아니다”라는 선언입니다.

- 컴포넌트 API나 interaction pattern을 바꾸는 것이 아니라, 테마/색/타이포 중심의 1단계라고 말합니다.[^3]
- 플러그인도 표준 컴포넌트/토큰을 쓰면 자동으로 상속된다고 했고, hardcoding한 스타일은 플러그인 개발자 마이그레이션 타임라인이라고 선을 그었습니다.[^3]

운영자에게 중요한 건 “정말 기능이 안 바뀌는가”보다 “문서가 얼마나 빨리 낡는가”입니다.

- 교육 자료의 스크린샷, 내부 위키의 UI 가이드, 런북의 클릭 경로는 UI refresh로 빠르게 무효화됩니다.
- feature toggle로 점진 적용되면, 조직 내에서도 사람마다 다른 화면을 보게 됩니다(특히 Cloud의 롤링 채널/스택별 토글). 그 순간부터 문서에는 “어떤 토글이 켜진 상태 기준인지”가 들어가야 합니다.

그래서 UI refresh를 도입할 때는, UI를 설명하는 문서를 줄이고 “목표 상태를 검증하는 체크리스트”를 늘리는 쪽이 비용이 덜 듭니다. 예를 들면 “Dashboards > Variables 메뉴에서 글로벌 변수 목록이 보인다” 같은 결과 중심 문장으로 바꿔야 합니다.

## 13.3 시점의 deprecation이 주는 시그널: 업그레이드는 화면이 아니라 정책을 바꾼다
13.3을 업그레이드 가이드 소재로 보기 충분한 이유는, What’s next에 실제 운영 영향이 있는 공지가 같이 올라와 있기 때문입니다.

### Plugin Frontend Sandbox: 켜둔 조직은 13.4 전에 결정을 내려야 한다
What’s next는 Plugin Frontend Sandbox가 13.3에서 deprecate되고 13.4에서 제거될 것이라고 명시합니다. 기능은 public preview였고 GA로 진행하지 않기로 했다는 설명도 포함돼 있습니다.[^11]

운영 체크포인트는 간단합니다.

- 지금 Sandbox를 켜서 얻고 있는 보안 이득이 무엇인지
- 제거 이후 그 이득이 어디로 이동하는지(다른 보안 옵션, CSP, 플러그인 허용 정책 등)

이 항목은 관측성 팀 단독으로 결정하기 어렵고, 보안팀과 합의를 만들어야 합니다.

### x_xss_protection: 경고 로그 하나가 “설정 관리 체계”를 흔든다
`[security] x_xss_protection` 설정은 13.3.0에서 deprecate됐고, 켜져 있으면 startup 시 deprecation warning을 찍는다고 공지합니다. 기본값이 true라서, 명시적으로 설정하지 않아도 경고가 뜰 수 있다는 설명도 있습니다.[^12]

운영적으로 이게 성가신 이유는, 경고 로그가 다음 두 문화를 강제하기 때문입니다.

- “경고를 무시해도 되는가”를 문서화해야 합니다.
- 기본값에 의존하는 설정을 줄이고, 우리 조직이 의도한 보안 헤더 정책(CSP 포함)을 명시해야 합니다.

Grafana는 CSP를 권장하고 report-only로 먼저 테스트하라는 체크리스트까지 제공합니다.[^12] 이건 사실상 보안 런북 업데이트를 요구하는 공지입니다.

### 모바일 폰에서 dashboard edit mode 제거: 내일(2026-11-05)부터 Cloud에 반영
What’s next는 “Dashboard edit mode is going away on mobile phones”를 2026-10-28에 공지했고, Cloud rollout이 2026-11-05로 잡혀 있습니다. self-managed 타깃은 Grafana v13.4.0입니다.[^13]

사용자가 폰에서 대시보드를 편집하는 조직은 많지 않겠지만, 이 공지가 의미하는 바는 따로 있습니다.

- Grafana는 모바일을 “편집”보다 “빠르고 신뢰할 수 있는 조회”에 집중하겠다고 말합니다.[^13]
- 즉, 운영 교육/업무 흐름은 데스크톱(또는 태블릿) 중심으로 재정렬됩니다.

이는 Notebooks 같은 artifact가 들어오는 흐름과도 맞물립니다. 편집이 필요한 작업은 큰 화면에서, 조회는 어디서나. 역할이 나뉩니다.

## feature toggle 운영: 켰다/껐다가 아니라 ‘우리 조직의 제품’을 정의하는 단계
13.3의 핵심 기능들은 공통적으로 public preview + feature toggle 조합입니다. cross-dashboard variables는 `grafana.dashboardGlobalVariables`, Notebooks는 `dashboard.notebooks`, UI refresh는 `grafana.visualDesignRefresh`로 안내됩니다.[^6]

여기서 중요한 디테일은 Grafana의 설정 방식 변화입니다.

- `[feature_toggles] enable` 옵션은 deprecated이며, “개별 토글 엔트리를 써라”고 문서가 명시합니다.[^14]
- 즉, 운영은 이제 “enable = a b c” 같은 뭉뚱그린 방식보다, 어떤 토글을 왜 켰는지까지 관리해야 합니다.

내 경우 토글은 다음 3단계로 운영하는 편이 비용이 덜 들었습니다.

1) dev 스택: 실험 토글을 마음껏 켜되, 켠 이유를 남김
2) stage 스택: prod와 동일 토글만 유지. 여기서 교육 자료를 갱신
3) prod 스택: 토글 변경은 릴리스 노트 기반 변경관리(티켓/승인)로만 진행

토글 기반 기능은 “UI에서 보이니까 써보자”로 시작하면 나중에 되돌리기 어렵습니다. 특히 cross-dashboard variables는 중앙집중이라 되돌릴 때 영향 범위가 넓습니다.

## (실습) cross-dashboard variables + Notebooks를 ‘운영 자산’으로 만들기
아래는 self-managed Grafana 13.3.0에서 토글을 켜고, 공유 변수를 만든 뒤, 조사 Notebook을 남기는 흐름을 한 번에 재현하는 구성을 정리한 것입니다. 기능의 UI 조작 자체는 공식 문서를 따르는 게 가장 안전합니다.

- cross-dashboard variables는 public preview이며 토글이 필요합니다.[^6]
- Notebooks도 public preview이며 토글이 필요합니다.[^9]

### docker-compose로 최소 환경 띄우기 (Grafana 13.3.0 + Prometheus + 샘플 앱)
Grafana 13.3.0은 공식 다운로드 페이지에서 Docker 실행 예시도 제공합니다.[^15] 여기서는 compose로 Prometheus까지 묶습니다.

`docker-compose.yaml`
```yaml
services:
  grafana:
    image: grafana/grafana:13.3.0
    ports:
      - "3000:3000"
    volumes:
      - ./grafana/grafana.ini:/etc/grafana/grafana.ini:ro
      - grafana-data:/var/lib/grafana

  prometheus:
    image: prom/prometheus:v2.55.1
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro

  app:
    build: ./app
    ports:
      - "8000:8000"

volumes:
  grafana-data: {}
```

`grafana/grafana.ini`
```ini
[server]
http_port = 3000

[security]
admin_user = admin
admin_password = admin

[feature_toggles]
# enable 옵션은 deprecated이므로 개별 토글로 관리합니다.[^14]
grafana.dashboardGlobalVariables = true
dashboard.notebooks = true
# UI refresh는 public preview이며, 필요 시 켜고 문제가 있으면 끄는 방식으로 롤아웃합니다.[^3]
grafana.visualDesignRefresh = true
```

`prometheus/prometheus.yml`
```yaml
global:
  scrape_interval: 5s

scrape_configs:
  - job_name: app
    static_configs:
      - targets: ["app:8000"]
```

`app/Dockerfile`
```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir prometheus-client
COPY app.py /app/app.py
CMD ["python", "/app/app.py"]
```

`app/app.py`
```python
from http.server import BaseHTTPRequestHandler, HTTPServer
from prometheus_client import CollectorRegistry, Counter, generate_latest
import os

registry = CollectorRegistry()

# env/cluster/service 라벨은 cross-dashboard variables로 표준화하기 좋은 축입니다.
requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["env", "cluster", "service"],
    registry=registry,
)

ENV = os.getenv("ENV", "prod")
CLUSTER = os.getenv("CLUSTER", "alpha")
SERVICE = os.getenv("SERVICE", "checkout")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            # 간단한 트래픽을 만들어서 패널이 움직이도록 합니다.
            requests_total.labels(env=ENV, cluster=CLUSTER, service=SERVICE).inc(3)
            data = generate_latest(registry)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_response(404)
        self.end_headers()

HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
```

실행:
```bash
docker compose up -d --build
```

Prometheus가 metrics를 받는지 확인:
```bash
curl -s "http://localhost:9090/api/v1/query?query=http_requests_total" | head
```

### Grafana에 Prometheus 데이터 소스 연결
이 부분은 Grafana UI로 설정하는 게 가장 빠릅니다.

- URL: `http://prometheus:9090`

이 단계가 끝나면, 대시보드/Explore에서 PromQL이 동작합니다.

### cross-dashboard variables 만들기: Dashboards > Variables
공식 문서는 cross-dashboard variables를 Dashboards > Variables에서 생성/관리하라고 안내합니다.[^6]

추천 규칙(운영 관점):

- 글로벌 변수(조직 표준)
  - env: prod, staging
  - region: us-east-1, us-west-2
- 폴더 변수(팀 표준)
  - cluster: alpha, beta
  - service: checkout, payments

변수 정의에 Description을 적극적으로 써야 합니다. cross-dashboard variables 문서는 Description에 링크를 넣을 수 있고 http/https만 clickable하다고 명시합니다.[^6]

내 경우 Description에는 최소한 아래를 넣었습니다.

- 변수의 의미(무엇을 고르는가)
- 값의 소스(예: Prometheus label)
- 값 추가/변경 프로세스(누가 PR/승인하는가)

### (선택) Terraform로 변수/대시보드 리소스를 ‘리소스 스토어’로 다루기
여기부터는 공식 문서라기보다 “운영자가 반복 작업을 줄이기 위해” 가는 영역입니다.

Grafana Terraform provider에는 Kubernetes 스타일 manifest를 그대로 관리하는 `grafana_apps_generic_resource`가 있고, App Platform resource를 typed 리소스가 없을 때 쓸 수 있다고 설명합니다.[^16]

이 리소스를 쓰면 Folder 같은 리소스도 manifest로 관리 가능합니다(문서 예시에 folder.grafana.app/v1 kind Folder가 등장).[^16]

다만 cross-dashboard variables의 App Platform 스키마/버전은 public preview 단계라 문서화가 덜 돼 있습니다. 커뮤니티 포럼에서 Grafana 측 답변으로 Variable kind와 Dashboard annotation 방식이 공유돼 있는데, 이 부분은 향후 변경 가능성이 높다고 보고 적용 범위를 제한하는 편이 낫습니다.[^17]

예시(커뮤니티 답변 기반, 변경 가능):

- Variable 리소스: `apiVersion = "dashboard.grafana.app/v2beta1"`, `kind = "Variable"`[^17]
- Dashboard에서 cross-dashboard variables를 쓰려면 `metadata.annotations.grafana.app/useCrossDashboardVariables`를 JSON string으로 지정[^17]

이 방식을 쓰면 “변수 정의를 Git/Terraform에서 통제”하고, “대시보드는 UI에서 선택적으로 attach”하는 혼합 모델이 가능합니다. cross-dashboard variables를 전면 as-code로 밀기보다, 변수 표준만 코드로 고정하는 쪽이 blast radius가 작습니다.

### Notebooks를 런북으로 굳히는 운영 규칙
Notebooks는 문서상으로 다음 특징이 있습니다.

- Viewers는 읽을 수 있고, Editors/Admins는 생성/편집/삭제 가능[^9]
- 공유 링크는 권한을 부여하지 않음[^9]
- Markdown export 시 패널은 JSON code block으로 떨어짐[^9]

이를 운영 규칙으로 번역하면 이렇게 됩니다.

- 사고 조사 Notebook에는 반드시 태그를 넣고(서비스/도메인/incident-id), 검색 가능한 제목 규칙을 강제
- time lock은 절대 시간을 기본으로 사용[^9]
- Notebook 링크를 Pager/Slack에 던질 때는 “누가 볼 수 있는지”를 함께 고지(권한 모델을 무시하지 않기)

대시보드는 계속 필요합니다. 다만 조사 결과를 대시보드에 더 덕지덕지 얹기보다, Notebook을 결과물로 남기고 대시보드는 관측 지도로 유지하는 편이 유지보수성이 좋아집니다.

## 업그레이드 판단: 13.3을 ‘바로’ 올릴지, ‘운영 모델부터’ 바꿀지
13.3의 핵심 기능이 public preview + feature toggle이라는 점을 감안하면, 업그레이드는 두 층으로 나뉩니다.

1) 바이너리 업그레이드(13.3.0으로 올리기)
- 공식 업그레이드 가이드는 v13.3 페이지로 제공됩니다.[^18]

2) 운영 모델 업그레이드(토글을 켜고 자산 단위를 옮기기)
- 토글을 켜는 순간, 사용자 교육/문서/런북이 같이 움직여야 합니다.

내 결론은 이렇습니다.

- 13.3을 설치하는 것 자체는 큰 이슈가 아닐 수 있지만, cross-dashboard variables와 Notebooks를 켜는 순간부터는 “대시보드 운영”이 아니라 “질문/조사 운영”으로 넘어갑니다.
- 그 전환에서 가장 먼저 해야 할 일은 대시보드 리팩토링이 아니라 변수 표준 사전과 변경관리 규칙을 만드는 일입니다.
- Notebook은 사고 대응 품질을 올리지만, 권한/시간 고정/내보내기(마크다운/PDF)까지 포함한 런북화 규칙이 없으면 다시 산만해집니다.

이 버전은 기능 목록보다 운영 철학을 바꾸는 쪽이 ROI가 큰 업그레이드입니다.

## 참고 자료
- [Grafana 13.3.0 다운로드 페이지](https://grafana.com/grafana/download/13.3.0?edition=oss)
- [Grafana 13.3 공식 발표 블로그](https://grafana.com/blog/grafana-13-3-release-all-the-latest-features/)
- [What’s new in Grafana v13.3](https://grafana.com/docs/grafana/latest/whatsnew/whats-new-in-v13/whats-new-in-v13-3/)
- [Cross-dashboard variables 문서](https://grafana.com/docs/grafana/latest/visualizations/dashboards/variables/cross-dashboard-variables/)
- [Variables 개요 문서](https://grafana.com/docs/grafana/latest/visualizations/dashboards/variables/)
- [Notebooks 문서](https://grafana.com/docs/grafana/latest/visualizations/notebooks/)
- [Grafana visual UI refresh 공지](https://grafana.com/whats-new/2026-10-26-grafana-visual-ui-refresh/)
- [What’s next: Plugin Frontend Sandbox deprecation](https://grafana.com/whats-next/2026-10-27-the-plugin-frontend-sandbox-is-now-deprecated-and-will-be-removed-in-grafana-v134/)
- [What’s next: x_xss_protection deprecation](https://grafana.com/whats-next/2026-09-29-deprecation-notice-for-the--x_xss_protection--configuration-option/)
- [What’s next: 모바일 폰에서 대시보드 편집 모드 제거](https://grafana.com/whats-next/2026-11-05-dashboard-edit-mode-is-going-away-on-mobile-phones/)
- [Configure feature toggles](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/feature-toggles/)
- [Grafana 설정 파일의 feature_toggles 섹션](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/)
- [Terraform Registry: grafana_apps_generic_resource](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/apps_generic_resource)
- [Grafana HTTP API: legacy /api deprecation](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/)
- [Dashboard API(/apis/dashboard.grafana.app) 문서](https://grafana.com/docs/grafana-cloud/learn-and-build/developer-resources/api-reference/http-api/dashboard/)

[^1]: <https://grafana.com/grafana/download/13.3.0?edition=oss>
[^2]: <https://grafana.com/blog/grafana-13-3-release-all-the-latest-features/>
[^3]: <https://grafana.com/whats-new/2026-10-26-grafana-visual-ui-refresh/?pg=grafana-13-3-release-all-the-latest-features&plcmt=in-text>
[^4]: <https://grafana.com/whats-next/>
[^5]: <https://grafana.com/docs/grafana/latest/visualizations/dashboards/variables/>
[^6]: <https://grafana.com/docs/grafana/latest/visualizations/dashboards/variables/cross-dashboard-variables/?pg=grafana-13-3-release-all-the-latest-features&plcmt=in-text>
[^7]: <https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/create-dashboard-url-variables/>
[^8]: <https://grafana.com/docs/grafana/latest/visualizations/dashboards/variables/add-template-variables/>
[^9]: <https://grafana.com/docs/grafana/latest/visualizations/notebooks/>
[^10]: <https://grafana.com/docs/grafana/latest/whatsnew/whats-new-in-v13/whats-new-in-v13-3/>
[^11]: <https://grafana.com/whats-next/2026-10-27-the-plugin-frontend-sandbox-is-now-deprecated-and-will-be-removed-in-grafana-v134/>
[^12]: <https://grafana.com/whats-next/2026-09-29-deprecation-notice-for-the--x_xss_protection--configuration-option/>
[^13]: <https://grafana.com/whats-next/2026-11-05-dashboard-edit-mode-is-going-away-on-mobile-phones/>
[^14]: <https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/?pg=new-in-grafana-8-5-updated-panels-new-rbac-features-simplified-reporting-and-more&plcmt=in-text>
[^15]: <https://grafana.com/grafana/download/13.3.0?edition=oss&platform=docker>
[^16]: <https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/apps_generic_resource>
[^17]: <https://community.grafana.com/t/testing-globaldashboardvariables/164300>
[^18]: <https://grafana.com/docs/grafana/latest/upgrade-guide/upgrade-v13/upgrade-v13.3/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
