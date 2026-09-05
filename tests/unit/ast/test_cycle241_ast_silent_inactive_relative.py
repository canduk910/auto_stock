"""cycle241 Red — 세션 상대 판정 구조 봉인 (AST G-241-1 ~ G-241-7).

> 선행 명세: `_workspace/red/cycle241_silent_inactive_relative_spec.md` §4.2

행위 테스트(`tests/unit/engine/test_cycle241_silent_inactive_relative.py`)가 잡지 못하는
**구조 계약**을 정적으로 못박는다:

- 게이트가 누적 루프 **앞**에 있을 것(반환 직전 필터로 옮기면 재개 경계로 오판이 이동한다)
- 기각 = pop + `return` (hold 금지)
- 기각 경로가 발화·cap·reconnect 를 건드리지 않을 것
- 마커 emit 은 예외 흡수 Try 안, `write_log` 0 (cycle72)
- peek→로그→mark (mark-before-log 금지, cycle226 D-3 동형)
- 시장 상태 신호(`src.engine.session` 등) 유입 금지 · scheduler seam 보존
- `scheduler.py` / `stale_manager.py` 무접촉

⚠️ 자기 가드 공허화 주의(cycle224/226 교훈) — 게이트 탐색은 지역 대입을 **전이적으로**
되짚는다. `_market_wide = eligible_n >= _MARKET_WIDE_MIN_ELIGIBLE and ...` 처럼 한 단계
경유해도 검출돼야 한다.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
_TARGET = _SRC / "engine" / "stale_session_recovery.py"
_SCHEDULER = _SRC / "engine" / "scheduler.py"
_FACADE = _SRC / "engine" / "stale_manager.py"

_MARKER = "[silent_inactive_market_wide_skip]"
_DETECT = "detect_silent_inactive_sessions"
_MIN_ELIGIBLE_CONST = "_MARKET_WIDE_MIN_ELIGIBLE"

# 이 모듈이 import 해도 되는 src 모듈 (Q1 단방향 + 시장 상태 신호 차단)
_ALLOWED_SRC_MODULES = {
    "src.engine.scanner",
    "src.engine.stale_diagnostics",
    "src.realtime.websocket",
    "src.realtime.websocket_pool",
}


# ===========================================================================
# 공통 헬퍼
# ===========================================================================
def _source() -> str:
    return _TARGET.read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_source())


def _func(name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(_tree()):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    pytest.fail(f"cycle241 미구현 — `{_TARGET.name}` 에 `{name}` 부재")


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _local_assign_map(fn: ast.AST) -> dict[str, set[str]]:
    """지역 대입 타깃 → 그 값에 등장하는 Name 집합 (전이 추적용)."""
    out: dict[str, set[str]] = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out.setdefault(target.id, set()).update(_names(node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                out.setdefault(node.target.id, set()).update(_names(node.value))
    return out


def _resolve(seed: set[str], assign_map: dict[str, set[str]]) -> set[str]:
    """지역 대입을 전이적으로 되짚어 참조 가능한 Name 전부를 모은다."""
    seen: set[str] = set()
    stack = list(seed)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        stack.extend(assign_map.get(name, set()) - seen)
    return seen


def _find_gate() -> ast.If:
    """`_MARKET_WIDE_MIN_ELIGIBLE` 를 (전이적으로) 참조하는 `If` = 상대 판정 게이트."""
    fn = _func(_DETECT)
    assign_map = _local_assign_map(fn)
    candidates = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.If)
        and _MIN_ELIGIBLE_CONST in _resolve(_names(node.test), assign_map)
    ]
    if not candidates:
        pytest.fail(
            f"cycle241 미구현 — `{_DETECT}` 안에 `{_MIN_ELIGIBLE_CONST}` 를 참조하는 게이트 If 부재. "
            f"리터럴 `2` 하드코딩도 여기서 걸린다(상수 SoT 의무)."
        )
    return min(candidates, key=lambda n: n.lineno)


def _accum_assign_lineno() -> int:
    """누적 루프의 `scheduler._silent_inactive_first_seen[label] = now` 위치."""
    fn = _func(_DETECT)
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Attribute)
                and target.value.attr == "_silent_inactive_first_seen"
            ):
                return node.lineno
    pytest.fail("`_silent_inactive_first_seen[label] = now` 누적 대입 부재 — 사이클 24 계약 소실")


def _parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _marker_calls(tree: ast.Module, attrs: tuple[str, ...]) -> list[ast.Call]:
    """`logger.<attr>(...)` 중 첫 인자 문자열에 마커 prefix 가 든 호출."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr in attrs):
            continue
        if not (isinstance(fn.value, ast.Name) and fn.value.id == "logger"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str) and _MARKER in first.value:
            out.append(node)
    return out


