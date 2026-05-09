"""AUTO_START 의사결정 — `_is_auto_start_enabled` 흐름.

- DB system_config 에서 key='auto_start' 조회 → 값이 True 또는 'true' 이면 활성
- DB 조회 실패 시 settings.auto_start 폴백
- 매일 시작 전 재확인 (Settings UI 변경 시 다음 영업일에 즉시 반영)
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.integration


def _patch_supabase(monkeypatch, *, value=None, raise_exc=None):
    """src.db.supabase.supabase 를 가짜로 치환."""
    if raise_exc is not None:
        class _Boom:
            def table(self, *a, **kw):
                raise raise_exc

        import src.db.supabase as supabase_mod
        monkeypatch.setattr(supabase_mod, "supabase", _Boom())
        return

    captured = SimpleNamespace(filters=[])

    class _Result:
        def __init__(self, data):
            self.data = data

    class _Query:
        def __init__(self, data):
            self._data = data

        def select(self, *_):
            return self

        def eq(self, *_args):
            return self

        def execute(self):
            return _Result([{"value": self._data}] if self._data is not None else [])

    class _Table:
        def __init__(self, value):
            self._value = value

        def table(self, name):
            captured.filters.append(name)
            return _Query(self._value)

    import src.db.supabase as supabase_mod
    monkeypatch.setattr(supabase_mod, "supabase", _Table(value))
    return captured


@pytest.mark.asyncio
async def test_auto_start_when_db_value_true_then_enabled(scheduler_env):
    sched = scheduler_env.scheduler
    _patch_supabase(scheduler_env.monkeypatch, value=True)

    assert await sched._is_auto_start_enabled() is True


@pytest.mark.asyncio
async def test_auto_start_when_db_value_string_true_then_enabled(scheduler_env):
    """DB 가 string 'true' 로 저장한 경우도 인식."""
    sched = scheduler_env.scheduler
    _patch_supabase(scheduler_env.monkeypatch, value="true")

    assert await sched._is_auto_start_enabled() is True


@pytest.mark.asyncio
async def test_auto_start_when_db_value_false_then_disabled(scheduler_env):
    sched = scheduler_env.scheduler
    _patch_supabase(scheduler_env.monkeypatch, value=False)

    assert await sched._is_auto_start_enabled() is False


@pytest.mark.asyncio
async def test_auto_start_when_db_empty_then_disabled(scheduler_env):
    """DB 에 row 가 없으면 False 로 해석."""
    sched = scheduler_env.scheduler
    _patch_supabase(scheduler_env.monkeypatch, value=None)

    assert await sched._is_auto_start_enabled() is False


@pytest.mark.asyncio
async def test_auto_start_falls_back_to_settings_when_db_raises(scheduler_env, monkeypatch):
    """DB 조회 실패 시 settings.auto_start 폴백."""
    sched = scheduler_env.scheduler
    _patch_supabase(scheduler_env.monkeypatch, raise_exc=RuntimeError("DB unavailable"))

    # settings.auto_start = True 로 패치 후 폴백 동작 검증
    from src.config import settings
    monkeypatch.setattr(settings, "auto_start", True)

    assert await sched._is_auto_start_enabled() is True
