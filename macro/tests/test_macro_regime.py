"""macro_lite/regime.py 체제 판단 단위 테스트.

원본: tests/unit/test_macro_regime.py — import 경로만 macro_lite.regime로 교체
(요건서 REQ-PKG-01). 본문은 원본 그대로 유지.
"""

import pytest

from macro_lite.regime import (
    REGIME_MATRIX,
    REGIME_PARAMS,
    REGIME_DESC,
    _classify_buffett,
    _classify_fear_greed,
    _classify_buffett_with_hysteresis,
    _classify_fg_with_hysteresis,
    determine_regime,
)


# ── _classify_buffett ─────────────────────────────────────────

class TestClassifyBuffett:
    def test_low(self):
        assert _classify_buffett(0.5) == "low"

    def test_normal(self):
        assert _classify_buffett(1.0) == "normal"

    def test_high(self):
        assert _classify_buffett(1.4) == "high"

    def test_extreme(self):
        assert _classify_buffett(2.0) == "extreme"

    def test_none(self):
        assert _classify_buffett(None) == "normal"

    def test_boundary_08(self):
        # 0.8 >= 0.8 -> not < 0.8 -> normal
        assert _classify_buffett(0.8) == "normal"

    def test_boundary_12(self):
        # 1.2 >= 1.2 -> not < 1.2 -> high
        assert _classify_buffett(1.2) == "high"

    def test_boundary_16(self):
        # 1.6 >= 1.6 -> not < 1.6 -> extreme
        assert _classify_buffett(1.6) == "extreme"

    def test_just_below_08(self):
        assert _classify_buffett(0.79) == "low"

    def test_just_below_12(self):
        assert _classify_buffett(1.19) == "normal"

    def test_just_below_16(self):
        assert _classify_buffett(1.59) == "high"


# ── _classify_fear_greed ──────────────────────────────────────

class TestClassifyFearGreed:
    def test_extreme_fear(self):
        assert _classify_fear_greed(10) == "extreme_fear"

    def test_fear(self):
        assert _classify_fear_greed(30) == "fear"

    def test_neutral(self):
        assert _classify_fear_greed(50) == "neutral"

    def test_greed(self):
        assert _classify_fear_greed(70) == "greed"

    def test_extreme_greed(self):
        assert _classify_fear_greed(90) == "extreme_greed"

    def test_vix_override(self):
        # VIX > 35이면 FG 값과 무관하게 extreme_fear
        assert _classify_fear_greed(90, vix=36) == "extreme_fear"

    def test_none(self):
        assert _classify_fear_greed(None) == "neutral"

    def test_vix_boundary_35(self):
        # VIX=35는 >35가 아님 -> 오버라이드 안 됨
        assert _classify_fear_greed(90, vix=35) == "extreme_greed"

    def test_vix_35_01(self):
        assert _classify_fear_greed(90, vix=35.01) == "extreme_fear"

    def test_boundary_20(self):
        assert _classify_fear_greed(20) == "fear"  # >=20이므로 fear

    def test_boundary_40(self):
        assert _classify_fear_greed(40) == "neutral"

    def test_boundary_60(self):
        assert _classify_fear_greed(60) == "greed"

    def test_boundary_80(self):
        assert _classify_fear_greed(80) == "extreme_greed"

    def test_boundary_19(self):
        assert _classify_fear_greed(19) == "extreme_fear"


# ── REGIME_MATRIX 20셀 전수 검증 ──────────────────────────────

class TestRegimeMatrix:
    @pytest.mark.parametrize("buffett,fg,expected", [
        ("low", "extreme_fear", "accumulation"),
        ("low", "fear", "accumulation"),
        ("low", "neutral", "selective"),
        ("low", "greed", "cautious"),
        ("low", "extreme_greed", "cautious"),
        ("normal", "extreme_fear", "selective"),
        ("normal", "fear", "selective"),
        ("normal", "neutral", "cautious"),
        ("normal", "greed", "cautious"),
        ("normal", "extreme_greed", "defensive"),
        ("high", "extreme_fear", "selective"),
        ("high", "fear", "cautious"),
        ("high", "neutral", "cautious"),
        ("high", "greed", "defensive"),
        ("high", "extreme_greed", "defensive"),
        ("extreme", "extreme_fear", "cautious"),
        ("extreme", "fear", "defensive"),
        ("extreme", "neutral", "defensive"),
        ("extreme", "greed", "defensive"),
        ("extreme", "extreme_greed", "defensive"),
    ])
    def test_matrix_cell(self, buffett, fg, expected):
        assert REGIME_MATRIX[(buffett, fg)] == expected

    def test_matrix_has_20_cells(self):
        assert len(REGIME_MATRIX) == 20


