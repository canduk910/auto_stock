#!/usr/bin/env python3
"""성적표 덧붙임 — 곡선 모으기 · 분기 순환 · 지표 · 판정 · 산출(사전 등록 §1-4 · §2 · §3 · §4 · §6).

입력 = ``sb_addons_ddp.py`` 가 낸 계좌 곡선(<books>/<sid>__<판>__<base|ddp>.npz) · ``sb_addons_wf.py`` 가 낸
재조정 곡선(<wf>/WF_<sid>__<판>.npz) · 성적표 곡선(``scoreboard.load_global`` · ``load_base``) · 실거래 왕복.

    python tools/replay/sb_addons_report.py <books_dir> <wf_dir> <out_dir>
"""
from __future__ import annotations

import json
import os
import sys
import time

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from replay import sb_addons_core as S  # noqa: E402
from replay import scoreboard as SBD  # noqa: E402

LIVE_TRIPS = ("/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/1177b759-a6e8-4448-8205-8c5f1396a3a3/"
              "scratchpad/audit/live_trips.json")
LIVE_START = "2026-04-29"
LIVE_PR = {"momentum": 0.25, "long_tail_volatility": 0.2}
END = "2026-10-02"
MDD_LIM = -0.35

DDP_SIDS = ("kojiro", "donchian", "vcp", "bfb", "vb", "etf_trend", "mr_band", "mr_fkeep")
PES = {"kojiro", "vb"}
NAMES = {"kojiro": "kojiro", "donchian": "donchian_swing", "vcp": "vcp_breakout", "bfb": "bull_flag_breakout",
         "vb": "volatility_breakout", "etf_trend": "etf_trend", "mr_band": "평균회귀 볼린저(현행)",
         "mr_fkeep": "평균회귀 볼린저(F-keep)", "momentum": "momentum", "long_tail_volatility": "long_tail_volatility",
         "ou": "평균회귀 OU z"}
# 분기 순환 구성(사전 등록 §2-1 나열 순서 = 동순위 순서)
ROT = ("momentum", "volatility_breakout", "long_tail_volatility", "donchian_swing", "bull_flag_breakout",
       "vcp_breakout", "kojiro", "etf_trend")
ROT_SRC = {"volatility_breakout": "vb", "donchian_swing": "donchian", "bull_flag_breakout": "bfb",
           "vcp_breakout": "vcp", "kojiro": "kojiro", "etf_trend": "etf_trend"}
OPW = {"kojiro": 0.30, "donchian_swing": 0.25, "vcp_breakout": 0.20, "bull_flag_breakout": 0.20, "momentum": 0.03,
       "etf_trend": 0.02, "volatility_breakout": 0.0, "long_tail_volatility": 0.0}
CURVE_DDP = ("K200", "BL_B0", "SPX", "NDX", "B1", "B")
CURVE_NAMES = {"K200": "KOSPI200 단순 보유(총수익 모형)", "BL_B0": "069500 단순 보유(바탕 층 계좌)",
               "SPX": "S&P500 단순 보유(환노출)", "NDX": "나스닥100 단순 보유(환노출)", "B1": "60/40(KOSPI200 60 · 미국채10년 40)",
               "B": "7자산 동일 비중 · 월 되돌림"}
QR_RULES = {
    "QR_TOP30": ("분기 순환 — 직전 분기 1위 30% · 나머지 균등", lambda r, av: S.weights_top(r, 0.30)),
    "QR_TOP50": ("분기 순환 — 직전 분기 1위 50% · 나머지 균등(민감도)", lambda r, av: S.weights_top(r, 0.50)),
    "QR_EQ": ("8전략 균등 · 분기 되돌림(비교 기준)", lambda r, av: S.weights_equal(av)),
    "QR_OPW": ("운영 비중 고정 · 분기 되돌림(비교 기준)", lambda r, av: S.weights_fixed(av, OPW)),
    "QR5_MAIN": ("상위 5 — 1위 30% · 2~5위 17.5%", lambda r, av: S.weights_topk(r, 5, [0.30] + [0.175] * 4)),
    "QR5_EQ": ("상위 5 — 균등 20%", lambda r, av: S.weights_topk(r, 5, [0.20] * 5)),
}


QRX_DD = 0.10
QRX_PES_EXTRA = 0.00075          # 추가 등록 §2-6: SLIPPAGE_ALLOWANCE 0.15%p 왕복의 편도
CRISIS = (("아시아 외환위기", "1997-07-01", "1998-12-31"), ("세계 금융위기", "2008-01-01", "2009-06-30"),
          ("코로나", "2020-02-01", "2020-06-30"), ("긴축 하락", "2022-01-01", "2022-12-31"))
CRISIS_REF = (("닷컴", "2000-01-01", "2001-12-31"), ("유럽 재정", "2011-08-01", "2011-12-31"))


