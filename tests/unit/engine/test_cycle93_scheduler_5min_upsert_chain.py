"""사이클 93 G-CC2 (HIGH) — scheduler 5분 주기 분기 stock_master upsert chain 의무.

Red 명세 (`_workspace/red/cycle93_call_chain_broken.md`):

`src/engine/scheduler.py::TradingScheduler._universe_eager_refresh_loop` self method
**5분 주기 while 루프 분기** (L2627~L2640) 가 매 5분마다 `fetch_top_500_universe()`
결과 ticker list 를 scanner module `_universe_eager_refresh_loop` 에 정확히 위임해야 한다.

Red 상태 (사이클 93 시점):
- 5분 주기 분기도 L2630 `tickers = await fetch_top_500_universe()` 후 ticker 버림
- scanner module upsert 호출 0회 → FAIL

Green (backend-dev 인계 후):
- 5분 분기에도 `await _scanner_upsert_loop(tickers)` 추가
- 개장 전 1회 + 5분 1회 = 총 2회 호출 (asyncio.sleep mock 으로 즉시 진행)

영속 의무:
- 사이클 89 silent 결함 영구 차단 (5분 주기까지)
- 매매 안전성 무영향 (stock_master 영역)
- 사이클 38 명문화 영속
- 사이클 42 5분 주기 `_heartbeat_metrics_loop` 패턴 답습
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


_MOCK_TICKERS = ["005930", "402340", "035720"]


@pytest.mark.asyncio
async def test_g_cc2_scheduler_5min_loop_calls_scanner_upsert_per_cycle(monkeypatch):
    """G-CC2: 5분 주기 분기에서도 매 사이클 scanner module upsert chain 호출 의무.

    검증 매트릭스:
    1. mock fetch_top_500_universe → 3 ticker 반환
    2. mock scanner module `_universe_eager_refresh_loop` (AsyncMock)
    3. asyncio.sleep mock → 5분 즉시 진행 + 1회만 sleep 후 _running=False 분기
    4. 의무: 개장 전 1회 + 5분 1회 = 총 2회 호출

    Red 상태: L2630 5분 분기에서 ticker 버림 → 5분마다 upsert 0회 → FAIL.

    Green: 5분 분기에도 `await _scanner_upsert_loop(tickers)` 추가 → 2회 호출 → PASS.

    영속: 운영 가시화 — `[universe_eager_refresh] 5분 주기 fetch 완료 universe=%d` INFO
    가 emit 되어도 stock_master upsert 0건 결함이 영구 잔존하던 chain broken 차단.
    """
    from src.engine import scanner as _scanner_mod
    from src.engine import stock_master_metrics as _sm_metrics
    from src.engine.scheduler import TradingScheduler

    fetch_mock = AsyncMock(return_value=list(_MOCK_TICKERS))
    upsert_mock = AsyncMock(return_value=None)

    monkeypatch.setattr(_scanner_mod, "fetch_top_500_universe", fetch_mock, raising=False)
    monkeypatch.setattr(
        _scanner_mod, "_universe_eager_refresh_loop", upsert_mock, raising=False
    )
    monkeypatch.setattr(
        _sm_metrics, "flush_universe_collector", lambda: None, raising=False
    )

    sched = TradingScheduler()
    sched._running = True  # 5분 주기 while loop 진입 허용

    # asyncio.sleep mock — 1회 sleep 후 _running=False 로 루프 종료
    sleep_call_count = {"n": 0}

    async def _fake_sleep(seconds: float) -> None:
        sleep_call_count["n"] += 1
        if sleep_call_count["n"] >= 1:
            sched._running = False  # 5분 1 cycle 후 종료

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    await sched._universe_eager_refresh_loop()

    # 의무 1: fetch 2회 (개장 전 1회 + 5분 1회)
    assert fetch_mock.call_count == 2, (
        f"fetch_top_500_universe 호출 = 개장 전 1 + 5분 1 = 2회 의무, "
        f"실제 {fetch_mock.call_count}회"
    )

    # 의무 2 (핵심 HIGH): scanner upsert chain 도 2회 호출
    assert upsert_mock.call_count == 2, (
        f"\n사이클 93 G-CC2 위반 — scheduler 5분 주기 분기에서 "
        f"scanner module `_universe_eager_refresh_loop` 호출 누락:\n\n"
        f"  fetch_top_500_universe 호출:    {fetch_mock.call_count}회 (개장 전 + 5분)\n"
        f"  scanner upsert chain 호출:      {upsert_mock.call_count}회 (의무 2회)\n\n"
        f"  결함 원인: scheduler.py L2630 5분 분기에서도 ticker list 버림\n"
        f"             → stock_master 영구 갱신 무용 (chain broken)\n\n"
        f"  시정 (Green): 5분 분기에도 동일 위임 추가 (개장 전 1회 분기 패턴 답습)\n"
        f"    try:\n"
        f"        await _scanner_upsert_loop(tickers)\n"
        f"    except Exception:\n"
        f"        logger.exception('[universe_eager_refresh] stock_master upsert 실패 graceful')"
    )

    # 의무 3: 모든 호출 인자 = mock ticker list
    for call in upsert_mock.call_args_list:
        args, _kwargs = call
        assert args and list(args[0]) == _MOCK_TICKERS, (
            f"scanner upsert chain 인자 = ticker list 의무, "
            f"실제 args={args}"
        )
