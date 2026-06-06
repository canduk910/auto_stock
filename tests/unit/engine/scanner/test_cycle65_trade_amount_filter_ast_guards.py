"""사이클 65 (2026-06-06) Red — G 카테고리: AST 정적 가드 (1 케이스 HIGH + 호출 카운트 1).

> **선행 명세**: `_workspace/red/cycle65_trade_amount_filter.md` (§File 6)
> **자문 응답**: Q1 옵션 D 답습 — `_apply_trade_amount_filter` 호출 시 `protected_tickers=` keyword 의무
> **선례**: 사이클 64 G-2 AST 가드 패턴 직답습

요구 행위 (Red 단계 모두 AssertionError 정답 — scanner.py 미구현):

- G-1 [HIGH]: `_apply_trade_amount_filter` 호출 시 `protected_tickers=` keyword 의무
- G-1-CC: `subscribe_filtered_stocks` 내부 `_apply_trade_amount_filter` 호출 카운트 의무

위험 등급 HIGH (보유/익일청산 보호 우회 결함 차단).

CLAUDE.md 절대 규칙 보호:
- "**WebSocket 시세 보유·익일청산 우선 보장**" — protected_tickers 누락 시 자동 우회 영구 차단
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# G-1 (HIGH): `_apply_trade_amount_filter` 호출 시 protected_tickers keyword 의무
# ===========================================================================
def test_G1_apply_trade_amount_filter_must_pass_protected_tickers_kwarg():
    """G-1 (HIGH, Q1 옵션 D): `_apply_trade_amount_filter` 호출 시 `protected_tickers=` keyword 필수.

    호출자가 깜빡 `_apply_trade_amount_filter(candidates)` 만 호출하면 보유/익일청산 종목이
    필터링 대상에 진입 → 시세 끊김 → 손절 발화 0 결함.

    AST 정적 검증 — `scanner.py` 모듈 전체 스캔.
    호출 식별:
    1. `Name` (`_apply_trade_amount_filter(...)`) — 모듈 함수 직접 호출
    2. `Attribute` (`xxx._apply_trade_amount_filter(...)`) — 메서드 호출

    사이클 64 G-2 패턴 답습 (검증 의미 동일).
    """
    scanner_path = Path("src/engine/scanner.py")
    assert scanner_path.exists(), f"scanner.py 경로 결함: {scanner_path.resolve()}"
    source = scanner_path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        pytest.fail(f"scanner.py SyntaxError: {e}")

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func

        fname = None
        if isinstance(fn, ast.Name) and fn.id == "_apply_trade_amount_filter":
            fname = "_apply_trade_amount_filter"
        elif isinstance(fn, ast.Attribute) and fn.attr == "_apply_trade_amount_filter":
            fname = "_apply_trade_amount_filter"

        if fname is None:
            continue

        kw_keys = {kw.arg for kw in node.keywords if kw.arg is not None}
        if "protected_tickers" not in kw_keys:
            violations.append(
                f"scanner.py:L{node.lineno} — `_apply_trade_amount_filter` 호출 시 "
                f"`protected_tickers=` keyword 누락 (kwargs={sorted(kw_keys)})"
            )

    assert not violations, (
        f"G-1 (HIGH) 자문 옵션 D 위반 — `protected_tickers=` keyword 누락 호출 "
        f"{len(violations)}건. 보유/익일청산 보호 우회 결함 위험:\n"
        + "\n".join(violations)
    )


# ===========================================================================
# G-1-CC: subscribe_filtered_stocks 내부 호출 4회 의무
# ===========================================================================
def test_G1_call_count_in_subscribe_filtered_stocks():
    """`subscribe_filtered_stocks` 내부에서 `_apply_trade_amount_filter` 호출 4회 의무.

    호출 위치 (사이클 65 설계 카드 v2 §2.2):
    1. tickers (1)
    2. extra_tickers (1)
    3. priority_groups 3 키 (breakout / momentum / swing) — 단 `if priority_groups.get(key)` 분기

    누락 시 일부 priority key 만 필터 적용 = 회귀 (사이클 64 G-2 답습).
    """
    scanner_path = Path("src/engine/scanner.py")
    source = scanner_path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        pytest.fail(f"scanner.py SyntaxError: {e}")

    target_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "subscribe_filtered_stocks":
            target_func = node
            break

    assert target_func is not None, (
        "`subscribe_filtered_stocks` AsyncFunctionDef 미발견 — scanner.py 영역 위반"
    )

    call_count = 0
    for node in ast.walk(target_func):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = None
        if isinstance(fn, ast.Name):
            name = fn.id
        elif isinstance(fn, ast.Attribute):
            name = fn.attr
        if name == "_apply_trade_amount_filter":
            call_count += 1

    assert call_count == 4, (
        f"`_apply_trade_amount_filter` 호출 4회 의무 (실제 {call_count}회). "
        "위치: tickers (1) + extra_tickers (1) + priority_groups 3 키 (breakout/momentum/swing)."
    )
