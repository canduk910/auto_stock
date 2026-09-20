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
from src.models.trade import TradeStatus, TradeType

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

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
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

    async def _fake(self, strategy_id, *, ticker=None, side="sell"):  # noqa: ARG001
        return "KRX"

    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._strategy_exchange_async",
        _fake,
    )
    return _fake


@pytest.fixture
def mock_get_balance(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """사이클 55 R-1 Q3 reconciliation — get_balance() 1회 호출 의존성 분리.

    insufficient_quantity 거부 분기 (`order_engine.py:807`) 가 lazy import 로
    `src.api.balance.get_balance` 호출 → 실제 KIS REST 호출되면 .env 미설정 CI
    환경에서 무한 hang (사이클 59 cycle hotfix). mock 누락 시 backend-test job
    이 GitHub Actions 6시간 timeout 으로 cancel.
    """
    mock = AsyncMock(return_value=([], None))
    import src.api.balance as _balance
    monkeypatch.setattr(_balance, "get_balance", mock)
    return mock


def _success_result(order_no: str) -> OrderResult:
    return OrderResult(order_no=order_no, order_time="090022", krx_org_no="")


def _market_disallow_error() -> KisApiError:
    """2026-05-11 계양전기 매도 거부 원문 (APBK1943)."""
    return KisApiError(
        rt_cd="1",
        msg_cd="APBK1943",
        msg1="시장가호가불가로 주문이 불가합니다.",
    )


def _aftermarket_disallow_error() -> KisApiError:
    """Phase H1 — 2026-05-11 NXT 애프터 매도 거부 원문 (APBK3013)."""
    return KisApiError(
        rt_cd="1",
        msg_cd="APBK3013",
        msg1="[애프터마켓]지정가 및 최유리/최우선지정가 주문만 가능합니다.",
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
    mock_get_balance: AsyncMock,
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


# ---------------------------------------------------------------------------
# 시나리오 H1 — 시장가 매도 + APBK3013 거부 (NXT 애프터) → step_down(5) 폴백 자동 작동
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_sell_when_apbk3013_aftermarket_then_limit_fallback_at_5_ticks_down(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
):
    """2026-05-11 NXT 애프터 16:05~16:28 APBK3013 매도 거부 → APBK1943과 동일 폴백.

    H1 키워드 확장 회귀 — `_MARKET_ORDER_DISALLOWED_KEYWORDS`에 추가된
    "최유리/최우선지정가 주문만" / "지정가 및 최유리"가 APBK3013 msg1을 매칭하여
    `is_market_order_disallowed=True` → `execute_sell` 폴백 분기 자동 진입.
    """
    from src.engine import scanner as _scanner

    _scanner.ticker_prices["012200"] = {"current_price": 4500}
    current_price = 4500
    expected_fallback = step_down(current_price, steps=5)

    mock_place_order.side_effect = [
        _aftermarket_disallow_error(),
        _success_result("ORDER-H1-1"),
    ]

    try:
        await engine.execute_sell("012200", Signal.STOP_LOSS, "momentum")
    finally:
        _scanner.ticker_prices.pop("012200", None)

    # APBK1943 케이스와 동일 — place_order 2회 (시장가 → 지정가 폴백)
    assert mock_place_order.await_count == 2

    second_call = mock_place_order.await_args_list[1]
    assert second_call.kwargs["side"] == OrderSide.SELL
    assert second_call.kwargs["price"] == expected_fallback
    assert second_call.kwargs.get("order_division") == OrderDivision.LIMIT
    assert second_call.kwargs.get("quantity") == 10

    # 매핑 동기 등록 — 시장가 경로와 동일 안전 규약
    assert engine._order_qty.get("ORDER-H1-1") == 10
    assert engine._order_strategy.get("ORDER-H1-1") == "momentum"
    assert engine._order_ticker.get("ORDER-H1-1") == "012200"

    # positions 보존 (체결 전)
    assert "012200" in strategy.state.positions


# ---------------------------------------------------------------------------
# 시나리오 I — cycle327 ⓑ 폴백 축: 접수 후 INSERT 가 실패해도 예외가 새지 않는다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_sell_when_fallback_insert_fails_then_no_raise_and_marked(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    caplog,
):
    """🔴 폴백 주문이 **나간 뒤** INSERT 가 일반 예외로 실패해도 예외가 밖으로 새지 않는다.

    cycle327 ⓑ 의 **폴백 축**이다. 주 경로는
    `test_cycle327_sell_fill_during_insert.py::test_sell_does_not_refire_on_generic_insert_error`
    가 덮지만, 폴백 경로의 같은 경계(`order_engine.py` 의 `path=fallback` 분기)는
    커버리지 0 이었다 — **바로 앞 커밋이 넣은 코드에 회귀가 없던 자리**다.

    주 경로와 실패 모양이 다르다. 폴백 블록은 `except KisApiError` **안**에 있어서,
    경계가 없으면 예외가 그 핸들러를 뚫고 재시도 루프와 `execute_sell` 을 통째로
    빠져나가 **호출자(`risk.on_tick`)로 전파**된다. 재발사가 아니라 **틱 처리 중단**이
    피해다 — 그 코루틴이 죽으면 그 순간의 다른 종목 손절 평가도 함께 사라진다.

    돌연변이 = `except Exception:` 블록을 지우면 이 `await` 가 `TimeoutError` 로 터진다.
    """
    import logging

    from src.engine import scanner as _scanner

    _scanner.ticker_prices["012200"] = {"current_price": 4500}

    # 1차 시장가 거부 → 2차 지정가 폴백은 **접수 성공**. 그 뒤 INSERT 만 실패시킨다.
    mock_place_order.side_effect = [
        _market_disallow_error(),
        _success_result("ORDER-I-1"),
    ]
    mock_insert_trade.side_effect = TimeoutError("DB 응답 없음 — 폴백 주문은 이미 나갔다")

    caplog.set_level(logging.ERROR, logger="src.engine.order_engine")
    try:
        await engine.execute_sell("012200", Signal.STOP_LOSS, "momentum")
    finally:
        _scanner.ticker_prices.pop("012200", None)

    # 폴백까지 정확히 2회 — INSERT 실패가 추가 발사를 부르지 않는다.
    assert mock_place_order.await_count == 2, (
        f"발사 {mock_place_order.await_count}회 — 접수 후 실패가 재발사를 불렀다"
    )

    # 조용한 흡수 금지 — 마커가 유일한 관측 채널이다.
    hits = [
        r.getMessage() for r in caplog.records
        if "[sell_post_send_error]" in r.getMessage() and "path=fallback" in r.getMessage()
    ]
    assert hits, "예외는 막았지만 아무 말도 남기지 않았다 — 조용한 흡수는 은폐다"
    assert "ORDER-I-1" in hits[0]

    # 포지션은 보존 — 주문은 접수됐고 체결통보가 정리한다.
    assert "012200" in strategy.state.positions


# ---------------------------------------------------------------------------
# 시나리오 J — cycle328: 호출부가 헬퍼로 넘기는 **값**을 봉인한다
# ---------------------------------------------------------------------------
#
# 관문 리뷰(2026-09-20)에서 tester·tdd-engineer 가 **독립적으로 같은 구멍**을 찾았다.
# 매도 PENDING 행의 `price`/`quantity` 를 단언하는 테스트가 리포 전체에 **없었다**
# (`record.price` 단언은 매수 축 `test_cycle291_pre_nxt_gtp.py:663` 이 유일).
# 위 시나리오 A 의 주석은 "폴백 주문번호 + 폴백 가격" 이라 적어 놓고 실제로는
# `record.order_no` 하나만 본다 — **주석을 단언으로 읽은 설계 카드가 틀렸다.**
#
# 실측된 돌연변이 3종이 전부 **행위 테스트 0건**으로 통과했다:
#   M5  폴백 `record_price=fallback_price` → `pos.buy_price`
#   M12 `_SELL_PENDING_SKIP_PATH_LABEL` 의 `"폴백 "` → `""`
#   M13 폴백 `quantity=pos.quantity` → `1`
#
# 이 구멍은 cycle328 리팩토링이 만든 것이 아니라 **원래 있던 것**이다. 다만 값이
# 이름 있는 인자 네 개로 헬퍼에 넘어가면서 **실수로 뒤바꾸기가 쉬워졌으므로**
# 그 단계의 산출물로 닫는다.
#
# 🔴 판별력의 전제 = 비교하는 두 값이 서로 달라야 한다.
#    `buy_price=4500` · `quantity=10` · `fallback_price=step_down(4500,5)=4475`
#    셋이 전부 다르므로 어느 쌍을 맞바꿔도 단언이 깨진다.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sell_pending_record_carries_buy_price_and_position_qty(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
):
    """🔴 **주 경로** PENDING 행 = `price=pos.buy_price` · `quantity=pos.quantity`.

    맞바꿈(M5 계열)을 잡는 유일한 축이다. `price` 4500 ↔ `quantity` 10 은
    자릿수가 달라 어느 방향으로 바꿔도 붉어진다.
    """
    mock_place_order.side_effect = [_success_result("ORDER-J-1")]

    await engine.execute_sell("012200", Signal.STOP_LOSS, "momentum")

    assert mock_insert_trade.await_count == 1
    record = mock_insert_trade.await_args.args[0]
    assert record.order_no == "ORDER-J-1"
    assert record.ticker == "012200"
    assert record.trade_type == TradeType.SELL
    assert record.status == TradeStatus.PENDING
    assert record.strategy == "momentum"
    assert record.price == 4500, (
        f"PENDING 가격 {record.price} (기대 4500 = pos.buy_price). "
        "가격·수량 인자가 뒤바뀌었을 수 있다"
    )
    assert record.quantity == 10, (
        f"PENDING 수량 {record.quantity} (기대 10 = pos.quantity)"
    )
    assert record.profit_loss == 0


