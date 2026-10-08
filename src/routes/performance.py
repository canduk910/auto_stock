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

    cycle411 보완 H2 — 배분(`cost_overlay.trade_costs`)은 항상 그 날짜 범위의 **전체**
    COMPLETED+PARTIAL 체결로 하고, `strategy` 필터는 배분 **뒤에** 그 전략 체결만 걸러
    `by_date` 로 더한다(배분 전에 거르면 그 전략 혼자 그 날 정산 전체를 떠안는다). 요율은
    화면 날짜 범위가 아니라 서버 오늘 기준 30일 창(M2).
    """
    if not records:
        return []
    dates = [r["date"] for r in records]
    start, end = min(dates), max(dates)
    # 3차 LOW 보완 — DB 조회뿐 아니라 그 뒤 순수 계산(`trade_costs`·`net_twr`)의 코드
    # 결함도 같은 try 안에서 삼킨다. 둘 다 이 함수 하나의 반환값(list | None)을 만드는
    # 데만 쓰여 중간에 멈춰도 부분 상태가 새지 않는다 — 계산이 실패하면 호출부가 기존
    # gross 응답을 그대로 유지한다(계약 결정 2).
    try:
        cost_rows = await trade_cost_db.get_daily_range(start, end)
        trades = await trade_cost_db.get_trades_by_status(start, end, ["COMPLETED", "PARTIAL"])
        rates = await cost_overlay.today_window_rates()
        etf_flags = await cost_overlay.stock_master_etf_flags(trades)

        tc_by_id = cost_overlay.trade_costs(cost_rows, trades, rates, etf_flags=etf_flags)

        target_trades = (
            trades if not strategy or strategy == "total"
            else [t for t in trades if t.get("strategy") == strategy]
        )

        by_date: dict = {}
        for t in target_trades:
            c = tc_by_id.get(t.get("id"))
            if c is None:
                continue
            acc = by_date.setdefault(t["trade_date"], {"fee": 0.0, "tax": 0.0, "statuses": []})
            acc["fee"] += c["fee"]
            acc["tax"] += c["tax"]
            acc["statuses"].append(c["cost_status"])

        costs_by_date = {
            d: {"fee": v["fee"], "tax": v["tax"],
                "cost_status": cost_overlay.day_cost_status(v["statuses"])}
            for d, v in by_date.items()
        }
        return cost_overlay.net_twr(records, costs_by_date)
    except Exception:
        logger.warning("[cost_overlay_unavailable] /api/performance 실비용 조회 실패", exc_info=True)
        return None


#: cycle411 보완 H1 — "개시 이래" 전체 조회용(100년, 실질 전체 — `get_performance` 의
#: `LIMIT $2` 가 실제 행 수보다 크면 전체를 돌려준다).
_SINCE_INCEPTION_DAYS = 36_500


async def _since_inception_net_rows(strategy: str) -> list[dict] | None:
    """`net_cumulative_return_rate` 가 창이 아니라 **개시 이래**로 쌓이도록 전체 기간을
    읽어 재누적한다(H1 — 창 첫 행부터 다시 쌓지 않는다). 조회 실패 = None(호출부가 net
    칸을 `None` 으로 둔다 — 세전 값을 세후 칸에 담지 않는다, 2차 보완 B2).

    🔴 개시 이래 재조회(`get_performance(days=_SINCE_INCEPTION_DAYS, …)`) 자체의 실패도
    `_net_overlay_rows` 와 같은 무게로 잡는다 — 이 호출을 try 밖에 두면 그 예외가
    `summary`/`daily` 라우트까지 그대로 전파돼 500 이 된다(비용 조회 실패는 200 을 유지하는
    계약, B2).
    """
    try:
        full_records = await get_performance(days=_SINCE_INCEPTION_DAYS, strategy=strategy)
    except Exception:
        logger.warning(
            "[cost_overlay_unavailable] /api/performance 개시 이래 조회 실패", exc_info=True,
        )
        return None
    return await _net_overlay_rows(full_records, strategy)


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

    # cycle411 — net(세후) 누적·평균. 🔴 2차 보완 B2 — 비용 조회가 실패하면 세전 값을
    # 세후 칸에 담지 않는다(「모름」 ≠ gross 값) — 초기값은 `None`이고, 아래 개시 이래
    # 재조회(`net_rows_full`)가 성공했을 때만 채운다.
    # 🔴 수수료·세금은 % 로는 작아 round(…, 2) 로 gross 와 자릿수를 맞추면 두 값이 같은
    # 자리로 뭉개진다 — net 은 4자리로 둔다(비교 단언은 라운딩 전 크기 차이를 본다).
    net_total_profit_rate: float | None = None
    net_avg_daily_profit_rate: float | None = None
    # cycle411 보완 H1 — 누적은 창(30일)이 아니라 개시 이래 전체로 재누적한다(창 첫 행부터
    # 다시 쌓지 않는다). 평균은 그대로 창(`records`) 범위만 본다.
    net_rows_full = await _since_inception_net_rows(strategy)
    if net_rows_full:
        net_total_profit_rate = round(net_rows_full[-1]["net_cumulative_return_rate"], 4)
        net_by_date = {r["date"]: r for r in net_rows_full}
        net_daily_rates = [
            net_by_date[r["date"]]["net_daily_profit_rate"]
            for r in records if r["date"] in net_by_date
        ]
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
    # cycle411 보완 H1 — net 누적은 이 창이 아니라 개시 이래 전체로 재누적한 값에서
    # 이 창의 날짜만 집어 쓴다(창 첫 행부터 다시 쌓지 않는다).
    net_rows = await _since_inception_net_rows(strategy)
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
