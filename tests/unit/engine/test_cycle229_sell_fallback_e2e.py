"""사이클 229 Red — `[단일가매매]` 거부의 매도 폴백 e2e (명세 W4-5).

명세 정본 `_workspace/red/cycle229_buy_cutoff_spec.md` W3·W4-5 /
자문 정본 `_workspace/domain_consult/cycle229_vb_1530_single_price.md` §5-2 /
행위 분해 `_workspace/red/cycle229_behaviors.md` §4.

**Red 단계 — 실패 테스트만. 프로덕션 미변경.** Green = backend-dev (`balance.py` 만).

## 이 파일이 검증하는 것 = W3 의 **하류 효과**

`order_engine.execute_sell` 은 **수정 대상이 아니다**(8영역). 이미 있는 분기

    if is_market_order_disallowed(e) and order_division == OrderDivision.MARKET:
        ... step_down(현재가, 5) 지정가 폴백 ...

가 실측 msg1 을 만나도 열리지 않는 이유는 오직 분류기의 키워드 미매칭 하나다.
`balance.py` 에 `"단일가매매"` 한 줄이 들어가면 이 경로가 **자동으로** 열린다 —
그게 이 파일의 단언 대상이다(기존 `test_order_engine_sell_fallback.py` 시나리오 H1 이
APBK3013 애프터마켓 변형에 대해 같은 일을 한 것과 동형).

## 왜 매도 축이 실익인가 — 매수와 귀결이 다르다

|                | 매수 `execute_buy`                       | 매도 `execute_sell`                  |
|----------------|------------------------------------------|--------------------------------------|
| 미분류 거부    | `raise` → `[callback_exception]` → WS 재연결 | 3회 재시도 후 **graceful 포기**      |
| TTL/cooldown   | —                                        | **없음**                             |
| 관측성         | 시끄럽다                                 | **조용하다**                         |

매도 축이 조용해서 안전한 게 아니라, **조용해서 안 보였을 뿐**이다. 15:30:00~15:30:30
랜덤엔드 창에서 손절/트레일링이 발화하면 시장가 매도가 거부되고, 어느 분류에도 안 걸려
재시도 후 포기한다. TTL 등록이 없으니 다음 틱마다 다시 3회 재시도한다 —
**청산이 그 창에서 실패한다는 사실 자체가 기록되지 않는다.**

⚠️ D+1 감시 항목: 지정가 매도 미체결 잔존 → `_selling` 좀비 가능성. 기존 180s
`[selling_reconcile]` 재대조 훅이 흡수한다(자문 §5-2 잔여 위험 1 — 신규 위험 아님).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.engine.util.tick_size import step_down
from src.models.order import OrderDivision, OrderResult, OrderSide

pytestmark = pytest.mark.unit

_TICKER = "012200"
_CURRENT_PRICE = 4500

# 실측 msg1 **전문** (APBK3013) — `test_cycle229_single_price_classifier.py` 와 동일 문자열
SINGLE_PRICE_MSG = (
    "[단일가매매] 지정가 주문(신규/정정/취소) 및 최유리/최우선 취소 주문만 가능합니다"
)
PRE_MARKET_MSG = "장운영시간이 아닙니다.([프리마켓] 시장가 매매 불가 시간)"


# ---------------------------------------------------------------------------
# 픽스처 — 기존 `test_order_engine_sell_fallback.py` 패턴 재사용 (새로 발명 금지)
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
    strat.state.positions[_TICKER] = Position(
        ticker=_TICKER,
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
def mock_write_log(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "write_log", mock)
    return mock


@pytest.fixture
def mock_delete_position(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    import src.db.positions as _positions

    monkeypatch.setattr(_positions, "delete_position", mock)
    return mock


@pytest.fixture
def mock_strategy_exchange(monkeypatch: pytest.MonkeyPatch):
    """`_strategy_exchange_async` → "KRX" 고정 — stock_master 의존성 분리."""

    async def _fake(self, strategy_id, *, ticker=None):  # noqa: ARG001
        return "KRX"

    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._strategy_exchange_async", _fake,
    )
    return _fake


@pytest.fixture
def no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """재시도 백오프 제거 — Red 경로는 3회 재시도(1s + 2s)를 타므로 테스트가 3초 걸린다.

    상수를 바꾸는 게 아니라 테스트 내 대체다(단위 테스트 1초 초과 금지 원칙).
    """
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "SELL_RETRY_DELAY", 0)


@pytest.fixture
def seeded_price(monkeypatch: pytest.MonkeyPatch) -> int:
    """폴백 가격 산출용 현재가 캐시 — 테스트 종료 시 자동 정리."""
    from src.engine import scanner as _scanner

    monkeypatch.setitem(_scanner.ticker_prices, _TICKER, {"current_price": _CURRENT_PRICE})
    return _CURRENT_PRICE


def _success(order_no: str) -> OrderResult:
    return OrderResult(order_no=order_no, order_time="153020", krx_org_no="")


def _single_price_error() -> KisApiError:
    return KisApiError(rt_cd="1", msg_cd="APBK3013", msg1=SINGLE_PRICE_MSG)


# ===========================================================================
# B4-1 / B4-3 — [RED] 실측 msg1 거부 → step_down(5) 지정가 폴백 진입
# ===========================================================================
@pytest.mark.asyncio
async def test_b4_1_single_price_rejection_enters_limit_fallback(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_place_order: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    no_retry_delay,
    seeded_price: int,
) -> None:
    """B4-1 (RED): 기존 폴백 분기가 **재사용**된다 — `execute_sell` 수정 0.

    현재 FAIL = 미분류라 폴백 분기 미진입 → 일반 재시도 3회(전부 시장가), LIMIT 0회.
    Green(`balance.py` 키워드 1줄) 후 = 시장가 1 + 지정가 폴백 1 = 2회.

    낮은 매도 지정가는 단일가 세션에서 **유효 주문**이고 종가에 체결된다 —
    매도 측에선 폴백이 정확히 옳은 처방이다(매수 측은 W1/W2 게이트가 이미 닫았다).
    """
    expected = step_down(seeded_price, steps=5)
    mock_place_order.side_effect = [_single_price_error(), _success("ORDER-229-1")]

    await engine.execute_sell(_TICKER, Signal.STOP_LOSS, "momentum")

    assert mock_place_order.await_count == 2, (
        f"폴백 미진입 (호출 {mock_place_order.await_count}회). 실측 `[단일가매매]` 변형이 "
        "`is_market_order_disallowed` 에 안 걸려 일반 재시도 루프로 떨어졌다"
    )

    first = mock_place_order.await_args_list[0]
    assert first.kwargs["side"] == OrderSide.SELL
    assert first.kwargs["price"] == 0  # 1차 시장가

    second = mock_place_order.await_args_list[1]
    assert second.kwargs["side"] == OrderSide.SELL
    assert second.kwargs["order_division"] == OrderDivision.LIMIT
    assert second.kwargs["price"] == expected, "폴백가는 `step_down(현재가, 5)`"
    assert second.kwargs["quantity"] == 10
    assert second.kwargs["exchange"] == "KRX", "폴백이 라우팅을 바꾸지 않는다"

    # B4-3 — 주문번호 매핑 3종 동기 등록 (체결통보 race 규약, 매수 폴백과 동일)
    assert engine._order_qty.get("ORDER-229-1") == 10
    assert engine._order_strategy.get("ORDER-229-1") == "momentum"
    assert engine._order_ticker.get("ORDER-229-1") == _TICKER

    # 체결 전이므로 포지션 보존
    assert _TICKER in strategy.state.positions
    assert mock_insert_trade.await_count == 1


# ===========================================================================
# B4-2 — [보존] 예외가 호출자로 전파되지 않는다 (매도 축이 '조용한' 이유)
# ===========================================================================
@pytest.mark.asyncio
async def test_b4_2_no_exception_propagates_to_caller(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_place_order: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_write_log: AsyncMock,
    mock_delete_position: AsyncMock,
    mock_strategy_exchange,
    no_retry_delay,
) -> None:
    """B4-2 (보존): `execute_sell` 은 거부를 re-raise 하지 않는다 — 지금도 앞으로도.

    이것이 매도 축 결함이 **무기록**이던 구조적 이유다(매수는 `raise` 로 시끄러웠다).
    Green 이 이 계약을 바꾸면 랜덤엔드 창의 매도 거부가 `on_tick` 밖으로 새어 나가
    매수 축과 똑같은 WS 재연결을 만든다 — G-REJECT-1 은 **원인**을 없애는 것이지
    전파 설계를 옮기는 게 아니다.

    현재가 캐시를 일부러 비워 폴백 불가 경로까지 태운다.
    """
    mock_place_order.side_effect = [_single_price_error()] * 3

    await engine.execute_sell(_TICKER, Signal.STOP_LOSS, "momentum")  # 예외 없이 반환

    assert _TICKER in strategy.state.positions, "청산 의무 — 포지션은 보존된다"
    assert mock_delete_position.await_count == 0
    assert _TICKER not in engine._selling, "`_selling` 해제 — stale 좀비 = 손절 마비"


# ===========================================================================
# B4-4 — [보존] 순서 계약 e2e: 프리마켓 거부는 여전히 '보류' 로 떨어진다
# ===========================================================================
@pytest.mark.asyncio
async def test_b4_4_pre_market_rejection_still_defers_without_fallback(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_place_order: AsyncMock,
    mock_insert_trade: AsyncMock,
    mock_write_log: AsyncMock,
    mock_delete_position: AsyncMock,
    mock_strategy_exchange,
    no_retry_delay,
    seeded_price: int,
) -> None:
    """B4-4 (보존): 신규 키워드가 `market_closed` 우선 검사를 뒤집지 않는다.

    프리마켓 msg1 은 두 분류기에 **동시 매칭**되며, `execute_sell` 이 closed 를 먼저 보는
    덕분에 '보류(포지션 보존 + 다음 09:00 TTL)' 로 떨어진다 — 프리장 왜곡 시세에
    지정가로 즉시 파는 것보다 09:00 KRX 보류가 안전하다는 2026-08-06 사용자 결정.
    순서가 뒤집히면 이 케이스가 place_order 2회(폴백 진입)로 깨진다.
    """
    mock_place_order.side_effect = [
        KisApiError(rt_cd="1", msg_cd="APBK0918", msg1=PRE_MARKET_MSG),
    ]

    await engine.execute_sell(_TICKER, Signal.STOP_LOSS, "momentum")

    assert mock_place_order.await_count == 1, "폴백 진입 = 검사 순서가 뒤집혔다"
    assert _TICKER in strategy.state.positions
    assert mock_delete_position.await_count == 0
