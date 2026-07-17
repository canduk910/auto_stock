"""사이클 M5 (Red) — boot_manager.py 3 supabase 사이트 전환.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (Supabase→RDS 이전, 누락 사이트).

boot_manager.boot() 잔존 supabase 직접 접근 3사이트:
- L187-192 최근 BUY strategy 조회 → `trade_history.get_recent_buy_strategy` (scheduler 와 공통).
- L239-245 kis_tickers PENDING BUY→COMPLETED 일괄 → `trade_history.mark_pending_buys_completed` (공통).
- L268-273 오늘 BUY (ticker, strategy) 조회 → `trade_history.get_today_buys_ticker_strategy`.
  ⚠️ 기존은 `today.isoformat()` TZ-naive → 신규 함수는 `_today_kst_iso()` +09:00 (사이클 53 KST 계약).

부팅 포지션 복구 hot path — graceful(except pass) 계약 보존 필수.

Red 유효성: production 여전히 supabase.table() → 헬퍼 미호출 + 소스 잔존 → FAIL.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_BOOT = _REPO / "src" / "engine" / "boot_manager.py"


def _boot_source() -> str:
    """boot_manager.boot() 함수 소스만 추출 (전 사이트가 이 함수 내부)."""
    body = _BOOT.read_text(encoding="utf-8")
    tree = ast.parse(body)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "boot":
            return ast.get_source_segment(body, node) or ""
    return ""


# ---------------------------------------------------------------------------
# 소스 텍스트 가드 — boot_manager.py supabase 직접 접근 0건
# ---------------------------------------------------------------------------
def test_boot_manager_no_supabase_reference():
    body = _BOOT.read_text(encoding="utf-8")
    assert "from src.db.supabase import" not in body, (
        "boot_manager.py 는 supabase 직접 import 금지 (trade_history 헬퍼 경유)."
    )
    assert "supabase.table(" not in body, "boot_manager.py 는 supabase.table() 호출 0건."


# ---------------------------------------------------------------------------
# 3 사이트 헬퍼 위임 (boot 함수 스코프 한정)
# ---------------------------------------------------------------------------
def test_boot_uses_get_recent_buy_strategy():
    """최근 BUY strategy 조회는 trade_history.get_recent_buy_strategy(ticker) 위임."""
    src = _boot_source()
    assert src, "boot() 함수 소스 추출 실패."
    assert "supabase" not in src, "boot() 내 supabase 잔존 금지."
    assert "get_recent_buy_strategy" in src, (
        "최근 BUY strategy 조회는 trade_history.get_recent_buy_strategy(ticker) 위임."
    )


def test_boot_uses_mark_pending_buys_completed():
    """kis_tickers PENDING BUY→COMPLETED 는 trade_history.mark_pending_buys_completed 위임."""
    src = _boot_source()
    assert src, "boot() 함수 소스 추출 실패."
    assert "mark_pending_buys_completed" in src, (
        "PENDING BUY→COMPLETED 일괄은 trade_history.mark_pending_buys_completed(ticker) 위임."
    )


def test_boot_uses_get_today_buys_ticker_strategy():
    """오늘 BUY (ticker, strategy) 조회는 trade_history.get_today_buys_ticker_strategy 위임."""
    src = _boot_source()
    assert src, "boot() 함수 소스 추출 실패."
    assert "get_today_buys_ticker_strategy" in src, (
        "오늘 BUY (ticker, strategy) 조회는 trade_history.get_today_buys_ticker_strategy() 위임 "
        "(supabase select(ticker,strategy).gte(timestamp, today) 대체)."
    )


def test_boot_today_buys_kst_contract_in_helper_not_naive():
    """⚠️ 오늘 BUY 조회 KST 계약: boot 소스가 today.isoformat() TZ-naive 바인딩을 직접 하지 않음.

    KST 계약은 trade_history.get_today_buys_ticker_strategy 헬퍼 내부 `_today_kst_iso()` 로 이관 —
    boot 소스에서 `today.isoformat()` 을 timestamp gte 인자로 직접 넘기던 패턴이 사라져야 한다
    (사이클 53 — TZ-naive 시 KST 00:00~09:00 BUY 누락).
    """
    src = _boot_source()
    assert src, "boot() 함수 소스 추출 실패."
    # 헬퍼 위임 후에는 boot 이 timestamp gte + today.isoformat() 을 직접 조합하지 않는다.
    assert not ("gte" in src and "today.isoformat()" in src), (
        "오늘 BUY 조회의 today.isoformat() TZ-naive gte 는 헬퍼(_today_kst_iso, +09:00)로 이관되어야 함."
    )
