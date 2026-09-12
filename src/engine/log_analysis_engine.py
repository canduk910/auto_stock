"""일일 시스템 로그 분석 엔진 — LLM 호출/저장 계층 (리팩토링 카드 ⑦, cycle259).

수집/집계 계층(system_logs/trade_history 조회부터 포트폴리오 리스크 스냅샷까지)은
`src/engine/log_metrics_collector.py` 로 분리됐다(이 파일 922L → 이 파일). 이 모듈은
OpenAI 호출·응답 검증·비용 계산과 `daily_log_reports` INSERT 만 담당하고,
`collect_daily_log_metrics`/`DAILY_LOG_FETCH_LIMIT`/`HIGH_SEVERITY_FETCH_CAP`/`KST`/
`_build_portfolio_risk_snapshot` 는 collector 에서 **재export**한다 —
`routes/log_reports.py:13` 의 `from src.engine.log_analysis_engine import ...` 는 이
재export 덕에 무변경이다.

매일 정산(21:30, cycle283) 직후 호출되어 당일 system_logs + trade_history를 집계하고
OpenAI에 개선 리포트 생성을 요청한 뒤 daily_log_reports에 저장한다.

생성 결과 스키마:
- summary: 1~2 문장 한국어 총평
- findings: [{category, severity, title, detail, suggestion}, ...]
- metrics: 원본 집계 (레벨별 카운트, 상위 WARNING 패턴, 거래/체결 통계) —
  `log_metrics_collector.collect_daily_log_metrics` 산출을 그대로 프롬프트/INSERT 에 싣는다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from src.api.base import reset_request_metrics
from src.config import settings
from src.db.log_reports import insert_log_report
from src.engine.log_metrics_collector import (
    DAILY_LOG_FETCH_LIMIT,
    HIGH_SEVERITY_FETCH_CAP,
    KST,
    _build_portfolio_risk_snapshot,
    collect_daily_log_metrics,
)

# 재export 계약(카드 ⑦) — `routes/log_reports.py:13` 과 테스트가 위 5 이름을 **이 모듈**
# 에서 가져간다. 본문이 안 쓰는 3(`DAILY_LOG_FETCH_LIMIT` · `HIGH_SEVERITY_FETCH_CAP` ·
# `_build_portfolio_risk_snapshot`)은 `__all__` 선언이 없으면 lint 상 unused import 라
# 자동 정리(ruff --fix 등)가 재export 를 조용히 지운다(cycle259 F2). 여기 목록은
# 재export 5 + 이 모듈의 공개 API 이지 routes 가 import 하는 전부가 아니다
# (`_validate_report` 는 이 모듈 소유 private — 이름으로 직접 import 되므로 무관).
__all__ = [
    # collector 재export
    "DAILY_LOG_FETCH_LIMIT",
    "HIGH_SEVERITY_FETCH_CAP",
    "KST",
    "_build_portfolio_risk_snapshot",
    "collect_daily_log_metrics",
    # LLM 계층 공개 API
    "generate_daily_log_report",
    "OPENAI_EMPTY_RESPONSE_SUMMARY",
]

logger = logging.getLogger(__name__)

#: OpenAI 가 타임아웃·빈 응답으로 끝난 날 `summary` 에 들어가는 **실패 placeholder**.
#: 모듈 상수인 이유: `POST /api/log-reports/run` 의 재실행 가드가 "완성본" 과 "실패한
#: 날의 행" 을 구별하려면 **같은 문자열 하나**를 봐야 한다. 리터럴을 두 벌로 두면
#: 그 판정이 조용히 어긋나 OpenAI 실패일의 수동 복구가 막힌다(이 라우트의 존재 이유).
OPENAI_EMPTY_RESPONSE_SUMMARY = (
    "AI 분석 응답을 받지 못했거나 빈 결과입니다 — 입력 메트릭만 보존합니다."
)

# 사이클 58 V-2 (2026-06-04) — OpenAI 모델별 토큰 단가 (USD per 1K tokens)
# (input_per_1k, output_per_1k)
# 미등록 모델 → cost_estimate_usd=None + WARNING [openai_pricing_miss]
_OPENAI_PRICING: dict[str, tuple[float, float]] = {
    "gpt-5.6-luna": (0.0010, 0.0060),
    "gpt-5.4": (0.0050, 0.0150),
    "gpt-4o": (0.0025, 0.0100),
    "gpt-4o-mini": (0.00015, 0.00060),
    "gpt-4-turbo": (0.0100, 0.0300),
    "gpt-4": (0.0300, 0.0600),
    "gpt-3.5-turbo": (0.0005, 0.0015),
}


@dataclass
class _OpenAIMeta:
    """OpenAI 호출 메타 — tokens / latency / cost."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    cost_estimate_usd: Decimal | None = None


