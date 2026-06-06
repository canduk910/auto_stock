"""사이클 65 (2026-06-06) Red — C 카테고리: 보유/익일청산 절대 보호 (2 케이스, **HIGH**).

> **선행 명세**: `_workspace/red/cycle65_trade_amount_filter.md` (§File 4)
> **자문 응답**: Q4 헬퍼 100% 재사용 + 사이클 64 Q1 옵션 D 3중 안전망 답습
> **선례**: 사이클 32 R4 universe guard + 사이클 64 C-1/C-2 패턴 답습
> **위험 등급**: **HIGH** — 시세 끊김 → 손절 발화 0 결함 직접 영역

요구 행위 (Red 단계 모두 ImportError / AttributeError 정답):

- C-1 [HIGH]: 보유 종목 (positions) — 거래대금 50만 (1억 임계 대비 200배 미달) 이어도 통과
- C-2 [HIGH]: 익일청산 종목 (`_pending_next_day_clear`) — 거래대금 100만이어도 통과

옵션 D 3중 안전망:
1. `_collect_protected_tickers_for_scanner` 헬퍼 (사이클 64 답습, 100% 재사용)
2. 최상단 early-return — `if ticker in protected_tickers: survivors.append(ticker); continue`
3. AST `protected_tickers=` keyword 의무 가드 (G-1)

CLAUDE.md 절대 규칙 보호:
- "**WebSocket 시세 보유·익일청산 우선 보장**" — scanner 차단 = 구독 안 됨 → stale → 손절 0건
- "**`tradable_boards` 매수 진입 전용 (사이클 38)**" — 매도/익일청산은 보호 종목 정상 보존
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_cycle65_scanner_state():
    """사이클 65 scanner 모듈 전역 reset — 테스트 격리."""
    from src.engine import scanner

    if hasattr(scanner, "_trade_amount_filter_cache"):
        scanner._trade_amount_filter_cache = None
    if hasattr(scanner, "_trade_amount_filter_cache_expires_at"):
        scanner._trade_amount_filter_cache_expires_at = 0.0
    if hasattr(scanner, "_trade_amount_filter_scanner_skip_logged_today"):
        scanner._trade_amount_filter_scanner_skip_logged_today.clear()
    if hasattr(scanner, "_trade_amount_filter_scanner_skip_count_today"):
        for k in list(scanner._trade_amount_filter_scanner_skip_count_today):
            scanner._trade_amount_filter_scanner_skip_count_today[k] = 0
    yield


# ===========================================================================
# C-1 [HIGH]: 보유 종목 — 거래대금 50만이어도 통과
# ===========================================================================
@pytest.mark.asyncio
async def test_C1_held_ticker_passes_below_threshold(monkeypatch):
    """C-1 (HIGH): 보유 종목 A001 — trade_amount_raw=50만 (1억 미만) 이어도 필터 통과.

    옵션 D 최상단 early-return 검증.
    회귀 가드: 시세 끊김 → 손절 발화 0 결함 차단.
    """
    from src.db.system_config import TradeAmountFilter
    from src.engine import scanner

    candidates = ["A001"]

    async def _stub_get():
        return TradeAmountFilter(min_amount=10_000_000_000)  # 100억 (강한 임계)
    monkeypatch.setattr(
        scanner, "_get_trade_amount_filter_for_scanner", _stub_get,
        raising=False,
    )
    monkeypatch.setattr(
        scanner, "ticker_market_info",
        {"A001": {"trade_amount_raw": 500_000}},  # 50만 (임계 대비 20,000배 미달)
        raising=False,
    )

    # `_get_acml_tr_pbmn` 호출 추적 — early-return 시 호출 0 (선택적 검증)
    with patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.stock_master.get", AsyncMock(return_value=None)):
        # protected_tickers 에 A001 포함
        survivors = await scanner._apply_trade_amount_filter(
            candidates, protected_tickers={"A001"},
        )

    assert survivors == ["A001"], (
        f"보유 종목 보호 위반 — 거래대금 50만 < 100억 임계여도 통과 의무 (실제 {survivors})"
    )


# ===========================================================================
# C-2 [HIGH]: 익일청산 종목 — 거래대금 100만이어도 통과
# ===========================================================================
@pytest.mark.asyncio
async def test_C2_next_day_clear_passes_below_threshold(monkeypatch):
    """C-2 (HIGH): 익일청산 보류 종목 B999 — trade_amount_raw=100만이어도 필터 통과.

    옵션 D 헬퍼 `_collect_protected_tickers_for_scanner` 가 `_pending_next_day_clear`
    합집합 포함. 익일 청산 직전 종목 시세 끊김 = 청산 실패 결함 차단.
    """
    from src.db.system_config import TradeAmountFilter
    from src.engine import scanner

    candidates = ["B999"]

    async def _stub_get():
        return TradeAmountFilter(min_amount=10_000_000_000)
    monkeypatch.setattr(
        scanner, "_get_trade_amount_filter_for_scanner", _stub_get,
        raising=False,
    )
    monkeypatch.setattr(
        scanner, "ticker_market_info",
        {"B999": {"trade_amount_raw": 1_000_000}},  # 100만
        raising=False,
    )

    with patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.stock_master.get", AsyncMock(return_value=None)):
        # protected_tickers 에 B999 포함 (익일청산 보류)
        survivors = await scanner._apply_trade_amount_filter(
            candidates, protected_tickers={"B999"},
        )

    assert survivors == ["B999"], (
        f"익일청산 보호 위반 — 거래대금 100만 < 100억 임계여도 통과 의무 (실제 {survivors})"
    )
