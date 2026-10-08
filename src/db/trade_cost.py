"""`trade_cost_daily` · `trade_cost_period_totals` CRUD + 귀속용 읽기 (트랙 C 실비용 산출).

스키마 = `supabase/migrations/045_trade_cost_daily.sql`.

- `trade_cost_daily` = KIS `TTTC8715R` 행을 `(trad_dt, pdno)` 로 접은 정산값. 같은 키 재대사는 덮어쓴다.
- `trade_cost_period_totals` = 대사 실행 기간의 KIS output2 합계(행 합계와 1원 대조용).
- `get_completed_trades` 는 `trade_history` 를 **읽기만** 한다(전략 귀속·슬리피지 계산 입력 —
  주문가 `order_price` 포함, cycle409).

바인딩 규약(`src/db/CLAUDE.md`) — DATE = `date` 객체, TIMESTAMPTZ = aware `datetime`,
JSONB = raw dict/list(호출부 `json.dumps` 금지), NUMERIC = `Decimal`. 예외는 삼키지 않고 전파한다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import src.db.pg as pg
from src.db._kst import now_kst_iso, to_date

_DAILY_NUMERIC = ("buy_qty", "buy_amt", "sll_qty", "sll_amt", "rlzt_pfls", "fee", "tl_tax")
_TOTAL_NUMERIC = (
    "buy_fee_smtl", "sll_fee_smtl", "sll_tltx_smtl", "buy_tax_smtl",
    "tot_fee", "tot_tltx", "tot_rlzt_pfls",
)


def _now() -> datetime:
    return datetime.fromisoformat(now_kst_iso())


def _dec_or_none(v) -> Decimal | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _kst_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    lo = datetime.fromisoformat(f"{start.isoformat()}T00:00:00+09:00")
    hi = datetime.fromisoformat(f"{(end + timedelta(days=1)).isoformat()}T00:00:00+09:00")
    return lo, hi


async def upsert_daily(rows: list[dict]) -> int:
    """집계된 `(trad_dt, pdno)` 행을 upsert 하고 쓴 행 수를 돌려준다."""
    if not rows:
        return 0
    fetched_at = _now()
    args = [
        (
            to_date(r["trad_dt"]), r["pdno"], r.get("prdt_name") or "",
            *(Decimal(r.get(k) or 0) for k in _DAILY_NUMERIC),
            int(r.get("row_count") or 1), list(r.get("raw") or []), fetched_at,
        )
        for r in rows
    ]
    await pg.executemany(
        """
        INSERT INTO trade_cost_daily (
            trad_dt, pdno, prdt_name, buy_qty, buy_amt, sll_qty, sll_amt,
            rlzt_pfls, fee, tl_tax, row_count, raw, fetched_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13)
        ON CONFLICT (trad_dt, pdno) DO UPDATE SET
            prdt_name = EXCLUDED.prdt_name, buy_qty = EXCLUDED.buy_qty,
            buy_amt = EXCLUDED.buy_amt, sll_qty = EXCLUDED.sll_qty,
            sll_amt = EXCLUDED.sll_amt, rlzt_pfls = EXCLUDED.rlzt_pfls,
            fee = EXCLUDED.fee, tl_tax = EXCLUDED.tl_tax,
            row_count = EXCLUDED.row_count, raw = EXCLUDED.raw,
            fetched_at = EXCLUDED.fetched_at
        """,
        args,
    )
    return len(args)


async def upsert_period_total(from_dt: date, to_dt: date, summary: dict) -> None:
    """대사 기간의 KIS output2 합계를 upsert 한다(숫자 칸 + 원문)."""
    summary = dict(summary or {})
    await pg.execute(
        """
        INSERT INTO trade_cost_period_totals (
            from_dt, to_dt, buy_fee_smtl, sll_fee_smtl, sll_tltx_smtl, buy_tax_smtl,
            tot_fee, tot_tltx, tot_rlzt_pfls, raw, fetched_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
        ON CONFLICT (from_dt, to_dt) DO UPDATE SET
            buy_fee_smtl = EXCLUDED.buy_fee_smtl, sll_fee_smtl = EXCLUDED.sll_fee_smtl,
            sll_tltx_smtl = EXCLUDED.sll_tltx_smtl, buy_tax_smtl = EXCLUDED.buy_tax_smtl,
            tot_fee = EXCLUDED.tot_fee, tot_tltx = EXCLUDED.tot_tltx,
            tot_rlzt_pfls = EXCLUDED.tot_rlzt_pfls, raw = EXCLUDED.raw,
            fetched_at = EXCLUDED.fetched_at
        """,
        to_date(from_dt), to_date(to_dt),
        *(_dec_or_none(summary.get(k)) for k in _TOTAL_NUMERIC),
        summary, _now(),
    )


async def get_daily_range(start: date, end: date) -> list[dict]:
    """`trad_dt` 가 `[start, end]` 인 정산 행(날짜·종목 순)."""
    return await pg.fetch(
        """
        SELECT trad_dt, pdno, prdt_name, buy_qty, buy_amt, sll_qty, sll_amt,
               rlzt_pfls, fee, tl_tax, row_count, raw
        FROM trade_cost_daily
        WHERE trad_dt BETWEEN $1 AND $2
        ORDER BY trad_dt, pdno
        """,
        to_date(start), to_date(end),
    )


async def get_completed_trades(start: date, end: date) -> list[dict]:
    """`trade_history` COMPLETED 행 — 체결일은 **KST** 날짜(`trade_date`)."""
    lo, hi = _kst_bounds(to_date(start), to_date(end))
    return await pg.fetch(
        """
        SELECT (timestamp AT TIME ZONE 'Asia/Seoul')::date AS trade_date,
               ticker, trade_type, strategy, price, quantity,
               COALESCE(profit_loss, 0) AS profit_loss, COALESCE(order_no, '') AS order_no,
               order_price
        FROM trade_history
        WHERE status = 'COMPLETED' AND timestamp >= $1 AND timestamp < $2
        ORDER BY timestamp
        """,
        lo, hi,
    )


async def get_trades_by_status(
    start: date, end: date, statuses: list[str] | tuple[str, ...] = ("COMPLETED", "PARTIAL"),
) -> list[dict]:
    """`trade_history` 행 — `status` 를 `ANY($n::text[])` 로 받는다(가산형, cycle411).

    `get_completed_trades` 와 달리 `id`·`ticker_name`·`order_price`·`status` 를 함께 읽는다 —
    실비용 체결 행 단위 귀속(`src/engine/cost_overlay.py::trade_costs`)의 입력. 체결일은 여기도
    **KST** 날짜(`trade_date`).
    """
    lo, hi = _kst_bounds(to_date(start), to_date(end))
    return await pg.fetch(
        """
        SELECT id, (timestamp AT TIME ZONE 'Asia/Seoul')::date AS trade_date,
               ticker, ticker_name, trade_type, strategy, price, quantity,
               COALESCE(profit_loss, 0) AS profit_loss, COALESCE(order_no, '') AS order_no,
               order_price, status
        FROM trade_history
        WHERE status = ANY($1::text[]) AND timestamp >= $2 AND timestamp < $3
        ORDER BY timestamp
        """,
        list(statuses), lo, hi,
    )

