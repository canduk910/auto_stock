"""사이클 173 (2026-06-22) — get_recent_daily_normalized 락/신선도 게이트 보강.

어댑터에 2 게이트 추가 (172 = raw 반환 + min_required 폴백, 173 = 락 + 신선도 폴백):
- 락 게이트 (G-EQ-3, 최우선 HIGH): DB 윈도우 내 1 row 라도 락 발생
  (flng_cls_code not in ("","00") OR abs(prtt_rate) > 0) → KIS 폴백 강제.
- 신선도 게이트 (G-EQ-4): max_bas_dd 가 today-staleness_days(=4) 보다 오래 → KIS 폴백.

★ team-leader 운영 DB 실측 확정 (자문 보정):
- flng_cls_code 기본 = "" / "00" (운영 실측 99.6% "00"). 비기본 (01/02/03/05) = 락.
- prtt_rate 기본 = 0 / "" / None (운영 실측 99.7% "0.0000"). 자문의 != 1.0 은 틀림 (전 종목 폴백).
  비-0 = 분할/병합/배당락 조정.
- 검사 대상 = get_recent_daily 반환 DB row 의 top-level flng_cls_code / prtt_rate 컬럼
  (raw JSONB 와 별개 정규화 컬럼, migration 033). KIS 추가 호출 0건 탐지.

영속 의무:
- 사이클 172 ADAPT-1~4 회귀 보존 (정상 fixture = 락/신선도 컬럼 부재 → 기본값 통과)
- 사이클 81 G-AST1 raw JSONB 변형 0
- 사이클 88 G-REJECT graceful
"""

from __future__ import annotations

import inspect
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _normal_db_rows(n: int, *, base_dd: date | None = None) -> list[dict]:
    """정상 (락 없음) DB rows — top-level flng_cls_code="00" / prtt_rate="0.0000"."""
    base_dd = base_dd or date(2026, 6, 20)
    rows = []
    for i in range(n):
        dd = base_dd - timedelta(days=i)
        rows.append({
            "ticker": "005930",
            "bas_dd": dd.isoformat(),
            "close_price": 71000 - i * 100,
            "flng_cls_code": "00",
            "prtt_rate": "0.0000",
            "raw": {
                "stck_bsop_date": dd.strftime("%Y%m%d"),
                "stck_clpr": str(71000 - i * 100),
                "stck_oprc": str(70500 - i * 100),
                "stck_hgpr": str(71500 - i * 100),
                "stck_lwpr": str(70000 - i * 100),
                "flng_cls_code": "00",
                "prtt_rate": "0.0000",
            },
        })
    return rows


# ---------------------------------------------------------------------------
# G-EQ-3 (락 폴백, 최우선 HIGH) — flng_cls_code 비기본 → KIS 폴백
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_eq3_lock_flng_cls_code_forces_kis_fallback():
    """윈도우 내 flng_cls_code="02" (락) 1 row → DB 버리고 KIS 폴백."""
    from src.db import stock_master_daily as _smd

    db_rows = _normal_db_rows(24)
    # 윈도우 중간 1 row 에 락 표시 (액면분할/병합)
    db_rows[10]["flng_cls_code"] = "02"

    kis_rows = [{"stck_bsop_date": "20260620", "stck_clpr": "14200"}]  # 락 후 재조정 값
    mock_fetch = AsyncMock(return_value=kis_rows)

    with patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(_smd, "max_bas_dd", new=AsyncMock(return_value=date.today() - timedelta(days=1))), \
            patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
        rows = await _smd.get_recent_daily_normalized("005930", 22, min_required=22)

    assert mock_fetch.await_count == 1, "락 발생 → KIS 폴백 강제 (DB 사용 금지)"
    assert rows == kis_rows, "락 종목은 KIS 재조정 값 사용"


@pytest.mark.asyncio
async def test_g_eq3_lock_prtt_rate_forces_kis_fallback():
    """윈도우 내 prtt_rate 비-0 (분할 비율) 1 row → KIS 폴백."""
    from src.db import stock_master_daily as _smd

    db_rows = _normal_db_rows(24)
    db_rows[5]["prtt_rate"] = "-0.2000"  # 운영 실측 락 조정 비율

    kis_rows = [{"stck_bsop_date": "20260620", "stck_clpr": "14200"}]
    mock_fetch = AsyncMock(return_value=kis_rows)

    with patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(_smd, "max_bas_dd", new=AsyncMock(return_value=date.today() - timedelta(days=1))), \
            patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
        rows = await _smd.get_recent_daily_normalized("005930", 22, min_required=22)

    assert mock_fetch.await_count == 1, "prtt_rate 비-0 → KIS 폴백"
    assert rows == kis_rows


