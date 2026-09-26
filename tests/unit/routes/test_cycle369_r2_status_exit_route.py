"""cycle369 round 2 Red — Q1 라우트 끝단. 저장 실패한 `off` 가 다음 패스에 살아남는다.

round-1 R5 는 PUT **직후** 메모리만 봤다. 그래서 「다음 패스의 refresh 가 60초(매수)·300초(청산)
안에 enforce 로 되돌린다」는 결함(리뷰 3건 MEDIUM, 실모듈 재현)이 초록으로 통과했다.
여기서는 PUT 뒤 **실제 패스**를 돌려 본다.

| 경로 | 기대 |
|---|---|
| PUT off · 저장 실패 → `refresh_modes` / `run_sell_pass` / `run_buy_pass` | off 유지 · 조회 0 · 발사 0 |
| 응답 `message` | 고정(다음 성공 저장 또는 재시작까지)을 말한다 — 「재시작 시 원복될 수 있다」만으로는 부족 |
| 한 축만 실패 | 실패한 축만 고정. 저장 성공한 축은 뒤의 SQL UPDATE 를 따른다 |
| 뒤의 성공 PUT | 고정 해제 |
| 🔁 R3 F4 — 저장이 **걸린** PUT | 메모리 off 가 DB 쓰기를 기다리지 않는다: 먼저 고정(`persisted=False`)으로 반영 → DB 쓰기 → 성공이면 다시 `persisted=True`(고정 해제). 한 요청의 두 축은 **둘 다** 쓰기 전에 반영된다 |

검증 패턴 = 라우트 함수 직접 await(cycle127 anyio portal hang 차단 관례).
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from tests.unit.engine._cycle369_support import (
    LIVE,
    clock,  # noqa: F401 — pytest 픽스처
    dblog,  # noqa: F401
    fetch,  # noqa: F401
    cand,
    hold,
    holder,
    leaf,
    make_sched,
    records,
)

pytestmark = [pytest.mark.unit, pytest.mark.real_status_watch]

_PATH = "/api/integrations/status-exit"


def _endpoint(method: str):
    from src.routes import system_integrations

    for r in system_integrations.router.routes:
        if getattr(r, "path", None) == _PATH and method in getattr(r, "methods", set()):
            return r.endpoint
    pytest.fail(f"{method} {_PATH} 라우트 미등록")


def _req(**body):
    from src.models.system_integrations import StatusExitModeRequest

    return StatusExitModeRequest(**body)


@pytest.fixture
def store(monkeypatch):
    """getter/setter 4종 스텁 — **축마다** 저장 실패를 고를 수 있다. 읽기는 저장값(행 없으면 None)."""
    from src.db import system_config as sc

    state = {"sell": None, "buy": None, "fail_sell": False, "fail_buy": False, "saved": []}

    async def _get_sell():
        return state["sell"]

    async def _get_buy():
        return state["buy"]

    async def _set_sell(mode):
        if state["fail_sell"]:
            raise RuntimeError("db write failed")
        state["saved"].append(("sell", mode))
        state["sell"] = mode

    async def _set_buy(mode):
        if state["fail_buy"]:
            raise RuntimeError("db write failed")
        state["saved"].append(("buy", mode))
        state["buy"] = mode

    monkeypatch.setattr(sc, "get_status_exit_mode_raw", _get_sell, raising=False)
    monkeypatch.setattr(sc, "get_status_buy_block_mode_raw", _get_buy, raising=False)
    monkeypatch.setattr(sc, "set_status_exit_mode", _set_sell, raising=False)
    monkeypatch.setattr(sc, "set_status_buy_block_mode", _set_buy, raising=False)
    return state


@pytest.mark.asyncio
async def test_r5b_failed_put_off_survives_next_refresh(store, clock):
    """R5b — 첫 PUT 이 저장에 실패하면 행이 없다(None). 다음 refresh 가 enforce 로 되돌리면 안 된다."""
    store["fail_sell"] = store["fail_buy"] = True
    clock.set(10, 0)
    resp = await _endpoint("PUT")(_req(sell_mode="off", buy_block_mode="off"))
    assert resp.data["persisted"] is False
    for _ in range(3):
        await leaf().refresh_modes()
    assert leaf().current_modes() == {"sell": "off", "buy": "off"}, (
        "저장 실패한 off 가 다음 refresh 에 enforce 로 되돌았다 — 사고 중 끈 청산이 60~300초 안에 다시 켜진다"
    )


@pytest.mark.asyncio
async def test_r5c_failed_put_off_holds_through_real_passes(store, clock, fetch, dblog):
    """R5c — 실제 패스(모두 시작 시 refresh)를 돌려도 off 는 off: 조회 0 · 발사 0."""
    store["fail_sell"] = store["fail_buy"] = True
    s = cand("bull_flag_breakout", candidates=["200001"])
    hold(s, "005160")
    sched = make_sched(s)
    fetch.table["005160"] = LIVE["005160"]
    fetch.table["200001"] = LIVE["294140"]

    clock.set(10, 0)
    await _endpoint("PUT")(_req(sell_mode="off", buy_block_mode="off"))
    clock.set(10, 0, 30)
    await leaf().run_sell_pass(sched)
    clock.set(10, 1, 0)
    await leaf().run_buy_pass(sched, kind="inc")
    clock.set(10, 5, 30)
    await leaf().run_sell_pass(sched)
    assert fetch.calls == [], f"off 인데 조회했다: {fetch.calls}"
    assert sched.order_engine.calls == [], "저장 실패한 off 뒤에 시장가 매도가 나갔다"


@pytest.mark.asyncio
async def test_r5d_failure_message_describes_pin(store, clock):
    """응답 message 가 실제 동작(메모리 고정 — 다음 성공 저장 또는 재시작까지)을 말한다."""
    store["fail_sell"] = True
    clock.set(10, 0)
    resp = await _endpoint("PUT")(_req(sell_mode="off"))
    msg = resp.message or ""
    assert any(tok in msg for tok in ("고정", "유지", "pinned")), (
        f"저장 실패 메시지가 고정 동작을 말하지 않는다: {msg!r}"
    )


@pytest.mark.asyncio
async def test_r5e_only_failed_axis_is_pinned(store, clock):
    """sell 저장 실패 · buy 저장 성공 → sell 만 고정. buy 는 뒤의 SQL UPDATE 를 따른다."""
    store["fail_sell"] = True
    clock.set(10, 0)
    resp = await _endpoint("PUT")(_req(sell_mode="off", buy_block_mode="off"))
    assert resp.data["persisted"] is False
    store["buy"] = "enforce"            # 운영자 SQL UPDATE (buy 는 저장이 됐던 축)
    await leaf().refresh_modes()
    assert leaf().current_modes() == {"sell": "off", "buy": "enforce"}


@pytest.mark.asyncio
async def test_r5f_later_successful_put_unpins(store, clock):
    store["fail_sell"] = True
    clock.set(10, 0)
    await _endpoint("PUT")(_req(sell_mode="off"))
    store["fail_sell"] = False
    resp = await _endpoint("PUT")(_req(sell_mode="observe"))
    assert resp.data["persisted"] is True
    store["sell"] = "enforce"           # 그 뒤 SQL UPDATE
    await leaf().refresh_modes()
    assert leaf().current_modes()["sell"] == "enforce", "성공 저장 뒤에도 고정이 남았다"


@pytest.mark.asyncio
async def test_r5g_pinned_warning_through_route(store, clock, caplog):
    caplog.set_level(logging.INFO, logger="src.engine.status_exit_watch")
    store["fail_sell"] = True
    clock.set(10, 0)
    await _endpoint("PUT")(_req(sell_mode="off"))
    await leaf().refresh_modes()
    await leaf().refresh_modes()
    pinned = records(caplog, "[status_exit_mode_pinned]", min_level=logging.WARNING)
    assert len(pinned) == 1


@pytest.mark.asyncio
async def test_r5h_successful_put_does_not_pin_control(store, clock):
    """대조 — 저장 성공이면 고정 없음: 그 뒤 SQL UPDATE 가 반영된다(R2 계약 유지)."""
    clock.set(10, 0)
    resp = await _endpoint("PUT")(_req(sell_mode="off"))
    assert resp.data["persisted"] is True
    store["sell"] = "enforce"
    await leaf().refresh_modes()
    assert leaf().current_modes()["sell"] == "enforce"


# ===========================================================================
# 🔁 cycle369 R3 F4 — RDS 가 멈춰도 메모리 off 는 기다리지 않는다
#
# R2 라우트는 `await sc.set_status_exit_mode(...)` 가 **돌아온 뒤**에 `apply_mode` 를 불렀다.
# `pg.execute` 는 acquire 타임아웃이 없고 `command_timeout=30s` 라, RDS 가 멈추면 운영자의 `off`
# 가 30초 넘게 메모리에 안 닿고 그 사이 도는 청산 패스가 시장가 매도를 낸다.
# 결정 F4 = 메모리에 **먼저 고정으로** 반영(`persisted=False`) → DB 쓰기 await → 성공이면 다시
# `persisted=True`(고정 해제). 고정이라 쓰기가 걸린 동안의 refresh 도 DB 의 옛 값으로 되돌리지 못한다.
# ===========================================================================
class _Stall:
    """setter 를 축마다 게이트에서 멈출 수 있게 감싼다(RDS 정지 모양) · 순서 기록."""

    def __init__(self, monkeypatch) -> None:
        from src.db import system_config as sc

        self.gate = {"sell": asyncio.Event(), "buy": asyncio.Event()}
        self.entered = {"sell": asyncio.Event(), "buy": asyncio.Event()}
        self.hold = {"sell": False, "buy": False}
        self.events: list[tuple] = []
        inner = {"sell": sc.set_status_exit_mode, "buy": sc.set_status_buy_block_mode}

        def _wrap(kind):
            async def _set(mode):
                self.events.append(("write_start", kind, mode))
                if self.hold[kind]:
                    self.entered[kind].set()
                    await self.gate[kind].wait()
                await inner[kind](mode)
                self.events.append(("write_ok", kind, mode))
            return _set

        monkeypatch.setattr(sc, "set_status_exit_mode", _wrap("sell"), raising=False)
        monkeypatch.setattr(sc, "set_status_buy_block_mode", _wrap("buy"), raising=False)

        lf = leaf()
        real_apply = lf.apply_mode

        def _spy(kind, mode, *a, **k):
            persisted = k.get("persisted", a[0] if a else True)
            self.events.append(("apply", kind, mode, bool(persisted)))
            return real_apply(kind, mode, *a, **k)

        monkeypatch.setattr(lf, "apply_mode", _spy)

    def release_all(self) -> None:
        for g in self.gate.values():
            g.set()


@pytest.fixture
def stall(store, monkeypatch):
    st = _Stall(monkeypatch)
    yield st
    st.release_all()


@pytest.mark.asyncio
async def test_f4_rds_stall_cannot_delay_in_memory_off(store, stall, clock, fetch, dblog):
    """sell 쓰기가 걸린 동안 — 메모리는 이미 off · 그 사이 도는 청산 패스는 조회 0 · 발사 0."""
    s = holder("bull_flag_breakout")
    hold(s, "005160")
    sched = make_sched(s)
    fetch.table["005160"] = LIVE["005160"]
    store["sell"] = "enforce"                        # DB 현재값(행 있음)
    stall.hold["sell"] = True
    clock.set(10, 0, 30)
    task = asyncio.create_task(_endpoint("PUT")(_req(sell_mode="off")))
    try:
        await asyncio.wait_for(stall.entered["sell"].wait(), timeout=2.0)
        assert leaf().current_modes()["sell"] == "off", (
            "DB 쓰기가 걸린 동안 메모리가 아직 enforce — 운영자의 off 가 RDS 지연에 묶였다"
        )
        await leaf().run_sell_pass(sched)            # 쓰기가 걸린 채 다음 청산 패스(시작 때 refresh)
        assert leaf().current_modes()["sell"] == "off", (
            "쓰기가 걸린 동안 refresh 가 DB 의 옛 enforce 로 되돌렸다 — 저장 전 반영은 고정이어야 한다"
        )
        assert fetch.calls == [] and sched.order_engine.calls == [], (
            f"off 를 보냈는데 쓰기가 끝나기 전 패스가 조회·발사했다: {fetch.calls} {sched.order_engine.calls}"
        )
    finally:
        stall.release_all()
    resp = await asyncio.wait_for(task, timeout=2.0)
    assert resp.data["persisted"] is True

    # 저장 성공 뒤에는 고정이 풀린다 — 그 뒤 SQL UPDATE 를 따른다(R2 계약 유지)
    store["sell"] = "enforce"
    await leaf().refresh_modes()
    assert leaf().current_modes()["sell"] == "enforce", "성공 저장 뒤에도 고정이 남았다"


@pytest.mark.asyncio
async def test_f4_both_axes_reach_memory_before_any_db_write(store, stall, clock):
    """한 요청의 두 축 — sell 쓰기가 걸려도 buy 의 off 까지 이미 메모리에 있다."""
    stall.hold["sell"] = True
    clock.set(10, 0)
    task = asyncio.create_task(_endpoint("PUT")(_req(sell_mode="off", buy_block_mode="off")))
    try:
        await asyncio.wait_for(stall.entered["sell"].wait(), timeout=2.0)
        assert leaf().current_modes() == {"sell": "off", "buy": "off"}, (
            f"한 축의 DB 쓰기가 다른 축의 메모리 반영을 막았다: {leaf().current_modes()}"
        )
    finally:
        stall.release_all()
    resp = await asyncio.wait_for(task, timeout=2.0)
    assert resp.data["persisted"] is True


@pytest.mark.asyncio
async def test_f4_order_pinned_apply_then_write_then_unpin(store, stall, clock):
    """순서 계약 — 축마다 `apply(persisted=False)` → 쓰기 → (성공 시) `apply(persisted=True)`."""
    clock.set(10, 0)
    resp = await _endpoint("PUT")(_req(sell_mode="observe", buy_block_mode="off"))
    assert resp.data["persisted"] is True
    ev = stall.events
    for kind, mode in (("sell", "observe"), ("buy", "off")):
        for step in (("apply", kind, mode, False), ("write_start", kind, mode),
                     ("write_ok", kind, mode), ("apply", kind, mode, True)):
            assert step in ev, f"{step} 없음 — 메모리 고정 반영이 DB 쓰기보다 먼저여야 한다: {ev}"
        pinned = ev.index(("apply", kind, mode, False))
        started = ev.index(("write_start", kind, mode))
        ok = ev.index(("write_ok", kind, mode))
        unpinned = ev.index(("apply", kind, mode, True))
        assert pinned < started < ok < unpinned, (kind, ev)
    first_write = min(i for i, e in enumerate(ev) if e[0] == "write_start")
    assert all(ev.index(("apply", k, m, False)) < first_write
               for k, m in (("sell", "observe"), ("buy", "off"))), ev


@pytest.mark.asyncio
async def test_f4_failed_write_after_stall_stays_pinned(store, stall, clock):
    """걸렸다가 실패한 쓰기 — 고정은 풀리지 않는다(`persisted=True` 재반영 없음) · refresh 가 못 되돌린다."""
    store["fail_sell"] = True
    store["sell"] = "enforce"
    clock.set(10, 0)
    resp = await _endpoint("PUT")(_req(sell_mode="off"))
    assert resp.data["persisted"] is False
    assert ("apply", "sell", "off", True) not in stall.events, stall.events
    await leaf().refresh_modes()
    assert leaf().current_modes()["sell"] == "off"

