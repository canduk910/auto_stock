"""cycle222-a — 트레일링 앵커 blind 내성 + **매수 이후 경계**(F1/F2 시정).

## 문제 1 — 앵커 blind (원 사이클 동기)

`risk.on_tick` 의 앵커 갱신은 **"수신된 틱들의 러닝 max"** 였다:

    pos.high_since_buy = max(pos.high_since_buy, current_price)

따라서 tick 미수신 구간(08-19 실측 최장 58분)의 고점은 **존재 자체가 기록되지
않는다**. 유일한 복구 경로 `strategy_base._apply_high_since_buy_from_candles` 는
`buy_date < 영업일 < today` **양쪽 strict** 라 매수 당일 봉을 의도적으로 배제하므로
**매수일 blind 고점은 영원히 복구되지 않는다.**
그런데 당일 고가는 WS 틱 payload `[8] STCK_HGPR` 로 **이미 실려 오는데 버려졌다.**

## 문제 2 (F1, CRITICAL) — "당일 고가" 는 틀린 불변식

1차 구현은 불변식을 "관측된 **당일** 고가" 로 세웠다. 옳은 문장은
"관측된 **매수 이후** 고가" 다. 매수 시점 경계가 없으면 **매수 전 구간의 고가**가
그대로 앵커에 박힌다:

    09:00 갭상승 +6% 스파이크 → 눌림 → 09:12 눌림에서 매수
    → 첫 관측이 day_high=매수 전 스파이크 를 실어 옴 → 앵커 즉시 점프
    → donchian breakeven(1.5×ATR, **라이브**) 즉시 성립 → 손절선이 진입 순간 매수가로 승격
    → 한 틱만 내려가면 STOP_LOSS (매수 직후 확정 손실 왕복 + `_bought_today` 재진입 차단)
    → kojiro 는 더 빠르다: 앵커를 부풀린 **그 틱에서** 2.5ATR 샹들리에가 발화

이 오염은 `_apply_high_since_buy_from_candles` 의 양쪽 strict 경계가 정확히 막으려고
존재하는 것이며 이번 사이클 AST 가드(A-6)가 그 경계를 지키라고 강제까지 한다.
**한 경로를 봉인하고 새 경로로 같은 오염을 허용**할 수는 없다.

## 문제 3 (F2, HIGH) — 프리장 배제가 시간축만 막았다

`_adopts_day_high()` 는 "MAIN 활성 시각인가" 만 본다. 그런데 시세 채널이
`scanner.TICK_TR_ID = "H0UNCNT0"` **통합**이라 `STCK_HGPR` 에 08:00~09:00 NXT
프리장 체결이 **누적**된다. → 09:00 MAIN 첫 틱에 프리장 얇은 호가 스파이크가
앵커로 박히며 시계 게이트를 우회한다.

## 이번 시정이 코드 계약으로 세우는 불변식

> 앵커에 채택되는 것은 **진입 시점 baseline 을 초과한 day_high 뿐**이다.
> baseline = 그 포지션 진입 후 **첫 관측**의 day_high (설정만 하고 채택하지 않는다).
> baseline 초과분은 정의상 **매수 이후** 고가이므로 과대복구가 구조적으로 불가능하다.
> 프리장 스파이크는 baseline 에 이미 포함되어 자동 배제된다(F2 동시 해소).

세부 불변식:
- **per-position-entry**: 청산 후 재진입하면 baseline 재스냅샷 (`order_no`/`buy_price`/
  `buy_date` 서명 + 포지션 소멸 시 pop).
- **일일 리셋**: 날짜가 바뀌면 baseline 무효 — 멀티데이 보유는 새 날 첫 관측이 새 baseline.
- **미설정이면 미채택**: 재시작 직후 baseline 부재 → 채택하지 않는다
  (**과소복구 = 안전 방향**, H-1 사이클 "오차는 과소복구 한 방향" 철학 일치).
- `risk` 내부 상태로만 — DB write 0 / `await` 추가 0 (hot path).
- 기존 가드 전부 유지: `TICK_DAY_HIGH_ANCHOR` / `day_high >= current_price` / MAIN 활성 / 올리기 전용.
"""

