"""사이클 67 Red — facade patch silent 결함 영구 차단 G-16 신규 가드 (1 케이스).

> **설계 카드**: `_workspace/cycle67_stale_manager_decomposition_design_card.md`
> **자문 응답 §5 Q4**: `_workspace/cycle67_stale_manager_decomposition_domain_response.md`

G-16 (자문 §5 Q4 신규) — Q4 옵션 B (facade patch 영속) 안전선 가드:
- `patch("src.engine.stale_manager.X")` 패턴은 facade re-export 만 변경,
  sub-module 정의 (`src.engine.stale_diagnostics.X` 등) 는 미변경 → silent 결함.
- 본 가드는 *향후* 누군가가 facade 직접 patch 추가 시 즉시 FAIL.
- 단, 해당 이름이 facade re-export 함수일 경우에만 silent 결함이므로:
  - facade 의 export 목록 (11 함수 + 10 상수) 기준으로 patch 대상 일치 시 위반.
  - export 목록 외 (예: 모듈 자체 내부 헬퍼) patch 는 허용.

자문 §5 Q4 실측: `patch("src.engine.stale_manager.*")` 현재 0건.
본 가드는 *향후 silent 결함* 차단 영구 의무.

Red 시점 결과: PASS (현재 violations 0건 — 실측 0건).
Green 시점: 분해 후에도 PASS 영속 의무.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
TESTS_ROOT = REPO_ROOT / "tests"


# ===========================================================================
# G-16 — facade patch silent 결함 영구 차단
# ===========================================================================
def test_G16_no_patch_via_stale_manager_facade_for_re_exported_names():
    """G-16 (자문 §5 Q4 신규): `patch("src.engine.stale_manager.<name>")` 패턴 사용 0건.

    silent 결함 차단 원리:
    - facade 가 sub-module 함수를 re-export → `from src.engine.stale_diagnostics import X`
      로 import 하는 코드는 sub-module patch (`patch("src.engine.stale_diagnostics.X")`) 만
      효력 발생.
    - facade patch (`patch("src.engine.stale_manager.X")`) 는 facade 모듈 내 reference 만
      교체 → 원본 sub-module 함수 호출 경로는 미변경 → 테스트가 *patch 가 적용된 것처럼*
      착각하나 실제 호출 시 원본 실행 = silent 결함.

    검증: tests/ 전체에서 `patch("src.engine.stale_manager.<X>")` 호출 노드 AST grep.
    위반 발견 시 sub-module 직접 patch 권고 메시지 출력.

    예외 영역:
    - facade 모듈 자체에만 정의된 헬퍼/상수 (re-export 아닌) 는 facade patch 정당.
      그러나 사이클 67 분해 후 facade 는 *re-export only* 의무 (자문 §2 Q1 옵션 A) →
      모든 patch("src.engine.stale_manager.*") 가 silent 결함 위험.

    Red/Green 단계 무관: 현재 0건 = PASS. 향후 누군가 추가 시 즉시 FAIL.
    """
    violations: list[str] = []
    facade_prefix = "src.engine.stale_manager."

    for test_file in TESTS_ROOT.rglob("test_*.py"):
        # 자기 자신은 검증 의도가 명시되어 있으므로 skip
        if test_file.name == "test_cycle67_facade_patch_persistence_g16.py":
            continue
        if "__pycache__" in test_file.parts:
            continue

        try:
            source = test_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # 빠른 사전 필터
        if "stale_manager" not in source:
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # patch("...") / mock.patch("...") / unittest.mock.patch("...") 매칭
                func_name = None
                if isinstance(func, ast.Name) and func.id == "patch":
                    func_name = "patch"
                elif isinstance(func, ast.Attribute) and func.attr == "patch":
                    func_name = "patch"

                if func_name and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        target = first.value
                        if target.startswith(facade_prefix):
                            # facade re-export 대상 이름 추출
                            rest = target[len(facade_prefix):]
                            # 단일 토큰 (.split('.')[0])
                            attr_name = rest.split(".")[0]
                            violations.append(
                                f"{test_file.relative_to(REPO_ROOT)}:{node.lineno} "
                                f"patch('{target}') → 권고: "
                                f"patch('src.engine.<sub_module>.{attr_name}')"
                            )

    assert not violations, (
        "`patch('src.engine.stale_manager.X')` 패턴 발견 — facade reference 만 변경, "
        "sub-module 정의 미변경 → silent 결함 위험 (자문 §5 Q4 옵션 B 안전선). "
        "sub-module 직접 patch 권고:\n"
        + "\n".join(violations)
    )
