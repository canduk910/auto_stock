"""donchian_swing 일중 시세 REST 폴링 보강 (2026-05-15, 결함 B).

배경:
    donchian_swing 은 멀티데이 보유 + ATR×2 Chandelier 트레일링 + 하드 -7% 손절
    전략이라 일중 시세에 100% 의존한다. 2026-05-15 운영 중 tick_coverage 가
    ratio 11~45% 로 종일 떨어지고 stale_watcher 도 6회 retry 초과 후 skip →
    **보유·후보 시세 누락 → 손절 평가 불가** 운영 위험. UI(ScanMonitor 최종 후보)
    에서도 종목명/현재가 빈칸 다수 보고.

해결:
    WebSocket 을 보강하는 REST 폴링 레이어 추가. WS 정상이면 그대로, stale 이면
    REST 가 메꿈. KIS Rate Limit(20req/s) 대비 1req/s 수준이라 안전 마진 충분.

본 테스트는 `_run_swing_rest_poll_once()` 단일 사이클 메서드를 검증한다.
loop 시간 가드(09:30~15:20)는 별도 케이스로 분리.

Red 의도:
    결함 상태(메서드 미구현)에선 `AttributeError` 또는 ticker_prices 비어 있어 fail.
    Green 후: 후보·보유 시세 갱신 + risk.on_tick 호출 + 손절 트리거 회로 모두 동작.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.engine.scheduler import TradingScheduler
from src.engine.strategy_base import Position

pytestmark = pytest.mark.unit
KST = ZoneInfo("Asia/Seoul")


def _build_detail(
    *, current: int, open_: int | None = None, prdy_close: int | None = None,
    name: str = "",
) -> dict:
    """KIS `FHKST01010100` 응답 output 형식의 dict 빌더.

    필요한 키만 채움. 폴링 로직이 사용하는 필드:
    - stck_prpr (현재가) / stck_oprc (시가) / prdy_vrss (전일대비) / prdy_ctrt (전일대비율)
    - hts_kor_isnm (종목명) — UI 보강용
    """
    o = open_ if open_ is not None else current
    pc = prdy_close if prdy_close is not None else current
    diff = current - pc
    rate = round(diff / pc * 100, 2) if pc else 0.0
    return {
        "stck_prpr": str(current),
        "stck_oprc": str(o),
        "prdy_vrss": str(diff),
        "prdy_ctrt": f"{rate:.2f}",
        "hts_kor_isnm": name,
    }


@pytest.fixture
def scanner_module():
    from src.engine import scanner
    return scanner


@pytest.fixture(autouse=True)
def _clean_scanner_caches(scanner_module):
    """각 테스트 격리 — 모듈 글로벌 dict 초기화."""
    scanner_module.ticker_prices.clear()
    scanner_module.ticker_last_tick.clear()
    # ticker_names 는 STATIC_TICKER_NAMES 가 모듈 import 시 미리 채워둠 → 보존
    yield
    scanner_module.ticker_prices.clear()
    scanner_module.ticker_last_tick.clear()


@pytest.fixture
def scheduler(monkeypatch):
    """donchian_swing 후보·보유 fixture 가 깔린 TradingScheduler."""
    sched = TradingScheduler()
    # `_running=True` 필수 — `_run_swing_rest_poll_once` 안의 종목 루프 가드 통과.
    # 운영에서는 `start()` 진입 직후 True 로 세팅되지만 테스트는 단위 단계라 직접 세팅.
    sched._running = True
    ds = sched.registry.get("donchian_swing")
    assert ds is not None
    # prepare 우회 — 직접 `_scanned_tickers` 세팅
    ds._scanned_tickers = ["005930", "000660", "035720"]
    ds.config.enabled = True
    # 1종목 보유 (손절 평가 대상)
    ds.state.positions["005930"] = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="O-1", strategy_id="donchian_swing", buy_date="2026-05-12",
    )
    ds.state.positions["005930"].high_since_buy = 70000
    # pending_buys 1종목 (체결가 추정 대상)
    ds.state.pending_buys.add("009150")
    return sched


# ---------------------------------------------------------------------------
# Case 1: 후보·보유·pending 합집합 ticker_prices 갱신
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_once_updates_ticker_prices_for_all_buckets(scheduler, scanner_module):
    """`_scanned_tickers` + `state.positions` + `state.pending_buys` 합집합 모든 종목의
    ticker_prices 가 KIS 응답 기반으로 갱신되어야 한다.

    결함 상태(폴링 미구현)에선 ticker_prices 비어있어 fail.
    """
    responses = {
        "005930": _build_detail(current=68000, open_=69500, prdy_close=70000, name="삼성전자"),
        "000660": _build_detail(current=130000, open_=132000, prdy_close=131000, name="SK하이닉스"),
        "035720": _build_detail(current=45000, open_=44500, prdy_close=44000, name="카카오"),
        "009150": _build_detail(current=85000, open_=84000, prdy_close=83000, name="삼성전기"),
    }

    async def _mock_fetch(ticker: str) -> dict:
        return responses.get(ticker, {})

    with patch("src.engine.scheduler.fetch_stock_detail", new=_mock_fetch), \
         patch.object(scheduler.risk_manager, "on_tick", new=AsyncMock()):
        await scheduler._run_swing_rest_poll_once()

    # 4종목 모두 갱신
    for t, resp in responses.items():
        assert t in scanner_module.ticker_prices, f"{t} ticker_prices 미갱신"
        info = scanner_module.ticker_prices[t]
        assert info["current_price"] == int(resp["stck_prpr"])
        assert info["open_price"] == int(resp["stck_oprc"])


# ---------------------------------------------------------------------------
# Case 2: ticker_last_tick touch — stale_watcher 협업
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_once_touches_ticker_last_tick(scheduler, scanner_module):
    """`ticker_last_tick[ticker] = datetime.now(KST_TZ)` 가 호출되어
    stale_watcher 가 자연스럽게 fresh 로 인식해야 한다."""
    responses = {
        t: _build_detail(current=10000) for t in ("005930", "000660", "035720", "009150")
    }

    async def _mock_fetch(ticker: str) -> dict:
        return responses.get(ticker, {})

    with patch("src.engine.scheduler.fetch_stock_detail", new=_mock_fetch), \
         patch.object(scheduler.risk_manager, "on_tick", new=AsyncMock()):
        await scheduler._run_swing_rest_poll_once()

    for t in responses:
        assert t in scanner_module.ticker_last_tick, f"{t} ticker_last_tick 미갱신"
        # KST aware datetime 이어야 stale_watcher 가 일관 비교 가능
        ts = scanner_module.ticker_last_tick[t]
        assert ts.tzinfo is not None


# ---------------------------------------------------------------------------
# Case 3: 보유 종목에 한해 RiskManager.on_tick 호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_once_calls_risk_on_tick_for_held_only(scheduler, scanner_module):
    """폴링 후 보유 종목 005930 에 대해서만 RiskManager.on_tick 이 호출되어야 함.

    `_scanned_tickers` 후보(000660, 035720) 와 pending_buys(009150) 는 호출 대상 아님 —
    매수 평가는 `_swing_buy_poll_loop`(09:05~09:30) 전용 + 시세 갱신 + 보유 평가만
    이 loop 의 책임이라는 불변식 보존.
    """
    responses = {
        t: _build_detail(current=68000, open_=69500, prdy_close=70000)
        for t in ("005930", "000660", "035720", "009150")
    }

    async def _mock_fetch(ticker: str) -> dict:
        return responses.get(ticker, {})

    on_tick_mock = AsyncMock()
    with patch("src.engine.scheduler.fetch_stock_detail", new=_mock_fetch), \
         patch.object(scheduler.risk_manager, "on_tick", new=on_tick_mock):
        await scheduler._run_swing_rest_poll_once()

    # 보유 종목만 호출 — 후보·pending 은 미호출
    held_tickers = {call.args[0] for call in on_tick_mock.call_args_list}
    assert held_tickers == {"005930"}, (
        f"on_tick 은 보유 종목(005930)에 한해 호출되어야 함. 실제 호출 ticker: {held_tickers}"
    )


# ---------------------------------------------------------------------------
# Case 4: 손절 트리거 회로 — 매수가 -7% 미만 응답 시 execute_sell 발화
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_once_triggers_stop_loss_via_risk_on_tick(scheduler, scanner_module):
    """보유 005930(매수가 70000) 의 시세를 -8% 인 64400 으로 mock → 폴링 후
    RiskManager.on_tick 이 호출되고 기존 트레일링/하드 손절 코드 경로로
    OrderEngine.execute_sell(STOP_LOSS) 가 트리거되어야 한다.

    별도 신규 청산 경로 신설 금지 — `risk.py` 의 check_exit_signal → execute_sell
    체인 그대로 재사용.
    """
    from src.engine.strategy_base import Signal as _Signal

    # 005930 시세를 매수가 70000 의 -8% 인 64400 으로 mock (하드 -7% 미달)
    responses = {
        "005930": _build_detail(current=64400, open_=68000, prdy_close=70000),
        "000660": _build_detail(current=130000),
        "035720": _build_detail(current=45000),
        "009150": _build_detail(current=85000),
    }

    async def _mock_fetch(ticker: str) -> dict:
        return responses.get(ticker, {})

    execute_sell_mock = AsyncMock()
    # 폴링이 risk_manager.on_tick 을 실제 호출하면 risk 내부에서
    # donchian.check_exit_signal → STOP_LOSS → order_engine.execute_sell 까지 흐름.
    # execute_sell 만 mock — 그 외 risk/strategy 경로는 실제 코드 사용.
    with patch("src.engine.scheduler.fetch_stock_detail", new=_mock_fetch), \
         patch.object(scheduler.order_engine, "execute_sell", new=execute_sell_mock):
        await scheduler._run_swing_rest_poll_once()

    # execute_sell 이 005930 에 대해 STOP_LOSS 신호로 호출되어야 함
    assert execute_sell_mock.await_count >= 1, (
        "보유 종목 -8% 시세 입수 후 execute_sell(STOP_LOSS) 가 트리거되지 않음 — "
        "손절 평가 회로 미동작 (운영 사고 재발 위험)"
    )
    # 첫 호출 인자에 005930 포함
    first_call = execute_sell_mock.await_args_list[0]
    assert first_call.args[0] == "005930"
    # 두 번째 인자가 STOP_LOSS 신호인지 확인
    assert first_call.args[1] == _Signal.STOP_LOSS, (
        f"STOP_LOSS 가 아닌 신호로 매도 호출됨: {first_call.args[1]}"
    )


# ---------------------------------------------------------------------------
# Case 5: KIS 종목별 실패는 격리 — 다른 종목 진행
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_once_isolates_per_ticker_failure(scheduler, scanner_module):
    """특정 종목 fetch 실패해도 나머지 종목은 정상 갱신되어야 한다.
    KIS 5xx/timeout 이 일시적일 때 사이클 전체가 망가지지 않도록 격리."""
    async def _mock_fetch(ticker: str) -> dict:
        if ticker == "000660":
            raise RuntimeError("KIS 5xx simulated")
        return _build_detail(current=10000)

    with patch("src.engine.scheduler.fetch_stock_detail", new=_mock_fetch), \
         patch.object(scheduler.risk_manager, "on_tick", new=AsyncMock()):
        await scheduler._run_swing_rest_poll_once()

    # 실패한 종목만 미갱신, 나머지는 갱신
    assert "000660" not in scanner_module.ticker_prices
    for t in ("005930", "035720", "009150"):
        assert t in scanner_module.ticker_prices, f"{t} 갱신 누락 — 실패 격리 미동작"
