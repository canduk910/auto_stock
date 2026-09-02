"""NXT 프리장(08:00~09:00) 청산 **평가** 보류 게이트 — 회귀 가드.

## 배경 (2026-08-06 사용자 결정)

30일 APBK0918 매도 거부 전수(8건, 고유 6케이스) = momentum 익일매도 2 +
donchian 멀티데이 손절 3 + LTV 당일 손절 1. 사용자 판정:

  "전일 상한가 종목도 NXT 프리장에서 시초가가 이상하게 하한가로 형성되는
   경우가 많다 — 프리장 매도는 의도와 다르다"

지금까지는 KIS 거부(시장가 불가)가 **우연히** 가드 역할을 해 전부 09:00 KRX
에서 체결됐다. 이 게이트는 그 우연을 정식 경로로 만든다.

## 왜 "주문 보류"가 아니라 "평가 보류"인가

주문만 보류하면 프리장 왜곡 틱이 손절을 발화시키고, 그 신호가 09:00 에
**실제 매도로 전환**된다 — KRX 시가가 정상이어도 팔린다. 평가 자체를 보류하면
09:00 부터 정상 시세로 재평가되어 진짜 이탈만 매도된다. 같은 이유로
`high_since_buy` 갱신도 보류한다(왜곡 고가가 트레일링 앵커를 오염 → 조기 청산).

## 설계 계약

- 판정 소스 = `session_tracker.active` (스케줄러 이벤트 구동) **OR** 시각 폴백
  `boards_at(risk._now_kst().time())` (cycle238, 2026-09-02).
  ⚠️ **"wall-clock 아님" 계약은 cycle238 에서 폐기됐다** — `active` 의 유일한
  기록자 `SessionTracker.tick()` 이 30초 주기라 `boards_at(07:59:xx)`=∅ 스냅샷이
  08:00:00~08:00:29 동안 살아남아 게이트가 fail-open 으로 열렸다(실측: 08:00:00
  청산 발화 → 08:00:29 deferred, 매도 주문이 나가 APBK0918 거부). 시각 폴백은
  같은 `_BOARD_SCHEDULE` 표를 fresh 로 읽어 그 창을 닫는다.
  결정성은 이제 루트 `tests/conftest.py` 의 autouse `_pin_pre_market_clock`
  (`risk._now_kst` 를 MAIN 구간으로 핀)이 담보한다 — 아래 빈 frozenset 케이스가
  시간대와 무관하게 '평가 유지'인 근거도 그 픽스처다. 게이트 자체의 회귀 가드는
  `test_cycle238_pre_market_clock_gate.py`.
- 조건 = `PRE_NXT ∈ active AND MAIN ∉ active` (매수측 PR-F 와 동일 membership).
- 화이트리스트 = `_PRE_MARKET_EXIT_EVAL_STRATEGIES = {"long_tail_volatility"}`
  — LTV 는 프리장 매매가 설계 의도(상한가 익일 청산 + 프리장 매수).
  ⚠️ `tradable_boards` 로 게이팅 금지 — 그 설정은 매수 전용(사이클 38)이라
  매수 목적의 보드 변경이 청산 규약을 조용히 바꾸는 커플링을 만든다.
- fail-open — session 판정 불가 시 평가 유지(손절 정지가 더 위험).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.risk import RiskManager
from src.engine.session import MarketBoard, session_tracker
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


class _SpyStrategy(StrategyBase):
    def __init__(self, config, exit_signal: Signal = Signal.STOP_LOSS):
        super().__init__(config)
        self.exit_calls: list = []
        self._exit_signal = exit_signal

    async def prepare(self):
        pass

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        self.exit_calls.append((ticker, current_price))
        return self._exit_signal

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0


@pytest.fixture
def _active(monkeypatch):
    def _set(boards):
        monkeypatch.setattr(session_tracker, "_active", frozenset(boards))
    return _set


def _rig(strategy_id: str, *, exit_signal=Signal.STOP_LOSS):
    reg = StrategyRegistry()
    strat = _SpyStrategy(
        StrategyConfig(strategy_id=strategy_id, name=strategy_id, weight=0.1),
        exit_signal=exit_signal,
    )
    reg.register(strat)
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=70_000, quantity=1, order_no="O",
        strategy_id=strategy_id,
    )
    oe = MagicMock()
    oe._selling = set()
    oe.execute_sell = AsyncMock()
    rm = RiskManager(reg, oe)
    return rm, strat, oe


# ---------------------------------------------------------------------------
# G-1 — PRE_NXT 단독: 평가·고점 갱신·매도 전부 보류
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sid", ["momentum", "donchian_swing", "kojiro", "vcp_breakout", "bull_flag_breakout"],
)
async def test_pre_nxt_defers_exit_eval_for_gated_strategies(sid, _active):
    _active({MarketBoard.PRE_NXT})
    rm, strat, oe = _rig(sid)
    await rm.on_tick("005930", 60_000, 60_000, 0.0)   # 왜곡된 프리장 급락 틱
    assert strat.exit_calls == [], "프리장엔 청산 평가 자체가 보류돼야 한다"
    oe.execute_sell.assert_not_awaited()


@pytest.mark.asyncio
async def test_pre_nxt_does_not_pollute_high_since_buy(_active):
    """프리장 왜곡 고가가 트레일링 앵커를 올리면 09:00 이후 조기 청산된다."""
    _active({MarketBoard.PRE_NXT})
    rm, strat, _ = _rig("kojiro", exit_signal=Signal.NONE)
    pos = strat.state.positions["005930"]
    await rm.on_tick("005930", 95_000, 95_000, 0.0)   # 왜곡된 프리장 급등 틱
    assert pos.high_since_buy == 70_000, "프리장 틱으로 고점이 오염되면 안 된다"


# ---------------------------------------------------------------------------
# G-2 — 화이트리스트: LTV 는 프리장에도 정상 평가 (설계 의도)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ltv_still_evaluates_exits_in_pre_nxt(_active):
    _active({MarketBoard.PRE_NXT})
    rm, strat, oe = _rig("long_tail_volatility")
    await rm.on_tick("005930", 60_000, 60_000, 0.0)
    assert len(strat.exit_calls) == 1, "LTV 는 프리장 매매가 설계 의도 — 보류 금지"
    oe.execute_sell.assert_awaited_once()


def test_whitelist_constant_is_ltv_only():
    """화이트리스트 확장은 의도적 변경이어야 한다 — 상수 고정."""
    from src.engine import risk as risk_mod

    assert risk_mod._PRE_MARKET_EXIT_EVAL_STRATEGIES == frozenset(
        {"long_tail_volatility"}
    )


def test_gate_does_not_read_tradable_boards():
    """사이클 38 doctrine 보존 — `tradable_boards` 는 매수 전용.

    게이트가 그걸 읽으면 매수 목적의 보드 변경이 청산 규약을 조용히 바꾼다.
    """
    import inspect

    from src.engine import risk as risk_mod

    src = inspect.getsource(risk_mod.RiskManager._defers_pre_market_exit)
    assert "tradable_boards" not in src


# ---------------------------------------------------------------------------
# G-3 — 게이트 해제 조건
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boards",
    [set(), {MarketBoard.MAIN}, {MarketBoard.PRE_NXT, MarketBoard.MAIN},
     {MarketBoard.POST_NXT}],
    ids=["empty(test-default)", "main", "pre+main(09:00 boundary)", "post_nxt"],
)
async def test_gate_off_outside_pre_nxt_only_window(boards, _active):
    """MAIN 활성·애프터·빈 세션(단위 테스트 기본)에서는 기존 평가 그대로.

    빈 세션 케이스가 곧 '기존 on_tick 테스트 11개 파일 무영향' 계약이다.
    """
    _active(boards)
    rm, strat, oe = _rig("donchian_swing")
    await rm.on_tick("005930", 60_000, 60_000, 0.0)
    assert len(strat.exit_calls) == 1
    oe.execute_sell.assert_awaited_once()


# ---------------------------------------------------------------------------
# G-4 — 관찰성: 보류 발생 시 1회/전략/일 로그
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_defer_emits_once_per_strategy_per_day(_active, caplog):
    import logging

    _active({MarketBoard.PRE_NXT})
    rm, _, _ = _rig("kojiro")
    with caplog.at_level(logging.INFO):
        for _ in range(5):
            await rm.on_tick("005930", 60_000, 60_000, 0.0)
    hits = [r for r in caplog.records if "pre_market_exit_deferred" in r.getMessage()]
    assert len(hits) == 1, "매 틱 로그 폭주 금지 — 1회/전략/일"
