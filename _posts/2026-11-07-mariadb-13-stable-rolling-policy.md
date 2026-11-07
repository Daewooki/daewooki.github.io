---
title: "MariaDB 13 Stable rolling release 채택 가이드: LTS와 롤링을 운영 정책으로 나누기"
description: "MariaDB 13.0 Stable rolling을 LTS와 함께 굴리기 위한 트랙 분리, 무중단 업그레이드, DuckDB 엔진 검증 프레임을 정리합니다."
date: 2026-11-07 11:29:14 +0900
categories: ["Database", "MariaDB"]
tags: ["mariadb", "rolling-release", "lts", "upgrade-policy", "duckdb"]
render_with_liquid: false
---

## Stable rolling release라는 말을 운영 관점에서 다시 쪼개기

2026-09-17에 MariaDB Foundation이 공개한 [MariaDB 13.0 Is Now Stable](https://mariadb.org/mariadb-13-0-is-now-stable/)는 제목부터 운영팀을 헷갈리게 만듭니다. Stable과 rolling은 같은 축의 단어가 아닙니다. 글에서도 Stable은 “개발 사이클을 통과해 일반 사용에 적합하다고 보는 성숙도”이고, rolling은 “업데이트 경로(다음 분기 minor로 계속 올라가야 하는 트랙)”라고 분리해서 설명합니다.[^1]

여기서 Stable은 안전하다는 보증이 아니라, 최소한 GA까지 올라오는 동안의 검증 포커스가 기능 추가에서 회귀/상호작용/업그레이드 경로/패키징 이슈로 이동했다는 신호입니다. MariaDB 13.0은 RC에서 Stable로 가는 구간에만 604 commits, 1,701 files changed, 23,748 test lines added, 335 MDEV 처리라는 숫자를 같이 제시했습니다. 이런 숫자는 마케팅 지표라기보다 “RC를 운영에 넣을 생각이면 최소 이 정도의 체인지 레이트를 감당하는 체계를 갖춰라”는 경고로 읽는 편이 맞습니다.[^1]

반대로 rolling은 배포 안정성(stability)과 별개로, 유지보수 창(maintenance window)이 짧다는 뜻입니다. MariaDB Foundation의 [About MariaDB Server](https://mariadb.org/about/)에는 rolling releases가 분기 단위로 발표되며, 13.0의 Community EOL이 Q4 2026, 13.1은 Q1 2027로 적혀 있습니다. 즉 13.0을 GA로 올렸다가도 몇 달 내에 “다음 minor로 가라”가 됩니다.[^2]

따라서 **Stable rolling**을 “안정적인 최신 버전”으로 오해하면 운영 정책이 틀어집니다. 이 조합은 “GA 성숙도는 갖췄지만, 유지보수는 짧고 업그레이드 빈도는 높은 트랙”입니다.[^1]

## MariaDB release model을 버전 번호로 읽는 법

MariaDB Community Server의 현재 release model은 문서로 고정되어 있습니다. [Release Model](https://mariadb.com/docs/release-notes/community-server/about/release-model) 요지는 다음입니다.

- 커뮤니티 릴리스는 연 4회(분기)입니다.
- 매 분기 “innovation release”가 RC로 나오고, 직전 RC가 GA(Stable)가 됩니다.
- rolling(innovation) 릴리스는 GA 이후에 정기적인 patch maintenance가 나오지 않습니다(긴급 상황 제외). 사용자는 다음 minor innovation으로 업그레이드해야 합니다.
- 약 4번째 innovation마다 LTS가 나오며, LTS는 GA 이후 3년 유지보수(Community 기준)입니다.[^3]

이 모델을 13.0에 대입하면, 13.0.0 Preview(2026-03-23) → 13.0.1 RC(2026-05-29) → 13.0.2 Stable(2026-09-15)라는 흐름이 “정상 루트”였다는 뜻입니다. 이 날짜는 MariaDB의 [All releases](https://mariadb.org/mariadb/all-releases/)에 그대로 나옵니다.[^4]

그리고 13.0.2가 Stable(GA)라는 사실은 MariaDB 문서 저장소의 13.0.2 릴리스 노트에도 “released on 2026-09-15”로 명시되어 있습니다.[^5]

여기서 운영 정책 설계에 중요한 디테일은 따로 있습니다.

- rolling 트랙에서는 “13.0.x에서 x만 올리면서 몇 년 버틴다”는 전략이 구조적으로 성립하지 않습니다.
- 반대로 LTS 트랙에서는 “같은 series에서 patch만 올린다”가 가능합니다(예: 12.3.2 → 12.3.3).[^4]

MariaDB 쪽에서 rolling의 특성을 더 노골적으로 말한 문서가 13.0 GA 발표글입니다. [Announcing MariaDB Community Server 13.0 GA](https://mariadb.com/resources/blog/announcing-mariadb-community-server-13-0-ga/)에 “rolling release cycle의 일부로서 13.0 GA는 rolling release이며, further bug-fix releases를 받지 않는다”가 박혀 있습니다.[^6]

이 한 줄이, 운영 관점에서 rolling 채택의 비용 구조를 결정합니다.

- LTS: 계획된 patch 업데이트를 통해 동일 메이저/마이너에서 안정화 이득을 누립니다.
- rolling: 안정화는 “다음 분기 minor로 이동하는 것”으로 해결하라는 모델입니다.

## LTS vs rolling을 ‘환경’이 아니라 ‘정책’으로 분리하기

많은 팀이 LTS는 production, rolling은 dev/test라고 단순 분리합니다. 문제는 production이 하나의 성격이 아니라는 점입니다. 같은 production 안에서도 “돈을 버는 OLTP”와 “운영 리포팅/분석”은 실패 비용과 변경 허용치가 다릅니다.

그래서 나는 LTS/rolling을 환경이 아니라 정책으로 나눕니다. 핵심은 트랙(track)과 링(ring)을 분리하는 것입니다. 예전에 브라우저 업데이트를 링으로 쪼개 운영했던 글[^7]과 논리는 비슷하지만, DB는 롤백이 훨씬 어려우니 더 보수적으로 설계해야 합니다.

### 트랙 정의: “무엇을 최적화하나”

- LTS 트랙: 변경량을 줄이고, 운영 시간 대부분을 “예측 가능성”에 투자합니다.
- rolling 트랙: 기능/성능/엔진 확장을 빠르게 흡수하되, 업그레이드 자체를 상시 업무로 내재화합니다.

MariaDB Foundation이 말하는 rolling의 목표도 “다음 LTS를 기다리지 않고 evolution을 따라가려는 사용자”입니다.[^1]

### 링 정의: “어디까지 자동으로 밀어붙이나”

내 경우 링은 보통 3개가 현실적입니다.

1) canary (소량 트래픽/내부 서비스)
2) mainline (대부분의 production)
3) holdback (장기 고정 또는 규제/감사 대상)

중요한 건 LTS/rolling과 링을 직교시키는 겁니다.

- canary는 rolling을 태울 수 있습니다.
- mainline은 LTS를 기본으로 두되, 특정 기능이 필요하면 rolling을 제한적으로 태웁니다.
- holdback은 LTS 중에서도 “가장 보수적인 것”만 둡니다.

MariaDB 13.0 Stable 공지 자체가 “이건 LTS가 아니고, 새 기능이 필요할 때 업그레이드가 relevant하다”라고 못 박습니다.[^1]

이 문장을 운영 정책 언어로 번역하면 다음입니다.

- rolling은 “전사 표준”이 아니라 “요건 기반 예외”가 기본값입니다.
- 단, 요건이 자주 발생하는 조직이라면 예외가 표준이 되므로(예: 분기별 성능/옵티마이저/관측 기능을 따라가야 하는 SaaS), 그때는 rolling을 하나의 상시 트랙으로 격상시키는 편이 더 싸게 먹힙니다.

## Rolling 트랙을 production에 넣을 수 있는 조건

rolling 트랙을 “운영에 넣는다”는 말은 사실 “업그레이드를 운영의 일부로 만든다”는 말입니다. MariaDB가 분기 릴리스 구조를 공개했기 때문에, 업그레이드가 연 1회 이벤트가 아니라 연 4회 루틴이 됩니다.[^3]

그 루틴을 감당하려면 조건이 필요합니다.

### 1) 업그레이드 리드타임을 SLO로 만든다

rolling을 태우는 팀에서 가장 흔한 실패는 “업그레이드 큐가 밀려서” 어느 순간 한 번에 2~3개 minor를 뛰게 되는 상황입니다. 그 순간부터는 rolling의 장점이 아니라 단점만 남습니다.

- 변경량은 누적되고
- 검증 난이도는 제곱으로 오르며
- 사고가 나면 원인 버전이 불명확해집니다.

그래서 업그레이드를 SLO로 둡니다.

- 예: GA 공개일 기준 30일 내 canary 반영
- 60일 내 mainline 반영 여부 결정
- 90일 내 미반영이면 “왜 못했는지”가 장애에 준하는 이슈가 됩니다.

이건 런타임 정책을 연 단위로 맞춰 “업그레이드가 쌓이지 않게” 만들었던 경험[^8]과 같은 결의 작업입니다.

### 2) 테스트는 기능 테스트가 아니라 회귀 탐지여야 한다

DB 업그레이드에서 운영을 터뜨리는 건 신기능이 아니라, 기존 쿼리의 plan 변화/락 행태/메모리 사용/일시적 latency 스파이크 같은 회귀입니다.

MariaDB 13.0의 기능 목록(예: `UPDATE ... RETURNING`, `QB_NAME()`, `innodb_log_archive`) 자체는 흥미롭지만, 운영팀이 봐야 하는 건 “내 워크로드가 이 버전에서 더 흔들리는가”입니다.[^9]

그래서 rolling 트랙에서는 테스트 범위를 이렇게 잡는 편이 맞습니다.

- API 레벨 기능 테스트: 최소화
- 주요 쿼리 셋(상위 N개, p95 latency 영향 큰 것) 리플레이: 필수
- replication 지연, purge lag, buffer pool hit ratio, temp table 증가 같은 운영 지표 비교: 필수

### 3) 패키지/이미지/클라우드의 ‘버전 진실’을 하나로 정한다

MariaDB 13.0.2를 실제로 굴리면 “서버 버전”이라는 단어가 여러 층에서 다르게 쓰입니다.

- MariaDB Foundation의 릴리스 날짜는 2026-09-15입니다.[^4]
- GitHub releases에도 13.0.2 릴리스가 2026-09-15로 기록됩니다.[^10]
- Docker Official Image에도 `mariadb:13.0.2-ubi10` 같은 태그가 존재합니다.[^11]

이 레이어가 조금만 어긋나도 장애 대응이 꼬입니다. 패키지 기반 버전 진실을 맞추는 작업이 왜 운영 리스크를 줄이는지에 대해서는 예전에 NGINX 사례로 적어둔 게 있고[^12], DB도 동일합니다.

rolling 트랙에서는 “어떤 소스가 진짜냐”를 운영 정책으로 고정해야 합니다.

- 기본: `SELECT VERSION()`
- 보조: 패키지 매니저 버전(apt/yum), 컨테이너 태그, Git commit
- 사고 시: 실행 바이너리와 빌드 플래그 확인

## 다운타임 최소화 업그레이드: ‘업그레이드 절차’가 아니라 ‘토폴로지’를 바꾸는 일

rolling 트랙을 진짜로 운영하려면, 업그레이드는 단일 노드에서 `apt upgrade` 하는 이벤트가 아니라 토폴로지를 이용한 스위치오버 작업이 됩니다.

MariaDB 공식 업그레이드 가이드는 “primary-replica 구성이면 replica부터 업그레이드하고, 검증 후 나머지를 올린 다음, replica를 primary로 승격하고 기존 primary를 업그레이드하라”를 권장합니다.[^13]

이 권고가 의미 있는 이유는 문서에 같이 적혀 있습니다.

- replica는 primary보다 어떤 newer version이어도 될 수 있다.[^13]

즉 “새 버전이 구버전의 binlog를 받아먹는 방향”을 이용해 무중단 경로를 만들라는 얘기입니다.

### rolling에서 롤백이 왜 어려운가

DB 업그레이드에서 롤백이 어려운 이유는 두 가지입니다.

1) 데이터 포맷/시스템 테이블 변경
2) binlog/replication 이벤트 호환성

