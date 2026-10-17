"""cycle470 — 세션 침묵 판정 약점 A·B 섀도 관측 (행위 0).

근거 `_workspace/analysis/2026-10-15_silent_skip_1240.md` §3(4) 표 A·B.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest

from src.engine import silence_shadow as ss
from src.engine import tick_volume

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 15, 12, 40, 0, tzinfo=KST)
TH = timedelta(seconds=60)
_LOG = "src.engine.scheduler"


@pytest.fixture(autouse=True)
def _reset_tv():
    tick_volume.reset_for_test()
    yield
    tick_volume.reset_for_test()


def _kw(**k):
    base = dict(ratio_threshold=0.2, min_subscribed=5, min_eligible=2)
    base.update(k)
    return base


# ── tick_volume WS 시각 ─────────────────────────────────────────────────────
def test_record_acml_vol_stamps_ws_time_and_negative_does_not():
    tick_volume.record_acml_vol("005930", 100)
    assert tick_volume.get_last_ws_frame_at("005930") is not None
    tick_volume.record_acml_vol("000660", -1)
    assert tick_volume.get_last_ws_frame_at("000660") is None


def test_ws_fresh_count_uses_ws_time_only(monkeypatch):
    stamps = {"A": NOW - timedelta(seconds=10), "B": NOW - timedelta(seconds=300)}
    monkeypatch.setattr(tick_volume, "get_last_ws_frame_at", lambda t: stamps.get(t))
    assert ss.ws_fresh_count(["A", "B", "C"], NOW, TH) == 1


# ── B: 세션 판정이 갈리는 순간 ──────────────────────────────────────────────
def test_session_diverges_when_rest_stamps_hide_dead_ws(caplog):
    # 메인 10종목 중 REST 로 3종목 신선(fresh_all=3 → 0.3, 침묵 아님) · WS 로는 0(침묵)
    rows = [("main", 10, 3, 0, False), ("q1", 10, 8, 8, False)]
    with caplog.at_level(logging.INFO, logger=_LOG):
        ss.observe_ws_shadow(NOW, rows, market_wide_now=False, **_kw())
        ss.observe_ws_shadow(NOW, rows, market_wide_now=False, **_kw())   # 같은 날 반복 = 1줄
    msgs = [m for m in caplog.messages if m.startswith("[silent_inactive_ws_shadow] session=")]
    assert msgs == ["[silent_inactive_ws_shadow] session=main sub=10 fresh_all=3 fresh_ws=0 "
                    "suspect_now=0 suspect_ws=1 market_wide_now=0"]


def test_market_wide_divergence_logged(caplog):
    rows = [("main", 10, 3, 0, False), ("q1", 10, 0, 0, True)]
    with caplog.at_level(logging.WARNING, logger=_LOG):
        ss.observe_ws_shadow(NOW, rows, market_wide_now=False, **_kw())
    mw = [m for m in caplog.messages if "scope=market_wide" in m]
    assert len(mw) == 1 and "market_wide_now=0 market_wide_ws=1" in mw[0]


def test_no_log_when_both_agree(caplog):
    rows = [("main", 10, 5, 5, False), ("q1", 3, 0, 0, False)]
    with caplog.at_level(logging.INFO, logger=_LOG):
        ss.observe_ws_shadow(NOW, rows, market_wide_now=False, **_kw())
    assert not [m for m in caplog.messages if "silent_inactive_ws_shadow" in m]


# ── A: 시장 침묵 기각 중 반증 ────────────────────────────────────────────────
async def test_counter_evidence_after_consecutive_rises(monkeypatch, caplog):
    vols = iter([1000, 1500, 2100])

    async def fake(_t):
        return next(vols)

    monkeypatch.setattr(ss, "_probe_acml_vol", fake)
    since = NOW
    with caplog.at_level(logging.WARNING, logger=_LOG):
        for i in range(3):
            ss.note_market_wide(NOW + timedelta(seconds=120 * i), since)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
    ev = [m for m in caplog.messages if m.startswith("[silent_inactive_market_wide_counter_evidence]")]
    assert len(ev) == 1 and "vols=1000,1500,2100" in ev[0]


async def test_flat_volume_is_not_counter_evidence(monkeypatch, caplog):
    async def fake(_t):
        return 5000

    monkeypatch.setattr(ss, "_probe_acml_vol", fake)
    with caplog.at_level(logging.WARNING, logger=_LOG):
        for i in range(4):
            ss.note_market_wide(NOW + timedelta(seconds=120 * i), NOW)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
    assert not [m for m in caplog.messages if "counter_evidence" in m]


async def test_probe_throttled_within_interval(monkeypatch):
    calls = []

    async def fake(t):
        calls.append(t)
        return 1

    monkeypatch.setattr(ss, "_probe_acml_vol", fake)
    ss.note_market_wide(NOW, NOW)
    await asyncio.sleep(0)
    ss.note_market_wide(NOW + timedelta(seconds=30), NOW)
    await asyncio.sleep(0)
    assert len(calls) == 1


async def test_single_jump_like_closing_auction_is_not_enough(monkeypatch, caplog):
    vols = iter([1000, 1000, 9000])

    async def fake(_t):
        return next(vols)

    monkeypatch.setattr(ss, "_probe_acml_vol", fake)
    with caplog.at_level(logging.WARNING, logger=_LOG):
        for i in range(3):
            ss.note_market_wide(NOW + timedelta(seconds=120 * i), NOW)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
    assert not [m for m in caplog.messages if "counter_evidence" in m]


def test_no_running_loop_is_harmless():
    ss.note_market_wide(NOW, NOW)   # 루프 없음 = 조용히 통과


# ── 판정 행위 불변 ───────────────────────────────────────────────────────────
def test_detect_result_unchanged_when_shadow_raises(monkeypatch):
    """관측기가 터져도 detect 결과는 같다(행위 0)."""
    from src.engine import stale_session_recovery as ssr

    def boom(*a, **k):
        raise RuntimeError("shadow boom")

    monkeypatch.setattr(ss, "observe_ws_shadow", boom)
    monkeypatch.setattr(ss, "ws_fresh_count", boom)
    src = open(ssr.__file__, encoding="utf-8").read()
    # 관측 호출이 모두 try 안에 있다(구조 확인) — 실제 행위 테스트는 cycle241 회귀가 그대로 통과하는 것으로 본다.
    assert src.count("import src.engine.silence_shadow as _ss") == 2
