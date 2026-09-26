"""cycle369 Red — J27 · K20 테스트 간 레지스트리 누수 방지.

매수 차단 레지스트리는 **모듈 전역**이다. api 테스트가 `short_over_yn:"Y"` 픽스처로
`005930` 을 기록하면, 같은 날짜로 도는 무관한 테스트(`test_cycle233_watcher_gate.py`
의 `_account_soft_gate_blocked("005930") is False`)가 뒤집힌다 — 시각·순서 의존 flaky.

그래서 `tests/conftest.py::_neutralize_status_watch`(autouse)가 매 테스트 전에

1. `status_exit_watch.reset_state_for_test()` 로 레지스트리를 비우고
2. 마커 `real_status_watch` 가 **없으면** `observe_fhkst` → no-op, `buy_gate` → `False`,
   `task_loop` → 즉시 반환 코루틴으로 바꾼다
   (`task_loop` 는 `scheduler.start()` 를 도는 기존 테스트가 실 루프를 띄우지 않게 한다 —
   cycle363 「게이트를 넣는 사이클이 중립화 픽스처를 같이 만든다」).

이 파일은 **모듈 마커를 달지 않는다**(달면 옵트아웃이 전부에 걸려 검증이 공허해진다).
아래 테스트는 **파일 안 순서대로** 돈다 — 앞 테스트가 흘린 기록을 뒤 테스트가 보면 붉다.
"""
from __future__ import annotations

import asyncio

import pytest

from tests.unit.engine._cycle369_support import fhkst, leaf

pytestmark = pytest.mark.unit

_T = "005930"


def _flagged_005930():
    return fhkst(_T, iscd="59", mang="N", short_over="Y")


def _momentum():
    from src.engine.strategies.momentum import MomentumStrategy
    from src.engine.strategy_base import StrategyConfig

    return MomentumStrategy(StrategyConfig(strategy_id="momentum", name="momentum",
                                           params={"exchange": "KRX"}))


def test_1_unmarked_hook_records_nothing():
    """중립화 아래에서 관측 훅은 아무것도 기록하지 않는다."""
    from src.api import condition

    condition._notify_status_observer(_T, _flagged_005930())
    assert leaf().snapshot()["blocks"] == []


def test_2_unmarked_gate_is_false_even_if_recorded():
    """누군가 레지스트리에 직접 써도 중립화된 게이트는 False — 무관한 스위트가 흔들리지 않는다."""
    lf = leaf()
    lf.record_read(_T, lf.classify(_flagged_005930()), now=lf._now_kst(), src="p1")
    assert _momentum()._account_soft_gate_blocked(_T) is False


@pytest.mark.real_status_watch
def test_3_marked_registry_starts_empty():
    """직전 테스트가 `005930` 을 기록했다 — 리셋이 없으면 여기서 True 가 된다."""
    assert leaf().snapshot()["blocks"] == []
    assert leaf().buy_gate(_T, "momentum") is False
    assert _momentum()._account_soft_gate_blocked(_T) is False


@pytest.mark.real_status_watch
def test_4_marked_real_gate_works_here():
    """옵트아웃이 실제로 진짜 게이트를 돌려준다(공허한 옵트아웃 방지)."""
    lf = leaf()
    lf.record_read(_T, lf.classify(_flagged_005930()), now=lf._now_kst(), src="p1")
    assert lf.buy_gate(_T, "momentum") is True


def test_5_unmarked_after_marked_is_clean_again():
    assert leaf().snapshot()["blocks"] == []
    assert _momentum()._account_soft_gate_blocked(_T) is False


@pytest.mark.asyncio
async def test_6_unmarked_task_loop_is_inert(monkeypatch):
    """중립화된 `task_loop` 는 패스를 돌지 않고 즉시 끝난다.

    🔁 cycle369 R3 F6(Y14) — 시계를 **평일 10:00 KST**(청산 창 안)로 고정한다. 실제 루프는 15:28
    이후 즉시 끝나므로, 벽시계에 맡기면 중립화를 지워도 장 밖 시각에 도는 CI 에서 초록이었다.
    그리고 실제 루프가 반드시 부르는 것들(`refresh_modes` · 시드 · 조회 `_fetch`)을 기록기로 바꿔
    「아무것도 부르지 않았다」 를 잰다 — 옛 단언(`_wait_until` 미호출)은 실제 루프도 부르지 않는
    이름이라 공허했다.
    """
    from datetime import datetime

    from tests.unit.engine._cycle369_support import KST, hold, holder, make_sched

    lf = leaf()
    monkeypatch.setattr(lf, "_now_kst", lambda: datetime(2026, 9, 28, 10, 0, 0, tzinfo=KST))  # 월요일
    calls: list[str] = []
    s = holder("bull_flag_breakout")
    hold(s, _T)
    sched = make_sched(s)

    async def _refresh(*a, **k):
        calls.append("refresh_modes")

    async def _fetch(t, *a, **k):
        calls.append(f"fetch:{t}")
        return _flagged_005930()

    async def _seed(*a, **k):
        calls.append("seed")
        return {}

    async def _sleep(*a, **k):
        calls.append("sleep")
        sched._running = False

    monkeypatch.setattr(lf, "refresh_modes", _refresh)
    monkeypatch.setattr(lf, "_fetch", _fetch)
    monkeypatch.setattr(lf, "_load_fire_counts", _seed, raising=False)
    monkeypatch.setattr(lf, "_sleep", _sleep, raising=False)
    await asyncio.wait_for(lf.task_loop(sched), timeout=1.0)
    assert calls == [], f"중립화된 task_loop 가 실제 루프를 돌았다(평일 10:00): {calls}"
    assert sched.order_engine.calls == []


def test_7_neutralizer_is_registered_in_conftest():
    """픽스처 이름·마커 등록 — 마커 미등록이면 `filterwarnings=error` 로 스위트 전체가 죽는다."""
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    conftest = (root / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "def _neutralize_status_watch(" in conftest
    assert "real_status_watch" in conftest
    markers = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "tool"]["pytest"]["ini_options"]["markers"]
    assert any(m.startswith("real_status_watch:") for m in markers)
