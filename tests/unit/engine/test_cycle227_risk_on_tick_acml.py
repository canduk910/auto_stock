"""cycle227 W2 (RED) — `RiskManager.on_tick` 이 `acml_vol` 을 수용해 관측 모듈에 기록.

## 계약 (`_workspace/red/cycle227_acml_vol_stage0_spec.md` W2)

- 시그니처: `*, day_high: int = 0, acml_vol: int = -1` (둘 다 **키워드 전용**).
- `acml_vol >= 0` 일 때만 `tick_volume.record_acml_vol(ticker, acml_vol)` (dict assign 1회).
- **`ticker_prices` 4키 불변** — `current_price`/`open_price`/`change_rate`/`prdy_ctrt`.
  `acml_vol` 키 대입은 **절대 금지**다:

  > `donchian_swing` 이 같은 dict 에서
  > `daily_high = max(stck_hgpr, high_price, current_price, open_price)` 를 읽어
  > `ext_pct` 과열 가드를 계산한다. 키가 채워지면 **donchian 매수 행위가 바뀐다.**

  이 파일의 `test_..._ticker_prices_has_exactly_four_keys` 는 Red 시점부터 통과하는
  **보존 검증**이며, Green 구현이 편의상 dict 에 주입하면 그때 FAIL 로 잡는 것이 존재 이유다.
- 그 외 on_tick 행위 변경 0 (기존 4-positional 호출 · `day_high` 앵커 계약 유지).
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

from src.engine import tick_volume
from src.engine.risk import RiskManager
from src.engine.session import MarketBoard, session_tracker
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

TICKER = "005180"
BUY = 75_800


class _NoopStrategy(StrategyBase):
    async def prepare(self):
        pass

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """관측 모듈 격리 + `ticker_prices` 는 매 테스트 빈 dict (프로덕션 실제 상태 재현)."""
    tick_volume.reset_for_test()
    monkeypatch.setattr("src.engine.scanner.ticker_prices", {}, raising=False)
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))
    yield
    tick_volume.reset_for_test()


def _rig(*, held: bool = False):
    reg = StrategyRegistry()
    strat = _NoopStrategy(StrategyConfig(strategy_id="kojiro", name="kojiro", weight=0.1))
    reg.register(strat)
    if held:
        pos = Position(
            ticker=TICKER, buy_price=BUY, quantity=1, order_no="O", strategy_id="kojiro",
        )
        pos.high_since_buy = BUY
        strat.state.positions[TICKER] = pos
    oe = MagicMock()
    oe._selling = set()
    oe.execute_sell = AsyncMock()
    oe.execute_buy = AsyncMock()
    return RiskManager(reg, oe), strat


# ===========================================================================
# W2-1 — 시그니처 계약
# ===========================================================================

def test_on_tick_exposes_keyword_only_acml_vol_with_default_minus_one():
    sig = inspect.signature(RiskManager.on_tick)
    assert "acml_vol" in sig.parameters, (
        "on_tick 이 `acml_vol` 을 받지 않는다 — payload 에 실려 온 누적거래량이 "
        "handler 에서 파싱돼도 갈 곳이 없다"
    )
    p = sig.parameters["acml_vol"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY, (
        "acml_vol 은 키워드 전용이어야 한다 (기존 4-positional 호출부 호환)"
    )
    assert p.default == -1, (
        f"기본값이 {p.default!r} 이다. `-1` 이어야 한다 — 기본값 `0` 은 "
        "'미수신'을 '거래량 0' 으로 위장해 P0 결함을 그대로 재생산한다"
    )


# ===========================================================================
# W2-2 / W2-3 / W2-4 / W2-5 — 기록 조건
# ===========================================================================

@pytest.mark.asyncio
@freeze_time("2026-08-25 09:30:00")
async def test_on_tick_when_acml_vol_positive_then_recorded():
    """W2-2 — 관측값이 `tick_volume` 에 기록된다."""
    rm, _ = _rig()
    await rm.on_tick(TICKER, 80_000, BUY, 0.0, acml_vol=1_234_567)
    assert tick_volume.get_observed_acml_vol(TICKER) == 1_234_567


@pytest.mark.asyncio
@freeze_time("2026-08-25 09:30:00")
async def test_on_tick_when_acml_vol_zero_then_recorded():
    """W2-5 — `0` 은 유효 관측이므로 기록된다 (미수신과 타입 분리)."""
    rm, _ = _rig()
    await rm.on_tick(TICKER, 80_000, BUY, 0.0, acml_vol=0)
    assert tick_volume.get_observed_acml_vol(TICKER) == 0


@pytest.mark.asyncio
@freeze_time("2026-08-25 09:30:00")
async def test_on_tick_when_acml_vol_omitted_then_not_recorded():
    """W2-3 — 기본값(-1) = 미수신 → 기록하지 않는다."""
    rm, _ = _rig()
    await rm.on_tick(TICKER, 80_000, BUY, 0.0)
    assert tick_volume.get_observed_acml_vol(TICKER) is None


@pytest.mark.asyncio
@freeze_time("2026-08-25 09:30:00")
async def test_on_tick_when_acml_vol_sentinel_then_not_recorded():
    """W2-4 — `-1` 명시 전달도 미기록."""
    rm, _ = _rig()
    await rm.on_tick(TICKER, 80_000, BUY, 0.0, acml_vol=-1)
    assert tick_volume.get_observed_acml_vol(TICKER) is None


@pytest.mark.asyncio
@freeze_time("2026-08-25 09:30:00")
async def test_on_tick_when_sentinel_after_valid_then_keeps_previous():
    """짧은 payload 한 건이 정상 관측을 지우면 안 된다."""
    rm, _ = _rig()
    await rm.on_tick(TICKER, 80_000, BUY, 0.0, acml_vol=500_000)
    await rm.on_tick(TICKER, 80_100, BUY, 0.0, acml_vol=-1)
    assert tick_volume.get_observed_acml_vol(TICKER) == 500_000


# ===========================================================================
# W2-6 — `ticker_prices` 4키 불변 (보존 검증 · donchian 커플링 영구 차단)
# ===========================================================================

@pytest.mark.asyncio
@freeze_time("2026-08-25 09:30:00")
async def test_on_tick_when_acml_vol_given_then_ticker_prices_has_exactly_four_keys():
    """W2-6 — `acml_vol` 을 흘리면서도 `ticker_prices` 는 4키 그대로여야 한다.

    donchian 이 이 dict 에서 고가 키를 읽어 `ext_pct` 과열 가드를 켠다 —
    키가 하나라도 늘면 **donchian 매수 행위가 바뀐다**(Stage 0 위반).
    """
    from src.engine import scanner as _scanner

    rm, _ = _rig()
    await rm.on_tick(TICKER, 80_000, BUY, 0.0, day_high=86_500, acml_vol=1_234_567)

    entry = _scanner.ticker_prices[TICKER]
    assert set(entry) == {"current_price", "open_price", "change_rate", "prdy_ctrt"}, (
        f"ticker_prices 키가 바뀌었다: {sorted(entry)}. "
        "acml_vol/day_high 는 **함수 인자로만** 흘러야 한다 (donchian ext_pct 커플링)"
    )
    assert "acml_vol" not in entry


# ===========================================================================
# W2-7 / W2-8 — 기존 행위 불변
# ===========================================================================

@pytest.mark.asyncio
@freeze_time("2026-08-25 09:30:00")
async def test_legacy_positional_call_still_works():
    """W2-7 — 기존 4-positional 호출부는 그대로 동작한다."""
    rm, strat = _rig(held=True)
    await rm.on_tick(TICKER, 80_000, BUY, 0.0)
    assert strat.state.positions[TICKER].high_since_buy == 80_000


@pytest.mark.asyncio
@freeze_time("2026-08-25 09:30:00")
async def test_day_high_anchor_unchanged_when_acml_vol_also_passed():
    """W2-8 — 두 키워드를 동시에 받아도 cycle222-a 앵커 계약(baseline)이 그대로다.

    첫 관측은 baseline 설정만 하고 채택하지 않는다 → 앵커는 현재가에 머문다.
    """
    rm, strat = _rig(held=True)
    await rm.on_tick(TICKER, 78_000, BUY, 0.0, day_high=86_500, acml_vol=1_000)
    assert strat.state.positions[TICKER].high_since_buy == 78_000, (
        "acml_vol 배관이 day_high baseline 계약을 흔들었다 (cycle222-a F1 회귀)"
    )
