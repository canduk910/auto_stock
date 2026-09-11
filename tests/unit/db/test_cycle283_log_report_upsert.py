"""cycle283 Red — `insert_log_report` upsert 전환 + 수동 재실행 비파괴 가드 (C9/C9-b).

## 왜 (D6)
20:20 클라우드 루틴의 POST 실측 시각 = **20:34 / 20:35 / 20:36 / 20:54**(09-10/09/08/07).
정산이 21:30 이 되면 루틴이 **먼저** 그날 행을 만든다(`upsert_external_report` 의
placeholder INSERT). 현행 `insert_log_report` 는 `ON CONFLICT` 없는 순수 INSERT 라
UNIQUE 충돌로 `None` 을 반환하고, `log_analysis_engine.py` 는 `if row:` 뿐이라 **조용히
끝난다**. 그러면 그날 **`metrics` JSONB 가 통째로 유실**된다 — OpenAI 텍스트만이 아니다.

## C9 계약
`INSERT … ON CONFLICT (target_date) DO UPDATE SET` — SET 절은 **base 9컬럼만**:
`summary` / `findings` / `metrics` / `model` / `input_tokens` / `output_tokens` /
`total_tokens` / `latency_ms` / `cost_estimate_usd`.

🔴 `ext_provider` / `ext_model` / `ext_summary` / `ext_findings` / `ext_report_md` /
`ext_created_at` **6컬럼은 SET 절에 절대 넣지 않는다** — 한 컬럼이라도 새면 20:20 루틴
결과가 조용히 지워진다(`upsert_external_report` 가 반대 방향으로 지키는 규약과 정확히
대칭이다: 그쪽 SET 절은 ext_* 6개뿐, 이쪽은 base 9개뿐 ⇒ **교집합 공집합**이라
20:05→20:34→21:30 과 20:34→21:30 두 순서 모두에서 상호 보존된다).

`created_at` 은 **보존**(DO UPDATE 에서 갱신하지 않는다).
반환 계약: 현재 "충돌 시 `None`" → 이제 **항상 행 반환**.

## 🔴 C9-b — 수동 재실행 비파괴 (자문 지적, 이것 없이는 GO 불가)
지금 `POST /api/log-reports/run` 재실행은 UNIQUE 충돌로 **무해한 no-op** 이다.
upsert 후에는 21:30 정산(= `reset_request_metrics()` + `_reset_daily_state()`) **뒤**에
실행하면 `collect_daily_log_metrics` 가 `api_metrics` 0 · `strategy_funnel` 0 을 새로
만들어 **그날 완성 리포트를 통째로 덮어쓴다**. `target_date` 는 항상 오늘(KST)이라 과거
파괴는 불가능하지만, 그날 하루치는 날아간다.

⇒ 라우트는 기본적으로 **덮어쓰지 않는다**. 덮어쓰려면 명시 플래그(`?force=1`)가 필요하다.

## Red 유효성
- C9 계열 — 현행 SQL 에 `ON CONFLICT` 가 없어 FAIL.
- C9-b 계열 — `run_now` 가 `force` 파라미터를 받지 않아 FAIL.
"""
from __future__ import annotations

import inspect
import re
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

_BASE_SET_COLUMNS = (
    "summary", "findings", "metrics", "model",
    "input_tokens", "output_tokens", "total_tokens",
    "latency_ms", "cost_estimate_usd",
)
_EXT_COLUMNS = (
    "ext_provider", "ext_model", "ext_summary",
    "ext_findings", "ext_report_md", "ext_created_at",
)


