#!/usr/bin/env python3
"""환헤지 항목의 「금리차 뺀 판」 — 성적표 환헤지 항목을 같은 규칙으로, 헤지 수익 계열만 바꿔 다시 돌린다.

환헤지판 일 수익 = 현지 수익 + 금리차(한국 3개월 − 그 통화 3개월) · dt (``global_alloc_data`` 128~129행,
``gold_alloc.gold_columns``). 금리차 뺀 판은 그 금리차 항만 뺀다.

- 1배 헤지 = ``{자산}_lret``(현지 통화 수익) — 보수·비용은 원 항목 그대로.
- 2배 헤지 = 원 식 ``2·lret − rf − c·dt + (cash − rf)`` 에서 금리차 항 ``(cash − rf)`` 만 뺀
  ``2·lret − rf − c·dt``(rf = 현지 조달금리 · c = 연 부대비용 — 그대로). −100% 하한·첫날 0 도 그대로.
- 환노출 자산·원화 현금·노출 경로(장세 규칙이 고른 노출)·학습해 고른 규칙은 원 항목 그대로 쓴다.

재현 관문: 같은 코드로 원 계열(금리차 포함)을 다시 돌린 곡선이 성적표 곡선과 같아야 금리차 뺀 판을 낸다.

    python tools/replay/hedge_nocarry.py [out_dir]
"""
from __future__ import annotations

import copy
import json
import os
import sys
import time

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_TOOLS)
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import global_alloc as G  # noqa: E402
from replay import global_alloc_b as GB  # noqa: E402

MAIN_REPO = "/Users/koscom/Projects/auto_stock"
PARQUET = os.path.join(MAIN_REPO, "data/archive/global_long/global_daily_krw.parquet")
GOLD_CSV = os.path.join(MAIN_REPO, "data/archive/global_long/raw/usagold_xauusd_daily.csv")
OUT_REL = "_workspace/analysis/hedge_nocarry_20261006"
SB_JSON = "_workspace/analysis/scoreboard_20261006/scoreboard.json"
GOLD_ENTRIES = "_workspace/analysis/gold_20261006/scoreboard_entries.json"
RAUS_ENTRIES = "_workspace/analysis/ra_us_20261006/scoreboard_entries.json"
RAUS_RESULT = "_workspace/analysis/ra_us_20261006/result.json"
RAUSB_ENTRIES = "_workspace/analysis/ra_us_breadth_20261006/scoreboard_entries.json"
RAUSB_RESULT = "_workspace/analysis/ra_us_breadth_20261006/result.json"
SUFFIX = "__NC"
TAIL = " · 금리차 제외"
GROUP_TITLE = "환헤지 항목 금리차 뺀 판(참고 · 원 항목 대체판)"
REPRO_TOL = 1e-9                     # 원 계열 재현 곡선 ↔ 성적표 곡선 최대 상대 오차
ROUND_TOL = 6e-9                     # 또는 최대 절대 오차 — 금 항목 파일은 누적을 소수 8자리로 반올림해 적었다(반 자리 5e-9)


# ═════════════════════════════════ 금리차 뺀 계열 ═════════════════════════════════

def carry_of(lret: np.ndarray, hret: np.ndarray) -> np.ndarray:
    """헤지판에 들어 있는 금리차 항(일) = hret − lret."""
    return np.asarray(hret, float) - np.asarray(lret, float)


def lev2_hedged(lret, hret, cash, dt, c: float, carry: bool = True) -> np.ndarray:
    """일일 2배 헤지 모형. carry=True 면 원 식(``GB.lev_returns`` 'H' · ``gold_alloc.lev2`` 'H') 그대로,
    False 면 금리차 항 (cash − rf) 만 뺀다. rf = cash − (hret − lret) = 현지 조달금리 · dt."""
    lret, hret, cash, dt = (np.asarray(x, float) for x in (lret, hret, cash, dt))
    rf = cash - (hret - lret)
    x = 2 * lret - rf - c * dt + ((cash - rf) if carry else 0.0)
    x = np.maximum(x, -1.0)
    x[0] = 0.0
    return x


def _dt(dates: pd.DatetimeIndex) -> np.ndarray:
    return pd.Series(dates, index=dates).diff().dt.days.fillna(1).to_numpy(float) / 365.0


