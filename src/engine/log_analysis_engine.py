"""일일 시스템 로그 분석 엔진.

매일 정산(16:10) 직후 호출되어 당일 system_logs + trade_history를 집계하고
OpenAI에 개선 리포트 생성을 요청한 뒤 daily_log_reports에 저장한다.

생성 결과 스키마:
- summary: 1~2 문장 한국어 총평
- findings: [{category, severity, title, detail, suggestion}, ...]
- metrics: 원본 집계 (레벨별 카운트, 상위 WARNING 패턴, 거래/체결 통계)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any

from src.config import settings
from src.db.log_reports import insert_log_report
from src.db.supabase import supabase
from src.db.trade_history import get_trades_in_range

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

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
    "- 한국어로 출력."
)

# 패턴 추출용 정규식 — 종목코드(6자리)/숫자/주문번호 등 제거 후 패턴화
_TICKER_RE = re.compile(r"\b[0-9A-Z]{6}\b")
_NUMBER_RE = re.compile(r"\b\d{4,}\b")


def _normalize_message(msg: str) -> str:
    """반복 패턴 집계용으로 메시지에서 가변 부분(종목코드/숫자)을 마스킹."""
    msg = _TICKER_RE.sub("<TICKER>", msg)
    msg = _NUMBER_RE.sub("<N>", msg)
    return msg.strip()[:200]


async def _fetch_logs_in_range(start: datetime, end: datetime, limit: int = 5000) -> list[dict]:
    """기간 내 system_logs를 시간 오름차순으로 가져온다."""
    result = (
        supabase.table("system_logs")
        .select("timestamp, log_level, message")
        .gte("timestamp", start.isoformat())
        .lte("timestamp", end.isoformat())
        .order("timestamp", desc=False)
        .limit(limit)
        .execute()
    )
    return result.data or []


def _aggregate_logs(logs: list[dict]) -> dict[str, Any]:
    """로그를 레벨별/패턴별로 집계한다."""
    by_level: Counter[str] = Counter()
    pattern_by_level: dict[str, Counter[str]] = {
        "WARNING": Counter(), "ERROR": Counter(), "CRITICAL": Counter(),
    }
    samples_by_level: dict[str, list[dict]] = {
        "WARNING": [], "ERROR": [], "CRITICAL": [],
    }

    for row in logs:
        level = (row.get("log_level") or "").upper()
        msg = row.get("message") or ""
        by_level[level] += 1
        if level in pattern_by_level:
            norm = _normalize_message(msg)
            pattern_by_level[level][norm] += 1
            # 샘플은 패턴별 첫 등장만 유지 (최대 8개)
            if len(samples_by_level[level]) < 8 and pattern_by_level[level][norm] == 1:
                samples_by_level[level].append({
                    "ts": row.get("timestamp"),
                    "message": msg[:300],
                })

    # 상위 패턴 N개씩
    top_patterns: dict[str, list[dict]] = {}
    for level, counter in pattern_by_level.items():
        top_patterns[level] = [
            {"pattern": pat, "count": cnt}
            for pat, cnt in counter.most_common(10)
        ]

    return {
        "level_counts": dict(by_level),
        "top_patterns": top_patterns,
        "samples": samples_by_level,
        "total_logs": len(logs),
    }


def _aggregate_trades(trades: list[dict]) -> dict[str, Any]:
    """trade_history 메트릭 집계."""
    by_strategy: Counter[str] = Counter()
    buys = 0
    sells = 0
    realized_pnl = 0.0
    pending = 0
    completed = 0
    cancelled = 0

    for t in trades:
        strat = t.get("strategy") or "unknown"
        by_strategy[strat] += 1
        ttype = t.get("trade_type")
        status = (t.get("status") or "").upper()
        if ttype == "BUY":
            buys += 1
        elif ttype == "SELL":
            sells += 1
            try:
                realized_pnl += float(t.get("profit_loss") or 0)
            except (TypeError, ValueError):
                pass
        if status == "PENDING":
            pending += 1
        elif status == "COMPLETED":
            completed += 1
        elif status == "CANCELLED":
            cancelled += 1

    return {
        "trades_total": len(trades),
        "buy_count": buys,
        "sell_count": sells,
        "realized_pnl": round(realized_pnl, 0),
        "by_strategy": dict(by_strategy),
        "by_status": {
            "PENDING": pending, "COMPLETED": completed, "CANCELLED": cancelled,
        },
    }


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


async def _call_openai(metrics: dict) -> dict:
    """OpenAI에 분석 요청. 실패 시 빈 dict."""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.error("openai 패키지가 설치되지 않았습니다")
        return {}

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    user_msg = (
        "아래는 당일 시스템 로그 집계와 거래 통계다.\n"
        "이를 보고 운영 개선 리포트를 위 스키마에 맞춰 JSON으로 작성하라.\n\n"
        + json.dumps(metrics, ensure_ascii=False, indent=2, default=str)
    )

    try:
        response = await client.chat.completions.create(
            model=settings.openai_recommend_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
    except Exception:
        logger.exception("OpenAI 호출 실패 (log analysis)")
        return {}

    try:
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
    except (json.JSONDecodeError, IndexError, AttributeError):
        logger.exception("OpenAI 응답 파싱 실패 (log analysis)")
        return {}


async def generate_daily_log_report() -> dict | None:
    """매일 정산(16:10) 직후 호출.

    당일 KST 00:00 ~ now 사이의 system_logs + trade_history를 집계해
    OpenAI에 분석 요청 → daily_log_reports INSERT.

    Returns:
        INSERT된 row, 이미 존재하거나 OpenAI 비활성/실패 시 None.
    """
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY 미설정 — 로그 분석 리포트 건너뜀")
        return None

    now_kst = datetime.now(KST)
    target_date = now_kst.date()
    start_kst = datetime.combine(target_date, datetime.min.time(), tzinfo=KST)

    # 1. 데이터 수집
    logs = await _fetch_logs_in_range(start_kst, now_kst)
    trades = await get_trades_in_range(target_date, target_date)

    log_metrics = _aggregate_logs(logs)
    trade_metrics = _aggregate_trades(trades)

    metrics = {
        "target_date": target_date.isoformat(),
        "logs": log_metrics,
        "trades": trade_metrics,
    }

    logger.info(
        "로그 분석 리포트 입력 — logs %d건 (W:%d, E:%d, C:%d), trades %d건",
        log_metrics["total_logs"],
        log_metrics["level_counts"].get("WARNING", 0),
        log_metrics["level_counts"].get("ERROR", 0),
        log_metrics["level_counts"].get("CRITICAL", 0),
        trade_metrics["trades_total"],
    )

    # 2. OpenAI 호출 (60초 타임아웃)
    try:
        raw = await asyncio.wait_for(_call_openai(metrics), timeout=60)
    except asyncio.TimeoutError:
        logger.warning("OpenAI 호출 타임아웃 (log analysis)")
        raw = {}

    summary, findings = _validate_report(raw)
    if not summary and not findings:
        summary = "AI 분석 응답을 받지 못했거나 빈 결과입니다 — 입력 메트릭만 보존합니다."

    # 3. INSERT (UNIQUE 충돌 시 None — 재실행 안전)
    row = await insert_log_report(
        target_date=target_date,
        summary=summary,
        findings=findings,
        metrics=metrics,
        model=settings.openai_recommend_model,
    )
    if row:
        logger.info(
            "로그 분석 리포트 저장 완료 — %s, findings %d건",
            target_date, len(findings),
        )
    return row
