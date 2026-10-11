-- llm_worker/ops/role.sql
-- 청산 AI 섀도 워커 전용 DB 역할(cycle446 — 사용자 결정 2026-10-11). 마이그레이션이 아니다
-- — supabase/migrations/ 밖에 두고, migration 050 적용 뒤 1회 psql 로 사람이 직접 실행한다.
--
-- journal_worker/ops/role.sql 과 같은 꼴(cycle412 선례).
--
-- 비밀번호는 psql 변수 llm_pw 하나로만 받는다(리터럴 비밀번호 0). 실행 예:
--   PW=$(openssl rand -hex 24)
--   psql "$DATABASE_URL" -v llm_pw="$PW" -f llm_worker/ops/role.sql
-- 변수에 먼저 담는 이유 둘 — ① 같은 값을 secrets/llm_worker.env 의 LLM_DATABASE_URL 에도
-- 옮겨야 한다 ② hex 는 DSN 을 깨는 `/`·`+`·`=`(base64 가 쓴다) 가 없다.
--
-- 두 번 실행해도 오류가 나지 않는다 — CREATE ROLE 은 존재 확인 뒤에만, GRANT·ALTER ROLE SET
-- 은 원래 멱등이다.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'llm_worker') THEN
        CREATE ROLE llm_worker WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END
$$;

-- $$ 안에는 psql 변수가 치환되지 않아 비밀번호는 DO 블록 밖에서 준다.
ALTER ROLE llm_worker WITH PASSWORD :'llm_pw';

-- 역할 수준 고정값 — 워커가 하루 한 번(08:15·재시도 08:35·08:55) 짧은 자동커밋 단문만 쓴다.
ALTER ROLE llm_worker SET statement_timeout = '5s';
ALTER ROLE llm_worker SET lock_timeout = '1s';
ALTER ROLE llm_worker SET idle_in_transaction_session_timeout = '5s';

-- 읽기만 — 입력 조립·사후 채움 대사에 쓴다. 워커가 이 표들을 바꿀 길은 없다.
GRANT SELECT ON stock_master_daily TO llm_worker;
GRANT SELECT ON trade_history TO llm_worker;
GRANT SELECT ON trade_journal_orders TO llm_worker;

-- 자기 표 둘 — SELECT·INSERT·UPDATE 만(DELETE 없음 — 사용자 결정 「히스토리도 남겨두자」 를
-- 권한으로 박는다. 영구 보존).
GRANT SELECT, INSERT, UPDATE ON exit_ai_evaluations TO llm_worker;
GRANT SELECT, INSERT, UPDATE ON exit_ai_runs TO llm_worker;

-- BIGSERIAL 시퀀스 — INSERT 가 nextval() 을 쓰려면 USAGE 가 필요하다.
-- exit_ai_runs 는 PK 가 run_date(DATE) 라 시퀀스가 없다.
GRANT USAGE ON SEQUENCE exit_ai_evaluations_id_seq TO llm_worker;

-- 그 밖의 표(positions·system_config·system_logs·strategy_config·kis_quote_accounts·
-- llm_buy_evaluations·pending_next_day_clear·trade_journal_stops·trade_journal_notes·
-- trade_journal_cursor 포함)는 전부 접근 0 — PUBLIC 기본 권한이 없으므로 아무것도 더
-- 주지 않는 것 자체가 거부다. 보유 목록·손절선·진입 ATR 은 G1(/api/balance/exit-lines)
-- 로만 읽는다(DB positions 를 열지 않는다 — 설계 §1.5).
