"""cycle446 — 지표 함수 단위 검증(`lw/features.py`). 값 자체는 `src/engine/llm_features.py`
와 동등해야 한다(동등성 대조는 backend 쪽 `tests/unit/engine/test_cycle446_feature_parity.py`)."""
from __future__ import annotations

import pytest

from lw import features

pytestmark = pytest.mark.unit


def test_ema_insufficient_samples_is_none():
    assert features.ema([1, 2], 5) is None


def test_ema_seed_then_recurrence():
    vals = [1, 2, 3, 4, 5]
    got = features.ema(vals, 3)
    # seed = mean(1,2,3)=2, alpha=0.5 → 2 + 0.5*(4-2)=3 → 3 + 0.5*(5-3)=4
    assert got == pytest.approx(4.0)


def test_rsi_all_gains_is_100():
    closes = [10 + i for i in range(20)]
    assert features.rsi_wilder(closes, 14) == 100.0


def test_rsi_flat_is_50():
    closes = [10.0] * 20
    assert features.rsi_wilder(closes, 14) == 50.0


def test_atr_wilder_insufficient_is_none():
    assert features.atr_wilder([1, 2], [1, 2], [1, 2], 14) is None


def test_hv_annualized_zero_price_is_none():
    assert features.hv_annualized([0.0] * 25, 20) is None


def test_channel_returns_high_low_of_window():
    highs = list(range(1, 25))
    lows = [h - 1 for h in highs]
    hi, lo = features.channel(highs, lows, 20)
    assert hi == 24 and lo == 4


def test_compute_technicals_never_raises_on_garbage_input():
    out = features.compute_technicals([{"bad": "row"}, None, 123], current_price=0)
    assert isinstance(out, dict)
    assert out["ema_stack"] == "mixed"
    assert out["up_days_streak"] == 0


def test_compute_technicals_empty_bars_all_none():
    out = features.compute_technicals([], current_price=100)
    assert out["ema5_won"] is None
    assert out["rsi14"] is None
    assert out["atr14_won"] is None
    assert out["hv20_pct"] is None
