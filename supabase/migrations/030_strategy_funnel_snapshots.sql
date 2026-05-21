-- 사이클 34 (2026-05-21) — 조건검색 단계별 DB 추적 영구화.
--
-- 배경:
-- - 사용자 5/21 15:26 funnel 카운터 (donchian 111→0 / BFB 30→0 / VCP 113→0) 결함 추적 시
--   단계별 살아남은/탈락 종목을 알 수 없어 디버깅 곤란.
-- - 사이클 33 시정 후에도 운영 중 단계별 추이를 영구 보존해야 회귀 검증 + 매매 결정 추적 가능.
--
-- 본 migration:
-- - `strategy_funnel_snapshots` 신규 테이블 — 전략별 단계별 후보 종목 + 탈락 sample 보존.
-- - JSONB 캡 200 (survived) / 20 (excluded sample) — 응답/저장 크기 보호.
-- - 매일 09:30 _scan_loop 첫 진입 시점 자동 snapshot + 사용자 수동 trigger 옵션.
-- - `_reset_daily_state` 와 무관 (DB 영구 보존, 시계열 분석용).

CREATE TABLE IF NOT EXISTS strategy_funnel_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_date DATE NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    strategy_id VARCHAR NOT NULL,
    step_no INT NOT NULL,
    step_name VARCHAR NOT NULL,
    survived_count INT NOT NULL,
    excluded_count INT NOT NULL DEFAULT 0,
    -- survived_tickers: ["005930", "000660", ...] (cap 200)
    survived_tickers JSONB,
    -- excluded_sample: [{"ticker": "...", "reason": "..."}, ...] (cap 20)
    excluded_sample JSONB,
    -- 같은 (target_date, strategy_id, step_no) 페어는 1회/사이클 — UNIQUE
    -- snapshot_at 까지 포함하면 동일 영업일 다회 snapshot 가능 (수동 trigger)
    UNIQUE (target_date, strategy_id, step_no, snapshot_at)
);

CREATE INDEX IF NOT EXISTS idx_funnel_target_date
    ON strategy_funnel_snapshots(target_date DESC);
CREATE INDEX IF NOT EXISTS idx_funnel_strategy_date
    ON strategy_funnel_snapshots(strategy_id, target_date DESC);

COMMENT ON TABLE strategy_funnel_snapshots IS
    '사이클 34 — 조건검색 단계별 후보/탈락 종목 영구 추적. 09:30 자동 + 수동 trigger.';
COMMENT ON COLUMN strategy_funnel_snapshots.survived_tickers IS
    'JSONB array of ticker strings (cap 200, 응답 크기 보호).';
COMMENT ON COLUMN strategy_funnel_snapshots.excluded_sample IS
    'JSONB array of {ticker, reason} (cap 20, 탈락 사유 진단용 sample).';
