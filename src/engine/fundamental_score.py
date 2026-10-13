"""재무·목표가 리비전 점수 — 순수 함수, I/O 0 (명세 `_workspace/design/2026-10-13_rs_fundamental_phase1.md` §B)."""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any, Iterable, Sequence

_QUARTER_LAG_DAYS = 45
_ANNUAL_LAG_DAYS = 90


def _month_end(stac_yymm: str) -> date:
    y, m = int(stac_yymm[:4]), int(stac_yymm[4:6])
    return date(y, m, calendar.monthrange(y, m)[1])


def available_from(stac_yymm: str, is_annual_or_q4: bool) -> date:
    """결산월 말일 + 45일(분기) / + 90일(4분기·연간) — 「그때 알 수 있던 값」 규칙."""
    lag = _ANNUAL_LAG_DAYS if is_annual_or_q4 else _QUARTER_LAG_DAYS
    return _month_end(stac_yymm) + timedelta(days=lag)


def known_as_of(rows: Sequence[dict], as_of: date) -> list:
    """`available_from <= as_of` 인 행만(입력 순서 유지). 플래그 없으면 12월 결산을 4분기로 본다."""
    out = []
    for r in rows:
        ym = r["stac_yymm"]
        flag = r.get("is_annual_or_q4")
        if flag is None:
            flag = ym[4:6] == "12"
        if available_from(ym, bool(flag)) <= as_of:
            out.append(r)
    return out


def quarterly_from_cumulative(rows: Iterable[dict]) -> dict[str, float | None]:
    """연초 누적 → 분기 단독값. 직전 분기 결측이면 None(추정 금지)."""
    cum: dict[str, float | None] = {r["stac_yymm"]: r.get("value") for r in rows}
    out: dict[str, float | None] = {}
    for ym, val in cum.items():
        if val is None:
            out[ym] = None
            continue
        y, m = int(ym[:4]), int(ym[4:6])
        if m == 3:
            out[ym] = val
        elif m in (6, 9, 12):
            prev = cum.get(f"{y:04d}{m - 3:02d}")
            out[ym] = None if prev is None else val - prev
        else:
            out[ym] = None
    return out


def turnaround_flags(q_now: float | None, q_yoy: float | None) -> dict:
    """흑자전환(yoy ≤ 0 ∧ now > 0) · YoY 증가율(yoy > 0 일 때만)."""
    if q_now is None or q_yoy is None:
        return {"turnaround": None, "yoy_growth": None}
    growth = (q_now / q_yoy - 1.0) if q_yoy > 0 else None
    return {"turnaround": bool(q_yoy <= 0 and q_now > 0), "yoy_growth": growth}


def _window_start(as_of: date, window_bd: int) -> date:
    """as_of 를 1일째로 세어 거꾸로 window_bd 번째 평일(공휴일 미고려)."""
    count = 0
    cur = as_of
    while True:
        if cur.weekday() < 5:
            count += 1
            if count >= window_bd:
                return cur
        cur -= timedelta(days=1)


def target_revision_breadth(
    opinions: Iterable[dict[str, Any]], as_of: date, window_bd: int = 60,
) -> float | None:
    """(상향 증권사 수 − 하향 증권사 수) ÷ 창 안 의견 낸 증권사 수. 의견 0건 = None."""
    start = _window_start(as_of, window_bd)
    by_broker: dict[str, list[tuple[date, float]]] = {}
    for o in opinions:
        goal = o.get("hts_goal_prc")
        d = o.get("bsop_date")
        if not goal or goal <= 0 or d is None or d < start or d > as_of:
            continue
        by_broker.setdefault(o["mbcr_name"], []).append((d, goal))
    if not by_broker:
        return None
    net = 0
    for rows in by_broker.values():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda x: x[0])
        prev, last = rows[-2][1], rows[-1][1]
        if last > prev:
            net += 1
        elif last < prev:
            net -= 1
    return net / len(by_broker)
