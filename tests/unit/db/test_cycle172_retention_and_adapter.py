"""사이클 172 (2026-06-22) — DAILY_RETENTION_DAYS 230 + get_recent_daily_normalized 어댑터.

retention 150 → 230 (220 + 10 마진, VCP 220일 보존) + DB raw JSONB 어댑터.

회귀 가드 매트릭스:
- RET-1: DAILY_RETENTION_DAYS == 230 상수
- RET-2: purge_old_rows 로직 불변 (cutoff = today - 230, 상수만 변경)
- ADAPT-1: get_recent_daily_normalized DB 충분 → raw JSONB 반환 (KIS 키 stck_clpr 보존)
- ADAPT-2: DB miss (< min_required) → KIS fetch_daily_candles 폴백
- ADAPT-3: min_required=None 기본값 (위임 정합)
- ADAPT-4: raw 키 부재 graceful

영속 의무:
- 사이클 32 R4 protected_tickers 절대 보호 (purge 로직 불변)
- 사이클 81 G-AST1 raw JSONB 분리 (어댑터 raw 그대로 반환, 변형 0)
- 사이클 88 G-REJECT graceful
- 사이클 122 get_recent_daily_with_fallback 위임 (어댑터 = 폴백 재사용)
"""

from __future__ import annotations

import inspect
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# RET-1 — DAILY_RETENTION_DAYS == 230
# ---------------------------------------------------------------------------
def test_ret1_retention_days_230():
    """DAILY_RETENTION_DAYS = 230 (220 + 10 마진, VCP 220일 보존)."""
    from src.db.stock_master_daily import DAILY_RETENTION_DAYS

    assert DAILY_RETENTION_DAYS == 230, \
        "DAILY_RETENTION_DAYS = 230 (VCP 220일 + 10일 안전 마진)"


# ---------------------------------------------------------------------------
# RET-2 — purge_old_rows 로직 불변 (상수만 변경)
# ---------------------------------------------------------------------------
def test_ret2_purge_logic_unchanged():
    """purge_old_rows 시그너처/로직 불변 — 상수만 변경."""
    from src.db.stock_master_daily import purge_old_rows

    sig = inspect.signature(purge_old_rows)
    params = sig.parameters
    assert "cutoff_date" in params, "cutoff_date 영역 영속"
    assert "protected_tickers" in params, "protected_tickers 영역 영속"
    assert params["protected_tickers"].kind == inspect.Parameter.KEYWORD_ONLY, \
        "protected_tickers keyword-only 영속 (사이클 32 R4)"

    # purge 본체에 .lt("bas_dd", ...) + not_.in_ 영속 (로직 불변)
    src = inspect.getsource(purge_old_rows)
    assert '.lt("bas_dd"' in src, "cutoff 이전 DELETE 로직 영속"
    assert "not_.in_" in src, "protected_tickers DELETE 제외 영속"


@pytest.mark.asyncio
async def test_ret2_purge_cutoff_protected():
    """purge_old_rows — protected_tickers DELETE 제외 (사이클 32 R4 영속).

    사이클 192 의미 전환 (사이클 66 K-2) — 날짜 슬라이스 루프 배치 전환에 맞게
    mock 형식 갱신 (bulk `delete().lt()` → SELECT oldest + DELETE eq 루프).
    검증 의도 보존: protected_tickers 가 DELETE 에서 제외 + protected_count 반환.
    """
    from src.db import stock_master_daily as _smd

    # SELECT: 1회차 row 반환 → 2회차 empty (drained)
    sel_result_1 = MagicMock()
    sel_result_1.data = [{"bas_dd": "2024-12-01"}]
    sel_result_2 = MagicMock()
    sel_result_2.data = []

    del_result = MagicMock()
    del_result.count = 0

    table_mock = MagicMock()
    table_mock.select.return_value.lt.return_value.not_.in_.return_value \
        .order.return_value.limit.return_value.execute.side_effect = [
            sel_result_1, sel_result_2,
        ]
    table_mock.delete.return_value.eq.return_value.not_.in_.return_value \
        .execute.return_value = del_result

    with patch.object(_smd, "supabase") as mock_supa:
        mock_supa.table.return_value = table_mock
        result = await _smd.purge_old_rows(
            date(2025, 1, 1), protected_tickers={"005930", "000660"}
        )

    assert result["protected_count"] == 2
    table_mock.delete.return_value.eq.return_value.not_.in_.assert_called_once()


