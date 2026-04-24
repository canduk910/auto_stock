-- 다중 전략 지원을 위한 스키마 변경

-- 1. trade_history에 strategy 컬럼 추가
ALTER TABLE trade_history
    ADD COLUMN IF NOT EXISTS strategy VARCHAR(30) DEFAULT 'momentum';

CREATE INDEX IF NOT EXISTS idx_trade_history_strategy
    ON trade_history(strategy);

-- 2. daily_performance를 (date, strategy) 복합PK로 변경
--    기존 데이터에 strategy='total' 부여 후 PK 재설정
ALTER TABLE daily_performance
    ADD COLUMN IF NOT EXISTS strategy VARCHAR(30) DEFAULT 'total';

-- 기존 단일 date PK 제거 → (date, strategy) 복합PK로 변경
ALTER TABLE daily_performance
    DROP CONSTRAINT IF EXISTS daily_performance_pkey;

ALTER TABLE daily_performance
    ADD PRIMARY KEY (date, strategy);
