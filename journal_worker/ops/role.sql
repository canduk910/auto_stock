-- journal_worker/ops/role.sql
-- 거래일지 워커 전용 DB 역할(사용자 결정 E1c). 마이그레이션이 아니다 — supabase/migrations/
-- 밖에 두고, migration 047 적용 뒤 1회 psql 로 사람이 직접 실행한다.
--
-- 이 사이클(cycle412)에서는 이 스크립트를 만들기만 하고 운영 DB 에는 실행하지 않는다.
--
-- 비밀번호는 psql 변수 journal_pw 하나로만 받는다(리터럴 비밀번호 0). 실행 예:
--   psql "$DATABASE_URL" -v journal_pw="$(openssl rand -base64 24)" -f journal_worker/ops/role.sql
--
-- 두 번 실행해도 오류가 나지 않는다 — CREATE ROLE 은 존재 확인 뒤에만, GRANT·ALTER ROLE SET
-- 은 원래 멱등이다.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'journal_worker') THEN
        CREATE ROLE journal_worker WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END
$$;

-- $$ 안에는 psql 변수가 치환되지 않아 비밀번호는 DO 블록 밖에서 준다.
ALTER ROLE journal_worker WITH PASSWORD :'journal_pw';

-- 역할 수준 고정값 — 워커가 로그 수확만 하는 짧은 트랜잭션이라 긴 잠금·대기를 허용하지 않는다.
ALTER ROLE journal_worker SET statement_timeout = '5s';
ALTER ROLE journal_worker SET lock_timeout = '1s';
ALTER ROLE journal_worker SET idle_in_transaction_session_timeout = '5s';

-- 읽기만 — trade_history·llm_buy_evaluations 는 워커의 대사(reconcile)·판단가 보강 입력일 뿐,
-- 워커가 매매 기록을 바꿀 길은 없다.
GRANT SELECT ON trade_history TO journal_worker;
GRANT SELECT ON llm_buy_evaluations TO journal_worker;

-- 거래일지 표 4개 — SELECT·INSERT·UPDATE 만(DELETE 없음, R8 사건·주문행은 지우지 않는다).
GRANT SELECT, INSERT, UPDATE ON trade_journal_orders TO journal_worker;
GRANT SELECT, INSERT, UPDATE ON trade_journal_stops TO journal_worker;
GRANT SELECT, INSERT, UPDATE ON trade_journal_notes TO journal_worker;
GRANT SELECT, INSERT, UPDATE ON trade_journal_cursor TO journal_worker;

-- BIGSERIAL 시퀀스 — INSERT 가 nextval() 을 쓰려면 USAGE 가 필요하다.
GRANT USAGE ON SEQUENCE trade_journal_orders_id_seq TO journal_worker;
GRANT USAGE ON SEQUENCE trade_journal_stops_id_seq TO journal_worker;
GRANT USAGE ON SEQUENCE trade_journal_notes_id_seq TO journal_worker;

-- 그 밖의 표(kis_quote_accounts·strategy_config·positions·system_config·system_logs·
-- pending_next_day_clear 포함)는 전부 접근 0 — PUBLIC 기본 권한이 없으므로 아무것도
-- 더 주지 않는 것 자체가 거부다. 대체 경로를 쓰게 되면 그때 이 파일에 GRANT 를 더한다.
