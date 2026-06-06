"""사이클 64 (2026-06-06) Red — B 카테고리: `scanner._apply_price_filter` 본체 (5 케이스).

> **선행 명세**: `_workspace/red/cycle64_price_filter_scanner.md` (§B)
> **설계 카드**: `_workspace/cycle64_price_filter_scanner_design_card.md` §2.3
> **자문 응답**: Q2 옵션 A (stock_master.raw.prdy_clpr 단독 + KIS pre-fetch 비채택)

요구 행위 (Red 단계 모두 AttributeError / ImportError 정답):

- B-1: 비활성 (0/0) → 전체 후보 통과 (필터 평가 skip)
- B-2: `prdy_clpr < min_price` 차단 + `[price_filter_scanner_skip]` INFO emit
- B-3: `prdy_clpr > max_price` 차단
- B-4: `prdy_clpr` 미확보 (stock_master miss / raw 비어있음) → graceful 통과 (Q2 자문)
- B-5: 임계 통과 시 후보 보존 + 순서 유지

위험 등급 MEDIUM — `_apply_price_filter` 동작 정확성.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_pf(min_price=0, max_price=0):
    """PriceFilter 헬퍼 — mode 인자 폐기 (사이클 64)."""
    from src.db.system_config import PriceFilter
    return PriceFilter(min_price=min_price, max_price=max_price)


def _make_basics(ticker: str, prdy_clpr: int):
    """StockBasics mock — raw.prdy_clpr 만 검증."""
    from src.models.stock import StockBasics
    return StockBasics(
        ticker=ticker, name=f"종목{ticker}",
        excg_dvsn_cd="1", nxt_tradable=True,
        krx_halted=False, admin_item=False,
        raw={"prdy_clpr": str(prdy_clpr)},
    )


# ---------------------------------------------------------------------------
# B-1: 비활성 (0/0) — 전체 후보 통과
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B1_inactive_filter_passes_all(monkeypatch):
    """B-1: PriceFilter(0, 0) — is_active=False → 전체 후보 그대로 반환.

    `is_active` 분기 즉시 return (KIS 호출 0, stock_master 호출 0).
    """
    from src.engine import scanner  # Red: _apply_price_filter AttributeError

    candidates = ["005930", "000660", "035720"]

    pf = _make_pf(0, 0)
    sm_get = AsyncMock()  # 호출 0 검증

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", sm_get):
        # Red: `_apply_price_filter` 미존재 → AttributeError 정답
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    assert result == candidates, "비활성 시 후보 그대로 반환해야 함"
    sm_get.assert_not_called()  # 필터 평가 skip → KIS 캐시 호출 0


# ---------------------------------------------------------------------------
# B-2: prdy_clpr < min_price → 차단 + INFO emit
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B2_below_min_price_blocked_with_emit(
    monkeypatch, caplog: pytest.LogCaptureFixture,
):
    """B-2: min=5000 + prdy_clpr=3000 → 차단 + `[price_filter_scanner_skip]` INFO emit.

    cap (`_price_filter_scanner_skip_logged_today`) 사용 — 1회/ticker/일.
    """
    from src.engine import scanner

    candidates = ["005930"]
    pf = _make_pf(min_price=5000, max_price=0)
    basics = _make_basics("005930", prdy_clpr=3000)

    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    assert result == [], "min 미달 종목 차단 실패"
    # `[price_filter_scanner_skip]` 1행 emit 검증
    skip_logs = [
        r for r in caplog.records
        if "[price_filter_scanner_skip]" in r.message
    ]
    assert len(skip_logs) == 1, (
        f"`[price_filter_scanner_skip]` 누락/중복 (실제 {len(skip_logs)}건)"
    )
    msg = skip_logs[0].message
    assert "005930" in msg
    assert "below_min" in msg or "reason=below_min" in msg.lower() or "below" in msg.lower(), (
        f"reason 필드 누락: {msg}"
    )


# ---------------------------------------------------------------------------
# B-3: prdy_clpr > max_price → 차단
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B3_above_max_price_blocked(monkeypatch):
    """B-3: max=1_000_000 + prdy_clpr=1_500_000 → 차단."""
    from src.engine import scanner

    candidates = ["005930"]
    pf = _make_pf(min_price=0, max_price=1_000_000)
    basics = _make_basics("005930", prdy_clpr=1_500_000)

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    assert result == [], "max 초과 종목 차단 실패"


# ---------------------------------------------------------------------------
# B-4: prdy_clpr 미확보 (stock_master miss / raw 비어있음) → graceful 통과
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B4_missing_prdy_clpr_graceful_pass(monkeypatch):
    """B-4: stock_master.get → None (miss) + raw 비어있는 종목 → graceful 통과 (Q2 자문).

    신규 상장 1일차 종목 영구 차단 방지 (Q3 자문 옵션 B + Q2 graceful).
    """
    from src.engine import scanner
    from src.models.stock import StockBasics

    # 3 시나리오: 완전 miss / raw 비어있음 / prdy_clpr 키 없음
    candidates = ["005930", "000660", "035720"]
    pf = _make_pf(min_price=5000, max_price=0)

    async def fake_sm_get(ticker):
        if ticker == "005930":
            return None  # 완전 miss
        if ticker == "000660":
            return StockBasics(
                ticker=ticker, name="", excg_dvsn_cd="", nxt_tradable=False,
                krx_halted=False, admin_item=False, raw={},  # 빈 raw
            )
        if ticker == "035720":
            return StockBasics(
                ticker=ticker, name="", excg_dvsn_cd="", nxt_tradable=False,
                krx_halted=False, admin_item=False, raw={"other_key": "1"},  # prdy_clpr 키 없음
            )
        return None

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(side_effect=fake_sm_get)), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    # 3 종목 모두 graceful 통과 (`prdy_clpr=0` 미확보 → 필터 skip)
    assert set(result) == {"005930", "000660", "035720"}, (
        f"graceful 통과 실패 — 미확보 종목 영구 차단 위험: result={result}"
    )


# ---------------------------------------------------------------------------
# B-5: 임계 통과 시 후보 보존 + 순서 유지
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B5_passes_within_range_preserves_order(monkeypatch):
    """B-5: 3 종목 (저가 차단 / 통과 / 고가 차단) 입력 → 1 종목 통과 + 순서 유지."""
    from src.engine import scanner

    candidates = ["AAAAAA", "BBBBBB", "CCCCCC"]
    pf = _make_pf(min_price=5000, max_price=100_000)

    async def fake_sm_get(ticker):
        return {
            "AAAAAA": _make_basics("AAAAAA", prdy_clpr=3000),    # 저가 차단
            "BBBBBB": _make_basics("BBBBBB", prdy_clpr=50_000),  # 통과
            "CCCCCC": _make_basics("CCCCCC", prdy_clpr=200_000), # 고가 차단
        }[ticker]

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(side_effect=fake_sm_get)), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    assert result == ["BBBBBB"], f"임계 통과 검증 실패: {result}"
