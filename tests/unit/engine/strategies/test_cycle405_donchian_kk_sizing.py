"""cycle405 Red — donchian 깡토식 사이징·신호 거름·키 (명세 §5 · §6 · §7 · §8).

명세 정본 = `_workspace/red/cycle405_donchian_kkangto_spec.md` §9-8 · §9-9 · §9-10 · §7 · §8

계약 요약
- R_buy = max(kk_r_floor_pct/100 × P, kk_r_atr_mult × N), N = `_candidates[t]["atr"]`.
- 설계 랏 q = floor(B × m × risk_pct ÷ R_buy) → min(q, int(B × m × position_ratio) // P).
  q > 0 → `_apply_budget_limit(q, P, t)`(잔여 클램프가 부분 매수) · q = 0 → 0(1주 폴백·비중 낙하 없음).
- 스탬프: q > 0 이면 `_entry_atr[t] = N`. N 없음·0 이하 → 0 · 스탬프 없음. `sizing_mode` 를 보지 않는다.
- 신호 단계: 설계 랏 0 → NONE + `[donchian_kk_lot_zero]`(1회/종목/일) · 오늘 매수일 보유 + 주문 중 ≥
  `max_daily_entries`(3) → NONE + `[donchian_daily_entry_cap]`(1회/종목/일). 잔여 부족은 거르지 않는다.
- K축(`max_lot_units`)·ρ축(`max_lot_ratio_mult`)은 설계 랏에 닿지 않는다.

예산 B = 743,000 · m = 1 → 1R 손실 8,916원 · 「N 작음」이면 R = 0.08P → q = floor(111,450 / P).

시계: donchian 진입창은 naive `datetime.now()` 09:05~09:30, 시장 유닛·매수일은 KST 날짜 —
freezegun naive 문자열 `"2026-09-28 09:10:00"` 는 naive 09:10 · KST 18:10 **같은 날짜**다(cycle382 관례).
"""
from __future__ import annotations

import logging
from datetime import date

import pytest
from freezegun import freeze_time

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig
from tests.unit.engine._cycle382_support import DAY, field, lines, open_info, seed

pytestmark = pytest.mark.unit

T = "990405"
B = 743_000
SIGNAL_TIME = "2026-09-28 09:10:00"          # naive 09:10 · KST 날짜 09-28 (= DAY)
CALC_TIME = "2026-09-28T10:00:00+09:00"
YESTERDAY = date(2026, 9, 23)                # 추석 전 마지막 거래일
NEW_KEYS = {
    "kk_r_floor_pct": 8.0, "kk_r_atr_mult": 1.5, "kk_breakeven_r": 3.0,
    "kk_time_exit_bars": 20, "kk_time_exit_min_r": 1.0, "kk_max_hold_bars": 250,
    "max_daily_entries": 3,
}
OFF_KEYS = ("stop_atr", "atr_trail_mult", "breakeven_promote_atr", "breakout_fail_n_days",
            "turtle_backstop_pct", "stop_loss_rate", "min_vol_floor_pct")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, caplog):
    monkeypatch.setattr("src.engine.scanner.ticker_prices", {}, raising=False)
    try:
        from src.engine import account_risk_watcher

        account_risk_watcher.reset_state_for_test()
    except Exception:
        pass
    caplog.set_level(logging.INFO)
    open_info(caplog)
    yield


def _mk(budget: int = B, **params) -> DonchianSwingStrategy:
    s = DonchianSwingStrategy(StrategyConfig(
        strategy_id="donchian_swing", name="도치안", weight=0.2,
        params={"market_unit_mode": "off", **params},
    ))
    s.state.total_investment = budget
    return s


def _cand(s, price: int, atr=400, ticker: str = T) -> None:
    info = {"prev_close": price, "ema60": int(price * 0.9), "donchian_high": price}
    if atr is not None:
        info["atr"] = atr
    s._candidates[ticker] = info


def _hold(s, ticker: str, buy_date: date, buy_price: int = 10_000) -> None:
    s.state.positions[ticker] = Position(ticker=ticker, buy_price=buy_price, quantity=1, order_no="O",
                                         strategy_id="donchian_swing", buy_date=buy_date)


