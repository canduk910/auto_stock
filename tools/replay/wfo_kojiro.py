#!/usr/bin/env python3
"""주기적 재조정(걷기 전진) — kojiro 어댑터. 사전 등록 = ``_workspace/analysis/wfo_20261006/prereg.md``.

30년 재검증 층(``strategies/kojiro_y30.py`` · ``kojiro_y30_run.py`` · ``kojiro_opt*.py``)을 그대로 쓴다.
체결 = 시가 + 0.76%(30년 B 와 같음) · 비용 = 시기별. 격자 = ``kojiro_opt_run.GRID`` 192.

실행: python tools/replay/wfo_kojiro.py [--no-alt]
"""
from __future__ import annotations

import hashlib
import itertools
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
from replay.audit.sizing import OpSizer  # noqa: E402
from replay.strategies import kojiro_opt as KO  # noqa: E402
from replay.strategies import kojiro_opt_run as KOR  # noqa: E402
from replay.strategies import kojiro_y30 as Y  # noqa: E402
from replay.strategies import kojiro_y30_run as KY  # noqa: E402
from src.engine.strategies.kojiro import KojiroStrategy  # noqa: E402

OUT = os.path.join(_REPO, "_workspace/analysis/wfo_20261006/kojiro")
CACHE = os.path.join(os.path.dirname(C.SCRATCH), "wfo")
SLIP = KY.SLIP
START, END = "1997-01-02", "2026-10-02"
FIXED_B = {"mu": "cur", "band": 0.045, "fresh": 3, "rank": None, "be": 0.0, "trail": 3.5, "time_n": None}


def log(*a):
    print(time.strftime("%H:%M:%S"), "[kojiro]", *a, flush=True)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


class Ctx:
    def __init__(self):
        self.D = KY.prepare()
        self.p, self.st, self.cal = self.D["p"], self.D["st"], self.D["cal"]
        Y.Y30Pos.LIM = Y.limit_table(self.cal)
        self.cost = Y.era_cost(self.cal)
        self.feats = self.D["feats_by"][5]
        self.memo = Y.PathMemo(self.st.bars, self.feats, self.p)
        keys = list(KOR.GRID)
        self.combos = [dict(zip(keys, v)) for v in itertools.product(*(KOR.GRID[k] for k in keys))]
        self.ids = [KOR.cfg_name(c) for c in self.combos]
        self.cfgs = dict(zip(self.ids, self.combos))
        self.g0, self.g1 = Y.gd_range(self.cal, (START, END))
        self.sizer = OpSizer(KojiroStrategy, "kojiro", self.p, atr_keys=("atr",))
        self._sig = {}

    def sigs(self, c):
        k = (c["fresh"], c["band"], c["mu"], c["rank"])
        if k not in self._sig:
            self._sig[k] = KO.select(self.D["sigs_by"][(c["fresh"], c["band"])], c["mu"], c["rank"])
        return self._sig[k]

    def trades(self, cid) -> W.Trades:
        c = self.cfgs[cid]
        pop = Y.population(self.sigs(c), self.memo, KOR.exit_cfg(c), self.g0, self.g1, SLIP)
        gin = np.array([x.s.gd for x in pop], dtype=np.int64)
        gout = np.array([x.exit_gd if x.exit_gd is not None else W.OPEN_GD for x in pop], dtype=np.int64)
        r = np.array([Y.net(x, self.cost) for x in pop])
        return W.Trades(gin, gout, r, W.week_keys([x.s.ticker for x in pop], gin, self.cal))

    def book(self, path, start, end, seeds, start_equity=float(C.BUDGET_C7)) -> list:
        cal = self.cal
        sbg, cfg_of = defaultdict(list), {}
        for y, cid in path.items():
            c = self.cfgs[cid]
            a, b = Y.gd_range(cal, (f"{y}-01-01", f"{y}-12-31"))
            for s in self.sigs(c):
                if a <= s.gd <= b:
                    ss = KO.slip_sig(s, SLIP)
                    sbg[s.gd].append(ss)
                    cfg_of[id(ss)] = c
        runs = []
        for seed in seeds:
            g = Y.Gates30(self.p, self.sizer)

            def open_pos(s, q, g=g):
                c = cfg_of[id(s)]
                pe = KOR.exit_cfg(c).params(self.p)
                ps = Y.Y30Pos(s, self.st.bars[s.ticker], self.feats[s.ticker], q, pe, mode="color", time_n=c["time_n"])
                g.opened.append(ps)
                return ps
            runs.append(Y.run_book30(sbg, open_pos, g.size, cal, start, end, seed, start_equity=start_equity,
                                     cost=self.cost, max_pos=int(self.p["max_positions"])))
        return runs


