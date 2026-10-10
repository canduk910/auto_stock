"""cycle427 — boot_manager 미체결 매수 주문 소유 해석 (⑦-F2 안3).

정본 자문 = `_workspace/domain_consult/2026-10-09_boot_unknown_order_owner.md`.
사용자 결정 10-10 「안3」 — 미체결 매수 주문 복구가 **종목 기준**(같은 종목을 그날
사고판 전략)으로 소유를 정하던 우회를 닫는다. 새 순서 = ① `trade_history` 의
PENDING/PARTIAL 행 중 **그 주문번호 일치** ② `llm_buy_evaluations` 의 같은 주문번호
`strategy_id` ③ 둘 다 없으면 "미상" — 어느 장부에도 올리지 않는다(체결되면
`order_engine` 의 고아 귀속 가드 + CRITICAL 이 처리한다).

자문의 「후속 검증 권고」 12 시나리오 중 boot_manager 단에서 검증 가능한 것들
(1·4·5·6·7·8) + 구조 검사(11)를 고정한다. 2(두 번째 부분체결)·3(전량 체결)·
9(재시작 전 부분체결)·10(매도 미체결)은 `order_engine`(8영역) 영역이라 이 파일
밖(기존 핀이 이미 지킨다) — 12(안2 선택 시)는 안3 채택이라 제외한다.
"""
from __future__ import annotations

import inspect
import logging
import re
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import boot_manager
from tests.unit.engine.test_cycle425_boot_fallback_owner import (
    _FakeRegistry,
    _FakeStrategy,
    _make_scheduler,
    _summary,
    _unfilled_order,
)

pytestmark = pytest.mark.unit


async def _run_boot(
    scheduler,
    *,
    all_orders,
    lookup_from_trade_history=None,
    get_by_order=None,
) -> None:
    """`boot_manager.boot()` 을 돌리되 주문번호 해석 두 단계를 직접 제어한다."""

    th_lookup = (
        lookup_from_trade_history
        if lookup_from_trade_history is not None
        else AsyncMock(return_value=None)
    )
    llm_lookup = get_by_order if get_by_order is not None else AsyncMock(return_value=None)

    with (
        patch("src.engine.boot_manager.token_manager") as tm,
        patch(
            "src.engine.boot_manager.get_balance",
            new=AsyncMock(return_value=([], _summary())),
        ),
        patch(
            "src.engine.boot_manager.get_daily_orders",
            new=AsyncMock(return_value=all_orders),
        ),
        patch("src.engine.boot_manager.write_log", new=AsyncMock()),
        patch("src.db.stock_master.count_active", new=AsyncMock(return_value=2768)),
        patch("src.db.positions.load_all", new=AsyncMock(return_value=[])),
        patch("src.db.positions.delete_position", new=AsyncMock()),
        patch("src.db.positions.save_position", new=AsyncMock()),
        patch("src.db.trade_history.get_recent_buy_strategy", new=AsyncMock(return_value=None)),
        patch("src.db.trade_history.mark_pending_buys_completed", new=AsyncMock()),
        patch(
            "src.db.trade_history.get_today_buys_ticker_strategy",
            new=AsyncMock(return_value=[]),
        ),
        patch("src.db.trade_history._lookup_strategy_from_trade_history", new=th_lookup),
        patch("src.db.llm_buy_evaluations.get_by_order", new=llm_lookup),
    ):
        tm.get_token = AsyncMock()
        await boot_manager.boot(scheduler)


def _ledger_has(scheduler, order_no: str) -> bool:
    oe = scheduler.order_engine
    return (
        order_no in oe._pending_buy_orders
        or order_no in oe._order_qty
        or order_no in oe._order_strategy
        or order_no in oe._order_ticker
    )


# ---------------------------------------------------------------------------
# 1. 미상 주문 — 어느 장부에도 올리지 않는다 (시나리오 1 — boot 쪽 단언)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unresolved_order_not_registered_in_any_ledger():
    """trade_history·llm_buy_evaluations 둘 다 모르면 미체결 주문은 미상이다."""
    registry = _FakeRegistry({"momentum": _FakeStrategy("momentum")})
    scheduler = _make_scheduler(registry)

    order = _unfilled_order("555555", "ORDER1", price=1_000, qty=10)

    await _run_boot(scheduler, all_orders=[order])

    momentum = registry.get("momentum")
    assert "555555" not in momentum.state.pending_buys
    assert "555555" not in momentum.state.pending_buy_amounts
    assert not _ledger_has(scheduler, "ORDER1")


