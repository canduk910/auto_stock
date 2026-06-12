"""사이클 124 — GET /{ticker}/daily 엔드포인트 AST 정적 가드.

G-AST1: src/routes/stock_master.py 에 /{ticker}/daily 데코레이터 + 함수 본체 존재 확인.
        stock_master_daily import 존재 확인.
        days Query 파라미터 존재 확인 (ge=1, le=100).

사이클 84 L-2 AST 영구 가드 영속: PUT/POST/DELETE/PATCH 0건 (refresh-universe 화이트리스트 제외).
"""
from __future__ import annotations

import ast
from pathlib import Path


ROUTES_PATH = Path(__file__).parent.parent.parent.parent / "src" / "routes" / "stock_master.py"


def _load_source() -> str:
    return ROUTES_PATH.read_text(encoding="utf-8")


# ─── G-AST1: /{ticker}/daily 엔드포인트 정적 검증 ─────────────────────────────

def test_g_ast1_daily_route_decorator_present():
    """@router.get('/{ticker}/daily') 데코레이터가 소스에 존재해야 함."""
    source = _load_source()
    assert '/{ticker}/daily"' in source or "/{ticker}/daily'" in source, (
        "/{ticker}/daily 라우트 데코레이터 누락 — 사이클 124 신규 의무"
    )


def test_g_ast1_stock_master_daily_import():
    """stock_master_daily 모듈이 import 되어야 함."""
    source = _load_source()
    assert "stock_master_daily" in source, (
        "from src.db import stock_master_daily 누락 — 일봉 조회 모듈 import 의무"
    )


def test_g_ast1_daily_function_defined():
    """get_stock_master_daily 함수가 정의되어야 함."""
    source = _load_source()
    tree = ast.parse(source)

    func_names = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
    ]
    assert "get_stock_master_daily" in func_names, (
        f"get_stock_master_daily 함수 미정의. 발견된 async 함수: {func_names}"
    )


def test_g_ast1_days_query_parameter():
    """days 파라미터가 Query 형식으로 선언되어야 함 (ge=1, le=100 범위 가드)."""
    source = _load_source()
    # Query(30, ge=1, le=100) 또는 Query(default=30, ...) 형식
    assert "days" in source, "days 파라미터 미존재"
    assert "ge=1" in source, "days Query ge=1 누락 (최솟값 가드)"
    assert "le=100" in source, "days Query le=100 누락 (최댓값 가드)"


def test_g_ast1_get_recent_daily_called():
    """get_stock_master_daily 함수 본체에서 stock_master_daily.get_recent_daily 를 호출해야 함."""
    source = _load_source()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_stock_master_daily":
            # 함수 본체 소스 추출 — 간단 텍스트 검색
            func_src = ast.unparse(node)
            assert "get_recent_daily" in func_src, (
                "get_stock_master_daily 본체에서 get_recent_daily 호출 누락"
            )
            return

    raise AssertionError("get_stock_master_daily 함수를 찾지 못함")


def test_g_ast1_smd_max_bas_dd_global_call():
    """stock_master.get_stats 에서 max_bas_dd() 를 ticker 인자 없이 호출해야 함.

    ticker=None (전체 MAX) 호출 패턴 정적 확인 — 사이클 124 영역 2 영속.
    """
    sm_path = Path(__file__).parent.parent.parent.parent / "src" / "db" / "stock_master.py"
    source = sm_path.read_text(encoding="utf-8")

    # max_bas_dd() 인자 없이 호출 (ticker 생략 = default None)
    assert "max_bas_dd()" in source, (
        "get_stats 에서 max_bas_dd() 인자 없이 호출 누락 — 전체 MAX(bas_dd) 조회 의무"
    )


def test_g_ast1_l2_no_extra_post_routes():
    """사이클 84 L-2 영속 — refresh-universe 외 POST/PUT/DELETE/PATCH 라우트 0건."""
    source = _load_source()
    lines = source.splitlines()

    _WHITELIST = {"refresh-universe"}

    extra_mutating = []
    for line in lines:
        stripped = line.strip()
        for method in ("router.post(", "router.put(", "router.delete(", "router.patch("):
            if method in stripped:
                # 화이트리스트 경로 제외
                if not any(w in stripped for w in _WHITELIST):
                    extra_mutating.append(stripped)

    assert not extra_mutating, (
        f"사이클 84 L-2 위반 — 비허용 변경 메서드 라우트 발견: {extra_mutating}"
    )
