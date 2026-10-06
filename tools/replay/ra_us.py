#!/usr/bin/env python3
"""(라) 장세 규칙을 S&P500 · 나스닥100 에 옮기기 (사전 등록 ``ra_us_20261006/prereg.frozen.md``).

원판 = ``regime_v2`` 의 (라) 「120일선 20일 기울기 > 0 × 시장 폭 ≤ 0.3」(한국 1997~2012 학습으로 고른 규칙).
미국 지수에 규칙을 바꾸지 않고 옮기면 그 자체가 표본 밖 검증이다.

판 A = 규칙 무변경 이식(미국 폭 자료 없음 → 폭 조건 「항상 거짓」) · A' = 한국 KOSPI200 폭 없이(폭의 몫) ·
B = 폭이 필요 없는 원판 상위 2·3·4위 이식 · C = 폭·코스닥 없는 92 후보 중 미국 1995~2012 학습 MAR 최대.
엔진 = ``regime_v2`` 의 지수 노출 사다리를 지수·2배 열을 인자로 받게 일반화한 것(한국 원판 재현 일치 확인).

    python tools/replay/ra_us.py <out_dir>
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_HERE), os.path.dirname(os.path.dirname(_HERE))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import global_alloc as G  # noqa: E402
from replay import global_alloc_b as GB  # noqa: E402
from replay import global_alloc_data as GD  # noqa: E402
from replay import regime_gate as RG  # noqa: E402
from replay import regime_gate_alloc as RA  # noqa: E402
from replay import regime_v2 as V  # noqa: E402

GLOBAL_DIR = os.path.join(RG.MAIN_REPO, "data/archive/global_long")
PARQUET = os.path.join(GLOBAL_DIR, "global_daily_krw.parquet")
RAW = os.path.join(GLOBAL_DIR, "raw")
PRICE_RAW = {"SPX": "yahoo_GSPC.json", "NDX": "yahoo_NDX.json"}     # 판단 = 가격지수(한국 원판과 같은 자리)
ASSETS = ("SPX", "NDX")
CCYS = ("U", "H")                                                    # 환노출 · 환헤지
CCY_NAMES = {"U": "환노출", "H": "환헤지"}
ASSET_NAMES = {"SPX": "S&P500", "NDX": "나스닥100", "K200": "KOSPI200"}
LADDER = V.LADDER
COST_RT = V.COST_RT
BOOT_REPS = 5000
BOOT_SEED = 20261006
N_BONF = 20

US_WINS = {"T": ("1995-01-03", "2012-12-28"), "V": ("2013-01-02", "2020-12-30"),
           "H": ("2021-01-04", "2026-10-02"), "FULL": ("1995-01-03", "2026-10-02")}
KR_WINS = RG.WINS
US_ERAS = (("1995-2001", ("1995-01-01", "2001-12-31")),) + tuple(RA.ERAS[1:])
CRISES = (("닷컴 2000~02", ("2000-01-01", "2002-12-31")), ("2008", ("2008-01-01", "2008-12-31")),
          ("2020", ("2020-01-01", "2020-12-31")), ("2022", ("2022-01-01", "2022-12-31")))

RULE_RA = (("T7", ">", 0.0), ("R5", "<=", 0.3))
MAP_RA = {"00": 0.0, "01": 1.0, "10": 2.0, "11": 0.0}
B_RULES = {
    "B2": ((("T3", ">", 0.0), ("T7", ">", 0.0)), {"00": 0.5, "01": 0.0, "10": 0.0, "11": 2.0}),
    "B3": ((("T3", ">", 0.0), ("R4", "<=", -0.2)), {"00": 0.0, "01": 0.5, "10": 2.0, "11": 0.5}),
    "B4": ((("T4", ">", 0.0), ("T7", ">", 0.0)), {"00": 0.0, "01": 0.0, "10": 0.0, "11": 2.0}),
}
NO_US = ("T8", "T9", "R5")                     # 시장 폭 · 코스닥 — 미국 대응 계열 없음


# ═════════════════════════════════ 특징 ═════════════════════════════════

def feats_from_close(c: pd.Series) -> pd.DataFrame:
    """종가 계열(자기 달력) → regime_v2 와 같은 식의 특징. 폭·코스닥 칸은 결측(= 조건 거짓)."""
    f = pd.DataFrame(index=c.index)
    for k, n in (("T1", 20), ("T2", 60), ("T3", 120), ("T4", 200)):
        f[k] = c / c.rolling(n).mean() - 1
    for k, n in (("T5", 20), ("T6", 60), ("T7", 120)):
        s = c.rolling(n).mean()
        f[k] = s / s.shift(20) - 1
    lr = np.log(c).diff()
    f["R1"] = lr.rolling(20).std() * np.sqrt(252)
    f["R2"] = lr.rolling(60).std() * np.sqrt(252)
    f["R3"] = c / c.rolling(60).max() - 1
    f["R4"] = c / c.rolling(250).max() - 1
    for k in NO_US:
        f[k] = np.nan
    return f


def us_close(asset: str, krw: bool = False) -> pd.Series:
    """미국 거래일 달력의 가격지수 종가(``krw`` = 같은 날 뉴욕 정오 원/달러를 곱한 원화 환산가)."""
    c = GD._yahoo(os.path.join(RAW, PRICE_RAW[asset]))
    if krw:
        fx = GD._fred(os.path.join(RAW, "fred_DEXKOUS.csv"))
        fx = fx.reindex(fx.index.union(c.index)).ffill().reindex(c.index)
        c = (c * fx).dropna()
    return c


def align_before(f: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """KRX 거래일 D 에 D 보다 앞선 마지막 미국 관측의 특징을 붙인다(수익 계열과 같은 정렬)."""
    src = f.shift(1, freq="D")
    return src.reindex(src.index.union(dates)).ffill().reindex(dates)


def us_features(asset: str, dates: pd.DatetimeIndex, krw: bool = False) -> pd.DataFrame:
    return align_before(feats_from_close(us_close(asset, krw)), dates)


# ═════════════════════════════════ 일반 엔진 ═════════════════════════════════

def cols(asset: str) -> tuple[int, int]:
    return GB.COLS.index(asset), GB.COLS.index("L" + asset)


def weights(e: float, ix: int, il: int) -> np.ndarray:
    w = np.zeros(GB.N)
    if e == 2.0:
        w[il] = 1.0
    else:
        w[ix] = e
        w[GB.I_CASH] = 1.0 - e
    return w


def expo_of(keys: np.ndarray, amap: dict) -> np.ndarray:
    return V.expo_of(keys, amap)


def schedule(m: GB.Mkt, expo: np.ndarray, a: int, b: int, ix: int, il: int) -> dict:
    dps = set(int(i) for i in GB.decision_points(m.dates, "M") if a <= i < b)
    dps.add(a)
    for i in range(a + 1, b):
        if expo[i] != expo[i - 1]:
            dps.add(i)
    return {i: weights(float(expo[i]), ix, il) for i in sorted(dps)}


def static_schedule(m: GB.Mkt, w: np.ndarray, a: int, b: int) -> dict:
    dps = set(int(i) for i in GB.decision_points(m.dates, "M") if a <= i < b)
    dps.add(a)
    return {i: w for i in sorted(dps)}


def learn(m: GB.Mkt, keys: np.ndarray, win, ix: int, il: int) -> dict:
    """``regime_v2.learn_index`` 의 일반판 — 칸마다 학습 창 t → t+2 수익의 평균 로그 성장 최대 노출."""
    a, b = RA.win_ab(m, win)
    r = m.ret - m.fee
    t = np.arange(a, b - 1)
    out, detail = {}, {}
    for k in sorted({x for x in keys[t] if x is not None}):
        sel = t[keys[t] == k] + 2
        n = int(len(sel))
        g = {}
        for e in LADDER:
            rr = r[sel, il] if e == 2.0 else e * r[sel, ix] + (1 - e) * r[sel, GB.I_CASH]
            g[e] = float(np.mean(np.log1p(rr))) * 252 if n else float("nan")
        if n < V.MIN_CELL_DAYS:
            best = 1.0
        else:
            best = LADDER[0]
            for e in LADDER[1:]:
                if g[e] > g[best]:
                    best = e
        out[k] = best
        detail[k] = {"n": n, "growth_ann": g, "chosen": best, "default": n < V.MIN_CELL_DAYS}
    return {"map": out, "detail": detail}


def switches_per_year(m: GB.Mkt, expo: np.ndarray, win) -> float:
    return V.switches_per_year(m, expo, win)


def us_candidates() -> list[tuple]:
    return [r for r in V.candidates() if not any(c[0] in NO_US for c in r)]


# ═════════════════════════════════ 지표 · 부트스트랩 ═════════════════════════════════

def win_metrics(m: GB.Mkt, sim: GB.Sim, win, expo: np.ndarray | None) -> dict:
    a, b = RA.win_ab(m, win)
    mt = GB.metrics(m, sim.value, a, b)
    yrs = (m.dates[b] - m.dates[a]).days / 365.25
    mt["turnover_yr"] = sim.turnover / yrs
    mt["cost_yr"] = sim.cost / yrs
    if expo is not None:
        mt["switch_yr"] = switches_per_year(m, expo, win)
        held = expo[a:b]
        mt["lev2_share"] = float((held == 2.0).mean())
        mt["mean_expo"] = float(held.mean())
    return mt


def boot(rc: np.ndarray, rb: np.ndarray, cash: np.ndarray, reps: int = BOOT_REPS, n_bonf: int = N_BONF) -> dict:
    rng = np.random.default_rng(BOOT_SEED)
    n = len(rc)
    acc = {k: np.empty(reps) for k in ("mar", "cagr", "sharpe")}
    for k in range(reps):
        ix = G.stationary_idx(n, 12.0, rng)
        acc["mar"][k] = G.m_mar(rc[ix]) - G.m_mar(rb[ix])
        acc["cagr"][k] = RA.m_cagr(rc[ix]) - RA.m_cagr(rb[ix])
        acc["sharpe"][k] = G.m_sharpe(rc[ix], cash[ix]) - G.m_sharpe(rb[ix], cash[ix])
    pt = {"mar": G.m_mar(rc) - G.m_mar(rb), "cagr": RA.m_cagr(rc) - RA.m_cagr(rb),
          "sharpe": G.m_sharpe(rc, cash) - G.m_sharpe(rb, cash)}
    return {k: {"d": float(pt[k]), "p05": float(np.percentile(acc[k], 5)), "p95": float(np.percentile(acc[k], 95)),
                "p_bonf": float(np.percentile(acc[k], 100 * 0.10 / n_bonf))} for k in acc}


def judge(bv: dict, bh: dict) -> str:
    if bv["mar"]["p05"] > 0:
        return "우위" if bh["mar"]["d"] > 0 else "검증만"
    if bv["mar"]["p95"] < 0:
        return "기준이 낫다"
    return "가려지지 않음"


def era_stats(dates, v, eras) -> dict:
    s = pd.Series(np.asarray(v, float), index=pd.DatetimeIndex(dates))
    out = {}
    for nm, (w0, w1) in eras:
        before = s.loc[:pd.Timestamp(w0) - pd.Timedelta(days=1)]
        seg = s.loc[w0:w1]
        if not len(seg):
            continue
        d0, x0 = (before.index[-1], before.iloc[-1]) if len(before) else (seg.index[0], seg.iloc[0])
        x = np.r_[x0, seg.to_numpy()]
        y = (seg.index[-1] - d0).days / 365.25
        cg = float((x[-1] / x[0]) ** (1 / y) - 1) if x[-1] > 0 else -1.0
        mdd = float((x / np.maximum.accumulate(x) - 1).min())
        out[nm] = {"cagr": cg, "mdd": mdd, "ret": float(x[-1] / x[0] - 1)}
    return out


# ═════════════════════════════════ 판 실행 ═════════════════════════════════

class Runner:
    """한 시장(통화판) · 한 지수에 대해 노출 계열 → 창별 결과."""

    def __init__(self, m: GB.Mkt, asset: str, wins: dict, eras):
        self.m, self.asset, self.wins, self.eras = m, asset, wins, eras
        self.ix, self.il = cols(asset)
        self.res: dict = {}

    def run_expo(self, name: str, expo: np.ndarray, extra: dict | None = None) -> dict:
        return self._run(name, lambda a, b: schedule(self.m, expo, a, b, self.ix, self.il), expo, extra)

    def run_static(self, name: str, w: np.ndarray, extra: dict | None = None) -> dict:
        return self._run(name, lambda a, b: static_schedule(self.m, w, a, b), None, extra)

    def _run(self, name, sched_fn, expo, extra) -> dict:
        m = self.m
        r = {"windows": {}, **(extra or {})}
        for wn, win in self.wins.items():
            a, b = RA.win_ab(m, win)
            sim = GB.simulate(m, sched_fn(a, b), a, b)
            r["windows"][wn] = {"metrics": win_metrics(m, sim, win, expo), "monthly": GB.monthly(m, sim.value, a, b),
                                "value": sim.value[a:b + 1], "dates": m.dates[a:b + 1]}
            if wn == "FULL":
                st = GB.simulate(m, sched_fn(a, b), a, b, tax=True)
                vt = st.value[a:b + 1]
                yrs = (m.dates[b] - m.dates[a]).days / 365.25
                r["after_tax_cagr"] = float((vt[-1] / vt[0]) ** (1 / yrs) - 1)
                r["eras"] = era_stats(m.dates[a:b + 1], sim.value[a:b + 1], self.eras)
                r["crises"] = {k: v["ret"] for k, v in era_stats(m.dates[a:b + 1], sim.value[a:b + 1],
                                                                  CRISES).items()}
        self.res[name] = r
        return r

    def baselines(self) -> None:
        for e, nm in ((1.0, "hold"), (2.0, "lev2"), (0.5, "fix050"), (0.75, "fix075")):
            self.run_expo(nm, np.full(len(self.m.dates), e))
        w = np.zeros(GB.N)
        w[self.ix], w[GB.I_UST] = 0.6, 0.4
        self.run_static("b6040", w)

    def judge_vs(self, name: str, refs=("hold", "fix075")) -> dict:
        out = {}
        for ref in refs:
            bt = {}
            for wn in ("T", "V", "H"):
                mo, mb = self.res[name]["windows"][wn]["monthly"], self.res[ref]["windows"][wn]["monthly"]
                bt[wn] = boot(mo["r"].to_numpy(), mb["r"].to_numpy(), mb["cash"].to_numpy())
            out[ref] = {"boot": bt, "judge": judge(bt["V"], bt["H"])}
        self.res[name]["vs"] = out
        return out


def select_c(m: GB.Mkt, f: pd.DataFrame, asset: str, win) -> dict:
    ix, il = cols(asset)
    rows = []
    for i, rule in enumerate(us_candidates()):
        keys = V.rule_keys(f, rule)
        lr = learn(m, keys, win, ix, il)
        expo = expo_of(keys, lr["map"])
        sw = switches_per_year(m, expo, win)
        a, b = RA.win_ab(m, win)
        sim = GB.simulate(m, schedule(m, expo, a, b, ix, il), a, b)
        mt = GB.metrics(m, sim.value, a, b)
        rows.append({"i": i, "rule": [list(x) for x in rule], "name": V.rule_name(rule), "n_cond": len(rule),
                     "map": lr["map"], "switch_T": sw, "eligible": sw <= V.SWITCH_CAP, "T_mar": mt["mar"],
                     "T_cagr": mt["cagr"], "T_mdd": mt["mdd"]})
    elig = [r for r in rows if r["eligible"] and r["T_mar"] is not None]
    best = max(elig, key=lambda r: (r["T_mar"], -r["n_cond"], -r["i"]))
    top = sorted(elig, key=lambda r: -r["T_mar"])[:5]
    return {"best": best, "n_cand": len(rows), "n_eligible": len(elig), "top5": top}


# ═════════════════════════════════ 한국 재현 · A' ═════════════════════════════════

def korea_stage() -> dict:
    m = V.load_mkt()
    f = V.features(m)
    run = Runner(m, "K200", KR_WINS, RA.ERAS)
    keys = V.rule_keys(f, RULE_RA)
    expo = expo_of(keys, MAP_RA)
    # 재현 관문 — 원판 regime_v2.run_index 와 이 엔진 · 성적표 곡선
    a, b = RA.win_ab(m, KR_WINS["FULL"])
    mine = GB.simulate(m, schedule(m, expo, a, b, *cols("K200")), a, b).value[a:b + 1]
    orig = V.run_index(m, expo, KR_WINS["FULL"]).value[a:b + 1]
    sb_path = os.path.join(os.path.dirname(os.path.dirname(_HERE)),
                           "_workspace/analysis/regime_v2_20261006/scoreboard_entries.json")
    ent = next(e for e in json.load(open(sb_path))["entries"] if e["id"] == "R2_IDX_ra")
    cum = np.asarray(ent["curve"]["cum"], float)
    err_engine = float(np.max(np.abs(mine / orig - 1)))
    err_sb = float(np.max(np.abs(mine / mine[0] / cum - 1))) if len(cum) == len(mine) else float("inf")
    print(f"[ra_us] 한국 재현: 엔진 오차 {err_engine:.2e} · 성적표 곡선 오차 {err_sb:.2e} · 길이 {len(mine)}/{len(cum)}",
          flush=True)
    if err_engine > 1e-9 or err_sb > 1e-9:
        raise SystemExit("[ra_us] 한국 원판 재현 불일치 — 멈춘다")
    run.baselines()                                    # b6040 = 원판 B1(KOSPI200 60 · 미국채 40)과 같은 정의
    run.run_expo("ra_orig", expo, {"rule": "원판(폭 있음)"})
    f0 = f.copy()
    f0["R5"] = np.nan
    expo0 = expo_of(V.rule_keys(f0, RULE_RA), MAP_RA)
    run.run_expo("A", expo0, {"rule": "폭 없음(조건2 항상 거짓)"})
    for bn, (rule, amap) in B_RULES.items():
        run.run_expo(bn, expo_of(V.rule_keys(f, rule), amap))
    for nm in ("ra_orig", "A", "B2", "B3", "B4"):
        run.judge_vs(nm)
    # 폭의 몫 = 원판 − 폭 없음
    share = {}
    for wn in ("T", "V", "H"):
        mo = run.res["ra_orig"]["windows"][wn]["monthly"]
        mb = run.res["A"]["windows"][wn]["monthly"]
        share[wn] = boot(mo["r"].to_numpy(), mb["r"].to_numpy(), mb["cash"].to_numpy())
    run.res["A"]["breadth_share"] = share
    agree = float((expo0 == expo).mean())
    run.res["A"]["agree_with_orig"] = agree
    return {"run": run, "repro": {"err_engine": err_engine, "err_scoreboard": err_sb, "n": len(mine)},
            "expo": {"orig": expo, "A": expo0}}


# ═════════════════════════════════ 미국 ═════════════════════════════════

def us_stage() -> dict:
    df = pd.read_parquet(PARQUET)
    mk = {"U": GB.load(df, "U"), "H": GB.load(df, "H", hedged=True)}
    out = {}
    for asset in ASSETS:
        f = us_features(asset, mk["U"].dates)
        fk = us_features(asset, mk["U"].dates, krw=True)
        for ccy in CCYS:
            t0 = time.time()
            m = mk[ccy]
            run = Runner(m, asset, US_WINS, US_ERAS)
            run.baselines()
            keys = V.rule_keys(f, RULE_RA)
            expoA = expo_of(keys, MAP_RA)
            run.run_expo("A", expoA, {"rule": V.rule_name(RULE_RA) + " (폭 = 항상 거짓)"})
            run.run_expo("A_krwsig", expo_of(V.rule_keys(fk, RULE_RA), MAP_RA), {"rule": "보조 — 원화 환산가 신호"})
            for bn, (rule, amap) in B_RULES.items():
                run.run_expo(bn, expo_of(V.rule_keys(f, rule), amap), {"rule": V.rule_name(rule), "map": amap})
            sel = select_c(m, f, asset, US_WINS["T"])
            best = sel["best"]
            rule = tuple(tuple(x) for x in best["rule"])
            run.run_expo("C", expo_of(V.rule_keys(f, rule), best["map"]),
                         {"rule": best["name"], "map": best["map"], "select": {k: v for k, v in sel.items()
                                                                                if k != "best"} | {"best": best}})
            for nm in ("A", "A_krwsig", "B2", "B3", "B4", "C"):
                run.judge_vs(nm)
            out[(asset, ccy)] = run
            r = run.res
            print(f"[ra_us] {asset}/{ccy} A V {r['A']['windows']['V']['metrics']['cagr']:+.3f} "
                  f"{r['A']['vs']['hold']['judge']}/{r['A']['vs']['fix075']['judge']} · C = {best['name']} "
                  f"{best['map']} · {time.time() - t0:.0f}s", flush=True)
    return out


# ═════════════════════════════════ 산출 ═════════════════════════════════

def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items() if k not in ("value", "monthly", "dates")}
    if isinstance(o, (list, tuple)):
        return [_clean(x) for x in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, pd.Timestamp):
        return str(o.date())
    return o


PLAN_DESC = {
    "A": "(라) 규칙 무변경 이식 — 120일선 20일 기울기 > 0 이면 2배, 아니면 원화 현금(미국 시장 폭 자료 없음 → 폭 조건 항상 거짓)",
    "B2": "원판 (라) 2위 이식 — 종가가 120일선 위·120일선 상승 = 2배 · 둘 다 아니면 0.5배 · 나머지 현금",
    "B3": "원판 (라) 3위 이식 — 종가가 120일선 위·250일 고점 −20% 안 = 2배 · 고점 −20% 밖 = 0.5배 · 나머지 현금",
    "B4": "원판 (라) 4위 이식 — 종가가 200일선 위·120일선 상승 = 2배 · 나머지 현금",
    "C": "폭·코스닥 없는 92 후보 중 미국 1995~2012 학습 MAR 최대 규칙 · 칸별 노출 학습 고정",
}


def build_entries(SB, kr: dict, us: dict, rf: pd.Series, bench: pd.Series) -> list:
    entries = []

    def ent(id_, name, desc, r, group_title, status_ref):
        w = r["windows"]["FULL"]
        d, v = w["dates"], w["value"]
        mt = SB.compute_metrics(d, v, rf, bench)
        r["full_sb"] = mt
        fm = w["metrics"]
        entries.append({"id": id_, "name": name, "desc": desc, "group": "ra_us", "group_title": group_title,
                        "status": "참고", "status_ref": status_ref, "source": "tools/replay/ra_us.py",
                        "period": [str(d[0].date()), str(d[-1].date())],
                        "curve": {"dates": [str(x.date()) for x in d], "cum": [float(x / v[0]) for x in v]},
                        "yearly": {str(y): x["ret"] for y, x in mt["yearly"].items()},
                        "turnover_yr": fm["turnover_yr"], "cost_yr": fm["cost_yr"],
                        "after_tax_cagr": r["after_tax_cagr"],
                        "tax_note": "해외 지수·2배 차익 15.4% · 현금 이자 15.4%" if "K200" not in id_ else
                        "국내 KOSPI200·2배 차익 비과세 가정 · 현금 이자 15.4%"})

    gt = "(라) 장세 규칙 미국 이식(ra_us) · 참고"
    ref = "_workspace/analysis/ra_us_20261006/result.md"
    ent("RAUS_K200_A", "KOSPI200 (라) 폭 없이 — 120일선 기울기 > 0 이면 2배",
        "원판 R2_IDX_ra 에서 시장 폭 조건을 항상 거짓으로 둔 판(폭의 몫 대조) · 1997~", kr["run"].res["A"], gt, ref)
    for (asset, ccy), run in us.items():
        for p in ("A", "B2", "B3", "B4", "C"):
            r = run.res[p]
            desc = PLAN_DESC[p] + (f" — 고른 규칙 「{r['rule']}」 행동 {r['map']}" if p == "C" else "")
            ent(f"RAUS_{asset}_{ccy}_{p}", f"{ASSET_NAMES[asset]}({CCY_NAMES[ccy]}) 장세 규칙 {p}",
                desc + f" · 2배 = 일일 리셋 모형({'환 1배' if ccy == 'U' else '환헤지'}) · 비용 왕복 0.38%", r, gt, ref)
    return entries


def summarize(run: Runner, names) -> dict:
    out = {}
    for nm in names:
        r = run.res[nm]
        row = {"windows": {wn: x["metrics"] for wn, x in r["windows"].items()}, "eras": r.get("eras"),
               "crises": r.get("crises"), "after_tax_cagr": r.get("after_tax_cagr")}
        for k in ("rule", "map", "vs", "select", "breadth_share", "agree_with_orig", "full_sb"):
            if k in r:
                row[k] = r[k]
        out[nm] = row
    return out


def main(out_dir: str) -> None:
    from replay import scoreboard as SB
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    kr = korea_stage()
    print(f"[ra_us] 한국 끝 {time.time() - t0:.0f}s", flush=True)
    us = us_stage()
    m = kr["run"].m
    rf = pd.Series(np.cumprod(1 + m.ret[:, GB.I_CASH]), index=m.dates)
    ik = GB.COLS.index("K200")
    bench = pd.Series(np.cumprod(1 + (m.ret[:, ik] - m.fee[:, ik])), index=m.dates)
    entries = build_entries(SB, kr, us, rf, bench)
    # 기준선·보조 곡선의 성적표 지표(결과 문서용)
    base = ("hold", "lev2", "fix050", "fix075", "b6040")
    for run in [kr["run"]] + list(us.values()):
        for nm in base + ("ra_orig", "A_krwsig", "B2", "B3", "B4"):
            if nm in run.res and "full_sb" not in run.res[nm]:
                w = run.res[nm]["windows"]["FULL"]
                run.res[nm]["full_sb"] = SB.compute_metrics(w["dates"], w["value"], rf, bench)
    res = {"meta": {"prereg_sha256": open(os.path.join(out_dir, "prereg.sha256")).read().split()[0],
                    "repro": kr["repro"], "n_us_candidates": len(us_candidates()), "us_wins": US_WINS,
                    "kr_wins": KR_WINS},
           "korea": summarize(kr["run"], base + ("ra_orig", "A", "B2", "B3", "B4")),
           "us": {f"{a}_{c}": summarize(run, base + ("A", "A_krwsig", "B2", "B3", "B4", "C"))
                  for (a, c), run in us.items()}}
    with open(os.path.join(out_dir, "result.json"), "w") as fh:
        json.dump(_clean(res), fh, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "scoreboard_entries.json"), "w") as fh:
        json.dump({"source": "ra_us 2026-10-06 · tools/replay/ra_us.py (_workspace/analysis/ra_us_20261006/result.md)",
                   "entries": [_clean_entry(e) for e in entries]}, fh, ensure_ascii=False)
    import pickle
    scr = os.path.join(RG.SCRATCH_ROOT, "ra_us")
    os.makedirs(scr, exist_ok=True)
    with open(os.path.join(scr, "runs.pkl"), "wb") as fh:
        pickle.dump({"korea": kr["run"].res, "us": {k: v.res for k, v in us.items()}}, fh)
    print(f"[ra_us] 끝 · 성적표 항목 {len(entries)} · {time.time() - t0:.0f}s", flush=True)


def _clean_entry(e):
    if isinstance(e, dict):
        return {str(k): _clean_entry(v) for k, v in e.items()}
    if isinstance(e, (list, tuple)):
        return [_clean_entry(x) for x in e]
    return _clean(e)


def posthoc(out_dir: str) -> dict:
    """사후 1(결과 문서 「사후 변경」): A·B 는 미국에서 아무것도 고르지 않아 30년 전체가 표본 밖이다 —
    FULL 월 수익으로 같은 부트스트랩(판 − 지수 보유 · 판 − 고정 0.75배 · 판 − 2배 보유)을 설명용으로 낸다(판정 아님)."""
    import pickle
    with open(os.path.join(RG.SCRATCH_ROOT, "ra_us", "runs.pkl"), "rb") as fh:
        runs = pickle.load(fh)
    out = {}
    for key, res in [("K200", runs["korea"])] + [(f"{a}_{c}", r) for (a, c), r in runs["us"].items()]:
        row = {}
        for p in ("A", "B2", "B3", "B4", "C", "ra_orig"):
            if p not in res:
                continue
            mo = res[p]["windows"]["FULL"]["monthly"]
            row[p] = {}
            for ref in ("hold", "fix075", "lev2"):
                mb = res[ref]["windows"]["FULL"]["monthly"]
                row[p][ref] = boot(mo["r"].to_numpy(), mb["r"].to_numpy(), mb["cash"].to_numpy())
            v = res[p]["windows"]["FULL"]["value"]
            d = res[p]["windows"]["FULL"]["dates"]
            dd = v / np.maximum.accumulate(v) - 1
            k = int(np.argmin(dd))
            row[p]["mdd_trough"] = str(d[k].date())
            row[p]["mdd_peak"] = str(d[int(np.argmax(v[:k + 1]))].date())
        out[key] = row
    with open(os.path.join(out_dir, "posthoc.json"), "w") as fh:
        json.dump(_clean(out), fh, ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    if sys.argv[1] == "posthoc":
        posthoc(sys.argv[2])
    else:
        main(sys.argv[1])
