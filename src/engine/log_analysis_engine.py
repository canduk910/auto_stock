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
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from datetime import time as _dtime
from decimal import Decimal
from typing import Any

import src.db.pg as pg
from src.api.base import get_request_metrics, reset_request_metrics
from src.config import settings
from src.db.log_reports import insert_log_report
from src.db.strategy_funnel import list_snapshots
from src.db.trade_history import get_today_buy_trades_for_funnel, get_trades_in_range

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

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

# 패턴 추출용 정규식 — 종목코드(6자리)/숫자/주문번호 등 제거 후 패턴화
_TICKER_RE = re.compile(r"\b[0-9A-Z]{6}\b")
_NUMBER_RE = re.compile(r"\b\d{4,}\b")


def _normalize_message(msg: str) -> str:
    """반복 패턴 집계용으로 메시지에서 가변 부분(종목코드/숫자)을 마스킹."""
    msg = _TICKER_RE.sub("<TICKER>", msg)
    msg = _NUMBER_RE.sub("<N>", msg)
    return msg.strip()[:200]


_LOGS_TS_SELECT = (
    "to_char(timestamp, 'YYYY-MM-DD\"T\"HH24:MI:SS.US+09:00') AS timestamp"
)

# 원문 로그 fetch 총 상한 (사이클 53.1 = 30,000). 08-03 실측 97,353건이 이를 3.2배
# 초과해 리포트가 07:45~09:47 두 시간만 보고 하루를 판정했다 → 절단 감지 의무.
DAILY_LOG_FETCH_LIMIT = 30_000
# ERROR/CRITICAL 전량 확보 상한 (평시 수십 건 — 사실상 무제한 역할).
HIGH_SEVERITY_FETCH_CAP = 5_000


async def _fetch_logs_in_range(start: datetime, end: datetime, limit: int = 5000) -> list[dict]:
    """기간 내 system_logs를 시간 오름차순으로 가져온다.

    RDS(pg) 페이지드 SELECT (LIMIT/OFFSET, 사이클 M5 — PostgREST 1000행 cap 대체).
    `limit` 은 *총* 한도 (예: limit=5000 → 최대 5페이지).
    빈 페이지 또는 <1000건 페이지 도달 시 종료. timestamp 는 `+09:00` KST str 캐스트
    (사이클 53 B-4 계약 — `_aggregate_logs` 등 소비처 str 계약 보존).
    """
    PAGE_SIZE = 1000
    all_rows: list[dict] = []
    offset = 0
    while offset < limit:
        page_limit = min(PAGE_SIZE, limit - offset)
        rows = await pg.fetch(
            f"""
            SELECT {_LOGS_TS_SELECT}, log_level, message FROM system_logs
            WHERE timestamp >= $1 AND timestamp <= $2
            ORDER BY timestamp ASC
            LIMIT $3 OFFSET $4
            """,
            start,
            end,
            page_limit,
            offset,
        )
        page = rows or []
        all_rows.extend(page)
        if len(page) < page_limit:
            break
        offset += page_limit
    return all_rows


async def _count_logs_by_level(start: datetime, end: datetime) -> dict[str, int]:
    """기간 내 **진짜** 레벨별 총계 (원문 fetch 절단과 무관).

    `_fetch_logs_in_range` 는 상한이 걸리면 조용히 끊기므로, 건수만큼은 DB 집계로
    따로 구한다. 실패는 graceful — 총계 없이도 리포트는 나가야 한다 (사이클 88).
    """
    try:
        rows = await pg.fetch(
            """
            SELECT log_level, count(*) AS cnt FROM system_logs
            WHERE timestamp >= $1 AND timestamp <= $2
            GROUP BY log_level
            """,
            start,
            end,
        )
    except Exception:
        logger.debug("[log_report] 레벨별 총계 집계 실패 graceful", exc_info=True)
        return {}
    return {
        str(r["log_level"]).upper(): int(r["cnt"])
        for r in (rows or [])
        if r.get("log_level")
    }


