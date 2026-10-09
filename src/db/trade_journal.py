"""`trade_journal_orders` · `_stops` · `_notes` 읽기 + 메모 쓰기 (cycle413, 거래일지 화면 1b).

스키마 = `supabase/migrations/047_trade_journal.sql`. 쓰는 쪽(`trade_journal_orders`·
`_stops`·`_cursor`)은 `journal_worker` 컨테이너뿐이다(관찰자 방식) — 이 모듈은 그 세
표를 **읽기만** 한다. `trade_journal_notes` 는 이 모듈이 유일한 쓰기 경로(D2 메모,
`PUT /api/history/journal/notes/{id}`).

계약 = `_workspace/red/cycle413/journal_view_contract.md` 2절.

- 빈 목록 인자 = **쿼리 없이** `[]`(빈 배치가 전체 스캔으로 번지지 않게).
- 예외를 **삼키지 않는다** — 라우트가 「조회 실패」(`lookup_failed`)와 「행 없음」을
  가른다. 빈 목록으로 접으면 그 구분이 사라진다.
- 쓰기 SQL 대상은 `trade_journal_notes` 하나뿐이다.

asyncpg 바인딩 규약(`src/db/CLAUDE.md`) — TIMESTAMPTZ 는 aware `datetime`, DATE 는
`_kst.to_date()`, JSONB 는 codec 이 왕복(raw dict 그대로). 시각 읽기는 모두
`to_char(..., 'YYYY-MM-DD"T"HH24:MI:SS.US+09:00')` 로 KST ISO 문자열 고정(사이클 53
B-4 관례).
"""

from __future__ import annotations

from datetime import date, datetime

import src.db.pg as pg
from src.db._kst import to_date

#: 시각 컬럼 KST ISO 고정 출력(`trade_history._TS_SELECT` 와 같은 관례).
_ISO_SELECT = "YYYY-MM-DD\"T\"HH24:MI:SS.US+09:00"


