-- Phase G2 (2026-05-13): stock_master ticker 형식 정규화 마이그레이션
--
-- 결함 진단:
-- - 운영 stock_master.ticker = 12자리 KIS pdno ("00000A000100" 형식)
-- - 운영 positions.ticker    = 6자리 KRX 단축코드 ("000100")
-- - stock_master.get(ticker)는 6자리로 조회 → 항상 miss
-- → Phase G NXT 사전 차단 (`_strategy_exchange_async`,
--   `_execute_next_day_clear`, `execute_sell` 사후 보강) 어제·오늘
--   실질적으로 무력화된 상태였음
--
-- 조치:
-- - 12자리 row 삭제 (next _boot eager_refresh 가 6자리로 정상 재생성)
-- - 적용 후 stock_master.ticker 는 6자리 KRX 단축코드만 보장

-- 1) 6자리 숫자 패턴이 아닌 모든 ticker row 삭제
--    (12자리 "00000A000100" 등 KIS pdno 형식 차단)
DELETE FROM stock_master
WHERE ticker !~ '^[0-9]{6}$';

-- 2) 검증: 남은 row 가 모두 6자리 숫자인지 (운영 안전성)
--    실패 시 마이그레이션 롤백 — DELETE 누락 행 즉시 감지
DO $$
DECLARE
  bad_count INT;
BEGIN
  SELECT COUNT(*) INTO bad_count
  FROM stock_master
  WHERE ticker !~ '^[0-9]{6}$';

  IF bad_count > 0 THEN
    RAISE EXCEPTION 'stock_master ticker 정규화 실패: 6자리 미준수 row % 건 잔존', bad_count;
  END IF;
END $$;
