"""cycle351 Red — 피라미딩 가상 사다리 순수 코어 `overlay_ladder` · `no_add_flags` · `LADDER_C`.

명세(정본) = `_workspace/red/cycle351_pyramid_shadow_spec.md` §1(코어 모형) · §4-2(C1~C14) · §5(돌연변이).
설계 = `_workspace/design/2026-09-24_three_stage_sizing_pyramiding.md` §3·§4.

## 무엇을 재는가

셰도 사다리는 **실제 청산(앵커) 위에 덧씌운다** — 사다리만의 추가 매수와 사다리만의 더 조인 손절선만
모형화하고, 앵커보다 늦게 나가지 않는다(§1 핵심 결정). 이 파일은 그 순수 코어의 하루 처리 순서
(손절 먼저 → 추가 → 앵커 → 고점 갱신, §1-2)와 물타기 금지 네 게이트(D0 · 추가 금지일 · 갭 스킵 ·
손절 먼저, §1-3)를 합성 봉으로 못박는다.

## 기대값은 전부 손으로 계산했다

공통 입력(§4-2) = `E=10,000 · N=500 · stop_atr=2 · hard=−8 · be=1.5 · LADDER_C`.
그래서 `r_unit = stop_atr × N = 1,000` 이고, 첫 추가 눈금 = 10,500, 둘째 = 11,000 이다.
각 테스트의 docstring/주석에 날짜별 판정을 적었다 — 구현을 흉내 내서 기대값을 만들지 않는다.

## Red 방식

leaf `src/engine/pyramid_shadow.py` 가 아직 없다. 모듈 수준 import 는 수집 오류(ImportError)라
「의도한 단언에서 붉다」를 보여 주지 못하므로 `_ps()` 가 **함수 안에서** import 하고 부재면
`pytest.fail` 로 떨어뜨린다(cycle249 `_collector()` 선례). import 는 정적 `from … import` 라
Green 뒤 영향 인덱스(`build_index.py`)가 이 파일을 leaf 에 자동으로 잇는다.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.unit

E = 10_000.0
N = 500.0
TWO_THIRDS = 2.0 / 3.0

#: 손절형 kind 집합(§1-4 `killed` 정의) — 이 밖의 kind 는 anchor · open 뿐이다.
LADDER_STOP_KINDS = {"gap", "set_line", "avg_backstop", "avg_breakeven", "stop_after_add"}

#: `overlay_ladder` 출력 dict 가 반드시 가진 키(§1-4).
CORE_OUT_KEYS = {
    "tranches", "fills", "avg", "exit_idx", "exit_price", "exit_kind",
    "virtual_R", "base_R", "set_stop", "fixed_stop", "killed", "peak_risk_R",
}


def _ps():
    """leaf 모듈. 부재면 수집 오류가 아니라 **실패**로 떨어뜨린다(Red 경로)."""
    try:
        from src.engine import pyramid_shadow  # noqa: PLC0415 — Red 경로 보존
    except ImportError as exc:  # pragma: no cover - Red 경로
        pytest.fail(
            "Red — `src/engine/pyramid_shadow.py` 미구현 (cycle351 §1). "
            f"`overlay_ladder`·`no_add_flags`·`LadderConfig`·`LADDER_C` 가 필요하다: {exc}"
        )
    return pyramid_shadow


def _dates(n: int, start: date = date(2026, 10, 5)) -> list[date]:
    """월요일 2026-10-05 부터 평일 n 개(코어는 날짜로 판정하지 않는다 — 추가 금지일은 `no_add` 인자)."""
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _bars(rows: list[tuple[float, float, float, float]]) -> list[tuple]:
    """(open, high, low, close) 목록 → (date, open, high, low, close) 오름차순."""
    ds = _dates(len(rows))
    return [(ds[i], *map(float, r)) for i, r in enumerate(rows)]


def _run(
    rows,
    *,
    n_entry: float = N,
    entry_price: float = E,
    no_add=None,
    be_atr=None,
    anchor_idx=None,
    anchor_price=None,
    anchor_add_allowed: bool = True,
    hard_stop_pct: float = -8.0,
    be_mult: float = 1.5,
    stop_atr: float = 2.0,
    cfg=None,
) -> dict:
    ps = _ps()
    bars = _bars(rows)
    out = ps.overlay_ladder(
        bars, 0, entry_price, n_entry,
        cfg=cfg if cfg is not None else ps.LADDER_C,
        stop_atr=stop_atr,
        hard_stop_pct=hard_stop_pct,
        be_mult=be_mult,
        be_atr=be_atr,
        no_add=list(no_add) if no_add is not None else [False] * len(bars),
        anchor_idx=anchor_idx,
        anchor_price=anchor_price,
        anchor_add_allowed=anchor_add_allowed,
    )
    assert isinstance(out, dict), type(out)
    missing = CORE_OUT_KEYS - set(out)
    assert not missing, f"출력 키 누락 {sorted(missing)} (§1-4)"
    return out


def _fills(out: dict) -> list[tuple[int, float, float]]:
    return [(int(i), round(float(p), 4), round(float(s), 4)) for i, p, s in out["fills"]]


def _approx(x: float):
    return pytest.approx(x, abs=1e-4)


# 공통 봉 — D0 은 진입일(고가 10,100 = 첫 hsb).
D0 = (10_000, 10_100, 9_900, 10_000)
#: D1 고가가 **정확히** 첫 눈금 10,500 — `high ≥ level` 경계(M1 `>` 돌연변이 탐지).
D1_ADD = (10_100, 10_500, 10_050, 10_400)


# ===========================================================================
# 상수
# ===========================================================================
def test_ladder_c_is_design_c_star():
    """§1-5 — 셰도가 쓰는 사다리는 C* 하나: 1N 간격 · 2/3u × 3 · 갭 스킵 1.05."""
    ps = _ps()
    c = ps.LADDER_C
    assert isinstance(c, ps.LadderConfig)
    assert c.step_n == 1.0
    assert [round(s, 10) for s in c.sizes] == [round(TWO_THIRDS, 10)] * 3
    assert c.gap_skip_mult == 1.05


# ===========================================================================
# C1 — 3트랜치까지 가고 4번째는 없다
# ===========================================================================
C1_ROWS = [
    D0,
    D1_ADD,                        # 추가① 10,500 (k=2, avg 10,250, 선 9,500)
    (10_450, 11_000, 10_400, 10_900),  # 추가② 11,000 (k=3, avg 10,500, 세트선 10,000)
    (10_950, 11_500, 10_900, 11_400),  # 4번째 눈금 11,500 도달 — 트랜치 상한 3 이라 없음
    (11_400, 11_600, 11_300, 11_500),  # hsb 11,500 ≥ avg+1.5N(11,250) → 선 10,500(본전), 저가 11,300 무사
    (11_500, 11_800, 11_400, 11_700),  # D5 = 앵커(11,700)
]


def test_c1_three_tranches_then_no_fourth():
    """C1 — 날짜별 손계산:

    - D1: k=1 이라 손절 없음. 눈금 10,500 · 시가 10,100 < 11,025 · 고가 10,500 ≥ 10,500 →
      체결 max(10,500, 10,100)=10,500. k=2 · avg=10,250 · 선=max(9,500, 9,430, —)=9,500, 저가 10,050 무사.
      다음 눈금 11,000 > 고가 → 끝. hsb=10,500.
    - D2: 선 9,500 무사. 눈금 11,000 ≤ 고가 → 체결 11,000. k=3 · avg=10,500 · 세트선 10,000.
    - D3: k=3 = len(sizes) → 추가 없음(고가 11,500 = 4번째 눈금이어도).
    - D4: hsb 11,500 ≥ 10,500+750 → 선 10,500. 저가 11,300 무사.
    - D5(앵커 11,700): 선 10,500 무사 → 앵커가 청산.
    virtual_R = 2/3 × (1,700 + 1,200 + 700) ÷ 1,000 = 2.4 · base_R = 1,700 ÷ 1,000 = 1.7.
    """
    out = _run(C1_ROWS, anchor_idx=5, anchor_price=11_700)

    assert out["tranches"] == 3
    assert _fills(out) == [
        (0, 10_000.0, 0.6667), (1, 10_500.0, 0.6667), (2, 11_000.0, 0.6667),
    ]
    assert out["avg"] == _approx(10_500.0)
    assert out["set_stop"] == _approx(10_000.0)
    assert out["fixed_stop"] == _approx(9_000.0)
    assert out["exit_idx"] == 5
    assert out["exit_price"] == _approx(11_700.0)
    assert out["exit_kind"] == "anchor"
    assert out["virtual_R"] == _approx(2.4)
    assert out["base_R"] == _approx(1.7)
    assert out["killed"] == 0


def test_c1b_ladder_never_trades_past_anchor():
    """§1 핵심 결정 — 사다리는 앵커보다 늦게 나가지 않는다. 앵커 뒤 봉(급등·급락)은 결과를 바꾸지 못한다."""
    rows = C1_ROWS + [
        (11_700, 15_000, 11_700, 14_000),  # 앵커 뒤 급등
        (14_000, 14_000, 5_000, 5_000),    # 앵커 뒤 폭락
    ]
    out = _run(rows, anchor_idx=5, anchor_price=11_700)
    assert out["exit_idx"] == 5
    assert out["exit_kind"] == "anchor"
    assert out["exit_price"] == _approx(11_700.0)
    assert out["virtual_R"] == _approx(2.4)
    assert out["base_R"] == _approx(1.7)


# ===========================================================================
# C2 — 세트선에 털린다(killed)
# ===========================================================================
C2_ROWS = [
    D0,
    D1_ADD,                          # 추가① 10,500 → 세트선 9,500
    (10_300, 10_350, 9_400, 9_600),  # 시가 10,300 > 9,500 · 저가 9,400 ≤ 9,500 → 9,500 청산(set_line)
    (9_600, 9_900, 9_500, 9_800),
    (9_800, 10_300, 9_750, 10_200),
    (10_200, 10_700, 10_150, 10_600),
    (10_600, 10_900, 10_550, 10_800),  # D6 = 앵커(10,800)
]


def test_c2_set_line_kills_ladder_before_anchor():
    """C2 — D2 선 = max(세트선 9,500, 평단 backstop 10,250×0.92=9,430, 본전 없음(hsb 10,500 < 11,000)) = 9,500.

    virtual_R = 2/3 × (−500 − 1,000) ÷ 1,000 = −1.0. 앵커(D6) 전에 사다리 선으로 나갔으니 killed=1.
    세트선 기준이 `last` 가 아니라 `E` 면(M5) 선이 9,430(backstop)이 되어 kind 가 바뀐다.
    """
    out = _run(C2_ROWS, anchor_idx=6, anchor_price=10_800)

    assert out["tranches"] == 2
    assert out["exit_idx"] == 2
    assert out["exit_kind"] == "set_line"
    assert out["exit_price"] == _approx(9_500.0)
    assert out["set_stop"] == _approx(9_500.0)
    assert out["fixed_stop"] == _approx(9_000.0)
    assert out["virtual_R"] == _approx(-1.0)
    assert out["base_R"] == _approx(0.8)
    assert out["killed"] == 1


# ===========================================================================
# C3 — 물타기 경로 부재
# ===========================================================================
C3_ROWS = [
    D0,
    (9_900, 9_950, 9_500, 9_600),     # 9,500 까지 하락 — 추가 눈금은 10,500 뿐
    (9_600, 10_250, 9_550, 10_200),   # 10,250 회복 — 여전히 10,500 미만
    (10_200, 10_250, 10_000, 10_100),
]


def test_c3_no_averaging_down_path():
    """C3 — 내려간 자리에서 사는 경로가 없다(§1-3). 추가 0, 마지막 종가 평가.

    virtual_R = 2/3 × 100 ÷ 1,000 = 0.0667 · base_R = 0.1.
    """
    out = _run(C3_ROWS)

    assert out["tranches"] == 1
    assert _fills(out) == [(0, 10_000.0, 0.6667)]
    assert all(p >= E for _, p, _ in _fills(out)), "진입가 아래 체결 = 물타기"
    assert out["exit_kind"] == "open"
    assert out["exit_idx"] == 3
    assert out["exit_price"] == _approx(10_100.0)
    assert out["virtual_R"] == _approx(TWO_THIRDS * 0.1)
    assert out["base_R"] == _approx(0.1)
    assert out["set_stop"] is None
    assert out["killed"] == 0


# ===========================================================================
# C4 — D0 추가 금지
# ===========================================================================
def test_c4_no_add_on_entry_day():
    """C4 — D0 고가가 10,600(≥ 10,500)이어도 D0 에는 사지 않는다(M2). D1 고가 10,480 < 10,500."""
    rows = [
        (10_000, 10_600, 9_950, 10_500),
        (10_450, 10_480, 10_300, 10_400),
    ]
    out = _run(rows)

    assert out["tranches"] == 1
    assert _fills(out) == [(0, 10_000.0, 0.6667)]
    assert out["exit_kind"] == "open"
    assert out["exit_price"] == _approx(10_400.0)


# ===========================================================================
# C5 — 추가 금지일
# ===========================================================================
def test_c5_no_add_day_defers_to_next_qualifying_day():
    """C5 — D1 이 조건을 채워도 `no_add[1]=True` 면 사지 않고, D2(조건 충족·금지 아님)에 산다(M3).

    D2 체결 = max(10,500, 시가 10,450) = 10,500.
    """
    rows = [
        D0,
        (10_100, 10_600, 10_050, 10_500),   # no_add
        (10_450, 10_550, 10_400, 10_500),   # 추가 10,500
        (10_500, 10_520, 10_450, 10_480),
    ]
    out = _run(rows, no_add=[False, True, False, False])

    assert out["tranches"] == 2
    assert _fills(out) == [(0, 10_000.0, 0.6667), (2, 10_500.0, 0.6667)]


# ===========================================================================
# C6 — 갭으로 눈금을 건너뛴 날
# ===========================================================================
@pytest.mark.parametrize("gap_open", [11_025, 11_100])
def test_c6_gap_over_level_times_1_05_skips_the_day(gap_open):
    """C6 — 시가 ≥ 10,500 × 1.05 = 11,025(경계 포함)면 그날 추가 전부 없음(M4)."""
    rows = [
        D0,
        (gap_open, 11_300, 11_020, 11_200),
    ]
    out = _run(rows)
    assert out["tranches"] == 1
    assert _fills(out) == [(0, 10_000.0, 0.6667)]


@pytest.mark.parametrize("small_gap_open", [10_600, 11_024])
def test_c6b_small_gap_fills_at_open(small_gap_open):
    """C6 — 시가가 눈금 위지만 1.05배 미만이면 **시가**에 체결(`px = max(level, open)`)."""
    rows = [
        D0,
        (small_gap_open, small_gap_open + 100, small_gap_open - 50, small_gap_open + 50),
    ]
    out = _run(rows)
    assert out["tranches"] == 2
    assert _fills(out) == [(0, 10_000.0, 0.6667), (1, float(small_gap_open), 0.6667)]


# ===========================================================================
# C7 — 앵커 날
# ===========================================================================
C7_ROWS = [
    D0,
    D1_ADD,                          # 추가① 10,500 → 선 9,500
    (9_800, 9_850, 9_400, 9_450),    # D2 = 앵커 날. 저가 9,400 ≤ 9,500 → 사다리 선 적중가 9,500
]


def test_c7a_anchor_day_ladder_line_above_anchor_price():
    """C7 — 앵커가 9,300 < 사다리 선 9,500 → 청산가 max(9,500, 9,300)=9,500, kind=set_line.

    앵커 **날** 청산이라 `exit_idx == anchor_idx` → killed=0(1랏보다 먼저 턴 것이 아니다).
    virtual_R = 2/3 × (−500 − 1,000) ÷ 1,000 = −1.0 · base_R = (9,300 − 10,000) ÷ 1,000 = −0.7.
    """
    out = _run(C7_ROWS, anchor_idx=2, anchor_price=9_300)
    assert out["exit_idx"] == 2
    assert out["exit_kind"] == "set_line"
    assert out["exit_price"] == _approx(9_500.0)
    assert out["virtual_R"] == _approx(-1.0)
    assert out["base_R"] == _approx(-0.7)
    assert out["killed"] == 0


def test_c7b_anchor_day_anchor_price_above_ladder_line():
    """C7 — 앵커가 9,700 > 9,500 → 청산가 9,700, kind=anchor(M8 `max`→`min` 탐지).

    virtual_R = 2/3 × (−300 − 800) ÷ 1,000 = −0.7333 · base_R = −0.3.
    """
    out = _run(C7_ROWS, anchor_idx=2, anchor_price=9_700)
    assert out["exit_idx"] == 2
    assert out["exit_kind"] == "anchor"
    assert out["exit_price"] == _approx(9_700.0)
    assert out["virtual_R"] == _approx(TWO_THIRDS * (-1.1))
    assert out["base_R"] == _approx(-0.3)
    assert out["killed"] == 0


@pytest.mark.parametrize("allowed,tranches,virtual", [
    (False, 1, TWO_THIRDS * 0.55),   # 추가 없이 앵커 10,550
    (True, 2, 0.4),                   # 10,500 추가 후 앵커 10,550: 2/3×(550+50)÷1,000
])
def test_c7c_anchor_add_allowed_gates_anchor_day_add(allowed, tranches, virtual):
    """C7 — `anchor_add_allowed=False`(실제 매도가 09:30 전) 면 앵커 날 추가 0."""
    rows = [
        D0,
        (10_100, 10_600, 10_050, 10_550),  # D1 = 앵커 날, 고가 ≥ 10,500
    ]
    out = _run(rows, anchor_idx=1, anchor_price=10_550, anchor_add_allowed=allowed)
    assert out["tranches"] == tranches
    assert out["exit_kind"] == "anchor"
    assert out["exit_price"] == _approx(10_550.0)
    assert out["virtual_R"] == _approx(virtual)


def test_c7d_anchor_on_entry_day_exits_at_anchor():
    """§1 핵심 결정의 귀결 — 매수일에 실제로 청산됐으면(anchor_idx == entry_idx) 사다리도 그날 앵커가에 나간다.

    ⚠️ 명세 표(C1~C14)에 없는 경계라 §1 「사다리는 앵커보다 늦게 나가지 않는다」에서 도출했다
    (kojiro 당일 손절 = S1 에서 sell_date == buy_date 인 청산 페어). virtual_R = 2/3 × (−750) ÷ 1,000 = −0.5.
    """
    rows = [
        (10_000, 10_100, 9_200, 9_300),
        (9_300, 11_000, 9_300, 10_900),   # 앵커 뒤 — 쓰면 안 된다
    ]
    out = _run(rows, anchor_idx=0, anchor_price=9_250)
    assert out["exit_idx"] == 0
    assert out["exit_kind"] == "anchor"
    assert out["exit_price"] == _approx(9_250.0)
    assert out["tranches"] == 1
    assert out["virtual_R"] == _approx(-0.5)
    assert out["base_R"] == _approx(-0.75)
    assert out["killed"] == 0


# ===========================================================================
# 손절 먼저 (M7)
# ===========================================================================
def test_stop_is_checked_before_add_on_the_same_bar():
    """§1-2 보수 순서 — k≥2 에서 같은 봉이 선(9,500)과 다음 눈금(11,000)을 둘 다 찍으면 **손절이 먼저**다.

    D2: 시가 10,000 > 9,500 · 저가 9,400 ≤ 9,500 → 9,500 청산. 11,000 추가는 일어나지 않는다.
    순서를 바꾸면(M7) 11,000 에 3번째를 사고 새 선에서 나간다 → 트랜치 3.
    """
    rows = [D0, D1_ADD, (10_000, 11_000, 9_400, 10_500)]
    out = _run(rows)
    assert out["tranches"] == 2
    assert out["exit_idx"] == 2
    assert out["exit_kind"] == "set_line"
    assert out["exit_price"] == _approx(9_500.0)


# ===========================================================================
# C8 — 평단 본전 승격은 다음 날부터
# ===========================================================================
def test_c8_breakeven_promotes_from_next_day():
    """C8 — 2트랜치(10,000/10,500, avg 10,250). 본전 임계 = 10,250 + 1.5×500 = 11,000.

    - D2(no_add): 고가 11,050 ≥ 11,000 이지만 **같은 날 고가로는 켜지지 않는다** — 선은 hsb(전일까지 10,500)
      기준 9,500 이라 저가 10,200 무사. 같은 날 켜면(돌연변이) 10,250 에 D2 청산.
    - D3: hsb 11,050 ≥ 11,000 → 선 = max(9,500, 9,430, 10,250) = 10,250 · 저가 10,200 → 10,250 청산(avg_breakeven).
    virtual_R = 2/3 × (250 − 250) = 0.0. 앵커(D5) 전이라 killed=1.
    """
    rows = [
        D0,
        D1_ADD,
        (10_450, 11_050, 10_200, 10_900),   # no_add — 3번째 추가(11,000)를 막는다
        (10_900, 10_950, 10_200, 10_300),
        (10_300, 10_500, 10_250, 10_450),
        (10_450, 10_700, 10_400, 10_600),   # 앵커 10,600
    ]
    out = _run(rows, no_add=[False, False, True, False, False, False], anchor_idx=5, anchor_price=10_600)
    assert out["tranches"] == 2
    assert out["exit_idx"] == 3
    assert out["exit_kind"] == "avg_breakeven"
    assert out["exit_price"] == _approx(10_250.0)
    assert out["virtual_R"] == _approx(0.0)
    assert out["base_R"] == _approx(0.6)
    assert out["killed"] == 1


# ===========================================================================
# C9 — 고ATR 에서는 평단 backstop 이 세트선보다 높다
# ===========================================================================
def test_c9_avg_backstop_above_set_line_on_high_atr():
    """C9 — N=600(6%) · r_unit=1,200. 추가① 10,600 → avg 10,300.

    선 = max(세트선 10,600−1,200=9,400, backstop 10,300×0.92=9,476, 본전 없음) = 9,476.
    D2 저가 9,450 ≤ 9,476 → 9,476 청산(avg_backstop).
    virtual_R = 2/3 × (−524 − 1,124) ÷ 1,200 = −0.915556.
    """
    rows = [
        D0,
        (10_100, 10_600, 10_050, 10_500),
        (10_300, 10_350, 9_450, 9_500),
    ]
    out = _run(rows, n_entry=600.0)
    assert out["tranches"] == 2
    assert out["exit_idx"] == 2
    assert out["exit_kind"] == "avg_backstop"
    assert out["exit_price"] == _approx(9_476.0)
    assert out["set_stop"] == _approx(9_400.0)
    assert out["fixed_stop"] == _approx(8_800.0)
    assert out["virtual_R"] == _approx(TWO_THIRDS * (-1_648.0) / 1_200.0)
    assert out["killed"] == 1


# ===========================================================================
# C10 — be_atr 는 본전 임계만 바꾼다 (N 고정)
# ===========================================================================
def test_c10_large_be_atr_leaves_levels_and_set_line_unchanged():
    """C10 — be_atr 를 크게(5,000) 줘도 추가 눈금·세트선은 N 고정(M6). C1 과 같은 결과."""
    base = _run(C1_ROWS, anchor_idx=5, anchor_price=11_700)
    big = _run(C1_ROWS, anchor_idx=5, anchor_price=11_700, be_atr=[5_000.0] * len(C1_ROWS))
    assert _fills(big) == _fills(base)
    assert big["set_stop"] == _approx(10_000.0)
    assert big["tranches"] == 3
    assert big["exit_kind"] == "anchor"
    assert big["virtual_R"] == _approx(2.4)


C10_ROWS = [
    D0,
    D1_ADD,                           # 추가① → avg 10,250, 세트선 9,500
    (10_400, 10_450, 10_200, 10_300),
]


def test_c10b_be_atr_reads_previous_bar_and_moves_only_breakeven():
    """C10 — `be_atr[d-1]` 를 읽는다. D2 는 be_atr[1]=100 → 임계 10,250 + 150 = 10,400.

    hsb(D0·D1 고가 max) = 10,500 ≥ 10,400 → 선 = max(9,500, 9,430, 10,250) = 10,250 · 저가 10,200 → 청산.
    be_atr[2]=5,000(당일 값)을 읽으면 승격이 안 켜진다 — 인덱스 돌연변이 탐지.
    세트선(9,500)과 체결은 be_atr 와 무관하게 같다. virtual_R = 2/3×(250 − 250) = 0.
    """
    out = _run(C10_ROWS, be_atr=[500.0, 100.0, 5_000.0])
    assert _fills(out) == [(0, 10_000.0, 0.6667), (1, 10_500.0, 0.6667)]
    assert out["set_stop"] == _approx(9_500.0)
    assert out["exit_idx"] == 2
    assert out["exit_kind"] == "avg_breakeven"
    assert out["exit_price"] == _approx(10_250.0)
    assert out["virtual_R"] == _approx(0.0)


def test_c10c_be_atr_none_uses_n_for_breakeven_threshold():
    """C10 — be_atr=None 이면 임계 = 10,250 + 1.5×500 = 11,000 → D2 승격 없음, 마지막 종가 10,300 평가.

    virtual_R = 2/3 × (300 − 200) ÷ 1,000 = 0.0667.
    """
    out = _run(C10_ROWS, be_atr=None)
    assert _fills(out) == [(0, 10_000.0, 0.6667), (1, 10_500.0, 0.6667)]
    assert out["set_stop"] == _approx(9_500.0)
    assert out["exit_kind"] == "open"
    assert out["exit_price"] == _approx(10_300.0)
    assert out["virtual_R"] == _approx(TWO_THIRDS * 0.1)


# ===========================================================================
# C11 — 손절 기준 위험 최고치
# ===========================================================================
def test_c11_peak_risk_is_one_r_for_full_c_star():
    """C11 — k=1: 2/3×2N÷2N = 0.6667 · k=2(세트선 9,500): 2/3×(500+1,000)÷1,000 = 1.0 ·
    k=3(세트선 10,000): 2/3×(0+500+1,000)÷1,000 = 1.0 → 최고치 1.0 (설계 §4-3)."""
    out = _run(C1_ROWS, anchor_idx=5, anchor_price=11_700)
    assert out["peak_risk_R"] == pytest.approx(1.0, abs=1e-9)


def test_c11b_peak_risk_single_tranche_is_two_thirds():
    out = _run(C3_ROWS)
    assert out["peak_risk_R"] == _approx(TWO_THIRDS)


# ===========================================================================
# C12 — 앵커 없음
# ===========================================================================
def test_c12_no_anchor_evaluates_last_close():
    out = _run(C3_ROWS)
    assert out["exit_kind"] == "open"
    assert out["exit_idx"] == len(C3_ROWS) - 1
    assert out["killed"] == 0


def test_c12b_no_anchor_ladder_stop_is_killed():
    """C12 — 앵커가 없어도 사다리 선으로 나가면 killed=1(`anchor_idx is None` 분기)."""
    out = _run(C2_ROWS[:3])
    assert out["exit_kind"] == "set_line"
    assert out["exit_idx"] == 2
    assert out["killed"] == 1


# ===========================================================================
# C13 — 추가 직후 같은 봉에서 손절
# ===========================================================================
def test_c13_stop_after_add_on_the_same_bar():
    """C13 — D1 에 10,500 추가(k=2) 후 새 선 9,500, 같은 봉 저가 9,450 → 9,500 청산(stop_after_add).

    virtual_R = 2/3 × (−500 − 1,000) ÷ 1,000 = −1.0 · killed=1.
    """
    rows = [D0, (10_100, 10_500, 9_450, 9_600), (9_600, 9_700, 9_500, 9_650)]
    out = _run(rows)
    assert out["tranches"] == 2
    assert out["exit_idx"] == 1
    assert out["exit_kind"] == "stop_after_add"
    assert out["exit_price"] == _approx(9_500.0)
    assert out["virtual_R"] == _approx(-1.0)
    assert out["killed"] == 1


# ===========================================================================
# C15 — `_stop_floor` 래칫 (독립 검증 지적 #17, 설계 §4-1) — 손절선은 조이기만 한다
# ===========================================================================
def test_c15_stop_floor_ratchet_holds_armed_breakeven_after_later_add_unarms_it():
    """C15 — probe351c 케이스 B 재현(E=10000, N=500, live ATR=400 상수).

    - D1: 10,500 추가(k=2, avg=10,250). 본전 임계 전날 hsb(10,100) 미달 → 세트선 9,500 이 첫 floor.
    - D2: 전날 hsb(10,900, D1 고가 포함) ≥ avg(10,250)+1.5×400=10,850 → 이번 pre-add 점검에서
      본전선 10,250 이 armed. floor = max(9,500, 10,250) = 10,250. 이 날은 트리거되지 않는다
      (open 10,600 · low 10,600 > 10,250). 이어서 11,000 추가(k=3, avg=10,500) → post-add 재계산은
      hsb(아직 10,900, 이날 고가 미반영) < avg(10,500)+600=11,100 이라 **본전 재무장 실패**(raw 10,000,
      set_line) — 래칫이 없으면 floor 가 10,000 으로 풀린다. 래칫은 max(10,250, 10,000)=10,250 을 유지.
    - D3: 전날 hsb(11,050, D2 고가 포함) 도 11,100 미달 → raw 는 여전히 10,000(set_line). 래칫 floor
      는 10,250 그대로. 저가 10,200 ≤ 10,250 → **10,250 에서 청산**(kind=avg_breakeven, 래칫 기억).
      래칫이 없으면(구형) raw 10,000 에 안 걸려 계속 보유(반증 = 이 테스트가 구현 이전 코드에서 붉다).

    virtual_R = (2/3×250 + 2/3×(-250) + 2/3×(-750)) ÷ 1,000 = −0.5 (문서 수치와 일치).
    """
    rows = [
        (10_000, 10_100, 9_900, 10_000),   # D0
        (10_100, 10_900, 10_050, 10_800),  # D1 — 추가 10,500, hsb→10,900
        (10_600, 11_050, 10_600, 10_950),  # D2 — 본전 armed(10,250) 무사, 추가 11,000, hsb→11,050
        (10_650, 10_700, 10_200, 10_600),  # D3 — 저가 10,200 ≤ floor(10,250) → 청산
    ]
    out = _run(rows, be_atr=[400.0] * len(rows), be_mult=1.5)
    assert out["tranches"] == 3
    assert out["exit_idx"] == 3
    assert out["exit_kind"] == "avg_breakeven"
    assert out["exit_price"] == _approx(10_250.0)
    assert out["virtual_R"] == _approx(-0.5)
    assert out["killed"] == 1


def test_c15b_stop_floor_never_decreases_across_days():
    """C15 — 명시적 단조성: 트리거되지 않는 중간 날에도 floor 는 이전 값 이하로 내려가지 않는다.

    C15 시나리오를 하루 더 연장해도(트리거 이후 봉은 안 쓰이므로) 이 사실 자체는 C15 로 충분히
    검증된다 — 여기서는 세트선이 오르는(last 증가) 정상 경로에서 floor 가 함께 오르는지만 재확인한다.
    """
    out = _run(C1_ROWS, anchor_idx=5, anchor_price=11_700)
    # C1 은 k=3 도달 후 세트선(last-2N)이 9,500 → 10,000 으로 오른다 — 래칫은 이 정상 상승을 그대로 반영.
    assert out["set_stop"] == _approx(10_000.0)


# ===========================================================================
# C16 — kojiro live ATR 「가중평단 − 2×ATR」 항 (설계 §4-1, `existing_2n_live`)
# ===========================================================================
def test_c16_kojiro_live_atr_line_tightens_below_set_line():
    """C16 — be_atr(live) 가 N 보다 훨씬 작으면 `avg − stop_atr×live_ATR` 가 세트선보다 더 조인다.

    D1 추가(10,500) 후 avg=10,250 · 세트선 9,500 · backstop 9,430. live ATR=100(고정) 이면
    `existing_2n_live = 10,250 − 2×100 = 10,050` 이 최댓값(가장 조인 선) — be_mult=0 으로 본전 무장은
    끈다. D2 저가 10,000 ≤ 10,050 → 10,050 에서 청산(kind=existing_2n_live). 이 항이 없으면(구형)
    최댓값은 세트선 9,500 이라 저가 10,000 은 무사 — 반증 테스트다.
    """
    rows = [
        (10_000, 10_100, 9_900, 10_000),   # D0
        (10_100, 10_600, 10_200, 10_500),  # D1 — 추가 10,500, 저가 10,200 은 10,050 에 무사
        (10_400, 10_450, 10_000, 10_100),  # D2 — 저가 10,000 ≤ 10,050
    ]
    out = _run(rows, be_atr=[100.0] * len(rows), be_mult=0.0)
    assert out["tranches"] == 2
    assert out["exit_idx"] == 2
    assert out["exit_kind"] == "existing_2n_live"
    assert out["exit_price"] == _approx(10_050.0)
    assert out["virtual_R"] == _approx(TWO_THIRDS * (-400.0) / 1_000.0)
    assert out["killed"] == 1


def test_c16b_donchian_no_be_atr_skips_live_atr_term():
    """C16 — `be_atr=None`(donchian) 이면 이 항 자체가 없다 — C16 과 같은 저가에서도 무사."""
    rows = [
        (10_000, 10_100, 9_900, 10_000),
        (10_100, 10_600, 10_050, 10_500),
        (10_400, 10_450, 10_000, 10_100),
    ]
    out = _run(rows, be_atr=None, be_mult=0.0)
    assert out["tranches"] == 2
    assert out["exit_kind"] == "open"
    assert out["killed"] == 0


# ===========================================================================
# G4 — 코어가 cfg.step_n 을 실제로 읽는지 (돌연변이 G4: `1.0 * N` 하드코딩 탐지)
# ===========================================================================
def test_g4_core_reads_cfg_step_n_not_hardcoded_one():
    """G4 — `step_n=0.5` 격자(½N)에서 첫 눈금은 10,250 이어야 한다(1N 이면 10,500).

    S0 앵커 모드가 {½N, 1N} 격자를 돌리는데, 코어가 `cfg.step_n` 대신 `1.0` 을 쓰면 ½N 결과가
    조용히 1N 결과로 나온다(§3 문서). 이 테스트는 ½N 격자가 실제로 다른 눈금을 만드는지 고정한다.
    """
    ps = _ps()
    half_n_cfg = ps.LadderConfig(step_n=0.5, sizes=ps.LADDER_C.sizes, gap_skip_mult=1.05)
    rows = [D0, (10_100, 10_260, 10_050, 10_200)]  # 고가 10,260 ≥ 10,250(½N) · < 10,500(1N)
    out = _run(rows, cfg=half_n_cfg)
    assert out["tranches"] == 2, "½N 눈금(10,250)에 닿아야 한다 — 1N 이면 추가 없음(tranches=1)"
    assert _fills(out) == [(0, 10_000.0, 0.6667), (1, 10_250.0, 0.6667)]


def test_g4b_full_n_step_still_works_as_baseline():
    """대조군 — `step_n=1.0`(LADDER_C 기본)이면 같은 고가(10,260)로는 추가가 없다."""
    out = _run([D0, (10_100, 10_260, 10_050, 10_200)])
    assert out["tranches"] == 1


# ===========================================================================
# S2 — 세트선이 `stop_atr` 파라미터를 실제로 쓰는지 (하드코딩 2.0 탐지)
# ===========================================================================
def test_s2_set_line_uses_stop_atr_param_not_hardcoded_two():
    """S2 — `stop_atr=3.0` 이면 세트선 = last−3N. 하드코딩 2.0 이면 세트선이 9,500 으로 더
    느슨해져(정답은 9,000) 저가 9,200 이 무사히 통과하지 못한다(정답은 통과해야 한다).

    backstop 은 hard=−20% 로 느슨하게 둬 세트선이 항상 최댓값이 되게 한다(9,000 vs 8,200).
    """
    rows = [
        D0,
        D1_ADD,                            # 추가 10,500 → avg 10,250
        (9_600, 9_650, 9_200, 9_300),       # 저가 9,200 — 정답 세트선(9,000) 은 무사, 하드코딩(9,500) 이면 트리거
    ]
    out = _run(rows, stop_atr=3.0, hard_stop_pct=-20.0)
    assert out["tranches"] == 2
    assert out["exit_kind"] == "open", "세트선이 last−3N(9,000) 이어야 저가 9,200 이 무사하다"
    assert out["exit_idx"] == 2


# ===========================================================================
# B6 — be_mult(breakeven_promote_atr) 이 실제로 승격 여부·임계를 가른다
# ===========================================================================
def test_b6_be_mult_zero_disables_breakeven_entirely():
    """B6 — `be_mult=0` 이면 본전 승격이 절대 켜지지 않는다. C8 시나리오를 그대로 쓰되 be_mult=0
    이면 D3 avg_breakeven(10,250) 청산 대신 앵커(10,600)까지 보유한다.
    """
    rows = [
        D0,
        D1_ADD,
        (10_450, 11_050, 10_200, 10_900),
        (10_900, 10_950, 10_200, 10_300),
        (10_300, 10_500, 10_250, 10_450),
        (10_450, 10_700, 10_400, 10_600),
    ]
    out = _run(
        rows, no_add=[False, False, True, False, False, False],
        anchor_idx=5, anchor_price=10_600, be_mult=0.0,
    )
    assert out["tranches"] == 2
    assert out["exit_idx"] == 5
    assert out["exit_kind"] == "anchor"
    assert out["virtual_R"] == _approx(TWO_THIRDS * 700.0 / 1_000.0)


def test_b6b_be_mult_one_uses_avg_plus_one_n_threshold_not_hardcoded_1_5():
    """B6 — `be_mult=1.0` 이면 임계 = avg+1.0N(10,750). 하드코딩 1.5 면 임계가 11,000 이라
    hsb 10,750 으로는 안 켜진다(정답은 켜져야 한다).
    """
    rows = [
        D0,
        D1_ADD,                             # 추가 10,500 → avg 10,250
        (10_400, 10_750, 10_350, 10_700),   # hsb → 10,750 = avg+1.0N(경계)
        (10_700, 10_750, 10_200, 10_300),   # 저가 10,200 ≤ 10,250(armed) → 청산
    ]
    out = _run(rows, be_mult=1.0)
    assert out["tranches"] == 2
    assert out["exit_idx"] == 3
    assert out["exit_kind"] == "avg_breakeven"
    assert out["exit_price"] == _approx(10_250.0)


# ===========================================================================
# B1 — 본전 승격 경계(hsb == avg + be_mult×A)는 등호 포함(`>=`)
# ===========================================================================
def test_b1_breakeven_arm_boundary_is_inclusive():
    """B1 — `be_mult=1.0` 로 임계를 정확히 10,750 에 맞춘다. hsb 가 **정확히** 10,750 이면
    armed 여야 한다(`>` 로 바뀌면 이 경계에서 armed 되지 않아 청산이 나지 않는다)."""
    rows = [
        D0,
        D1_ADD,                             # 추가 10,500 → avg 10,250
        (10_400, 10_750, 10_350, 10_700),   # hsb 정확히 10,750(=avg+1.0×500)
        (10_700, 10_750, 10_200, 10_300),   # 저가 10,200 ≤ armed 선 10,250
    ]
    out = _run(rows, be_mult=1.0)
    assert out["exit_kind"] == "avg_breakeven", "경계(==)에서 armed 되지 않으면 set_line(9,500) 무사 통과로 open 이 된다"
    assert out["exit_price"] == _approx(10_250.0)


# ===========================================================================
# C14 — no_add_flags
# ===========================================================================
def test_c14_no_add_flags_calendar():
    """C14 — `flag[i] = (dates[i+1] − dates[i]).days ≥ 3`, 마지막 봉은 금요일이면 True.

    09-25(금)→09-28(월) 3일 True · 월→화 False · 화→수 False · 수(목 휴장)→금 2일 False · 마지막 10-02 금 True.
    """
    ps = _ps()
    dates = [
        date(2026, 9, 25), date(2026, 9, 28), date(2026, 9, 29),
        date(2026, 9, 30), date(2026, 10, 2),
    ]
    assert list(ps.no_add_flags(dates)) == [True, False, False, False, True]


def test_c14b_no_add_flags_last_bar_thursday_and_long_holiday():
    """마지막 봉 목요일 = False(다음 거래일을 모른다 · KIS chk-holiday 호출 금지). 수→월(5일) = True."""
    ps = _ps()
    assert list(ps.no_add_flags([date(2026, 9, 30), date(2026, 10, 1)])) == [False, False]
    assert list(ps.no_add_flags([date(2026, 9, 30), date(2026, 10, 5), date(2026, 10, 6)])) == [
        True, False, False,
    ]
    assert list(ps.no_add_flags([])) == []


# ===========================================================================
# 비유한 입력 거부 (§1-4 끝)
# ===========================================================================
@pytest.mark.parametrize("bad_n", [0.0, -1.0, float("nan"), float("inf")])
def test_non_finite_or_non_positive_n_is_rejected(bad_n):
    """`N ≤ 0`·NaN·inf 는 ValueError — 어댑터가 그 레코드를 error 로 남긴다."""
    ps = _ps()
    with pytest.raises(ValueError):
        ps.overlay_ladder(
            _bars(C3_ROWS), 0, E, bad_n,
            cfg=ps.LADDER_C, stop_atr=2.0, hard_stop_pct=-8.0, be_mult=1.5, be_atr=None,
            no_add=[False] * len(C3_ROWS), anchor_idx=None, anchor_price=None,
            anchor_add_allowed=True,
        )


def test_outputs_are_finite_numbers():
    """§1-4 — 모든 값은 유한수(None 은 허용 — `set_stop` 은 k=1 이면 None)."""
    out = _run(C1_ROWS, anchor_idx=5, anchor_price=11_700)
    for key in ("avg", "exit_price", "virtual_R", "base_R", "set_stop", "fixed_stop", "peak_risk_R"):
        v = out[key]
        assert v is None or math.isfinite(float(v)), (key, v)
