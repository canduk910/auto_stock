"""cycle369 Red — 보유 청산(sell side). 명세 §3 · 자문 §4(a)(b)(e)(g)(h).

| 절 | 무엇 |
|---|---|
| B | 발사 창 `09:00:30 <= now < 15:28:00` KST — 경계 양쪽 |
| C | 확인 두 번 — 창 안 **이번 패스의 조회값**으로만 발사 |
| D | 발사 계약 — `execute_sell(t, Signal.STATUS_EXIT, sid)` · `limit_price` 없음 · 상한 3회/일 |
| E | 청산 킬스위치 `status_exit_mode` (enforce·observe·off · 키 없음·모름·DB 예외) |

- 대상 = `registry.all()` 의 모든 전략(**꺼진 전략 포함**)의 `state.positions` 중 `quantity > 0`.
- 조회 = `src.api.condition.fetch_stock_detail` 만(테스트는 그 이름을 스텁으로 바꾼다).
- 시각 = `status_exit_watch._now_kst` seam(테스트 `clock` 픽스처).
- caplog = 로거명 `src.engine.status_exit_watch` + 레벨 하한 + 마커 prefix 3중 한정(cycle252 T2).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.unit.engine._cycle369_support import (
    DAY,
    LIVE,
    NEXT_DAY,
    FakeOrderEngine,
    clean,
    clock,  # noqa: F401 — pytest 픽스처
    db_modes,  # noqa: F401
    dblog,  # noqa: F401
    drain_writes,
    fetch,  # noqa: F401
    fhkst,
    field,
    hold,
    holder,
    leaf,
    lines,
    make_sched,
    managed,
    open_info,
    overheat,
    records,
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.real_status_watch,
    pytest.mark.usefixtures("no_real_kis"),
]


@pytest.fixture(autouse=True)
def _info(caplog, db_modes):
    open_info(caplog)


def _sched_with(ticker="005160", *, sid="bull_flag_breakout", enabled=True, qty=3,
                buy_date=date(2026, 9, 25)):
    s = holder(sid, enabled=enabled)
    hold(s, ticker, qty=qty, buy_date=buy_date)
    return make_sched(s), s


async def _sell(sched):
    return await leaf().run_sell_pass(sched)


# ===========================================================================
# B. 발사 창
# ===========================================================================
@pytest.mark.asyncio
async def test_b1_pre_pass_before_open_arms_but_never_fires(clock, fetch, dblog, caplog):
    """B1 — 08:59:59 장 전 패스: 해당이어도 주문 0 · `[status_exit_armed]` 1."""
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(8, 59, 59)
    await leaf().run_pre_pass(sched)
    assert sched.order_engine.calls == [], "장 전 값으로 발사했다(K5)"
    armed = lines(caplog, "[status_exit_armed]")
    assert len(armed) == 1
    assert field(armed[0], "ticker") == "005160"
    assert field(armed[0], "phase") == "pre"


@pytest.mark.asyncio
async def test_b1b_sell_pass_before_window_never_fires(clock, fetch, dblog):
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(8, 59, 59)
    await _sell(sched)
    assert sched.order_engine.calls == []
    # 🔁 cycle369 R3 F6 — 창 밖 패스는 **조회도 0**(패스 첫머리 창 판정). 발사 직전 재확인(Q3)만
    # 남기고 패스 첫머리 판정을 지워도 주문 0 은 그대로라, 조회 수로만 그 회귀(M8·M9)가 드러난다.
    assert fetch.calls == [], f"창 밖 청산 패스가 보유 종목을 읽었다: {fetch.calls}"


@pytest.mark.asyncio
async def test_b2_window_start_boundary(clock, fetch, dblog):
    """B2 — 09:00:29 → 0회 / 09:00:30 → 1회."""
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(9, 0, 29)
    await _sell(sched)
    assert sched.order_engine.calls == []
    clock.set(9, 0, 30)
    await _sell(sched)
    assert sched.order_engine.fired() == [("005160", "bull_flag_breakout")]


@pytest.mark.asyncio
async def test_b3_window_end_boundary(clock, fetch, dblog):
    """B3 — 15:27:59 → 1회 / 15:28:00 → 0회 (반열린 구간)."""
    sched, _ = _sched_with("294140")
    fetch.table["294140"] = LIVE["294140"]
    clock.set(15, 27, 59)
    await _sell(sched)
    assert len(sched.order_engine.calls) == 1

    sched2, _ = _sched_with("294140")
    leaf().reset_state_for_test()
    clock.set(15, 28, 0)
    await _sell(sched2)
    assert sched2.order_engine.calls == [], "15:28:00 은 창 밖이다(15:30 종가 단일가 직전 컷)"


@pytest.mark.asyncio
async def test_b4_after_market_never_fires(clock, fetch, dblog, monkeypatch):
    """B4 — 16:30 KRX 애프터(실전): 단기과열은 애프터 거래대상 제외(KRX 원문) → 발사 금지(K4)."""
    from src.config import settings

    monkeypatch.setattr(settings, "kis_env", "real")
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(16, 30)
    await _sell(sched)
    assert sched.order_engine.calls == []
    assert fetch.calls == [], f"🔁 R3 F6 — 창 밖(애프터) 청산 패스가 조회했다: {fetch.calls}"


@pytest.mark.asyncio
@pytest.mark.parametrize("hms", [(7, 50, 0), (20, 30, 0), (15, 45, 0)])
async def test_b5_outside_window_never_fires(clock, fetch, dblog, hms):
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(*hms)
    await _sell(sched)
    assert sched.order_engine.calls == []
    assert fetch.calls == [], f"🔁 R3 F6 — 창 밖 청산 패스가 조회했다: {fetch.calls}"


# ===========================================================================
# C. 확인 두 번
# ===========================================================================
@pytest.mark.asyncio
async def test_c1_pre_armed_but_clean_in_window_is_disarmed(clock, fetch, dblog, caplog):
    """C1 — P0(08:45) 해당 → 09:00:30 창 안 재조회 clean → 0회 + disarmed (M11)."""
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(8, 45)
    await leaf().run_pre_pass(sched)
    assert lines(caplog, "[status_exit_armed]")

    fetch.table["005160"] = clean("005160")
    clock.set(9, 0, 30)
    await _sell(sched)
    assert sched.order_engine.calls == [], "장 전 arm 만으로 발사했다 — 창 안 재조회가 발사 근거여야 한다"
    assert len(lines(caplog, "[status_exit_disarmed]")) == 1
    assert fetch.count("005160") == 2, "창 안에서 다시 읽지 않았다"


@pytest.mark.asyncio
async def test_c2_frame_hint_alone_never_fires(clock, fetch, dblog, caplog, monkeypatch):
    """C2 — 프레임 `H0UNMKO0` 은 59 인데 REST 가 N → 0회 + `[status_exit_frame_hint]`."""
    from src.engine import market_operation_monitor as mom

    monkeypatch.setattr(mom, "get_last_event",
                        lambda t: SimpleNamespace(iscd_stat_cls_code="59", mksc_shrn_iscd=t))
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = clean("005160")
    clock.set(10, 0)
    await _sell(sched)
    assert sched.order_engine.calls == []
    assert len(lines(caplog, "[status_exit_frame_hint]")) == 1


@pytest.mark.asyncio
async def test_c3_fetch_error_no_fire_then_retry_next_pass(clock, fetch, dblog, caplog):
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = RuntimeError("quote pool down")
    clock.set(10, 0, 30)
    await _sell(sched)
    assert sched.order_engine.calls == []
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 5, 30)
    await _sell(sched)
    assert len(sched.order_engine.calls) == 1, "다음 패스에서 다시 읽고 발사해야 한다"


@pytest.mark.asyncio
async def test_c4_unknown_response_never_fires(clock, fetch, dblog, caplog):
    """A5 모양(칸 None · 현재가 0) 보유 → 발사 0 + `[status_exit_unknown]` 1회/일."""
    sched, _ = _sched_with("043090")
    fetch.table["043090"] = LIVE["043090"]
    clock.set(10, 0, 30)
    await _sell(sched)
    clock.set(10, 5, 30)
    await _sell(sched)
    assert sched.order_engine.calls == []
    assert len(lines(caplog, "[status_exit_unknown]")) == 1


@pytest.mark.asyncio
async def test_c5_short_sale_overheat_and_notice_never_fire(clock, fetch, dblog):
    """K1·K2 — 공매도과열·단기과열 예고는 팔지 않는다."""
    s = holder("kojiro")
    hold(s, "035760")
    hold(s, "356680")
    sched = make_sched(s)
    fetch.table["035760"] = fhkst("035760", iscd="55", mang="N", short_over="N", ssts_hot_yn="Y")
    fetch.table["356680"] = LIVE["356680"]
    clock.set(10, 0, 30)
    await _sell(sched)
    assert sched.order_engine.calls == []


@pytest.mark.asyncio
async def test_c6_flagged_but_price_zero_is_unknown_not_fired(clock, fetch, dblog, caplog):
    """발사는 가격이 확인된 창 안 조회값으로만 — 현재가 0 이면 「모름」(명세 §2 청산 해석)."""
    sched, _ = _sched_with("123450")
    fetch.table["123450"] = managed("123450", prpr="0")
    clock.set(10, 0, 30)
    await _sell(sched)
    assert sched.order_engine.calls == []
    assert len(lines(caplog, "[status_exit_unknown]")) == 1


# ===========================================================================
# D. 발사 계약
# ===========================================================================
@pytest.mark.asyncio
async def test_d1_fire_contract_market_status_exit(clock, fetch, dblog, caplog):
    """D1 — `(ticker, Signal.STATUS_EXIT, sid)` · `limit_price` 없음 = 시장가 · 영속 기록."""
    from src.engine.strategy_base import Signal

    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 0, 30)
    await _sell(sched)
    assert len(sched.order_engine.calls) == 1
    ticker, signal, sid, args, kwargs = sched.order_engine.calls[0]
    assert (ticker, sid) == ("005160", "bull_flag_breakout")
    assert signal == Signal.STATUS_EXIT
    assert signal.value == "STATUS_EXIT"
    assert "limit_price" not in kwargs and args == (), "지정가 인자 전달 금지 — 시장가가 계약"

    fire = records(caplog, "[status_exit_fire]", min_level=logging.WARNING)
    assert len(fire) == 1
    msg = fire[0].getMessage()
    assert field(msg, "reason") == "overheat"
    assert field(msg, "mode") == "enforce"
    assert field(msg, "attempt") == "1"
    assert field(msg, "qty") == "3"
    # 🔁 cycle369 R3 F3 — 영속은 루트 `_DbLogHandler` 가 위 logger WARNING(로거 `src.engine.status_exit_watch`)
    # 을 옮겨 적는 한 줄뿐이다. leaf 가 write_log 로 또 쓰면 같은 발사가 두 줄(cycle72 G-6).
    # 한 줄 계약 자체는 `test_cycle369_r2_sell_safety.py::test_f3_each_event_persists_exactly_one_row`.
    await drain_writes()
    assert dblog.lines("[status_exit_fire]") == [], "발사 기록을 write_log 로 한 번 더 썼다 — system_logs 두 줄"
    summary = lines(caplog, "[status_exit_summary]")
    assert summary and field(summary[-1], "fired") == "1"


@pytest.mark.asyncio
async def test_d2_disabled_strategy_holding_is_liquidated(clock, fetch, dblog):
    """D2 — 꺼진 전략의 보유도 대상(M16 — `registry.enabled()` 로 축소 금지)."""
    sched, _ = _sched_with("294140", sid="kojiro", enabled=False)
    fetch.table["294140"] = LIVE["294140"]
    clock.set(11, 0, 30)
    await _sell(sched)
    assert sched.order_engine.fired() == [("294140", "kojiro")]


@pytest.mark.asyncio
async def test_d3_no_position_or_zero_qty_is_skipped(clock, fetch, dblog):
    s = holder("momentum")
    hold(s, "294140", qty=0)
    sched = make_sched(s)
    fetch.table["294140"] = LIVE["294140"]
    clock.set(10, 0, 30)
    await _sell(sched)
    assert sched.order_engine.calls == []


@pytest.mark.asyncio
async def test_d4_already_selling_is_skipped(clock, fetch, dblog):
    sched, _ = _sched_with("005160")
    sched.order_engine._selling.add("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 0, 30)
    await _sell(sched)
    assert sched.order_engine.calls == []


@pytest.mark.asyncio
async def test_d5_three_fires_per_day_then_giveup_once(clock, fetch, dblog, caplog):
    """D5 — 하루 3회 상한. 4번째 패스 0회 + `[status_exit_giveup]` CRITICAL 1회."""
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    for hm in ((9, 0, 30), (9, 5, 30), (9, 10, 30), (9, 15, 30), (9, 20, 30)):
        clock.set(*hm)
        await _sell(sched)
    assert len(sched.order_engine.calls) == 3
    attempts = [field(m, "attempt") for m in lines(caplog, "[status_exit_fire]", min_level=logging.WARNING)]
    assert attempts == ["1", "2", "3"]
    giveup = records(caplog, "[status_exit_giveup]", min_level=logging.CRITICAL)
    assert len(giveup) == 1
    await drain_writes()   # 🔁 cycle369 R3 F3 — 영속은 루트 핸들러 한 줄(위 CRITICAL 로거 줄)
    assert dblog.lines("[status_exit_giveup]") == [], "giveup 을 write_log 로 한 번 더 썼다 — system_logs 두 줄"


@pytest.mark.asyncio
async def test_d6_counter_resets_next_day(clock, fetch, dblog):
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    for hm in ((9, 0, 30), (9, 5, 30), (9, 10, 30), (9, 15, 30)):
        clock.set(*hm)
        await _sell(sched)
    assert len(sched.order_engine.calls) == 3
    clock.set(9, 0, 30, day=NEXT_DAY)
    await _sell(sched)
    assert len(sched.order_engine.calls) == 4, "날짜 키 카운터 — 다음 날 다시 판다(_reset_daily_state 무의존)"


@pytest.mark.asyncio
async def test_d7_halted_waits_then_fires_when_released(clock, fetch, dblog, caplog):
    """D7 — 016790(관리+58) → 0회 + wait_halt · 다음 패스 정지 해제면 1회(K8)."""
    sched, _ = _sched_with("016790")
    fetch.table["016790"] = LIVE["016790"]
    clock.set(9, 0, 30)
    await _sell(sched)
    clock.set(9, 5, 30)
    await _sell(sched)
    assert sched.order_engine.calls == []
    assert len(lines(caplog, "[status_exit_wait_halt]")) == 1
    fetch.table["016790"] = fhkst("016790", iscd="51", mang="Y", short_over="N")
    clock.set(9, 10, 30)
    await _sell(sched)
    assert len(sched.order_engine.calls) == 1


@pytest.mark.asyncio
async def test_d7b_temp_stop_is_also_a_halt(clock, fetch, dblog):
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = overheat("005160", temp_stop="Y")
    clock.set(9, 0, 30)
    await _sell(sched)
    assert sched.order_engine.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("buy_date,expected", [(DAY, "1"), (date(2026, 9, 25), "0")])
async def test_d8_bought_today_field(clock, fetch, dblog, caplog, buy_date, expected):
    """D8 — 당일 산 종목을 파는 경우(첫날 매수 누수)를 `bought_today=1` 로 드러낸다."""
    sched, _ = _sched_with("005160", buy_date=buy_date)
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 0, 30)
    await _sell(sched)
    fire = lines(caplog, "[status_exit_fire]", min_level=logging.WARNING)
    assert fire and field(fire[0], "bought_today") == expected


@pytest.mark.asyncio
async def test_d9_execute_sell_exception_is_absorbed(clock, fetch, dblog, caplog):
    """D9 — 한 종목의 `execute_sell` 예외가 패스를 죽이지 않는다."""
    s = holder("bull_flag_breakout")
    hold(s, "005160")
    hold(s, "294140")
    oe = FakeOrderEngine()
    oe.raise_for["005160"] = RuntimeError("boom")
    sched = make_sched(s, order_engine=oe)
    fetch.table["005160"] = LIVE["005160"]
    fetch.table["294140"] = LIVE["294140"]
    clock.set(10, 0, 30)
    await _sell(sched)  # 예외 없이 반환
    assert sorted(t for t, _ in oe.fired()) == ["005160", "294140"]
    assert len(records(caplog, "[status_exit_fire_error]", min_level=logging.WARNING)) == 1


@pytest.mark.asyncio
async def test_d10_fire_marker_is_logged_before_await_and_cancel_propagates(clock, fetch, dblog, caplog):
    """D10 — `[status_exit_fire]` 는 `execute_sell` await **전에** 남는다(M33).

    `execute_sell` 이 첫 줄에서 멈춘 동안 이미 마커가 있어야 한다. 그리고 그 대기 중
    취소는 삼키지 않는다(`CancelledError` re-raise — `stop()` 이 좀비를 남기면 안 된다).
    """
    oe = FakeOrderEngine()
    oe.hang = True
    s = holder("bull_flag_breakout")
    hold(s, "005160")
    sched = make_sched(s, order_engine=oe)
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 0, 30)
    task = asyncio.create_task(_sell(sched))
    await asyncio.wait_for(oe.entered.wait(), timeout=2.0)
    assert records(caplog, "[status_exit_fire]", min_level=logging.WARNING), (
        "execute_sell await 중인데 발사 마커가 없다 — await 뒤에 남기면 hang·취소 시 사라진다"
    )
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_d11_one_fetch_per_ticker_judged_per_strategy(clock, fetch, dblog):
    """종목별 조회는 1회, 판정은 (전략, 종목)마다."""
    a = holder("bull_flag_breakout")
    b = holder("momentum")
    hold(a, "005160")
    hold(b, "005160")
    sched = make_sched(a, b)
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 0, 30)
    await _sell(sched)
    assert fetch.count("005160") == 1
    assert sorted(sid for _, sid in sched.order_engine.fired()) == ["bull_flag_breakout", "momentum"]


@pytest.mark.asyncio
async def test_d12_positive_control_managed_fires(clock, fetch, dblog):
    """F5 양성 대조군 — 부정 단언만 있으면 본체가 사라져도 초록이다."""
    sched, _ = _sched_with("294140")
    fetch.table["294140"] = LIVE["294140"]
    clock.set(13, 0, 30)
    await _sell(sched)
    assert sched.order_engine.fired() == [("294140", "bull_flag_breakout")]


@pytest.mark.asyncio
async def test_d13_iscd_conflict_explicit_n_never_fires(clock, fetch, dblog, caplog):
    """K3' — 명시 `N` + iscd 51 은 팔지 않는다(자문의 단순 OR 이면 시장가 오매도)."""
    sched, _ = _sched_with("123450")
    fetch.table["123450"] = fhkst("123450", iscd="51", mang="N", short_over="N")
    clock.set(10, 0, 30)
    await _sell(sched)
    clock.set(10, 5, 30)
    await _sell(sched)
    assert sched.order_engine.calls == []
    assert len(lines(caplog, "[status_exit_iscd_conflict]")) == 1, "플래그↔iscd 충돌은 1회/일 남긴다(명세 §2)"


