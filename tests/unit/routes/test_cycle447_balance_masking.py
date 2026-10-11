"""cycle447 제안 7 — `GET /api/balance` 의 `[balance] get_balance 실패` 경고가
httpx 예외 문자열(요청 URL 전체, 계좌번호 `CANO=` 포함)을 그대로 실었다
(`_workspace/analysis/balance_5xx_20261011/result.md` §4).
"""

from __future__ import annotations

import importlib
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_FAKE_ACCOUNT = "12345678"


def _balance_app_with_failing_get_balance(monkeypatch):
    bal = importlib.import_module("src.routes.balance")

    async def _boom():
        raise RuntimeError(
            f"Server error '500' for url "
            f"'https://openapivts.koreainvestment.com:29443/uapi/domestic-stock/"
            f"v1/trading/inquire-balance?CANO={_FAKE_ACCOUNT}&ACNT_PRDT_CD=01'"
        )

    monkeypatch.setattr(bal, "get_balance", _boom, raising=False)
    monkeypatch.setattr(bal, "get_balance_cached", _boom, raising=False)
    app = FastAPI()
    app.include_router(bal.router)
    return TestClient(app, raise_server_exceptions=False)


def test_balance_route_failure_log_does_not_leak_account_number(monkeypatch, caplog):
    client = _balance_app_with_failing_get_balance(monkeypatch)

    with caplog.at_level(logging.WARNING):
        resp = client.get("/api/balance")

    assert resp.status_code == 200
    assert resp.json()["success"] is False

    joined = " | ".join(r.getMessage() for r in caplog.records)
    assert "[balance] get_balance 실패" in joined
    assert _FAKE_ACCOUNT not in joined, f"계좌번호가 로그에 남았다: {joined}"
    assert _FAKE_ACCOUNT not in resp.json()["message"], (
        f"계좌번호가 응답 message 에 남았다: {resp.json()['message']}"
    )
