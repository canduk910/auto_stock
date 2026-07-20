"""RDS asyncpg date-객체 buy_date 크래시 회귀 가드 (2026-07-20 운영 사고).

사고: boot_manager.boot() 포지션 복구가 `date.fromisoformat(row["buy_date"])` 호출 →
asyncpg 는 positions.buy_date(DATE) 를 `datetime.date` 객체로 반환 →
`TypeError: fromisoformat: argument must be str` → _boot 크래시 → 매매 프로세스
무한 재시작 루프(15:18~20:09) → 15:20 VB 일괄청산 미실행 → 당일 포지션 익일 방치.

수정: `date.fromisoformat(row["buy_date"])` → `to_date(row.get("buy_date"))`
(src/db/_kst.py::to_date — date/datetime/str/None 모두 안전 처리).
"""
from __future__ import annotations

import ast
from datetime import date, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import boot_manager

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_REPO = Path(__file__).resolve().parents[3]
_BOOT = _REPO / "src" / "engine" / "boot_manager.py"


def _boot_source() -> str:
    body = _BOOT.read_text(encoding="utf-8")
    tree = ast.parse(body)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "boot":
            return ast.get_source_segment(body, node) or ""
    return ""


# ── (a) 행위: date 객체 buy_date 로 포지션 복구 → 크래시 없이 정상 등록 ──

@pytest.mark.asyncio
async def test_boot_recovers_position_with_date_object_buy_date():
    """asyncpg 가 buy_date 를 datetime.date 로 반환해도 boot 이 크래시하지 않고 복구."""
    today = date.today()
    # asyncpg 실제 반환 형태 — buy_date 가 str 이 아니라 date 객체
    db_row = {
        "ticker": "073240", "ticker_name": "금호타이어",
        "buy_price": 6080, "quantity": 13, "order_no": "0000374000",
        "strategy_id": "volatility_breakout", "buy_date": today,  # ★ date 객체
        "high_since_buy": 6080,
    }
    holding = MagicMock(ticker="073240", quantity=13, avg_price=6080, name="금호타이어")
    summary = MagicMock(net_asset=1_000_000)

    target = MagicMock()
    target.strategy_id = "volatility_breakout"
    target.state = MagicMock()
    target.state.positions = {}

    scheduler = MagicMock()
    scheduler._preissue_all_tokens = AsyncMock()
    scheduler._load_strategy_config = AsyncMock()
    scheduler._refresh_market_regime_and_persist = AsyncMock()
    scheduler._resolve_cash_usage_ratio = AsyncMock(return_value=1.0)
    scheduler._eager_refresh_stock_master_for_held_positions = AsyncMock()
    scheduler._sync_orders_to_db = AsyncMock()
    scheduler.registry = MagicMock()
    scheduler.registry.enabled.return_value = []
    scheduler.registry.all.return_value = []
    scheduler.registry.is_ticker_held_by_any.return_value = True
    scheduler.registry.get.return_value = target
    scheduler.registry.allocate_funds = MagicMock()
    scheduler.order_engine = MagicMock()
    scheduler.order_engine._pending_buy_orders = {}
    scheduler.order_engine._order_qty = {}
    scheduler.order_engine._order_strategy = {}
    scheduler.order_engine._order_ticker = {}

    with patch("src.engine.boot_manager.token_manager") as tm, \
         patch("src.engine.boot_manager.get_balance",
               new=AsyncMock(return_value=([holding], summary))), \
         patch("src.engine.boot_manager.get_daily_orders", new=AsyncMock(return_value=[])), \
         patch("src.engine.boot_manager.write_log", new=AsyncMock()), \
         patch("src.db.stock_master.count_active", new=AsyncMock(return_value=2768)), \
         patch("src.db.positions.load_all", new=AsyncMock(return_value=[db_row])), \
         patch("src.db.trade_history.get_recent_buy_strategy", new=AsyncMock(return_value=None)), \
         patch("src.db.trade_history.mark_pending_buys_completed", new=AsyncMock()), \
         patch("src.db.trade_history.get_today_buys_ticker_strategy", new=AsyncMock(return_value=[])):
        tm.get_token = AsyncMock()
        # 크래시 없이 완주해야 한다 (Red: date.fromisoformat(date객체) → TypeError)
        await boot_manager.boot(scheduler)

    # 포지션이 정확한 date 로 복구됨
    assert "073240" in target.state.positions
    pos = target.state.positions["073240"]
    assert pos.buy_date == today
    assert pos.strategy_id == "volatility_breakout"
    assert pos.quantity == 13


# ── (b) AST 가드: buy_date 파싱은 to_date, raw fromisoformat 금지 ──

def test_boot_uses_to_date_for_buy_date_not_raw_fromisoformat():
    src = _boot_source()
    assert src, "boot() 소스 추출 실패."
    assert 'date.fromisoformat(row["buy_date"])' not in src, (
        "buy_date 를 date.fromisoformat 로 파싱 금지 — asyncpg DATE 는 date 객체라 TypeError. to_date 사용."
    )
    assert "to_date(" in src, "포지션 복구는 to_date() 로 buy_date 안전 파싱해야 함."
