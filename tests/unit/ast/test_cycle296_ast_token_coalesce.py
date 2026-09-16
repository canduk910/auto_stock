"""cycle296 — `issue()` 합류 구조 · leaf 관측 5키 AST 가드 (RED).

정본 = `_workspace/red/cycle296_token_refresh_coalesce_spec.md` §5-2.

| 가드 | 내용 | 수명 |
|------|------|------|
| A1 | 전역 61초 직렬화가 `issue()` 안에 **그대로** 남아 있다 (양성 대조군) | 영구 |
| A2 | 합류 판단이 **첫 `await` 앞**이고, 리더 등록이 **락 획득 앞**이다 | 영구 |
| A3 | `issue()` 에 `try/finally` 가 있고 finally 가 `_inflight` 를 비운다 | 영구 |
| A4 | 합류 대기는 `asyncio.shield` + 상한(`asyncio.wait_for`) 을 쓴다 | 영구 |
| A5 | `get_token`·`revoke`·`_is_valid` 세그먼트 sha **불변** (스코프 실증) | 영구 |
| A6 | leaf 요약 5키 + G-270-2/4 격리 계약 유지 (`import time` 은 허용) | 영구 |

⚠️ 핀은 `ast.dump` 가 아니라 `ast.get_source_segment` 의 sha256 이다
(3.12(CI)/3.13(로컬) `ast.dump` 출력 차이로 CI 만 붉어진 cycle256/259 실측).

⚠️ **양성 대조군 규약** — "…가 0건" 식 부정 단언만 두면 대상 코드가 통째로
사라져도 초록이다(cycle292 교훈). 각 가드는 "있어야 할 것이 있다" 를 함께 잰다.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
_TOKEN = _SRC / "auth" / "token.py"
_LEAF = _SRC / "engine" / "quote_token_refresh.py"

_MARKER = "[quote_token_refresh]"


def _token_src() -> str:
    return _TOKEN.read_text(encoding="utf-8")


def _method(src: str, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    tree = ast.parse(src)
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TokenManager"
    )
    return next(
        n
        for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )


def _pos(node: ast.AST) -> tuple[int, int]:
    return (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))


def _inflight_attrs(fn: ast.AST) -> list[ast.Attribute]:
    return [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Attribute)
        and n.attr == "_inflight"
        and isinstance(n.value, ast.Name)
        and n.value.id == "self"
    ]


# ===========================================================================
# A1 — 61초 전역 직렬화 보존 (양성 대조군)
# ===========================================================================

def test_a1_global_serialization_survives_the_coalescing_change():
    """합류는 락 **바깥**의 판단이다 — 락·gap 을 없애서 발급을 줄이면 안 된다.

    락을 매니저 단위로 쪼개거나 gap 을 줄이면 KIS 분당 1개 한도(전역)를 위반해
    403 → 앱키 정지로 간다(사이클 20 이 고친 결함의 재현).
    """
    import src.auth.token as token_mod

    assert token_mod._ISSUE_GAP_SECS == 61.0, (
        f"gap 실측 {token_mod._ISSUE_GAP_SECS} — 분당 1개(1초 마진) 계약"
    )

    src = _token_src()
    tree = ast.parse(src)
    module_level = {
        t.id
        for n in tree.body
        if isinstance(n, (ast.Assign, ast.AnnAssign))
        for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
        if isinstance(t, ast.Name)
    }
    assert "_GLOBAL_ISSUE_LOCK" in module_level, (
        "`_GLOBAL_ISSUE_LOCK` 이 모듈 전역이 아니다 — 매니저 단위 락은 403 을 부른다"
    )

    fn = _method(src, "issue")
    lock_withs = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.AsyncWith)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == "_get_global_issue_lock"
            for item in n.items
        )
    ]
    assert len(lock_withs) == 1, (
        f"`issue()` 안의 `async with _get_global_issue_lock()` 이 {len(lock_withs)}곳 — "
        "정확히 1곳이어야 한다"
    )

    # 양성 대조군 — 발급 본체(POST + 필드 대입 + gap 앵커 갱신)가 여전히 살아 있다.
    body_src = ast.get_source_segment(src, fn) or ""
    assert "httpx.AsyncClient" in body_src and "/oauth2/tokenP" in body_src, (
        "`issue()` 에서 KIS 발급 호출이 사라졌다 — '합류' 가 '발급 제거' 로 둔갑했다"
    )
    assigned = {
        t.attr
        for n in ast.walk(fn)
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Attribute)
        and isinstance(t.value, ast.Name)
        and t.value.id == "self"
    }
    assert {"access_token", "token_expired"} <= assigned, (
        f"발급 결과 대입이 사라졌다 — 실측 self.* 대입 {sorted(assigned)}"
    )
    globals_assigned = {
        t.id
        for n in ast.walk(fn)
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name)
    }
    assert "_LAST_ISSUE_AT" in globals_assigned, (
        "gap 앵커(`_LAST_ISSUE_AT`) 갱신이 사라졌다 — 61초 직렬화가 다음 호출부터 무력해진다"
    )


# ===========================================================================
# A2 — 합류 판단은 첫 await 앞, 리더 등록은 락 획득 앞
# ===========================================================================

def test_a2_join_decision_is_atomic_and_leader_registers_before_the_lock():
    """asyncio 는 단일 스레드다 — **첫 `await` 앞**의 체크·설정만 원자적이다.

    `_inflight` 등록을 락 획득 **뒤**로 옮기면(M3) 리더가 락을 기다리는 61초 동안
    들어온 호출자가 합류 대상을 못 봐서 이 사이클이 고치려는 (B) 가 그대로 남는다.
    """
    src = _token_src()
    fn = _method(src, "issue")

    attrs = _inflight_attrs(fn)
    assert attrs, (
        "`issue()` 안에 `self._inflight` 참조가 없다 — 매니저 단위 in-flight 합류 미구현"
    )

    awaits = [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
    assert awaits, "`issue()` 에 `await` 가 하나도 없다 — 발급 본체가 사라졌다"
    first_await = min(_pos(n) for n in awaits)
    first_read = min(_pos(a) for a in attrs)
    assert first_read < first_await, (
        f"첫 `self._inflight` 참조 {first_read} 가 첫 `await` {first_await} 뒤에 있다 — "
        "합류 판단은 첫 await 앞에서 동기적으로 끝나야 원자적이다"
    )

    writes = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Assign)
        and any(
            isinstance(t, ast.Attribute)
            and t.attr == "_inflight"
            and isinstance(t.value, ast.Name)
            and t.value.id == "self"
            for t in n.targets
        )
    ]
    assert writes, "`self._inflight = ...` 대입이 없다 — 리더 등록 부재"

    lock_with = next(
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.AsyncWith)
        and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == "_get_global_issue_lock"
            for item in n.items
        )
    )
    leader_writes = [w for w in writes if _pos(w) < _pos(lock_with)]
    assert leader_writes, (
        f"`self._inflight` 등록이 전부 락 획득(line {lock_with.lineno}) 뒤에 있다 — "
        "락 대기 중인 리더에 합류할 길이 사라진다(원인 (B) 미해결)"
    )


# ===========================================================================
# A3 — finally 가 반드시 _inflight 를 비운다
# ===========================================================================

def test_a3_finally_always_clears_inflight():
    """`_inflight` 가 남으면 **끝난 Future 에 영구 합류**해 만료 뒤 전 REST 가 401 이다(R5, HIGH).

    성공·실패·취소 어느 길로 끝나도 비워지는 자리는 `finally` 하나뿐이다.
    """
    src = _token_src()
    fn = _method(src, "issue")

    tries = [n for n in ast.walk(fn) if isinstance(n, ast.Try) and n.finalbody]
    assert tries, "`issue()` 에 `try/finally` 가 없다 — 취소 경로에서 `_inflight` 가 샌다"

    cleared = [
        t
        for t in tries
        if any(
            isinstance(stmt, ast.Assign)
            and any(
                isinstance(tgt, ast.Attribute)
                and tgt.attr == "_inflight"
                and isinstance(tgt.value, ast.Name)
                and tgt.value.id == "self"
                for tgt in stmt.targets
            )
            and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is None
            for node in t.finalbody
            for stmt in ast.walk(node)
        )
    ]
    assert cleared, (
        "`finally` 안에서 `self._inflight = None` 대입을 못 찾았다 — 실패·취소 경로에서 "
        "in-flight 가 영구히 남는다"
    )

    # 양성 대조군 — 예외를 조용히 삼키지 않는다(`except: pass` 금지).
    for t in tries:
        for handler in t.handlers:
            assert any(
                isinstance(s, (ast.Raise, ast.Return))
                for node in handler.body
                for s in ast.walk(node)
            ), (
                f"line {handler.lineno} 의 except 가 예외를 삼킨다 — 대기자가 빈 토큰을 "
                "받아 무음 401 이 된다"
            )


# ===========================================================================
# A4 — 합류 대기는 shield + 상한
# ===========================================================================

def test_a4_waiters_shield_the_shared_future_and_bound_the_wait():
    """`shield` 가 없으면 한 대기자의 타임아웃·취소가 **공유 Future 를 취소**한다(R3).

    상한(`wait_for`)은 I-3 의 2차 방어다 — 리더의 HTTP 가 httpx timeout 을 뚫고
    매달리는 경우만 잡는다(명세 §8-4 열린 질문 4 = "포함" 이 기본 제안).
    """
    src = _token_src()
    fn = _method(src, "issue")

    # `asyncio.shield(...)` 와 `from asyncio import shield` 양쪽을 센다.
    calls: set[str] = set()
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call):
            continue
        if isinstance(n.func, ast.Attribute):
            calls.add(n.func.attr)
        elif isinstance(n.func, ast.Name):
            calls.add(n.func.id)

    assert "shield" in calls, (
        f"합류 대기에 `asyncio.shield` 가 없다 — 실측 호출 {sorted(calls)}. "
        "대기자 하나가 취소되면 공유 Future 가 죽어 전원이 실패한다(N10)"
    )
    assert "wait_for" in calls, (
        f"합류 대기에 상한(`asyncio.wait_for`)이 없다 — 실측 호출 {sorted(calls)}. "
        "명세 §8-4 열린 질문 4 의 기본 제안 = 포함(리더의 HTTP 가 httpx timeout 을 뚫고 "
        "매달리는 경우의 2차 방어)"
    )


# ===========================================================================
# A5 — 접촉 범위 실증 (issue() 말고는 손대지 않는다)
# ===========================================================================

# `ast.get_source_segment(...)` 의 sha256 (2026-09-17 HEAD = cycle295 `5421a90`).
_SEGMENT_PINS = {
    # 캐시 hit 경로 — 여기가 바뀌면 "정상 흐름은 issue() 에 안 들어간다" 가 흔들린다.
    "get_token": "e35d497435a2ed509fe04d0d2a535bb74970e717484076d1855e8b45324a99e5",
    # cycle270 앵커 이동의 전제(G-270-3 자매 핀)
    "revoke": "0d454ce0587a25bd7976ce4776576decee56cc5bf7518fbf77ae2315e62d968a",
    # 10분 선제 갱신 마진 — 줄이면 만료 직전 매매 REST 가 401 (g269_6 자매 핀)
    "_is_valid": "d58f356b02c8de7ee75ef1404f836a2770a849fe13a73c44ed8cbb083a581d15",
}


@pytest.mark.parametrize("name,expected", sorted(_SEGMENT_PINS.items()))
def test_a5_only_issue_is_touched(name: str, expected: str):
    """cycle296 이 바꾸는 것은 `issue()` **하나**다.

    `src/auth/token.py` 는 8영역이고 이 사이클의 승인 범위는 "`issue()` 합류" 로
    한정된다. 다른 메서드가 같이 움직였다면 승인 범위 밖이다.
    """
    src = _token_src()
    fn = _method(src, name)
    actual = hashlib.sha256(
        (ast.get_source_segment(src, fn) or "").encode("utf-8")
    ).hexdigest()
    assert actual == expected, (
        f"`TokenManager.{name}` 가 바뀌었다 — cycle296 의 승인 범위는 `issue()` 뿐이다. "
        f"실측 sha={actual}"
    )


def test_a5b_issue_actually_changed_from_the_cycle295_baseline():
    """양성 대조군 — `issue()` **는** 바뀌어야 한다.

    A5 가 "아무것도 안 바뀌었다" 로 통과하는 가짜 GREEN 을 막는다. cycle295 시점의
    `issue()` 세그먼트 sha 와 **달라야** 한다.
    """
    _ISSUE_SHA_BEFORE = (
        "7e30971af254ee95aa7507d9ff77fc61093ed3849415c77832a5fb031c93dc07"
    )
    src = _token_src()
    fn = _method(src, "issue")
    actual = hashlib.sha256(
        (ast.get_source_segment(src, fn) or "").encode("utf-8")
    ).hexdigest()
    assert actual != _ISSUE_SHA_BEFORE, (
        "`issue()` 가 cycle295 기준선 그대로다 — in-flight 합류가 아직 구현되지 않았다"
    )


# ===========================================================================
# A6 — leaf 관측 5키 + 격리 계약 유지
# ===========================================================================

def test_a6_leaf_summary_has_five_keys_with_matching_format():
    """`run_periodic_task_loop._build_log_args` 가 `summary_keys` 순서대로 `%d` 를 채운다.

    키 수와 `%d` 수가 어긋나면 요약 1행이 **매일** `TypeError` 로 죽는다(그리고 그
    예외는 `logger.info` 호출부라 task loop 의 graceful 에 먹혀 조용히 사라진다).
    """
    from src.engine import quote_token_refresh as mod

    assert mod._SUMMARY_KEYS == (
        "accounts", "issued", "failed", "elapsed_s", "window_issues_total",
    ), f"실측 {mod._SUMMARY_KEYS}"
    assert mod._SUMMARY_LOG_FORMAT == (
        f"{_MARKER} accounts=%d issued=%d failed=%d "
        "elapsed_s=%d window_issues_total=%d"
    ), f"실측 {mod._SUMMARY_LOG_FORMAT!r}"
    assert mod._SUMMARY_LOG_FORMAT.count("%d") == len(mod._SUMMARY_KEYS)


def test_a6b_leaf_isolation_contracts_survive(monkeypatch):
    """G-270-2/4 양성 대조군 — 관측 보강이 격리 계약을 건드리지 않았다.

    cycle296 은 leaf 에 `import time` 을 더한다. 금지 대상은 `asyncio` import 와
    자체 `sleep` 이지 `time` 이 아니다 — 그 둘이 함께 풀리지 않았는지 다시 잰다.
    """
    tree = ast.parse(_LEAF.read_text(encoding="utf-8"))

    imported: list[str] = []
    from_token: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
            if node.module.startswith("src.auth.token"):
                from_token += [a.name for a in node.names]

    assert not any(n.split(".")[0] == "asyncio" for n in imported), (
        f"leaf 에 asyncio import 금지(자체 sleep·gap 조작 경로) — 실측 {imported}"
    )
    assert from_token == ["get_token_manager"], (
        f"`src.auth.token` 에서 가져오는 이름은 `get_token_manager` 뿐이어야 한다 — "
        f"실측 {from_token}. `issue_history` 는 매니저의 **공개 속성**이라 "
        "`getattr(manager, ...)` 로 읽는다"
    )

    called = {
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    } | {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "sleep" not in called, "leaf 가 직접 sleep 하면 직렬화 계약이 이원화된다"
    # 양성 대조군 — 이 파일이 실제로 leaf 를 읽고 있다(경로가 썩으면 위가 전부 공허해진다).
    assert "revoke" in called and "issue" in called, (
        "leaf 에서 revoke/issue 호출이 사라졌다 — cycle269/270 계약 붕괴"
    )
