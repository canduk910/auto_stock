-- 사이클 5 (2026-05-17): 외부 통합 토글 system_config 키 사전 등록.
--
-- DB 우선 / .env fallback 패턴. 본 INSERT 는 멱등 — `ON CONFLICT (key) DO NOTHING`.
-- 운영 .env (DKSTOCK_REGIME_ENABLED / KIS_MCP_ENABLED) 값이 진실이라면 이 row 들은
-- 생성 안 됨 (또는 false 로 생성). 운영자가 Settings UI 에서 토글 시 upsert 로
-- value 갱신.
--
-- 적용 보류 — 사용자 명시 지시 후 Supabase 콘솔에서 수동 실행 권장.
-- (사이클 2 023 / 024 동일 컨벤션)

INSERT INTO system_config (key, value)
VALUES
  ('dkstock_regime_enabled', '{"value": false}'::jsonb),
  ('kis_mcp_enabled', '{"value": false}'::jsonb)
ON CONFLICT (key) DO NOTHING;

-- 참고: auto_regime_adjust 는 사이클 2 023 마이그레이션에서 이미 추가 (기본 true).
-- 본 마이그레이션은 dkstock_regime_enabled + kis_mcp_enabled 만 신규 등록.
