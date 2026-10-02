"""cycle403 돌연변이 검사가 찾은 빈틈을 메우는 행위 고정 테스트.

각 테스트는 돌연변이 하나가 살아남던 자리를 겨눈다(괄호 = 살아남던 변형):

- leaf `simulate_exit` 의 고정% 받침선 `E × 0.91`(0.91→0.92)
- leaf `entry_signal` 의 돌파 `c > line`(>→>=) · 거래대금 `>= 1.5 × 평균`(>=→>)
- leaf `return_correlation` 의 관측 수 하한 `< min_obs`(<→<=)
- leaf `channel_low` 의 창 길이 10(10→9)
- 전략 묶음 문턱 `corr > 0.9`(prepare · recompute 양쪽, >→>=)
- 전략 `calc_buy_quantity` 시장 유닛 경로의 `lot_after <= 0 → 0`(관문 `_apply_budget_limit(0)` 로 바꿔 1주 폴백 부활)
- 전략 `recompute_held_atr` 의 `hsb` = 매수일 **포함** 최고가(>=→>)
- 전략 `prepare` 의 일봉 품질 두 조건(최신봉 신선도 · 최근 거래일 결손) — 기존 테스트에서는 한 종목이 두 조건에 동시에 걸려 서로를 가렸다
"""
from __future__ import annotations

import importlib
import math
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.unit.engine.test_cycle403_etf_trend_strategy import (  # noqa: F401 — _isolate 는 autouse 픽스처
    A,
    A2,
    DAY,
    LAST,
    PX,
    T,
    U,
    Daily,
    _isolate,
    _recompute,
    at,
    bars,
    cand,
    install_daily,
    int_bars,
    make,
    pos,
    to_rows,
)

pytestmark = pytest.mark.unit


def _core():
    return importlib.import_module("src.engine.etf_trend_core")


# ===========================================================================
# leaf — simulate_exit 고정% 받침선
# ===========================================================================
def test_simulate_exit_uses_minus_9pct_backstop_when_atr_stop_is_looser():
    """2N 이 진입가의 9% 를 넘으면 손절선은 E×0.91 이다(재현 `hard = max(E-2N, E×0.91)`)."""
    lf = _core()
    j = 24
    opens = [100.0] * (j + 1)
    highs = [103.0] * (j + 1)
    lows = [97.0] * (j + 1)
    closes = [100.0] * (j + 1)
    # 매수일 D = j+1: 시가 100(=E), 장중 저가 90.5 — 받침선 91 에 닿는다.
    opens.append(100.0)
    highs.append(101.0)
    lows.append(90.5)
    closes.append(95.0)
    tr = lf.true_ranges(highs, lows, closes)
    n = lf.n14(tr, j)
    assert n == pytest.approx(6.0) and 2 * n > 9.0, "전제 — ATR 손절(E-2N=88)이 받침선(91)보다 느슨하다"
    k, px, why = lf.simulate_exit(opens, highs, lows, closes, j)
    assert (k, why) == (j + 1, "stop")
    assert px == pytest.approx(91.0)
    assert px == pytest.approx(lf.hard_stop(100.0, n)), "simulate_exit 과 hard_stop 이 같은 손절선"


# ===========================================================================
# leaf — entry_signal 경계
# ===========================================================================
def _rising(n=120, *, last_close=None, last_tv=None):
    closes = [10_000 + 10 * i for i in range(n)]
    highs = [c + 100 for c in closes]
    lows = [c - 100 for c in closes]
    tv = [3_000_000_000] * n
    if last_close is not None:
        closes[-1] = last_close
        highs[-1] = last_close + 100
        lows[-1] = last_close - 100
    if last_tv is not None:
        tv[-1] = last_tv
    return highs, lows, closes, tv


def test_entry_close_equal_to_line_is_not_breakout():
    lf = _core()
    h0, _, _, _ = _rising()
    line = max(h0[-21:-1])
    highs, lows, closes, tv = _rising(last_close=line, last_tv=6_000_000_000)
    sig = lf.entry_signal(highs, lows, closes, tv, len(closes) - 1)
    assert sig.stage == "breakout" and not sig.ok, "종가 = 돌파선은 돌파가 아니다(재현 `c > line`)"
    highs, lows, closes, tv = _rising(last_close=line + 1, last_tv=6_000_000_000)
    assert lf.entry_signal(highs, lows, closes, tv, len(closes) - 1).ok, "양성 대조 — 1원 위면 돌파"


