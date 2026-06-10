"""사이클 95 H-2 — 500 ticker 누적 영속 + chicken-and-egg lock-in 차단 (HIGH).

명세 (`_workspace/red/cycle95_chicken_and_egg_fix_ui.md`):

- 운영 실측: 사이클 94 영역 3 시정 후에도 universe 78 ticker 영속 lock-in
- 시정 후: 500 ticker 응답 + stock_master 부재 422건 = universe 500 영속 (cap)
- 사이클 89 KOSPI 250 + KOSDAQ 250 = 500 영속 + 사이클 95 unknown 합산

Red 상태: production 코드 = None continue → universe = KOSPI N + KOSDAQ M (≤ 500 영역).
운영 실측 시점 stock_master 적재 영역 78건 → universe 78 → FAIL (500 ≠ 78).

Green: KOSPI[:250] + KOSDAQ[:250] + unknown[:max(0, 500 - kospi - kosdaq)] → universe 500 → PASS.

영속 의무:
- 사이클 89 KOSPI 250 + KOSDAQ 250 = 500 cap 영속
- 사이클 94 영역 1/2 (`"0000"` + `_fetch_volume_rank(market="all", top_n=500)`) 영속
- 매매 안전성 영향 0 (scanner 단계 = 매수 진입 *전*)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_volume_rank_row(ticker: str) -> dict:
    return {
        "mksc_shrn_iscd": ticker,
        "prdy_vol": "1000000",
        "stck_prpr": "50000",
        "prdy_vrss": "1000",
        "prdy_ctrt": "2.04",
    }


def _make_stock_basics(ticker: str, excg_dvsn_cd: str):
    from src.models.stock import StockBasics

    return StockBasics(
        ticker=ticker,
        name=f"종목{ticker}",
        excg_dvsn_cd=excg_dvsn_cd,
        raw={"mksc_shrn_iscd": ticker, "excg_dvsn_cd": excg_dvsn_cd, "bfdy_clpr": "50000"},
    )


@pytest.mark.asyncio
async def test_h2_universe_500_break_lock_in():
    """H-2.a: 500 ticker 응답 + stock_master 78건만 적재 → universe 500 (lock-in 차단).

    검증 매트릭스 (운영 실측 재현):
    - volume_rank 응답 500건
    - stock_master 적재 78건 (KOSPI 50 + KOSDAQ 28)
    - 부재 422건 → 사이클 95 unknown 합집합 영역
    - 합산: KOSPI 50 + KOSDAQ 28 + unknown 422 = 500

    Red (사이클 95): production 코드 = None continue → universe 78 → FAIL (500 ≠ 78).

    Green: unknown 합집합 → universe 500 → PASS.
    """
    from src.engine import scanner

    # 500 raw rows
    raw_rows = [_make_volume_rank_row(f"{i:06d}") for i in range(500)]

    # 78건만 stock_master 적재 (운영 실측 재현)
    sm_map = {}
    for i in range(50):
        sm_map[f"{i:06d}"] = _make_stock_basics(f"{i:06d}", "02")  # KOSPI 50
    for i in range(50, 78):
        sm_map[f"{i:06d}"] = _make_stock_basics(f"{i:06d}", "03")  # KOSDAQ 28
    # 78~499 = 부재 422건 (사이클 95 unknown 합집합)

    async def fake_get(ticker: str):
        return sm_map.get(ticker)

    with patch.object(scanner, "_fetch_volume_rank", new=AsyncMock(return_value=raw_rows)), \
         patch("src.db.stock_master.get", side_effect=fake_get):
        universe = await scanner.fetch_top_500_universe()

    assert len(universe) == 500, (
        f"\n사이클 95 H-2.a 위반 — chicken-and-egg lock-in 운영 실측 재현:\n"
        f"  시나리오: stock_master 적재 78건 (사이클 94 영역 3 결함 영속)\n"
        f"  기대: universe = 500 (KOSPI 50 + KOSDAQ 28 + unknown 422)\n"
        f"  실제: universe = {len(universe)}\n"
        f"  결함 인과: None 자연 skip → 78 ticker 영구 lock-in\n"
        f"  시정: unknown 합집합 → 첫 호출에서 422 ticker upsert chain trigger\n"
        f"  다음 사이클부터 KOSPI/KOSDAQ 정확 분류 자연 회복"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 96 Q50=D — 사이클 94 post-split chain 폐기 계약. "
        "사이클 96 영역 복원 = 2회 분리 호출 (각 top_n=250 ceiling 독립 적용). "
        "사이클 95 post-split 결과 cap 가정 = 폐기 계약. 사이클 66 K-2 의미 전환 패턴."
    ),
)
@pytest.mark.asyncio
async def test_h2_universe_500_cap_with_full_kospi_kosdaq():
    """H-2.b: KOSPI 300 + KOSDAQ 300 적재 시 500 cap 영속 (사이클 89 영속).

    검증 매트릭스:
    - volume_rank 응답 500건 (KOSPI 300 + KOSDAQ 200)
    - stock_master 전수 적재
    - 사이클 89 KOSPI[:250] + KOSDAQ[:250] = 500 cap 영속
    - unknown 0건 (전수 분류 가능)

    영속 의무: 사이클 89 KOSPI 250 + KOSDAQ 250 cap 변경 0.
    """
    from src.engine import scanner

    raw_rows = []
    sm_map = {}
    # KOSPI 300건 (전수 적재)
    for i in range(300):
        ticker = f"1{i:05d}"
        raw_rows.append(_make_volume_rank_row(ticker))
        sm_map[ticker] = _make_stock_basics(ticker, "02")
    # KOSDAQ 200건
    for i in range(200):
        ticker = f"2{i:05d}"
        raw_rows.append(_make_volume_rank_row(ticker))
        sm_map[ticker] = _make_stock_basics(ticker, "03")

    async def fake_get(ticker: str):
        return sm_map.get(ticker)

    with patch.object(scanner, "_fetch_volume_rank", new=AsyncMock(return_value=raw_rows)), \
         patch("src.db.stock_master.get", side_effect=fake_get):
        universe = await scanner.fetch_top_500_universe()

    # 사이클 89 cap 영속: KOSPI 250 + KOSDAQ 200 = 450 (unknown 0)
    assert len(universe) == 450, (
        f"\n사이클 95 H-2.b 위반 — 사이클 89 KOSPI/KOSDAQ cap 변경:\n"
        f"  기대: KOSPI[:250] + KOSDAQ[:200] = 450 (unknown 0)\n"
        f"  실제: {len(universe)}\n"
        f"  영속 위반 — 사이클 89 KOSPI 250 + KOSDAQ 250 cap 절대 변경 금지"
    )


@pytest.mark.asyncio
async def test_h2_universe_500_cap_with_overflow_unknown():
    """H-2.c: KOSPI 250 + KOSDAQ 250 + unknown 100 → universe 500 (cap), unknown overflow 폐기.

    검증 매트릭스:
    - 600건 응답 (KOSPI 250 + KOSDAQ 250 + 부재 100)
    - 사이클 89 KOSPI 250 + KOSDAQ 250 = 500 cap 도달
    - remaining = max(0, 500 - 250 - 250) = 0
    - unknown[:0] = [] → universe 500 (unknown 0)

    영속 의무: 500 cap 절대 영속 (사이클 89).
    """
    from src.engine import scanner

    raw_rows = []
    sm_map = {}
    for i in range(250):
        ticker = f"1{i:05d}"
        raw_rows.append(_make_volume_rank_row(ticker))
        sm_map[ticker] = _make_stock_basics(ticker, "02")
    for i in range(250):
        ticker = f"2{i:05d}"
        raw_rows.append(_make_volume_rank_row(ticker))
        sm_map[ticker] = _make_stock_basics(ticker, "03")
    for i in range(100):
        ticker = f"9{i:05d}"
        raw_rows.append(_make_volume_rank_row(ticker))
        # stock_master 부재

    async def fake_get(ticker: str):
        return sm_map.get(ticker)

    with patch.object(scanner, "_fetch_volume_rank", new=AsyncMock(return_value=raw_rows)), \
         patch("src.db.stock_master.get", side_effect=fake_get):
        universe = await scanner.fetch_top_500_universe()

    assert len(universe) == 500, (
        f"\n사이클 95 H-2.c 위반 — 500 cap 영속 결함:\n"
        f"  기대: KOSPI 250 + KOSDAQ 250 = 500 (unknown overflow 폐기)\n"
        f"  실제: {len(universe)}\n"
        f"  영속 의무: 사이클 89 500 cap 절대 변경 금지 + 사이클 95 unknown 합산도 cap 준수"
    )
