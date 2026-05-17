"""Phase J3 Red — `src/db/system_config.py::get/set_cash_usage_ratio`.

총 가용금액 게이지. system_config 테이블 키 `cash_usage_ratio`, 값 `{"value": float}`.

요구 행위:
1. `get_cash_usage_ratio()` — 키 부재 시 기본 1.0 반환.
2. `set_cash_usage_ratio(ratio)` — [0.5, 1.0] 범위 외 → ValueError.
3. `set_cash_usage_ratio(ratio)` — 5% 단위로 round 보정 (0.83 → 0.85, 0.87 → 0.85, 0.825 → 0.80, 0.875 → 0.90).
4. upsert + 재조회 round-trip.

테스트 더블:
- `src.db.system_config.supabase` 를 `FakeSupabase` 로 monkeypatch.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_get_cash_usage_ratio_when_missing_then_default_1(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    ratio = await system_config.get_cash_usage_ratio()
    assert ratio == 1.0


@pytest.mark.asyncio
async def test_set_then_get_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    await system_config.set_cash_usage_ratio(0.80)
    assert await system_config.get_cash_usage_ratio() == pytest.approx(0.80)

    await system_config.set_cash_usage_ratio(0.50)
    assert await system_config.get_cash_usage_ratio() == pytest.approx(0.50)


@pytest.mark.asyncio
async def test_set_below_zero_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """사이클 2 (2026-05-17): 범위 [0.0, 1.0] 확장 — 0.0 미만만 거부.

    이전엔 0.5 미만 거부였으나 레짐 자동 조정으로 0.25(defensive) 같은 값이
    정상 입력될 수 있어 MIN=0.0 으로 확장. 음수는 여전히 거부.
    """
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    with pytest.raises(ValueError):
        await system_config.set_cash_usage_ratio(-0.1)


@pytest.mark.asyncio
async def test_set_above_1_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    with pytest.raises(ValueError):
        await system_config.set_cash_usage_ratio(1.01)


@pytest.mark.asyncio
async def test_cycle2_low_values_accepted(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """사이클 2 (2026-05-17): 0.0 / 0.25 / 0.5 모두 정상 통과 (defensive 레짐 수용)."""
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    await system_config.set_cash_usage_ratio(0.0)
    assert await system_config.get_cash_usage_ratio() == pytest.approx(0.0)

    await system_config.set_cash_usage_ratio(0.25)
    assert await system_config.get_cash_usage_ratio() == pytest.approx(0.25)

    await system_config.set_cash_usage_ratio(0.45)
    assert await system_config.get_cash_usage_ratio() == pytest.approx(0.45)


@pytest.mark.asyncio
async def test_set_rounds_to_5_percent_steps(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """5% 단위 자동 보정 (운영자 실수 방지).

    0.83 → 0.85 (round)
    0.87 → 0.85
    0.825 → 0.80 (banker's rounding 영향 없게 입력)
    0.875 → 0.90
    """
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    await system_config.set_cash_usage_ratio(0.83)
    assert await system_config.get_cash_usage_ratio() == pytest.approx(0.85)

    await system_config.set_cash_usage_ratio(0.87)
    assert await system_config.get_cash_usage_ratio() == pytest.approx(0.85)

    await system_config.set_cash_usage_ratio(0.82)
    assert await system_config.get_cash_usage_ratio() == pytest.approx(0.80)

    await system_config.set_cash_usage_ratio(0.88)
    assert await system_config.get_cash_usage_ratio() == pytest.approx(0.90)


@pytest.mark.asyncio
async def test_set_boundary_values_accepted(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """경계값 0.5 / 1.0 정상 통과."""
    from src.db import system_config

    monkeypatch.setattr(system_config, "supabase", fake_supabase)

    await system_config.set_cash_usage_ratio(0.5)
    assert await system_config.get_cash_usage_ratio() == pytest.approx(0.5)

    await system_config.set_cash_usage_ratio(1.0)
    assert await system_config.get_cash_usage_ratio() == pytest.approx(1.0)