# ---------------------------------------------------------------------------
# 4. trade_history 주문번호 일치 — 그 전략으로 등록 (타이머 정상)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_order_resolved_by_trade_history_order_no_match():
    """trade_history 의 그 주문번호 PENDING/PARTIAL 행이 strategy 를 알려주면 등록된다."""
    registry = _FakeRegistry(
        {"momentum": _FakeStrategy("momentum"), "kojiro": _FakeStrategy("kojiro")}
    )
    scheduler = _make_scheduler(registry)

    order = _unfilled_order("666666", "ORDER2", price=2_000, qty=5)
    th_lookup = AsyncMock(return_value="kojiro")

    await _run_boot(scheduler, all_orders=[order], lookup_from_trade_history=th_lookup)

    kojiro = registry.get("kojiro")
    momentum = registry.get("momentum")
    assert "666666" in kojiro.state.pending_buys
    # cycle436 카드 E — 키 = (ticker, order_no), 부팅 복구는 order_no 를 안다.
    assert kojiro.state.pending_buy_amounts[("666666", "ORDER2")] == 10_000
    assert "666666" not in momentum.state.pending_buys
    assert scheduler.order_engine._order_strategy["ORDER2"] == "kojiro"
    assert scheduler.order_engine._order_qty["ORDER2"] == 5
    th_lookup.assert_awaited_once()
    args = th_lookup.await_args.args
    assert args[0] == "666666"
    assert args[1] == "ORDER2"


# ---------------------------------------------------------------------------
# 5. trade_history 미스 + llm_buy_evaluations 같은 주문번호 — 그 전략으로 등록
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_order_resolved_by_llm_evaluation_when_trade_history_misses():
    """trade_history 에 없고 llm_buy_evaluations 가 같은 주문번호를 알면 등록된다."""
    registry = _FakeRegistry(
        {"momentum": _FakeStrategy("momentum"), "donchian_swing": _FakeStrategy("donchian_swing")}
    )
    scheduler = _make_scheduler(registry)

    order = _unfilled_order("777777", "ORDER3", price=3_000, qty=2)
    llm_lookup = AsyncMock(return_value={"strategy_id": "donchian_swing"})

    await _run_boot(scheduler, all_orders=[order], get_by_order=llm_lookup)

    donchian = registry.get("donchian_swing")
    momentum = registry.get("momentum")
    assert "777777" in donchian.state.pending_buys
    assert "777777" not in momentum.state.pending_buys
    assert scheduler.order_engine._order_strategy["ORDER3"] == "donchian_swing"
    llm_lookup.assert_awaited_once_with("ORDER3")


# ---------------------------------------------------------------------------
# 6/7. 종목 기준 당일 BUY(다른 주문번호 · COMPLETED 행 포함)는 근거에서 뺀다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ticker_based_same_day_buy_is_not_accepted_as_evidence():
    """같은 종목에 전략 X 의 다른 주문번호 매매 이력이 있어도 소유는 해석되지 않는다.

    cycle425 까지는 `db_strategy_map`(종목→전략, `get_today_buys_ticker_strategy`
    출처)이 이 미체결 주문(다른 odno)을 그 전략 것으로 삼았다. 안3 은 종목 기준
    귀속을 근거에서 뺀다 — `_lookup_strategy_from_trade_history` 는 **그 주문번호**
    로만 조회하므로, 같은 종목의 다른 주문 이력이 있어도 호출 결과는 변하지 않는다
    (여기서는 실제 DB 호출 경로를 그대로 두고 trade_history/llm 조회 모두 미스로
    고정해 "종목 기준 보강 경로가 없다" 는 것을 확인한다).
    """
    registry = _FakeRegistry(
        {"momentum": _FakeStrategy("momentum"), "volatility_breakout": _FakeStrategy("volatility_breakout")}
    )
    scheduler = _make_scheduler(registry)

    # 전략 X(volatility_breakout)가 오늘 이 종목을 사고판 이력은 있지만, 미체결
    # 주문의 odno(ORDER4)는 그 이력과 다르다 — trade_history/llm 조회는 그 odno
    # 기준이라 미스로 떨어진다(구 경로였던 종목 기준 맵은 더 이상 참조되지 않는다).
    order = _unfilled_order("888888", "ORDER4", price=1_500, qty=4)

    await _run_boot(scheduler, all_orders=[order])

    vb = registry.get("volatility_breakout")
    momentum = registry.get("momentum")
    assert "888888" not in vb.state.pending_buys
    assert "888888" not in momentum.state.pending_buys
    assert not _ledger_has(scheduler, "ORDER4")


