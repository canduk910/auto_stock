"""cycle382 Red — 시장 유닛: 4전략 `calc_buy_quantity` 설계 랏 축소 (R17~R31).

명세 = `_workspace/red/cycle382_market_unit_spec.md` §4 · §5 · §9 · §11.2(calc)

계약 요약(§5):
- 모드 `off`/`shadow` → **현행 수량 byte 동일**. shadow 는 m<1 이면 `[market_unit] … where=calc` 한 줄만 남긴다.
- `enforce` ∧ m<1 → 설계 랏만 `int(예산 × m)` 로 다시 잰다(터틀 유닛·비중 경로 모두).
  잔여(`예산 − 사용액`)·K축·ρ축은 **줄이지 않은 예산**으로 본다. `fraction=m` 금지(명목 상한이 안 줄어든다).
- 축소일에 설계 랏이 0 이면 `return 0` — 1주 폴백·터틀→비중 낙하 **없음**(원인 불문).
- 터틀 ATR 스탬프(`_entry_atr`)는 m 과 무관하게 사이징 ATR 그대로(손절선 불변).
- 스냅샷 없음·실패·헬퍼 예외 → m=1 과 같은 수량(fail-open) + WARNING.

시계: aware KST(`2026-09-28T10:00:00+09:00`) — 시장 유닛은 KST 날짜만 본다.
Red 유효성: `StrategyBase._market_unit_*`·leaf 가 없어 `[Red]` 로 실패한다(스냅샷을 심는 `seed` 가
먼저 실패한다). R17 의 산식 비교 자체는 현행 코드에서도 성립한다 — 구현 뒤 M26 「shadow 가 수량을
바꾼다」 를 잡는 몫이다.
"""
from __future__ import annotations

import itertools
import logging

import pytest
from freezegun import freeze_time

from src.engine.turtle_sizing import compute_unit_qty_guarded
from tests.unit.engine._cycle382_support import (
    ATR_KEY, DAY, T, TURTLE4, field, fnum, lines, make, need_base, open_info, seed,
)

pytestmark = pytest.mark.unit

_NOW = "2026-09-28T10:00:00+09:00"
_SB_LOGGER = "src.engine.strategy_base"


def _cand(s, sid: str, atr) -> None:
    """후보 dict — 그 전략의 **실제** ATR 키 하나만 둔다(키 불일치를 드러내려고)."""
    entry = {"prev_close": 10_000}
    if atr is not None:
        entry[ATR_KEY[sid]] = atr
    s._candidates[T] = entry


def _turtle(sid: str, *, mode="enforce", budget=1_000_000, risk=0.01, ratio=0.2, maxpos=5, **kw):
    return make(sid, budget=budget, mode=mode, sizing_mode="turtle", risk_pct=risk,
                position_ratio=ratio, max_positions=maxpos, **kw)


def _ratio_bfb(*, mode="enforce", budget=1_000_000, ratio=0.25):
    return make("bull_flag_breakout", budget=budget, mode=mode, sizing_mode="position_ratio",
                position_ratio=ratio, max_positions=4)


