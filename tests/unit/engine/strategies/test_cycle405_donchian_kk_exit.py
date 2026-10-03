"""cycle405 Red — donchian 깡토식 청산: `check_exit_signal` · `get_effective_stop_price` (명세 §1·§2·§4).

명세 정본 = `_workspace/red/cycle405_donchian_kkangto_spec.md` §9 1·2·3·4·7
자문 = `_workspace/domain_consult/cycle405_donchian_kkangto.md` §2 · §10

계약 요약
- R = max(kk_r_floor_pct/100 × E, kk_r_atr_mult × N). N = `_entry_atr[t]`(없거나 0 이하면 ATR 항 0 → R = 0.08E).
- 손절선 = E − R. 고점 H ≥ E + 3R(무장)이면 손절선 = max(E − R, E) = E. 현재가 ≤ 손절선 → STOP_LOSS.
- 무장일 때만 10일 저가 채널: 현재가 < `_channel_low[t]` → TRAILING_STOP. 무장 전에는 채널을 보지 않는다.
- 옛 청산(2N·−9% 받침선·미스탬프 고정%·1.5N 승격·샹들리에·돌파 실패 시간 청산)은 donchian 이 더 읽지 않는다.
- 시간 청산은 `check_exit_signal` 에 없다(15:20 `check_force_clear` 만).
- 미러 = max(손절선, 무장일 때 채널) 의 양수 `int`. 같은 헬퍼를 쓴다(AST G-405-4).

각 케이스는 옛 규칙과 **값이 갈리는 입력**을 골랐다(옛 규칙에서도 우연히 같은 답이 나오는
92,000·91,000 경계는 명세 §9-1 그대로 두되, 갈리는 N=3,000·7,000 케이스를 함께 둔다).

시계: aware KST 로 고정. 매수일은 보유일 관측(`[days_held_observe]`)만 쓰고 판정에는 닿지 않는다.
"""
from __future__ import annotations

import logging
from datetime import date

import pytest
from freezegun import freeze_time

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

T = "990405"                       # 합성 종목
E = 100_000                        # 매수가
NOW = "2026-10-05T10:00:00+09:00"  # 월 · 장중
BUY_DATE = date(2026, 10, 1)       # 목
DC_LOGGER = "src.engine.strategies.donchian_swing"


def _mk(**params) -> DonchianSwingStrategy:
    cfg = StrategyConfig(
        strategy_id="donchian_swing", name="도치안", weight=0.2,
        params={"market_unit_mode": "off", **params},
    )
    s = DonchianSwingStrategy(cfg)
    s.state.total_investment = 743_000
    return s


def _hold(s, *, high: int = E, n: float | None = None, channel: int | None = None,
          buy_price: int = E, buy_date: date | None = BUY_DATE, ticker: str = T) -> Position:
    pos = Position(ticker=ticker, buy_price=buy_price, quantity=1, order_no="O405",
                   strategy_id="donchian_swing", buy_date=buy_date or BUY_DATE)
    if buy_date is None:
        pos.buy_date = None
    pos.high_since_buy = high
    s.state.positions[ticker] = pos
    if n is not None:
        s._entry_atr[ticker] = n
    if channel is not None:
        s._channel_low[ticker] = channel
    return pos


def _exit(s, price: int, ticker: str = T) -> Signal:
    return s.check_exit_signal(ticker, price, price)


# ===========================================================================
# 1. R 두 갈래 (명세 §9-1)
# ===========================================================================
@freeze_time(NOW)
@pytest.mark.parametrize("n, stop", [(4_000, 92_000), (6_000, 91_000), (3_000, 92_000), (7_000, 89_500)])
def test_r1_stop_line_is_entry_minus_r_when_stamped_then_stop_loss_at_line(n, stop):
    """R = max(8%·E, 1.5·N) — 손절선에서 STOP_LOSS, 1원 위에서 NONE."""
    s = _mk()
    _hold(s, n=n)
    assert _exit(s, stop) == Signal.STOP_LOSS, f"N={n}: 손절선 {stop} 에서 STOP_LOSS"
    assert _exit(s, stop + 1) == Signal.NONE, f"N={n}: 손절선 {stop}+1 은 NONE"


