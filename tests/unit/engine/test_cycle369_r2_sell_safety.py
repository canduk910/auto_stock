"""cycle369 round 2 Red — 보유 청산(sell side) 안전 보강. Q2 · Q3 · Q4 · Q5 · Q6(armed) · Q11.

| 절 | main-session 결정 | 무엇을 막나 |
|---|---|---|
| Q2 | 청산은 **전용 플래그가 Y 일 때만** 쏜다(`mang_issu_cls_code=="Y"` 또는 `short_over_yn=="Y"`). 종목상태 51/59 **폴백만** 맞으면 arm + `[status_exit_fallback_only]` WARNING 1회/(종목,일), **발사 0** | cycle203 이 51 을 정상 ETF·스팩·우선주에서 봤다(`scanner.py:3591-3593`). 매도는 틀리면 비싸다. 매수 차단은 폴백을 유지한다(막는 쪽이 안전 방향 — `test_cycle369_status_buy_block.py` J7 그대로) |
| Q3 | 발사 직전 `_now_kst()` 로 창 재확인 · `system_logs` 쓰기는 발사 경로 밖(fire-and-forget, logger 줄은 동기 그대로) · `execute_sell` 을 `asyncio.shield` 로 감싼다 | 느린 DB 가 시장가 매도 시각을 15:28 밖으로 민다 · DB 가 매도를 막는다 · `stop()` 이 주문 제출 중간을 자른다 |
| Q4 | task_loop 시작 때 오늘(KST) `[status_exit_fire]` 영속 행으로 종목별 발사 횟수를 채운다(읽기 전용) | 재시작하면 하루 3회 상한·giveup 이 0 부터 다시 센다 |
| Q5 | `trading_calendar.is_open_day(오늘)` 이 **False** 면 청산·P0·P1·INC 를 돌지 않는다. None(모름)은 돈다 | 주말·휴장일 수동 기동이 금요일 값으로 시장가 매도를 KIS 에 보낸다 |
| Q6 | armed 는 그날 것만 보이고, 더 이상 보유하지 않는 종목은 armed 에서 빠진다 | GET `today.armed` 에 지난 날·판 종목이 남아 사고 중 오판 |
| Q11 | round-1 생존 돌연변이 M33b · M22c · Y16 을 죽이는 회귀 | — |
| 🔁 R3 F2 | 발사 직전 `_modes["sell"]` 재확인(창 재확인 옆·`_fires` 증가 앞) — enforce 아니면 안 쏜다, observe 면 would_fire | 패스 도중 들어온 `PUT off` 가 그 패스의 남은 종목 시장가 매도를 못 멈춘다 |
| 🔁 R3 F3 | 발사·giveup·would_fire 의 `_spawn_write` 제거 — 영속은 루트 `_DbLogHandler` 한 줄. 시드는 메시지 **어디든** `[status_exit_fire]` 를 찾는다 | 사건당 `system_logs` 두 줄(cycle72 G-6) · 시드가 핸들러 줄을 버린다 |

## Q4 seam (새 계약)

``status_exit_watch._load_fire_counts(day: date) -> dict[str, int]`` — 코루틴. 그날(KST)
영속된 `[status_exit_fire]` 로 **종목별 발사 횟수**를 돌려준다. 실 Postgres 동작(두 줄 모양·
날짜 경계·다른 마커 배제)은 `tests/integration/test_cycle369_r2_fire_seed_pg.py` 가 잰다.
여기서는 그 seam 을 바꿔 **task_loop 가 시작할 때 1회 읽고, 메모리 카운터와 max 로 합친다**를 잰다.

## 시계

leaf `_now_kst` seam(`clock`) · 루프 대기 `_sleep`/`sched._wait_until` 을 이 Clock 으로 전진.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

import pytest

from tests.unit.engine._cycle369_support import (
    DAY,
    LIVE,
    NEXT_DAY,
    FakeOrderEngine,
    cand,
    clock,  # noqa: F401 — pytest 픽스처
    db_modes,  # noqa: F401
    dblog,  # noqa: F401
    drain_writes,
    fetch,  # noqa: F401
    fhkst,
    field,
    hold,
    holder,
    kst,
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

SATURDAY = date(2026, 10, 3)


@pytest.fixture(autouse=True)
def _info(caplog, db_modes):
    open_info(caplog)


def _sched_with(ticker="005160", *, sid="bull_flag_breakout", qty=3, order_engine=None):
    s = holder(sid)
    hold(s, ticker, qty=qty)
    return make_sched(s, order_engine=order_engine), s


async def _sell(sched):
    return await leaf().run_sell_pass(sched)


def _fire_lines(caplog):
    return lines(caplog, "[status_exit_fire]", min_level=logging.WARNING)


# ===========================================================================
# Q2 — 폴백만 맞으면 쏘지 않는다
# ===========================================================================
_FALLBACK_ONLY = [
    pytest.param(dict(iscd="51", mang=None, short_over="N"), id="iscd51_mang_none"),
    pytest.param(dict(iscd="59", mang="N", short_over=None), id="iscd59_short_over_none"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("kw", _FALLBACK_ONLY)
async def test_q2_fallback_only_arms_but_never_fires(clock, fetch, dblog, caplog, kw):
    """전용 플래그가 비고 종목상태 51/59 만 맞음 → 발사 0 · armed · `[status_exit_fallback_only]` 1회/일."""
    sched, _ = _sched_with("123450")
    fetch.table["123450"] = fhkst("123450", **kw)
    clock.set(10, 0, 30)
    await _sell(sched)
    clock.set(10, 5, 30)
    await _sell(sched)
    assert sched.order_engine.calls == [], "폴백(51/59) 만으로 시장가 매도를 냈다 — 전용 플래그 Y 가 발사 조건"
    assert _fire_lines(caplog) == []
    fb = records(caplog, "[status_exit_fallback_only]", min_level=logging.WARNING)
    assert len(fb) == 1, f"폴백 전용 경고는 (종목, 일) 1회: {len(fb)}"
    assert "123450" in fb[0].getMessage()
    armed = [a for a in leaf().snapshot()["armed"] if a.get("ticker") == "123450"]
    assert armed, "폴백 전용도 arm 은 한다(운영자가 보고 판단한다)"


@pytest.mark.asyncio
async def test_q2_fallback_only_warning_once_per_ticker_across_strategies(clock, fetch, dblog, caplog):
    """두 전략이 같은 종목을 보유해도 경고는 종목당 1회/일."""
    a = holder("bull_flag_breakout")
    b = holder("momentum")
    hold(a, "123450")
    hold(b, "123450")
    sched = make_sched(a, b)
    fetch.table["123450"] = fhkst("123450", iscd="51", mang=None, short_over="N")
    clock.set(10, 0, 30)
    await _sell(sched)
    assert sched.order_engine.calls == []
    assert len(records(caplog, "[status_exit_fallback_only]", min_level=logging.WARNING)) == 1


@pytest.mark.asyncio
async def test_q2_fallback_only_warns_again_next_day(clock, fetch, dblog, caplog):
    sched, _ = _sched_with("123450")
    fetch.table["123450"] = fhkst("123450", iscd="59", mang="N", short_over=None)
    clock.set(10, 0, 30)
    await _sell(sched)
    clock.set(10, 0, 30, day=NEXT_DAY)
    await _sell(sched)
    assert sched.order_engine.calls == []
    assert len(records(caplog, "[status_exit_fallback_only]", min_level=logging.WARNING)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kw", [
    pytest.param(dict(iscd="51", mang="Y", short_over="N"), id="mang_Y"),
    pytest.param(dict(iscd="59", mang="N", short_over="Y"), id="short_over_Y"),
    pytest.param(dict(iscd="55", mang="Y", short_over="N"), id="mang_Y_iscd_hidden"),
    pytest.param(dict(iscd="51", mang=None, short_over="Y"), id="mang_none_but_short_over_Y"),
])
async def test_q2_dedicated_flag_y_still_fires(clock, fetch, dblog, caplog, kw):
    """양성 대조 — 전용 플래그 하나라도 Y 면 쏜다(iscd 가 58·00·55 로 가려진 관리종목 포함)."""
    sched, _ = _sched_with("123450")
    fetch.table["123450"] = fhkst("123450", **kw)
    clock.set(10, 0, 30)
    await _sell(sched)
    assert sched.order_engine.fired() == [("123450", "bull_flag_breakout")]
    assert records(caplog, "[status_exit_fallback_only]", min_level=logging.WARNING) == []


# ===========================================================================
# Q3 — 창 재확인 · DB 쓰기는 발사 경로 밖 · shield
# ===========================================================================
@pytest.mark.asyncio
async def test_q3_window_rechecked_right_before_each_fire(clock, fetch, dblog, caplog):
    """15:27:50 에 시작한 패스가 조회 지연으로 15:28 을 넘기면, 넘긴 뒤의 종목은 쏘지 않는다.

    창은 패스 시작 1회가 아니라 **발사 직전** `_now_kst()` 로 다시 본다. 쏘지 않은 종목은
    발사 마커도 없다(마커 수 = 주문 수).
    """
    s = holder("bull_flag_breakout")
    hold(s, "005160")
    hold(s, "294140")
    sched = make_sched(s)
    fetch.table["005160"] = LIVE["005160"]
    fetch.table["294140"] = LIVE["294140"]
    fetch.on_call = lambda _t: clock.advance(6.0)      # 조회마다 6초(시세 풀 지연)
    clock.set(15, 27, 50)
    await _sell(sched)
    fired = [t for t, _sid in sched.order_engine.fired()]
    assert fired == ["005160"], (
        f"15:28:02 에 시장가 매도를 냈다(창 밖): {fired} — 창은 발사 직전에 다시 본다"
    )
    assert len(_fire_lines(caplog)) == len(fired), "발사 마커와 실제 주문 수가 다르다"


@pytest.mark.asyncio
async def test_q3_window_recheck_does_not_consume_daily_cap(clock, fetch, dblog, caplog):
    """창 밖이라 안 쏜 시도는 하루 3회 상한을 쓰지 않는다 — 그 종목의 같은 날 첫 실제 발사가 attempt=1.

    (재현을 위해 시계를 같은 날 창 안으로 되감는다. 재확인을 카운터 증가 **뒤**에 두면 attempt=2 가 된다.)
    """
    s = holder("bull_flag_breakout")
    hold(s, "005160")
    hold(s, "294140")
    sched = make_sched(s)
    fetch.table["005160"] = LIVE["005160"]
    fetch.table["294140"] = LIVE["294140"]
    fetch.on_call = lambda _t: clock.advance(6.0)
    clock.set(15, 27, 50)
    await _sell(sched)
    fetch.on_call = None
    # 같은 날 창 안으로 되감은 재시도(시계 조작 = 재현용) — 294140 의 첫 발사여야 한다
    clock.set(15, 0, 30)
    await _sell(sched)
    attempts = {field(m, "ticker"): field(m, "attempt") for m in _fire_lines(caplog)}
    assert attempts.get("294140") == "1", f"창 밖 미발사가 발사 횟수를 먹었다: {attempts}"


def _hanging_db(monkeypatch):
    """`write_log`·`safe_write_log` 가 영원히 걸린다(RDS 페일오버 모양). 끝에 풀어 준다."""
    from src.db import system_logs

    gate = asyncio.Event()
    written: list[tuple[str, str]] = []

    async def _hang(level, message, *a, **k):
        await gate.wait()
        written.append((str(level), str(message)))

    monkeypatch.setattr(system_logs, "write_log", _hang)
    monkeypatch.setattr(system_logs, "safe_write_log", _hang)
    return gate, written


async def _drain(gate):
    gate.set()
    for _ in range(20):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_q3_fire_is_not_blocked_by_system_logs_write(clock, fetch, monkeypatch, caplog):
    """`system_logs` 쓰기가 걸려 있어도 시장가 매도는 나간다.

    logger WARNING 은 동기 그대로 `execute_sell` 전에 남는다(D10 계약 유지).

    🔁 cycle369 R3 F3 — 발사 기록의 영속은 루트 `_DbLogHandler` 가 그 logger 줄을 큐로 옮겨 적는
    **한 줄**뿐이다(발사 경로 밖 — 큐 적재는 동기·non-blocking). leaf 가 `write_log` 로 한 번 더
    쓰면 같은 발사가 `system_logs` 에 두 줄이 된다(cycle72 G-6 이중 INSERT 금지). 그래서 걸린
    `write_log` 에 발사 행이 **하나도** 도착하지 않아야 한다.
    """
    gate, written = _hanging_db(monkeypatch)
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 0, 30)
    try:
        await asyncio.wait_for(_sell(sched), timeout=2.0)
    except asyncio.TimeoutError:
        await _drain(gate)
        pytest.fail("system_logs 쓰기가 걸리자 청산 패스가 멈췄다 — 매도 시각이 DB 지연에 묶였다")
    assert sched.order_engine.fired() == [("005160", "bull_flag_breakout")]
    assert len(_fire_lines(caplog)) == 1
    await _drain(gate)
    assert not any("[status_exit_fire]" in m for _l, m in written), (
        "leaf 가 발사 기록을 write_log 로 직접 썼다 — 루트 `_DbLogHandler` 줄과 합쳐 system_logs 에 "
        "같은 발사가 두 줄(cycle72 G-6)"
    )


@pytest.mark.asyncio
async def test_q3_giveup_write_does_not_delay_other_tickers_fire(clock, fetch, dblog, monkeypatch, caplog):
    """한 종목의 giveup CRITICAL 영속이 걸려도 뒤 종목의 매도는 나간다(같은 패스 = 같은 발사 경로)."""
    sched, s = _sched_with("000545")     # 정렬상 먼저 처리되는 종목
    hold(s, "005160")
    fetch.table["000545"] = LIVE["000545"]
    fetch.table["005160"] = fhkst("005160", iscd="55", mang="N", short_over="N")   # 아직 정상
    # 000545 를 오늘 3번 쏜다 → 다음 패스에서 giveup
    for hm in ((9, 0, 30), (9, 5, 30), (9, 10, 30)):
        clock.set(*hm)
        await _sell(sched)
    assert [t for t, _ in sched.order_engine.fired()] == ["000545"] * 3

    gate, _written = _hanging_db(monkeypatch)
    fetch.table["005160"] = LIVE["005160"]
    clock.set(9, 15, 30)
    try:
        await asyncio.wait_for(_sell(sched), timeout=2.0)
    except asyncio.TimeoutError:
        await _drain(gate)
        pytest.fail("giveup 영속이 걸리자 뒤 종목 매도가 멈췄다")
    assert sched.order_engine.fired()[-1] == ("005160", "bull_flag_breakout")
    assert len(records(caplog, "[status_exit_giveup]", min_level=logging.CRITICAL)) == 1
    await _drain(gate)


class _ShieldProbeEngine(FakeOrderEngine):
    """`execute_sell` 이 게이트에서 멈춘다. 취소가 **주문 코루틴 안까지** 닿았는지 기록한다."""

    def __init__(self) -> None:
        super().__init__()
        self.release = asyncio.Event()
        self.completed = False
        self.inner_cancelled = False

    async def execute_sell(self, ticker, signal, strategy_id, *args, **kwargs):
        self.calls.append((ticker, signal, strategy_id, args, dict(kwargs)))
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.inner_cancelled = True
            raise
        self.completed = True


@pytest.mark.asyncio
async def test_q3_stop_cannot_cut_order_mid_submission(clock, fetch, dblog):
    """`stop()` 이 패스 task 를 취소해도 이미 제출 중인 `execute_sell` 은 끝까지 간다(asyncio.shield).

    패스 task 자체는 `CancelledError` 로 끝난다(삼키지 않는다 — D10 계약 유지).
    shield 가 없으면 취소가 `place_order` 한가운데로 들어가 매핑·PENDING 행 없이 주문이 나갈 수 있다.
    """
    oe = _ShieldProbeEngine()
    sched, _ = _sched_with("005160", order_engine=oe)
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 0, 30)
    task = asyncio.create_task(_sell(sched))
    await asyncio.wait_for(oe.entered.wait(), timeout=2.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert oe.inner_cancelled is False, "stop() 의 취소가 주문 제출 코루틴 안까지 들어갔다 — shield 부재"
    oe.release.set()
    for _ in range(20):
        await asyncio.sleep(0)
    assert oe.completed is True, "취소 뒤 주문 제출이 끝나지 않았다"


# ===========================================================================
# 🔁 cycle369 R3 F2 — 킬스위치가 **진행 중인** 청산 패스에도 닿는다
#
# 패스는 시작 때 모드를 1회 읽는다. 운영자의 `PUT sell_mode=off` 가 그 패스가 앞 종목의
# `_read` 나 `execute_sell` 을 기다리는 동안 들어오면, 옛 스냅샷으로 뒤 종목 시장가 매도가
# 계속 나갔다(리뷰 탐침: `mode after PUT: off | fired in same pass: ['111111', '222222']`).
# 결정 F2 = 발사 직전(Q3 창 재확인 옆, `_fires` 증가 **앞**) `_modes["sell"]` 를 다시 읽는다 —
# enforce 가 아니면 쏘지 않고, observe 면 would_fire 로 간다.
# ===========================================================================
class _FlipOnFirstOrder(FakeOrderEngine):
    """첫 시장가 매도가 나가는 동안 운영자 PUT 이 들어온다(라우트 = 같은 요청에서 `apply_mode`)."""

    def __init__(self, to_mode: str) -> None:
        super().__init__()
        self.to_mode = to_mode

    async def execute_sell(self, ticker, signal, strategy_id, *args, **kwargs):
        await super().execute_sell(ticker, signal, strategy_id, *args, **kwargs)
        if len(self.calls) == 1:
            leaf().apply_mode("sell", self.to_mode)


def _two_flagged(order_engine=None):
    s = holder("bull_flag_breakout")
    hold(s, "111111")
    hold(s, "222222")
    return make_sched(s, order_engine=order_engine)


@pytest.mark.asyncio
@pytest.mark.parametrize("flip_at", ["during_first_order", "during_second_read"])
async def test_f2_put_off_mid_pass_stops_remaining_fires(clock, fetch, dblog, caplog, flip_at):
    """패스 도중 off → 뒤 종목은 쏘지 않는다 · 발사 마커도 없다 · 하루 3회 상한도 쓰지 않는다."""
    oe = _FlipOnFirstOrder("off") if flip_at == "during_first_order" else FakeOrderEngine()
    sched = _two_flagged(oe)
    fetch.table["111111"] = overheat("111111")
    fetch.table["222222"] = overheat("222222")
    if flip_at == "during_second_read":
        def _flip(t):
            if t == "222222":
                leaf().apply_mode("sell", "off")
        fetch.on_call = _flip
    clock.set(10, 0, 30)
    await _sell(sched)
    fetch.on_call = None
    assert [t for t, _sid in oe.fired()] == ["111111"], (
        f"운영자가 off 한 뒤에도 같은 패스에서 시장가 매도가 나갔다: {oe.fired()}"
    )
    assert [field(m, "ticker") for m in _fire_lines(caplog)] == ["111111"], "마커 수 = 주문 수"

    # 다시 켜진 다음 패스(모드 = DB 키 없음 → enforce) — 안 쏜 종목의 첫 발사는 attempt=1
    clock.set(10, 5, 30)
    await _sell(sched)
    attempts = {field(m, "ticker"): field(m, "attempt") for m in _fire_lines(caplog)}
    assert attempts.get("222222") == "1", f"off 로 안 쏜 시도가 하루 3회 상한을 먹었다: {attempts}"


@pytest.mark.asyncio
async def test_f2_put_observe_mid_pass_routes_to_would_fire(clock, fetch, dblog, caplog):
    """패스 도중 observe → 뒤 종목은 주문 대신 `[status_exit_would_fire]`."""
    oe = _FlipOnFirstOrder("observe")
    sched = _two_flagged(oe)
    fetch.table["111111"] = overheat("111111")
    fetch.table["222222"] = overheat("222222")
    clock.set(10, 0, 30)
    await _sell(sched)
    assert [t for t, _sid in oe.fired()] == ["111111"], oe.fired()
    wf = records(caplog, "[status_exit_would_fire]", min_level=logging.WARNING)
    assert [field(r.getMessage(), "ticker") for r in wf] == ["222222"], (
        "observe 로 바뀐 뒤의 해당 종목은 would_fire 로 남아야 한다"
    )


@pytest.mark.asyncio
async def test_f2_mode_unchanged_control_fires_both(clock, fetch, dblog):
    """대조 — 모드가 그대로면 같은 패스에서 두 종목 다 쏜다(재확인이 공허하지 않다)."""
    sched = _two_flagged()
    fetch.table["111111"] = overheat("111111")
    fetch.table["222222"] = overheat("222222")
    clock.set(10, 0, 30)
    await _sell(sched)
    assert [t for t, _sid in sched.order_engine.fired()] == ["111111", "222222"]


# ===========================================================================
# 🔁 cycle369 R3 F3 — 한 사건 = 영속 한 줄
#
# 루트 `_DbLogHandler`(src/main.py)가 `src.*` 로거의 INFO+ 를 큐로 옮겨 `system_logs` 에 적는다
# (`"[src.engine.status_exit_watch] [status_exit_fire] …"`). R2 는 그 옆에서 `_spawn_write` 로
# **한 번 더** 썼다 — 발사·giveup·would_fire 마다 두 줄(cycle72 G-6 이 금지한 이중 INSERT, 가드는
# 래퍼·변수 메시지 때문에 못 봤다). 결정 F3 = 그 세 자리의 `_spawn_write` 를 걷는다. 발사 경로에서
# DB 를 기다리지 않는다는 Q3 목표는 큐 적재(동기·non-blocking)로 그대로 지켜진다.
# ===========================================================================
@pytest.fixture
def handler_rows(monkeypatch):
    """운영 배선 그대로 — 루트 로거에 붙은 `src.main._db_handler` 가 큐에 적재하는 행을 모은다.

    `importlib` 로 지연 참조한다 — 정적 import 면 `src.main` 의 전이 의존(라우트 전체)이 이 파일을
    거의 모든 모듈의 영향 테스트로 만든다. 대신 `manual_overrides.yaml` 의 `src/main.py` 항목이 잇는다.
    """
    import importlib
    import queue

    main_mod = importlib.import_module("src.main")

    q: queue.Queue = queue.Queue()
    monkeypatch.setattr(main_mod, "_LOG_QUEUE", q)
    monkeypatch.setattr(main_mod._db_handler, "_dedupe_cache", {})
    root = logging.getLogger()
    added = main_mod._db_handler not in root.handlers
    if added:
        root.addHandler(main_mod._db_handler)

    def _rows() -> list[tuple[str, str]]:
        out = []
        while not q.empty():
            out.append(q.get_nowait())
        return out

    yield _rows
    if added:
        root.removeHandler(main_mod._db_handler)


async def _run_event(kind, sched, clock, db_modes):
    if kind == "would_fire":
        db_modes(sell="observe", buy=None)
        clock.set(10, 0, 30)
        await _sell(sched)
        return {"[status_exit_would_fire]": 1}
    passes = 1 if kind == "fire" else 4          # giveup = 3번 쏜 뒤 네 번째 패스
    for k in range(passes):
        clock.set(9, 0, 30)
        clock.advance(300 * k)
        await _sell(sched)
    if kind == "fire":
        return {"[status_exit_fire]": 1}
    return {"[status_exit_fire]": 3, "[status_exit_giveup]": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["fire", "giveup", "would_fire"])
async def test_f3_each_event_persists_exactly_one_row(clock, fetch, dblog, db_modes, handler_rows, kind):
    """발사·giveup·would_fire — `system_logs` 로 가는 행이 사건당 정확히 1 (핸들러 줄 하나)."""
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    expected = await _run_event(kind, sched, clock, db_modes)
    await drain_writes()        # 혹시 남은 fire-and-forget 쓰기가 있으면 여기서 도착한다
    queued = handler_rows()
    for marker, n in expected.items():
        via_handler = [m for _lvl, m in queued if marker in m]
        direct = [m for _lvl, m in dblog.rows if marker in m]
        assert len(via_handler) == n, (
            f"{marker}: 루트 핸들러 행 {len(via_handler)} (기대 {n}) — logger 줄이 운영 핸들러에 안 닿는다"
        )
        assert all(m.startswith("[src.engine.status_exit_watch] ") for m in via_handler), via_handler
        assert direct == [], (
            f"{marker}: leaf 가 write_log 로 한 번 더 썼다 {len(direct)}줄 — 사건당 system_logs 두 줄"
            "(cycle72 G-6 이중 INSERT 금지)"
        )


@pytest.mark.asyncio
async def test_f3_seed_parses_handler_form_rows(monkeypatch):
    """재시작 시드는 핸들러 모양 행(`[src.engine.status_exit_watch] [status_exit_fire] …`)을 센다.

    F3 뒤에는 그 모양만 남는다 — `startswith("[status_exit_fire]")` 로 거르면 오늘 발사가 0 으로 읽혀
    재시작이 하루 3회 상한을 0 부터 다시 센다. 종목별 `attempt=` 최댓값 = 발사 횟수.
    """
    from src.db import system_logs

    def _h(msg: str) -> dict:
        return {"message": f"[src.engine.status_exit_watch] {msg}"}

    rows = [
        _h("[status_exit_fire] ticker=005160 strategy=bull_flag_breakout reason=overheat iscd=59 mang=N "
           "short_over=Y qty=3 mode=enforce attempt=1 bought_today=0"),
        _h("[status_exit_fire] ticker=005160 strategy=bull_flag_breakout reason=overheat iscd=59 mang=N "
           "short_over=Y qty=3 mode=enforce attempt=2 bought_today=0"),
        _h("[status_exit_fire] ticker=294140 strategy=kojiro reason=managed iscd=51 mang=Y "
           "short_over=N qty=1 mode=enforce attempt=1 bought_today=0"),
        # 발사가 아닌 마커 — 세면 안 된다
        _h("[status_exit_fire_error] ticker=005160 strategy=bull_flag_breakout err=boom"),
        _h("[status_exit_would_fire] ticker=111111 strategy=bull_flag_breakout reason=overheat"),
        _h("[status_exit_giveup] ticker=005160 strategy=bull_flag_breakout fires=3"),
    ]
    seen: dict = {}

    async def _search(q, **kw):
        seen["q"] = q
        seen.update(kw)
        return {"logs": [dict(r) for r in rows], "total": len(rows), "has_more": False}

    monkeypatch.setattr(system_logs, "search_logs", _search)
    got = await leaf()._load_fire_counts(DAY)
    assert {k: int(v) for k, v in dict(got).items() if int(v)} == {"005160": 2, "294140": 1}, got
    assert "status_exit_fire" in str(seen.get("q", "")), seen


# ===========================================================================
# Q4 — 재시작에도 하루 3회 상한이 남는다
# ===========================================================================
class _RealLoop:
    """실제 `task_loop` + 실제 패스. 대기(`_sleep`·`sched._wait_until`)만 가짜 시계로 전진한다."""

    def __init__(self, clock, sched, monkeypatch, *, horizon: datetime, seed=None):
        lf = leaf()
        self.seed_calls: list = []

        async def _seed(day, *a, **k):
            self.seed_calls.append(day)
            if isinstance(seed, BaseException):
                raise seed
            return dict(seed or {})

        monkeypatch.setattr(lf, "_load_fire_counts", _seed, raising=False)

        async def _sleep(secs, *a, **k):
            clock.advance(max(float(secs), 0.001))
            if clock.now >= horizon:
                sched._running = False

        async def _wait_until(target, *a, **k):
            tgt = clock.now.replace(hour=target.hour, minute=target.minute,
                                    second=target.second, microsecond=0)
            clock.now = tgt if tgt > clock.now else clock.now + timedelta(milliseconds=1)
            if clock.now >= horizon:
                sched._running = False

        monkeypatch.setattr(lf, "_sleep", _sleep, raising=False)
        sched._wait_until = _wait_until
        self.sched = sched

    async def run(self, timeout=20.0):
        await asyncio.wait_for(leaf().task_loop(self.sched), timeout=timeout)


@pytest.mark.asyncio
async def test_q4_restart_after_three_fires_does_not_fire_again(clock, fetch, dblog, caplog, monkeypatch):
    """오늘 이미 3번 쏜 종목 — 10:31 재시작 뒤 첫 청산 패스는 쏘지 않고 giveup 한다."""
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 31, 0)
    rig = _RealLoop(clock, sched, monkeypatch, horizon=kst(10, 31, 20), seed={"005160": 3})
    await rig.run()
    assert sched.order_engine.calls == [], "재시작이 하루 3회 상한을 0 부터 다시 셌다"
    assert len(records(caplog, "[status_exit_giveup]", min_level=logging.CRITICAL)) == 1
    assert rig.seed_calls == [DAY], f"task_loop 시작 때 오늘 날짜로 1회 읽어야 한다: {rig.seed_calls}"


@pytest.mark.asyncio
async def test_q4_restart_continues_attempt_numbering(clock, fetch, dblog, caplog, monkeypatch):
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 31, 0)
    rig = _RealLoop(clock, sched, monkeypatch, horizon=kst(10, 31, 20), seed={"005160": 1})
    await rig.run()
    fire = _fire_lines(caplog)
    assert len(fire) == 1 and field(fire[0], "attempt") == "2", fire


@pytest.mark.asyncio
@pytest.mark.parametrize("db_count", [1, 2], ids=["db_lags", "db_equal"])
async def test_q4_seed_merges_with_memory_by_max(clock, fetch, dblog, caplog, monkeypatch, db_count):
    """같은 프로세스 재시작(`/api/trading/restart` = stop→start)은 메모리 카운터가 남는다.

    메모리 2회 + DB 가 1(쓰기 지연) 또는 2 → 다음 발사는 **attempt=3**. 합치기는 max 다 —
    더하면(4) 한 번도 더 못 쏘고, 덮으면(1) 한 번을 더 쏜다.
    """
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    for hm in ((10, 0, 30), (10, 5, 30)):
        clock.set(*hm)
        await _sell(sched)
    assert len(sched.order_engine.calls) == 2
    clock.set(10, 31, 0)
    rig = _RealLoop(clock, sched, monkeypatch, horizon=kst(10, 31, 20), seed={"005160": db_count})
    await rig.run()
    attempts = [field(m, "attempt") for m in _fire_lines(caplog)]
    assert attempts == ["1", "2", "3"], attempts


@pytest.mark.asyncio
async def test_q4_seed_failure_is_fail_open(clock, fetch, dblog, caplog, monkeypatch):
    """영속 행 조회가 실패해도 루프는 산다(현행 동작 = 메모리 카운터만) — 패스가 돈다."""
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 31, 0)
    rig = _RealLoop(clock, sched, monkeypatch, horizon=kst(10, 31, 20), seed=RuntimeError("db down"))
    await rig.run()
    fire = _fire_lines(caplog)
    assert len(fire) == 1 and field(fire[0], "attempt") == "1"


# ===========================================================================
# Q5 — 휴장일(False) 수동 기동은 아무 패스도 돌지 않는다 · 모름(None)은 돈다
# ===========================================================================
def _calendar(monkeypatch, value):
    from src.engine import trading_calendar

    async def _lookup(_d):
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(trading_calendar, "_lookup_open", _lookup)


def _day_sched():
    s = cand("bull_flag_breakout", scanned=["200001"], candidates=["200001"])
    hold(s, "005160")
    return make_sched(s)


@pytest.mark.asyncio
@pytest.mark.parametrize("start,horizon", [
    pytest.param((8, 44, 0), (8, 46, 0), id="p0"),
    pytest.param((9, 0, 0), (9, 6, 0), id="p1_inc_sell"),
])
async def test_q5_holiday_manual_start_runs_no_pass(clock, fetch, dblog, monkeypatch, start, horizon):
    """KIS 휴장일(평일) — P0·P1·INC·청산 모두 조회 0 · 발사 0."""
    _calendar(monkeypatch, False)
    sched = _day_sched()
    fetch.table["005160"] = LIVE["005160"]
    fetch.table["200001"] = LIVE["294140"]
    clock.set(*start)
    rig = _RealLoop(clock, sched, monkeypatch, horizon=kst(*horizon))
    await rig.run()
    assert fetch.calls == [], f"휴장일에 조회했다: {fetch.calls}"
    assert sched.order_engine.calls == [], "휴장일에 금요일 값으로 시장가 매도를 냈다"


@pytest.mark.asyncio
async def test_q5_weekend_manual_start_runs_no_pass(clock, fetch, dblog, monkeypatch):
    """토요일 — 조회 seam 없이도 주말은 휴장(`is_open_day` 규약)."""
    sched = _day_sched()
    fetch.table["005160"] = LIVE["005160"]
    clock.set(9, 0, 0, day=SATURDAY)
    rig = _RealLoop(clock, sched, monkeypatch, horizon=kst(9, 6, 0, day=SATURDAY))
    await rig.run()
    assert fetch.calls == []
    assert sched.order_engine.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, True, RuntimeError("calendar down")],
                         ids=["unknown", "open", "lookup_raises"])
async def test_q5_unknown_or_open_day_still_runs(clock, fetch, dblog, monkeypatch, value):
    """모름·개장·조회 예외(→ 모름)는 돈다 — 휴장일 판정 실패가 청산을 끄면 안 된다."""
    _calendar(monkeypatch, value)
    sched = _day_sched()
    fetch.table["005160"] = LIVE["005160"]
    clock.set(9, 0, 0)
    rig = _RealLoop(clock, sched, monkeypatch, horizon=kst(9, 1, 0))
    await rig.run()
    assert "200001" in fetch.calls, "P1 이 돌지 않았다"
    assert sched.order_engine.fired() == [("005160", "bull_flag_breakout")], "청산이 돌지 않았다"


@pytest.mark.asyncio
async def test_q5_is_open_day_exception_is_never_raise(clock, fetch, dblog, monkeypatch):
    """`is_open_day` 자체가 예외를 내도 leaf 는 죽지 않고 「모름」으로 돈다."""
    from src.engine import trading_calendar

    async def _boom(_d):
        raise RuntimeError("calendar broken")

    monkeypatch.setattr(trading_calendar, "is_open_day", _boom)
    sched = _day_sched()
    fetch.table["005160"] = LIVE["005160"]
    clock.set(9, 0, 0)
    rig = _RealLoop(clock, sched, monkeypatch, horizon=kst(9, 1, 0))
    await rig.run()
    assert sched.order_engine.fired() == [("005160", "bull_flag_breakout")]


# ===========================================================================
# Q6 — armed 는 그날 것 · 보유 중인 것만
# ===========================================================================
def _armed_tickers():
    return sorted({a.get("ticker") for a in leaf().snapshot().get("armed", [])})


@pytest.mark.asyncio
async def test_q6_armed_from_yesterday_is_not_shown_today(clock, fetch, dblog):
    """D 에 정지 대기로 arm 된 종목 → D+1 GET `today.armed` 에 보이지 않는다(패스 전이라도)."""
    sched, _ = _sched_with("016790")
    fetch.table["016790"] = LIVE["016790"]
    clock.set(10, 0, 30)
    await _sell(sched)
    assert _armed_tickers() == ["016790"], "전제 — D 에 arm"
    clock.set(8, 0, 0, day=NEXT_DAY)
    assert _armed_tickers() == [], "어제 armed 가 오늘로 보인다"


@pytest.mark.asyncio
async def test_q6_armed_from_yesterday_purged_by_p0(clock, fetch, dblog):
    sched, s = _sched_with("016790")
    fetch.table["016790"] = LIVE["016790"]
    clock.set(10, 0, 30)
    await _sell(sched)
    del s.state.positions["016790"]           # 밤사이 정리됨
    clock.set(8, 45, 0, day=NEXT_DAY)
    await leaf().run_pre_pass(sched)
    assert _armed_tickers() == []


@pytest.mark.asyncio
async def test_q6_sold_ticker_drops_out_of_armed(clock, fetch, dblog):
    """같은 날 — arm 된 종목을 다 팔면 다음 청산 패스에서 armed 에서 빠진다."""
    s = holder("bull_flag_breakout")
    hold(s, "016790")
    hold(s, "005930")
    sched = make_sched(s)
    fetch.table["016790"] = LIVE["016790"]
    clock.set(10, 0, 30)
    await _sell(sched)
    assert "016790" in _armed_tickers()
    del s.state.positions["016790"]            # 체결 완료
    clock.set(10, 5, 30)
    await _sell(sched)
    assert "016790" not in _armed_tickers(), "판 종목이 armed 에 남았다 — 사고 중 「매도 대기」로 오판"


# ===========================================================================
# Q11 — round-1 생존 돌연변이 봉인
# ===========================================================================
@pytest.mark.asyncio
async def test_q11_m33b_execute_sell_raising_every_pass_still_caps_at_three(clock, fetch, dblog, caplog):
    """M33b — 발사 횟수 증가를 `await execute_sell` **뒤**로 옮기면, 매번 예외일 때 상한이 사라진다.

    `execute_sell` 이 매 패스 예외 → 호출은 정확히 3회 · attempt 1,2,3 · giveup CRITICAL 1회.
    """
    oe = FakeOrderEngine()
    oe.raise_for["005160"] = RuntimeError("KIS 5xx")
    sched, _ = _sched_with("005160", order_engine=oe)
    fetch.table["005160"] = LIVE["005160"]
    for k in range(6):
        clock.set(9, 0, 30)
        clock.advance(300 * k)
        await _sell(sched)
    assert len(oe.calls) == 3, f"예외가 난 발사도 1회로 센다: {len(oe.calls)}회"
    assert [field(m, "attempt") for m in _fire_lines(caplog)] == ["1", "2", "3"]
    assert len(records(caplog, "[status_exit_fire_error]", min_level=logging.WARNING)) == 3
    assert len(records(caplog, "[status_exit_giveup]", min_level=logging.CRITICAL)) == 1


@pytest.mark.asyncio
async def test_q11_m22c_sell_off_p0_does_not_read_held(clock, fetch, dblog, db_modes):
    """M22c — 청산 off 면 P0 도 보유 종목을 읽지 않는다(후보만)."""
    db_modes(sell="off", buy=None)
    s = cand("bull_flag_breakout", candidates=["200001"])
    hold(s, "005160")
    sched = make_sched(s)
    clock.set(8, 45)
    await leaf().run_pre_pass(sched)
    assert "005160" not in fetch.calls, f"청산 off 인데 P0 가 보유 종목을 읽었다: {fetch.calls}"
    assert "200001" in fetch.calls, "양성 — 매수 차단 축은 켜져 있어 후보는 읽는다"


@pytest.mark.asyncio
async def test_q11_y16_would_fire_once_per_day_not_per_process(clock, fetch, dblog, caplog, db_modes):
    """Y16 — observe 를 며칠 켜 두면 would_fire 가 **날마다** 1회씩 남는다(상한 키에 날짜)."""
    db_modes(sell="observe", buy=None)
    sched, _ = _sched_with("005160")
    fetch.table["005160"] = LIVE["005160"]
    clock.set(10, 0, 30)
    await _sell(sched)
    clock.set(10, 5, 30)
    await _sell(sched)
    clock.set(10, 0, 30, day=NEXT_DAY)
    await _sell(sched)
    assert sched.order_engine.calls == []
    assert len(records(caplog, "[status_exit_would_fire]", min_level=logging.WARNING)) == 2


@pytest.mark.asyncio
async def test_q11_managed_fixture_positive_control(clock, fetch, dblog):
    """이 파일의 부정 단언들이 공허하지 않다는 양성 대조 — 같은 배선에서 managed 는 쏜다."""
    sched, _ = _sched_with("123450")
    fetch.table["123450"] = managed("123450")
    clock.set(11, 0, 30)
    await _sell(sched)
    assert sched.order_engine.fired() == [("123450", "bull_flag_breakout")]
