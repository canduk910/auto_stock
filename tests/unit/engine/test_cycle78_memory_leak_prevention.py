"""사이클 78 의제 2 — collector 메모리 leak 차단 검증.

Red 단계: flush 호출 사이트 미존재 → collector 무한 누적 → 운영 후 비워지지 않음 FAIL.
Green 단계: 5분 주기 task 가 collector flush → 윈도우 종료 후 `len == 0` PASS.

운영 메모리 leak 위험:
- `_swing_rest_poll_collector: list[dict]` 60s 주기 → 5분 = 5 dict 누적 → flush 후 0
- `_stale_watcher_collector: list[dict]` 120s 주기 → 5분 = 2.5 → 3 dict 누적 → flush 후 0
- flush 호출 사이트 누락 = 영업일 12시간 운영 = 720 + 360 = 1,080 dict / day 누적

영속 의무:
- 사이클 17 KIS LMS chain 차단 / 사이클 38 명문화 / 매매 안전성 영향 0
- 사이클 74 record/flush 함수 시그너처 영속 (호출 사이트만 신규 추가)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# G-ML1: 5분 윈도우 종료 후 양쪽 collector 모두 비워짐 (운영 leak 차단)
# ===========================================================================
@pytest.mark.asyncio
async def test_g_ml1_periodic_task_clears_both_collectors(monkeypatch):
    """G-ML1: 5분 주기 task 1회 실행 후 양쪽 collector 모두 `len == 0`.

    검증 방식:
    1. `_swing_rest_poll_collector` + `_stale_watcher_collector` 에 임의 stats 누적
    2. 스케줄러 5분 주기 task (옵션 1 = `_api_recovered_collector_loop` 본체) 1회 실행
       - asyncio.sleep monkeypatch 로 즉시 통과
       - `self._running` True → False 전환으로 단일 루프만 실행
    3. 양쪽 collector 모두 `len == 0` 확인 (메모리 leak 차단)

    Red: 5분 주기 task 가 swing/stale flush 호출 안 함 → collector 잔존 → FAIL
    Green: 양쪽 flush 호출 → collector 비워짐 → PASS

    영구 가드 — 미래 5분 주기 task 본체에서 flush 호출 제거 시 즉시 FAIL.
    """
    import asyncio

    from src.engine import scheduler as _sched
    from src.engine import stale_watcher_core as _swc

    # Step 1: 양쪽 collector 에 stats 누적 (5 + 3 건)
    _sched._swing_rest_poll_collector.clear()
    _swc._stale_watcher_collector.clear()

    for i in range(5):
        _sched.record_swing_rest_poll({
            "candidates": 10 + i,
            "held": 2,
            "pending": 0,
            "updated": 10 + i,
            "failed": 0,
            "elapsed_ms": 1000 + i * 100,
        })
    for i in range(3):
        _swc.record_stale_watcher_check({
            "subscribed": 30,
            "stale": i,
            "force_reregistered": 0,
            "skipped_giveup": 0,
            "force_retried": 0,
            "cap_blocked": 0,
        })

    assert len(_sched._swing_rest_poll_collector) == 5, (
        "G-ML1: 사전 누적 swing collector 5 건 실패"
    )
    assert len(_swc._stale_watcher_collector) == 3, (
        "G-ML1: 사전 누적 stale collector 3 건 실패"
    )

    # Step 2: 스케줄러 5분 주기 task 1회 실행
    scheduler_instance = _sched.TradingScheduler()
    scheduler_instance._running = True

    # asyncio.sleep monkeypatch → 즉시 통과 + 단일 루프 보장
    sleep_call_count = {"n": 0}
    original_sleep = asyncio.sleep

    async def _fast_sleep(delay):
        sleep_call_count["n"] += 1
        # 첫 sleep 후 _running False → 다음 iteration break
        if sleep_call_count["n"] >= 1:
            scheduler_instance._running = False
        # 진정한 sleep 0 (event loop yield)
        await original_sleep(0)

    monkeypatch.setattr("src.engine.scheduler.asyncio.sleep", _fast_sleep)

    # `_flush_api_recovered_collector` + `_flush_quote_recovered_collector` 는
    # `src/api/base.py` 정의 — 본 테스트 영역 외부, 부수 효과 0 (스텁 불요).
    # 본 테스트는 *swing + stale collector 가 비워지는지* 만 검증.

    await scheduler_instance._api_recovered_collector_loop()

    # Step 3: 양쪽 collector 모두 비워짐 확인 (메모리 leak 차단 영구 가드)
    assert len(_sched._swing_rest_poll_collector) == 0, (
        f"\n사이클 78 G-ML1 위반 — 5분 주기 task 1회 실행 후 "
        f"`_swing_rest_poll_collector` 잔존 {len(_sched._swing_rest_poll_collector)} 건.\n"
        f"  메모리 leak: 720 dict/day 누적 영구 (영업일 12시간 운영)\n"
        f"  시정: `_api_recovered_collector_loop` 본체에 "
        f"`flush_swing_rest_poll_collector()` 호출 추가"
    )
    assert len(_swc._stale_watcher_collector) == 0, (
        f"\n사이클 78 G-ML1 위반 — 5분 주기 task 1회 실행 후 "
        f"`_stale_watcher_collector` 잔존 {len(_swc._stale_watcher_collector)} 건.\n"
        f"  메모리 leak: 360 dict/day 누적 영구\n"
        f"  시정: `_api_recovered_collector_loop` 본체에 "
        f"`flush_stale_watcher_collector()` 호출 추가\n"
        f"  import: from src.engine.stale_watcher_core import flush_stale_watcher_collector"
    )
