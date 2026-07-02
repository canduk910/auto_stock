"""사이클 188 — `_wait_until(advance_if_passed=True)` never-return 회귀 시정 (Red).

승인 계획: `~/.claude/plans/188-bubbly-spring.md` (2026-07-02 사용자 승인).

결함 (사이클 160 회귀, 2026-06-17 도입 — 2주 지속):
`src/engine/scheduler.py::_wait_until(advance_if_passed=True)` 모드에 return 경로가 없다.
- 60초 단위 sleep 루프가 매 iteration "오늘의 target" 을 재계산.
- target 도달 순간 `now >= target` → `target_dt += 1일` 로 밀고 return 없이 계속 sleep.
- 자정 지나면 다시 "오늘 target" 대기 → 도달하면 또 `+1일` → 영원히 반복.
- 유일한 탈출 = `self._running = False`.

결과: `task_loop_helper.py::run_periodic_task_loop` while 루프 (production 유일 advance
호출처) 가 영원히 대기 → 모든 정기 task (16:00 일봉 / 16:10 basics / 16:15 purge /
16:20 저녁 funnel / 16:30 master / 20:00:05 universe) 정기 시각 발화 0회. 매일 아침
boot 의 `immediate_first_run` 만 발화.

기존 스위트가 못 잡은 이유:
cycle160 ADVANCE-1 / cycle152 PAST-1 등 기존 advance 케이스는 전부 *고정 clock*
(MockDT.now 고정값) + fake sleep 안에서 `_running=False` 강제 탈출 → "return 여부" 를
단언한 적 없음. 본 파일은 *전진 가상 시계* (fake sleep 이 가상 시각을 전진) 로 갭 전담.

mock 방식:
- `_VClock.current` = mutable 가상 시각. `_MockDT.now()` 가 이를 반환 (naive datetime).
- fake `asyncio.sleep(secs)` = 가상 시각을 `secs` 만큼 전진 + 호출 카운트.
- 무한 루프 안전망 = fake sleep 호출 5,000 회 초과 시 `_running=False` + `pytest.fail`.
  (현재 결함 코드의 advance 모드 never-return 을 유한 시간에 FAIL 로 포착.)
- freezegun 미사용 (사이클 187 교훈: freeze 된 monotonic + asyncio sleep = hang).

Green 계약 (목표 동작):
    호출 시점에 target_dt 1회 확정:
      now < target  → 오늘 target
      now >= target → default: 즉시 return (사이클 160 보존)
                      advance : 내일 동일 시각 +1일 (사이클 152 폭주 차단 보존)
    이후 while self._running 루프:
      now >= 확정 target_dt → return (사이클 188 신규 — 발화)
      아니면 asyncio.sleep(min(잔여초, 60))

회귀 가드:
- G-188-1 (HIGH): advance, now=10:00, target=16:00 → 당일 16:00 도달 시 return
- G-188-2 (HIGH): advance, now=18:00, target=16:30 → 익일 16:30 return + 당일 return 없음
- G-188-3 (HIGH): G-188-1/2 return 시점 = 확정 target 이상 + 초과 ≤ 60s
- G-188-4 (MED): default, now=16:00, target=15:20 → 즉시 return + sleep 0회
- G-188-5 (MED): default, now=10:00, target=15:20 → 15:20 도달 시 return
- G-188-6 (MED): advance, 대기 중 `_running=False` → 발화 없이 return
- G-188-7 (HIGH): 통합 run_periodic_task_loop(immediate_first_run=False) + 실제 _wait_until
                  → once_callable 정기 발화 ≥1

현재 production 코드 기준: G-188-1/2/3/7 FAIL, G-188-4/5/6 PASS.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from unittest.mock import patch

import pytest

_FAKE_SLEEP_CAP = 5_000


def _make_scheduler():
    """실제 `_wait_until` 본체 실행 영역 (mock 금지) — TradingScheduler 인스턴스."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._running = True
    return sched


class _VClock:
    """전진 가상 시계 — fake sleep 이 `current` 를 전진시킨다."""

    def __init__(self, start: datetime):
        self.current = start
        self.sleep_count = 0
        self.sleep_total = 0.0


def _patches(vclock: _VClock, sched, *, cap: int = _FAKE_SLEEP_CAP, stop_after=None):
    """`src.engine.scheduler.datetime` + `asyncio.sleep` patch 페어 생성.

    - `_MockDT.now()` = 가상 시각 (naive, 기존 cycle160/152 patch 경로 동일).
    - `_fake_sleep(secs)` = 가상 시각 전진 + 카운트. stop_after 도달 시 `_running=False`
      (G-188-6). cap 초과 시 `pytest.fail` (never-return 결함 유한 포착).
    """

    class _MockDT:
        @classmethod
        def now(cls):
            return vclock.current

    async def _fake_sleep(secs: float):
        vclock.sleep_count += 1
        vclock.sleep_total += secs
        vclock.current = vclock.current + timedelta(seconds=secs)
        if stop_after is not None and vclock.sleep_count >= stop_after:
            sched._running = False
            return
        if vclock.sleep_count > cap:
            sched._running = False
            pytest.fail(
                f"fake sleep 호출 상한 {cap} 초과 — _wait_until never-return 결함 재현 "
                f"(사이클 188 회귀). advance 모드가 target 도달 후에도 +1일로 밀며 무한 sleep."
            )

    return _MockDT, _fake_sleep