def gb_nocarry(m: GB.Mkt, df: pd.DataFrame, one_x: bool, lev: bool, c: float = GB.C_LEV_BASE) -> GB.Mkt:
    """GB 시장의 헤지 열을 금리차 뺀 계열로 바꾼 사본. one_x = 1배 헤지 자산(HEDGEABLE) 열 · lev = 2배 헤지 열."""
    m2 = copy.copy(m)
    ret = m.ret.copy()
    cash = df["CASH_ret"].to_numpy(float)
    dt = _dt(pd.DatetimeIndex(df.index))
    for a in G.HEDGEABLE:
        rl, h = df[f"{a}_lret"].to_numpy(float), df[f"{a}_hret"].to_numpy(float)
        if one_x:
            ret[:, GB.COLS.index(a)] = rl
        if lev:
            ret[:, GB.COLS.index("L" + a)] = lev2_hedged(rl, h, cash, dt, c, carry=False)
    ret[0, :] = 0.0
    m2.ret = ret
    return m2


# ═════════════════════════════════ 재현 관문 ═════════════════════════════════

def max_rel_err(v: np.ndarray, cum: np.ndarray) -> float:
    v, cum = np.asarray(v, float), np.asarray(cum, float)
    if len(v) != len(cum):
        return float("inf")
    return float(np.max(np.abs(v / v[0] / cum - 1.0)))


def max_abs_err(v: np.ndarray, cum: np.ndarray) -> float:
    v, cum = np.asarray(v, float), np.asarray(cum, float)
    if len(v) != len(cum):
        return float("inf")
    return float(np.max(np.abs(v / v[0] - cum)))


def repro_ok(v: np.ndarray, cum: np.ndarray) -> bool:
    """재현 관문 — 상대 오차 1e-9 미만이거나(같은 계산) 절대 오차가 소수 8자리 반올림 폭 안."""
    return bool(max_rel_err(v, cum) < REPRO_TOL or max_abs_err(v, cum) <= ROUND_TOL)


def month_cum(dates: pd.DatetimeIndex, v: np.ndarray) -> np.ndarray:
    from replay import scoreboard as SB
    return np.asarray(SB.curves(dates, v)["cum"], float)


# ═════════════════════════════════ 항목별 ═════════════════════════════════

class Item:
    def __init__(self, iid, dates, v_orig, v_nc, turnover_yr=None, cost_yr=None, after_tax_cagr=None, note=""):
        self.id, self.dates, self.v_orig, self.v_nc = iid, pd.DatetimeIndex(dates), v_orig, v_nc
        self.turnover_yr, self.cost_yr, self.after_tax_cagr, self.note = turnover_yr, cost_yr, after_tax_cagr, note


def _gb_run(m, sched, a, b):
    s = GB.simulate(m, sched, a, b)
    st = GB.simulate(m, sched, a, b, tax=True)
    yrs = (m.dates[b] - m.dates[a]).days / 365.25
    vt = st.value[a:b + 1]
    from replay import scoreboard as SB
    return (s.value[a:b + 1], s.turnover / yrs, s.cost / yrs, SB.cagr(vt[0], vt[-1], m.dates[a], m.dates[b]))


def global_items(df: pd.DataFrame) -> list[Item]:
    """B-H · OL_{SPX,NDX,NKY,HSCEI}_H — ``scoreboard.load_global`` 과 같은 경로."""
    m = GB.load(df, "U")
    a, b = GB.periods(m)["full"]
    d = m.dates[a:b + 1]
    out = []
    mh = GB.load(df, "U", hedged=True)
    mh_nc = gb_nocarry(mh, df, one_x=True, lev=False)
    o, n = _gb_run(mh, GB.schedule(mh, "B", a, b), a, b), _gb_run(mh_nc, GB.schedule(mh_nc, "B", a, b), a, b)
    out.append(Item("B-H", d, o[0], n[0], *n[1:]))
    mlh = GB.load(df, "H")
    mlh_nc = gb_nocarry(mlh, df, one_x=False, lev=True)
    for x in ("SPX", "NDX", "NKY", "HSCEI"):
        w = np.zeros(GB.N)
        w[GB.COLS.index("L" + x)] = 1.0
        o, n = _gb_run(mlh, {a: w}, a, b), _gb_run(mlh_nc, {a: w}, a, b)
        out.append(Item(f"OL_{x}_H", d, o[0], n[0], *n[1:]))
    return out


