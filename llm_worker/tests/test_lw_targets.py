"""cycle446 — 대상 선정(`lw/targets.py`, 설계 §2.1)."""
from __future__ import annotations

from datetime import date

import pytest

from lw import targets

pytestmark = pytest.mark.unit

_BAR = date(2026, 10, 13)


def _item(**kw):
    base = {"strategy_id": "donchian_swing", "ticker": "005930", "quantity": 10,
            "buy_date": "2026-10-10", "order_no": "123"}
    base.update(kw)
    return base


def test_select_targets_allows_known_strategies():
    items = [_item(strategy_id=s) for s in
             ("donchian_swing", "kojiro", "vcp_breakout", "bull_flag_breakout", "etf_trend")]
    out = targets.select_targets(items, bar_date=_BAR)
    assert len(out) == 5


def test_select_targets_excludes_unlisted_strategies():
    items = [_item(strategy_id=s) for s in ("momentum", "volatility_breakout", "long_tail_volatility",
                                             "ndx2x_riskoff")]
    out = targets.select_targets(items, bar_date=_BAR)
    assert out == []


def test_select_targets_excludes_buy_date_after_bar_date():
    items = [_item(buy_date="2026-10-14")]  # bar_date 뒤 매수 — 아직 장 마감을 안 넘김
    out = targets.select_targets(items, bar_date=_BAR)
    assert out == []


def test_select_targets_allows_buy_date_equal_bar_date():
    items = [_item(buy_date=str(_BAR))]
    out = targets.select_targets(items, bar_date=_BAR)
    assert len(out) == 1


def test_select_targets_excludes_zero_or_negative_quantity():
    items = [_item(quantity=0), _item(quantity=-1)]
    out = targets.select_targets(items, bar_date=_BAR)
    assert out == []


def test_select_targets_skips_malformed_items_without_raising():
    items = [None, 123, {"strategy_id": "donchian_swing"}, _item()]
    out = targets.select_targets(items, bar_date=_BAR)
    assert len(out) == 1


def test_select_targets_handles_empty_input():
    assert targets.select_targets([], bar_date=_BAR) == []
    assert targets.select_targets(None, bar_date=_BAR) == []
