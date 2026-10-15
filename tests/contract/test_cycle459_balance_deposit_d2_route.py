"""cycle459 — `GET /api/balance` 의 summary 에 D+1·D+2 예수금이 실린다.

`get_balance()` 가 KIS 응답에서 읽은 값(정수 원 또는 None)이 라우트 본문까지 그대로
간다 — 모르는 값은 JSON `null`(0 아님).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


def _summary(d1, d2):
    from src.models.balance import AccountSummary

    return AccountSummary(
        deposit=346_455, deposit_d1=d1, deposit_d2=d2,
        stock_eval_amount=0, total_eval_amount=346_455, net_asset=346_455,
        purchase_total=0, eval_total=0, profit_loss_total=0,
    )


@pytest.mark.parametrize("d1,d2", [(296_455, 1_046_455), (None, None)])
def test_balance_route_carries_deposit_d1_d2(contract_env, monkeypatch, d1, d2):
    async def fake_get_balance():
        return [], _summary(d1, d2)

    monkeypatch.setattr("src.routes.balance.get_balance", fake_get_balance)
    r = contract_env.client.get("/api/balance")
    assert r.status_code == 200
    summary = r.json()["data"]["summary"]
    assert summary["deposit"] == 346_455
    assert summary["deposit_d1"] == d1
    assert summary["deposit_d2"] == d2
