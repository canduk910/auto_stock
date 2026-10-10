"""cycle431 — `StrategyBase.on_scale_event` 가격 차원 스탬프 이동 회귀.

사용자 결정 2026-10-10(안1). 가격 차원 선언(`_PRICE_DIM_SIMPLE_ATTRS` ·
`_PRICE_DIM_BOARD_ATTRS` · `_PRICE_DIM_NESTED_ATTRS`)에 따라 `/r` 로만 옮기고,
선언 밖 속성(거래량·무차원·구조)은 손대지 않는지 확인한다.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.engine.strategy_base import StrategyBase

pytestmark = pytest.mark.unit


class _Stub(StrategyBase):
    """price-dim 선언만 가진 최소 StrategyBase 서브클래스."""

    _PRICE_DIM_SIMPLE_ATTRS = ("_entry_atr", "_stop_floor")
    _PRICE_DIM_BOARD_ATTRS = ("_prev_price_board",)
    _PRICE_DIM_NESTED_ATTRS = {"_candidates": ("prev_close", "atr")}

    def __init__(self):
        self.config = SimpleNamespace(strategy_id="stub")
        self._entry_atr = {"001390": 1000.0}
        self._stop_floor = {"001390": 9500, "002222": 8000}
        self._prev_price_board = {"001390": {"main": 10_000, "pre_nxt": 10_050}}
        self._candidates = {"001390": {"prev_close": 10_000, "atr": 500, "stage": 3, "name": "X"}}
        self._untouched_volume = {"001390": 1000}  # 선언 안 됨 — 손대지 않는다

    async def prepare(self, *, as_of=None):  # pragma: no cover — 미사용
        return None

    def check_buy_signal(self, *a, **kw):  # pragma: no cover
        return None

    def check_exit_signal(self, *a, **kw):  # pragma: no cover
        return None

    def calc_buy_quantity(self, *a, **kw):  # pragma: no cover
        return 0


def test_on_scale_event_divides_simple_attrs():
    s = _Stub()
    s.on_scale_event("001390", 10.0)
    assert s._entry_atr["001390"] == pytest.approx(100.0)
    assert s._stop_floor["001390"] == pytest.approx(950.0)
    assert s._stop_floor["002222"] == 8000  # 다른 종목은 무접촉


def test_on_scale_event_divides_board_nested_values():
    s = _Stub()
    s.on_scale_event("001390", 10.0)
    assert s._prev_price_board["001390"]["main"] == pytest.approx(1_000.0)
    assert s._prev_price_board["001390"]["pre_nxt"] == pytest.approx(1_005.0)


def test_on_scale_event_divides_only_declared_nested_keys():
    s = _Stub()
    s.on_scale_event("001390", 10.0)
    assert s._candidates["001390"]["prev_close"] == pytest.approx(1_000.0)
    assert s._candidates["001390"]["atr"] == pytest.approx(50.0)
    # 선언 밖 키(stage·name) 는 그대로 — 범주 오염 금지
    assert s._candidates["001390"]["stage"] == 3
    assert s._candidates["001390"]["name"] == "X"


def test_on_scale_event_does_not_touch_undeclared_attrs():
    s = _Stub()
    s.on_scale_event("001390", 10.0)
    assert s._untouched_volume["001390"] == 1000


def test_on_scale_event_noop_for_zero_or_negative_r():
    s = _Stub()
    s.on_scale_event("001390", 0.0)
    assert s._entry_atr["001390"] == 1000.0
    s.on_scale_event("001390", -1.0)
    assert s._entry_atr["001390"] == 1000.0


def test_on_scale_event_never_raises_on_internal_error(monkeypatch):
    s = _Stub()
    # 선언된 속성을 깨뜨려 내부 예외를 유도 — never-raise 계약 확인
    s._entry_atr = MagicMock()
    s._entry_atr.__contains__ = MagicMock(side_effect=RuntimeError("boom"))
    s.on_scale_event("001390", 10.0)  # 예외가 새지 않는다


def test_default_strategy_has_empty_price_dim_declarations():
    """선언 없는 전략(기본값) — on_scale_event 호출이 안전한 no-op."""

    class _Bare(StrategyBase):
        def __init__(self):
            self.config = SimpleNamespace(strategy_id="bare")
            self._whatever = {"001390": 100}

        async def prepare(self, *, as_of=None):
            return None

        def check_buy_signal(self, *a, **kw):
            return None

        def check_exit_signal(self, *a, **kw):
            return None

        def calc_buy_quantity(self, *a, **kw):
            return 0

    b = _Bare()
    b.on_scale_event("001390", 10.0)
    assert b._whatever["001390"] == 100
