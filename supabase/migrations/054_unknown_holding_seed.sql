-- 054_unknown_holding_seed.sql
-- 신규 전략 'unknown'(비식별 보유) strategy_config 초기 등록(cycle461 ⑦-F1 안 U).
-- 사용자 결정 2026-10-10 「안 U = 전용 전략 unknown — 비중 0 · 항상 켜짐 · 매수 없음」 + 2026-10-15
-- 「구현 시작하자」. 출처 모를 보유(KIS 잔고에만 있는 종목)를 맡아 KRX 정규장에 청산만 한다.
-- enabled=true(항상 켜짐 — 끄면 그 보유의 청산 평가가 멈춘다), weight=0(예산 없음).
-- 청산 모드는 observe 로 시작한다(사용자 결정 ⑤ — 몇 주 관찰 뒤 enforce).

INSERT INTO strategy_config (strategy_id, enabled, weight, params)
VALUES ('unknown', true, 0, '{"unknown_exit_mode": "observe"}'::jsonb)
ON CONFLICT (strategy_id) DO NOTHING;
