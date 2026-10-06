#!/usr/bin/env python3
"""30년 재검증 — 평균회귀 OU z(2차 수정판) · 1단계(종목별 추정·통과율·거래) + 2단계(판정).

사전 등록 = ``_workspace/analysis/strategy_30y_20261006/mr_regime/prereg.md``(sha256 동결).
신호 계산은 2차 수정판 그대로(``strategies/mean_reversion/signals.estimate_series`` — Engle–Granger N=2 ·
60봉 창 · 5일 재추정). 집행은 ``execution.simulate_ticker`` 와 같은 규칙에 **시기별 가격제한폭**과
**시기별 비용**만 바꿔 끼웠다(``simulate_y30`` — 폭 30%·비용 고정이면 원본과 같은 거래를 낸다, 테스트로 확인).

    python -m tools.replay.y30_mr_ou stage1 <scratch>/ou_stage1.pkl [--sample N]
    python -m tools.replay.y30_mr_ou stage2 <scratch>/ou_stage1.pkl <out_dir>
"""
from __future__ import annotations

import itertools
import json
import math
import multiprocessing as mp
import os
import pickle
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, ".."), os.path.join(_HERE, "..", "..")):
    _p = os.path.abspath(_p)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import y30_mr_data as Y  # noqa: E402
from replay.strategies.mean_reversion.signals import REASON_CODES, estimate_series, manage  # noqa: E402

SEED = 20261001
Z_ENTRY = (-1.5, -2.0, -2.5)
Z_EXIT = (-0.5, -0.25, 0.0)
STOPS = ((5.0, 1.0), (7.0, 1.5), (10.0, 2.0))
MODES = ("resid", "price")
MU_RULES = ("block0", "m1", "none")
CURRENT = (-1.5, 0.0, 7.0, 1.5, "resid", "block0")      # 2차 채택 키 z|-1.5|0.0|0.0038|7.0|1.5|resid|asof|mu
GRID = list(itertools.product(Z_ENTRY, Z_EXIT, STOPS, MODES, MU_RULES))
GRID = [(ez, xz, sp, k, mode, mu) for ez, xz, (sp, k), mode, mu in GRID]
assert len(GRID) == 162 and CURRENT in GRID
REASONS = ("profit", "disaster_pct", "disaster_z", "regime_break", "timeout")
_RB_STAT = {REASON_CODES[k] for k in ("adf", "half_life", "b_range", "sigma")}

TRADE_DT = np.dtype([("tj", "i4"), ("sig", "i4"), ("ei", "i4"), ("xi", "i4"), ("gross", "f4"), ("cost", "f4"),
                     ("reason", "i1"), ("rb", "i1"), ("z_entry", "f4"), ("z_exit", "f4"), ("entry_px", "f4"),
                     ("exit_px", "f4"), ("entry_raw", "f4"), ("mu", "f4"), ("mae", "f4"), ("mfe", "f4"),
                     ("hl", "f4")])


# ── 집행 (execution.simulate_ticker 와 같은 규칙 + 시기별 폭·비용) ──────────────

def _locked(o, h, l, c, lim, t: int) -> bool:
    return (t > 0 and math.isfinite(o[t]) and math.isfinite(c[t - 1])
            and o[t] <= c[t - 1] * Y.limit_down_mult(lim[t]) and h[t] == l[t])


def simulate_y30(o, h, l, c, sig, elig, mu_exec, *, ez, xz, stop_pct, k_stop, mu_rule, lim, cost_day,
                 stats: "dict | None" = None) -> "list[dict]":
    """거래 목록. 진입 = t 종가 신호 → t+1 시가. ``cost_day[t]`` = t 일 왕복 비용(진입 비용 조건에 씀).

    ``mu_rule``: block0 = 시장 유닛 0 이면 진입 없음(현행) · m1 = 1 일 때만 · none = 무시. 결측 = 진입 없음.
    """
    n = len(c)
    z, ss = sig.z, sig.sigma_stat
    with np.errstate(invalid="ignore"):
        base = sig.valid & elig & np.isfinite(z) & (z <= ez)
        costok = (abs(ez) - abs(xz)) * ss > cost_day
    base[n - 1] = False
    cand = np.nonzero(base & costok)[0]
    blocked = np.nonzero(base & ~costok)[0]
    stop_mult = 1.0 - stop_pct / 100.0
    trades = []
    held = []          # (ei, 마지막 보유일) — 비용 걸림 계수용
    t_free = 0
    for t0 in cand:
        if t0 < t_free:
            continue
        m = mu_exec[t0 + 1]
        if not math.isfinite(m):
            continue
        if (mu_rule == "block0" and m == 0.0) or (mu_rule == "m1" and m != 1.0):
            continue
        op = o[t0 + 1]
        if not math.isfinite(op) or (math.isfinite(c[t0]) and op >= c[t0] * Y.limit_up_mult(lim[t0 + 1])):
            continue
        pos = dict(ei=t0 + 1, sig_day=t0, entry_px=op, z_entry=z[t0], hl=sig.hl[t0], mu=m)
        pending = None
        closed = None
        for t in range(t0 + 1, n):
            if pending is not None:
                if math.isfinite(o[t]) and not _locked(o, h, l, c, lim, t):
                    _close(trades, pos, t, o[t], pending, h, l)
                    closed = t
                    break
            if math.isfinite(l[t]):
                stop_px = pos["entry_px"] * stop_mult
                if l[t] <= stop_px:
                    if _locked(o, h, l, c, lim, t):
                        if pending is None:
                            pending = "disaster_pct"
                            pos["rb_kind"] = 0
                        continue
                    fill = o[t] if (t > pos["ei"] and math.isfinite(o[t]) and o[t] <= stop_px) else stop_px
                    _close(trades, pos, t, fill, "disaster_pct", h, l)
                    closed = t
                    break
            if pending is None:
                why = manage(z=z[t], valid_today=bool(sig.valid[t]), is_est_today=bool(sig.is_est[t]),
                             held_days=t - pos["ei"], hl_entry=pos["hl"], z_entry=pos["z_entry"], k_stop=k_stop,
                             exit_z=xz, leung_bounds=None, leung_L=None)
                if why is not None:
                    pending = why
                    pos["z_exit_sig"] = z[t]
                    pos["rb_kind"] = (1 if int(sig.est_reason[t]) in _RB_STAT else 2) if why == "regime_break" else 0
        if closed is None:
            held.append((t0 + 1, n))
            break
        held.append((t0 + 1, closed))
        t_free = closed
    if stats is not None:
        nb = 0
        for b in blocked:
            if not any(a <= b < e for a, e in held):
                nb += 1
        stats["cost_blocked"] = stats.get("cost_blocked", 0) + nb
    for tr in trades:
        tr["cost"] = 0.5 * cost_day[tr["ei"]] + 0.5 * cost_day[tr["xi"]]
    return trades


