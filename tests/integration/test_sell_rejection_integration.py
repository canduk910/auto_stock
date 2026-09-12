"""사이클 55 R-1 Red — execute_sell ↔ SellRejectionTracker 통합 검증.

배경 (refactor-expert 설계 카드 §2/§4, 2026-06-03):
    `OrderEngine.execute_sell` 의 4 거부 분류 분기가 `SellRejectionTracker` 정책 객체에
    위임되었을 때, 호출 흐름 + 호환 layer + Q2/Q3 신규 행위 (NXT 익일 전환 +
    positions reconciliation) 가 회귀 없이 동작함을 검증.

테스트 매트릭스 (8 케이스):
    C-1: 진입 게이트 — tracker.is_blocked=True 면 KIS 호출 없이 skip + INFO 1줄
    C-2: market_closed 거부 → tracker.register_market_closed 호출 + stock_master 사후 보강 보존
    C-3: market_order_disallowed 폴백 흐름 + tracker.register_market_order_disallowed 호출
    C-4: market_order_disallowed + NXT + 폴백 실패 → next_day_clear 등록 (Q2 핵심)
    C-5: insufficient_quantity 거부 → tracker 적재 + [positions_reconciliation] 로그 + get_balance() 호출
    C-6: scheduler._reset_daily_state → order_engine.reset_daily_state → tracker.reset_daily 위임 체인
    C-7: 호환 property 위임 — engine._market_closed_blocked 가 tracker 내부 dict 와 `is` 동일
    C-8: 사이클 30 _completed_orders race 가드 무영향

Red 상태:
    - `SellRejectionTracker` 모듈 부재 → ImportError 또는 attribute 부재로 FAIL.
    - Q3 reconciliation (get_balance + [positions_reconciliation] 로그) 미구현 → 호출 carga 검증 FAIL.
    - Q2 next_day_clear 등록 미구현 → set add 미발화 FAIL.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

_KST_TEST = timezone(timedelta(hours=9))  # 사이클 68 hotfix
from unittest.mock import AsyncMock, MagicMock

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

pytestmark = pytest.mark.integration


KST_TZ = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 더미 전략
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
    strat.state.positions["064400"] = Position(
        ticker="064400",
        buy_price=10_000,
        quantity=1,
        order_no="ORDER-PRE-064400",
        strategy_id="momentum",
        buy_date=datetime.now(_KST_TEST).date(),
    )
    reg.register(strat)
    return reg


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
    mock = AsyncMock(return_value=None)
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "write_log", mock)
    # 사이클 56-E (2026-06-04): safe_write_log 도 동일 mock 으로 패치.
    # order_engine 내 write_log → safe_write_log 마이그레이션 후 호출 추적 보존.
    monkeypatch.setattr(_oe, "safe_write_log", mock)
    return mock


@pytest.fixture
def mock_strategy_exchange(monkeypatch: pytest.MonkeyPatch):
    async def _fake(self, strategy_id, *, ticker=None):  # noqa: ARG001
        return "KRX"

    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._strategy_exchange_async",
        _fake,
    )
    return _fake


@pytest.fixture
def mock_stock_master(monkeypatch: pytest.MonkeyPatch):
    import src.db.stock_master as _sm

    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "upsert_one", AsyncMock(return_value=None))
    return _sm


@pytest.fixture
def mock_get_balance(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Q3 reconciliation — get_balance() 호출 검증용.

    설계 카드 §4.5: insufficient_quantity 거부 시 positions 정리 직후 1회 호출.
    """
    mock = AsyncMock(return_value=([], None))
    # OrderEngine 내부에서 lazy import 가정 (sell_rejection 분기에서 reconciliation 시).
    # backend-dev 가 어디서 import 하든 가능하도록 양쪽 경로 다 패치.
    import src.api.balance as _balance
    monkeypatch.setattr(_balance, "get_balance", mock)
    try:
        import src.engine.order_engine as _oe
        if hasattr(_oe, "get_balance"):
            monkeypatch.setattr(_oe, "get_balance", mock)
    except AttributeError:
        pass
    return mock


