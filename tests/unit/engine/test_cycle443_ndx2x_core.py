"""cycle443 Red — ndx2x_riskoff 핵심 신호(규칙 C)·KIS 파서·집행창 순수 함수.

오라클 = `tools/replay/ra_us.py::feats_from_close`(연구 규칙 원본). 운영 신호 함수
(`src.engine.ndx2x_core`)가 그 함수와 **날짜별로 완전히 일치**해야 한다(자문
`_workspace/domain_consult/2026-10-06_ndx2x_risk_off.md` 「후속 검증 권고」 1).

이 worktree 에는 `data/archive/global_long/raw/yahoo_NDX.json` 실측 원자료가 없다
(git 비추적 · 로컬 1회 수집물) — 그래서 역사적 날짜(2020-02~04 등)를 리터럴로 쓰는
대신, 같은 경계(R4=-20% 정확히·T7=0 정확히·느린 약세장·V 자 폭락 모양)를 만드는
합성 종가열로 오라클과 대조한다(한계 — 보고서에 명시).
"""
from __future__ import annotations

import math
from datetime import time

import pandas as pd
import pytest

from src.engine import ndx2x_core as core
from tools.replay.ra_us import feats_from_close


def _oracle_cells(closes: list[float]) -> list[str]:
    """`ra_us.feats_from_close` 로 날짜별 칸(연구 규약 — 결측=조건 거짓)을 재현한다."""
    f = feats_from_close(pd.Series(closes))
    cells = []
    for t7, r4 in zip(f["T7"], f["R4"]):
        cond1 = (not math.isnan(t7)) and t7 > 0
        cond2 = (not math.isnan(r4)) and r4 <= -0.20
        cells.append(f"{int(cond1)}{int(cond2)}")
    return cells


def _slow_bear_series(n: int = 400) -> list[float]:
    """느린 약세장 모양 — 2008/2022 형(천천히 오르다 서서히 무너진다). T7·R4 둘 다 살아 움직인다."""
    out = []
    price = 100.0
    for i in range(n):
        if i < 200:
            price *= 1.0015  # 완만한 상승 (고점 형성)
        elif i < 320:
            price *= 0.9975  # 완만한 하락 (추세 꺾임 + 고점 대비 하락 누적)
        else:
            price *= 1.0025  # 회복
        out.append(price)
    return out


def _v_shape_crash_series(n: int = 400) -> list[float]:
    """V 자 폭락 — 2020 형(짧고 깊게 빠진 뒤 빠르게 회복). 자문의 "브레이크 무방비" 반례."""
    out = []
    price = 100.0
    for i in range(n):
        if i < 260:
            price *= 1.001
        elif i < 280:
            price *= 0.96  # 20일 동안 급락
        else:
            price *= 1.02  # 급등 회복
        out.append(price)
    return out


def _flat_series(n: int = 400) -> list[float]:
    return [100.0] * n


@pytest.mark.parametrize(
    "series_factory", [_slow_bear_series, _v_shape_crash_series, _flat_series],
)
def test_decide_daily_cell_matches_ra_us_oracle_every_day(series_factory):
    """매 날짜 — ndx2x_core 의 칸이 ra_us 오라클과 완전히 일치(이력이 충분한 날만 비교)."""
    closes = series_factory()
    oracle = _oracle_cells(closes)
    for i in range(core.MIN_HISTORY_DAYS - 1, len(closes)):
        t7 = core.compute_t7(closes, i)
        r4 = core.compute_r4(closes, i)
        got_cell = core.research_cell(t7, r4)
        assert got_cell == oracle[i], f"day {i}: got={got_cell} oracle={oracle[i]} t7={t7} r4={r4}"


def test_decide_daily_uses_last_index_and_matches_oracle():
    closes = _slow_bear_series()
    decision = core.decide_daily(closes)
    assert decision.reason == "ok"
    oracle = _oracle_cells(closes)
    assert decision.cell == oracle[-1]
    assert decision.desired_state == core.state_for_cell(decision.cell)


