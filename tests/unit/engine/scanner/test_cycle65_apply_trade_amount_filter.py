"""사이클 65 (2026-06-06) Red — B 카테고리: `scanner._apply_trade_amount_filter` 본체 (4 케이스).

> **선행 명세**: `_workspace/red/cycle65_trade_amount_filter.md` (§File 2)
> **설계 카드 v2**: `_workspace/cycle65_trade_amount_filter_design_card.md` §2.3
> **자문 응답**: Q2 옵션 C 통합 폴백 + Q6-1 09:00 race graceful 영속

요구 행위 (Red 단계 모두 ImportError / AttributeError 정답):

- B-1 [LOW]: 비활성 (`min_amount=0`) → 모든 후보 통과 (필터 평가 skip)
- B-2 [LOW]: 임계 미만 (`min_amount=1억`, `trade_amount_raw=5천만`) → 차단
- B-3 [LOW, Q6-1 HIGH 영속]: 양쪽 miss → graceful 통과 (09:00 race 차단)
- B-4 [LOW]: 임계 이상 (`min_amount=1억`, `trade_amount_raw=50억`) → 통과

위험 등급 LOW + Q6-1 (HIGH 영속).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# autouse fixture — scanner 모듈 전역 reset (테스트 격리 의무, Red 명세 §3)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_cycle65_scanner_state():
    """사이클 65 scanner 모듈 전역 reset — 테스트 격리.

    Red 단계 — 필드 미존재 시 setattr 자동 무시 (graceful).
    Green 단계 후 모든 필드 정합성 검증.
    """
    from src.engine import scanner

    # 사전 reset (필드 존재 시만)
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
    # 사후 reset
    if hasattr(scanner, "_trade_amount_filter_cache"):
        scanner._trade_amount_filter_cache = None
    if hasattr(scanner, "_trade_amount_filter_cache_expires_at"):
        scanner._trade_amount_filter_cache_expires_at = 0.0
    if hasattr(scanner, "_trade_amount_filter_scanner_skip_logged_today"):
        scanner._trade_amount_filter_scanner_skip_logged_today.clear()
    if hasattr(scanner, "_trade_amount_filter_scanner_skip_count_today"):
        for k in list(scanner._trade_amount_filter_scanner_skip_count_today):
            scanner._trade_amount_filter_scanner_skip_count_today[k] = 0


# ---------------------------------------------------------------------------
# B-1: 비활성 (min_amount=0) → 모든 후보 통과
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B1_inactive_filter_passes_all(monkeypatch):
    """B-1: TradeAmountFilter(min_amount=0) → is_active=False → 전체 후보 그대로 반환.

    Q6-1 영속 — 비활성 시 09:00 race 자체 무관 (필터 평가 skip).
    """
    from src.db.system_config import TradeAmountFilter
    from src.engine import scanner  # Red: _apply_trade_amount_filter 미존재 → AttributeError

    candidates = ["005930", "000660", "035720"]

    async def _stub_get():
        return TradeAmountFilter(min_amount=0)
    monkeypatch.setattr(
        scanner, "_get_trade_amount_filter_for_scanner", _stub_get,
        raising=False,
    )

    # ticker_market_info 호출 0 검증 — 필터 평가 skip
    with patch.dict(scanner.ticker_market_info, {}, clear=False):
        # Red: `_apply_trade_amount_filter` 미존재 → AttributeError 정답
        survivors = await scanner._apply_trade_amount_filter(
            candidates, protected_tickers=set(),
        )

    assert survivors == candidates, (
        "비활성 시 전체 후보 보존 의무 — Q1 자문 디폴트 0 (비활성) 영속"
    )


# ---------------------------------------------------------------------------
# B-2: 임계 미만 차단 (trade_amount_raw=5천만 < min=1억)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B2_below_min_amount_excluded(monkeypatch):
    """B-2: min_amount=1억, ticker_market_info["trade_amount_raw"]=5천만 → 차단."""
    from src.db.system_config import TradeAmountFilter
    from src.engine import scanner

    candidates = ["A001"]

    async def _stub_get():
        return TradeAmountFilter(min_amount=100_000_000)  # 1억
    monkeypatch.setattr(
        scanner, "_get_trade_amount_filter_for_scanner", _stub_get,
        raising=False,
    )
    # Q2 옵션 C 1순위 — scanner ticker_market_info hit (5천만 < 1억)
    monkeypatch.setattr(
        scanner, "ticker_market_info",
        {"A001": {"trade_amount_raw": 50_000_000}},
        raising=False,
    )

    with patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.stock_master.get", AsyncMock(return_value=None)):
        survivors = await scanner._apply_trade_amount_filter(
            candidates, protected_tickers=set(),
        )

    assert survivors == [], (
        "임계 미만 차단 실패 — trade_amount_raw=5천만 < min=1억"
    )


# ---------------------------------------------------------------------------
# B-3: 미확보 graceful 통과 (Q6-1 HIGH 영속)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B3_missing_data_graceful_passes(monkeypatch):
    """B-3 (Q6-1 HIGH 영속): scanner ticker_market_info miss + stock_master.get → None →
    `_get_acml_tr_pbmn` 0 반환 → graceful 통과.

    09:00 직후 누적 거래대금 미반영 시 전체 후보 차단 = 시스템 매매 무용 위험.
    """
    from src.db.system_config import TradeAmountFilter
    from src.engine import scanner

    candidates = ["A001"]

    async def _stub_get():
        return TradeAmountFilter(min_amount=1_000_000_000)  # 10억 활성
    monkeypatch.setattr(
        scanner, "_get_trade_amount_filter_for_scanner", _stub_get,
        raising=False,
    )
    # scanner miss
    monkeypatch.setattr(scanner, "ticker_market_info", {}, raising=False)

    # stock_master miss
    with patch("src.db.stock_master.get", AsyncMock(return_value=None)), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        survivors = await scanner._apply_trade_amount_filter(
            candidates, protected_tickers=set(),
        )

    # Q6-1 영속 — 둘 다 miss 시 graceful 통과 (차단 X)
    assert survivors == candidates, (
        "Q6-1 09:00 race graceful 통과 위반 — 양쪽 miss 시 차단 = 시스템 매매 무용 위험"
    )


# ---------------------------------------------------------------------------
# B-4: 임계 이상 통과 (trade_amount_raw=50억 > min=1억)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B4_above_min_amount_passes(monkeypatch):
    """B-4: min_amount=1억, ticker_market_info["trade_amount_raw"]=50억 → 통과."""
    from src.db.system_config import TradeAmountFilter
    from src.engine import scanner

    candidates = ["A001"]

    async def _stub_get():
        return TradeAmountFilter(min_amount=100_000_000)  # 1억
    monkeypatch.setattr(
        scanner, "_get_trade_amount_filter_for_scanner", _stub_get,
        raising=False,
    )
    monkeypatch.setattr(
        scanner, "ticker_market_info",
        {"A001": {"trade_amount_raw": 5_000_000_000}},  # 50억
        raising=False,
    )

    with patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.stock_master.get", AsyncMock(return_value=None)):
        survivors = await scanner._apply_trade_amount_filter(
            candidates, protected_tickers=set(),
        )

    assert survivors == candidates