def _close(trades, pos, t, px, reason, h, l):
    ei = pos["ei"]
    seg_l, seg_h = l[ei:t + 1], h[ei:t + 1]
    mae = float(np.nanmin(seg_l) / pos["entry_px"] - 1.0) if np.isfinite(seg_l).any() else float("nan")
    mfe = float(np.nanmax(seg_h) / pos["entry_px"] - 1.0) if np.isfinite(seg_h).any() else float("nan")
    trades.append(dict(ei=ei, xi=t, sig_day=pos["sig_day"], entry_px=pos["entry_px"], exit_px=px,
                       gross=px / pos["entry_px"] - 1.0, reason=reason, z_entry=pos["z_entry"],
                       z_exit=pos.get("z_exit_sig", float("nan")), hl=pos["hl"], held=t - ei, mae=mae, mfe=mfe,
                       mu=pos["mu"], rb_kind=pos.get("rb_kind", 0)))


# ── 1단계 작업자 ──────────────────────────────────────────────────────────────
G: dict = {}


def _surrogate(logp, rng, kind):
    out = np.full_like(logp, np.nan)
    fin = np.where(np.isfinite(logp))[0]
    if len(fin) < 3:
        return out
    seg = logp[fin[0]:fin[-1] + 1].copy()
    r = np.diff(seg)
    ok = np.isfinite(r)
    rr = r[ok]
    rr = rng.permutation(rr) if kind == "shuffle" else rng.normal(0.0, np.std(rr) if len(rr) > 1 else 0.01,
                                                                  size=len(rr))
    new = np.zeros(len(r))
    new[ok] = rr
    path = seg[0] + np.concatenate([[0.0], np.cumsum(new)])
    path[~np.isfinite(seg)] = np.nan
    out[fin[0]:fin[-1] + 1] = path
    return out


def _pass_counts(sig, elig, segi):
    """구간(T·V·H) × (쓸 수 있는 창, 통과 창, 사유 코드 분포) + 종목 단위 ever/consec."""
    est = np.where(sig.is_est)[0]
    codes = sig.est_reason[est]
    usable = elig[est] & ~np.isin(codes, [REASON_CODES["warmup"], REASON_CODES["halt"], REASON_CODES["short"]])
    ok = usable & (codes == REASON_CODES["ok"])
    sg = segi[est]
    out = {}
    for k in range(3):
        m = sg == k
        out[k] = dict(usable=int((usable & m).sum()), ok=int((ok & m).sum()),
                      codes=np.bincount(codes[usable & m].astype(int), minlength=9),
                      any_usable=bool((usable & m).any()), ever=bool((ok & m).any()),
                      consec=bool(np.any(ok[1:] & ok[:-1] & m[1:])) if len(ok) > 1 else False,
                      halt=int(((codes == REASON_CODES["halt"]) & elig[est] & m).sum()))
    return out, est[ok]


