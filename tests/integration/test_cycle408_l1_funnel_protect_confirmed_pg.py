"""cycle408-L1 Red — 실 Postgres 왕복: `protect_confirmed=True` 는 기존 확정 행을 덮지 않는다.

명세 = `_workspace/refactor/2026-10-04_eight_area_observability_fixes.md` L1 절 (4) R1.
SQL 조각·호출자 계약은 `tests/unit/engine/test_cycle408_l1_funnel_protect_confirmed.py`.
기본값(보호 꺼짐)의 확정→확정 덮어쓰기는 `test_cycle364_funnel_protect_confirmed_pg.py::
test_c364_pg_3b_4` 가 계속 잰다.

🔴 벽시계 의존 금지 — 행 시각은 INSERT 뒤 직접 `UPDATE … SET snapshot_at` 으로 고정(cycle350 관례).
docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 skip (CI 가 돌린다).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_KST = timezone(timedelta(hours=9))
_D = date(2026, 9, 29)
_SID = "vcp_breakout"


async def _write(*, is_provisional: bool, survived, protect_confirmed: bool | None = None):
    from src.db.strategy_funnel import insert_snapshot

    extra = {} if protect_confirmed is None else {"protect_confirmed": protect_confirmed}
    return await insert_snapshot(
        target_date=_D, strategy_id=_SID, step_no=99, step_name="최종",
        survived_tickers=list(survived), is_provisional=is_provisional, **extra,
    )


async def _pin(pg, at: datetime):
    status = await pg.execute(
        "UPDATE strategy_funnel_snapshots SET snapshot_at = $1 "
        "WHERE target_date = $2 AND strategy_id = $3 AND step_no = 99",
        at, _D, _SID,
    )
    assert status == "UPDATE 1", status


async def _rows(pg):
    return await pg.fetch(
        "SELECT survived_tickers, survived_count, is_provisional, snapshot_at "
        "FROM strategy_funnel_snapshots WHERE target_date = $1 AND strategy_id = $2 AND step_no = 99",
        _D, _SID,
    )


@pytest.mark.asyncio
async def test_l1_pg_1_confirmed_over_confirmed_when_protected_then_rejected_row_unchanged(
    clean_strategy_funnel,
):
    """재기동한 날 자동 캡처(확정·보호)는 09:35 확정 행을 덮지 못한다."""
    pg = clean_strategy_funnel
    await _write(is_provisional=False, survived=("990101",))
    pinned = datetime(2026, 9, 29, 9, 35, tzinfo=_KST)
    await _pin(pg, pinned)

    out = await _write(is_provisional=False, survived=("990201", "990202"), protect_confirmed=True)
    assert out is None, "보호로 거부되면 None(RETURNING 0행) — 예외 아님"
    rows = await _rows(pg)
    assert len(rows) == 1
    assert rows[0]["survived_tickers"] == ["990101"], "확정 행 내용이 재기동 값으로 덮였다"
    assert rows[0]["survived_count"] == 1
    assert rows[0]["is_provisional"] is False
    assert rows[0]["snapshot_at"] == pinned, "거부된 쓰기가 snapshot_at 을 갱신했다"


@pytest.mark.asyncio
async def test_l1_pg_2_confirmed_over_provisional_when_protected_then_overwrites(clean_strategy_funnel):
    """09:35 정상 경로 — 전날 21:00 미리보기(잠정)는 보호 켠 확정 캡처가 교체한다."""
    pg = clean_strategy_funnel
    await _write(is_provisional=True, survived=("990101",))
    await _pin(pg, datetime(2026, 9, 28, 21, 1, tzinfo=_KST))
    out = await _write(is_provisional=False, survived=("990104",), protect_confirmed=True)
    assert out is not None
    rows = await _rows(pg)
    assert len(rows) == 1
    assert rows[0]["is_provisional"] is False and rows[0]["survived_tickers"] == ["990104"]


@pytest.mark.asyncio
async def test_l1_pg_3_no_row_when_protected_then_inserts(clean_strategy_funnel):
    """오전에 확정되지 못한 전략(빈 날)은 재기동 뒤 자동 캡처가 채운다."""
    pg = clean_strategy_funnel
    out = await _write(is_provisional=False, survived=("990105",), protect_confirmed=True)
    assert out is not None
    rows = await _rows(pg)
    assert len(rows) == 1 and rows[0]["survived_tickers"] == ["990105"]
    assert rows[0]["is_provisional"] is False


@pytest.mark.asyncio
async def test_l1_pg_4_confirmed_over_confirmed_when_default_then_still_overwrites(clean_strategy_funnel):
    """기본값(수동 trigger) 은 현행 그대로 덮는다 — 보호는 자동 캡처 한정."""
    pg = clean_strategy_funnel
    await _write(is_provisional=False, survived=("990101",))
    out = await _write(is_provisional=False, survived=("990106",), protect_confirmed=False)
    assert out is not None
    assert (await _rows(pg))[0]["survived_tickers"] == ["990106"]
