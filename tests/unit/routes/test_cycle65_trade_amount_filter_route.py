"""사이클 65 (2026-06-06) Red — C-Route: `/api/system/trade-amount-filter` 컨트랙트 (3 함수).

> **선행 명세**: `_workspace/red/cycle65_trade_amount_filter.md` (§File 9)
> **설계 카드 v2**: `_workspace/cycle65_trade_amount_filter_design_card.md` §3
> **선례**: 사이클 64 C-Route 패턴 답습 (extra=forbid 422 + 음수 400 + 정상 invalidate)

요구 행위 (Red 단계 422 / 400 / 200 응답 결함 정답):

- PUT extra 키 → 422 (`ConfigDict(extra="forbid")`)
- PUT min_amount=-1 → 400 (ValueError)
- 정상 PUT → 200 + `invalidate_trade_amount_filter_cache_scanner` 호출 검증 (mock)

위험 등급 MEDIUM (인터페이스 정합성).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture
def client(monkeypatch):
    """거래대금 필터 DB 헬퍼 mock — A 영역 DB 의존성 격리."""
    from src.db import system_config as sc

    state = {"min_amount": 0}

    async def fake_get():
        # Red: TradeAmountFilter import 자체가 실패할 수 있음 — 라우트 호출 시점 해결
        from src.db.system_config import TradeAmountFilter
        return TradeAmountFilter(min_amount=state["min_amount"])

    async def fake_set(min_amount=None):
        if min_amount is not None:
            if min_amount < 0:
                raise ValueError(f"min_amount out of range: {min_amount}")
            state["min_amount"] = min_amount

    monkeypatch.setattr(sc, "get_trade_amount_filter", fake_get, raising=False)
    monkeypatch.setattr(sc, "set_trade_amount_filter", fake_set, raising=False)

    from src.main import app
    return SimpleNamespace(client=TestClient(app), state=state)


# ---------------------------------------------------------------------------
# C-R-1-A: PUT body extra 키 → 422 (extra=forbid)
# ---------------------------------------------------------------------------
def test_put_extra_field_returns_422(client):
    """C-R-1-A: PUT body 에 unexpected_key 명시 → 422.

    `TradeAmountFilterUpdateRequest.model_config = ConfigDict(extra="forbid")` 의무.
    클라이언트 오용 (예: mode 잔재 키 전달) 방지.
    """
    res = client.client.put(
        "/api/system/trade-amount-filter",
        json={"min_amount": 100_000_000, "unexpected_key": 42},
    )
    assert res.status_code == 422, (
        f"extra=forbid 위반 — extra 키 전달 시 422 의무 (실제 {res.status_code})"
    )


# ---------------------------------------------------------------------------
# C-R-1-B: PUT min_amount=-1 → 400 (ValueError)
# ---------------------------------------------------------------------------
def test_put_negative_returns_400(client):
    """C-R-1-B: PUT min_amount=-1 → 400 (set_trade_amount_filter ValueError → HTTPException 400).

    사이클 64 PriceFilter PUT 음수 → 400 패턴 답습.
    """
    res = client.client.put(
        "/api/system/trade-amount-filter",
        json={"min_amount": -1},
    )
    assert res.status_code == 400, (
        f"음수 입력 시 400 의무 (실제 {res.status_code})"
    )


# ---------------------------------------------------------------------------
# C-R-1-C: 정상 PUT → 200 + invalidate 호출 검증
# ---------------------------------------------------------------------------
def test_put_normal_invokes_invalidate(client, monkeypatch):
    """C-R-1-C: 정상 PUT (min_amount=100_000_000) → 200 +
    `invalidate_trade_amount_filter_cache_scanner` 호출 검증.

    Q7-1 즉시 반영 (60s TTL 캐시 무효화) — scanner 영역 invalidate.
    """
    inv_mock = MagicMock()
    # routes/system.py 가 `from src.engine import scanner` 후
    # `scanner.invalidate_trade_amount_filter_cache_scanner()` 호출 의무
    monkeypatch.setattr(
        "src.engine.scanner.invalidate_trade_amount_filter_cache_scanner",
        inv_mock,
        raising=False,
    )

    res = client.client.put(
        "/api/system/trade-amount-filter",
        json={"min_amount": 100_000_000},
    )
    assert res.status_code == 200, (
        f"정상 PUT 결함 (실제 {res.status_code}, body={res.json() if res.content else 'empty'})"
    )

    inv_mock.assert_called_once()
