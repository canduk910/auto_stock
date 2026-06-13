"""사이클 120 — TTL 우회 옵션 (force=True) 추가 (사용자 강제 새로고침 영역).

근본 원인 (사이클 119 효과 검증 시점, 2026-06-12 19:28 KST):
- 사이클 119 시정 (4 매핑 추가) push 완료 후 EC2 재기동 → _full_universe_load_once 자동 실행
- 결과: total=2769 / fetched=0 / skipped_ttl=2697 / elapsed_ms=163004
- 24h TTL 영역 영구 영속이 (사이클 101 `is_stale(max_age_hours=24)`) → 기존 2,696 ticker fresh skip
- 사이클 116/118/119 매핑 영역 영구 영속이 미적용 (신규 ticker만 적용)

시정 (사용자 결정):
- POST /refresh-universe ?force=true 영역 영구 영속이 디폴트 (UI 강제 새로고침 의도)
- _full_universe_load_once(force=False) 인자 추가
- _full_universe_load_krx_primary(force=False) + _full_universe_load_kis_fallback(force=False) 인자 추가
- force=True 시 TTL 검사 우회 (전 ticker 강제 갱신)
- 자동 발화 (사이클 106 매일 20:00:05) = force=False 영속 (TTL 적용)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCANNER_PY = Path(__file__).resolve().parents[4] / "src" / "engine" / "scanner.py"
_ROUTE_PY = Path(__file__).resolve().parents[4] / "src" / "routes" / "stock_master.py"


def _find_function(tree: ast.AST, name: str) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _get_function_args(fn: ast.AST) -> dict:
    """함수 시그너처의 인자 + 기본값 추출."""
    args = {}
    for arg, default in zip(reversed(fn.args.args), reversed(fn.args.defaults)):
        args[arg.arg] = ast.unparse(default)
    return args


def test_h1_full_universe_load_once_has_force_arg():
    """HIGH-1: _full_universe_load_once(force: bool = False) 시그너처 영구 영속이."""
    source = _SCANNER_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = _find_function(tree, "_full_universe_load_once")
    assert fn is not None
    args = _get_function_args(fn)
    assert "force" in args, "_full_universe_load_once 영역 force 인자 부재"
    assert args["force"] == "False", "force 디폴트 False 영속 (TTL 자동 발화 영역)"


def test_h2_full_universe_load_krx_primary_has_force_arg():
    """HIGH-2: _full_universe_load_krx_primary(force: bool = False) 시그너처 영구 영속이."""
    source = _SCANNER_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = _find_function(tree, "_full_universe_load_krx_primary")
    assert fn is not None
    args = _get_function_args(fn)
    assert "force" in args
    assert args["force"] == "False"


def test_h3_full_universe_load_kis_fallback_has_force_arg():
    """HIGH-3: _full_universe_load_kis_fallback(force: bool = False) 시그너처 영구 영속이."""
    source = _SCANNER_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = _find_function(tree, "_full_universe_load_kis_fallback")
    assert fn is not None
    args = _get_function_args(fn)
    assert "force" in args
    assert args["force"] == "False"


def test_h4_route_refresh_universe_now_force_default_true():
    """HIGH-4: POST /refresh-universe 영역 force=True 디폴트 (UI 강제 새로고침 의도)."""
    source = _ROUTE_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = _find_function(tree, "refresh_universe_now")
    assert fn is not None
    args = _get_function_args(fn)
    assert "force" in args, "refresh_universe_now 영역 force 인자 부재"
    assert args["force"] == "True", (
        "라우트 force 디폴트 True 영속 (UI 강제 새로고침 의도, 사이클 120)"
    )


@pytest.mark.xfail(
    strict=False,
    reason="사이클 127 fire-and-forget BackgroundTasks 전환 — 라우트가 _full_universe_load_once 직접 호출 폐기 → _run_universe_background 위임 (사이클 66 K-2 패턴)",
)
def test_h5_route_passes_force_to_load_once():
    """HIGH-5: 라우트 영역에서 _full_universe_load_once(force=force) 전달 영구 영속이."""
    source = _ROUTE_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = _find_function(tree, "refresh_universe_now")
    fn_source = ast.unparse(fn)
    assert "_full_universe_load_once(force=force)" in fn_source, (
        "라우트 → _full_universe_load_once(force=force) 전달 부재"
    )


def test_m1_krx_primary_bypasses_ttl_when_force():
    """MEDIUM-1: KRX 1차 영역 force=True 시 TTL 검사 우회 분기 영구 확정."""
    source = _SCANNER_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = _find_function(tree, "_full_universe_load_krx_primary")
    fn_source = ast.unparse(fn)
    # force 분기 영구 확정 (`if not force:`)
    assert "if not force:" in fn_source, (
        "_full_universe_load_krx_primary 영역 'if not force:' TTL 우회 분기 부재"
    )


def test_m2_kis_fallback_bypasses_ttl_when_force():
    """MEDIUM-2: KIS 폴백 영역 force=True 시 TTL 검사 우회 분기 영구 확정."""
    source = _SCANNER_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = _find_function(tree, "_full_universe_load_kis_fallback")
    fn_source = ast.unparse(fn)
    assert "if not force:" in fn_source, (
        "_full_universe_load_kis_fallback 영역 'if not force:' TTL 우회 분기 부재"
    )


def test_g_ast1_force_arg_propagation_chain():
    """AST 영구 가드: force 인자 영역 영구 영속이 라우트 → load_once → primary/fallback 체인 영속.

    사용자 강제 새로고침 의도 영구 영속이 미래 시정 누락 차단 (사이클 78/79 G-AST 답습).
    """
    scanner_source = _SCANNER_PY.read_text(encoding="utf-8")
    route_source = _ROUTE_PY.read_text(encoding="utf-8")

    # 라우트 → load_once 전달
    assert "_full_universe_load_once(force=force)" in route_source

    # load_once → primary/fallback 전달 (force=force 인자 영구 영속이)
    assert "_full_universe_load_krx_primary(force=force)" in scanner_source, (
        "load_once → primary 영역 force 전달 부재"
    )
    assert "_full_universe_load_kis_fallback(force=force)" in scanner_source, (
        "load_once → fallback 영역 force 전달 부재"
    )

    # 사이클 120 주석 영속
    assert "사이클 120" in scanner_source
    assert "사이클 120" in route_source