from __future__ import annotations

import inspect
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

from src.engine import risk as risk_mod
from src.engine.risk import RiskManager
from src.engine.session import MarketBoard, session_tracker
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

# 005180 빙그레 실측 시나리오
BUY = 75_800
BLIND_HIGH = 86_500      # blind 구간에 실제로 찍힌 당일 고가 (틱 미수신)
LATE_TICK = 80_000       # blind 이후 도착한 단 하나의 관측 (현재가)


class _SpyStrategy(StrategyBase):
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


def _rig(strategy_id: str = "kojiro", *, high_since_buy: int = BUY, order_no: str = "O"):
    reg = StrategyRegistry()
    strat = _SpyStrategy(
        StrategyConfig(strategy_id=strategy_id, name=strategy_id, weight=0.1),
    )
    reg.register(strat)
    pos = Position(
        ticker="005180", buy_price=BUY, quantity=1, order_no=order_no,
        strategy_id=strategy_id,
    )
    pos.high_since_buy = high_since_buy
    strat.state.positions["005180"] = pos
    oe = MagicMock()
    oe._selling = set()
    oe.execute_sell = AsyncMock()
    oe.execute_buy = AsyncMock()
    rm = RiskManager(reg, oe)
    return rm, strat, pos


# ---------------------------------------------------------------------------
# G-0 — 시그니처 계약 (키워드 + 기본값 = 기존 호출부 무해)
# ---------------------------------------------------------------------------

def test_on_tick_exposes_keyword_only_day_high_with_default_zero():
    sig = inspect.signature(RiskManager.on_tick)
    assert "day_high" in sig.parameters, (
        "on_tick 이 `day_high` 를 받지 않는다 — 당일 고가 관측이 통째로 버려진다"
    )
    p = sig.parameters["day_high"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY, (
        "day_high 는 **키워드 전용**이어야 한다 — 기존 4-positional 호출부 호환"
    )
    assert p.default == 0, "기본값 0 (미관측) — 기존 호출부가 구 동작 그대로여야 한다"


@pytest.mark.asyncio
async def test_legacy_positional_call_still_works(_active):
    """기존 호출부(4 positional)는 그대로 동작해야 한다 = 러닝 max 폴백."""
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig()
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0)
    assert pos.high_since_buy == LATE_TICK


def test_rollback_switch_constant_exists_and_defaults_true():
    assert hasattr(risk_mod, "TICK_DAY_HIGH_ANCHOR"), (
        "롤백 스위치 `TICK_DAY_HIGH_ANCHOR` 부재 — 라이브 즉시 되돌릴 수단이 없다"
    )
    assert risk_mod.TICK_DAY_HIGH_ANCHOR is True


# ===========================================================================
# B — 매수 이후 baseline 경계 (F1 CRITICAL 시정, 이번 사이클의 핵심)
# ===========================================================================

@pytest.mark.asyncio
async def test_pre_entry_spike_is_not_adopted_on_first_observation(_active):
    """**F1 핵심** — 매수 전 스파이크(86,500)가 앵커에 박히면 안 된다.

    매수 75,800 / 매수 전 당일고가 86,500 / 매수 후 현재가 78,000.
    앵커는 매수가~현재가 근처(78,000)에 머물러야 한다. 첫 관측은 **baseline 설정만**
    하고 채택하지 않는다 — 그 day_high 안에 매수 전 구간이 섞여 있기 때문이다.
    """
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig()

    await rm.on_tick("005180", 78_000, BUY, 0.0, day_high=BLIND_HIGH)

    assert pos.high_since_buy == 78_000, (
        f"매수 전 스파이크가 앵커에 유입됐다 (앵커={pos.high_since_buy}). "
        "불변식은 '관측된 당일 고가' 가 아니라 '관측된 **매수 이후** 고가' 다"
    )
    assert pos.high_since_buy < BLIND_HIGH


@pytest.mark.asyncio
async def test_pre_entry_spike_stays_excluded_across_repeated_ticks(_active):
    """같은 day_high 가 몇 번을 더 와도 baseline 이하라 영원히 미채택."""
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig()
    for px in (78_000, 77_500, 78_200):
        await rm.on_tick("005180", px, BUY, 0.0, day_high=BLIND_HIGH)
    assert pos.high_since_buy == 78_200, (
        "baseline 이하 day_high 는 반복돼도 채택되면 안 된다"
    )


