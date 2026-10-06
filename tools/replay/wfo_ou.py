#!/usr/bin/env python3
"""주기적 재조정(걷기 전진) — 평균회귀 OU z 어댑터. 사전 등록 = ``wfo_20261006/prereg.md``.

입력 = 30년 재검증 1단계 피클(``scratchpad/y30mr/ou_stage1.pkl`` — 162조합 전체 기간 거래) + ``panel.pkl``.
계좌 = ``y30_mr_ou_judge.account(mode="p3")`` 그대로(거래 목록 기반이라 해마다 다른 조합의 거래를 이어 붙여 넣으면
정확히 이어 붙인 계좌가 된다 · z 순 결정적이라 씨앗 하나). 해 배정 = 신호일(``sig``, 30년 판정과 같음).

실행: python tools/replay/wfo_ou.py [--no-alt]
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_REPO = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import wfo_core as W  # noqa: E402
from replay import y30_mr_ou as OU  # noqa: E402
from replay import y30_mr_ou_judge as OJ  # noqa: E402
from replay.audit import config as C  # noqa: E402

OUT = os.path.join(_REPO, "_workspace/analysis/wfo_20261006/ou")
STAGE1 = os.path.join(os.path.dirname(C.SCRATCH), "y30mr", "ou_stage1.pkl")
FIXED_B = (-2.5, -0.5, 10.0, 2.0, "resid", "block0")
END = "2026-10-02"


def log(*a):
    print(time.strftime("%H:%M:%S"), "[ou]", *a, flush=True)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main(do_alt=True):
    t0 = time.time()
    payload = pickle.load(open(STAGE1, "rb"))
    panel = pickle.load(open(os.path.join(os.path.dirname(STAGE1), "panel.pkl"), "rb"))
    ctx = OJ.Ctx(payload, panel)
    cal = pd.DatetimeIndex(ctx.dates)
    yi = W.YearIndex(cal, END)
    tr = payload["trades"]
    ids = [OJ.keystr(k) for k in OU.GRID]
    key_of = dict(zip(ids, OU.GRID))
    cfgs = {OJ.keystr(k): dict(zip(("ez", "xz", "stop", "k", "mode", "mu"), k)) for k in OU.GRID}
    cur_id, b_id = OJ.keystr(OU.CURRENT), OJ.keystr(FIXED_B)
    wk = cal.isocalendar()
    wkey = (wk["year"].astype(str) + "-W" + wk["week"].map(lambda x: f"{x:02d}")).to_numpy()
    log("load", f"{time.time()-t0:.0f}s")

    trades = {}
    for c in ids:
        a = tr[key_of[c]]
        trades[c] = W.Trades(a["sig"].astype(np.int64), a["xi"].astype(np.int64), ctx.net(a),
                             np.array([f"{int(t)}|{wkey[int(e)]}" for t, e in zip(a["tj"], a["ei"])], dtype=object))
    log("trades", f"{time.time()-t0:.0f}s")

    def arr_of(path):
        parts = []
        for y, c in path.items():
            a = tr[key_of[c]]
            parts.append(a[(a["sig"] >= yi.first(y)) & (a["sig"] <= yi.last(y))])
        return np.concatenate(parts)

    def acct(path, a_, b_):
        r = OJ.account(ctx, arr_of(path), (a_, b_), mode="p3")
        eq = float(OJ.C7) * np.cumprod(1 + r["daily"])
        return eq, r

    alt = None
    if do_alt:
        ta = time.time()
        alt = {}
        for i, c in enumerate(ids):
            alt[c] = {}
            for y in range(1997, 2026):
                eq, _ = acct({y: c}, f"{y}-01-01", f"{y}-12-31")
                alt[c][y] = eq
            if i % 27 == 0:
                log("alt", i, f"{time.time()-ta:.0f}s")
            if time.time() - ta > 3600:
                alt = None
                log("alt 60분 초과 — 생략")
                break

    def book_fn(path, version):
        eq, r = acct(path, "2007-01-02", END)
        g0 = r["g0"]
        bs = W.book_summary([eq], cal[g0:g0 + len(eq)], float(OJ.C7), fills=[r["fills"]])
        bs["unaffordable_ratio"] = r["unaffordable_ratio"]
        return bs

    res = W.run_wfo(cal=cal, combos=ids, cfgs=cfgs, trades=trades, current_id=cur_id, fixed_b_id=b_id,
                    base_cfg=cfgs[cur_id], min_tpy=30, book_fn=book_fn, alt_curves=alt, start_equity=float(OJ.C7),
                    log=log)
    res["strategy"] = "ou"
    res["cfgs"] = cfgs
    res["elapsed_s"] = time.time() - t0
    res["code_sha256"] = {f: sha(os.path.join(os.path.dirname(__file__), f)) for f in ("wfo_core.py", "wfo_ou.py")}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "result.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=W.js)
    log("done", f"{res['elapsed_s']:.0f}s", res["judge"]["r"]["label"])


if __name__ == "__main__":
    main(do_alt="--no-alt" not in sys.argv)
