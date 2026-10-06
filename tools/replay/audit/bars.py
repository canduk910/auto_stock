"""집행 층 — 동결본 §1.4 같은 봉 체결 규칙 · §1.3 P5 봉 안 경로.

한 봉을 걷는 순수 함수 하나(``walk_bar``)와 진입·잠김 판정 헬퍼만 둔다. 어떤 청산선을 쓰는지
(손절·본전·트레일링·채널·돌파 실패)는 전략 층이 ``lines_fn`` 으로 넘긴다.

봉 안 경로(P5):
- ``mode="color"``  = 판정판 가정 — 양봉(종가 ≥ 시가) 시→저→고→종 · 음봉 시→고→저→종
- ``mode="adverse"`` = 불리판 — 언제나 시→저→고→종(같은 봉에 손절선과 이익선이 다 있으면 손절 먼저)

선 갱신 시점:
- ``ratchet="intrabar"`` — 봉 안에서 새 고가가 나오면 그 즉시 ``on_up`` 을 불러 선을 올린다(cycle405)
- ``ratchet="next_bar"`` — 봉 안에서는 선을 올리지 않는다. 전략이 봉을 다 본 뒤 고가로 올린다(cycle391)

체결가:
- 시가가 이미 선 아래(갭) → 시가
- 장중에 선을 깨면 → min(직전 경로 가격, 선) — 직전 경로 가격이 선 위였으면 선 가격
- 하한가 잠김(시가 ≤ 전일 종가 × 0.71 ∧ 고가 = 저가)이면 그날은 못 판다 → ``kind="locked"``
  (전략이 다음 잠기지 않은 날 시가로 미룬다 — 평균회귀 2차 M7)
"""
from __future__ import annotations

import math
from typing import Callable, NamedTuple, Optional, Sequence

LIMIT_UP = 1.29
LIMIT_DOWN = 0.71


class Line(NamedTuple):
    """청산선 하나. ``strict=True`` 면 가격이 선 **아래**(<)일 때만, 아니면 선 이하(≤)에서 깨진다."""

    price: float
    reason: str
    strict: bool = False


class BarExit(NamedTuple):
    px: float
    reason: str
    kind: str          # "gap" | "intra" | "locked"


def hits(px: float, ln: Line) -> bool:
    return (px < ln.price) if ln.strict else (px <= ln.price)


def _pick_default(trig: "Sequence[Line]") -> Line:
    """가장 높은 선. 같은 가격이면 목록 앞쪽(전략이 넘긴 순서) — cycle405 ``max(..., key=price)`` 와 같다."""
    best = trig[0]
    for ln in trig[1:]:
        if ln.price > best.price:
            best = ln
    return best


def path_order(o: float, h: float, l: float, c: float, mode: str) -> "tuple[float, float, float]":
    if mode == "adverse":
        return (l, h, c)
    if mode == "color":
        return (l, h, c) if c >= o else (h, l, c)
    raise ValueError(mode)


def locked_limit_down(o: float, h: float, l: float, prev_c: float) -> bool:
    return (math.isfinite(o) and math.isfinite(prev_c) and prev_c > 0
            and o <= prev_c * LIMIT_DOWN and h == l)


def limit_up_open(o: float, prev_c: float) -> bool:
    """시가가 전일 종가 대비 +29% 이상 — 매수 불가로 본다."""
    return math.isfinite(o) and math.isfinite(prev_c) and prev_c > 0 and o >= prev_c * LIMIT_UP


def walk_bar(o: float, h: float, l: float, c: float, *,
             lines_fn: Callable[[], "Sequence[Line]"],
             on_up: Optional[Callable[[float], None]] = None,
             mode: str = "color", ratchet: str = "intrabar", gap_check: bool = True,
             locked: bool = False,
             pick: Callable[["Sequence[Line]"], Line] = _pick_default) -> "BarExit | None":
    """한 봉. 청산이면 ``BarExit``, 아니면 ``None``.

    ``gap_check=False`` 는 진입 봉(시가에 샀다 — 시가 갭 판정 없음, 시가로 선을 올리지 않음)이다.
    ``locked=True`` 면 어떤 선이 깨져도 그날 체결하지 않고 ``kind="locked"`` 를 돌려준다.
    """
    if gap_check:
        trig = [ln for ln in lines_fn() if hits(o, ln)]
        if trig:
            b = pick(trig)
            return BarExit(float("nan"), b.reason, "locked") if locked else BarExit(o, b.reason, "gap")
        if ratchet == "intrabar" and on_up is not None:
            on_up(o)
    prev = o
    for px in path_order(o, h, l, c, mode):
        if px > prev:
            if ratchet == "intrabar" and on_up is not None:
                on_up(px)
        elif px < prev:
            trig = [ln for ln in lines_fn() if hits(px, ln)]
            if trig:
                b = pick(trig)
                if locked:
                    return BarExit(float("nan"), b.reason, "locked")
                return BarExit(min(prev, b.price), b.reason, "intra")
        prev = px
    return None


def breakout_fill(o: float, h: float, line: float, chase_pct: float) -> "float | None":
    """장중 돌파 진입(§1.4) — 체결가 = max(시가, 돌파선). 시가가 이미 추격 상한(돌파선 × (1+chase%)) 위거나
    고가가 돌파선에 못 닿으면 진입 없음(``None``)."""
    if not (math.isfinite(o) and math.isfinite(h) and math.isfinite(line)) or line <= 0:
        return None
    if o > line * (1.0 + chase_pct / 100.0):
        return None
    if h < line:
        return None
    return max(o, line)