@pytest.mark.asyncio
async def test_new_high_above_baseline_is_adopted(_active):
    """**매수 이후 신고가는 채택** — baseline 86,500 → 이후 88,000 관측 → 앵커 88,000."""
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig()

    await rm.on_tick("005180", 78_000, BUY, 0.0, day_high=BLIND_HIGH)   # baseline
    await rm.on_tick("005180", 79_000, BUY, 0.0, day_high=88_000)       # 매수 후 신고가

    assert pos.high_since_buy == 88_000, (
        "baseline 초과분은 정의상 매수 이후 고가다 — 채택하지 않으면 blind 내성이 사라진다"
    )


@pytest.mark.asyncio
async def test_blind_window_recovered_by_single_observation_after_baseline(_active):
    """**의미 전환** — 구 케이스 `단 하나의 틱으로 86,500 완전 복구`.

    구 케이스는 baseline 없이 첫 틱 하나로 86,500 을 채택했는데, 그건 곧
    **매수 전 스파이크도 첫 틱 하나로 채택**된다는 뜻이었다(F1).
    baseline 확립 **이후** 라면 blind 구간의 고점은 여전히 관측 1개로 완전 복구된다 —
    복구력은 유지하되 오염만 잘라낸 것이 이번 시정이다.
    """
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig()

    # 09:12 매수 직후 첫 관측 — 당시 당일 고가는 76,000 (매수가 부근)
    await rm.on_tick("005180", 76_000, BUY, 0.0, day_high=76_000)
    assert pos.high_since_buy == 76_000

    # 58분 blind (틱 0건). 그 사이 86,500 을 찍었다.
    # blind 이후 도착한 **단 하나의 관측**이 앵커를 완전 복구한다.
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)

    assert pos.high_since_buy == BLIND_HIGH, (
        f"blind 고가 {BLIND_HIGH} 가 유실됐다 (실제 {pos.high_since_buy}). "
        "baseline 확립 이후의 blind 복구력은 유지돼야 한다"
    )


@pytest.mark.asyncio
async def test_restart_without_baseline_does_not_adopt(_active):
    """**재시작(미설정) 미채택** — baseline 이 없으면 day_high 를 채택하지 않는다.

    재시작 직후엔 매수 전/후를 가를 근거가 메모리에 없다. 이때의 선택은
    **과소복구(안전)** — H-1 사이클이 세운 "남는 오차는 과소복구 한 방향" 철학과 같다.
    """
    _active({MarketBoard.MAIN})
    rm, strat, pos = _rig()

    # 재시작 시뮬레이션 — RiskManager 새 인스턴스(내부 baseline 맵 비어 있음)
    fresh = RiskManager(rm.registry, rm.order_engine)
    await fresh.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)

    assert pos.high_since_buy == LATE_TICK, (
        "baseline 미설정 상태에서 채택하면 재시작이 곧 과대복구 창구가 된다"
    )


@pytest.mark.asyncio
async def test_reentry_resnapshots_baseline(_active):
    """**재진입 재스냅샷** — 청산 후 같은 종목을 다시 사면 baseline 이 새로 잡힌다.

    안 그러면 1차 보유 때의 낮은 baseline 이 남아, 재진입 시점엔 **매수 전** 인
    구간의 고가가 곧바로 채택된다.
    """
    _active({MarketBoard.MAIN})
    rm, strat, pos = _rig(order_no="O-1")

    await rm.on_tick("005180", 76_000, BUY, 0.0, day_high=76_000)   # baseline=76,000
    await rm.on_tick("005180", 77_000, BUY, 0.0, day_high=84_000)   # 정상 채택
    assert pos.high_since_buy == 84_000

    # 청산
    strat.state.positions.pop("005180")
    await rm.on_tick("005180", 84_000, BUY, 0.0, day_high=84_000)   # 무보유 틱

    # 재진입 — 새 주문번호/새 매수가
    pos2 = Position(
        ticker="005180", buy_price=82_000, quantity=1, order_no="O-2",
        strategy_id="kojiro",
    )
    strat.state.positions["005180"] = pos2

    # 재진입 후 첫 관측 = 새 baseline(84,000, 재진입 전 구간 포함) → 미채택
    await rm.on_tick("005180", 82_500, BUY, 0.0, day_high=84_000)
    assert pos2.high_since_buy == 82_500, (
        "재진입인데 1차 보유의 baseline 이 남아 매수 전 고가가 채택됐다"
    )

    # 재진입 이후 신고가는 정상 채택
    await rm.on_tick("005180", 83_000, BUY, 0.0, day_high=85_000)
    assert pos2.high_since_buy == 85_000


