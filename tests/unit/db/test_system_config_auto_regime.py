"""사이클 2 — `src/db/system_config.py::get/set_auto_regime_adjust`.

매크로 레짐 기반 cash_usage_ratio 자동 조정 토글.

요구 행위:
1. `get_auto_regime_adjust()` — 키 부재 시 기본 True 반환.
2. `set_auto_regime_adjust(False)` → upsert + 재조회 False.
3. round-trip: True → False → True.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_get_default_true_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    enabled = await system_config.get_auto_regime_adjust()
    assert enabled is True


@pytest.mark.asyncio
async def test_set_false_then_get_false(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    await system_config.set_auto_regime_adjust(False)
    enabled = await system_config.get_auto_regime_adjust()
    assert enabled is False


@pytest.mark.asyncio
async def test_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    await system_config.set_auto_regime_adjust(False)
    assert await system_config.get_auto_regime_adjust() is False
    await system_config.set_auto_regime_adjust(True)
    assert await system_config.get_auto_regime_adjust() is True
