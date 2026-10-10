"""cycle379 Red — ⑨A `buying_reconcile` 구조 가드 (AST · 주석/docstring 제외).

명세 = `_workspace/red/cycle379_buying_reconcile_spec.md` §4 「배선·API·구조」

| # | 계약 |
|---|---|
| G1 | leaf 는 8영역(`src.realtime`·`src.auth`·`src.api.order`·`src.engine.{order_engine,risk,strategy_registry,session,scanner}`)과 `scheduler` 를 import 하지 않는다 — 함수 안 지연 import 포함 |
| G2 | `write_log`·`create_task`·`ensure_future`·`execute_buy`·`execute_sell`·`place_order`·`cancel_order` 식별자 0 |
| G3 | 상태 변이는 `pending_buys.discard` · `state.release_buy` · `_pending_buy_orders.pop` **셋뿐**(셋 다 있어야 한다). 매핑 5종·`sold_today`·`buy_blocked_until`·`low_funds_tickers`·`_completed_buy_orders` 는 **참조조차 0** |
| G4 | `update_trade_status` 호출은 전부 `order_no=` 를 넘기고 `match_partial` 도 `**kwargs` 도 넘기지 않는다 |
| G5 | 재검증(`has_position` 호출 + `… in/not in ….pending_buys` 또는 `is_buy_pending` 호출 + `_pending_buy_orders` 참조)이 세 변이 **직전**, 마지막 `await` **뒤**에 있고, 세 변이 사이에 `await` 0 |
| G6 | scheduler: `_sync_positions_from_balance` 안에서 `reconcile_stale_buying` 을 `reconcile_stale_selling` **뒤**에 await · `pending_buys` 조건 `if` 아래 · `_selling` 조건 `if` 밖 · 인자 `(self.registry, self.order_engine, holdings)` · 지연 import · `scheduler.py` < 3,900L |

G3 은 변이를 **직접 속성 호출**로 쓰라는 뜻이기도 하다 — `pb = s.state.pending_buys; pb.discard(t)` 같은
별칭은 가드가 추적하지 못하므로 쓰지 않는다(쓰면 "셋 다 있어야 한다" 가 붉어진다).

cycle436 카드 E — `pending_buy_amounts.pop(ticker, None)` 직접 호출이 `StrategyState.release_buy(ticker)`
단일 진입점 호출로 바뀌었다(`pending_buy_amounts` 직접 접근 0 이 전역 계약, AST =
`test_cycle436_ast_pending_buy_reservation.py`). `pending_buys.discard` 는 그대로 직접 호출이다
(이 leaf 의 해제는 종목 전체 해제 — 커밋 ① 은 키가 `ticker` 라 `release_buy` 도 종목 전체를 지운다).

G5 는 재검증을 변이와 **같은 함수**에 두거나, 같은 모듈의 **동기** 헬퍼 한 단계로 불러도 된다.
동기 `def` 안에서 재검증+변이를 하면 `await` 이 원천적으로 없어 자동으로 만족한다.

## HEAD 기준

G1~G5 RED(leaf 부재) · G6 RED(배선 부재).
"""
from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_LEAF_REL = "src/engine/buying_reconcile.py"
_SCHED_REL = "src/engine/scheduler.py"
_SCHEDULER_LINE_CAP = 3900

_FORBIDDEN_IMPORTS = (
    "src.realtime",
    "src.auth",
    "src.api.order",
    "src.engine.order_engine",
    "src.engine.risk",
    "src.engine.strategy_registry",
    "src.engine.session",
    "src.engine.scanner",
    "src.engine.scheduler",
)
_FORBIDDEN_IDENTS = {
    "write_log", "create_task", "ensure_future",
    "execute_buy", "execute_sell", "place_order", "cancel_order",
}
_ALLOWED_MUTATIONS = {
    ("pending_buys", "discard"),
    ("state", "release_buy"),
    ("_pending_buy_orders", "pop"),
}
_MUTATORS = {
    "add", "discard", "remove", "pop", "popitem", "clear", "update", "setdefault",
    "append", "extend", "insert", "__setitem__", "__delitem__",
    "release_buy",  # cycle436 카드 E — pending_buy_amounts 해제 단일 진입점
}
_STATE_ATTRS = {
    "state", "positions", "pending_buys", "pending_buy_amounts", "_pending_buy_orders",
    "sold_today", "buy_blocked_until", "low_funds_tickers", "_completed_buy_orders",
    "_completed_orders", "_order_qty", "_order_strategy", "_order_ticker", "_order_exchange",
    "_order_division", "_filled_qty", "_selling", "_selling_since",
}
_NEVER_REFERENCED = {
    "_order_qty", "_order_strategy", "_order_ticker", "_order_exchange", "_order_division",
    "sold_today", "buy_blocked_until", "low_funds_tickers", "_completed_buy_orders",
}