# ===========================================================================
# G-241-1 — 게이트 존재 + pop + return + 누적 루프 앞
# ===========================================================================
class TestG241_1GateStructure:
    def test_gate_body_pops_first_seen_and_returns(self):
        """기각 = `_silent_inactive_first_seen.pop(...)` + `return` (hold 변형 차단)."""
        gate = _find_gate()
        body_src = "\n".join(ast.unparse(stmt) for stmt in gate.body)

        assert any(isinstance(n, ast.Return) for n in ast.walk(gate)), (
            "게이트 body 에 `return` 부재 — 기각하지 않으면 누적 루프로 흘러 발화한다"
        )
        pops = [
            n for n in ast.walk(gate)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "pop"
            and "_silent_inactive_first_seen" in ast.unparse(n.func)
        ]
        assert pops, (
            "게이트 body 에 `_silent_inactive_first_seen.pop(...)` 부재 = hold 변형(m2). "
            f"first_seen 을 유지하면 시장 재개 직후 첫 사이클에 즉발한다. body=\n{body_src}"
        )

    def test_gate_precedes_first_seen_accumulation(self):
        """게이트는 누적 루프 **앞** — 반환 직전 필터(m7)면 오판이 재개 경계로 이동할 뿐."""
        gate_line = _find_gate().lineno
        accum_line = _accum_assign_lineno()
        assert gate_line < accum_line, (
            f"게이트 L{gate_line} 가 누적 대입 L{accum_line} 보다 뒤에 있다 — "
            f"'누적 후 필터' 는 first_seen 이 계속 자라 재개 순간 즉발한다."
        )


# ===========================================================================
# G-241-2 — 기각 경로가 발화·cap·reconnect·관측상태 를 건드리지 않는다
# ===========================================================================
class TestG241_2RejectPathIsolation:
    def test_gate_body_has_no_fire_or_cap_tokens(self):
        gate_src = "\n".join(ast.unparse(stmt) for stmt in _find_gate().body)
        for token in ("silent_labels.append", "force_reconnect", "_silent_inactive_recovery_count"):
            assert token not in gate_src, (
                f"기각 경로에 `{token}` 등장 — 기각은 발화·cap 어느 쪽도 건드리지 않는다. "
                f"시간당 세션당 2회 cap(KIS LMS/앱키 정지 위험)은 무접촉 계약이다."
            )

    def test_episode_state_never_drives_behavior(self):
        """`_MW_EPISODE` 는 관측 전용 — 판정 함수의 분기 조건에 등장하면 안 된다(m15).

        선행 단언으로 `_MW_EPISODE` 존재를 요구한다 — 없으면 이 검사가 항상 참이 되는
        공허한 가드로 남는다(cycle224 자기 가드 공허화 교훈).
        """
        assert "_MW_EPISODE" in _source(), (
            "cycle241 미구현 — 모듈 전역 `_MW_EPISODE` 부재. 이 가드는 그 상태가 "
            "행위로 새어나가지 않는지를 보는 것이라 대상이 없으면 공허해진다."
        )
        fn = _func(_DETECT)
        for node in ast.walk(fn):
            tests = []
            if isinstance(node, (ast.If, ast.IfExp, ast.While)):
                tests.append(node.test)
            elif isinstance(node, ast.Compare):
                tests.append(node)
            for t in tests:
                assert "_MW_EPISODE" not in ast.unparse(t), (
                    f"L{getattr(t, 'lineno', '?')}: 관측 상태로 행위를 분기한다 — "
                    f"관측기 실패/리셋이 기각 여부를 바꾸면 안 된다."
                )


