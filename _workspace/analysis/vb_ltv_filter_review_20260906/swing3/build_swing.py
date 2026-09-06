#!/usr/bin/env python3
"""스윙 3전략(donchian_swing · kojiro · vcp_breakout) 후보-레벨 관측 테이블 빌더.

입력  = extract.py 가 내려받은 data/*.usv (운영 DB SELECT 결과, 읽기 전용)
출력  = data/swing_obs.csv · data/swing_trades.csv · data/coverage.csv
        (+ data/gate_corr.csv 기존 게이트 ↔ 신규 점수 상관)

정의는 전부 리포 코드에서 읽어 재현했다 (아래 상수 블록의 출처 주석 참조).
근사한 부분은 컬럼명 접미사와 coverage.csv 의 note 에 명시한다.
"""
from __future__ import annotations

import csv
import json
import math
import os
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SEP = "\x1f"

# ─────────────────────────────────────────────────────────────────────────────
# 상수 — 전부 운영 DB strategy_config(라이브) + 코드 DEFAULT_PARAMS 실측 (2026-09-06)
# ─────────────────────────────────────────────────────────────────────────────
COST_BP = 28.0          # 왕복 수수료 0.015%×2 + 거래세 0.15% + 슬리피지 10bp
INDEX_TICKER = "069500"  # KODEX200 — ta_indicators.relative_strength 지수 소스
RS_PERIOD = 20           # ta_indicators.relative_strength(period=20)
RSI_PERIOD = 14          # ta_indicators.rsi(period=14) Wilder
HOLD_HORIZONS = (3, 5, 10, 20)
MAX_SIM_DAYS = 30        # 규약 근사 시뮬레이션 상한 (거래일)

# 후보 풀 = (전략, step_no) → 라벨.  step_name 은 funnel_raw 에서 확인한 실측 라벨.
POOLS = {
    "donchian_swing": [(9, "final"), (5, "wide")],       # 9=최종 후보 / 5=신고가 돌파
    "kojiro":         [(9, "final"), (7, "wide")],       # 9=최종 후보 / 7=스테이지1+3선 우상향
    "vcp_breakout":   [(9, "final"), (6, "wide"), (5, "wide2")],  # 9=최종 / 6=베이스 검출 / 5=EMA정렬
}

# 라이브 파라미터 (strategy_config, [DB 09-06]) — 청산 규약 근사에 쓰는 값만
LIVE = {
    "donchian_swing": dict(
        sizing_mode="turtle", atr_period=14, atr_kind="sma",  # strategy_base._atr = TR 단순평균
        stop_atr=2.0, turtle_backstop_pct=-9.0, breakeven_promote_atr=1.5,
        atr_trail_mult=1.8, stop_loss_rate=-6.0, breakout_fail_n_days=2,
        channel_exit_period=10, donchian_period=20, max_positions=3,
    ),
    "kojiro": dict(
        sizing_mode="turtle", atr_period=20, atr_kind="wilder",  # kojiro_indicators.atr ewm(1/20)
        stop_atr=2.0, hard_stop_pct=-8.0, breakeven_promote_atr=0.0,
        trail_atr=2.5, ema_short=5, ema_mid=20, ema_long=40, max_positions=6,
    ),
    "vcp_breakout": dict(
        sizing_mode="position_ratio", atr_period=14, atr_kind="sma",
        stop_loss_rate=-7.0, breakeven_promote_atr=1.5, atr_trail_mult=2.0,
        ema_short=50, max_positions=5,
    ),
}

FIN_FIRST_LOAD = "2026-07-15"   # stock_master_financial 최초 적재일 [DB 09-06]
FIN_LAST_LOAD = "2026-08-12"    # 마지막 갱신일 (그 뒤 갱신 0건)


# ─────────────────────────────────────────────────────────────────────────────
# 로더
# ─────────────────────────────────────────────────────────────────────────────
def read_usv(name):
    path = os.path.join(DATA, name)
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line:
                yield line.split(SEP)


def f(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


# ── 일봉 ─────────────────────────────────────────────────────────────────────
def load_daily():
    """ticker -> {dates:[], o/h/l/c/v/tv: np.array}  (bas_dd 오름차순)"""
    tmp = defaultdict(list)
    for r in read_usv("daily_raw.usv"):
        t, dd = r[0], r[1]
        o, h, l, c = f(r[2]), f(r[3]), f(r[4]), f(r[5])
        v, tv = f(r[6]), f(r[7])
        cre = r[9] if len(r) > 9 else ""
        if c is None or c <= 0:
            continue
        tmp[t].append((dd, o, h, l, c, v or 0.0, tv or 0.0, cre))
    out = {}
    for t, rows in tmp.items():
        rows.sort(key=lambda x: x[0])
        out[t] = {
            "dates": [r[0] for r in rows],
            "idx": {r[0]: i for i, r in enumerate(rows)},
            "o": np.array([r[1] if r[1] else r[4] for r in rows], float),
            "h": np.array([r[2] if r[2] else r[4] for r in rows], float),
            "l": np.array([r[3] if r[3] else r[4] for r in rows], float),
            "c": np.array([r[4] for r in rows], float),
            "v": np.array([r[5] for r in rows], float),
            "tv": np.array([r[6] for r in rows], float),
            # created_at(KST 날짜) — 그 행이 DB 에 처음 들어온 날. 과거 bas_dd 행이
            # 나중 날짜에 backfill 되므로 "그날 엔진이 실제로 볼 수 있던 시리즈"
            # 재구성(PIT)의 유일한 근거다.
            "cre": [r[7] for r in rows],
        }
    return out


# ── 지표 (코드 정의 재현) ────────────────────────────────────────────────────
def rsi_wilder(closes, period=RSI_PERIOD):
    """src/engine/ta_indicators.py::rsi 재현 (Wilder)."""
    if closes is None or len(closes) < period + 1:
        return None
    d = np.diff(closes)
    g = np.where(d > 0, d, 0.0)
    ls = np.where(d < 0, -d, 0.0)
    ag, al = g[:period].mean(), ls[:period].mean()
    for i in range(period, len(d)):
        ag = (ag * (period - 1) + g[i]) / period
        al = (al * (period - 1) + ls[i]) / period
    if al == 0:
        return 100.0 if ag > 0 else 50.0
    if ag == 0:
        return 0.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def rel_strength(s, ix, period=RS_PERIOD):
    """src/engine/ta_indicators.py::relative_strength 재현 (%p)."""
    if s is None or ix is None or len(s) < period + 1 or len(ix) < period + 1:
        return None
    sb, ib = s[-1 - period], ix[-1 - period]
    if sb == 0 or ib == 0:
        return None
    return ((s[-1] - sb) / sb - (ix[-1] - ib) / ib) * 100.0


def atr_sma(h, l, c, period):
    """strategy_base._atr 재현 — 최근 period 일 TR 단순평균 (donchian/VCP/BFB 공유)."""
    n = len(c)
    if n < period + 2:
        return None
    trs = []
    for i in range(n - 1, n - 1 - period, -1):
        trs.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return float(np.mean(trs))


def atr_wilder(h, l, c, period):
    """kojiro_indicators.atr 재현 — TR 의 ewm(alpha=1/period, adjust=False)."""
    n = len(c)
    if n < period + 2:
        return None
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    tr[1:] = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])
    a = 1.0 / period
    v = tr[0]
    for i in range(1, n):
        v = a * tr[i] + (1 - a) * v
    return float(v)