@lru_cache(maxsize=4)
def _tree(rel: str) -> ast.Module:
    path = _ROOT / rel
    if not path.exists():
        pytest.fail(f"[Red] `{rel}` 미존재 (명세 §2.1)")
    return ast.parse(path.read_text(encoding="utf-8"))


def _leaf() -> ast.Module:
    return _tree(_LEAF_REL)


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    out: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[child] = node
    return out


def _receiver_name(expr: ast.AST) -> str | None:
    if isinstance(expr, ast.Attribute):
        return expr.attr
    if isinstance(expr, ast.Name):
        return expr.id
    return None


def _call_name(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _state_mutation_calls(tree: ast.AST) -> list[tuple[str, str, ast.Call]]:
    out = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _MUTATORS
        ):
            recv = _receiver_name(node.func.value)
            if recv in _STATE_ATTRS:
                out.append((recv, node.func.attr, node))
    return out


# ===========================================================================
# G1
# ===========================================================================
def test_g1_leaf_imports_no_eight_area_or_scheduler_module() -> None:
    bad = []
    for node in ast.walk(_leaf()):
        mods: list[str] = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        for m in mods:
            for f in _FORBIDDEN_IMPORTS:
                if m == f or m.startswith(f + "."):
                    bad.append((node.lineno, m))
    assert not bad, (
        f"leaf 가 8영역/scheduler 를 import 한다 — {bad}. KST 는 leaf 안에서 "
        "`timezone(timedelta(hours=9))` 로 만든다(scanner import 0, 명세 §2.2)"
    )


# ===========================================================================
# G2
# ===========================================================================
def test_g2_no_write_log_task_spawn_or_order_calls() -> None:
    hits = []
    for node in ast.walk(_leaf()):
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.alias):
            for n in (node.name.rsplit(".", 1)[-1], node.asname):
                if n in _FORBIDDEN_IDENTS:
                    hits.append((getattr(node, "lineno", 0), n))
            continue
        if name in _FORBIDDEN_IDENTS:
            hits.append((node.lineno, name))
    assert not hits, (
        f"금지 식별자 {hits} — 영속은 루트 `_DbLogHandler`(write_log 이중 쓰기 금지), "
        "주문·취소·태스크 발사는 이 leaf 의 일이 아니다"
    )


# ===========================================================================
# G3
# ===========================================================================
def test_g3_state_mutations_are_exactly_the_three_first_fill_clears() -> None:
    tree = _leaf()
    got = {(recv, m) for (recv, m, _) in _state_mutation_calls(tree)}
    extra = got - _ALLOWED_MUTATIONS
    missing = _ALLOWED_MUTATIONS - got
    assert not extra, f"허용 밖 상태 변이 {sorted(extra)} — 해제는 첫 체결 경로가 지우는 세 가지뿐"
    assert not missing, f"해제 변이 {sorted(missing)} 가 직접 속성 호출로 없다"

    bad_assign = []
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        if isinstance(node, (ast.Assign,)):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = list(node.targets)
        for t in targets:
            base = t.value if isinstance(t, ast.Subscript) else t
            if isinstance(base, ast.Attribute) and base.attr in _STATE_ATTRS:
                bad_assign.append((node.lineno, base.attr))
            if isinstance(t, ast.Attribute) and t.attr in _STATE_ATTRS:
                bad_assign.append((node.lineno, t.attr))
    assert not bad_assign, f"상태 속성 대입/삭제 {bad_assign}"