# ===========================================================================
# E. 청산 킬스위치
# ===========================================================================
@pytest.mark.asyncio
async def test_e1_off_reads_nothing(clock, fetch, dblog, db_modes):
    db_modes(sell="off")
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 0, 30)
    await _sell(sched)
    assert fetch.calls == [], "off = 보유 조회 0"
    assert sched.order_engine.calls == []


@pytest.mark.asyncio
async def test_e2_observe_logs_would_fire_without_selling(clock, fetch, dblog, caplog, db_modes):
    db_modes(sell="observe")
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 0, 30)
    await _sell(sched)
    clock.set(10, 5, 30)
    await _sell(sched)
    assert sched.order_engine.calls == []
    assert len(records(caplog, "[status_exit_would_fire]", min_level=logging.WARNING)) == 1
    await drain_writes()   # 🔁 cycle369 R3 F3 — 영속은 루트 핸들러 한 줄(위 WARNING 로거 줄)
    assert dblog.lines("[status_exit_would_fire]") == [], "would_fire 를 write_log 로 한 번 더 썼다 — system_logs 두 줄"


@pytest.mark.asyncio
async def test_e3_unknown_value_becomes_observe(db_modes, caplog):
    db_modes(sell="maybe", buy=None)
    await leaf().refresh_modes()
    assert leaf().current_modes()["sell"] == "observe"
    assert records(caplog, "[status_exit_mode_invalid]", min_level=logging.WARNING)


