"""Leung & Li (2015) 최적 진입·청산 경계 — 연구 전용(scipy).

문헌 = Leung, T. & Li, X. (2015) "Optimal Mean Reversion Trading with Transaction Costs and
Stop-Loss Exit", IJTAF 18(3). arXiv:1411.5062v3. 식 번호는 그 판본을 따른다.

모형: dX = μ(θ − X)dt + σ dB (문헌 표기 — μ = 회귀 속도, θ = 중심).
- 무손절판: 청산 b* (정리 4.2, 식 4.3) · 진입 d* (정리 4.5, 식 4.11)
- 손절판(손절 수준 L): 청산 b*_L (정리 5.1, 식 5.5) · 진입 구간 [a*_L, d*_L] (정리 5.5,
  d*_L = 식 5.16 — 4.11 과 같은 꼴에 V_L, a*_L = 식 5.15 — F̂(V_L' − 1) = F̂'(V_L − a − ĉ))

수치 처리: s = σ/√(2μ) 로 표준화한 y = (x − θ)/s 에서 F(y) = ∫₀^∞ u^{a−1} e^{yu − u²/2} du
(a = r/μ, 식 3.3), G(y) = F(−y) (식 3.4). u→0 특이점은 ∫₀¹ u^{a−1}(e^{f}−1)du + 1/a 로 뺀다.
r = 0 이면 F 가 발산한다(문헌도 r > 0 을 요구) — 그 경우 ``ValueError``.

🔴 이름 정직성: 이 모듈 밖의 z 경계 코드에 Leung 이름을 붙이지 않는다(지시서 §3.5).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy import integrate, optimize


def _F_std(y: float, a: float) -> float:
    if a <= 0:
        raise ValueError("r must be > 0 (Leung & Li 2015 §2.2)")
    f1 = integrate.quad(lambda u: u ** (a - 1.0) * math.expm1(y * u - 0.5 * u * u), 0.0, 1.0,
                        limit=200)[0]
    f2 = integrate.quad(lambda u: u ** (a - 1.0) * math.exp(y * u - 0.5 * u * u), 1.0, np.inf,
                        limit=200)[0]
    return f1 + 1.0 / a + f2


def _dF_std(y: float, a: float) -> float:
    """dF/dy = ∫ u^a e^{yu − u²/2} du."""
    return integrate.quad(lambda u: u ** a * math.exp(y * u - 0.5 * u * u), 0.0, np.inf,
                          limit=200)[0]


def _d2F_std(y: float, a: float) -> float:
    return integrate.quad(lambda u: u ** (a + 1.0) * math.exp(y * u - 0.5 * u * u), 0.0, np.inf,
                          limit=200)[0]


@dataclass(frozen=True)
class OUParams:
    theta: float   # 중심 (문헌 θ)
    mu: float      # 회귀 속도 (문헌 μ)
    sigma: float
    r: float       # 할인율 (μ 와 같은 시간 단위)
    c: float       # 청산 비용
    c_hat: float   # 진입 비용

    @property
    def s(self) -> float:
        return self.sigma / math.sqrt(2.0 * self.mu)

    @property
    def a(self) -> float:
        return self.r / self.mu


class _FG:
    """x 단위의 F, F', G, G' (식 3.3·3.4)."""

    def __init__(self, p: OUParams):
        self.p = p

    def y(self, x):
        return (x - self.p.theta) / self.p.s

    def F(self, x):
        return _F_std(self.y(x), self.p.a)

    def dF(self, x):
        return _dF_std(self.y(x), self.p.a) / self.p.s

    def G(self, x):
        return _F_std(-self.y(x), self.p.a)

    def dG(self, x):
        return -_dF_std(-self.y(x), self.p.a) / self.p.s


def _bracket_root(fun, lo: float, hi: float, n: int = 60) -> "float | None":
    xs = np.linspace(lo, hi, n)
    vals = [fun(x) for x in xs]
    for i in range(n - 1):
        if not (np.isfinite(vals[i]) and np.isfinite(vals[i + 1])):
            continue
        if vals[i] == 0:
            return float(xs[i])
        if vals[i] * vals[i + 1] < 0:
            return float(optimize.brentq(fun, xs[i], xs[i + 1], xtol=1e-10))
    return None


# ── 무손절판 ──────────────────────────────────────────────────────────────────

def exit_level(p: OUParams) -> "float | None":
    """b*: F(b) = (b − c)F'(b) (식 4.3). b* > c 이고 b* > L* = (μθ + rc)/(μ + r) (식 4.1)."""
    fg = _FG(p)
    lstar = (p.mu * p.theta + p.r * p.c) / (p.mu + p.r)
    lo = max(lstar, p.c) + 1e-9 * p.s
    return _bracket_root(lambda b: fg.F(b) - (b - p.c) * fg.dF(b), lo, p.theta + 8 * p.s)


