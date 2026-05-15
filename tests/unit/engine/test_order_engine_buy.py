"""Phase B Red — OrderEngine.execute_buy 시장가 거부 → 지정가 5호가 폴백.

2026-05-11 계양전기(012200) "시장가매매불가" 거부 → 진입 실패 회귀 대응.
사용자 컨펌: **지정가 1회 자동 폴백, 호가 차이 5단계** (시장가 의도 보존).

검증 시나리오:

A. 시장가 정상           — 회귀 기준선 (place_order 1회, insert_trade PENDING, 매핑 등록)
B. 시장가 거부 → 폴백 성공 — 1차 KisApiError("시장가매매불가") + 2차 지정가 성공
                            → 매핑은 2차 주문번호 기준 등록, insert_trade PENDING(폴백 가격)
C. 시장가 거부 → 폴백 재거부 — 2차도 KisApiError
                            → block_low_funds(ticker, cooldown), pending_buys 회수
D. 자금부족 거부          — 폴백 *없음*, block_buy 호출 (기존 동작 회귀 보존)

테스트 더블:
- `place_order` AsyncMock — 시나리오별 side_effect 로 성공/거부 시퀀스 제어
- `insert_trade` AsyncMock
- `get_buyable` AsyncMock — 충분한 max_buy_quantity 반환
- StrategyBase 더미 — calc_buy_quantity 고정값
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import (
    Signal,
    StrategyBase,
    StrategyConfig,
)
from src.engine.strategy_registry import StrategyRegistry
from src.models.balance import BuyableInfo
from src.models.order import OrderDivision, OrderResult, OrderSide

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 더미 전략 — calc_buy_quantity 고정 + prepare/check_* no-op
# ---------------------------------------------------------------------------
class _DummyStrategy(StrategyBase):
    """매수 단위 테스트용 최소 전략. calc_buy_quantity 만 결정적으로 동작."""

    def __init__(self, strategy_id: str = "momentum", quantity: int = 10) -> None:
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
        self._fixed_qty = quantity

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int) -> int:
        return self._fixed_qty


@pytest.fixture
def registry() -> StrategyRegistry:
    reg = StrategyRegistry()
    reg.register(_DummyStrategy(strategy_id="momentum", quantity=10))
    return reg


@pytest.fixture
def strategy(registry: StrategyRegistry) -> StrategyBase:
    return registry.get("momentum")


@pytest.fixture
def engine(registry: StrategyRegistry) -> OrderEngine:
    return OrderEngine(registry)


@pytest.fixture
def mock_get_buyable(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """OrderEngine 이 참조하는 get_buyable 을 모킹 — 충분한 max_buy_quantity 반환."""
    mock = AsyncMock(
        return_value=BuyableInfo(
            cash_available=10_000_000,
            max_buy_amount=10_000_000,
            max_buy_quantity=999,
        )
    )
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "get_buyable", mock)
    return mock


@pytest.fixture
def mock_insert_trade(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """trade_history INSERT 호출 가로채기."""
    mock = AsyncMock(return_value=None)
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "insert_trade", mock)
    return mock


@pytest.fixture
def mock_place_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """place_order 모킹 — 각 테스트가 side_effect 로 시나리오 주입."""
    mock = AsyncMock()
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "place_order", mock)
    return mock


def _success_result(order_no: str) -> OrderResult:
    return OrderResult(order_no=order_no, order_time="093000", krx_org_no="")


# ---------------------------------------------------------------------------
# 시나리오 A — 시장가 정상 (회귀 기준선)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_buy_when_market_order_succeeds_then_mapping_registered(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
):
    """시장가 성공 — 매핑/INSERT 정상, place_order 1회만 호출."""
    mock_place_order.return_value = _success_result("ORDER-A-1")

    await engine.execute_buy("012200", 4500, strategy)

    assert mock_place_order.await_count == 1
    call = mock_place_order.await_args
    assert call.kwargs["side"] == OrderSide.BUY
    assert call.kwargs["price"] == 0  # 시장가
    # 매핑 등록 확인
    assert engine._order_qty.get("ORDER-A-1") == 10
    assert engine._order_strategy.get("ORDER-A-1") == "momentum"
    assert engine._order_ticker.get("ORDER-A-1") == "012200"
    assert "ORDER-A-1" in engine._pending_buy_orders
    # PENDING INSERT 발생
    assert mock_insert_trade.await_count == 1
    # pending_buys 에 ticker 등록 (체결 대기)
    assert "012200" in strategy.state.pending_buys


# ---------------------------------------------------------------------------
# 시나리오 B — 시장가 거부 → 지정가 5호가 폴백 성공
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_buy_when_market_disallowed_then_limit_fallback_at_5_ticks_up(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
):
    """1차 시장가 거부("시장가매매불가") → 2차 지정가 폴백 성공.

    폴백 가격은 `step_up(current_price, steps=5)`.
    """
    from src.engine.util.tick_size import step_up

    current_price = 4500  # 5원 단위 구간 → step_up(5) = 4525
    expected_fallback = step_up(current_price, steps=5)

    market_reject = KisApiError(rt_cd="1", msg_cd="UNKNOWN", msg1="시장가매매불가 종목입니다.")
    mock_place_order.side_effect = [market_reject, _success_result("ORDER-B-2")]

    await engine.execute_buy("012200", current_price, strategy)

    # place_order 2회 호출 (시장가 → 지정가)
    assert mock_place_order.await_count == 2

    first_call = mock_place_order.await_args_list[0]
    assert first_call.kwargs["price"] == 0  # 1차 시장가
    # OrderDivision.MARKET 은 기본값이라 명시되지 않을 수 있음 — 1차는 price=0 으로만 검증

    second_call = mock_place_order.await_args_list[1]
    assert second_call.kwargs["price"] == expected_fallback
    assert second_call.kwargs.get("order_division") == OrderDivision.LIMIT
    assert second_call.kwargs.get("side") == OrderSide.BUY
    assert second_call.kwargs.get("quantity") == 10

    # 매핑은 폴백 주문번호로 등록
    assert engine._order_qty.get("ORDER-B-2") == 10
    assert engine._order_strategy.get("ORDER-B-2") == "momentum"
    assert engine._order_ticker.get("ORDER-B-2") == "012200"
    assert "ORDER-B-2" in engine._pending_buy_orders

    # 1차 거부 주문번호로는 매핑이 등록되지 않음
    # (1차는 응답 자체가 없었음)

    # PENDING INSERT 는 폴백 성공 시점에 발생 (폴백 가격으로)
    assert mock_insert_trade.await_count == 1
    record_arg = mock_insert_trade.await_args.args[0]
    # TradeRecord 의 price 가 폴백 가격이어야 한다 — 시장가 의도였지만 실제 발주는 지정가
    assert record_arg.price == expected_fallback
    assert record_arg.order_no == "ORDER-B-2"

    # pending_buys 는 체결 대기 상태로 유지
    assert "012200" in strategy.state.pending_buys


# ---------------------------------------------------------------------------
# 시나리오 C — 시장가 거부 → 폴백도 거부
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_buy_when_both_market_and_limit_rejected_then_low_funds_cooldown(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
):
    """1차 시장가 + 2차 지정가 모두 거부 — cooldown 등록 + pending 회수."""
    market_reject = KisApiError(rt_cd="1", msg_cd="UNKNOWN", msg1="시장가매매불가 종목입니다.")
    limit_reject = KisApiError(rt_cd="1", msg_cd="UNKNOWN", msg1="해당 가격으로 매매 불가.")
    mock_place_order.side_effect = [market_reject, limit_reject]

    await engine.execute_buy("012200", 4500, strategy)

    # 2회 호출 후 종결
    assert mock_place_order.await_count == 2

    # 매핑 등록 없음 (1차도 응답 실패, 2차도 응답 실패)
    assert not engine._pending_buy_orders
    assert not engine._order_qty
    assert not engine._order_strategy
    assert not engine._order_ticker

    # pending_buys 회수
    assert "012200" not in strategy.state.pending_buys

    # low_funds cooldown 등록 (폴백 실패 → 동일 종목 매 틱 재시도 차단)
    assert "012200" in strategy.state.low_funds_tickers

    # trade_history INSERT 없음 (둘 다 응답 실패)
    assert mock_insert_trade.await_count == 0


# ---------------------------------------------------------------------------
# 시나리오 D — 자금부족 거부는 폴백하지 않는다 (회귀 보존)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_buy_when_insufficient_cash_then_no_fallback_and_block_buy(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
):
    """1차 거부가 `is_insufficient_cash` True → 폴백 *없음*, block_buy 호출."""
    cash_reject = KisApiError(rt_cd="1", msg_cd="APBK0919", msg1="주문가능금액이 부족합니다.")
    mock_place_order.side_effect = [cash_reject]

    await engine.execute_buy("012200", 4500, strategy)

    # 폴백 없음 — 1회만 호출
    assert mock_place_order.await_count == 1

    # 매수 락 발동
    import time

    assert strategy.state.is_buy_blocked(time.time())

    # pending_buys 회수
    assert "012200" not in strategy.state.pending_buys

    # 폴백 시도 안 했으므로 low_funds cooldown 도 등록 안 됨
    assert "012200" not in strategy.state.low_funds_tickers

    # PENDING INSERT 없음
    assert mock_insert_trade.await_count == 0


# ---------------------------------------------------------------------------
# 회귀 — pending_buy_amounts 동기 라이프사이클 (2026-05-11 P1 잔여 자금 폴백 가드)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_execute_buy_when_market_success_then_pending_amount_registered(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
):
    """시장가 성공 — pending_buy_amounts[ticker] = current_price × quantity."""
    mock_place_order.return_value = _success_result("ORDER-PA-1")

    await engine.execute_buy("012200", 4500, strategy)

    # 동기 등록: ticker → 4500 × 10 = 45000
    assert strategy.state.pending_buy_amounts.get("012200") == 45_000


@pytest.mark.asyncio
async def test_execute_buy_when_fallback_success_then_pending_amount_uses_fallback_price(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
):
    """지정가 폴백 성공 — pending_buy_amounts[ticker]는 폴백 가격 기준 재계산."""
    from src.engine.util.tick_size import step_up

    current_price = 4500
    expected_fallback = step_up(current_price, steps=5)

    market_reject = KisApiError(rt_cd="1", msg_cd="UNKNOWN", msg1="시장가매매불가 종목입니다.")
    mock_place_order.side_effect = [market_reject, _success_result("ORDER-PA-2")]

    await engine.execute_buy("012200", current_price, strategy)

    # 폴백 가격 × 수량 으로 재등록
    assert strategy.state.pending_buy_amounts.get("012200") == expected_fallback * 10


@pytest.mark.asyncio
async def test_execute_buy_when_both_rejected_then_pending_amount_cleared(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
):
    """시장가+폴백 모두 거부 — pending_buy_amounts 도 함께 정리 (pending_buys 동기)."""
    market_reject = KisApiError(rt_cd="1", msg_cd="UNKNOWN", msg1="시장가매매불가 종목입니다.")
    limit_reject = KisApiError(rt_cd="1", msg_cd="UNKNOWN", msg1="해당 가격으로 매매 불가.")
    mock_place_order.side_effect = [market_reject, limit_reject]

    await engine.execute_buy("012200", 4500, strategy)

    # pending_buys 회수 시 pending_buy_amounts 도 동시 정리
    assert "012200" not in strategy.state.pending_buys
    assert "012200" not in strategy.state.pending_buy_amounts


@pytest.mark.asyncio
async def test_execute_buy_when_insufficient_cash_then_pending_amount_cleared(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
):
    """자금부족 거부 — pending_buys 회수와 동시에 pending_buy_amounts 정리."""
    cash_reject = KisApiError(rt_cd="1", msg_cd="APBK0919", msg1="주문가능금액이 부족합니다.")
    mock_place_order.side_effect = [cash_reject]

    await engine.execute_buy("012200", 4500, strategy)

    assert "012200" not in strategy.state.pending_buys
    assert "012200" not in strategy.state.pending_buy_amounts


# ---------------------------------------------------------------------------
# PR-F (P2, 2026-05-15) — NXT 프리마켓 시장가 사전 차단 (preconvert)
#
# 결함 (운영 로그 2026-05-15 08:00:34):
#   LTV 매수 신호 [pre_nxt]: 064400 ...
#   BUY 주문 완료: 064400 1주 @ 0  (시장가)
#   WARNING 시장가 거부 → 지정가 5호가 폴백: 064400 @ 92300
#     (원인 [APBK0918] 장운영시간이 아닙니다.([프리마켓] 시장가 매매 불가 시간))
# - NXT 프리(08:00~09:00) 는 KIS 정책상 지정가만 허용
# - 매번 시장가 → 거부 → 5호가 폴백 패턴 (폴백 자체는 정상이지만 운영 노이즈)
#
# Fix 사양:
#   `place_order` 직전, `session_tracker.active == {pre_nxt}` AND `exchange in (NXT, SOR)` 면
#   사전에 `step_up(current_price, 5)` 지정가로 변환해 발사 — APBK0918 거부 자체를 차단.
#   기존 사후 폴백 분기는 보존(다른 거부 사유 대응).
# ---------------------------------------------------------------------------
@pytest.fixture
def _patch_session_active(monkeypatch):
    """src.engine.session.session_tracker._active 를 강제 설정하는 fixture factory."""
    from src.engine import session as _session
    from src.engine.session import MarketBoard

    def _set(boards: set[MarketBoard]) -> None:
        _session.session_tracker._active = frozenset(boards)

    yield _set, MarketBoard
    # 테스트 종료 후 원복
    _session.session_tracker._active = frozenset()


# NOTE: 미사용 + asyncio.run() 이 @pytest.mark.asyncio 안에서 호출되면
# `RuntimeError: asyncio.run() cannot be called from a running event loop`
# 발생하던 결함 fixture 제거 (PR #9 Copilot 리뷰 2026-05-15).
# 본 테스트들은 mock_kis_order_engine fixture 의 `_strategy_exchange_async` mock 으로 충분.


@pytest.mark.asyncio
async def test_execute_buy_preconverts_market_to_limit_in_pre_nxt_only_window(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    monkeypatch,
    _patch_session_active,
    caplog,
):
    """pre_nxt 단독 활성 + exchange=SOR → place_order 직전 LIMIT(step_up(price,5)) 변환."""
    import logging
    from src.engine.util.tick_size import step_up
    from src.engine import order_engine as _oe

    set_active, MarketBoard = _patch_session_active
    set_active({MarketBoard.PRE_NXT})

    # _strategy_exchange_async 가 SOR 반환하도록 패치
    async def _fake_exchange(self, strategy_id, *, ticker=None):
        return "SOR"
    monkeypatch.setattr(_oe.OrderEngine, "_strategy_exchange_async", _fake_exchange)

    mock_place_order.return_value = _success_result("ORDER-PRECONV-1")

    current_price = 91800
    expected_fallback = step_up(current_price, steps=5)

    caplog.set_level(logging.INFO, logger="src.engine.order_engine")
    await engine.execute_buy("064400", current_price, strategy)

    # place_order 1회 호출 — 시장가 거부 → 폴백 시퀀스 *없음*
    assert mock_place_order.await_count == 1
    call = mock_place_order.await_args
    assert call.kwargs["price"] == expected_fallback, (
        f"사전 변환된 폴백 가격으로 발사: 기대 {expected_fallback}, 실제 {call.kwargs['price']}"
    )
    assert call.kwargs.get("order_division") == OrderDivision.LIMIT, (
        "pre_nxt 단독 + NXT/SOR 면 LIMIT 으로 변환"
    )
    assert call.kwargs.get("exchange") == "SOR", "exchange 는 그대로 유지"

    # PENDING INSERT — 폴백 가격으로 기록
    assert mock_insert_trade.await_count == 1
    record_arg = mock_insert_trade.await_args.args[0]
    assert record_arg.price == expected_fallback


@pytest.mark.asyncio
async def test_execute_buy_preconverts_when_pre_nxt_and_krx_open_both_active(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    monkeypatch,
    _patch_session_active,
):
    """08:30~09:00 시간대 = active={PRE_NXT, KRX_OPEN} — 시장가 변환 적용 필요.

    PR #9 Codex P2 회귀 차단:
    - 초기 구현은 `active == frozenset({PRE_NXT})` exact equality 라
      KRX_OPEN 이 함께 활성인 후반 30분(08:30~09:00)에 false → 시장가 거부+폴백
      사이클 반복. membership 체크(`PRE_NXT in active and MAIN not in active`)
      로 NXT 프리마켓 전체 시간대 커버.
    """
    from src.engine.util.tick_size import step_up
    from src.engine import order_engine as _oe

    set_active, MarketBoard = _patch_session_active
    # 08:30~09:00 시나리오: PRE_NXT + KRX_OPEN 동시 활성
    set_active({MarketBoard.PRE_NXT, MarketBoard.KRX_OPEN})

    async def _fake_exchange(self, strategy_id, *, ticker=None):
        return "SOR"
    monkeypatch.setattr(_oe.OrderEngine, "_strategy_exchange_async", _fake_exchange)

    mock_place_order.return_value = _success_result("ORDER-PRECONV-2")
    current_price = 91800
    expected_fallback = step_up(current_price, steps=5)

    await engine.execute_buy("064400", current_price, strategy)

    assert mock_place_order.await_count == 1
    call = mock_place_order.await_args
    assert call.kwargs["price"] == expected_fallback, (
        "PRE_NXT + KRX_OPEN 동시 활성도 사전 변환 적용 (membership 체크)"
    )
    assert call.kwargs.get("order_division") == OrderDivision.LIMIT


@pytest.mark.asyncio
async def test_execute_buy_keeps_market_order_in_main_board(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    monkeypatch,
    _patch_session_active,
):
    """MAIN 보드 활성 → 시장가(price=0) 그대로 — 사전 변환 안 함."""
    from src.engine import order_engine as _oe

    set_active, MarketBoard = _patch_session_active
    set_active({MarketBoard.MAIN})

    async def _fake_exchange(self, strategy_id, *, ticker=None):
        return "SOR"
    monkeypatch.setattr(_oe.OrderEngine, "_strategy_exchange_async", _fake_exchange)

    mock_place_order.return_value = _success_result("ORDER-MAIN-1")

    await engine.execute_buy("064400", 91800, strategy)

    assert mock_place_order.await_count == 1
    call = mock_place_order.await_args
    assert call.kwargs["price"] == 0, "MAIN 보드면 시장가 유지"
    # MARKET 은 OrderDivision 기본값 — order_division 키워드 자체가 빠질 수 있음.
    # 명시되었다면 MARKET 이어야 함.
    if "order_division" in call.kwargs:
        assert call.kwargs["order_division"] == OrderDivision.MARKET


@pytest.mark.asyncio
async def test_execute_buy_keeps_market_order_for_krx_exchange_in_pre_nxt(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    monkeypatch,
    _patch_session_active,
):
    """exchange=KRX 이면 pre_nxt 활성이어도 시장가 유지 — KRX 는 시장가 받음."""
    from src.engine import order_engine as _oe

    set_active, MarketBoard = _patch_session_active
    set_active({MarketBoard.PRE_NXT})

    async def _fake_exchange(self, strategy_id, *, ticker=None):
        return "KRX"
    monkeypatch.setattr(_oe.OrderEngine, "_strategy_exchange_async", _fake_exchange)

    mock_place_order.return_value = _success_result("ORDER-KRX-1")

    await engine.execute_buy("064400", 91800, strategy)

    assert mock_place_order.await_count == 1
    call = mock_place_order.await_args
    assert call.kwargs["price"] == 0, "exchange=KRX 면 pre_nxt 활성이어도 시장가 유지"
    assert call.kwargs.get("exchange") == "KRX"


@pytest.mark.asyncio
async def test_execute_buy_market_preconvert_emits_log(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    monkeypatch,
    _patch_session_active,
    caplog,
):
    """변환 시 [market_order_preconvert_pre_nxt] INFO 로그 1행 노출."""
    import logging
    from src.engine import order_engine as _oe

    set_active, MarketBoard = _patch_session_active
    set_active({MarketBoard.PRE_NXT})

    async def _fake_exchange(self, strategy_id, *, ticker=None):
        return "NXT"
    monkeypatch.setattr(_oe.OrderEngine, "_strategy_exchange_async", _fake_exchange)

    mock_place_order.return_value = _success_result("ORDER-LOG-1")

    caplog.set_level(logging.INFO, logger="src.engine.order_engine")
    await engine.execute_buy("064400", 91800, strategy)

    msgs = "\n".join(r.message for r in caplog.records)
    assert "[market_order_preconvert_pre_nxt]" in msgs, (
        f"사전 변환 시 영문 prefix 로그 노출 필수, msgs={msgs!r}"
    )


@pytest.mark.asyncio
async def test_execute_buy_post_fallback_still_works_for_apbk1943(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_get_buyable: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    monkeypatch,
    _patch_session_active,
):
    """기존 사후 폴백(예: MAIN 시간대 시장가 거부) 은 그대로 작동.

    MAIN 활성 + 시장가 → 1차 거부 → 사후 폴백 → 2차 LIMIT 성공.
    PR-F 의 사전 변환은 pre_nxt 단독 케이스에만 적용되므로 MAIN 에서는 기존 분기 사용.
    """
    from src.engine import order_engine as _oe
    from src.engine.util.tick_size import step_up

    set_active, MarketBoard = _patch_session_active
    set_active({MarketBoard.MAIN})

    async def _fake_exchange(self, strategy_id, *, ticker=None):
        return "SOR"
    monkeypatch.setattr(_oe.OrderEngine, "_strategy_exchange_async", _fake_exchange)

    market_reject = KisApiError(rt_cd="1", msg_cd="APBK1943", msg1="시장가호가불가 종목입니다.")
    mock_place_order.side_effect = [market_reject, _success_result("ORDER-POST-2")]

    current_price = 4500
    expected_fallback = step_up(current_price, steps=5)
    await engine.execute_buy("012200", current_price, strategy)

    # 1차 시장가 → 2차 사후 폴백 (기존 분기) = 2회 호출
    assert mock_place_order.await_count == 2
    second_call = mock_place_order.await_args_list[1]
    assert second_call.kwargs["price"] == expected_fallback
    assert second_call.kwargs.get("order_division") == OrderDivision.LIMIT
