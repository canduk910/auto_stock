"""사이클 B-1 Red — 매도 좀비 폭주 차단 (시장 closed 거부 후 외부 재호출 게이트).

배경 (운영 실측, 2026-06-01):
    - 종목 064400 (LG씨엔에스, momentum) KST 08:00~08:09 10분간 500+ 매도 거부
      ([APBK0918] / [KIOK0320] "장운영시간이 아닙니다").
    - root cause: `src/engine/order_engine.py:519~569` 의 `is_market_closed_rejection(e)`
      분기는 *호출 내* 재시도만 차단하고 *외부 재진입* (risk.on_tick 매 tick
      check_exit_signal → execute_sell) 을 막지 못함.

결정:
    `OrderEngine._market_closed_blocked: dict[str, datetime]` ticker별 TTL 게이트 도입.
    TTL = 다음 KST 09:00 단순 만료 (domain-expert 자문 불필요 — 폭주 차단 단일 책임).
    차단 등록 위치: `is_market_closed_rejection(e)` True 분기 내. 차단 검사 위치:
    `execute_sell()` 진입 직후. `_reset_daily_state` 동행 clear.

회귀 가드 시나리오 (총 6+1):
    S1: 100회 연속 호출 → KIS API 호출 정확히 1회
        (나머지 99회는 진입 차단으로 skip). positions 메모리 보존.
    S2: KIOK0320 (msg_cd 다른 코드, 동일 msg1) 도 동일 차단.
    S3a/3b/3c: 다른 거부 분류는 차단 set 미등록 (회귀 가드):
        - is_insufficient_quantity → 기존 즉시 break + positions 삭제
        - is_market_order_disallowed → 기존 step_down 5호가 폴백
        - is_insufficient_cash → 기존 동작 (매수 분기, 매도 단위 검증 생략)
    S4: TTL 만료 후 재진입 가능 — 08:30 KST 차단 등록, 09:01 KST 진입 시 재호출.
    S5: ticker별 격리 — 064400 차단 등록 후 005930 매도 호출 정상 진입.
    S6: `reset_daily_state()` (또는 scheduler `_reset_daily_state` 동행) 호출 시 set clear.
    S7: 100회 진입 차단 시 INFO `[market_closed_blocked]` prefix 카운트 == 1 (cap).

테스트 더블:
    - place_order: AsyncMock — 시나리오별 side_effect 로 KisApiError raise
    - insert_trade / write_log: AsyncMock (호출 안전성만 확인)
    - delete_position: AsyncMock (S3a 회귀 가드용)
    - _strategy_exchange_async: KRX 반환 fake (stock_master 의존성 분리)
    - freezegun: KST 시간 고정/진행 (S4)

시간 헬퍼:
    `KST_TZ = timezone(timedelta(hours=9))` — `src.engine.scanner.KST_TZ` 와 동일.
    사이클 36 NameError 선례 (datetime.now() 단독 금지) 회피 — 모든 시각 비교는 KST aware.

Red 상태 검증 (Green 구현 전):
    - S1/S2/S4/S7 → 100회 place_order 호출되거나 차단 set attribute 부재로 AttributeError → FAIL
    - S3a/S3b/S3c → 다른 거부 분기는 *기존 코드* 가 이미 차단 set 등록 안 함 (set 자체 없음)
      → set 자체가 없으므로 attribute 검증 단계에서 AttributeError → FAIL
    - S5 → ticker별 분리 set 등록 자체가 없음 → 두 번째 호출도 정상 진입 (PASS 가능),
      그러나 핵심 검증인 "064400 여전히 차단" 검증에서 set 부재로 FAIL
    - S6 → `reset_daily_state` 헬퍼 메서드 부재로 AttributeError → FAIL
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import (
    Position,
    Signal,
    StrategyBase,
    StrategyConfig,
)
from src.engine.strategy_registry import StrategyRegistry
from src.models.order import OrderResult

pytestmark = pytest.mark.unit


# KST 시간대 — 사이클 36 NameError 선례 (datetime.now() 단독 금지) 회피.
KST_TZ = timezone(timedelta(hours=9))


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
    strat.state.positions["064400"] = Position(
        ticker="064400",
        buy_price=10_000,
        quantity=1,
        order_no="ORDER-PRE-064400",
        strategy_id="momentum",
        buy_date=date.today(),
    )
    strat.state.positions["005930"] = Position(
        ticker="005930",
        buy_price=70_000,
        quantity=1,
        order_no="ORDER-PRE-005930",
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
    mock = AsyncMock(return_value=None)
    import src.db.positions as _positions

    monkeypatch.setattr(_positions, "delete_position", mock)
    return mock


@pytest.fixture
def mock_write_log(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """write_log AsyncMock — S7 INFO 카운트 검증에도 사용."""
    mock = AsyncMock(return_value=None)
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "write_log", mock)
    return mock


@pytest.fixture
def mock_strategy_exchange(monkeypatch: pytest.MonkeyPatch):
    """`_strategy_exchange_async` 가 KRX 를 반환 — stock_master 의존 분리."""

    async def _fake(self, strategy_id, *, ticker=None):  # noqa: ARG001
        return "KRX"

    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._strategy_exchange_async",
        _fake,
    )
    return _fake


@pytest.fixture
def mock_stock_master(monkeypatch: pytest.MonkeyPatch):
    """NXT 시간대 사후 보강 (`stock_master.upsert_one`) 의존성 분리.

    is_market_closed_rejection 분기 진입 시 (08:00~09:00 / 15:30~20:00) 호출되므로,
    Supabase 의존성 차단을 위해 stub.
    """
    import src.db.stock_master as _sm

    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "upsert_one", AsyncMock(return_value=None))


def _market_closed_error_apbk0918() -> KisApiError:
    """KST 08:00~09:00 NXT 프리/KRX 진입 전 매도 거부 원문."""
    return KisApiError(
        rt_cd="1",
        msg_cd="APBK0918",
        msg1="장운영시간이 아닙니다.",
    )


def _market_closed_error_kiok0320() -> KisApiError:
    """KIOK0320 (msg_cd 다른 코드, 동일 msg1) — `_MARKET_CLOSED_KEYWORDS` 분기 검증."""
    return KisApiError(
        rt_cd="1",
        msg_cd="KIOK0320",
        msg1="장운영시간이 아닙니다.",
    )


def _market_disallow_error_apbk1943() -> KisApiError:
    """시장가 호가 불가 — `is_market_order_disallowed` 분기 (회귀 가드용)."""
    return KisApiError(
        rt_cd="1",
        msg_cd="APBK1943",
        msg1="시장가호가불가로 주문이 불가합니다.",
    )


def _insufficient_qty_error() -> KisApiError:
    """보유 부족 — `is_insufficient_quantity` 분기 (회귀 가드용)."""
    return KisApiError(
        rt_cd="1",
        msg_cd="APBK1234",
        msg1="매도가능수량이 부족합니다.",
    )


def _success_result(order_no: str) -> OrderResult:
    return OrderResult(order_no=order_no, order_time="090022", krx_org_no="")


# ===========================================================================
# S1 — 100회 연속 호출 시 KIS API 정확히 1회만
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-01 08:00:00", tz_offset=-9)  # KST 08:00 (UTC 전날 23:00)
async def test_s1_when_apbk0918_then_100_calls_invoke_place_order_only_once(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
):
    """결함 차단: KIS 매도 거부 (APBK0918 장운영시간 외) 후 100회 재진입 → 진입 게이트로 99회 skip."""
    # 1회 거부 + 이후 99회는 진입 차단으로 KIS 호출 자체가 없어야 함.
    # 만약 진입 차단이 없으면 100회 모두 호출 → side_effect 가 부족하면 StopIteration.
    # 따라서 100개의 거부를 미리 채워두어 *결함 상태* 에서도 100회 진입이 가능함을 보장.
    mock_place_order.side_effect = [_market_closed_error_apbk0918()] * 100

    for _ in range(100):
        # 매 호출마다 _selling 가드를 우회 (정상 흐름은 체결통보에서 discard 되지만 단위 테스트는
        # 사전 정리). _selling 가드는 본 사이클 검증 범위 밖.
        engine._selling.discard("064400")
        await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")

    # 핵심 검증: 100회 호출 시도에도 KIS API 는 1회만 호출
    assert mock_place_order.await_count == 1, (
        f"진입 차단 누락: place_order 가 {mock_place_order.await_count}회 호출됨 "
        f"(기대: 1회). _market_closed_blocked 게이트 미구현."
    )

    # positions 보존 (메모리)
    assert "064400" in strategy.state.positions, "positions 보존 위반"

    # 차단 set 등록 검증
    assert hasattr(engine, "_market_closed_blocked"), (
        "OrderEngine._market_closed_blocked 필드 미정의 — Green 구현 필요"
    )
    assert "064400" in engine._market_closed_blocked, (
        "차단 set 에 064400 등록 안 됨"
    )
    expiry = engine._market_closed_blocked["064400"]
    # TTL = 다음 KST 09:00 (당일 08:00 기준 → 당일 09:00)
    expected_expiry = datetime(2026, 6, 1, 9, 0, 0, tzinfo=KST_TZ)
    assert expiry == expected_expiry, (
        f"TTL 불일치: {expiry} != {expected_expiry} (KST 다음 09:00 기대)"
    )


# ===========================================================================
# S2 — KIOK0320 도 동일 차단
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-01 08:05:00", tz_offset=-9)  # KST 08:05
async def test_s2_when_kiok0320_then_100_calls_invoke_place_order_only_once(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
):
    """결함 차단: KIOK0320 (msg_cd 다른 코드, 동일 msg1) 도 APBK0918 과 동일 차단."""
    mock_place_order.side_effect = [_market_closed_error_kiok0320()] * 100

    for _ in range(100):
        engine._selling.discard("064400")
        await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")

    assert mock_place_order.await_count == 1, (
        f"KIOK0320 차단 누락: place_order {mock_place_order.await_count}회 호출"
    )
    assert hasattr(engine, "_market_closed_blocked")
    assert "064400" in engine._market_closed_blocked


# ===========================================================================
# S3a — is_insufficient_quantity 는 차단 set 미등록 (회귀 가드)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-01 09:30:00", tz_offset=-9)  # KST 09:30 (정규장 시간)
async def test_s3a_when_insufficient_quantity_then_not_registered_in_block_set(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_delete_position: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
):
    """회귀 가드: 보유 부족 거부는 기존 즉시 break + positions 삭제 동작 보존, 차단 set 미등록."""
    mock_place_order.side_effect = [_insufficient_qty_error()]

    await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")

    # 기존 동작 보존 — 정확히 1회 호출 (재시도 없음, 폴백 없음)
    assert mock_place_order.await_count == 1
    # positions 메모리 삭제 (기존 동작)
    assert "064400" not in strategy.state.positions
    # 차단 set 미등록 — 본 사이클 신규 가드 침범 안 함
    blocked = getattr(engine, "_market_closed_blocked", {})
    assert "064400" not in blocked, (
        "is_insufficient_quantity 가 차단 set 에 잘못 등록됨 — 회귀 위반"
    )


# ===========================================================================
# S3b — is_market_order_disallowed 는 차단 set 미등록 (회귀 가드)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-01 09:00:30", tz_offset=-9)  # KST 09:00:30 (정규장 직후)
async def test_s3b_when_market_order_disallowed_then_fallback_runs_and_block_set_clean(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
):
    """회귀 가드: APBK1943 시장가 호가 불가 → step_down 5호가 지정가 폴백 (기존 동작).
    차단 set 미등록 — 본 가드는 시장 closed 거부에만 작동.
    """
    from src.engine import scanner as _scanner

    _scanner.ticker_prices["064400"] = {"current_price": 10_000}
    try:
        # 1차 시장가 거부 → 2차 지정가 폴백 성공
        mock_place_order.side_effect = [
            _market_disallow_error_apbk1943(),
            _success_result("ORDER-S3B-1"),
        ]

        await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")
    finally:
        _scanner.ticker_prices.pop("064400", None)

    # 폴백 1회 발생 — place_order 정확히 2회
    assert mock_place_order.await_count == 2, (
        "기존 시장가→지정가 폴백 회귀 — 폴백 호출 누락"
    )
    # 차단 set 미등록
    blocked = getattr(engine, "_market_closed_blocked", {})
    assert "064400" not in blocked, (
        "is_market_order_disallowed 가 차단 set 에 잘못 등록됨 — 회귀 위반"
    )


# ===========================================================================
# S4 — TTL 만료 후 재진입 가능 (08:30 차단 → 09:01 재호출)
# ===========================================================================
@pytest.mark.asyncio
async def test_s4_when_ttl_expired_then_can_reinvoke_place_order(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
):
    """결함 차단: TTL = 다음 KST 09:00. 09:01 진입 시 같은 ticker 재호출 가능.
    만료 시 차단 set 에서 ticker 제거.
    """
    # 1차: 08:30 KST — 거부 응답 등록
    # 2차: 09:01 KST — TTL 만료, 성공 응답
    mock_place_order.side_effect = [
        _market_closed_error_apbk0918(),  # 08:30 거부 → 차단 등록
        _success_result("ORDER-S4-1"),     # 09:01 성공
    ]

    with freeze_time("2026-06-01 08:30:00", tz_offset=-9):  # KST 08:30
        engine._selling.discard("064400")
        await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")

        # 차단 등록 검증
        assert hasattr(engine, "_market_closed_blocked")
        assert "064400" in engine._market_closed_blocked
        # 차단 상태에서 추가 호출 시도 → KIS 호출 안 됨
        await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")
        assert mock_place_order.await_count == 1, (
            "TTL 미만료 구간 — 추가 호출은 차단되어야 함"
        )

    # 시간 진행: 09:01 KST → TTL 만료
    with freeze_time("2026-06-01 09:01:00", tz_offset=-9):  # KST 09:01 (TTL 만료 후)
        engine._selling.discard("064400")
        await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")

    # TTL 만료 후 2번째 KIS 호출 발생
    assert mock_place_order.await_count == 2, (
        f"TTL 만료 후 재진입 안 됨: place_order {mock_place_order.await_count}회 (기대 2)"
    )
    # 만료 시 차단 set 에서 ticker 제거
    blocked = getattr(engine, "_market_closed_blocked", {})
    assert "064400" not in blocked, (
        "TTL 만료 후 차단 set 에서 ticker 자동 제거 안 됨"
    )


# ===========================================================================
# S5 — ticker별 격리 (064400 차단 후 005930 정상 진입)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-01 08:00:00", tz_offset=-9)  # KST 08:00
async def test_s5_when_one_ticker_blocked_then_other_ticker_still_invokes(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
):
    """결함 차단: 차단은 ticker 별 — 064400 등록이 005930 매도를 막으면 안 됨."""
    # 1차: 064400 거부 → 차단 등록
    # 2차: 005930 성공 (다른 ticker, 차단 영향 받지 않음)
    mock_place_order.side_effect = [
        _market_closed_error_apbk0918(),
        _success_result("ORDER-S5-005930"),
    ]

    # 064400 거부 등록
    engine._selling.discard("064400")
    await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")
    assert mock_place_order.await_count == 1

    # 005930 매도 — 정상 진입해야 함
    engine._selling.discard("005930")
    await engine.execute_sell("005930", Signal.STOP_LOSS, "momentum")
    assert mock_place_order.await_count == 2, (
        "다른 ticker (005930) 매도가 차단됨 — ticker 격리 위반"
    )

    # 064400 은 여전히 차단 상태
    blocked = getattr(engine, "_market_closed_blocked", {})
    assert "064400" in blocked, "064400 차단 등록 누락"
    assert "005930" not in blocked, (
        "005930 (성공한 ticker) 이 차단 set 에 잘못 등록됨"
    )


# ===========================================================================
# S6 — reset_daily_state() 호출 시 set clear
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-01 08:00:00", tz_offset=-9)  # KST 08:00
async def test_s6_when_reset_daily_state_then_block_set_cleared(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
):
    """결함 차단: `_reset_daily_state` 동행 clear — 차단 set/로그 cap 모두 비워짐.

    Green 명세: `OrderEngine.reset_daily_state()` 헬퍼 추가 (캡슐화) — scheduler 가 호출.
    """
    # 차단 등록
    mock_place_order.side_effect = [_market_closed_error_apbk0918()]
    await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")

    assert hasattr(engine, "_market_closed_blocked")
    assert "064400" in engine._market_closed_blocked

    # reset_daily_state() 헬퍼 호출 — Green 단계에서 OrderEngine 에 추가됨
    assert hasattr(engine, "reset_daily_state"), (
        "OrderEngine.reset_daily_state() 헬퍼 미정의 — Green 구현 필요 "
        "(scheduler `_reset_daily_state` 가 위임 호출)"
    )
    engine.reset_daily_state()

    # 차단 set 비워짐
    assert engine._market_closed_blocked == {}, (
        "reset_daily_state 후 _market_closed_blocked 비어있지 않음"
    )
    # 로그 cap 도 비워짐
    logged = getattr(engine, "_market_closed_blocked_logged_today", set())
    assert logged == set(), (
        "reset_daily_state 후 _market_closed_blocked_logged_today 비어있지 않음"
    )


# ===========================================================================
# S7 — 진입 차단 INFO emit cap (ticker별 일일 1회)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-01 08:00:00", tz_offset=-9)  # KST 08:00
async def test_s7_when_100_blocked_calls_then_info_log_emitted_only_once(
    engine: OrderEngine,
    strategy: StrategyBase,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
):
    """결함 차단: 100회 차단 시 INFO `[market_closed_blocked]` prefix 1회만 emit (cap).

    사이클 31 R6 의 `_risk_silent_skip_logged_today` 동형 패턴 —
    `_market_closed_blocked_logged_today: set[str]` (ticker only).
    """
    # 1회 거부 + 99회 차단
    mock_place_order.side_effect = [_market_closed_error_apbk0918()] * 100

    for _ in range(100):
        engine._selling.discard("064400")
        await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")

    # INFO `[market_closed_blocked]` prefix 호출 카운트 == 1 (cap)
    # write_log AsyncMock 호출 인자에서 prefix 카운트
    blocked_info_calls = [
        call for call in mock_write_log.await_args_list
        if len(call.args) >= 2 and "[market_closed_blocked]" in str(call.args[1])
    ]
    assert len(blocked_info_calls) == 1, (
        f"[market_closed_blocked] INFO emit cap 위반: {len(blocked_info_calls)}회 "
        f"(기대 1회). _market_closed_blocked_logged_today set 미구현."
    )
