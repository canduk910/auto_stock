"""cycle393 Red — `[no_feed_held]` 는 **측정했을 때만** 말한다.

> 정본 명세: `scratchpad/c393/spec.md` §2·§3·§4·§6·§7·§9.1 (사용자 결정 7, 2026-10-02)

## 결함 (사실)

지금 판정식은 `no_feed_high = {t ∈ high_tickers : is_no_feed(t)}` 하나다
(`stale_watcher_core.py` `check_and_resubscribe_stale`). `is_no_feed` 는
`stock_master.nxt_tradable == False`(KRX 전용) **정적 집합**이라 프레임 수신 여부를
보지 않는다. 그래서 KRX 전용 종목을 하나라도 보유하면 09:00 뒤 첫 사이클에 **반드시**
뜬다 — 운영 09-28·09-29(2회)·09-30·10-01 5회. 10-01 은 대상 4종목이 마커(09:01:50)보다
먼저 정규장 체결 틱을 받았다(417200 09:00:06 · 003490 09:00:18 · 425040 09:00:22 ·
232140 09:00:29) — 거짓 경보다.

## 이 사이클이 요구하는 것

`[no_feed_held]` 는 두 다리가 **모두 측정됐을 때만** 낸다.

- **W** — WS 체결 기록 부재: `tick_volume.get_observed_acml_vol(t) is None`(REST 폴은 기록하지 않는다)
- **R** — 구독 중 체결 발생: `inquire_acml_vol(t, market="J")` 를 `NO_FEED_PROBE_INTERVAL_SECS`(600)
  간격으로 **두 번** 읽어 늘었는가 → 늘어난 뒤 `NO_FEED_CONFIRM_SECS`(60) 더 기다려도 W 가 참이면 확정

판정 창 = KRX 정규장 K3 `[개장 + NO_FEED_OPEN_GRACE_SECS(180), 종료)` = 오늘 표 09:03:00~15:20:00(끝 제외).
시각 게이트 실패는 억제하지 않고(창 안으로 본다), 증거 다리 실패는 말하지 않는다.

테스트가 갈아끼우는 유일 지점 = 모듈 비동기 seam `_probe_krx_acml_vol(ticker) -> int | None`
(conftest autouse 가 `None` 반환 스텁으로 바꾼다. 진짜 seam 은 `real_no_feed_probe` 마커).

| ID | 검사 |
|----|------|
| E1 | 10-01 재현 — WS 기록 있는 KRX 전용 보유 4종목 → 0행 · REST 0회 |
| E1b | `ticker_last_tick` 은 없고 WS 기록은 있음 → 0행 (판정이 `ticker_last_tick` 을 보지 않는다) |
| E2 | 저유동 정상 무체결(REST 값 동일) → 종일 0행 · 기준만 옮겨 감 · cap 미소비 |
| E2b | 누적거래량 일중 감소(이상값, 1000→0→1000) → 기준을 내리지 않는다 → 0행(F1 리뷰) |
| E3 | 진짜 무송출(WS 없음, REST 1000→1500) → 확인 대기 사이클 0행 → 확정 사이클 1행 |
| E3b | E3 이 「모두 fresh」 조기 반환 경로(REST 폴로 `ticker_last_tick` 신선)에서도 1행 |
| E4 | 확인 대기 중 WS 기록이 생김 → 0행 · 상태 삭제(다시 기준부터) |
| E4b | 기준 뒤 구독 공백 → 상태 삭제(다시 구독돼도 처음부터) |
| E5 | REST None / 예외 / 타임아웃 → 0행 · 예외 미전파 · cap 미소비 · 다음 사이클 재시도 |
| E5b | 기준 뒤 두 번째 읽기 실패 → 증분으로 취급하지 않는다(기준 유지, 재시도로 진짜 증분 뒤에만 확정) |
| E6 | 창 밖(08:10 · 09:01:00 · 09:02:59 · 15:20:00 · 15:25 · 16:30) REST 0 · 0행 / 09:03:00 은 포함 |
| E6b | 확인 대기가 15:19 에 서고 확인이 15:21 → 1행(확인은 창 밖에서도 같은 날 진행, REST 재조회 없음) |
| E7 | `get_market_table` 예외·행 없음 → 창 안으로 본다(16:30 에도 REST 호출) |
| E8 | 재기동 모사 10:30 — 누적이 이미 큼, 이후 값 동일 → 0행 |
| E9 | 후보 6종목 → 사이클당 REST ≤ 4(정렬 순) · 같은 종목 간격 전 재조회 0 |
| E10 | 전날 기준이 남은 채 다음 날 09:05 → 전날 기준 무효(새 기준부터) |
| E11 | 범위 — HIGH 비 no_feed · LOW no_feed · 구독 안 된 보유 → 0행 · REST 0 / 익일청산 HIGH 는 대상 |
| E12 | 배치 — 그 사이클의 HIGH 재등록 SEND·세션 상세가 모두 끝난 **뒤** 첫 REST |
| E13 | 차분 — 기준 sha `9df058d` 구현과 HIGH 재등록·LOW skip 5축 불일치 0(≥200 조합 × 3 사이클) |
| E14 | 관측기 내부 예외(seam·tick_volume·표·cap peek) → 사이클 무예외 · HIGH 재등록 완료 |
| E15 | 동시호가 조기 반환 → `is_no_feed` 0 · REST 0 · 0행 |
| E16 | 그날 cap 이 이미 쓰였으면 REST 0 (대조군: 안 쓰였으면 REST 호출) |
| E17 | 08:00:15 프리장 → 0행 · REST 0 |
| E18 | 진짜 seam — `quotation.inquire_acml_vol(ticker, market="J")` 1회 · 반환값 그대로 |
"""
from __future__ import annotations

import asyncio as _real_asyncio
import importlib.util
import logging
import random
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
_REPO_ROOT = Path(__file__).resolve().parents[3]

_HELD_PREFIX = "[no_feed_held] "
_PROBE_PREFIX = "[no_feed_held_probe] "
_OBSERVE_FAILED = "[no_feed_held_observe_failed]"

# 10-01 실측 KRX 전용 보유 4종목 (003490 kojiro · 232140·417200·425040 BFB)
_KRX_ONLY_HELD = ("003490", "232140", "417200", "425040")
_LOW_NORMAL = "006340"


# ---------------------------------------------------------------------------
# 공용 픽스처
# ---------------------------------------------------------------------------
def _core():
    from src.engine import stale_watcher_core as core

    return core


def _reset_probe_state(core) -> None:
    reset = getattr(core, "reset_no_feed_held_probe_for_test", None)
    if callable(reset):
        reset()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """cap · 관측 상태 · tick_volume 을 테스트마다 비운다(날짜 충돌 시한폭탄 W7 교훈)."""
    from src.engine import tick_volume
    from src.engine.daily_emit_cap import KstDailyEmitCap

    core = _core()
    monkeypatch.setattr(core, "_no_feed_held_logged", KstDailyEmitCap())
    _reset_probe_state(core)
    tick_volume.reset_for_test()
    core._stale_watcher_collector.clear()
    yield
    _reset_probe_state(core)
    tick_volume.reset_for_test()
    core._stale_watcher_collector.clear()