async def _capture_sql(**overrides) -> tuple[str, list]:
    """`insert_log_report` 가 pg 에 넘긴 (sql, args) 를 잡는다."""
    from src.db import log_reports

    kwargs = dict(
        target_date=date(2026, 9, 14),
        summary="요약",
        findings=[{"category": "api", "severity": "low"}],
        metrics={"logs": {"total_logs": 3}},
        model="gpt-x",
    )
    kwargs.update(overrides)
    with patch.object(log_reports, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "row-1"})
        pg_mod.fetchval = AsyncMock(return_value=None)
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await log_reports.insert_log_report(**kwargs)
    call = pg_mod.fetchrow.await_args or pg_mod.execute.await_args
    assert call is not None, "pg 호출이 없다"
    return call.args[0], list(call.args[1:])


def _set_clause(sql: str) -> str:
    m = re.search(r"DO\s+UPDATE\s+SET(.*?)(RETURNING|$)", sql, re.S | re.I)
    assert m, f"`DO UPDATE SET` 절을 찾지 못했다 — SQL:\n{sql}"
    return m.group(1)


# ===========================================================================
# C9 — upsert 전환
# ===========================================================================

@pytest.mark.asyncio
async def test_c283_c9_1_sql_is_upsert_on_target_date():
    sql, _ = await _capture_sql()
    assert re.search(r"ON\s+CONFLICT\s*\(\s*target_date\s*\)", sql, re.I), (
        "`ON CONFLICT (target_date)` 부재 — 20:20 루틴이 먼저 행을 만든 날 그날 "
        f"`metrics` JSONB 가 통째로 유실된다\nSQL:\n{sql}"
    )
    assert re.search(r"DO\s+UPDATE\s+SET", sql, re.I), "`DO UPDATE SET` 부재"


