-- Phase 3 (2026-05-16) — 20:00 AI자문 ↔ 백테스트 검증 동봉.
-- recommendation_engine.generate_recommendations() 가 OpenAI 자문 INSERT 후
-- 6 전략 × {current, recommended} = 최대 12 backtest_runs job 을 fire-and-forget 발화 →
-- 폴 루프가 모든 row 가 종료 상태(completed/failed/skipped) 에 도달하면
-- parameter_recommendations.backtest_summary 에 비교 메트릭 + diff 를 동봉한다.
--
-- 컬럼 스펙:
--   - JSONB nullable.
--   - null = 백테스트 미실행 / 폴 진행중 / 모든 row 가 종료 상태에 도달하지 못함.
--   - 정상 종료 시 구조:
--       {
--         "current":     { "<strategy_id>": { 8 metrics... } | null, ... },
--         "recommended": { "<strategy_id>": { 8 metrics... } | null, ... },
--         "diff":        { "<strategy_id>": { "<metric_key>": <delta>, ... }, ... }
--       }

ALTER TABLE parameter_recommendations
    ADD COLUMN IF NOT EXISTS backtest_summary JSONB;

COMMENT ON COLUMN parameter_recommendations.backtest_summary IS
    'Phase 3 (2026-05-16) — 외부 MCP 백테스트 비교 결과. current vs recommended 메트릭 + diff. NULL 이면 백테스트 미실행/진행중/실패.';

-- 백테스트 폴 루프 진입 시 미완료 자문 빠른 조회 (Phase 3 _backtest_poll_loop)
CREATE INDEX IF NOT EXISTS idx_param_recommendations_backtest_pending
    ON parameter_recommendations (target_date)
    WHERE backtest_summary IS NULL;
