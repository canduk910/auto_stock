"""R2 (2026-05-04): NBER 침체 + S&P -20% 약세장 음영 데이터 단위 테스트.

원본: tests/unit/test_macro_events.py — import 경로만 macro_lite.events로 교체
(요건서 REQ-PKG-01). 본문은 원본 그대로 유지.
"""

from macro_lite.events import (
    NBER_RECESSIONS,
    SP500_BEAR_MARKETS,
    get_events_in_range,
)


def test_data_integrity():
    """상수 데이터 정합성 — 개수 + 필수 필드 (1960년 이후 전체 시계열)."""
    assert len(NBER_RECESSIONS) == 9
    assert len(SP500_BEAR_MARKETS) == 9
    for r in NBER_RECESSIONS:
        assert r["start"] < r["end"]
        assert r["label"]
    for b in SP500_BEAR_MARKETS:
        assert b["start"] < b["end"]
        assert b["drawdown"] < -20  # -20% 이상 약세장
        assert b["label"]


def test_get_events_in_range_includes_overlapping_recession():
    """입력 범위와 겹치는 침체 포함 (서브프라임 침체)."""
    ev = get_events_in_range("2007-01-01", "2010-12-31")
    labels = [r["label"] for r in ev["recessions"]]
    assert "서브프라임 침체" in labels


def test_legacy_recessions_included():
    """1962년 이후 전 시계열 침체 (오일쇼크/볼커/걸프전 등)도 포함."""
    ev = get_events_in_range("1960-01-01", "2025-12-31")
    labels = {r["label"] for r in ev["recessions"]}
    for expected in ("오일쇼크 침체", "볼커 침체", "걸프전 침체", "닷컴 침체", "서브프라임 침체", "코로나 침체"):
        assert expected in labels


def test_legacy_bear_markets_included():
    """1962~1987 약세장(케네디/오일쇼크/블랙먼데이 등)도 포함."""
    ev = get_events_in_range("1960-01-01", "2025-12-31")
    labels = {b["label"] for b in ev["bear_markets"]}
    for expected in ("케네디 슬라이드", "오일쇼크 약세장", "블랙먼데이", "닷컴 약세장", "서브프라임 약세장"):
        assert expected in labels


def test_get_events_in_range_excludes_outside():
    """겹치지 않는 기간은 제외."""
    ev = get_events_in_range("2024-01-01", "2025-12-31")
    assert ev["recessions"] == []
    assert ev["bear_markets"] == []


def test_get_events_in_range_clips_to_input_range():
    """원본 시작/종료가 입력 범위 밖이면 클립 + original_* 보존."""
    ev = get_events_in_range("2008-01-01", "2008-06-30")
    assert len(ev["recessions"]) == 1
    rec = ev["recessions"][0]
    assert rec["start"] == "2008-01-01"  # clipped
    assert rec["end"] == "2008-06-30"    # clipped
    assert rec["original_start"] == "2007-12-01"
    assert rec["original_end"] == "2009-06-30"


def test_invalid_range_returns_empty():
    """start > end 또는 빈 입력은 빈 dict."""
    assert get_events_in_range("", "") == {"recessions": [], "bear_markets": []}
    assert get_events_in_range("2020-12-31", "2020-01-01") == {"recessions": [], "bear_markets": []}


def test_bear_markets_include_inflation_2022():
    """2022 인플레 약세장도 포함."""
    ev = get_events_in_range("2022-01-01", "2022-12-31")
    labels = [b["label"] for b in ev["bear_markets"]]
    assert "인플레 약세장" in labels