@pytest.mark.asyncio
async def test_g_eq3_normal_no_lock_uses_db():
    """정상 (락 없음) — flng_cls_code="00" + prtt_rate="0.0000" → DB 사용 (폴백 0)."""
    from src.db import stock_master_daily as _smd

    db_rows = _normal_db_rows(24)
    mock_fetch = AsyncMock(return_value=[])

    with patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(_smd, "max_bas_dd", new=AsyncMock(return_value=date.today() - timedelta(days=1))), \
            patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
        rows = await _smd.get_recent_daily_normalized("005930", 22, min_required=22)

    assert mock_fetch.await_count == 0, "정상 종목 → DB 사용 (폴백 0)"
    # raw JSONB (KIS 키) 반환 정합
    assert rows[0].get("stck_clpr") == "71000"


@pytest.mark.asyncio
async def test_g_eq3_prtt_rate_zero_variants_not_lock():
    """prtt_rate 기본값 변형 (0 / "" / None / "0.0000") 모두 락 아님 (정상 통과)."""
    from src.db import stock_master_daily as _smd

    for variant in ("0.0000", "0", "", None, 0, 0.0):
        db_rows = _normal_db_rows(24)
        for r in db_rows:
            r["prtt_rate"] = variant
        mock_fetch = AsyncMock(return_value=[])

        with patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
                patch.object(_smd, "max_bas_dd", new=AsyncMock(return_value=date.today() - timedelta(days=1))), \
                patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
            rows = await _smd.get_recent_daily_normalized("005930", 22, min_required=22)

        assert mock_fetch.await_count == 0, f"prtt_rate={variant!r} 기본값 → 락 아님 (DB 사용)"


@pytest.mark.asyncio
async def test_g_eq3_flng_cls_code_blank_variants_not_lock():
    """flng_cls_code 기본값 변형 ("" / "00" / None) 모두 락 아님."""
    from src.db import stock_master_daily as _smd

    for variant in ("00", "", None):
        db_rows = _normal_db_rows(24)
        for r in db_rows:
            r["flng_cls_code"] = variant
        mock_fetch = AsyncMock(return_value=[])

        with patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
                patch.object(_smd, "max_bas_dd", new=AsyncMock(return_value=date.today() - timedelta(days=1))), \
                patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
            rows = await _smd.get_recent_daily_normalized("005930", 22, min_required=22)

        assert mock_fetch.await_count == 0, f"flng_cls_code={variant!r} 기본값 → 락 아님"


# ---------------------------------------------------------------------------
# G-EQ-4 (신선도 가드) — max_bas_dd 가 today-4 보다 오래 → KIS 폴백
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_eq4_stale_max_bas_dd_forces_kis_fallback():
    """DB 최신봉이 today-4 보다 오래 (D-1 미적재) → KIS 폴백."""
    from src.db import stock_master_daily as _smd

    db_rows = _normal_db_rows(24)
    kis_rows = [{"stck_bsop_date": "20260620", "stck_clpr": "71000"}]
    mock_fetch = AsyncMock(return_value=kis_rows)

    # max_bas_dd 가 10일 전 (staleness > 4) → 폴백
    stale_dd = date.today() - timedelta(days=10)

    with patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(_smd, "max_bas_dd", new=AsyncMock(return_value=stale_dd)), \
            patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
        rows = await _smd.get_recent_daily_normalized("005930", 22, min_required=22)

    assert mock_fetch.await_count == 1, "신선도 미달 (max_bas_dd 10일 전) → KIS 폴백"
    assert rows == kis_rows


@pytest.mark.asyncio
async def test_g_eq4_fresh_max_bas_dd_uses_db():
    """DB 최신봉이 today-2 (주말 마진 내) → DB 사용 (폴백 0)."""
    from src.db import stock_master_daily as _smd

    db_rows = _normal_db_rows(24)
    mock_fetch = AsyncMock(return_value=[])

    fresh_dd = date.today() - timedelta(days=2)  # staleness 2 < 4

    with patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(_smd, "max_bas_dd", new=AsyncMock(return_value=fresh_dd)), \
            patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
        rows = await _smd.get_recent_daily_normalized("005930", 22, min_required=22)

    assert mock_fetch.await_count == 0, "신선 (max_bas_dd 2일 전) → DB 사용"


