-- 050_exit_ai_evaluations.sql
-- 청산 AI 섀도 기록(cycle446 — 사용자 결정 2026-10-11 「히스토리도 남겨두자」).
-- 가산형: 신규 테이블 2개만. 기존 테이블 무수정.
--
-- 설계 = `_workspace/design/2026-10-11_exit_ai_shadow.md` §5. `llm_worker` 컨테이너가
-- 아침 08:15(재시도 08:35·08:55) 1회 확정 일봉으로 멀티데이 보유(donchian_swing·kojiro·
-- vcp_breakout·bull_flag_breakout·etf_trend) 의 「계속 보유 vs 오늘 시가 청산」 을
-- AI 에게 묻고 기록만 한다. 매매 행위 0 — 어떤 청산 경로에도 들어가지 않는다.
--
-- exit_ai_evaluations : 평가 1행 = 포지션 × 입력 봉 날짜. 영구 보존(삭제 권한을 주지 않는다).
-- exit_ai_runs        : 하루 1행 — 「대상 없음」 과 「워커가 안 돌았다」 를 가른다.

CREATE TABLE IF NOT EXISTS exit_ai_evaluations (
    id                    BIGSERIAL   PRIMARY KEY,

    -- 날짜
    bar_date              DATE        NOT NULL,   -- 입력 마지막 확정 일봉 날짜
    act_date              DATE        NOT NULL,   -- 반사실 매도일(= 실행 당일)

    -- 포지션 스냅샷(G1)
    strategy_id           TEXT        NOT NULL,
    ticker                TEXT        NOT NULL,
    buy_date              DATE        NOT NULL,
    buy_order_no          TEXT        NOT NULL DEFAULT '',
    quantity              INTEGER,
    buy_price_won         NUMERIC,
    bars_held             INTEGER,

    -- 평가 순간 상태 스냅샷 — 「AI 가 무엇을 보고 그렇게 말했나」
    close_won             NUMERIC,
    unrealized_pct        NUMERIC,
    high_since_buy_won    NUMERIC,
    mfe_pct               NUMERIC,
    mae_pct               NUMERIC,
    stop_price_won        NUMERIC,
    stop_source           TEXT,
    stop_dist_pct         NUMERIC,
    target_price_won      NUMERIC,
    entry_atr             NUMERIC,
    kk_armed              BOOLEAN,
    time_exit_bars_left   INTEGER,

    -- 실행 결과
    mode                  TEXT        NOT NULL DEFAULT 'shadow',
    result                TEXT        NOT NULL,          -- ok | failed | skipped
    reason                TEXT,
    attempts              INTEGER     NOT NULL DEFAULT 1,

    -- 판단
    action                TEXT,                           -- hold | exit
    exit_score            INTEGER,
    inconsistent          BOOLEAN,
    rationale             TEXT,
    key_risks             JSONB,
    invalidations         JSONB,

    -- 모델·비용·재현
    model                 TEXT,
    prompt_version        TEXT,
    feature_version       TEXT,
    tokens_in             INTEGER,
    tokens_out            INTEGER,
    cost_usd              NUMERIC(12, 6),
    latency_ms            INTEGER,
    evaluated_at          TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    input_payload         JSONB,
    raw_response          TEXT,

    -- 사후 채움 ① — 반사실 시가
    next_open_won         NUMERIC,
    next_open_filled_at   TIMESTAMPTZ,

    -- 사후 채움 ② — 실제 결과
    outcome_status        TEXT        NOT NULL DEFAULT 'open',  -- open | closed | unknown
    exit_date              DATE,
    exit_vwap_after_won    NUMERIC,
    sold_qty_after         INTEGER,
    exit_reason            TEXT,
    -- 수동 청산 여부(cycle446 D-6) — trade_journal_orders.source 로 판정.
    -- NULL = 모름(일지 행 없음·조회 실패) · true = 운영자 수동(external/unmatched) ·
    -- false = 엔진이 낸 매도(알려진 사유 코드).
    exit_is_manual         BOOLEAN,
    outcome_filled_at      TIMESTAMPTZ,

    UNIQUE (bar_date, strategy_id, ticker, buy_date, buy_order_no)
);

CREATE INDEX IF NOT EXISTS idx_exit_ai_evaluations_act_date
    ON exit_ai_evaluations (act_date);
CREATE INDEX IF NOT EXISTS idx_exit_ai_evaluations_strategy_ticker_buy_date
    ON exit_ai_evaluations (strategy_id, ticker, buy_date);
CREATE INDEX IF NOT EXISTS idx_exit_ai_evaluations_outcome_open
    ON exit_ai_evaluations (outcome_status)
    WHERE outcome_status = 'open';

COMMENT ON TABLE exit_ai_evaluations IS
    'cycle446 — 청산 AI 섀도 기록. 평가 1행 = 포지션 × 입력 봉 날짜. 영구 보존(삭제 권한을 주지 않는다).
     어떤 매매 경로에도 연결되지 않는다(관찰 전용, 설계 §8).';
COMMENT ON COLUMN exit_ai_evaluations.exit_is_manual IS
    'trade_journal_orders.source 판정 — external/unmatched=true(운영자 수동), 알려진 사유=false(엔진),
     일지 행 없음·조회 실패=NULL(모름). 반사실 분석에서 수동 청산을 가르는 용도(cycle446 D-6).';

CREATE TABLE IF NOT EXISTS exit_ai_runs (
    run_date              DATE        PRIMARY KEY,
    bar_date              DATE,
    started_at            TIMESTAMPTZ,
    finished_at           TIMESTAMPTZ,
    status                TEXT        NOT NULL,  -- done | engine_not_running | g1_failed | no_targets | partial | disabled
    n_targets             INTEGER     NOT NULL DEFAULT 0,
    n_ok                  INTEGER     NOT NULL DEFAULT 0,
    n_failed              INTEGER     NOT NULL DEFAULT 0,
    n_skipped             INTEGER     NOT NULL DEFAULT 0,
    n_next_open_filled     INTEGER     NOT NULL DEFAULT 0,
    n_outcome_filled       INTEGER     NOT NULL DEFAULT 0,
    model                 TEXT,
    prompt_version        TEXT,
    note                  TEXT
);

COMMENT ON TABLE exit_ai_runs IS
    'cycle446 — 하루 1행. 평가 행이 0 인 날이 "대상이 없었다" 인지 "워커가 죽었다" 인지 가른다.';