def _market_closed_err() -> KisApiError:
    return KisApiError(rt_cd="1", msg_cd="APBK0918", msg1="장운영시간이 아닙니다.")


def _market_disallow_err() -> KisApiError:
    return KisApiError(
        rt_cd="1", msg_cd="APBK1943",
        msg1="시장가호가불가로 주문이 불가합니다.",
    )


def _insufficient_qty_err() -> KisApiError:
    return KisApiError(
        rt_cd="1", msg_cd="APBK1234", msg1="매도가능수량이 부족합니다.",
    )


def _success(order_no: str) -> OrderResult:
    return OrderResult(order_no=order_no, order_time="100000", krx_org_no="")


# ===========================================================================
# C-1 — 진입 게이트: tracker.is_blocked=True 시 KIS 호출 없이 skip
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-03 11:00:00", tz_offset=-9)
async def test_c1_when_tracker_is_blocked_then_no_kis_call_and_info_log_once(
    engine: OrderEngine,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
):
    """C-1: tracker.is_blocked=True (사전 등록) 시 execute_sell 가 KIS 호출 없이 즉시 skip.

    호환 layer 의 진입 게이트가 tracker 위임으로 동작함을 검증.
    """
    # 사전 등록 (사이클 55 R-1 — tracker 위임)
    now_kst = datetime.now(KST_TZ)
    # KRX 메인 시간 — 5분 TTL 등록 (직접 tracker API 호출)
    assert hasattr(engine, "_sell_rejection"), (
        "OrderEngine._sell_rejection 필드 미정의 — 사이클 55 Green 구현 필요"
    )
    engine._sell_rejection.register_market_closed(
        "064400", now_kst, in_krx_main_hours=True
    )

    # execute_sell 호출 — 차단되어 KIS 호출 없어야 함
    await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")

    assert mock_place_order.await_count == 0, (
        "tracker.is_blocked=True 인데 KIS 호출 발생 — 진입 게이트 위임 결함"
    )

    # 100회 호출에도 INFO 1줄 (cap)
    for _ in range(100):
        engine._selling.discard("064400")
        await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")

    blocked_info_calls = [
        c for c in mock_write_log.await_args_list
        if len(c.args) >= 2 and "[market_closed_blocked]" in str(c.args[1])
    ]
    assert len(blocked_info_calls) == 1, (
        f"INFO emit cap 위반: {len(blocked_info_calls)}회 (기대 1회)"
    )


