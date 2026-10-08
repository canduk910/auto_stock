"""실비용 라우트: /api/costs/* (트랙 C).

- `POST /api/costs/reconcile?from=YYYY-MM-DD&to=YYYY-MM-DD` — KIS `TTTC8715R` 정산값을 가져와
  `trade_cost_daily` 에 저장한다(백필 겸용, 운영자 수동 실행). 실제 KIS 를 부른다.
- `GET /api/costs/summary?from=&to=&strategy=` — 전략별 gross·수수료·세금·net·실효 왕복 bp·슬리피지.
- `GET /api/costs/today?strategy=` — 오늘 체결 × (정산 or 추정 요율), 전략별 + total
  (OrderMonitor 용, cycle411 — scheduler 무접촉 경로).
- `GET /api/costs/daily?from=&to=` — 날짜별 비용·슬리피지·`cost_status` 추이(cycle411).
- `GET /api/costs/schedule` · `PUT /api/costs/schedule {"time":"HH:MM"|null,"days":1~31}` — 매일 자동
  대사 시각(`system_config.trade_cost_reconcile_time`). 시각은 루프 수명 `[07:45, 21:30)` 안만 받는다
  (밖이면 영영 발화하지 않는다) · `time: null` = 끄기(cycle409 — 사용자 결정 10-04 Q1).

오류를 삼키지 않는다 — 날짜 형식·순서·범위 422 · 모의 환경 409 · KIS 거부 502 · 그 밖 500
(+`[trade_cost_route_error]`). 빈 결과로 위장하면 「비용 0」 으로 읽힌다.
`Decimal` 은 여기서 `float` 로 사영한다(pydantic v2 는 `Decimal` 을 JSON 문자열로 낸다).
인증은 최외곽 미들웨어 단일 지점이 맡는다(POST 는 리포터 스코프에서 403).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.api.base import KisApiError
from src.api.trade_profit import RealEnvRequired
from src.db import system_config
from src.db import trade_cost as trade_cost_db
from src.db._kst import today_kst
from src.engine import cost_overlay
from src.engine import trade_cost
from src.engine import trade_cost_reconcile_task as reconcile_task
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/costs", tags=["costs"])

_MARKER_ERROR = "[trade_cost_route_error]"
_MAX_SPAN_DAYS = 366


def _parse_range(from_: str, to: str) -> tuple[date, date]:
    try:
        if len(from_) != 10 or len(to) != 10:
            raise ValueError
        start, end = date.fromisoformat(from_), date.fromisoformat(to)
    except ValueError:
        raise HTTPException(status_code=422, detail="from/to 는 YYYY-MM-DD 여야 한다")
    if start > end:
        raise HTTPException(status_code=422, detail="from 이 to 보다 늦다")
    if (end - start).days + 1 > _MAX_SPAN_DAYS:
        raise HTTPException(status_code=422, detail=f"기간은 {_MAX_SPAN_DAYS}일 이하")
    return start, end


def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


@router.post("/reconcile")
async def reconcile_costs(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
) -> ApiResponse:
    start, end = _parse_range(from_, to)
    try:
        result = await trade_cost.reconcile(start, end)
    except RealEnvRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except KisApiError as exc:
        logger.warning("%s reconcile KIS 거부 msg_cd=%s msg1=%s", _MARKER_ERROR, exc.msg_cd, exc.msg1)
        raise HTTPException(status_code=502, detail=f"KIS 거부 [{exc.msg_cd}] {exc.msg1}")
    except Exception as exc:
        logger.warning("%s reconcile 실패: %r", _MARKER_ERROR, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="실비용 대사 실패")
    return ApiResponse(success=True, data=_plain(result), message="")


@router.get("/summary")
async def cost_summary(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    strategy: str | None = Query(None),
) -> ApiResponse:
    start, end = _parse_range(from_, to)
    try:
        result = await trade_cost.build_summary(start, end, strategy)
    except Exception as exc:
        logger.warning("%s summary 실패: %r", _MARKER_ERROR, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="실비용 요약 조회 실패")
    return ApiResponse(success=True, data=_plain(result), message="")


@router.get("/today")
async def costs_today(strategy: str | None = Query(None)) -> ApiResponse:
    """오늘 체결 × (정산 or 추정 요율) — 전략별 + total (OrderMonitor 용, cycle411).

    `scheduler.py` 무접촉 경로 — `trade_cost_db`·`cost_overlay` 만 읽는다.
    """
    today = today_kst()
    try:
        cost_rows = await trade_cost_db.get_daily_range(today, today)
        trades = await trade_cost_db.get_trades_by_status(today, today, ["COMPLETED", "PARTIAL"])
    except Exception as exc:
        logger.warning("%s today 조회 실패: %r", _MARKER_ERROR, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="오늘 실비용 조회 실패")

    if strategy:
        trades = [t for t in trades if t.get("strategy") == strategy]

    rates = cost_overlay.estimate_rates(cost_rows)
    costs = cost_overlay.trade_costs(cost_rows, trades, rates)

    by_strategy: dict[str, dict] = {}
    for t in trades:
        sid = t.get("strategy") or trade_cost.UNATTRIBUTED
        c = costs.get(t.get("id"), {"fee": 0.0, "tax": 0.0, "cost_status": "estimated"})
        acc = by_strategy.setdefault(sid, {"gross_pnl": 0.0, "fee": 0.0, "tax": 0.0})
        if str(t.get("trade_type") or "").upper() == "SELL":
            acc["gross_pnl"] += float(t.get("profit_loss") or 0.0)
        acc["fee"] += c["fee"]
        acc["tax"] += c["tax"]

    strategies = []
    for sid in sorted(by_strategy):
        v = by_strategy[sid]
        net_pnl = v["gross_pnl"] - v["fee"] - v["tax"]
        strategies.append({"strategy": sid, "gross_pnl": v["gross_pnl"], "fee": v["fee"],
                           "tax": v["tax"], "net_pnl": net_pnl})

    total = {
        "gross_pnl": sum(s["gross_pnl"] for s in strategies),
        "fee": sum(s["fee"] for s in strategies),
        "tax": sum(s["tax"] for s in strategies),
        "net_pnl": sum(s["net_pnl"] for s in strategies),
    }
    statuses = [c["cost_status"] for c in costs.values()] or ["estimated"]

    return ApiResponse(success=True, data={
        "date": today.isoformat(),
        "fee_rate": rates["fee_rate"],
        "tax_rate": rates["tax_rate"],
        "rate_source": rates["source"],
        "cost_status": cost_overlay.day_cost_status(statuses),
        "strategies": strategies,
        "total": total,
    }, message="")


@router.get("/daily")
async def costs_daily(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
) -> ApiResponse:
    """날짜별 비용·슬리피지·`cost_status` 추이(cycle411)."""
    start, end = _parse_range(from_, to)
    try:
        cost_rows = await trade_cost_db.get_daily_range(start, end)
        trades = await trade_cost_db.get_trades_by_status(start, end, ["COMPLETED", "PARTIAL"])
    except Exception as exc:
        logger.warning("%s daily 조회 실패: %r", _MARKER_ERROR, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="실비용 일별 조회 실패")

    rates = cost_overlay.estimate_rates(cost_rows)
    costs = cost_overlay.trade_costs(cost_rows, trades, rates)

    by_date: dict[date, dict] = {}
    for t in trades:
        d = t.get("trade_date")
        if d is None:
            continue
        c = costs.get(t.get("id"), {"fee": 0.0, "tax": 0.0, "cost_status": "estimated"})
        acc = by_date.setdefault(d, {"fee": 0.0, "tax": 0.0, "statuses": [],
                                     "slippage_won": 0.0, "slippage_n": 0})
        acc["fee"] += c["fee"]
        acc["tax"] += c["tax"]
        acc["statuses"].append(c["cost_status"])
        order_price = t.get("order_price")
        if order_price is not None:
            qty = float(t.get("quantity") or 0)
            price = float(t.get("price") or 0)
            op = float(order_price)
            side = str(t.get("trade_type") or "").upper()
            acc["slippage_won"] += (price - op) * qty if side == "BUY" else (op - price) * qty
            acc["slippage_n"] += 1

    days = []
    d = start
    while d <= end:
        v = by_date.get(d)
        if v:
            days.append({
                "date": d.isoformat(), "fee": v["fee"], "tax": v["tax"],
                "slippage_won": v["slippage_won"], "slippage_n": v["slippage_n"],
                "cost_status": cost_overlay.day_cost_status(v["statuses"]),
            })
        else:
            days.append({"date": d.isoformat(), "fee": 0.0, "tax": 0.0,
                        "slippage_won": 0.0, "slippage_n": 0, "cost_status": None})
        d += timedelta(days=1)

    return ApiResponse(success=True, data={
        "from": start.isoformat(), "to": end.isoformat(), "days": days,
    }, message="")


class ReconcileScheduleIn(BaseModel):
    time: str | None
    days: int = 1


@router.get("/schedule")
async def get_reconcile_schedule() -> ApiResponse:
    try:
        raw = await system_config.get_trade_cost_reconcile_schedule_raw()
    except Exception as exc:
        logger.warning("%s schedule 조회 실패: %r", _MARKER_ERROR, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="자동 대사 시각 조회 실패")
    parsed = reconcile_task.parse_schedule(raw)
    data = ({"enabled": False, "time": None, "days": None} if parsed is None else
            {"enabled": True, "time": parsed[0].strftime("%H:%M"), "days": parsed[1]})
    return ApiResponse(success=True, data=data, message="")


@router.put("/schedule")
async def put_reconcile_schedule(body: ReconcileScheduleIn) -> ApiResponse:
    if body.time is None:
        value: dict = {"value": None}
    else:
        if reconcile_task.parse_hhmm(body.time) is None:
            raise HTTPException(
                status_code=422,
                detail=f"time 은 HH:MM 이고 {reconcile_task.LOOP_OPEN:%H:%M} 이상 "
                       f"{reconcile_task.LOOP_CLOSE:%H:%M} 미만이어야 한다",
            )
        if reconcile_task.parse_days(body.days) is None:
            raise HTTPException(status_code=422,
                                detail=f"days 는 1~{reconcile_task.MAX_DAYS} 정수여야 한다")
        value = {"value": body.time, "days": body.days}
    try:
        await system_config.set_trade_cost_reconcile_schedule(value)
    except Exception as exc:
        logger.warning("%s schedule 저장 실패: %r", _MARKER_ERROR, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="자동 대사 시각 저장 실패")
    return ApiResponse(success=True, data=value, message="")
