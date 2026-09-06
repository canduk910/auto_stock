#!/usr/bin/env python3
"""VB 'RS 강세만 매수' 반사실 계산 (읽기 전용, 기존 데이터셋 재사용).

입력  : ../data/observations.csv · ../data/daily_raw.usv · ../data/trades_roundtrips.csv
출력  : rs_strong.json · counterfactual.md 용 표 데이터

핵심 규약
  - 기본 표본 = **적격 부분집합** (D-1 거래대금 ≥ 500억). 저장 funnel 은 16:20 저녁 캡처라
    D 당일 거래대금으로 걸러져 있어 D 성과 정렬 시 룩어헤드(부적격 481건 = 21.1%).
  - RS 는 08-03 부터만 존재 → RS 평가 가능 표본 = 적격 ∩ RS 보유 (23 거래일).
  - 비용 = 왕복 28bp (수수료 0.015%×2 + 거래세 0.15% + 슬리피지 0.10%).
  - 표준오차·검정 = 일별 클러스터 (영향함수, df = G−1).
"""
from __future__ import annotations

import collections
import csv
import json
import math
import os

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
SEP = "\x1f"
_RULES_CACHE = {}

COST_BP = 28.0
NOTIONAL = 140_547.0        # VB 왕복 평균 명목 (실체결 수수료 역산, consult.md:199)
ELIG_TV = 5e10              # D-1 거래대금 ≥ 500억
PRIOR_END = "2026-08-14"
INDEX = "069500"
EXTREME_BP = 500.0          # |지수 전일비| > 5%


# --------------------------------------------------------------------------- stats
def cluster_mean_test(vals, clusters):
    n = len(vals)
    if n < 2:
        return dict(n=n, mean=(float(np.mean(vals)) if n else None), se=None, t=None, p=None,
                    G=len(set(clusters)))
    m = float(np.mean(vals))
    infl = collections.defaultdict(float)
    for v, d in zip(vals, clusters):
        infl[d] += (v - m) / n
    G = len(infl)
    if G < 2:
        return dict(n=n, mean=m, se=None, t=None, p=None, G=G)
    var = sum(x * x for x in infl.values()) * G / (G - 1)
    se = math.sqrt(var) if var > 0 else 0.0
    t = m / se if se > 0 else None
    p = float(2 * stats.t.sf(abs(t), df=G - 1)) if t is not None else None
    return dict(n=n, mean=m, se=se, t=t, p=p, G=G)


def cluster_diff_test(va, da, vb_, db):
    """mean(a) − mean(b), 일별 클러스터 영향함수 SE. a ⊂ b (중첩) 도 유효."""
    na, nb = len(va), len(vb_)
    if na < 2 or nb < 2:
        return dict(n_a=na, n_b=nb, diff=None, se=None, t=None, p=None, G=None)
    ma, mb = float(np.mean(va)), float(np.mean(vb_))
    infl = collections.defaultdict(float)
    for v, d in zip(va, da):
        infl[d] += (v - ma) / na
    for v, d in zip(vb_, db):
        infl[d] -= (v - mb) / nb
    G = len(infl)
    if G < 2:
        return dict(n_a=na, n_b=nb, mean_a=ma, mean_b=mb, diff=ma - mb, se=None, t=None, p=None, G=G)
    var = sum(x * x for x in infl.values()) * G / (G - 1)
    se = math.sqrt(var) if var > 0 else 0.0
    diff = ma - mb
    t = diff / se if se > 0 else None
    p = float(2 * stats.t.sf(abs(t), df=G - 1)) if t is not None else None
    return dict(n_a=na, n_b=nb, mean_a=ma, mean_b=mb, diff=diff, se=se, t=t, p=p, G=G)


