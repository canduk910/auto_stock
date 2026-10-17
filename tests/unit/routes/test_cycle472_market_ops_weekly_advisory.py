"""cycle472 — 운영 현황 「AI 매매자문」 행이 주간 자문일을 안다(워크리스트 「market_ops.py:595 요일 결함」).

20:00 AI 자문은 cycle445 부터 주간 자문일(기본 목요일)에만 돈다. 행은 요일을 몰라
주 4일 `not_fired` 로 보였다. 자문일이 아닌 날 산출물이 없으면 `skipped_weekly` 다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import src.routes.market_ops as mo

pytestmark = pytest.mark.unit
_KST = timezone(timedelta(hours=9))


@pytest.mark.parametrize("status", ["not_fired", "scheduled"])
def test_non_advisory_day_without_evidence_is_skipped_weekly(status):
    assert mo._recommendation_weekly_status(status, advisory_day=False) == "skipped_weekly"


@pytest.mark.parametrize("status", ["done", "running", "failed", "unknown"])
def test_evidence_wins_on_non_advisory_day(status):
    assert mo._recommendation_weekly_status(status, advisory_day=False) == status


@pytest.mark.parametrize("advisory_day", [True, None])
def test_advisory_day_or_unknown_keeps_status(advisory_day):
    assert mo._recommendation_weekly_status("not_fired", advisory_day=advisory_day) == "not_fired"


async def test_advisory_day_probe_is_never_raise(monkeypatch):
    from src.engine import weekly_advisory

    async def boom(_now):
        raise RuntimeError("db")

    monkeypatch.setattr(weekly_advisory, "should_run_weekly_advisory", boom)
    assert await mo._is_weekly_advisory_today(datetime(2026, 10, 16, 21, 0, tzinfo=_KST)) is None


async def test_advisory_day_probe_delegates(monkeypatch):
    from src.engine import weekly_advisory

    async def fake(_now):
        return False

    monkeypatch.setattr(weekly_advisory, "should_run_weekly_advisory", fake)
    assert await mo._is_weekly_advisory_today(datetime(2026, 10, 16, 21, 0, tzinfo=_KST)) is False


def test_route_wires_weekly_status_before_finalize():
    src = open(mo.__file__, encoding="utf-8").read()
    seg = src[src.index('"recommendation", "AI 매매자문"') - 600: src.index('"recommendation", "AI 매매자문"') + 400]
    assert "_recommendation_weekly_status(" in seg
    assert "_finalize_status(" in seg[seg.index("_recommendation_weekly_status("):]