def test_entry_volume_exactly_1_5x_passes():
    lf = _core()
    h0, _, _, _ = _rising()
    line = max(h0[-21:-1])
    highs, lows, closes, tv = _rising(last_close=line + 50, last_tv=4_500_000_000)  # = 1.5 × 3e9
    sig = lf.entry_signal(highs, lows, closes, tv, len(closes) - 1)
    assert sig.ok, f"거래대금 = 1.5 × 직전 20봉 평균이면 통과(재현 `>=`): {sig}"
    highs, lows, closes, tv = _rising(last_close=line + 50, last_tv=4_499_999_999)
    assert lf.entry_signal(highs, lows, closes, tv, len(closes) - 1).stage == "volume", "음성 대조"


# ===========================================================================
# leaf — return_correlation 관측 수 하한 · channel_low 창
# ===========================================================================
def test_return_correlation_exactly_min_obs_is_computed():
    lf = _core()
    cal = [date(2026, 1, 1) + timedelta(days=i) for i in range(61)]   # 수익률 60개
    a = {d: 100.0 * (1.01 if i % 2 else 0.995) ** i for i, d in enumerate(cal)}
    b = {d: 50.0 * (1.02 if i % 3 else 0.99) ** i for i, d in enumerate(cal)}
    assert lf.return_correlation(a, b, calendar=cal, window=120, min_obs=60) is not None, (
        "관측 수 = min_obs 면 계산한다(`< min_obs` 일 때만 None)")
    assert lf.return_correlation(a, b, calendar=cal, window=120, min_obs=61) is None


def test_channel_low_window_is_exactly_10():
    lf = _core()
    assert lf.channel_low([0, 1] + [5] * 9) == 1, "끝에서 10번째 봉이 창 안에 든다"
    assert lf.channel_low([1] + [5] * 10) == 5, "끝에서 11번째 봉은 창 밖이다"


# ===========================================================================
# 전략 — 묶음 문턱은 0.9 초과(같으면 묶지 않는다)
# ===========================================================================
async def _prepare_two_candidates(monkeypatch, corr_value):
    core = _core()
    monkeypatch.setattr(core, "return_correlation", lambda *a, **k: corr_value)
    table = {A: to_rows(A, bars(150, LAST)), A2: to_rows(A2, bars(150, LAST, scale=2.0, tv=4e9)),
             "069500": to_rows("069500", bars(150, LAST, breakout=False))}

    async def fake_universe(min_market_cap_eok: int = 500):
        return [{"ticker": t, "name": t, "hts_avls_eok": 1_000} for t in (A, A2)]

    monkeypatch.setattr("src.db.stock_master.list_etf_trend_universe", fake_universe, raising=False)
    mod = importlib.import_module("src.engine.strategies.etf_trend")
    monkeypatch.setattr(mod, "list_etf_trend_universe", fake_universe)
    install_daily(monkeypatch, Daily(table))
    s = make()
    monkeypatch.setattr(s, "_refresh_market_unit", AsyncMock())
    with at(7, 45):
        await s.prepare()
    assert set(s._candidates) == {A, A2}, "전제 — 두 종목 모두 후보"
    return s


@pytest.mark.asyncio
async def test_prepare_cluster_threshold_is_strictly_greater(monkeypatch):
    s = await _prepare_two_candidates(monkeypatch, 0.9)
    assert not s._cluster_pairs, "상관 = 0.9 는 묶지 않는다(`> 0.9`)"


@pytest.mark.asyncio
async def test_prepare_cluster_just_above_threshold_pairs(monkeypatch):
    s = await _prepare_two_candidates(monkeypatch, math.nextafter(0.9, 1.0))
    assert frozenset({A, A2}) in s._cluster_pairs, "양성 대조"


@pytest.mark.asyncio
@pytest.mark.parametrize("corr_value, want", [(0.9, False), (math.nextafter(0.9, 1.0), True)])
async def test_recompute_cluster_threshold_is_strictly_greater(monkeypatch, corr_value, want):
    core = _core()
    monkeypatch.setattr(core, "return_correlation", lambda *a, **k: corr_value)
    asc = int_bars(60, LAST, breakout=False)
    s = make(sizing_mode="turtle")
    s._candidate_closes = {A: {r[0]: r[4] for r in asc}}
    s.state.positions[U] = pos(U, days_ago=(DAY - asc[-3][0]).days)
    with at(7, 50):
        await _recompute(s, monkeypatch, {U: to_rows(U, asc)})
    assert (frozenset({A, U}) in s._cluster_pairs) is want