def qrx_id(qid: str) -> str:
    return "QRX_5_" + qid[4:] if qid.startswith("QR5_") else "QRX_" + qid[3:]


def _crisis_of(d, wins):
    for nm, a, b in wins:
        if pd.Timestamp(a) <= d <= pd.Timestamp(b):
            return nm
    return None


def qrx_events(events, dates, base_v, C) -> list:
    bl = C.bl
    bv = pd.Series(np.asarray(base_v, float), index=pd.DatetimeIndex(dates))
    out = []
    for e in events:
        s = pd.Timestamp(e["sell"]) if e.get("sell") else None
        rr = pd.Timestamp(e["reenter"]) if e.get("reenter") else None
        row = {"trigger": e["trigger"], "sell": e.get("sell"), "reenter": e.get("reenter"),
               "dd_at_trigger": e["value"] / e["peak"] - 1.0}
        if s is not None:
            end = rr if rr is not None else bl.index[-1]
            b0 = float(bl[bl.index <= s].iloc[-1])
            b1 = float(bl[bl.index <= end].iloc[-1])
            row["index_move"] = b1 / b0 - 1.0
            row["base_move"] = float(bv[bv.index <= end].iloc[-1] / bv[bv.index <= s].iloc[-1] - 1.0)
            row["false_alarm"] = bool(rr is not None and b1 > b0)
            row["crisis"] = _crisis_of(s, CRISIS)
            row["crisis_ref"] = _crisis_of(s, CRISIS_REF)
        out.append(row)
    return out


def qrx_summary(evs) -> dict:
    n = len([e for e in evs if e.get("sell")])
    hit = sum(1 for e in evs if e.get("crisis"))
    hit_ref = sum(1 for e in evs if e.get("crisis_ref"))
    fa = sum(1 for e in evs if e.get("false_alarm"))
    covered = sorted({e["crisis"] for e in evs if e.get("crisis")})
    missed = [nm for nm, _, _ in CRISIS if nm not in covered]
    return {"n": n, "crisis_hits": hit, "crisis_ref_hits": hit_ref, "false_alarms": fa, "covered": covered,
            "missed": missed}


def load_npz(path):
    z = np.load(path, allow_pickle=False)
    return pd.DatetimeIndex(pd.to_datetime(z["dates"].astype(str))), np.asarray(z["equity"], float), \
        json.loads(str(z["meta"]))


# ═════════════════════════════════ 지표 ═════════════════════════════════

class Ctx:
    def __init__(self):
        t0 = time.time()
        g, rf = SBD.load_global()
        self.rf = rf
        self.glob = g
        b = SBD.load_base()
        self.base = b
        self.k200 = pd.Series(g["K200"].value, index=g["K200"].dates)
        self.bl = pd.Series(b["BL_B0"].value, index=b["BL_B0"].dates)
        print(f"[report] 성적표 곡선 {time.time() - t0:.0f}s", flush=True)

    def bl_cagr(self, d0, d1) -> float:
        s = self.bl.reindex(self.bl.index.union(pd.DatetimeIndex([d0, d1]))).ffill()
        return SBD.cagr(float(s[d0]), float(s[d1]), d0, d1)

    def metrics(self, dates, v) -> dict:
        dates = pd.DatetimeIndex(dates)
        v = np.asarray(v, float)
        m = SBD.compute_metrics(dates, v, self.rf, self.k200)
        m.pop("yearly", None)
        m["bl_cagr_same_window"] = self.bl_cagr(dates[0], dates[-1])
        m["excess_vs_bl"] = m["cagr"] - m["bl_cagr_same_window"]
        per = {}
        for nm, a, b in S.PERIODS:
            p = S.period_stats(dates, v, a, b)
            if p is None:
                continue
            p["bl_cagr"] = self.bl_cagr(pd.Timestamp(p["start"]), pd.Timestamp(p["end"]))
            blp = S.period_stats(self.bl.index, self.bl.to_numpy(), a, b)
            p["bl_mdd"] = blp["mdd"] if blp else None
            per[nm] = p
        m["periods"] = per
        return m


def absolute_pass(m) -> bool:
    return bool(m["cagr"] > 0 and m["mdd"] >= MDD_LIM and m["cagr"] >= m["bl_cagr_same_window"])


# ═════════════════════════════════ 조립 ═════════════════════════════════

def live_curves(cal: pd.DatetimeIndex) -> dict:
    trips = json.load(open(LIVE_TRIPS))["trips"]
    out = {}
    for sid, pr in LIVE_PR.items():
        d, v, n = S.live_curve(trips, sid, cal, LIVE_START, pr, end=END)
        out[sid] = (d, v, n)
    return out


