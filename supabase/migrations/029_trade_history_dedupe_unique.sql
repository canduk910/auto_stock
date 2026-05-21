-- 사이클 30 (긴급, 2026-05-21) — trade_history 중복 INSERT 결함 (042700 사고) 영구 차단 안전망.
--
-- 배경:
-- - 2026-05-20 042700 trade_history 19건 중 15건 중복 (실거래 4건). 매매손익 8건 잡힘 (실거래 2건).
-- - `_sync_orders_to_db` 가 `get_today_buy_trades()` (ticker dedupe) 사용 →
--   같은 ticker 다른 order_no 가려져 신규 판정 → 무한 핑퐁.
-- - 코드 수정 (신규 `_for_sync` 함수) 완료. DB UNIQUE 제약은 영구 안전망.
--
-- 본 migration:
-- 1. `(ticker, order_no, trade_type)` 부분 UNIQUE 인덱스 추가.
--    - 부분 인덱스 조건: `order_no IS NOT NULL AND order_no != ''`
--    - NULL/빈 order_no (수동 매매 사전 등) 는 UNIQUE 제외 — 운영 호환성.
-- 2. 적용 전 반드시 중복 정리 (사이클 30 Phase 2 SQL 실행) 완료 필수.
--    중복 잔존 시 인덱스 생성 ERROR (`duplicate key value violates unique constraint`).
--
-- 사전 검증 (적용 전 실행 권장):
-- ```sql
-- SELECT ticker, order_no, trade_type, COUNT(*)
-- FROM trade_history
-- WHERE order_no IS NOT NULL AND order_no != ''
-- GROUP BY ticker, order_no, trade_type
-- HAVING COUNT(*) > 1;
-- ```
-- 0건 반환 시 안전. 1건 이상 시 Phase 2 DELETE 우선 처리.

CREATE UNIQUE INDEX IF NOT EXISTS uq_trade_history_ticker_order_no_type
    ON trade_history (ticker, order_no, trade_type)
    WHERE order_no IS NOT NULL AND order_no != '';

-- 의도: 같은 (ticker, order_no, trade_type) 페어가 2건 이상 INSERT 시 PG 거부 →
-- 코드 결함 재발 시 trade_history DB 레벨에서 즉시 차단 (애플리케이션 로직 회귀 보호).
COMMENT ON INDEX uq_trade_history_ticker_order_no_type IS
    '사이클 30 — 042700 핑퐁 사고 영구 안전망. (ticker, order_no, trade_type) UNIQUE. NULL/빈 order_no 는 제외 (수동 매매 호환).';