def test_g3b_mappings_and_same_day_gates_are_never_referenced() -> None:
    refs = sorted(
        {(n.lineno, n.attr) for n in ast.walk(_leaf())
         if isinstance(n, ast.Attribute) and n.attr in _NEVER_REFERENCED}
    )
    assert not refs, (
        f"참조 금지 속성 {refs} — 매핑 5종은 늦은 체결의 안전망(21:30 reset 이 치운다), "
        "당일 차단 3종은 사용자 결정 9-a(재매수 허용)와 충돌"
    )


# ===========================================================================
# G4
# ===========================================================================
def test_g4_cancelled_update_is_order_scoped_and_pending_only() -> None:
    calls = [
        n for n in ast.walk(_leaf())
        if isinstance(n, ast.Call) and _call_name(n) == "update_trade_status"
    ]
    assert calls, "update_trade_status 호출이 없다 — 장부 CANCELLED 표기는 필수(명세 §2.3 D)"
    for c in calls:
        kws = {k.arg for k in c.keywords}
        assert None not in kws, f"L{c.lineno}: **kwargs 로 넘기면 가드가 인자를 볼 수 없다"
        assert "order_no" in kws, f"L{c.lineno}: order_no= 없음 — 같은 종목 다른 주문 행까지 덮는다"
        assert "match_partial" not in kws, f"L{c.lineno}: match_partial — PARTIAL 행이 CANCELLED 로 뒤집힌다"


# ===========================================================================
# G5
# ===========================================================================
def _enclosing_fn(node: ast.AST, parents: dict) -> ast.AST | None:
    cur = parents.get(node)
    while cur is not None and not isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
        cur = parents.get(cur)
    return cur


def _own_nodes(fn: ast.AST):
    """fn 본문 노드 — 중첩 함수/람다 안은 제외."""
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield n
        stack.extend(ast.iter_child_nodes(n))


def _revalidation_markers(nodes) -> set[str]:
    found: set[str] = set()
    for n in nodes:
        if isinstance(n, ast.Call) and _call_name(n) == "has_position":
            found.add("has_position")
        if isinstance(n, ast.Call) and _call_name(n) == "is_buy_pending":
            found.add("in_pending_buys")
        if isinstance(n, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in n.ops):
            if any(isinstance(c, ast.Attribute) and c.attr == "pending_buys" for c in n.comparators):
                found.add("in_pending_buys")
        if isinstance(n, ast.Attribute) and n.attr == "_pending_buy_orders":
            found.add("_pending_buy_orders")
    return found


_NEED = {"has_position", "in_pending_buys", "_pending_buy_orders"}


def test_g5_revalidation_then_mutation_without_await_between() -> None:
    tree = _leaf()
    parents = _parents(tree)
    muts = [c for (recv, m, c) in _state_mutation_calls(tree) if (recv, m) in _ALLOWED_MUTATIONS]
    assert muts, "[Red] 해제 변이가 없다"
    fns = {_enclosing_fn(c, parents) for c in muts}
    assert len(fns) == 1 and None not in fns, "세 변이는 한 함수 안에 있어야 한다"
    fn = fns.pop()
    lo = min(c.lineno for c in muts)
    hi = max(c.end_lineno or c.lineno for c in muts)
    own = list(_own_nodes(fn))
    awaits = [n for n in own if isinstance(n, ast.Await)]
    between = [a.lineno for a in awaits if lo <= a.lineno <= hi]
    assert not between, f"세 변이 사이에 await {between} — 원자성 위반"

    # 재검증 창의 시작 = 변이 앞 마지막 await. 변이를 감싼 루프 안에 await 가 있으면
    # 다음 반복의 변이는 그 await 뒤에 온다 → 창 시작을 루프 머리로 당긴다.
    start = max([a.lineno for a in awaits if a.lineno < lo] + [fn.lineno])
    first = min(muts, key=lambda c: c.lineno)
    cur = parents.get(first)
    while cur is not None and cur is not fn:
        if isinstance(cur, (ast.For, ast.AsyncFor, ast.While)):
            if any(isinstance(n, ast.Await) for n in ast.walk(cur)):
                start = max(start, cur.lineno)
            break
        cur = parents.get(cur)

    window = [n for n in own if start < getattr(n, "lineno", -1) < lo]
    found = _revalidation_markers(window)
    if not _NEED <= found:
        # 같은 모듈의 동기 헬퍼 한 단계 허용
        helpers = {
            n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)
        }
        for n in window:
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in helpers:
                found |= _revalidation_markers(_own_nodes(helpers[n.func.id]))
    assert _NEED <= found, (
        f"마지막 await(L{start}) 뒤 · 변이(L{lo}) 앞에 재검증이 없다 — 빠진 표지 {sorted(_NEED - found)} "
        "(① t∈pending_buys ③ 연결 주문 집합 ④ has_position, 명세 §2.3 C)"
    )


