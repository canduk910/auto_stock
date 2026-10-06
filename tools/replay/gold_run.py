#!/usr/bin/env python3
"""금 투자 추가 — 실행(엔진 검산 → 항목 계산 → 판정 → ETF 대조 → 성적표 항목 json).

    python tools/replay/gold_run.py <global_daily_krw.parquet> <gold_csv> <out_dir>
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.dirname(_HERE)
for _p in (_TOOLS, os.path.dirname(_TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import global_alloc as G  # noqa: E402
from replay import global_alloc_b as GB  # noqa: E402
from replay import gold_alloc as A  # noqa: E402
from replay import scoreboard as SB  # noqa: E402

OUT_REL = "_workspace/analysis/gold_20261006"
GROUP_TITLE = "여러 나라 자산배분 · 금 추가(원화 총수익 지수 모형 · 1995-01 ~ 2026-10)"
GROUP_TITLE_WF = "1차 후보 걷기 전진 · 금 추가(2005-12 ~ 2026-10 · 앞 10년은 학습)"
STATIC_RISKY = ("K200", "SPX", "NDX", "UST10", "USD", "GOLD", "GOLD_H", "LGOLD", "LGOLD_H", "LNDX")

ITEMS = [  # id, 이름, 설명, 비중, 주기, 판정 여부, 세금 메모
    ("GOLD", "금 단순 보유(환노출)", "런던 금 현물 달러 가격 원화 환산 · 보수 연 0.45% · 처음에 사서 보유",
     {"GOLD": 1.0}, None, False, "금 ETF 차익 15.4%"),
    ("GOLD_H", "금 단순 보유(환헤지)", "금 달러 가격 변화 + 원화·달러 금리차(헤지) · 보수 연 0.45% · 보유",
     {"GOLD_H": 1.0}, None, False, "금 ETF 차익 15.4%"),
    ("GOLD_LEV2", "금 2배 단순 보유(환노출)", "일일 2배 리셋 모형(조달 = 미국 3개월 금리 + 연 0.8%) · 환 1배 · 국내 상장 상품 없음 · 전 구간 모형",
     {"LGOLD": 1.0}, None, False, "차익 15.4%"),
    ("AU_LEV2_H", "금 2배 단순 보유(환헤지)", "일일 2배 리셋 모형 + 원화·달러 금리차 · 전 구간 모형",
     {"LGOLD_H": 1.0}, None, False, "차익 15.4%"),
    ("AU_K80G20", "KOSPI200 80 · 금 20", "KOSPI200 80% · 금(환노출) 20% · 월말 결정 · 다음 종가 되돌림",
     {"K200": 0.8, "GOLD": 0.2}, "M", True, "금 몫 차익 15.4%"),
    ("AU_B1G10", "60/40 + 금 10%", "B1(KOSPI200 60 · 미국채10년 40)을 비례 축소 = KOSPI200 54 · 미국채 36 · 금 10 · 월 되돌림",
     {"K200": 0.54, "UST10": 0.36, "GOLD": 0.10}, "M", True, "미국채·금 몫 차익 15.4%"),
    ("AU_PERM", "영구 포트폴리오(한국판)", "KOSPI200 25 · 미국채10년 25 · 금 25 · 원화 현금 25 · 월 되돌림",
     {"K200": 0.25, "UST10": 0.25, "GOLD": 0.25, "CASH": 0.25}, "M", True, "미국채·금 몫 차익 15.4% · 현금 이자 15.4%"),
    ("NQG_EW", "나스닥100 · 나스닥100 2배 · 금 · 현금 각 25%", "NDX(환노출) 25 · NDX 2배(환노출, = OL_NDX_U 모형) 25 · 금(환노출) 25 · "
     "원화 현금 25 · 분기 말 결정 · 다음 종가 되돌림", {"NDX": 0.25, "LNDX": 0.25, "GOLD": 0.25, "CASH": 0.25}, "Q", True,
     "차익 15.4% · 현금 이자 15.4%"),
    ("NQG_IV", "나스닥100 · 2배 · 금 위험 균형 + 현금 25%", "NDX · NDX 2배 · 금을 직전 252 거래일 변동성 역수로 75%, 원화 현금 25% · "
     "분기 말 결정(첫 252일은 균등)", "IV", "Q", True, "차익 15.4% · 현금 이자 15.4%"),
]
WF_ITEMS = [
    ("AU_WF", "걷기 전진 W + 금", "1차 걷기 전진 W(F1~F6 전체 후보 · 직전 10년 일 샤프 최고 → 다음 1년)에 위험 자산으로 금(환노출)을 더한 8자산판",
     G.RISKY + ("GOLD",), "해외·금 몫 차익 15.4%"),
    ("NQG_WF", "걷기 전진 W — 나스닥100 · 2배 · 금 · 현금", "1차 걷기 전진 W 규칙 그대로, 위험 자산 = NDX · NDX 2배(환노출) · 금 · 대피 = 원화 현금",
     ("NDX", "LNDX", "GOLD"), "차익 15.4% · 현금 이자 15.4%"),
]
COMPARE = [("K200", {"K200": 1.0}, None), ("B1", {"K200": 0.6, "UST10": 0.4}, "M"),
           ("NDX", {"NDX": 1.0}, None), ("OL_NDX_U", {"LNDX": 1.0}, None)]


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(os.path.join(OUT_REL, "progress.log"), "a") as f:
        f.write(line + "\n")


def crisis(dates, v) -> dict:
    return {k: A.window_return(dates, v, d0, d1) for k, (d0, d1) in A.CRISES.items()}


def summarize(m, v, a, b, rf, bench, sim=None, tax_v=None) -> dict:
    d = m.dates[a:b + 1]
    x = v[a:b + 1]
    met = SB.compute_metrics(d, x, rf, bench)
    met["crisis"] = crisis(d, x)
    yrs = (d[-1] - d[0]).days / 365.25
    if sim is not None:
        met["turnover_yr"] = sim.turnover / yrs
        met["cost_yr"] = sim.cost / yrs
    if tax_v is not None:
        met["after_tax_cagr"] = SB.cagr(tax_v[a], tax_v[b], d[0], d[-1])
    return met


def run(parquet: str, gold_csv: str, out_dir: str) -> None:
    t0 = time.time()
    df = pd.read_parquet(parquet)
    gold = A.load_gold_csv(gold_csv)
    gc = A.gold_columns(df, gold)
    df2 = df.join(gc)
    m = A.build_mkt(df2, STATIC_RISKY)
    gbm = GB.load(df, "U")
    a, b = GB.periods(gbm)["full"]
    res = {"period": [str(m.dates[a].date()), str(m.dates[b].date())], "check": {}, "items": {}, "compare": {}}
    rf = pd.Series(np.cumprod(1 + m.ret[:, m.i_cash]), index=m.dates)

    # ── 엔진 검산: 같은 비중을 GB 엔진과 이 엔진으로 ──
    curves = {}
    for cid, spec, fq in COMPARE:
        s = A.static_schedule(m, A.wvec(m, spec), a, b, fq)
        sim = A.simulate(m, s, a, b)
        st = A.simulate(m, s, a, b, tax=True)
        curves[cid] = (sim, st)
    one = lambda nm: (lambda w: (w.__setitem__(GB.COLS.index(nm), 1.0), w)[1])(np.zeros(GB.N))
    gb_sched = {"K200": GB.schedule(gbm, "B0", a, b), "B1": GB.schedule(gbm, "B1", a, b),
                "NDX": {a: one("NDX")}, "OL_NDX_U": {a: one("LNDX")}}
    for cid, s in gb_sched.items():
        vg = GB.simulate(gbm, s, a, b).value
        mine = curves[cid][0].value
        res["check"][cid] = {"max_abs_diff_cum": float(np.nanmax(np.abs(vg[a:b + 1] - mine[a:b + 1]))),
                             "final_gb": float(vg[b]), "final_mine": float(mine[b])}
    log(f"엔진 검산 {json.dumps({k: round(v['max_abs_diff_cum'], 10) for k, v in res['check'].items()})}")

    bench = pd.Series(curves["K200"][0].value[a:b + 1], index=m.dates[a:b + 1])
    for cid, (sim, st) in curves.items():
        res["compare"][cid] = summarize(m, sim.value, a, b, rf, bench, sim, st.value)
    base_full = {"B0": curves["K200"][0].value, "B1": curves["B1"][0].value}

    entries, vals = [], {}
    for iid, name, desc, spec, fq, judged, taxn in ITEMS:
        if spec == "IV":
            dps = [int(i) for i in G.decision_points(m.dates, fq) if a <= i < b]
            dps = dps if a in dps else [a] + dps
            mi = A.build_mkt(df2, ("NDX", "LNDX", "GOLD"))
            s_small = {i: A.inv_vol_weights(mi, i) for i in dps}
            s = {i: A.wvec(m, {c: float(w[j]) for j, c in enumerate(mi.cols) if w[j] != 0}) for i, w in s_small.items()}
            res.setdefault("iv_weights", {})
            res["iv_weights"] = {str(m.dates[i].date()): {c: round(float(w[j]), 4) for j, c in enumerate(mi.cols)}
                                 for i, w in list(s_small.items())[::8]}
        else:
            s = A.static_schedule(m, A.wvec(m, spec), a, b, fq)
        sim = A.simulate(m, s, a, b)
        st = A.simulate(m, s, a, b, tax=True)
        met = summarize(m, sim.value, a, b, rf, bench, sim, st.value)
        if judged:
            met["judge"] = A.judge(m, sim.value, base_full, a, b, 7)
        if fq == "M" and spec != "IV":
            sq = A.simulate(m, A.static_schedule(m, A.wvec(m, spec), a, b, "Q"), a, b)
            mq = SB.compute_metrics(m.dates[a:b + 1], sq.value[a:b + 1], rf, bench)
            met["quarterly_sensitivity"] = {k: mq[k] for k in ("cagr", "mdd", "sharpe", "total_return")}
        res["items"][iid] = met
        vals[iid] = (a, b, sim.value)
        status = ("통과" if met["judge"]["pass"] else "실패") if judged else "참고"
        entries.append(entry(iid, name, desc, m.dates, sim.value, a, b, met, status, taxn, GROUP_TITLE))
        log(f"{iid} 연복리 {met['cagr']:.4f} 낙폭 {met['mdd']:.4f} 샤프 {met['sharpe']:.3f} {status}")

    # ── 걷기 전진 — 먼저 원래 7자산으로 1차 W 재현 ──
    m7 = A.build_mkt(df, G.RISKY)
    wf7 = A.walk_forward_W(m7)
    v7 = A.simulate(m7, wf7["sched"], wf7["a"], wf7["b"]).value
    a7, b7 = wf7["a"], wf7["b"]
    pub = json.load(open("_workspace/analysis/global_alloc_20261006/results.json"))["M"]["cands"]["W"]
    yrs7 = (m7.dates[b7] - m7.dates[a7]).days / 365.25
    res["check"]["W_7asset"] = {"cagr_mine": float(v7[b7] ** (1 / yrs7) - 1), "cagr_published": pub["cagr"],
                                "start": str(m7.dates[a7].date()), "picks": wf7["picks"]}
    log(f"W 7자산 재현 연복리 {res['check']['W_7asset']['cagr_mine']:.5f} (공표 {pub['cagr']:.5f})")

    for iid, name, desc, risky, taxn in WF_ITEMS:
        mw = A.build_mkt(df2, risky)
        wf = A.walk_forward_W(mw)
        aw, bw = wf["a"], wf["b"]
        sim = A.simulate(mw, wf["sched"], aw, bw)
        st = A.simulate(mw, wf["sched"], aw, bw, tax=True)
        mb = A.build_mkt(df2, ("K200", "UST10"))
        bb0 = A.simulate(mb, {aw: A.wvec(mb, {"K200": 1.0})}, aw, bw).value
        bb1 = A.simulate(mb, A.static_schedule(mb, A.wvec(mb, {"K200": 0.6, "UST10": 0.4}), aw, bw, "M"), aw, bw).value
        bench_w = pd.Series(bb0[aw:bw + 1], index=mw.dates[aw:bw + 1])
        met = summarize(mw, sim.value, aw, bw, rf, bench_w, sim, st.value)
        met["judge"] = A.judge(mw, sim.value, {"B0": bb0, "B1": bb1}, aw, bw, 7)
        met["picks"] = wf["picks"]
        lastd = max(wf["sched"])
        met["last_weights"] = {"date": str(mw.dates[lastd].date()),
                               "w": {c: round(float(x), 4) for c, x in zip(mw.cols, wf["sched"][lastd]) if x}}
        res["items"][iid] = met
        res["compare"].setdefault("wf_window", {})
        res["compare"]["wf_window"]["K200"] = SB.compute_metrics(mw.dates[aw:bw + 1], bb0[aw:bw + 1], rf, bench_w)
        res["compare"]["wf_window"]["B1"] = SB.compute_metrics(mw.dates[aw:bw + 1], bb1[aw:bw + 1], rf, bench_w)
        res["compare"]["wf_window"]["K200"]["crisis"] = crisis(mw.dates[aw:bw + 1], bb0[aw:bw + 1])
        res["compare"]["wf_window"]["B1"]["crisis"] = crisis(mw.dates[aw:bw + 1], bb1[aw:bw + 1])
        status = "통과" if met["judge"]["pass"] else "실패"
        entries.append(entry(iid, name, desc, mw.dates, sim.value, aw, bw, met, status, taxn, GROUP_TITLE_WF))
        log(f"{iid} 연복리 {met['cagr']:.4f} 낙폭 {met['mdd']:.4f} 샤프 {met['sharpe']:.3f} {status} ({time.time() - t0:.0f}s)")

    # ── ETF 대조 ──
    gfee = A.GOLD_FEE
    dt = pd.Series(m.dates, index=m.dates).diff().dt.days.fillna(1) / 365.0
    res["etf"] = {}
    for tk, col, nm in (("132030", "GOLD_hret", "KODEX 골드선물(H)"), ("411060", "GOLD_ret", "ACE KRX금현물"),
                        ("319640", "GOLD_hret", "TIGER 골드선물(H)")):
        try:
            px = A.etf_close(tk)
            mr = df2[col] - gfee * dt
            res["etf"][tk] = {"name": nm, "model_col": col, **A.tracking(mr, px)}
            e = res["etf"][tk]
            log(f"ETF {tk} {nm} {e['start']}~ 모형 {e['cagr_model']:.4f} ETF {e['cagr_etf']:.4f} 월상관 {e['corr_monthly']:.3f}")
        except Exception as ex:  # 한 상품 실패가 전체를 멈추지 않게
            res["etf"][tk] = {"name": nm, "error": repr(ex)}

    res["gold_data"] = {"source": "usagold.com Daily Gold Price History (XAUUSD, 미 산악시간 15:00 기록)",
                        "first": str(gold.index[0].date()), "last": str(gold.index[-1].date()), "rows": int(len(gold))}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "results.json"), "w") as f:
        json.dump(SB._clean(res), f, ensure_ascii=False, indent=1)
    doc = {"source": "gold 2026-10-06 · tools/replay/gold_run.py (gold_alloc · global_alloc_b 관례)", "entries": entries}
    with open(os.path.join(out_dir, "scoreboard_entries.json"), "w") as f:
        json.dump(SB._clean(doc), f, ensure_ascii=False)
    log(f"끝 {time.time() - t0:.0f}s")


def entry(iid, name, desc, dates, v, a, b, met, status, taxn, gtitle) -> dict:
    d = dates[a:b + 1]
    x = v[a:b + 1]
    return {"id": iid, "name": name, "desc": desc, "period": [str(d[0].date()), str(d[-1].date())],
            "curve": {"dates": [str(t.date()) for t in d], "cum": [round(float(y / x[0]), 8) for y in x]},
            "yearly": {k: y["ret"] for k, y in met["yearly"].items()},
            "status": status, "status_ref": f"{OUT_REL}/result.md §2 · prereg.frozen.md §6",
            "group_title": gtitle, "turnover_yr": met.get("turnover_yr"), "cost_yr": met.get("cost_yr"),
            "after_tax_cagr": met.get("after_tax_cagr"), "tax_note": taxn, "source": "tools/replay/gold_run.py"}


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], sys.argv[3])