@pytest.mark.asyncio
@pytest.mark.parametrize("col", _BASE_SET_COLUMNS)
async def test_c283_c9_2_set_clause_covers_every_base_column(col):
    """base 9컬럼 전부가 SET 절에 있다 — 하나라도 빠지면 그 컬럼만 1차 값에 고착된다."""
    sql, _ = await _capture_sql()
    clause = _set_clause(sql)
    assert re.search(rf"\b{col}\s*=", clause), (
        f"`{col}` 이 SET 절에 없다 — 21:30 완전판이 그 컬럼만 20:05 스냅샷 값으로 남는다"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("col", _EXT_COLUMNS)
async def test_c283_c9_3_set_clause_never_touches_ext_columns(col):
    """🔴 `ext_*` 6컬럼은 SET 절에 절대 없다.

    한 컬럼이라도 새면 20:20 클라우드 루틴의 그날 결과가 21:30 에 조용히 지워진다.
    `upsert_external_report` 가 정확히 반대 방향으로 지키는 규약의 거울이다.
    """
    sql, _ = await _capture_sql()
    clause = _set_clause(sql)
    assert not re.search(rf"\b{col}\s*=", clause), (
        f"`{col}` 이 SET 절에 있다 — 20:20 루틴 결과가 21:30 upsert 에 지워진다\n{clause}"
    )


@pytest.mark.asyncio
async def test_c283_c9_4_created_at_is_preserved_on_conflict():
    """`created_at` 은 DO UPDATE 에서 갱신하지 않는다.

    ⚠️ 부작용(문서화로 충분) — UI 가 그 값을 '생성' 으로 표시하므로
    (`DailyReportTab.tsx`) 완성본의 생성 시각이 **20:05 로 보인다**. 값 오류가 아니라
    라벨 문제다.
    """
    sql, _ = await _capture_sql()
    clause = _set_clause(sql)
    assert not re.search(r"\bcreated_at\s*=", clause), (
        "`created_at` 이 SET 절에 있다 — 행의 최초 생성 시각을 잃는다"
    )


@pytest.mark.asyncio
async def test_c283_c9_5_returns_row_even_when_row_already_exists():
    """반환 계약 — 이제 **항상 행**. `None` 은 정상 경로에서 나오지 않는다.

    호출자는 `log_analysis_engine.py` 하나뿐이고 `if row:` 로 로그만 찍으므로 안전하다
    (`None` 을 가드로 쓰는 호출자 0건 — grep 확인 완료).
    """
    from src.db import log_reports

    existing = {"id": "row-1", "target_date": date(2026, 9, 14), "summary": "완전판"}

    async def _pg_like_postgres(sql, *args):
        """실 Postgres 흉내 — 그날 행이 이미 있고, SQL 에 `ON CONFLICT` 가 없으면
        **UniqueViolation 을 던진다**. 단순 `return_value` mock 이면 SQL 이 무엇이든
        행을 돌려줘 이 단언이 공허해진다.
        """
        if not re.search(r"ON\s+CONFLICT", sql, re.I):
            raise Exception(
                "duplicate key value violates unique constraint "
                '"daily_log_reports_target_date_key" (23505)'
            )
        return existing

    with patch.object(log_reports, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(side_effect=_pg_like_postgres)
        pg_mod.fetchval = AsyncMock(return_value=None)
        pg_mod.execute = AsyncMock(side_effect=_pg_like_postgres)
        out = await log_reports.insert_log_report(
            target_date=date(2026, 9, 14), summary="완전판",
            findings=[], metrics={"x": 1}, model="m",
        )
    assert out == existing, (
        "그날 행이 이미 있는 상태에서 `None` 이 돌아왔다 — 20:20 루틴이 먼저 행을 만든 "
        "날 그날 `metrics` JSONB 가 통째로 유실된다(`if row:` 는 조용히 끝난다)"
    )


@pytest.mark.asyncio
async def test_c283_c9_6_on_conflict_nothing_mode_exists():
    """C9-b(DB 층) — `on_conflict='nothing'` 이면 기존 행을 **건드리지 않는다**.

    수동 재실행 파괴를 막는 두 방법(라우트 409 / DB 층 no-op) 중 어느 쪽을 골라도
    좋지만, DB 층이 no-op 모드를 제공하면 라우트가 단순해진다. 기본값은 `'update'`
    (정산 경로의 계약)이고 `'nothing'` 은 **명시적으로만** 쓴다.
    """
    from src.db import log_reports

    sig = inspect.signature(log_reports.insert_log_report)
    assert "on_conflict" in sig.parameters, (
        "`insert_log_report(..., on_conflict='update'|'nothing')` 파라미터 부재 (C9-b)"
    )
    assert sig.parameters["on_conflict"].default == "update", (
        "기본값은 `'update'` — 정산 경로가 아무 인자 없이 완전판을 덮어쓸 수 있어야 한다"
    )

    with patch.object(log_reports, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod.fetchval = AsyncMock(return_value=None)
        pg_mod.execute = AsyncMock(return_value="INSERT 0 0")
        await log_reports.insert_log_report(
            target_date=date(2026, 9, 14), summary="s", findings=[],
            metrics={}, model=None, on_conflict="nothing",
        )
    call = pg_mod.fetchrow.await_args or pg_mod.execute.await_args
    sql = call.args[0]
    assert re.search(r"ON\s+CONFLICT\s*\(\s*target_date\s*\)\s*DO\s+NOTHING", sql, re.I), (
        f"`on_conflict='nothing'` 인데 DO NOTHING 이 아니다\nSQL:\n{sql}"
    )


@pytest.mark.asyncio
async def test_c283_c9_7_invalid_on_conflict_is_rejected():
    """오타가 조용히 `update` 로 떨어지면 안 된다 — 파괴 방향의 기본값이라 더 그렇다."""
    from src.db import log_reports

    with patch.object(log_reports, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        with pytest.raises((ValueError, AssertionError)):
            await log_reports.insert_log_report(
                target_date=date(2026, 9, 14), summary="s", findings=[],
                metrics={}, model=None, on_conflict="upsert",  # 오타
            )


def test_c283_c9_8_docstring_no_longer_promises_none_on_conflict():
    """C9 ③ — 거짓이 되는 문서 2곳 중 하나: `upsert_external_report` 의 docstring.

    "이 함수가 먼저 placeholder 를 만들면 그날의 `insert_log_report` 는 UNIQUE 충돌로
    `None` 을 반환한다" 는 서술이 **반증된다**. 나머지 하나는 `src/db/CLAUDE.md` 다
    (`tests/unit/engine/test_cycle283_evening_window.py::test_c283_11b` 가 잰다).
    """
    from src.db import log_reports

    ext_doc = inspect.getdoc(log_reports.upsert_external_report) or ""
    assert "UNIQUE 충돌을 그대로 맞고" not in ext_doc, (
        "`upsert_external_report` docstring 이 아직 '충돌 → None' 을 말한다 — 반증됐다"
    )
    ins_doc = inspect.getdoc(log_reports.insert_log_report) or ""
    assert "동일 영업일 재실행 시 None 반환" not in ins_doc, (
        "`insert_log_report` docstring 이 아직 순수 INSERT 계약을 말한다"
    )
    assert "ON CONFLICT" in ins_doc or "upsert" in ins_doc.lower(), (
        "새 계약(upsert + ext_* 무접촉)이 docstring 에 없다"
    )


# ===========================================================================
# C9-b — 라우트 수동 재실행 비파괴
# ===========================================================================

def test_c283_c9b_1_run_route_accepts_an_explicit_force_flag():
    """`POST /api/log-reports/run` 이 명시 플래그를 받는다.

    현행 시그니처는 `run_now()` — 인자가 없다. upsert 이후 그 상태로 두면
    21:30 이후 재실행 한 번이 그날 완성 리포트를 `api_metrics` 0 · `strategy_funnel` 0
    으로 덮어쓴다(21:30 정산이 `reset_request_metrics()` 와 `_reset_daily_state()` 를
    이미 돌린 뒤이기 때문).
    """
    from src.routes import log_reports as route

    sig = inspect.signature(route.run_now)
    assert "force" in sig.parameters, (
        "`run_now` 에 `force` 파라미터 부재 — 수동 재실행이 파괴적이 된다 (C9-b)"
    )
    assert sig.parameters["force"].default in (False, 0), (
        "기본값이 덮어쓰기면 가드가 아니다 — 기본은 비파괴"
    )


@pytest.mark.asyncio
async def test_c283_c9b_2_rerun_without_force_does_not_overwrite_a_complete_report():
    """force 없이 재실행하면 완성 리포트를 **건드리지 않는다**."""
    from src.routes import log_reports as route

    complete = {
        "target_date": "2026-09-14",
        "summary": "완전판 요약",
        "model": "gpt-x",
        "metrics": {"api_metrics": {"total": 4821}},
    }
    gen = AsyncMock(return_value={"id": "new"})
    with patch.object(route, "get_log_report", AsyncMock(return_value=complete)), \
            patch.object(route, "generate_daily_log_report", gen):
        resp = await route.run_now()

    assert gen.await_count == 0, (
        "완성 리포트가 있는데 재분석을 실행했다 — 21:30 이후라면 그날 `api_metrics` 와 "
        "`strategy_funnel` 이 0 으로 덮여 사라진다"
    )
    assert resp.success is False, "비파괴 거부는 조용하면 안 된다(운영자가 알아야 한다)"


@pytest.mark.asyncio
async def test_c283_c9b_3_rerun_with_force_is_allowed():
    """명시 플래그를 주면 덮어쓴다 — 가드는 금지가 아니라 **의도 확인**이다."""
    from src.routes import log_reports as route

    complete = {"target_date": "2026-09-14", "summary": "완전판", "model": "gpt-x"}
    gen = AsyncMock(return_value={"id": "new"})
    with patch.object(route, "get_log_report", AsyncMock(return_value=complete)), \
            patch.object(route, "generate_daily_log_report", gen):
        resp = await route.run_now(force=True)

    assert gen.await_count == 1
    assert resp.success is True


@pytest.mark.asyncio
async def test_c283_c9b_4_rerun_is_allowed_when_no_complete_report_yet():
    """1차 스냅샷만 있는 상태(20:05~21:30)의 수동 실행은 **막지 않는다**.

    그 시간대엔 덮어쓸 완성본이 없다. 막으면 20:10 OpenAI 가 실패한 날의 수동 복구
    경로가 사라진다 — 그게 이 라우트의 존재 이유다.
    """
    from src.routes import log_reports as route

    from src.engine.daily_metrics_snapshot import SNAPSHOT_SUMMARY
    from src.engine.log_analysis_engine import OPENAI_EMPTY_RESPONSE_SUMMARY

    # ⚠️ 픽스처는 **프로덕션이 실제로 쓰는 행 모양**이어야 한다. 1차 스냅샷의
    # `summary` 는 비어 있지 않다(`SNAPSHOT_SUMMARY`) — `{"summary": ""}` 로 재면
    # `summary` 축 하나만으로 통과해 `model` 축을 지우는 뮤테이션이 살아남는다
    # (적대 검증 M23 ESCAPED). 상수를 import 해 단일 출처로 묶는다.
    snapshot_only = {"target_date": "2026-09-14", "summary": SNAPSHOT_SUMMARY,
                     "model": None,
                     "metrics": {"logs": {"total_logs": 12}, "snapshot_pass": 1}}
    # 20:10(현 21:30) OpenAI 가 타임아웃·빈 응답으로 끝난 날의 행 — `model` 이 채워져
    # 있어 종전 2축 판정에서 '완성본' 으로 오분류됐다. **이 라우트의 존재 이유**가
    # 그날의 수동 복구인데 정작 그 경로가 막혀 있었다(통합 검증 F1).
    openai_failed = {"target_date": "2026-09-14",
                     "summary": OPENAI_EMPTY_RESPONSE_SUMMARY,
                     "model": "gpt-5-mini",
                     "metrics": {"logs": {"total_logs": 12}}}
    gen = AsyncMock(return_value={"id": "new"})
    for existing in (None, snapshot_only, openai_failed):
        gen.reset_mock()
        with patch.object(route, "get_log_report", AsyncMock(return_value=existing)), \
                patch.object(route, "generate_daily_log_report", gen):
            resp = await route.run_now()
        assert gen.await_count == 1, f"완성본이 없는데 막혔다 (existing={existing!r})"
        assert resp.success is True


@pytest.mark.asyncio
async def test_c283_c9b_5_both_axes_of_the_snapshot_verdict_are_live():
    """스냅샷 판정의 두 축(`snapshot_pass` 센티널 · 실패 placeholder)이 **각각** 산다.

    같은 `summary`(1차 스냅샷 문구)를 두고 `model` 만 다른 두 행을 **대조**한다 —
    한 축만으로 판정하면 둘 중 하나가 반드시 틀린다.
    """
    from src.routes import log_reports as route
    from src.engine.daily_metrics_snapshot import SNAPSHOT_SUMMARY

    # 센티널이 있으면 `model` 이 채워져 있어도 1차 행이다 → 막지 않는다.
    snapshot_with_model = {"summary": SNAPSHOT_SUMMARY, "model": "gpt-5-mini",
                           "metrics": {"snapshot_pass": 1}}
    assert route._is_complete_report(snapshot_with_model) is False, (
        "`metrics.snapshot_pass` 센티널을 무시한다 — 1차 행을 완성본으로 오분류"
    )
    # 센티널이 없고 `model` 도 없으면(=1차 행의 기본형) 역시 완성본이 아니다.
    assert route._is_complete_report({"summary": SNAPSHOT_SUMMARY, "model": None}) is False, (
        "`model` 축이 죽었다 — `summary` 만으로 판정하면 20:05~21:30 수동 실행이 전부 막힌다"
    )
    # 네 축을 모두 만족하는 행만 완성본이다.
    assert route._is_complete_report(
        {"summary": "오늘의 분석", "model": "gpt-5-mini", "metrics": {"logs": {}}}
    ) is True
    assert route._is_complete_report(None) is False