def ema_series(x, span):
    a = 2.0 / (span + 1.0)
    out = np.empty(len(x))
    v = x[0]
    out[0] = v
    for i in range(1, len(x)):
        v = a * x[i] + (1 - a) * v
        out[i] = v
    return out


_STAGE_MAP = {("s", "m", "l"): 1, ("m", "s", "l"): 2, ("m", "l", "s"): 3,
              ("l", "m", "s"): 4, ("l", "s", "m"): 5, ("s", "l", "m"): 6}


def stage_of(s, m, l, prev=None):
    """kojiro_indicators.stage_of 재현."""
    if s == m or m == l or s == l:
        return prev
    trio = sorted([("s", s), ("m", m), ("l", l)], key=lambda x: -x[1])
    return _STAGE_MAP.get(tuple(n for n, _ in trio), prev)


# ── 재무 (quant_score.py 재현) ───────────────────────────────────────────────
FIN_COLS = ["sale_account", "sale_totl_prfi", "bsop_prti", "thtr_ntin", "depr_cost",
            "cras", "fxas", "total_aset", "flow_lblt", "total_lblt", "total_cptl",
            "cpfn", "cptl_ntin_rate", "sale_totl_rate", "lblt_rate", "crnt_rate",
            "ebitda", "ev_ebitda"]


def load_financials():
    """ticker -> [ (stac_yymm, {col: val}) ... ]  div_cls='0'(연간), stac_yymm DESC"""
    by = defaultdict(list)
    for r in read_usv("fin_raw.usv"):
        t, ym, dc = r[0], r[1], r[2]
        if dc != "0":
            continue
        rec = {c: f(r[3 + i]) for i, c in enumerate(FIN_COLS)}
        by[t].append((ym, rec))
    for t in by:
        by[t].sort(key=lambda x: x[0], reverse=True)
    return by


def compute_f_score_7(curr, prev):
    """src/engine/quant_score.py::compute_f_score_7 재현."""
    if curr is None or prev is None:
        return None
    pk = ("cptl_ntin_rate", "lblt_rate", "crnt_rate", "sale_totl_rate",
          "sale_account", "total_aset", "cpfn")
    if all(prev.get(k) is None for k in pk):
        return None
    s = 0
    croa, proa = curr.get("cptl_ntin_rate"), prev.get("cptl_ntin_rate")
    if croa is not None and croa > 0:
        s += 1
    if croa is not None and proa is not None and croa > proa:
        s += 1
    cl, pl = curr.get("lblt_rate"), prev.get("lblt_rate")
    if cl is not None and pl is not None and cl < pl:
        s += 1
    cc, pc = curr.get("crnt_rate"), prev.get("crnt_rate")
    if cc is not None and pc is not None and cc > pc:
        s += 1
    cg, pg = curr.get("sale_totl_rate"), prev.get("sale_totl_rate")
    if cg is not None and pg is not None and cg > pg:
        s += 1
    cs, ca = curr.get("sale_account"), curr.get("total_aset")
    ps, pa = prev.get("sale_account"), prev.get("total_aset")
    if (cs is not None and ca is not None and ca > 0 and ps is not None
            and pa is not None and pa > 0 and cs / ca > ps / pa):
        s += 1
    cf, pf = curr.get("cpfn"), prev.get("cpfn")
    if cf is not None and pf is not None and cf <= pf:
        s += 1
    return int(s)


def compute_ey(fin, mktcap):
    """quant_score._compute_ey 재현."""
    ev_ebitda = fin.get("ev_ebitda")
    if ev_ebitda is not None and ev_ebitda > 0:
        return 1.0 / ev_ebitda
    bsop = fin.get("bsop_prti")
    ev = (mktcap or 0.0) + (fin.get("total_lblt") or 0.0)
    if bsop is not None and ev > 0:
        return bsop / ev
    return None


def compute_roc(fin):
    """quant_score._compute_roc 재현."""
    b, cr, fl, fx = (fin.get("bsop_prti"), fin.get("cras"),
                     fin.get("flow_lblt"), fin.get("fxas"))
    if b is None or cr is None or fl is None or fx is None:
        return None
    den = (cr - fl) + fx
    return None if den <= 0 else b / den


def rank_desc(vals):
    """quant_score._rank_descending 재현 (None 최하위, ticker 오름차순 tie-break)."""
    tk = sorted(vals)
    ranked = sorted(tk, key=lambda t: (vals[t] is None,
                                       -(vals[t]) if vals[t] is not None else 0.0, t))
    return {t: i + 1 for i, t in enumerate(ranked)}


