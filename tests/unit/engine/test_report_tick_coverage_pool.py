"""사이클 14-A (2026-05-18) — `_report_tick_coverage()` 풀 통합 회귀 가드.

사이클 11 에서 `scanner.get_scan_status()` 는 `kis_ws_pool.get_subscribed_tickers()`
풀 합집합으로 갱신됐지만, 짝궁 메서드 `_report_tick_coverage()` 가 함께
갱신되지 않은 누락 결함. 본 사이클 14-A 가 풀 통합 적용.

운영 사고 (2026-05-18 KST 12:57~14:25): 풀 25 종목 구독에도 system_logs
`[tick_coverage] subscribed=0` 출력 → 운영자가 "전부 끊김"이라고 오인.
사이클 14-A 배포 후 풀 실측치 25 가 정상 노출되어야 한다.

검증:
- Case A: 풀 합집합 25 종목 → subscribed=25
- Case B: 메인 0 + 보조 25 시 → subscribed=25 (보조 분배 가시화)
- Case C: 풀 0 → subscribed=0 (회귀 보존)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


KST_TZ = timezone(timedelta(hours=9))


@pytest.fixture(autouse=True)
def _reset_ticker_last_tick():
    from src.engine import scanner as scanner_module

    scanner_module.ticker_last_tick.clear()
    yield
    scanner_module.ticker_last_tick.clear()


# ===========================================================================
# Case A: 풀 합집합 25 종목 → subscribed=25 (사이클 14-A 핵심)
# ===========================================================================
@pytest.mark.asyncio
async def test_report_tick_coverage_reads_pool_union(caplog):
    """`_report_tick_coverage` 가 `kis_ws_pool.get_subscribed_tickers()` 풀 합집합을 사용.

    사이클 11 (`scanner.get_scan_status`) 와 동일 source 일관성 보장.
    """
    from src.engine import scanner as scanner_module
    from src.engine.scheduler import TradingScheduler
    from src.realtime.websocket_pool import kis_ws_pool

    now = datetime.now(KST_TZ)
    # 25 종목 모두 fresh (10초 전 tick)
    pool_tickers = {f"00{i:04d}" for i in range(25)}
    for t in pool_tickers:
        scanner_module.ticker_last_tick[t] = now - timedelta(seconds=10)

    with patch.object(kis_ws_pool, "get_subscribed_tickers",
                      return_value=pool_tickers):
        with patch("src.engine.scheduler.write_log", new=AsyncMock()) as mock_write_log:
            caplog.set_level(logging.INFO, logger="src.engine.scheduler")
            sched = TradingScheduler()
            await sched._report_tick_coverage()

    coverage_msgs = [r for r in caplog.records if "[tick_coverage]" in r.getMessage()]
    assert len(coverage_msgs) == 1, (
        f"풀 통합 후 [tick_coverage] 로그 1행 노출 필요, 실제={len(coverage_msgs)}"
    )
    msg = coverage_msgs[0].getMessage()
    assert "subscribed=25" in msg, (
        f"풀 25 종목 합집합이 subscribed=25 로 반영되어야 함, 실제 메시지={msg}"
    )
    assert "fresh=25" in msg
    assert "stale=0" in msg

    mock_write_log.assert_called_once()
    log_payload = mock_write_log.call_args.args[1]
    assert "subscribed=25" in log_payload


# ===========================================================================
# Case B: 메인 0 + 보조 25 (운영 사고 재현) → subscribed=25
# ===========================================================================
@pytest.mark.asyncio
async def test_report_tick_coverage_quote_only_25_reflects_pool(caplog):
    """메인 직접 구독 0 + 보조 25 인 상황 (2026-05-18 운영 사고) — 풀 25 반영.

    사이클 14-A 이전: `kis_ws.get_subscribed_tickers()` 메인 단독 → 0 노출 → 운영자 오인.
    사이클 14-A 이후: 풀 합집합 → 25 노출 → 실측 일관성.
    """
    from src.engine import scanner as scanner_module
    from src.engine.scheduler import TradingScheduler
    from src.realtime.websocket import kis_ws  # 메인 단독 (사이클 14-A 이전 source)
    from src.realtime.websocket_pool import kis_ws_pool

    now = datetime.now(KST_TZ)
    quote_tickers = {f"03{i:04d}" for i in range(25)}
    for t in quote_tickers:
        scanner_module.ticker_last_tick[t] = now - timedelta(seconds=20)

    # 메인 단독 mock 은 의도적으로 빈 set 반환 — 사이클 14-A 이전 결함 재현
    with patch.object(kis_ws, "get_subscribed_tickers", return_value=set()):
        # 풀 mock — 모든 25 종목이 보조 세션에 분배된 상태
        with patch.object(kis_ws_pool, "get_subscribed_tickers",
                          return_value=quote_tickers):
            with patch("src.engine.scheduler.write_log", new=AsyncMock()):
                caplog.set_level(logging.INFO, logger="src.engine.scheduler")
                sched = TradingScheduler()
                await sched._report_tick_coverage()

    msg = next(r.getMessage() for r in caplog.records if "[tick_coverage]" in r.getMessage())
    assert "subscribed=25" in msg, (
        "사이클 14-A — 메인 단독 0 이어도 풀 합집합 25 반영. "
        f"메인 mock=set() 이지만 풀 25 가 subscribed 로 노출되어야 함. 실제={msg}"
    )


# ===========================================================================
# Case C: 풀 0 → subscribed=0 (회귀 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_report_tick_coverage_empty_pool(caplog):
    """풀 자체가 0 종목이면 subscribed=0 — 기존 회귀 패턴 보존."""
    from src.engine.scheduler import TradingScheduler
    from src.realtime.websocket_pool import kis_ws_pool

    with patch.object(kis_ws_pool, "get_subscribed_tickers", return_value=set()):
        with patch("src.engine.scheduler.write_log", new=AsyncMock()):
            caplog.set_level(logging.INFO, logger="src.engine.scheduler")
            sched = TradingScheduler()
            await sched._report_tick_coverage()

    msgs = [r.getMessage() for r in caplog.records if "[tick_coverage]" in r.getMessage()]
    assert len(msgs) == 1
    assert "subscribed=0" in msgs[0]
    assert "fresh=0" in msgs[0]
    assert "stale=0" in msgs[0]
