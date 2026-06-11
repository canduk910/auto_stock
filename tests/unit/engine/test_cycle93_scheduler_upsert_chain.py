"""사이클 93 G-CC1 (HIGH) — scheduler 개장 전 1회 분기 stock_master upsert chain 의무.

Red 명세 (`_workspace/red/cycle93_call_chain_broken.md`):

`src/engine/scheduler.py::TradingScheduler._universe_eager_refresh_loop` self method
개장 전 1회 분기 (사이클 89 도입 L2616~L2624) 가 `fetch_top_500_universe()` 결과
ticker list 를 scanner module 의 `_universe_eager_refresh_loop(candidates)` 모듈 함수
(stock_master upsert 담당, 사이클 89 도입) 에 정확히 위임해야 한다.

Red 상태 (사이클 93 시점):
- scheduler self method 가 `tickers = await fetch_top_500_universe()` 후 ticker
  list 를 *버림* → scanner module `_universe_eager_refresh_loop` 호출 카운트 = 0
- mock scanner module `_universe_eager_refresh_loop` 가 호출되지 않음 → FAIL

Green (backend-dev 인계 후):
- scheduler self method 가 `from src.engine.scanner import _universe_eager_refresh_loop
  as _scanner_upsert_loop` + `await _scanner_upsert_loop(tickers)` 추가
- mock 호출 카운트 = 1 + 인자 = mock fetch 반환 ticker list → PASS

영속 의무:
- 사이클 89 silent 결함 (호출 chain broken) 영구 차단 = silent 결함 21회 누적
- 매매 안전성 무영향 (stock_master 영역, 매도 hot path 무관)
- 사이클 38 명문화 영속 (`tradable_boards` 영향 0)
- 사이클 32 R4 universe guard 영속 (보유/익일청산 절대 보호 영역 별개)
- WebSocket 4중 안전망 / 사이클 17 KIS LMS chain 영역 무관
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


_MOCK_TICKERS = ["005930", "402340", "035720", "000660", "035420"]


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q69=B — `_universe_eager_refresh_loop` (scheduler self method + scanner module) 영구 폐기 "
        "(`_full_universe_load_task_loop` + `_full_universe_load_once` 으로 전환). "
        "사이클 93 시점 개장 전 chain 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
@pytest.mark.asyncio
async def test_g_cc1_scheduler_boot_chain_calls_scanner_upsert_with_tickers(monkeypatch):
    """G-CC1: scheduler 개장 전 1회 분기에서 scanner module `_universe_eager_refresh_loop`
    가 정확히 ticker list 인자로 1회 호출되어야 한다 (사이클 89 chain broken 영구 시정).

    검증 매트릭스:
    1. mock `fetch_top_500_universe` → 5 ticker 반환
    2. mock scanner module `_universe_eager_refresh_loop` (AsyncMock)
    3. scheduler self method `_universe_eager_refresh_loop()` 호출 (_running=False 로 5분 루프 skip)
    4. 의무: scanner module 함수 1회 호출 + 인자 = mock ticker list

    Red 상태: scheduler L2618 `tickers = await fetch_top_500_universe()` 후 ticker 버림
    → scanner module 호출 0회 → FAIL.

    Green: `from src.engine.scanner import _universe_eager_refresh_loop as _scanner_upsert_loop`
    + `await _scanner_upsert_loop(tickers)` 추가 → 1회 호출 → PASS.
    """
    from src.engine import scanner as _scanner_mod
    from src.engine.scheduler import TradingScheduler

    # 사전 조건: scanner module `_universe_eager_refresh_loop` 모듈 함수 존재 (사이클 89)
    assert hasattr(_scanner_mod, "_universe_eager_refresh_loop"), (
        "G-CC1 사전조건: scanner module `_universe_eager_refresh_loop` 부재 — "
        "사이클 89 도입 영역 회귀."
    )

    fetch_mock = AsyncMock(return_value=list(_MOCK_TICKERS))
    upsert_mock = AsyncMock(return_value=None)
    flush_mock = AsyncMock(return_value=None)

    monkeypatch.setattr(_scanner_mod, "fetch_top_500_universe", fetch_mock, raising=False)
    monkeypatch.setattr(
        _scanner_mod, "_universe_eager_refresh_loop", upsert_mock, raising=False
    )

    # flush_universe_collector 는 sync 함수 — patch 로 noop
    from src.engine import stock_master_metrics as _sm_metrics
    monkeypatch.setattr(
        _sm_metrics, "flush_universe_collector", lambda: None, raising=False
    )

    sched = TradingScheduler()
    sched._running = False  # 5분 주기 while loop 진입 차단 (개장 전 1회만 실행)

    await sched._universe_eager_refresh_loop()

    # 의무 1: fetch_top_500_universe 1회 호출
    assert fetch_mock.call_count == 1, (
        f"개장 전 1회 fetch 의무, 실제 {fetch_mock.call_count}회"
    )

    # 의무 2 (핵심 HIGH): scanner module _universe_eager_refresh_loop 1회 호출
    assert upsert_mock.call_count == 1, (
        f"\n사이클 93 G-CC1 위반 — scheduler 개장 전 1회 분기에서 "
        f"scanner module `_universe_eager_refresh_loop` 호출 누락:\n\n"
        f"  fetch_top_500_universe 호출:    {fetch_mock.call_count}회\n"
        f"  scanner upsert chain 호출:      {upsert_mock.call_count}회 (의무 1회)\n\n"
        f"  결함 원인: scheduler.py L2618 `tickers = await fetch_top_500_universe()`\n"
        f"             후 ticker list *버림* → stock_master upsert 영구 0건\n"
        f"             → 사용자 보고 stock_master 60 ticker 영속 (사이클 89 silent 결함)\n\n"
        f"  시정 (Green): scheduler self method 에 다음 추가\n"
        f"    from src.engine.scanner import (\n"
        f"        fetch_top_500_universe,\n"
        f"        _universe_eager_refresh_loop as _scanner_upsert_loop,\n"
        f"    )\n"
        f"    tickers = await fetch_top_500_universe()\n"
        f"    try:\n"
        f"        await _scanner_upsert_loop(tickers)\n"
        f"    except Exception:\n"
        f"        logger.exception('[universe_eager_refresh] stock_master upsert 실패 graceful')"
    )

    # 의무 3: 인자 정확성 (ticker list 그대로 전달)
    args, _kwargs = upsert_mock.call_args
    assert args and list(args[0]) == _MOCK_TICKERS, (
        f"scanner upsert chain 인자 = fetch ticker list 의무, "
        f"실제 args={args}"
    )
