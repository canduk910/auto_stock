"""cycle364 S1 Red — 실 Postgres 왕복: ③-b 확정 행 보호 + OPS 저녁 증거(미래 날짜 잠정 행).

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §2.6 · §6.2 ③-b · OPS · M7 · M12.
SQL 문구·반환 전파는 `tests/unit/db/test_cycle364_funnel_protect_confirmed.py` ·
`tests/unit/routes/test_cycle364_market_ops_evening_preview.py` 가 로컬에서도 잰다.

🔴 벽시계 의존 금지 — 행 시각은 INSERT 뒤 테스트 DB 에 직접 `UPDATE … SET snapshot_at` 으로
고정한다(cycle350 관례). 「덮어쓰기 시 snapshot_at = DB now()」 는 같은 DB 의 `SELECT now()`
로 앞뒤를 잰다.

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip` (CI 가 돌린다).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_KST = timezone(timedelta(hours=9))
_D = date(2026, 9, 22)
_D_NEXT = date(2026, 9, 23)
_SID = "vcp_breakout"


def _kst(d: date, hh: int, mm: int, ss: int = 0, us: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, ss, us, tzinfo=_KST)


async def _write(*, is_provisional: bool, survived=("990101",), target_date: date = _D,
                 strategy_id: str = _SID, step_no: int = 99):
    from src.db.strategy_funnel import insert_snapshot

    return await insert_snapshot(
        target_date=target_date, strategy_id=strategy_id, step_no=step_no,
        step_name="최종", survived_tickers=list(survived), is_provisional=is_provisional,
    )


async def _pin(pg, at: datetime, *, target_date: date = _D, strategy_id: str = _SID, step_no: int = 99):
    status = await pg.execute(
        "UPDATE strategy_funnel_snapshots SET snapshot_at = $1 "
        "WHERE target_date = $2 AND strategy_id = $3 AND step_no = $4",
        at, target_date, strategy_id, step_no,
    )
    assert status == "UPDATE 1", status


async def _row(pg, *, target_date: date = _D, strategy_id: str = _SID, step_no: int = 99):
    rows = await pg.fetch(
        "SELECT survived_tickers, is_provisional, snapshot_at FROM strategy_funnel_snapshots "
        "WHERE target_date = $1 AND strategy_id = $2 AND step_no = $3",
        target_date, strategy_id, step_no,
    )
    assert len(rows) == 1, len(rows)
    return rows[0]


async def _combined(pg, d: date = _D) -> dict:
    from src.db._kst import to_date
    from src.routes.market_ops import _COMBINED_SQL, _funnel_evidence_floor

    return await pg.fetchrow(_COMBINED_SQL, to_date(d), _funnel_evidence_floor(d))


# ══════════════════════════════════════════════════════════════════════
# ③-b — 확정 행 보호 (4방향)
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_c364_pg_3b_1_provisional_over_confirmed_when_written_then_rejected_row_unchanged(
    clean_strategy_funnel,
):
    """09:35 확정 행을 장중 재기동 +600초 캡처(잠정)가 덮지 못한다 (M7)."""
    pg = clean_strategy_funnel
    await _write(is_provisional=False, survived=("990101",))
    pinned = _kst(_D, 9, 35)
    await _pin(pg, pinned)

    out = await _write(is_provisional=True, survived=("990102", "990103"))
    assert out is None, "거부된 잠정 쓰기는 None(RETURNING 0행) — 예외 아님"
    row = await _row(pg)
    assert row["is_provisional"] is False, "확정 행이 잠정으로 바뀌었다 (M7)"
    assert row["survived_tickers"] == ["990101"], "확정 행 내용이 덮였다 (M7)"
    assert row["snapshot_at"] == pinned, "거부된 쓰기가 snapshot_at 을 갱신했다"


@pytest.mark.asyncio
async def test_c364_pg_3b_2_confirmed_over_provisional_when_written_then_overwrites(clean_strategy_funnel):
    """다음 날 09:30 확정 캡처가 전날 저녁 A1 잠정 행(target_date=그날)을 덮는다 — 정상 경로."""
    pg = clean_strategy_funnel
    await _write(is_provisional=True, survived=("990101",))
    await _pin(pg, _kst(_D - timedelta(days=1), 21, 1))
    out = await _write(is_provisional=False, survived=("990104",))
    assert out is not None
    row = await _row(pg)
    assert row["is_provisional"] is False and row["survived_tickers"] == ["990104"]


@pytest.mark.asyncio
async def test_c364_pg_3b_3_provisional_over_provisional_when_written_then_overwrites_and_refreshes_at(
    clean_strategy_funnel,
):
    pg = clean_strategy_funnel
    await _write(is_provisional=True, survived=("990101",))
    await _pin(pg, _kst(_D, 7, 57))
    t0 = await pg.fetchval("SELECT now()")
    out = await _write(is_provisional=True, survived=("990105",))
    t1 = await pg.fetchval("SELECT now()")
    assert out is not None
    row = await _row(pg)
    assert row["survived_tickers"] == ["990105"] and t0 <= row["snapshot_at"] <= t1


@pytest.mark.asyncio
async def test_c364_pg_3b_4_confirmed_over_confirmed_when_written_then_overwrites(clean_strategy_funnel):
    """수동 캡처(확정)를 같은 날 다시 누르면 덮는다 — 보호는 잠정→확정 방향만."""
    pg = clean_strategy_funnel
    await _write(is_provisional=False, survived=("990101",))
    out = await _write(is_provisional=False, survived=("990106",))
    assert out is not None
    assert (await _row(pg))["survived_tickers"] == ["990106"]


# ══════════════════════════════════════════════════════════════════════
# OPS — 저녁 증거 = 오늘 저녁(하한 19:00 이후)에 쓴 **다음 세션** 잠정 행
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_c364_pg_ops_1_next_session_provisional_row_when_after_floor_then_counted(clean_strategy_funnel):
    pg = clean_strategy_funnel
    await _write(is_provisional=True, target_date=_D_NEXT)
    await _pin(pg, _kst(_D, 21, 1, 7), target_date=_D_NEXT)
    row = await _combined(pg, _D)
    assert row["funnel_rows"] == 1, "A1 저녁 행(target_date=다음 거래일)이 저녁 증거로 안 셈해졌다 (M12)"
    assert row["funnel_last_at"] == "2026-09-22T21:01:07+09:00"


@pytest.mark.asyncio
async def test_c364_pg_ops_2_today_date_provisional_row_when_evening_then_not_evidence(clean_strategy_funnel):
    """오늘 날짜 잠정 행(아침 +600초 캡처·거래일 비상 as_of=오늘)은 21:0x 에 써도 저녁 증거가 아니다."""
    pg = clean_strategy_funnel
    await _write(is_provisional=True, target_date=_D)
    await _pin(pg, _kst(_D, 21, 1), target_date=_D)
    assert (await _combined(pg, _D))["funnel_rows"] == 0


@pytest.mark.asyncio
async def test_c364_pg_ops_3_floor_when_1900_boundary_then_inclusive(clean_strategy_funnel):
    """하한 = 21:00 − 2h = 19:00 (`>=`). 1µs 전은 안 센다."""
    pg = clean_strategy_funnel
    await _write(is_provisional=True, target_date=_D_NEXT)
    await _pin(pg, _kst(_D, 19, 0), target_date=_D_NEXT)
    assert (await _combined(pg, _D))["funnel_rows"] == 1
    await _pin(pg, _kst(_D, 18, 59, 59, 999_999), target_date=_D_NEXT)
    assert (await _combined(pg, _D))["funnel_rows"] == 0


@pytest.mark.asyncio
async def test_c364_pg_ops_4_route_when_next_session_row_written_then_done(
    clean_strategy_funnel, clean_system_config, clean_log_reports,
    clean_daily_performance, clean_parameter_recommendations,
):
    import src.routes.market_ops as mo

    pg = clean_strategy_funnel
    await _write(is_provisional=True, target_date=_D_NEXT)
    await _pin(pg, _kst(_D, 21, 1), target_date=_D_NEXT)
    frozen = _kst(_D, 22, 0)

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    orig = mo.datetime
    mo.datetime = _Frozen
    try:
        with patch.object(mo, "_resolve_trading_day", AsyncMock(return_value=(True, "kis"))):
            data = (await mo.read_market_ops()).data
    finally:
        mo.datetime = orig
    assert data["evidence_errors"] == []
    row = {t["id"]: t for t in data["tasks"]}["evening_funnel_capture"]
    assert row["status"] == "done" and row["evidence"] == {"snapshot_rows_today": 1}
