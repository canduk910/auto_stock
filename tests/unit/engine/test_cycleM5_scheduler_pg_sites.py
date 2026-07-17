"""사이클 M5 (Red) — scheduler.py 3 supabase 사이트 전환.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (Supabase→RDS 이전, 누락 사이트).

scheduler.py 잔존 supabase 직접 접근 3사이트:
- L413-414 `_is_auto_start_enabled` auto_start read → `system_config.get_auto_start()`.
- L3738-3743 `_sync_positions_from_balance` PENDING BUY→COMPLETED → `trade_history.mark_pending_buys_completed`.
- L3755-3762 최근 BUY strategy 조회 → `trade_history.get_recent_buy_strategy`.

`_is_auto_start_enabled` = 부팅 매매 스케줄 결정 → 계약 보존 필수 (예외 시 .env settings.auto_start 폴백).

Red 유효성: production 여전히 supabase.table() → 헬퍼 미호출 + 소스 텍스트 잔존 → FAIL.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_SCHED = _REPO / "src" / "engine" / "scheduler.py"


# ---------------------------------------------------------------------------
# 소스 텍스트 가드 — scheduler.py supabase 직접 접근 0건
# ---------------------------------------------------------------------------
def test_scheduler_no_supabase_reference():
    """scheduler.py 내 supabase import / table() 호출 0건."""
    body = _SCHED.read_text(encoding="utf-8")
    assert "from src.db.supabase import" not in body, (
        "scheduler.py 는 supabase 직접 import 금지 (system_config / trade_history 헬퍼 경유)."
    )
    assert "supabase.table(" not in body, "scheduler.py 는 supabase.table() 호출 0건."


# ---------------------------------------------------------------------------
# _is_auto_start_enabled → system_config.get_auto_start()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_is_auto_start_enabled_delegates_to_system_config():
    """_is_auto_start_enabled → system_config.get_auto_start() 위임 (auto_start 읽기 RDS 정합)."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    with patch("src.db.system_config.get_auto_start", new=AsyncMock(return_value=True)) as g:
        out = await sched._is_auto_start_enabled()

    g.assert_awaited_once()
    assert out is True, "get_auto_start() True → _is_auto_start_enabled True 계약 보존."


@pytest.mark.asyncio
async def test_is_auto_start_enabled_env_fallback_on_exception():
    """DB 예외 시 settings.auto_start .env 폴백 계약 보존 (부팅 스케줄 결정 절대 보호)."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    with patch("src.db.system_config.get_auto_start",
               new=AsyncMock(side_effect=RuntimeError("db down"))), \
         patch("src.config.settings") as _settings:
        _settings.auto_start = True
        out = await sched._is_auto_start_enabled()

    assert out is True, "DB 예외 → settings.auto_start(.env) 폴백 계약 보존."


# ---------------------------------------------------------------------------
# _sync_positions_from_balance — 2 trade_history 사이트 헬퍼 위임 (AST-scoped 검증)
# ---------------------------------------------------------------------------
def _sync_positions_source() -> str:
    """scheduler.py 의 _sync_positions_from_balance 함수 소스만 추출 (오탐 차단)."""
    tree = ast.parse(_SCHED.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_sync_positions_from_balance":
            return ast.get_source_segment(_SCHED.read_text(encoding="utf-8"), node) or ""
    return ""


def test_sync_positions_uses_mark_pending_buys_completed():
    """_sync_positions_from_balance 내 PENDING BUY→COMPLETED 는 trade_history 헬퍼 위임."""
    src = _sync_positions_source()
    assert src, "_sync_positions_from_balance 함수 소스 추출 실패."
    assert "supabase" not in src, "함수 내 supabase 잔존 금지."
    assert "mark_pending_buys_completed" in src, (
        "PENDING BUY→COMPLETED 는 trade_history.mark_pending_buys_completed(ticker) 위임."
    )


def test_sync_positions_uses_get_recent_buy_strategy():
    """_sync_positions_from_balance 내 최근 BUY strategy 조회는 trade_history 헬퍼 위임."""
    src = _sync_positions_source()
    assert src, "_sync_positions_from_balance 함수 소스 추출 실패."
    assert "get_recent_buy_strategy" in src, (
        "최근 BUY strategy 조회는 trade_history.get_recent_buy_strategy(ticker) 위임 "
        "(supabase select(strategy).order(timestamp desc).limit(1) 대체)."
    )
