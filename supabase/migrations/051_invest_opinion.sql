-- RS·재무·목표가 리비전 1단계 — 증권사 투자의견 이력 + 추정실적 월초 스냅샷 (가산형 신규 테이블).

CREATE TABLE IF NOT EXISTS invest_opinion_history (
    ticker          TEXT NOT NULL,
    bsop_date       DATE NOT NULL,
    mbcr_name       TEXT NOT NULL,
    invt_opnn       TEXT,
    rgbf_invt_opnn  TEXT,
    hts_goal_prc    BIGINT,
    stck_prdy_clpr  BIGINT,
    dprt            NUMERIC(10,2),
    raw             JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, bsop_date, mbcr_name)
);

CREATE TABLE IF NOT EXISTS estimate_perform_snapshot (
    ticker          TEXT NOT NULL,
    snapshot_month  DATE NOT NULL,
    settle_months   TEXT[] NOT NULL DEFAULT '{}',
    raw             JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, snapshot_month)
);
