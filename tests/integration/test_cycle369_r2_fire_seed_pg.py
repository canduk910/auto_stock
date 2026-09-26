"""cycle369 round 2 Red — Q4. 오늘 발사 횟수를 **실 Postgres** `system_logs` 에서 되살린다.

단위 쌍 = `tests/unit/engine/test_cycle369_r2_sell_safety.py::test_q4_*`(task_loop 가 이 seam 을
시작 때 1회 부르고 메모리 카운터와 max 로 합친다).

## seam 계약

``status_exit_watch._load_fire_counts(day: date) -> dict[str, int]`` — 코루틴. 그날(**KST**)
`[status_exit_fire]` 발사마다 1로 센 **종목별 횟수**. 읽기 전용.

## 함정 — 행 모양 (🔁 cycle369 R3 F3)

발사 기록의 영속은 `src/main.py::_DbLogHandler` 가 logger WARNING 을 옮겨 적는 **한 줄**뿐이다 —
`"[src.engine.status_exit_watch] [status_exit_fire] … attempt=n …"`(R3 가 leaf 의 `write_log`
이중 쓰기를 걷었다 = cycle72 G-6). 그래서 시드는 `startswith("[status_exit_fire]")` 가 아니라
메시지 **어디든** `[status_exit_fire]` 를 찾아야 하고, 종목별 `attempt=` 최댓값이 발사 횟수다.
같은 발사가 모양만 다른 두 줄로 남아도(R2 빌드가 남긴 평문 줄 + 핸들러 줄) max 로 1 이다.
`[status_exit_fire_error]`·`[status_exit_would_fire]`·`[status_exit_giveup]` 는 발사가 아니다.

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

KST = timezone(timedelta(hours=9))
DAY = date(2026, 9, 28)
PREV = date(2026, 9, 27)


def _fire(ticker: str, attempt: int, sid: str = "bull_flag_breakout") -> str:
    return (
        f"[status_exit_fire] ticker={ticker} strategy={sid} reason=overheat iscd=59 mang=N "
        f"short_over=Y qty=3 mode=enforce attempt={attempt} bought_today=0"
    )


def _handler_copy(msg: str) -> str:
    """`_DbLogHandler` 가 남기는 줄 모양(🔁 R3 F3 — 발사 기록의 유일한 영속 모양)."""
    return f"[src.engine.status_exit_watch] {msg}"[:500]


def _at(d: date, h: int, m: int, s: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, m, s, tzinfo=KST)


async def _insert(pg_pool, rows):
    for ts, level, msg in rows:
        await pg_pool.execute(
            "INSERT INTO system_logs (timestamp, log_level, message) VALUES ($1, $2, $3)",
            ts, level, msg,
        )


def _seam():
    from src.engine import status_exit_watch as sew

    fn = getattr(sew, "_load_fire_counts", None)
    assert fn is not None, "[Red] status_exit_watch._load_fire_counts(day) 미존재 (Q4)"
    return fn


@pytest.mark.asyncio
async def test_q4_load_fire_counts_from_real_system_logs(clean_system_logs):
    pg_pool = clean_system_logs
    rows = [
        # 오늘 — 005160 두 번 발사(핸들러 줄) · 두 번째 발사는 R2 빌드의 평문 줄도 같이 남았다
        (_at(DAY, 9, 0, 31), "WARNING", _handler_copy(_fire("005160", 1))),
        (_at(DAY, 9, 5, 31), "WARNING", _handler_copy(_fire("005160", 2))),
        (_at(DAY, 9, 5, 31), "WARNING", _fire("005160", 2)),
        # 오늘 — 294140 한 번(핸들러 줄뿐 — R3 뒤의 정상 모양)
        (_at(DAY, 9, 5, 32), "WARNING", _handler_copy(_fire("294140", 1, "kojiro"))),
        # 오늘 00:10 KST = 전날 15:10 UTC — KST 날짜 경계 안쪽
        (_at(DAY, 0, 10), "WARNING", _handler_copy(_fire("000545", 1))),
        # 어제 — 세면 안 된다(23:50 KST 는 UTC 로 같은 날 14:50)
        (_at(PREV, 23, 50), "WARNING", _handler_copy(_fire("000545", 1))),
        (_at(PREV, 10, 0), "WARNING", _handler_copy(_fire("005160", 3))),
        # 오늘이지만 발사가 아닌 마커(핸들러 줄) — 세면 안 된다
        (_at(DAY, 9, 5, 33), "WARNING", _handler_copy(
            "[status_exit_fire_error] ticker=005160 strategy=bull_flag_breakout err=boom")),
        (_at(DAY, 9, 5, 34), "WARNING", _handler_copy(
            "[status_exit_would_fire] ticker=005160 strategy=bull_flag_breakout reason=overheat")),
        (_at(DAY, 9, 5, 35), "CRITICAL", _handler_copy(
            "[status_exit_giveup] ticker=005160 strategy=bull_flag_breakout fires=3")),
        (_at(DAY, 9, 5, 36), "WARNING", _handler_copy("[status_exit_fire] malformed-without-ticker")),
    ]
    await _insert(pg_pool, rows)

    got = await _seam()(DAY)
    assert {k: int(v) for k, v in dict(got).items() if int(v)} == {
        "005160": 2, "294140": 1, "000545": 1,
    }, got


@pytest.mark.asyncio
async def test_q4_load_fire_counts_empty_day(clean_system_logs):
    await _insert(clean_system_logs, [(_at(PREV, 10, 0), "WARNING", _handler_copy(_fire("005160", 1)))])
    got = await _seam()(DAY)
    assert not {k: v for k, v in dict(got).items() if int(v)}, got