@pytest.mark.asyncio
async def test_reentry_without_intervening_flat_tick_also_resnapshots(_active):
    """무보유 틱이 한 번도 안 끼어도(같은 날 즉시 재진입) 재스냅샷돼야 한다.

    포지션 소멸 pop 에만 의존하면 이 경로가 샌다 — 진입 서명(order_no/매수가/매수일)
    비교가 두 번째 방어선이다.
    """
    _active({MarketBoard.MAIN})
    rm, strat, _ = _rig(order_no="O-1")

    await rm.on_tick("005180", 76_000, BUY, 0.0, day_high=76_000)   # baseline=76,000

    pos2 = Position(
        ticker="005180", buy_price=83_000, quantity=1, order_no="O-2",
        strategy_id="kojiro",
    )
    strat.state.positions["005180"] = pos2

    await rm.on_tick("005180", 83_500, BUY, 0.0, day_high=86_000)
    assert pos2.high_since_buy == 83_500, (
        "재진입 서명이 바뀌었는데 구 baseline 으로 매수 전 고가를 채택했다"
    )


@pytest.mark.asyncio
async def test_baseline_applies_to_entry_day_only_not_to_later_days(_active):
    """**의미 전환 (cycle222-a2)** — baseline 은 **매수 당일에만** 적용된다.

    ## 구 케이스가 아무것도 지키지 않았던 이유

    이 자리에 있던 `test_daily_reset_invalidates_baseline` 은 "날짜가 바뀌면 baseline
    무효" 를 확인한다고 적혀 있었지만, 실제로는 **날짜 키를 유지하든 제거하든** 통과
    하는 문장이었다(조사 실측: 재설계 구현으로 돌리면 `direct_adopt=4` /
    `baseline_set=0` 인데도 최종 앵커 84,000/86,000 이 그대로 맞아떨어진다).

    픽스처부터 시나리오와 어긋나 있었다 — `_rig()` 를 `freeze_time` **밖**에서 호출해
    포지션의 `buy_date` 가 **실제 오늘**(프리즈된 2026-08-19/20 보다 미래)로 잡힌다.
    "며칠째 보유 중인 종목의 날짜 경계" 를 재현한다고 해 놓고 정작 미래 매수일
    포지션을 만들어 놓은 것이다. 우연히 통과하는 가드는 가드가 아니다.

    ## 새 계약

    사용자 지적:

    > "당일로 쪼개버리면 기간중 최고점에서 야금야금 하락했을 때 익절을 못한다는
    >  이야기아니야?"

    매일 baseline 을 다시 잡으면 그날 **첫 관측**이 통째로 버려진다. 그게 버리는 것은
    정확히 **오늘의 blind 고점**이다 — 멀티데이 고점은 매일 아침
    `_apply_high_since_buy_from_candles` 가 일봉으로 복구하지만, **오늘 봉은 미확정이라
    그 경로가 `buy_date < 영업일 < today` 로 의도적으로 배제**하고, on_tick 이 올린 값은
    DB 에 쓰이지 않는다. 즉 오늘의 blind 고점은 아무도 복구하지 않는다.

    그래서 baseline 의 **적용 범위**를 매수 당일로 한정한다:

    - `buy_date == today` → 매수 전 스파이크가 섞여 있으므로 baseline 게이트 유지(F1)
    - `buy_date <  today` → 하루 전체가 진입 이후 구간 → **첫 관측부터 즉시 채택**

    프리장 오염(F2) 방어는 baseline 이 아니라 **소스**(`handler` 의 `[27] HGPR_HOUR`
    MAIN 창 필터)로 이관됐다 — 통합 채널의 일-스코프 필드가 09:00 에 리셋되지 않는다는
    라이브 실측(000250, 2026-08-21)에 대한 정확한 대응이다. 통합 경로 검증은
    `test_cycle222a2_regression_guards.py`.
    """
    _active({MarketBoard.MAIN})

    with freeze_time("2026-08-21 01:00:00"):   # KST 2026-08-21 10:00
        # --- 매수 다음 날: baseline 없이 첫 관측부터 채택 ---
        rm, _, pos = _rig()
        pos.buy_date = date(2026, 8, 20)

        # 09:00~09:58 blind(틱 0건) 뒤 도착한 **단 하나의** 관측.
        await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)
        assert pos.high_since_buy == BLIND_HIGH, (
            f"멀티데이 보유의 오늘 blind 고점이 유실됐다 (앵커={pos.high_since_buy}). "
            "매일 baseline 을 다시 잡으면 그날 첫 관측 = 그날 blind 고점이 매일 버려진다"
        )

        # --- 매수 당일: baseline 게이트는 그대로 살아 있다 (F1 축소 아님) ---
        rm2, _, pos2 = _rig()
        pos2.buy_date = date(2026, 8, 21)

        await rm2.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)
        assert pos2.high_since_buy == LATE_TICK, (
            "매수 당일 첫 관측에는 매수 전 구간 고가가 섞여 있다 — baseline 설정만 해야 한다"
        )
        # baseline 초과분 = 정의상 매수 이후 고가 → 채택
        await rm2.on_tick("005180", 81_000, BUY, 0.0, day_high=88_000)
        assert pos2.high_since_buy == 88_000


