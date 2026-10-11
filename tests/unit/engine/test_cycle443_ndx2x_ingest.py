"""cycle443 — ndx2x_ingest.ensure_history widening-fetch 회귀 가드.

KIS·DB 둘 다 monkeypatch(`src.api.*` 직접 import 소비 모듈과 같은 패턴 —
`monkeypatch.setattr(ndx2x_ingest, "fetch_daily_chartprice", ...)` /
`monkeypatch.setattr(ndx2x_ingest.db, "get_latest_date", ...)`).
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from src.api.overseas_quote import OverseasIndexEmptyResponseError
from src.engine import ndx2x_ingest as ing

pytestmark = pytest.mark.unit


def _row(bsop: str, close: float) -> dict:
    return {"stck_bsop_date": bsop, "ovrs_nmix_prpr": str(close)}


def _master(n: int, start: date) -> list[tuple[str, float]]:
    """start 로부터 하루 1영업일씩 n일치 (date 오름차순)."""
    out = []
    d = start
    for i in range(n):
        out.append((d.strftime("%Y%m%d"), 100.0 + i))
        d += timedelta(days=1)
    return out


@pytest.mark.asyncio
async def test_already_fresh_and_sufficient_history_makes_zero_kis_calls(monkeypatch):
    today = date(2026, 10, 11)
    existing = [(today - timedelta(days=i), 100.0) for i in range(ing.MIN_HISTORY_DAYS + 60, 0, -1)]
    monkeypatch.setattr(ing.db, "get_latest_date", AsyncMock(return_value=today))
    monkeypatch.setattr(ing.db, "get_recent_closes", AsyncMock(return_value=existing))
    mock_fetch = AsyncMock()
    monkeypatch.setattr(ing, "fetch_daily_chartprice", mock_fetch)
    mock_upsert = AsyncMock()
    monkeypatch.setattr(ing.db, "upsert_many", mock_upsert)

    result = await ing.ensure_history(today=today)

    mock_fetch.assert_not_called()
    mock_upsert.assert_not_called()
    assert result.reached_target is True
    assert result.rows_upserted == 0


@pytest.mark.asyncio
async def test_empty_db_widening_fetch_reaches_target_within_attempt_budget(monkeypatch):
    """빈 DB — 콜마다 커서를 과거로 당기며 겹치게 받아 목표 이력에 도달한다."""
    today = date(2026, 10, 11)
    target = ing.MIN_HISTORY_DAYS + 50  # 300
    master = _master(target + 50, today - timedelta(days=target + 50))  # 오늘까지 350일 원자료

    monkeypatch.setattr(ing.db, "get_latest_date", AsyncMock(return_value=None))
    monkeypatch.setattr(ing.db, "get_recent_closes", AsyncMock(return_value=[]))
    mock_upsert = AsyncMock(return_value=0)
    monkeypatch.setattr(ing.db, "upsert_many", mock_upsert)

    call_log: list[tuple[date, date]] = []

    async def _fake_fetch(start, end, iscd="NDX"):
        call_log.append((start, end))
        # [start, end] 안의 master 날짜 중 최근 100개, 그리고 "시작 근처 5일" 을 추가로 뺀다(quirk 모사).
        in_range = [(d, c) for d, c in master if start.strftime("%Y%m%d") <= d <= end.strftime("%Y%m%d")]
        in_range.sort(key=lambda kv: kv[0])
        capped = in_range[-100:] if len(in_range) > 100 else in_range
        dropped = capped[5:] if len(capped) > 5 else capped  # 시작 근처 5일 누락
        rows = [_row(d, c) for d, c in sorted(dropped, key=lambda kv: kv[0], reverse=True)]
        if not rows:
            raise OverseasIndexEmptyResponseError("no rows in window")
        return rows

    monkeypatch.setattr(ing, "fetch_daily_chartprice", AsyncMock(side_effect=_fake_fetch))

    result = await ing.ensure_history(target_days=target, today=today)

    assert result.reached_target is True
    assert result.total_history_days >= target
    assert len(call_log) >= 2  # 한 번의 100행 캡으로는 300일을 못 채운다 — 반드시 여러 번 호출
    assert len(call_log) <= ing._MAX_FETCH_ATTEMPTS
    # upsert 에 넘긴 날짜 집합이 겹침 없이 연속(각 call 의 "시작 근처 5일 누락"이 다음 콜로 메워짐).
    upserted_rows = mock_upsert.await_args.args[1]
    dates_sent = {d for d, _ in upserted_rows}
    assert len(dates_sent) == len(upserted_rows)  # dedupe 확인(중복 없음)


@pytest.mark.asyncio
async def test_empty_response_on_first_call_is_graceful_not_raising(monkeypatch):
    today = date(2026, 10, 11)
    monkeypatch.setattr(ing.db, "get_latest_date", AsyncMock(return_value=None))
    monkeypatch.setattr(ing.db, "get_recent_closes", AsyncMock(return_value=[]))
    mock_upsert = AsyncMock(return_value=0)
    monkeypatch.setattr(ing.db, "upsert_many", mock_upsert)
    monkeypatch.setattr(
        ing, "fetch_daily_chartprice",
        AsyncMock(side_effect=OverseasIndexEmptyResponseError("bad iscd")),
    )

    result = await ing.ensure_history(today=today)  # raise 하지 않는다

    assert result.reached_target is False
    assert result.rows_upserted == 0


@pytest.mark.asyncio
async def test_no_progress_breaks_loop_without_infinite_retry(monkeypatch):
    """같은 창만 반복해서 받으면(진전 없음) 1회만 호출하고 안전 종료한다."""
    today = date(2026, 10, 11)
    monkeypatch.setattr(ing.db, "get_latest_date", AsyncMock(return_value=None))
    monkeypatch.setattr(ing.db, "get_recent_closes", AsyncMock(return_value=[]))
    monkeypatch.setattr(ing.db, "upsert_many", AsyncMock(return_value=0))

    fixed_rows = [_row("20261009", 100.0), _row("20261008", 99.0)]
    mock_fetch = AsyncMock(return_value=fixed_rows)
    monkeypatch.setattr(ing, "fetch_daily_chartprice", mock_fetch)

    result = await ing.ensure_history(target_days=ing.MIN_HISTORY_DAYS, today=today)

    # 1회차: 오늘→20261008 로 진전. 2회차: 같은 창만 반복 수신(진전 없음) → 안전 종료.
    # 상한(_MAX_FETCH_ATTEMPTS)까지 반복하지 않는다(무한루프 방지의 핵심 단언).
    assert mock_fetch.await_count == 2
    assert mock_fetch.await_count < ing._MAX_FETCH_ATTEMPTS
    assert result.reached_target is False
