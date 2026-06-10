"""사이클 93 G-AST1 (LOW, 영구 가드) — AST 정적 검증:
scheduler `_universe_eager_refresh_loop` 본체 + routes/stock_master.py
`refresh_universe_now` 본체에 scanner module `_universe_eager_refresh_loop` 호출 의무.

미래 신규 universe refresh 영역 추가 시 stock_master upsert chain 누락
silent 결함 영구 차단 (사이클 89 silent 결함 21회 누적 패턴 재발 차단).

Red 상태 (사이클 93 시점):
- scheduler `_universe_eager_refresh_loop` 본체에 `_scanner_upsert_loop` (또는
  `_universe_eager_refresh_loop` 모듈 함수) 호출 노드 0건 → FAIL
- routes/stock_master.py `refresh_universe_now` 동일 영역 호출 0건 → FAIL

Green (backend-dev 인계 후):
- 양쪽 사이트 모두 `await _scanner_upsert_loop(tickers)` 호출 추가
- AST 분석 결과 각 함수 본체에 호출 노드 ≥ 1건 → PASS

영속 의무:
- 사이클 78 G-AST1 (`record_*` ↔ `flush_*` 호출 사이트 영구 가드) 패턴 답습
- 사이클 79 G-AST1 (`asyncio.create_task` ↔ `stop()` task_attrs 영구 가드) 패턴 답습
- 사이클 89 silent 결함 영구 차단 패턴 정착 (호출 chain 누락 정적 검출)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SCHEDULER_PY = _PROJECT_ROOT / "src" / "engine" / "scheduler.py"
_ROUTE_PY = _PROJECT_ROOT / "src" / "routes" / "stock_master.py"


# scanner module 의 upsert chain 함수 이름 후보 (alias 허용)
_UPSERT_CALL_NAMES = {"_scanner_upsert_loop", "_universe_eager_refresh_loop"}


def _find_function(tree: ast.AST, *, class_name: str | None, func_name: str) -> ast.AST | None:
    """주어진 트리에서 함수 노드 찾기.

    class_name=None 이면 모듈 레벨 함수 검색.
    class_name 지정 시 해당 클래스 본체에서 검색.
    """
    if class_name is None:
        for node in tree.body:  # type: ignore[attr-defined]
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == func_name
            ):
                return node
        return None

    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or cls.name != class_name:
            continue
        for fn in cls.body:
            if (
                isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                and fn.name == func_name
            ):
                return fn
    return None


def _count_upsert_chain_calls(fn_node: ast.AST) -> int:
    """함수 본체에서 scanner module upsert chain 호출 노드 카운트.

    매칭 패턴 (AST):
    - `await _scanner_upsert_loop(tickers)` — Await ➜ Call(func=Name(id="_scanner_upsert_loop"))
    - `await _universe_eager_refresh_loop(tickers)` — alias 미사용 시
    - `_scanner_upsert_loop(tickers)` — await 없음도 허용 (defensive)
    """
    count = 0
    for sub in ast.walk(fn_node):
        # `Call` 노드 (Await 안이든 밖이든)
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        # `Name` 직접 호출 패턴 (`_scanner_upsert_loop(tickers)` 또는 alias)
        if isinstance(func, ast.Name) and func.id in _UPSERT_CALL_NAMES:
            count += 1
            continue
        # `Attribute` 호출 패턴 (`scanner._universe_eager_refresh_loop(tickers)` 등)
        if (
            isinstance(func, ast.Attribute)
            and func.attr in _UPSERT_CALL_NAMES
        ):
            count += 1
    return count


def test_g_ast1_scheduler_upsert_chain_required():
    """G-AST1 (a): scheduler `_universe_eager_refresh_loop` 본체 (self method) 에
    scanner module upsert chain 호출 ≥ 1건 정적 검증 (미래 silent 결함 영구 차단).

    Red 상태: scheduler 본체에 chain 호출 0건 → FAIL.
    Green: backend-dev 가 `await _scanner_upsert_loop(tickers)` 호출 추가 → PASS.
    """
    tree = ast.parse(_SCHEDULER_PY.read_text(encoding="utf-8"))

    fn = _find_function(tree, class_name="TradingScheduler", func_name="_universe_eager_refresh_loop")
    assert fn is not None, (
        "G-AST1 사전조건: `TradingScheduler._universe_eager_refresh_loop` self method 부재 — "
        "사이클 89 도입 영역 회귀."
    )

    count = _count_upsert_chain_calls(fn)
    assert count >= 1, (
        f"\n사이클 93 G-AST1(a) 위반 — `TradingScheduler._universe_eager_refresh_loop` "
        f"본체에 scanner upsert chain 호출 누락:\n\n"
        f"  매칭 패턴: {sorted(_UPSERT_CALL_NAMES)}\n"
        f"  호출 노드 수: {count} (의무 ≥ 1)\n\n"
        f"  결함 원인: 사이클 89 도입 시 `fetch_top_500_universe()` 만 호출 +\n"
        f"             ticker list 버림 → stock_master upsert 영구 0건\n\n"
        f"  시정 (Green): scheduler self method 에 다음 추가\n"
        f"    from src.engine.scanner import (\n"
        f"        fetch_top_500_universe,\n"
        f"        _universe_eager_refresh_loop as _scanner_upsert_loop,\n"
        f"    )\n"
        f"    tickers = await fetch_top_500_universe()\n"
        f"    try:\n"
        f"        await _scanner_upsert_loop(tickers)\n"
        f"    except Exception:\n"
        f"        logger.exception('[universe_eager_refresh] stock_master upsert 실패 graceful')\n\n"
        f"  영속 의무 — 미래 신규 universe refresh 영역 추가 시 chain 누락\n"
        f"  silent 결함 즉시 FAIL (사이클 89 silent 결함 21회 누적 패턴 영구 차단)."
    )


def test_g_ast1_route_upsert_chain_required():
    """G-AST1 (b): `routes/stock_master.py::refresh_universe_now` 본체에 scanner module
    upsert chain 호출 ≥ 1건 정적 검증 (수동 trigger 영역까지 영구 가드).

    Red 상태: 라우트 본체에 chain 호출 0건 → FAIL.
    Green: backend-dev 가 라우트 본체에 호출 추가 → PASS.
    """
    tree = ast.parse(_ROUTE_PY.read_text(encoding="utf-8"))

    fn = _find_function(tree, class_name=None, func_name="refresh_universe_now")
    assert fn is not None, (
        "G-AST1 사전조건: `routes/stock_master.py::refresh_universe_now` 함수 부재 — "
        "사이클 90 도입 영역 회귀."
    )

    count = _count_upsert_chain_calls(fn)
    assert count >= 1, (
        f"\n사이클 93 G-AST1(b) 위반 — `routes/stock_master.py::refresh_universe_now` "
        f"본체에 scanner upsert chain 호출 누락:\n\n"
        f"  매칭 패턴: {sorted(_UPSERT_CALL_NAMES)}\n"
        f"  호출 노드 수: {count} (의무 ≥ 1)\n\n"
        f"  결함 원인: 사이클 90 도입 시 `fetch_top_500_universe()` 만 호출 +\n"
        f"             ticker list 버림 → 사용자 UI '지금 새로고침' 무용\n"
        f"             → stock_master 60 ticker 영속 (사용자 보고 영역)\n\n"
        f"  시정 (Green): 라우트 본체에 다음 추가\n"
        f"    from src.engine.scanner import (\n"
        f"        fetch_top_500_universe,\n"
        f"        _universe_eager_refresh_loop as _scanner_upsert_loop,\n"
        f"    )\n"
        f"    tickers = await fetch_top_500_universe()\n"
        f"    try:\n"
        f"        await _scanner_upsert_loop(tickers)\n"
        f"    except Exception:\n"
        f"        logger.exception('[refresh_universe_now] stock_master upsert 실패 graceful')\n\n"
        f"  영속 의무 — 미래 신규 라우트 도입 시 chain 누락 영구 차단."
    )
