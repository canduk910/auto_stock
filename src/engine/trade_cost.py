"""실비용 산출 — KIS 정산값 사후 대사 · 전략 귀속 · 요약 · 경보 (트랙 C).

명세 = `_workspace/design/2026-10-01_mean_reversion_handoff.md` §4.

- **수수료·세금 = KIS 정산값**(`TTTC8715R`)을 사후에 가져와 `trade_cost_daily` 에 둔다. 매매 경로
  (`order_engine.py` 손익 계산)는 건드리지 않는다. `trade_history.profit_loss` 는 그대로 **세전·비용 전
  gross** 이고, net = gross − 수수료 − 세금 은 이 모듈이 계산만 한다.
- **전략 귀속** = 같은 KST 날짜·같은 종목의 `trade_history` COMPLETED 행 체결금액(price × quantity)
  비율. 수수료는 매수+매도 체결금액 비율, 세금·실현손익은 매도 체결금액 비율(매도가 없으면 전체
  비율)로 나눈다. 두 전략 이상이 나눠 가지면 `estimated=True`(「배분 추정」). 짝이 없는 KIS 행은
  `unattributed`. ⚠️ BUY 행 가격은 다건 체결통보면 마지막 체결가다(cycle392 §5.3-2) — 매수 쪽 비율에
  그 오차가 들어간다.
- **슬리피지** = `trade_history.order_price`(주문가) 대비 체결가(`price`), + 가 비용 — 매수 = (체결가 −
  주문가) × 수량, 매도 = (주문가 − 체결가) × 수량. `order_price` 가 NULL 인 행은 빠지고 덮인 건수
  `slippage_n` 을 함께 낸다(cycle409 — 사용자 결정 10-04 Q4). ⚠️ 한계 둘 — ① 시장가 주문의 주문가 =
  주문 순간 현재가(호가가 아니다)라 호가 스프레드 절반이 빠지고, 매도 시장가에 현재가 캐시가 없으면
  NULL 이다 ② 이 칸 이전 행·체결통보 선행 보정·동기화 INSERT 는 NULL 이라 덮이지 않는다.
- **경보** `[trade_cost_high]` = 전략별 30 달력일 실효 왕복비용 bp 가 `system_config.trade_cost_alert_bp`
  를 넘을 때 WARNING. 기준이 없으면 경보도 없다(기준값은 사용자 결정). 관측 전용 — 행위 변경 없음.

실효 왕복비용 bp = (수수료 + 세금) ÷ ((매수금액 + 매도금액) / 2) × 10⁴ — 한 번 사고 판 포지션 크기
대비 비용이다. 슬리피지 bp 는 덮인 주문금액(Σ 주문가 × 수량) 기준으로 따로 낸다(덮는 범위가 달라 합치지 않는다).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from src.api import trade_profit
from src.db import system_config, system_logs
from src.db import trade_cost as trade_cost_db

logger = logging.getLogger(__name__)

UNATTRIBUTED = "unattributed"
ALERT_WINDOW_DAYS = 30
_MARKER_HIGH = "[trade_cost_high]"

_SUM_FIELDS = ("buy_qty", "buy_amt", "sll_qty", "sll_amt", "rlzt_pfls", "fee", "tl_tax")


def _dec(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if v is None:
        return Decimal(0)
    s = str(v).strip().replace(",", "")
    if not s:
        return Decimal(0)
    try:
        return Decimal(s)
    except InvalidOperation:
        logger.warning("[trade_cost_parse] 숫자 아님 — 0 으로 읽음: %r", v)
        return Decimal(0)


def _parse_yyyymmdd(s) -> date | None:
    s = str(s or "").strip()
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:]))
    except ValueError:
        return None


def aggregate_kis_rows(rows: list[dict]) -> list[dict]:
    """KIS output1 행을 `(trad_dt, pdno 뒤 6자리)` 로 접는다. 날짜·종목이 빈 행은 버린다."""
    folded: dict[tuple[date, str], dict] = {}
    for row in rows:
        d = _parse_yyyymmdd(row.get("trad_dt"))
        pdno = str(row.get("pdno") or "").strip()[-6:]
        if d is None or not pdno:
            continue
        acc = folded.get((d, pdno))
        if acc is None:
            acc = {"trad_dt": d, "pdno": pdno, "prdt_name": str(row.get("prdt_name") or "").strip(),
                   **{k: Decimal(0) for k in _SUM_FIELDS}, "row_count": 0, "raw": []}
            folded[(d, pdno)] = acc
        for k in _SUM_FIELDS:
            acc[k] += _dec(row.get(k))
        acc["row_count"] += 1
        acc["raw"].append(row)
    return sorted(folded.values(), key=lambda r: (r["trad_dt"], r["pdno"]))


def _share(part: Decimal, whole: Decimal) -> Decimal:
    return part / whole if whole else Decimal(0)


def attribute(cost_rows: list[dict], trades: list[dict]) -> list[dict]:
    """정산 행을 전략으로 나눈다 — 행마다 (날짜, 종목, 전략) 1행씩."""
    sides: dict[tuple[date, str], dict[str, dict[str, Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: {"BUY": Decimal(0), "SELL": Decimal(0)})
    )
    for t in trades:
        side = str(t.get("trade_type") or "").upper()
        if side not in ("BUY", "SELL"):
            continue
        amt = _dec(t.get("price")) * _dec(t.get("quantity"))
        sides[(t["trade_date"], str(t.get("ticker") or ""))][t.get("strategy") or UNATTRIBUTED][side] += amt

    out: list[dict] = []
    for c in cost_rows:
        by_strategy = {s: v for s, v in sides.get((c["trad_dt"], c["pdno"]), {}).items()
                       if v["BUY"] + v["SELL"] > 0}
        vals = {k: _dec(c.get(k)) for k in ("buy_amt", "sll_amt", "fee", "tl_tax", "rlzt_pfls")}
        if not by_strategy:
            out.append({"trad_dt": c["trad_dt"], "pdno": c["pdno"], "strategy": UNATTRIBUTED,
                        **{k: float(v) for k, v in vals.items()}, "estimated": False})
            continue
        buy_tot = sum((v["BUY"] for v in by_strategy.values()), Decimal(0))
        sell_tot = sum((v["SELL"] for v in by_strategy.values()), Decimal(0))
        all_tot = buy_tot + sell_tot
        estimated = len(by_strategy) > 1
        for s, v in sorted(by_strategy.items()):
            total_share = _share(v["BUY"] + v["SELL"], all_tot)
            sell_share = _share(v["SELL"], sell_tot) if sell_tot else total_share
            buy_share = _share(v["BUY"], buy_tot) if buy_tot else total_share
            out.append({
                "trad_dt": c["trad_dt"], "pdno": c["pdno"], "strategy": s,
                "buy_amt": float(vals["buy_amt"] * buy_share),
                "sll_amt": float(vals["sll_amt"] * sell_share),
                "fee": float(vals["fee"] * total_share),
                "tl_tax": float(vals["tl_tax"] * sell_share),
                "rlzt_pfls": float(vals["rlzt_pfls"] * sell_share),
                "estimated": estimated,
            })
    return out


def _bp(num: float, den: float) -> float | None:
    return round(num / den * 10000, 2) if den else None


def _finish(acc: dict) -> dict:
    gross, fee, tax = acc["gross_pnl"], acc["fee"], acc["tax"]
    return {
        "strategy": acc["strategy"],
        "gross_pnl": round(gross, 2),
        "fee": round(fee, 2),
        "tax": round(tax, 2),
        "net_pnl": round(gross - fee - tax, 2),
        "kis_rlzt_pfls": round(acc["kis_rlzt_pfls"], 2),
        "buy_amt": round(acc["buy_amt"], 2),
        "sell_amt": round(acc["sell_amt"], 2),
        "cost_bp": _bp(fee + tax, (acc["buy_amt"] + acc["sell_amt"]) / 2),
        "slippage_won": round(acc["slippage_won"], 2),
        "slippage_bp": _bp(acc["slippage_won"], acc["slippage_base"]),
        "slippage_n": acc["slippage_n"],
        "cost_rows": acc["cost_rows"],
        "estimated_rows": acc["estimated_rows"],
    }


def _blank(strategy: str) -> dict:
    return {"strategy": strategy, "gross_pnl": 0.0, "fee": 0.0, "tax": 0.0,
            "kis_rlzt_pfls": 0.0, "buy_amt": 0.0, "sell_amt": 0.0, "slippage_won": 0.0,
            "slippage_base": 0.0, "slippage_n": 0, "cost_rows": 0, "estimated_rows": 0}


def summarize(cost_rows: list[dict], trades: list[dict], strategy: str | None = None) -> dict:
    """전략별 gross·수수료·세금·net·실효 bp·슬리피지. `strategy` 를 주면 그 전략만(total 도)."""
    accs: dict[str, dict] = {}

    def acc_for(s: str) -> dict:
        if s not in accs:
            accs[s] = _blank(s)
        return accs[s]

    for r in attribute(cost_rows, trades):
        a = acc_for(r["strategy"])
        a["fee"] += r["fee"]
        a["tax"] += r["tl_tax"]
        a["kis_rlzt_pfls"] += r["rlzt_pfls"]
        a["buy_amt"] += r["buy_amt"]
        a["sell_amt"] += r["sll_amt"]
        a["cost_rows"] += 1
        a["estimated_rows"] += 1 if r["estimated"] else 0

    for t in trades:
        s = t.get("strategy") or UNATTRIBUTED
        side = str(t.get("trade_type") or "").upper()
        if side == "SELL":
            acc_for(s)["gross_pnl"] += float(_dec(t.get("profit_loss")))
        if side not in ("BUY", "SELL") or t.get("order_price") is None:
            continue
        order_price = _dec(t.get("order_price"))
        if order_price <= 0:
            continue
        qty = _dec(t.get("quantity"))
        fill = _dec(t.get("price"))
        a = acc_for(s)
        a["slippage_won"] += float(((fill - order_price) if side == "BUY" else (order_price - fill)) * qty)
        a["slippage_base"] += float(order_price * qty)
        a["slippage_n"] += 1

    picked = [accs[s] for s in sorted(accs) if strategy is None or s == strategy]
    total = _blank("total")
    for a in picked:
        for k, v in a.items():
            if k != "strategy":
                total[k] += v
    return {"strategies": [_finish(a) for a in picked], "total": _finish(total)}


def cost_alerts(summary: dict, threshold_bp: float | None) -> list[dict]:
    """기준 bp 를 넘는 전략 목록. 기준 None = 경보 끔. `unattributed` 는 제외."""
    if threshold_bp is None:
        return []
    out = []
    for r in summary.get("strategies", []):
        bp = r.get("cost_bp")
        if r.get("strategy") == UNATTRIBUTED or bp is None:
            continue
        if float(bp) > float(threshold_bp):
            out.append({"strategy": r["strategy"], "cost_bp": float(bp),
                        "threshold_bp": float(threshold_bp)})
    return out


async def build_summary(start: date, end: date, strategy: str | None = None) -> dict:
    """DB(정산 행 · 체결 행 — 주문가 `order_price` 포함)를 읽어 `summarize` 한다."""
    cost_rows = await trade_cost_db.get_daily_range(start, end)
    trades = await trade_cost_db.get_completed_trades(start, end)
    out = summarize(cost_rows, trades, strategy=strategy)
    out["from"] = start.isoformat()
    out["to"] = end.isoformat()
    return out


async def _check_alerts(end: date) -> list[dict]:
    threshold = await system_config.get_trade_cost_alert_bp()
    if threshold is None:
        return []
    window_start = end - timedelta(days=ALERT_WINDOW_DAYS - 1)
    alerts = cost_alerts(await build_summary(window_start, end), threshold)
    for a in alerts:
        msg = (f"{_MARKER_HIGH} strategy={a['strategy']} cost_bp={a['cost_bp']:g} "
               f"threshold_bp={a['threshold_bp']:g} window={window_start.isoformat()}~{end.isoformat()}")
        logger.warning(msg)
        try:
            await system_logs.write_log("WARNING", msg)
        except Exception:
            logger.debug("[trade_cost] system_logs 기록 실패", exc_info=True)
    return alerts


def _summary_num(summary: dict, key: str) -> float | None:
    raw = summary.get(key)
    if raw is None or str(raw).strip() == "":
        return None
    return float(_dec(raw))


async def reconcile(start: date, end: date) -> dict:
    """KIS 정산값을 가져와 저장하고, 행 합계 ↔ KIS 합계 대조와 경보 결과를 돌려준다.

    KIS 거부·DB 예외는 전파한다(호출부가 HTTP 오류로 낸다). 경보 계산 실패만 삼킨다(관측 전용).
    """
    fetched = await trade_profit.fetch_period_trade_profit(
        start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    )
    rows = aggregate_kis_rows(fetched.rows)
    saved = await trade_cost_db.upsert_daily(rows)
    await trade_cost_db.upsert_period_total(start, end, fetched.summary)

    row_fee = float(sum((r["fee"] for r in rows), Decimal(0)))
    row_tax = float(sum((r["tl_tax"] for r in rows), Decimal(0)))
    kis_fee = _summary_num(fetched.summary, "tot_fee")
    kis_tax = _summary_num(fetched.summary, "tot_tltx")
    totals_match = None
    if kis_fee is not None and kis_tax is not None:
        totals_match = abs(row_fee - kis_fee) < 0.5 and abs(row_tax - kis_tax) < 0.5

    try:
        alerts = await _check_alerts(end)
    except Exception:
        logger.warning("[trade_cost] 경보 판정 실패 — 대사 결과는 유지", exc_info=True)
        alerts = []

    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "kis_rows": len(fetched.rows),
        "saved_rows": saved,
        "pages": fetched.pages,
        "truncated": fetched.truncated,
        "row_fee": row_fee,
        "row_tax": row_tax,
        "kis_tot_fee": kis_fee,
        "kis_tot_tltx": kis_tax,
        "totals_match": totals_match,
        "alerts": alerts,
    }
