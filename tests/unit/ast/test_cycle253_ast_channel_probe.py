"""cycle253 Red — AST/구조 가드 g253_1: 프로브의 **안전 경계**와 **범위**를 봉인.

> 정본 명세: `spec_cycle253_channel_probe.md` §1(범위/금지) / §2 g253_1
> 설계 메모: `_workspace/forensics/krx_channel_probe_design.md` §2

행위 테스트(`tests/unit/routes/test_cycle253_channel_probe.py`)가 잡지 못하는 **구조**를
고정한다 — 프로브가 HIGH 슬롯을 밀거나, 라이브 통합 채널이 허용 집합으로 승격되거나,
영구 로그 실패가 프로브 행위를 죽이거나, 시정이 8영역/scheduler 로 새는 회귀.

| ID | 검사 | 뮤테이션 표적 |
|----|------|--------------|
| g253_1a | probe 핸들러 3개(POST/GET/DELETE) 존재 + 경로 | 배선 누락 |
| g253_1b | 3 핸들러 본문에 `bypass_limit=True` 0 | 41 cap 우회 → HIGH 보유 시세 강탈 |
| g253_1c | 허용 tr_id 집합에 `"H0UNCNT0"` 0 (+ H0STCNT0·H0NXCNT0 존재) | 라이브 채널 중복 구독 |
| g253_1d | 8영역 · `scheduler.py` · `stale_*` diff 0 | 범위 이탈 |
| g253_1e | 변경 파일이 §1 화이트리스트 안 | 범위 이탈 |
| g253_1f | 3 핸들러 + 이행 호출 모듈 헬퍼 **폐쇄**에 `write_log` 참조 0 (+ 추적기 자기 검증) | logger.info 와 write_log 병행 = system_logs 이중 INSERT(cycle72 G-6) |

⚠️ **g253_1d / g253_1e / g253_1e2 는 사이클 한정 가드 — cycle253 배포(커밋) 후 폐기 대상**이다.
bare `git diff HEAD` 를 영구 동결하면 그 파일의 모든 후속 시정이 무조건 RED 가 된다
(cycle222a `test_a11b_stale_watcher_core_untouched` 를 cycle240 이 재스코프해야 했던
선례, cycle252 G-252-5b 가 고아로 남아 cycle253 워킹트리에서 FAIL 한 선례 — Verify F11).
HEAD 의 `src/routes/realtime.py` 에 프로브가 들어가는 순간 세 케이스는 `pytest.skip` 으로
**자기 은퇴**한다(`_skip_if_cycle_committed`) — skip 메시지가 삭제 신호다.

g253_1b / g253_1c / g253_1f 는 **영구 가드**다 — 프로브가 사는 한 유효한 안전 경계다.

g253_1f 의 종전 판본("핸들러 본문의 write_log 는 try 안")은 **공허**했다(Verify F8) —
구현이 write_log 를 헬퍼 `_persist_probe_log` 로 한 겹 감싸 핸들러 본문 호출이 0 이라
무조건 통과했고, 그 헬퍼가 만들던 이중 INSERT(Verify F1)를 어느 가드도 잡지 못했다.
현 판본은 핸들러에서 도달 가능한 모듈 함수 폐쇄 전체에서 `write_log` 참조 0 을 요구하고,
합성 모듈로 추적기가 헬퍼 우회를 실제로 잡는지 자기 검증한다.
"""

from __future__ import annotations

import ast
import subprocess
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ROUTE_REL = "src/routes/realtime.py"
_ROUTE = _REPO_ROOT / _ROUTE_REL

#: 프로브 엔드포인트 경로 접두 — 라우터 prefix(`/api/realtime`) 아래 상대 경로.
_PROBE_PATH = "/channel-probe"

#: 허용 채널 = KRX 단독 + NXT 단독. 통합 채널은 **라이브** 라 프로브 대상이 아니다.
_ALLOWED_TR_IDS = {"H0STCNT0", "H0NXCNT0"}
_LIVE_TICK_TR_ID = "H0UNCNT0"


