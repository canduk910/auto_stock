"""donchian_swing — Pull 기반 매수 평가 (G안, 2026-05-12).

배경: donchian_swing 은 일봉 전략이라 실시간 tick 이 구조적 낭비. 50~150개 후보를
WebSocket 으로 구독해 momentum/breakout 시세 슬롯을 잠식하던 결함을 차단.

새 동작: `_swing_buy_poll_loop()` 가 09:05~09:30 KST 1분 주기로 `fetch_stock_detail` 폴링.
- 보유 종목은 그대로 WebSocket(positions HIGH 그룹) 으로 구독 → 청산은 on_tick
- 매수만 Pull (1분 주기 1회)

검증 사항:
1. 09:05~09:30 사이 1사이클 발화 → execute_buy 1회 호출
2. _bought_today 가드 — 같은 종목 중복 매수 차단
3. is_ticker_blocked_for_buy=True → skip
4. stck_oprc/stck_prpr=0 응답 → skip
5. INFO 로그 `[swing_poll] candidates=N filtered=M bought=K elapsed=...`
6. 09:30 이후 task 종료
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import contextlib
import datetime as _datetime_module

import pytest

from src.engine.scheduler import TradingScheduler
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


@contextlib.contextmanager
def freeze_time(iso: str, tick=False):
    """freezegun 대안 — `datetime.now` 만 patch.

    freezegun 은 monotonic 까지 freeze 해서 asyncio.sleep 이 절대 진행 안 함.
    이 테스트에서는 매수 윈도우 시간 가드만 평가하면 되므로 datetime.now 만 patch.

    `iso` 는 KST 시각으로 해석한다(테스트 가독성).
    - `now()` (naive): base 그대로 (기존 호환 — naive datetime 사용 코드 회귀 방지)
    - `now(tz=KST)`: base 에 KST tzinfo 부착 (KST 시각이라 변환 불필요)
    - `now(tz=other)`: KST aware 로 부착 후 해당 tz 로 astimezone
    """
    base_naive = _datetime_module.datetime.fromisoformat(iso)
    _KST_TZ = _datetime_module.timezone(_datetime_module.timedelta(hours=9))
    base_kst = base_naive.replace(tzinfo=_KST_TZ)

    class _FrozenDateTime(_datetime_module.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return base_naive
            if tz is _KST_TZ or getattr(tz, "utcoffset", lambda _x: None)(None) == _KST_TZ.utcoffset(None):
                return base_kst
            return base_kst.astimezone(tz)

    real_dt = _datetime_module.datetime
    _datetime_module.datetime = _FrozenDateTime
    # 모듈 안에서 `from datetime import datetime` 한 곳에 영향 전파를 위해 직접 patch.
    # scheduler / strategies 모두 모듈 임포트 시점에 datetime 을 캡쳐했으므로 동시 모킹 필요.
    from src.engine import scheduler as _sched
    from src.engine.strategies import donchian_swing as _ds

    sched_dt = getattr(_sched, "datetime", None)
    ds_dt = getattr(_ds, "datetime", None)
    if sched_dt is real_dt:
        _sched.datetime = _FrozenDateTime
    if ds_dt is real_dt:
        _ds.datetime = _FrozenDateTime
    try:
        yield
    finally:
        _datetime_module.datetime = real_dt
        if sched_dt is real_dt:
            _sched.datetime = real_dt
        if ds_dt is real_dt:
            _ds.datetime = real_dt


class _FakeDonchianSwing(StrategyBase):
    """donchian_swing 의 Pull 폴링 인터페이스만 모킹한 더블."""

    def __init__(self, scanned: list[str], buy_results: dict[str, Signal] | None = None):
        cfg = StrategyConfig(
            strategy_id="donchian_swing", name="DS", weight=0.2, enabled=True,
        )
        super().__init__(cfg)
        self._scanned_tickers = list(scanned)
        self._bought_today: set[str] = set()
        self._buy_results = buy_results or {}
        self._candidates: dict[str, dict] = {t: {"prev_close": 10000, "atr": 100, "ema60": 9500, "donchian_high": 11000} for t in scanned}

    async def prepare(self) -> None:
        pass

    def get_scanned_tickers(self) -> list[str]:
        return list(self._scanned_tickers)

    def check_buy_signal(self, ticker: str, current_price: int, open_price: int) -> Signal:
        if ticker in self._bought_today:
            return Signal.NONE
        result = self._buy_results.get(ticker, Signal.NONE)
        if result == Signal.BUY:
            self._bought_today.add(ticker)
        return result

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int) -> int:
        return 1


def _make_scheduler(scanned: list[str], buy_results: dict[str, Signal]):
    """TradingScheduler 인스턴스 + donchian_swing 더블 + order_engine mock."""
    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = StrategyRegistry()
    sched._pending_next_day_clear = set()
    sched._running = True

    strategy = _FakeDonchianSwing(scanned, buy_results)
    sched.registry.register(strategy)

    sched.order_engine = MagicMock()
    sched.order_engine.execute_buy = AsyncMock()

    return sched, strategy


# ---------------------------------------------------------------------------
# Case 1: 09:05~09:30 사이 1사이클 발화 + execute_buy 호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_swing_poll_executes_buy_in_window():
    """09:05:30 시점에 BUY 신호 종목이 execute_buy 호출되어야 한다."""
    sched, strategy = _make_scheduler(
        scanned=["005930"], buy_results={"005930": Signal.BUY},
    )

    fake_detail = {"stck_prpr": "60000", "stck_oprc": "59000"}

    with freeze_time("2026-05-12 09:05:30"), \
         patch("src.api.condition.fetch_stock_detail", new=AsyncMock(return_value=fake_detail)):
        # 1사이클만 발화 후 종료 시키기 위해 _running=False 토글하는 헬퍼 task
        async def _stopper():
            await asyncio.sleep(0.3)
            sched._running = False
        stop_task = asyncio.create_task(_stopper())
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=5.0)
        await stop_task

    # execute_buy 가 정확히 1회 호출
    assert sched.order_engine.execute_buy.call_count == 1
    call = sched.order_engine.execute_buy.call_args
    # 위치 인자: (ticker, current_price, strategy)
    args = call.args
    assert args[0] == "005930"
    assert args[1] == 60000  # stck_prpr
    assert args[2] is strategy


# ---------------------------------------------------------------------------
# Case 2: _bought_today 중복 가드 — 동일 종목 한 사이클 후 두 번째 사이클 skip
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_swing_poll_bought_today_prevents_duplicate():
    """첫 사이클에서 매수한 종목은 두 번째 사이클에서 다시 매수하지 않는다."""
    sched, strategy = _make_scheduler(
        scanned=["005930"], buy_results={"005930": Signal.BUY},
    )

    fake_detail = {"stck_prpr": "60000", "stck_oprc": "59000"}

    # _bought_today 에 이미 있으면 폴링이 skip 해야 함 — 그 사이클은 execute_buy 호출 0회
    strategy._bought_today.add("005930")

    with freeze_time("2026-05-12 09:10:00"), \
         patch("src.api.condition.fetch_stock_detail", new=AsyncMock(return_value=fake_detail)):
        async def _stopper():
            await asyncio.sleep(0.3)
            sched._running = False
        stop_task = asyncio.create_task(_stopper())
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=5.0)
        await stop_task

    assert sched.order_engine.execute_buy.call_count == 0, "_bought_today 가드로 skip 되어야 함"


# ---------------------------------------------------------------------------
# Case 3: is_ticker_blocked_for_buy=True → skip
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_swing_poll_skips_blocked_tickers():
    sched, strategy = _make_scheduler(
        scanned=["005930"], buy_results={"005930": Signal.BUY},
    )

    # registry.is_ticker_blocked_for_buy 가 True 반환하도록 패치
    sched.registry.is_ticker_blocked_for_buy = MagicMock(return_value=True)

    fake_detail = {"stck_prpr": "60000", "stck_oprc": "59000"}
    with freeze_time("2026-05-12 09:10:00"), \
         patch("src.api.condition.fetch_stock_detail", new=AsyncMock(return_value=fake_detail)):
        async def _stopper():
            await asyncio.sleep(0.3)
            sched._running = False
        stop_task = asyncio.create_task(_stopper())
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=5.0)
        await stop_task

    assert sched.order_engine.execute_buy.call_count == 0, "is_ticker_blocked_for_buy=True → skip"


# ---------------------------------------------------------------------------
# Case 4: stck_oprc/stck_prpr=0 → skip
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_swing_poll_skips_zero_prices():
    """fetch_stock_detail 가 0 또는 빈 값 반환 시 해당 종목 skip."""
    sched, strategy = _make_scheduler(
        scanned=["005930", "000660"],
        buy_results={"005930": Signal.BUY, "000660": Signal.BUY},
    )

    def _detail_side_effect(ticker):
        if ticker == "005930":
            return {"stck_prpr": "0", "stck_oprc": "0"}
        return {"stck_prpr": "180000", "stck_oprc": "179000"}

    with freeze_time("2026-05-12 09:10:00"), \
         patch("src.api.condition.fetch_stock_detail", new=AsyncMock(side_effect=_detail_side_effect)):
        async def _stopper():
            await asyncio.sleep(0.3)
            sched._running = False
        stop_task = asyncio.create_task(_stopper())
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=5.0)
        await stop_task

    # 005930 skip, 000660 만 매수
    calls = sched.order_engine.execute_buy.call_args_list
    assert len(calls) == 1
    assert calls[0].args[0] == "000660"


# ---------------------------------------------------------------------------
# Case 5: [swing_poll] INFO 로그 형식
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_swing_poll_emits_info_log(caplog):
    sched, strategy = _make_scheduler(
        scanned=["005930", "000660"],
        buy_results={"005930": Signal.BUY, "000660": Signal.NONE},
    )
    fake_detail = {"stck_prpr": "60000", "stck_oprc": "59000"}

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    with freeze_time("2026-05-12 09:10:00"), \
         patch("src.api.condition.fetch_stock_detail", new=AsyncMock(return_value=fake_detail)):
        async def _stopper():
            await asyncio.sleep(0.3)
            sched._running = False
        stop_task = asyncio.create_task(_stopper())
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=5.0)
        await stop_task

    log_text = "\n".join(r.message for r in caplog.records)
    assert "[swing_poll]" in log_text
    assert "candidates=2" in log_text  # 전체 후보 2개
    assert "bought=" in log_text  # 매수 발생 수
    assert "elapsed=" in log_text


# ---------------------------------------------------------------------------
# Case 6: 09:30:01 이후 task 즉시 종료
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_swing_poll_terminates_after_window():
    """09:30 초과 시 더 이상 폴링하지 않고 즉시 종료한다."""
    sched, strategy = _make_scheduler(
        scanned=["005930"], buy_results={"005930": Signal.BUY},
    )
    fake_detail = {"stck_prpr": "60000", "stck_oprc": "59000"}

    with freeze_time("2026-05-12 09:31:00"), \
         patch("src.api.condition.fetch_stock_detail", new=AsyncMock(return_value=fake_detail)):
        # 명시적 stopper 없이도 즉시 종료해야 함 (5s 안에)
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=5.0)

    # 매수 없음 — 윈도우 밖이므로
    assert sched.order_engine.execute_buy.call_count == 0


# ---------------------------------------------------------------------------
# Case 7: disabled donchian_swing → poll 즉시 종료
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_swing_poll_skips_when_strategy_disabled():
    sched, strategy = _make_scheduler(
        scanned=["005930"], buy_results={"005930": Signal.BUY},
    )
    strategy.config.enabled = False

    fake_detail = {"stck_prpr": "60000", "stck_oprc": "59000"}
    with freeze_time("2026-05-12 09:10:00"), \
         patch("src.api.condition.fetch_stock_detail", new=AsyncMock(return_value=fake_detail)):
        async def _stopper():
            await asyncio.sleep(0.3)
            sched._running = False
        stop_task = asyncio.create_task(_stopper())
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=5.0)
        await stop_task

    assert sched.order_engine.execute_buy.call_count == 0


# ---------------------------------------------------------------------------
# Case 8 (Codex P1): execute_buy 호출 직후 즉시 WS subscribe 보장
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_swing_poll_subscribes_ticker_after_buy_signal():
    """매수 신호 발사 직후 동일 ticker 를 WebSocket TICK 구독에 즉시 추가해야 한다.

    안전 불변식: donchian_swing 보유 종목은 ATR 트레일링/-7% 하드 손절 평가가 필수.
    매수 직후 다음 5분 _scan_loop 통합 구독까지 시세 무수신 구간 차단.
    `bypass_limit=True` 로 MAX_SUBSCRIPTIONS=41 한도 무시 (positions HIGH 절대 보장 규약).
    """
    sched, strategy = _make_scheduler(
        scanned=["005930"], buy_results={"005930": Signal.BUY},
    )

    fake_detail = {"stck_prpr": "60000", "stck_oprc": "59000"}

    with freeze_time("2026-05-12 09:05:30"), \
         patch("src.api.condition.fetch_stock_detail", new=AsyncMock(return_value=fake_detail)), \
         patch("src.engine.scanner.kis_ws.subscribe", new=AsyncMock()) as mock_subscribe:
        async def _stopper():
            await asyncio.sleep(0.3)
            sched._running = False
        stop_task = asyncio.create_task(_stopper())
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=5.0)
        await stop_task

    # execute_buy 1회 호출
    assert sched.order_engine.execute_buy.call_count == 1
    # WS subscribe 가 H0UNCNT0 + ticker + bypass_limit=True 로 호출되었는지
    sub_calls = mock_subscribe.call_args_list
    matching = [
        c for c in sub_calls
        if c.args[0] == "H0UNCNT0" and c.args[1] == "005930"
        and c.kwargs.get("bypass_limit") is True
    ]
    assert len(matching) >= 1, (
        f"매수 직후 H0UNCNT0/005930 bypass_limit=True subscribe 1회 이상 호출 필요. "
        f"실제 호출={sub_calls}"
    )


@pytest.mark.asyncio
async def test_swing_poll_subscribe_failure_does_not_crash_loop():
    """subscribe 가 예외를 던져도 매수 사이클 자체는 정상 종료.

    매수는 이미 처리됐고, 시세 구독 실패는 다음 _scan_loop 5분 사이클에서 회복.
    """
    sched, strategy = _make_scheduler(
        scanned=["005930", "000660"],
        buy_results={"005930": Signal.BUY, "000660": Signal.BUY},
    )

    fake_detail = {"stck_prpr": "60000", "stck_oprc": "59000"}

    async def _flaky_subscribe(*args, **kwargs):
        raise RuntimeError("WebSocket 일시 단절")

    with freeze_time("2026-05-12 09:05:30"), \
         patch("src.api.condition.fetch_stock_detail", new=AsyncMock(return_value=fake_detail)), \
         patch("src.engine.scanner.kis_ws.subscribe", new=AsyncMock(side_effect=_flaky_subscribe)):
        async def _stopper():
            await asyncio.sleep(0.3)
            sched._running = False
        stop_task = asyncio.create_task(_stopper())
        # asyncio.wait_for 가 예외 없이 정상 종료해야 함
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=5.0)
        await stop_task

    # subscribe 가 raise 해도 execute_buy 는 두 종목 모두 호출되었어야 함
    assert sched.order_engine.execute_buy.call_count == 2, (
        "subscribe 실패가 매수 사이클을 깨면 안 됨"
    )


# ---------------------------------------------------------------------------
# Case 9 (Copilot P2): KST 윈도우 가드 검증 — UTC 서버에서도 KST 기준 동작
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_swing_poll_window_uses_kst_not_naive():
    """KST 08:50 (윈도우 진입 전) — execute_buy 호출 0회.

    `freeze_time` 헬퍼는 ISO 를 KST 시각으로 취급. `datetime.now(KST_TZ)` 가 정상 동작하면
    08:50 은 BUY_WINDOW_START(09:05) 이전이므로 매수 0회.

    naive `datetime.now()` 였다면 UTC 서버에서는 시스템 UTC 시각으로 비교해 윈도우가
    어긋났을 것 — KST aware 비교를 강제해야 한다.
    """
    sched, strategy = _make_scheduler(
        scanned=["005930"], buy_results={"005930": Signal.BUY},
    )
    fake_detail = {"stck_prpr": "60000", "stck_oprc": "59000"}

    with freeze_time("2026-05-13 08:50:00"), \
         patch("src.api.condition.fetch_stock_detail", new=AsyncMock(return_value=fake_detail)):
        async def _stopper():
            await asyncio.sleep(0.3)
            sched._running = False
        stop_task = asyncio.create_task(_stopper())
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=5.0)
        await stop_task

    assert sched.order_engine.execute_buy.call_count == 0, (
        "KST 08:50 은 윈도우 진입 전 — execute_buy 호출되면 안 됨"
    )


@pytest.mark.asyncio
async def test_swing_poll_window_kst_active_when_utc_pre_midnight():
    """KST 09:10 (윈도우 안) — execute_buy 1회 호출.

    `_datetime.now(KST_TZ)` 사용 시 정상 매수, naive `datetime.now()` 라면 UTC 서버에서
    KST 09:10 == UTC 00:10 → time 비교가 윈도우 밖으로 잘못 평가될 위험.
    """
    sched, strategy = _make_scheduler(
        scanned=["005930"], buy_results={"005930": Signal.BUY},
    )
    fake_detail = {"stck_prpr": "60000", "stck_oprc": "59000"}

    with freeze_time("2026-05-13 09:10:00"), \
         patch("src.api.condition.fetch_stock_detail", new=AsyncMock(return_value=fake_detail)):
        async def _stopper():
            await asyncio.sleep(0.3)
            sched._running = False
        stop_task = asyncio.create_task(_stopper())
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=5.0)
        await stop_task

    assert sched.order_engine.execute_buy.call_count == 1, (
        "KST 09:10 은 윈도우 안 — execute_buy 1회 호출되어야 함"
    )
