-- Phase G (2026-05-11) — 종목 마스터 캐시.
-- KIS CTPF1002R 응답에서 파생된 NXT 거래가능 여부를 24h TTL 로 캐시한다.
-- 익일 청산/거래소 라우팅 사전 차단에 사용.

CREATE TABLE IF NOT EXISTS stock_master (
    ticker         TEXT PRIMARY KEY,
    name           TEXT NOT NULL DEFAULT '',
    excg_dvsn_cd   TEXT NOT NULL DEFAULT '',
    nxt_tradable   BOOLEAN NOT NULL,
    krx_halted     BOOLEAN NOT NULL DEFAULT FALSE,
    admin_item     BOOLEAN NOT NULL DEFAULT FALSE,
    raw            JSONB NOT NULL DEFAULT '{}'::jsonb,
    refreshed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE stock_master IS
    'KIS CTPF1002R 응답 캐시. nxt_tradable 사전 판별용 (24h TTL).';
COMMENT ON COLUMN stock_master.nxt_tradable IS
    '(cptt_trad_tr_psbl_yn==Y) AND (nxt_tr_stop_yn==N)';
COMMENT ON COLUMN stock_master.refreshed_at IS
    'CTPF1002R 마지막 갱신 시각. 24h 초과 시 stale 로 판정.';

-- refreshed_at 정렬 인덱스 (eager 갱신 시 stale 일괄 추출에 사용)
CREATE INDEX IF NOT EXISTS idx_stock_master_refreshed
    ON stock_master (refreshed_at);
