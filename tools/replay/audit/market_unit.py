"""시장 유닛 — 069500(KODEX 200) 일봉 → 체결일별 배수 m.

판정 식은 운영 ``src.engine.market_unit.classify`` 를 **그대로 부른다**(마지막 80개 종가 ·
SMA60(D−1) 위 · SMA60(D−1) > SMA60(D−21) · 엄격 부등호). 체결일 D 의 m = D 보다 앞선
가장 가까운 069500 봉까지의 종가로 판정한 값(운영 = 「직전 영업일 봉」).

fail-open 규칙(운영과 같음): 행 부족(< 80) · 직전 봉이 ``STALE_FALLBACK_MAX_CALENDAR_DAYS``(10일)
넘게 묵음 → m = NaN 으로 돌려준다. NaN 을 1.0 으로 읽을지는 호출자가 정한다(운영 = 1.0).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.engine import market_unit as _op  # noqa: E402  (운영 판정 그대로)

SOURCE_TICKER = _op.SOURCE_TICKER


def m_at_bars(closes: np.ndarray) -> np.ndarray:
    """봉 k 의 종가까지로 판정한 m(k). 판정 불가 = NaN. 운영 ``classify`` 를 봉마다 부른다."""
    out = np.full(len(closes), np.nan)
    vals = [float(x) for x in closes]
    for k in range(_op.MIN_ROWS - 1, len(vals)):
        cl, reason = _op.classify(vals[k - _op.MIN_ROWS + 1:k + 1])
        if cl is not None:
            out[k] = cl.m
    return out


def m_for_days(cal: pd.DatetimeIndex, bar_dates: pd.DatetimeIndex, closes: np.ndarray,
               stale_days: int = _op.STALE_FALLBACK_MAX_CALENDAR_DAYS) -> np.ndarray:
    """전역 달력의 날 D 마다 m(D) = m(D 보다 앞선 마지막 069500 봉). 없음·묵음 = NaN."""
    mk = m_at_bars(np.asarray(closes, dtype=float))
    bd = pd.DatetimeIndex(bar_dates)
    pos = bd.searchsorted(cal, side="left") - 1          # D 보다 엄격히 앞선 마지막 봉
    out = np.full(len(cal), np.nan)
    for i, p in enumerate(pos):
        if p < 0:
            continue
        if (cal[i] - bd[p]).days > stale_days:
            continue
        out[i] = mk[p]
    return out
