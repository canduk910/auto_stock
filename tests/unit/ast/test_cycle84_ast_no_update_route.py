"""사이클 84 Red — L-2 (LOW): AST 영구 가드 — `src/routes/stock_master.py` READ-ONLY 영속.

Q9=B 결정 채택 영속 (READ-ONLY GET only, 매매 hot path 무관) → 미래 신규 PUT/POST/DELETE/PATCH
라우트 추가 silent 결함 영구 차단.

본 AST 가드는 `src/routes/stock_master.py` 의 모든 라우트 데코레이터가 `@router.get(...)` 만
허용한다는 정적 검증. PUT/POST/DELETE/PATCH 데코레이터 0건 의무.

위험 등급 LOW (영구 정적 가드, 미래 silent 결함 차단 패턴 영역).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROUTE_PATH = (
    Path(__file__).resolve().parents[3]
    / "src" / "routes" / "stock_master.py"
)

FORBIDDEN_METHODS = {"put", "post", "delete", "patch"}


def test_L2_ast_no_write_decorators_in_stock_master_route():
    """L-2: src/routes/stock_master.py 의 router 데코레이터 중 PUT/POST/DELETE/PATCH 0건.

    AST 정적 분석:
    - 모든 함수 정의 데코레이터 순회
    - `router.<method>(...)` 또는 `<x>.put/post/delete/patch(...)` 매칭 시 fail
    """
    assert ROUTE_PATH.exists(), (
        f"라우트 파일 미작성: {ROUTE_PATH} — backend-dev Green 단계 의무"
    )
    tree = ast.parse(ROUTE_PATH.read_text(encoding="utf-8"))
    forbidden_hits = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            # `@router.put(...)` / `@router.post(...)` / ...
            call_node = deco if isinstance(deco, ast.Call) else None
            func = call_node.func if call_node is not None else deco
            if isinstance(func, ast.Attribute) and func.attr.lower() in FORBIDDEN_METHODS:
                forbidden_hits.append(
                    f"{node.name} 에 @<x>.{func.attr}(...) 데코레이터 (L{deco.lineno})"
                )

    assert not forbidden_hits, (
        f"READ-ONLY 위반: PUT/POST/DELETE/PATCH 데코레이터 {len(forbidden_hits)} 건 검출\n"
        + "\n".join(forbidden_hits)
        + "\n→ Q9=B 결정 영속 = READ-ONLY GET only. 향후 변경 라우트 필요 시 별개 사이클 의제."
    )
