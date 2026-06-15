"""사이클 139 (2026-06-15) — AST 가드 49 파일 DRY 4차 마이그레이션 + 카드 #25 완전 종결.

사용자 결정 영속:
- Q1=A 사이클 138 commit `ec2061d` push + CI success 4분 31초 + EC2 Deploy success 20s 영속
- Q2=A 사이클 139 = AST DRY 4차 마이그레이션 잔존 ~12 파일 (실측 23 파일)
- Q3=A 즉시 발주

배경 (사이클 130 권고 카드 #25 영속 + 사이클 136/137/138 1·2·3차 마이그레이션 영속):
- 사이클 136 = 7 파일 마이그레이션
- 사이클 137 = 10 파일 마이그레이션
- 사이클 138 = 10 파일 마이그레이션
- 사이클 139 = 잔존 23 파일 전수 마이그레이션 (카드 #25 완전 종결)

team-leader 영속 (잔존 23 파일 영역 영구 영속):
1. test_cycle83_ast_task_cancel_required.py (206L)
2. test_cycle99_default_arg_persistence.py (168L)
3. test_cycle102_ast_callback_exception.py (168L)
4. test_cycle91_ast_pagination_pattern.py (165L)
5. test_cycle89_ast_task_cancel_required.py (160L)
6. test_cycle94_ast_no_industry_code.py (149L)
7. test_cycle83_ast_tradable_boards_no_reference.py (147L)
8. test_cycle97_ast_no_volume_rank.py (144L)
9. test_cycle96_ast_no_zero_market_code.py (131L)
10. test_cycle107_ast_inquire_price_tr_id.py (124L)
11. test_cycle101_ast_task_cancel.py (115L)
12. test_cycle98_ast_rank_sort_cls_code.py (115L)
13. test_cycle100_ast_count_eager_refresh_three_prefix.py (113L)
14. test_cycle73_ast_realtime_no_logger_write_log_pair.py (112L)
15. test_cycle100_docstring_kis_chk_citation.py (108L)
16. test_cycle101_ast_chk_citation.py (107L)
17. test_cycle73_ast_swing_rest_poll_no_logger_write_log_pair.py (100L)
18. test_cycle101_fluctuation_purged.py (89L)
19. test_cycle101_universe_eager_refresh_purged.py (85L)
20. test_cycle108_ast_no_kis_volume_rank.py (80L)
21. test_cycle126_ast_basics_refresh_persistence.py (62L)
22. test_cycle129_ast_master_raw_separation.py (56L)

예외 (read 패턴 부재 영역):
- test_cycle99_kis_limit_documentation.py (143L, read 0 / parse 0 = 마이그레이션 대상 외)

영속 의무 매트릭스 영구 영속:
- 사이클 38 명문화 (테스트 영역 한정 production 영향 0)
- 사이클 67 facade re-export 패턴 답습
- 사이클 79 G-AST2 / 81 G-AST1 (영향 0)
- 사이클 89 G-AST1 의미 전환 영속 (헬퍼 영역 보존)
- 사이클 136/137/138 헬퍼 모듈 영속 확장 패턴 영속
- 사이클 84/124/127/129/131/135 화이트리스트 영속 (행위 보존)
"""

from __future__ import annotations

from pathlib import Path

import pytest


# =============================================================================
# G-139-A — 잔존 22 파일 전수 마이그레이션 영역 (카드 #25 완전 종결)
# =============================================================================