def _affected(status: str) -> int:
    """asyncpg `execute()` 상태 문자열("DELETE 1" 등) → affected int."""
    try:
        return int(str(status).strip().split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0


async def list_orders(order_nos: list[str], *, date_from: date, date_to: date) -> list[dict]:
    """`trade_journal_orders` — 주문번호 ∩ `[date_from, date_to]`(`order_date`).

    열 = 표 전 칸(`order_date`·`order_no`·`side`·`strategy`·`ticker`·`source`·
    `reason_code`·`reason_sub`·`judge_price`·`order_price`·`order_division`·
    `exchange`·`parent_order_no`·`fired_line`·`effective_line`·`signal`·`params`·
    `noted_at`(KST ISO)). 빈 `order_nos` = 쿼리 없이 `[]`.
    """
    keys = [str(x) for x in (order_nos or []) if str(x or "").strip()]
    if not keys:
        return []
    sql = f"""
        SELECT order_date, order_no, side, strategy, ticker, source, reason_code, reason_sub,
               judge_price, order_price, order_division, exchange, parent_order_no,
               fired_line, effective_line, signal, params,
               to_char(noted_at, '{_ISO_SELECT}') AS noted_at
        FROM trade_journal_orders
        WHERE order_no = ANY($1::text[]) AND order_date BETWEEN $2 AND $3
        ORDER BY noted_at
    """
    return await pg.fetch(sql, keys, to_date(date_from), to_date(date_to))


async def list_stops(keys: list[tuple[str, str]], *, since: datetime, until: datetime) -> list[dict]:
    """`trade_journal_stops` — `(전략, 종목)` 합집합 ∩ `observed_at ∈ [since, until]`.

    `keys` = `[(strategy, ticker), ...]`. asyncpg 는 튜플 배열 바인딩이 없어 두
    평행 배열(`unnest($1::text[], $2::text[])`)로 합집합을 묻는다. 빈 `keys` =
    쿼리 없이 `[]`.
    """
    pairs = [(str(s), str(t)) for s, t in (keys or []) if str(s or "").strip() and str(t or "").strip()]
    if not pairs:
        return []
    strategies = [p[0] for p in pairs]
    tickers = [p[1] for p in pairs]
    sql = f"""
        SELECT s.strategy, s.ticker, s.buy_date, s.pos_order_no,
               to_char(s.observed_at, '{_ISO_SELECT}') AS observed_at, s.event, s.stop_price,
               s.stop_kind, s.target_price, s.target_hit, s.arm_price, s.inputs
        FROM trade_journal_stops s
        WHERE EXISTS (
            SELECT 1 FROM unnest($1::text[], $2::text[]) AS k(strategy, ticker)
            WHERE k.strategy = s.strategy AND k.ticker = s.ticker
        )
        AND s.observed_at BETWEEN $3 AND $4
        ORDER BY s.observed_at
    """
    return await pg.fetch(sql, strategies, tickers, since, until)


async def list_notes(anchor_ids: list[str]) -> list[dict]:
    """`trade_journal_notes` — `anchor_trade_id` 목록 조회. 빈 목록 = 쿼리 없이 `[]`."""
    keys = [str(x) for x in (anchor_ids or []) if str(x or "").strip()]
    if not keys:
        return []
    sql = f"""
        SELECT anchor_trade_id::text AS anchor_trade_id, body,
               to_char(created_at, '{_ISO_SELECT}') AS created_at,
               to_char(updated_at, '{_ISO_SELECT}') AS updated_at
        FROM trade_journal_notes
        WHERE anchor_trade_id = ANY($1::uuid[])
    """
    return await pg.fetch(sql, keys)


async def get_record_start() -> dict:
    """기록 시작일 4종 — 값은 KST 날짜 `'YYYY-MM-DD'` 문자열 또는 행 0 이면 `None`.

    - `orders_restored` = `MIN(order_date)` WHERE `source='log_restore'`.
    - `orders_live` = `MIN(order_date)` WHERE `source<>'log_restore'`.
    - `stops` = `MIN(observed_at)` 의 KST 날짜.
    - `order_price` = `trade_history.order_price` 가 처음 채워진 체결의 KST 날짜.
    """
    row = await pg.fetchrow(
        """
        SELECT
            (SELECT MIN(order_date) FROM trade_journal_orders WHERE source = 'log_restore')
                AS orders_restored,
            (SELECT MIN(order_date) FROM trade_journal_orders WHERE source <> 'log_restore')
                AS orders_live,
            (SELECT MIN((observed_at AT TIME ZONE 'Asia/Seoul')::date) FROM trade_journal_stops)
                AS stops,
            (SELECT MIN((timestamp AT TIME ZONE 'Asia/Seoul')::date) FROM trade_history
                WHERE order_price IS NOT NULL) AS order_price
        """
    )
    row = dict(row or {})
    return {
        key: (row.get(key).isoformat() if row.get(key) else None)
        for key in ("orders_restored", "orders_live", "stops", "order_price")
    }


async def upsert_note(
    anchor_trade_id: str, body: str, *, strategy: str, ticker: str, buy_date: date,
) -> dict:
    """메모 upsert — `ON CONFLICT (anchor_trade_id) DO UPDATE`(`created_at` 은 보존).

    쓰기 SQL 대상은 `trade_journal_notes` 하나다(워커 표에 쓰지 않는다).
    """
    row = await pg.fetchrow(
        f"""
        INSERT INTO trade_journal_notes (anchor_trade_id, strategy, ticker, buy_date, body)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (anchor_trade_id) DO UPDATE SET
            body = EXCLUDED.body, strategy = EXCLUDED.strategy, ticker = EXCLUDED.ticker,
            buy_date = EXCLUDED.buy_date, updated_at = now()
        RETURNING anchor_trade_id::text AS anchor_trade_id, body,
            to_char(created_at, '{_ISO_SELECT}') AS created_at,
            to_char(updated_at, '{_ISO_SELECT}') AS updated_at
        """,
        str(anchor_trade_id), strategy, ticker, to_date(buy_date), body,
    )
    return dict(row)


async def delete_note(anchor_trade_id: str) -> bool:
    """메모 1건 삭제 — 지운 행이 있으면 `True`, 없으면 `False`."""
    status = await pg.execute(
        "DELETE FROM trade_journal_notes WHERE anchor_trade_id = $1::uuid",
        str(anchor_trade_id),
    )
    return _affected(status) > 0
