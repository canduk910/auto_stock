"""사이클 2 — `/api/market-regime/*` 컨트랙트 테스트.

- GET /current 정상 응답 (empty regime 시에도 200)
- GET /history 정상 응답
- PUT /auto-adjust 토글
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.contract


@pytest.fixture
def client(monkeypatch):
    # 운영 supabase 호출 차단
    from src.db import market_regime_snapshots as mrs
    from src.db import system_config as sc

    async def fake_list_recent(days=30):
        return []
    monkeypatch.setattr(mrs, "list_recent", fake_list_recent)

    async def fake_get_auto():
        return True
    monkeypatch.setattr(sc, "get_auto_regime_adjust", fake_get_auto)

    async def fake_get_ratio():
        return 0.85
    monkeypatch.setattr(sc, "get_cash_usage_ratio", fake_get_ratio)

    async def fake_set_auto(v):
        return None
    monkeypatch.setattr(sc, "set_auto_regime_adjust", fake_set_auto)

    from src.main import app
    return TestClient(app)


def test_get_current_returns_200_empty_regime(client, monkeypatch):
    """empty regime (외부 호출 없음 / DKSTOCK 비활성) 상태에서도 200."""
    from src.engine import market_regime as mr_mod

    monkeypatch.setattr(mr_mod, "get_current_regime", lambda: mr_mod.MarketRegime.empty())

    resp = client.get("/api/market-regime/current")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["regime"] is None
    assert data["buy_blocked"] is False
    assert data["block_reason"] is None
    assert data["auto_regime_adjust"] is True
    assert data["cash_usage_ratio"] == pytest.approx(0.85)
    # 사이클 I — ETF 레짐 관찰 필드 스키마 (신호 부재 시 None / 토글 기본 False)
    assert "etf_kospi_stage" in data
    assert "etf_kosdaq_stage" in data
    assert "etf_defensive" in data
    assert data["etf_enabled"] is False


def test_get_current_with_defensive_regime(client, monkeypatch):
    from src.engine import market_regime as mr_mod

    defensive = mr_mod.MarketRegime(
        regime="defensive",
        regime_desc="방어 (공포 현금)",
        cycle_phase="expansion",
        vix=18.43,
        fear_greed_score=76.0,
        cash_min=75,
    )
    monkeypatch.setattr(mr_mod, "get_current_regime", lambda: defensive)

    resp = client.get("/api/market-regime/current")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["regime"] == "defensive"
    # 사이클 I — 레짐 매수 게이트 제거: defensive 여도 buy_blocked 는 항상 False (정직 표시).
    # block_reason 은 관찰용 "레짐 경보 사유"로 유지 (매수 미개입).
    assert data["buy_blocked"] is False
    assert "defensive" in data["block_reason"].lower()


def test_get_history_returns_list(client):
    resp = client.get("/api/market-regime/history?days=7")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)


def test_put_auto_adjust_toggle(client):
    resp = client.put("/api/market-regime/auto-adjust", json={"enabled": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["auto_regime_adjust"] is False
