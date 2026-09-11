-- cycle276 (2026-09-11) — AI 매수평가(LLM shadow) 주문 시점 기록 전용 테이블.
--
-- 배경: cycle274 는 `check_buy_signal` 의 `return Signal.BUY` 직전(= 신호 시점)에서
-- 평가를 던졌다. 신호 10건 중 실제 주문은 5건(50%)이라 점수 절반이 실현손익에 붙지
-- 않았고, 래치가 (전략, 종목)/일 이라 12:06 첫 신호의 점수가 15:13 주문에 붙는 사례
-- (09-10 000990)까지 생겼다. cycle276 은 훅을 `order_engine.execute_buy` 의
-- `place_order` 성공 직후로 옮겨 **주문 1건 = 평가 1행**을 만든다.
--
-- PK (trade_date, account_no, ticker, order_no) — KIS ODNO 는 **하루 단위로만** 유일하다
-- (`order_engine.reset_daily_state` docstring). 그래서 날짜가 PK 선두에 있어야 하고,
-- trade_history 조인도 (trade_date, ticker, order_no) 3축이어야 안전하다.
-- order_no 는 TEXT NOT NULL DEFAULT '' — 향후 enforce 로 "차단되어 주문이 없는 평가"를
-- 같은 PK 로 수용하기 위한 전방 호환이며, 그 경우를 지금 있는 order_no 빈 값 수기 체결
-- 행과 구분하려고 eval_kind('order'|'blocked') 열을 처음부터 둔다.
--
-- 회고분석 전제(사후 복원 불가라 지금 넣는다):
--   prompt_version/feature_version  — 프롬프트·지표가 바뀐 전후 행을 섞어 회귀하면 안 된다
--   budget_remaining_after_won/open_positions_n — 차단의 반사실은 "손익이 사라진다"가
--     아니라 "다른 종목 매수로 대체된다" 일 수 있다. 그 구분에 필요하다
--   raw_response — 파싱 실패 재분류 + 다른 파서로 재판독
--   input_payload — build_messages 세 인자 그대로. 훗날 다른 모델로 오프라인 재채점
--   order_kst/evaluated_at/eval_to_order_lag_ms — enforce(선평가)로 가면 "얼마나 묵은
--     점수로 샀는지" 를 재야 한다
--
-- 매매 안전성: 이 테이블은 주문이 KIS 에 접수된 **뒤** 기록되는 관측 계층이다.
-- 쓰기는 전부 `asyncio.create_task` 안 never-raise 경로이고 매매 hot path 무관.
--
-- IF NOT EXISTS 는 deploy.yml 이 매 push 마다 전 마이그레이션을 재적용하고
-- ON_ERROR_STOP=0 + `|| true` 로 오류를 삼키기 때문에 **필수**다(031·042 선례).
--
-- 번호 재배정: cycle275(입출금 T+2) 명세도 043 을 예약했었다 — cycle276 이 043,
-- cycle275 는 044 로 재배정한다.

CREATE TABLE IF NOT EXISTS llm_buy_evaluations (
    -- ---- PK 4열 -------------------------------------------------------
    trade_date              DATE        NOT NULL,
    account_no              TEXT        NOT NULL,
    ticker                  TEXT        NOT NULL,
    order_no                TEXT        NOT NULL DEFAULT '',

    -- ---- 분류 ---------------------------------------------------------
    eval_kind               TEXT        NOT NULL DEFAULT 'order',
    account_product         TEXT,
    strategy_id             TEXT        NOT NULL,
    mode                    TEXT        NOT NULL,
    result                  TEXT        NOT NULL,
    reason                  TEXT,

    -- ---- 평가 결과 -----------------------------------------------------
    score                   INTEGER,
    min_score               INTEGER     NOT NULL,
    would_block             BOOLEAN,
    rationale               TEXT,
    key_risks               JSONB,
    invalidations           JSONB,

    -- ---- 모델/비용/지연 -------------------------------------------------
    model                   TEXT,
    tokens_in               INTEGER,
    tokens_out              INTEGER,
    cost_usd                NUMERIC(12, 6),
    latency_ms              INTEGER,
    verdict_lag_ms          INTEGER,
    eval_to_order_lag_ms    INTEGER,
    order_kst               TIMESTAMPTZ NOT NULL,
    evaluated_at            TIMESTAMPTZ,

    -- ---- 주문 스냅샷 ----------------------------------------------------
    order_price_won         BIGINT      NOT NULL,
    ordered_qty             INTEGER     NOT NULL,
    order_notional_won      BIGINT      NOT NULL,
    order_division          TEXT        NOT NULL,
    order_path              TEXT        NOT NULL,
    exchange                TEXT,
    board                   TEXT        NOT NULL,
    current_price_won       BIGINT,

    -- ---- 신호 역참조(있을 때만) -------------------------------------------
    signal_matched          BOOLEAN     NOT NULL DEFAULT FALSE,
    signal_price_won        BIGINT,
    -- ⚠️ tz-naive 로컬 시각 문자열("HH:MM:SS")이다. 원천은 전략의 `datetime.now()`
    -- (tz 인자 없음)이라 EC2 컨테이너의 `TZ=Asia/Seoul` 전제에서만 KST 와 같다 —
    -- 값 자체는 KST 를 **보장하지 않는다**. 그래서 이름에 `_kst` 를 쓰지 않는다.
    signal_time_local       TEXT,
    strategy_board          TEXT,
    target_won              BIGINT,
    k                       NUMERIC(10, 4),
    breakout_excess_bp      NUMERIC(12, 4),

    -- ---- 판정 시점 표류 --------------------------------------------------
    post_order_drift_bp     NUMERIC(12, 4),
    drift_price_won         BIGINT,
    tick_age_s              NUMERIC(10, 2),

    -- ---- 주문 시점 제약(반사실 분석용) -------------------------------------
    budget_total_won        BIGINT,
    budget_remaining_after_won BIGINT,
    open_positions_n        INTEGER,

    -- ---- 버전 고정 + 원문 -------------------------------------------------
    prompt_version          TEXT,
    feature_version         TEXT,
    bars_count              INTEGER,
    input_payload           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    raw_response            JSONB,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (trade_date, account_no, ticker, order_no)
);