class _SleepSpy:
    """`stale_watcher_core.asyncio` 대역. 관측기는 이 이름에 기대면 안 된다(명세 §5.8)."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []

    async def sleep(self, secs: float) -> None:
        self.sleeps.append(secs)


class _Slow:
    def __init__(self, secs: float, value: Any) -> None:
        self.secs = secs
        self.value = value


class _Probe:
    """`_probe_krx_acml_vol` 대역 — 종목별 현재 값을 테스트가 사이클마다 바꾼다.

    값: int(그대로) · None(실패) · BaseException 인스턴스(raise) · `_Slow`(실제 대기 후 반환).
    """

    def __init__(self, values: dict | None = None, *, default: Any = None,
                 events: list | None = None) -> None:
        self.values: dict[str, Any] = dict(values or {})
        self.default = default
        self.calls: list[str] = []
        self.events = events

    async def __call__(self, ticker, *args, **kwargs):
        self.calls.append(ticker)
        if self.events is not None:
            self.events.append(("probe", ticker))
        v = self.values.get(ticker, self.default)
        if isinstance(v, BaseException):
            raise v
        if isinstance(v, _Slow):
            await _real_asyncio.sleep(v.secs)
            return v.value
        return v


def _install_probe(monkeypatch, core, probe: _Probe) -> _Probe:
    # raising=False — Red 단계(seam 미존재)에서도 결함 그 자체(지금 판정이 말해 버린다)로 붉게.
    monkeypatch.setattr(core, "_probe_krx_acml_vol", probe, raising=False)
    return probe


def _make_pool(monkeypatch, subscribed, events: list | None = None) -> MagicMock:
    import src.realtime.websocket_pool as wp_mod

    pool = MagicMock()
    pool.get_subscribed_tickers = lambda: set(subscribed)

    def _rec(kind):
        def _side(*args, **kwargs):
            if events is not None:
                events.append((kind, args[1] if len(args) > 1 else None))
            return None
        return _side

    pool.unsubscribe_in_pool = AsyncMock(side_effect=_rec("unsub"))
    pool.subscribe = AsyncMock(side_effect=_rec("sub"))
    pool.unsubscribe = AsyncMock()
    pool.get_subscriptions_by_session = MagicMock(return_value={})
    pool._subscribed_at = {}
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool)
    return pool


def _setup_ticks(monkeypatch, *, stale=(), fresh=(), now):
    """`scanner.ticker_last_tick` 주입. stale=120s 전 / fresh=5s 전 / 그 외=부재."""
    import src.engine.scanner as scanner_mod

    lt = {}
    for t in stale:
        lt[t] = now - timedelta(seconds=120)
    for t in fresh:
        lt[t] = now - timedelta(seconds=5)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", lt)
    return lt


def _make_sched(*, positions=(), next_day_clear=()):
    from src.engine.scheduler import TradingScheduler

    s = TradingScheduler.__new__(TradingScheduler)
    s._stale_retry_count = {}
    s._stale_last_resubscribe_at = {}
    s._stale_force_retry_history = {}
    s._pending_next_day_clear = set(next_day_clear)
    s._universe_excluded_today = set()
    s._running = True
    s._STALE_DETAIL_TICKER_CAP = 20
    st = MagicMock()
    st.positions = {t: MagicMock() for t in positions}
    strat = MagicMock()
    strat.state = st
    reg = MagicMock()
    reg.all = MagicMock(return_value=[strat])
    reg.is_ticker_held_by_any = MagicMock(side_effect=lambda t: t in set(positions))
    s.registry = reg
    return s


class _RegistrySpy:
    def __init__(self, no_feed) -> None:
        self.no_feed = set(no_feed)
        self.is_no_feed_calls: list[str] = []

    async def ensure_fresh(self, tickers, **kwargs):
        return None

    def is_no_feed(self, ticker: str) -> bool:
        self.is_no_feed_calls.append(ticker)
        return ticker in self.no_feed


def _patch_registry(monkeypatch, no_feed) -> _RegistrySpy:
    from src.engine import no_feed_registry as reg

    reg.reset_state_for_test()
    spy = _RegistrySpy(no_feed)
    monkeypatch.setattr(reg, "ensure_fresh", spy.ensure_fresh)
    monkeypatch.setattr(reg, "is_no_feed", spy.is_no_feed)
    return spy


def _set_ws(tickers=(), vol: int = 1000) -> None:
    """오늘(동결 시각 기준 KST) WS 체결 기록. 매 사이클 다시 만든다."""
    from src.engine import tick_volume

    tick_volume.reset_for_test()
    for t in tickers:
        tick_volume.record_acml_vol(t, vol)


async def _cycle(core, monkeypatch, *, subscribed, positions=(), ndc=(), no_feed=(),
                 ws=(), stale=(), fresh=(), events=None, sched=None):
    """현재 동결 시각에서 K stale watcher 1사이클."""
    now = datetime.now(KST)
    pool = _make_pool(monkeypatch, subscribed, events=events)
    _setup_ticks(monkeypatch, stale=stale, fresh=fresh, now=now)
    monkeypatch.setattr(core, "asyncio", _SleepSpy())
    reg = _patch_registry(monkeypatch, no_feed)
    _set_ws(ws)
    sched = sched if sched is not None else _make_sched(positions=positions, next_day_clear=ndc)
    await core.check_and_resubscribe_stale(sched)
    return pool, sched, reg


def _held_rows(caplog) -> list[logging.LogRecord]:
    """CI 루트 로거는 DEBUG — 레벨·prefix 로 한정한다(cycle252 T2 교훈)."""
    return [r for r in caplog.records
            if r.levelno >= logging.WARNING and r.getMessage().startswith(_HELD_PREFIX)]


_PROBE_RE = re.compile(r"ticker=['\"]?(?P<t>\w+)['\"]?.*?\bphase=(?P<p>\w+)")


def _probe_phases(caplog, ticker: str | None = None) -> list[str]:
    out = []
    for r in caplog.records:
        msg = r.getMessage()
        if not msg.startswith(_PROBE_PREFIX):
            continue
        m = _PROBE_RE.search(msg)
        if m is None:
            continue
        if ticker is None or m.group("t") == ticker:
            out.append(m.group("p"))
    return out


def _at(day: str, hms: str) -> str:
    return f"{day} {hms}+09:00"


def _cap_unused(core, now: datetime) -> bool:
    return core._no_feed_held_logged.should_emit(core._NO_FEED_HELD_KEY, now=now) is True


# ===========================================================================
# E1 / E1b — 10-01 재현: WS 기록이 있으면 말하지 않는다
# ===========================================================================
async def test_e1_oct01_ws_recorded_krx_only_holdings_never_alarm(monkeypatch, caplog):
    """10-01 운영 재현 — 대상 4종목이 마커보다 먼저 정규장 체결 틱을 받았다.

    지금 판정은 정적 분류(KRX 전용) 하나라 09:01:50 첫 사이클에 1행을 낸다(= 결함).
    WS 기록이 있는 종목은 REST 를 읽을 이유조차 없다 — REST 0회.
    """
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe(default=1000))
    day = "2026-10-01"
    subscribed = [*_KRX_ONLY_HELD, _LOW_NORMAL]

    with freeze_time(_at(day, "09:01:50"), real_asyncio=True) as frozen:
        for i, hms in enumerate(("09:01:50", "09:03:00", "09:13:00", "09:15:00", "09:30:00")):
            frozen.move_to(_at(day, hms))
            probe.default = 1000 * (i + 1)  # 증가값 — 쓰이면 안 된다
            await _cycle(core, monkeypatch, subscribed=subscribed,
                         positions=_KRX_ONLY_HELD, no_feed=_KRX_ONLY_HELD,
                         ws=_KRX_ONLY_HELD, fresh=subscribed)

    held = _held_rows(caplog)
    assert held == [], (
        "10-01 거짓 경보 재현 — WS 체결 기록이 있는 KRX 전용 보유 종목에 [no_feed_held] 가 떴다. "
        f"actual={[r.getMessage() for r in held]}"
    )
    assert probe.calls == [], (
        f"WS 기록이 있는 종목은 REST 를 읽지 않는다 — actual calls={probe.calls!r}"
    )


async def test_e1b_judgement_ignores_ticker_last_tick(monkeypatch, caplog):
    """`ticker_last_tick` 이 비어 있어도(부재) WS 기록이 있으면 0행.

    `ticker_last_tick` 은 REST 폴도 찍는다(scheduler `_run_swing_rest_poll_once` → `on_tick`)
    — 거짓 음성·거짓 양성을 함께 만드는 출처라 판정에 쓰지 않는다(명세 §3.2).
    """
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe(default=1000))
    day = "2026-10-01"
    subscribed = ["003490", _LOW_NORMAL]

    with freeze_time(_at(day, "09:03:00"), real_asyncio=True) as frozen:
        for i, hms in enumerate(("09:03:00", "09:13:00", "09:15:00")):
            frozen.move_to(_at(day, hms))
            probe.default = 1000 + 500 * i
            await _cycle(core, monkeypatch, subscribed=subscribed,
                         positions=["003490"], no_feed=["003490"],
                         ws=["003490"], fresh=[_LOW_NORMAL])  # 003490 은 ticker_last_tick 부재

    assert _held_rows(caplog) == [], (
        "`ticker_last_tick` 부재를 무송출 증거로 읽었다 — 판정은 WS 기록(tick_volume)만 본다. "
        f"actual={[r.getMessage() for r in _held_rows(caplog)]}"
    )
    assert probe.calls == [], f"WS 기록이 있으면 REST 0 — actual={probe.calls!r}"


# ===========================================================================
# E2 — 저유동 정상 무체결
# ===========================================================================
async def test_e2_flat_volume_low_liquidity_never_alarms(monkeypatch, caplog):
    """WS 기록 없음 + REST 누적이 그대로 = 체결이 없었다(정상). 종일 0행.

    기준은 `(vol1, now)` 로 옮겨 간다 — REST 는 간격(600s)마다 한 번씩만.
    """
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe(default=1000))
    day = "2026-10-05"
    subscribed = ["003490", _LOW_NORMAL]
    times = ("09:03:00", "09:05:00", "09:13:00", "09:15:00", "09:23:00", "09:25:00")

    with freeze_time(_at(day, times[0]), real_asyncio=True) as frozen:
        for hms in times:
            frozen.move_to(_at(day, hms))
            await _cycle(core, monkeypatch, subscribed=subscribed,
                         positions=["003490"], no_feed=["003490"],
                         ws=(), stale=["003490"], fresh=[_LOW_NORMAL])
        now = datetime.now(KST)
        cap_unused = _cap_unused(core, now)

    assert _held_rows(caplog) == [], (
        "체결이 없는 저유동 보유를 무송출로 오판했다(누적 증가 없음 = 정상). "
        f"actual={[r.getMessage() for r in _held_rows(caplog)]}"
    )
    assert probe.calls == ["003490", "003490", "003490"], (
        "REST 는 09:03(기준)·09:13(간격 경과)·09:23(옮긴 기준에서 간격 경과) 3회 — "
        f"actual={probe.calls!r}"
    )
    assert _probe_phases(caplog, "003490") == ["baseline", "flat", "flat"], (
        f"[no_feed_held_probe] phase 순서 — actual={_probe_phases(caplog, '003490')!r}"
    )
    assert cap_unused, "말하지 않았으면 그날 cap 도 쓰지 않는다"


# ===========================================================================
# E2b — 일중 누적거래량 감소(이상값)로 기준이 내려가면 안 된다 (F1, cycle393 리뷰)
# ===========================================================================
async def test_e2b_volume_dip_does_not_lower_baseline(monkeypatch, caplog):
    """1000 → 0(이상값, 응답 결측 "0" 폴백 등) → 1000 복귀 = 체결 0건이지 증분이 아니다.

    기준을 내렸다면 세 번째 읽기(1000)가 직전 기준(0)보다 커서 "증분"으로 오판되고,
    60초 뒤 `[no_feed_held]` 가 뜬다 — 이번 사이클이 없애려던 거짓 경보가 되살아난다.
    """
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe())
    day = "2026-10-05"
    ticker = "003490"
    subscribed = [ticker, _LOW_NORMAL]
    plan = (("09:03:00", 1000), ("09:13:00", 0), ("09:23:00", 1000), ("09:23:59", 1000))

    with freeze_time(_at(day, plan[0][0]), real_asyncio=True) as frozen:
        for hms, vol in plan:
            frozen.move_to(_at(day, hms))
            probe.values[ticker] = vol
            await _cycle(core, monkeypatch, subscribed=subscribed,
                         positions=[ticker], no_feed=[ticker], ws=(),
                         stale=[ticker], fresh=[_LOW_NORMAL])

    assert _held_rows(caplog) == [], (
        "누적거래량 이상 감소 뒤 복귀를 증분(체결)으로 오판했다 — "
        f"actual={[r.getMessage() for r in _held_rows(caplog)]}"
    )
    assert probe.calls == [ticker, ticker, ticker], (
        f"REST 는 기준(09:03)·간격경과(09:13)·간격경과(09:23) 3회 — actual={probe.calls!r}"
    )
    assert _probe_phases(caplog, ticker) == ["baseline", "decreased", "flat"], (
        f"기준 1000 유지 — 09:13 은 decreased(0<1000), 09:23 은 flat(1000==유지된 기준) — "
        f"actual={_probe_phases(caplog, ticker)!r}"
    )


# ===========================================================================
# E3 / E3b — 진짜 무송출
# ===========================================================================
async def _drive_genuine(core, monkeypatch, caplog, *, day, ticker, fresh_path: bool):
    """09:03 기준 1000 → 09:13 1500(증분) → 09:13:30(대기) → 09:15(확정). 사이클별 신규 행 수."""
    probe = _install_probe(monkeypatch, core, _Probe())
    subscribed = [ticker, _LOW_NORMAL]
    plan = (("09:03:00", 1000), ("09:05:00", 1200), ("09:13:00", 1500),
            ("09:13:30", 1600), ("09:15:00", 1700))
    rows_per_cycle: list[int] = []
    with freeze_time(_at(day, plan[0][0]), real_asyncio=True) as frozen:
        for hms, vol in plan:
            frozen.move_to(_at(day, hms))
            probe.values[ticker] = vol
            before = len(_held_rows(caplog))
            if fresh_path:
                # REST 폴(donchian·kojiro)이 `ticker_last_tick` 을 찍어 전부 fresh → 조기 반환 출구
                await _cycle(core, monkeypatch, subscribed=subscribed,
                             positions=[ticker], no_feed=[ticker], ws=(),
                             fresh=subscribed)
            else:
                await _cycle(core, monkeypatch, subscribed=subscribed,
                             positions=[ticker], no_feed=[ticker], ws=(),
                             stale=[ticker], fresh=[_LOW_NORMAL])
            rows_per_cycle.append(len(_held_rows(caplog)) - before)
    return probe, rows_per_cycle


async def test_e3_genuine_no_feed_alarms_only_after_confirm(monkeypatch, caplog):
    """구독 중 KRX 체결(1000→1500)이 있었는데 WS 기록 0 → 확인 대기(60s) 뒤 1행."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe, rows = await _drive_genuine(core, monkeypatch, caplog, day="2026-10-05",
                                       ticker="003490", fresh_path=False)

    assert rows == [0, 0, 0, 0, 1], (
        "기준(09:03)·간격 전(09:05)·증분 확인(09:13)·확인 대기(09:13:30) 는 0행, "
        f"09:15 확정에서 1행이어야 한다 — 사이클별 신규 행={rows!r}"
    )
    assert probe.calls == ["003490", "003490"], (
        f"REST 는 기준·증분 두 번뿐(확인 대기는 다시 읽지 않는다) — actual={probe.calls!r}"
    )
    msg = _held_rows(caplog)[0].getMessage()
    assert msg.startswith("[no_feed_held] tickers="), f"첫 필드 tickers= 유지 — {msg!r}"
    assert "003490" in msg and "1000" in msg and "1500" in msg, (
        f"evidence 에 종목·두 누적값이 있어야 D+1 판독이 된다 — {msg!r}"
    )
    assert "evidence=" in msg, f"evidence= 필드 — {msg!r}"
    for stale_word in ("연속체결 미수신", "H0UNCNT0", "09:05~15:20"):
        assert stale_word not in msg, f"낡은 문구 {stale_word!r} 잔존 — {msg!r}"
    assert _probe_phases(caplog, "003490") == ["baseline", "traded"], (
        f"[no_feed_held_probe] phase — actual={_probe_phases(caplog, '003490')!r}"
    )


