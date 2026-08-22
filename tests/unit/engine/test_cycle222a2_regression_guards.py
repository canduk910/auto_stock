"""cycle222-a2 — 앵커 baseline 을 **매수 당일로 한정**할 때 열리는 사각의 비회귀 가드.

## 왜 재설계인가

cycle222-a 1차 구현은 `_day_high_since_entry` 가 **매일** baseline 을 다시 잡았다 —
그날 첫 관측은 기록만 하고 미채택, 이후 초과분만 채택. 사용자가 반대한 지점:

> "당일로 쪼개버리면 기간중 최고점에서 야금야금 하락했을 때 익절을 못한다는 이야기아니야?"

조사로 확정된 사실:

- **매일 baseline 이 버리는 것 = 오늘의 blind 고점**이다. 멀티데이 고점 자체는 매일 아침
  `_apply_high_since_buy_from_candles`(`buy_date < 봉일 < today`)가 일봉으로 복구한다.
  그러나 **오늘 봉은 미확정이라 그 경로가 의도적으로 배제**하고, on_tick 이 올린 값은
  DB 에 안 쓰이므로 **오늘의 blind 고점은 아무도 복구하지 않는다.** 갭은 실재한다.
- 1차 구현이 매일 baseline 을 다시 잡은 이유는 **F2 방어**였다 — 통합 채널
  `H0UNCNT0` 의 당일고가에 08:00~09:00 NXT 프리장이 누적된다. 이 주장은 라이브
  실측으로 확증됐다(000250 삼천당제약 2026-08-21: MAIN 구간 통합 틱의 일-스코프
  시가 182,800 vs 같은 날 KRX 일봉 O/H/L/C 177,500/177,500/166,000/168,700 —
  182,800 은 KRX 당일고가를 +3.0% 초과하고 **전일 종가와 정확히 일치**하는 NXT
  프리장 기준가 체결이다. 즉 통합 채널의 일-스코프 필드는 09:00 에 리셋되지 않는다).

## 재설계 = 방어선의 재배치 (이 파일이 지키는 계약)

프리장 배제를 **시간축이 아니라 소스에서** 한다:

- **A. `realtime/handler.py`** — KIS 정본 `ccnl_total`(H0UNCNT0) 46컬럼의
  `[27] HGPR_HOUR`(최고가 시간, HHMMSS)를 읽어 KRX 정규장 창(`090000 <= h <= 153000`,
  cycle222-a3 F-A 로 상한을 `_BOARD_SCHEDULE` MAIN 15:40 → 정규장 종료 15:30 포함으로
  하향) 밖이면 `day_high` 를 **0(미관측)으로 강등**한다. 파싱 실패도 0. **틱은 절대 버리지 않는다**
  (사이클 88 G-REJECT-1 재연결 오발화 차단).
- **B. `engine/risk.py`** — baseline 게이트를 **매수 당일에만** 적용한다.
  `buy_date < today` 면 하루 전체가 진입 이후 구간이므로 첫 관측부터 즉시 채택한다.

## 이 재배치가 만드는 사각 — 이 파일의 존재 이유

B 때문에 **D+1 이후 포지션에는 risk 계층의 baseline 방어가 없다.** 프리장 오염을
막는 것은 이제 A(핸들러 필터) 하나뿐이고, 그 하나가 무너지면:

1. **F2 재발** — 09:00 첫 MAIN 틱이 프리장 누적 고가를 실어 오면 **즉시** 앵커에 박힌다.
   (1차 구현에서는 baseline 이 흡수했지만, 이제는 흡수해 줄 baseline 이 없다.)
2. **cycle142 무효화** — `scheduler.py:1461-1467` 이 LTV 익일 트레일링 기준점을
   `pos.high_since_buy = today_open` 으로 **내리는 절대 대입**(max 아님)을 한다.
   프리장 고가가 채택되면 그 시정이 매 틱 되돌려지고, 얇은 프리장 호가로 만들어진
   허깨비 고점 대비 −2% 트레일링이 09:00 즉시 발화한다.
3. **kojiro `_stop_floor` 비가역 래칫** — `breakeven_promote_atr > 0`(cycle220 활성화
   시) 이면 오염 고가 한 번이 손절선을 **매수가로 영구 승격**시킨다. `_stop_floor` 는
   tighten-only 라 같은 프로세스에서 되돌아가지 않는다(F6).

그래서 이 파일은 **handler → on_tick 통합 경로**로 검증한다. 조사 결과 이 경로를
end-to-end 로 확인하는 테스트가 기존에 **0건**이었다 — 두 계층을 각자 단위 테스트만
하면 "핸들러가 거른다"와 "risk 가 거른다"를 서로에게 미루는 사각이 남는다.

각 시나리오는 **거부(프리장)와 채택(MAIN)을 한 쌍으로** 검증한다. 거부만 확인하면
"day_high 를 통째로 무시" 하는 구현도 통과하는 공허한 가드가 되기 때문이다.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

from src.engine.risk import RiskManager
from src.engine.session import MarketBoard, session_tracker
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.realtime import handler as handler_mod

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]

# UTC 01:00 = KST 10:00 (MAIN 구간). 날짜 경계 비결정성 제거용 — `_day_high_since_entry`
# 가 받는 `today` 는 `on_tick` 안에서 `datetime.now(KST).date()` 로 계산되므로,
# 테스트가 만든 `buy_date` 와 같은 시계 위에 있어야 한다.
_FROZEN_UTC = "2026-08-21 01:00:00"
_TODAY = date(2026, 8, 21)
_YESTERDAY = date(2026, 8, 20)

TICKER = "005180"

# KRX MAIN 창 경계 (`session._BOARD_SCHEDULE` MAIN 09:00~15:40 배타)
HOUR_PRE_MARKET = "081500"     # NXT 프리장 — 배제 대상
HOUR_MAIN_OPEN = "090000"      # MAIN 시작 (포함 경계)
HOUR_MAIN = "101500"
HOUR_POST_MARKET = "160500"    # NXT 애프터 — 배제 대상


# ---------------------------------------------------------------------------
# KIS 정본 payload 빌더 (ccnl_total / H0UNCNT0, 46 컬럼)
# ---------------------------------------------------------------------------
# 0-index 검증된 배치:
#   [7]STCK_OPRC [8]STCK_HGPR [9]STCK_LWPR ... [24]OPRC_HOUR
#   [25]OPRC_VRSS_PRPR_SIGN [26]OPRC_VRSS_PRPR **[27]HGPR_HOUR**
#   [28]HGPR_VRSS_PRPR_SIGN ... [33]BSOP_DATE
# 현행 handler 는 `len(fields) < 10` 가드 뒤 [0]~[9] 만 읽어 [27] 을 버린다.
_FIELD_COUNT = 46


def _payload(
    *,
    ticker: str = TICKER,
    current: int,
    open_: int,
    high: int,
    hgpr_hour: str,
    low: int = 0,
) -> str:
    f = ["0"] * _FIELD_COUNT
    f[0] = ticker
    f[1] = "100000"          # STCK_CNTG_HOUR
    f[2] = str(current)      # STCK_PRPR
    f[3] = "2"
    f[4] = "0"
    f[5] = "0.00"
    f[6] = str(current)
    f[7] = str(open_)        # STCK_OPRC
    f[8] = str(high)         # STCK_HGPR
    f[9] = str(low or open_)  # STCK_LWPR
    f[24] = "090000"         # OPRC_HOUR
    f[27] = hgpr_hour        # HGPR_HOUR ← 이번 재설계의 판별자
    f[33] = "20260821"       # BSOP_DATE
    return "^".join(f)


# ---------------------------------------------------------------------------
# 공통 지그 — handler → RiskManager.on_tick 통합 배선
# ---------------------------------------------------------------------------

class _SpyStrategy(StrategyBase):
    """청산/매수 판단을 하지 않는 관찰용 전략 — 앵커 갱신만 노출한다."""

    async def prepare(self):
        pass

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0


class _Wire:
    """`handler._handle_tick` 부터 앵커까지의 통합 경로 + 경계 관측치."""

    def __init__(self, rm, strategy, pos, order_engine):
        self.rm = rm
        self.strategy = strategy
        self.pos = pos
        self.oe = order_engine
        # on_tick 이 실제로 **수신한** day_high — 핸들러 필터가 살아 있는지의 직접 증거.
        self.seen: list[int] = []

    async def send(self, *, current: int, open_: int, high: int, hgpr_hour: str) -> None:
        await handler_mod._handle_tick(
            _payload(current=current, open_=open_, high=high, hgpr_hour=hgpr_hour),
        )

    @property
    def last_day_high(self) -> int:
        assert self.seen, "on_tick 이 호출되지 않았다 (틱이 통째로 drop 됐다)"
        return self.seen[-1]


@pytest.fixture
def _active(monkeypatch):
    """`session_tracker.active` 는 이벤트 구동 — wall-clock 이 아니라 결정적이다."""
    def _set(boards):
        monkeypatch.setattr(session_tracker, "_active", frozenset(boards))
    return _set


@pytest.fixture
def wire(monkeypatch):
    """전략/포지션을 받아 handler 배선을 마친 `_Wire` 를 만드는 팩토리.

    handler 의 모듈 전역 `_on_tick` 을 복원하고 `ticker_prices`/`_silent_drop_count`
    오염도 정리한다(다른 파일과 공유되는 전역이라 필수).
    """
    from src.engine.scanner import ticker_prices

    original = handler_mod._on_tick
    handler_mod._silent_drop_count.clear()
    ticker_prices.pop(TICKER, None)
    made: list[_Wire] = []

    def _build(strategy, pos, *, strategy_id: str | None = None) -> _Wire:
        reg = StrategyRegistry()
        reg.register(strategy)
        strategy.state.positions[pos.ticker] = pos
        oe = MagicMock()
        oe._selling = set()
        oe.execute_sell = AsyncMock()
        oe.execute_buy = AsyncMock()
        rm = RiskManager(reg, oe)
        w = _Wire(rm, strategy, pos, oe)

        async def _relay(ticker, current_price, open_price, change_rate, **kw):
            w.seen.append(int(kw.get("day_high", 0) or 0))
            await rm.on_tick(ticker, current_price, open_price, change_rate, **kw)

        handler_mod.register_tick_handler(_relay)
        made.append(w)
        return w

    yield _build

    handler_mod._on_tick = original
    handler_mod._silent_drop_count.clear()
    ticker_prices.pop(TICKER, None)
    made.clear()


def _spy_wire(build, strategy_id: str, *, buy_price: int, buy_date: date,
              high_since_buy: int | None = None) -> _Wire:
    strat = _SpyStrategy(
        StrategyConfig(strategy_id=strategy_id, name=strategy_id, weight=0.2),
    )
    pos = Position(
        ticker=TICKER, buy_price=buy_price, quantity=10, order_no="O-1",
        strategy_id=strategy_id, buy_date=buy_date,
    )
    if high_since_buy is not None:
        pos.high_since_buy = high_since_buy
    return build(strat, pos)


# ===========================================================================
# R-1 (F2, HIGH) — D+1 포지션: 프리장 시각 고가는 09:00 첫 MAIN 틱에도 앵커에 못 박힌다
#
# 재설계 B 로 D+1 포지션에는 risk 계층 baseline 이 **없다**. 프리장 오염을 막는 것은
# 핸들러 필터(A) 하나뿐이므로, 이 경로는 통합으로 검증해야 의미가 있다.
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("strategy_id", ["kojiro", "donchian_swing"])
async def test_r1_premarket_hour_high_is_not_anchored_for_multiday_position(
    strategy_id, wire, _active,
):
    """프리장 시각(`HGPR_HOUR=081500`) 고가는 **소스에서** 0 으로 강등된다.

    실측 근거(000250, 2026-08-21): 통합 채널의 일-스코프 필드는 09:00 에 리셋되지
    않아 전일 종가 기준의 NXT 프리장 체결이 KRX 당일고가를 3% 넘게 초과한 채로
    MAIN 구간 틱에 계속 실려 온다. `_adopts_day_high()` 는 **시계만** 보므로 이걸
    구분하지 못한다 — 판별자는 payload 안의 `[27] HGPR_HOUR` 다.
    """
    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _spy_wire(wire, strategy_id, buy_price=75_800, buy_date=_YESTERDAY)

        await w.send(current=76_500, open_=76_000, high=86_500,
                     hgpr_hour=HOUR_PRE_MARKET)

    assert w.last_day_high == 0, (
        f"프리장 시각 고가가 on_tick 까지 흘러왔다 (day_high={w.last_day_high}). "
        "재설계 A 는 시간축이 아니라 **소스**(HGPR_HOUR)에서 걸러야 한다 — "
        "D+1 포지션에는 이를 흡수해 줄 baseline 이 더 이상 없다"
    )
    assert w.pos.high_since_buy == 76_500, (
        f"프리장 누적 고가가 앵커에 박혔다 (앵커={w.pos.high_since_buy}). "
        "F2 가 baseline 제거와 함께 되살아났다"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy_id", ["kojiro", "donchian_swing"])
async def test_r1b_main_hour_high_is_adopted_immediately_for_multiday_position(
    strategy_id, wire, _active,
):
    """**같은 쌍의 채택 측** — MAIN 시각 고가는 D+1 포지션에서 첫 관측부터 채택된다.

    이게 없으면 "day_high 를 통째로 무시" 하는 구현도 R-1 을 통과한다.
    그리고 이 문장이야말로 사용자가 요구한 것 — 오늘 09:00~09:58 blind 동안 찍힌
    고점이 **첫 관측 하나로** 복구돼야 매일 baseline 이 버리던 갭이 닫힌다.
    """
    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _spy_wire(wire, strategy_id, buy_price=75_800, buy_date=_YESTERDAY)

        # 09:00~09:58 blind. 09:58 도착한 단 하나의 관측이 앵커를 복구한다.
        await w.send(current=80_000, open_=76_000, high=86_500, hgpr_hour="094500")

    assert w.last_day_high == 86_500
    assert w.pos.high_since_buy == 86_500, (
        f"D+1 포지션의 MAIN 고가가 채택되지 않았다 (앵커={w.pos.high_since_buy}). "
        "매일 baseline 을 다시 잡으면 **오늘의 blind 고점**이 매일 버려진다 — "
        "오늘 봉은 미확정이라 `_apply_high_since_buy_from_candles` 도 복구하지 않는다"
    )


@pytest.mark.asyncio
async def test_r1c_premarket_then_main_sequence_keeps_only_main_high(wire, _active):
    """실제 하루의 순서 — 프리장 누적치는 끝까지 배제되고 MAIN 고가만 앵커가 된다.

    통합 채널의 `STCK_HGPR` 는 하루 내 단조 비감소라 프리장 스파이크(86,500)가
    MAIN 고가(79,000)보다 계속 크게 남는다. 즉 "더 큰 값이니 채택" 은 성립하지
    않으며, **어느 창에서 찍힌 고가인지**만이 유일한 판별자다.
    """
    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _spy_wire(wire, "kojiro", buy_price=75_800, buy_date=_YESTERDAY)

        # 09:00:05 — 필드에는 프리장 스파이크가 살아 있다
        await w.send(current=76_500, open_=76_000, high=86_500,
                     hgpr_hour=HOUR_PRE_MARKET)
        assert w.pos.high_since_buy == 76_500

        # 10:15 — MAIN 에서 갱신된 진짜 고가. `[8]` 은 여전히 86,500 을 담고 있으나
        # `[27]` 이 MAIN 시각으로 바뀌면서 비로소 유효 관측이 된다.
        await w.send(current=78_000, open_=76_000, high=86_500, hgpr_hour=HOUR_MAIN)

    assert w.pos.high_since_buy == 86_500, (
        "MAIN 시각으로 확정된 당일고가는 채택돼야 한다"
    )


@pytest.mark.asyncio
async def test_r1d_main_window_boundaries(wire, _active):
    """창 경계 — `090000` 포함 / `153000` 포함 / 그 밖 배제 (cycle222-a3 F-A).

    경계를 반대로 잡으면 09:00:00 정각에 찍힌 시가 = 당일고가 케이스(개장 갭상승
    후 하락)가 통째로 유실되거나, 15:40 이후 NXT 애프터 체결이 새어 들어온다.
    """
    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _spy_wire(wire, "kojiro", buy_price=75_800, buy_date=_YESTERDAY)

        await w.send(current=80_000, open_=86_000, high=86_000,
                     hgpr_hour=HOUR_MAIN_OPEN)
        assert w.last_day_high == 86_000, "090000(포함 경계)이 배제됐다"
        assert w.pos.high_since_buy == 86_000

        await w.send(current=80_000, open_=86_000, high=99_000,
                     hgpr_hour=HOUR_POST_MARKET)
        assert w.last_day_high == 0, "NXT 애프터(160500) 고가가 새어 들어왔다"

    assert w.pos.high_since_buy == 86_000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_hour", ["", "ABC", "9999"],
    ids=["empty", "alpha", "not-hhmmss"],
)
async def test_r1e_unparsable_hour_is_fail_closed_but_never_drops_the_tick(
    bad_hour, wire, _active,
):
    """`[27]` 파싱 실패는 **fail-closed(0)** 이되 **틱은 절대 버리지 않는다**.

    고가는 부가 관측이다. 여기서 예외를 던지거나 return 으로 틱을 drop 하면
    `handler.py` 의 `except Exception: ... raise` 계약(사이클 88 G-REJECT-1 /
    사이클 102 G-CALLBACK1)에 걸려 **WebSocket 재연결이 오발화**하고, 그 사이
    손절 평가가 통째로 멈춘다 — 고가 필드 하나 때문에 치를 대가가 아니다.
    """
    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _spy_wire(wire, "kojiro", buy_price=75_800, buy_date=_YESTERDAY)

        await w.send(current=76_500, open_=76_000, high=86_500, hgpr_hour=bad_hour)

    assert len(w.seen) == 1, "고가 시각 파싱 실패로 틱 전체가 drop 됐다"
    assert w.last_day_high == 0, "판정 불가 시 미관측(0) — fail-closed"
    assert handler_mod._silent_drop_count.get(TICKER) is None, (
        "고가 시각 파싱 실패는 silent drop 카운터 대상이 아니다 (틱은 정상 처리)"
    )
    assert w.pos.high_since_buy == 76_500


# ===========================================================================
# R-2 (cycle142 비회귀, HIGH) — LTV 익일 트레일링 기준점 절대 대입 보존
#
# `scheduler.py:1461-1467` 은 갭상승 익일청산 종목에 대해
#     pos.high_since_buy = today_open        # ← max() 가 아니라 **절대 대입**
# 을 한다(사이클 142, 후성 093370 -5.91% 실측 대응). 트레일링 기준점을 오늘 시가로
# **내려서** 익일 트레일링 분기가 실제로 발화하게 만드는 것이 목적이다.
# D+1 day_high 채택은 이 시정을 무효화하면 안 된다.
# ===========================================================================

def _ltv_wire(build, *, buy_price: int, today_open: int) -> _Wire:
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy

    strat = LongTailVolatilityStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="롱테일VB", weight=0.01),
    )
    pos = Position(
        ticker=TICKER, buy_price=buy_price, quantity=10, order_no="O-1",
        strategy_id="long_tail_volatility", buy_date=_YESTERDAY,
    )
    w = build(strat, pos)
    # 전일 상한가 도달 → 익일 청산 모드
    strat._limit_up_reached.add(TICKER)
    strat._next_day_clear_pending = False
    # 사이클 142 가 09:00 시가 확정 시 수행하는 **절대 대입** 재현
    pos.high_since_buy = today_open
    return w


@pytest.mark.asyncio
async def test_r2_cycle142_anchor_reset_is_not_undone_by_premarket_high(
    wire, _active,
):
    """프리장 누적 고가가 `today_open` 기준점을 되돌리지 않는다.

    전일 상한가 종목의 NXT 프리장은 전일 종가 기준가에서 얇게 체결되어 당일고가
    필드를 130,000 까지 밀어 올린다(실측 000250 과 동형). 이 값이 채택되면
      - 사이클 142 의 `pos.high_since_buy = today_open`(121,000) 이 매 틱 무효화되고
      - `trailing_stop_rate=-2.0` 기준으로 (120,000−130,000)/130,000 = **−7.7%**
        → 09:00 첫 틱에서 곧바로 TRAILING_STOP 이 나간다.
    즉 "허깨비 고점 대비 트레일링" 이라는, 사이클 142 가 정확히 없애려던 사고다.
    """
    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _ltv_wire(wire, buy_price=100_000, today_open=121_000)

        await w.send(current=120_000, open_=121_000, high=130_000,
                     hgpr_hour=HOUR_PRE_MARKET)

    assert w.last_day_high == 0, "프리장 시각 고가가 걸러지지 않았다"
    assert w.pos.high_since_buy == 121_000, (
        f"트레일링 기준점이 프리장 고가로 되돌려졌다 (앵커={w.pos.high_since_buy}). "
        "사이클 142 의 절대 대입(today_open)은 D+1 채택보다 우선한다"
    )
    w.oe.execute_sell.assert_not_awaited()


@pytest.mark.asyncio
async def test_r2b_ltv_anchor_is_never_raised_by_day_high_even_in_main(wire, _active):
    """**의미 전환 (cycle222-a3 F-B)** — LTV 는 MAIN 고가조차 채택하지 않는다.

    ## 구 계약 (cycle222-a2)

    "09:00 이후 앵커를 올리는 것은 오직 MAIN 고가" — 프리장 130,000 은 배제하되
    MAIN 126,000 은 채택해서 blind 고점을 반영한다.

    ## 왜 뒤집혔나 — 런타임 재현된 cycle142 회귀

        OLD anchor=10200 sells=[]
        NEW anchor=10500 sells=[(005180, Signal.TRAILING_STOP, long_tail_volatility)]

    **08:00:30 근방** 스케줄러가 앵커를 `today_open` 으로 **내리는 절대 대입**을
    하는데(사이클 142, 후성 093370 −5.91%), 그 뒤 MAIN 체결이 `HGPR_HOUR` 창을
    정당하게 통과하므로 다음 틱에서 verbatim 채택돼 대입 효과를 **되돌린다**.
    창 필터는 여기서 아무 것도 못 한다 — 그 고가는 진짜 KRX 고가이기 때문이다.

    ## 시정 — 그리고 근거 정정 (cycle222-a3 G-4)

    앵커에 **외부 소유자의 절대 대입**이 있는 전략은 채택 대상에서 제외한다
    (`_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES`).

    ⚠️ 구 docstring 은 근거를 "LTV 앵커는 러닝 max 가 아니라 익일 시가 기준점이라
       blind 복구가 의미 없다" 로 적었는데 **거짓**이다 —
       `long_tail_volatility.py` 익일 트레일링 분기는 매 틱
       `max(pos.high_since_buy, current_price)` 로 러닝 max 를 돌린다.
       LTV 는 제외로 **실제 기능(놓치던 오늘 고점 관측)을 잃는다**.
       그럼에도 제외하는 결정적 근거는 **귀인** 이다 — 이번 사이클의 동기는
       kojiro/donchian 이고, LTV 청산 타이밍까지 같이 움직이면 D+1 관측에서
       원인을 가를 수 없다. 재검토 조건 = kojiro/donchian 실측 축적 후.
    """
    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _ltv_wire(wire, buy_price=100_000, today_open=121_000)

        await w.send(current=120_000, open_=121_000, high=130_000,
                     hgpr_hour=HOUR_PRE_MARKET)
        await w.send(current=124_000, open_=121_000, high=126_000,
                     hgpr_hour=HOUR_MAIN)

    assert w.last_day_high == 126_000, (
        "핸들러 창 필터가 MAIN 고가를 거르면 안 된다 — 제외는 risk 계층 책임이다"
    )
    assert w.pos.high_since_buy == 124_000, (
        f"LTV 앵커가 day_high 로 올라갔다 (앵커={w.pos.high_since_buy}). "
        "사이클 142 의 today_open 절대 대입이 무력화된다 — "
        "`_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES` 로 제외해야 한다"
    )
    # (124,000−124,000)/124,000 = 0% → 트레일링 미발화 (현재가 러닝 max 만 반영)
    w.oe.execute_sell.assert_not_awaited()


@pytest.mark.asyncio
async def test_r2d_ltv_exclusion_prevents_the_reproduced_trailing_stop(wire, _active):
    """★ F-B 프로브 재현 — 제외가 없으면 **같은 틱에서 매도**가 나간다.

    시나리오(프로브와 동일 수치): 08:00:30 근방 스케줄러가 앵커=today_open 10,000
    으로 내림 → 09:00:05 MAIN 프린트 10,500 이 창을 통과 → 다음 틱에서 채택되면
    drop = (10,200−10,500)/10,500 = −2.86% ≤ −2.0% → TRAILING_STOP.

    (cycle222-a3 G-4 — 대입 시각 서술 정정. `_next_day_task` 는
     `TIME_PRE_NXT_OPEN`=08:00 직후 생성되고 `NEXT_DAY_STABILIZE_SECS`=30 을 잔다.)
    """
    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _ltv_wire(wire, buy_price=8_000, today_open=10_000)

        await w.send(current=10_200, open_=10_000, high=10_500, hgpr_hour="090005")

    assert w.last_day_high == 10_500, "핸들러는 정당한 MAIN 고가를 그대로 넘긴다"
    assert w.pos.high_since_buy == 10_200, (
        f"앵커가 10,500 으로 올라갔다 (실제={w.pos.high_since_buy}) — "
        "cycle142 기준점이 되돌려졌다"
    )
    w.oe.execute_sell.assert_not_awaited()


def test_r2e_day_high_exclusion_is_an_explicit_constant_not_board_gated():
    """제외 판정은 **명시 상수** 로만 한다 — `tradable_boards` 게이팅 금지.

    `tradable_boards` 는 매수 진입 전용(사이클 38 명문화)이고, 매수 목적의 보드
    변경이 청산 규약을 조용히 바꾸는 커플링을 차단한다
    (`_PRE_MARKET_EXIT_EVAL_STRATEGIES` 선례와 동형).
    """
    from src.engine.risk import _DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES

    assert isinstance(_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES, frozenset)
    assert "long_tail_volatility" in _DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES


def test_r2c_scheduler_still_assigns_today_open_absolutely():
    """사이클 142 의 **절대 대입** 자체가 `max()` 로 바뀌지 않았는지 소스 확인.

    D+1 채택이 들어왔다고 이 줄을 `max(pos.high_since_buy, today_open)` 으로
    "안전하게" 바꾸면, 전일 고점이 남아 익일 트레일링이 영원히 발화하지 않는
    후성 093370 결함(6/12 매수 → 6/15 silent 미발화 −5.91%)이 그대로 재현된다.
    기준점을 **내리는 것이 의도**다.
    """
    src = (_REPO_ROOT / "src" / "engine" / "scheduler.py").read_text(encoding="utf-8")
    assert "pos.high_since_buy = today_open" in src, (
        "사이클 142 의 today_open 절대 대입이 사라졌거나 max() 로 완화됐다"
    )


# ===========================================================================
# R-3 (kojiro `_stop_floor` 비가역 래칫, HIGH) — cycle220 활성화 대비
#
# `breakeven_promote_atr` 는 현재 0.0 다크런치라 비활성이지만, cycle220 활성화
# (N=10 도달 시 DB UPDATE) 순간 살아난다. `_stop_floor` 는 tighten-only 라
# 한 번 매수가로 승격되면 **그 프로세스 생애 동안 되돌아가지 않는다**(F6) —
# 오염 고가 한 틱의 대가가 영구적이다.
# ===========================================================================

def _kojiro_wire(build, *, buy_price: int, atr: float, be_mult: float) -> _Wire:
    from src.engine.strategies.kojiro import KojiroStrategy

    strat = KojiroStrategy(
        StrategyConfig(
            strategy_id="kojiro", name="고지로 대순환", weight=0.6,
            params={"breakeven_promote_atr": be_mult},
        ),
    )
    pos = Position(
        ticker=TICKER, buy_price=buy_price, quantity=1, order_no="O-1",
        strategy_id="kojiro", buy_date=_YESTERDAY,
    )
    w = build(strat, pos)
    strat._position_atr[TICKER] = atr   # `_effective_atr` 폴백 정본
    return w


@pytest.mark.asyncio
async def test_r3_premarket_high_never_ratchets_stop_floor_to_breakeven(
    wire, _active,
):
    """프리장 오염 고가가 손절선을 **매수가로 영구 승격**시키지 않는다.

    매수 75,800 / ATR 2,000 / `breakeven_promote_atr=1.5` → 승격 임계 78,800.
    프리장 고가 86,500 이 앵커에 박히면 임계를 즉시 넘겨 `_stop_floor` 가
    71,800(=매수가−2ATR) → **75,800(매수가)** 로 래칫되고, 정상 눌림 75,000 에서
    확정 손실 STOP_LOSS 가 난다. `_stop_floor` 는 tighten-only 라 플래그를 꺼도
    되돌아가지 않는다 — 컨테이너 재시작 전까지 남는다.
    """
    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _kojiro_wire(wire, buy_price=75_800, atr=2_000.0, be_mult=1.5)

        await w.send(current=76_500, open_=76_000, high=86_500,
                     hgpr_hour=HOUR_PRE_MARKET)

        assert w.last_day_high == 0
        assert w.pos.high_since_buy == 76_500, "프리장 고가가 앵커에 박혔다"
        assert w.strategy._stop_floor.get(TICKER) == 71_800, (
            f"손절선이 매수가로 승격됐다 (floor={w.strategy._stop_floor.get(TICKER)}) — "
            "비가역 래칫이라 이 한 틱의 오염이 프로세스 생애 동안 남는다"
        )

        # 정상 눌림 — 하드손절선(71,800) 위라 아무 일도 없어야 한다.
        await w.send(current=75_000, open_=76_000, high=86_500,
                     hgpr_hour=HOUR_PRE_MARKET)

    w.oe.execute_sell.assert_not_awaited()
    assert w.strategy.check_exit_signal(TICKER, 75_000, 76_000) is Signal.NONE, (
        "프리장 고가로 승격된 손절선이 매수 직후 확정 손실을 만들었다"
    )


@pytest.mark.asyncio
async def test_r3b_genuine_main_high_does_ratchet_stop_floor(wire, _active):
    """**같은 쌍의 채택 측** — MAIN 에서 실제로 임계를 넘기면 승격은 정상 발화한다.

    이 짝이 없으면 "day_high 를 통째로 버려" 도 R-3 을 통과한다. cycle220 의
    이익보호 설계 자체를 무력화하지 않았음을 함께 못박는다.
    """
    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _kojiro_wire(wire, buy_price=75_800, atr=2_000.0, be_mult=1.5)

        # 프리장 누적치는 여전히 필드에 있으나 배제된다.
        await w.send(current=76_500, open_=76_000, high=86_500,
                     hgpr_hour=HOUR_PRE_MARKET)
        assert w.strategy._stop_floor.get(TICKER) == 71_800

        # MAIN 에서 79,500 (≥ 78,800 임계) 확정 → blind 였어도 관측 하나로 복구.
        await w.send(current=77_000, open_=76_000, high=79_500, hgpr_hour=HOUR_MAIN)

    assert w.pos.high_since_buy == 79_500, (
        f"MAIN 고가가 채택되지 않았다 (앵커={w.pos.high_since_buy}) — "
        "blind 구간에서 임계를 넘긴 이익이 보호되지 않는다"
    )
    assert w.strategy._stop_floor.get(TICKER) == 75_800, (
        "MAIN 고가로 임계를 넘겼는데 브레이크이븐 승격이 발화하지 않았다"
    )


@pytest.mark.asyncio
async def test_r3c_dark_launch_default_still_never_promotes(wire, _active):
    """다크런치 기본값(`breakeven_promote_atr=0.0`)에서는 어떤 고가도 승격 못 시킨다.

    활성화 결정은 cycle220 의 별도 게이트(N=10)다 — 이번 재설계가 그 결정을
    앞당겨 버리면 안 된다.
    """
    from src.engine.strategies.kojiro import KojiroStrategy

    assert KojiroStrategy.DEFAULT_PARAMS["breakeven_promote_atr"] == 0.0

    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _kojiro_wire(wire, buy_price=75_800, atr=2_000.0, be_mult=0.0)
        await w.send(current=77_000, open_=76_000, high=86_500, hgpr_hour=HOUR_MAIN)

    assert w.pos.high_since_buy == 86_500, "MAIN 고가 채택 자체는 정상"
    assert w.strategy._stop_floor.get(TICKER) == 71_800, (
        "다크런치 상태인데 브레이크이븐 플로어가 승격됐다"
    )


# ===========================================================================
# R-4 — `_adopts_day_high()` 는 MAIN 미활성 구간에서 여전히 미채택
#
# 핸들러 필터(A)와 보드 게이트(B 진입부의 `_adopts_day_high`)는 **중복이 아니다**:
#   - A 는 "고가가 **언제 찍혔나**"(payload 사실)를 본다
#   - `_adopts_day_high` 는 "지금 **어느 보드**인가"(우리 상태)를 본다
# 아래는 `[27]` 이 MAIN 창 안이라 A 를 통과하는 payload 로 **B 계층만** 고립 검증한다.
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boards",
    [set(), {MarketBoard.PRE_NXT}, {MarketBoard.POST_NXT}],
    ids=["scheduler-off", "pre_nxt", "post_nxt"],
)
async def test_r4_day_high_not_adopted_while_main_inactive(boards, wire, _active):
    """MAIN 미활성(스케줄러 미가동 포함) = 판정 불가 → **fail-closed(미채택)**.

    D+1 포지션이라 baseline 이 없으므로, 이 게이트가 무너지면 프리장/애프터 구간의
    관측이 곧바로 앵커가 된다. 최악이 "구 동작(러닝 max) 유지" 인 방향으로만
    실패해야 한다.

    전략은 프리장 청산 평가 화이트리스트(LTV)로 둔다 — 그래야 `_defers_pre_market_exit`
    가 앵커 갱신 자체를 막아 버려 이 가드가 공허해지는 것을 피한다.
    """
    _active(boards)
    with freeze_time(_FROZEN_UTC):
        w = _spy_wire(wire, "long_tail_volatility",
                      buy_price=75_800, buy_date=_YESTERDAY)

        await w.send(current=76_500, open_=76_000, high=86_500, hgpr_hour=HOUR_MAIN)
        await w.send(current=76_800, open_=76_000, high=86_500, hgpr_hour=HOUR_MAIN)

    assert w.last_day_high == 86_500, (
        "이 케이스는 **보드 게이트만** 고립 검증한다 — 핸들러는 통과시켜야 한다"
    )
    assert w.pos.high_since_buy == 76_800, (
        f"MAIN 미활성 구간에서 day_high 가 채택됐다 (앵커={w.pos.high_since_buy})"
    )


# ===========================================================================
# R-5 — 매수 당일 baseline 은 **그대로 살아 있다** (재설계의 축소 범위 못박기)
#
# 이번 재설계는 baseline 을 **제거**하는 게 아니라 **적용 범위를 매수 당일로 한정**한다.
# 매수 당일에는 여전히 "09:00 갭상승 스파이크 → 눌림 → 09:12 매수" 오염이 실재하므로
# baseline 이 필요하다.
# ===========================================================================

@pytest.mark.asyncio
async def test_r5_same_day_entry_still_gated_by_baseline(wire, _active):
    """`buy_date == today` 면 첫 관측은 baseline 설정만 — 채택 없음."""
    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _spy_wire(wire, "kojiro", buy_price=75_800, buy_date=_TODAY)

        # 09:12 매수 직후 첫 관측 — day_high 에 매수 전 갭상승 스파이크가 섞여 있다.
        await w.send(current=78_000, open_=76_000, high=86_500, hgpr_hour=HOUR_MAIN)
        assert w.pos.high_since_buy == 78_000, (
            "매수 당일 첫 관측은 baseline 설정만 해야 한다 (매수 전 구간 오염)"
        )

        # baseline 초과분 = 정의상 매수 이후 고가 → 채택
        await w.send(current=79_000, open_=76_000, high=88_000, hgpr_hour=HOUR_MAIN)

    assert w.pos.high_since_buy == 88_000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_buy_date", [None, "2026-08-20", 20_260_820],
    ids=["none", "str", "int"],
)
async def test_r5b_non_date_buy_date_is_fail_closed(bad_buy_date, wire, _active):
    """`buy_date` 가 `datetime.date` 가 아니면 **미채택**(fail-closed).

    비교(`buy_date < today`)가 타입 오류로 터지면 hot path 에서 예외가 새고,
    조용히 True 로 떨어지면 진입 전 고가가 통째로 유입된다. 둘 다 금지 —
    판정 불가의 최악은 "구 동작 유지" 여야 한다.
    """
    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _spy_wire(wire, "kojiro", buy_price=75_800, buy_date=_YESTERDAY)
        w.pos.buy_date = bad_buy_date

        await w.send(current=76_500, open_=76_000, high=86_500, hgpr_hour=HOUR_MAIN)
        await w.send(current=76_800, open_=76_000, high=86_500, hgpr_hour=HOUR_MAIN)

    assert w.pos.high_since_buy == 76_800, (
        f"buy_date={bad_buy_date!r} 인데 day_high 가 채택됐다 "
        f"(앵커={w.pos.high_since_buy}) — fail-closed 여야 한다"
    )


@pytest.mark.asyncio
async def test_r5c_future_buy_date_is_fail_closed(wire, _active):
    """미래 매수일 = 데이터 오염 → 미채택.

    `buy_date > today` 는 정상 상태에서 나올 수 없다(시계 오차·DB 오염·테스트 픽스처
    누수). 이때 `buy_date < today` 가 False 라는 이유로 "매수 당일" 분기로 흘려보내면
    baseline 이 오염된 서명 위에 세워진다 — 명시적으로 잘라낸다.
    """
    _active({MarketBoard.MAIN})
    with freeze_time(_FROZEN_UTC):
        w = _spy_wire(wire, "kojiro", buy_price=75_800, buy_date=date(2026, 8, 22))

        await w.send(current=76_500, open_=76_000, high=86_500, hgpr_hour=HOUR_MAIN)
        await w.send(current=76_800, open_=76_000, high=88_000, hgpr_hour=HOUR_MAIN)

    assert w.pos.high_since_buy == 76_800, (
        f"미래 매수일 포지션에서 day_high 가 채택됐다 (앵커={w.pos.high_since_buy})"
    )


# ===========================================================================
# R-6 — hot path / 범위 계약 (재설계가 8영역 규약을 흔들지 않는다)
# ===========================================================================

def _risk_func(name: str):
    tree = ast.parse((_REPO_ROOT / "src" / "engine" / "risk.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def test_r6_baseline_resolver_keeps_name_and_stays_sync():
    """`_day_high_since_entry` / `_day_high_baseline` 이름·동기성 유지 (A-10/A-10b 정합).

    재설계는 **분기 추가**이지 개명이 아니다. 이름이 바뀌면 A-10/A-10b 가
    "부재" 로 오탐하거나(가드 무효화) 조용히 통과한다.
    """
    fn = _risk_func("_day_high_since_entry")
    assert fn is not None, "baseline 리졸버가 사라졌거나 개명됐다"
    assert not isinstance(fn, ast.AsyncFunctionDef), "리졸버는 동기 함수 (hot path)"
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)], (
        "리졸버에 await 유입 — hot path 계약 위반"
    )
    from src.engine.risk import RiskManager as _RM
    rm = _RM(StrategyRegistry(), MagicMock())
    assert isinstance(rm._day_high_baseline, dict), "baseline 맵이 사라졌다"


def test_r6b_risk_module_has_no_high_key_literals():
    """A-3 정합 — `risk.py` 문자열 상수에 `stck_hgpr`/`high_price` 0건.

    `donchian_swing.py:804-806` 이 `ticker_prices` 의 그 키들을 읽는다(현재 항상 0
    폴백). 값이 채워지면 `ext_pct` 가 올라가 **매수가 더 많이 skip 된다** = 매수 행위
    변경. `day_high` 는 끝까지 **함수 인자로만** 흘러야 한다.
    """
    tree = ast.parse((_REPO_ROOT / "src" / "engine" / "risk.py").read_text(encoding="utf-8"))
    offenders = sorted({
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and n.value in ("stck_hgpr", "high_price")
    })
    assert not offenders, f"risk.py 에 고가 키 문자열 잔존: {offenders}"


def test_r6c_handler_hour_window_constants_are_module_level():
    """정규장 창 경계는 **모듈 상수**로 명시한다 — 매직넘버 금지.

    **의미 전환 (cycle222-a3 F-A)**: 상한이 `154000`(=`_BOARD_SCHEDULE` MAIN 종료,
    배타) 에서 `153000`(=KRX 정규장 종료, 포함) 으로 내려갔다. 15:30~15:40 은
    보드 전환 갭 마진이라 그 사이의 새 당일고가는 NXT 애프터 체결뿐이다.
    출처가 어디인지는 여전히 코드에 남아 있어야 필터가 스테일 되지 않는다.
    """
    src = (_REPO_ROOT / "src" / "realtime" / "handler.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    consts: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and isinstance(node.value, ast.Constant) \
                        and isinstance(node.value.value, int):
                    consts[t.id] = node.value.value
    assert 90_000 in consts.values(), (
        "MAIN 시작 경계(090000) 모듈 상수 부재 — 매직넘버 금지"
    )
    assert 153_000 in consts.values(), (
        "정규장 종료 경계(153000) 모듈 상수 부재 — 매직넘버 금지"
    )
    assert 154_000 not in consts.values(), (
        "구 상한(154000)이 잔존한다 — 15:30~15:40 NXT 애프터 체결이 KRX 당일고가로 "
        "새어 들어온다(F-A)"
    )
    assert "_BOARD_SCHEDULE" in src, (
        "상한이 `session._BOARD_SCHEDULE` MAIN 종료(15:40)와 **의도적으로 다르다**는 "
        "사실이 주석으로 남아 있지 않다 — 나중에 누가 '일관성' 을 이유로 되돌린다"
    )


def test_r6d_handler_reads_hgpr_hour_after_length_guard():
    """`[27]` 은 반드시 `len(fields) < 10` 가드 **이후** 에서만 읽는다.

    가드 앞에서 읽으면 짧은 payload 가 IndexError 로 터져 기존 silent-drop 계약
    (`_silent_drop_count`)이 깨지고, 콜백 예외 재-raise 경로로 번져 재연결이
    오발화한다.
    """
    src = (_REPO_ROOT / "src" / "realtime" / "handler.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_handle_tick":
            fn = node
    assert fn is not None
    body = ast.unparse(fn)
    assert "len(fields) < 10" in body, "기존 silent-drop 길이 가드가 사라졌다"
    guard_at = body.index("len(fields) < 10")
    for idx in ("fields[8]", "fields[27]"):
        if idx in body:
            assert body.index(idx) > guard_at, (
                f"`{idx}` 를 길이 가드 앞에서 읽는다 — 짧은 payload IndexError"
            )
