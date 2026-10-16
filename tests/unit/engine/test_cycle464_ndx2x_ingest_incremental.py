"""cycle464 — ndx2x_ingest 증분(슬라이딩) 적재 회귀 가드.

결함: 이력이 목표(300)를 넘으면 widening 루프가 0회라 새 봉을 영원히 못 받았다
(운영 DB NDX latest 가 2026-10-09 에 멈춤). 자문
`_workspace/domain_consult/2026-10-16_ndx2x_ingest_incremental.md` 권고안 —
이력이 충분하면 「DB 최신일 − 14 달력일」 부터 오늘까지만 받는다(최신일 앵커).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from src.api.overseas_quote import OverseasIndexEmptyResponseError
from src.engine import ndx2x_ingest as ing

pytestmark = pytest.mark.unit

_LOGGER = "src.engine.ndx2x_ingest"


def _row(bsop: str, close: float) -> dict:
    return {"stck_bsop_date": bsop, "ovrs_nmix_prpr": str(close)}


def _weekdays(start: date, end: date) -> list[date]:
    """[start, end] 평일(미국 영업일 근사) 오름차순."""
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _existing_ending(latest: date, n: int) -> list[tuple[date, float]]:
    days = _weekdays(latest - timedelta(days=n * 2), latest)[-n:]
    return [(d, 100.0 + i) for i, d in enumerate(days)]


def _fake_kis(master: dict[str, float], call_log: list[tuple[date, date]]):
    """[start, end] 안 원자료 → 최근 100행 캡 → 시작 근처 5일 누락(quirk 모사)."""

    async def _fetch(start, end, iscd="NDX"):
        call_log.append((start, end))
        s, e = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
        in_range = sorted((d, c) for d, c in master.items() if s <= d <= e)
        capped = in_range[-100:]
        dropped = capped[5:] if len(capped) > 5 else capped
        if not dropped:
            raise OverseasIndexEmptyResponseError("no rows")
        return [_row(d, c) for d, c in sorted(dropped, reverse=True)]

    return _fetch


def _patch_db(monkeypatch, existing):
    latest = existing[-1][0] if existing else None
    monkeypatch.setattr(ing.db, "get_latest_date", AsyncMock(return_value=latest))
    monkeypatch.setattr(ing.db, "get_recent_closes", AsyncMock(return_value=existing))
    upsert = AsyncMock(side_effect=lambda code, rows, **kw: len(rows))
    monkeypatch.setattr(ing.db, "upsert_many", upsert)
    return upsert


def _upserted_dates(upsert: AsyncMock) -> set[str]:
    out: set[str] = set()
    for call in upsert.await_args_list:
        out |= {d for d, _ in call.args[1]}
    return out


@pytest.mark.asyncio
async def test_1_full_history_but_stale_fetches_once_and_fills_missing_days(monkeypatch):
    """본 결함 — 397행·latest 10-09·today 10-16 → KIS 1회, 10-12~15 적재."""
    latest, today = date(2026, 10, 9), date(2026, 10, 16)
    existing = _existing_ending(latest, 397)
    upsert = _patch_db(monkeypatch, existing)
    master = {d.strftime("%Y%m%d"): 200.0 for d in _weekdays(latest - timedelta(days=60), date(2026, 10, 15))}
    calls: list[tuple[date, date]] = []
    monkeypatch.setattr(ing, "fetch_daily_chartprice", AsyncMock(side_effect=_fake_kis(master, calls)))

    result = await ing.ensure_history(today=today)

    assert len(calls) == 1
    assert calls[0][0] == latest - timedelta(days=ing.INCREMENTAL_OVERLAP_DAYS)
    assert {"20261012", "20261013", "20261014", "20261015"} <= _upserted_dates(upsert)
    assert result.latest_date == "20261015"
    assert result.outcome == "new_bar"


@pytest.mark.asyncio
async def test_2_long_stale_with_100_cap_leaves_no_gap(monkeypatch):
    """200일 낡음 — 100 캡에 잘려도 커서를 당겨 구멍 없이 잇는다(호출 ≤ 6)."""
    today = date(2026, 10, 16)
    latest = _weekdays(today - timedelta(days=205), today - timedelta(days=200))[-1]
    existing = _existing_ending(latest, 300)
    upsert = _patch_db(monkeypatch, existing)
    master = {d.strftime("%Y%m%d"): 300.0 for d in _weekdays(latest - timedelta(days=60), today - timedelta(days=1))}
    calls: list[tuple[date, date]] = []
    monkeypatch.setattr(ing, "fetch_daily_chartprice", AsyncMock(side_effect=_fake_kis(master, calls)))

    result = await ing.ensure_history(today=today)

    assert 2 <= len(calls) <= ing._MAX_FETCH_ATTEMPTS
    have = {d.strftime("%Y%m%d") for d, _ in existing} | _upserted_dates(upsert)
    want = {d.strftime("%Y%m%d") for d in _weekdays(latest, today - timedelta(days=1))}
    assert want <= have, f"구멍: {sorted(want - have)[:5]}"
    assert result.outcome == "new_bar"


@pytest.mark.asyncio
async def test_3_incremental_never_requests_or_writes_before_overlap_anchor(monkeypatch):
    """오염 반경 — 겹침 앵커 이전은 요청·쓰기 0, 겹침 안 수정값은 반영."""
    latest, today = date(2026, 10, 9), date(2026, 10, 16)
    existing = _existing_ending(latest, 300)
    upsert = _patch_db(monkeypatch, existing)
    anchor = latest - timedelta(days=ing.INCREMENTAL_OVERLAP_DAYS)
    master = {d.strftime("%Y%m%d"): 1.0 for d in _weekdays(latest - timedelta(days=90), date(2026, 10, 15))}
    master["20261007"] = 999.0  # 겹침 안 사후 수정
    calls: list[tuple[date, date]] = []
    monkeypatch.setattr(ing, "fetch_daily_chartprice", AsyncMock(side_effect=_fake_kis(master, calls)))

    await ing.ensure_history(today=today)

    assert all(start >= anchor for start, _ in calls)
    written = {}
    for call in upsert.await_args_list:
        written.update(dict(call.args[1]))
    assert min(written) >= anchor.strftime("%Y%m%d")
    assert written["20261007"] == 999.0


@pytest.mark.asyncio
async def test_4_us_holiday_no_new_bar_is_info_not_error(monkeypatch, caplog):
    """원자료 최신일 == DB latest — no_new_bar, 예외·ERROR 없음(평일 1일 = INFO)."""
    latest, today = date(2026, 11, 25), date(2026, 11, 27)  # 11-26 추수감사절
    existing = _existing_ending(latest, 300)
    _patch_db(monkeypatch, existing)
    master = {d.strftime("%Y%m%d"): 5.0 for d in _weekdays(latest - timedelta(days=40), latest)}
    calls: list[tuple[date, date]] = []
    monkeypatch.setattr(ing, "fetch_daily_chartprice", AsyncMock(side_effect=_fake_kis(master, calls)))

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        result = await ing.ensure_history(today=today)

    assert len(calls) == 1
    assert result.outcome == "no_new_bar"
    assert result.latest_date == latest.strftime("%Y%m%d")
    outcome_logs = [r for r in caplog.records if "[ndx2x_ingest_outcome]" in r.getMessage()]
    assert outcome_logs and all(r.levelno == logging.INFO for r in outcome_logs)


@pytest.mark.asyncio
async def test_4b_no_new_bar_for_two_weekdays_warns(monkeypatch, caplog):
    latest, today = date(2026, 11, 25), date(2026, 11, 28)  # 11-26·27 평일 2일 새 봉 없음
    _patch_db(monkeypatch, _existing_ending(latest, 300))
    master = {d.strftime("%Y%m%d"): 5.0 for d in _weekdays(latest - timedelta(days=40), latest)}
    monkeypatch.setattr(ing, "fetch_daily_chartprice", AsyncMock(side_effect=_fake_kis(master, [])))

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        result = await ing.ensure_history(today=today)

    assert result.outcome == "no_new_bar"
    assert any(
        r.levelno == logging.WARNING and r.getMessage().startswith("[ndx2x_ingest_outcome]")
        for r in caplog.records
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [OverseasIndexEmptyResponseError("empty"), RuntimeError("net")])
async def test_5_fetch_failure_preserves_db_and_recovers_next_day(monkeypatch, caplog, exc):
    latest = date(2026, 10, 9)
    existing = _existing_ending(latest, 300)
    upsert = _patch_db(monkeypatch, existing)
    monkeypatch.setattr(ing, "fetch_daily_chartprice", AsyncMock(side_effect=exc))

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        result = await ing.ensure_history(today=date(2026, 10, 16))  # raise 하지 않는다

    assert result.outcome == "fetch_failed"
    upsert.assert_not_called()
    assert any(
        r.levelno == logging.ERROR and r.getMessage().startswith("[ndx2x_ingest_outcome]")
        for r in caplog.records
    )

    # 다음 날 — 같은 앵커로 다시 받아 구멍 없이 회복
    master = {d.strftime("%Y%m%d"): 7.0 for d in _weekdays(latest - timedelta(days=40), date(2026, 10, 16))}
    calls: list[tuple[date, date]] = []
    monkeypatch.setattr(ing, "fetch_daily_chartprice", AsyncMock(side_effect=_fake_kis(master, calls)))
    result2 = await ing.ensure_history(today=date(2026, 10, 17))

    assert calls[0][0] == latest - timedelta(days=ing.INCREMENTAL_OVERLAP_DAYS)
    want = {d.strftime("%Y%m%d") for d in _weekdays(date(2026, 10, 12), date(2026, 10, 16))}
    assert want <= _upserted_dates(upsert)
    assert result2.outcome == "new_bar"
