#!/usr/bin/env python3
"""Leung 경계 검증 — (a) 문헌 재현 · (b) 몬테카를로 · 원인 진단 · 격자 보간 오차 (지시서 §3.5).

    python tools/replay/leung_check.py <out_dir>

1차에는 이 스크립트가 리포에 없었다(보고서 R14). 2차 사전 등록 R4 의 프로토콜을 그대로 따른다.
- (a) 문헌 표 1 GLD–GDX + 그림 7 설명의 입력으로 b*_L·d*_L 을 풀어 0.5570·0.4978 과 허용 오차 0.002 로 비교.
- (b) 표준화 OU(경로 10,000 · dt 0.01 · 지평 60 · 시드 20261001)에서 우리 경계의 기대 할인 이익이
  이웃 8개 경계와 「안 사기(0)」 중 어느 것보다도 2 표준오차 넘게 뒤지지 않으면 통과.
연구 venv(scipy) 전용. 네트워크·DB 접속 없음.
"""
from __future__ import annotations

import json
import math
import os
import pickle
import sys
import time

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from replay.strategies.mean_reversion import leung as LG  # noqa: E402

PAPER = dict(theta=0.5388, mu=16.6677, sigma=0.1599, r=0.05, c=0.05, c_hat=0.05)
PAPER_L = 0.4834
PAPER_D, PAPER_B = 0.4978, 0.5570
TOL = 0.002
SEED = 20261001
STEP = 0.25
RESEARCH_POINTS = (("research_a5e-4_cs0.05", 5e-4, 0.05), ("research_a2e-3_cs0.03", 2e-3, 0.03),
                   ("research_a1e-3_cs0.15", 1e-3, 0.15))


def _roots(fun, lo, hi, n=2000):
    xs = np.linspace(lo, hi, n)
    v = np.array([fun(x) for x in xs])
    ok = np.isfinite(v[1:]) & np.isfinite(v[:-1])
    return [float(x) for x in xs[1:][ok & (np.sign(v[1:]) != np.sign(v[:-1]))]]


def literature_a() -> dict:
    p = LG.OUParams(**PAPER)
    fg = LG._FG(p)
    L = PAPER_L
    b = LG.exit_level_stop(p, L)
    a_fix, d_fix = LG.entry_interval_stop(p, L, b)
    a_raw, d_raw = LG.entry_interval_stop(p, L, b, require_positive=False)
    V, dV = LG.V_stop(p, L, b)

    def eqb(x):
        Fb, Gb, dFb, dGb = fg.F(x), fg.G(x), fg.dF(x), fg.dG(x)
        FL, GL = fg.F(L), fg.G(L)
        return ((L - p.c) * Gb - (x - p.c) * GL) * dFb + ((x - p.c) * FL - (L - p.c) * Fb) * dGb - (Gb * FL - GL * Fb)

    lo, hi = L + 1e-6 * p.s, b - 1e-6 * p.s
    xs = np.linspace(lo, hi, 2000)
    reward = np.array([V(x) - x - p.c_hat for x in xs])
    # 독립 확인: r → 0 극한에서 척도 함수로 청산 가치를 직접 최대화한 b
    from scipy import integrate, optimize
    s = p.s
    S = lambda x: integrate.quad(lambda u: math.exp((u - p.theta) ** 2 / (2 * s * s)), p.theta, x)[0]  # noqa: E731
    x0 = 0.52
    f = lambda bb: ((bb - p.c) * (S(x0) - S(L)) + (L - p.c) * (S(bb) - S(x0))) / (S(bb) - S(L))  # noqa: E731
    b_r0 = optimize.minimize_scalar(lambda bb: -f(bb), bounds=(x0 + 1e-4, 0.7), method="bounded").x
    d_ok = d_fix is not None and math.isfinite(d_fix)
    passed = bool(b is not None and d_ok and abs(b - PAPER_B) <= TOL and abs(d_fix - PAPER_D) <= TOL)
    return dict(
        inputs=PAPER | dict(L=L), literature=dict(d=PAPER_D, b=PAPER_B), tol=TOL,
        ours=dict(b=b, d_raw_root=d_raw, a_raw_root=a_raw, d_after_fix=None if not d_ok else d_fix),
        err=dict(b=None if b is None else b - PAPER_B, d_raw=None if d_raw is None else d_raw - PAPER_D),
        passed=passed,
        diagnosis=dict(
            transcription_L_from_theta_minus_2s=p.theta - 2 * p.s, stationary_sd=p.s,
            roots_b=_roots(eqb, L + 1e-6 * p.s, p.theta + 8 * p.s),
            roots_d=_roots(lambda x: fg.G(x) * (dV(x) - 1.0) - fg.dG(x) * (V(x) - x - p.c_hat), lo, hi),
            roots_a=_roots(lambda x: fg.F(x) * (dV(x) - 1.0) - fg.dF(x) * (V(x) - x - p.c_hat), lo, hi),
            reward_max=float(reward.max()), reward_argmax=float(xs[reward.argmax()]),
            band_b_minus_L=b - L, round_trip_cost=p.c + p.c_hat,
            literature_b_minus_d=PAPER_B - PAPER_D,
            b_r0_scale_function=float(b_r0),
            no_entry_after_fix=not d_ok))


