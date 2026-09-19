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


# ---------------------------------------------------------------------------
# cycle315 — `enabled` 는 DB 우선 / env fallback (`system_integrations._build_status` 규약)
# ---------------------------------------------------------------------------
def _patch_db_toggle(monkeypatch, value):
    from src.db import system_config as sc

    async def _get():
        return value

    monkeypatch.setattr(sc, "get_dkstock_regime_enabled", _get)


def test_current_enabled_prefers_db_over_env(client, monkeypatch):
    """env=False + DB=True → enabled 는 True.

    Settings UI 토글은 DB 를 쓴다. 라우트가 env 만 보면 운영자가 켠 상태가 화면에
    영원히 꺼짐으로 보인다.
    """
    from src.config import settings

    monkeypatch.setattr(settings, "dkstock_regime_enabled", False, raising=False)
    _patch_db_toggle(monkeypatch, True)

    data = client.get("/api/market-regime/current").json()["data"]
    assert data["enabled"] is True


def test_current_enabled_db_false_overrides_env_true(client, monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "dkstock_regime_enabled", True, raising=False)
    _patch_db_toggle(monkeypatch, False)

    data = client.get("/api/market-regime/current").json()["data"]
    assert data["enabled"] is False


def test_current_enabled_db_none_falls_back_to_env(client, monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "dkstock_regime_enabled", True, raising=False)
    _patch_db_toggle(monkeypatch, None)

    data = client.get("/api/market-regime/current").json()["data"]
    assert data["enabled"] is True


def test_current_enabled_db_error_falls_back_to_env(client, monkeypatch):
    """DB 조회 예외는 graceful — 200 + env 값."""
    from src.config import settings
    from src.db import system_config as sc

    monkeypatch.setattr(settings, "dkstock_regime_enabled", True, raising=False)

    async def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(sc, "get_dkstock_regime_enabled", _boom)

    resp = client.get("/api/market-regime/current")
    assert resp.status_code == 200
    assert resp.json()["data"]["enabled"] is True


def test_current_buy_blocked_is_always_false_regression(client, monkeypatch):
    """🔴 레짐은 매수를 차단하지 않는다 — DB 토글이 켜져도 buy_blocked 는 상수 False."""
    from src.config import settings
    from src.engine import market_regime as mr_mod

    monkeypatch.setattr(settings, "dkstock_regime_enabled", False, raising=False)
    _patch_db_toggle(monkeypatch, True)
    monkeypatch.setattr(
        mr_mod, "get_current_regime",
        lambda: mr_mod.MarketRegime(
            regime="defensive", regime_desc="방어 (공포 현금)",
            cycle_phase="expansion", vix=14.81, fear_greed_score=69.0,
            buffett_ratio=2.626, cash_min=75,
        ),
    )

    data = client.get("/api/market-regime/current").json()["data"]
    assert data["enabled"] is True
    assert data["regime"] == "defensive"
    assert data["buy_blocked"] is False
    assert data["cash_min"] == 75
