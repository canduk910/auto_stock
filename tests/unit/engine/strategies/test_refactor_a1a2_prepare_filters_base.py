"""refactor-review A1·A2 (2026-08-09) — prepare 필터 2메서드 base 승격 회귀 가드.

`_apply_price_filter_in_prepare`(A1)·`_apply_master_block_filter_in_prepare`(A2) 를
StrategyBase 로 승격. 5 전략(vb/ltv/donchian/bfb/vcp)은 자체 정의 금지(상속). 로그
접두사는 `_PREPARE_LOG_LABEL`(vb/ltv/dc/bfb/vcp)로 보존. ⚠️ kojiro 는 FREEZE(N=1)라
자체 정의 유지(override) — 승격 대상 제외.
"""
import ast
from pathlib import Path

from src.engine.strategy_base import StrategyBase
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

_REPO = Path(__file__).resolve().parents[4]
_STRAT_DIR = _REPO / "src" / "engine" / "strategies"
_METHODS = ("_apply_price_filter_in_prepare", "_apply_master_block_filter_in_prepare")
# 승격 대상 5 전략 (kojiro 제외 — FREEZE, 자체 override 유지)
_TARGET_FILES = {
    "vb": "volatility_breakout.py",
    "ltv": "long_tail_volatility.py",
    "dc": "donchian_swing.py",
    "bfb": "bull_flag_breakout.py",
    "vcp": "vcp_breakout.py",
}
_EXPECTED_LABELS = {
    VolatilityBreakoutStrategy: "vb",
    LongTailVolatilityStrategy: "ltv",
    DonchianSwingStrategy: "dc",
    BullFlagBreakoutStrategy: "bfb",
    VcpBreakoutStrategy: "vcp",
}


def _local_defs(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        n.name for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name in _METHODS
    }


def test_base_defines_both_prepare_filters():
    """base 가 두 메서드 + _PREPARE_LOG_LABEL 정의."""
    assert "_apply_price_filter_in_prepare" in StrategyBase.__dict__
    assert "_apply_master_block_filter_in_prepare" in StrategyBase.__dict__
    assert hasattr(StrategyBase, "_PREPARE_LOG_LABEL")
    assert StrategyBase._PREPARE_LOG_LABEL is None  # base 기본값


def test_target_strategies_no_local_definition():
    """5 전략(kojiro 제외) 자체 정의 금지 — base 상속만 (드리프트 차단)."""
    offenders = {}
    for label, fname in _TARGET_FILES.items():
        local = _local_defs(_STRAT_DIR / fname)
        if local:
            offenders[label] = local
    assert not offenders, f"A1·A2: 5 전략 자체 정의 금지 (base 상속) — {offenders}"


def test_kojiro_keeps_own_definitions_freeze():
    """kojiro 는 FREEZE(N=1)라 자체 정의 유지 (승격 제외 — override)."""
    local = _local_defs(_STRAT_DIR / "kojiro.py")
    assert local == set(_METHODS), (
        f"kojiro 는 두 메서드 자체 정의 유지 의무(FREEZE) — 실제 {local}"
    )


def test_prepare_log_labels_preserved():
    """로그 접두사 보존 — [vb/ltv/dc/bfb/vcp_price_filter_prepare] 운영자 grep 이력."""
    for cls, expected in _EXPECTED_LABELS.items():
        assert cls._PREPARE_LOG_LABEL == expected, (
            f"{cls.__name__} _PREPARE_LOG_LABEL={cls._PREPARE_LOG_LABEL} != {expected}"
        )


def test_strategies_inherit_prepare_filters():
    """5 전략이 base 메서드를 상속(callable) — 호출 site 계약 보존."""
    for cls in _EXPECTED_LABELS:
        assert hasattr(cls, "_apply_price_filter_in_prepare")
        assert hasattr(cls, "_apply_master_block_filter_in_prepare")
