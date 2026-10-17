"""바닥 상향 후보 루프 (prereg §1~§2). off · V0 · F2 · F3 · U2 · U3 · Z.
위약 8판 = F2·F3·U2·U3 (T·V). off 판 거래 목록 · 덧댄(m>1) 사이징 깎임 집계를 같이 남긴다."""
from __future__ import annotations

import os
import pickle
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "mu_riskoff_20261016"))
sys.path.insert(0, os.path.join(HERE, "..", "mu_variants_20261016"))
import common as CM  # noqa: E402
import mvar  # noqa: E402  (to_days 재사용)

SCR = None
NAMES = tuple(x for x in os.environ.get("VARIANTS", "V0,F2,F3,U2,U3,Z").split(",") if x)
PLACEBO = ("F2", "F3", "U2", "U3")
MAP = {
    "V0": lambda m: m,
    "F2": lambda m: (1.0 + m) / 2.0,
    "F3": lambda m: (1.0 + 2.0 * m) / 3.0,
    "U2": lambda m: 1.0 + m,
    "U3": lambda m: 1.0 + 2.0 * m,
    "Z": lambda m: np.where(m == 0.0, 1.0, m),
}
CUR = {"vn": None, "wn": None}
CUTS = defaultdict(lambda: defaultdict(float))


def install_patches():
    """분석 프로세스 안에서만 — 파일 무변경 (prereg §1 「운영 사이징 재현 — m 이 1 보다 클 때」)."""
    from replay.audit import sizing as SZ
    from src.engine.strategy_base import StrategyBase as SB

    class _Lab(dict):
        def __missing__(self, k):
            return "up_rising" if k >= 1.0 else ("up_falling" if k >= 0.75 else ("down_rising" if k > 0 else "down_falling"))
    SZ._STATE_OF_M = _Lab(SZ._STATE_OF_M)

    orig = SB._market_unit_sizing

    def patched(self, current_price, ticker):
        try:
            view = self._market_unit_view(ticker)
            if view.mode == "enforce" and view.m > 1.0:
                lots = self._market_unit_lots(current_price, ticker, view.m)
                if lots.design_before > 0:
                    return lots
                return None
        except Exception:
            return None
        return orig(self, current_price, ticker)
    SB._market_unit_sizing = patched

    oq = SZ.OpSizer.qty

    def qty(self, price, atr, *, budget, used, m, ticker="999999", extra=None):
        q = oq(self, price, atr, budget=budget, used=used, m=m, ticker=ticker, extra=extra)
        vn = CUR["vn"]
        if vn and "|" not in vn and m is not None and m == m and m > 0:
            try:
                l1 = self.s._market_unit_lots(int(price), ticker, 1.0)
                lm = self.s._market_unit_lots(int(price), ticker, float(m))
            except Exception:
                return q
            key = (vn, CUR["wn"], round(float(m), 4))
            c = CUTS[key]
            c["n"] += 1
            if l1.design_before > 0:
                c["n_d1"] += 1
                c["eff_sum"] += q / l1.design_before
                c["nom_sum"] += lm.design_after / l1.design_before
                c["cut_vs_design_m"] += int(q < lm.design_after)
                c["remain_bind"] += int(lm.design_after > lm.remaining_qty)
            c["zero"] += int(q <= 0)
        return q
    SZ.OpSizer.qty = qty


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


def counts_of(runs):
    c = defaultdict(int)
    for r in runs:
        for k, v in (r.get("counts") or {}).items():
            c[k] += v
    return dict(c)


def run(tag, cal, src, MU, base, setm, book, wins, prev_pkl, log):
    install_patches()
    v0 = mvar.all_days(cal, src, MU, ("V0",))["V0"]
    prev = pickle.load(open(prev_pkl, "rb"))
    for mk in ("kospi", "kosdaq"):
        a, b = v0[mk], np.asarray(prev["m"][mk], float)
        same = np.array_equal(np.isnan(a), np.isnan(b)) and np.array_equal(a[~np.isnan(a)], b[~np.isnan(b)])
        log("repro-m", mk, same)
        if not same:
            raise SystemExit("V0 m 계열 불일치 — 중단")
    MS = {}
    for nm in NAMES:
        MS[nm] = {}
        for mk in ("kospi", "kosdaq"):
            a = v0[mk]
            out = np.full(len(a), np.nan)
            ok = np.isfinite(a)
            out[ok] = MAP[nm](a[ok])
            MS[nm][mk] = out
    R = {"cal": np.asarray(cal), "m": MS, "book": {}, "curves": {}, "trades": {}, "counts": {}}
    plan = [("off", None, ("T", "V", "H"))]
    for nm in NAMES:
        plan.append((nm, (MS[nm]["kospi"], MS[nm]["kosdaq"]), ("T", "V", "H")))
        if nm in PLACEBO:
            for sh in CM.SHIFTS:
                plan.append((f"{nm}|plc{sh}", (CM.shifted(MS[nm]["kospi"], sh), CM.shifted(MS[nm]["kosdaq"], sh)), ("T", "V")))
    for vn, mm, ws in plan:
        sg = setm(base, mm)
        for wn in ws:
            CUR["vn"], CUR["wn"] = vn, wn
            bk = book(sg, wn, vn)
            runs = CM.take()
            R["book"][(vn, wn)] = bk
            R["curves"][(vn, wn)] = slim(CM.curves(runs, cal, wins[wn]))
            if "|" not in vn:
                R["counts"][(vn, wn)] = counts_of(runs)
            if vn in ("off", "V0", "Z", "U2"):
                R["trades"][(vn, wn)] = trades_of(runs)
            if vn in ("off", "V0"):
                pv = prev["book"][("on" if vn == "V0" else "off", wn)]
                d = max(abs(bk["cagr"] - pv["cagr"]), abs(bk["mdd"] - pv["mdd"]))
                log("repro-book", vn, wn, d)
                if d > 1e-9:
                    raise SystemExit("V0/off 계좌 재현 실패 — 중단")
            if "|" not in vn:
                log(vn, wn, round(bk["cagr"], 5), round(bk["mdd"], 5))
    CUR["vn"] = None
    R["cuts"] = {k: dict(v) for k, v in CUTS.items()}
    os.makedirs(os.path.join(SCR, "mf"), exist_ok=True)
    out = os.path.join(SCR, "mf", f"{tag}.pkl")
    with open(out, "wb") as fh:
        pickle.dump(R, fh, protocol=4)
    log("done", out)
