"""daily_log_reports CRUD.

사이클 M1-2 (Supabase→RDS 이전 단계1 증분2): supabase-py → `src.db.pg`(asyncpg) 전환.
함수 시그니처·반환형 100% 보존 — 호출부(log_analysis_engine 등) diff 0.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

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
) -> dict | None:
    """일일 로그 분석 리포트를 INSERT한다.

    (target_date) UNIQUE — 동일 영업일 재실행 시 None 반환.

    사이클 58 V-2: OpenAI 호출 메타(tokens/latency/cost)를 함께 기록한다.
    모두 NULL 허용 — 기존 row 자연 보존.
    """
    sql = """
        INSERT INTO daily_log_reports (
            target_date, summary, findings, metrics, model,
            input_tokens, output_tokens, total_tokens, latency_ms,
            cost_estimate_usd, created_at
        ) VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6, $7, $8, $9, $10, $11)
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
            logger.info("daily_log_reports 중복 (이미 존재): %s", target_date)
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
    `target_date` 는 UNIQUE 이므로, 이 함수가 먼저 placeholder 행을 만들면 그날의
    `insert_log_report`(OpenAI 경로, 순수 `INSERT`)는 그 UNIQUE 충돌을 그대로 맞고
    `None` 을 반환한다(중복 시 `None` 은 그 함수의 기존 계약). 빈 값 채우기의 목적은
    오직 "호출자 데이터가 기존 컬럼에 심기지 않게" 하는 것뿐이다. 정상 운영 순서
    (20:10 OpenAI → 20:20 이 함수)에서는 행이 이미 있으므로 이 경로는 발생하지 않지만,
    **순서를 뒤집어 수동 호출**(디버깅·백필)할 때는 이 함수를 먼저 부르면 그날의
    OpenAI 리포트가 영구히 만들어지지 않는다는 점을 알고 있어야 한다.
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
