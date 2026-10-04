"""운용 전략 전수 점검(2026-10-05) — 전략 공용 재현 층.

사전 등록 정본 = ``_workspace/analysis/strategy_audit_20261005/prereg.frozen.md``(sha256 2d7e7b42…).
층 구성:
- ``config``     — 동결본 §0·§1 의 고정값(예산 C7 · 비용 C1 · 창 C2 · 씨앗 D-9)
- ``panel``      — 보관소(주식·ETF) + DB 추출본 → 종목별 일봉 배열(전역 달력 인덱스)
- ``market_unit``— 069500 → 체결일별 시장 유닛 m (운영 ``src.engine.market_unit.classify`` 그대로)
- ``indicators`` — ATR(단순·Wilder) · EMA(pandas·운영 FIR) · 직전 N봉 고가/저가
- ``bars``       — §1.4 같은 봉 체결 규칙 + P5 봉 안 경로(유리/불리) 한 봉 걷기
- ``sizing``     — 운영 ``calc_buy_quantity`` 를 그대로 부르는 어댑터(K축·ρ축·1주 폴백·시장 유닛)
- ``book``       — C7 단독 풀 한 계좌(정수 주 · 자기 평가액 복리 · 같은 날 순서 씨앗 16)
- ``judge``      — P1~P6 · L1 판정기 + 군집 부트스트랩 + R 슬리브(cycle391 판정판 정의)
- ``live``       — ``trade_history`` → 왕복 거래(D-1·D-2·D-4·D-7·D-8)

연구 전용: 운영 DB·KIS·KRX 호출 0(추출본 파일만 읽는다). ``src/`` 는 import 만 한다.
"""
