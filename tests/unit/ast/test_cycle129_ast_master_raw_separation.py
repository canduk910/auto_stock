"""사이클 129 AST 영구 가드 — master_raw 영역 raw 분리 영속.

배경:
- 사이클 81 G-AST1 영속 보호 (raw 영역 덮어쓰기 금지)
- master_raw 별도 컬럼 채택 (Q6=C) → 자동 분리 영역 영구 가드

회귀 가드 1 케이스:
- G-AST-MS1: upsert_master_raw 함수 영역 = raw 영역 변경 0 영구 가드
  (사이클 81 G-AST1 영역 확장)
"""
from __future__ import annotations

import ast
from pathlib import Path

from tests.unit.ast._ast_helpers import read_module_source

_STOCK_MASTER_SRC = (
    Path(__file__).resolve().parents[3] / "src/db/stock_master.py"
)


def test_g_ast_ms1_upsert_master_raw_no_raw_key():
    """G-AST-MS1: upsert_master_raw 함수 본체 = raw / bfdy_clpr / hts_avls 키 미참조.

    사이클 81 G-AST1 영속 보호 영역 확장 — master_raw 별도 컬럼 영역에서
    raw 영역 덮어쓰기 절대 금지.
    """
    src = read_module_source(_STOCK_MASTER_SRC)
    tree = ast.parse(src)

    target_func = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            if node.name == "upsert_master_raw":
                target_func = node
                break

    assert target_func is not None, (
        "G-AST-MS1: upsert_master_raw 함수 영역 부재"
    )

    # 함수 본체 영역 검증 — "raw" / "bfdy_clpr" / "hts_avls" 문자열 키 미참조
    func_src = ast.get_source_segment(src, target_func) or ""

    # raw= 명시 영역 (dict key "raw") 부재
    assert '"raw"' not in func_src and "'raw'" not in func_src, (
        "G-AST-MS1: upsert_master_raw 본체 'raw' 키 참조 영역 발견 — "
        "사이클 81 G-AST1 위반 (raw 덮어쓰기 금지)"
    )

    # bfdy_clpr / hts_avls 키 부재 (사이클 81 G-AST1 영역 확장)
    assert "bfdy_clpr" not in func_src, (
        "G-AST-MS1: upsert_master_raw 'bfdy_clpr' 영역 발견 — 사이클 81 G-AST1 위반"
    )
    assert "hts_avls" not in func_src, (
        "G-AST-MS1: upsert_master_raw 'hts_avls' 영역 발견 — 사이클 81 G-AST1 위반"
    )
