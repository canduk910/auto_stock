"""사이클 65 (2026-06-06) Red — H-2 scheduler 통합 가드 (1 동적 + 2 AST).

> **선행 명세**: `_workspace/red/cycle65_trade_amount_filter.md` (§File 8)
> **자문 응답**: 사이클 64 hotfix H-2/G-3 패턴 답습 — silent 결함화 영구 차단
> **선례**: 사이클 64 H-2 AST 가드 + _reset_daily_state 동행 호출 패턴

요구 행위 (Red 단계 모두 AssertionError 정답 — scheduler.py 미구현):

- H-2 [MEDIUM]: scheduler `_settle()` 진입 직전 `emit_trade_amount_filter_scanner_daily_summary` 호출 의무 (AST)
- H-2-NO-TRY: 호출이 try/except 로 감싸지지 않음 (사이클 64 hotfix 영구 패턴)
- H-2-RESET: `_reset_daily_state` 가 `reset_trade_amount_filter_daily_state` 호출 의무

위험 등급 MEDIUM (운영자 가시화 카드 영속 의무 보장).

CLAUDE.md 절대 규칙 보호:
- "**`_reset_daily_state` 제거 금지**" — 동행 reset 의무 영속
- 사이클 64 hotfix 영속: H-2 (scheduler 직접 호출) + G-3 (폐기 메서드 0건) 답습
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


SCHEDULER_PATH = Path("src/engine/scheduler.py")


def _parse_scheduler_tree():
    """scheduler.py AST 파싱 헬퍼."""
    assert SCHEDULER_PATH.exists(), f"scheduler.py 경로 결함: {SCHEDULER_PATH.resolve()}"
    src = SCHEDULER_PATH.read_text(encoding="utf-8")
    try:
        return src, ast.parse(src)
    except SyntaxError as e:
        pytest.fail(f"scheduler.py SyntaxError: {e}")


# ===========================================================================
# H-2 [MEDIUM]: scheduler 가 emit_trade_amount_filter_scanner_daily_summary 직접 호출
# ===========================================================================
def test_H2_scheduler_calls_emit_trade_amount_daily_summary():
    """H-2 (MEDIUM): scheduler.py 의 _settle 진입 직전 분기가
    `scanner.emit_trade_amount_filter_scanner_daily_summary` 를 호출해야 함.

    사이클 64 H-2 패턴 답습 — silent 결함화 영구 차단.

    검증 (AST 정적):
    - `emit_trade_amount_filter_scanner_daily_summary` Attribute 접근 또는
      Name 직접 호출 1건 이상.
    """
    src, tree = _parse_scheduler_tree()

    found_calls: list[str] = []

    for node in ast.walk(tree):
        # Attribute 접근 (xxx.emit_trade_amount_filter_scanner_daily_summary)
        if isinstance(node, ast.Attribute) and node.attr == "emit_trade_amount_filter_scanner_daily_summary":
            found_calls.append(f"scheduler.py:L{node.lineno}")
        # 모듈 함수 직접 호출 (emit_trade_amount_filter_scanner_daily_summary())
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "emit_trade_amount_filter_scanner_daily_summary":
                found_calls.append(f"scheduler.py:L{node.lineno} (direct import)")

    assert found_calls, (
        "scheduler.py 내 `emit_trade_amount_filter_scanner_daily_summary` 호출 0건. "
        "사이클 65 H 카테고리 운영자 가시화 카드 무력화 — _settle 직전 분기에서 "
        "`scanner.emit_trade_amount_filter_scanner_daily_summary()` 호출 의무. "
        "권고 시정 위치: scheduler.py L637-640 (사이클 64 price_filter emit 직후)"
    )


# ===========================================================================
# H-2-NO-TRY: 호출이 try/except 로 감싸지지 않음 (사이클 64 hotfix 영구 패턴)
# ===========================================================================
def test_H2_emit_trade_amount_call_not_wrapped_in_try_except():
    """AST 가드 — scheduler.py 의 `emit_trade_amount_filter_scanner_daily_summary` 호출이
    try/except 로 감싸이지 않음 (사이클 64 hotfix H-2 영구 패턴 답습).

    감싸이면 AttributeError 가 silent 되어 회귀 가시화 불가 (사이클 64 H-2 정합성 보존).
    """
    src, tree = _parse_scheduler_tree()

    violations: list[str] = []

    # 모든 Try 노드 walk → 내부에서 emit_trade_amount_filter_scanner_daily_summary 호출 발견 시 위반
    for try_node in ast.walk(tree):
        if not isinstance(try_node, ast.Try):
            continue
        for child in ast.walk(try_node):
            name = None
            if isinstance(child, ast.Attribute):
                name = child.attr
            elif isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                name = child.func.id
            if name == "emit_trade_amount_filter_scanner_daily_summary":
                violations.append(f"scheduler.py:L{getattr(child, 'lineno', try_node.lineno)}")

    assert not violations, (
        f"`emit_trade_amount_filter_scanner_daily_summary` 호출이 try/except 로 감싸짐 "
        f"({len(violations)}건) — 사이클 64 hotfix H-2 영구 패턴 위반:\n"
        + "\n".join(violations)
        + "\n→ 직접 호출 (사이클 64 답습) 의무. silent 결함화 방지 위해 try/except 금지."
    )


# ===========================================================================
# H-2-RESET: _reset_daily_state 가 reset_trade_amount_filter_daily_state 호출 의무
# ===========================================================================
def test_H2_scheduler_reset_daily_state_calls_reset_trade_amount():
    """AST 가드 — `_reset_daily_state` 가 `reset_trade_amount_filter_daily_state` 호출 의무.

    CLAUDE.md 절대 규칙 "**`_reset_daily_state` 제거 금지**" — 동행 reset 의무 영속.
    사이클 64 E-2 답습 (scanner.reset_price_filter_daily_state 동행 호출 패턴).
    """
    src, tree = _parse_scheduler_tree()

    target_func = None
    for node in ast.walk(tree):
        # 동기 def `_reset_daily_state`
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_reset_daily_state":
            target_func = node
            break

    assert target_func is not None, (
        "`_reset_daily_state` 함수 미발견 — scheduler.py 영역 위반"
    )

    found = False
    for child in ast.walk(target_func):
        name = None
        if isinstance(child, ast.Attribute):
            name = child.attr
        elif isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            name = child.func.id
        if name == "reset_trade_amount_filter_daily_state":
            found = True
            break

    assert found, (
        "`_reset_daily_state` 가 `scanner.reset_trade_amount_filter_daily_state` 호출 누락 — "
        "CLAUDE.md `_reset_daily_state` 동행 reset 의무 위반 "
        "(다음 영업일 cap 잔류 + 일일 카운터 누적 결함 위험). "
        "사이클 64 E-2 답습."
    )
