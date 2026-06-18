"""사이클 163 (2026-06-18) — `_handle_buy_fill` 전량 체결 분기 3 영역 try/except 분리 회귀 가드.

의제 #6 영역 — 6/17 12:43:09 알지노믹스 (476830) BUY callback_exception 영구 차단.
사이클 88 G-REJECT-1 영속 부분 예외 (DB INSERT race는 재연결로 해결 안 됨).
사이클 147 `_handle_sell_fill` 변경 0.
"""
from __future__ import annotations

import ast
import logging
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position, StrategyState


def _make_strategy(sid: str = "long_tail_volatility"):
    state = StrategyState(strategy_id=sid)
    s = MagicMock()
    s.strategy_id = sid
    s.state = state
    return s


def _make_engine(strategy_id: str = "long_tail_volatility"):
    registry = MagicMock()
    strategy = _make_strategy(strategy_id)
    registry.get = MagicMock(return_value=strategy)
    registry.is_ticker_held_by_any = MagicMock(return_value=False)
    engine = OrderEngine(registry)
    engine._order_strategy["0001521700"] = strategy_id
    engine._order_qty["0001521700"] = 1
    engine._order_ticker["0001521700"] = "476830"
    engine._pending_buy_orders["0001521700"] = {"ticker": "476830"}
    return engine, strategy


@pytest.mark.asyncio
async def test_G163_BUYFILL_1_update_trade_status_exception_no_raise(caplog):
    """G-163-BUYFILL-1: update_trade_status 예외 → ERROR + callback raise 0건.

    사이클 88 G-REJECT-1 영속 부분 예외 — DB 영역만 graceful 영역.
    """
    engine, strategy = _make_engine()

    with patch("src.engine.order_engine.update_trade_status",
               AsyncMock(side_effect=RuntimeError("supabase HTTP/2 ConnectionTerminated"))) as mock_update, \
         patch("src.engine.order_engine.insert_trade", AsyncMock()) as mock_insert, \
         patch("src.engine.order_engine._update_trade_status_by_order_no", AsyncMock(return_value=1)), \
         patch("src.db.positions.save_position", AsyncMock()):
        with caplog.at_level(logging.ERROR):
            # raise 발생 시 pytest 가 fail 시킴 — graceful 영역 영속 검증
            await engine._handle_buy_fill("476830", "0001521700", 110000, 1, 1, 1)

    assert any("[buy_fill_db_error]" in r.message and "update_trade_status" in r.message
               for r in caplog.records), "buy_fill_db_error step=update_trade_status ERROR 영구 영속 부재"
    # 메모리 positions 등록 영속
    assert "476830" in strategy.state.positions


@pytest.mark.asyncio
async def test_G163_BUYFILL_3_forced_update_exception_no_raise(caplog):
    """G-163-BUYFILL-3: forced_update 예외 → ERROR + callback raise 0건.

    사이클 147 `_update_trade_status_by_order_no` 예외 시 graceful 영속.
    """
    engine, strategy = _make_engine()

    with patch("src.engine.order_engine.update_trade_status",
               AsyncMock(return_value=0)) as mock_update, \
         patch("src.engine.order_engine.insert_trade",
               AsyncMock(side_effect=RuntimeError("UniqueViolation"))) as mock_insert, \
         patch("src.engine.order_engine._update_trade_status_by_order_no",
               AsyncMock(side_effect=RuntimeError("DB timeout"))) as mock_forced, \
         patch("src.db.positions.save_position", AsyncMock()):
        with caplog.at_level(logging.ERROR):
            await engine._handle_buy_fill("476830", "0001521700", 110000, 1, 1, 1)

    assert any("[buy_fill_db_error]" in r.message and "forced_update" in r.message
               for r in caplog.records), "step=forced_update ERROR 영구 영속 부재"
    assert "476830" in strategy.state.positions