def _marker(caplog, marker: str) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.levelno >= logging.INFO and r.getMessage().startswith(marker + " ")]


def _signal(s, price: int, ticker: str = T) -> Signal:
    return s.check_buy_signal(ticker, price, price)


# ===========================================================================
# §7 키
# ===========================================================================
def test_k1_new_keys_with_defaults():
    d = DonchianSwingStrategy.DEFAULT_PARAMS
    got = {k: d.get(k, "<없음>") for k in NEW_KEYS}
    assert got == NEW_KEYS
    for k in ("kk_time_exit_bars", "kk_max_hold_bars", "max_daily_entries"):
        assert type(d[k]) is int, f"{k} 는 정수"


def test_k2_changed_defaults_and_budget_invariant():
    d = DonchianSwingStrategy.DEFAULT_PARAMS
    assert (d["risk_pct"], d["position_ratio"], d["max_positions"], d["sizing_mode"],
            d["channel_exit_period"]) == (0.012, 0.15, 6, "turtle", 10)
    assert d["position_ratio"] * d["max_positions"] <= 1.0


def test_k3_off_keys_kept_this_cycle_and_buy_paused_kept():
    """D7 — 끄는 키는 이번엔 지우지 않는다. buy_paused 는 절대 지우지 않는다."""
    d = DonchianSwingStrategy.DEFAULT_PARAMS
    assert [k for k in OFF_KEYS if k not in d] == []
    assert d["buy_paused"] is False
    assert d["max_lot_units"] == 2.0 and d["max_lot_ratio_mult"] == 2.5


def test_k4_catalog_registers_new_keys_not_auto_tunable():
    from src.engine import param_catalog as pc

    keys = set(pc.keys_for_strategy("donchian_swing"))
    assert [k for k in NEW_KEYS if k not in keys] == [], "param_catalog 등록(화면 라벨·그룹)"
    assert [k for k in NEW_KEYS if k in set(pc.auto_tunable_keys())] == [], "자동 튜닝 불가"


# ===========================================================================
# 8. 사이징 (명세 §9-8)
# ===========================================================================
@freeze_time(CALC_TIME)
@pytest.mark.parametrize("price, qty", [(111_450, 1), (111_451, 0), (55_725, 2), (10_000, 11)])
def test_r8_design_lot_floor_r_branch(price, qty):
    s = _mk()
    _cand(s, price, atr=10)
    assert s.calc_buy_quantity(price, T) == qty


@freeze_time(CALC_TIME)
def test_r8_atr_branch_when_wide_atr():
    """N=1,000 → R = max(800, 1,500) = 1,500 → q = floor(8,916/1,500) = 5 (명목 상한 11)."""
    s = _mk()
    _cand(s, 10_000, atr=1_000)
    assert s.calc_buy_quantity(10_000, T) == 5


@freeze_time(CALC_TIME)
def test_l6_r_at_least_half_price_blocks_buy():
    """cycle405 리뷰 L6 — R ≥ 0.5×가격이면 설계 랏이 0(손절선이 매수가의 절반 이하로
    내려가는 종목을 사지 않는다). N=4,000 → R = max(800, 6,000) = 6,000 = 0.6×가격."""
    s = _mk()
    _cand(s, 10_000, atr=4_000)
    assert s.calc_buy_quantity(10_000, T) == 0
    assert T not in s._entry_atr


@freeze_time(CALC_TIME)
def test_l6_r_just_under_half_price_still_buys():
    """경계 바로 아래(R < 0.5×가격)는 평소대로 매수한다 — 과잉 차단 금지.
    N=3,000 → R = max(800, 4,500) = 4,500 = 0.45×가격 → q = floor(8,916/4,500) = 1."""
    s = _mk()
    _cand(s, 10_000, atr=3_000)
    assert s.calc_buy_quantity(10_000, T) == 1
    assert s._entry_atr[T] == 3_000


@freeze_time(CALC_TIME)
def test_r8_no_one_share_fallback_and_no_ratio_fallthrough():
    """q=0 이면 0 — 잔여가 충분해도 1주를 사지 않고, position_ratio 경로로 떨어지지 않는다."""
    s = _mk(budget=10_000_000)
    _cand(s, 1_600_000, atr=10)
    # R = 128,000 → 120,000 / 128,000 = 0.94 → q=0. 잔여 10,000,000 이라 옛 1주 폴백이면 1주였다
    assert s.calc_buy_quantity(1_600_000, T) == 0
    assert T not in s._entry_atr


