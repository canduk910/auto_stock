#!/usr/bin/env python3
"""평균회귀(OU) 트랙 R 연구 — 2단계: 판정·표.

    python tools/replay/analyze_mean_reversion.py <scratch_dir> <out_dir>

입력(<scratch_dir>): ``mr_arch.pkl``·``mr_db.pkl``·``mr_db_noprov.pkl``(1단계 산출) +
``mr_db_extract.jsonl.gz``(DB 추출본). 보관소 패널은 ``replay.data.load_archive`` 로 다시 읽는다.
출력(<out_dir>): ``results.json`` + 표 CSV 몇 개. 요약 md 는 이 결과로 쓴다.
판정 규칙·문턱 = 지시서 §3.6·§3.9 (사전 고정 — 이 파일에서 바꾸지 않는다).
"""
from __future__ import annotations

import csv
import json
import math
import os
import pickle
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from replay import data as D  # noqa: E402
from replay import judge as J  # noqa: E402
from replay import portfolio as PF  # noqa: E402
from replay.run_mean_reversion import (COSTS, REASONS, TRADE_COLS, Z_ENTRY, Z_EXIT,  # noqa: E402
                                        mu_exec_series)
from replay.strategies.mean_reversion.ou import efficiency_ratio  # noqa: E402

CI = {c: i for i, c in enumerate(TRADE_COLS)}
BUDGET = 5_000_000 * 0.95 * 0.05      # 237,500원 (§3.4 D7)
MAIN_COST = 0.0038
MIN_SELECT_TRADES = 30


def gather(payload, key):
    arrs = [r["trades"][key] for r in payload["results"] if key in r["trades"]]
    if not arrs:
        return np.zeros((0, len(TRADE_COLS)))
    return np.vstack(arrs)


def trade_stats(a: np.ndarray, cost: float) -> dict:
    n = len(a)
    if n == 0:
        return dict(n=0)
    net = a[:, CI["gross"]] - cost
    pos, neg = net[net > 0].sum(), -net[net < 0].sum()
    rc = np.bincount(a[:, CI["reason"]].astype(int), minlength=len(REASONS)) / n
    is_rb = a[:, CI["reason"]].astype(int) == REASONS.index("regime_break")
    rbk = a[:, CI["rb_kind"]].astype(int)
    return dict(n=n, win=float(np.mean(net > 0)), mean_net=float(net.mean()),
                regime_break_split=dict(stat=float(np.mean(is_rb & (rbk == 1))),
                                        unmeasurable=float(np.mean(is_rb & (rbk == 2))),
                                        stat_mean_net=float(net[is_rb & (rbk == 1)].mean()) if np.any(is_rb & (rbk == 1)) else None,
                                        unmeasurable_mean_net=float(net[is_rb & (rbk == 2)].mean()) if np.any(is_rb & (rbk == 2)) else None),
                median_net=float(np.median(net)), mean_gross=float(a[:, CI["gross"]].mean()),
                pf=float(pos / neg) if neg > 0 else float("inf"), held=float(a[:, CI["held"]].mean()),
                reasons={REASONS[i]: float(rc[i]) for i in range(len(REASONS))},
                z_entry=float(np.nanmean(a[:, CI["z_entry"]])), z_exit=float(np.nanmean(a[:, CI["z_exit"]])),
                mae=float(np.nanmean(a[:, CI["mae"]])), mfe=float(np.nanmean(a[:, CI["mfe"]])))


def clusters_for(a: np.ndarray, dates: np.ndarray, tickers: list):
    wk = dates[a[:, CI["ei"]].astype(int)].astype("datetime64[W]").astype(int)
    tk = np.array([tickers[int(j)] for j in a[:, CI["tj"]]])
    return tk, wk


def boot_mean(a, cost, dates, tickers):
    if len(a) == 0:
        return (float("nan"),) * 3
    tk, wk = clusters_for(a, dates, tickers)
    return J.bootstrap_mean(a[:, CI["gross"]] - cost, J.cluster_ids(tk, wk), q=0.05)


def boot_diff(a, b, cost, dates, tickers):
    if len(a) == 0 or len(b) == 0:
        return (float("nan"),) * 3
    tka, wka = clusters_for(a, dates, tickers)
    tkb, wkb = clusters_for(b, dates, tickers)
    ids = J.cluster_ids(np.concatenate([tka, tkb]), np.concatenate([wka, wkb]))
    return J.bootstrap_diff(a[:, CI["gross"]] - cost, ids[:len(a)], b[:, CI["gross"]] - cost,
                            ids[len(a):], q=0.05)


