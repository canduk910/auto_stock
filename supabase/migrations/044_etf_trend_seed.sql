-- 044_etf_trend_seed.sql
-- 신규 전략 'etf_trend'(ETF 추세) strategy_config 초기 등록(cycle403).
-- 기본 비활성(enabled=false, weight=0) — 섀도(S1) 검증 후 수동 활성화.

INSERT INTO strategy_config (strategy_id, enabled, weight, params)
VALUES ('etf_trend', false, 0, '{}'::jsonb)
ON CONFLICT (strategy_id) DO NOTHING;