@freeze_time(NOW)
def test_r1_floor_branch_when_small_atr_then_not_old_2n_stop():
    """N=3,000 — 옛 2N 손절(94,000)은 사라지고 8% 하한(92,000)만 남는다."""
    s = _mk()
    _hold(s, n=3_000)
    assert _exit(s, 93_000) == Signal.NONE, "93,000 은 옛 2N 손절선(94,000) 아래지만 새 손절선(92,000) 위"


@freeze_time(NOW)
def test_r1_atr_branch_when_large_atr_then_not_old_9pct_backstop():
    """N=7,000 — R=10,500(10.5%). 옛 −9% 받침선(91,000)이 더 이르게 자르지 않는다."""
    s = _mk()
    _hold(s, n=7_000)
    assert _exit(s, 90_000) == Signal.NONE, "−10% 는 옛 받침선 아래지만 새 손절선(89,500) 위"


# ===========================================================================
# 2. 스탬프 없음 → R = 0.08E (명세 §9-2)
# ===========================================================================
@freeze_time(NOW)
@pytest.mark.parametrize("stamp", [None, 0, -5.0])
def test_r2_no_stamp_when_entry_atr_absent_or_nonpositive_then_r_is_8pct(stamp):
    s = _mk()
    _hold(s, n=stamp)
    assert _exit(s, 92_500) == Signal.NONE, "옛 미스탬프 −7% 고정 손절(93,000)이 아니라 R=8% 를 탄다"
    assert _exit(s, 92_000) == Signal.STOP_LOSS


@freeze_time(NOW)
def test_r2_no_stamp_ignores_stop_loss_rate_param():
    """`stop_loss_rate` 를 −2% 로 조여도 donchian 청산은 그 키를 읽지 않는다(§7.3)."""
    s = _mk(stop_loss_rate=-2.0)
    _hold(s)
    assert _exit(s, 97_000) == Signal.NONE


# ===========================================================================
# 3. 무장 경계 (명세 §9-3) — E=100,000 · N=4,000 → R=8,000 · 3R 고점 = 124,000
# ===========================================================================
@freeze_time(NOW)
def test_r3_unarmed_when_high_below_3r_then_channel_break_is_none():
    s = _mk()
    _hold(s, n=4_000, high=123_999, channel=110_000)
    assert _exit(s, 105_000) == Signal.NONE, "무장 전에는 채널 이탈을 보지 않는다"


@freeze_time(NOW)
def test_r3_unarmed_stop_stays_entry_minus_r():
    s = _mk()
    _hold(s, n=4_000, high=123_999)
    assert _exit(s, 92_001) == Signal.NONE
    assert _exit(s, 92_000) == Signal.STOP_LOSS
    assert _exit(s, 99_000) == Signal.NONE, "무장 전에는 본전 손절이 없다"


@freeze_time(NOW)
def test_r3_armed_when_high_reaches_3r_then_stop_is_breakeven():
    s = _mk()
    _hold(s, n=4_000, high=124_000)
    assert _exit(s, 100_000) == Signal.STOP_LOSS, "무장 후 손절선 = E(본전) — 사유는 STOP_LOSS"
    assert _exit(s, 100_001) == Signal.NONE


@freeze_time(NOW)
def test_r3_armed_when_price_below_channel_then_trailing_stop():
    s = _mk()
    _hold(s, n=4_000, high=124_000, channel=110_000)
    assert _exit(s, 109_999) == Signal.TRAILING_STOP
    assert _exit(s, 110_000) == Signal.NONE, "채널은 엄격 부등호(현재가 < 채널)"


@freeze_time(NOW)
def test_r3_armed_stop_has_priority_over_channel():
    s = _mk()
    _hold(s, n=4_000, high=124_000, channel=110_000)
    assert _exit(s, 100_000) == Signal.STOP_LOSS, "손절선이 채널보다 먼저 평가된다"


