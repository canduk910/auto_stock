"""cycle295 (D) 축 — 손절 잔여 재주문의 **주문번호 매핑** 행위 증언.

정본 = `_workspace/red/cycle295_gap_hold_removal_spec.md` §2-0b.
짝 가드 = `tests/unit/ast/test_cycle295_ast_market_rest.py::test_c4_*`(**구조**만
잰다 — "값을 받는가"). 이 파일은 **무엇을 등록하는가**를 잰다. 둘 다 있어야
「받아서 버리는」 구현이 막힌다 — 그 docstring 이 이 파일 이름을 이미 인용하고
있었는데 파일이 없었다(착지 직후 적대 검증 HIGH, 뮤테이션 11종 ESCAPED).

═══════════════════════════════════════════════════════════════════════════
왜 개수 가드로는 부족한가
═══════════════════════════════════════════════════════════════════════════
남아 있던 유일한 방어선 `tests/unit/ast/test_cycle291_ast_scope.py::test_a10c`
는 `src.count("self._order_exchange[") == 5` 같은 **개수**만 잰다. 다섯 자리를
그대로 둔 채 값·키를 오염시키면 전부 통과한다 — 실측으로 다음이 전부 초록이었다:

  · `_order_qty[new] = 0`                      (부분체결이 전량체결로 읽힌다)
  · `_order_strategy[new] = "momentum"` 하드코딩 (오귀속)
  · `_order_exchange[new] = "KRX"` 하드코딩      (취소가 다른 거래소로 샌다)
  · `_order_ticker[원주문 order_no] = ticker`    (신규 주문번호는 영영 미매핑)
  · `_completed_orders.discard` → `add`         (체결통보 race 가드 반전)
  · `if result … and False:`                    (고침 자체를 통째로 끔)

⇒ 이 파일은 **값과 키를 각각** 단언한다. 전략 id 는 `"momentum"` 이 아닌 값,
거래소는 `"KRX"` 가 아닌 값, 신규 주문번호는 원주문과 다른 값으로 리그를 짜야
위 뮤테이션들이 실제로 죽는다.

═══════════════════════════════════════════════════════════════════════════
실害 (§2-0b)
═══════════════════════════════════════════════════════════════════════════
매핑이 비면 재주문의 체결통보가 `_order_strategy` miss → `trade_history` miss →
`"momentum"` 오귀속으로 흐르고, `_order_qty` 부재로 부분체결이 전량체결로 읽힌다.
발화 조건은 «손절 주문이 부분체결되는 것» 하나뿐이라 오늘 라이브에 도달 가능하다.

⚠️ 시각은 전부 **컷 창(15:30~16:00) 밖**으로 잡는다 — 창 안이면 (B) 쌍 게이트가
`cancel_order` 앞에서 먼저 return 해 이 경로에 도달하지 못한다.
🔴 모든 날짜는 **2026-09-14 이상**(K6 `effective_from`).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import (
    Position,
    Signal,
    StrategyBase,
    StrategyConfig,
)
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

KST_TZ = timezone(timedelta(hours=9))
_OE_LOGGER = "src.engine.order_engine"

_TICKER = "161580"
#: 🔴 `"momentum"` 이 **아니어야** 한다 — `_order_strategy` 폴백 하드코딩과
#: 진짜 등록을 구별하는 유일한 수단이다.
_SID = "long_tail_volatility"
#: 🔴 원주문 ↔ 신규 주문 번호는 **달라야** 한다 — 키 오염(원주문 번호로 등록)을
#: 구별하는 유일한 수단이다.
_ORIG_NO = "ORD-PARTIAL-0001"
_NEW_NO = "ORD-REORDER-9999"
_REMAINING = 7

_DAY = date(2026, 9, 15)
# freezegun 은 naive 문자열을 UTC 로 동결한다. KST = UTC + 9h.
_F_1100 = "2026-09-15 02:00:00"  # KST 11:00 — 정규장(컷 밖)
_F_1605 = "2026-09-15 07:05:00"  # KST 16:05 — KRX 애프터마켓(컷 밖)


class _DummyStrategy(StrategyBase):
    def __init__(self) -> None:
        super().__init__(
            StrategyConfig(
                strategy_id=_SID,
                name="ltv-dummy",
                enabled=True,
                weight=1.0,
                params={"exchange": "SOR"},
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
        return 1


def _make_engine():
    reg = StrategyRegistry()
    strat = _DummyStrategy()
    strat.state.positions[_TICKER] = Position(
        ticker=_TICKER,
        buy_price=10_000,
        quantity=10,
        order_no=_ORIG_NO,
        strategy_id=_SID,
        buy_date=date(2026, 9, 11),
    )
    reg.register(strat)
    return OrderEngine(reg), strat


@pytest.fixture
def mock_place_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock()
    mock.return_value = SimpleNamespace(
        order_no=_NEW_NO, order_time="160500", krx_org_no="",
    )
    monkeypatch.setattr(_oe, "place_order", mock)
    return mock


@pytest.fixture
def mock_cancel_order(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.engine.order_engine as _oe

    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(_oe, "cancel_order", mock)
    return mock


@pytest.fixture(autouse=True)
def _rig(monkeypatch: pytest.MonkeyPatch):
    """DB·LLM·시세 격리 + 보드 캐시 비움. `PARTIAL_FILL_WAIT` 는 0."""
    import src.engine.order_engine as _oe
    import src.db.stock_master as _sm
    import src.engine.scanner as _scanner
    from src.engine.session import session_tracker

    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "safe_write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "update_trade_status", AsyncMock(return_value=1))
    monkeypatch.setattr(_oe.llm_buy_gate, "observe_order", lambda **kw: None)
    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "upsert_one", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0)
    monkeypatch.setattr(_scanner, "ticker_prices", {_TICKER: {"current_price": 35_000}})
    monkeypatch.setattr(_scanner, "ticker_last_tick", {})
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    return None


# ═══════════════════════ D1 — 매핑 4종 + discard (정규장) ═══════════════════
@pytest.mark.asyncio
@freeze_time(_F_1100)
async def test_d1_reorder_registers_every_mapping_with_live_values(
    mock_place_order: AsyncMock, mock_cancel_order: AsyncMock,
) -> None:
    """🔴 D1 (§2-0b) — 재주문 주문번호에 매핑 4종이 **실제 값으로** 붙는다.

    각 단언이 죽이는 뮤테이션을 옆에 적는다. 하나라도 빠지면 그 뮤테이션이
    다시 살아난다.
    """
    engine, strat = _make_engine()
    engine._order_strategy[_ORIG_NO] = _SID
    engine._order_exchange[_ORIG_NO] = "NXT"  # 🔴 "KRX" 가 아니어야 한다
    # 체결통보 선행 race 가드가 원주문 번호를 남겨 둔 상태를 재현한다.
    engine._completed_orders.add(_NEW_NO)

    await engine._cancel_and_reorder(
        _TICKER, _ORIG_NO, _REMAINING, is_stop_loss=True,
    )

    assert mock_cancel_order.await_count == 1, "취소가 나가지 않았다"
    assert mock_place_order.await_count == 1, "잔여 재주문이 나가지 않았다"

    # (a) 수량 — 부재/0 이면 부분체결이 전량체결로 읽힌다 (M17 · M32)
    assert engine._order_qty.get(_NEW_NO) == _REMAINING, (
        f"`_order_qty[{_NEW_NO}]` = {engine._order_qty.get(_NEW_NO)} — "
        f"{_REMAINING} 이어야 한다. 부재·0 이면 부분체결이 전량체결로 읽힌다"
    )
    # (b) 전략 — 부재면 `"momentum"` 폴백 오귀속 (M18 · M33)
    assert engine._order_strategy.get(_NEW_NO) == _SID, (
        f"`_order_strategy[{_NEW_NO}]` = {engine._order_strategy.get(_NEW_NO)} — "
        f"원주문 전략 {_SID!r} 이어야 한다. `\"momentum\"` 이면 하드코딩이거나 "
        "미등록(체결통보가 폴백으로 흐른다)"
    )
    assert engine._order_strategy.get(_NEW_NO) != "momentum"
    # (c) 종목 — 키가 원주문 번호면 신규 주문은 영영 미매핑 (M19 · M35)
    assert engine._order_ticker.get(_NEW_NO) == _TICKER, (
        f"`_order_ticker[{_NEW_NO}]` 미등록 — 키는 **신규** 주문번호다"
    )
    # (d) 거래소 — 원주문의 실제 거래소. 라우터 재평가값·하드코딩 금지 (M34)
    assert engine._order_exchange.get(_NEW_NO) == "NXT", (
        f"`_order_exchange[{_NEW_NO}]` = {engine._order_exchange.get(_NEW_NO)} — "
        "원주문 거래소 'NXT' 여야 한다. 'KRX' 면 하드코딩이고, 그 값으로 취소가 "
        "나가면 원주문과 다른 거래소로 샌다(cycle287 적대 검증)"
    )
    # (e) 체결통보 선행 race 가드 — discard 여야 한다. `add` 는 의미가 반대다 (M22 · M36)
    assert _NEW_NO not in engine._completed_orders, (
        "`_completed_orders` 에 신규 주문번호가 남았다 — `discard` 가 아니라 "
        "`add` 이거나 미호출이다. 자매 4곳과 같은 모양이어야 한다"
    )


# ═══════════════════ D2 — 호가유형(`_order_division`) (KRX 애프터) ═══════════
@pytest.mark.asyncio
@freeze_time(_F_1605)
async def test_d2_reorder_registers_the_after_market_division(
    mock_place_order: AsyncMock, mock_cancel_order: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 D2 (§2-0b · cycle287 §4-C3) — 애프터 창 재주문은 `_order_division` 도 등록한다.

    `reorder_division is not None` 인 경로는 KRX 애프터마켓(16:00~20:00)
    ∧ `settings.is_production` 에서만 성립한다. 그 자리가 미실행이면
    (커버리지 실측: L2754) 등록 삭제 뮤테이션이 조용히 통과한다.
    """
    from src.config import settings

    monkeypatch.setattr(settings, "kis_env", "real")

    engine, strat = _make_engine()
    engine._order_strategy[_ORIG_NO] = _SID
    engine._order_exchange[_ORIG_NO] = "KRX"  # 애프터 변환은 KRX 에서만

    await engine._cancel_and_reorder(
        _TICKER, _ORIG_NO, _REMAINING, is_stop_loss=True,
    )

    assert mock_place_order.await_count == 1
    kwargs = mock_place_order.await_args.kwargs
    assert "order_division" in kwargs, (
        "애프터 창인데 호가유형 변환이 없다 — 시장가는 그 창에서 100% 거부된다"
    )
    sent = kwargs["order_division"]
    assert engine._order_division.get(_NEW_NO) == sent.value, (
        f"`_order_division[{_NEW_NO}]` = {engine._order_division.get(_NEW_NO)} — "
        f"실제로 보낸 호가유형 {sent.value!r} 이어야 한다(취소 경로가 이 값을 읽는다)"
    )
    # 자매 매핑도 함께 살아 있어야 한다
    assert engine._order_qty.get(_NEW_NO) == _REMAINING
    assert engine._order_strategy.get(_NEW_NO) == _SID
    assert engine._order_ticker.get(_NEW_NO) == _TICKER
    assert engine._order_exchange.get(_NEW_NO) == "KRX"


