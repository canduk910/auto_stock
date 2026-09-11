"""`llm_buy_evaluations` CRUD — AI 매수평가(LLM shadow) 주문 시점 기록 (cycle276).

정본 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §2·§3·§4 (C31~C36).
스키마 = `supabase/migrations/043_llm_buy_evaluations.sql`.

**주문 1건 = 평가 1행**(성공·실패 모두). PK `(trade_date, account_no, ticker, order_no)` —
KIS ODNO 는 하루 단위로만 유일하므로 날짜가 PK 선두에 있어야 하고, `trade_history` 조인도
`(trade_date, ticker, order_no)` 3축이어야 안전하다.

## asyncpg 바인딩 규약 (`src/db/CLAUDE.md`, C34)
- **DATE** = `_kst.to_date(...)` 로 `date` 객체 강제. `str` 을 그대로 넘기면 asyncpg 가
  ``'str' object has no attribute 'toordinal'`` 로 즉사한다(M6 라이브 핫픽스).
- **TIMESTAMPTZ** = **aware `datetime`**. `now_kst_iso()`(str)를 넘기면 mock 은 전건
  초록인데 실 PG 에서만 `DataError` 다(cycle273a HIGH#1).
- **JSONB** = raw dict/list 를 그대로 바인딩(`$N::jsonb`). 호출부 `json.dumps` **금지** —
  `pg._init_conn` 의 codec 이 왕복을 책임진다. 문자열로 미리 말아 넣으면 읽을 때 `str` 이
  돌아와 `isinstance(x, dict)` 분기가 전부 조용히 폴백한다.
- **NUMERIC** = `Decimal` 로 바인딩하고 `Decimal` 로 돌아온다. 라우트가 `float` 로
  사영한다(cycle266 흰 화면 — pydantic v2 는 `Decimal` 을 JSON 문자열로 내보낸다).

## 오류를 삼키지 않는다
이 모듈은 예외를 **전파**한다. 기록 실패의 침묵은 leaf 의 persist 마커가, 조회 실패의
침묵은 라우트의 500 이 깨는데, 여기서 `except Exception: return None` 을 하면 그 두
채널이 동시에 막힌다(cycle266 정본).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import src.db.pg as pg
from src.db._kst import now_kst_iso, to_date

logger = logging.getLogger(__name__)

TABLE_NAME = "llm_buy_evaluations"

# 열 순서 = migration 043 의 CREATE TABLE 순서(53열). 바인딩 순서의 정본이다.
_COLUMNS: tuple[str, ...] = (
    "trade_date", "account_no", "ticker", "order_no",
    "eval_kind", "account_product", "strategy_id", "mode", "result", "reason",
    "score", "min_score", "would_block", "rationale", "key_risks", "invalidations",
    "model", "tokens_in", "tokens_out", "cost_usd", "latency_ms", "verdict_lag_ms",
    "eval_to_order_lag_ms", "order_kst", "evaluated_at",
    "order_price_won", "ordered_qty", "order_notional_won", "order_division",
    "order_path", "exchange", "board", "current_price_won",
    "signal_matched", "signal_price_won", "signal_time_local", "strategy_board",
    "target_won", "k", "breakout_excess_bp",
    "post_order_drift_bp", "drift_price_won", "tick_age_s",
    "budget_total_won", "budget_remaining_after_won", "open_positions_n",
    "prompt_version", "feature_version", "bars_count", "input_payload", "raw_response",
    "created_at", "updated_at",
)

_PK_COLUMNS = ("trade_date", "account_no", "ticker", "order_no")
_JSONB_COLUMNS = frozenset({"key_risks", "invalidations", "input_payload", "raw_response"})

# 프론트가 `Intl.DateTimeFormat(timeZone:'Asia/Seoul')` 로 그리는 계약의 원천.
# `new Date(iso).getHours()` 로컬타임 추출 금지 규약과 짝을 이룬다.
_ISO_FMT = "YYYY-MM-DD\"T\"HH24:MI:SS.US+09:00"
_ISO_SELECT = (
    f"to_char(order_kst, '{_ISO_FMT}') AS order_kst_iso, "
    f"to_char(evaluated_at, '{_ISO_FMT}') AS evaluated_at_iso, "
    f"to_char(created_at, '{_ISO_FMT}') AS created_at_iso"
)


def _placeholder(idx: int, col: str) -> str:
    return f"${idx}::jsonb" if col in _JSONB_COLUMNS else f"${idx}"


_UPSERT_SQL = (
    f"INSERT INTO {TABLE_NAME} ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join(_placeholder(i, c) for i, c in enumerate(_COLUMNS, 1))}) "
    f"ON CONFLICT ({', '.join(_PK_COLUMNS)}) DO UPDATE SET "
    + ", ".join(
        f"{c} = EXCLUDED.{c}"
        for c in _COLUMNS
        if c not in _PK_COLUMNS and c != "created_at"
    )
    + " RETURNING *"
)


# ---------------------------------------------------------------------------
# 값 강제 변환 — 타입 규약을 **호출자에게 맡기지 않는다**
# ---------------------------------------------------------------------------
def _to_dt(value) -> datetime | None:
    """TIMESTAMPTZ 바인딩 값을 aware `datetime` 으로 강제한다(str 금지, C34)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"TIMESTAMPTZ 바인딩에 지원하지 않는 타입: {type(value).__name__}")


