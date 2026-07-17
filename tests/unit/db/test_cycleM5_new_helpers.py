"""사이클 M5 (Red) — 신규 db 헬퍼 계약 가드 (누락 사이트 전환 지원).

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (Supabase→RDS 이전, 누락 사이트).

M5 = src/db/ 밖 4파일의 직접 supabase.table() 호출을 pg/db함수로 전환. 이를 위해 신규 4 헬퍼:
- `system_config.set_auto_start(enabled)` — routes/strategies.py auto_start 쓰기 대상 (M3b get_auto_start 대칭).
- `trade_history.mark_pending_buys_completed(ticker)` — scheduler/boot_manager PENDING BUY→COMPLETED 일괄.
- `trade_history.get_recent_buy_strategy(ticker)` — scheduler/boot_manager 최근 BUY strategy 조회.
- `trade_history.get_today_buys_ticker_strategy()` — boot_manager 오늘 BUY (ticker, strategy) 조회.

Red 유효성: production 신규 헬퍼 부재 → AttributeError FAIL.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

from src.models.trade import TradeStatus, TradeType


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


def _args_for(pg_mod, name: str) -> tuple:
    m = getattr(pg_mod, name, None)
    if m is not None and getattr(m, "await_args", None) is not None:
        return m.await_args.args
    return ()


# ---------------------------------------------------------------------------
# system_config.set_auto_start — auto_start 쓰기 헬퍼 신규 (M3b get_auto_start 대칭)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_set_auto_start_symbol_exists():
    """set_auto_start 심볼 존재 (routes.strategies.py upsert 대체)."""
    from src.db import system_config as sc

    assert hasattr(sc, "set_auto_start"), (
        "system_config.set_auto_start 신규 헬퍼 필요 — routes/strategies.py 의 "
        "supabase.table('system_config').upsert(auto_start) 전환 대상."
    )


@pytest.mark.asyncio
async def test_set_auto_start_upserts_jsonb_value_true():
    """set_auto_start(True) → _upsert_value(auto_start, {"value": True}) — JSONB {"value": bool} 계약."""
    from src.db import system_config as sc

    with patch.object(sc, "_upsert_value", new=AsyncMock()) as up:
        await sc.set_auto_start(True)

    up.assert_awaited_once()
    key = up.await_args.args[0]
    payload = up.await_args.args[1]
    assert key == sc._AUTO_START_KEY == "auto_start", "키는 auto_start."
    assert isinstance(payload, dict) and payload.get("value") is True, (
        "JSONB {\"value\": bool} 형태 (get_auto_start dict.value 파싱 계약 정합)."
    )


@pytest.mark.asyncio
async def test_set_auto_start_coerces_to_bool():
    """set_auto_start 값은 bool 강제 (set_auto_regime_adjust 패턴 답습)."""
    from src.db import system_config as sc

    with patch.object(sc, "_upsert_value", new=AsyncMock()) as up:
        await sc.set_auto_start(False)

    payload = up.await_args.args[1]
    assert payload.get("value") is False, "False upsert 계약."
    assert isinstance(payload.get("value"), bool), "bool 강제 변환."


@pytest.mark.asyncio
async def test_auto_start_roundtrip_get_after_set():
    """왕복: set_auto_start 가 upsert 한 payload 를 get_auto_start 가 True 로 해석 (split-brain 해소 핵심)."""
    from src.db import system_config as sc

    captured: dict = {}

    async def _fake_upsert(key, value):
        captured["value"] = value

    async def _fake_select(key):
        return captured.get("value", sc._MISSING)

    with patch.object(sc, "_upsert_value", new=_fake_upsert), \
         patch.object(sc, "_select_value", new=_fake_select):
        await sc.set_auto_start(True)
        got = await sc.get_auto_start()

    assert got is True, "set(True) → get() == True (routes/scheduler 동일 소스 = split-brain 해소)."


# ---------------------------------------------------------------------------
# trade_history.mark_pending_buys_completed — PENDING BUY → COMPLETED 일괄
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mark_pending_buys_completed_symbol_exists():
    from src.db import trade_history as th

    assert hasattr(th, "mark_pending_buys_completed"), (
        "trade_history.mark_pending_buys_completed 신규 필요 — scheduler/boot_manager 의 "
        "supabase.table('trade_history').update(status=COMPLETED).eq(...) 공통 전환 대상."
    )


@pytest.mark.asyncio
async def test_mark_pending_buys_completed_uses_pg_update():
    """mark_pending_buys_completed(ticker) → pg.execute UPDATE (ticker + BUY + PENDING → COMPLETED)."""
    from src.db import trade_history as th

    with patch.object(th, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="UPDATE 1")
        await th.mark_pending_buys_completed("005930")

    sql = _args_for(pg_mod, "execute")[0]
    up = sql.upper()
    assert "UPDATE TRADE_HISTORY" in up, "UPDATE trade_history 누락."
    assert "SET STATUS" in up, "status 갱신 누락."
    # 바인딩: ticker + status 필터
    bind = _args_for(pg_mod, "execute")[1:]
    assert "005930" in bind, "ticker 바인딩 누락."
    assert TradeStatus.COMPLETED.value in bind, "COMPLETED 타깃 status 누락."
    assert TradeType.BUY.value in bind, "BUY trade_type 필터 누락."
    assert TradeStatus.PENDING.value in bind, "PENDING 원본 status 필터 누락 (전량 갱신 방지)."


@pytest.mark.asyncio
async def test_mark_pending_buys_completed_graceful_on_pg_exception():
    """mark_pending_buys_completed — pg.execute 실패 시 예외 미전파 (graceful, 기존 except pass 계약)."""
    from src.db import trade_history as th

    with patch.object(th, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(side_effect=RuntimeError("db down"))
        # 예외가 전파되면 boot/sync hot path 붕괴 → 반드시 흡수
        await th.mark_pending_buys_completed("005930")


# ---------------------------------------------------------------------------
# trade_history.get_recent_buy_strategy — 최근 BUY strategy 조회 (order_no 무관)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_recent_buy_strategy_symbol_exists():
    from src.db import trade_history as th

    assert hasattr(th, "get_recent_buy_strategy"), (
        "trade_history.get_recent_buy_strategy 신규 필요 — scheduler/boot_manager 의 "
        "select(strategy).eq(ticker).eq(BUY).order(timestamp desc).limit(1) 전환 대상."
    )


@pytest.mark.asyncio
async def test_get_recent_buy_strategy_uses_pg_fetch_order_desc_limit1():
    """get_recent_buy_strategy(ticker) → pg.fetch SELECT strategy ... BUY ORDER timestamp DESC LIMIT 1."""
    from src.db import trade_history as th

    with patch.object(th, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"strategy": "volatility_breakout"}])
        out = await th.get_recent_buy_strategy("005930")

    assert out == "volatility_breakout", "최근 BUY row 의 strategy 반환."
    sql = _args_for(pg_mod, "fetch")[0]
    up = sql.upper()
    assert "SELECT STRATEGY" in up, "strategy 컬럼 SELECT 누락."
    assert "TRADE_HISTORY" in up, "trade_history 테이블 누락."
    assert "ORDER BY" in up and "DESC" in up, "timestamp DESC 정렬 누락 (최근 1건)."
    assert "LIMIT 1" in up, "LIMIT 1 누락."
    bind = _args_for(pg_mod, "fetch")[1:]
    assert "005930" in bind, "ticker 바인딩 누락."
    assert TradeType.BUY.value in bind, "BUY trade_type 필터 누락."


@pytest.mark.asyncio
async def test_get_recent_buy_strategy_none_when_no_row():
    """조회 0건 → None (graceful, 호출자 'momentum' 폴백)."""
    from src.db import trade_history as th

    with patch.object(th, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await th.get_recent_buy_strategy("999999")

    assert out is None, "0건 → None 계약."


@pytest.mark.asyncio
async def test_get_recent_buy_strategy_graceful_on_exception():
    """pg.fetch 실패 → None (예외 미전파, 기존 except pass 계약)."""
    from src.db import trade_history as th

    with patch.object(th, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=RuntimeError("db down"))
        out = await th.get_recent_buy_strategy("005930")

    assert out is None, "예외 → None graceful."


# ---------------------------------------------------------------------------
# trade_history.get_today_buys_ticker_strategy — 오늘 BUY (ticker, strategy) + KST 계약
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_today_buys_ticker_strategy_symbol_exists():
    from src.db import trade_history as th

    assert hasattr(th, "get_today_buys_ticker_strategy"), (
        "trade_history.get_today_buys_ticker_strategy 신규 필요 — boot_manager 의 "
        "select(ticker, strategy).eq(BUY).gte(timestamp, today) 전환 대상."
    )


@pytest.mark.asyncio
async def test_get_today_buys_ticker_strategy_uses_pg_fetch_kst_bind():
    """get_today_buys_ticker_strategy() → pg.fetch SELECT ticker,strategy ... BUY gte 오늘 KST(+09:00)."""
    from src.db import trade_history as th

    with patch.object(th, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[
            {"ticker": "005930", "strategy": "momentum"},
        ])
        out = await th.get_today_buys_ticker_strategy()

    assert out == [{"ticker": "005930", "strategy": "momentum"}], "row list 반환 계약."
    sql = _args_for(pg_mod, "fetch")[0]
    up = sql.upper()
    assert "TRADE_HISTORY" in up, "trade_history 테이블 누락."
    assert "TICKER" in up and "STRATEGY" in up, "ticker/strategy 컬럼 SELECT 누락."
    assert ">=" in sql or "GTE" in up, "오늘 timestamp gte 필터 누락."
    bind = _args_for(pg_mod, "fetch")[1:]
    # ⚠️ +09:00 KST 계약 (사이클 53 B-4) — TZ-naive 바인딩 금지
    def _is_kst(a) -> bool:
        if isinstance(a, str):
            return "+09:00" in a
        return isinstance(a, datetime) and a.tzinfo is not None
    assert any(_is_kst(a) for a in bind), (
        "오늘 시작 시각 바인딩은 +09:00 KST 명시 필수 (사이클 53 — TZ-naive 시 KST 00:00~09:00 BUY 누락)."
    )
    assert TradeType.BUY.value in bind, "BUY trade_type 필터 누락."


@pytest.mark.asyncio
async def test_get_today_buys_ticker_strategy_graceful_on_exception():
    """pg.fetch 실패 → 빈 리스트 (예외 미전파, 호출자 boot 루프 보호)."""
    from src.db import trade_history as th

    with patch.object(th, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=RuntimeError("db down"))
        out = await th.get_today_buys_ticker_strategy()

    assert out == [], "예외 → 빈 리스트 graceful."
