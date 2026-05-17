-- 사이클 8 (2026-05-18): 매수 가드 4 모드 + 4 임계값 조정 — system_config 키 5개 사전 등록.
--
-- 배경: 사이클 2 매수 가드는 단일 HARD 분기. 5/17 사용자 실측 — regime=defensive
-- 단독으로 모든 전략 매수 차단(VIX 18.43/normal + FG 76.0/탐욕 정상 범위인데도).
-- 운영자 시야: "강제 매수 잠금이 너무 가혹함, 컨트롤 가능하게".
--
-- 4 모드:
--   - OFF: 가드 완전 비활성 (모든 시장 상황 매수 허용)
--   - WARN: 매수 허용 + WARNING 로그만 (감사용)
--   - SOFT: 매수 허용 + position_ratio × 0.5 (최소 1주)
--   - HARD: 완전 차단 (기존 동작, 기본값)
--
-- 4 임계값:
--   - buy_block_vix_threshold: VIX > 임계값 시 발동 (기본 25.0)
--   - buy_block_fg_high_threshold: fear_greed_score > 임계값 시 발동 (기본 85.0)
--   - buy_block_fg_low_threshold: fear_greed_score < 임계값 시 발동 (기본 15.0)
--   - buy_block_regime_defensive_enabled: regime=defensive 차단 ON/OFF (기본 true)
--
-- DB 우선 패턴 (J3 / 사이클 2 / 사이클 5 컨벤션). JSONB `{"value": ...}` 표준 형태.
-- 본 INSERT 는 멱등 — `ON CONFLICT (key) DO NOTHING`.
--
-- 적용 보류 — 사용자 명시 지시 후 Supabase 콘솔에서 수동 실행 권장.
-- (마이그 023~026 동일 컨벤션)

INSERT INTO system_config (key, value)
VALUES
  ('buy_block_mode', '{"value": "HARD"}'::jsonb),
  ('buy_block_vix_threshold', '{"value": 25.0}'::jsonb),
  ('buy_block_fg_high_threshold', '{"value": 85.0}'::jsonb),
  ('buy_block_fg_low_threshold', '{"value": 15.0}'::jsonb),
  ('buy_block_regime_defensive_enabled', '{"value": true}'::jsonb)
ON CONFLICT (key) DO NOTHING;

-- 기본값 의도:
--   - mode=HARD: 본 사이클 배포 후에도 현재 동작 회귀 완벽 보존.
--     운영자가 명시적으로 IntegrationToggleCard 에서 OFF/WARN/SOFT 선택 시에만 완화.
--   - 임계값 4종: 사이클 2 의 하드코딩 임계값(25/85/15/true) 동일 — 회귀 0.
--
-- 운영자 사용 가이드:
--   - 5/17 케이스(defensive 단독, VIX/FG 정상)는 mode=SOFT 또는
--     buy_block_regime_defensive_enabled=false 권장 (regime 가드만 끄고 VIX/FG 임계 유지).
--   - 진성 위기(VIX>30 + defensive) 시 HARD 유지.
--   - 평소 시장(neutral/aggressive)은 임계값 조정 불필요.
