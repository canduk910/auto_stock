"""기술적 지표 계산 정본 — EMA · True Range · ATR (과제 B 1단계, cycle471 — 사용자 지시 2026-10-16 「과제B 착수하자」).

전에는 EMA·ATR 이 전략·모듈마다 따로 있었다. 이 파일이 계산식의 단일 정본이고, 각 자리는
**지금과 똑같은 값이 나오는 인자**로 이 함수를 부른다(행위 보존 — 골든 테스트가 옛 구현과
비트 단위로 같음을 확인한다). 시작 방식을 하나로 통일할지는 별도 결정이다(매매 행위 변경).

시작 방식(seed)
- ``"first"`` — 첫 값에서 시작해 모든 값을 갱신한다(``y = v·k + y·(1−k)``).
  쓰는 곳: donchian·VCP `_ema`, `etf_trend_core.ema`·`atr_wilder`.
- ``"sma"`` — 처음 `period` 개의 단순평균에서 시작한다. 갱신식은 원래 쓰던 모양 그대로 둔다
  (EMA ``y + α·(v−y)`` · Wilder ``(y·(n−1)+v)/n``) — 모양이 다르면 부동소수 끝자리가 달라진다.
  쓰는 곳: `llm_features.ema`·`atr_wilder`.

남겨 둔 것(이 파일을 쓰지 않는다)
- `kojiro_indicators.ema`·`atr` — pandas `ewm(adjust=False)` 파이프라인. 손절선 정의(Wilder ATR 20)라
  상호 재사용 금지 규약이 있고, pandas 내부 정규화 때문에 끝자리가 같다는 보장이 없다.
- `src/db/stock_master_daily.get_atr` — DB 계층의 단순평균 TR. 호출자 = VCP prepare 의 ATR 교차검증 하나(정리는 사용자 결정 대상).

표준 라이브러리만 쓴다 — `src.*` import 0, I/O·로깅·`await` 0.
"""
from __future__ import annotations

from typing import Literal, Sequence

Seed = Literal["first", "sma"]


# ── EMA ──────────────────────────────────────────────────────────────────────
def ema_last(values: Sequence[float], period: int, *, seed: Seed = "first") -> float | None:
    """오래된→최신 `values` 의 마지막 EMA 값.

    - ``seed="first"`` — 빈 입력은 ``None``. 길이가 `period` 보다 짧아도 계산한다.
    - ``seed="sma"`` — `period <= 0`·길이 < `period`·숫자 변환 실패는 ``None``.
    """
    if seed == "first":
        if not values:
            return None
        k = 2 / (period + 1)
        out = float(values[0])
        for v in values[1:]:
            out = v * k + out * (1 - k)
        return out
    if period is None or period <= 0:
        return None
    try:
        vals = [float(v) for v in values]
    except (TypeError, ValueError):
        return None
    if len(vals) < period:
        return None
    out = sum(vals[:period]) / period
    alpha = 2.0 / (period + 1)
    for v in vals[period:]:
        out = out + alpha * (v - out)
    return out


def ema_series(values: Sequence[float], span: int) -> list[float]:
    """오래된→최신 `values` 의 EMA 전 구간(첫 값 시작). 빈 입력 = 빈 목록."""
    a = 2.0 / (span + 1)
    out: list[float] = []
    for i, v in enumerate(values):
        out.append(float(v) if i == 0 else a * v + (1 - a) * out[-1])
    return out


# ── True Range ───────────────────────────────────────────────────────────────
def _tr(high, low, prev_close):
    """한 봉의 True Range — 세 항의 순서·연산이 옛 구현들과 같다(비트 동일)."""
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def true_ranges(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> list[float]:
    """오래된→최신 TR 목록. 첫 봉은 직전 종가가 없어 고가 − 저가."""
    out = []
    for i in range(len(highs)):
        if i == 0:
            out.append(highs[0] - lows[0])
        else:
            out.append(_tr(highs[i], lows[i], closes[i - 1]))
    return out


# ── ATR ──────────────────────────────────────────────────────────────────────
def atr_sma_latest_first(highs, lows, closes, period: int) -> float:
    """최신→오래된 순(idx 0 = 가장 최근 완성봉) 입력의 최근 `period` 개 TR **단순평균**.

    `closes[i+1]` 이 `i` 봉의 직전 종가다. 길이가 모자라면 0.0(옛 `StrategyBase._atr` 그대로).
    """
    if len(highs) <= period or len(lows) <= period or len(closes) <= period + 1:
        return 0.0
    trs = []
    for i in range(period):
        trs.append(_tr(highs[i], lows[i], closes[i + 1]))
    return sum(trs) / period


def wilder_series(tr: Sequence[float], period: int) -> list[float]:
    """TR 목록(오래된→최신)의 Wilder 평활 전 구간 — 첫 TR 에서 시작(``seed="first"``)."""
    a = 1.0 / period
    out: list[float] = []
    for i, v in enumerate(tr):
        out.append(float(v) if i == 0 else a * v + (1 - a) * out[-1])
    return out


def atr_wilder_last(highs, lows, closes, period: int = 14) -> float | None:
    """오래된→최신 입력의 Wilder ATR 마지막 값 — 처음 `period` 개 TR 단순평균에서 시작(``seed="sma"``).

    TR 은 두 번째 봉부터 센다(첫 봉은 직전 종가가 없다). 숫자 변환 실패·표본 부족은 ``None``.
    """
    try:
        h = [float(x) for x in highs]
        low = [float(x) for x in lows]
        c = [float(x) for x in closes]
    except (TypeError, ValueError):
        return None
    n = min(len(h), len(low), len(c))
    if n < period + 1:
        return None
    trs = []
    for i in range(1, n):
        trs.append(_tr(h[i], low[i], c[i - 1]))
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for t in trs[period:]:
        atr = (atr * (period - 1) + t) / period
    return atr