async def test_e3b_genuine_no_feed_on_all_fresh_early_return_path(monkeypatch, caplog):
    """cycle252 T1 의도 — REST 폴로 fresh 처럼 보이는 보유도 판정한다(조기 반환 출구)."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    _probe, rows = await _drive_genuine(core, monkeypatch, caplog, day="2026-10-05",
                                        ticker="003490", fresh_path=True)

    assert rows == [0, 0, 0, 0, 1], (
        "「모두 fresh」 조기 반환 사이클에서도 관측기가 돌아야 한다 — "
        f"사이클별 신규 행={rows!r}"
    )


# ===========================================================================
# E4 / E4b — 상태 삭제
# ===========================================================================
async def test_e4_ws_record_during_confirm_wait_cancels_and_resets(monkeypatch, caplog):
    """확인 대기 중 WS 기록이 생기면 0행 + 상태 삭제 — W 가 다시 참이 되면 기준부터."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe())
    day = "2026-10-05"
    t = "003490"
    subscribed = [t, _LOW_NORMAL]
    kw = dict(subscribed=subscribed, positions=[t], no_feed=[t],
              stale=[t], fresh=[_LOW_NORMAL])

    with freeze_time(_at(day, "09:03:00"), real_asyncio=True) as frozen:
        probe.values[t] = 1000
        await _cycle(core, monkeypatch, ws=(), **kw)           # 기준
        frozen.move_to(_at(day, "09:13:00"))
        probe.values[t] = 1500
        await _cycle(core, monkeypatch, ws=(), **kw)           # 증분 확인
        frozen.move_to(_at(day, "09:15:00"))
        await _cycle(core, monkeypatch, ws=[t], **kw)          # 확인 시점에 WS 기록 생김
        calls_after_ws = len(probe.calls)
        frozen.move_to(_at(day, "09:16:00"))
        probe.values[t] = 1600
        await _cycle(core, monkeypatch, ws=(), **kw)           # W 다시 참 → 처음부터

    assert _held_rows(caplog) == [], (
        "WS 기록이 생긴 종목은 확정하지 않는다 · 상태가 지워져야 다음 사이클에도 확정되지 않는다. "
        f"actual={[r.getMessage() for r in _held_rows(caplog)]}"
    )
    assert calls_after_ws == 2, f"WS 기록이 있는 사이클은 REST 0 — calls={probe.calls!r}"
    assert len(probe.calls) == 3, (
        "상태가 지워졌으면 W 가 다시 참일 때 기준 읽기부터 다시 한다(REST 1회) — "
        f"calls={probe.calls!r}"
    )
    assert _probe_phases(caplog, t)[-1] == "baseline", (
        f"삭제 뒤 첫 읽기는 baseline — phases={_probe_phases(caplog, t)!r}"
    )


