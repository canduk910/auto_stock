"""사이클 138 (2026-06-15) — AST 가드 49 파일 DRY 3차 마이그레이션 (10 파일) 격리 가드.

사용자 결정 영속:
- Q1=A 사이클 137 commit `afaa40c` push + CI success 4분 16초 영속
- Q2=A 사이클 138 = AST DRY 3차 마이그레이션 10 파일 (~-300L)
- Q3=A 사이클 137 CI success 직후 즉시 사이클 138 발주

배경 (사이클 130 권고 카드 #25 영속 + 사이클 136/137 1·2차 마이그레이션 영속):
- 사이클 136 = 7 파일 마이그레이션 (사이클 78/89/101/102/110/127/129)
- 사이클 137 = 10 파일 마이그레이션 (사이클 90/93/84/74/128/124/72/79/81/122)
- 사이클 138 = 10 파일 3차 마이그레이션 (잔존 ~22 파일 중 read 빈도 상위)
- 사이클 139 = 잔존 ~12 파일 마무리 (카드 #25 종결 예정)

team-leader 우선순위 영역 (read 패턴 빈도 + 효과 영역):
1. test_cycle92_g_reject_persistence.py (9 read)
2. test_external_llm_reject_patterns.py (7 read)
3. test_cycle112_security_ast.py (5 read / 3 parse)
4. test_cycle89_g_reject_persistence.py (4 read)
5. test_cycle103_ast_no_dead_strategy_funcs.py (4 read)
6. test_cycle115_krx_endpoint_urls.py (4 read)
7. test_cycle76_ast_api_retry_helper.py (3 read / 1 parse)
8. test_cycle115_krx_no_plaintext_key.py (3 read / 2 parse)
9. test_cycle103_ast_momentum_log_format.py (3 read)
10. test_cycle98_ast_chk_citation_required.py (1 read / 1 parse)

영속 의무 매트릭스:
- 사이클 38 명문화 (테스트 영역 한정 production 영향 0)
- 사이클 67 facade re-export 패턴 답습
- 사이클 79 G-AST2 / 81 G-AST1 (영향 0)
- 사이클 89 G-AST1 의미 전환 영속 (헬퍼 영역 보존)
- 사이클 136/137 헬퍼 모듈 영역 영속 확장 패턴 영속
- 사이클 84/124/127/129/131/135 화이트리스트 영속 (행위 보존)
"""

from __future__ import annotations

from pathlib import Path

import pytest


# =============================================================================
# G-138-A — 3차 마이그레이션 영역 영속 (≥ 10 파일 영속)
# =============================================================================


class TestCycle138MigrationPersistence:
    """사이클 138 3차 마이그레이션 영역 영속 (≥ 10 파일 영속 의무)."""

    def test_g_138_a1_migrated_files_use_helpers(self):
        """G-138-A1 — 3차 마이그레이션 영역 ≥ 10 파일 영역 헬퍼 import 영속.

        잔존 22 파일 중 read 빈도 상위 10 파일 마이그레이션.
        사이클 139 = 잔존 12 파일 마무리 (카드 #25 종결 예정).
        """
        candidate_files = [
            "test_cycle92_g_reject_persistence.py",
            "test_external_llm_reject_patterns.py",
            "test_cycle112_security_ast.py",
            "test_cycle89_g_reject_persistence.py",
            "test_cycle103_ast_no_dead_strategy_funcs.py",
            "test_cycle115_krx_endpoint_urls.py",
            "test_cycle76_ast_api_retry_helper.py",
            "test_cycle115_krx_no_plaintext_key.py",
            "test_cycle103_ast_momentum_log_format.py",
            "test_cycle98_ast_chk_citation_required.py",
        ]
        ast_dir = Path("tests/unit/ast")
        migrated_count = 0

        for fname in candidate_files:
            fpath = ast_dir / fname
            if not fpath.exists():
                continue
            src = fpath.read_text(encoding="utf-8")
            if (
                "from tests.unit.ast._ast_helpers import" in src
                or "from tests.unit.ast.ast_helpers import" in src
                or "from ._ast_helpers import" in src
                or "from .ast_helpers import" in src
            ):
                migrated_count += 1

        assert migrated_count >= 10, (
            f"사이클 138 3차 마이그레이션 ≥ 10 파일 의무 위반 — "
            f"got {migrated_count}. 사이클 138 카드 #25 3차 마이그레이션 영속 의무."
        )

    def test_g_138_a2_cumulative_migration_count(self):
        """G-138-A2 — 누적 마이그레이션 영역 ≥ 27 파일 (사이클 136 7 + 137 10 + 138 10)."""
        ast_dir = Path("tests/unit/ast")
        total_migrated = 0
        for fpath in ast_dir.glob("test_*.py"):
            src = fpath.read_text(encoding="utf-8")
            if (
                "from tests.unit.ast._ast_helpers import" in src
                or "from ._ast_helpers import" in src
            ):
                total_migrated += 1

        assert total_migrated >= 27, (
            f"누적 마이그레이션 ≥ 27 파일 영속 의무 위반 — got {total_migrated}. "
            "사이클 136 (7) + 137 (10) + 138 (10) 누적 영속."
        )


# =============================================================================
# G-138-B — 헬퍼 모듈 영역 compact 영속 (≤ 250L 영속)
# =============================================================================


class TestHelperModuleCompactPersistence:
    """헬퍼 모듈 영역 compact 영속 (사이클 137 한도 답습)."""

    def test_g_138_b1_helper_module_compact(self):
        """G-138-B1 — 헬퍼 모듈 ≤ 250L 영속 (사이클 137 한도 답습)."""
        helper_path = Path("tests/unit/ast/_ast_helpers.py")
        if not helper_path.exists():
            pytest.skip("헬퍼 모듈 미존재")

        line_count = len(helper_path.read_text(encoding="utf-8").splitlines())
        assert line_count <= 250, (
            f"헬퍼 모듈 compact 영속 위반 — got {line_count}L, target ≤ 250L. "
            "사이클 67 패턴 답습 + 사이클 138 영속."
        )

    def test_g_138_b2_helper_all_exports_persistence(self):
        """G-138-B2 — `__all__` ≥ 8 함수 영속 (사이클 137 baseline 답습)."""
        from tests.unit.ast import _ast_helpers as helpers

        all_attrs = getattr(helpers, "__all__", [])
        assert len(all_attrs) >= 8, (
            f"공통 헬퍼 함수 ≥ 8 영속 의무 — got {len(all_attrs)}: {all_attrs}. "
            "사이클 137 baseline 답습."
        )