# ---------------------------------------------------------------------------
# ADAPT-1 — get_recent_daily_normalized DB 충분 → raw JSONB 반환
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_adapt1_returns_raw_jsonb():
    """DB 충분 시 raw JSONB (KIS 원본 키 stck_clpr 등 보존) 반환."""
    from src.db import stock_master_daily as _smd

    db_rows = [
        {
            "ticker": "005930",
            "bas_dd": "2026-06-20",
            "close_price": 71000,
            "raw": {"stck_bsop_date": "20260620", "stck_clpr": "71000",
                    "stck_oprc": "70500", "stck_hgpr": "71500", "stck_lwpr": "70000"},
        },
        {
            "ticker": "005930",
            "bas_dd": "2026-06-19",
            "close_price": 70500,
            "raw": {"stck_bsop_date": "20260619", "stck_clpr": "70500",
                    "stck_oprc": "70000", "stck_hgpr": "70800", "stck_lwpr": "69900"},
        },
    ]

    with patch.object(
        _smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)
    ):
        rows = await _smd.get_recent_daily_normalized("005930", 2, min_required=2)

    assert len(rows) == 2
    # raw JSONB (KIS 원본 키) 보존 — 173 prepare 의 c.get("stck_clpr") 무변경 사용
    assert rows[0].get("stck_clpr") == "71000", "KIS 원본 키 stck_clpr 보존"
    assert rows[0].get("stck_oprc") == "70500"
    assert rows[1].get("stck_clpr") == "70500"


# ---------------------------------------------------------------------------
# ADAPT-2 — DB miss (< min_required) → KIS fetch_daily_candles 폴백
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_adapt2_kis_fallback_on_miss():
    """DB 부족 (< min_required) → KIS fetch_daily_candles 폴백."""
    from src.db import stock_master_daily as _smd

    # DB 1건만 (min_required=22 미만)
    db_rows = [{"ticker": "005930", "bas_dd": "2026-06-20", "raw": {"stck_clpr": "71000"}}]
    kis_rows = [
        {"stck_bsop_date": "20260620", "stck_clpr": "71000"},
        {"stck_bsop_date": "20260619", "stck_clpr": "70500"},
    ]

    mock_fetch = AsyncMock(return_value=kis_rows)

    with patch.object(
        _smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)
    ), patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
        rows = await _smd.get_recent_daily_normalized("005930", 22, min_required=22)

    # KIS 폴백 결과 = 원본 KIS 키 (stck_clpr) 반환
    assert mock_fetch.await_count == 1, "DB 부족 → KIS 폴백 호출"
    assert rows == kis_rows
    assert rows[0].get("stck_clpr") == "71000"


# ---------------------------------------------------------------------------
# ADAPT-3 — min_required=None 기본값 (위임 정합)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_adapt3_min_required_default():
    """min_required=None 기본값 — DB 충분 판정 정상 동작."""
    from src.db import stock_master_daily as _smd

    sig = inspect.signature(_smd.get_recent_daily_normalized)
    assert "min_required" in sig.parameters
    assert sig.parameters["min_required"].kind == inspect.Parameter.KEYWORD_ONLY, \
        "min_required keyword-only"
    assert sig.parameters["min_required"].default is None, "기본값 None"

    # min_required=None 시 충분한 DB row → 폴백 없이 raw 반환
    db_rows = [
        {"ticker": "005930", "bas_dd": f"2026-06-{20-i:02d}",
         "raw": {"stck_clpr": str(71000 - i * 100)}}
        for i in range(20)
    ]
    mock_fetch = AsyncMock(return_value=[])

    with patch.object(
        _smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)
    ), patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
        rows = await _smd.get_recent_daily_normalized("005930", 20)

    assert mock_fetch.await_count == 0, "min_required=None 기본값 + DB 충분 → 폴백 0"
    assert len(rows) == 20


# ---------------------------------------------------------------------------
# ADAPT-4 — raw 키 부재 graceful
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_adapt4_raw_missing_graceful():
    """DB row 에 raw 키 부재 시 row 자체 반환 (graceful)."""
    from src.db import stock_master_daily as _smd

    # raw 키 없는 비정상 row (graceful 통과)
    db_rows = [
        {"ticker": "005930", "bas_dd": "2026-06-20", "close_price": 71000},
        {"ticker": "005930", "bas_dd": "2026-06-19", "close_price": 70500},
    ]

    with patch.object(
        _smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)
    ):
        rows = await _smd.get_recent_daily_normalized("005930", 2, min_required=2)

    # raw 부재 → row 자체 반환 (예외 없음)
    assert len(rows) == 2
    assert rows[0].get("close_price") == 71000