def account(a: np.ndarray, closes: np.ndarray, n_days: int, slots: int, cost: float,
            day_lo: int = 0) -> dict:
    tr = [dict(tj=int(r[CI["tj"]]), ei=int(r[CI["ei"]]), xi=int(r[CI["xi"]]), entry_px=r[CI["entry_px"]],
               exit_px=r[CI["exit_px"]], entry_raw=r[CI["entry_raw"]], z_entry=r[CI["z_entry"]])
          for r in a if r[CI["sig_day"]] >= day_lo]
    res = PF.run_account(tr, closes, n_days, budget=BUDGET, slots=slots, cost=cost)
    dr = res["daily_ret"][day_lo:]
    eq = res["equity"][day_lo:]
    sh, so = PF.sharpe_sortino(dr)
    res.update(sharpe=sh, sortino=so, mdd_period=float(np.min(eq / np.maximum.accumulate(eq) - 1.0)),
               net_period=float(eq[-1] / eq[0] - 1.0))
    return res


def pass_summary(payload, market=None):
    out = {}
    for m in ("resid", "price", "shuffle", "rw"):
        u = o = ever = consec = anyu = nh = nhe = 0
        codes = np.zeros(9)
        for r in payload["results"]:
            if market and payload["market"].get(r["ticker"]) != market:
                continue
            ps = r["pass"][m]
            nh += ps.get("n_halt", 0)
            nhe += ps.get("n_halt_eligible", 0)
            u += ps["n_usable"]
            o += ps["n_ok"]
            codes += ps["codes"]
            anyu += ps["any_usable"]
            ever += ps["ever"]
            consec += ps["consec"]
        out[m] = dict(windows=u, ok=o, rate=o / u if u else float("nan"), halt_windows=nh,
                      halt_windows_eligible=nhe,
                      ever=ever / anyu if anyu else float("nan"),
                      consec=consec / anyu if anyu else float("nan"), tickers=anyu,
                      reason_share={k: float(codes[v] / u) if u else float("nan")
                                    for k, v in [("ok", 0), ("adf", 1), ("half_life", 2), ("b_range", 3)]})
    return out


def hl_summary(payload):
    hl = np.concatenate([r["hl"][0] for r in payload["results"]] or [np.zeros(0)])
    ha = np.concatenate([r["hl"][1] for r in payload["results"]] or [np.zeros(0)])
    q = [0.1, 0.25, 0.5, 0.75, 0.9]

    def qs(v):
        v = v[np.isfinite(v)]
        return {str(k): float(np.quantile(v, k)) for k in q} if len(v) else {}
    return dict(raw=qs(hl), kendall=qs(ha), kendall_nan_share=float(np.mean(~np.isfinite(ha))) if len(ha) else None)


def leung_fail_rate(payload, key):
    tried = fails = no_entry = 0
    for r in payload["results"]:
        t, f, ne = r["leung_fail"].get(key, (0, 0, 0))
        tried += t
        fails += f
        no_entry += ne
    return dict(tried=tried, fails=fails, rate=fails / tried if tried else float("nan"),
                no_entry=no_entry, no_entry_rate=no_entry / tried if tried else float("nan"))


def record_counts(payload, key):
    """2차 M9 — halt 총수(종목 거래 구간 안) · 비용 조건이 거른 신호 수."""
    return dict(halt_rows=int(sum(r.get("halt_rows", 0) for r in payload["results"])),
                cost_blocked=int(sum(r.get("cost_blocked", {}).get(key, 0) for r in payload["results"])))


def er_series(closes):
    return np.array([efficiency_ratio(closes, t, 20) for t in range(len(closes))])


def bucket_table(a, cost, mu_vals, er_b):
    """시장 유닛 × ER 삼분위 거래 표. mu_vals = 진입 거래의 시장 유닛, er_b = 신호일 ER 칸."""
    net = a[:, CI["gross"]] - cost if len(a) else np.zeros(0)
    out = {}
    for mu in (1.0, 0.75, 0.5, 0.0, None):
        for eb in (0, 1, 2, None):
            m = np.ones(len(a), dtype=bool)
            if mu is not None:
                m &= mu_vals == mu
            if eb is not None:
                m &= er_b == eb
            n = int(m.sum())
            out[f"mu={mu}|er={eb}"] = dict(n=n, mean_net=float(net[m].mean()) if n else None,
                                           thin=n < 10)
    return out


# ── 기존 전략 일별 수익률 (DB 구간 §3.7) ─────────────────────────────────────
# 2차(M1·M2): 날짜 = KST · 결측 종가는 직전 평가가(첫 종가 전에는 체결가) · 분모 = 전략별 그날 전략 예산
# (앞선 가장 가까운 0 초과 daily_performance 행, 없으면 투입 원금) · 누적 수량이 음수가 되는 키는 제외.

KST = timezone(timedelta(hours=9))
EXISTING_WINDOW_ALT_START = "2026-04-29"   # 보조 창 — 첫 입금(총자산 약 49만 → 98만) 다음부터 (판정에 안 씀)


