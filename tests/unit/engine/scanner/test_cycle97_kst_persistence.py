"""사이클 97 L-2 — KST 영속 (LOW).

명세 (`_workspace/red/cycle97_fluctuation_api_replacement.md`):

- 사이클 96 KST 영속 영역 영구 정합
- 사이클 68 KST 일관성 영속 (`_kst.py` 헬퍼)
- 사이클 97 영역 신규 도입 후에도 KST 영속

기대 동작 (영속, backend-dev 인계):
- scanner.py 에 `KST_TZ` import 영속
- `datetime.utcnow()` 영구 부재 (UTC naive 0건 AST 정적 가드)

Red 상태 (사이클 97): production 코드 영속 → PASS (사이클 96 영속 가드 영역).

영속 의무:
- 사이클 68 KST 일관성 영속
- 사이클 96 KST 영속 답습
- "절대 깨지 말 것" KST 강제 영속
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _scanner_module_path() -> Path:
    """scanner.py 모듈 절대 경로."""
    import src.engine.scanner as scanner_mod
    return Path(scanner_mod.__file__)


def _scanner_module_source() -> str:
    return _scanner_module_path().read_text(encoding="utf-8")


def test_l2_kst_tz_import_persisted():
    """L-2.a: scanner.py 에 `KST_TZ` 또는 KST 영속 import 영역.

    검증 영역:
    - `from src.db._kst import KST` 영속 (사이클 68 헬퍼)
    - 또는 모듈 내 `KST_TZ` 정의 영속 (사이클 95+ 영역 답습)

    영속 의무: 사이클 68 KST 일관성 영속 + "절대 깨지 말 것" KST 강제 영속.
    """
    source = _scanner_module_source()

    # KST 영역 다양한 패턴 (사이클 95+ 영역)
    kst_patterns = [
        "KST",
        "Asia/Seoul",
        "ZoneInfo",
        "timezone(timedelta(hours=9))",
    ]

    found_any = any(pat in source for pat in kst_patterns)
    assert found_any, (
        f"\n사이클 97 L-2.a 위반 — scanner.py KST 영역 부재:\n"
        f"  기대 패턴 (any): {kst_patterns}\n"
        f"  사이클 68 KST 일관성 영속 의무"
    )


def test_l2_no_datetime_utcnow_in_scanner():
    """L-2.b: scanner.py 에 `datetime.utcnow()` UTC naive 영구 부재.

    검증 영역 (AST + raw text grep):
    - `datetime.utcnow()` 직접 호출 영구 부재
    - `utcnow()` 단독 영역도 영구 부재

    영속 의무: 사이클 68 KST 일관성 영속 + "모든 시각 데이터 KST 강제" 영구 영속.
    """
    source = _scanner_module_source()

    # raw text grep 1차
    forbidden_literals = [
        "datetime.utcnow()",
        ".utcnow(",
    ]
    found_literals: list[str] = []
    for lit in forbidden_literals:
        if lit in source:
            found_literals.append(lit)

    assert not found_literals, (
        f"\n사이클 97 L-2.b 위반 — scanner.py UTC naive 영속:\n"
        f"  발견 literal: {found_literals}\n"
        f"  사이클 68 KST 일관성 영속 의무\n"
        f"  CLAUDE.md '절대 깨지 말 것' 영역: 모든 시각 데이터 KST 강제"
    )

    # AST 2차 (utcnow attribute 호출)
    tree = ast.parse(source)
    found_calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "utcnow":
                found_calls.append("utcnow() call")

    assert not found_calls, (
        f"\n사이클 97 L-2.b 위반 — scanner.py utcnow() 호출 영속:\n"
        f"  발견: {found_calls}\n"
        f"  사이클 68 KST 일관성 영속 의무"
    )
