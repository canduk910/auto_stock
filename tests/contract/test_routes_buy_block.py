"""사이클 8 (2026-05-18) Red — `/api/integrations/buy-block` 컨트랙트.

신규 라우트 — 매수 가드 4 모드 + 4 임계값 조정 통합.

GET 응답 구조:
{
    "mode": "OFF"|"WARN"|"SOFT"|"HARD",
    "thresholds": {
        "vix_threshold": float,
        "fg_high_threshold": float,
        "fg_low_threshold": float,
        "defensive_enabled": bool
    },
    "blocked": bool,         // 현재 가드 발동 여부 (mode 무관, 임계 OR 평가)
    "reasons": list[str],    // 발동 사유 (UI 표시용)
    "soft_multiplier": float // SOFT 시 0.5, 그 외 1.0
}

PUT body (부분 갱신):
{
    "mode": "OFF"|"WARN"|"SOFT"|"HARD" (optional),
    "vix_threshold": float (optional, 10~50),
    "fg_high_threshold": float (optional, 50~100),
    "fg_low_threshold": float (optional, 0~50),
    "defensive_enabled": bool (optional)
}
→ 응답에 갱신된 전체 상태.

422 케이스:
- mode 외 값 (예: "STRICT")
- vix_threshold 범위 외 (예: -10 / 100)
- fg_high_threshold 범위 외 (예: 150)
- fg_low_threshold 범위 외 (예: -1)
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.contract


@pytest.fixture
def client(monkeypatch):
    """4 모드 + 4 임계값 DB 헬퍼 + MarketRegime monkeypatch."""
    from src.db import system_config as sc

    state = {
        "mode": "HARD",
        "vix": 25.0,
        "fg_high": 85.0,
        "fg_low": 15.0,
        "defensive_enabled": True,
    }

    async def fake_get_mode():
        return state["mode"]

    async def fake_set_mode(m):
        if m not in {"OFF", "WARN", "SOFT", "HARD"}:
            raise ValueError(f"invalid mode: {m}")
        state["mode"] = m

    async def fake_get_thresholds():
        from src.db.system_config import BuyBlockThresholds  # type: ignore
        return BuyBlockThresholds(
            vix_threshold=state["vix"],
            fg_high_threshold=state["fg_high"],
            fg_low_threshold=state["fg_low"],
            defensive_enabled=state["defensive_enabled"],
        )

    async def fake_set_thresholds(
        vix_threshold=None,
        fg_high_threshold=None,
        fg_low_threshold=None,
        defensive_enabled=None,
    ):
        from src.db.system_config import BuyBlockThresholds  # type: ignore
        if vix_threshold is not None:
            state["vix"] = vix_threshold
        if fg_high_threshold is not None:
            state["fg_high"] = fg_high_threshold
        if fg_low_threshold is not None:
            state["fg_low"] = fg_low_threshold
        if defensive_enabled is not None:
            state["defensive_enabled"] = defensive_enabled
        return BuyBlockThresholds(
            vix_threshold=state["vix"],
            fg_high_threshold=state["fg_high"],
            fg_low_threshold=state["fg_low"],
            defensive_enabled=state["defensive_enabled"],
        )

    monkeypatch.setattr(sc, "get_buy_block_mode", fake_get_mode, raising=False)
    monkeypatch.setattr(sc, "set_buy_block_mode", fake_set_mode, raising=False)
    monkeypatch.setattr(sc, "get_buy_block_thresholds", fake_get_thresholds, raising=False)
    monkeypatch.setattr(sc, "set_buy_block_thresholds", fake_set_thresholds, raising=False)

    # MarketRegime — defensive 가정해서 blocked 응답 검증
    from src.engine import market_regime as mr
    fake_regime = mr.MarketRegime(regime="defensive")
    monkeypatch.setattr(mr, "get_current_regime", lambda: fake_regime, raising=False)

    from src.main import app
    return SimpleNamespace(client=TestClient(app), state=state)


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------
def test_get_buy_block_returns_full_state(client):
    """기본값 HARD + 기본 임계 + defensive 발동 → blocked=True."""
    resp = client.client.get("/api/integrations/buy-block")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["mode"] == "HARD"
    assert data["thresholds"]["vix_threshold"] == 25.0
    assert data["thresholds"]["fg_high_threshold"] == 85.0
    assert data["thresholds"]["fg_low_threshold"] == 15.0
    assert data["thresholds"]["defensive_enabled"] is True
    # defensive regime + HARD → blocked
    assert data["blocked"] is True
    assert "soft_multiplier" in data
    assert data["soft_multiplier"] == 1.0
    assert isinstance(data["reasons"], list)
    assert any("defensive" in r for r in data["reasons"])


def test_get_buy_block_soft_mode_multiplier(client):
    """SOFT 모드 → blocked=False + soft_multiplier=0.5 응답."""
    client.state["mode"] = "SOFT"
    resp = client.client.get("/api/integrations/buy-block")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "SOFT"
    assert data["soft_multiplier"] == 0.5
    assert data["blocked"] is False  # SOFT 는 매수 허용


# ---------------------------------------------------------------------------
# PUT — 부분 갱신
# ---------------------------------------------------------------------------
def test_put_mode_only_updates_mode(client):
    resp = client.client.put(
        "/api/integrations/buy-block", json={"mode": "SOFT"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "SOFT"
    assert client.state["mode"] == "SOFT"
    # 임계는 그대로
    assert data["thresholds"]["vix_threshold"] == 25.0


def test_put_thresholds_only(client):
    resp = client.client.put(
        "/api/integrations/buy-block",
        json={"vix_threshold": 30.0, "fg_high_threshold": 90.0},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["thresholds"]["vix_threshold"] == 30.0
    assert data["thresholds"]["fg_high_threshold"] == 90.0
    # 기본 mode 유지
    assert data["mode"] == "HARD"
    assert client.state["vix"] == 30.0


def test_put_defensive_enabled_false_disables_regime(client):
    """5/17 사용자 케이스 — regime=defensive 차단만 끄기."""
    resp = client.client.put(
        "/api/integrations/buy-block", json={"defensive_enabled": False},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["thresholds"]["defensive_enabled"] is False
    # 응답의 blocked — defensive 무시 + VIX/FG 미설정 → False 여야
    assert data["blocked"] is False


# ---------------------------------------------------------------------------
# 422 — 잘못된 입력
# ---------------------------------------------------------------------------
def test_put_invalid_mode_returns_422(client):
    resp = client.client.put(
        "/api/integrations/buy-block", json={"mode": "STRICT"},
    )
    assert resp.status_code == 422


def test_put_vix_out_of_range_returns_422(client):
    """VIX 범위 [10, 50] 외 → 422."""
    resp = client.client.put(
        "/api/integrations/buy-block", json={"vix_threshold": -10.0},
    )
    assert resp.status_code == 422

    resp = client.client.put(
        "/api/integrations/buy-block", json={"vix_threshold": 100.0},
    )
    assert resp.status_code == 422


def test_put_fg_high_out_of_range_returns_422(client):
    resp = client.client.put(
        "/api/integrations/buy-block", json={"fg_high_threshold": 150.0},
    )
    assert resp.status_code == 422


def test_put_fg_low_out_of_range_returns_422(client):
    resp = client.client.put(
        "/api/integrations/buy-block", json={"fg_low_threshold": -1.0},
    )
    assert resp.status_code == 422
