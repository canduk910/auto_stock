"""RS 1단계 Red — `src/engine/rs_score.py` (순수 함수, I/O 0).

명세 = `_workspace/design/2026-10-13_rs_fundamental_phase1.md` §A.

명세 해석 가정(구현이 따를 계약):
- `ibd_lite_return(closes)` — closes 는 오래된→최신. 길이 < 190(=189봉+1) → None.
  r_n = closes[-1]/closes[-1-n] − 1, 점수 = 0.4·r63 + 0.3·r126 + 0.3·r189.
  계산에 쓰는 네 가격(closes[-1]·[-64]·[-127]·[-190]) 중 하나라도 ≤ 0 이면 None.
  계산에 쓰지 않는 가격의 0 이하는 결과에 영향이 없다(가장 단순한 해석).
- `percentile_ranks(scores)` — 오름차순 순위(가장 낮은 점수 = 순위 1 → 0, 가장 높은 점수 → 99).
  동점 = 최소 순위. n==1 → 99. None 은 순위 계산에서 빼고 None 유지. 빈 dict → 빈 dict.
- `sector_relative(scores, sector_of, min_members=5)` — 반환 = 종목별 dict
  `{"vs_sector": float|None, "sector_pct": int|None, "in_sector_pct": int|None}`.
  · 구성원 수 = 그 섹터에서 점수가 None 이 아닌 종목 수.
  · (B) vs_sector = 종목 점수 − 섹터 동일가중 평균.
  · (C) sector_pct = 섹터 평균을 **자격 있는 섹터끼리** `percentile_ranks` 한 값,
    in_sector_pct = 섹터 안에서 `percentile_ranks` 한 값.
  · 「미분류」로 시작하는 섹터 · 구성 < min_members 섹터 · sector_of 에 없는 종목 ·
    점수 None 인 종목 → 세 값 모두 None (결측 = 중립, 감점 없음).
  · 반환 dict 의 키 = 입력 scores 의 키 전부.
"""
from __future__ import annotations

import math

import pytest

from src.engine import rs_score as rs

pytestmark = pytest.mark.unit


# ── ibd_lite_return ──────────────────────────────────────────────────────────

def _series(n: int, *, base: float = 100.0) -> list[float]:
    return [base] * n


def test_ibd_lite_return_when_fewer_than_190_bars_then_none():
    assert rs.ibd_lite_return(_series(189)) is None
    assert rs.ibd_lite_return([]) is None


def test_ibd_lite_return_when_exactly_190_bars_then_weighted_sum():
    closes = _series(190)
    closes[-1] = 120.0          # 최신
    closes[-1 - 63] = 100.0     # r63 = 0.2
    closes[-1 - 126] = 80.0     # r126 = 0.5
    closes[-1 - 189] = 60.0     # r189 = 1.0
    got = rs.ibd_lite_return(closes)
    assert got == pytest.approx(0.4 * 0.2 + 0.3 * 0.5 + 0.3 * 1.0)


def test_ibd_lite_return_when_longer_series_then_uses_tail_only():
    head = [1.0] * 50  # 오래된 구간은 쓰지 않는다
    closes = head + _series(190)
    closes[-1] = 110.0
    assert rs.ibd_lite_return(closes) == pytest.approx(0.1)  # 0.4·0.1+0.3·0.1+0.3·0.1


def test_ibd_lite_return_when_flat_then_zero():
    assert rs.ibd_lite_return(_series(200)) == pytest.approx(0.0)


@pytest.mark.parametrize("idx", [-1, -64, -127, -190])
@pytest.mark.parametrize("bad", [0.0, -5.0])
def test_ibd_lite_return_when_used_price_nonpositive_then_none(idx, bad):
    closes = _series(190)
    closes[idx] = bad
    assert rs.ibd_lite_return(closes) is None


# ── percentile_ranks ─────────────────────────────────────────────────────────

def test_percentile_ranks_when_single_value_then_99():
    assert rs.percentile_ranks({"A": 0.3}) == {"A": 99}


def test_percentile_ranks_when_empty_then_empty():
    assert rs.percentile_ranks({}) == {}


def test_percentile_ranks_when_distinct_then_floor_formula_0_to_99():
    got = rs.percentile_ranks({"a": 0.1, "b": 0.2, "c": 0.3, "d": 0.4})
    # floor(99 × (rank-1)/(n-1)), n=4
    assert got == {"a": 0, "b": 33, "c": 66, "d": 99}


def test_percentile_ranks_when_tie_then_minimum_rank():
    got = rs.percentile_ranks({"a": 1.0, "b": 2.0, "c": 2.0, "d": 3.0})
    # 순위 a1, b2, c2(최소 순위), d4
    assert got == {"a": 0, "b": 33, "c": 33, "d": 99}


def test_percentile_ranks_when_all_tied_then_all_zero():
    got = rs.percentile_ranks({"a": 1.0, "b": 1.0, "c": 1.0})
    assert got == {"a": 0, "b": 0, "c": 0}


def test_percentile_ranks_when_none_present_then_excluded_and_kept_none():
    got = rs.percentile_ranks({"a": 0.1, "x": None, "b": 0.5, "y": None})
    assert got == {"a": 0, "b": 99, "x": None, "y": None}


def test_percentile_ranks_when_only_one_non_none_then_99():
    assert rs.percentile_ranks({"a": None, "b": -0.4}) == {"a": None, "b": 99}


def test_percentile_ranks_when_all_none_then_all_none():
    assert rs.percentile_ranks({"a": None, "b": None}) == {"a": None, "b": None}


def test_percentile_ranks_values_are_int_in_range():
    scores = {f"t{i}": math.sin(i) for i in range(37)}
    got = rs.percentile_ranks(scores)
    assert all(isinstance(v, int) and 0 <= v <= 99 for v in got.values())
    assert min(got.values()) == 0 and max(got.values()) == 99


