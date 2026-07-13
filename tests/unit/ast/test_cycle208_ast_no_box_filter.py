"""사이클 208 Red (AST/SAFETY) — donchian prepare 박스 필터 토큰 영구 부재.

> 자문: `_workspace/domain_consult/cycle_donchian_box_contraction.md`

G-208-6: donchian_swing.py prepare 영역에 박스 수축 필터 토큰
(`box_range` / `max_box_vol` / `box_contraction`) 잔존 0건 (미래 재도입 영구 차단).

+ 매매 안전성 (SAFETY 불변식): 필터 제거는 prepare(매수 진입 전, 사이클 38) 한정 →
  check_exit_signal / 청산 / 손절 무관. donchian check_exit_signal 본체 미변경 확인.

Red 유효성 (production 미변경):
  - G-208-6 토큰 부재 = FAIL (현재 코드에 토큰 잔존)
  - SAFETY 불변식 (check_exit_signal 존재) = PASS
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_DONCHIAN = (
    Path(__file__).resolve().parents[3]
    / "src" / "engine" / "strategies" / "donchian_swing.py"
)

# 박스 수축 필터 고유 토큰 (제거 대상). 미래 재도입 시 이 토큰들이 되살아남.
_BOX_FILTER_TOKENS = ("box_range", "max_box_vol", "box_contraction")


def _prepare_source() -> str:
    src = _DONCHIAN.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "prepare":
            return ast.get_source_segment(src, node) or ""
    raise AssertionError("donchian_swing.py 에 prepare 정의 부재")


# ===========================================================================
# G-208-6 — prepare 영역 박스 필터 토큰 잔존 0건 (미래 재도입 영구 차단)
# ===========================================================================
@pytest.mark.parametrize("token", _BOX_FILTER_TOKENS)
def test_g208_6_no_box_filter_token_in_prepare(token):
    """donchian prepare 본문에 박스 수축 필터 토큰 부재."""
    body = _prepare_source()
    assert token not in body, (
        f"prepare 영역에 박스 수축 필터 토큰 '{token}' 잔존 금지 "
        f"(사이클 208 제거 — 미래 재도입 영구 차단)"
    )


def test_g208_6_no_box_keys_in_module_source():
    """donchian_swing.py 전체에 box 파라미터 키 문자열 부재.

    DEFAULT_PARAMS / _empty_scan_stats 잔존까지 포괄 차단.
    """
    src = _DONCHIAN.read_text(encoding="utf-8")
    assert "box_contraction_period" not in src, (
        "donchian_swing.py 에 box_contraction_period 잔존 금지 (DEFAULT_PARAMS 포함)"
    )
    assert "max_box_volatility_pct" not in src, (
        "donchian_swing.py 에 max_box_volatility_pct 잔존 금지"
    )
    assert "box_contraction_pass" not in src, (
        "donchian_swing.py 에 box_contraction_pass 잔존 금지 (_empty_scan_stats 포함)"
    )


# ===========================================================================
# SAFETY 불변식 — 청산/손절 경로 미변경 (제거 후에도 PASS)
# ===========================================================================
def test_safety_check_exit_signal_body_present():
    """donchian check_exit_signal 본체 존재 (박스 제거는 prepare 한정, 청산 무관).

    사이클 38: 필터 제거는 매수 진입 전 (prepare) 영역만 — 청산/손절 경로 불변.
    """
    src = _DONCHIAN.read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                node.name == "check_exit_signal":
            found = True
            body = ast.get_source_segment(src, node) or ""
            # 청산 핵심 로직 토큰 (트레일링/손절)은 박스 필터와 무관하게 보존
            assert "STOP_LOSS" in body or "TRAILING" in body or "stop_loss" in body, (
                "check_exit_signal 청산 로직 보존 의무"
            )
    assert found, "donchian check_exit_signal 정의 존재 의무"


def test_safety_no_box_token_in_check_exit_signal():
    """check_exit_signal 에는 애초에 박스 토큰이 없어야 함 (prepare 전용 결함이었음)."""
    src = _DONCHIAN.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                node.name == "check_exit_signal":
            body = ast.get_source_segment(src, node) or ""
            for token in _BOX_FILTER_TOKENS:
                assert token not in body, (
                    f"check_exit_signal 에 박스 토큰 '{token}' 부재 (청산 경로 무관)"
                )
