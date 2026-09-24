"""cycle358 카드 D (관측 전용) — PARTIAL/CANCELLED UPDATE `affected==0` 무흔적 시정.

명세 = `_workspace/domain_consult/cycle335_buy_post_send_boundary.md` §5 카드 D.
사용자 승인 = 워크리스트 ⑨(2026-09-25, 8영역 `order_engine.py` 관측 로그 승인).

`update_trade_status`(`src/db/trade_history.py`) 는 이미 영향 행 수(`affected`)를
반환한다. COMPLETED 는 `affected==0` 시 보정 INSERT/강제 UPDATE 로 스스로 흡수하지만,
PARTIAL·CANCELLED 는 그런 흡수 경로가 없어 장부 행이 없으면 부분체결·취소가 한
글자도 안 남았다 — 이 사이클은 `[trade_status_update_miss]` WARNING 1줄만 추가한다
(매매·주문·상태전이 로직 무변경 — 분기·반환값·예외 흐름 byte 동일).

4 호출부:
  - BUY  PARTIAL   — `OrderEngine._handle_buy_fill`
  - SELL PARTIAL   — `OrderEngine._handle_sell_fill`
  - BUY  CANCELLED — `OrderEngine._cancel_after_wait`
  - SELL CANCELLED — `OrderEngine._cancel_and_reorder`

각 호출부에 3 계약을 판다:
  1. `affected==0` → `[trade_status_update_miss]` WARNING 정확히 1줄
  2. `affected>=1` → 그 WARNING 무발화
  3. `logger.warning` 자체가 예외를 던져도 호출부의 흐름(완료 로그까지)이 끊기지 않는다
     (관측 emit 은 예외 흡수, 행위는 cap 밖 — 기존 규약과 동일)

PARTIAL 두 곳은 `qty_src="payload"` 로 호출해 잔량 취소/재주문 타이머 스케줄을
피한다(백그라운드 task 오염 차단) — `affected==0` 판정은 그 분기보다 **먼저** 있어
어느 qty_src 를 줘도 관측 대상 코드는 동일하게 실행된다.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.unit

TICKER = "004990"
STRATEGY_ID = "kojiro"
MARKER = "[trade_status_update_miss]"


class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id: str = STRATEGY_ID) -> None:
        super().__init__(
            StrategyConfig(
                strategy_id=strategy_id, name=strategy_id, enabled=True, weight=1.0,
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
    reg.register(_DummyStrategy())
    return reg


@pytest.fixture(autouse=True)
def _rig(monkeypatch: pytest.MonkeyPatch):
    """DB·주문 I/O 격리.

    `_cancel_and_reorder` 의 §3-5③ 15:30~16:00 휴식 컷 게이트는 이 사이클의
    관심사 밖이다 — 루트 `conftest.py::_neutralize_market_rest` 가 전 스위트에
    autouse 로 `_market_rest_now` 를 무장 해제해 두므로 여기서 따로 손대지
    않는다(손대면 `test_cycle317_market_rest_clock_pin.py` 의 옵트아웃 의무
    가드에 걸린다).
    """
    import src.db.positions as _positions
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "safe_write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "cancel_order", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "place_order", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0)
    monkeypatch.setattr(_positions, "save_position", AsyncMock(return_value=None))
    monkeypatch.setattr(_positions, "delete_position", AsyncMock(return_value=None))


@pytest.fixture
def engine(registry: StrategyRegistry) -> OrderEngine:
    eng = OrderEngine(registry)
    eng._unsubscribe_if_no_other_strategy = AsyncMock(return_value=None)
    yield eng
    # `_schedule_cancel*` 를 거치지 않는 직접 호출뿐이라 보통 비어 있지만,
    # 다른 테스트와의 상호오염을 막기 위해 관례대로 정리한다.
    for task in list(eng._pending_cancel_tasks.values()):
        task.cancel()
    eng._pending_cancel_tasks.clear()


def _warn_lines(caplog: pytest.LogCaptureFixture, prefix: str = MARKER) -> list[str]:
    """caplog 단언은 WARNING 이상 + prefix 로 한정한다(CI 루트 로거 DEBUG)."""
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(prefix)
    ]


def _has_message(caplog: pytest.LogCaptureFixture, substr: str) -> bool:
    return any(substr in r.getMessage() for r in caplog.records)


# ─────────────────────────── 4 호출부 invoke 어댑터 ─────────────────────────

async def _invoke_buy_partial(engine: OrderEngine, order_no: str) -> None:
    engine._order_strategy[order_no] = STRATEGY_ID
    # qty_src="payload" — `_schedule_cancel` 스케줄을 피한다(관측 코드는 그 분기보다 앞).
    await engine._handle_buy_fill(TICKER, order_no, 10_000, 3, 3, 5, qty_src="payload")


async def _invoke_sell_partial(engine: OrderEngine, order_no: str) -> None:
    engine._order_strategy[order_no] = STRATEGY_ID
    await engine._handle_sell_fill(TICKER, order_no, 10_000, 3, 3, 5, qty_src="payload")


async def _invoke_buy_cancelled(engine: OrderEngine, order_no: str) -> None:
    engine._order_exchange[order_no] = "KRX"
    await engine._cancel_after_wait(TICKER, order_no, STRATEGY_ID)


async def _invoke_sell_cancelled(engine: OrderEngine, order_no: str) -> None:
    engine._order_exchange[order_no] = "KRX"
    engine._order_strategy[order_no] = STRATEGY_ID
    await engine._cancel_and_reorder(TICKER, order_no, 2, is_stop_loss=False)


# (invoke, status, side, 정상 완료를 증언하는 INFO 부분문자열)
_SITES = {
    "buy_partial": (
        _invoke_buy_partial, TradeStatus.PARTIAL.value, TradeType.BUY.value,
        "매수 부분 체결:",
    ),
    "sell_partial": (
        _invoke_sell_partial, TradeStatus.PARTIAL.value, TradeType.SELL.value,
        "매도 부분 체결:",
    ),
    "buy_cancelled": (
        _invoke_buy_cancelled, TradeStatus.CANCELLED.value, TradeType.BUY.value,
        "부분 체결 잔여 취소:",
    ),
    "sell_cancelled": (
        _invoke_sell_cancelled, TradeStatus.CANCELLED.value, TradeType.SELL.value,
        "매도 잔여 취소:",
    ),
}


# ═══════════════════════════ 계약 1 — affected==0 ═══════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("site", sorted(_SITES))
async def test_affected_zero_emits_warning_once(
    site: str, engine: OrderEngine, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import src.engine.order_engine as _oe

    invoke, status, side, _completion = _SITES[site]
    order_no = f"ORD-{site}-Z"
    monkeypatch.setattr(_oe, "update_trade_status", AsyncMock(return_value=0))
    caplog.set_level(logging.WARNING)

    await invoke(engine, order_no)

    lines = _warn_lines(caplog)
    assert len(lines) == 1, f"{site}: 기대 1줄, 실측 {lines}"
    line = lines[0]
    assert line.startswith(MARKER), line
    assert f"status={status}" in line, line
    assert f"order_no={order_no}" in line, line
    assert f"side={side}" in line, line
    assert TICKER in line, line


# ═══════════════════════════ 계약 2 — affected>=1 (무로그) ══════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("site", sorted(_SITES))
async def test_affected_nonzero_emits_no_warning(
    site: str, engine: OrderEngine, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import src.engine.order_engine as _oe

    invoke, _status, _side, _completion = _SITES[site]
    order_no = f"ORD-{site}-N"
    monkeypatch.setattr(_oe, "update_trade_status", AsyncMock(return_value=1))
    caplog.set_level(logging.WARNING)

    await invoke(engine, order_no)

    assert _warn_lines(caplog) == [], f"{site}: affected>=1 인데 관측 WARNING 이 발화했다"


# ═══════════════════ 계약 3 — 로그 예외가 흐름을 안 끊는다 ═══════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("site", sorted(_SITES))
async def test_logger_failure_does_not_break_flow(
    site: str, engine: OrderEngine, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import src.engine.order_engine as _oe

    invoke, _status, _side, completion = _SITES[site]
    order_no = f"ORD-{site}-E"
    monkeypatch.setattr(_oe, "update_trade_status", AsyncMock(return_value=0))

    original_warning = _oe.logger.warning

    def _boom(msg, *args, **kwargs):
        if isinstance(msg, str) and msg.startswith(MARKER):
            raise RuntimeError("[test] trade_status_update_miss 로그 자체 실패")
        return original_warning(msg, *args, **kwargs)

    monkeypatch.setattr(_oe.logger, "warning", _boom)
    caplog.set_level(logging.DEBUG)

    # 여기서 raise 되면(=예외가 전파되면) 이 await 자체가 테스트를 실패시킨다.
    await invoke(engine, order_no)

    # 예외가 다른 곳(예: `_cancel_after_wait`/`_cancel_and_reorder` 의 바깥
    # `except Exception: logger.exception(...)`)에 조용히 먹혀 정상 완료 로그가
    # 안 찍히는 것도 같은 결함이다 — 완료 로그가 실제로 찍혔는지까지 본다.
    assert _has_message(caplog, completion), (
        f"{site}: 로그 실패 후 완료 로그({completion!r})가 없다 — 흐름이 끊겼거나 "
        "예외가 더 바깥에서 조용히 흡수됐다"
    )
    assert not _has_message(caplog, "잔여 취소 실패") and not _has_message(
        caplog, "잔여 취소/재주문 실패",
    ), f"{site}: 예외가 바깥 except 로 전파돼 '실패' 로그로 흡수됐다"


# ═══════════════════════ 계약 4(부가) — 1회/(order_no,status)/일 cap ════════

@pytest.mark.asyncio
@pytest.mark.parametrize("site", sorted(_SITES))
async def test_affected_zero_dedupes_within_same_order_no(
    site: str, engine: OrderEngine, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """같은 (order_no, status) 로 두 번 affected==0 이 나도 WARNING 은 1줄뿐이다."""
    import src.engine.order_engine as _oe

    invoke, _status, _side, _completion = _SITES[site]
    order_no = f"ORD-{site}-DUP"
    monkeypatch.setattr(_oe, "update_trade_status", AsyncMock(return_value=0))
    caplog.set_level(logging.WARNING)

    await invoke(engine, order_no)
    await invoke(engine, order_no)

    assert len(_warn_lines(caplog)) == 1, "같은 (order_no, status) 인데 두 번 emit 됐다"