def _git(*args: str) -> str:
    res = subprocess.run(
        ["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    if getattr(res, "returncode", 0) != 0:
        raise AssertionError(
            f"git {' '.join(args)} 실패 (rc={res.returncode}) — fail-closed. "
            f"stderr: {(res.stderr or '').strip()}"
        )
    return res.stdout


def _cycle253_committed() -> bool:
    """HEAD 의 `src/routes/realtime.py` 에 이미 프로브가 있으면 True — 사이클 한정 가드 은퇴 신호."""
    res = subprocess.run(
        ["git", "grep", "-q", "channel-probe", "HEAD", "--", _ROUTE_REL],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    return getattr(res, "returncode", 1) == 0


def _skip_if_cycle_committed() -> None:
    """사이클 한정 diff 가드의 자기 은퇴 — 고아 가드가 다음 사이클을 붉히지 않게 (Verify F11)."""
    if _cycle253_committed():
        pytest.skip(
            "cycle253 이 HEAD 에 커밋됨 — 사이클 한정 diff 가드 자기 은퇴. "
            "이 케이스를 삭제하라 (cycle252 G-252-5b 고아 선례)."
        )


def _tree() -> ast.Module:
    return ast.parse(_ROUTE.read_text(encoding="utf-8"))


def _route_decorators(func) -> list[tuple[str, str]]:
    """함수의 `@router.<method>("<path>")` 데코레이터를 (method, path) 로 추출."""
    out: list[tuple[str, str]] = []
    for dec in getattr(func, "decorator_list", []):
        if not isinstance(dec, ast.Call):
            continue
        fn = dec.func
        if not isinstance(fn, ast.Attribute):
            continue
        if not (isinstance(fn.value, ast.Name) and fn.value.id == "router"):
            continue
        if not dec.args:
            continue
        first = dec.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            out.append((fn.attr.lower(), first.value))
    return out


def _handlers_in(tree: ast.Module) -> dict[str, ast.AST]:
    """method → 핸들러 함수 노드 (경로가 `/channel-probe` 로 시작하는 것만)."""
    handlers: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for method, path in _route_decorators(node):
            if path.startswith(_PROBE_PATH):
                handlers[method] = node
    return handlers


def _probe_handlers() -> dict[str, ast.AST]:
    return _handlers_in(_tree())


def _require_handlers() -> dict[str, ast.AST]:
    handlers = _probe_handlers()
    missing = {"post", "get", "delete"} - set(handlers)
    if missing:  # pragma: no cover - Red 단계 경로
        pytest.fail(
            f"cycle253 §1 — `{_ROUTE_REL}` 에 프로브 핸들러 미구현 (Red). "
            f"누락 메서드={sorted(missing)}, 발견={sorted(_probe_handlers())}"
        )
    return handlers


# ===========================================================================
# g253_1a — 배선 (POST/GET 은 `/channel-probe`, DELETE 는 `/{ticker}`)
# ===========================================================================
def test_g253_1a_three_probe_handlers_are_wired():
    handlers = _require_handlers()
    paths = {
        method: [p for m, p in _route_decorators(node) if m == method]
        for method, node in handlers.items()
    }
    assert paths["post"] == [_PROBE_PATH], paths["post"]
    assert paths["get"] == [_PROBE_PATH], paths["get"]
    assert paths["delete"] == [f"{_PROBE_PATH}/{{ticker}}"], paths["delete"]


# ===========================================================================
# g253_1b — `bypass_limit=True` 0 (프로브가 HIGH 슬롯을 밀면 안 된다)
# ===========================================================================
def test_g253_1b_probe_handlers_never_bypass_subscription_limit():
    """`bypass_limit=True` 는 41 cap 을 무시하고 메인 슬롯을 강탈하는 스위치다.

    HIGH(보유·익일청산) 절대 보장이 그 슬롯 위에 서 있으므로, 진단 도구가 그것을
    쓰면 프로브 한 번이 손절 시세를 굶길 수 있다.
    """
    handlers = _require_handlers()
    offenders: list[str] = []
    for method, node in handlers.items():
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            for kw in call.keywords:
                if kw.arg != "bypass_limit":
                    continue
                if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    offenders.append(f"{method} 핸들러 L{kw.value.lineno}")
                elif not (
                    isinstance(kw.value, ast.Constant) and kw.value.value is False
                ):
                    offenders.append(
                        f"{method} 핸들러 L{getattr(kw.value, 'lineno', '?')}"
                        " — bypass_limit 이 리터럴 False 가 아님(동적 값 금지)"
                    )
    assert offenders == [], (
        f"프로브 핸들러의 bypass_limit 위반: {offenders} — 명세 §1 금지"
    )


# ===========================================================================
# g253_1c — 허용 집합에 라이브 통합 채널 없음
# ===========================================================================
def _tr_id_containers(tree: ast.Module) -> list[tuple[int, set[str]]]:
    """문자열 상수 컨테이너(Set/List/Tuple/`Literal[...]`) 를 (lineno, 값집합) 으로."""
    out: list[tuple[int, set[str]]] = []

    def _consts(elts) -> set[str] | None:
        values: set[str] = set()
        for elt in elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                values.add(elt.value)
            else:
                return None
        return values

    for node in ast.walk(tree):
        elts = None
        if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
            elts = node.elts
        elif isinstance(node, ast.Subscript):
            base = node.value
            name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
            if name == "Literal":
                sl = node.slice
                elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
        if elts is None:
            continue
        values = _consts(elts)
        if values:
            out.append((getattr(node, "lineno", 0), values))
    return out


def test_g253_1c_allowed_tr_id_set_excludes_live_unified_channel():
    """허용 집합 = {H0STCNT0, H0NXCNT0}. `H0UNCNT0` 가 들어가면 프로브가 라이브가 된다.

    `_ticker_to_session` 은 tr_key 단일 키라, 통합 채널 프로브는 그 종목의 라이브
    라우팅을 덮어쓴다 — 진단이 시세를 훔치는 경로.
    """
    _require_handlers()
    containers = _tr_id_containers(_tree())

    allowed = [
        (lineno, values) for lineno, values in containers
        if "H0STCNT0" in values
    ]
    assert allowed, (
        f"`{_ROUTE_REL}` 에서 허용 tr_id 집합(H0STCNT0 포함 컨테이너)을 찾지 못했다 — "
        "명세 §1 은 허용 집합을 명시 리터럴로 요구한다"
    )

    offenders = [
        (lineno, sorted(values)) for lineno, values in allowed
        if _LIVE_TICK_TR_ID in values
    ]
    assert offenders == [], (
        f"허용 tr_id 집합에 라이브 통합 채널 {_LIVE_TICK_TR_ID} 포함: {offenders}"
    )

    assert any(_ALLOWED_TR_IDS <= values for _lineno, values in allowed), (
        f"허용 집합에 {sorted(_ALLOWED_TR_IDS)} 가 모두 있어야 한다 — "
        f"발견={[sorted(v) for _l, v in allowed]}"
    )


# ===========================================================================
# g253_1d / g253_1e — 범위 이탈 0 (⚠️ 사이클 한정 가드, 배포 후 폐기)
# ===========================================================================
_EIGHT_AREAS = [
    "src/engine/risk.py",
    "src/engine/order_engine.py",
    "src/engine/scanner.py",
    "src/engine/session.py",
    "src/engine/strategy_registry.py",
    "src/api/order.py",
    "src/realtime",
    "src/auth",
]
_FROZEN_PATHS = _EIGHT_AREAS + [
    "src/engine/scheduler.py",
    "src/engine/stale_watcher_core.py",
    "src/engine/stale_diagnostics.py",
    "src/engine/stale_universe_guard.py",
    "src/engine/stale_session_recovery.py",
]


def test_g253_1d_out_of_scope_files_untouched():
    """명세 §1 금지 — 8영역 · `scheduler.py` · `stale_*` 4파일 diff 0.

    ⚠️ **사이클 한정 가드다.** cycle253 이 커밋되면 `_skip_if_cycle_committed` 가 skip
    으로 은퇴시키고, 그때 이 케이스를 **삭제**한다.
    """
    _skip_if_cycle_committed()
    tracked = _git("diff", "HEAD", "--name-only", "--", *_FROZEN_PATHS).split()
    untracked = _git(
        "ls-files", "--others", "--exclude-standard", "--", *_FROZEN_PATHS,
    ).split()
    changed = sorted(set(tracked) | set(untracked))
    assert changed == [], (
        f"cycle253 범위 밖 변경 감지: {changed} — 프로브는 8영역 무접촉이 존재 이유다"
        "(무접촉이 깨지면 승인·sha 재핀 비용이 가설 검증에 얹힌다)"
    )


def test_g253_1e_changed_files_are_within_declared_scope():
    """변경 파일 화이트리스트 — 명세 §1 목록 밖 소스 변경 0 (프론트 무접촉 포함).

    ⚠️ 사이클 한정 — 커밋 후 `_skip_if_cycle_committed` 가 은퇴시킨다(삭제 대상).
    """
    _skip_if_cycle_committed()
    allowed_prefixes = (
        "src/routes/realtime.py",
        "tests/",
        "_workspace/",
        "docs/",
        "CLAUDE.md",
    )
    tracked = _git("diff", "HEAD", "--name-only").split()
    untracked = _git("ls-files", "--others", "--exclude-standard").split()
    changed = sorted(set(tracked) | set(untracked))
    offenders = [
        p for p in changed
        if not p.startswith(allowed_prefixes) and not p.endswith(".md")
    ]
    assert offenders == [], f"명세 §1 범위 밖 파일 변경: {offenders}"


def test_g253_1e2_frontend_untouched():
    """프론트 무접촉 — 수동 curl 프로브가 목적이므로 UI 배선 0.

    ⚠️ 사이클 한정 — 커밋 후 `_skip_if_cycle_committed` 가 은퇴시킨다(삭제 대상).
    """
    _skip_if_cycle_committed()
    tracked = _git("diff", "HEAD", "--name-only", "--", "frontend", "e2e").split()
    untracked = _git(
        "ls-files", "--others", "--exclude-standard", "--", "frontend", "e2e",
    ).split()
    changed = sorted(set(tracked) | set(untracked))
    assert changed == [], f"프론트/E2E 변경 감지: {changed} — 명세 §1 금지"


# ===========================================================================
# g253_1f — 프로브 호출 폐쇄에 `write_log` 참조 0 (logger.info 단독 = 단일 INSERT)
# ===========================================================================
def _module_functions(tree: ast.Module) -> dict[str, ast.AST]:
    return {
        n.name: n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _transitive_closure(
    tree: ast.Module, roots: dict[str, ast.AST]
) -> dict[str, ast.AST]:
    """roots + 그것들이 (이행적으로) 호출하는 **모듈 수준 함수** 전부 (name → node).

    `write_log` 를 헬퍼로 한 겹 감싸는 우회를 잡기 위해 핸들러 본문만이 아니라 호출
    폐쇄를 검사한다 — 종전 판본이 놓친 것이 정확히 그 우회였다(Verify F1/F8).
    """
    funcs = _module_functions(tree)
    closure: dict[str, ast.AST] = {}
    stack = list(roots.items())
    while stack:
        name, node = stack.pop()
        if name in closure:
            continue
        closure[name] = node
        for call in ast.walk(node):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                callee = call.func.id
                if callee in funcs and callee not in closure:
                    stack.append((callee, funcs[callee]))
    return closure


def _write_log_refs(node) -> list[str]:
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == "write_log":
            out.append(f"L{sub.lineno} Name write_log")
        elif isinstance(sub, ast.Attribute) and sub.attr == "write_log":
            out.append(f"L{sub.lineno} Attribute .write_log")
    return out


def test_g253_1f_probe_call_closure_never_references_write_log():
    """`src.` 로거의 INFO 는 `main._DbLogHandler` 가 system_logs 에 적재한다 — 같은 내용을
    `write_log` 로 또 쓰면 액션당 2행(cycle72 G-6 이 막는 이중 INSERT 그 자체).

    핸들러 3개와 그것들이 이행적으로 호출하는 모듈 함수 전부에서 `write_log` 참조 0.
    폐쇄에 `_build_probe_row` 가 잡혀야 추적기가 공허하지 않다(자기 검증).
    """
    handlers = _require_handlers()
    closure = _transitive_closure(
        _tree(), {f"handler:{m}": n for m, n in handlers.items()}
    )
    assert "_build_probe_row" in closure, (
        f"이행 추적기 자기 검증 실패 — 핸들러가 부르는 헬퍼가 폐쇄에 없다: {sorted(closure)}"
    )
    assert len(closure) > len(handlers), "핸들러 밖 헬퍼가 하나도 잡히지 않았다 — 추적기 결함"

    offenders = {
        name: refs for name, node in closure.items() if (refs := _write_log_refs(node))
    }
    assert offenders == {}, (
        f"프로브 호출 폐쇄에 write_log 참조: {offenders} — logger.info 가 이미 "
        "_DbLogHandler 위임으로 system_logs 에 INSERT 되므로 이중 INSERT(cycle72 G-6)"
    )


def test_g253_1f_self_test_tracker_catches_helper_wrapped_write_log():
    """가드의 가드 — 헬퍼로 한 겹 감싼 write_log 를 추적기가 실제로 잡는다 (F8 공허 재발 차단).

    합성 모듈 = 종전 구현 형태(핸들러 → `_persist` → try 안 `await write_log`) 그대로.
    종전 g253_1f 는 이 형태를 PASS 시켰다.
    """
    src = textwrap.dedent(
        '''
        async def _persist(msg):
            try:
                await write_log("INFO", msg)
            except Exception:
                pass

        def _unrelated():
            return write_log

        @router.post("/channel-probe")
        async def start():
            await _persist("x")

        @router.get("/channel-probe")
        async def get_():
            return 1

        @router.delete("/channel-probe/{ticker}")
        async def stop(ticker):
            return 1
        '''
    )
    tree = ast.parse(src)
    handlers = _handlers_in(tree)
    assert set(handlers) == {"post", "get", "delete"}

    closure = _transitive_closure(
        tree, {f"handler:{m}": n for m, n in handlers.items()}
    )
    assert "_persist" in closure, sorted(closure)
    assert "_unrelated" not in closure, "호출되지 않는 함수까지 폐쇄에 넣으면 오탐"

    offenders = {name for name, node in closure.items() if _write_log_refs(node)}
    assert offenders == {"_persist"}, offenders
