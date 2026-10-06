"""운용 전략 전수 점검(2026-10-05) — 전략 공용 재현 층 단위 테스트.

사전 등록 = ``_workspace/analysis/strategy_audit_20261005/prereg.frozen.md`` §1.2 · §1.3 · §1.4 · C7.
네트워크·DB·보관소 파일 0 — 합성 입력만 쓴다.
"""
from __future__ import annotations

import math
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import bars as B  # noqa: E402
from replay.audit import book as BK  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import indicators as IND  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.audit import live as LV  # noqa: E402
from replay.audit import market_unit as MU  # noqa: E402
from replay.audit.sizing import OpSizer  # noqa: E402

pytestmark = pytest.mark.unit


# ── config ───────────────────────────────────────────────────────────────

def test_c7_budget_is_frozen_value():
    assert C.BUDGET_C7 == 4_707_820
    assert C.COST_RT_JUDGE == 0.0038
    assert C.BOOK_SEEDS == tuple(range(16))
    assert C.BOOT_SEED == 20261005


# ── bars (§1.4 · P5) ─────────────────────────────────────────────────────

def _lines(*ls):
    return lambda: list(ls)


def test_gap_below_stop_fills_at_open():
    ex = B.walk_bar(90, 95, 88, 94, lines_fn=_lines(B.Line(92, "STOP")))
    assert ex == B.BarExit(90, "STOP", "gap")


def test_intrabar_break_fills_at_line_not_low():
    ex = B.walk_bar(100, 101, 90, 99, lines_fn=_lines(B.Line(95, "STOP")))
    assert ex.px == 95 and ex.kind == "intra"


def test_strict_line_needs_price_below():
    # 채널은 「아래」 일 때만 — 저가가 선과 같으면 안 깨진다
    assert B.walk_bar(100, 101, 95, 99, lines_fn=_lines(B.Line(95, "CH", strict=True))) is None
    assert B.walk_bar(100, 101, 95, 99, lines_fn=_lines(B.Line(95, "ST"))) is not None


def test_color_vs_adverse_order_with_intrabar_trailing():
    # 음봉: 색 판정 = 시→고→저→종. 고가 120 에서 트레일링이 110 으로 올라간 뒤 저가 100 에서 110 에 판다.
    # 불리판 = 시→저→고→종: 저가 100 이 먼저 와서 옛 선(95)을 안 깨고, 고가 뒤 종가 105 가 새 선 110 을 깨 105... 아니라
    # min(직전 경로 120, 110) = 110 에 판다 — 같은 값이지만 불리판은 「고가가 먼저 오지 않았다면」 을 잰다.
    st = {"hi": 100.0}

    def lines():
        return [B.Line(max(95.0, st["hi"] - 10), "TRAIL")]

    def up(px):
        st["hi"] = max(st["hi"], px)

    ex = B.walk_bar(105, 120, 100, 102, lines_fn=lines, on_up=up, mode="color")
    assert ex.px == 110 and ex.kind == "intra"
    st["hi"] = 100.0
    # 불리판: 시가 105 로 선이 95 그대로 → 저가 100 안 깨짐 → 고가 120 → 선 110 → 종가 102 가 깬다(직전 120 → 110)
    ex2 = B.walk_bar(105, 120, 100, 102, lines_fn=lines, on_up=up, mode="adverse")
    assert ex2.px == 110


def test_adverse_order_stop_before_take_profit():
    # 같은 봉에 손절선(95)과 익절선(이익 쪽 — 가격이 위로 닿는 선은 전략이 다루므로 여기서는 경로 순서만)
    assert B.path_order(100, 110, 90, 108, "color") == (90, 110, 108)
    assert B.path_order(100, 110, 90, 92, "color") == (110, 90, 92)
    assert B.path_order(100, 110, 90, 92, "adverse") == (90, 110, 92)


