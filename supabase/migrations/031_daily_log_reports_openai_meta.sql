-- 사이클 58 V-2 (2026-06-04): daily_log_reports OpenAI 메타 컬럼 추가
-- input/output/total tokens + latency + cost_estimate_usd (KRW 환산은 조회 시점)
-- 모두 NULL 허용 — 사이클 53.1 row (model='cycle53.1-metrics-only') 자연 보존

ALTER TABLE daily_log_reports
    ADD COLUMN IF NOT EXISTS input_tokens INT NULL,
    ADD COLUMN IF NOT EXISTS output_tokens INT NULL,
    ADD COLUMN IF NOT EXISTS total_tokens INT NULL,
    ADD COLUMN IF NOT EXISTS latency_ms INT NULL,
    ADD COLUMN IF NOT EXISTS cost_estimate_usd DECIMAL(10, 6) NULL;
