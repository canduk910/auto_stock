"""30년 6장세 — 낙폭 신호 D−1 규약 · 탐지 지연 계산 테스트."""
from __future__ import annotations

import os
import sys

import pytest

pytest.importorskip("scipy")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import y30_regime as R  # noqa: E402


def test_dd60_uses_previous_close_only():
    idx = pd.date_range("2001-01-01", periods=80, freq="D")
    c = pd.Series(100.0, index=idx)
    c.iloc[70] = 85.0                      # 70 일 종가가 −15%
    dd = R.dd60_series(c)
    assert dd.iloc[70] == pytest.approx(0.0)        # 그날 세션에는 아직 모른다
    assert dd.iloc[71] == pytest.approx(-0.15)      # 다음 세션에 안다
    assert np.isnan(dd.iloc[59])


def test_detect_lag_and_already_flag():
    arr = np.array([False, False, False, True, True, False])
    c = np.arange(6, dtype=float)
    assert R.detect(arr, 1, 5, c) == (2, 3, False)
    arr2 = np.array([False, True, False, False, True, False])
    assert R.detect(arr2, 1, 5, c) == (3, 4, True)
    assert R.detect(np.zeros(6, bool), 1, 5, c) == (None, None, False)