def test_next_bar_ratchet_does_not_raise_within_bar():
    st = {"hi": 100.0}

    def lines():
        return [B.Line(st["hi"] - 10, "TRAIL")]

    def up(px):
        st["hi"] = max(st["hi"], px)

    # 다음 봉 갱신: 봉 안에서 고가 120 이 와도 선은 90 그대로 → 저가 100 안 깨짐
    assert B.walk_bar(105, 120, 100, 102, lines_fn=lines, on_up=up, mode="color",
                      ratchet="next_bar") is None
    assert st["hi"] == 100.0


def test_locked_limit_down_defers():
    assert B.locked_limit_down(70, 70, 70, 100)
    ex = B.walk_bar(70, 70, 70, 70, lines_fn=_lines(B.Line(95, "STOP")), locked=True)
    assert ex.kind == "locked" and math.isnan(ex.px)


def test_entry_bar_has_no_gap_check():
    # 진입 봉은 시가에 샀으므로 시가 갭 판정이 없다 — 장중 저가가 선을 깨면 선 가격
    assert B.walk_bar(100, 101, 89, 99, lines_fn=_lines(B.Line(92, "STOP")), gap_check=False).px == 92
    # 진입 봉에서는 시가로 선을 올리지 않는다(장중 경로 가격만 on_up)
    called = []
    B.walk_bar(100, 100, 99, 99.5, lines_fn=_lines(B.Line(92, "STOP")), on_up=called.append, gap_check=False)
    assert called == [99.5]


def test_breakout_fill_rules():
    assert B.breakout_fill(98, 105, 100, 5.0) == 100          # 장중 돌파 → 돌파선
    assert B.breakout_fill(103, 105, 100, 5.0) == 103         # 시가가 이미 위(추격 상한 안) → 시가
    assert B.breakout_fill(106, 110, 100, 5.0) is None        # 시가가 추격 상한 위 → 없음
    assert B.breakout_fill(95, 99, 100, 5.0) is None          # 못 닿음
    assert B.limit_up_open(129, 100) and not B.limit_up_open(128, 100)


# ── indicators ────────────────────────────────────────────────────────────

def test_atr_sma_matches_operating_atr():
    from src.engine.strategy_base import StrategyBase
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0, 1, 60))
    h = c + rng.uniform(0, 2, 60)
    l = c - rng.uniform(0, 2, 60)
    a = IND.atr_sma(h, l, c, 14)
    i = 40
    # 운영: 최신순 배열(idx0 = 어제), closes[i+1] = 직전일
    hs, ls, cs = h[:i + 1][::-1], l[:i + 1][::-1], c[:i + 1][::-1]
    op = StrategyBase._atr(list(hs), list(ls), list(cs), 14)
    assert a[i] == pytest.approx(op, rel=1e-12)


def test_ema_fir_matches_operating_ema():
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    rng = np.random.default_rng(2)
    c = 100 + np.cumsum(rng.normal(0, 1, 90))
    e = IND.ema_fir(c, 60)
    assert e[80] == pytest.approx(DonchianSwingStrategy._ema(list(c[21:81]), 60), rel=1e-12)


def test_prior_max_excludes_today():
    x = np.array([1, 5, 2, 3, 9], dtype=float)
    pm = IND.prior_max(x, 2)
    assert np.isnan(pm[1]) and pm[2] == 5 and pm[4] == 3


# ── market unit (운영 classify 그대로) ────────────────────────────────────

def test_market_unit_uses_operating_classify_and_previous_bar():
    from src.engine import market_unit as op
    rng = np.random.default_rng(3)
    closes = 30000 * np.exp(np.cumsum(rng.normal(0, 0.01, 200)))
    dates = pd.bdate_range("2024-01-01", periods=200)
    cal = dates
    m = MU.m_for_days(cal, dates, closes)
    for i in (80, 81, 120, 199):
        cl, _ = op.classify(list(closes[i - 80:i]))          # D 의 m = D−1 봉까지
        assert m[i] == cl.m
    assert np.isnan(m[79]) and np.isnan(m[0])