async def test_e4b_subscription_gap_resets_evidence(monkeypatch, caplog):
    """기준 뒤 구독이 빠졌다가 돌아오면 「구독 중 체결」 증명이 깨진다 — 처음부터."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe())
    day = "2026-10-05"
    t = "003490"
    base = dict(positions=[t], no_feed=[t], ws=(), stale=[t], fresh=[_LOW_NORMAL])

    with freeze_time(_at(day, "09:03:00"), real_asyncio=True) as frozen:
        probe.values[t] = 1000
        await _cycle(core, monkeypatch, subscribed=[t, _LOW_NORMAL], **base)   # 기준
        frozen.move_to(_at(day, "09:05:00"))
        await _cycle(core, monkeypatch, subscribed=[_LOW_NORMAL], **base)      # 구독 공백
        frozen.move_to(_at(day, "09:13:00"))
        probe.values[t] = 1500
        await _cycle(core, monkeypatch, subscribed=[t, _LOW_NORMAL], **base)   # 재구독 = 새 기준
        frozen.move_to(_at(day, "09:15:00"))
        await _cycle(core, monkeypatch, subscribed=[t, _LOW_NORMAL], **base)

    assert _held_rows(caplog) == [], (
        "구독 공백을 낀 누적 증가는 「구독 중 체결」 증거가 아니다. "
        f"actual={[r.getMessage() for r in _held_rows(caplog)]}"
    )
    assert _probe_phases(caplog, t) == ["baseline", "baseline"], (
        f"재구독 뒤 읽기는 새 기준(baseline) — phases={_probe_phases(caplog, t)!r}"
    )


# ===========================================================================
# E5 / E5b — REST 실패는 말하지 않는다
# ===========================================================================
_FAIL_KINDS = ["none", "raise", "timeout"]


def _fail_value(kind: str, monkeypatch, core):
    if kind == "none":
        return None
    if kind == "raise":
        return RuntimeError("KIS 500")
    # 타임아웃 — 상수는 호출 시점에 모듈 전역에서 읽는다(테스트가 0.05 로 줄인다, 1초 미만 유지)
    monkeypatch.setattr(core, "NO_FEED_PROBE_TIMEOUT_SECS", 0.05, raising=False)
    return _Slow(0.5, 999_999)


@pytest.mark.parametrize("kind", _FAIL_KINDS)
async def test_e5_probe_failure_is_silent_and_retried(monkeypatch, caplog, kind):
    """REST 실패·None·타임아웃·예외 → 상태 무변경 · 0행 · cap 미소비 · 다음 사이클 재시도."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe())
    day = "2026-10-05"
    t = "003490"
    probe.values[t] = _fail_value(kind, monkeypatch, core)
    kw = dict(subscribed=[t, _LOW_NORMAL], positions=[t], no_feed=[t], ws=(),
              stale=[t], fresh=[_LOW_NORMAL])

    with freeze_time(_at(day, "09:05:00"), real_asyncio=True) as frozen:
        await _cycle(core, monkeypatch, **kw)   # raise 하면 즉시 FAIL
        frozen.move_to(_at(day, "09:07:00"))
        await _cycle(core, monkeypatch, **kw)
        now = datetime.now(KST)
        cap_unused = _cap_unused(core, now)

    assert _held_rows(caplog) == [], (
        f"측정 실패({kind})로 말했다 — 이번 결함 그 자체. "
        f"actual={[r.getMessage() for r in _held_rows(caplog)]}"
    )
    assert probe.calls == [t, t], (
        "실패는 기준을 저장하지 않는다 — 다음 사이클(간격 무관)에 다시 기준을 읽는다. "
        f"actual={probe.calls!r}"
    )
    assert _probe_phases(caplog, t) == ["failed", "failed"], (
        f"[no_feed_held_probe] phase=failed — actual={_probe_phases(caplog, t)!r}"
    )
    assert cap_unused, "실패는 cap 을 쓰지 않는다"


