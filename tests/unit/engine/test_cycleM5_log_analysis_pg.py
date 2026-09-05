"""사이클 M5 (Red) — log_analysis_engine.py system_logs 페이지드 SELECT 전환.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (Supabase→RDS 이전, 누락 사이트).

log_analysis_engine L29 import + L122 `supabase.table("system_logs")` = `_fetch_logs_in_range` 의
페이지드 SELECT (M 노트가 "insert"라 했으나 실제는 **읽기**). RDS(pg) 로 전환.

계약 보존:
- 시간 윈도우 (gte start / lte end) + ASC 정렬 + LIMIT/OFFSET 페이징.
- 반환 row 컬럼 = timestamp / log_level / message (기존 select 컬럼).
- timestamp 는 +09:00 KST str (사이클 53 B-4).

Red 유효성: production 여전히 supabase.table("system_logs") → pg.fetch 미호출 + 소스 잔존 → FAIL.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_LAE = _REPO / "src" / "engine" / "log_analysis_engine.py"
# cycle259 카드 ⑦ — `_fetch_logs_in_range` 등 pg 접근 코드의 실제 소재지.
_COLLECTOR = _REPO / "src" / "engine" / "log_metrics_collector.py"

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 소스 텍스트 가드 — supabase 직접 접근 제거
# ---------------------------------------------------------------------------
def test_log_analysis_no_supabase_reference():
    for path in (_LAE, _COLLECTOR):
        body = path.read_text(encoding="utf-8")
        assert "from src.db.supabase import" not in body, (
            f"{path.name} 는 supabase 직접 import 금지 (pg 경유)."
        )
        assert "supabase.table(" not in body, f"{path.name} 는 supabase.table() 호출 0건."


# ---------------------------------------------------------------------------
# _fetch_logs_in_range → pg.fetch (페이지드 SELECT + 윈도우 + ASC)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_logs_uses_pg_fetch():
    """_fetch_logs_in_range → pg.fetch SELECT FROM system_logs (supabase 체인 폐기)."""
    from src.engine import log_metrics_collector as lae  # cycle259 카드 ⑦ — 이동처

    start = datetime(2026, 7, 17, 0, 0, tzinfo=KST)
    end = datetime(2026, 7, 17, 23, 59, tzinfo=KST)

    with patch.object(lae, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await lae._fetch_logs_in_range(start, end, limit=1000)

    assert out == [], "빈 결과 계약."
    pg_mod.fetch.assert_awaited()
    sql = pg_mod.fetch.await_args.args[0]
    up = sql.upper()
    assert "FROM SYSTEM_LOGS" in up, "system_logs SELECT 누락."
    # 컬럼 계약 (timestamp / log_level / message)
    assert "LOG_LEVEL" in up and "MESSAGE" in up, "log_level / message 컬럼 SELECT 누락."
    assert "TIMESTAMP" in up, "timestamp 컬럼 SELECT 누락."


@pytest.mark.asyncio
async def test_fetch_logs_window_and_order_asc():
    """윈도우 (gte start / lte end) + ASC 정렬 + LIMIT/OFFSET 페이징 계약 보존."""
    from src.engine import log_metrics_collector as lae  # cycle259 카드 ⑦ — 이동처

    start = datetime(2026, 7, 17, 0, 0, tzinfo=KST)
    end = datetime(2026, 7, 17, 23, 59, tzinfo=KST)

    with patch.object(lae, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await lae._fetch_logs_in_range(start, end, limit=1000)

    sql = pg_mod.fetch.await_args.args[0]
    up = sql.upper()
    assert ">=" in sql, "start 이상(gte) 윈도우 누락."
    assert "<=" in sql, "end 이하(lte) 윈도우 누락."
    assert "ORDER BY" in up and "ASC" in up, "timestamp ASC 정렬 누락 (오름차순 계약)."
    assert "LIMIT" in up and "OFFSET" in up, "LIMIT/OFFSET 페이징 누락 (range 대체)."


@pytest.mark.asyncio
async def test_fetch_logs_paging_drains_until_short_page():
    """PAGE_SIZE 미만 페이지 도달 시 종료 — 페이징 루프 계약 보존.

    1000/1000/300 반환 → pg.fetch 3회 (마지막 <1000 이면 종료).
    """
    from src.engine import log_metrics_collector as lae  # cycle259 카드 ⑦ — 이동처

    start = datetime(2026, 7, 17, 0, 0, tzinfo=KST)
    end = datetime(2026, 7, 17, 23, 59, tzinfo=KST)

    pages = [
        [{"timestamp": "t", "log_level": "INFO", "message": "m"}] * 1000,
        [{"timestamp": "t", "log_level": "INFO", "message": "m"}] * 1000,
        [{"timestamp": "t", "log_level": "INFO", "message": "m"}] * 300,
    ]
    call_count = {"n": 0}

    async def _fetch(sql, *args):
        i = call_count["n"]
        call_count["n"] += 1
        return pages[i] if i < len(pages) else []

    with patch.object(lae, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=_fetch)
        out = await lae._fetch_logs_in_range(start, end, limit=30000)

    assert call_count["n"] == 3, "1000/1000/300 → 3회 페이지 후 종료 (짧은 페이지 도달 시 break)."
    assert len(out) == 2300, "전 페이지 누적 (1000+1000+300)."


@pytest.mark.asyncio
async def test_fetch_logs_timestamp_kst_expr():
    """timestamp 는 +09:00 KST str 로 반환 (SELECT to_char '+09:00' 캐스트, 사이클 53 B-4)."""
    from src.engine import log_metrics_collector as lae  # cycle259 카드 ⑦ — 이동처

    start = datetime(2026, 7, 17, 0, 0, tzinfo=KST)
    end = datetime(2026, 7, 17, 23, 59, tzinfo=KST)

    with patch.object(lae, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await lae._fetch_logs_in_range(start, end, limit=1000)

    sql = pg_mod.fetch.await_args.args[0]
    assert "+09:00" in sql, (
        "timestamp SELECT 는 to_char(...,'...+09:00') KST str 캐스트 필요 "
        "(_aggregate_logs / 소비처 timestamp str 계약 보존)."
    )