def gold_items(df: pd.DataFrame, gold_csv: str = GOLD_CSV) -> list[Item]:
    """GOLD_H · AU_LEV2_H — ``gold_run`` 과 같은 경로(엔진 ``gold_alloc``)."""
    from replay import gold_alloc as A
    from replay import gold_run as GR
    from replay import scoreboard as SB
    gc = A.gold_columns(df, A.load_gold_csv(gold_csv))
    df2 = df.join(gc)
    m = A.build_mkt(df2, GR.STATIC_RISKY)
    a, b = GB.periods(GB.load(df, "U"))["full"]
    gl, gh = df2["GOLD_lret"].to_numpy(float), df2["GOLD_hret"].to_numpy(float)
    cash, dt = df2["CASH_ret"].to_numpy(float), _dt(pd.DatetimeIndex(df2.index))
    m_nc = copy.copy(m)
    ret = m.ret.copy()
    ret[:, m.cols.index("GOLD_H")] = gl
    ret[:, m.cols.index("LGOLD_H")] = lev2_hedged(gl, gh, cash, dt, A.C_LEV, carry=False)
    ret[0, :] = 0.0
    m_nc.ret = ret
    m_nc.cache = {}
    out = []
    for iid, col in (("GOLD_H", "GOLD_H"), ("AU_LEV2_H", "LGOLD_H")):
        vals = []
        for mk in (m, m_nc):
            s = A.static_schedule(mk, A.wvec(mk, {col: 1.0}), a, b, None)
            sim, st = A.simulate(mk, s, a, b), A.simulate(mk, s, a, b, tax=True)
            yrs = (mk.dates[b] - mk.dates[a]).days / 365.25
            vals.append((sim.value[a:b + 1], sim.turnover / yrs, sim.cost / yrs,
                         SB.cagr(st.value[a], st.value[b], mk.dates[a], mk.dates[b])))
        out.append(Item(iid, m.dates[a:b + 1], vals[0][0], vals[1][0], *vals[1][1:]))
    return out


def _expo_run(m, asset, expo, win):
    from replay import ra_us as R
    from replay import regime_gate_alloc as RA
    from replay import scoreboard as SB
    ix, il = R.cols(asset)
    a, b = RA.win_ab(m, win)
    sched = R.schedule(m, expo, a, b, ix, il)
    sim, st = GB.simulate(m, sched, a, b), GB.simulate(m, sched, a, b, tax=True)
    yrs = (m.dates[b] - m.dates[a]).days / 365.25
    return (m.dates[a:b + 1], sim.value[a:b + 1], sim.turnover / yrs, sim.cost / yrs,
            SB.cagr(st.value[a], st.value[b], m.dates[a], m.dates[b]))


def raus_expos(dates) -> dict:
    """RAUS_{SPX,NDX}_H_{A,B2,B3,B4,C} 의 노출 경로 — ``ra_us.us_stage`` 와 같은 규칙. C 는 원 연구가 고른 규칙·행동."""
    from replay import ra_us as R
    from replay import regime_v2 as V
    res = json.load(open(os.path.join(_ROOT, RAUS_RESULT)))["us"]
    out = {}
    for asset in R.ASSETS:
        f = R.us_features(asset, dates)
        out[(asset, "A")] = R.expo_of(V.rule_keys(f, R.RULE_RA), R.MAP_RA)
        for bn, (rule, amap) in R.B_RULES.items():
            out[(asset, bn)] = R.expo_of(V.rule_keys(f, rule), amap)
        c = res[f"{asset}_H"]["C"]
        rule = tuple(tuple(x) for x in c["select"]["best"]["rule"])
        out[(asset, "C")] = R.expo_of(V.rule_keys(f, rule), c["map"])
    return out


def rausb_expos(dates) -> dict:
    """RAUSB_{P0,P1,P2}_{SPX,NDX}_H_{TR,RL} — ``ra_us_breadth.us_stage`` 와 같은 규칙. 문턱·재학습 행동은 원 연구 값."""
    from replay import ra_us as R
    from replay import ra_us_breadth as RB
    from replay import regime_v2 as V
    res = json.load(open(os.path.join(_ROOT, RAUSB_RESULT)))
    out = {}
    for asset in R.ASSETS:
        f = R.us_features(asset, dates)
        for px in RB.PROXIES:
            xa = RB.aligned(RB.proxy_series(px, asset), dates)
            fx = f.copy()
            fx["BX"] = xa
            thr = res["meta"]["thresholds"][f"{px}_{asset}"]["thr"]
            keys = V.rule_keys(fx, RB.rule_of(thr))
            out[(asset, px, "TR")] = R.expo_of(keys, R.MAP_RA)
            out[(asset, px, "RL")] = R.expo_of(keys, res["us"][f"{asset}_H"][f"RL_{px}"]["map"])
    return out


def us_items(df: pd.DataFrame) -> list[Item]:
    from replay import ra_us as R
    mh = GB.load(df, "H", hedged=True)
    mh_nc = gb_nocarry(mh, df, one_x=True, lev=True)
    win = R.US_WINS["FULL"]
    out = []
    plans = [(f"RAUS_{a}_H_{p}", a, e) for (a, p), e in raus_expos(mh.dates).items()]
    plans += [(f"RAUSB_{px}_{a}_H_{k}", a, e) for (a, px, k), e in rausb_expos(mh.dates).items()]
    for iid, asset, expo in plans:
        d, vo, *_ = _expo_run(mh, asset, expo, win)
        _, vn, to, co, at = _expo_run(mh_nc, asset, expo, win)
        out.append(Item(iid, d, vo, vn, to, co, at))
    return out


