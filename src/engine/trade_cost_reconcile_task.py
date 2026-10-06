"""매일 자동 대사 훅 — KIS 정산값(`TTTC8715R`)을 직전 영업일분 하루 1회 가져온다 (트랙 C · cycle409).

cycle409 — 사용자 결정 10-04 Q1 「매일 자동으로 돌리자 — 시각은 첫날 실측 뒤 같이 정한다」.

- **실행 시각은 코드에 없다.** `system_config.trade_cost_reconcile_time` = `{"value":"HH:MM","days":N}`
  을 매 폴링마다 다시 읽는다(`PUT /api/costs/schedule` 한 번으로 재시작 없이 켜고 끈다).
  **키 없음·`value` null·형식 오류·조회 예외 = 실행 안 함** — 관측 기능이라 꺼짐이 기본이다.
- 대상 = 직전 영업일(`trading_calendar.previous_trading_day`)까지 `days` 달력일(기본 1 = 그날 하루).
  `reconcile` 은 같은 키를 덮어쓰므로 창이 겹쳐도 안전하다.
- 발화 = 오늘 아직 안 돌았고 `at ≤ now < at + 60분`. 그 창을 지나 기동하면 그날은 건너뛴다 —
  늦은 재기동이 장중에 메인 계좌 REST 를 몰래 쓰지 않게.
- 시각은 루프 수명 `[07:45, 21:30)` 안이어야 한다 — 이 task 는 `scheduler.start()` 가 띄우고
  21:30 정산 뒤 cancel 된다. 밖의 시각은 영영 발화하지 않으므로 꺼짐으로 읽는다(라우트도 422).
- 오늘이 휴장일(False)이면 돌지 않는다. 직전 영업일을 모르면(None) WARNING 1행 후 건너뛴다.
- 실패(KIS 거부·모의 환경·DB 예외·상한 `_RUN_TIMEOUT_SECS` 초과) = `[trade_cost_reconcile_failed]`
  WARNING 1행으로 흡수하고 같은 날 재시도하지 않는다. 매매 루프와는 별도 task 라 그 루프를 막지 않는다.
- 8영역·`scheduler.py` import 0(leaf 경계 — AST `test_cycle409_ast_reconcile_hook.py`).
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, time, timedelta

from src.db import system_config
from src.db._kst import KST
from src.engine import trade_cost, trading_calendar

logger = logging.getLogger(__name__)

LOOP_OPEN = time(7, 45)     # = scheduler.TIME_AUTO_START
LOOP_CLOSE = time(21, 30)   # = scheduler.TIME_SETTLEMENT (정산 뒤 이 task 는 cancel 된다)
MAX_DAYS = 31
_LATE_GRACE = timedelta(minutes=60)
_POLL_SECS = 60.0
_RUN_TIMEOUT_SECS = 600.0
_HHMM = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")

_MARKER_DONE = "[trade_cost_reconcile_done]"
_MARKER_FAILED = "[trade_cost_reconcile_failed]"


def _now_kst() -> datetime:
    return datetime.now(KST)


async def _sleep(secs: float) -> None:
    await asyncio.sleep(secs)


def parse_hhmm(value) -> time | None:
    """`HH:MM`(두 자리) 이고 루프 수명 `[07:45, 21:30)` 안이면 `time`, 아니면 None."""
    if not isinstance(value, str) or not _HHMM.fullmatch(value):
        return None
    at = time(int(value[:2]), int(value[3:]))
    return at if LOOP_OPEN <= at < LOOP_CLOSE else None


def parse_days(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= MAX_DAYS else None


def parse_schedule(raw) -> tuple[time, int] | None:
    """저장값 → `(시각, days)`. 꺼짐·형식 오류는 None."""
    if isinstance(raw, str):
        raw = {"value": raw}
    if not isinstance(raw, dict):
        return None
    at = parse_hhmm(raw.get("value"))
    days = parse_days(raw.get("days", 1))
    if at is None or days is None:
        return None
    return at, days


def is_due(now: datetime, at: time, done_day: date | None) -> bool:
    if done_day == now.date():
        return False
    start = datetime.combine(now.date(), at, tzinfo=now.tzinfo)
    return start <= now < start + _LATE_GRACE


async def _read_schedule() -> tuple[time, int] | None:
    try:
        raw = await system_config.get_trade_cost_reconcile_schedule_raw()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("[trade_cost_reconcile] 시각 키 조회 실패 — 꺼짐으로 읽는다", exc_info=True)
        return None
    return parse_schedule(raw)


async def run_once(today: date, days: int) -> dict | None:
    """직전 영업일까지 `days` 달력일을 대사한다. 어떤 실패도 밖으로 내지 않는다."""
    try:
        if await trading_calendar.is_open_day(today) is False:
            logger.info("[trade_cost_reconcile] 휴장일 — 건너뜀 today=%s", today.isoformat())
            return None
        end = await trading_calendar.previous_trading_day(today)
        if end is None:
            logger.warning("%s reason=calendar_unknown today=%s — 직전 영업일을 모른다",
                           _MARKER_FAILED, today.isoformat())
            return None
        start = end - timedelta(days=days - 1)
        out = await asyncio.wait_for(trade_cost.reconcile(start, end), timeout=_RUN_TIMEOUT_SECS)
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        logger.warning("%s reason=timeout limit_s=%g today=%s", _MARKER_FAILED,
                       _RUN_TIMEOUT_SECS, today.isoformat())
        return None
    except Exception as exc:
        logger.warning("%s reason=error today=%s err=%r", _MARKER_FAILED, today.isoformat(), exc)
        return None
    logger.info("%s from=%s to=%s kis_rows=%s saved_rows=%s totals_match=%s", _MARKER_DONE,
                start.isoformat(), end.isoformat(), out.get("kis_rows"), out.get("saved_rows"),
                out.get("totals_match"))
    return out


async def task_loop(sched) -> None:
    """`sched._running` 동안 `_POLL_SECS` 마다 시각 키를 읽고, 때가 되면 하루 1회 대사한다."""
    done_day: date | None = None
    while getattr(sched, "_running", False):
        now = _now_kst()
        schedule = await _read_schedule()
        if schedule is not None and is_due(now, schedule[0], done_day):
            done_day = now.date()
            await run_once(now.date(), schedule[1])
        await _sleep(_POLL_SECS)