def test_market_unit_stale_is_nan():
    dates = pd.bdate_range("2024-01-01", periods=100)
    closes = np.linspace(100, 200, 100)
    cal = pd.DatetimeIndex(list(dates) + [dates[-1] + pd.Timedelta(days=30)])
    m = MU.m_for_days(cal, dates, closes)
    assert np.isnan(m[-1]) and m[-2] == 1.0


# ── sizing (운영 calc_buy_quantity) ───────────────────────────────────────

@pytest.fixture
def kojiro_sizer():
    from src.engine.strategies.kojiro import KojiroStrategy
    return OpSizer(KojiroStrategy, "kojiro", {"sizing_mode": "turtle", "risk_pct": 0.005,
                                              "position_ratio": 0.166, "max_positions": 6,
                                              "market_unit_mode": "enforce"})


def test_sizer_turtle_lot_matches_formula(kojiro_sizer):
    budget, P, atr = 4_707_820, 20_000, 600.0
    q = kojiro_sizer.qty(P, atr, budget=budget, used=0, m=1.0)
    unit = math.floor(budget * 0.005 / atr)                        # 39
    notional_cap = int(budget * 0.166) // P                        # 39
    assert q == min(unit, notional_cap)


def test_sizer_market_unit_scales_and_zero_blocks(kojiro_sizer):
    budget, P, atr = 4_707_820, 20_000, 600.0
    q1 = kojiro_sizer.qty(P, atr, budget=budget, used=0, m=1.0)
    q05 = kojiro_sizer.qty(P, atr, budget=budget, used=0, m=0.5)
    assert q05 == math.floor(int(budget * 0.5) * 0.005 / atr) and q05 < q1
    assert kojiro_sizer.qty(P, atr, budget=budget, used=0, m=0.0) == 0
    assert kojiro_sizer.blocks_entry(P, atr, budget=budget, used=0, m=0.0)


def test_sizer_remaining_budget_clamps(kojiro_sizer):
    q = kojiro_sizer.qty(20_000, 600.0, budget=4_707_820, used=4_707_820 - 100_000, m=1.0)
    assert q == 100_000 // 20_000


def test_sizer_one_share_fallback_is_rho_capped(kojiro_sizer):
    # 비싼 종목: 비중 랏 0 → 1주 폴백 → ρ축 2.5 × 0.166 × 예산 = 1,953,745 를 넘으면 0
    # (ATR 이 커서 K축 2유닛이 1주 미만이면 K축이 먼저 막는다 — 여기서는 K축 4주로 통과시킨다)
    assert kojiro_sizer.qty(2_500_000, 10_000.0, budget=4_707_820, used=0, m=1.0) == 0
    assert kojiro_sizer.qty(1_500_000, 10_000.0, budget=4_707_820, used=0, m=1.0) == 1
    # K축: floor(2 × 예산 × 0.005 ÷ ATR) = 0 이면 1주 폴백도 막힌다
    assert kojiro_sizer.qty(1_500_000, 50_000.0, budget=4_707_820, used=0, m=1.0) == 0


def test_sizer_nan_market_unit_is_fail_open(kojiro_sizer):
    a = kojiro_sizer.qty(20_000, 600.0, budget=4_707_820, used=0, m=float("nan"))
    b = kojiro_sizer.qty(20_000, 600.0, budget=4_707_820, used=0, m=1.0)
    assert a == b


# ── book (C7 계좌) ─────────────────────────────────────────────────────────

class _Sig:
    def __init__(self, t, gd, ti, E):
        self.ticker, self.gd, self.ti, self.E, self.E_raw = t, gd, ti, E, E


