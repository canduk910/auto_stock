# AWS RDS PostgreSQL 프로비저닝 가이드 (Supabase 이전 M4 선행)

> 목적: `db-migration-rds` 브랜치의 컷오버(M4)에 쓸 관리형 Postgres 인스턴스 생성.
> 원칙: **클라우드 중립 표준 Postgres**(향후 GCP Cloud SQL 이전 대비) — RDS Proxy/IAM-auth 등 AWS 고유기능 **미사용**, 표준 `postgresql://` DSN + TLS만.

## 목표 스펙
- 엔진: **PostgreSQL 15+** (생성컬럼 PG12+ / 표준 DDL 요구 충족)
- 인스턴스: **db.t4g.micro** (ARM, 2 vCPU / 1GB) — 신규 계정이면 12개월 프리티어 750h/월 무료
- 리전: **ap-northeast-2** (EC2와 동일, 서울)
- 스토리지: 20GB gp3 (현 데이터 ~150MB, 충분)
- 가용성: Single-AZ (트레이딩 소형 DB, Multi-AZ는 비용 2배 — 보류)
- 백업: 자동 백업 7일 보존
- 네트워크: **EC2와 동일 VPC**, 보안그룹 inbound 5432 = **EC2 SG에서만** 허용(공개 비권장)

## 사전 확인 (AWS CLI 재인증 후)
현재 `aws sts get-caller-identity`가 세션 만료. 세션에서 아래로 재인증:
```
! aws sso login          # 또는 aws login / 자격증명 방식에 맞게
```
재인증 후 EC2의 VPC/SG를 확인(RDS를 같은 VPC에 두기 위함):
```
# EC2 인스턴스의 VPC·SG·서브넷 조회 (EC2 퍼블릭 IP 3.38.228.74 기준)
aws ec2 describe-instances --region ap-northeast-2 \
  --filters "Name=ip-address,Values=3.38.228.74" \
  --query "Reservations[].Instances[].{VpcId:VpcId,Subnet:SubnetId,SG:SecurityGroups[].GroupId,AZ:Placement.AvailabilityZone}"
```

## 방법 A — AWS CLI (권장, 재현성)
아래 변수를 채운 뒤 순서대로 실행. `<VPC_ID>`/`<EC2_SG_ID>`는 위 조회 결과.

```bash
REGION=ap-northeast-2
DB_ID=autostock-pg
DB_NAME=autostock
DB_USER=autostock_admin
DB_PASS='<강력한-비밀번호-16자+>'      # 셸 히스토리 노출 주의, 이후 secret으로만 보관
VPC_ID=<VPC_ID>
EC2_SG_ID=<EC2_SG_ID>

# 1) RDS 전용 보안그룹 생성 + EC2 SG에서 5432 인바운드 허용
RDS_SG_ID=$(aws ec2 create-security-group --region $REGION \
  --group-name autostock-rds-sg --description "autostock RDS 5432 from EC2" \
  --vpc-id $VPC_ID --query GroupId --output text)
aws ec2 authorize-security-group-ingress --region $REGION \
  --group-id $RDS_SG_ID --protocol tcp --port 5432 --source-group $EC2_SG_ID

# 2) DB 서브넷 그룹 (VPC의 서브넷 2개 이상 필요)
SUBNETS=$(aws ec2 describe-subnets --region $REGION \
  --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[].SubnetId" --output text)
aws rds create-db-subnet-group --region $REGION \
  --db-subnet-group-name autostock-subnet-grp \
  --db-subnet-group-description "autostock" --subnet-ids $SUBNETS

# 3) RDS 인스턴스 생성 (Single-AZ, gp3 20GB, 프리티어 호환)
aws rds create-db-instance --region $REGION \
  --db-instance-identifier $DB_ID \
  --db-instance-class db.t4g.micro \
  --engine postgres --engine-version 15.7 \
  --master-username $DB_USER --master-user-password "$DB_PASS" \
  --allocated-storage 20 --storage-type gp3 \
  --db-name $DB_NAME \
  --vpc-security-group-ids $RDS_SG_ID \
  --db-subnet-group-name autostock-subnet-grp \
  --backup-retention-period 7 \
  --no-multi-az --no-publicly-accessible \
  --no-auto-minor-version-upgrade

# 4) 생성 완료 대기 + 엔드포인트 확인 (~5-10분)
aws rds wait db-instance-available --region $REGION --db-instance-identifier $DB_ID
aws rds describe-db-instances --region $REGION --db-instance-identifier $DB_ID \
  --query "DBInstances[0].Endpoint.Address" --output text
```

## 방법 B — AWS 콘솔
1. RDS → Create database → Standard create → **PostgreSQL 15.x**
2. Templates: **Free tier**(가능 시) 또는 Dev/Test
3. DB instance identifier `autostock-pg`, master user/password 설정
4. Instance: **db.t4g.micro**, Storage gp3 20GB
5. Connectivity: **EC2와 동일 VPC**, Public access **No**, 새 보안그룹 또는 위 RDS SG
6. Additional: Initial database name `autostock`, 백업 7일
7. Create → 5-10분 후 엔드포인트 확보

## 생성 후 (컷오버 준비)
1. **연결문자열**: `postgresql://autostock_admin:<PASS>@<엔드포인트>:5432/autostock`
   - SSL 강제: `?sslmode=require` 추가 권장.
2. **GitHub Secret 교체**: `SUPABASE_DB_URL`(deploy.yml migration 적용용) → RDS 연결문자열. 추후 앱 런타임용 `DATABASE_URL`도 동일값(또는 EC2 `.env`).
3. **연결 확인**(EC2에서): `psql "<연결문자열>" -c "select version();"`
4. → 이후 M4: migration 001~041 적용 + pg_dump/pg_restore + 컷오버(계획 참조).

## GCP 이식성 메모
- RDS Proxy / IAM DB auth / Aurora 확장 **미사용** = Cloud SQL for PostgreSQL로 이전 시 연결문자열 교체 + pg_dump/restore만으로 동일 동작.
- 파라미터 그룹은 기본값 유지(타임존은 앱이 세션 단위 `SET TIME ZONE 'Asia/Seoul'`로 처리 = M0 `pg.py`).

## 보안 주의
- 마스터 비밀번호는 셸 히스토리/코드에 남기지 말 것 → GitHub Secret / EC2 `.env`(git 미포함)로만.
- Public access No + EC2 SG 한정 인바운드 = 인터넷 노출 0.
