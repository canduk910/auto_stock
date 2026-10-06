#!/usr/bin/env python3
"""(라) 장세 문 — 지표 · 판정 · 균등 병행 포트폴리오 · 산출(사전 등록 §4 · §5).

    python tools/replay/ra_gate_report.py <data.pkl> <runs_dir> <out_dir>
"""
from __future__ import annotations

import json
import os
import pickle
import sys
from collections import Counter

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from replay import ra_gate_core as G  # noqa: E402
from replay import ra_gate_run as RR  # noqa: E402
from replay import regime_v2 as RV  # noqa: E402
from replay import sb_addons_core as S  # noqa: E402
from replay import sb_addons_report as SR  # noqa: E402
from replay import scoreboard as SBD  # noqa: E402
from replay import sector_rs_report as SRR  # noqa: E402

SIDS = ("kojiro", "donchian", "vcp", "bfb", "vb", "etf_trend", "mr_band", "mr_fkeep")
PES = {"kojiro", "vb"}
NAMES = SR.NAMES
REF = "_workspace/analysis/ra_gate_20261006/result.md"
WIN = {"T": ("1997-01-02", "2012-12-28"), "V": ("2013-01-02", "2020-12-30"), "H": ("2021-01-04", "2026-10-02")}
WNAME = {"T": "학습", "V": "검증", "H": "보류"}
VN = {"G0": "원판", "G0N": "시장 유닛 끔", "G1": "(라) 문", "G2": "(라) 문 + 시장 유닛", "G3": "시장 유닛만",
      "G3S": "모든 전략 시장 유닛", "G2S": "(라) 문 + 모든 전략 시장 유닛"}
PORT_VARIANTS = ("G0", "G0N", "G1", "G2", "G3S", "G2S")
# 판정 짝(대상, 기준) — 사전 등록 §4-5
PAIRS_TURTLE = (("G1", "G0"), ("G2", "G0"), ("G0N", "G0"), ("G1", "G0N"))
PAIRS_OTHER = (("G1", "G0"), ("G3S", "G0"), ("G2S", "G0"), ("G2S", "G3S"))
PAIRS_PORT = (("G1", "G0"), ("G2", "G0"), ("G3S", "G0"), ("G2S", "G0"), ("G2S", "G3S"), ("G0N", "G0"),
              ("G1", "G0N"))


def actual(sid: str, variant: str) -> str:
    """판 → 실제로 돈 곡선(등가 판은 같은 곡선 — 사전 등록 §3 표)."""
    if sid in G.TURTLE:
        return {"G3": "G0", "G3S": "G0", "G2S": "G2"}.get(variant, variant)
    return {"G0N": "G0", "G2": "G1", "G3": "G0"}.get(variant, variant)


def load_run(runs_dir, sid, ver, variant):
    path = os.path.join(runs_dir, f"{sid}__{ver}__{actual(sid, variant)}.pkl")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        o = pickle.load(fh)
    o["dates"] = pd.DatetimeIndex(pd.to_datetime(o["dates"]))
    return o


def win_rows(rows, w):
    a, b = WIN[w]
    return [r for r in rows if a <= r[0] <= b]


def monthly(o) -> pd.Series:
    """씨앗 16 월 수익 평균(30년 이어 달린 계좌의 월말 값)."""
    start = float(o["meta"]["start_equity"])
    d = pd.DatetimeIndex(pd.to_datetime(o["all_dates"]))
    dd = pd.DatetimeIndex([d[0] - pd.Timedelta(days=1)]).append(d)
    return pd.concat([RV._month_ret(SBD, dd, np.r_[start, e]) for _, e in o["all_runs"]], axis=1).mean(axis=1)


def curve_monthly(dates, v) -> pd.Series:
    return RV._month_ret(SBD, pd.DatetimeIndex(dates), np.asarray(v, float))


def months_of(w) -> tuple:
    a, b = WIN[w]
    return pd.Period(a[:7], "M"), pd.Period(b[:7], "M")


