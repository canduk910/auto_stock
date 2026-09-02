"""cycle239 Red — 게이트 신선도 구조 봉인 (AST/소스 정적 가드).

명세 = `_workspace/red/cycle239_gate_freshness_spec.md` §4.2.
cycle233 의 AST 파일(`test_cycle233_ast_account_risk.py`)은 **봉인 기록으로 무접촉**
— 이 파일이 신선도 계약만 따로 못박는다.

봉인 목록:
- G-239-1: `_GATE_STALE_MAX_SECS` = `_WATCH_INTERVAL_SECS * 3` **곱 파생**(리터럴 900 금지,
  system_config 이관 금지 — `is_soft_gated()` 는 동기 hot path 라 async 게터를 못 부른다).
- G-239-2: `is_soft_gated` 첫 문장 = `if not _gate_active: return False` (hot path 비용 상한).
- G-239-3: 판정 함수군에 ISO 재파싱·벽시계·await 0 (`_gate_age_secs` 는 `_now_mono` 경유).
- G-239-4: 판정 함수군은 **read-only** — `global` 문 0 (단일 기록자 계약).
- G-239-5: `run_account_risk_watch_once` 양 분기에 `_gate_active`/`_evaluated_mono` 대입이
  **await 없이 인접**(스탬프 원자성) + `was_active` 는 **원시 `_gate_active`**
  (cycle239-R1 — 적대 검증 확증: 기록자가 `is_soft_gated()`(fresh-aware)를 부르면
  소비자용 `gate_stale` WARNING/cap 을 선소비해 정상 일일 라이프사이클(20:10 종료 →
  익일 07:55 부팅)마다 거짓 '사멸 의심' 이 발화했다. 상세 = 소스 docstring cycle239-R1).
- G-239-6: `ensure_watch_loop` 에 `add_done_callback` + `_on_watch_loop_done` 정의(사멸 LOUD).

G-239-7(변경 범위 = §5 허용 목록, 전 트리 `git diff` 트립와이어)은 **cycle239-R1 에서
삭제** — 선례(g223_10/g223f_9/cycle222a3 등) 전부 **경로 한정**(`-- <8영역 경로>`)
가드인데 이 가드만 인자 없는 전 트리 diff 라, 커밋 후 클린 트리에서만 통과하고
**다음 어떤 사이클이든** 목록 밖 파일을 하나만 건드리면 거짓 FAIL 한다(동시 활성
cycle238 조차 트립). 8영역 diff-zero 는 기존 가드(경로 한정)가 이미 담당한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WATCHER = ROOT / "src" / "engine" / "account_risk_watcher.py"

# 판정 함수군 — 이 넷은 상태를 **읽기만** 하고 시각은 monotonic seam 으로만 본다.
READ_FUNCS = ("is_soft_gated", "_gate_age_secs", "_is_stale", "get_gate_state")

FORBIDDEN_TIME_CALLS = ("fromisoformat", "strptime", "now", "time")


def _tree() -> ast.Module:
    return ast.parse(WATCHER.read_text(encoding="utf-8"))


def _fn(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"account_risk_watcher.{name} 부재 (cycle239 미구현)")


def _body_after_docstring(node) -> list[ast.stmt]:
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(
        getattr(body[0], "value", None), ast.Constant
    ) and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def _assigned_names(stmt: ast.stmt) -> set[str]:
    if isinstance(stmt, ast.Assign):
        return {t.id for t in stmt.targets if isinstance(t, ast.Name)}
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        return {stmt.target.id}
    return set()


def _call_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            if isinstance(fn, ast.Name):
                names.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                names.add(fn.attr)
    return names


# ===========================================================================
# G-239-1 — 임계는 주기의 3배 파생 (리터럴/설정 이관 금지)
# ===========================================================================
def test_g239_1_stale_threshold_is_derived_from_watch_interval():
    tree = _tree()
    value = None
    for node in tree.body:
        if "_GATE_STALE_MAX_SECS" in _assigned_names(node):
            value = node.value
    assert value is not None, "_GATE_STALE_MAX_SECS 모듈 상수 부재 (cycle239 미구현)"
    assert isinstance(value, ast.BinOp) and isinstance(value.op, ast.Mult), (
        "임계는 `_WATCH_INTERVAL_SECS * 3` 곱 파생이어야 한다 — 리터럴 900 은 "
        "주기 변경 시 조용히 어긋난다"
    )
    operands = {type(value.left), type(value.right)}
    assert operands == {ast.Name, ast.Constant}, ast.dump(value)
    name_node = value.left if isinstance(value.left, ast.Name) else value.right
    const_node = value.right if isinstance(value.left, ast.Name) else value.left
    assert name_node.id == "_WATCH_INTERVAL_SECS", name_node.id
    assert const_node.value == 3, const_node.value

    from src.engine import account_risk_watcher as watcher
    assert watcher._GATE_STALE_MAX_SECS == 900
    assert watcher._GATE_STALE_MAX_SECS == 3 * watcher._WATCH_INTERVAL_SECS


# ===========================================================================
# G-239-2 — fast path 첫 문장 고정
# ===========================================================================
def test_g239_2_is_soft_gated_first_statement_is_fast_path():
    body = _body_after_docstring(_fn(_tree(), "is_soft_gated"))
    assert body, "is_soft_gated 본문 비어 있음"
    first = body[0]
    assert isinstance(first, ast.If), (
        "첫 문장이 fast path 가 아니다 — age 계산이 앞서면 7전략 per-tick 비용 상한 위반"
    )
    test = first.test
    assert isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not), ast.dump(test)
    assert isinstance(test.operand, ast.Name) and test.operand.id == "_gate_active", (
        ast.dump(test)
    )
    assert len(first.body) == 1 and isinstance(first.body[0], ast.Return), ast.dump(first)
    ret = first.body[0].value
    assert isinstance(ret, ast.Constant) and ret.value is False, ast.dump(first)


# ===========================================================================
# G-239-3 — monotonic 단일 소스 (ISO 재파싱·벽시계·await 금지)
# ===========================================================================
@pytest.mark.parametrize("name", READ_FUNCS)
def test_g239_3_read_funcs_have_no_wallclock_or_await(name):
    fn = _fn(_tree(), name)
    called = _call_names(fn)
    for bad in FORBIDDEN_TIME_CALLS:
        assert bad not in called, (
            f"{name} 에 `{bad}` 호출 — 판정은 `_evaluated_mono`(monotonic) 단일 소스여야 "
            "한다(ISO 재파싱은 hot path 비용 + NTP 점프 취약)"
        )
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)], (
        f"{name} 에 await — 동기 hot path 계약 위반"
    )


def test_g239_3b_gate_age_uses_mono_seam():
    fn = _fn(_tree(), "_gate_age_secs")
    assert "_now_mono" in _call_names(fn), (
        "_gate_age_secs 가 `_now_mono` seam 을 경유하지 않는다 (테스트 결정성 seam)"
    )


# ===========================================================================
# G-239-4 — read 경로는 상태를 쓰지 않는다 (단일 기록자)
# ===========================================================================
@pytest.mark.parametrize("name", READ_FUNCS)
def test_g239_4_read_funcs_are_read_only(name):
    fn = _fn(_tree(), name)
    globals_ = [n for n in ast.walk(fn) if isinstance(n, ast.Global)]
    assert not globals_, (
        f"{name} 안에 global 문 — 판정 함수가 상태를 바꾸면 기록자가 둘이 되고 "
        "'같은 사실에 두 답' 이 생긴다"
    )


# ===========================================================================
# G-239-5 — 스탬프 원자성 + fresh-aware was_active (양 분기)
# ===========================================================================
def _try_node(fn) -> ast.Try:
    for node in fn.body:
        if isinstance(node, ast.Try):
            return node
    raise AssertionError("run_account_risk_watch_once 에 try 블록 부재")


def _assert_stamp_block(body: list[ast.stmt], label: str) -> None:
    idx_gate = idx_stamp = None
    for i, stmt in enumerate(body):
        names = _assigned_names(stmt)
        if "_gate_active" in names:
            idx_gate = i
        if "_evaluated_mono" in names:
            idx_stamp = i
    assert idx_gate is not None, f"{label}: `_gate_active` 대입 부재"
    assert idx_stamp is not None, (
        f"{label}: `_evaluated_mono` 스탬프 대입 부재 — 이 분기는 신선도를 "
        "갱신하지 않아 '살아 있는 실패'가 stale 로 오독된다"
    )
    lo, hi = min(idx_gate, idx_stamp), max(idx_gate, idx_stamp)
    for stmt in body[lo:hi + 1]:
        assert not [n for n in ast.walk(stmt) if isinstance(n, ast.Await)], (
            f"{label}: 판정 대입과 스탬프 사이 await — '새 판정 + 낡은 스탬프' 조합이 "
            "관측 가능해진다"
        )


def test_g239_5_run_once_stamps_both_branches_atomically():
    fn = _fn(_tree(), "run_account_risk_watch_once")
    node = _try_node(fn)
    _assert_stamp_block(node.body, "try-body")
    assert node.handlers, "except 핸들러 부재"
    _assert_stamp_block(node.handlers[0].body, "handler-body")


def test_g239_5b_was_active_is_raw_gate_active():
    """cycle239-R1 — `was_active` 는 원시 `_gate_active`(fresh-aware 금지).

    최초 cycle239 설계는 `was_active = is_soft_gated()`(fresh-aware) 였으나,
    적대 검증이 이러면 기록자가 소비자용 `gate_stale` WARNING/cap 을
    선소비해(정상 일일 라이프사이클마다 거짓 '사멸 의심') D2 LOUD 계약을
    실사건에서만 침묵시킴을 확증했다. 시정 = raw `_gate_active` 로 환원.
    """
    fn = _fn(_tree(), "run_account_risk_watch_once")
    found = 0
    for stmt in ast.walk(fn):
        if "was_active" not in _assigned_names(stmt):
            continue
        found += 1
        value = stmt.value
        assert isinstance(value, ast.Name) and value.id == "_gate_active", (
            "was_active 가 `is_soft_gated()` 호출이면 기록자가 소비자용 "
            "stale WARNING/cap 을 선소비한다(cycle239-R1 확증 결함) — 원시 "
            f"`_gate_active` 여야 한다: {ast.dump(value)}"
        )
    assert found == 2, f"was_active 대입이 양 분기에 있어야 한다 (실측 {found})"


# ===========================================================================
# G-239-6 — 루프 사멸 LOUD
# ===========================================================================
def test_g239_6_ensure_watch_loop_registers_done_callback():
    tree = _tree()
    fn = _fn(tree, "ensure_watch_loop")
    assert "add_done_callback" in _call_names(fn), (
        "루프 태스크에 done 콜백 미등록 — 사멸이 완전 무음(Task exception never retrieved)"
    )
    _fn(tree, "_on_watch_loop_done")  # 정의 부재 시 AssertionError


# G-239-7 (전 트리 허용목록 트립와이어)은 cycle239-R1 적대 검증(HIGH 확증 3렌즈)에서
# 삭제됐다 — 근거는 모듈 docstring 상단 및 스펙 §「적대 검증 확증/시정」 참조.
# 8영역 diff-zero 는 기존 경로 한정 가드(g223_10/g223f_9/cycle222a3 등)가 담당한다.
