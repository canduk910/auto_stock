"""trade_history CRUD.

사이클 M2a (Supabase→RDS 이전, 매매 hot path): supabase-py → `src.db.pg`(asyncpg) 전환.
함수 시그니처·반환형·graceful 100% 보존 — 호출부(order_engine/scheduler) diff 0.

⚠️ 3대 미묘 계약 (hot path 절대 보존):
1. TIMESTAMPTZ `+09:00` str 계약 (사이클 53 B-4):
   - 쓰기: timestamp 는 datetime 바인딩 (asyncpg TIMESTAMPTZ str 금지).
   - 읽기: SELECT 가 timestamp 를 `to_char(timestamp,'YYYY-MM-DD"T"HH24:MI:SS+09:00')` 로
     str `+09:00` 캐스트 반환 → `_to_kst`/`get_trade_pairs` 소비처 무변경 보장.
   - 범위: `get_trades_in_range` 가 `"{d}T00:00:00+09:00"` / `"{d}T23:59:59.999999+09:00"` 바인딩.
2. `get_trade_pairs` Decimal 페어링 — 가중평균 buy/sell + profit_loss Decimal 보존.
3. count + range 페이징 — `get_trades` 는 별도 count(*) SELECT + LIMIT/OFFSET.
   `.in_(status)` → `status = ANY($1::text[])`. sync 함수는 dedupe 없음 + CANCELLED 제외(사이클 30/73).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import src.db.pg as pg
from src.models.trade import TradeRecord, TradeStatus, TradeType

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# timestamp 를 항상 +09:00 str 로 반환하는 SELECT 표현식 (읽기 str 계약, 사이클 53 B-4).
_TS_SELECT = "to_char(t.timestamp, 'YYYY-MM-DD\"T\"HH24:MI:SS.US+09:00') AS timestamp"


def _to_kst(ts: str | None) -> tuple[str | None, str | None]:
    """ISO 타임스탬프 → (KST YYYY-MM-DD, KST HH:MM:SS).

    Supabase 가 반환하는 ISO 가 UTC(`+00:00`)인 경우와 KST(`+09:00`)인 경우 모두
    일관된 KST 출력을 보장한다. tz-naive 는 DB 가 이미 KST 로 저장한 케이스로 간주.

    잘못된 입력(None / 빈 문자열 / 파싱 불가)은 `(None, None)` 반환.
    """
    if not ts:
        return None, None
    try:
        # Postgres `Z` suffix → fromisoformat 호환 변환
        s = ts.replace("Z", "+00:00") if isinstance(ts, str) else ts
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)  # tz-naive 는 KST 가정
        kst_dt = dt.astimezone(KST)
        return kst_dt.strftime("%Y-%m-%d"), kst_dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return None, None


def _today_kst_iso() -> str:
    """KST 기준 오늘 00:00:00 의 ISO 문자열 (timezone 명시).

    PostgreSQL TIMESTAMPTZ 비교에 TZ-naive 문자열을 사용하면 UTC 로 해석되어
    KST 09시 이전 매수 기록이 누락된다. `+09:00` 명시로 차단.
    """
    today = datetime.now(KST).date()
    return f"{today.isoformat()}T00:00:00+09:00"


async def insert_trade(record: TradeRecord) -> None:
    """거래 기록을 삽입한다."""
    await pg.execute(
        """
        INSERT INTO trade_history (
            ticker, ticker_name, trade_type, price, quantity,
            profit_loss, status, strategy, order_no, timestamp
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """,
        record.ticker,
        record.ticker_name,
        record.trade_type.value,
        float(record.price),
        record.quantity,
        float(record.profit_loss),
        record.status.value,
        record.strategy,
        record.order_no,
        datetime.now(KST),
    )
    logger.debug("거래 기록 삽입: %s %s (전략: %s)", record.trade_type.value, record.ticker, record.strategy)


async def update_trade_status(
    ticker: str,
    trade_type: TradeType,
    status: TradeStatus,
    strategy: str = "momentum",
    price: int | None = None,
    profit_loss: float | None = None,
) -> int:
    """최신 PENDING 거래 기록의 상태를 업데이트하고 영향받은 행 수를 반환한다."""
    set_clauses = ["status = $1"]
    args: list = [status.value]

    if price is not None:
        args.append(float(price))
        set_clauses.append(f"price = ${len(args)}")
    if profit_loss is not None:
        args.append(float(profit_loss))
        set_clauses.append(f"profit_loss = ${len(args)}")

    args.extend([ticker, trade_type.value, TradeStatus.PENDING.value, strategy])
    ticker_idx = len(args) - 3
    type_idx = len(args) - 2
    pending_idx = len(args) - 1
    strategy_idx = len(args)

    sql = (
        f"UPDATE trade_history SET {', '.join(set_clauses)} "
        f"WHERE ticker = ${ticker_idx} AND trade_type = ${type_idx} "
        f"AND status = ${pending_idx} AND strategy = ${strategy_idx}"
    )

    result = await pg.execute(sql, *args)
    affected = _parse_affected(result)
    logger.debug("거래 상태 변경: %s %s -> %s (전략: %s, %d건)",
                 ticker, trade_type.value, status.value, strategy, affected)
    return affected


def _parse_affected(status_str: str) -> int:
    """asyncpg execute() 상태 문자열("UPDATE 1" / "DELETE 0" 등) → affected int."""
    try:
        return int(status_str.strip().split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0


async def _lookup_strategy_from_trade_history(
    ticker: str,
    order_no: str,
    trade_type: TradeType,
) -> str | None:
    """trade_history PENDING/PARTIAL row 영역에서 strategy 영역 조회 (사이클 147).

    `OrderEngine._handle_sell_fill` + `_handle_buy_fill` 영역의 매핑 dict miss 시
    잘못된 "momentum" 하드코딩 폴백 영역 영구 차단용 fallback chain.

    005940 NH투자증권 사고 (2026-06-16 08:00 SELL → 09:09 reboot → 09:18 callback exception)
    재발 영구 차단.

    Args:
        ticker: 6자리 종목코드
        order_no: KIS 주문번호 (사이클 30 UNIQUE 인덱스 정합)
        trade_type: TradeType.BUY / TradeType.SELL

    Returns:
        strategy str (PENDING/PARTIAL row 1건 매칭) / None (0건 또는 예외 graceful)
    """
    try:
        rows = await pg.fetch(
            """
            SELECT strategy FROM trade_history
            WHERE ticker = $1 AND order_no = $2 AND trade_type = $3
            AND status = ANY($4::text[])
            LIMIT 1
            """,
            ticker,
            order_no,
            trade_type.value,
            [TradeStatus.PENDING.value, TradeStatus.PARTIAL.value],
        )
        if not rows:
            return None
        return rows[0].get("strategy")
    except Exception as exc:
        logger.warning(
            "[trade_history_strategy_lookup_failed] ticker=%s order_no=%s trade_type=%s err=%r",
            ticker, order_no, trade_type.value, exc,
        )
        return None


async def _update_trade_status_by_order_no(
    order_no: str,
    trade_type: TradeType,
    status: TradeStatus,
    price: int | None = None,
    profit_loss: float | None = None,
) -> int:
    """order_no 단일 키 영역 영구 영속 강제 UPDATE (사이클 147).

    `_handle_sell_fill` 보정 INSERT 영역 UniqueViolation 시 fallback.
    strategy 필터 영역 폐기 영구 영속 — 사이클 30 부분 UNIQUE 인덱스
    `(ticker, order_no, trade_type)` 영역 영구 영속 정합.

    Args:
        order_no: KIS 주문번호 (단일 키 영구 영속)
        trade_type: TradeType.BUY / TradeType.SELL
        status: TradeStatus.COMPLETED / PARTIAL / CANCELLED
        price: 체결가 (옵셔널)
        profit_loss: 실현손익 (옵셔널)

    Returns:
        affected row 수
    """
    set_clauses = ["status = $1"]
    args: list = [status.value]

    if price is not None:
        args.append(float(price))
        set_clauses.append(f"price = ${len(args)}")
    if profit_loss is not None:
        args.append(float(profit_loss))
        set_clauses.append(f"profit_loss = ${len(args)}")

    args.extend([order_no, trade_type.value, TradeStatus.PENDING.value])
    order_no_idx = len(args) - 2
    type_idx = len(args) - 1
    pending_idx = len(args)

    sql = (
        f"UPDATE trade_history SET {', '.join(set_clauses)} "
        f"WHERE order_no = ${order_no_idx} AND trade_type = ${type_idx} "
        f"AND status = ${pending_idx}"
    )

    try:
        result = await pg.execute(sql, *args)
        affected = _parse_affected(result)
        logger.info(
            "[trade_status_update_by_order_no] order_no=%s trade_type=%s status=%s affected=%d",
            order_no, trade_type.value, status.value, affected,
        )
        return affected
    except Exception as exc:
        logger.warning(
            "[trade_status_update_by_order_no_failed] order_no=%s err=%r",
            order_no, exc,
        )
        return 0


async def mark_pending_buys_completed(ticker: str) -> None:
    """ticker 의 PENDING BUY row 전량을 COMPLETED 로 일괄 갱신한다 (사이클 M5).

    `scheduler._sync_positions_from_balance` + `boot_manager.boot()` 공통 전환 대상
    (기존 supabase update/eq 체인 방식 — status COMPLETED / ticker / trade_type BUY /
    status PENDING 필터). 체결통보 누락으로 상태가 갱신되지 않은 경우 잔고 sync
    시점에 보정. graceful — 예외 미전파 (기존 `except Exception: pass` 계약 보존,
    호출부 hot path 보호).
    """
    try:
        await pg.execute(
            """
            UPDATE trade_history SET status = $1
            WHERE ticker = $2 AND trade_type = $3 AND status = $4
            """,
            TradeStatus.COMPLETED.value,
            ticker,
            TradeType.BUY.value,
            TradeStatus.PENDING.value,
        )
    except Exception as exc:
        logger.debug(
            "[mark_pending_buys_completed_failed] ticker=%s err=%r", ticker, exc,
        )


async def get_recent_buy_strategy(ticker: str) -> str | None:
    """ticker 의 가장 최근 BUY row(전체 status, order_no 무관) 의 strategy 를 조회한다 (사이클 M5).

    `scheduler._sync_positions_from_balance` + `boot_manager.boot()` 공통 전환 대상
    (기존 `select(strategy).eq(ticker).eq(BUY).order(timestamp desc).limit(1)`).
    `_lookup_strategy_from_trade_history` (사이클 147) 와 다른 점 — 그쪽은 order_no +
    PENDING/PARTIAL 필터 한정, 이 함수는 order_no 무관 최근 BUY 아무 status.

    Returns:
        strategy str (1건 매칭) / None (0건 또는 예외 graceful — 호출자 "momentum" 폴백)
    """
    try:
        rows = await pg.fetch(
            """
            SELECT strategy FROM trade_history
            WHERE ticker = $1 AND trade_type = $2
            ORDER BY timestamp DESC LIMIT 1
            """,
            ticker,
            TradeType.BUY.value,
        )
        if not rows:
            return None
        return rows[0].get("strategy")
    except Exception as exc:
        logger.debug(
            "[get_recent_buy_strategy_failed] ticker=%s err=%r", ticker, exc,
        )
        return None


async def get_today_buys_ticker_strategy() -> list[dict]:
    """오늘(KST) BUY row 의 (ticker, strategy) 목록을 조회한다 (사이클 M5, boot_manager 전용).

    기존 `select(ticker, strategy).eq(trade_type,BUY).gte(timestamp, today.isoformat())`
    (TZ-naive) → `_today_kst_iso()` (`+09:00` 명시) 로 시정 (사이클 53 B-4 계약 —
    TZ-naive 는 KST 00:00~09:00 매수 기록 누락 위험).

    Returns:
        [{"ticker": str, "strategy": str}, ...] / 예외 시 빈 리스트 graceful (boot 루프 보호)
    """
    try:
        today_iso = _today_kst_iso()
        rows = await pg.fetch(
            """
            SELECT ticker, strategy FROM trade_history
            WHERE trade_type = $1 AND timestamp >= $2
            """,
            TradeType.BUY.value,
            datetime.fromisoformat(today_iso),
        )
        return rows or []
    except Exception as exc:
        logger.debug("[get_today_buys_ticker_strategy_failed] err=%r", exc)
        return []


async def get_today_trades_for_settlement(strategy: str | None = None) -> list[dict]:
    """정산용 — 당일 체결 거래 전체(중복 dedup 없음, 매수+매도 합산용).

    COMPLETED + PARTIAL 상태만 포함. 매매 cashflow / 실현손익 합 계산에 사용.
    `_today_kst_iso()` 로 PostgreSQL TIMESTAMPTZ 와 timezone 명시 비교.
    """
    today_iso = _today_kst_iso()

    sql = f"""
        SELECT t.*, {_TS_SELECT} FROM trade_history t
        WHERE timestamp >= $1 AND status = ANY($2::text[])
    """
    args: list = [datetime.fromisoformat(today_iso), ["COMPLETED", "PARTIAL"]]
    if strategy:
        sql += f" AND strategy = ${len(args) + 1}"
        args.append(strategy)
    sql += " ORDER BY t.timestamp ASC"

    return await pg.fetch(sql, *args) or []


async def get_today_buy_trades(strategy: str | None = None) -> list[dict]:
    """당일 매수 기록을 조회한다 (포지션 복구용 — ticker 별 dedupe).

    `_today_kst_iso()` 로 timezone 명시 — KST 09시 이전 매수 기록 누락 차단
    (2026-05-12 005930 보완 INSERT 사고 대응).

    사이클 30 (긴급, 2026-05-21) — 본 함수의 ticker dedupe 는 의도된 동작 (포지션
    복구용 — 매수 시점 매핑 잔존). `_sync_orders_to_db` 중복 판정용으로는 부적합
    (같은 ticker 다른 order_no 가 가려져 핑퐁 INSERT — 042700 사고). sync 용은
    신규 `get_today_buy_trades_for_sync()` 사용.
    """
    today_iso = _today_kst_iso()

    sql = f"""
        SELECT t.*, {_TS_SELECT} FROM trade_history t
        WHERE trade_type = 'BUY' AND timestamp >= $1 AND status = ANY($2::text[])
    """
    args: list = [datetime.fromisoformat(today_iso), ["PENDING", "COMPLETED", "PARTIAL"]]
    if strategy:
        sql += f" AND strategy = ${len(args) + 1}"
        args.append(strategy)
    sql += " ORDER BY t.timestamp DESC"

    rows = await pg.fetch(sql, *args) or []
    # 같은 종목이 여러 번 매수된 경우 최신 기록만 사용
    seen: dict[str, dict] = {}
    for row in rows:
        ticker = row["ticker"]
        if ticker not in seen:
            seen[ticker] = row
    return list(seen.values())


async def get_today_buy_trades_for_funnel() -> list[dict]:
    """funnel cross-check 전용 — dedupe 없음 + CANCELLED 포함 모든 BUY row 반환.

    PR-D 보강 (Copilot/Codex, 2026-05-14):
    - `get_today_buy_trades()` 는 포지션 복구용 (ticker 별 dedupe + CANCELLED 필터).
      → funnel 카운트에 부적합: (1) 같은 ticker 재진입/DCA/partial fills 시
      under-count, (2) 두 전략이 같은 ticker 매수 시 최신 row 의 strategy 만
      반영 (다른 전략 funnel 0 잔존), (3) CANCELLED 매수는 orders 미반영.
    - 이 함수는 raw 모든 BUY row 를 반환 — strategy_funnel cross-check 가
      EC2 재시작 시 in-memory 카운터 회복하려던 본래 목적 달성.

    `status in (PENDING, COMPLETED, PARTIAL, CANCELLED)` 전부 포함.
    """
    today_iso = _today_kst_iso()

    sql = f"""
        SELECT t.*, {_TS_SELECT} FROM trade_history t
        WHERE trade_type = 'BUY' AND timestamp >= $1 AND status = ANY($2::text[])
        ORDER BY t.timestamp DESC
    """
    rows = await pg.fetch(
        sql, datetime.fromisoformat(today_iso), ["PENDING", "COMPLETED", "PARTIAL", "CANCELLED"]
    )
    return rows or []


async def get_today_sell_trades(strategy: str | None = None) -> list[dict]:
    """당일 매도 기록을 조회한다 (포지션/손익 매핑용 — ticker 별 dedupe).

    사이클 30 (긴급, 2026-05-21) — 본 함수의 ticker dedupe 는 의도된 동작 (포지션
    복구·손익 매핑용). `_sync_orders_to_db` 중복 판정용으로는 부적합 (같은 ticker
    다른 order_no 가 가려져 핑퐁 INSERT 결함 — 042700 사고). sync 용은 신규
    `get_today_sell_trades_for_sync()` 사용.
    """
    today_iso = _today_kst_iso()

    sql = f"""
        SELECT t.*, {_TS_SELECT} FROM trade_history t
        WHERE trade_type = 'SELL' AND timestamp >= $1 AND status = ANY($2::text[])
    """
    args: list = [datetime.fromisoformat(today_iso), ["COMPLETED", "PARTIAL"]]
    if strategy:
        sql += f" AND strategy = ${len(args) + 1}"
        args.append(strategy)
    sql += " ORDER BY t.timestamp DESC"

    rows = await pg.fetch(sql, *args) or []
    seen: dict[str, dict] = {}
    for row in rows:
        ticker = row["ticker"]
        if ticker not in seen:
            seen[ticker] = row
    return list(seen.values())


# ---------------------------------------------------------------------------
# 사이클 30 (긴급, 2026-05-21) — `_sync_orders_to_db` 중복 판정용 신규 함수.
#
# 결함 배경:
# - 2026-05-20 042700 한미반도체 trade_history 19건 중 15건 중복 (실거래 4건).
# - `_sync_orders_to_db` (scheduler.py:1996-2001) 가 `get_today_buy_trades()` 호출
#   → ticker 별 dedupe 결과 1건만 반환 → 같은 ticker 다른 order_no 가 가려져 신규
#   판정 → INSERT. 매 재기동마다 누적 (무한 핑퐁).
#
# 본 함수 (`_for_sync`) 의 차이점:
# - `get_today_buy_trades()` (포지션 복구용): ticker dedupe O / CANCELLED 제외 X
# - `get_today_buy_trades_for_funnel()` (funnel cross-check): dedupe X / CANCELLED **포함**
# - `get_today_buy_trades_for_sync()` (본 함수, sync 중복 판정): dedupe X / CANCELLED 제외
#   + optional ticker filter
# ---------------------------------------------------------------------------


async def get_today_buy_trades_for_sync(ticker: str | None = None) -> list[dict]:
    """`_sync_orders_to_db` 중복 판정 전용 — dedupe 없음 + CANCELLED 제외 + optional ticker filter.

    사이클 30 (긴급, 2026-05-21) — 042700 무한 핑퐁 사고 대응.
    `(ticker, order_no)` 페어 정확 추적이 필요한 sync 경로 전용 (PR 명시 분리).

    Args:
        ticker: 단일 ticker 만 조회 (옵션). None 이면 당일 전체.

    Returns:
        raw row list. 같은 ticker 의 모든 order_no 보존 (dedupe 없음).
        status in (PENDING, COMPLETED, PARTIAL) — CANCELLED 제외 (sync 무관 row 차단).
    """
    today_iso = _today_kst_iso()

    sql = f"""
        SELECT t.*, {_TS_SELECT} FROM trade_history t
        WHERE trade_type = 'BUY' AND timestamp >= $1 AND status = ANY($2::text[])
    """
    args: list = [datetime.fromisoformat(today_iso), ["PENDING", "COMPLETED", "PARTIAL"]]
    if ticker:
        sql += f" AND ticker = ${len(args) + 1}"
        args.append(ticker)
    sql += " ORDER BY t.timestamp DESC"

    return await pg.fetch(sql, *args) or []


async def get_today_sell_trades_for_sync(ticker: str | None = None) -> list[dict]:
    """`_sync_orders_to_db` 중복 판정 전용 (매도) — dedupe 없음 + CANCELLED 제외 + optional ticker filter.

    사이클 30 (긴급, 2026-05-21) — 042700 무한 핑퐁 사고 대응. 매수 동일 패턴.
    """
    today_iso = _today_kst_iso()

    sql = f"""
        SELECT t.*, {_TS_SELECT} FROM trade_history t
        WHERE trade_type = 'SELL' AND timestamp >= $1 AND status = ANY($2::text[])
    """
    args: list = [datetime.fromisoformat(today_iso), ["PENDING", "COMPLETED", "PARTIAL"]]
    if ticker:
        sql += f" AND ticker = ${len(args) + 1}"
        args.append(ticker)
    sql += " ORDER BY t.timestamp DESC"

    return await pg.fetch(sql, *args) or []


async def get_trades(
    limit: int = 50,
    offset: int = 0,
    ticker: str | None = None,
    strategy: str | None = None,
) -> tuple[list[dict], int]:
    """거래 내역을 조회한다. (데이터, 전체 건수) 반환."""
    count_sql = "SELECT count(*) FROM trade_history t WHERE 1=1"
    data_sql = f"SELECT t.*, {_TS_SELECT} FROM trade_history t WHERE 1=1"
    count_args: list = []
    data_args: list = []

    if ticker:
        count_args.append(ticker)
        count_sql += f" AND ticker = ${len(count_args)}"
        data_args.append(ticker)
        data_sql += f" AND ticker = ${len(data_args)}"
    if strategy:
        count_args.append(strategy)
        count_sql += f" AND strategy = ${len(count_args)}"
        data_args.append(strategy)
        data_sql += f" AND strategy = ${len(data_args)}"

    data_args.extend([limit, offset])
    data_sql += (
        f" ORDER BY t.timestamp DESC LIMIT ${len(data_args) - 1} OFFSET ${len(data_args)}"
    )

    total = await pg.fetchval(count_sql, *count_args)
    rows = await pg.fetch(data_sql, *data_args)
    return rows or [], total or 0


async def get_trades_in_range(
    start_date,
    end_date,
    strategy: str | None = None,
) -> list[dict]:
    """[start_date, end_date] 범위의 거래 기록을 timestamp 기준 inclusive하게 조회한다.

    파라미터 추천 모듈 등에서 N영업일치 통계 산출에 사용한다.
    """
    start_iso = f"{start_date.isoformat()}T00:00:00+09:00"
    end_iso = f"{end_date.isoformat()}T23:59:59.999999+09:00"

    sql = f"""
        SELECT t.*, {_TS_SELECT} FROM trade_history t
        WHERE timestamp >= $1 AND timestamp <= $2
    """
    args: list = [datetime.fromisoformat(start_iso), datetime.fromisoformat(end_iso)]
    if strategy:
        sql += f" AND strategy = ${len(args) + 1}"
        args.append(strategy)
    sql += " ORDER BY t.timestamp ASC"

    return await pg.fetch(sql, *args) or []


async def get_trade_pairs(
    strategy: str | None = None,
    ticker: str | None = None,
) -> list[dict]:
    """매수/매도 페어 리스트를 반환한다 (매매손익 뷰용).

    페어링 모델: 같은 (ticker, strategy) 그룹 내에서 timestamp 오름차순으로
    누적 보유 수량(position)을 추적하다가 0으로 돌아오는 시점마다 한 페어 emit.
    분할 매수/매도가 한 사이클 안에 발생해도 매수가/매도가는 가중평균으로 한 행에 표현.
    매도 후에도 잔량이 남으면(보유 중) 'open' 페어 1행 추가 — 미실현 손익은
    `scanner.ticker_prices`의 현재가를 사용해 계산, 시세 미수신이면 None.

    Returns: 각 dict는 다음 키를 갖는다 —
        buy_date, buy_time, sell_date, sell_time, ticker, ticker_name,
        buy_price, buy_qty, sell_price, sell_qty,
        profit_loss, profit_rate, status('closed'|'open'), strategy
    """
    from collections import defaultdict
    from decimal import Decimal

    # 1) trade_history 전체 조회 (체결 또는 부분체결만 페어링 대상)
    sql = f"""
        SELECT t.*, {_TS_SELECT} FROM trade_history t
        WHERE status = ANY($1::text[])
    """
    args: list = [["COMPLETED", "PARTIAL"]]
    if strategy:
        sql += f" AND strategy = ${len(args) + 1}"
        args.append(strategy)
    if ticker:
        sql += f" AND ticker = ${len(args) + 1}"
        args.append(ticker)
    sql += " ORDER BY t.timestamp ASC"

    rows = await pg.fetch(sql, *args) or []

    # 2) (ticker, strategy)별 그룹화
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        key = (r.get("ticker") or "", r.get("strategy") or "")
        grouped[key].append(r)

    # 3) 시세 캐시 (open 페어 미실현 손익용) — read-only
    try:
        from src.engine.scanner import ticker_prices  # type: ignore
    except Exception:
        ticker_prices = {}  # 모듈 미로드 환경 fallback

    pairs: list[dict] = []

    for (tkr, strat), trades in grouped.items():
        ticker_name = ""
        for t in trades:
            if t.get("ticker_name"):
                ticker_name = t["ticker_name"]
                break

        position = 0
        buy_buf: list[tuple[str, Decimal, int]] = []   # (ts, price, qty)
        sell_buf: list[tuple[str, Decimal, int]] = []

        def emit_closed():
            buy_total_qty = sum(q for _, _, q in buy_buf)
            sell_total_qty = sum(q for _, _, q in sell_buf)
            if buy_total_qty <= 0:
                return
            buy_total_amt = sum(p * q for _, p, q in buy_buf)
            sell_total_amt = sum(p * q for _, p, q in sell_buf)
            buy_avg = buy_total_amt / buy_total_qty
            sell_avg = sell_total_amt / sell_total_qty if sell_total_qty else Decimal(0)
            pl = (sell_avg - buy_avg) * sell_total_qty
            rate = ((sell_avg - buy_avg) / buy_avg * 100) if buy_avg else Decimal(0)
            buy_ts = buy_buf[0][0]
            sell_ts = sell_buf[-1][0] if sell_buf else None
            buy_d, buy_t = _to_kst(buy_ts)
            sell_d, sell_t = _to_kst(sell_ts)
            pairs.append({
                "buy_date": buy_d,
                "buy_time": buy_t,
                "sell_date": sell_d,
                "sell_time": sell_t,
                "ticker": tkr,
                "ticker_name": ticker_name,
                "buy_price": float(round(buy_avg, 2)),
                "buy_qty": int(buy_total_qty),
                "sell_price": float(round(sell_avg, 2)),
                "sell_qty": int(sell_total_qty),
                "profit_loss": float(round(pl, 2)),
                "profit_rate": float(round(rate, 4)),
                "status": "closed",
                "strategy": strat,
            })

        for t in trades:
            ttype = t.get("trade_type")
            try:
                p = Decimal(str(t.get("price") or 0))
                q = int(t.get("quantity") or 0)
            except Exception:
                continue
            if q <= 0:
                continue
            ts = t.get("timestamp") or ""
            if ttype == "BUY":
                buy_buf.append((ts, p, q))
                position += q
            elif ttype == "SELL":
                sell_buf.append((ts, p, q))
                position -= q
                if position <= 0:
                    emit_closed()
                    buy_buf, sell_buf = [], []
                    position = 0  # 음수 케이스(데이터 이상) 방어

        # 그룹 끝: 잔여 보유분이 있으면 open 페어
        if position > 0 and buy_buf:
            buy_total_amt = sum(p * q for _, p, q in buy_buf)
            buy_total_qty = sum(q for _, _, q in buy_buf)
            buy_avg = buy_total_amt / buy_total_qty
            buy_ts = buy_buf[0][0]
            cur_price = ticker_prices.get(tkr, {}).get("current_price", 0) or 0
            if cur_price > 0:
                cur_dec = Decimal(str(cur_price))
                pl = (cur_dec - buy_avg) * position
                rate = ((cur_dec - buy_avg) / buy_avg * 100) if buy_avg else Decimal(0)
                pl_val: float | None = float(round(pl, 2))
                rate_val: float | None = float(round(rate, 4))
            else:
                pl_val = None
                rate_val = None
            buy_d, buy_t = _to_kst(buy_ts)
            pairs.append({
                "buy_date": buy_d,
                "buy_time": buy_t,
                "sell_date": None,
                "sell_time": None,
                "ticker": tkr,
                "ticker_name": ticker_name,
                "buy_price": float(round(buy_avg, 2)),
                "buy_qty": int(position),
                "sell_price": None,
                "sell_qty": None,
                "profit_loss": pl_val,
                "profit_rate": rate_val,
                "status": "open",
                "strategy": strat,
            })

    # 4) 신규 매수가 위로 오도록 buy_date+buy_time DESC. open이 closed보다 우선
    def _sort_key(p: dict):
        # status=open(보유 중)을 먼저, 그 안에서 buy_date DESC
        return (0 if p["status"] == "open" else 1,
                -(int((p["buy_date"] or "0").replace("-", "") or 0)),
                -(int((p["buy_time"] or "00:00:00").replace(":", "") or 0)))

    pairs.sort(key=_sort_key)
    return pairs
