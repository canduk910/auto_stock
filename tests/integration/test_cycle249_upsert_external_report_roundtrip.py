"""cycle249 위생 (5) — `upsert_external_report` 실 Postgres 왕복.

`tests/unit/db/test_cycle249_upsert_external_report.py` 는 `pg.fetchrow` 를
monkeypatch 해 **SQL 문자열**만 검증한다(멱등 규칙·SET 절 컬럼 집합·바인딩 타입).
이 파일은 그 SQL 이 실제 `daily_log_reports` 테이블에 대해 **정말로** 그렇게
동작하는지 — `ON CONFLICT (target_date) DO UPDATE` 가 물리적으로 기존 OpenAI 컬럼을
건드리지 않는지, `target_date` UNIQUE 제약이 정말로 이후 `insert_log_report` 를
튕기는지 — 를 mock 없이 실증한다(계획 3대 리스크 1순위: JSONB codec + 실 SQL 안전망,
`tests/integration/test_cycleM1_2_four_modules_roundtrip.py` 패턴 답습).

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_D = date(2026, 9, 4)

#: `upsert_external_report` 가 절대 건드리면 안 되는 20:10 OpenAI 경로의 기존 컬럼값.
_OPENAI_SUMMARY = "체결 3건, WARNING 2건 — OpenAI 경로 원본 요약"
_OPENAI_FINDINGS = [{"category": "trading", "severity": "medium", "title": "T", "detail": "D"}]
_OPENAI_METRICS = {"logs": {"total_logs": 42}, "trades": {"trades_total": 3}}
_OPENAI_MODEL = "gpt-5.6-luna"


async def _insert_openai_row():
    from src.db import log_reports

    return await log_reports.insert_log_report(
        target_date=_D,
        summary=_OPENAI_SUMMARY,
        findings=_OPENAI_FINDINGS,
        metrics=_OPENAI_METRICS,
        model=_OPENAI_MODEL,
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        latency_ms=2345,
        cost_estimate_usd=Decimal("0.012345"),
    )


# ---------------------------------------------------------------------------
# A — OpenAI 행이 먼저 있는 정상 순서: ext_* 만 갱신, 기존 컬럼 불변
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upsert_after_openai_row_then_existing_columns_untouched(clean_log_reports):
    """A — 20:10 OpenAI INSERT 후 20:20 upsert 를 **두 번**(재시도 흉내) 호출해도,
    기존 컬럼(summary/findings/metrics/model/토큰 5 + created_at/id)은 최초 INSERT
    값 그대로고, `ext_*` 만 **최신 호출값**으로 갱신된다(`DO UPDATE SET` 이 ext_* 밖으로
    새지 않는다는 unit 테스트의 SQL 문자열 가드를 실 SQL 로 확증).
    """
    from src.db import log_reports

    inserted = await _insert_openai_row()
    assert inserted is not None, "OpenAI 경로 INSERT 가 실패했다(전제 붕괴)"

    row1 = await log_reports.upsert_external_report(
        target_date=_D,
        provider="claude-code",
        model="claude-opus-5",
        summary="1차 외부 분석 요약",
        findings=[{"category": "trading", "severity": "high", "title": "E1", "detail": "d1"}],
        report_md="# 1차 리포트",
    )
    assert row1 is not None

    row2 = await log_reports.upsert_external_report(
        target_date=_D,
        provider="claude-code",
        model="claude-opus-6",
        summary="2차 외부 분석 요약(재시도)",
        findings=[{"category": "trading", "severity": "low", "title": "E2", "detail": "d2"}],
        report_md="# 2차 리포트",
    )
    assert row2 is not None

    got = await log_reports.get_log_report(_D)
    assert got is not None

    # 기존 컬럼 — 최초 OpenAI INSERT 값 그대로(두 번의 ext upsert 에도 불변).
    assert got["id"] == inserted["id"], "id 가 바뀌었다 — UPSERT 가 새 행을 만들었다"
    assert got["target_date"] == _D
    assert got["summary"] == _OPENAI_SUMMARY, "OpenAI summary 가 ext upsert 로 지워졌다"
    assert got["findings"] == _OPENAI_FINDINGS, "OpenAI findings 가 ext upsert 로 지워졌다"
    assert got["metrics"] == _OPENAI_METRICS, "OpenAI metrics 가 ext upsert 로 지워졌다"
    assert got["model"] == _OPENAI_MODEL, "OpenAI model 이 ext upsert 로 지워졌다"
    assert got["input_tokens"] == 1000
    assert got["output_tokens"] == 500
    assert got["total_tokens"] == 1500
    assert got["latency_ms"] == 2345
    assert got["cost_estimate_usd"] == Decimal("0.012345")
    assert got["created_at"] == inserted["created_at"], (
        "created_at 이 바뀌었다 — INSERT 가 아니라 새 행 취급됐다"
    )

    # ext_* — 두 번째(최신) 호출값으로 갱신돼 있어야 한다(DO UPDATE 실증).
    assert got["ext_provider"] == "claude-code"
    assert got["ext_model"] == "claude-opus-6"
    assert got["ext_summary"] == "2차 외부 분석 요약(재시도)"
    assert got["ext_findings"] == [
        {"category": "trading", "severity": "low", "title": "E2", "detail": "d2"}
    ]
    assert got["ext_report_md"] == "# 2차 리포트"
    assert got["ext_created_at"] is not None


# ---------------------------------------------------------------------------
# B — 빈 테이블에 upsert 가 먼저 도착: placeholder 행 위에 OpenAI 경로가 실린다
#     🔁 cycle283 재표현 (2026-09-11)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upsert_before_openai_row_then_insert_log_report_fills_base_columns(
    clean_log_reports,
):
    """B — 빈 테이블에 `upsert_external_report` 가 먼저 행을 만든(placeholder) 뒤에도
    같은 날짜의 `insert_log_report` 가 base 9컬럼을 **정상 기록**하고 `ext_*` 는 보존된다.

    🔁 **cycle283 재표현.** 종전 단언은 "순수 INSERT 라 UNIQUE 충돌 → `None`" 이었고,
    그것이 이 사이클이 **고친 결함**이다: 정산이 21:30 으로 밀리면서 20:20 클라우드
    루틴(POST 실측 20:34~20:54)이 거의 항상 **먼저** 행을 만들게 됐고, 그러면 그날
    `metrics` JSONB 가 통째로 유실됐다(호출부 `log_analysis_engine` 이 `if row:` 뿐이라
    조용히 끝난다). 이제 `insert_log_report` 는 `ON CONFLICT (target_date) DO UPDATE`
    이고 SET 절이 base 9컬럼뿐이라 **양방향 보존**이 성립한다.

    이 테스트가 지키는 *원 의도*(= 행은 하나 · ext_* 는 이 함수 호출값 그대로)는 그대로다.
    """
    from src.db import log_reports

    placeholder = await log_reports.upsert_external_report(
        target_date=_D,
        provider="claude-code",
        model="claude-opus-5",
        summary="OpenAI 경로보다 먼저 도착한 외부 분석",
        findings=[],
        report_md=None,
    )
    assert placeholder is not None

    written = await _insert_openai_row()
    assert written is not None, (
        "placeholder 행이 있다고 insert_log_report 가 None 을 돌려줬다 — "
        "그러면 그날 `metrics` JSONB 가 통째로 유실된다 (cycle283 D6 가 고친 결함)"
    )

    got = await log_reports.get_log_report(_D)
    assert got is not None
    # base 컬럼 = OpenAI 경로가 덮어쓴 값 (cycle283: 종전에는 빈 placeholder 값이었다)
    assert got["summary"] != "", "base 컬럼이 placeholder 빈 값에 고착됐다"
    assert got["model"] is not None
    # ext_* 는 placeholder 호출값 그대로 — 두 SET 절의 교집합이 공집합이라 상호 보존.
    assert got["ext_provider"] == "claude-code"
    assert got["ext_summary"] == "OpenAI 경로보다 먼저 도착한 외부 분석"

    rows = await log_reports.list_log_reports()
    assert len(rows) == 1, "target_date UNIQUE 인데 행이 2개다"