def kst_date(ts: str) -> str:
    return datetime.fromisoformat(ts).astimezone(KST).date().isoformat()


SCALE_BAND = (0.70, 1.30)   # 사후 발견 1(M11) — 같은 날 체결가 ÷ DB 종가가 가격제한폭 밖이면 가격 기준 불일치


def existing_daily_returns(ext, P, *, scale_check: bool = False):
    """→ (pnl[전략], budget[전략], meta). pnl = 그날 평가손익(원), budget = 그날 전략 예산(원, 없으면 NaN).

    ``scale_check`` = 사후 발견 1(M11) 고친 판 — DB 종가가 뒤의 기업행위로 소급 수정돼 체결가와 기준이 다른
    (전략, 종목) 키를 뺀다. 기본값 False = 사전 등록 판.
    """
    cols, rows = ext["trades"]
    ix = {c: i for i, c in enumerate(cols)}
    di = {str(d): i for i, d in enumerate(P.dates)}
    tj = {t: j for j, t in enumerate(P.tickers)}
    n = len(P.dates)
    recs = []
    skipped, skipped_dates = 0, defaultdict(int)
    for r in rows:
        d = kst_date(r[ix["timestamp"]])
        if d not in di:
            skipped += 1
            skipped_dates[d] += 1
            continue
        recs.append((r[ix["timestamp"]], r[ix["strategy"]], r[ix["ticker"]], di[d],
                     1.0 if r[ix["trade_type"]] == "BUY" else -1.0, float(r[ix["quantity"]]), float(r[ix["price"]])))
    recs.sort(key=lambda x: x[0])
    by_key = defaultdict(list)
    for rec in recs:
        by_key[(rec[1], rec[2])].append(rec)
    neg_keys, neg_rows = 0, 0
    sc_keys, sc_rows = 0, 0
    pnl = defaultdict(lambda: np.zeros(n))
    basis = defaultdict(lambda: np.zeros(n))     # 그날 장 마감 후 평균 매입원가 합
    missing_close = 0
    for (strat, tk), lst in by_key.items():
        q = 0.0
        bad = False
        for rec in lst:
            q += rec[4] * rec[5]
            if q < -1e-9:
                bad = True
                break
        if bad:
            neg_keys += 1
            neg_rows += len(lst)
            continue
        if tk not in tj:
            missing_close += 1
            continue
        if scale_check:
            clk = P.c[:, tj[tk]]
            ratios = [rec[6] / clk[rec[3]] for rec in lst if np.isfinite(clk[rec[3]]) and clk[rec[3]] > 0]
            if any(not (SCALE_BAND[0] <= q <= SCALE_BAND[1]) for q in ratios):
                sc_keys += 1
                sc_rows += len(lst)
                continue
        flow = np.zeros(n)
        cash = np.zeros(n)
        last_px = np.full(n, np.nan)
        cost_eod = np.zeros(n)
        qty, cost = 0.0, 0.0
        k = 0
        for i in range(n):
            while k < len(lst) and lst[k][3] == i:
                _ts, _s, _t, _i, sgn, qq, px = lst[k]
                flow[i] += sgn * qq
                cash[i] -= sgn * qq * px
                if sgn > 0:
                    cost += qq * px
                    qty += qq
                else:
                    avg = cost / qty if qty > 0 else 0.0
                    cost -= avg * qq
                    qty -= qq
                    if qty <= 1e-9:
                        qty, cost = 0.0, 0.0
                last_px[i] = px
                k += 1
            cost_eod[i] = cost
        hold = np.cumsum(flow)
        cl = P.c[:, tj[tk]]
        v = np.full(n, np.nan)
        trade_px = np.nan
        for i in range(n):
            if np.isfinite(last_px[i]):
                trade_px = last_px[i]
            if np.isfinite(cl[i]):
                v[i] = cl[i]
            elif i > 0 and np.isfinite(v[i - 1]):
                v[i] = v[i - 1]
            else:
                v[i] = trade_px
        val = np.where(np.abs(hold) > 1e-9, hold * v, 0.0)
        if not np.all(np.isfinite(val)):
            missing_close += 1
            val = np.nan_to_num(val)
        pnl[strat] += np.diff(np.concatenate([[0.0], val])) + cash
        basis[strat] += cost_eod
    # 전략 예산 — 앞선 가장 가까운 0 초과 daily_performance 행(같은 전략), 없으면 투입 원금(전일 장 마감 원가)
    pcols, prows = ext.get("perf_total", [None, []])
    rows_by = defaultdict(list)
    if pcols:
        px = {c: i for i, c in enumerate(pcols)}
        for r in prows:
            sname = r[px["strategy"]]
            if sname == "total":
                continue
            v = r[px["total_asset"]]
            if v is not None and float(v) > 0:
                rows_by[sname].append((r[px["date"]][:10], float(v)))
    budget = {}
    src = defaultdict(lambda: defaultdict(int))
    for strat in pnl:
        rb = sorted(rows_by.get(strat, []))
        b = np.full(n, np.nan)
        for i in range(n):
            day = str(P.dates[i])
            prior = [v for d, v in rb if d < day]
            if prior:
                b[i] = prior[-1]
                src[strat]["perf_row"] += 1
            elif i > 0 and basis[strat][i - 1] > 0:
                b[i] = basis[strat][i - 1]
                src[strat]["principal"] += 1
        budget[strat] = b
    meta = dict(skipped_rows=skipped, skipped_dates=dict(skipped_dates), tickers_without_close=missing_close,
                negative_qty_keys=neg_keys, negative_qty_rows=neg_rows,
                scale_mismatch_keys=sc_keys, scale_mismatch_rows=sc_rows,
                n_rows_used=len(recs) - neg_rows - sc_rows,
                budget_source={k: dict(v) for k, v in src.items()})
    return dict(pnl), budget, meta


