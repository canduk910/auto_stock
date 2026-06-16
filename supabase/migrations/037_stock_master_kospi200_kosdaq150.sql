-- 사이클 153 (2026-06-16) — stock_master 영역 is_kospi200 / is_kosdaq150 컬럼 신규
--
-- 사용자 결정 영속:
--   Q1=A KIS 공식 마스터 source (kospi200_apnt_cls_code != "" AND ksq150_nmix_yn == "Y")
--   Q2=A is_kospi200: bool | None + is_kosdaq150: bool | None 인자 (사이클 108 nxt_tradable 답습)
--
-- 근본 원인 (사이클 121 silent 결함):
--   donchian_swing.py::_scan_universe() 영역 KOSPI200/KOSDAQ150 필터 영역 완전 누락
--   = 사용자 보고 "코스피200 코스닥150의 합집합이 5개라는게 말이 안되는 것 같아" 영역 영구 영속
--
-- 영속 의무:
--   사이클 81 G-AST1 — raw JSONB 영역 영구 영속 보호 (신규 컬럼 = raw 영역 외부)
--   사이클 129 master_raw 영역 영구 영속 (변경 0)
--   사이클 146 upsert_master_raw nxt_tradable 명시 영속 답습 (is_kospi200/is_kosdaq150 동행 명시)
--   사이클 32 R4 보유/익일청산 절대 보호 (스캐너 매수 진입 전 영역 한정)
--   IF NOT EXISTS idempotent (사이클 129 134 패턴 답습)

ALTER TABLE stock_master
    ADD COLUMN IF NOT EXISTS is_kospi200 BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE stock_master
    ADD COLUMN IF NOT EXISTS is_kosdaq150 BOOLEAN NOT NULL DEFAULT FALSE;

-- 부분 인덱스 (KOSPI200/KOSDAQ150 종목 필터링 영역 성능 영구 영속)
CREATE INDEX IF NOT EXISTS idx_stock_master_is_kospi200
    ON stock_master (is_kospi200)
    WHERE is_kospi200 = TRUE;

CREATE INDEX IF NOT EXISTS idx_stock_master_is_kosdaq150
    ON stock_master (is_kosdaq150)
    WHERE is_kosdaq150 = TRUE;

COMMENT ON COLUMN stock_master.is_kospi200 IS
    '사이클 153 — KOSPI200 지수 편입 여부. KIS 마스터 영역 kospi200_apnt_cls_code != "" 영역 영구 영속.';
COMMENT ON COLUMN stock_master.is_kosdaq150 IS
    '사이클 153 — KOSDAQ150 지수 편입 여부. KIS 마스터 영역 ksq150_nmix_yn == "Y" 영역 영구 영속.';