MariaDB 문서에도 다운그레이드는 별도 가이드로 존재하고, 특정 버전/특정 변경에서는 downgrade가 불가능할 수 있음을 전제합니다.[^14]

그래서 운영 정책에서 “롤백”을 이렇게 재정의하는 편이 맞습니다.

- 같은 노드를 이전 바이너리로 되돌리는 rollback: 기대하지 않는다.
- 구버전 primary를 일정 시간 보존해 “트래픽을 되돌리는 rollback”만 가능하게 만든다.

이 차이를 정책 문서에 써 두지 않으면, 사고 때 의사결정이 늦어집니다.

### `innodb_log_archive` 같은 기능은 백업/복구 정책을 같이 흔든다

MariaDB 13.0.2 릴리스 노트에는 `innodb_log_archive`가 “InnoDB redo log를 연속 파일로 보존해 PITR/증분 백업에 도움”이 된다고 쓰면서, 동시에 `mariadb-backup`이 아직 이 포맷을 지원하지 않아 `innodb_log_archive=ON`이면 실패한다고 명시합니다.[^9]

운영팀 입장에서 이 문장은 기능 소개가 아니라 업그레이드 게이트입니다.

- 13.0을 올리는 순간 `innodb_log_archive`를 켜고 싶어질 수 있는데
- 켜는 순간 기존 백업 파이프라인이 깨질 수 있습니다.

