"""Phase 2 Red — `src/engine/backtest_yaml.py` 전략별 YAML 변환.

6 전략을 외부 백테스트 서버(MCP) YAML DSL 로 매핑한다.
YAML DSL 표현력 한계로 정확 매핑은 불가능 — **근사 매핑** 또는 **`BacktestNotSupportedError`** 명시 raise.

표현력 평가:
- momentum: ROC(1) > buy_threshold + risk.stop_loss. **(a) 근사 가능**.
- volatility_breakout: maximum(high, k)+ATR 근사 + stop_loss. **(a) 근사 가능**.
- donchian_swing: maximum(high, 20) + EMA(60) + trailing_stop. **(a) 가능 (가장 정합)**.
- long_tail_volatility: 상한가 모드 전환 미지원. **(b) BacktestNotSupportedError**.
- bull_flag_breakout: 폴/플래그 패턴 검출 미지원. **(b) BacktestNotSupportedError**.
- vcp_breakout: 베이스 수축 패턴 미지원. **(b) BacktestNotSupportedError**.

요구 행위:
1. `build_yaml(strategy_id, params) -> str` — (a) 3 전략 케이스에서 유효 YAML 문자열.
2. (b) 3 전략에서는 `BacktestNotSupportedError` raise.
3. 동일 입력 → 일관된 출력 (snapshot 안정성).
4. params 미지정 시 strategy DEFAULT_PARAMS 사용.
"""

from __future__ import annotations

import pytest
import yaml

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# (a) 외부 YAML 근사 매핑 — 3 전략
# ---------------------------------------------------------------------------
def test_build_yaml_momentum_emits_valid_yaml_with_roc_indicator():
    """momentum: ROC(1) > buy_threshold 매핑.

    외부 서버 list_indicators_tool 에 `roc` 가 있음 — ROC(1) 가 전일대비 변화율.
    """
    from src.engine.backtest_yaml import build_yaml

    yaml_str = build_yaml(
        "momentum",
        {"buy_threshold": 29.0, "stop_loss_rate": -7.5, "trailing_stop_rate": -2.0},
    )

    parsed = yaml.safe_load(yaml_str)
    assert parsed["version"] == "1.0.0"
    assert parsed["strategy"]["id"] == "momentum"
    # ROC 지표가 포함되어야 한다
    indicator_ids = [ind["id"] for ind in parsed["strategy"]["indicators"]]
    assert "roc" in indicator_ids
    # entry 에 임계치 29 가 들어가야 한다
    entry_conds = parsed["strategy"]["entry"]["conditions"]
    threshold_used = any(
        c.get("value") == 29.0 or c.get("value") == 29 for c in entry_conds
    )
    assert threshold_used, f"buy_threshold 29.0 이 conditions 에 반영 안 됨: {entry_conds}"
    # stop_loss 가 risk 에 들어가야 한다 (절대값)
    assert parsed["risk"]["stop_loss"]["enabled"] is True
    assert parsed["risk"]["stop_loss"]["percent"] == 7.5


def test_build_yaml_volatility_breakout_uses_atr_and_stop_loss():
    """volatility_breakout: ATR 기반 변동성 + stop_loss 3%."""
    from src.engine.backtest_yaml import build_yaml

    yaml_str = build_yaml(
        "volatility_breakout",
        {"k_value_krx_main": 0.5, "stop_loss_rate": -3.0, "k_period": 20},
    )

    parsed = yaml.safe_load(yaml_str)
    assert parsed["strategy"]["id"] == "volatility_breakout"
    indicator_ids = [ind["id"] for ind in parsed["strategy"]["indicators"]]
    # 변동성 돌파 근사 — ATR 또는 maximum 기반
    assert any(i in indicator_ids for i in ["atr", "maximum"])
    # stop_loss 절대값 3.0
    assert parsed["risk"]["stop_loss"]["enabled"] is True
    assert parsed["risk"]["stop_loss"]["percent"] == 3.0


