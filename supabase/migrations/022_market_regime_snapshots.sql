-- 022_market_regime_snapshots.sql
-- 사이클 2 (2026-05-17): 시장 레짐 일일 스냅샷
--
-- dkstock.cloud `/api/macro/macro-cycle` + `/api/macro/sentiment` 응답을 매일 _boot
-- (07:50) 시점에 1행 저장한다. 운영자가 사후 회고/디버깅/Grafana 분석에 사용.
--
-- 적용: 운영 활성화(DKSTOCK_REGIME_ENABLED=true) 전에 Supabase 콘솔에서 실행.
--       활성화 전이라도 INSERT 코드는 try/except 로 graceful 처리되므로 무해.

CREATE TABLE IF NOT EXISTS market_regime_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_date DATE NOT NULL,
    regime TEXT NOT NULL,                  -- defensive / neutral / aggressive
    regime_desc TEXT,
    cycle_phase TEXT,                       -- expansion / contraction
    vix NUMERIC(8, 2),
    fear_greed_score NUMERIC(5, 2),
    buffett_ratio NUMERIC(8, 2),
    raw_response JSONB NOT NULL,            -- macro-cycle + sentiment 원본 (감사 추적)
    computed_cash_usage_ratio NUMERIC(4, 3),
    buy_blocked BOOLEAN NOT NULL,
    block_reason TEXT,                      -- "regime=defensive" / "vix>25" / "fear_greed>85" / "fear_greed<15"
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_market_regime_date
    ON market_regime_snapshots (snapshot_date DESC);

COMMENT ON TABLE market_regime_snapshots IS
    '사이클 2 (2026-05-17): dkstock.cloud 매크로 일일 스냅샷. _boot 시점 1행. 매수 가드 + cash_usage_ratio 자동 조정 결과 영구 기록.';

COMMENT ON COLUMN market_regime_snapshots.regime IS
    'defensive(현금 비중 권고) / neutral / aggressive. dkstock.cloud regime 값 원본.';

COMMENT ON COLUMN market_regime_snapshots.buy_blocked IS
    '복합 임계 OR: regime=defensive OR vix>25 OR fear_greed>85 OR fear_greed<15. true 시 _boot 다음 사이클 동안 모든 전략 매수 차단.';

COMMENT ON COLUMN market_regime_snapshots.computed_cash_usage_ratio IS
    '자동 조정 결과 (auto_regime_adjust=true 시). clamp((100 - cash_min) / 100, 0.0, 1.0).';
