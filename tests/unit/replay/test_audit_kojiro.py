"""운용 전략 전수 점검(2026-10-05) S1 kojiro — 전략 층 단위 테스트.

사전 등록 = ``_workspace/analysis/strategy_audit_20261005/prereg.frozen.md`` §3.1 · §1.4.
운영 지표(``src.engine.kojiro_indicators.enrich``)·운영 전략 메서드와 값을 대조한다. 네트워크·DB·보관소 0.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit.sizing import OpSizer  # noqa: E402
from replay.strategies import kojiro as KJ  # noqa: E402
from src.engine.kojiro_indicators import KojiroIndicatorConfig, enrich  # noqa: E402
from src.engine.strategies.kojiro import KojiroStrategy, _stage_recently  # noqa: E402

pytestmark = pytest.mark.unit

P = {**KojiroStrategy.DEFAULT_PARAMS, "breakeven_promote_atr": 1.5, "sizing_mode": "turtle",
     "position_ratio": 0.166, "max_positions": 6, "market_unit_mode": "enforce"}


def _series(n: int, seed: int):
    """추세 국면이 바뀌는 합성 일봉(스테이지 전환이 자주 나도록)."""
    rng = np.random.default_rng(seed)
    drift = np.repeat(rng.choice([-0.012, -0.004, 0.006, 0.015], size=n // 15 + 1), 15)[:n]
    r = drift + rng.normal(0, 0.018, n)
    c = 10000 * np.exp(np.cumsum(r))
    o = c * np.exp(rng.normal(0, 0.006, n))
    h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.01, n)))
    l = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.01, n)))
    return np.round(o), np.round(h), np.round(l), np.round(c)


def _bars(o, h, l, c):
    n = len(c)
    return {"di": np.arange(n), "o": o, "h": h, "l": l, "c": c, "o_raw": o, "c_raw": c, "raw": np.ones(n),
            "tv": np.full(n, 5e9), "vol": np.full(n, 1e5), "mktcap": np.full(n, 1e11),
            "notrade": np.zeros(n, dtype=bool)}


def _op_decision(o, h, l, c, i, p):
    """운영 prepare 한 종목 판정(봉 i 까지 최근 100봉) — kojiro.py prepare 본문과 같은 순서."""
    s = max(0, i - KJ.WINDOW + 1)
    df = pd.DataFrame({"open": o[s:i + 1], "high": h[s:i + 1], "low": l[s:i + 1], "close": c[s:i + 1],
                       "volume": np.ones(i + 1 - s)}).astype("int64")
    cfg = KojiroIndicatorConfig(ema_short=p["ema_short"], ema_mid=p["ema_mid"], ema_long=p["ema_long"],
                                macd_signal=p["macd_signal"], atr_period=p["atr_period"],
                                slope_lookback=p["slope_lookback"])
    en = enrich(df, cfg)
    last = en.iloc[-1]
    stages = en["stage"].tolist()
    pc = int(last["close"])
    atr = float(last["atr"])
    ratio = atr / pc
    tech = (i + 1 - s >= KJ.MIN_BARS and p["atr_ratio_min"] <= ratio <= p["atr_ratio_max"]
            and last["stage"] == 1 and bool(last["ema_s_up"] and last["ema_m_up"] and last["ema_l_up"])
            and _stage_recently(stages, 6, 1, within=int(p["stage1_freshness"])) and pc > float(last["ema_s"]))
    rank = KojiroStrategy._rank_candidate_components(None, en, stages, int(p["stage1_freshness"]))
    return {"atr": atr, "stage": last["stage"], "tech": bool(tech), "rank": rank}


# ── 지표 = 운영 enrich (창 100봉, ewm 재시작) ─────────────────────────────

def test_fir_equals_pandas_ewm_on_window():
    x = np.random.default_rng(1).normal(100, 5, 300)
    L, a = 100, 2 / 21
    f = KJ._fir(x, a, L)
    for i in (99, 150, 299):
        ref = pd.Series(x[i - L + 1:i + 1]).ewm(alpha=a, adjust=False).mean().iloc[-1]
        assert f[i] == pytest.approx(ref, rel=1e-12)


@pytest.mark.parametrize("seed", [3, 7, 11])
def test_features_match_operating_enrich_every_bar(seed):
    o, h, l, c = _series(420, seed)
    f = KJ.features(_bars(o, h, l, c), P)
    n_tech = 0
    for i in range(KJ.MIN_BARS - 1, len(c)):
        op = _op_decision(o, h, l, c, i, P)
        assert f["atr"][i] == pytest.approx(op["atr"], rel=1e-9), i
        assert int(f["stage"][i]) == int(op["stage"]), i
        assert bool(f["tech"][i]) == op["tech"], i
        n_tech += op["tech"]
        for k in range(3):
            assert f["rank"][k, i] == pytest.approx(op["rank"][k], rel=1e-7, abs=1e-12), (i, k)
    assert n_tech > 0          # 합성 시리즈가 실제로 후보를 낸다(공허한 대조 방지)


def test_short_history_uses_window_from_first_bar():
    o, h, l, c = _series(95, 5)
    f = KJ.features(_bars(o, h, l, c), P)
    assert not f["tech"][: KJ.MIN_BARS - 1].any()     # 80봉 미만은 후보 없음
    op = _op_decision(o, h, l, c, 90, P)
    assert f["atr"][90] == pytest.approx(op["atr"], rel=1e-9)


def test_score_candidates_is_operating_minmax():
    raw = {"A": (0.01, 0.2, 5.0), "B": (0.0, 0.0, 1.0)}
    sc = KojiroStrategy._score_candidates(None, raw, P)
    assert sc["A"] == pytest.approx(1.0) and sc["B"] == pytest.approx(0.0)


# ── 신호 ─────────────────────────────────────────────────────────────────

def test_gap_filter_and_next_day_open_entry():
    o, h, l, c = _series(420, 3)
    b = _bars(o, h, l, c)
    f = KJ.features(b, P)
    i = int(np.nonzero(f["tech"])[0][0])
    u = KJ.universe(b, P)
    m = np.ones(len(c))
    sigs, cnt = KJ.build_signals({"005930": b}, {"005930": f}, {"005930": u}, m, P)
    s = next((x for x in sigs if x.extra["i"] == i), None)
    gap = (o[i + 1] - math.floor(c[i])) / math.floor(c[i]) * 100
    if -4.0 < gap < 5.0:
        assert s is not None and s.E == o[i + 1] and s.N == f["atr"][i]
    else:
        assert s is None
    # 갭 +5% 를 만들면 빠진다
    b2 = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in b.items()}
    b2["o"][i + 1] = math.floor(c[i]) * 1.05
    sigs2, _ = KJ.build_signals({"005930": b2}, {"005930": f}, {"005930": u}, m, P)
    assert all(x.extra["i"] != i for x in sigs2)


def test_universe_cuts():
    o, h, l, c = _series(120, 2)
    b = _bars(o, h, l, c)
    b["mktcap"][10] = 4.9e10
    b["tv"][11] = 9.9e8
    b["c_raw"][12] = 2_999
    u = KJ.universe(b, P)
    assert not u[10] and not u[11] and not u[12] and u[13]


# ── 포지션 경로(운영 check_exit_signal) ───────────────────────────────────

def _pos(o, h, l, c, stage=None, atr=None, E=100.0, N=2.0, p=P):
    n = len(c)
    b = _bars(np.array(o, float), np.array(h, float), np.array(l, float), np.array(c, float))
    f = {"atr": np.array(atr if atr is not None else [N] * n, float),
         "stage": np.array(stage if stage is not None else [1] * n, dtype=np.int8)}
    s = KJ.Sig("005930", 1, 1, E, E, N, 1.0)
    return KJ.KJPos(s, b, f, 10, p), b


def test_hard_stop_pct_gap_fills_at_open():
    ps, _ = _pos([100, 100, 90], [100, 101, 91], [100, 99, 89], [100, 100, 90], N=1.0)
    assert not ps.intraday_phase(1, 1, True)
    assert ps.open_phase(2, 2) and ps.exit_px == 90 and ps.exit_reason == "STOP_LOSS"


def test_atr_floor_is_tighten_only():
    # 진입 ATR 2 → 바닥 96. 다음 날 ATR 5 로 커져도 바닥은 96 (91 로 내려가지 않는다)
    ps, _ = _pos([100, 100, 97, 97], [100, 100, 98, 97.5], [100, 99.5, 96.5, 95], [100, 100, 97, 95.5],
                 atr=[2, 2, 5, 5])
    assert not ps.intraday_phase(1, 1, True)
    assert not ps.open_phase(2, 2) and not ps.intraday_phase(2, 2, False)
    assert ps.floor == pytest.approx(96.0)
    assert ps.open_phase(3, 3) is False
    assert ps.intraday_phase(3, 3, False) and ps.exit_px == pytest.approx(96.0)


def test_breakeven_promotion_lifts_floor_to_entry():
    # 고점 103 ≥ 100 + 1.5×2 → 바닥 = 100. 그 뒤 99 까지 밀리면 100 에서 청산(샹들리에 103−5=98 보다 높다)
    ps, _ = _pos([100, 100, 101], [100, 103, 101], [100, 100.5, 99], [100, 102, 99.5])
    assert not ps.intraday_phase(1, 1, True)
    assert ps.be_hit and ps.floor == pytest.approx(100.0)
    assert not ps.open_phase(2, 2)
    assert ps.intraday_phase(2, 2, False) and ps.exit_px == pytest.approx(100.0) and ps.exit_reason == "STOP_LOSS"


def test_breakeven_off_when_param_zero():
    ps, _ = _pos([100, 100, 101], [100, 103, 101], [100, 100.5, 99], [100, 102, 99.5],
                 p={**P, "breakeven_promote_atr": 0.0})
    ps.intraday_phase(1, 1, True)
    assert not ps.be_hit and ps.floor == pytest.approx(96.0)


def test_stage3_exits_next_open():
    # 봉 2 의 스테이지 3 → 봉 3 시가 TREND_EXIT
    ps, _ = _pos([100, 100, 101, 102], [100, 101, 102, 103], [100, 99.5, 100, 101], [100, 100.5, 101.5, 102.5],
                 stage=[1, 1, 3, 3])
    assert not ps.intraday_phase(1, 1, True)
    assert not ps.open_phase(2, 2) and not ps.intraday_phase(2, 2, False)
    assert ps.open_phase(3, 3) and ps.exit_reason == "TREND_EXIT" and ps.exit_px == 102


def test_chandelier_intrabar_ratchet():
    # 봉 2 양봉: 시→저→고→종. 고가 120 이 샹들리에를 120−5=115 로 올리고, 종가 114 는 경로상 고가 뒤라 청산
    ps, _ = _pos([100, 100, 110], [100, 101, 120], [100, 99.5, 109], [100, 100.5, 114])
    ps.intraday_phase(1, 1, True)
    assert not ps.open_phase(2, 2)
    assert ps.intraday_phase(2, 2, False) and ps.exit_reason == "TRAILING_STOP" and ps.exit_px == pytest.approx(115)


def test_adverse_path_hits_stop_first():
    # 같은 봉에 바닥(96)과 새 고점이 다 있다 — 불리판은 저가 먼저
    ps, _ = _pos([100, 100, 100], [100, 101, 110], [100, 99.5, 95], [100, 100.5, 99], p=P)
    ps.mode = "adverse"
    ps.intraday_phase(1, 1, True)
    assert not ps.open_phase(2, 2)
    assert ps.intraday_phase(2, 2, False) and ps.exit_px == pytest.approx(96.0)


def test_locked_limit_down_defers_exit():
    # 봉 2 시가 = 전일 종가 × 0.70 · 고가 = 저가 → 그날 못 판다, 다음 날 시가
    ps, _ = _pos([100, 100, 70, 68], [100, 101, 70, 72], [100, 99.5, 70, 66], [100, 100, 70, 69])
    ps.intraday_phase(1, 1, True)
    assert not ps.open_phase(2, 2) and ps.locked_days == 1
    assert not ps.intraday_phase(2, 2, False)
    assert ps.open_phase(3, 3) and ps.exit_px == 68


# ── 계좌 게이트 ───────────────────────────────────────────────────────────

class _FakeSizer:
    def qty(self, *a, **k):
        return 3

    def blocks_entry(self, *a, **k):
        return False


def _held(sector, E=100.0, N=2.0, qty=10):
    ps, _ = _pos([E] * 3, [E] * 3, [E] * 3, [E] * 3, E=E, N=N)
    ps.s.sector = sector
    ps.k = qty
    return ps


def test_sector_cap_blocks_third_same_sector():
    g = KJ.Gates(P, _FakeSizer(), risk_cap=False)
    g.opened = [_held("반도체"), _held("반도체")]
    s = KJ.Sig("000660", 1, 5, 100, 100, 2, 1.0, sector="반도체")
    assert g.size(s, 10_000_000, 0) == (0, "sector")
    s2 = KJ.Sig("000661", 1, 5, 100, 100, 2, 1.0, sector="미분류-000661")
    assert g.size(s2, 10_000_000, 0)[0] == 3


def test_open_risk_cap_blocks_when_sum_reaches_limit():
    g = KJ.Gates(P, _FakeSizer(), sector_cap=False)
    # 랏 1: k=1000 · E 100 · 바닥 96 · 받침 92 · 샹들리에 95 → 실효 96 → 리스크 4,000
    g.opened = [_held("A", qty=1000)]
    s = KJ.Sig("000660", 1, 5, 100, 100, 2, 1.0, sector="B")
    assert g.size(s, int(4_000 / 0.045) - 1, 0) == (0, "riskcap")
    assert g.size(s, int(4_000 / 0.045) + 1000, 0)[0] == 3


def test_daily_loss_limit_gate():
    g = KJ.Gates(P, _FakeSizer(), sector_cap=False, risk_cap=False)
    x = _held("A", qty=100)
    x._exit(90.0, "STOP_LOSS", 5, "open")
    x.cost_basis = 100 * 100.0
    g.opened = [x]
    s = KJ.Sig("000660", 1, 5, 100, 100, 2, 1.0)
    assert g.size(s, 10_000, 0) == (0, "dailyloss")          # −1,000 / 10,000 = −10% ≤ −8%
    assert g.size(s, 100_000, 0)[0] == 3


# ── 운영 사이저(kojiro 터틀) ─────────────────────────────────────────────

def test_op_sizer_turtle_and_market_unit():
    sz = OpSizer(KojiroStrategy, "kojiro", P)
    B = 4_707_820
    q = sz.qty(50_000, 1_500.0, budget=B, used=0, m=1.0)
    assert q == min(math.floor(B * 0.005 / 1_500.0), int(B * 0.166) // 50_000)
    assert sz.blocks_entry(50_000, 1_500.0, budget=B, used=0, m=0.0)
    assert sz.qty(50_000, 1_500.0, budget=B, used=0, m=0.5) <= q
