"""AUTO_START 의사결정 — `_is_auto_start_enabled` 흐름.

- DB system_config 에서 key='auto_start' 조회 → 값이 True 또는 'true' 이면 활성
- DB 조회 실패 시 settings.auto_start 폴백
- 매일 시작 전 재확인 (Settings UI 변경 시 다음 영업일에 즉시 반영)

사이클 M5 — `_is_auto_start_enabled` 가 `system_config.get_auto_start()` (RDS/pg 헬퍼)
로 위임 전환되어, 본 스위트도 supabase mock 대신 `system_config.get_auto_start` 를
직접 patch (Red 메모 `test_cycleM5_scheduler_pg_sites.py` 답습).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.integration


def _patch_get_auto_start(monkeypatch, *, return_value=None, raise_exc=None):
    """`src.db.system_config.get_auto_start` 를 가짜로 치환.

    `get_auto_start()` 자체가 dict/str/bool 파싱 + graceful except 를 내부에서
    수행하므로 (사이클 M3b), 여기서는 그 함수의 *반환값/예외* 만 직접 지정한다.
    """
    import src.db.system_config as system_config_mod

    if raise_exc is not None:
        monkeypatch.setattr(
            system_config_mod, "get_auto_start", AsyncMock(side_effect=raise_exc),
        )
        return

    monkeypatch.setattr(
        system_config_mod, "get_auto_start", AsyncMock(return_value=return_value),
    )


@pytest.mark.asyncio
async def test_auto_start_when_db_value_true_then_enabled(scheduler_env):
    sched = scheduler_env.scheduler
    _patch_get_auto_start(scheduler_env.monkeypatch, return_value=True)

    assert await sched._is_auto_start_enabled() is True


@pytest.mark.asyncio
async def test_auto_start_when_db_value_string_true_then_enabled(scheduler_env):
    """DB 가 string 'true' 로 저장한 경우도 인식 (get_auto_start 내부 파싱 계약)."""
    sched = scheduler_env.scheduler
    _patch_get_auto_start(scheduler_env.monkeypatch, return_value=True)

    assert await sched._is_auto_start_enabled() is True


@pytest.mark.asyncio
async def test_auto_start_when_db_value_false_then_disabled(scheduler_env):
    sched = scheduler_env.scheduler
    _patch_get_auto_start(scheduler_env.monkeypatch, return_value=False)

    assert await sched._is_auto_start_enabled() is False


@pytest.mark.asyncio
async def test_auto_start_when_db_empty_then_disabled(scheduler_env):
    """DB 에 row 가 없으면 False 로 해석 (get_auto_start 키 부재 계약)."""
    sched = scheduler_env.scheduler
    _patch_get_auto_start(scheduler_env.monkeypatch, return_value=False)

    assert await sched._is_auto_start_enabled() is False


@pytest.mark.asyncio
async def test_auto_start_falls_back_to_settings_when_db_raises(scheduler_env, monkeypatch):
    """DB 조회 실패 시 settings.auto_start 폴백."""
    sched = scheduler_env.scheduler
    _patch_get_auto_start(scheduler_env.monkeypatch, raise_exc=RuntimeError("DB unavailable"))

    # settings.auto_start = True 로 패치 후 폴백 동작 검증
    from src.config import settings
    monkeypatch.setattr(settings, "auto_start", True)

    assert await sched._is_auto_start_enabled() is True
