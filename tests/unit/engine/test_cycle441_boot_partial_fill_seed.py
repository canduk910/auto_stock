"""cycle441 — 장중 재시작 뒤 일부 체결된 매수 주문의 잔량 체결 (B-ii 부팅 시드).

정본 자문 = `_workspace/domain_consult/2026-10-10_j4_exact_fill_attribution.md`
§4(b), 표 C3·C4, J4-11. 사용자 결정 10-10 — B-ii(부팅 쪽, 8영역 아님)로 C3·C4
결함을 고친다.

지금(cycle441 전) 미체결 매수 주문 복구 루프는 `is_ticker_held_by_any(ticker)`
가 참이면 **무조건** 건너뛴다 — 부팅 전 일부만 체결된 매수 주문의 잔량 체결이
`order_engine._filled_qty` 시드가 없어 다음 체결통보를 전량으로 오판하거나
(C4, 기존 결함) `held_conflict` 로 버려졌다(C3).

이 사이클은 「주문의 주인을 주문번호로 찾았고(`_resolve_unfilled_buy_owner`,
cycle427), 그 주인이 그 종목의 현재 보유 전략과 같을 때만」 매핑을 등록하고
`_filled_qty[order_no] = tot_ccld_qty` 로 시드한다. 그 밖(주인 미상·주인 ≠
보유자·`pos.quantity != tot_ccld_qty`)은 지금처럼 조용히 건너뛴다.
"""
from __future__ import annotations

import logging

import pytest
from unittest.mock import AsyncMock

from src.engine import boot_manager
from tests.unit.engine.test_cycle425_boot_fallback_owner import (
    _FakeRegistry,
    _FakeStrategy,
    _make_scheduler,
    _summary,
)
from tests.unit.engine.test_cycle427_boot_unfilled_order_owner import (
    _ledger_has,
    _run_boot,
)

pytestmark = pytest.mark.unit


def _partial_order(
    ticker: str,
    order_no: str,
    *,
    price: int,
    ord_qty: int,
    rmn_qty: int,
    tot_ccld_qty: int,
) -> dict:
    """부팅이 보는 그날 주문내역(TTTC0081R) 한 행 — 일부 체결·잔량 존재."""
    return {
        "sll_buy_dvsn_cd": "02",
        "rmn_qty": str(rmn_qty),
        "pdno": ticker,
        "ord_unpr": str(price),
        "ord_qty": str(ord_qty),
        "odno": order_no,
        "tot_ccld_qty": str(tot_ccld_qty),
    }


def _make_scheduler_with_filled_qty(registry) -> object:
    """cycle425 `_make_scheduler` + 실제 dict `_filled_qty`(검증 가능해야 한다)."""
    scheduler = _make_scheduler(registry)
    scheduler.order_engine._filled_qty = {}
    return scheduler


def _seed_held_position(strategy: _FakeStrategy, ticker: str, *, quantity: int, order_no: str = "") -> None:
    from src.engine.strategy_base import Position

    strategy.state.positions[ticker] = Position(
        ticker=ticker,
        buy_price=1_000,
        quantity=quantity,
        order_no=order_no,
        strategy_id=strategy.strategy_id,
    )