@pytest.mark.asyncio
async def test_g_eq4_max_bas_dd_none_graceful_uses_db_if_sufficient():
    """max_bas_dd None (신선도 미상) → 보수적이지만 DB 충분 시 사용 (graceful, miss 아님)."""
    from src.db import stock_master_daily as _smd

    db_rows = _normal_db_rows(24)
    mock_fetch = AsyncMock(return_value=[])

    # max_bas_dd None — 신선도 판정 불가. DB 충분 + 락 없음이면 사용 (graceful).
    with patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(_smd, "max_bas_dd", new=AsyncMock(return_value=None)), \
            patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
        rows = await _smd.get_recent_daily_normalized("005930", 22, min_required=22)

    # max_bas_dd None 은 신선도 게이트 통과 (graceful) — db_rows 자체가 신선도 증거
    assert mock_fetch.await_count == 0, "max_bas_dd None → 신선도 게이트 graceful 통과"


# ---------------------------------------------------------------------------
# G-EQ-5 (min_required 경계, HIGH) — 게이트 우선순위 락 > 신선도 > min_required
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_eq5_min_required_boundary_below_fallback():
    """DB len == min_required - 1 (경계) → KIS 폴백."""
    from src.db import stock_master_daily as _smd

    db_rows = _normal_db_rows(62)  # donchian min_required=63 → 62 = 미달
    kis_rows = [{"stck_bsop_date": "20260620", "stck_clpr": "71000"}]
    mock_fetch = AsyncMock(return_value=kis_rows)

    with patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(_smd, "max_bas_dd", new=AsyncMock(return_value=date.today() - timedelta(days=1))), \
            patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
        rows = await _smd.get_recent_daily_normalized("005930", 66, min_required=63)

    assert mock_fetch.await_count == 1, "len 62 < min_required 63 → 폴백"
    assert rows == kis_rows


@pytest.mark.asyncio
async def test_g_eq5_min_required_boundary_at_threshold_uses_db():
    """DB len == min_required (경계) → DB 사용 (폴백 0)."""
    from src.db import stock_master_daily as _smd

    db_rows = _normal_db_rows(63)  # donchian min_required=63 정확
    mock_fetch = AsyncMock(return_value=[])

    with patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(_smd, "max_bas_dd", new=AsyncMock(return_value=date.today() - timedelta(days=1))), \
            patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
        rows = await _smd.get_recent_daily_normalized("005930", 66, min_required=63)

    assert mock_fetch.await_count == 0, "len 63 == min_required 63 → DB 사용"


# ---------------------------------------------------------------------------
# G-EQ-6 (폴백 동등) — DB 완전 miss → KIS 폴백 (현행 KIS-only 동등)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_eq6_db_empty_kis_fallback():
    """DB 완전 miss → KIS fetch_daily_candles 폴백 (회귀 보존)."""
    from src.db import stock_master_daily as _smd

    kis_rows = [
        {"stck_bsop_date": "20260620", "stck_clpr": "71000"},
        {"stck_bsop_date": "20260619", "stck_clpr": "70500"},
    ]
    mock_fetch = AsyncMock(return_value=kis_rows)

    with patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=[])), \
            patch.object(_smd, "max_bas_dd", new=AsyncMock(return_value=None)), \
            patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
        rows = await _smd.get_recent_daily_normalized("005930", 22, min_required=22)

    assert mock_fetch.await_count == 1
    assert rows == kis_rows


# ---------------------------------------------------------------------------
# 게이트 우선순위 — 락이 신선도/min_required 보다 우선 (락 먼저 검사)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gate_priority_lock_takes_precedence():
    """락 + 충분 + 신선 동시 → 락이 우선 KIS 폴백."""
    from src.db import stock_master_daily as _smd

    db_rows = _normal_db_rows(24)
    db_rows[3]["flng_cls_code"] = "03"  # 락
    kis_rows = [{"stck_bsop_date": "20260620", "stck_clpr": "14200"}]
    mock_fetch = AsyncMock(return_value=kis_rows)

    with patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(_smd, "max_bas_dd", new=AsyncMock(return_value=date.today() - timedelta(days=1))), \
            patch("src.api.condition.fetch_daily_candles", new=mock_fetch):
        rows = await _smd.get_recent_daily_normalized("005930", 22, min_required=22)

    assert mock_fetch.await_count == 1
    assert rows == kis_rows


# ---------------------------------------------------------------------------
# AST — staleness 상수 존재 + 게이트 검사 정적 가드
# ---------------------------------------------------------------------------
def test_ast_adapter_has_lock_and_stale_gates():
    """어댑터 본체에 flng_cls_code / prtt_rate / max_bas_dd 검사 정적 존재."""
    from src.db import stock_master_daily as _smd

    src = inspect.getsource(_smd.get_recent_daily_normalized)
    assert "flng_cls_code" in src, "락 게이트 flng_cls_code 검사 영속"
    assert "prtt_rate" in src, "락 게이트 prtt_rate 검사 영속"
    assert "max_bas_dd" in src, "신선도 게이트 max_bas_dd 검사 영속"
