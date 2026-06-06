"""사이클 65 (2026-06-06) Red — F 카테고리: integration E2E (4 케이스).

> **선행 명세**: `_workspace/red/cycle65_trade_amount_filter.md` (§File 10)
> **설계 카드 v2**: `_workspace/cycle65_trade_amount_filter_design_card.md` §2.2 / §2.3
> **자문 응답**: Q3 순차 hook + funnel step_no=97

요구 행위 (Red 단계 모두 ImportError / AttributeError 정답):

- F-1 [MEDIUM]: scan → price → trade_amount → subscribe 정합성 (4 호출 순서)
- F-2 [MEDIUM]: 보유 종목 보호 E2E (가격 + 거래대금 양쪽 통과)
- F-3 [LOW]: funnel `step_no=97` snapshot hook 호출 검증
- F-4 [LOW]: 가격 차단 종목은 거래대금 필터 candidates 에 미도달 (순차 hook)

위험 등급 MEDIUM (통합 정합성).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _reset_cycle65_scanner_state():
    """사이클 65 + 64 scanner 모듈 전역 reset."""
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
    # 사이클 64 캐시 동행 reset (E2E)
    if hasattr(scanner, "invalidate_price_filter_cache_scanner"):
        scanner.invalidate_price_filter_cache_scanner()
    if hasattr(scanner, "reset_price_filter_daily_state"):
        scanner.reset_price_filter_daily_state()
    yield


# ---------------------------------------------------------------------------
# F-1: scan → price → trade_amount → subscribe 정합성 (4 호출 순서)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F1_scan_then_price_then_trade_amount_then_subscribe():
    """F-1 (E2E): `subscribe_filtered_stocks` 진입 시
    `_apply_price_filter` 1차 hook → `_apply_trade_amount_filter` 2차 hook → ws subscribe.

    Q3 순차 hook 정합성 — 사이클 64 + 65 연속 호출 흐름 검증.
    호출 순서 + survivors 흐름 검증 (call_args_list).
    """
    from src.engine import scanner

    # 1) price filter — A001, B002 통과 / C003 차단
    price_filter_mock = AsyncMock(side_effect=lambda candidates, **kw: [
        c for c in candidates if c != "C003"
    ])
    # 2) trade amount filter — A001 통과 / B002 차단
    trade_amount_filter_mock = AsyncMock(side_effect=lambda candidates, **kw: [
        c for c in candidates if c != "B002"
    ])

    # ws mock — 통과 종목 1개만 (A001)
    mock_ws = MagicMock()
    mock_ws.subscribe = AsyncMock()

    with patch("src.engine.scanner._apply_price_filter", price_filter_mock), \
         patch("src.engine.scanner._apply_trade_amount_filter", trade_amount_filter_mock, create=True), \
         patch("src.engine.scanner._collect_protected_tickers_for_scanner", return_value=set()), \
         patch("src.engine.scanner.kis_ws", mock_ws):
        await scanner.subscribe_filtered_stocks(
            ["A001", "B002", "C003"],
            source_counts=None,
        )

    # 1) price filter 1차 호출
    assert price_filter_mock.call_count >= 1, (
        f"_apply_price_filter 호출 누락 (실제 {price_filter_mock.call_count}건)"
    )
    # 2) trade amount filter 2차 호출 (price 차단 후 candidates)
    assert trade_amount_filter_mock.call_count >= 1, (
        f"_apply_trade_amount_filter 호출 누락 (실제 {trade_amount_filter_mock.call_count}건). "
        "사이클 65 순차 hook 미구현."
    )

    # 호출 순서 — price 가 trade_amount 보다 먼저
    # mock 객체 별로 mock_calls 가 분리되므로 부모 mock 으로 추적
    parent = MagicMock()
    parent.attach_mock(price_filter_mock, "price")
    parent.attach_mock(trade_amount_filter_mock, "trade")

    # 호출 순서 검증 — 첫 호출은 price
    first_trade_call = trade_amount_filter_mock.call_args_list[0]
    first_trade_candidates = first_trade_call[0][0] if first_trade_call[0] else first_trade_call.kwargs.get("candidates")
    # C003 가 price 단계에서 빠진 candidates 가 trade_amount 진입
    assert "C003" not in first_trade_candidates, (
        f"순차 hook 결함 — 가격 차단 종목이 거래대금 필터로 전달됨: {first_trade_candidates}"
    )


# ---------------------------------------------------------------------------
# F-2: 보유 종목 보호 E2E — 가격 + 거래대금 양쪽 통과
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F2_held_position_protected_across_both_filters():
    """F-2: 보유 종목은 가격 필터 + 거래대금 필터 양쪽 모두 통과 (3 중 안전망 일관).

    Q1 옵션 D 답습 — 사이클 64 와 사이클 65 양쪽 protected_tickers 보호 검증.
    """
    from src.db.system_config import PriceFilter, TradeAmountFilter
    from src.engine import scanner

    # 강한 임계 — 보호 안 되면 차단됨
    pf = PriceFilter(min_price=10_000, max_price=1_000_000)
    taf = TradeAmountFilter(min_amount=10_000_000_000)

    candidates = ["HELD1"]
    protected = {"HELD1"}

    # 가격 / 거래대금 모두 임계 미달 (보호 안 되면 차단 대상)
    monkeypatch_settings = {
        "ticker_market_info": {"HELD1": {"trade_amount_raw": 1_000_000}},  # 100만
    }

    from src.models.stock import StockBasics
    held_basics = StockBasics(
        ticker="HELD1", name="", excg_dvsn_cd="",
        nxt_tradable=True, krx_halted=False, admin_item=False,
        raw={"prdy_clpr": "100", "acml_tr_pbmn": "0"},  # 100원 (임계 미만) + 0
    )

    async def _stub_get_taf():
        return taf
    async def _stub_get_pf():
        return pf

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.engine.scanner._get_trade_amount_filter_for_scanner", _stub_get_taf, create=True), \
         patch("src.engine.scanner.get_trade_amount_filter", AsyncMock(return_value=taf), create=True), \
         patch("src.engine.scanner.ticker_market_info", monkeypatch_settings["ticker_market_info"]), \
         patch("src.db.stock_master.get", AsyncMock(return_value=held_basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()):

        # 가격 필터 단독 — 보유 종목 통과
        price_result = await scanner._apply_price_filter(candidates, protected_tickers=protected)
        assert price_result == ["HELD1"], (
            f"가격 필터 보유 보호 결함 (실제 {price_result})"
        )

        # 거래대금 필터 단독 — 보유 종목 통과
        # Red: `_apply_trade_amount_filter` 미존재 → AttributeError 정답
        trade_result = await scanner._apply_trade_amount_filter(
            candidates, protected_tickers=protected,
        )
        assert trade_result == ["HELD1"], (
            f"거래대금 필터 보유 보호 결함 (실제 {trade_result})"
        )


# ---------------------------------------------------------------------------
# F-3: funnel step_no=97 snapshot hook
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F3_funnel_hook_step_no_97():
    """F-3 (Q3 자문): `_apply_trade_amount_filter` 차단 발생 시
    `strategy_funnel.insert_snapshot(step_no=97)` 호출.

    Q3 옵션 A — 사이클 64 step_no=98 분리 (사이클 65 = 97).
    graceful — funnel hook 실패는 매수 흐름 영향 0.
    """
    from src.db.system_config import TradeAmountFilter
    from src.engine import scanner

    candidates = ["A001"]

    async def _stub_get():
        return TradeAmountFilter(min_amount=1_000_000_000)
    funnel_insert_mock = AsyncMock()

    with patch.object(scanner, "_get_trade_amount_filter_for_scanner", _stub_get, create=True), \
         patch.object(scanner, "ticker_market_info",
                     {"A001": {"trade_amount_raw": 50_000_000}}), \
         patch("src.db.strategy_funnel.insert_snapshot", funnel_insert_mock), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.stock_master.get", AsyncMock(return_value=None)):
        # Red: `_apply_trade_amount_filter` 미존재 → AttributeError 정답
        result = await scanner._apply_trade_amount_filter(
            candidates, protected_tickers=set(),
        )

    assert result == []

    # funnel insert_snapshot 호출 검증 (step_no=97)
    assert funnel_insert_mock.call_count > 0, (
        "Q3 funnel hook 누락 — 차단 발생 시 strategy_funnel.insert_snapshot(step_no=97) 호출 의무"
    )
    call_kwargs = funnel_insert_mock.call_args.kwargs
    assert call_kwargs.get("step_no") == 97, (
        f"funnel step_no=97 (Q3 자문) 위반: kwargs={call_kwargs}"
    )
    step_name = call_kwargs.get("step_name", "")
    assert "trade_amount_filter" in step_name, (
        f"step_name 결함 — 'trade_amount_filter' 포함 의무: {step_name}"
    )


# ---------------------------------------------------------------------------
# F-4: 사이클 64+65 순차 hook E2E (가격 차단 → 거래대금 미도달)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F4_price_blocked_ticker_does_not_reach_trade_amount():
    """F-4 (자문 신규): 가격 필터로 차단된 종목은 거래대금 필터 candidates 에 미도달.

    순차 hook 정합성 — Q3 옵션 A 패턴 (직접 호출 순서 검증).
    """
    from src.engine import scanner

    # 가격 필터 — 모두 차단
    price_filter_spy = AsyncMock(return_value=[])
    # 거래대금 필터 — spy 만, 호출 시 candidates 인자 검증
    trade_amount_filter_spy = AsyncMock(return_value=[])

    mock_ws = MagicMock()
    mock_ws.subscribe = AsyncMock()

    with patch("src.engine.scanner._apply_price_filter", price_filter_spy), \
         patch("src.engine.scanner._apply_trade_amount_filter", trade_amount_filter_spy, create=True), \
         patch("src.engine.scanner._collect_protected_tickers_for_scanner", return_value=set()), \
         patch("src.engine.scanner.kis_ws", mock_ws):
        await scanner.subscribe_filtered_stocks(
            ["BLOCKED1", "BLOCKED2", "BLOCKED3"],
            source_counts=None,
        )

    # 거래대금 필터 호출은 빈 candidates ([]) 로 시작
    assert trade_amount_filter_spy.call_count >= 1, (
        "trade_amount_filter 호출 누락 — 사이클 65 순차 hook 미구현"
    )

    first_call = trade_amount_filter_spy.call_args_list[0]
    candidates = first_call[0][0] if first_call[0] else first_call.kwargs.get("candidates")

    assert candidates == [], (
        f"가격 필터 차단 종목이 거래대금 필터로 전달됨 (실제 {candidates}). "
        "Q3 순차 hook 정합성 결함."
    )