def boot_pair(mc: pd.Series, mb: pd.Series, cash_m: pd.Series, w: str) -> dict:
    a, b = months_of(w)
    idx = mc.index.intersection(mb.index)
    idx = idx[(idx >= a) & (idx <= b)]
    rc, rb = mc.reindex(idx).to_numpy(float), mb.reindex(idx).to_numpy(float)
    cm = cash_m.reindex(idx).fillna(0.0).to_numpy(float)
    out = RV.boot(rc, rb, cm)
    out["n_months"] = int(len(idx))
    return out


def judge(bv, bh, tradeless: bool) -> str:
    if tradeless:
        return "판정 불가(매매 없음)"
    if bv["mar"]["p05"] > 0:
        return "우위" if bh["mar"]["d"] > 0 else "검증만"
    if bv["mar"]["p95"] < 0:
        return "원판이 낫다"
    return "가려지지 않음"


def mar_of(p) -> float:
    if p is None:
        return float("nan")
    return p["cagr"] / abs(p["mdd"]) if p["mdd"] < 0 else float("nan")


def dropped_window(base, var, w=None) -> dict:
    if w is None:
        return SRR.dropped_stats(base, var)
    a, b = WIN[w]
    bs = {"seeds": [{**s, "trades": [r for r in s["trades"] if a <= r[0] <= b]} for s in base["seeds"]],
          "rep": base["rep"]}
    vs = {"seeds": [{**s, "dropped": [r for r in s["dropped"] if a <= r[0] <= b]} for s in var["seeds"]],
          "rep": var["rep"]}
    return SRR.dropped_stats(bs, vs)