# ---------------------------------------------------------------------------
# 1. 주인 = 보유자, 수량 일치 — 시드 + 매핑 등록 + 잔량분만 예약
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_partial_fill_seed_registers_mapping_when_owner_matches_holder():
    """보유자와 해석된 주인이 같고 보유수량이 이미체결수량과 같으면 시드한다."""
    registry = _FakeRegistry({"kojiro": _FakeStrategy("kojiro"), "momentum": _FakeStrategy("momentum")})
    scheduler = _make_scheduler_with_filled_qty(registry)
    kojiro = registry.get("kojiro")

    # 보유 3주 — 부팅 전 그 주문의 이미 체결분과 같다(재시작 전 PARTIAL/COMPLETED
    # 어느 쪽이든 수량은 보존됐다고 가정).
    _seed_held_position(kojiro, "111222", quantity=3)

    order = _partial_order(
        "111222", "ORD441A", price=1_000, ord_qty=4, rmn_qty=1, tot_ccld_qty=3,
    )
    th_lookup = AsyncMock(return_value="kojiro")

    await _run_boot(scheduler, all_orders=[order], lookup_from_trade_history=th_lookup)

    oe = scheduler.order_engine
    assert oe._filled_qty.get("ORD441A") == 3, "기체결 수량이 _filled_qty 에 시드돼야 한다(J-4 E3 전제)"
    assert oe._order_qty.get("ORD441A") == 4
    assert oe._order_strategy.get("ORD441A") == "kojiro"
    assert oe._order_ticker.get("ORD441A") == "111222"
    assert "ORD441A" in oe._pending_buy_orders

    assert "111222" in kojiro.state.pending_buys
    # 카드 E(cycle436) — 예약은 잔량분만(1주 × 1,000원), 이미 체결된 3주는
    # 포지션에 있으므로 예약 대상이 아니다.
    assert kojiro.state.pending_buy_amounts[("111222", "ORD441A")] == 1_000 * 1


@pytest.mark.asyncio
async def test_partial_fill_seed_j4_prev_total_positive_after_restart():
    """시드 덕분에 재시작 뒤에도 J-4(cycle438) E3(prev_total>0)가 성립한다."""
    registry = _FakeRegistry({"donchian_swing": _FakeStrategy("donchian_swing")})
    scheduler = _make_scheduler_with_filled_qty(registry)
    donchian = registry.get("donchian_swing")
    _seed_held_position(donchian, "333444", quantity=5)

    order = _partial_order(
        "333444", "ORD441B", price=2_000, ord_qty=10, rmn_qty=5, tot_ccld_qty=5,
    )
    th_lookup = AsyncMock(return_value="donchian_swing")

    await _run_boot(scheduler, all_orders=[order], lookup_from_trade_history=th_lookup)

    oe = scheduler.order_engine
    prev_total = oe._filled_qty.get("ORD441B", 0)
    assert prev_total > 0, "재시작 뒤 이 프로세스가 '이미 체결을 본 적 있음' 이 성립해야 한다"


# ---------------------------------------------------------------------------
# 2. 수량 불일치 — 시드하지 않고 WARNING 1행
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_partial_fill_seed_skipped_on_qty_mismatch(caplog):
    """보유수량과 KIS 이미체결수량이 다르면 시드하지 않고 WARNING 을 남긴다."""
    registry = _FakeRegistry({"kojiro": _FakeStrategy("kojiro")})
    scheduler = _make_scheduler_with_filled_qty(registry)
    kojiro = registry.get("kojiro")
    # 사람이 그 사이 1주를 팔아 보유가 2주로 줄었다 — KIS 이미체결은 3주.
    _seed_held_position(kojiro, "555666", quantity=2)

    order = _partial_order(
        "555666", "ORD441C", price=1_500, ord_qty=4, rmn_qty=1, tot_ccld_qty=3,
    )
    th_lookup = AsyncMock(return_value="kojiro")

    caplog.set_level(logging.WARNING, logger="src.engine.boot_manager")
    await _run_boot(scheduler, all_orders=[order], lookup_from_trade_history=th_lookup)

    oe = scheduler.order_engine
    assert "ORD441C" not in oe._filled_qty
    assert not _ledger_has(scheduler, "ORD441C")
    assert "555666" not in kojiro.state.pending_buys

    msgs = [
        r.getMessage()
        for r in caplog.records
        if r.name == "src.engine.boot_manager" and r.levelno >= logging.WARNING
    ]
    assert any(
        "[boot_partial_fill_seed_skipped]" in m and "reason=qty_mismatch" in m and "ORD441C" in m
        for m in msgs
    ), f"기대한 WARNING 없음: {caplog.text}"


