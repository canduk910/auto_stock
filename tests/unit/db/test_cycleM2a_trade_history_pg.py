"""사이클 M2a (Red) — src/db/trade_history.py asyncpg 전환 계약 가드 (매매 hot path 핵심).

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 2 — 매매 hot path, HIGH).

현행 trade_history.py = supabase-py 체인. 이 증분 = `pg.*` 전환.
**함수 계약(시그니처·반환형·graceful) 100% 보존** → 호출부(order_engine/scheduler) diff 0.

⚠️ 3대 미묘 계약 (hot path 절대 보존):
1. **TIMESTAMPTZ `+09:00` str 계약 (사이클 53 B-4)**:
   - 쓰기: `insert_trade` timestamp 는 datetime 바인딩 (asyncpg TIMESTAMPTZ str 금지, M1 패턴 2).
   - 읽기: SELECT 가 timestamp 를 `to_char(ts,'YYYY-MM-DD"T"HH24:MI:SS+09:00') AS timestamp` 로
     **str `+09:00`** 반환 → `_to_kst(row["timestamp"])` / `get_trade_pairs` 소비처 무변경 보장.
   - 범위: `get_trades_in_range` 가 `"{d}T00:00:00+09:00"` / `"{d}T23:59:59.999999+09:00"` 바인딩
     (KST 00:00~09:00 거래 누락 차단, 사이클 53 B-4).
2. **`get_trade_pairs` Decimal 페어링** — 가중평균 buy/sell, closed/open emit. 이미 Decimal(str(...)) 명시.
3. **count + range 페이징** — `get_trades` = 별도 count SELECT(총건수) + LIMIT/OFFSET data.
   `.in_(status)` = `status = ANY($1::text[])`. sync 함수 dedupe 없음·CANCELLED 제외 (사이클 30/73).

Red 유효성: production 미변경 → pg mock 미발화 → 계약 단언 FAIL.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

from src.models.trade import TradeRecord, TradeStatus, TradeType


def _make_record(**over) -> TradeRecord:
    base = dict(
        ticker="005930",
        ticker_name="삼성전자",
        trade_type=TradeType.BUY,
        price=70000,
        quantity=10,
        profit_loss=0,
        status=TradeStatus.PENDING,
        strategy="momentum",
        order_no="BUY-000001",
    )
    base.update(over)
    return TradeRecord(**base)


# ---------------------------------------------------------------------------
# insert_trade — INSERT + timestamp datetime 바인딩 (M1 패턴 2)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_insert_trade_uses_pg_execute_insert():
    """insert_trade → pg.execute INSERT INTO trade_history. price/profit_loss float 캐스트."""
    from src.db import trade_history

    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        out = await trade_history.insert_trade(_make_record())

    assert out is None, "insert_trade 반환형 None 계약 보존."
    all_sql = _collect_sql(pg_mod)
    assert any("INSERT INTO trade_history" in s for s in all_sql), "INSERT INTO trade_history 누락."
    args = _insert_args(pg_mod)
    assert "005930" in args, "ticker 바인딩 누락."
    assert "BUY" in args, "trade_type value 바인딩 누락."
    # price/profit_loss 는 float 캐스트 (기존 계약)
    assert any(isinstance(a, float) and abs(a - 70000.0) < 1e-6 for a in args), "price float 캐스트 누락."


@pytest.mark.asyncio
async def test_insert_trade_timestamp_is_datetime():
    """⚠️ timestamp TIMESTAMPTZ 바인딩은 datetime 인스턴스 (M1 패턴 2 — asyncpg str 금지)."""
    from src.db import trade_history

    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await trade_history.insert_trade(_make_record())

    args = _insert_args(pg_mod)
    assert any(isinstance(a, datetime) for a in args), (
        "timestamp 는 datetime 바인딩 (datetime.now(KST)) — str 바인딩 시 asyncpg TIMESTAMPTZ 캐스트 실패."
    )


# ---------------------------------------------------------------------------
# update_trade_status — UPDATE affected 수 ("UPDATE N" 파싱) +
# 4-eq + (opt-in) 당일 하한 + (opt-in) order_no 필터
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_trade_status_returns_affected_count():
    """update_trade_status → pg.execute UPDATE, "UPDATE N" 파싱 → affected int 반환.

    체결통보 선행 race 판단(0건 → 보정 INSERT)의 핵심 계약 — affected 수 정확 보존.
    """
    from src.db import trade_history

    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="UPDATE 1")
        affected = await trade_history.update_trade_status(
            "005930", TradeType.BUY, TradeStatus.COMPLETED, strategy="momentum",
            price=70000, profit_loss=0.0,
        )

    assert affected == 1, "'UPDATE 1' → affected=1 (execute 상태 문자열 파싱 계약)."
    sql = _first_sql_matching(pg_mod, "UPDATE")
    assert sql is not None and "trade_history" in sql
    # 4-eq 필터 보존 (ticker/trade_type/status=PENDING/strategy) — 기본 호출(match_partial
    # 미전달) 한정. cycle273a 는 opt-in `match_partial=True` 시 PENDING∪PARTIAL 로
    # 넓히는 것을 허용하지만, 그 경로는 여기 대상이 아니다(별도 테스트).
    assert "PENDING" in sql or "PENDING" in str(pg_mod.execute.await_args.args), (
        "PENDING 필터 보존 누락 (기본 경로 갱신)."
    )


@pytest.mark.asyncio
async def test_update_trade_status_zero_affected():
    """0건 갱신 → 0 반환 (체결통보 선행 race → 보정 INSERT 트리거 계약)."""
    from src.db import trade_history

    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="UPDATE 0")
        affected = await trade_history.update_trade_status(
            "005930", TradeType.SELL, TradeStatus.COMPLETED,
        )

    assert affected == 0, "'UPDATE 0' → affected=0 (보정 INSERT 트리거)."


# ---------------------------------------------------------------------------
# get_trades — count + range 페이징 (총건수 정확) + .in_ / .eq
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_trades_count_and_range_pagination():
    """get_trades → (data, total). 별도 count SELECT(총건수) + LIMIT/OFFSET data."""
    from src.db import trade_history

    data_rows = [
        {"ticker": "005930", "trade_type": "BUY", "timestamp": "2026-07-16T10:00:00+09:00"},
        {"ticker": "000660", "trade_type": "SELL", "timestamp": "2026-07-16T09:00:00+09:00"},
    ]
    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=data_rows)
        pg_mod.fetchval = AsyncMock(return_value=57)  # count(*) 총건수
        out_data, total = await trade_history.get_trades(limit=50, offset=0)

    assert out_data == data_rows, "data 반환 계약."
    assert total == 57, "total 은 별도 count(*) SELECT 결과 (페이징 총건수 정확)."
    # count 는 fetchval("SELECT count(*) ...") 로 발화
    count_sql = pg_mod.fetchval.await_args.args[0]
    assert "count(" in count_sql.lower(), "count(*) 별도 SELECT 누락."
    # data 는 LIMIT/OFFSET
    data_sql = pg_mod.fetch.await_args.args[0]
    assert "LIMIT" in data_sql.upper(), "range → LIMIT 누락."
    assert "OFFSET" in data_sql.upper(), "range → OFFSET 누락."
    assert "ORDER BY" in data_sql.upper() and "DESC" in data_sql.upper(), "timestamp DESC 정렬 누락."


@pytest.mark.asyncio
async def test_get_trades_ticker_strategy_filter():
    """get_trades(ticker=, strategy=) → 두 필터 count/data 양쪽 반영."""
    from src.db import trade_history

    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchval = AsyncMock(return_value=0)
        await trade_history.get_trades(limit=10, offset=5, ticker="005930", strategy="momentum")

    # count + data 양쪽에 ticker/strategy 바인딩 (인자 어딘가에 등장)
    count_args = pg_mod.fetchval.await_args.args[1:]
    data_args = pg_mod.fetch.await_args.args[1:]
    assert "005930" in count_args and "005930" in data_args, "ticker 필터 count/data 양쪽 누락."
    assert "momentum" in count_args and "momentum" in data_args, "strategy 필터 양쪽 누락."


# ---------------------------------------------------------------------------
# get_trades_in_range — ⚠️ +09:00 TZ 경계 (사이클 53 B-4)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_trades_in_range_kst_boundary_bindings():
    """⚠️ get_trades_in_range → start "{d}T00:00:00+09:00" / end "{d}T23:59:59.999999+09:00" 바인딩.

    사이클 53 B-4: TZ 명시 없으면 UTC 해석 → KST 00:00~09:00 거래 누락. +09:00 필수.
    """
    from src.db import trade_history

    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await trade_history.get_trades_in_range(date(2026, 7, 14), date(2026, 7, 16))

    args = pg_mod.fetch.await_args.args[1:]
    # start/end 바인딩이 +09:00 KST 경계를 담고 있어야 함 (str 또는 datetime)
    def _contains_kst_start(a) -> bool:
        if isinstance(a, str):
            return a == "2026-07-14T00:00:00+09:00"
        if isinstance(a, datetime):
            return a == datetime.fromisoformat("2026-07-14T00:00:00+09:00")
        return False

    def _contains_kst_end(a) -> bool:
        if isinstance(a, str):
            return a == "2026-07-16T23:59:59.999999+09:00"
        if isinstance(a, datetime):
            return a == datetime.fromisoformat("2026-07-16T23:59:59.999999+09:00")
        return False

    assert any(_contains_kst_start(a) for a in args), (
        "start 경계 +09:00 바인딩 누락 (KST 00:00, 사이클 53 B-4)."
    )
    assert any(_contains_kst_end(a) for a in args), (
        "end 경계 +09:00 바인딩 누락 (KST 23:59, 사이클 53 B-4)."
    )


@pytest.mark.asyncio
async def test_get_trades_in_range_reads_timestamp_as_iso_str():
    """읽기 str 계약 — SELECT 결과 timestamp 를 _to_kst 가 파싱 가능한 +09:00 str 로 반환.

    asyncpg TIMESTAMPTZ 는 기본 datetime 반환 → Green 은 to_char 로 str 캐스트해야
    _to_kst(row["timestamp"]) 계약이 유지된다. 반환 dict 를 그대로 pass-through 하는지 단언.
    """
    from src.db import trade_history

    rows = [{"ticker": "005930", "timestamp": "2026-07-16T08:30:00+09:00", "trade_type": "BUY"}]
    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await trade_history.get_trades_in_range(date(2026, 7, 16), date(2026, 7, 16))

    assert out == rows, "get_trades_in_range → fetch 결과 pass-through (timestamp str 계약)."
    # SELECT 가 timestamp 를 to_char 로 +09:00 str 캐스트 (읽기 str 계약)
    sql = pg_mod.fetch.await_args.args[0]
    assert "to_char" in sql.lower(), (
        "timestamp 읽기 str 계약: SELECT 가 to_char(...+09:00) 로 캐스트해야 _to_kst 계약 유지."
    )


# ---------------------------------------------------------------------------
# get_trade_pairs — Decimal 페어링 + closed/open + .in_(COMPLETED/PARTIAL)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_trade_pairs_decimal_weighted_avg_closed():
    """get_trade_pairs → 매수/매도 페어링. profit_loss/가중평균 Decimal 보존 → float 반환."""
    from src.db import trade_history

    rows = [
        {"ticker": "005930", "ticker_name": "삼성전자", "strategy": "momentum",
         "trade_type": "BUY", "price": 70000, "quantity": 10,
         "timestamp": "2026-07-16T09:00:00+09:00", "status": "COMPLETED"},
        {"ticker": "005930", "ticker_name": "삼성전자", "strategy": "momentum",
         "trade_type": "SELL", "price": 72000, "quantity": 10,
         "timestamp": "2026-07-16T10:00:00+09:00", "status": "COMPLETED"},
    ]
    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await trade_history.get_trade_pairs()

    assert len(out) == 1, "매수 10 + 매도 10 → position 0 → closed 페어 1건."
    pair = out[0]
    assert pair["status"] == "closed"
    assert pair["buy_price"] == 70000.0 and pair["sell_price"] == 72000.0
    # profit_loss = (72000-70000)*10 = 20000 (Decimal → float 정합)
    assert abs(pair["profit_loss"] - 20000.0) < 1e-6, "Decimal 페어링 손익 계약 (20,000)."
    assert abs(pair["profit_rate"] - (2000 / 70000 * 100)) < 1e-3
    # .in_(COMPLETED/PARTIAL) = ANY($1::text[]) 배열 바인딩
    sql = pg_mod.fetch.await_args.args[0]
    assert "ANY(" in sql.upper() or "= ANY" in sql.upper(), (
        ".in_(status) → status = ANY($1::text[]) 배열 바인딩 계약."
    )


@pytest.mark.asyncio
async def test_get_trade_pairs_open_pair_when_holding():
    """매수만 있고 미매도 → open 페어 1건 (미실현 손익 = 시세 없으면 None)."""
    from src.db import trade_history

    rows = [
        {"ticker": "000660", "ticker_name": "SK하이닉스", "strategy": "volatility_breakout",
         "trade_type": "BUY", "price": 100000, "quantity": 5,
         "timestamp": "2026-07-16T09:00:00+09:00", "status": "COMPLETED"},
    ]
    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await trade_history.get_trade_pairs()

    assert len(out) == 1
    assert out[0]["status"] == "open", "잔여 보유 → open 페어."
    assert out[0]["buy_qty"] == 5


# ---------------------------------------------------------------------------
# sync 함수 — dedupe 없음 + CANCELLED 제외 (사이클 30/73)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_today_buy_trades_for_sync_no_dedupe():
    """get_today_buy_trades_for_sync → 같은 ticker 다른 order_no 전부 보존 (dedupe 없음, 사이클 30)."""
    from src.db import trade_history

    rows = [
        {"ticker": "042700", "order_no": "A-1", "trade_type": "BUY", "status": "COMPLETED",
         "timestamp": "2026-07-16T09:00:00+09:00"},
        {"ticker": "042700", "order_no": "A-2", "trade_type": "BUY", "status": "COMPLETED",
         "timestamp": "2026-07-16T09:05:00+09:00"},
    ]
    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await trade_history.get_today_buy_trades_for_sync()

    assert len(out) == 2, (
        "sync 함수는 dedupe 없음 — 같은 ticker 다른 order_no 전부 보존 (042700 핑퐁 사고 차단)."
    )


@pytest.mark.asyncio
async def test_get_today_buy_trades_for_sync_excludes_cancelled():
    """get_today_buy_trades_for_sync → status.in_(PENDING/COMPLETED/PARTIAL), CANCELLED 제외 SQL 계약."""
    from src.db import trade_history

    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await trade_history.get_today_buy_trades_for_sync(ticker="042700")

    args = pg_mod.fetch.await_args.args[1:]
    # status 배열 인자 어딘가에 CANCELLED 미포함
    status_arrays = [a for a in args if isinstance(a, (list, tuple))]
    assert status_arrays, "status 배열 바인딩(ANY) 누락."
    joined = str(args)
    assert "CANCELLED" not in joined, "sync 는 CANCELLED 제외 계약 (사이클 30)."
    assert "PENDING" in joined and "COMPLETED" in joined and "PARTIAL" in joined, (
        "sync status 배열 = [PENDING, COMPLETED, PARTIAL] 계약 누락."
    )
    assert "042700" in args, "optional ticker filter 바인딩 누락."


@pytest.mark.asyncio
async def test_get_today_sell_trades_for_sync_no_dedupe_no_cancelled():
    """get_today_sell_trades_for_sync → dedupe 없음 + CANCELLED 제외 (매수 동일 패턴)."""
    from src.db import trade_history

    rows = [
        {"ticker": "042700", "order_no": "S-1", "trade_type": "SELL", "status": "COMPLETED",
         "timestamp": "2026-07-16T14:00:00+09:00"},
        {"ticker": "042700", "order_no": "S-2", "trade_type": "SELL", "status": "PARTIAL",
         "timestamp": "2026-07-16T14:05:00+09:00"},
    ]
    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await trade_history.get_today_sell_trades_for_sync()

    assert len(out) == 2, "매도 sync dedupe 없음."
    assert "CANCELLED" not in str(pg_mod.fetch.await_args.args), "매도 sync CANCELLED 제외 계약."


@pytest.mark.asyncio
async def test_get_today_buy_trades_dedupe_for_recovery():
    """포지션 복구용 get_today_buy_trades → ticker 별 dedupe (최신 1건). sync 와 구분 계약."""
    from src.db import trade_history

    rows = [
        {"ticker": "042700", "order_no": "A-2", "trade_type": "BUY", "status": "COMPLETED",
         "timestamp": "2026-07-16T09:05:00+09:00"},
        {"ticker": "042700", "order_no": "A-1", "trade_type": "BUY", "status": "COMPLETED",
         "timestamp": "2026-07-16T09:00:00+09:00"},
    ]
    with patch.object(trade_history, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await trade_history.get_today_buy_trades()

    assert len(out) == 1, "포지션 복구용은 ticker dedupe (최신 1건) — sync 와 절대 혼용 금지."


# ---------------------------------------------------------------------------
# _today_kst_iso — +09:00 timezone 명시 (사이클 53 유틸 무변경 계약)
# ---------------------------------------------------------------------------
def test_today_kst_iso_has_plus_09_00():
    """_today_kst_iso() 는 +09:00 명시 str (TIMESTAMPTZ UTC 해석 결함 차단)."""
    from src.db import trade_history

    iso = trade_history._today_kst_iso()
    assert iso.endswith("+09:00"), "_today_kst_iso() +09:00 명시 계약 (사이클 53 B-4 무변경)."
    assert "T00:00:00" in iso, "당일 00:00 KST 기준점."


def test_to_kst_parses_plus_09_00_str():
    """_to_kst(+09:00 str) → (KST date, KST time). 읽기 str 계약 소비처 무변경 검증."""
    from src.db import trade_history

    d, t = trade_history._to_kst("2026-07-16T08:30:00+09:00")
    assert d == "2026-07-16" and t == "08:30:00", "KST 08:30 파싱 계약 (읽기 str → _to_kst)."


# ---------------------------------------------------------------------------
# 계약 보존 불변식 — supabase 미참조 (pg 단독)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_trade_history_no_supabase_reference_after_transition():
    """전환 후 trade_history.py 는 supabase 를 참조하지 않는다 (pg 단독)."""
    from src.db import trade_history

    assert not hasattr(trade_history, "supabase"), (
        "전환 후 trade_history 모듈에 supabase 심볼이 남으면 안 됨 (pg 단독)."
    )
    assert hasattr(trade_history, "pg"), "trade_history 가 src.db.pg 를 import 해야 함."


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _collect_sql(pg_mod) -> list[str]:
    sqls: list[str] = []
    for name in ("execute", "fetchrow", "fetch", "fetchval"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            sqls.append(m.await_args.args[0])
    return sqls


def _insert_args(pg_mod) -> tuple:
    for name in ("execute", "fetchrow"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            sql = m.await_args.args[0]
            if "INSERT" in sql.upper():
                return m.await_args.args[1:]
    return ()


def _first_sql_matching(pg_mod, keyword: str) -> str | None:
    for name in ("execute", "fetchrow", "fetch"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            sql = m.await_args.args[0]
            if keyword.upper() in sql.upper():
                return sql
    return None
