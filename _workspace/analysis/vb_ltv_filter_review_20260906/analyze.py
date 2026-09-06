#!/usr/bin/env python3
"""VB 관찰 훅(F-Score/마법공식/RS/RSI) 재검정 + 실체결 연결 — 로컬 분석 (DB 무접촉).

입력: build_dataset.py 산출 (data/funnel_long.csv, data/daily_raw.usv, data/trades_raw.usv)
출력: data/observations.csv · data/daily_summary.csv · data/score_buckets.csv ·
      data/score_tests.csv · data/trades_roundtrips.csv · data/trades_by_bucket.csv ·
      results.json

정렬 규칙 (실측으로 확정):
  - strategy_funnel_snapshots 는 (target_date, strategy_id, step_no) 당 1행 (upsert, 최신 쓰기 승).
    VB step 6~9 는 전부 is_provisional=true, snapshot_at ≈ 07:57~08:03 (첫 INSERT 시각 =
    부팅 직후 첫 _scan_loop 의 자동 캡처; 이후 16:20 저녁 캡처가 같은 행을 덮어쓴다).
  - 저장된 RSI/RS 를 재계산하면 "D-1 까지의 종가 + 당일(D) 스텁 1행(종가=D-1 종가)" 창과
    1e-6 이내로 일치 (RSI 1,440/1,451 · RS 1,444/1,450). 즉 target_date=D 행의 후보·점수는
    D-1 데이터로 만든 **D 거래일용** 후보다 → 성과일 = D (당일). 잠정→익일 정렬은 쓰지 않는다.
  - stock_master_daily 의 D 행은 D 07:55 에 거래량 0 스텁으로 INSERT 되고 D+1 아침에 실값으로
    갱신된다 → 마지막 날(09-04)은 스텁뿐이라 성과일에서 제외. 07-17 은 일봉 자체가 없음(휴장
    또는 결손, 체결도 0건) → 제외. 07-18(토) 스냅샷도 제외.
"""
from __future__ import annotations

import collections
import csv
import json
import math
import os
import statistics
from datetime import date, datetime

import numpy as np
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SEP = "\x1f"

K_MULT = 1.3          # k_value_krx_main (라이브)
K_PERIOD = 15         # 라이브 k_period (strategy_config 09-06 실측; DEFAULT 20 — 기간 중 변경 이력은 미확인)
STOP = -0.05          # -5% 손절
COST_BP = 28.0        # 왕복 수수료 0.015%×2 + 거래세 0.15% + 슬리피지 0.10% = 0.28%
FEE_RT = 0.00015      # 편도 수수료 (실체결 net 추정용; 슬리피지는 체결가에 이미 내재)
TAX = 0.0015          # 매도 거래세
INDEX = "069500"
PRIOR_END = "2026-08-14"   # 선행 창 마지막 거래일 (08-15 토 광복절, 08-17 대체휴일)
NEW_START = "2026-08-18"
MIN_REAL_ROWS_FOR_TRADING_DAY = 500


# ----------------------------------------------------------------------------- load
def load_daily():
    daily = collections.defaultdict(list)
    with open(os.path.join(DATA, "daily_raw.usv"), encoding="utf-8") as fh:
        for line in fh:
            p = line.rstrip("\n").split(SEP)
            if len(p) < 9:
                continue
            t, d, o, h, l, c, v, tv, cr = p
            try:
                row = dict(d=d, o=int(o), h=int(h), l=int(l), c=int(c), v=int(v),
                           tv=int(tv) if tv else 0)
            except ValueError:
                continue
            daily[t].append(row)
    for t in daily:
        daily[t].sort(key=lambda r: r["d"])
    return daily


