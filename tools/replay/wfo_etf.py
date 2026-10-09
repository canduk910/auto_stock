#!/usr/bin/env python3
"""주기적 재조정(걷기 전진) — etf_trend 어댑터. 사전 등록 = ``wfo_20261006/prereg.md`` §3.6.

30년 재검증 층(``y30_etfbase_run.py`` 의 ``etf_load`` · ``gen_signals30`` · ``attach30`` · ``etf_book30`` 하루 순서)을
그대로 쓴다. ETF 유니버스가 2015 년부터라 10년 학습이 되는 첫 해 = 2025 → 표본 밖 = 2025 ~ 2026-10-02.
계좌 = ``etf_book30`` 과 같은 하루 순서에 신호마다 그 해 조합(L · 트레일링 · 채널 · 손익분기 · m 규칙).

표본 밖 해(``years``) · 학습 창 길이(``train_years``) · 출력 폴더(``out``)는 인자다(``wfo_window_20261009/prereg.md``
§7). 기본값 = 원 등록 그대로(2025·2026 · 10년 · ``wfo_20261006/etf_trend``)라 인자 없이 돌리면 원 결과와 같다.
창과 무관한 앞부분(적재 · 신호 · 청산 · 거래 묶음 · 계좌 함수)은 ``prepare()`` 로 한 번 만들어 ``main(ctx=…)`` 에
넘겨 여러 창에서 다시 쓸 수 있다.

실행: python tools/replay/wfo_etf.py [--no-alt] [--train-years K] [--years 2020,2021,…] [--out 폴더]
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import sys
import time
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_REPO = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import wfo_core as W  # noqa: E402
from replay import y30_etfbase_run as ER  # noqa: E402
from replay.audit import config as C  # noqa: E402

OUT = os.path.join(_REPO, "_workspace/analysis/wfo_20261006/etf_trend")
YEARS = (2025, 2026)
FIXED_B = (20, 3.0, 10, True, "ge075")
END = "2026-10-02"
ETF_FIRST_YEAR = 2015            # ETF 유니버스 첫 해 — 대안 규칙 1년 계좌 곡선의 첫 해


def log(*a):
    print(time.strftime("%H:%M:%S"), "[etf]", *a, flush=True)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def cname(cb) -> str:
    L, tr, ch, bl, mu = cb
    return f"L{L}|tr{tr}|ch{ch}|bl{int(bl)}|{mu}"


def prepare(log=log) -> dict:
    """창과 무관한 앞부분 — 적재 · 신호 · 청산 · 조합별 거래 묶음 · 계좌 함수 · 자기 대조. ``main(ctx=…)`` 이 다시 쓴다."""
    from replay.audit.sizing import OpSizer
    from replay.strategies import etf_trend_b as EB
    from replay.strategies import etf_trend_b_audit as EA
    from replay.strategies import etf_trend_opt as EO
    t0 = time.time()
    V = ER.etf_load()
    cal = V["cal"]
    yi = W.YearIndex(cal, END)
    thr = 2e9 * V["defl"]
    log("load", f"{time.time()-t0:.0f}s")
    sigs = {L: ER.gen_signals30(V["data"], V["mu"], L, thr, V["anom"], V["lock"])[0] for L in EO.L_GRID}
    G = EO.grid()
    ids = [cname(cb) for cb in G]
    cb_of = dict(zip(ids, G))
    cfgs = {cname(cb): dict(zip(("L", "trail", "chan", "bl", "mu"), cb)) for cb in G}
    cur_id, b_id = cname(EO.CURRENT), cname(FIXED_B)
    exits = {}
    for L in EO.L_GRID:
        for tr, ch, bl in itertools.product(EO.TR_GRID, EO.CH_GRID, EO.BL_GRID):
            exits[(L, tr, ch, bl)] = ER.attach30(sigs[L], V, tr, ch, bl)
    trades = {}
    for cb in G:
        L, tr, ch, bl, mu = cb
        pool = [t for t in exits[(L, tr, ch, bl)] if t["fu"] and EO.mu_ok(t["m"], mu) and not t["anom"]]
        ded = ER.with_cost(EB.dedup(pool, V["corr"]), "table")
        gin = np.array([t["entry_ci"] for t in ded], dtype=np.int64)
        trades[cname(cb)] = W.Trades(gin, np.array([t["exit_ci"] for t in ded], dtype=np.int64),
                                     np.array([t["RN"] for t in ded]),
                                     W.week_keys([t["ticker"] for t in ded], gin, cal))
    log("trades", f"{time.time()-t0:.0f}s")

    op = OpSizer(EA._import_operating_class(), "etf_trend", {"market_unit_mode": "shadow"}, atr_keys=("atr",))
    cs_day = V["cost_rt"]["table"] / 2
    data = V["data"]

    def book(path, start, end, seeds, start_equity=float(C.BUDGET_C7)):
        sbg, cb_sig = defaultdict(list), {}
        for y, cid in path.items():
            cb = cb_of[cid]
            a, b = yi.first(y), yi.last(y)
            for t in sigs[cb[0]]:
                if not (t["fu"] and EO.mu_ok(t["m"], cb[4])) or not (a <= t["entry_ci"] <= b):
                    continue
                s = EA.ETFSig(t["ticker"], t["j"] + 1, t["entry_ci"], t["E"], t["E"], t["N"], t["line"], t["m"],
                              t["tv20"], t["sig_ci"])
                sbg[t["entry_ci"]].append(s)
                cb_sig[id(s)] = cb
        g0, g1 = ER.win_idx(cal, (start, end))
        runs = []
        for sd in seeds:
            rng = np.random.default_rng(sd)
            cash = float(start_equity)
            pos, eq_prev, equity, cnt = {}, float(start_equity), [], Counter()
            for gd in range(g0, g1 + 1):
                cs = float(cs_day[gd])
                B = eq_prev
                sold_today = set()
                for t in list(pos):
                    ps = pos[t]
                    ti = ps.cur_ti(gd)
                    if ti is None:
                        continue
                    if ps.open_phase(ti, gd):
                        cash += ps.k * ps.exit_px * (1 - cs)
                        sold_today.add(t)
                        del pos[t]
                todays = list(sbg.get(gd, []))
                rng.shuffle(todays)
                todays.sort(key=lambda s: -s.tv20)
                taken = []
                for s in todays:
                    if s.ticker in pos or s.ticker in sold_today:
                        continue
                    cnt["signal"] += 1
                    if len(pos) >= EB.SLOTS:
                        cnt["slot_full"] += 1
                        continue
                    pool = set(pos) | sold_today | set(taken)
                    if any(EB.same_cluster(V["corr"], s.ticker, o, s.sig_ci) for o in pool if o != s.ticker):
                        cnt["cluster"] += 1
                        continue
                    used = sum(x.cost_basis for x in pos.values())
                    P = int(round(s.E_raw))
                    qn = op.qty(P, s.N, budget=int(B), used=int(used), m=s.m)
                    if qn <= 0:
                        cnt["zero_" + ("funds" if int(B) - int(used) < P else "design")] += 1
                        continue
                    L, tr, ch, bl, _mu = cb_sig[id(s)]
                    ps = EO.EtfPosV(s, data[s.ticker], qn, trail=tr, chan=ch, bl=bl, mode="color", fadj=None)
                    cash -= qn * s.E_raw * (1 + cs)
                    pos[s.ticker] = ps
                    taken.append(s.ticker)
                    cnt["fill"] += 1
                for t in list(pos):
                    ps = pos[t]
                    ti = ps.cur_ti(gd)
                    if ti is None:
                        if ps.data_ended(gd):
                            ps._exit(ps.last_px, "END", gd)
                            cash += ps.k * ps.exit_px * (1 - cs)
                            del pos[t]
                        continue
                    if ps.intraday_phase(ti, gd, ti == ps.s.ti):
                        cash += ps.k * ps.exit_px * (1 - cs)
                        del pos[t]
                eq = cash + sum(x.value() for x in pos.values())
                equity.append(eq)
                eq_prev = eq
            runs.append({"equity": np.array(equity), "fills": cnt["fill"], "counts": dict(cnt)})
        return runs, cal[g0:g1 + 1]

    # 자기 대조 — 현행 고정 경로 계좌 = ``etf_book30``(H 창) 과 같아야 한다
    rr, _ = book({y: cur_id for y in range(2021, 2027)}, "2021-01-04", END, seeds=(0,))
    ref = ER.etf_book30(V, sigs[20], EO.CURRENT, ("2021-01-04", END), seeds=(0,))
    self_check = float(rr[0]["equity"][-1] - ref["equity_seed0"][-1])
    log("self_check Δ최종자산", self_check)

    return {"t0": t0, "V": V, "cal": cal, "yi": yi, "sigs": sigs, "ids": ids, "cb_of": cb_of, "cfgs": cfgs,
            "cur_id": cur_id, "b_id": b_id, "trades": trades, "book": book, "self_check": self_check,
            "min_tpy": EO.MIN_TRADES_PER_YEAR, "alt_cache": {}}


def alt_curves(ctx: dict, alt_years, log=log) -> dict:
    """대안 규칙(학습 MAR)용 — 조합 × 해마다 C7 로 새로 시작한 1년 계좌(씨앗 0) 일별 자산. ``ctx`` 에 캐시한다."""
    cache, book = ctx["alt_cache"], ctx["book"]
    for c in ctx["ids"]:
        for y in alt_years:
            if (c, y) not in cache:
                cache[(c, y)] = book({y: c}, f"{y}-01-01", f"{y}-12-31", (0,))[0][0]["equity"]
    log("alt", f"{time.time()-ctx['t0']:.0f}s")
    return {c: {y: cache[(c, y)] for y in alt_years} for c in ctx["ids"]}


def main(do_alt=True, years=YEARS, train_years=W.TRAIN_YEARS, out=OUT, ctx=None, log=log) -> dict:
    years = tuple(int(y) for y in years)
    if ctx is None:
        ctx = prepare(log=log)
    t0, cal, book = ctx["t0"], ctx["cal"], ctx["book"]
    cfgs, ids, cur_id, b_id = ctx["cfgs"], ctx["ids"], ctx["cur_id"], ctx["b_id"]

    alt = None
    if do_alt:
        # 원 등록과 같은 범위 — 표본 밖 첫해 이전 해의 1년 곡선만(기본 = 2015 ~ 2024). 그 뒤 해의 학습 MAR 에는
        # 표본 밖 첫해 이후의 곡선이 빠진다(원 결과와 같게 두려고 그대로 둔다 — 창 비교에서는 대안 규칙을 돌리지 않는다).
        alt = alt_curves(ctx, range(max(ETF_FIRST_YEAR, years[0] - train_years), years[0]), log=log)

    def book_fn(path, version):
        runs, dates = book(path, f"{years[0]}-01-02", END, C.BOOK_SEEDS)
        return W.book_summary([r["equity"] for r in runs], dates, float(C.BUDGET_C7), fills=[r["fills"] for r in runs],
                              eras=((f"{years[0]}-01-01", "2026-12-31"),))

    res = W.run_wfo(cal=cal, combos=ids, cfgs=cfgs, trades=ctx["trades"], current_id=cur_id, fixed_b_id=b_id,
                    base_cfg=cfgs[cur_id], min_tpy=ctx["min_tpy"], book_fn=book_fn, years=years,
                    alt_curves=alt, log=log, train_years=train_years)
    res["strategy"] = "etf_trend"
    res["train_years"] = int(train_years)
    res["cfgs"] = cfgs
    res["self_check_final_equity_diff"] = ctx["self_check"]
    res["n_oos_trades_wfo"] = res["trade"]["wfo"]["r"]["n"]
    res["small_sample"] = bool(res["n_oos_trades_wfo"] < 100)
    res["elapsed_s"] = time.time() - t0
    res["code_sha256"] = {f: sha(os.path.join(os.path.dirname(__file__), f)) for f in ("wfo_core.py", "wfo_etf.py")}
    if out:
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "result.json"), "w") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1, default=W.js)
    log("done", f"K={train_years}", f"{years[0]}–{years[-1]}", f"{res['elapsed_s']:.0f}s", res["judge"]["r"]["label"])
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-alt", action="store_true")
    ap.add_argument("--train-years", type=int, default=W.TRAIN_YEARS)
    ap.add_argument("--years", default=",".join(map(str, YEARS)), help="표본 밖 해(쉼표) — 예 2020,2021,…,2026")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    main(do_alt=not a.no_alt, years=tuple(int(x) for x in a.years.split(",")), train_years=a.train_years, out=a.out)
