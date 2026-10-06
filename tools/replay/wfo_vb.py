#!/usr/bin/env python3
"""주기적 재조정(걷기 전진) — volatility_breakout 어댑터. 사전 등록 = ``wfo_20261006/prereg.md``.

30년 재검증 층(``strategies/vb_y30.py`` · ``vb_y30_run.py``)을 그대로 쓴다. base 트랙(체결 = 목표가 × 1.0193) ·
시기별 비용 · 낙관(opt)·비관(pes) 두 판. 선택 점수 = min(낙관 하한, 비관 하한)(30년 B 규칙). 두 판은 쿨다운 때문에
모집단 구성이 달라 따로 이어 붙이고(같은 해별 조합), 두 판 모두 판정을 통과해야 「통과」.

실행: python tools/replay/wfo_vb.py [--no-alt]
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import sys
import time
from collections import defaultdict

for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "audit-dummy")

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_REPO = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import wfo_core as W  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.strategies import vb as VB  # noqa: E402
from replay.strategies import vb_y30 as Y  # noqa: E402
from replay.strategies import vb_y30_run as R  # noqa: E402

OUT = os.path.join(_REPO, "_workspace/analysis/wfo_20261006/vb")
CACHE = os.path.join(os.path.dirname(C.SCRATCH), "wfo")
END = "2026-10-02"
FILL = Y.FILL_BASE
FIXED_B = (0.8, "N", "close", -5.0, "F1")
VERS = ("opt", "pes")


def log(*a):
    print(time.strftime("%H:%M:%S"), "[vb]", *a, flush=True)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def kid(k) -> str:
    km, hold, mode, stop, filt = k
    return f"km{km:g}|{hold}|{mode}{stop:g}|{filt}"


def main(do_alt=True):
    t0 = time.time()
    os.makedirs(CACHE, exist_ok=True)
    st, meta = R.load()
    ctx = R.Ctx(st, meta)
    cal = ctx.cal
    yi = W.YearIndex(cal)
    sizer, _ = R.vb_sizer()
    G = R.grid()
    ids = [kid(k) for k in G]
    key_of = dict(zip(ids, G))
    cfgs = {kid(k): dict(zip(("km", "hold", "stop_mode", "stop", "filt"), k)) for k in G}
    cur_id, b_id = kid(R.CUR), kid(FIXED_B)
    log("ctx", f"{time.time()-t0:.0f}s")
    g_end = yi.end_gd

    def to_trades(p) -> W.Trades:
        m = p["gd"] <= g_end
        gin = p["gd"][m].astype(np.int64)
        names = [ctx.cd.names[int(t)] for t in ctx.cd.tk[p["row"][m]]]
        return W.Trades(gin, p["xg"][m].astype(np.int64), p["net"][m], W.week_keys(names, gin, cal))

    pk = os.path.join(CACHE, "vb_trades.pkl")
    if os.path.exists(pk):
        T = pickle.load(open(pk, "rb"))
    else:
        T = {v: {} for v in VERS}
        for i, k in enumerate(G):
            for v in VERS:
                T[v][kid(k)] = to_trades(ctx.pop(*k, FILL, v))
            if i % 21 == 0:
                log("pop", i, kid(k), len(T["opt"][kid(k)]), f"{time.time()-t0:.0f}s")
        pickle.dump(T, open(pk, "wb"), protocol=pickle.HIGHEST_PROTOCOL)
    log("populations", f"{time.time()-t0:.0f}s")

    sel_cache = {}

    def select_fn(y):
        if y in sel_cache:
            return sel_cache[y]
        rows = []
        for ci, c in enumerate(ids):
            to = T["opt"][c].take(yi.train_mask(T["opt"][c], y))
            tp = T["pes"][c].take(yi.train_mask(T["pes"][c], y))
            n = len(to)
            elig = n >= R.MIN_TPY * W.TRAIN_YEARS
            if elig:
                lo_o = W.cluster_boot(to.r, to.ck)[1]
                lo_p = W.cluster_boot(tp.r, tp.ck)[1]
                sc = float(min(lo_o, lo_p))
            else:
                sc = float("nan")
            rows.append({"id": c, "order": ci, "n": n, "eligible": bool(elig), "score": sc,
                         "mean": float(to.r.mean()) if n else float("nan"),
                         "mean_pes": float(tp.r.mean()) if len(tp) else float("nan"),
                         "changed": W.n_changed(cfgs[c], cfgs[cur_id])})
        el = [r for r in rows if r["eligible"] and np.isfinite(r["score"])]
        if not el:
            out = {"year": y, "chosen": cur_id, "fallback": True, "n_eligible": 0, "rows": rows}
        else:
            b = min(el, key=lambda r: (-r["score"], -r["mean"], r["changed"], r["order"]))
            out = {"year": y, "chosen": b["id"], "fallback": False, "n_eligible": len(el), "rows": rows,
                   "chosen_score": b["score"], "chosen_train_mean": b["mean"], "chosen_train_n": b["n"],
                   "chosen_train_mean_pes": b["mean_pes"]}
        sel_cache[y] = out
        log("sel", y, out["chosen"], out.get("chosen_score"))
        return out

    allsig_cache = {}

    def allsig(c, v):
        if (c, v) not in allsig_cache:
            allsig_cache[(c, v)] = R.allsig(ctx, *key_of[c], FILL, v)
        return allsig_cache[(c, v)]

    def book(path, v, g0, g1, seeds):
        sbg = defaultdict(list)
        cd = ctx.cd
        for y, c in path.items():
            a, b = max(yi.first(y), g0), min(yi.last(y), g1)
            p = allsig(c, v)
            for j in np.nonzero((p["gd"] >= a) & (p["gd"] <= b))[0]:
                r = int(p["row"][j])
                sbg[int(p["gd"][j])].append(Y.BSig(cd.names[int(cd.tk[r])], int(p["gd"][j]), float(p["E"][j]),
                                                   float(p["E"][j] * cd.raw[r]), float(p["px"][j]), int(p["why"][j]),
                                                   int(p["xg"][j]), float(cd.C[r])))
        return [Y.run_book_var(sbg, sizer, cal, g0, g1, seed, start_equity=float(C.BUDGET_C7), cost_rt_gd=ctx.cost,
                               max_pos=VB.VB_OP["max_pos"]) for seed in seeds]

    alt_sel = None
    if do_alt:
        ak = os.path.join(CACHE, "vb_alt_curves.pkl")
        if os.path.exists(ak):
            curves = pickle.load(open(ak, "rb"))
        else:
            ta = time.time()
            curves = {v: {} for v in VERS}
            for i, c in enumerate(ids):
                for v in VERS:
                    curves[v][c] = {yy: book({yy: c}, v, yi.first(yy), yi.last(yy), (0,))[0]["equity"]
                                    for yy in range(1997, 2026)}
                if i % 21 == 0:
                    log("alt", i, f"{time.time()-ta:.0f}s")
                if time.time() - ta > 3600:
                    curves = None
                    log("alt 60분 초과 — 생략")
                    break
            if curves is not None:
                pickle.dump(curves, open(ak, "wb"), protocol=pickle.HIGHEST_PROTOCOL)
        if curves is not None:
            alt_sel = {}
            for y in W.OOS_YEARS:
                s = select_fn(y)
                elig = {r["id"]: r["eligible"] for r in s["rows"]}
                metric = {c: min(W.chained_mar(curves[v][c], list(range(y - 10, y)), float(C.BUDGET_C7)) for v in VERS)
                          for c in ids}
                alt_sel[y] = W.select_year_by_metric(y, ids, metric, elig, cfgs, cfgs[cur_id], cur_id)

    out = {"strategy": "vb", "cfgs": cfgs, "fill": FILL}
    for v in VERS:
        def book_fn(path, version, _v=v):
            g0 = yi.first(2007)
            runs = book(path, _v, g0, g_end, C.BOOK_SEEDS)
            return W.book_summary([r["equity"] for r in runs], cal[g0:g_end + 1], float(C.BUDGET_C7),
                                  fills=[r["counts"].get("fill", 0) for r in runs])
        out[v] = W.run_wfo(cal=cal, combos=ids, cfgs=cfgs, trades=T[v], current_id=cur_id, fixed_b_id=b_id,
                           base_cfg=cfgs[cur_id], min_tpy=R.MIN_TPY, book_fn=book_fn, select_fn=select_fn,
                           alt_select_fn=(lambda y: alt_sel[y]) if alt_sel else None, log=log)
        log(v, out[v]["judge"]["r"]["label"])
    j = [out[v]["judge"]["r"] for v in VERS]
    out["label"] = "통과" if all(x["label"] == "통과" for x in j) else "실패(" + " / ".join(
        f"{v} {x['label']}" for v, x in zip(VERS, j)) + ")"
    out["elapsed_s"] = time.time() - t0
    out["code_sha256"] = {f: sha(os.path.join(os.path.dirname(__file__), f)) for f in ("wfo_core.py", "wfo_vb.py")}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "result.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=W.js)
    log("done", f"{out['elapsed_s']:.0f}s", out["label"])


if __name__ == "__main__":
    main(do_alt="--no-alt" not in sys.argv)
