-- 049_ndx2x_riskoff_seed.sql
-- 신규 전략 'ndx2x_riskoff'(나스닥2배-위험회피) strategy_config 초기 등록(cycle443).
-- 사용자 결정 2026-10-11 "지금 구현 시작하자. 섀도 운영부터 하다가 자금배정할게."
-- 섀도 시작 — enabled=true(섀도 전략 켜짐 유지 규약, 루트 CLAUDE.md shadow_mode 항목),
-- weight=0, params.shadow_mode=true. BUY 순간 [shadow_buy] 만 남고 주문은 나가지 않는다.

INSERT INTO strategy_config (strategy_id, enabled, weight, params)
VALUES ('ndx2x_riskoff', true, 0, '{"shadow_mode": true}'::jsonb)
ON CONFLICT (strategy_id) DO NOTHING;