def _neighbors(lo, d, b, L):
    out = []
    for dd in (-STEP, 0.0, STEP):
        for db in (-STEP, 0.0, STEP):
            if dd == 0.0 and db == 0.0:
                continue
            nd = d + dd
            out.append((min(lo, nd) if dd < 0 else lo, nd, b + db))
    return out


def mc_point(name, a, c_std, L_y=-2.0, offset=0.0) -> dict:
    t0 = time.time()
    p = LG.OUParams(theta=0.0, mu=1.0, sigma=math.sqrt(2.0), r=a, c=c_std, c_hat=c_std)
    b = LG.exit_level_stop(p, L_y)
    lo_r, d_r = LG.entry_interval_stop(p, L_y, b, require_positive=False)
    lo_f, d_f = LG.entry_interval_stop(p, L_y, b)
    lo_r = lo_r if lo_r is not None else L_y
    no_entry = d_f is not None and math.isnan(d_f)
    ours = None if no_entry else (lo_r, d_r, b)
    neigh = _neighbors(lo_r, d_r, b, L_y)
    rules = [ours, (lo_r, d_r, b), None] + neigh
    vals = LG.mc_rule_values(a, c_std, c_std, L_y, rules, seed=SEED, offset=offset)
    opt = vals[0]
    beat = [dict(rule=None if r is None else list(r), value=list(v)) for r, v in zip(rules[2:], vals[2:])
            if v[0] - opt[0] > 2.0 * math.hypot(v[1], opt[1])]
    return dict(name=name, a=a, c_std=c_std, L=L_y, offset=offset, bounds=dict(lo=lo_r, d=d_r, b=b),
                no_entry_after_fix=no_entry, ours_value=list(opt), raw_root_value=list(vals[1]),
                never_enter_value=list(vals[2]),
                neighbors=[dict(rule=list(r), value=list(v)) for r, v in zip(neigh, vals[3:])],
                beating_ours_beyond_2se=beat, passed=not beat, seconds=time.time() - t0)


def grid_interp_error(grid_path: str, n: int = 200) -> dict:
    if not os.path.exists(grid_path):
        return dict(error="grid missing")
    with open(grid_path, "rb") as fh:
        g = LG.BoundsGrid(pickle.load(fh))
    rng = np.random.default_rng(SEED)
    errs_d, errs_b, mism = [], [], 0
    for _ in range(n):
        a = float(np.exp(rng.uniform(np.log(LG.GRID_A[0]), np.log(LG.GRID_A[-1]))))
        cs = float(np.exp(rng.uniform(np.log(LG.GRID_CS[0]), np.log(LG.GRID_CS[-1]))))
        got = g.lookup(a, cs)
        ex = LG._std_bounds_cached(a, cs, cs, -2.0)
        if got is None or ex is None:
            mism += int((got is None) != (ex is None))
            continue
        if math.isfinite(got[1]) != math.isfinite(ex[1]):
            mism += 1
            continue
        if math.isfinite(ex[1]):
            errs_d.append(abs(got[1] - ex[1]))
        errs_b.append(abs(got[2] - ex[2]))
    return dict(n=n, max_err_d=max(errs_d) if errs_d else None, max_err_b=max(errs_b) if errs_b else None,
                p99_err_d=float(np.quantile(errs_d, 0.99)) if errs_d else None, entry_mismatch=mism)


def main():
    out_dir = sys.argv[1]
    grid_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(out_dir, ".leung_grid_L-2.pkl")
    lit = literature_a()
    p = LG.OUParams(**PAPER)
    points = [mc_point("paper_fig7", p.r / p.mu, p.c / p.s, (PAPER_L - p.theta) / p.s, offset=p.theta / p.s)]
    points += [mc_point(nm, a, cs) for nm, a, cs in RESEARCH_POINTS]
    res = dict(a_literature=lit, b_mc=points, b_passed=all(x["passed"] for x in points),
               grid_interp=grid_interp_error(grid_path),
               protocol="prereg.md §2 R4 — 허용 오차 0.002 · MC 경로 10,000 · dt 0.01 · 지평 60 · 시드 20261001")
    with open(os.path.join(out_dir, "leung_check.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print(json.dumps(dict(a_passed=lit["passed"], b_passed=res["b_passed"],
                          b_points={x["name"]: (x["passed"], x["ours_value"], x["no_entry_after_fix"]) for x in points},
                          grid=res["grid_interp"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