@pytest.mark.asyncio
async def test_g_188_1_advance_same_day_returns():
    """G-188-1 (HIGH) — advance 모드, 당일 target 도달 시 return.

    now=10:00, target=16:00 → 오늘 16:00 도달 시 반드시 return.
    현재 코드 = 16:00 도달 후 +1일로 밀며 무한 advance → cap 초과 FAIL.
    """
    sched = _make_scheduler()
    vclock = _VClock(datetime(2026, 7, 2, 10, 0, 0))
    target = time(16, 0)
    mockdt, fake_sleep = _patches(vclock, sched)

    with patch("src.engine.scheduler.datetime", mockdt), \
         patch("asyncio.sleep", fake_sleep):
        await sched._wait_until(target, advance_if_passed=True)

    # return 시점 = 당일 16:00 이상 + 다음 날로 밀리지 않음
    assert vclock.current >= datetime(2026, 7, 2, 16, 0, 0), (
        f"advance 모드 당일 target 도달 시 return 의무. current={vclock.current}"
    )
    assert vclock.current < datetime(2026, 7, 3, 0, 0, 0), (
        f"당일 target 인데 +1일로 밀려 다음 날 대기 = never-return 결함. "
        f"current={vclock.current}"
    )


@pytest.mark.asyncio
async def test_g_188_2_advance_next_day_returns_no_same_day_return():
    """G-188-2 (HIGH) — advance 모드, target 이미 지난 시점 → 익일 도달 시 return.

    now=18:00, target=16:30 → 오늘 16:30 이미 지남 → 내일 16:30 대기 후 return.
    당일 (18:00 시점) 즉시 return 금지 (사이클 152 폭주 차단 보존).
    현재 코드 = 내일 16:30 도달 후에도 +1일로 밀며 무한 → cap 초과 FAIL.
    """
    sched = _make_scheduler()
    vclock = _VClock(datetime(2026, 7, 2, 18, 0, 0))
    target = time(16, 30)
    mockdt, fake_sleep = _patches(vclock, sched)

    with patch("src.engine.scheduler.datetime", mockdt), \
         patch("asyncio.sleep", fake_sleep):
        await sched._wait_until(target, advance_if_passed=True)

    # 내일 16:30 도달 후 return (당일 즉시 return = 사이클 152 이전 폭주 결함)
    assert vclock.current >= datetime(2026, 7, 3, 16, 30, 0), (
        f"target 지난 시점 advance = 내일 동일 시각 대기 후 return 의무. "
        f"current={vclock.current}"
    )
    assert vclock.current.date() == date(2026, 7, 3), (
        f"당일 즉시 return 금지 (사이클 152 폭주 차단 보존). return date={vclock.current.date()}"
    )


@pytest.mark.asyncio
async def test_g_188_3_return_time_within_60s_of_target():
    """G-188-3 (HIGH) — return 시점이 확정 target 이상 + 초과 ≤ 60s.

    G-188-1/2 시나리오 모두에서 재-advance 로 밀리지 않음 (정확히 target 창에 return).
    현재 코드 = 두 시나리오 모두 never-return → cap 초과 FAIL.
    """
    # 시나리오 A — advance 당일 (now=10:00, target=16:00)
    sched_a = _make_scheduler()
    vclock_a = _VClock(datetime(2026, 7, 2, 10, 0, 0))
    mockdt_a, fake_sleep_a = _patches(vclock_a, sched_a)
    with patch("src.engine.scheduler.datetime", mockdt_a), \
         patch("asyncio.sleep", fake_sleep_a):
        await sched_a._wait_until(time(16, 0), advance_if_passed=True)

    overshoot_a = (vclock_a.current - datetime(2026, 7, 2, 16, 0, 0)).total_seconds()
    assert 0 <= overshoot_a <= 60, (
        f"당일 advance return 초과 ≤ 60s 의무 (재-advance 밀림 없음). overshoot={overshoot_a}s"
    )

    # 시나리오 B — advance 익일 (now=18:00, target=16:30)
    sched_b = _make_scheduler()
    vclock_b = _VClock(datetime(2026, 7, 2, 18, 0, 0))
    mockdt_b, fake_sleep_b = _patches(vclock_b, sched_b)
    with patch("src.engine.scheduler.datetime", mockdt_b), \
         patch("asyncio.sleep", fake_sleep_b):
        await sched_b._wait_until(time(16, 30), advance_if_passed=True)

    overshoot_b = (vclock_b.current - datetime(2026, 7, 3, 16, 30, 0)).total_seconds()
    assert 0 <= overshoot_b <= 60, (
        f"익일 advance return 초과 ≤ 60s 의무. overshoot={overshoot_b}s"
    )


