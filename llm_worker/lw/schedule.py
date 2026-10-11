"""cycle446 — 08:15/08:35/08:55 KST 루프(설계 §3.2). `src` 0, EC2 cron 0(컨테이너 재시작에
일정이 묶이지 않는다). 컨테이너가 08:15 이후에 기동하면 그날 08:55 전이면 **그 슬롯까지**
즉시 1회, 08:55 를 넘겼으면 그날은 건너뛰고 다음 날 08:15 까지 기다린다."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone

from lw.config import RUN_TIMES_KST

KST = timezone(timedelta(hours=9))
log = logging.getLogger(__name__)


def _parse_times():
    out = []
    for s in RUN_TIMES_KST:
        h, m, sec = (int(x) for x in s.split(":"))
        out.append(time(h, m, sec))
    return out


_RUN_TIMES = _parse_times()


def next_run_at(now: datetime) -> datetime:
    """`now` 이후(포함) 첫 예정 시각. 오늘 슬롯이 전부 지났으면 내일 첫 슬롯."""
    today = now.date()
    for t in _RUN_TIMES:
        candidate = datetime.combine(today, t, tzinfo=now.tzinfo)
        if candidate >= now:
            return candidate
    return datetime.combine(today + timedelta(days=1), _RUN_TIMES[0], tzinfo=now.tzinfo)


def due_today_up_to(now: datetime) -> bool:
    """지금이 오늘의 실행 구간(첫 슬롯~마지막 슬롯) 안인가."""
    today = now.date()
    first = datetime.combine(today, _RUN_TIMES[0], tzinfo=now.tzinfo)
    last = datetime.combine(today, _RUN_TIMES[-1], tzinfo=now.tzinfo)
    return first <= now <= last


def _next_pending_slot(n: datetime, fired: set) -> datetime:
    """`n` 뒤(초과, `>`)의 가장 가까운 **아직 안 쏜** 슬롯. 오늘 안에 없으면 내일 첫 슬롯.

    `next_run_at` 과 달리 `>` 를 쓴다 — `n` 이 방금 쏜 슬롯과 정확히 같은 시각이면
    `next_run_at(n)`(`>=`)이 같은 슬롯을 다시 돌려줘 대기 0초 무한 루프가 된다.
    """
    today = n.date()
    candidates = [
        datetime.combine(today, t, tzinfo=n.tzinfo) for t in _RUN_TIMES
    ]
    pending = [s for s in candidates if s not in fired and s > n]
    if pending:
        return min(pending)
    return datetime.combine(today + timedelta(days=1), _RUN_TIMES[0], tzinfo=n.tzinfo)


async def run_forever(run_once, *, now=lambda: datetime.now(KST), sleep=asyncio.sleep,
                      stop=lambda: False) -> None:
    """`run_once()` 를 슬롯마다 1회 부른다. 대상 선정·재시도(이미 `ok` 인 행 skip)는
    `run_once` 자체가 한다 — 이 루프는 "언제 부를까" 만 안다."""
    fired: set = set()
    while not stop():
        n = now()
        fired = {s for s in fired if s.date() == n.date()}  # 전날 슬롯 흔적 정리

        due = []
        if due_today_up_to(n):
            for t in _RUN_TIMES:
                slot = datetime.combine(n.date(), t, tzinfo=n.tzinfo)
                if slot <= n and slot not in fired:
                    due.append(slot)

        if due:
            try:
                await run_once()
            except Exception as exc:  # pragma: no cover — never-raise
                log.warning("[exit_ai_run_error] %s", exc)
            fired.update(due)
            continue

        target = _next_pending_slot(n, fired)
        delay = max(0.001, (target - n).total_seconds())
        await sleep(min(delay, 60.0))