# ===========================================================================
# G-241-3 — 마커 emit 은 예외 흡수 Try 안, write_log 0
# ===========================================================================
class TestG241_3ObserverSafety:
    def test_three_transition_markers_exist(self):
        tree = _tree()
        consts = [
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and _MARKER in n.value
        ]
        transitions = {t for t in ("entered", "persisting", "exited")
                       if any(f"transition={t}" in c for c in consts)}
        assert transitions == {"entered", "persisting", "exited"}, (
            f"에피소드 3전이 마커 누락 — got {sorted(transitions)}. "
            f"entered(진입 1회)/persisting(30분마다 WARNING)/exited(이탈 1회)."
        )

    def test_every_marker_emit_is_inside_exception_absorbing_try(self):
        tree = _tree()
        parents = _parent_map(tree)
        calls = _marker_calls(tree, ("info", "warning"))
        assert calls, "마커 emit 사이트 0 — 미구현"
        for call in calls:
            node: ast.AST | None = call
            guarded = False
            while node is not None:
                parent = parents.get(id(node))
                if isinstance(parent, ast.Try) and node in parent.body:
                    for handler in parent.handlers:
                        if handler.type is None or "Exception" in ast.unparse(handler.type):
                            guarded = True
                            break
                if guarded:
                    break
                node = parent
            assert guarded, (
                f"L{call.lineno}: 마커 emit 이 `except Exception` Try 밖 — "
                f"관측 실패가 기각 행위(pop + [])를 삼키면 결함 주입이다(m14)."
            )

    def test_no_write_log_call_in_module(self):
        """cycle72 A7~A9 — logger 위임 단일 INSERT. `write_log` **호출** 0건.

        주석의 이력 서술("write_log 제거")은 무시하고 실제 Call 노드만 센다 —
        문자열 검사로 두면 주석 때문에 항상 FAIL 하는 공허한 가드가 된다.
        """
        calls = []
        for node in ast.walk(_tree()):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in ("write_log", "_write_log", "safe_write_log"):
                calls.append(f"L{node.lineno}")
        assert not calls, (
            f"`write_log` 호출 {calls} — `_DbLogHandler` 위임과 이중 INSERT (cycle72 G-A7/A8/A9)."
        )


# ===========================================================================
# G-241-4 — peek → 로그 → mark (mark-before-log 금지)
# ===========================================================================
class TestG241_4PeekLogMark:
    @staticmethod
    def _mark_linenos(fn, key: str) -> list[int]:
        """`_MW_EPISODE` 에 `key` 를 **non-None** 으로 기록하는 지점의 lineno."""
        out: list[int] = []
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and "_MW_EPISODE.update" in ast.unparse(node.func):
                for kw in node.keywords:
                    if kw.arg == key and not (
                        isinstance(kw.value, ast.Constant) and kw.value.value is None
                    ):
                        out.append(node.lineno)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                        isinstance(target, ast.Subscript)
                        and "_MW_EPISODE" in ast.unparse(target.value)
                        and isinstance(target.slice, ast.Constant)
                        and target.slice.value == key
                    ):
                        if not (isinstance(node.value, ast.Constant) and node.value.value is None):
                            out.append(node.lineno)
        return sorted(out)

    def test_since_recorded_after_entered_log(self):
        fn = _func("_observe_market_wide")
        infos = [
            n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == "info"
            and n.args and isinstance(n.args[0], ast.Constant)
            and isinstance(n.args[0].value, str) and _MARKER in n.args[0].value
        ]
        marks = self._mark_linenos(fn, "since")
        assert infos, "`_observe_market_wide` 에 entered INFO emit 부재"
        assert marks, "`since` 기록 지점 부재 — 에피소드가 열리지 않는다"
        assert min(marks) > min(infos), (
            f"mark-before-log(m9) — `since` 기록 L{min(marks)} 이 로그 L{min(infos)} 보다 앞. "
            f"로그가 던지면 에피소드만 열려 entered 가 영영 안 찍힌다(cycle226 D-3 동형)."
        )

    def test_last_warn_at_recorded_after_persisting_log(self):
        fn = _func("_observe_market_wide")
        warns = [
            n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == "warning"
            and n.args and isinstance(n.args[0], ast.Constant)
            and isinstance(n.args[0].value, str) and _MARKER in n.args[0].value
        ]
        marks = self._mark_linenos(fn, "last_warn_at")
        assert warns, "persisting WARNING emit 부재"
        assert marks, "`last_warn_at` 기록 지점 부재 — 30분 cap 이 성립하지 않는다"
        assert min(marks) > min(warns), (
            f"mark-before-log — `last_warn_at` L{min(marks)} 이 WARNING L{min(warns)} 보다 앞."
        )