async def _fetch_high_severity_logs(
    start: datetime, end: datetime, limit: int = HIGH_SEVERITY_FETCH_CAP,
) -> list[dict]:
    """ERROR/CRITICAL 만 별도 전량 확보 (원문 cap 과 무관).

    일반 fetch 가 ASC 로 잘리면 오후 ERROR 가 통째로 사라진다. 가장 중요한 신호는
    절대 잘리지 않도록 레벨 필터를 건 별도 쿼리로 가져온다. ERROR/CRITICAL 은
    평시 수십 건 수준이라 상한(기본 5,000)에 닿지 않는다. 실패는 graceful.
    """
    try:
        rows = await pg.fetch(
            f"""
            SELECT {_LOGS_TS_SELECT}, log_level, message FROM system_logs
            WHERE timestamp >= $1 AND timestamp <= $2
              AND log_level IN ('ERROR', 'CRITICAL')
            ORDER BY timestamp ASC
            LIMIT $3
            """,
            start,
            end,
            limit,
        )
    except Exception:
        logger.debug("[log_report] ERROR/CRITICAL 전량 fetch 실패 graceful", exc_info=True)
        return []
    return list(rows or [])


def _merge_high_severity(logs: list[dict], high: list[dict]) -> list[dict]:
    """절단된 원문에 cap 밖 ERROR/CRITICAL 을 합친다 (중복 제거 + 시간 오름차순).

    동일 `(timestamp, log_level, message)` 는 1건으로 — 두 쿼리의 겹치는 구간이
    이중 집계되면 패턴 카운트가 부풀려진다.
    """
    if not high:
        return logs
    seen = {
        (r.get("timestamp"), r.get("log_level"), r.get("message"))
        for r in logs
    }
    merged = list(logs)
    for r in high:
        key = (r.get("timestamp"), r.get("log_level"), r.get("message"))
        if key not in seen:
            seen.add(key)
            merged.append(r)
    merged.sort(key=lambda r: str(r.get("timestamp") or ""))
    return merged


def _aggregate_logs(logs: list[dict], fetch_limit: int | None = None) -> dict[str, Any]:
    """로그를 레벨별/패턴별로 집계한다.

    `fetch_limit` 전달 시 표본 절단 여부(`truncated`)와 실제로 본 시간 구간
    (`covered_from`/`covered_to`)을 함께 싣는다. 리포트가 하루 전체를 본 것처럼
    보이지 않게 하기 위한 것 — 미전달 시 기존 계약 그대로(`truncated=False`).
    """
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

    # 커버 구간은 **상한이 걸리는 레벨**(ERROR/CRITICAL 제외) 기준으로 잡는다.
    # ERROR/CRITICAL 은 별도 쿼리로 전량 병합되므로, 그 시각까지 포함하면 다른
    # 레벨도 거기까지 수집된 것처럼 보이는 역-오인이 생긴다.
    capped = [
        str(r.get("timestamp")) for r in logs
        if r.get("timestamp") and (r.get("log_level") or "").upper() not in ("ERROR", "CRITICAL")
    ]
    if not capped:  # 전량이 ERROR/CRITICAL 인 희소한 날 — 전체 기준으로 폴백
        capped = [str(r.get("timestamp")) for r in logs if r.get("timestamp")]
    # 절단 판정도 capped 레벨 건수 기준 (병합분이 상한을 넘겨 오판정하지 않게).
    capped_count = sum(
        1 for r in logs if (r.get("log_level") or "").upper() not in ("ERROR", "CRITICAL")
    )
    return {
        "level_counts": dict(by_level),
        "top_patterns": top_patterns,
        "samples": samples_by_level,
        "total_logs": len(logs),
        # 표본 절단 관측 — 리포트가 하루 전체를 본 것처럼 오인되지 않게 한다.
        "fetched_logs": len(logs),
        "truncated": bool(fetch_limit) and capped_count >= int(fetch_limit),
        "covered_from": min(capped) if capped else None,
        "covered_to": max(capped) if capped else None,
        "coverage_note": (
            "covered_from~covered_to 는 ERROR/CRITICAL 을 제외한 레벨의 수집 구간이다. "
            "ERROR/CRITICAL 은 상한과 무관하게 전량 포함."
        ),
    }


