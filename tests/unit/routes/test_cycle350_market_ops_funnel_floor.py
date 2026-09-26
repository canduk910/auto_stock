"""cycle350 B2 — `GET /api/market-ops` 저녁 funnel 증거에 evidence-time 게이트.

정본 = `_workspace/red/cycle350_evening_funnel_spec.md` §4 B2.

B1(`insert_snapshot` 이 덮어쓸 때 `snapshot_at = now()`) 로 `snapshot_at` 이 「마지막 쓰기
시각」이 되면, 부팅 +600초(≈07:57) 잠정 행이 07:57~09:35 동안 「저녁 캡처 완료」로 보이던
오판을 시각으로 걸러낼 수 있다. 다른 행이 쓰는 `_evidence_after_schedule`(2시간 유예)와
**같은 규칙**이다.

이 파일 = 순수 헬퍼 `_funnel_evidence_floor` + 라우트 호출 인자 + SQL 문구(가짜 pg).
실 PG 에서 그 SQL 이 실제로 그 뜻인지는 `tests/integration/test_cycle350_funnel_snapshot_at_pg.py`.

검증 대상:
- B2-2 `_funnel_evidence_floor(today) == combine(today, TIME_EVENING_FUNNEL_CAPTURE, KST)
  - _SCHEDULE_EVIDENCE_GRACE` (tz-aware KST). 시각 리터럴 금지 → 두 상수를 따라 움직인다.
- B2-1 그 하한이 `_evidence_after_schedule` 과 같은 규칙이다.
- 라우트 호출 = `pg.fetchrow(_COMBINED_SQL, to_date(today), _funnel_evidence_floor(today))`.
- B2-1/B2-3 `funnel_rows` 서브쿼리만 `snapshot_at >= $2` 를 갖는다.
- B2-4 `funnel_last_at` 은 게이트 없음(전체 기간 최댓값).
- B2-5 evidence 키·응답 모양 불변.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_D = date(2026, 9, 14)

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


def _floor_fn():
    """Red 사유를 「미구현」으로 고정한다 — import 오류로 붉지 않게 getattr 로 찾는다."""
    import src.routes.market_ops as mo

    fn = getattr(mo, "_funnel_evidence_floor", None)
    assert callable(fn), (
        "src/routes/market_ops.py::_funnel_evidence_floor 미구현 (Red — cycle350 B2-2). "
        "`_funnel_evidence_floor(today) -> datetime` = combine(today, "
        "TIME_EVENING_FUNNEL_CAPTURE, tzinfo=_KST) - _SCHEDULE_EVIDENCE_GRACE"
    )
    return fn


def _expected_floor(d: date) -> datetime:
    """명세 B2-2 식 그대로 — 두 상수는 정본 모듈에서 읽는다(값을 베끼지 않는다)."""
    import src.routes.market_ops as mo
    from src.engine.scheduler import TIME_EVENING_FUNNEL_CAPTURE

    return (
        datetime.combine(d, TIME_EVENING_FUNNEL_CAPTURE, tzinfo=_KST)
        - mo._SCHEDULE_EVIDENCE_GRACE
    )


@pytest.fixture
def mo(monkeypatch):
    """모듈을 반환하며 기본 목(정상 개장, 증거 0)을 깐다 — cycle285 라우트 테스트 동형."""
    import src.routes.market_ops as _mo

    monkeypatch.setattr(_mo, "_resolve_trading_day", AsyncMock(return_value=(True, "kis")))
    monkeypatch.setattr(
        _mo.system_config, "get_task_last_success_bulk", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        _mo.refresh_progress,
        "get_all_progress",
        lambda: {k: dict(_IDLE_PROGRESS) for k in ("universe", "basics", "daily", "master", "financial")},
    )
    monkeypatch.setattr(_mo.pg, "fetchrow", AsyncMock(return_value=dict(_EMPTY_COMBINED)))
    monkeypatch.setattr(_mo, "get_log_report", AsyncMock(return_value=None))
    monkeypatch.setattr(_mo.trading_scheduler, "_running", False, raising=False)
    monkeypatch.setattr(_mo.trading_scheduler, "_phase", "idle", raising=False)
    return _mo


async def _call_route_at(mo, monkeypatch, moment: datetime) -> dict:
    """라우트 본체를 `moment` 로 얼린 시계에서 직접 await (cycle285 pg_4 관례)."""
    frozen = moment

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr(mo, "datetime", _FrozenDatetime)
    response = await mo.read_market_ops()
    return response.data


def _funnel_subqueries(sql: str) -> dict[str, str]:
    """`_COMBINED_SQL` 을 별칭 → 서브쿼리 본문으로. `(SELECT ...) AS alias` 단위."""
    flat = re.sub(r"\s+", " ", sql)
    out = {}
    for body, alias in re.findall(r"\(SELECT (.*?)\) AS (\w+)", flat):
        out[alias] = body
    return out


# ===========================================================================
# B2-2 — 순수 헬퍼 `_funnel_evidence_floor`
# ===========================================================================
def test_c350_b2_2_floor_when_called_with_date_then_tz_aware_kst_instant():
    """M6 — naive datetime 이면 asyncpg 가 **프로세스 로컬 TZ** 로 해석한다(로컬 KST 면
    우연히 맞고 UTC 러너면 9시간 어긋난다). tz-aware KST 여야 어디서나 같은 순간이다."""
    floor = _floor_fn()(_D)
    assert isinstance(floor, datetime), f"datetime 이 아니다: {type(floor)!r}"
    assert floor.tzinfo is not None and floor.utcoffset() is not None, (
        "하한이 naive datetime 이다 — asyncpg 가 프로세스 로컬 TZ 로 해석해 CI(UTC)에서 "
        "9시간 어긋난다 (M6)"
    )
    assert floor.utcoffset() == timedelta(hours=9), f"KST 가 아니다: {floor.utcoffset()}"


def test_c350_b2_2_floor_when_called_then_capture_time_minus_grace():
    """M5 — 하한 = 저녁 캡처 예정 시각 − 2시간 유예. 유예를 빼면(=16:20 정각) 14:20~16:20
    사이 정상 near-schedule 증거가 걸러진다."""
    floor = _floor_fn()(_D)
    assert floor == _expected_floor(_D), (
        f"하한 {floor!r} != 명세 B2-2 식 {_expected_floor(_D)!r}"
    )
    assert floor.date() == _D, "하한 날짜는 인자로 받은 today 다"


def test_c350_b2_2_floor_when_capture_constant_moves_then_floor_follows(monkeypatch):
    """M7 — 하한이 `time(16, 20)` 같은 리터럴이면 기존 AST 가드(`test_cycle285_ast_market_ops`
    A1 = 문자열 `HH:MM` 만 · A2 = `N * 60` 산술만)가 못 잡는다. 상수를 옮겨 따라오는지 본다
    — 다음 사이클이 캡처 시각을 옮기는 순간 이 화면이 거짓말하지 않게."""
    import src.routes.market_ops as mo

    fn = _floor_fn()
    monkeypatch.setattr(mo, "TIME_EVENING_FUNNEL_CAPTURE", time(18, 45))
    got = fn(_D)
    want = datetime.combine(_D, time(18, 45), tzinfo=_KST) - mo._SCHEDULE_EVIDENCE_GRACE
    assert got == want, (
        f"TIME_EVENING_FUNNEL_CAPTURE 를 옮겨도 하한이 {got!r} 에 머문다 — 시각 리터럴을 "
        f"베꼈다 (M7). 기대 {want!r}"
    )


def test_c350_b2_2_floor_when_grace_constant_moves_then_floor_follows(monkeypatch):
    """M5 변형 — 유예를 `timedelta(hours=2)` 리터럴로 베끼면 `_evidence_after_schedule`
    과 규칙이 갈라진다. 같은 상수를 읽는지 본다."""
    import src.routes.market_ops as mo
    from src.engine.scheduler import TIME_EVENING_FUNNEL_CAPTURE

    fn = _floor_fn()
    monkeypatch.setattr(mo, "_SCHEDULE_EVIDENCE_GRACE", timedelta(minutes=30))
    got = fn(_D)
    want = datetime.combine(_D, TIME_EVENING_FUNNEL_CAPTURE, tzinfo=_KST) - timedelta(minutes=30)
    assert got == want, f"_SCHEDULE_EVIDENCE_GRACE 를 따라오지 않는다: {got!r} != {want!r}"


@pytest.mark.parametrize(
    "offset",
    [
        timedelta(hours=-2, microseconds=-1),  # 하한 1µs 전 — 제외
        timedelta(hours=-2),                   # 하한 정각 — 포함(B2-3 `>=`)
        timedelta(hours=-1),                   # 유예 안
        timedelta(0),                          # 예정 정각
        timedelta(hours=2, minutes=30),        # 저녁 늦게 (🔁 cycle364 — 캡처 21:00 이라 +3h30m 은 자정을 넘는다)
    ],
    ids=["floor-1us", "floor", "grace-mid", "scheduled", "late"],
)
def test_c350_b2_1_floor_when_compared_then_same_rule_as_evidence_after_schedule(offset):
    """B2-1 — 「다른 행이 쓰는 `_evidence_after_schedule` 과 **같은 규칙**」을 기계로 잰다.
    같은 날 증거 `ts` 에 대해 `ts >= floor` ⇔ `_evidence_after_schedule(ts, today, 저녁캡처)`."""
    import src.routes.market_ops as mo

    floor = _floor_fn()(_D)
    scheduled_dt = datetime.combine(_D, mo.TIME_EVENING_FUNNEL_CAPTURE, tzinfo=_KST)
    ts = scheduled_dt + offset
    assert ts.date() == _D  # 표본은 전부 같은 날
    rule = mo._evidence_after_schedule(ts, _D, mo.TIME_EVENING_FUNNEL_CAPTURE)
    assert (ts >= floor) is rule, (
        f"ts={ts.isoformat()} : `ts >= floor`={ts >= floor} 인데 "
        f"_evidence_after_schedule={rule} — 두 규칙이 갈라졌다"
    )


# ===========================================================================
# B2 — 라우트가 하한을 `_COMBINED_SQL` 의 두 번째 인자로 넘긴다
# ===========================================================================
@pytest.mark.asyncio
async def test_c350_b2_route_when_read_then_fetchrow_gets_today_and_floor(mo, monkeypatch):
    """라우트 호출 = `pg.fetchrow(_COMBINED_SQL, to_date(today), _funnel_evidence_floor(today))`."""
    await _call_route_at(mo, monkeypatch, datetime(2026, 9, 14, 18, 0, tzinfo=_KST))
    call = mo.pg.fetchrow.await_args
    assert call is not None, "라우트가 산출물 집계 쿼리를 부르지 않았다"
    assert call.args[0] is mo._COMBINED_SQL
    assert len(call.args) == 3, (
        f"`_COMBINED_SQL` 인자가 {len(call.args) - 1}개다 — 하한(`_funnel_evidence_floor(today)`) "
        "을 두 번째 인자로 넘겨야 한다 (Red — cycle350 B2-2 미구현)"
    )
    assert call.args[1] == _D and type(call.args[1]) is date, "첫 인자는 오늘 date(to_date)"
    floor_arg = call.args[2]
    assert isinstance(floor_arg, datetime) and floor_arg.utcoffset() == timedelta(hours=9), (
        f"하한 인자가 tz-aware KST datetime 이 아니다: {floor_arg!r} (M6)"
    )
    assert floor_arg == _expected_floor(_D), f"하한 {floor_arg!r} != {_expected_floor(_D)!r}"


@pytest.mark.asyncio
async def test_c350_b2_route_when_as_of_is_next_morning_then_floor_is_that_day(mo, monkeypatch):
    """하한의 날짜는 `as_of` 의 KST 날짜다 — 다음 날 08:00 에 열면 그날 저녁 기준이다
    (전날 16:21 행이 다음 날 오전 「완료」로 새지 않는 것은 `target_date = $1` 이 막는다)."""
    nxt = _D + timedelta(days=1)
    await _call_route_at(mo, monkeypatch, datetime(2026, 9, 15, 8, 0, tzinfo=_KST))
    call = mo.pg.fetchrow.await_args
    assert len(call.args) == 3, "하한 인자 누락 (Red — cycle350 B2-2 미구현)"
    assert call.args[1] == nxt
    assert call.args[2] == _expected_floor(nxt)


# ===========================================================================
# B2-1 / B2-3 / B2-4 — SQL 문구 (실 의미는 PG 왕복이 잰다)
# ===========================================================================
def test_c350_b2_1_combined_sql_when_counting_funnel_rows_then_gated_by_floor_param():
    """M3·M4 — `funnel_rows` 서브쿼리에 `snapshot_at >= $2`. `>` 이면 하한과 같은 순간의
    행이 빠진다(B2-3). 기존 조건 `is_provisional = TRUE` 유지.

    🔁 cycle364 의도적 개정 — 날짜 조건 `target_date = $1` → **`target_date > $1`**. A1 저녁
    캡처는 다음 거래일 라벨로 쓰므로 저녁 증거 = 「오늘 저녁에 쓴 다음 세션 행」이다(설계
    `_workspace/domain_consult/cycle364_a1_as_of_design.md` §2.6 · M12)."""
    import src.routes.market_ops as mo

    subs = _funnel_subqueries(mo._COMBINED_SQL)
    body = subs.get("funnel_rows")
    assert body is not None, f"funnel_rows 서브쿼리를 못 찾았다: {sorted(subs)}"
    assert re.search(r"\btarget_date\s*>\s*\$1\b", body), body
    assert "is_provisional = TRUE" in body, body
    assert re.search(r"\bsnapshot_at\s*>=\s*\$2\b", body), (
        f"funnel_rows 에 `snapshot_at >= $2` 게이트가 없다 (Red — cycle350 B2-1 미구현): {body}"
    )


def test_c350_b2_4_combined_sql_when_reading_funnel_last_at_then_no_floor_gate():
    """M2 — `funnel_last_at` 은 뜻 불변(전체 기간 잠정 행의 마지막 쓰기). 여기에 하한을
    붙이면 07:57 잠정 쓰기가 최신일 때 그 값이 사라진다. `$2` 는 funnel_rows 만 쓴다."""
    import src.routes.market_ops as mo

    subs = _funnel_subqueries(mo._COMBINED_SQL)
    last_at = subs.get("funnel_last_at")
    assert last_at is not None, f"funnel_last_at 서브쿼리를 못 찾았다: {sorted(subs)}"
    assert "is_provisional = TRUE" in last_at, last_at
    assert "$2" not in last_at and "target_date" not in last_at, (
        f"funnel_last_at 에 오늘/하한 게이트가 붙었다 — 전체 기간 최댓값 계약 위반: {last_at}"
    )
    users_of_p2 = [alias for alias, b in subs.items() if "$2" in b]
    assert users_of_p2 in ([], ["funnel_rows"]), (
        f"`$2`(저녁 funnel 하한)를 funnel_rows 밖에서 쓴다: {users_of_p2}"
    )


# ===========================================================================
# B2-5 — 응답 모양 불변 (보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_c350_b2_5_funnel_row_when_counted_then_evidence_key_and_status_unchanged(
    mo, monkeypatch,
):
    """evidence 키 `snapshot_rows_today` · `last_success_at` = `funnel_last_at` 그대로 ·
    상태 어휘 불변 → 프론트·MSW·e2e mock 무변경.

    🔁 cycle364 — 조회 시각 18:00 → 22:00. 캡처가 21:00 으로 옮겨 18:00 은 이제 「예정 전」
    (`scheduled`)이다. 「예정 시각이 지났는데 증거 0 → not_fired」 라는 이 단언의 뜻은 그대로다."""
    monkeypatch.setattr(
        mo.pg, "fetchrow",
        AsyncMock(return_value={
            **_EMPTY_COMBINED, "funnel_rows": 0,
            "funnel_last_at": "2026-09-14T07:57:00+09:00",
        }),
    )
    data = await _call_route_at(mo, monkeypatch, datetime(2026, 9, 14, 22, 0, tzinfo=_KST))
    row = {t["id"]: t for t in data["tasks"]}["evening_funnel_capture"]
    assert row["evidence"] == {"snapshot_rows_today": 0}
    assert row["last_success_at"] == "2026-09-14T07:57:00+09:00"
    assert row["status"] == "not_fired"
