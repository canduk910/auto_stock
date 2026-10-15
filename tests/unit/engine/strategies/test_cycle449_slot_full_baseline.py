"""cycle449 (RED) — BFB·VCP 「슬롯이 찬 동안에도 직전 가격 추적」.

## 결함

`bull_flag_breakout.py::check_buy_signal` 과 `vcp_breakout.py::check_buy_signal` 은
`if self.is_max_positions(): return Signal.NONE` 이 `_prev_price` read-then-write 보다
**앞**이다. 슬롯(`max_positions`)이 찬 동안 그 종목의 `_prev_price` 가 갱신되지 않아,
슬롯이 비는 첫 틱에 **이미 돌파선 위에 있던 종목**이 `prev < 돌파선 <= current` 로
「방금 돌파」로 읽혀 바로 매수된다.

실사례 3건 전부 손실 — 10-06 14:06 엑스게이트(다른 종목 매도 1초 뒤) ·
10-07 13:39 빛과전자(매도 2초 뒤) · 09-23 에이치브이엠(매도 15초 뒤 래치 무장).
근거 = `_workspace/domain_consult/2026-10-12_bfb_breakout_volume_mult.md`.

## 계약 (사용자 결정 2026-10-12 — 명세 `_workspace/red/cycle449_slot_full_baseline_spec.md`)

`is_max_positions()` 가 참이라 `Signal.NONE` 을 돌려주기 **직전**에 「만석 추적」을
한 번 수행한다(동기·순수 메모리·never-raise).

1. 후보가 아니거나 `current_price <= 0` → 아무것도 하지 않는다.
2. 그 종목에 거래량 래치가 무장돼 있으면 아무것도 하지 않는다(001450 회귀 규약).
3. BFB 만: `_breakout_first_seen` 에 있으면 pop.
4. 돌파선이 양수이고 이번 틱이 교차면 `[bfb|vcp_full_cross_skipped]` INFO 1회/종목/일.
5. `_prev_price[ticker] = current_price`.

선례 = VB·LTV 09:00 진입 보류(`strategies/CLAUDE.md` 각주 ② — 「보류 중에도
baseline 을 갱신한다. 얼리면 해제 뒤 첫 틱이 거짓 돌파」).

## 시계

두 전략의 매수 창 게이트가 naive `datetime.now().time()` 이라 모든 호출을
`freeze_time` 안에서 한다(기본 10:00 — BFB 09:05~13:00 · VCP 09:05~14:30 안).
`tick_volume` 도 KST 날짜 키 자기 리셋이라 기록을 같은 freeze 안에서 한다.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

import pytest
from freezegun import freeze_time

from src.engine import tick_volume
from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

IN_WINDOW = "2026-10-12 10:00:00"
NEXT_DAY_IN_WINDOW = "2026-10-13 10:00:00"
OUT_OF_WINDOW = "2026-10-12 08:00:00"


# ---------------------------------------------------------------------------
# 전략별 도구 묶음
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Kit:
    name: str
    make: Callable[[], object]
    ticker: str
    line: int             # 돌파선 (BFB flag_high / VCP base_high)
    low: int              # 구조 하단 (BFB flag_low / VCP base_low)
    line_key: str         # `_candidates[ticker]` 안의 돌파선 키 = 로그 필드명
    enough_vol: int       # 거래량 게이트를 넘는 실측 누적 거래량
    short_vol: int        # 임계 미달 거래량
    open_price: int
    logger_name: str
    marker: str


def _make_bfb(retention_minutes: int = 0) -> BullFlagBreakoutStrategy:
    strat = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="BFB", weight=0.15)
    )
    strat.config.params["breakout_retention_minutes"] = retention_minutes
    strat._candidates["280360"] = {
        "pole_start": 100_000,
        "pole_high": 130_000,
        "flag_high": 136_200,
        "flag_low": 118_900,
        "flag_avg_volume": 18_651.5,     # × breakout_volume_mult(2.0) = 37,303
        "pole_len": 5,
        "flag_len": 9,
        "atr14": 3_000,
        "prev_close": 133_000,
    }
    return strat


def _make_vcp() -> VcpBreakoutStrategy:
    strat = VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.10)
    )
    strat._candidates["005930"] = {
        "base_high": 12_000,
        "base_low": 10_500,
        "last_pullback_pct": 0.05,
        "atr14": 200,
        "ema50": 11_500,
        "ema150": 11_000,
        "ema200": 10_800,
        "prev_close": 11_900,
        "avg_volume_20": 300_000,        # × breakout_volume_mult(1.5) = 450,000
    }
    return strat


BFB = Kit(
    name="bfb", make=_make_bfb, ticker="280360", line=136_200, low=118_900,
    line_key="flag_high", enough_vol=37_304, short_vol=2_990, open_price=130_000,
    logger_name="src.engine.strategies.bull_flag_breakout",
    marker="[bfb_full_cross_skipped]",
)
VCP = Kit(
    name="vcp", make=_make_vcp, ticker="005930", line=12_000, low=10_500,
    line_key="base_high", enough_vol=450_001, short_vol=10_000, open_price=11_900,
    logger_name="src.engine.strategies.vcp_breakout",
    marker="[vcp_full_cross_skipped]",
)


@pytest.fixture(params=[BFB, VCP], ids=lambda k: k.name)
def kit(request) -> Kit:
    return request.param


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    tick_volume.reset_for_test()
    monkeypatch.setattr("src.engine.scanner.ticker_prices", {}, raising=False)
    yield
    tick_volume.reset_for_test()


def _fill_slots(strat) -> list[str]:
    """`max_positions` 만큼 다른 종목 보유를 채워 만석으로 만든다."""
    n = int(strat.config.params["max_positions"])
    held = [f"9{i:05d}" for i in range(n)]
    for t in held:
        strat.state.positions[t] = Position(
            ticker=t, buy_price=10_000, quantity=1, order_no=f"o{t}",
            strategy_id=strat.config.strategy_id,
        )
    assert strat.is_max_positions(), "픽스처 오류 — 만석이 되지 않았다"
    return held


def _free_one_slot(strat, held: list[str]) -> None:
    del strat.state.positions[held[0]]
    assert not strat.is_max_positions(), "픽스처 오류 — 슬롯이 비지 않았다"


def _tick(strat, kit: Kit, price: int) -> Signal:
    return strat.check_buy_signal(kit.ticker, price, kit.open_price)


def _marker_records(caplog, kit: Kit) -> list[logging.LogRecord]:
    """해당 전략 모듈 로거 · INFO · prefix 로 한정 (CI 루트 DEBUG 잡음 차단)."""
    return [
        r for r in caplog.records
        if r.name == kit.logger_name
        and r.levelno == logging.INFO
        and r.getMessage().startswith(kit.marker + " ")
    ]


# ###########################################################################
# T1 — 결함 재현: 만석 동안 돌파선을 넘은 종목은 슬롯이 비어도 사지 않는다
# ###########################################################################

@pytest.mark.parametrize("seed_prev_below", [False, True], ids=["first_seen_while_full", "prev_below_before_full"])
def test_slot_freed_when_price_already_above_line_then_no_buy(kit, seed_prev_below):
    """T1 — 만석 중 아래→위로 올라간 종목은 슬롯이 빈 첫 틱에 사지 않는다.

    현 코드는 만석 동안 `_prev_price` 가 얼어 있어(미관측이면 0, 관측됐으면 돌파선
    아래 옛 값) 슬롯이 빈 첫 틱이 `prev < 돌파선 <= current` = 「방금 돌파」가 되고,
    거래량이 충분하면 그대로 BUY 다.
    """
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        tick_volume.record_acml_vol(kit.ticker, kit.enough_vol)
        if seed_prev_below:
            strat._prev_price[kit.ticker] = kit.line - 300
        held = _fill_slots(strat)

        for price in (kit.line - 200, kit.line - 100, kit.line + 50, kit.line + 100):
            assert _tick(strat, kit, price) == Signal.NONE, "만석인데 신호가 났다"

        _free_one_slot(strat, held)
        sig = _tick(strat, kit, kit.line + 100)

    assert sig == Signal.NONE, (
        f"슬롯이 빈 첫 틱에 {sig} — 만석 동안 이미 돌파선({kit.line}) 위에 있던 종목을 "
        "「방금 돌파」로 읽었다(`_prev_price` 가 만석 동안 얼어 있었다)"
    )
    assert kit.ticker not in strat._bought_today
    assert strat.state.buy_signals == []


def test_slot_full_ticks_update_prev_price(kit):
    """T1 — 만석 동안의 모든 틱이 `_prev_price` 를 그 틱 가격으로 갱신한다."""
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _fill_slots(strat)
        for price in (kit.line - 200, kit.line + 50, kit.line + 100, kit.line - 50):
            assert _tick(strat, kit, price) == Signal.NONE
            assert strat._prev_price.get(kit.ticker) == price, (
                f"만석 틱 {price} 뒤 `_prev_price`={strat._prev_price.get(kit.ticker)} — "
                "만석 동안 직전 가격이 추적되지 않는다"
            )


def test_slot_freed_when_already_above_and_volume_short_then_latch_not_armed(kit):
    """T1 — 거래량이 미달이어도 거짓 교차가 래치를 무장하면 안 된다.

    09-23 에이치브이엠 유형: 매도 15초 뒤 래치가 무장되고 뒤늦게 거래량이 차서 샀다.
    거짓 교차가 거래량 게이트에 닿는 것 자체가 결함이다.
    """
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        tick_volume.record_acml_vol(kit.ticker, kit.short_vol)
        held = _fill_slots(strat)
        for price in (kit.line - 100, kit.line + 100):
            _tick(strat, kit, price)
        _free_one_slot(strat, held)

        assert _tick(strat, kit, kit.line + 100) == Signal.NONE
        assert kit.ticker not in strat._vol_latch, (
            "슬롯이 빈 첫 틱이 거래량 게이트에 닿아 래치를 무장했다 — 뒤늦게 거래량이 "
            "차면 진짜 돌파 없이 매수된다"
        )

        tick_volume.record_acml_vol(kit.ticker, kit.enough_vol)
        assert _tick(strat, kit, kit.line + 150) == Signal.NONE


def test_slot_full_tracking_ignores_entry_window(kit):
    """T1 — 만석 추적은 매수 시간 창과 무관하다(만석이라 NONE 인 그 지점에서 수행)."""
    strat = kit.make()
    with freeze_time(OUT_OF_WINDOW):
        _fill_slots(strat)
        assert _tick(strat, kit, kit.line + 100) == Signal.NONE
        assert strat._prev_price.get(kit.ticker) == kit.line + 100


def test_slot_full_tracking_touches_nothing_else(kit):
    """T1 — 만석 추적은 `_prev_price` 말고 다른 상태를 바꾸지 않는다(새 카운터 없음)."""
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        tick_volume.record_acml_vol(kit.ticker, kit.enough_vol)
        _fill_slots(strat)
        before = {
            "scan_stats": copy.deepcopy(strat._scan_stats),
            "candidates": copy.deepcopy(strat._candidates),
            "positions": set(strat.state.positions),
            "pending": set(strat.state.pending_buys),
        }
        for price in (kit.line - 100, kit.line + 100, kit.line - 50, kit.line + 80):
            _tick(strat, kit, price)

    assert strat._scan_stats == before["scan_stats"], "만석 추적이 `_scan_stats` 를 건드렸다"
    assert strat._candidates == before["candidates"], "만석 추적이 `_candidates` 를 바꿨다"
    assert set(strat.state.positions) == before["positions"]
    assert set(strat.state.pending_buys) == before["pending"]
    assert strat._vol_latch == {}
    assert strat._bought_today == set()
    assert strat._cooldown_until == {}
    assert strat._position_setup == {}
    assert getattr(strat, "_entry_atr", {}) == {}
    assert strat.state.buy_signals == []


# ###########################################################################
# T2 — 진짜 재돌파는 산다 (「고친 뒤 영영 못 사는」 회귀 차단)
# ###########################################################################

def test_slot_freed_then_real_recross_buys(kit):
    """T2 — 슬롯이 빈 뒤 돌파선 아래로 내려갔다 다시 넘으면 정상대로 BUY."""
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        tick_volume.record_acml_vol(kit.ticker, kit.enough_vol)
        held = _fill_slots(strat)
        for price in (kit.line - 100, kit.line + 100):
            _tick(strat, kit, price)
        _free_one_slot(strat, held)

        assert _tick(strat, kit, kit.line + 100) == Signal.NONE      # 이미 선 위 — 안 산다
        assert _tick(strat, kit, kit.line - 50) == Signal.NONE       # 선 아래로 복귀
        assert _tick(strat, kit, kit.line + 100) == Signal.BUY, (
            "돌파선 아래에 있다가 다시 넘는 진짜 돌파인데 사지 않았다"
        )
    assert kit.ticker in strat._bought_today


def test_price_drops_below_line_while_full_then_cross_after_free_buys(kit):
    """T2 (대조군) — 만석 중 선 아래로 돌아온 종목은 슬롯이 빈 뒤 넘는 순간 산다.

    이 파일의 거래량·추격 상한 픽스처가 BUY 까지 닿는다는 양성 대조군이기도 하다
    (현 코드에서도 초록 — T1 이 수정 뒤 공허하게 초록이 되지 않게 한다).
    """
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        tick_volume.record_acml_vol(kit.ticker, kit.enough_vol)
        held = _fill_slots(strat)
        for price in (kit.line - 100, kit.line + 100, kit.line - 50):
            assert _tick(strat, kit, price) == Signal.NONE
        _free_one_slot(strat, held)

        assert _tick(strat, kit, kit.line + 100) == Signal.BUY
    assert kit.ticker in strat._bought_today


# ###########################################################################
# T4 — 래치 불가침
# ###########################################################################

def test_latched_ticker_untouched_while_full_above_low(kit, caplog):
    """T4 — 만석 전에 래치가 무장된 종목은 만석 동안 하단 위 틱이면 `_prev_price`·`_vol_latch` 그대로.

    기존 규약(001450 회귀): `_prev_price` 는 fresh 경로에서만 read-then-write 하고
    래치 재평가 경로에서는 건드리지 않는다. 하단 아래 틱은 아래 T4c(cycle460)가 본다.
    """
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        tick_volume.record_acml_vol(kit.ticker, kit.short_vol)
        strat._prev_price[kit.ticker] = kit.line - 100
        assert _tick(strat, kit, kit.line + 100) == Signal.NONE
        assert kit.ticker in strat._vol_latch, "픽스처 오류 — 래치가 무장되지 않았다"
        latch_before = dict(strat._vol_latch[kit.ticker])
        prev_before = strat._prev_price[kit.ticker]

        _fill_slots(strat)
        for price in (kit.line - 300, kit.line + 200, kit.low + 1, kit.line + 50):
            assert _tick(strat, kit, price) == Signal.NONE

    assert strat._prev_price[kit.ticker] == prev_before, "래치 무장 종목의 `_prev_price` 가 바뀌었다"
    assert strat._vol_latch.get(kit.ticker) == latch_before, "만석 추적이 래치를 건드렸다"
    assert _marker_records(caplog, kit) == [], "래치 무장 종목에 교차 스킵 로그가 찍혔다"


def test_latched_ticker_released_while_full_below_low(kit):
    """T4c (cycle460) — 만석 중 하단 아래 틱은 래치를 해제하고 그 틱부터 직전 가격을 추적한다."""
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        tick_volume.record_acml_vol(kit.ticker, kit.short_vol)
        strat._prev_price[kit.ticker] = kit.line - 100
        assert _tick(strat, kit, kit.line + 100) == Signal.NONE
        assert kit.ticker in strat._vol_latch, "픽스처 오류 — 래치가 무장되지 않았다"

        _fill_slots(strat)
        assert _tick(strat, kit, kit.low - 1) == Signal.NONE

    assert kit.ticker not in strat._vol_latch, "만석 중 하단 이탈인데 래치가 남았다"
    assert strat._prev_price[kit.ticker] == kit.low - 1


def test_stale_yesterday_latch_does_not_freeze_tracking_while_full(kit):
    """T4b — 어제 날짜로 무장된 낡은 래치는 불가침이 아니다.

    `_latch_entry` 가 읽는 순간 지우므로(fresh 경로와 같은 정리) 그 종목은 만석 동안에도
    계속 추적된다. 안 그러면 낡은 래치가 추적을 하루 종일 막아, 슬롯이 빈 첫 틱에
    `_prev_price` 가 얼어 있던 값(없음)으로 거짓 돌파가 난다.
    """
    strat = kit.make()
    low_key = kit.line_key.replace("high", "low")
    with freeze_time(IN_WINDOW):
        tick_volume.record_acml_vol(kit.ticker, kit.enough_vol)
        strat._vol_latch[kit.ticker] = {
            "armed_at": datetime(2026, 10, 11, 10, 0, 0),
            "armed_date": date(2026, 10, 11),
            kit.line_key: kit.line,
            low_key: kit.low,
        }
        held = _fill_slots(strat)

        assert _tick(strat, kit, kit.line - 100) == Signal.NONE
        assert strat._prev_price.get(kit.ticker) == kit.line - 100, "낡은 래치가 추적을 막았다"
        assert kit.ticker not in strat._vol_latch, "낡은 래치 엔트리가 남아 있다"

        assert _tick(strat, kit, kit.line + 100) == Signal.NONE
        _free_one_slot(strat, held)
        assert _tick(strat, kit, kit.line + 100) == Signal.NONE
    assert kit.ticker not in strat._bought_today


# ###########################################################################
# T5 — BFB 전용: 돌파 대기(retention) 중 만석이 되면 대기를 지운다
# ###########################################################################

def test_bfb_pending_retention_dropped_when_slots_fill():
    """T5 — retention 대기 중 만석이 되면 대기가 지워지고, 슬롯이 빈 뒤 retention
    경과 틱이 와도 BUY 가 아니다(새 교차 필요)."""
    strat = _make_bfb(retention_minutes=3)
    with freeze_time("2026-10-12 10:00:00"):
        tick_volume.record_acml_vol(BFB.ticker, BFB.enough_vol)
        strat._prev_price[BFB.ticker] = BFB.line - 100
        assert _tick(strat, BFB, BFB.line + 100) == Signal.NONE
        assert BFB.ticker in strat._breakout_first_seen, "픽스처 오류 — 대기가 등록되지 않았다"
        held = _fill_slots(strat)

    with freeze_time("2026-10-12 10:01:00"):
        assert _tick(strat, BFB, BFB.line + 100) == Signal.NONE
        assert BFB.ticker not in strat._breakout_first_seen, (
            "만석인데 돌파 대기가 남아 있다 — 슬롯이 빈 뒤 낡은 대기가 retention 완주로 읽힌다"
        )
        _free_one_slot(strat, held)

    with freeze_time("2026-10-12 10:04:00"):
        tick_volume.record_acml_vol(BFB.ticker, BFB.enough_vol)
        sig = _tick(strat, BFB, BFB.line + 100)

    assert sig == Signal.NONE, (
        f"슬롯이 빈 뒤 retention 경과 틱에 {sig} — 만석 전의 낡은 돌파 대기로 샀다"
    )
    assert BFB.ticker not in strat._bought_today
    assert BFB.ticker not in strat._vol_latch
    assert BFB.ticker not in strat._breakout_first_seen


def test_bfb_slot_freed_when_already_above_then_no_retention_wait_registered():
    """T5 — retention>0 에서도 슬롯이 빈 첫 틱(이미 선 위)이 돌파 대기를 새로 만들지 않는다.

    현 코드는 이 틱을 「돌파 1차 감지」로 등록하고 retention 뒤 산다.
    """
    strat = _make_bfb(retention_minutes=3)
    with freeze_time("2026-10-12 10:00:00"):
        tick_volume.record_acml_vol(BFB.ticker, BFB.enough_vol)
        held = _fill_slots(strat)
        for price in (BFB.line - 100, BFB.line + 100):
            _tick(strat, BFB, price)
        _free_one_slot(strat, held)
        assert _tick(strat, BFB, BFB.line + 100) == Signal.NONE
        assert BFB.ticker not in strat._breakout_first_seen, (
            "이미 선 위에 있던 종목을 「돌파 1차 감지」로 등록했다"
        )

    with freeze_time("2026-10-12 10:04:00"):
        tick_volume.record_acml_vol(BFB.ticker, BFB.enough_vol)
        assert _tick(strat, BFB, BFB.line + 100) == Signal.NONE
    assert BFB.ticker not in strat._bought_today


def test_bfb_pending_retention_dropped_while_full_does_not_count_retreat():
    """T5 — 만석이 지운 대기는 「후퇴」가 아니다(`breakout_retreat_count` 무변경)."""
    strat = _make_bfb(retention_minutes=3)
    with freeze_time(IN_WINDOW):
        strat._prev_price[BFB.ticker] = BFB.line - 100
        _tick(strat, BFB, BFB.line + 100)
        stats_before = copy.deepcopy(strat._scan_stats)
        _fill_slots(strat)
        _tick(strat, BFB, BFB.line - 50)

    assert BFB.ticker not in strat._breakout_first_seen
    assert strat._scan_stats == stats_before


# ###########################################################################
# T6 — 관측: 만석 중 교차는 하루 1회/종목만 기록
# ###########################################################################

def test_full_cross_logged_once_per_ticker_per_day(kit, caplog):
    """T6 — 만석 중 교차 틱에서 `[bfb|vcp_full_cross_skipped]` INFO 1줄, 같은 날 재교차는 무음."""
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _fill_slots(strat)
        _tick(strat, kit, kit.line - 100)
        assert _marker_records(caplog, kit) == [], "교차가 아닌 틱에 로그가 찍혔다"

        _tick(strat, kit, kit.line + 100)          # 교차 1
        recs = _marker_records(caplog, kit)
        assert len(recs) == 1, (
            f"만석 중 교차 로그가 {len(recs)}줄 — 「만석이라 놓친 돌파」가 기록되지 않는다. "
            f"records={[(r.name, r.levelname, r.getMessage()) for r in caplog.records]}"
        )
        msg = recs[0].getMessage()
        for field in (
            f"ticker={kit.ticker}",
            f"{kit.line_key}={kit.line}",
            f"price={kit.line + 100}",
            f"prev={kit.line - 100}",
        ):
            assert field in msg.split(), f"로그에 `{field}` 필드가 없다: {msg}"

        _tick(strat, kit, kit.line + 150)          # 위→위 (교차 아님)
        _tick(strat, kit, kit.line - 50)           # 후퇴
        _tick(strat, kit, kit.line + 100)          # 교차 2 — cap
        assert len(_marker_records(caplog, kit)) == 1, "같은 날 같은 종목에 두 번 찍혔다"


def test_full_cross_log_cap_resets_next_day(kit, caplog):
    """T6 — cap 은 「일」 단위다: 다음 날 만석 중 교차는 다시 1줄."""
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _fill_slots(strat)
        _tick(strat, kit, kit.line - 100)
        _tick(strat, kit, kit.line + 100)
    with freeze_time(NEXT_DAY_IN_WINDOW):
        _tick(strat, kit, kit.line - 100)
        _tick(strat, kit, kit.line + 100)

    assert len(_marker_records(caplog, kit)) == 2


def test_first_seen_above_line_while_full_logs_nothing_but_tracks_price(kit, caplog):
    """T6 — 만석 중 처음 본 틱이 이미 선 위(`prev` 없음)면 교차가 아니라 첫 관측이다.

    로그는 내지 않고 `_prev_price` 만 그 틱 가격으로 채운다.
    """
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _fill_slots(strat)
        assert kit.ticker not in strat._prev_price
        assert _tick(strat, kit, kit.line + 100) == Signal.NONE

    assert _marker_records(caplog, kit) == [], "prev 없는 첫 틱에 교차 로그가 찍혔다"
    assert strat._prev_price.get(kit.ticker) == kit.line + 100


def test_first_seen_above_line_while_full_then_later_cross_still_logs(kit, caplog):
    """T6 — 첫 관측 틱이 로그 cap 을 소비하지 않는다: 이후 진짜 교차는 여전히 1줄."""
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _fill_slots(strat)
        _tick(strat, kit, kit.line + 100)          # 첫 관측 (선 위) — 무음
        _tick(strat, kit, kit.line - 100)          # 후퇴
        _tick(strat, kit, kit.line + 100)          # 진짜 교차

    assert len(_marker_records(caplog, kit)) == 1


def test_full_cross_log_failure_does_not_change_behavior(kit, monkeypatch):
    """T6 — 로그가 실패해도 `_prev_price` 는 갱신되고 NONE 을 돌려준다(행위는 cap 밖)."""
    strat = kit.make()

    def _boom(*args, **kwargs):
        raise RuntimeError("log sink down")

    with freeze_time(IN_WINDOW):
        _fill_slots(strat)
        _tick(strat, kit, kit.line - 100)
        monkeypatch.setattr(logging.getLogger(kit.logger_name), "info", _boom)
        assert _tick(strat, kit, kit.line + 100) == Signal.NONE
        assert strat._prev_price.get(kit.ticker) == kit.line + 100, (
            "관측 로그 실패가 직전 가격 갱신을 막았다"
        )


# ###########################################################################
# T7 — never-raise
# ###########################################################################

@pytest.mark.parametrize(
    "broken",
    [
        {"unrelated": 1},                 # 돌파선 키 없음
        {"__line__": None},               # 돌파선 None
        {"__line__": "not-a-number"},     # 돌파선 비수치
        [1, 2, 3],                        # dict 가 아닌 truthy
    ],
    ids=["missing_key", "none_line", "str_line", "non_dict"],
)
def test_slot_full_tracking_never_raises_on_broken_candidate(kit, broken):
    """T7 — 후보 엔트리가 깨져 있어도 만석이면 NONE 이고 예외가 새지 않는다.

    `check_buy_signal` 예외는 `risk.on_tick` 을 죽여 그 틱의 청산 평가까지 멈춘다.
    """
    strat = kit.make()
    if isinstance(broken, dict) and "__line__" in broken:
        broken = {kit.line_key: broken["__line__"]}
    strat._candidates[kit.ticker] = broken
    with freeze_time(IN_WINDOW):
        _fill_slots(strat)
        assert _tick(strat, kit, kit.line + 100) == Signal.NONE


# ###########################################################################
# T8 — 후보 아님 · 가격 0
# ###########################################################################

def test_slot_full_non_candidate_creates_no_prev_price(kit):
    """T8 — 후보가 아닌 종목은 만석 동안 `_prev_price` 를 만들지 않는다."""
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _fill_slots(strat)
        assert strat.check_buy_signal("123456", kit.line + 100, kit.open_price) == Signal.NONE
    assert "123456" not in strat._prev_price


@pytest.mark.parametrize("bad_price", [0, -1])
def test_slot_full_non_positive_price_leaves_prev_price(kit, bad_price):
    """T8 — `current_price <= 0` 은 `_prev_price` 를 만들지도 덮지도 않는다."""
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _fill_slots(strat)
        assert _tick(strat, kit, bad_price) == Signal.NONE
        assert kit.ticker not in strat._prev_price

        _tick(strat, kit, kit.line - 100)
        assert _tick(strat, kit, bad_price) == Signal.NONE
        assert strat._prev_price.get(kit.ticker) == kit.line - 100