rolling 트랙에서는 이런 “운영 계약 변경”을 기능 단위로 체크리스트화해야 합니다.

## (실행 가능한) 11.8 → 13.0.2 무중단에 가까운 업그레이드 리허설

아래 리허설은 핵심만 남긴 구성입니다.

- `db1`: MariaDB 11.8.9 (구버전 primary)
- `db2`: MariaDB 13.0.2 (신버전 replica)
- 스위치오버는 애플리케이션이 아니라 단순히 “쓰기 대상을 어디로 보느냐”로 시뮬레이션합니다.

공식 문서가 말하는 전제(“replica는 primary보다 newer version 가능”)를 그대로 확인하는 목적입니다.[^13]

### docker-compose.yml

```yaml
services:
  db1:
    image: mariadb:11.8.9-ubi
    container_name: db1_118
    environment:
      MARIADB_ROOT_PASSWORD: rootpass
      MARIADB_DATABASE: app
    command:
      - --server-id=118
      - --log-bin=mysql-bin
      - --binlog-format=ROW
      - --gtid-strict-mode=ON
      - --enforce-gtid-consistency=ON
      - --log-slave-updates=ON
      - --skip-name-resolve=ON
    ports:
      - "33118:3306"

  db2:
    image: mariadb:13.0.2-ubi
    container_name: db2_130
    environment:
      MARIADB_ROOT_PASSWORD: rootpass
    command:
      - --server-id=130
      - --read-only=ON
      - --log-bin=mysql-bin
      - --binlog-format=ROW
      - --gtid-strict-mode=ON
      - --enforce-gtid-consistency=ON
      - --log-slave-updates=ON
      - --skip-name-resolve=ON
    ports:
      - "33130:3306"

networks:
  default:
    name: mariadb_upgrade_lab
```