# ===========================================================================
# C-2 — market_closed 거부 → tracker 등록 + stock_master 사후 보강 보존
# ===========================================================================
# cycle286 (C4-a, 2026-09-12) — 이 자리의 원래 단정은 "NXT 시간대(시계)면 무조건
# nxt_tradable=False 를 쓴다" 였고 `mock_strategy_exchange` 는 기본값 "KRX" 를
# 돌려주는데도 통과했다 — 그게 곧 이번에 닫은 결함의 화석이다(시계만으로 판정하면
# KRX 로 나간 주문의 거부에도 쓴다). 이제 판정축은 **거래소 ∧ 좁힌 프리장 창
# (08:00~08:50)** 이라 이 테스트는 거래소를 명시적으로 NXT 로 고정해 "진짜 NXT
# 거부의 학습은 살아 있다"를 증명하고, 바로 아래 `test_c2b_*` 가 그 반대(KRX 라우팅
# 거부는 쓰지 않는다)를 짝으로 고정한다.
@pytest.mark.asyncio
@freeze_time("2026-06-03 08:30:00", tz_offset=-9)  # NXT 프리마켓(08:00~08:50) 안
async def test_c2_when_market_closed_then_tracker_register_called_and_stock_master_upsert(
    engine: OrderEngine,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
    monkeypatch: pytest.MonkeyPatch,
):
    """C-2 (cycle286 갱신): NXT 로 나간 주문의 market_closed 거부 → tracker 등록 +
    stock_master.upsert_one 사후 보강 양쪽 모두 발화.

    `target_exchange` 를 명시적으로 "NXT" 로 override 한다 — `mock_strategy_exchange`
    공용 픽스처의 기본값 "KRX" 로는 이 사이클부터 학습 write 가 발생하지 않는다
    (그것이 정확히 이번 사이클이 닫은 결함이다).
    """
    async def _nxt(self, strategy_id, *, ticker=None):  # noqa: ARG001
        return "NXT"

    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._strategy_exchange_async", _nxt,
    )
    mock_place_order.side_effect = [_market_closed_err()]

    await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")

    # tracker 등록 — _blocked_until / _blocked_reason 양쪽 동기 등록
    assert "064400" in engine._sell_rejection._blocked_until, (
        "tracker._blocked_until 등록 누락 — register_market_closed 위임 결함"
    )
    assert engine._sell_rejection._blocked_reason.get("064400") == "market_closed", (
        "_blocked_reason 등록 누락 또는 잘못된 분류"
    )

    # NXT 로 나간 프리마켓 거부 — stock_master.upsert_one 사후 보강 호출 보존
    mock_stock_master.upsert_one.assert_awaited()


@pytest.mark.asyncio
@freeze_time("2026-06-03 08:30:00", tz_offset=-9)  # NXT 프리마켓(08:00~08:50) 안
async def test_c2b_when_market_closed_and_krx_routed_then_no_stock_master_upsert(
    engine: OrderEngine,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
):
    """C-2b (cycle286 신규, C4-a): 같은 시각·같은 거부라도 **KRX 로 나간 주문**이면
    학습하지 않는다 — `mock_strategy_exchange` 기본값 "KRX" 그대로(override 없음).

    거부는 여전히 tracker 에 등록된다(TTL 축 무접촉) — 달라지는 것은 DB write 뿐이다.
    """
    mock_place_order.side_effect = [_market_closed_err()]

    await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")

    assert "064400" in engine._sell_rejection._blocked_until, (
        "KRX 라우팅이어도 tracker 등록(TTL 축)은 그대로여야 한다"
    )
    mock_stock_master.upsert_one.assert_not_awaited()


# ===========================================================================
# C-3 — market_order_disallowed: 폴백 흐름 + tracker 등록
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-03 10:00:00", tz_offset=-9)  # KRX 메인
async def test_c3_when_market_order_disallowed_then_fallback_and_tracker_register(
    engine: OrderEngine,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
):
    """C-3: market_order_disallowed 거부 → step_down 폴백 + tracker.register_market_order_disallowed
    호출 (30초 TTL 등록).
    """
    from src.engine import scanner as _scanner
    _scanner.ticker_prices["064400"] = {"current_price": 10_000}
    try:
        mock_place_order.side_effect = [
            _market_disallow_err(),
            _success("ORDER-C3-1"),
        ]
        await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")
    finally:
        _scanner.ticker_prices.pop("064400", None)

    # 폴백 호출 정상 (2회 = 시장가 거부 + 지정가 폴백)
    assert mock_place_order.await_count == 2

    # tracker 등록 — 30초 TTL
    assert "064400" in engine._sell_rejection._blocked_until, (
        "tracker._blocked_until 등록 누락 — market_order_disallowed 위임 결함"
    )
    assert engine._sell_rejection._blocked_reason.get("064400") == "market_order_disallowed"


