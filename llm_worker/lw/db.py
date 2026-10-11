"""청산 AI 섀도 DB 접근(cycle446). 메서드마다 자동커밋 단문 1개뿐. 트랜잭션 금지.

`httpx`·`sleep`·OpenAI 를 모른다(journal_worker/jw/db.py 관례 그대로 — 트랜잭션 안에서
HTTP·sleep 을 거는 실수를 원천 차단한다).
"""
from __future__ import annotations

import json


def _jsonb(value):
    if value is None:
        return None
    return json.dumps(value, default=str, ensure_ascii=False)


class ExitAiDB:
    def __init__(self, conn):
        self._conn = conn

    # ---- 입력 조립 ------------------------------------------------------

    async def fetch_recent_daily(self, ticker: str, limit: int) -> list:
        sql = ("SELECT bas_dd, open_price, high_price, low_price, close_price, volume, updated_at"
               " FROM stock_master_daily WHERE ticker = $1 ORDER BY bas_dd DESC LIMIT $2")
        rows = await self._conn.fetch(sql, ticker, limit)
        return [dict(r) for r in rows]

    async def fetch_head_row(self, ticker: str) -> dict | None:
        """그 종목의 가장 최근 1봉(헤드 판정용)."""
        sql = ("SELECT bas_dd, updated_at FROM stock_master_daily WHERE ticker = $1"
               " ORDER BY bas_dd DESC LIMIT 1")
        row = await self._conn.fetchrow(sql, ticker)
        return dict(row) if row else None

    # ---- 평가 기록 --------------------------------------------------------

    async def get_existing_evaluation(self, *, bar_date, strategy_id, ticker, buy_date, buy_order_no) -> dict | None:
        sql = ("SELECT id, attempts, result FROM exit_ai_evaluations WHERE bar_date=$1 AND strategy_id=$2"
               " AND ticker=$3 AND buy_date=$4 AND buy_order_no=$5")
        row = await self._conn.fetchrow(sql, bar_date, strategy_id, ticker, buy_date, buy_order_no or "")
        return dict(row) if row else None

    async def upsert_evaluation(self, row: dict) -> None:
        """`(bar_date, strategy_id, ticker, buy_date, buy_order_no)` 로 insert 또는 전량 갱신(재시도)."""
        cols = [
            "bar_date", "act_date", "strategy_id", "ticker", "buy_date", "buy_order_no",
            "quantity", "buy_price_won", "bars_held",
            "close_won", "unrealized_pct", "high_since_buy_won", "mfe_pct", "mae_pct",
            "stop_price_won", "stop_source", "stop_dist_pct", "target_price_won", "entry_atr",
            "kk_armed", "time_exit_bars_left",
            "mode", "result", "reason", "attempts",
            "action", "exit_score", "inconsistent", "rationale", "key_risks", "invalidations",
            "model", "prompt_version", "feature_version", "tokens_in", "tokens_out",
            "cost_usd", "latency_ms", "evaluated_at", "input_payload", "raw_response",
        ]
        jsonb_cols = {"key_risks", "invalidations", "input_payload"}
        values = []
        for c in cols:
            v = row.get(c)
            values.append(_jsonb(v) if c in jsonb_cols else v)
        placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
        update_assign = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in
                                  ("bar_date", "strategy_id", "ticker", "buy_date", "buy_order_no"))
        sql = (
            f"INSERT INTO exit_ai_evaluations ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT (bar_date, strategy_id, ticker, buy_date, buy_order_no) "
            f"DO UPDATE SET {update_assign}"
        )
        await self._conn.execute(sql, *values)

    # ---- 일일 run 행 -------------------------------------------------------

    async def upsert_run(self, row: dict) -> None:
        cols = ["run_date", "bar_date", "started_at", "finished_at", "status", "n_targets",
                "n_ok", "n_failed", "n_skipped", "n_next_open_filled", "n_outcome_filled",
                "model", "prompt_version", "note"]
        values = [row.get(c) for c in cols]
        placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
        update_assign = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "run_date")
        sql = (f"INSERT INTO exit_ai_runs ({', '.join(cols)}) VALUES ({placeholders}) "
               f"ON CONFLICT (run_date) DO UPDATE SET {update_assign}")
        await self._conn.execute(sql, *values)

    # ---- 사후 채움 ① 반사실 시가 ----------------------------------------------

    async def list_open_missing_next_open(self, *, before: object) -> list:
        sql = ("SELECT id, ticker, act_date FROM exit_ai_evaluations"
               " WHERE outcome_status = 'open' AND next_open_won IS NULL AND act_date < $1")
        rows = await self._conn.fetch(sql, before)
        return [dict(r) for r in rows]

    async def fetch_open_price(self, ticker: str, bas_dd) -> object:
        sql = "SELECT open_price FROM stock_master_daily WHERE ticker=$1 AND bas_dd=$2"
        return await self._conn.fetchval(sql, ticker, bas_dd)

    async def fill_next_open(self, eval_id: int, open_price, now) -> None:
        sql = "UPDATE exit_ai_evaluations SET next_open_won=$2, next_open_filled_at=$3 WHERE id=$1"
        await self._conn.execute(sql, eval_id, open_price, now)

    # ---- 사후 채움 ② 실제 결과 -----------------------------------------------

    async def list_open_evaluations(self) -> list:
        sql = ("SELECT id, strategy_id, ticker, buy_date, buy_order_no, quantity, act_date"
               " FROM exit_ai_evaluations WHERE outcome_status = 'open'")
        rows = await self._conn.fetch(sql)
        return [dict(r) for r in rows]

    async def fetch_sell_trades(self, strategy_id: str, ticker: str, since) -> list:
        sql = ("SELECT order_no, quantity, price, timestamp, status FROM trade_history"
               " WHERE strategy=$1 AND ticker=$2 AND trade_type='SELL'"
               " AND status IN ('COMPLETED', 'PARTIAL') AND timestamp >= $3 ORDER BY timestamp ASC")
        rows = await self._conn.fetch(sql, strategy_id, ticker, since)
        return [dict(r) for r in rows]

    async def fetch_journal_order(self, order_date, order_no: str, side: str) -> dict | None:
        sql = ("SELECT source, reason_code FROM trade_journal_orders"
               " WHERE order_date=$1 AND order_no=$2 AND side=$3")
        row = await self._conn.fetchrow(sql, order_date, order_no, side)
        return dict(row) if row else None

    async def fill_outcome(self, eval_id: int, *, outcome_status, exit_date, exit_vwap_after_won,
                           sold_qty_after, exit_reason, exit_is_manual, now) -> None:
        sql = ("UPDATE exit_ai_evaluations SET outcome_status=$2, exit_date=$3,"
               " exit_vwap_after_won=$4, sold_qty_after=$5, exit_reason=$6, exit_is_manual=$7,"
               " outcome_filled_at=$8 WHERE id=$1")
        await self._conn.execute(sql, eval_id, outcome_status, exit_date, exit_vwap_after_won,
                                 sold_qty_after, exit_reason, exit_is_manual, now)
