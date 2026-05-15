"""Phase 6 (보강) — donchian_swing YAML 외부 서버 호환성 추가 가드.

결함 B: 외부 preset 10개에 donchian_swing 미포함. YAML 커스텀 경로(`run_backtest_tool`) 사용.
`build_yaml("donchian_swing", ...)` 출력이 외부 `validate_yaml_tool` 통과 가능한 구조인지 검증.

본 테스트는 외부 서버 호출 안 함 — 정적 YAML 구조만 검증.
실제 외부 서버 호환성은 scripts/verify_mcp_response_schema.py 로 사후 확인.
"""
from __future__ import annotations

import pytest
import yaml

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# B1: donchian YAML 출력에 maximum + ema + atr 지표 모두 포함
# ---------------------------------------------------------------------------
def test_b1_donchian_yaml_includes_required_indicators():
    from src.engine.backtest_yaml import build_yaml

    yaml_str = build_yaml("donchian_swing", {})
    parsed = yaml.safe_load(yaml_str)
    indicator_ids = {ind["id"] for ind in parsed["strategy"]["indicators"]}
    assert "maximum" in indicator_ids, f"maximum 누락: {indicator_ids}"
    assert "ema" in indicator_ids, f"ema 누락: {indicator_ids}"
    assert "atr" in indicator_ids, f"atr 누락: {indicator_ids}"


# ---------------------------------------------------------------------------
# B2: risk.stop_loss / risk.trailing_stop 둘 다 양수 값 + enabled True
# ---------------------------------------------------------------------------
def test_b2_donchian_yaml_risk_section_complete():
    from src.engine.backtest_yaml import build_yaml

    yaml_str = build_yaml(
        "donchian_swing",
        {"stop_loss_rate": -7.0, "atr_trail_mult": 2.0, "atr_period": 14},
    )
    parsed = yaml.safe_load(yaml_str)
    risk = parsed["risk"]
    assert risk["stop_loss"]["enabled"] is True
    assert risk["stop_loss"]["percent"] > 0  # 양수 (음수 손절률 → 절대값)
    assert risk["trailing_stop"]["enabled"] is True
    assert risk["trailing_stop"]["percent"] > 0


# ---------------------------------------------------------------------------
# B3: YAML round-trip 파싱 OK + 외부 DSL 필수 필드 보존
# ---------------------------------------------------------------------------
def test_b3_donchian_yaml_roundtrip_safe():
    from src.engine.backtest_yaml import build_yaml

    yaml_str = build_yaml("donchian_swing", {})
    parsed = yaml.safe_load(yaml_str)
    redumped = yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True)
    reparsed = yaml.safe_load(redumped)
    # 외부 DSL 필수 키
    assert reparsed["version"] == "1.0.0"
    assert "metadata" in reparsed
    assert "strategy" in reparsed
    assert reparsed["strategy"]["id"] == "donchian_swing"
    assert "indicators" in reparsed["strategy"]
    assert "entry" in reparsed["strategy"]
    assert "exit" in reparsed["strategy"]


# ---------------------------------------------------------------------------
# B4: 결정성 — 동일 입력 두 번 호출 시 동일 문자열
# ---------------------------------------------------------------------------
def test_b4_donchian_yaml_deterministic():
    from src.engine.backtest_yaml import build_yaml

    params = {"donchian_period": 20, "long_ma_period": 60, "stop_loss_rate": -7.0}
    a = build_yaml("donchian_swing", params)
    b = build_yaml("donchian_swing", params)
    assert a == b


# ---------------------------------------------------------------------------
# B5: 사용자 override 가 YAML 에 반영 (donchian_period / long_ma_period)
# ---------------------------------------------------------------------------
def test_b5_donchian_yaml_user_params_override():
    from src.engine.backtest_yaml import build_yaml

    yaml_str = build_yaml(
        "donchian_swing",
        {"donchian_period": 30, "long_ma_period": 100},
    )
    parsed = yaml.safe_load(yaml_str)
    inds = {ind["alias"]: ind for ind in parsed["strategy"]["indicators"]}
    # maximum 의 period 가 30 으로 override 되어야 한다
    assert inds["donchian_high"]["params"]["period"] == 30
    # ema 의 period 가 100 으로 override 되어야 한다
    assert inds["ema_long"]["params"]["period"] == 100


# ---------------------------------------------------------------------------
# B6: cross_above 패턴 — 외부 DSL 표준 operator
# ---------------------------------------------------------------------------
def test_b6_donchian_entry_uses_cross_above_operator():
    """외부 서버 list_operators_tool 표준: cross_above / cross_below / greater_than / less_than."""
    from src.engine.backtest_yaml import build_yaml

    yaml_str = build_yaml("donchian_swing", {})
    parsed = yaml.safe_load(yaml_str)
    conds = parsed["strategy"]["entry"]["conditions"]
    operators = {c["operator"] for c in conds}
    # cross_above + greater_than 가 entry 에 모두 포함
    assert "cross_above" in operators
    assert "greater_than" in operators
