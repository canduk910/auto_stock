-- =====================================================================================
-- cycle392 — 다건 체결통보 매도의 실현손익 덮어쓰기: 과거 행 정정 초안
-- 작성: team-leader, 2026-10-02 07:0x KST
--
-- 🔴 이 파일은 실행되지 않았다. 실행 주체 = 메인 세션, 사용자 확인 뒤
--    (루트 CLAUDE.md 「여전히 승인이 필요한 것」 — DB UPDATE 는 되돌리기 어려운 운영 조치).
--
-- 대상 = 확정 3행. 모두 EC2 파일 로그(09-12~10-01)의 「매도 부분 체결」 줄과
-- DB 서명(profit_loss ÷ (price − 매수가) = 마지막 통보 수량, 정수)이 둘 다 맞았다.
--
--   주문          종목              전략                 통보                         기록(가격·손익)     정정(가격·손익)
--   0001637700   149950 아바텍      bull_flag_breakout   3@12,380 + 11@12,350         12,350 · −7,590     12,356.43 · −9,570
--   0000806100   054920 한컴위드    long_tail_volatility 2@4,830  + 7@4,825           4,825  · −1,855     4,826.11  · −2,375
--   0000501000   035760 CJ ENM      kojiro               1@36,150 + 4@36,100          36,100 · −13,200    36,110    · −16,450
--
--   매수가(장부 BUY 행 = 손익 역산값 일치): 아바텍 13,040 · 한컴위드 5,090 · CJ ENM 39,400
--   손익 정정 = Σ(체결가 − 매수가) × 체결수량
--     아바텍   3×(12,380−13,040) + 11×(12,350−13,040) = −1,980 − 7,590  = −9,570
--     한컴위드 2×(4,830−5,090)   +  7×(4,825−5,090)   =   −520 − 1,855  = −2,375
--     CJ ENM   1×(36,150−39,400) +  4×(36,100−39,400) = −3,250 − 13,200 = −16,450
--   가격 정정 = 체결 가중평균, 소수 둘째 자리 반올림(코드 시정과 같은 규칙)
--     172,990 / 14 = 12,356.428… → 12,356.43 · 43,435 / 9 = 4,826.111… → 4,826.11 · 180,550 / 5 = 36,110
--   과소 기록 합계 = −5,750원(장부 손익이 실제보다 5,750원 덜 나빴다)
--
-- 범위 밖(이 파일이 고치지 않는 것):
--   · 09-12 이전 행 — 파일 로그가 없어 DB 서명으로만 판별된다. 서명 0건(376 SELL 행 중).
--     매수 기준가가 장부 BUY 와 어긋난 79행(대부분 04~06월)은 서명 판별이 불가하므로
--     그 안에 다건 통보 주문이 섞였을 가능성은 배제하지 못한다. 근거 없이 고치지 않는다.
--   · daily_log_reports.metrics(JSONB) 의 그날 by_ticker_pnl 등 — 당시 리포트 스냅샷이라 손대지 않는다.
-- =====================================================================================


-- -------------------------------------------------------------------------------------
-- 0. 실행 시점
--    · trade_history 정정은 매매 메모리(daily_realized_pnl·손실 게이트)에 닿지 않는다 — 장중에도 무해.
--    · daily_performance 는 그날 21:30 정산의 recompute_daily_performance() 가 trade_history 에서
--      전 기간을 다시 계산하므로 21:30 **전**에 1~3 단계를 끝내면 따로 할 일이 없다.
--      21:30 을 넘겼거나 즉시 반영이 필요하면 5 단계(선택)를 실행한다.
--    · 20:00~21:35 창에서는 실행하지 않는다(21:30 정산과 겹치지 않게).
-- -------------------------------------------------------------------------------------


-- -------------------------------------------------------------------------------------
-- 1. 백업 (읽기 전용 — 먼저 실행해 결과를 파일로 남긴다)
--    EC2 에서: psql "<RDS DSN>" 으로 접속해 아래 두 \copy 를 먼저 실행한다(경로는 EC2 호스트 기준 절대경로).
-- -------------------------------------------------------------------------------------
-- \copy (SELECT * FROM trade_history WHERE id IN ('c030d3aa-a9bb-482b-9ed2-07c787761ad5','7ce67961-c9ea-415b-ab30-795985c4e690','7bf4492d-d181-4df0-a79d-4765ccd3896b')) TO '/home/ubuntu/auto_stock/backup_c392_trade_history.csv' CSV HEADER
-- \copy (SELECT * FROM daily_performance ORDER BY date, strategy) TO '/home/ubuntu/auto_stock/backup_c392_daily_performance.csv' CSV HEADER

