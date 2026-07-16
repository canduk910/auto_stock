"""사이클 5 (2026-05-17) Red — `src/db/system_config.py` 신규 토글 헬퍼.

외부 통합 ON/OFF 토글을 DB(system_config) 에 영속화. .env fallback 보존.

요구 행위:
1. `get_dkstock_regime_enabled()` — 키 부재 시 `None` 반환 (호출자가 .env fallback).
2. `set_dkstock_regime_enabled(True/False)` → upsert + 재조회 일치.
3. `get_kis_mcp_enabled()` / `set_kis_mcp_enabled()` — 동일 패턴.
4. round-trip: True → False → True.

기존 J3 cash_usage_ratio / 사이클 2 auto_regime_adjust 패턴과 다른 점:
- **`get_*` 의 기본값이 `None`** — 호출자가 settings.* 환경변수 fallback 결정.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# dkstock_regime_enabled
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_dkstock_regime_enabled_missing_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    """키 부재 시 None 반환 — 호출자가 .env fallback."""
    from src.db import system_config

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)
    value = await system_config.get_dkstock_regime_enabled()
    assert value is None


@pytest.mark.asyncio
async def test_set_dkstock_regime_enabled_true_then_get_true(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)
    await system_config.set_dkstock_regime_enabled(True)
    assert await system_config.get_dkstock_regime_enabled() is True


@pytest.mark.asyncio
async def test_set_dkstock_regime_enabled_false_then_get_false(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)
    await system_config.set_dkstock_regime_enabled(False)
    assert await system_config.get_dkstock_regime_enabled() is False


@pytest.mark.asyncio
async def test_dkstock_regime_enabled_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)
    await system_config.set_dkstock_regime_enabled(True)
    assert await system_config.get_dkstock_regime_enabled() is True
    await system_config.set_dkstock_regime_enabled(False)
    assert await system_config.get_dkstock_regime_enabled() is False
    await system_config.set_dkstock_regime_enabled(True)
    assert await system_config.get_dkstock_regime_enabled() is True


# ---------------------------------------------------------------------------
# kis_mcp_enabled
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_kis_mcp_enabled_missing_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)
    value = await system_config.get_kis_mcp_enabled()
    assert value is None


@pytest.mark.asyncio
async def test_set_kis_mcp_enabled_true_then_get_true(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)
    await system_config.set_kis_mcp_enabled(True)
    assert await system_config.get_kis_mcp_enabled() is True


@pytest.mark.asyncio
async def test_set_kis_mcp_enabled_false_then_get_false(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)
    await system_config.set_kis_mcp_enabled(False)
    assert await system_config.get_kis_mcp_enabled() is False


@pytest.mark.asyncio
async def test_kis_mcp_enabled_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)
    await system_config.set_kis_mcp_enabled(True)
    assert await system_config.get_kis_mcp_enabled() is True
    await system_config.set_kis_mcp_enabled(False)
    assert await system_config.get_kis_mcp_enabled() is False
