-- 사이클 84 — stock_master 변경기록 추적 테이블 (Q1=B, Q5=B, Q6=A, Q7=B 90일, Q8=A)
-- 작성: 2026-06-09

CREATE TABLE IF NOT EXISTS stock_master_history (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    change_type TEXT NOT NULL CHECK (change_type IN ('INSERT', 'UPDATE', 'DELETE', 'TTL_REFRESH')),
    before_raw JSONB,
    after_raw JSONB,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_smh_ticker_changed_at
    ON stock_master_history (ticker, changed_at DESC);

CREATE INDEX IF NOT EXISTS idx_smh_changed_at
    ON stock_master_history (changed_at DESC);

-- trigger 함수: INSERT/UPDATE/DELETE 각 케이스 분기
-- UPDATE 시 raw 가 동일하면 TTL_REFRESH, 변경되면 UPDATE
CREATE OR REPLACE FUNCTION stock_master_history_trigger()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'INSERT') THEN
        INSERT INTO stock_master_history (ticker, change_type, before_raw, after_raw)
        VALUES (NEW.ticker, 'INSERT', NULL, NEW.raw);
        RETURN NEW;
    ELSIF (TG_OP = 'UPDATE') THEN
        IF OLD.raw IS DISTINCT FROM NEW.raw THEN
            INSERT INTO stock_master_history (ticker, change_type, before_raw, after_raw)
            VALUES (NEW.ticker, 'UPDATE', OLD.raw, NEW.raw);
        ELSE
            INSERT INTO stock_master_history (ticker, change_type, before_raw, after_raw)
            VALUES (NEW.ticker, 'TTL_REFRESH', OLD.raw, NEW.raw);
        END IF;
        RETURN NEW;
    ELSIF (TG_OP = 'DELETE') THEN
        INSERT INTO stock_master_history (ticker, change_type, before_raw, after_raw)
        VALUES (OLD.ticker, 'DELETE', OLD.raw, NULL);
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER stock_master_history_track
AFTER INSERT OR UPDATE OR DELETE ON stock_master
FOR EACH ROW EXECUTE FUNCTION stock_master_history_trigger();
