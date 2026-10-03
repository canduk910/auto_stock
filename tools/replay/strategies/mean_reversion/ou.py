"""평균회귀 연구 — OU 추정·ADF·z 순수 함수 (numpy 만).

지시서 = ``_workspace/design/2026-10-01_mean_reversion_handoff.md`` §3.3.

- ADF 는 ``statsmodels.tsa.stattools.adfuller(x, regression="c", autolag="AIC")`` 를
  numpy 로 다시 쓴 것이다(나중에 운영 leaf 로 옮길 때 statsmodels 가 없다 — §2-5).
  p 값만 MacKinnon 근사(``mackinnon_p``)를 쓴다. 같은 결과인지는
  ``tests/unit/replay/test_mr_ou.py`` 가 adfuller 와 대조한다.
- 모든 함수는 입력 창만 본다 — 창 밖(미래) 데이터를 받지 않는다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# macOS Accelerate BLAS 는 정상 입력의 matmul 에서도 0 나눗셈·넘침 FP 플래그를 세워 경고를 낸다
# (값은 정상 — adfuller 와 1e-13 일치). 선형대수 헬퍼에만 국소적으로 끈다.
_quiet = np.errstate(divide="ignore", over="ignore", invalid="ignore")

# §3.3-2 무효 조건 상수
ADF_P_MAX = 0.05
HALF_LIFE_MIN = 1.0
HALF_LIFE_MAX = 5.0

# MacKinnon (1994, 2010 개정) — regression="c", N=1 의 근사 계수.
# statsmodels.tsa.adfvalues 의 _tau_maxs/_tau_mins/_tau_smallps/_tau_largeps["c"][0] 와 같은 값.
_TAU_MAX_C = 2.74
_TAU_MIN_C = -18.83
_TAU_STAR_C = -1.61
_TAU_SMALLP_C = (2.1659, 1.4412, 0.038269)
_TAU_LARGEP_C = (1.7339, 0.93202, -0.12745, -0.010368)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def mackinnon_p(tau: float) -> float:
    """MacKinnon 근사 p 값 (상수항, 변수 1개)."""
    if tau > _TAU_MAX_C:
        return 1.0
    if tau < _TAU_MIN_C:
        return 0.0
    coef = _TAU_LARGEP_C if tau > _TAU_STAR_C else _TAU_SMALLP_C
    poly = sum(c * tau ** i for i, c in enumerate(coef))
    return _norm_cdf(poly)


@_quiet
def _ols(y: np.ndarray, X: np.ndarray):
    """계수·잔차제곱합·계수 표준오차."""
    beta, _res, rank, _sv = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    ssr = float(resid @ resid)
    n, k = X.shape
    return beta, ssr, n, k, rank


def _lagmat_in(xdiff: np.ndarray, maxlag: int) -> np.ndarray:
    """statsmodels ``lagmat(xdiff[:,None], maxlag, trim='both', original='in')`` 와 같다.

    열 0 = 원값(xdiff[t]), 열 j = xdiff[t-j]. 행 = maxlag .. len-1.
    """
    n = len(xdiff)
    cols = [xdiff[maxlag - j: n - j] for j in range(maxlag + 1)]
    return np.column_stack(cols)


@_quiet
def adf_c_aic(x: np.ndarray) -> "tuple[float, float, int]":
    """ADF(상수항, 시차 AIC 자동). 반환 = (통계량, p, 쓴 시차)."""
    x = np.asarray(x, dtype=float)
    nobs_all = x.shape[0]
    maxlag = int(math.ceil(12.0 * (nobs_all / 100.0) ** 0.25))
    maxlag = min(nobs_all // 2 - 1 - 1, maxlag)  # adfuller: ntrend=1 → nobs//2 - ntrend - 1
    if maxlag < 0:
        raise ValueError("sample too short")
    xdiff = np.diff(x)
    xdall = _lagmat_in(xdiff, maxlag)
    nobs = xdall.shape[0]
    xdall[:, 0] = x[-nobs - 1:-1]
    xdshort = xdiff[-nobs:]
    full = np.column_stack([np.ones(nobs), xdall])  # add_trend(prepend=True)
    best = None
    startlag = 2  # const + level
    for lag in range(startlag, startlag + maxlag + 1):
        _b, ssr, n, k, _r = _ols(xdshort, full[:, :lag])
        llf = -n / 2.0 * (math.log(2 * math.pi) + math.log(ssr / n) + 1.0)
        aic = -2.0 * llf + 2.0 * k
        cand = (aic, lag)
        if best is None or cand < best:
            best = cand
    bestlag = best[1] - startlag
    xdall = _lagmat_in(xdiff, bestlag)
    nobs = xdall.shape[0]
    xdall[:, 0] = x[-nobs - 1:-1]
    xdshort = xdiff[-nobs:]
    X = np.column_stack([xdall[:, :bestlag + 1], np.ones(nobs)])
    beta, ssr, n, k, _r = _ols(xdshort, X)
    sigma2 = ssr / (n - k)
    cov = sigma2 * np.linalg.inv(X.T @ X)
    tau = float(beta[0] / math.sqrt(cov[0, 0]))
    return tau, mackinnon_p(tau), bestlag


@dataclass(frozen=True)
class OUFit:
    """창 하나의 추정 결과. ``reason == "ok"`` 일 때만 신호를 낸다."""

    reason: str
    adf_p: float
    b: float
    a: float
    theta: float          # 회귀 속도(일)
    mu: float             # 중심
    sigma: float          # 연속시간 σ
    sigma_stat: float     # 정상분포 표준편차 = σ/√(2θ)
    half_life: float
    half_life_adj: float  # Kendall 편향 보정판


@_quiet
def ar1(x: np.ndarray) -> "tuple[float, float, float]":
    """X_{s+1} = a + b·X_s + e 의 OLS. 반환 (a, b, std(e))."""
    x0, x1 = x[:-1], x[1:]
    X = np.column_stack([np.ones(len(x0)), x0])
    beta, ssr, n, _k, _r = _ols(x1, X)
    resid_sd = math.sqrt(ssr / n)
    return float(beta[0]), float(beta[1]), resid_sd


def half_life_from_b(b: float) -> float:
    if not (0.0 < b < 1.0):
        return float("nan")
    theta = -math.log(b)
    return math.log(2.0) / theta


def kendall_adjust(b: float, T: int) -> float:
    """Kendall 근사 ``b_adj = b + (1+3b)/T``."""
    return b + (1.0 + 3.0 * b) / T


def fit_window(x: np.ndarray, *, with_adf: bool = True) -> OUFit:
    """창 하나(오름차순, 마지막 = t)로 OU 를 추정한다 (§3.3-2)."""
    x = np.asarray(x, dtype=float)
    nan = float("nan")
    if len(x) < 30 or not np.all(np.isfinite(x)):
        return OUFit("short", nan, nan, nan, nan, nan, nan, nan, nan, nan)
    p = nan
    if with_adf:
        try:
            _tau, p, _lag = adf_c_aic(x)
        except (ValueError, np.linalg.LinAlgError):
            return OUFit("adf_fail", nan, nan, nan, nan, nan, nan, nan, nan, nan)
    a, b, sd = ar1(x)
    T = len(x) - 1
    b_adj = kendall_adjust(b, T)
    hl_adj = half_life_from_b(b_adj)
    if not (0.0 < b < 1.0):
        return OUFit("b_range", p, b, a, nan, nan, nan, nan, nan, hl_adj)
    if sd <= 0:
        return OUFit("sigma", p, b, a, nan, nan, nan, nan, nan, hl_adj)
    # θ = −ln b 를 log1p 로 — b≈1 에서 1−b 의 자릿수 손실을 막는다
    theta = -math.log1p(b - 1.0)
    mu = a / (1.0 - b)
    one_minus_b2 = -math.expm1(2.0 * math.log(b))
    sigma = sd * math.sqrt(2.0 * theta / one_minus_b2)
    sigma_stat = sigma / math.sqrt(2.0 * theta)
    hl = math.log(2.0) / theta
    if with_adf and not (p < ADF_P_MAX):
        reason = "adf"
    elif not (HALF_LIFE_MIN <= hl <= HALF_LIFE_MAX):
        reason = "half_life"
    else:
        reason = "ok"
    return OUFit(reason, p, b, a, theta, mu, sigma, sigma_stat, hl, hl_adj)


def zscore(x_t: float, fit: OUFit) -> float:
    return (x_t - fit.mu) / fit.sigma_stat


@_quiet
def rolling_beta(logp: np.ndarray, logb: np.ndarray, t: int, window: int = 60) -> float:
    """t 의 β = 직전 ``window`` 봉(t-window .. t-1, 1봉 늦춘 창) 로그가격 수준 OLS 기울기."""
    lo = t - window
    if lo < 0:
        return float("nan")
    y = logp[lo:t]
    x = logb[lo:t]
    if not (np.all(np.isfinite(y)) and np.all(np.isfinite(x))):
        return float("nan")
    xm = x - x.mean()
    den = float(xm @ xm)
    if den <= 0:
        return float("nan")
    return float(xm @ (y - y.mean()) / den)


def efficiency_ratio(closes: np.ndarray, t: int, n: int = 20) -> float:
    """Kaufman ER — t 일 종가까지만 (§3.7)."""
    if t - n < 0:
        return float("nan")
    seg = closes[t - n: t + 1]
    den = float(np.sum(np.abs(np.diff(seg))))
    if den <= 0 or not np.isfinite(den):
        return float("nan")
    return abs(float(seg[-1] - seg[0])) / den
