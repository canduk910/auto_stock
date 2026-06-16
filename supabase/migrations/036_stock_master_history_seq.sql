-- 사이클 150 — stock_master_history seq=0/1 단일 정책 (SUPABASE 용량초과 시정)
-- 작성: 2026-06-16
-- 사용자 결정 Q1=A (직전본 1 row) + Q5=B (즉시 DROP).
--
-- 기존 영역 (사이클 84 migration 032):
--   PK = id BIGSERIAL (변경 시점마다 INSERT, 92K row 폭증)
--   trigger 영역 = UPDATE / TTL_REFRESH 모두 INSERT (일평균 +11.5K row)
--
-- 신규 영역 (사이클 150):
--   PK = (ticker, seq IN (0, 1)) — 직전본 1 row 단일
--   seq=0 = 최신본 / seq=1 = 직전본
--   UPDATE 시 = OLD seq=0 → seq=1 shift + 신규 seq=0 INSERT (raw 영역 변경 시에만)
--   TTL_REFRESH 영역 = trigger 미발화 (OLD.raw IS NOT DISTINCT FROM NEW.raw)
--
-- 영속 의무:
--   사이클 32 R4 universe guard 영속 (변경 0)
--   사이클 38 명문화 영속 (매매 hot path 무관)
--   사이클 81 G-AST1 raw JSONB 영속 (raw 영역 변경 0)
--   사이클 84 trigger 영역 재설계 영속

-- ============================================================================
-- 1. 기존 테이블 + trigger DROP (Q5=B 즉시 DROP, 92K row 폐기)
-- ============================================================================

DROP TRIGGER IF EXISTS stock_master_history_track ON stock_master;
DROP FUNCTION IF EXISTS stock_master_history_trigger();
DROP TABLE IF EXISTS stock_master_history CASCADE;

-- ============================================================================
-- 2. seq=0/1 단일 정책 테이블 재생성
-- ============================================================================

CREATE TABLE stock_master_history (
    ticker TEXT NOT NULL,
    seq INT NOT NULL CHECK (seq IN (0, 1)),  -- 0=최신본, 1=직전본
    change_type TEXT NOT NULL CHECK (change_type IN ('INSERT', 'UPDATE', 'DELETE')),
    raw JSONB,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ticker, seq)
);

-- 진단용 인덱스 단일 (PK 영역 영역 외 영역)
CREATE INDEX IF NOT EXISTS idx_smh_changed_at
    ON stock_master_history (changed_at DESC);

-- ============================================================================
-- 3. trigger 영역 재설계
-- ============================================================================
--
-- INSERT 영역: 신규 ticker (stock_master) → seq=0 INSERT
-- UPDATE 영역: raw 변경 시 → seq=0 → seq=1 shift + 신규 seq=0 INSERT (UPSERT)
-- UPDATE 영역: raw 미변경 (TTL_REFRESH) → trigger 미발화 (RETURN NEW 즉시)
-- DELETE 영역: ticker (stock_master) DELETE → seq=0/1 모두 삭제

CREATE OR REPLACE FUNCTION stock_master_history_trigger()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'INSERT') THEN
        -- 신규 ticker → seq=0 INSERT (직전본 영역 없음)
        INSERT INTO stock_master_history (ticker, seq, change_type, raw)
        VALUES (NEW.ticker, 0, 'INSERT', NEW.raw)
        ON CONFLICT (ticker, seq) DO UPDATE
        SET change_type = EXCLUDED.change_type,
            raw = EXCLUDED.raw,
            changed_at = now();
        RETURN NEW;

    ELSIF (TG_OP = 'UPDATE') THEN
        -- raw 영역 변경 시에만 trigger 발화 (TTL_REFRESH 영역 미발화)
        IF OLD.raw IS DISTINCT FROM NEW.raw THEN
            -- seq=0 → seq=1 shift (직전본 영역 갱신)
            -- 기존 seq=0 row 영역에서 ticker / raw / change_type 영역 복제
            INSERT INTO stock_master_history (ticker, seq, change_type, raw, changed_at)
            VALUES (NEW.ticker, 1, 'UPDATE', OLD.raw, now())
            ON CONFLICT (ticker, seq) DO UPDATE
            SET change_type = 'UPDATE',
                raw = EXCLUDED.raw,
                changed_at = now();

            -- 신규 seq=0 INSERT (최신본 영역 갱신)
            INSERT INTO stock_master_history (ticker, seq, change_type, raw, changed_at)
            VALUES (NEW.ticker, 0, 'UPDATE', NEW.raw, now())
            ON CONFLICT (ticker, seq) DO UPDATE
            SET change_type = 'UPDATE',
                raw = EXCLUDED.raw,
                changed_at = now();
        END IF;
        -- TTL_REFRESH 영역 (raw 미변경) = INSERT 0건 (사이클 150 핵심 영역)
        RETURN NEW;

    ELSIF (TG_OP = 'DELETE') THEN
        -- ticker (stock_master) DELETE → seq=0/1 모두 삭제 (PK CASCADE 영역)
        DELETE FROM stock_master_history WHERE ticker = OLD.ticker;
        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER stock_master_history_track
AFTER INSERT OR UPDATE OR DELETE ON stock_master
FOR EACH ROW EXECUTE FUNCTION stock_master_history_trigger();
