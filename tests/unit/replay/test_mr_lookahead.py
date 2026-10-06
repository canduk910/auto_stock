"""평균회귀 연구(트랙 R) — 룩어헤드·체결 규약 테스트 (지시서 §5.1 의 1~4·6).

연구 전용 의존성(statsmodels·scipy)이 없는 운영 테스트 환경에서는 통째로 건너뛴다.
대상은 ``tools/replay/`` 의 순수 함수뿐이다 — DB·네트워크·``src/`` 쓰기 없음.
"""
from __future__ import annotations

import math
import os
import sys

import pytest

pytest.importorskip("statsmodels")
pytest.importorskip("scipy")

import numpy as np  # noqa: E402

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import judge as J  # noqa: E402
from replay.execution import Rule, simulate_ticker  # noqa: E402
from replay.portfolio import run_account  # noqa: E402
from replay.run_mean_reversion import mu_exec_series  # noqa: E402
from replay.strategies.mean_reversion.ou import efficiency_ratio, rolling_beta  # noqa: E402
from replay.strategies.mean_reversion.signals import SignalSeries, estimate_series  # noqa: E402


def _ou_panel(n=400, seed=3, phi=0.6):
    rng = np.random.default_rng(seed)
    lb = np.cumsum(rng.normal(0, 0.01, n)) + 7.0
    e = np.zeros(n)
    for i in range(1, n):
        e[i] = phi * e[i - 1] + rng.normal(0, 0.02)
    lp = 1.2 * lb + e - 3.0
    return lp, lb


@pytest.mark.parametrize("t", [150, 233, 301])
def test_future_change_does_not_alter_past_signals(t):
    """§5.1-1 — t 이후 데이터를 바꿔도 t 이하의 β·OU·ADF·z 가 그대로다."""
    lp, lb = _ou_panel()
    halt = np.zeros(len(lp), dtype=bool)
    base = estimate_series(lp, lb, halt)
    lp2, lb2 = lp.copy(), lb.copy()
    rng = np.random.default_rng(99)
    lp2[t + 1:] += rng.normal(0, 0.5, len(lp) - t - 1)
    lb2[t + 1:] += rng.normal(0, 0.5, len(lp) - t - 1)
    pert = estimate_series(lp2, lb2, halt)
    for name in ("z", "hl", "hl_adj", "sigma_stat", "theta", "adf_p"):
        a, b = getattr(base, name)[: t + 1], getattr(pert, name)[: t + 1]
        assert np.allclose(a, b, equal_nan=True), name
    assert np.array_equal(base.valid[: t + 1], pert.valid[: t + 1])
    assert np.array_equal(base.est_reason[: t + 1], pert.est_reason[: t + 1])
    for s in range(61, t + 1):
        assert rolling_beta(lp, lb, s) == pytest.approx(rolling_beta(lp2, lb2, s))


def test_beta_uses_lagged_window_only():
    """β_t 는 t-60..t-1 만 본다 — t 일 값을 바꿔도 β_t 가 그대로다."""
    lp, lb = _ou_panel()
    b0 = rolling_beta(lp, lb, 200)
    lp2 = lp.copy()
    lp2[200] += 5.0
    assert rolling_beta(lp2, lb, 200) == pytest.approx(b0)


def _flat_sig(n, z, valid=True, hl=2.0, est_every=5):
    return SignalSeries(
        z=np.asarray(z, dtype=float), valid=np.full(n, valid), is_est=np.array([i % est_every == 0 for i in range(n)]),
        est_reason=np.zeros(n, dtype=np.int8), hl=np.full(n, hl), hl_adj=np.full(n, hl),
        sigma_stat=np.full(n, 0.05), theta=np.full(n, math.log(2) / hl), adf_p=np.full(n, 0.01))


def test_signal_at_close_fills_next_open():
    """§5.1-2 — t 종가 신호 → t+1 시가 체결 (가격은 t+1 시가)."""
    n = 30
    o = np.linspace(100, 129, n)
    c = o + 0.5
    h, l = c + 1.0, o - 0.2
    z = np.zeros(n)
    z[10] = -2.6
    z[11:14] = -1.0
    z[14] = 0.5
    sig = _flat_sig(n, z, hl=5.0)
    tr = simulate_ticker(o, h, l, c, sig, np.ones(n, bool), np.ones(n), Rule("z", -2.0, 0.0, 0.0038, 50.0, 9.0))
    assert len(tr) == 1
    assert tr[0]["sig_day"] == 10 and tr[0]["ei"] == 11
    assert tr[0]["entry_px"] == o[11]
    assert tr[0]["xi"] == 15 and tr[0]["exit_px"] == o[15] and tr[0]["reason"] == "profit"


def test_timestop_counts_business_day_indices():
    """§5.1-3 — 타임스톱은 영업일(달력 인덱스) 기준. hl=1 → ceil(2)=2 → 보유 3영업일째 종가 판정."""
    n = 30
    o = np.full(n, 100.0)
    c = np.full(n, 100.0)
    h, l = c + 0.5, c - 0.5
    z = np.full(n, -1.0)
    z[5] = -3.0
    sig = _flat_sig(n, z, hl=1.0, est_every=1000)  # 재추정 없음 → 회귀 깨짐 없음
    tr = simulate_ticker(o, h, l, c, sig, np.ones(n, bool), np.ones(n), Rule("z", -2.0, 0.0, 0.0, 50.0, 9.0))
    assert tr[0]["ei"] == 6
    assert tr[0]["reason"] == "timeout"
    assert tr[0]["xi"] == 6 + 3 + 1  # held=3 > 2 인 날(인덱스 9) 종가 → 10 시가