# ===========================================================================
# G6 — scheduler 배선
# ===========================================================================
def _sync_fn() -> ast.AsyncFunctionDef:
    for n in ast.walk(_tree(_SCHED_REL)):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_sync_positions_from_balance":
            return n
    pytest.fail("`_sync_positions_from_balance` 를 찾지 못했다")


def _src_of(node: ast.AST) -> str:
    return ast.unparse(node)


def test_g6_scheduler_awaits_buying_leaf_after_selling_under_pending_guard() -> None:
    fn = _sync_fn()
    parents = _parents(fn)
    calls = {
        name: [n for n in ast.walk(fn) if isinstance(n, ast.Call) and _call_name(n) == name]
        for name in ("reconcile_stale_selling", "reconcile_stale_buying")
    }
    assert calls["reconcile_stale_selling"], "selling 위임이 사라졌다"
    assert len(calls["reconcile_stale_buying"]) == 1, (
        f"[Red] reconcile_stale_buying 호출 {len(calls['reconcile_stale_buying'])}개 (기대 1)"
    )
    buy = calls["reconcile_stale_buying"][0]
    sell = calls["reconcile_stale_selling"][0]
    assert isinstance(parents.get(buy), ast.Await), "reconcile_stale_buying 을 await 해야 한다"
    assert buy.lineno > sell.lineno, "buying 은 selling 위임 뒤에 둔다(명세 §2.1)"

    assert [_src_of(a) for a in buy.args[:3]] == ["self.registry", "self.order_engine", "holdings"], (
        f"인자 {[_src_of(a) for a in buy.args]} — holdings 는 첫 줄 get_balance() 결과 재사용"
    )

    ifs = []
    cur = parents.get(buy)
    while cur is not None and cur is not fn:
        if isinstance(cur, ast.If):
            ifs.append(_src_of(cur.test))
        cur = parents.get(cur)
    assert any("pending_buys" in t for t in ifs), f"pending 조건 if 가 없다 — 둘러싼 if {ifs}"
    assert not any("_selling" in t for t in ifs), (
        f"selling `if` 블록 안이다 — `_selling` 이 비면 buying leaf 가 영영 안 돈다 ({ifs})"
    )

    lazy = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.ImportFrom) and n.module == "src.engine.buying_reconcile"
        and any(a.name == "reconcile_stale_buying" for a in n.names)
    ]
    assert lazy, "함수 안 지연 import(`from src.engine.buying_reconcile import reconcile_stale_buying`)가 없다"
    top = [
        n for n in _tree(_SCHED_REL).body
        if isinstance(n, ast.ImportFrom) and n.module == "src.engine.buying_reconcile"
    ]
    assert not top, "scheduler 최상단 import 금지 — selling 위임과 같은 지연 import 관례"


def test_g6b_scheduler_line_cap() -> None:
    n = len((_ROOT / _SCHED_REL).read_text(encoding="utf-8").splitlines())
    assert n < _SCHEDULER_LINE_CAP, f"scheduler.py {n}L — 영구 상한 {_SCHEDULER_LINE_CAP} 위반(cycle257)"