@freeze_time(NOW)
def test_r3_armed_channel_off_when_period_zero():
    s = _mk(channel_exit_period=0)
    _hold(s, n=4_000, high=124_000, channel=110_000)
    assert _exit(s, 105_000) == Signal.NONE


@freeze_time(NOW)
def test_r3_unstamped_arming_uses_8pct_r():
    """스탬프 없음 → R=8,000 → 3R 고점 124,000 동일."""
    s = _mk()
    _hold(s, high=124_000, channel=110_000)
    assert _exit(s, 109_999) == Signal.TRAILING_STOP
    _hold(s, high=123_999, channel=110_000)
    assert _exit(s, 109_999) == Signal.NONE


@freeze_time(NOW)
def test_r3_kk_breakeven_r_param_moves_arming_line():
    """`kk_breakeven_r=2.0` → 무장 고점 = E + 2R = 116,000."""
    s = _mk(kk_breakeven_r=2.0)
    _hold(s, n=4_000, high=116_000, channel=110_000)
    assert _exit(s, 109_999) == Signal.TRAILING_STOP
    _hold(s, n=4_000, high=115_999, channel=110_000)
    assert _exit(s, 109_999) == Signal.NONE


# ===========================================================================
# 4. 옛 청산이 죽었다 (명세 §9-4) — 새 손절선 위에서는 전부 NONE
# ===========================================================================
@freeze_time(NOW)
def test_r4_chandelier_is_dead():
    """옛 샹들리에 = 110,000 − 2.0×4,000 = 102,000. 101,000 은 그 아래."""
    s = _mk()
    _hold(s, n=4_000, high=110_000)
    s._candidates[T] = {"prev_close": E, "atr": 4_000, "ema60": 0, "donchian_high": 0}
    assert _exit(s, 101_000) == Signal.NONE


@freeze_time(NOW)
def test_r4_breakout_fail_time_exit_is_dead():
    """옛 §2.5 — 돌파선 105,000 아래 · 보유 10영업일 ≥ n_days 2 → 옛 TIME_EXIT."""
    s = _mk(breakout_fail_n_days=2)
    _hold(s, n=4_000, high=101_000, buy_date=date(2026, 9, 21))
    s._breakout_high[T] = 105_000
    assert _exit(s, 101_000) == Signal.NONE


@freeze_time(NOW)
def test_r4_time_exit_never_from_check_exit_signal_even_when_due():
    """20봉 · +1R 미도달 · 손절선 위 — 시간 청산은 15:20 경로만(§2), 틱 경로는 NONE."""
    s = _mk()
    _hold(s, n=4_000, high=101_000, buy_date=date(2026, 6, 1))   # 보유 ≫ 20영업일(폴백 계상)
    assert _exit(s, 99_000) == Signal.NONE


@freeze_time(NOW)
def test_r4_backstop_9pct_is_dead():
    s = _mk()
    _hold(s, n=7_000)
    assert _exit(s, 90_500) == Signal.NONE, "−9.5% 지만 새 손절선 89,500 위"


@freeze_time(NOW)
def test_r4_backstop_param_is_not_read():
    s = _mk(turtle_backstop_pct=-1.0)
    _hold(s, n=4_000)
    assert _exit(s, 98_000) == Signal.NONE


@freeze_time(NOW)
def test_r4_breakeven_promote_1_5n_is_dead():
    """옛 1.5N 승격 고점 = 106,000 → 옛 손절선 100,000. 새 규칙은 3R(124,000) 전이라 92,000."""
    s = _mk()
    _hold(s, n=4_000, high=106_000)
    assert _exit(s, 99_000) == Signal.NONE


@freeze_time(NOW)
def test_r4_stop_atr_param_is_not_read():
    s = _mk(stop_atr=0.5)
    _hold(s, n=4_000)
    assert _exit(s, 97_000) == Signal.NONE, "stop_atr 0.5 → 옛 손절선 98,000 / 새 92,000"


