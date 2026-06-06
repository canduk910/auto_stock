"""사이클 67 Red — 사이클 60 영구 가드 영속 G-14~G-15 (2 케이스).

> **설계 카드**: `_workspace/cycle67_stale_manager_decomposition_design_card.md`
> **자문 응답**: `_workspace/cycle67_stale_manager_decomposition_domain_response.md`

G-14~G-15 = 사이클 60 영구 가드 영속 검증:
- G-14: 폐기 메서드 0건 (사이클 64 hotfix H-2 영속, src/ 전체 AST grep)
        — `_emit_price_filter_daily_summary` 잔존 0건 (사이클 62 폐기 메서드)
        — 본 가드는 사이클 67 분해와 직접 무관하나 영구 영속 의무 (refactor 사이클 표준)
- G-15: 사이클 29 005935 사고 영역 가드 영속 — `resubscribe_stale_priority` 의
        HIGH cap 위반 허용 + `[stale_priority_resubscribe_cap_exceeded]` WARNING 로그
        AST 검증 (사이클 66 시정 본체 영속)

Red 시점 결과:
- G-14: PASS (현재 src/ 전체에서 폐기 메서드 호출 0건 — 사이클 64 hotfix 영속)
- G-15: PASS (사이클 66 시정 본체가 stale_manager.py 잔존 — 영속)

Green 시점: 분해 후에도 두 가드 PASS 영속 의무.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "src"
SRC_ENGINE = SRC_ROOT / "engine"


# ===========================================================================
# G-14 — 폐기 메서드 0건 영구 가드 (사이클 64 hotfix H-2 영속)
# ===========================================================================
def test_G14_deprecated_emit_price_filter_daily_summary_zero_calls_in_src():
    """G-14 (사이클 64 hotfix G-3 영속): `_emit_price_filter_daily_summary` 호출 0건.

    사이클 62 폐기 메서드 — 사이클 64 hotfix 시 scheduler.py:638-642 잔존 호출 발견 →
    AttributeError graceful skip → 운영 가시화 무력화 결함. 영구 차단 의무.

    AST grep: src/ 전체에서 함수명 호출 0건 검증.

    본 가드는 사이클 67 분해와 직접 무관하나 모든 refactor 사이클에 *영속 의무*.

    Red/Green 단계 무관: 현재 0건 영속 = 항상 PASS. 향후 누군가 잔존 호출 추가 시
    즉시 FAIL.
    """
    deprecated_name = "_emit_price_filter_daily_summary"
    violations: list[str] = []

    for py_file in SRC_ROOT.rglob("*.py"):
        # _workspace / build 산출물 제외
        if "__pycache__" in py_file.parts:
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if deprecated_name not in source:
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            # 함수 호출 패턴 모두 검사 (Attribute / Name)
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == deprecated_name:
                    violations.append(f"{py_file.relative_to(REPO_ROOT)}:{node.lineno}")
                elif isinstance(func, ast.Name) and func.id == deprecated_name:
                    violations.append(f"{py_file.relative_to(REPO_ROOT)}:{node.lineno}")

    assert not violations, (
        f"`{deprecated_name}` 호출 발견 — 사이클 62 폐기 메서드 영구 차단 의무 위반. "
        f"사이클 64 hotfix H-2 + G-3 영속 패턴 답습 필수. 위반: {violations}"
    )


# ===========================================================================
# G-15 — 사이클 29 005935 사고 영역 가드 영속 (WARNING 로그 + cap 위반 허용)
# ===========================================================================
def test_G15_cycle29_accident_area_warning_log_persisted():
    """G-15 (사이클 29 005935 사고 영역 영속): `resubscribe_stale_priority` 본체에
    `[stale_priority_resubscribe_cap_exceeded]` WARNING 로그 영속.

    사이클 29 005935 사고 패턴:
    - 보유 005935 stale → HIGH cap 밖 잘림 → 8분 영구 잔류 → KIS LMS chain.
    - 사이클 66 시정 = HIGH > cap 허용 + WARNING 로그 운영 가시화 (Q3 옵션 A).

    AST 검증:
    1. `resubscribe_stale_priority` 본체에 `logger.warning(...)` 호출 발견
    2. 호출 첫 인자에 `[stale_priority_resubscribe_cap_exceeded]` substring 포함

    Red 단계: 분해 전 stale_manager.py 가 사이클 66 시정 본체 보유 → PASS.
    Green 단계: 분해 후 stale_watcher_core.py 에 영속 = PASS.
    """
    candidate_paths = [
        SRC_ENGINE / "stale_watcher_core.py",
        SRC_ENGINE / "stale_manager.py",
    ]
    source = None
    chosen_path = None
    for p in candidate_paths:
        if p.exists():
            source = p.read_text(encoding="utf-8")
            chosen_path = p
            break

    assert source is not None, "stale_watcher_core.py / stale_manager.py 모두 미존재"

    tree = ast.parse(source)
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "resubscribe_stale_priority":
            target = node
            break

    assert target is not None, f"{chosen_path}: `resubscribe_stale_priority` 누락"

    found_warning = False
    for node in ast.walk(target):
        if isinstance(node, ast.Call):
            func = node.func
            # logger.warning(...) 매칭
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "warning"
                and isinstance(func.value, ast.Name)
                and func.value.id == "logger"
            ):
                # 첫 인자에 cap_exceeded substring 검사
                if node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        if "[stale_priority_resubscribe_cap_exceeded]" in first.value:
                            found_warning = True
                            break

    assert found_warning, (
        f"{chosen_path}: `resubscribe_stale_priority` 에 "
        f"`logger.warning('[stale_priority_resubscribe_cap_exceeded] ...')` 누락. "
        f"사이클 66 Q3 옵션 A 영속 + 사이클 29 005935 사고 영역 가드 의무 위반 — "
        f"HIGH > cap 시 운영 가시화 silent 누락 위험."
    )
