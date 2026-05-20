"""사이클 20 (2026-05-20) — boot 시점 사전 순차 발급 회귀 가드.

`TradingScheduler._preissue_all_tokens()` — 메인 + 보조 N 매니저를 순차 발급.
- (F) 메인 + 보조 N 순차 발급 — 모든 매니저 `get_token()` 호출됨
- (G) 보조 1개 발급 실패 graceful — 다음 보조로 진행 + 메인 흐름 보존
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def _make_account(label: str, kis_env: str = "vts"):
    """KisQuoteAccount 더미 객체 — 라벨/env 만 필요."""
    from src.models.kis_quote_account import KisQuoteAccount

    return KisQuoteAccount(
        id=uuid4(),
        label=label,
        app_key="key-" + label,
        app_secret_masked="****abcd",
        kis_env=kis_env,
        active=True,
        created_at=datetime.now(),
        updated_at=None,
    )


@pytest.mark.asyncio
async def test_F_preissue_calls_main_and_all_quote_managers(
    monkeypatch: pytest.MonkeyPatch,
):
    """(F) `_preissue_all_tokens()` 호출 시 메인 + 보조 N 매니저 모두 get_token() 호출."""
    from src.auth import token as token_mod
    from src.db import kis_quote_accounts as kqa
    from src.engine.scheduler import trading_scheduler

    # 보조 매니저 3개 active
    accounts = [
        _make_account("quote-sub-1"),
        _make_account("quote-gold"),
        _make_account("quote-isa"),
    ]

    async def fake_list_accounts(active_only=False):
        return accounts

    monkeypatch.setattr(kqa, "list_accounts", fake_list_accounts, raising=False)

    # 메인 매니저 get_token mock
    main_called = {"n": 0}

    async def fake_main_get_token():
        main_called["n"] += 1
        return "MAIN-TOK"

    monkeypatch.setattr(
        token_mod.token_manager, "get_token", fake_main_get_token, raising=False,
    )

    # 보조 매니저 get_token_manager mock — 각 라벨별로 dummy 매니저 반환
    quote_calls: list[str] = []

    class _DummyMgr:
        def __init__(self, label):
            self._label = label

        async def get_token(self):
            quote_calls.append(self._label)
            return "TOK-" + self._label

    async def fake_get_token_manager(label):
        if label is None:
            return token_mod.token_manager
        return _DummyMgr(label)

    monkeypatch.setattr(
        token_mod, "get_token_manager", fake_get_token_manager, raising=False,
    )

    # 호출
    await trading_scheduler._preissue_all_tokens()

    # 메인 1회 + 보조 3개 모두 호출
    assert main_called["n"] == 1
    assert quote_calls == ["quote-sub-1", "quote-gold", "quote-isa"]


@pytest.mark.asyncio
async def test_G_preissue_continues_on_quote_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    """(G) 보조 1개 발급 실패 → 예외 흡수 후 다음 보조로 진행. 메인 흐름 보존."""
    from src.auth import token as token_mod
    from src.db import kis_quote_accounts as kqa
    from src.engine.scheduler import trading_scheduler

    # 보조 3개 — 중간 (quote-gold) 만 실패
    accounts = [
        _make_account("quote-sub-1"),
        _make_account("quote-gold"),
        _make_account("quote-isa"),
    ]

    async def fake_list_accounts(active_only=False):
        return accounts

    monkeypatch.setattr(kqa, "list_accounts", fake_list_accounts, raising=False)

    # 메인 정상
    main_called = {"n": 0}

    async def fake_main_get_token():
        main_called["n"] += 1
        return "MAIN-TOK"

    monkeypatch.setattr(
        token_mod.token_manager, "get_token", fake_main_get_token, raising=False,
    )

    # 보조 중 quote-gold 만 예외
    quote_calls: list[str] = []

    class _DummyMgr:
        def __init__(self, label):
            self._label = label

        async def get_token(self):
            quote_calls.append(self._label)
            if self._label == "quote-gold":
                raise RuntimeError("KIS 403 Forbidden (사이클 20 시뮬레이션)")
            return "TOK-" + self._label

    async def fake_get_token_manager(label):
        if label is None:
            return token_mod.token_manager
        return _DummyMgr(label)

    monkeypatch.setattr(
        token_mod, "get_token_manager", fake_get_token_manager, raising=False,
    )

    # 호출 — 예외 전파되면 안 됨
    await trading_scheduler._preissue_all_tokens()

    # 메인은 정상 호출
    assert main_called["n"] == 1
    # 보조 3개 모두 시도됨 (quote-gold 실패 후 quote-isa 진행)
    assert quote_calls == ["quote-sub-1", "quote-gold", "quote-isa"]
