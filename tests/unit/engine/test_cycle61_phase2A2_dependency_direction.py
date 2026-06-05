"""사이클 61 Phase 2-A2 Red — D 카테고리: 의존성 역전 정적 검증 (1 케이스).

> **선행 명세**: `_workspace/red/cycle61_phase2A2_stale_manager.md` (Q3-G6 갱신)
> **선례**: 사이클 60 A1 `test_D1_stale_manager_does_not_import_scheduler` 답습 + 강화.

`stale_manager.py` 가 `scheduler.py` 를 역참조하면 순환 의존 위험 + 모듈 분해 무의미.

**A2 시점 강화**: 사이클 60 A1 의 `_build_session_subscription_view` 가 사용한 lazy
import 패턴 (`from src.engine import scheduler as _sched_mod; _sched_mod.STALE_FRESHNESS_SECS`)
은 본 사이클 Green 시점 제거 의무 — `STALE_FRESHNESS_SECS` 가 stale_manager 로 이전된 후
자연 해소.

Red 단계: stale_manager.py L62 에 `from src.engine import scheduler as _sched_mod`
잔존 → 본 케이스 FAIL 정상.
Green: 본 lazy import 제거 → 검증 PASS.

회귀 가드: 단순화 원칙 — stale_manager 가 scheduler 역참조하면 모듈 분해 의미 상실.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_D1_stale_manager_does_not_import_scheduler():
    """D-1: `ast` 모듈로 `src/engine/stale_manager.py` parsing → scheduler import 0건.

    검증 대상 (모두 fail):
    - `from src.engine.scheduler import ...`
    - `from src.engine import scheduler` (alias 무관)
    - `import src.engine.scheduler`

    A2 시점 의무: `STALE_FRESHNESS_SECS` lazy import 제거 (이전 후 자연 해소).
    """
    path = Path("src/engine/stale_manager.py")
    assert path.exists(), "stale_manager.py 가 존재해야 함 (Red 단계 미존재 시 FAIL)"

    tree = ast.parse(path.read_text(encoding="utf-8"))
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "src.engine.scheduler":
                violations.append(
                    f"L{node.lineno}: `from src.engine.scheduler import ...` 역참조 발견"
                )
            if node.module == "src.engine" and any(
                alias.name == "scheduler" for alias in node.names
            ):
                violations.append(
                    f"L{node.lineno}: `from src.engine import scheduler` 역참조 발견 "
                    "(사이클 60 A1 의 STALE_FRESHNESS_SECS lazy import 제거 의무 — "
                    "A2 시점 stale_manager 로 이전 후 자연 해소)"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src.engine.scheduler":
                    violations.append(
                        f"L{node.lineno}: `import src.engine.scheduler` 역참조 발견"
                    )

    assert not violations, (
        "stale_manager.py 가 scheduler 역참조 — 의존성 역전 위반:\n"
        + "\n".join(violations)
    )
