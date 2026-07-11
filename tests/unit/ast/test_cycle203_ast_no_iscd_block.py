"""사이클 203 — iscd_stat_cls_code 차단 재도입 영구 차단 AST 가드.

명세: _workspace/red/cycle203_iscd_stat_overblock.md
자문: _workspace/domain_consult/cycle203_iscd_stat_overblock.md

배경: scanner.py `_is_master_blocked_for_entry` 영역이 raw.iscd_stat_cls_code 를
차단 기준으로 사용하면 KOSPI200∪KOSDAQ150 정상 대형주 60~75% 오차단 (실측 57=정상 91%).
KIS 는 iscd_stat_cls_code 코드값 의미를 공식 배포하지 않음 → 하드코딩 블록리스트는
미래 회귀 위험 (신규 코드값 등장 시 silent 오차단/오통과). 따라서 차단 로직에서 완전
제거하고, 재도입을 AST 로 영구 차단.

가드 범위 (사이클 167 AST 가드 패턴 답습 — 함수 영역 한정 false-positive 차단):
- `_is_master_blocked_for_entry` 함수 노드 *내부* 에만 `iscd_stat_cls_code` 참조 0건.
- 함수 밖 (merge 상수 `_FHKST_MERGE_KEYS` 는 condition.py 소관 — 적재는 유지, 차단만 제거)은
  본 가드 대상 아님. scanner.py 다른 위치의 iscd 언급도 무관 (현재 없음).
- docstring 언급도 포함 (함수 노드 전체를 unparse → 문자열 검사). 사이클 203 시정 시
  docstring 의 iscd 문구도 제거 대상이므로.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
SCANNER_PY = REPO_ROOT / "src" / "engine" / "scanner.py"

assert SCANNER_PY.exists(), f"scanner.py 영역 부재 ({SCANNER_PY})"
_SRC = SCANNER_PY.read_text(encoding="utf-8")

_TARGET_FUNC = "_is_master_blocked_for_entry"


def _extract_function_source(src: str, func_name: str) -> str:
    """`func_name` 함수 노드 전체(시그니처+docstring+본체)를 소스로 반환.

    ast.get_source_segment 로 원본 라인을 그대로 잘라내 주석까지 포함
    (docstring/문자열 리터럴 언급도 포착).
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            seg = ast.get_source_segment(src, node)
            assert seg is not None, f"{func_name} 소스 세그먼트 추출 실패"
            return seg
    raise AssertionError(f"{func_name} 함수 정의 부재")


class TestCycle203AstNoIscdBlock:
    def test_g_203_9_no_iscd_stat_reference_in_block_func(self):
        """G-203-9 (AST): `_is_master_blocked_for_entry` 영역 iscd_stat_cls_code 0건.

        미래 재도입(코드/docstring/주석) 영구 차단. 현재 코드는 L2565-2568 + docstring
        L2529 에 iscd_stat_cls_code 참조 잔존 → RED.
        """
        func_src = _extract_function_source(_SRC, _TARGET_FUNC)
        assert "iscd_stat_cls_code" not in func_src, (
            "G-203-9 — _is_master_blocked_for_entry 영역에 iscd_stat_cls_code 참조 잔존. "
            "사이클 203 시정 = L2565-2568 차단 로직 + docstring iscd 문구 완전 삭제 의무. "
            "재도입 시 정상 대형주 60~75% 오차단 회귀 (실측 57=정상 91%)."
        )

    def test_g_203_9b_block_func_still_defined(self):
        """G-203-9b (구조 보존): `_is_master_blocked_for_entry` 함수 자체는 존치.

        전용 플래그 12건 차단은 유지 — 함수 삭제가 아니라 iscd 분기만 제거.
        """
        tree = ast.parse(_SRC)
        found = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == _TARGET_FUNC
            for node in ast.walk(tree)
        )
        assert found, "G-203-9b — _is_master_blocked_for_entry 함수 정의 존치 의무 (전용 플래그 차단 보존)"