# ── sector_relative ──────────────────────────────────────────────────────────

def _sector_fixture():
    # 반도체 5종(평균 0.3) · 은행 5종(평균 0.1) · 미분류 5종 · 소형섹터 4종
    scores: dict[str, float | None] = {}
    sector_of: dict[str, str] = {}
    for i, v in enumerate([0.1, 0.2, 0.3, 0.4, 0.5]):
        scores[f"S{i}"] = v
        sector_of[f"S{i}"] = "반도체"
    for i, v in enumerate([0.0, 0.05, 0.1, 0.15, 0.2]):
        scores[f"B{i}"] = v
        sector_of[f"B{i}"] = "은행"
    for i in range(5):
        scores[f"U{i}"] = 0.9
        sector_of[f"U{i}"] = "미분류(기타)"
    for i in range(4):
        scores[f"M{i}"] = 0.7
        sector_of[f"M{i}"] = "소형"
    return scores, sector_of


def test_sector_relative_vs_sector_is_score_minus_equal_weight_mean():
    scores, sector_of = _sector_fixture()
    got = rs.sector_relative(scores, sector_of)
    assert got["S4"]["vs_sector"] == pytest.approx(0.5 - 0.3)
    assert got["S0"]["vs_sector"] == pytest.approx(0.1 - 0.3)
    assert got["B2"]["vs_sector"] == pytest.approx(0.0)


def test_sector_relative_sector_pct_ranks_only_eligible_sectors():
    scores, sector_of = _sector_fixture()
    got = rs.sector_relative(scores, sector_of)
    # 자격 섹터 = 반도체(0.3) · 은행(0.1) → 반도체 99, 은행 0
    assert got["S0"]["sector_pct"] == 99
    assert got["B4"]["sector_pct"] == 0


def test_sector_relative_in_sector_pct_ranks_within_sector():
    scores, sector_of = _sector_fixture()
    got = rs.sector_relative(scores, sector_of)
    assert [got[f"S{i}"]["in_sector_pct"] for i in range(5)] == [0, 24, 49, 74, 99]


def test_sector_relative_when_unclassified_prefix_then_all_none():
    scores, sector_of = _sector_fixture()
    got = rs.sector_relative(scores, sector_of)
    assert got["U0"] == {"vs_sector": None, "sector_pct": None, "in_sector_pct": None}


def test_sector_relative_when_members_below_min_then_all_none():
    scores, sector_of = _sector_fixture()
    got = rs.sector_relative(scores, sector_of)
    assert got["M0"] == {"vs_sector": None, "sector_pct": None, "in_sector_pct": None}


def test_sector_relative_min_members_counts_only_non_none_scores():
    scores = {f"S{i}": float(i) for i in range(4)}
    scores["S4"] = None  # 5종목이지만 유효 점수 4개 → 자격 없음
    sector_of = {t: "반도체" for t in scores}
    got = rs.sector_relative(scores, sector_of)
    assert all(v == {"vs_sector": None, "sector_pct": None, "in_sector_pct": None}
               for v in got.values())


def test_sector_relative_when_score_none_or_unmapped_then_none_and_not_in_mean():
    scores, sector_of = _sector_fixture()
    scores["S5"] = None
    sector_of["S5"] = "반도체"
    scores["Z0"] = 0.4  # sector_of 에 없음
    got = rs.sector_relative(scores, sector_of)
    assert got["S5"] == {"vs_sector": None, "sector_pct": None, "in_sector_pct": None}
    assert got["Z0"] == {"vs_sector": None, "sector_pct": None, "in_sector_pct": None}
    # None 은 평균에서 빠진다 → 반도체 평균 그대로 0.3
    assert got["S4"]["vs_sector"] == pytest.approx(0.2)


def test_sector_relative_min_members_parameter_honored():
    scores, sector_of = _sector_fixture()
    got = rs.sector_relative(scores, sector_of, min_members=4)
    assert got["M0"]["vs_sector"] == pytest.approx(0.0)
    assert got["M0"]["sector_pct"] == 99  # 소형 0.7 > 반도체 0.3 > 은행 0.1


def test_sector_relative_returns_entry_for_every_input_ticker():
    scores, sector_of = _sector_fixture()
    got = rs.sector_relative(scores, sector_of)
    assert set(got) == set(scores)


# ── 비유한값·섹터명 결측 가드 ────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_ibd_lite_return_non_finite_input_gives_none(bad):
    closes = [100.0] * 189 + [bad]
    assert rs.ibd_lite_return(closes) is None
    closes = [bad] + [100.0] * 188 + [110.0]
    assert rs.ibd_lite_return(closes) is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_percentile_ranks_non_finite_becomes_none(bad):
    got = rs.percentile_ranks({"a": 1.0, "b": bad, "c": 2.0})
    assert got["b"] is None
    assert got["a"] == 0 and got["c"] == 99


@pytest.mark.parametrize("sec", [None, "", "   "])
def test_sector_relative_blank_sector_name_is_missing(sec):
    scores = {f"T{i}": 0.1 * i for i in range(6)}
    got = rs.sector_relative(scores, {t: sec for t in scores})
    assert all(v == {"vs_sector": None, "sector_pct": None, "in_sector_pct": None} for v in got.values())


def test_sector_relative_non_finite_score_excluded():
    scores = {f"T{i}": 0.1 * i for i in range(5)}
    scores["T5"] = float("nan")
    got = rs.sector_relative(scores, {t: "반도체" for t in scores})
    assert got["T5"]["vs_sector"] is None
    assert got["T0"]["vs_sector"] == pytest.approx(0.0 - 0.2)
