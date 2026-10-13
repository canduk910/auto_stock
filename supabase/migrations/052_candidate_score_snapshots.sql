-- RS·재무·목표가 리비전 2단계 — 후보·보유 종목 점수 관찰 스냅샷 (가산형 신규 테이블).
-- 매일 부팅 때 4전략(donchian_swing · vcp_breakout · kojiro · etf_trend)의 후보/보유 종목별 점수를 한 행씩 남긴다.
-- 모든 점수 칸은 NULL 허용 — 「모름」 = NULL (0 으로 채우지 않는다).

CREATE TABLE IF NOT EXISTS candidate_score_snapshots (
    target_date             DATE NOT NULL,
    strategy_id             TEXT NOT NULL,
    ticker                  TEXT NOT NULL,
    role                    TEXT NOT NULL,
    rs_raw                  DOUBLE PRECISION,
    rs_pct                  INTEGER,
    sector_key              TEXT,
    vs_sector               DOUBLE PRECISION,
    sector_pct              INTEGER,
    in_sector_pct           INTEGER,
    revision_breadth        DOUBLE PRECISION,
    target_median_change    DOUBLE PRECISION,
    opinion_brokers         INTEGER,
    fin_quarter             TEXT,
    op_income_q             DOUBLE PRECISION,
    op_income_q_yoy         DOUBLE PRECISION,
    op_turnaround           BOOLEAN,
    op_yoy_growth           DOUBLE PRECISION,
    revenue_yoy_growth      DOUBLE PRECISION,
    net_turnaround          BOOLEAN,
    roe                     DOUBLE PRECISION,
    debt_ratio_latest       DOUBLE PRECISION,
    debt_ratio_down_years   INTEGER,
    ttm_op_to_max_ratio     DOUBLE PRECISION,
    rs_population           INTEGER,
    computed_at             TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (target_date, strategy_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_candidate_score_snapshots_ticker
    ON candidate_score_snapshots (ticker, target_date);
