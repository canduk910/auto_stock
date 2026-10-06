-- 046_trade_history_order_price.sql
-- cycle409 — 사용자 결정 10-04 Q4: 주문가 기록(슬리피지 원천).
-- 가산형: NULL 허용 칸 1개만. 기존 행·기존 칸의 의미 무변경.
--
-- trade_history.price 는 PENDING INSERT 때 주문가였다가 체결통보가 체결가로 덮는다.
-- order_price 는 PENDING INSERT 때 한 번만 쓰이고 체결 UPDATE 는 건드리지 않는다.
--   - 매수·매도 PENDING — 지정가 = 주문가, 시장가 = 주문 순간 현재가(호가가 아니다, 없으면 NULL).
--     매도 PENDING 의 price 는 매수가(장부 계약)라 주문가는 호출부가 따로 넘긴다.
--   - 체결통보 선행 보정 INSERT · 주문 동기화 INSERT · 이 칸 이전 행 = NULL.

ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS order_price NUMERIC NULL;

COMMENT ON COLUMN trade_history.order_price IS
    '주문가 — PENDING INSERT 때만 기록(지정가=주문가, 시장가=주문 순간 현재가). 체결 UPDATE 무접촉. 보정·동기화 행은 NULL (cycle409)';
