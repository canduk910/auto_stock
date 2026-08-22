"""cycle222-a2 — 앵커 baseline 을 **매수 당일로 한정** (사용자 재설계 지시).

## 왜 재설계인가

cycle222-a 1차 구현은 `_day_high_since_entry()` 가 **매일** baseline 을 다시 잡는다 —
그날 첫 관측을 기록만 하고 미채택, 이후 초과분만 채택. 사용자가 반대했다:

  > "당일로 쪼개버리면 기간중 최고점에서 야금야금 하락했을 때 익절을 못한다는
  >  이야기아니야?"

조사 결과 사용자 지적이 맞다. **매일 baseline 이 버리는 것은 '오늘의 blind 고점'** 이다:

- 멀티데이 고점 자체는 매일 아침 `_apply_high_since_buy_from_candles`
  (`buy_date < 봉일 < today`)가 일봉으로 복구하므로 살아 있다.
- 그러나 **오늘 봉은 미확정이라 그 캔들 경로가 구조적으로 배제**하고, on_tick 이
  올린 값은 DB 미기록이라 **오늘의 blind 고점은 아무도 복구하지 않는다.**
- 즉 D+1 에 09:00~09:58 이 blind 였고 그 사이 고점을 찍었다면, 1차 구현은 09:58
  첫 틱이 실어온 그 고점을 **baseline 이라는 이유로 통째로 버린다** — 그리고 그
  고점이 곧 샹들리에/트레일링의 기준점이었다.

## 그런데 baseline 자체는 왜 있었나 (F1/F2)

`STCK_HGPR` 는 **매수 전 구간**을 포함한다. 매수 당일이라면 09:00 갭상승 스파이크 →
눌림 → 09:12 눌림 매수 시, 첫 관측의 당일고가는 전부 **매수 전** 값이라 그대로
앵커에 박히면 진입 순간 브레이크이븐 승격/샹들리에가 오발화한다(F1).
게다가 통합 채널(`H0UNCNT0`)의 일-스코프 필드는 09:00 에 리셋되지 않아
08:00~09:00 NXT 프리장 체결이 누적된다(F2 — 000250 삼천당제약 2026-08-21 실측:
MAIN 구간 통합 틱의 일-스코프 시가 182,800 vs 같은 날 KRX 일봉 O/H/L/C
177,500/177,500/166,000/168,700 → 전일 종가와 일치하는 프리장 기준가).

## 이번 사이클이 세우는 계약

> **매수 이후 구간인지의 판정은 '매수일 대비 오늘'로 한다.**
>
> - `buy_date < today` (멀티데이 보유) → **하루 전체가 이미 진입 이후**다.
>   baseline 이 가릴 것이 하나도 없으므로 `day_high` 를 **첫 관측에서 즉시 채택**한다.
> - `buy_date == today` (매수 당일) → **기존 baseline 게이트 유지**. 매수 전
>   스파이크를 잘라낼 근거가 그것뿐이다.
> - `buy_date > today` / `buy_date` 가 date 가 아님 / `today` 가 None
>   → **미채택(fail-closed)**. 판정 불가 시 최악은 "구 동작(러닝 max) 유지"이고,
>     잘못 채택하면 앵커 과대복구 → 허깨비 조기 청산이다.
>
> 프리장 오염(F2)은 **매수 당일에만** 위험하다 — D+1 이후의 프리장 체결은 정의상
> 이미 보유 중인 구간에서 난 실거래이므로 '매수 전 구간' 이 아니다. 여전히
> `_adopts_day_high()`(MAIN 활성)가 얇은 호가 왜곡을 시각 축에서 걸러낸다.

⚠️ 이 파일의 모든 Position 은 `buy_date` 를 **명시 전달**한다. 자매 파일
`test_cycle222a_tick_day_high_anchor.py` 는 전부 기본값(오늘)이라 새 분기를 한 번도
타지 않는다 — 그 파일이 지키는 것은 `buy_date == today` 축, 이 파일이 지키는 것은
`buy_date < today` 축이다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

from src.engine.risk import RiskManager
from src.engine.scanner import KST_TZ
from src.engine.session import MarketBoard, session_tracker
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

# 005180 빙그레 실측 시나리오 (자매 파일과 동일 수치 — 두 축 비교가 쉬워진다)
BUY = 75_800
BLIND_HIGH = 86_500      # blind 구간에 실제로 찍힌 당일 고가 (틱 미수신)
LATE_TICK = 80_000       # blind 이후 도착한 단 하나의 관측 (현재가)


class _SpyStrategy(StrategyBase):
    """자매 파일 `_SpyStrategy` 와 동일 계약 — 청산 호출 인자만 기록한다."""

    def __init__(self, config, exit_signal: Signal = Signal.NONE):
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


def _today() -> date:
    """on_tick 이 `day_high_date` 로 쓰는 것과 **같은 소스**의 오늘(KST)."""
    return datetime.now(KST_TZ).date()


def _rig(
    strategy_id: str = "kojiro",
    *,
    buy_date,
    high_since_buy: int = BUY,
    order_no: str = "O",
    buy_price: int = BUY,
):
    """자매 파일 `_rig` 패턴 재사용 + **`buy_date` 명시 주입**.

    자매 파일 rig 는 `buy_date` 기본값(오늘)으로 고정돼 멀티데이 분기를 못 탄다.
    여기서는 `buy_date` 를 필수 키워드로 올려 호출부가 축을 반드시 선언하게 한다.
    """
    reg = StrategyRegistry()
    strat = _SpyStrategy(
        StrategyConfig(strategy_id=strategy_id, name=strategy_id, weight=0.1),
    )
    reg.register(strat)
    pos = Position(
        ticker="005180", buy_price=buy_price, quantity=1, order_no=order_no,
        strategy_id=strategy_id, buy_date=buy_date,
    )
    pos.high_since_buy = high_since_buy
    strat.state.positions["005180"] = pos
    oe = MagicMock()
    oe._selling = set()
    oe.execute_sell = AsyncMock()
    oe.execute_buy = AsyncMock()
    rm = RiskManager(reg, oe)
    return rm, strat, pos


# ===========================================================================
# 1 — 멀티데이 보유는 **첫 관측에서 즉시 채택** (사용자 요구의 핵심)
# ===========================================================================

@pytest.mark.asyncio
async def test_multiday_position_adopts_day_high_on_first_observation(_active):
    """`buy_date < today` 면 하루 전체가 진입 이후 → baseline 없이 즉시 채택.

    1차 구현은 이 첫 관측을 baseline 으로 삼아 **버렸다**. 그런데 D+1 에는 가릴
    '매수 전 구간' 이 애초에 없다 — 그 하루의 모든 체결은 이미 보유 중에 난 것이다.
    버리는 순간 그날의 blind 고점은 영구 유실된다(오늘 봉은 미확정이라 캔들 복구
    경로가 배제하고, on_tick 값은 DB 에 남지 않는다).
    """
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig(buy_date=_today() - timedelta(days=1))

    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)

    assert pos.high_since_buy == BLIND_HIGH, (
        f"멀티데이 보유의 첫 관측이 버려졌다 (앵커={pos.high_since_buy}). "
        "D+1 에는 매수 전 구간이 존재하지 않으므로 baseline 이 가릴 것이 없다"
    )


@pytest.mark.asyncio
async def test_multiday_blind_window_high_recovered_by_first_tick_of_day(_active):
    """**blind 구간 고점 복구** — D+1 09:00~09:58 무틱 → 09:58 첫 틱이 앵커를 복구.

    부팅 시 `_apply_high_since_buy_from_candles` 가 전일까지의 고점(82,000)을
    복구해 둔 상태에서, 오늘 09:00~09:58 이 통째로 blind 였고 그 사이 86,500 을
    찍었다. 09:58 에 도착한 **단 하나의 관측**이 그 고점을 실어 온다.
    """
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig(
        buy_date=_today() - timedelta(days=3),
        high_since_buy=82_000,      # 부팅 시 일봉으로 복구된 전일까지의 고점
    )

    # 오늘의 첫 틱 = 09:58. day_high 에 09:00~09:58 blind 구간 고점이 실려 있다.
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)

    assert pos.high_since_buy == BLIND_HIGH, (
        f"오늘의 blind 고점 {BLIND_HIGH} 가 baseline 으로 버려졌다 "
        f"(앵커={pos.high_since_buy}). 오늘 봉은 미확정이라 캔들 경로가 배제하므로 "
        "이 관측을 버리면 복구자가 아무도 없다"
    )


@pytest.mark.asyncio
async def test_multiday_adoption_survives_fresh_risk_manager(_active):
    """**재시작 후에도 채택** — 멀티데이 축에서는 baseline 부재가 걸림돌이 아니다.

    자매 파일 `test_restart_without_baseline_does_not_adopt` 는 `buy_date == today`
    축의 계약이다(매수 전/후를 가를 근거가 메모리에만 있었으므로 과소복구 선택).
    멀티데이는 근거가 **DB 에 영속된 `buy_date`** 라 재시작과 무관하게 판정된다.
    """
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig(buy_date=_today() - timedelta(days=1))

    fresh = RiskManager(rm.registry, rm.order_engine)   # 재시작 시뮬레이션
    await fresh.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)

    assert pos.high_since_buy == BLIND_HIGH, (
        "멀티데이 판정 근거는 영속된 buy_date 다 — 재시작이 채택을 막으면 안 된다"
    )


def test_helper_returns_day_high_verbatim_for_multiday():
    """리졸버 단위 계약 — `buy_date < today` 면 `day_high` 를 **그대로** 돌려준다."""
    today = _today()
    rm, _, pos = _rig(buy_date=today - timedelta(days=1))

    assert rm._day_high_since_entry("kojiro", "005180", pos, BLIND_HIGH, today) == BLIND_HIGH, (
        "멀티데이 분기 부재 — 리졸버가 첫 호출을 baseline 으로 삼켰다"
    )
    # 반복 호출도 동일 (baseline 축적으로 값이 흔들리면 안 된다)
    assert rm._day_high_since_entry("kojiro", "005180", pos, BLIND_HIGH, today) == BLIND_HIGH


# ===========================================================================
# 2 — 매수 당일 축은 **기존 baseline 게이트 그대로** (F1 회귀 금지)
# ===========================================================================

@pytest.mark.asyncio
async def test_same_day_entry_still_gated_by_baseline(_active):
    """`buy_date == today` 는 1차 구현 계약을 **byte 그대로** 유지한다.

    매수 전 스파이크(86,500)는 첫 관측 baseline 으로 흡수돼 미채택,
    그 이후의 신고가(88,000)만 채택된다.
    """
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig(buy_date=_today())

    await rm.on_tick("005180", 78_000, BUY, 0.0, day_high=BLIND_HIGH)
    assert pos.high_since_buy == 78_000, (
        "매수 당일 축까지 즉시 채택으로 바뀌면 F1(진입 직후 오발화)이 되살아난다"
    )

    await rm.on_tick("005180", 79_000, BUY, 0.0, day_high=88_000)
    assert pos.high_since_buy == 88_000, "baseline 초과분은 매수 당일에도 채택된다"


@pytest.mark.asyncio
async def test_same_day_premarket_accumulation_still_excluded(_active):
    """**F2 회귀 금지** — 매수 당일의 프리장 누적 고가는 여전히 baseline 이 흡수한다.

    통합 채널(`H0UNCNT0`) 일-스코프 필드는 09:00 에 리셋되지 않는다(000250 실측).
    매수 당일이라면 그 누적분이 곧 '매수 전 구간' 이므로 반드시 배제돼야 한다.
    """
    rm, _, pos = _rig("long_tail_volatility", buy_date=_today())

    _active({MarketBoard.PRE_NXT})                      # 08:30 프리장 — 시각 축에서 미채택
    await rm.on_tick("005180", 76_000, BUY, 0.0, day_high=BLIND_HIGH)
    assert pos.high_since_buy == 76_000

    _active({MarketBoard.PRE_NXT, MarketBoard.MAIN})    # 09:00 첫 MAIN 틱 — 누적 잔존
    await rm.on_tick("005180", 76_500, BUY, 0.0, day_high=BLIND_HIGH)
    assert pos.high_since_buy == 76_500, (
        "매수 당일 프리장 누적 고가가 앵커에 박혔다 — baseline 경계가 무너졌다"
    )


# ===========================================================================
# 3 — fail-closed: 미래 매수일 / 비-date buy_date / today 미상
# ===========================================================================

@pytest.mark.asyncio
async def test_future_buy_date_is_never_adopted(_active):
    """`buy_date > today` = 오염된 포지션 → 어떤 day_high 도 채택하지 않는다.

    1차 구현은 이 케이스를 '매수 당일' 과 구분하지 못해 baseline 초과분을 그대로
    채택했다. 매수일이 미래라는 것은 시계/DB 오염이라는 뜻이고, 그 상태에서
    앵커를 올리면 근거 없는 조기 청산이 난다.
    """
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig(buy_date=_today() + timedelta(days=1))

    await rm.on_tick("005180", 78_000, BUY, 0.0, day_high=BLIND_HIGH)
    await rm.on_tick("005180", 79_000, BUY, 0.0, day_high=88_000)

    assert pos.high_since_buy == 79_000, (
        f"미래 매수일 포지션에서 day_high 가 채택됐다 (앵커={pos.high_since_buy}) — "
        "판정 불가는 fail-closed(구 동작 유지)여야 한다"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_buy_date",
    [None, "2026-08-20", 20260820, 0],
    ids=["none", "str", "int", "zero"],
)
async def test_non_date_buy_date_is_never_adopted(bad_buy_date, _active):
    """`buy_date` 가 `datetime.date` 가 아니면 미채택 — 예외도 던지지 않는다.

    on_tick 은 hot path 라 예외가 새면 그 틱의 **나머지 전략 순회 전체**가 죽는다.
    (DB 복구/수동 주입 등으로 타입이 깨진 포지션이 실제로 존재할 수 있다.)
    """
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig(buy_date=_today() - timedelta(days=1))
    pos.buy_date = bad_buy_date     # 타입 오염 주입

    await rm.on_tick("005180", 78_000, BUY, 0.0, day_high=BLIND_HIGH)
    await rm.on_tick("005180", 79_000, BUY, 0.0, day_high=88_000)

    assert pos.high_since_buy == 79_000, (
        f"buy_date={bad_buy_date!r} 인데 day_high 가 채택됐다 — "
        "타입 판정 실패는 fail-closed 여야 한다"
    )


def test_today_none_is_never_adopted():
    """`today` 가 None(구간 자격 미판정)이면 리졸버는 항상 0 을 돌려준다.

    호출부는 `adopt_day_high` 가 False 면 None 을 넘기므로 정상 경로에선 도달하지
    않지만, 계약을 코드로 못박아 둔다 — None 을 date 와 비교하면 TypeError 다.
    """
    rm, _, pos = _rig(buy_date=_today() - timedelta(days=1))
    assert rm._day_high_since_entry("kojiro", "005180", pos, BLIND_HIGH, None) == 0


# ===========================================================================
# 4 — 올리기 전용 / 단조 증가 (전 기간 최고점 보존)
# ===========================================================================

@pytest.mark.asyncio
async def test_multiday_anchor_is_raise_only(_active):
    """D+1 에서도 앵커는 **올리기 전용** — 낮은 day_high 는 max 에 흡수된다.

    앵커가 내려가면 트레일링이 풀려 이미 확정된 이익 보호선이 사라진다.
    """
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig(buy_date=_today() - timedelta(days=2), high_since_buy=92_000)

    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)

    assert pos.high_since_buy == 92_000, "앵커 갱신은 tighten-only(올리기 전용)"


@pytest.mark.asyncio
async def test_anchor_monotonic_across_multiple_days(_active):
    """**사용자 원질문의 정면 반례** — 며칠에 걸쳐도 전 기간 최고점이 보존된다.

    "기간중 최고점에서 야금야금 하락" 시나리오: D+1 에 84,000 을 찍고, D+2 는
    종일 낮게(79,000) 흐르다가, 나중에 90,000 신고가. 앵커는 절대 내려가지 않고
    각 날의 고점을 **그날 첫 관측에서** 흡수해야 한다.
    """
    rm, _, pos = _rig(buy_date=date(2026, 8, 19))
    _active({MarketBoard.MAIN})

    with freeze_time("2026-08-20 01:00:00"):        # KST 2026-08-20 10:00
        await rm.on_tick("005180", 80_000, BUY, 0.0, day_high=84_000)
        assert pos.high_since_buy == 84_000, "D+1 첫 관측이 버려졌다"

    with freeze_time("2026-08-21 01:00:00"):        # KST 2026-08-21 10:00
        # 오늘은 종일 약세 — day_high 가 기존 앵커보다 낮다.
        await rm.on_tick("005180", 78_000, BUY, 0.0, day_high=79_000)
        assert pos.high_since_buy == 84_000, (
            "날짜가 바뀌었다고 전 기간 최고점을 잃으면 안 된다"
        )
        # 같은 날 후반 신고가 — 즉시 채택
        await rm.on_tick("005180", 88_000, BUY, 0.0, day_high=90_000)
        assert pos.high_since_buy == 90_000


# ===========================================================================
# 5 — 재진입: D+1 보유 → 청산 → 당일 재매수 시 baseline 모드 복귀
# ===========================================================================

@pytest.mark.asyncio
async def test_reentry_today_falls_back_to_baseline_mode(_active):
    """청산 후 **당일 재매수**하면 다시 `buy_date == today` = baseline 게이트.

    멀티데이 즉시 채택이 재진입 포지션까지 흘러가면, 재진입 **직전** 구간(1차 보유
    시절의 고가)이 새 포지션 앵커에 그대로 박혀 진입 순간 오발화한다.
    """
    _active({MarketBoard.MAIN})
    today = _today()
    rm, strat, pos = _rig(buy_date=today - timedelta(days=1), order_no="O-1")

    # 멀티데이 국면 — 즉시 채택
    await rm.on_tick("005180", 80_000, BUY, 0.0, day_high=84_000)
    assert pos.high_since_buy == 84_000

    # 청산 후 같은 종목 당일 재매수 (새 주문번호 / 새 매수가 / buy_date=오늘)
    strat.state.positions.pop("005180")
    pos2 = Position(
        ticker="005180", buy_price=85_000, quantity=1, order_no="O-2",
        strategy_id="kojiro", buy_date=today,
    )
    strat.state.positions["005180"] = pos2

    # 재진입 후 첫 관측 = 새 baseline(86,000 — 재진입 전 구간 포함) → 미채택
    await rm.on_tick("005180", 85_500, BUY, 0.0, day_high=86_000)
    assert pos2.high_since_buy == 85_500, (
        "재진입 포지션에 멀티데이 즉시 채택이 적용돼 매수 전 고가가 박혔다"
    )

    # 재진입 이후 신고가는 정상 채택
    await rm.on_tick("005180", 86_500, BUY, 0.0, day_high=88_000)
    assert pos2.high_since_buy == 88_000


# ===========================================================================
# 6 — 기존 구간/정합 가드는 멀티데이 축에서도 그대로 (우회 금지)
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boards",
    [set(), {MarketBoard.POST_NXT}, {MarketBoard.PRE_NXT}],
    ids=["empty(test-default)", "post_nxt", "pre_nxt"],
)
async def test_multiday_still_requires_main_active(boards, _active):
    """MAIN 미활성이면 멀티데이라도 미채택 — 시각 축 게이트를 우회하지 않는다.

    프리장/시간외의 얇은 호가 왜곡은 보유 기간과 무관하게 위험하다.
    (LTV 는 프리장 청산 평가 화이트리스트지만 `day_high` 는 예외 없이 배제.)
    """
    _active(boards)
    rm, _, pos = _rig("long_tail_volatility", buy_date=_today() - timedelta(days=1))

    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)

    assert pos.high_since_buy == LATE_TICK


@pytest.mark.asyncio
async def test_multiday_rejects_inconsistent_payload(_active):
    """`day_high < current_price` = 구조적 불가 → 멀티데이라도 미채택."""
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig(buy_date=_today() - timedelta(days=1))

    await rm.on_tick("005180", 82_000, BUY, 0.0, day_high=70_000)

    assert pos.high_since_buy == 82_000, (
        "이상 페이로드는 미채택하되 current_price 러닝 max 는 유지돼야 한다"
    )


@pytest.mark.asyncio
async def test_multiday_zero_day_high_is_noop(_active):
    """`day_high=0`(미관측/파싱 실패 폴백)은 멀티데이에서도 구 동작 그대로."""
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig(buy_date=_today() - timedelta(days=1))

    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=0)
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=0)

    assert pos.high_since_buy == LATE_TICK


@pytest.mark.asyncio
async def test_multiday_pre_market_defer_gate_still_holds(_active):
    """프리장 청산 평가 보류 전략은 멀티데이라도 앵커 갱신 자체가 보류된다.

    2026-08-06 계약(`_PRE_MARKET_EXIT_EVAL_STRATEGIES` 비화이트리스트) 보존.
    """
    _active({MarketBoard.PRE_NXT})
    rm, _, pos = _rig("kojiro", buy_date=_today() - timedelta(days=1))

    await rm.on_tick("005180", 95_000, BUY, 0.0, day_high=99_000)

    assert pos.high_since_buy == BUY


@pytest.mark.asyncio
async def test_exit_evaluation_still_uses_current_price(_active):
    """청산 평가는 여전히 `current_price` 로 — `day_high` 로 대체 금지."""
    _active({MarketBoard.MAIN})
    rm, strat, _ = _rig(buy_date=_today() - timedelta(days=1))

    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)

    assert strat.exit_calls == [("005180", LATE_TICK)]


# ===========================================================================
# 7 — 행위 레벨: 멀티데이 blind 고점 복구가 실제로 익절을 만든다
# ===========================================================================

@pytest.mark.asyncio
async def test_kojiro_chandelier_fires_on_recovered_multiday_blind_high(_active):
    """**사용자 우려의 실제 사고 재현** — D+1 blind 고점을 버리면 익절이 안 난다.

    kojiro 매수 75,800 / ATR 2,000 → 샹들리에 = 고점 − 2.5×2,000.
      - 앵커가 blind 고점 86,500 을 흡수하면 손절선 81,500 → 현재가 80,000 에서
        `TRAILING_STOP` 발화 = **+5.5% 지점에서 이익 확정**.
      - 1차 구현처럼 그 관측을 baseline 으로 버리면 앵커가 80,000 에 머물러
        샹들리에가 75,000 까지 내려간다 → 고점 대비 −7.5% 를 더 반납해야 비로소
        발화 = 사용자가 말한 "야금야금 하락했을 때 익절을 못한다".

    (하드손절 −8%=69,736 / 2ATR=71,800 은 모두 80,000 아래라 미발화 —
     이 테스트가 검증하는 것은 오직 샹들리에다.)
    """
    from src.engine.strategies.kojiro import KojiroStrategy

    _active({MarketBoard.MAIN})
    reg = StrategyRegistry()
    strat = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로 대순환", weight=0.6),
    )
    reg.register(strat)
    pos = Position(
        ticker="005180", buy_price=BUY, quantity=1, order_no="O-1",
        strategy_id="kojiro", buy_date=_today() - timedelta(days=2),
    )
    strat.state.positions["005180"] = pos
    strat._position_atr["005180"] = 2_000
    oe = MagicMock()
    oe._selling = set()
    oe.execute_sell = AsyncMock()
    oe.execute_buy = AsyncMock()
    rm = RiskManager(reg, oe)

    assert strat.config.params["trail_atr"] == 2.5, "샹들리에 배수 전제(2.5)"

    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)

    assert pos.high_since_buy == BLIND_HIGH, (
        f"멀티데이 blind 고점이 앵커에 반영되지 않았다 (앵커={pos.high_since_buy})"
    )
    oe.execute_sell.assert_awaited_once()
    assert oe.execute_sell.await_args.args[1] is Signal.TRAILING_STOP, (
        "복구된 고점 기준 샹들리에가 발화해야 한다 — 이것이 이익 반납 차단의 본체다"
    )
