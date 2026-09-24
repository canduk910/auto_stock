"""cycle285 적대 검증 — `market_ops.py` 의 실 SQL 을 mock 없이 왕복 확인한다.

`tests/unit/routes/test_cycle285_market_ops_route.py` 는 `pg.fetchrow`/
`system_config.get_task_last_success_bulk` 를 전부 monkeypatch 하므로, `_COMBINED_SQL`
문자열 자체가 실제 Postgres 에서 의도대로 도는지는 이 스위트가 유일하게 잰다
(cycle273a 의 "KST 하한을 str 로 바인딩 → 실 PG 에서만 DataError" 사고가 같은 사각에서
났다 — 이 파일은 그 재발을 막는 회귀 그물이다, test 렌즈 MEDIUM #7).

검증 대상:
1. `strategy_funnel_snapshots` 의 `is_provisional=TRUE` 필터가 09:30 자동 캡처
   (`is_provisional=FALSE`) 행을 실제로 배제한다(HIGH #1 시정의 실 DB 증거).
2. `funnel_last_at`/`rec_last_at` 이 `target_date` 필터 없이 전체 기간 최댓값을 낸다.
3. `system_config.set_task_last_success` → `get_task_last_success_bulk` 왕복이
   ISO 문자열을 그대로 보존한다(결측 라벨은 키 자체가 없다).
4. `GET /api/market-ops` 라우트 전체를 실 PG 위에서 태워 200 + `evidence_errors == []`
   + 오늘 산출물이 정확한 상태로 반영됨을 확인한다.

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_KST = timezone(timedelta(hours=9))
_D = date(2026, 9, 14)


def _funnel_floor(d: date):
    """cycle350 B2 — `_COMBINED_SQL` 의 두 번째 인자(저녁 funnel 증거 하한).

    `getattr` 로 찾는 이유 = 미구현일 때 import 오류가 아니라 assert 로 붉게 하려고.
    """
    import src.routes.market_ops as mo

    fn = getattr(mo, "_funnel_evidence_floor", None)
    assert callable(fn), (
        "src/routes/market_ops.py::_funnel_evidence_floor 미구현 (Red — cycle350 B2-2)"
    )
    return fn(d)


async def _pin_funnel_snapshot_at(pg, at: datetime, *, target_date: date, step_no: int) -> None:
    """cycle350 — 벽시계 배제. 저녁 캡처 행의 `snapshot_at` 을 그날 16:21 로 고정한다
    (B1 이후 `snapshot_at` = 마지막 쓰기 시각이고 B2 가 그 값에 하한을 건다)."""
    status = await pg.execute(
        "UPDATE strategy_funnel_snapshots SET snapshot_at = $1 "
        "WHERE target_date = $2 AND strategy_id = 'donchian_swing' AND step_no = $3",
        at, target_date, step_no,
    )
    assert status == "UPDATE 1", status


@pytest.mark.asyncio
async def test_c285_pg_1_funnel_rows_excludes_non_provisional(
    clean_strategy_funnel, clean_system_config,
):
    """09:30 자동 캡처(`is_provisional=False`)와 16:20 저녁 캡처(`True`)가 같은
    (target_date, strategy_id, step_no) 를 UPSERT 해도 `_COMBINED_SQL` 의
    `funnel_rows`/`funnel_last_at` 은 저녁 캡처 행만 센다."""
    from src.db.strategy_funnel import insert_snapshot
    from src.routes.market_ops import _COMBINED_SQL
    from src.db._kst import to_date
    import src.db.pg as pg

    # 09:30 자동 캡처(비잠정) — 실제로는 이게 먼저 UPSERT 되는 순서다.
    await insert_snapshot(
        target_date=_D, strategy_id="donchian_swing", step_no=99,
        step_name="최종", survived_tickers=["005930"], is_provisional=False,
    )
    # cycle350 — 하한 이후 시각으로 고정해 「is_provisional 필터만」 을 잰다(시각 게이트와 분리).
    await _pin_funnel_snapshot_at(
        pg, datetime(2026, 9, 14, 16, 21, tzinfo=_KST), target_date=_D, step_no=99,
    )
    row = await pg.fetchrow(_COMBINED_SQL, to_date(_D), _funnel_floor(_D))
    assert row["funnel_rows"] == 0, (
        "09:30 자동 캡처(is_provisional=False)가 저녁 잠정 캡처 카운트에 새고 있다"
        " — HIGH #1 이 실제로는 안 고쳐졌다"
    )

    # 16:20 저녁 캡처(잠정) — 같은 step_no 라 UPSERT 가 그 행을 덮어쓴다.
    await insert_snapshot(
        target_date=_D, strategy_id="donchian_swing", step_no=99,
        step_name="최종", survived_tickers=["005930"], is_provisional=True,
    )
    await _pin_funnel_snapshot_at(
        pg, datetime(2026, 9, 14, 16, 21, tzinfo=_KST), target_date=_D, step_no=99,
    )
    row2 = await pg.fetchrow(_COMBINED_SQL, to_date(_D), _funnel_floor(_D))
    assert row2["funnel_rows"] == 1
    assert row2["funnel_last_at"] is not None


@pytest.mark.asyncio
async def test_c285_pg_2_last_at_fields_are_all_time_not_today_only(
    clean_strategy_funnel, clean_system_config,
):
    """`rec_last_at`/`funnel_last_at` 은 마커 기반 4열과 같은 의미(전체 기간 마지막
    성공)를 가지도록 오늘 필터가 없어야 한다(honest 렌즈 LOW #8 시정)."""
    from src.db.strategy_funnel import insert_snapshot
    from src.routes.market_ops import _COMBINED_SQL
    from src.db._kst import to_date
    import src.db.pg as pg

    yesterday = _D - timedelta(days=1)
    await insert_snapshot(
        target_date=yesterday, strategy_id="donchian_swing", step_no=99,
        step_name="최종", survived_tickers=["005930"], is_provisional=True,
    )
    await _pin_funnel_snapshot_at(
        pg, datetime(2026, 9, 13, 16, 21, tzinfo=_KST), target_date=yesterday, step_no=99,
    )
    # 오늘(target_date=_D) 은 아직 아무 행도 없다.
    row = await pg.fetchrow(_COMBINED_SQL, to_date(_D), _funnel_floor(_D))
    assert row["funnel_rows"] == 0, "오늘 행이 없어야 한다"
    assert row["funnel_last_at"] == "2026-09-13T16:21:00+09:00", (
        "어제 성공한 저녁 캡처의 마지막 성공 시각이 여전히 보여야 한다"
        "(전체 기간 최댓값 계약 — cycle350 하한은 funnel_rows 에만 걸린다)"
    )


@pytest.mark.asyncio
async def test_c285_pg_3_marker_bulk_roundtrip_preserves_iso_string(clean_system_config):
    from src.db.system_config import set_task_last_success, get_task_last_success_bulk

    iso = "2026-09-14T16:12:03+09:00"
    await set_task_last_success("stock_master_basics_refresh", iso)
    result = await get_task_last_success_bulk(
        ["stock_master_basics_refresh", "stock_master_master_load"]
    )
    assert result.get("stock_master_basics_refresh") == iso
    assert "stock_master_master_load" not in result, (
        "마커가 없는 라벨은 결과에 키 자체가 없어야 한다(빈 문자열이 아니다)"
    )


@pytest.mark.asyncio
async def test_c285_pg_4_route_end_to_end_over_real_pg(
    clean_strategy_funnel, clean_system_config, clean_log_reports,
    clean_daily_performance, clean_parameter_recommendations,
):
    """라우트 본체를 실 PG 위에서 직접 `await` 로 태우고(사이클 127 관례 —
    `TestClient` + asyncpg 풀은 서로 다른 이벤트 루프라 `attached to a different
    loop` 로 죽는다), 오늘 자문 행 + 저녁 잠정 캡처가 정확히 반영되는지 확인한다 —
    mock 이 절대 못 잡는 SQL 오탈자·타입 불일치의 최종 방어선."""
    import src.routes.market_ops as mo
    from src.db.strategy_funnel import insert_snapshot
    from src.db.system_config import set_task_last_success

    await insert_snapshot(
        target_date=_D, strategy_id="donchian_swing", step_no=99,
        step_name="최종", survived_tickers=["005930"], is_provisional=True,
    )
    # cycle350 — 벽시계 배제: 저녁 캡처 행을 그날 16:21 로 고정(하한 이후 = 저녁 증거).
    import src.db.pg as pg

    await _pin_funnel_snapshot_at(
        pg, datetime(2026, 9, 14, 16, 21, tzinfo=_KST), target_date=_D, step_no=99,
    )
    await set_task_last_success(
        "stock_master_basics_refresh", "2026-09-14T16:12:00+09:00"
    )

    frozen = datetime(2026, 9, 14, 18, 0, tzinfo=_KST)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    orig_dt = mo.datetime
    mo.datetime = _FrozenDatetime
    # trading_day/engine 은 이 테스트의 관심사가 아니다 — DB 경로만 실측한다.
    import unittest.mock as _um
    with _um.patch.object(
        mo, "_resolve_trading_day", AsyncMock(return_value=(True, "kis"))
    ):
        try:
            response = await mo.read_market_ops()
        finally:
            mo.datetime = orig_dt

    data = response.data
    assert data["evidence_errors"] == [], (
        f"실 PG 경로에서 소스 실패가 있었다: {data['evidence_errors']}"
    )
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["evening_funnel_capture"]["status"] == "done"
    assert by_id["evening_funnel_capture"]["evidence"]["snapshot_rows_today"] == 1
    assert by_id["stock_master_basics_refresh"]["status"] == "done"
    # 18:00 은 TIME_RECOMMENDATION(20:00) 이전이라 증거가 없어도 "scheduled" 다.
    assert by_id["recommendation"]["status"] == "scheduled"
    assert by_id["recommendation"]["evidence"]["recommendation_rows_today"] == 0