def test_build_yaml_donchian_swing_uses_maximum_and_ema_and_trailing():
    """donchian_swing: maximum(high, 20) + EMA(60) + trailing_stop."""
    from src.engine.backtest_yaml import build_yaml

    yaml_str = build_yaml(
        "donchian_swing",
        {
            "donchian_period": 20,
            "long_ma_period": 60,
            "stop_loss_rate": -7.0,
            "atr_trail_mult": 2.0,
            "atr_period": 14,
        },
    )

    parsed = yaml.safe_load(yaml_str)
    assert parsed["strategy"]["id"] == "donchian_swing"
    indicator_ids = [ind["id"] for ind in parsed["strategy"]["indicators"]]
    # 20일 신고가 + 60일 EMA 모두 표현
    assert "maximum" in indicator_ids or "donchian" in indicator_ids
    assert "ema" in indicator_ids
    # 하드 손절 + ATR 트레일링
    assert parsed["risk"]["stop_loss"]["percent"] == 7.0
    assert parsed["risk"]["trailing_stop"]["enabled"] is True


def test_build_yaml_stable_across_runs():
    """동일 입력 → 동일 YAML 출력 (snapshot 안정성)."""
    from src.engine.backtest_yaml import build_yaml

    params = {"buy_threshold": 29.0, "stop_loss_rate": -7.5}
    y1 = build_yaml("momentum", params)
    y2 = build_yaml("momentum", params)
    assert y1 == y2


def test_build_yaml_uses_defaults_when_params_missing():
    """params 누락 시 strategy DEFAULT_PARAMS 사용 — 빈 dict 도 유효 YAML 생성."""
    from src.engine.backtest_yaml import build_yaml

    yaml_str = build_yaml("momentum", {})
    parsed = yaml.safe_load(yaml_str)
    assert parsed["strategy"]["id"] == "momentum"
    # DEFAULT_PARAMS 의 buy_threshold=29.0 이 자동 사용되어야 한다
    entry_conds = parsed["strategy"]["entry"]["conditions"]
    threshold_used = any(
        c.get("value") in (29.0, 29) for c in entry_conds
    )
    assert threshold_used


# ---------------------------------------------------------------------------
# (b) 로컬 어댑터 폴백 — 3 전략 BacktestNotSupportedError
# ---------------------------------------------------------------------------
def test_build_yaml_long_tail_volatility_raises_not_supported():
    """LTV: 상한가 모드 전환은 YAML DSL 미지원 — 명시 raise."""
    from src.engine.backtest_yaml import build_yaml
    from src.services.exceptions import BacktestNotSupportedError

    with pytest.raises(BacktestNotSupportedError) as exc:
        build_yaml("long_tail_volatility", {})
    assert "long_tail_volatility" in str(exc.value)


def test_build_yaml_bull_flag_breakout_raises_not_supported():
    """bull_flag_breakout: 폴/플래그 패턴 검출 미지원."""
    from src.engine.backtest_yaml import build_yaml
    from src.services.exceptions import BacktestNotSupportedError

    with pytest.raises(BacktestNotSupportedError) as exc:
        build_yaml("bull_flag_breakout", {})
    assert "bull_flag_breakout" in str(exc.value)


def test_build_yaml_vcp_breakout_raises_not_supported():
    """vcp_breakout: 베이스 수축 패턴 미지원."""
    from src.engine.backtest_yaml import build_yaml
    from src.services.exceptions import BacktestNotSupportedError

    with pytest.raises(BacktestNotSupportedError) as exc:
        build_yaml("vcp_breakout", {})
    assert "vcp_breakout" in str(exc.value)


# ---------------------------------------------------------------------------
# (c) 미지원 전략 ID
# ---------------------------------------------------------------------------
def test_build_yaml_unknown_strategy_raises():
    """알 수 없는 strategy_id 는 BacktestNotSupportedError (안전한 graceful degrade)."""
    from src.engine.backtest_yaml import build_yaml
    from src.services.exceptions import BacktestNotSupportedError

    with pytest.raises(BacktestNotSupportedError):
        build_yaml("nonexistent_strategy", {})
