"""cycle234 — tick blind 계측 (G2 대체 조치 ①, 관측 전용) R1~R3.

자문 cycle232 §3.5-γ: 부팅 시 직전 하트비트와의 갭 = 프로세스 부재 blind.
`market_blind_secs`(평일 09:00~15:30 KST 겹침)가 서버 스탑 재검토의 정량 근거.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.engine import uptime_monitor as um

KST = timezone(timedelta(hours=9))


@pytest.fixture(autouse=True)
def _reset():
    um.reset_state_for_test()
    yield
    um.reset_state_for_test()


def _dt(y, m, d, hh, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=KST)


class TestR1MarketOverlap:
    """2026-08-31(월)~09-04(금) 평일, 08-29/30 = 토/일."""

    def test_fully_inside_market_hours(self):
        assert um.market_blind_overlap_secs(
            _dt(2026, 8, 31, 9, 30), _dt(2026, 8, 31, 10, 30)) == 3600

    def test_overnight_zero(self):
        assert um.market_blind_overlap_secs(
            _dt(2026, 8, 31, 16, 0), _dt(2026, 9, 1, 8, 0)) == 0

    def test_weekend_zero(self):
        assert um.market_blind_overlap_secs(
            _dt(2026, 8, 29, 10, 0), _dt(2026, 8, 30, 14, 0)) == 0

    def test_boundary_partial(self):
        # 08:00 → 09:10 = 09:00~09:10 만 겹침 = 600s
        assert um.market_blind_overlap_secs(
            _dt(2026, 8, 31, 8, 0), _dt(2026, 8, 31, 9, 10)) == 600

    def test_multiday_gap(self):
        # 금(08-28) 15:00 → 월(08-31) 09:20 = 금 15:00~15:30(1800) + 월 09:00~09:20(1200)
        assert um.market_blind_overlap_secs(
            _dt(2026, 8, 28, 15, 0), _dt(2026, 8, 31, 9, 20)) == 3000

    def test_inverted_range_zero(self):
        assert um.market_blind_overlap_secs(
            _dt(2026, 8, 31, 10, 0), _dt(2026, 8, 31, 9, 0)) == 0


class TestR2BootReport:
    @pytest.mark.asyncio
    async def test_reports_gap_and_reheartbeats(self, monkeypatch, caplog):
        from src.db import system_config as sc
        now = datetime.now(KST)
        last = (now - timedelta(seconds=125)).isoformat()

        async def _get(label):
            return last

        recorded = {}

        async def _set(label, iso):
            recorded["label"] = label
            recorded["iso"] = iso

        monkeypatch.setattr(sc, "get_task_last_success", _get)
        monkeypatch.setattr(sc, "set_task_last_success", _set)
        with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
            await um.report_boot_blind_gap()
        hits = [r for r in caplog.records if "[tick_blind_boot]" in r.message]
        assert len(hits) == 1
        assert "downtime_secs=" in hits[0].message
        assert "market_blind_secs=" in hits[0].message
        # 갭 보고 직후 하트비트 재기록 — 다음 재시작의 기준점
        assert recorded.get("label") == um.HEARTBEAT_TASK_LABEL

    @pytest.mark.asyncio
    async def test_first_boot_marker(self, monkeypatch, caplog):
        from src.db import system_config as sc

        async def _get(label):
            return None

        async def _set(label, iso):
            pass

        monkeypatch.setattr(sc, "get_task_last_success", _get)
        monkeypatch.setattr(sc, "set_task_last_success", _set)
        with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
            await um.report_boot_blind_gap()
        assert any("first_boot" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_future_marker_clamped_to_zero(self, monkeypatch, caplog):
        from src.db import system_config as sc
        future = (datetime.now(KST) + timedelta(hours=1)).isoformat()

        async def _get(label):
            return future

        async def _set(label, iso):
            pass

        monkeypatch.setattr(sc, "get_task_last_success", _get)
        monkeypatch.setattr(sc, "set_task_last_success", _set)
        with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
            await um.report_boot_blind_gap()
        hits = [r for r in caplog.records if "[tick_blind_boot]" in r.message]
        assert hits and "downtime_secs=0" in hits[0].message

    @pytest.mark.asyncio
    async def test_never_raises(self, monkeypatch):
        from src.db import system_config as sc

        async def _boom(label):
            raise RuntimeError("db down")

        monkeypatch.setattr(sc, "get_task_last_success", _boom)
        await um.report_boot_blind_gap()  # 예외 전파 시 FAIL


class TestR3HeartbeatLoop:
    @pytest.mark.asyncio
    async def test_loop_repeats_until_stopped(self, monkeypatch):
        import asyncio
        calls = {"n": 0}
        sched = SimpleNamespace(_running=True)

        async def fake_hb():
            calls["n"] += 1
            if calls["n"] >= 2:
                sched._running = False

        monkeypatch.setattr(um, "record_heartbeat", fake_hb)

        async def fast_sleep(_):
            return None

        monkeypatch.setattr(um.asyncio, "sleep", fast_sleep)
        await asyncio.wait_for(um.heartbeat_loop(sched), timeout=2.0)
        assert calls["n"] >= 2

    @pytest.mark.asyncio
    async def test_loop_exits_immediately_when_not_running(self):
        import asyncio
        sched = SimpleNamespace(_running=False)
        await asyncio.wait_for(um.heartbeat_loop(sched), timeout=1.0)

    @pytest.mark.asyncio
    async def test_ensure_idempotent(self):
        import asyncio
        sched = SimpleNamespace(_running=False)
        um._hb_task = None
        um.ensure_heartbeat_loop(sched)
        first = um._hb_task
        assert first is not None
        um.ensure_heartbeat_loop(sched)
        if not first.done():
            assert um._hb_task is first
        await asyncio.sleep(0)
        um._hb_task = None
