"""cycle346 — 대순환 MACD(하) 골든크로스 vs 고지로 현행 strict entry 짝지은 비교 (읽기 전용).

실행 = 운영 backend 컨테이너 안(`python /tmp/cycle346.py`). DB 는 SELECT 만.
지표 = 저장소 정본 `src.engine.kojiro_indicators.enrich` 를 그대로 import 한다.

정의
- strict(A)  : ATR/종가 ∈ [1%,6%] ∧ stage==1 ∧ EMA5/20/40 우상향 ∧ 최근 5봉 내 6→1 ∧ 종가>EMA5
- gc3        : macd3[t-1] <= sig3[t-1] ∧ macd3[t] > sig3[t]
- B6         : ATR 밴드 ∧ stage==6 ∧ gc3      (원전 본매매 게이트)
- B0         : ATR 밴드 ∧ gc3                  (무게이트)
- 진입가     : 신호봉 다음 날 시가. 갭 게이트(+5% 이상 / -4% 이하) 걸리면 그날 스킵(다음 신호일 재시도).
- 청산       : kojiro 운영 규칙을 일봉으로 재현 — hard_stop -8% · 2ATR tighten-only floor(ATR = D-1 완성봉)
               · 브레이크이븐 1.5ATR(운영 DB 값) · stage3(D-1 완성봉 stage==3 → 당일 시가, 진입일 제외)
               · 2.5ATR 샹들리에. 시가가 손절선 아래면 시가 체결(갭 관통), 아니면 저가가 닿으면 손절선 체결.
               손절선은 **전일까지의 정보**로 정하고, 당일 고가 갱신은 판정 뒤에 반영한다.
- R          : (청산가 − 진입가) / 초기위험, 초기위험 = 진입가 − max(진입가×0.92, 진입가 − 2×ATR_진입)
"""
import asyncio
import json
import os
import sys

import numpy as np
import pandas as pd
import asyncpg

sys.path.insert(0, "/app")
from src.engine.kojiro_indicators import KojiroIndicatorConfig, enrich  # noqa: E402

ETF_KEYWORDS = ("KODEX", "TIGER", "KBSTAR", "KOSEF", "ARIRANG", "SOL", "ACE",
                "RISE", "KoAct", "PLUS", "TIMEFOLIO", "WOORI", "FOCUS",
                "HANARO", "히어로즈", "마이티", "BNK", "MASTER", "WON",
                "ETN", "선물", "인버스", "레버리지", "채권", "혼합")

P = dict(atr_min=0.01, atr_max=0.06, fresh=5, hard=-8.0, stop_atr=2.0, trail_atr=2.5,
         be_atr=1.5, gap_up=5.0, gap_dn=-4.0)
WARMUP = 80
PAIR_WIN = 40
RNG = np.random.default_rng(346)


def stage_recently(st, i, within):
    lo = max(0, i - within)
    for k in range(lo, i):
        if st[k] == 6 and st[k + 1] == 1:
            return True
    return False


def simulate(df, t, reason_tag=""):
    """신호봉 t → t+1 시가 진입. 반환 dict 또는 None(데이터 없음)."""
    n = len(df)
    if t + 1 >= n:
        return None
    o, h, l, c = df["open"].values, df["high"].values, df["low"].values, df["close"].values
    atr = df["atr"].values
    stg = df["stage"].values
    E = float(o[t + 1])
    a0 = float(atr[t])
    if E <= 0 or a0 <= 0:
        return None
    pct_line = E * (1 + P["hard"] / 100)
    floor = E - P["stop_atr"] * a0
    init_risk = E - max(pct_line, floor)
    hsb = E
    mfe = 0.0
    for j in range(t + 1, n):
        a = float(atr[j - 1]) if j - 1 >= t else a0
        if j > t + 1:
            floor = max(floor, E - P["stop_atr"] * a)
            if stg[j - 1] == 3:
                px = float(o[j])
                return dict(E=E, X=px, why="stage3", days=j - t - 1, j=j, R=(px - E) / init_risk,
                            ret=(px / E - 1) * 100, mfe=mfe, open=False)
        be = E if hsb >= E + P["be_atr"] * a else -1e18
        chand = hsb - P["trail_atr"] * a
        stop_lvl = max(pct_line, floor, be)
        lvl = max(stop_lvl, chand)
        why = "trail" if chand >= stop_lvl else ("hard" if pct_line >= max(floor, be) else
                                                  ("breakeven" if be >= floor else "atr_stop"))
        if o[j] <= lvl and j > t + 1:
            px = float(o[j])
            return dict(E=E, X=px, why=why, days=j - t - 1, j=j, R=(px - E) / init_risk,
                        ret=(px / E - 1) * 100, mfe=mfe, open=False)
        if l[j] <= lvl:
            px = float(min(lvl, o[j])) if j > t + 1 else float(lvl)
            return dict(E=E, X=px, why=why, days=j - t - 1, j=j, R=(px - E) / init_risk,
                        ret=(px / E - 1) * 100, mfe=mfe, open=False)
        hsb = max(hsb, float(h[j]))
        mfe = max(mfe, (hsb - E) / init_risk)
    px = float(c[n - 1])
    return dict(E=E, X=px, why="open_eod", days=n - 1 - t - 1, j=n - 1, R=(px - E) / init_risk,
                ret=(px / E - 1) * 100, mfe=mfe, open=True)


