#!/usr/bin/env python3
"""바탕 층(지수 보유 코어) 검증 — 사전 등록 ``_workspace/analysis/base_layer_20261005/prereg.md``.

연구 전용. 운영 코드(``src/``)는 판정 함수 두 개를 읽어서 부르기만 한다
(``market_unit.classify`` = ``replay.audit.market_unit`` 경유 · ``market_regime_label.session_labels``).

- 순수 함수: 낙폭 · 덧씌움 상태 · 목표 비중 경로 · 계좌 집행 · 짝 블록 부트스트랩 · −10% 사건 진단
- 실행부 ``main``: 격자 133 → 학습 T 선택 → 검증 V 판정 → 보류 H 부호 → −10% 진단 → result.json

실행: python tools/replay/base_layer.py [--out PATH]
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay.audit import config as C  # noqa: E402

COST = C.COST_RT_JUDGE
T_WIN = ("2020-10-05", "2023-09-29")
T_SUB = (("2020-10-05", "2021-09-30"), ("2021-10-01", "2022-09-30"), ("2022-10-01", "2023-09-29"))
V_WIN = ("2023-10-04", "2025-10-02")
H_WIN = ("2025-10-10", "2026-09-23")
BLOCK = 40
N_BOOT_T = 2000
N_BOOT_V = 20000
N_COMBOS = 133
BONF_Q = 0.10 / N_COMBOS

K200, KQ150, SHORT, USD, KTB10 = "069500", "229200", "153130", "261240", "148070"
ASSETS = (K200, KQ150, SHORT, USD, KTB10)
AI = {a: i for i, a in enumerate(ASSETS)}

# 비노출분 / 방어 자산 — {자산: 몫}
PARK = {"cash": {}, "short": {SHORT: 1.0}, "usd": {USD: 1.0}, "ktb": {KTB10: 1.0},
        "usdktb": {USD: 0.5, KTB10: 0.5}}


# ── 격자 ────────────────────────────────────────────────────────────────

def grid() -> list:
    g = [{"fam": "B0"}]
    for park, R, band in itertools.product(("cash", "short"), ("D", "W", "M"), (0.0, 0.5)):
        g.append({"fam": "B1", "park": park, "R": R, "band": band})
    for dfn, R, band in itertools.product(("usd", "ktb", "usdktb"), ("D", "W", "M"), (0.0, 0.5)):
        g.append({"fam": "B2", "def": dfn, "R": R, "band": band})
    for base, X, a, Y, park in itertools.product(("hold", "m"), (0.07, 0.10, 0.12, 0.15), (0.0, 0.5),
                                                 ("Y1", "Y2", "Y3"), ("short", "usdktb")):
        g.append({"fam": "B3", "base": base, "X": X, "a": a, "Y": Y, "park": park})
    for mix, kind in itertools.product((0.7, 0.5), ("hold", "m", "m_ov")):
        g.append({"fam": "B4", "mix": mix, "kind": kind})
    return g


def name(cb: dict) -> str:
    f = cb["fam"]
    if f == "B0":
        return "B0 069500 보유"
    if f == "B1":
        return f"B1 m비례 · 비노출 {cb['park']} · R{cb['R']} · band{cb['band']}"
    if f == "B2":
        return f"B2 m비례 · m=0 방어 {cb['def']} · R{cb['R']} · band{cb['band']}"
    if f == "B3":
        return (f"B3 {cb['base']} · X{int(round(cb['X'] * 100))} · a{cb['a']} · {cb['Y']} · 비노출 {cb['park']}")
    return f"B4 혼합 {int(cb['mix'] * 100)}:{int(round((1 - cb['mix']) * 100))} · {cb['kind']}"


# ── 신호 ────────────────────────────────────────────────────────────────

def drawdown60(c: np.ndarray) -> np.ndarray:
    """DD(t) = c(t) / max(c[t-59..t]) − 1. 60봉 미만 = NaN."""
    s = pd.Series(np.asarray(c, dtype=float))
    return (s / s.rolling(60, min_periods=60).max() - 1).to_numpy()


def prior_max20(c: np.ndarray) -> np.ndarray:
    """직전 20봉(자기 제외) 최고 종가. 20봉 미만 = NaN."""
    s = pd.Series(np.asarray(c, dtype=float))
    return s.shift(1).rolling(20, min_periods=20).max().to_numpy()


def overlay_state(dd: np.ndarray, m: np.ndarray, c: np.ndarray, X: float, Y: str) -> np.ndarray:
    """종가 t 까지 걸어 온 덧씌움 발동 여부(세션 t+1 에 쓴다). m NaN = 1.0, dd NaN = 발동 판단 없음."""
    pm20 = prior_max20(c)
    out = np.zeros(len(dd), dtype=bool)
    active, dipped = False, False
    for t in range(len(dd)):
        d = dd[t]
        mt = 1.0 if not np.isfinite(m[t]) else float(m[t])
        if not active:
            if np.isfinite(d) and d <= -X:
                active, dipped = True, mt < 1.0
        else:
            dipped = dipped or mt < 1.0
            if np.isfinite(d) and d > -X:
                if Y == "Y1":
                    rel = d > -X / 2
                elif Y == "Y2":
                    rel = (mt >= 1.0) if dipped else (d > -X / 2)
                elif Y == "Y3":
                    rel = np.isfinite(pm20[t]) and c[t] > pm20[t]
                else:
                    raise ValueError(Y)
                if rel:
                    active, dipped = False, False
        out[t] = active
    return out


def sample_mask(cal: pd.DatetimeIndex, R: str) -> np.ndarray:
    """세션 날짜가 신호를 읽는 날인가 — D 매일 · W 그 주 첫 거래일 · M 그 달 첫 거래일."""
    if R == "D":
        return np.ones(len(cal), dtype=bool)
    if R == "W":
        k = np.array([d.isocalendar()[0] * 100 + d.isocalendar()[1] for d in cal])
    elif R == "M":
        k = np.array([d.year * 100 + d.month for d in cal])
    else:
        raise ValueError(R)
    return np.r_[True, k[1:] != k[:-1]]


def _vec(eq_w: float, eq_split: dict, park_w: dict) -> np.ndarray:
    v = np.zeros(len(ASSETS))
    for a, s in eq_split.items():
        v[AI[a]] += eq_w * s
    for a, s in park_w.items():
        v[AI[a]] += (1.0 - eq_w) * s
    return v


def weights_path(cb: dict, cal: pd.DatetimeIndex, m: np.ndarray, dd: np.ndarray, c: np.ndarray) -> np.ndarray:
    """세션 D 의 목표 비중(자산 5열). 세션 D 는 종가 D−1 까지만 본다. 세션 0 = 신호 없음(보유 1 · m=1)."""
    n = len(cal)
    msess = np.r_[np.nan, m[:-1]]
    msess = np.where(np.isfinite(msess), msess, 1.0)
    f = cb["fam"]
    W = np.zeros((n, len(ASSETS)))
    if f == "B0":
        W[:, AI[K200]] = 1.0
        return W
    if f in ("B1", "B2"):
        samp = sample_mask(cal, cb["R"])
        held = None
        for D in range(n):
            if held is None or samp[D]:
                new = msess[D]
                if held is None or abs(new - held) >= cb["band"] - 1e-12:
                    held = new
            if f == "B1":
                park = PARK[cb["park"]]
            else:
                park = PARK[cb["def"]] if held <= 0.0 else PARK["short"]
            W[D] = _vec(held, {K200: 1.0}, park)
        return W
    if f == "B3":
        act = np.r_[False, overlay_state(dd, m, c, cb["X"], cb["Y"])[:-1]]
        for D in range(n):
            wb = 1.0 if cb["base"] == "hold" else msess[D]
            w = cb["a"] * wb if act[D] else wb
            W[D] = _vec(w, {K200: 1.0}, PARK[cb["park"]])
        return W
    if f == "B4":
        split = {K200: cb["mix"], KQ150: 1.0 - cb["mix"]}
        act = (np.r_[False, overlay_state(dd, m, c, 0.10, "Y1")[:-1]] if cb["kind"] == "m_ov"
               else np.zeros(n, dtype=bool))
        for D in range(n):
            w = 1.0 if cb["kind"] == "hold" else msess[D]
            if act[D]:
                w = 0.0
            W[D] = _vec(w, split, PARK["short"])
        return W
    raise ValueError(f)


# ── 계좌 ────────────────────────────────────────────────────────────────

def run_account(W: np.ndarray, O: np.ndarray, Cl: np.ndarray, g0: int, g1: int,
                budget: float = float(C.BUDGET_C7), cost_rt: float = COST) -> dict:
    """세션 g0..g1 계좌. 첫날 목표대로 사고, 그 뒤는 비중이 바뀐 자산만 시가에 정수 주로 맞춘다."""
    cs = cost_rt / 2
    na = W.shape[1]
    cash, sh = float(budget), np.zeros(na, dtype=np.int64)
    eqs, stock_share, cash_share = [], [], []
    orders, paid, traded = 0, 0.0, 0.0
    prev = None
    for g in range(g0, g1 + 1):
        w = W[g]
        o = O[g]
        chg = np.ones(na, dtype=bool) if prev is None else ~np.isclose(w, prev, atol=1e-12)
        if chg.any():
            eq_o = cash + float((sh * np.nan_to_num(o)).sum())
            want = sh.copy()
            for i in np.where(chg)[0]:
                want[i] = int((eq_o * w[i]) // (o[i] * (1 + cs))) if w[i] > 0 else 0
            for i in np.where(want < sh)[0]:                       # 매도 먼저
                q = int(sh[i] - want[i])
                amt = q * o[i]
                cash += amt - amt * cs
                paid += amt * cs
                traded += amt
                sh[i] = want[i]
                orders += 1
            for i in np.where(want > sh)[0]:                       # 매수 — 현금 안에서
                q = int(want[i] - sh[i])
                q = min(q, int(cash // (o[i] * (1 + cs))))
                if q <= 0:
                    continue
                amt = q * o[i]
                cash -= amt + amt * cs
                paid += amt * cs
                traded += amt
                sh[i] += q
                orders += 1
            prev = w.copy()
        val = sh * Cl[g]
        eq = cash + float(val.sum())
        eqs.append(eq)
        stock_share.append(float(val[AI[K200]] + val[AI[KQ150]]) / eq)
        cash_share.append(cash / eq)
    eq = np.array(eqs)
    yrs = len(eq) / 252.0
    cg = float((eq[-1] / budget) ** (252.0 / len(eq)) - 1)
    e = np.r_[budget, eq]
    md = float((e / np.maximum.accumulate(e) - 1).min())
    return {"equity": eq, "cagr": cg, "mdd": md, "mar": cg / abs(md) if md < 0 else float("nan"),
            "orders_per_year": orders / yrs, "cost_per_year_pct": float(paid / eq.mean() / yrs * 100),
            "turnover_per_year": float(traded / eq.mean() / yrs), "avg_stock_share": float(np.mean(stock_share)),
            "avg_cash_share": float(np.mean(cash_share)), "days": len(eq)}


def daily_returns(eq: np.ndarray, budget: float = float(C.BUDGET_C7)) -> np.ndarray:
    e = np.r_[budget, eq]
    return e[1:] / e[:-1] - 1


def boot_index(n: int, reps: int, block: int = BLOCK, seed: int = C.BOOT_SEED) -> np.ndarray:
    """원형 블록 재표집 색인(reps × n)."""
    rng = np.random.default_rng(seed)
    nb = -(-n // block)
    starts = rng.integers(0, n, size=(reps, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return idx.reshape(reps, -1)[:, :n]


def mar_paths(r: np.ndarray, idx: np.ndarray) -> np.ndarray:
    rr = r[idx]
    path = np.cumprod(1 + rr, axis=1)
    n = r.shape[0]
    cg = path[:, -1] ** (252.0 / n) - 1
    e = np.concatenate([np.ones((path.shape[0], 1)), path], axis=1)
    md = (e / np.maximum.accumulate(e, axis=1) - 1).min(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(md < 0, cg / np.abs(md), np.nan)


def mar_diff_boot(rA: np.ndarray, rB: np.ndarray, reps: int, block: int = BLOCK, seed: int = C.BOOT_SEED) -> np.ndarray:
    """짝지은 원형 블록 부트스트랩 — 같은 색인으로 두 판의 MAR 차이(A − B)."""
    idx = boot_index(len(rA), reps, block, seed)
    return mar_paths(rA, idx) - mar_paths(rB, idx)


# ── −10% 진단 ───────────────────────────────────────────────────────────

def dd_events(dd: np.ndarray, X: float = 0.10) -> list:
    """무장 상태에서 DD ≤ −X 인 첫 종가 색인. 사건 뒤 DD > −X/2 에서 재무장."""
    ev, armed = [], True
    for t, d in enumerate(dd):
        if not np.isfinite(d):
            continue
        if armed and d <= -X:
            ev.append(t)
            armed = False
        elif not armed and d > -X / 2:
            armed = True
    return ev


def first_after(mask: np.ndarray, start: int, limit: int = 120) -> "int | None":
    hits = np.where(mask[start:start + limit + 1])[0]
    return int(start + hits[0]) if len(hits) else None


def event_table(cal, c_adj, o_adj, dd, m_close, dir_close, X: float = 0.10) -> list:
    """사건별 표. ``m_close``·``dir_close`` = 종가 t 까지로 판정한 값(= 세션 t+1 의 값)."""
    n = len(c_adj)
    rows = []
    for t in dd_events(dd, X):
        w0 = t - 59
        pk = w0 + int(np.argmax(c_adj[w0:t + 1]))
        r = {"signal": str(cal[t].date()), "peak": str(cal[pk].date()), "peak_to_signal": t - pk,
             "dd_at_signal": float(dd[t])}
        for h in (20, 60):
            r[f"fwd{h}"] = float(c_adj[t + h] / o_adj[t + 1] - 1) if t + h < n else None
            r[f"fwd{h}_from_close"] = float(c_adj[t + h] / c_adj[t] - 1) if t + h < n else None
        seg = c_adj[t + 1:min(n, t + 61)]
        r["further_drop60"] = float(seg.min() / c_adj[t] - 1) if len(seg) else None
        r["rebound60"] = float(seg.max() / c_adj[t] - 1) if len(seg) else None
        r["complete60"] = t + 60 < n
        seg20 = c_adj[t + 1:min(n, t + 21)]
        if t + 20 < n:
            r["false_alarm"] = bool(c_adj[t + 20] > c_adj[t] and seg20.min() / c_adj[t] - 1 > -0.05)
            r["false_alarm_loose"] = bool(c_adj[t + 20] > c_adj[t])
        else:
            r["false_alarm"] = r["false_alarm_loose"] = None
        mm = np.where(np.isfinite(m_close), m_close, 1.0)
        dir_ = np.array([d if d is not None else "" for d in dir_close])
        for key, mask in (("m_lt1", mm < 1.0), ("m_eq0", mm <= 0.0),
                          ("label_not_up", (dir_ != "up") & (dir_ != "")), ("label_down", dir_ == "down")):
            k = first_after(mask, pk)
            r[key] = str(cal[k].date()) if k is not None else None
            r[key + "_lead"] = (k - t) if k is not None else None
        rows.append(r)
    return rows


# ── 실행 ────────────────────────────────────────────────────────────────

def load() -> dict:
    from replay.audit import market_unit as MU
    from replay.audit import panel as PN
    PN.check_archive(C.ETF_ARCHIVE, C.ETF_PARQUET_SHA)
    full = PN.load_archive(C.ETF_ARCHIVE)
    sub = full[full.ticker.isin(ASSETS)]
    cal = pd.DatetimeIndex(sorted(full.bas_dd.unique()))
    O = np.full((len(cal), len(ASSETS)), np.nan)
    Cl = O.copy()
    raw = {}
    for a in ASSETS:
        s = sub[sub.ticker == a].set_index("bas_dd").sort_index().reindex(cal)
        if s.close_adj.isna().any():
            raise SystemExit(f"[base_layer] {a} 결측 봉 {int(s.close_adj.isna().sum())}")
        O[:, AI[a]] = s.open_adj.to_numpy(float)
        Cl[:, AI[a]] = s.close_adj.to_numpy(float)
        raw[a] = s.close.to_numpy(float)
    m = MU.m_at_bars(raw[K200])
    return {"cal": cal, "O": O, "Cl": Cl, "m": m, "c": Cl[:, AI[K200]], "dd": drawdown60(Cl[:, AI[K200]])}


def win_idx(cal, win) -> tuple:
    return int(cal.searchsorted(pd.Timestamp(win[0]))), int(cal.searchsorted(pd.Timestamp(win[1]), side="right")) - 1


def _summ(r: dict) -> dict:
    return {k: v for k, v in r.items() if k != "equity"}


def main():  # noqa: C901
    t0 = time.time()
    out_dir = os.path.join(C.REPO, "_workspace/analysis/base_layer_20261005")
    out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(out_dir, "result.json")
    V = load()
    cal, O, Cl, m, c, dd = V["cal"], V["O"], V["Cl"], V["m"], V["c"], V["dd"]
    G = grid()
    assert len(G) == N_COMBOS, len(G)
    paths = [weights_path(cb, cal, m, dd, c) for cb in G]
    wins = {"T": win_idx(cal, T_WIN), "V": win_idx(cal, V_WIN), "H": win_idx(cal, H_WIN)}
    subs = [win_idx(cal, w) for w in T_SUB]

    res = []
    for cb, W in zip(G, paths):
        row = {"combo": cb, "name": name(cb)}
        for k, (g0, g1) in wins.items():
            row[k] = run_account(W, O, Cl, g0, g1)
        row["T_sub"] = [run_account(W, O, Cl, g0, g1) for g0, g1 in subs]
        res.append(row)
    b0 = res[0]
    assert b0["combo"]["fam"] == "B0"

    # 학습 T — 강건 · 부트스트랩 하한
    nT = b0["T"]["days"]
    idxT = boot_index(nT, N_BOOT_T)
    rB0 = daily_returns(b0["T"]["equity"])
    marB0 = mar_paths(rB0, idxT)
    for row in res[1:]:
        row["robust_n"] = int(sum(s["mar"] > s0["mar"] for s, s0 in zip(row["T_sub"], b0["T_sub"])))
        row["robust"] = row["robust_n"] >= 2
        dif = mar_paths(daily_returns(row["T"]["equity"]), idxT) - marB0
        row["T_boot"] = {"mean": float(np.nanmean(dif)), "lo90": float(np.nanquantile(dif, 0.05)),
                         "hi90": float(np.nanquantile(dif, 0.95))}
    cands = [r for r in res[1:] if r["robust"]]
    robust_none = not cands
    if robust_none:
        cands = res[1:]
    chosen = max(cands, key=lambda r: (r["T_boot"]["lo90"], -r["T"]["turnover_per_year"]))

    # 검증 V — 한 번
    rA = daily_returns(chosen["V"]["equity"])
    rB = daily_returns(b0["V"]["equity"])
    difV = mar_diff_boot(rA, rB, N_BOOT_V)
    J1 = {"mar_chosen": chosen["V"]["mar"], "mar_b0": b0["V"]["mar"],
          "diff": chosen["V"]["mar"] - b0["V"]["mar"], "lo90": float(np.nanquantile(difV, 0.05)),
          "hi90": float(np.nanquantile(difV, 0.95)), "bonf_q": BONF_Q,
          "lo_bonf": float(np.nanquantile(difV, BONF_Q)), "p_le0": float(np.nanmean(difV <= 0))}
    J1["pass"] = bool(J1["diff"] > 0 and J1["lo90"] > 0)
    J1["pass_bonf"] = bool(J1["diff"] > 0 and J1["lo_bonf"] > 0)
    J2 = {"cagr_ge": chosen["V"]["cagr"] >= b0["V"]["cagr"], "mdd_shallower": chosen["V"]["mdd"] > b0["V"]["mdd"]}
    J2["pass"] = bool(J2["cagr_ge"] and J2["mdd_shallower"])
    Hs = {"mar_diff": chosen["H"]["mar"] - b0["H"]["mar"], "cagr_diff": chosen["H"]["cagr"] - b0["H"]["cagr"],
          "mdd_diff": chosen["H"]["mdd"] - b0["H"]["mdd"]}
    Hs["mar_sign_kept"] = bool(np.sign(Hs["mar_diff"]) == np.sign(J1["diff"]))

    # 보고 전용 — 같은 V 부트스트랩을 참고 기준선·묶음 최선에도(판정 아님)
    ref = next(r for r in res if r["combo"] == {"fam": "B1", "park": "cash", "R": "D", "band": 0.0})
    fam_best = {}
    for f in ("B1", "B2", "B3", "B4"):
        rows = [r for r in res if r["combo"]["fam"] == f]
        rr = [r for r in rows if r["robust"]] or rows
        fam_best[f] = max(rr, key=lambda r: (r["T_boot"]["lo90"], -r["T"]["turnover_per_year"]))
    report_v = {}
    for key, r in [("ref_B1_cash_D", ref)] + [(f"best_{f}", r) for f, r in fam_best.items()]:
        d = mar_diff_boot(daily_returns(r["V"]["equity"]), rB, N_BOOT_T)
        report_v[key] = {"name": r["name"], "diff": r["V"]["mar"] - b0["V"]["mar"],
                         "lo90": float(np.nanquantile(d, 0.05)), "hi90": float(np.nanquantile(d, 0.95))}
    # B3 X=10 묶음 V 요약(−10% 매매 가치 근거, 보고 전용)
    x10 = [{"name": r["name"], "T": _summ(r["T"]), "V": _summ(r["V"]), "H": _summ(r["H"]),
            "robust_n": r["robust_n"], "T_lo90": r["T_boot"]["lo90"]}
           for r in res if r["combo"]["fam"] == "B3" and abs(r["combo"]["X"] - 0.10) < 1e-9]

    # −10% 진단
    m_close = m.copy()
    from src.engine import market_regime_label as RL
    sl = RL.session_labels(list(cal.date), list(c))
    lab_sess = {d: p for d, p in sl}
    dir_close = [None] * len(cal)
    for i in range(len(cal) - 1):                     # 종가 i 까지의 상태 = 세션 i+1 라벨
        p = lab_sess.get(cal[i + 1].date())
        dir_close[i] = p.direction if p is not None else None
    last = RL.label_after_closes(list(c))[-1]
    dir_close[-1] = last.direction if last is not None else None
    ev = event_table(cal, c, O[:, AI[K200]], dd, m_close, dir_close, 0.10)
    counts = {f"X{int(x * 100)}": len(dd_events(dd, x)) for x in (0.07, 0.10, 0.12, 0.15)}
    base = {}
    for h in (20, 60):
        fr = np.array([c[t + h] / c[t] - 1 for t in range(59, len(c) - h)])
        base[f"fwd{h}"] = {"n": len(fr), "mean": float(fr.mean()), "median": float(np.median(fr)),
                           "pos": float((fr > 0).mean()), "p10": float(np.quantile(fr, 0.10))}
    # 신호 당일 같은 날짜의 정합 확인(사용자 근거 06-24)
    check_0624 = [e for e in ev if e["signal"].startswith("2026-06")]

    def row_out(r):
        o = {"name": r["name"], "combo": r["combo"]}
        for k in ("T", "V", "H"):
            o[k] = _summ(r[k])
        o["T_sub_mar"] = [s["mar"] for s in r["T_sub"]]
        for k in ("robust_n", "robust", "T_boot"):
            if k in r:
                o[k] = r[k]
        return o

    top = sorted(res[1:], key=lambda r: (not r["robust"], -r["T_boot"]["lo90"]))
    out = {
        "prereg_sha256": open(os.path.join(out_dir, "prereg.sha256")).read().split()[0],
        "windows": {k: [str(cal[a].date()), str(cal[b].date())] for k, (a, b) in wins.items()},
        "n_combos": len(G), "n_robust": sum(r.get("robust", False) for r in res[1:]),
        "robust_none": robust_none,
        "B0": row_out(b0), "chosen": row_out(chosen), "ref_B1_cash_D": row_out(ref),
        "family_best": {f: row_out(r) for f, r in fam_best.items()},
        "J1": J1, "J2": J2, "H": Hs, "report_v_boot": report_v,
        "top10": [row_out(r) for r in top[:10]],
        "all": [row_out(r) for r in res],
        "b3_x10": x10,
        "dd_diag": {"events": ev, "counts": counts, "base_rates": base, "jun2026": check_0624},
        "elapsed_sec": round(time.time() - t0, 1),
    }
    with open(out_path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=float)
    print(f"[base_layer] {out_path} · {out['elapsed_sec']}s · chosen = {chosen['name']} · J1 {J1['pass']}")


if __name__ == "__main__":
    main()
