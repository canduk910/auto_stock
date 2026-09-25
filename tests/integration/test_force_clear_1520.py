"""15:20 KRX 메인 강제 청산 — `_force_clear_main_only` 정책 검증.

핵심 행위:
- 대상: VB / LTV 중 enabled 전략
- 각 전략의 `tradable_boards` 에 `POST_NXT` 가 포함되어 있으면 청산 보류 (NXT 애프터까지 유지)
- POST_NXT 미활성 전략은 `check_force_clear()` 결과 ticker 들에 대해 `execute_sell(FORCE_CLEAR)` 호출
- momentum / donchian_swing 은 이 함수의 대상이 아님 (각각 익일청산 / 추세추종)
"""

from __future__ import annotations

import pytest
from freezegun import freeze_time

from src.engine.strategy_base import Position, Signal

pytestmark = pytest.mark.integration


# 2026-05-15 hot fix — `_force_clear_main_only` 가 KRX 메인 마감(15:30) 이후 호출 시
# skip 하도록 시간 가드 추가. 본 모듈 모든 테스트는 15:20 정상 호출 시점을 검증하므로
# autouse fixture 로 시각을 15:20:30 으로 고정.
@pytest.fixture(autouse=True)
def _freeze_at_force_clear_time():
    with freeze_time("2026-05-15 15:20:30"):
        yield


def _seed_pos(strategy, ticker, buy_price=80000, qty=10):
    pos = Position(
        ticker=ticker, buy_price=buy_price, quantity=qty,
        order_no="ORIG-1", strategy_id=strategy.strategy_id,
    )
    strategy.state.positions[ticker] = pos
    return pos


@pytest.mark.asyncio
async def test_force_clear_when_post_nxt_active_then_calls_check_force_clear(scheduler_env):
    """사이클 142 의미 전환 (사이클 66 K-2 패턴 답습) — 결함 #1 시정 영역 영구 영속.

    *사이클 142 이전 (결함 #1 영역)*: POST_NXT 활성 시 `_force_clear_main_only` 가
    `check_force_clear()` 호출 자체 안 함 → 모든 종목 보류 (사이클 38 명세 위반).

    *사이클 142 시정 이후*: POST_NXT 활성 무관 `check_force_clear()` 호출 영속.
    - VB는 `check_force_clear()` 본체가 전량 청산 영속 (POST_NXT 미포함, 사이클 26 영속)
    - LTV는 `check_force_clear()` 본체가 `_limit_up_reached` 영역 영구 영속 상한가 모드 종목 제외 영속

    본 테스트 시정: VB 에 강제 POST_NXT 추가 (실 운영 미적용) → 시정 후 청산 발화 영속.
    """
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["tradable_boards"] = ["pre_nxt", "main", "post_nxt"]
    _seed_pos(vb, "005930")

    await sched._force_clear_main_only()

    # 사이클 142 시정: POST_NXT 활성 무관 check_force_clear() 호출 영속.
    # VB.check_force_clear() = 전량 청산 (POST_NXT 미포함, 사이클 26 영속) → 청산 발화
    sells = scheduler_env.calls.execute_sell
    assert len(sells) == 1, (
        f"사이클 142 시정 위반: POST_NXT 활성 시 check_force_clear() 호출 + 청산 영속 의무. "
        f"got sells={sells}"
    )
    assert sells[0]["ticker"] == "005930"
    assert sells[0]["signal"] == Signal.FORCE_CLEAR
    assert "005930" not in vb.state.positions  # 청산됨 영속


@pytest.mark.asyncio
async def test_force_clear_when_post_nxt_inactive_then_clears_main_holdings(scheduler_env):
    """VB 의 tradable_boards 에 post_nxt 없음 → 강제청산 실행."""
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["tradable_boards"] = ["main"]  # POST_NXT 미포함
    _seed_pos(vb, "005930")

    await sched._force_clear_main_only()

    # FORCE_CLEAR 신호로 매도 호출
    sells = scheduler_env.calls.execute_sell
    assert len(sells) == 1
    assert sells[0]["ticker"] == "005930"
    assert sells[0]["signal"] == Signal.FORCE_CLEAR
    assert sells[0]["strategy_id"] == "volatility_breakout"


@pytest.mark.asyncio
async def test_force_clear_skips_disabled_strategies(scheduler_env):
    sched = scheduler_env.scheduler
    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = False  # 비활성
    vb.config.params["tradable_boards"] = ["main"]
    _seed_pos(vb, "005930")

    await sched._force_clear_main_only()
    assert scheduler_env.calls.execute_sell == []


