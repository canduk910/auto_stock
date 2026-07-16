"""사이클 65 (2026-06-06) Red — A 카테고리: `src/db/system_config.py` 거래대금 필터 (3 케이스).

> **선행 명세**: `_workspace/red/cycle65_trade_amount_filter.md` (§File 1)
> **설계 카드 v2**: `_workspace/cycle65_trade_amount_filter_design_card.md` §1
> **자문 응답**: Q1 디폴트 0 (비활성) 확정
> **선례**: 사이클 64 A 4 케이스 (PriceFilter) → 단일 키 단순화로 3 케이스

요구 행위 (Red 단계 모두 ImportError / AttributeError / AssertionError 정답):

- A-1: `get_trade_amount_filter()` 디폴트 — `min_amount=0` + `is_active=False`
- A-2: `set_trade_amount_filter(min_amount=100_000_000)` 갱신 + 재조회 일치
- A-3: `set_trade_amount_filter(min_amount=-1)` → ValueError

위험 등급 LOW. 회귀 가드 — DB 단일 키 정합성.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# A-1: 디폴트 — min_amount=0 + is_active=False
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_A1_get_trade_amount_filter_default(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    """A-1: 미설정 시 TradeAmountFilter(min_amount=0) + is_active=False 반환.

    사이클 65 — Q1 자문 옵션 A 디폴트 0 (비활성) 확정.
    Red 단계 — `TradeAmountFilter` / `get_trade_amount_filter` 미존재 → ImportError 정답.
    """
    from src.db import system_config
    from src.db.system_config import TradeAmountFilter, get_trade_amount_filter

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)
    taf = await get_trade_amount_filter()

    assert isinstance(taf, TradeAmountFilter)
    assert taf.min_amount == 0
    assert taf.is_active is False, (
        "Q1 자문 디폴트 0 (비활성) 위반 — is_active False 의무"
    )


# ---------------------------------------------------------------------------
# A-2: set → get 일치 (양수 정상)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_A2_set_then_get_trade_amount_filter(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    """A-2: `set_trade_amount_filter(min_amount=100_000_000)` 갱신 + 재조회 일치 + is_active=True.

    1억 = Q1 자문 권장값 마커 최저 단위 (1억/5억/10억).
    """
    from src.db import system_config
    from src.db.system_config import (
        get_trade_amount_filter,
        set_trade_amount_filter,
    )

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)

    await set_trade_amount_filter(min_amount=100_000_000)
    taf = await get_trade_amount_filter()
    assert taf.min_amount == 100_000_000
    assert taf.is_active is True, (
        "min_amount > 0 이면 is_active=True 의무 (Q1 자문)"
    )

    # 갱신 — 5억으로 변경
    await set_trade_amount_filter(min_amount=500_000_000)
    taf2 = await get_trade_amount_filter()
    assert taf2.min_amount == 500_000_000


# ---------------------------------------------------------------------------
# A-3: 음수 입력 → ValueError
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_A3_set_trade_amount_filter_negative_raises(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    """A-3: `set_trade_amount_filter(min_amount=-1)` → ValueError.

    음수는 의미 없는 입력 — 양수 검증 보존 (사이클 64 set_price_filter 패턴 답습).
    """
    from src.db import system_config
    from src.db.system_config import set_trade_amount_filter

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)

    with pytest.raises(ValueError):
        await set_trade_amount_filter(min_amount=-1)

    with pytest.raises(ValueError):
        await set_trade_amount_filter(min_amount=-100_000_000)
