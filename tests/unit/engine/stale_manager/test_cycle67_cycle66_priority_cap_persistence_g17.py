"""사이클 67 Red — 사이클 66 priority 분리 *후* cap 영속 G-17 신규 가드 (1 케이스).

> **설계 카드**: `_workspace/cycle67_stale_manager_decomposition_design_card.md`
> **자문 응답 §8.2 G-17**: `_workspace/cycle67_stale_manager_decomposition_domain_response.md`

G-17 (자문 §8.2 신규) — 사이클 66 시정 본체가 `stale_watcher_core` 로 이주 후
AST 가드 위치 보존:
- 결함 패턴: `stale_tickers[:cap]` (priority 분리 *전* cap 적용) 잔존 0건
- 시정 패턴: `low_targets[: max(0, cap - len(high_targets))]` (priority 분리 *후*) 1건
- 사이클 29 005935 사고 영역 영구 차단 의무

Red 시점 결과: PASS (분해 전 stale_manager.py 가 사이클 66 시정 영속).
Green 시점: 분해 후 stale_watcher_core.py 에 영속 = PASS.

본 가드는 사이클 66 K-AST 와 유사하나 *분해 후 파일 위치 변경* 대비 신규 가드.
사이클 66 K-AST 는 stale_manager.py 고정, G-17 은 facade/sub-module 양쪽 지원.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ENGINE = REPO_ROOT / "src" / "engine"


# ===========================================================================
# G-17 — priority 분리 *후* cap 적용 영속 (사이클 66 시정 영속, 위치 변경 대비)
# ===========================================================================
def test_G17_priority_split_before_cap_application_static_guard_post_decomposition():
    """G-17 (사이클 66 시정 영속, 분해 후 위치 변경 대비): `resubscribe_stale_priority`
    본체에 priority 분리 *후* cap 적용 영속.

    사이클 66 시정 (영속 의무):
    - 결함: `targets = stale_tickers[:cap]` (priority 분리 *전* cap 적용)
    - 시정: `targets = high_targets + low_targets[: max(0, cap - len(high_targets))]`

    분해 후 본체 위치:
    - stale_watcher_core.py (분해 후) 또는 stale_manager.py (분해 전).
    - 양쪽 후보 검색 → 발견 시 본체 본체 source AST unparse → substring 검증.

    AST 검증:
    1. 시정 substring `low_targets[: max(0, cap - len(high_targets))]` (공백 ± 허용) 존재
       또는 `low_targets[:max(0, cap - len(high_targets))]` 존재.
    2. 결함 substring `stale_tickers[:cap]` 부재 (영구 차단).
    3. `high_targets` + `low_targets` 분리 변수 영속.

    사이클 29 005935 사고 패턴 (HIGH 종목 cap 밖 잘림 8분 영구 잔류 + LMS chain)
    영구 차단 의무.

    Red 단계: 분해 전 stale_manager.py 가 본체 보유 → PASS.
    Green 단계: 분해 후 stale_watcher_core.py 이주 후 영속 = PASS.
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

    assert target is not None, (
        f"{chosen_path}: `resubscribe_stale_priority` 함수 정의 누락. "
        f"사이클 63 A3 이주 영속 위반"
    )

    func_source = ast.unparse(target)

    # 시정 substring 영속 (공백 ± 허용 — ast.unparse 결과 표준화)
    has_fix_pattern = (
        "low_targets[:max(0, cap - len(high_targets))]" in func_source
        or "low_targets[: max(0, cap - len(high_targets))]" in func_source
    )
    assert has_fix_pattern, (
        f"{chosen_path}: 사이클 66 시정 substring "
        f"(`low_targets[: max(0, cap - len(high_targets))]`) 누락. "
        f"priority 분리 *후* cap 적용 패턴 영속 의무 위반. "
        f"분해 후 stale_watcher_core.py 이주 시 본체 행위 보존 위반."
    )

    # 결함 substring 영구 차단
    assert "stale_tickers[:cap]" not in func_source, (
        f"{chosen_path}: 사이클 63 결함 substring (`stale_tickers[:cap]`) 잔존. "
        f"사이클 66 시정 영속 위반 — priority 분리 *전* cap 적용 = "
        f"사이클 29 005935 사고 패턴 재현 위험 (HIGH 종목 cap 밖 잘림 + LMS chain)."
    )

    # 분리 변수 영속
    assert "high_targets" in func_source and "low_targets" in func_source, (
        f"{chosen_path}: priority 분리 변수 (`high_targets` / `low_targets`) 누락. "
        f"사이클 25-B + 사이클 29-R3 + 사이클 66 시정 영속 의무 위반."
    )
