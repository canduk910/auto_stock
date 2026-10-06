"""바탕 층 검증(2026-10-05) 실행기 단위 테스트 — 합성 입력만(보관소·DB 0).

- 낙폭 · 덧씌움 발동/해제(Y1 · Y2 · Y3) · −10% 사건 재무장
- 목표 비중이 그날 종가를 보지 않는다(세션 D = 종가 D−1 까지)
- 계좌 집행: 비용 · 비중이 바뀐 자산만 매매 · 현금 음수 없음
- 격자 133 · 짝 부트스트랩 대칭
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for p in (_TOOLS, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from replay import base_layer as BL  # noqa: E402

pytestmark = pytest.mark.unit


def _cal(n):
    return pd.bdate_range("2021-01-04", periods=n)


def _prices(n, seed=1):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.012, (n, len(BL.ASSETS))), axis=0))
    o = c * np.exp(rng.normal(0, 0.003, c.shape))
    return o, c


def test_grid_133_unique():
    g = BL.grid()
    assert len(g) == BL.N_COMBOS == 133
    assert len({BL.name(cb) for cb in g}) == 133
    assert g[0] == {"fam": "B0"}


def test_drawdown60_matches_definition():
    c = np.r_[np.linspace(100, 120, 70), np.linspace(119, 100, 30)]
    dd = BL.drawdown60(c)
    assert np.isnan(dd[58]) and np.isfinite(dd[59])
    t = 85
    assert dd[t] == pytest.approx(c[t] / c[t - 59:t + 1].max() - 1)


def _dd_path():
    # 60봉 상승 → 12% 하락 → 회복
    c = np.r_[np.linspace(100, 130, 80), np.linspace(130, 112, 10), np.linspace(112, 135, 40)]
    return c, BL.drawdown60(c)


def test_overlay_y1_triggers_and_releases_at_half():
    c, dd = _dd_path()
    m = np.ones(len(c))
    s = BL.overlay_state(dd, m, c, 0.10, "Y1")
    t_on = int(np.argmax(s))
    assert dd[t_on] <= -0.10 and (dd[:t_on][np.isfinite(dd[:t_on])] > -0.10).all()
    t_off = t_on + int(np.argmin(s[t_on:]))
    assert dd[t_off] > -0.05 and (dd[t_on:t_off] <= -0.05).all()


def test_overlay_y3_needs_new_20d_high_and_dd_above_x():
    c, dd = _dd_path()
    m = np.ones(len(c))
    s = BL.overlay_state(dd, m, c, 0.10, "Y3")
    t_on = int(np.argmax(s))
    t_off = t_on + int(np.argmin(s[t_on:]))
    pm = BL.prior_max20(c)
    assert c[t_off] > pm[t_off] and dd[t_off] > -0.10
    assert not any(c[t] > pm[t] and dd[t] > -0.10 for t in range(t_on + 1, t_off))


def test_overlay_y2_waits_for_m_recovery_after_dip():
    c, dd = _dd_path()
    m = np.ones(len(c))
    s1 = BL.overlay_state(dd, m, c, 0.10, "Y1")
    t_on = int(np.argmax(s1))
    m2 = m.copy()
    m2[t_on + 1:t_on + 30] = 0.5          # 발동 뒤 m 이 꺾였다가 t_on+30 에 회복
    s2 = BL.overlay_state(dd, m2, c, 0.10, "Y2")
    assert s2[t_on:t_on + 30].all()
    t_off = t_on + int(np.argmin(s2[t_on:]))
    assert t_off >= t_on + 30 and m2[t_off] == 1.0 and dd[t_off] > -0.10
    # m 이 한 번도 안 꺾이면 Y1 과 같다
    assert (BL.overlay_state(dd, m, c, 0.10, "Y2") == s1).all()


def test_weights_path_no_lookahead():
    n = 200
    cal = _cal(n)
    _, cl = _prices(n)
    c = cl[:, 0]
    m = np.r_[np.full(80, np.nan), np.where(np.arange(n - 80) % 17 < 8, 1.0, 0.5)]
    dd = BL.drawdown60(c)
    for cb in BL.grid():
        W = BL.weights_path(cb, cal, m, dd, c)
        m2, c2 = m.copy(), c.copy()
        m2[150:] = 0.0
        c2[150:] *= 0.5
        W2 = BL.weights_path(cb, cal, m2, BL.drawdown60(c2), c2)
        assert np.allclose(W[:151], W2[:151]), BL.name(cb)
        assert np.allclose(W.sum(axis=1)[W.sum(axis=1) > 0], 1.0) or cb.get("park") == "cash"


def test_sample_mask_week_month():
    cal = _cal(60)
    w = BL.sample_mask(cal, "W")
    assert w[0] and all(cal[i].weekday() == 0 for i in np.where(w)[0][1:])
    mm = BL.sample_mask(cal, "M")
    assert all(cal[i].month != cal[i - 1].month for i in np.where(mm)[0][1:])


def test_run_account_b0_one_buy_and_cost():
    n = 50
    o, c = _prices(n)
    W = np.zeros((n, len(BL.ASSETS)))
    W[:, BL.AI[BL.K200]] = 1.0
    r = BL.run_account(W, o, c, 0, n - 1, budget=1_000_000, cost_rt=0.0038)
    q = int(1_000_000 // (o[0, 0] * 1.0019))
    cash = 1_000_000 - q * o[0, 0] * 1.0019
    assert r["equity"][-1] == pytest.approx(cash + q * c[-1, 0])
    assert r["orders_per_year"] == pytest.approx(1 / (n / 252))


def test_run_account_trades_only_changed_assets_and_cash_nonnegative():
    n = 120
    o, c = _prices(n, seed=3)
    W = np.zeros((n, len(BL.ASSETS)))
    W[:, BL.AI[BL.K200]] = np.where(np.arange(n) % 20 < 10, 1.0, 0.5)
    W[:, BL.AI[BL.SHORT]] = 1 - W[:, BL.AI[BL.K200]]
    r = BL.run_account(W, o, c, 0, n - 1, budget=5_000_000)
    switches = int((np.abs(np.diff(W[:, 0])) > 0).sum())
    assert r["orders_per_year"] * n / 252 == pytest.approx(1 + 2 * switches)
    assert r["avg_cash_share"] >= 0


def test_boot_identical_is_zero_and_antisymmetric():
    rng = np.random.default_rng(0)
    a, b = rng.normal(0.0005, 0.01, 300), rng.normal(0.0003, 0.012, 300)
    assert np.allclose(np.nan_to_num(BL.mar_diff_boot(a, a, 200)), 0)
    d1 = BL.mar_diff_boot(a, b, 200)
    d2 = BL.mar_diff_boot(b, a, 200)
    assert np.allclose(d1, -d2, equal_nan=True)


def test_dd_events_rearm_at_half():
    dd = np.array([np.nan, -0.02, -0.11, -0.12, -0.06, -0.11, -0.04, -0.105, -0.2])
    assert BL.dd_events(dd, 0.10) == [2, 7]