def work(j: int) -> dict:
    P = G["panel"]
    o = P.o[j].astype(float)
    h = P.h[j].astype(float)
    l = P.l[j].astype(float)
    c = P.c[j].astype(float)
    halt = P.notrade[j] | P.flag[j] | ~np.isfinite(c)
    logp = np.log(c)
    elig = G["elig"][j]
    lim = G["lim"][j].astype(float)
    segi = G["segi"]
    rng = np.random.default_rng(SEED + j)
    s_res = estimate_series(logp, G["logb"], halt)
    s_pri = estimate_series(logp, None, halt)
    res = {"j": j, "ticker": P.tickers[j]}
    pc = {}
    pc["resid"], okd = _pass_counts(s_res, elig, segi)
    pc["price"], _ = _pass_counts(s_pri, elig, segi)
    for kind in ("shuffle", "rw"):
        sp = _surrogate(logp, rng, kind)
        ss = estimate_series(sp, G["logb"], halt | ~np.isfinite(sp))
        pc[kind], _ = _pass_counts(ss, elig, segi)
    res["pass"] = pc
    res["hl"] = (s_res.hl[okd].astype(np.float32), s_res.hl_adj[okd].astype(np.float32), segi[okd])
    fin = np.where(np.isfinite(c))[0]
    if len(fin):
        span = slice(fin[0], fin[-1] + 1)
        res["missing_ratio"] = float(np.mean(P.notrade[j][span]))
    else:
        res["missing_ratio"] = float("nan")
    trades = {}
    blocked = {}
    for key in G["rules"]:
        ez, xz, sp_, k, mode, mu = key
        sig = s_res if mode == "resid" else s_pri
        st: dict = {}
        tr = simulate_y30(o, h, l, c, sig, elig, G["mu"], ez=ez, xz=xz, stop_pct=sp_, k_stop=k, mu_rule=mu,
                          lim=lim, cost_day=G["cost"], stats=st)
        blocked[key] = st.get("cost_blocked", 0)
        if tr:
            a = np.zeros(len(tr), dtype=TRADE_DT)
            for i, x in enumerate(tr):
                a[i] = (j, x["sig_day"], x["ei"], x["xi"], x["gross"], x["cost"], REASONS.index(x["reason"]),
                        x["rb_kind"], x["z_entry"], x["z_exit"], x["entry_px"], x["exit_px"],
                        P.o_raw[j, x["ei"]], x["mu"], x["mae"], x["mfe"], x["hl"])
            trades[key] = a
    res["trades"] = trades
    res["cost_blocked"] = blocked
    return res


def prepare(scratch: str):
    with open(os.path.join(scratch, "panel.pkl"), "rb") as fh:
        P = pickle.load(fh)
    mk = np.load(os.path.join(scratch, "mkt.npz"))
    sd, sc = mk["sd"], mk["sc"]
    pos = np.searchsorted(sd, P.dates)
    assert np.all(sd[pos] == P.dates)
    bench = sc[pos]
    uni = Y.universe_shares(P)
    elig = Y.eligible_matrix(P.mktcap, uni["mktcap_share"])
    lim = Y.limit_matrix(P)
    cost = Y.cost_vector(P.dates)
    G.update(panel=P, elig=elig, lim=lim, cost=cost, mu=mk["mu"], logb=np.log(bench), segi=Y.seg_index(P.dates),
             rules=GRID)
    return P, bench, uni


def stage1(scratch: str, out: str, sample: "int | None" = None):
    t0 = time.time()
    P, bench, uni = prepare(scratch)
    cols = [j for j in range(len(P.tickers)) if G["elig"][j].any()]
    if sample:
        rng = np.random.default_rng(SEED)
        cols = sorted(rng.choice(cols, size=min(sample, len(cols)), replace=False).tolist())
    print(f"[ou] tickers {len(cols)}/{len(P.tickers)} rules {len(GRID)} universe {uni} prep {time.time()-t0:.0f}s",
          flush=True)
    ctx = mp.get_context("fork")
    results = []
    nproc = int(os.environ.get("Y30_NPROC", max(1, os.cpu_count() - 2)))
    with ctx.Pool(nproc) as pool:
        for k, r in enumerate(pool.imap_unordered(work, cols, chunksize=2)):
            results.append(r)
            if (k + 1) % 100 == 0:
                print(f"  {k+1}/{len(cols)} {time.time()-t0:.0f}s", flush=True)
    results.sort(key=lambda r: r["j"])
    trades = {}
    for key in GRID:
        arrs = [r["trades"][key] for r in results if key in r["trades"]]
        trades[key] = np.concatenate(arrs) if arrs else np.zeros(0, dtype=TRADE_DT)
        for r in results:
            r["trades"].pop(key, None)
    payload = dict(meta=dict(panel=P.meta, universe=uni, n_cols=len(cols), sample=sample, seed=SEED,
                             seconds=time.time() - t0, nproc=nproc),
                   results=results, trades=trades, dates=P.dates, tickers=P.tickers, mu=G["mu"], bench=bench,
                   cost=G["cost"])
    with open(out, "wb") as fh:
        pickle.dump(payload, fh, protocol=5)
    print(f"[ou] done {time.time()-t0:.0f}s → {out}", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "stage1":
        smp = int(sys.argv[sys.argv.index("--sample") + 1]) if "--sample" in sys.argv else None
        stage1(os.path.dirname(sys.argv[2]), sys.argv[2], smp)
    elif sys.argv[1] == "stage2":
        from replay import y30_mr_ou_judge as JD
        JD.main(sys.argv[2], sys.argv[3])
