"""사이클 95 L-1 — 사이클 88 G-REJECT 영속 (외부 LLM 영구 차단 AST 가드 영역 0) (LOW).

명세 (`_workspace/red/cycle95_chicken_and_egg_fix_ui.md` §3 L-1):

- 사이클 88 G-REJECT-1/2/3 AST 가드 (외부 LLM 영구 차단 패턴) 영역 영속
- 사이클 95 시정 영역과 무관 (영역 분리)
- AST 가드 파일 영속 의무

영속 의무:
- 사이클 88 G-REJECT 영역 영속 (변경 0)
- 사이클 89/90/91/92/93/94 답습 영역 영속
- 사이클 95 시정 = scanner 행위 영역만 (AST 가드 영역 영향 0)
- 매매 안전성 영향 0
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_l1_cycle88_g_reject_ast_guard_file_persists():
    """L-1.a: 사이클 88 G-REJECT AST 가드 파일 영속 (변경 0).

    사이클 89/90/91/92/93/94 답습 영역.

    영속 의무: 사이클 95 시정 시 G-REJECT 영역 변경 0.
    """
    guard_files = [
        "tests/unit/ast/test_cycle89_g_reject_persistence.py",
        "tests/unit/ast/test_cycle90_g_reject_persistence.py",
        "tests/unit/ast/test_cycle92_g_reject_persistence.py",
    ]

    repo_root = Path(__file__).resolve().parents[4]

    missing = []
    for relpath in guard_files:
        full_path = repo_root / relpath
        if not full_path.exists():
            missing.append(relpath)

    assert missing == [], (
        f"\n사이클 95 L-1.a 위반 — 사이클 88 G-REJECT 영속 가드 파일 부재:\n"
        f"  부재: {missing}\n"
        f"  영속 의무: 사이클 88 G-REJECT 영역 변경 0"
    )


def test_l1_cycle95_does_not_introduce_g_reject_keywords_in_scanner():
    """L-1.b: scanner.py 가 사이클 95 시정 후에도 G-REJECT 금지 키워드 0건 영속.

    사이클 88 G-REJECT 답습 영역 영속 의무.

    검증 영역:
    - `# 외부 LLM` 코멘트 부재
    - `# external llm` 부재
    - `external_llm_recommendation` 함수 부재
    """
    import inspect

    from src.engine import scanner as scanner_mod

    source = inspect.getsource(scanner_mod)
    source_lower = source.lower()

    forbidden_patterns = [
        "# 외부 llm",
        "# external llm",
        "external_llm_recommendation",
    ]

    leaked = []
    for pattern in forbidden_patterns:
        if pattern in source_lower:
            leaked.append(pattern)

    assert leaked == [], (
        f"\n사이클 95 L-1.b 위반 — G-REJECT 금지 키워드 영속 결함:\n"
        f"  잔존 영역: {leaked}\n"
        f"  사이클 88 G-REJECT 영구 차단 영역 영속 의무"
    )