@pytest.mark.asyncio
async def test_sell_fallback_pending_record_carries_fallback_price_not_buy_price(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
):
    """🔴 **폴백 경로** PENDING 행 = `price=fallback_price`(≠ `pos.buy_price`).

    `step_down(4500, 5) = 4475` 이므로 `pos.buy_price`(4500)와 다르다 —
    그 차이가 M5 를 판별하는 전부다. 위 시나리오 A 는 이 값을 보지 않는다.
    """
    from src.engine import scanner as _scanner

    _scanner.ticker_prices["012200"] = {"current_price": 4500}
    expected_fallback = step_down(4500, steps=5)

    # 🔴 전제 봉인 — 리터럴이 아니라 **실제 포지션 값**과 대조한다.
    # 누가 현재가를 바꾸거나 호가단위 구간 경계를 건드려 둘이 우연히 같아지면
    # 아래 price 단언이 **초록인 채로 아무것도 재지 않게** 된다.
    pos_buy_price = strategy.state.positions["012200"].buy_price
    pos_qty = strategy.state.positions["012200"].quantity
    assert expected_fallback != pos_buy_price, (
        f"픽스처 전제 붕괴 — 폴백가({expected_fallback})와 매수가({pos_buy_price})가 같아지면 "
        "아래 price 단언이 공허하다"
    )
    assert expected_fallback != pos_qty, "폴백가와 수량이 같으면 맞바꿈을 판별할 수 없다"

    mock_place_order.side_effect = [
        _market_disallow_error(),
        _success_result("ORDER-J-2"),
    ]
    try:
        await engine.execute_sell("012200", Signal.STOP_LOSS, "momentum")
    finally:
        _scanner.ticker_prices.pop("012200", None)

    assert mock_insert_trade.await_count == 1
    record = mock_insert_trade.await_args.args[0]
    assert record.price == expected_fallback, (
        f"폴백 PENDING 가격 {record.price} (기대 {expected_fallback}). "
        f"`pos.buy_price`({pos_buy_price}) 가 들어갔다면 폴백가가 기록에서 사라진다"
    )
    assert record.quantity == pos_qty, (
        f"폴백 PENDING 수량 {record.quantity} (기대 {pos_qty} = pos.quantity)"
    )
    # 🔴 나머지 4필드도 주 경로와 **대칭**으로 단언한다.
    # 이 결함이 실제로 나는 방식은 「주 경로 블록을 폴백에 복붙하고 두 줄만 고치는 것」이라,
    # 폴백 단언이 둘뿐이면 고치지 않은 나머지가 무방비다. 비대칭이 이 결함의 뿌리였다.
    assert record.order_no == "ORDER-J-2"
    assert record.ticker == "012200"
    assert record.trade_type == TradeType.SELL
    assert record.status == TradeStatus.PENDING
    assert record.strategy == "momentum"
    assert record.profit_loss == 0