COMMENT ON TABLE llm_buy_evaluations IS
    'cycle276 — AI 매수평가(LLM shadow) 주문 시점 기록. 주문 1건 = 1행(성공·실패 모두).
     PK (trade_date, account_no, ticker, order_no) — KIS ODNO 는 하루 단위로만 유일.
     trade_history 조인은 (trade_date, ticker, order_no) 3축. 체결 결과(체결가·수량·손익)는
     이 테이블에 절대 쓰지 않는다 — 결과는 언제나 조인으로 얻는다(자문 R1).';

COMMENT ON COLUMN llm_buy_evaluations.eval_kind IS
    '''order'' = 실제 주문에 붙은 평가 / ''blocked'' = (미래 enforce) 차단되어 주문이 없는 평가.
     운영 DB 에 이미 존재하는 order_no 빈 값 수기 체결 행과 충돌하지 않게 처음부터 분리한다.';
COMMENT ON COLUMN llm_buy_evaluations.board IS
    '주문 접수 KST 시각만으로 파생한 보드(pre_nxt/main/post_nxt/off_hours).
     session_tracker.active 가 아니다 — 그 값은 30초 stale 이라 09:00:0x 에 pre_nxt 로 굳는다(cycle264).';
COMMENT ON COLUMN llm_buy_evaluations.order_path IS
    '''market'' = 주 경로(시장가 또는 프리장 사전변환 지정가) / ''fallback'' = 시장가 거부 후
     지정가 5호가 폴백. 둘 다 LIMIT 일 수 있어 order_division 만으로는 분리되지 않는다(자문 R3).';
COMMENT ON COLUMN llm_buy_evaluations.ordered_qty IS
    '주문 수량이며 체결 수량이 아니다. 실현손익 분석은 trade_history.quantity 를 쓴다(자문 R8).';
COMMENT ON COLUMN llm_buy_evaluations.budget_remaining_after_won IS
    '이 주문의 pending_buy_amounts 가 이미 등록된 **뒤**의 전략 잔여 예산
     (= total_investment - _calc_used_funds()). "이 주문을 안 냈다면 남았을 예산" 은
     이 값 + order_notional_won 이다(자문 MEDIUM).';
COMMENT ON COLUMN llm_buy_evaluations.post_order_drift_bp IS
    '판정 도착 순간 scanner 현재가 대비 주문가 이동폭(bp). + = 주문 뒤 올랐다(이득).
     cycle274 의 slip_bp 와 **부호 의미가 반대**다 — 두 이름의 값을 절대 합산하지 말 것.';
COMMENT ON COLUMN llm_buy_evaluations.tick_age_s IS
    '드리프트 기준 틱의 나이(초). 무송출 종목(nxt_tradable=false, cycle252)은 고정값이 실려
     "표류 0" 으로 오독되므로, 판독 시 stale 행을 분포에서 제외하는 근거로 쓴다.';
COMMENT ON COLUMN llm_buy_evaluations.input_payload IS
    'build_messages 의 세 인자 그대로 {payload, tech, bars30}. 요약·절단 금지 —
     훗날 다른 모델·다른 프롬프트로 같은 거래를 오프라인 재채점하는 유일한 다리다.';

CREATE INDEX IF NOT EXISTS idx_llm_eval_trade_date
    ON llm_buy_evaluations (trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_llm_eval_strategy_date
    ON llm_buy_evaluations (strategy_id, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_llm_eval_ticker_date
    ON llm_buy_evaluations (ticker, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_llm_eval_order_no
    ON llm_buy_evaluations (order_no)
    WHERE order_no <> '';

COMMENT ON INDEX idx_llm_eval_order_no IS
    'cycle276 — UI 버튼이 order_no 단독(또는 CSV 배치)으로 조회한다. PK 선두가 trade_date 라
     PK 인덱스로는 그 조회가 커버되지 않는다. 빈 order_no 행은 조회 대상이 아니라 부분 인덱스.';
