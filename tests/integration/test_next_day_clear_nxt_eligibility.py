"""P1(B) Red — NXT 거래가능 여부에 따른 익일 청산 시점 분기.

배경 (운영 회고 2026-05-09):
- 08:00 NXT 프리에 모멘텀 익일 청산이 KRX 단독 종목(012200 KEC) 시장가 매도를 시도 →
  KIS APBK0918 "장운영시간이 아닙니다" → 좀비 포지션 발생.
- KIS OpenAPI 에는 종목별 NXT 거래가능 여부를 조회하는 명시적 TR 이 확인되지 않음 →
  대안: WebSocket 시가 수신 여부로 NXT 거래 가능성을 추론한다.

명세 (옵션 B 변형):
- (a) NXT 시가 수신됨 (`ticker_prices[ticker]["open_price"] > 0`) → 08:00 NXT 프리에서
      **지정가**(직전가 -1호가, KRX 호가단위 적용) 매도 (`ORD_DVSN=00`, exchange="NXT")
- (b) NXT 시가 미수신 → 청산 보류 (포지션 보존, _selling 비활성).
      `_pending_next_day_clear` 에 등록되고, `_confirm_breakout_open_prices(board="main")`
      이후 (09:00 KRX 시가 확정 후) 재트리거되어 정규 시장가 청산을 수행한다.

요구 행위:
1. NXT 시가 수신 + 갭률 < threshold → execute_sell 호출 + 가격이 step_down(현재가, 1) 지정가
2. NXT 시가 수신 + 갭률 ≥ threshold → 트레일링 모드 (호출 없음, 기존 동작 보존)
3. NXT 시가 미수신 → execute_sell 호출 *없음* + `_pending_next_day_clear` set 에 등록
4. high_since_buy 폴백 + 갭률 0.0% 즉시 청산은 제거 (안전성)
5. _pending_next_day_clear 종목은 KRX 메인 시가 확정 시 *시장가* 청산 (정규장은 시장가 OK)
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from src.engine.strategy_base import Position, Signal

pytestmark = pytest.mark.integration


def _seed_next_day_pos(strategy, ticker, buy_price=15000, qty=6, high=None):
    pos = Position(
        ticker=ticker,
        buy_price=buy_price,
        quantity=qty,
        order_no="ORIG-NEXT",
        strategy_id=strategy.strategy_id,
        buy_date=date.today() - timedelta(days=1),
        high_since_buy=high if high is not None else buy_price,
    )
    strategy.state.positions[ticker] = pos
    return pos


# ---------------------------------------------------------------------------
# 1) NXT 시가 수신됨 → 08:00 지정가 매도
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_next_day_clear_when_nxt_open_received_and_gap_below_then_limit_order(
    scheduler_env,
):
    """NXT 시가 수신 + 갭률 < threshold → 직전가 -1호가 지정가 매도."""
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "012200", buy_price=15000)

    # NXT 시가 15050 = 갭 +0.33% (< 10% threshold)
    from src.engine import scanner
    scanner.ticker_prices["012200"] = {
        "open_price": 15050, "current_price": 15050,
    }

    await sched._execute_next_day_clear()

    sells = scheduler_env.calls.execute_sell
    assert len(sells) == 1, "갭률 미만 시 즉시 청산"
    assert sells[0]["ticker"] == "012200"
    assert sells[0]["signal"] == Signal.NEXT_DAY_CLEAR
    # 지정가 정보가 전달되었는지 — fake_execute_sell 시그니처 확장 필요
    assert sells[0].get("limit_price", 0) == 15040, (
        "직전가 15050(10원 단위) -1호가 = 15040 이 지정가로 전달되어야 함"
    )


# ---------------------------------------------------------------------------
# 2) NXT 시가 수신됨 + 갭률 ≥ threshold → 트레일링 (회귀 가드)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_next_day_clear_when_nxt_open_received_and_gap_above_then_trailing(
    scheduler_env,
):
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "005930", buy_price=80000)

    from src.engine import scanner
    scanner.ticker_prices["005930"] = {"open_price": 89600}  # +12% > 10%

    await sched._execute_next_day_clear()

    assert scheduler_env.calls.execute_sell == []
    assert "005930" in momentum.state.positions


# ---------------------------------------------------------------------------
# 3) NXT 시가 미수신 → 청산 보류 + _pending_next_day_clear 등록
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_next_day_clear_when_nxt_open_missing_then_defers_to_main(scheduler_env):
    """NXT 시가 미수신 → 08:00 청산 *안 함*, _pending_next_day_clear 등록."""
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "012200", buy_price=15000, high=15500)

    # ticker_prices 비어있음 = NXT 시가 미수신
    from src.engine import scanner
    scanner.ticker_prices.clear()

    # _resolve_open_price 폴백도 0 반환 (NXT 거래 불가 종목)
    async def fake_resolve(ticker, max_wait_s=2.0):
        return 0

    sched._resolve_open_price = fake_resolve

    await sched._execute_next_day_clear()

    # 08:00 시점에는 청산 X
    assert scheduler_env.calls.execute_sell == [], (
        "NXT 시가 미수신 + NXT 거래 불가 종목으로 판단 → 08:00 청산 보류"
    )
    # 포지션 유지
    assert "012200" in momentum.state.positions
    # _pending_next_day_clear 에 등록 (KRX 시가 확정 후 청산용)
    assert hasattr(sched, "_pending_next_day_clear"), (
        "scheduler 에 _pending_next_day_clear set 이 존재해야 함"
    )
    assert ("012200", "momentum") in sched._pending_next_day_clear


# ---------------------------------------------------------------------------
# 4) high_since_buy 폴백 + 갭률 0% 즉시 청산은 제거 (안전성)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_next_day_clear_no_longer_uses_high_since_buy_fallback(scheduler_env):
    """시가 미수신 시 high_since_buy 사용 + 갭률 0% 즉시 청산 경로 제거 검증.

    종전 동작: open_price=high_since_buy → gap_rate=0% < 10% → 즉시 청산 (위험!)
    신규 동작: 시가 미수신이면 청산 보류 (위 케이스 #3 과 동일)
    """
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "012200", buy_price=15000, high=15500)

    from src.engine import scanner
    scanner.ticker_prices.clear()

    async def fake_resolve(ticker, max_wait_s=2.0):
        return 0

    sched._resolve_open_price = fake_resolve

    await sched._execute_next_day_clear()

    # 갭률 0% 즉시 청산 금지
    assert scheduler_env.calls.execute_sell == []


# ---------------------------------------------------------------------------
# 5) KRX 시가 확정 후 _pending_next_day_clear 재트리거 (시장가)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pending_next_day_clear_when_main_open_confirmed_then_market_order(
    scheduler_env,
):
    """`_confirm_breakout_open_prices(board="main")` 직후 pending 종목 시장가 청산."""
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "012200", buy_price=15000)

    # _pending_next_day_clear 시드 (Step #3 이후 상태 시뮬레이트)
    sched._pending_next_day_clear = {("012200", "momentum")}

    # KRX 시가 확정 시뮬
    from src.engine import scanner
    scanner.ticker_prices["012200"] = {"open_price": 14800, "current_price": 14800}

    # `_drain_pending_next_day_clear` 라는 메서드를 호출하면 시장가 청산이 트리거되어야 함
    assert hasattr(sched, "_drain_pending_next_day_clear"), (
        "_drain_pending_next_day_clear 메서드가 존재해야 함"
    )
    await sched._drain_pending_next_day_clear()

    sells = scheduler_env.calls.execute_sell
    assert len(sells) == 1
    assert sells[0]["ticker"] == "012200"
    assert sells[0]["strategy_id"] == "momentum"
    assert sells[0]["signal"] == Signal.NEXT_DAY_CLEAR
    # KRX 정규장은 시장가 — limit_price 없음(0)
    assert sells[0].get("limit_price", 0) == 0
    # pending set 에서 제거
    assert ("012200", "momentum") not in sched._pending_next_day_clear
