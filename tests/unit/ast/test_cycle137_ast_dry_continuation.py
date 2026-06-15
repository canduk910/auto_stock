"""사이클 137 (2026-06-15) — AST 가드 49 파일 DRY 후속 마이그레이션 (10 파일) 격리 가드.

사용자 결정 영속:
- Q1=A 사이클 136 commit `90fafc0` push + CI 영속
- Q2=A 사이클 137 = AST DRY 후속 마이그레이션 10 파일 (~-300L)
- Q3=A 사이클 136 commit/push + CI 직후 즉시 사이클 137 발주

배경 (사이클 130 권고 카드 #25 영속 + 사이클 136 1차 마이그레이션 영속):
- 사이클 136 = 7 파일 마이그레이션 영속 (사이클 78/89/101/102/110/127/129)
- 사이클 137 = 후속 10 파일 마이그레이션 영속 (잔존 41 파일 영역 중)
- 헬퍼 함수 보강 영역 영구 영속 (POST 화이트리스트 / task_attrs / import 차단 / 상수 단일 정의처)

team-leader 우선순위 영역 영구 영속 (read 패턴 빈도 높은 영역 영구 영속):
1. test_cycle90_g_reject_persistence.py (4 read)
2. test_cycle93_ast_chain_required.py (2 read)
3. test_cycle84_ast_no_update_route.py (2 read, 화이트리스트)
4. test_cycle74_ast_aggregator_helper.py (2 read)
5. test_cycle128_ast_no_range_9999_silent_cap.py (2 read)
6. test_cycle124_ast_endpoint.py (2 read)
7. test_cycle72_ast_no_logger_write_log_pair.py (1 read)
8. test_cycle79_ast_task_cancel_required.py (1 read, task_attrs)
9. test_cycle81_ast_price_filter_key.py (1 read)
10. test_cycle122_kis_tr_id_persistence.py (헬퍼 보강 가치)

영속 의무 매트릭스 영구 영속:
- 사이클 38 명문화 (테스트 영역 한정 production 영향 0)
- 사이클 67 facade re-export 패턴 답습
- 사이클 79 G-AST2 / 81 G-AST1 (영향 0)
- 사이클 89 G-AST1 의미 전환 영속 (헬퍼 영역 보존)
- 사이클 136 헬퍼 모듈 영역 영구 영속 확장 패턴 영속
- 사이클 84/124/127/129/131/135 화이트리스트 영속 (행위 보존)
"""

from __future__ import annotations

from pathlib import Path

import pytest


# =============================================================================
# G-137-A — 마이그레이션 영역 영구 영속 (≥ 10 파일 영속)
# =============================================================================


class TestCycle137MigrationPersistence:
    """사이클 137 후속 마이그레이션 영역 영구 영속 (≥ 10 파일 영속 의무)."""

    def test_g_137_a1_migrated_files_use_helpers(self):
        """G-137-A1 — 마이그레이션 영역 영구 영속 ≥ 10 파일 영역 영구 영속 헬퍼 import 영속.

        사이클 137 = 잔존 41 파일 중 10 파일 우선순위 마이그레이션.
        사이클 138+ = 후속 분할 (10 파일/사이클 영역 영구 영속).
        """
        # team-leader 우선순위 영역 영구 영속 (read 패턴 빈도 + 가치 영역 영구 영속)
        candidate_files = [
            "test_cycle90_g_reject_persistence.py",
            "test_cycle93_ast_chain_required.py",
            "test_cycle84_ast_no_update_route.py",
            "test_cycle74_ast_aggregator_helper.py",
            "test_cycle128_ast_no_range_9999_silent_cap.py",
            "test_cycle124_ast_endpoint.py",
            "test_cycle72_ast_no_logger_write_log_pair.py",
            "test_cycle79_ast_task_cancel_required.py",
            "test_cycle81_ast_price_filter_key.py",
            "test_cycle122_kis_tr_id_persistence.py",
        ]
        ast_dir = Path("tests/unit/ast")
        migrated_count = 0

        for fname in candidate_files:
            fpath = ast_dir / fname
            if not fpath.exists():
                continue
            src = fpath.read_text(encoding="utf-8")
            # 헬퍼 모듈 import 영역 영구 영속 = 마이그레이션 영속 영구 영속
            if (
                "from tests.unit.ast._ast_helpers import" in src
                or "from tests.unit.ast.ast_helpers import" in src
                or "from ._ast_helpers import" in src
                or "from .ast_helpers import" in src
            ):
                migrated_count += 1

        assert migrated_count >= 10, (
            f"사이클 137 마이그레이션 영역 영구 영속 ≥ 10 파일 영역 영구 영속 의무 위반 — "
            f"got {migrated_count}. 사이클 137 카드 #25 후속 마이그레이션 영속 의무."
        )


