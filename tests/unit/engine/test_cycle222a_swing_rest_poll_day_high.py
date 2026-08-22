"""cycle222-a — REST 폴 배선 + 폴 윈도우 09:05 확장 (RED).

## 배선

`_run_swing_rest_poll_once` 는 `fetch_stock_detail` 응답에서
`stck_prpr / stck_oprc / prdy_ctrt` 만 읽는다. **같은 응답에 `stck_hgpr` 가 있다.**
WS 가 stale 인 구간(REST 폴이 존재하는 이유 그 자체)에서야말로 당일 고가 관측이
가장 필요한데, 폴이 그걸 버리면 앵커 blind 는 REST 경로에서도 메워지지 않는다.

## 폴 윈도우

`SWING_REST_POLL_WINDOW_START = time(9, 30)` 인데 kojiro/donchian **매수창이
09:05~09:30** 이다. 즉 **매수 직후 25분(당일 고가가 가장 자주 찍히는 구간)의
청산 폴 보강이 0** 이었다.

검증 완료 — 이 상수는 `_swing_rest_poll_loop`(청산 폴) 한 곳에서만 쓰이고
`_swing_buy_poll_loop` 는 별도 상수를 쓴다 → **매수 행위 diff 0**.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

from src.engine import scheduler as sched_mod
from src.engine.scheduler import TradingScheduler
from src.engine.strategy_base import Position

pytestmark = pytest.mark.unit

BUY = 75_800


def _detail(*, current=80_000, open_=75_800, high: str | None = "86500", name="빙그레") -> dict:
    d = {
        "stck_prpr": str(current),
        "stck_oprc": str(open_),
        "prdy_vrss": "4200",
        "prdy_ctrt": "5.54",
        "hts_kor_isnm": name,
    }
    if high is not None:
        d["stck_hgpr"] = high
    return d


@pytest.fixture
def scanner_module():
    from src.engine import scanner
    return scanner


@pytest.fixture(autouse=True)
def _clean_scanner_caches(scanner_module):
    scanner_module.ticker_prices.clear()
    scanner_module.ticker_last_tick.clear()
    yield
    scanner_module.ticker_prices.clear()
    scanner_module.ticker_last_tick.clear()


@pytest.fixture
def scheduler():
    sched = TradingScheduler()
    sched._running = True
    ds = sched.registry.get("donchian_swing")
    assert ds is not None
    ds.config.enabled = True
    ds._scanned_tickers = []
    ds.state.positions["005180"] = Position(
        ticker="005180", buy_price=BUY, quantity=10,
        order_no="O-1", strategy_id="donchian_swing",
    )
    ds.state.positions["005180"].high_since_buy = BUY
    return sched


def _day_high_of(call) -> int:
    if "day_high" in call.kwargs:
        return call.kwargs["day_high"]
    assert len(call.args) >= 5, (
        f"폴이 day_high 를 넘기지 않았다 — args={call.args} kwargs={call.kwargs}"
    )
    return call.args[4]


# ---------------------------------------------------------------------------
# P-1 — 폴이 stck_hgpr 를 읽어 on_tick(day_high=...) 로 넘긴다
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_forwards_stck_hgpr_as_day_high(scheduler):
    async def _fetch(ticker: str) -> dict:
        return _detail(high="86500")

    on_tick = AsyncMock()
    with patch("src.engine.scheduler.fetch_stock_detail", new=_fetch), \
         patch.object(scheduler.risk_manager, "on_tick", new=on_tick):
        await scheduler._run_swing_rest_poll_once()

    on_tick.assert_awaited_once()
    assert _day_high_of(on_tick.await_args) == 86_500, (
        "REST 폴이 같은 응답에 실려 온 stck_hgpr 를 버리고 있다"
    )


@pytest.mark.asyncio
async def test_poll_day_high_zero_when_key_absent(scheduler):
    """응답에 `stck_hgpr` 가 없으면 0 (미관측) — 폴 자체는 정상 진행."""
    async def _fetch(ticker: str) -> dict:
        return _detail(high=None)

    on_tick = AsyncMock()
    with patch("src.engine.scheduler.fetch_stock_detail", new=_fetch), \
         patch.object(scheduler.risk_manager, "on_tick", new=on_tick):
        await scheduler._run_swing_rest_poll_once()

    on_tick.assert_awaited_once()
    assert _day_high_of(on_tick.await_args) == 0


@pytest.mark.asyncio
async def test_poll_day_high_zero_when_unparsable(scheduler):
    """비숫자 고가는 0 폴백 — 종목을 통째로 failed 처리하면 손절 평가가 사라진다."""
    async def _fetch(ticker: str) -> dict:
        return _detail(high="ABC")

    on_tick = AsyncMock()
    with patch("src.engine.scheduler.fetch_stock_detail", new=_fetch), \
         patch.object(scheduler.risk_manager, "on_tick", new=on_tick):
        stats = await scheduler._run_swing_rest_poll_once()

    on_tick.assert_awaited_once()
    assert _day_high_of(on_tick.await_args) == 0
    assert stats["updated"] == 1 and stats["failed"] == 0


@pytest.mark.asyncio
async def test_poll_does_not_write_high_into_ticker_prices(scheduler, scanner_module):
    """`ticker_prices` 키 집합 불변 — donchian `ext_pct` 경유 매수 행위 변경 차단."""
    async def _fetch(ticker: str) -> dict:
        return _detail(high="86500")

    with patch("src.engine.scheduler.fetch_stock_detail", new=_fetch), \
         patch.object(scheduler.risk_manager, "on_tick", new=AsyncMock()):
        await scheduler._run_swing_rest_poll_once()

    assert set(scanner_module.ticker_prices["005180"].keys()) == {
        "current_price", "open_price", "change_rate", "prdy_ctrt",
    }


# ===========================================================================
# P-2 — 폴 윈도우 09:05 확장 + **stale 감지 중립성** (F3 시정)
#
# 1차 구현은 `SWING_REST_POLL_WINDOW_START` 를 09:30 → 09:05 로 그냥 내렸다.
# 그런데 `_run_swing_rest_poll_once` 는 폴한 종목마다 `ticker_last_tick[t] = now`
# 를 찍고, stale watcher 는 (`stale_watcher_core.py:215` / `:450`) **그 dict 하나만**
# 보고 강제 재구독을 판정한다.
#
# 09:30~15:20 은 기존 트레이드오프였지만, 확장 구간 09:05~09:30 은
# **개장 러시 = OPSP0008 구독 거부가 실제로 터진 구간**이다. 여기서 REST 가
# `ticker_last_tick` 을 갱신하면 08-19 사고의 blind 종목들이 "신선해 보여"
# 재구독이 안 걸린다 — **이 사이클이 잡으려던 blind 를 스스로 은폐**한다.
#
# 채택안 = (a) 변형: 확장 구간은 **보유 종목만** 폴하고 `ticker_last_tick` 을
# **중립**으로 둔다(on_tick 이 안에서 찍는 것까지 원복). 09:30~15:20 기본 동작은
# 인자 기본값으로 **byte 동일** — 안 (b)처럼 기존 구간의 stale 판정을 엄격화해
# 강제 재구독/LMS 압력을 늘리지 않는다.
# ===========================================================================

def test_rest_poll_window_constants():
    """**의미 전환** — 구 케이스 `WINDOW_START == 09:05`.

    전체 폴(후보 포함 + `ticker_last_tick` 갱신) 시작은 **09:30 그대로** 두고,
    09:05~09:30 은 별도 상수의 **확장 구간**(보유 전용·stale 중립)으로 분리한다.
    상수를 그냥 내리면 stale 감지 약화가 딸려 온다(F3).
    """
    from datetime import time as _time

    assert sched_mod.SWING_REST_POLL_EARLY_START == _time(9, 5), (
        "확장 구간 시작 상수(09:05) 부재 — 매수창 25분 청산 폴 보강이 0 이다"
    )
    assert sched_mod.SWING_REST_POLL_WINDOW_START == _time(9, 30), (
        "전체 폴 시작은 09:30 유지 — 내리면 개장 러시 구간 stale 감지가 약해진다"
    )
    assert sched_mod.SWING_REST_POLL_WINDOW_END == _time(15, 20), "종료 시각 불변"
    assert sched_mod.SWING_REST_POLL_EARLY_START < sched_mod.SWING_REST_POLL_WINDOW_START


def test_run_once_signature_has_early_window_flags():
    import inspect

    sig = inspect.signature(sched_mod.TradingScheduler._run_swing_rest_poll_once)
    for name, default in (("held_only", False), ("preserve_last_tick", False)):
        assert name in sig.parameters, f"`{name}` 파라미터 부재 — 확장 구간 분리 불가"
        p = sig.parameters[name]
        assert p.kind is inspect.Parameter.KEYWORD_ONLY
        assert p.default is default, (
            f"`{name}` 기본값은 {default} 여야 한다 — 09:30~15:20 기존 동작 byte 보존"
        )


@pytest.mark.asyncio
async def test_early_window_does_not_touch_ticker_last_tick(scheduler, scanner_module):
    """**F3 핵심** — 확장 구간 폴이 `ticker_last_tick` 을 신선하게 만들면 안 된다.

    `on_tick` 내부에서도 찍히므로, 호출 전후 값을 원복해야 stale watcher 가
    blind 종목을 계속 blind 로 본다.
    """
    async def _fetch(ticker: str) -> dict:
        return _detail(high="86500")

    with patch("src.engine.scheduler.fetch_stock_detail", new=_fetch):
        await scheduler._run_swing_rest_poll_once(
            held_only=True, preserve_last_tick=True,
        )

    assert "005180" not in scanner_module.ticker_last_tick, (
        "확장 구간 REST 폴이 ticker_last_tick 을 갱신했다 — "
        "개장 러시 blind 종목이 '신선해 보여' 강제 재구독이 걸리지 않는다"
    )


@pytest.mark.asyncio
async def test_early_window_preserves_existing_ws_timestamp(scheduler, scanner_module):
    """WS 가 남긴 기존 타임스탬프도 **덮어쓰지 않고 원복**된다 (신선화 금지)."""
    from datetime import datetime, timedelta

    from src.engine.scanner import KST_TZ

    stale_ts = datetime.now(KST_TZ) - timedelta(minutes=45)
    scanner_module.ticker_last_tick["005180"] = stale_ts

    async def _fetch(ticker: str) -> dict:
        return _detail(high="86500")

    with patch("src.engine.scheduler.fetch_stock_detail", new=_fetch):
        await scheduler._run_swing_rest_poll_once(
            held_only=True, preserve_last_tick=True,
        )

    assert scanner_module.ticker_last_tick["005180"] == stale_ts, (
        "45분 blind 종목이 REST 폴 때문에 신선해졌다 — stale watcher 무력화"
    )


@pytest.mark.asyncio
async def test_early_window_still_evaluates_exit_with_day_high(scheduler):
    """stale 중립성을 지키면서도 **청산 평가 + day_high 전달**은 정상이어야 한다."""
    async def _fetch(ticker: str) -> dict:
        return _detail(high="86500")

    on_tick = AsyncMock()
    with patch("src.engine.scheduler.fetch_stock_detail", new=_fetch), \
         patch.object(scheduler.risk_manager, "on_tick", new=on_tick):
        await scheduler._run_swing_rest_poll_once(
            held_only=True, preserve_last_tick=True,
        )

    on_tick.assert_awaited_once()
    assert _day_high_of(on_tick.await_args) == 86_500


@pytest.mark.asyncio
async def test_early_window_polls_held_only(scheduler):
    """확장 구간은 **보유 종목만** 폴한다 — 개장 러시 REST 부하 + 후보 오염 차단."""
    ds = scheduler.registry.get("donchian_swing")
    ds._scanned_tickers = ["000660", "005930"]

    fetched: list[str] = []

    async def _fetch(ticker: str) -> dict:
        fetched.append(ticker)
        return _detail(high="86500")

    with patch("src.engine.scheduler.fetch_stock_detail", new=_fetch), \
         patch.object(scheduler.risk_manager, "on_tick", new=AsyncMock()):
        await scheduler._run_swing_rest_poll_once(
            held_only=True, preserve_last_tick=True,
        )

    assert fetched == ["005180"], f"보유 외 종목까지 폴했다: {fetched}"


@pytest.mark.asyncio
async def test_full_window_behaviour_unchanged(scheduler, scanner_module):
    """09:30~15:20 기본 동작 보존 — 후보 포함 + `ticker_last_tick` 갱신.

    안 (b)(REST 갱신을 별도 dict 로 분리)를 채택하면 여기가 바뀌면서
    기존 구간의 stale 판정이 엄격해져 **강제 재구독 증가 = LMS 압력**이 된다.
    """
    ds = scheduler.registry.get("donchian_swing")
    ds._scanned_tickers = ["000660"]

    fetched: list[str] = []

    async def _fetch(ticker: str) -> dict:
        fetched.append(ticker)
        return _detail(high="86500")

    with patch("src.engine.scheduler.fetch_stock_detail", new=_fetch), \
         patch.object(scheduler.risk_manager, "on_tick", new=AsyncMock()):
        await scheduler._run_swing_rest_poll_once()

    assert set(fetched) == {"000660", "005180"}, "기본 폴은 후보 ∪ 보유 전체"
    assert "005180" in scanner_module.ticker_last_tick
    assert "000660" in scanner_module.ticker_last_tick


class _StopLoop(Exception):
    pass


def _loop_probe(scheduler, limit: int = 40):
    """루프를 1사이클만 돌리고 호출 인자를 캡처한다."""
    captured: list[dict] = []
    real_sleep = asyncio.sleep
    n = {"i": 0}

    async def _fast_sleep(_secs, *a, **k):
        n["i"] += 1
        if n["i"] > limit:
            raise _StopLoop
        await real_sleep(0)

    async def _once(**kwargs):
        captured.append(kwargs)
        scheduler._running = False
        return {}

    return captured, _fast_sleep, _once


@pytest.mark.asyncio
@freeze_time("2026-08-19 09:10:00")
async def test_loop_runs_early_window_in_stale_neutral_mode(scheduler):
    """09:10 = 확장 구간 → 실행되되 **held_only + preserve_last_tick** 으로."""
    captured, _fast_sleep, _once = _loop_probe(scheduler)

    with patch.object(scheduler, "_run_swing_rest_poll_once", new=_once), \
         patch("asyncio.sleep", new=_fast_sleep):
        try:
            await scheduler._swing_rest_poll_loop()
        except _StopLoop:
            pass

    assert captured, (
        "09:10 은 매수 직후 고가가 가장 자주 찍히는 구간인데 청산 폴이 실행되지 않았다"
    )
    assert captured[0] == {"held_only": True, "preserve_last_tick": True}, (
        f"확장 구간은 stale 중립 모드여야 한다: {captured[0]}"
    )


@pytest.mark.asyncio
@freeze_time("2026-08-19 10:00:00")
async def test_loop_runs_full_mode_after_0930(scheduler):
    """09:30 이후는 기존 전체 폴 모드 (기본값)."""
    captured, _fast_sleep, _once = _loop_probe(scheduler)

    with patch.object(scheduler, "_run_swing_rest_poll_once", new=_once), \
         patch("asyncio.sleep", new=_fast_sleep):
        try:
            await scheduler._swing_rest_poll_loop()
        except _StopLoop:
            pass

    assert captured
    assert captured[0] == {"held_only": False, "preserve_last_tick": False}, (
        f"09:30 이후 기존 동작이 바뀌었다: {captured[0]}"
    )


@pytest.mark.asyncio
@freeze_time("2026-08-19 08:50:00")
async def test_loop_still_skipped_before_window(scheduler):
    """08:50(프리장)은 여전히 윈도우 밖 — 확장은 09:05 까지만."""
    captured, _fast_sleep, _once = _loop_probe(scheduler, limit=20)

    with patch.object(scheduler, "_run_swing_rest_poll_once", new=_once), \
         patch("asyncio.sleep", new=_fast_sleep):
        try:
            await scheduler._swing_rest_poll_loop()
        except _StopLoop:
            pass

    assert not captured, "08:50 프리장에 청산 폴이 돌면 왜곡 시세로 평가된다"


def test_buy_poll_window_untouched():
    """매수 폴은 별도 상수 — 매수 행위 diff 0 계약."""
    import inspect

    src = inspect.getsource(sched_mod.TradingScheduler._swing_buy_poll_loop)
    for const in ("SWING_REST_POLL_WINDOW_START", "SWING_REST_POLL_EARLY_START"):
        assert const not in src, (
            f"매수 폴루프가 청산 폴 상수 `{const}` 를 읽으면 확장이 매수 행위를 바꾼다"
        )