@pytest.mark.asyncio
async def test_force_clear_handles_multiple_strategies_independently(scheduler_env):
    """사이클 142 의미 전환 — VB / LTV 모두 청산 (POST_NXT 무관, 결함 #1 시정).

    *사이클 142 이전*: VB POST_NXT 활성 → 보류 (사이클 38 명세 위반).
    *사이클 142 시정 이후*: POST_NXT 무관 두 전략 모두 청산 영속.

    LTV의 `check_force_clear()` 본체는 `_limit_up_reached` 미등록 종목 청산 영역 영구 영속.
    상한가 모드 종목 보존은 LTV strategy 본체에서 영속 정합 (G-142-SAFETY-1 영속).
    """
    sched = scheduler_env.scheduler

    vb = sched.registry.get("volatility_breakout")
    vb.config.enabled = True
    vb.config.params["tradable_boards"] = ["pre_nxt", "main", "post_nxt"]
    _seed_pos(vb, "005930", buy_price=80000)

    ltv = sched.registry.get("long_tail_volatility")
    ltv.config.enabled = True
    ltv.config.params["tradable_boards"] = ["main"]
    _seed_pos(ltv, "000660", buy_price=100000)

    await sched._force_clear_main_only()

    # 사이클 142 시정: VB + LTV 모두 청산 영역 영구 영속.
    sells = scheduler_env.calls.execute_sell
    tickers = {c["ticker"]: c["strategy_id"] for c in sells}
    assert tickers == {
        "005930": "volatility_breakout",  # 사이클 142 시정 = VB도 청산 영속
        "000660": "long_tail_volatility",
    }, f"got sells={sells}"
    assert "005930" not in vb.state.positions  # 사이클 142 시정 = 청산됨
    assert "000660" not in ltv.state.positions  # 청산됨


@pytest.mark.asyncio
async def test_force_clear_does_not_target_momentum_or_donchian(scheduler_env):
    """momentum / donchian_swing 보유 종목은 이 함수의 대상 아님."""
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_pos(momentum, "005930")

    donchian = sched.registry.get("donchian_swing")
    donchian.config.enabled = True
    _seed_pos(donchian, "000660")

    await sched._force_clear_main_only()

    # momentum / donchian 은 _force_clear_main_only 의 대상 strategies 에 없음
    assert scheduler_env.calls.execute_sell == []


# ---------------------------------------------------------------------------
# cycle352 — I1/I2: LTV 15:20 상한가 유지 확인 (`limit_up_close_hold_mode`)
#
# 정본 = `_workspace/domain_consult/cycle352_ltv_limit_up_trailing.md` §5.4.
# I3(=`check_force_clear` 자체 예외 시 `_force_clear_main_only` 는 try 없이 호출한다는
# 현행 결함 재현)은 이번에 고치지 않는다(`scheduler.py` 무접촉) — 전략 쪽에서
# `T11`(단위 테스트)이 그 경로를 이미 막는다는 사실만 여기 문서로 남긴다.
# ---------------------------------------------------------------------------
async def test_force_clear_ltv_limit_up_mode_exits_when_below_threshold_at_1520(
    scheduler_env,
):
    """I1 — 상한가 모드 당일 보유 + 15:20 가격이 임계 미만 → FORCE_CLEAR 매도 1회."""
    from src.engine import scanner

    sched = scheduler_env.scheduler
    ltv = sched.registry.get("long_tail_volatility")
    ltv.config.enabled = True
    ltv.config.params["tradable_boards"] = ["main"]
    _seed_pos(ltv, "005930", buy_price=80000)
    ltv._limit_up_reached.add("005930")

    # ticker_prev_close["005930"] = 70000 (scheduler_env 고정) → +24% ≈ 86800
    scanner.ticker_prices["005930"] = {"current_price": 86800}

    await sched._force_clear_main_only()

    sells = scheduler_env.calls.execute_sell
    assert len(sells) == 1, f"got sells={sells}"
    assert sells[0]["ticker"] == "005930"
    assert sells[0]["signal"] == Signal.FORCE_CLEAR
    assert sells[0]["strategy_id"] == "long_tail_volatility"
    assert "005930" not in ltv.state.positions


async def test_force_clear_ltv_limit_up_mode_holds_when_at_threshold_at_1520(
    scheduler_env,
):
    """I2 — 같은 조건, 15:20 가격이 여전히 임계(29%) 이상 → 매도 없음(익일 보유 보존)."""
    from src.engine import scanner

    sched = scheduler_env.scheduler
    ltv = sched.registry.get("long_tail_volatility")
    ltv.config.enabled = True
    ltv.config.params["tradable_boards"] = ["main"]
    _seed_pos(ltv, "005930", buy_price=80000)
    ltv._limit_up_reached.add("005930")

    # +29.9% ≈ 90930 (limit_up_threshold=29.0 이상 → hold)
    scanner.ticker_prices["005930"] = {"current_price": 90930}

    await sched._force_clear_main_only()

    assert scheduler_env.calls.execute_sell == []
    assert "005930" in ltv.state.positions