@pytest.mark.asyncio
async def test_reset_daily_state_clears_baseline(_active):
    """`reset_daily_state()` 동행 clear — 정산 후 잔류 금지 (프로젝트 관례)."""
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig()
    await rm.on_tick("005180", 76_000, BUY, 0.0, day_high=76_000)

    rm.reset_daily_state()

    await rm.on_tick("005180", 77_000, BUY, 0.0, day_high=84_000)
    assert pos.high_since_buy == 77_000, (
        "reset_daily_state 후에도 구 baseline 이 살아 있으면 매수 전 고가가 채택된다"
    )


# ---------------------------------------------------------------------------
# B-behavior — F1 이 만들던 실제 사고: 진입 직후 오발화
# ---------------------------------------------------------------------------

def _donchian_rig():
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy

    reg = StrategyRegistry()
    strat = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="20일 신고가", weight=0.2),
    )
    reg.register(strat)
    pos = Position(
        ticker="005180", buy_price=BUY, quantity=10, order_no="O-1",
        strategy_id="donchian_swing",
    )
    strat.state.positions["005180"] = pos
    strat._entry_atr["005180"] = 2_000     # 터틀 매수 = ATR 손절 경로 (breakeven 무장)
    oe = MagicMock()
    oe._selling = set()
    oe.execute_sell = AsyncMock()
    oe.execute_buy = AsyncMock()
    return RiskManager(reg, oe), strat, pos, oe


@pytest.mark.asyncio
async def test_no_breakeven_misfire_right_after_entry_donchian(_active):
    """**진입 직후 브레이크이븐 오발화 차단** (donchian, breakeven_promote_atr=1.5 라이브).

    매수 75,800 / entry_atr 2,000 → 임계 78,800 · 하드손절선 71,800.
    매수 전 스파이크 86,500 이 앵커에 박히면 임계가 즉시 성립해 손절선이 매수가로
    승격되고, 다음 틱 75,000 에서 **매수 직후 확정 손실 STOP_LOSS** 가 난다.
    """
    _active({MarketBoard.MAIN})
    rm, strat, pos, oe = _donchian_rig()
    assert strat.config.params["breakeven_promote_atr"] == 1.5, "라이브 값 전제"

    await rm.on_tick("005180", 78_000, BUY, 0.0, day_high=BLIND_HIGH)
    assert pos.high_since_buy < BUY + 1.5 * 2_000, (
        "앵커가 브레이크이븐 임계를 진입 순간에 넘겼다 — 매수 전 고가 유입"
    )
    oe.execute_sell.assert_not_awaited()

    # 한 틱 하락 — 정상이면 하드손절선(71,800) 위라 아무 일도 없어야 한다.
    await rm.on_tick("005180", 75_000, BUY, 0.0, day_high=BLIND_HIGH)
    oe.execute_sell.assert_not_awaited()
    assert strat.check_exit_signal("005180", 75_000, BUY) is Signal.NONE, (
        "진입 직후 브레이크이븐 승격으로 손절선이 매수가까지 올라갔다"
    )