def test_r4_boundary_exactly_minus_20pct_is_cash_side():
    """R4 == -0.20 정확히 → `<=` 라 조건2 성립(현금 성분). 돌연변이 표적 `<=`→`<`.

    경계는 `research_cell`(칸 결정 함수)의 비교 연산 자체를 직접 겨눈다 — 부동소수
    나눗셈으로 -0.20 을 bit-identical 하게 재현하는 것은 일반적으로 불가능하다
    (`0.8 - 1.0 != -0.2`, IEEE754). 나눗셈 공식 자체의 날짜별 일치는 위 오라클
    파라미터 테스트가 전 구간을 돈다.
    """
    cell = core.research_cell(t7=-0.01, r4=core.R4_THRESHOLD)
    assert cell == "01"
    assert core.state_for_cell(cell) == "cash"


def test_t7_boundary_exactly_zero_is_slope_down_side():
    """T7 == 0 정확히 → `> 0` 이 아니므로 조건1 거짓(기울기 하락 성립). 돌연변이 표적 `>`→`>=`."""
    cell = core.research_cell(t7=0.0, r4=0.0)
    assert cell[0] == "0"  # 조건1 거짓 비트

    # compute_t7 자체도 평탄 종가열에서 정확히 0.0 을 낸다는 사실(공식 계층)을 확인.
    flat = [100.0] * 400  # SMA120(t) == SMA120(t-20) 항상 같다
    assert core.compute_t7(flat, 399) == 0.0


def test_insufficient_history_is_fail_closed_not_research_default():
    """이력 < 250 → reason=insufficient_history, desired_state=None(연구의 "결측→2배"로 새지 않는다)."""
    closes = [100.0] * (core.MIN_HISTORY_DAYS - 1)
    decision = core.decide_daily(closes)
    assert decision.reason == "insufficient_history"
    assert decision.desired_state is None
    assert decision.cell is None


def test_exactly_min_history_is_sufficient():
    closes = [100.0 + i * 0.01 for i in range(core.MIN_HISTORY_DAYS)]
    decision = core.decide_daily(closes)
    assert decision.reason == "ok"


# ─────────────────────────── 집행창 ───────────────────────────

@pytest.mark.parametrize("t,expected", [
    (time(9, 29, 59), False),
    (time(9, 30, 0), True),
    (time(10, 0, 0), True),
    (time(10, 30, 0), True),
    (time(10, 30, 1), False),
    (time(15, 0, 0), False),
])
def test_in_execution_window_boundaries(t, expected):
    assert core.in_execution_window(t) is expected


# ─────────────────────────── 상태 전이 ───────────────────────────

@pytest.mark.parametrize("held,desired,expected", [
    (None, "2x", "BUY"),
    ("cash", "2x", "BUY"),
    ("2x", "2x", "NONE"),
    ("2x", "cash", "SELL"),
    (None, "cash", "NONE"),
    ("cash", "cash", "NONE"),
    ("2x", None, "NONE"),  # fail-closed 보류 — 직전 상태 유지
    ("cash", None, "NONE"),
])
def test_plan_action(held, desired, expected):
    assert core.plan_action(held, desired) == expected


# ─────────────────────────── KIS FHKST03030100 파서 ───────────────────────────

def _row(date_str: str, close: float) -> dict:
    return {"stck_bsop_date": date_str, "ovrs_nmix_prpr": str(close)}


def test_parse_kis_rows_latest_first_roundtrip():
    rows = [_row("20261009", 100.5), _row("20261008", 99.0), _row("20261007", 98.0)]
    parsed = core.parse_kis_rows(rows)
    assert parsed == [("20261009", 100.5), ("20261008", 99.0), ("20261007", 98.0)]


def test_parse_kis_rows_rejects_non_latest_first_order():
    """0행은 오류로 다루는 호출부와 별개로, 순서가 최신순이 아니면 KIS 계약 drift로 본다."""
    rows = [_row("20261007", 98.0), _row("20261009", 100.5)]  # 오름차순(비정상)
    with pytest.raises(core.MalformedRowError):
        core.parse_kis_rows(rows)


