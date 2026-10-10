"""사이클 434 — `src/db/system_logs.py::get_today_alert_logs` 단위 계약 (pg mock).

대시보드 경고등(`GET /api/system/alerts`) 전용 조회. 오늘(KST) WARNING 이상 로그 중
명부 패턴(OR ILIKE)에 걸리는 행만 가져온다. `src/engine/alert_markers.py::ALL_PATTERNS`
를 몰라도 되게(의존 역전) `patterns` 인자로 받는다.

요구 행위:
A. 패턴 리스트를 `message ILIKE $n OR ...` 로 OR 바인딩한다.
B. 오늘(KST) `+09:00` 00:00:00 ~ 23:59:59.999999 경계를 바인딩한다(`day` 인자로 고정 가능).
C. `log_level = ANY($n::text[])` 로 WARNING/ERROR/CRITICAL 만 거른다.
D. `timestamp ASC` 정렬.
E. 빈 patterns = 쿼리 없이 `[]`.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_empty_patterns_returns_empty_without_query():
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"should": "not happen"}])
        out = await _mod.get_today_alert_logs([])

    assert out == []
    pg_mod.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_binds_or_ilike_patterns_and_level_filter():
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await _mod.get_today_alert_logs(
            ["%[holding_qty_unexplained]%", "%매도 주문 최종 실패:%"],
            day=date(2026, 10, 10),
        )

    sql = pg_mod.fetch.await_args.args[0]
    sql_upper = sql.upper()
    assert sql_upper.count("ILIKE") == 2, f"OR ILIKE 2개 바인딩 누락: {sql}"
    assert "LOG_LEVEL = ANY(" in sql_upper, f"레벨 필터 누락: {sql}"
    assert "ORDER BY TIMESTAMP ASC" in sql_upper, f"timestamp ASC 정렬 누락: {sql}"

    passed = list(pg_mod.fetch.await_args.args[1:])
    passed_str = [str(a) for a in passed]
    assert any("2026-10-10T00:00:00+09:00" in s for s in passed_str), (
        f"오늘 00:00:00+09:00 하한 바인딩 누락: {passed_str}"
    )
    assert any("2026-10-10T23:59:59.999999+09:00" in s for s in passed_str), (
        f"오늘 23:59:59.999999+09:00 상한 바인딩 누락: {passed_str}"
    )
    assert "%[holding_qty_unexplained]%" in passed
    assert "%매도 주문 최종 실패:%" in passed
    assert ["WARNING", "ERROR", "CRITICAL"] in passed or any(
        isinstance(a, list) and set(a) == {"WARNING", "ERROR", "CRITICAL"} for a in passed
    )


@pytest.mark.asyncio
async def test_defaults_to_today_kst_when_day_omitted():
    from src.db import system_logs as _mod

    with patch.object(_mod, "pg", create=True) as pg_mod, patch.object(
        _mod, "today_kst", return_value=date(2026, 10, 10)
    ):
        pg_mod.fetch = AsyncMock(return_value=[])
        await _mod.get_today_alert_logs(["%x%"])

    passed_str = [str(a) for a in pg_mod.fetch.await_args.args[1:]]
    assert any("2026-10-10T00:00:00+09:00" in s for s in passed_str)


@pytest.mark.asyncio
async def test_returns_rows_as_is():
    from src.db import system_logs as _mod

    rows = [{"log_level": "ERROR", "message": "x", "timestamp": "2026-10-10T10:00:00+09:00"}]
    with patch.object(_mod, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await _mod.get_today_alert_logs(["%x%"], day=date(2026, 10, 10))

    assert out == rows
