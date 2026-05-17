"""사이클 5 (2026-05-17) Red — BacktestEngine.enabled DB 우선 / .env fallback.

기존: `BacktestEngine.enabled` 가 ctor 시점 settings.kis_mcp_enabled 만 참조 → 운영 중 토글 불가.

신규:
1. `is_enabled_async() -> bool` 신규 메서드 — DB 값 우선, None 시 .env fallback.
2. `enabled` 프로퍼티는 호환성 유지 (sync 접근, 기존 호출자 그대로 — `_engine_instance` 의 `_enabled` 반환). 하지만 핵심 API(`run_for_strategy`/`poll`/`wait_for_result`) 는 `is_enabled_async()` 로 가드.
3. DB 값 갱신 → 다음 API 호출에서 즉시 반영.

테스트 더블:
- `src.db.system_config.get_kis_mcp_enabled` monkeypatch.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _make_engine(enabled_ctor: bool = False):
    from src.engine.backtest_engine import BacktestEngine

    class _FakeClient:
        async def call_tool(self, name, params):
            return {}

    return BacktestEngine(client=_FakeClient(), enabled=enabled_ctor)


@pytest.mark.asyncio
async def test_db_true_overrides_env_false(monkeypatch: pytest.MonkeyPatch):
    from src.db import system_config

    async def fake_get_db():
        return True

    monkeypatch.setattr(system_config, "get_kis_mcp_enabled", fake_get_db)
    engine = _make_engine(enabled_ctor=False)

    assert await engine.is_enabled_async() is True


@pytest.mark.asyncio
async def test_db_false_overrides_env_true(monkeypatch: pytest.MonkeyPatch):
    from src.db import system_config

    async def fake_get_db():
        return False

    monkeypatch.setattr(system_config, "get_kis_mcp_enabled", fake_get_db)
    engine = _make_engine(enabled_ctor=True)

    assert await engine.is_enabled_async() is False


@pytest.mark.asyncio
async def test_db_none_falls_back_to_env(monkeypatch: pytest.MonkeyPatch):
    from src.db import system_config

    async def fake_get_db():
        return None

    monkeypatch.setattr(system_config, "get_kis_mcp_enabled", fake_get_db)
    engine_enabled_env = _make_engine(enabled_ctor=True)
    engine_disabled_env = _make_engine(enabled_ctor=False)

    assert await engine_enabled_env.is_enabled_async() is True
    assert await engine_disabled_env.is_enabled_async() is False


@pytest.mark.asyncio
async def test_run_for_strategy_uses_db_toggle(monkeypatch: pytest.MonkeyPatch):
    """run_for_strategy 가 ctor _enabled 가 아닌 is_enabled_async() 결과로 가드."""
    from src.db import system_config
    from src.services.exceptions import ConfigError

    # ctor 시점엔 True 였지만 DB 가 False → ConfigError 기대.
    async def fake_get_db():
        return False

    monkeypatch.setattr(system_config, "get_kis_mcp_enabled", fake_get_db)
    engine = _make_engine(enabled_ctor=True)

    with pytest.raises(ConfigError):
        await engine.run_for_strategy("momentum", {})


@pytest.mark.asyncio
async def test_run_for_strategy_allowed_when_db_true(monkeypatch: pytest.MonkeyPatch):
    """ctor _enabled=False 였어도 DB=True 면 호출 진행 (이후 단계는 외부 mock 응답)."""
    from src.db import system_config

    async def fake_get_db():
        return True

    monkeypatch.setattr(system_config, "get_kis_mcp_enabled", fake_get_db)

    from src.engine.backtest_engine import BacktestEngine

    class _FakeClient:
        async def call_tool(self, name, params):
            if name == "validate_yaml_tool":
                return {"data": {"valid": True}}
            if name == "run_backtest_tool":
                return {"data": {"job_id": "j1"}}
            return {}

    engine = BacktestEngine(client=_FakeClient(), enabled=False)
    # ConfigError 가 발생하지 않아야 함 (DB=True 가 .env=False 를 덮어씀)
    job_id = await engine.run_for_strategy("momentum", {})
    assert job_id == "j1"


@pytest.mark.asyncio
async def test_db_exception_falls_back_to_env(monkeypatch: pytest.MonkeyPatch):
    from src.db import system_config

    async def fake_get_db():
        raise RuntimeError("DB error")

    monkeypatch.setattr(system_config, "get_kis_mcp_enabled", fake_get_db)
    engine = _make_engine(enabled_ctor=True)

    assert await engine.is_enabled_async() is True
