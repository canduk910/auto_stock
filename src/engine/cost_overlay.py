"""실적 화면에 실비용(수수료·세금) 합치기 — 순수 계산 leaf (cycle411).

명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` (사용자 결정 10-08 Q1~Q4).
Red 메모 = `_workspace/red/cycle411/cost_overlay.md`.

🔴 **8영역(`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py`·
`src/api/order.py`·`src/realtime/**`·`src/auth/**`)·`scheduler.py` 무접촉** — 이 leaf 는 그
어느 것도 import 하지 않는다(`tests/unit/ast/test_cycle411_ast_scope.py::test_e1`). DB 저장값·
마이그레이션도 건드리지 않는다. `trade_history.profit_loss` 의미(세전) 불변.

- `estimate_rates` — `trade_cost_daily` 정산 행으로 수수료·세율을 추정한다(없으면 기본값
  0.142%/0.199%, 사용자 결정 10-08 Q1).
- `trade_costs` — 체결 행(`trade_history`) 단위 비용. 정산 행이 있으면 `trade_cost.allocate_rows`
  (key="id")로 나누고, 없으면 추정 요율 × 체결금액(세금은 매도만, ETF/ETN 매도는 0)을 쓴다.
  정산값이 있으면 ETF 라도 그 값이 정본이다(KIS 가 낸 세금을 0 으로 덮지 않는다).
- `net_twr` — `daily_performance` 행에 일별 비용을 얹어 net TWR(시간가중수익률)을 재누적한다.
  분모는 가장 가까운 이전 0 아닌 `total_asset`(DB 함수 `recompute_daily_performance` 와 같은 식).
- `day_cost_status` — 그날 체결 상태 목록을 settled/estimated/mixed 로 접는다.
- `overlay_pairs` — **async 어댑터**(설계 문서 「새 leaf … 순수 함수 + async 어댑터」). `get_trade_pairs`
  출력(`buy_trade_ids`/`sell_trade_ids` 병행 리스트, cycle411 DB 추가)에 위 순수 함수들로
  fee·tax·net_profit_loss·net_profit_rate·cost_bp·slippage_won·cost_status·allocated 를
  채운다. `/api/history/pnl`·`/api/strategies/te` 가 공유한다. DB 조회 실패 = None(호출부가
  기존 응답을 유지).
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable

from src.db import trade_cost as trade_cost_db
from src.engine import trade_cost
from src.engine.etf_like import is_etf_like

logger = logging.getLogger(__name__)

#: 사용자 결정 10-08 Q1 — 최근 30달력일 `trade_cost_daily` 표본이 없을 때의 기본값.
DEFAULT_FEE_RATE = 0.00142
DEFAULT_TAX_RATE = 0.00199


def _num(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if v is None:
        return Decimal(0)
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return Decimal(0)


def estimate_rates(cost_rows: list[dict]) -> dict:
    """정산 행으로 수수료·세율을 추정한다 — 표본 없으면 기본값(사용자 결정 10-08 Q1)."""
    if not cost_rows:
        return {"fee_rate": DEFAULT_FEE_RATE, "tax_rate": DEFAULT_TAX_RATE, "source": "default"}

    fee_sum = sum((_num(c.get("fee")) for c in cost_rows), Decimal(0))
    tax_sum = sum((_num(c.get("tl_tax")) for c in cost_rows), Decimal(0))
    vol = sum((_num(c.get("buy_amt")) + _num(c.get("sll_amt")) for c in cost_rows), Decimal(0))
    sell_vol = sum((_num(c.get("sll_amt")) for c in cost_rows), Decimal(0))

    fee_rate = float(fee_sum / vol) if vol else DEFAULT_FEE_RATE
    tax_rate = float(tax_sum / sell_vol) if sell_vol else DEFAULT_TAX_RATE
    return {"fee_rate": fee_rate, "tax_rate": tax_rate, "source": "measured"}


def _is_etf(ticker: str, ticker_name: str | None, etf_tickers: frozenset[str]) -> bool:
    if ticker in etf_tickers:
        return True
    return is_etf_like(None, ticker_name)


def trade_costs(
    cost_rows: list[dict],
    trades: list[dict],
    rates: dict,
    etf_tickers: frozenset[str] = frozenset(),
) -> dict:
    """체결 행(`id`) 단위 비용 — 정산 행이 있으면 대사값, 없으면 추정 요율.

    반환 = `{id: {"fee": float, "tax": float, "cost_status": "settled"|"estimated",
    "allocated": bool}}`. `allocated` = 같은 날·종목 정산 1행을 2개 이상 체결 행이 나눠
    받았을 때만 True(추정 행은 항상 False — 사용자 결정 10-08 §6).
    """
    settled_rows = trade_cost.allocate_rows(cost_rows, trades, key="id")
    settled_by_id = {r["id"]: r for r in settled_rows if r["id"] is not None}

    out: dict = {}
    for t in trades:
        tid = t.get("id")
        if tid in settled_by_id:
            r = settled_by_id[tid]
            out[tid] = {
                "fee": r["fee"],
                "tax": r["tl_tax"],
                "cost_status": "settled",
                "allocated": bool(r["estimated"]),
            }
            continue

        price = _num(t.get("price"))
        qty = _num(t.get("quantity"))
        amt = float(price * qty)
        side = str(t.get("trade_type") or "").upper()
        fee = amt * rates["fee_rate"]
        tax = 0.0
        if side == "SELL" and not _is_etf(str(t.get("ticker") or ""), t.get("ticker_name"), etf_tickers):
            tax = amt * rates["tax_rate"]
        out[tid] = {"fee": fee, "tax": tax, "cost_status": "estimated", "allocated": False}
    return out


def day_cost_status(statuses: Iterable[str]) -> str:
    """그날 체결 상태 목록을 settled/estimated/mixed 로 접는다."""
    uniq = set(statuses)
    if not uniq or uniq == {"settled"}:
        return "settled"
    if uniq == {"estimated"}:
        return "estimated"
    return "mixed"


def net_twr(records: list[dict], costs_by_date: dict) -> list[dict]:
    """`daily_performance` 행(오름차순)에 일별 비용을 얹어 net TWR 을 재누적한다.

    반환 행 = `date, daily_fee, daily_tax, daily_net_pnl, net_daily_profit_rate,
    net_cumulative_return_rate, cost_status`. 분모는 가장 가까운 이전 0 아닌
    `total_asset`(DB 함수 `recompute_daily_performance` 와 같은 식). 비용 0 이면 net 일·누적
    = gross 일·누적(N2).
    """
    out: list[dict] = []
    prev_nonzero_asset: float | None = None
    cum = 1.0
    for rec in records:
        d = rec["date"]
        cost = costs_by_date.get(d, {})
        fee = float(cost.get("fee") or 0.0)
        tax = float(cost.get("tax") or 0.0)
        cost_status = cost.get("cost_status")

        gross_pnl = float(rec.get("daily_realized_pnl") or 0.0)
        net_pnl = gross_pnl - fee - tax

        asset = float(rec.get("total_asset") or 0.0)
        denom = prev_nonzero_asset if prev_nonzero_asset else asset
        if fee == 0.0 and tax == 0.0:
            # N2 — 비용이 없으면 기존 daily_profit_rate 를 그대로 쓴다(부동소수 재계산 오차 없음).
            net_rate = float(rec.get("daily_profit_rate") or 0.0)
        else:
            net_rate = (net_pnl / denom * 100) if denom else 0.0

        cum *= 1 + net_rate / 100
        out.append({
            "date": d,
            "daily_fee": fee,
            "daily_tax": tax,
            "daily_net_pnl": net_pnl,
            "net_daily_profit_rate": net_rate,
            "net_cumulative_return_rate": (cum - 1) * 100,
            "cost_status": cost_status,
        })

        if asset != 0:
            prev_nonzero_asset = asset
    return out


async def overlay_pairs(pairs: list[dict]) -> dict[int, dict] | None:
    """페어마다 fee·tax·net_profit_loss·net_profit_rate·cost_bp·slippage_won·cost_status·
    allocated 를 채운다(async 어댑터, `/api/history/pnl`·`/api/strategies/te` 공유).

    거래 단위 귀속 — `buy_trade_ids`·`sell_trade_ids`(cycle411 DB 추가)로 체결 행 비용을
    모아 더한다(수수료 = 매수+매도 전부, 세금 = 매도 행만 — 매수 행의 세금은 이미 0).
    보유 중(open) 페어 = 낸 매수 수수료(정산/추정) + 예상 매도비용(현재가 추정, 사용자 결정
    10-08 §3·§5 — 현재가는 `buy_price + profit_loss/buy_qty` 로 페어 안에서만 역산한다,
    scanner 시세 캐시에 의존하지 않는다). 추정 행의 `allocated` 는 항상 False(§6).

    비용 조회가 실패하면 `[cost_overlay_unavailable]` WARNING 을 남기고 None 을 돌려준다
    (호출부가 기존 응답을 그대로 둔다 — 사용자 결정 10-08 §2).

    돌아오는 `{id: trade}` 맵은 `slippage_n`(order_price 덮인 체결 행 수) 집계용.
    """
    dates: list[date] = []
    for p in pairs:
        for key in ("buy_date", "sell_date"):
            raw = p.get(key)
            if not raw:
                continue
            try:
                dates.append(date.fromisoformat(str(raw)))
            except ValueError:
                pass
    if not dates:
        return {}

    try:
        cost_rows = await trade_cost_db.get_daily_range(min(dates), max(dates))
        trades = await trade_cost_db.get_trades_by_status(
            min(dates), max(dates), ["COMPLETED", "PARTIAL"])
    except Exception:
        logger.warning("[cost_overlay_unavailable] 실비용 조회 실패", exc_info=True)
        return None

    rates = estimate_rates(cost_rows)
    costs = trade_costs(cost_rows, trades, rates)
    trades_by_id = {t["id"]: t for t in trades if t.get("id") is not None}

    for p in pairs:
        ids = list(p.get("buy_trade_ids") or []) + list(p.get("sell_trade_ids") or [])
        entries = [costs[i] for i in ids if i in costs]

        if p.get("status") == "open":
            buy_fee = sum(c["fee"] for c in entries)
            qty = float(p.get("buy_qty") or 0)
            buy_price = float(p.get("buy_price") or 0)
            pl = p.get("profit_loss")
            cur_price = (buy_price * qty + float(pl)) / qty if (pl is not None and qty) else 0.0
            sell_amt = cur_price * qty
            fee_est = sell_amt * rates["fee_rate"]
            tax_est = 0.0 if is_etf_like(None, p.get("ticker_name")) else sell_amt * rates["tax_rate"]
            fee, tax = buy_fee + fee_est, tax_est
            cost_status, allocated = "estimated", False
        else:
            fee = sum(c["fee"] for c in entries)
            tax = sum(c["tax"] for c in entries)
            statuses = [c["cost_status"] for c in entries] or ["estimated"]
            cost_status = day_cost_status(statuses)
            allocated = any(c["allocated"] for c in entries)

        p["fee"] = fee
        p["tax"] = tax
        p["cost_status"] = cost_status
        p["allocated"] = allocated
        p["net_profit_loss"] = float(p.get("profit_loss") or 0.0) - fee - tax

        buy_amt = float(p.get("buy_price") or 0) * float(p.get("buy_qty") or 0)
        p["net_profit_rate"] = round(p["net_profit_loss"] / buy_amt * 100, 4) if buy_amt else None

        sell_amt = (float(p.get("sell_price") or 0) * float(p.get("sell_qty") or 0)
                    if p.get("sell_qty") else 0.0)
        denom = (buy_amt + sell_amt) / 2 if sell_amt else buy_amt
        p["cost_bp"] = round((fee + tax) / denom * 1e4, 4) if denom else None

        slip = 0.0
        for i in (p.get("buy_trade_ids") or []):
            t = trades_by_id.get(i)
            if t and t.get("order_price") is not None:
                slip += (float(t["price"]) - float(t["order_price"])) * float(t["quantity"])
        for i in (p.get("sell_trade_ids") or []):
            t = trades_by_id.get(i)
            if t and t.get("order_price") is not None:
                slip += (float(t["order_price"]) - float(t["price"])) * float(t["quantity"])
        p["slippage_won"] = slip

    return trades_by_id