def build(books_dir, wf_dir, out_dir):
    C = Ctx()
    res = {"generated_kst": pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m-%d %H:%M"), "ddp": {}, "ddp_curve": {},
           "qr": {}, "qrx": {}, "wf": {}}
    entries = []
    curves_for = {}                 # 성적표 항목 곡선

    # ── DDP 거래 단위 ──
    for sid in DDP_SIDS:
        row = {}
        for ver in ("opt", "pes"):
            vv = ver if sid in PES else "opt"
            db, vb_, mb = load_npz(os.path.join(books_dir, f"{sid}__{vv}__base.npz"))
            dd, vd, md = load_npz(os.path.join(books_dir, f"{sid}__{vv}__ddp.npz"))
            assert list(db) == list(dd)
            mb_ = C.metrics(db, vb_)
            md_ = C.metrics(dd, vd)
            dc, dm = md_["cagr"] - mb_["cagr"], md_["mdd"] - mb_["mdd"]
            eff = "도움" if (dc > 0 and dm > 0) else ("해" if (dc < 0 and dm <= 0) else "엇갈림")
            row[ver] = {"base": mb_, "ddp": md_, "d_cagr": dc, "d_mdd": dm, "effect": eff,
                        "abs_pass": absolute_pass(md_), "same_as_opt": sid not in PES,
                        "seed": {"base_cagr_median": mb["seed_cagr_median"], "ddp_cagr_median": md["seed_cagr_median"],
                                 "base_mdd_median": mb["seed_mdd_median"], "ddp_mdd_median": md["seed_mdd_median"]},
                        "gate": md["ddp_rep"], "gate_median": md["ddp_median"],
                        "per_period_d_cagr": {k: md_["periods"][k]["cagr"] - mb_["periods"][k]["cagr"]
                                              for k in md_["periods"] if k in mb_["periods"]}}
            if ver == "opt" or sid in PES:
                eid = f"DDP_{sid.upper()}" + ("_PES" if ver == "pes" else "")
                curves_for[eid] = (dd, vd)
        effs = {row[v]["effect"] for v in ("opt", "pes")}
        row["effect"] = "도움" if effs == {"도움"} else ("해" if effs == {"해"} else "엇갈림")
        row["status"] = "통과" if (row["opt"]["abs_pass"] and row["pes"]["abs_pass"]) else "실패"
        res["ddp"][sid] = row
        for ver in (("opt", "pes") if sid in PES else ("opt",)):
            eid = f"DDP_{sid.upper()}" + ("_PES" if ver == "pes" else "")
            r = row[ver]
            entries.append({
                "id": eid, "name": f"{NAMES[sid]} · 낙폭 −20% 이면 30영업일 신규매수 정지"
                                   + (" (비관 체결)" if ver == "pes" else ""),
                "desc": (f"단독 계좌 종가 평가액이 기준 최고치 대비 −20% 이하인 날 다음 영업일부터 30영업일 신규매수 금지"
                         f"(보유분은 원래 규칙대로) · 재개일 종가로 기준 재설정 · 발동 {r['gate']['n_events']}회 · "
                         f"정지 {r['gate']['paused_days']}영업일"),
                "status": "통과" if r["abs_pass"] else "실패",
                "status_ref": "_workspace/analysis/sb_addons_20261006/result.md §1",
                "group_title": "낙폭 정지 DDP — 전략별 단독 계좌(거래 단위 재시뮬레이션)",
                "source": f"sb_addons_ddp.py · {sid} · {ver} · 대표 씨앗 = 하위 중앙"})

    # ── DDP 곡선 근사 ──
    rf = C.rf
    for cid in CURVE_DDP:
        c = C.glob.get(cid) or C.base.get(cid)
        dates, v = pd.DatetimeIndex(c.dates), np.asarray(c.value, float)
        rfi = rf.reindex(rf.index.union(dates)).ffill().reindex(dates).to_numpy()
        rr = np.zeros(len(dates))
        rr[1:] = rfi[1:] / rfi[:-1] - 1.0
        rr = np.nan_to_num(rr)
        out, ev = S.ddp_curve(v, rr)
        mb_, md_ = C.metrics(dates, v), C.metrics(dates, out)
        res["ddp_curve"][cid] = {"base": mb_, "ddp": md_, "d_cagr": md_["cagr"] - mb_["cagr"],
                                 "d_mdd": md_["mdd"] - mb_["mdd"], "events": [
                                     [str(dates[a].date()), str(dates[b].date()) if b is not None else None]
                                     for a, b in ev]}
        eid = f"DDP_C_{cid.replace('-', '_')}"
        curves_for[eid] = (dates, out)
        entries.append({"id": eid, "name": f"{CURVE_NAMES[cid]} · 낙폭 −20% 이면 현금 30영업일(근사)",
                        "desc": f"곡선 단위 근사 — 낙폭 −20% 인 날 종가에 전량 현금화 · 30영업일 원화 단기금리 · 재진입(편도 0.19%씩) · "
                                f"현금화 {len(ev)}회",
                        "status": "참고", "status_ref": "_workspace/analysis/sb_addons_20261006/result.md §1.3",
                        "group_title": "낙폭 정지 DDP — 곡선형 항목 근사(참고)",
                        "source": f"sb_addons_core.ddp_curve({cid})"})

    # ── 분기 순환 ──
    cal = pd.DatetimeIndex(C.bl.index)
    live = live_curves(cal)
    res["live"] = {k: {"n_trips": n, "start": str(d[0].date()), "final": float(v[-1])} for k, (d, v, n) in live.items()}
    for ver in ("opt", "pes"):
        comp = {}
        for sid in ROT:
            if sid in LIVE_PR:
                d, v, _ = live[sid]
                comp[sid] = (d, v)
                continue
            src = ROT_SRC[sid]
            vv = ver if src in PES else "opt"
            d, v, _ = load_npz(os.path.join(books_dir, f"{src}__{vv}__base.npz"))
            comp[sid] = (d, v)
        for qid, (desc, rule) in QR_RULES.items():
            r = S.rotation(comp, list(ROT), rule)
            m = C.metrics(r["dates"], r["value"])
            melted = 0
            for lg in r["log"]:
                top = lg["ranked"][0] if lg["ranked"] else None
                if top is None:
                    continue
                d, v = comp[top]
                s = pd.Series(v, index=d)
                val = s[s.index <= pd.Timestamp(lg["date"])]
                if len(val) and val.iloc[-1] < 0.1 * v[0]:
                    melted += 1
            top_cnt = {}
            for lg in r["log"]:
                if lg["ranked"]:
                    top_cnt[lg["ranked"][0]] = top_cnt.get(lg["ranked"][0], 0) + 1
            res["qr"].setdefault(qid, {})[ver] = {
                "metrics": m, "abs_pass": absolute_pass(m), "start": r["start"], "n_rebal": len(r["log"]),
                "turnover_mean": float(np.mean([x["turnover"] for x in r["log"]])),
                "cost_total": float(np.sum([x["cost"] for x in r["log"]])),
                "top_melted_quarters": melted, "top_count": top_cnt,
                "log_tail": r["log"][-6:]}
            eid = qid + ("_PES" if ver == "pes" else "")
            curves_for[eid] = (r["dates"], r["value"])
            # ── 추가 등록 QRX: 포트폴리오 −10% → 다음 날 전량 매도 · 30영업일 현금 · 31번째 날 재진입 ──
            dts = pd.DatetimeIndex(r["dates"])
            rfi = C.rf.reindex(C.rf.index.union(dts)).ffill().reindex(dts).to_numpy()
            rfr = np.zeros(len(dts))
            rfr[1:] = np.nan_to_num(rfi[1:] / rfi[:-1] - 1.0)
            rx = S.rotation(comp, list(ROT), rule, stop={"dd": QRX_DD, "days": 30, "rf": rfr,
                                                          "extra": 0.0 if ver == "opt" else QRX_PES_EXTRA})
            mx = C.metrics(rx["dates"], rx["value"])
            xid = qrx_id(qid)
            res["qrx"].setdefault(xid, {"base": qid})[ver] = {
                "metrics": mx, "abs_pass": absolute_pass(mx), "d_cagr": mx["cagr"] - m["cagr"],
                "d_mdd": mx["mdd"] - m["mdd"], "events": qrx_events(rx["events"], dts, r["value"], C)}
            curves_for[xid + ("_PES" if ver == "pes" else "")] = (rx["dates"], rx["value"])
    for xid, q in res["qrx"].items():
        q["status"] = "통과" if (q["opt"]["abs_pass"] and q["pes"]["abs_pass"]) else "실패"
        q["summary"] = qrx_summary(q["opt"]["events"])
        q["summary_pes"] = qrx_summary(q["pes"]["events"])
        desc = QR_RULES[q["base"]][0]
        for ver in ("opt", "pes"):
            entries.append({"id": xid + ("_PES" if ver == "pes" else ""),
                            "name": f"{desc} + 계좌 −10% 손절(30영업일 현금)" + (" (비관 체결)" if ver == "pes" else ""),
                            "desc": "포트폴리오 평가액이 직전 최고치 대비 −10% 인 날 → 다음 영업일 종가 전량 매도 → 30영업일 현금 → "
                                    f"31번째 영업일 재진입(그 시점 비중) · 발동 {len(q[ver]['events'])}회",
                            "status": q["status"], "status_ref": "_workspace/analysis/sb_addons_20261006/result.md §3.5",
                            "group_title": "분기 순환 + 계좌 −10% 손절 QRX — 추가 등록(곡선 단위 근사)",
                            "source": f"sb_addons_core.rotation(stop) · {ver}"})
    for qid, (desc, _) in QR_RULES.items():
        q = res["qr"][qid]
        q["status"] = "통과" if (q["opt"]["abs_pass"] and q["pes"]["abs_pass"]) else "실패"
        for ver in ("opt", "pes"):
            eid = qid + ("_PES" if ver == "pes" else "")
            grp = ("상위 5 QR5 — 8전략 섀도 · 분기말 상위 5만 신규매수(곡선 단위 근사)" if qid.startswith("QR5")
                   else "분기 순환 QR — 8전략 함께 · 분기말 재배분(곡선 단위 근사)")
            entries.append({"id": eid, "name": desc + (" (비관 체결)" if ver == "pes" else ""),
                            "desc": "8전략 단독 계좌 곡선을 분기말에 재배분 · 회전 비용 = 바뀐 비중 × 0.19% · "
                                    "momentum·LTV 는 2026-04-29 실거래 근사부터 · etf_trend 는 2003 부터 편입",
                            "status": q["status"], "status_ref": "_workspace/analysis/sb_addons_20261006/result.md §2·§3",
                            "group_title": grp, "source": f"sb_addons_core.rotation · {ver}"})
    for qid in QR_RULES:
        for ver in ("opt", "pes"):
            m = res["qr"][qid][ver]["metrics"]
            e = res["qr"]["QR_EQ"][ver]["metrics"]
            res["qr"][qid][ver]["vs_eq"] = {"all": m["cagr"] - e["cagr"],
                                           **{k: m["periods"][k]["cagr"] - e["periods"][k]["cagr"]
                                              for k in m["periods"]}}

    # ── WF ──
    wf_status = {}
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith(".npz"):
            continue
        sid, ver = fn[3:-4].split("__")
        d, v, meta = load_npz(os.path.join(wf_dir, fn))
        m = C.metrics(d, v)
        res["wf"][f"{sid}__{ver}"] = {"metrics": m, "meta": meta}
        wres = json.load(open(os.path.join(_ROOT, "_workspace/analysis/wfo_20261006", sid, "result.json")))
        label = wres["label"] if sid == "vb" else wres["judge"]["r"]["label"]
        wf_status[sid] = label
        eid = f"WF_{sid.upper()}" + ("_PES" if ver == "pes" else "")
        curves_for[eid] = (d, v)
        entries.append({"id": eid, "name": f"{NAMES[sid]} · 주기적 재조정(직전 10년 → 다음 1년)"
                                           + (" (비관 체결)" if ver == "pes" else ""),
                        "desc": "해마다 직전 10년 학습 거래의 90% 하한 최대 조합을 다음 1년에 사용 · 이어 붙인 계좌(씨앗 하위 중앙)",
                        "status": "실패" if "실패" in label else "통과",
                        "status_ref": f"_workspace/analysis/wfo_20261006/result.md · {sid}",
                        "group_title": "주기적 재조정 WF — 재조정판 계좌(2007~, etf_trend 2025~)",
                        "source": f"sb_addons_wf.py · wfo_{sid} book_fn(저장 경로)"})
    res["wf_labels"] = wf_status

    # ── 곡선 붙이기 · 저장 ──
    for e in entries:
        d, v = curves_for[e["id"]]
        d = pd.DatetimeIndex(d)
        v = np.asarray(v, float)
        e["period"] = [str(d[0].date()), str(d[-1].date())]
        e["curve"] = {"dates": [str(x.date()) for x in d], "cum": [float(f"{x / v[0]:.7g}") for x in v]}
    doc = {"source": "sb_addons 2026-10-06 · tools/replay/sb_addons_*.py · 사전 등록 "
                     "_workspace/analysis/sb_addons_20261006/prereg.frozen.md", "entries": entries}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "scoreboard_entries.json"), "w") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(out_dir, "result.json"), "w") as fh:
        json.dump(SBD._clean(res), fh, ensure_ascii=False, indent=1)
    print(f"[report] 항목 {len(entries)} · {out_dir}", flush=True)
    return res, entries


