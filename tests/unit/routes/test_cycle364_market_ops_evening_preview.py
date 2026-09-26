"""cycle364 S1 Red — OPS: `GET /api/market-ops` 저녁 funnel 행 = 「오늘 저녁에 쓴 다음 세션 행」.

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §2.6 · §6.2 OPS · M12.
실 PG 의미는 `tests/integration/test_cycle364_funnel_protect_confirmed_pg.py` 의 OPS 절.

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 계약 (`src/routes/market_ops.py`)
────────────────────────────────────────────────────────────────────────────
- `_COMBINED_SQL` 의 `funnel_rows` = `target_date > $1 AND is_provisional = TRUE AND
  snapshot_at >= $2` — 저녁 증거 = 미래 날짜 잠정 행. 오늘 날짜 잠정 행(아침 캡처·비상)은
  자연히 빠진다. `funnel_last_at` 무변경(전체 기간 최댓값).
- 하한 = `_funnel_evidence_floor(today)` 공식 그대로 → 21:00 − 2시간 = **19:00 KST**.
- evidence 키 `snapshot_rows_today` 는 계약이라 이름 유지(뜻 = 오늘 저녁에 쓴 다음 세션 행).
- 행 순서: 저녁 funnel 행을 「일봉 적재(20:30)」 바로 뒤 · 「정산(21:30)」 앞으로.
- `scheduled_at` = `_hms(TIME_EVENING_FUNNEL_CAPTURE)` = "21:00".

Red 유효성: 현행 SQL 은 `target_date = $1`, 행은 3번째, scheduled_at "16:20", 하한 14:20.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_D = date(2026, 9, 22)

_IDLE_PROGRESS = {
    "status": "idle", "total": 0, "processed": 0, "updated": 0, "skipped": 0,
    "failed": 0, "started_at": None, "finished_at": None, "elapsed_ms": 0,
    "error_message": None,
}
_EMPTY_COMBINED = {
    "rec_rows": 0, "rec_last_at": None, "perf_rows": 0, "daily_head": None,
    "daily_today_rows": 0, "daily_tail": None, "funnel_rows": 0,
    "funnel_last_at": None, "sm_refreshed_last": None, "sm_master_last": None,
}


def _funnel_subqueries(sql: str) -> dict[str, str]:
    flat = re.sub(r"\s+", " ", sql)
    return {alias: body for body, alias in re.findall(r"\(SELECT (.*?)\) AS (\w+)", flat)}


@pytest.fixture
def mo(monkeypatch):
    import src.routes.market_ops as _mo

    monkeypatch.setattr(_mo, "_resolve_trading_day", AsyncMock(return_value=(True, "kis")))
    monkeypatch.setattr(_mo.system_config, "get_task_last_success_bulk", AsyncMock(return_value={}))
    monkeypatch.setattr(
        _mo.refresh_progress, "get_all_progress",
        lambda: {k: dict(_IDLE_PROGRESS) for k in ("universe", "basics", "daily", "master", "financial")},
    )
    monkeypatch.setattr(_mo.pg, "fetchrow", AsyncMock(return_value=dict(_EMPTY_COMBINED)))
    monkeypatch.setattr(_mo, "get_log_report", AsyncMock(return_value=None))
    monkeypatch.setattr(_mo.trading_scheduler, "_running", False, raising=False)
    monkeypatch.setattr(_mo.trading_scheduler, "_phase", "idle", raising=False)
    return _mo


async def _at(mo, monkeypatch, moment: datetime, combined: dict | None = None) -> dict:
    if combined is not None:
        monkeypatch.setattr(mo.pg, "fetchrow", AsyncMock(return_value=combined))
    frozen = moment

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr(mo, "datetime", _Frozen)
    return (await mo.read_market_ops()).data


def test_ops_1_funnel_rows_when_counted_then_future_date_provisional_after_floor():
    """M12 — `target_date > $1`. `= $1` 이면 A1 의 다음 세션 행이 증거가 못 되고 아침 캡처
    (오늘 날짜 잠정)가 다시 증거가 된다."""
    import src.routes.market_ops as mo

    body = _funnel_subqueries(mo._COMBINED_SQL).get("funnel_rows")
    assert body is not None
    assert re.search(r"\btarget_date\s*>\s*\$1\b", body), (
        f"funnel_rows 가 `target_date > $1` 이 아니다 (Red — cycle364 §2.6 / M12): {body}"
    )
    assert not re.search(r"\btarget_date\s*=\s*\$1\b", body), f"오늘 날짜 조건이 남았다: {body}"
    assert "is_provisional = TRUE" in body and re.search(r"\bsnapshot_at\s*>=\s*\$2\b", body), body


def test_ops_2_funnel_last_at_when_read_then_unchanged_all_time_max():
    import src.routes.market_ops as mo

    body = _funnel_subqueries(mo._COMBINED_SQL).get("funnel_last_at")
    assert body is not None and "is_provisional = TRUE" in body
    assert "$1" not in body and "$2" not in body and "target_date" not in body, body


def test_ops_3_floor_when_capture_at_2100_then_1900_kst():
    import src.routes.market_ops as mo

    assert mo._funnel_evidence_floor(_D) == datetime(2026, 9, 22, 19, 0, tzinfo=_KST), (
        f"하한 = 21:00 − 2h = 19:00 (실측 {mo._funnel_evidence_floor(_D)!r})"
    )


async def test_ops_4_row_when_listed_then_between_daily_load_and_settlement(mo, monkeypatch):
    data = await _at(mo, monkeypatch, datetime(2026, 9, 22, 22, 0, tzinfo=_KST))
    ids = [t["id"] for t in data["tasks"]]
    i_daily, i_funnel, i_settle = (
        ids.index("stock_master_daily_load"), ids.index("evening_funnel_capture"), ids.index("settlement"),
    )
    assert i_daily + 1 == i_funnel < i_settle, (
        f"저녁 funnel 행은 일봉 적재 바로 뒤·정산 앞 (§2.6) — 실측 순서 {ids}"
    )
    assert len(ids) == 14, "행 수 불변"


async def test_ops_5_row_when_scheduled_then_2100_and_evidence_key_kept(mo, monkeypatch):
    data = await _at(mo, monkeypatch, datetime(2026, 9, 22, 20, 0, tzinfo=_KST))
    row = {t["id"]: t for t in data["tasks"]}["evening_funnel_capture"]
    assert row["scheduled_at"] == "21:00", row
    assert row["status"] == "scheduled", "20:00 = 예정 시각 전 + 증거 0 → scheduled"
    assert row["evidence"] == {"snapshot_rows_today": 0}, "evidence 키는 계약 — 이름 유지"


async def test_ops_6_row_when_next_session_rows_counted_then_done(mo, monkeypatch):
    data = await _at(
        mo, monkeypatch, datetime(2026, 9, 22, 22, 0, tzinfo=_KST),
        combined={**_EMPTY_COMBINED, "funnel_rows": 59, "funnel_last_at": "2026-09-22T21:01:07+09:00"},
    )
    row = {t["id"]: t for t in data["tasks"]}["evening_funnel_capture"]
    assert row["status"] == "done" and row["evidence"] == {"snapshot_rows_today": 59}
    assert row["last_success_at"] == "2026-09-22T21:01:07+09:00"
