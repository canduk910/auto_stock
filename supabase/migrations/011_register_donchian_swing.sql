-- 011_register_donchian_swing.sql
-- 신규 전략 'donchian_swing' (20일 신고가 스윙) strategy_config 초기 등록.
-- 기본 비활성 (enabled=false, weight=0) — 검증 후 수동 활성화.

insert into strategy_config (strategy_id, enabled, weight, params)
values ('donchian_swing', false, 0, '{}'::jsonb)
on conflict (strategy_id) do nothing;