# ═════════════════════════════════ 문서 ═════════════════════════════════

def _p(x, d=1, sign=True):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x * 100:+.{d}f}%".replace("-", "−") if sign else f"{x * 100:.{d}f}%".replace("-", "−")


def _f(x, d=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:+.{d}f}".replace("-", "−")


def _yr(y):
    return f"{_p(y['ret'])} ({y['year']})" if y else "—"


def _row_metrics(m):
    per = m["periods"]
    pc = " | ".join(f"{_p(per[k]['cagr'])} · {_p(per[k]['mdd'], 0)}" if k in per else "—" for k in ("학습", "검증", "보류"))
    return (f"{_p(m['total_return'], 0)} | **{_p(m['cagr'], 2)}** | {_yr(m['best_year'])} | {_yr(m['worst_year'])} | "
            f"{_p(m['mdd'])} | {_f(m['sharpe'])} | {_p(m['excess_vs_bl'], 2)} | {pc}")


HDR = ("| 최종 누적 | 연복리 | 최고 연간(연도) | 최악 연간(연도) | 최대 낙폭 | 샤프 | 지수 보유 대비 연 초과 | "
       "학습 1997–2012 연·낙폭 | 검증 2013–2020 연·낙폭 | 보류 2021–2026 연·낙폭 |")