class _Pos:
    """진입 다음 봉 시가에 무조건 판다."""

    def __init__(self, s, q, closes):
        self.s, self.qty, self.cl = s, q, closes
        self.k = q
        self.cost_basis = q * s.E_raw
        self.last_px = s.E
        self.exit_px = self.exit_reason = self.exit_gd = None

    def cur_ti(self, gd):
        return gd if gd < len(self.cl) else None

    def data_ended(self, gd):
        return gd >= len(self.cl)

    def open_phase(self, ti, gd):
        self._exit(self.cl[ti], "OPEN_X", gd)
        return True

    def intraday_phase(self, ti, gd, is_entry):
        self.last_px = self.cl[ti]
        return False

    def _exit(self, px, why, gd):
        self.exit_px, self.exit_reason, self.exit_gd = px, why, gd

    def value(self):
        return self.k * self.last_px


def test_book_reconciles_and_counts_slots():
    cal = pd.bdate_range("2024-01-01", periods=5)
    closes = [100.0, 110.0, 121.0, 121.0, 121.0]
    sigs = {1: [_Sig("A", 1, 1, 100.0), _Sig("B", 1, 1, 100.0)], 2: [_Sig("A", 2, 2, 110.0)]}
    r = BK.run_book(sigs, lambda s, q: _Pos(s, q, closes), lambda s, B_, used: (int(B_ * 0.5 // s.E_raw), "ok"),
                    cal, str(cal[0].date()), str(cal[-1].date()), 0, start_equity=1000.0, cost_side=0.001,
                    max_pos=1)
    assert abs(r["recon"]) < 1e-9
    assert r["counts"]["fill"] == 1 and r["counts"]["slot_full"] == 1
    # A 는 2일째 시가에 팔렸으므로 그날 재매수 금지 → 2일째 신호는 세지 않는다
    assert r["counts"]["signal"] == 2


def test_cagr_and_mdd_definitions():
    eq = np.array([110.0, 90.0, 120.0])
    assert BK.mdd(eq, 100.0) == pytest.approx(90 / 110 - 1)
    assert BK.cagr(eq, 100.0) == pytest.approx(1.2 ** (252 / 3) - 1)


# ── judge ─────────────────────────────────────────────────────────────────

def test_cluster_bootstrap_weighted_estimate_and_order():
    v = [1.0, -1.0, 3.0]
    est, lo, hi = J.cluster_bootstrap(v, ["a", "b", "a"], weights=[1, 1, 0.5], n_boot=200, seed=1)
    assert est == pytest.approx((1 - 1 + 1.5) / 2.5)
    assert lo <= est <= hi
    with pytest.raises(ValueError):
        J.cluster_bootstrap(v, ["a", "b", "a"], order="x")


def test_cluster_bootstrap_first_order_reproduces_cycle391_boot_ci():
    """cycle391 ``boot_ci`` — 진입일 묶음 · m 가중 비 · 2.5/97.5 분위 · 묶음 = 처음 나온 순서."""
    from collections import defaultdict
    rng0 = np.random.default_rng(7)
    ts = [{"entry_ci": int(rng0.integers(0, 40)), "m": float(rng0.choice([0.5, 0.75, 1.0])),
           "Rnet": float(rng0.normal(0.2, 1.0))} for _ in range(300)]
    cl = defaultdict(lambda: [0.0, 0.0])
    for t in ts:
        cl[t["entry_ci"]][0] += t["m"] * t["Rnet"]
        cl[t["entry_ci"]][1] += t["m"]
    s1 = np.array([v[0] for v in cl.values()])
    s0 = np.array([v[1] for v in cl.values()])
    K = len(s1)
    rng = np.random.default_rng(20261002)
    cnt = rng.multinomial(K, np.full(K, 1.0 / K), size=2000).astype(float)
    stat = np.einsum("ij,j->i", cnt, s1) / np.einsum("ij,j->i", cnt, s0)
    want = (float(np.percentile(stat, 2.5)), float(np.percentile(stat, 97.5)))
    got = J.cluster_bootstrap([t["Rnet"] for t in ts], [t["entry_ci"] for t in ts],
                              weights=[t["m"] for t in ts], n_boot=2000, seed=20261002, q=0.025,
                              order="first")
    assert got[1] == pytest.approx(want[0], abs=1e-12) and got[2] == pytest.approx(want[1], abs=1e-12)


def test_p1_threshold_and_iso_week_key():
    assert J.iso_week_key("005930", date(2026, 1, 1)) == "005930|2026-W01"
    r = J.p1([0.01] * 50 + [-0.005] * 50, ["A"] * 100, [date(2024, 1, 1) + pd.Timedelta(days=7 * i)
                                                       for i in range(100)])
    assert r["pass"] and r["mean"] > 0 and r["lo90"] > C.P1_LO


def test_l1_and_p6_small_samples_are_undecidable():
    assert J.l1([0.1] * 29, ["2026-05-01"] * 29)["label"] == "판정 불가"
    assert J.p6([("A", "2026-05-01")] * 9, set())["label"] == "관문 판정 불가"
    r = J.p6([("A", "d1")] * 7 + [("B", "d2")] * 3, {("A", "d1")})
    assert r["rate"] == 0.7 and r["pass"]


def test_p5_flip_is_hold():
    assert J.p5(0.002, -0.001)["label"].startswith("판정 보류")
    assert J.p5(0.002, 0.001)["label"] == "유지"


# ── live (K4) ─────────────────────────────────────────────────────────────

def _row(ts, tt, px, q, st="COMPLETED", strat="kojiro", tk="000001", on=""):
    return {"timestamp": ts, "trade_type": tt, "price": px, "quantity": q, "status": st,
            "strategy": strat, "ticker": tk, "order_no": on, "ticker_name": "x"}


def test_kst_date_crosses_midnight():
    # UTC 23:30 = KST 다음 날 08:30 (D-2)
    assert LV.kst_date("2026-05-03T23:30:00+00:00") == date(2026, 5, 4)


def test_round_trip_partial_sells_and_exclusions():
    rows = [
        _row("2026-05-04T00:10:00+00:00", "BUY", 1000, 10, on="1"),
        _row("2026-05-04T00:10:01+00:00", "BUY", 1010, 10, on="1"),       # 같은 주문의 두 번째 체결 행
        _row("2026-05-05T01:00:00+00:00", "SELL", 1100, 5, on="2"),
        _row("2026-05-06T01:00:00+00:00", "SELL", 1200, 15, on="3"),
        _row("2026-05-06T02:00:00+00:00", "BUY", 500, 3, st="PENDING", on="4"),
        _row("2026-05-07T02:00:00+00:00", "SELL", 900, 2, on="5"),        # 보유 없음 → orphan
    ]
    out = LV.round_trips(rows, cost_rt=0.0038)
    assert len(out["trips"]) == 1
    t = out["trips"][0]
    assert t["qty"] == 20 and t["n_buy"] == 1 and t["n_sell"] == 2
    assert t["buy_px"] == pytest.approx(1005.0)
    assert t["sell_px"] == pytest.approx((1100 * 5 + 1200 * 15) / 20)
    assert t["net"] == pytest.approx(t["sell_px"] / 1005.0 - 1 - 0.0038)
    assert out["excluded"][("kojiro", "BUY", "PENDING")] == 1
    assert len(out["orphan_sells"]) == 1


def test_round_trip_corporate_action_flag_and_window():
    rows = [_row("2026-04-27T00:10:00+00:00", "BUY", 1000, 1, on="1"),
            _row("2026-05-06T01:00:00+00:00", "SELL", 500, 1, on="2")]
    out = LV.round_trips(rows, cost_rt=0.0038, ca_days={"000001": {date(2026, 4, 30)}})
    t = out["trips"][0]
    assert t["ca_flag"] and not t["in_window"]


def test_ca_days_from_db_flags_code_and_jump():
    cols = ["ticker", "bas_dd", "close_price", "flng_cls_code"]
    rows = [["A", "2026-05-01", 1000, "00"], ["A", "2026-05-04", 500, "00"], ["A", "2026-05-05", 510, "02"],
            ["A", "2026-05-06", 520, "01"],
            ["B", "2026-05-22", 102000, "00"], ["B", "2026-05-26", 132600, "00"]]   # 상한가 +30.0% 는 아니다
    d = LV.ca_days_from_db(cols, rows)
    assert d["A"] == {date(2026, 5, 4), date(2026, 5, 6)}          # 배당락(02)은 D-1 대상이 아니다
    assert "B" not in d


# ── 전략 층 이식의 회귀 고정 (관문 1·2 에서 원본과 비트 단위로 같았던 규칙) ─────────────

def _synthetic_etf(seed: int, n: int = 160) -> dict:
    rng = np.random.default_rng(seed)
    c = 10_000 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
    o = c * np.exp(rng.normal(0, 0.01, n))
    h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.012, n)))
    l = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.012, n)))
    return {"o": o, "h": h, "l": l, "c": c, "n14": IND.atr_sma(h, l, c, 14), "hi_prev20": IND.prior_max(h, 20)}