# ===========================================================================
# G-241-5 — import 표면 + scheduler seam
# ===========================================================================
class TestG241_5ImportSurface:
    def test_no_market_state_or_cyclic_imports(self):
        tree = _tree()
        offenders: list[str] = []
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                mods.append(node.module)
            elif isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            for mod in mods:
                if mod.startswith("src.") and mod not in _ALLOWED_SRC_MODULES:
                    offenders.append(f"L{node.lineno}: {mod}")
        assert not offenders, (
            f"허용 밖 src import: {offenders}. 시장 침묵 판정에 시간창 리터럴·"
            f"`tradable_boards`·`src.engine.session` 을 쓰지 않는다 — 세션 비교만이 "
            f"15:30~15:40 갭까지 닫는다. `stale_watcher_core` 는 Q1 단방향 위반."
        )

    def test_scheduler_namespace_seam_preserved(self):
        """`sys.modules.get("src.engine.scheduler")` 3건 — D-1/D-2 + freezegun patch 호환."""
        count = _source().count('sys.modules.get("src.engine.scheduler")')
        assert count >= 3, (
            f"scheduler 네임스페이스 seam {count}건 (>=3 의무) — 제거 시 "
            f"`patch('src.engine.scheduler.datetime')` 테스트 seam 과 운영 객체 일치가 깨진다."
        )


# ===========================================================================
# G-241-6 — scheduler.py 무접촉 (토큰 유입 0)
#   ⚠️ 사이클 한정 동결 `test_scheduler_line_count_unchanged`(== 3999) 는 자기소멸 조건대로
#   cycle257(보드 전환 죽은 코드 삭제, 3,999 → <3,900L) 이 은퇴시켰다 — 라인 수 계약은
#   `test_cycle257_ast_dead_code_removed.py::TestA4`(< 3,900) 와 기존 상한(< 4,000) 이 담당.
# ===========================================================================
class TestG241_6SchedulerUntouched:
    def test_no_market_wide_token_in_scheduler(self):
        text = _SCHEDULER.read_text(encoding="utf-8")
        for token in ("market_wide", "_MW_EPISODE"):
            assert token not in text, f"scheduler.py 에 `{token}` 유입 — 이번 사이클 diff 0 계약"


# ===========================================================================
# G-241-7 — facade 무접촉 (신규 export 0)
# ===========================================================================
class TestG241_7FacadeUntouched:
    def test_no_new_export_in_stale_manager(self):
        text = _FACADE.read_text(encoding="utf-8")
        for token in ("market_wide", "reset_market_wide_episode_state"):
            assert token not in text, (
                f"facade 에 `{token}` 유입 — 상수·상태·헬퍼는 전부 module private, "
                f"`__all__` 미편입이 계약이다."
            )
