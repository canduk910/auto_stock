"""사이클 211 (2026-07-15) — DEFAULT_PARAMS 변경 범위 AST 가드 (G-211-4).

명세: `_workspace/red/cycle211_bfb_flag_retracement.md`
사이클 198/208/209 답습 — 단일 파라미터 완화 시 다른 전략 DEFAULT_PARAMS diff 0
+ 매수 진입 임계(flag_retracement) 가 청산(check_exit_signal) 경로에 누출되지 않음을 고정.

영속 의무: 사이클 180 C.8 / 167 — **AST 토큰 기반** (정규식/텍스트 스캔 아닌 `ast` 모듈).
각 전략 모듈의 클래스-레벨 `DEFAULT_PARAMS = {...}` dict 리터럴을 파싱해
key→value 맵으로 환원한 뒤 단언한다. 주석/docstring 은 AST 노드가 아니므로 자연 무시.

가드 ID:
- G-211-SCOPE-1: donchian DEFAULT_PARAMS 에 `flag_retracement_max` 키 부재 (BFB 전용 키).
- G-211-SCOPE-2: vcp DEFAULT_PARAMS 에 `flag_retracement_max` 키 부재.
- G-211-SCOPE-3: donchian 대표 키 불변 (사이클 211 이 donchian 파라미터 무변경).
- G-211-SCOPE-4: vcp 대표 키 불변 (사이클 211 이 vcp 파라미터 무변경).
- G-211-SCOPE-5 (self-test): BFB DEFAULT_PARAMS 에 `flag_retracement_max` 키 존재 (탐지기 검증).
- G-211-SAFETY-1: BFB `check_exit_signal` 본체가 `flag_retracement_max` 를 참조하지 않음
  (매수 진입 임계 = prepare/검출 전용, 청산 hot path 불변 — 사이클 38 명문화).

본 파일 전체는 0.382/0.5 양쪽 PASS (불변식) — Red 아님. 사이클 211 이 BFB 외
전략 파라미터 + 청산 경로를 건드리지 않음을 고정하는 회귀 가드.
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


def _find_function(module_path: Path, func_name: str) -> ast.AST:
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return node
    raise AssertionError(f"{module_path.name} 에 {func_name} 함수가 없음")


def _string_constants(node: ast.AST) -> set[str]:
    """서브트리 내 문자열 리터럴(dict key 접근 등) 전수 수집."""
    found: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            found.add(n.value)
    return found


# ===========================================================================
# G-211-SCOPE-1 — donchian 에 flag_retracement_max 키 부재 (BFB 전용 키)
# ===========================================================================
def test_g211_scope_1_donchian_no_flag_retracement_max():
    params = _extract_default_params(_DONCHIAN_PY)
    assert "flag_retracement_max" not in params, (
        "donchian_swing DEFAULT_PARAMS 는 flag_retracement_max 키를 가지면 안 됨 "
        "(BFB 전용). 사이클 211 이 donchian 을 건드리지 않음."
    )


# ===========================================================================
# G-211-SCOPE-2 — vcp 에 flag_retracement_max 키 부재
# ===========================================================================
def test_g211_scope_2_vcp_no_flag_retracement_max():
    params = _extract_default_params(_VCP_PY)
    assert "flag_retracement_max" not in params, (
        "vcp_breakout DEFAULT_PARAMS 는 flag_retracement_max 키를 가지면 안 됨. "
        "사이클 211 이 vcp 를 건드리지 않음."
    )


# ===========================================================================
# G-211-SCOPE-3 — donchian 대표 키 불변 (파라미터 무변경 증명)
# ===========================================================================
def test_g211_scope_3_donchian_representative_keys_unchanged():
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
            f"donchian {key} 는 사이클 211 에서 불변({val})이어야 함. "
            f"실제={_literal(params[key])}"
        )


# ===========================================================================
# G-211-SCOPE-4 — vcp 대표 키 불변 (파라미터 무변경 증명)
# ===========================================================================
def test_g211_scope_4_vcp_representative_keys_unchanged():
    params = _extract_default_params(_VCP_PY)
    expected = {
        "ema_short": 50,
        "ema_mid": 60,
        "ema_long": 120,
        "base_min_days": 25,
        "base_max_days": 75,
        "last_pullback_max": 0.12,
        "volume_contraction_ratio": 0.70,
        "breakout_volume_mult": 1.5,
    }
    for key, val in expected.items():
        assert key in params, f"vcp DEFAULT_PARAMS 에 {key} 키가 있어야 함"
        assert _literal(params[key]) == val, (
            f"vcp {key} 는 사이클 211 에서 불변({val})이어야 함. "
            f"실제={_literal(params[key])}"
        )


# ===========================================================================
# G-211-SCOPE-5 (self-test) — BFB 에 flag_retracement_max 키 존재 (탐지기 검증)
# ===========================================================================
def test_g211_scope_5_bfb_has_flag_retracement_max():
    """탐지기 self-test — BFB DEFAULT_PARAMS 에는 flag_retracement_max 키가 존재.

    _extract_default_params 가 실제로 BFB 딕셔너리를 파싱함을 검증
    (false-negative 방어). 값 자체는 여기서 단언하지 않음 (완화 전/후 0.382↔0.5 변동).
    """
    params = _extract_default_params(_BFB_PY)
    assert "flag_retracement_max" in params, (
        "BFB DEFAULT_PARAMS 는 flag_retracement_max 키를 가져야 함 (탐지기 검증)."
    )
    assert isinstance(_literal(params["flag_retracement_max"]), float)


# ===========================================================================
# G-211-SAFETY-1 — check_exit_signal 본체가 flag_retracement_max 미참조 (청산 불변)
# ===========================================================================
def test_g211_safety_1_check_exit_signal_no_flag_retracement():
    """BFB `check_exit_signal` 본체가 `flag_retracement_max` 를 참조하지 않음.

    flag_retracement_max 는 매수 진입 임계 = prepare/검출(`_detect_pole_and_flag_detailed`)
    전용. 청산 hot path (손절/플래그 하단/트레일링) 에 누출되지 않음을 고정
    (사이클 38 명문화 — tradable_boards/진입 임계는 매수 진입 전용).
    """
    func = _find_function(_BFB_PY, "check_exit_signal")
    strings = _string_constants(func)
    assert "flag_retracement_max" not in strings, (
        "check_exit_signal 본체는 flag_retracement_max 를 참조하면 안 됨 "
        "(진입 임계가 청산 경로에 누출 = 사이클 38 위반). "
        f"발견된 문자열 상수 중 flag_retracement_max 존재."
    )
    # self-test — 탐지기가 실제로 check_exit_signal 을 파싱함 (알려진 청산 키 존재)
    assert "stop_loss_rate" in strings, (
        "탐지기 검증 — check_exit_signal 은 stop_loss_rate 를 참조해야 함 "
        f"(false-negative 방어). 발견 문자열={sorted(strings)}"
    )
