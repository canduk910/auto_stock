"""RS 1단계 Red — `src/engine/fundamental_score.py` (순수 함수, I/O 0).

명세 = `_workspace/design/2026-10-13_rs_fundamental_phase1.md` §B.

명세 해석 가정(구현이 따를 계약):
- `available_from(stac_yymm, is_annual_or_q4)` — "YYYYMM" 결산월의 **말일** + 45일(분기) /
  + 90일(4분기·연간). 예 202603 분기 → 2026-03-31 + 45 = 2026-05-15.
- `known_as_of(rows, as_of)` — 행 = dict, `stac_yymm` 필수. `is_annual_or_q4` 키가 있으면 그 값을,
  없으면 결산월이 12 인지로 판정(12월 결산 가정). `available_from <= as_of` 인 행만, 입력 순서 유지.
- `quarterly_from_cumulative(rows)` — 행 = `{"stac_yymm": "YYYYMM", "value": float|None}`.
  12월 결산 가정: 03=1Q(그대로) · 06/09/12 = 그 누적 − 같은 해 직전 분기(−3개월) 누적.
  4분기(12) = 연간 누적 − 3분기 누적. 직전 분기 결측(행 없음 또는 value None) → None(추정 금지).
  자기 value None → None. 입력 순서 무관.
- `turnaround_flags(q_now, q_yoy)` → `{"turnaround": bool|None, "yoy_growth": float|None}`.
  turnaround = (q_yoy ≤ 0 ∧ q_now > 0). yoy_growth = q_now/q_yoy − 1 (q_yoy > 0 일 때만).
  어느 입력이든 None → 두 값 모두 None.
- `target_revision_breadth(opinions, as_of, window_bd=60)` — opinion = dict
  `{"bsop_date": date, "mbcr_name": str, "hts_goal_prc": int|float|None}` (C 래퍼의 정규화 형식).
  · 창 = as_of 를 1일째로 세어 거꾸로 **평일** window_bd 개(공휴일은 고려하지 않는 단순 평일 기준).
    창 시작일(그 window_bd 번째 평일) 포함, as_of 이후(미래) 제외.
  · 목표가 0·None 행은 먼저 버린다. 남은 창 안 행만으로 증권사별 가장 최근 vs 그 직전(둘 다 창 안) 비교.
  · 분모 = 창 안에 유효 행이 1개 이상인 증권사 수. 행이 1개뿐이거나 같으면 상향·하향 어느 쪽도 아님.
  · 분모 0 → None.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.engine import fundamental_score as fs

pytestmark = pytest.mark.unit


# ── available_from ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("yymm,annual,expected", [
    ("202603", False, date(2026, 5, 15)),   # 3/31 + 45
    ("202606", False, date(2026, 8, 14)),   # 6/30 + 45
    ("202609", False, date(2026, 11, 14)),  # 9/30 + 45
    ("202612", True, date(2027, 3, 31)),    # 12/31 + 90
    ("202802", False, date(2028, 4, 14)),   # 윤년 2/29 + 45
    ("202602", False, date(2026, 4, 14)),   # 평년 2/28 + 45
])
def test_available_from_month_end_plus_lag(yymm, annual, expected):
    assert fs.available_from(yymm, annual) == expected


def test_available_from_q4_flag_uses_90_even_if_not_december():
    # 비12월 결산사의 4분기(예 6월 결산) — 플래그가 정본이다.
    assert fs.available_from("202606", True) == date(2026, 6, 30) + timedelta(days=90)


# ── known_as_of ──────────────────────────────────────────────────────────────

def test_known_as_of_boundary_inclusive_and_excludes_future():
    rows = [
        {"stac_yymm": "202603", "is_annual_or_q4": False, "v": 1},
        {"stac_yymm": "202606", "is_annual_or_q4": False, "v": 2},
    ]
    assert fs.known_as_of(rows, date(2026, 5, 14)) == []
    assert fs.known_as_of(rows, date(2026, 5, 15)) == [rows[0]]
    assert fs.known_as_of(rows, date(2026, 8, 14)) == rows


def test_known_as_of_infers_q4_from_december_when_flag_absent():
    rows = [{"stac_yymm": "202512"}]  # 12월 → +90 → 2026-03-31
    assert fs.known_as_of(rows, date(2026, 3, 30)) == []
    assert fs.known_as_of(rows, date(2026, 3, 31)) == rows


def test_known_as_of_empty_rows():
    assert fs.known_as_of([], date(2026, 10, 13)) == []


# ── quarterly_from_cumulative ────────────────────────────────────────────────

def _cum(**kv):
    return [{"stac_yymm": k[1:], "value": v} for k, v in kv.items()]


def test_quarterly_from_cumulative_full_year():
    rows = _cum(m202603=100.0, m202606=250.0, m202609=300.0, m202612=500.0)
    assert fs.quarterly_from_cumulative(rows) == {
        "202603": 100.0, "202606": 150.0, "202609": 50.0, "202612": 200.0,
    }


def test_quarterly_from_cumulative_q1_is_as_is_even_alone():
    assert fs.quarterly_from_cumulative(_cum(m202603=-30.0)) == {"202603": -30.0}


def test_quarterly_from_cumulative_when_prev_quarter_missing_then_none():
    rows = _cum(m202603=100.0, m202609=300.0, m202612=500.0)  # 2분기 결측
    got = fs.quarterly_from_cumulative(rows)
    assert got["202609"] is None
    assert got["202612"] == pytest.approx(200.0)  # 4분기 = 연간 − 3분기 누적
    assert got["202603"] == 100.0


def test_quarterly_from_cumulative_when_q3_missing_then_q4_none():
    got = fs.quarterly_from_cumulative(_cum(m202606=250.0, m202612=500.0))
    assert got["202612"] is None


def test_quarterly_from_cumulative_prev_value_none_counts_as_missing():
    got = fs.quarterly_from_cumulative(_cum(m202603=None, m202606=250.0))
    assert got["202603"] is None
    assert got["202606"] is None


def test_quarterly_from_cumulative_does_not_cross_fiscal_year():
    # 2026 1분기는 2025 4분기를 빼지 않는다.
    got = fs.quarterly_from_cumulative(_cum(m202512=900.0, m202603=100.0))
    assert got["202603"] == 100.0


def test_quarterly_from_cumulative_order_independent():
    rows = _cum(m202612=500.0, m202603=100.0, m202609=300.0, m202606=250.0)
    assert fs.quarterly_from_cumulative(rows)["202606"] == 150.0


# ── turnaround_flags ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("now,yoy,turn,growth", [
    (5.0, -10.0, True, None),    # 적자 → 흑자
    (5.0, 0.0, True, None),      # 0 → 흑자 (yoy ≤ 0 경계 포함)
    (0.0, -10.0, False, None),   # now > 0 이 아니다 (0 경계)
    (0.0, 0.0, False, None),
    (-3.0, -10.0, False, None),  # 적자 지속
    (15.0, 10.0, False, 0.5),    # 흑자 지속 + 50% 증가
    (-5.0, 10.0, False, -1.5),   # 흑자 → 적자
])
def test_turnaround_flags_cases(now, yoy, turn, growth):
    got = fs.turnaround_flags(now, yoy)
    assert got["turnaround"] is turn
    if growth is None:
        assert got["yoy_growth"] is None
    else:
        assert got["yoy_growth"] == pytest.approx(growth)


@pytest.mark.parametrize("now,yoy", [(None, 1.0), (1.0, None), (None, None)])
def test_turnaround_flags_when_input_none_then_all_none(now, yoy):
    assert fs.turnaround_flags(now, yoy) == {"turnaround": None, "yoy_growth": None}


# ── target_revision_breadth ──────────────────────────────────────────────────

AS_OF = date(2026, 10, 13)  # 화요일


def _bd_back(d: date, n: int) -> date:
    """d 를 1일째로 세어 n 번째 평일(테스트 쪽 독립 계산 — 공휴일 미고려)."""
    count = 0
    cur = d
    while True:
        if cur.weekday() < 5:
            count += 1
            if count == n:
                return cur
        cur -= timedelta(days=1)


def _op(d: date, broker: str, goal):
    return {"bsop_date": d, "mbcr_name": broker, "hts_goal_prc": goal}


def test_breadth_two_up_one_down_three_brokers_then_plus_one_third():
    ops = [
        _op(date(2026, 9, 1), "A", 100), _op(date(2026, 10, 1), "A", 120),  # 상향
        _op(date(2026, 9, 2), "B", 100), _op(date(2026, 10, 2), "B", 110),  # 상향
        _op(date(2026, 9, 3), "C", 100), _op(date(2026, 10, 5), "C", 90),   # 하향
    ]
    assert fs.target_revision_breadth(ops, AS_OF) == pytest.approx(1 / 3)


def test_breadth_when_no_opinions_then_none():
    assert fs.target_revision_breadth([], AS_OF) is None


def test_breadth_single_row_broker_counts_in_denominator_only():
    ops = [
        _op(date(2026, 9, 1), "A", 100), _op(date(2026, 10, 1), "A", 120),  # 상향
        _op(date(2026, 10, 6), "B", 80),                                    # 의견만
    ]
    assert fs.target_revision_breadth(ops, AS_OF) == pytest.approx(1 / 2)


def test_breadth_unchanged_target_is_neither():
    ops = [_op(date(2026, 9, 1), "A", 100), _op(date(2026, 10, 1), "A", 100)]
    assert fs.target_revision_breadth(ops, AS_OF) == pytest.approx(0.0)


def test_breadth_uses_most_recent_vs_immediately_previous():
    ops = [
        _op(date(2026, 8, 20), "A", 150),
        _op(date(2026, 9, 10), "A", 100),
        _op(date(2026, 10, 1), "A", 110),  # 직전(100) 대비 상향 — 150 과 비교하지 않는다
    ]
    assert fs.target_revision_breadth(ops, AS_OF) == pytest.approx(1.0)


def test_breadth_zero_or_missing_target_rows_excluded():
    ops = [
        _op(date(2026, 9, 1), "A", 100),
        _op(date(2026, 10, 1), "A", 0),     # 버림 → A 는 행 1개 → 중립
        _op(date(2026, 10, 2), "B", None),  # 버림 → B 는 분모에서도 빠짐
        _op(date(2026, 9, 3), "C", 100), _op(date(2026, 10, 5), "C", 90),   # 하향
    ]
    assert fs.target_revision_breadth(ops, AS_OF) == pytest.approx(-1 / 2)


def test_breadth_when_all_targets_zero_then_none():
    ops = [_op(date(2026, 10, 1), "A", 0), _op(date(2026, 10, 2), "B", None)]
    assert fs.target_revision_breadth(ops, AS_OF) is None


def test_breadth_rows_outside_window_excluded():
    start = _bd_back(AS_OF, 60)
    before = start - timedelta(days=1)
    while before.weekday() >= 5:
        before -= timedelta(days=1)
    ops = [
        _op(before, "A", 50),               # 창 밖 → 직전값이 될 수 없다
        _op(date(2026, 10, 1), "A", 120),   # 창 안 1개 → 중립
        _op(start, "B", 100),               # 창 시작일 포함
        _op(date(2026, 10, 1), "B", 130),   # 상향
        _op(date(2026, 1, 5), "C", 100),    # 창 한참 밖 → C 는 분모에서 빠짐
    ]
    assert fs.target_revision_breadth(ops, AS_OF) == pytest.approx(1 / 2)


def test_breadth_future_rows_excluded_no_lookahead():
    ops = [
        _op(date(2026, 10, 1), "A", 100),
        _op(date(2026, 10, 14), "A", 200),  # as_of 다음날 — 그때 몰랐던 값
    ]
    assert fs.target_revision_breadth(ops, AS_OF) == pytest.approx(0.0)


def test_breadth_window_bd_parameter_honored():
    ops = [_op(_bd_back(AS_OF, 10), "A", 100), _op(AS_OF, "A", 120)]
    assert fs.target_revision_breadth(ops, AS_OF, window_bd=10) == pytest.approx(1.0)
    # 창 9영업일이면 첫 행이 빠져 중립
    assert fs.target_revision_breadth(ops, AS_OF, window_bd=9) == pytest.approx(0.0)


def test_breadth_range_bounded():
    ops = [_op(date(2026, 9, 1), "A", 100), _op(date(2026, 10, 1), "A", 50)]
    got = fs.target_revision_breadth(ops, AS_OF)
    assert -1.0 <= got <= 1.0 and got == pytest.approx(-1.0)
