"""사이클 126 AST 영구 가드.

G-AST1: scheduler.py 의 task_attrs 튜플 3곳 모두에 _stock_master_basics_refresh_task 포함
        (사이클 79 G-AST2 영속 — task cancel 누락 silent 결함 영구 차단)
G-AST2: stock_master.py route 의 _ALLOWED_POST_ROUTES 화이트리스트에 신규 2 라우트 포함
        (사이클 84 L-2 영속 — POST 추가 silent 결함 영구 차단)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import read_module_source

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]


def test_g_ast1_task_attrs_includes_basics_refresh_task():
    """G-AST1: scheduler.py task_attrs 튜플 3곳 모두 _stock_master_basics_refresh_task 포함."""
    source = read_module_source((ROOT / "src" / "engine" / "scheduler.py"))
    occurrences = source.count('"_stock_master_basics_refresh_task"')
    assert occurrences >= 3, (
        f"_stock_master_basics_refresh_task 의 task_attrs 등장 횟수 = {occurrences} (기대 ≥3, "
        f"사이클 79 G-AST2 영속 = start finally / run_daily finally / stop() 3 영역)"
    )


def test_g_ast2_post_basics_and_daily_in_route_source():
    """G-AST2: routes/stock_master.py 에 POST /basics/refresh + POST /daily/refresh 등록."""
    source = read_module_source((ROOT / "src" / "routes" / "stock_master.py"))
    assert '"/basics/refresh"' in source, "POST /basics/refresh 라우트 미등록"
    assert '"/daily/refresh"' in source, "POST /daily/refresh 라우트 미등록"


def test_g_ast2_whitelist_includes_new_routes():
    """G-AST2: 사이클 84 L-2 AST 화이트리스트 갱신 — 3 라우트 포함."""
    whitelist_source = read_module_source((
        ROOT / "tests" / "unit" / "ast" / "test_cycle84_ast_no_update_route.py"
    ))
    assert '"/refresh-universe"' in whitelist_source, "사이클 90 영속 영역 보존"
    assert '"/basics/refresh"' in whitelist_source, "사이클 126 신규 POST 미등록"
    assert '"/daily/refresh"' in whitelist_source, "사이클 126 신규 POST 미등록"


def test_g_ast1_basics_refresh_task_creation_in_start():
    """G-AST1 보강: scheduler.start() 내부 _stock_master_basics_refresh_task asyncio.create_task 발화."""
    source = read_module_source((ROOT / "src" / "engine" / "scheduler.py"))
    # asyncio.create_task(self._stock_master_basics_refresh_task_loop()) 호출 영역 존재 검증
    assert "_stock_master_basics_refresh_task_loop" in source, (
        "_stock_master_basics_refresh_task_loop 메서드 미정의"
    )
    assert "self._stock_master_basics_refresh_task = asyncio.create_task(" in source, (
        "start() 에서 _stock_master_basics_refresh_task asyncio.create_task 미발화"
    )


def test_g_ast_time_constant_defined():
    """G-AST 보강: TIME_STOCK_MASTER_BASICS_REFRESH = time(16, 10) 상수 정의."""
    source = read_module_source((ROOT / "src" / "engine" / "scheduler.py"))
    assert "TIME_STOCK_MASTER_BASICS_REFRESH" in source, "시간 상수 미정의"
    assert "time(16, 10)" in source, "16:10 KST 시간 미정의 (일봉 task 16:00 직후 10분 마진)"