# ─────────────────────────────────────────────────────────────────────────────
def main():
    daily = load_daily()
    fins = load_financials()

    master = {}
    for r in read_usv("master_raw.usv"):
        master[r[0]] = dict(name=r[1], mcap_eok=f(r[2]) or 0.0, tv_won=f(r[3]) or 0.0,
                            k200=r[4] == "true", kq150=r[5] == "true")

    # 거래일 달력 = KODEX200(069500) 일봉 (ETF — 전 세션 체결)
    if INDEX_TICKER not in daily:
        raise SystemExit("index 069500 daily missing")
    cal = daily[INDEX_TICKER]["dates"]
    cal_idx = {d: i for i, d in enumerate(cal)}
    ix_close = daily[INDEX_TICKER]["c"]

    # ── funnel 후보 풀 ───────────────────────────────────────────────────────
    pool_rows = []          # (strategy, pool, target_date, ticker)
    funnel_meta = []        # coverage 용
    seen_pool = set()
    for r in read_usv("funnel_raw.usv"):
        sid, tdate, snap_kst, step, sname, prov, scount, xcount, js = r
        step = int(step)
        funnel_meta.append((sid, tdate, step, sname, int(scount), snap_kst))
        for pstep, label in POOLS.get(sid, []):
            if step != pstep:
                continue
            items = json.loads(js) if js else []
            for it in items:
                tk = it if isinstance(it, str) else str(it.get("ticker", "")).strip()
                if not tk or not tk.isdigit() or len(tk) != 6:
                    continue
                key = (sid, label, tdate, tk)
                if key in seen_pool:
                    continue
                seen_pool.add(key)
                pool_rows.append(key)

    # ── 관측 행 생성 ─────────────────────────────────────────────────────────
    obs = []
    # 마법공식 유니버스 랭킹은 (전략, 날짜, pool) 그룹 단위 + 재무 전체(347) 단위 둘 다
    by_group = defaultdict(list)
    for sid, label, tdate, tk in pool_rows:
        by_group[(sid, label, tdate)].append(tk)

    # 전체 재무 유니버스 상시 랭킹 (347 종목, 시총은 stock_master 현재값 — 근사)
    univ_tk = sorted(fins.keys())
    ey_u = {t: compute_ey(fins[t][0][1], (master.get(t, {}).get("mcap_eok") or 0.0) * 1e8)
            for t in univ_tk if fins[t]}
    roc_u = {t: compute_roc(fins[t][0][1]) for t in univ_tk if fins[t]}
    ey_ru, roc_ru = rank_desc(ey_u), rank_desc(roc_u)
    n_univ = len(univ_tk)
    mf_univ = {t: ey_ru[t] + roc_ru[t] for t in univ_tk if t in ey_ru}
    mf_univ_sorted = sorted(mf_univ.items(), key=lambda x: (x[1], x[0]))
    mf_univ_rank = {t: i + 1 for i, (t, _) in enumerate(mf_univ_sorted)}

    fscore_cache = {}
    for t, series in fins.items():
        curr = series[0][1] if len(series) >= 1 else None
        prev = series[1][1] if len(series) >= 2 else None
        fscore_cache[t] = compute_f_score_7(curr, prev)

    for (sid, label, tdate), tks in sorted(by_group.items()):
        live = LIVE[sid]
        # 그룹 내 마법공식 (live 정의: 그날 그 전략 후보 중 재무 보유 종목 상대순위)
        grp_fin = {t: fins[t][0][1] for t in tks if t in fins and fins[t]}
        if grp_fin:
            ey_g = {t: compute_ey(v, (master.get(t, {}).get("mcap_eok") or 0.0) * 1e8)
                    for t, v in grp_fin.items()}
            roc_g = {t: compute_roc(v) for t, v in grp_fin.items()}
            eyr, rocr = rank_desc(ey_g), rank_desc(roc_g)
            mf_g = {t: eyr[t] + rocr[t] for t in grp_fin}
        else:
            mf_g = {}
        n_grp = len(grp_fin)

        for tk in sorted(tks):
            d = daily.get(tk)
            row = dict(strategy=sid, pool=label, target_date=tdate, ticker=tk,
                       name=(master.get(tk, {}).get("name") or ""),
                       pool_n=len(tks))
            # ── 일봉 정렬: D 이하 마지막 봉 ─────────────────────────────────
            if d is None:
                row["daily_ok"] = 0
                obs.append(row)
                continue
            # D 시점 인덱스 (D 봉이 없으면 D 이전 마지막)
            di = None
            for i in range(len(d["dates"]) - 1, -1, -1):
                if d["dates"][i] <= tdate:
                    di = i
                    break
            if di is None or di < RS_PERIOD + 2:
                row["daily_ok"] = 0
                obs.append(row)
                continue
            row["daily_ok"] = 1
            row["bar_date_d"] = d["dates"][di]
            row["bar_is_exact_d"] = int(d["dates"][di] == tdate)
            row["close_d"] = d["c"][di]

            # ── 점수: RS / RSI (D 종가까지 · D-1 종가까지 두 버전) ─────────
            for suf, end in (("_d", di + 1), ("_dm1", di)):
                sc = d["c"][:end]
                # 지수는 같은 달력 날짜 기준으로 절단
                edate = d["dates"][end - 1] if end - 1 >= 0 else None
                if edate is None:
                    row["rs20" + suf] = None
                    row["rsi14" + suf] = None
                    continue
                ii = None
                for j in range(len(cal) - 1, -1, -1):
                    if cal[j] <= edate:
                        ii = j
                        break
                ixc = ix_close[:ii + 1] if ii is not None else None
                row["rs20" + suf] = rel_strength(sc[-(RS_PERIOD + 1):] if len(sc) >= RS_PERIOD + 1 else None,
                                                 ixc[-(RS_PERIOD + 1):] if (ixc is not None and len(ixc) >= RS_PERIOD + 1) else None)
                row["rsi14" + suf] = rsi_wilder(sc[-(RSI_PERIOD + 30):]) if len(sc) >= RSI_PERIOD + 1 else None

            # ── 점수(PIT): 그날 DB 에 실제로 있던 행만으로 재계산 ───────────
            # stock_master_daily 는 과거 bas_dd 행을 나중에 backfill 한다(실측:
            # 08-20 적재분에 bas_dd 2026-03-26 행 포함). 그래서 오늘 시리즈로 만든
            # 점수 ≠ 그날 엔진이 본 점수다. created_at ≤ D 로 필터해 PIT 를 병기한다.
            pit_i = [i for i in range(di + 1) if d["cre"][i] and d["cre"][i] <= tdate]
            row["pit_bars_30"] = min(len(pit_i), 30)
            row["pit_bars_total"] = len(pit_i)
            if len(pit_i) >= RS_PERIOD + 1:
                pc = d["c"][pit_i][-30:]
                pdates = [d["dates"][i] for i in pit_i][-30:]
                ixp = [j for j in range(len(cal)) if cal[j] <= pdates[-1]
                       and daily[INDEX_TICKER]["cre"][j] and daily[INDEX_TICKER]["cre"][j] <= tdate]
                row["rsi14_pit"] = rsi_wilder(pc)
                if len(ixp) >= RS_PERIOD + 1:
                    row["rs20_pit"] = rel_strength(pc, ix_close[ixp][-30:])
                # PIT 창의 달력 밀도 = 최근 30봉이 실제 며칠에 걸쳐 있나
                if len(pdates) >= 21:
                    a, b = cal_idx.get(pdates[-21]), cal_idx.get(pdates[-1])
                    row["pit_rs_span_sessions"] = (b - a) if (a is not None and b is not None) else None

            # ── 점수: F-Score / 마법공식 ────────────────────────────────────
            row["f_score"] = fscore_cache.get(tk)
            row["has_fin"] = int(tk in fins)
            row["fin_asof_ok"] = int(tdate >= FIN_FIRST_LOAD)
            row["mf_rank_pool"] = mf_g.get(tk)
            row["mf_pool_n"] = n_grp
            row["mf_pct_pool"] = (mf_g[tk] / (2.0 * n_grp)) if (tk in mf_g and n_grp) else None
            row["mf_rank_univ"] = mf_univ_rank.get(tk)
            row["mf_pct_univ"] = (mf_univ_rank[tk] / n_univ) if tk in mf_univ_rank else None
            row["ey"] = ey_u.get(tk)
            row["roc"] = roc_u.get(tk)

            # ── 기존 게이트 프록시 (중복도 측정용) ──────────────────────────
            h, l, c, v, tv = d["h"][:di + 1], d["l"][:di + 1], d["c"][:di + 1], d["v"][:di + 1], d["tv"][:di + 1]
            ap = int(live["atr_period"])
            atr_d = atr_wilder(h, l, c, ap) if live["atr_kind"] == "wilder" else atr_sma(h, l, c, ap)
            row["atr"] = atr_d
            row["atr_pct"] = (atr_d / c[-1] * 100.0) if (atr_d and c[-1]) else None
            row["ret20_d"] = ((c[-1] / c[-1 - RS_PERIOD] - 1) * 100.0) if len(c) > RS_PERIOD else None
            row["ret60_d"] = ((c[-1] / c[-61] - 1) * 100.0) if len(c) > 60 else None
            row["tv_d_won"] = float(tv[-1])
            row["tv_ratio20"] = (float(tv[-1]) / float(tv[-21:-1].mean())) if (len(tv) > 21 and tv[-21:-1].mean() > 0) else None
            row["vol_ratio20"] = (float(v[-1]) / float(v[-21:-1].mean())) if (len(v) > 21 and v[-21:-1].mean() > 0) else None
            row["mcap_eok"] = master.get(tk, {}).get("mcap_eok")
            if len(c) >= 20:
                row["don20_high"] = float(h[-20:].max())
                row["breakout_ext_pct"] = ((c[-1] / float(h[-21:-1].max()) - 1) * 100.0) if len(h) > 21 and h[-21:-1].max() > 0 else None
            if len(c) >= 61:
                e5, e20, e40 = ema_series(c, 5), ema_series(c, 20), ema_series(c, 40)
                row["ema5_d"], row["ema20_d"], row["ema40_d"] = e5[-1], e20[-1], e40[-1]
                st = None
                for i in range(len(c)):
                    st = stage_of(e5[i], e20[i], e40[i], st)
                row["kojiro_stage"] = st
                row["band_pct"] = abs(e20[-1] - e40[-1]) / c[-1] * 100.0
            if len(c) >= 200:
                row["ema50_dist_pct"] = (c[-1] / ema_series(c, 50)[-1] - 1) * 100.0
                row["ema150_dist_pct"] = (c[-1] / ema_series(c, 150)[-1] - 1) * 100.0
            row["ema60_dist_pct"] = ((c[-1] / ema_series(c, 60)[-1] - 1) * 100.0) if len(c) >= 61 else None
            row["ch_low10"] = float(l[-10:].min()) if len(l) >= 10 else None

            # ── 성과: 진입일 두 갈래 ─────────────────────────────────────────
            # d0 = 후보일 D 시가 진입 (라이브 정합 — 실체결이 D 09:05 에 난다.
            #      funnel 행 내용이 D-1 종가 정보라는 것은 VB 훅 재현 99.6% 로 실증)
            # d1 = D+1 시가 진입 (보수 변형 — 계획서가 지정한 가정)
            for tag, ei in (("d0", di), ("d1", di + 1)):
                if ei >= len(d["dates"]):
                    row[f"{tag}_entry_ok"] = 0
                    continue
                entry_px = d["o"][ei]
                if not entry_px or entry_px <= 0:
                    row[f"{tag}_entry_ok"] = 0
                    continue
                entry_dd = d["dates"][ei]
                row[f"{tag}_entry_ok"] = 1
                row[f"{tag}_entry_date"] = entry_dd
                row[f"{tag}_entry_open"] = entry_px
                base_close = d["c"][ei - 1] if ei >= 1 else None
                row[f"{tag}_gap_open_pct"] = ((entry_px / base_close - 1) * 100.0) if base_close else None
                eci = cal_idx.get(entry_dd)
                row[f"{tag}_cal_days_after_entry"] = (len(cal) - eci) if eci is not None else None
                row[f"{tag}_fwd_bars_avail"] = len(d["dates"]) - ei
                for hh in HOLD_HORIZONS:
                    j = ei + hh - 1   # 보유 hh 거래일 = 진입일 포함 hh 번째 봉 종가 청산
                    want = cal[eci + hh - 1] if (eci is not None and eci + hh - 1 < len(cal)) else None
                    if j < len(d["c"]):
                        g = (d["c"][j] / entry_px - 1) * 10000.0
                        row[f"{tag}_ret{hh}d_bp"] = g
                        row[f"{tag}_ret{hh}d_net_bp"] = g - COST_BP
                        row[f"{tag}_ret{hh}d_exit_date"] = d["dates"][j]
                        row[f"{tag}_ret{hh}d_aligned"] = int(want is not None and d["dates"][j] == want)
                    else:
                        row[f"{tag}_ret{hh}d_miss_reason"] = ("calendar_truncation" if want is None
                                                             else "daily_load_gap")
                j2 = min(ei + 19, len(d["c"]) - 1)
                if j2 >= ei:
                    row[f"{tag}_mfe20_bp"] = (d["h"][ei:j2 + 1].max() / entry_px - 1) * 10000.0
                    row[f"{tag}_mae20_bp"] = (d["l"][ei:j2 + 1].min() / entry_px - 1) * 10000.0
                # 규약 근사: 진입 시점 ATR = 진입 전날까지의 봉으로 산출 (라이브 _entry_atr 정합)
                hh_, ll_, cc_ = d["h"][:ei], d["l"][:ei], d["c"][:ei]
                a_ = (atr_wilder(hh_, ll_, cc_, ap) if live["atr_kind"] == "wilder"
                      else atr_sma(hh_, ll_, cc_, ap))
                ctx = dict(row)
                if ei >= 1:
                    ctx["ch_low10"] = float(d["l"][max(0, ei - 10):ei].min()) if ei >= 10 else None
                    ctx["don20_high"] = float(d["h"][max(0, ei - 20):ei].max()) if ei >= 20 else None
                sim = simulate_exit(sid, live, d, ei, entry_px, a_ or 0.0, ctx)
                row[f"{tag}_entry_atr"] = a_
                for k, v in sim.items():
                    row[f"{tag}_{k}"] = v

            obs.append(row)

    write_obs(obs)
    trades = build_trades(daily, obs)
    write_coverage(obs, trades, funnel_meta)
    gate_corr(obs)
    print(f"obs rows={len(obs)}  trades={len(trades)}")


