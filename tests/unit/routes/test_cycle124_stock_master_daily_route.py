"""사이클 124 — GET /{ticker}/daily 라우트 회귀 가드.

G-DAILY1: 정상 응답 — ApiResponse 래퍼 + rows 반환
G-DAILY2: 데이터 없음 → 404
G-DAILY3: 라우트 등록 순서 정적 가드 — /daily 가 /{ticker} 보다 먼저 등록되어야 함

FastAPI 라우트 등록 순서 의무:
  /{ticker}/history → /{ticker}/daily → /{ticker}  (사이클 124 추가)
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


# ─── G-DAILY1: 정상 응답 ──────────────────────────────────────────────────────

async def test_g_daily1_success_response():
    """GET /{ticker}/daily — 일봉 데이터 ApiResponse 정상 반환."""
    fake_rows = [
        {
            "ticker": "005930",
            "bas_dd": "2026-06-12",
            "open_price": 79000,
            "high_price": 80000,
            "low_price": 78500,
            "close_price": 79500,
            "volume": 12345678,
            "trade_value": 981234567890,
            "change_rate": 0.63,
            "raw": {},
        }
    ]

    with patch(
        "src.routes.stock_master.stock_master_daily.get_recent_daily",
        new_callable=AsyncMock,
        return_value=fake_rows,
    ) as mock_get:
        from fastapi import FastAPI
        from src.routes.stock_master import router

        app = FastAPI()
        app.include_router(router, prefix="/api/stock-master")

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/stock-master/005930/daily?days=1")

    assert resp.status_code == 200, f"status={resp.status_code} body={resp.text}"
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1
    assert body["data"][0]["ticker"] == "005930"
    assert "message" in body

    # get_recent_daily 가 ticker + days 인자로 호출되었는지 검증
    mock_get.assert_awaited_once_with(ticker="005930", days=1)


# ─── G-DAILY2: 404 ────────────────────────────────────────────────────────────

async def test_g_daily2_not_found_when_no_data():
    """GET /{ticker}/daily — 빈 rows 시 404 반환."""
    with patch(
        "src.routes.stock_master.stock_master_daily.get_recent_daily",
        new_callable=AsyncMock,
        return_value=[],  # 빈 리스트 → 404
    ):
        from fastapi import FastAPI
        from src.routes.stock_master import router

        app = FastAPI()
        app.include_router(router, prefix="/api/stock-master")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/stock-master/XXXXX/daily")

    assert resp.status_code == 404, f"빈 rows 시 404 의무, got {resp.status_code}"
    body = resp.json()
    assert "detail" in body


async def test_g_daily2b_graceful_on_exception():
    """GET /{ticker}/daily — get_recent_daily 예외 시 graceful → 404 (빈 리스트 처리)."""
    with patch(
        "src.routes.stock_master.stock_master_daily.get_recent_daily",
        new_callable=AsyncMock,
        side_effect=RuntimeError("DB 장애"),
    ):
        from fastapi import FastAPI
        from src.routes.stock_master import router

        app = FastAPI()
        app.include_router(router, prefix="/api/stock-master")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/stock-master/000001/daily")

    # 예외 → rows=[] → 404 (graceful, 500 아님)
    assert resp.status_code == 404, f"예외 graceful → 404 의무, got {resp.status_code}"


# ─── G-DAILY3: 라우트 등록 순서 정적 가드 ─────────────────────────────────────

def test_g_daily3_route_registration_order():
    """/{ticker}/daily 가 /{ticker} 보다 먼저 소스에 등록되어야 함 (정적 AST 검증)."""
    src_path = Path(__file__).parent.parent.parent.parent / "src" / "routes" / "stock_master.py"
    source = src_path.read_text(encoding="utf-8")
    lines = source.splitlines()

    # 각 경로 데코레이터 첫 번째 등장 줄 번호 수집
    daily_lines = []
    ticker_only_lines = []
    history_lines = []

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if '@router.get("/{ticker}/daily")' in stripped:
            daily_lines.append(i)
        elif '@router.get("/{ticker}/history")' in stripped:
            history_lines.append(i)
        elif '@router.get("/{ticker}")' in stripped:
            ticker_only_lines.append(i)

    assert daily_lines, "/{ticker}/daily 라우트 데코레이터 미등록 — 사이클 124 신규 의무"
    assert history_lines, "/{ticker}/history 라우트 데코레이터 누락"
    assert ticker_only_lines, "/{ticker} 라우트 데코레이터 누락"

    first_daily = daily_lines[0]
    first_history = history_lines[0]
    first_ticker = ticker_only_lines[0]

    assert first_history < first_daily, (
        f"/{{{ticker}}}/history (line {first_history}) 는 /{{{ticker}}}/daily (line {first_daily}) 보다 먼저 등록 의무"
    )
    assert first_daily < first_ticker, (
        f"/{{{ticker}}}/daily (line {first_daily}) 는 /{{{ticker}}} (line {first_ticker}) 보다 먼저 등록 의무 "
        f"(FastAPI LIFO — /daily 가 뒤에 오면 동적 경로가 먹어버림)"
    )
