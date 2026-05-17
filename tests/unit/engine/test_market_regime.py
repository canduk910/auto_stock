"""src/engine/market_regime.py 단위 테스트 (사이클 2 — 시장 레짐 필터).

복합 임계 매수 가드 + cash_usage_ratio 자동 산출.

- 복합 임계 OR: regime=defensive OR vix>25 OR fear_greed>85 OR fear_greed<15
- cash_usage_ratio_from_regime(cash_min) = clamp((100 - cash_min) / 100, 0.0, 1.0)
- regime 정보 없음 → True (graceful fallback)
- auto_regime_adjust=False 시 cash_usage_ratio 변경 안 함 (호출자 결정)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _make_regime(
    *,
    regime: str = "aggressive",
    vix: float = 15.0,
    fear_greed_score: float = 50.0,
    cash_min: int = 20,
    buffett_ratio: float = 254.0,
    cycle_phase: str = "expansion",
) -> "MarketRegime":  # noqa: F821
    from src.engine.market_regime import MarketRegime

    return MarketRegime(
        regime=regime,
        regime_desc=f"테스트 {regime}",
        cycle_phase=cycle_phase,
        vix=vix,
        fear_greed_score=fear_greed_score,
        buffett_ratio=buffett_ratio,
        cash_min=cash_min,
        raw={},
    )


# ---------------------------------------------------------------------------
# B2-A: 모든 조건 안전 → True
# ---------------------------------------------------------------------------
def test_b2a_aggressive_low_vix_neutral_fg_allows_buy():
    mr = _make_regime(regime="aggressive", vix=15.0, fear_greed_score=50.0)
    assert mr.is_buy_allowed("momentum") is True
    assert mr.block_reason is None


# ---------------------------------------------------------------------------
# B2-B: regime=defensive → False
# ---------------------------------------------------------------------------
def test_b2b_defensive_blocks_buy():
    mr = _make_regime(regime="defensive", vix=15.0, fear_greed_score=50.0)
    assert mr.is_buy_allowed("momentum") is False
    assert mr.block_reason is not None
    assert "defensive" in mr.block_reason.lower()


# ---------------------------------------------------------------------------
# B2-C: vix > 25 → False
# ---------------------------------------------------------------------------
def test_b2c_high_vix_blocks_buy():
    mr = _make_regime(regime="aggressive", vix=26.0, fear_greed_score=50.0)
    assert mr.is_buy_allowed("momentum") is False
    assert "vix" in mr.block_reason.lower()


# ---------------------------------------------------------------------------
# B2-D: fear_greed > 85 → False (극도 탐욕)
# ---------------------------------------------------------------------------
def test_b2d_extreme_greed_blocks_buy():
    mr = _make_regime(regime="aggressive", vix=15.0, fear_greed_score=86.0)
    assert mr.is_buy_allowed("momentum") is False
    assert "fear_greed" in mr.block_reason.lower() or "탐욕" in mr.block_reason


# ---------------------------------------------------------------------------
# B2-E: fear_greed < 15 → False (극도 공포)
# ---------------------------------------------------------------------------
def test_b2e_extreme_fear_blocks_buy():
    mr = _make_regime(regime="aggressive", vix=15.0, fear_greed_score=14.0)
    assert mr.is_buy_allowed("momentum") is False
    assert "fear_greed" in mr.block_reason.lower() or "공포" in mr.block_reason


# ---------------------------------------------------------------------------
# B2-F: regime 정보 없음 (None) → True (graceful)
# ---------------------------------------------------------------------------
def test_b2f_none_regime_allows_buy_graceful():
    from src.engine.market_regime import MarketRegime

    mr = MarketRegime.empty()
    # 외부 fetch 실패 / DKSTOCK 비활성 — 기존 동작 유지 (매수 허용)
    assert mr.is_buy_allowed("momentum") is True
    assert mr.is_buy_allowed("volatility_breakout") is True
    assert mr.block_reason is None


# ---------------------------------------------------------------------------
# B2-G: cash_usage_ratio_from_regime — cash_min=75 → 0.25, 50 → 0.5, 20 → 0.8
# ---------------------------------------------------------------------------
def test_b2g_cash_usage_ratio_from_regime():
    from src.engine.market_regime import cash_usage_ratio_from_regime

    assert cash_usage_ratio_from_regime(75) == pytest.approx(0.25, abs=0.01)
    assert cash_usage_ratio_from_regime(50) == pytest.approx(0.5, abs=0.01)
    assert cash_usage_ratio_from_regime(20) == pytest.approx(0.8, abs=0.01)
    assert cash_usage_ratio_from_regime(0) == pytest.approx(1.0, abs=0.01)
    assert cash_usage_ratio_from_regime(100) == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# B2-H: clamp [0.0, 1.0]
# ---------------------------------------------------------------------------
def test_b2h_cash_usage_ratio_clamp():
    from src.engine.market_regime import cash_usage_ratio_from_regime

    # cash_min < 0 → ratio > 1 → clamp to 1.0
    assert cash_usage_ratio_from_regime(-50) == 1.0
    # cash_min > 100 → ratio < 0 → clamp to 0.0
    assert cash_usage_ratio_from_regime(150) == 0.0


# ---------------------------------------------------------------------------
# 모든 전략에 동일 적용 (전략별 차등 X)
# ---------------------------------------------------------------------------
def test_b2_all_strategies_share_same_decision():
    mr = _make_regime(regime="defensive")
    for sid in ("momentum", "volatility_breakout", "long_tail_volatility", "donchian_swing", "bull_flag_breakout", "vcp_breakout"):
        assert mr.is_buy_allowed(sid) is False


def test_b2_empty_regime_to_dict_safe():
    """프론트 노출용 dict 직렬화가 빈 레짐에서도 안전한지 (None 키 누락 X)."""
    from src.engine.market_regime import MarketRegime

    mr = MarketRegime.empty()
    d = mr.to_dict()
    assert d["regime"] is None
    assert d["buy_blocked"] is False
    assert d["block_reason"] is None