# ─────────────────────────────────────────────────────────────────────────────
def simulate_exit(sid, live, d, ei, entry_px, atr_d, row):
    """일봉 기반 청산 규약 근사.

    한계(명시): (a) 일봉이라 장중 순서(손절 vs 고점 갱신)를 모른다 — 손절선 이탈은
    저가 터치로, 트레일링은 종가로 판정한다(보수). (b) ATR·채널저가는 진입일 값
    고정 (live 는 매 prepare 재산출). (c) donchian 시간청산의 `breakout_high` 는
    D 기준 20일 신고가로 근사. (d) kojiro 스테이지3 판정은 종가 EMA 로 재현하되
    live 는 전일 precompute 라 하루 지연이 있다.
    """
    out = {"sim_ok": 0}
    n = len(d["c"])
    stage_series = None
    ema50_series = None
    if sid == "kojiro" and n >= 61:
        e5, e20, e40 = ema_series(d["c"], 5), ema_series(d["c"], 20), ema_series(d["c"], 40)
        stage_series, st = [], None
        for i in range(n):
            st = stage_of(e5[i], e20[i], e40[i], st)
            stage_series.append(st)
    if sid == "vcp_breakout" and n >= 51:
        ema50_series = ema_series(d["c"], 50)
    if ei >= n or not atr_d or atr_d <= 0:
        # ATR 없으면 고정% 경로만
        atr_d = atr_d or 0.0
    highs_since = entry_px
    stop_floor = None
    be_latched = False
    exit_reason, exit_px, exit_i = None, None, None

    if sid == "donchian_swing":
        hard = entry_px - live["stop_atr"] * atr_d if atr_d > 0 else entry_px * (1 + live["stop_loss_rate"] / 100.0)
        backstop = entry_px * (1 + live["turtle_backstop_pct"] / 100.0) if atr_d > 0 else None
        ch_low = row.get("ch_low10") or 0.0
        bh = row.get("don20_high") or 0.0
        nfail = live["breakout_fail_n_days"]
    elif sid == "kojiro":
        hard = entry_px * (1 + live["hard_stop_pct"] / 100.0)
        atr_stop = entry_px - live["stop_atr"] * atr_d if atr_d > 0 else None
    else:  # vcp_breakout — position_ratio → 고정 -7% + BE 래치 + 2ATR 트레일 + EMA50
        hard = entry_px * (1 + live["stop_loss_rate"] / 100.0)

    for k in range(ei, min(ei + MAX_SIM_DAYS, n)):
        o, hi, lo, cl = d["o"][k], d["h"][k], d["l"][k], d["c"][k]
        held = k - ei + 1          # 진입일 포함 보유 거래일
        if sid == "donchian_swing":
            stop = hard
            if atr_d > 0 and highs_since >= entry_px + live["breakeven_promote_atr"] * atr_d:
                stop = max(stop, entry_px)
            if lo <= stop:
                exit_reason, exit_px, exit_i = "stop", min(o, stop) if o <= stop else stop, k
                break
            if backstop and lo <= backstop:
                exit_reason, exit_px, exit_i = "backstop", backstop, k
                break
            if bh > 0 and held >= nfail and cl < bh:
                exit_reason, exit_px, exit_i = "time_exit", cl, k
                break
            if ch_low > 0 and cl < ch_low:
                exit_reason, exit_px, exit_i = "channel", cl, k
                break
            highs_since = max(highs_since, hi)
            if atr_d > 0 and cl <= highs_since - live["atr_trail_mult"] * atr_d:
                exit_reason, exit_px, exit_i = "trail", cl, k
                break
        elif sid == "kojiro":
            if lo <= hard:
                exit_reason, exit_px, exit_i = "hard_stop_pct", min(o, hard) if o <= hard else hard, k
                break
            if atr_stop:
                stop_floor = atr_stop if stop_floor is None else max(stop_floor, atr_stop)
                if lo <= stop_floor:
                    exit_reason, exit_px, exit_i = "atr_stop", stop_floor, k
                    break
            if stage_series is not None and stage_series[k] == 3:
                exit_reason, exit_px, exit_i = "stage3", cl, k
                break
            highs_since = max(highs_since, hi)
            if atr_d > 0 and cl <= highs_since - live["trail_atr"] * atr_d:
                exit_reason, exit_px, exit_i = "trail", cl, k
                break
        else:
            if lo <= hard:
                exit_reason, exit_px, exit_i = "stop_-7pct", min(o, hard) if o <= hard else hard, k
                break
            highs_since = max(highs_since, hi)
            if atr_d > 0 and not be_latched and highs_since >= entry_px + live["breakeven_promote_atr"] * atr_d:
                be_latched = True
            if be_latched and cl <= entry_px:
                exit_reason, exit_px, exit_i = "breakeven", entry_px, k
                break
            if atr_d > 0 and cl <= highs_since - live["atr_trail_mult"] * atr_d:
                exit_reason, exit_px, exit_i = "trail", cl, k
                break
            if ema50_series is not None and cl < ema50_series[k]:
                exit_reason, exit_px, exit_i = "ema50", cl, k
                break

    if exit_reason is None:
        k = min(ei + MAX_SIM_DAYS - 1, n - 1)
        if k >= ei:
            exit_reason, exit_px, exit_i = "cap30", d["c"][k], k
    if exit_px:
        out["sim_ok"] = 1
        out["sim_exit_reason"] = exit_reason
        out["sim_hold_days"] = exit_i - ei + 1
        out["sim_ret_bp"] = (exit_px / entry_px - 1) * 10000.0
        out["sim_ret_net_bp"] = out["sim_ret_bp"] - COST_BP
        out["sim_exit_date"] = d["dates"][exit_i]
    return out


