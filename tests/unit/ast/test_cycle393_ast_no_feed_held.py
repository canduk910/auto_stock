"""cycle393 AST — `[no_feed_held]` 증거 판정의 구조 가드.

> 정본 명세: `scratchpad/c393/spec.md` §3.2 · §4 · §5 · §7 · §9.4

행위 테스트(`tests/unit/engine/test_cycle393_no_feed_held_evidence.py`)가 표본으로 못 덮는
구조 계약을 소스에서 직접 잠근다. 대상 함수 집합은 이름 목록이 아니라 **관측기
`_observe_no_feed_held` 에서 모듈 안으로 닿는 함수 전부**(전이 폐포)다 — 창 헬퍼·W 헬퍼의
이름이 무엇이든 관측기가 부르면 같은 규약을 진다.

| ID | 검사 | 막는 것 |
|----|------|---------|
| A1 | 관측기 폐포 안 `ticker_last_tick` 0 | REST 폴이 찍는 값을 무송출 증거로 쓰기(거짓 음성·양성 동시) |
| A2 | 관측기 폐포 안 시각 리터럴 0(`"HH:MM"` · `time(정수)` · `.replace(hour=)`) | 판정 창을 표 대신 리터럴로 박기(G-252-6 승계) |
| A3 | KIS 호출 = `_probe_krx_acml_vol` 안 `inquire_acml_vol` 1곳 · `kis_request`/`kis_get_quote` 0 · `src.api` 모듈 상단 import 0 | Rate Limit·풀 라우팅·메트릭 우회, 테스트 seam 이탈 |
| A4 | `check_and_resubscribe_stale` 안 `await _observe_no_feed_held(...)` = 2 — 「모두 fresh」 블록 안 `return` 앞 1 + HIGH 루프·세션 상세 뒤 1, 루프 앞 다른 최상위 문장 0 | REST 대기가 HIGH 재등록을 늦추기 |
| A5 | 관측기 본문 = `try/except Exception` 하나 · `BaseException`/맨 `except` 0 · 흔적 `[no_feed_held_observe_failed]` | 관측 예외 전파 · `CancelledError` 삼키기 |
| A6 | `_maybe_emit_no_feed_held` WARNING 문자열에 낡은 문구 0 | 「프레임 0(연속체결 미수신)」·「H0UNCNT0」·「09:05~15:20」 부활 |
| A7 | 새 상수 5개 = 모듈 상수(값 명세대로) · `PARAM_RANGES`/`DEFAULT_PARAMS`/`INT_PARAMS` 편입 0 | 관측 상수를 매매 파라미터·AI 자문 경로로 열기 |
| A8 | 관측기 폐포 안 `asyncio.` 속성 접근 0 | 테스트가 바꾸는 `core.asyncio`(`_SleepSpy`)에 타임아웃이 묶이기(명세 §5.8) |
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CORE_REL = "src/engine/stale_watcher_core.py"
_CORE = _REPO_ROOT / _CORE_REL

_OBSERVER = "_observe_no_feed_held"
_SEAM = "_probe_krx_acml_vol"
_EMITTER = "_maybe_emit_no_feed_held"
_CHECK = "check_and_resubscribe_stale"

_CONSTANTS = (
    "NO_FEED_OPEN_GRACE_SECS",
    "NO_FEED_PROBE_INTERVAL_SECS",
    "NO_FEED_CONFIRM_SECS",
    "NO_FEED_PROBE_TIMEOUT_SECS",
    "NO_FEED_PROBES_PER_CYCLE",
)


def _tree() -> ast.Module:
    return ast.parse(_CORE.read_text(encoding="utf-8"))


def _module_funcs(tree: ast.Module) -> dict[str, ast.AST]:
    return {
        n.name: n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _require(funcs: dict, name: str):
    node = funcs.get(name)
    if node is None:
        pytest.fail(f"cycle393 — `{name}` 미정의 ({_CORE_REL}) — Red")
    return node


def _observer_closure(tree: ast.Module) -> dict[str, ast.AST]:
    """관측기에서 모듈 안으로 닿는 함수 전부(이름 참조 기준 전이 폐포) + seam."""
    funcs = _module_funcs(tree)
    _require(funcs, _OBSERVER)
    _require(funcs, _SEAM)
    seen: dict[str, ast.AST] = {}
    stack = [_OBSERVER, _SEAM]
    while stack:
        name = stack.pop()
        if name in seen or name not in funcs:
            continue
        seen[name] = funcs[name]
        for sub in ast.walk(funcs[name]):
            if isinstance(sub, ast.Name) and sub.id in funcs and sub.id not in seen:
                stack.append(sub.id)
    return seen


# ===========================================================================
# A1 — ticker_last_tick 금지
# ===========================================================================
def test_a1_observer_closure_never_reads_ticker_last_tick():
    """REST 폴(`scheduler._run_swing_rest_poll_once` → `on_tick`)이 `ticker_last_tick` 을 찍는다.

    그 값으로 판정하면 donchian·kojiro 보유는 WS 가 죽어도 「부재」 가 안 되고(거짓 음성),
    거래 없는 저유동 보유는 「부재」 라 경보가 된다(거짓 양성) — 명세 §3.2 기각 대안.
    """
    offenders: list[str] = []
    for name, fn in _observer_closure(_tree()).items():
        for sub in ast.walk(fn):
            hit = (
                (isinstance(sub, ast.Name) and sub.id == "ticker_last_tick")
                or (isinstance(sub, ast.Attribute) and sub.attr == "ticker_last_tick")
                or (isinstance(sub, ast.alias) and "ticker_last_tick" in (sub.name, sub.asname))
                or (isinstance(sub, ast.Constant) and sub.value == "ticker_last_tick")
            )
            if hit:
                offenders.append(f"{name} L{getattr(sub, 'lineno', '?')}")
    assert offenders == [], (
        f"`[no_feed_held]` 판정이 `ticker_last_tick` 을 읽는다 — {offenders}. "
        "WS 증거는 `tick_volume.get_observed_acml_vol` 만 쓴다"
    )


# ===========================================================================
# A2 — 시각 리터럴 0
# ===========================================================================
_HHMM = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
_TIME_CTORS = {"time", "dt_time", "_time", "dtime"}


def test_a2_observer_closure_has_no_time_literals():
    """판정 창 경계는 `market_state.get_market_table` 의 K3(REGULAR) 행에서만 얻는다."""
    offenders: list[str] = []
    for name, fn in _observer_closure(_tree()).items():
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and _HHMM.match(sub.value):
                offenders.append(f"{name} L{sub.lineno}: {sub.value!r}")
            if not isinstance(sub, ast.Call):
                continue
            fname = (sub.func.id if isinstance(sub.func, ast.Name)
                     else sub.func.attr if isinstance(sub.func, ast.Attribute) else None)
            int_args = [a for a in sub.args
                        if isinstance(a, ast.Constant) and isinstance(a.value, int)
                        and not isinstance(a.value, bool)]
            if fname in _TIME_CTORS and int_args:
                offenders.append(f"{name} L{sub.lineno}: {fname}({', '.join(str(a.value) for a in int_args)})")
            if fname == "replace" and any(
                k.arg in ("hour", "minute") and isinstance(k.value, ast.Constant)
                for k in sub.keywords
            ):
                offenders.append(f"{name} L{sub.lineno}: .replace(hour/minute=리터럴)")
    assert offenders == [], f"관측기 폐포에 시각 리터럴 — {offenders}"


def test_a2b_window_read_from_market_table():
    """창 경계 출처 = `get_market_table` (관측기 폐포 어딘가에서 호출)."""
    names = set()
    for fn in _observer_closure(_tree()).values():
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Attribute):
                names.add(sub.attr)
            elif isinstance(sub, ast.Name):
                names.add(sub.id)
            elif isinstance(sub, ast.alias):
                names.add(sub.asname or sub.name)
    assert "get_market_table" in names, (
        "판정 창은 `src.engine.market_state.get_market_table(now.date())` 의 KRX·REGULAR 행에서 "
        "얻는다(명세 §3.4) — 관측기 폐포에 참조가 없다"
    )


# ===========================================================================
# A3 — KIS 호출 단일 지점
# ===========================================================================
def test_a3_single_kis_call_site_inside_seam():
    tree = _tree()
    funcs = _module_funcs(tree)
    seam = _require(funcs, _SEAM)

    seam_ids = {id(n) for n in ast.walk(seam)}
    calls_total = 0
    outside: list[str] = []
    for sub in ast.walk(tree):
        is_ref = (
            (isinstance(sub, ast.Name) and sub.id == "inquire_acml_vol")
            or (isinstance(sub, ast.Attribute) and sub.attr == "inquire_acml_vol")
        )
        if isinstance(sub, ast.Call):
            f = sub.func
            if (isinstance(f, ast.Name) and f.id == "inquire_acml_vol") or (
                isinstance(f, ast.Attribute) and f.attr == "inquire_acml_vol"
            ):
                calls_total += 1
        if is_ref and id(sub) not in seam_ids:
            outside.append(f"L{sub.lineno}")
    assert outside == [], f"`inquire_acml_vol` 참조가 seam 밖에 있다 — {outside}"
    assert calls_total == 1, f"`inquire_acml_vol` 호출 = 정확히 1(seam 안) — actual={calls_total}"

    banned = [
        f"L{sub.lineno}: {sub.id if isinstance(sub, ast.Name) else sub.attr}"
        for sub in ast.walk(tree)
        if (isinstance(sub, ast.Name) and sub.id in ("kis_request", "kis_get_quote"))
        or (isinstance(sub, ast.Attribute) and sub.attr in ("kis_request", "kis_get_quote"))
    ]
    assert banned == [], f"KIS 직접 호출 금지(quotation 경유) — {banned}"

    top_api = [
        f"L{n.lineno}"
        for n in tree.body
        if (isinstance(n, ast.ImportFrom) and (n.module or "").startswith("src.api"))
        or (isinstance(n, ast.Import) and any(a.name.startswith("src.api") for a in n.names))
    ]
    assert top_api == [], f"`quotation` 은 함수 안 lazy import — 모듈 상단 src.api import {top_api}"


# ===========================================================================
# A4 — 호출 위치 두 곳
# ===========================================================================
def _is_observer_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    return (isinstance(f, ast.Name) and f.id == _OBSERVER) or (
        isinstance(f, ast.Attribute) and f.attr == _OBSERVER
    )


def _observer_calls(node: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(node) if _is_observer_call(n)]


def _is_not_stale_tickers(test: ast.AST) -> bool:
    return (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
            and isinstance(test.operand, ast.Name) and test.operand.id == "stale_tickers")


def _is_stale_loop(node: ast.AST) -> bool:
    return (isinstance(node, (ast.For, ast.AsyncFor))
            and isinstance(node.iter, ast.Name) and node.iter.id == "stale_tickers")


def _calls_name(node: ast.AST, name: str) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            if (isinstance(f, ast.Name) and f.id == name) or (
                isinstance(f, ast.Attribute) and f.attr == name
            ):
                return True
    return False


def test_a4_observer_called_exactly_at_two_exits_after_high_loop():
    tree = _tree()
    func = _require(_module_funcs(tree), _CHECK)
    body = func.body

    all_calls = _observer_calls(func)
    assert len(all_calls) == 2, (
        f"`{_OBSERVER}` 호출 = 정확히 2(두 출구) — actual={len(all_calls)}"
    )
    awaited = {id(n.value) for n in ast.walk(func) if isinstance(n, ast.Await)}
    assert all(id(c) in awaited for c in all_calls), "두 호출 모두 `await` 한다"

    loop_idx = next((i for i, n in enumerate(body) if _is_stale_loop(n)), None)
    assert loop_idx is not None, "`for ticker in stale_tickers` 최상위 루프를 찾지 못했다"
    fresh_idx = next(
        (i for i, n in enumerate(body) if isinstance(n, ast.If) and _is_not_stale_tickers(n.test)),
        None,
    )
    assert fresh_idx is not None and fresh_idx < loop_idx, "`if not stale_tickers:` 블록(루프 앞)"

    fresh_block = body[fresh_idx]
    in_fresh = _observer_calls(fresh_block)
    assert len(in_fresh) == 1, f"「모두 fresh」 블록 안 호출 = 1 — actual={len(in_fresh)}"
    ret_lines = [n.lineno for n in ast.walk(fresh_block) if isinstance(n, ast.Return)]
    assert ret_lines and in_fresh[0].lineno < max(ret_lines), (
        "「모두 fresh」 출구의 호출은 그 블록의 `return` **직전**이어야 한다"
    )

    before = [
        f"L{c.lineno}"
        for i, n in enumerate(body[:loop_idx]) if i != fresh_idx
        for c in _observer_calls(n)
    ]
    assert before == [], (
        f"HIGH 재등록 루프 앞(「모두 fresh」 블록 밖) 최상위 문장에 관측기 호출 — {before}. "
        "REST 대기가 그 사이클의 HIGH 재등록을 늦춘다(명세 §4)"
    )
    after = [c for n in body[loop_idx + 1:] for c in _observer_calls(n)]
    assert len(after) == 1, f"HIGH 루프 뒤 호출 = 1 — actual={len(after)}"

    detail_idx = next(
        (i for i, n in enumerate(body) if i > loop_idx and _calls_name(n, "emit_stale_session_detail")),
        None,
    )
    assert detail_idx is not None, "`emit_stale_session_detail(...)` 호출(루프 뒤)을 찾지 못했다"
    assert after[0].lineno > body[detail_idx].lineno, (
        "함수 끝 출구의 호출은 `emit_stale_session_detail(...)` **뒤**(명세 §4)"
    )


# ===========================================================================
# A5 — never-raise 본문
# ===========================================================================
def _handler_names(h: ast.ExceptHandler) -> list[str]:
    if h.type is None:
        return ["<bare>"]
    nodes = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    return [n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else "?"
            for n in nodes]


def _is_trivial_empty_guard(stmt: ast.AST) -> bool:
    """`if not <이름>: return` — 던질 수 없는 조기 반환(명세 §4 「cohort 가 비면 즉시 반환」)."""
    return (
        isinstance(stmt, ast.If) and not stmt.orelse
        and isinstance(stmt.test, ast.UnaryOp) and isinstance(stmt.test.op, ast.Not)
        and isinstance(stmt.test.operand, ast.Name)
        and len(stmt.body) == 1 and isinstance(stmt.body[0], ast.Return)
        and stmt.body[0].value is None
    )


def test_a5_observer_body_is_wrapped_in_try_except_exception():
    fn = _require(_module_funcs(_tree()), _OBSERVER)
    stmts = list(fn.body)
    if stmts and isinstance(stmts[0], ast.Expr) and isinstance(stmts[0].value, ast.Constant) \
            and isinstance(stmts[0].value.value, str):
        stmts = stmts[1:]  # docstring
    while stmts and _is_trivial_empty_guard(stmts[0]):
        stmts = stmts[1:]
    assert len(stmts) == 1 and isinstance(stmts[0], ast.Try), (
        "관측기 본문 최상위는 `try/except Exception` 하나로 감싼다(명세 §5.3) — "
        f"actual top-level={[type(s).__name__ for s in stmts]}"
    )
    names = [n for h in stmts[0].handlers for n in _handler_names(h)]
    assert "Exception" in names, f"`except Exception` 이 있어야 한다 — handlers={names}"
    assert not ({"BaseException", "<bare>", "CancelledError"} & set(names)), (
        f"`CancelledError` 를 막지 않는다 — BaseException·맨 except 금지, handlers={names}"
    )
    tokens = [
        sub.value for h in stmts[0].handlers for sub in ast.walk(h)
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str)
    ]
    assert "[no_feed_held_observe_failed]" in tokens, (
        "흡수 흔적은 `trace_observer_failure(\"[no_feed_held_observe_failed]\", ...)`(debug) — "
        f"handler 문자열={tokens}"
    )


# ===========================================================================
# A6 — 낡은 문구 0
# ===========================================================================
_STALE_WORDINGS = ("프레임 0(연속체결 미수신)", "H0UNCNT0", "09:05~15:20")


def test_a6_emitter_warning_has_no_stale_wording():
    fn = _require(_module_funcs(_tree()), _EMITTER)
    texts: list[str] = []
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.Call):
            continue
        f = sub.func
        if isinstance(f, ast.Attribute) and f.attr == "warning":
            for arg in ast.walk(sub):
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    texts.append(arg.value)
    assert texts, f"`{_EMITTER}` 안 `logger.warning(...)` 을 찾지 못했다"
    joined = "".join(texts)
    hits = [w for w in _STALE_WORDINGS if w in joined]
    assert hits == [], (
        f"`[no_feed_held]` WARNING 에 측정하지 않은 사실·낡은 시각이 남았다 — {hits}"
    )
    assert "tickers=" in joined, "첫 필드 `tickers=` 유지(W7·운영 grep)"


# ===========================================================================
# A7 — 관측 상수 5개
# ===========================================================================
def _module_assign_values(tree: ast.Module) -> dict[str, ast.AST]:
    out: dict[str, ast.AST] = {}
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = n.value
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value is not None:
            out[n.target.id] = n.value
    return out


def test_a7_constants_are_module_level_with_spec_values():
    vals = _module_assign_values(_tree())
    missing = [c for c in _CONSTANTS if c not in vals]
    assert missing == [], f"모듈 상수 미정의 — {missing}"

    def _lit(name):
        v = vals[name]
        return v.value if isinstance(v, ast.Constant) else None

    assert _lit("NO_FEED_OPEN_GRACE_SECS") == 180
    assert _lit("NO_FEED_PROBE_INTERVAL_SECS") == 600
    assert _lit("NO_FEED_PROBE_TIMEOUT_SECS") == 3.0
    assert _lit("NO_FEED_PROBES_PER_CYCLE") == 4
    confirm = vals["NO_FEED_CONFIRM_SECS"]
    assert isinstance(confirm, ast.Name) and confirm.id == "STALE_FRESHNESS_SECS", (
        "`NO_FEED_CONFIRM_SECS` 는 `STALE_FRESHNESS_SECS`(60) 재사용 — 새 숫자를 박지 않는다"
    )


_PARAM_DICT_NAMES = {"PARAM_RANGES", "DEFAULT_PARAMS", "INT_PARAMS"}


def _target_name(t: ast.AST) -> str | None:
    if isinstance(t, ast.Name):
        return t.id
    if isinstance(t, ast.Attribute):
        return t.attr
    return None


def test_a7b_constants_not_in_param_dicts():
    """관측 상수는 매매 파라미터가 아니다 — AI 자문 자동 적용 경로에 열지 않는다."""
    banned = {c for c in _CONSTANTS} | {c.lower() for c in _CONSTANTS}
    offenders: list[str] = []
    for path in sorted((_REPO_ROOT / "src").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign):
                targets, value = n.targets, n.value
            elif isinstance(n, ast.AnnAssign) and n.value is not None:
                targets, value = [n.target], n.value
            else:
                continue
            if not any(_target_name(t) in _PARAM_DICT_NAMES for t in targets):
                continue
            for sub in ast.walk(value):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and sub.value in banned:
                    offenders.append(f"{path.relative_to(_REPO_ROOT)} L{sub.lineno}: {sub.value}")
    assert offenders == [], f"관측 상수가 파라미터 dict 에 편입됐다 — {offenders}"


# ===========================================================================
# A8 — 모듈 asyncio 이름에 기대지 않는다
# ===========================================================================
def test_a8_observer_closure_does_not_use_module_asyncio_name():
    """많은 테스트가 `core.asyncio` 를 `_SleepSpy` 로 바꾼다 — 타임아웃은 import 시점에 따로 묶은
    참조(`from asyncio import wait_for as _wait_for` 류)로 건다(명세 §5.8)."""
    offenders = [
        f"{name} L{sub.lineno}: asyncio.{sub.attr}"
        for name, fn in _observer_closure(_tree()).items()
        for sub in ast.walk(fn)
        if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name)
        and sub.value.id == "asyncio"
    ]
    assert offenders == [], f"관측기 폐포가 모듈 `asyncio` 이름을 쓴다 — {offenders}"