def pearson(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 4:
        return dict(n=len(pairs), r=None, p=None)
    a = np.array([p[0] for p in pairs], float)
    b = np.array([p[1] for p in pairs], float)
    if a.std() == 0 or b.std() == 0:
        return dict(n=len(pairs), r=None, p=None)
    r, p = stats.pearsonr(a, b)
    return dict(n=len(pairs), r=float(r), p=float(p))


# --------------------------------------------------------------------------- load
def load_daily():
    daily = collections.defaultdict(list)
    with open(os.path.join(DATA, "daily_raw.usv"), encoding="utf-8") as fh:
        for line in fh:
            p = line.rstrip("\n").split(SEP)
            if len(p) < 9:
                continue
            t, d, o, h, l, c, v, tv, _cr = p
            try:
                daily[t].append(dict(d=d, o=int(o), h=int(h), l=int(l), c=int(c),
                                     v=int(v), tv=int(tv) if tv else 0))
            except ValueError:
                continue
    for t in daily:
        daily[t].sort(key=lambda r: r["d"])
    return daily


def fnum(x):
    if x in ("", "None", None):
        return None
    try:
        return float(x)
    except ValueError:
        return None


def load_obs():
    with open(os.path.join(DATA, "observations.csv"), encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------- 단기 강도 (§6)
def build_strength(daily):
    """ticker -> date -> {r1, r3x, r5x} — 전부 D-1 이전 실봉만 사용 (룩어헤드 0)."""
    real = {}
    for t, rows in daily.items():
        real[t] = [r for r in rows if r["v"] > 0 and r["o"] > 0 and r["h"] >= r["l"]]
    idx_closes = {r["d"]: r["c"] for r in real.get(INDEX, [])}
    idx_days = sorted(idx_closes)
    idx_pos = {d: i for i, d in enumerate(idx_days)}

    def idx_ret(prev_d, k):
        i = idx_pos.get(prev_d)
        if i is None or i - k < 0:
            return None
        return (idx_closes[prev_d] / idx_closes[idx_days[i - k]] - 1.0) * 100.0

    out = collections.defaultdict(dict)
    for t, rows in real.items():
        closes = [r["c"] for r in rows]
        for i, r in enumerate(rows):
            prev_d = r["d"]
            rec = {}
            for k, key in ((1, "r1"), (3, "r3"), (5, "r5")):
                if i - k >= 0 and closes[i - k] > 0:
                    rec[key] = (closes[i] / closes[i - k] - 1.0) * 100.0
                else:
                    rec[key] = None
            rec["r3x"] = None if rec["r3"] is None or idx_ret(prev_d, 3) is None else rec["r3"] - idx_ret(prev_d, 3)
            rec["r5x"] = None if rec["r5"] is None or idx_ret(prev_d, 5) is None else rec["r5"] - idx_ret(prev_d, 5)
            out[t][prev_d] = rec
    return out


# --------------------------------------------------------------------------- 격자
OUTCOMES = [
    ("a", "ret_oc_bp", None, "(a) 무조건 시가→종가"),
    ("b", "ret_bo_live_bp", "breakout_live", "(b) 라이브 목표가 돌파 조건부"),
    ("c", "ret_bo_live_stoplb_bp", "breakout_live", "(c) 돌파 + 손절하한(-5%)"),
]

STRONG_RULES = ["none", "ge0", "top50", "top25", "ge10", "drop_bot25"]
WEAK_RULES = ["lt0", "bot50", "bot25", "lt10", "drop_top25"]
RULE_LABEL = {
    "none": "미적용(전량)", "ge0": "RS ≥ 0", "top50": "일별 상위 50%", "top25": "일별 상위 25%",
    "ge10": "RS ≥ 10 %p", "drop_bot25": "일별 하위 25% 배제",
    "lt0": "RS < 0", "bot50": "일별 하위 50%", "bot25": "일별 하위 25%",
    "lt10": "RS < 10 %p", "drop_top25": "일별 상위 25% 배제",
}


def day_cuts(rows, key):
    """날짜별 p25/p50/p75 (해당 날짜의 신호 보유 행 기준). key 를 직접 읽는다."""
    byday = collections.defaultdict(list)
    for r in rows:
        v = r.get(key)
        if v is not None:
            byday[r["target_date"]].append(v)
    cuts = {}
    for d, vals in byday.items():
        if len(vals) < 4:
            cuts[d] = None
        else:
            cuts[d] = (float(np.percentile(vals, 25)), float(np.percentile(vals, 50)),
                       float(np.percentile(vals, 75)))
    return cuts


def passes(rule, v, cut):
    if rule == "none":
        return True
    if v is None:
        return None                    # 평가 불가
    if rule == "ge0":
        return v >= 0
    if rule == "lt0":
        return v < 0
    if rule == "ge10":
        return v >= 10.0
    if rule == "lt10":
        return v < 10.0
    if cut is None:
        return None
    q1, q2, q3 = cut
    if rule == "top50":
        return v >= q2
    if rule == "bot50":
        return v < q2
    if rule == "top25":
        return v >= q3
    if rule == "bot25":
        return v < q1
    if rule == "drop_bot25":
        return v > q1
    if rule == "drop_top25":
        return v <= q3
    raise ValueError(rule)


def eval_grid(rows, sigkey, rules, label):
    """rows 는 이미 신호 보유 행만. 각 rule × outcome 성과."""
    cuts = day_cuts(rows, sigkey)
    res = []
    for oc_id, valkey, bokey, oc_label in OUTCOMES:
        base = []
        for r in rows:
            if bokey and r.get(bokey) is not True:
                continue
            v = r.get(valkey)
            if v is None:
                continue
            base.append(r)
        if len(base) < 2:
            continue
        bvals = [r[valkey] for r in base]
        bdays = [r["target_date"] for r in base]
        bt = cluster_mean_test(bvals, bdays)
        for rule in rules:
            kept_ix = {i for i, r in enumerate(base)
                       if passes(rule, r.get(sigkey), cuts.get(r["target_date"])) is True}
            kept = [base[i] for i in sorted(kept_ix)]
            if len(kept) < 2:
                res.append(dict(signal=sigkey, signal_label=label, rule=rule, outcome=oc_id,
                                outcome_label=oc_label, n=len(kept), n_base=len(base),
                                pass_rate=(len(kept) / len(base)) if base else None,
                                insufficient=True))
                continue
            kvals = [r[valkey] for r in kept]
            kdays = [r["target_date"] for r in kept]
            mt = cluster_mean_test(kvals, kdays)
            dt = cluster_diff_test(kvals, kdays, bvals, bdays) if rule != "none" else None
            excl = [r for i, r in enumerate(base) if i not in kept_ix]
            res.append(dict(
                signal=sigkey, signal_label=label, rule=rule, rule_label=RULE_LABEL[rule],
                outcome=oc_id, outcome_label=oc_label,
                n=len(kept), n_base=len(base), n_days=mt["G"], n_days_base=bt["G"],
                pass_rate=round(len(kept) / len(base), 4),
                mean_bp=round(mt["mean"], 2), mean_net_bp=round(mt["mean"] - COST_BP, 2),
                median_bp=round(float(np.median(kvals)), 2),
                win_rate=round(float(np.mean([v > 0 for v in kvals])), 4),
                win_rate_net=round(float(np.mean([v - COST_BP > 0 for v in kvals])), 4),
                se_cluster=(round(mt["se"], 2) if mt["se"] is not None else None),
                t_vs0=(round(mt["t"], 2) if mt["t"] is not None else None),
                p_vs0=(round(mt["p"], 4) if mt["p"] is not None else None),
                base_mean_bp=round(bt["mean"], 2),
                delta_bp=(round(dt["diff"], 2) if dt and dt["diff"] is not None else 0.0),
                delta_se=(round(dt["se"], 2) if dt and dt.get("se") is not None else None),
                delta_t=(round(dt["t"], 2) if dt and dt.get("t") is not None else None),
                delta_p=(round(dt["p"], 4) if dt and dt.get("p") is not None else None),
                delta_krw=(round(dt["diff"] * NOTIONAL / 1e4, 1) if dt and dt["diff"] is not None else 0.0),
                excluded_n=len(excl),
                excluded_mean_bp=(round(float(np.mean([r[valkey] for r in excl])), 2) if len(excl) >= 2 else None),
            ))
    return res




def o_rules_for(tag):
    return _RULES_CACHE[tag]


# --------------------------------------------------------------------------- main
def main():
    daily = load_daily()
    obs_raw = load_obs()
    strength = build_strength(daily)

    tvmap = {}
    for t, rows in daily.items():
        for r in rows:
            tvmap[(t, r["d"])] = r["tv"]

    obs = []
    for o in obs_raw:
        rec = dict(o)
        rec["rs"] = fnum(o["rs"])
        rec["rsi"] = fnum(o["rsi"])
        for k in ("ret_oc_bp", "ret_bo_live_bp", "ret_bo_live_stoplb_bp", "ret_bo_live_stopub_bp",
                  "idx_oc_bp", "idx_cc_bp", "gap_bp", "open", "close", "target_live"):
            rec[k] = fnum(o.get(k))
        rec["breakout_live"] = (o.get("breakout_live") == "True")
        rec["prev_tv"] = tvmap.get((o["ticker"], o["prev_date"]), 0)
        rec["eligible"] = rec["prev_tv"] >= ELIG_TV
        st = strength.get(o["ticker"], {}).get(o["prev_date"], {})
        rec["r1"] = st.get("r1")
        rec["r3x"] = st.get("r3x")
        rec["r5x"] = st.get("r5x")
        obs.append(rec)

    elig = [o for o in obs if o["eligible"]]
    elig_rs = [o for o in elig if o["rs"] is not None]
    days_elig = sorted({o["target_date"] for o in elig})
    days_rs = sorted({o["target_date"] for o in elig_rs})

    out = dict(
        meta=dict(
            cost_bp=COST_BP, notional_krw=NOTIONAL, eligibility="D-1 거래대금 ≥ 500억",
            n_obs_all=len(obs), n_eligible=len(elig), n_eligible_rs=len(elig_rs),
            n_days_eligible=len(days_elig), n_days_rs=len(days_rs),
            rs_first_day=days_rs[0] if days_rs else None, rs_last_day=days_rs[-1] if days_rs else None,
            contaminated_n=len(obs) - len(elig),
            contaminated_share=round((len(obs) - len(elig)) / len(obs), 4),
        ),
    )

    # ---- §1/§2 RS 격자 (강세 + 약세), 적격 ∩ RS 보유
    out["grid_rs"] = eval_grid(elig_rs, "rs", STRONG_RULES + WEAK_RULES, "RS(20일, %p)")

    # 오염 표본 대조 (라벨링용)
    contam_rs = [o for o in obs if not o["eligible"] and o["rs"] is not None]
    out["grid_rs_contaminated"] = eval_grid(contam_rs, "rs", STRONG_RULES, "RS — 오염(부적격)") \
        if len(contam_rs) > 20 else []
    allobs_rs = [o for o in obs if o["rs"] is not None]
    out["grid_rs_alldata"] = eval_grid(allobs_rs, "rs", STRONG_RULES, "RS — 전체(오염 포함)")

    # ---- fail-open 전체 적용 (RS 결측은 통과) : 적격 1,803 기준
    fo = []
    for o in elig:
        o2 = dict(o)
        o2["_sig_present"] = o["rs"] is not None
        fo.append(o2)
    cuts_fo = day_cuts(fo, "rs")
    failopen = []
    for oc_id, valkey, bokey, oc_label in OUTCOMES:
        base = [r for r in fo if (not bokey or r.get(bokey) is True) and r.get(valkey) is not None]
        if len(base) < 2:
            continue
        bvals = [r[valkey] for r in base]; bdays = [r["target_date"] for r in base]
        bt = cluster_mean_test(bvals, bdays)
        for rule in STRONG_RULES:
            kept = [r for r in base
                    if (r["rs"] is None) or (passes(rule, r["rs"], cuts_fo.get(r["target_date"])) is True)]
            if len(kept) < 2:
                continue
            kvals = [r[valkey] for r in kept]; kdays = [r["target_date"] for r in kept]
            mt = cluster_mean_test(kvals, kdays)
            dt = cluster_diff_test(kvals, kdays, bvals, bdays) if rule != "none" else None
            failopen.append(dict(rule=rule, rule_label=RULE_LABEL[rule], outcome=oc_id,
                                 outcome_label=oc_label, n=len(kept), n_base=len(base),
                                 pass_rate=round(len(kept) / len(base), 4),
                                 mean_bp=round(mt["mean"], 2), mean_net_bp=round(mt["mean"] - COST_BP, 2),
                                 p_vs0=(round(mt["p"], 4) if mt["p"] is not None else None),
                                 base_mean_bp=round(bt["mean"], 2),
                                 delta_bp=(round(dt["diff"], 2) if dt else 0.0),
                                 delta_p=(round(dt["p"], 4) if dt and dt.get("p") is not None else None),
                                 delta_krw=(round(dt["diff"] * NOTIONAL / 1e4, 1) if dt else 0.0)))
    out["grid_rs_failopen"] = failopen

    # ---- §6 단기 강도
    out["grid_short"] = []
    for sig, lab in (("r1", "전일 종가 수익률 (%)"), ("r3x", "3일 초과수익 (%p)"), ("r5x", "5일 초과수익 (%p)")):
        rows_full = [o for o in elig if o.get(sig) is not None]
        out["grid_short"] += [dict(scope="적격 전체(37일)", **r)
                              for r in eval_grid(rows_full, sig, STRONG_RULES, lab)]
        rows_rs = [o for o in elig_rs if o.get(sig) is not None]
        out["grid_short"] += [dict(scope="RS 보유 창(23일)", **r)
                              for r in eval_grid(rows_rs, sig, STRONG_RULES, lab)]
    # RS 자신도 같은 두 스코프로 (비교표용)
    out["grid_short"] += [dict(scope="RS 보유 창(23일)", **r)
                          for r in eval_grid(elig_rs, "rs", STRONG_RULES, "RS 20일 (%p)")]

    # ---- §4 안정성
    def subset_grid(rows, tag):
        return [dict(subset=tag, **r) for r in eval_grid(rows, "rs", STRONG_RULES, "RS(20일)")]

    stab = []
    stab += subset_grid([o for o in elig_rs if o["target_date"] <= PRIOR_END], "선행 창(08-03~08-14)")
    stab += subset_grid([o for o in elig_rs if o["target_date"] > PRIOR_END], "신규 창(08-18~09-03)")
    stab += subset_grid([o for o in elig_rs if (o["idx_cc_bp"] or 0) > 0], "지수 상승일(종가기준)")
    stab += subset_grid([o for o in elig_rs if (o["idx_cc_bp"] or 0) <= 0], "지수 하락일(종가기준)")
    stab += subset_grid([o for o in elig_rs if (o["idx_oc_bp"] or 0) > 0], "지수 상승일(시가→종가)")
    stab += subset_grid([o for o in elig_rs if (o["idx_oc_bp"] or 0) <= 0], "지수 하락일(시가→종가)")
    stab += subset_grid(elig_rs, "극단일 포함(전체 23일)")
    stab += subset_grid([o for o in elig_rs if abs(o["idx_cc_bp"] or 0) <= EXTREME_BP], "극단일 제외")
    out["stability"] = stab
    out["extreme_days"] = sorted({o["target_date"] for o in elig_rs if abs(o["idx_cc_bp"] or 0) > EXTREME_BP})

    # ---- §5 검정력
    power = []
    for oc_id, valkey, bokey, oc_label in OUTCOMES:
        base = [r for r in elig_rs if (not bokey or r.get(bokey) is True) and r.get(valkey) is not None]
        if len(base) < 2:
            continue
        cuts = day_cuts(elig_rs, "rs")
        for rule in STRONG_RULES:
            if rule == "none":
                continue
            perday = []
            byday = collections.defaultdict(list)
            for r in base:
                byday[r["target_date"]].append(r)
            for d, rs_ in byday.items():
                kept = [r for r in rs_ if passes(rule, r["rs"], cuts.get(d)) is True]
                if not kept or len(rs_) < 2:
                    continue
                perday.append(float(np.mean([r[valkey] for r in kept])) -
                              float(np.mean([r[valkey] for r in rs_])))
            if len(perday) < 3:
                continue
            mu = float(np.mean(perday)); sd = float(np.std(perday, ddof=1))
            if mu == 0:
                continue
            need = 7.849 * (sd ** 2) / (mu ** 2)     # (1.96+0.8416)^2
            power.append(dict(outcome=oc_id, outcome_label=oc_label, rule=rule,
                              rule_label=RULE_LABEL[rule], days_observed=len(perday),
                              mu_bp=round(mu, 2), sd_bp=round(sd, 2),
                              days_needed_80=int(math.ceil(need)),
                              multiple_of_23=round(need / 23.0, 1),
                              multiple_of_observed=round(need / len(perday), 1)))
    out["power"] = power

    # ---- §7 부수
    supp = dict()
    cuts = day_cuts(elig_rs, "rs")
    br = []
    for rule in ["none"] + STRONG_RULES[1:] + WEAK_RULES:
        kept = [r for r in elig_rs if passes(rule, r["rs"], cuts.get(r["target_date"])) is True]
        if len(kept) < 5:
            continue
        n_bo = sum(1 for r in kept if r["breakout_live"])
        br.append(dict(rule=rule, rule_label=RULE_LABEL[rule], n=len(kept), n_breakout=n_bo,
                       breakout_rate=round(n_bo / len(kept), 4)))
    supp["breakout_rate_by_rule"] = br
    # 분위별 (일별 사분위)
    qrows = collections.defaultdict(list)
    for r in elig_rs:
        c = cuts.get(r["target_date"])
        if c is None:
            continue
        v = r["rs"]
        q = "Q1" if v <= c[0] else ("Q2" if v <= c[1] else ("Q3" if v <= c[2] else "Q4"))
        qrows[q].append(r)
    supp["by_rs_quartile"] = []
    for q in ("Q1", "Q2", "Q3", "Q4"):
        rs_ = qrows.get(q, [])
        if len(rs_) < 5:
            continue
        n_bo = sum(1 for r in rs_ if r["breakout_live"])
        vals = [r["ret_oc_bp"] for r in rs_ if r["ret_oc_bp"] is not None]
        mt = cluster_mean_test(vals, [r["target_date"] for r in rs_ if r["ret_oc_bp"] is not None])
        supp["by_rs_quartile"].append(dict(
            q=q, n=len(rs_), n_breakout=n_bo, breakout_rate=round(n_bo / len(rs_), 4),
            mean_rs=round(float(np.mean([r["rs"] for r in rs_])), 2),
            mean_gap_bp=round(float(np.mean([r["gap_bp"] for r in rs_ if r["gap_bp"] is not None])), 1),
            mean_oc_bp=round(mt["mean"], 2), p_oc=(round(mt["p"], 4) if mt["p"] is not None else None)))
    supp["corr_rs_gap"] = pearson([r["rs"] for r in elig_rs], [r["gap_bp"] for r in elig_rs])
    tgt_over_open = []
    for r in elig_rs:
        if r["target_live"] and r["open"]:
            tgt_over_open.append((r["target_live"] / r["open"] - 1.0) * 1e4)
        else:
            tgt_over_open.append(None)
    supp["corr_rs_target_over_open"] = pearson([r["rs"] for r in elig_rs], tgt_over_open)
    supp["corr_rs_ret_oc"] = pearson([r["rs"] for r in elig_rs], [r["ret_oc_bp"] for r in elig_rs])
    out["supplementary"] = supp

    # ---- §3 실체결 재현
    with open(os.path.join(DATA, "trades_roundtrips.csv"), encoding="utf-8") as fh:
        rts = list(csv.DictReader(fh))
    rt_cuts = day_cuts(elig_rs, "rs")   # 그날 적격∩RS 후보의 사분위 = 라이브에서 쓸 수 있는 컷
    obs_rs = {(o["target_date"], o["ticker"]): o["rs"] for o in obs}
    obs_elig = {(o["target_date"], o["ticker"]): o["eligible"] for o in obs}
    rt_out = {}
    for strat, tag, dmin in (("volatility_breakout", "VB", "2026-07-13"),
                             ("long_tail_volatility", "LTV", "2026-07-13")):
        sub = [r for r in rts if r["strategy"] == strat and r["buy_date"] >= dmin]
        for r in sub:
            key = (r["buy_date"], r["ticker"])
            r["_rs"] = fnum(r["rs"])
            if r["_rs"] is None:
                r["_rs"] = obs_rs.get(key)
            r["_elig"] = obs_elig.get(key)
            r["_gross"] = float(r["gross_pnl_calc"] or 0)
            r["_net"] = float(r["net_pnl_est"] or 0)
        joined = [r for r in sub if r["_rs"] is not None]
        # 일별 컷 (그 날 적격∩RS 후보 기준 — 실제 라이브에서 쓸 수 있는 컷)
        rows = []
        for rule in STRONG_RULES:
            kept, drop = [], []
            for r in sub:
                if r["_rs"] is None:
                    kept.append(r)              # fail-open (조인 실패 = 규칙 평가 불가 → 통과)
                    continue
                ok = passes(rule, r["_rs"], rt_cuts.get(r["buy_date"]))
                (kept if ok is not False else drop).append(r)
            rows.append(dict(
                rule=rule, rule_label=RULE_LABEL[rule],
                n_kept=len(kept), n_dropped=len(drop),
                n_kept_joined=sum(1 for r in kept if r["_rs"] is not None),
                gross_kept=round(sum(r["_gross"] for r in kept)),
                net_kept=round(sum(r["_net"] for r in kept)),
                gross_dropped=round(sum(r["_gross"] for r in drop)),
                net_dropped=round(sum(r["_net"] for r in drop)),
                win_kept=(round(float(np.mean([r["_net"] > 0 for r in kept])), 3) if kept else None),
            ))
        rt_out[tag] = dict(
            n_roundtrips=len(sub), n_joined=len(joined), n_join_fail=len(sub) - len(joined),
            n_join_fail_before_0803=sum(1 for r in sub if r["_rs"] is None and r["buy_date"] < "2026-08-03"),
            n_in_vb_pool=sum(1 for r in sub if r["in_vb_pool"] == "True"),
            n_eligible=sum(1 for r in sub if r["_elig"] is True),
            gross_total=round(sum(r["_gross"] for r in sub)),
            net_total=round(sum(r["_net"] for r in sub)),
            rules=rows,
        )
        # 조인된 것만으로 본 순수 규칙 효과
        rows2 = []
        for rule in STRONG_RULES:
            kix = {i for i, r in enumerate(joined)
                   if passes(rule, r["_rs"], rt_cuts.get(r["buy_date"])) is True}
            kept = [joined[i] for i in sorted(kix)]
            drop = [r for i, r in enumerate(joined) if i not in kix]
            rows2.append(dict(rule=rule, rule_label=RULE_LABEL[rule], n_kept=len(kept), n_dropped=len(drop),
                              gross_kept=round(sum(r["_gross"] for r in kept)),
                              net_kept=round(sum(r["_net"] for r in kept)),
                              gross_dropped=round(sum(r["_gross"] for r in drop)),
                              net_dropped=round(sum(r["_net"] for r in drop))))
        rt_out[tag]["rules_joined_only"] = rows2
    out["roundtrips"] = rt_out


    # ---- §3b 실체결: 수익률 기준 + 무작위 배제 벤치마크 + 동일명목 반사실
    rt_ret = {}
    for strat, tag in (("volatility_breakout", "VB"), ("long_tail_volatility", "LTV")):
        sub = [r for r in rts if r["strategy"] == strat and r["buy_date"] >= "2026-07-13"]
        for r in sub:
            r["_bp"] = float(r["ret_bp"] or 0)
            r["_not"] = float(r["notional"] or 0)
        joined = [r for r in sub if r["_rs"] is not None]
        mean_net_all = float(np.mean([r["_net"] for r in sub]))
        rows = []
        for rule in STRONG_RULES:
            kept_ix = set()
            for i, r in enumerate(sub):
                if r["_rs"] is None:
                    kept_ix.add(i); continue
                if passes(rule, r["_rs"], rt_cuts.get(r["buy_date"])) is not False:
                    kept_ix.add(i)
            kept = [sub[i] for i in sorted(kept_ix)]
            drop = [r for i, r in enumerate(sub) if i not in kept_ix]
            actual_gain = -sum(r["_net"] for r in drop)
            random_gain = -mean_net_all * len(drop)
            # 동일명목 반사실
            eq_all = sum(r["_bp"] for r in sub) * NOTIONAL / 1e4
            eq_keep = sum(r["_bp"] for r in kept) * NOTIONAL / 1e4
            # 초소액(명목 < 50,000원) 제외 민감도
            big = [r for r in sub if r["_not"] >= 50_000]
            bigk = [r for r in kept if r["_not"] >= 50_000]
            eq_all_b = sum(r["_bp"] for r in big) * NOTIONAL / 1e4
            eq_keep_b = sum(r["_bp"] for r in bigk) * NOTIONAL / 1e4
            dt = None
            if len(drop) >= 2 and len(kept) >= 2:
                dt = cluster_diff_test([r["_bp"] for r in kept], [r["buy_date"] for r in kept],
                                       [r["_bp"] for r in drop], [r["buy_date"] for r in drop])
            rows.append(dict(
                rule=rule, rule_label=RULE_LABEL[rule], n_kept=len(kept), n_dropped=len(drop),
                mean_bp_kept=round(float(np.mean([r["_bp"] for r in kept])), 1) if kept else None,
                mean_bp_dropped=round(float(np.mean([r["_bp"] for r in drop])), 1) if drop else None,
                diff_bp=(round(dt["diff"], 1) if dt and dt["diff"] is not None else None),
                diff_p=(round(dt["p"], 3) if dt and dt.get("p") is not None else None),
                net_kept=round(sum(r["_net"] for r in kept)),
                actual_gain=round(actual_gain), random_drop_gain=round(random_gain),
                excess_vs_random=round(actual_gain - random_gain),
                eq_notional_all=round(eq_all), eq_notional_kept=round(eq_keep),
                eq_notional_delta=round(eq_keep - eq_all),
                eq_big_delta=round(eq_keep_b - eq_all_b),
                n_tiny_dropped=sum(1 for r in drop if r["_not"] < 50_000),
            ))
        rt_ret[tag] = dict(mean_net_per_rt=round(mean_net_all), n=len(sub),
                           n_joined=len(joined), rules=rows)
    out["roundtrips_return_based"] = rt_ret
    global _RULES_CACHE
    _RULES_CACHE = {t: v["rules"] for t, v in rt_ret.items()}

    # ---- §3c 순열검정 (동일 유지율 무작위 부분집합) + 비용 규약 정합
    rng = np.random.default_rng(20260906)
    perm = {}
    for tag, strat in (("VB", "volatility_breakout"), ("LTV", "long_tail_volatility")):
        sub = [r for r in rts if r["strategy"] == strat and r["buy_date"] >= "2026-07-13"]
        nets = np.array([r["_net"] for r in sub], float)
        nots = np.array([float(r["notional"] or 0) for r in sub], float)
        fees = np.array([float(r["fees_tax_est"] or 0) for r in sub], float)
        total_not = float(nots.sum())
        implied_bp = float(fees.sum() / total_not * 1e4) if total_not else None
        slip = total_not * (COST_BP - implied_bp) / 1e4 if implied_bp is not None else None
        rows = []
        for r_ in o_rules_for(tag):
            k = r_["n_kept"]
            if k == 0 or k == len(sub):
                continue
            draws = np.array([nets[rng.choice(len(nets), size=k, replace=False)].sum()
                              for _ in range(20000)])
            actual = float(r_["net_kept"])
            pval = float((draws >= actual).mean())
            rows.append(dict(rule=r_["rule"], rule_label=r_["rule_label"], n_kept=k,
                             net_kept=round(actual), rand_mean=round(float(draws.mean())),
                             rand_p95=round(float(np.percentile(draws, 95))),
                             perm_p=round(pval, 4)))
        perm[tag] = dict(rules=rows, implied_cost_bp=(round(implied_bp, 1) if implied_bp else None),
                         total_notional=round(total_not),
                         slippage_at_28bp=(round(slip) if slip else None),
                         net_total_at_28bp=(round(float(nets.sum()) - slip) if slip else None))
    out["permutation"] = perm


    # ---- 교차검증: 풀드 사분위 RS Q4−Q1 (verify_report −55.7bp / p 0.215 대조)
    rsvals = [o["rs"] for o in elig_rs]
    q1c, _, q3c = (float(np.percentile(rsvals, 25)), float(np.percentile(rsvals, 50)),
                   float(np.percentile(rsvals, 75)))
    xcheck = {}
    for oc_id, valkey, bokey, _lab in OUTCOMES:
        hi = [r for r in elig_rs if r["rs"] > q3c and (not bokey or r.get(bokey) is True)
              and r.get(valkey) is not None]
        lo = [r for r in elig_rs if r["rs"] <= q1c and (not bokey or r.get(bokey) is True)
              and r.get(valkey) is not None]
        if len(hi) < 2 or len(lo) < 2:
            continue
        dt = cluster_diff_test([r[valkey] for r in hi], [r["target_date"] for r in hi],
                               [r[valkey] for r in lo], [r["target_date"] for r in lo])
        xcheck[oc_id] = dict(n_q4=len(hi), n_q1=len(lo), q4_minus_q1_bp=round(dt["diff"], 1),
                             p=(round(dt["p"], 4) if dt.get("p") is not None else None),
                             cuts=[round(q1c, 2), round(q3c, 2)])
    out["xcheck_pooled_quartile"] = xcheck

    with open(os.path.join(HERE, "rs_strong.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    import _md
    lines = _md.write_md(out)
    lines = _md.write_md2(out, lines)
    lines = _md.write_md3(out, lines)
    with open(os.path.join(HERE, "counterfactual.md"), "w", encoding="utf-8") as fh:
        import re as _re
        body = "\n".join(lines) + "\n"
        body = _re.sub(r"(?<=[\s|(*])-(?=[0-9])", "\u2212", body)   # 숫자 앞 하이픈 → 마이너스 기호
        fh.write(body)

    print("meta:", json.dumps(out["meta"], ensure_ascii=False))
    print("extreme days:", out["extreme_days"])
    for tag, v in rt_out.items():
        print(tag, "n=%d joined=%d fail=%d gross=%d net=%d" %
              (v["n_roundtrips"], v["n_joined"], v["n_join_fail"], v["gross_total"], v["net_total"]))
    return out


if __name__ == "__main__":
    main()
