"""사이클 136 (2026-06-15) — AST 가드 49 파일 DRY 헬퍼 모듈 격리 가드.

사용자 결정 영속:
- Q1=A 사이클 135 commit `aeb63a7` push + CI 영속
- Q2=B 사이클 136 = 카드 #25 AST 가드 49 파일 DRY (LOW, -1,500L) 발주
- Q3=A 사이클 135 commit/push + CI 직후 즉시 사이클 136 발주

배경 (사이클 130 권고 카드 #25 영속):
- `tests/unit/ast/` 49 파일 누적 (사이클 84/124/127/129/131/135 화이트리스트 다수)
- 48 파일 read 패턴 사용 / 34 파일 ast.parse 사용
- 8 파일 헬퍼 함수 직접 정의 (`_has_function_def` / `_count_calls_to` / `_module_source` 등)
- 추정 감소 라인 -1,500L (점진 마이그레이션 5~10 파일/사이클)

영속 의무 매트릭스 영구 영속:
- 사이클 38 명문화 (테스트 영역 한정)
- 사이클 67 4 sub-module + facade 분해 패턴 답습
- 사이클 79 G-AST2 / 81 G-AST1 (영향 0)
- 사이클 84/124/127/129/131/135 화이트리스트 영속 (행위 보존)
- 122/126/127/128/129/131/132/133/134/135 영속 (영향 0)

행위 보존 의무 (refactor 가정):
- 49 AST 가드 회귀 테스트 통과 영속
- 헬퍼 모듈 영역 = 테스트 디렉토리 내부 (production 영향 0)
- 매매 안전성 무영향 (테스트 영역 한정)

점진 마이그레이션 전략:
- 사이클 136 (본 사이클): 헬퍼 모듈 신규 + 8 직접 헬퍼 정의 파일 마이그레이션 (≥ 5 파일 영속)
- 사이클 137+: 후속 분할 (10 파일/사이클 추정)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


# =============================================================================
# G-136-A — 공통 헬퍼 모듈 영속 영구 영속
# =============================================================================


class TestAstHelperModulePersistence:
    """AST 공통 헬퍼 모듈 `_ast_helpers.py` 또는 동등 영속 영구 영속."""

    def test_g_136_a1_helper_module_exists(self):
        """G-136-A1 — 공통 헬퍼 모듈 영속.

        후보 경로: `tests/unit/ast/_ast_helpers.py` 또는 `tests/unit/ast/ast_helpers.py`.
        """
        candidates = [
            Path("tests/unit/ast/_ast_helpers.py"),
            Path("tests/unit/ast/ast_helpers.py"),
            Path("tests/unit/ast/_helpers.py"),
        ]
        existing = [p for p in candidates if p.exists()]
        assert len(existing) >= 1, (
            f"AST 공통 헬퍼 모듈 영속 부재 — 후보: {[str(p) for p in candidates]}. "
            "사이클 136 카드 #25 영속 의무."
        )

    def test_g_136_a2_core_helpers_exported(self):
        """G-136-A2 — 핵심 헬퍼 함수 영속.

        시그너처 후보:
        - `read_module_source(module_path: Path | str) -> str` — UTF-8 read
        - `has_function_def(source: str, name: str) -> bool` — 함수 정의 OR 모듈 export 영역
        - `count_function_calls(source: str, name: str) -> int` — 함수 호출 빈도
        - `find_function_def(source: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None`
        """
        try:
            from tests.unit.ast import _ast_helpers as helpers
        except ImportError:
            try:
                from tests.unit.ast import ast_helpers as helpers
            except ImportError:
                pytest.fail("AST 공통 헬퍼 모듈 import 부재 — 사이클 136 카드 #25 영속 의무.")

        # 핵심 헬퍼 4 함수 영속 의무 영구 영속
        for func_name in (
            "read_module_source",
            "has_function_def",
            "count_function_calls",
            "find_function_def",
        ):
            assert hasattr(helpers, func_name), (
                f"공통 헬퍼 `{func_name}` 영속 부재 — 사이클 136 카드 #25 영속 의무"
            )
            assert callable(getattr(helpers, func_name)), (
                f"`{func_name}` callable 영속 의무"
            )


# =============================================================================
# G-136-B — 헬퍼 동작 영속 (read + has_function_def + count_function_calls + find)
# =============================================================================


class TestHelperBehavior:
    """헬퍼 동작 영속 영구 영속 (사이클 89 G-AST1 의미 전환 패턴 답습)."""

    def test_g_136_b1_read_module_source_utf8(self):
        """G-136-B1 — `read_module_source` UTF-8 영역 영구 영속 정합."""
        try:
            from tests.unit.ast._ast_helpers import read_module_source
        except ImportError:
            try:
                from tests.unit.ast.ast_helpers import read_module_source
            except ImportError:
                pytest.skip("Red 단계 — Green 후 영속 의무")

        # 자기 자신 read 영역 영구 영속 (한글 영역 영구 영속 포함)
        self_path = Path("tests/unit/ast/test_cycle136_ast_helpers.py")
        source = read_module_source(self_path)
        assert isinstance(source, str)
        assert "사이클 136" in source

    def test_g_136_b2_has_function_def_handles_module_export(self):
        """G-136-B2 — `has_function_def` 영역 영구 영속 = 함수 정의 OR 모듈 export 영역 영구 영속 흡수.

        사이클 133 의미 전환 패턴 영속 답습 (사이클 89 G-AST1 `_has_function_def`).
        """
        try:
            from tests.unit.ast._ast_helpers import has_function_def
        except ImportError:
            try:
                from tests.unit.ast.ast_helpers import has_function_def
            except ImportError:
                pytest.skip("Red 단계 — Green 후 영속 의무")

        # 패턴 1: def 영역 영구 영속
        src1 = """
