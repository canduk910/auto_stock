"""운용 전략 전수 점검(2026-10-05) — bull_flag_breakout(S4) 재현 층 단위 테스트.

사전 등록 = ``_workspace/analysis/strategy_audit_20261005/prereg.frozen.md`` §1.4 · §3.4.
폴/플래그 판정이 운영 ``_detect_pole_and_flag_detailed`` 와 같은지 · 측정 이동 익절(위로 깨는 선) ·
시간 청산(달력일 > max_hold + 2 → 그날 시가) · 운영 ``check_exit_signal`` 과 틱 단위 대조.
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
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig
    return BullFlagBreakoutStrategy(StrategyConfig(strategy_id="bull_flag_breakout", name="bfb", weight=1.0,
                                                   params=dict(EN.BFB_DB)))


def _flaggy(seed: int, n: int = 160):
    """정수 OHLCV — 군데군데 급등(폴) 뒤 얕은 눌림(플래그)이 생기게."""
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0, 0.02, n)
    for s in rng.integers(25, n - 15, 6):
        r[s:s + 4] += rng.uniform(0.04, 0.09)
        r[s + 4:s + 9] = rng.normal(-0.004, 0.008, 5)
    c = np.round(10000 * np.exp(np.cumsum(r))).astype(float)
    o = np.round(np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.004, n)))
    h = np.maximum(o, c) + np.round(c * rng.uniform(0, 0.01, n))
    lo = np.minimum(o, c) - np.round(c * rng.uniform(0, 0.01, n))
    v = np.round(rng.lognormal(12, 0.4, n))
    for s in range(n):                      # 급등 봉 거래량 크게
        if r[s] > 0.035:
            v[s] *= 4
    return o, h, lo, c, v


def _candles(o, h, l, c, v, i: int, avail: int) -> list:
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
    prm = d["bull_flag_breakout"]["params"]
    prm = prm if isinstance(prm, dict) else json.loads(prm)
    for k, v in EN.BFB_DB.items():
        assert prm[k] == v, k


def test_pole_flag_detection_matches_operating(ops):
    n_cmp = n_found = 0
    keys = ("flag_high", "flag_low", "pole_high", "pole_start")
    for seed in range(12):
        o, h, l, c, v = _flaggy(seed)
        det = EN.bfb_detect(o, h, l, c, v)
        for i in range(22, len(c)):
            cand = _candles(o, h, l, c, v, i, min(EN.BFB_FETCH_DAYS, i + 1))
            res, stage, _ = ops._detect_pole_and_flag_detailed(cand)
            n_cmp += 1
            assert bool(det["found"][i]) == (res is not None), (seed, i, stage)
            if res is not None:
                n_found += 1
                for k in keys:
                    assert det[k][i] == res[k], (seed, i, k)
                assert int(det["flag_avg"][i]) == res["flag_avg_volume"]
                assert (det["fl"][i], det["pl"][i]) == (res["flag_len"], res["pole_len"])
    assert n_cmp > 1500 and n_found > 30


def test_required_length_and_atr_gate():
    o, h, l, c, v = _flaggy(3)
    f = EN.bfb_features({"o": o, "h": h, "l": l, "c": c, "vol": v})
    assert not f["cand"][:EN.BFB_REQUIRED_LEN - 1].any()
    i = np.nonzero(f["cand"])[0]
    assert len(i) > 0
    k = i[0]
    assert f["target"][k] == pytest.approx(f["line"][k] + (
        EN.bfb_detect(o, h, l, c, v)["pole_high"][k] - EN.bfb_detect(o, h, l, c, v)["pole_start"][k]))


# ── 청산 ───────────────────────────────────────────────────────────────────

def _store(rows, atr=2.0, start="2026-01-05", dates=None):
    n = len(rows)
    b = {"di": np.arange(n), "o": np.array([r[0] for r in rows], float), "h": np.array([r[1] for r in rows], float),
         "l": np.array([r[2] for r in rows], float), "c": np.array([r[3] for r in rows], float),
         "raw": np.ones(n), "notrade": np.zeros(n, bool), "vol": np.ones(n)}
    f = {"atr": np.full(n, atr), "ema50": np.full(n, np.nan)}
    cal = pd.DatetimeIndex(dates) if dates is not None else pd.bdate_range(start, periods=n)
    return b, f, cal


def _sig(E, low, target, N=2.0, entry="cross"):
    return EN.Sig("000001", 1, 1, E, E, N, E, low, target, 1.0, True, entry)


def test_measured_move_take_profit_full_exit_at_target():
    b, f, cal = _store([(100, 100, 98, 99), (99, 101, 98.5, 100.5), (101, 112, 100.5, 111)], atr=4.0)
    ps = EN.BPos(_sig(100.0, 90.0, 110.0, N=4.0), b, f, 1, kind="bfb", p=EN.BFB_DB, cal=cal)
    assert not ps.intraday_phase(1, 1, True)
    assert not ps.open_phase(2, 2)
    assert ps.intraday_phase(2, 2, False)
    assert ps.exit_reason == "TAKE_PROFIT" and ps.exit_px == 110.0


def test_take_profit_gap_open_fills_at_open():
    b, f, cal = _store([(100, 100, 98, 99), (99, 101, 98.5, 100.5), (113, 115, 112, 114)], atr=4.0)
    ps = EN.BPos(_sig(100.0, 90.0, 110.0, N=4.0), b, f, 1, kind="bfb", p=EN.BFB_DB, cal=cal)
    ps.intraday_phase(1, 1, True)
    assert ps.open_phase(2, 2) and ps.exit_px == 113 and ps.exit_reason == "TAKE_PROFIT"


def test_adverse_path_takes_stop_before_target_in_same_bar():
    rows = [(100, 100, 98, 99), (99, 101, 98.5, 100.5), (101, 112, 92, 105)]
    b, f, cal = _store(rows, atr=4.0)
    ps = EN.BPos(_sig(100.0, 90.0, 110.0, N=4.0), b, f, 1, kind="bfb", p=EN.BFB_DB, cal=cal, mode="adverse")
    ps.intraday_phase(1, 1, True)
    ps.open_phase(2, 2)
    assert ps.intraday_phase(2, 2, False) and ps.exit_reason == "STOP_LOSS"        # 저가 먼저
    # 같은 봉이 양봉이면 color 도 시→저→고 라 손절 먼저 · 음봉이면 color 는 시→고→저 라 익절 먼저
    ps2 = EN.BPos(_sig(100.0, 90.0, 110.0, N=4.0), b, f, 1, kind="bfb", p=EN.BFB_DB, cal=cal, mode="color")
    ps2.intraday_phase(1, 1, True)
    ps2.open_phase(2, 2)
    assert ps2.intraday_phase(2, 2, False) and ps2.exit_reason == "STOP_LOSS"
    b3, f3, _ = _store([(100, 100, 98, 99), (99, 101, 98.5, 100.5), (101, 112, 92, 98)], atr=4.0)
    ps3 = EN.BPos(_sig(100.0, 90.0, 110.0, N=4.0), b3, f3, 1, kind="bfb", p=EN.BFB_DB, cal=cal, mode="color")
    ps3.intraday_phase(1, 1, True)
    ps3.open_phase(2, 2)
    assert ps3.intraday_phase(2, 2, False) and ps3.exit_reason == "TAKE_PROFIT" and ps3.exit_px == 110.0


def test_time_exit_at_open_after_calendar_days():
    # 매수 월(01-05) → 달력일 > 7 인 첫 거래일 = 01-13(화) 시가
    dates = pd.bdate_range("2026-01-02", periods=9)            # 01-02(금) 신호 봉, 01-05(월) 진입 …
    rows = [(100, 100, 99, 99.5)] + [(100.0, 100.4, 99.8, 100.1)] * 8
    b, f, cal = _store(rows, atr=1.0, dates=dates)
    ps = EN.BPos(_sig(100.0, 90.0, 130.0, N=1.0, entry="gap"), b, f, 1, kind="bfb", p=EN.BFB_DB, cal=cal)
    assert not ps.intraday_phase(1, 1, True)
    exited = None
    for t in range(2, 9):
        if ps.open_phase(t, t) or ps.intraday_phase(t, t, False):
            exited = t
            break
    assert exited is not None and str(cal[exited].date()) == "2026-01-13"
    assert ps.exit_reason == "TIME_EXIT" and ps.exit_px == 100.0


def test_cooldown_three_trading_days():
    n = 20
    b = {"di": np.arange(n), "o": np.full(n, 100.0), "h": np.full(n, 101.0), "l": np.full(n, 99.0),
         "c": np.full(n, 100.0), "raw": np.ones(n), "notrade": np.zeros(n, bool), "vol": np.ones(n)}
    b["l"][3] = 80.0
    f = {"atr": np.full(n, 1.0), "ema50": np.full(n, np.nan)}
    cal = pd.bdate_range("2026-01-05", periods=n)
    sigs = [EN.Sig("A", t, t, 100.0, 100.0, 1.0, 100.0, 50.0, 200.0, 1.0, True, "gap") for t in range(2, 15)]
    pop = EN.population(sigs, {"A": b}, {"A": f}, 0, n - 1, kind="bfb", p=EN.BFB_DB, cal=cal)
    assert pop[0].exit_gd == 3 and pop[1].s.gd == 3 + 3 + 1


# ── 운영 check_exit_signal 과 틱 단위 대조 ─────────────────────────────────────

def test_exit_tick_index_matches_operating_check_exit_signal():
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategy_base import Position, Signal, StrategyConfig
    rng = np.random.default_rng(11)
    n_exit = n_tp = 0
    for trial in range(300):
        E = 10000
        atr = int(rng.integers(100, 600))
        flag_low = int(E * rng.uniform(0.85, 0.995))
        flag_high = E
        pole_start = int(E * rng.uniform(0.7, 0.85))
        pole_high = int(E * rng.uniform(0.95, 1.02))
        target = flag_high + (pole_high - pole_start)
        steps = rng.integers(-70, 90, 120)
        ticks = [E] + list(E + np.cumsum(steps))
        b = {"di": np.arange(2), "o": np.full(2, E, float), "h": np.full(2, E, float), "l": np.full(2, E, float),
             "c": np.full(2, E, float), "raw": np.ones(2), "notrade": np.zeros(2, bool), "vol": np.ones(2)}
        f = {"atr": np.full(2, float(atr)), "ema50": np.full(2, np.nan)}
        cal = pd.bdate_range("2026-01-05", periods=2)
        ps = EN.BPos(EN.Sig("000001", 1, 1, E, E, atr, E, flag_low, float(target), 1.0, True, "gap"), b, f, 1,
                     kind="bfb", p=EN.BFB_DB, cal=cal)
        ps._ti = 1
        mine, why = None, None
        prev = ticks[0]
        for k, px in enumerate(ticks[1:], start=1):
            if ps._walk(prev, (px,), 1, False):
                mine, why = k, ps.exit_reason
                break
            prev = px
        s = BullFlagBreakoutStrategy(StrategyConfig(strategy_id="bull_flag_breakout", name="b", weight=1.0,
                                                    params=dict(EN.BFB_DB)))
        pos = Position("000001", E, 1, "o1", "bull_flag_breakout")
        s.state.positions["000001"] = pos
        s._entry_atr["000001"] = float(atr)
        s._candidates["000001"] = {"flag_low": flag_low, "flag_high": flag_high, "pole_high": pole_high,
                                   "pole_start": pole_start, "atr14": atr}
        op, op_sig = None, None
        for k, px in enumerate(ticks):
            pos.high_since_buy = max(pos.high_since_buy, int(px))
            sg = s.check_exit_signal("000001", int(px), E)
            if sg != Signal.NONE:
                op, op_sig = k, sg.value
                break
        assert mine == op, (trial, mine, op)
        if op is not None:
            n_exit += 1
            assert (why == "TAKE_PROFIT") == (op_sig == "TAKE_PROFIT")
            n_tp += op_sig == "TAKE_PROFIT"
    assert n_exit > 50 and n_tp > 5
