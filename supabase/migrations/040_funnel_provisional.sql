-- 사이클 171 (2026-06-22) — strategy_funnel_snapshots 잠정(provisional) 플래그 컬럼
--
-- 배경 (자문 _workspace/domain_consult/cycle171_master_funnel_timing_redesign.md 의제 4):
-- funnel 은 순수 관찰성 + D-1 일봉 기반이라 장중 불변 → 전날 저녁 (16:20) 미리 생성하면
-- 운영자가 밤에 다음 영업일 후보를 확인 가능 (현재 09:30 개장 후 캡처는 늦음).
-- 단 "저녁에 본 후보" 와 "아침 확정 후보" 가 다를 수 있어 (08:46 마스터 델타로 빠지는 종목,
-- 사이클 174 인계) UI 에 "잠정/확정" 명시 필요 (자문 의제 9 반례 3).
--
-- is_provisional:
--   - TRUE  = 16:20 저녁 잠정 캡처 (전일 마스터 + 16:10 basics 기준, 아침 델타 미반영)
--   - FALSE = 09:30 자동 캡처 / 수동 trigger (현행 확정 캡처)
--
-- 매매 안전성: 관찰성 전용 컬럼. scanner/risk/order_engine/realtime/auth 무관.
-- additive (ADD COLUMN IF NOT EXISTS + NOT NULL DEFAULT FALSE) → 기존 row 자동 FALSE,
-- 장중에도 안전 (데이터 손실 0 / 락 최소). idempotent.

ALTER TABLE strategy_funnel_snapshots
  ADD COLUMN IF NOT EXISTS is_provisional BOOLEAN NOT NULL DEFAULT FALSE;