# ═════════════════════════════════ 관문 · 산출 ═════════════════════════════════

def _entry_curves(rel: str) -> dict:
    p = os.path.join(_ROOT, rel)
    return {e["id"]: e for e in json.load(open(p))["entries"]} if os.path.exists(p) else {}


def gate(items: list[Item]) -> dict:
    """원 계열 재현 곡선 ↔ 성적표 곡선. 외부 항목은 일별 곡선 상대 오차, REGISTRY 항목은 월말 누적 상대 오차."""
    sb = {r["id"]: r for r in json.load(open(os.path.join(_ROOT, SB_JSON)))["rows"]}
    ext = {}
    for rel in (GOLD_ENTRIES, RAUS_ENTRIES, RAUSB_ENTRIES):
        ext.update(_entry_curves(rel))
    out = {}
    for it in items:
        if it.id in ext:
            e = ext[it.id]
            cum = e["curve"]["cum"]
            same_dates = [str(x.date()) for x in it.dates] == e["curve"]["dates"]
            out[it.id] = {"kind": "daily", "max_rel_err": max_rel_err(it.v_orig, cum),
                          "max_abs_err": max_abs_err(it.v_orig, cum), "same_dates": same_dates,
                          "ok": bool(repro_ok(it.v_orig, cum) and same_dates)}
        elif it.id in sb:
            mc = month_cum(it.dates, it.v_orig)
            cum = sb[it.id]["curves"]["cum"]
            out[it.id] = {"kind": "month_end", "max_rel_err": max_rel_err(mc, cum), "max_abs_err": max_abs_err(mc, cum),
                          "ok": repro_ok(mc, cum)}
        else:
            out[it.id] = {"kind": "none", "ok": False, "why": "성적표에 원 항목 없음"}
    return out


def nc_entry(it: Item, orig: dict) -> dict:
    v = np.asarray(it.v_nc, float)
    return {"id": it.id + SUFFIX, "name": orig["name"] + TAIL,
            "desc": orig["desc"] + " — 금리차 제외판: 헤지 수익에서 한국·현지 단기금리 차를 뺀 현지 통화 수익(규칙·노출 그대로)",
            "period": [str(it.dates[0].date()), str(it.dates[-1].date())],
            "curve": {"dates": [str(x.date()) for x in it.dates], "cum": [float(x / v[0]) for x in v]},
            "status": "참고", "status_ref": f"{OUT_REL}/progress.log · tools/replay/hedge_nocarry.py",
            "group_title": GROUP_TITLE, "turnover_yr": it.turnover_yr, "cost_yr": it.cost_yr,
            "after_tax_cagr": it.after_tax_cagr, "tax_note": orig.get("tax_note", ""),
            "source": "tools/replay/hedge_nocarry.py"}


def _cagr(dates, v) -> float:
    yrs = (dates[-1] - dates[0]).days / 365.25
    return float((v[-1] / v[0]) ** (1 / yrs) - 1)


def run(out_dir: str) -> dict:
    t0 = time.time()
    df = pd.read_parquet(PARQUET)
    items = global_items(df)
    print(f"[nocarry] global {len(items)} · {time.time() - t0:.0f}s", flush=True)
    items += gold_items(df)
    print(f"[nocarry] gold · {time.time() - t0:.0f}s", flush=True)
    items += us_items(df)
    print(f"[nocarry] us · {len(items)} · {time.time() - t0:.0f}s", flush=True)
    g = gate(items)
    bad = [k for k, x in g.items() if not x["ok"]]
    sb = {r["id"]: r for r in json.load(open(os.path.join(_ROOT, SB_JSON)))["rows"]}
    summary = {it.id: {"cagr_orig": _cagr(it.dates, it.v_orig), "cagr_nc": _cagr(it.dates, it.v_nc)} for it in items}
    res = {"gate": g, "gate_fail": bad, "summary": summary, "n": len(items)}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "result.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    if bad:
        raise SystemExit(f"[nocarry] 재현 관문 실패 {bad} — 금리차 뺀 판을 내지 않는다")
    doc = {"source": "hedge_nocarry 2026-10-06 · tools/replay/hedge_nocarry.py(환헤지 항목 금리차 뺀 대체판)",
           "entries": [nc_entry(it, sb[it.id]) for it in items]}
    with open(os.path.join(out_dir, "scoreboard_entries.json"), "w") as fh:
        json.dump(doc, fh, ensure_ascii=False)
    print(f"[nocarry] 끝 · 관문 {len(items) - len(bad)}/{len(items)} · {time.time() - t0:.0f}s", flush=True)
    return res


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else os.path.join(_ROOT, OUT_REL))
