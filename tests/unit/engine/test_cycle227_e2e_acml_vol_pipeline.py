"""cycle227 W7 (RED) — **P0 를 처음부터 잡았을 바로 그 테스트**.

## 이 파일의 존재 이유

`bull_flag_breakout` / `vcp_breakout` 은 전 기간 체결 0건이었다. 원인은
매수 최종 관문이 `scanner.ticker_prices[t]["acml_vol"]` 를 읽는데
**그 키를 쓰는 코드가 전체 소스에 없었다**는 것이다 — 즉 소비처만 있고 **대입부가 없었다.**

그런데 회귀 테스트는 통과하고 있었다. `test_bull_flag_breakout.py` 등 3파일이
`ticker_prices` 에 `acml_vol` 을 **손으로 주입**해서 게이트를 통과시켰기 때문이다.
그 주입이 프로덕션에는 존재하지 않는 배관을 테스트 안에서만 가공해 준 것이다.

⇒ **계층을 잘라 놓고 각 계층을 mock 으로 만족시키면 "연결이 없다"는 결함은 영원히 안 잡힌다.**

이 파일은 그래서 mock 을 쓰지 않는다. WebSocket payload 문자열 하나를 넣고
**프로덕션 코드만으로** `handler._handle_tick` → `RiskManager.on_tick` →
`tick_volume` 까지 흐르는지 본다. 이 테스트가 사이클 227 이전에 있었다면
P0-1 은 첫날 잡혔다.

## 검증하는 두 문장

1. payload `[13] ACML_VOL` 이 **관측 모듈에 실제로 도착한다** (대입부 존재).
2. 그 과정에서 `ticker_prices` 에는 **끝내 `acml_vol` 이 들어가지 않는다**
   (donchian `ext_pct` 커플링 차단 — 고치는 김에 다른 전략을 망가뜨리지 않는다).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

from src.engine import tick_volume
from src.engine.risk import RiskManager
from src.engine.session import MarketBoard, session_tracker
from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.realtime import handler

pytestmark = pytest.mark.unit

TICKER = "001450"
ACML_VOL = 3_628_183          # 2026-08-25 BFB 실측 임계 상한대
_FIELD_COUNT = 46             # KIS 정본 `ccnl_total` / H0UNCNT0


class _NoopStrategy(StrategyBase):
    async def prepare(self):
        pass

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0


def _payload(*, acml_vol: str = str(ACML_VOL)) -> str:
    f = ["0"] * _FIELD_COUNT
    f[0] = TICKER
    f[1] = "093000"
    f[2] = "50800"       # 현재가
    f[3] = "2"
    f[4] = "200"
    f[5] = "0.40"
    f[6] = "50700"
    f[7] = "50600"       # 시가
    f[8] = "50900"       # 고가
    f[9] = "50500"
    f[13] = acml_vol     # 누적거래량 ACML_VOL
    f[14] = "184000000000"
    f[24] = "090000"
    f[27] = "093000"     # HGPR_HOUR (MAIN 창)
    f[33] = "20260825"
    return "^".join(f)


@pytest.fixture
def pipeline(monkeypatch):
    """프로덕션 `RiskManager.on_tick` 을 실제 tick handler 로 등록한다 (mock 없음)."""
    tick_volume.reset_for_test()
    monkeypatch.setattr("src.engine.scanner.ticker_prices", {}, raising=False)
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))

    reg = StrategyRegistry()
    reg.register(_NoopStrategy(StrategyConfig(strategy_id="kojiro", name="kojiro", weight=0.1)))
    oe = MagicMock()
    oe._selling = set()
    oe.execute_sell = AsyncMock()
    oe.execute_buy = AsyncMock()
    rm = RiskManager(reg, oe)

    original = handler._on_tick
    handler.register_tick_handler(rm.on_tick)
    handler._silent_drop_count.clear()
    yield rm
    handler._on_tick = original
    handler._silent_drop_count.clear()
    tick_volume.reset_for_test()


@pytest.mark.asyncio
@freeze_time("2026-08-25 01:00:00")
async def test_ws_payload_reaches_tick_volume_through_production_code(pipeline):
    """E2E-1 — payload `[13]` → handler → risk → `tick_volume`. 중간 대역 0.

    실패 = 배관 어딘가가 끊겨 있다는 뜻이고, 그게 정확히 P0-1 의 상태였다.
    """
    await handler._handle_tick(_payload())

    got = tick_volume.get_observed_acml_vol(TICKER)
    assert got == ACML_VOL, (
        f"WS payload 의 누적거래량이 관측 모듈에 도달하지 않았다 (got={got!r}). "
        "소비처만 있고 대입부가 없는 상태 = P0-1 그 자체다"
    )


@pytest.mark.asyncio
@freeze_time("2026-08-25 01:00:00")
async def test_pipeline_never_writes_acml_vol_into_ticker_prices(pipeline):
    """E2E-2 — 같은 경로에서 `ticker_prices` 는 끝내 4키 그대로다.

    donchian 이 이 dict 의 고가 키를 읽어 `ext_pct` 과열 가드를 계산한다 —
    BFB/VCP 를 고치면서 donchian 매수 행위를 바꾸면 시정이 아니라 사고다.
    """
    from src.engine import scanner as _scanner

    await handler._handle_tick(_payload())

    entry = _scanner.ticker_prices[TICKER]
    assert "acml_vol" not in entry, f"ticker_prices 오염: {sorted(entry)}"
    assert set(entry) == {"current_price", "open_price", "change_rate", "prdy_ctrt"}


@pytest.mark.asyncio
@freeze_time("2026-08-25 01:00:00")
async def test_pipeline_when_acml_vol_unparsable_then_no_observation_and_tick_survives(
    pipeline,
):
    """미수신은 `None` 으로 남고 틱은 산다 — sentinel 이 `0` 이면 이 구별이 사라진다."""
    from src.engine import scanner as _scanner

    await handler._handle_tick(_payload(acml_vol="ABC"))

    assert tick_volume.get_observed_acml_vol(TICKER) is None
    assert _scanner.ticker_prices[TICKER]["current_price"] == 50_800, (
        "거래량 파싱 실패가 틱 전체를 죽였다"
    )
    assert handler._silent_drop_count.get(TICKER) is None