def gap_ok(df, t):
    if t + 1 >= len(df):
        return False
    pc = df["close"].values[t]
    op = df["open"].values[t + 1]
    if pc <= 0 or op <= 0:
        return False
    g = (op - pc) / pc * 100
    return P["gap_dn"] < g < P["gap_up"]


def sequential(df, sig, ticker, rule):
    trades = []
    n = len(df)
    t = WARMUP
    while t < n - 1:
        if sig[t] and gap_ok(df, t):
            r = simulate(df, t)
            if r is None:
                break
            r.update(ticker=ticker, rule=rule, t=t, date=str(df.index[t]),
                     exit_date=str(df.index[r["j"]]))
            trades.append(r)
            t = r["j"] + 1  # 청산 다음 봉부터 재진입 평가(sold_today 근사)
            continue
        t += 1
    return trades


def stats(arr):
    arr = np.asarray(arr, dtype=float)
    if len(arr) == 0:
        return {}
    bs = RNG.choice(arr, size=(4000, len(arr)), replace=True).mean(axis=1)
    return dict(n=int(len(arr)), mean=float(arr.mean()), median=float(np.median(arr)),
                q1=float(np.percentile(arr, 25)), q3=float(np.percentile(arr, 75)),
                win=float((arr > 0).mean()), ci_lo=float(np.percentile(bs, 2.5)),
                ci_hi=float(np.percentile(bs, 97.5)))


def cluster_ci(trades, key="date"):
    """진입일 단위 클러스터 부트스트랩(같은 날 동시 신호의 상관 반영)."""
    if not trades:
        return None
    df = pd.DataFrame(trades)
    g = df.groupby(key)["R"].agg(["sum", "count"])
    s, c = g["sum"].values, g["count"].values
    idx = RNG.integers(0, len(g), size=(4000, len(g)))
    m = s[idx].sum(axis=1) / c[idx].sum(axis=1)
    return [float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))]


def max_losing_streak(trades):
    tr = sorted(trades, key=lambda x: (x["exit_date"], x["ticker"]))
    best = cur = 0
    for x in tr:
        if x["R"] < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def summarize(trades):
    if not trades:
        return {}
    R = [x["R"] for x in trades]
    ret = [x["ret"] for x in trades]
    whys = pd.Series([x["why"] for x in trades]).value_counts().to_dict()
    out = dict(R=stats(R), ret=stats(ret), ret_net=stats([r - 0.25 for r in ret]),
               R_cluster_ci=cluster_ci(trades), streak=max_losing_streak(trades),
               why=whys, open_n=int(sum(x["open"] for x in trades)),
               days_med=float(np.median([x["days"] for x in trades])),
               stop_rate=float(np.mean([x["why"] in ("hard", "atr_stop") for x in trades])))
    return out