# ===========================================================================
# C-4 — market_order_disallowed + NXT + 폴백 실패 → next_day_clear 등록 (Q2)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-03 16:00:00", tz_offset=-9)  # NXT 애프터
async def test_c4_when_nxt_fallback_failed_then_pending_next_day_clear_add(
    engine: OrderEngine,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
):
    """C-4 (Q2 핵심): NXT 시간대 market_order_disallowed 폴백 실패 →
    `_pending_next_day_clear_provider().add(ticker)` 호출 (다음 영업일 09:00 KRX 시장가 전환).
    """
    # scheduler 의 _pending_next_day_clear set 모의 — provider 주입
    next_day_set: set[str] = set()
    engine._pending_next_day_clear_provider = lambda: next_day_set

    from src.engine import scanner as _scanner
    _scanner.ticker_prices["064400"] = {"current_price": 10_000}
    try:
        mock_place_order.side_effect = [
            _market_disallow_err(),  # 시장가 거부
            _market_disallow_err(),  # 지정가 폴백도 거부 (NXT 야간)
        ]
        await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")
    finally:
        _scanner.ticker_prices.pop("064400", None)

    # Q2 핵심 검증 — 익일 청산 전환
    # scheduler 실제 _pending_next_day_clear 는 set[tuple[ticker, strategy_id]] 이므로
    # add((ticker, strategy_id)) 형태로 등록됨. 단순 ticker 문자열 포함 여부 확인.
    assert any(
        entry == "064400" or (isinstance(entry, tuple) and len(entry) >= 1 and entry[0] == "064400")
        for entry in next_day_set
    ), (
        "사이클 55 R-1 Q2 핵심: NXT 폴백 실패 시 _pending_next_day_clear.add 누락 "
        f"(next_day_set={next_day_set})"
    )
    # 30초 TTL 동일 등록 (동일 tick 폭주 차단)
    assert "064400" in engine._sell_rejection._blocked_until


# ===========================================================================
# C-5 — insufficient_quantity: tracker 적재 + reconciliation 로그 + get_balance
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-03 10:00:00", tz_offset=-9)
async def test_c5_when_insufficient_qty_then_reconciliation_log_and_balance_inquiry(
    engine: OrderEngine,
    registry: StrategyRegistry,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_delete_position: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
    mock_get_balance: AsyncMock,
):
    """C-5 (Q3): insufficient_quantity 거부 → (1) tracker.register_insufficient_quantity 호출
    (2) [positions_reconciliation] INFO 로그 (3) get_balance() 1회 호출 (4) positions 정리.
    """
    mock_place_order.side_effect = [_insufficient_qty_err()]
    strategy = registry.get("momentum")

    await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")

    # (1) tracker history 등록 — Q3 도메인 자문
    history = engine._sell_rejection.get_recent_rejections("064400")
    assert len(history) == 1, (
        "사이클 55 R-1 Q3: insufficient_quantity history 적재 누락"
    )
    assert history[0].reason == "insufficient_quantity"

    # (2) [positions_reconciliation] 로그
    recon_calls = [
        c for c in mock_write_log.await_args_list
        if len(c.args) >= 2 and "[positions_reconciliation]" in str(c.args[1])
    ]
    assert len(recon_calls) >= 1, (
        "사이클 55 R-1 Q3: [positions_reconciliation] 로그 미발화"
    )

    # (3) get_balance() 1회 호출
    assert mock_get_balance.await_count >= 1, (
        "사이클 55 R-1 Q3: get_balance() reconciliation 호출 누락"
    )

    # (4) 기존 동작 보존 — positions 메모리 정리
    assert "064400" not in strategy.state.positions, (
        "기존 동작 회귀 — insufficient_quantity 후 positions 정리 누락"
    )

    # tracker 는 차단 X (Q3 도메인 자문)
    assert "064400" not in engine._sell_rejection._blocked_until, (
        "Q3: insufficient_quantity 가 차단 set 등록 — positions 제거가 자연 차단인데 중복"
    )


