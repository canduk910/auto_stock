"""사이클 63 Phase 2-A3 Red — D 카테고리: 의존성 역전 AST 정적 가드 (2 케이스).

> **선행 명세**: `_workspace/red/cycle63_phase2A3.md` §2 D
> **선례**: 사이클 60 A1 D-1 + 사이클 61 A2 D-1 답습 + 강화.

D-1: stale_manager.py 가 scheduler.py 정적 import 0건 (순환 의존 차단).
D-2: A3 이주 후 신규 함수도 `sys.modules.get("src.engine.scheduler")` 패턴 사용
     (Q4 RECOMMEND + 사이클 61 패턴 답습 — lazy import 빚 청산).

Red 단계: A3 함수 미이주 → D-2 는 함수 부재로 검증 skip 또는 FAIL.
Green 단계: A3 2 함수 모두 `sys.modules.get` 패턴 적용 → PASS.

회귀 가드: stale_manager 가 scheduler 역참조 시 모듈 분해 의미 상실.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_D1_stale_manager_does_not_import_scheduler_statically():
    """D-1: `ast` 모듈로 `src/engine/stale_manager.py` parsing → scheduler 정적 import 0건.

    A3 이주 후에도 본 가드 PASS 의무 — `from src.engine.scheduler import ...` /
    `from src.engine import scheduler` / `import src.engine.scheduler` 금지.

    `sys.modules.get("src.engine.scheduler")` 패턴은 정적 import 가 아니므로 D-1 통과.
    """
    path = Path("src/engine/stale_manager.py")
    assert path.exists(), "stale_manager.py 존재 의무"

    tree = ast.parse(path.read_text(encoding="utf-8"))
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "src.engine.scheduler":
                violations.append(
                    f"L{node.lineno}: `from src.engine.scheduler import ...` 역참조"
                )
            if node.module == "src.engine" and any(
                alias.name == "scheduler" for alias in node.names
            ):
                violations.append(
                    f"L{node.lineno}: `from src.engine import scheduler` 역참조"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src.engine.scheduler":
                    violations.append(
                        f"L{node.lineno}: `import src.engine.scheduler` 역참조"
                    )

    assert not violations, (
        "stale_manager.py 가 scheduler 역참조 — 의존성 역전 위반:\n"
        + "\n".join(violations)
    )


def test_D2_a3_functions_use_sys_modules_get_pattern():
    """D-2: A3 2 함수가 `sys.modules.get("src.engine.scheduler")` 패턴 사용.

    domain Q4 RECOMMEND + 사이클 61 A2 패턴 답습. `kis_ws_pool` / `datetime.now()` /
    `scanner` 접근 시 scheduler 네임스페이스 우선 참조 → 테스트 patch 호환.

    Red: A3 미이주 → 함수 부재 → AttributeError 또는 패턴 grep 0건.
    Green: `check_and_resubscribe_stale` / `resubscribe_stale_priority` 본체에
           `sys.modules.get("src.engine.scheduler")` 1회 이상 호출 의무.

    사이클 67 분해 후:
    - A2 함수 (detect_silent_inactive_sessions + force_reconnect_session) →
      stale_session_recovery.py 로 이주
    - A3 함수 (check_and_resubscribe_stale + resubscribe_stale_priority) →
      stale_watcher_core.py 로 이주
    stale_manager.py 는 facade (re-export only) — 직접 grep 대신 sub-module 합산.
    """
    # 사이클 67 분해 후: 함수 본체는 각 sub-module 에 위치.
    # stale_session_recovery.py = A2 (2건), stale_watcher_core.py = A3 (2건 이상).
    # stale_manager.py (facade) 는 re-export only — 패턴 0건 정상.
    candidate_paths = [
        Path("src/engine/stale_watcher_core.py"),   # A3 함수 본체
        Path("src/engine/stale_session_recovery.py"),  # A2 함수 본체
    ]

    pattern = 'sys.modules.get("src.engine.scheduler")'
    count = 0
    for p in candidate_paths:
        if p.exists():
            count += p.read_text(encoding="utf-8").count(pattern)

    # 함수 본문 전체에서 `sys.modules.get("src.engine.scheduler")` 패턴 출현 수
    # 사이클 61 A2 = 2건 이상 (detect_silent_inactive_sessions + force_reconnect_session).
    # 사이클 63 A3 추가 2건 이상 의무 (check_and_resubscribe_stale +
    # resubscribe_stale_priority) → 총 ≥ 4건.
    assert count >= 4, (
        f"`sys.modules.get(\"src.engine.scheduler\")` 패턴 출현 수 {count} < 4. "
        f"사이클 61 A2 기존 2건 (stale_session_recovery.py) + "
        f"사이클 63 A3 신규 2건 이상 (stale_watcher_core.py) 의무. "
        f"A3 2 함수가 scheduler 네임스페이스 우회 시 테스트 patch 호환 깨짐 + "
        f"운영 객체 동일성 깨짐 위험."
    )
