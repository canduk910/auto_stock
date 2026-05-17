"""사이클 5 (2026-05-17) Red — `/api/integrations/*` 컨트랙트.

3 토글 통합 라우트:
- dkstock-regime (DB→.env fallback / 활성화 시 백그라운드 fetch trigger)
- kis-mcp (DB→.env fallback / 즉시 fetch 없음)
- auto-regime-adjust (이미 system_config 에 키 존재 — 라우트만 통합 위치 이동)

응답 구조:
{
    "enabled": bool,   // 현재 유효 값 (DB 우선, 없으면 env)
    "source": "db"|"env",  // 현재 enabled 의 결정 출처
    "env_value": bool,  // settings.* 환경변수 원본
    "db_value": bool|null,  // system_config DB 원본 (없으면 null)
}

PUT body: {"enabled": bool} → DB 갱신 + 응답 갱신값.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.contract


@pytest.fixture
def client(monkeypatch):
    """라우트 자체 테스트 fixture — DB 헬퍼와 settings 둘 다 monkeypatch."""
    from src.db import system_config as sc

    state = {
        "dkstock_db": None,
        "mcp_db": None,
        "auto_regime_db": None,
    }
    trigger_calls = []

    async def fake_get_dkstock():
        return state["dkstock_db"]

    async def fake_set_dkstock(v):
        state["dkstock_db"] = bool(v)

    async def fake_get_mcp():
        return state["mcp_db"]

    async def fake_set_mcp(v):
        state["mcp_db"] = bool(v)

    async def fake_get_auto_regime():
        return state["auto_regime_db"] if state["auto_regime_db"] is not None else True

    async def fake_set_auto_regime(v):
        state["auto_regime_db"] = bool(v)

    monkeypatch.setattr(sc, "get_dkstock_regime_enabled", fake_get_dkstock, raising=False)
    monkeypatch.setattr(sc, "set_dkstock_regime_enabled", fake_set_dkstock, raising=False)
    monkeypatch.setattr(sc, "get_kis_mcp_enabled", fake_get_mcp, raising=False)
    monkeypatch.setattr(sc, "set_kis_mcp_enabled", fake_set_mcp, raising=False)
    monkeypatch.setattr(sc, "get_auto_regime_adjust", fake_get_auto_regime, raising=False)
    monkeypatch.setattr(sc, "set_auto_regime_adjust", fake_set_auto_regime, raising=False)

    # settings 환경변수 (env_value 노출 기본값 False)
    from src.config import settings
    monkeypatch.setattr(settings, "dkstock_regime_enabled", False, raising=False)
    monkeypatch.setattr(settings, "kis_mcp_enabled", False, raising=False)

    # 활성화 시 백그라운드 fetch trigger — 호출만 기록
    from src.routes import system_integrations as si_mod

    async def fake_refresh():
        trigger_calls.append("dkstock_fetch")

    monkeypatch.setattr(
        si_mod, "_refresh_market_regime_and_persist_safely", fake_refresh, raising=False,
    )

    from src.main import app
    return SimpleNamespace(client=TestClient(app), state=state, trigger_calls=trigger_calls)


# ---------------------------------------------------------------------------
# GET — 3 토글 응답 구조
# ---------------------------------------------------------------------------
def test_get_dkstock_regime_db_none_env_false(client):
    """DB None / env False → enabled=False, source=env, db_value=null."""
    resp = client.client.get("/api/integrations/dkstock-regime")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["enabled"] is False
    assert data["source"] == "env"
    assert data["env_value"] is False
    assert data["db_value"] is None


def test_get_dkstock_regime_db_true_overrides_env(client, monkeypatch):
    client.state["dkstock_db"] = True

    resp = client.client.get("/api/integrations/dkstock-regime")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["enabled"] is True
    assert data["source"] == "db"
    assert data["env_value"] is False
    assert data["db_value"] is True


def test_get_kis_mcp_basic(client):
    resp = client.client.get("/api/integrations/kis-mcp")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["enabled"] is False
    assert data["source"] == "env"
    assert data["db_value"] is None


def test_get_auto_regime_adjust(client):
    """auto-regime-adjust — 기존 system_config 이미 있는 키. 라우트만 통합."""
    resp = client.client.get("/api/integrations/auto-regime-adjust")
    assert resp.status_code == 200
    data = resp.json()["data"]
    # 기본값은 True (fake_get_auto_regime).
    assert data["enabled"] is True
    # auto_regime_adjust 는 항상 DB 가 진실 (None=기본 True 컨벤션은 DB 헬퍼 책임).
    # 본 라우트는 source 표시는 형식적 — DB 부재 시 True 디폴트는 system_config 헬퍼 책임.


# ---------------------------------------------------------------------------
# PUT — DB 갱신 + 응답
# ---------------------------------------------------------------------------
def test_put_dkstock_regime_enabled_true(client):
    resp = client.client.put(
        "/api/integrations/dkstock-regime", json={"enabled": True}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["enabled"] is True
    assert data["db_value"] is True
    assert data["source"] == "db"
    # DB 상태도 변경 확인
    assert client.state["dkstock_db"] is True


def test_put_dkstock_regime_enabled_true_triggers_background_fetch(client):
    """활성화(True) 시 _refresh_market_regime_and_persist_safely 백그라운드 task 발화."""
    resp = client.client.put(
        "/api/integrations/dkstock-regime", json={"enabled": True}
    )
    assert resp.status_code == 200
    # 백그라운드 task 가 실제로 호출되었는지 확인 (TestClient 는 task 도 await)
    assert "dkstock_fetch" in client.trigger_calls


def test_put_dkstock_regime_enabled_false_no_fetch_trigger(client):
    """비활성화(False) 시 fetch trigger 발화 안 함."""
    resp = client.client.put(
        "/api/integrations/dkstock-regime", json={"enabled": False}
    )
    assert resp.status_code == 200
    assert "dkstock_fetch" not in client.trigger_calls


def test_put_kis_mcp_enabled_true_no_fetch_trigger(client):
    """KIS MCP 토글은 즉시 fetch 안 함 — 백테스트는 자문 시점 발화."""
    resp = client.client.put(
        "/api/integrations/kis-mcp", json={"enabled": True}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["enabled"] is True
    assert client.state["mcp_db"] is True
    # 백그라운드 task 없음
    assert "dkstock_fetch" not in client.trigger_calls


def test_put_auto_regime_adjust(client):
    resp = client.client.put(
        "/api/integrations/auto-regime-adjust", json={"enabled": False}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["enabled"] is False
    assert client.state["auto_regime_db"] is False


# ---------------------------------------------------------------------------
# DB 갱신 실패 시 에러 응답
# ---------------------------------------------------------------------------
def test_put_dkstock_regime_db_failure_returns_500(client, monkeypatch):
    from src.db import system_config as sc

    async def fail_set(v):
        raise RuntimeError("DB down")

    monkeypatch.setattr(sc, "set_dkstock_regime_enabled", fail_set, raising=False)

    resp = client.client.put(
        "/api/integrations/dkstock-regime", json={"enabled": True}
    )
    assert resp.status_code == 500
