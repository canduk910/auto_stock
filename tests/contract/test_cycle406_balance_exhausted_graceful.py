"""cycle406 L2 — `GET /api/balance` 가 `get_balance()` 소진 예외를 ASGI 500 이 아니라
`ApiResponse(success=False)` 로 흡수한다.

배경 — 09-30 10:21 정규장에 TTTC8434R 잔고조회 소진 예외가 `/api/balance` 를
원시 500 으로 반복(`_workspace/reports/2026-10-02_night_work.md` §3.4 L2). 같은
흡수 규약은 `src/routes/portfolio.py:34-41` `_net_asset_graceful` 이 이미 쓰고
있다(관찰 전용 라우트는 그래도 200 을 낸다). `/api/balance` 는 잔고 자체가 본문이라
200+빈 데이터로 꾸밀 수 없으므로 `success=False` 로 흡수한다(루트 CLAUDE.md
API 응답 래퍼 규약).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


class _RetriesExhausted(Exception):
    """KIS 소진 예외를 흉내 — 실제 타입이 아니라 '어떤 예외든 흡수한다'를 검정한다."""


def test_get_balance_exhausted_then_500_not_raised_and_success_false(contract_env, monkeypatch):
    async def fake_get_balance_raises():
        raise _RetriesExhausted("TTTC8434R 소진")

    monkeypatch.setattr("src.routes.balance.get_balance", fake_get_balance_raises)

    resp = contract_env.client.get("/api/balance")

    assert resp.status_code == 200, (
        f"소진 예외가 ASGI 미처리 500 으로 나갔다 — 응답: {resp.status_code} {resp.text[:300]}"
    )
    body = resp.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["message"]  # 빈 문자열이면 운영자가 원인을 못 본다


def test_get_balance_normal_then_success_true_unaffected(contract_env, monkeypatch):
    """흡수 규약 추가가 정상 경로를 깨지 않는다 — 기존 기본 fixture 경로 그대로."""
    resp = contract_env.client.get("/api/balance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "holdings" in body["data"]
    assert "summary" in body["data"]
