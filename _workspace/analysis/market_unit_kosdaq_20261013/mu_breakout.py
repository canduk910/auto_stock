"""단순 돌파 대용 모형(prereg §2.3) — 진입·청산을 만들어 trades.parquet 로 저장. 시장 유닛은 걸지 않는다."""
import glob
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[3]
ARCH = ROOT / "data/archive/krx_daily_long"
OUT = Path(__file__).resolve().parent
COLS = ["ticker", "name", "bas_dd", "open_adj", "high_adj", "low_adj", "close_adj", "volume", "trade_value", "mktcap", "market", "no_trade"]


def load():
    d = pd.concat([pd.read_parquet(x, columns=COLS) for x in sorted(glob.glob(str(ARCH / "unified/*.parquet")))], ignore_index=True)
    d = d[d.ticker.str.fullmatch(r"\d{6}")].copy()
    d["market"] = d.market.replace({"KOSDAQ GLOBAL": "KOSDAQ"})
    d = d.sort_values(["ticker", "bas_dd"]).reset_index(drop=True)
    return d


def features(d):
    g = d.groupby("ticker", sort=False)
    d["traded"] = (~d.no_trade) & (d.volume > 0) & (d.open_adj > 0)
    d["bar"] = g.cumcount() + 1
    pc = g.close_adj.shift(1)
    tr = np.maximum(d.high_adj - d.low_adj, np.maximum((d.high_adj - pc).abs(), (d.low_adj - pc).abs()))
    d["tr"] = tr
    d["N"] = d.groupby("ticker", sort=False).tr.transform(lambda s: s.rolling(20).mean())
    d["hh20"] = g.high_adj.transform(lambda s: s.shift(1).rolling(20).max())
    d["ll10"] = g.low_adj.transform(lambda s: s.shift(1).rolling(10).min())
    d["sma60"] = g.close_adj.transform(lambda s: s.rolling(60).mean())
    d["tv20"] = g.trade_value.transform(lambda s: s.rolling(20).mean())
    # 위반 표시: 앞 62봉 안
    j = pd.read_csv(ARCH / "meta/unified_jump_flags.csv", dtype={"ticker": str}, parse_dates=["bas_dd"])[["ticker", "bas_dd"]]
    j["jump"] = 1
    d = d.merge(j, on=["ticker", "bas_dd"], how="left"); d["jump"] = d.jump.fillna(0)
    d["jump62"] = d.groupby("ticker", sort=False).jump.transform(lambda s: s.rolling(62, min_periods=1).sum())
    # 그날 횡단면 백분위(6자리 숫자 전 종목)
    d["cap_pct"] = d.groupby("bas_dd").mktcap.rank(pct=True, ascending=False)
    d["tv_pct"] = d.groupby("bas_dd").tv20.rank(pct=True, ascending=False)
    common = d.ticker.str.endswith("0") & ~d.name.fillna("").str.contains("스팩") & (d.mktcap > 0)
    d["common"] = common
    d["kq_rank"] = d[common & (d.market == "KOSDAQ")].groupby("bas_dd").mktcap.rank(ascending=False)
    d["kp_rank"] = d[common & (d.market == "KOSPI")].groupby("bas_dd").mktcap.rank(ascending=False)
    d["sig"] = (common & d.traded & (d.bar >= 62) & (d.close_adj > d.hh20) & (d.close_adj > d.sma60)
                & (d.cap_pct <= 0.5) & (d.tv_pct <= 0.5) & (d.jump62 == 0) & (d.N > 0))
    return d


def simulate(d, costs):
    rows = []
    for tk, x in d.groupby("ticker", sort=False):
        sig = x.sig.values
        if not sig.any():
            continue
        o, h, l, c = x.open_adj.values, x.high_adj.values, x.low_adj.values, x.close_adj.values
        tr, N, ll10, dt = x.traded.values, x.N.values, x.ll10.values, x.bas_dd.values
        n = len(x); i = 0
        idx = np.flatnonzero(sig)
        free_from = 0
        for s in idx:
            e = s + 1
            if s < free_from or e >= n:
                continue
            if not tr[e] or o[e] <= 0 or o[e] / c[s] - 1 >= 0.05:
                continue
            ep = o[e]; stop = ep - 2 * N[s]
            if stop <= 0:
                continue
            pending = False; xp = None; why = None; t = e
            while t < n:
                if tr[t]:
                    if pending:
                        xp, why = o[t], "CH"; break
                    if l[t] <= stop:
                        xp, why = (min(o[t], stop) if t > e else stop), "SL"; break
                    if t - e + 1 >= 120:
                        xp, why = c[t], "TM"; break
                    if not np.isnan(ll10[t]) and c[t] < ll10[t]:
                        pending = True
                t += 1
            if xp is None:
                t = n - 1; xp, why = c[t], "END"
            free_from = t + 1
            rows.append((tk, x.market.values[s], dt[s], dt[e], dt[t], ep, xp, 2 * N[s] / ep, t - e + 1, why,
                         x.kq_rank.values[s], x.kp_rank.values[s], x.mktcap.values[s]))
    T = pd.DataFrame(rows, columns=["ticker", "market", "sig_dd", "entry_dd", "exit_dd", "entry", "exit", "risk", "bars", "why", "kq_rank", "kp_rank", "mktcap"])
    cs = pd.read_csv(ARCH / "meta/regime_costs.csv", parse_dates=["from"])
    T = T.sort_values("entry_dd")
    T = pd.merge_asof(T, cs[["from", "round_trip_pct_assumed"]].sort_values("from"), left_on="entry_dd", right_on="from")
    T["gross"] = T.exit / T.entry - 1
    T["ret"] = T.gross - T.round_trip_pct_assumed / 100
    T["R"] = T.ret / T.risk
    return T.drop(columns=["from"])


if __name__ == "__main__":
    d = features(load())
    print("rows", len(d), "sig", int(d.sig.sum()))
    T = simulate(d, None)
    T = T[(T.entry_dd >= "1997-01-02")]
    T.to_parquet(OUT / "trades.parquet")
    print(len(T), T.market.value_counts().to_dict(), T.why.value_counts().to_dict())
    print(T.groupby("market")[["gross", "ret", "R", "bars"]].mean().round(4).to_string())