def test_etf_b_exit_matches_cycle391_sim_donchian():
    import importlib.util
    path = os.path.join(_TOOLS, "..", "_workspace", "domain_consult", "cycle391_etf_s0_remeasure.py")
    spec = importlib.util.spec_from_file_location("c391_for_test", path)
    c391 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c391)
    from replay.strategies import etf_trend_b as EB
    checked = 0
    for seed in range(40):
        d = _synthetic_etf(seed)
        for j in range(30, 150, 7):
            if not (d["n14"][j] > 0):
                continue
            assert EB.sim_b(d, j) == c391.sim_donchian(d, j)
            assert EB.sim_b(d, j, mode="adverse") == c391.sim_donchian(d, j)
            checked += 1
    assert checked > 500


def test_donchian_kk_position_rules():
    from replay.strategies import donchian_kk as DK
    n = 40
    o = np.full(n, 100.0)
    h = np.full(n, 101.0)
    l = np.full(n, 99.0)
    c = np.full(n, 100.0)
    b = {"di": np.arange(n), "o": o, "h": h, "l": l, "c": c, "notrade": np.zeros(n, bool)}
    f = {"chan10": IND.prior_min(l, 10)}
    sig = DK.Sig("T", 0, 0, 100.0, 100.0, 2.0, 0.0, 1.0)    # N=2 → R = max(8, 3) = 8
    # 손절: 저가 91 이 손절선 92 를 깬다 → 92
    l2 = l.copy()
    l2[3] = 91.0
    ps = DK.run_path(sig, dict(b, l=l2), f, n)
    assert (ps.exit_px, ps.exit_reason, ps.exit_gd) == (92.0, "STOP_LOSS", 3)
    # 20봉째 고점 < E + 1R(108) → 그날 종가 시간 청산
    ps = DK.run_path(sig, b, f, n)
    assert (ps.exit_reason, ps.exit_gd, ps.exit_px) == ("TIME_EXIT", 19, 100.0)
    # 3R(124) 도달 → 손절선 본전 + 채널 무장
    h3, c3, o3, l3 = h.copy(), c.copy(), o.copy(), l.copy()
    h3[2], c3[2] = 125.0, 120.0
    o3[3:], h3[3:], l3[3:], c3[3:] = 120.0, 121.0, 119.0, 120.0
    l3[15] = 100.5                                             # 채널(직전 10봉 저가 119) 이탈
    f3 = {"chan10": IND.prior_min(l3, 10)}
    ps = DK.run_path(sig, dict(b, o=o3, h=h3, l=l3, c=c3), f3, n)
    assert ps.armed and ps.exit_reason == "TRAILING_STOP" and ps.exit_px == 119.0