@pytest.mark.asyncio
async def test_sell_pending_skip_warning_distinguishes_market_and_fallback(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    caplog,
):
    """🔴 선행 체결통보 WARNING 이 두 경로를 **문구로 구분**한다.

    이 로그에는 `path=` 필드가 없어 **문구가 유일한 구분자**다. 경로 수식어
    표(`_SELL_PENDING_SKIP_PATH_LABEL`)의 값이 뭉개지면(M12: `"폴백 "` → `""`)
    운영자가 로그만 보고 주 경로 거부인지 폴백 거부인지 가릴 수 없게 된다.
    그런데 그 돌연변이를 잡는 행위 테스트가 **0건**이었다.
    """
    import logging

    from src.engine import scanner as _scanner

    caplog.set_level(logging.WARNING, logger="src.engine.order_engine")

    # ── 주 경로: 체결통보가 응답보다 먼저 도착한 상태를 만든다
    async def _main_then_completed(ticker, side, quantity, price=0, **kwargs):
        engine._completed_orders.add("ORDER-J-3")
        return _success_result("ORDER-J-3")

    # 🔴 CI 루트 로거가 DEBUG 라 `caplog.records` 에 무관한 행이 섞인다.
    # 레벨 ≥ WARNING **과** `"매도 "` 접두로 한정한다(이 메시지엔 `[marker]` 접두가 없다).
    def _skip_warnings() -> list[str]:
        return [
            r.getMessage() for r in caplog.records
            if r.levelno >= logging.WARNING
            and r.getMessage().startswith("매도 ")
            and "PENDING INSERT 생략" in r.getMessage()
        ]

    mock_place_order.side_effect = _main_then_completed
    await engine.execute_sell("012200", Signal.STOP_LOSS, "momentum")

    main_msgs = _skip_warnings()
    assert len(main_msgs) == 1, f"주 경로 생략 WARNING 이 {len(main_msgs)}행: {main_msgs}"
    assert "폴백" not in main_msgs[0], (
        f"주 경로인데 '폴백' 이 붙었다: {main_msgs[0]}"
    )

    # ── 폴백 경로: 시장가 거부 후 폴백 주문의 체결통보가 선행한 상태
    caplog.clear()
    engine._selling.discard("012200")
    _scanner.ticker_prices["012200"] = {"current_price": 4500}

    calls = {"n": 0}

    async def _fallback_then_completed(ticker, side, quantity, price=0, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _market_disallow_error()
        engine._completed_orders.add("ORDER-J-4")
        return _success_result("ORDER-J-4")

    mock_place_order.side_effect = _fallback_then_completed
    try:
        await engine.execute_sell("012200", Signal.STOP_LOSS, "momentum")
    finally:
        _scanner.ticker_prices.pop("012200", None)

    fb_msgs = _skip_warnings()
    assert len(fb_msgs) == 1, f"폴백 생략 WARNING 이 {len(fb_msgs)}행: {fb_msgs}"
    assert "폴백" in fb_msgs[0], (
        f"폴백 경로인데 '폴백' 수식어가 없다: {fb_msgs[0]}. "
        "이 로그에는 path= 필드가 없어 문구가 유일한 구분자다"
    )
