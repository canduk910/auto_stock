"""daily_log_reports CRUD.

사이클 M1-2 (Supabase→RDS 이전 단계1 증분2): supabase-py → `src.db.pg`(asyncpg) 전환.
함수 시그니처·반환형 100% 보존 — 호출부(log_analysis_engine 등) diff 0.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

import src.db.pg as pg
from src.db._kst import now_kst_iso, to_date

logger = logging.getLogger(__name__)


async def insert_log_report(
    *,
    target_date: date,
    summary: str,
    findings: list[dict],
    metrics: dict,
    model: str | None,
    # 사이클 58 V-2 (2026-06-04) — OpenAI 메타 컬럼
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    latency_ms: int | None = None,
    cost_estimate_usd: Decimal | None = None,
    on_conflict: Literal["update", "nothing"] = "update",
) -> dict | None:
    """일일 로그 분석 리포트를 저장한다 — `ON CONFLICT (target_date)` upsert (cycle283 D6).

    `DO UPDATE SET` 절은 **base 9컬럼만**: summary / findings / metrics / model /
    input_tokens / output_tokens / total_tokens / latency_ms / cost_estimate_usd.

    🔴 `ext_provider`/`ext_model`/`ext_summary`/`ext_findings`/`ext_report_md`/
    `ext_created_at` 6컬럼은 SET 절에 **절대 넣지 않는다** — 한 컬럼이라도 새면 20:20
    클라우드 루틴 결과가 조용히 지워진다. `upsert_external_report` 가 정확히 반대
    방향으로 지키는 규약의 거울이고, 두 SET 절의 **교집합이 공집합**이라 어느 순서로
    쓰든 상호 보존된다. `created_at` 도 SET 절 밖 = 행의 최초 생성 시각 보존.

    왜 upsert 인가: 정산이 21:30(cycle283 D3)이 되면서 20:20 클라우드 루틴이 그날 행을
    **먼저** 만든다(placeholder INSERT, 실측 POST 20:34~20:54). 순수 INSERT 였다면 그날
    `metrics` JSONB 가 통째로 유실된다 — 호출부(`log_analysis_engine`)가 `if row:` 뿐이라
    조용히 끝나기 때문이다.

    Args:
        on_conflict: `"update"`(기본, 정산 경로의 계약 — 완전판이 1차 스냅샷을 덮어쓴다)
            또는 `"nothing"`(비파괴 — 기존 행이 있으면 손대지 않고 `None` 반환).
            ⚠️ **`"nothing"` 은 현재 프로덕션 호출자가 0건이다** — 호출부 두 곳
            (`daily_metrics_snapshot` · `log_analysis_engine`)이 둘 다 인자를 넘기지
            않는다. 오용 방어용 파라미터이고, `POST /api/log-reports/run` 의 비파괴는
            **라우트의 선조회 가드**(`_is_complete_report`)가 혼자 담당한다.
            라우트가 이 값을 쓰지 *않는* 이유: 20:05~21:30 구간엔 1차 스냅샷 행이 이미
            있으므로 `DO NOTHING` 이면 수동 실행의 완전판이 조용히 버려진다 — 여기서의
            "비파괴" 는 복구 경로를 막는 방향이다.

    Returns:
        저장/갱신된 row. `on_conflict="nothing"` + 기존 행 존재 시에만 `None`.

    사이클 58 V-2: OpenAI 호출 메타(tokens/latency/cost)를 함께 기록한다.
    모두 NULL 허용 — 기존 row 자연 보존.
    """
    if on_conflict not in ("update", "nothing"):
        raise ValueError(
            f"on_conflict 는 'update' | 'nothing' 만 허용 (실측 {on_conflict!r}) — "
            "오타가 조용히 파괴 방향(update)으로 떨어지면 안 된다"
        )
    conflict_clause = (
        """ON CONFLICT (target_date) DO UPDATE SET
            summary = EXCLUDED.summary,
            findings = EXCLUDED.findings,
            metrics = EXCLUDED.metrics,
            model = EXCLUDED.model,
            input_tokens = EXCLUDED.input_tokens,
            output_tokens = EXCLUDED.output_tokens,
            total_tokens = EXCLUDED.total_tokens,
            latency_ms = EXCLUDED.latency_ms,
            cost_estimate_usd = EXCLUDED.cost_estimate_usd"""
        if on_conflict == "update"
        else "ON CONFLICT (target_date) DO NOTHING"
    )
    sql = f"""
        INSERT INTO daily_log_reports (
            target_date, summary, findings, metrics, model,
            input_tokens, output_tokens, total_tokens, latency_ms,
            cost_estimate_usd, created_at
        ) VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6, $7, $8, $9, $10, $11)
        {conflict_clause}
        RETURNING *
    """
    # M6 — target_date DATE 컬럼 바인딩. str 입력도 date 로 강제 변환.
    bound_target_date = to_date(target_date)
    try:
        row = await pg.fetchrow(
            sql,
            bound_target_date,
            summary,
            findings,
            metrics,
            model,
            input_tokens,
            output_tokens,
            total_tokens,
            latency_ms,
            float(cost_estimate_usd) if cost_estimate_usd is not None else None,
            datetime.fromisoformat(now_kst_iso()),
        )
        return row
    except Exception as e:
        msg = str(e)
        if "duplicate key" in msg or "23505" in msg:
            # cycle283 이후 **정상 경로에서는 도달 불가**하다(ON CONFLICT 가 흡수한다).
            # 살아 있는 이유는 하나 — `ON CONFLICT` 타깃이 어긋났을 때 울리는 종이다.
            logger.warning(
                "[log_report_unexpected_conflict] daily_log_reports 중복 (%s) — "
                "ON CONFLICT 타깃이 어긋났는지 확인하라", target_date,
            )
            return None
        logger.exception("daily_log_reports INSERT 실패")
        raise


async def upsert_external_report(
    *,
    target_date: date,
    provider: str,
    model: str,
    summary: str,
    findings: list[dict],
    report_md: str | None,
) -> dict:
    """20:20 KST 클라우드 루틴 결과를 `ext_*` 6컬럼에만 저장한다(cycle249).

    병행 기간 동안 하루의 행에 20:10 OpenAI 경로(summary/findings/metrics/model +
    토큰 5)와 이 함수가 쓰는 `ext_*` 가 공존한다. `DO UPDATE SET` 절이 `ext_*` 밖으로
    한 컬럼이라도 새면 그날의 OpenAI 리포트(비교 기준선)가 지워지고 아무도 즉시
    알아채지 못한다 — 그래서 SET 절은 **ext_* 6개뿐**이다.

    행이 아직 없는 날(20:10 이 실패했거나 병행 종료 후)에도 저장돼야 하므로 INSERT
    경로의 기존 컬럼은 빈 값으로 채운다(호출자 데이터를 심지 않는다) — 이건
    `insert_log_report` 가 나중에 성공하도록 "튕김을 막는" 조치가 **아니다**.
    ⚠️ cycle283 정정 — 종전 이 자리에는 "이 함수가 먼저 placeholder 를 만들면 그날의
    `insert_log_report` 는 UNIQUE 충돌로 `None` 을 반환한다" 고 적혀 있었다. 그 서술은
    **반증됐다**: `insert_log_report` 도 이제 `ON CONFLICT (target_date) DO UPDATE` 라
    순서가 뒤집혀도 base 9컬럼을 정상 기록한다. 두 SET 절의 교집합이 공집합
    (여기 `ext_*` 6 / 저기 base 9)이라 **어느 쪽이 먼저 와도 상호 보존**된다. 정산이
    21:30 으로 밀린 뒤에는 이 함수(20:34 실측)가 먼저 오는 것이 오히려 정상 순서다.
    빈 값 채우기의 목적은 여전히 "호출자 데이터가 기존 컬럼에 심기지 않게" 하는 것뿐이다.
    """
    sql = """
        INSERT INTO daily_log_reports (
            target_date, summary, findings, metrics, model, created_at,
            ext_provider, ext_model, ext_summary, ext_findings, ext_report_md,
            ext_created_at
        ) VALUES (
            $1, '', '[]'::jsonb, '{}'::jsonb, NULL, $2,
            $3, $4, $5, $6::jsonb, $7, $8
        )
        ON CONFLICT (target_date) DO UPDATE SET
            ext_provider = EXCLUDED.ext_provider,
            ext_model = EXCLUDED.ext_model,
            ext_summary = EXCLUDED.ext_summary,
            ext_findings = EXCLUDED.ext_findings,
            ext_report_md = EXCLUDED.ext_report_md,
            ext_created_at = EXCLUDED.ext_created_at
        RETURNING *
    """
    bound_target_date = to_date(target_date)
    now = datetime.fromisoformat(now_kst_iso())
    row = await pg.fetchrow(
        sql,
        bound_target_date,
        now,
        provider,
        model,
        summary,
        findings,
        report_md,
        now,
    )
    return row


async def list_log_reports(days: int = 30) -> list[dict]:
    """최근 N일치 리포트를 신규순으로 조회한다."""
    rows = await pg.fetch(
        "SELECT * FROM daily_log_reports ORDER BY target_date DESC LIMIT $1",
        days,
    )
    return rows or []


async def get_log_report(target_date: date) -> dict | None:
    """단일 영업일 리포트를 조회한다."""
    return await pg.fetchrow(
        "SELECT * FROM daily_log_reports WHERE target_date = $1 LIMIT 1",
        to_date(target_date),
    )
