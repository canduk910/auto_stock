"""cycle409 — 사용자 결정 10-04 Q1: 매일 자동 대사 훅의 `scheduler.py` 배선 (AST).

| # | 계약 |
|---|---|
| W1 | `start()` 가 `trade_cost_reconcile_task.task_loop(self)` 를 `asyncio.create_task` 로 띄워 `_trade_cost_reconcile_task` 에 둔다 |
| W2 | 그 속성 이름이 백그라운드 task cancel 목록 **세 곳 전부**에 있다(정산 뒤 루프가 남지 않게) |
| W3 | 훅 leaf 는 시각 리터럴을 상수로 두지 않는다 — 실행 시각은 `system_config` 키에서만 온다(루프 수명 경계 2개 제외) |
| W4 | 훅 leaf 는 8영역·`scheduler.py` 를 import 하지 않는다 |
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SCHED = _ROOT / "src" / "engine" / "scheduler.py"
_LEAF = _ROOT / "src" / "engine" / "trade_cost_reconcile_task.py"
_ATTR = "_trade_cost_reconcile_task"


def _tree(p: Path) -> ast.Module:
    return ast.parse(p.read_text(encoding="utf-8"))


def test_w1_start_spawns_task():
    tree = _tree(_SCHED)
    found = False
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        t = node.targets[0]
        if not (isinstance(t, ast.Attribute) and t.attr == _ATTR):
            continue
        call = node.value
        assert isinstance(call, ast.Call) and ast.unparse(call.func) == "asyncio.create_task"
        assert ast.unparse(call.args[0]) == "trade_cost_reconcile_task.task_loop(self)"
        found = True
    assert found


def test_w2_attr_in_all_cancel_tuples():
    tree = _tree(_SCHED)
    tuples = []
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
            names = [e.value for e in node.iter.elts if isinstance(e, ast.Constant)]
            if "_status_exit_task" in names:
                tuples.append(names)
    assert len(tuples) == 3, tuples
    for names in tuples:
        assert _ATTR in names


def test_w3_no_time_literal_except_loop_bounds():
    tree = _tree(_LEAF)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and ast.unparse(n.func) in ("time", "dt_time", "datetime.time")]
    lits = sorted(ast.unparse(c) for c in calls if c.args and all(
        isinstance(a, ast.Constant) for a in c.args))
    assert lits == ["time(21, 30)", "time(7, 45)"], lits


def test_w4_leaf_imports_no_eight_areas_or_scheduler():
    banned = ("src.engine.risk", "src.engine.order_engine", "src.engine.session",
              "src.engine.scanner", "src.engine.strategy_registry", "src.engine.scheduler",
              "src.api.order", "src.realtime", "src.auth")
    for node in ast.walk(_tree(_LEAF)):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        for m in mods:
            assert not m.startswith(banned), m
