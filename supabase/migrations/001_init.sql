-- trade_history (거래 내역)
CREATE TABLE IF NOT EXISTS trade_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT now(),
    ticker VARCHAR(20) NOT NULL,
    trade_type VARCHAR(4) NOT NULL CHECK (trade_type IN ('BUY', 'SELL')),
    price NUMERIC NOT NULL,
    quantity INTEGER NOT NULL,
    profit_loss NUMERIC DEFAULT 0,
    status VARCHAR(10) NOT NULL CHECK (status IN ('PENDING', 'COMPLETED', 'PARTIAL', 'CANCELLED'))
);

-- daily_performance (일일 실적)
CREATE TABLE IF NOT EXISTS daily_performance (
    date DATE PRIMARY KEY,
    total_asset NUMERIC NOT NULL,
    daily_profit_rate NUMERIC NOT NULL
);

-- system_logs (시스템 로그)
CREATE TABLE IF NOT EXISTS system_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT now(),
    log_level VARCHAR(10) NOT NULL,
    message TEXT NOT NULL
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_trade_history_ticker ON trade_history(ticker);
CREATE INDEX IF NOT EXISTS idx_trade_history_timestamp ON trade_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_system_logs_timestamp ON system_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(log_level);
