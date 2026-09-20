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

## ⚠️ 사이클 한정 — 커밋 후 정리 의무

`_BASE_SHA`(8영역 내용 핀)와 `_ATOMIC_SEGMENT_SHA`(A-ATOMIC 핀)는 **브랜치 base `34ba9e6`**
의 값을 고정한 것이다. 이후 8영역을 **정당하게** 바꾸는 사이클이 오면 그 사이클이 이 dict 를
갱신하거나 이 파일을 삭제한다(고아 가드 방지 — cycle240 A11b · cycle252 G-252-5b).
`bare git diff HEAD` 를 영구 가드로 두지 않는 이유도 같다.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest

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


def _content_sha(rel: str) -> str:
    return hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()


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


def _completed_check_lines(fn) -> list[int]:
    """`result.order_no in self._completed_orders` 판정문 lineno (오름차순)."""
    out = []
    for n in ast.walk(fn):
        if not isinstance(n, ast.Compare):
            continue
        for op, cmp_ in zip(n.ops, n.comparators):
            if isinstance(op, ast.In) and isinstance(cmp_, ast.Attribute) \
                    and cmp_.attr == "_completed_orders":
                out.append(n.lineno)
    return sorted(out)


def _insert_helper_lines(fn) -> list[int]:
    """`_insert_pending_or_absorb_race(...)` 호출 lineno (오름차순).

    cycle327 에서 이 흡수기가 매수·매도 공용으로 일반화되며 이름이 바뀌었다
    (`_insert_pending_buy_or_absorb_race` → `_insert_pending_or_absorb_race`).
    이 가드가 보는 것은 execute_buy 안의 호출이라 대상은 그대로다.
    """
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "_insert_pending_or_absorb_race":
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
_ATOMIC_SEGMENT_SHA = "9fa886727eac9c391d4887a1fb124caffce8abb0e4d167484211c5f765f2b891"

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

# 8영역(order_engine 제외) + scheduler + strategy_base + 전략 5파일 blob sha (base 34ba9e6).
# ⚠️ **핀을 먼저 재산출하지 마라** — 그 순간 실제 변경이 새 스냅샷으로 봉인된다.
#    1) `git diff 34ba9e6 -- <path>` 를 눈으로 읽어라. 2) 범위 밖이면 되돌려라.
#    3) 이 사이클은 이 파일들을 바꾸지 않는다 — 재산출할 일이 없다.
# 🔁 2026-09-11 (cycle283) 재핀 — 저녁 창 재설계가 `scanner.py`(8영역, 사용자 승인)와
#    `scheduler.py`(라인 상한 승인 대상)를 바꿨다. 이 사이클의 변경이 아니라 **다른
#    사이클의 승인된 변경**이므로 값만 현재 워킹트리로 재산출한다(cycle274→cycle276
#    승계 때와 같은 절차). 나머지 핀은 불변이다.
_BASE_SHA = {
    "src/engine/risk.py":
        "e8614235cc0bea638f8c349b2f6910c94f5f9a5b849f5d65bef0583f959d81c9",
    "src/engine/session.py":
        "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    # 🔁 cycle302(2026-09-18) 재핀 — 사용자 승인 일봉 backfill **대상** 확대
    #    (분기에서 지수 소속 판정 제거 · `vcp_universe_tickers` 집합 소멸.
    #    목표 깊이 상수는 불변). 값만 옮긴다 — 단언은 그대로다.
    #    구 값은 cycle299 기준선(3b7366cc…)이다.
    "src/engine/scanner.py":
        "95cbb103a38821bb3b68d267a3662094b192fa55ad6071fa8dc4a63726e1c942",
    "src/engine/strategy_registry.py":
        "d794696e54ffdc36efa6df917879d780e86bc1f373bb3b5d8dcbc0beac8cef8b",
    "src/api/order.py":
        "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    # ⚠️ cycle292(2026-09-14) 재핀 — `_subscribe_market_operation_tickers` 176줄을
    # 신규 leaf `src/engine/market_op_subscribe.py` 로 추출(행위 변경 0 · 5줄 위임
    # wrapper · 3,897→3,726L, 사용자 승인). 여섯 자매 핀(cycle274/276/278/282/290/291)
    # 을 **한 값으로 동시에** 옮겼다 — 한 곳만 넣으면 나머지가 "코드를 되돌려라" 로
    # 붉어져 승인된 변경을 되돌리도록 오도한다. 직전 값 =
    # `50658e06062a0d38afecab1baa08871b89212e295cc95f2a3af62a2ae076115d`.
    "src/engine/scheduler.py":
        "088d54efc4927899c1048d01ea7c15265ce87858da25447ac28a1ffaa56f3c23",
    "src/engine/strategy_base.py":
        "869dc20ca561adc561a9ebe9fdb5fe5a3e097f7ec176fdf274d577d509de9252",
    # 🔁 cycle296(2026-09-17) 재핀 — 사용자 승인 `issue()` 매니저 단위 in-flight 합류(`src/auth/**`). 같은 값을 10곳 동시 갱신했다.
    "src/auth/token.py":
        "bfbdcfbe2bd595055bcc38f5e094e2815ef67854f2153aa20c40629c9e4e6764",
    "src/auth/hashkey.py":
        "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    "src/realtime/handler.py":
        "23768e6d89ed54b626cce2645a07cc5472ce10120c0b1c81f5d6436ff521ed47",
    "src/realtime/websocket.py":
        "d4c443bde2ed7aeafba3e9471db0ca4efc15a654610555435145a9b305150c5b",
    "src/realtime/websocket_pool.py":
        "8b02442bcf5f558d6f7095b47d2016f004e3746e07ddc91dae8768b1dd46a10d",
    # 🔁 cycle290(킬스위치 등재, 2026-09-13) 재핀 — `DEFAULT_PARAMS` 말미 2키 추가뿐.
    "src/engine/strategies/momentum.py":
        "50d5c0b9a232d6110f6b85fc524569853f2b8edffe2fd44adc24289800b95ae2",
    "src/engine/strategies/donchian_swing.py":
        "cc57e5673f9982aca97f61677084e040171fff307483fedf10459b567a4679e3",
    "src/engine/strategies/kojiro.py":
        "9477790e9d20eb6d17f36fc7586ada77ac5e2e4b0136a334888244afdb7e9cbc",
    "src/engine/strategies/vcp_breakout.py":
        "5b324b34335f922f82b848ae2313e08660bde75c02d12432867ed224e9709228",
    "src/engine/strategies/bull_flag_breakout.py":
        "0feb3b629bab5ad08ad589315ca12e76b57a73950b948570a78dfe84ba792595",
}

