-- 018_register_bull_flag_and_vcp.sql
-- 신규 전략 2종 strategy_config 초기 등록:
--   - bull_flag_breakout  (눌림목 돌파, 폴/플래그 + 측정된 이동 익절)
--   - vcp_breakout        (변동성 수축 돌파, 미네르비니식 VCP)
-- 모두 기본 비활성 (enabled=false, weight=0) — 검증 후 Settings에서 수동 활성화.
-- 011_register_donchian_swing.sql 패턴 동일.
--
-- params JSONB 는 빈 dict 로 등록 — 전략 클래스가 DEFAULT_PARAMS 와 merge 처리.
-- DB 에 params 를 비워두는 이유:
--   1) 신규 파라미터 추가 시 코드만 배포하면 자동 반영 (DB 갱신 불필요)
--   2) 운영자가 Settings 에서 일부 키만 override 했을 때 코드 디폴트가 진실의 원천

insert into strategy_config (strategy_id, enabled, weight, params)
values
  ('bull_flag_breakout', false, 0, '{}'::jsonb),
  ('vcp_breakout',       false, 0, '{}'::jsonb)
on conflict (strategy_id) do nothing;