# ---------------------------------------------------------------------------
# 8. DB 조회 예외 — 미상으로 처리, 부팅은 계속, 장부 등록 0
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lookup_exceptions_resolve_to_unknown_and_boot_continues():
    """두 조회가 모두 예외를 던지면 그 주문은 미상이고 부팅은 중단되지 않는다."""
    registry = _FakeRegistry({"momentum": _FakeStrategy("momentum")})
    scheduler = _make_scheduler(registry)

    order = _unfilled_order("999999", "ORDER5", price=1_000, qty=1)
    th_lookup = AsyncMock(side_effect=RuntimeError("boom-th"))
    llm_lookup = AsyncMock(side_effect=RuntimeError("boom-llm"))

    # 예외가 전파되지 않고 부팅이 끝까지 돈다.
    await _run_boot(
        scheduler,
        all_orders=[order],
        lookup_from_trade_history=th_lookup,
        get_by_order=llm_lookup,
    )

    momentum = registry.get("momentum")
    assert "999999" not in momentum.state.pending_buys
    assert not _ledger_has(scheduler, "ORDER5")


@pytest.mark.asyncio
async def test_lookup_exception_logs_warning(caplog):
    """조회 예외는 조용히 넘어가지 않는다 — WARNING 1행."""
    registry = _FakeRegistry({"momentum": _FakeStrategy("momentum")})
    scheduler = _make_scheduler(registry)

    order = _unfilled_order("121212", "ORDER6", price=1_000, qty=1)
    th_lookup = AsyncMock(side_effect=RuntimeError("boom"))

    caplog.set_level(logging.WARNING, logger="src.engine.boot_manager")
    await _run_boot(scheduler, all_orders=[order], lookup_from_trade_history=th_lookup)

    msgs = [
        r.getMessage()
        for r in caplog.records
        if r.name == "src.engine.boot_manager" and r.levelno >= logging.WARNING
    ]
    assert any(
        "[boot_recover_order_owner_lookup_failed]" in m and "stage=trade_history" in m
        for m in msgs
    ), f"기대한 WARNING 없음: {caplog.text}"
    assert any(
        "[boot_recover_strategy_unknown]" in m and "ORDER6" in m and "장부 미등록" in m
        for m in msgs
    ), f"기대한 미상 마커 없음: {caplog.text}"


# ---------------------------------------------------------------------------
# 11. AST — 미체결 복구 루프 안에 "momentum" 리터럴·FALLBACK_OWNER_ID 사용 0
# ---------------------------------------------------------------------------
def test_ast_unfilled_recovery_loop_has_no_ticker_based_fallback_literal():
    """미체결 주문 복구 루프(`for order in all_orders:` ~) 안에 종목 기준 폴백 흔적이 없다.

    `_resolve_fallback_owner` 호출(식별자 자체) 은 허용한다 — 해석된 주문의 등록
    경로는 그대로이고, 금기는 "미상 판정 자리에 momentum 하드코딩·FALLBACK_OWNER_ID
    리터럴이 다시 들어오는 것"이다.
    """
    source = inspect.getsource(boot_manager.boot)
    match = re.search(
        r"for order in all_orders:.*?(?=\n    total_pos = sum)", source, re.DOTALL
    )
    assert match, "미체결 매수 주문 복구 루프를 찾지 못했다 — 마커 주석/다음 섹션이 바뀌었는지 확인"
    loop_src = match.group(0)
    assert '"momentum"' not in loop_src, "미체결 복구 루프 안에 momentum 리터럴이 있다"
    assert "FALLBACK_OWNER_ID" not in loop_src, (
        "미체결 복구 루프 안에서 FALLBACK_OWNER_ID 로 미상을 때우고 있다"
    )
