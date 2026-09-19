"""cycle316 — `set_cash_usage_ratio` 가 자금을 크게 줄일 때 소리를 낸다.

🔴 고치는 것 = 자금 비율이 **비교도 로그도 없이** 덮이던 것이다.
`scheduler._resolve_cash_usage_ratio` 는 레짐 계산값을 그대로 저장하는데,
그 함수 전체에 성공 경로 로그가 한 줄도 없어서 운영자는 예산이 4분의 1로 접힌 것을
「매수 수량 0 → 900s cooldown」 WARNING 으로만 만나게 된다(오귀인).

여기서 세우는 계약은 **행위가 아니라 관측**이다 — 저장은 그대로 하되,
직전 값 대비 큰 폭으로 줄면 WARNING 을 남긴다.
"""
from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_large_drop_emits_warning(monkeypatch, caplog):
    """1.00 → 0.25 처럼 크게 줄면 그 사실이 로그에 남는다."""
    from src.db import system_config

    async def _current(_key):
        return {"value": 1.0}

    saved = {}

    async def _upsert(key, value):
        saved[key] = value

    monkeypatch.setattr(system_config, "_select_value", _current)
    monkeypatch.setattr(system_config, "_upsert_value", _upsert)

    with caplog.at_level(logging.WARNING, logger="src.db.system_config"):
        await system_config.set_cash_usage_ratio(0.25)

    msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("[cash_usage_ratio]" in m and "0.25" in m and "1.0" in m for m in msgs), msgs
    # 🔴 관측이 저장을 막지 않는다
    assert saved["cash_usage_ratio"] == {"value": 0.25}


@pytest.mark.asyncio
async def test_small_change_is_quiet(monkeypatch, caplog):
    """운영자가 슬라이더를 한두 칸 움직이는 것은 소음이 아니다."""
    from src.db import system_config

    async def _current(_key):
        return {"value": 1.0}

    async def _upsert(key, value):
        return None

    monkeypatch.setattr(system_config, "_select_value", _current)
    monkeypatch.setattr(system_config, "_upsert_value", _upsert)

    with caplog.at_level(logging.WARNING, logger="src.db.system_config"):
        await system_config.set_cash_usage_ratio(0.90)

    msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert not any("[cash_usage_ratio]" in m for m in msgs), msgs


@pytest.mark.asyncio
async def test_observation_failure_never_blocks_save(monkeypatch):
    """직전 값 조회가 실패해도 저장은 된다 — 관측이 행위를 막으면 안 된다."""
    from src.db import system_config

    async def _boom(_key):
        raise RuntimeError("db down")

    saved = {}

    async def _upsert(key, value):
        saved[key] = value

    monkeypatch.setattr(system_config, "_select_value", _boom)
    monkeypatch.setattr(system_config, "_upsert_value", _upsert)

    await system_config.set_cash_usage_ratio(0.25)
    assert saved["cash_usage_ratio"] == {"value": 0.25}