def test_market_unit_reads_only_prior_bars():
    """§5.1-4 — 체결일 d 의 시장 유닛은 d-1 봉까지만 읽는다(d 이후를 바꿔도 같다)."""
    rng = np.random.default_rng(5)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 200)))
    base = mu_exec_series(closes)
    for d in (90, 120, 170):
        alt = closes.copy()
        alt[d:] *= 0.5
        assert np.array_equal(mu_exec_series(alt)[: d + 1], base[: d + 1], equal_nan=True)
    assert np.all(np.isnan(base[:80])) and np.isfinite(base[80])


def test_market_unit_zero_blocks_entry():
    """D5 — 체결일 시장 유닛 0 이면 진입하지 않는다(결측은 규칙에 따라)."""
    n = 20
    o = c = np.full(n, 100.0)
    h, l = c + 0.5, c - 0.5
    z = np.zeros(n)
    z[5] = -3.0
    sig = _flat_sig(n, z, hl=5.0)
    mu = np.ones(n)
    mu[6] = 0.0
    assert simulate_ticker(o, h, l, c, sig, np.ones(n, bool), mu, Rule("z", -2.0, 0.0, 0.0038)) == []
    mu[6] = np.nan
    assert simulate_ticker(o, h, l, c, sig, np.ones(n, bool), mu, Rule("z", -2.0, 0.0, 0.0038)) == []
    got = simulate_ticker(o, h, l, c, sig, np.ones(n, bool), mu, Rule("z", -2.0, 0.0, 0.0038, mu_missing_enter=True))
    assert len(got) == 1


def test_disaster_stop_fills_at_stop_or_gap_open():
    n = 20
    o = np.full(n, 100.0)
    c = np.full(n, 100.0)
    h = c + 0.5
    l = c - 0.5
    l[8] = 90.0                      # 장중 −10% → 손절가(93) 체결
    z = np.full(n, -1.0)
    z[5] = -3.0
    sig = _flat_sig(n, z, hl=5.0, est_every=1000)
    tr = simulate_ticker(o, h, l, c, sig, np.ones(n, bool), np.ones(n), Rule("z", -2.0, 0.0, 0.0038, 7.0, 9.0))
    assert tr[0]["reason"] == "disaster_pct" and tr[0]["exit_px"] == pytest.approx(93.0)
    o2 = o.copy()
    o2[8] = 88.0                     # 갭 하락 → 시가 체결
    l2 = l.copy()
    l2[8] = 87.0
    tr = simulate_ticker(o2, h, l2, c, sig, np.ones(n, bool), np.ones(n), Rule("z", -2.0, 0.0, 0.0038, 7.0, 9.0))
    assert tr[0]["exit_px"] == 88.0


@pytest.mark.parametrize("t", [40, 77])
def test_er_ignores_future_and_terciles_use_front_only(t):
    """§5.1-6 — ER 은 t 이후를 바꿔도 같고, 삼분위 경계는 앞 60% 만으로 정한다."""
    rng = np.random.default_rng(11)
    cl = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 120)))
    er = np.array([efficiency_ratio(cl, i) for i in range(len(cl))])
    alt = cl.copy()
    alt[t + 1:] *= 1.7
    er2 = np.array([efficiency_ratio(alt, i) for i in range(len(cl))])
    assert np.allclose(er[: t + 1], er2[: t + 1], equal_nan=True)
    cut = J.split_index(len(cl))
    assert J.er_terciles(er, cut) == J.er_terciles(np.concatenate([er[:cut], er2[cut:] * 0 + 0.99]), cut)


def test_account_settles_same_day_stop():
    """진입 당일 손절(xi == ei) 거래가 슬롯을 영구 점유하지 않는다 (2026-10-04 발견 결함의 회귀)."""
    closes = np.full((10, 2), 100.0)
    trades = [dict(tj=0, ei=2, xi=2, entry_px=100.0, exit_px=93.0, entry_raw=100.0, z_entry=-2.5),
              dict(tj=1, ei=4, xi=6, entry_px=100.0, exit_px=101.0, entry_raw=100.0, z_entry=-2.1)]
    r = run_account(trades, closes, 10, budget=237_500, slots=1, cost=0.0)
    assert r["n_filled"] == 2 and r["n_slot_full"] == 0


def test_account_counts_unaffordable_without_one_share_fallback():
    closes = np.full((5, 1), 300_000.0)
    trades = [dict(tj=0, ei=1, xi=3, entry_px=300_000.0, exit_px=300_000.0, entry_raw=300_000.0, z_entry=-2.0)]
    r = run_account(trades, closes, 5, budget=237_500, slots=2, cost=0.0038)
    assert r["n_unaffordable"] == 1 and r["n_filled"] == 0


def test_cluster_bootstrap_is_seeded():
    v = np.random.default_rng(1).normal(0, 1, 200)
    cl = np.repeat(np.arange(40), 5)
    assert J.bootstrap_mean(v, cl) == J.bootstrap_mean(v, cl)
