"""사이클 M2a (Red) — system_config / trade_history 실 Postgres 왕복 검증 (매매 hot path).

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 2 — 매매 hot path, HIGH).

mock 단위 테스트로 못 잡는 **실 SQL · JSONB codec · TIMESTAMPTZ +09:00 경계 · NUMERIC→Decimal ·
count+range 페이징 · sync dedupe/CANCELLED** 안전망. docker/DATABASE_URL_TEST 없으면
pg_harness fixture 가 pytest.skip.

⚠️ 핵심 (계획 3대 리스크):
1. **JSONB codec** — system_config `{"value": x}` 왕복이 dict 로 복원 →
   `isinstance(raw, dict)` True → 실제 값 (미작동 시 default 폴백 = 매매 파라미터 silent 오작동).
2. **TIMESTAMPTZ +09:00 경계 (사이클 53 B-4)** — KST 08:00 (UTC 전날 23:00) 거래가 당일
   `get_trades_in_range` 범위에 **포함**되는지 (TZ 누락 시 UTC 해석 → 누락). 읽기 str 계약.
3. **NUMERIC→Decimal** — trade_history price/profit_loss.

Red 유효성: production(2 모듈) 이 아직 pg 미사용 → 실 PG 왕복 경로 없음 → 전부 FAIL/에러.
"""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


# ===========================================================================
# system_config — ⚠️ JSONB {"value": x} codec 왕복 (계획 최대 위험 1순위)
# ===========================================================================
@pytest.mark.asyncio
async def test_cash_usage_ratio_jsonb_roundtrip_returns_float(clean_system_config):
    """⚠️ set 0.35 → get 0.35 (JSONB {"value": x} codec → dict → float).

    codec 미작동 시 get 이 default 1.0 폴백 → 이 단언 FAIL = 매매 파라미터 silent 오작동 가드.
    """
    from src.db import system_config

    await system_config.set_cash_usage_ratio(0.35)
    got = await system_config.get_cash_usage_ratio()

    assert abs(got - 0.35) < 1e-9, (
        "JSONB {\"value\": x} 왕복 = 0.35. 1.0 이면 codec 미작동 silent 폴백 (매매 파라미터 오작동)."
    )
    assert isinstance(got, float)


@pytest.mark.asyncio
async def test_buy_block_mode_jsonb_roundtrip_str(clean_system_config):
    """set 'SOFT' → get 'SOFT' (JSONB str codec 왕복)."""
    from src.db import system_config

    await system_config.set_buy_block_mode("SOFT")
    got = await system_config.get_buy_block_mode()

    assert got == "SOFT", "JSONB str 왕복 (매수 가드 모드 계약)."


@pytest.mark.asyncio
async def test_auto_regime_adjust_jsonb_bool_roundtrip(clean_system_config):
    """set False → get False (JSONB bool codec 왕복)."""
    from src.db import system_config

    await system_config.set_auto_regime_adjust(False)
    got = await system_config.get_auto_regime_adjust()

    assert got is False, "JSONB bool 왕복."


@pytest.mark.asyncio
async def test_buy_block_thresholds_float_roundtrip(clean_system_config):
    """set_buy_block_thresholds 부분 갱신 → get 4임계 왕복 (float JSONB)."""
    from src.db import system_config

    await system_config.set_buy_block_thresholds(vix_threshold=30.0, fg_low_threshold=10.0)
    th = await system_config.get_buy_block_thresholds()

    assert abs(th.vix_threshold - 30.0) < 1e-9, "vix 임계 JSONB float 왕복."
    assert abs(th.fg_low_threshold - 10.0) < 1e-9, "fg_low 임계 JSONB float 왕복."
    # 미지정 키는 기본값 보존
    assert abs(th.fg_high_threshold - 85.0) < 1e-9, "미지정 fg_high 기본 85.0 보존."


@pytest.mark.asyncio
async def test_system_config_upsert_key_single_row(clean_system_config):
    """동일 key 2회 set → ON CONFLICT (key) 1행 갱신 (중복 없음)."""
    from src.db import system_config
    import src.db.pg as pg

    await system_config.set_cash_usage_ratio(0.5)
    await system_config.set_cash_usage_ratio(0.75)

    cnt = await pg.fetchval(
        "SELECT count(*) FROM system_config WHERE key = $1", "cash_usage_ratio"
    )
    assert cnt == 1, "key PK upsert → 1행."
    assert abs(await system_config.get_cash_usage_ratio() - 0.75) < 1e-9, "최신 값 반영."


