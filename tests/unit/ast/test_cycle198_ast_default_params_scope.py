"""사이클 198 (2026-07-09) — DEFAULT_PARAMS 변경 범위 AST 가드 (c 그룹).

명세: `_workspace/red/cycle198_bfb_flag_lookback_min.md`
자문 후속 검증 권고 #3: "BFB만 완화하는 TDD 사이클을 돌린다면 donchian·VCP
DEFAULT_PARAMS diff 0 을 AST 가드로 고정 (다른 전략 무변경 증명)."

영속 의무: 사이클 180 C.8 / 167 — **AST 토큰 기반** (정규식/텍스트 스캔 아닌 `ast` 모듈).
각 전략 모듈의 클래스-레벨 `DEFAULT_PARAMS = {...}` dict 리터럴을 파싱해
key→value 맵으로 환원한 뒤 단언한다. 주석/docstring 은 AST 노드가 아니므로 자연 무시.

가드 ID:
- G-198-SCOPE-1: donchian DEFAULT_PARAMS 에 `flag_lookback_min` 키 부재 (BFB 전용 키).
- G-198-SCOPE-2: vcp DEFAULT_PARAMS 에 `flag_lookback_min` 키 부재.
- G-198-SCOPE-3: donchian 대표 키 불변 (사이클 198 이 donchian 파라미터 무변경).
- G-198-SCOPE-4: vcp 대표 키 불변 (사이클 198 이 vcp 파라미터 무변경).
- G-198-SCOPE-5 (self-test): BFB DEFAULT_PARAMS 에 `flag_lookback_min` 키 존재 (탐지기 검증).

본 파일 전체는 min=3/min=2 양쪽 PASH (불변식) — Red 아님. 사이클 198 이 BFB 외
전략 파라미터를 건드리지 않음을 고정하는 회귀 가드.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
_STRAT_DIR = REPO_ROOT / "src" / "engine" / "strategies"
_BFB_PY = _STRAT_DIR / "bull_flag_breakout.py"
_DONCHIAN_PY = _STRAT_DIR / "donchian_swing.py"
_VCP_PY = _STRAT_DIR / "vcp_breakout.py"


# ---------------------------------------------------------------------------
# AST 헬퍼 — 클래스-레벨 `DEFAULT_PARAMS = {...}` dict 리터럴 → {key: value_node}
# ---------------------------------------------------------------------------
def _extract_default_params(module_path: Path) -> dict[str, ast.AST]:
    """모듈에서 `DEFAULT_PARAMS = {dict-literal}` 을 찾아 key→value AST 노드 맵 반환.

    문자열 키(ast.Constant str) 만 대상. `**expr` 언패킹은 무시.
    docstring/주석은 AST 노드가 아니므로 자연 무시 (사이클 167 교훈).
    """
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        # 클래스 본문의 `DEFAULT_PARAMS = {...}` (Assign, single target Name)
        if not isinstance(node, ast.Assign):
            continue
        targets = node.targets
        if len(targets) != 1:
            continue
        tgt = targets[0]
        if not (isinstance(tgt, ast.Name) and tgt.id == "DEFAULT_PARAMS"):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        result: dict[str, ast.AST] = {}
        for k, v in zip(node.value.keys, node.value.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                result[k.value] = v
        return result
    raise AssertionError(f"{module_path.name} 에 DEFAULT_PARAMS dict 리터럴이 없음")


def _literal(node: ast.AST):
    """AST value 노드를 파이썬 리터럴로 환원 (숫자/문자/None/음수/list)."""
    return ast.literal_eval(node)


# ===========================================================================
# G-198-SCOPE-1 — donchian 에 flag_lookback_min 키 부재 (BFB 전용 키)
# ===========================================================================
def test_g198_scope_1_donchian_no_flag_lookback_min():
    params = _extract_default_params(_DONCHIAN_PY)
    assert "flag_lookback_min" not in params, (
        "donchian_swing DEFAULT_PARAMS 는 flag_lookback_min 키를 가지면 안 됨 "
        "(BFB 전용). 사이클 198 이 donchian 을 건드리지 않음."
    )


# ===========================================================================
# G-198-SCOPE-2 — vcp 에 flag_lookback_min 키 부재
# ===========================================================================
def test_g198_scope_2_vcp_no_flag_lookback_min():
    params = _extract_default_params(_VCP_PY)
    assert "flag_lookback_min" not in params, (
        "vcp_breakout DEFAULT_PARAMS 는 flag_lookback_min 키를 가지면 안 됨. "
        "사이클 198 이 vcp 를 건드리지 않음."
    )


# ===========================================================================
# G-198-SCOPE-3 — donchian 대표 키 불변 (파라미터 무변경 증명)
# ===========================================================================
def test_g198_scope_3_donchian_representative_keys_unchanged():
    params = _extract_default_params(_DONCHIAN_PY)
    expected = {
        "donchian_period": 20,
        "long_ma_period": 60,
        "volume_multiplier": 1.5,
        "stop_loss_rate": -7.0,
        "breakout_fail_n_days": 5,
    }
    for key, val in expected.items():
        assert key in params, f"donchian DEFAULT_PARAMS 에 {key} 키가 있어야 함"
        assert _literal(params[key]) == val, (
            f"donchian {key} 는 사이클 198 에서 불변({val})이어야 함. "
            f"실제={_literal(params[key])}"
        )


# ===========================================================================
# G-198-SCOPE-4 — vcp 대표 키 불변 (파라미터 무변경 증명)
# ===========================================================================
def test_g198_scope_4_vcp_representative_keys_unchanged():
    params = _extract_default_params(_VCP_PY)
    expected = {
        "ema_short": 50,
        "ema_mid": 60,
        "ema_long": 120,
        "base_min_days": 25,
        "base_max_days": 75,
        "pullback_count_min": 2,
        "pullback_count_max": 4,
        "last_pullback_max": 0.12,
        "volume_contraction_ratio": 0.70,
        "breakout_volume_mult": 1.5,
    }
    for key, val in expected.items():
        assert key in params, f"vcp DEFAULT_PARAMS 에 {key} 키가 있어야 함"
        assert _literal(params[key]) == val, (
            f"vcp {key} 는 사이클 198 에서 불변({val})이어야 함. "
            f"실제={_literal(params[key])}"
        )


# ===========================================================================
# G-198-SCOPE-5 (self-test) — BFB 에 flag_lookback_min 키 존재 (탐지기 검증)
# ===========================================================================
def test_g198_scope_5_bfb_has_flag_lookback_min():
    """탐지기 self-test — BFB DEFAULT_PARAMS 에는 flag_lookback_min 키가 존재.

    _extract_default_params 가 실제로 BFB 딕셔너리를 파싱함을 검증
    (false-negative 방어). 값 자체는 여기서 단언하지 않음 (완화 전/후 3↔2 변동).
    """
    params = _extract_default_params(_BFB_PY)
    assert "flag_lookback_min" in params, (
        "BFB DEFAULT_PARAMS 는 flag_lookback_min 키를 가져야 함 (탐지기 검증)."
    )
    # 값은 정수 리터럴이어야 함 (완화 전 3 / 완화 후 2)
    assert isinstance(_literal(params["flag_lookback_min"]), int)
