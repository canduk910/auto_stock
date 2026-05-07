-- 매일 정산(16:10) 후 system_logs + trade_history 메트릭을 OpenAI로 분석한 개선 리포트.
-- (target_date) UNIQUE — 동일 영업일 재실행 시 중복 방지.

CREATE TABLE IF NOT EXISTS daily_log_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_date DATE NOT NULL UNIQUE,
    summary TEXT,
    findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    model VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_log_reports_date
    ON daily_log_reports(target_date DESC);

COMMENT ON TABLE daily_log_reports IS
    '매일 정산(16:10) 후 system_logs/trade_history 메트릭을 OpenAI로 분석한 개선 리포트';
COMMENT ON COLUMN daily_log_reports.findings IS
    '[{category, severity(high/medium/low), title, detail, suggestion}, ...]';
COMMENT ON COLUMN daily_log_reports.metrics IS
    '집계 메트릭: 레벨별 카운트, 상위 WARNING/ERROR 패턴, 거래/체결 통계 등';
