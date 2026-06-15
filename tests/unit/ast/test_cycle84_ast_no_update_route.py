"""사이클 84 Red — L-2 (LOW): AST 영구 가드 — `src/routes/stock_master.py` READ-ONLY 영속.

Q9=B 결정 채택 영속 (READ-ONLY GET only, 매매 hot path 무관) → 미래 신규 PUT/POST/DELETE/PATCH
라우트 추가 silent 결함 영구 차단.

본 AST 가드는 `src/routes/stock_master.py` 의 모든 라우트 데코레이터가 `@router.get(...)` 만
허용한다는 정적 검증. PUT/POST/DELETE/PATCH 데코레이터 0건 의무.

**사이클 90 (H-3) 갱신**: POST 1개 예외 허용 (`refresh-universe`) — 사용자 결정 Q24=B
+ Q25=A 채택 영속. `_ALLOWED_POST_ROUTES` 화이트리스트로 1건만 예외 허용 + 기타 POST/PUT/DELETE/PATCH 0건 영속.
사이클 84 Q9=B 의미 영속 (READ-ONLY 원칙 보존 + 1개 명시 예외 허용 + 미래 silent 결함 차단).

위험 등급 LOW (영구 정적 가드, 미래 silent 결함 차단 패턴 영역).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

# 사이클 137 (2026-06-15) — 카드 #25 AST DRY 헬퍼 모듈 마이그레이션.
from tests.unit.ast._ast_helpers import read_module_source as _read

pytestmark = pytest.mark.unit

ROUTE_PATH = (
    Path(__file__).resolve().parents[3]
    / "src" / "routes" / "stock_master.py"
)

FORBIDDEN_METHODS = {"put", "post", "delete", "patch"}

# 사이클 90 (H-3) → 사이클 126 갱신 — POST 3개 예외 화이트리스트.
# 사용자 결정 Q24=B + Q25=A 채택 영속 + 사이클 126 사용자 결정 (basics/daily refresh).
# 신규 항목 추가 시 별개 사이클 의제 의무 (사이클 84 Q9=B READ-ONLY 원칙 영속).
_ALLOWED_POST_ROUTES = {
    "/refresh-universe",       # 사이클 90
    "/basics/refresh",         # 사이클 126 — KIS CTPF1002R 매스 보강 수동 trigger
    "/daily/refresh",          # 사이클 126 — 일봉 적재 수동 trigger
    "/master/refresh",         # 사이클 129 — KIS 종목 마스터 파일 적재 수동 trigger
}


def _extract_route_path(deco: ast.AST) -> str | None:
    """`@router.post("/refresh-universe", ...)` 데코레이터에서 첫 인자 path 문자열 추출."""
    if not isinstance(deco, ast.Call):
        return None
    if not deco.args:
        return None
    first_arg = deco.args[0]
    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
        return first_arg.value
    return None


def test_L2_ast_no_write_decorators_in_stock_master_route():
    """L-2: src/routes/stock_master.py 의 router 데코레이터 중 PUT/POST/DELETE/PATCH 0건.

    AST 정적 분석:
    - 모든 함수 정의 데코레이터 순회
    - `router.<method>(...)` 또는 `<x>.put/post/delete/patch(...)` 매칭 시 fail
    - 사이클 90 갱신: POST `/refresh-universe` 단독 화이트리스트 예외 허용
    """
    assert ROUTE_PATH.exists(), (
        f"라우트 파일 미작성: {ROUTE_PATH} — backend-dev Green 단계 의무"
    )
    tree = ast.parse(_read(ROUTE_PATH))
    forbidden_hits = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            # `@router.put(...)` / `@router.post(...)` / ...
            call_node = deco if isinstance(deco, ast.Call) else None
            func = call_node.func if call_node is not None else deco
            if isinstance(func, ast.Attribute) and func.attr.lower() in FORBIDDEN_METHODS:
                # 사이클 90 (H-3) 갱신 — POST 1개 예외 화이트리스트
                if func.attr.lower() == "post":
                    route_path = _extract_route_path(deco)
                    if route_path is not None and route_path in _ALLOWED_POST_ROUTES:
                        # 허용된 POST 영역 — 사이클 90 Q24=B + Q25=A 영속
                        continue
                forbidden_hits.append(
                    f"{node.name} 에 @<x>.{func.attr}(...) 데코레이터 (L{deco.lineno})"
                )

    assert not forbidden_hits, (
        f"READ-ONLY 위반: PUT/POST/DELETE/PATCH 데코레이터 {len(forbidden_hits)} 건 검출\n"
        + "\n".join(forbidden_hits)
        + "\n→ Q9=B 결정 영속 = READ-ONLY GET only + POST 1개 예외 허용 (사이클 90).\n"
        + f"  허용 화이트리스트: {_ALLOWED_POST_ROUTES}\n"
        + "  향후 변경 라우트 필요 시 별개 사이클 의제."
    )


def test_L2_h3_cycle90_post_refresh_universe_whitelisted_only():
    """L-2 H-3 (사이클 90): POST `/refresh-universe` 단독 화이트리스트 예외 + 기타 POST 0건.

    사이클 90 Q24=B + Q25=A 영속 — POST 1개 (`refresh-universe`) 만 예외 허용.
    기타 POST 라우트 추가 silent 결함 영구 차단 패턴.
    """
    assert ROUTE_PATH.exists()
    tree = ast.parse(_read(ROUTE_PATH))
    post_routes = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            call_node = deco if isinstance(deco, ast.Call) else None
            func = call_node.func if call_node is not None else deco
            if isinstance(func, ast.Attribute) and func.attr.lower() == "post":
                route_path = _extract_route_path(deco)
                post_routes.append((node.name, route_path, deco.lineno))

    # POST 라우트 검출 시도 모두 화이트리스트 검증 (사이클 90 갱신 영역)
    unauthorized = [
        (name, path, lineno)
        for (name, path, lineno) in post_routes
        if path not in _ALLOWED_POST_ROUTES
    ]
    assert not unauthorized, (
        f"사이클 90 H-3 위반 — 화이트리스트 외 POST 라우트 {len(unauthorized)}건 검출:\n"
        + "\n".join(f"  - {name} `{path}` (L{lineno})" for (name, path, lineno) in unauthorized)
        + f"\n→ 허용 화이트리스트: {_ALLOWED_POST_ROUTES}\n"
        + "→ 신규 POST 라우트 필요 시 별개 사이클 의제 의무 (사이클 84 Q9=B 영속)."
    )