def test_parse_kis_row_rejects_malformed_date():
    with pytest.raises(core.MalformedRowError):
        core.parse_kis_row({"stck_bsop_date": "bad", "ovrs_nmix_prpr": "100.0"})


def test_parse_kis_row_rejects_unparseable_price():
    with pytest.raises(core.MalformedRowError):
        core.parse_kis_row({"stck_bsop_date": "20261009", "ovrs_nmix_prpr": "n/a"})


def test_parse_kis_row_rejects_nonpositive_price():
    with pytest.raises(core.MalformedRowError):
        core.parse_kis_row({"stck_bsop_date": "20261009", "ovrs_nmix_prpr": "0"})


def test_parse_kis_rows_empty_list_is_allowed_passthrough():
    """0행 자체는 이 파서가 아니라 I/O 래퍼(`OverseasIndexEmptyResponseError`)가 막는다."""
    assert core.parse_kis_rows([]) == []


# ─────────────────────────── 100행 캡 + 시작일 누락 → 겹치게 이어붙이기 ───────────────────────────

def test_merge_batches_dedupes_overlap_and_sorts_ascending():
    """겹치는 날짜가 있는 두 배치(과거로 커서를 당겨 받은 순서)를 날짜 오름차순 하나로 합친다."""
    # 콜1: 최근 구간(최신순이 아니라 아무 순서로 와도 merge 는 날짜키 dict 이므로 무관)
    batch1 = [("20261009", 100.5), ("20261008", 99.0), ("20261007", 98.0)]
    # 콜2: 커서를 과거로 당겨 받은 배치 — 20261007 에서 겹친다(경계 보장 설계)
    batch2 = [("20261007", 98.0), ("20261006", 97.5), ("20261005", 97.0)]
    merged = core.merge_batches([batch1, batch2])
    assert merged == [
        ("20261005", 97.0), ("20261006", 97.5), ("20261007", 98.0),
        ("20261008", 99.0), ("20261009", 100.5),
    ]


def test_merge_batches_first_batch_wins_on_conflicting_overlap():
    """겹치는 날짜의 값이 다르면(비정상) 먼저 받은(더 최근을 다룬) 배치 값을 유지한다."""
    batch1 = [("20261007", 98.0)]
    batch2 = [("20261007", 999.0)]  # 충돌 — 있어서는 안 되는 상황이지만 결정적이어야 한다
    merged = core.merge_batches([batch1, batch2])
    assert merged == [("20261007", 98.0)]


def test_merge_batches_simulates_missing_near_start_quirk_bridged_by_cursor_overlap():
    """실측 — 요청 시작일 근처 며칠이 빠지는 현상을 커서 겹침으로 복원.

    master 400일 중 call1=[300:400), call2=[150:305)(앞쪽 155일 중 처음 5일만 "빠짐" 모사,
    즉 150~154 일이 call2 응답에서 빠짐) → call2 의 시작 근처 누락은 call3 가 겹쳐 메운다.
    """
    master = [(f"{20260101 + i:08d}", 100.0 + i * 0.1) for i in range(400)]
    call1 = master[300:400]
    # call2 는 call1 의 최저 날짜(300)에서 커서를 당겨 받았다고 가정 — 실제로는 [150,300] 구간을
    # 요청했는데 시작일 근처(150~154) 5일이 빠져서 왔다(실측 quirk 모사).
    call2 = master[155:301]
    # call3 는 call2 의 최저 날짜(155)에서 다시 커서를 당겨 받았고, 역시 시작일 근처(100~104) 가 빠졌다.
    call3 = master[105:156]
    merged = core.merge_batches([call1, call2, call3])
    # 105~399 전 구간이 빠짐없이 복원된다(150~154·100~104 의 "빠짐"이 다음 콜의 겹침으로 메워짐).
    expected = master[105:400]
    assert merged == expected
