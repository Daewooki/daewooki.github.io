---
title: "AWS 비용 50% 절감한 방법 💰"
date: 2025-12-01 11:00:00 +0900
categories: [Infrastructure, AWS]
tags: [aws, cost-optimization, cloud, infra]
---

<div class="pageviews" style="margin: 0.25rem 0 1rem; opacity: 0.8;">
  <span style="font-weight: 600;">조회수</span>: <span id="pv-post">-</span>
</div>
<script defer src="/assets/js/pageviews.js"></script>


## 배경

어느 날 AWS 청구서를 보니... 😱

```
예상 비용: $3,000/월 → 실제: $6,000/월
```

이대로는 안 되겠다 싶어 비용 최적화에 돌입했습니다.

---

## 🔍 비용 분석 먼저

### AWS Cost Explorer 활용

```
1. AWS Console → Cost Explorer
2. 서비스별 비용 분석
3. 일별/주별 트렌드 확인
```

우리 경우 비용 Top 3:
1. **EC2** (45%) - 컴퓨팅
2. **RDS** (25%) - 데이터베이스
3. **Data Transfer** (15%) - 네트워크

---

## 💡 최적화 전략

### 1. EC2 Right-sizing

**문제**: 대부분의 인스턴스가 CPU 사용률 10% 미만

**해결**:
```bash
# AWS Compute Optimizer 활용
# 추천 인스턴스 타입 확인

# Before
m5.xlarge (4 vCPU, 16GB) - $140/월

# After  
t3.medium (2 vCPU, 4GB) - $30/월
```

**절감**: 인스턴스당 약 78% 절감

### 2. Reserved Instances & Savings Plans

**1년 이상 사용할 인스턴스는 예약!**

```
On-Demand: $100/월
1년 예약 (선결제 없음): $63/월  → 37% 절감
1년 예약 (전체 선결제): $55/월  → 45% 절감
3년 예약 (전체 선결제): $37/월  → 63% 절감
```

**팁**: Savings Plans가 더 유연해서 추천

### 3. Spot Instances 활용

**배치 작업, 개발 환경에 적합**

```yaml
# EKS에서 Spot 노드 그룹 설정
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata:
  name: my-cluster
nodeGroups:
  - name: spot-workers
    instanceTypes: ["m5.large", "m5a.large", "m4.large"]
    spot: true
    minSize: 2
    maxSize: 10
```

**절감**: On-Demand 대비 최대 90% 절감

### 4. RDS 최적화

**Multi-AZ가 정말 필요한가?**

```
개발/스테이징: Single-AZ로 변경
프로덕션: Multi-AZ 유지 (가용성 중요)
```

**Aurora Serverless v2 고려**
```
트래픽 변동이 큰 경우 → Aurora Serverless
일정한 트래픽 → Provisioned
```

### 5. 스토리지 정리

**S3 Lifecycle Policy**
```json
{
  "Rules": [
    {
      "ID": "MoveToIA",
      "Status": "Enabled",
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        },
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ]
    }
  ]
}
```

**EBS 스냅샷 정리**
```bash
# 30일 이상 된 스냅샷 삭제
aws ec2 describe-snapshots --owner-ids self \
  --query 'Snapshots[?StartTime<=`2025-11-01`].SnapshotId' \
  --output text | xargs -n 1 aws ec2 delete-snapshot --snapshot-id
```

### 6. 네트워크 비용

**NAT Gateway 비용 폭탄 주의!**

```
NAT Gateway: $0.045/GB + $0.045/시간

대안:
- NAT Instance (t3.nano): 저렴하지만 관리 필요
- VPC Endpoint: S3, DynamoDB 등은 무료
- IPv6: NAT 불필요
```

**VPC Endpoint 추가**
```bash
aws ec2 create-vpc-endpoint \
  --vpc-id vpc-xxx \
  --service-name com.amazonaws.ap-northeast-2.s3 \
  --route-table-ids rtb-xxx
```

---

## 📊 결과

| 항목 | Before | After | 절감률 |
|------|--------|-------|--------|
| EC2 | $2,700 | $1,200 | 56% |
| RDS | $1,500 | $800 | 47% |
| Network | $900 | $400 | 56% |
| Storage | $600 | $300 | 50% |
| **Total** | **$6,000** | **$2,900** | **52%** |

---

## 🛠️ 자동화

### AWS Budget 알림 설정

```bash
aws budgets create-budget \
  --account-id 123456789012 \
  --budget file://budget.json \
  --notifications-with-subscribers file://notifications.json
```

### 태그 기반 비용 추적

```
필수 태그:
- Environment: prod/staging/dev
- Team: backend/frontend/data
- Project: project-name
```

---

## 🎯 마무리

비용 최적화 체크리스트:

- [ ] Cost Explorer로 현황 파악
- [ ] Right-sizing (Compute Optimizer 활용)
- [ ] Reserved Instances / Savings Plans 검토
- [ ] 개발 환경 Spot 전환
- [ ] S3 Lifecycle Policy 적용
- [ ] 사용하지 않는 리소스 정리
- [ ] Budget 알림 설정

**클라우드 비용은 방심하면 순식간에 늘어납니다.**
정기적인 모니터링이 핵심이에요! 💪