@freeze_time(NOW)
def test_r4_malformed_buy_date_never_blocks_stop():
    """보유일 계산(관측·폴백 가시성)이 터져도 손절은 난다 — 손절 앞에 두는 것은 전부 never-raise.

    실재 경로: 테스트·복구 경로가 `buy_date` 를 문자열로 넣은 포지션(`test_swing_rest_poll.py` 픽스처).
    """
    s = _mk()
    pos = _hold(s, n=4_000)
    pos.buy_date = "2026-10-01"
    assert _exit(s, 92_000) == Signal.STOP_LOSS
    assert _exit(s, 92_001) == Signal.NONE


# ===========================================================================
# 7. 미러 일치 (명세 §9-7 · §4)
# ===========================================================================
@freeze_time(NOW)
@pytest.mark.parametrize(
    "n, high, channel, want",
    [
        (4_000, 110_000, 105_000, 92_000),    # 무장 전 — 채널 무시(옛 미러 105,000)
        (4_000, 124_000, 110_000, 110_000),   # 무장 — max(E, 채널)(옛 116,000 샹들리에)
        (4_000, 124_000, 95_000, 100_000),    # 무장 — 채널이 본전 아래면 본전
        (None, 100_000, None, 92_000),        # 스탬프 없음 — 0.08E(옛 −7% 93,000)
        (7_000, 100_000, None, 89_500),       # ATR 갈래(옛 받침선 91,000)
    ],
)
def test_r7_mirror_equals_kk_price_lines(n, high, channel, want):
    s = _mk()
    _hold(s, n=n, high=high, channel=channel)
    s._candidates[T] = {"prev_close": E, "atr": 4_000, "ema60": 0, "donchian_high": 0}
    got = s.get_effective_stop_price(T)
    assert isinstance(got, int) and got == want, f"미러 {got!r} != {want}"


@freeze_time(NOW)
def test_r7_mirror_boundary_agrees_with_exit_signal_unarmed():
    s = _mk()
    _hold(s, n=6_000, high=110_000)
    line = s.get_effective_stop_price(T)
    assert line == 91_000
    assert _exit(s, line) == Signal.STOP_LOSS
    assert _exit(s, line + 1) == Signal.NONE


@freeze_time(NOW)
def test_r7_mirror_is_read_only_and_silent(caplog):
    caplog.set_level(logging.DEBUG, logger=DC_LOGGER)
    s = _mk()
    _hold(s, n=4_000, high=124_000, channel=110_000)
    before = (dict(s._entry_atr), dict(s._channel_low), s.state.positions[T].high_since_buy)
    s.get_effective_stop_price(T)
    assert (dict(s._entry_atr), dict(s._channel_low), s.state.positions[T].high_since_buy) == before
    assert [r for r in caplog.records if r.name == DC_LOGGER] == [], "미러는 로그를 내지 않는다"


def test_r7_mirror_none_when_no_position():
    s = _mk()
    assert s.get_effective_stop_price(T) is None


# ===========================================================================
# §7.1 읽는 쪽 범위 — 벗어나거나 숫자가 아니면 기본값 + WARNING 1회/일
# ===========================================================================
@freeze_time(NOW)
@pytest.mark.parametrize("bad", [50.0, 1.0, "abc", None])
def test_r_floor_out_of_range_when_put_then_default_and_one_warning(caplog, bad):
    caplog.set_level(logging.INFO, logger=DC_LOGGER)
    s = _mk(kk_r_floor_pct=bad)
    _hold(s)                                   # 스탬프 없음 → R = 하한%만
    assert _exit(s, 92_001) == Signal.NONE
    assert _exit(s, 92_000) == Signal.STOP_LOSS, "범위 밖 하한은 기본 8% 로 읽는다"
    _exit(s, 95_000)
    warns = [r for r in caplog.records
             if r.name == DC_LOGGER and r.levelno >= logging.WARNING and "kk_r_floor_pct" in r.getMessage()]
    assert len(warns) == 1, f"WARNING 1회/일 — got {len(warns)}"