def combine_existing(pnl: dict, budget: dict, window: np.ndarray):
    """(본 판정) Σ전략 손익 ÷ Σ전략 예산, (보조) 전략 수익률 단순합. 예산 없는 전략은 그날 빠진다."""
    n = len(window)
    num, den, simple = np.zeros(n), np.zeros(n), np.zeros(n)
    has = np.zeros(n, dtype=bool)
    for s, p in pnl.items():
        b = budget.get(s)
        if b is None:
            continue
        ok = np.isfinite(b) & (b > 0)
        num[ok] += p[ok]
        den[ok] += b[ok]
        simple[ok] += p[ok] / b[ok]
        has |= ok
    use = has & window
    comb = np.where(use, num / np.where(den > 0, den, 1.0), np.nan)
    return comb, np.where(use, simple, np.nan)


def main():
    scratch, out_dir = sys.argv[1], sys.argv[2]
    extract_path = sys.argv[3] if len(sys.argv) > 3 else os.path.join(scratch, "mr_db_extract.jsonl.gz")
    os.makedirs(out_dir, exist_ok=True)
    A = pickle.load(open(os.path.join(scratch, "mr_arch.pkl"), "rb"))
    B = pickle.load(open(os.path.join(scratch, "mr_db.pkl"), "rb"))
    B2 = pickle.load(open(os.path.join(scratch, "mr_db_noprov.pkl"), "rb"))
    P = D.load_archive()
    ext = D.load_db_extract(extract_path)
    Q = D.db_panel(ext)
    res: dict = {"meta": {"archive": A["meta"] | {"excluded": None}, "db": B["meta"] | {"excluded": None}}}
    res["meta"]["archive"]["excluded_reasons"] = _count(A["meta"]["excluded"])
    res["meta"]["db"]["excluded_reasons"] = _count(B["meta"]["excluded"])
    nA, nB = len(A["dates"]), len(B["dates"])
    cutA, cutB = J.split_index(nA), J.split_index(nB)
    res["split"] = dict(archive_cut_date=str(A["dates"][cutA]), db_cut_date=str(B["dates"][cutB]))

    # 1) 통과율
    res["pass"] = {"archive": pass_summary(A), "archive_KOSPI": pass_summary(A, "KOSPI"),
                   "archive_KOSDAQ": pass_summary(A, "KOSDAQ"), "db": pass_summary(B)}
    res["half_life"] = {"archive": hl_summary(A), "db": hl_summary(B)}

    # 2) z 고르기 — 앞 60%, 비용 0.38%, 잔차, asof, 시장유닛 차단, 기본 손절
    def zkey(ez, xz, cost=MAIN_COST, sp=7.0, k=1.5, mode="resid", uni="asof", mu="mu"):
        return f"z|{ez}|{xz}|{cost}|{sp}|{k}|{mode}|{uni}|{mu}"

    def lkey(r="r3.5", cost=MAIN_COST, sp=7.0, k=1.5, uni="asof", mu="mu"):
        return f"leung|{r}|{cost}|{sp}|{k}|resid|{uni}|{mu}"

    sel_rows = []
    for ez in Z_ENTRY:
        for xz in Z_EXIT:
            a = gather(A, zkey(ez, xz))
            fr = a[a[:, CI["sig_day"]] < cutA]
            bk = a[a[:, CI["sig_day"]] >= cutA]
            sel_rows.append(dict(ez=ez, xz=xz, front=trade_stats(fr, MAIN_COST), back=trade_stats(bk, MAIN_COST),
                                 full=trade_stats(a, MAIN_COST)))
    eligible = [r for r in sel_rows if r["front"].get("n", 0) >= MIN_SELECT_TRADES]
    best = max(eligible, key=lambda r: r["front"]["mean_net"])
    ez, xz = best["ez"], best["xz"]
    res["z_selection"] = dict(table=sel_rows, chosen=dict(entry_z=ez, exit_z=xz),
                              rule="앞 60% 거래당 순기대값 최대(거래 ≥ 30)")
    za = gather(A, zkey(ez, xz))
    la = gather(A, lkey())
    zb, lb_ = za[za[:, CI["sig_day"]] >= cutA], la[la[:, CI["sig_day"]] >= cutA]

    # 3) z vs Leung 판정 (§3.6)
    diff = boot_diff(lb_, zb, MAIN_COST, A["dates"], A["tickers"])
    fail = leung_fail_rate(A, lkey())
    acc_z = account(za, P.c, nA, 2, MAIN_COST, cutA)
    acc_l = account(la, P.c, nA, 2, MAIN_COST, cutA)
    # 문헌 재현 (a) — ``leung_check.py`` 산출(out_dir/leung_check.json). 없으면 미검증으로 본다.
    lc_path = os.path.join(out_dir, "leung_check.json")
    lit = json.load(open(lc_path)) if os.path.exists(lc_path) else None
    lit_pass = bool(lit and lit["a_literature"]["passed"])
    cond = {
        "1_back_mean_higher_and_boot_lo_gt_0": bool(diff[0] > 0 and diff[1] > 0),
        "2_solver_fail_lt_10pct": bool(fail["rate"] < 0.10),
        "3_literature_replicated": lit_pass,
        "4_mdd_le_1.2x": bool(abs(acc_l["mdd_period"]) <= 1.2 * abs(acc_z["mdd_period"])),
    }
    res["z_vs_leung"] = dict(back_z=trade_stats(zb, MAIN_COST), back_leung=trade_stats(lb_, MAIN_COST),
                             diff_leung_minus_z=dict(mean=diff[0], lo90=diff[1], hi90=diff[2]),
                             solver=fail, mdd_back_slots2=dict(z=acc_z["mdd_period"], leung=acc_l["mdd_period"]),
                             conditions=cond, adopt_leung=all(cond.values()),
                             leung_label="Leung" if lit_pass else "Leung(미검증)",
                             leung_check_b_passed=None if lit is None else lit["b_passed"])
    adopt_key_arch = lkey() if all(cond.values()) else zkey(ez, xz)
    adopt_key_db = adopt_key_arch.replace("|asof|", "|db|")
    adopted = la if all(cond.values()) else za

    # 4) 문턱
    ab = adopted[adopted[:, CI["sig_day"]] >= cutA]
    bm = boot_mean(ab, MAIN_COST, A["dates"], A["tickers"])
    years = nA / 252.0
    dbt = gather(B, adopt_key_db)
    db_stats = trade_stats(dbt, MAIN_COST)
    arch_full = trade_stats(adopted, MAIN_COST)
    pr = res["pass"]["archive"]
    acc2 = account(adopted, P.c, nA, 2, MAIN_COST)
    th = {}
    th["T1"] = dict(back_mean_net=bm[0], boot_lo90=bm[1], boot_hi90=bm[2], n=len(ab),
                    verdict="통과" if (bm[0] > 0 and bm[1] > -0.001) else "실패")
    d_sh = pr["resid"]["rate"] - pr["shuffle"]["rate"]
    d_rw = pr["resid"]["rate"] - pr["rw"]["rate"]
    th["T2"] = dict(resid=pr["resid"]["rate"], shuffle=pr["shuffle"]["rate"], rw=pr["rw"]["rate"],
                    minus_shuffle_pp=d_sh * 100, minus_rw_pp=d_rw * 100,
                    verdict="통과" if (d_sh >= 0.05 and d_rw >= 0.05) else "실패")
    per_year = len(adopted) / years
    if db_stats.get("n", 0) < 15:
        sign_v = "판정 불가(DB 거래 < 15)"
        t4 = "통과" if per_year >= 30 else "실패"
    else:
        same = np.sign(db_stats["mean_net"]) == np.sign(arch_full["mean_net"])
        sign_v = "같음" if same else "다름"
        t4 = "통과" if (per_year >= 30 and same) else "실패"
    th["T4"] = dict(trades_per_year=per_year, archive_mean_net=arch_full["mean_net"],
                    db_n=db_stats.get("n", 0), db_mean_net=db_stats.get("mean_net"), sign=sign_v, verdict=t4)
    th["T5"] = dict(unaffordable_ratio=acc2["unaffordable_ratio"], unaffordable_ratio_all=acc2["unaffordable_ratio_all"],
                    n_signal=acc2["n_signal"], n_slot_full=acc2["n_slot_full"], n_unaffordable=acc2["n_unaffordable"],
                    n_filled=acc2["n_filled"], verdict="통과" if acc2["unaffordable_ratio"] < 0.5 else "실패")

    # 5) 계좌 지표 (슬롯 1·2·3, 비용 3단계)
    accts = {}
    for cost in COSTS:
        ka = adopt_key_arch.replace(f"|{MAIN_COST}|", f"|{cost}|")
        aa = gather(A, ka)
        for s in (1, 2, 3):
            r = account(aa, P.c, nA, s, cost)
            accts[f"cost={cost}|slots={s}"] = {k: r[k] for k in ("net_return", "mdd", "sharpe", "sortino", "turnover",
                                                                 "n_signal", "n_slot_full", "n_unaffordable",
                                                                 "n_filled", "unaffordable_ratio")}
            accts[f"cost={cost}|slots={s}"]["gross_return_trades_mean"] = trade_stats(aa, 0.0).get("mean_net")
    res["accounts_archive"] = accts

    # 6) 비용 단계 · 손절 격자 · 모드 · 유니버스 · 시장유닛 변형
    res["cost_table"] = {str(c): trade_stats(gather(A, adopt_key_arch.replace(f"|{MAIN_COST}|", f"|{c}|")), c)
                         for c in COSTS}
    grid = {}
    for sp in (5.0, 7.0, 10.0):
        for k in (1.0, 1.5, 2.0):
            grid[f"X={sp}|k={k}|z"] = trade_stats(gather(A, zkey(ez, xz, sp=sp, k=k)), MAIN_COST)
            grid[f"X={sp}|k={k}|leung"] = trade_stats(gather(A, lkey(sp=sp, k=k)), MAIN_COST)
    res["stop_grid"] = grid
    res["variants"] = {
        "price_mode": trade_stats(gather(A, zkey(ez, xz, mode="price")), MAIN_COST),
        "today_universe": trade_stats(gather(A, zkey(ez, xz, uni="today")), MAIN_COST),
        "no_market_unit_block": trade_stats(gather(A, zkey(ez, xz, mu="nomu")), MAIN_COST),
        "mu_missing_enter": trade_stats(gather(A, zkey(ez, xz, mu="mumiss")), MAIN_COST),
        "leung_r10": trade_stats(gather(A, lkey(r="r10")), MAIN_COST),
        "leung_today": trade_stats(gather(A, lkey(uni="today")), MAIN_COST),
        "leung_no_mu": trade_stats(gather(A, lkey(mu="nomu")), MAIN_COST),
    }
    for kk in ("front", "back"):
        res["variants"][f"today_universe_{kk}"] = trade_stats(_part(gather(A, zkey(ez, xz, uni="today")), cutA, kk), MAIN_COST)
        res["variants"][f"asof_universe_{kk}"] = trade_stats(_part(za, cutA, kk), MAIN_COST)

    # 7) 장세 두 축 — 보관소 (기준 = KOSPI 근사 지수)
    idx = A["bench"]["kospi_approx"]
    erA = er_series(idx)
    erA_bounds = J.er_terciles(erA, cutA)
    erA_b = J.er_bucket(erA, erA_bounds)
    nomu = gather(A, zkey(ez, xz, mu="nomu"))
    res["regime_archive"] = dict(
        er_bounds_front60=erA_bounds,
        adopted=bucket_table(adopted, MAIN_COST, adopted[:, CI["mu"]], erA_b[adopted[:, CI["sig_day"]].astype(int)]),
        no_mu_block=bucket_table(nomu, MAIN_COST, nomu[:, CI["mu"]], erA_b[nomu[:, CI["sig_day"]].astype(int)]),
        back_only=bucket_table(ab, MAIN_COST, ab[:, CI["mu"]], erA_b[ab[:, CI["sig_day"]].astype(int)]),
        mu_day_share={str(m): float(np.mean(A["mu_exec"] == m)) for m in (1.0, 0.75, 0.5, 0.0)},
    )

    # 8) DB 구간
    res["db"] = dict(adopted=db_stats, adopted_noprov=trade_stats(gather(B2, adopt_key_db), MAIN_COST),
                     leung=trade_stats(gather(B, lkey(uni="db")), MAIN_COST),
                     prov_flags=B["meta"]["prov_flags"] and {k: v for k, v in B["meta"]["prov_flags"].items() if k != "by_day"},
                     pass_noprov=pass_summary(B2))
    # 시장 유닛 일치율 — DB 구간에 KOSPI 근사 지수를 이어 만든다(현재 시총 × 가격비로 그날 시총 근사)
    mcols, mrows = ext["master"]
    mx = {c: i for i, c in enumerate(mcols)}
    capnow = {r[mx["ticker"]]: (r[mx["hts_avls_eok"]] or 0) for r in mrows}
    ks = [j for j, t in enumerate(Q.tickers) if Q.market.get(t) == "KOSPI"
          and Q.meta["group_code"].get(t) in (None, "", "ST")]
    cq = Q.c[:, ks]
    last = np.array([cq[np.where(np.isfinite(cq[:, k]))[0][-1], k] if np.isfinite(cq[:, k]).any() else np.nan
                     for k in range(cq.shape[1])])
    w_now = np.array([capnow.get(Q.tickers[j], 0) for j in ks], dtype=float)
    kidx = np.full(nB, np.nan)
    kidx[0] = 1.0
    for i in range(1, nB):
        r = cq[i] / cq[i - 1] - 1.0
        w = w_now * cq[i - 1] / last
        ok = np.isfinite(r) & np.isfinite(w) & (w > 0) & (np.abs(r) < 0.3)
        kidx[i] = kidx[i - 1] * (1.0 + (np.sum(w[ok] * r[ok]) / np.sum(w[ok]) if ok.any() else 0.0))
    mu_k = mu_exec_series(kidx)
    mu_e = B["mu_exec"]
    both = np.isfinite(mu_k) & np.isfinite(mu_e)
    j200 = Q.tickers.index("069500")
    corr_idx = float(np.corrcoef(np.diff(np.log(kidx)), np.diff(np.log(Q.c[:, j200])))[0, 1])
    res["db"]["market_unit_agreement"] = dict(days=int(both.sum()),
                                              agree=float(np.mean(mu_k[both] == mu_e[both])) if both.any() else None,
                                              zero_agree=float(np.mean((mu_k[both] == 0) == (mu_e[both] == 0))) if both.any() else None,
                                              daily_ret_corr_kospi_approx_vs_069500=corr_idx,
                                              note="DB 구간 KOSPI 근사 = 현재 시총(hts_avls_eok) × 가격비 가중")
    # 장세 축 · 기존 전략 상관 (§3.7)
    c200 = Q.c[:, j200]
    erB = er_series(c200)
    erB_bounds = J.er_terciles(erB, cutB)
    erB_b = J.er_bucket(erB, erB_bounds)
    pnl, budget, pnl_meta = existing_daily_returns(ext, Q)
    tcols, trows = ext["trades"]
    tix = {c: i for i, c in enumerate(tcols)}
    first_trade = min(kst_date(r[tix["timestamp"]]) for r in trows)
    day_str = np.array([str(d) for d in Q.dates])
    win_main = day_str >= first_trade
    win_alt = day_str >= EXISTING_WINDOW_ALT_START
    ex_ret, ex_simple = combine_existing(pnl, budget, win_main)
    ex_ret_alt, _ = combine_existing(pnl, budget, win_alt)
    pnl_f, budget_f, pnl_meta_f = existing_daily_returns(ext, Q, scale_check=True)   # 사후 발견 1 고친 판
    ex_ret_f, ex_simple_f = combine_existing(pnl_f, budget_f, win_main)
    ex_ret_f_alt, _ = combine_existing(pnl_f, budget_f, win_alt)
    accB = account(dbt, Q.c, nB, 2, MAIN_COST)
    mr_ret = accB["daily_ret"]

    def corr(mask, ex=None):
        ex = ex_ret if ex is None else ex
        m = mask & np.isfinite(ex) & np.isfinite(mr_ret)
        if m.sum() < 5 or np.std(mr_ret[m]) == 0 or np.std(ex[m]) == 0:
            return dict(n=int(m.sum()), corr=None)
        return dict(n=int(m.sum()), corr=float(np.corrcoef(mr_ret[m], ex[m])[0, 1]),
                    mr_mean=float(mr_ret[m].mean()), ex_mean=float(ex[m].mean()))

    allm = np.ones(nB, dtype=bool)
    allm[0] = False
    rolling = {}
    for w in (20, 60):
        vals = []
        for i in range(w, nB):
            a1, b1 = mr_ret[i - w + 1:i + 1], ex_ret[i - w + 1:i + 1]
            if np.all(np.isfinite(b1)) and np.std(a1) > 0 and np.std(b1) > 0:
                vals.append(np.corrcoef(a1, b1)[0, 1])
        rolling[str(w)] = dict(n=len(vals), mean=float(np.mean(vals)) if vals else None,
                               min=float(np.min(vals)) if vals else None, max=float(np.max(vals)) if vals else None)
    fin = np.isfinite(ex_ret)
    res["correlation_db"] = dict(
        existing_meta=pnl_meta, strategies=sorted(pnl.keys()),
        existing_window=dict(main_start=first_trade, alt_start=EXISTING_WINDOW_ALT_START, end=str(Q.dates[-1]),
                             main_days_with_data=int(fin.sum()),
                             abs_ret_gt_50pct_days=int(np.sum(np.abs(ex_ret[fin]) > 0.5)),
                             ex_mean=float(ex_ret[fin].mean()) if fin.any() else None,
                             ex_min=float(ex_ret[fin].min()) if fin.any() else None,
                             ex_max=float(ex_ret[fin].max()) if fin.any() else None),
        er_low_simple_sum=corr(allm & (erB_b == 0), ex_simple),
        posthoc1_scale_fixed=dict(
            existing_meta=pnl_meta_f,
            ex_mean=float(np.nanmean(ex_ret_f)), ex_min=float(np.nanmin(ex_ret_f)), ex_max=float(np.nanmax(ex_ret_f)),
            abs_ret_gt_50pct_days=int(np.sum(np.abs(ex_ret_f[np.isfinite(ex_ret_f)]) > 0.5)),
            all=corr(allm, ex_ret_f), by_er={str(b): corr(allm & (erB_b == b), ex_ret_f) for b in (0, 1, 2)},
            by_mu={str(m): corr(allm & (mu_e == m), ex_ret_f) for m in (1.0, 0.75, 0.5, 0.0)},
            er_low_simple_sum=corr(allm & (erB_b == 0), ex_simple_f),
            er_low_alt_window=corr(allm & (erB_b == 0), ex_ret_f_alt),
            T3_verdict=None),
        er_low_alt_window=corr(allm & (erB_b == 0), ex_ret_alt),
        all_alt_window=corr(allm, ex_ret_alt),
        mr_account=dict(n_filled=accB["n_filled"], n_signal=accB["n_signal"], net=accB["net_return"],
                        unaffordable_ratio=accB["unaffordable_ratio"]),
        all=corr(allm), rolling=rolling, er_bounds_front60=erB_bounds,
        by_er={str(b): corr(allm & (erB_b == b)) for b in (0, 1, 2)},
        by_mu={str(m): corr(allm & (mu_e == m)) for m in (1.0, 0.75, 0.5, 0.0)},
        cross={f"mu={m}|er={b}": corr(allm & (mu_e == m) & (erB_b == b)) for m in (1.0, 0.75, 0.5, 0.0) for b in (0, 1, 2)},
        back40_er_low=corr(allm & (erB_b == 0) & (np.arange(nB) >= cutB)),
    )
    t3f = res["correlation_db"]["posthoc1_scale_fixed"]["by_er"]["0"]
    res["correlation_db"]["posthoc1_scale_fixed"]["T3_verdict"] = (
        "판정 불가" if t3f["corr"] is None else ("통과" if t3f["corr"] < 0 else "실패"))
    t3 = res["correlation_db"]["by_er"]["0"]
    th["T3"] = dict(er_low=t3, verdict=("판정 불가(평균회귀 일수익률 분산 0 또는 표본 < 5)" if t3["corr"] is None
                                        else ("통과" if t3["corr"] < 0 else "실패")))
    res["thresholds"] = th
    res["records"] = dict(archive=record_counts(A, adopt_key_arch) | dict(
                              halt_windows_resid=res["pass"]["archive"]["resid"]["halt_windows"]),
                          db=record_counts(B, adopt_key_db) | dict(
                              halt_windows_resid=res["pass"]["db"]["resid"]["halt_windows"]),
                          leung_no_entry_archive=leung_fail_rate(A, lkey()),
                          leung_no_entry_db=leung_fail_rate(B, lkey(uni="db")))
    res["adopted_key"] = dict(archive=adopt_key_arch, db=adopt_key_db)
    res["clean_exit_cards"] = dict(reasons_archive=arch_full.get("reasons"))
    with open(os.path.join(out_dir, "results.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=_jd)
    _write_csv(os.path.join(out_dir, "z_selection.csv"), sel_rows)
    print(json.dumps(th, ensure_ascii=False, indent=1, default=_jd))
    print(json.dumps(res["z_vs_leung"]["conditions"], ensure_ascii=False))


def _part(a, cut, which):
    return a[a[:, CI["sig_day"]] < cut] if which == "front" else a[a[:, CI["sig_day"]] >= cut]


def _count(d):
    out = defaultdict(int)
    for v in d.values():
        out[v] += 1
    return dict(out)


def _jd(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def _write_csv(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["entry_z", "exit_z", "part", "n", "win", "mean_net", "median_net", "pf", "held"])
        for r in rows:
            for part in ("front", "back", "full"):
                s = r[part]
                w.writerow([r["ez"], r["xz"], part, s.get("n"), s.get("win"), s.get("mean_net"),
                            s.get("median_net"), s.get("pf"), s.get("held")])


if __name__ == "__main__":
    main()
