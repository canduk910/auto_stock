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
    return dict(n=n, win=float(np.mean(net > 0)), mean_net=float(net.mean()),
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
        u = o = ever = consec = anyu = 0
        codes = np.zeros(9)
        for r in payload["results"]:
            if market and payload["market"].get(r["ticker"]) != market:
                continue
            ps = r["pass"][m]
            u += ps["n_usable"]
            o += ps["n_ok"]
            codes += ps["codes"]
            anyu += ps["any_usable"]
            ever += ps["ever"]
            consec += ps["consec"]
        out[m] = dict(windows=u, ok=o, rate=o / u if u else float("nan"),
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
    tried = fails = 0
    for r in payload["results"]:
        t, f = r["leung_fail"].get(key, (0, 0))
        tried += t
        fails += f
    return dict(tried=tried, fails=fails, rate=fails / tried if tried else float("nan"))


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

def existing_daily_returns(ext, P):
    cols, rows = ext["trades"]
    ix = {c: i for i, c in enumerate(cols)}
    di = {str(d): i for i, d in enumerate(P.dates)}
    tj = {t: j for j, t in enumerate(P.tickers)}
    n = len(P.dates)
    flows = defaultdict(lambda: np.zeros(n))   # (strategy, ticker) → 매수 +수량 / 매도 −수량
    cash = defaultdict(lambda: np.zeros(n))    # 매수 −금액 / 매도 +금액
    skipped = 0
    for r in rows:
        d = r[ix["timestamp"]][:10]
        if d not in di:
            skipped += 1
            continue
        k = (r[ix["strategy"]], r[ix["ticker"]])
        q = float(r[ix["quantity"]])
        px = float(r[ix["price"]])
        sgn = 1.0 if r[ix["trade_type"]] == "BUY" else -1.0
        flows[k][di[d]] += sgn * q
        cash[k][di[d]] -= sgn * q * px
    pnl = defaultdict(lambda: np.zeros(n))
    missing_close = 0
    for (strat, tk), fl in flows.items():
        qty = np.cumsum(fl)
        if tk in tj:
            cl = P.c[:, tj[tk]].copy()
            # 결측 종가는 직전 값으로 (평가가 끊기지 않게)
            for i in range(1, n):
                if not np.isfinite(cl[i]):
                    cl[i] = cl[i - 1]
        else:
            missing_close += 1
            continue
        val = np.nan_to_num(qty * cl)
        pnl[strat] += np.diff(np.concatenate([[0.0], val])) + cash[(strat, tk)]
    return pnl, dict(skipped_rows=skipped, tickers_without_close=missing_close)


def main():
    scratch, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    A = pickle.load(open(os.path.join(scratch, "mr_arch.pkl"), "rb"))
    B = pickle.load(open(os.path.join(scratch, "mr_db.pkl"), "rb"))
    B2 = pickle.load(open(os.path.join(scratch, "mr_db_noprov.pkl"), "rb"))
    P = D.load_archive()
    ext = D.load_db_extract(os.path.join(scratch, "mr_db_extract.jsonl.gz"))
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
    lit_pass = False   # 문헌 재현 (a) — summary 의 수치 참조: b*_L 0.5673 vs 0.5570, d*_L 0.5048 vs 0.4978
    cond = {
        "1_back_mean_higher_and_boot_lo_gt_0": bool(diff[0] > 0 and diff[1] > 0),
        "2_solver_fail_lt_10pct": bool(fail["rate"] < 0.10),
        "3_literature_replicated": lit_pass,
        "4_mdd_le_1.2x": bool(abs(acc_l["mdd_period"]) <= 1.2 * abs(acc_z["mdd_period"])),
    }
    res["z_vs_leung"] = dict(back_z=trade_stats(zb, MAIN_COST), back_leung=trade_stats(lb_, MAIN_COST),
                             diff_leung_minus_z=dict(mean=diff[0], lo90=diff[1], hi90=diff[2]),
                             solver=fail, mdd_back_slots2=dict(z=acc_z["mdd_period"], leung=acc_l["mdd_period"]),
                             conditions=cond, adopt_leung=all(cond.values()))
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
    pnl, pnl_meta = existing_daily_returns(ext, Q)
    tot = sum(pnl.values()) if pnl else np.zeros(nB)
    pcols, prows = ext.get("perf_total", [None, []])
    asset = {}
    if pcols:
        px = {c: i for i, c in enumerate(pcols)}
        for r in prows:
            if r[px["strategy"]] == "total":
                asset[r[px["date"]][:10]] = float(r[px["total_asset"]])
    den = np.array([asset.get(str(Q.dates[i - 1]), np.nan) if i > 0 else np.nan for i in range(nB)])
    den = np.where(np.isfinite(den) & (den > 0), den, 5_000_000.0)
    ex_ret = tot / den
    accB = account(dbt, Q.c, nB, 2, MAIN_COST)
    mr_ret = accB["daily_ret"]

    def corr(mask):
        m = mask & np.isfinite(ex_ret) & np.isfinite(mr_ret)
        if m.sum() < 5 or np.std(mr_ret[m]) == 0 or np.std(ex_ret[m]) == 0:
            return dict(n=int(m.sum()), corr=None)
        return dict(n=int(m.sum()), corr=float(np.corrcoef(mr_ret[m], ex_ret[m])[0, 1]),
                    mr_mean=float(mr_ret[m].mean()), ex_mean=float(ex_ret[m].mean()))

    allm = np.ones(nB, dtype=bool)
    allm[0] = False
    rolling = {}
    for w in (20, 60):
        vals = []
        for i in range(w, nB):
            a1, b1 = mr_ret[i - w + 1:i + 1], ex_ret[i - w + 1:i + 1]
            if np.std(a1) > 0 and np.std(b1) > 0:
                vals.append(np.corrcoef(a1, b1)[0, 1])
        rolling[str(w)] = dict(n=len(vals), mean=float(np.mean(vals)) if vals else None,
                               min=float(np.min(vals)) if vals else None, max=float(np.max(vals)) if vals else None)
    res["correlation_db"] = dict(
        existing_meta=pnl_meta, strategies=sorted(pnl.keys()),
        mr_account=dict(n_filled=accB["n_filled"], n_signal=accB["n_signal"], net=accB["net_return"],
                        unaffordable_ratio=accB["unaffordable_ratio"]),
        all=corr(allm), rolling=rolling, er_bounds_front60=erB_bounds,
        by_er={str(b): corr(allm & (erB_b == b)) for b in (0, 1, 2)},
        by_mu={str(m): corr(allm & (mu_e == m)) for m in (1.0, 0.75, 0.5, 0.0)},
        cross={f"mu={m}|er={b}": corr(allm & (mu_e == m) & (erB_b == b)) for m in (1.0, 0.75, 0.5, 0.0) for b in (0, 1, 2)},
        back40_er_low=corr(allm & (erB_b == 0) & (np.arange(nB) >= cutB)),
    )
    t3 = res["correlation_db"]["by_er"]["0"]
    th["T3"] = dict(er_low=t3, verdict=("판정 불가(평균회귀 일수익률 분산 0 또는 표본 < 5)" if t3["corr"] is None
                                        else ("통과" if t3["corr"] < 0 else "실패")))
    res["thresholds"] = th
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