# ─────────────────────────────────────────────────────────────────────────────
OBS_COLS = (
    ["strategy", "pool", "target_date", "ticker", "name", "pool_n",
     "daily_ok", "bar_date_d", "bar_is_exact_d", "close_d",
     # 점수 — 주 컬럼은 `_dm1`(D-1 종가까지). funnel 후보는 D-1 정보로 만들어졌고
     # 실체결은 D 09:05 라, D-1 이 유일하게 룩어헤드 없는 정보집합이다.
     "rs20_dm1", "rsi14_dm1", "rs20_d", "rsi14_d",
     "rs20_pit", "rsi14_pit", "pit_bars_total", "pit_rs_span_sessions",
     "f_score", "has_fin", "fin_asof_ok",
     "mf_rank_pool", "mf_pool_n", "mf_pct_pool", "mf_rank_univ", "mf_pct_univ", "ey", "roc",
     # 기존 게이트 프록시 (중복도 측정) — D 종가 기준
     "atr", "atr_pct", "ret20_d", "ret60_d", "tv_d_won", "tv_ratio20", "vol_ratio20",
     "mcap_eok", "don20_high", "breakout_ext_pct", "ema5_d", "ema20_d", "ema40_d",
     "kojiro_stage", "band_pct", "ema50_dist_pct", "ema150_dist_pct", "ema60_dist_pct", "ch_low10"]
    + [f"{tag}_{c}" for tag in ("d0", "d1") for c in
       (["entry_ok", "entry_date", "entry_open", "gap_open_pct", "cal_days_after_entry",
         "fwd_bars_avail", "entry_atr"]
        + [f"ret{h}d_{k}" for h in HOLD_HORIZONS
           for k in ("bp", "net_bp", "exit_date", "aligned", "miss_reason")]
        + ["mfe20_bp", "mae20_bp",
           "sim_ok", "sim_exit_reason", "sim_hold_days", "sim_ret_bp", "sim_ret_net_bp",
           "sim_exit_date"])]
)