# cycle234 — tick blind 계측 집계 (uptime_monitor 부팅 갭 로그, G2 대체 조치 ①)
_TICK_BLIND_RE = re.compile(
    r"\[tick_blind_boot\](?:\s+downtime_secs=(\d+)\s+market_blind_secs=(\d+))?"
)


def _aggregate_tick_blind(logs: list[dict]) -> dict[str, int]:
    """`[tick_blind_boot]` 집계 — 일 단위 프로세스 부재 blind 총량.

    `market_blind_secs_total` 이 자문 cycle232 §3.5 가 요구한 "그 숫자"다 —
    서버 스탑(역지정가) 편익의 정량 분자. first_boot 행은 boot_count 만 올린다.
    """
    boot_count = 0
    downtime_total = 0
    market_total = 0
    for row in logs:
        msg = row.get("message") or ""
        m = _TICK_BLIND_RE.search(msg)
        if m:
            boot_count += 1
            if m.group(1):
                downtime_total += int(m.group(1))
                market_total += int(m.group(2))
    return {
        "boot_count": boot_count,
        "downtime_secs_total": downtime_total,
        "market_blind_secs_total": market_total,
    }


# PR-B (2026-05-14): 구조화 prefix 카운팅
_NDC_DEFERRED_RE = re.compile(r"\[next_day_clear_deferred\]")
_NDC_DRAINED_SUCCESS_RE = re.compile(r"\[next_day_clear_drained\][^\n]*result=success")
_NDC_DRAINED_FAIL_RE = re.compile(r"\[next_day_clear_drained\][^\n]*result=fail")


