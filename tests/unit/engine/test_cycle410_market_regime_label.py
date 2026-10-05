"""cycle410 — 6장세 라벨 leaf (`src/engine/market_regime_label.py`). 관찰 전용 — 매매 무접촉.

정의 정본 = `_workspace/domain_consult/2026-10-05_six_regime_strategy_map.md` §1.1~§1.4(권고 D4 × V4).

| # | 계약 |
|---|---|
| L1 | 방향 히스테리시스 — 횡보에서 기울기 > +3% 상승 · < −3% 하락. 상승은 +1% 밑에서, 하락은 −1% 위에서 풀린다(풀리는 날 반대 문턱을 넘으면 곧장 반대편) |
| L2 | 변동 히스테리시스 — > 20% 변동 · < 16% 안정 · 사이는 직전 유지 |
| L3 | 특징 = SMA60(t) / SMA60(t−20) − 1 · 20일 로그수익률 표본표준편차 × √252. 첫 값은 80번째 종가에서 |
| L4 | 상태는 첫 특징에서 (횡보, 안정)으로 시작해 이력을 처음부터 걸어 이어 간다 |
| L5 | D 일 라벨 = D-1 종가까지 — `session_labels` 의 D 일 값은 D 일 종가를 보지 않는다 |
| L6 | 결측·0 이하·비유한 종가 = ValueError(조용히 건너뛰면 창이 어긋난다) |
| G1 | 골든 — 메모 §1.4 실측(1,390일 · 덩어리 35 · 연도별 일수)을 ETF 보관소 069500 `close_adj` 로 재현(보관소 없으면 skip) |

⚠️ G1 은 **보관소 기준**이다. 운영 API(`/api/market-regime-label`)는 운영 DB `stock_master_daily` 의 069500 종가를
읽는데, 두 출처는 2025-10 이후 197일 동안 약 1% 다르다(종합 보고서 작업 실측). 그래서 화면 값(기울기·변동성,
경계 근처의 라벨)은 이 골든과 다를 수 있다 — 골든은 판정 식의 재현이지 운영 값의 재현이 아니다.
"""

from __future__ import annotations

import math
import os
import statistics
from datetime import date, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from src.engine import market_regime_label as mrl  # noqa: E402


# ── L1 · L2 — 상태 전이 ─────────────────────────────────────────────────────
@pytest.mark.parametrize("prev, slope, want", [
    ("flat", 0.031, "up"),
    ("flat", 0.03, "flat"),          # 문턱 동률은 안 넘는다
    ("flat", -0.031, "down"),
    ("flat", -0.03, "flat"),
    ("up", 0.02, "up"),              # +1% 위면 상승 유지(해제 문턱이 진입 문턱과 다르다)
    ("up", 0.01, "up"),
    ("up", 0.0099, "flat"),
    ("up", -0.031, "down"),          # 풀리는 날 반대 문턱을 넘으면 곧장 하락
    ("down", -0.02, "down"),
    ("down", -0.01, "down"),
    ("down", -0.0099, "flat"),
    ("down", 0.031, "up"),
])
def test_l1_direction_hysteresis(prev, slope, want):
    assert mrl.step_direction(prev, slope) == want


@pytest.mark.parametrize("prev, vol, want", [
    ("stable", 0.201, "volatile"),
    ("stable", 0.20, "stable"),
    ("stable", 0.18, "stable"),
    ("volatile", 0.18, "volatile"),  # 사이 구간은 직전 유지
    ("volatile", 0.16, "volatile"),
    ("volatile", 0.159, "stable"),
    ("stable", 0.10, "stable"),
])
def test_l2_volatility_hysteresis(prev, vol, want):
    assert mrl.step_volatility(prev, vol) == want


def test_thresholds_are_module_constants():
    assert (mrl.MA_WINDOW, mrl.SLOPE_LOOKBACK, mrl.VOL_WINDOW) == (60, 20, 20)
    assert (mrl.DIR_ENTER, mrl.DIR_EXIT) == (0.03, 0.01)
    assert (mrl.VOL_HIGH, mrl.VOL_LOW) == (0.20, 0.16)
    assert mrl.SOURCE_TICKER == "069500"
    assert set(mrl.LABELS) == {
        "stable_up", "volatile_up", "stable_flat",
        "volatile_flat", "stable_down", "volatile_down",
    }


# ── L3 · L4 — 특징과 시작 상태 ──────────────────────────────────────────────
def _wavy(n: int, *, drift: float = 0.0015, amp: float = 0.012, seed: int = 7) -> list[float]:
    """결정론적 합성 종가 — 추세 + 사인 흔들림."""
    out, p = [], 10_000.0
    for i in range(n):
        r = drift + amp * math.sin(i * 0.9 + seed) + 0.5 * amp * math.sin(i * 2.3)
        p *= math.exp(r)
        out.append(round(p, 2))
    return out


def _ref_features(closes: list[float], i: int) -> tuple[float, float]:
    sma = sum(closes[i - 59:i + 1]) / 60
    sma_prev = sum(closes[i - 79:i - 19]) / 60
    lr = [math.log(closes[k] / closes[k - 1]) for k in range(i - 19, i + 1)]
    return sma / sma_prev - 1, statistics.stdev(lr) * math.sqrt(252)


def test_l3_features_and_warmup():
    closes = _wavy(150)
    pts = mrl.label_after_closes(closes)
    assert len(pts) == 150
    assert all(p is None for p in pts[:79])
    assert all(p is not None for p in pts[79:])
    for i in (79, 100, 149):
        slope, vol = _ref_features(closes, i)
        assert pts[i].slope_pct == pytest.approx(slope * 100, rel=1e-9)
        assert pts[i].vol_pct == pytest.approx(vol * 100, rel=1e-9)
        assert pts[i].label == f"{pts[i].volatility}_{pts[i].direction}"