@pytest.mark.asyncio
async def test_G163_BUYFILL_4_save_position_exception_no_raise(caplog):
    """G-163-BUYFILL-4: save_position 예외 → ERROR + 메모리 positions 등록 영속.

    6/17 12:43:09 알지노믹스 사고 영역 핵심 — DB 미동기화 시 15분 sync 회복 기대.
    """
    engine, strategy = _make_engine()

    with patch("src.engine.order_engine.update_trade_status", AsyncMock(return_value=1)), \
         patch("src.engine.order_engine.insert_trade", AsyncMock()), \
         patch("src.engine.order_engine._update_trade_status_by_order_no", AsyncMock(return_value=1)), \
         patch("src.db.positions.save_position",
               AsyncMock(side_effect=RuntimeError("HTTP/2 ConnectionTerminated"))) as mock_save:
        with caplog.at_level(logging.ERROR):
            await engine._handle_buy_fill("476830", "0001521700", 110000, 1, 1, 1)

    assert any("[buy_fill_db_error]" in r.message and "save_position" in r.message
               for r in caplog.records), "step=save_position ERROR 영구 영속 부재"
    # 사이클 163 핵심 — 메모리 positions 등록 영속
    assert "476830" in strategy.state.positions
    pos = strategy.state.positions["476830"]
    assert pos.buy_price == 110000
    assert pos.quantity == 1


@pytest.mark.asyncio
async def test_G163_BUYFILL_5_normal_flow_no_regression(caplog):
    """G-163-BUYFILL-5: 정상 흐름 → 모든 INFO + 매핑 정리 영속 (회귀 보존)."""
    engine, strategy = _make_engine()

    with patch("src.engine.order_engine.update_trade_status",
               AsyncMock(return_value=1)) as mock_update, \
         patch("src.engine.order_engine.insert_trade", AsyncMock()), \
         patch("src.engine.order_engine._update_trade_status_by_order_no", AsyncMock(return_value=1)), \
         patch("src.db.positions.save_position", AsyncMock()) as mock_save:
        with caplog.at_level(logging.INFO):
            await engine._handle_buy_fill("476830", "0001521700", 110000, 1, 1, 1)

    mock_update.assert_awaited_once()
    mock_save.assert_awaited_once()
    # 매핑 정리 영속 (회귀 보존)
    assert "0001521700" not in engine._order_qty
    assert "0001521700" not in engine._order_strategy
    assert "0001521700" not in engine._order_ticker
    # ERROR 발화 0건
    assert not any("[buy_fill_db_error]" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_G163_BUYFILL_2_insert_trade_race_unique_violation(caplog):
    """G-163-BUYFILL-2: insert_trade UniqueViolation → forced_update 시도 영속."""
    engine, strategy = _make_engine()

    with patch("src.engine.order_engine.update_trade_status",
               AsyncMock(return_value=0)), \
         patch("src.engine.order_engine.insert_trade",
               AsyncMock(side_effect=RuntimeError("duplicate key value violates unique constraint"))), \
         patch("src.engine.order_engine._update_trade_status_by_order_no",
               AsyncMock(return_value=1)) as mock_forced, \
         patch("src.db.positions.save_position", AsyncMock()):
        with caplog.at_level(logging.WARNING):
            await engine._handle_buy_fill("476830", "0001521700", 110000, 1, 1, 1)

    assert any("[buy_fill_correction_unique_violation]" in r.message
               for r in caplog.records), "UniqueViolation WARNING 영속 부재"
    mock_forced.assert_awaited_once()


def test_G163_SAFETY_1_handle_sell_fill_unchanged():
    """G-163-SAFETY-1: `_handle_sell_fill` 변경 0 (사이클 147 영속).

    AST 정적 검증 — `_handle_sell_fill` 함수 본체 변경 0 검증을 위해
    핵심 시그너처/내부 호출 패턴 영속 확인.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    src = (repo_root / "src/engine/order_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    sell_fill_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_handle_sell_fill":
            sell_fill_node = node
            break

    assert sell_fill_node is not None, "_handle_sell_fill 함수 부재"

    src_str = ast.unparse(sell_fill_node)
    # 사이클 147 영속 영역 영구 보존
    assert "_lookup_strategy_from_trade_history" in src_str
    assert "[sell_fill_strategy_lookup_fallback]" in src_str
    assert "[sell_fill_correction_unique_violation]" in src_str
