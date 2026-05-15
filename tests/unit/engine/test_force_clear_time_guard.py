"""`_force_clear_main_only` KRX 메인 마감 후 호출 skip (2026-05-15 사고 hot fix).

배경:
    5/15 15:41, 16:04 두 차례 EC2 재시작 → _boot 후 scheduler.start() 가
    `now > TIME_KRX_MAIN_BUY_STOP(15:20)` else 분기에 들어가도 직후 라인 380 에서
    `_force_clear_main_only()` 무조건 호출 → VB 보유(000100, 066570) 청산 시도
    → SOR 시장가 → KRX 애프터(15:30~) APBK3013 거부 × 3회 재시도 모두 실패.

    시세 캐시 미확보(재시작 직후 WS 미수신)로 `is_market_order_disallowed` 폴백
    (`step_down(current_price, 5)` 지정가) 도 작동 안 함 → CRITICAL 매도 실패.

결정:
    `_force_clear_main_only()` 진입 즉시 시간 가드. KRX 메인 마감(15:30) 이후면
    skip + 익일 청산 안전망(`_execute_next_day_clear`)에 위임 (방금 추가한 VB 안전망).

Red:
    15:31 시각 고정 + VB 보유 종목 fixture → `_force_clear_main_only()` 호출 →
    `execute_sell` 호출되면 안 됨 (시간 가드로 즉시 return).
    결함 상태에선 execute_sell 호출됨.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

from src.engine.scheduler import TradingScheduler
from src.engine.strategy_base import Position

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
@freeze_time("2026-05-15 15:31:00")
async def test_force_clear_main_only_skipped_after_krx_main_close():
    """KRX 메인 마감(15:30) 이후 호출 시 execute_sell 호출 안 함."""
    sched = TradingScheduler()
    sched._running = True

    vb = sched.registry.get("volatility_breakout")
    assert vb is not None
    vb.config.enabled = True
    vb.state.positions["066570"] = Position(
        ticker="066570", buy_price=237000, quantity=1,
        order_no="O-TEST", strategy_id="volatility_breakout",
    )

    execute_sell_mock = AsyncMock()
    with patch.object(sched.order_engine, "execute_sell", new=execute_sell_mock), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()):
        await sched._force_clear_main_only()

    assert execute_sell_mock.await_count == 0, (
        "15:30 이후 호출인데 execute_sell 발동됨 — 시간 가드 누락. "
        "재시작 시점이 KRX 메인 마감 후면 SOR 시장가 매도가 APBK3013 으로 "
        "거부됨 (5/15 운영 사고 회귀)."
    )


@pytest.mark.asyncio
@freeze_time("2026-05-15 15:19:00")
async def test_force_clear_main_only_runs_before_krx_main_close():
    """15:20 직전 정상 시간대(15:19)에는 그대로 작동 — 회귀 가드."""
    sched = TradingScheduler()
    sched._running = True

    vb = sched.registry.get("volatility_breakout")
    assert vb is not None
    vb.config.enabled = True
    vb.state.positions["066570"] = Position(
        ticker="066570", buy_price=237000, quantity=1,
        order_no="O-TEST", strategy_id="volatility_breakout",
    )

    execute_sell_mock = AsyncMock()
    with patch.object(sched.order_engine, "execute_sell", new=execute_sell_mock), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()):
        await sched._force_clear_main_only()

    # 정상 시간대엔 청산 호출 발동
    assert execute_sell_mock.await_count >= 1, (
        "15:20 정상 시간대인데 청산이 발동되지 않음 — 시간 가드가 너무 엄격."
    )


@pytest.mark.asyncio
@freeze_time("2026-05-15 15:30:00")
async def test_force_clear_main_only_boundary_15_30_exact_is_skipped():
    """15:30 정각 boundary는 skip (KRX 메인 마감 시작)."""
    sched = TradingScheduler()
    sched._running = True

    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.state.positions["066570"] = Position(
        ticker="066570", buy_price=237000, quantity=1,
        order_no="O-TEST", strategy_id="volatility_breakout",
    )

    execute_sell_mock = AsyncMock()
    with patch.object(sched.order_engine, "execute_sell", new=execute_sell_mock), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()):
        await sched._force_clear_main_only()

    assert execute_sell_mock.await_count == 0, (
        "15:30 정각 호출은 KRX 메인 마감 시점이므로 SOR 시장가 매도 거부 위험 — skip 해야 함."
    )