@pytest.mark.parametrize("kind", _FAIL_KINDS)
async def test_e5b_failed_second_read_is_not_an_increment(monkeypatch, caplog, kind):
    """기준 뒤 두 번째 읽기 실패 → 기준 유지 · 재시도. 진짜 증분이 측정된 뒤에만 확정."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe())
    day = "2026-10-05"
    t = "003490"
    kw = dict(subscribed=[t, _LOW_NORMAL], positions=[t], no_feed=[t], ws=(),
              stale=[t], fresh=[_LOW_NORMAL])
    plan = (("09:03:00", 1000), ("09:13:00", _fail_value(kind, monkeypatch, core)),
            ("09:14:10", None), ("09:15:00", 1500), ("09:15:30", 1600), ("09:16:00", 1700))
    rows: list[int] = []

    with freeze_time(_at(day, plan[0][0]), real_asyncio=True) as frozen:
        for hms, v in plan:
            frozen.move_to(_at(day, hms))
            probe.values[t] = v
            before = len(_held_rows(caplog))
            await _cycle(core, monkeypatch, **kw)
            rows.append(len(_held_rows(caplog)) - before)

    assert rows == [0, 0, 0, 0, 0, 1], (
        "실패한 읽기를 증분으로 취급하면 09:14:10 에 확정된다. 기준(09:03)은 유지되고 "
        f"09:15 의 진짜 증분 뒤 60초(09:16)에만 1행 — 사이클별 신규 행={rows!r}"
    )


# ===========================================================================
# E6 / E6b — 판정 창
# ===========================================================================
@pytest.mark.parametrize("hms", ["08:10:00", "09:01:00", "09:02:59", "15:20:00",
                                 "15:25:00", "16:30:00"])
async def test_e6_outside_window_no_rest_no_alarm(monkeypatch, caplog, hms):
    """창 = K3 `[개장+180s, 종료)` — 창 밖은 REST 를 읽지 않는다(15:20:00 은 제외 경계)."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe(default=5000))
    day = "2026-10-05"
    t = "003490"

    with freeze_time(_at(day, hms), real_asyncio=True):
        await _cycle(core, monkeypatch, subscribed=[t, _LOW_NORMAL], positions=[t],
                     no_feed=[t], ws=(), stale=[t], fresh=[_LOW_NORMAL])

    assert probe.calls == [], f"{hms} 은 판정 창 밖 — REST 0, actual={probe.calls!r}"
    assert _held_rows(caplog) == [], (
        f"{hms} 창 밖 — 측정 없이 말했다. actual={[r.getMessage() for r in _held_rows(caplog)]}"
    )


async def test_e6_grace_end_is_inclusive(monkeypatch, caplog):
    """09:03:00 정각(개장+180s)은 창 안 — 기준 읽기 1회."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe(default=5000))
    t = "003490"

    with freeze_time(_at("2026-10-05", "09:03:00"), real_asyncio=True):
        await _cycle(core, monkeypatch, subscribed=[t, _LOW_NORMAL], positions=[t],
                     no_feed=[t], ws=(), stale=[t], fresh=[_LOW_NORMAL])

    assert probe.calls == [t], f"grace 끝 시각은 포함 — actual={probe.calls!r}"
    assert _held_rows(caplog) == [], "기준 읽기만 — 말하지 않는다"


async def test_e6b_confirm_proceeds_after_window_close_same_day(monkeypatch, caplog):
    """15:19 증분 확인 → 15:21 확정. 체결은 창 안에서 측정됐다 — 확인은 같은 날 창 밖에서도."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe())
    day = "2026-10-05"
    t = "003490"
    kw = dict(subscribed=[t, _LOW_NORMAL], positions=[t], no_feed=[t], ws=(),
              stale=[t], fresh=[_LOW_NORMAL])
    rows: list[int] = []

    with freeze_time(_at(day, "15:09:00"), real_asyncio=True) as frozen:
        for hms, v in (("15:09:00", 1000), ("15:19:00", 1500), ("15:21:00", 1600)):
            frozen.move_to(_at(day, hms))
            probe.values[t] = v
            before = len(_held_rows(caplog))
            await _cycle(core, monkeypatch, **kw)
            rows.append(len(_held_rows(caplog)) - before)

    assert rows == [0, 0, 1], f"15:21 확정 1행 — 사이클별 신규 행={rows!r}"
    assert probe.calls == [t, t], (
        f"확인 단계는 REST 를 다시 읽지 않는다(15:21 은 창 밖) — actual={probe.calls!r}"
    )


# ===========================================================================
# E7 — 표 조회 실패는 창 안으로 본다
# ===========================================================================
def _patch_table(monkeypatch, core, fn) -> dict:
    import src.engine.market_state as ms

    seen = {"n": 0}

    def _wrapped(*a, **k):
        seen["n"] += 1
        return fn(*a, **k)

    monkeypatch.setattr(ms, "get_market_table", _wrapped)
    # 구현이 core 전역으로 묶어 쓰는 경우도 같은 대역을 보게 한다
    monkeypatch.setattr(core, "get_market_table", _wrapped, raising=False)
    return seen


def _raise_table(*_a, **_k):
    raise RuntimeError("market table down")


@pytest.mark.parametrize("variant,day", [("raise", "2026-10-07"), ("empty", "2026-10-08")])
async def test_e7_table_failure_fails_open_to_inside_window(monkeypatch, caplog, variant, day):
    """시각 게이트 실패는 억제하지 않는다(cycle357 승계) — 16:30 이어도 REST 를 읽는다.

    날짜는 이 테스트 전용(10-07·10-08) — 다른 테스트가 같은 날짜의 창을 미리 계산해 두면
    대역이 우회될 수 있다.
    """
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe(default=5000))
    seen = _patch_table(monkeypatch, core, _raise_table if variant == "raise" else (lambda *a, **k: ()))
    t = "003490"

    with freeze_time(_at(day, "16:30:00"), real_asyncio=True):
        await _cycle(core, monkeypatch, subscribed=[t, _LOW_NORMAL], positions=[t],
                     no_feed=[t], ws=(), stale=[t], fresh=[_LOW_NORMAL])

    assert seen["n"] >= 1, "판정 창은 `market_state.get_market_table` 에서 읽는다(시각 리터럴 0)"
    assert probe.calls == [t], (
        f"표 조회 실패({variant})는 창 안으로 본다 — REST 1회, actual={probe.calls!r}"
    )


