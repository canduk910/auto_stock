-- cycle455 (2026-10-14) — 국내 업종지수 일별 종가 (시장 유닛 원천: 코스피 종합 0001 · 코스닥 종합 1001).
-- KIS FHKUP03500100(국내주식업종기간별시세) 응답 영속화. index_code 로 지수를 구분한다.
-- 가산형(신규 테이블) — 사용자 사전 승인 범위.

CREATE TABLE IF NOT EXISTS domestic_index_daily (
    index_code  TEXT NOT NULL,
    bas_dd      DATE NOT NULL,
    close_price NUMERIC(18,4) NOT NULL,
    raw         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (index_code, bas_dd)
);

COMMENT ON TABLE domestic_index_daily IS
    'KIS FHKUP03500100 국내 업종지수 일별 종가 (cycle455). 시장 유닛(터틀 4전략) 원천.';
COMMENT ON COLUMN domestic_index_daily.index_code IS 'KIS 업종 코드(FID_INPUT_ISCD) — 0001 코스피 종합 · 1001 코스닥 종합';
COMMENT ON COLUMN domestic_index_daily.bas_dd IS '거래일(KIS stck_bsop_date YYYYMMDD)';
COMMENT ON COLUMN domestic_index_daily.close_price IS '종가(KIS bstp_nmix_prpr)';
COMMENT ON COLUMN domestic_index_daily.raw IS 'KIS output2 row 원본';

CREATE INDEX IF NOT EXISTS idx_domestic_index_daily_code_bas_dd
    ON domestic_index_daily (index_code, bas_dd DESC);
