-- trade_history에 종목명, KIS 주문번호 컬럼 추가
ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS ticker_name VARCHAR(50) DEFAULT '';
ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS order_no VARCHAR(20) DEFAULT '';
