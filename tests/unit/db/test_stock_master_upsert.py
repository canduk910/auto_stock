"""Phase G2 (2026-05-13) — `stock_master.upsert_one` 방어적 ticker 정규화.

결함 진단:
- 운영 DB stock_master.ticker = `00000A000100` (KIS pdno 12자리)
- positions.ticker = `000100` (KRX 6자리)
- `get(ticker="000100")` 항상 miss → Phase G 사전 차단 무력화 (어제·오늘 운영 중)

이중 안전망: `inquire_stock_basics` 정규화 외에 `upsert_one` 자체도
6자리 보장 가드. 호출자가 마이그레이션/수동 보강 경로로 12자리를 넣어도 안전.

요구 행위:
1. 12자리 KIS pdno 형식이 들어오면 `_normalize_ticker` 로 6자리 변환 + WARNING 로그.
2. 정상 6자리 입력은 그대로 통과 (변환 로직 발화 안 함).
"""

from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.unit


def _basics(
    ticker: str,
    *,
    name: str = "테스트종목",
    nxt_tradable: bool = True,
    krx_halted: bool = False,
    admin_item: bool = False,
    excg: str = "02",
):
    from src.models.stock import StockBasics

    return StockBasics(
        ticker=ticker,
        name=name,
        excg_dvsn_cd=excg,
        nxt_tradable=nxt_tradable,
        krx_halted=krx_halted,
        admin_item=admin_item,
        raw={"pdno": ticker},
    )


@pytest.mark.asyncio
async def test_upsert_one_normalizes_12char_ticker(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_stock_master,
    caplog: pytest.LogCaptureFixture,
):
    """12자리 KIS pdno → 6자리 정규화 후 upsert (이중 안전망)."""
    from src.db import stock_master

    monkeypatch.setattr(stock_master, "pg", fake_pg_stock_master)

    with caplog.at_level(logging.WARNING, logger="src.db.stock_master"):
        await stock_master.upsert_one(_basics("00000A000100", nxt_tradable=True))

    # 저장된 row 의 ticker 가 6자리로 정규화됐는지 검증
    rows = list(fake_pg_stock_master.store.values())
    assert len(rows) == 1
    assert rows[0]["ticker"] == "000100"
    # get() 도 6자리 키로 hit
    loaded = await stock_master.get("000100")
    assert loaded is not None
    assert loaded.ticker == "000100"
    assert loaded.nxt_tradable is True
    # WARNING 로그 — 정규화 발화 흔적 (운영 디버깅용)
    assert any(
        "정규화" in record.message or "normaliz" in record.message.lower()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_upsert_one_preserves_6digit_ticker(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_stock_master,
    caplog: pytest.LogCaptureFixture,
):
    """정상 6자리 입력은 정규화 가드 발화 안 함 (변환 0회)."""
    from src.db import stock_master

    monkeypatch.setattr(stock_master, "pg", fake_pg_stock_master)

    with caplog.at_level(logging.WARNING, logger="src.db.stock_master"):
        await stock_master.upsert_one(_basics("000100"))

    rows = list(fake_pg_stock_master.store.values())
    assert len(rows) == 1
    assert rows[0]["ticker"] == "000100"
    # WARNING 로그 없음 — 정상 경로는 silent
    normalize_warnings = [
        r for r in caplog.records if "정규화" in r.message
    ]
    assert normalize_warnings == []