# ── 하이스테리시스 ────────────────────────────────────────────

class TestHysteresisFG:
    def test_boundary_up_stay(self):
        # FG=41, 이전 fear -> 40+5=45 미만이므로 fear 유지
        assert _classify_fg_with_hysteresis(41, None, "fear") == "fear"

    def test_boundary_up_clear(self):
        # FG=46, 이전 fear -> 46 >= 45이므로 neutral 전환
        assert _classify_fg_with_hysteresis(46, None, "fear") == "neutral"

    def test_boundary_down_stay(self):
        # FG=39, 이전 neutral -> 40-5=35, 39 > 35이므로 neutral 유지
        assert _classify_fg_with_hysteresis(39, None, "neutral") == "neutral"

    def test_boundary_down_pass(self):
        # FG=34, 이전 neutral -> 34 < 35이므로 fear 전환
        assert _classify_fg_with_hysteresis(34, None, "neutral") == "fear"

    def test_vix_override_ignores_buffer(self):
        # VIX>35는 하이스테리시스 무시
        assert _classify_fg_with_hysteresis(50, 36, "neutral") == "extreme_fear"

    def test_exact_buffer_45(self):
        # FG=45, 이전 fear -> score < threshold+5 (threshold=40, +5=45, 45 < 45 is False)
        # 실제: 45 < 40+5=45 -> False -> 전환
        assert _classify_fg_with_hysteresis(45, None, "fear") == "neutral"

    def test_just_below_buffer_44(self):
        # FG=44, 이전 fear -> 44 < 45 -> True -> fear 유지
        assert _classify_fg_with_hysteresis(44, None, "fear") == "fear"

    def test_no_previous(self):
        assert _classify_fg_with_hysteresis(50, None, None) == "neutral"

    def test_same_level(self):
        assert _classify_fg_with_hysteresis(50, None, "neutral") == "neutral"

    def test_extreme_fear_to_fear_boundary(self):
        # FG=21, 이전 extreme_fear -> 20+5=25, 21 < 25 -> extreme_fear 유지
        assert _classify_fg_with_hysteresis(21, None, "extreme_fear") == "extreme_fear"

    def test_extreme_fear_to_fear_clear(self):
        # FG=26, 이전 extreme_fear -> 26 >= 25 -> fear 전환
        assert _classify_fg_with_hysteresis(26, None, "extreme_fear") == "fear"

    def test_greed_to_extreme_greed_stay(self):
        # FG=81, 이전 greed -> 80+5=85, 81 < 85 -> greed 유지
        assert _classify_fg_with_hysteresis(81, None, "greed") == "greed"


class TestHysteresisBuffett:
    def test_up_stay(self):
        # 0.82, 이전 low -> 0.80+0.05=0.85, 0.82 < 0.85 -> low 유지
        assert _classify_buffett_with_hysteresis(0.82, "low") == "low"

    def test_up_clear(self):
        # 0.86, 이전 low -> 0.86 >= 0.85 -> normal 전환
        assert _classify_buffett_with_hysteresis(0.86, "low") == "normal"

    def test_down_stay(self):
        # 0.78, 이전 normal -> 0.80-0.05=0.75, 0.78 > 0.75 -> normal 유지
        assert _classify_buffett_with_hysteresis(0.78, "normal") == "normal"

    def test_down_pass(self):
        # 0.74, 이전 normal -> 0.74 < 0.75 -> low 전환
        assert _classify_buffett_with_hysteresis(0.74, "normal") == "low"

    def test_no_previous(self):
        assert _classify_buffett_with_hysteresis(1.0, None) == "normal"

    def test_same_level(self):
        assert _classify_buffett_with_hysteresis(1.0, "normal") == "normal"

    def test_normal_to_high_stay(self):
        # 1.22, 이전 normal -> 1.20+0.05=1.25, 1.22 < 1.25 -> normal 유지
        assert _classify_buffett_with_hysteresis(1.22, "normal") == "normal"

    def test_normal_to_high_clear(self):
        assert _classify_buffett_with_hysteresis(1.26, "normal") == "high"

    def test_high_to_extreme_stay(self):
        # 1.62, 이전 high -> 1.60+0.05=1.65, 1.62 < 1.65 -> high 유지
        assert _classify_buffett_with_hysteresis(1.62, "high") == "high"


# ── determine_regime (통합) ───────────────────────────────────

