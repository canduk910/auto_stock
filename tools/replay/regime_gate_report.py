#!/usr/bin/env python3
"""장세 문 연구 — 표·부트스트랩·성적표 입력 (사전 등록 §1.5 · §2 · §3).

입력 = ``regime_gate.py select/apply`` 산출(``select_*.json`` · 스크래치 ``regime_gate/apply_*.pkl``) +
``regime_gate_alloc`` (여기서 바로 돈다 — 수 초). 지표 = 성적표 ``compute_metrics`` 스냅샷.

    python tools/replay/regime_gate_report.py <out_dir> <scoreboard_snapshot.py>
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pickle
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_HERE), os.path.dirname(os.path.dirname(_HERE))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import regime_gate as RG  # noqa: E402
from replay import regime_gate_alloc as RA  # noqa: E402

SNAP_SHA = "54baf7c5c8521e765efbf28413ec868e44a1bd39014fae9a0e93fe8debd5b178"
SID_NAMES = {"kojiro": "kojiro", "donchian": "donchian_swing", "vcp": "vcp_breakout", "bfb": "bull_flag_breakout",
             "vb": "volatility_breakout", "etf_trend": "etf_trend", "mr_ou": "평균회귀 OU z"}


def load_snapshot(path: str):
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if h != SNAP_SHA:
        raise SystemExit(f"성적표 스냅샷 sha 불일치 {h}")
    spec = importlib.util.spec_from_file_location("sb_snap", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sb_snap"] = mod                      # dataclass 가 모듈을 찾는다
    spec.loader.exec_module(mod)
    return mod


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()
                if not str(k).startswith("_") and k not in ("value", "value_tax")}
    if isinstance(o, pd.DatetimeIndex):
        return [str(o[0].date()), str(o[-1].date())]
    if isinstance(o, (list, tuple)):
        return [_clean(x) for x in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    return o


def month_ret(SB, dates, v) -> pd.Series:
    me = SB.month_points(pd.DatetimeIndex(dates), np.asarray(v, float))
    r = me.pct_change().dropna()
    r.index = r.index.to_period("M")
    return r


def seed_mean_monthly(SB, rec, start) -> pd.Series:
    d0 = pd.Timestamp(rec["dates"][0]) - pd.Timedelta(days=1)
    dates = pd.DatetimeIndex([d0]).append(pd.DatetimeIndex(rec["dates"]))
    rs = [month_ret(SB, dates, np.r_[start, e]) for _, e in rec["runs"]]
    return pd.concat(rs, axis=1).mean(axis=1)


def rep_curve(rec, start):
    """대표 씨앗 = 최종 평가액 하위 중앙(성적표와 같은 규칙)."""
    finals = np.array([float(e[-1]) for _, e in rec["runs"]])
    k = int(np.argsort(finals, kind="stable")[(len(finals) - 1) // 2])
    d0 = pd.Timestamp(rec["dates"][0]) - pd.Timedelta(days=1)
    dates = pd.DatetimeIndex([d0]).append(pd.DatetimeIndex(rec["dates"]))
    return dates, np.r_[start, np.asarray(rec["runs"][k][1], float)], int(rec["runs"][k][0])


def seed_med(rec, start):
    d = pd.DatetimeIndex(rec["dates"])
    return RG.seed_summary(rec["runs"], start, d)


def strategies(SB, out_dir, rf, bench, entries):
    res = {}
    for sid in RG.ORDER:
        sp = os.path.join(out_dir, f"select_{sid}.json")
        ap = os.path.join(RG.SCRATCH_ROOT, "regime_gate", f"apply_{sid}.pkl")
        if not (os.path.exists(sp) and os.path.exists(ap)):
            print(f"[report] {sid} 산출 없음 — 건너뜀", flush=True)
            continue
        sel = json.load(open(sp))
        ap = pickle.load(open(ap, "rb"))
        start = ap["start"]
        chosen = tuple(ap["chosen"])
        none_row = next(r for r in sel["rows"] if not r["rest"])
        rows = {}
        for wn in ("T", "V", "H", "FULL"):
            b, g = ap["res"][(wn, "base")], ap["res"][(wn, "gate")]
            sb, sg = seed_med(b, start), seed_med(g, start)
            row = {"base": {k: sb[k] for k in ("cagr_median", "mdd_median", "mar_median")},
                   "gate": {k: sg[k] for k in ("cagr_median", "mdd_median", "mar_median")},
                   "rest_ratio": g["rest_ratio"], "signals_kept": g["n_kept"], "signals_all": b["n_kept"]}
            if chosen and wn in ("V", "H", "T"):
                mb, mg = seed_mean_monthly(SB, b, start), seed_mean_monthly(SB, g, start)
                cash = rf.reindex(rf.index.union(pd.DatetimeIndex(b["dates"]))).ffill()
                cm = cash.groupby(cash.index.to_period("M")).last().pct_change().reindex(mb.index).fillna(0.0)
                row["boot"] = RA.boot_diff(mg.to_numpy(), mb.to_numpy(), cm.to_numpy())
            rows[wn] = row
        # 30년 이어 달린 곡선 — 대표 씨앗
        full = {}
        for tag in ("base", "gate"):
            dates, v, seed = rep_curve(ap["res"][("FULL", tag)], start)
            mt = SB.compute_metrics(dates, v, rf, bench)
            full[tag] = {"rep_seed": seed, "metrics": mt}
            if tag == "gate" and chosen:
                entries.append(entry(SB, f"RG_{sid}", f"{SID_NAMES[sid]} · 장세 쉼({RG.set_name(chosen)})",
                                     f"진입 세션 라벨이 {RG.set_name(chosen)} 이면 신규 진입 안 함(보유분은 원래 청산). "
                                     f"집합은 1997~2012 학습 MAR 최대로 고름", "strategy_gate", dates, v, mt,
                                     source=f"regime_gate.apply {sid}"))
        lab = judge(rows, chosen)
        res[sid] = {"name": SID_NAMES[sid], "chosen": list(chosen), "chosen_name": RG.set_name(chosen),
                    "T_mar_chosen": sel["chosen"]["mar"], "T_mar_none": none_row["mar"],
                    "n_candidates": sel["n_candidates"], "skipped_rest_cap": len(sel["skipped_rest_cap"]),
                    "top5": sel["rows"][:5], "windows": rows, "full": full, "label": lab}
        print(f"[report] {sid} {RG.set_name(chosen)} → {lab}", flush=True)
    return res


def judge(rows, chosen) -> str:
    if not chosen:
        return "학습에서도 쉬는 게 낫지 않았다"
    bv, h = rows["V"]["boot"]["mar"], rows["H"]["boot"]["mar"]
    if bv["p05"] > 0 and h["d"] > 0:
        return "쉬는 게 낫다"
    if bv["p95"] < 0:
        return "쉬면 해롭다"
    return "가려지지 않음"


def entry(SB, id_, name, desc, group, dates, v, mt, *, source="", **opt) -> dict:
    """성적표 외부 항목 형식(scoreboard.md §8) — 일별 곡선 ``curve{dates, cum}``(첫 값 = 시작점 1.0)."""
    d = pd.DatetimeIndex(dates)
    v = np.asarray(v, float)
    return {"id": id_, "name": name, "desc": desc, "group": group, "status": "참고",
            "status_ref": "_workspace/analysis/regime_gate_20261006/result.md", "source": source,
            "period": [str(d[0].date()), str(d[-1].date())],
            "curve": {"dates": [str(x.date()) for x in d], "cum": [float(x / v[0]) for x in v]},
            "yearly": {y: x["ret"] for y, x in mt["yearly"].items()}, **opt}


def alloc(SB, rf, bench, entries):
    m = RA.load_market()
    out = {}
    RA.part1(m, out)
    RA.part2(m, out)
    p1 = out["part1"]
    for base, r in p1.items():
        for wn, w in r["windows"].items():
            for tag in ("base", "gate"):
                d, v = w[f"_curve_{tag}"]
                w[f"sb_{tag}"] = SB.compute_metrics(pd.DatetimeIndex(d), np.asarray(v), rf, bench)
            if wn == "FULL" and r["chosen"]:
                d, v = w["_curve_gate"]
                entries.append(entry(SB, f"RG_{base}", f"{r['name']} · 장세 현금({r['chosen_name']})",
                                     f"상태가 {r['chosen_name']} 이면 원화 현금 100%, 아니면 기본 비중. 집합은 1997~2012 학습 "
                                     f"MAR 최대로 고름", "global_gate", pd.DatetimeIndex(d), np.asarray(v),
                                     w["sb_gate"], source=f"regime_gate_alloc.part1 {base}",
                                     turnover_yr=w["gate"]["turnover_yr"], cost_yr=w["gate"]["cost_yr"],
                                     after_tax_cagr=w["gate"]["after_tax_cagr"]))
        r["judge"] = (judge({"V": {"boot": r["windows"]["V"]["boot"]}, "H": {"boot": r["windows"]["H"]["boot"]}},
                            tuple(r["chosen"])))
        print(f"[report] alloc {base} {r['chosen_name']} → {r['judge']}", flush=True)
    p2 = out["part2"]
    dates = p2["dates"]
    for key, r in p2["runs"].items():
        r["sb"] = SB.compute_metrics(dates, r["value"], rf, bench)
        r["sb_tax"] = SB.compute_metrics(dates, r["value_tax"], rf, bench)
        if key[:2] in ("V1", "V2", "V3"):
            entries.append(entry(SB, f"RG_{key}", f"60/40 변형 {key}", r["desc"], "global_gate", dates, r["value"],
                                 r["sb"], source="regime_gate_alloc.part2", turnover_yr=r["metrics"]["turnover_yr"],
                                 cost_yr=r["metrics"]["cost_yr"], after_tax_cagr=r["metrics"]["after_tax_cagr"],
                                 tax_note="KOSPI200 2배 차익 비과세 가정(도입 전 확인) · 미국채·S&P500 2배 몫 차익 15.4%"))
    return out


def main():
    out_dir, snap = sys.argv[1], sys.argv[2]
    SB = load_snapshot(snap)
    df = pd.read_parquet(RA.PARQUET)
    rf = pd.Series(np.cumprod(1 + df["CASH_ret"].to_numpy(float)), index=pd.DatetimeIndex(df.index))
    m = RA.load_market()
    a, b = RA.win_ab(m, RG.FULL)
    k = np.cumprod(1 + (m.ret[:, 0] - m.fee[:, 0]))          # K200 보유(보수 뒤) 지수 — 같은 창 비교 기준
    bench = pd.Series(k, index=m.dates)
    entries: list = []
    res = {"strategies": strategies(SB, out_dir, rf, bench, entries)}
    res["alloc"] = alloc(SB, rf, bench, entries)
    res["meta"] = {"scoreboard_snapshot_sha256": SNAP_SHA, "label_counts_30y": RG.label_series()
                   .loc[RG.FULL[0]:RG.FULL[1]].value_counts().to_dict()}
    with open(os.path.join(out_dir, "result.json"), "w") as fh:
        json.dump(_clean(res), fh, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "scoreboard_entries.json"), "w") as fh:
        json.dump(_clean({"source": "regime_gate 2026-10-06 · tools/replay/regime_gate*.py "
                                    "(_workspace/analysis/regime_gate_20261006/result.md)",
                          "entries": entries}), fh, ensure_ascii=False, indent=1)
    with open(os.path.join(RG.SCRATCH_ROOT, "regime_gate", "report_full.pkl"), "wb") as fh:
        pickle.dump(res, fh)
    print("[report] done", flush=True)


if __name__ == "__main__":
    main()