이 예시는 UBI 기반 공식 이미지 태그를 썼습니다. Docker Official Image에서 13.0.2 태그가 존재함은 tags 목록에서 확인할 수 있습니다.[^11]

### 1) 기동 및 버전 확인

```bash
docker compose up -d

docker exec -it db1_118 mariadb -uroot -prootpass -e "SELECT VERSION();"
docker exec -it db2_130 mariadb -uroot -prootpass -e "SELECT VERSION();"
```

예상 출력은 대략 아래처럼 나옵니다(정확한 build suffix는 이미지에 따라 달라질 수 있습니다).

- db1: `11.8.9-MariaDB ...`
- db2: `13.0.2-MariaDB ...`

### 2) replication 계정 생성(db1)

```bash
docker exec -it db1_118 mariadb -uroot -prootpass <<'SQL'
CREATE USER IF NOT EXISTS 'repl'@'%' IDENTIFIED BY 'replpass';
GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%';
FLUSH PRIVILEGES;
SQL
```

### 3) db2를 db1의 replica로 붙이기

MariaDB replication에서 GTID 기반으로 붙일 때 흔히 쓰는 방식 중 하나가 `MASTER_USE_GTID=slave_pos`입니다.

```bash
docker exec -it db2_130 mariadb -uroot -prootpass <<'SQL'
STOP SLAVE;
RESET SLAVE ALL;

CHANGE MASTER TO
  MASTER_HOST='db1_118',
  MASTER_PORT=3306,
  MASTER_USER='repl',
  MASTER_PASSWORD='replpass',
  MASTER_USE_GTID=slave_pos;

START SLAVE;
SQL
```

