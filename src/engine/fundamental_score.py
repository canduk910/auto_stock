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


def _is_fiscal_end(stac_yymm: str, fiscal_end_month: int) -> bool:
    return int(stac_yymm[4:6]) == fiscal_end_month


def available_from(
    stac_yymm: str, is_annual_or_q4: bool | None = None, *, fiscal_end_month: int = 12,
) -> date:
    """결산월 말일 + 45일(분기) / + 90일(4분기·연간) — 「그때 알 수 있던 값」 규칙.

    `is_annual_or_q4` 가 None 이면 결산월이 회계연도 마지막 달(`fiscal_end_month`)인지로 판정한다.
    """
    if is_annual_or_q4 is None:
        is_annual_or_q4 = _is_fiscal_end(stac_yymm, fiscal_end_month)
    lag = _ANNUAL_LAG_DAYS if is_annual_or_q4 else _QUARTER_LAG_DAYS
    return _month_end(stac_yymm) + timedelta(days=lag)


def known_as_of(rows: Sequence[dict], as_of: date, *, fiscal_end_month: int = 12) -> list:
    """`available_from <= as_of` 인 행만(입력 순서 유지).

    행에 `is_annual_or_q4` 가 있으면 그것을 우선하고, 없으면 회계연도 마지막 달(기본 12월)을 4분기로 본다.
    """
    out = []
    for r in rows:
        flag = r.get("is_annual_or_q4")
        if available_from(r["stac_yymm"], flag, fiscal_end_month=fiscal_end_month) <= as_of:
            out.append(r)
    return out


def _shift_months(stac_yymm: str, delta: int) -> str:
    idx = int(stac_yymm[:4]) * 12 + (int(stac_yymm[4:6]) - 1) + delta
    return f"{idx // 12:04d}{idx % 12 + 1:02d}"


def quarterly_from_cumulative(
    rows: Iterable[dict], *, fiscal_end_month: int = 12,
) -> dict[str, float | None]:
    """회계연도 누적 → 분기 단독값. 직전 분기(같은 회계연도 3개월 전) 결측이면 None(추정 금지).

    회계연도 시작월 = `fiscal_end_month` 다음 달. 시작 후 3번째 달 = 1분기(그대로), 6·9·12번째 달 = 누적 − 직전 분기 누적.
    """
    cum: dict[str, float | None] = {r["stac_yymm"]: r.get("value") for r in rows}
    start_month = fiscal_end_month % 12 + 1
    out: dict[str, float | None] = {}
    for ym, val in cum.items():
        if val is None:
            out[ym] = None
            continue
        pos = (int(ym[4:6]) - start_month) % 12 + 1  # 회계연도 안 몇 번째 달
        if pos == 3:
            out[ym] = val
        elif pos in (6, 9, 12):
            prev = cum.get(_shift_months(ym, -3))
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


def _latest_prev_by_broker(
    opinions: Iterable[dict[str, Any]], as_of: date, window_bd: int, lookback_bd: int,
) -> dict[str, tuple[float, float | None]]:
    """증권사별 (창 안 가장 최근 목표가, 그 직전 목표가|None). 창 안 의견 없는 증권사는 빠진다.

    같은 증권사·같은 날 중복은 입력에서 마지막 행이 이긴다. 직전은 창 밖도 허용(as_of 기준 lookback_bd 평일 이내).
    """
    win_start = _window_start(as_of, window_bd)
    look_start = _window_start(as_of, lookback_bd)
    per_day: dict[str, dict[date, float]] = {}
    for o in opinions:
        goal = o.get("hts_goal_prc")
        d = o.get("bsop_date")
        if not goal or goal <= 0 or d is None or d < look_start or d > as_of:
            continue
        per_day.setdefault(o["mbcr_name"], {})[d] = goal  # 같은 날 = 마지막 입력
    out: dict[str, tuple[float, float | None]] = {}
    for broker, days in per_day.items():
        ordered = sorted(days)
        if ordered[-1] < win_start:
            continue
        last = days[ordered[-1]]
        prev = days[ordered[-2]] if len(ordered) >= 2 else None
        out[broker] = (last, prev)
    return out


def target_revision_breadth(
    opinions: Iterable[dict[str, Any]], as_of: date, window_bd: int = 60, lookback_bd: int = 250,
) -> float | None:
    """(상향 증권사 수 − 하향 증권사 수) ÷ 창 안 의견 낸 증권사 수. 의견 0건 = None.

    증권사별 「창 안 가장 최근 목표가」 vs 「그 증권사의 바로 직전 목표가」(창 밖 허용, lookback_bd 이내).
    직전이 없으면 분모에만 포함(변화 0).
    """
    pairs = _latest_prev_by_broker(opinions, as_of, window_bd, lookback_bd)
    if not pairs:
        return None
    net = 0
    for last, prev in pairs.values():
        if prev is None:
            continue
        if last > prev:
            net += 1
        elif last < prev:
            net -= 1
    return net / len(pairs)


def target_median_change(
    opinions: Iterable[dict[str, Any]], as_of: date, window_bd: int = 60, lookback_bd: int = 250,
) -> float | None:
    """직전 목표가가 있는 증권사의 (최근/직전 − 1) 중앙값. 쌍 0 = None."""
    changes = sorted(
        last / prev - 1.0
        for last, prev in _latest_prev_by_broker(opinions, as_of, window_bd, lookback_bd).values()
        if prev is not None
    )
    if not changes:
        return None
    n = len(changes)
    mid = n // 2
    return changes[mid] if n % 2 else (changes[mid - 1] + changes[mid]) / 2.0
