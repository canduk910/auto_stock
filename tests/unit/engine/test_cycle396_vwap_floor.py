"""cycle396 — 매도 장부 가격(체결 가중평균)은 원 단위 절사한 정수다.

사용자 요청(2026-10-02): 「손익계산 시 소수점 표시되는 사례가 있어. 9/28 054920 종목이야.
소수점은 절사하도록 수정해줄래?」 — 054920 한컴위드 주문 `0000806100` 2@4,830 + 7@4,825 의
장부 가격이 cycle392 규약(소수 둘째 자리 반올림)으로 4,826.11 이 되어 화면에 소수가 보였다.

계약 (`src/engine/order_engine.py::_vwap_floor(value, qty, fallback)`)
- 반환 = Σ(가격×수량) ÷ Σ수량 을 **원 단위 내림**한 `int` — `float` 이면 `36110.0` 처럼
  DB 바인딩·로그에 소수 흔적이 남으므로 정수형이어야 한다
- 반올림·올림 금지 — 100.005 → 100, 4,826.99… 도 4,826
- `qty <= 0` 이면 `fallback` 그대로(cycle392 폴백 유지)
- 손익(`book_pnl`)은 정수 증분 합이라 이 함수와 무관하다
"""
from __future__ import annotations

import pytest

import src.engine.order_engine as oe


def _fn():
    fn = getattr(oe, "_vwap_floor", None)
    assert fn is not None, "`order_engine._vwap_floor` 가 없다 — 가중평균 절사 헬퍼(cycle396)"
    return fn


@pytest.mark.parametrize(
    ("fills", "expected"),
    [
        ([(1, 36_150), (4, 36_100)], 36_110),   # 10-01 CJ ENM 035760 — 나누어떨어짐
        ([(2, 4_830), (7, 4_825)], 4_826),      # 09-28 054920 한컴위드 — 4,826.11 → 4,826
        ([(3, 12_380), (11, 12_350)], 12_356),  # 09-22 149950 아바텍 — 12,356.43 → 12,356
        ([(199, 100), (1, 101)], 100),          # 100.005 → 100 (반올림 아님)
        ([(2, 101), (1, 100)], 100),            # 302/3 = 100.67 → 100 (반올림·올림 아님)
        ([(5, 36_100)], 36_100),                # 단일 통보 = 체결가 그대로
    ],
)
def test_vwap_floor_when_weighted_average_has_fraction_then_truncates_to_int(fills, expected):
    value = sum(q * p for q, p in fills)
    qty = sum(q for q, _ in fills)
    got = _fn()(value, qty, fills[-1][1])
    assert got == expected, f"{fills} → {got!r} (기대 {expected})"
    assert type(got) is int, f"{fills} → {got!r} 는 {type(got).__name__} — int 여야 한다"


@pytest.mark.parametrize("qty", [0, -3])
def test_vwap_floor_when_qty_not_positive_then_returns_fallback(qty):
    assert _fn()(180_550, qty, 36_100) == 36_100
