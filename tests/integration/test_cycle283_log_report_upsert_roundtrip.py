"""cycle283 Red — `insert_log_report` upsert 실 Postgres 왕복 (C14 ⑥).

`tests/unit/db/test_cycle283_log_report_upsert.py` 는 `pg.fetchrow` 를 monkeypatch 해
**SQL 문자열**만 검증한다(ON CONFLICT 타깃·SET 절 컬럼 집합). 이 파일은 그 SQL 이 실제
`daily_log_reports` 테이블에 대해 **정말로** 그렇게 동작하는지를 mock 없이 실증한다:

- 20:05 1차 스냅샷 → 21:30 완전판이 **같은 행**을 쓴다(행 1개).
- 그 사이 20:20 클라우드 루틴(`upsert_external_report`)이 쓴 `ext_*` 6컬럼이
  21:30 upsert 에 **지워지지 않는다**.
- `created_at` 은 1차가 만든 값 그대로(갱신되지 않는다).
- 순서를 뒤집어도(20:34 루틴 먼저 → 21:30) 양방향으로 보존된다.

두 함수의 SET 절은 **교집합이 공집합**이다 — `upsert_external_report` 는 `ext_*` 6개뿐,
`insert_log_report` 는 base 9개뿐. 그 사실이 두 순서 모두에서 상호 보존을 만든다.

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_D = date(2026, 9, 14)

_SNAPSHOT_METRICS = {
    "logs": {"total_logs": 18_421},
    "api_metrics": {"total": 4_821, "err_5xx": 3},
    "strategy_funnel": {"donchian_swing": {"signals": 12, "orders": 2, "fills": 2}},
}
_FULL_METRICS = {
    "logs": {"total_logs": 19_002},
    "api_metrics": {"total": 4_990, "err_5xx": 3},
    "strategy_funnel": {"donchian_swing": {"signals": 12, "orders": 2, "fills": 2}},
}

_EXT = dict(
    provider="claude-routine",
    model="opus-5",
    summary="20:20 클라우드 루틴 요약",
    findings=[{"category": "trading", "severity": "low", "title": "T", "detail": "D"}],
    report_md="# 리포트\n본문",
)


async def _snapshot_pass():
    """20:05 1차 — OpenAI 미호출이라 model/토큰 전부 NULL."""
    from src.db import log_reports

    return await log_reports.insert_log_report(
        target_date=_D,
        summary="",
        findings=[],
        metrics=_SNAPSHOT_METRICS,
        model=None,
    )


async def _full_pass():
    """21:30 완전판 — OpenAI 메타 포함."""
    from src.db import log_reports

    return await log_reports.insert_log_report(
        target_date=_D,
        summary="완전판 요약 — 체결 2건, WARNING 5건",
        findings=[{"category": "api", "severity": "medium", "title": "5xx", "detail": "d"}],
        metrics=_FULL_METRICS,
        model="gpt-5.6-luna",
        input_tokens=1200,
        output_tokens=400,
        total_tokens=1600,
        latency_ms=3210,
        cost_estimate_usd=Decimal("0.021500"),
    )


# ---------------------------------------------------------------------------
# A — 1차 → 2차: 같은 행, 완전판이 덮어쓴다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c283_pg_1_snapshot_then_full_pass_is_one_row(clean_log_reports):
    from src.db import log_reports

    first = await _snapshot_pass()
    assert first is not None, "1차 저장이 행을 못 만들었다"
    created_at = first["created_at"]

    second = await _full_pass()
    assert second is not None, (
        "🔴 완전판이 `None` 을 돌려줬다 — 순수 INSERT 그대로다. 그러면 그날 `metrics` "
        "JSONB 가 통째로 유실되고 `log_analysis_engine` 의 `if row:` 는 조용히 끝난다"
    )

    count = await clean_log_reports.fetchval(
        "SELECT count(*) FROM daily_log_reports WHERE target_date = $1", _D
    )
    assert count == 1, f"같은 영업일에 행이 {count}개다 — upsert 가 아니라 중복 INSERT 다"

    row = await log_reports.get_log_report(_D)
    assert row["summary"] == "완전판 요약 — 체결 2건, WARNING 5건"
    assert row["model"] == "gpt-5.6-luna"
    assert row["metrics"]["api_metrics"]["total"] == 4_990
    assert row["total_tokens"] == 1600
    assert row["created_at"] == created_at, (
        "`created_at` 이 갱신됐다 — DO UPDATE SET 에 들어가면 안 된다 "
        "(행의 최초 생성 시각을 잃는다)"
    )


# ---------------------------------------------------------------------------
# B — 3자 공존: 20:05 → 20:34 루틴 → 21:30
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c283_pg_2_three_writers_coexist_in_order(clean_log_reports):
    """D+1 판독의 핵심 서명 — 행 1개 안에 세 주체의 결과가 모두 살아 있다."""
    from src.db import log_reports

    await _snapshot_pass()
    await log_reports.upsert_external_report(target_date=_D, **_EXT)
    await _full_pass()

    row = await log_reports.get_log_report(_D)
    assert row["summary"].startswith("완전판"), "base 컬럼 = 21:30 완전판"
    assert row["ext_provider"] == "claude-routine", (
        "🔴 21:30 upsert 가 `ext_provider` 를 지웠다 — SET 절에서 `ext_` 가 샜다"
    )
    assert row["ext_summary"] == _EXT["summary"]
    assert row["ext_report_md"] == _EXT["report_md"]
    assert row["ext_created_at"] is not None
    assert row["metrics"]["api_metrics"]["total"] == 4_990


# ---------------------------------------------------------------------------
# C — 역순: 20:34 루틴이 먼저 (1차가 실패한 날)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c283_pg_3_routine_first_then_full_pass(clean_log_reports):
    """루틴 placeholder 가 먼저인 날에도 21:30 이 `metrics` 를 남긴다.

    이것이 D6 의 존재 이유다 — 정산이 21:30 이 되면 루틴(20:34)이 **거의 항상 먼저**다.
    순수 INSERT 였다면 여기서 UNIQUE 충돌 → `None` → 그날 `metrics` 통째 유실이었다.
    """
    from src.db import log_reports

    await log_reports.upsert_external_report(target_date=_D, **_EXT)
    row = await _full_pass()
    assert row is not None

    row = await log_reports.get_log_report(_D)
    assert row["metrics"]["api_metrics"]["total"] == 4_990, (
        "루틴이 먼저 만든 placeholder 위에 완전판 metrics 가 안 실렸다"
    )
    assert row["model"] == "gpt-5.6-luna"
    assert row["ext_provider"] == "claude-routine", "루틴 결과가 지워졌다"


# ---------------------------------------------------------------------------
# D — C9-b: 비파괴 모드는 기존 행을 건드리지 않는다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c283_pg_4_on_conflict_nothing_preserves_the_complete_row(clean_log_reports):
    """`on_conflict='nothing'` — 21:30 이후 수동 재실행의 안전 모드.

    upsert 이후 `POST /api/log-reports/run` 재실행은 21:30 정산
    (`reset_request_metrics()` + `_reset_daily_state()`) **뒤**라면 `api_metrics` 0 ·
    `strategy_funnel` 0 을 새로 만들어 그날 완성 리포트를 덮어쓴다. 기본은 비파괴다.
    """
    from src.db import log_reports

    await _full_pass()
    out = await log_reports.insert_log_report(
        target_date=_D,
        summary="",                       # 21:30 이후 재실행이 만드는 빈 값
        findings=[],
        metrics={"api_metrics": {"total": 0}, "strategy_funnel": {}},
        model=None,
        on_conflict="nothing",
    )
    assert out is None, "`DO NOTHING` 은 RETURNING 이 비어 None 이다"

    row = await log_reports.get_log_report(_D)
    assert row["summary"].startswith("완전판"), "비파괴 모드가 완성본을 덮어썼다"
    assert row["metrics"]["api_metrics"]["total"] == 4_990
    assert row["model"] == "gpt-5.6-luna"
