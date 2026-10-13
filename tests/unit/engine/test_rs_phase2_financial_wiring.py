"""RS 2단계 Red — 16:40 재무 적재 task 에 추가 적재를 얹는 배선 (`data_load_tasks`).

명세 = `_workspace/design/2026-10-13_rs_fundamental_phase2.md` §A 「배선」.

계약:
- `stock_master_financial_load_task_loop` 가 `run_periodic_task_loop` 에 넘기는 `once_callable` 은
  ① `scanner._stock_master_financial_load_once(force=False)` → ② `fundamental_load_tasks.run_extra_loads_once()`
  순서로 부르고 ① 의 summary 를 그대로 돌려준다. 둘 다 **호출 시점 모듈 속성**으로 찾는다.
- ② 의 예외는 삼키고(`logger.exception`) ① summary 를 돌려준다.
- ① 이 실패해도 ② 는 돌고, 그 뒤 ① 의 예외를 그대로 다시 올린다(기존 graceful 계약 — 헬퍼가 처리).
- 나머지 kw(라벨·요약 서식·키·900초·168h)는 그대로다 — 기존 C3/cycle363/cycle193 가드와 겹치는 확인.

기존 가드 정합: `test_cycleC3_financial_load_task.py::SCHED-2` 는 루프 본체 소스에
`_stock_master_financial_load_once` 토큰을 요구한다 — 합성 함수를 루프 **안**(중첩) 에 두거나
루프 본체가 그 이름을 참조해야 한다(`scanner._stock_master_financial_load_once` 속성 참조도 토큰을 만족).
"""
from __future__ import annotations

from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import data_load_tasks, scanner

pytestmark = pytest.mark.unit

_ANNUAL_SUMMARY = {"total": 5, "updated": 4, "skipped": 1, "failed": 0, "elapsed_ms": 12}


async def _capture_once_and_kwargs() -> tuple:
    captured: dict = {}

    async def _capture(**kwargs):
        captured.update(kwargs)

    with patch("src.engine.task_loop_helper.run_periodic_task_loop", _capture):
        await data_load_tasks.stock_master_financial_load_task_loop(
            SimpleNamespace(_running=False), wait_time=time(16, 40),
        )
    return captured["once_callable"], captured


def _flt_module():
    import src.engine.fundamental_load_tasks as flt  # noqa: PLC0415 — 없으면 Red
    return flt


async def test_once_calls_annual_then_extras_and_returns_annual_summary(monkeypatch):
    flt = _flt_module()
    order: list[str] = []

    async def _annual(force=False):
        order.append(f"annual:{force}")
        return dict(_ANNUAL_SUMMARY)

    async def _extra(**kw):
        order.append("extra")
        return {"mode": "on"}

    once, _ = await _capture_once_and_kwargs()
    monkeypatch.setattr(scanner, "_stock_master_financial_load_once", _annual)
    monkeypatch.setattr(flt, "run_extra_loads_once", _extra)
    summary = await once()
    assert order == ["annual:False", "extra"], order
    assert summary == _ANNUAL_SUMMARY, "연간 요약 키·값 불변"


async def test_extra_exception_does_not_block_annual_summary(monkeypatch):
    flt = _flt_module()
    once, _ = await _capture_once_and_kwargs()
    monkeypatch.setattr(scanner, "_stock_master_financial_load_once",
                        AsyncMock(return_value=dict(_ANNUAL_SUMMARY)))
    monkeypatch.setattr(flt, "run_extra_loads_once", AsyncMock(side_effect=RuntimeError("boom")))
    assert await once() == _ANNUAL_SUMMARY


async def test_annual_exception_still_runs_extras_then_reraises(monkeypatch):
    flt = _flt_module()
    once, _ = await _capture_once_and_kwargs()
    extra = AsyncMock(return_value={})
    monkeypatch.setattr(scanner, "_stock_master_financial_load_once",
                        AsyncMock(side_effect=ValueError("annual down")))
    monkeypatch.setattr(flt, "run_extra_loads_once", extra)
    with pytest.raises(ValueError, match="annual down"):
        await once()
    assert extra.await_count == 1


async def test_once_is_not_the_bare_annual_function():
    once, _ = await _capture_once_and_kwargs()
    assert once is not scanner._stock_master_financial_load_once, "합성 함수로 바꿔야 한다"


async def test_other_kwargs_unchanged():
    _, kw = await _capture_once_and_kwargs()
    assert kw["task_label"] == "stock_master_financial_load"
    assert kw["summary_log_format"] == (
        "[stock_master_financial_load_task_summary] total=%d updated=%d "
        "skipped=%d failed=%d"
    )
    assert tuple(kw["summary_keys"]) == ("total", "updated", "skipped", "failed")
    assert kw["initial_delay_secs"] == 900
    assert kw["immediate_skip_if_fresh_hours"] == 168
    assert not kw.get("immediate_skip_if_fresh_since_trading_slot")

