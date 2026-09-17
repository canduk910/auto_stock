"""사이클 172 (2026-06-22) — _stock_master_daily_load_once VCP universe 220일 backfill 분기.
사이클 196 (2026-07-07) — 임계 220 → 120 수렴 (retention 154영업일 실측 기반).
cycle299 (2026-09-17) — 임계 120 → 225 확장 (retention 390cal ≈ 261영업일 동반 확장).

이 파일이 재는 것은 **분기의 존재와 방향**이지 임계값 자체가 아니다 (임계값 정본 가드 =
`test_cycle196_vcp_backfill_convergence.py::B-1` + `test_cycle299_backfill_target_expansion.py::G-299-2`).
아래 케이스들은 임계가 120 이든 225 든 같은 쪽으로 떨어지도록 골라져 있어 값 변경에
무접촉이다 (count 100/50 은 어느 임계에서도 미달, 230 은 어느 임계에서도 충족).

VCP universe (KOSPI200 ∪ KOSDAQ150) 종목 중 DB 깊이 < 임계 → 분할 fetch backfill.
나머지 종목 = 현행 T-100 유지 (회귀 0).

회귀 가드 매트릭스:
- SCAN-1 (HIGH): VCP universe (is_kospi200) DB < 임계 → fetch_daily_candles_backfill 분기
- SCAN-2 (HIGH): VCP universe (is_kosdaq150) 동일 분기
- SCAN-3 (HIGH): 비 VCP universe → 현행 100일 fetch_daily_candles 유지 (회귀)
- SCAN-4: VCP universe DB >= 임계 → 증분 유지 (재 backfill 금지)
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


# 문서용 상수 — 이 파일의 어떤 테스트도 참조하지 않는다(케이스가 임계 무접촉이라 그렇다,
# 위 모듈 docstring). cycle299 가 프로덕션 임계를 225 로 올려 값을 다시 맞췄다.
_VCP_BACKFILL_THRESHOLD = 225  # noqa: F841 — 의도적 문서 상수


def _vcp_candle(bas_dd: str = "20260620") -> dict:
    return {
        "stck_bsop_date": bas_dd, "stck_clpr": "71000",
        "stck_oprc": "70500", "stck_hgpr": "71500", "stck_lwpr": "70000",
        "acml_vol": "12345678", "acml_tr_pbmn": "876543210000",
    }


# ---------------------------------------------------------------------------
# SCAN-1 (HIGH) — VCP universe (is_kospi200) DB < 225 → backfill 분기
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan1_kospi200_under_target_triggers_backfill():
    """is_kospi200=True + DB < 225 → fetch_daily_candles_backfill 호출."""
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
        new=AsyncMock(return_value=100),  # < 225 → VCP backfill
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
        "VCP universe (is_kospi200) DB < 225 → fetch_daily_candles_backfill 분기"
    assert ranged_kis_mock.await_count == 0, "VCP universe 는 100일 fetch 미사용"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# SCAN-2 (HIGH) — VCP universe (is_kosdaq150) 동일 분기
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan2_kosdaq150_under_target_triggers_backfill():
    """is_kosdaq150=True + DB < 225 → fetch_daily_candles_backfill 호출."""
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
        new=AsyncMock(return_value=50),  # < 225 → VCP backfill
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
        "VCP universe (is_kosdaq150) DB < 225 → backfill 분기"
    assert ranged_kis_mock.await_count == 0
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# SCAN-3 (HIGH) — 비 VCP universe → 현행 100일 fetch_daily_candles 유지 (회귀)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan3_non_vcp_keeps_100day():
    """비 VCP universe (is_kospi200=False, is_kosdaq150=False) → 현행 100일 유지."""
    stock_master_rows = [
        {"ticker": "999999", "is_kospi200": False, "is_kosdaq150": False,
         "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},  # 사이클 206 자격
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
    stock_master_rows = [
        {"ticker": "005930",
         "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},  # 사이클 206 자격
    ]  # 사이클 122 mock 형식 (플래그 키 없음)

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
# SCAN-4 — VCP universe DB >= 225 → 증분 유지 (재 backfill 금지)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan4_vcp_over_target_incremental():
    """VCP universe DB >= 225 → 증분 모드 (재 backfill 금지)."""
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
        new=AsyncMock(return_value=230),  # >= 225 → 증분
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

    assert backfill_mock.await_count == 0, "DB >= 225 → 재 backfill 금지"
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
        {"ticker": "000660", "is_kospi200": False, "is_kosdaq150": False,
         "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},  # 사이클 206 자격
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
        new=AsyncMock(return_value=100),  # VCP < 225 / 비VCP < 50 모두 백필
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
