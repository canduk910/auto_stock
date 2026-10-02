"""ETF 추세 전략(etf_trend) 순수 leaf — 지표/신호/청산선/상관 판정 함수.

재현 정본(`_workspace/domain_consult/cycle391_etf_s0_remeasure.py`)과 같은 식으로
지표·진입 판정·청산 시뮬레이션·묶음 상관을 계산한다(cycle403 §3). 표준 라이브러리
(`math`·`typing`)만 import 한다 — `src.*` import 0 · I/O 0 · `await` 0 · 로깅 0.
"""
from __future__ import annotations

import math
from typing import NamedTuple


def ema(values, span):
    a = 2.0 / (span + 1)
    out = []
    for i, v in enumerate(values):
        out.append(float(v) if i == 0 else a * v + (1 - a) * out[-1])
    return out


def true_ranges(highs, lows, closes):
    out = []
    for i in range(len(highs)):
        if i == 0:
            out.append(highs[0] - lows[0])
        else:
            pc = closes[i - 1]
            out.append(max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc)))
    return out


def atr_wilder(tr, period=20):
    a = 1.0 / period
    out = []
    for i, v in enumerate(tr):
        out.append(float(v) if i == 0 else a * v + (1 - a) * out[-1])
    return out


def n14(tr, i, period=14):  # 14 = 재현 측정값(묶음 B 사이징 ATR) — 바꾸면 측정 밖
    if i < period:
        return None
    w = tr[i - period + 1:i + 1]
    return sum(w) / period


def breakout_line(highs, j, period=20):  # 20 = 재현 측정값(20일 신고가 돌파) — 바꾸면 측정 밖
    if j < period:
        return None
    return max(highs[j - period:j])


def tv20(tv, j, period=20):  # 20 = 재현 측정값(거래대금 20일 평균) — 바꾸면 측정 밖
    if j < period - 1:
        return None
    return sum(tv[j - period + 1:j + 1]) / period


def tv_prev20(tv, j, period=20):  # 20 = 재현 측정값 — 바꾸면 측정 밖
    if j < period:
        return None
    return sum(tv[j - period:j]) / period


class EntrySignal(NamedTuple):
    ok: bool
    stage: str | None
    line: float | None = None
    n: float | None = None
    atr20: float | None = None
    tv20: float | None = None
    close: float | None = None
    ema60: float | None = None


def entry_signal(highs, lows, closes, trade_values, j, *, min_trade_amount_20d=2_000_000_000,
                 min_price=1_000, max_price=500_000, atr_ratio_min=0.01, atr_ratio_max=0.06,
                 min_bars=100, volume_multiplier=1.5):
    if j + 1 < min_bars:
        return EntrySignal(False, "min_bars")
    c = closes[j]
    tr = true_ranges(highs[:j + 1], lows[:j + 1], closes[:j + 1])
    a20 = atr_wilder(tr, 20)[j]  # 20 = 재현 측정값(변동성 밴드 ATR20) — 바꾸면 측정 밖
    t20 = tv20(trade_values, j)
    if not (t20 is not None and t20 >= min_trade_amount_20d and c >= min_price and a20 / c >= atr_ratio_min):
        return EntrySignal(False, "liquidity")
    if not (c <= max_price and a20 / c <= atr_ratio_max):
        return EntrySignal(False, "band")
    line = breakout_line(highs, j)
    if not (line is not None and line > 0 and c > line):
        return EntrySignal(False, "breakout")
    e = ema(closes[:j + 1], 60)  # 60 = 재현 측정값(장기 추세 EMA) — 바꾸면 측정 밖
    if not (e[j] > e[j - 1] and c > e[j]):
        return EntrySignal(False, "ema")
    tp = tv_prev20(trade_values, j)
    if not (tp is not None and tp > 0 and trade_values[j] >= volume_multiplier * tp):
        return EntrySignal(False, "volume")
    n = n14(tr, j)
    if not (n is not None and n > 0):
        return EntrySignal(False, "n")
    return EntrySignal(True, None, line, n, a20, t20, c, e[j])


def gap_skip_reason(open_price, close_t, line, gap_pct=3.0, over_line_pct=4.0):
    if open_price >= close_t * (1 + gap_pct / 100):
        return "gap_up"
    if open_price > line * (1 + over_line_pct / 100):
        return "gap_over_line"
    return None


def hard_stop(E, N, backstop_pct=-9.0, stop_atr=2.0):
    back = E * (1 + backstop_pct / 100)
    if not N:
        return back
    return max(E - stop_atr * N, back)


def stop_line(E, N, hsb_closed, *, backstop_pct=-9.0, stop_atr=2.0, breakeven_atr=1.5, trail_atr=1.8):
    hard = hard_stop(E, N, backstop_pct, stop_atr)
    if hsb_closed is None or not N:
        return hard
    be = E if hsb_closed >= E + breakeven_atr * N else -math.inf
    return max(hard, be, hsb_closed - trail_atr * N)


def channel_low(lows_prev, period=10):  # 10 = 재현 측정값(10일 저가 채널) — 바꾸면 측정 밖
    w = list(lows_prev)[-period:]
    return min(w) if w else None


def breakout_failed(price, line, bars_since_buy, min_bars=2):
    return bars_since_buy >= min_bars and price < line


def simulate_exit(opens, highs, lows, closes, j):
    tr = true_ranges(highs, lows, closes)
    E = opens[j + 1]
    N = n14(tr, j)
    line = breakout_line(highs, j)
    hard = max(E - 2.0 * N, E * 0.91)
    stop, hsb = hard, -math.inf
    n = len(closes)
    D = j + 1
    for k in range(D, n):
        ch = min(lows[max(0, k - 10):k]) if k >= D + 1 else -math.inf
        if opens[k] <= stop or opens[k] < ch:
            return k, opens[k], ("stop_gap" if opens[k] <= stop else "chan10_gap")
        trig = []
        if lows[k] <= stop:
            trig.append((stop, "stop"))
        if lows[k] < ch:
            trig.append((ch, "chan10"))
        if trig:
            px, why = max(trig)
            return k, px, why
        if k >= D + 2 and closes[k] < line:
            return k, closes[k], "below_line"
        hsb = max(hsb, highs[k])
        be = E if hsb >= E + 1.5 * N else -math.inf
        stop = max(hard, be, hsb - 1.8 * N)
    return n - 1, closes[n - 1], "end"


def return_correlation(closes_a, closes_b, *, calendar, window=120, min_obs=60):
    cal = list(calendar)
    ci = len(cal) - 1
    lo = max(1, ci - window + 1)
    xs, ys = [], []
    for i in range(lo, ci + 1):
        d0, d1 = cal[i - 1], cal[i]
        if d0 in closes_a and d1 in closes_a and d0 in closes_b and d1 in closes_b:
            xs.append(closes_a[d1] / closes_a[d0] - 1)
            ys.append(closes_b[d1] / closes_b[d0] - 1)
    if len(xs) < min_obs:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sx * sy)