def _compute_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    """모델·토큰 수 → 추정 비용(USD).

    미등록 모델은 None 반환 (호출자가 [openai_pricing_miss] 로그 처리).
    """
    pricing = _OPENAI_PRICING.get(model)
    if pricing is None:
        return None
    input_per_1k, output_per_1k = pricing
    cost = (input_tokens / 1000 * input_per_1k) + (output_tokens / 1000 * output_per_1k)
    return Decimal(str(round(cost, 6)))

ALLOWED_SEVERITIES = {"high", "medium", "low"}
ALLOWED_CATEGORIES = {
    "trading", "order", "websocket", "scan", "balance",
    "settlement", "data_quality", "infra", "etc",
}

SYSTEM_PROMPT = (
    "너는 한국 주식 자동매매 시스템의 운영 엔지니어다.\n"
    "당일 시스템 로그 집계와 거래 통계를 받아, 운영 개선 리포트를 작성한다.\n"
    "허용 출력 JSON 스키마만 사용:\n"
    '{"summary": "<1~2 문장 한국어 총평>",\n'
    ' "findings": [\n'
    '   {"category": "<trading|order|websocket|scan|balance|settlement|data_quality|infra|etc>",\n'
    '    "severity": "<high|medium|low>",\n'
    '    "title": "<한 줄 요약>",\n'
    '    "detail": "<무엇이 일어났는지 — 근거 로그/숫자 포함>",\n'
    '    "suggestion": "<구체적인 액션. 코드 변경/파라미터 조정/모니터링 항목 등>"}\n'
    " ]}\n"
    "규칙:\n"
    "- 같은 패턴 반복은 묶어 한 finding으로 작성. 핵심 3~7개로 압축.\n"
    "- WARNING/ERROR가 없으면 findings는 빈 배열, summary는 '특이사항 없음' 류로.\n"
    "- 숫자/시각/종목코드 등 사실은 입력 데이터를 인용하고 추측 금지.\n"
    "- **표본 절단 주의**: `logs.truncated` 가 true 면 원문 로그는 "
    "`logs.covered_from`~`logs.covered_to` 구간만 수집된 것이다(상한 초과). "
    "이때 `logs.level_counts` 는 표본 건수일 뿐이므로 **총계는 반드시 "
    "`logs.level_counts_actual`(DB 전수 집계)을 인용**하고, 하루 전체를 본 것처럼 "
    "서술하지 말고 summary 에 분석 구간을 명시하라. "
    "ERROR/CRITICAL 은 절단과 무관하게 전량 포함돼 있다.\n"
    "- 한국어로 출력."
)


def _validate_report(raw: dict) -> tuple[str, list[dict]]:
    """LLM 응답을 검증해 (summary, findings)로 정리."""
    summary = str(raw.get("summary") or "").strip()[:1000]
    raw_findings = raw.get("findings") or []
    findings: list[dict] = []
    if not isinstance(raw_findings, list):
        return summary, findings

    for item in raw_findings:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "etc").lower().strip()
        if category not in ALLOWED_CATEGORIES:
            category = "etc"
        severity = str(item.get("severity") or "medium").lower().strip()
        if severity not in ALLOWED_SEVERITIES:
            severity = "medium"
        title = str(item.get("title") or "").strip()[:200]
        detail = str(item.get("detail") or "").strip()[:1500]
        suggestion = str(item.get("suggestion") or "").strip()[:1000]
        if not title or not detail:
            continue
        findings.append({
            "category": category,
            "severity": severity,
            "title": title,
            "detail": detail,
            "suggestion": suggestion,
        })
        if len(findings) >= 15:
            break

    return summary, findings


