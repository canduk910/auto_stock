"""cycle447 제안 3 — `get_balance()` 최근 성공 결과 공유 캐시.

정본 = `_workspace/analysis/balance_5xx_20261011/result.md` 제안 3.
🔴 매도/매수 직전 재대조(order_engine #1.5·D1 판정·selling_reconcile.
reconcile_selling_unknown_one)는 이 캐시를 쓰지 않는다 — 별도 가드(AST).
"""

from __future__ import annotations

import pytest

from src.api import balance as balance_mod
from src.models.balance import AccountSummary


def _make_summary(net_asset=1_000_000) -> AccountSummary:
    return AccountSummary(
        deposit=0, stock_eval_amount=0, total_eval_amount=0, net_asset=net_asset,
        purchase_total=0, eval_total=0, profit_loss_total=0,
    )


@pytest.fixture(autouse=True)
def _reset_cache():
    balance_mod.reset_balance_cache_for_test()
    yield
    balance_mod.reset_balance_cache_for_test()


@pytest.fixture
def fake_clock(monkeypatch):
    state = {"now": 1_000.0}

    def _fake_monotonic():
        return state["now"]

    monkeypatch.setattr(balance_mod.time, "monotonic", _fake_monotonic, raising=False)
    return state


@pytest.mark.asyncio
async def test_cache_hit_within_ttl_skips_kis_call(monkeypatch, fake_clock):
    calls = {"n": 0}

    async def _fake_get_balance(afhr_flpr="N"):
        calls["n"] += 1
        return ([], _make_summary())

    monkeypatch.setattr(balance_mod, "get_balance", _fake_get_balance)

    r1 = await balance_mod.get_balance_cached()
    fake_clock["now"] += 5.0  # TTL(20s) 안
    r2 = await balance_mod.get_balance_cached()

    assert calls["n"] == 1, "TTL 안 재호출은 KIS 를 다시 부르면 안 된다"
    assert r1 is r2


@pytest.mark.asyncio
async def test_cache_refetches_after_ttl_expires(monkeypatch, fake_clock):
    calls = {"n": 0}

    async def _fake_get_balance(afhr_flpr="N"):
        calls["n"] += 1
        return ([], _make_summary(net_asset=calls["n"]))

    monkeypatch.setattr(balance_mod, "get_balance", _fake_get_balance)

    await balance_mod.get_balance_cached()
    fake_clock["now"] += balance_mod._BALANCE_CACHE_TTL_SECS + 1.0
    await balance_mod.get_balance_cached()

    assert calls["n"] == 2, "TTL 경과 뒤에는 다시 불러야 한다"


@pytest.mark.asyncio
async def test_cache_ttl_is_within_10_to_30_seconds():
    assert 10.0 <= balance_mod._BALANCE_CACHE_TTL_SECS <= 30.0


@pytest.mark.asyncio
async def test_failed_call_is_not_cached(monkeypatch, fake_clock):
    calls = {"n": 0}

    async def _fake_get_balance(afhr_flpr="N"):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("KIS down")
        return ([], _make_summary())

    monkeypatch.setattr(balance_mod, "get_balance", _fake_get_balance)

    with pytest.raises(RuntimeError):
        await balance_mod.get_balance_cached()

    # 실패는 캐시되지 않는다 — 바로 다음 호출이 다시 KIS 를 부른다.
    data = await balance_mod.get_balance_cached()
    assert calls["n"] == 2
    assert data[1].net_asset == 1_000_000


@pytest.mark.asyncio
async def test_concurrent_callers_share_single_fetch(monkeypatch):
    """TTL 이 비어 있을 때 동시 호출은 한 번만 KIS 를 부른다(쏠림 방지).

    🔴 `fake_clock` 를 쓰지 않는다 — 이 테스트는 실제 `asyncio.sleep` 로 동시성을
    만드는데, `fake_clock` 이 `time.monotonic` 을 전역으로 동결해(모듈 객체가
    같아 asyncio 이벤트루프 내부 시계까지 같이 동결된다) `asyncio.sleep` 이
    영원히 끝나지 않는 행을 만든다(실제 실측).
    """
    import asyncio

    calls = {"n": 0}

    async def _fake_get_balance(afhr_flpr="N"):
        calls["n"] += 1
        await asyncio.sleep(0.01)
        return ([], _make_summary())

    monkeypatch.setattr(balance_mod, "get_balance", _fake_get_balance)

    results = await asyncio.gather(
        balance_mod.get_balance_cached(),
        balance_mod.get_balance_cached(),
        balance_mod.get_balance_cached(),
    )
    assert calls["n"] == 1
    assert results[0] is results[1] is results[2]
