#!/usr/bin/env python3
"""주기적 재조정(걷기 전진) — vcp_breakout · bull_flag_breakout 어댑터.

사전 등록 = ``_workspace/analysis/wfo_20261006/prereg.md``. 30년 재검증 층(``strategies/y30_bfbvcp.py`` ·
``y30_data.py`` · ``bfb_vcp_opt.py``)을 그대로 불러 쓴다(고치지 않는다). 이 파일이 더하는 것:
조합마다 전체 기간(1997-01-02 ~ 2026-10-02) 모집단 → ``wfo_core.Trades`` · 해마다 조합이 바뀌는 이어 붙인 계좌 ·
대안 규칙용 조합 × 해 1년 계좌(씨앗 0).

실행: python tools/replay/wfo_bfbvcp.py vcp|bfb [--no-alt]
"""
from __future__ import annotations

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
from replay.strategies import bfb_vcp_opt as OP  # noqa: E402
from replay.strategies import y30_bfbvcp as YB  # noqa: E402
from replay.strategies import y30_data as Y  # noqa: E402

OUT = os.path.join(_REPO, "_workspace/analysis/wfo_20261006")
CACHE = os.path.join(os.path.dirname(C.SCRATCH), "wfo")
FIXED_B = {"vcp": "cur|C_cap7.5_k1.5|X3|ge075", "bfb": "strict|C_cap3_k0|X3|eq1"}
START, END = "1997-01-02", "2026-10-02"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


class Ctx:
    def __init__(self, kind: str):
        self.kind = kind
        self.cls, self.featf = YB._classes(kind)
        self.st, self.meta = Y.build()
        self.cal = self.st.cal
        self.m, _ = Y.market_unit(self.cal)
        self.cost = YB.EraCostY(self.cal)
        self.feats, self.univ = {}, {}
        for s in OP.SETUPS[kind]:
            p_s = OP.params_for(kind, s, "X0")
            self.feats[s] = {t: self.featf(b, p_s) for t, b in self.st.bars.items()}
            self.univ[s] = Y.universe(self.st, self.meta["ratios"], kind, mode="pct")
        self.entries = {e[0]: e for e in OP.entries_for(kind)}
        self.grid = OP.grid(kind)
        self.ids = [g["id"] for g in self.grid]
        self.cfgs = {g["id"]: {"setup": g["setup"], "entry": g["entry"][0], "exit": g["exit"], "mu": g["mu"]}
                     for g in self.grid}
        self._sig = {}
        self._op = {}
        g0 = int(self.cal.searchsorted(pd.Timestamp(START)))
        g1 = int(self.cal.searchsorted(pd.Timestamp(END), side="right")) - 1
        self.g0, self.g1 = g0, g1

    def parts(self, gid):
        s_, e_, x_, mu_ = gid.split("|")
        return s_, e_, OP.params_for(self.kind, s_, x_), OP.MU_THR[mu_]

    def sigs(self, setup, ename):
        k = (setup, ename)
        if k not in self._sig:
            _, meth, cap, kk = self.entries[ename]
            p_s = OP.params_for(self.kind, setup, "X0")
            self._sig[k] = YB.build_signals(self.st.bars, self.feats[setup], self.m, p_s, self.univ[setup],
                                            method=meth, cap=cap, k=kk, slip=YB.LIVE_SLIP)
        return self._sig[k]

    def trades(self, gid) -> W.Trades:
        s_, e_, p, mu = self.parts(gid)
        pop, _ = YB.population(self.sigs(s_, e_), self.st.bars, self.feats[s_], self.g0, self.g1, kind=self.kind,
                               p=p, cal=self.cal, mu_thr=mu)
        gin = np.array([ps.s.gd for ps in pop], dtype=np.int64)
        gout = np.array([ps.exit_gd if ps.exit_gd is not None else W.OPEN_GD for ps in pop], dtype=np.int64)
        r = np.array([ps.exit_px / ps.E - 1 - self.cost.rt(ps.s.gd, ps.exit_gd if ps.exit_gd is not None else self.g1)
                      for ps in pop])
        return W.Trades(gin, gout, r, W.week_keys([ps.s.ticker for ps in pop], gin, self.cal))

    def sizer(self, gid):
        if gid not in self._op:
            _, _, p, _ = self.parts(gid)
            sid = "vcp_breakout" if self.kind == "vcp" else "bull_flag_breakout"
            self._op[gid] = OpSizer(self.cls, sid, {k: v for k, v in p.items() if not k.startswith("_")},
                                    atr_keys=("atr14",))
        return self._op[gid]

    # ── 계좌: 신호마다 그 해의 조합 ─────────────────────────────────────────
    def book(self, path: "dict[int, str]", start: str, end: str, seeds, start_equity=float(C.BUDGET_C7)) -> list:
        cal = self.cal
        sbg, gid_of = defaultdict(list), {}
        cds = set()
        for y, gid in path.items():
            s_, e_, p, _ = self.parts(gid)
            cds.add(int(p["reentry_cooldown_days"]))
            a = int(cal.searchsorted(pd.Timestamp(f"{y}-01-01")))
            b = int(cal.searchsorted(pd.Timestamp(f"{y}-12-31"), side="right")) - 1
            for s in self.sigs(s_, e_):
                if a <= s.gd <= b:
                    sbg[s.gd].append(s)
                    gid_of[id(s)] = gid
        assert len(cds) == 1, cds
        cd = cds.pop()
        maxpos = {int(self.parts(g)[2]["max_positions"]) for g in set(path.values())}
        assert len(maxpos) == 1, maxpos
        runs = []
        for seed in seeds:
            cs = YB._CD(sbg, cd)

            def size_fn(s, B, used):
                gid = gid_of[id(s)]
                _, _, p, mu_thr = self.parts(gid)
                op = self.sizer(gid)
                P = int(round(s.E_raw))
                if s.m <= 0 or s.m < mu_thr:
                    return 0, "mu"
                N_raw = s.N * (s.E_raw / s.E)
                if op.blocks_entry(P, N_raw, budget=int(B), used=int(used), m=s.m, ticker=s.ticker):
                    return 0, "mu"
                q = op.qty(P, N_raw, budget=int(B), used=int(used), m=s.m, ticker=s.ticker)
                if q > 0:
                    return q, "ok"
                return 0, ("funds" if int(B) - int(used) < P else "design")

            def open_pos(s, q, _cs=cs):
                gid = gid_of[id(s)]
                s_, _, p, _ = self.parts(gid)
                return YB.YPos(s, self.st.bars[s.ticker], self.feats[s_][s.ticker], q, kind=self.kind, p=p, cal=cal,
                               mode="color", on_exit=_cs.note_exit)
            r = YB.run_book(cs, open_pos, size_fn, cal, start, end, seed, start_equity=start_equity, cost=self.cost,
                            max_pos=next(iter(maxpos)))
            runs.append(r)
        return runs


