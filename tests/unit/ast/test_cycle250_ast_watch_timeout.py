"""cycle250 Red — 평가 타임아웃 구조 봉인 (AST/소스 정적 가드).

명세 = team-leader 지시 (2026-09-05, cycle239 후속 A) §5-T8.
cycle233/cycle239 의 AST 파일은 **봉인 기록으로 무접촉** — 이 파일이 타임아웃
계약만 따로 못박는다.

봉인 목록:
- G-250-1: `watch_loop` 본문에 raw `run_account_risk_watch_once(` 호출 0 ∧
  guarded 1 (루프가 상한 없는 await 로 되돌아가는 회귀 차단).
- G-250-2: `boot_manager` 부팅 동기 1회도 guarded (raw 0) — 같은 hang 이 부팅을
  막는 경로다.
- G-250-3: `_EVAL_TIMEOUT_SECS` 모듈 상수 1곳 ∧ `wait_for(timeout=)` 이 그 이름을
  참조 ∧ 런타임 부등식
  `0 < _EVAL_TIMEOUT_SECS <= _WATCH_INTERVAL_SECS < _GATE_STALE_MAX_SECS`
  (타임아웃 후 **다음 평가가 stale 이전에 온다** = cycle239 신선도 계약과의 접합).
- G-250-4: guarded 의 TimeoutError 핸들러 안에서 `_gate_active` 대입과
  `_evaluated_mono` 대입 사이 await 0 (cycle239 G-239-5 동형 — "새 판정 + 낡은
  스탬프" 조합이 관측 가능해지는 것을 막는다) ∧ 그 try 가 **TimeoutError 만**
  잡는다(광범위 except 는 내부 실패 분기와 이중 기록).
- G-250-5: `run_account_risk_watch_once` **본체 무변경**(HEAD 대비 ast.dump 동일).
  이 사이클의 변경 범위는 wrapper + 호출부 2곳 + 모듈 docstring 뿐이고, 기존
  회귀(test_cycle233_watcher_gate.py · test_cycle239_gate_freshness.py)가 그
  함수의 계약을 통째로 물고 있다.

⚠️ G-250-5 는 **docstring 도 포함**해 비교한다(ast.dump 는 문자열 상수를 본다).
설명을 남기고 싶으면 함수 docstring 이 아니라 **모듈 docstring**(명세 4)에 쓴다 —
"왜 타임아웃이 루프 안이 아니라 wrapper 인가"가 그 자리다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
WATCHER = ROOT / "src" / "engine" / "account_risk_watcher.py"
BOOT = ROOT / "src" / "engine" / "boot_manager.py"

_RAW = "run_account_risk_watch_once"
_GUARDED = "run_account_risk_watch_once_guarded"
_WATCHER_REL = "src/engine/account_risk_watcher.py"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _fn(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} 부재 (cycle250 미구현)")


def _assigned_names(stmt: ast.stmt) -> set[str]:
    if isinstance(stmt, ast.Assign):
        return {t.id for t in stmt.targets if isinstance(t, ast.Name)}
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        return {stmt.target.id}
    return set()


def _called_exact(node: ast.AST, name: str) -> int:
    """`name(...)` / `mod.name(...)` **정확 일치** 호출 수.

    부분 문자열 매칭 금지 — guarded 이름이 raw 이름을 포함하므로 dump 검색은
    두 호출을 구별하지 못한다(가드 자기 공허화).
    """
    count = 0
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        fn = sub.func
        if isinstance(fn, ast.Name) and fn.id == name:
            count += 1
        elif isinstance(fn, ast.Attribute) and fn.attr == name:
            count += 1
    return count


# ===========================================================================
# G-250-1 — watch_loop 호출부 교체
# ===========================================================================
def test_g250_1_watch_loop_calls_guarded_only():
    fn = _fn(_tree(WATCHER), "watch_loop")
    raw = _called_exact(fn, _RAW)
    guarded = _called_exact(fn, _GUARDED)
    assert raw == 0, (
        f"`watch_loop` 이 아직 raw 를 직접 부른다({raw}회) — 상한 없는 await 라 "
        "hang 하면 루프가 영원히 그 자리에 서고, 예외가 아니라서 "
        "`[account_risk_watch_loop_died]` 조차 찍히지 않는다"
    )
    assert guarded == 1, (
        f"`watch_loop` 의 guarded 호출이 정확히 1회여야 한다 (실측 {guarded}회)"
    )


# ===========================================================================
# G-250-2 — 부팅 동기 1회도 guarded
# ===========================================================================
def test_g250_2_boot_manager_calls_guarded_only():
    tree = _tree(BOOT)
    raw = _called_exact(tree, _RAW)
    guarded = _called_exact(tree, _GUARDED)
    assert raw == 0, (
        f"`boot_manager` 가 raw 를 직접 부른다({raw}회) — 같은 hang 이 07:55 "
        "부팅을 통째로 막는다(그 뒤 프리서브·익일청산 배선이 전부 지연)"
    )
    assert guarded == 1, f"부팅 동기 1회 guarded 호출 부재/중복 (실측 {guarded}회)"


# ===========================================================================
# G-250-3 — 임계 단일 리터럴 + 계약 부등식
# ===========================================================================
def test_g250_3a_timeout_constant_declared_once_at_module_level():
    tree = _tree(WATCHER)
    assigns = [n for n in tree.body if "_EVAL_TIMEOUT_SECS" in _assigned_names(n)]
    assert len(assigns) == 1, (
        f"`_EVAL_TIMEOUT_SECS` 모듈 상수가 정확히 1곳이어야 한다 (실측 {len(assigns)})"
    )
    value = assigns[0].value
    ok_literal = isinstance(value, ast.Constant) and value.value == 300
    ok_derived = any(
        isinstance(n, ast.Name) and n.id == "_WATCH_INTERVAL_SECS"
        for n in ast.walk(value)
    )
    assert ok_literal or ok_derived, (
        f"임계는 리터럴 300 또는 `_WATCH_INTERVAL_SECS` 파생이어야 한다: "
        f"{ast.dump(value)}"
    )


def test_g250_3b_no_stray_timeout_literal_in_module():
    """호출부 인라인 리터럴 금지 — 상수를 고쳐도 안 따라오는 그림자 임계 차단."""
    tree = _tree(WATCHER)
    allowed: set[int] = set()
    for node in tree.body:
        names = _assigned_names(node)
        if names & {"_EVAL_TIMEOUT_SECS", "_WATCH_INTERVAL_SECS"}:
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Constant):
                    allowed.add(id(sub))
    stray = [
        sub for sub in ast.walk(tree)
        if isinstance(sub, ast.Constant)
        and not isinstance(sub.value, bool)
        and isinstance(sub.value, (int, float))
        and sub.value == 300
        and id(sub) not in allowed
    ]
    assert not stray, (
        f"모듈에 임계 리터럴 300 이 상수 선언 밖에 {len(stray)}곳 있다 — "
        "주기/임계를 바꿔도 안 따라오는 그림자 값이 생긴다"
    )


def test_g250_3c_wait_for_timeout_arg_references_the_constant():
    fn = _fn(_tree(WATCHER), _GUARDED)
    waits = [
        sub for sub in ast.walk(fn)
        if isinstance(sub, ast.Call)
        and ((isinstance(sub.func, ast.Attribute) and sub.func.attr == "wait_for")
             or (isinstance(sub.func, ast.Name) and sub.func.id == "wait_for"))
    ]
    assert len(waits) == 1, (
        f"`asyncio.wait_for` 호출이 정확히 1회여야 한다 (실측 {len(waits)})"
    )
    call = waits[0]
    args = [kw.value for kw in call.keywords if kw.arg == "timeout"]
    if not args and len(call.args) >= 2:
        args = [call.args[1]]
    assert args, f"타임아웃 인자 부재: {ast.dump(call)}"
    node = args[0]
    assert isinstance(node, ast.Name) and node.id == "_EVAL_TIMEOUT_SECS", (
        f"타임아웃 인자는 모듈 상수 이름이어야 한다(테스트가 축소 monkeypatch 로 "
        f"쓰는 seam 이기도 하다): {ast.dump(node)}"
    )
    inner = call.args[0] if call.args else None
    assert inner is not None and _called_exact(inner, _RAW) == 1, (
        f"wait_for 가 감싸는 대상이 raw 평가 1회여야 한다: "
        f"{ast.dump(inner) if inner is not None else None}"
    )


def test_g250_3d_threshold_invariant_holds_at_runtime():
    from src.engine import account_risk_watcher as watcher

    timeout = getattr(watcher, "_EVAL_TIMEOUT_SECS", None)
    assert timeout is not None, "`_EVAL_TIMEOUT_SECS` 부재 (cycle250 미구현)"
    assert 0 < timeout <= watcher._WATCH_INTERVAL_SECS, (
        f"타임아웃({timeout}) 이 주기({watcher._WATCH_INTERVAL_SECS}) 를 넘으면 "
        "평가 하나가 다음 주기를 잡아먹어 상한의 의미가 사라진다"
    )
    assert watcher._WATCH_INTERVAL_SECS < watcher._GATE_STALE_MAX_SECS, (
        "타임아웃 후 다음 평가가 stale(900s) 이전에 와야 한다 — 이 부등식이 깨지면 "
        "정상 타임아웃마다 소비자 경로가 거짓 stale 을 본다"
    )


# ===========================================================================
# G-250-4 — 스탬프 원자성 + TimeoutError 만 잡는다
# ===========================================================================
def _timeout_try(fn) -> ast.Try:
    for node in ast.walk(fn):
        if isinstance(node, ast.Try) and _called_exact(
            ast.Module(body=list(node.body), type_ignores=[]), "wait_for"
        ):
            return node
    raise AssertionError(f"{_GUARDED} 에 wait_for 를 감싸는 try 블록 부재")


def test_g250_4a_timeout_handler_stamps_atomically():
    fn = _fn(_tree(WATCHER), _GUARDED)
    node = _timeout_try(fn)
    assert node.handlers, "except 핸들러 부재"
    body = node.handlers[0].body
    idx_gate = idx_stamp = None
    for i, stmt in enumerate(body):
        names = _assigned_names(stmt)
        if "_gate_active" in names:
            idx_gate = i
        if "_evaluated_mono" in names:
            idx_stamp = i
    assert idx_gate is not None, "타임아웃 핸들러에 `_gate_active` 대입 부재(fail-open 미수행)"
    assert idx_stamp is not None, (
        "타임아웃 핸들러에 `_evaluated_mono` 스탬프 부재 — 타임아웃이 신선도를 "
        "갱신하지 않으면 '루프 생존 중 타임아웃'이 '루프 사멸'로 오독된다"
    )
    lo, hi = min(idx_gate, idx_stamp), max(idx_gate, idx_stamp)
    for stmt in body[lo:hi + 1]:
        assert not [n for n in ast.walk(stmt) if isinstance(n, ast.Await)], (
            "판정 대입과 스탬프 사이 await — '새 판정 + 낡은 스탬프' 조합이 "
            "관측 가능해진다(cycle239 G-239-5 동형)"
        )


def test_g250_4b_only_timeout_error_is_caught():
    fn = _fn(_tree(WATCHER), _GUARDED)
    node = _timeout_try(fn)
    for handler in node.handlers:
        assert handler.type is not None, (
            "bare except — 취소(CancelledError)까지 삼켜 stop 이 안 먹는다"
        )
        names = {
            n.attr if isinstance(n, ast.Attribute) else n.id
            for n in ast.walk(handler.type)
            if isinstance(n, (ast.Attribute, ast.Name))
        }
        assert names & {"TimeoutError"}, (
            f"wait_for 를 감싼 try 가 TimeoutError 밖의 예외까지 잡는다 "
            f"({sorted(names)}) — 내부 함수의 기존 실패 분기와 이중 기록이 되고, "
            "내부가 못 잡은 진짜 배선 오류까지 조용히 삼켜진다"
        )
        assert "Exception" not in names and "BaseException" not in names, (
            f"광범위 except 금지: {sorted(names)}"
        )
        # cycle250 적대 검증 M28 — 위 두 assert 는 `except (asyncio.TimeoutError,
        # asyncio.CancelledError)` 를 통과시킨다(CancelledError 는 "TimeoutError"
        # 토큰과 무관 + Exception/BaseException 도 아님). 취소를 함께 잡으면
        # stop/shutdown 취소가 삼켜져 루프가 종료 불능이 된다(뮤턴트 재현 =
        # teardown 이 280s+ hang). 이름 집합을 상한으로 봉인한다.
        assert names <= {"asyncio", "TimeoutError"}, (
            f"wait_for 를 감싼 except 가 TimeoutError 외 타입을 함께 잡는다: "
            f"{sorted(names)} — CancelledError 동반 포착은 stop/shutdown 취소를 "
            "삼켜 루프가 다음 주기로 계속 돈다"
        )


# ===========================================================================
# G-250-5 — 내부 평가 함수 본체 무변경 (HEAD 대비)
# ===========================================================================

# 리터럴 핀 (2026-09-05 리팩토링 리뷰 카드 #2) — HEAD 비교는 커밋 직후 자기 일치로 전락하고
# 편집 순간 영구 동결이 된다(cycle252 tester F-4 교훈). 정당한 본체 변경이면 아래 한 줄을
# `hashlib.sha256(ast.dump(fn).encode()).hexdigest()` 로 재산출해 갱신한다(핀을 먼저 재산출하지 마라).
_RUN_ONCE_BODY_SHA256 = "1d87f590e0f406f9fac203dd6a3400a48c291fd941edc51eb266d4c8547a6a90"


def test_g250_5_run_once_body_pinned():
    """cycle250 계약 — `run_account_risk_watch_once` 본체 무변경(wrapper 신설 + 호출부 2곳만).

    ast.dump 의 sha256 리터럴 핀. ast.dump 는 함수 docstring 도 본다 — 설명은 모듈
    docstring 에 쓴다.
    """
    import hashlib as _hl
    work_fn = _fn(_tree(WATCHER), _RAW)
    actual = _hl.sha256(ast.dump(work_fn).encode("utf-8")).hexdigest()
    assert actual == _RUN_ONCE_BODY_SHA256, (
        "`run_account_risk_watch_once` 본체가 cycle250 승인 형상과 다르다 — 정당한 변경이면 "
        f"team-leader 확인 후 `_RUN_ONCE_BODY_SHA256` 을 {actual} 로 갱신하라: {actual}"
    )