@pytest.mark.asyncio
async def test_e4_db_error_keeps_last_value(db_modes):
    db_modes(sell="off", buy="observe")
    await leaf().refresh_modes()
    assert leaf().current_modes() == {"sell": "off", "buy": "observe"}
    db_modes(sell_exc=RuntimeError("db down"), buy_exc=RuntimeError("db down"))
    await leaf().refresh_modes()
    assert leaf().current_modes() == {"sell": "off", "buy": "observe"}, "DB 실패로 기본값에 되돌렸다"


@pytest.mark.asyncio
async def test_e4b_db_error_on_first_read_is_enforce(db_modes):
    db_modes(sell_exc=RuntimeError("db down"), buy_exc=RuntimeError("db down"))
    await leaf().refresh_modes()
    assert leaf().current_modes() == {"sell": "enforce", "buy": "enforce"}


@pytest.mark.asyncio
async def test_e5_missing_key_is_enforce(db_modes):
    """E5 — 키 없음 = enforce (사용자 결정 「시장가로 청산」·「지정 첫날 매수를 막는거지」)."""
    db_modes(sell="off", buy="off")
    await leaf().refresh_modes()
    db_modes(sell=None, buy=None)
    await leaf().refresh_modes()
    assert leaf().current_modes() == {"sell": "enforce", "buy": "enforce"}