def build(data_pkl, runs_dir, out_dir):
    D = pickle.load(open(data_pkl, "rb"))
    cell_of, _ = RR.lookups(D)
    C = SR.Ctx()
    rf = C.rf
    cash_m = rf.groupby(rf.index.to_period("M")).last().pct_change()
    res = {"generated_kst": pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m-%d %H:%M"), "strategies": {},
           "check_scoreboard": {}, "m_check": {}, "portfolio": {}, "cells": {}}
    res["cells"] = {"first_valid": D["first_valid"], "regv2_key_diff": D["check"].get("regv2_key_diff"),
                    "share": {w: G.cell_share(D["dates"], cell_of, *WIN[w]) for w in WIN},
                    "share_full": G.cell_share(D["dates"], cell_of, WIN["T"][0], WIN["H"][1])}
    entries, curves_for, books = [], {}, {}
    for sid in SIDS:
        row = {"turtle": sid in G.TURTLE, "versions": {}}
        for ver in (("opt", "pes") if sid in PES else ("opt",)):
            runs = {v: load_run(runs_dir, sid, ver, v) for v in RR.variants_of(sid)}
            if any(o is None for o in runs.values()):
                print(f"[rag_report] {sid} {ver} 판 빠짐 — 건너뜀 {[v for v, o in runs.items() if o is None]}", flush=True)
                continue
            if ver == "opt":
                res["check_scoreboard"][sid] = runs["G0"]["meta"].get("check_scoreboard_max_abs")
                if sid in G.TURTLE:
                    ss = runs["G0"]["seeds"]
                    res["m_check"][sid] = {"checked": int(sum(s["m_checked"] for s in ss)),
                                           "mismatch": int(sum(s["m_mismatch"] for s in ss)),
                                           "examples": ss[runs["G0"]["rep"]]["m_mismatch_ex"][:5]}
            vr, mon = {}, {}
            for v, o in runs.items():
                m = C.metrics(o["dates"], o["equity"])
                tr = o["seeds"][o["rep"]]["trades"]
                rec = {"metrics": m, "abs_pass": SR.absolute_pass(m), "trades": SRR.trade_stats(tr),
                       "trades_win": {w: SRR.trade_stats(win_rows(tr, w)) for w in WIN},
                       "mar_win": {w: mar_of(m["periods"].get(WNAME[w])) for w in WIN},
                       "seed_cagr_median": o["meta"]["seed_cagr_median"], "seed_mdd_median": o["meta"]["seed_mdd_median"],
                       "dropped_rep": len(o["seeds"][o["rep"]]["dropped"]),
                       "dropped_mu_rep": len(o["seeds"][o["rep"]]["dropped_mu"]),
                       "dropped_median": float(np.median([len(s["dropped"]) for s in o["seeds"]]))}
                if v == "G0":
                    by = {}
                    for w in WIN:
                        rows = win_rows(tr, w)
                        by[w] = {c: SRR.trade_stats([r for r in rows if cell_of(r[0]) == c]) for c in G.CELLS}
                    rec["by_cell"] = by
                    rec["by_cell_all"] = {c: SRR.trade_stats([r for r in tr if cell_of(r[0]) == c]) for c in G.CELLS}
                vr[v] = rec
                mon[v] = monthly(o)
                books[(sid, ver, v)] = (o["dates"], o["equity"])
            pairs = {}
            for tgt, ref in (PAIRS_TURTLE if sid in G.TURTLE else PAIRS_OTHER):
                b = {w: boot_pair(mon[tgt], mon[ref], cash_m, w) for w in ("V", "H")}
                tl = any(vr[x]["trades_win"][w]["n"] == 0 for x in (tgt, ref) for w in ("V", "H"))
                mt, mr_ = vr[tgt]["metrics"], vr[ref]["metrics"]
                pairs[f"{tgt}_vs_{ref}"] = {
                    "boot": b, "judge": judge(b["V"], b["H"], tl), "tradeless": tl,
                    "d_cagr": mt["cagr"] - mr_["cagr"], "d_mdd": mt["mdd"] - mr_["mdd"],
                    "d_mar_full": (mt["mar"] if mt.get("mar") is not None else float("nan"))
                    - (mr_["mar"] if mr_.get("mar") is not None else float("nan")),
                    "d_cagr_win": {w: (mt["periods"][WNAME[w]]["cagr"] - mr_["periods"][WNAME[w]]["cagr"])
                                   if WNAME[w] in mt["periods"] and WNAME[w] in mr_["periods"] else None for w in WIN},
                    "d_trade_mean_win": {w: vr[tgt]["trades_win"][w]["mean"] - vr[ref]["trades_win"][w]["mean"]
                                         for w in WIN}}
            # 버린 신호 — 같은 시장 유닛 설정의 원판 거래와 짝(§4-6)
            drops = {}
            for v in ("G1", "G2") if sid in G.TURTLE else ("G1", "G2S"):
                base = runs["G0N" if (sid in G.TURTLE and v == "G1") else ("G3S" if v == "G2S" else "G0")]
                drops[v] = {"all": dropped_window(base, runs[v]), **{w: dropped_window(base, runs[v], w) for w in WIN}}
            row["versions"][ver] = {"variants": vr, "pairs": pairs, "dropped": drops}
            # 성적표 항목
            show = ("G0N", "G1", "G2") if sid in G.TURTLE else ("G1", "G3S", "G2S")
            for v in show:
                eid = f"RAG_{sid.upper()}_{v}" + ("_PES" if ver == "pes" else "")
                r = vr[v]
                pk = pairs.get(f"{v}_vs_G0")
                curves_for[eid] = books[(sid, ver, v)]
                entries.append({
                    "id": eid,
                    "name": f"{NAMES[sid]} · {VN[v]}" + (" (비관 체결)" if ver == "pes" else ""),
                    "desc": _desc(sid, v, r),
                    "status": "참고",
                    "status_ref": f"{REF} §2" + (f" · 판정 {pk['judge']}" if pk else ""),
                    "group_title": "(라) 장세 문 — 전략별 단독 계좌(거래 단위 재시뮬레이션)",
                    "source": f"ra_gate_run.py · {sid} · {ver} · {v} · 대표 씨앗 = 하위 중앙"})
        if row["versions"]:
            res["strategies"][sid] = row
            print(f"[rag_report] {sid} " + " · ".join(f"{k} {p['judge']}" for k, p in
                                                    row["versions"]["opt"]["pairs"].items()), flush=True)

    # ── 균등 병행 포트폴리오 ──
    order = list(SIDS)
    rule = lambda r, av: S.weights_equal(av)  # noqa: E731
    port = {}
    for ver in ("opt", "pes"):
        for v in PORT_VARIANTS:
            comp = {}
            for sid in SIDS:
                vv = ver if sid in PES else "opt"
                k = (sid, vv, actual(sid, v))
                if k not in books:
                    comp = None
                    break
                comp[sid] = books[k]
            if comp is None:
                continue
            rr = S.rotation(comp, order, rule)
            port[(ver, v)] = (rr["dates"], rr["value"])
    pm = {}
    for (ver, v), (d, val) in port.items():
        m = C.metrics(d, val)
        pm[(ver, v)] = curve_monthly(d, val)
        res["portfolio"][f"{ver}__{v}"] = {"metrics": m, "abs_pass": SR.absolute_pass(m),
                                           "mar_win": {w: mar_of(m["periods"].get(WNAME[w])) for w in WIN}}
    for ver in ("opt", "pes"):
        for tgt, ref in PAIRS_PORT:
            if (ver, tgt) not in pm or (ver, ref) not in pm:
                continue
            b = {w: boot_pair(pm[(ver, tgt)], pm[(ver, ref)], cash_m, w) for w in ("V", "H")}
            mt = res["portfolio"][f"{ver}__{tgt}"]["metrics"]
            mr_ = res["portfolio"][f"{ver}__{ref}"]["metrics"]
            res["portfolio"].setdefault(f"{ver}__pairs", {})[f"{tgt}_vs_{ref}"] = {
                "boot": b, "judge": judge(b["V"], b["H"], False), "d_cagr": mt["cagr"] - mr_["cagr"],
                "d_mdd": mt["mdd"] - mr_["mdd"]}
    for (ver, v), (d, val) in port.items():
        eid = f"RAG_PORT_{v}" + ("_PES" if ver == "pes" else "")
        curves_for[eid] = (d, val)
        pk = res["portfolio"].get(f"{ver}__pairs", {}).get(f"{v}_vs_G0")
        entries.append({
            "id": eid,
            "name": f"8전략 균등 병행 · {VN[v]}" + (" (비관 체결)" if ver == "pes" else ""),
            "desc": ("kojiro·donchian·vcp·bfb·vb·etf_trend·평균회귀 2판 단독 계좌 곡선 균등 · 분기말 되돌림 · 회전 비용 0.19%/편도 · "
                     f"구성 = 각 전략의 「{VN[v]}」 곡선(해당 판이 없으면 등가 곡선)"),
            "status": "참고", "status_ref": f"{REF} §4" + (f" · 판정 {pk['judge']}" if pk else ""),
            "group_title": "(라) 장세 문 — 8전략 균등 병행(곡선 근사)",
            "source": "ra_gate_report.py · sb_addons_core.rotation(균등)"})

    for e in entries:
        d, v = curves_for[e["id"]]
        d = pd.DatetimeIndex(d)
        v = np.asarray(v, float)
        e["period"] = [str(d[0].date()), str(d[-1].date())]
        e["curve"] = {"dates": [str(x.date()) for x in d], "cum": [float(f"{x / v[0]:.7g}") for x in v]}
    doc = {"source": "ra_gate 2026-10-06 · tools/replay/ra_gate_*.py · 사전 등록 "
                     "_workspace/analysis/ra_gate_20261006/prereg.frozen.md", "entries": entries}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "scoreboard_entries.json"), "w") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(out_dir, "result.json"), "w") as fh:
        json.dump(SBD._clean(res), fh, ensure_ascii=False, indent=1)
    print(f"[rag_report] 항목 {len(entries)} · {out_dir}", flush=True)
    return res, entries


