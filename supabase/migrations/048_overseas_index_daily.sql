-- cycle443 (2026-10-11) — 해외 지수 일별 종가 (ndx2x_riskoff 전략의 유일한 신호 원천).
-- KIS FHKST03030100(해외주식 종목/지수/환율기간별시세) 응답 영속화. index_code 로 자산을
-- 구분(지금은 "NDX" 하나) — 다른 해외지수를 쓰는 전략이 생기면 그 코드로 같은 표를 공유한다.
-- 가산형(신규 테이블) — 사용자 사전 승인 범위.

CREATE TABLE IF NOT EXISTS overseas_index_daily (
    index_code  TEXT NOT NULL,
    bas_dd      DATE NOT NULL,
    close_price NUMERIC(18,4) NOT NULL,
    raw         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (index_code, bas_dd)
);

COMMENT ON TABLE overseas_index_daily IS
    'KIS FHKST03030100 해외지수 일별 종가 (cycle443). ndx2x_riskoff 전략 T7/R4 신호 원천.';
COMMENT ON COLUMN overseas_index_daily.index_code IS '해외지수 코드(KIS FID_INPUT_ISCD) — 지금은 "NDX"(나스닥100) 하나';
COMMENT ON COLUMN overseas_index_daily.bas_dd IS '미국 거래일(KIS stck_bsop_date YYYYMMDD)';
COMMENT ON COLUMN overseas_index_daily.close_price IS '종가(KIS ovrs_nmix_prpr)';
COMMENT ON COLUMN overseas_index_daily.raw IS 'KIS output2 row 원본(사이클 81 G-AST1 raw merge 관례 답습)';

-- 최근 N영업일 조회(T7 SMA140·R4 250일 창) — 핵심 인덱스
CREATE INDEX IF NOT EXISTS idx_overseas_index_daily_code_bas_dd
    ON overseas_index_daily (index_code, bas_dd DESC);