def test_e9_reset_state_restores_enforce():
    leaf().apply_mode("sell", "off")
    leaf().apply_mode("buy", "observe")
    leaf().reset_state_for_test()
    assert leaf().current_modes() == {"sell": "enforce", "buy": "enforce"}


@pytest.mark.asyncio
async def test_e10_sell_pass_rereads_mode_each_pass(clock, fetch, dblog, db_modes):
    """모든 패스 시작 시 모드를 새로 읽는다 — SQL UPDATE 도 다음 패스에 반영(명세 §5)."""
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    db_modes(sell="off", buy=None)
    clock.set(10, 0, 30)
    await _sell(sched)
    assert sched.order_engine.calls == [], "패스 시작 시 DB 모드(off)를 읽지 않았다"
    db_modes(sell=None, buy=None)
    clock.set(10, 5, 30)
    await _sell(sched)
    assert len(sched.order_engine.calls) == 1


@pytest.mark.asyncio
async def test_e11_no_subscription_side_effects(clock, fetch, dblog, monkeypatch):
    """K7 — 청산 패스는 구독을 건드리지 않는다(보유 종목 시세를 끊으면 손절이 눈을 감는다)."""
    from src.engine import scanner

    unsub = AsyncMock()
    monkeypatch.setattr(scanner, "unsubscribe_ticker", unsub, raising=False)
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 0, 30)
    await _sell(sched)
    assert unsub.await_count == 0
