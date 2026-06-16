"""사이클 155 — 매매 안전성 영역 영구 영속 회귀 가드.

영속 의무 매트릭스:
- 사이클 32 R4 보유/익일청산 절대 보호
- 사이클 38 명문화 (scanner 매수 진입 전 한정)
- 사이클 81 G-AST1 raw 영역 영구 영속 보호 (덮어쓰기 0)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_CONDITION_PY = Path(__file__).resolve().parents[4] / "src" / "api" / "condition.py"
_SCANNER_PY = Path(__file__).resolve().parents[4] / "src" / "engine" / "scanner.py"
_RISK_PY = Path(__file__).resolve().parents[4] / "src" / "engine" / "risk.py"
_ORDER_PY = Path(__file__).resolve().parents[4] / "src" / "engine" / "order_engine.py"


class TestCycle155Safety:
    """G-155-SAFETY-1~4: 매매 안전성 변경 0 영역 영구 영속."""

    def test_g_155_safety_1_risk_order_unchanged(self):
        """G-155-SAFETY-1 (HIGH): risk.on_tick / order_engine 영역 _FHKST_MERGE_KEYS 영역 영구 영속 import 0건."""
        # risk.py 영역 영구 영속에 사이클 155 신규 상수 영역 import 부재 의무
        risk_src = _RISK_PY.read_text(encoding="utf-8")
        assert "_FHKST_MERGE_KEYS" not in risk_src, (
            "G-155-SAFETY-1: risk.py 영역 _FHKST_MERGE_KEYS 영역 영구 영속 import 결함"
        )
        assert "_ZERO_VALUE_SKIP_KEYS" not in risk_src

        # order_engine.py 영역 동일 영속
        order_src = _ORDER_PY.read_text(encoding="utf-8")
        assert "_FHKST_MERGE_KEYS" not in order_src
        assert "_ZERO_VALUE_SKIP_KEYS" not in order_src

    def test_g_155_safety_2_scanner_entry_block_only(self):
        """G-155-SAFETY-2 (HIGH): scanner _is_master_blocked_for_entry 영역 매수 진입 전 한정.

        호출 사이트 0건 영역 영구 영속 (사이클 156+ 활용 영역 영영 영영) → 회귀 보존.
        """
        scanner_src = _SCANNER_PY.read_text(encoding="utf-8")
        tree = ast.parse(scanner_src)

        # _is_master_blocked_for_entry 함수 영역 영구 영속 정의 영역 영구 영속
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_is_master_blocked_for_entry":
                found = True
                # 인자 영역 = master_raw + raw (사이클 155 영역 영구 영속)
                arg_names = [a.arg for a in node.args.args]
                assert "master_raw" in arg_names
                assert "raw" in arg_names, (
                    "G-155-SAFETY-2: _is_master_blocked_for_entry 영역 raw 인자 영역 영구 영속 부재"
                )
                break
        assert found, "G-155-SAFETY-2: _is_master_blocked_for_entry 함수 정의 부재"

    def test_g_155_safety_3_raw_preserve_pattern(self):
        """G-155-SAFETY-3 (HIGH): 사이클 145 raw 영역 덮어쓰기 0 패턴 영속 (numeric_value == 0 영역 영구 영속).

        사이클 145 G-145-RAW-4 영역 영구 영속 답습.
        """
        condition_src = _CONDITION_PY.read_text(encoding="utf-8")

        # numeric_value == 0 영역 영구 영속 분기 영속 (사이클 145 영역 영구 영속)
        assert "numeric_value == 0" in condition_src, (
            "G-155-SAFETY-3: 사이클 145 0 값 영역 영구 영속 가드 영역 영구 영속 변경 결함"
        )
        # _ZERO_VALUE_SKIP_KEYS 영역 영구 영속 분기
        assert "_ZERO_VALUE_SKIP_KEYS" in condition_src

        # merged_raw 영역 영구 영속 = dict(ctpf_output) 영역 영구 영속 보존
        assert "merged_raw = dict(ctpf_output)" in condition_src

    def test_g_155_safety_4_master_blocked_signature(self):
        """G-155-SAFETY-4 (MEDIUM): _is_master_blocked_for_entry 시그너처 영역 영구 영속.

        raw 인자 영역 디폴트 None (회귀 보존 — 사이클 153 영영 영영 호출자 영역 영구 영속 호환).
        """
        from src.engine import scanner

        # 기존 호출 시그너처 (master_raw 만) 호환 의무
        b, r = scanner._is_master_blocked_for_entry({})
        assert b is False
        assert r == ""

        # raw 명시 호출
        b, r = scanner._is_master_blocked_for_entry({}, None)
        assert b is False