def main(do_alt=True):
    t0 = time.time()
    os.makedirs(CACHE, exist_ok=True)
    ctx = Ctx()
    cal = ctx.cal
    log("prepare", f"{time.time()-t0:.0f}s")
    pk = os.path.join(CACHE, "kojiro_trades.pkl")
    if os.path.exists(pk):
        trades = pickle.load(open(pk, "rb"))
    else:
        trades = {}
        for i, cid in enumerate(ctx.ids):
            trades[cid] = ctx.trades(cid)
            if i % 12 == 0:
                log("pop", i, cid, len(trades[cid]), f"{trades[cid].r.mean():+.4f}", f"{time.time()-t0:.0f}s")
        pickle.dump(trades, open(pk, "wb"), protocol=pickle.HIGHEST_PROTOCOL)
    log("populations", len(trades), f"{time.time()-t0:.0f}s")
    alt = None
    if do_alt:
        ak = os.path.join(CACHE, "kojiro_alt_curves.pkl")
        if os.path.exists(ak):
            alt = pickle.load(open(ak, "rb"))
        else:
            ta = time.time()
            alt = {}
            for i, cid in enumerate(ctx.ids):
                alt[cid] = {y: ctx.book({y: cid}, f"{y}-01-01", f"{y}-12-31", seeds=(0,))[0]["equity"]
                            for y in range(1997, 2026)}
                if i % 12 == 0:
                    log("alt", i, f"{time.time()-ta:.0f}s")
                if time.time() - ta > 3600:
                    log("alt 60분 초과 — 생략(prereg §1-5)")
                    alt = None
                    break
            if alt is not None:
                pickle.dump(alt, open(ak, "wb"), protocol=pickle.HIGHEST_PROTOCOL)

    def book_fn(path, version):
        runs = ctx.book(path, "2007-01-02", END, seeds=C.BOOK_SEEDS)
        bs = W.book_summary([r["equity"] for r in runs], runs[0]["dates"], float(C.BUDGET_C7),
                            fills=[r["counts"].get("fill", 0) for r in runs])
        bs["recon_max_abs"] = float(max(abs(r["recon"]) for r in runs))
        return bs

    cur_id, b_id = KOR.cfg_name(KOR.CURRENT), KOR.cfg_name(FIXED_B)
    res = W.run_wfo(cal=cal, combos=ctx.ids, cfgs=ctx.cfgs, trades=trades, current_id=cur_id, fixed_b_id=b_id,
                    base_cfg=KOR.CURRENT, min_tpy=KY.MIN_TPY, book_fn=book_fn, alt_curves=alt, log=log)
    res["strategy"] = "kojiro"
    res["cfgs"] = ctx.cfgs
    res["elapsed_s"] = time.time() - t0
    res["code_sha256"] = {f: sha(os.path.join(os.path.dirname(__file__), f)) for f in ("wfo_core.py", "wfo_kojiro.py")}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "result.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=W.js)
    log("done", f"{res['elapsed_s']:.0f}s", res["judge"]["r"]["label"])


if __name__ == "__main__":
    main(do_alt="--no-alt" not in sys.argv)