상태 확인:

```bash
docker exec -it db2_130 mariadb -uroot -prootpass -e "SHOW SLAVE STATUS\G" | egrep "Slave_IO_Running|Slave_SQL_Running|Using_Gtid|Seconds_Behind_Master"
```

정상이라면 대략 아래가 나옵니다.

- `Slave_IO_Running: Yes`
- `Slave_SQL_Running: Yes`
- `Using_Gtid: Slave_Pos`

여기까지가 “newer replica가 older primary를 따라간다”는 전제를 실물로 확인하는 단계입니다. 이 전제가 공식 업그레이드 가이드에 명시되어 있고, 이 전제가 성립해야 무중단 스위치오버가 가능합니다.[^13]

### 4) 샘플 쓰기 트래픽을 db1에 발생시키고 db2에서 읽기

```bash
docker exec -it db1_118 mariadb -uroot -prootpass app <<'SQL'
CREATE TABLE IF NOT EXISTS orders (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  amount DECIMAL(10,2) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_user_created (user_id, created_at)
) ENGINE=InnoDB;

INSERT INTO orders(user_id, amount) VALUES (101, 19.99), (101, 3.50), (202, 120.00);
SQL

# replica에서 확인
sleep 1

docker exec -it db2_130 mariadb -uroot -prootpass app -e "SELECT user_id, SUM(amount) sum_amount FROM orders GROUP BY user_id ORDER BY user_id;"
```

이 리허설은 단순하지만, 운영 정책에서 중요한 결론을 줍니다.

- rolling 도입의 전제는 “스위치오버 가능한 토폴로지”입니다.
- 즉, 단일 노드 DB(복제 없음)에서 rolling은 곧 다운타임/리스크로 직결됩니다.

### 5) 스위치오버(쓰기 대상 변경) 시뮬레이션

db2를 primary처럼 만들려면 최소한 read-only를 풀고, replication을 끊는 단계를 밟습니다.

```bash
docker exec -it db2_130 mariadb -uroot -prootpass <<'SQL'
STOP SLAVE;
SET GLOBAL read_only=OFF;
SQL
```

이후부터 “쓰기 대상”을 db2로 바꾸면 됩니다(실서비스에서는 ProxySQL/HAProxy, 혹은 애플리케이션 connection string 레벨에서 처리합니다).

여기서 중요한 운영 포인트는 “스위치오버 직전까지 구 primary(db1)를 살려두면, 일정 시간 동안은 되돌릴 수 있다”는 점입니다. 이게 현실적인 rollback입니다.

## 신규 기능 검증 프레임: DuckDB engine을 ‘기능’이 아니라 ‘운영 계약’으로 본다

MariaDB 13.0 Stable 공지에서 눈에 띄는 건 DuckDB storage engine입니다. 공지는 DuckDB storage engine을 “gamma”라고 표현하면서도(즉 완전히 production-safe로 말하지는 않으면서도), 13.0.2 시점에 패키지(`MariaDB-duckdb-engine`)로 제공되는 예시(dnf info)를 같이 보여줍니다.[^1]