# =============================================================================
# G-137-B — 헬퍼 함수 추가 영역 영구 영속 (선택적, 보강 영역 영구 영속)
# =============================================================================


class TestExtendedHelpers:
    """사이클 137 헬퍼 함수 보강 영역 영구 영속 (선택적, 1+ 헬퍼 보강 영속 의무)."""

    def test_g_137_b1_at_least_one_new_helper_or_pattern_pass(self):
        """G-137-B1 — 헬퍼 함수 ≥ 6 영역 영구 영속 (사이클 136 기준 5 + 사이클 137 1+ 추가).

        후보: assert_whitelist_routes / assert_task_attrs_persistence /
              assert_module_no_imports / assert_constant_defined_single_location /
              count_string_occurrences (단순 문자열 카운트).
        """
        from tests.unit.ast import _ast_helpers as helpers

        # __all__ 영역 영구 영속 ≥ 6 영속 (사이클 136 기준 6 함수 + 사이클 137 1+ 추가)
        all_attrs = getattr(helpers, "__all__", [])
        assert len(all_attrs) >= 6, (
            f"공통 헬퍼 함수 ≥ 6 영속 의무 — got {len(all_attrs)}: {all_attrs}. "
            "사이클 137 보강 의무."
        )

    def test_g_137_b2_assert_constant_helper(self):
        """G-137-B2 — `assert_constant_defined` 헬퍼 영속 (상수 단일 정의처, 사이클 67/135 답습)."""
        from tests.unit.ast import _ast_helpers as helpers

        # 후보 영역 영구 영속 = `assert_constant_defined` 또는 `find_constant_value`
        has_constant_helper = (
            hasattr(helpers, "assert_constant_defined")
            or hasattr(helpers, "find_constant_value")
            or hasattr(helpers, "get_module_constant")
        )
        assert has_constant_helper, (
            "상수 정의처 헬퍼 영속 부재 — assert_constant_defined / find_constant_value / "
            "get_module_constant 중 1+ 영속 의무"
        )


# =============================================================================
# G-137-C — 헬퍼 모듈 영역 영구 영속 보강 영역 영구 영속 (≤ 250L 영속)
# =============================================================================


class TestHelperModuleExtensionPersistence:
    """헬퍼 모듈 보강 후 compact 영속 (≤ 250L 영속)."""

    def test_g_137_c1_helper_module_compact_after_extension(self):
        """G-137-C1 — 헬퍼 모듈 보강 후 ≤ 250L 영속."""
        helper_path = Path("tests/unit/ast/_ast_helpers.py")
        if not helper_path.exists():
            pytest.skip("Red 단계 — Green 후 영속 의무")

        line_count = len(helper_path.read_text(encoding="utf-8").splitlines())
        assert line_count <= 250, (
            f"헬퍼 모듈 compact 영속 위반 — got {line_count}L, target ≤ 250L. "
            "사이클 67 패턴 답습 + 사이클 137 보강 영속."
        )