# cycle272 시점 = cycle274 배선 **이전**의 메서드 세그먼트 sha. C11 은 이 값으로의
# **복귀**를 요구한다(전략 원상 복구의 유일한 기계적 증거).
_CYCLE272_METHOD_SHA = {
    ("vb", "check_buy_signal"):
        "e620ae0d14a71f916550ee13f57edff12e1b84c12b8a4712b29583b44b56f20a",
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
# C13 — 8영역 나머지 + scheduler + strategy_base + 전략 5파일 byte 동일
# ===========================================================================
@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_c5_1_untouchable_files_byte_identical(rel: str) -> None:
    """C13 (HIGH) — `order_engine.py` 를 뺀 8영역 + scheduler + strategy_base + 전략 5파일 불변.

    이 사이클이 접촉 승인을 받은 8영역 파일은 **`order_engine.py` 하나뿐**이다.
    """
    assert _content_sha(rel) == _BASE_SHA[rel], (
        f"{rel} 이 base(34ba9e6) 와 다르다 — 접촉 허용은 order_engine.py 하나뿐"
    )


def test_c5_1b_realtime_and_auth_have_no_new_python_files() -> None:
    """C13 — `src/realtime/**`·`src/auth/**` 에 신규 `.py` 가 생기지 않았다."""
    seen = {
        p.relative_to(_ROOT).as_posix()
        for d in ("realtime", "auth") for p in (_SRC / d).rglob("*.py")
        if p.name != "__init__.py"
    }
    assert seen <= set(_BASE_SHA), f"8영역 디렉터리에 신규 파일: {sorted(seen - set(_BASE_SHA))}"


def test_c5_2_scheduler_line_count_is_pinned() -> None:
    """C13 — `scheduler.py` 정확 라인 핀 = cycle276 무접촉의 대리 지표.

    🔴 함수명에서 숫자를 뺐다(`…_is_3897` → `…_is_pinned`) — 이름에 값을 박으면
    정당한 라인 변경마다 개명이 따라온다.
    cycle292(2026-09-14)가 `_subscribe_market_operation_tickers` 176줄을 신규 leaf
    `src/engine/market_op_subscribe.py` 로 추출(행위 변경 0 · 5줄 위임 wrapper)해
    3,897 → 3,726 으로 줄었다. 🔴 정확 핀을 상한 핀(`< 3900`)으로 완화하지 않는다 —
    그러면 확보한 174줄 예산의 무단 증식을 아무도 못 잡는다.
    """
    lines = len(_read(_SCHEDULER).splitlines())
    assert lines == 3785, f"scheduler.py {lines}L (기대 3,785 — cycle283 뒤 3,897 → cycle292 leaf 추출 → cycle298 재핀)"


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
_ALL_SEVEN_STRATEGY_RELS = frozenset(
    f"src/engine/strategies/{name}.py"
    for name in (
        "momentum", "volatility_breakout", "long_tail_volatility",
        "donchian_swing", "bull_flag_breakout", "vcp_breakout", "kojiro",
    )
)


@pytest.mark.parametrize("key", _KEYS)
def test_c6_3a_four_keys_live_in_exactly_vb_and_ltv(key: str) -> None:
    """C12 — 4키를 `DEFAULT_PARAMS` 에 가진 전략 파일 = **7전략 전부**.

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
    assert sorted(set(owners)) == sorted(_ALL_SEVEN_STRATEGY_RELS), (
        f"`{key}` 보유 전략 {sorted(set(owners))} (기대 = 7전략 전부)"
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
# C14 / C15 — 자매 핀 4곳 대칭 ("핀은 항상 4곳")
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


def test_c6_4b_cycle223_sibling_content_pin_matches_current_source() -> None:
    """C15 — cycle223 `_CYCLE228_STRATEGY_CONTENT_SHA` 의 VB·LTV **파일 sha 는 현재값**.

    메서드 핀은 cycle272 로 **복귀**하지만 파일 sha 는 4키가 남아 cycle272 와 다르다 —
    두 핀의 방향이 다르다는 것이 이 사이클의 미묘한 지점이다.
    """
    text = (_AST_DIR / "test_cycle223_ast_donchian_exit_fix.py").read_text(encoding="utf-8")
    for rel in (_VB_REL, _LTV_REL):
        m = re.search(rf'"{re.escape(rel)}"\s*:\s*\n?\s*"([0-9a-f]{{64}})"', text)
        if m is None:
            continue  # dict 가 비워졌으면 재핀 의무 없음(그 편이 정상)
        assert m.group(1) == _content_sha(rel), (
            f"`_CYCLE228_STRATEGY_CONTENT_SHA[{rel}]` 가 현재 소스와 다르다 — 자매 핀 재핀 누락"
        )


#: `_APPROVED_CONTENT_SHA`(= `test_cycle222a3_ast_followup_fixes.py`)에 등록돼도 좋은
#: 8영역 파일 — **사용자 승인을 받은 사이클만** 여기 한 줄을 더한다.
#:   · `order_engine.py` = cycle276(AI 매수평가 주문 발화 시점 이동) → cycle287 재핀
#:   · `scanner.py`      = cycle283(오늘봉 커트오프 15:40 → 20:00) → **cycle299 재핀**
#:     (일봉 backfill 창 `_DAILY_LOAD_VCP_BACKFILL_DAYS` 120 → 220, 사용자 명시
#:     8영역 승인 2026-09-17). 등록 **집합은 그대로**이고 그 파일의 sha 만 옮겼다 —
#:     승인 목록이 늘어난 것이 아니므로 이 집합에 새 줄이 생기지 않는다.
#:   · `api/order.py`    = cycle287(시각이 거래소·호가유형을 정한다, docstring 만)
#:   · `websocket.py` / `websocket_pool.py` = cycle293(시세 채널 리졸버 2단계 —
#:     등가 비교 → 집합 멤버십 + 병행 dict `_ticker_to_tr_id`, 사용자 승인 2026-09-14)
#:   · `risk.py`      = cycle293 §3-E B-1 **매수 축 보존 게이트**. 🔴 오케스트레이션
#:     지시는 `risk.py` diff 0 을 요구했고 이 항목은 그것과 상충한다 — **사용자
#:     승인 1건이 열려 있다**(판단 근거 =
#:     `test_cycle293_ast_channel_resolver.py::test_a1b` docstring). 승인이 거절되면
#:     이 줄과 자매 4곳의 `risk.py` 핀을 함께 지우고 리졸버를 HIGH 전용으로 좁힌다.
#:   · `src/realtime/CLAUDE.md` = cycle293 **문서 전용**. `src/realtime/**` 이 8영역
#:     디렉터리라 `.md` 도 diff 가드에 잡힌다 — 프로덕션 코드 영향 0 이고, 적대
#:     검증이 "합집합 서술이 이제 참이다 / 프로브 격리 기준이 채널→정체성으로
#:     바뀌었다 / `H0UNCNT0` 무송출 사실이 이 문서에 0회 등장한다" 를 지적해 갱신했다.
#:   · `src/auth/token.py` = cycle296(`TokenManager.issue()` 매니저 단위 in-flight
#:     합류, 사용자 결정 "결정 1 진행" 2026-09-17). 범위 = `issue()` + `__init__`
#:     신규 필드뿐 — `get_token`/`revoke`/`_is_valid` 는 세그먼트 sha 로 무접촉 증명.
#:   · `src/auth/CLAUDE.md` = **문서 전용**(2026-09-17 문서 개편). `src/auth/**` 이
#:     8영역 디렉터리라 `.md` 도 diff 가드에 잡힌다 — `src/realtime/CLAUDE.md` 와 같은
#:     계열이고 프로덕션 코드 영향 0. 소제목의 사이클 번호를 규칙 이름으로 바꾸고
#:     걷어낸 경위를 `docs/history/src-auth-CLAUDE.history.md` 로 옮겼다.
_APPROVED_EIGHT_AREA_PINS = {
    _ORDER_ENGINE_REL, "src/engine/scanner.py", "src/api/order.py",
    "src/realtime/websocket.py", "src/realtime/websocket_pool.py",
    "src/engine/risk.py", "src/realtime/CLAUDE.md", "src/auth/token.py",
    "src/auth/CLAUDE.md",
}


def test_c6_4c_cycle222a3_approvals_match_the_explicit_list() -> None:
    """C14 (HIGH) — 8영역 diff 가드의 승인 등록이 **명시 목록과 정확히 일치**한다.

    ⚠️ 구 이름 `test_c6_4c_cycle222a3_approves_only_order_engine`
    (2026-09-17 cycle299 에서 개명). 그 이름은 cycle283 이 기대 집합을
    `_APPROVED_EIGHT_AREA_PINS` 로 올린 순간부터 사실과 어긋나 있었다 — 집합은
    이미 9항목이고 `order_engine.py` 는 그중 하나다. 이름이 단언보다 좁게
    읽히면 다음 사람이 "승인이 하나뿐이어야 한다" 로 오독해 정당한 등록을
    되돌린다(cycle263 계열 오도). 단언 자체는 한 글자도 약해지지 않았다.
    2026-09-14 실측 로그(`_workspace/00_URGENT_WORKLIST.md`)가 구 이름으로
    이 테스트를 부른다.

    승인 sha 핀은 "이 사이클이 이 파일을 바꾼다" 는 명시 선언이자 자기소멸 기전이다
    (내용이 1 byte 라도 더 바뀌면 FAIL, 커밋되면 diff 에서 사라져 죽은 값이 된다).
    등록되지 않은 8영역 파일이 이 dict 에 들어가면 승인 범위가 조용히 넓어진다.

    🔁 2026-09-11 (cycle283) 재표현 — 종전에는 `{order_engine.py}` 하나로 하드코딩돼
    있었다. 그 서술의 *의도*는 "이 사이클이 바꾸는 파일 하나뿐" 이 아니라 **"승인 목록이
    조용히 늘지 않는다"** 이고, 후속 사이클이 사용자 승인을 받아 다른 8영역 파일을
    등록하는 것은 그 의도를 깨지 않는다. 그래서 기대 집합을 모듈 상수
    `_APPROVED_EIGHT_AREA_PINS` 로 올려 **명시적으로만** 늘어나게 했다 —
    cycle283 이 `scanner.py`(커트오프 20:00, 사용자 승인)를 추가한 것이 그 첫 사례다.
    """
    mod = _AST_DIR / "test_cycle222a3_ast_followup_fixes.py"
    text = mod.read_text(encoding="utf-8")
    m = re.search(r"_APPROVED_CONTENT_SHA: dict\[str, str\] = \{(.*?)\n\}", text, re.S)
    assert m, "`_APPROVED_CONTENT_SHA` dict 를 찾지 못했다"
    entries = dict(re.findall(r'"([^"]+)"\s*:\s*\n?\s*"([0-9a-f]{64})"', m.group(1)))
    assert set(entries) == _APPROVED_EIGHT_AREA_PINS, (
        f"승인 등록 {sorted(entries)} (기대 {sorted(_APPROVED_EIGHT_AREA_PINS)}) — "
        "새 항목은 **사용자 승인을 받은 사이클만** 추가한다"
    )
    for rel_path, pinned in entries.items():
        assert pinned == _content_sha(rel_path), (
            f"승인 sha 핀이 현재 `{rel_path}` 내용과 다르다 — 등록 후 추가 편집"
        )