class TestCycle139TerminationMigration:
    """사이클 139 잔존 22 파일 전수 마이그레이션 영역 (카드 #25 완전 종결 의무)."""

    def test_g_139_a1_migrated_files_use_helpers(self):
        """G-139-A1 — 4차 마이그레이션 ≥ 22 파일 영역 헬퍼 import 영속.

        잔존 22 파일 (read 패턴 1+ 영역) 전수 마이그레이션 의무.
        test_cycle99_kis_limit_documentation.py (read 0 / parse 0) 예외.
        """
        candidate_files = [
            "test_cycle83_ast_task_cancel_required.py",
            "test_cycle99_default_arg_persistence.py",
            "test_cycle102_ast_callback_exception.py",
            "test_cycle91_ast_pagination_pattern.py",
            "test_cycle89_ast_task_cancel_required.py",
            "test_cycle94_ast_no_industry_code.py",
            "test_cycle83_ast_tradable_boards_no_reference.py",
            "test_cycle97_ast_no_volume_rank.py",
            "test_cycle96_ast_no_zero_market_code.py",
            "test_cycle107_ast_inquire_price_tr_id.py",
            "test_cycle101_ast_task_cancel.py",
            "test_cycle98_ast_rank_sort_cls_code.py",
            "test_cycle100_ast_count_eager_refresh_three_prefix.py",
            "test_cycle73_ast_realtime_no_logger_write_log_pair.py",
            "test_cycle100_docstring_kis_chk_citation.py",
            "test_cycle101_ast_chk_citation.py",
            "test_cycle73_ast_swing_rest_poll_no_logger_write_log_pair.py",
            "test_cycle101_fluctuation_purged.py",
            "test_cycle101_universe_eager_refresh_purged.py",
            "test_cycle108_ast_no_kis_volume_rank.py",
            "test_cycle126_ast_basics_refresh_persistence.py",
            "test_cycle129_ast_master_raw_separation.py",
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

        assert migrated_count >= 22, (
            f"사이클 139 4차 마이그레이션 ≥ 22 파일 의무 위반 — "
            f"got {migrated_count}. 사이클 139 카드 #25 완전 종결 영속 의무."
        )

    def test_g_139_a2_card25_termination_cumulative_count(self):
        """G-139-A2 — 카드 #25 완전 종결 영역 누적 ≥ 49 파일 영속.

        사이클 136 (7) + 137 (10) + 138 (10) + 139 (≥ 22) = ≥ 49 영속.
        카드 #25 권고 -1,500L 추정 영역 완전 종결.
        """
        ast_dir = Path("tests/unit/ast")
        total_migrated = 0
        for fpath in ast_dir.glob("test_*.py"):
            src = fpath.read_text(encoding="utf-8")
            if (
                "from tests.unit.ast._ast_helpers import" in src
                or "from ._ast_helpers import" in src
            ):
                total_migrated += 1

        assert total_migrated >= 49, (
            f"카드 #25 완전 종결 누적 ≥ 49 파일 영속 위반 — got {total_migrated}. "
            "사이클 136 (7) + 137 (10) + 138 (10) + 139 (≥ 22) = ≥ 49 영속."
        )


# =============================================================================
# G-139-B — 헬퍼 모듈 영역 compact 영속 (≤ 250L 영속)
# =============================================================================


class TestHelperModuleCompactPersistence:
    """헬퍼 모듈 영역 compact 영속 (사이클 137/138 한도 답습)."""

    def test_g_139_b1_helper_module_compact(self):
        """G-139-B1 — 헬퍼 모듈 ≤ 250L 영속."""
        helper_path = Path("tests/unit/ast/_ast_helpers.py")
        if not helper_path.exists():
            pytest.skip("헬퍼 모듈 미존재")

        line_count = len(helper_path.read_text(encoding="utf-8").splitlines())
        assert line_count <= 250, (
            f"헬퍼 모듈 compact 영속 위반 — got {line_count}L, target ≤ 250L. "
            "사이클 67 패턴 답습 + 사이클 139 영속."
        )

    def test_g_139_b2_helper_all_exports_persistence(self):
        """G-139-B2 — `__all__` ≥ 8 함수 영속."""
        from tests.unit.ast import _ast_helpers as helpers

        all_attrs = getattr(helpers, "__all__", [])
        assert len(all_attrs) >= 8, (
            f"공통 헬퍼 함수 ≥ 8 영속 의무 — got {len(all_attrs)}: {all_attrs}."
        )
