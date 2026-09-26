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


async def _pin_funnel_snapshot_at(
    pg, at: datetime, *, target_date: date, step_no: int, strategy_id: str = "donchian_swing",
) -> None:
    """cycle350 — 벽시계 배제. 저녁 캡처 행의 `snapshot_at` 을 고정 시각으로 되돌린다
    (B1 이후 `snapshot_at` = 마지막 쓰기 시각이고 B2 가 그 값에 하한을 건다)."""
    status = await pg.execute(
        "UPDATE strategy_funnel_snapshots SET snapshot_at = $1 "
        "WHERE target_date = $2 AND strategy_id = $3 AND step_no = $4",
        at, target_date, strategy_id, step_no,
    )
    assert status == "UPDATE 1", status


@pytest.mark.asyncio
async def test_c285_pg_1_funnel_rows_excludes_non_provisional(
    clean_strategy_funnel, clean_system_config,
):
    """09:30 자동 캡처(`is_provisional=False`)는 저녁 잠정 캡처 카운트에 새지 않는다(HIGH #1).

    🔁 cycle364 의도적 개정(설계 `_workspace/domain_consult/cycle364_a1_as_of_design.md` §2.6 ·
    ③-b · M7/M12) — 종전 이 테스트는 「확정 행을 잠정 쓰기가 덮으면 그 행이 저녁 증거가 된다」
    (False→True 덮어쓰기 뒤 `funnel_rows == 1`)를 단언했다. cycle350 §8.2 가 「③-b 착수 때 다시
    짜야 한다」고 적어 둔 바로 그 봉인이다. 이제:
    (a) 오늘 09:35 확정 행을 잠정 쓰기가 **덮지 못한다**(행·`snapshot_at` 불변, 반환 None)
    (b) 오늘 날짜 잠정 행은 저녁 증거가 아니다(아침 +600초 캡처·거래일 비상)
    (c) 다음 세션 확정 행도 아니다 — (d) 다음 세션 잠정 행(하한 이후)만 센다.
    """
    from src.db.strategy_funnel import insert_snapshot
    from src.routes.market_ops import _COMBINED_SQL
    from src.db._kst import to_date
    import src.db.pg as pg

    nxt = _D + timedelta(days=1)
    # 09:30 자동 캡처(확정) — 오늘 키
    await insert_snapshot(
        target_date=_D, strategy_id="donchian_swing", step_no=99,
        step_name="최종", survived_tickers=["005930"], is_provisional=False,
    )
    confirmed_at = datetime(2026, 9, 14, 9, 35, tzinfo=_KST)
    await _pin_funnel_snapshot_at(pg, confirmed_at, target_date=_D, step_no=99)
    row = await pg.fetchrow(_COMBINED_SQL, to_date(_D), _funnel_floor(_D))
    assert row["funnel_rows"] == 0, "09:30 자동 캡처(확정)가 저녁 캡처 카운트에 샌다 (HIGH #1)"

    # (a) 같은 키 잠정 쓰기 → 거부
    rejected = await insert_snapshot(
        target_date=_D, strategy_id="donchian_swing", step_no=99,
        step_name="최종", survived_tickers=["000660"], is_provisional=True,
    )
    assert rejected is None, "잠정 쓰기가 확정 행을 덮었다 (③-b / M7)"
    kept = await pg.fetchrow(
        "SELECT is_provisional, snapshot_at, survived_tickers FROM strategy_funnel_snapshots "
        "WHERE target_date = $1 AND strategy_id = 'donchian_swing' AND step_no = 99", _D,
    )
    assert kept["is_provisional"] is False and kept["snapshot_at"] == confirmed_at
    assert kept["survived_tickers"] == ["005930"]

    # (b) 오늘 날짜 잠정 행(다른 전략 키) — 21:01 에 써도 저녁 증거가 아니다
    await insert_snapshot(
        target_date=_D, strategy_id="kojiro", step_no=99,
        step_name="최종", survived_tickers=["005930"], is_provisional=True,
    )
    await _pin_funnel_snapshot_at(
        pg, datetime(2026, 9, 14, 21, 1, tzinfo=_KST), target_date=_D, step_no=99,
        strategy_id="kojiro",
    )
    # (c) 다음 세션 확정 행
    await insert_snapshot(
        target_date=nxt, strategy_id="vcp_breakout", step_no=99,
        step_name="최종", survived_tickers=["005930"], is_provisional=False,
    )
    await _pin_funnel_snapshot_at(
        pg, datetime(2026, 9, 14, 21, 1, tzinfo=_KST), target_date=nxt, step_no=99,
        strategy_id="vcp_breakout",
    )
    row2 = await pg.fetchrow(_COMBINED_SQL, to_date(_D), _funnel_floor(_D))
    assert row2["funnel_rows"] == 0, "오늘 날짜 잠정 행·다음 세션 확정 행이 저녁 증거로 셈해졌다 (M12)"

    # (d) 다음 세션 잠정 행(A1 저녁 캡처)
    await insert_snapshot(
        target_date=nxt, strategy_id="donchian_swing", step_no=99,
        step_name="최종", survived_tickers=["005930"], is_provisional=True,
    )
    await _pin_funnel_snapshot_at(
        pg, datetime(2026, 9, 14, 21, 1, tzinfo=_KST), target_date=nxt, step_no=99,
    )
    row3 = await pg.fetchrow(_COMBINED_SQL, to_date(_D), _funnel_floor(_D))
    assert row3["funnel_rows"] == 1
    assert row3["funnel_last_at"] is not None


