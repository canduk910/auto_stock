#!/usr/bin/env python3
"""관문 2 — 공용 층으로 cycle391b 묶음 B 판정판(n=495 · +0.315R · 연 +16.1% · 근사 MDD −11.6%p)을 다시 낸다.

원 가정 그대로(cycle391 유니버스 · 비용 왕복 0.06/0.11% · R 슬리브 4칸 · 씨앗 20261002/20263002) 돌린다.
단계별 대조: 시장 유닛(운영 classify ↔ cycle391 pandas) → 원 거래 목록(cycle391 ``gen_trades("donchian")``
전 필드) → 판정 수치(cycle391b ``results.json`` B) → 판정 거래 목록.
유니버스 분류만 원본 모듈 함수를 부른다(전략 고유 — 공용 층 검증 대상 아님).

실행: python tools/replay/audit/gate_c391b.py → 표준출력 + 스크래치 audit/gate_c391b.json
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import config as C  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.audit import market_unit as MU  # noqa: E402
from replay.audit import panel as PN  # noqa: E402
from replay.strategies import etf_trend_b as EB  # noqa: E402

BASE_PY = os.path.join(C.REPO, "_workspace/domain_consult/cycle391_etf_s0_remeasure.py")
BASE_SHA = "c05d4d5ab0d252e181ab37b03c356fc7ae8655416954337c820a8f9cca27aea0"
REF_JSON = ("/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/"
            "1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/c391b/results.json")
FULL_START, FULL_END = "2021-01-01", "2026-09-23"
PERIOD_A = ("2021-01-01", "2022-12-31")
SEED_BOOT, SEED_SLEEVE = 20261002, 20263002


def load_c391():
    if PN.sha256(BASE_PY) != BASE_SHA:
        raise SystemExit("[gate391b] cycle391 모듈 sha256 불일치 — 멈춘다")
    spec = importlib.util.spec_from_file_location("c391", BASE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def classify(c391):
    meta, _last_date, _n = c391.load_meta()
    dbj = json.load(open(c391.DB_FIELDS))
    db = {r["ticker"]: r for r in dbj["rows"]}
    agr = c391.agreement(meta, db, c391.rule_v1)
    rule_fn = c391.rule_v1 if (agr["precision"] >= 0.9 and agr["recall"] >= 0.9) else c391.rule_v3
    cls = {}
    for t, mm in meta.items():
        if t in db:
            r = db[t]
            v = (r["grp"] == "EF" and r["txtn"] == "01" and r["mult"] == "1" and (r["heed"] or "N") != "Y")
        else:
            v = rule_fn(mm)
        cls[t] = bool(v and c391.live_code(t))
    return cls, meta


def stats(ded):
    wR = J.m_weighted_R(ded)
    est, lo, hi = J.cluster_bootstrap([t["Rnet"] for t in ded], [t["entry_ci"] for t in ded],
                                      weights=[t["m"] for t in ded], seed=SEED_BOOT, q=0.025, order="first")
    A = [t for t in ded if PERIOD_A[0] <= t["entry_date"] <= PERIOD_A[1]]
    ex25 = [t for t in ded if not t["entry_date"].startswith("2025")]
    k = int(np.ceil(0.01 * len(ded)))
    srt = sorted(ded, key=lambda x: -x["Rnet"])
    return {"n": len(ded), "wR": wR, "ci95_lo": lo, "ci95_hi": hi, "wR_A": J.m_weighted_R(A),
            "wR_ex2025": J.m_weighted_R(ex25), "wR_ex_top1pct": J.m_weighted_R(srt[k:])}


def main():
    t0 = time.time()
    c391 = load_c391()
    PN.check_archive(C.ETF_ARCHIVE, C.ETF_PARQUET_SHA)
    cls, meta = classify(c391)
    listed = {t: m["listed_at_end"] for t, m in meta.items()}
    out = {"inputs": {"cycle391_module": BASE_SHA, "c391b_results.json": PN.sha256(REF_JSON),
                      "U1_class_total": int(sum(cls.values()))}}

    # ── 공용 층: 데이터 · 지표 · 시장 유닛 ──
    full = PN.load_archive(C.ETF_ARCHIVE)
    cal = pd.DatetimeIndex(sorted(full.bas_dd.unique()))
    need = {t for t, v in cls.items() if v} | {MU.SOURCE_TICKER}
    st = PN.build_store(full, nontrade="drop", junction_rescale=False, cal=cal, tickers=need)
    data = {t: EB.ticker_arrays(b) for t, b in st.bars.items()}
    k200 = data[MU.SOURCE_TICKER]
    mu = np.full(len(cal), np.nan)
    mu[k200["ci"]] = MU.m_at_bars(k200["c"])
    last_ci = len(cal) - 1

    # ── 원본(cycle391 그대로) ──
    df = pd.concat([pd.read_parquet(p) for p in c391.PARQUETS], ignore_index=True)
    rcal = np.array(sorted(df["bas_dd"].unique()))
    cal_map = pd.Series(np.arange(len(rcal)), index=pd.DatetimeIndex(rcal))
    rdata = {}
    for t, g in df[df["ticker"].isin(need)].groupby("ticker"):
        d = c391.build_ticker_cal(g, lambda v: cal_map.loc[pd.DatetimeIndex(v)].to_numpy(), None)
        if d is not None:
            rdata[t] = d
    rmu = c391.market_unit_series(rdata["069500"], len(rcal))
    out["market_unit"] = {"equal": bool(np.array_equal(mu, rmu, equal_nan=True)),
                          "n_diff": int(np.sum(~((mu == rmu) | (np.isnan(mu) & np.isnan(rmu)))))}
    print("[gate391b] market unit", out["market_unit"], flush=True)

    dcls = {t: d for t, d in data.items() if cls.get(t)}
    rdcls = {t: d for t, d in rdata.items() if cls.get(t)}
    mine = EB.gen_trades(dcls, cls, mu, cal, listed, last_ci)
    ref = c391.gen_trades("donchian", rdcls, cls, rmu, rcal, meta, last_ci)
    keys = [k for k in ref[0] if k in mine[0]] if ref and mine else []
    neq = [i for i, (a, b) in enumerate(zip(mine, ref))
           if any(not ((a[k] == b[k]) or (a[k] != a[k] and b[k] != b[k])) for k in keys)]
    out["raw_trades"] = {"n_mine": len(mine), "n_ref": len(ref), "fields_compared": keys,
                         "n_field_mismatch": len(neq), "first_mismatch": neq[:3]}
    if neq:
        i = neq[0]
        out["raw_trades"]["example"] = {k: (mine[i][k], ref[i][k]) for k in keys if mine[i][k] != ref[i][k]}
    print("[gate391b] raw trades", {k: v for k, v in out["raw_trades"].items() if k != "fields_compared"},
          flush=True)

    # ── 판정판 파이프라인(공용 judge) ──
    allt = [t for t in mine if t["entry_date"] >= FULL_START and t["m"] is not None]
    base = [t for t in allt if EB.full_u(t)]
    buy = [t for t in base if t["m"] > 0]
    tick_list = sorted(data)
    col = {t: i for i, t in enumerate(tick_list)}
    ret = np.full((len(cal), len(tick_list)), np.nan)
    for t, d in data.items():
        cc = np.full(len(cal), np.nan)
        cc[d["ci"]] = d["c"]
        ret[1:, col[t]] = cc[1:] / cc[:-1] - 1
    ded = EB.dedup(buy, EB.Corr(ret, col))
    s = stats(ded)
    yrs = (pd.Timestamp(FULL_END) - pd.Timestamp(FULL_START)).days / 365.25
    sl = J.r_sleeve(ded, SEED_SLEEVE, years=yrs)
    refj = json.load(open(REF_JSON))["bundles"]["B"]
    rs, rl = refj["stats"], refj["sleeve"]
    cmp = {"n": (s["n"], rs["n"]), "wR": (s["wR"], rs["wR"]), "ci95_lo": (s["ci95_lo"], rs["ci95"][0]),
           "ci95_hi": (s["ci95_hi"], rs["ci95"][1]), "wR_A": (s["wR_A"], rs["wR_A"]),
           "wR_ex2025": (s["wR_ex2025"], rs["wR_ex2025"]), "wR_ex_top1pct": (s["wR_ex_top1pct"], rs["wR_ex_top1pct"]),
           "ann_mean": (sl["ann_mean"], rl["ann_mean"]), "mdd_median": (sl["mdd_median"], rl["mdd_median"]),
           "ret_over_mdd": (sl["ret_over_mdd"], rl["ret_over_mdd"])}
    out["judged_B"] = {k: {"mine": a, "ref": b, "absdiff": abs(a - b)} for k, (a, b) in cmp.items()}
    out["judged_B_max_absdiff"] = max(abs(a - b) for a, b in cmp.values())
    rt = refj["trades"]
    my_t = [{k: t[k] for k in rt[0]} for t in ded]
    out["judged_trade_list_equal"] = my_t == rt
    out["counts"] = {"signals_full_universe": len(base), "signals_m_pos": len(buy), "dedup_m_pos": len(ded),
                     "ref": [refj["signals_full_universe"], refj["signals_m_pos"], refj["dedup_m_pos"]]}
    print("[gate391b] judged B", json.dumps({k: [v["mine"], v["ref"]] for k, v in out["judged_B"].items()}),
          "max|diff|", out["judged_B_max_absdiff"], "trade list equal", out["judged_trade_list_equal"],
          out["counts"], flush=True)

    # ── 보고판(관문 아님): 같은 거래를 P5 불리 경로로 — 이 청산 규칙은 봉 안에서 선을 올리지 않으므로 같아야 한다 ──
    mine_adv = EB.gen_trades(dcls, cls, mu, cal, listed, last_ci, mode="adverse")
    out["adverse_path_identical"] = [(a["exit_ci"], a["exit_px"]) for a in mine_adv] == \
        [(a["exit_ci"], a["exit_px"]) for a in mine]
    out["elapsed_s"] = time.time() - t0
    with open(os.path.join(C.SCRATCH, "gate_c391b.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print("[gate391b] adverse identical", out["adverse_path_identical"], f"{out['elapsed_s']:.0f}s")


if __name__ == "__main__":
    main()
