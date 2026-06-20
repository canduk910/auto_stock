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
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.unit.ast._ast_helpers import read_module_source

REPO_ROOT = Path(__file__).resolve().parents[3]
SCANNER_PY = REPO_ROOT / "src" / "engine" / "scanner.py"


def test_h1_no_dead_func_market_cap_master_to_millions():
    """HIGH-1.1: `market_cap_master_to_millions` 모듈 함수 영구 부재.

    사이클 167 폐기 의무 — scanner.py 영역 모듈 def (들여쓰기 0) 영구 부재.
    """
    assert SCANNER_PY.exists(), f"scanner.py 영역 부재 ({SCANNER_PY})"
    src = read_module_source(SCANNER_PY)

    pattern = re.compile(r"^def market_cap_master_to_millions\b", re.MULTILINE)
    matches = pattern.findall(src)

    assert len(matches) == 0, (
        f"[dead code 폐기 실패] `def market_cap_master_to_millions(` 영구 부재 의무 "
        f"(실제 매칭 {len(matches)}건). 사이클 167 = callsite 0건 폐기."
    )


def test_h1_no_dead_func_validate_market_cap_consistency():
    """HIGH-1.2: `validate_market_cap_consistency` 모듈 함수 영구 부재."""
    src = read_module_source(SCANNER_PY)

    pattern = re.compile(r"^def validate_market_cap_consistency\b", re.MULTILINE)
    matches = pattern.findall(src)

    assert len(matches) == 0, (
        f"[dead code 폐기 실패] `def validate_market_cap_consistency(` 영구 부재 의무 "
        f"(실제 매칭 {len(matches)}건). 사이클 167 = production 호출 0건 폐기."
    )


def test_h1_no_dead_func_get_market_cap_millions():
    """HIGH-1.3: `get_market_cap_millions` 모듈 함수 영구 부재."""
    src = read_module_source(SCANNER_PY)

    pattern = re.compile(r"^def get_market_cap_millions\b", re.MULTILINE)
    matches = pattern.findall(src)

    assert len(matches) == 0, (
        f"[dead code 폐기 실패] `def get_market_cap_millions(` 영구 부재 의무 "
        f"(실제 매칭 {len(matches)}건). 사이클 167 = production 호출 0건 폐기."
    )


def test_h1_no_callsite_for_dead_funcs():
    """HIGH-1.4: 3 함수 정의/호출 패턴 `name(` 잔존 0건.

    폐기 기록 주석의 함수명 언급(`#` 줄)은 허용 — 실제 코드 토큰 `name(` 만 차단.
    """
    src = read_module_source(SCANNER_PY)
    # 주석 줄 제외 (폐기 기록 주석 허용)
    code_lines = [
        ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
    ]
    code_src = "\n".join(code_lines)

    for name in (
        "market_cap_master_to_millions",
        "validate_market_cap_consistency",
        "get_market_cap_millions",
    ):
        # 호출/정의 패턴 `name(` 잔존 0건 (주석 외 코드 영역)
        assert f"{name}(" not in code_src, (
            f"[dead code 폐기 실패] {name!r} 호출/정의 패턴 잔존 (주석 외 코드). "
            f"사이클 167 = 3 함수 폐쇄 그래프 일괄 폐기 의무."
        )


def test_h2_persistence_layer_unchanged():
    """HIGH-2 (보강): 보존 영역 변경 0 — 실제 시총 필터/차단 hook 영속.

    사이클 167 폐기는 dead code 한정. 다음 영역은 변경 0 의무:
    - `_is_master_blocked_for_entry` (1단계 차단 13건 hook, 사이클 129/155)
    - `apply_master_block_filter` (5 전략 공통 hook, 사이클 157)
    - `MIN_MARKET_CAP` 상수 (사이클 89)
    """
    src = read_module_source(SCANNER_PY)

    for area in (
        "def _is_master_blocked_for_entry",
        "async def apply_master_block_filter",
        "MIN_MARKET_CAP",
    ):
        assert area in src, (
            f"[보존 영역 변경 실패] {area!r} = scanner.py 영속 의무 "
            f"(사이클 167 폐기는 dead code 3 함수 한정)."
        )
