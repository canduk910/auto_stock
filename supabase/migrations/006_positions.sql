-- 포지션(보유종목) 영속화 테이블
CREATE TABLE IF NOT EXISTS positions (
    ticker VARCHAR(10) PRIMARY KEY,
    ticker_name VARCHAR(50) DEFAULT '',
    buy_price INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    order_no VARCHAR(20) DEFAULT '',
    strategy_id VARCHAR(30) NOT NULL,
    buy_date DATE NOT NULL,
    high_since_buy INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT now()
);