def _aggregate_next_day_clear(logs: list[dict]) -> dict[str, int]:
    """`[next_day_clear_*]` prefix 카운터 — Loki 검색 가능 메트릭."""
    deferred = 0
    drained_success = 0
    drained_fail = 0
    for row in logs:
        msg = row.get("message") or ""
        if _NDC_DEFERRED_RE.search(msg):
            deferred += 1
        elif _NDC_DRAINED_SUCCESS_RE.search(msg):
            drained_success += 1
        elif _NDC_DRAINED_FAIL_RE.search(msg):
            drained_fail += 1
    return {
        "deferred": deferred,
        "drained_success": drained_success,
        "drained_fail": drained_fail,
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
    # 종목별/시간대별 손익 분해 — SELL 거래만 집계
    ticker_pnl: dict[str, dict[str, float]] = {}
    hour_pnl: dict[str, dict[str, float]] = {}

    for t in trades:
        strat = t.get("strategy") or "unknown"
        by_strategy[strat] += 1
        ttype = t.get("trade_type")
        status = (t.get("status") or "").upper()
        if ttype == "BUY":
            buys += 1
        elif ttype == "SELL":
            sells += 1
            pnl = 0.0
            try:
                pnl = float(t.get("profit_loss") or 0)
            except (TypeError, ValueError):
                pnl = 0.0
            realized_pnl += pnl

            # 종목별
            ticker = t.get("ticker") or ""
            if ticker:
                bucket = ticker_pnl.setdefault(ticker, {"realized_pnl": 0.0, "sell_count": 0})
                bucket["realized_pnl"] += pnl
                bucket["sell_count"] += 1

            # 시간대별 (KST hour)
            ts = t.get("timestamp")
            if ts:
                try:
                    if isinstance(ts, str):
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    else:
                        dt = ts
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    hour_key = f"{dt.astimezone(KST).hour:02d}"
                    hbucket = hour_pnl.setdefault(hour_key, {"realized_pnl": 0.0, "sell_count": 0})
                    hbucket["realized_pnl"] += pnl
                    hbucket["sell_count"] += 1
                except (ValueError, TypeError):
                    pass

        if status == "PENDING":
            pending += 1
        elif status == "COMPLETED":
            completed += 1
        elif status == "CANCELLED":
            cancelled += 1

    # 종목별 상위 5개(절대값 큰 순)
    by_ticker_pnl = {
        ticker: {"realized_pnl": round(v["realized_pnl"], 0), "sell_count": v["sell_count"]}
        for ticker, v in sorted(
            ticker_pnl.items(), key=lambda x: -abs(x[1]["realized_pnl"])
        )[:5]
    }
    by_hour_pnl = {
        h: {"realized_pnl": round(v["realized_pnl"], 0), "sell_count": v["sell_count"]}
        for h, v in sorted(hour_pnl.items())
    }

    return {
        "trades_total": len(trades),
        "buy_count": buys,
        "sell_count": sells,
        "realized_pnl": round(realized_pnl, 0),
        "by_strategy": dict(by_strategy),
        "by_status": {
            "PENDING": pending, "COMPLETED": completed, "CANCELLED": cancelled,
        },
        "by_ticker_pnl": by_ticker_pnl,
        "by_hour_pnl": by_hour_pnl,
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


async def _build_portfolio_risk_snapshot(_now_kst: datetime | None = None) -> dict | None:
    """포트폴리오 리스크 관찰 스냅샷 빌드 (사이클 H) — 20:10 리포트 metrics seam.

    registry 전 전략 + KIS 순자산 + 보유 ticker 섹터 분류를 pull 하여
    `compute_portfolio_risk_snapshot` 호출. 관찰 전용(매수 차단 0). lazy import 로
    순환 방지(scheduler ↔ log_analysis_engine). 호출부가 try/except 로 흡수하므로
    치명 실패는 상위에서 None 처리.
    """
    from src.api.balance import get_balance
    from src.engine.portfolio_risk import (
        compute_portfolio_risk_snapshot,
        extract_hard_stop_pct,
    )
    from src.engine.scheduler import trading_scheduler
    from src.engine.sector_naming import resolve_sector_names

    strategies = list(trading_scheduler.registry.all())

    try:
        _holdings, summary = await get_balance()
        net_asset = int(getattr(summary, "net_asset", 0) or 0)
    except Exception:
        logger.debug("[portfolio_risk] get_balance 실패 graceful", exc_info=True)
        net_asset = 0

    hard_stop_pcts: dict[str, float] = {}
    held_tickers: set[str] = set()
    for strat in strategies:
        sid = getattr(strat, "strategy_id", None) or "unknown"
        config = getattr(strat, "config", None)
        params = (
            getattr(config, "params", None)
            if config is not None
            else getattr(strat, "params", None)
        )
        hard_stop_pcts[sid] = extract_hard_stop_pct(
            params if isinstance(params, dict) else None
        )
        state = getattr(strat, "state", None)
        positions = getattr(state, "positions", None) if state is not None else None
        if isinstance(positions, dict):
            held_tickers.update(positions.keys())

    # 섹터명 해석은 `sector_naming` 단일 진실원에 위임 (portfolio 라우트와 동일 계약).
    sector_of = await resolve_sector_names(held_tickers)

    # cycle233 — 척도 병기: 전략이 노출하는 실효 손절선 주입 (fail-open — 미구현/예외
    # 전략은 프록시 폴백). 관찰 전용 — 매매 상태 무변경.
    strat_by_id = {
        (getattr(s, "strategy_id", None) or "unknown"): s for s in strategies
    }

    def _stop_of(sid: str, ticker: str):
        fn = getattr(strat_by_id.get(sid), "get_effective_stop_price", None)
        if not callable(fn):
            return None
        try:
            return fn(ticker)
        except Exception:
            return None

    snapshot = compute_portfolio_risk_snapshot(
        strategies,
        net_asset=net_asset,
        hard_stop_pcts=hard_stop_pcts,
        sector_of=sector_of,
        stop_price_of=_stop_of,
    )
    # cycle233 — 1주 폴백 notional 초과 관측 (자문 cycle232 §정정 1, 관측 전용)
    try:
        from src.engine.portfolio_risk import compute_over_cap_positions
        snapshot["over_cap_positions"] = compute_over_cap_positions(strategies)
    except Exception:
        logger.debug("[portfolio_risk] over_cap 계산 실패 graceful", exc_info=True)
    return snapshot


async def collect_daily_log_metrics(
    target_date: date, *, now_kst: datetime | None = None
) -> dict:
    """대상 영업일의 system_logs + trade_history 를 집계해 `metrics` dict 를 만든다.

    cycle249 — `generate_daily_log_report` 의 "1. 데이터 수집" 블록을 추출한 것이다.
    20:20 KST 클라우드 루틴이 `GET /api/log-reports/bundle` 로 읽는 번들이 이 함수의
    반환값과 **같은 것**이어야 병행 기간(OpenAI ↔ Claude) 비교가 성립한다.

    반환 dict 의 **키 집합·순서**는 종전 `generate_daily_log_report` 의 `metrics` 와
    정확히 같다 — 이 dict 는 그대로 (a) OpenAI 프롬프트 본문이고 (b)
    `daily_log_reports.metrics` JSONB 다.

    Args:
        target_date: 집계 대상 영업일.
        now_kst: 수집 윈도우의 끝(KST). None 이면 `target_date` 가 오늘(KST)일 때
            `datetime.now(KST)`(장중 수동 호출·`run_now` 경로 보존), 과거 날짜면
            그 날 23:59:59 KST(과거 날짜에 `now()` 를 쓰면 여러 날치 로그가 한 날
            리포트로 섞인다).
    """
    if now_kst is None:
        today = datetime.now(KST).date()
        if target_date == today:
            now_kst = datetime.now(KST)
        else:
            now_kst = datetime.combine(target_date, _dtime(23, 59, 59), tzinfo=KST)
    start_kst = datetime.combine(target_date, datetime.min.time(), tzinfo=KST)

    # 1. 데이터 수집
    # 사이클 53.1 — 운영 부피 18,000건/일 대비 30,000 (1.6배 마진).
    # 디폴트 5000 은 부족하여 drained(ASC 7,000+번) 누락 결함.
    logs = await _fetch_logs_in_range(start_kst, now_kst, limit=DAILY_LOG_FETCH_LIMIT)
    # ERROR/CRITICAL 은 상한과 무관하게 전량 — 원문이 ASC 로 잘리면 오후 ERROR 가
    # 통째로 사라진다(08-03 실측: cap 경계 09:47, 이후 ERROR 5건 전부 시야 밖).
    high_severity = await _fetch_high_severity_logs(start_kst, now_kst)
    logs = _merge_high_severity(logs, high_severity)
    trades = await get_trades_in_range(target_date, target_date)

    log_metrics = _aggregate_logs(logs, fetch_limit=DAILY_LOG_FETCH_LIMIT)
    # 진짜 총계는 원문 절단과 무관하게 DB 집계로 (표본 건수와 구분해 병기).
    log_metrics["level_counts_actual"] = await _count_logs_by_level(start_kst, now_kst)
    if log_metrics["truncated"]:
        logger.warning(
            "[log_report_truncated] 표본이 상한(%d)에 걸려 %s~%s 구간만 분석됨 "
            "— 실제 총계 %s. 리포트의 시간 범위 해석에 주의",
            DAILY_LOG_FETCH_LIMIT,
            log_metrics.get("covered_from"), log_metrics.get("covered_to"),
            log_metrics.get("level_counts_actual"),
        )
    trade_metrics = _aggregate_trades(trades)
    api_metrics = get_request_metrics()
    strategy_funnel = await _collect_strategy_funnel()
    strategy_funnel_stages = await _collect_strategy_funnel_stages(target_date)
    next_day_clear_metrics = _aggregate_next_day_clear(logs)
    tick_blind_metrics = _aggregate_tick_blind(logs)  # cycle234 — G2 정량 근거

    # 사이클 H — 포트폴리오 리스크 관찰 스냅샷 (전 전략 합산 오픈 리스크 + 섹터/전략별 노출).
    # 빌드 실패(잔고/registry 일시 장애)는 graceful → None (리포트 INSERT 는 보존, 사이클 88).
    try:
        portfolio_risk_snapshot = await _build_portfolio_risk_snapshot(now_kst)
    except Exception:
        logger.debug("[portfolio_risk] 스냅샷 빌드 실패 graceful", exc_info=True)
        portfolio_risk_snapshot = None

    metrics = {
        "target_date": target_date.isoformat(),
        "logs": log_metrics,
        "trades": trade_metrics,
        "api_metrics": api_metrics,
        "strategy_funnel": strategy_funnel,           # 병존 (coarse, 불변)
        "strategy_funnel_stages": strategy_funnel_stages,  # 신규 (E-1, 사이클 199)
        "next_day_clear": next_day_clear_metrics,
        "portfolio_risk_snapshot": portfolio_risk_snapshot,  # 신규 (사이클 H, 관찰 전용)
        "tick_blind": tick_blind_metrics,  # 신규 (cycle234 — 프로세스 부재 blind)
    }

    logger.info(
        "로그 분석 리포트 입력 — logs %d건 (W:%d, E:%d, C:%d), trades %d건",
        log_metrics["total_logs"],
        log_metrics["level_counts"].get("WARNING", 0),
        log_metrics["level_counts"].get("ERROR", 0),
        log_metrics["level_counts"].get("CRITICAL", 0),
        trade_metrics["trades_total"],
    )

    return metrics


async def generate_daily_log_report(
    _now_kst: datetime | None = None,
) -> dict | None:
    """매일 정산(16:10) 직후 호출.

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
        summary = "AI 분석 응답을 받지 못했거나 빈 결과입니다 — 입력 메트릭만 보존합니다."

    # 3. INSERT (UNIQUE 충돌 시 None — 재실행 안전)
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
    # 리포트 INSERT 후 api 메트릭 리셋 — 다음 영업일 누적 시작
    reset_request_metrics()
    return row


# 패턴 단계 키워드 (verdict 판정용). drop_step.step_name 이 이 중 하나를 포함하면
# "패턴희소", 아니면 (유니버스/필터/차단 등 이른 단계) "후보부족".
_PATTERN_STEP_KEYWORDS = (
    "신고가", "돌파", "폴", "플래그", "베이스", "Pullback", "수축", "검출", "EMA", "정렬",
    # kojiro 대순환 (2026-07) — ATR밴드/스테이지 붕괴 = 패턴희소 (후보부족 오분류 차단, obs-M)
    "스테이지", "변동성", "ATR", "밴드", "대순환",
)


async def _collect_strategy_funnel_stages(target_date: date) -> dict[str, dict]:
    """전략별 per-step funnel + 0신호 자동 판정 (E-1, 사이클 199).

    strategy_funnel_snapshots (DB) 를 읽어 전략별 단계별 생존 수 + verdict 산출.
    순수 관찰성 — 매매 무관. 실패/빈 → {} graceful (리포트 무중단, 사이클 88 패턴).
    """
    try:
        rows = await list_snapshots(target_date=target_date)
    except Exception:
        logger.exception("[funnel_stages] list_snapshots 실패 — graceful {}")
        return {}
    if not rows:
        return {}

    # strategy_id 별 그룹핑 (step_no != 99 만 파이프라인)
    by_sid: dict[str, list[dict]] = {}
    for row in rows:
        sid = row.get("strategy_id") or "unknown"
        by_sid.setdefault(sid, []).append(row)

    result: dict[str, dict] = {}
    for sid, sid_rows in by_sid.items():
        pipeline = sorted(
            (r for r in sid_rows if int(r.get("step_no", 0)) != 99),
            key=lambda r: int(r.get("step_no", 0)),
        )
        steps = [
            {
                "step_no": int(r.get("step_no", 0)),
                "step_name": r.get("step_name") or "",
                "survived_count": int(r.get("survived_count", 0)),
                "excluded_count": int(r.get("excluded_count", 0)),
            }
            for r in pipeline
        ]

        if not steps:
            result[sid] = {
                "steps": [], "peak_survived": 0, "final_prepared": 0,
                "drop_step": None, "verdict": "기록없음",
            }
            continue

        peak_survived = max(s["survived_count"] for s in steps)
        final_prepared = steps[-1]["survived_count"]  # 최대 step_no(≠99) survived

        # drop_step = 직전 step>0 → 현재 step==0 으로 처음 떨어지는 step
        drop_step = None
        for i in range(1, len(steps)):
            if steps[i - 1]["survived_count"] > 0 and steps[i]["survived_count"] == 0:
                drop_step = {"step_no": steps[i]["step_no"], "step_name": steps[i]["step_name"]}
                break

        # verdict
        if final_prepared > 0:
            verdict = "후보준비완료"
        elif drop_step is not None:
            if any(kw in drop_step["step_name"] for kw in _PATTERN_STEP_KEYWORDS):
                verdict = "패턴희소"
            else:
                verdict = "후보부족"
        else:
            verdict = "미상"

        result[sid] = {
            "steps": steps,
            "peak_survived": peak_survived,
            "final_prepared": final_prepared,
            "drop_step": drop_step,
            "verdict": verdict,
        }
    return result


async def _collect_strategy_funnel() -> dict[str, dict[str, int]]:
    """전략별 신호→주문→체결 카운터 수집 — 정산 후 _reset_daily_state 직전에 호출됨.

    PR-D (2026-05-14): EC2 재시작으로 in-memory 카운터가 휘발된 경우를 위해
    `trade_history` 당일 KST BUY 행으로 cross-check 보강한다.
    - fills  = max(in_memory, COMPLETED count)
    - orders = max(in_memory, all-status count: PENDING+COMPLETED+PARTIAL+CANCELLED)
    - signals = max(in_memory, orders)   # 단조성 signals ≥ orders ≥ fills

    PR-D 보강 (Copilot/Codex, 2026-05-14): `get_today_buy_trades_for_funnel()` 사용 —
    `get_today_buy_trades()` 는 포지션 복구용으로 ticker 별 dedupe + CANCELLED 제외라
    multi-BUY/multi-strategy/CANCELLED 시나리오를 under-count 하여 본래 목적 달성 못 함.

    in-memory 가 더 크면 그대로 사용 (재시작 없이 정상 수집된 케이스).
    DB 조회 실패 시 in-memory 만 사용 (예외 흡수).
    """
    try:
        from src.engine.scheduler import trading_scheduler
    except ImportError:
        return {}

    # 당일 KST BUY trade 집계 — DB 실패 시 빈 dict 로 fallback
    by_strategy_completed: dict[str, int] = {}
    by_strategy_all: dict[str, int] = {}
    try:
        today_buys = await get_today_buy_trades_for_funnel()
        for row in today_buys or []:
            sid = row.get("strategy") or "unknown"
            status = (row.get("status") or "").upper()
            by_strategy_all[sid] = by_strategy_all.get(sid, 0) + 1
            if status == "COMPLETED":
                by_strategy_completed[sid] = by_strategy_completed.get(sid, 0) + 1
    except Exception:
        logger.exception(
            "[funnel_crosscheck] get_today_buy_trades 실패 — in-memory 카운터만 사용"
        )

    funnel: dict[str, dict[str, int]] = {}
    for strategy in trading_scheduler.registry.all():
        s = strategy.state
        sid = strategy.strategy_id
        db_fills = by_strategy_completed.get(sid, 0)
        db_orders = by_strategy_all.get(sid, 0)
        # in-memory vs DB 중 큰 값 — 재시작 시 in-memory=0 이면 DB 보강
        fills = max(s.fill_count_today, db_fills)
        orders = max(s.order_attempt_today, db_orders)
        # signal 단조성: signals ≥ orders ≥ fills
        signals = max(s.signal_count_today, orders)
        funnel[sid] = {"signals": signals, "orders": orders, "fills": fills}
    return funnel