def _desc(sid, v, r) -> str:
    if v == "G0N":
        return "원판에서 시장 유닛만 끈 참고판 — 모든 신호 m = 1(랏 그대로 · m = 0 날도 진입)"
    base = ("120일선 20일 기울기 오름·시장 폭 > 0.3 또는 기울기 내림·폭 ≤ 0.3 인 날(D−1 종가)에만 신규 매수 · 나머지 두 칸은 그날 "
            "신규 매수 신호를 버림 · 보유분 청산 그대로")
    mu = {"G1": " · 시장 유닛 없음" if sid in G.TURTLE else " · 원판 그대로(이 전략은 운영상 시장 유닛 없음)",
          "G2": " · 허용 칸에서 운영 시장 유닛(1·0.75·0.5·0배) 그대로",
          "G3S": "", "G2S": " · 허용 칸에서 시장 유닛(1·0.75·0.5·0배)을 랏에 곱함(운영상 이 전략엔 없음 — 참고)"}[v]
    if v == "G3S":
        return ("관문 없이 시장 유닛(1·0.75·0.5·0배, m = 0 이면 그날 신호 버림)만 랏에 곱한 참고판 — 운영상 이 전략엔 시장 유닛 없음")
    return base + mu + f" · 버린 신호(대표 씨앗) {r['dropped_rep']:,}"