def test_l4_state_walks_from_flat_stable_and_carries():
    closes = _wavy(260)
    pts = mrl.label_after_closes(closes)
    d, v = "flat", "stable"
    for i in range(79, 260):
        slope, vol = _ref_features(closes, i)
        d, v = mrl.step_direction(d, slope), mrl.step_volatility(v, vol)
        assert (pts[i].direction, pts[i].volatility) == (d, v), i


def test_l4_mild_first_slope_starts_flat_not_up():
    # 첫 특징 기울기가 +1%~+3% 이면 시작 상태 횡보 그대로(상승으로 시작하지 않는다)
    closes = [10_000.0 * (1.0003 ** i) for i in range(80)]
    p = mrl.label_after_closes(closes)[79]
    assert 0.0 < p.slope_pct < 3.0
    assert p.direction == "flat"
    assert p.volatility == "stable"


# ── L5 — D 일 라벨은 D-1 종가까지 ──────────────────────────────────────────
def test_l5_session_label_uses_previous_close_only():
    closes = _wavy(200)
    dates = [date(2026, 1, 1) + timedelta(days=k) for k in range(200)]
    sess = mrl.session_labels(dates, closes)
    # 첫 라벨 세션 = 81번째 날(80번째 종가 다음 날)
    assert sess[0][0] == dates[80]
    assert len(sess) == 200 - 80
    for d, p in sess[::17] + sess[-1:]:
        k = dates.index(d)
        assert p == mrl.label_after_closes(closes[:k])[-1], d
    # D 일 종가를 크게 바꿔도 D 일 라벨은 그대로
    k = 150
    bumped = list(closes)
    bumped[k] *= 1.8
    sess2 = dict(mrl.session_labels(dates, bumped))
    assert sess2[dates[k]] == dict(sess)[dates[k]]
    assert sess2[dates[k + 1]] != dict(sess)[dates[k + 1]]


def test_l5_session_labels_rejects_length_mismatch():
    with pytest.raises(ValueError):
        mrl.session_labels([date(2026, 1, 1)], [1.0, 2.0])


# ── L6 — 나쁜 종가 ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [None, 0, -5.0, float("nan"), float("inf"), "x"])
def test_l6_bad_close_raises(bad):
    closes = _wavy(100)
    closes[40] = bad
    with pytest.raises(ValueError):
        mrl.label_after_closes(closes)


# ── G1 — 메모 §1.4 골든 ──────────────────────────────────────────────────────
_ARCHIVE = Path(os.environ.get(
    "AUTO_STOCK_ETF_ARCHIVE_DIR",
    Path(__file__).resolve().parents[3] / "data/archive/krx_etf_daily/parquet",
))

#: 메모는 보관소(~2026-09-23) 뒤를 전수 점검 DB 추출본의 069500 종가 5일로 이었다
#: (스크래치 `regime/k200_db.csv` — 2026-09-24~26 은 추석 휴장).
_DB_TAIL = [
    (date(2026, 9, 28), 109500.0), (date(2026, 9, 29), 109990.0),
    (date(2026, 9, 30), 109545.0), (date(2026, 10, 1), 111520.0),
    (date(2026, 10, 2), 112060.0),
]

#: 메모 §1.4 연도별 일수 — 순서 = 안정상승·변동상승·안정횡보·변동횡보·안정하락·변동하락.
_GOLDEN_YEARS = {
    2021: (19, 39, 122, 0, 49, 0),
    2022: (0, 0, 80, 62, 27, 77),
    2023: (43, 0, 158, 44, 0, 0),
    2024: (0, 0, 118, 69, 29, 28),
    2025: (75, 56, 38, 48, 11, 14),
    2026: (0, 147, 0, 9, 0, 28),
}
_ORDER = ("stable_up", "volatile_up", "stable_flat", "volatile_flat", "stable_down", "volatile_down")


def _archive_series() -> tuple[list[date], list[float]]:
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    files = sorted(_ARCHIVE.glob("krx_daily_*.parquet"))
    if not files:
        pytest.skip(f"ETF 보관소 없음: {_ARCHIVE}")
    frames = [pd.read_parquet(f, columns=["ticker", "bas_dd", "close_adj"]) for f in files]
    k = pd.concat(frames)
    k = k[k.ticker == mrl.SOURCE_TICKER].sort_values("bas_dd")
    dates = [pd.Timestamp(x).date() for x in k.bas_dd]
    closes = [float(x) for x in k.close_adj]
    last = dates[-1]
    for d, c in _DB_TAIL:
        if d > last:
            dates.append(d)
            closes.append(c)
    return dates, closes


def test_g1_golden_reproduces_memo_section_1_4():
    dates, closes = _archive_series()
    sess = mrl.session_labels(dates, closes)
    assert sess[0][0] == date(2021, 1, 29)
    assert sess[-1][0] == date(2026, 10, 2)
    assert len(sess) == 1390

    years: dict[int, list[int]] = {}
    for d, p in sess:
        years.setdefault(d.year, [0] * 6)[_ORDER.index(p.label)] += 1
    assert {y: tuple(v) for y, v in years.items()} == _GOLDEN_YEARS

    spells, prev = 0, None
    for _, p in sess:
        if p.label != prev:
            spells += 1
            prev = p.label
    assert spells == 35
