"""사이클 101 G-AST1 — `record_full_universe_load_summary` ↔ `flush_*` 영구 가드 (MEDIUM).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**사이클 78 G-AST1 영속 (record_* ↔ flush_* 호출 사이트 영구 가드 패턴 답습)**:
- `record_full_universe_load_summary` 정의 모듈의 대응 `flush_full_universe_load_collector` 호출 사이트 ≥1건
- 미래 신규 collector 추가 시 flush 호출 누락 silent 결함 영구 차단

검증 매트릭스 (사이클 78 G-AST1 영속):
- G-AST1-A: `record_full_universe_load_summary` 함수 정의 영속 (Red = 부재)
- G-AST1-B: `flush_full_universe_load_collector` 함수 정의 영속
- G-AST1-C: production 코드 어딘가에 `flush_full_universe_load_collector` 호출 사이트 ≥1건

Red 상태: 신규 함수 부재 또는 호출 사이트 0건.
Green (backend-dev): `stock_master_metrics.py` 함수 정의 + scheduler.py 또는 scanner.py 호출.

영속 의무:
- 사이클 78 G-AST1 영구 가드 패턴 답습 (`tests/unit/ast/test_cycle78_ast_flush_required.py`)
- 매매 안전성 영역 영향 0 (collector 영역 한정)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# 사이클 136 (2026-06-15) — 카드 #25 AST DRY 헬퍼 모듈 영역 영구 영속 마이그레이션.
# ast.walk 영역 영구 영속 = ast.Await 영역 영구 영속 내부 ast.Call 영역 영구 영속 자동 traversal 영속.
# 헬퍼 영역 영구 영속 = await 영역 영구 영속 자연 흡수 (ast.walk recursive 영속).
from tests.unit.ast._ast_helpers import (
    read_module_source as _module_source,
    find_function_def as _find_function_def,
    count_function_calls as _find_function_calls,
)


def test_g_ast1_a_record_full_universe_load_summary_exists() -> None:
    """G-AST1-A: `record_full_universe_load_summary` 함수 정의 영속 (MEDIUM)."""
    import src.engine.stock_master_metrics as metrics_mod

    assert hasattr(metrics_mod, "record_full_universe_load_summary"), (
        "\n사이클 101 G-AST1-A Red — `record_full_universe_load_summary` 부재.\n"
        "  Green: src/engine/stock_master_metrics.py 함수 정의 의무 (사이클 74/89 패턴 답습)"
    )


def test_g_ast1_b_flush_full_universe_load_collector_exists() -> None:
    """G-AST1-B: `flush_full_universe_load_collector` 함수 정의 영속 (MEDIUM)."""
    import src.engine.stock_master_metrics as metrics_mod

    assert hasattr(metrics_mod, "flush_full_universe_load_collector"), (
        "\n사이클 101 G-AST1-B Red — `flush_full_universe_load_collector` 부재.\n"
        "  Green: src/engine/stock_master_metrics.py 함수 정의 의무 (사이클 78 G-AST1 답습)"
    )


def test_g_ast1_c_flush_call_site_at_least_one() -> None:
    """G-AST1-C: `flush_full_universe_load_collector` 호출 사이트 ≥1건 영속 (MEDIUM).

    검증 매트릭스 (사이클 78 G-AST1 답습):
    - production source (scheduler.py + scanner.py) 영역에서 호출 사이트 ≥1건
    - 미래 silent 결함 영구 차단 (사이클 74 도입 누락 결함 패턴 답습)

    Red 상태: 호출 사이트 0건 → collector 무한 누적 (메모리 leak HIGH).
    Green (backend-dev): scheduler `_full_universe_load_task` 또는 `_api_recovered_collector_loop`
    영역에서 호출 사이트 영속.
    """
    import src.engine.scheduler as scheduler_mod
    import src.engine.scanner as scanner_mod

    scheduler_src = _module_source(Path(scheduler_mod.__file__))
    scanner_src = _module_source(Path(scanner_mod.__file__))

    scheduler_calls = _find_function_calls(scheduler_src, "flush_full_universe_load_collector")
    scanner_calls = _find_function_calls(scanner_src, "flush_full_universe_load_collector")
    total = scheduler_calls + scanner_calls

    assert total >= 1, (
        f"\n사이클 101 G-AST1-C 위반 — flush 호출 사이트 0건 (사이클 78 답습 silent 결함):\n"
        f"  기대: production 영역 호출 사이트 ≥1건\n"
        f"  실제 (scheduler.py + scanner.py 합산): {total}건\n"
        f"  Red 결함 가설: 사이클 74 패턴 — record 도입 / flush 호출 누락 = 메모리 leak HIGH\n"
        f"  Green (backend-dev): _full_universe_load_task 본체 또는\n"
        f"    _api_recovered_collector_loop 본체 영역에 flush 호출 영속 의무"
    )
