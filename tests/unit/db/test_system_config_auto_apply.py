"""사이클 23 P3-3 Red — system_config.auto_apply_enabled 키 헬퍼.

요구 행위:
1. 기본값 False (DB 미설정)
2. set/get round-trip (True 저장 → True 조회)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_auto_apply_enabled_default_false(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """DB 미설정 시 기본값 False."""
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)
    value = await system_config.get_auto_apply_enabled()
    assert value is False


@pytest.mark.asyncio
async def test_auto_apply_enabled_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """set True → get True round-trip."""
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)
    await system_config.set_auto_apply_enabled(True)
    assert await system_config.get_auto_apply_enabled() is True
    await system_config.set_auto_apply_enabled(False)
    assert await system_config.get_auto_apply_enabled() is False