# ===========================================================================
# 전략 — 시장 유닛 경로에서 랏 0 이면 관문(1주 폴백)으로 가지 않는다(L5)
# ===========================================================================
def test_calc_market_unit_lot_zero_returns_zero_without_fallback(monkeypatch):
    s = make(m=0.5, market_unit_mode="enforce")
    lots = SimpleNamespace(path="turtle", lot_after=0, design_after=0, atr=200.0)
    monkeypatch.setattr(s, "_market_unit_sizing", lambda *a, **k: lots)
    monkeypatch.setattr(s, "_fallback_one_share",
                        lambda *a, **k: pytest.fail("1주 폴백 호출 — 시장 유닛 랏 0 은 0 이다(L5)"))
    with at(9, 10):
        assert s.calc_buy_quantity(PX, T) == 0
    assert T not in s._entry_atr


# ===========================================================================
# 전략 — recompute 의 hsb 는 매수일 봉을 포함한다(재현 simulate_exit 과 같다)
# ===========================================================================
@pytest.mark.asyncio
async def test_recompute_hsb_includes_buy_day_high(monkeypatch):
    asc = [list(r) for r in int_bars(60, LAST, breakout=False)]
    buy_i = len(asc) - 4
    asc[buy_i][2] = max(r[2] for r in asc) + 5_000                   # 매수일 고가가 가장 높다
    asc = [tuple(r) for r in asc]
    s = make(sizing_mode="turtle")
    s.state.positions[T] = pos(days_ago=(DAY - asc[buy_i][0]).days, buy_price=asc[buy_i][1])
    with at(7, 50):
        await _recompute(s, monkeypatch, {T: to_rows(T, asc)})
    assert s._hsb_closed[T] == asc[buy_i][2]


# ===========================================================================
# 전략 — prepare 일봉 품질 두 조건을 따로 고정한다
# ===========================================================================
async def _prepare_one(monkeypatch, rows):
    table = {A: rows, "069500": to_rows("069500", bars(150, LAST, breakout=False))}

    async def fake_universe(min_market_cap_eok: int = 500):
        return [{"ticker": A, "name": A, "hts_avls_eok": 1_000}]

    monkeypatch.setattr("src.db.stock_master.list_etf_trend_universe", fake_universe, raising=False)
    mod = importlib.import_module("src.engine.strategies.etf_trend")
    monkeypatch.setattr(mod, "list_etf_trend_universe", fake_universe)
    install_daily(monkeypatch, Daily(table))
    s = make()
    monkeypatch.setattr(s, "_refresh_market_unit", AsyncMock())
    with at(7, 45):
        await s.prepare()
    return s


@pytest.mark.asyncio
async def test_prepare_positive_control_single_candidate(monkeypatch):
    s = await _prepare_one(monkeypatch, to_rows(A, bars(150, LAST)))
    assert A in s._candidates


@pytest.mark.asyncio
async def test_prepare_head_newer_than_k200_is_excluded(monkeypatch):
    """최근 069500 날짜는 전부 있지만 최신봉이 069500 보다 하루 앞선다 → 신선도 불일치."""
    s = await _prepare_one(monkeypatch, to_rows(A, bars(151, LAST + timedelta(days=3))))  # 금→월
    assert A not in s._candidates
    steps = {st["step_no"]: st for st in s._funnel_steps}
    assert not steps[2]["survived"], "일봉 품질(2단계)에서 탈락"


@pytest.mark.asyncio
async def test_prepare_missing_recent_trading_day_is_excluded(monkeypatch):
    """최신봉은 069500 과 같지만 최근 60거래일 안에 하루가 빠졌다 → 결손."""
    rows = to_rows(A, bars(151, LAST))
    del rows[30]                                                       # DESC — 최근 31번째 거래일
    s = await _prepare_one(monkeypatch, rows)
    assert A not in s._candidates
    steps = {st["step_no"]: st for st in s._funnel_steps}
    assert not steps[2]["survived"], "일봉 품질(2단계)에서 탈락"
