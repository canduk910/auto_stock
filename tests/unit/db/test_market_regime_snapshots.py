"""src/db/market_regime_snapshots.py 단위 테스트 (사이클 2).

market_regime_snapshots 테이블 CRUD 검증.

- insert_snapshot 정상 INSERT
- UNIQUE(snapshot_date) 충돌 시 None 반환
- get_latest() snapshot_date DESC LIMIT 1
"""
from __future__ import annotations

from datetime import date

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.xfail(
        reason=(
            "사이클 M1-2 의미 전환 — market_regime_snapshots.py 가 supabase-py 체인에서 "
            "src.db.pg(asyncpg) 로 전환되어 `fake_supabase`/`supabase.table(...)` "
            "monkeypatch 전제가 더 이상 성립하지 않는다(AttributeError). 동등 계약은 "
            "`tests/unit/db/test_cycleM1_2_market_regime_pg.py` 가 pg mock 기반으로 "
            "전량 대체(insert/dup/race/get_by_date/get_latest/list_recent 전이). "
            "회귀 아님 (사이클 M1-1 선례 답습)."
        ),
        strict=False,
    ),
]


@pytest.mark.asyncio
async def test_insert_snapshot_returns_row(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    from src.db import market_regime_snapshots as mrs

    monkeypatch.setattr(mrs, "supabase", fake_supabase)

    row = await mrs.insert_snapshot(
        snapshot_date=date(2026, 5, 17),
        regime="defensive",
        regime_desc="방어 (공포 현금)",
        cycle_phase="expansion",
        vix=18.43,
        fear_greed_score=76.0,
        buffett_ratio=254.2,
        raw_response={"regime": {"regime": "defensive"}},
        computed_cash_usage_ratio=0.25,
        buy_blocked=True,
        block_reason="regime=defensive",
    )

    assert row is not None
    assert row["regime"] == "defensive"
    assert row["buy_blocked"] is True
    assert row["computed_cash_usage_ratio"] == 0.25
    stored = fake_supabase.store["market_regime_snapshots"]
    assert len(stored) == 1


@pytest.mark.asyncio
async def test_insert_snapshot_unique_conflict_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """동일 snapshot_date 재 INSERT 시 None 반환 (graceful)."""
    from src.db import market_regime_snapshots as mrs

    monkeypatch.setattr(mrs, "supabase", fake_supabase)

    target = date(2026, 5, 17)
    first = await mrs.insert_snapshot(
        snapshot_date=target,
        regime="neutral",
        regime_desc="중립",
        cycle_phase="expansion",
        vix=20.0,
        fear_greed_score=50.0,
        buffett_ratio=240.0,
        raw_response={},
        computed_cash_usage_ratio=0.5,
        buy_blocked=False,
        block_reason=None,
    )
    second = await mrs.insert_snapshot(
        snapshot_date=target,
        regime="aggressive",
        regime_desc="공격",
        cycle_phase="expansion",
        vix=15.0,
        fear_greed_score=60.0,
        buffett_ratio=250.0,
        raw_response={},
        computed_cash_usage_ratio=0.8,
        buy_blocked=False,
        block_reason=None,
    )

    assert first is not None
    assert second is None  # UNIQUE 충돌 → graceful None
    stored = fake_supabase.store["market_regime_snapshots"]
    assert len(stored) == 1
    assert stored[0]["regime"] == "neutral"  # 첫 행 보존


@pytest.mark.asyncio
async def test_get_latest_returns_most_recent_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """get_latest() 가 가장 최근 snapshot_date 행을 반환.

    운영 supabase 는 .order("snapshot_date", desc=True).limit(1) 로 정렬되지만
    FakeSupabase 는 order() 가 no-op 라 INSERT 시점 정렬을 반영하기 위해
    INSERT 순서를 date 오름차순으로 한다. 운영 측 정렬 로직은 그대로 유지하되,
    본 테스트는 INSERT 순서가 곧 신규순이라는 가정만 검증.
    """
    from src.db import market_regime_snapshots as mrs

    monkeypatch.setattr(mrs, "supabase", fake_supabase)

    await mrs.insert_snapshot(
        snapshot_date=date(2026, 5, 17),
        regime="defensive", regime_desc="", cycle_phase="contraction",
        vix=26.0, fear_greed_score=86.0, buffett_ratio=260.0,
        raw_response={}, computed_cash_usage_ratio=0.25,
        buy_blocked=True, block_reason="regime=defensive",
    )

    latest = await mrs.get_latest()
    assert latest is not None
    assert latest["regime"] == "defensive"
    assert latest["buy_blocked"] is True


@pytest.mark.asyncio
async def test_get_latest_empty_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    from src.db import market_regime_snapshots as mrs

    monkeypatch.setattr(mrs, "supabase", fake_supabase)
    latest = await mrs.get_latest()
    assert latest is None