@pytest.mark.asyncio
async def test_string_key_none_when_missing(clean_system_config):
    """키 부재 → _get_string_or_none None (호출자 fallback 계약)."""
    from src.db import system_config

    got = await system_config._get_string_or_none("krx_open_api_key")
    assert got is None, "키 부재 → None."


# ===========================================================================
# trade_history — ⚠️ TIMESTAMPTZ +09:00 경계 (사이클 53 B-4) + Decimal
# ===========================================================================
@pytest.mark.asyncio
async def test_trades_in_range_includes_kst_early_morning(clean_trade_history):
    """⚠️ KST 08:00 (UTC 전날 23:00) 거래가 당일 get_trades_in_range 범위에 포함.

    사이클 53 B-4: TZ 명시 없으면 UTC 해석 → KST 00:00~09:00 거래가 전날로 밀려 누락.
    +09:00 경계 바인딩 실증 (start "{d}T00:00:00+09:00").
    """
    import src.db.pg as pg
    from src.db import trade_history

    # KST 08:00 매수 (UTC 로는 전날 23:00)
    await pg.execute(
        """
        INSERT INTO trade_history (timestamp, ticker, ticker_name, trade_type, price,
                                   quantity, profit_loss, status, strategy, order_no)
        VALUES ($1, $2, $3, 'BUY', $4, $5, 0, 'COMPLETED', 'momentum', $6)
        """,
        __import__("datetime").datetime.fromisoformat("2026-07-16T08:00:00+09:00"),
        "005930", "삼성전자", 70000.0, 10, "BUY-1",
    )

    rows = await trade_history.get_trades_in_range(date(2026, 7, 16), date(2026, 7, 16))

    assert len(rows) == 1, (
        "KST 08:00 거래가 당일 범위에 포함 (사이클 53 B-4 +09:00 경계). "
        "0건이면 UTC 해석으로 전날 밀림 = 결함 재현."
    )
    # 읽기 str 계약 — _to_kst 가 파싱 가능한 str
    d, t = trade_history._to_kst(rows[0]["timestamp"])
    assert d == "2026-07-16" and t == "08:00:00", "timestamp 읽기 str +09:00 → KST 파싱 계약."


@pytest.mark.asyncio
async def test_insert_trade_and_pairs_decimal(clean_trade_history):
    """insert_trade 왕복 → get_trade_pairs Decimal 페어링 (매수/매도 closed)."""
    from src.db import trade_history
    from src.models.trade import TradeRecord, TradeStatus, TradeType

    await trade_history.insert_trade(TradeRecord(
        ticker="005930", ticker_name="삼성전자", trade_type=TradeType.BUY,
        price=70000, quantity=10, profit_loss=0, status=TradeStatus.COMPLETED,
        strategy="momentum", order_no="B-1",
    ))
    await trade_history.insert_trade(TradeRecord(
        ticker="005930", ticker_name="삼성전자", trade_type=TradeType.SELL,
        price=72000, quantity=10, profit_loss=20000, status=TradeStatus.COMPLETED,
        strategy="momentum", order_no="S-1",
    ))

    pairs = await trade_history.get_trade_pairs(ticker="005930")
    assert len(pairs) == 1, "매수 10 + 매도 10 → closed 페어 1건."
    pair = pairs[0]
    assert pair["status"] == "closed"
    assert abs(pair["profit_loss"] - 20000.0) < 1e-6, "Decimal 가중평균 손익 (20,000)."
    assert abs(pair["buy_price"] - 70000.0) < 1e-6
    assert abs(pair["sell_price"] - 72000.0) < 1e-6


@pytest.mark.asyncio
async def test_get_trades_count_range_pagination_roundtrip(clean_trade_history):
    """get_trades count + range 페이징 — 총건수 정확 + 페이지 데이터."""
    from src.db import trade_history
    from src.models.trade import TradeRecord, TradeStatus, TradeType

    for i in range(5):
        await trade_history.insert_trade(TradeRecord(
            ticker=f"00{i}000", ticker_name=f"종목{i}", trade_type=TradeType.BUY,
            price=1000 + i, quantity=1, profit_loss=0, status=TradeStatus.COMPLETED,
            strategy="momentum", order_no=f"B-{i}",
        ))

    page1, total = await trade_history.get_trades(limit=2, offset=0)
    assert total == 5, "count(*) 총건수 정확 (PostgREST 1000 cap 무관, asyncpg count)."
    assert len(page1) == 2, "range → LIMIT 2."

    page3, total3 = await trade_history.get_trades(limit=2, offset=4)
    assert total3 == 5
    assert len(page3) == 1, "마지막 페이지 offset=4 → 1건."