SELECT id::text, ticker, ticker_name, trade_type, price, quantity, profit_loss, status, strategy, order_no,
       to_char(timestamp AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI:SS.US') AS ts_kst
  FROM trade_history
 WHERE id IN ('c030d3aa-a9bb-482b-9ed2-07c787761ad5',
              '7ce67961-c9ea-415b-ab30-795985c4e690',
              '7bf4492d-d181-4df0-a79d-4765ccd3896b')
 ORDER BY timestamp;
-- 기대(2026-10-02 07:0x 읽기 전용 조회 결과):
--   c030d3aa… 149950 SELL 12350 14 −7590  COMPLETED bull_flag_breakout   0001637700 2026-09-22 14:36:50.977631
--   7ce67961… 054920 SELL 4825   9 −1855  COMPLETED long_tail_volatility 0000806100 2026-09-28 10:52:33.862478
--   7bf4492d… 035760 SELL 36100  5 −13200 COMPLETED kojiro               0000501000 2026-10-01 09:44:19.055438

SELECT date, strategy, daily_realized_pnl, daily_profit_rate, cumulative_return_rate
  FROM daily_performance
 WHERE date IN ('2026-09-22', '2026-09-28', '2026-10-01')
   AND strategy IN ('bull_flag_breakout', 'long_tail_volatility', 'kojiro', 'total')
 ORDER BY date, strategy;
-- 기대(정정 전): 09-22 BFB −12,490 · total −25,170 / 09-28 LTV 1,190 · total −28,630 / 10-01 kojiro −13,200 · total −13,940


-- -------------------------------------------------------------------------------------
-- 2. 정정 (한 트랜잭션 — 세 행 중 하나라도 기대값과 다르면 전부 되돌린다)
--    WHERE 에 옛 값(price·profit_loss·quantity·order_no·status)을 모두 건다 → 두 번 실행해도 무해(멱등),
--    그 사이에 누가 값을 바꿨으면 0행이 되어 예외로 멈춘다.
-- -------------------------------------------------------------------------------------
BEGIN;

DO $$
DECLARE n integer;
BEGIN
  UPDATE trade_history
     SET price = 12356.43, profit_loss = -9570
   WHERE id = 'c030d3aa-a9bb-482b-9ed2-07c787761ad5'
     AND order_no = '0001637700' AND trade_type = 'SELL' AND status = 'COMPLETED'
     AND quantity = 14 AND price = 12350 AND profit_loss = -7590;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'cycle392 149950 정정 대상 % 행 (기대 1) — 중단', n; END IF;

  UPDATE trade_history
     SET price = 4826.11, profit_loss = -2375
   WHERE id = '7ce67961-c9ea-415b-ab30-795985c4e690'
     AND order_no = '0000806100' AND trade_type = 'SELL' AND status = 'COMPLETED'
     AND quantity = 9 AND price = 4825 AND profit_loss = -1855;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'cycle392 054920 정정 대상 % 행 (기대 1) — 중단', n; END IF;

  UPDATE trade_history
     SET price = 36110, profit_loss = -16450
   WHERE id = '7bf4492d-d181-4df0-a79d-4765ccd3896b'
     AND order_no = '0000501000' AND trade_type = 'SELL' AND status = 'COMPLETED'
     AND quantity = 5 AND price = 36100 AND profit_loss = -13200;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN RAISE EXCEPTION 'cycle392 035760 정정 대상 % 행 (기대 1) — 중단', n; END IF;
END $$;

COMMIT;


-- -------------------------------------------------------------------------------------
-- 3. 확인 (읽기 전용)
-- -------------------------------------------------------------------------------------
SELECT id::text, ticker, price, quantity, profit_loss, order_no
  FROM trade_history
 WHERE id IN ('c030d3aa-a9bb-482b-9ed2-07c787761ad5',
              '7ce67961-c9ea-415b-ab30-795985c4e690',
              '7bf4492d-d181-4df0-a79d-4765ccd3896b')
 ORDER BY timestamp;
-- 기대: 149950 12356.43 14 −9570 / 054920 4826.11 9 −2375 / 035760 36110 5 −16450


-- -------------------------------------------------------------------------------------
-- 4. 되돌리기 (필요할 때만) — 새 값이 그대로일 때만 옛 값으로
-- -------------------------------------------------------------------------------------
-- BEGIN;
-- UPDATE trade_history SET price = 12350, profit_loss = -7590
--  WHERE id = 'c030d3aa-a9bb-482b-9ed2-07c787761ad5' AND price = 12356.43 AND profit_loss = -9570;
-- UPDATE trade_history SET price = 4825, profit_loss = -1855
--  WHERE id = '7ce67961-c9ea-415b-ab30-795985c4e690' AND price = 4826.11 AND profit_loss = -2375;
-- UPDATE trade_history SET price = 36100, profit_loss = -13200
--  WHERE id = '7bf4492d-d181-4df0-a79d-4765ccd3896b' AND price = 36110 AND profit_loss = -16450;
-- COMMIT;
-- (그 뒤 daily_performance 는 다음 21:30 정산 또는 5 단계로 다시 맞춰진다)


-- -------------------------------------------------------------------------------------
-- 5. (선택) daily_performance 즉시 재계산 — 21:30 정산 전에 1~3 단계를 끝냈으면 불필요
--    DB 함수가 trade_history SELL profit_loss 합으로 전 기간을 다시 쓴다(매일 21:30 에 이미 도는 함수).
--    20:00~21:35 창에서는 실행하지 않는다.
-- -------------------------------------------------------------------------------------
-- SELECT recompute_daily_performance();
--
-- 확인:
-- SELECT date, strategy, daily_realized_pnl FROM daily_performance
--  WHERE date IN ('2026-09-22','2026-09-28','2026-10-01')
--    AND strategy IN ('bull_flag_breakout','long_tail_volatility','kojiro','total') ORDER BY date, strategy;
-- 기대(정정 후): 09-22 BFB −14,470 · total −27,150 / 09-28 LTV 670 · total −29,150 / 10-01 kojiro −16,450 · total −17,190
--   (10-01 total −17,190 = 그날 메모리 daily_realized_pnl 합과 같다 — 로그 분석 M1 의 「−13,940 vs −17,190」 해소)
--   daily_profit_rate·cumulative_return_rate 는 이 날짜 이후 전 행이 함께 바뀐다(TWR 연쇄 — 정상).
