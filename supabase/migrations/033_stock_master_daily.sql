-- 사이클 122 (2026-06-12) — KIS 일봉 정규화 테이블.
-- KIS FHKST03010100 (`inquire_daily_itemchartprice`) 응답 영속화.
-- 매일 16:00 KST 일괄 적재 + donchian (20일 신고가) / VCP (베이스 + Pullback) / VB (ATR) 전략 활용.
-- 사용자 결정: Q1=A 매일 16:00 KST + Q2=C T-100일 + Q3=B 점진 적재 + Q4=B DB 적재만.

CREATE TABLE IF NOT EXISTS stock_master_daily (
    ticker         TEXT NOT NULL,
    bas_dd         DATE NOT NULL,
    open_price     INTEGER NOT NULL DEFAULT 0,
    high_price     INTEGER NOT NULL DEFAULT 0,
    low_price      INTEGER NOT NULL DEFAULT 0,
    close_price    INTEGER NOT NULL DEFAULT 0,
    volume         BIGINT NOT NULL DEFAULT 0,
    trade_value    BIGINT NOT NULL DEFAULT 0,
    change_rate    NUMERIC(8,4) NOT NULL DEFAULT 0,
    flng_cls_code  TEXT NOT NULL DEFAULT '',
    prtt_rate      NUMERIC(8,4) NOT NULL DEFAULT 0,
    raw            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, bas_dd)
);

COMMENT ON TABLE stock_master_daily IS
    'KIS FHKST03010100 일봉 정규화 (사이클 122). 매일 16:00 KST 적재 + donchian/VCP/VB 전략 활용.';
COMMENT ON COLUMN stock_master_daily.ticker IS 'KRX 6자리 단축코드 (stock_master.ticker 정합)';
COMMENT ON COLUMN stock_master_daily.bas_dd IS '영업일 기준일 (KIS stck_bsop_date YYYYMMDD)';
COMMENT ON COLUMN stock_master_daily.open_price IS '시가 (KIS stck_oprc)';
COMMENT ON COLUMN stock_master_daily.high_price IS '고가 (KIS stck_hgpr)';
COMMENT ON COLUMN stock_master_daily.low_price IS '저가 (KIS stck_lwpr)';
COMMENT ON COLUMN stock_master_daily.close_price IS '종가 (KIS stck_clpr)';
COMMENT ON COLUMN stock_master_daily.volume IS '거래량 (KIS acml_vol, 일봉 종가 기준 = 일일 거래량 정합)';
COMMENT ON COLUMN stock_master_daily.trade_value IS '거래대금 (KIS acml_tr_pbmn 원 단위)';
COMMENT ON COLUMN stock_master_daily.change_rate IS '전일 대비율 (KIS prdy_ctrt 또는 후처리 산출)';
COMMENT ON COLUMN stock_master_daily.flng_cls_code IS '락 구분 코드 (액면분할/배당) — VCP 종가 라인 진단';
COMMENT ON COLUMN stock_master_daily.prtt_rate IS '분할 비율 — 액면분할 시점 감지';
COMMENT ON COLUMN stock_master_daily.raw IS 'KIS output2 row 원본 (사이클 81 G-AST1 raw merge 답습)';

-- 최근 N일 조회 (donchian 20일 / VCP 60~120일 / VB 14일 ATR) — 핵심 인덱스
CREATE INDEX IF NOT EXISTS idx_stock_master_daily_ticker_bas_dd
    ON stock_master_daily (ticker, bas_dd DESC);

-- 영업일 전체 조회 (적재 진단 + 회고 분석)
CREATE INDEX IF NOT EXISTS idx_stock_master_daily_bas_dd
    ON stock_master_daily (bas_dd DESC);
