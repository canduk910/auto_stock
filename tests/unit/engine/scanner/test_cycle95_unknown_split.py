"""사이클 95 H-1 — stock_master 부재 종목 = unknown 영역 합집합 진입 (HIGH).

명세 (`_workspace/red/cycle95_chicken_and_egg_fix_ui.md`):

- 사이클 94 영역 3 결함 = `_classify_market(None) -> None` → 자연 skip
- 사이클 95 시정 = None 분기 → `unknown.append(row)` (continue 금지)
- chicken-and-egg lock-in 차단 (첫 호출에서 ~500 ticker upsert chain trigger)

Red 상태 (사이클 95): production 코드 None 분기 = `continue` → unknown 영역 0건 → FAIL.

Green (backend-dev): None 분기 = `unknown.append(row)` → unknown ≥ stock_master 부재 카운트 → PASS.

영속 의무:
- 매매 안전성 영향 0 (scanner 단계 = 매수 진입 *전*, 사이클 38 명문화 영속)
- 사이클 94 영역 1/2 (`"0000"` 단일화 + post-split) 영속
- KIS 호출 0건 증가 (사이클 94 영역 3 패턴 답습)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_volume_rank_row(ticker: str) -> dict:
    """KIS volume_rank output 1행 mock — 사이클 94 형식 답습."""
    return {
        "mksc_shrn_iscd": ticker,
        "prdy_vol": "1000000",
        "stck_prpr": "50000",
        "prdy_vrss": "1000",
        "prdy_ctrt": "2.04",
    }


def _make_stock_basics(ticker: str, excg_dvsn_cd: str):
    """StockBasics mock — `_classify_market` 영역 정합 ('02'=KOSPI / '03'=KOSDAQ)."""
    from src.models.stock import StockBasics

    return StockBasics(
        ticker=ticker,
        name=f"종목{ticker}",
        excg_dvsn_cd=excg_dvsn_cd,
        raw={"mksc_shrn_iscd": ticker, "excg_dvsn_cd": excg_dvsn_cd, "bfdy_clpr": "50000"},
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 96 Q50=D — 사이클 94 post-split chain (`_classify_market` + `stock_master.get`) 폐기 계약. "
        "사이클 96 영역 복원 = 2회 분리 호출 (KIS API 업종코드 분류 자체 = unknown 불필요). "
        "사이클 95 unknown 합집합 graceful = unknown=0 정상 영속. 사이클 66 K-2 의미 전환 패턴."
    ),
)
@pytest.mark.asyncio
async def test_h1_unknown_split_appends_when_stock_master_absent():
    """H-1.a: stock_master 부재 종목 = unknown 영역 합집합 진입.

    검증 매트릭스:
    - volume_rank 응답 10건 중 KOSPI 2 + KOSDAQ 1 + stock_master 부재 7
    - 사이클 95 시정 후: universe = KOSPI 2 + KOSDAQ 1 + unknown 7 = 10
    - 사이클 94 영속 (Red 단계): universe = KOSPI 2 + KOSDAQ 1 + (None 자연 skip 7) = 3

    Red 상태 (사이클 95): production 코드 = None continue → universe 3 → FAIL (10 ≠ 3).

    Green (backend-dev): None → `unknown.append(row)` → universe 10 → PASS.
    """
    from src.engine import scanner

    # 10 종목 raw (KOSPI 2 + KOSDAQ 1 + 부재 7)
    raw_rows = [_make_volume_rank_row(f"00500{i}") for i in range(10)]

    # stock_master.get 동작: 005000=KOSPI, 005001=KOSPI, 005002=KOSDAQ, 나머지 7건 None
    sm_map = {
        "005000": _make_stock_basics("005000", "02"),
        "005001": _make_stock_basics("005001", "02"),
        "005002": _make_stock_basics("005002", "03"),
    }

    async def fake_get(ticker: str):
        return sm_map.get(ticker)

    with patch.object(scanner, "_fetch_volume_rank", new=AsyncMock(return_value=raw_rows)), \
         patch("src.db.stock_master.get", side_effect=fake_get):
        universe = await scanner.fetch_top_500_universe()

    assert len(universe) == 10, (
        f"\n사이클 95 H-1.a 위반 — chicken-and-egg lock-in 영구 잔존:\n"
        f"  기대: universe = KOSPI 2 + KOSDAQ 1 + unknown 7 = 10\n"
        f"  실제: universe = {len(universe)} (None 자연 skip 영역 잔존)\n"
        f"  결함 인과: `_classify_market(None) -> None` 분기 자연 skip\n"
        f"  시정: None → `unknown.append(row)` 합집합 진입 의무\n"
        f"  KIS 호출 0건 증가 (stock_master 캐시 활용)"
    )


@pytest.mark.asyncio
async def test_h1_unknown_subset_includes_absent_tickers():
    """H-1.b: unknown 합집합 영역에 stock_master 부재 ticker 전수 포함.

    검증 매트릭스:
    - stock_master 부재 7건 ticker 가 universe 영역에 모두 포함
    - chicken-and-egg lock-in 차단 = 첫 호출에서 모든 미적재 ticker 도 upsert chain 진입

    Red 상태: None continue → 부재 7건 universe 영역 0건 → FAIL.

    Green: 부재 7건 universe 영역 7건 → PASS.
    """
    from src.engine import scanner

    raw_rows = [_make_volume_rank_row(f"00500{i}") for i in range(10)]
    sm_map = {
        "005000": _make_stock_basics("005000", "02"),
        "005002": _make_stock_basics("005002", "03"),
    }
    absent_tickers = {f"00500{i}" for i in range(10)} - set(sm_map.keys())

    async def fake_get(ticker: str):
        return sm_map.get(ticker)

    with patch.object(scanner, "_fetch_volume_rank", new=AsyncMock(return_value=raw_rows)), \
         patch("src.db.stock_master.get", side_effect=fake_get):
        universe = await scanner.fetch_top_500_universe()

    universe_set = set(universe)
    missing_from_universe = absent_tickers - universe_set

    assert missing_from_universe == set(), (
        f"\n사이클 95 H-1.b 위반 — stock_master 부재 ticker 영구 lock-in:\n"
        f"  부재 ticker (stock_master 미적재): {sorted(absent_tickers)}\n"
        f"  universe 누락: {sorted(missing_from_universe)}\n"
        f"  결함 인과: None 자연 skip → 다음 사이클에서도 stock_master 미적재 → 영구 lock-in\n"
        f"  시정: None → unknown 합집합 → 다음 _universe_eager_refresh_loop 에서 upsert"
    )