def _to_num(value) -> Decimal | None:
    """NUMERIC 바인딩 값을 `Decimal` 로 강제한다(asyncpg 는 float 을 받지 않는다)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _to_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _norm_order_no(value) -> str:
    """`None`/공백을 `''` 로 정규화한다.

    NULL 을 허용하면 PK 가 통째로 사라지고(NULL 은 유일성 판정 밖) 같은 주문이
    여러 행이 된다.
    """
    return str(value or "").strip()


async def upsert_evaluation(
    *,
    trade_date,
    account_no: str,
    ticker: str,
    order_no,
    eval_kind: str = "order",
    account_product: str | None = None,
    strategy_id: str,
    mode: str,
    result: str,
    reason: str | None = None,
    score: int | None = None,
    min_score: int,
    would_block: bool | None = None,
    rationale: str | None = None,
    key_risks=None,
    invalidations=None,
    model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd=None,
    latency_ms: int | None = None,
    verdict_lag_ms: int | None = None,
    eval_to_order_lag_ms: int | None = None,
    order_kst,
    evaluated_at=None,
    order_price_won: int,
    ordered_qty: int,
    order_notional_won: int,
    order_division: str,
    order_path: str,
    exchange: str | None = None,
    board: str,
    current_price_won: int | None = None,
    signal_matched: bool = False,
    signal_price_won: int | None = None,
    signal_time_local: str | None = None,
    strategy_board: str | None = None,
    target_won: int | None = None,
    k=None,
    breakout_excess_bp=None,
    post_order_drift_bp=None,
    drift_price_won: int | None = None,
    tick_age_s=None,
    budget_total_won: int | None = None,
    budget_remaining_after_won: int | None = None,
    open_positions_n: int | None = None,
    prompt_version: str | None = None,
    feature_version: str | None = None,
    bars_count: int | None = None,
    input_payload: dict | None = None,
    raw_response: dict | None = None,
) -> dict | None:
    """평가 1건 UPSERT — 같은 PK 로 다시 쓰면 갱신하되 `created_at` 은 보존한다.

    예외는 **전파**한다(호출자 = leaf `_persist_evaluation` 이 persist 마커의
    `result=error` 로 시끄럽게 남긴다).
    """
    now_dt = datetime.fromisoformat(now_kst_iso())

    values = (
        to_date(trade_date),
        str(account_no or ""),
        str(ticker or ""),
        _norm_order_no(order_no),
        str(eval_kind or "order"),
        account_product,
        str(strategy_id or ""),
        str(mode or ""),
        str(result or ""),
        reason,
        _to_int(score),
        _to_int(min_score),
        would_block,
        rationale,
        key_risks,
        invalidations,
        model,
        _to_int(tokens_in),
        _to_int(tokens_out),
        _to_num(cost_usd),
        _to_int(latency_ms),
        _to_int(verdict_lag_ms),
        _to_int(eval_to_order_lag_ms),
        _to_dt(order_kst),
        _to_dt(evaluated_at),
        _to_int(order_price_won),
        _to_int(ordered_qty),
        _to_int(order_notional_won),
        str(order_division or ""),
        str(order_path or ""),
        exchange,
        str(board or ""),
        _to_int(current_price_won),
        bool(signal_matched),
        _to_int(signal_price_won),
        signal_time_local,
        strategy_board,
        _to_int(target_won),
        _to_num(k),
        _to_num(breakout_excess_bp),
        _to_num(post_order_drift_bp),
        _to_int(drift_price_won),
        _to_num(tick_age_s),
        _to_int(budget_total_won),
        _to_int(budget_remaining_after_won),
        _to_int(open_positions_n),
        prompt_version,
        feature_version,
        _to_int(bars_count),
        input_payload if input_payload is not None else {},
        raw_response,
        now_dt,
        now_dt,
    )
    assert len(values) == len(_COLUMNS), "바인딩 값 개수가 열 개수와 다르다"

    return await pg.fetchrow(_UPSERT_SQL, *values)


async def get_by_order(order_no: str, *, trade_date=None) -> dict | None:
    """주문번호 1건 조회.

    `trade_date` 를 주면 그 날짜로 좁히고, 없으면 **가장 최근** 1건을 돌려준다
    (KIS ODNO 는 날짜별로만 유일하므로 같은 번호가 여러 날짜에 존재할 수 있다).
    """
    ono = _norm_order_no(order_no)
    bound_date = to_date(trade_date) if trade_date is not None else None

    if bound_date is not None:
        return await pg.fetchrow(
            f"SELECT *, {_ISO_SELECT} FROM {TABLE_NAME} "
            "WHERE order_no = $1 AND trade_date = $2 "
            "ORDER BY trade_date DESC LIMIT 1",
            ono,
            bound_date,
        )
    return await pg.fetchrow(
        f"SELECT *, {_ISO_SELECT} FROM {TABLE_NAME} "
        "WHERE order_no = $1 "
        "ORDER BY trade_date DESC LIMIT 1",
        ono,
    )


async def list_by_order_nos(order_nos, *, trade_date=None) -> list[dict]:
    """주문번호 배치 조회 — 존재하는 **`(trade_date, order_no)` 쌍 전부**를 돌려준다.

    빈 목록이면 **쿼리 없이** `[]` (빈 배치가 전체 스캔으로 번지지 않게).

    ⚠️ 종전에는 "주문번호당 최신 1행" 으로 접었다(`trade_date DESC` + 첫 등장만).
    KIS ODNO 는 **하루 단위로만 유일**해서 같은 번호가 여러 날짜에 존재할 수 있고,
    접으면 오래된 날짜의 평가가 응답에서 사라진다 — 그 날짜의 거래 행은 "평가 기록
    없음"(버튼 비활성)이 되는데 상세 조회(`get_by_order(..., trade_date=…)`)로는
    멀쩡히 읽힌다. 배치와 상세의 날짜 축 비대칭이 화면의 거짓말이 되므로, 접는 일은
    이 층에서 하지 않고 호출자가 `(trade_date, order_no)` 두 값으로 대조한다.
    """
    keys = [str(x) for x in (order_nos or []) if str(x or "").strip()]
    if not keys:
        return []

    bound_date = to_date(trade_date) if trade_date is not None else None
    if bound_date is not None:
        rows = await pg.fetch(
            f"SELECT *, {_ISO_SELECT} FROM {TABLE_NAME} "
            "WHERE order_no = ANY($1::text[]) AND trade_date = $2 "
            "ORDER BY trade_date DESC",
            keys,
            bound_date,
        )
    else:
        rows = await pg.fetch(
            f"SELECT *, {_ISO_SELECT} FROM {TABLE_NAME} "
            "WHERE order_no = ANY($1::text[]) "
            "ORDER BY trade_date DESC",
            keys,
        )

    # 접지 않는다 — 같은 주문번호의 다른 날짜 행도 그대로 돌려준다(위 docstring).
    # 정렬(`trade_date DESC`)은 유지해 호출자가 최신부터 읽을 수 있게 한다.
    return list(rows or [])
