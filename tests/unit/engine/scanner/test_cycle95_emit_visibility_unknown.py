"""사이클 95 M-1 — `[stock_master_bulk_refresh]` emit 영역 unknown 카운트 추가 (MEDIUM).

명세 (`_workspace/red/cycle95_chicken_and_egg_fix_ui.md`):

- 사이클 89 영속 emit format: `[stock_master_bulk_refresh] universe=N kospi=K kosdaq=L securities=S etf_excluded=E elapsed_ms=...`
- 사이클 95 시정 emit: `[stock_master_bulk_refresh] universe=N kospi=K kosdaq=L unknown=U securities=S etf_excluded=E elapsed_ms=...`
- 운영 가시화 = chicken-and-egg 회복 곡선 측정 (첫 사이클 unknown >> 다음 사이클 ↓ 영속)

Red 상태 (사이클 95): production emit 에 unknown 키 부재 → FAIL (substring 매칭).

Green: emit 에 `unknown=%d` 추가 + collector dict 에 `unknown` 키 추가 → PASS.

영속 의무:
- 사이클 89 emit format 영속 (universe / kospi / kosdaq / securities / etf_excluded / elapsed_ms 키)
- 사이클 78 답습 (collector flush 5분 윈도우)
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_volume_rank_row(ticker: str) -> dict:
    return {
        "mksc_shrn_iscd": ticker,
        "prdy_vol": "1000000",
        "stck_prpr": "50000",
        "prdy_vrss": "1000",
    }


def _make_stock_basics(ticker: str, excg_dvsn_cd: str):
    from src.models.stock import StockBasics

    return StockBasics(
        ticker=ticker,
        name=f"종목{ticker}",
        excg_dvsn_cd=excg_dvsn_cd,
        raw={"mksc_shrn_iscd": ticker, "excg_dvsn_cd": excg_dvsn_cd},
    )


@pytest.mark.asyncio
async def test_m1_emit_visibility_includes_unknown_count(caplog):
    """M-1.a: `[stock_master_bulk_refresh]` emit 에 `unknown=%d` 영역 영속.

    검증 매트릭스:
    - volume_rank 10건 (KOSPI 2 + KOSDAQ 1 + 부재 7)
    - 사이클 95 시정 후 emit substring `unknown=7` 포함

    Red (사이클 95): production emit format = "universe=%d kospi=%d kosdaq=%d ..."
                     → "unknown=" substring 부재 → FAIL.

    Green: emit format = "universe=%d kospi=%d kosdaq=%d unknown=%d ..."
           → "unknown=7" substring 매칭 → PASS.
    """
    from src.engine import scanner

    raw_rows = [_make_volume_rank_row(f"00500{i}") for i in range(10)]
    sm_map = {
        "005000": _make_stock_basics("005000", "02"),
        "005001": _make_stock_basics("005001", "02"),
        "005002": _make_stock_basics("005002", "03"),
    }

    async def fake_get(ticker: str):
        return sm_map.get(ticker)

    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    with patch.object(scanner, "_fetch_volume_rank", new=AsyncMock(return_value=raw_rows)), \
         patch("src.db.stock_master.get", side_effect=fake_get):
        await scanner.fetch_top_500_universe()

    bulk_refresh_records = [
        rec for rec in caplog.records
        if "[stock_master_bulk_refresh]" in rec.getMessage()
    ]
    assert len(bulk_refresh_records) >= 1, (
        "사이클 95 M-1.a 위반 — `[stock_master_bulk_refresh]` emit 누락 (사이클 89 영속 위반)"
    )

    msg = bulk_refresh_records[0].getMessage()
    assert "unknown=" in msg, (
        f"\n사이클 95 M-1.a 위반 — emit unknown 키 누락:\n"
        f"  emit: {msg}\n"
        f"  기대 substring: 'unknown=' (운영 가시화 영속)\n"
        f"  결함 인과: 사이클 89 영속 emit format 에 unknown 카운트 부재\n"
        f"  시정: 'unknown=%d' format 영역 추가 의무 (사이클 95 운영 가시화)"
    )
    assert "unknown=7" in msg, (
        f"\n사이클 95 M-1.a 위반 — unknown 카운트 값 결함:\n"
        f"  emit: {msg}\n"
        f"  기대: 'unknown=7' (stock_master 부재 7건)\n"
        f"  실제 substring 영역 결함"
    )


@pytest.mark.asyncio
async def test_m1_collector_includes_unknown_key():
    """M-1.b: `record_universe_refresh` collector 에 `unknown` 키 영역 영속.

    검증 매트릭스:
    - 사이클 78 답습 (collector flush 5분 윈도우 통계)
    - 사이클 95 시정 후 collector dict 에 'unknown' 키 포함
    - 미래 신규 통계 영역 (chicken-and-egg 회복 곡선 측정) 활용 가능

    Red (사이클 95): collector dict = {universe, kospi, kosdaq, securities, etf_excluded, fetched, skipped_fresh, failed, elapsed_ms}
                     → 'unknown' 키 부재 → FAIL.

    Green: collector dict 에 'unknown' 키 추가 → PASS.
    """
    from src.engine import scanner

    raw_rows = [_make_volume_rank_row(f"00500{i}") for i in range(10)]
    sm_map = {
        "005000": _make_stock_basics("005000", "02"),
        "005002": _make_stock_basics("005002", "03"),
    }

    async def fake_get(ticker: str):
        return sm_map.get(ticker)

    from src.engine import stock_master_metrics as _metrics

    captured = []
    original_record = _metrics.record_universe_refresh

    def capture(stats):
        captured.append(dict(stats))
        return original_record(stats)

    with patch.object(scanner, "_fetch_volume_rank", new=AsyncMock(return_value=raw_rows)), \
         patch("src.db.stock_master.get", side_effect=fake_get), \
         patch.object(_metrics, "record_universe_refresh", side_effect=capture):
        await scanner.fetch_top_500_universe()

    assert len(captured) >= 1, "사이클 95 M-1.b 위반 — `record_universe_refresh` 호출 누락"

    stats = captured[0]
    assert "unknown" in stats, (
        f"\n사이클 95 M-1.b 위반 — collector dict 'unknown' 키 누락:\n"
        f"  실제 dict 키: {sorted(stats.keys())}\n"
        f"  기대: 'unknown' 키 포함 (운영 가시화 영속)\n"
        f"  시정: record_universe_refresh({{... 'unknown': len(unknown_sorted), ...}}) 의무"
    )
    assert stats["unknown"] == 8, (
        f"\n사이클 95 M-1.b 위반 — collector unknown 카운트 결함:\n"
        f"  기대: unknown=8 (stock_master 부재 8건, KOSPI 1 + KOSDAQ 1 분리 후)\n"
        f"  실제: unknown={stats.get('unknown')}\n"
        f"  결함 영역: 사이클 95 unknown 합산 카운트 정합 결함"
    )
