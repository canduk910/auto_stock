"""사이클 209 Red (AST/SAFETY) — max_breakout_extension_pct PARAM_RANGES 제외 + 청산 불변.

> 자문: `_workspace/domain_consult/cycle209_donchian_extension_gate.md`
> 선례: 사이클 208 (box 2키 PARAM_RANGES 제외 가드 패턴 답습)

G-209-2: recommendation_engine.PARAM_RANGES 에 max_breakout_extension_pct 부재
  (AI 자동튜닝 제외 — 진입 기준은 전략 정체성 상수, AI 과튜닝으로 0.5 조임 재발 차단).
  INT_PARAMS 무관 (float 이라 애초에 미등록 — 확인).
G-209-6: PARAM_RANGES 소스 텍스트에 부재 + donchian check_exit_signal 본체 미변경(SAFETY).
  extension 가드는 매수 진입(check_buy_signal)만 = 청산 무관 (사이클 38).

Red 유효성 (production 미변경 = PARAM_RANGES 에 max_breakout_extension_pct 잔존):
  - G-209-2 (키 부재 단언) = FAIL (현재 PARAM_RANGES L105 에 (0.5, 10.0) 잔존)
  - G-209-6 텍스트 부재 = FAIL (현재 잔존)
  - SAFETY check_exit_signal 존재 = PASS (extension 은 매수 게이트, 청산 무관)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_RECO = (
    Path(__file__).resolve().parents[3]
    / "src" / "engine" / "recommendation_engine.py"
)
_DONCHIAN = (
    Path(__file__).resolve().parents[3]
    / "src" / "engine" / "strategies" / "donchian_swing.py"
)

_PARAM = "max_breakout_extension_pct"


# ===========================================================================
# G-209-2 — PARAM_RANGES / INT_PARAMS 부재 (런타임 dict 기준)
# ===========================================================================
def test_g209_2_param_absent_from_param_ranges():
    """recommendation_engine.PARAM_RANGES 에 max_breakout_extension_pct 부재.

    Red: 현재 L105 `"max_breakout_extension_pct": (0.5, 10.0)` 잔존 → FAIL.
    """
    from src.engine.recommendation_engine import PARAM_RANGES
    assert _PARAM not in PARAM_RANGES, (
        f"PARAM_RANGES 에 '{_PARAM}' 잔존 금지 (사이클 209 AI 자동튜닝 제외 — "
        f"진입 기준 = 전략 정체성 상수, 0.5 과튜닝 재발 차단)"
    )


def test_g209_2_param_absent_from_int_params():
    """INT_PARAMS 무관 확인 — float 이라 애초에 미등록 (제거 후에도 부재)."""
    from src.engine.recommendation_engine import INT_PARAMS
    assert _PARAM not in INT_PARAMS, (
        f"'{_PARAM}' 은 float — INT_PARAMS 미등록 (제거 후에도 부재 유지)"
    )


# ===========================================================================
# G-209-6 (AST/SAFETY) — 소스 텍스트 부재 + 청산 경로 불변
# ===========================================================================
def test_g209_6_param_absent_from_param_ranges_dict_literal():
    """PARAM_RANGES dict 리터럴 키 목록에 max_breakout_extension_pct 부재 (AST).

    소스 텍스트 substring 이 아닌 PARAM_RANGES 할당의 dict 키 노드를 AST 로 검사
    (docstring/주석 언급 false-positive 차단, 사이클 208/167 패턴 답습).
    """
    src = _RECO.read_text(encoding="utf-8")
    tree = ast.parse(src)
    param_ranges_keys: list[str] = []
    for node in ast.walk(tree):
        # PARAM_RANGES: dict[...] = {...} 는 AnnAssign (타입 어노테이션 동반) —
        # plain Assign 과 AnnAssign 양쪽 포괄.
        value = None
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "PARAM_RANGES"
                   for t in node.targets):
                value = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "PARAM_RANGES":
                value = node.value
        if isinstance(value, ast.Dict):
            for k in value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    param_ranges_keys.append(k.value)
    assert param_ranges_keys, "PARAM_RANGES dict 리터럴 파싱 실패"
    assert _PARAM not in param_ranges_keys, (
        f"PARAM_RANGES dict 리터럴에 '{_PARAM}' 키 잔존 금지 (사이클 209 제거)"
    )


def test_g209_6_safety_check_exit_signal_unchanged():
    """SAFETY — donchian check_exit_signal 본체 존재 + 청산 로직 보존.

    extension 가드는 check_buy_signal(매수 진입 전, 사이클 38) 한정 →
    check_exit_signal / ATR 트레일링 / 손절 무관. 값/PARAM_RANGES 변경이
    청산 경로를 건드리지 않음을 정적 확인.
    """
    src = _DONCHIAN.read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                node.name == "check_exit_signal":
            found = True
            body = ast.get_source_segment(src, node) or ""
            assert "STOP_LOSS" in body or "TRAILING" in body or "stop_loss" in body, (
                "check_exit_signal 청산 로직 보존 의무"
            )
            # extension 가드 토큰은 매수 게이트 전용 — 청산 본체에 부재
            assert "max_breakout_extension_pct" not in body, (
                "check_exit_signal 에 extension 가드 토큰 부재 (매수 게이트 전용)"
            )
    assert found, "donchian check_exit_signal 정의 존재 의무"


def test_g209_6_safety_extension_gate_in_check_buy_signal():
    """SAFETY 반증 — extension 가드는 check_buy_signal 에만 존재 (매수 게이트 전용 확인)."""
    src = _DONCHIAN.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                node.name == "check_buy_signal":
            body = ast.get_source_segment(src, node) or ""
            assert "max_breakout_extension_pct" in body, (
                "extension 가드는 check_buy_signal 매수 게이트에 존재해야 함 "
                "(로직 제거가 아닌 값/튜닝만 변경)"
            )
            return
    raise AssertionError("donchian check_buy_signal 정의 부재")