def write_obs(obs):
    path = os.path.join(DATA, "swing_obs.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=OBS_COLS, extrasaction="ignore")
        w.writeheader()
        for r in obs:
            w.writerow({k: fmt(r.get(k)) for k in OBS_COLS})
    print("wrote", path)


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return ""
        return f"{v:.6g}"
    return v


# ── 실체결 FIFO 왕복 ─────────────────────────────────────────────────────────
TRADE_COLS = ["strategy", "ticker", "name", "buy_date", "buy_time", "buy_price", "qty",
              "sell_date", "sell_time", "sell_price", "hold_days_cal", "gross_pnl_won", "db_profit_loss",
              "gross_ret_bp", "net_ret_bp", "score_join_ok", "score_src_date", "pool_joined", "join_kind",
              "rs20_dm1", "rsi14_dm1", "rs20_d", "rsi14_d", "f_score", "mf_rank_univ",
              "mf_pct_univ", "atr_pct", "d0_ret5d_bp", "d0_ret20d_bp",
              "d0_sim_ret_bp", "d0_sim_exit_reason"]


def build_trades(daily, obs):
    """trades_roundtrips.csv 방식 재사용 — 전략·종목별 FIFO 매칭."""
    by = defaultdict(list)
    for r in read_usv("trades_raw.usv"):
        _id, ts, tk, nm, tt, px, qty, pl, st, sid, ono = r
        by[(sid, tk)].append(dict(ts=ts, tt=tt, px=f(px) or 0.0, qty=int(qty or 0),
                                  pl=f(pl) or 0.0, name=nm, status=st, qty_orig=int(qty or 0)))
    # 점수 조인 인덱스: (strategy, ticker) -> {target_date: row}
    score_idx = defaultdict(dict)
    for r in obs:
        if r.get("daily_ok"):
            score_idx[(r["strategy"], r["ticker"])].setdefault(r["target_date"], r)

    rows = []
    for (sid, tk), evs in sorted(by.items()):
        evs.sort(key=lambda e: e["ts"])
        lots = []
        for e in evs:
            if e["tt"] == "BUY":
                lots.append(dict(ts=e["ts"], px=e["px"], qty=e["qty"], name=e["name"]))
            elif e["tt"] == "SELL":
                q = e["qty"]
                while q > 0 and lots:
                    lot = lots[0]
                    m = min(q, lot["qty"])
                    rows.append(mk_trade(sid, tk, lot, e, m, score_idx))
                    lot["qty"] -= m
                    q -= m
                    if lot["qty"] == 0:
                        lots.pop(0)
                if q > 0:  # 매수 이력 없는 매도 (사전 보유/수동)
                    rows.append(mk_trade(sid, tk, None, e, q, score_idx))
    path = os.path.join(DATA, "swing_trades.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=TRADE_COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: fmt(r.get(k)) for k in TRADE_COLS})
    print("wrote", path)
    return rows


def mk_trade(sid, tk, lot, sell, qty, score_idx):
    r = dict(strategy=sid, ticker=tk, name=(lot or {}).get("name") or sell.get("name") or "",
             qty=qty, sell_date=sell["ts"][:10], sell_time=sell["ts"][11:],
             sell_price=sell["px"],
             # DB 원본 profit_loss 를 그대로 옮긴다(FIFO 분할 시 첫 랏에만 전액 계상).
             # 브리프 수치의 정본이 이 컬럼이고, gross_pnl_won 은 (매도가−매수가)×수량 재계산이다.
             db_profit_loss=(sell["pl"] if qty == sell.get("qty_orig") else ""))
    if lot:
        r["buy_date"] = lot["ts"][:10]
        r["buy_time"] = lot["ts"][11:]
        r["buy_price"] = lot["px"]
        if lot["px"] > 0:
            g = (sell["px"] / lot["px"] - 1) * 10000.0
            r["gross_ret_bp"] = g
            r["net_ret_bp"] = g - COST_BP
            r["gross_pnl_won"] = (sell["px"] - lot["px"]) * qty
        d0 = lot["ts"][:10]
        d1 = sell["ts"][:10]
        try:
            from datetime import date
            a = date(*map(int, d0.split("-")))
            b = date(*map(int, d1.split("-")))
            r["hold_days_cal"] = (b - a).days
        except Exception:
            pass
        # 점수 조인 = 매수일의 직전 후보일 행 (D+1 진입 규약과 정합: buy_date 의 전 영업일 후보)
        # 라이브 정합 = 후보일 D 의 09:05 매수 (실측: donchian 17/28·kojiro 18/20 이
        # target_date == buy_date). 그래서 조인 1순위는 **매수일 당일** 후보행이고,
        # 없으면 직전 후보일로 폴백한다.
        cand = score_idx.get((sid, tk), {})
        pick = cand.get(d0)
        row_kind = "same_day"
        if pick is None:
            for td in sorted(cand.keys(), reverse=True):
                if td < d0:
                    pick, row_kind = cand[td], "prev_cand_day"
                    break
        if pick:
            r["score_join_ok"] = 1
            r["score_src_date"] = pick["target_date"]
            r["pool_joined"] = pick["pool"]
            r["join_kind"] = row_kind
            for k in ("rs20_dm1", "rsi14_dm1", "rs20_d", "rsi14_d", "f_score",
                      "mf_rank_univ", "mf_pct_univ", "atr_pct",
                      "d0_ret5d_bp", "d0_ret20d_bp", "d0_sim_ret_bp", "d0_sim_exit_reason"):
                r[k] = pick.get(k)
        else:
            r["score_join_ok"] = 0
    return r


# ── coverage ─────────────────────────────────────────────────────────────────
def write_coverage(obs, trades, funnel_meta):
    rows = []
    # (a) funnel 단계 인벤토리
    inv = defaultdict(lambda: [0, set(), 0])
    for sid, tdate, step, sname, scount, snap in funnel_meta:
        k = (sid, step, sname)
        inv[k][0] += 1
        inv[k][1].add(tdate)
        inv[k][2] += scount
    for (sid, step, sname), (nrow, dates, tot) in sorted(inv.items()):
        rows.append(dict(section="funnel_steps", strategy=sid, pool=f"step{step}",
                         metric=sname, days=len(dates), n=nrow,
                         value=f"{tot/max(nrow,1):.1f}", note="survived_count 평균/일"))
    # (b) 전략×pool 커버리지
    grp = defaultdict(list)
    for r in obs:
        grp[(r["strategy"], r["pool"])].append(r)
    for (sid, pool), rs in sorted(grp.items()):
        days = len({r["target_date"] for r in rs})
        n = len(rs)
        def frac(pred):
            return f"{sum(1 for r in rs if pred(r))}/{n} ({100*sum(1 for r in rs if pred(r))/max(n,1):.1f}%)"
        tr = [t for t in trades if t["strategy"] == sid and t.get("pool_joined") == pool]
        rows.append(dict(section="pool_coverage", strategy=sid, pool=pool,
                         metric="후보 관측", days=days, n=n, value=f"{n/max(days,1):.2f}/일",
                         note=f"거래일 {days}일"))
        for label, pred in (
            ("일봉 보유(daily_ok)", lambda r: r.get("daily_ok") == 1),
            ("D 시가 진입 가능(d0)", lambda r: r.get("d0_entry_ok") == 1),
            ("D+1 시가 진입 가능(d1)", lambda r: r.get("d1_entry_ok") == 1),
            ("RS 보유(D-1)", lambda r: r.get("rs20_dm1") is not None),
            ("RSI 보유(D-1)", lambda r: r.get("rsi14_dm1") is not None),
            ("F-Score 보유", lambda r: r.get("f_score") is not None),
            ("MF(유니버스) 보유", lambda r: r.get("mf_rank_univ") is not None),
            ("재무 시점적격(D≥07-15)", lambda r: r.get("fin_asof_ok") == 1),
            ("d0 ret5d 보유", lambda r: r.get("d0_ret5d_bp") is not None),
            ("d0 ret20d 보유", lambda r: r.get("d0_ret20d_bp") is not None),
            ("d1 ret5d 보유", lambda r: r.get("d1_ret5d_bp") is not None),
            ("d1 ret20d 보유", lambda r: r.get("d1_ret20d_bp") is not None),
            ("d0 규약근사 성립", lambda r: r.get("d0_sim_ok") == 1),
        ):
            rows.append(dict(section="pool_coverage", strategy=sid, pool=pool,
                             metric=label, days=days, n=n, value=frac(pred), note=""))
        rows.append(dict(section="pool_coverage", strategy=sid, pool=pool,
                         metric="실체결 조인", days=days, n=len(tr),
                         value=str(len(tr)), note="이 pool 로 점수 조인된 왕복 수"))
    # (c) 월별 재무 커버리지
    m = defaultdict(lambda: [0, 0, 0])
    for r in obs:
        if r.get("daily_ok") != 1:
            continue
        k = (r["strategy"], r["pool"], r["target_date"][:7])
        m[k][0] += 1
        m[k][1] += 1 if r.get("f_score") is not None else 0
        m[k][2] += 1 if r.get("mf_rank_univ") is not None else 0
    for (sid, pool, mon), (n, nf, nm) in sorted(m.items()):
        rows.append(dict(section="fin_coverage_monthly", strategy=sid, pool=pool, metric=mon,
                         days=0, n=n, value=f"F {nf}/{n} ({100*nf/max(n,1):.0f}%) · MF {nm}/{n} ({100*nm/max(n,1):.0f}%)",
                         note=""))
    # (d) 실체결 요약
    tg = defaultdict(list)
    for t in trades:
        tg[t["strategy"]].append(t)
    for sid, ts in sorted(tg.items()):
        ok = sum(1 for t in ts if t.get("score_join_ok") == 1)
        pnl = sum(t.get("gross_pnl_won") or 0 for t in ts)
        rows.append(dict(section="trades", strategy=sid, pool="-", metric="왕복(FIFO)",
                         days=len({t["sell_date"] for t in ts}), n=len(ts),
                         value=f"조인 {ok}/{len(ts)}", note=f"gross 손익합 {pnl:.0f}원"))
    # (e) forward bar 결손 진단 — 20거래일 표본의 정보적 결손 경고
    import statistics as _st
    for (sid, pool), rs in sorted(grp.items()):
        ent = [r for r in rs if r.get("d0_entry_ok") == 1]
        if not ent:
            continue
        trunc = sum(1 for r in ent if r.get("d0_ret20d_miss_reason") == "calendar_truncation")
        gap = sum(1 for r in ent if r.get("d0_ret20d_miss_reason") == "daily_load_gap")
        rows.append(dict(section="fwd_bar_diag", strategy=sid, pool=pool,
                         metric="ret20d 결손 사유", days=0, n=len(ent),
                         value=f"달력절단 {trunc} · 일봉적재결손 {gap}",
                         note="일봉적재결손 = 달력엔 날이 있는데 그 종목 봉이 없음"))
        has = [r for r in ent if r.get("d0_ret20d_bp") is not None]
        no = [r for r in ent if r.get("d0_ret20d_bp") is None]
        def med(xs, k):
            v = [x[k] for x in xs if x.get(k) is not None]
            return f"{_st.median(v):.0f}" if v else "-"
        rows.append(dict(section="fwd_bar_diag", strategy=sid, pool=pool,
                         metric="결손 정보성(시총 중앙, 억)", days=0, n=len(ent),
                         value=f"보유 {med(has,'mcap_eok')} vs 결손 {med(no,'mcap_eok')}",
                         note="차이 크면 20일 표본은 대형주 편향"))
        rows.append(dict(section="fwd_bar_diag", strategy=sid, pool=pool,
                         metric="결손 정보성(ret5d 중앙, bp)", days=0, n=len(ent),
                         value=f"보유 {med(has,'d0_ret5d_bp')} vs 결손 {med(no,'d0_ret5d_bp')}",
                         note="차이 크면 20일 표본은 성과 편향"))
        al = [r for r in ent if r.get("d0_ret10d_bp") is not None]
        nal = sum(1 for r in al if r.get("d0_ret10d_aligned") == 0)
        rows.append(dict(section="fwd_bar_diag", strategy=sid, pool=pool,
                         metric="ret10d 달력 불일치", days=0, n=len(al),
                         value=f"{nal}/{len(al)}",
                         note="봉 10칸 뒤 ≠ 달력 10거래일 뒤 (중간 결손일)"))

    # (f) 읽는 사람이 반드시 알아야 하는 계약/한계 (validate.py 실측 근거)
    NOTES = [
        ("진입 가정", "d0 = 후보일 D 시가 · d1 = D+1 시가",
         "funnel target_date == 실매수일 실측(donchian 17/28 · kojiro 18/20 · BFB 2/2 same_day). "
         "d0 가 라이브 정합, d1 은 계획서가 지정한 보수 변형. 둘 다 산출했다."),
        ("정보집합", "주 점수 = `_dm1` (D-1 종가까지)",
         "저장된 funnel 행의 내용은 D-1 종가 정보다 — VB 훅 기록값을 end=D-1 창으로 99.6%(1441/1447) "
         "정확 재현. 계획서가 가정한 `end=D, period=20` 은 4.3% 만 재현한다. `_d` 컬럼은 D 종가까지라 "
         "d0 진입 기준에서는 룩어헤드다(참고용)."),
        ("RS 정의", "ta_indicators.relative_strength(period=20) 재현",
         "훅 기록값과 정확히 맞는 파라미터는 (end=D-1, period=19)였다. 코드 period 는 20 이므로 "
         "1봉 차이는 캡처 시점 DB 시리즈와 현재 시리즈의 vintage 차이로 보이며 원인을 현재 데이터로는 "
         "확정할 수 없었다. `rs20_dm1` 은 **코드 정의(period=20)** 를 D-1 창에 적용한 값이다."),
        ("F-Score", "quant_score.compute_f_score_7 재현 — 정확일치 1800/1800",
         "결측 지표는 0점, prev 7필드 전부 결측이면 None(fail-open). 연간(div_cls='0') 2기 비교."),
        ("마법공식", "compute_magic_formula 재현 — Spearman 0.9986, |diff| 중앙 1랭크",
         "정확일치는 39% 뿐이다(EY 분모 시총이 라이브는 그날 값, 오프라인은 현재 값 = 시점 드리프트). "
         "`mf_rank_pool` = 라이브 정의(그날 그 전략 후보 안 상대순위), `mf_rank_univ`/`mf_pct_univ` = "
         "재무 보유 347종목 고정 모집단 순위 — 후보 2~3개짜리 날에는 pool 순위가 무의미하므로 univ 를 쓸 것."),
        ("재무 정지", "stock_master_financial 마지막 갱신 2026-08-12 · 347 종목",
         "07-15 최초 적재. D<2026-07-15 후보는 라이브에서 점수를 볼 수 없었다(`fin_asof_ok=0`). "
         "커버리지는 전략별로 극단적으로 갈린다 — donchian 100% vs kojiro 50% vs VCP 56~67%."),
        ("20일 성과 편향", "ret20d 는 달력 절단이 지배적이며 표본이 대형주·초기 구간에 쏠린다",
         "fwd_bar_diag 섹션 참조. 20일 결과를 전 표본 결과로 읽지 말 것 — 같은 날짜 안에서만 비교하거나 "
         "3/5/10일을 주 지평으로 쓸 것."),
        ("VCP 표본", "최종 단계(step9) 후보가 전 기간 2건",
         "step7(Pullback 수축)에서 13.5→0.8/일로 잘린다. 그래서 pool=wide(step6 베이스 검출, 13.8/일)와 "
         "wide2(step5 EMA 정렬, 24.9/일)를 함께 냈다. VCP 는 실체결도 0건이라 후보-레벨만 가능하다."),
        ("청산 근사", "일봉 기반, 실체결 왕복과 상관 0.658 · 부호일치 19/28",
         "장중 순서를 모른다(손절은 저가 터치, 트레일은 종가 판정). ATR·채널저가는 진입일 값 고정. "
         "donchian breakout_high 는 진입 직전 20일 신고가로 근사. VCP 는 base_low 를 재현할 수 없어 "
         "그 분기가 빠졌다(계획서의 VCP `max_hold_days` 는 코드에 없다 — BFB 전용 키다)."),
        ("비용", f"왕복 {COST_BP:.0f}bp 차감 = `*_net_bp`", "수수료 0.015%×2 + 거래세 0.15% + 슬리피지 10bp."),
        ("금기", "이 산출물은 SELECT 만으로 만들었다", "리포·DB·설정 무변경."),
    ]
    for a, b, c in NOTES:
        rows.append(dict(section="notes", strategy="-", pool="-", metric=a, days=0, n=0,
                         value=b, note=c))

    path = os.path.join(DATA, "coverage.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["section", "strategy", "pool", "metric",
                                           "days", "n", "value", "note"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("wrote", path)


# ── 기존 게이트 ↔ 신규 점수 상관 ─────────────────────────────────────────────
def gate_corr(obs):
    from scipy import stats
    new = ["rs20_dm1", "rsi14_dm1", "f_score", "mf_pct_univ"]
    gates = {
        "donchian_swing": ["atr_pct", "tv_ratio20", "breakout_ext_pct", "ema60_dist_pct", "ret20_d"],
        "kojiro": ["atr_pct", "band_pct", "kojiro_stage", "ema60_dist_pct", "ret20_d"],
        "vcp_breakout": ["atr_pct", "vol_ratio20", "ema50_dist_pct", "ema150_dist_pct", "ret20_d"],
    }
    rows = []
    grp = defaultdict(list)
    for r in obs:
        if r.get("daily_ok") == 1:
            grp[(r["strategy"], r["pool"])].append(r)
    for (sid, pool), rs in sorted(grp.items()):
        for a in new:
            for b in gates[sid]:
                x = [r.get(a) for r in rs]
                y = [r.get(b) for r in rs]
                pairs = [(p, q) for p, q in zip(x, y) if p is not None and q is not None]
                if len(pairs) < 10:
                    rows.append(dict(strategy=sid, pool=pool, score=a, gate=b, n=len(pairs),
                                     spearman="", pval="", pearson="",
                                     spearman_within_date="", n_within=0))
                    continue
                xs = np.array([p for p, _ in pairs], float)
                ys = np.array([q for _, q in pairs], float)
                sr = stats.spearmanr(xs, ys)
                pr = stats.pearsonr(xs, ys) if xs.std() > 0 and ys.std() > 0 else (float("nan"), float("nan"))
                # 날짜 내 순위 상관 — 같은 날 후보끼리만 비교해 시장 공통 성분을 제거한다.
                # RS 는 정의상 `종목 20일 수익률 − 지수 20일 수익률` 이고 지수 항은 그날 상수라
                # 날짜를 섞으면 ret20 과의 상관이 인위적으로 부푼다.
                byd = defaultdict(list)
                for r in rs:
                    if r.get(a) is not None and r.get(b) is not None:
                        byd[r["target_date"]].append((float(r[a]), float(r[b])))
                zx, zy = [], []
                for _, ps in byd.items():
                    if len(ps) < 3:
                        continue
                    ax = np.array([p for p, _ in ps], float)
                    ay = np.array([q for _, q in ps], float)
                    rx = stats.rankdata(ax)
                    ry = stats.rankdata(ay)
                    zx.extend(rx - rx.mean())
                    zy.extend(ry - ry.mean())
                if len(zx) >= 10 and np.std(zx) > 0 and np.std(zy) > 0:
                    wr = float(np.corrcoef(zx, zy)[0, 1])
                    wn = len(zx)
                else:
                    wr, wn = float("nan"), len(zx)
                rows.append(dict(strategy=sid, pool=pool, score=a, gate=b, n=len(pairs),
                                 spearman=f"{sr.statistic:.3f}", pval=f"{sr.pvalue:.4f}",
                                 pearson=f"{pr[0]:.3f}",
                                 spearman_within_date=("" if wr != wr else f"{wr:.3f}"),
                                 n_within=wn))
    path = os.path.join(DATA, "gate_corr.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["strategy", "pool", "score", "gate", "n",
                                           "spearman", "pval", "pearson",
                                           "spearman_within_date", "n_within"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("wrote", path)


if __name__ == "__main__":
    main()