# ---------------------------------------------------------------------------
# 3. 주인 미상 — 보유 중이어도 시드하지 않고, 종전처럼 조용히 건너뛴다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_partial_fill_seed_skipped_when_owner_unresolved(caplog):
    """주문번호로 주인을 못 찾으면 보유 중이어도 손대지 않는다(조용히 skip)."""
    registry = _FakeRegistry({"kojiro": _FakeStrategy("kojiro")})
    scheduler = _make_scheduler_with_filled_qty(registry)
    kojiro = registry.get("kojiro")
    _seed_held_position(kojiro, "777888", quantity=3)

    order = _partial_order(
        "777888", "ORD441D", price=1_000, ord_qty=4, rmn_qty=1, tot_ccld_qty=3,
    )
    # trade_history·llm_buy_evaluations 둘 다 미스 → 주인 미상.

    caplog.set_level(logging.WARNING, logger="src.engine.boot_manager")
    await _run_boot(scheduler, all_orders=[order])

    oe = scheduler.order_engine
    assert "ORD441D" not in oe._filled_qty
    assert not _ledger_has(scheduler, "ORD441D")

    msgs = [
        r.getMessage()
        for r in caplog.records
        if r.name == "src.engine.boot_manager" and r.levelno >= logging.WARNING
    ]
    # 이번 범위는 "주인 확인 = 보유자" 하나뿐이다 — 보유 중인데 주인 미상인
    # 경우는 기존(cycle441 전)과 같은 침묵 skip 이어야 한다(장부 미등록 WARNING
    # 은 "보유 없음" 경로 전용 — 여기서 새로 울리지 않는다).
    assert not any("[boot_recover_strategy_unknown]" in m for m in msgs), (
        f"보유 중 주인 미상은 조용히 건너뛰어야 하는데 WARNING 이 울렸다: {caplog.text}"
    )


# ---------------------------------------------------------------------------
# 4. 주인 ≠ 보유자 — 조용히 건너뛴다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_partial_fill_seed_skipped_when_owner_differs_from_holder():
    """해석된 주인이 실제 보유자와 다르면 시드하지 않는다(사람 주문 보호)."""
    registry = _FakeRegistry(
        {"kojiro": _FakeStrategy("kojiro"), "donchian_swing": _FakeStrategy("donchian_swing")}
    )
    scheduler = _make_scheduler_with_filled_qty(registry)
    kojiro = registry.get("kojiro")
    donchian = registry.get("donchian_swing")
    # kojiro 가 실제 보유자이지만, 이 주문번호는 donchian_swing 것으로 해석된다
    # (예: 날짜가 다른 주문번호 재사용 — 우연한 번호 충돌).
    _seed_held_position(kojiro, "999000", quantity=3)

    order = _partial_order(
        "999000", "ORD441E", price=1_000, ord_qty=4, rmn_qty=1, tot_ccld_qty=3,
    )
    th_lookup = AsyncMock(return_value="donchian_swing")

    await _run_boot(scheduler, all_orders=[order], lookup_from_trade_history=th_lookup)

    oe = scheduler.order_engine
    assert "ORD441E" not in oe._filled_qty
    assert not _ledger_has(scheduler, "ORD441E")
    assert "999000" not in kojiro.state.pending_buys
    assert "999000" not in donchian.state.pending_buys


# ---------------------------------------------------------------------------
# 5. 잔량 0 — 보유 중이든 아니든 애초에 루프에 닿지 않는다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_partial_fill_seed_skipped_when_remaining_zero():
    """rmn_qty<=0 인 행은 보유 중 종목이어도 시드 시도 자체가 없다."""
    registry = _FakeRegistry({"kojiro": _FakeStrategy("kojiro")})
    scheduler = _make_scheduler_with_filled_qty(registry)
    kojiro = registry.get("kojiro")
    _seed_held_position(kojiro, "121314", quantity=4)

    order = _partial_order(
        "121314", "ORD441F", price=1_000, ord_qty=4, rmn_qty=0, tot_ccld_qty=4,
    )
    th_lookup = AsyncMock(return_value="kojiro")

    await _run_boot(scheduler, all_orders=[order], lookup_from_trade_history=th_lookup)

    oe = scheduler.order_engine
    assert "ORD441F" not in oe._filled_qty
    assert not _ledger_has(scheduler, "ORD441F")
    th_lookup.assert_not_awaited()