class TestDetermineRegime:
    def test_basic_accumulation(self):
        sentiment = {
            "buffett_indicator": {"ratio": 0.5},
            "fear_greed": {"score": 10},
            "vix": {"value": 20},
        }
        result = determine_regime(sentiment)
        assert result["regime"] == "accumulation"
        assert result["buffett_level"] == "low"
        assert result["fg_level"] == "extreme_fear"

    def test_vix_override(self):
        sentiment = {
            "buffett_indicator": {"ratio": 0.5},
            "fear_greed": {"score": 90},
            "vix": {"value": 36},
        }
        result = determine_regime(sentiment)
        # VIX>35 -> fg=extreme_fear, low+extreme_fear -> accumulation
        assert result["fg_level"] == "extreme_fear"
        assert result["regime"] == "accumulation"

    def test_buffett_percent_conversion(self):
        # 235.2(백분율) -> 2.352(소수) -> extreme
        sentiment = {
            "buffett_indicator": {"ratio": 235.2},
            "fear_greed": {"score": 50},
            "vix": 20,
        }
        result = determine_regime(sentiment)
        assert result["buffett_ratio"] == pytest.approx(2.352, abs=0.001)
        assert result["buffett_level"] == "extreme"

    def test_vix_dict_format(self):
        sentiment = {
            "buffett_indicator": {"ratio": 1.0},
            "fear_greed": {"score": 50},
            "vix": {"value": 25},
        }
        result = determine_regime(sentiment)
        assert result["vix"] == pytest.approx(25.0)

    def test_vix_float_format(self):
        sentiment = {
            "buffett_indicator": {"ratio": 1.0},
            "fear_greed": {"score": 50},
            "vix": 25,
        }
        result = determine_regime(sentiment)
        assert result["vix"] == pytest.approx(25.0)

    def test_fg_score_key(self):
        sentiment = {
            "buffett_indicator": {"ratio": 1.0},
            "fear_greed": {"score": 45},
            "vix": 20,
        }
        result = determine_regime(sentiment)
        assert result["fear_greed_score"] == pytest.approx(45.0)

    def test_fg_value_key(self):
        sentiment = {
            "buffett_indicator": {"ratio": 1.0},
            "fear_greed": {"value": 45},
            "vix": 20,
        }
        result = determine_regime(sentiment)
        assert result["fear_greed_score"] == pytest.approx(45.0)

    def test_returns_params(self):
        sentiment = {
            "buffett_indicator": {"ratio": 0.5},
            "fear_greed": {"score": 10},
            "vix": 20,
        }
        result = determine_regime(sentiment)
        assert result["params"] == REGIME_PARAMS["accumulation"]
        assert result["params"]["stock_max"] == 75
        assert result["params"]["single_cap"] == 5

    def test_returns_desc(self):
        sentiment = {
            "buffett_indicator": {"ratio": 0.5},
            "fear_greed": {"score": 10},
            "vix": 20,
        }
        result = determine_regime(sentiment)
        assert result["regime_desc"] == REGIME_DESC["accumulation"]
        assert "축적" in result["regime_desc"]

    def test_with_previous_regime(self):
        sentiment = {
            "buffett_indicator": {"ratio": 1.0},
            "fear_greed": {"score": 41},  # 경계값 근처
            "vix": 20,
        }
        result = determine_regime(sentiment, previous_regime="selective")
        # 하이스테리시스 적용 여부 검증 (경계 근처에서 이전 체제 유지 가능)
        assert result["regime"] in ("selective", "cautious")

    def test_fg_string_score(self):
        sentiment = {
            "buffett_indicator": {"ratio": 1.0},
            "fear_greed": {"score": "45"},
            "vix": 20,
        }
        result = determine_regime(sentiment)
        assert result["fear_greed_score"] == pytest.approx(45.0)

    def test_buffett_key_alias(self):
        # buffett 키도 지원
        sentiment = {
            "buffett": {"ratio": 0.5},
            "fear_greed": {"score": 10},
            "vix": 20,
        }
        result = determine_regime(sentiment)
        assert result["buffett_ratio"] == pytest.approx(0.5)

    def test_empty_sentiment(self):
        result = determine_regime({})
        # 모든 None -> buffett=normal, fg=neutral -> cautious
        assert result["regime"] == "cautious"

    def test_regime_params_completeness(self):
        for regime in ["accumulation", "selective", "cautious", "defensive"]:
            params = REGIME_PARAMS[regime]
            assert "margin" in params
            assert "stock_max" in params
            assert "cash_min" in params
            assert "single_cap" in params
