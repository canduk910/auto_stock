-- 047_trade_journal.sql
-- 거래일지 1a(cycle412) — 관찰자 방식(워커가 로그·G0·G1 을 읽어 쓴다, 주문 경로 0줄).
-- 가산형: 신규 테이블 4개만. 기존 테이블 무수정.
--
-- trade_journal_orders : 주문 1건 1행 — (order_date, order_no, side) UNIQUE, 처음 값을 지킨다.
-- trade_journal_stops  : 손절선 사건(R8) — 한 회전·한 (전략,종목)에 1행.
-- trade_journal_notes  : 메모(D2, 1a 는 표만 — API 는 1b).
-- trade_journal_cursor : 로그 꼬리읽기 커서(재시작 복구용).

CREATE TABLE IF NOT EXISTS trade_journal_orders (
    id               BIGSERIAL PRIMARY KEY,
    order_date       DATE        NOT NULL,
    order_no         TEXT        NOT NULL,
    side             TEXT        NOT NULL,
    strategy         TEXT        NOT NULL,
    ticker           TEXT        NOT NULL,
    source           TEXT        NOT NULL,
    reason_code      TEXT,
    reason_sub       TEXT,
    judge_price      INTEGER,
    order_price      INTEGER,
    order_division   TEXT,
    exchange         TEXT,
    parent_order_no  TEXT,
    fired_line       INTEGER,
    effective_line   INTEGER,
    signal           JSONB,
    params           JSONB,
    noted_at         TIMESTAMPTZ NOT NULL,
    UNIQUE (order_date, order_no, side)
);

CREATE TABLE IF NOT EXISTS trade_journal_stops (
    id            BIGSERIAL PRIMARY KEY,
    strategy      TEXT        NOT NULL,
    ticker        TEXT        NOT NULL,
    buy_date      DATE,
    pos_order_no  TEXT,
    observed_at   TIMESTAMPTZ NOT NULL,
    event         TEXT        NOT NULL,
    stop_price    INTEGER,
    stop_kind     TEXT,
    target_price  INTEGER,
    target_hit    BOOLEAN,
    arm_price     INTEGER,
    inputs        JSONB
);

CREATE INDEX IF NOT EXISTS idx_trade_journal_stops_strategy_ticker_observed_at
    ON trade_journal_stops (strategy, ticker, observed_at);

CREATE TABLE IF NOT EXISTS trade_journal_notes (
    id               BIGSERIAL PRIMARY KEY,
    anchor_trade_id  UUID        NOT NULL UNIQUE,
    strategy         TEXT,
    ticker           TEXT,
    buy_date         DATE,
    body             TEXT        NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trade_journal_cursor (
    name         TEXT PRIMARY KEY,
    file_name    TEXT        NOT NULL,
    inode        BIGINT      NOT NULL,
    byte_offset  BIGINT      NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
