# DEST: tests/unit/ast/test_cycle273a_ast_partial_optin_and_timer.py
"""cycle273a Red (AST) — 행위 테스트로는 잡히지 않는 **구조 계약**만 정적으로 고정한다.

명세 = `_workspace/red/cycle273a_c235v2_cancel_timer_and_partial_spec.md`
행위 가드 = `test_cycle273a_cancel_timer_on_full_fill.py` ·
            `test_cycle273a_partial_row_full_fill_no_correction.py`

| # | 가드 | 지키는 것 | HEAD |
|---|---|---|---|
| G-273-AST1 | `match_partial=True` 는 소스 전체에 **정확히 2회**, 둘 다 `update_trade_status(..., TradeStatus.COMPLETED, ...)` | §3.3 — 전역 확대 금지 | **RED** |
| G-273-AST2 | 🔴 `TradeStatus.CANCELLED` 를 넘기는 `update_trade_status` 호출에 `match_partial` 키워드 **0건** | C5/C6 봉인(PARTIAL→CANCELLED 뒤집힘) | GREEN(영구) |
| G-273-AST3 | 매수·매도 **전량 체결 분기**(`if total_filled >= ordered_qty`) 안에 `_pending_cancel_tasks` 참조가 **존재** | 되살림 차단(가드의 역방향) | **RED** |
| G-273-AST4 | 그 참조 자리에 `order_no` 비교가 **함께** 있다 | §1.4 — `pop(ticker)` 단독 금지 | **RED** |

## 규약

- `ast.dump` sha 를 핀하지 않는다(3.12 CI ↔ 3.13 로컬 출력 상이 — cycle256 G-250-5).
- 소스 스캔에 `git grep`/`git ls-files` 를 쓰지 않는다(미추적 파일 실종 — cycle259 S4b).
  전부 `Path.rglob` + AST 다.
- 기준선이 사라지면 **명시 FAIL** 시킨다(vacuous PASS 재발 차단, 사이클 224).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# 루트는 **임포트된 `src` 패키지의 위치**에서 유도한다 — `parents[N]` 하드코딩은
# 파일이 옮겨 다니는 Red 단계에서 조용히 빗나가고, `git ls-files` 는 미추적 파일을
# 놓친다(cycle259 S4b). 최종 목적지(tests/unit/ast/)에서도 동일하게 동작한다.
import src as _src_pkg  # noqa: E402

_SRC = Path(_src_pkg.__file__).resolve().parent
_ROOT = _SRC.parent
_ORDER_ENGINE = _SRC / "engine" / "order_engine.py"


def _py_files() -> list[Path]:
    return [p for p in _SRC.rglob("*.py") if p.is_file()]


def _calls_named(tree: ast.AST, name: str) -> list[ast.Call]:
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        label = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if label == name:
            out.append(node)
    return out


def _status_arg_label(call: ast.Call) -> str | None:
    """`update_trade_status` 의 3번째 위치 인자(status) 를 `TradeStatus.X` 로 읽는다."""
    if len(call.args) < 3:
        return None
    node = call.args[2]
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "TradeStatus":
            return node.attr
    return None


def _kw(call: ast.Call, name: str) -> ast.keyword | None:
    for k in call.keywords:
        if k.arg == name:
            return k
    return None


def _full_fill_if(fn: ast.AST) -> ast.If | None:
    """`if total_filled >= ordered_qty:` 노드."""
    for node in ast.walk(fn):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        test = node.test
        left = test.left
        if not (isinstance(left, ast.Name) and left.id == "total_filled"):
            continue
        if not test.ops or not isinstance(test.ops[0], ast.GtE):
            continue
        right = test.comparators[0]
        if isinstance(right, ast.Name) and right.id == "ordered_qty":
            return node
    return None


def _func(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


# ---------------------------------------------------------------------------
# G-273-AST1 — match_partial=True 는 정확히 2회, 둘 다 COMPLETED
# ---------------------------------------------------------------------------
def test_g273_ast1_match_partial_true_exactly_twice_on_completed():
    """RED (HEAD) — 아직 0회다. Green 이후 2회를 넘으면 곧 전역 확대다."""
    sites: list[tuple[str, int, str | None]] = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in _calls_named(tree, "update_trade_status"):
            kw = _kw(call, "match_partial")
            if kw is None:
                continue
            if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                sites.append((str(path.relative_to(_ROOT)), call.lineno, _status_arg_label(call)))

    assert len(sites) == 2, (
        f"`match_partial=True` 는 정확히 2회(매수·매도 전량 체결 COMPLETED)여야 한다 — 실측 {sites}"
    )
    assert all(label == "COMPLETED" for _p, _l, label in sites), (
        f"`match_partial=True` 가 COMPLETED 이외의 status 호출에 붙었다 — {sites}"
    )
    assert {p for p, _l, _s in sites} == {"src/engine/order_engine.py"}, (
        f"`match_partial=True` 가 order_engine 밖으로 퍼졌다 — {sites}"
    )


# ---------------------------------------------------------------------------
# G-273-AST2 — 🔴 CANCELLED 호출에는 match_partial 이 절대 붙지 않는다 (영구)
# ---------------------------------------------------------------------------
def test_g273_ast2_cancelled_calls_never_widen():
    """GREEN(영구 가드) — 이 파일에서 가장 중요한 한 줄(§3.3).

    PARTIAL 행이 CANCELLED 로 뒤집히면 정산(COMPLETED∪PARTIAL)에서도 sync
    (CANCELLED 제외)에서도 빠져 **부분 체결 사실 자체가 소실**된다.
    """
    cancelled_sites = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in _calls_named(tree, "update_trade_status"):
            if _status_arg_label(call) != "CANCELLED":
                continue
            cancelled_sites.append((str(path.relative_to(_ROOT)), call.lineno))
            assert _kw(call, "match_partial") is None, (
                f"{path.relative_to(_ROOT)}:{call.lineno} — CANCELLED 호출에 "
                f"match_partial 이 붙었다(§3.3 금기)"
            )

    assert len(cancelled_sites) >= 2, (
        f"기준선 소실 — CANCELLED 호출(C5·C6)이 2곳 미만이다: {cancelled_sites}. "
        "이 가드가 검사할 대상이 없으면 조용히 통과한다(vacuous PASS 차단)"
    )


# ---------------------------------------------------------------------------
# G-273-AST3/4 — 전량 체결 분기 안의 타이머 해제 + order_no 게이트
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fn_name", ["_handle_buy_fill", "_handle_sell_fill"])
def test_g273_ast3_full_fill_branch_touches_pending_cancel_tasks(fn_name: str):
    """RED (HEAD) — 전량 체결 분기에 `_pending_cancel_tasks` 참조 0건."""
    tree = ast.parse(_ORDER_ENGINE.read_text(encoding="utf-8"))
    fn = _func(tree, fn_name)
    assert fn is not None, f"기준선 소실 — {fn_name} 정의를 찾지 못했다"

    branch = _full_fill_if(fn)
    assert branch is not None, (
        f"기준선 소실 — {fn_name} 안에 `if total_filled >= ordered_qty:` 가 없다"
    )

    names = {
        node.attr for node in ast.walk(branch) if isinstance(node, ast.Attribute)
    }
    assert "_pending_cancel_tasks" in names, (
        f"{fn_name} 전량 체결 분기가 잔여취소 타이머를 손대지 않는다 "
        f"(C235-V2-a — 004990 09-10 09:05)"
    )


@pytest.mark.parametrize("fn_name", ["_handle_buy_fill", "_handle_sell_fill"])
def test_g273_ast4_timer_release_is_gated_by_order_no(fn_name: str):
    """RED (HEAD) — 해제는 반드시 `order_no` 비교 뒤에서만 일어난다(§1.4).

    `_pending_cancel_tasks` 의 키는 **ticker** 이고 매수·매도가 같은 dict 를 쓴다.
    ticker 만 보고 지우면 남의 타이머가 실종된다.
    """
    tree = ast.parse(_ORDER_ENGINE.read_text(encoding="utf-8"))
    fn = _func(tree, fn_name)
    branch = _full_fill_if(fn) if fn is not None else None
    assert branch is not None, f"기준선 소실 — {fn_name} 전량 체결 분기 부재"

    touches = [
        node for node in ast.walk(branch)
        if isinstance(node, ast.Attribute) and node.attr == "_pending_cancel_tasks"
    ]
    assert touches, f"{fn_name} 전량 체결 분기에 타이머 해제가 없다 (AST3 참조)"

    order_no_compare = any(
        isinstance(node, ast.Compare)
        and any(
            isinstance(sub, ast.Name) and sub.id == "order_no"
            for sub in ast.walk(node)
        )
        for node in ast.walk(branch)
    )
    assert order_no_compare, (
        f"{fn_name} 전량 체결 분기의 타이머 해제에 order_no 일치 게이트가 없다 — "
        f"`_pending_cancel_tasks.pop(ticker)` 단독은 매수 잔량 취소를 실종시킨다(§1.4)"
    )


def test_ast5_timestamp_bindings_are_datetime_objects():
    """G-273a-AST5(영속) — `src/db/trade_history.py` 의 `timestamp >=/<=` 절에 붙는 바인딩은
    전부 `datetime.fromisoformat(...)` 객체여야 한다(str 바인딩은 asyncpg DataError —
    사이클 M6 DATE str 사고 · cycle273a 검증 r2 HIGH#1, 같은 계열 3회차 재발 차단)."""
    from pathlib import Path
    src = Path("src/db/trade_history.py").read_text(encoding="utf-8")
    assert "args.append(_today_kst_iso())" not in src, "KST 하한을 str 로 바인딩하는 줄이 되살아났다"
    clauses = src.count("timestamp >=") + src.count("timestamp <=")
    assert clauses >= 1
    assert src.count("datetime.fromisoformat(") >= clauses, (
        "timestamp 비교 절 수보다 datetime.fromisoformat 바인딩 수가 적다 — str 바인딩 의심"
    )
