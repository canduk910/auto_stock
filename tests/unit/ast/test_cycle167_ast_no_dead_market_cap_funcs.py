"""사이클 167 — 시총 헬퍼 3개 dead code 폐기 AST 영구 가드.

명세: _workspace/red/cycle167_market_cap_dead_code.md
영속 의무: 사이클 103 dead code 폐기 패턴 100% 답습 (callsite 0건 → 폐기 + AST 가드).

배경: 사이클 166 인계 "헬퍼 명칭 통일" 진단 결과, 3 함수가 production 호출 0건
(dead code) 확인. 실제 시총 필터는 list_by_filter / list_paged_by_filter 가 직접
수행 (사이클 166 억원 정합 완료). 3 함수는 사이클 129 도입 이후 줄곧 미사용.

폐기 대상 (서로만 호출하는 폐쇄 그래프, 외부 진입점 0):
- market_cap_master_to_millions (validate / get 내부에서만 호출)
- validate_market_cap_consistency (production 호출 0)
- get_market_cap_millions (production 호출 0)

탐지 방식 (사이클 167 코드리뷰 보강 — AST 기반):
- 사이클 136 `_ast_helpers` 재사용 (has_function_def / count_function_calls).
- def / async def / 메서드 / 모듈-레벨 할당 / import 바인딩 / 호출 사이트 어느 형태든
  재도입 포착. 문자열 / docstring / 주석 언급은 무시.
- 정규식(`^def`)·부분문자열(`name(`) 방식의 결함 동시 차단:
  - false negative: 별칭 재export(`name = alias` / `from x import name`) + 공백 def(`def name (`).
  - false positive: scanner.py docstring 이 폐기 함수명을 단순 언급 시 빌드 red.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import (
    count_function_calls,
    find_constant_value,
    has_function_def,
    read_module_source,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SCANNER_PY = REPO_ROOT / "src" / "engine" / "scanner.py"

# 사이클 167 폐기 대상 — 서로만 호출하던 폐쇄 그래프 (production callsite 0건).
DEAD_FUNCS = (
    "market_cap_master_to_millions",
    "validate_market_cap_consistency",
    "get_market_cap_millions",
)

# 효율 (코드리뷰 #7): scanner.py(약 117KB) 1회 read 후 전 케이스 공유.
assert SCANNER_PY.exists(), f"scanner.py 영역 부재 ({SCANNER_PY})"
_SRC = read_module_source(SCANNER_PY)


def _name_is_reintroduced(src: str, name: str) -> bool:
    """`name` 이 모듈 네임스페이스에 (재)도입됐는지 — AST 토큰만 (문자열/주석 무시).

    포착 형태 (정규식/부분문자열이 놓치던 케이스 포함):
    - def / async def (중첩·메서드 포함), 모듈-레벨 단일/튜플 할당 → `has_function_def`
    - 호출 사이트 `name(...)` / `obj.name(...)` / `await name(...)` (공백 무관) → `count_function_calls`
    - import 바인딩 (`import name` / `from x import name` / `... as name`)
    - 어노테이션 할당 (`name: T = ...`)

    docstring / 일반 문자열 리터럴 / `#` 주석 내 단순 언급은 AST 노드가 아니므로 무시.
    """
    if has_function_def(src, name):
        return True
    if count_function_calls(src, name) > 0:
        return True
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                if bound == name:
                    return True
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == name:
                return True
    return False


@pytest.mark.parametrize("name", DEAD_FUNCS)
def test_h1_dead_func_not_reintroduced(name):
    """HIGH-1: 폐기 3 함수가 scanner.py 네임스페이스에 재도입 0건 (AST, 어느 형태든).

    사이클 167 = callsite 0건 폐기. 정규식/부분문자열이 놓치던 별칭 재export·공백 def·
    async def·메서드도 AST 로 포착 (코드리뷰 #2/#3/#5).
    """
    assert not _name_is_reintroduced(_SRC, name), (
        f"[dead code 폐기 실패] {name!r} 재도입 (def/async/할당/import/호출 어느 형태든) "
        f"— scanner.py 영구 부재 의무. 사이클 167 = 3 함수 폐쇄 그래프 일괄 폐기."
    )


def test_h2_persistence_layer_unchanged():
    """HIGH-2 (보강): 보존 영역 변경 0 — 실제 시총 필터/차단 hook 영속 (AST 검증).

    사이클 167 폐기는 dead code 한정. 다음 영역은 영속 의무:
    - `_is_master_blocked_for_entry` (1단계 차단 13건 hook, 사이클 129/155)
    - `apply_master_block_filter` (5 전략 공통 hook, 사이클 157)
    - `MIN_MARKET_CAP` 상수 (사이클 89)
    """
    assert has_function_def(_SRC, "_is_master_blocked_for_entry"), (
        "[보존 영역 변경] `_is_master_blocked_for_entry` 부재 (사이클 129/155 진입 차단 hook)."
    )
    assert has_function_def(_SRC, "apply_master_block_filter"), (
        "[보존 영역 변경] `apply_master_block_filter` 부재 (사이클 157 5 전략 공통 hook)."
    )
    assert find_constant_value(_SRC, "MIN_MARKET_CAP") is not None, (
        "[보존 영역 변경] `MIN_MARKET_CAP` 모듈-레벨 상수 부재 (사이클 89)."
    )


# ---------------------------------------------------------------------------
# 탐지기 self-test (코드리뷰 보강) — `_name_is_reintroduced` 견고성 박제.
# 정규식 `^def name`·부분문자열 `name(` 가 놓치던 형태를 합성 source 로 직접 검증.
# 이 self-test 가 green = HIGH-1 가드가 미래 재도입을 실제로 catch 함을 보장.
# ---------------------------------------------------------------------------

_NAME = "get_market_cap_millions"


@pytest.mark.parametrize(
    "snippet",
    [
        f"def {_NAME}(x):\n    return x",                       # 모듈-레벨 def
        f"async def {_NAME}(x):\n    return x",                 # async def
        f"class C:\n    def {_NAME}(self):\n        return 1",  # 메서드 (들여쓰기 def)
        f"{_NAME} = _impl",                                     # 단일 할당 별칭
        f"({_NAME}, other) = factory()",                       # 튜플 언패킹 별칭
        f"from src.engine.helpers import {_NAME}",             # import 바인딩
        f"from x import y as {_NAME}",                         # import as 별칭
        f"x = {_NAME}(a, b)",                                  # 호출 사이트
        f"x = {_NAME} (a, b)",                                 # 공백+괄호 호출 (PEP8 위반이나 valid)
        f"{_NAME}: int = 0",                                   # 어노테이션 할당
    ],
)
def test_detector_catches_reintroduction_forms(snippet):
    """탐지기 견고성 — 정규식/부분문자열이 놓치던 재도입 형태 전부 포착 (코드리뷰 #2/#3/#5)."""
    assert _name_is_reintroduced(snippet, _NAME), (
        f"탐지 누락 (false negative): {snippet!r}"
    )


@pytest.mark.parametrize(
    "snippet",
    [
        f'"""문서: 과거 {_NAME}(m, r) 호출을 list_by_filter 로 대체."""',  # docstring 언급
        f"# {_NAME}(...) 폐기 기록 주석",                                  # `#` 주석 언급
        f"x = '{_NAME}(a)'",                                              # 문자열 리터럴 언급
        "y = other_func()",                                              # 무관 코드
    ],
)
def test_detector_ignores_mentions(snippet):
    """탐지기 false positive 차단 — 문자열/docstring/주석 단순 언급은 무시 (코드리뷰 #6)."""
    assert not _name_is_reintroduced(snippet, _NAME), (
        f"오탐 (false positive): {snippet!r}"
    )
