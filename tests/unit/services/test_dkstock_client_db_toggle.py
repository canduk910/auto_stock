"""사이클 5 (2026-05-17) Red — dkstock_client `_check_enabled` DB 우선 / .env fallback.

기존 동작 (사이클 2): `self._enabled` 가 생성자 시점 settings.dkstock_regime_enabled 만 참조 → 운영 중 재기동 없이 토글 불가.

신규 요구 (사이클 5):
1. `_check_enabled()` 는 async 로 변경되어 DB 값을 우선 조회.
2. DB 값이 `True` → 활성 (DB가 진실).
3. DB 값이 `False` → 비활성 (DB가 진실).
4. DB 값이 `None` (키 부재) → `settings.dkstock_regime_enabled` 환경변수 fallback.
5. DB 값 갱신 후 다음 호출에서 즉시 반영 (캐시 없이 매 호출 조회 — 운영자 즉시 ON/OFF 보장).

테스트 더블:
- `src.db.system_config.get_dkstock_regime_enabled` 를 monkeypatch.
- `src.config.settings` 의 `dkstock_regime_enabled` 도 monkeypatch.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _make_client(enabled_ctor: bool = False):
    from src.services.dkstock_client import DkstockClient

    return DkstockClient(
        base_url="https://dkstock.cloud",
        username="autostock",
        password="AUTOSTOCK1",
        enabled=enabled_ctor,  # 사이클 5 이후엔 fallback 만 책임
    )


@pytest.mark.asyncio
async def test_db_true_overrides_env_false(monkeypatch: pytest.MonkeyPatch):
    """DB=True / .env=False → 활성 (DB 우선)."""
    from src.db import system_config
    from src.services import dkstock_client as dc

    async def fake_get_db():
        return True

    monkeypatch.setattr(system_config, "get_dkstock_regime_enabled", fake_get_db)
    # .env fallback 은 False
    client = _make_client(enabled_ctor=False)

    enabled = await client._check_enabled_async()
    assert enabled is True


@pytest.mark.asyncio
async def test_db_false_overrides_env_true(monkeypatch: pytest.MonkeyPatch):
    """DB=False / .env=True → 비활성 (DB 우선)."""
    from src.db import system_config

    async def fake_get_db():
        return False

    monkeypatch.setattr(system_config, "get_dkstock_regime_enabled", fake_get_db)
    client = _make_client(enabled_ctor=True)

    enabled = await client._check_enabled_async()
    assert enabled is False


@pytest.mark.asyncio
async def test_db_none_falls_back_to_env_true(monkeypatch: pytest.MonkeyPatch):
    """DB=None / .env=True → 활성 (fallback)."""
    from src.db import system_config

    async def fake_get_db():
        return None

    monkeypatch.setattr(system_config, "get_dkstock_regime_enabled", fake_get_db)
    client = _make_client(enabled_ctor=True)

    enabled = await client._check_enabled_async()
    assert enabled is True


@pytest.mark.asyncio
async def test_db_none_falls_back_to_env_false(monkeypatch: pytest.MonkeyPatch):
    """DB=None / .env=False → 비활성 (fallback)."""
    from src.db import system_config

    async def fake_get_db():
        return None

    monkeypatch.setattr(system_config, "get_dkstock_regime_enabled", fake_get_db)
    client = _make_client(enabled_ctor=False)

    enabled = await client._check_enabled_async()
    assert enabled is False


@pytest.mark.asyncio
async def test_db_value_change_is_reflected_immediately(monkeypatch: pytest.MonkeyPatch):
    """DB 값 갱신 후 다음 _check_enabled_async 호출에서 즉시 반영 (캐시 없음)."""
    from src.db import system_config

    state = {"value": False}

    async def fake_get_db():
        return state["value"]

    monkeypatch.setattr(system_config, "get_dkstock_regime_enabled", fake_get_db)
    client = _make_client(enabled_ctor=False)

    assert await client._check_enabled_async() is False
    state["value"] = True
    assert await client._check_enabled_async() is True
    state["value"] = False
    assert await client._check_enabled_async() is False


@pytest.mark.asyncio
async def test_db_exception_falls_back_to_env(monkeypatch: pytest.MonkeyPatch):
    """DB 조회 예외 시 .env fallback (graceful)."""
    from src.db import system_config

    async def fake_get_db():
        raise RuntimeError("DB connection failed")

    monkeypatch.setattr(system_config, "get_dkstock_regime_enabled", fake_get_db)
    client = _make_client(enabled_ctor=True)

    # .env=True → True 로 fallback (예외 흡수)
    enabled = await client._check_enabled_async()
    assert enabled is True
