"""VB 당일 15:20 일괄 청산 정책 (2026-05-15, 결함 D).

배경:
    VB 정책 "당일 -3% 손절 + 15:20 KRX 메인 청산"이 OVERNIGHT 거부 원칙임에도
    DEFAULT_TRADABLE_BOARDS 에 POST_NXT 포함 → `_force_clear_main_only` 의
    "POST_NXT 활성 전략은 19:50까지 보류" 분기로 빠져 15:20 청산 스킵.
    그러나 19:50 시점에는 매수 중단(buy_disabled=True) + AI자문만 호출되고
    **강제 청산 코드 자체가 누락** → 결과적으로 5/13~5/15 005930 멀티데이
    보유 후 손절. VB가 사실상 donchian처럼 동작하던 결함.

결정 (2026-05-15):
    VB 를 당일 15:20 일괄매도로 변경. DEFAULT_TRADABLE_BOARDS 에서 POST_NXT 제거.
    → 15:20 _force_clear_main_only 가 VB 를 청산 대상으로 인식 (keeps_post_nxt=False).

Red:
    1. `VolatilityBreakoutStrategy.DEFAULT_TRADABLE_BOARDS` 에 "post_nxt" 가 없어야 함.
    2. `DEFAULT_PARAMS["tradable_boards"]` 도 동일.
    3. `_force_clear_main_only()` 가 VB 의 보유 종목에 대해 `execute_sell(FORCE_CLEAR)`
       호출 — POST_NXT 활성 분기로 스킵되지 않음.

회귀 가드: LTV 는 별도 정책 (롱테일 청산 모드) 이라 본 테스트 대상 아님.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.engine.scheduler import TradingScheduler
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Position, Signal

pytestmark = pytest.mark.unit


def test_vb_default_tradable_boards_excludes_post_nxt():
    """VB DEFAULT_TRADABLE_BOARDS 에 post_nxt 가 포함되면 안 됨.

    결정 (2026-05-15): VB 는 당일 15:20 일괄매도 정책 — NXT 애프터 매매 비활성.
    """
    assert "post_nxt" not in VolatilityBreakoutStrategy.DEFAULT_TRADABLE_BOARDS, (
        "VB DEFAULT_TRADABLE_BOARDS 에 post_nxt 가 포함되어 있음 — "
        "당일 15:20 일괄매도 정책과 충돌. 15:20 _force_clear_main_only 가 "
        "POST_NXT 활성 분기로 빠져 청산 스킵 → OVERNIGHT 보유 결함 회귀."
    )
    # PRE_NXT + MAIN 만 활성 (08:00~15:20)
    assert "pre_nxt" in VolatilityBreakoutStrategy.DEFAULT_TRADABLE_BOARDS
    assert "main" in VolatilityBreakoutStrategy.DEFAULT_TRADABLE_BOARDS


def test_vb_default_params_tradable_boards_excludes_post_nxt():
    """DEFAULT_PARAMS['tradable_boards'] 도 동일하게 post_nxt 제외."""
    assert "post_nxt" not in VolatilityBreakoutStrategy.DEFAULT_PARAMS["tradable_boards"]


@pytest.mark.asyncio
async def test_force_clear_main_only_targets_vb_at_15_20():
    """15:20 `_force_clear_main_only()` 호출 시 VB 보유 종목이 청산 대상이어야 함.

    POST_NXT 활성 분기(keeps_post_nxt=True) 로 스킵되면 안 됨.
    """
    sched = TradingScheduler()
    sched._running = True

    vb = sched.registry.get("volatility_breakout")
    assert vb is not None
    vb.config.enabled = True
    vb.state.positions["005930"] = Position(
        ticker="005930", buy_price=284250, quantity=1,
        order_no="O-TEST", strategy_id="volatility_breakout", buy_date="2026-05-15",
    )

    # 15:20 청산 후보를 반환하도록 check_force_clear 가 동작해야 함.
    # 기본 구현은 모든 보유 종목 반환 (POST_NXT 미활성 전략 한정).
    execute_sell_mock = AsyncMock()
    # `_force_clear_main_only` 내부의 `write_log` 는 실제 Supabase HTTP 호출 — mock 필요.
    with patch.object(sched.order_engine, "execute_sell", new=execute_sell_mock), \
         patch("src.engine.scheduler.write_log", new=AsyncMock()):
        await sched._force_clear_main_only()

    # VB 005930 에 대해 FORCE_CLEAR 매도 호출이 1회 이상 발생해야 함
    sell_calls = [
        c for c in execute_sell_mock.await_args_list
        if c.args[0] == "005930" and c.args[2] == "volatility_breakout"
    ]
    assert len(sell_calls) >= 1, (
        "_force_clear_main_only 가 VB 005930 을 청산 대상으로 호출하지 않음. "
        "DEFAULT_TRADABLE_BOARDS 에 post_nxt 가 남아 있어 POST_NXT 활성 분기로 "
        "스킵되었을 가능성 — 15:20 일괄매도 정책 회귀."
    )
    # FORCE_CLEAR 신호인지 확인
    assert sell_calls[0].args[1] == Signal.FORCE_CLEAR
