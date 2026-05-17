-- 사이클 7-A (2026-05-17): 보조 KIS 시세 수신 계좌 풀.
--
-- 매매/잔고/체결통보(H0STCNI0)는 메인 계좌 단일 보장. 본 테이블에 등록된 계좌는
-- 시세 수신 전용 — REST 시세성 호출 라운드로빈 + WebSocketPool(사이클 7-B/C) 용도.
--
-- 자금 안전 원칙:
--   - 본 계좌 등록은 시세 수신 한정. order.py / balance.py / 체결통보 구독은 영원히 메인 계좌만 사용.
--   - 코드 리뷰 시 보조 계좌 변수(label, account_id) 가 매매/잔고 함수로 전달되는지 확인.
--
-- app_secret 1차 평문 저장 (Supabase RLS 의존). 후속 사이클 KMS 암호화 보강 예정.
-- service_role / authenticated 역할 외에는 SELECT 차단 RLS 정책 권장 (운영 콘솔 설정).
--
-- 적용 보류 — 사용자 명시 지시 후 Supabase 콘솔에서 수동 실행 권장.
-- (마이그 023~025 동일 컨벤션)

CREATE TABLE IF NOT EXISTS kis_quote_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  label TEXT NOT NULL UNIQUE,
  app_key TEXT NOT NULL,
  app_secret TEXT NOT NULL,
  kis_env TEXT NOT NULL CHECK (kis_env IN ('real', 'vts')),
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kis_quote_accounts_active
  ON kis_quote_accounts (active) WHERE active = true;

COMMENT ON TABLE kis_quote_accounts IS
  '사이클 7-A (2026-05-17) — 보조 시세 수신 계좌 풀. 매매/체결통보는 메인 계좌 단일 보장 — 본 테이블의 계좌는 시세 only.';
COMMENT ON COLUMN kis_quote_accounts.app_secret IS
  '1차 평문 저장 (Supabase RLS 의존). 후속 사이클 KMS 암호화 보강 예정.';
COMMENT ON COLUMN kis_quote_accounts.label IS
  '운영자 식별 라벨 (UNIQUE). 예: "quote-1", "quote-2". 토큰 매니저 multi-account 키.';
COMMENT ON COLUMN kis_quote_accounts.kis_env IS
  '''real'' = 실전, ''vts'' = 모의. 운영 환경과 일치해야 함.';
COMMENT ON COLUMN kis_quote_accounts.active IS
  'false 면 시세 수신 풀에서 제외. WebSocketPool/라운드로빈은 active=true 만 사용.';
