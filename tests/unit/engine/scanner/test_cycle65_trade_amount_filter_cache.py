"""사이클 65 (2026-06-06) Red — D 60s TTL 캐시 + E DailyEmitCap (4 케이스).

> **선행 명세**: `_workspace/red/cycle65_trade_amount_filter.md` (§File 5)
> **설계 카드 v2**: `_workspace/cycle65_trade_amount_filter_design_card.md` §2.5 / §2.6
> **자문 응답**: Q4 별도 캐시 + Q7-1 unsubscribe 0건 (HIGH 영속)
> **선례**: 사이클 56-E `BUY_BLOCK_CACHE_TTL=60.0` + 사이클 64 D/E 패턴 답습

요구 행위 (Red 단계 모두 AttributeError 정답 — `_get_trade_amount_filter_for_scanner` /
`invalidate_trade_amount_filter_cache_scanner` / `_trade_amount_filter_*` 필드 미존재):

- D-1 [MEDIUM]: 60s 내 재호출 시 DB 호출 1건 (캐시 hit, freezegun)
- D-2 [LOW, Q7-1 HIGH]: invalidate 후 ws.unsubscribe 호출 0건 (KIS LMS chain 차단)
- E-1 [LOW]: 동일 ticker 차단 2회 → write_log 1회만 (DailyEmitCap)
- E-2 [LOW]: reset 후 동일 ticker 차단 → write_log 재호출
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_cycle65_scanner_state():
    """사이클 65 scanner 모듈 전역 reset."""
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


# ---------------------------------------------------------------------------
# D-1: 60s 내 재호출 시 DB 호출 1건
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_D1_cache_hit_within_60s_no_db_call():
    """D-1: 1초 간격 60회 호출 시 DB 호출 1건 (TTL 캐시 동작).

    사이클 56-E BUY_BLOCK_CACHE_TTL=60.0 답습. 분당 1,800 DB 쿼리 → 1.
    """
    from src.db.system_config import TradeAmountFilter
    from src.engine import scanner  # Red: _get_trade_amount_filter_for_scanner 미존재

    taf = TradeAmountFilter(min_amount=1_000_000_000)
    db_get_mock = AsyncMock(return_value=taf)

    with patch("src.engine.scanner.get_trade_amount_filter", db_get_mock, create=True):
        base = 1_000_000.0
        # 1초 간격 60회 (60s 이내 TTL 만료 *전*)
        with patch("time.monotonic", side_effect=[base + i for i in range(61)]):
            for _ in range(60):
                # Red: `_get_trade_amount_filter_for_scanner` 미존재 → AttributeError 정답
                result = await scanner._get_trade_amount_filter_for_scanner()
                assert result == taf

    assert db_get_mock.call_count == 1, (
        f"캐시 hit 결함 — 60s 내 60회 호출 시 DB 1건 의무 (실제 {db_get_mock.call_count}건). "
        "사이클 56-E BUY_BLOCK_CACHE_TTL=60.0 답습 의무."
    )


# ---------------------------------------------------------------------------
# D-2 (Q7-1 HIGH): invalidate 시 unsubscribe 호출 0건
# ---------------------------------------------------------------------------
def test_D2_invalidate_does_not_trigger_unsubscribe():
    """D-2 (Q7-1 HIGH): `invalidate_trade_amount_filter_cache_scanner()` 호출 시
    `kis_ws_pool.unsubscribe` 호출 0건 (KIS LMS chain 차단).

    자문 §Q7-1 HIGH 답습: "invalidate 가 unsubscribe 발화 안 함 — 다음 `_scan_loop` 5분
    자연 delta 위임". 즉시 unsubscribe = KIS 등록/해제 race → 사이클 17 OPSP0002 폭주 재발 위험.
    """
    from src.db.system_config import TradeAmountFilter
    from src.engine import scanner

    # ws_pool.unsubscribe mock — 호출 0 검증 의무
    mock_pool = MagicMock()
    mock_pool.unsubscribe = MagicMock()

    # 캐시 사전 주입
    if hasattr(scanner, "_trade_amount_filter_cache"):
        scanner._trade_amount_filter_cache = TradeAmountFilter(min_amount=1_000_000_000)

    with patch("src.engine.scanner.kis_ws_pool", mock_pool):
        # Red: `invalidate_trade_amount_filter_cache_scanner` 미존재 → AttributeError 정답
        scanner.invalidate_trade_amount_filter_cache_scanner()

    # 1) 캐시 무효화 검증
    assert scanner._trade_amount_filter_cache is None, "캐시 무효화 결함"

    # 2) Q7-1 핵심 — unsubscribe 호출 0건
    mock_pool.unsubscribe.assert_not_called()
    unsub_calls = [c for c in mock_pool.method_calls
                   if "unsubscribe" in str(c).lower()]
    assert len(unsub_calls) == 0, (
        f"Q7-1 자문 위반 — invalidate 시 unsubscribe 호출 {len(unsub_calls)}건 발생 "
        f"(KIS LMS chain 위험, 사이클 17 OPSP0002 재발 위험)"
    )


# ---------------------------------------------------------------------------
# E-1: 동일 ticker 차단 2회 → write_log 1회만
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_E1_emit_cap_logs_once_per_ticker(monkeypatch):
    """E-1: 동일 ticker 차단 2회 → `system_logs.write_log` 1회만 발화.

    `_trade_amount_filter_scanner_skip_logged_today: DailyEmitCap[str]` cap.
    매 스캔 폭주 차단.
    """
    from src.db.system_config import TradeAmountFilter
    from src.engine import scanner

    write_log_mock = AsyncMock()

    async def _stub_get():
        return TradeAmountFilter(min_amount=1_000_000_000)
    monkeypatch.setattr(
        scanner, "_get_trade_amount_filter_for_scanner", _stub_get,
        raising=False,
    )
    monkeypatch.setattr(
        scanner, "ticker_market_info",
        {"A001": {"trade_amount_raw": 50_000_000}},  # 5천만 < 10억
        raising=False,
    )

    # write_log mock — `_apply_trade_amount_filter` 내부 import 경로 patch
    with patch("src.db.system_logs.write_log", write_log_mock), \
         patch("src.db.stock_master.get", AsyncMock(return_value=None)):
        # 사전 cap clear (autouse fixture 이후 추가 안전)
        if hasattr(scanner, "_trade_amount_filter_scanner_skip_logged_today"):
            scanner._trade_amount_filter_scanner_skip_logged_today.clear()

        await scanner._apply_trade_amount_filter(["A001"], protected_tickers=set())
        await scanner._apply_trade_amount_filter(["A001"], protected_tickers=set())

    # 1회/ticker/일 cap 검증 — write_log 1회만
    skip_calls = [
        c for c in write_log_mock.call_args_list
        if "[trade_amount_filter_scanner_skip]" in str(c)
    ]
    assert len(skip_calls) == 1, (
        f"DailyEmitCap 위반 — 동일 ticker 2회 차단 시 write_log 1회 의무 (실제 {len(skip_calls)}회)"
    )


# ---------------------------------------------------------------------------
# E-2: reset 후 동일 ticker 차단 → write_log 재호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_E2_reset_daily_state_re_enables_emit(monkeypatch):
    """E-2: `reset_trade_amount_filter_daily_state()` 후 동일 ticker 차단 → write_log 재호출.

    매일 자정 reset → 다음 영업일 재 emit 검증.
    """
    from src.db.system_config import TradeAmountFilter
    from src.engine import scanner

    write_log_mock = AsyncMock()

    async def _stub_get():
        return TradeAmountFilter(min_amount=1_000_000_000)
    monkeypatch.setattr(
        scanner, "_get_trade_amount_filter_for_scanner", _stub_get,
        raising=False,
    )
    monkeypatch.setattr(
        scanner, "ticker_market_info",
        {"A001": {"trade_amount_raw": 50_000_000}},
        raising=False,
    )

    with patch("src.db.system_logs.write_log", write_log_mock), \
         patch("src.db.stock_master.get", AsyncMock(return_value=None)):
        if hasattr(scanner, "_trade_amount_filter_scanner_skip_logged_today"):
            scanner._trade_amount_filter_scanner_skip_logged_today.clear()

        # 1회 차단 → write_log 1회
        await scanner._apply_trade_amount_filter(["A001"], protected_tickers=set())

        # reset → cap clear (다음 영업일 시뮬레이션)
        # Red: `reset_trade_amount_filter_daily_state` 미존재 → AttributeError 정답
        scanner.reset_trade_amount_filter_daily_state()

        # 2회 차단 → write_log 추가 1회 (총 2회)
        await scanner._apply_trade_amount_filter(["A001"], protected_tickers=set())

    skip_calls = [
        c for c in write_log_mock.call_args_list
        if "[trade_amount_filter_scanner_skip]" in str(c)
    ]
    assert len(skip_calls) == 2, (
        f"reset 후 재 emit 결함 — reset 후 동일 ticker 차단 시 write_log 재호출 의무 "
        f"(실제 {len(skip_calls)}회). CLAUDE.md `_reset_daily_state` 동행 규칙 위반."
    )
