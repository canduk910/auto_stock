"""사이클 83 G-AST2 — AST 영구 가드: eager refresh 신규 코드 영역에
`tradable_boards` keyword 참조 0건 영구 차단.

사이클 38 명문화 영속 가드 — `tradable_boards` 는 매수 진입 전용.
eager refresh 영역 (`subscribe_filtered_stocks` 진입점 hook + 백그라운드 task)
은 stock_master 캐시 갱신만 담당 → 매도/익일청산/손절 영역과 무관 →
`tradable_boards` 참조 시 사이클 38 명문화 위반 silent 결함 위험.

Red 단계 (사이클 83):
- 신규 코드 영역 (스캐너 `_scan_pool_eager_refresh_*` / `_collect_scan_pool_tickers_for_eager_refresh`
  / 스케줄러 `_scan_pool_eager_refresh_loop` / `_scan_pool_eager_refresh_task`) 미존재 시
  G-AST2 사전조건 단계에서 fail.

Green 단계 (사이클 84):
- backend-dev 신규 코드 영역 도입 시 `tradable_boards` keyword 참조 0건 검증 → PASS.

검증 규칙:
- `src/engine/scanner.py` + `src/engine/scheduler.py` 에서 eager refresh 관련
  함수/메서드 정의 영역의 AST unparse 본문 내에 `tradable_boards` 문자열 0건

영속 의무:
- 사이클 38 명문화 영속 (`tradable_boards` 매수 진입 전용, 매도/익일청산/손절 무관)
- 사이클 32 R4 universe_guard 영속 (보유/익일청산 절대 보호)
- 매매 안전성 영향 0 (신규 코드 영역 = stock_master 캐시 갱신 단독)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import read_module_source

pytestmark = pytest.mark.unit


_SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
_SCANNER_PY = _SRC_ROOT / "engine" / "scanner.py"
_SCHEDULER_PY = _SRC_ROOT / "engine" / "scheduler.py"

# 사이클 83 신규 코드 영역 식별자 (Q1=B + Q2=C 명명 규칙 답습)
# backend-dev 가 다른 명명을 사용하더라도 prefix `scan_pool_eager_refresh` 유지 의무
_NEW_AREA_NAME_PATTERNS = (
    "scan_pool_eager_refresh",
    "_collect_scan_pool_tickers_for_eager_refresh",
    "_record_scan_pool_eager_refresh",
    "_flush_scan_pool_eager_refresh_collector",
)

_FORBIDDEN_KEYWORD = "tradable_boards"


def _collect_function_bodies_matching(
    py_path: Path, name_patterns: tuple[str, ...],
) -> dict[str, str]:
    """모듈 내 함수/메서드 정의 중 이름이 패턴 중 하나라도 포함되는 것의 본문 소스 반환.

    반환: dict[fully_qualified_name, ast.unparse(body)]
    """
    source = read_module_source(py_path)
    tree = ast.parse(source)
    result: dict[str, str] = {}

    def _walk_funcs(node: ast.AST, prefix: str = "") -> None:
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                _walk_funcs(sub, prefix=f"{prefix}{node.name}.")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            full_name = f"{prefix}{node.name}"
            if any(p in node.name for p in name_patterns):
                # 함수 본문 모두 unparse
                body_src = "\n".join(ast.unparse(stmt) for stmt in node.body)
                result[full_name] = body_src
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    _walk_funcs(sub, prefix=f"{prefix}{node.name}.")
        elif isinstance(node, ast.Module):
            for sub in node.body:
                _walk_funcs(sub, prefix=prefix)

    _walk_funcs(tree)
    return result


# ===========================================================================
# G-AST2: eager refresh 신규 코드 영역에 `tradable_boards` 참조 0건
# ===========================================================================
def test_g_ast2_eager_refresh_area_no_tradable_boards_reference():
    """G-AST2: eager refresh 신규 코드 영역 (`scan_pool_eager_refresh` 관련 함수/메서드)
    의 본문에 `tradable_boards` keyword 참조 0건 (사이클 38 명문화 영속).

    검증 매트릭스:
    - scanner.py 에서 함수명에 `scan_pool_eager_refresh` 포함 함수 본문 unparse
    - scheduler.py 에서 함수명에 `scan_pool_eager_refresh` 포함 메서드 본문 unparse
    - 양쪽 모두 `tradable_boards` 문자열 0건

    Red 상태 (사이클 83):
    - 신규 코드 영역 0건 → 사전조건 단계에서 FAIL (Red 의무)

    Green (사이클 84 backend-dev):
    - eager refresh 신규 함수/메서드 도입 + `tradable_boards` 참조 0건 → PASS

    영속 의무:
    - 사이클 38 명문화: `tradable_boards` 매수 진입 전용
    - eager refresh = stock_master 캐시 갱신 (매도/익일청산/손절 무관)
    - `tradable_boards` 참조 시 사이클 38 명문화 위반 silent 결함 위험
    """
    scanner_areas = _collect_function_bodies_matching(_SCANNER_PY, _NEW_AREA_NAME_PATTERNS)
    scheduler_areas = _collect_function_bodies_matching(_SCHEDULER_PY, _NEW_AREA_NAME_PATTERNS)

    all_areas: dict[str, str] = {}
    for name, body in scanner_areas.items():
        all_areas[f"scanner.py::{name}"] = body
    for name, body in scheduler_areas.items():
        all_areas[f"scheduler.py::{name}"] = body

    # 사전조건: 신규 코드 영역 도입 의무 (Red 상태 시점 0건 → FAIL 정상)
    assert all_areas, (
        f"\n사이클 83 G-AST2 사전조건 위반 — eager refresh 신규 코드 영역 0건 발견:\n\n"
        f"  검색 패턴: {_NEW_AREA_NAME_PATTERNS}\n"
        f"  대상 파일: scanner.py + scheduler.py\n\n"
        f"  Red 상태 (사이클 83) = 신규 코드 미도입 → 본 사전조건 FAIL 정상.\n"
        f"  Green (사이클 84) = backend-dev 가 신규 함수/메서드 도입 시 본 사전조건\n"
        f"  자동 충족 + 본 가드 본체 (tradable_boards 0 참조) 검증 → PASS.\n\n"
        f"  사이클 83 카드 #82-A 옵션 1 = Q1=B `subscribe_filtered_stocks` 진입점\n"
        f"  hook + Q2=C 백그라운드 task → 신규 헬퍼 도입 의무."
    )

    # 본 가드: 신규 영역 본문 내 `tradable_boards` 0 참조
    violations: list[str] = []
    for area_name, body in all_areas.items():
        count = body.count(_FORBIDDEN_KEYWORD)
        if count > 0:
            violations.append(
                f"  - {area_name}: `{_FORBIDDEN_KEYWORD}` 참조 {count} 건 (= 0 의무)"
            )

    assert not violations, (
        f"\n사이클 83 G-AST2 위반 — eager refresh 신규 코드 영역에 "
        f"`{_FORBIDDEN_KEYWORD}` keyword 참조 발견:\n\n"
        + "\n".join(violations)
        + "\n\n  사이클 38 명문화 (2026-05-22): `tradable_boards` 는 매수 진입 전용.\n"
        f"  eager refresh = stock_master 캐시 갱신 (매도/익일청산/손절 무관).\n"
        f"  → `tradable_boards` 참조 시 사이클 38 명문화 위반 silent 결함 위험.\n\n"
        f"  시정: eager refresh 영역에서 `tradable_boards` 참조 전수 제거.\n"
        f"  매수 진입 후보 풀 (보유/익일청산 절대 보호) 만 영향 → session_tracker\n"
        f"  연동 불필요."
    )
