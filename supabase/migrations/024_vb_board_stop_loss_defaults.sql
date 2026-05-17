-- 사이클 3 (2026-05-17) — VB 보드별 손절 분리 디폴트 자동 복사.
--
-- 배경: 5/15 첫 자문의 VB code_review_notes 권고 — "보드별 개별 손절 파라미터 분리".
-- K값은 이미 보드별 분리(k_value_krx_main / k_value_nxt_pre / k_value_nxt_post)
-- 되어 있고, 사이클 1 PARAM_RANGES 에 등록 완료. 본 마이그는 손절도 같은 패턴으로
-- 확장 — 기존 stop_loss_rate 값을 보드별 키로 자동 복사해 운영자가 Settings
-- 갱신 없이도 기존 동작 회귀 0건 + 사후에 보드별 차별화 가능하도록 한다.
--
-- 멱등 가드:
--   - strategy_id='volatility_breakout' 만 대상
--   - params 에 stop_loss_rate 키 존재해야 함
--   - 보드별 키(stop_loss_main) 이미 있으면 skip — 운영자 차별화 보호
--
-- 적용 보류 (2026-05-17 시점): 코드 변경은 100% 하위 호환 (Phase A2 패턴과 동일).
-- 본 마이그 적용 전후 5/18 첫 발화 영향 0. 운영자가 보드별 차별화하고 싶을 때만
-- 본 마이그 적용 → Settings 에서 main/pre_nxt 별도 조정.
--
-- stop_loss_post_nxt 는 VB POST_NXT 미사용이라 제외 — 사이클 3-B 에서 재검토.

UPDATE strategy_config
SET params = params
    || jsonb_build_object(
        'stop_loss_main', (params->>'stop_loss_rate')::numeric,
        'stop_loss_pre_nxt', (params->>'stop_loss_rate')::numeric
    )
WHERE strategy_id = 'volatility_breakout'
  AND params ? 'stop_loss_rate'
  AND NOT (params ? 'stop_loss_main')
  AND NOT (params ? 'stop_loss_pre_nxt');

COMMENT ON TABLE strategy_config IS
  'VB 보드별 손절 분리 (사이클 3, 2026-05-17): stop_loss_main / stop_loss_pre_nxt 키 도입. '
  '기존 stop_loss_rate 단일 키 운영은 하위 호환 — VB.check_exit_signal 의 _get_stop_loss_for_board '
  '헬퍼가 보드별 키 부재 시 top-level stop_loss_rate 로 자동 fallback.';