def _oracle(s, sid: str, price: int, ticker: str) -> int:
    """명세 이전 알고리즘(옮겨 적음) — 관문 본문은 A12 가 byte 고정하므로 그대로 부른다."""
    params = s.config.params
    if params.get("sizing_mode") == "turtle" and ticker is not None:
        atr = float((s._candidates.get(ticker) or {}).get(ATR_KEY[sid]) or 0)
        budget = int(s.state.total_investment)
        q = compute_unit_qty_guarded(
            budget, atr, price, float(params.get("risk_pct") or 0),
            remaining_budget=max(0, budget - s._calc_used_funds()),
            min_vol_pct=float(params.get("min_vol_floor_pct", 1.0)),
            position_ratio=float(params.get("position_ratio") or 0),
        )
        if q > 0:
            return s._apply_budget_limit(q, price, ticker)
    amount = int(s.state.total_investment * params["position_ratio"])
    return s._apply_budget_limit(amount // price, price, ticker)


def _calc_lines(caplog):
    return [ln for ln in lines(caplog, "[market_unit]") if field(ln, "where") == "calc"]


# ===========================================================================
# R17 — off · shadow 는 현행 byte 동일 (m 네 값 모두)
# ===========================================================================
_GRID = list(itertools.product(
    (10_000, 50_000, 150_000, 300_000),          # 가격
    (None, 50, 500, 1_500),                       # ATR (결측 · 저변동 · 보통 · 큼)
    (1_000_000, 5_000_000),                       # 예산
    (0, 600_000),                                 # 사용액(pending)
))


@freeze_time(_NOW)
# cycle405 — donchian 은 옛 오라클(터틀 유닛·비중 낙하) 대상이 아니다(깡토식 설계 랏). off·shadow
# 동치는 `test_cycle405_donchian_kk_sizing.py::test_r8_off_and_shadow_equal_kk_oracle_grid` 가 지킨다.
@pytest.mark.parametrize("sid,sizing", [
    ("kojiro", "turtle"), ("vcp_breakout", "turtle"),
    ("bull_flag_breakout", "turtle"), ("bull_flag_breakout", "position_ratio"),
])
@pytest.mark.parametrize("m", [1.0, 0.75, 0.5, 0.0])
def test_r17_off_and_shadow_equal_pre_spec_oracle(sid, sizing, m):
    for price, atr, budget, used in _GRID:
        got = {}
        for mode in ("off", "shadow"):
            s = make(sid, budget=budget, mode=mode, sizing_mode=sizing, risk_pct=0.01,
                     position_ratio=0.2, max_positions=5)
            _cand(s, sid, atr)
            if used:
                s.state.pending_buy_amounts["OTHER"] = used
            seed(s, m)
            got[mode] = (s.calc_buy_quantity(price, T), dict(getattr(s, "_entry_atr", {})))
        o = make(sid, budget=budget, mode="off", sizing_mode=sizing, risk_pct=0.01,
                 position_ratio=0.2, max_positions=5)
        _cand(o, sid, atr)
        if used:
            o.state.pending_buy_amounts["OTHER"] = used
        expect = _oracle(o, sid, price, T)
        ctx = f"{sid}/{sizing} m={m} price={price} atr={atr} budget={budget} used={used}"
        assert got["off"][0] == expect, f"off 가 현행과 다르다: {ctx}"
        assert got["shadow"][0] == expect, f"shadow 가 수량을 바꿨다(M26): {ctx}"
        assert got["shadow"][1] == got["off"][1], f"shadow 가 _entry_atr 스탬프를 바꿨다: {ctx}"


# ===========================================================================
# R18 — shadow 기록 (수량 불변 + 한 줄)
# ===========================================================================
def _kojiro_r18(mode: str):
    s = _turtle("kojiro", mode=mode, budget=2_000_000, risk=0.005, ratio=0.166, maxpos=6)
    _cand(s, "kojiro", 1_000.0)
    return s


@freeze_time(_NOW)
@pytest.mark.parametrize("m,after", [(0.75, 4), (0.5, 3)])
def test_r18_shadow_keeps_quantity_and_logs_lot_before_after(caplog, m, after):
    open_info(caplog)
    s = _kojiro_r18("shadow")
    seed(s, m)
    assert s.calc_buy_quantity(50_000, T) == 6, "shadow 인데 수량이 바뀌었다(M26)"
    ls = _calc_lines(caplog)
    assert len(ls) == 1, ls
    ln = ls[0]
    assert ln.split()[1:7] == [
        "strategy=kojiro", f"state={'up_falling' if m == 0.75 else 'down_rising'}",
        f"m={field(ln, 'm')}", "lot_before=6", f"lot_after={after}", "mode=shadow",
    ], "앞 6필드 순서는 과업 지정(strategy state m lot_before lot_after mode)"
    assert fnum(ln, "m") == m
    assert field(ln, "ticker") == T
    assert field(ln, "path") == "turtle"
    assert field(ln, "fallback") == "-"
    assert field(ln, "skip") == "0" and field(ln, "reason") == "-"
    assert int(field(ln, "price")) == 50_000


@freeze_time(_NOW)
def test_r18_shadow_zero_state_logs_would_skip_but_still_buys(caplog):
    open_info(caplog)
    s = _kojiro_r18("shadow")
    seed(s, 0.0)
    assert s.calc_buy_quantity(50_000, T) == 6
    ln = _calc_lines(caplog)[0]
    assert (field(ln, "lot_after"), field(ln, "skip"), field(ln, "reason")) == ("0", "1", "zero_state")


@freeze_time(_NOW)
def test_r18_m1_logs_nothing_and_calc_line_is_capped_per_ticker_day(caplog):
    open_info(caplog)
    s = _kojiro_r18("shadow")
    seed(s, 1.0)
    assert s.calc_buy_quantity(50_000, T) == 6
    assert _calc_lines(caplog) == [], "m=1 인데 시장 유닛 줄이 나왔다"
    s2 = _kojiro_r18("shadow")
    seed(s2, 0.5)
    s2.calc_buy_quantity(50_000, T)
    s2.calc_buy_quantity(50_000, T)
    assert len(_calc_lines(caplog)) == 1, "같은 (ticker, where) 줄이 하루 두 번 나왔다"


# ===========================================================================
# R19~R22 — enforce 축소 수량
# ===========================================================================
@freeze_time(_NOW)
@pytest.mark.parametrize("m,qty", [(1.0, 6), (0.75, 4), (0.5, 3)])
def test_r19_enforce_turtle_kojiro(m, qty):
    s = _kojiro_r18("enforce")
    seed(s, m)
    assert s.calc_buy_quantity(50_000, T) == qty


@freeze_time(_NOW)
def test_r20_remaining_budget_is_not_reduced():
    s = _turtle("donchian_swing")
    _cand(s, "donchian_swing", 500)
    s.state.pending_buy_amounts["OTHER"] = 500_000
    seed(s, 0.5)
    # cycle405 — donchian 설계 랏 = floor(1M×0.5×0.01 / max(800, 750)) = 6 (명목 상한 10)
    assert s.calc_buy_quantity(10_000, T) == 6, "잔여를 int(예산×m) 로 계산했다(M12) — 그러면 0"


@freeze_time(_NOW)
@pytest.mark.parametrize("m,qty", [(1.0, 20), (0.5, 10)])
def test_r21_notional_cap_also_scales_with_m(m, qty):
    # cycle405 — donchian 설계 랏은 R 이 묶는다. 명목 상한이 묶이도록 risk_pct 를 키운다
    # (floor(1M×m×0.05/800) = 62·31 > 명목 20·10).
    s = _turtle("donchian_swing", risk=0.05)
    _cand(s, "donchian_swing", 150)
    seed(s, m)
    assert s.calc_buy_quantity(10_000, T) == qty, "fraction=m 식이면 명목 상한이 안 줄어 20(M11)"


@freeze_time(_NOW)
@pytest.mark.parametrize("m,qty", [(1.0, 8), (0.75, 6), (0.5, 4)])
def test_r22_enforce_ratio_path_bfb(m, qty):
    s = _ratio_bfb()
    seed(s, m)
    assert s.calc_buy_quantity(30_000, T) == qty


# ===========================================================================
# X06 (리뷰 지적) — 비중 경로도 `lot_after = min(design_after, remaining_qty)` 로
# 잔여 클램프된다(§5.2). 터틀 경로만 격자 테스트(R20)가 있고 비중 경로는 미포함이었다.
# ===========================================================================
@freeze_time(_NOW)
def test_x06_ratio_path_lot_after_clamped_by_remaining_qty(caplog):
    """BFB 비중 경로, 예산 1,000,000 · position_ratio 0.25 · 사용 850,000 ·
    가격 30,000 · m=0.75 → `design_after = int(750,000×0.25)//30,000 = 6` 이지만
    잔여(150,000)가 5주치뿐이라 `lot_after` 는 **5**로 잘려야 한다. 클램프
    (`min(design_after, remaining_qty)`)가 빠진 돌연변이는 6 을 돌려준다.
    """
    open_info(caplog)
    s = _ratio_bfb(ratio=0.25, budget=1_000_000)
    s.state.pending_buy_amounts["OTHER"] = 850_000
    seed(s, 0.75)
    assert s.calc_buy_quantity(30_000, T) == 5, "잔여 클램프 없이 design_after(6) 그대로 샀다"
    ln = _calc_lines(caplog)[-1]
    assert field(ln, "path") == "ratio"
    assert field(ln, "lot_after") == "5"


# ===========================================================================
# R23 — 1주 폴백 차단 (비중 경로)
# ===========================================================================
@freeze_time(_NOW)
def test_r23_one_share_fallback_blocked_on_reduced_day(caplog):
    open_info(caplog)
    s1 = _ratio_bfb()
    seed(s1, 1.0)
    assert s1.calc_buy_quantity(300_000, T) == 1, "m=1 은 현행 1주 폴백(ρ컷 625,000 ≥ 가격)"
    s = _ratio_bfb()
    seed(s, 0.5)
    assert s.calc_buy_quantity(300_000, T) == 0, "축소일에 관문 1주 폴백에 닿았다(M13)"
    ln = _calc_lines(caplog)[-1]
    assert (field(ln, "fallback"), field(ln, "skip"), field(ln, "reason")) == ("one_share", "1", "no_fallback")
    assert (field(ln, "lot_before"), field(ln, "lot_after"), field(ln, "path")) == ("0", "0", "ratio")


@freeze_time(_NOW)
def test_r23_rounds_to_zero_on_reduced_day(caplog):
    open_info(caplog)
    s1 = _ratio_bfb()
    seed(s1, 1.0)
    assert s1.calc_buy_quantity(150_000, T) == 1
    s = _ratio_bfb()
    seed(s, 0.5)
    assert s.calc_buy_quantity(150_000, T) == 0
    ln = _calc_lines(caplog)[-1]
    assert (field(ln, "lot_before"), field(ln, "lot_after")) == ("1", "0")
    assert (field(ln, "fallback"), field(ln, "reason")) == ("-", "rounds_to_zero")


@freeze_time(_NOW)
def test_r23_shadow_logs_one_share_but_buys_one(caplog):
    open_info(caplog)
    s = _ratio_bfb(mode="shadow")
    seed(s, 0.5)
    assert s.calc_buy_quantity(300_000, T) == 1
    ln = _calc_lines(caplog)[-1]
    assert (field(ln, "fallback"), field(ln, "lot_after"), field(ln, "reason")) == ("one_share", "0", "no_fallback")


# ===========================================================================
# R24 — ATR 키 동치: m=1 설계 랏 == 그 전략의 기존 터틀 수량
# ===========================================================================
@freeze_time(_NOW)
# cycle405 — donchian 의 설계 랏은 옛 터틀 유닛(`_turtle_buy_quantity`)이 아니라 R 기반이라 뺀다.
@pytest.mark.parametrize("sid", [x for x in TURTLE4 if x != "donchian_swing"])
def test_r24_design_before_equals_existing_turtle_qty(sid):
    need_base()
    for price, atr, used in itertools.product((9_000, 50_000, 120_000), (0, 90, 600, 2_400), (0, 400_000)):
        s = _turtle(sid, budget=3_000_000, risk=0.005, ratio=0.2)
        _cand(s, sid, atr)
        if used:
            s.state.pending_buy_amounts["OTHER"] = used
        lots = s._market_unit_lots(price, T, 1.0)
        ref = _turtle(sid, budget=3_000_000, risk=0.005, ratio=0.2)
        _cand(ref, sid, atr)
        if used:
            ref.state.pending_buy_amounts["OTHER"] = used
        if sid == "kojiro":
            b = int(ref.state.total_investment)
            expect = compute_unit_qty_guarded(
                b, float(atr), price, 0.005, remaining_budget=max(0, b - ref._calc_used_funds()),
                min_vol_pct=1.0, position_ratio=0.2,
            )
        else:
            expect = ref._turtle_buy_quantity(price, T)
        ctx = f"{sid} price={price} atr={atr} used={used}"
        assert lots.path == "turtle", ctx
        assert lots.design_before == expect, f"_MARKET_UNIT_ATR_KEY/읽기 관용 불일치: {ctx}"
        assert float(lots.atr) == float(atr), ctx
        assert lots.remaining_qty == max(0, 3_000_000 - used) // price, ctx
        assert lots.lot_before == min(lots.design_before, lots.remaining_qty), ctx


# ===========================================================================
# R25 — 터틀 → 비중 낙하 금지 (ATR 결측 · 저변동 floor)
# ===========================================================================
@freeze_time(_NOW)
@pytest.mark.parametrize("m", [1.0, 0.5])
def test_r25_no_turtle_to_ratio_fallthrough_on_reduced_day(caplog, m):
    """cycle405 — donchian 은 어느 날이든 비중 낙하가 없다. ATR 결측이면 m 과 무관하게 0 · 미스탬프.

    (옛 계약: m=1 은 비중 낙하 20주, 축소일만 0. 깡토식 사이징은 N 없이는 사지 않는다.)
    """
    open_info(caplog)
    s = _turtle("donchian_swing")
    _cand(s, "donchian_swing", None)
    seed(s, m)
    assert s.calc_buy_quantity(10_000, T) == 0, "ATR 결측인데 비중 경로로 낙하했다(M14)"
    assert T not in s._entry_atr


# ===========================================================================
# R26 — 터틀 ATR 스탬프·손절선 불변
# ===========================================================================
_STAMP_SIDS = ("donchian_swing", "bull_flag_breakout", "vcp_breakout")


@freeze_time(_NOW)
@pytest.mark.parametrize("sid", _STAMP_SIDS)
def test_r26_stamp_equals_sizing_atr_and_stop_is_unchanged(sid):
    from src.engine.strategy_base import Position

    atr = 800.0
    price = 40_000
    got = {}
    for m in (1.0, 0.5):
        s = _turtle(sid, budget=5_000_000, risk=0.01, ratio=0.2)
        _cand(s, sid, atr)
        if sid == "bull_flag_breakout":
            s._candidates[T].update(flag_low=36_000, flag_high=39_500, pole_high=45_000, pole_start=30_000)
        if sid == "vcp_breakout":
            s._candidates[T].update(base_low=36_000, base_high=39_500, ema50=37_000)
        seed(s, m)
        qty = s.calc_buy_quantity(price, T)
        assert qty > 0, f"{sid} m={m} 에 수량 0 — 시나리오 전제 붕괴"
        assert s._entry_atr.get(T) == atr, f"{sid} m={m} 스탬프가 사이징 ATR 과 다르다(M15)"
        s.state.positions[T] = Position(ticker=T, buy_price=price, quantity=qty, order_no="O",
                                         strategy_id=sid, buy_date=DAY, high_since_buy=price)
        got[m] = (qty, s)
    assert got[0.5][0] < got[1.0][0], "축소가 수량을 줄이지 않았다"
    full, half = got[1.0][1], got[0.5][1]
    assert half.get_effective_stop_price(T) == full.get_effective_stop_price(T)
    for p in (price - 3_000, price - 1_700, price - 1_500, price - 500, price + 500):
        assert half.check_exit_signal(T, p, price) == full.check_exit_signal(T, p, price), p


# ===========================================================================
# R27 · R28 — 예산·캡 무접촉
# ===========================================================================
@freeze_time(_NOW)
@pytest.mark.parametrize("sid", TURTLE4)
def test_r27_total_investment_and_loss_limit_denominator_unchanged(sid):
    s = _turtle(sid, budget=2_000_000)
    _cand(s, sid, 700)
    seed(s, 0.5)
    s.state.daily_realized_pnl = -130_000
    before = (s.state.total_investment, s.is_daily_loss_exceeded())
    for price in (10_000, 30_000, 70_000):
        s.calc_buy_quantity(price, T)
    assert (s.state.total_investment, s.is_daily_loss_exceeded()) == before
    if sid == "kojiro":
        assert s._is_open_risk_capped() is False


@freeze_time(_NOW)
@pytest.mark.parametrize("sid", TURTLE4)
def test_r28_k_and_rho_caps_are_noop_on_reduced_lot(caplog, sid):
    caplog.set_level(logging.INFO, logger=_SB_LOGGER)
    need_base()
    s = _turtle(sid)
    _cand(s, sid, 500)
    s.state.pending_buy_amounts["OTHER"] = 600_000          # 줄인 예산(500,000) 기준 잔여면 0
    seed(s, 0.5)
    lots = s._market_unit_lots(10_000, T, 0.5)
    qty = s.calc_buy_quantity(10_000, T)
    # cycle405 — donchian 줄인 설계 랏 = floor(500,000×0.01 / max(800, 750)) = 6
    assert lots.lot_after == (6 if sid == "donchian_swing" else 10)
    assert qty == lots.lot_after, "최종 수량 ≠ lot_after — K·ρ 캡이나 잔여에 축소 예산이 섞였다(M22)"
    bad = [
        r.getMessage() for r in caplog.records
        if r.getMessage().startswith(("[fallback_notional_capped]", "[ratio_notional_blocked]",
                                      "[fallback_cap_skipped]"))
    ]
    assert bad == []


# ===========================================================================
# R29 · R30 · R31 — 방어선 · fail-open
# ===========================================================================
@freeze_time(_NOW)
@pytest.mark.parametrize("sid", TURTLE4)
def test_r29_enforce_zero_state_calc_returns_zero(sid):
    s = _turtle(sid)
    _cand(s, sid, 500)
    seed(s, 0.0)
    assert s.calc_buy_quantity(10_000, T) == 0


@freeze_time(_NOW)
@pytest.mark.parametrize("sid", TURTLE4)
def test_r30_no_snapshot_is_same_as_off_with_one_view_warning(caplog, sid):
    open_info(caplog)
    need_base()
    off = _turtle(sid, mode="off")
    _cand(off, sid, 500)
    expect = off.calc_buy_quantity(10_000, T)
    assert lines(caplog, "[market_unit_unavailable]", min_level=logging.WARNING) == [], "off 가 경보를 냈다"
    s = _turtle(sid)
    _cand(s, sid, 500)
    assert s.calc_buy_quantity(10_000, T) == expect
    s.calc_buy_quantity(10_000, T)
    warns = lines(caplog, "[market_unit_unavailable]", min_level=logging.WARNING)
    assert len(warns) == 1, warns
    assert field(warns[0], "where") == "view" and field(warns[0], "reason") == "not_computed"
    assert "m=1.00" in warns[0]


@freeze_time(_NOW)
@pytest.mark.parametrize("sid", TURTLE4)
def test_r30_failed_snapshot_is_same_as_off(sid):
    off = _turtle(sid, mode="off")
    _cand(off, sid, 500)
    s = _turtle(sid)
    _cand(s, sid, 500)
    seed(s, 1.0, ok=False, reason="stale_head")
    assert s.calc_buy_quantity(10_000, T) == off.calc_buy_quantity(10_000, T)
    view = s._market_unit_view()
    assert (float(view.m), view.state, view.reason) == (1.0, "unavailable", "stale_head")


@freeze_time(_NOW)
@pytest.mark.parametrize("sid", TURTLE4)
def test_r31_helper_exception_fails_open(caplog, monkeypatch, sid):
    open_info(caplog)
    need_base()
    off = _turtle(sid, mode="off")
    _cand(off, sid, 500)
    s = _turtle(sid)
    _cand(s, sid, 500)
    seed(s, 0.5)

    def _boom(*a, **k):
        raise RuntimeError("lots failed")

    monkeypatch.setattr(s, "_market_unit_lots", _boom)
    assert s.calc_buy_quantity(10_000, T) == off.calc_buy_quantity(10_000, T)
    s.calc_buy_quantity(10_000, T)
    errs = lines(caplog, "[market_unit_error]", min_level=logging.WARNING)
    assert len(errs) == 1, errs
    assert field(errs[0], "where") == "calc" and field(errs[0], "strategy") == sid