# ═════════ D3 — 「고침 자체를 끄는」 뮤테이션 봉인 (M45 · M23b) ═════════════
@pytest.mark.asyncio
@freeze_time(_F_1100)
async def test_d3_mapping_is_not_optional(
    mock_place_order: AsyncMock, mock_cancel_order: AsyncMock,
) -> None:
    """🔴 D3 — 재주문이 나갔는데 매핑이 **하나도** 없으면 붉어진다.

    `if result is not None and getattr(result, "order_no", None) and False:` 처럼
    구조·개수를 전부 보존한 채 등록만 통째로 끄는 뮤테이션이 실측으로 통과했다
    (565 tests 전부 초록). 이 단언이 그 구멍을 닫는다.
    """
    engine, strat = _make_engine()
    engine._order_strategy[_ORIG_NO] = _SID
    engine._order_exchange[_ORIG_NO] = "NXT"

    await engine._cancel_and_reorder(
        _TICKER, _ORIG_NO, _REMAINING, is_stop_loss=True,
    )

    assert mock_place_order.await_count == 1
    registered = {
        "_order_qty": _NEW_NO in engine._order_qty,
        "_order_strategy": _NEW_NO in engine._order_strategy,
        "_order_ticker": _NEW_NO in engine._order_ticker,
        "_order_exchange": _NEW_NO in engine._order_exchange,
    }
    missing = [k for k, ok in registered.items() if not ok]
    assert not missing, (
        f"재주문이 나갔는데 매핑 {missing} 이 비었다 — 체결통보가 전략·수량을 "
        "모르는 채 도착한다(§2-0b)"
    )