async def _call_openai(
    client: Any,
    metrics: dict,
    model: str,
) -> tuple[dict | None, _OpenAIMeta]:
    """OpenAI에 분석 요청 — (parsed_result, meta) 반환.

    사이클 58 V-2: client/model 을 호출자에서 주입받아 메타 수집 후 반환한다.
    예외 발생 시 result=None + latency_ms 만 채워진 meta 반환 (graceful).
    """
    meta = _OpenAIMeta()
    start = time.monotonic()

    user_msg = (
        "아래는 당일 시스템 로그 집계와 거래 통계다.\n"
        "이를 보고 운영 개선 리포트를 위 스키마에 맞춰 JSON으로 작성하라.\n\n"
        + json.dumps(metrics, ensure_ascii=False, indent=2, default=str)
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
        meta.latency_ms = int((time.monotonic() - start) * 1000)

        # 사용량 메타 수집
        usage = getattr(response, "usage", None)
        if usage is not None:
            meta.input_tokens = getattr(usage, "prompt_tokens", None)
            meta.output_tokens = getattr(usage, "completion_tokens", None)
            meta.total_tokens = getattr(usage, "total_tokens", None)
            if meta.input_tokens is not None and meta.output_tokens is not None:
                meta.cost_estimate_usd = _compute_cost_usd(
                    model, meta.input_tokens, meta.output_tokens
                )
                if meta.cost_estimate_usd is None:
                    logger.warning(
                        "[openai_pricing_miss] model=%s — cost_estimate_usd=None", model
                    )

        # 응답 파싱
        content = response.choices[0].message.content or "{}"
        return json.loads(content), meta

    except Exception:
        meta.latency_ms = int((time.monotonic() - start) * 1000)
        logger.exception("[openai_call_failed] model=%s", model)
        return None, meta


async def generate_daily_log_report(
    _now_kst: datetime | None = None,
) -> dict | None:
    """매일 정산(21:30, cycle283 D3) 직후 호출.

    당일 KST 00:00 ~ now 사이의 system_logs + trade_history를 집계해
    OpenAI에 분석 요청 → daily_log_reports INSERT.

    Args:
        _now_kst: 테스트용 현재 시각 override. None 이면 datetime.now(KST) 사용.

    Returns:
        INSERT된 row, 이미 존재하거나 OpenAI 비활성/실패 시 None.
    """
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY 미설정 — 로그 분석 리포트 건너뜀")
        return None

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.error("openai 패키지가 설치되지 않았습니다")
        return None

    now_kst = _now_kst if _now_kst is not None else datetime.now(KST)
    target_date = now_kst.date()

    # 1. 데이터 수집 — cycle249: `collect_daily_log_metrics` 로 추출(20:20 클라우드
    # 루틴의 번들 GET 과 같은 함수를 공유한다). `now_kst` 를 그대로 넘겨 기존
    # `_now_kst` 주입 seam(장중 수동 호출·`run_now`)을 byte 동일 보존한다.
    metrics = await collect_daily_log_metrics(target_date, now_kst=now_kst)

    # 2. OpenAI 호출 (60초 타임아웃) — 사이클 58 V-2: client/model 주입 + meta 수집
    model = settings.openai_recommend_model
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    meta = _OpenAIMeta()
    try:
        raw, meta = await asyncio.wait_for(
            _call_openai(client, metrics, model), timeout=60
        )
    except asyncio.TimeoutError:
        logger.warning("OpenAI 호출 타임아웃 (log analysis)")
        raw = None

    if raw is None:
        raw = {}

    summary, findings = _validate_report(raw)
    if not summary and not findings:
        summary = OPENAI_EMPTY_RESPONSE_SUMMARY

    # 3. upsert (cycle283 D6 — `ON CONFLICT (target_date) DO UPDATE`, base 9컬럼만).
    #    20:05 1차 스냅샷 행을 이 완전판이 덮어쓰고, 20:20 클라우드 루틴의 `ext_*` 는 보존된다.
    # 사이클 58 V-2: OpenAI 메타(tokens/latency/cost) 함께 저장
    row = await insert_log_report(
        target_date=target_date,
        summary=summary,
        findings=findings,
        metrics=metrics,
        model=model,
        input_tokens=meta.input_tokens,
        output_tokens=meta.output_tokens,
        total_tokens=meta.total_tokens,
        latency_ms=meta.latency_ms,
        cost_estimate_usd=meta.cost_estimate_usd,
    )
    if row:
        logger.info(
            "로그 분석 리포트 저장 완료 — %s, findings %d건",
            target_date, len(findings),
        )
    else:
        # cycle283 — upsert 이후 이 분기는 **정상 경로에서 도달 불가**하다.
        # 살아 있는 이유는 하나: `ON CONFLICT` 타깃이 어긋났을 때 울리는 유일한 종이다.
        # (종전에는 else 가 없어 그날 `metrics` JSONB 유실이 아무 소리 없이 지나갔다.)
        logger.warning(
            "[daily_log_report_not_saved] target_date=%s — 저장 결과가 비었다. "
            "insert_log_report 의 ON CONFLICT 타깃(target_date)을 확인하라",
            target_date,
        )
    # 리포트 INSERT 후 api 메트릭 리셋 — 다음 영업일 누적 시작
    reset_request_metrics()
    return row
