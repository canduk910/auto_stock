"""사이클 122 (2026-06-12) — stock_master_daily CRUD + 활용 헬퍼 회귀 가드.

회귀 가드 매트릭스:
- G-DB1 (HIGH) — upsert_daily 단건 ON CONFLICT
- G-DB2 (HIGH) — upsert_batch 100건 단위 + graceful
- G-DB3 (HIGH) — get_recent_daily DESC 정렬 + clamp
- G-DB4 (HIGH) — get_donchian_high MAX(high_price)
- G-DB5 (HIGH) — get_atr Wilder True Range
- G-DB6 (MEDIUM) — get_recent_daily_with_fallback DB 우선 + KIS fallback
- G-DB7 (MEDIUM) — count_all / count_by_ticker / max_bas_dd 진단 영역

영속 의무:
- 사이클 14 fetch_daily_candles 재사용 (KIS 응답 키 호환)
- 사이클 68 KST 영속 (now_kst_iso)
- 사이클 81 G-AST1 raw JSONB 영속
- 사이클 88 G-REJECT graceful 단위
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db import stock_master_daily

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — KIS FHKST03010100 output2 row mock (chk_inquire_daily_itemchartprice.py 정본 정합)
# ---------------------------------------------------------------------------
def _kis_candle(
    bas_dd: str = "20260612",
    open_price: str = "70000",
    high_price: str = "71500",
    low_price: str = "69500",
    close_price: str = "71000",
    volume: str = "12345678",
    trade_value: str = "876543210000",
    change_rate: str = "1.43",
    flng_cls: str = "",
    prtt_rate: str = "0",
) -> dict:
    """KIS output2 row mock — 사이클 81 G-AST1 raw 전수 키 포함."""
    return {
        "stck_bsop_date": bas_dd,
        "stck_oprc": open_price,
        "stck_hgpr": high_price,
        "stck_lwpr": low_price,
        "stck_clpr": close_price,
        "acml_vol": volume,
        "acml_tr_pbmn": trade_value,
        "prdy_ctrt": change_rate,
        "flng_cls_code": flng_cls,
        "prtt_rate": prtt_rate,
    }


def _db_row(
    ticker: str = "005930",
    bas_dd: str = "2026-06-12",
    open_price: int = 70000,
    high_price: int = 71500,
    low_price: int = 69500,
    close_price: int = 71000,
    volume: int = 12345678,
) -> dict:
    """DB row mock — supabase select 응답 형식."""
    return {
        "ticker": ticker,
        "bas_dd": bas_dd,
        "open_price": open_price,
        "high_price": high_price,
        "low_price": low_price,
        "close_price": close_price,
        "volume": volume,
        "trade_value": 876543210000,
        "change_rate": 1.43,
        "raw": {"stck_bsop_date": bas_dd.replace("-", "")},
    }


# ---------------------------------------------------------------------------
# G-DB1 (HIGH) — upsert_daily 단건 ON CONFLICT (ticker, bas_dd)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_db1_upsert_daily_single_row_on_conflict():
    """단건 upsert 시 ON CONFLICT (ticker, bas_dd) 사용 + raw JSONB 보존.

    사이클 M2b — pg.execute("INSERT ... ON CONFLICT (ticker, bas_dd) ...", *args).
    raw dict 직접 바인딩 (codec 전담), bas_dd 는 date 바인딩.
    """
    with patch.object(stock_master_daily, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        candle = _kis_candle()
        await stock_master_daily.upsert_daily("005930", date(2026, 6, 12), candle)

    sql = pg_mod.execute.await_args.args[0]
    assert "INSERT INTO stock_master_daily" in sql, "INSERT INTO stock_master_daily 누락"
    assert "ON CONFLICT (ticker, bas_dd)" in sql.replace('"', ""), "복합키 ON CONFLICT 누락"
    args = pg_mod.execute.await_args.args[1:]
    assert "005930" in args, "ticker 바인딩 누락"
    assert date(2026, 6, 12) in args, "bas_dd date 바인딩 누락"
    assert 71000 in args and 71500 in args, "close/high price 바인딩 누락"
    # 사이클 81 G-AST1 — raw JSONB dict 직접 바인딩 (KIS 원본 키 영속)
    raw_arg = next((a for a in args if isinstance(a, dict) and "stck_bsop_date" in a), None)
    assert raw_arg is not None, "raw JSONB dict (KIS 원본 키) 바인딩 누락"


@pytest.mark.asyncio
async def test_g_db1_upsert_daily_bas_dd_parse_failure_graceful():
    """bas_dd 파싱 실패 시 graceful skip + WARNING 1행 — 사이클 88 G-REJECT.

    _candle_to_row 가 None 반환 → upsert_daily 가 WARNING + return (pg.execute 미발화).
    """
    with patch.object(stock_master_daily, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock()
        bad_candle = {"stck_bsop_date": "INVALID", "stck_clpr": "71000"}
        await stock_master_daily.upsert_daily("005930", date(2026, 6, 12), bad_candle)

    # graceful skip — pg.execute 호출 0건 (잘못된 데이터 영구 차단)
    assert pg_mod.execute.await_count == 0


# ---------------------------------------------------------------------------
# G-DB2 (HIGH) — upsert_batch 100건 단위 batch + graceful
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_db2_upsert_batch_100_per_chunk():
    """100건 단위 batch — Supabase HTTP/2 stale connection 회피 (사이클 26 답습).

    사이클 M2b — pg.executemany(SQL, arglist) 로 100건 chunk. 250건 → 3 chunk.
    """
    # 250건 → 100 + 100 + 50 = 3 batch
    candles = [_kis_candle(bas_dd=f"2026{(m % 12) + 1:02d}{(d % 28) + 1:02d}")
               for m in range(25) for d in range(10)]

    with patch.object(stock_master_daily, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock()
        upserted = await stock_master_daily.upsert_batch("005930", candles)

    # 3 chunk 호출됨 (executemany)
    assert pg_mod.executemany.await_count == 3
    assert upserted == 250
    # 복합키 ON CONFLICT
    sql = pg_mod.executemany.await_args_list[0].args[0]
    assert "ON CONFLICT (ticker, bas_dd)" in sql.replace('"', ""), "복합키 ON CONFLICT 누락"


@pytest.mark.asyncio
async def test_g_db2_upsert_batch_graceful_single_batch_failure():
    """batch 1건 실패 시 다음 batch 진행 — 사이클 88 G-REJECT.

    사이클 M2b — pg.executemany 첫 chunk raise → except 흡수 → 다음 chunk 진행.
    """
    # YYYYMMDD 형식 — 5개월 × 30일 = 150건 (단, 2/30 + 4/30 등 부정 일자 2건 skip)
    # 실제 _candle_to_row 파싱 통과 = 148건 → chunk 100 + 48 = 2 chunk
    candles = []
    for m in range(1, 6):  # 1~5월
        for d in range(1, 31):  # 1~30일
            candles.append(_kis_candle(bas_dd=f"2026{m:02d}{d:02d}"))
    assert len(candles) == 150

    call_count = [0]

    async def _executemany(sql, arglist):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("pg 일시 실패")
        return None

    with patch.object(stock_master_daily, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock(side_effect=_executemany)
        upserted = await stock_master_daily.upsert_batch("005930", candles)

    # 2 chunk 시도 (1 실패 + 1 성공)
    assert call_count[0] == 2
    # 첫 chunk 100 실패 + 두 번째 chunk 48 성공 (150 - 2 skip = 148)
    assert upserted == 48


@pytest.mark.asyncio
async def test_g_db2_upsert_batch_empty_returns_zero():
    """빈 candles → 즉시 0 반환 (pg.executemany 호출 0)."""
    with patch.object(stock_master_daily, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock()
        result = await stock_master_daily.upsert_batch("005930", [])
    assert result == 0
    assert pg_mod.executemany.await_count == 0


# ---------------------------------------------------------------------------
# G-DB3 (HIGH) — get_recent_daily bas_dd DESC + days clamp
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_db3_get_recent_daily_desc_with_clamp():
    """bas_dd DESC + days clamp (1~`_MAX_DAILY_ROWS`).

    사이클 M2b — pg.fetch("... ORDER BY bas_dd DESC LIMIT $2", ticker, clamped).
    cycle300 — 상한이 100 → `_MAX_DAILY_ROWS`(400) 로 올랐다. 여기서 재는 것은 그 숫자가
    아니라 **클램프가 살아 있다는 사실**이라, 상한을 넘는 요청이 상한으로 잘리는지만 본다
    (숫자 자체는 `test_cycle300_daily_depth_switch.py` 가 근거와 함께 잰다).
    """
    mock_rows = [_db_row(bas_dd=f"2026-06-{i:02d}") for i in range(12, 7, -1)]
    over = stock_master_daily._MAX_DAILY_ROWS + 100

    with patch.object(stock_master_daily, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=mock_rows)
        result = await stock_master_daily.get_recent_daily("005930", days=over)

    sql = pg_mod.fetch.await_args.args[0].upper()
    assert "ORDER BY BAS_DD DESC" in sql, "bas_dd DESC 정렬 누락"
    assert "LIMIT" in sql, "limit 절 누락"
    args = pg_mod.fetch.await_args.args[1:]
    assert "005930" in args, "ticker 바인딩 누락"
    assert stock_master_daily._MAX_DAILY_ROWS in args, (
        f"days={over} → 상한 {stock_master_daily._MAX_DAILY_ROWS} 클램프 바인딩 누락"
    )
    assert len(result) == 5  # mock 응답 길이


@pytest.mark.asyncio
async def test_g_db3_get_recent_daily_graceful_on_db_failure():
    """DB 실패 시 빈 list 반환 — 호출자 KIS fallback 영역."""
    with patch.object(stock_master_daily, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=RuntimeError("pg down"))
        result = await stock_master_daily.get_recent_daily("005930", days=20)

    assert result == []


# ---------------------------------------------------------------------------
# G-DB4 (HIGH) — get_donchian_high MAX(high_price)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_db4_get_donchian_high_max_high_price():
    """donchian 20일 신고가 = MAX(high_price) over recent 20 rows."""
    # high_price 다양: 71500, 72000, 70000, 73000, 71000 → MAX = 73000
    mock_rows = [
        _db_row(high_price=71500, bas_dd="2026-06-12"),
        _db_row(high_price=72000, bas_dd="2026-06-11"),
        _db_row(high_price=70000, bas_dd="2026-06-10"),
        _db_row(high_price=73000, bas_dd="2026-06-09"),
        _db_row(high_price=71000, bas_dd="2026-06-08"),
    ]

    with patch(
        "src.db.stock_master_daily.get_recent_daily",
        new=AsyncMock(return_value=mock_rows),
    ):
        result = await stock_master_daily.get_donchian_high("005930", days=20)

    assert result == 73000


@pytest.mark.asyncio
async def test_g_db4_get_donchian_high_none_when_empty():
    """데이터 부재 시 None — 호출자 graceful."""
    with patch(
        "src.db.stock_master_daily.get_recent_daily",
        new=AsyncMock(return_value=[]),
    ):
        result = await stock_master_daily.get_donchian_high("005930", days=20)
    assert result is None


# ---------------------------------------------------------------------------
# G-DB5 (HIGH) — get_atr Wilder True Range
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_db5_get_atr_wilder_true_range():
    """ATR = mean(True Range) over last N days. TR = max(H-L, |H-prevC|, |L-prevC|)."""
    # 3일치 mock: prev_close=70000 → curr (high=72000, low=69500, close=71000)
    # TR1 = max(72000-69500=2500, |72000-70000|=2000, |69500-70000|=500) = 2500
    # 다음 날 prev_close=71000 → (high=71500, low=70500, close=71200)
    # TR2 = max(71500-70500=1000, |71500-71000|=500, |70500-71000|=500) = 1000
    # ATR = (2500 + 1000) / 2 = 1750
    mock_rows = [
        # DESC 정렬 (get_recent_daily 응답 형식)
        {"high_price": 71500, "low_price": 70500, "close_price": 71200},
        {"high_price": 72000, "low_price": 69500, "close_price": 71000},
        {"high_price": 70500, "low_price": 69800, "close_price": 70000},  # prev_close baseline
    ]

    with patch(
        "src.db.stock_master_daily.get_recent_daily",
        new=AsyncMock(return_value=mock_rows),
    ):
        result = await stock_master_daily.get_atr("005930", days=14)

    # ATR = (2500 + 1000) / 2 = 1750.0
    assert result == pytest.approx(1750.0, rel=0.01)


@pytest.mark.asyncio
async def test_g_db5_get_atr_none_when_insufficient_data():
    """rows < 2 → None (TR 계산 불가)."""
    with patch(
        "src.db.stock_master_daily.get_recent_daily",
        new=AsyncMock(return_value=[{"high_price": 71500, "low_price": 70500, "close_price": 71200}]),
    ):
        result = await stock_master_daily.get_atr("005930", days=14)
    assert result is None


# ---------------------------------------------------------------------------
# G-DB6 (MEDIUM) — get_recent_daily_with_fallback DB 우선 + KIS fallback
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_db6_fallback_prefers_db_when_sufficient():
    """DB 충분 시 KIS 호출 0건 (DB 결과 그대로 반환)."""
    db_rows = [_db_row(bas_dd=f"2026-06-{i:02d}") for i in range(28, 13, -1)]  # 15건

    with patch(
        "src.db.stock_master_daily.get_recent_daily",
        new=AsyncMock(return_value=db_rows),
    ), patch("src.api.condition.fetch_daily_candles", new=AsyncMock(return_value=[])) as mock_kis:
        result = await stock_master_daily.get_recent_daily_with_fallback(
            "005930", days=20, min_required=10,
        )

    assert len(result) == 15
    assert not mock_kis.called  # KIS fallback 호출 0


@pytest.mark.asyncio
async def test_g_db6_fallback_to_kis_when_db_insufficient():
    """DB 부족 시 KIS 호출 fallback (사이클 122 A5 영속)."""
    db_rows = [_db_row(bas_dd="2026-06-12")]  # 1건 (부족)
    kis_rows = [_kis_candle(bas_dd=f"2026061{i}") for i in range(2, 5)]  # 3건

    with patch(
        "src.db.stock_master_daily.get_recent_daily",
        new=AsyncMock(return_value=db_rows),
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=kis_rows),
    ) as mock_kis:
        result = await stock_master_daily.get_recent_daily_with_fallback(
            "005930", days=20, min_required=10,
        )

    assert mock_kis.called  # KIS fallback 호출됨
    assert result == kis_rows  # KIS 응답 그대로 반환


# ---------------------------------------------------------------------------
# G-DB7 (MEDIUM) — count_all / count_by_ticker / max_bas_dd 진단 영역
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_db7_count_all_uses_supabase_count_exact():
    """count_all — count(*) 정확 카운트 (사이클 M2b — pg.fetchval)."""
    with patch.object(stock_master_daily, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=270000)
        result = await stock_master_daily.count_all()

    assert result == 270000
    sql = pg_mod.fetchval.await_args.args[0].lower()
    assert "count(" in sql and "stock_master_daily" in sql, "count(*) SELECT 누락"


@pytest.mark.asyncio
async def test_g_db7_max_bas_dd_returns_date_or_none():
    """max_bas_dd — 점진 적재 시 신규 행 영역 결정 (사이클 M2b — pg.fetchval MAX)."""
    with patch.object(stock_master_daily, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value="2026-06-12")
        result = await stock_master_daily.max_bas_dd("005930")

    assert result == date(2026, 6, 12)
    sql = pg_mod.fetchval.await_args.args[0].lower()
    assert "max(bas_dd)" in sql, "MAX(bas_dd) SELECT 누락"
    assert "005930" in pg_mod.fetchval.await_args.args[1:], "ticker 지정 분기 바인딩 누락"


@pytest.mark.asyncio
async def test_g_db7_max_bas_dd_returns_none_when_missing():
    """ticker 부재 시 None 반환 (백필 의무 신호)."""
    with patch.object(stock_master_daily, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=None)
        result = await stock_master_daily.max_bas_dd("005930")

    assert result is None
