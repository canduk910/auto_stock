"""Phase C Red — OrderEngine.execute_sell 시장가 거부 → 지정가 5호가 폴백.

2026-05-11 계양전기(012200) 09:00:21 매도 ×3 실패 (APBK1943 "시장가호가불가") 회귀 대응.
사용자 컨펌: 매수 패턴과 대칭 — **지정가 1회 자동 폴백, 호가 차이 5단계 step_down** (매도는 호가 깊이로 내려 체결률 확보).

검증 시나리오:

A. 시장가 매도 + APBK1943 거부 → 폴백 1회 시도
   - 폴백 가격: `step_down(current_price, steps=5)` (매수의 step_up 대칭)
   - 매핑 동기 등록(`_order_qty`/`_order_strategy`/`_order_ticker`) + `_completed_orders` race 가드
   - `insert_trade(PENDING, price=fallback_price)`

B. 시장가 매도 + 폴백도 거부 → 재시도 중단, 메모리/DB positions **보존**
   - 다음 사이클 자연 재트리거 가능 (NXT 거부와 동일 패턴; cooldown 등록 안 함 — 청산 의무)

C. **지정가 매도(`limit_price>0`) + APBK1943 거부 → 폴백 안 함** (이미 지정가)

D. 시장가 매도 + 다른 거부:
   D1. `is_insufficient_quantity` True → 폴백 안 함, 즉시 break + positions 삭제 (기존 동작)
   D2. `is_market_closed_rejection` True → 폴백 안 함, positions 보존 (기존 동작)

E. `is_market_order_disallowed`("시장가호가불가" 키워드) 매칭 — 헬퍼 단위 보장
   (test_insufficient_classification.py 에서 별도 검증, 여기서는 매도 폴백 분기 진입 검증)

F. 매핑 동기 등록 + `_completed_orders` race 가드가 매수 폴백과 동일 순서
   — 시장가 즉시체결 race 시 동일 안전성

매도 폴백 측 추가 불변식:
- 폴백 호출 인자: `side=SELL`, `order_division=LIMIT`, `price=step_down(current_price,5)`,
  `exchange=원래 라우팅(시장가 측 _strategy_exchange_async 결과)`, `quantity=pos.quantity`
- 폴백 호출은 **1회만** (재시도 루프 안에서 거부 시 break → 루프 밖 1회 폴백)
- 폴백 실패해도 cooldown 등록 안 함 (매수는 LOW_FUNDS_COOLDOWN; 매도는 청산 의무 → 자연 재트리거)

테스트 더블:
- `place_order` AsyncMock — 시나리오별 side_effect
- `insert_trade` AsyncMock
- `delete_position` AsyncMock (insufficient_quantity 분기에서만 호출)
- 더미 전략 — positions 사전 등록
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import (
    Position,
    Signal,
    StrategyBase,
    StrategyConfig,
)
from src.engine.strategy_registry import StrategyRegistry
from src.engine.util.tick_size import step_down
from src.models.order import OrderDivision, OrderResult, OrderSide

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 더미 전략 — 매도 단위 테스트용
# ---------------------------------------------------------------------------
class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id: str = "momentum") -> None:
        super().__init__(
            StrategyConfig(
                strategy_id=strategy_id,
                name=f"{strategy_id}-dummy",
                enabled=True,
                weight=1.0,
                params={"exchange": "KRX"},
            )
        )
        self.state.total_investment = 10_000_000

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int) -> int:
        return 0


@pytest.fixture
def registry() -> StrategyRegistry:
    reg = StrategyRegistry()
    strat = _DummyStrategy(strategy_id="momentum")
    # 사전 포지션 — 매도 대상
    strat.state.positions["012200"] = Position(
        ticker="012200",
        buy_price=4500,
        quantity=10,
        order_no="ORDER-PRE",
        strategy_id="momentum",
        buy_date=date.today(),
    )
    reg.register(strat)
    return reg


@pytest.fixture
def strategy(registry: StrategyRegistry) -> StrategyBase:
    return registry.get("momentum")


@pytest.fixture
def engine(registry: StrategyRegistry) -> OrderEngine:
    return OrderEngine(registry)


@pytest.fixture
def mock_insert_trade(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "insert_trade", mock)
    return mock


@pytest.fixture
def mock_place_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "place_order", mock)
    return mock


@pytest.fixture
def mock_delete_position(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """DB positions 삭제 모킹 — insufficient_quantity 분기에서만 호출 검증."""
    mock = AsyncMock(return_value=None)
    import src.db.positions as _positions

    monkeypatch.setattr(_positions, "delete_position", mock)
    return mock


@pytest.fixture
def mock_write_log(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "write_log", mock)
    return mock


@pytest.fixture
def mock_strategy_exchange(monkeypatch: pytest.MonkeyPatch):
    """`_strategy_exchange_async` 가 KRX 를 반환하도록 모킹.

    Phase G stock_master 보강 의존성을 분리해 폴백 분기만 단위 검증.
    """

    async def _fake(self, strategy_id, *, ticker=None):  # noqa: ARG001
        return "KRX"

    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._strategy_exchange_async",
        _fake,
    )
    return _fake


def _success_result(order_no: str) -> OrderResult:
    return OrderResult(order_no=order_no, order_time="090022", krx_org_no="")


def _market_disallow_error() -> KisApiError:
    """2026-05-11 계양전기 매도 거부 원문 (APBK1943)."""
    return KisApiError(
        rt_cd="1",
        msg_cd="APBK1943",
        msg1="시장가호가불가로 주문이 불가합니다.",
    )


# ---------------------------------------------------------------------------
# 시나리오 A — 시장가 매도 + APBK1943 거부 → step_down(5) 지정가 폴백 성공
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_sell_when_market_disallowed_then_limit_fallback_at_5_ticks_down(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
):
    """매도 시장가 APBK1943 거부 → step_down(current_price, 5) 지정가 폴백 1회."""
    # ticker_prices 에 현재가 등록 — 폴백 가격 산출에 사용
    from src.engine import scanner as _scanner

    _scanner.ticker_prices["012200"] = {"current_price": 4500}
    current_price = 4500
    expected_fallback = step_down(current_price, steps=5)

    # 1차 시장가 거부, 2차 지정가 폴백 성공
    mock_place_order.side_effect = [
        _market_disallow_error(),
        _success_result("ORDER-C-1"),
    ]

    try:
        await engine.execute_sell("012200", Signal.STOP_LOSS, "momentum")
    finally:
        _scanner.ticker_prices.pop("012200", None)

    # place_order 정확히 2회 (시장가 → 지정가 폴백) — 재시도 루프는 1회 거부 후 break
    assert mock_place_order.await_count == 2

    first_call = mock_place_order.await_args_list[0]
    assert first_call.kwargs["side"] == OrderSide.SELL
    assert first_call.kwargs["price"] == 0  # 1차 시장가

    second_call = mock_place_order.await_args_list[1]
    assert second_call.kwargs["side"] == OrderSide.SELL
    assert second_call.kwargs["price"] == expected_fallback
    assert second_call.kwargs.get("order_division") == OrderDivision.LIMIT
    assert second_call.kwargs.get("quantity") == 10
    # exchange 는 _strategy_exchange_async 결과(여기서는 "KRX") 그대로 — 폴백이 KRX 강제 안 함
    assert second_call.kwargs.get("exchange") == "KRX"

    # 매핑은 폴백 주문번호로 등록
    assert engine._order_qty.get("ORDER-C-1") == 10
    assert engine._order_strategy.get("ORDER-C-1") == "momentum"
    assert engine._order_ticker.get("ORDER-C-1") == "012200"

    # PENDING INSERT 발생 — 폴백 주문번호 + 폴백 가격(매수 패턴과 대칭; 매도 PENDING price 는 기록용)
    assert mock_insert_trade.await_count == 1
    record = mock_insert_trade.await_args.args[0]
    assert record.order_no == "ORDER-C-1"
    # _selling 은 체결통보에서 해제되므로 폴백 성공 후에도 set 안에 있어도 됨 — 성공 분기는 _selling 보존
    # 다만 핵심은 positions 보존 (체결 전이므로)
    assert "012200" in strategy.state.positions


# ---------------------------------------------------------------------------
# 시나리오 B — 시장가 + 폴백 둘 다 거부 → positions 보존, 다음 사이클 재트리거 가능
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_sell_when_both_market_and_limit_rejected_then_positions_preserved(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_delete_position: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
):
    """폴백도 거부 — 재시도 중단, 메모리/DB positions 보존, cooldown 등록 안 함."""
    from src.engine import scanner as _scanner

    _scanner.ticker_prices["012200"] = {"current_price": 4500}

    market_reject = _market_disallow_error()
    limit_reject = KisApiError(
        rt_cd="1", msg_cd="APBK1943", msg1="시장가호가불가로 주문이 불가합니다.",
    )
    mock_place_order.side_effect = [market_reject, limit_reject]

    try:
        await engine.execute_sell("012200", Signal.STOP_LOSS, "momentum")
    finally:
        _scanner.ticker_prices.pop("012200", None)

    # 2회 호출 후 종결 (시장가 1 + 폴백 1) — 재시도 루프 추가 호출 없음
    assert mock_place_order.await_count == 2

    # positions 보존 (메모리)
    assert "012200" in strategy.state.positions
    # DB positions 삭제 호출 없음 — insufficient_quantity 분기 아니므로
    assert mock_delete_position.await_count == 0

    # _selling 해제 — 다음 사이클 매도 트리거 가능 상태
    assert "012200" not in engine._selling

    # PENDING INSERT 없음 (둘 다 응답 실패)
    assert mock_insert_trade.await_count == 0


# ---------------------------------------------------------------------------
# 시나리오 C — 지정가 매도(limit_price>0) + APBK1943 거부 → 폴백 안 함
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_sell_when_limit_order_rejected_then_no_fallback(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
):
    """지정가 매도(`limit_price>0`)가 APBK1943 거부 시 폴백 *없음* — 이미 지정가.

    기존 3회 재시도 동작 유지: 실패 후 마지막 시도까지 호출, positions 보존.
    """
    mock_place_order.side_effect = [_market_disallow_error()] * 3

    await engine.execute_sell(
        "012200", Signal.NEXT_DAY_CLEAR, "momentum", limit_price=4495,
    )

    # 폴백 분기 진입 없음 — 정확히 SELL_MAX_RETRIES(3) 회
    assert mock_place_order.await_count == 3

    # 모든 호출이 지정가 그대로 (price=4495)
    for call in mock_place_order.await_args_list:
        assert call.kwargs.get("order_division") == OrderDivision.LIMIT
        assert call.kwargs.get("price") == 4495

    # positions 보존
    assert "012200" in strategy.state.positions


# ---------------------------------------------------------------------------
# 시나리오 D1 — 시장가 + 보유부족 거부 → 폴백 안 함, positions 삭제 (기존 동작)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_sell_when_insufficient_quantity_then_no_fallback_and_positions_cleared(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_delete_position: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
):
    """`is_insufficient_quantity` True → 폴백 분기 진입 *안 함*, 즉시 break + DB 삭제."""
    qty_reject = KisApiError(
        rt_cd="1", msg_cd="APBK1234", msg1="매도가능수량이 부족합니다.",
    )
    mock_place_order.side_effect = [qty_reject]

    await engine.execute_sell("012200", Signal.STOP_LOSS, "momentum")

    # 정확히 1회 — 폴백 없음, 재시도 없음
    assert mock_place_order.await_count == 1

    # positions 메모리 삭제
    assert "012200" not in strategy.state.positions
    # DB positions 삭제 호출
    assert mock_delete_position.await_count == 1


# ---------------------------------------------------------------------------
# 시나리오 D2 — 시장가 + 장운영시간 외 거부 → 폴백 안 함, positions 보존 (기존 동작)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_sell_when_market_closed_rejected_then_no_fallback_and_positions_preserved(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_delete_position: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
):
    """`is_market_closed_rejection` True → 폴백 분기 진입 *안 함*, positions 보존."""
    closed_reject = KisApiError(
        rt_cd="1", msg_cd="APBK0918", msg1="장운영시간이 아닙니다.",
    )
    mock_place_order.side_effect = [closed_reject]

    await engine.execute_sell("012200", Signal.STOP_LOSS, "momentum")

    # 정확히 1회 — 폴백 없음
    assert mock_place_order.await_count == 1

    # positions 보존
    assert "012200" in strategy.state.positions
    # DB 삭제 호출 없음
    assert mock_delete_position.await_count == 0


# ---------------------------------------------------------------------------
# 시나리오 F — 매핑 동기 등록 + _completed_orders race 가드 (매수 폴백과 동일)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_sell_when_fallback_and_completion_arrives_first_then_no_pending_insert(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
):
    """폴백 응답 *전* 체결통보가 도착해 `_completed_orders` 에 등록된 경우 PENDING INSERT 생략.

    place_order 응답 직후 동기 영역에서 매핑 등록 → `_completed_orders` 체크 → INSERT 생략.
    """
    from src.engine import scanner as _scanner

    _scanner.ticker_prices["012200"] = {"current_price": 4500}

    # 폴백 응답이 도착하기 전 체결통보가 먼저 도착했다고 가정 — _completed_orders 에 사전 등록
    fallback_order_no = "ORDER-F-1"
    engine._completed_orders.add(fallback_order_no)

    mock_place_order.side_effect = [
        _market_disallow_error(),
        _success_result(fallback_order_no),
    ]

    try:
        await engine.execute_sell("012200", Signal.STOP_LOSS, "momentum")
    finally:
        _scanner.ticker_prices.pop("012200", None)

    # 폴백 호출 발생
    assert mock_place_order.await_count == 2

    # 매핑은 등록되어야 함 (동기 영역 — INSERT 생략과 무관)
    assert engine._order_qty.get(fallback_order_no) == 10
    assert engine._order_ticker.get(fallback_order_no) == "012200"

    # _completed_orders 에서 제거됨 (가드 1회 소비)
    assert fallback_order_no not in engine._completed_orders

    # PENDING INSERT 생략 — race 가드 동작
    assert mock_insert_trade.await_count == 0