# ===========================================================================
# C-6 — reset_daily_state 위임 체인
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-03 11:00:00", tz_offset=-9)
async def test_c6_when_reset_daily_state_then_tracker_reset_daily_chain(
    engine: OrderEngine,
):
    """C-6: OrderEngine.reset_daily_state() → SellRejectionTracker.reset_daily() 위임 체인.

    사이클 48 stale_tracker 패턴 답습.
    """
    now_kst = datetime.now(KST_TZ)
    engine._sell_rejection.register_market_closed(
        "064400", now_kst, in_krx_main_hours=True
    )
    engine._sell_rejection.register_insufficient_quantity("005930", now_kst)
    engine._sell_rejection.mark_block_logged("064400")
    engine._sell_rejection.record_rejection(
        "064400", "market_closed", "X", "msg", now_kst
    )

    # 사전 상태 확인
    assert engine._sell_rejection._blocked_until, "사전 상태 누락 — 테스트 결함"
    assert engine._sell_rejection._logged_today, "사전 상태 누락 — 테스트 결함"
    assert engine._sell_rejection._history, "사전 상태 누락 — 테스트 결함"

    # OrderEngine.reset_daily_state() 위임 호출
    engine.reset_daily_state()

    # 4 필드 모두 빈 상태
    assert engine._sell_rejection._blocked_until == {}, "tracker._blocked_until clear 누락"
    assert engine._sell_rejection._blocked_reason == {}, "tracker._blocked_reason clear 누락"
    assert engine._sell_rejection._logged_today == set(), "tracker._logged_today clear 누락"
    assert engine._sell_rejection._history == {}, "tracker._history clear 누락"


# ===========================================================================
# C-7 — 호환 property 위임 (is 동일성)
# ===========================================================================
def test_c7_compat_layer_property_is_identity_preserved(engine: OrderEngine):
    """C-7: engine._market_closed_blocked 가 tracker._blocked_until 동일 객체 (is 동일성).

    사이클 48 stale_tracker S-6 패턴 답습 — 호환 layer 가 매 접근마다 동일 dict 반환.
    """
    d1 = engine._market_closed_blocked
    d2 = engine._market_closed_blocked
    assert d1 is d2, "호환 layer 가 매번 새 dict 반환 — race 위험"
    assert d1 is engine._sell_rejection._blocked_until, (
        "engine._market_closed_blocked 가 tracker._blocked_until 와 동일 인스턴스 아님"
    )

    s1 = engine._market_closed_blocked_logged_today
    s2 = engine._market_closed_blocked_logged_today
    assert s1 is s2
    assert s1 is engine._sell_rejection._logged_today, (
        "engine._market_closed_blocked_logged_today 가 tracker._logged_today 동일 인스턴스 아님"
    )


# ===========================================================================
# C-8 — 사이클 30 _completed_orders race 가드 무영향
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-03 10:00:00", tz_offset=-9)
async def test_c8_when_completed_orders_race_then_pending_insert_skipped(
    engine: OrderEngine,
    mock_insert_trade: AsyncMock,
    mock_place_order: AsyncMock,
    mock_write_log: AsyncMock,
    mock_strategy_exchange,
    mock_stock_master,
):
    """C-8: 사이클 30 _completed_orders race 가드 — 체결통보 선행 시 PENDING insert 생략.

    사이클 55 R-1 tracker 도입 후에도 무영향 (별 영역) 확인.
    """
    order_no = "ORDER-RACE-1"
    # 체결통보 선행 시뮬레이션
    engine._completed_orders.add(order_no)
    mock_place_order.side_effect = [_success(order_no)]

    await engine.execute_sell("064400", Signal.STOP_LOSS, "momentum")

    # 사이클 30 가드 — PENDING insert 생략, _completed_orders 정리
    assert order_no not in engine._completed_orders, (
        "_completed_orders 정리 누락 — 사이클 30 race 가드 회귀"
    )
    # insert_trade 호출 없어야 함 (이미 COMPLETED INSERT 됨)
    assert mock_insert_trade.await_count == 0, (
        "_completed_orders race 가드 회귀 — PENDING insert 발생"
    )