@pytest.mark.asyncio
async def test_g_188_4_default_passed_immediate_return_no_sleep():
    """G-188-4 (MED) — default 모드, target 이미 지남 → 즉시 return + sleep 0회.

    사이클 160 BREAK 본질 보존 (run_daily phase 전환 즉시 진입).
    """
    sched = _make_scheduler()
    vclock = _VClock(datetime(2026, 7, 2, 16, 0, 0))
    target = time(15, 20)
    mockdt, fake_sleep = _patches(vclock, sched)

    with patch("src.engine.scheduler.datetime", mockdt), \
         patch("asyncio.sleep", fake_sleep):
        await sched._wait_until(target)  # default (advance_if_passed=False)

    assert vclock.sleep_count == 0, (
        f"default 모드 target 지난 시점 즉시 return = sleep 0회 의무 (사이클 160 본질). "
        f"sleep_count={vclock.sleep_count}"
    )


@pytest.mark.asyncio
async def test_g_188_5_default_future_returns_at_target():
    """G-188-5 (MED) — default 모드, target 미래 → 도달 시 return (원설계 보존)."""
    sched = _make_scheduler()
    vclock = _VClock(datetime(2026, 7, 2, 10, 0, 0))
    target = time(15, 20)
    mockdt, fake_sleep = _patches(vclock, sched)

    with patch("src.engine.scheduler.datetime", mockdt), \
         patch("asyncio.sleep", fake_sleep):
        await sched._wait_until(target)

    assert vclock.current >= datetime(2026, 7, 2, 15, 20, 0), (
        f"default 모드 target 도달 시 return 의무. current={vclock.current}"
    )
    assert vclock.current < datetime(2026, 7, 2, 16, 20, 0), (
        f"target 창 근처 return 의무 (밀림 없음). current={vclock.current}"
    )


@pytest.mark.asyncio
async def test_g_188_6_advance_running_false_returns_without_firing():
    """G-188-6 (MED) — advance 모드 대기 중 `_running=False` → 발화 없이 return.

    헬퍼의 `if not scheduler._running: break` 가 흡수하는 종료 경로.
    target 도달 *전* `_running=False` → 루프 탈출 + 미발화.
    """
    sched = _make_scheduler()
    vclock = _VClock(datetime(2026, 7, 2, 10, 0, 0))
    target = time(16, 0)
    # 3번째 sleep 후 _running=False (target 16:00 도달 전 = ~10:03)
    mockdt, fake_sleep = _patches(vclock, sched, stop_after=3)

    with patch("src.engine.scheduler.datetime", mockdt), \
         patch("asyncio.sleep", fake_sleep):
        await sched._wait_until(target, advance_if_passed=True)

    assert vclock.current < datetime(2026, 7, 2, 16, 0, 0), (
        f"_running=False 로 target 도달 전 return (미발화) 의무. current={vclock.current}"
    )


@pytest.mark.asyncio
async def test_g_188_7_periodic_task_loop_fires_at_scheduled_time():
    """G-188-7 (HIGH) — 통합: run_periodic_task_loop + 실제 _wait_until 정기 발화.

    immediate_first_run=False → 즉시 발화 없이 while 루프 진입 → _wait_until(16:00,
    advance=True) → once_callable 정기 발화 ≥1 (end-to-end). 1회 발화 후 `_running=False`
    로 종료. 현재 코드 = _wait_until never-return → once_callable 0회 → cap 초과 FAIL.
    """
    from src.engine.task_loop_helper import run_periodic_task_loop

    sched = _make_scheduler()
    vclock = _VClock(datetime(2026, 7, 2, 10, 0, 0))
    mockdt, fake_sleep = _patches(vclock, sched)

    fired_at: list[datetime] = []

    async def _once_callable() -> dict:
        fired_at.append(vclock.current)
        sched._running = False  # 1회 발화 후 루프 종료
        return {}

    def _record_fn(summary: dict) -> None:
        return None

    def _flush_fn() -> None:
        return None

    with patch("src.engine.scheduler.datetime", mockdt), \
         patch("asyncio.sleep", fake_sleep):
        await run_periodic_task_loop(
            scheduler=sched,
            task_label="cycle188_test",
            wait_time=time(16, 0),
            once_callable=_once_callable,
            record_fn=_record_fn,
            flush_fn=_flush_fn,
            summary_log_format="[cycle188_test]",
            summary_keys=(),
            immediate_first_run=False,
        )

    assert len(fired_at) >= 1, (
        "정기 시각 도달 시 once_callable 발화 의무 (모든 정기 task 발화 = _wait_until "
        "advance 모드 return 의존). 발화 0회 = never-return 결함."
    )
    # 정기 발화 시점 = 당일 16:00 (재-advance 밀림 없음)
    assert fired_at[0] >= datetime(2026, 7, 2, 16, 0, 0), (
        f"정기 발화 시점 = 당일 16:00 도달 후 의무. fired_at={fired_at[0]}"
    )
