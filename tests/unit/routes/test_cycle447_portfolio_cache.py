"""cycle447 제안 3 — `GET /api/portfolio/risk` 가 `get_balance_cached()` 를 쓴다.

관찰 전용 라우트(매수 차단 0)라 20초 공유 캐시를 쓸 수 있다
(`_workspace/analysis/balance_5xx_20261011/result.md` 제안 3).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_portfolio_risk_route_shares_cached_balance_across_calls(monkeypatch):
    from src.api import balance as balance_mod
    from src.routes import portfolio as pf

    monkeypatch.setattr(
        pf, "trading_scheduler",
        SimpleNamespace(registry=SimpleNamespace(all=lambda: [])),
        raising=False,
    )

    calls = {"n": 0}

    async def _fake_get_balance(afhr_flpr: str = "N"):
        calls["n"] += 1
        return ([], SimpleNamespace(net_asset=1_000_000))

    # 라우트는 `get_balance_cached()` 를 쓴다 — 실제로 KIS 를 부르는 밑단
    # `balance_mod.get_balance` 만 패치해 캐시 경로 자체(진짜 코드)를 검증한다.
    monkeypatch.setattr(balance_mod, "get_balance", _fake_get_balance)

    await pf.get_portfolio_risk()
    await pf.get_portfolio_risk()

    assert calls["n"] == 1, (
        f"20초 안 재호출은 캐시를 써야 한다 — KIS 호출 {calls['n']}회 (기대 1)"
    )