# ════════════ D4 — 🔵 양성 대조군: 재주문이 없으면 매핑도 없다 ═════════════
@pytest.mark.asyncio
@freeze_time(_F_1100)
async def test_d4_no_reorder_means_no_mapping(
    mock_place_order: AsyncMock, mock_cancel_order: AsyncMock,
) -> None:
    """🔵 D4 (양성 대조군) — `is_stop_loss=False` 면 취소만 하고 재주문은 없다.

    D1~D3 의 부정 단언이 "무조건 등록한다" 는 퇴화 구현으로도 만족되지 않게
    한다. 취소는 나가되 `place_order` 는 0건이고 매핑도 생기지 않는다.
    """
    engine, strat = _make_engine()
    engine._order_strategy[_ORIG_NO] = _SID
    engine._order_exchange[_ORIG_NO] = "NXT"

    await engine._cancel_and_reorder(
        _TICKER, _ORIG_NO, _REMAINING, is_stop_loss=False,
    )

    assert mock_cancel_order.await_count == 1, "순수 취소 경로가 막혔다"
    assert mock_place_order.await_count == 0, "손절이 아닌데 재주문이 나갔다"
    assert _NEW_NO not in engine._order_qty
    assert _NEW_NO not in engine._order_strategy
    assert _NEW_NO not in engine._order_ticker
    assert _NEW_NO not in engine._order_exchange