# ===========================================================================
# E8 — 재기동 모사
# ===========================================================================
async def test_e8_restart_with_large_morning_volume_does_not_alarm(monkeypatch, caplog):
    """10:30 재기동 — 첫 읽기 누적이 이미 크다(아침 거래). 한 번 읽기로 말하면 거짓 경보."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe(default=520_000))
    day = "2026-10-05"
    t = "003490"

    with freeze_time(_at(day, "10:30:00"), real_asyncio=True) as frozen:
        for hms in ("10:30:00", "10:32:00", "10:40:00", "10:42:00", "10:50:00", "10:52:00"):
            frozen.move_to(_at(day, hms))
            await _cycle(core, monkeypatch, subscribed=[t, _LOW_NORMAL], positions=[t],
                         no_feed=[t], ws=(), stale=[t], fresh=[_LOW_NORMAL])

    assert _held_rows(caplog) == [], (
        f"누적 증가 없는 재기동 날 — actual={[r.getMessage() for r in _held_rows(caplog)]}"
    )
    assert _probe_phases(caplog, t) == ["baseline", "flat", "flat"], (
        f"phases={_probe_phases(caplog, t)!r}"
    )


# ===========================================================================
# E9 — 사이클당 REST 상한 · 간격 전 재조회 0
# ===========================================================================
async def test_e9_per_cycle_probe_cap_and_interval(monkeypatch, caplog):
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe(default=1000))
    day = "2026-10-05"
    six = ["000815", "003490", "035720", "232140", "417200", "425040"]
    subscribed = [*six, _LOW_NORMAL]
    per_cycle: dict[str, list[str]] = {}

    with freeze_time(_at(day, "09:05:00"), real_asyncio=True) as frozen:
        for hms in ("09:05:00", "09:07:00", "09:09:00", "09:15:00", "09:17:00"):
            frozen.move_to(_at(day, hms))
            before = len(probe.calls)
            await _cycle(core, monkeypatch, subscribed=subscribed, positions=six,
                         no_feed=six, ws=(), stale=six, fresh=[_LOW_NORMAL])
            per_cycle[hms] = probe.calls[before:]

    assert sorted(per_cycle["09:05:00"]) == six[:4], (
        f"첫 사이클 = 정렬 순 앞 4종목 — actual={per_cycle!r}"
    )
    assert sorted(per_cycle["09:07:00"]) == six[4:], (
        f"남은 종목은 다음 사이클 — actual={per_cycle!r}"
    )
    assert per_cycle["09:09:00"] == [], f"간격(600s) 전 재조회 0 — actual={per_cycle!r}"
    assert sorted(per_cycle["09:15:00"]) == six[:4], (
        f"09:05 기준 종목만 간격 경과 — actual={per_cycle!r}"
    )
    assert sorted(per_cycle["09:17:00"]) == six[4:], f"actual={per_cycle!r}"
    for hms, calls in per_cycle.items():
        assert len(calls) <= 4, f"{hms} 사이클 REST {len(calls)} > 4"


# ===========================================================================
# E10 — 날짜 자기 리셋
# ===========================================================================
async def test_e10_previous_day_baseline_is_discarded(monkeypatch, caplog):
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe())
    t = "003490"
    kw = dict(subscribed=[t, _LOW_NORMAL], positions=[t], no_feed=[t], ws=(),
              stale=[t], fresh=[_LOW_NORMAL])

    with freeze_time(_at("2026-10-05", "15:00:00"), real_asyncio=True) as frozen:
        probe.values[t] = 1000
        await _cycle(core, monkeypatch, **kw)            # 어제 기준
        caplog.clear()
        frozen.move_to(_at("2026-10-06", "09:05:00"))
        probe.values[t] = 5000                           # 어제 기준 대비 「증가」 처럼 보이는 값
        await _cycle(core, monkeypatch, **kw)
        frozen.move_to(_at("2026-10-06", "09:06:05"))
        await _cycle(core, monkeypatch, **kw)
        frozen.move_to(_at("2026-10-06", "09:08:00"))
        await _cycle(core, monkeypatch, **kw)

    assert _held_rows(caplog) == [], (
        "전날 기준을 오늘 증거로 썼다 — 장외·전날 체결이 「구독 중 체결」 로 둔갑한다. "
        f"actual={[r.getMessage() for r in _held_rows(caplog)]}"
    )
    assert _probe_phases(caplog, t) == ["baseline"], (
        f"오늘 첫 읽기는 새 기준 — phases={_probe_phases(caplog, t)!r}"
    )


# ===========================================================================
# E11 — 대상 범위
# ===========================================================================
@pytest.mark.parametrize("case", ["high_not_no_feed", "low_no_feed", "held_not_subscribed"])
async def test_e11_scope_excludes_non_cohort(monkeypatch, caplog, case):
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe(default=1000))
    day = "2026-10-05"
    if case == "high_not_no_feed":
        kw = dict(subscribed=["005930", _LOW_NORMAL], positions=["005930"], no_feed=())
    elif case == "low_no_feed":
        kw = dict(subscribed=["005935", _LOW_NORMAL], positions=(), no_feed=["005935"])
    else:  # 보유 · KRX 전용인데 이번 사이클 구독에 없다(구독 누락은 다른 결함)
        kw = dict(subscribed=[_LOW_NORMAL], positions=["003490"], no_feed=["003490"])

    with freeze_time(_at(day, "09:05:00"), real_asyncio=True) as frozen:
        for i, hms in enumerate(("09:05:00", "09:15:00", "09:16:30")):
            frozen.move_to(_at(day, hms))
            probe.default = 1000 + 500 * i
            await _cycle(core, monkeypatch, ws=(), fresh=[_LOW_NORMAL], **kw)

    assert probe.calls == [], f"{case} — 대상 밖 REST 0, actual={probe.calls!r}"
    assert _held_rows(caplog) == [], (
        f"{case} — 대상 밖 0행, actual={[r.getMessage() for r in _held_rows(caplog)]}"
    )


async def test_e11d_next_day_clear_high_is_in_scope(monkeypatch, caplog):
    """익일청산 HIGH 는 대상 — 증거가 서면 1행."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe())
    day = "2026-10-05"
    t = "000815"
    kw = dict(subscribed=[t, _LOW_NORMAL], ndc={(t, "kojiro")}, no_feed=[t], ws=(),
              stale=[t], fresh=[_LOW_NORMAL])
    rows: list[int] = []

    with freeze_time(_at(day, "09:05:00"), real_asyncio=True) as frozen:
        for hms, v in (("09:05:00", 1000), ("09:15:00", 1500), ("09:16:30", 1600)):
            frozen.move_to(_at(day, hms))
            probe.values[t] = v
            before = len(_held_rows(caplog))
            await _cycle(core, monkeypatch, **kw)
            rows.append(len(_held_rows(caplog)) - before)

    assert rows == [0, 0, 1], f"익일청산 HIGH 확정 1행 — 사이클별={rows!r}"
    assert t in _held_rows(caplog)[0].getMessage()


# ===========================================================================
# E12 — 배치: HIGH 재등록이 먼저
# ===========================================================================
async def test_e12_probe_runs_after_high_reregistration_and_detail(monkeypatch, caplog):
    """REST 를 재등록 앞에서 기다리면 그 사이클의 HIGH 재등록(손절 시세 복구)이 늦어진다."""
    core = _core()
    caplog.set_level(logging.DEBUG)
    events: list[tuple] = []
    _install_probe(monkeypatch, core, _Probe(default=1000, events=events))
    real_detail = core.emit_stale_session_detail

    def _detail(*a, **k):
        events.append(("detail", None))
        return real_detail(*a, **k)

    monkeypatch.setattr(core, "emit_stale_session_detail", _detail)
    t = "003490"

    with freeze_time(_at("2026-10-05", "09:05:00"), real_asyncio=True):
        await _cycle(core, monkeypatch, subscribed=[t, _LOW_NORMAL], positions=[t],
                     no_feed=[t], ws=(), stale=[t, _LOW_NORMAL], events=events)

    kinds = [e[0] for e in events]
    assert "probe" in kinds, f"이 사이클에 기준 REST 가 있어야 한다 — events={events!r}"
    first_probe = kinds.index("probe")
    sends = [i for i, k in enumerate(kinds) if k in ("sub", "unsub")]
    assert sends and ("sub", t) in events, f"HIGH 재등록 SEND 가 있어야 한다 — events={events!r}"
    assert max(sends) < first_probe, (
        f"HIGH 재등록 SEND 가 모두 끝난 뒤 첫 REST 여야 한다 — events={events!r}"
    )
    assert "detail" in kinds and kinds.index("detail") < first_probe, (
        f"관측기는 `emit_stale_session_detail` 뒤에 돈다(명세 §4) — events={events!r}"
    )


# ===========================================================================
# E13 — 차분: HIGH 재등록·LOW skip 5축이 기준 sha 구현과 같다
# ===========================================================================
_BASELINE_SHA_393 = "9df058df655b4aad31901e638504dc15f9776758"
_BASE_MOD_NAME = "_cycle393_base_stale_watcher_core"