def V_nostop(p: OUParams, b: float):
    fg = _FG(p)
    Fb = fg.F(b)

    def V(x):
        return (b - p.c) * fg.F(x) / Fb if x < b else x - p.c

    def dV(x):
        return (b - p.c) * fg.dF(x) / Fb if x < b else 1.0
    return V, dV


def entry_level(p: OUParams, b: float) -> "float | None":
    """d*: Ĝ(d)(V'(d) − 1) = Ĝ'(d)(V(d) − d − ĉ) (식 4.11). Ĝ 은 r̂ = r 로 둔다."""
    fg = _FG(p)
    V, dV = V_nostop(p, b)
    return _bracket_root(lambda d: fg.G(d) * (dV(d) - 1.0) - fg.dG(d) * (V(d) - d - p.c_hat),
                         p.theta - 8 * p.s, b - 1e-9 * p.s)


# ── 손절판 ────────────────────────────────────────────────────────────────────

def exit_level_stop(p: OUParams, L: float) -> "float | None":
    """b*_L: 식 (5.5)."""
    fg = _FG(p)
    FL, GL = fg.F(L), fg.G(L)

    def eq(b):
        Fb, Gb, dFb, dGb = fg.F(b), fg.G(b), fg.dF(b), fg.dG(b)
        lhs = ((L - p.c) * Gb - (b - p.c) * GL) * dFb + ((b - p.c) * FL - (L - p.c) * Fb) * dGb
        return lhs - (Gb * FL - GL * Fb)
    return _bracket_root(eq, L + 1e-6 * p.s, p.theta + 8 * p.s, n=80)


def V_stop(p: OUParams, L: float, b: float):
    """식 (5.3)·(5.4)."""
    fg = _FG(p)
    FL, GL, Fb, Gb = fg.F(L), fg.G(L), fg.F(b), fg.G(b)
    den = Fb * GL - FL * Gb
    C = ((b - p.c) * GL - (L - p.c) * Gb) / den
    D = ((L - p.c) * Fb - (b - p.c) * FL) / den

    def V(x):
        return C * fg.F(x) + D * fg.G(x) if L < x < b else x - p.c

    def dV(x):
        return C * fg.dF(x) + D * fg.dG(x) if L < x < b else 1.0
    return V, dV


def entry_interval_stop(p: OUParams, L: float, b: float) -> "tuple[float | None, float | None]":
    """[a*_L, d*_L] (정리 5.5). d*_L = 식 5.16, a*_L = 식 5.15."""
    fg = _FG(p)
    V, dV = V_stop(p, L, b)
    lo, hi = L + 1e-6 * p.s, b - 1e-6 * p.s
    d = _bracket_root(lambda x: fg.G(x) * (dV(x) - 1.0) - fg.dG(x) * (V(x) - x - p.c_hat),
                      lo, hi, n=80)
    if d is None:
        return None, None
    a = _bracket_root(lambda x: fg.F(x) * (dV(x) - 1.0) - fg.dF(x) * (V(x) - x - p.c_hat),
                      lo, d, n=80)
    return a, d


# ── 연구용 표준화 경계 (캐시) ─────────────────────────────────────────────────

def _sig3(v: float) -> float:
    if v == 0 or not math.isfinite(v):
        return v
    return float(f"{v:.3g}")


@lru_cache(maxsize=200_000)
def _std_bounds_cached(a: float, c_s: float, ch_s: float, L_y: float):
    p = OUParams(theta=0.0, mu=1.0, sigma=math.sqrt(2.0), r=a, c=c_s, c_hat=ch_s)  # s = 1
    try:
        b = exit_level_stop(p, L_y)
        if b is None:
            return None
        lo, d = entry_interval_stop(p, L_y, b)
        if d is None:
            return None
        return (lo if lo is not None else L_y, d, b)
    except (ValueError, ZeroDivisionError, OverflowError, FloatingPointError):
        return None


def std_bounds(theta_speed: float, r_per_day: float, c: float, c_hat: float, L_y: float = -2.0):
    """표준화(y = (X − μ̂)/σ_stat) 경계 (a_y, d_y, b_y) 또는 None(솔버 실패).

    a = r/θ, c/s, ĉ/s 를 유효숫자 3자리로 반올림해 캐시한다(같은 꼴의 창이 많다).
    σ_stat 가 곧 s 다(σ/√(2θ)). 연구는 X 를 μ̂ 로 중심화해 θ = 0 으로 푼다(보고서 명시).
    """
    return _std_bounds_cached(_sig3(r_per_day / theta_speed), _sig3(c), _sig3(c_hat), L_y)


def std_bounds_scaled(theta_speed: float, sigma_stat: float, r_per_day: float, cost_rt: float,
                      L_y: float = -2.0):
    """왕복비용 ``cost_rt``(로그 단위)를 진입·청산 반반으로 나눠 표준화 경계를 구한다."""
    half = cost_rt / 2.0
    return std_bounds(theta_speed, r_per_day, half / sigma_stat, half / sigma_stat, L_y)


