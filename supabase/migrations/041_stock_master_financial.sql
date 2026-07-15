-- 사이클 C1 (2026-07-15) — 퀀트 재무필터 데이터 수집·적재 인프라.
--
-- 마법공식(Magic Formula) + F-Score-7 퀀트 재무 필터를 위한 시계열 재무 데이터
-- 테이블. `stock_master_daily` 일봉형 100% 미러 패턴 (사이클 122 답습).
--
-- KIS 5 TR (모두 output=다기간 list, 각 원소 stac_yymm 키):
--   손익 FHKST66430200 → sale_account/sale_totl_prfi/bsop_prti/thtr_ntin/depr_cost
--   대차 FHKST66430100 → cras/fxas/total_aset/flow_lblt/total_lblt/total_cptl/cpfn
--   수익성 FHKST66430400 → cptl_ntin_rate/sale_totl_rate
--   안정성 FHKST66430600 → lblt_rate/crnt_rate
--   기타 FHKST66430500 → ebitda/ev_ebitda
--
-- PK (ticker, stac_yymm, div_cls) — div_cls: 0=년/1=분기. raw JSONB 원본 보존
-- (사이클 81 G-AST1 답습). refreshed_at 신선도/백필 게이트.
--
-- 034/039 답습 — IF NOT EXISTS idempotent (deploy migration 자동 적용 재적용 안전,
-- 사이클 145 의무).
--
-- 매매 안전성: scanner 매수 진입 전 데이터 계층 (사이클 38). 매매 hot path 무관.

CREATE TABLE IF NOT EXISTS stock_master_financial (
    ticker TEXT NOT NULL,
    stac_yymm TEXT NOT NULL,
    div_cls TEXT NOT NULL,

    -- 손익계산서 (FHKST66430200)
    sale_account NUMERIC,
    sale_totl_prfi NUMERIC,
    bsop_prti NUMERIC,
    thtr_ntin NUMERIC,
    depr_cost NUMERIC,

    -- 대차대조표 (FHKST66430100)
    cras NUMERIC,
    fxas NUMERIC,
    total_aset NUMERIC,
    flow_lblt NUMERIC,
    total_lblt NUMERIC,
    total_cptl NUMERIC,
    cpfn NUMERIC,

    -- 수익성비율 (FHKST66430400)
    cptl_ntin_rate NUMERIC,
    sale_totl_rate NUMERIC,

    -- 안정성비율 (FHKST66430600)
    lblt_rate NUMERIC,
    crnt_rate NUMERIC,

    -- 기타주요비율 (FHKST66430500)
    ebitda NUMERIC,
    ev_ebitda NUMERIC,

    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (ticker, stac_yymm, div_cls)
);

COMMENT ON TABLE stock_master_financial IS
    '사이클 C1 — KIS 재무 5 TR (손익/대차/수익성/안정성/기타) 정규화 시계열.
     마법공식 + F-Score-7 퀀트 재무 필터 데이터 계층. PK (ticker, stac_yymm, div_cls).
     raw JSONB = 5 TR 원본 병합 보존 (사이클 81 G-AST1 답습). 매매 hot path 무관
     (scanner 매수 진입 전, 사이클 38).';

CREATE INDEX IF NOT EXISTS ix_smf_ticker_div
    ON stock_master_financial (ticker, div_cls, stac_yymm DESC);

COMMENT ON INDEX ix_smf_ticker_div IS
    '사이클 C1 — 종목별 최신 기수 우선 시계열 조회 최적화 (get_financial_series).';
