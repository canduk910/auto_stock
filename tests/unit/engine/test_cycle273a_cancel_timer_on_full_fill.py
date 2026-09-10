# DEST: tests/unit/engine/test_cycle273a_cancel_timer_on_full_fill.py
"""cycle273a Red — D2(가)-a: 전량 체결이 잔여취소 30초 타이머를 해제한다.

명세 = `_workspace/red/cycle273a_c235v2_cancel_timer_and_partial_spec.md`
정본 = `_workspace/analysis/2026-09-10_cycle273_UA_order_engine.md` §1·§3.1
사고 = 09-10 09:05 `004990` (kojiro 3/5 부분체결 → 같은 초 5/5 전량체결 →
30초 뒤 `cancel_order` 가 잔량 0 인 주문을 취소하려다 KIS APBK0927 거부,
`system_logs` ERROR 3행). 발화 하한 2회(08-28 `257720` · 09-10 `004990`).

## HEAD 기준 RED / GREEN

| 테스트 | HEAD | 이유 |
|---|---|---|
| `test_a1_full_fill_cancels_pending_timer_for_same_order` | **RED** | 전량 체결 분기(`order_engine.py:1262-1360`)에 `_pending_cancel_tasks` 참조 0건 |
| `test_a1b_sell_full_fill_cancels_pending_timer` | **RED** | 매도 전량 체결 분기(`:1433-1498`)도 동일 |
| `test_a2_other_order_timer_survives_full_fill` | GREEN(계약 가드) | §1.4 — 키가 ticker 라 `pop(ticker)` 로 고치면 깨진다 |
| `test_a3_buy_timer_survives_sell_full_fill_on_same_ticker` | GREEN(계약 가드) | 매수·매도가 같은 dict 를 공유(§1.4) |
| `test_a4_cancelled_timer_task_terminates_without_leaking` | **RED** | 오늘은 task 가 30초 sleep 을 계속한다 |
| `test_a5_cancel_replace_then_full_fill_releases_new_timer` | GREEN(회귀 가드) | 직전 검증 HIGH#2 — 뮤테이션 M18(finally 의 shadow pop 을 identity 가드 밖으로) 이 ESCAPED 였다. 짝 dict(`_pending_cancel_tasks`/`_pending_cancel_order_no`) 불변식을 직접 잰다 |
| `test_a6_timer_cleared_marker_emitted_once_per_axis` | GREEN(회귀 가드) | 직전 검증 MEDIUM — 뮤테이션 M17(`[partial_cancel_timer_cleared]` 마커 삭제) 이 ESCAPED 였다. 명세 O-A2 의 D+1 양성 대조 마커 |
| `test_a7_natural_expiry_clears_both_dicts` | GREEN(회귀 가드) | 직전 검증 LOW#4 — 뮤테이션 M8(두 `finally` 의 shadow pop 삭제) 이 ESCAPED 였다. 전량 체결 없이 자연 만료된 경우도 짝 dict 가 함께 빈다 |

## 왜 `pop(ticker)` 로 고치면 안 되는가 (A2·A3 이 지키는 것)

`_pending_cancel_tasks` 의 키는 **ticker** 이고(`order_engine.py:79`) 매수
(`_schedule_cancel`)·매도(`_schedule_cancel_and_reorder`)가 **같은 dict** 를 쓴다.
ticker 만 보고 지우면 매수 잔량 취소 타이머가 매도 전량 체결에 실종되어
미체결 잔량이 장 마감까지 남는다. ⇒ **해제는 "그 타이머가 이 order_no 의 것일 때만"**.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from unittest.mock import AsyncMock

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

TICKER = "004990"


class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id: str = "kojiro") -> None:
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
    reg.register(_DummyStrategy("kojiro"))
    return reg


@pytest.fixture
def mock_db(monkeypatch: pytest.MonkeyPatch):
    """DB·KIS 부작용 전면 격리 (이 파일은 타이머 생애만 잰다)."""
    import src.db.positions as _positions
    import src.engine.order_engine as _oe

    stubs = {
        "update_trade_status": AsyncMock(return_value=1),
        "insert_trade": AsyncMock(return_value=None),
        "cancel_order": AsyncMock(return_value={"rt_cd": "0"}),
        "place_order": AsyncMock(return_value={"rt_cd": "0"}),
        "write_log": AsyncMock(return_value=None),
        "safe_write_log": AsyncMock(return_value=None),
    }
    for name, stub in stubs.items():
        monkeypatch.setattr(_oe, name, stub, raising=False)
    monkeypatch.setattr(_positions, "save_position", AsyncMock(return_value=None))
    monkeypatch.setattr(_positions, "delete_position", AsyncMock(return_value=None))
    return stubs


@pytest.fixture
def engine(registry: StrategyRegistry, mock_db) -> OrderEngine:
    eng = OrderEngine(registry)
    # 매도 전량 체결 경로의 WS 정리 훅 — 이 파일 범위 밖
    eng._unsubscribe_if_no_other_strategy = AsyncMock(return_value=None)
    return eng


@pytest.fixture(autouse=True)
def _drain_timers(engine: OrderEngine):
    """남은 30초 타이머를 반드시 정리 — 'Task was destroyed' 경고 차단."""
    yield
    for task in list(engine._pending_cancel_tasks.values()):
        task.cancel()
    engine._pending_cancel_tasks.clear()


async def _buy_notice(engine: OrderEngine, order_no: str, qty: int, *, price: int = 24_800):
    await engine.handle_execution_notice(
        ticker=TICKER, order_no=order_no, side="BUY", price=price, quantity=qty,
    )


async def _sell_notice(engine: OrderEngine, order_no: str, qty: int, *, price: int = 24_800):
    await engine.handle_execution_notice(
        ticker=TICKER, order_no=order_no, side="SELL", price=price, quantity=qty,
    )


# ---------------------------------------------------------------------------
# G-273-A1 — 같은 order_no 전량 체결 → 그 타이머 해제 + cancel_order 미발화
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a1_full_fill_cancels_pending_timer_for_same_order(
    engine: OrderEngine, mock_db, monkeypatch: pytest.MonkeyPatch,
):
    """004990 재현 — 3/5 부분체결 직후 5/5 전량체결. RED (HEAD).

    HEAD 는 전량 체결 분기에서 `_pending_cancel_tasks` 를 손대지 않으므로
    30초 뒤 `cancel_order(order_no, 0, cancel_all=True)` 가 잔량 0 인 주문을
    취소하려다 APBK0927 로 거부된다.
    """
    import src.engine.order_engine as _oe
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0.02)

    order_no = "0000305100"
    engine._order_qty[order_no] = 5
    engine._order_strategy[order_no] = "kojiro"
    engine._order_ticker[order_no] = TICKER

    await _buy_notice(engine, order_no, 3)          # 3/5 → PARTIAL + 타이머 등록
    assert TICKER in engine._pending_cancel_tasks, "전제 실패 — 부분체결이 타이머를 만들지 않았다"

    await _buy_notice(engine, order_no, 2)          # 5/5 → 전량 체결

    assert engine._pending_cancel_tasks == {}, (
        "전량 체결이 같은 order_no 의 잔여취소 타이머를 해제하지 않았다 "
        "(C235-V2-a — 004990 09-10 09:05 재현)"
    )

    await asyncio.sleep(0.08)
    assert mock_db["cancel_order"].call_count == 0, (
        "이미 100% 체결된 주문에 cancel_order 가 발화했다 — KIS APBK0927 거부 경로"
    )


# ---------------------------------------------------------------------------
# G-273-A1b — 매도 축도 같은 계약 (`_schedule_cancel_and_reorder`)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a1b_sell_full_fill_cancels_pending_timer(
    engine: OrderEngine, registry: StrategyRegistry, mock_db, monkeypatch: pytest.MonkeyPatch,
):
    """매도 부분체결 → 같은 order_no 전량체결. RED (HEAD).

    ⚠️ 매도 쪽은 잠재 이빨이 더 크다 — `_cancel_and_reorder` 는 취소 성공 뒤
    **부분체결 시점에 고정된** `remaining` 주를 재주문한다(`:1545-1552`). 지금은
    `cancel_order` 가 APBK0927 로 던져 그 줄에 닿지 못할 뿐이며, "KIS 가 거부해
    주는 것" 이 유일한 중복매도 방어선이다.
    """
    import src.engine.order_engine as _oe
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0.02)

    strategy = registry.get("kojiro")
    strategy.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=24_000, quantity=5,
        order_no="B-1", strategy_id="kojiro",
    )

    order_no = "0000400100"
    engine._order_qty[order_no] = 5
    engine._order_strategy[order_no] = "kojiro"
    engine._order_ticker[order_no] = TICKER

    await _sell_notice(engine, order_no, 3)
    assert TICKER in engine._pending_cancel_tasks, "전제 실패 — 매도 부분체결이 타이머를 만들지 않았다"

    await _sell_notice(engine, order_no, 2)

    assert engine._pending_cancel_tasks == {}, (
        "매도 전량 체결이 잔여취소/재주문 타이머를 해제하지 않았다 (C235-V2-a 매도 축)"
    )

    await asyncio.sleep(0.08)
    assert mock_db["cancel_order"].call_count == 0
    assert mock_db["place_order"].call_count == 0, (
        "낡은 remaining 으로 중복 매도 재주문이 나갔다"
    )


# ---------------------------------------------------------------------------
# G-273-A2 — 다른 order_no 의 전량 체결은 남의 타이머를 건드리지 않는다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a2_other_order_timer_survives_full_fill(
    engine: OrderEngine, mock_db, monkeypatch: pytest.MonkeyPatch,
):
    """주문 A 부분체결 → **다른** 주문 B 전량체결 → A 타이머 생존. GREEN(계약 가드).

    `self._pending_cancel_tasks.pop(ticker).cancel()` 로 고치면 이 테스트가 깨진다
    (§1.4). 해제는 order_no 일치 게이트 뒤에서만 일어나야 한다.
    """
    import src.engine.order_engine as _oe
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 30)  # 만료 전 상태만 본다

    order_a = "0000305100"
    engine._order_qty[order_a] = 5
    engine._order_strategy[order_a] = "kojiro"
    engine._order_ticker[order_a] = TICKER
    await _buy_notice(engine, order_a, 3)
    task_a = engine._pending_cancel_tasks[TICKER]

    order_b = "0000305199"
    engine._order_qty[order_b] = 2
    engine._order_strategy[order_b] = "kojiro"
    engine._order_ticker[order_b] = TICKER
    await _buy_notice(engine, order_b, 2)           # B 전량 체결

    assert engine._pending_cancel_tasks.get(TICKER) is task_a, (
        "다른 주문의 전량 체결이 주문 A 의 잔여취소 타이머를 지웠다 — "
        "매수 잔량이 장 마감까지 미체결로 남는다(§1.4)"
    )
    assert not task_a.done()


# ---------------------------------------------------------------------------
# G-273-A3 — 매수 타이머는 같은 ticker 의 매도 전량 체결에 살아남는다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a3_buy_timer_survives_sell_full_fill_on_same_ticker(
    engine: OrderEngine, registry: StrategyRegistry, mock_db, monkeypatch: pytest.MonkeyPatch,
):
    """매수·매도가 `_pending_cancel_tasks` 를 공유한다는 사실의 가드. GREEN(계약 가드)."""
    import src.engine.order_engine as _oe
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 30)

    buy_order = "0000305100"
    engine._order_qty[buy_order] = 5
    engine._order_strategy[buy_order] = "kojiro"
    engine._order_ticker[buy_order] = TICKER
    await _buy_notice(engine, buy_order, 3)
    buy_task = engine._pending_cancel_tasks[TICKER]

    strategy = registry.get("kojiro")
    strategy.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=24_000, quantity=2,
        order_no=buy_order, strategy_id="kojiro",
    )
    sell_order = "0000400100"
    engine._order_qty[sell_order] = 2
    engine._order_strategy[sell_order] = "kojiro"
    engine._order_ticker[sell_order] = TICKER
    await _sell_notice(engine, sell_order, 2)       # 매도 전량 체결

    assert engine._pending_cancel_tasks.get(TICKER) is buy_task, (
        "매도 전량 체결이 매수 잔여취소 타이머를 실종시켰다 (같은 dict 공유, §1.4)"
    )


# ---------------------------------------------------------------------------
# G-273-A4 — 해제된 task 는 즉시 종료되고 CancelledError 를 밖으로 흘리지 않는다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a4_cancelled_timer_task_terminates_without_leaking(
    engine: OrderEngine, mock_db, monkeypatch: pytest.MonkeyPatch,
):
    """RED (HEAD) — 오늘은 task 가 30초 sleep 을 계속한다.

    `_cancel_after_wait` 는 이미 `except asyncio.CancelledError: pass`(`:1517-1518`)
    를 갖고 있으므로, `.cancel()` 은 예외를 밖으로 흘리지 않는다. 이 테스트는
    (a) 타이머가 실제로 **종료**됐고 (b) 그 종료가 조용했음을 함께 잰다 —
    `_pending_cancel_tasks` 가 비었다는 것만으로는 (a) 를 증명하지 못한다
    (dict 에서 빼기만 하고 task 를 살려 두면 30초 뒤 여전히 cancel_order 가 나간다).
    """
    import src.engine.order_engine as _oe
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 30)  # 만료로 끝나는 것이 아님을 보장

    order_no = "0000305100"
    engine._order_qty[order_no] = 5
    engine._order_strategy[order_no] = "kojiro"
    engine._order_ticker[order_no] = TICKER

    await _buy_notice(engine, order_no, 3)
    task = engine._pending_cancel_tasks[TICKER]

    await _buy_notice(engine, order_no, 2)          # 전량 체결

    for _ in range(20):
        if task.done():
            break
        await asyncio.sleep(0.01)

    assert task.done(), (
        "타이머 task 가 살아 있다 — dict 에서만 빼고 cancel() 하지 않으면 "
        "30초 뒤 그대로 cancel_order 가 나간다"
    )
    if not task.cancelled():
        assert task.exception() is None, "타이머 종료가 예외를 남겼다"
    assert mock_db["cancel_order"].call_count == 0


# ---------------------------------------------------------------------------
# G-273-A5 — 짝 dict 불변식: cancel-replace 로 교체된 새 타이머의 shadow 는
# 죽은 이전 task 의 finally 에 지워지지 않는다 (직전 검증 HIGH#2, 뮤테이션 M18)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a5_cancel_replace_then_full_fill_releases_new_timer(
    engine: OrderEngine, registry: StrategyRegistry, mock_db, monkeypatch: pytest.MonkeyPatch,
):
    """매수 타이머가 살아 있는 도중 같은 ticker 매도 부분체결이 그 타이머를
    cancel-replace 한 뒤, **새** 타이머(매도)의 order_no shadow 가 죽은 매수
    task 의 `finally` 에 지워지지 않아야 한다.

    `_pending_cancel_tasks`/`_pending_cancel_order_no` 는 항상 짝으로 갱신되는
    두 dict 다(§1.4). `finally` 의 identity 가드(`... is asyncio.current_task()`)가
    task pop 은 지키지만, shadow pop 을 그 가드 **밖**으로 옮겨도(뮤테이션 M18)
    이 사이클의 표적/회귀 82건은 전부 초록이었다 — 이 테스트가 그 빈틈을 닫는다.
    """
    import src.engine.order_engine as _oe
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0.05)

    buy_order = "BUY-X"
    engine._order_qty[buy_order] = 5
    engine._order_strategy[buy_order] = "kojiro"
    engine._order_ticker[buy_order] = TICKER
    await _buy_notice(engine, buy_order, 3)          # 3/5 → task_a(매수) 등록
    task_a = engine._pending_cancel_tasks[TICKER]

    # A 를 sleep 지점(body)까지 한 스텝 진행시킨다 — 이 줄이 없으면 A 는 첫 스텝
    # 전에 취소돼 `finally` 자체가 실행되지 않아 이 테스트가 공허해진다(실측 확인).
    await asyncio.sleep(0)
    assert not task_a.done(), "전제 실패 — task_a 가 body 진입 전에 이미 끝났다"

    strategy = registry.get("kojiro")
    strategy.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=24_000, quantity=3, order_no=buy_order, strategy_id="kojiro",
    )

    sell_order = "SELL-Y"
    engine._order_qty[sell_order] = 5
    engine._order_strategy[sell_order] = "kojiro"
    engine._order_ticker[sell_order] = TICKER
    await _sell_notice(engine, sell_order, 3)        # 3/5 → task_a cancel-replace → task_b(매도) 등록

    task_b = engine._pending_cancel_tasks[TICKER]
    assert task_b is not task_a

    # task_a 의 finally 를 소진시킨다(취소 스케줄 → 실제 실행까지 두 스텝 필요).
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert engine._pending_cancel_order_no[TICKER] == sell_order, (
        "죽은 매수 task 의 finally 가 새(매도) 타이머의 shadow 를 지웠다 — "
        "다음 전량 체결이 order_no 게이트를 통과하지 못해 30초 뒤 cancel_order 가 나간다"
    )

    await _sell_notice(engine, sell_order, 2)        # 5/5 → 매도 전량 체결

    assert engine._pending_cancel_tasks == {}, "짝 dict 가 어긋나 새 타이머가 해제되지 않았다"

    await asyncio.sleep(0.12)
    assert mock_db["cancel_order"].call_count == 0
    assert mock_db["place_order"].call_count == 0


# ---------------------------------------------------------------------------
# G-273-A6 — [partial_cancel_timer_cleared] 마커가 실제로 발화한다
# (직전 검증 MEDIUM, 뮤테이션 M17)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a6_timer_cleared_marker_emitted_once_per_axis(
    engine: OrderEngine, registry: StrategyRegistry, mock_db, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """명세 O-A2 가 '넣는다' 로 결정한 D+1 양성 대조 마커의 회귀 가드.

    마커가 없으면 D+1 판독에서 APBK0927 0건이 "고쳐졌다" 와 "그날 부분체결이
    없었다" 를 구별하지 못한다(§6). 매수·매도 축 각각 1건, `order_no=` 를 담고,
    A2(다른 order_no 전량체결) 시나리오에서는 0건이어야 한다(마커가 게이트
    안에서만 찍힌다는 증거).
    """
    import src.engine.order_engine as _oe
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0.02)
    caplog.set_level(logging.INFO, logger="src.engine.order_engine")
    prefix = "[partial_cancel_timer_cleared]"

    # 매수 축
    buy_order = "0000305100"
    engine._order_qty[buy_order] = 5
    engine._order_strategy[buy_order] = "kojiro"
    engine._order_ticker[buy_order] = TICKER
    await _buy_notice(engine, buy_order, 3)
    await _buy_notice(engine, buy_order, 2)

    buy_hits = [r.getMessage() for r in caplog.records if r.getMessage().startswith(prefix)]
    assert len(buy_hits) == 1, f"매수 축 마커가 정확히 1건이 아니다 — {buy_hits}"
    assert f"order_no={buy_order}" in buy_hits[0]

    caplog.clear()

    # 매도 축 — 별도 ticker 로 축 간섭 차단
    ticker2 = "005930"
    registry.get("kojiro").state.positions[ticker2] = Position(
        ticker=ticker2, buy_price=60_000, quantity=5, order_no="B-2", strategy_id="kojiro",
    )
    sell_order = "0000400200"
    engine._order_qty[sell_order] = 5
    engine._order_strategy[sell_order] = "kojiro"
    engine._order_ticker[sell_order] = ticker2
    await engine.handle_execution_notice(
        ticker=ticker2, order_no=sell_order, side="SELL", price=24_800, quantity=3,
    )
    await engine.handle_execution_notice(
        ticker=ticker2, order_no=sell_order, side="SELL", price=24_800, quantity=2,
    )

    sell_hits = [r.getMessage() for r in caplog.records if r.getMessage().startswith(prefix)]
    assert len(sell_hits) == 1, f"매도 축 마커가 정확히 1건이 아니다 — {sell_hits}"
    assert f"order_no={sell_order}" in sell_hits[0]

    caplog.clear()

    # A2 — 다른 order_no 전량체결은 마커 0건(게이트 밖에서는 절대 찍히지 않는다)
    ticker3 = "000660"
    order_a = "A-KEEP"
    engine._order_qty[order_a] = 5
    engine._order_strategy[order_a] = "kojiro"
    engine._order_ticker[order_a] = ticker3
    await engine.handle_execution_notice(
        ticker=ticker3, order_no=order_a, side="BUY", price=100_000, quantity=3,
    )
    order_b = "B-DIFFERENT"
    engine._order_qty[order_b] = 2
    engine._order_strategy[order_b] = "kojiro"
    engine._order_ticker[order_b] = ticker3
    await engine.handle_execution_notice(
        ticker=ticker3, order_no=order_b, side="BUY", price=100_000, quantity=2,
    )

    no_hits = [r.getMessage() for r in caplog.records if r.getMessage().startswith(prefix)]
    assert no_hits == [], f"다른 order_no 전량체결인데 마커가 발화했다 — {no_hits}"


# ---------------------------------------------------------------------------
# G-273-A7 — 자연 만료(전량 체결 없이 30초 경과)도 짝 dict 를 함께 비운다
# (직전 검증 LOW#4, 뮤테이션 M8)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a7_natural_expiry_clears_both_dicts(
    engine: OrderEngine, mock_db, monkeypatch: pytest.MonkeyPatch,
):
    """부분체결 뒤 아무 후속 체결 없이 타이머가 자연 만료된 경우도
    `_pending_cancel_tasks` 와 `_pending_cancel_order_no` 가 **둘 다** 비어야 한다.

    `finally` 의 shadow pop 을 지워도(뮤테이션 M8) `_pending_cancel_tasks` 만
    보는 가드는 전부 초록이었다 — 이 테스트가 shadow 잔존을 직접 잰다.
    """
    import src.engine.order_engine as _oe
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0.02)

    order_no = "0000305100"
    engine._order_qty[order_no] = 5
    engine._order_strategy[order_no] = "kojiro"
    engine._order_ticker[order_no] = TICKER

    await _buy_notice(engine, order_no, 3)           # 3/5 → 타이머 등록
    assert engine._pending_cancel_order_no.get(TICKER) == order_no

    task = engine._pending_cancel_tasks[TICKER]
    for _ in range(20):
        if task.done():
            break
        await asyncio.sleep(0.01)
    assert task.done(), "전제 실패 — 타이머가 자연 만료되지 않았다"

    assert engine._pending_cancel_tasks == {}
    assert engine._pending_cancel_order_no == {}, (
        "task dict 는 비었지만 order_no shadow 가 남았다 — 짝 dict 불변식 위반(§1.4)"
    )