# ═══════════ D5 — 컷 창 안에서는 이 경로에 도달조차 하지 않는다 ═════════════
@pytest.mark.asyncio
@freeze_time("2026-09-15 06:45:30")  # KST 15:45:30 — 컷 한가운데
async def test_d5_rest_window_gates_the_pair_before_any_mapping(
    mock_place_order: AsyncMock, mock_cancel_order: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """🔵 D5 — (B) 쌍 게이트와의 경계. 컷 창이면 취소도 재주문도 매핑도 0.

    (D) 의 단언들이 (B) 를 무력화하는 방향으로 되살아나지 않게 고정한다.
    """
    engine, strat = _make_engine()
    engine._order_strategy[_ORIG_NO] = _SID
    engine._order_exchange[_ORIG_NO] = "NXT"

    with caplog.at_level(logging.INFO, logger=_OE_LOGGER):
        await engine._cancel_and_reorder(
            _TICKER, _ORIG_NO, _REMAINING, is_stop_loss=True,
        )

    assert mock_cancel_order.await_count == 0
    assert mock_place_order.await_count == 0
    assert _NEW_NO not in engine._order_qty
    blocked = [
        r.getMessage() for r in caplog.records
        if r.name == _OE_LOGGER and r.levelno >= logging.WARNING
        and r.getMessage().startswith("[market_rest_blocked]")
    ]
    assert len(blocked) == 1, f"분모 마커가 {len(blocked)}행: {blocked}"
    assert "base=NXT" in blocked[0], (
        f"`base=` 가 원주문 거래소를 싣지 않았다: {blocked[0]}"
    )
