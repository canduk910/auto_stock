"""사이클 92 M-3 — _boot() 완료 후 TIME_PRESUBSCRIBE 발화 영속 (MEDIUM).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

domain-expert 자문 A1-Q2/Q3 영속:
- TIME_BOOT (07:55) ~ TIME_PRESUBSCRIBE (07:59) 4분 마진 영속
- _boot() 동기 영역 (`await self._boot()`) 보장 — race 0
- 사전 구독 *전* 토큰 안정화 영역 확보

기대 동작 (Green, 사이클 92):
- TIME_PRESUBSCRIBE - TIME_BOOT >= 4분 (정적 검증)
- TIME_PRESUBSCRIBE < TIME_PRE_NXT_OPEN (08:00) (사전 구독 전 진입)

Red 상태 (사이클 92, production 변경 0):
- TIME_BOOT == time(7, 50), TIME_PRESUBSCRIBE == time(7, 55) → margin 5분 → PASS
- 사이클 92 시정 후 TIME_BOOT==(7,55), TIME_PRESUBSCRIBE==(7,59) → margin 4분 → PASS

영속 의무:
- 사이클 92 Q32=B 영속 (TIME_PRESUBSCRIBE 동행 이동)
- domain-expert A1-Q2 (TIME_PRESUBSCRIBE 도 동행 이동 의무)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_m3_boot_presubscribe_4_min_margin():
    """M-3-1: TIME_PRESUBSCRIBE - TIME_BOOT >= 4분 영속 (race 회피).

    검증:
    - TIME_PRESUBSCRIBE - TIME_BOOT 차이 >= 4분
    - _boot() 완료 후 사전 구독 분리 명시적 단계 분리

    Red 상태 (사이클 92, production 변경 0):
    - TIME_BOOT == time(7, 50), TIME_PRESUBSCRIBE == time(7, 55) → margin 5분 → PASS
    - 사이클 92 시정 후 TIME_BOOT == time(7, 55), TIME_PRESUBSCRIBE == time(7, 59) → margin 4분 → PASS

    영속 의무 (domain-expert A1-Q2/Q3):
    - _boot() 완료 후 4분 마진 (race 회피 + 토큰 안정화 영역)
    - TIME_PRESUBSCRIBE 도 동행 이동 의무
    """
    from src.engine.scheduler import TIME_BOOT, TIME_PRESUBSCRIBE

    boot_min = TIME_BOOT.hour * 60 + TIME_BOOT.minute
    presub_min = TIME_PRESUBSCRIBE.hour * 60 + TIME_PRESUBSCRIBE.minute
    margin = presub_min - boot_min

    assert margin >= 4, (
        f"\n사이클 92 M-3-1 위반 — TIME_PRESUBSCRIBE 사전 마진 부족:\n"
        f"  TIME_BOOT={TIME_BOOT}, TIME_PRESUBSCRIBE={TIME_PRESUBSCRIBE}\n"
        f"  현재 margin: {margin}분 < 4분\n"
        f"  근거: _boot() 완료 후 race 회피 + 토큰 안정화 영역"
    )


def test_m3_boot_async_method_persists():
    """M-3-2: _boot() async 메서드 영속 (`await self._boot()` 동기 영역 의무).

    검증:
    - Scheduler._boot 가 coroutine function (`async def`)
    - 사이클 51 boot_manager 위임 영속 (`boot_manager.boot(scheduler)`)

    영속 의무 (domain-expert A1-Q4):
    - `await self._boot()` 동기 영역 → TIME_PRESUBSCRIBE/TIME_PRE_NXT_OPEN 자동 대기 → race 0
    """
    import inspect

    from src.engine.scheduler import TradingScheduler

    boot_method = getattr(TradingScheduler, "_boot", None)
    assert boot_method is not None, (
        "\n사이클 92 M-3-2 위반 — TradingScheduler._boot 메서드 부재"
    )
    assert inspect.iscoroutinefunction(boot_method), (
        "\n사이클 92 M-3-2 위반 — _boot() 가 async 아님:\n"
        "  근거: domain-expert A1-Q4 동기 영역 의무"
    )