@pytest.mark.asyncio
async def test_c285_pg_2_last_at_fields_are_all_time_not_today_only(
    clean_strategy_funnel, clean_system_config,
):
    """`rec_last_at`/`funnel_last_at` 은 마커 기반 4열과 같은 의미(전체 기간 마지막
    성공)를 가지도록 오늘 필터가 없어야 한다(honest 렌즈 LOW #8 시정).

    🔁 cycle364 — 어제 저녁 A1 캡처 행은 **target_date=오늘**(다음 세션)로 쓰였고 `snapshot_at`
    은 어제 21:01 이다. 오늘 저녁 증거(`target_date > 오늘`)는 아니지만 마지막 쓰기 시각으로는
    여전히 보여야 한다.
    """
    from src.db.strategy_funnel import insert_snapshot
    from src.routes.market_ops import _COMBINED_SQL
    from src.db._kst import to_date
    import src.db.pg as pg

    await insert_snapshot(
        target_date=_D, strategy_id="donchian_swing", step_no=99,
        step_name="최종", survived_tickers=["005930"], is_provisional=True,
    )
    await _pin_funnel_snapshot_at(
        pg, datetime(2026, 9, 13, 21, 1, tzinfo=_KST), target_date=_D, step_no=99,
    )
    row = await pg.fetchrow(_COMBINED_SQL, to_date(_D), _funnel_floor(_D))
    assert row["funnel_rows"] == 0, "오늘 저녁에 쓴 다음 세션 행이 아직 없어야 한다"
    assert row["funnel_last_at"] == "2026-09-13T21:01:00+09:00", (
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

    nxt = _D + timedelta(days=1)
    await insert_snapshot(
        target_date=nxt, strategy_id="donchian_swing", step_no=99,
        step_name="최종", survived_tickers=["005930"], is_provisional=True,
    )
    # cycle350 — 벽시계 배제: 저녁 캡처 행을 그날 21:01 로 고정(하한 이후 = 저녁 증거).
    # 🔁 cycle364 — A1 저녁 캡처는 다음 세션 라벨(target_date = 오늘 + 1)로 쓴다.
    import src.db.pg as pg

    await _pin_funnel_snapshot_at(
        pg, datetime(2026, 9, 14, 21, 1, tzinfo=_KST), target_date=nxt, step_no=99,
    )
    await set_task_last_success(
        "stock_master_basics_refresh", "2026-09-14T16:12:00+09:00"
    )

    frozen = datetime(2026, 9, 14, 22, 0, tzinfo=_KST)  # 🔁 cycle364 — 저녁 캡처(21:00) 뒤

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
    # 22:00 은 TIME_RECOMMENDATION(20:00) 뒤라 증거가 없으면 "not_fired" 다
    # (🔁 cycle364 — 조회 시각 18:00 → 22:00. 「증거 없음은 시계로 판정」 이라는 뜻은 같다).
    assert by_id["recommendation"]["status"] == "not_fired"
    assert by_id["recommendation"]["evidence"]["recommendation_rows_today"] == 0
