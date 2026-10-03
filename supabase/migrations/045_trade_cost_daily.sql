-- 045_trade_cost_daily.sql
-- 트랙 C(실비용 산출) — KIS TTTC8715R(기간별매매손익현황조회) 정산값 사후 대사 저장소.
-- 가산형: 신규 테이블 2개만. 기존 테이블·trade_history.profit_loss 의미(세전·비용 전) 무변경.
--
-- trade_cost_daily        : (매매일, 종목) 1행 — KIS 행을 같은 키로 접어 합산, 원문은 raw 목록.
-- trade_cost_period_totals: 대사 실행 기간(from_dt~to_dt)의 KIS output2 합계 — 행 합계와 1원 대조용.
-- 금액·수량은 KIS 가 문자열로 주므로 NUMERIC 으로 손실 없이 둔다.

CREATE TABLE IF NOT EXISTS trade_cost_daily (
    trad_dt     DATE        NOT NULL,
    pdno        VARCHAR(12) NOT NULL,
    prdt_name   TEXT        NOT NULL DEFAULT '',
    buy_qty     NUMERIC     NOT NULL DEFAULT 0,
    buy_amt     NUMERIC     NOT NULL DEFAULT 0,
    sll_qty     NUMERIC     NOT NULL DEFAULT 0,
    sll_amt     NUMERIC     NOT NULL DEFAULT 0,
    rlzt_pfls   NUMERIC     NOT NULL DEFAULT 0,
    fee         NUMERIC     NOT NULL DEFAULT 0,
    tl_tax      NUMERIC     NOT NULL DEFAULT 0,
    row_count   INTEGER     NOT NULL DEFAULT 1,
    raw         JSONB       NOT NULL DEFAULT '[]'::jsonb,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trad_dt, pdno)
);

CREATE TABLE IF NOT EXISTS trade_cost_period_totals (
    from_dt        DATE        NOT NULL,
    to_dt          DATE        NOT NULL,
    buy_fee_smtl   NUMERIC,
    sll_fee_smtl   NUMERIC,
    sll_tltx_smtl  NUMERIC,
    buy_tax_smtl   NUMERIC,
    tot_fee        NUMERIC,
    tot_tltx       NUMERIC,
    tot_rlzt_pfls  NUMERIC,
    raw            JSONB       NOT NULL DEFAULT '{}'::jsonb,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (from_dt, to_dt)
);