def my_function():
    pass
"""
        assert has_function_def(src1, "my_function") is True

        # 패턴 2: 모듈 export tuple unpacking 영역 영구 영속 (사이클 133 답습)
        src2 = """
(record_fn, flush_fn, _collector) = make_collector()
"""
        assert has_function_def(src2, "record_fn") is True
        assert has_function_def(src2, "flush_fn") is True

        # 패턴 3: 단일 모듈 export 영역 영구 영속
        src3 = """
my_var = some_factory()
"""
        assert has_function_def(src3, "my_var") is True

        # 패턴 4: 미존재 영역 영구 영속
        assert has_function_def(src1, "non_existent") is False

    def test_g_136_b3_count_function_calls(self):
        """G-136-B3 — `count_function_calls` 영역 영구 영속 (단순 호출 + 속성 호출 매칭)."""
        try:
            from tests.unit.ast._ast_helpers import count_function_calls
        except ImportError:
            try:
                from tests.unit.ast.ast_helpers import count_function_calls
            except ImportError:
                pytest.skip("Red 단계 — Green 후 영속 의무")

        src = """
foo()
foo(1, 2)
obj.foo()
bar.foo(x=1)
baz()
"""
        assert count_function_calls(src, "foo") == 4
        assert count_function_calls(src, "bar") == 0
        assert count_function_calls(src, "baz") == 1

    def test_g_136_b4_find_function_def_returns_node(self):
        """G-136-B4 — `find_function_def` 영역 영구 영속 (FunctionDef/AsyncFunctionDef 반환)."""
        try:
            from tests.unit.ast._ast_helpers import find_function_def
        except ImportError:
            try:
                from tests.unit.ast.ast_helpers import find_function_def
            except ImportError:
                pytest.skip("Red 단계 — Green 후 영속 의무")

        src = """
def sync_func():
    pass

async def async_func():
    pass
"""
        sync_node = find_function_def(src, "sync_func")
        assert sync_node is not None
        assert isinstance(sync_node, ast.FunctionDef)

        async_node = find_function_def(src, "async_func")
        assert async_node is not None
        assert isinstance(async_node, ast.AsyncFunctionDef)

        none_node = find_function_def(src, "missing")
        assert none_node is None


# =============================================================================
# G-136-C — 마이그레이션 영역 영구 영속 (≥ 5 파일 영속)
# =============================================================================


class TestMigratedFilesPersistence:
    """사이클 136 본 사이클 마이그레이션 영역 영구 영속 (≥ 5 파일 영속)."""

    def test_g_136_c1_migrated_files_use_helpers(self):
        """G-136-C1 — 마이그레이션 영역 영구 영속 ≥ 5 파일 영역 영구 영속 헬퍼 import 영속.

        사이클 136 본 사이클 = 헬퍼 모듈 신규 + 점진 마이그레이션 ≥ 5 파일.
        사이클 137+ = 후속 분할 (10 파일/사이클 추정).
        """
        # 마이그레이션 대상 후보 파일 영역 영구 영속 = 헬퍼 함수 직접 정의 보유 파일 8개
        candidate_files = [
            "test_cycle78_ast_flush_required.py",
            "test_cycle89_ast_flush_required.py",
            "test_cycle101_ast_flush_required.py",
            "test_cycle102_ast_flush_call_sites.py",
            "test_cycle110_ast_no_deprecated_imports.py",
            "test_cycle127_ast_progress_hooks.py",
            "test_cycle129_ast_task_key_master_persistence.py",
            "test_cycle93_ast_chain_required.py",
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

        assert migrated_count >= 5, (
            f"마이그레이션 영역 영구 영속 ≥ 5 파일 영역 영구 영속 의무 위반 — got {migrated_count}. "
            "사이클 136 카드 #25 본 사이클 점진 마이그레이션 영속 의무."
        )


# =============================================================================
# G-136-D — 회귀 가드 통과 영속 (행위 보존 영역 영구 영속)
# =============================================================================


class TestRegressionGuardsPersistence:
    """마이그레이션 영역 영구 영속 후 기존 AST 가드 영역 영구 영속 회귀 통과 영속 의무."""

    def test_g_136_d1_helper_module_compact(self):
        """G-136-D1 — 헬퍼 모듈 compact 영속 (사이클 137 의미 전환 ≤ 250L 영속).

        사이클 136 Red 시점 = ≤ 200L (5 헬퍼) / 사이클 137 보강 후 = ≤ 250L (7 헬퍼).
        사이클 66 K-2 의미 전환 패턴 답습 — 헬퍼 추가 영역 영구 영속 흡수.
        """
        candidates = [
            Path("tests/unit/ast/_ast_helpers.py"),
            Path("tests/unit/ast/ast_helpers.py"),
        ]
        helper_path = None
        for p in candidates:
            if p.exists():
                helper_path = p
                break
        if helper_path is None:
            pytest.skip("Red 단계 — Green 후 영속 의무")

        line_count = len(helper_path.read_text(encoding="utf-8").splitlines())
        # 사이클 137 의미 전환 영속 — 헬퍼 모듈 보강 (find_constant_value + count_string_occurrences)
        assert line_count <= 250, (
            f"헬퍼 모듈 compact 영속 위반 — got {line_count}L, target ≤ 250L "
            "(사이클 137 보강 후, 사이클 67 패턴 답습)."
        )
