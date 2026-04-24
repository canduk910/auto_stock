-- 전략 설정 영속화 테이블
CREATE TABLE IF NOT EXISTS strategy_config (
    strategy_id VARCHAR(30) PRIMARY KEY,
    enabled BOOLEAN DEFAULT TRUE,
    weight NUMERIC DEFAULT 0.5,
    params JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT now()
);
