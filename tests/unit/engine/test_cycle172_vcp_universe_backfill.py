"""사이클 172 (2026-06-22) — _stock_master_daily_load_once VCP universe 220일 backfill 분기.
사이클 196 (2026-07-07) — 임계 220 → 120 수렴 (retention 154영업일 실측 기반).

VCP universe (KOSPI200 ∪ KOSDAQ150) 종목 중 DB 깊이 < 120 → 120일 backfill (분할 fetch).
나머지 종목 = 현행 T-100 유지 (회귀 0).

회귀 가드 매트릭스:
- SCAN-1 (HIGH): VCP universe (is_kospi200) DB < 120 → fetch_daily_candles_backfill 분기
- SCAN-2 (HIGH): VCP universe (is_kosdaq150) 동일 분기
- SCAN-3 (HIGH): 비 VCP universe → 현행 100일 fetch_daily_candles 유지 (회귀)
- SCAN-4: VCP universe DB >= 120 → 증분 유지 (재 backfill 금지)
- SCAN-5: graceful (backfill 실패 → 다음 ticker 진행)
- SAFETY-1 (HIGH): 매매 무관 — risk/order_engine/realtime/auth import 0

영속 의무:
- 사이클 38 명문화 (scanner 매수 진입 전 영역 — 16:00 daily task 만)
- 사이클 88 G-REJECT graceful
- 사이클 122 백필/증분 분기 영속 (비 VCP universe)
- 사이클 153 is_kospi200/is_kosdaq150 컬럼 (list_all .select("*") 포함)
"""

from __future__ import annotations

import ast
import inspect
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import scanner

pytestmark = pytest.mark.unit


_VCP_BACKFILL_THRESHOLD = 220


def _vcp_candle(bas_dd: str = "20260620") -> dict:
    return {
        "stck_bsop_date": bas_dd, "stck_clpr": "71000",
        "stck_oprc": "70500", "stck_hgpr": "71500", "stck_lwpr": "70000",
        "acml_vol": "12345678", "acml_tr_pbmn": "876543210000",
    }


# ---------------------------------------------------------------------------
# SCAN-1 (HIGH) — VCP universe (is_kospi200) DB < 220 → backfill 분기
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan1_kospi200_under_220_triggers_backfill():
    """is_kospi200=True + DB < 220 → fetch_daily_candles_backfill 호출."""
    stock_master_rows = [
        {"ticker": "005930", "is_kospi200": True, "is_kosdaq150": False},
    ]

    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    ranged_kis_mock = AsyncMock(return_value=[_vcp_candle()])

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=100),  # < 220 → VCP backfill
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=ranged_kis_mock,
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    assert backfill_mock.await_count == 1, \
        "VCP universe (is_kospi200) DB < 220 → fetch_daily_candles_backfill 분기"
    assert ranged_kis_mock.await_count == 0, "VCP universe 는 100일 fetch 미사용"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# SCAN-2 (HIGH) — VCP universe (is_kosdaq150) 동일 분기
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan2_kosdaq150_under_220_triggers_backfill():
    """is_kosdaq150=True + DB < 220 → fetch_daily_candles_backfill 호출."""
    stock_master_rows = [
        {"ticker": "247540", "is_kospi200": False, "is_kosdaq150": True},
    ]

    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    ranged_kis_mock = AsyncMock(return_value=[_vcp_candle()])

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=50),  # < 220 → VCP backfill
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=ranged_kis_mock,
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    assert backfill_mock.await_count == 1, \
        "VCP universe (is_kosdaq150) DB < 220 → backfill 분기"
    assert ranged_kis_mock.await_count == 0
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# SCAN-3 (HIGH) — 비 VCP universe → 현행 100일 fetch_daily_candles 유지 (회귀)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan3_non_vcp_keeps_100day():
    """비 VCP universe (is_kospi200=False, is_kosdaq150=False) → 현행 100일 유지."""
    stock_master_rows = [
        {"ticker": "999999", "is_kospi200": False, "is_kosdaq150": False},
    ]

    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    captured_days: list[int] = []

    async def capture_fetch(ticker, days):
        captured_days.append(days)
        return [_vcp_candle()]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=10),  # < 50 백필 (사이클 122 현행)
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=capture_fetch),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    assert backfill_mock.await_count == 0, "비 VCP universe 는 backfill 미사용"
    assert 100 in captured_days, "비 VCP universe 현행 100일 fetch 유지 (회귀)"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# SCAN-3b — is_kospi200 키 부재 (기존 사이클 122 mock) → 비 VCP 취급 (회귀 0)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan3b_missing_flag_keys_treated_non_vcp():
    """is_kospi200/is_kosdaq150 키 부재 row → 비 VCP 취급 (기존 테스트 회귀 0)."""
    stock_master_rows = [{"ticker": "005930"}]  # 사이클 122 mock 형식 (플래그 키 없음)

    backfill_mock = AsyncMock(return_value=[_vcp_candle()])

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=10),
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=[_vcp_candle()]),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    assert backfill_mock.await_count == 0, "플래그 키 부재 → 비 VCP 취급 (회귀 0)"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# SCAN-4 — VCP universe DB >= 220 → 증분 유지 (재 backfill 금지)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan4_vcp_over_220_incremental():
    """VCP universe DB >= 220 → 증분 모드 (재 backfill 금지)."""
    stock_master_rows = [
        {"ticker": "005930", "is_kospi200": True, "is_kosdaq150": False},
    ]

    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    captured_days: list[int] = []

    async def capture_fetch(ticker, days):
        captured_days.append(days)
        return [_vcp_candle()]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=date(2026, 6, 1)),  # 미래 아님 → 적재 진행
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=230),  # >= 220 → 증분
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=capture_fetch),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    assert backfill_mock.await_count == 0, "DB >= 220 → 재 backfill 금지"
    assert 7 in captured_days, "증분 모드 (T-7일) 유지"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# SCAN-5 — graceful (backfill 실패 → 다음 ticker 진행)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan5_backfill_failure_graceful():
    """VCP backfill 실패 → 사이클 88 G-REJECT graceful (다음 ticker 진행)."""
    stock_master_rows = [
        {"ticker": "005930", "is_kospi200": True, "is_kosdaq150": False},
        {"ticker": "000660", "is_kospi200": False, "is_kosdaq150": False},
    ]

    async def backfill_fail(ticker, **kwargs):
        raise RuntimeError("KIS backfill 실패")

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=100),  # VCP < 220 / 비VCP < 50 모두 백필
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=AsyncMock(side_effect=backfill_fail),
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=[_vcp_candle()]),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    # 005930 VCP backfill 실패 → failed++, 000660 비VCP 정상 진행
    assert summary["failed"] >= 1, "VCP backfill 실패 → failed++ graceful"
    assert summary["fetched"] >= 1, "다음 ticker (비VCP) 정상 진행"


# ---------------------------------------------------------------------------
# SAFETY-1 (HIGH) — 매매 무관 (scanner _stock_master_daily_load_once import 0)
# ---------------------------------------------------------------------------
def test_safety1_no_trading_hot_path_import():
    """_stock_master_daily_load_once 본체 — risk/order_engine/realtime/auth 참조 0."""
    src = inspect.getsource(scanner._stock_master_daily_load_once)
    for forbidden in ("risk.on_tick", "order_engine", "execute_buy", "execute_sell",
                      "place_order", "check_exit_signal", "check_buy_signal"):
        assert forbidden not in src, \
            f"_stock_master_daily_load_once 매매 hot path 참조 0 의무: {forbidden}"
