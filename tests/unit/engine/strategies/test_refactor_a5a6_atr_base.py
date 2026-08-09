"""refactor-review A5·A6 (2026-08-09) — `_rederive_entry_atr`·`_atr` base 승격 회귀 가드.

전략 파일에 정의가 남으면 드리프트 재발 → base 위임만 허용 (H-1
`test_no_duplicate_helper_definition_in_strategy_files` 미러). kojiro 는 Wilder ATR
(kojiro_indicators.atr) 전용이라 base SMA `_atr` 을 절대 사용하지 않는다(ATR 이원화 봉인).
"""
import ast
from pathlib import Path

from src.engine.strategy_base import StrategyBase
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.donchian_swing import DonchianSwingStrategy

_STRAT_DIR = Path(__file__).resolve().parents[4] / "src" / "engine" / "strategies"


def _defs_in_strategy_files(name: str) -> list[str]:
    offenders = []
    for path in sorted(_STRAT_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                offenders.append(f"{path.name}:{node.lineno}")
    return offenders


def test_no_duplicate_rederive_entry_atr_definition():
    """`_rederive_entry_atr` 정의는 StrategyBase 단독 — 전략 파일 잔존 0."""
    assert not _defs_in_strategy_files("_rederive_entry_atr"), (
        f"A5: _rederive_entry_atr 정의는 base 단독 — 잔존 {_defs_in_strategy_files('_rederive_entry_atr')}"
    )


def test_no_duplicate_sma_atr_definition():
    """SMA `_atr` 정의는 StrategyBase 단독 — 전략 파일 잔존 0."""
    assert not _defs_in_strategy_files("_atr"), (
        f"A6: _atr 정의는 base 단독 — 잔존 {_defs_in_strategy_files('_atr')}"
    )


def test_kojiro_does_not_use_sma_atr():
    """kojiro 는 self._atr 을 쓰지 않는다 — Wilder ATR(kojiro_indicators) 전용 봉인."""
    src = (_STRAT_DIR / "kojiro.py").read_text(encoding="utf-8")
    assert "self._atr(" not in src, "kojiro 는 base SMA _atr 사용 금지 (ATR 이원화)"


def test_base_has_atr_and_rederive():
    """base 에 _atr(static) + _rederive_entry_atr + _ENTRY_ATR_REDERIVE_LABEL 존재."""
    assert "_atr" in StrategyBase.__dict__
    assert "_rederive_entry_atr" in StrategyBase.__dict__
    assert hasattr(StrategyBase, "_ENTRY_ATR_REDERIVE_LABEL")
    assert StrategyBase._ENTRY_ATR_REDERIVE_LABEL is None  # base 기본값


def test_entry_atr_log_prefix_labels_preserved():
    """로그 접두사 보존 — [vcp/bfb/donchian_entry_atr_rederive] 운영자 grep 이력 단절 방지."""
    assert VcpBreakoutStrategy._ENTRY_ATR_REDERIVE_LABEL == "vcp"
    assert BullFlagBreakoutStrategy._ENTRY_ATR_REDERIVE_LABEL == "bfb"
    assert DonchianSwingStrategy._ENTRY_ATR_REDERIVE_LABEL == "donchian"


def test_sma_atr_byte_equivalent_behavior():
    """base _atr 이 승격 전 3벌과 동일 산식(SMA True Range) — 결정적 값."""
    highs = [110, 108, 107, 105, 106]
    lows = [100, 101, 102, 100, 101]
    closes = [105, 104, 103, 102, 103]
    # period=2: TR[0]=max(110-100,|110-104|,|100-104|)=10, TR[1]=max(108-101,|108-103|,|101-103|)=7 → (10+7)/2=8.5
    assert StrategyBase._atr(highs, lows, closes, 2) == 8.5
    # 봉 부족 → 0.0
    assert StrategyBase._atr([1, 2], [1, 2], [1, 2], 5) == 0.0
