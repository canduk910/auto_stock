#!/usr/bin/env python3
"""etf_trend 효율화(2026-10-05) — 사전 등록 ``_workspace/analysis/strategy_opt_20261005/etf_trend/prereg.md`` 실행기.

현행판 = 전수 점검 「운영 해석판」(원본가 판정 · 분배 포함 수익 · 시장 유닛 shadow · 비용 0.38%).
격자 108 = 진입선 L{20,40,60} × 트레일링{1.8N,3.0N,없음} × 채널{10,20} × 15:20 돌파 실패{켬,끔} × 시장 유닛{m>0,m≥0.75,m=1}.
선택은 학습 T 에서만, 판정은 검증 V 한 번, 보류 H 는 부호만. 비교 기준선 B1~B3(069500)은 보고만.

실행: python tools/replay/strategies/etf_trend_opt.py [--out PATH]
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import date

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay.audit import bars as BR  # noqa: E402
from replay.audit import book as BK  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import indicators as IND  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.strategies import etf_trend_b as EB  # noqa: E402
from replay.strategies import etf_trend_b_audit as EA  # noqa: E402

COST = C.COST_RT_JUDGE
T_WIN = ("2020-10-05", "2023-09-29")
T_SUB = (("2020-10-05", "2021-09-30"), ("2021-10-01", "2022-09-30"), ("2022-10-01", "2023-09-29"))
V_WIN = ("2023-10-04", "2025-10-02")
H_WIN = ("2025-10-10", "2026-09-23")
MIN_TRADES_PER_YEAR = 30
N_BOOT_DIFF = 20000
BONF_Q = 0.10 / 108

L_GRID = (20, 40, 60)
TR_GRID = (1.8, 3.0, None)
CH_GRID = (10, 20)
BL_GRID = (True, False)
MU_GRID = ("gt0", "ge075", "eq1")
CURRENT = (20, 1.8, 10, True, "gt0")


def grid() -> list:
    return list(itertools.product(L_GRID, TR_GRID, CH_GRID, BL_GRID, MU_GRID))


def combo_name(cb) -> str:
    L, tr, ch, bl, mu = cb
    return f"L{L}|TR{'off' if tr is None else tr}|CH{ch}|BL{'on' if bl else 'off'}|MU{mu}"


def mu_ok(m: float, mu: str) -> bool:
    if m is None or m != m:
        return False
    return {"gt0": m > 0, "ge075": m >= 0.75, "eq1": m >= 1.0}[mu]


def years(win) -> float:
    return (pd.Timestamp(win[1]) - pd.Timestamp(win[0])).days / 365.25


# ── 청산(일반화) ─────────────────────────────────────────────────────────

def sim_v(d: dict, j: int, line: float, trail, chan: int, bl: bool, mode: str = "color"):
    """``EB.sim_b`` 의 일반화. (L=20 선 · trail 1.8 · chan 10 · bl 켬) 이면 ``sim_b`` 와 같다."""
    E = d["o"][j + 1]
    N = d["n14"][j]
    hard = max(E - 2.0 * N, E * 0.91)
    stop, hsb = hard, -np.inf
    n = len(d["c"])
    D = j + 1
    for k in range(D, n):
        ch = np.min(d["l"][max(0, k - chan):k]) if k >= D + 1 else -np.inf

        def lines(stop=stop, ch=ch):
            ls = [BR.Line(stop, "stop")]
            if np.isfinite(ch):
                ls.append(BR.Line(ch, "chan10", strict=True))
            return ls

        o = d["o"][k]
        if o <= stop or o < ch:
            return k, o, ("stop_gap" if o <= stop else "chan10_gap")
        ex = BR.walk_bar(o, d["h"][k], d["l"][k], d["c"][k], lines_fn=lines, mode=mode, ratchet="next_bar",
                         gap_check=False, pick=EB._pick)
        if ex is not None:
            return k, ex.px, ex.reason
        if bl and k >= D + 2 and d["c"][k] < line:
            return k, d["c"][k], "below_line"
        hsb = max(hsb, d["h"][k])
        be = E if hsb >= E + 1.5 * N else -np.inf
        stop = max(hard, be, (hsb - trail * N) if trail is not None else -np.inf)
    return n - 1, d["c"][n - 1], "end"


class EtfPosV(EA.EtfPos):
    """계좌용 한 랏 — ``EA.EtfPos`` 에 트레일링·채널·돌파 실패 축만 바꾼다."""

    def __init__(self, sig, d, qty, *, trail=1.8, chan=10, bl=True, mode="color", fadj=None):
        super().__init__(sig, d, qty, mode=mode, fadj=fadj)
        self.trail, self.chan, self.bl = trail, chan, bl

    def _ch(self, ti):
        if ti >= self.s.ti + 1:
            return float(np.min(self.d["l"][max(0, ti - self.chan):ti]))
        return -np.inf

    def intraday_phase(self, ti: int, gd: int, is_entry: bool) -> bool:
        self._kupd(ti)
        d = self.d
        ch = self._ch(ti)

        def lines():
            ls = [BR.Line(self.stop, "stop")]
            if np.isfinite(ch):
                ls.append(BR.Line(ch, "chan10", strict=True))
            return ls

        ex = BR.walk_bar(d["o"][ti], d["h"][ti], d["l"][ti], d["c"][ti], lines_fn=lines, mode=self.mode,
                         ratchet="next_bar", gap_check=False, pick=EB._pick)
        if ex is not None:
            self._exit(ex.px, ex.reason, gd, ti)
            return True
        if self.bl and ti >= self.s.ti + 2 and d["c"][ti] < self.s.line:
            self._exit(d["c"][ti], "below_line", gd, ti)
            return True
        self.last_px = d["c"][ti]
        self.hsb = max(self.hsb, d["h"][ti])
        be = self.E if self.hsb >= self.E + 1.5 * self.s.N else -np.inf
        tr = (self.hsb - self.trail * self.s.N) if self.trail is not None else -np.inf
        self.stop = max(self.hard, be, tr)
        return False


def run_path_v(sig, d, *, trail, chan, bl, mode="color") -> EtfPosV:
    ps = EtfPosV(sig, d, 1, trail=trail, chan=chan, bl=bl, mode=mode)
    n = len(d["c"])
    for ti in range(sig.ti, n):
        gd = int(d["ci"][ti])
        if ti > sig.ti and ps.open_phase(ti, gd):
            return ps
        if ps.intraday_phase(ti, gd, ti == sig.ti):
            return ps
    ps._exit(d["c"][n - 1], "end", int(d["ci"][n - 1]), n - 1)
    return ps


# ── 신호(진입선 L) ───────────────────────────────────────────────────────

def gen_signals(data: dict, cls: dict, mu: np.ndarray, L: int) -> list:
    """``EB.gen_trades`` 의 진입 조건 그대로 — 돌파선만 직전 L봉 고가. 청산은 따로 붙인다."""
    out = []
    for t, d in data.items():
        if not cls.get(t):
            continue
        hpL = d["hi_prev20"] if L == 20 else d.setdefault(f"hi_prev{L}", IND.prior_max(d["h"], L))
        n = len(d["c"])
        e60 = d["e60"]
        for j in range(EB.MIN_BARS - 1, n - 1):
            ci = d["ci"][j]
            if d["ci"][j + 1] != ci + 1:
                continue
            c = d["c"][j]
            a20 = d["atr20"][j]
            atr_pct = a20 / c
            if not (d["tv20"][j] >= EB.TV20_MIN and d["craw"][j] >= EB.PX_MIN and atr_pct >= EB.ATR_LO):
                continue
            hp = hpL[j]
            if not (hp > 0 and c > hp):
                continue
            if not (e60[j] > e60[j - 1] and c > e60[j]):
                continue
            tvp = d["tvprev20"][j]
            if not (tvp > 0 and d["tv"][j] >= 1.5 * tvp):
                continue
            N = d["n14"][j]
            if not (N > 0):
                continue
            o1 = d["o"][j + 1]
            if o1 >= c * 1.03 or o1 > hp * 1.04:
                continue
            m = mu[ci]
            out.append({"ticker": t, "j": int(j), "sig_ci": int(ci), "entry_ci": int(ci + 1), "line": float(hp),
                        "E": float(o1), "N": float(N), "rw": float(2.0 * N), "m": float(m) if m == m else None,
                        "tv20": float(d["tv20"][j]),
                        "fu": bool(d["mc"][j] >= EB.MCAP_MIN and d["craw"][j] <= EB.PX_MAX
                                   and atr_pct <= EB.ATR_HI and d["qual60"][j])})
    return out


def attach_exit(sigs: list, data: dict, fadj: dict, cal, trail, chan, bl, mode="color") -> list:
    out = []
    for s in sigs:
        d = data[s["ticker"]]
        k, px, why = sim_v(d, s["j"], s["line"], trail, chan, bl, mode=mode)
        f = fadj[s["ticker"]]
        ret = EA.adj_return(s["E"], px, f[s["j"] + 1], f[k])
        out.append(dict(s, k=int(k), exit_ci=int(d["ci"][k]), exit_px=float(px), reason=why, ret=float(ret),
                        RN=float(ret - COST), entry_date=str(cal[s["entry_ci"]].date()),
                        exit_date=str(cal[d["ci"][k]].date())))
    return out


def in_win(t, win) -> bool:
    return win[0] <= t["entry_date"] <= win[1]


# ── 판정 재료 ───────────────────────────────────────────────────────────

def stats(ts: list) -> dict:
    if not ts:
        return {"n": 0, "mean": float("nan"), "lo90": float("nan"), "hi90": float("nan")}
    est, lo, hi = J.cluster_bootstrap([t["RN"] for t in ts], [J.iso_week_key(t["ticker"], t["entry_date"]) for t in ts],
                                      order="sorted")
    hold = [t["exit_ci"] - t["entry_ci"] for t in ts]
    return {"n": len(ts), "mean": est, "lo90": lo, "hi90": hi, "hold_median": float(np.median(hold)),
            "win_rate": float(np.mean([t["RN"] > 0 for t in ts]))}


def week_of(t) -> str:
    y, w, _ = date.fromisoformat(t["entry_date"]).isocalendar()
    return f"{y}-W{w:02d}"


def diff_bootstrap(A: list, B: list, *, n_boot=N_BOOT_DIFF, seed=C.BOOT_SEED) -> dict:
    """블록(진입 ISO 주, 전 종목 공통) 복원 추출 — 평균(A) − 평균(B)."""
    weeks = sorted({week_of(t) for t in A} | {week_of(t) for t in B})
    ix = {w: i for i, w in enumerate(weeks)}
    K = len(weeks)

    def sums(ts):
        s = np.zeros(K)
        c = np.zeros(K)
        for t in ts:
            s[ix[week_of(t)]] += t["RN"]
            c[ix[week_of(t)]] += 1
        return s, c
    sa, ca = sums(A)
    sb, cb = sums(B)
    est = sa.sum() / ca.sum() - sb.sum() / cb.sum()
    rng = np.random.default_rng(seed)
    cnt = rng.multinomial(K, np.full(K, 1.0 / K), size=n_boot).astype(float)
    dot = lambda v: np.einsum("ij,j->i", cnt, v)          # noqa: E731 — judge.cluster_bootstrap 와 같은 꼴
    with np.errstate(invalid="ignore", divide="ignore"):
        st = dot(sa) / dot(ca) - dot(sb) / dot(cb)
    st = st[np.isfinite(st)]
    return {"diff": float(est), "weeks": K, "lo90": float(np.quantile(st, 0.05)),
            "lo_bonf": float(np.quantile(st, BONF_Q)), "hi90": float(np.quantile(st, 0.95)), "n_boot_ok": int(len(st))}


# ── 계좌 ────────────────────────────────────────────────────────────────

def run_book(V: dict, sigs: list, cb, win, *, seeds, mu_mode="shadow"):
    from replay.audit.sizing import OpSizer
    L, tr, ch, bl, mu = cb
    op = OpSizer(EA._import_operating_class(), "etf_trend", {"market_unit_mode": mu_mode}, atr_keys=("atr",))
    data, store, fadj, cal = V["data"], V["store"], V["fadj"], V["cal"]
    sbg = defaultdict(list)
    for t in sigs:
        if not (t["fu"] and mu_ok(t["m"], mu)):
            continue
        raw = store.bars[t["ticker"]]["raw"][t["j"] + 1]
        sbg[t["entry_ci"]].append(EA.ETFSig(t["ticker"], t["j"] + 1, t["entry_ci"], t["E"], t["E"] * raw, t["N"],
                                            t["line"], t["m"], t["tv20"], t["sig_ci"]))

    def size_fn(s, B, used):
        P = int(round(s.E_raw))
        q = op.qty(P, s.N * (s.E_raw / s.E), budget=int(B), used=int(used), m=s.m)
        if q > 0:
            return q, "ok"
        return 0, ("funds" if int(B) - int(used) < P else "design")

    def open_pos(s, q):
        return EtfPosV(s, data[s.ticker], q, trail=tr, chan=ch, bl=bl, fadj=fadj[s.ticker])
    cs = COST / 2
    runs = [EA.etf_book(sbg, open_pos, size_fn, cal, win[0], win[1], start_equity=float(C.BUDGET_C7),
                        cost_side=cs, max_pos=EB.SLOTS, corr=V["corr"], seed=sd) for sd in seeds]
    sm = BK.book_summary(runs, float(C.BUDGET_C7))
    r0 = runs[0]
    eq = r0["equity"]
    paid = sum(ps.qty * ps.s.E_raw * cs + (ps.k * ps.exit_px * cs if ps.exit_reason != "OPEN" else 0.0)
               for ps in r0["trades"])
    yrs = len(eq) / 252.0
    return {"cagr_median": sm["cagr_median"], "mdd_median": sm["mdd_median"], "trades_median": sm["trades_median"],
            "fills_per_year_median": sm["fills_per_year_median"],
            "unaffordable_ratio_median": sm["unaffordable_ratio_median"], "recon_max_abs": sm["recon_max_abs"],
            "cost_per_year_pct_of_avg_equity": float(paid / np.mean(eq) / yrs * 100),
            "exit_reasons_seed0": dict(Counter(ps.exit_reason for ps in r0["trades"])),
            "hold_median_days": float(np.median([ps.exit_gd - ps.s.gd for ps in r0["trades"] if ps.exit_gd is not None]
                                                or [float("nan")])),
            "per_seed_identical": len({round(float(r["equity"][-1]), 6) for r in runs}) == 1,
            "counts_seed0": r0["counts"]}


def baseline(k: dict, mu: np.ndarray, cal, win, kind: str) -> dict:
    """B1 보유 · B2 × m · B3 m=1 일 때만. 069500 분배 수정가(재투자 근사) · 정수 주 · 시가 집행 · 한쪽 0.19%."""
    cs = COST / 2
    ci = k["ci"]
    g0 = int(cal.searchsorted(pd.Timestamp(win[0])))
    g1 = int(cal.searchsorted(pd.Timestamp(win[1]), side="right")) - 1
    pos = {int(c): i for i, c in enumerate(ci)}
    cash, sh, eqs, ntr, paid, prev_tgt = float(C.BUDGET_C7), 0, [], 0, 0.0, None
    for gd in range(g0, g1 + 1):
        i = pos.get(gd)
        if i is None:
            continue
        m = mu[gd - 1] if gd >= 1 else np.nan
        m = 1.0 if m != m else float(m)
        tgt = {"B1": 1.0, "B2": m, "B3": 1.0 if m >= 1.0 else 0.0}[kind]
        o = k["o"][i]
        if prev_tgt is None or tgt != prev_tgt:
            eq_o = cash + sh * o
            want = int((eq_o * tgt) // (o * (1 + cs))) if tgt > 0 else 0
            dq = want - sh
            if dq != 0:
                amt = abs(dq) * o
                paid += amt * cs
                cash -= dq * o + amt * cs
                sh = want
                ntr += 1
            prev_tgt = tgt
        eqs.append(cash + sh * k["c"][i])
    eq = np.array(eqs)
    yrs = len(eq) / 252.0
    return {"cagr": BK.cagr(eq, float(C.BUDGET_C7)), "mdd": BK.mdd(eq, float(C.BUDGET_C7)),
            "trades_per_year": ntr / yrs, "cost_per_year_pct_of_avg_equity": float(paid / np.mean(eq) / yrs * 100),
            "days": len(eq)}


# ── 실행 ────────────────────────────────────────────────────────────────

def load():
    from replay.audit import gate_c391b as GT
    from replay.audit import market_unit as MU
    from replay.audit import panel as PN
    c391 = GT.load_c391()
    PN.check_archive(C.ETF_ARCHIVE, C.ETF_PARQUET_SHA)
    cls, meta = GT.classify(c391)
    full = PN.load_archive(C.ETF_ARCHIVE)
    cal = pd.DatetimeIndex(sorted(full.bas_dd.unique()))
    need = {t for t, v in cls.items() if v} | {MU.SOURCE_TICKER}
    st = PN.build_store(full, nontrade="drop", junction_rescale=False, cal=cal, tickers=need)
    raw_full = full.copy()
    for x in ("open", "high", "low", "close"):
        raw_full[x + "_adj"] = raw_full[x]
    st_raw = PN.build_store(raw_full, nontrade="drop", junction_rescale=False, cal=cal, tickers=need)
    data = {t: EB.ticker_arrays(b) for t, b in st_raw.bars.items()}
    dadj = {t: EB.ticker_arrays(b) for t, b in st.bars.items()}
    k200 = data[MU.SOURCE_TICKER]
    mu = np.full(len(cal), np.nan)
    mu[k200["ci"]] = MU.m_at_bars(k200["c"])
    dcls = {t: d for t, d in data.items() if cls.get(t)}
    fadj = {t: st.bars[t]["c"] / st_raw.bars[t]["c"] for t in dcls}
    tick_list = sorted(data)
    col = {t: i for i, t in enumerate(tick_list)}
    ret = np.full((len(cal), len(tick_list)), np.nan)
    for t, d in data.items():
        cc = np.full(len(cal), np.nan)
        cc[d["ci"]] = d["c"]
        ret[1:, col[t]] = cc[1:] / cc[:-1] - 1
    return {"cls": cls, "meta": meta, "cal": cal, "data": dcls, "all_data": data, "mu": mu, "fadj": fadj,
            "store": st_raw, "corr": EB.Corr(ret, col), "k200_adj": dadj[MU.SOURCE_TICKER]}


def main():  # noqa: C901
    t0 = time.time()
    out_dir = os.path.join(C.REPO, "_workspace/analysis/strategy_opt_20261005/etf_trend")
    out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(out_dir, "result.json")
    V = load()
    cal, data, mu, fadj, corr = V["cal"], V["data"], V["mu"], V["fadj"], V["corr"]
    res = {"prereg_sha256": open(os.path.join(out_dir, "prereg.sha256")).read().split()[0]}
    print(f"[opt] loaded {time.time()-t0:.0f}s", flush=True)

    # ── 관문: 현행판 = 전수 점검 EB.gen_trades(원본가판) ──
    listed = {t: m["listed_at_end"] for t, m in V["meta"].items()}
    ref = EB.gen_trades(data, V["cls"], mu, cal, listed, len(cal) - 1)
    ref_ded = EB.dedup([t for t in ref if t["m"] is not None and EB.full_u(t) and t["m"] > 0], corr)
    sigs = {L: gen_signals(data, V["cls"], mu, L) for L in L_GRID}
    cur_all = attach_exit(sigs[20], data, fadj, cal, 1.8, 10, True)
    cur_ded = EB.dedup([t for t in cur_all if t["fu"] and mu_ok(t["m"], "gt0")], corr)
    a = [(t["ticker"], t["entry_ci"], t["exit_ci"], round(t["exit_px"], 9), t["reason"]) for t in ref_ded]
    b = [(t["ticker"], t["entry_ci"], t["exit_ci"], round(t["exit_px"], 9),
          t["reason"] if t["reason"] != "end" else None) for t in cur_ded]
    a = [x if x[4] not in ("open_end", "delist") else x[:4] + (None,) for x in a]
    gate = {"ref_n": len(a), "opt_n": len(b), "identical": a == b}
    res["gate_current_equals_audit"] = gate
    print("[opt] gate", gate, flush=True)
    if not gate["identical"]:
        raise SystemExit("관문 실패 — 현행판이 전수 점검 거래 목록과 다르다")

    # ── 격자 ──
    exits = {}
    for L in L_GRID:
        for tr, ch, bl in itertools.product(TR_GRID, CH_GRID, BL_GRID):
            exits[(L, tr, ch, bl)] = attach_exit(sigs[L], data, fadj, cal, tr, ch, bl)
    print(f"[opt] exits {time.time()-t0:.0f}s", flush=True)
    ded = {}
    for cb in grid():
        L, tr, ch, bl, m = cb
        ded[cb] = EB.dedup([t for t in exits[(L, tr, ch, bl)] if t["fu"] and mu_ok(t["m"], m)], corr)
    print(f"[opt] dedup {time.time()-t0:.0f}s", flush=True)

    yT = years(T_WIN)
    cur_T = [t for t in ded[CURRENT] if in_win(t, T_WIN)]
    cur_sub = [np.mean([t["RN"] for t in cur_T if in_win(t, w)] or [np.nan]) for w in T_SUB]
    rows = []
    for cb in grid():
        ts = [t for t in ded[cb] if in_win(t, T_WIN)]
        s = stats(ts)
        sub = [np.mean([t["RN"] for t in ts if in_win(t, w)] or [np.nan]) for w in T_SUB]
        dpos = sum(1 for x, y in zip(sub, cur_sub) if x == x and y == y and x - y > 0)
        rows.append({"combo": combo_name(cb), "cb": list(cb), "T": s, "per_year": s["n"] / yT,
                     "sub_mean": sub, "sub_diff_pos": dpos,
                     "eligible": bool(s["n"] / yT >= MIN_TRADES_PER_YEAR),
                     "robust": bool(dpos >= 2) if cb != CURRENT else None})
    res["grid_T"] = rows
    cur_row = next(r for r in rows if tuple(r["cb"]) == CURRENT)
    cand = [r for r in rows if tuple(r["cb"]) != CURRENT and r["eligible"] and r["robust"]]
    cand.sort(key=lambda r: (-r["T"]["lo90"], r["T"]["n"]))
    pick = cand[0] if cand and cand[0]["T"]["lo90"] > cur_row["T"]["lo90"] else None
    chosen = tuple(pick["cb"]) if pick else CURRENT
    res["selection"] = {"n_grid": len(rows), "n_eligible": sum(r["eligible"] for r in rows),
                        "n_eligible_robust": len(cand), "chosen": combo_name(chosen),
                        "chosen_is_current": chosen == CURRENT, "current_T": cur_row}
    print("[opt] chosen", combo_name(chosen), pick["T"] if pick else None, flush=True)

    # ── 검증 V · 보류 H ──
    out = {}
    for name, cb in (("current", CURRENT), ("chosen", chosen)):
        L, tr, ch, bl, m = cb
        tsV = [t for t in ded[cb] if in_win(t, V_WIN)]
        tsH = [t for t in ded[cb] if in_win(t, H_WIN)]
        adv = []
        for t in tsV:
            d = data[t["ticker"]]
            k, px, _ = sim_v(d, t["j"], t["line"], tr, ch, bl, mode="adverse")
            f = fadj[t["ticker"]]
            adv.append(EA.adj_return(t["E"], px, f[t["j"] + 1], f[k]) - COST)
        out[name] = {"combo": combo_name(cb), "T": stats([t for t in ded[cb] if in_win(t, T_WIN)]),
                     "V": stats(tsV), "H": stats(tsH), "V_adverse_mean": float(np.mean(adv)) if adv else float("nan"),
                     "V_reasons": dict(Counter(t["reason"] for t in tsV)),
                     "V_per_year": len(tsV) / years(V_WIN)}
    curV = [t for t in ded[CURRENT] if in_win(t, V_WIN)]
    chV = [t for t in ded[chosen] if in_win(t, V_WIN)]
    curH = [t for t in ded[CURRENT] if in_win(t, H_WIN)]
    chH = [t for t in ded[chosen] if in_win(t, H_WIN)]
    out["D1_V_diff"] = diff_bootstrap(chV, curV) if chosen != CURRENT else None
    out["H_diff"] = (float(np.mean([t["RN"] for t in chH]) - np.mean([t["RN"] for t in curH]))
                     if chosen != CURRENT and chH and curH else None)

    # 계좌(T · V · H, C7) — 현행 · 고른 판 · 고른 판 enforce
    books = {}
    for name, cb in (("current", CURRENT), ("chosen", chosen)):
        sl = sigs[cb[0]]
        for wn, win in (("T", T_WIN), ("V", V_WIN), ("H", H_WIN)):
            books[f"{name}|{wn}"] = run_book(V, sl, cb, win, seeds=C.BOOK_SEEDS if wn == "V" else (0,))
            print(f"[opt] book {name}|{wn}", {k: books[f'{name}|{wn}'][k] for k in ('cagr_median', 'mdd_median',
                  'fills_per_year_median')}, f"{time.time()-t0:.0f}s", flush=True)
        books[f"{name}|V|enforce"] = run_book(V, sl, cb, V_WIN, seeds=(0,), mu_mode="enforce")
    out["books"] = books
    # 판정
    ch = out["chosen"]
    bV = books["chosen|V"]
    d1 = out["D1_V_diff"]
    J_ = {"D1": bool(d1 and d1["diff"] > 0 and d1["lo90"] > 0), "D1_bonferroni": bool(d1 and d1["lo_bonf"] > 0),
          "D2": bool(ch["V"]["mean"] > 0 and ch["V"]["lo90"] > C.P1_LO),
          "D3": bool(bV["cagr_median"] > 0 and bV["mdd_median"] >= C.P3_MDD),
          "D4": bool(bV["fills_per_year_median"] >= C.P4_FILLS_PER_YEAR and not (bV["unaffordable_ratio_median"] >= C.P4_UNAFF)),
          "D5_same_sign": bool(np.sign(ch["V_adverse_mean"]) == np.sign(ch["V"]["mean"])),
          "H_n": ch["H"]["n"],
          "H_sign_same": bool(np.sign(ch["H"]["mean"]) == np.sign(ch["V"]["mean"])),
          "H_diff_sign_same": (bool(np.sign(out["H_diff"]) == np.sign(d1["diff"])) if d1 and out["H_diff"] is not None
                               else None)}
    cu = out["current"]
    bc = books["current|V"]
    J_["current_D2"] = bool(cu["V"]["mean"] > 0 and cu["V"]["lo90"] > C.P1_LO)
    J_["current_D3"] = bool(bc["cagr_median"] > 0 and bc["mdd_median"] >= C.P3_MDD)
    J_["current_D4"] = bool(bc["fills_per_year_median"] >= C.P4_FILLS_PER_YEAR)
    out["judge"] = J_
    res["validation"] = out

    # ── 기준선 ──
    k = V["k200_adj"]
    res["baselines"] = {f"{kind}|{wn}": baseline(k, mu, cal, win, kind)
                        for kind in ("B1", "B2", "B3") for wn, win in (("T", T_WIN), ("V", V_WIN), ("H", H_WIN))}
    res["elapsed_s"] = time.time() - t0
    with open(out_path, "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("[opt] done", out_path, f"{res['elapsed_s']:.0f}s", flush=True)


if __name__ == "__main__":
    main()
