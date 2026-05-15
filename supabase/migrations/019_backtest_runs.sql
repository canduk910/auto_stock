-- Phase 2 (2026-05-16) — 백테스트 실행 영속화.
-- 외부 MCP 백테스트 서버에 제출한 job 메타데이터 + 결과 메트릭 캐시.
-- 20:00 자문 시점에 6 전략 × {current, recommended} = 최대 12 row INSERT.
-- UNIQUE (target_date, strategy_id, params_kind) — 동일 자문 사이클 재진입 멱등성 보장.

CREATE TABLE IF NOT EXISTS backtest_runs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_date       DATE NOT NULL,
    strategy_id       TEXT NOT NULL,
    params_kind       TEXT NOT NULL
                      CHECK (params_kind IN ('current', 'recommended')),
    params_snapshot   JSONB NOT NULL,
    metrics           JSONB,
    status            TEXT NOT NULL DEFAULT 'queued'
                      CHECK (status IN ('queued', 'running', 'completed', 'failed', 'skipped')),
    mcp_job_id        TEXT,
    error_message     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ,
    UNIQUE (target_date, strategy_id, params_kind)
);

COMMENT ON TABLE backtest_runs IS
    '외부 MCP 백테스트 서버 실행 영속화 (Phase 2). 자문 사이클당 6 전략 × 2 kind = 최대 12 row.';
COMMENT ON COLUMN backtest_runs.params_kind IS
    'current = 운영 적용 중 파라미터 / recommended = OpenAI 자문 결과';
COMMENT ON COLUMN backtest_runs.status IS
    'queued → running → completed | failed | skipped (YAML DSL 미지원 전략은 skipped)';
COMMENT ON COLUMN backtest_runs.metrics IS
    '백테스트 결과: total_return_pct / cagr / sharpe_ratio / sortino_ratio / max_drawdown / win_rate / profit_factor / total_trades';
COMMENT ON COLUMN backtest_runs.mcp_job_id IS
    'run_backtest_tool 응답의 job_id. retry_backtest_tool 호출 시 재사용.';

-- 날짜+전략 조회 인덱스 (UI 비교 카드 + Phase 3 자문 화면)
CREATE INDEX IF NOT EXISTS idx_backtest_runs_date_strategy
    ON backtest_runs (target_date DESC, strategy_id);

-- 진행중 status 빠른 조회 (Phase 3 poll loop)
CREATE INDEX IF NOT EXISTS idx_backtest_runs_status_running
    ON backtest_runs (status) WHERE status IN ('queued', 'running');
