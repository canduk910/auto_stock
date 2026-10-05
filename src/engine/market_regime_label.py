"""cycle410 — 6장세 라벨 leaf. **관찰 전용 — 매매 경로가 읽지 않는다.**

KODEX 200(``069500``) 일봉 종가로 장세를 {안정, 변동} × {상승, 횡보, 하락} 6칸에 매긴다.
정의 정본 = ``_workspace/domain_consult/2026-10-05_six_regime_strategy_map.md`` §1.1~§1.4
(사용자 결정 10-05 — 권고 D4 × V4).

- 방향 = SMA60(t) / SMA60(t−20) − 1. 횡보에서 > +3% 상승 · < −3% 하락. 상승은 +1% 밑에서,
  하락은 −1% 위에서 풀린다(풀리는 날 반대 문턱을 넘으면 곧장 반대편).
- 변동 = 20일 로그수익률 표본표준편차 × √252. > 20% 변동 · < 16% 안정 · 사이는 직전 유지.
- 상태는 첫 특징(80번째 종가)에서 (횡보, 안정)으로 시작해 이력을 처음부터 걸어 이어 간다
  — 그래서 이력 시작점이 다르면 첫 구간 라벨이 달라질 수 있다.
- D 일 라벨 = D-1 종가까지(``session_labels``). 그날 봉은 쓰지 않는다.

시장 유닛(``market_unit.py``)과 재료는 같지만 다른 장치다 — 이 라벨은 랏을 바꾸지 않는다.
I/O 없음 · 표준 라이브러리만.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

SOURCE_TICKER = "069500"          # KODEX 200
MA_WINDOW = 60
SLOPE_LOOKBACK = 20
VOL_WINDOW = 20
ANNUALIZATION = 252
WARMUP_CLOSES = MA_WINDOW + SLOPE_LOOKBACK      # 80 — 첫 특징이 나오는 종가 수

DIR_ENTER = 0.03
DIR_EXIT = 0.01
VOL_HIGH = 0.20
VOL_LOW = 0.16

DIRECTIONS = ("up", "flat", "down")
VOLATILITIES = ("stable", "volatile")
LABELS = tuple(f"{v}_{d}" for v in VOLATILITIES for d in DIRECTIONS)

_INITIAL_DIRECTION = "flat"
_INITIAL_VOLATILITY = "stable"


@dataclass(frozen=True)
class Point:
    """한 종가 시점까지 걸어 온 상태 — 다음 세션의 라벨이다."""

    label: str
    direction: str
    volatility: str
    slope_pct: float
    vol_pct: float


def step_direction(prev: str, slope: float) -> str:
    """방향 히스테리시스 한 걸음."""
    if prev == "up":
        if slope < DIR_EXIT:
            return "down" if slope < -DIR_ENTER else "flat"
        return "up"
    if prev == "down":
        if slope > -DIR_EXIT:
            return "up" if slope > DIR_ENTER else "flat"
        return "down"
    if slope > DIR_ENTER:
        return "up"
    if slope < -DIR_ENTER:
        return "down"
    return "flat"


def step_volatility(prev: str, vol: float) -> str:
    """변동 히스테리시스 한 걸음 — 문턱 사이는 직전 유지."""
    if prev == "stable" and vol > VOL_HIGH:
        return "volatile"
    if prev == "volatile" and vol < VOL_LOW:
        return "stable"
    return prev


def _clean(closes: Sequence[Any]) -> list[float]:
    out: list[float] = []
    for i, raw in enumerate(closes):
        if raw is None or isinstance(raw, bool):
            raise ValueError(f"종가 결측 index={i}")
        try:
            v = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"종가 비수치 index={i}") from None
        if not math.isfinite(v) or v <= 0:
            raise ValueError(f"종가 비정상 index={i} value={raw!r}")
        out.append(v)
    return out


def label_after_closes(closes: Sequence[Any]) -> "list[Point | None]":
    """오름차순 종가 → 각 종가 시점의 상태(앞 79개는 ``None``). 나쁜 종가 = ``ValueError``."""
    c = _clean(closes)
    n = len(c)
    out: "list[Point | None]" = [None] * n
    direction, volatility = _INITIAL_DIRECTION, _INITIAL_VOLATILITY
    for i in range(WARMUP_CLOSES - 1, n):
        sma = sum(c[i - MA_WINDOW + 1:i + 1]) / MA_WINDOW
        j = i - SLOPE_LOOKBACK
        sma_prev = sum(c[j - MA_WINDOW + 1:j + 1]) / MA_WINDOW
        slope = sma / sma_prev - 1
        rets = [math.log(c[k] / c[k - 1]) for k in range(i - VOL_WINDOW + 1, i + 1)]
        vol = statistics.stdev(rets) * math.sqrt(ANNUALIZATION)
        direction = step_direction(direction, slope)
        volatility = step_volatility(volatility, vol)
        out[i] = Point(
            label=f"{volatility}_{direction}", direction=direction, volatility=volatility,
            slope_pct=slope * 100, vol_pct=vol * 100,
        )
    return out


def session_labels(dates: Sequence[date], closes: Sequence[Any]) -> "list[tuple[date, Point]]":
    """봉 날짜별 세션 라벨 — ``dates[i]`` 의 라벨은 ``closes[i-1]`` 까지의 상태(D-1 기준)."""
    if len(dates) != len(closes):
        raise ValueError("dates/closes 길이 불일치")
    pts = label_after_closes(closes)
    return [(dates[i], pts[i - 1]) for i in range(1, len(dates)) if pts[i - 1] is not None]
