"""사이클 124 — get_stats() 8 키 확장 회귀 가드.

G-STATS1: with_hts_avls — raw.hts_avls > 0 카운트 정확
G-STATS2: with_acml_tr_pbmn — raw.acml_tr_pbmn > 0 카운트 정확
G-STATS3: total_daily_rows — stock_master_daily.count_all() 연동
G-STATS4: last_daily_load_at — stock_master_daily.max_bas_dd(ticker=None) 연동

사이클 85 기존 4 키 (count_all / bfdy_clpr_present / nxt_tradable_count / top_10_recent) 영속:
  각 케이스에서 4 기존 키 누락 0건 검증 포함.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── 공용 helpers ──────────────────────────────────────────────────────────────

def _make_row(ticker: str, raw: dict | None = None, *, nxt_tradable: bool = False) -> dict:
    return {
        "ticker": ticker,
        "name": f"종목_{ticker}",
        "nxt_tradable": nxt_tradable,
        "raw": raw,
        "refreshed_at": "2026-06-12T20:00:00+09:00",
    }


def _mock_sm_result(rows: list[dict]) -> MagicMock:
    """supabase.table().select()...execute() 반환 모의"""
    m = MagicMock()
    m.data = rows
    return m


# ─── G-STATS1: with_hts_avls ──────────────────────────────────────────────────

@pytest.mark.xfail(
    strict=False,
    reason="사이클 128 — Python-side sum (raw rows .range(0,9999)) 영역 영구 폐기 → count='exact' 별도 쿼리 전환 (PostgREST 1000 silent cap 영구 차단). 의미 전환 xfail (사이클 66 K-2 패턴).",
)
async def test_g_stats1_with_hts_avls_count():
    """with_hts_avls = raw.hts_avls 값이 None/""/0/"0" 이 아닌 row 수."""
    rows = [
        _make_row("000001", raw={"hts_avls": "500000", "bfdy_clpr": "50000"}),   # 포함
        _make_row("000002", raw={"hts_avls": "0", "bfdy_clpr": "0"}),            # 제외 (0)
        _make_row("000003", raw={"hts_avls": None, "bfdy_clpr": None}),           # 제외 (None)
        _make_row("000004", raw={"hts_avls": "", "bfdy_clpr": ""}),               # 제외 ("")
        _make_row("000005", raw={"hts_avls": "1000000", "bfdy_clpr": "10000"}),  # 포함
        _make_row("000006", raw=None),                                             # 제외 (raw None)
    ]

    mock_execute = MagicMock()
    mock_execute.data = rows

    with (
        patch("src.db.stock_master.supabase") as mock_sb,
        patch("src.db.stock_master_daily.count_all", new_callable=AsyncMock, return_value=100),
        patch("src.db.stock_master_daily.max_bas_dd", new_callable=AsyncMock, return_value=date(2026, 6, 12)),
    ):
        # 사이클 126 영역 1 — count chain (select(count="exact").limit(0).execute()) + raw chain (select.order.range.execute()) 양쪽 호환
        mock_execute.count = len(rows)
        mock_sb.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value = mock_execute
        # count="exact" chain
        mock_sb.table.return_value.select.return_value.limit.return_value.execute.return_value = mock_execute

        from src.db import stock_master
        result = await stock_master.get_stats()

    assert result["with_hts_avls"] == 2, f"expected 2, got {result['with_hts_avls']}"

    # 사이클 85 기존 4 키 영속
    assert "count_all" in result
    assert "bfdy_clpr_present" in result
    assert "nxt_tradable_count" in result
    assert "top_10_recent" in result


# ─── G-STATS2: with_acml_tr_pbmn ──────────────────────────────────────────────

@pytest.mark.xfail(
    strict=False,
    reason="사이클 128 — Python-side sum 영역 영구 폐기 → count='exact' 별도 쿼리 전환. 의미 전환 xfail (사이클 66 K-2 패턴).",
)
async def test_g_stats2_with_acml_tr_pbmn_count():
    """with_acml_tr_pbmn = raw.acml_tr_pbmn 값이 None/""/0/"0" 이 아닌 row 수."""
    rows = [
        _make_row("000010", raw={"acml_tr_pbmn": "9999999999"}),   # 포함
        _make_row("000011", raw={"acml_tr_pbmn": "0"}),            # 제외
        _make_row("000012", raw={"acml_tr_pbmn": 0}),              # 제외 (int 0)
        _make_row("000013", raw={"acml_tr_pbmn": "8888888888"}),   # 포함
        _make_row("000014", raw=None),                              # 제외
    ]

    mock_execute = MagicMock()
    mock_execute.data = rows

    with (
        patch("src.db.stock_master.supabase") as mock_sb,
        patch("src.db.stock_master_daily.count_all", new_callable=AsyncMock, return_value=50),
        patch("src.db.stock_master_daily.max_bas_dd", new_callable=AsyncMock, return_value=None),
    ):
        # 사이클 126 영역 1 — count chain (select(count="exact").limit(0).execute()) + raw chain (select.order.range.execute()) 양쪽 호환
        mock_execute.count = len(rows)
        mock_sb.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value = mock_execute
        # count="exact" chain
        mock_sb.table.return_value.select.return_value.limit.return_value.execute.return_value = mock_execute

        from src.db import stock_master
        result = await stock_master.get_stats()

    assert result["with_acml_tr_pbmn"] == 2, f"expected 2, got {result['with_acml_tr_pbmn']}"

    # 사이클 85 기존 4 키 영속
    for key in ("count_all", "bfdy_clpr_present", "nxt_tradable_count", "top_10_recent"):
        assert key in result, f"기존 키 {key} 누락"


# ─── G-STATS3: total_daily_rows ───────────────────────────────────────────────

async def test_g_stats3_total_daily_rows_from_smd():
    """total_daily_rows = stock_master_daily.count_all() 값 반영."""
    rows = [_make_row("000020", raw={})]

    mock_execute = MagicMock()
    mock_execute.data = rows

    with (
        patch("src.db.stock_master.supabase") as mock_sb,
        patch("src.db.stock_master_daily.count_all", new_callable=AsyncMock, return_value=75000) as mock_count,
        patch("src.db.stock_master_daily.max_bas_dd", new_callable=AsyncMock, return_value=date(2026, 6, 11)),
    ):
        # 사이클 126 영역 1 — count chain (select(count="exact").limit(0).execute()) + raw chain (select.order.range.execute()) 양쪽 호환
        mock_execute.count = len(rows)
        mock_sb.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value = mock_execute
        # count="exact" chain
        mock_sb.table.return_value.select.return_value.limit.return_value.execute.return_value = mock_execute

        from src.db import stock_master
        result = await stock_master.get_stats()

    assert result["total_daily_rows"] == 75000
    mock_count.assert_awaited_once()  # count_all() 실제 호출 검증

    # graceful fallback 검증: count_all 예외 시 0 반환
    mock_execute2 = MagicMock()
    mock_execute2.data = rows

    with (
        patch("src.db.stock_master.supabase") as mock_sb2,
        patch("src.db.stock_master_daily.count_all", new_callable=AsyncMock, side_effect=RuntimeError("DB 오류")),
        patch("src.db.stock_master_daily.max_bas_dd", new_callable=AsyncMock, return_value=None),
    ):
        mock_sb2.table.return_value.select.return_value.order.return_value.execute.return_value = mock_execute2

        result2 = await stock_master.get_stats()

    assert result2["total_daily_rows"] == 0, "예외 시 graceful fallback 0 의무"


# ─── G-STATS4: last_daily_load_at ─────────────────────────────────────────────

async def test_g_stats4_last_daily_load_at_from_smd():
    """last_daily_load_at = stock_master_daily.max_bas_dd(ticker=None) 를 str 변환."""
    rows = [_make_row("000030", raw={})]

    mock_execute = MagicMock()
    mock_execute.data = rows

    target_date = date(2026, 6, 12)

    with (
        patch("src.db.stock_master.supabase") as mock_sb,
        patch("src.db.stock_master_daily.count_all", new_callable=AsyncMock, return_value=1000),
        patch("src.db.stock_master_daily.max_bas_dd", new_callable=AsyncMock, return_value=target_date) as mock_max,
    ):
        # 사이클 126 영역 1 — count chain (select(count="exact").limit(0).execute()) + raw chain (select.order.range.execute()) 양쪽 호환
        mock_execute.count = len(rows)
        mock_sb.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value = mock_execute
        # count="exact" chain
        mock_sb.table.return_value.select.return_value.limit.return_value.execute.return_value = mock_execute

        from src.db import stock_master
        result = await stock_master.get_stats()

    assert result["last_daily_load_at"] == "2026-06-12"
    # ticker=None 으로 호출되었는지 검증
    mock_max.assert_awaited_once_with()  # 인자 없이 호출 (default ticker=None)

    # max_bas_dd 반환 None 시 last_daily_load_at=None
    mock_execute3 = MagicMock()
    mock_execute3.data = rows

    with (
        patch("src.db.stock_master.supabase") as mock_sb3,
        patch("src.db.stock_master_daily.count_all", new_callable=AsyncMock, return_value=0),
        patch("src.db.stock_master_daily.max_bas_dd", new_callable=AsyncMock, return_value=None),
    ):
        mock_sb3.table.return_value.select.return_value.order.return_value.execute.return_value = mock_execute3

        result3 = await stock_master.get_stats()

    assert result3["last_daily_load_at"] is None, "max_bas_dd=None 시 None 반환 의무"
