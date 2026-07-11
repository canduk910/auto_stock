"""사이클 204 — 투자유의(invt_caful_yn) 차단 재도입 + mrkt_warn "01" 재강화 영구 차단 AST 가드.

명세: _workspace/red/cycle204_investment_caution_unblock.md
자문: _workspace/domain_consult/cycle204_investment_caution_unblock.md

배경: scanner.py `_is_master_blocked_for_entry` raw 분기가
- `mrkt_warn_cls_code >= "01"` (투자주의 01 포함) 차단
- `invt_caful_yn == "Y"` (투자유의) 차단
하면 급등 → 투자주의 지정된 우량 대형주 (실측 차단 index 9종목 전부 우량주) 를
돌파전략 후보에서 제거 = 매매 기회 손실. KIS 삼각검증 00=정상/01=투자주의/02=경고/03=위험.
투자주의(01)/투자유의는 급등 극단·작전 위험이 아니므로 차단 해제. 투자경고(02)/투자위험(03)
+ 급등 3플래그(단기과열/공매도과열/이상급등)는 유지 (SAFETY). 재도입/재강화를 AST 로 영구 차단.

가드 범위 (사이클 167/203 AST 가드 패턴 답습 — 함수 영역 한정 false-positive 차단):
- `_is_master_blocked_for_entry` 함수 노드 *내부* 에만 검사.
- `invt_caful_yn` 참조 0건 (차단 로직 + docstring 문구 완전 삭제 의무).
- mrkt_warn 임계는 `>= "02"` (또는 "01" 배제) 패턴 — `>= "01"` 잔존 0건.
- **주의**: merge 상수 `condition._FHKST_MERGE_KEYS` 의 invt_caful_yn/mrkt_warn_cls_code
  적재는 유지 (본 가드 대상 아님 = scanner 함수 영역 밖). 차단만 완화.
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
    """`func_name` 함수 노드 전체(시그니처+docstring+본체)를 소스로 반환."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            seg = ast.get_source_segment(src, node)
            assert seg is not None, f"{func_name} 소스 세그먼트 추출 실패"
            return seg
    raise AssertionError(f"{func_name} 함수 정의 부재")


class TestCycle204AstNoCautionBlock:
    def test_g_204_8_no_invt_caful_reference_in_block_func(self):
        """G-204-8 (AST): `_is_master_blocked_for_entry` 영역 invt_caful_yn 0건.

        미래 재도입(코드/docstring/주석) 영구 차단. 현재 코드는 L2564-2565 차단 블록 +
        docstring L2528 에 invt_caful_yn 참조 잔존 → RED.
        """
        func_src = _extract_function_source(_SRC, _TARGET_FUNC)
        assert "invt_caful_yn" not in func_src, (
            "G-204-8 — _is_master_blocked_for_entry 영역에 invt_caful_yn 참조 잔존. "
            "사이클 204 시정 = 투자유의 차단 블록 + docstring 문구 완전 삭제 의무 "
            "(적재 merge 는 condition.py 소관으로 유지). 재도입 시 급등 우량주 오차단 회귀."
        )

    def test_g_204_8b_market_warn_threshold_is_02(self):
        """G-204-8b (AST): mrkt_warn 임계 `>= "01"` 잔존 0건 (>= "02" 정합).

        투자주의(01) 재강화 영구 차단. 현재 코드 `mrkt_warn >= "01"` → RED.
        Green (`>= "02"`) 후 "01" 임계 배제.
        """
        func_src = _extract_function_source(_SRC, _TARGET_FUNC)
        assert 'mrkt_warn_cls_code' in func_src, (
            "G-204-8b — mrkt_warn_cls_code 차단(02/03) 자체는 존치 의무 (SAFETY)"
        )
        # `>= "01"` 임계는 투자주의 재강화 = 금지. `>= "02"` 로 정합해야 함.
        normalized = func_src.replace(" ", "").replace("'", '"')
        assert '>="01"' not in normalized, (
            'G-204-8b — mrkt_warn `>= "01"` 임계 잔존 (투자주의 재강화). '
            '사이클 204 시정 = `>= "02"` 로 완화 의무 (투자경고 02/투자위험 03만 차단).'
        )
        assert '>="02"' in normalized, (
            'G-204-8b — mrkt_warn `>= "02"` 임계 패턴 부재. '
            '투자경고/투자위험 차단 (SAFETY) 정합 확인.'
        )

    def test_g_204_8c_block_func_still_defined(self):
        """G-204-8c (구조 보존): `_is_master_blocked_for_entry` 함수 자체는 존치.

        전용 플래그(급등 3 + 경고/위험 + 거래정지 등) 차단은 유지 — 함수 삭제가 아니라
        투자주의/투자유의 분기만 완화.
        """
        tree = ast.parse(_SRC)
        found = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == _TARGET_FUNC
            for node in ast.walk(tree)
        )
        assert found, (
            "G-204-8c — _is_master_blocked_for_entry 함수 정의 존치 의무 (전용 플래그 차단 보존)"
        )
