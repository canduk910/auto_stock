"""etf_trend 묶음 B(cycle391b 판정판) — 신호·청산·묶음 캡 (공용 층 위에 얹은 전략 층).

재현 원본 = ``_workspace/domain_consult/cycle391_etf_s0_remeasure.py``(``gen_trades("donchian")``·``sim_donchian``·
``dedup``·``Corr``) + ``cycle391b_etf_exit_sizing_bundle.py``(``gen_trades_bundle("B","B")``). 유니버스 분류
(국내주식형 1배 — DB 필드 + 상장폐지분 규칙)만 원본 모듈 함수를 그대로 부르고, 나머지(데이터 배열 · 지표 ·
시장 유닛 · 봉 걷기 · 부트스트랩 · 슬리브)는 공용 층으로 다시 짰다. 관문 = cycle391b B 판정판 수치 재현.

청산(B, 판정판 = 돌파선 아래 「그날 종가」):
  hard = max(E − 2N, 0.91E) · 시가가 손절선 이하 또는 직전 10봉 저가 아래 → 시가 ·
  장중 저가 ≤ 손절선 → 손절선 · 저가 < 채널 → 채널(둘 다면 높은 쪽) ·
  D+2 부터 종가 < 돌파선 → 그날 종가 · 봉을 다 본 뒤 고가로 본전(1.5N)·트레일링(고가 − 1.8N) 갱신(다음 봉부터)
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from replay.audit import bars as BR
from replay.audit import indicators as IND

TV20_MIN = 2_000_000_000
MCAP_MIN = 50_000_000_000
PX_MIN, PX_MAX = 1_000, 500_000
ATR_LO, ATR_HI = 0.01, 0.06
MIN_BARS = 100
QUAL_WIN = 60
CORR_WIN, CORR_MIN_OBS, CORR_TH = 120, 60, 0.9
RISK_PCT, POS_RATIO, SLOTS = 0.01, 0.25, 4
REP_BUDGET = 750_000
COST_LIQ, COST_ILLIQ = 0.0006, 0.0011
COST_LIQ_TV = 10_000_000_000


def ticker_arrays(b: dict) -> dict:
    """공용 층 종목 배열 → 이 전략의 지표 배열(인과적)."""
    d = {"ci": b["di"].astype(np.int64), "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
         "craw": b["c_raw"], "tv": b["tv"], "mc": b["mktcap"]}
    d["e60"] = IND.ema_ewm(b["c"], 60)
    d["atr20"] = IND.atr_wilder(b["h"], b["l"], b["c"], 20)
    d["n14"] = IND.atr_sma(b["h"], b["l"], b["c"], 14)
    d["tv20"] = __import__("pandas").Series(b["tv"]).rolling(20, min_periods=20).mean().to_numpy()
    d["tvprev20"] = IND.prior_mean(b["tv"], 20)
    d["hi_prev20"] = IND.prior_max(b["h"], 20)
    ci = d["ci"]
    start = np.searchsorted(ci, ci - (QUAL_WIN - 1), side="left")
    d["qual60"] = (np.arange(len(ci)) - start + 1) == QUAL_WIN
    return d


def _pick(trig):
    return max(trig, key=lambda ln: (ln.price, ln.reason))


def sim_b(d: dict, j: int, mode: str = "color", line_exec: str = "close") -> "tuple[int, float, str]":
    """신호봉 j · 진입봉 j+1(시가). 반환 = (청산 봉, 청산가, 사유). ``line_exec="next_open"`` = 감사 M1(a)."""
    E = d["o"][j + 1]
    N = d["n14"][j]
    line = d["hi_prev20"][j]
    hard = max(E - 2.0 * N, E * 0.91)
    st = {"stop": hard, "hsb": -np.inf}
    n = len(d["c"])
    D = j + 1
    pending = False
    for k in range(D, n):
        if pending:
            return k, d["o"][k], "below_line_next_open"
        ch = np.min(d["l"][max(0, k - 10):k]) if k >= D + 1 else -np.inf

        def lines():
            ls = [BR.Line(st["stop"], "stop")]
            if np.isfinite(ch):
                ls.append(BR.Line(ch, "chan10", strict=True))
            return ls

        o = d["o"][k]
        if o <= st["stop"] or o < ch:          # 시가 갭 — 원본 우선순위(손절선 먼저)
            return k, o, ("stop_gap" if o <= st["stop"] else "chan10_gap")
        ex = BR.walk_bar(o, d["h"][k], d["l"][k], d["c"][k], lines_fn=lines, mode=mode, ratchet="next_bar",
                         gap_check=False, pick=_pick)
        if ex is not None:
            return k, ex.px, ex.reason
        if k >= D + 2 and d["c"][k] < line:
            if line_exec == "close":
                return k, d["c"][k], "below_line"
            pending = True
            continue
        st["hsb"] = max(st["hsb"], d["h"][k])
        be = E if st["hsb"] >= E + 1.5 * N else -np.inf
        st["stop"] = max(hard, be, st["hsb"] - 1.8 * N)
    return n - 1, d["c"][n - 1], "end"


def gen_trades(data: dict, cls: dict, mu: np.ndarray, cal, listed_at_end: dict, last_ci: int,
               mode: str = "color", line_exec: str = "close") -> list:
    """``mu[ci]`` = 신호봉 ci 종가까지로 판정한 m(= 진입일 m). cycle391b ``gen_trades_bundle("B","B")`` 와 같은 열."""
    trades = []
    for t, d in data.items():
        if not cls.get(t):
            continue
        n = len(d["c"])
        e60 = d["e60"]
        for j in range(MIN_BARS - 1, n - 1):
            ci = d["ci"][j]
            if d["ci"][j + 1] != ci + 1:
                continue
            c = d["c"][j]
            craw = d["craw"][j]
            a20 = d["atr20"][j]
            atr_pct = a20 / c
            if not (d["tv20"][j] >= TV20_MIN and craw >= PX_MIN and atr_pct >= ATR_LO):
                continue
            hp = d["hi_prev20"][j]
            if not (hp > 0 and c > hp):
                continue
            if not (e60[j] > e60[j - 1] and c > e60[j]):
                continue
            tvp = d["tvprev20"][j]
            if not (tvp > 0 and d["tv"][j] >= 1.5 * tvp):
                continue
            N = d["n14"][j]
            if not (N > 0):
                continue
            o1 = d["o"][j + 1]
            if o1 >= c * 1.03 or o1 > hp * 1.04:
                continue
            k, px, why = sim_b(d, j, mode=mode, line_exec=line_exec)
            m = mu[ci]
            E = d["o"][j + 1]
            rw = 2.0 * N
            cost = COST_LIQ if d["tv20"][j] >= COST_LIQ_TV else COST_ILLIQ
            if why == "end":
                why = "open_end" if d["ci"][k] == last_ci else "delist"
            f = min(1.0, POS_RATIO * (N / c) / RISK_PCT)
            scale = craw / c
            lot = 0
            if m == m and m > 0:
                bgt = REP_BUDGET * m
                lot = int(math.floor(min(bgt * RISK_PCT / (N * scale), POS_RATIO * bgt / craw)))
            trades.append({
                "ticker": t, "sig_ci": int(ci), "entry_ci": int(ci + 1), "exit_ci": int(d["ci"][k]),
                "entry_date": str(cal[ci + 1].date()), "exit_date": str(cal[d["ci"][k]].date()),
                "E": float(E), "exit_px": float(px), "reason": why, "R": float((px - E) / rw),
                "Rnet": float((px - E - cost * E) / rw), "m": float(m) if m == m else None, "f": float(f),
                "tv20": float(d["tv20"][j]), "atr_pct": float(atr_pct), "size_atr_pct": float(N / c),
                "hold": int(k - j - 1), "lot75": lot, "listed_at_end": bool(listed_at_end[t]),
                "f_mcap": bool(d["mc"][j] >= MCAP_MIN), "f_pxhi": bool(craw <= PX_MAX),
                "f_atrhi": bool(atr_pct <= ATR_HI), "f_qual": bool(d["qual60"][j]),
                "j": int(j), "k": int(k), "rw": float(rw), "cost": float(cost),
            })
    return trades


def full_u(t) -> bool:
    return t["f_mcap"] and t["f_pxhi"] and t["f_atrhi"] and t["f_qual"]


class Corr:
    """120봉 일간수익률 상관(관측 ≥ 60). 운영 묶음 캡(120일 상관 > 0.9)의 재현."""

    def __init__(self, ret, col):
        self.ret, self.col, self.cache = ret, col, {}

    def __call__(self, a, b, ci):
        if a == b:
            return 1.0
        key = (min(a, b), max(a, b), ci)
        if key in self.cache:
            return self.cache[key]
        lo = max(0, ci - CORR_WIN + 1)
        x = self.ret[lo:ci + 1, self.col[a]]
        y = self.ret[lo:ci + 1, self.col[b]]
        mk = np.isfinite(x) & np.isfinite(y)
        v = None
        if mk.sum() >= CORR_MIN_OBS:
            xx, yy = x[mk], y[mk]
            if xx.std() != 0 and yy.std() != 0:
                v = float(np.corrcoef(xx, yy)[0, 1])
        self.cache[key] = v
        return v


def same_cluster(corr, a, b, ci) -> bool:
    v = corr(a, b, ci)
    return v is not None and v > CORR_TH


def dedup(trades: list, corr) -> list:
    """같은 날 20일 거래대금 내림차순 · 보유 중(청산일 포함)이거나 그날 이미 고른 종목과 상관 > 0.9 면 뺀다."""
    by_day = defaultdict(list)
    for tr in trades:
        by_day[tr["entry_ci"]].append(tr)
    held, out = [], []
    for day in sorted(by_day):
        held = [h for h in held if h["exit_ci"] >= day]
        cands = sorted(by_day[day], key=lambda x: -x["tv20"])
        taken = []
        for c in cands:
            pool = held + taken
            if any(same_cluster(corr, c["ticker"], h["ticker"], c["sig_ci"]) for h in pool):
                continue
            taken.append(c)
            out.append(c)
        held.extend(taken)
    return out
