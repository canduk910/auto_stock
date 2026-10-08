"""거래일지 DB 접근(cycle412 계약 3.7절) — 메서드마다 자동커밋 단문 1개뿐. 트랜잭션 금지.

httpx·sleep 을 모른다(트랜잭션 안에서 HTTP·sleep 을 거는 실수를 원천 차단).
"""
from __future__ import annotations

import json


def _jsonb(value):
    if value is None:
        return None
    return json.dumps(value, default=str, ensure_ascii=False)


def _rows_affected(status) -> int:
    """asyncpg ``Connection.execute`` 커맨드 상태 문자열(``"INSERT 0 1"``·``"UPDATE 1"``) 끝의 수."""
    if not status:
        return 0
    try:
        return int(status.split()[-1])
    except (ValueError, IndexError):
        return 0


class JournalDB:
    def __init__(self, conn):
        self._conn = conn

    async def insert_order(self, row: dict) -> bool:
        """``INSERT 0 1``(새로 넣음) → True · ``INSERT 0 0``(이미 있음, ON CONFLICT DO NOTHING) → False."""
        sql = (
            "INSERT INTO trade_journal_orders "
            "(order_date, order_no, side, strategy, ticker, source, reason_code, reason_sub, "
            "judge_price, order_price, order_division, exchange, parent_order_no, fired_line, "
            "effective_line, signal, params, noted_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18) "
            "ON CONFLICT (order_date, order_no, side) DO NOTHING"
        )
        status = await self._conn.execute(
            sql, row["order_date"], row["order_no"], row["side"], row["strategy"], row["ticker"],
            row["source"], row["reason_code"], row["reason_sub"], row["judge_price"], row["order_price"],
            row["order_division"], row["exchange"], row["parent_order_no"], row["fired_line"],
            row["effective_line"], _jsonb(row["signal"]), _jsonb(row["params"]), row["noted_at"],
        )
        return _rows_affected(status) > 0

    async def promote_order(self, row: dict) -> bool:
        """같은 키의 행이 ``unmatched``·``external`` 일 때만 빈 칸(NULL·전략 ``'unknown'``)을 채우고
        source 를 로그 행 것으로 바꾼다. ``UPDATE 1`` → True · ``UPDATE 0``(이미 실측·없는 키) → False."""
        sql = (
            "UPDATE trade_journal_orders SET "
            "strategy = CASE WHEN strategy = 'unknown' THEN $4 ELSE strategy END, "
            "source = $5, "
            "reason_code = COALESCE(reason_code, $6), "
            "reason_sub = COALESCE(reason_sub, $7), "
            "judge_price = COALESCE(judge_price, $8), "
            "order_price = COALESCE(order_price, $9), "
            "order_division = COALESCE(order_division, $10), "
            "exchange = COALESCE(exchange, $11), "
            "parent_order_no = COALESCE(parent_order_no, $12), "
            "fired_line = COALESCE(fired_line, $13), "
            "effective_line = COALESCE(effective_line, $14), "
            "signal = COALESCE(signal, $15), "
            "params = COALESCE(params, $16) "
            "WHERE order_date = $1 AND order_no = $2 AND side = $3 "
            "AND source IN ('unmatched', 'external')"
        )
        status = await self._conn.execute(
            sql, row["order_date"], row["order_no"], row["side"], row["strategy"], row["source"],
            row["reason_code"], row["reason_sub"], row["judge_price"], row["order_price"],
            row["order_division"], row["exchange"], row["parent_order_no"], row["fired_line"],
            row["effective_line"], _jsonb(row["signal"]), _jsonb(row["params"]),
        )
        return _rows_affected(status) > 0

    async def fill_order_division(self, order_date, order_no, side, division) -> None:
        sql = (
            "UPDATE trade_journal_orders SET order_division = $4 "
            "WHERE order_date = $1 AND order_no = $2 AND side = $3 AND order_division IS NULL"
        )
        await self._conn.execute(sql, order_date, order_no, side, division)

    async def insert_stop(self, event: dict) -> None:
        sql = (
            "INSERT INTO trade_journal_stops "
            "(strategy, ticker, buy_date, pos_order_no, observed_at, event, stop_price, stop_kind, "
            "target_price, target_hit, arm_price, inputs) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)"
        )
        await self._conn.execute(
            sql, event["strategy"], event["ticker"], event["buy_date"], event["pos_order_no"],
            event["observed_at"], event["event"], event["stop_price"], event["stop_kind"],
            event["target_price"], event["target_hit"], event["arm_price"], _jsonb(event["inputs"]),
        )

    async def load_cursor(self, name: str = "main"):
        sql = "SELECT file_name, inode, byte_offset FROM trade_journal_cursor WHERE name = $1"
        row = await self._conn.fetchrow(sql, name)
        if row is None:
            return None
        return {"file_name": row["file_name"], "inode": row["inode"], "byte_offset": row["byte_offset"]}

    async def save_cursor(self, cursor: dict, name: str = "main") -> None:
        sql = (
            "INSERT INTO trade_journal_cursor (name, file_name, inode, byte_offset) "
            "VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (name) DO UPDATE SET file_name = $2, inode = $3, byte_offset = $4, "
            "updated_at = now()"
        )
        await self._conn.execute(sql, name, cursor["file_name"], cursor["inode"], cursor["byte_offset"])

    async def last_stop_rows(self) -> dict:
        sql = (
            "SELECT DISTINCT ON (strategy, ticker) strategy, ticker, pos_order_no, stop_price, stop_kind, "
            "target_price, target_hit, arm_price, event, observed_at "
            "FROM trade_journal_stops ORDER BY strategy, ticker, observed_at DESC"
        )
        rows = await self._conn.fetch(sql)
        return {(r["strategy"], r["ticker"]): dict(r) for r in rows}

    async def trades_since(self, since) -> list:
        sql = (
            "SELECT order_no, trade_type, strategy, ticker, timestamp, status, price, order_price "
            "FROM trade_history WHERE timestamp >= $1"
        )
        rows = await self._conn.fetch(sql, since)
        return [dict(r) for r in rows]