def _load_baseline_module(tmp_path: Path):
    res = subprocess.run(
        ["git", "show", f"{_BASELINE_SHA_393}:src/engine/stale_watcher_core.py"],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    if res.returncode != 0:
        pytest.skip(
            f"기준 sha {_BASELINE_SHA_393[:7]} 소스 조회 불가 (rc={res.returncode}, "
            f"shallow clone 등) — E13 차분 생략. stderr={(res.stderr or '').strip()!r}"
        )
    path = tmp_path / "base_stale_watcher_core.py"
    path.write_text(res.stdout, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(_BASE_MOD_NAME, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_BASE_MOD_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


def _pool_trace(pool: MagicMock) -> list[tuple]:
    return [(c[0], tuple(c[1]), dict(c[2])) for c in pool.mock_calls]


def _sched_axes(sched) -> dict:
    return {
        "retry": dict(sched._stale_retry_count),
        "last_at": dict(sched._stale_last_resubscribe_at),
        "history": {k: list(v) for k, v in sched._stale_force_retry_history.items()},
    }


def _clone_sched(positions, ndc, retry, last_at, history):
    s = _make_sched(positions=positions, next_day_clear=ndc)
    s._stale_retry_count = dict(retry)
    s._stale_last_resubscribe_at = dict(last_at)
    s._stale_force_retry_history = {k: list(v) for k, v in history.items()}
    return s


@pytest.mark.slow
async def test_e13_high_reregistration_identical_to_baseline(monkeypatch, tmp_path, caplog):
    """cohort 비공집합 · REST 무작위 · WS 기록 무작위 · 창 안 시각에서 5축 비교.

    (a) pool 호출 순서·인자(전체 `mock_calls`) (b) `_stale_retry_count`
    (c) `_stale_last_resubscribe_at` (d) `_stale_force_retry_history` (e) collector 통계.
    조합마다 3사이클(t0 · t0+600s · t0+660s) — 기준·증분·확정 단계가 모두 지나가게 한다.
    관측기가 한 번도 REST 를 읽지 않으면 차분이 공허하므로 그것도 실패로 본다.
    """
    from src.engine.stale_diagnostics import STALE_FORCE_RETRY_HOURLY_CAP

    core = _core()
    base = _load_baseline_module(tmp_path)
    caplog.set_level(logging.WARNING)

    # 채널 전환 사이클은 두 구현이 공유하는 바깥 의존이고 하루 1회 상태를 가진다 —
    # 먼저 도는 쪽만 pool 을 건드리는 허위 불일치를 막기 위해 양쪽 모두 무동작으로 둔다.
    from src.engine import tick_channel_switch

    async def _no_switch(*_a, **_k):
        return {"skip": "test"}

    monkeypatch.setattr(tick_channel_switch, "run_switch_cycle", _no_switch)

    universe = [*_KRX_ONLY_HELD, "005935", _LOW_NORMAL, "035720", "047040"]
    rnd = random.Random(20261002)
    combos = 210
    mismatches: list[str] = []
    probe_total = 0
    stat_keys = ("subscribed", "stale", "force_reregistered", "skipped_giveup",
                 "force_retried", "cap_blocked", "no_feed_skipped")

    with freeze_time(_at("2026-10-05", "09:03:00"), real_asyncio=True) as frozen:
        for i in range(combos):
            tickers = rnd.sample(universe, rnd.randint(2, 6))
            positions = [t for t in tickers if rnd.random() < 0.5]
            ndc = {(t, "kojiro") for t in tickers if t not in positions and rnd.random() < 0.15}
            no_feed = {t for t in tickers if rnd.random() < 0.6}
            if positions and not (no_feed & set(positions)):
                no_feed.add(positions[0])  # cohort 비공집합 보장(대부분)
            t0 = datetime(2026, 10, 5, 9, 3, tzinfo=KST) + timedelta(
                minutes=rnd.randint(0, 6 * 60 - 20))
            frozen.move_to(t0)
            retry = {t: rnd.choice([0, 1, 4, 5, 6, 8]) for t in tickers}
            last_at = {}
            for t in tickers:
                age = rnd.choice([None, 10, 300, 700, 4000])
                if age is not None:
                    last_at[t] = t0 - timedelta(seconds=age)
            history = {
                t: [t0 - timedelta(seconds=60 * k + 5)
                    for k in range(rnd.choice([0, 0, 1, STALE_FORCE_RETRY_HOURLY_CAP]))]
                for t in tickers
            }
            scheds = {
                "base": _clone_sched(positions, ndc, retry, last_at, history),
                "core": _clone_sched(positions, ndc, retry, last_at, history),
            }
            _reset_probe_state(core)
            from src.engine.daily_emit_cap import KstDailyEmitCap
            monkeypatch.setattr(core, "_no_feed_held_logged", KstDailyEmitCap())
            probe = _install_probe(monkeypatch, core, _Probe())

            for step, offset in enumerate((0, 600, 660)):
                now = t0 + timedelta(seconds=offset)
                frozen.move_to(now)
                subscribed = [t for t in tickers if rnd.random() < 0.9] or tickers[:1]
                stale = [t for t in subscribed if rnd.random() < 0.6]
                fresh = [t for t in subscribed if t not in stale and rnd.random() < 0.8]
                ws = [t for t in tickers if rnd.random() < 0.3]
                for t in tickers:
                    probe.values[t] = rnd.choice(
                        [None, RuntimeError("x"), 1000, 1000 + 100 * step, 1000 + 500 * step])

                results = {}
                for name, mod in (("base", base), ("core", core)):
                    pool = _make_pool(monkeypatch, subscribed)
                    _setup_ticks(monkeypatch, stale=stale, fresh=fresh, now=now)
                    monkeypatch.setattr(mod, "asyncio", _SleepSpy())
                    _patch_registry(monkeypatch, no_feed)
                    _set_ws(ws)
                    mod._stale_watcher_collector.clear()
                    await mod.check_and_resubscribe_stale(scheds[name])
                    stats = [{k: s.get(k) for k in stat_keys} for s in mod._stale_watcher_collector]
                    mod._stale_watcher_collector.clear()
                    results[name] = (_pool_trace(pool), _sched_axes(scheds[name]), stats)

                if results["base"] != results["core"]:
                    mismatches.append(
                        f"combo#{i} step{step} tickers={sorted(tickers)} positions={sorted(positions)} "
                        f"no_feed={sorted(no_feed)} subscribed={sorted(subscribed)} stale={sorted(stale)}\n"
                        f"  BASE={results['base']}\n  CORE={results['core']}"
                    )
                    break
            probe_total += len(probe.calls)
            if len(mismatches) >= 3:
                break

    assert mismatches == [], (
        f"HIGH 재등록·LOW skip 행위가 기준 sha {_BASELINE_SHA_393[:7]} 와 다르다 "
        f"({len(mismatches)} 건):\n" + "\n".join(mismatches)
    )
    assert probe_total > 0, (
        "차분이 공허하다 — 관측기가 어느 조합에서도 REST 를 읽지 않았다(cohort·창·W 구성을 확인하라)"
    )


# ===========================================================================
# E14 — 관측기 내부 예외는 HIGH 재등록을 끊지 않는다
# ===========================================================================
class _RaisingMap:
    def __init__(self) -> None:
        self.n = 0

    def get(self, *_a, **_k):
        self.n += 1
        raise RuntimeError("tick_volume broken")

    def __contains__(self, _k):
        self.n += 1
        raise RuntimeError("tick_volume broken")

    def __getitem__(self, _k):
        self.n += 1
        raise RuntimeError("tick_volume broken")

    def clear(self):
        return None


class _BoomCap:
    def __init__(self) -> None:
        self.n = 0

    def should_emit(self, *_a, **_k):
        self.n += 1
        raise RuntimeError("cap broken")

    def mark_emitted(self, *_a, **_k):
        raise RuntimeError("cap broken")


@pytest.mark.parametrize("fault", ["seam", "tick_volume", "table", "cap_peek"])
async def test_e14_observer_faults_never_break_high_reregistration(monkeypatch, caplog, fault):
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe(default=1000))
    day = "2026-10-05"
    t = "003490"
    probe_marker: dict[str, Any] = {}

    if fault == "seam":
        probe.default = RuntimeError("seam broken")
    elif fault == "table":
        probe_marker["table"] = _patch_table(monkeypatch, core, _raise_table)
    elif fault == "cap_peek":
        probe_marker["cap"] = _BoomCap()
        monkeypatch.setattr(core, "_no_feed_held_logged", probe_marker["cap"])

    with freeze_time(_at(day, "09:05:00"), real_asyncio=True):
        now = datetime.now(KST)
        pool = _make_pool(monkeypatch, [t, _LOW_NORMAL])
        _setup_ticks(monkeypatch, stale=[t, _LOW_NORMAL], now=now)
        monkeypatch.setattr(core, "asyncio", _SleepSpy())
        _patch_registry(monkeypatch, [t])
        _set_ws(())
        if fault == "tick_volume":
            from src.engine import tick_volume
            rm = _RaisingMap()
            probe_marker["tv"] = rm
            monkeypatch.setattr(tick_volume, "_observed", rm)
            monkeypatch.setattr(tick_volume, "_observed_day", now.strftime("%Y-%m-%d"))
        sched = _make_sched(positions=[t])

        await core.check_and_resubscribe_stale(sched)  # raise 하면 즉시 FAIL

    subs = {c.args[1]: c.kwargs for c in pool.subscribe.await_args_list}
    assert subs.get(t, {}).get("priority") == "HIGH" and subs[t].get("bypass_limit") is True, (
        f"관측기 결함({fault})이 HIGH 재등록을 끊었다 — subscribe={subs!r}"
    )
    assert sched._stale_retry_count.get(t) == 1 and t in sched._stale_last_resubscribe_at
    assert core._stale_watcher_collector and core._stale_watcher_collector[-1]["stale"] == 2, (
        "사이클 완주(collector 도달)"
    )
    assert _held_rows(caplog) == [], "결함 상태에서 말하지 않는다"

    if fault == "seam":
        assert probe.calls == [t], f"seam 이 실제로 불렸어야 한다(결함 경로 실행) — {probe.calls!r}"
    elif fault == "tick_volume":
        assert probe_marker["tv"].n >= 1, "W 다리(tick_volume)를 실제로 읽었어야 한다"
        assert probe.calls == [], "W 를 모르면(예외) 그 종목은 건너뛴다 — REST 0"
    elif fault == "table":
        assert probe_marker["table"]["n"] >= 1
        assert probe.calls == [t], "표 실패 = 창 안 — REST 1회"
    else:
        assert probe_marker["cap"].n >= 1, "관측기는 cap 을 peek 한다(명세 §3.5)"
        trace = [r for r in caplog.records
                 if r.levelno == logging.DEBUG and _OBSERVE_FAILED in r.getMessage()]
        assert trace, (
            f"관측기 내부 예외는 흡수 + {_OBSERVE_FAILED} debug 흔적 — "
            f"records={[r.getMessage()[:80] for r in caplog.records][-10:]}"
        )


# ===========================================================================
# E15 — 동시호가 조기 반환
# ===========================================================================
@pytest.mark.parametrize("held_fresh", [False, True])
async def test_e15_call_auction_early_return_is_untouched(monkeypatch, caplog, held_fresh):
    """W9 계약 승계 — 동시호가 조기 반환 사이클은 `is_no_feed`·REST 0."""
    from src.engine.session import session_tracker

    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe(default=1000))

    with freeze_time(_at("2026-10-05", "15:25:00"), real_asyncio=True):
        now = datetime.now(KST)
        if held_fresh:
            # HIGH(KRX 전용 보유)는 fresh, LOW 만 stale → HIGH stale 없음 → 조기 반환
            subscribed = ["003490", "005935", _LOW_NORMAL]
            _make_pool(monkeypatch, subscribed)
            _setup_ticks(monkeypatch, stale=["005935", _LOW_NORMAL], fresh=["003490"], now=now)
            positions = ["003490"]
            no_feed = ["003490", "005935"]
        else:
            subscribed = ["005935", _LOW_NORMAL]
            _make_pool(monkeypatch, subscribed)
            _setup_ticks(monkeypatch, stale=subscribed, now=now)
            positions = []
            no_feed = ["005935"]
        monkeypatch.setattr(core, "asyncio", _SleepSpy())
        spy = _patch_registry(monkeypatch, no_feed)
        monkeypatch.setattr(session_tracker, "is_call_auction_now", lambda now=None: True,
                            raising=False)
        _set_ws(())
        await core.check_and_resubscribe_stale(_make_sched(positions=positions))

    assert spy.is_no_feed_calls == [], f"is_no_feed 0 — actual={spy.is_no_feed_calls!r}"
    assert probe.calls == [], f"REST 0 — actual={probe.calls!r}"
    assert _held_rows(caplog) == []


# ===========================================================================
# E16 — 그날 cap 이 쓰였으면 REST 0
# ===========================================================================
async def test_e16_used_cap_skips_rest(monkeypatch, caplog):
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe(default=1000))
    day = "2026-10-05"
    t = "003490"
    kw = dict(subscribed=[t, _LOW_NORMAL], positions=[t], no_feed=[t], ws=(),
              stale=[t], fresh=[_LOW_NORMAL])

    with freeze_time(_at(day, "09:05:00"), real_asyncio=True) as frozen:
        await _cycle(core, monkeypatch, **kw)
        assert probe.calls == [t], (
            f"대조군 — cap 이 비어 있으면 기준 REST 1회. actual={probe.calls!r}"
        )
        now = datetime.now(KST)
        cap = core._no_feed_held_logged
        cap.should_emit(core._NO_FEED_HELD_KEY, now=now)
        cap.mark_emitted(core._NO_FEED_HELD_KEY, now=now)
        frozen.move_to(_at(day, "09:20:00"))  # 간격 경과 — cap 이 없으면 다시 읽을 시점
        probe.default = 2000
        await _cycle(core, monkeypatch, **kw)

    assert probe.calls == [t], (
        f"그날 cap 이 이미 쓰였으면 판정 전체를 건너뛴다(REST 0) — actual={probe.calls!r}"
    )


