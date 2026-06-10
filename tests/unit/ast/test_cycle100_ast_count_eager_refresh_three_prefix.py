"""사이클 100 G-UI2 — AST 영구 가드: `count_eager_refresh_today` 본체 3 prefix grep 영속 (HIGH).

명세 (`_workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md`):

**미래 silent 결함 영구 차단 패턴 (사이클 81 답습)**:
- backend-dev 가 사이클 100 시정 후 prefix 1개 silent 삭제 영역 영구 차단
- production `count_eager_refresh_today` 함수 본체 source text 영역에 3 prefix 영역 grep 모두 ≥1건 영속

3 prefix 영구 영속 (사용자 결정 Q65=C-1):
- `universe_eager_refresh` (사이클 89, 244건 7일 영속)
- `scan_pool_eager_refresh` (사이클 83, 230건 7일 영속)
- `stock_master_bulk_refresh` (사이클 95, 140건 7일 영속)

**Red 상태**: production 본체 = `scan_pool_eager_refresh` 단독 → 3 prefix 검증 시 2 영역 부재 → FAIL.

**Green (backend-dev)**: 3 prefix 영역 source 영역 등장 → PASS.

영속 의무:
- 사이클 81 silent 결함 영구 차단 패턴 답습 (`prdy_clpr` → `bfdy_clpr` AST 영구 가드)
- 사이클 98 G-DOC1 답습 (KIS 정본 인용 의무 AST 영구 가드)
- 사이클 89 G-AST1 답습 (사이클 76 task 패턴 영속)
- 매매 안전성 영역 영향 0 (DB 영역 한정)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _stock_master_module_path() -> Path:
    """stock_master.py 모듈 절대 경로."""
    import src.db.stock_master as sm_mod
    return Path(sm_mod.__file__)


def _stock_master_module_source() -> str:
    """stock_master.py source text."""
    return _stock_master_module_path().read_text(encoding="utf-8")


def _get_count_eager_refresh_today_source() -> str | None:
    """`count_eager_refresh_today` 함수 본체 source text 추출 (AST FunctionDef / AsyncFunctionDef)."""
    source = _stock_master_module_source()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "count_eager_refresh_today":
                # ast.get_source_segment 으로 함수 본체 source text 추출
                segment = ast.get_source_segment(source, node)
                return segment
    return None


REQUIRED_PREFIXES = (
    "universe_eager_refresh",       # 사이클 89, 244건 7일 영속
    "scan_pool_eager_refresh",      # 사이클 83, 230건 7일 영속
    "stock_master_bulk_refresh",    # 사이클 95, 140건 7일 영속
)


def test_g_ui2_count_eager_refresh_today_function_exists():
    """G-UI2-A: `count_eager_refresh_today` 함수 영속 (HIGH)."""
    body = _get_count_eager_refresh_today_source()
    assert body is not None, (
        "\n사이클 100 G-UI2-A Red 상태 — `count_eager_refresh_today` 함수 부재.\n"
        "  Green (backend-dev): src/db/stock_master.py 에 함수 영속 의무.\n"
        "  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )


def test_g_ui2_count_eager_refresh_today_contains_three_prefix():
    """G-UI2-B: `count_eager_refresh_today` 본체에 3 prefix 영역 ≥1건 영속 (HIGH).

    검증 매트릭스 (사이클 100 영역 영구 영속):
    - `universe_eager_refresh` (사이클 89, 244건 영속) 영속
    - `scan_pool_eager_refresh` (사이클 83, 230건 영속) 영속
    - `stock_master_bulk_refresh` (사이클 95, 140건 영속) 영속

    Red 상태 (사이클 100): production 본체 = scan_pool 단독 → 2 영역 부재 → FAIL.

    Green (backend-dev): 3 prefix 영역 source 영역 등장 → PASS.

    영속 의무:
    - 사이클 81 silent 결함 영구 차단 패턴 답습 (`prdy_clpr` → `bfdy_clpr`)
    - 사이클 98 G-DOC1 답습 (KIS 정본 인용 의무 AST 영구 가드)
    - 미래 backend-dev 가 prefix 1개 silent 삭제 영역 영구 차단
    - 매매 안전성 영역 영향 0 (DB 영역 한정)
    """
    body = _get_count_eager_refresh_today_source()
    assert body is not None, (
        "\n사이클 100 G-UI2-B Red 상태 — `count_eager_refresh_today` 함수 부재.\n"
        "  Green (backend-dev): src/db/stock_master.py 에 함수 영속 의무."
    )

    missing_prefixes = [p for p in REQUIRED_PREFIXES if p not in body]
    assert not missing_prefixes, (
        f"\n사이클 100 G-UI2-B 위반 — 3 prefix 영역 ≥1건 영속 위반:\n"
        f"  기대 영역 (사용자 결정 Q65=C-1):\n"
        f"    - universe_eager_refresh (사이클 89, 244건 7일 영속)\n"
        f"    - scan_pool_eager_refresh (사이클 83, 230건 7일 영속)\n"
        f"    - stock_master_bulk_refresh (사이클 95, 140건 7일 영속)\n"
        f"  누락 영역: {missing_prefixes}\n"
        f"  Red 결함: production `count_eager_refresh_today` 본체 = scan_pool_eager_refresh 단독 grep 영속\n"
        f"  실측 영역 (Supabase 7일): 244 + 230 + 140 = 614 영역 중 단일 grep = 230 = ~62% 누락\n"
        f"  Green (backend-dev): 3 prefix OR 영역 시정 의무 (사용자 결정 Q65=C-1)\n"
        f"  영구 가드 패턴 답습: 사이클 81 (prdy_clpr → bfdy_clpr) + 사이클 98 G-DOC1\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )
