"""일일 로그 리포트 — 수집/집계 계층 (리팩토링 카드 ⑦, cycle259).

`log_analysis_engine.py`(922L)에서 분리한 것이다 — system_logs/trade_history 조회부터
전략 funnel·포트폴리오 리스크 스냅샷까지 **수집·집계**만 이 모듈이 담당한다. LLM 호출
(OpenAI)과 `daily_log_reports` INSERT 는 `log_analysis_engine.py` 에 남고, 그 모듈이
이 모듈의 `collect_daily_log_metrics`/`DAILY_LOG_FETCH_LIMIT`/`HIGH_SEVERITY_FETCH_CAP`
/`KST`/`_build_portfolio_risk_snapshot` 를 **재export**한다(`routes/log_reports.py:13`
의 `from src.engine.log_analysis_engine import ...` 는 무변경 — 그 재export 를 그대로
쓴다).

이동은 **행위 보존**이다 — 함수 본문은 이동 전과 byte 동일이다(`_build_portfolio_risk_snapshot`
의 계좌 게이트 관측 부분만 예외: 같은 사이클의 카드 ⑥ 이 `get_gate_state()` +
`_eval_timeout_count()` 두 벌 호출을 `account_risk_watcher.get_gate_snapshot()` 단일
위임으로 바꾼다 — 이 함수 본문 변경은 그 카드가 요구하는 것이지 이동이 만든 것이
아니다).

`collect_daily_log_metrics` 의 반환 dict 는 그대로 (a) OpenAI 프롬프트 본문
(b) `daily_log_reports.metrics` JSONB (c) 20:20 클라우드 루틴 번들이다 — 키 **집합·순서**
는 계약이다(cycle249 C-1).
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from datetime import time as _dtime
from typing import Any

import src.db.pg as pg
from src.api.base import get_request_metrics
from src.db.strategy_funnel import list_snapshots
from src.db.trade_history import get_today_buy_trades_for_funnel, get_trades_in_range

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

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


async def _build_portfolio_risk_snapshot(_now_kst: datetime | None = None) -> dict | None:
    """포트폴리오 리스크 관찰 스냅샷 빌드 (사이클 H) — 20:10 리포트 metrics seam.

    registry 전 전략 + KIS 순자산 + 보유 ticker 섹터 분류를 pull 하여
    `compute_portfolio_risk_snapshot` 호출. 관찰 전용(매수 차단 0). lazy import 로
    순환 방지(scheduler ↔ log_metrics_collector). 호출부가 try/except 로 흡수하므로
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

    # cycle251 — 계좌 SOFT Σ상한 게이트 관측 부착 (후속 G, 관측 전용). over_cap 과
    # 독립된 별도 try — 한쪽 실패가 다른 쪽을 삼키지 않는다. cycle259 카드 ⑥ — 조립은
    # watcher 단일 소유 `get_gate_snapshot()`(무발화, `is_soft_gated()` 호출 금지 —
    # cycle233 F1 / cycle239 R1 동형) 하나로 위임한다. 두 소비자(이 함수 · `routes/
    # portfolio.py::get_portfolio_risk`)가 같은 형상을 내는 것이 카드 ⑥ 의 계약이다.
    try:
        from src.engine import account_risk_watcher
        snapshot["account_gate"] = account_risk_watcher.get_gate_snapshot()
    except Exception:
        logger.debug("[portfolio_risk] account_gate 관측 실패 graceful", exc_info=True)

    return snapshot


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
