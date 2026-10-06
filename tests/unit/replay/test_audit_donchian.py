"""운용 전략 전수 점검(2026-10-05) §3.2 donchian_swing(깡토 개조) — 운영 해석 층 단위 테스트.

K1 대조에서 나온 차이(운영 코드를 따른다 — 동결본 §1.1 K1)를 재현 층이 옵션으로 갖는지 본다.
기본값은 cycle405 재현(관문 1 비트 일치)과 같아야 하고, 운영 해석은 옵션을 켰을 때만 바뀐다.
네트워크·DB·보관소 파일 0 — 합성 입력만 쓴다.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import indicators as IND  # noqa: E402
from replay.strategies import donchian_kk as DK  # noqa: E402
from replay.strategies import donchian_kk_audit as DA  # noqa: E402

pytestmark = pytest.mark.unit


def _flat(n=40):
    o = np.full(n, 100.0)
    h = np.full(n, 101.0)
    l = np.full(n, 99.0)
    c = np.full(n, 100.0)
    return {"di": np.arange(n), "o": o, "h": h, "l": l, "c": c, "notrade": np.zeros(n, bool)}


def _armed_series(touch_low: float):
    """3R 도달로 무장한 뒤 15번 봉 저가가 채널(직전 10봉 저가 119)에 ``touch_low`` 로 닿는다."""
    b = _flat()
    b["h"][2], b["c"][2] = 125.0, 120.0
    b["o"][3:], b["h"][3:], b["l"][3:], b["c"][3:] = 120.0, 121.0, 119.0, 120.0
    b["l"][15] = touch_low
    return b, {"chan10": IND.prior_min(b["l"], 10)}


SIG = DK.Sig("T", 0, 0, 100.0, 100.0, 2.0, 0.0, 1.0)      # R = max(8, 3) = 8


def test_default_channel_is_inclusive_like_cycle405():
    # 3번 봉부터 저가가 매일 119 — 직전 10봉 저가(채널)도 119 가 되는 13번 봉에서 c405 는 깬다(≤)
    b, f = _armed_series(119.0)
    ps = DK.run_path(SIG, b, f, 40)
    assert (ps.exit_reason, ps.exit_gd, ps.exit_px) == ("TRAILING_STOP", 13, 119.0)


def test_operating_channel_is_strict_below():
    # 운영 check_exit_signal: current_price < channel (엄격) — 같으면 안 판다
    b, f = _armed_series(119.0)
    kk = dict(DK.KK, chan_strict=True)
    ps = DK.run_path(SIG, b, f, 40, kk=kk)
    assert ps.exit_reason == "END"                          # 저가가 채널과 같기만 하면 끝까지 안 깬다
    b2, f2 = _armed_series(118.0)
    ps2 = DK.run_path(SIG, b2, f2, 40, kk=kk)
    assert ps2.exit_reason == "TRAILING_STOP" and ps2.exit_gd == 15 and ps2.exit_px == 119.0


def test_turnover_option_uses_close_times_volume():
    n = 70
    rng = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(rng.normal(0.004, 0.01, n)))
    b = {"o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "c_raw": c * 2.0, "vol": np.full(n, 1e6),
         "tv": np.full(n, 1e12), "notrade": np.zeros(n, bool)}
    b["vol"][-1] = 3e6                                       # 마지막 봉만 거래량 3배
    mem = np.ones(n, bool)
    f_tv = DK.features(b, mem)                               # tv 평평 → 배수 조건 실패
    f_cv = DK.features(b, mem, turnover="cv")                # 종가×거래량 → 배수 조건 통과 가능
    assert not f_tv["cond"][-1]
    # 운영: today_turnover = closes[0]*vols[0] ≥ 1.5 × 직전 20봉 (close×vol) 평균
    cv = b["c_raw"] * b["vol"]
    assert f_cv["turnover"][-1] == pytest.approx(cv[-1])
    assert f_cv["turnover_avg20"][-1] == pytest.approx(cv[-21:-1].mean())


def test_r_half_price_block_matches_operating_l6():
    # 운영 _kk_design_lot: R ≥ 0.5 × 가격이면 수량 0(사지 않는다). R = max(8% P, 1.5 N)
    assert DA.r_half_blocked(E=100.0, N=33.4)            # 1.5N = 50.1 ≥ 50
    assert not DA.r_half_blocked(E=100.0, N=33.2)        # 49.8 < 50
    assert not DA.r_half_blocked(E=100.0, N=float("nan"))


def test_db_member_from_master_row():
    assert DA.db_member({"is_kospi200": True, "scty_grp_id_cd": "ST"})
    assert DA.db_member({"is_kosdaq150": True, "scty_grp_id_cd": None, "scty_grp_id_cd_master": "ST"})
    assert not DA.db_member({"is_kospi200": True, "scty_grp_id_cd": "EF"})
    assert not DA.db_member({"is_kospi200": False, "is_kosdaq150": False, "scty_grp_id_cd": "ST"})
    assert not DA.db_member(None)


def test_provisional_flags_detects_close_rewritten_next_day():
    # t 일 종가 1000, t+1 의 전일 대비가 +10% 인데 종가 1111 → 역산 전일 종가 1010 ≠ 1000 → 잠정
    dates = np.array(["2026-09-24", "2026-09-25", "2026-09-30"], dtype="datetime64[D]")
    c = np.array([1000.0, 1111.0, 1200.0])
    chg = np.array([0.0, 10.0, 8.0])
    fl = DA.provisional_flags(dates, c, chg, cutoff="2026-09-28")
    assert fl.tolist() == [True, False, False]
    c_ok = np.array([1000.0, 1100.0, 1200.0])
    chg_ok = np.array([0.0, 10.0, round((1200 / 1100 - 1) * 100, 4)])
    assert DA.provisional_flags(dates, c_ok, chg_ok, cutoff="2026-09-28").tolist() == [False, False, False]