그리고 MariaDB Foundation은 별도 프로젝트 페이지인 [MariaDB DuckDB — native columnar analytics inside MariaDB](https://mariadb.org/projects/mariadb-duckdb/)에서 이 엔진이 무엇인지, 어떻게 동작하는지, 어떤 범위의 pushdown이 일어나는지를 꽤 구체적으로 문서화했습니다. 핵심만 뽑으면 다음입니다.

- `ENGINE=DuckDB` 테이블을 만들 수 있습니다.
- DuckDB의 columnar/vectorized 실행이 MariaDB 안으로 들어옵니다.
- `SELECT` 전체가 DuckDB로 pushdown될 수 있습니다.
- InnoDB와 DuckDB 테이블을 한 쿼리에서 join하는 cross-engine join이 가능합니다.
- 내부적으로는 pluggable storage engine(ha_duckdb) 형태입니다.
- 11.4, 11.8, 12.3, 13.x 브랜치에서 available하다고 적혀 있습니다.[^15]

여기서 운영 정책 설계의 포인트는 “DuckDB를 쓸지 말지”가 아닙니다. rolling 트랙이 유효해지는 대표적 이유가 바로 이런 엔진/실행기 추가이기 때문입니다.

### DuckDB 검증을 위한 5가지 질문

1) 데이터 내구성: 이 엔진 테이블의 파일/redo/undo/크래시 리커버리 특성은 InnoDB와 동등한가?
2) 백업/복구: 기존 백업 도구(mariadb-backup, logical dump)가 엔진 테이블을 어떻게 다루나?
3) replication: row-based binlog에서 이 엔진의 DML이 안전하게 재현되나?
4) 리소스 격리: OLTP(InnoDB)와 OLAP(DuckDB)가 같은 mysqld 프로세스에서 CPU/memory를 어떻게 경쟁하나?
5) 장애 모드: DuckDB 엔진이 죽었을 때 서버 전체가 죽나, 기능 일부만 죽나?

이 질문들은 기능 소개로는 답이 안 나옵니다. staging에서 “운영 계약” 테스트를 해야 답이 나옵니다.

### 검증 프레임을 ‘단계’로 쪼개기

- Phase 0: 존재 확인
  - `SHOW ENGINES;`에서 DuckDB가 보이는지
  - `CREATE TABLE ... ENGINE=DuckDB`가 되는지
- Phase 1: 읽기 전용 분석 워크로드로만 사용
  - ETL 없이 빠른 리포팅이 목적이라면, 먼저 append-only 형태(예: 일자별 집계 테이블)부터 시작하는 게 안전합니다.
- Phase 2: cross-engine join을 제한적으로 허용
  - 프로젝트 페이지에 cross-engine join의 내부 동작(select_handler pushdown, 외부 테이블 스캔을 fiber로 처리 등)이 설명돼 있는데, 이건 성능/락/동시성에서 함정이 생기기 쉬운 지점입니다.[^15]
- Phase 3: SLA가 있는 production 경로에 넣기
  - 이 단계는 rolling 트랙에서만 의미가 있습니다. LTS-only 팀이면 Phase 2에서 멈추는 게 보통 더 낫습니다.

## 13.0 rolling 도입 여부를 가르는 기준: ‘새 기능 가치’가 업그레이드 비용을 이기나

MariaDB 13.0.2 릴리스 노트의 신기능 중 운영 정책과 직접 연결되는 건 크게 세 가지 축입니다.

1) 운영 가시성/관리성
- `INFORMATION_SCHEMA.SYSTEM_VARIABLES`에 deprecation status 컬럼 추가(`IS_DEPRECATED`, `DEPRECATED_REPLACEMENT`)가 들어갔습니다.[^9]

이건 단순히 편한 기능이 아니라, rolling 트랙의 필수 도구가 됩니다. rolling은 “다음 minor로 계속 갈 것”이 전제라서, config debt(곧 사라질 변수/옵션)를 빨리 청산해야 합니다.

