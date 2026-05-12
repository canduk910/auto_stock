"""Phase J3 Red — `/api/strategies/system/cash-usage-ratio` GET/PUT.

요구 행위:
1. GET 기본 1.0 (DB 미설정 시).
2. PUT 0.8 → 200 응답 `{ratio: 0.8}`, 재 GET 0.8.
3. PUT 0.4 → 400 (범위 미만).
4. PUT 1.5 → 400 (범위 초과).
5. PUT 0.83 → 200 응답 `{ratio: 0.85}` (5% 보정).

라우터는 `src.routes.strategies` 모듈의 `get_cash_usage_ratio` / `set_cash_usage_ratio`
헬퍼를 모듈 네임스페이스로 사용한다고 가정 — 테스트는 그 두 함수를 monkeypatch.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


@pytest.fixture
def cash_ratio_env(contract_env, monkeypatch):
    """In-memory cash_usage_ratio store + helper monkeypatch."""
    state = {"value": 1.0}

    async def fake_get():
        return state["value"]

    async def fake_set(ratio: float):
        if ratio < 0.5 or ratio > 1.0:
            raise ValueError(f"cash_usage_ratio out of range [0.5, 1.0]: {ratio}")
        # 5% 단위 보정
        adjusted = round(ratio / 0.05) * 0.05
        state["value"] = round(adjusted, 2)

    monkeypatch.setattr(
        "src.routes.strategies.get_cash_usage_ratio", fake_get, raising=False
    )
    monkeypatch.setattr(
        "src.routes.strategies.set_cash_usage_ratio", fake_set, raising=False
    )

    contract_env.state.cash_usage_ratio = state  # type: ignore[attr-defined]
    return contract_env


def test_get_cash_usage_ratio_default(cash_ratio_env):
    r = cash_ratio_env.client.get("/api/strategies/system/cash-usage-ratio")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["ratio"] == pytest.approx(1.0)


def test_put_cash_usage_ratio_valid_persists(cash_ratio_env):
    r = cash_ratio_env.client.put(
        "/api/strategies/system/cash-usage-ratio",
        json={"ratio": 0.8},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["ratio"] == pytest.approx(0.8)

    # 재 GET 0.8
    r2 = cash_ratio_env.client.get("/api/strategies/system/cash-usage-ratio")
    assert r2.json()["data"]["ratio"] == pytest.approx(0.8)


def test_put_cash_usage_ratio_below_05_returns_400(cash_ratio_env):
    r = cash_ratio_env.client.put(
        "/api/strategies/system/cash-usage-ratio",
        json={"ratio": 0.4},
    )
    assert r.status_code == 400


def test_put_cash_usage_ratio_above_1_returns_400(cash_ratio_env):
    r = cash_ratio_env.client.put(
        "/api/strategies/system/cash-usage-ratio",
        json={"ratio": 1.5},
    )
    assert r.status_code == 400


def test_put_cash_usage_ratio_rounds_to_5_percent(cash_ratio_env):
    """0.83 → 0.85 (자동 보정). 응답에 보정된 값을 포함."""
    r = cash_ratio_env.client.put(
        "/api/strategies/system/cash-usage-ratio",
        json={"ratio": 0.83},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["ratio"] == pytest.approx(0.85)
