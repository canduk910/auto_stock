# 사이클 30 — DB 정리 SQL 초안 (042700 + 475430 중복 제거)

> **주의**: 자금 안전 critical. DELETE 전 반드시 SELECT 결과 확인 + 사용자 명시 승인 필수.

## 1. 042700 한미반도체 — 5/20 중복 정리

### Step 1 — SELECT 로 현황 확인 (먼저 실행)
```sql
-- 5/20 042700 BUY/SELL 전체 조회 (timestamp ASC)
SELECT
    id,
    timestamp AT TIME ZONE 'Asia/Seoul' AS ts_kst,
    trade_type,
    status,
    order_no,
    price,
    quantity,
    strategy,
    created_at AT TIME ZONE 'Asia/Seoul' AS created_kst
FROM trade_history
WHERE ticker = '042700'
  AND timestamp >= '2026-05-20T00:00:00+09:00'
  AND timestamp <  '2026-05-21T00:00:00+09:00'
ORDER BY trade_type, timestamp ASC;
```

### Step 2 — 실거래 4건 식별 패턴
사용자 보고에 따르면 042700 5/20 실거래는 **BUY 4건 + SELL 2건 = 총 6건** (실현손익 8건 잡힘은 페어링 오류 — 4 BUY × 2 SELL 잘못 페어).

식별 기준 (운영 로그 + 시각 + order_no 매칭):
- 02:14:16 BUY (첫 매수, NXT 야간 추정)
- 03:21:16 BUY (NXT 추가 매수)
- 13:21:16 BUY (KRX 첫 매수)
- (4번째 BUY 시각은 SELECT 결과 확인 후)
- (SELL 2건 시각은 SELECT 결과 확인 후)

### Step 3 — 중복 식별 및 보존할 id 확정
```sql
-- 같은 (order_no, trade_type) 그룹에서 가장 이른 created_at row 만 보존
-- (가장 최초 INSERT = 실거래 시점 매핑 가능성 높음. 핑퐁 INSERT 는 후속 재기동)
WITH dup_ranked AS (
    SELECT
        id,
        order_no,
        trade_type,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY ticker, order_no, trade_type
            ORDER BY created_at ASC
        ) AS rn
    FROM trade_history
    WHERE ticker = '042700'
      AND timestamp >= '2026-05-20T00:00:00+09:00'
      AND timestamp <  '2026-05-21T00:00:00+09:00'
)
SELECT id, order_no, trade_type, created_at, rn
FROM dup_ranked
WHERE rn > 1  -- 중복 (보존 대상이 아닌 row)
ORDER BY created_at;
```

### Step 4 — DELETE (사용자 승인 후만 실행)
```sql
-- DELETE 전 반드시 위 Step 3 SELECT 결과 사용자 검토 후 진행
WITH dup_ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY ticker, order_no, trade_type
            ORDER BY created_at ASC
        ) AS rn
    FROM trade_history
    WHERE ticker = '042700'
      AND timestamp >= '2026-05-20T00:00:00+09:00'
      AND timestamp <  '2026-05-21T00:00:00+09:00'
)
DELETE FROM trade_history
WHERE id IN (SELECT id FROM dup_ranked WHERE rn > 1)
RETURNING id, order_no, trade_type;
```

### 대안: NULL order_no 가 포함된 경우 — `order_no IS NULL` 별도 처리
```sql
-- order_no NULL row 는 위 PARTITION 에서 모두 별도 그룹 → 보존됨.
-- NULL row 가 명백한 핑퐁 INSERT 라면 별도 식별 후 수동 DELETE 필요.
```

---

## 2. 475430 — 5/20 SELL 0000462500 1건 중복 정리

### Step 1 — SELECT
```sql
SELECT
    id,
    timestamp AT TIME ZONE 'Asia/Seoul' AS ts_kst,
    trade_type,
    status,
    order_no,
    price,
    quantity,
    created_at AT TIME ZONE 'Asia/Seoul' AS created_kst
FROM trade_history
WHERE ticker = '475430'
  AND trade_type = 'SELL'
  AND order_no = '0000462500'
  AND timestamp >= '2026-05-20T00:00:00+09:00'
  AND timestamp <  '2026-05-21T00:00:00+09:00'
ORDER BY created_at ASC;
```

### Step 2 — DELETE (가장 이른 created_at 1건만 보존)
```sql
WITH dup_ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY ticker, order_no, trade_type
            ORDER BY created_at ASC
        ) AS rn
    FROM trade_history
    WHERE ticker = '475430'
      AND order_no = '0000462500'
      AND trade_type = 'SELL'
      AND timestamp >= '2026-05-20T00:00:00+09:00'
      AND timestamp <  '2026-05-21T00:00:00+09:00'
)
DELETE FROM trade_history
WHERE id IN (SELECT id FROM dup_ranked WHERE rn > 1)
RETURNING id, order_no;
```

---

## 3. daily_performance 재계산 (DELETE 완료 후)

```sql
-- 5/20 일일 실적 재계산 (멱등 함수)
SELECT recompute_daily_performance('2026-05-20');

-- 결과 확인
SELECT
    date,
    strategy,
    total_asset,
    daily_realized_pnl,
    daily_profit_rate,
    cumulative_return_rate
FROM daily_performance
WHERE date = '2026-05-20'
ORDER BY strategy;
```

---

## 4. 사고 전체 영향 범위 추가 조사 (선택)

같은 결함이 다른 종목/날짜에도 잠복했을 가능성. 전수 조사 SQL:

```sql
-- 같은 (ticker, order_no, trade_type) 페어가 2건 이상인 row 식별
WITH dup_check AS (
    SELECT
        ticker,
        order_no,
        trade_type,
        COUNT(*) AS cnt,
        MIN(timestamp) AS first_ts,
        MAX(timestamp) AS last_ts
    FROM trade_history
    WHERE order_no IS NOT NULL
      AND order_no != ''
      AND timestamp >= '2026-05-01T00:00:00+09:00'
    GROUP BY ticker, order_no, trade_type
    HAVING COUNT(*) >= 2
)
SELECT * FROM dup_check ORDER BY first_ts DESC;
```

---

## 5. 안전 가드

- **DELETE 절대 금지** — Step 1 SELECT 결과 사용자 검토 후에만 진행
- created_at ASC 정렬로 "가장 먼저 INSERT 된 row 보존" 원칙 — 실거래 시점 매핑 가능성 가장 높음
- ROW_NUMBER PARTITION 기준 `(ticker, order_no, trade_type)` — UNIQUE 후보 키와 동일
- NULL order_no row 는 별도 그룹화 → 모두 보존 (수동 매매 사전 등 가능성)
- DELETE 후 `daily_performance` 재계산 필수 (실현손익 왜곡 정정)
- 운영 중에는 실행 자제 — 자정 후 또는 _settle 완료 후 권장
