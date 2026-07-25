"""사이클 214 (2026-07-15) — H0UNMKO0 후보 구독 풀 분산 + cap 20→60.

`scheduler._subscribe_market_operation_tickers` 행위 검증.

- G-214-1 (HIGH, cycle 32 R4): HIGH(보유+익일청산) = `kis_ws.subscribe(bypass_limit=True)`
  메인 직접 유지 (풀 미경유). 불변식.
- G-214-2 (HIGH, 행위): LOW 후보 = `kis_ws_pool.subscribe(priority="LOW")` 경유.
- G-214-4: cap 기본값 == 60.

domain 자문: `_workspace/domain_consult/cycle214_h0unmko0_cap.md` (판정 (b))
Red memo: `_workspace/red/cycle214_h0unmko0_pool.md`
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.market_operation import MARKET_OP_TR_ID
from src.engine.scheduler import TradingScheduler


def _make_scheduler(*, positions: set[str], pending: set[str]):
    """최소 스케줄러 인스턴스 (subscribe 함수만 태우기 위해 __new__ + 필드 주입)."""
    sched = TradingScheduler.__new__(TradingScheduler)

    strat = SimpleNamespace(
        state=SimpleNamespace(positions={t: object() for t in positions})
    )
    registry = MagicMock()
    registry.all.return_value = [strat]

    sched.registry = registry
    sched._pending_next_day_clear = {(t, "some_strategy") for t in pending}
    return sched


def _patch_ws(monkeypatch, *, main_ws_present: bool = True):
    """`kis_ws` (메인 직접) + `kis_ws_pool` (풀 분산) 을 mock 으로 격리.

    함수 본체가 `kis_ws` 는 `src.realtime.websocket` 에서, `kis_ws_pool` 은
    `src.realtime.websocket_pool` 에서 지연 import 하므로 각 소스 모듈 네임스페이스를
    패치한다. (kis_ws_pool 을 websocket 네임스페이스에 패치하면 실제 import 경로와
    어긋나 mock 이 미적용 — 결함 1(ImportError) 시정 후 patch 경로 적응.)
    """
    fake_ws = MagicMock()
    fake_ws._ws = object() if main_ws_present else None
    fake_ws.subscribe = AsyncMock(return_value=None)

    fake_pool = MagicMock()
    fake_pool.subscribe = AsyncMock(return_value="quote-1")

    monkeypatch.setattr("src.realtime.websocket.kis_ws", fake_ws, raising=False)
    monkeypatch.setattr(
        "src.realtime.websocket_pool.kis_ws_pool", fake_pool, raising=False
    )
    return fake_ws, fake_pool


@pytest.mark.asyncio
async def test_G_214_2_low_candidates_go_through_pool(monkeypatch) -> None:
    """G-214-2 (HIGH, 행위) — LOW 후보 H0UNMKO0 는 풀 분산 경유.

    현재 production 은 LOW 후보를 `kis_ws.subscribe(bypass_limit=False)` 로
    메인 직접 구독 → 이 단언은 FAIL (Red).
    """
    fake_ws, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions=set(), pending=set())

    candidates = {"111111", "222222", "333333"}
    await sched._subscribe_market_operation_tickers(candidates)

    # LOW 후보는 풀 subscribe 로 분산되어야 한다.
    assert fake_pool.subscribe.await_count == len(candidates)
    for call in fake_pool.subscribe.await_args_list:
        args, kwargs = call
        # (tr_id, ticker, *, priority="LOW")
        assert args[0] == MARKET_OP_TR_ID
        assert kwargs.get("priority") == "LOW"

    # LOW 후보가 메인 직접(kis_ws.subscribe)으로 새지 않아야 한다.
    low_direct = [
        c for c in fake_ws.subscribe.await_args_list
        if c.kwargs.get("bypass_limit") is False
    ]
    assert low_direct == []


@pytest.mark.asyncio
async def test_G_214_1_high_stays_main_direct_bypass(monkeypatch) -> None:
    """G-214-1 (HIGH, cycle 32 R4) — HIGH 보유/익일청산 은 메인 직접 bypass=True 유지.

    풀 미경유 = 사이클 32 R4 절대 보호 불변식.
    """
    fake_ws, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions={"005930"}, pending={"000660"})

    await sched._subscribe_market_operation_tickers(set())

    high_calls = fake_ws.subscribe.await_args_list
    high_tickers = set()
    for call in high_calls:
        args, kwargs = call
        assert args[0] == MARKET_OP_TR_ID
        assert kwargs.get("bypass_limit") is True  # 절대 보호
        high_tickers.add(args[1])
    assert high_tickers == {"005930", "000660"}

    # HIGH 는 풀 경유 금지 (메인 절대 보장).
    high_via_pool = [
        c for c in fake_pool.subscribe.await_args_list
        if c[0][1] in {"005930", "000660"}
    ]
    assert high_via_pool == []


@pytest.mark.asyncio
async def test_G_214_1b_high_excluded_from_low(monkeypatch) -> None:
    """G-214-1 보강 — HIGH 종목은 LOW 후보에서 제외 (중복 구독 방지)."""
    fake_ws, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions={"005930"}, pending=set())

    # 후보에 보유 종목이 섞여 있어도 LOW 풀 경유에서 제외되어야 한다.
    await sched._subscribe_market_operation_tickers({"005930", "111111"})

    pool_tickers = {c[0][1] for c in fake_pool.subscribe.await_args_list}
    assert "005930" not in pool_tickers
    assert "111111" in pool_tickers


def test_G_214_4_cap_default_is_60() -> None:
    """G-214-4 — cap 기본값 20→60.

    현재 production 은 cap=20 → 이 단언은 FAIL (Red).
    """
    sig = inspect.signature(
        TradingScheduler._subscribe_market_operation_tickers
    )
    assert sig.parameters["cap"].default == 60


@pytest.mark.asyncio
async def test_G_214_2b_low_cap_applies(monkeypatch) -> None:
    """G-214-2 보강 — LOW cap(기본 60) 초과 후보는 잘린다 (결정적 sorted)."""
    fake_ws, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions=set(), pending=set())

    candidates = {f"{i:06d}" for i in range(80)}
    await sched._subscribe_market_operation_tickers(candidates, cap=60)

    assert fake_pool.subscribe.await_count == 60