def main(kind: str, do_alt: bool = True):
    t0 = time.time()
    os.makedirs(CACHE, exist_ok=True)
    ctx = Ctx(kind)
    log(kind, "store", ctx.meta["tickers"], "features ready", f"{time.time()-t0:.0f}s")
    cal = ctx.cal
    pk = os.path.join(CACHE, f"{kind}_trades.pkl")
    if os.path.exists(pk):
        trades = pickle.load(open(pk, "rb"))
    else:
        trades = {}
        for i, gid in enumerate(ctx.ids):
            trades[gid] = ctx.trades(gid)
            if i % 12 == 0:
                log(kind, "pop", i, gid, len(trades[gid]), f"{trades[gid].r.mean():+.4f}", f"{time.time()-t0:.0f}s")
        pickle.dump(trades, open(pk, "wb"), protocol=pickle.HIGHEST_PROTOCOL)
    log(kind, "populations", len(trades), f"{time.time()-t0:.0f}s")

    alt = None
    if do_alt:
        ak = os.path.join(CACHE, f"{kind}_alt_curves.pkl")
        if os.path.exists(ak):
            alt = pickle.load(open(ak, "rb"))
        else:
            ta = time.time()
            alt = {}
            for i, gid in enumerate(ctx.ids):
                alt[gid] = {}
                for y in range(1997, 2026):
                    r = ctx.book({y: gid}, f"{y}-01-01", f"{y}-12-31", seeds=(0,))[0]
                    alt[gid][y] = r["equity"]
                if i % 12 == 0:
                    log(kind, "alt", i, f"{time.time()-ta:.0f}s")
                if time.time() - ta > 3600:
                    log(kind, "alt 60분 초과 — 생략(prereg §1-5)")
                    alt = None
                    break
            if alt is not None:
                pickle.dump(alt, open(ak, "wb"), protocol=pickle.HIGHEST_PROTOCOL)

    def book_fn(path, version):
        runs = ctx.book(path, "2007-01-02", END, seeds=C.BOOK_SEEDS)
        g0 = int(cal.searchsorted(pd.Timestamp("2007-01-02")))
        dates = cal[g0:g0 + len(runs[0]["equity"])]
        bs = W.book_summary([r["equity"] for r in runs], dates, float(C.BUDGET_C7),
                            fills=[r["counts"].get("fill", 0) for r in runs])
        bs["recon_max_abs"] = float(max(abs(r["recon"]) for r in runs))
        return bs

    res = W.run_wfo(cal=cal, combos=ctx.ids, cfgs=ctx.cfgs, trades=trades, current_id=OP.CURRENT_ID,
                    fixed_b_id=FIXED_B[kind], base_cfg=ctx.cfgs[OP.CURRENT_ID], min_tpy=YB.MIN_TRADES_PER_YEAR,
                    book_fn=book_fn, alt_curves=alt, log=lambda *a: log(kind, *a))
    res["strategy"] = kind
    res["cfgs"] = ctx.cfgs
    res["elapsed_s"] = time.time() - t0
    res["code_sha256"] = {f: W_sha(os.path.join(os.path.dirname(__file__), f)) for f in ("wfo_core.py", "wfo_bfbvcp.py")}
    od = os.path.join(OUT, kind)
    os.makedirs(od, exist_ok=True)
    with open(os.path.join(od, "result.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=W.js)
    log(kind, "done", f"{res['elapsed_s']:.0f}s", res["judge"]["r"]["label"])


def W_sha(p):
    import hashlib
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


if __name__ == "__main__":
    main(sys.argv[1], do_alt="--no-alt" not in sys.argv)