2) 업그레이드/복구 전략에 영향을 주는 기능
- `innodb_log_archive`는 PITR/증분 백업 가능성을 열어주지만, 동시에 도구 미지원(`mariadb-backup` 실패)을 동반합니다.[^9]

3) 워크로드 성격을 바꾸는 엔진 확장
- DuckDB engine은 “같은 서버에서 HTAP 실험”을 가능하게 만들지만, 운영 계약이 달라집니다.[^15]

그래서 판단 기준은 단순합니다.

- 13.0에서만 얻을 수 있는 가치가 지금 있는가?
- 그 가치가 분기 업그레이드 루틴을 만들 만큼 큰가?

MariaDB 13.0 Stable 공지도 업그레이드 이유를 기능 기반으로 제한해서 말합니다. “이건 LTS가 아니고, 새 기능을 쓰려는 시나리오에서만 relevant하다”고 했습니다.[^1]

## 2026년 10~11월 업그레이드 큐 정리에서의 현실적인 선택지

MariaDB는 “매년 LTS가 나온다”는 큰 로드맵을 이미 블로그로 공개했습니다. 13.0은 rolling이고, 다음 LTS는 13.3으로 2027-05 예정이라는 타임라인이 포함돼 있습니다.[^16]

즉 2026-11-07(KST) 시점에서 선택지는 보통 세 가지입니다.

### 선택지 A: 지금은 LTS에 머물고, 13.x는 canary에서만 굴린다

- 장점: production의 업그레이드 빈도를 억제할 수 있습니다.
- 단점: DuckDB 같은 변화는 “평가만” 하고 실제 반영이 늦습니다.

이 접근은 DB가 제품의 핵심이고, 조직이 분기 업그레이드 체계를 아직 갖추지 못한 경우에 맞습니다.

### 선택지 B: production은 LTS, 특정 워크로드만 rolling로 분리한다

- 예: OLTP는 LTS(예: 12.3 LTS), 리포팅/분석은 rolling(13.0) 또는 별도 클러스터
- 핵심: 같은 MariaDB라도 “서로 다른 운영 계약”으로 취급합니다.

이게 내가 가장 자주 택하는 형태입니다. DB 한 덩어리를 rolling로 몰아넣는 게 아니라, rolling이 필요한 이유(엔진/옵티마이저/관측 기능)를 갖는 워크로드만 분리해 트랙을 태웁니다.

### 선택지 C: rolling을 mainline으로 올리고, LTS를 holdback으로 둔다

이건 조직이 이미 다음을 갖고 있을 때만 성립합니다.

- replica 기반 무중단 스위치오버가 일상화
- 쿼리 리플레이 기반 회귀 탐지 파이프라인 보유
- 업그레이드 리드타임 SLO가 실제로 돌아감

이 조건이 없으면, rolling mainline은 “언젠가 한 번 크게 터질 것”에 가깝습니다. 작은 패치가 운영에 큰 리스크가 되는 구조는 커널 stable에서도 똑같이 봤고[^17], DB에서는 그 폭발 반경이 더 큽니다.

## 정리

MariaDB 13.0.2는 2026-09-15에 Stable(GA)로 릴리스되었고, MariaDB Foundation은 2026-09-17에 “latest Stable rolling release”라고 공식 발표했습니다.[^5]

하지만 Stable은 성숙도이고 rolling은 업데이트 경로입니다. rolling 트랙을 채택한다는 건 “업그레이드 빈도 증가”를 받아들이는 것이고, 그 비용은 기능 소개로 상쇄되지 않습니다. replica 기반 스위치오버, 회귀 탐지 자동화, 버전 진실의 단일화 같은 운영 역량을 갖춘 팀만 rolling의 이득을 실제로 회수합니다.[^13]

그래서 결론은 단순합니다. 13.0의 새 기능(특히 DuckDB engine, `innodb_log_archive`, deprecation 가시성)이 지금 당장 운영 계약을 바꿀 만큼 가치가 있는 워크로드만 rolling 트랙으로 분리하고, 나머지는 LTS 트랙에 남기는 편이 2026년 10~11월 업그레이드 큐 정리에서 가장 비용 대비 결과가 좋습니다.