@freeze_time(CALC_TIME)
@pytest.mark.parametrize("sizing_mode", ["turtle", "position_ratio"])
def test_r8_stamp_equals_sizing_atr_and_sizing_mode_is_not_read(sizing_mode):
    s = _mk(sizing_mode=sizing_mode)
    _cand(s, 10_000, atr=400)
    assert s.calc_buy_quantity(10_000, T) == 11
    assert s._entry_atr.get(T) == 400


@freeze_time(CALC_TIME)
@pytest.mark.parametrize("atr", [None, 0, -3])
def test_r8_missing_atr_then_zero_and_no_stamp(atr):
    s = _mk()
    _cand(s, 10_000, atr=atr)
    assert s.calc_buy_quantity(10_000, T) == 0
    assert T not in s._entry_atr


@freeze_time(CALC_TIME)
def test_r8_remaining_budget_clamp_makes_partial_buy():
    """설계 랏 11 · 잔여 50,000 → 5주(관문의 잔여 클램프)."""
    s = _mk()
    _cand(s, 10_000, atr=400)
    _hold(s, "990900", YESTERDAY, buy_price=B - 50_000)
    assert s.calc_buy_quantity(10_000, T) == 5


@freeze_time(CALC_TIME)
def test_r8_enforce_half_m_halves_design_lot_and_logs_market_unit(caplog):
    s = _mk(market_unit_mode="enforce")
    seed(s, 0.5)
    _cand(s, 10_000, atr=400)
    assert s.calc_buy_quantity(10_000, T) == 5, "B×0.5 판: floor(4,458/800)=5 · 명목 55,725//10,000=5"
    assert s._entry_atr.get(T) == 400
    ln = [x for x in lines(caplog, "[market_unit]") if "where=calc" in x]
    assert ln and field(ln[0], "lot_before") == "11" and field(ln[0], "lot_after") == "5", ln


@freeze_time(CALC_TIME)
def test_r8_shadow_half_m_keeps_full_lot_but_logs_both(caplog):
    s = _mk(market_unit_mode="shadow")
    seed(s, 0.5)
    _cand(s, 10_000, atr=400)
    assert s.calc_buy_quantity(10_000, T) == 11
    ln = [x for x in lines(caplog, "[market_unit]") if "where=calc" in x]
    assert ln and field(ln[0], "lot_before") == "11" and field(ln[0], "lot_after") == "5", ln


@freeze_time(CALC_TIME)
def test_r8_enforce_half_m_no_fallback_when_design_lot_zero():
    s = _mk(market_unit_mode="enforce")
    seed(s, 0.5)
    _cand(s, 111_450, atr=10)            # m=1 → 1주, m=0.5 → 0
    assert s.calc_buy_quantity(111_450, T) == 0


@freeze_time(CALC_TIME)
def test_r8_enforce_zero_state_calc_zero():
    s = _mk(market_unit_mode="enforce")
    seed(s, 0.0)
    _cand(s, 10_000, atr=400)
    assert s.calc_buy_quantity(10_000, T) == 0


