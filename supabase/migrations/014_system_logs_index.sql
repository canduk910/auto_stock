-- system_logs 조회 가속용 복합 인덱스.
-- 대시보드 LogViewer (/api/logs)와 일일 로그 분석(generate_daily_log_report)에서
-- timestamp DESC + log_level 필터를 자주 사용 → 풀 스캔 제거.

CREATE INDEX IF NOT EXISTS idx_system_logs_ts_level
    ON system_logs (timestamp DESC, log_level);

COMMENT ON INDEX idx_system_logs_ts_level IS
    '대시보드/AI 분석에서 timestamp DESC + log_level 필터 가속';
