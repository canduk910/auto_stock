#!/usr/bin/env python3
"""주기적 재조정(걷기 전진) — donchian_swing(깡토 개조) 어댑터. 사전 등록 = ``wfo_20261006/prereg.md``.

30년 재검증 층(``strategies/donchian_y30.py`` · ``donchian_y30_data.py``)을 그대로 쓴다. 해마다 30년 B 와 같은
**단계 선택**: 단계 A(진입 24, 청산 현행) → 그 진입으로 단계 B(청산 81). 계좌 설정(단계 C)은 현행 고정.
체결 = 시가 · 비용 = 시기별. 고정 B 판 = 30년 B 의 (A, B, C) 그대로.

실행: python tools/replay/wfo_donchian.py [--no-alt]
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
from replay.audit.sizing import OpSizer, load_strategy_class  # noqa: E402
from replay.strategies import donchian_kk as DK  # noqa: E402
from replay.strategies import donchian_kk_audit as DA  # noqa: E402
from replay.strategies import donchian_y30 as DY  # noqa: E402
from replay.strategies import donchian_y30_data as YD  # noqa: E402

OUT = os.path.join(_REPO, "_workspace/analysis/wfo_20261006/donchian")
CACHE = os.path.join(os.path.dirname(C.SCRATCH), "wfo")
START, END = "1997-01-02", "2026-10-02"
FIXED_B = (dict(entry_n=20, vol_mult=1.5, clv=None, mu="m1"), dict(r=(10.0, 1.5), be_r=4.0, time_bars=30, chan=30),
           dict(slots=(6, 0.15), daily_cap=5))


def log(*a):
    print(time.strftime("%H:%M:%S"), "[donchian]", *a, flush=True)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def norm(d):
    return {k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()}


def cid_of(en, ex):
    return (f"A:{en['entry_n']}/{en['vol_mult']}/{en['clv']}/{en['mu']}"
            f"|B:{ex['r'][0]:g}%-{ex['r'][1]:g}ATR/be{ex['be_r']:g}/t{ex['time_bars']}/ch{ex['chan']}")


class Ctx:
    def __init__(self):
        self.st, self.m, self.kser, self.info = YD.build(DY.CACHE)
        self.cal = self.st.cal
        DY._CAL["cal"] = self.cal
        self.bars = self.st.bars
        self.era = DY.Costs(self.cal)
        self.cls = load_strategy_class(DA.BRANCH_DONCHIAN, "DonchianSwingStrategy", "y30_branch_donchian_kk")
        if DA.PN.sha256(DA.BRANCH_DONCHIAN) != DA.BRANCH_SHA:
            raise SystemExit("브랜치 전략 파일 sha256 불일치")
        self.g0 = int(self.cal.searchsorted(pd.Timestamp(START)))
        self.g1 = int(self.cal.searchsorted(pd.Timestamp(END), side="right")) - 1
        self.fc = {}
        self.cfg = {}            # id → (entry, exit)
        self.flat = {}           # id → 진입·청산 합친 설정(안정성 축 비교용, 등록 때마다 늘어난다)
        self._op = {}

    def register(self, en, ex) -> str:
        i = cid_of(en, ex)
        self.cfg[i] = (dict(en), dict(ex))
        self.flat[i] = {**en, **norm(ex)}
        return i

    def sigs(self, en, kk):
        key = (en["entry_n"], en["vol_mult"], en["clv"])
        if key not in self.fc:
            feats = {t: DY.features_y30(b, entry_n=key[0], vol_mult=key[1], clv=key[2]) for t, b in self.bars.items()}
            self.fc[key] = (feats, DK.build_signals(self.bars, feats, self.m))
        feats, raw = self.fc[key]
        sg = [s for s in raw if not DA.r_half_blocked(s.E, s.N, kk)]
        return feats, DY.mu_apply(sg, en["mu"])

    def parts(self, cid, acct=DY.ACCT0):
        en, ex = self.cfg[cid]
        kk = DY.kk_of(ex, acct)
        feats, sg = self.sigs(en, kk)
        fv = {t: DY.feats_view(f, ex["chan"]) for t, f in feats.items()}
        return en, ex, kk, sg, fv

    def trades(self, cid) -> W.Trades:
        en, ex, kk, sg, fv = self.parts(cid)
        pop = DY.population(sg, self.bars, fv, self.g0, self.g1, kk=kk)
        gin = np.array([p.s.gd for p in pop], dtype=np.int64)
        gout = np.array([p.exit_gd if p.exit_gd is not None else W.OPEN_GD for p in pop], dtype=np.int64)
        r = np.array([p.exit_px / p.E - 1 - self.era.rt(p.s.gd, p.exit_gd if p.exit_gd is not None else self.g1)
                      for p in pop])
        return W.Trades(gin, gout, r, W.week_keys([p.s.ticker for p in pop], gin, self.cal))

    def sizer(self, cid, acct):
        k = (cid, str(acct))
        if k not in self._op:
            en, ex = self.cfg[cid]
            kk = DY.kk_of(ex, acct)
            self._op[k] = OpSizer(self.cls, "donchian_swing", {
                "market_unit_mode": "enforce", "risk_pct": kk["risk_pct"], "position_ratio": acct["slots"][1],
                "max_positions": acct["slots"][0], "kk_r_floor_pct": ex["r"][0], "kk_r_atr_mult": ex["r"][1]})
        return self._op[k]

    def book(self, path, start, end, seeds, acct=DY.ACCT0, start_equity=float(C.BUDGET_C7)) -> list:
        cal = self.cal
        sbg, info = defaultdict(list), {}
        for y, cid in path.items():
            en, ex, kk, sg, fv = self.parts(cid, acct)
            a = int(cal.searchsorted(pd.Timestamp(f"{y}-01-01")))
            b = int(cal.searchsorted(pd.Timestamp(f"{y}-12-31"), side="right")) - 1
            for s in sg:
                if a <= s.gd <= b:
                    sbg[s.gd].append(s)
                    info[id(s)] = (cid, kk, fv)
        kk0 = DY.kk_of(DY.EXIT0, acct)

        def opsize(s, B, used):
            cid, kk, _ = info[id(s)]
            P = int(round(s.E_raw))
            if s.m <= 0 or P <= 0:
                return 0, "mu"
            q = self.sizer(cid, acct).qty(P, s.N * (s.E_raw / s.E), budget=int(B), used=int(used), m=s.m)
            if q > 0:
                return q, "ok"
            return 0, ("funds" if int(B) - int(used) < P else "design")

        def open_pos(s, q):
            cid, kk, fv = info[id(s)]
            return DY.Y30Pos(s, self.bars[s.ticker], fv[s.ticker], q, mode="color", kk=kk)
        return [DY.run_book(sbg, open_pos, opsize, cal, start, end, sd, start_equity=start_equity, costs=self.era,
                            max_pos=kk0["max_pos"], daily_cap=kk0["daily_cap"]) for sd in seeds]


def main(do_alt=True):
    t0 = time.time()
    os.makedirs(CACHE, exist_ok=True)
    ctx = Ctx()
    cal = ctx.cal
    yi = W.YearIndex(cal)
    log("store", f"{time.time()-t0:.0f}s")
    A_ids = [ctx.register(en, DY.EXIT0) for en in DY.GRID_A]
    cur_id = cid_of(DY.ENTRY0, DY.EXIT0)
    b_id = ctx.register(*FIXED_B[:2])
    pk = os.path.join(CACHE, "donchian_trades.pkl")
    trades = pickle.load(open(pk, "rb")) if os.path.exists(pk) else {}

    def ensure(ids):
        new = [i for i in ids if i not in trades]
        for i in new:
            trades[i] = ctx.trades(i)
        if new:
            pickle.dump(trades, open(pk, "wb"), protocol=pickle.HIGHEST_PROTOCOL)
            log("pop +", len(new), "total", len(trades), f"{time.time()-t0:.0f}s")
    ensure(A_ids + [b_id])
    base_cfg = {**DY.ENTRY0, **{k: (tuple(v) if isinstance(v, list) else v) for k, v in DY.EXIT0.items()}}

    def cfgs():
        return ctx.flat

    min_tpy = DY.MIN_TRADES_PER_YEAR

    def B_ids_for(a_id):
        en = ctx.cfg[a_id][0]
        return [ctx.register(en, ex) for ex in DY.GRID_B]

    def select_fn(y):
        sA = W.select_year(yi, y, A_ids, trades, cfgs(), base_cfg, min_tpy, cur_id)
        a = sA["chosen"]
        bids = B_ids_for(a)
        ensure(bids)
        sB = W.select_year(yi, y, bids, trades, cfgs(), base_cfg, min_tpy, a)
        out = dict(sB)
        out["stage_A"] = {k: v for k, v in sA.items() if k != "rows"}
        out["n_eligible"] = (sA["n_eligible"], sB["n_eligible"])
        out["fallback"] = bool(sA["fallback"] or sB["fallback"])
        return out

    alt_fn = None
    if do_alt:
        ak = os.path.join(CACHE, "donchian_alt_curves.pkl")
        curves = pickle.load(open(ak, "rb")) if os.path.exists(ak) else {}
        ta = [time.time(), False]

        def curves_for(ids):
            new = [i for i in ids if i not in curves]
            for i in new:
                curves[i] = {yy: ctx.book({yy: i}, f"{yy}-01-01", f"{yy}-12-31", seeds=(0,))[0]["equity"]
                             for yy in range(1997, 2026)}
            if new:
                pickle.dump(curves, open(ak, "wb"), protocol=pickle.HIGHEST_PROTOCOL)
                log("alt curves +", len(new), f"{time.time()-ta[0]:.0f}s")
            if time.time() - ta[0] > 3600:
                ta[1] = True

        def pick_mar(y, ids, base_id):
            elig = {i: len(trades[i].take(yi.train_mask(trades[i], y))) >= min_tpy * W.TRAIN_YEARS for i in ids}
            metric = {i: W.chained_mar(curves[i], list(range(y - 10, y)), float(C.BUDGET_C7)) for i in ids}
            return W.select_year_by_metric(y, ids, metric, elig, cfgs(), base_cfg, base_id)

        def alt_fn(y):
            if ta[1]:
                return {"year": y, "chosen": cur_id, "fallback": True, "skipped": "60분 초과"}
            curves_for(A_ids)
            sa = pick_mar(y, A_ids, cur_id)
            bids = B_ids_for(sa["chosen"])
            ensure(bids)
            curves_for(bids)
            sb = pick_mar(y, bids, sa["chosen"])
            return {"year": y, "chosen": sb["chosen"], "fallback": bool(sa["fallback"] or sb["fallback"]),
                    "stage_A": sa}

    def book_fn(path, version, acct=DY.ACCT0):
        runs = ctx.book(path, "2007-01-02", END, seeds=C.BOOK_SEEDS, acct=acct)
        bs = W.book_summary([r["equity"] for r in runs], runs[0]["dates"], float(C.BUDGET_C7),
                            fills=[r["counts"].get("fill", 0) for r in runs])
        bs["recon_max_abs"] = float(max(abs(r["recon"]) for r in runs))
        return bs

    def book_fn_dispatch(path, version):
        # 고정 B 판만 그 판의 계좌 설정(단계 C), 나머지는 현행 계좌 설정
        if set(path.values()) == {b_id}:
            return book_fn(path, version, acct=FIXED_B[2])
        return book_fn(path, version)

    res = W.run_wfo(cal=cal, combos=A_ids, cfgs=cfgs(), trades=trades, current_id=cur_id, fixed_b_id=b_id,
                    base_cfg=base_cfg, min_tpy=min_tpy, book_fn=book_fn_dispatch, select_fn=select_fn,
                    alt_select_fn=alt_fn, log=log)
    res["stage_A_by_year"] = {y: res["selection"][y].get("stage_A") for y in res["years"]}
    res["strategy"] = "donchian"
    res["cfgs"] = {k: v for k, v in cfgs().items() if k in set(res["path"].values()) | {cur_id, b_id}}
    res["elapsed_s"] = time.time() - t0
    res["code_sha256"] = {f: sha(os.path.join(os.path.dirname(__file__), f)) for f in ("wfo_core.py", "wfo_donchian.py")}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "result.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=W.js)
    log("done", f"{res['elapsed_s']:.0f}s", res["judge"]["r"]["label"])


if __name__ == "__main__":
    main(do_alt="--no-alt" not in sys.argv)
