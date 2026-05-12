"""POST_NXT 보드 진입 시 `_confirm_breakout_open_prices(board="post_nxt")` 호출 보장.

결함 배경 (2026-05-12):
- `scheduler.start()` 흐름에서 15:30 KRX 메인 마감 → NXT 애프터 전환 후
  `_confirm_breakout_open_prices()` 호출이 **누락**되어 있었음.
- 그 결과 VB/LTV 후보 종목의 `_targets[ticker]["boards"]["post_nxt"]["open_price"]`
  가 영영 채워지지 않아 사용자 화면에 "시가 대기" 종목 잠복.
- PRE_NXT(08:00) / MAIN(09:00:05) 진입 시점엔 정상 호출되는데, POST_NXT 만 빠져있던
  구멍을 막는 1줄 추가.

본 테스트는 무한 루프 함수 `start()` 를 통째로 실행하지 않고, **소스 AST 정적 검사**
로 호출 시퀀스를 검증한다. 흐름 시뮬레이션 대비:
- (a) 외부 의존성(WebSocket/체결통보 구독/AI자문/정산)을 전부 모킹할 필요 없음
- (b) 시각 흐름을 가짜 시간으로 강제할 필요 없음
- (c) "라인 순서" 보존 — 호출이 `TIME_KRX_MAIN_CLOSE` 대기 이후, 그리고
  `TIME_NXT_POST_BUY_STOP` 대기 이전에 있어야 한다는 사양을 검증

회귀 보호 4 케이스:
- A: POST_NXT 진입 시점 `_confirm_breakout_open_prices(board="post_nxt")` 호출 존재
- B: 재시작(15:20 이후 진입) 흐름도 같은 line 을 통과 → 동일 호출 1회 보장
- C: MAIN 시가 확정 호출(`board="main"`)은 그대로 존재
- D: PRE_NXT 시가 확정 호출(board 인자 없음 = 자동 결정)은 그대로 존재
"""

from __future__ import annotations

import ast
import inspect

import pytest

from src.engine.scheduler import TradingScheduler

pytestmark = pytest.mark.integration


def _start_func_ast() -> ast.AsyncFunctionDef:
    """`TradingScheduler.start` 의 AST 노드를 반환."""
    src = inspect.getsource(TradingScheduler.start)
    # inspect.getsource 는 들여쓰기를 포함해 반환 — dedent 후 parse
    src = inspect.cleandoc(src)
    # cleandoc 는 docstring 정리용. 진짜 dedent.
    import textwrap

    src = textwrap.dedent(inspect.getsource(TradingScheduler.start))
    module = ast.parse(src)
    assert isinstance(module.body[0], ast.AsyncFunctionDef)
    return module.body[0]


def _collect_confirm_calls(func: ast.AsyncFunctionDef) -> list[tuple[int, dict[str, str]]]:
    """`self._confirm_breakout_open_prices(...)` 호출만 추출.

    Returns:
        [(lineno, kwargs_dict_as_strings), ...]
    """
    calls: list[tuple[int, dict[str, str]]] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (
            isinstance(f, ast.Attribute)
            and f.attr == "_confirm_breakout_open_prices"
            and isinstance(f.value, ast.Name)
            and f.value.id == "self"
        ):
            continue
        kwargs: dict[str, str] = {}
        for kw in node.keywords:
            if kw.arg is None:
                continue
            # 단순 상수만 추출(ast.Constant) — board="post_nxt" 같은 케이스
            if isinstance(kw.value, ast.Constant):
                kwargs[kw.arg] = repr(kw.value.value)
            else:
                kwargs[kw.arg] = ast.unparse(kw.value)
        calls.append((node.lineno, kwargs))
    return calls


