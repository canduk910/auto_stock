"""사이클 64 (2026-06-06) Red — C-Route: `/api/system/price-filter` 컨트랙트 (2 케이스).

> **선행 명세**: `_workspace/red/cycle64_price_filter_scanner.md` (§C-Route)
> **설계 카드**: `_workspace/cycle64_price_filter_scanner_design_card.md` §3
> **선례**: 사이클 62 C-Route 3 케이스 → 사이클 64 mode 폐기로 2 케이스 단순화

요구 행위 (Red 단계 모두 422 / 200 응답 결함 정답):

- CR-1: GET 응답에 `mode` 필드 부재 (mode 폐기 후 단순화)
- CR-2: PUT body 에 `mode` 명시 시 거부 (422) — 호환성 차단

위험 등급 LOW (인터페이스 변경 단순).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.contract


@pytest.fixture
def client(monkeypatch):
    """가격 필터 DB 헬퍼 mock — mode 인자 폐기 시뮬레이션."""
    from src.db import system_config as sc

    state = {"min_price": 0, "max_price": 0}

    async def fake_get():
        # Red: PriceFilter import 자체가 실패할 수 있음 — 라우트 호출 시점에 해결
        from src.db.system_config import PriceFilter
        return PriceFilter(
            min_price=state["min_price"],
            max_price=state["max_price"],
        )

    async def fake_set(min_price=None, max_price=None):
        # 사이클 64 — mode 인자 자체 폐기
        if min_price is not None:
            if min_price < 0:
                raise ValueError(f"min_price out of range: {min_price}")
            state["min_price"] = min_price
        if max_price is not None:
            if max_price < 0:
                raise ValueError(f"max_price out of range: {max_price}")
            state["max_price"] = max_price
        if state["max_price"] > 0 and state["min_price"] > state["max_price"]:
            raise ValueError("max_price < min_price")

    monkeypatch.setattr(sc, "get_price_filter", fake_get, raising=False)
    monkeypatch.setattr(sc, "set_price_filter", fake_set, raising=False)
    # 사이클 223-F (2026-08-21) — **소비처 바인딩까지** 패치.
    #
    # `src/routes/system.py` 는 `from src.db.system_config import set_price_filter` 로
    # 모듈 로드 시점에 이름을 **바인딩**한다. 따라서 위의 `sc.<name>` 패치는
    # `src.routes.system` 이 아직 import 되지 않은 경우에만 효과가 있다 —
    # 앞선 contract 테스트가 이미 `src.main` 을 import 했다면 라우트는 **실제** 함수를
    # 호출하고, DB 미가동이라 `set_price_filter` 가 모듈 전역
    # `_price_filter_memory_override` 에 값을 남긴다. 그 잔재가 뒤따르는
    # `tests/unit/db/test_cycle64_price_filter_scanner_system_config.py::test_A1`
    # (기본값 0 기대)을 **수집 순서에 따라** 깨뜨린다(잠복 누수).
    # import 순서와 무관하게 성립하도록 소비처 모듈도 함께 패치한다.
    from src.routes import system as routes_system

    monkeypatch.setattr(routes_system, "get_price_filter", fake_get, raising=False)
    monkeypatch.setattr(routes_system, "set_price_filter", fake_set, raising=False)

    from src.main import app
    return SimpleNamespace(client=TestClient(app), state=state)


# ---------------------------------------------------------------------------
# CR-1: GET 응답에 mode 필드 부재
# ---------------------------------------------------------------------------
def test_CR1_get_price_filter_response_no_mode_field(client):
    """CR-1: GET /api/system/price-filter → 200 + data.mode 필드 부재.

    사이클 64 단순화 — mode 폐기.
    """
    resp = client.client.get("/api/system/price-filter")
    assert resp.status_code == 200, f"status={resp.status_code}"
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["min_price"] == 0
    assert data["max_price"] == 0
    # 사이클 64 — mode 필드 폐기
    assert "mode" not in data, (
        f"사이클 64 mode 폐기 위반 — GET 응답에 mode 필드 잔존: {data}"
    )


# ---------------------------------------------------------------------------
# CR-2: PUT body 에 mode 명시 시 거부 (422)
# ---------------------------------------------------------------------------
def test_CR2_put_with_mode_field_rejected(client):
    """CR-2: PUT body 에 mode 명시 시 422 (Pydantic Extra Forbid).

    사이클 64 — mode 인자 호환성 차단. 클라이언트 오용 방지.
    `PriceFilterUpdateRequest.model_config = ConfigDict(extra="forbid")` 의무.
    """
    # mode 명시 시도
    resp = client.client.put(
        "/api/system/price-filter",
        json={"min_price": 5000, "mode": "HARD"},
    )
    # 422 (Extra forbid) 또는 400 (라우트에서 명시 거부)
    assert resp.status_code in (400, 422), (
        f"mode 인자 호환성 차단 결함 (status={resp.status_code}). "
        "사이클 64 단순화 — mode 필드 자체 폐기 의무"
    )

    # 정상 case — min/max 만 (mode 없이)
    resp_ok = client.client.put(
        "/api/system/price-filter",
        json={"min_price": 5000, "max_price": 1_000_000},
    )
    assert resp_ok.status_code == 200, (
        f"정상 PUT 결함 (status={resp_ok.status_code}, body={resp_ok.json()})"
    )
    data = resp_ok.json()["data"]
    assert data["min_price"] == 5000
    assert data["max_price"] == 1_000_000
    assert "mode" not in data