async def main():
    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
    conn = await asyncpg.connect(dsn)
    uni = await conn.fetch(
        "select ticker, name from stock_master where hts_avls_eok >= 500 "
        "and acml_tr_pbmn_won >= 1000000000")
    tickers = [r["ticker"] for r in uni
               if r["ticker"] and len(r["ticker"]) == 6 and r["ticker"].isdigit()
               and not any(k in (r["name"] or "") for k in ETF_KEYWORDS)]
    cfg = KojiroIndicatorConfig()
    diag = dict(universe=len(tickers), no_data=0, short=0, lock_rows_tickers=0, jump_excluded=0, used=0,
                bars=0)
    all_trades = {"A": [], "B6": [], "B0": []}
    pairs, pairs6 = [], []
    gc_events = []
    signal_counts = {"A_days": 0, "A_episodes": 0, "B6": 0, "B0": 0, "gc3_raw": 0}
    first_date, last_date = None, None
    CH = 100
    for ci in range(0, len(tickers), CH):
        chunk = tickers[ci:ci + CH]
        rows = await conn.fetch(
            "select ticker, bas_dd, open_price, high_price, low_price, close_price, volume, "
            "flng_cls_code, prtt_rate from stock_master_daily where ticker = any($1::text[]) "
            "order by ticker, bas_dd", chunk)
        by = {}
        for r in rows:
            by.setdefault(r["ticker"], []).append(r)
        for tk in chunk:
            rs = by.get(tk)
            if not rs:
                diag["no_data"] += 1
                continue
            # 락 행(배당락 02·권리락 03 등)은 제외하지 않는다 — 2026-09-24 확인: 락 행 표본 400건 중
            # 전일 대비 31% 초과 불연속 0건(일봉이 수정주가로 적재됨). 대신 아래 31% 점프 필터로 거른다.
            diag["lock_rows_tickers"] += int(any((r["flng_cls_code"] not in (None, "", "00")) for r in rs))
            df = pd.DataFrame({
                "open": [float(r["open_price"] or 0) for r in rs],
                "high": [float(r["high_price"] or 0) for r in rs],
                "low": [float(r["low_price"] or 0) for r in rs],
                "close": [float(r["close_price"] or 0) for r in rs],
                "volume": [float(r["volume"] or 0) for r in rs],
            }, index=[r["bas_dd"] for r in rs])
            df = df[(df["close"] > 0) & (df["open"] > 0)]
            if len(df) < WARMUP + 20:
                diag["short"] += 1
                continue
            chg = df["close"].pct_change().abs()
            if (chg > 0.31).any():
                diag["jump_excluded"] += 1
                continue
            e = enrich(df, cfg)
            diag["used"] += 1
            diag["bars"] += len(e)
            fd, ld = e.index[0], e.index[-1]
            first_date = fd if first_date is None else min(first_date, fd)
            last_date = ld if last_date is None else max(last_date, ld)
            n = len(e)
            st = [None if (s is None or (isinstance(s, float) and np.isnan(s))) else int(s)
                  for s in e["stage"].tolist()]
            close = e["close"].values
            ema_s = e["ema_s"].values
            atr = e["atr"].values
            up = (e["ema_s_up"] & e["ema_m_up"] & e["ema_l_up"]).values
            m3, s3 = e["macd3"].values, e["macd3_sig"].values
            band = (atr / close >= P["atr_min"]) & (atr / close <= P["atr_max"])
            A = np.zeros(n, bool)
            gc = np.zeros(n, bool)
            for i in range(1, n):
                gc[i] = (m3[i - 1] <= s3[i - 1]) and (m3[i] > s3[i])
                if i < WARMUP:
                    continue
                if band[i] and st[i] == 1 and up[i] and close[i] > ema_s[i] and \
                        stage_recently(st, i, P["fresh"]):
                    A[i] = True
            gc[:WARMUP] = False
            B0 = gc & band
            B6 = B0 & np.array([s == 6 for s in st])
            signal_counts["A_days"] += int(A.sum())
            signal_counts["B6"] += int(B6.sum())
            signal_counts["B0"] += int(B0.sum())
            signal_counts["gc3_raw"] += int(gc.sum())
            all_trades["A"] += sequential(e, A, tk, "A")
            all_trades["B6"] += sequential(e, B6, tk, "B6")
            all_trades["B0"] += sequential(e, B0, tk, "B0")

            # 1) 짝짓기 — strict 에피소드 시작점 기준, 직전 40봉 안 마지막 gc3
            ep = [i for i in range(WARMUP, n) if A[i] and not A[i - 1]]
            signal_counts["A_episodes"] += len(ep)
            op = e["open"].values
            for tA in ep:
                if tA + 1 >= n:
                    continue
                PA = op[tA + 1]
                for (lst, gate) in ((pairs, None), (pairs6, 6)):
                    tg = None
                    for k in range(tA, max(tA - PAIR_WIN, 0) - 1, -1):
                        if gc[k] and (gate is None or st[k] == gate):
                            tg = k
                            break
                    rec = dict(ticker=tk, tA=str(e.index[tA]), paired=tg is not None)
                    if tg is not None:
                        PG = op[tg + 1]
                        rec.update(lead=int(tA - tg), disc=float((PA - PG) / PA * 100),
                                   stage_at_gc=st[tg])
                        rA = simulate(e, tA)
                        rG = simulate(e, tg)
                        if rA and rG:
                            rec.update(RA=rA["R"], RG=rG["R"], retA=rA["ret"], retG=rG["ret"],
                                       G_exit_before_A=bool(rG["j"] <= tA + 1),
                                       G_why=rG["why"], A_why=rA["why"],
                                       G_open=rG["open"], A_open=rA["open"])
                    lst.append(rec)
            # 2) gc3 사건별 운명 — 40봉 안에 strict 에피소드가 왔는가
            ep_set = set(ep)
            for k in np.where(B0)[0]:
                if k + PAIR_WIN >= n:
                    censored = True
                else:
                    censored = False
                hit = any((k <= x <= k + PAIR_WIN) for x in ep_set)
                reach1 = any(st[x] == 1 for x in range(k, min(n, k + PAIR_WIN + 1)))
                r = simulate(e, int(k))
                if r is None:
                    continue
                gc_events.append(dict(ticker=tk, stage=st[k], censored=censored, hit=hit,
                                      reach1=reach1, R=r["R"], ret=r["ret"], why=r["why"],
                                      open=r["open"]))
    await conn.close()

    out = dict(diag=diag, period=[str(first_date), str(last_date)], signal_counts=signal_counts)
    out["trades"] = {k: summarize(v) for k, v in all_trades.items()}

    def pair_summary(lst):
        d = pd.DataFrame(lst)
        res = dict(n_episodes=int(len(d)), paired=int(d["paired"].sum()))
        p = d[d["paired"]]
        if len(p):
            res["lead"] = stats(p["lead"].values)
            res["disc"] = stats(p["disc"].values)
            res["disc_neg_rate"] = float((p["disc"] < 0).mean())
            res["stage_at_gc"] = p["stage_at_gc"].value_counts().to_dict()
            q = p.dropna(subset=["RA", "RG"])
            q = q[~(q["A_open"].astype(bool) | q["G_open"].astype(bool))]
            res["closed_pairs"] = int(len(q))
            res["RA"] = stats(q["RA"].values)
            res["RG"] = stats(q["RG"].values)
            res["dR"] = stats((q["RG"] - q["RA"]).values)
            res["dret"] = stats((q["retG"] - q["retA"]).values)
            res["G_better_rate"] = float((q["retG"] > q["retA"]).mean())
            res["G_exit_before_A"] = float(q["G_exit_before_A"].mean())
            ge = q[q["G_exit_before_A"]]
            res["G_exit_before_A_detail"] = dict(n=int(len(ge)), G_why=ge["G_why"].value_counts().to_dict(),
                                                 retG_mean=float(ge["retG"].mean()) if len(ge) else None,
                                                 retA_mean=float(ge["retA"].mean()) if len(ge) else None)
            by_lead = {}
            for name, lo, hi in (("0", 0, 0), ("1-5", 1, 5), ("6-15", 6, 15), ("16-40", 16, 40)):
                s = q[(q["lead"] >= lo) & (q["lead"] <= hi)]
                if len(s):
                    by_lead[name] = dict(n=int(len(s)), disc_med=float(s["disc"].median()),
                                         dret_mean=float((s["retG"] - s["retA"]).mean()),
                                         dret_med=float((s["retG"] - s["retA"]).median()),
                                         dR_mean=float((s["RG"] - s["RA"]).mean()))
            res["by_lead"] = by_lead
        return res

    out["pair_any"] = pair_summary(pairs)
    out["pair_stage6"] = pair_summary(pairs6)
    g = pd.DataFrame(gc_events)
    gd = {}
    for name, sub in (("B0_all", g), ("B6_only", g[g["stage"] == 6])):
        s = sub[~sub["censored"]]
        gd[name] = dict(n=int(len(sub)), judged=int(len(s)),
                        hit_rate=float(s["hit"].mean()), reach1_rate=float(s["reach1"].mean()))
        for lab, part in (("hit", s[s["hit"]]), ("miss", s[~s["hit"]]),
                          ("no_stage1", s[~s["reach1"]])):
            gd[name][lab] = dict(R=stats(part["R"].values), ret=stats(part["ret"].values),
                                 why=part["why"].value_counts().to_dict(),
                                 open_n=int(part["open"].sum()))
    out["gc_fate"] = gd
    out["trade_rows"] = [[k, x["ticker"], x["date"], x["exit_date"], round(x["R"], 4), round(x["ret"], 3), x["why"],
                          x["open"]] for k, v in all_trades.items() for x in v]
    out["pair_rows"] = [p for p in pairs if p.get("RA") is not None]
    out["pair6_rows"] = [p for p in pairs6 if p.get("RA") is not None]
    out["gc_rows"] = gc_events
    print(json.dumps(out, ensure_ascii=False, default=str, indent=1))


asyncio.run(main())
