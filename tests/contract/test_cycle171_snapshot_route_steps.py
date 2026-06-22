"""사이클 171 — POST /api/strategy-funnel/snapshot 단계별 캡처 전환 회귀 가드.

배경 (자문 cycle171 의제 6 (a)):
- 현재 수동 trigger 는 step_no=99 (최종)만 캡처.
- 운영자 "지금 각 단계 후보를 보고 싶다" 니즈 → capture_funnel_snapshots(is_provisional=False)
  단계별 전체 캡처로 통일 (09:30 자동 hook 과 동일 헬퍼).

회귀 가드:
- G-171-ROUTE-1: 수동 trigger 가 단계별 (step1~N + 99) 캡처 (step_no=99 단독 폐기)
- G-171-ROUTE-2: 수동 trigger 는 is_provisional=False (확정)
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

pytestmark = pytest.mark.contract

_ROUTE_PY = Path(__file__).resolve().parents[2] / "src" / "routes" / "strategy_funnel.py"


@pytest.fixture
def client(monkeypatch):
    from fastapi import FastAPI
    from src.routes.strategy_funnel import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_g_171_route_1_step_by_step_capture(monkeypatch, client):
    """G-171-ROUTE-1: 수동 trigger → 단계별 + 최종 insert_snapshot 호출 (헬퍼 위임)."""
    from src.db import strategy_funnel as db_sf

    # registry — 1 전략, _funnel_steps 2 단계
    strat = MagicMock()
    strat.strategy_id = "donchian_swing"
    strat._funnel_steps = [
        {"step_no": 1, "step_name": "코스피200+코스닥150",
         "survived": ["005930"], "survived_count": 1,
         "excluded": [], "excluded_count": 0},
        {"step_no": 4, "step_name": "20일 신고가 돌파",
         "survived": ["005930"], "survived_count": 1,
         "excluded": [], "excluded_count": 0},
    ]
    strat.get_scanned_tickers = MagicMock(return_value=["005930"])

    fake_scheduler = MagicMock()
    fake_scheduler.registry.all = MagicMock(return_value=[strat])
    monkeypatch.setattr("src.engine.scheduler.trading_scheduler", fake_scheduler)

    captured: list = []

    async def _spy(**kw):
        captured.append(kw)
        return {"id": f"row-{kw['step_no']}"}

    # capture 헬퍼는 src.db.strategy_funnel.insert_snapshot 호출 → DB 모듈 패치
    monkeypatch.setattr(db_sf, "insert_snapshot", _spy)

    resp = client.post("/api/strategy-funnel/snapshot")
    assert resp.status_code == 200

    step_nos = sorted(c["step_no"] for c in captured)
    assert 1 in step_nos, "단계별 step_no=1 캡처 누락 (사이클 171 단계별 전환)"
    assert 4 in step_nos, "단계별 step_no=4 캡처 누락"
    assert 99 in step_nos, "최종 step_no=99 캡처 누락"


def test_g_171_route_2_provisional_false():
    """G-171-ROUTE-2: 수동 trigger 핸들러가 is_provisional=False 명시 (AST)."""
    source = read_module_source(_ROUTE_PY)
    node = find_function_def(source, "trigger_snapshot")
    assert node is not None
    body = ast.unparse(node)
    assert "capture_funnel_snapshots" in body, (
        "수동 trigger 가 capture_funnel_snapshots 헬퍼 위임 안 함"
    )
    assert "is_provisional=False" in body or "is_provisional = False" in body, (
        "수동 trigger is_provisional=False 명시 의무 (확정 캡처)"
    )
