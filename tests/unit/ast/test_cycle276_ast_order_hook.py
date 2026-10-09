"""cycle276 Red — AST/구조 가드: 주문 시점 LLM 평가 훅의 **행위 0 기계 증명**.

명세 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §1-A (C1~C16) · §7 · §8 ·
브리프 `scratchpad/cycle276_brief.md` §3 설계 결정 1·2.

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 이 파일이 재는 것

cycle274 는 훅을 전략의 `check_buy_signal` **신호 시점**에 두었다. cycle276 은 그것을
`OrderEngine.execute_buy` 의 **주문 접수 직후**(두 매수 경로 각각)로 옮긴다. 옮기는 대상은
관측이고 옮기는 자리는 **8영역**(`src/engine/order_engine.py`)이라, "매매 경로가 한 글자도
바뀌지 않았다" 를 사람의 눈이 아니라 AST 로 증명해야 한다.

| 계약 | 증명 방식 |
|---|---|
| C1·C2 | 훅은 `ast.Expr` statement 2개, 각자 `try/except Exception` 흡수기 안 |
| C4·C5 | `place_order` 인자 불변 · A-ATOMIC 구간 **소스 세그먼트 sha 동일** |
| C6 | 매도 경로(`execute_sell`·손절 재주문)에 훅 0건 |
| C7·C8 | 매핑 대입 **뒤**, `_completed_orders` 판정·PENDING INSERT **앞**, 사이 `await` 0 |
| C10 | `order_engine.py` 의 `src.*` import 증가분 정확히 1 |
| C11·C12 | 전략 2파일 6 메서드 sha 가 **cycle272 값으로 복귀** + `llm_buy_gate` 참조 0 |
| C13·C14·C15 | 8영역 나머지 byte 동일 · order_engine 만 승인 sha 핀 · 자매 핀 4곳 대칭 |

## 왜 `git grep`/`git ls-files` 로 스캔하지 않는가

추적 파일만 보므로 Green 이 새로 만든 **미추적** 파일을 로컬에서 못 보고 CI(커밋 후)에서만
잡는다(cycle259 S4b). 소스 스캔은 `Path(...).rglob` + AST 로 한다.

## 왜 `ast.dump` sha 를 핀하지 않는가

3.12(CI) / 3.13(로컬) 출력이 달라 로컬 초록·CI 실패가 난다(cycle256 G-250-5 · cycle259 S4a).
본체 무변경 핀은 `ast.get_source_segment` 또는 **소스 라인 슬라이스**의 sha256 으로 잰다.

## 핀의 자리

`_ATOMIC_SEGMENT_SHA`(A-ATOMIC 구간 sha)는 이 파일의 내용 계약이다. 8영역 + `scheduler.py`
파일 내용 sha 는 정본 `test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA` 한 곳에만
둔다(cycle419 — 이 파일의 C13 파일 핀·정확 줄 수 핀·승인 목록 사본은 걷었다).
`scheduler.py` 라인 **상한**(`< 3,900`, cycle257)은 C13 이 계속 복창한다.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest

from tests import _strategy_census as census

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
_AST_DIR = _ROOT / "tests" / "unit" / "ast"
_STRATEGY_DIR = _SRC / "engine" / "strategies"

_ORDER_ENGINE = _SRC / "engine" / "order_engine.py"
_ORDER_ENGINE_REL = "src/engine/order_engine.py"
_SCHEDULER = _SRC / "engine" / "scheduler.py"
_RECO = _SRC / "engine" / "recommendation_engine.py"

_VB = _STRATEGY_DIR / "volatility_breakout.py"
_LTV = _STRATEGY_DIR / "long_tail_volatility.py"
_VB_REL = "src/engine/strategies/volatility_breakout.py"
_LTV_REL = "src/engine/strategies/long_tail_volatility.py"

_HOOK_NAME = "observe_order"
_LEAF_MODULE = "src.engine.llm_buy_gate"

_KEYS = (
    "llm_gate_mode",
    "llm_gate_min_score",
    "llm_gate_daily_call_cap",
    "llm_gate_timeout_secs",
)

_MUTATING_CALLS = {"add", "pop", "discard", "update", "clear", "append", "setdefault"}


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _read(path: Path) -> str:
    assert path.exists(), f"{path.relative_to(_ROOT)} 가 없다 — 명세 파일 목록 미이행(Red)"
    return path.read_text(encoding="utf-8")


def _tree(path: Path) -> tuple[ast.Module, str]:
    src = _read(path)
    return ast.parse(src), src


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    out: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            out[id(child)] = parent
    return out


def _func(tree: ast.Module, name: str):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def _execute_buy():
    tree, src = _tree(_ORDER_ENGINE)
    fn = _func(tree, "execute_buy")
    assert fn is not None, "`execute_buy` 를 찾지 못했다"
    return tree, src, fn


def _hook_calls(scope: ast.AST) -> list[ast.Call]:
    """`llm_buy_gate.observe_order(...)` Call 노드 (호출 형태 무관 — attr 이름으로 찾는다)."""
    out = []
    for n in ast.walk(scope):
        if isinstance(n, ast.Call):
            fn = n.func
            if isinstance(fn, ast.Attribute) and fn.attr == _HOOK_NAME:
                out.append(n)
            elif isinstance(fn, ast.Name) and fn.id == _HOOK_NAME:
                out.append(n)
    return sorted(out, key=lambda c: c.lineno)


def _require_two(nodes, what: str):
    """0건이면 **공허 통과**가 되는 단언들을 위한 선행 관문.

    훅이 아직 없을 때 `for call in []:` 는 조용히 초록이 된다 — 그러면 Red 가 Red 처럼
    보이지 않고, 나중에 훅 하나를 지우는 뮤테이션(M1)도 이 케이스들을 통과한다.
    """
    assert len(nodes) == 2, f"{what} {len(nodes)}건 (기대 2) — 훅 배선 미이행 또는 누락"
    return nodes


def _hook_stmts(tree: ast.Module, scope: ast.AST) -> list[ast.Expr]:
    """훅 Call 의 **직접 부모** — `ast.Expr` 이어야 한다(C1)."""
    parents = _parents(tree)
    return [parents[id(c)] for c in _hook_calls(scope)]


def _mapping_assign_lines(fn) -> list[int]:
    """`self._pending_buy_orders[...] = {...}` 대입문 lineno (오름차순)."""
    out = []
    for n in ast.walk(fn):
        if not isinstance(n, ast.Assign):
            continue
        for tgt in n.targets:
            if (
                isinstance(tgt, ast.Subscript)
                and isinstance(tgt.value, ast.Attribute)
                and tgt.value.attr == "_pending_buy_orders"
            ):
                out.append(n.lineno)
    return sorted(out)


#: 접수 후 PENDING 영속화의 **진입점 계보**. 개명·층 추가가 있을 때마다 여기에
#: 더하고, 가드 본문은 손대지 않는다 — 이 가드가 보는 계약은 이름이 아니라
#: 「`execute_buy` 안에서 훅이 그것보다 앞인가」 이고 그 계약은 한 번도 안 바뀌었다.
#:
#: cycle271 `_insert_pending_buy_or_absorb_race`
#:   → cycle327 매수·매도 공용 `_insert_pending_or_absorb_race`
#:   → cycle334 4경로 공용 코어 `_persist_pending_after_send`
#:   → cycle335 매수 경계 래퍼 `_persist_buy_pending_after_send`
#:      (`execute_buy` 는 이제 코어를 직접 부르지 않고 이 래퍼를 부른다)
_PERSIST_ENTRYPOINTS = frozenset({
    "_persist_pending_after_send",
    "_persist_buy_pending_after_send",
})


def _completed_check_lines(fn) -> list[int]:
    """체결통보 선행 **판정에 도달하는 지점**의 lineno (오름차순).

    ⚠️ cycle334 에서 그 판정이 `execute_buy` 본문에서 **코어 헬퍼**
    `_persist_pending_after_send` 안으로 옮겨갔고, cycle335 가 그 앞에 매수 경계
    래퍼를 한 층 더 끼웠다. 계약은 그대로다 — 「훅은 그 판정보다 **앞**」.
    그래서 판정 그 자체(`ast.Compare`)가 아니라 **그 판정으로 들어가는 문**
    (= `_PERSIST_ENTRYPOINTS` 호출)의 lineno 를 본다.

    🔴 `ast.Compare` 로 되돌리면 `execute_buy` 안에 0건이라 **가드가 공허해진다**
    (훅을 아무 데나 옮겨도 초록이 된다). 이름 하나로 고정하는 것도 같은 결과다 —
    다음 층이 생기는 순간 0건이 된다. `len(checks) >= 2` 가 그 방어다.
    """
    return _insert_helper_lines(fn)


def _insert_helper_lines(fn) -> list[int]:
    """접수 후 PENDING 영속화 호출의 lineno (오름차순).

    🔴 이름 집합(`_PERSIST_ENTRYPOINTS`)으로 찾는 이유 = 이 계보는 사이클마다 한 층씩
    바뀌는데 **계약은 안 바뀌기** 때문이다. 이름 하나로 고정하면 다음 개명에서
    `inserts == []` 가 되고, `len(inserts) >= 2` 양성 대조군이 없으면 그 순간
    가드가 **공허하게 초록**이 된다(호출부 2곳 단언이 그 방어다).
    """
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr in _PERSIST_ENTRYPOINTS:
            out.append(n.lineno)
    return sorted(out)


def _place_order_calls(scope: ast.AST) -> list[ast.Call]:
    out = []
    for n in ast.walk(scope):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id == "place_order":
            out.append(n)
    return sorted(out, key=lambda c: c.lineno)


def _kwarg_names(call: ast.Call) -> list[str]:
    return sorted("**" if k.arg is None else k.arg for k in call.keywords)


def _nearest_try(tree: ast.Module, node: ast.AST):
    """`node` 를 **body** 에 담은 가장 가까운 `ast.Try` (handlers 안이면 계속 올라간다)."""
    parents = _parents(tree)
    cur = node
    while id(cur) in parents:
        parent = parents[id(cur)]
        if isinstance(parent, ast.Try) and any(cur is st for st in parent.body):
            return parent
        cur = parent
    return None


def _atomic_bounds(src: str, fn) -> tuple[int, int]:
    """A-ATOMIC 구간 = `calc_buy_quantity` 호출문 ~ 첫 `pending_buys.add(ticker)` (동적 산출).

    ⚠️ 라인 리터럴을 쓰지 않는다 — 명세 §14-1 이 브리프의 `:272~:314` 를 `:313~:354` 로
    정정했듯 좌표는 사이클마다 흔들린다. 경계는 **AST 로 매번 다시 계산**한다
    (`tests/unit/ast/test_budget_limit_ast.py` 선례).
    """
    start = None
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "calc_buy_quantity":
            start = n.lineno if start is None else min(start, n.lineno)
    assert start is not None, "`calc_buy_quantity` 호출을 찾지 못했다"

    ends = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "add" \
                and isinstance(n.func.value, ast.Attribute) \
                and n.func.value.attr == "pending_buys":
            if n.lineno >= start:
                ends.append(n.lineno)
    assert ends, "`state.pending_buys.add(ticker)` 를 찾지 못했다"
    return start, min(ends)


def _segment(src: str, start_line: int, end_line: int) -> str:
    return "".join(src.splitlines(keepends=True)[start_line - 1:end_line])


def _src_imports(tree: ast.Module) -> set[str]:
    """모듈 **최상단** `src.*` import 의 정규화 이름 집합."""
    out: set[str] = set()
    for n in tree.body:
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith("src"):
                    out.add(a.name)
        elif isinstance(n, ast.ImportFrom):
            if n.module and n.module.startswith("src"):
                for a in n.names:
                    out.add(f"{n.module}.{a.name}")
    return out


def _method_segment(path: Path, cls_name: str, method: str) -> str:
    src = _read(path)
    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    fn = next(
        n for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method
    )
    return ast.get_source_segment(src, fn) or ""


_STRATEGY_META = {
    "vb": (_VB, "VolatilityBreakoutStrategy"),
    "ltv": (_LTV, "LongTailVolatilityStrategy"),
}
_KINDS = ("vb", "ltv")


def _current_method_sha(kind: str, method: str) -> str:
    path, cls_name = _STRATEGY_META[kind]
    return hashlib.sha256(_method_segment(path, cls_name, method).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# base(34ba9e6) 스냅샷 — 이 사이클이 **바꾸지 않는다**고 약속한 값들
# ---------------------------------------------------------------------------

# A-ATOMIC 구간(`calc_buy_quantity` 호출문 ~ 첫 `pending_buys.add`)의 소스 슬라이스 sha256.
# 🔁 2026-10-04 (cycle408-L3) 재핀 — 사용자 승인 10-04 8영역 관측 결함 해결: 구간 안 `quantity <= 0`
#    분기의 WARNING 에 원인 꼬리(`원인: funds|cap|unknown, 잔여:`)를 붙이는 동기 판정 try 1개 추가.
#    await 0 그대로(`test_c3_2`), 쿨다운·return 순서 불변.
#    직전 값 = `9fa886727eac9c391d4887a1fb124caffce8abb0e4d167484211c5f765f2b891`.
_ATOMIC_SEGMENT_SHA = "838ca5f93969d697508b730bbec9584f679ff5fc0d9d2eaddef07d9d78953adb"

# `order_engine.py` 모듈 최상단 `src.*` import 이름 집합(base). 증가분은 leaf 1건뿐이다(C10).
_BASE_ORDER_ENGINE_SRC_IMPORTS = frozenset({
    "src.api.balance.get_buyable",
    "src.api.balance.is_insufficient_cash",
    "src.api.balance.is_insufficient_quantity",
    "src.api.balance.is_market_closed_rejection",
    "src.api.balance.is_market_order_disallowed",
    "src.api.balance.is_sell_qty_exceeded",
    "src.api.base.KisApiError",
    "src.api.order.cancel_order",
    "src.api.order.place_order",
    "src.db.system_logs.safe_write_log",
    "src.db.system_logs.write_log",
    "src.db.trade_history._lookup_strategy_from_trade_history",
    "src.db.trade_history._update_trade_status_by_order_no",
    "src.db.trade_history.insert_trade",
    "src.db.trade_history.update_trade_status",
    "src.engine.daily_emit_cap.DailyEmitCap",
    "src.engine.scanner.t",
    "src.engine.sell_rejection.SellRejectionTracker",
    "src.engine.sell_rejection.is_krx_main_hours",
    "src.engine.sell_rejection.is_nxt_session_hours",
    "src.engine.strategy_base.Position",
    "src.engine.strategy_base.Signal",
    "src.engine.strategy_base.StrategyBase",
    "src.engine.strategy_registry.StrategyRegistry",
    "src.engine.util.tick_size.step_down",
    "src.engine.util.tick_size.step_up",
    "src.models.order.OrderDivision",
    "src.models.order.OrderSide",
    "src.models.trade.TradeRecord",
    "src.models.trade.TradeStatus",
    "src.models.trade.TradeType",
})

# 두 매수 `place_order` 호출의 키워드 이름(base). 주 경로는 `**place_kwargs` 언팩이라
# `dict(...)` 쪽 키워드도 함께 잰다(C4 — 언팩 뒤에 숨는 인자 변경 차단).
_BASE_PLACE_ORDER_KWARGS = [["**"], ["exchange", "order_division", "price", "quantity", "side", "ticker"]]
_BASE_PLACE_KWARGS_DICT = ["exchange", "price", "quantity", "side", "ticker"]

# cycle272 시점 = cycle274 배선 **이전**의 메서드 세그먼트 sha. C11 은 이 값으로의
# **복귀**를 요구한다(전략 원상 복구의 유일한 기계적 증거).
_CYCLE272_METHOD_SHA = {
    # 🔁 cycle399 재핀 — 공통 섀도 모드(사용자 승인 10-02 R1) — BUY 반환 앞 섀도 관문 1문장(`if self._shadow_buy_intercepted(...): return Signal.NONE`) 삽입. 그 밖 무변경.
    ("vb", "check_buy_signal"):
        "5424dc5b23fb3b382174098b4a964c7a76a6ffb7ab3ed9597e0774b03e31c2da",
    ("vb", "check_exit_signal"):
        "86593b038e4cf8121ae47069fb368346edc50d9692b29db4cbdcc8897421b72e",
    ("vb", "calc_buy_quantity"):
        "6d24ef3f3afd211ae6123623075b08320cdc08c9cd48a6db965355305ad4e732",
    ("ltv", "check_buy_signal"):
        "fb1e7460e5d6906aacd9dd6cbc1037fb7327759c24ca4df055773ba1f22cac2a",
    ("ltv", "check_exit_signal"):
        "c8b0e6a8c8705d49bb6f12f82f505d426a5bdeb81413f8b2e0276eabb7dd9cad",
    ("ltv", "calc_buy_quantity"):
        "1149ecc8ea37fb1ba164cc1fd88e6525111d5142168ca879f1026c7890905b81",
}


# ===========================================================================
# C1 — 훅은 `ast.Expr` statement 2개 (반환값이 매매 결정에 닿지 않는다)
# ===========================================================================
def test_c1_1_hook_appears_exactly_twice() -> None:
    """C1 — `observe_order` 호출이 `order_engine.py` 에 **정확히 2건**(주 경로 + 지정가 폴백).

    1건이면 폴백 경로의 주문이 통째로 기록에서 빠지고(뮤테이션 M1), 3건이면 같은 주문이
    두 번 평가돼 비용·래치가 흔들린다.
    """
    tree, _src = _tree(_ORDER_ENGINE)
    calls = _hook_calls(tree)
    assert len(calls) == 2, f"`{_HOOK_NAME}` 호출 {len(calls)}건 (기대 2)"


def test_c1_2_hook_is_bare_expression() -> None:
    """C1 (HIGH) — 두 훅 모두 Call 의 **직접 부모가 `ast.Expr`**.

    반환값이 어떤 이름에도 바인딩되지 않고 `if`/`return`/비교의 피연산자도 아니다 =
    "점수가 주문을 못 막는다" 의 기계 증명. 이 한 가지가 이 사이클의 심장이다.
    """
    tree, _src = _tree(_ORDER_ENGINE)
    parents = _parents(tree)
    for call in _require_two(_hook_calls(tree), "훅 호출"):
        parent = parents[id(call)]
        assert isinstance(parent, ast.Expr), (
            f"line {call.lineno}: `{_HOOK_NAME}(...)` 의 부모가 {type(parent).__name__} 다 — "
            "값이 소비되는 자리에 두면 shadow 계약이 깨진다"
        )


def test_c1_3_hook_uses_keyword_args_only() -> None:
    """C1 — 위치 인자 0개. 인자 순서 실수 하나가 주문가·수량을 뒤바꿔 기록한다."""
    tree, _src = _tree(_ORDER_ENGINE)
    for call in _require_two(_hook_calls(tree), "훅 호출"):
        assert call.args == [], f"line {call.lineno}: 위치 인자 {len(call.args)}개 — 키워드 전용이어야 한다"


def test_c1_4_no_await_on_hook() -> None:
    """C1/C8 — 훅 statement 및 그 인자식 어디에도 `ast.Await` 0건.

    `await` 하나가 매핑 등록과 PENDING INSERT 사이에 새 양보점을 만들어 cycle271 이
    닫은 race 창을 다시 연다.
    """
    tree, _src = _tree(_ORDER_ENGINE)
    for stmt in _require_two(_hook_stmts(tree, tree), "훅 statement"):
        awaits = [n for n in ast.walk(stmt) if isinstance(n, ast.Await)]
        assert not awaits, f"line {stmt.lineno}: 훅 statement 에 `await` {len(awaits)}건"


def test_c1_5_hook_is_inside_execute_buy() -> None:
    """C1 — 두 훅 모두 `execute_buy` FunctionDef 범위 안(다른 메서드로 새지 않았다)."""
    tree, _src, fn = _execute_buy()
    inside = _hook_calls(fn)
    assert len(inside) == 2, f"`execute_buy` 안 훅 {len(inside)}건 (기대 2)"
    for call in inside:
        assert fn.lineno <= call.lineno <= (fn.end_lineno or call.lineno)


def test_c1_6_hook_follows_pending_buy_orders_assign() -> None:
    """C7 — 훅 자리는 `_pending_buy_orders[...] = {...}` 대입 **직후**.

    그 대입이 끝나야 `result.order_no` 가 확정되고 PK `(trade_date, account, ticker,
    order_no)` 가 성립한다.
    """
    _tree_, _src, fn = _execute_buy()
    mapping = _mapping_assign_lines(fn)
    hooks = [c.lineno for c in _hook_calls(fn)]
    assert len(mapping) == 2 and len(hooks) == 2, f"매핑 {mapping} / 훅 {hooks}"
    for m, h in zip(mapping, hooks):
        assert m < h, f"매핑 대입(line {m}) 이 훅(line {h}) 뒤에 있다"


def test_c1_7_hook_precedes_completed_orders_check() -> None:
    """C7 — 훅은 `_completed_orders` 선행 판정 **앞**이다(뮤테이션 M3).

    판정 뒤로 옮기면 "체결통보가 REST 응답보다 먼저 도착한" 코호트에서 분기가 갈려
    기록 위치가 두 갈래가 된다.
    """
    _tree_, _src, fn = _execute_buy()
    hooks = [c.lineno for c in _hook_calls(fn)]
    checks = _completed_check_lines(fn)
    assert len(hooks) == 2 and len(checks) >= 2, f"훅 {hooks} / 판정 {checks}"
    for h, c in zip(hooks, checks[:2]):
        assert h < c, f"훅(line {h}) 이 `_completed_orders` 판정(line {c}) 뒤에 있다"


def test_c1_8_hook_precedes_insert_helper() -> None:
    """C7 (HIGH) — 훅은 PENDING INSERT(`_insert_pending_or_absorb_race`) **앞**이다.

    INSERT 뒤로 옮기면 체결통보 선행 코호트(가장 빨리 체결되는 진입)가 기록에서 통째로
    빠진다 — 09-09 034020 · 09-10 004990 실측(뮤테이션 M2).
    """
    _tree_, _src, fn = _execute_buy()
    hooks = [c.lineno for c in _hook_calls(fn)]
    inserts = _insert_helper_lines(fn)
    assert len(hooks) == 2 and len(inserts) >= 2, f"훅 {hooks} / INSERT {inserts}"
    for h, i in zip(hooks, inserts[:2]):
        assert h < i, f"훅(line {h}) 이 PENDING INSERT(line {i}) 뒤에 있다"


def test_c1_9_no_await_between_hook_and_insert() -> None:
    """C8 — 훅 끝과 PENDING INSERT 사이에 `await` 0건(새 양보점 금지)."""
    # ⚠️ `ast.parse(src)` 로 **다시 파싱**하면 `fn` 은 앞선 파스의 노드라 부모 맵의
    # id 가 어긋나 `KeyError` 다(Red 결함 시정 — 같은 트리를 써야 한다).
    _tree_, _src, fn = _execute_buy()
    hook_stmts = _hook_stmts(_tree_, fn)
    inserts = _insert_helper_lines(fn)
    assert len(hook_stmts) == 2 and len(inserts) >= 2
    for stmt, ins in zip(hook_stmts, inserts[:2]):
        lo = stmt.end_lineno or stmt.lineno
        bad = [
            n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Await) and lo < n.lineno < ins
        ]
        assert not bad, f"훅(line {stmt.lineno})~INSERT(line {ins}) 사이 `await` {bad}"


def test_c1_10_each_hook_wrapped_in_try_except_exception() -> None:
    """C2 (HIGH) — 각 훅은 자기 `try:` / 1문 / `except Exception:` 흡수기 안이다.

    폴백 경로의 훅은 `except KisApiError` 핸들러 **안**의 중첩 try 안에 있어서, 형제
    핸들러가 non-`KisApiError` 를 못 잡는다 — 흡수기가 `Exception` 이 아니면 관측 실패
    하나가 pending 좀비를 만든다(명세 C3 · 뮤테이션 M5).
    """
    tree, _src = _tree(_ORDER_ENGINE)
    for stmt in _require_two(_hook_stmts(tree, tree), "훅 statement"):
        try_node = _nearest_try(tree, stmt)
        assert try_node is not None, f"line {stmt.lineno}: 훅을 감싼 `try` 가 없다"
        assert len(try_node.body) == 1, (
            f"line {try_node.lineno}: 훅 전용 `try` 본문이 {len(try_node.body)}문 — "
            "훅 한 문장만 감싼다(다른 문장을 같이 감싸면 그 문장의 실패까지 조용히 삼킨다)"
        )
        handler_names = [
            h.type.id if isinstance(h.type, ast.Name) else ast.dump(h.type) if h.type else "bare"
            for h in try_node.handlers
        ]
        assert handler_names == ["Exception"], (
            f"line {try_node.lineno}: 흡수기 핸들러 {handler_names} — `except Exception` 하나여야 한다"
        )


def test_c1_11_absorber_body_has_no_state_mutation() -> None:
    """C2 — 흡수기 `except` 본문에 `raise`/`return`/상태 변경문 0건.

    흡수기가 `pending_buys.discard` 같은 정리를 하면 그것이 곧 행위 변경이다.
    """
    tree, _src = _tree(_ORDER_ENGINE)
    for stmt in _require_two(_hook_stmts(tree, tree), "훅 statement"):
        try_node = _nearest_try(tree, stmt)
        assert try_node is not None
        for h in try_node.handlers:
            for n in ast.walk(ast.Module(body=h.body, type_ignores=[])):
                assert not isinstance(n, (ast.Raise, ast.Return)), (
                    f"line {getattr(n, 'lineno', '?')}: 흡수기 본문에 raise/return"
                )
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                    assert n.func.attr not in _MUTATING_CALLS, (
                        f"line {n.lineno}: 흡수기 본문이 상태를 바꾼다(`{n.func.attr}`)"
                    )
                assert not isinstance(n, (ast.Assign, ast.AugAssign)), (
                    f"line {getattr(n, 'lineno', '?')}: 흡수기 본문에 대입문"
                )


def test_c1_12_hook_args_have_no_store_context() -> None:
    """C9 — 훅 인자식에 Store 컨텍스트 0건(인자 계산이 상태를 심지 않는다)."""
    tree, _src = _tree(_ORDER_ENGINE)
    for call in _require_two(_hook_calls(tree), "훅 호출"):
        for kw in call.keywords:
            for n in ast.walk(kw.value):
                ctx = getattr(n, "ctx", None)
                assert not isinstance(ctx, (ast.Store, ast.Del)), (
                    f"line {call.lineno}: 인자식 `{kw.arg}` 가 Store/Del 컨텍스트를 갖는다"
                )


def test_c1_13_hook_args_have_no_mutating_calls() -> None:
    """C9 — 훅 인자식의 Call 이름에 `add/pop/discard/update/clear/append` 0건.

    `dict(strategy.config.params)` · `list(state.buy_signals[-3:])` 같은 **복사**는 허용,
    원본을 건드리는 메서드는 금지.
    """
    tree, _src = _tree(_ORDER_ENGINE)
    for call in _require_two(_hook_calls(tree), "훅 호출"):
        for kw in call.keywords:
            for n in ast.walk(kw.value):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                    assert n.func.attr not in _MUTATING_CALLS, (
                        f"line {call.lineno}: 인자식 `{kw.arg}` 가 `{n.func.attr}()` 를 부른다"
                    )


def test_c1_14_hook_args_have_no_db_or_http() -> None:
    """C8 — 훅 인자식에 DB/HTTP/로그쓰기 흔적 0건(동기 hot path 계약)."""
    _tree_, src, _fn = _execute_buy()
    tree = ast.parse(src)
    banned = ("pg.", "httpx", "requests", "insert_trade", "write_log", "fetch(")
    for call in _require_two(_hook_calls(tree), "훅 호출"):
        for kw in call.keywords:
            seg = ast.get_source_segment(src, kw.value) or ""
            hits = [b for b in banned if b in seg]
            assert not hits, f"line {call.lineno}: 인자식 `{kw.arg}` 에 {hits}"


# ===========================================================================
# C6 — 매도 경로에 훅 0건
# ===========================================================================
def test_c2_1_sell_paths_have_no_hook() -> None:
    """C6 (HIGH) — `execute_sell` 및 `OrderSide.SELL` `place_order` 와 같은 `try` 에 훅 0건.

    매도에 붙으면 "매수 평가" 테이블에 매도가 섞여 회고분석의 모집단이 오염된다.
    """
    tree, src = _tree(_ORDER_ENGINE)
    sell_fn = _func(tree, "execute_sell")
    assert sell_fn is not None
    assert not _hook_calls(sell_fn), "`execute_sell` 안에 훅이 있다"

    # B4-3(cycle424) — 폴백 블록(⑰)이 `_handle_sell_market_disallowed` 로
    # 뽑혔다. 그 메서드도 매도 경로라 훅 0건이 그대로 적용돼야 한다(약화 금지,
    # 대상 함수 목록에 더한다).
    fallback_fn = _func(tree, "_handle_sell_market_disallowed")
    assert fallback_fn is not None, "B4-3 추출 메서드가 없다"
    assert not _hook_calls(fallback_fn), "`_handle_sell_market_disallowed` 안에 훅이 있다"

    for call in _place_order_calls(tree):
        seg = ast.get_source_segment(src, call) or ""
        if "OrderSide.SELL" not in seg:
            continue
        try_node = _nearest_try(tree, call)
        node = try_node if try_node is not None else call
        assert not _hook_calls(node), (
            f"line {call.lineno}: 매도 `place_order` 와 같은 try 안에 훅이 있다"
        )


def test_c2_2_hook_name_count_in_whole_file_is_two() -> None:
    """C6 — 파일 전체 AST 에서 `observe_order` 이름 노드가 **정확히 2건**.

    ⚠️ 주석·docstring 은 세지 않는다(cycle259 S4b 계열 — 소스 스캔은 AST 로).
    """
    tree, _src = _tree(_ORDER_ENGINE)
    seen = 0
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr == _HOOK_NAME:
            seen += 1
        elif isinstance(n, ast.Name) and n.id == _HOOK_NAME:
            seen += 1
    assert seen == 2, f"`{_HOOK_NAME}` 이름 노드 {seen}건 (기대 2)"


# ===========================================================================
# C5 — A-ATOMIC 구간 byte 동일
# ===========================================================================
def test_c3_1_atomic_segment_sha_unchanged() -> None:
    """C5 (HIGH) — `calc_buy_quantity` ~ `pending_buys.add` 구간 소스 sha 가 base 와 동일.

    이 구간의 원자성(`await` 0)이 예산 클램프의 전제다 — 깨지면 두 코루틴이 같은 잔여를
    보고 각자 매수한다(A-ATOMIC).
    """
    _tree_, src, fn = _execute_buy()
    start, end = _atomic_bounds(src, fn)
    seg = _segment(src, start, end)
    actual = hashlib.sha256(seg.encode("utf-8")).hexdigest()
    assert actual == _ATOMIC_SEGMENT_SHA, (
        f"A-ATOMIC 구간(line {start}~{end}) 이 base(34ba9e6) 와 다르다 — "
        "이 사이클은 그 구간을 한 글자도 바꾸지 않는다"
    )


def test_c3_2_atomic_segment_has_no_await() -> None:
    """C5 — 그 구간에 `ast.Await` 0건(라인 리터럴이 아니라 AST 동적 경계로 잰다)."""
    _tree_, src, fn = _execute_buy()
    start, end = _atomic_bounds(src, fn)
    bad = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Await) and start <= n.lineno <= end]
    assert not bad, f"A-ATOMIC 구간(line {start}~{end}) 에 `await` {bad}"


# ===========================================================================
# C4 / C10 — `place_order` 인자 불변 · import 증가분 1
# ===========================================================================
def test_c4_1_place_order_kwargs_unchanged() -> None:
    """C4 (HIGH) — 두 매수 `place_order` 호출의 키워드 집합이 base 와 동일.

    주 경로는 `**place_kwargs` 언팩이므로 `place_kwargs = dict(...)` 쪽 키워드도 함께
    잰다 — 언팩 뒤에 인자 변경이 숨는 것을 막는다.
    """
    _tree_, src, fn = _execute_buy()
    calls = _place_order_calls(fn)
    assert len(calls) == 2, f"`execute_buy` 안 `place_order` 호출 {len(calls)}건 (기대 2)"
    assert [_kwarg_names(c) for c in calls] == _BASE_PLACE_ORDER_KWARGS

    dict_kwargs = None
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "place_kwargs" for t in n.targets
        ) and isinstance(n.value, ast.Call):
            dict_kwargs = _kwarg_names(n.value)
    assert dict_kwargs == _BASE_PLACE_KWARGS_DICT, (
        f"`place_kwargs = dict(...)` 키워드 {dict_kwargs} (기대 {_BASE_PLACE_KWARGS_DICT})"
    )


def test_c4_2_order_engine_src_imports_delta_is_one() -> None:
    """C10 (HIGH) — 모듈 최상단 `src.*` import 증가분이 정확히 `src.engine.llm_buy_gate` 1건.

    `observer_trace`·`settings`·`db.llm_buy_evaluations` 는 order_engine 이 모른다 —
    계좌·기록은 leaf 책임이다(8영역 표면을 넓히지 않는다).
    """
    tree, _src = _tree(_ORDER_ENGINE)
    now = _src_imports(tree)
    added = now - _BASE_ORDER_ENGINE_SRC_IMPORTS
    removed = _BASE_ORDER_ENGINE_SRC_IMPORTS - now
    assert removed == set(), f"base import 가 사라졌다: {sorted(removed)}"
    assert added == {_LEAF_MODULE}, f"import 증가분 {sorted(added)} (기대 {{{_LEAF_MODULE}}})"


# ===========================================================================
# C13 — `scheduler.py` 라인 상한 (cycle257 영구 상한 복창)
# ===========================================================================
def test_c5_2_scheduler_line_count_under_permanent_cap() -> None:
    """C13 — `scheduler.py` 라인 상한(cycle257 영구 상한 3,900 미만).

    정확 줄 수 핀은 cycle419 에서 걷었다 — 「무접촉」 은 정본 승인 도장
    (`test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA`)이 파일 내용 sha 로 잰다.
    """
    lines = len(_read(_SCHEDULER).splitlines())
    assert lines < 3900, f"scheduler.py {lines}L — cycle257 영구 상한 3,900 초과"


def test_c5_3_scheduler_line_cap_is_not_looser_than_cycle257() -> None:
    """C13 — 자체 상한이 cycle257 의 **영구** 상한보다 느슨하지 않다.

    cycle264 가 자기 상한을 4,000 으로 두는 바람에 cycle257 영구 가드 위반을 초록으로
    덮을 뻔했다(적대 검증 HIGH). 두 수가 갈라지면 항상 **더 조인 쪽**이 정본이다.
    """
    mine = {int(c) for c in re.findall(
        r"assert lines [<=]=? (\d+)", Path(__file__).read_text(encoding="utf-8"),
    )}
    theirs = {int(c) for c in re.findall(
        r"assert count < (\d+)",
        (_AST_DIR / "test_cycle257_ast_dead_code_removed.py").read_text(encoding="utf-8"),
    )}
    assert mine and theirs
    assert min(mine) <= min(theirs), f"cycle276 상한({sorted(mine)}) > cycle257({sorted(theirs)})"


# ===========================================================================
# C11 / C12 — 전략 2파일 원상 복구
# ===========================================================================
# 🔁 2026-09-12 (cycle286, C2-a) — `("ltv", "check_buy_signal")` 항목은 **자기소멸**
#    했다(cycle223 헤더 TODO 선례 — 자문 §명세 조건 2, backend-dev Green 적용).
#    LTV `check_buy_signal` 이 이 사이클에서 **다시, 정당하게** 바뀐다(main 보드 15:20
#    매수 컷 발사점 게이트) — cycle276 의 "cycle272 값으로 복귀" 불변식과 cycle274 의
#    "현재값으로 재핀"(`test_cycle274_ast_llm_gate.py::test_c18_3`, 동적 비교라 항상
#    참) 이 이제 동시에 성립할 수 없는 매듭이었다. 자문 권고대로 **청산·수량 4핀은
#    불변 유지**하고 `check_buy_signal` 엔트리만 여기서 은퇴한다 — VB 의
#    `check_buy_signal` 은 이 사이클 무접촉이라 cycle272 값 그대로 남는다(아래에서
#    계속 검사). `test_cycle264_scope_and_pins.py::_STRATEGY_PINS` 의 LTV
#    `check_buy_signal` 핀은 cycle286 현재값으로 갱신했다(그 파일의 동적 재핀 계약과
#    정합). ⚠️ 이 은퇴는 도메인 자문이 권고했으나 최종 확정은 메인 세션 몫이다
#    (자문 §명세 "그 은퇴 결정은 메인 세션이 내린다").
_FROZEN_272 = sorted(k for k in _CYCLE272_METHOD_SHA if k != ("ltv", "check_buy_signal"))


@pytest.mark.parametrize("key", _FROZEN_272)
def test_c6_1_strategy_methods_return_to_cycle272_sha(key) -> None:
    """C11 (HIGH) — VB·LTV 5 메서드(청산·수량 4 + VB `check_buy_signal`) 세그먼트 sha 가
    **cycle272 값으로 복귀**한다.

    cycle274 가 `check_buy_signal` 2핀을 바꿨다. cycle276 은 훅을 `order_engine` 으로
    옮기므로 그 2핀이 되돌아와야 한다 — 되돌아오지 않으면 전략에 죽은 배선이 남았다는 뜻.
    청산·수량 4핀은 애초부터 불변. **LTV `check_buy_signal` 은 cycle286 이 은퇴**했다
    (위 배너) — 그 사이클에서 정당하게 다시 바뀌었기 때문이다.
    """
    kind, method = key
    assert _current_method_sha(kind, method) == _CYCLE272_METHOD_SHA[key], (
        f"{kind}.{method} 이 cycle272 값과 다르다 — 전략 원상 복구 미완(Red)"
    )


@pytest.mark.parametrize("kind", _KINDS)
def test_c6_2_strategies_have_no_llm_buy_gate_import_or_call(kind: str) -> None:
    """C12 (HIGH) — VB·LTV 에 `llm_buy_gate` **import·호출 0건**.

    ⚠️ 문자열 전수가 아니라 AST 로 잰다 — `DEFAULT_PARAMS` 4키 주석이 leaf 이름을
    설명으로 언급하고(명세 §8 은 그 주석 블록을 "한 글자도 건드리지 않는다" 고 못박았다)
    그 주석은 배선이 아니다. 배선의 정의는 import 와 호출이다(C12 괄호 문면).
    """
    path, _cls = _STRATEGY_META[kind]
    tree, _src = _tree(path)

    imported = [
        n.lineno for n in ast.walk(tree)
        if (isinstance(n, ast.ImportFrom)
            and any(a.name == "llm_buy_gate" for a in n.names))
        or (isinstance(n, ast.Import)
            and any(a.name.endswith("llm_buy_gate") for a in n.names))
    ]
    assert not imported, f"{kind}: `llm_buy_gate` import 가 남아 있다 (lines {imported})"

    refs = [
        n.lineno for n in ast.walk(tree)
        if (isinstance(n, ast.Name) and n.id == "llm_buy_gate")
        or (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            and n.value.id == "llm_buy_gate")
    ]
    assert not refs, f"{kind}: `llm_buy_gate` 참조가 남아 있다 (lines {refs})"


#: cycle297(2026-09-17) — 5전략 LLM 매수평가 shadow 확대로 소유 축이 {VB, LTV} →
#: **7전략 전부**로 뒤집혔다(사용자 결정 "결정 2 진행"). 가드는 삭제·skip 하지 않고
#: 기대값만 반전한다(명세 §5.2 — cycle297 자체 가드 `test_g2_1b` 가 존재·무회피를 잠근다).
#: 리팩토링 카드 #1 — 기대값은 「7개 고정 목록」 이 아니라 **전략 명부 전부**
#: (`tests/_strategy_census.py`)다. 규약을 지켜 4키를 가진 여덟째 전략을 거짓으로 붉히지 않는다.
_ALL_STRATEGY_RELS = census.STRATEGY_RELS


@pytest.mark.parametrize("key", _KEYS)
def test_c6_3a_four_keys_live_in_exactly_vb_and_ltv(key: str) -> None:
    """C12 — 4키를 `DEFAULT_PARAMS` 에 가진 전략 파일 = **전략 명부 전부**.

    🔁 cycle297 반전 — 원래 {VB, LTV} 였다(명세 §6 스코프). 사용자 결정으로 5전략이
    추가됐고, 함수명·존재는 유지한 채 기대값만 뒤집는다(삭제·skip 금지).
    """
    owners: list[str] = []
    for path in _STRATEGY_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "DEFAULT_PARAMS" for t in node.targets):
                continue
            if not isinstance(node.value, ast.Dict):
                continue
            for k in node.value.keys:
                if isinstance(k, ast.Constant) and k.value == key:
                    owners.append(path.relative_to(_ROOT).as_posix())
    assert sorted(set(owners)) == sorted(_ALL_STRATEGY_RELS), (
        f"`{key}` 보유 전략 {sorted(set(owners))} (기대 = 명부 전부, "
        f"빠짐 {sorted(_ALL_STRATEGY_RELS - set(owners))}). "
        "새 전략이면 그 파일의 `DEFAULT_PARAMS` 에 4키(`llm_gate_mode`·`llm_gate_min_score`·"
        "`llm_gate_daily_call_cap`·`llm_gate_timeout_secs`)를 다른 전략과 같은 값으로 넣어라. "
        "전략이 아닌 파일이 갖고 있으면 지워라"
    )


@pytest.mark.parametrize("key", _KEYS)
def test_c6_3b_four_keys_stay_out_of_param_ranges(key: str) -> None:
    """C12 — 4키는 `PARAM_RANGES`/`INT_PARAMS` 밖(런타임 dict + 소스 리터럴 이중).

    편입되면 AI 자문이 임계 70·비용 cap 을 최근 손실에 맞춰 자동 튜닝한다(cycle223 선례).
    """
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    assert key not in PARAM_RANGES
    assert key not in INT_PARAMS
    hits = [i for i, line in enumerate(_read(_RECO).splitlines(), 1) if key in line]
    assert not hits, f"`recommendation_engine.py` 에 `{key}` 리터럴(lines {hits})"


# ===========================================================================
# C14 — cycle264 메서드 핀이 cycle272 값으로 복귀
# ===========================================================================
def test_c6_4a_cycle264_pins_are_restored_to_cycle272_values() -> None:
    """C15 — cycle264 `_STRATEGY_PINS` 의 VB `check_buy_signal` 핀이 **cycle272 값으로 복귀**.

    cycle274 가 이 핀을 현재값으로 갱신했다. 전략을 되돌리면 핀도 함께 되돌아와야 한다 —
    아니면 cycle264 가드가 붉어지고, 붉다고 그 가드를 지우면 무접촉 증거가 사라진다.

    🔁 2026-09-12 (cycle286) — **LTV 는 이 단정에서 은퇴**했다(위 `test_c6_1` 배너와
    같은 매듭). LTV `check_buy_signal` 이 cycle286 에서 다시 정당하게 바뀌어
    `_STRATEGY_PINS` 의 그 항목은 이제 cycle272 값이 아니라 **cycle286 현재값**을
    가져야 한다 — 그 계약은 `test_cycle274_ast_llm_gate.py::test_c18_3`(동적 비교)가
    계속 잰다.
    """
    text = (_AST_DIR / "test_cycle264_scope_and_pins.py").read_text(encoding="utf-8")
    for kind in ("vb",):
        module = "volatility_breakout" if kind == "vb" else "long_tail_volatility"
        m = re.search(
            rf'\(\s*"{module}"\s*,\s*"\w+"\s*,\s*"check_buy_signal"\s*\)\s*:\s*\n?\s*"([0-9a-f]{{64}})"',
            text,
        )
        assert m, f"`_STRATEGY_PINS` 에서 {module}.check_buy_signal 핀을 찾지 못했다"
        assert m.group(1) == _CYCLE272_METHOD_SHA[(kind, "check_buy_signal")], (
            f"{module}.check_buy_signal 핀이 cycle272 값이 아니다 — 복귀 누락"
        )
