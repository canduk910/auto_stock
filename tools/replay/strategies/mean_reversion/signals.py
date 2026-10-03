"""평균회귀 — walk-forward 추정·신호 (순수 함수, numpy 만).

지시서 §3.3·§3.4. 각 종목·각 날짜 t 에 대해 t 이하 데이터만 쓴다.

- 재추정 = 전역 달력 인덱스 ``i % REEST_EVERY == 0`` 인 날(종목 공통 위상). 그날 종가까지 창 60.
- β_e = 직전 60봉(e-60..e-1) 로그가격 수준 OLS (1봉 늦춘 창). 가격 모드는 β = 0.
- 추정일 e 의 (β, μ, σ_stat) 는 다음 추정일 전날까지 그대로 쓴다. z_t = (X_t − μ)/σ_stat.
- 진입(``entries``)·관리(``manage``)는 그날 값만 받는 순수 함수 — 운영 leaf 로 옮길 모양.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .ou import fit_window, rolling_beta

WINDOW = 60
BETA_WINDOW = 60
REEST_EVERY = 5

REASON_CODES = {"ok": 0, "adf": 1, "half_life": 2, "b_range": 3, "sigma": 4, "short": 5,
                "adf_fail": 6, "halt": 7, "warmup": 8}


@dataclass
class SignalSeries:
    """종목 하나의 날짜별 신호 재료. 길이 = 달력 길이."""

    z: np.ndarray            # NaN = 그날 유효 추정 없음
    valid: np.ndarray        # bool — 그날 적용 중인 추정이 ok
    is_est: np.ndarray       # bool — 재추정일
    est_reason: np.ndarray   # int — 재추정일의 사유 코드(그 밖 -1)
    hl: np.ndarray
    hl_adj: np.ndarray
    sigma_stat: np.ndarray
    theta: np.ndarray
    adf_p: np.ndarray


def estimate_series(logp: np.ndarray, logb: "np.ndarray | None", halt: np.ndarray,
                    *, window: int = WINDOW, every: int = REEST_EVERY) -> SignalSeries:
    """walk-forward 추정. ``logb`` 가 None 이면 가격 모드(X = log P)."""
    n = len(logp)
    z = np.full(n, np.nan)
    valid = np.zeros(n, dtype=bool)
    is_est = np.zeros(n, dtype=bool)
    reason = np.full(n, -1, dtype=np.int8)
    hl = np.full(n, np.nan)
    hl_adj = np.full(n, np.nan)
    ss = np.full(n, np.nan)
    th = np.full(n, np.nan)
    pp = np.full(n, np.nan)
    est_days = [e for e in range(n) if e % every == 0]
    for k, e in enumerate(est_days):
        nxt = est_days[k + 1] if k + 1 < len(est_days) else n
        is_est[e] = True
        lo = e - window + 1
        if lo < 0 or (logb is not None and e - BETA_WINDOW < 0):
            reason[e] = REASON_CODES["warmup"]
            continue
        if logb is not None:
            beta = rolling_beta(logp, logb, e, BETA_WINDOW)
            if not math.isfinite(beta):
                reason[e] = REASON_CODES["short"]
                continue
            x = logp[lo:e + 1] - beta * logb[lo:e + 1]
        else:
            beta = 0.0
            x = logp[lo:e + 1]
        if halt[lo:e + 1].any() or not np.all(np.isfinite(x)):
            reason[e] = REASON_CODES["halt"]
            continue
        fit = fit_window(x)
        reason[e] = REASON_CODES[fit.reason]
        pp[e] = fit.adf_p
        hl_adj[e] = fit.half_life_adj
        if fit.reason != "ok":
            continue
        seg = slice(e, nxt)
        xs = logp[seg] - (beta * logb[seg] if logb is not None else 0.0)
        z[seg] = (xs - fit.mu) / fit.sigma_stat
        valid[seg] = np.isfinite(z[seg])
        hl[seg] = fit.half_life
        ss[seg] = fit.sigma_stat
        th[seg] = fit.theta
    return SignalSeries(z, valid, is_est, reason, hl, hl_adj, ss, th, pp)


# ── 진입 · 관리 (그날 값만 받는 순수 함수) ─────────────────────────────────────

def entry_z(z: float, sigma_stat: float, entry_z: float, exit_z: float, cost: float) -> bool:
    """z 경계 진입: z ≤ 진입 경계 ∧ 비용 조건 (|진입z| − |청산z|)·σ_stat > 왕복비용 (§3.6)."""
    if not (math.isfinite(z) and math.isfinite(sigma_stat)):
        return False
    if (abs(entry_z) - abs(exit_z)) * sigma_stat <= cost:
        return False
    return z <= entry_z


def entry_leung(z: float, bounds, z_prev: float = float("nan"), L: float = -2.0) -> bool:
    """Leung 진입 구간 [a*, d*] (표준화 z 단위). bounds=None(솔버 실패) → 진입 없음.

    이산 관측 보정: 연속 경로는 위에서 내려오며 d* 를 반드시 먼저 지나므로(정리 5.5 의 ν*),
    전날 z > d* 이고 오늘 L < z ≤ d* 이면 그날 d* 를 지난 것으로 보고 진입한다. 할인율이
    회귀 속도에 비해 작으면 [a*, d*] 가 거의 한 점으로 줄어 일봉에서 구간 안에 떨어질 일이 없다.
    """
    if bounds is None or not math.isfinite(z):
        return False
    a, d, _b = bounds
    if a <= z <= d:
        return True
    return math.isfinite(z_prev) and z_prev > d and L < z <= d


def manage(*, z: float, valid_today: bool, is_est_today: bool, held_days: int,
           hl_entry: float, z_entry: float, k_stop: float, exit_z: float,
           leung_bounds=None, leung_L: "float | None" = None) -> "str | None":
    """종가 기준 청산 판정 → 다음 날 시가 청산 사유 또는 None.

    우선순위 = 회귀 깨짐 > 재난(z) > Leung 손절 > 이익 > 타임스톱.
    가격 재난 손절(장중 저가)은 집행 층이 따로 본다.
    """
    if is_est_today and not valid_today:
        return "regime_break"
    if math.isfinite(z):
        if z <= z_entry - k_stop:
            return "disaster_z"
        if leung_L is not None and z <= leung_L:
            return "leung_stop"
        target = leung_bounds[2] if leung_bounds is not None else exit_z
        if z >= target:
            return "profit"
    if held_days > math.ceil(hl_entry * 2.0):
        return "timeout"
    return None