@pytest.mark.asyncio
async def test_update_trade_status_affected_roundtrip(clean_trade_history):
    """insert PENDING → update COMPLETED → affected=1 (체결통보 race 계약)."""
    from src.db import trade_history
    from src.models.trade import TradeRecord, TradeStatus, TradeType

    await trade_history.insert_trade(TradeRecord(
        ticker="005930", ticker_name="삼성전자", trade_type=TradeType.BUY,
        price=70000, quantity=10, profit_loss=0, status=TradeStatus.PENDING,
        strategy="momentum", order_no="B-1",
    ))
    affected = await trade_history.update_trade_status(
        "005930", TradeType.BUY, TradeStatus.COMPLETED, strategy="momentum", price=70050,
    )
    assert affected == 1, "PENDING → COMPLETED affected=1 ('UPDATE 1' 파싱)."

    # 재호출 → 0건 (이미 COMPLETED, PENDING 없음)
    again = await trade_history.update_trade_status(
        "005930", TradeType.BUY, TradeStatus.COMPLETED, strategy="momentum",
    )
    assert again == 0, "PENDING 소진 → affected=0 (보정 INSERT 트리거 계약)."


@pytest.mark.asyncio
async def test_update_trade_status_match_partial_roundtrip(clean_trade_history):
    """cycle273a — `match_partial=True` 를 **실 asyncpg** 로 왕복시킨다(검증 r2 HIGH#3).

    PARTIAL 행 INSERT → COMPLETED UPDATE(match_partial=True) → affected=1. KST 당일 하한이
    TIMESTAMPTZ 에 datetime 으로 바인딩돼야 한다 — str 이면 DataError(사이클 M6 계열).
    """
    from src.db import trade_history
    from src.models.trade import TradeRecord, TradeStatus, TradeType

    await trade_history.insert_trade(TradeRecord(
        ticker="005930", ticker_name="삼성전자", trade_type=TradeType.BUY,
        price=70000, quantity=10, profit_loss=0, status=TradeStatus.PARTIAL,
        strategy="momentum", order_no="B-2",
    ))
    affected = await trade_history.update_trade_status(
        "005930", TradeType.BUY, TradeStatus.COMPLETED, strategy="momentum", price=70050,
        match_partial=True,
    )
    assert affected == 1, "PARTIAL 행이 match_partial=True 로 COMPLETED 돼야 한다(실 PG 왕복)."
    rows = await trade_history.get_today_buy_trades_for_sync()
    mine = [r for r in rows if r.get("order_no") == "B-2"]
    assert mine and mine[0]["status"] == TradeStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_sync_no_dedupe_excludes_cancelled_roundtrip(clean_trade_history):
    """sync 함수 왕복 — 같은 ticker 다른 order_no 전부 보존 + CANCELLED 제외 (사이클 30/73)."""
    from src.db import trade_history
    from src.models.trade import TradeRecord, TradeStatus, TradeType

    # 같은 ticker 다른 order_no 2건 + CANCELLED 1건
    for order_no, status in (
        ("A-1", TradeStatus.COMPLETED),
        ("A-2", TradeStatus.COMPLETED),
        ("A-3", TradeStatus.CANCELLED),
    ):
        await trade_history.insert_trade(TradeRecord(
            ticker="042700", ticker_name="한미반도체", trade_type=TradeType.BUY,
            price=100000, quantity=1, profit_loss=0, status=status,
            strategy="momentum", order_no=order_no,
        ))

    rows = await trade_history.get_today_buy_trades_for_sync(ticker="042700")
    order_nos = {r["order_no"] for r in rows}
    assert order_nos == {"A-1", "A-2"}, (
        "sync 는 dedupe 없음 (A-1/A-2 보존) + CANCELLED(A-3) 제외 (042700 핑퐁 사고 차단)."
    )

    # 포지션 복구용은 dedupe (최신 1건)
    recovery = await trade_history.get_today_buy_trades()
    assert len([r for r in recovery if r["ticker"] == "042700"]) == 1, (
        "포지션 복구용은 ticker dedupe — sync 와 구분."
    )
