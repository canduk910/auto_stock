#!/usr/bin/env python3
"""섹터 RS 배제 — 지표 · 판정 · 균등 병행 포트폴리오 · 산출(사전 등록 §4 · §5 · §6).

    python tools/replay/sector_rs_report.py <data.pkl> <runs_dir> <out_dir>
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

from replay import judge as J  # noqa: E402
from replay import sb_addons_core as S  # noqa: E402
from replay import sb_addons_report as SR  # noqa: E402
from replay import scoreboard as SBD  # noqa: E402
from replay import sector_rs_core as R  # noqa: E402

SIDS = ("kojiro", "donchian", "vcp", "bfb", "vb", "etf_trend", "mr_band", "mr_fkeep")
PES = {"kojiro", "vb"}
NAMES = SR.NAMES
VARIANTS = ("R60", "R20", "R120", "IBD", "BF", "ETF")
VNAME = {"R60": "60일 RS", "R20": "20일 RS", "R120": "120일 RS", "IBD": "IBD 가중 RS(3·6·9·12개월 40/20/20/20)",
         "BF": "60일 RS · 첫 분류 소급(참고)", "ETF": "60일 RS · 섹터 ETF 실가격(보조판)"}
SUFFIX = {"R60": "", "R20": "_R20", "R120": "_R120", "IBD": "_IBD", "BF": "_BF", "ETF": "_ETF"}
PORT_VARIANTS = ("R60", "R20", "R120", "IBD", "ETF")
REF = "_workspace/analysis/sector_rs_20261006/result.md"


def load_run(runs_dir, sid, ver, variant):
    path = os.path.join(runs_dir, f"{sid}__{ver}__{variant}.pkl")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        o = pickle.load(fh)
    o["dates"] = pd.DatetimeIndex(pd.to_datetime(o["dates"]))
    return o


def trade_stats(rows) -> dict:
    if not rows:
        return {"n": 0, "mean": float("nan"), "lo90": float("nan"), "hi90": float("nan")}
    v = np.array([r for _, _, r in rows], float)
    cl = R.month_clusters([d for d, _, _ in rows])
    m, lo, hi = J.bootstrap_mean(v, cl, q=0.05)
    return {"n": int(len(v)), "mean": m, "lo90": lo, "hi90": hi}


def dropped_stats(base, var) -> dict:
    """씨앗마다 원판 거래 중 배제판이 버린 (날짜, 종목)과 같은 것 → 모아서 평균 · 90% 구간."""
    rows, allrows = [], []
    for sb, sv in zip(base["seeds"], var["seeds"]):
        keys = {(d, t) for d, t, _ in sv["dropped"]}
        allrows += sb["trades"]
        rows += [(d, t, r) for d, t, r in sb["trades"] if (d, t) in keys]
    st = trade_stats(rows)
    allm = float(np.mean([r for _, _, r in allrows])) if allrows else float("nan")
    if st["n"] == 0:
        verdict = "빠진 거래 없음"
    elif st["hi90"] < allm:
        verdict = "나쁜 거래를 뺐다"
    elif st["lo90"] > allm:
        verdict = "좋은 거래를 뺐다"
    else:
        verdict = "구분 못 함"
    return {"matched": st, "base_all_mean": allm, "base_all_n": len(allrows), "verdict": verdict,
            "dropped_rep": len(var["seeds"][var["rep"]]["dropped"]),
            "dropped_median": float(np.median([len(s["dropped"]) for s in var["seeds"]])),
            "dropped_by_bucket_rep": dict(Counter(b for _, _, b in var["seeds"][var["rep"]]["dropped"]))}


def coverage(run) -> dict:
    s = run["seeds"][run["rep"]]
    by = s["by_year"]
    out = {"seen": s["seen"], "unclassified": s["unclassified"],
           "share": s["unclassified"] / s["seen"] if s["seen"] else float("nan"), "periods": {}}
    for nm, a, b in S.PERIODS:
        ya, yb = int(a[:4]), int(b[:4])
        se = sum(v[0] for y, v in by.items() if ya <= int(y) <= yb)
        un = sum(v[1] for y, v in by.items() if ya <= int(y) <= yb)
        out["periods"][nm] = {"seen": se, "unclassified": un, "share": un / se if se else float("nan")}
    pre = [v for y, v in by.items() if int(y) <= 2001]
    out["to_2001"] = {"seen": sum(v[0] for v in pre), "unclassified": sum(v[1] for v in pre)}
    return out


def effect(dc, dm) -> str:
    return "도움" if (dc > 0 and dm > 0) else ("해" if (dc < 0 and dm <= 0) else "엇갈림")


def build(data_pkl, runs_dir, out_dir):
    D = pickle.load(open(data_pkl, "rb"))
    C = SR.Ctx()
    res = {"generated_kst": pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m-%d %H:%M"), "strategies": {},
           "check_scoreboard": {}, "portfolio": {}, "data": {}}
    entries, curves_for = [], {}
    # 자료 요약
    cal = D["cal"]
    st = D["snap_stats"]
    first = {m: next((c["date"] for c in st["cover"] if c[m] > 0), None) for m in ("STK", "KSQ")}
    res["data"] = {"n_snapshots": len(D["snaps"]), "first_snapshot": first, "unmapped_labels": st["unmapped"],
                   "labels": st["labels"],
                   "index_start": {k: {b: str(cal[i].date()) for b, i in v["start"].items()} for k, v in D["index"].items()},
                   "etf_first": D["index"]["etf"].get("first", {})}
    bfreq = {}
    for name, ex in D["excl"].items():
        days = [x for x in ex if x]
        c = Counter(b for x in days for b in x)
        nz = [i for i, x in enumerate(ex) if x]
        bfreq[name] = {"first_day": str(cal[nz[0]].date()) if nz else None, "n_days": len(days),
                       "bucket_share": {b: c[b] / len(days) for b in R.BUCKETS if days}}
    res["data"]["bottom_freq"] = bfreq

    books = {}
    for sid in SIDS:
        row = {"versions": {}}
        for ver in (("opt", "pes") if sid in PES else ("opt",)):
            base = load_run(runs_dir, sid, ver, "BASE")
            if base is None:
                continue
            if ver == "opt":
                res["check_scoreboard"][sid] = base["meta"].get("check_scoreboard_max_abs")
                row["coverage"] = coverage(base)
                if sid == "etf_trend":
                    rows = base["seeds"][base["rep"]]["trades"]
                    tk = Counter(t for _, t, _ in rows)
                    u = pd.read_csv("/Users/koscom/Projects/auto_stock/data/archive/krx_daily_long/meta/universe_etf.csv",
                                    dtype=str)
                    nm = dict(zip(u["ticker"], u["name"]))
                    row["etf_traded"] = {t: {"n": n, "name": nm.get(t, ""), "bucket": R.etf_bucket(nm.get(t, ""))}
                                         for t, n in tk.most_common()}
            mb = C.metrics(base["dates"], base["equity"])
            vr = {"BASE": {"metrics": mb, "abs_pass": SR.absolute_pass(mb),
                           "trades": trade_stats(base["seeds"][base["rep"]]["trades"]),
                           "seed_cagr_median": base["meta"]["seed_cagr_median"],
                           "seed_mdd_median": base["meta"]["seed_mdd_median"]}}
            books[(sid, ver, "BASE")] = (base["dates"], base["equity"])
            for v in VARIANTS:
                o = load_run(runs_dir, sid, ver, v)
                if o is None:
                    continue
                m = C.metrics(o["dates"], o["equity"])
                dc, dm = m["cagr"] - mb["cagr"], m["mdd"] - mb["mdd"]
                vr[v] = {"metrics": m, "abs_pass": SR.absolute_pass(m), "d_cagr": dc, "d_mdd": dm,
                         "effect": effect(dc, dm), "trades": trade_stats(o["seeds"][o["rep"]]["trades"]),
                         "dropped": dropped_stats(base, o),
                         "seed_cagr_median": o["meta"]["seed_cagr_median"],
                         "seed_mdd_median": o["meta"]["seed_mdd_median"],
                         "per_period_d_cagr": {k: m["periods"][k]["cagr"] - mb["periods"][k]["cagr"]
                                               for k in m["periods"] if k in mb["periods"]}}
                books[(sid, ver, v)] = (o["dates"], o["equity"])
            row["versions"][ver] = vr
        if "opt" not in row["versions"]:
            continue
        vers = list(row["versions"])
        summ = {}
        for v in VARIANTS:
            vx = [x for x in vers if v in row["versions"][x]]
            if vx:
                effs = {row["versions"][x][v]["effect"] for x in vx}
                summ[v] = {"effect": effs.pop() if len(effs) == 1 else "엇갈림",
                           "status": ("참고" if v == "BF" else
                                      ("통과" if all(row["versions"][x][v]["abs_pass"] for x in vx) else "실패")),
                           "versions": vx}
        row["summary"] = summ
        res["strategies"][sid] = row
        for v in VARIANTS:
            for ver in vers:
                if v not in row["versions"][ver]:
                    continue
                eid = f"SRS_{sid.upper()}{SUFFIX[v]}" + ("_PES" if ver == "pes" else "")
                r = row["versions"][ver][v]
                curves_for[eid] = books[(sid, ver, v)]
                entries.append({
                    "id": eid,
                    "name": f"{NAMES[sid]} · 섹터 RS 하위 30% 배제({VNAME[v]})" + (" (비관 체결)" if ver == "pes" else ""),
                    "desc": (f"그날 신호 중 섹터(KRX 업종 → ETF 묶음 19개) RS 하위 30% 섹터 종목의 신규매수를 버림 · "
                             f"RS = 섹터 수익 − KOSPI200 수익(D-1 종가) · 보유분 청산 그대로 · 빠진 신호(대표 씨앗) "
                             f"{r['dropped']['dropped_rep']}"),
                    "status": "참고" if v == "BF" else ("통과" if r["abs_pass"] else "실패"),
                    "status_ref": f"{REF} §2",
                    "group_title": "섹터 RS 하위 30% 배제 — 전략별 단독 계좌(거래 단위 재시뮬레이션)",
                    "source": f"sector_rs_run.py · {sid} · {ver} · {v} · 대표 씨앗 = 하위 중앙"})

    # ── 균등 병행 포트폴리오 ──
    order = list(SIDS)
    rule = lambda r, av: S.weights_equal(av)  # noqa: E731
    port = {}
    for ver, vlist in (("opt", ("BASE",) + PORT_VARIANTS), ("pes", ("BASE", "R60"))):
        for v in vlist:
            comp = {}
            for sid in SIDS:
                vv = ver if sid in PES else "opt"
                if (sid, vv, v) not in books:
                    comp = None
                    break
                comp[sid] = books[(sid, vv, v)]
            if comp is None:
                continue
            rr = S.rotation(comp, order, rule)
            port[(ver, v)] = (rr["dates"], rr["value"])
    for (ver, v), (d, val) in port.items():
        m = C.metrics(d, val)
        rec = {"metrics": m, "abs_pass": SR.absolute_pass(m)}
        if v != "BASE" and (ver, "BASE") in port:
            mb = C.metrics(*port[(ver, "BASE")])
            rec.update({"d_cagr": m["cagr"] - mb["cagr"], "d_mdd": m["mdd"] - mb["mdd"],
                        "effect": effect(m["cagr"] - mb["cagr"], m["mdd"] - mb["mdd"]),
                        "per_period_d_cagr": {k: m["periods"][k]["cagr"] - mb["periods"][k]["cagr"]
                                              for k in m["periods"] if k in mb["periods"]}})
        res["portfolio"][f"{ver}__{v}"] = rec
        eid = "SRS_PORT" + ("_PES" if ver == "pes" else "") + ("_BASE" if v == "BASE" else SUFFIX[v])
        curves_for[eid] = (d, val)
        entries.append({
            "id": eid,
            "name": ("8전략 균등 병행 · 분기 되돌림" + (" · 원판" if v == "BASE" else f" · 섹터 RS 하위 30% 배제({VNAME[v]})")
                     + (" (비관 체결)" if ver == "pes" else "")),
            "desc": "kojiro·donchian·vcp·bfb·vb·etf_trend·평균회귀 2판 단독 계좌 곡선 균등 · 분기말 되돌림 · 회전 비용 0.19%/편도",
            "status": "통과" if rec["abs_pass"] else "실패", "status_ref": f"{REF} §4",
            "group_title": "섹터 RS 하위 30% 배제 — 8전략 균등 병행(곡선 근사)",
            "source": "sector_rs_report.py · sb_addons_core.rotation(균등)"})

    for e in entries:
        d, v = curves_for[e["id"]]
        d = pd.DatetimeIndex(d)
        v = np.asarray(v, float)
        e["period"] = [str(d[0].date()), str(d[-1].date())]
        e["curve"] = {"dates": [str(x.date()) for x in d], "cum": [float(f"{x / v[0]:.7g}") for x in v]}
    doc = {"source": "sector_rs 2026-10-06 · tools/replay/sector_rs_*.py · 사전 등록 "
                     "_workspace/analysis/sector_rs_20261006/prereg.frozen.md", "entries": entries}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "scoreboard_entries.json"), "w") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(out_dir, "result.json"), "w") as fh:
        json.dump(SBD._clean(res), fh, ensure_ascii=False, indent=1)
    print(f"[srs_report] 항목 {len(entries)} · {out_dir}", flush=True)
    return res, entries


# ═════════════════════════════════ 문서 ═════════════════════════════════

_p, _f, _yr, _row_metrics, HDR, SEP = SR._p, SR._f, SR._yr, SR._row_metrics, SR.HDR, SR.SEP
VERN = {"opt": "낙관", "pes": "비관"}


def _ts(t):
    if not t or t["n"] == 0:
        return "0건"
    return f"{t['n']:,}건 · {_p(t['mean'], 2)} [{_p(t['lo90'], 2)}]"


def write_md(res, out_dir, head_path):
    L = []
    a = L.append
    if head_path and os.path.exists(head_path):
        a(open(head_path, encoding="utf-8").read().rstrip())
        a("")
    S_ = res["strategies"]
    # ── 2. 전략별 주판 ──
    a("## 2. 전략별 — 원판 vs 섹터 RS 60일 하위 30% 배제(주판)")
    a("")
    a("각 전략 단독 계좌(시작 4,707,820원) · 대표 씨앗 = 16개 중 최종 평가액 하위 중앙. 「효과」 = 연복리가 오르고 최대 낙폭이 얕아지면 "
      "도움, 연복리가 내리고 낙폭도 얕아지지 않으면 해, 그 밖 엇갈림. 「절대」 = 연복리 > 0 · 최대 낙폭 ≥ −35% · 같은 창 069500 보유 연복리 이상.")
    a("")
    a("| 전략 | 판 | 판(관문) " + HDR)
    a("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for sid in SIDS:
        if sid not in S_:
            continue
        for ver, vr in S_[sid]["versions"].items():
            for v in ("BASE", "R60"):
                if v not in vr:
                    continue
                lab = "원판" if v == "BASE" else "배제"
                a(f"| {NAMES[sid]} | {VERN[ver]} | {lab} | {_row_metrics(vr[v]['metrics'])} |")
    a("")
    a("| 전략 | 판 | 연복리 차 | 최대 낙폭 차 | 학습 · 검증 · 보류 연복리 차 | 효과 | 절대(배제판) | 절대(원판) |")
    a("|---|---|---|---|---|---|---|---|")
    for sid in SIDS:
        if sid not in S_:
            continue
        for ver, vr in S_[sid]["versions"].items():
            r = vr.get("R60")
            if not r:
                continue
            pp = " · ".join(_p(r["per_period_d_cagr"].get(k), 2) for k in ("학습", "검증", "보류"))
            a(f"| {NAMES[sid]} | {VERN[ver]} | {_p(r['d_cagr'], 2)} | {_p(r['d_mdd'])} | {pp} | {r['effect']} | "
              f"{'통과' if r['abs_pass'] else '실패'} | {'통과' if vr['BASE']['abs_pass'] else '실패'} |")
    a("")
    a("### 2.1 거래 — 빠진 것이 실제로 나쁜 거래였나")
    a("")
    a("거래당 순수익 = 청산가/진입가 − 1 − 0.38%(평평한 비용 — 원판·배제판 같은 잣대). 「[ ]」 = 진입월 블록 부트스트랩 90% 구간의 하한. "
      "「빠진 거래」 = 원판 씨앗 16개의 거래 중, 같은 씨앗의 배제판에서 관문이 버린 (날짜, 종목) 신호와 같은 것들(씨앗 16 모음).")
    a("")
    a("| 전략 | 판 | 원판 거래(대표 씨앗) | 배제판 거래(대표 씨앗) | 빠진 신호(대표 · 씨앗 중앙) | 빠진 거래의 원판 성과 [90% 구간] | 원판 전체 평균(씨앗 16) | 판정 |")
    a("|---|---|---|---|---|---|---|---|")
    for sid in SIDS:
        if sid not in S_:
            continue
        for ver, vr in S_[sid]["versions"].items():
            r = vr.get("R60")
            if not r:
                continue
            dd = r["dropped"]
            mt = dd["matched"]
            ms = (f"{mt['n']:,}건 · {_p(mt['mean'], 2)} [{_p(mt['lo90'], 2)} ~ {_p(mt['hi90'], 2)}]"
                  if mt["n"] else "0건")
            a(f"| {NAMES[sid]} | {VERN[ver]} | {_ts(vr['BASE']['trades'])} | {_ts(r['trades'])} | "
              f"{dd['dropped_rep']:,} · {dd['dropped_median']:,.0f} | {ms} | {_p(dd['base_all_mean'], 2)} | {dd['verdict']} |")
    a("")
    # ── 3. 민감도 ──
    a("## 3. 민감도 — RS 기간 · 가중 · 분류 소급 · ETF 실가격")
    a("")
    a("값 = 배제판 − 원판(낙관). 「연복리 차 / 최대 낙폭 차 / 효과」. BF = 첫 분류(2001)를 1997~2000 에 소급(분류에 한해 미래 정보 — 참고). "
      "ETF = 섹터 RS 를 대표 섹터 ETF 종가로 잰 판(실질 2008-08 부터).")
    a("")
    a("| 전략 | " + " | ".join(VNAME[v] for v in VARIANTS) + " |")
    a("|---|" + "---|" * len(VARIANTS))
    for sid in SIDS:
        if sid not in S_:
            continue
        vr = S_[sid]["versions"]["opt"]
        cells = []
        for v in VARIANTS:
            r = vr.get(v)
            cells.append(f"{_p(r['d_cagr'], 2)} / {_p(r['d_mdd'])} / {r['effect']}" if r else "—")
        a(f"| {NAMES[sid]} | " + " | ".join(cells) + " |")
    a("")
    a("판정 요약(효과 · 절대 — kojiro·vb 의 60일 RS 는 낙관·비관을 함께 본 값, 나머지 칸은 낙관만):")
    a("")
    a("| 전략 | " + " | ".join(VNAME[v] for v in VARIANTS) + " |")
    a("|---|" + "---|" * len(VARIANTS))
    for sid in SIDS:
        if sid not in S_:
            continue
        sm = S_[sid]["summary"]
        a(f"| {NAMES[sid]} | " + " | ".join(f"{sm[v]['effect']} · {sm[v]['status']}" if v in sm else "—"
                                            for v in VARIANTS) + " |")
    a("")
    # ── 4. 포트폴리오 ──
    a("## 4. 8전략 균등 병행 포트폴리오(곡선 근사)")
    a("")
    a("8전략 단독 계좌 대표 곡선을 균등 비중으로 묶고 분기말마다 균등으로 되돌림(회전 비용 0.19%/편도 · etf_trend 는 2003 편입). "
      "곡선 단위 근사 — 실운영은 비중 변경이 신규 매수 예산에만 닿는다.")
    a("")
    a("| 판 | 관문 " + HDR + " 연복리 차 | 낙폭 차 | 효과 | 절대 |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for key, rec in res["portfolio"].items():
        ver, v = key.split("__")
        lab = "원판" if v == "BASE" else VNAME[v]
        a(f"| {VERN[ver]} | {lab} | {_row_metrics(rec['metrics'])} | {_p(rec.get('d_cagr'), 2)} | {_p(rec.get('d_mdd'))} | "
          f"{rec.get('effect', '—')} | {'통과' if rec['abs_pass'] else '실패'} |")
    a("")
    # ── 5. 자료 ──
    d = res["data"]
    a("## 5. 섹터 분류 출처 · 미분류 비중 · 어느 섹터가 자주 빠졌나")
    a("")
    a(f"- 분류 = KRX 정보데이터시스템 「업종분류 현황」(MDCSTAT03901) 월초 스냅숏 {d['n_snapshots']}개 · 첫 행이 온 날 = "
      f"KOSPI {d['first_snapshot']['STK']} · KOSDAQ {d['first_snapshot']['KSQ']}(그 전 요청은 빈 응답).")
    a(f"- 표에 없는 업종명(미분류 처리): {d['unmapped_labels'] or '없음'}")
    a("- 버킷 지수 시작(주판): " + " · ".join(f"{b} {x}" for b, x in d["index_start"]["strict"].items()))
    a("- ETF 보조판 대표 ETF 첫 가격일: " + " · ".join(f"{b} {x}" for b, x in d.get("etf_first", {}).items()))
    a("")
    a("신호 중 미분류 비중(원판 대표 씨앗 · 관문이 보는 그날 신호 기준 — 미분류는 배제되지 않고 통과):")
    a("")
    a("| 전략 | 전체 | 학습 1997–2012 | 검증 2013–2020 | 보류 2021–2026 | 1997–2001 신호 중 미분류 |")
    a("|---|---|---|---|---|---|")
    for sid in SIDS:
        if sid not in S_ or "coverage" not in S_[sid]:
            continue
        c = S_[sid]["coverage"]
        pr = " | ".join(f"{_p(c['periods'][k]['share'], 1, False)} ({c['periods'][k]['seen']:,})" if k in c["periods"] else "—"
                        for k in ("학습", "검증", "보류"))
        t01 = c["to_2001"]
        a(f"| {NAMES[sid]} | {_p(c['share'], 1, False)} ({c['seen']:,}) | {pr} | "
          f"{t01['unclassified']:,}/{t01['seen']:,} |")
    a("")
    a("하위 30% 에 든 날의 비율(주판 R60 · 배제가 있는 날 기준):")
    a("")
    bf = d["bottom_freq"]["R60"]
    a("| " + " | ".join(R.BUCKETS) + " |")
    a("|" + "---|" * len(R.BUCKETS))
    a("| " + " | ".join(_p(bf["bucket_share"].get(b, 0.0), 0, False) for b in R.BUCKETS) + " |")
    a("")
    a("관문 판별 배제가 처음 있는 날 · 배제 있는 날 수: " + " · ".join(
        f"{k} {v['first_day']}({v['n_days']:,}일)" for k, v in d["bottom_freq"].items()))
    a("")
    et = S_.get("etf_trend", {}).get("etf_traded")
    if et:
        a("etf_trend 원판(대표 씨앗)이 산 ETF 와 버킷(이름 규칙 — 없음 = 시장 대표·해외 → 통과):")
        a("")
        a("| ETF | 이름 | 거래 수 | 버킷 |")
        a("|---|---|---|---|")
        for t, x in et.items():
            a(f"| {t} | {x['name']} | {x['n']} | {x['bucket'] or '통과'} |")
        a("")
    a("성적표 대조(관문 끈 낙관판 − 성적표 books, 최대 원): " + " · ".join(f"{k} {v:.4f}" for k, v in res["check_scoreboard"].items()))
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