def _collect_wait_until_calls(func: ast.AsyncFunctionDef) -> list[tuple[int, str]]:
    """`await self._wait_until(<NAME>)` 의 (lineno, NAME) 추출."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (
            isinstance(f, ast.Attribute)
            and f.attr == "_wait_until"
            and isinstance(f.value, ast.Name)
            and f.value.id == "self"
        ):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Name):
            out.append((node.lineno, arg.id))
        elif isinstance(arg, ast.Attribute):
            out.append((node.lineno, arg.attr))
    return out


@pytest.fixture(scope="module")
def start_ast() -> ast.AsyncFunctionDef:
    return _start_func_ast()


# ---------------------------------------------------------------------------
# Case A — POST_NXT 진입 시점 board="post_nxt" 호출 보장
# ---------------------------------------------------------------------------
def test_post_nxt_confirm_call_exists_after_main_close_wait(start_ast):
    """15:30 KRX 메인 마감 대기(`TIME_KRX_MAIN_CLOSE`) *이후* 그리고
    19:50 NXT 애프터 매수 중단 대기(`TIME_NXT_POST_BUY_STOP`) *이전* 에
    `_confirm_breakout_open_prices(board="post_nxt")` 가 존재해야 한다."""
    confirms = _collect_confirm_calls(start_ast)
    waits = _collect_wait_until_calls(start_ast)

    # KRX 메인 마감 대기와 NXT 매수 중단 대기의 라인 위치
    main_close_lines = [ln for ln, name in waits if name == "TIME_KRX_MAIN_CLOSE"]
    post_buy_stop_lines = [ln for ln, name in waits if name == "TIME_NXT_POST_BUY_STOP"]
    assert main_close_lines, "TIME_KRX_MAIN_CLOSE 대기 라인 없음 — 회귀"
    assert post_buy_stop_lines, "TIME_NXT_POST_BUY_STOP 대기 라인 없음 — 회귀"

    main_close_line = main_close_lines[0]
    post_buy_stop_line = post_buy_stop_lines[0]

    # board="post_nxt" 호출이 두 라인 사이에 있어야 한다
    post_nxt_calls = [
        (ln, kw)
        for ln, kw in confirms
        if kw.get("board") == repr("post_nxt")
        and main_close_line < ln < post_buy_stop_line
    ]
    assert post_nxt_calls, (
        "POST_NXT 진입(TIME_KRX_MAIN_CLOSE~TIME_NXT_POST_BUY_STOP) 구간에 "
        "`_confirm_breakout_open_prices(board=\"post_nxt\")` 호출이 없음. "
        "15:30 NXT 애프터 전환 시 시가 확정 폴링 누락 결함 회귀."
    )


# ---------------------------------------------------------------------------
# Case B — 재시작 흐름(15:20 이후 진입)도 같은 라인을 통과
# ---------------------------------------------------------------------------
def test_post_nxt_confirm_is_reachable_in_restart_path(start_ast):
    """`run_daily` 가 15:20 이후 시작될 때도 `_wait_until(TIME_KRX_MAIN_CLOSE)` 는
    즉시 통과 → 같은 board="post_nxt" 호출 라인을 거친다. 즉 분기 안에 갇혀있지 않고
    `if scan_task is None or scan_task.done()` 같은 조건문 *위* 에 위치해야 한다.

    구현 검증: board="post_nxt" 호출이 `if`/`elif`/`else`/`while`/`for` 같은
    조건 컨테이너 안에 들어있지 않고 함수 본문 직계(top-level statements) 또는
    `try`/`except` 직계에 위치하는지 확인.
    """
    target_lineno: int | None = None
    for ln, kw in _collect_confirm_calls(start_ast):
        if kw.get("board") == repr("post_nxt"):
            target_lineno = ln
            break
    assert target_lineno is not None, "board=\"post_nxt\" 호출이 아예 없음 — Case A 와 함께 회귀"

    # AST 경로상 가장 가까운 조건 분기 컨테이너(If/While/For)를 찾는다
    # — 그 컨테이너의 라인 범위가 함수 본문 직계가 아니면(=try/except 안이 아니면) 조건부.
    enclosing_branch_type: str | None = None

    def walk(node: ast.AST, parents: list[ast.AST]) -> None:
        nonlocal enclosing_branch_type
        if enclosing_branch_type is not None:
            return
        if isinstance(node, ast.Call) and getattr(node, "lineno", None) == target_lineno:
            for p in reversed(parents):
                if isinstance(p, (ast.If, ast.For, ast.While)):
                    enclosing_branch_type = type(p).__name__
                    return
                if isinstance(p, ast.AsyncFunctionDef):
                    return  # 본문 직계까지 도달 — 조건분기 없음
                if isinstance(p, (ast.Try, ast.ExceptHandler)):
                    continue  # try 직계는 허용 — 본문 흐름과 동등
            return
        for child in ast.iter_child_nodes(node):
            walk(child, parents + [node])

    walk(start_ast, [])
    assert enclosing_branch_type is None, (
        f"board=\"post_nxt\" 호출이 {enclosing_branch_type} 분기 안에 있어 "
        "15:20 이후 재시작 흐름에서 우회될 수 있음. `if scan_task is None` 같은 "
        "조건문 위에 무조건 실행되도록 배치되어야 한다."
    )


# ---------------------------------------------------------------------------
# Case C — MAIN 시가 확정 호출(board="main") 회귀 보호
# ---------------------------------------------------------------------------
def test_main_board_confirm_call_still_exists(start_ast):
    """기존 09:00:05 KRX 메인 시가 확정 호출은 그대로 존재해야 한다.
    명시 `board="main"` 또는 board 인자 없음(자동 결정 = main 우선) 둘 다 허용.
    """
    confirms = _collect_confirm_calls(start_ast)
    waits = _collect_wait_until_calls(start_ast)

    open_confirm_lines = [ln for ln, name in waits if name == "TIME_KRX_OPEN_CONFIRM"]
    assert open_confirm_lines, "TIME_KRX_OPEN_CONFIRM 대기 라인 없음 — 회귀"
    open_confirm_line = open_confirm_lines[0]

    # KRX 메인 마감 대기까지의 범위 안에 main(또는 인자없음) 호출이 최소 1개
    main_close_lines = [ln for ln, name in waits if name == "TIME_KRX_MAIN_CLOSE"]
    assert main_close_lines
    end_line = main_close_lines[0]

    main_calls = [
        (ln, kw)
        for ln, kw in confirms
        if open_confirm_line < ln < end_line
        and (kw.get("board") == repr("main") or "board" not in kw)
    ]
    assert main_calls, (
        "09:00:05 ~ 15:30 구간에 `_confirm_breakout_open_prices` (main 또는 자동결정) "
        "호출이 없음 — 기존 MAIN 시가 확정 회귀."
    )


# ---------------------------------------------------------------------------
# Case D — PRE_NXT 시가 확정 호출(자동 결정) 회귀 보호
# ---------------------------------------------------------------------------
def test_pre_nxt_board_confirm_call_still_exists(start_ast):
    """기존 08:00 NXT 프리 진입 시 시가 확정 호출은 그대로 존재해야 한다.
    PRE_NXT 시점엔 board 인자 없음(자동 결정) 호출이 정상 동작.
    """
    confirms = _collect_confirm_calls(start_ast)
    waits = _collect_wait_until_calls(start_ast)

    pre_nxt_open_lines = [ln for ln, name in waits if name == "TIME_PRE_NXT_OPEN"]
    open_confirm_lines = [ln for ln, name in waits if name == "TIME_KRX_OPEN_CONFIRM"]
    assert pre_nxt_open_lines and open_confirm_lines

    start_line = pre_nxt_open_lines[0]
    end_line = open_confirm_lines[0]

    # PRE_NXT 진입 ~ MAIN 시가 확정 대기 사이에 board 인자 없는 호출 1개 이상
    pre_nxt_calls = [
        (ln, kw)
        for ln, kw in confirms
        if start_line < ln < end_line and "board" not in kw
    ]
    assert pre_nxt_calls, (
        "08:00 PRE_NXT 진입 시 `_confirm_breakout_open_prices()` (board 인자 없음 = 자동결정) "
        "호출이 없음 — 기존 PRE_NXT 시가 확정 회귀."
    )