def load_funnel():
    """target_date -> ticker -> {f_score, mf_rank, rs, rsi, in6}"""
    fun = collections.defaultdict(dict)
    snap_at = {}
    with open(os.path.join(DATA, "funnel_long.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            d = r["target_date"]; t = r["ticker"]; s = r["step_no"]
            rec = fun[d].setdefault(t, {"f_score": None, "mf_rank": None, "rs": None, "rsi": None, "in6": False})
            snap_at.setdefault((d, s), r["snapshot_at_kst"])
            if s == "6":
                rec["in6"] = True
            elif s == "7":
                rec["f_score"] = _num(r["f_score"], int)
                rec["mf_rank"] = _num(r["mf_rank"], int)
            elif s == "8":
                rec["rs"] = _num(r["rs"], float)
            elif s == "9":
                rec["rsi"] = _num(r["rsi"], float)
    return fun, snap_at


def _num(x, typ):
    if x in ("", "None", None):
        return None
    try:
        return typ(float(x))
    except ValueError:
        return None


def load_trades():
    rows = []
    with open(os.path.join(DATA, "trades_raw.usv"), encoding="utf-8") as fh:
        for line in fh:
            p = line.rstrip("\n").split(SEP)
            if len(p) < 11:
                continue
            _id, ts, t, name, typ, px, qty, pnl, status, strat, order_no = p
            rows.append(dict(id=_id, ts=ts, ticker=t, name=name, type=typ, px=float(px),
                             qty=int(qty), pnl=float(pnl or 0), status=status, strategy=strat,
                             order_no=order_no))
    rows.sort(key=lambda r: r["ts"])
    return rows


# ----------------------------------------------------------------------------- helpers
def real(row):
    return row is not None and row["v"] > 0 and row["h"] >= row["l"] and row["o"] > 0


def noise_k(rows):
    vals = []
    for r in rows:
        rng = r["h"] - r["l"]
        if rng > 0:
            vals.append(1 - abs(r["c"] - r["o"]) / rng)
    return (sum(vals) / len(vals)) if vals else None


def bp(a, b):
    return (a / b - 1.0) * 1e4


def cluster_mean_test(vals, clusters):
    """평균 vs 0, 일별 클러스터 표준오차 (G-1 자유도)."""
    n = len(vals)
    if n < 2:
        return dict(n=n, mean=float(np.mean(vals)) if n else None, se=None, t=None, p=None, G=len(set(clusters)))
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
    p = 2 * stats.t.sf(abs(t), df=G - 1) if t is not None else None
    return dict(n=n, mean=m, se=se, t=t, p=p, G=G)


def cluster_diff_test(va, da, vb, db):
    """mean(a) - mean(b), 일별 클러스터 표준오차."""
    na, nb = len(va), len(vb)
    if na < 2 or nb < 2:
        return dict(n_a=na, n_b=nb, diff=None, se=None, t=None, p=None, G=None)
    ma, mb = float(np.mean(va)), float(np.mean(vb))
    infl = collections.defaultdict(float)
    for v, d in zip(va, da):
        infl[d] += (v - ma) / na
    for v, d in zip(vb, db):
        infl[d] -= (v - mb) / nb
    G = len(infl)
    var = sum(x * x for x in infl.values()) * G / (G - 1)
    se = math.sqrt(var) if var > 0 else 0.0
    diff = ma - mb
    t = diff / se if se > 0 else None
    p = 2 * stats.t.sf(abs(t), df=G - 1) if t is not None else None
    return dict(n_a=na, n_b=nb, mean_a=ma, mean_b=mb, diff=diff, se=se, t=t, p=p, G=G)


def quartile_cuts(values):
    arr = np.array([v for v in values if v is not None], dtype=float)
    if len(arr) < 8:
        return None
    return [float(np.percentile(arr, q)) for q in (25, 50, 75)]


def quartile_of(v, cuts):
    if v is None or cuts is None:
        return None
    if v <= cuts[0]:
        return "Q1"
    if v <= cuts[1]:
        return "Q2"
    if v <= cuts[2]:
        return "Q3"
    return "Q4"


def rsi_bin(v):
    if v is None:
        return None
    if v < 30:
        return "<30"
    if v < 50:
        return "30-50"
    if v < 70:
        return "50-70"
    if v <= 85:
        return "70-85"
    return ">85"


def fscore_group(v):
    if v is None:
        return None
    if v <= 2:
        return "0-2"
    if v <= 4:
        return "3-4"
    return "5-7"


def period_of(d):
    return "prior(07-13~08-14)" if d <= PRIOR_END else "new(08-18~09-03)"


def fmt(x, nd=1):
    if x is None or (isinstance(x, float) and (math.isnan(x))):
        return "—"
    return f"{x:.{nd}f}"


# ----------------------------------------------------------------------------- build observations
def build_observations(daily, fun):
    # 거래일 = 실 일봉(거래량>0) 행이 충분한 날
    per_date_real = collections.Counter()
    for t, rows in daily.items():
        for r in rows:
            if real(r):
                per_date_real[r["d"]] += 1
    trading_days = sorted(d for d, n in per_date_real.items() if n >= MIN_REAL_ROWS_FOR_TRADING_DAY)
    tset = set(trading_days)

    idx_rows = {r["d"]: r for r in daily.get(INDEX, []) if real(r)}
    idx_prev_close = {}
    for i, d in enumerate(trading_days):
        if i > 0 and trading_days[i - 1] in idx_rows:
            idx_prev_close[d] = idx_rows[trading_days[i - 1]]["c"]

    obs = []
    skipped = collections.Counter()
    for d in sorted(fun):
        if d not in tset:
            skipped[f"non_trading_or_stub_day:{d}"] += sum(1 for t, r in fun[d].items() if r["in6"])
            continue
        prev_d = trading_days[trading_days.index(d) - 1]
        for t, sc in sorted(fun[d].items()):
            if not sc["in6"]:
                continue
            rows = daily.get(t, [])
            by_d = {r["d"]: r for r in rows}
            rd = by_d.get(d)
            if not real(rd):
                skipped["no_real_D_row"] += 1
                continue
            before = [r for r in rows if r["d"] < d and real(r)]
            if not before:
                skipped["no_prev_row"] += 1
                continue
            prev = before[-1]
            prev_gap = prev["d"] != prev_d
            prev_range = prev["h"] - prev["l"]
            if prev_range <= 0:
                skipped["prev_range_le0"] += 1
                continue
            kn = noise_k(before[-1 - K_PERIOD:-1]) if len(before) >= 6 else None
            o, h, l, c = rd["o"], rd["h"], rd["l"], rd["c"]

            # (a) 무조건 시가→종가
            ret_oc = bp(c, o)
            # (b) 단순 K=1.3 × 전일 range (과제 명세 = 선행 판정과 동일)
            tgt_s = o + K_MULT * prev_range
            bo_s = h >= tgt_s
            ret_bo_s = bp(c, tgt_s) if bo_s else None
            stop_px_s = tgt_s * (1 + STOP)
            stopped_s_ub = bool(bo_s and l <= stop_px_s)          # 상한: 저가 터치 = 손절 (진입 전 터치 포함)
            stopped_s_lb = bool(bo_s and c <= stop_px_s)          # 하한: 종가가 손절선 이하 = 확실한 손절
            ret_bo_s_stop_ub = (STOP * 1e4) if stopped_s_ub else ret_bo_s
            ret_bo_s_stop_lb = (STOP * 1e4) if stopped_s_lb else ret_bo_s
            amb_s = bool(stopped_s_ub and o < stop_px_s)
            # (b') 라이브 충실: target_offset = int(int(range × k_noise) × 1.3)
            if kn is not None:
                tgt_l = o + int(int(prev_range * kn) * K_MULT)
                bo_l = tgt_l > o and h >= tgt_l
                ret_bo_l = bp(c, tgt_l) if bo_l else None
                stop_px_l = tgt_l * (1 + STOP)
                stopped_l_ub = bool(bo_l and l <= stop_px_l)
                stopped_l_lb = bool(bo_l and c <= stop_px_l)
                ret_bo_l_stop_ub = (STOP * 1e4) if stopped_l_ub else ret_bo_l
                ret_bo_l_stop_lb = (STOP * 1e4) if stopped_l_lb else ret_bo_l
                amb_l = bool(stopped_l_ub and o < stop_px_l)
            else:
                tgt_l = None; bo_l = None; ret_bo_l = None; stopped_l_ub = None; stopped_l_lb = None
                ret_bo_l_stop_ub = None; ret_bo_l_stop_lb = None; amb_l = None

            ir = idx_rows.get(d)
            obs.append(dict(
                target_date=d, ticker=t, period=period_of(d), prev_date=prev["d"], prev_gap=prev_gap,
                f_score=sc["f_score"], mf_rank=sc["mf_rank"], rs=sc["rs"], rsi=sc["rsi"],
                open=o, high=h, low=l, close=c, volume=rd["v"],
                prev_high=prev["h"], prev_low=prev["l"], prev_close=prev["c"], prev_range=prev_range,
                k_noise=kn, target_simple=tgt_s, target_live=tgt_l,
                ret_oc_bp=ret_oc, ret_oc_net_bp=ret_oc - COST_BP,
                breakout_simple=bo_s, ret_bo_simple_bp=ret_bo_s,
                ret_bo_simple_net_bp=(ret_bo_s - COST_BP) if ret_bo_s is not None else None,
                stopped_simple_lb=stopped_s_lb, stopped_simple_ub=stopped_s_ub,
                ret_bo_simple_stoplb_bp=ret_bo_s_stop_lb, ret_bo_simple_stopub_bp=ret_bo_s_stop_ub,
                ret_bo_simple_stoplb_net_bp=(ret_bo_s_stop_lb - COST_BP) if ret_bo_s_stop_lb is not None else None,
                stop_ambiguous_simple=amb_s,
                breakout_live=bo_l, ret_bo_live_bp=ret_bo_l,
                ret_bo_live_net_bp=(ret_bo_l - COST_BP) if ret_bo_l is not None else None,
                stopped_live_lb=stopped_l_lb, stopped_live_ub=stopped_l_ub,
                ret_bo_live_stoplb_bp=ret_bo_l_stop_lb, ret_bo_live_stopub_bp=ret_bo_l_stop_ub,
                ret_bo_live_stoplb_net_bp=(ret_bo_l_stop_lb - COST_BP) if ret_bo_l_stop_lb is not None else None,
                stop_ambiguous_live=amb_l,
                idx_oc_bp=bp(ir["c"], ir["o"]) if ir else None,
                idx_cc_bp=bp(ir["c"], idx_prev_close[d]) if (ir and d in idx_prev_close) else None,
                gap_bp=bp(o, prev["c"]),
            ))
    return obs, trading_days, skipped


# ----------------------------------------------------------------------------- score analysis
OUTCOMES = [
    ("ret_oc_bp", "(a) 무조건 시가→종가"),
    ("ret_bo_simple_bp", "(b) K=1.3 돌파 조건부, 종가 청산"),
    ("ret_bo_simple_stoplb_bp", "(b+stop) K=1.3 돌파 조건부, 종가≤손절선이면 -5% 확정(하한 정의)"),
]
SUPP_OUTCOMES = [
    ("ret_bo_simple_stopub_bp", "(b+stop_ub) K=1.3 돌파 조건부, 저가 터치면 -5% (상한 정의, 진입 전 터치 포함)"),
    ("ret_bo_live_bp", "(b') 라이브 목표가(1.3×k_noise×range) 돌파 조건부, 종가 청산"),
    ("ret_bo_live_stoplb_bp", "(b'+stop) 라이브 목표가 돌파 조건부, 종가≤손절선이면 -5%"),
    ("ret_bo_live_stopub_bp", "(b'+stop_ub) 라이브 목표가 돌파 조건부, 저가 터치면 -5%"),
]


def bucket_defs(obs):
    mf_cuts = quartile_cuts([o["mf_rank"] for o in obs])
    rs_cuts = quartile_cuts([o["rs"] for o in obs])
    # RS 일내 4분위 (robustness)
    by_day = collections.defaultdict(list)
    for o in obs:
        if o["rs"] is not None:
            by_day[o["target_date"]].append(o["rs"])
    day_cuts = {d: quartile_cuts(v) for d, v in by_day.items()}

    def f_bucket(o):
        return fscore_group(o["f_score"])

    def mf_bucket(o):
        return quartile_of(o["mf_rank"], mf_cuts)

    def rs_bucket(o):
        return quartile_of(o["rs"], rs_cuts)

    def rs_sign(o):
        return None if o["rs"] is None else ("rs>0" if o["rs"] > 0 else "rs<=0")

    def rs_day_bucket(o):
        return quartile_of(o["rs"], day_cuts.get(o["target_date"]))

    def rsi_b(o):
        return rsi_bin(o["rsi"])

    return {
        "f_score": dict(fn=f_bucket, order=["0-2", "3-4", "5-7"], hi="5-7", lo="0-2",
                        hyp="F-Score 높을수록 유리(+)", cuts=None),
        "mf_rank": dict(fn=mf_bucket, order=["Q1", "Q2", "Q3", "Q4"], hi="Q4", lo="Q1",
                        hyp="Q1=우량(낮은 rank). 가설 = Q4−Q1 < 0", cuts=mf_cuts),
        "rs": dict(fn=rs_bucket, order=["Q1", "Q2", "Q3", "Q4"], hi="Q4", lo="Q1",
                   hyp="Q4=지수 대비 강세. 가설 = Q4−Q1 > 0 (선행 판정: 반대)", cuts=rs_cuts),
        "rs_sign": dict(fn=rs_sign, order=["rs<=0", "rs>0"], hi="rs>0", lo="rs<=0",
                        hyp="rs>0 − rs<=0 > 0", cuts=None),
        "rs_within_day": dict(fn=rs_day_bucket, order=["Q1", "Q2", "Q3", "Q4"], hi="Q4", lo="Q1",
                              hyp="일내 4분위 robustness", cuts=None),
        "rsi": dict(fn=rsi_b, order=["<30", "30-50", "50-70", "70-85", ">85"], hi="70-85", lo="30-50",
                    hyp="과매수(70-85) − 중립(30-50); >85 는 표본 확인", cuts=None),
    }


def analyze_scores(obs, defs, out_buckets, out_tests):
    bucket_rows = []
    test_rows = []
    periods = [("all", lambda o: True),
               ("prior", lambda o: o["period"].startswith("prior")),
               ("new", lambda o: o["period"].startswith("new"))]
    for score, dd in defs.items():
        for out_key, out_label in OUTCOMES + SUPP_OUTCOMES:
            for pname, pf in periods:
                groups = collections.defaultdict(list)
                for o in obs:
                    if not pf(o):
                        continue
                    b = dd["fn"](o)
                    v = o[out_key]
                    if v is None:
                        continue
                    groups[b].append((v, o["target_date"]))
                for b in dd["order"] + [None]:
                    g = groups.get(b, [])
                    if not g:
                        continue
                    vals = [x[0] for x in g]; cl = [x[1] for x in g]
                    mt = cluster_mean_test(vals, cl)
                    bucket_rows.append(dict(
                        score=score, outcome=out_key, period=pname, bucket=("NA" if b is None else b),
                        n=len(vals), n_days=len(set(cl)), n_tickers=None,
                        mean_bp=round(float(np.mean(vals)), 2), median_bp=round(float(np.median(vals)), 2),
                        win_rate=round(float(np.mean([v > 0 for v in vals])), 4),
                        mean_net_bp=round(float(np.mean(vals)) - COST_BP, 2),
                        win_rate_net=round(float(np.mean([v - COST_BP > 0 for v in vals])), 4),
                        se_cluster=(round(mt["se"], 2) if mt["se"] is not None else None),
                        t_vs0=(round(mt["t"], 2) if mt["t"] is not None else None),
                        p_vs0=(round(mt["p"], 4) if mt["p"] is not None else None),
                    ))
                hi = groups.get(dd["hi"], []); lo = groups.get(dd["lo"], [])
                dt = cluster_diff_test([x[0] for x in hi], [x[1] for x in hi],
                                       [x[0] for x in lo], [x[1] for x in lo])
                test_rows.append(dict(
                    score=score, outcome=out_key, period=pname,
                    contrast=f"{dd['hi']} − {dd['lo']}", hypothesis=dd["hyp"],
                    n_hi=dt["n_a"], n_lo=dt["n_b"],
                    mean_hi_bp=(round(dt["mean_a"], 2) if dt.get("mean_a") is not None else None),
                    mean_lo_bp=(round(dt["mean_b"], 2) if dt.get("mean_b") is not None else None),
                    diff_bp=(round(dt["diff"], 2) if dt["diff"] is not None else None),
                    se_cluster=(round(dt["se"], 2) if dt["se"] is not None else None),
                    t=(round(dt["t"], 2) if dt["t"] is not None else None),
                    p=(round(dt["p"], 4) if dt["p"] is not None else None),
                    n_days=dt["G"],
                ))
    with open(out_buckets, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(bucket_rows[0].keys()))
        w.writeheader(); w.writerows(bucket_rows)
    with open(out_tests, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(test_rows[0].keys()))
        w.writeheader(); w.writerows(test_rows)
    return bucket_rows, test_rows


# ----------------------------------------------------------------------------- trades
def build_roundtrips(trades, fun, obs_index, defs):
    open_buys = collections.defaultdict(collections.deque)
    rts = []
    orphans = []
    for r in trades:
        key = (r["strategy"], r["ticker"])
        if r["type"] == "BUY":
            if r["status"] in ("COMPLETED", "PARTIAL"):
                open_buys[key].append(dict(r))
            continue
        if r["type"] == "SELL" and r["status"] == "COMPLETED":
            if not open_buys[key]:
                orphans.append(r)
                continue
            b = open_buys[key].popleft()
            qty = r["qty"]
            gross_calc = (r["px"] - b["px"]) * qty
            fees = FEE_RT * (b["px"] + r["px"]) * qty + TAX * r["px"] * qty
            bd = b["ts"][:10]
            sc = fun.get(bd, {}).get(r["ticker"], {})
            ob = obs_index.get((bd, r["ticker"]))
            rt = dict(
                strategy=r["strategy"], ticker=r["ticker"], name=r["name"],
                buy_ts=b["ts"], buy_px=b["px"], buy_qty=b["qty"], sell_ts=r["ts"], sell_px=r["px"], sell_qty=qty,
                buy_date=bd, sell_date=r["ts"][:10], holding_days=(date.fromisoformat(r["ts"][:10]) - date.fromisoformat(bd)).days,
                gross_pnl_db=r["pnl"], gross_pnl_calc=gross_calc, fees_tax_est=round(fees, 1),
                net_pnl_est=round(r["pnl"] - fees, 1), ret_bp=bp(r["px"], b["px"]),
                notional=b["px"] * qty,
                in_vb_pool=bool(sc.get("in6")), f_score=sc.get("f_score"), mf_rank=sc.get("mf_rank"),
                rs=sc.get("rs"), rsi=sc.get("rsi"),
                f_group=fscore_group(sc.get("f_score")),
                mf_q=quartile_of(sc.get("mf_rank"), defs["mf_rank"]["cuts"]),
                rs_q=quartile_of(sc.get("rs"), defs["rs"]["cuts"]),
                rs_sign=(None if sc.get("rs") is None else ("rs>0" if sc["rs"] > 0 else "rs<=0")),
                rsi_bin=rsi_bin(sc.get("rsi")),
                sim_target_live=(ob["target_live"] if ob else None),
                sim_target_simple=(ob["target_simple"] if ob else None),
                sim_ret_oc_bp=(ob["ret_oc_bp"] if ob else None),
                sim_ret_bo_live_stoplb_bp=(ob["ret_bo_live_stoplb_bp"] if ob else None),
                sim_ret_bo_live_stopub_bp=(ob["ret_bo_live_stopub_bp"] if ob else None),
                sim_stopped_live_lb=(ob["stopped_live_lb"] if ob else None),
                sim_stopped_live_ub=(ob["stopped_live_ub"] if ob else None),
                actual_stop=bool(r["strategy"] == "volatility_breakout" and r["ts"][11:16] < "15:19" and bp(r["px"], b["px"]) <= -400),
                implied_mult_k15=((b["px"] - ob["open"]) / int(ob["prev_range"] * ob["k_noise"])) if (ob and ob["k_noise"] and int(ob["prev_range"] * ob["k_noise"]) > 0) else None,
                entry_vs_target_live_bp=(bp(b["px"], ob["target_live"]) if (ob and ob["target_live"]) else None),
                day_open=(ob["open"] if ob else None), day_close=(ob["close"] if ob else None),
                gap_bp=(ob["gap_bp"] if ob else None),
                entry_vs_target_prevclose_bp=(bp(b["px"], ob["prev_close"] + int(int(ob["prev_range"] * ob["k_noise"]) * K_MULT)) if (ob and ob["k_noise"]) else None),
                entry_vs_open_bp=(bp(b["px"], ob["open"]) if ob else None),
                early_entry=bool(b["ts"][11:19] <= "09:01:30" and b["ts"][11:19] >= "09:00:00"),
                overnight=bool(r["ts"][:10] > bd),
            )
            rts.append(rt)
    return rts, orphans, {k: list(v) for k, v in open_buys.items() if v}


def trades_by_bucket(rts):
    rows = []
    dims = [("f_group", ["0-2", "3-4", "5-7"]), ("mf_q", ["Q1", "Q2", "Q3", "Q4"]),
            ("rs_q", ["Q1", "Q2", "Q3", "Q4"]), ("rs_sign", ["rs<=0", "rs>0"]),
            ("rsi_bin", ["<30", "30-50", "50-70", "70-85", ">85"])]
    for strat in ("volatility_breakout", "long_tail_volatility"):
        sub = [r for r in rts if r["strategy"] == strat]
        rows.append(dict(strategy=strat, dim="ALL", bucket="ALL", n=len(sub),
                         gross_sum=round(sum(r["gross_pnl_db"] for r in sub), 0),
                         net_sum=round(sum(r["net_pnl_est"] for r in sub), 0),
                         mean_ret_bp=(round(statistics.mean(r["ret_bp"] for r in sub), 1) if sub else None),
                         win_rate=(round(sum(r["gross_pnl_db"] > 0 for r in sub) / len(sub), 3) if sub else None)))
        inpool = [r for r in sub if r["in_vb_pool"]]
        rows.append(dict(strategy=strat, dim="in_vb_pool", bucket="True", n=len(inpool),
                         gross_sum=round(sum(r["gross_pnl_db"] for r in inpool), 0),
                         net_sum=round(sum(r["net_pnl_est"] for r in inpool), 0),
                         mean_ret_bp=(round(statistics.mean(r["ret_bp"] for r in inpool), 1) if inpool else None),
                         win_rate=(round(sum(r["gross_pnl_db"] > 0 for r in inpool) / len(inpool), 3) if inpool else None)))
        for dim, order in dims:
            for b in order + [None]:
                g = [r for r in sub if r[dim] == b]
                if not g:
                    continue
                rows.append(dict(strategy=strat, dim=dim, bucket=("NA" if b is None else b), n=len(g),
                                 gross_sum=round(sum(r["gross_pnl_db"] for r in g), 0),
                                 net_sum=round(sum(r["net_pnl_est"] for r in g), 0),
                                 mean_ret_bp=round(statistics.mean(r["ret_bp"] for r in g), 1),
                                 win_rate=round(sum(r["gross_pnl_db"] > 0 for r in g) / len(g), 3)))
    return rows


# ----------------------------------------------------------------------------- daily summary
def daily_summary(obs):
    by_d = collections.defaultdict(list)
    for o in obs:
        by_d[o["target_date"]].append(o)
    rows = []
    for d in sorted(by_d):
        g = by_d[d]
        bo_s = [o for o in g if o["breakout_simple"]]
        bo_l = [o for o in g if o["breakout_live"]]
        rows.append(dict(
            target_date=d, period=period_of(d), n_pool=len(g),
            n_scored_f=sum(1 for o in g if o["f_score"] is not None),
            n_scored_rs=sum(1 for o in g if o["rs"] is not None),
            breakout_rate_simple=round(len(bo_s) / len(g), 4), n_bo_simple=len(bo_s),
            breakout_rate_live=(round(len(bo_l) / sum(1 for o in g if o["breakout_live"] is not None), 4)
                                if any(o["breakout_live"] is not None for o in g) else None), n_bo_live=len(bo_l),
            mean_ret_oc_bp=round(statistics.mean(o["ret_oc_bp"] for o in g), 1),
            mean_ret_bo_simple_bp=(round(statistics.mean(o["ret_bo_simple_bp"] for o in bo_s), 1) if bo_s else None),
            mean_ret_bo_simple_stoplb_bp=(round(statistics.mean(o["ret_bo_simple_stoplb_bp"] for o in bo_s), 1) if bo_s else None),
            mean_ret_bo_live_bp=(round(statistics.mean(o["ret_bo_live_bp"] for o in bo_l), 1) if bo_l else None),
            mean_ret_bo_live_stoplb_bp=(round(statistics.mean(o["ret_bo_live_stoplb_bp"] for o in bo_l), 1) if bo_l else None),
            idx_oc_bp=(round(g[0]["idx_oc_bp"], 1) if g[0]["idx_oc_bp"] is not None else None),
            idx_cc_bp=(round(g[0]["idx_cc_bp"], 1) if g[0]["idx_cc_bp"] is not None else None),
            mean_k_noise=(round(statistics.mean(o["k_noise"] for o in g if o["k_noise"] is not None), 4)
                          if any(o["k_noise"] is not None for o in g) else None),
        ))
    return rows


def corr(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 4:
        return dict(n=len(pairs))
    a = np.array([p[0] for p in pairs]); b = np.array([p[1] for p in pairs])
    pr = stats.pearsonr(a, b); sr = stats.spearmanr(a, b)
    return dict(n=len(pairs), pearson_r=round(float(pr[0]), 3), pearson_p=round(float(pr[1]), 4),
                spearman_rho=round(float(sr[0]), 3), spearman_p=round(float(sr[1]), 4))


# ----------------------------------------------------------------------------- main
def main():
    daily = load_daily()
    fun, snap_at = load_funnel()
    trades = load_trades()

    obs, trading_days, skipped = build_observations(daily, fun)
    with open(os.path.join(DATA, "observations.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(obs[0].keys()))
        w.writeheader(); w.writerows(obs)

    defs = bucket_defs(obs)
    bucket_rows, test_rows = analyze_scores(
        obs, defs, os.path.join(DATA, "score_buckets.csv"), os.path.join(DATA, "score_tests.csv"))

    ds = daily_summary(obs)
    with open(os.path.join(DATA, "daily_summary.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ds[0].keys()))
        w.writeheader(); w.writerows(ds)

    obs_index = {(o["target_date"], o["ticker"]): o for o in obs}
    rts, orphans, unmatched = build_roundtrips(trades, fun, obs_index, defs)
    with open(os.path.join(DATA, "trades_roundtrips.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rts[0].keys()))
        w.writeheader(); w.writerows(rts)
    tb = trades_by_bucket(rts)
    with open(os.path.join(DATA, "trades_by_bucket.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(tb[0].keys()))
        w.writeheader(); w.writerows(tb)

    # ---- headline numbers
    def pool_stats(sub, key):
        vals = [(o[key], o["target_date"]) for o in sub if o[key] is not None]
        if not vals:
            return dict(n=0)
        mt = cluster_mean_test([v for v, _ in vals], [d for _, d in vals])
        return dict(n=mt["n"], n_days=mt["G"], mean_bp=round(mt["mean"], 2),
                    median_bp=round(float(np.median([v for v, _ in vals])), 2),
                    win_rate=round(float(np.mean([v > 0 for v, _ in vals])), 4),
                    mean_net_bp=round(mt["mean"] - COST_BP, 2),
                    se_cluster=(round(mt["se"], 2) if mt["se"] else None),
                    t=(round(mt["t"], 2) if mt["t"] else None), p=(round(mt["p"], 4) if mt["p"] else None))

    headline = {}
    extreme_days = sorted({o["target_date"] for o in obs if o["idx_cc_bp"] is not None and abs(o["idx_cc_bp"]) > 500})
    for pname, sub in (("all", obs), ("prior", [o for o in obs if o["period"].startswith("prior")]),
                       ("new", [o for o in obs if o["period"].startswith("new")]),
                       ("all_ex_extreme_idx_days", [o for o in obs if o["target_date"] not in extreme_days])):
        headline[pname] = {
            "n_obs": len(sub), "n_days": len({o["target_date"] for o in sub}),
            "n_tickers": len({o["ticker"] for o in sub}),
            "n_with_f_score": sum(1 for o in sub if o["f_score"] is not None),
            "n_with_mf_rank": sum(1 for o in sub if o["mf_rank"] is not None),
            "n_with_rs": sum(1 for o in sub if o["rs"] is not None),
            "n_with_rsi": sum(1 for o in sub if o["rsi"] is not None),
            "n_rsi_gt85": sum(1 for o in sub if o["rsi"] is not None and o["rsi"] > 85),
            "breakout_rate_simple": round(float(np.mean([o["breakout_simple"] for o in sub])), 4) if sub else None,
            "breakout_rate_live": (round(float(np.mean([o["breakout_live"] for o in sub if o["breakout_live"] is not None])), 4)
                                   if any(o["breakout_live"] is not None for o in sub) else None),
            "stop_rate_simple_lb_given_breakout": (round(float(np.mean([o["stopped_simple_lb"] for o in sub if o["breakout_simple"]])), 4)
                                                   if any(o["breakout_simple"] for o in sub) else None),
            "stop_rate_simple_ub_given_breakout": (round(float(np.mean([o["stopped_simple_ub"] for o in sub if o["breakout_simple"]])), 4)
                                                   if any(o["breakout_simple"] for o in sub) else None),
            "stop_ambiguous_share_simple_ub": (round(float(np.mean([o["stop_ambiguous_simple"] for o in sub if o["stopped_simple_ub"]])), 4)
                                               if any(o["stopped_simple_ub"] for o in sub) else None),
            "stop_rate_live_lb_given_breakout": (round(float(np.mean([o["stopped_live_lb"] for o in sub if o["breakout_live"]])), 4)
                                                 if any(o["breakout_live"] for o in sub) else None),
            "stop_rate_live_ub_given_breakout": (round(float(np.mean([o["stopped_live_ub"] for o in sub if o["breakout_live"]])), 4)
                                                 if any(o["breakout_live"] for o in sub) else None),
            "ret_oc": pool_stats(sub, "ret_oc_bp"),
            "ret_bo_simple": pool_stats(sub, "ret_bo_simple_bp"),
            "ret_bo_simple_stoplb": pool_stats(sub, "ret_bo_simple_stoplb_bp"),
            "ret_bo_simple_stopub": pool_stats(sub, "ret_bo_simple_stopub_bp"),
            "ret_bo_live": pool_stats(sub, "ret_bo_live_bp"),
            "ret_bo_live_stoplb": pool_stats(sub, "ret_bo_live_stoplb_bp"),
            "ret_bo_live_stopub": pool_stats(sub, "ret_bo_live_stopub_bp"),
            "mean_k_noise": (round(float(np.mean([o["k_noise"] for o in sub if o["k_noise"] is not None])), 4) if sub else None),
        }

    # regime correlations (일별)
    reg = {
        "mean_bo_simple_vs_idx_cc": corr([r["mean_ret_bo_simple_bp"] for r in ds], [r["idx_cc_bp"] for r in ds]),
        "mean_bo_simple_vs_idx_cc_ex_extreme": corr([r["mean_ret_bo_simple_bp"] for r in ds if r["target_date"] not in extreme_days], [r["idx_cc_bp"] for r in ds if r["target_date"] not in extreme_days]),
        "mean_bo_simple_vs_idx_oc": corr([r["mean_ret_bo_simple_bp"] for r in ds], [r["idx_oc_bp"] for r in ds]),
        "mean_bo_live_vs_idx_cc": corr([r["mean_ret_bo_live_bp"] for r in ds], [r["idx_cc_bp"] for r in ds]),
        "mean_oc_vs_idx_oc": corr([r["mean_ret_oc_bp"] for r in ds], [r["idx_oc_bp"] for r in ds]),
        "breakout_rate_simple_vs_idx_cc": corr([r["breakout_rate_simple"] for r in ds], [r["idx_cc_bp"] for r in ds]),
        "pool_size_vs_idx_cc_prev": None,
    }
    # 일별 돌파 조건부 수익 분포
    bo_days = [r["mean_ret_bo_simple_bp"] for r in ds if r["mean_ret_bo_simple_bp"] is not None]
    reg["daily_mean_bo_simple_distribution"] = dict(
        n_days=len(bo_days), mean=round(float(np.mean(bo_days)), 1), median=round(float(np.median(bo_days)), 1),
        p10=round(float(np.percentile(bo_days, 10)), 1), p90=round(float(np.percentile(bo_days, 90)), 1),
        share_days_positive=round(float(np.mean([x > 0 for x in bo_days])), 3),
        share_days_positive_net=round(float(np.mean([x - COST_BP > 0 for x in bo_days])), 3),
    )
    idx_up = [r for r in ds if r["idx_cc_bp"] is not None and r["idx_cc_bp"] > 0 and r["mean_ret_bo_simple_bp"] is not None]
    idx_dn = [r for r in ds if r["idx_cc_bp"] is not None and r["idx_cc_bp"] <= 0 and r["mean_ret_bo_simple_bp"] is not None]
    reg["bo_simple_by_index_day"] = dict(
        idx_up_days=len(idx_up), idx_up_mean_bp=(round(float(np.mean([r["mean_ret_bo_simple_bp"] for r in idx_up])), 1) if idx_up else None),
        idx_down_days=len(idx_dn), idx_down_mean_bp=(round(float(np.mean([r["mean_ret_bo_simple_bp"] for r in idx_dn])), 1) if idx_dn else None),
    )

    # trades headline
    def tsum(sub):
        return dict(n=len(sub), gross_sum=round(sum(r["gross_pnl_db"] for r in sub), 0),
                    net_sum_est=round(sum(r["net_pnl_est"] for r in sub), 0),
                    fees_tax_est=round(sum(r["fees_tax_est"] for r in sub), 0),
                    mean_ret_bp=(round(statistics.mean(r["ret_bp"] for r in sub), 1) if sub else None),
                    win_rate=(round(sum(r["gross_pnl_db"] > 0 for r in sub) / len(sub), 3) if sub else None),
                    in_vb_pool=sum(1 for r in sub if r["in_vb_pool"]),
                    with_any_score=sum(1 for r in sub if r["f_score"] is not None or r["rs"] is not None))
    vb_rts = [r for r in rts if r["strategy"] == "volatility_breakout"]
    ltv_rts = [r for r in rts if r["strategy"] == "long_tail_volatility"]
    vb_since = [r for r in vb_rts if r["buy_date"] >= "2026-07-13"]
    trades_head = {
        "vb_all_since_0701": tsum(vb_rts), "ltv_all_since_0701": tsum(ltv_rts),
        "vb_since_0713_funnel_available": tsum(vb_since),
        "vb_since_0818": tsum([r for r in vb_rts if r["buy_date"] >= NEW_START]),
        "ltv_since_0818": tsum([r for r in ltv_rts if r["buy_date"] >= NEW_START]),
        "vb_not_in_pool_examples": [dict(d=r["buy_date"], t=r["ticker"], name=r["name"]) for r in vb_since if not r["in_vb_pool"]][:20],
        "orphan_sells": len(orphans), "unmatched_buys": sum(len(v) for v in unmatched.values()),
        "vb_entry_vs_target_live_bp": (lambda v: dict(n=len(v), mean=round(float(np.mean(v)), 1), median=round(float(np.median(v)), 1))
                                       if v else dict(n=0))([r["entry_vs_target_live_bp"] for r in vb_rts if r["entry_vs_target_live_bp"] is not None]),
        "vb_sim_vs_actual": (lambda pairs: dict(n=len(pairs), mean_actual_bp=round(float(np.mean([p[0] for p in pairs])), 1),
                                                mean_sim_live_stoplb_bp=round(float(np.mean([p[1] for p in pairs])), 1),
                                                mean_sim_live_stopub_bp=round(float(np.mean([p[2] for p in pairs])), 1),
                                                corr_lb=(round(float(np.corrcoef([p[0] for p in pairs], [p[1] for p in pairs])[0, 1]), 3) if len(pairs) > 3 else None))
                             if pairs else dict(n=0))([(r["ret_bp"], r["sim_ret_bo_live_stoplb_bp"], r["sim_ret_bo_live_stopub_bp"]) for r in vb_rts if r["sim_ret_bo_live_stoplb_bp"] is not None]),
        "vb_actual_stop_calibration": (lambda sub: dict(
            n=len(sub), actual_stop_rate=round(sum(r["actual_stop"] for r in sub) / len(sub), 3) if sub else None,
            sim_lb_rate=round(sum(bool(r["sim_stopped_live_lb"]) for r in sub) / len(sub), 3) if sub else None,
            sim_ub_rate=round(sum(bool(r["sim_stopped_live_ub"]) for r in sub) / len(sub), 3) if sub else None,
            agree_lb=round(sum((r["actual_stop"] == bool(r["sim_stopped_live_lb"])) for r in sub) / len(sub), 3) if sub else None,
            agree_ub=round(sum((r["actual_stop"] == bool(r["sim_stopped_live_ub"])) for r in sub) / len(sub), 3) if sub else None,
        ))([r for r in vb_rts if r["sim_stopped_live_lb"] is not None]),
        "vb_actual_stop_rate_all": round(sum(r["actual_stop"] for r in vb_rts) / len(vb_rts), 3) if vb_rts else None,
        "orphan_sell_detail": [dict(ts=o["ts"], ticker=o["ticker"], name=o["name"], px=o["px"], qty=o["qty"], pnl=o["pnl"]) for o in orphans],
        "vb_gross_reconciled_incl_orphan": round(sum(r["gross_pnl_db"] for r in vb_rts) + sum(o["pnl"] for o in orphans if o["strategy"] == "volatility_breakout"), 0),
        "vb_entry_timing": {
            "early(<=09:01:30)": tsum([r for r in vb_rts if r["early_entry"]]),
            "later": tsum([r for r in vb_rts if not r["early_entry"]]),
            "early_since_0713": tsum([r for r in vb_since if r["early_entry"]]),
            "later_since_0713": tsum([r for r in vb_since if not r["early_entry"]]),
            "early_gap_bp_mean": (lambda v: round(float(np.mean(v)), 1) if v else None)([r["gap_bp"] for r in vb_rts if r["early_entry"] and r["gap_bp"] is not None]),
            "later_gap_bp_mean": (lambda v: round(float(np.mean(v)), 1) if v else None)([r["gap_bp"] for r in vb_rts if not r["early_entry"] and r["gap_bp"] is not None]),
            "early_entry_vs_target_live_bp_median": (lambda v: round(float(np.median(v)), 1) if v else None)([r["entry_vs_target_live_bp"] for r in vb_rts if r["early_entry"] and r["entry_vs_target_live_bp"] is not None]),
            "early_entry_vs_target_prevclose_bp": (lambda v: dict(n=len(v), median=round(float(np.median(v)), 1), p25=round(float(np.percentile(v, 25)), 1), p75=round(float(np.percentile(v, 75)), 1)) if v else dict(n=0))([r["entry_vs_target_prevclose_bp"] for r in vb_rts if r["early_entry"] and r["entry_vs_target_prevclose_bp"] is not None]),
            "later_entry_vs_target_prevclose_bp": (lambda v: dict(n=len(v), median=round(float(np.median(v)), 1), p25=round(float(np.percentile(v, 25)), 1), p75=round(float(np.percentile(v, 75)), 1)) if v else dict(n=0))([r["entry_vs_target_prevclose_bp"] for r in vb_rts if not r["early_entry"] and r["entry_vs_target_prevclose_bp"] is not None]),
            "later_entry_vs_target_live_bp": (lambda v: dict(n=len(v), median=round(float(np.median(v)), 1), p25=round(float(np.percentile(v, 25)), 1), p75=round(float(np.percentile(v, 75)), 1)) if v else dict(n=0))([r["entry_vs_target_live_bp"] for r in vb_rts if not r["early_entry"] and r["entry_vs_target_live_bp"] is not None]),
            "early_entry_vs_open_bp_median": (lambda v: round(float(np.median(v)), 1) if v else None)([r["entry_vs_open_bp"] for r in vb_rts if r["early_entry"] and r["entry_vs_open_bp"] is not None]),
        },
        "vb_overnight_roundtrips": tsum([r for r in vb_rts if r["overnight"]]),
        "vb_actual_stops": tsum([r for r in vb_rts if r["actual_stop"]]),
        "ltv_overnight_roundtrips": tsum([r for r in ltv_rts if r["overnight"]]),
        "vb_implied_mult_k15": (lambda v: dict(n=len(v), median=round(float(np.median(v)), 3), p25=round(float(np.percentile(v, 25)), 3), p75=round(float(np.percentile(v, 75)), 3))
                                if v else dict(n=0))([r["implied_mult_k15"] for r in vb_rts if r["implied_mult_k15"] is not None]),
    }

    results = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "alignment_rule": {
            "rule": "target_date=D 행 = D 거래일용 후보(점수는 D-1 데이터) → 성과일 = D(당일)",
            "evidence": "저장 RSI/RS 재계산: 'D-1 종가 + 당일 스텁' 창과 1e-6 일치 RSI 1440/1451, RS 1444/1450",
            "snapshot_rows": len(snap_at), "all_provisional": True,
            "snapshot_time_range_kst": sorted(set(v[11:16] for v in snap_at.values()))[:3] + ["..."] + sorted(set(v[11:16] for v in snap_at.values()))[-3:],
            "excluded_days": {"2026-07-17": "일봉 0행(휴장/결손, 체결 0건)", "2026-07-18": "토요일 스냅샷", "2026-09-04": "일봉이 스텁(거래량 0)만 존재"},
            "skipped_counts": dict(skipped),
        },
        "params": dict(K_MULT=K_MULT, K_PERIOD=K_PERIOD, STOP=STOP, COST_BP=COST_BP, FEE_RT=FEE_RT, TAX=TAX, INDEX=INDEX,
                       prior_window="2026-07-13~2026-08-14 (거래일)", new_window="2026-08-18~2026-09-03 (거래일)"),
        "trading_days_in_scope": [d for d in trading_days if "2026-07-13" <= d <= "2026-09-03"],
        "headline": headline,
        "extreme_index_days_abs_gt_500bp": extreme_days,
        "quartile_cuts": {"mf_rank": defs["mf_rank"]["cuts"], "rs": defs["rs"]["cuts"]},
        "score_tests_primary": [t for t in test_rows if t["outcome"] in [o[0] for o in OUTCOMES] and t["score"] in ("f_score", "mf_rank", "rs", "rsi")],
        "score_tests_all": test_rows,
        "regime": reg,
        "trades": trades_head,
        "bonferroni_alpha_12": round(0.05 / 12, 4),
        "comparison_to_prior": {
            "n_obs": {"prior_judgment": 1498, "now_all": len(obs), "now_prior_window": headline["prior"]["n_obs"], "now_new_window": headline["new"]["n_obs"]},
            "n_tickers": {"prior_judgment": 195, "now_all": headline["all"]["n_tickers"]},
            "alignment": {"prior_judgment": "잠정(16:20)→익일 / 확정(09:30)→당일", "now": "target_date=D → 당일 D (RSI/RS 재계산으로 실측 확정; 저장 행은 전부 provisional 1행/일)"},
            "pool_oc_bp": {"prior_judgment": -11.5, "now_all": headline["all"]["ret_oc"]["mean_bp"], "now_prior_window": headline["prior"]["ret_oc"]["mean_bp"], "now_new_window": headline["new"]["ret_oc"]["mean_bp"]},
            "breakout_conditional_bp_K1.3": {"prior_judgment": -41.9, "now_all": headline["all"]["ret_bo_simple"]["mean_bp"], "now_prior_window": headline["prior"]["ret_bo_simple"]["mean_bp"], "now_new_window": headline["new"]["ret_bo_simple"]["mean_bp"], "now_all_net": headline["all"]["ret_bo_simple"]["mean_net_bp"]},
            "breakout_conditional_bp_live_target": {"now_all": headline["all"]["ret_bo_live"]["mean_bp"], "now_all_net": headline["all"]["ret_bo_live"]["mean_net_bp"], "now_new_window": headline["new"]["ret_bo_live"]["mean_bp"]},
            "rs_q1_q4_oc_bp": {"prior_judgment": {"Q1": 91.1, "Q4": 34.7, "t": -1.73, "p": 0.08},
                                "now_all": next({"Q1": t["mean_lo_bp"], "Q4": t["mean_hi_bp"], "t": t["t"], "p": t["p"]} for t in test_rows if t["score"] == "rs" and t["outcome"] == "ret_oc_bp" and t["period"] == "all"),
                                "now_prior_window": next({"Q1": t["mean_lo_bp"], "Q4": t["mean_hi_bp"], "t": t["t"], "p": t["p"]} for t in test_rows if t["score"] == "rs" and t["outcome"] == "ret_oc_bp" and t["period"] == "prior"),
                                "now_new_window": next({"Q1": t["mean_lo_bp"], "Q4": t["mean_hi_bp"], "t": t["t"], "p": t["p"]} for t in test_rows if t["score"] == "rs" and t["outcome"] == "ret_oc_bp" and t["period"] == "new")},
            "rsi_gt85_count": {"prior_judgment": 0, "now_all": headline["all"]["n_rsi_gt85"]},
            "fscore_mf_p_range": {"prior_judgment": "0.29~0.95",
                                   "now_primary_all": [round(min(float(t["p"]) for t in test_rows if t["score"] in ("f_score", "mf_rank") and t["period"] == "all" and t["outcome"] in [o[0] for o in OUTCOMES] and t["p"] is not None), 3),
                                                        round(max(float(t["p"]) for t in test_rows if t["score"] in ("f_score", "mf_rank") and t["period"] == "all" and t["outcome"] in [o[0] for o in OUTCOMES] and t["p"] is not None), 3)]},
            "primary_12_tests_min_p": round(min(float(t["p"]) for t in test_rows if t["period"] == "all" and t["score"] in ("f_score", "mf_rank", "rs", "rsi") and t["outcome"] in [o[0] for o in OUTCOMES]), 4),
        },
        "prior_judgment_2026_08_18": {
            "n_obs": 1498, "n_tickers": 195, "rs_q1_bp": 91.1, "rs_q4_bp": 34.7, "rs_t": -1.73, "rs_p": 0.08,
            "rsi_gt85": 0, "fscore_mf_p_range": "0.29~0.95", "pool_oc_bp": -11.5, "breakout_conditional_bp": -41.9,
            "alignment": "잠정(16:20)→익일 / 확정(09:30)→당일 (당시 가정)",
        },
    }
    with open(os.path.join(HERE, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(results["headline"]["all"], ensure_ascii=False, indent=1))
    print("tests(primary):")
    for t in results["score_tests_primary"]:
        if True:
            print(f'  {t["score"]:8s} {t["outcome"]:24s} {t["contrast"]:14s} hi={fmt(t["mean_hi_bp"])} lo={fmt(t["mean_lo_bp"])} diff={fmt(t["diff_bp"])} t={fmt(t["t"],2)} p={fmt(t["p"],3)} n={t["n_hi"]}/{t["n_lo"]} G={t["n_days"]}')
    print("trades:", json.dumps(trades_head, ensure_ascii=False, default=str)[:1500])
    print("regime:", json.dumps(reg, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