SEP = "|---|---|---|---|---|---|---|---|---|---|"


def write_md(res, out_dir, head_path):
    L = []
    if os.path.exists(head_path):
        L.append(open(head_path).read().rstrip() + "\n")
    L.append(f"\n> 생성 {res['generated_kst']} KST · `tools/replay/sb_addons_report.py` · 원자료 `result.json` · "
             "성적표 항목 `scoreboard_entries.json`(접두 DDP_ · QR_ · QR5_ · WF_)\n")
    L.append("\n지수 보유 = 069500 단순 보유 계좌(성적표 `BL_B0`, 2002-10 전 KOSPI200 가격지수). 「지수 보유 대비 연 초과」 = "
             "같은 시작·끝일의 그 계좌 연복리와의 차. 구간 칸 = 그 구간만 잘라 잰 연복리 · 최대 낙폭.\n")
    # §1
    L.append("\n## 1. 낙폭 정지 DDP — 전략별 단독 계좌\n")
    L.append("규칙: 종가 평가액이 기준 최고치 대비 −20% 이하인 날 → 다음 영업일부터 30영업일 신규매수 금지(보유분은 원래 규칙대로 "
             "나간다) → 재개일 종가로 기준 최고치 재설정. 곡선 = 씨앗 16 중 최종 평가액 하위 중앙(성적표와 같은 씨앗 규칙).\n")
    L.append("\n| 전략 | 판 | 원판 연복리 · 낙폭 | DDP 연복리 · 낙폭 | 연복리 차 | 낙폭 차 | 학습 · 검증 · 보류 연복리 차 | "
             "발동 · 정지 영업일 | 씨앗 중앙 연복리 원판 → DDP | 지수 보유 대비(DDP) | 효과 | 절대 판정 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for sid, row in res["ddp"].items():
        for ver in ("opt", "pes"):
            r = row[ver]
            if ver == "pes" and r["same_as_opt"]:
                continue
            b, d = r["base"], r["ddp"]
            pdc = " · ".join(_p(r["per_period_d_cagr"].get(k), 1) for k in ("학습", "검증", "보류"))
            lab = {"opt": "낙관", "pes": "비관"}[ver] + ("(판 하나)" if r["same_as_opt"] else "")
            L.append(f"| {NAMES[sid]} | {lab} | {_p(b['cagr'], 2)} · {_p(b['mdd'], 0)} | {_p(d['cagr'], 2)} · "
                     f"{_p(d['mdd'], 0)} | {_p(r['d_cagr'], 2)} | {_p(r['d_mdd'], 1)} | {pdc} | "
                     f"{r['gate']['n_events']} · {r['gate']['paused_days']} | {_p(r['seed']['base_cagr_median'], 2)} → "
                     f"{_p(r['seed']['ddp_cagr_median'], 2)} | {_p(d['excess_vs_bl'], 2)} | {r['effect']} | "
                     f"{'통과' if r['abs_pass'] else '실패'} |")
    L.append("\n- 「효과」 = 도움(연복리 ↑ 이고 낙폭 얕아짐) · 해(연복리 ↓ 이고 낙폭도 안 얕아짐) · 엇갈림. 「판 하나」 = 30년 재검증이 "
             "체결 판을 하나만 정의한 전략(비관 = 낙관).")
    L.append("- 절대 판정 = 연복리 > 0 ∧ 최대 낙폭 ≥ −35% ∧ 같은 창 지수 보유 연복리 이상(30년 재검증 P2·P3 문턱 + 지수).\n")
    eff = {sid: row["effect"] for sid, row in res["ddp"].items()}
    L.append("전략별 종합 효과(두 판 모두): " + " · ".join(f"{NAMES[k]} {v}" for k, v in eff.items()) + "\n")
    L.append("\n### 1.3 곡선형 항목 — 근사(참고)\n")
    L.append("곡선 단위: 낙폭 −20% 인 날 종가에 전량 현금화(편도 0.19%) → 곡선 달력 30영업일 원화 단기금리 → 재진입(편도 0.19%) · "
             "재진입 값이 새 기준. **거래 단위 시뮬레이션이 아니다**(근사).\n")
    L.append("\n| 항목 | 원판 연복리 · 낙폭 | 근사 DDP 연복리 · 낙폭 | 연복리 차 | 낙폭 차 | 현금화 횟수 | 학습 · 검증 · 보류 연복리 차 |")
    L.append("|---|---|---|---|---|---|---|")
    for cid, r in res["ddp_curve"].items():
        b, d = r["base"], r["ddp"]
        pdc = " · ".join(_p(d["periods"][k]["cagr"] - b["periods"][k]["cagr"], 1) if k in d["periods"] else "—"
                         for k in ("학습", "검증", "보류"))
        L.append(f"| {CURVE_NAMES[cid]} | {_p(b['cagr'], 2)} · {_p(b['mdd'], 0)} | {_p(d['cagr'], 2)} · {_p(d['mdd'], 0)} | "
                 f"{_p(r['d_cagr'], 2)} | {_p(r['d_mdd'], 1)} | {len(r['events'])} | {pdc} |")
    # §2 · §3
    L.append("\n## 2. 분기 순환 QR · 3. 상위 5 QR5 — 8전략을 함께\n")
    L.append("구성 = 8전략 단독 계좌 곡선(낙관/비관). 분기말 종가 뒤 직전 분기 수익 순위로 비중을 다시 정한다 · 분기 안에서는 비중이 "
             "떠다닌다 · 회전 비용 = 평가액 × Σ|새 비중 − 떠다닌 비중| × 0.19%.\n")
    L.append("\n| 판 | 체결 | " + HDR[2:] + " 판정 |")
    L.append("|---|---|" + SEP[1:] + "---|")
    for qid, (desc, _) in QR_RULES.items():
        for ver in ("opt", "pes"):
            q = res["qr"][qid][ver]
            L.append(f"| {desc} | {'낙관' if ver == 'opt' else '비관'} | {_row_metrics(q['metrics'])} | "
                     f"{res['qr'][qid]['status'] if ver == 'opt' else ''} |")
    bl = res["qr"]["QR_EQ"]["opt"]["metrics"]
    L.append(f"\n같은 창(1996-12-31 ~ 2026-10-02) 지수 보유(069500 계좌) 연복리 = **{_p(bl['bl_cagr_same_window'], 2)}**.\n")
    L.append("\n**순환 효과(그 판 연복리 − 8전략 균등 분기 연복리, %p)**\n")
    L.append("| 판 | 체결 | 전체 | 학습 | 검증 | 보류 | 평균 회전/분기 | 비용 합 | 1위가 녹은 계좌였던 분기 | 1위 횟수(분기) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for qid, (desc, _) in QR_RULES.items():
        for ver in ("opt", "pes"):
            q = res["qr"][qid][ver]
            v = q["vs_eq"]
            tc = " · ".join(f"{k} {n}" for k, n in sorted(q["top_count"].items(), key=lambda x: -x[1]))
            L.append(f"| {desc} | {'낙관' if ver == 'opt' else '비관'} | {_p(v['all'], 2)} | {_p(v.get('학습'), 2)} | "
                     f"{_p(v.get('검증'), 2)} | {_p(v.get('보류'), 2)} | {q['turnover_mean'] * 100:.1f}% | "
                     f"{_p(q['cost_total'], 2, sign=False)} | {q['top_melted_quarters']} / {q['n_rebal']} | {tc} |")
    st = res["qr"]["QR_TOP30"]["opt"]["start"]
    L.append("\n**편입 시작일**(곡선 시작점 · 그 뒤 첫 분기말부터 비중) — " + " · ".join(f"{k} {v}" for k, v in st.items()))
    lv = res["live"]
    L.append("\nmomentum · LTV = 30년 재현 없음 → 실거래 왕복 근사 곡선(2026-04-29 ~, 매도일에 순수익 × position_ratio): "
             + " · ".join(f"{k} {v['n_trips']}건 · 끝 값 {v['final']:.4f}" for k, v in lv.items()) + "\n")
    L.append("\n최근 리밸런싱(낙관 · QR_TOP30):\n")
    L.append("| 날짜 | 순위(직전 분기 수익) | 새 비중 |")
    L.append("|---|---|---|")
    for lg in res["qr"]["QR_TOP30"]["opt"]["log_tail"]:
        rk = " > ".join(f"{k}({lg['rets'][k] * 100:+.1f}%)" for k in lg["ranked"])
        w = " · ".join(f"{k} {x * 100:.1f}%" for k, x in lg["weights"].items())
        L.append(f"| {lg['date']} | {rk} | {w} |")
    # §3.5 QRX
    L.append("\n## 3.5 추가 등록 QRX — 포트폴리오 계좌 −10% 손절(30영업일 현금)\n")
    L.append("규칙(`prereg_addendum.md`): 포트폴리오 평가액이 직전 최고치 대비 −10% 인 날 → 다음 영업일 종가 전량 매도(편도 0.19%) → "
             "30영업일 원화 단기금리 → 31번째 영업일 종가에 그 시점 규칙 비중으로 재진입(편도 0.19%) · 재진입 값이 새 기준. "
             "비관판은 매도·재진입마다 0.075% 추가.\n")
    L.append("\n| 판 | 체결 | " + HDR[2:] + " 원판 대비 연복리 · 낙폭 | 발동 | 위기 창 겹침 | 헛발동 | 판정 |")
    L.append("|---|---|" + SEP[1:] + "---|---|---|---|---|")
    for xid, q in res["qrx"].items():
        desc = QR_RULES[q["base"]][0]
        for ver in ("opt", "pes"):
            x = q[ver]
            sm = q["summary"] if ver == "opt" else q["summary_pes"]
            L.append(f"| {desc} + 손절 | {'낙관' if ver == 'opt' else '비관'} | {_row_metrics(x['metrics'])} | "
                     f"{_p(x['d_cagr'], 2)} · {_p(x['d_mdd'], 1)} | {sm['n']} | {sm['crisis_hits']} / {sm['n']} | "
                     f"{sm['false_alarms']} / {sm['n']} | {q['status'] if ver == 'opt' else ''} |")
    L.append("\n- 위기 창(사전 고정): 아시아 외환위기 1997-07 ~ 1998-12 · 세계 금융위기 2008-01 ~ 2009-06 · 코로나 2020-02 ~ 06 · "
             "긴축 하락 2022. 「겹침」 = 매도일이 창 안. 「헛발동」 = 재진입일 지수 보유 값 > 매도일 값.\n")
    L.append("\n**위기 창별 — 발동이 있었나(낙관판)**\n")
    L.append("| 판 | " + " | ".join(nm for nm, _, _ in CRISIS) + " | 참고: 닷컴 · 유럽 재정 겹침 |")
    L.append("|---|" + "---|" * (len(CRISIS) + 1))
    for xid, q in res["qrx"].items():
        sm = q["summary"]
        cells = " | ".join("발동" if nm in sm["covered"] else "**없음**" for nm, _, _ in CRISIS)
        L.append(f"| {QR_RULES[q['base']][0]} | {cells} | {sm['crisis_ref_hits']} |")
    for xid, q in res["qrx"].items():
        evs = q["opt"]["events"]
        L.append(f"\n<details><summary>{QR_RULES[q['base']][0]} + 손절 — 발동 목록(낙관 · {len(evs)}회)</summary>\n")
        L.append("| 발동일 | 매도일 | 재진입일 | 발동 때 낙폭 | 매도→재진입 지수 보유 | 같은 기간 원판(손절 없음) | 위기 창 | 헛발동 |")
        L.append("|---|---|---|---|---|---|---|---|")
        for e in evs:
            cz = e.get("crisis") or (("참고 " + e["crisis_ref"]) if e.get("crisis_ref") else "—")
            L.append(f"| {e['trigger']} | {e.get('sell') or '—'} | {e.get('reenter') or '(끝까지 현금)'} | "
                     f"{_p(e['dd_at_trigger'], 1)} | {_p(e.get('index_move'), 1)} | {_p(e.get('base_move'), 1)} | "
                     f"{cz} | {'예' if e.get('false_alarm') else ''} |")
        L.append("\n</details>\n")
    # §4 WF
    L.append("\n## 4. 주기적 재조정 WF — 재조정판 계좌 곡선(성적표 등록용)\n")
    L.append("| 전략 | 체결 | " + HDR[2:] + " wfo 판정 | 씨앗 중앙 연복리 · 낙폭(공표 대조) |")
    L.append("|---|---|" + SEP[1:] + "---|---|")
    for k, w in res["wf"].items():
        sid, ver = k.split("__")
        mt = w["meta"]
        fill = ({"opt": "낙관", "pes": "비관"}[ver] if sid == "vb" else
                ("시가 + 0.76%(wfo 판 하나)" if sid == "kojiro" else "wfo 판 하나"))
        L.append(f"| {NAMES[sid]} | {fill} | {_row_metrics(w['metrics'])} | "
                 f"{res['wf_labels'].get(sid, '')} | {_p(mt['cagr_median'], 2)} · {_p(mt['mdd_median'], 0)} "
                 f"(공표 {_p(mt['ref_cagr_median'], 2)} · {_p(mt['ref_mdd_median'], 0)}) |")
    L.append("\n- 곡선 = 씨앗 16 중 최종 평가액 하위 중앙(성적표 규칙). wfo 결과 문서의 「계좌 연·낙폭」 은 씨앗 **중앙값**이라 "
             "대표 씨앗 곡선의 지표와 조금 다를 수 있다(오른쪽 칸이 씨앗 중앙 = 공표값 대조).\n")
    with open(os.path.join(out_dir, "result.md"), "w") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    r, _ = build(sys.argv[1], sys.argv[2], sys.argv[3])
    write_md(r, sys.argv[3], os.path.join(sys.argv[3], "head.md"))
