"""cycle350 B1+B2 — 실 Postgres 왕복으로 「뜻」을 잰다 (mock 없음).

정본 = `_workspace/red/cycle350_evening_funnel_spec.md` §4.

단위 가드(`tests/unit/db/test_cycle350_funnel_snapshot_at.py` · `tests/unit/routes/
test_cycle350_market_ops_funnel_floor.py`)는 SQL 문구와 호출 인자만 본다. 여기서는
- B1: 두 번째 쓰기 뒤 그 행의 `snapshot_at` 이 **실제로** 두 번째 쓰기의 DB `now()` 가 되는가
- B2: `_COMBINED_SQL` + `_funnel_evidence_floor(today)` 가 실 PG 에서 07:57 잠정 행을 빼고
  하한 이후 행만 세는가, `funnel_last_at` 은 여전히 전체 기간 최댓값인가
- 라우트 본체를 실 PG 위에서 태워 07:57 잠정 행이 「완료」로 보이지 않는가

🔴 벽시계 의존 금지 — 행 시각은 INSERT 뒤 **테스트 DB 에 직접 `UPDATE ... SET snapshot_at`**
으로 고정한다. 하한·경계 시각은 전부 KST tz-aware 값으로 만든다. 예외는 B1 의 「두 번째
쓰기 = DB now()」 하나인데, 그것은 파이썬 시계가 아니라 같은 DB 의 `SELECT now()` 로
앞뒤를 잰다. `_D` 는 과거 날짜라 DB now() 는 언제나 그날 하한보다 늦다.

🔴 「잠정이 확정을 덮는다」를 단언하지 않는다(명세 §4 B1-2) — 여기 모든 덮어쓰기는 같은
`is_provisional` 값끼리다.

🔁 cycle364 의도적 개정(설계 `_workspace/domain_consult/cycle364_a1_as_of_design.md` §2.6) —
저녁 캡처가 21:00 A1(다음 거래일 라벨)이 되면서 저녁 증거 SQL 이 `target_date > $1` 이 됐다.
B2 계열의 「저녁 행」은 이제 `target_date = _D + 1`(오늘 저녁에 쓴 다음 세션 행)이고, 하한은
21:00 − 2h = 19:00 이다. B1(같은 `is_provisional` 끼리 덮으면 `snapshot_at` 갱신)은 그대로다.
「확정→잠정 거부」·「확정→확정 허용」은 `test_cycle364_funnel_protect_confirmed_pg.py` 가 든다.

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""

from __future__ import annotations

import os
import time as _time
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_KST = timezone(timedelta(hours=9))
_D = date(2026, 9, 14)
_NXT = date(2026, 9, 15)  # cycle364 — A1 저녁 캡처가 쓰는 다음 세션 라벨
_SID = "vcp_breakout"
_STEP = 99


def _kst(d: date, hh: int, mm: int, ss: int = 0, us: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, ss, us, tzinfo=_KST)


def _floor(d: date) -> datetime:
    """Red 사유를 「미구현」으로 고정 — import 오류가 아니라 assert 로 붉는다."""
    import src.routes.market_ops as mo

    fn = getattr(mo, "_funnel_evidence_floor", None)
    assert callable(fn), (
        "src/routes/market_ops.py::_funnel_evidence_floor 미구현 (Red — cycle350 B2-2)"
    )
    return fn(d)


def _spec_floor(d: date) -> datetime:
    """명세 B2-2 식을 테스트 쪽에서 독립 계산 — 헬퍼가 틀려도 기준은 움직이지 않는다."""
    import src.routes.market_ops as mo
    from src.engine.scheduler import TIME_EVENING_FUNNEL_CAPTURE

    return (
        datetime.combine(d, TIME_EVENING_FUNNEL_CAPTURE, tzinfo=_KST)
        - mo._SCHEDULE_EVIDENCE_GRACE
    )


async def _write(*, is_provisional: bool, survived=("005930",), target_date: date = _D,
                 strategy_id: str = _SID, step_no: int = _STEP):
    from src.db.strategy_funnel import insert_snapshot

    row = await insert_snapshot(
        target_date=target_date, strategy_id=strategy_id, step_no=step_no,
        step_name="최종", survived_tickers=list(survived), is_provisional=is_provisional,
    )
    assert row is not None, "insert_snapshot 이 None — 실 PG UPSERT 실패"
    return row


async def _pin(pg, at: datetime, *, target_date: date = _D, strategy_id: str = _SID,
               step_no: int = _STEP) -> None:
    """테스트 DB 한정 — 그 행의 `snapshot_at` 을 고정 시각으로 되돌린다(벽시계 배제)."""
    assert at.tzinfo is not None, "고정 시각은 tz-aware 여야 한다"
    status = await pg.execute(
        "UPDATE strategy_funnel_snapshots SET snapshot_at = $1 "
        "WHERE target_date = $2 AND strategy_id = $3 AND step_no = $4",
        at, target_date, strategy_id, step_no,
    )
    assert status == "UPDATE 1", f"고정 대상 행이 1개가 아니다: {status}"


async def _snapshot_at(pg, *, target_date: date = _D, strategy_id: str = _SID,
                       step_no: int = _STEP) -> datetime:
    rows = await pg.fetch(
        "SELECT snapshot_at FROM strategy_funnel_snapshots "
        "WHERE target_date = $1 AND strategy_id = $2 AND step_no = $3",
        target_date, strategy_id, step_no,
    )
    assert len(rows) == 1, f"UPSERT 는 1행이어야 한다: {len(rows)}"
    return rows[0]["snapshot_at"]


async def _combined(pg, d: date = _D) -> dict:
    from src.db._kst import to_date
    from src.routes.market_ops import _COMBINED_SQL

    return await pg.fetchrow(_COMBINED_SQL, to_date(d), _floor(d))


# ===========================================================================
# B1 — insert_snapshot 이 덮어쓸 때 snapshot_at = DB now()
# ===========================================================================
@pytest.mark.asyncio
async def test_c350_pg_b1_1_second_write_when_same_key_then_snapshot_at_is_second_write_db_now(
    clean_strategy_funnel,
):
    """B1-1 — 07:57 에 고정해 둔 행을 다시 쓰면 `snapshot_at` 이 그 두 번째 쓰기의 DB
    `now()` 가 된다(앞뒤 `SELECT now()` 사이). 대입이 없으면 07:57 에 그대로 남는다(M1)."""
    pg = clean_strategy_funnel
    await _write(is_provisional=True)
    stale = _kst(_D, 7, 57)
    await _pin(pg, stale)

    t_before = await pg.fetchval("SELECT now()")
    returned = await _write(is_provisional=True, survived=("005930", "000660"))
    t_after = await pg.fetchval("SELECT now()")

    got = await _snapshot_at(pg)
    assert got != stale, (
        "두 번째 쓰기 뒤에도 snapshot_at 이 07:57 그대로다 — `DO UPDATE SET` 에 "
        "`snapshot_at = now()` 가 없다 (Red — cycle350 B1-1 미구현 / M1)"
    )
    assert t_before <= got <= t_after, (
        f"snapshot_at {got!r} 이 두 번째 쓰기의 DB 시계 구간 [{t_before!r}, {t_after!r}] 밖이다"
    )
    assert returned["snapshot_at"] == got, "RETURNING * 가 갱신된 snapshot_at 을 돌려줘야 한다"


@pytest.mark.asyncio
async def test_c350_pg_b1_1_first_insert_when_new_key_then_snapshot_at_is_default_now(
    clean_strategy_funnel,
):
    """B1-1 후단(보존) — 첫 INSERT 는 지금처럼 컬럼 기본값 `now()`."""
    pg = clean_strategy_funnel
    t_before = await pg.fetchval("SELECT now()")
    await _write(is_provisional=False)
    t_after = await pg.fetchval("SELECT now()")
    got = await _snapshot_at(pg)
    assert t_before <= got <= t_after, f"첫 INSERT snapshot_at {got!r} 이 기본값 now() 가 아니다"


@pytest.mark.asyncio
async def test_c350_pg_b1_2_overwrite_when_same_key_then_one_row_and_last_write_values(
    clean_strategy_funnel,
):
    """B1-2(보존) — 같은 키 재저장 = 1행 + 값은 마지막 쓰기. 같은 `is_provisional` 끼리만
    덮는다(방향성 단언 금지 — ③-b 소관)."""
    pg = clean_strategy_funnel
    await _write(is_provisional=True, survived=("005930",))
    await _write(is_provisional=True, survived=("000660", "035420"))
    rows = await pg.fetch(
        "SELECT survived_tickers, survived_count, is_provisional FROM strategy_funnel_snapshots"
    )
    assert len(rows) == 1
    assert rows[0]["survived_tickers"] == ["000660", "035420"]
    assert rows[0]["survived_count"] == 2
    assert rows[0]["is_provisional"] is True


# ===========================================================================
# B2 — `_COMBINED_SQL` + `_funnel_evidence_floor(today)` 실 PG 의미
# ===========================================================================
@pytest.mark.asyncio
async def test_c350_pg_b2_1_morning_provisional_row_when_before_floor_then_not_evening_evidence(
    clean_strategy_funnel,
):
    """B2-1 / B2-4 — 하한(19:00) 앞인 07:57 에 쓴 다음 세션(`_D + 1`) 잠정 행은 저녁 캡처
    증거가 아니다(M3). 그래도 `funnel_last_at` 은 그 07:57 을 보여야 한다 — 이 태스크의 마지막
    쓰기다(M2).

    🔁 cycle364 — 행을 `target_date = _D + 1` 로 쓰는 것은 날짜 조건(`target_date > $1`)을
    통과시켜 **하한 게이트 하나만** 이 행을 빼게 하려는 것이다. S1 의 부팅 +600초 레거시
    캡처(07:57)는 실제로는 오늘 라벨(`target_date = _D`)이라 날짜 조건만으로도 빠진다."""
    pg = clean_strategy_funnel
    await _write(is_provisional=True, target_date=_NXT)
    await _pin(pg, _kst(_D, 7, 57), target_date=_NXT)

    row = await _combined(pg)
    assert row["funnel_rows"] == 0, (
        "07:57 잠정 행이 저녁 캡처 완료로 셈해졌다 — funnel_rows 에 하한 게이트가 없다 (M3)"
    )
    assert row["funnel_last_at"] == "2026-09-14T07:57:00+09:00", (
        f"funnel_last_at={row['funnel_last_at']!r} — 전체 기간 최댓값 계약(B2-4)이 깨졌다 (M2)"
    )


@pytest.mark.asyncio
async def test_c350_pg_b2_1_evening_provisional_row_when_after_capture_then_counted(
    clean_strategy_funnel,
):
    pg = clean_strategy_funnel
    await _write(is_provisional=True, target_date=_NXT)
    await _pin(pg, _kst(_D, 21, 1), target_date=_NXT)
    row = await _combined(pg)
    assert row["funnel_rows"] == 1
    assert row["funnel_last_at"] == "2026-09-14T21:01:00+09:00"


@pytest.mark.asyncio
async def test_c350_pg_b2_3_row_when_exactly_at_floor_then_counted_and_1us_before_then_not(
    clean_strategy_funnel,
):
    """B2-3 — 경계 `>=`. 하한과 같은 순간의 행은 센다(M4 `>` 가 잡힌다), 1µs 전은 안 센다.
    고정 시각은 테스트가 명세 식으로 **독립 계산**한다(헬퍼가 움직여도 기준은 고정)."""
    pg = clean_strategy_funnel
    boundary = _spec_floor(_D)
    await _write(is_provisional=True, target_date=_NXT)

    await _pin(pg, boundary, target_date=_NXT)
    at_floor = await _combined(pg)
    assert at_floor["funnel_rows"] == 1, (
        f"하한 정각({boundary.isoformat()}) 행이 빠졌다 — `>=` 가 `>` 로 바뀌었거나(M4) "
        "하한이 명세 식과 다르다"
    )

    await _pin(pg, boundary - timedelta(microseconds=1), target_date=_NXT)
    before = await _combined(pg)
    assert before["funnel_rows"] == 0, "하한 1µs 전 행이 셈해졌다 — 하한이 명세 식보다 이르다"


@pytest.mark.asyncio
async def test_c350_pg_b2_1_row_when_inside_grace_window_then_counted(clean_strategy_funnel):
    """M5 — 예정 시각 전 2시간 유예 안(예정 − 유예/2)의 잠정 행은 정상 near-schedule
    증거다. 하한에서 유예를 빼면(예정 시각 정각 = 21:00) 이 행이 빠진다."""
    import src.routes.market_ops as mo
    from src.engine.scheduler import TIME_EVENING_FUNNEL_CAPTURE

    pg = clean_strategy_funnel
    inside = (
        datetime.combine(_D, TIME_EVENING_FUNNEL_CAPTURE, tzinfo=_KST)
        - mo._SCHEDULE_EVIDENCE_GRACE / 2
    )
    await _write(is_provisional=True, target_date=_NXT)
    await _pin(pg, inside, target_date=_NXT)
    row = await _combined(pg)
    assert row["funnel_rows"] == 1, (
        f"유예 구간 안({inside.isoformat()}) 행이 빠졌다 — 하한에서 유예가 빠졌다 (M5)"
    )


@pytest.mark.asyncio
async def test_c350_pg_b2_1_non_provisional_row_when_after_floor_then_still_excluded(
    clean_strategy_funnel,
):
    """보존(cycle285 HIGH #1) — 09:35 확정 캡처·스캐너 훅(`is_provisional=False`)은 하한
    이후라도 저녁 캡처 증거가 아니다. 새 게이트가 기존 필터를 대체하면 안 된다."""
    pg = clean_strategy_funnel
    await _write(is_provisional=False, target_date=_NXT)
    await _pin(pg, _kst(_D, 21, 1), target_date=_NXT)
    row = await _combined(pg)
    assert row["funnel_rows"] == 0
    assert row["funnel_last_at"] is None


@pytest.mark.asyncio
async def test_c350_pg_b1_b2_evening_overwrite_when_morning_row_exists_then_counted(
    clean_strategy_funnel,
):
    """B1 × B2 — 07:57 잠정 행을 저녁 캡처가 덮어쓰면 그 행이 저녁 증거가 된다. B1 이
    없으면(M1) 행이 07:57 에 고정돼 `funnel_rows=0` — 저녁 캡처가 매일 안 돈 것처럼 보인다.
    (두 번째 쓰기 시각 = 실제 DB now() 라 `_D` 하한보다 늘 늦다.)"""
    pg = clean_strategy_funnel
    await _write(is_provisional=True, target_date=_NXT)
    await _pin(pg, _kst(_D, 7, 57), target_date=_NXT)
    await _write(is_provisional=True, survived=("005930", "000660"), target_date=_NXT)

    row = await _combined(pg)
    assert row["funnel_rows"] == 1, (
        "07:57 행을 저녁 쓰기가 덮었는데 저녁 증거로 안 셈해졌다 — snapshot_at 이 갱신되지 "
        "않았다 (M1)"
    )
    assert row["funnel_last_at"] != "2026-09-14T07:57:00+09:00", (
        "funnel_last_at 이 여전히 07:57 이다 — 덮어쓴 시각이 반영되지 않았다 (M1)"
    )


@pytest.fixture
def _process_tz_utc():
    """프로세스 로컬 TZ 를 UTC 로 — asyncpg 는 naive datetime 을 **로컬 TZ** 로 해석한다
    (`timestamptz_encode` 의 `obj.astimezone(utc)`). 로컬이 KST 인 개발 맥에서는 naive
    하한이 우연히 맞아 M6 가 숨는다. CI 러너(UTC)와 같은 조건을 만들어 로컬에서도 잡는다."""
    saved = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    _time.tzset()
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = saved
        _time.tzset()


@pytest.mark.asyncio
async def test_c350_pg_b2_2_floor_when_process_tz_is_utc_then_still_kst_instant(
    clean_strategy_funnel, _process_tz_utc,
):
    """M6 — 하한이 naive 면 UTC 프로세스에서 14:20 이 KST 23:20 으로 읽혀 15:20 KST
    행이 빠진다(9시간 어긋남). tz-aware KST 면 프로세스 TZ 와 무관하게 같은 순간이다."""
    import src.routes.market_ops as mo
    from src.engine.scheduler import TIME_EVENING_FUNNEL_CAPTURE

    assert _time.localtime().tm_gmtoff == 0, "픽스처가 프로세스 TZ 를 UTC 로 못 바꿨다"
    pg = clean_strategy_funnel
    inside = (
        datetime.combine(_D, TIME_EVENING_FUNNEL_CAPTURE, tzinfo=_KST)
        - mo._SCHEDULE_EVIDENCE_GRACE / 2
    )
    await _write(is_provisional=True, target_date=_NXT)
    await _pin(pg, inside, target_date=_NXT)
    row = await _combined(pg)
    assert row["funnel_rows"] == 1, (
        "프로세스 TZ 가 UTC 일 때 유예 구간 안 행이 빠졌다 — 하한이 naive datetime 이다 (M6)"
    )


# ===========================================================================
# 라우트 본체 — 실 PG 위에서 07:57 잠정 행이 「완료」로 보이지 않는다
# ===========================================================================
async def _route_at(moment: datetime) -> dict:
    """cycle285 pg_4 관례 — `TestClient` + asyncpg 풀은 루프가 달라 직접 await."""
    import src.routes.market_ops as mo

    frozen = moment

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    orig = mo.datetime
    mo.datetime = _FrozenDatetime
    try:
        with patch.object(mo, "_resolve_trading_day", AsyncMock(return_value=(True, "kis"))):
            response = await mo.read_market_ops()
    finally:
        mo.datetime = orig
    return response.data


@pytest.mark.asyncio
async def test_c350_pg_route_morning_provisional_row_when_viewed_same_morning_then_scheduled(
    clean_strategy_funnel, clean_system_config, clean_log_reports,
    clean_daily_performance, clean_parameter_recommendations,
):
    """명세 §4 B2-1 효과 — 07:57~09:35 동안 「저녁 캡처 완료」로 보이던 오판이 사라진다.
    10:00(예정 21:00 전)에는 `scheduled`, 마지막 쓰기(07:57)는 그대로 보인다.

    🔁 cycle364 — 07:57 행을 `target_date = _D + 1`(다음 세션 라벨)로 쓴다. 오늘 라벨이면
    `target_date > $1` 날짜 조건만으로 빠져 하한 게이트를 격리하지 못한다."""
    pg = clean_strategy_funnel
    await _write(is_provisional=True, target_date=_NXT)
    await _pin(pg, _kst(_D, 7, 57), target_date=_NXT)

    data = await _route_at(_kst(_D, 10, 0))
    assert data["evidence_errors"] == [], f"실 PG 경로 소스 실패: {data['evidence_errors']}"
    row = {t["id"]: t for t in data["tasks"]}["evening_funnel_capture"]
    assert row["status"] == "scheduled", (
        f"10:00 에 07:57 부팅 잠정 행이 저녁 캡처 {row['status']!r} 로 보인다 — "
        "funnel_rows 하한 게이트가 라우트에 배선되지 않았다 (Red — cycle350 B2)"
    )
    assert row["evidence"] == {"snapshot_rows_today": 0}
    assert row["last_success_at"] == "2026-09-14T07:57:00+09:00"


@pytest.mark.asyncio
async def test_c350_pg_route_morning_row_only_when_viewed_after_capture_time_then_not_fired(
    clean_strategy_funnel, clean_system_config, clean_log_reports,
    clean_daily_performance, clean_parameter_recommendations,
):
    """저녁 캡처가 그날 실패해 07:57 행만 남았으면 캡처 시각(21:00) 뒤 22:00 에는
    `not_fired` 여야 한다 — 07:57 행 때문에 「완료」로 보이면 저녁 실패가 가려진다.

    🔁 cycle364 — 07:57 행을 `target_date = _D + 1`(다음 세션 라벨)로 쓴다. 오늘 라벨이면
    `target_date > $1` 날짜 조건만으로 빠져, 이 테스트가 하한 게이트(M3)를 격리하지 못한다."""
    pg = clean_strategy_funnel
    await _write(is_provisional=True, target_date=_NXT)
    await _pin(pg, _kst(_D, 7, 57), target_date=_NXT)

    data = await _route_at(_kst(_D, 22, 0))  # 🔁 cycle364 — 캡처 21:00 뒤
    assert data["evidence_errors"] == []
    row = {t["id"]: t for t in data["tasks"]}["evening_funnel_capture"]
    assert row["status"] == "not_fired", (
        f"저녁 캡처가 안 돌았는데 {row['status']!r} — 07:57 행이 저녁 실패를 가린다 "
        "(Red — cycle350 B2)"
    )


@pytest.mark.asyncio
async def test_c350_pg_route_evening_row_when_viewed_after_capture_time_then_done(
    clean_strategy_funnel, clean_system_config, clean_log_reports,
    clean_daily_performance, clean_parameter_recommendations,
):
    """보존 — 저녁 잠정 행이 있으면 캡처 시각 뒤에 `done`, 증거 1.

    🔁 cycle364 — 저녁 행 = 21:01 에 쓴 다음 세션 행(target_date = _D + 1), 조회 22:00."""
    pg = clean_strategy_funnel
    await _write(is_provisional=True, target_date=_NXT)
    await _pin(pg, _kst(_D, 21, 1), target_date=_NXT)

    data = await _route_at(_kst(_D, 22, 0))
    assert data["evidence_errors"] == []
    row = {t["id"]: t for t in data["tasks"]}["evening_funnel_capture"]
    assert row["status"] == "done"
    assert row["evidence"] == {"snapshot_rows_today": 1}
    assert row["last_success_at"] == "2026-09-14T21:01:00+09:00"
