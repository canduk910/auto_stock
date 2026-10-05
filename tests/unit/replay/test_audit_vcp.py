"""운용 전략 전수 점검(2026-10-05) — vcp_breakout(S3) 재현 층 단위 테스트.

사전 등록 = ``_workspace/analysis/strategy_audit_20261005/prereg.frozen.md`` §1.4 · §3.3.
재현의 빠른 후보 판정이 운영 메서드와 같은지(정수 가격 무작위 시리즈) · 청산선 · 진입 봉 경로 · 쿨다운을 본다.
네트워크·DB·보관소 0 — 합성 입력만. (DB 값 대조 테스트 하나만 스크래치 추출본이 있으면 읽는다.)
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import config as C  # noqa: E402
from replay.strategies import bfb_vcp_engine as EN  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def ops():
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig
    return VcpBreakoutStrategy(StrategyConfig(strategy_id="vcp_breakout", name="vcp", weight=1.0,
                                              params=dict(EN.VCP_DB)))


def _series(seed: int, n: int = 320, drift: float = 0.0015, vol: float = 0.018):
    """정수 가격 OHLCV — 상승 추세 + 박스(수축) 구간이 섞이도록."""
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, vol, n)
    r[n // 2: n // 2 + 40] *= 0.35                       # 수축 구간
    c = np.round(20000 * np.exp(np.cumsum(r))).astype(float)
    o = np.round(c * (1 + rng.normal(0, 0.006, n)))
    h = np.maximum(o, c) + np.round(c * rng.uniform(0, 0.015, n))
    lo = np.minimum(o, c) - np.round(c * rng.uniform(0, 0.015, n))
    v = np.round(rng.lognormal(12, 0.5, n))
    return o, h, lo, c, v


def _candles(o, h, l, c, v, i: int, avail: int) -> list:
    """운영 일봉 dict(최신순, idx0 = i). ``avail`` = 운영이 받는 봉 수."""
    out = []
    for k in range(i, max(-1, i - avail), -1):
        out.append({"stck_bsop_date": f"D{k:05d}", "stck_oprc": str(int(o[k])), "stck_hgpr": str(int(h[k])),
                    "stck_lwpr": str(int(l[k])), "stck_clpr": str(int(c[k])), "acml_vol": str(int(v[k]))})
    return out


def test_db_params_match_extract():
    if not os.path.exists(C.DB_EXTRACT):
        pytest.skip("스크래치 추출본 없음")
    import json
    from replay.audit import panel as PN
    ext = PN.load_db_extract()
    cols, rows = ext["strategy_config"]
    d = {r[0]: dict(zip(cols, r)) for r in rows}
    prm = d["vcp_breakout"]["params"]
    prm = prm if isinstance(prm, dict) else json.loads(prm)
    for k, v in EN.VCP_DB.items():
        assert prm[k] == v, k


def test_fetch_days_full_mode():
    assert EN.vcp_fetch_days(EN.VCP_DB) == 250
    assert EN.vcp_fetch_days(dict(EN.VCP_DB, daily_fetch_depth_mode="cap100")) == 100


def test_trend_filter_matches_operating(ops):
    n_cmp = n_pass = 0
    for seed in range(6):
        o, h, l, c, v = _series(seed, n=330, drift=0.002 if seed % 2 == 0 else 0.0)
        ok, e50, eff = EN.vcp_trend(c)
        for i in list(range(54, 330, 3)):
            avail = min(250, i + 1)
            effo = min(200, avail - 20 - 5)
            if effo < 30:
                assert eff[i] == 0
                continue
            cand = _candles(o, h, l, c, v, i, avail)
            res = ops._check_trend_filter(cand, effective_ema_long=effo)
            assert bool(ok[i]) == (res is not None), (seed, i)
            assert eff[i] == effo
            if res is not None:
                assert int(e50[i]) == res["ema50"]
                n_pass += 1
            n_cmp += 1
    assert n_cmp > 400 and n_pass > 20          # 비교가 공허하지 않다


def test_base_matches_operating(ops):
    n_found = 0
    for seed in range(5):
        o, h, l, c, v = _series(seed + 10, n=200, vol=0.012)
        Lv, Hv, LLv = EN.vcp_base_vec(h, l)
        for i in range(30, 200, 2):
            cand = _candles(o, h, l, c, v, i, min(250, i + 1))
            res = ops._detect_base(cand)
            sc = EN.vcp_base(h, l, i)
            if res is None:
                assert sc is None and Lv[i] == 0
            else:
                n_found += 1
                assert sc == (res["length"], res["high"], res["low"])
                assert (Lv[i], Hv[i], LLv[i]) == (res["length"], res["high"], res["low"])
                assert int(float(np.sum(v[i - 19:i + 1])) / 20) == res["avg_volume_20"]
    assert n_found > 50


def test_pullback_and_volume_contraction_match_operating(ops):
    n = n_ok = n_vc = 0
    for seed in range(8):
        o, h, l, c, v = _series(seed + 20, n=220, vol=0.02)
        for i in range(60, 220, 2):
            cand = _candles(o, h, l, c, v, i, min(250, i + 1))
            base = ops._detect_base(cand)
            if base is None:
                continue
            L = base["length"]
            ok_op = ops._check_pullback_sequence(cand, dict(base))
            pbs = EN.vcp_pullbacks(c, h, l, i, L)
            assert EN.vcp_pullback_ok(pbs) == ok_op, (seed, i)
            vc_op = ops._check_volume_contraction(cand, base)
            assert EN.vcp_volc_ok(v, i, L) == vc_op, (seed, i)
            n += 1
            n_ok += ok_op
            n_vc += vc_op
    assert n > 200 and n_ok > 5 and 0 < n_vc < n


def test_atr_matches_operating():
    from src.engine.strategy_base import StrategyBase
    o, h, l, c, v = _series(3, n=60)
    a = EN.ops_atr(h, l, c, 14)
    for i in (14, 15, 16, 40, 59):
        cand_h, cand_l, cand_c = list(h[:i + 1][::-1]), list(l[:i + 1][::-1]), list(c[:i + 1][::-1])
        assert a[i] == pytest.approx(StrategyBase._atr(cand_h, cand_l, cand_c, 14), rel=1e-12, abs=1e-12)


# ── 청산선 ─────────────────────────────────────────────────────────────────

def _one_bar_store(rows, atr=2.0, ema50=50.0):
    """rows = [(o,h,l,c)] — 0 번은 신호 봉(D−1), 1 번이 진입 봉."""
    n = len(rows)
    b = {"di": np.arange(n), "o": np.array([r[0] for r in rows], float), "h": np.array([r[1] for r in rows], float),
         "l": np.array([r[2] for r in rows], float), "c": np.array([r[3] for r in rows], float),
         "raw": np.ones(n), "notrade": np.zeros(n, bool), "vol": np.ones(n)}
    f = {"atr": np.full(n, atr), "ema50": np.full(n, ema50)}
    cal = pd.bdate_range("2026-01-05", periods=n)
    return b, f, cal


def _sig(E, line, low, N, entry="cross", ti=1, target=float("nan")):
    return EN.Sig("000001", ti, ti, E, E, N, line, low, target, 1.0, True, entry)


def test_initial_stop_is_chandelier_not_min_stop_band():
    # 운영: 터틀 손절 = min(E−2N, 0.95E) 이지만 샹들리에(고점 E − 2·ATR)가 E−2N 이라 −5% 밴드는 효력이 없다
    b, f, cal = _one_bar_store([(100, 101, 99, 100), (99, 101, 99, 101), (100.5, 100.6, 96.5, 97)], atr=2.0)
    s = _sig(100.0, 100.0, 50.0, 2.0)
    ps = EN.BPos(s, b, f, 1, kind="vcp", p=EN.VCP_DB, cal=cal)
    assert not ps.intraday_phase(1, 1, True)               # 진입 봉: 고점 101
    assert ps.open_phase(2, 2) is False
    assert ps.intraday_phase(2, 2, False)
    assert ps.exit_reason == "TRAILING_STOP" and ps.exit_px == pytest.approx(97.0)   # 101 − 2×2


def test_backstop_binds_when_two_atr_is_wide():
    b, f, cal = _one_bar_store([(100, 101, 99, 100), (99, 100, 99, 100), (99, 99.5, 85, 88)], atr=6.0)
    s = _sig(100.0, 100.0, 50.0, 6.0)
    ps = EN.BPos(s, b, f, 1, kind="vcp", p=EN.VCP_DB, cal=cal)
    ps.intraday_phase(1, 1, True)
    ps.open_phase(2, 2)
    assert ps.intraday_phase(2, 2, False)
    assert ps.exit_px == pytest.approx(91.0) and ps.exit_reason == "STOP_LOSS"      # −9% 백스톱


def test_breakeven_promotes_stop_to_entry():
    b, f, cal = _one_bar_store([(100, 101, 99, 100), (100, 104, 99.5, 103.5), (103, 103.2, 98, 98.5)], atr=2.0)
    s = _sig(100.0, 100.0, 50.0, 2.0)
    ps = EN.BPos(s, b, f, 1, kind="vcp", p=EN.VCP_DB, cal=cal)
    ps.intraday_phase(1, 1, True)                          # 고점 104 ≥ 100 + 1.5×2
    assert ps.be
    ps.open_phase(2, 2)
    assert ps.intraday_phase(2, 2, False)
    assert ps.exit_px == pytest.approx(100.0)              # max(샹들리에 100, 본전 100)


def test_base_low_is_strict_and_ema50_strict():
    b, f, cal = _one_bar_store([(100, 101, 99, 100), (100, 101, 99.8, 100.5), (100.5, 100.7, 99.0, 99.5)],
                               atr=0.5, ema50=90.0)
    s = _sig(100.0, 100.0, 99.0, 0.5)
    ps = EN.BPos(s, b, f, 1, kind="vcp", p=EN.VCP_DB, cal=cal)
    ps.intraday_phase(1, 1, True)
    ps.open_phase(2, 2)
    # 샹들리에 = 101 − 1 = 100 이 먼저 깨진다 → 100 에 판다(base_low 99 는 엄격 < 라 99.0 에서는 안 깨짐)
    assert ps.intraday_phase(2, 2, False) and ps.exit_px == pytest.approx(100.0)
    ln = [x for x in ps._lines() if x.price == 99.0][0]
    assert ln.strict


def test_entry_bar_paths_color_vs_adverse():
    # 진입 봉 음봉(시 99 → 고 103 → 저 95 → 종 96): color 는 돌파(100) 뒤 고·저 → 샹들리에 103−5=98 에서 손절
    # (ATR 2.5 — 본전 승격 문턱 100+3.75 에 못 닿는다)
    rows = [(100, 100, 98, 99), (99, 103, 95, 96)]
    b, f, cal = _one_bar_store(rows, atr=2.5)
    ps = EN.BPos(_sig(100.0, 100.0, 50.0, 2.5), b, f, 1, kind="vcp", p=EN.VCP_DB, cal=cal)
    assert ps.intraday_phase(1, 1, True) and ps.exit_px == pytest.approx(98.0)
    assert not ps.be
    # ATR 2.0 이면 고가 103 ≥ 100+3 → 본전 승격 → 본전 100 에서 판다(샹들리에 99 보다 높다)
    b1, f1, _ = _one_bar_store(rows, atr=2.0)
    ps1 = EN.BPos(_sig(100.0, 100.0, 50.0, 2.0), b1, f1, 1, kind="vcp", p=EN.VCP_DB, cal=cal)
    assert ps1.intraday_phase(1, 1, True) and ps1.exit_px == pytest.approx(100.0) and ps1.be
    # 양봉(시 99 → 저 95 → 고 103 → 종 102): color 는 돌파 뒤 고·종만 → 생존
    b2, f2, _ = _one_bar_store([(100, 100, 98, 99), (99, 103, 95, 102)], atr=2.0)
    ps2 = EN.BPos(_sig(100.0, 100.0, 50.0, 2.0), b2, f2, 1, kind="vcp", p=EN.VCP_DB, cal=cal)
    assert not ps2.intraday_phase(1, 1, True)
    # adverse 는 돌파 뒤 저가 먼저 → 손절선 96(=100−2×2) 에서 손절
    ps3 = EN.BPos(_sig(100.0, 100.0, 50.0, 2.0), b2, f2, 1, kind="vcp", p=EN.VCP_DB, cal=cal, mode="adverse")
    assert ps3.intraday_phase(1, 1, True) and ps3.exit_px == pytest.approx(96.0)


def test_locked_limit_down_defers_to_next_open():
    rows = [(100, 101, 99, 100), (100, 101, 99.5, 100), (70, 70, 70, 70), (72, 75, 71, 74)]
    b, f, cal = _one_bar_store(rows, atr=2.0)
    ps = EN.BPos(_sig(100.0, 100.0, 50.0, 2.0, entry="gap"), b, f, 1, kind="vcp", p=EN.VCP_DB, cal=cal)
    ps.intraday_phase(1, 1, True)
    assert ps.open_phase(2, 2) is False and ps.pending is not None
    assert ps.open_phase(3, 3) and ps.exit_px == 72


# ── 신호 ───────────────────────────────────────────────────────────────────

def _sig_store(o_d, h_d, l_d, c_d, line=100.0):
    n = 3
    b = {"di": np.arange(n), "o": np.array([99, 99, o_d], float), "h": np.array([100, 100, h_d], float),
         "l": np.array([97, 97, l_d], float), "c": np.array([99, 99, c_d], float), "raw": np.ones(n),
         "notrade": np.zeros(n, bool), "vol": np.array([1e5, 1e5, 2e5])}
    f = {"cand": np.array([False, True, False]), "line": np.array([np.nan, line, np.nan]),
         "low": np.array([np.nan, 90.0, np.nan]), "avg": np.array([0, 1e5, 0]), "atr": np.full(n, 2.0),
         "target": np.full(n, np.nan)}
    return {"A": b}, {"A": f}, {"A": np.ones(n, bool)}


def test_signal_gap_above_cap_is_no_entry_but_latch_variant_buys_at_cap():
    bars, feats, uni = _sig_store(108.0, 110.0, 104.0, 105.0)       # 시가 +8% > 7.5%
    m = np.ones(3)
    assert EN.build_signals(bars, feats, m, EN.VCP_DB, uni) == []
    s = EN.build_signals(bars, feats, m, EN.VCP_DB, uni, latch=True)
    assert len(s) == 1 and s[0].entry == "latch" and s[0].E == pytest.approx(107.5)


def test_signal_cross_and_volume_flag():
    bars, feats, uni = _sig_store(99.0, 103.0, 98.0, 102.0)
    s = EN.build_signals(bars, feats, np.ones(3), EN.VCP_DB, uni)
    assert len(s) == 1 and s[0].E == 100.0 and s[0].entry == "cross"
    assert s[0].vol_ok                                                   # 2e5 ≥ 1e5 × 1.2


def test_population_respects_cooldown_trading_days():
    # 같은 종목 신호가 날마다 있어도, 청산일 뒤 7 거래일 동안은 다시 들어가지 않는다
    n = 30
    b = {"di": np.arange(n), "o": np.full(n, 100.0), "h": np.full(n, 101.0), "l": np.full(n, 99.0),
         "c": np.full(n, 100.0), "raw": np.ones(n), "notrade": np.zeros(n, bool), "vol": np.ones(n)}
    b["l"][3] = 80.0                                                     # 3번 봉에서 손절
    f = {"atr": np.full(n, 1.0), "ema50": np.full(n, 50.0)}
    cal = pd.bdate_range("2026-01-05", periods=n)
    sigs = [EN.Sig("A", t, t, 100.0, 100.0, 1.0, 100.0, 50.0, float("nan"), 1.0, True, "gap") for t in range(2, 20)]
    pop = EN.population(sigs, {"A": b}, {"A": f}, 0, n - 1, kind="vcp", p=EN.VCP_DB, cal=cal)
    assert pop[0].s.gd == 2 and pop[0].exit_gd == 3
    assert pop[1].s.gd == 3 + 7 + 1


# ── 운영 check_exit_signal 과 틱 단위 대조 ─────────────────────────────────────

def _ops_exit_index(cls, sid, params, E, N, setup, ticks):
    """운영 객체에 포지션을 심고 틱마다 고점 갱신(risk.on_tick 순서) → check_exit_signal. 첫 청산 틱 인덱스."""
    from src.engine.strategy_base import Position, Signal, StrategyConfig
    s = cls(StrategyConfig(strategy_id=sid, name=sid, weight=1.0, params=dict(params)))
    pos = Position("000001", int(E), 1, "o1", sid)
    s.state.positions["000001"] = pos
    s._entry_atr["000001"] = float(N)
    s._candidates["000001"] = dict(setup)
    for k, px in enumerate(ticks):
        pos.high_since_buy = max(pos.high_since_buy, int(px))
        if s.check_exit_signal("000001", int(px), int(ticks[0])) != Signal.NONE:
            return k
    return None


def test_exit_tick_index_matches_operating_check_exit_signal():
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    rng = np.random.default_rng(7)
    n_exit = 0
    for trial in range(300):
        E = 10000
        atr = int(rng.integers(100, 700))
        N = atr
        low = int(E * rng.uniform(0.80, 0.995))
        ema50 = int(E * rng.uniform(0.85, 0.99))
        steps = rng.integers(-60, 70, 150)
        ticks = [E] + list(E + np.cumsum(steps))
        b = {"di": np.arange(2), "o": np.full(2, E, float), "h": np.full(2, E, float), "l": np.full(2, E, float),
             "c": np.full(2, E, float), "raw": np.ones(2), "notrade": np.zeros(2, bool), "vol": np.ones(2)}
        f = {"atr": np.full(2, float(atr)), "ema50": np.full(2, float(ema50))}
        cal = pd.bdate_range("2026-01-05", periods=2)
        ps = EN.BPos(EN.Sig("000001", 1, 1, E, E, N, E, low, float("nan"), 1.0, True, "gap"), b, f, 1,
                     kind="vcp", p=EN.VCP_DB, cal=cal)
        ps._ti = 1
        mine = None
        prev = ticks[0]
        for k, px in enumerate(ticks[1:], start=1):
            if ps._walk(prev, (px,), 1, False):
                mine = k
                break
            prev = px
        op = _ops_exit_index(VcpBreakoutStrategy, "vcp_breakout", EN.VCP_DB, E, N,
                             {"base_low": low, "base_high": E, "atr14": atr, "ema50": ema50}, ticks)
        assert mine == op, (trial, mine, op)
        n_exit += mine is not None
    assert n_exit > 50


def test_path_modes_entry_vs_later_split():
    # 진입 봉 양봉(시 99 저 95 고 103 종 102), E=100(장중 돌파), ATR 2.5 → 손절 95 · 샹들리에(고 103) 98
    # 다음 봉 음봉형 경로 차이: (시 102 고 108 저 99 종 104) — color(음봉 아님: 종 104 ≥ 시 102 → 양봉)…
    rows = [(100, 100, 98, 99), (99, 103, 95, 102), (102, 108, 99, 101)]
    b, f, cal = _one_bar_store(rows, atr=2.5)

    def run(mode):
        ps = EN.BPos(_sig(100.0, 100.0, 50.0, 2.5), b, f, 1, kind="vcp", p=EN.VCP_DB, cal=cal, mode=mode)
        if ps.intraday_phase(1, 1, True):
            return ("entry", ps.exit_px)
        if ps.open_phase(2, 2) or ps.intraday_phase(2, 2, False):
            return ("next", ps.exit_px)
        return None
    # 다음 봉 음봉(종 101 < 시 102): color = 시→고(108, 샹들리에 103)→저 99 → 103 에 판다
    assert run("color") == ("next", 103.0)
    # adverse: 진입 뒤 저 95 먼저 → 손절선 95
    assert run("adverse") == ("entry", 95.0)
    assert run("adv_entry") == ("entry", 95.0)
    # adverse_lit: 진입 봉은 저가가 돌파 앞(생존) · 다음 봉 시→저 99(샹들리에 98 위)→고 108→종 101 ≤ 103 → 103
    assert run("adverse_lit") == ("next", 103.0)
    assert run("adv_later") == ("next", 103.0)


def test_signal_slip_variant_fills_above_line_within_cap():
    bars, feats, uni = _sig_store(99.0, 103.0, 98.0, 102.0)
    s = EN.build_signals(bars, feats, np.ones(3), EN.VCP_DB, uni, slip=0.02)
    assert len(s) == 1 and s[0].E == pytest.approx(102.0) and s[0].entry == "cross"
    s4 = EN.build_signals(bars, feats, np.ones(3), EN.VCP_DB, uni, slip=0.04)               # 고가 103 에서 멈춤
    assert len(s4) == 1 and s4[0].E == 103.0
    bars2, feats2, uni2 = _sig_store(103.0, 106.0, 102.0, 105.0)                             # 시가가 이미 위
    s2 = EN.build_signals(bars2, feats2, np.ones(3), EN.VCP_DB, uni2, slip=0.02)
    assert s2[0].E == 103.0 and s2[0].entry == "gap"
