"""Phase G Red — `OrderEngine._strategy_exchange(strategy_id, ticker=None)`.

NXT/SOR 라우팅 요청이지만 stock_master 가 `nxt_tradable=False` 로 알려준 종목은
**KRX 강제 다운그레이드** + `[nxt_downgrade]` system_logs 1행.

요구 행위:

1. ticker 인자 미지정 또는 nxt_tradable=True → 전략 params["exchange"] 그대로 반환.
2. ticker 인자 + stock_master 캐시 hit + nxt_tradable=False:
   - 전략 exchange 가 `NXT` 또는 `SOR` 이면 → `KRX` 반환
   - 전략 exchange 가 이미 `KRX` 이면 → `KRX` 반환 (no-op)
   - 다운그레이드 시 `system_logs.write_log(level, msg)` 가 호출되고 msg 에 `[nxt_downgrade]` prefix.
3. stock_master 캐시 miss → 전략 exchange 그대로 (보수적 fallback, KIS 호출은 호출자 책임).

테스트 더블:
- `stock_master.get` AsyncMock 으로 nxt_tradable 분기 시뮬.
- `write_log` AsyncMock 으로 로그 호출 검증.
- 전략은 `_DummyStrategy(exchange=...)` 로 케이스별 주입.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

# cycle287 검증 시정 — `_strategy_exchange_async` 는 다운그레이드(시각 무관) *뒤*
# 규칙 1 라우터(시각 의존)를 거친다. base 가 이미 "KRX" 인 케이스는 라우터가
# clause 1(`base_krx`)에서 즉시 통과해 시각 무관이지만, base 가 "NXT"/"SOR" 로
# 유지되길 기대하는 케이스는 실행 시각에 따라 KRX 정규장·애프터마켓 시간대에
# 걸리면 라우터가 "KRX" 로 되돌린다(적대 검증 H2 — CI 가 UTC 기준으로 도는
# 시각에 따라 이 파일이 깨지던 결함). 어느 거래소도 우리 호가유형을 받지 않는
# `both_unsupported_keep` 창(23:00 KST)으로 고정해 라우터가 항상 base 를
# 그대로 반환하게 한다.
_BOTH_UNSUPPORTED_KST_2300 = "2026-01-15 14:00:00"  # UTC → KST 23:00

pytestmark = pytest.mark.unit


class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id: str, exchange: str) -> None:
        super().__init__(
            StrategyConfig(
                strategy_id=strategy_id,
                name=f"{strategy_id}-dummy",
                enabled=True,
                weight=1.0,
                params={"exchange": exchange},
            )
        )

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 1


def _registry(strategy_id: str, exchange: str) -> StrategyRegistry:
    reg = StrategyRegistry()
    reg.register(_DummyStrategy(strategy_id=strategy_id, exchange=exchange))
    return reg


@pytest.fixture
def mock_write_log(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    import src.engine.order_engine as _oe

    # OrderEngine 이 어떤 경로로 호출하든 가로채기
    monkeypatch.setattr(_oe, "write_log", mock, raising=False)
    return mock


@pytest.fixture
def stub_stock_master_factory(monkeypatch: pytest.MonkeyPatch):
    """stock_master.get 을 nxt_tradable 분기로 stub 하는 factory."""

    def _setup(*, nxt_tradable: bool | None):
        """nxt_tradable=None → cache miss (get returns None)."""
        import src.engine.order_engine as _oe

        async def _get(ticker: str):
            if nxt_tradable is None:
                return None
            from src.models.stock import StockBasics

            return StockBasics(
                ticker=ticker,
                name="",
                excg_dvsn_cd="02",
                nxt_tradable=nxt_tradable,
                krx_halted=False,
                admin_item=False,
                raw={},
            )

        # OrderEngine 이 어떤 경로로 stock_master 를 참조하든 가로채기
        import src.db.stock_master as _sm

        monkeypatch.setattr(_sm, "get", _get)
        if hasattr(_oe, "stock_master_get"):
            monkeypatch.setattr(_oe, "stock_master_get", _get, raising=False)
        return _get

    return _setup


# ---------------------------------------------------------------------------
# 1. ticker 인자 없으면 전략 exchange 그대로
# ---------------------------------------------------------------------------
def test_strategy_exchange_without_ticker_returns_strategy_default():
    reg = _registry("momentum", "SOR")
    eng = OrderEngine(reg)
    assert eng._strategy_exchange("momentum") == "SOR"


# ---------------------------------------------------------------------------
# 2. nxt_tradable=False 일 때 NXT → KRX
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_strategy_exchange_downgrades_nxt_to_krx_when_not_tradable(
    stub_stock_master_factory,
    mock_write_log: AsyncMock,
):
    stub_stock_master_factory(nxt_tradable=False)
    reg = _registry("momentum", "NXT")
    eng = OrderEngine(reg)

    result = await eng._strategy_exchange_async("momentum", ticker="012200")

    assert result == "KRX"
    # [nxt_downgrade] 로그 1행
    assert mock_write_log.await_count >= 1
    logged = " ".join(
        str(a) for c in mock_write_log.await_args_list for a in c.args
    )
    assert "[nxt_downgrade]" in logged
    assert "012200" in logged


# ---------------------------------------------------------------------------
# 3. nxt_tradable=False 일 때 SOR → KRX
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_strategy_exchange_downgrades_sor_to_krx_when_not_tradable(
    stub_stock_master_factory,
    mock_write_log: AsyncMock,
):
    stub_stock_master_factory(nxt_tradable=False)
    reg = _registry("momentum", "SOR")
    eng = OrderEngine(reg)

    result = await eng._strategy_exchange_async("momentum", ticker="012200")
    assert result == "KRX"


# ---------------------------------------------------------------------------
# 4. nxt_tradable=True 이면 전략 exchange 그대로 (no downgrade)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_strategy_exchange_keeps_nxt_when_tradable(
    stub_stock_master_factory,
    mock_write_log: AsyncMock,
):
    stub_stock_master_factory(nxt_tradable=True)
    reg = _registry("momentum", "NXT")
    eng = OrderEngine(reg)

    with freeze_time(_BOTH_UNSUPPORTED_KST_2300):
        result = await eng._strategy_exchange_async("momentum", ticker="012200")
    assert result == "NXT"
    # downgrade 로그 없음
    logged = " ".join(
        str(a) for c in mock_write_log.await_args_list for a in c.args
    )
    assert "[nxt_downgrade]" not in logged


# ---------------------------------------------------------------------------
# 5. stock_master cache miss → 전략 exchange 그대로 (보수적 fallback)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_strategy_exchange_cache_miss_keeps_strategy_default(
    stub_stock_master_factory,
    mock_write_log: AsyncMock,
):
    stub_stock_master_factory(nxt_tradable=None)
    reg = _registry("momentum", "SOR")
    eng = OrderEngine(reg)

    with freeze_time(_BOTH_UNSUPPORTED_KST_2300):
        result = await eng._strategy_exchange_async("momentum", ticker="012200")
    assert result == "SOR"


# ---------------------------------------------------------------------------
# 6. KRX 전략 + nxt_tradable=False — no-op
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_strategy_exchange_krx_strategy_no_op(
    stub_stock_master_factory,
    mock_write_log: AsyncMock,
):
    stub_stock_master_factory(nxt_tradable=False)
    reg = _registry("momentum", "KRX")
    eng = OrderEngine(reg)

    result = await eng._strategy_exchange_async("momentum", ticker="012200")
    assert result == "KRX"
    # downgrade 로그 없음 (이미 KRX)
    logged = " ".join(
        str(a) for c in mock_write_log.await_args_list for a in c.args
    )
    assert "[nxt_downgrade]" not in logged
