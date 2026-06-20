-- 사이클 168 (2026-06-20) — stock_master 시총/거래대금 numeric 생성 컬럼 + 인덱스
--
-- 결함: stock_master.raw.hts_avls / acml_tr_pbmn 가 운영 DB 에 전부 JSONB *문자열* 로
-- 저장됨 (적재부 src/api/condition.py merge 가 KIS 응답 문자열 "1503" 등을 그대로 저장).
-- list_paged_by_filter (UI 읽기 경로) 의 jsonb numeric 비교
--   q.gte("raw->hts_avls", 1000)  ≡  raw->'hts_avls' >= '1000'::jsonb
-- 는 PostgreSQL jsonb 정렬에서 number > string 이라 항상 false → 시총/거래대금 필터 0건.
-- 운영 DB 실측: raw->'hts_avls' >= '1000'::jsonb = 0건 vs (raw->>'hts_avls')::numeric >= 1000 = 1734건.
--
-- 시정 (사용자 결정 Option A): 생성 컬럼(STORED) + 인덱스. 정확한 numeric 비교 + 인덱스 활용.
--   - hts_avls_eok    : 억원 단위 (raw 문자열 → bigint). 쿼리 .gte('hts_avls_eok', min_market_cap // 100_000_000)
--   - acml_tr_pbmn_won: 원 단위   (raw 문자열 → bigint). 쿼리 .gte('acml_tr_pbmn_won', min_trade_amount)
-- 비숫자/null 은 ~ '^[0-9]+$' 가드로 NULL (graceful — .gte 에서 자동 제외).
--
-- 매매 안전성: 생성 컬럼은 raw 를 *읽기만*(GENERATED) → raw 변경 0 (사이클 81 G-AST1 영속).
-- scanner list_by_filter (Python-side int 파싱, 사이클 108/166) 는 무관 → 후보 풀 정확 유지.
-- additive/computed 컬럼이라 데이터 손실 0. ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS idempotent.

ALTER TABLE stock_master ADD COLUMN IF NOT EXISTS hts_avls_eok bigint
  GENERATED ALWAYS AS (
    CASE WHEN raw->>'hts_avls' ~ '^[0-9]+$' THEN (raw->>'hts_avls')::bigint END
  ) STORED;

ALTER TABLE stock_master ADD COLUMN IF NOT EXISTS acml_tr_pbmn_won bigint
  GENERATED ALWAYS AS (
    CASE WHEN raw->>'acml_tr_pbmn' ~ '^[0-9]+$' THEN (raw->>'acml_tr_pbmn')::bigint END
  ) STORED;

CREATE INDEX IF NOT EXISTS ix_sm_hts_avls_eok ON stock_master(hts_avls_eok);
CREATE INDEX IF NOT EXISTS ix_sm_acml_tr_pbmn_won ON stock_master(acml_tr_pbmn_won);
