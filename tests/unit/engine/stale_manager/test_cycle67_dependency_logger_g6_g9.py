"""사이클 67 Red — sub-module 의존성 + logger binding G-6~G-9 (4 케이스).

> **설계 카드**: `_workspace/cycle67_stale_manager_decomposition_design_card.md`
> **자문 응답**: `_workspace/cycle67_stale_manager_decomposition_domain_response.md`

G-6~G-9 = 의존성 + logger 검증 (AST 정적 가드):
- G-6 (Q3, HIGH): 4 sub-module 모두 `logging.getLogger("src.engine.scheduler")` 명시 binding
                  — 사이클 60 I1 영속 (caplog 호환 + 운영 logging.yaml 호환)
- G-7 (Q1): import 의존성 단방향 — stale_watcher_core 가 진단/복구/가드 호출,
            역방향 0건 (옵션 A 단방향)
- G-8 (Q2): stale_watcher_core 가 `from src.engine.stale_diagnostics import emit_stale_session_detail`
            모듈-레벨 정적 import 영속 (Q4=B 직접 호출 + 자문 §3 Q2 옵션 P1)
- G-9 (Q5): scheduler.py 11 wrapper 가 facade 경유 lazy import
            (`from src.engine import stale_manager`) 영속 — 변경 0

Red 시점 결과:
- G-6, G-7, G-8: FAIL (4 sub-module 미존재)
- G-9: PASS (scheduler.py 현재 facade 경유 lazy import 영속 — 자연 통과)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ENGINE = REPO_ROOT / "src" / "engine"

SUB_MODULES = [
    "stale_diagnostics",
    "stale_session_recovery",
    "stale_universe_guard",
    "stale_watcher_core",
]


# ===========================================================================
# G-6 (HIGH) — logger binding 영속 (사이클 60 I1 영속)
# ===========================================================================
def test_G6_logger_binding_src_engine_scheduler_consistency():
    """G-6 (Q3 옵션 A, HIGH): 4 sub-module 모두 `logging.getLogger("src.engine.scheduler")` binding.

    사이클 60 I1 영속 의무:
    - caplog `set_level(logger="src.engine.scheduler")` 호환 (78 회귀 가드)
    - 운영 logging.yaml `src.engine.scheduler` 단일 logger 명시 호환
    - sub-module 별 logger 시 silent 누락 위험 (사이클 60 I1 hotfix 답습 사례)

    AST walk:
    - `logger = logging.getLogger("src.engine.scheduler")` 패턴 검색
    - 4 sub-module 모두 해당 패턴 존재 의무

    Red 단계: sub-module 미존재 = FileNotFoundError = FAIL.
    Green 단계: 4 sub-module 모두 영속 = PASS.
    """
    for mod_name in SUB_MODULES:
        path = SRC_ENGINE / f"{mod_name}.py"
        if not path.exists():
            pytest.fail(
                f"`{path}` 미존재 — 사이클 67 분해 G-1~G-4 미완료. "
                f"G-6 검증 진입 불가."
            )

        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id == "logger":
                    if isinstance(node.value, ast.Call):
                        func = node.value.func
                        # logging.getLogger(...) 패턴
                        if (
                            isinstance(func, ast.Attribute)
                            and func.attr == "getLogger"
                            and len(node.value.args) == 1
                            and isinstance(node.value.args[0], ast.Constant)
                            and node.value.args[0].value == "src.engine.scheduler"
                        ):
                            found = True
                            break

        assert found, (
            f"{path}: `logger = logging.getLogger('src.engine.scheduler')` 누락. "
            f"사이클 60 I1 영속 의무 위반 — caplog 78 회귀 가드 silent 누락 위험 + "
            f"운영 logging.yaml 호환 깨짐."
        )


# ===========================================================================
# G-7 (Q1) — import 의존성 단방향 (옵션 A)
# ===========================================================================
def test_G7_import_dependency_acyclic_unidirectional():
    """G-7 (Q1 옵션 A): import 의존성 단방향 — 진단/복구/가드 가 watcher_core import 0건.

    옵션 A 단방향 의존 구조:
    - stale_watcher_core → stale_diagnostics / stale_session_recovery / stale_universe_guard
                          (cross-module call 허용)
    - 역방향 0건 (순환 import 차단)

    AST walk: 3 모듈 (diagnostics / session_recovery / universe_guard) 의 `Import` /
    `ImportFrom` 노드에서 `stale_watcher_core` 참조 0건 검증.

    Red 단계: sub-module 미존재 = FileNotFoundError = FAIL.
    Green 단계: 단방향 영속 = PASS.
    """
    # watcher_core 를 import 하면 안 되는 3 모듈
    non_watcher_modules = [
        "stale_diagnostics",
        "stale_session_recovery",
        "stale_universe_guard",
    ]

    for mod_name in non_watcher_modules:
        path = SRC_ENGINE / f"{mod_name}.py"
        if not path.exists():
            pytest.fail(
                f"`{path}` 미존재 — 사이클 67 분해 G-1~G-4 미완료. G-7 검증 진입 불가."
            )

        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            # `from src.engine.stale_watcher_core import X` 차단
            if isinstance(node, ast.ImportFrom):
                if node.module and "stale_watcher_core" in node.module:
                    pytest.fail(
                        f"{path} L{node.lineno}: `from {node.module} import ...` 발견. "
                        f"옵션 A 단방향 의존 위반 — 순환 import 위험."
                    )
            # `import src.engine.stale_watcher_core` 차단
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "stale_watcher_core" in alias.name:
                        pytest.fail(
                            f"{path} L{node.lineno}: `import {alias.name}` 발견. "
                            f"옵션 A 단방향 의존 위반."
                        )


# ===========================================================================
# G-8 (Q2) — Q4=B cross-module 모듈-레벨 정적 import 영속
# ===========================================================================
def test_G8_stale_watcher_core_imports_emit_stale_session_detail_at_module_level():
    """G-8 (Q2 옵션 P1): stale_watcher_core 가 `from src.engine.stale_diagnostics import ...`
    모듈-레벨 정적 import 영속.

    자문 §3 Q2 옵션 P1 (모듈-레벨 정적 import) 채택:
    - Q4=B 직접 호출 (사이클 63 영속) + cross-module → 명시 import 필요
    - 함수-레벨 lazy import (P1') 비채택 — 가독성 + AST G-7 가드 검증 명시성

    AST walk: stale_watcher_core 의 *모듈-레벨* ImportFrom 에서
    `module=='src.engine.stale_diagnostics'` + `'emit_stale_session_detail'` 포함 검증.

    Red 단계: stale_watcher_core 미존재 = FAIL.
    Green 단계: 모듈-레벨 정적 import 영속 = PASS.
    """
    path = SRC_ENGINE / "stale_watcher_core.py"
    if not path.exists():
        pytest.fail(
            f"`{path}` 미존재 — 사이클 67 분해 G-4 미완료. G-8 검증 진입 불가."
        )

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 모듈-레벨 (tree.body 직접) ImportFrom 만 순회
    found = False
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.module == "src.engine.stale_diagnostics":
                names = [alias.name for alias in node.names]
                if "emit_stale_session_detail" in names:
                    found = True
                    break

    assert found, (
        "stale_watcher_core.py 모듈-레벨에 "
        "`from src.engine.stale_diagnostics import emit_stale_session_detail` 누락. "
        "자문 §3 Q2 옵션 P1 (모듈-레벨 정적 import) 의무 위반. "
        "함수-레벨 lazy import 사용 시 가독성 ↓ + G-7 AST 가드 검증 어려움."
    )


# ===========================================================================
# G-9 (Q5) — scheduler.py 11 wrapper 가 facade 경유 lazy import 영속
# ===========================================================================
def test_G9_scheduler_wrappers_use_facade_lazy_import():
    """G-9 (Q5 옵션 A): scheduler.py 11 wrapper 가 `from src.engine import stale_manager` 영속.

    Q5 옵션 A: facade 유지 + scheduler.py wrapper 변경 0 의무:
    - 사이클 60~66 8 사이클 답습 패턴 100% 영속
    - 4 sub-module 분해 후에도 wrapper 변경 0 보장 (facade re-export 가 호환)
    - wrapper 내부 `from src.engine import stale_manager` 형태 영속

    분해 후 sub-module 직접 import (`from src.engine.stale_diagnostics import X`) 로
    변경되면 wrapper 시그너처 영향 + 외부 인터페이스 변경 → 사이클 60 §Q5 push 시점
    의무 위반.

    AST walk: scheduler.py 의 *함수 본체 내* ImportFrom 중 `module == 'src.engine'` +
    `names == ['stale_manager']` 패턴 11회 이상 검증.

    Red 단계: PASS (scheduler.py 현재 11 wrapper 모두 facade 경유).
    Green 단계: PASS (변경 0 의무 — facade 유지로 영속).
    """
    path = SRC_ENGINE / "scheduler.py"
    assert path.exists(), f"scheduler.py 미존재: {path}"

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    facade_import_count = 0
    # 모든 함수 본체 + 클래스 메서드 본체에서 facade lazy import 검색
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if isinstance(child, ast.ImportFrom):
                    # `from src.engine import stale_manager` 패턴
                    if child.module == "src.engine":
                        names = [alias.name for alias in child.names]
                        if "stale_manager" in names:
                            facade_import_count += 1

    # 사이클 60~63 누적 11 wrapper = 최소 11 회 lazy import 출현 의무
    assert facade_import_count >= 11, (
        f"scheduler.py wrapper facade lazy import 발견 수 = {facade_import_count}, "
        f"기대 ≥ 11 (사이클 60+61+63 누적 11 wrapper). Q5 옵션 A 영속 의무 위반 — "
        f"wrapper 가 sub-module 직접 import 로 변경되면 외부 인터페이스 변경 "
        f"+ 사이클 60 §Q5 push 시점 의무 위반."
    )
