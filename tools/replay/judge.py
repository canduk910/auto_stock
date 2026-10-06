"""재현 틀 — 판정 층 (블록 부트스트랩 · 기간 분할 · ER 삼분위).

블록 = (종목, 진입 주) — 같은 종목·같은 주의 거래는 함께 뽑힌다(지시서 §3.6).
"""
from __future__ import annotations

import numpy as np

# macOS Accelerate BLAS 의 matmul 가짜 FP 경고(값은 정상)를 이 헬퍼들에서만 끈다.
_quiet = np.errstate(divide="ignore", over="ignore", invalid="ignore")


def cluster_ids(tickers: np.ndarray, week: np.ndarray) -> np.ndarray:
    keys = np.char.add(np.char.add(tickers.astype(str), "|"), week.astype(str))
    _u, inv = np.unique(keys, return_inverse=True)
    return inv


@_quiet
def bootstrap_mean(values: np.ndarray, clusters: np.ndarray, *, n_boot: int = 2000,
                   seed: int = 20261001, q: float = 0.05) -> "tuple[float, float, float]":
    """군집 부트스트랩 평균의 (점추정, 하한 q, 상한 1−q)."""
    if len(values) == 0:
        return float("nan"), float("nan"), float("nan")
    ncl = clusters.max() + 1
    s = np.bincount(clusters, weights=values, minlength=ncl)
    cnt = np.bincount(clusters, minlength=ncl).astype(float)
    rng = np.random.default_rng(seed)
    w = rng.multinomial(ncl, np.full(ncl, 1.0 / ncl), size=n_boot).astype(float)
    means = (w @ s) / np.maximum(w @ cnt, 1e-12)
    return float(values.mean()), float(np.quantile(means, q)), float(np.quantile(means, 1 - q))


@_quiet
def bootstrap_diff(va: np.ndarray, ca: np.ndarray, vb: np.ndarray, cb: np.ndarray, *,
                   n_boot: int = 2000, seed: int = 20261001, q: float = 0.05):
    """mean(a) − mean(b) 군집 부트스트랩. ``ca``·``cb`` 는 같은 군집 공간(공통 인덱스)."""
    if len(va) == 0 or len(vb) == 0:
        return float("nan"), float("nan"), float("nan")
    ncl = int(max(ca.max(), cb.max()) + 1)
    sa = np.bincount(ca, weights=va, minlength=ncl)
    na = np.bincount(ca, minlength=ncl).astype(float)
    sb = np.bincount(cb, weights=vb, minlength=ncl)
    nb = np.bincount(cb, minlength=ncl).astype(float)
    rng = np.random.default_rng(seed)
    w = rng.multinomial(ncl, np.full(ncl, 1.0 / ncl), size=n_boot).astype(float)
    d = (w @ sa) / np.maximum(w @ na, 1e-12) - (w @ sb) / np.maximum(w @ nb, 1e-12)
    return float(va.mean() - vb.mean()), float(np.quantile(d, q)), float(np.quantile(d, 1 - q))


def split_index(n_days: int, front: float = 0.6) -> int:
    """앞 60% 의 끝(배타) 인덱스."""
    return int(np.floor(n_days * front))


def er_terciles(er: np.ndarray, cut: int) -> "tuple[float, float]":
    """ER 삼분위 경계 — 앞 기간(``[:cut]``)만으로 정한다 (§3.7 룩어헤드 금지)."""
    v = er[:cut]
    v = v[np.isfinite(v)]
    return float(np.quantile(v, 1 / 3)), float(np.quantile(v, 2 / 3))


def er_bucket(er: np.ndarray, bounds: "tuple[float, float]") -> np.ndarray:
    lo, hi = bounds
    out = np.full(len(er), -1, dtype=int)
    f = np.isfinite(er)
    out[f & (er <= lo)] = 0
    out[f & (er > lo) & (er <= hi)] = 1
    out[f & (er > hi)] = 2
    return out
