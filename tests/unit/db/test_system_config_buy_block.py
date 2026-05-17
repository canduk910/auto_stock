"""사이클 8 (2026-05-18) Red — `src/db/system_config.py` 매수 가드 4 모드 헬퍼.

요구 행위:
1. `get_buy_block_mode()` — 키 부재 시 기본 'HARD' 반환 (기존 동작 회귀 보존).
2. `set_buy_block_mode(mode)` — 4 모드(OFF/WARN/SOFT/HARD) 외 ValueError.
3. `get_buy_block_thresholds()` — Pydantic `BuyBlockThresholds`. 기본 25.0/85.0/15.0/True.
4. `set_buy_block_thresholds(vix=..., fg_high=..., fg_low=..., defensive_enabled=...)` — 부분 갱신.

기존 cash_usage_ratio(기본 1.0) / auto_regime_adjust(기본 True) 패턴 답습.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Mode (8-1) — 기본 'HARD'
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_buy_block_mode_missing_returns_hard(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """키 부재 시 기본 'HARD' 반환 — 현재 동작 회귀 보존."""
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)
    value = await system_config.get_buy_block_mode()
    assert value == "HARD"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["OFF", "WARN", "SOFT", "HARD"])
async def test_set_buy_block_mode_valid_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
    mode: str,
):
    """4 모드 정상 저장 + 재조회 일치."""
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)
    await system_config.set_buy_block_mode(mode)
    assert await system_config.get_buy_block_mode() == mode


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["INVALID", "off", "soft", "", "hard ", "STRICT", None, 0])
async def test_set_buy_block_mode_invalid_raises(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
    bad,
):
    """4 모드 외 값은 ValueError."""
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)
    with pytest.raises(ValueError):
        await system_config.set_buy_block_mode(bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Thresholds (8-2) — 기본값 + 부분 갱신
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_buy_block_thresholds_missing_returns_defaults(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """4 키 부재 시 기본값 — vix=25.0, fg_high=85.0, fg_low=15.0, defensive_enabled=True."""
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)
    t = await system_config.get_buy_block_thresholds()
    assert t.vix_threshold == 25.0
    assert t.fg_high_threshold == 85.0
    assert t.fg_low_threshold == 15.0
    assert t.defensive_enabled is True


@pytest.mark.asyncio
async def test_set_buy_block_thresholds_partial_update(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """부분 갱신 가능 — vix 만 변경하면 나머지는 기본값 유지."""
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)
    await system_config.set_buy_block_thresholds(vix_threshold=30.0)
    t = await system_config.get_buy_block_thresholds()
    assert t.vix_threshold == 30.0
    assert t.fg_high_threshold == 85.0  # 기본 유지
    assert t.fg_low_threshold == 15.0
    assert t.defensive_enabled is True


@pytest.mark.asyncio
async def test_set_buy_block_thresholds_full_update_and_persist(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """4 키 모두 갱신 후 재조회 일치."""
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)
    await system_config.set_buy_block_thresholds(
        vix_threshold=20.0,
        fg_high_threshold=90.0,
        fg_low_threshold=10.0,
        defensive_enabled=False,
    )
    t = await system_config.get_buy_block_thresholds()
    assert t.vix_threshold == 20.0
    assert t.fg_high_threshold == 90.0
    assert t.fg_low_threshold == 10.0
    assert t.defensive_enabled is False


@pytest.mark.asyncio
async def test_set_buy_block_thresholds_defensive_only_toggle(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """defensive_enabled 단독 토글 — 5/17 사용자 케이스(regime 가드만 끄기)."""
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)
    await system_config.set_buy_block_thresholds(defensive_enabled=False)
    t = await system_config.get_buy_block_thresholds()
    assert t.defensive_enabled is False
    # 다른 임계는 기본 유지
    assert t.vix_threshold == 25.0
    assert t.fg_high_threshold == 85.0
    assert t.fg_low_threshold == 15.0