## 참고 자료

- [MariaDB 13.0 Is Now Stable](https://mariadb.org/mariadb-13-0-is-now-stable/)
- [MariaDB Server – All releases](https://mariadb.org/mariadb/all-releases/)
- [MariaDB 13.0.2 Release Notes (mariadb-docs GitHub)](https://github.com/mariadb-corporation/mariadb-docs/blob/main/release-notes/community-server/13.0/13.0.2.md)
- [MariaDB 13.0.2 Release Notes (MariaDB Documentation)](https://mariadb.com/docs/release-notes/community-server/13.0/13.0.2)
- [Release Model (MariaDB Community Server)](https://mariadb.com/docs/release-notes/community-server/about/release-model)
- [About MariaDB Server (maintenance policy / rolling EOL)](https://mariadb.org/about/)
- [Announcing MariaDB Community Server 13.0 GA](https://mariadb.com/resources/blog/announcing-mariadb-community-server-13-0-ga/)
- [Announcing Yearly LTS Releases for MariaDB Community Server](https://mariadb.com/resources/blog/announcing-yearly-lts-releases-for-mariadb-community-server/)
- [Upgrading Between Major MariaDB Versions](https://mariadb.com/docs/server/server-management/install-and-upgrade-mariadb/upgrading/platform-specific-upgrade-guides/upgrading-on-linux/upgrading-between-major-mariadb-versions)
- [Downgrading Between Major Versions of MariaDB](https://mariadb.com/docs/server/server-management/install-and-upgrade-mariadb/downgrading-between-major-versions-of-mariadb)
- [MariaDB DuckDB — native columnar analytics inside MariaDB](https://mariadb.org/projects/mariadb-duckdb/)
- [mariadb Docker Official Image tags](https://hub.docker.com/_/mariadb/tags)
- [Chrome Stable 2주 릴리스가 바꾸는 업데이트 운영](https://daewooki.github.io/posts/chrome-two-week-stable-ring-design/)
- [NGINX 1.31.8 업그레이드: 패키지 기준으로 버전 진실 맞추기](https://daewooki.github.io/posts/nginx-mainline-package-version-source-of-truth/)

[^1]: <https://mariadb.org/mariadb-13-0-is-now-stable/>
[^2]: <https://mariadb.org/about/>
[^3]: <https://mariadb.com/docs/release-notes/community-server/about/release-model>
[^4]: <https://mariadb.org/mariadb/all-releases/>
[^5]: <https://github.com/mariadb-corporation/mariadb-docs/blob/main/release-notes/community-server/13.0/13.0.2.md>
[^6]: <https://mariadb.com/resources/blog/announcing-mariadb-community-server-13-0-ga/>
[^7]: <https://daewooki.github.io/posts/chrome-two-week-stable-ring-design/>
[^8]: <https://daewooki.github.io/posts/nodejs-annual-major-enterprise-runtime-policy/>
[^9]: <https://mariadb.com/docs/release-notes/community-server/13.0/13.0.2>
[^10]: <https://github.com/mariadb/server/releases>
[^11]: <https://hub.docker.com/_/mariadb/tags>
[^12]: <https://daewooki.github.io/posts/nginx-mainline-package-version-source-of-truth/>
[^13]: <https://mariadb.com/docs/server/server-management/install-and-upgrade-mariadb/upgrading/platform-specific-upgrade-guides/upgrading-on-linux/upgrading-between-major-mariadb-versions>
[^14]: <https://mariadb.com/docs/server/server-management/install-and-upgrade-mariadb/downgrading-between-major-versions-of-mariadb>
[^15]: <https://mariadb.org/projects/mariadb-duckdb/>
[^16]: <https://mariadb.com/resources/blog/announcing-yearly-lts-releases-for-mariadb-community-server/>
[^17]: <https://daewooki.github.io/posts/linux-kernel-stable-rollout-contract/>

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-7990TVG7C7"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-7990TVG7C7');
</script>