def _kk_oracle(budget: int, used: int, price: int, atr) -> int:
    """명세 §5 를 옮겨 적은 m=1 오라클 — 설계 랏 → 잔여 클램프(관문). K·ρ 축은 항등 무접촉.

    cycle405 리뷰 L6 — R ≥ 0.5×가격이면 손절선이 매수가의 절반 이하가 되어 0.
    """
    if atr is None or atr <= 0:
        return 0
    r = max(0.08 * price, 1.5 * atr)
    if r >= 0.5 * price:
        return 0
    q = min(int(budget * 0.012 // r), int(budget * 0.15) // price)
    if q <= 0:
        return 0
    return min(q, max(0, budget - used) // price)


@freeze_time(CALC_TIME)
@pytest.mark.parametrize("m", [1.0, 0.75, 0.5, 0.0])
def test_r8_off_and_shadow_equal_kk_oracle_grid(m):
    """off · shadow 는 m 과 무관하게 m=1 설계 랏을 산다(shadow 는 기록만) — cycle382 R17 의 donchian 판."""
    import itertools

    for price, atr, budget, used in itertools.product(
        (10_000, 50_000, 150_000, 300_000), (None, 50, 500, 1_500, 20_000),
        (1_000_000, 5_000_000), (0, 600_000),
    ):
        got = {}
        for mode in ("off", "shadow"):
            s = _mk(budget=budget, market_unit_mode=mode)
            _cand(s, price, atr=atr)
            if used:
                s.state.pending_buy_amounts["OTHER"] = used
            seed(s, m)
            got[mode] = (s.calc_buy_quantity(price, T), dict(s._entry_atr))
        ctx = f"m={m} price={price} atr={atr} budget={budget} used={used}"
        want = _kk_oracle(budget, used, price, atr)
        assert got["off"][0] == want, f"off: {got['off'][0]} != {want} — {ctx}"
        assert got["shadow"] == got["off"], f"shadow 가 수량·스탬프를 바꿨다 — {ctx}"


# ===========================================================================
# 10. 관문·캡 무접촉 (명세 §9-10)
# ===========================================================================
@freeze_time(CALC_TIME)
@pytest.mark.parametrize("price, atr", [(10_000, 400), (10_000, 1_000), (55_725, 10), (3_000, 300)])
def test_r10_k_and_rho_caps_do_not_change_design_lot(price, atr):
    a = _mk()
    _cand(a, price, atr=atr)
    b = _mk(max_lot_units=20.0, max_lot_ratio_mult=20.0)
    _cand(b, price, atr=atr)
    assert a.calc_buy_quantity(price, T) == b.calc_buy_quantity(price, T) > 0


@freeze_time(CALC_TIME)
def test_r10_positive_lot_goes_through_budget_gate(monkeypatch):
    s = _mk()
    _cand(s, 10_000, atr=400)
    seen = []
    orig = s._apply_budget_limit

    def spy(qty, price, ticker=None):
        seen.append((qty, price, ticker))
        return orig(qty, price, ticker)

    monkeypatch.setattr(s, "_apply_budget_limit", spy)
    assert s.calc_buy_quantity(10_000, T) == 11
    assert seen == [(11, 10_000, T)], "q>0 은 관문에 설계 랏 그대로 넘긴다"
    seen.clear()
    _cand(s, 111_451, atr=10)
    assert s.calc_buy_quantity(111_451, T) == 0
    assert seen == [], "q=0 은 관문에 넘기지 않는다(관문의 1주 폴백 분기 차단)"


# ===========================================================================
# §6-1 신호 단계: 설계 랏 0 → NONE + 마커 (명세 §9-8)
# ===========================================================================
@freeze_time(SIGNAL_TIME)
def test_s1_lot_zero_when_price_above_reach_then_none_and_marker_once(caplog):
    s = _mk()
    _cand(s, 111_451, atr=10)
    assert _signal(s, 111_451) == Signal.NONE
    assert _signal(s, 111_451) == Signal.NONE
    m = _marker(caplog, "[donchian_kk_lot_zero]")
    assert len(m) == 1, f"1회/종목/일 — {m}"
    assert f"ticker={T}" in m[0] and "price=111451" in m[0]
    assert T not in s._breakout_high and not s.state.buy_signals, "거름은 매수 상태를 만들지 않는다"


@freeze_time(SIGNAL_TIME)
def test_s1_lot_one_when_price_at_reach_then_buy():
    s = _mk()
    _cand(s, 111_450, atr=10)
    assert _signal(s, 111_450) == Signal.BUY


@freeze_time(SIGNAL_TIME)
def test_s1_missing_atr_then_none():
    s = _mk()
    _cand(s, 10_000, atr=0)
    assert _signal(s, 10_000) == Signal.NONE


@freeze_time(SIGNAL_TIME)
def test_s1_funds_short_is_not_filtered_at_signal():
    """설계 랏 > 0 · 잔여 < 1주 — 거르지 않는다(기존 자금 경로가 맞는 귀인)."""
    s = _mk()
    _cand(s, 10_000, atr=400)
    _hold(s, "990900", YESTERDAY, buy_price=B - 5_000)
    assert _signal(s, 10_000) == Signal.BUY


@freeze_time(SIGNAL_TIME)
def test_s1_enforce_half_m_lot_zero_then_none():
    s = _mk(market_unit_mode="enforce")
    seed(s, 0.5)
    _cand(s, 111_450, atr=10)
    assert _signal(s, 111_450) == Signal.NONE


@freeze_time(SIGNAL_TIME)
def test_s1_buy_paused_stops_before_any_kk_marker(caplog):
    s = _mk(buy_paused=True)
    _cand(s, 111_451, atr=10)
    assert _signal(s, 111_451) == Signal.NONE
    assert _marker(caplog, "[donchian_kk_lot_zero]") == []


# ===========================================================================
# 9. 하루 신규 상한 (명세 §9-9)
# ===========================================================================
@freeze_time(SIGNAL_TIME)
def test_r9_daily_cap_when_two_held_today_and_one_pending_then_none_and_marker(caplog):
    s = _mk()
    _cand(s, 10_000, atr=400)
    _hold(s, "990101", DAY)
    _hold(s, "990102", DAY)
    s.state.pending_buys.add("990103")
    assert _signal(s, 10_000) == Signal.NONE
    assert _signal(s, 10_000) == Signal.NONE
    m = _marker(caplog, "[donchian_daily_entry_cap]")
    assert len(m) == 1, m
    assert f"ticker={T}" in m[0] and "count=3" in m[0] and "cap=3" in m[0]


@freeze_time(SIGNAL_TIME)
def test_r9_yesterday_holdings_are_not_counted():
    s = _mk()
    _cand(s, 10_000, atr=400)
    for t in ("990201", "990202", "990203"):
        _hold(s, t, YESTERDAY)
    _hold(s, "990101", DAY)
    _hold(s, "990102", DAY)
    assert _signal(s, 10_000) == Signal.BUY, "오늘 매수 2 + 주문 0 < 3 (어제 보유 3 은 세지 않는다)"


@freeze_time(SIGNAL_TIME)
def test_r9_cap_param_is_read():
    s = _mk(max_daily_entries=1)
    _cand(s, 10_000, atr=400)
    _hold(s, "990101", DAY)
    assert _signal(s, 10_000) == Signal.NONE


@freeze_time(SIGNAL_TIME)
def test_r9_lot_zero_filter_runs_before_daily_cap(caplog):
    s = _mk()
    _cand(s, 111_451, atr=10)
    _hold(s, "990101", DAY)
    _hold(s, "990102", DAY)
    s.state.pending_buys.add("990103")
    assert _signal(s, 111_451) == Signal.NONE
    assert len(_marker(caplog, "[donchian_kk_lot_zero]")) == 1
    assert _marker(caplog, "[donchian_daily_entry_cap]") == []


# ===========================================================================
# §8 LLM 매수평가 서술·산식 (관측 경로)
# ===========================================================================
@pytest.mark.parametrize("sizing_mode", ["turtle", "position_ratio"])
@pytest.mark.parametrize("atr_pct, want", [(4.0, -8.0), (6.0, -9.0), (None, -8.0)])
def test_l1_llm_stop_pct_is_minus_max_floor_and_atr_mult(sizing_mode, atr_pct, want):
    from src.engine import llm_buy_gate as g

    params = {**DonchianSwingStrategy.DEFAULT_PARAMS, "sizing_mode": sizing_mode}
    tech = {} if atr_pct is None else {"atr14_pct": atr_pct}
    # 실제 경로 = payload 의 최소 키 복사(`_read_stop_params`) → 재해석
    got = g._resolve_stop_loss_pct("donchian_swing", g._read_stop_params(params), tech)
    assert got == pytest.approx(want)


def test_l2_llm_exit_rule_text_is_kk():
    from src.engine import llm_buy_gate as g

    txt = g._read_exit_rule("donchian_swing", dict(DonchianSwingStrategy.DEFAULT_PARAMS))
    import re

    for token in ("1R", "본전", "15:20"):
        assert token in txt, f"{token!r} 없음: {txt}"
    assert re.search(r"3(\.0)?R", txt), f"3R(본전·채널 무장) 서술 없음: {txt}"
    assert "샹들리에" not in txt and "백스톱" not in txt, txt