@pytest.mark.asyncio
async def test_no_chandelier_misfire_right_after_entry_kojiro(_active):
    """**진입 직후 샹들리에 오발화 차단** (kojiro 2.5ATR).

    kojiro 는 더 빠르다 — 앵커 갱신이 `check_exit_signal` 바로 앞이라, 스파이크를
    앵커에 박은 **그 틱에서** 샹들리에(86,500 − 5,000 = 81,500 ≥ 78,000)가 발화해
    매수 → 즉시 전량 청산이 된다.
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
        strategy_id="kojiro",
    )
    strat.state.positions["005180"] = pos
    strat._position_atr["005180"] = 2_000
    oe = MagicMock()
    oe._selling = set()
    oe.execute_sell = AsyncMock()
    oe.execute_buy = AsyncMock()
    rm = RiskManager(reg, oe)

    await rm.on_tick("005180", 78_000, BUY, 0.0, day_high=BLIND_HIGH)

    oe.execute_sell.assert_not_awaited()
    assert strat.check_exit_signal("005180", 78_000, BUY) is Signal.NONE, (
        "매수 전 스파이크가 앵커에 박혀 진입 순간 샹들리에가 발화했다"
    )


# ---------------------------------------------------------------------------
# G-2 — 올리기 전용 (앵커는 절대 내려가지 않는다)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_day_high_never_lowers_existing_anchor(_active):
    """기존 앵커가 더 높으면 `day_high` 는 앵커를 내리지 못한다.

    (재시작 후 candles 복구로 앵커가 더 높게 서 있는 케이스 — 내려가면 트레일링이
     풀려 이미 확정된 이익 보호선이 사라진다.)
    """
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig(high_since_buy=92_000)
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)
    assert pos.high_since_buy == 92_000, "앵커 갱신은 tighten-only(올리기 전용)"


# ---------------------------------------------------------------------------
# G-3 — 정합 가드: `day_high < current_price` 인 이상 페이로드 미채택
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inconsistent_payload_day_high_below_current_is_rejected(_active):
    """고가 < 현재가 = 구조적으로 불가능 → 페이로드 신뢰 불가, 미채택.

    이때도 `current_price` 러닝 max 는 정상 동작해야 한다(퇴행 금지).
    """
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig()
    await rm.on_tick("005180", 82_000, BUY, 0.0, day_high=70_000)
    assert pos.high_since_buy == 82_000, (
        "이상 페이로드는 미채택하되 current_price 러닝 max 는 유지돼야 한다"
    )


@pytest.mark.asyncio
async def test_inconsistent_payload_does_not_poison_baseline(_active):
    """이상 페이로드는 baseline 으로도 채택되면 안 된다 (낮은 baseline = 과대복구 창구)."""
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig()
    await rm.on_tick("005180", 82_000, BUY, 0.0, day_high=70_000)   # 이상 → 무시
    await rm.on_tick("005180", 82_000, BUY, 0.0, day_high=BLIND_HIGH)  # 여기서 baseline
    assert pos.high_since_buy == 82_000, (
        "이상 페이로드가 baseline 으로 굳으면 그 직후 매수 전 고가가 통째로 채택된다"
    )


@pytest.mark.asyncio
async def test_zero_day_high_is_noop(_active):
    """`day_high=0` (미관측/파싱 실패 폴백) 은 구 동작과 동일해야 한다."""
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig()
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=0)
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=0)
    assert pos.high_since_buy == LATE_TICK


@pytest.mark.asyncio
async def test_zero_day_high_does_not_become_baseline(_active):
    """미관측(0)은 baseline 으로 굳으면 안 된다 — 0 baseline = 다음 관측 전량 채택."""
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig()
    await rm.on_tick("005180", 76_000, BUY, 0.0, day_high=0)
    await rm.on_tick("005180", 76_000, BUY, 0.0, day_high=BLIND_HIGH)
    assert pos.high_since_buy == 76_000, (
        "0 이 baseline 이 되면 첫 실관측(매수 전 고가 포함)이 통째로 채택된다"
    )


# ---------------------------------------------------------------------------
# G-4 — 프리장 배제 (MAIN 활성일 때만 채택) + F2 (통합 채널 누적 고가)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pre_nxt_only_does_not_adopt_day_high_even_for_ltv(_active):
    """LTV 는 프리장 청산 평가 화이트리스트지만 **day_high 는 여전히 배제**한다."""
    _active({MarketBoard.PRE_NXT})
    rm, _, pos = _rig("long_tail_volatility")
    await rm.on_tick("005180", 76_000, BUY, 0.0, day_high=BLIND_HIGH)
    await rm.on_tick("005180", 76_000, BUY, 0.0, day_high=BLIND_HIGH)
    assert pos.high_since_buy == 76_000, (
        "프리장 왜곡 고가를 앵커에 채택하면 안 된다 (LTV 예외 없음)"
    )


@pytest.mark.asyncio
async def test_pre_nxt_gated_strategy_anchor_untouched(_active):
    """비화이트리스트 전략은 프리장에 앵커 갱신 자체가 보류된다 (2026-08-06 계약 보존)."""
    _active({MarketBoard.PRE_NXT})
    rm, _, pos = _rig("kojiro")
    await rm.on_tick("005180", 95_000, BUY, 0.0, day_high=99_000)
    assert pos.high_since_buy == BUY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boards",
    [set(), {MarketBoard.POST_NXT}, {MarketBoard.PRE_NXT}],
    ids=["empty(test-default)", "post_nxt", "pre_nxt"],
)
async def test_day_high_not_adopted_when_main_inactive(boards, _active):
    """MAIN 미활성 = 판정 불가 포함 → 보수적으로 미채택."""
    _active(boards)
    rm, _, pos = _rig("long_tail_volatility")
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)
    assert pos.high_since_buy == LATE_TICK


@pytest.mark.asyncio
async def test_premarket_accumulated_high_not_anchored_on_first_main_tick(_active):
    """**F2** — 프리장 스파이크가 09:00 MAIN 첫 틱에 앵커로 박히지 않는다.

    시세 채널이 `H0UNCNT0` **통합**이라 `STCK_HGPR` 에 08:00~09:00 NXT 프리장 체결이
    누적된다. 시계 게이트(`_adopts_day_high`)는 "MAIN 활성인가" 만 보므로 09:00 첫
    틱이 프리장 얇은 호가 고가를 실어 오면 그대로 통과했다.
    baseline 경계는 그 고가를 **진입 시점 관측**으로 흡수해 자동 배제한다.
    """
    rm, _, pos = _rig("long_tail_volatility")   # 프리장 청산 평가 화이트리스트

    # 08:30 프리장 — 얇은 호가로 86,500 스파이크. MAIN 미활성이라 미채택.
    _active({MarketBoard.PRE_NXT})
    await rm.on_tick("005180", 76_000, BUY, 0.0, day_high=BLIND_HIGH)
    assert pos.high_since_buy == 76_000

    # 09:00 MAIN 첫 틱 — day_high 에 프리장 스파이크가 **여전히 누적돼 있다**.
    _active({MarketBoard.PRE_NXT, MarketBoard.MAIN})
    await rm.on_tick("005180", 76_500, BUY, 0.0, day_high=BLIND_HIGH)

    assert pos.high_since_buy == 76_500, (
        f"프리장 누적 고가가 MAIN 첫 틱에 앵커로 박혔다 (앵커={pos.high_since_buy}). "
        "시계 게이트만으로는 통합 채널 누적을 막을 수 없다 — baseline 경계가 필요하다"
    )


@pytest.mark.asyncio
async def test_day_high_adopted_at_0900_boundary_pre_and_main(_active):
    """09:00 경계(PRE_NXT + MAIN 동시 활성)에서도 baseline 확립 후엔 정상 채택."""
    _active({MarketBoard.PRE_NXT, MarketBoard.MAIN})
    rm, _, pos = _rig()
    await rm.on_tick("005180", 76_000, BUY, 0.0, day_high=76_000)   # baseline
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)
    assert pos.high_since_buy == BLIND_HIGH


# ---------------------------------------------------------------------------
# G-5 — 롤백 스위치: False 면 구 동작(러닝 max)과 완전 동일
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rollback_switch_off_restores_running_max_exactly(_active, monkeypatch):
    _active({MarketBoard.MAIN})
    monkeypatch.setattr(risk_mod, "TICK_DAY_HIGH_ANCHOR", False)
    rm, _, pos = _rig()
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)
    assert pos.high_since_buy == LATE_TICK, (
        "TICK_DAY_HIGH_ANCHOR=False 는 앵커 **갱신 규칙**을 구 동작으로 되돌린다"
    )


def test_rollback_switch_docstring_admits_state_is_not_rewound():
    """**F6** — 롤백 스위치는 규칙만 되돌리고 **상태는 못 되돌린다**.

    kojiro `_stop_floor` 는 tighten-only 래칫이라, 오염된 앵커로 승격된 브레이크이븐
    플로어는 플래그를 꺼도 **그 프로세스 생애 동안 남는다**. "구 동작 완전 복원" 은
    과장이고, 정직한 계약은 **"플래그 변경 + 컨테이너 재시작 필요"** 다
    (재시작해야 `recompute_held_atr` 가 일봉으로 손절선을 재도출한다).
    """
    src = inspect.getsource(risk_mod)
    head = src.split("TICK_DAY_HIGH_ANCHOR")[0]
    assert "완전 복원" not in head, (
        "롤백 주석의 '구 동작 완전 복원' 은 거짓 — _stop_floor 래칫은 되돌아가지 않는다"
    )
    assert "재시작" in head, (
        "롤백 계약에 '컨테이너 재시작 필요' 가 명시돼야 한다 (F6)"
    )


# ---------------------------------------------------------------------------
# G-6 — 매수 행위 diff 0: ticker_prices 에 쓰는 키 집합 불변
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ticker_prices_payload_keys_unchanged(_active):
    """`day_high` 는 **함수 인자로만** 흐른다 — 공유 시세 dict 오염 금지."""
    from src.engine.scanner import ticker_prices

    ticker_prices.pop("005180", None)
    _active({MarketBoard.MAIN})
    rm, _, _ = _rig()
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)

    assert set(ticker_prices["005180"].keys()) == {
        "current_price", "open_price", "change_rate", "prdy_ctrt",
    }, "ticker_prices 키 집합 불변 (stck_hgpr/high_price 주입 금지)"
    ticker_prices.pop("005180", None)


# ---------------------------------------------------------------------------
# G-7 — 청산 평가 경로 퇴행 없음 (앵커 복구가 청산을 막거나 만들지 않는다)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exit_evaluation_still_runs_with_day_high(_active):
    _active({MarketBoard.MAIN})
    rm, strat, _ = _rig()
    await rm.on_tick("005180", LATE_TICK, BUY, 0.0, day_high=BLIND_HIGH)
    assert strat.exit_calls == [("005180", LATE_TICK)], (
        "check_exit_signal 은 current_price 로 평가된다 — day_high 로 대체 금지"
    )


@pytest.mark.asyncio
async def test_baseline_map_does_not_grow_for_unheld_tickers(_active):
    """무보유 종목 틱이 baseline 맵을 무한 성장시키면 안 된다 (hot path 메모리)."""
    _active({MarketBoard.MAIN})
    rm, strat, _ = _rig()
    strat.state.positions.pop("005180")
    for i in range(50):
        await rm.on_tick(f"00518{i % 10}", 80_000, BUY, 0.0, day_high=BLIND_HIGH)
    assert not rm._day_high_baseline, (
        "보유하지 않은 종목의 baseline 은 남기지 않는다"
    )
