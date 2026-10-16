"""공용 루프 (prereg §5·§6). off · V0 · DS(도출 규칙) · DKR(국내만 도출, 보조) · ORC(신탁). 위약 8판은 DS·DKR(T·V).
off 판의 거래 목록을 따로 뽑아 둔다(전략 쪽 조건부 손익 진단용)."""
from __future__ import annotations

import os
import pickle
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "mu_riskoff_20261016"))
import common as CM  # noqa: E402
import dmvar  # noqa: E402

SCR = None
NAMES = ("V0", "DS", "DKR", "ORC")
PLACEBO = ("DS", "DKR")


def slim(cs):
    return [{"dates": c["dates"], "eq": c["eq"].astype(np.float64), "inv": c["inv"].astype(np.float32),
             "npos": c["npos"].astype(np.int16)} for c in cs]


def trades_of(runs):
    out = []
    for sd, r in enumerate(runs):
        for ps in r["trades"]:
            s = ps.s
            kq = getattr(s, "kq", None)
            if kq is None:
                kq = s.extra.get("kq") if hasattr(s, "extra") else None
            E = getattr(ps, "E", None) or getattr(s, "E", None)
            xp = getattr(ps, "exit_px", None)
            out.append((sd, s.ticker, int(s.gd), None if ps.exit_gd is None else int(ps.exit_gd),
                        None if (xp is None or not E) else float(xp) / float(E) - 1.0, float(ps.cost_basis), bool(kq)))
    return pd.DataFrame(out, columns=["seed", "ticker", "gd", "xgd", "gross", "cost_basis", "kq"])


def run(tag, cal, src, MU, base, setm, book, wins, prev_pkl, log):
    # DKR 배수표의 0.25 는 운영 상태표(1/0.75/0.5/0)에 없는 값 — 재현 계좌에서만 쓰도록 이름표 하나를 더한다(Snapshot.m 을 그대로 쓴다)
    from replay.audit import sizing as SZ
    SZ._STATE_OF_M.setdefault(0.25, "down_rising")
    ser = pd.read_csv(os.path.join(SCR, "series.csv"), index_col=0, parse_dates=True)
    ks = ser["kospi"].dropna()
    MS = dmvar.all_days(cal, src, MU, NAMES, (ks.index, ks.to_numpy(float)))
    prev = pickle.load(open(prev_pkl, "rb"))
    for mk in ("kospi", "kosdaq"):
        a, b = MS["V0"][mk], np.asarray(prev["m"][mk], float)
        same = np.array_equal(np.isnan(a), np.isnan(b)) and np.array_equal(a[~np.isnan(a)], b[~np.isnan(b)])
        log("repro-m", mk, same)
        if not same:
            raise SystemExit("V0 m 계열 불일치 — 중단")
    R = {"cal": np.asarray(cal), "m": MS, "book": {}, "curves": {}, "trades": {}}
    plan = [("off", None, ("T", "V", "H"))]
    for nm in NAMES:
        plan.append((nm, (MS[nm]["kospi"], MS[nm]["kosdaq"]), ("T", "V", "H")))
        if nm in PLACEBO:
            for sh in CM.SHIFTS:
                plan.append((f"{nm}|plc{sh}", (CM.shifted(MS[nm]["kospi"], sh), CM.shifted(MS[nm]["kosdaq"], sh)), ("T", "V")))
    for vn, mm, ws in plan:
        sg = setm(base, mm)
        for wn in ws:
            bk = book(sg, wn, vn)
            runs = CM.take()
            R["book"][(vn, wn)] = bk
            R["curves"][(vn, wn)] = slim(CM.curves(runs, cal, wins[wn]))
            if vn == "off":
                R["trades"][wn] = trades_of(runs)
            if vn in ("off", "V0"):
                pv = prev["book"][("on" if vn == "V0" else "off", wn)]
                d = max(abs(bk["cagr"] - pv["cagr"]), abs(bk["mdd"] - pv["mdd"]))
                log("repro-book", vn, wn, d)
                if d > 1e-9:
                    raise SystemExit("V0/off 계좌 재현 실패 — 중단")
            if "|" not in vn:
                log(vn, wn, round(bk["cagr"], 5), round(bk["mdd"], 5))
    os.makedirs(os.path.join(SCR, "md"), exist_ok=True)
    out = os.path.join(SCR, "md", f"{tag}.pkl")
    with open(out, "wb") as fh:
        pickle.dump(R, fh, protocol=4)
    log("done", out)
