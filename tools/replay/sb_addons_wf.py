#!/usr/bin/env python3
"""주기적 재조정(wfo) 「재조정판」 계좌 곡선 — 사전 등록 §5.

각 wfo 어댑터의 ``main`` 을 그대로 부르되 ``wfo_core.run_wfo`` 를 바꿔 끼워, 해마다 다시 고르지 않고
``result.json`` 에 저장된 경로(``path``)로 계좌(``book_fn``)만 돈다. ``wfo_core.book_summary`` 를 감싸
씨앗 16 의 일별 평가액을 붙잡는다. 어댑터의 ``OUT`` 은 스크래치로 돌려 커밋된 result.json 을 덮지 않는다.

    python tools/replay/sb_addons_wf.py <out_dir> [vcp bfb kojiro donchian vb ou etf_trend]
"""
from __future__ import annotations

import json
import os
import sys
import time

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY", "KIS_APP_KEY_REAL",
           "KIS_APP_SECRET_REAL", "KIS_ACCOUNT_NO_REAL", "KIS_APP_KEY_VTS", "KIS_APP_SECRET_VTS", "KIS_ACCOUNT_NO_VTS",
           "DATABASE_URL"):
    os.environ.setdefault(_k, "audit-dummy")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from replay import sb_addons_core as S  # noqa: E402
from replay import wfo_core as W  # noqa: E402

WFO_DIR = os.path.join(_ROOT, "_workspace/analysis/wfo_20261006")
SCRATCH_OUT = "/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/sb_addons/wfo_out"


class _Done(Exception):
    pass


def _paths(sid: str) -> "dict[str, dict[int, str]]":
    d = json.load(open(os.path.join(WFO_DIR, sid, "result.json")))
    if sid == "vb":
        return {v: {int(y): c for y, c in d[v]["path"].items()} for v in ("opt", "pes")}, d
    return {"r": {int(y): c for y, c in d["path"].items()}}, d


def _books_ref(sid, d, v):
    return (d[v] if sid == "vb" else d)["books"]["wfo"]["r"]


def run(sid: str) -> list:
    """반환 = [{version, dates, equities(16), ref}]"""
    import importlib
    paths, res = _paths(sid)
    modname = {"vcp": "wfo_bfbvcp", "bfb": "wfo_bfbvcp", "etf_trend": "wfo_etf"}.get(sid, f"wfo_{sid}")
    M = importlib.import_module(f"replay.{modname}")
    M.OUT = os.path.join(SCRATCH_OUT, sid)                # 커밋된 result.json 을 덮지 않는다
    grabbed, calls = [], [0]
    orig_bs, orig_run = W.book_summary, W.run_wfo

    def bs(equities, dates, *a, **k):
        se = a[0] if a else k["start_equity"]
        grabbed.append({"equities": [np.asarray(e, float) for e in equities], "dates": pd.DatetimeIndex(dates),
                        "start": float(se)})
        return orig_bs(equities, dates, *a, **k)

    ctx_box = {}
    if sid == "donchian":
        orig_init = M.Ctx.__init__

        def init(self, *a, **k):
            orig_init(self, *a, **k)
            ctx_box["ctx"] = self
        M.Ctx.__init__ = init

    def stub(**kw):
        v = ("opt", "pes")[calls[0]] if sid == "vb" else "r"
        calls[0] += 1
        path = paths[v]
        if sid == "donchian":
            ctx = ctx_box["ctx"]
            need = set(path.values()) - set(ctx.cfg)
            for en in M.DY.GRID_A:
                for ex in M.DY.GRID_B:
                    if M.cid_of(en, ex) in need:
                        ctx.register(en, ex)
            for en in M.DY.GRID_A:
                if M.cid_of(en, M.DY.EXIT0) in need:
                    ctx.register(en, M.DY.EXIT0)
            miss = set(path.values()) - set(ctx.cfg)
            if miss:
                raise SystemExit(f"[wf] donchian 경로 id 를 격자에서 못 찾음: {sorted(miss)[:3]}")
        n0 = len(grabbed)
        summ = kw["book_fn"](path, "r")
        assert len(grabbed) == n0 + 1
        grabbed[-1].update(version="opt" if v in ("r", "opt") else "pes", summary=summ,
                           ref=_books_ref(sid, res, v if sid == "vb" else "r"))
        if sid == "vb" and calls[0] == 1:
            return {"judge": {"r": {"label": "stub"}}}
        raise _Done

    W.book_summary, W.run_wfo = bs, stub
    try:
        if sid in ("vcp", "bfb"):
            M.main(sid, do_alt=False)
        else:
            M.main(do_alt=False)
    except _Done:
        pass
    finally:
        W.book_summary, W.run_wfo = orig_bs, orig_run
    return grabbed


def pack(sid, g) -> dict:
    eqs, dates = g["equities"], g["dates"]
    start = g["start"]
    rep = S.rep_index([e[-1] for e in eqs])
    d0 = dates[0] - pd.Timedelta(1, unit="D")
    summ, ref = g["summary"], g["ref"]
    meta = {"sid": sid, "version": g["version"], "rep_seed": rep, "n_seeds": len(eqs), "start_equity": start,
            "cagr_median": summ["cagr_median"], "mdd_median": summ["mdd_median"],
            "ref_cagr_median": ref["cagr_median"], "ref_mdd_median": ref["mdd_median"],
            "diff_cagr": summ["cagr_median"] - ref["cagr_median"], "diff_mdd": summ["mdd_median"] - ref["mdd_median"],
            "cagr_min": summ["cagr_min"], "cagr_max": summ["cagr_max"]}
    return {"dates": np.array([str(d0.date())] + [str(d.date()) for d in dates]),
            "equity": np.r_[start, eqs[rep]], "meta": meta}


def main():
    out_dir = sys.argv[1]
    names = sys.argv[2:] or ["vcp", "bfb", "kojiro", "donchian", "vb", "ou", "etf_trend"]
    os.makedirs(out_dir, exist_ok=True)
    for sid in names:
        t0 = time.time()
        for g in run(sid):
            p = pack(sid, g)
            path = os.path.join(out_dir, f"WF_{sid}__{p['meta']['version']}.npz")
            np.savez_compressed(path, dates=p["dates"], equity=p["equity"], meta=json.dumps(p["meta"]))
            m = p["meta"]
            print(f"[wf] {sid} {m['version']} {time.time() - t0:.0f}s → {path} · CAGR 중앙 {m['cagr_median']:+.4f} "
                  f"(공표 {m['ref_cagr_median']:+.4f}) · 낙폭 {m['mdd_median']:+.3f} (공표 {m['ref_mdd_median']:+.3f})",
                  flush=True)


if __name__ == "__main__":
    main()