# ── 표준화 격자 + 보간 (연구 속도용) ─────────────────────────────────────────
# 경계는 (a = r/θ, c/s, ĉ/s, L_y) 의 매끄러운 함수다. 창마다 적분·근 찾기를 하면 종목당 수십 초라
# 격자(log 간격)에서 한 번 풀고 쌍선형 보간한다. 보간 오차는 실행기가 무작위 점에서 정확해와
# 대조해 보고한다. 네 모서리 중 하나라도 솔버 실패면 정확해로 다시 푼다(조용한 대체 없음).

GRID_A = np.logspace(math.log10(3e-5), math.log10(2e-2), 24)
GRID_CS = np.logspace(math.log10(2e-3), math.log10(1.5), 40)


def solve_grid_point(args):
    a, cs, L_y = args
    return _std_bounds_cached(float(a), float(cs), float(cs), L_y)


class BoundsGrid:
    def __init__(self, table: dict, L_y: float = -2.0):
        self.table = table          # (ia, ic) → (a, d, b) | None
        self.L_y = L_y
        self.la = np.log(GRID_A)
        self.lc = np.log(GRID_CS)

    def lookup(self, a: float, cs: float):
        if not (GRID_A[0] <= a <= GRID_A[-1] and GRID_CS[0] <= cs <= GRID_CS[-1]):
            return _std_bounds_cached(_sig3(a), _sig3(cs), _sig3(cs), self.L_y)
        x, y = math.log(a), math.log(cs)
        i = min(int(np.searchsorted(self.la, x, side="right") - 1), len(GRID_A) - 2)
        k = min(int(np.searchsorted(self.lc, y, side="right") - 1), len(GRID_CS) - 2)
        corners = [self.table.get((i + di, k + dk)) for di in (0, 1) for dk in (0, 1)]
        if any(cn is None for cn in corners):
            return _std_bounds_cached(_sig3(a), _sig3(cs), _sig3(cs), self.L_y)
        tx = (x - self.la[i]) / (self.la[i + 1] - self.la[i])
        ty = (y - self.lc[k]) / (self.lc[k + 1] - self.lc[k])
        w = ((1 - tx) * (1 - ty), (1 - tx) * ty, tx * (1 - ty), tx * ty)
        return tuple(sum(wi * cn[m] for wi, cn in zip(w, corners)) for m in range(3))

    def bounds(self, theta_speed: float, sigma_stat: float, r_per_day: float, cost_rt: float):
        return self.lookup(r_per_day / theta_speed, (cost_rt / 2.0) / sigma_stat)


def mc_rule_values(a_disc: float, c: float, c_hat: float, L: float, rules, *, n_paths: int = 10_000,
                   dt: float = 0.01, horizon: float = 60.0, x0: float = 0.0, seed: int = 20261001,
                   offset: float = 0.0):
    """검증 (b) — 표준화 OU(dY = −Y dt + √2 dW, s = 1)에서 규칙별 기대 할인 이익.

    ``rules`` = [(lo, d, b), ...] — Y ∈ [lo, d] 에서 진입(위에서 d 를 지나면 d 에서 체결),
    Y ≥ b 이익 청산(b 에서 체결), Y ≤ L 손절(L 에서 체결). 만기에 보유 중이면 그때 값으로 청산,
    진입 못 했으면 0. 공통 난수(같은 경로)로 규칙을 비교한다. 반환 = (평균, 표준오차) 목록.
    ``offset`` = θ/s — 문헌처럼 수준(θ ≠ 0)이 보상에 들어가는 문제를 표준화 단위로 돌릴 때 쓴다.
    """
    rng = np.random.default_rng(seed)
    n_steps = int(horizon / dt)
    ea = math.exp(-dt)
    sd = math.sqrt(1.0 - ea * ea)
    y = np.full(n_paths, x0, dtype=float)
    R = len(rules)
    state = np.zeros((R, n_paths), dtype=np.int8)   # 0 대기 1 보유 2 끝
    val = np.zeros((R, n_paths))
    for step in range(1, n_steps + 1):
        y_prev = y
        y = y_prev * ea + sd * rng.standard_normal(n_paths)
        disc = math.exp(-a_disc * step * dt)
        for k, (lo, d, b) in enumerate(rules):
            st = state[k]
            w = st == 0
            enter_cross = w & (y_prev > d) & (y <= d) & (y > L)
            enter_in = w & (y >= lo) & (y <= d) & ~enter_cross
            px = np.where(enter_cross, d, y)
            ent = enter_cross | enter_in
            val[k, ent] += disc * (-(px[ent] + offset) - c_hat)
            st[ent] = 1
            hold = (st == 1) & ~ent
            up = hold & (y >= b)
            dn = hold & (y <= L)
            val[k, up] += disc * (b + offset - c)
            val[k, dn] += disc * (L + offset - c)
            st[up | dn] = 2
    disc = math.exp(-a_disc * horizon)
    out = []
    for k in range(R):
        h = state[k] == 1
        val[k, h] += disc * (y[h] + offset - c)
        out.append((float(val[k].mean()), float(val[k].std(ddof=1) / math.sqrt(n_paths))))
    return out