# ═════════════════════════════════ 문서 ═════════════════════════════════

_p, _f, _row_metrics, HDR = SR._p, SR._f, SR._row_metrics, SR.HDR
VERN = {"opt": "낙관", "pes": "비관"}


def _ts(t):
    if not t or t["n"] == 0:
        return "0건"
    return f"{t['n']:,}건 · {_p(t['mean'], 2)} [{_p(t['lo90'], 2)}]"


def _bt(b):
    m = b["mar"]
    return f"{_f(m['d'], 3)} [{_f(m['p05'], 3)}, {_f(m['p95'], 3)}]"


def write_md(res, out_dir, head_path):
    L = []
    a = L.append
    if head_path and os.path.exists(head_path):
        a(open(head_path, encoding="utf-8").read().rstrip())
        a("")
    S_ = res["strategies"]
    a("## 2. 전략별 — 판정표")
    a("")
    a("판정 = 검증(2013–2020) MAR 차 90% 하한 > 0 ∧ 보류(2021–2026) MAR 차 > 0 → 우위 · 검증 하한만 > 0 → 검증만 · 검증 상한 < 0 → "
      "원판이 낫다 · 나머지 가려지지 않음. MAR 차 = 씨앗 16 월 수익 평균의 정상 블록 부트스트랩(평균 12개월 · 5,000회) — "
      "「점추정 [5%, 95%]」. 「판정 불가」 = 그 구간에 어느 한 판이 거래 0.")
    a("")
    a("| 전략 | 판 | 짝 | 30년 연복리 차 | 30년 낙폭 차 | 검증 MAR 차 [90%] | 보류 MAR 차 [90%] | 검증 · 보류 연복리 차 | 판정 |")
    a("|---|---|---|---|---|---|---|---|---|")
    for sid in SIDS:
        if sid not in S_:
            continue
        for ver, vv in S_[sid]["versions"].items():
            for k, p in vv["pairs"].items():
                t, r = k.split("_vs_")
                dc = " · ".join(_p(p["d_cagr_win"].get(w), 1) for w in ("V", "H"))
                a(f"| {NAMES[sid]} | {VERN[ver]} | {VN[t]} vs {VN[r]} | {_p(p['d_cagr'], 2)} | {_p(p['d_mdd'])} | "
                  f"{_bt(p['boot']['V'])} | {_bt(p['boot']['H'])} | {dc} | **{p['judge']}** |")
    a("")
    a("## 3. 전략별 — 계좌(대표 씨앗 · 30년 이어 달림)")
    a("")
    a("| 전략 | 판 | 곡선 " + HDR + " 검증 MAR | 보류 MAR |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for sid in SIDS:
        if sid not in S_:
            continue
        for ver, vv in S_[sid]["versions"].items():
            for v, r in vv["variants"].items():
                a(f"| {NAMES[sid]} | {VERN[ver]} | {VN[v]} | {_row_metrics(r['metrics'])} | {_f(r['mar_win']['V'])} | "
                  f"{_f(r['mar_win']['H'])} |")
    a("")
    a("### 3.1 거래당 평균 — 구간별(대표 씨앗 · 순수익 = 청산/진입 − 1 − 0.38% · 「[ ]」 = 진입월 블록 부트스트랩 90% 하한)")
    a("")
    a("| 전략 | 판 | 곡선 | 학습 | 검증 | 보류 | 30년 | 버린 신호(칸 · 대표) | 버린 신호(m=0 · 대표) |")
    a("|---|---|---|---|---|---|---|---|---|")
    for sid in SIDS:
        if sid not in S_:
            continue
        for ver, vv in S_[sid]["versions"].items():
            for v, r in vv["variants"].items():
                a(f"| {NAMES[sid]} | {VERN[ver]} | {VN[v]} | " + " | ".join(_ts(r["trades_win"][w]) for w in WIN)
                  + f" | {_ts(r['trades'])} | {r['dropped_rep']:,} | {r['dropped_mu_rep']:,} |")
    a("")
    a("### 3.2 버린 신호 — 원판에서는 어떤 거래였나")
    a("")
    a("씨앗 16개 각각에서, 관문 판이 중단 칸 때문에 버린 (날짜, 종목) 신호와 같은 원판 거래(시장 유닛 설정이 같은 쪽 — 터틀 G1 은 "
      "「시장 유닛 끔」, 비터틀 G2* 는 「모든 전략 시장 유닛」, 나머지는 원판)를 모았다. 「[ ]」 = 90% 구간.")
    a("")
    a("| 전략 | 판 | 곡선 | 구간 | 버린 신호(대표 · 씨앗 중앙) | 짝지어진 원판 거래 [90%] | 원판 전체 평균 | 판정 |")
    a("|---|---|---|---|---|---|---|---|")
    for sid in SIDS:
        if sid not in S_:
            continue
        for ver, vv in S_[sid]["versions"].items():
            for v, dd in vv["dropped"].items():
                for w in ("all", "V", "H"):
                    x = dd[w]
                    mt = x["matched"]
                    ms = (f"{mt['n']:,}건 · {_p(mt['mean'], 2)} [{_p(mt['lo90'], 2)} ~ {_p(mt['hi90'], 2)}]"
                          if mt["n"] else "0건")
                    wn = "30년" if w == "all" else WNAME[w]
                    a(f"| {NAMES[sid]} | {VERN[ver]} | {VN[v]} | {wn} | {x['dropped_rep']:,} · {x['dropped_median']:,.0f} | "
                      f"{ms} | {_p(x['base_all_mean'], 2)} | {x['verdict']} |")
    a("")
    # ── 포트폴리오 ──
    a("## 4. 8전략 균등 병행 포트폴리오(곡선 근사)")
    a("")
    a("8전략 단독 계좌 대표 곡선을 균등 비중으로 묶고 분기말마다 균등으로 되돌림(회전 비용 0.19%/편도 · etf_trend 는 2003 편입). "
      "각 판의 구성 곡선 = 그 판에 해당하는 전략 곡선(없으면 등가 — 터틀의 「시장 유닛만」 = 원판, 비터틀의 「(라) + 시장 유닛」 = (라) 문).")
    a("")
    a("| 판 | 곡선 " + HDR + " 검증 MAR | 보류 MAR |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    P = res["portfolio"]
    for ver in ("opt", "pes"):
        for v in PORT_VARIANTS:
            rec = P.get(f"{ver}__{v}")
            if rec:
                a(f"| {VERN[ver]} | {VN[v]} | {_row_metrics(rec['metrics'])} | {_f(rec['mar_win']['V'])} | "
                  f"{_f(rec['mar_win']['H'])} |")
    a("")
    a("| 판 | 짝 | 30년 연복리 차 | 30년 낙폭 차 | 검증 MAR 차 [90%] | 보류 MAR 차 [90%] | 판정 |")
    a("|---|---|---|---|---|---|---|")
    for ver in ("opt", "pes"):
        for k, p in P.get(f"{ver}__pairs", {}).items():
            t, r = k.split("_vs_")
            a(f"| {VERN[ver]} | {VN[t]} vs {VN[r]} | {_p(p['d_cagr'], 2)} | {_p(p['d_mdd'])} | {_bt(p['boot']['V'])} | "
              f"{_bt(p['boot']['H'])} | **{p['judge']}** |")
    a("")
    # ── 칸 ──
    c = res["cells"]
    a("## 5. 칸 — 날 비율 · 원판 거래 성적표")
    a("")
    a(f"칸 키 = regime_v2 저장 키와 다른 날 {c['regv2_key_diff']} · 두 조건이 모두 정의되는 첫날 {c['first_valid']}. 세션 D 의 칸 = "
      "판단 계열 달력에서 D 보다 앞선 마지막 종가의 키.")
    a("")
    a("| 구간 | 세션 | " + " | ".join(G.CELL_NAMES[k] for k in G.CELLS) + " | 허용 합 |")
    a("|---|---|" + "---|" * (len(G.CELLS) + 1))
    for w in WIN:
        sh = c["share"][w]
        a(f"| {WNAME[w]} | {sh['n']:,} | " + " | ".join(_p(sh[k], 1, False) for k in G.CELLS)
          + f" | {_p(sh['10'] + sh['01'], 1, False)} |")
    sh = c["share_full"]
    a(f"| 30년 | {sh['n']:,} | " + " | ".join(_p(sh[k], 1, False) for k in G.CELLS)
      + f" | {_p(sh['10'] + sh['01'], 1, False)} |")
    a("")
    a("원판(G0 · 낙관 · 대표 씨앗) 거래를 진입일 칸으로 나눈 거래당 평균 「건수 · 평균 [90% 하한]」:")
    a("")
    a("| 전략 | 구간 | " + " | ".join(G.CELL_NAMES[k] for k in G.CELLS) + " |")
    a("|---|---|" + "---|" * len(G.CELLS))
    for sid in SIDS:
        if sid not in S_:
            continue
        r = S_[sid]["versions"]["opt"]["variants"]["G0"]
        for w in WIN:
            a(f"| {NAMES[sid]} | {WNAME[w]} | " + " | ".join(_ts(r["by_cell"][w][k]) for k in G.CELLS) + " |")
        a(f"| {NAMES[sid]} | 30년 | " + " | ".join(_ts(r["by_cell_all"][k]) for k in G.CELLS) + " |")
    a("")
    a("## 6. 대조")
    a("")
    a("- 성적표 대조(관문 끈 낙관판 − 성적표 books, 최대 원): " + " · ".join(
        f"{k} {v:.4f}" for k, v in res["check_scoreboard"].items()))
    a("- 터틀 원판 신호의 m 과 날짜별 시장 유닛(운영 classify · D−1) 대조(씨앗 16 합): " + " · ".join(
        f"{k} {v['mismatch']:,}/{v['checked']:,}" for k, v in res["m_check"].items()))
    a("")
    tail = os.path.join(out_dir, "tail.md")
    if os.path.exists(tail):
        a(open(tail, encoding="utf-8").read().rstrip())
        a("")
    with open(os.path.join(out_dir, "result.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    res, _ = build(sys.argv[1], sys.argv[2], sys.argv[3])
    write_md(res, sys.argv[3], os.path.join(sys.argv[3], "head.md"))
