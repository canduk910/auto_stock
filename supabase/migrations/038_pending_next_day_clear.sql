-- 사이클 162 (2026-06-17) — 익일청산큐 DB 영속화
--
-- 사용자 보고: 알테오젠 (196170, VB) + 알지노믹스 (476830, LTV) 6/17 15:20 강제청산 누락.
-- 근본 원인 후보: `_pending_next_day_clear: set[tuple[ticker, strategy_id]]` 메모리 휘발
-- (EC2 재기동 시) → drain 시 0건 → 강제청산 영구 누락.
--
-- 옵션 A (domain-expert 자문 채택) — DB 테이블 신규.
-- - target_date PK = 다음 영업일 drain 후 즉시 DELETE 가능
-- - ticker + strategy_id 복합 PK = 동일 종목 여러 전략 보유 시 보존
-- - reason 컬럼 = 진단 (nxt_not_tradable / nxt_open_missing / market_order_disallowed_fallback)
--
-- 영속 의무 매트릭스:
-- - 사이클 32 R4 보유/익일청산 절대 보호
-- - 사이클 38 명문화 (매도/익일청산 hot path 영속)
-- - 사이클 88 G-REJECT graceful (DB 실패 시 메모리 set 보존)
-- - 사이클 149 boot REST seed 패턴 답습 (boot_manager 영역 호출)

CREATE TABLE IF NOT EXISTS pending_next_day_clear (
    target_date DATE NOT NULL,
    ticker      VARCHAR(10) NOT NULL,
    strategy_id VARCHAR(50) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason      VARCHAR(50) NOT NULL DEFAULT 'unknown',
    PRIMARY KEY (target_date, ticker, strategy_id)
);

CREATE INDEX IF NOT EXISTS idx_pending_ndc_target_date
    ON pending_next_day_clear (target_date);
