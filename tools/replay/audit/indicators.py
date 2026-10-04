"""지표 — 재현에 쓰는 식을 한 곳에. 각 식은 어느 운영/재현 코드와 같은지 적는다.

모든 함수는 인과적이다(인덱스 i 의 값은 i 까지의 봉만 본다). 「직전 N봉」 은 i 를 뺀 i−N..i−1 이다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray, *, first: str = "nan") -> np.ndarray:
    """TR[i] = max(h−l, |h−c[i−1]|, |l−c[i−1]|). ``first="nan"`` → TR[0]=NaN(cycle405) ·
    ``first="hl"`` → TR[0]=h−l(cycle391 ``nanmax``)."""
    n = len(c)
    tr = np.full(n, np.nan)
    if n == 0:
        return tr
    tr[1:] = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])
    if first == "hl":
        tr[0] = h[0] - l[0]
    return tr


def atr_sma(h, l, c, n: int = 14) -> np.ndarray:
    """TR 단순평균(첫 TR 제외) — 운영 donchian/VCP/BFB ``atr`` · cycle405 · cycle391 ``n14``."""
    return pd.Series(true_range(h, l, c)).rolling(n, min_periods=n).mean().to_numpy()


def atr_wilder(h, l, c, n: int = 20) -> np.ndarray:
    """Wilder(ewm alpha=1/n, adjust=False), 첫 TR = h−l — cycle391 ``atr20``."""
    return pd.Series(true_range(h, l, c, first="hl")).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def ema_ewm(c: np.ndarray, span: int) -> np.ndarray:
    """pandas ewm(span, adjust=False) — 전 구간 재귀(cycle391 ``e60``)."""
    return pd.Series(c).ewm(span=span, adjust=False).mean().to_numpy()


def ema_fir(c: np.ndarray, n: int) -> np.ndarray:
    """운영 ``_ema(closes[-n:])`` — 최근 n봉 창 안에서 첫 값으로 시작하는 EMA(k=2/(n+1)). cycle405 ``ema``."""
    k = 2.0 / (n + 1)
    w = np.empty(n)
    w[0] = (1 - k) ** (n - 1)
    for j in range(1, n):
        w[j] = k * (1 - k) ** (n - 1 - j)
    out = np.full(len(c), np.nan)
    if len(c) >= n:
        out[n - 1:] = np.convolve(c, w[::-1], mode="valid")
    return out


def prior_max(x: np.ndarray, n: int) -> np.ndarray:
    """직전 n봉 최댓값(i 제외) — 돌파선."""
    return pd.Series(x).shift(1).rolling(n, min_periods=n).max().to_numpy()


def prior_min(x: np.ndarray, n: int) -> np.ndarray:
    """직전 n봉 최솟값(i 제외) — 채널 저가."""
    return pd.Series(x).shift(1).rolling(n, min_periods=n).min().to_numpy()


def prior_mean(x: np.ndarray, n: int) -> np.ndarray:
    """직전 n봉 평균(i 제외) — 거래대금 배수 분모."""
    return pd.Series(x).shift(1).rolling(n, min_periods=n).mean().to_numpy()