# ===========================================================================
# E17 — 프리장
# ===========================================================================
async def test_e17_pre_market_no_rest_no_alarm(monkeypatch, caplog):
    core = _core()
    caplog.set_level(logging.DEBUG)
    probe = _install_probe(monkeypatch, core, _Probe(default=1000))
    t = "003490"

    with freeze_time(_at("2026-10-05", "08:00:15"), real_asyncio=True):
        await _cycle(core, monkeypatch, subscribed=[t, _LOW_NORMAL], positions=[t],
                     no_feed=[t], ws=(), fresh=[_LOW_NORMAL])

    assert probe.calls == []
    assert _held_rows(caplog) == []


# ===========================================================================
# E18 — 진짜 seam
# ===========================================================================
@pytest.mark.real_no_feed_probe
@pytest.mark.parametrize("ret", [4321, None])
async def test_e18_real_seam_routes_through_quotation_inquire_acml_vol(monkeypatch, ret):
    import src.api.quotation as q_mod

    core = _core()
    seam = getattr(core, "_probe_krx_acml_vol", None)
    if seam is None:
        pytest.fail("명세 §5.7 — 모듈 비동기 seam `_probe_krx_acml_vol(ticker)` 미존재 (Red)")
    calls: list[tuple] = []

    async def _fake(*args, **kwargs):
        calls.append((args, kwargs))
        return ret

    monkeypatch.setattr(q_mod, "inquire_acml_vol", _fake)

    got = await seam("003490")

    assert got == ret, f"반환값 그대로 — expected={ret!r} actual={got!r}"
    assert len(calls) == 1, f"1회 호출 — actual={calls!r}"
    args, kwargs = calls[0]
    assert args[:1] == ("003490",), f"첫 인자 = ticker — actual={calls!r}"
    market = kwargs.get("market", args[1] if len(args) > 1 else None)
    assert market == "J", f'KRX 누적거래량 = market="J" 명시 — actual={calls!r}'


async def test_e18b_conftest_stub_neutralizes_seam_without_marker(monkeypatch):
    """메타 — 마커가 없는 테스트는 conftest 스텁(None)을 본다. 실 KIS 로 새지 않는다."""
    import src.api.quotation as q_mod

    core = _core()
    called: list[Any] = []

    async def _spy(*a, **k):
        called.append((a, k))
        return 1

    monkeypatch.setattr(q_mod, "inquire_acml_vol", _spy)
    seam = getattr(core, "_probe_krx_acml_vol", None)
    assert seam is not None, "conftest autouse 가 seam 자리를 None 반환 스텁으로 채운다"
    assert await seam("003490") is None
    assert called == [], "스텁은 quotation 을 부르지 않는다"
