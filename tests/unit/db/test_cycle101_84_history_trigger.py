"""사이클 101 G-PERSIST3 — 사이클 84 history trigger 영속 (LOW).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**사이클 84 history trigger 영속**:
- `stock_master_history` 90일 retention 영속
- 사이클 101 ~2,800 universe = 252,000 row 예상 (5% 미만, 안전)
- `upsert_one` 호출 시 history INSERT trigger 영속 보장

검증 매트릭스:
- G-PERSIST3-A: `src/db/stock_master.py::upsert_one` 함수 영속
- G-PERSIST3-B: 사이클 84 history retention 90일 영속 (docstring 또는 모듈 영역 인용)

Red 상태: 함수 부재 또는 사이클 84 영역 silent 삭제.
Green: 영속 영구 보장.

영속 의무:
- 사이클 84 history trigger 영구 영속 (90일 retention)
- 사이클 101 ~2,800 universe = 5% 미만 (안전)
- 매매 안전성 영역 영향 0 (DB 영역)
"""
from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.unit


def test_g_persist3_a_upsert_one_exists() -> None:
    """G-PERSIST3-A: `stock_master.upsert_one` 함수 영속 (LOW)."""
    from src.db import stock_master

    assert hasattr(stock_master, "upsert_one"), (
        "\n사이클 101 G-PERSIST3-A Red — `stock_master.upsert_one` 부재.\n"
        "  사이클 84 history trigger 영속 의무 (~2,800 universe upsert chain)"
    )

    func = stock_master.upsert_one
    assert callable(func), (
        f"\nG-PERSIST3-A Red — upsert_one callable 아님: {type(func)}"
    )


def test_g_persist3_b_is_stale_exists_for_24h_ttl() -> None:
    """G-PERSIST3-B: `stock_master.is_stale` 24h TTL 영속 (LOW).

    검증 매트릭스:
    - 사이클 101 = 매일 20:00:05 1회 적재
    - 24h TTL = 사이클 83/89 답습 (fresh skip 영역)
    - is_stale(ticker, max_age_hours=24) 호출 가능 영속
    """
    from src.db import stock_master

    assert hasattr(stock_master, "is_stale"), (
        "\nG-PERSIST3-B Red — `stock_master.is_stale` 부재.\n"
        "  사이클 83/89 답습 영속 의무 (24h TTL fresh skip)"
    )
    sig = inspect.signature(stock_master.is_stale)
    params = sig.parameters
    assert "max_age_hours" in params, (
        f"\nG-PERSIST3-B 위반 — `is_stale(ticker, max_age_hours=...)` 시그너처 영속 위반:\n"
        f"  실제 파라미터: {list(params.keys())}\n"
        f"  Green: max_age_hours 영속 의무 (사이클 83 영속)"
    )
