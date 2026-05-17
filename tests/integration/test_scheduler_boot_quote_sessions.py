"""Cycle 7-C Red — `_boot()` 가 보조 시세 세션을 연결한다.

`scheduler.TradingScheduler.start()` (또는 `_boot()`) 가 메인 WS 연결 외에
풀의 보조 세션을 함께 connect 한다. 보조 세션 0개면 메인 only 동작 (회귀 0).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# E-1. 보조 0개 → 메인 only (회귀)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_boot_when_no_secondary_then_main_only(monkeypatch):
    """보조 계좌 0개일 때 `kis_ws_pool.start()` 가 메인만 처리 — 회귀 0."""
    from src.realtime import websocket_pool as wp_mod

    # 보조 0개
    async def _empty(*_args, **_kwargs):
        return []
    monkeypatch.setattr(
        "src.db.kis_quote_accounts.list_accounts", _empty, raising=False
    )

    # `kis_ws_pool.start()` 호출 시 _quotes 가 비어있어야
    pool = wp_mod.WebsocketPool()
    await pool.start()

    assert pool._quotes == [], f"보조 0개 시 _quotes 빈 리스트, 실제={pool._quotes}"


# ---------------------------------------------------------------------------
# E-2. 보조 N개 → 풀의 _quotes 채워짐 + connect 발화
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_boot_when_n_secondary_then_connects_pool(monkeypatch):
    """보조 2개 등록 시 `pool.start()` 후 `_quotes` 길이 2."""
    from src.realtime import websocket_pool as wp_mod
    from src.auth import token as token_mod

    class _Acct:
        def __init__(self, label):
            self.label = label
            self.active = True

    async def _list_active(*_args, active_only=False, **_kwargs):
        return [_Acct("quote-1"), _Acct("quote-2")]

    monkeypatch.setattr(
        "src.db.kis_quote_accounts.list_accounts", _list_active, raising=False
    )

    # 보조 매니저 mock
    async def _get_tm(label):
        if label is None:
            return token_mod.token_manager
        mm = AsyncMock()
        mm.label = label
        mm.get_approval_key = AsyncMock(return_value=f"appkey-{label}")
        mm.get_token = AsyncMock(return_value=f"tok-{label}")
        mm.build_headers = lambda tr_id, hashkey="": {"tr_id": tr_id}
        mm.app_key = f"{label}-key"
        mm.app_secret = f"{label}-secret"
        return mm

    monkeypatch.setattr(token_mod, "get_token_manager", _get_tm, raising=False)

    pool = wp_mod.WebsocketPool()
    await pool.start()

    assert len(pool._quotes) == 2, (
        f"보조 2개 시 _quotes 길이 2, 실제={len(pool._quotes)}"
    )


# ---------------------------------------------------------------------------
# E-3. 보조 세션 connect 실패 → graceful
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_boot_when_secondary_connect_fails_then_graceful(monkeypatch):
    """보조 토큰 매니저 발급 실패 시 다른 보조 / 메인 정상 동작."""
    from src.realtime import websocket_pool as wp_mod
    from src.auth import token as token_mod

    class _Acct:
        def __init__(self, label):
            self.label = label
            self.active = True

    async def _list_active(*_args, active_only=False, **_kwargs):
        return [_Acct("quote-broken"), _Acct("quote-2")]

    monkeypatch.setattr(
        "src.db.kis_quote_accounts.list_accounts", _list_active, raising=False
    )

    async def _get_tm(label):
        if label is None:
            return token_mod.token_manager
        if label == "quote-broken":
            raise ValueError("보조 미등록")
        mm = AsyncMock()
        mm.label = label
        mm.get_approval_key = AsyncMock(return_value=f"appkey-{label}")
        mm.get_token = AsyncMock(return_value=f"tok-{label}")
        mm.build_headers = lambda tr_id, hashkey="": {"tr_id": tr_id}
        mm.app_key = f"{label}-key"
        mm.app_secret = f"{label}-secret"
        return mm

    monkeypatch.setattr(token_mod, "get_token_manager", _get_tm, raising=False)

    pool = wp_mod.WebsocketPool()
    # 예외 전파 없이 graceful 진행
    await pool.start()

    # quote-2 만 등록되었어야
    assert len(pool._quotes) == 1, (
        f"실패한 quote-broken 제외 quote-2 만 등록, 실제={len(pool._quotes)}"
    )


# ---------------------------------------------------------------------------
# E-4. 보조 등록 후에도 체결통보는 메인만 — 가드 회귀
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_boot_execution_notice_still_main_only(monkeypatch):
    """보조 세션 N개 등록 후에도 체결통보(H0STCNI0/H0STCNI9) 구독은 메인만."""
    from src.realtime import websocket_pool as wp_mod
    from src.auth import token as token_mod

    class _Acct:
        def __init__(self, label):
            self.label = label
            self.active = True

    async def _list_active(*_args, active_only=False, **_kwargs):
        return [_Acct("quote-1")]

    monkeypatch.setattr(
        "src.db.kis_quote_accounts.list_accounts", _list_active, raising=False
    )

    async def _get_tm(label):
        if label is None:
            return token_mod.token_manager
        mm = AsyncMock()
        mm.label = label
        mm.get_approval_key = AsyncMock(return_value=f"appkey-{label}")
        mm.get_token = AsyncMock(return_value=f"tok-{label}")
        mm.build_headers = lambda tr_id, hashkey="": {"tr_id": tr_id}
        mm.app_key = f"{label}-key"
        mm.app_secret = f"{label}-secret"
        return mm

    monkeypatch.setattr(token_mod, "get_token_manager", _get_tm, raising=False)

    pool = wp_mod.WebsocketPool()
    await pool.start()

    # 체결통보 구독 시도 → 메인으로만 (체결통보 가드는 사이클 7-B 유지)
    main_sub_spy = AsyncMock()
    monkeypatch.setattr(pool._main, "subscribe", main_sub_spy, raising=False)

    # quote-1 의 subscribe 도 spy
    quote_sub_spies = []
    for q in pool._quotes:
        spy = AsyncMock()
        monkeypatch.setattr(q, "subscribe", spy, raising=False)
        quote_sub_spies.append(spy)

    await pool.subscribe("H0STCNI0", "HTSID", priority="LOW")

    # 메인만 호출
    assert main_sub_spy.await_count == 1
    for spy in quote_sub_spies:
        assert spy.await_count == 0, "보조 세션에 체결통보 구독 시도되면 안 됨"
