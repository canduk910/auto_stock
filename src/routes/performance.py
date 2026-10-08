"""매매 실적 라우트: /api/performance/*"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from src.db import trade_cost as trade_cost_db
from src.db.daily_performance import get_latest_performance, get_performance, recompute_from_trades
from src.engine import cost_overlay
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/performance", tags=["performance"])


async def _net_overlay_rows(records: list[dict], strategy: str) -> list[dict] | None:
    """`records`(daily_performance 행, 오름차순)에 실비용을 얹어 net TWR 을 재누적한다.

    조회 실패(DB 오류 등) = None — 호출부가 기존 gross 응답을 그대로 유지한다
    (사용자 결정 10-08 §2 `[cost_overlay_unavailable]`).
    """
    if not records:
        return []
    dates = [r["date"] for r in records]
    start, end = min(dates), max(dates)
    try:
        cost_rows = await trade_cost_db.get_daily_range(start, end)
        trades = await trade_cost_db.get_trades_by_status(start, end, ["COMPLETED", "PARTIAL"])
    except Exception:
        logger.warning("[cost_overlay_unavailable] /api/performance 실비용 조회 실패", exc_info=True)
        return None

    if strategy and strategy != "total":
        trades = [t for t in trades if t.get("strategy") == strategy]

    rates = cost_overlay.estimate_rates(cost_rows)
    tc_by_id = cost_overlay.trade_costs(cost_rows, trades, rates)

    by_date: dict = {}
    for t in trades:
        c = tc_by_id.get(t.get("id"))
        if c is None:
            continue
        acc = by_date.setdefault(t["trade_date"], {"fee": 0.0, "tax": 0.0, "statuses": []})
        acc["fee"] += c["fee"]
        acc["tax"] += c["tax"]
        acc["statuses"].append(c["cost_status"])

    costs_by_date = {
        d: {"fee": v["fee"], "tax": v["tax"], "cost_status": cost_overlay.day_cost_status(v["statuses"])}
        for d, v in by_date.items()
    }
    return cost_overlay.net_twr(records, costs_by_date)


@router.get("/summary", response_model=ApiResponse)
async def summary(strategy: str = "total"):
    """최근 30일 실적 요약. 누적은 TWR 복리, 평균은 일별 실현 수익률 평균."""
    records = await get_performance(days=30, strategy=strategy)
    if not records:
        return ApiResponse(success=True, data={
            "total_days": 0,
            "total_profit_rate": 0,
            "avg_daily_profit_rate": 0,
            "latest_asset": 0,
            "strategy": strategy,
            "net_total_profit_rate": 0,
            "net_avg_daily_profit_rate": 0,
        })

    latest = await get_latest_performance(strategy=strategy)
    cum_rate = float(latest.get("cumulative_return_rate", 0) or 0) if latest else 0.0

    daily_rates = [float(r.get("daily_profit_rate", 0) or 0) for r in records]
    avg_rate = sum(daily_rates) / len(daily_rates) if daily_rates else 0.0

    # cycle411 — net(세후) 누적·평균. 비용 조회가 실패하면 gross 값으로 폴백한다.
    # 🔴 수수료·세금은 % 로는 작아 round(…, 2) 로 gross 와 자릿수를 맞추면 두 값이 같은
    # 자리로 뭉개진다 — net 은 4자리로 둔다(비교 단언은 라운딩 전 크기 차이를 본다).
    net_total_profit_rate = round(cum_rate, 4)
    net_avg_daily_profit_rate = round(avg_rate, 4)
    net_rows = await _net_overlay_rows(records, strategy)
    if net_rows:
        net_total_profit_rate = round(net_rows[-1]["net_cumulative_return_rate"], 4)
        net_daily_rates = [r["net_daily_profit_rate"] for r in net_rows]
        if net_daily_rates:
            net_avg_daily_profit_rate = round(sum(net_daily_rates) / len(net_daily_rates), 4)

    return ApiResponse(
        success=True,
        data={
            "total_days": len(records),
            "total_profit_rate": round(cum_rate, 2),
            "avg_daily_profit_rate": round(avg_rate, 2),
            # `float()` 필수 — `daily_performance.total_asset` 은 NUMERIC 이라 asyncpg 가
            # Decimal 로 주고, pydantic v2 는 JSON 에서 Decimal 을 **문자열**로 직렬화한다.
            # 프론트 계약은 `latest_asset: number`(`types/trading.ts`)이고 `PerformanceCard`
            # 가 `.toLocaleString('ko-KR')` 를 직접 걸어, 문자열이면 `Object.prototype` 쪽으로
            # 떨어져 천단위 구분이 사라진다. 같은 dict 의 다른 두 수치는 위에서 이미 float 다.
            "latest_asset": float(records[-1]["total_asset"] or 0) if records else 0,
            "strategy": strategy,
            "net_total_profit_rate": net_total_profit_rate,
            "net_avg_daily_profit_rate": net_avg_daily_profit_rate,
        },
    )


@router.post("/recompute", response_model=ApiResponse)
async def recompute():
    """trade_history 기반 daily_performance 전체 소급 재계산.

    매일 정산(_settle) 후 자동 호출되지만, 거래 내역이 보정된 경우
    수동 호출하여 즉시 반영할 수 있다. 멱등.
    """
    ok = await recompute_from_trades()
    return ApiResponse(
        success=ok,
        message="일별 실적 재계산 완료" if ok else "재계산 실패",
    )


@router.get("/daily", response_model=ApiResponse)
async def daily(days: int = 30, strategy: str = "total"):
    """일별 실적 데이터를 반환한다.

    응답 필드:
    - daily_profit_rate: 일별 실현손익 기반 수익률(%)
    - cumulative_return_rate: TWR 복리 누적 수익률(%)
    - daily_realized_pnl: 당일 실현손익
    - net_external_cashflow: 외부 입출금 추정 (입금 +, 출금 −)
    - total_asset: 정산 시점 순자산
    - deposit: 정산 시점 예수금
    - daily_fee·daily_tax·daily_net_pnl·net_daily_profit_rate·net_cumulative_return_rate·
      cost_status(cycle411 — 실비용 합치기, 비용 조회 실패 시 전부 None)
    """
    records = await get_performance(days=days, strategy=strategy)
    rows = [dict(r) for r in records]
    net_rows = await _net_overlay_rows(records, strategy)
    if net_rows is None:
        for r in rows:
            r["daily_fee"] = None
            r["daily_tax"] = None
            r["daily_net_pnl"] = None
            r["net_daily_profit_rate"] = None
            r["net_cumulative_return_rate"] = None
            r["cost_status"] = None
    else:
        net_by_date = {n["date"]: n for n in net_rows}
        for r in rows:
            n = net_by_date.get(r["date"], {})
            r["daily_fee"] = n.get("daily_fee", 0.0)
            r["daily_tax"] = n.get("daily_tax", 0.0)
            r["daily_net_pnl"] = n.get("daily_net_pnl", float(r.get("daily_realized_pnl") or 0.0))
            r["net_daily_profit_rate"] = n.get("net_daily_profit_rate", float(r.get("daily_profit_rate") or 0.0))
            r["net_cumulative_return_rate"] = n.get(
                "net_cumulative_return_rate", float(r.get("cumulative_return_rate") or 0.0)
            )
            r["cost_status"] = n.get("cost_status")
    return ApiResponse(success=True, data=rows)
