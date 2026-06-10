"""사이클 95 M-2 — `_scanner_upsert_loop` chain 영속 (unknown 영역 ticker 도 upsert 진입) (MEDIUM).

명세 (`_workspace/red/cycle95_chicken_and_egg_fix_ui.md`):

- 사이클 93 `_universe_eager_refresh_loop` chain 영속:
  `fetch_top_500_universe()` → `_universe_eager_refresh_loop(tickers)` 호출 chain
- 사이클 95 시정 = universe 영역에 unknown ticker 합집합 진입 후 upsert chain 도 unknown 처리

검증:
- `fetch_top_500_universe()` 반환 universe 영역에 unknown ticker 포함
- 동일 universe 가 `_universe_eager_refresh_loop` 입력으로 그대로 전달 (chain 변경 0)
- unknown ticker 도 24h TTL fresh skip 후 `inquire_stock_basics` + `upsert_one` 호출
- chicken-and-egg 자연 회복 메커니즘 (다음 사이클 KOSPI/KOSDAQ 정확 분류)

영속 의무:
- 사이클 93 호출 chain 시그너처 변경 0
- 사이클 89 `_universe_eager_refresh_loop` 함수 본체 변경 0 (24h TTL + 50ms Rate Limit)
- 매매 안전성 영향 0 (scanner 단계)
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
    }


def _make_stock_basics(ticker: str, excg_dvsn_cd: str):
    from src.models.stock import StockBasics

    return StockBasics(
        ticker=ticker,
        name=f"종목{ticker}",
        excg_dvsn_cd=excg_dvsn_cd,
        raw={"mksc_shrn_iscd": ticker, "excg_dvsn_cd": excg_dvsn_cd},
    )


@pytest.mark.asyncio
async def test_m2_unknown_tickers_in_universe_chain_input():
    """M-2.a: `fetch_top_500_universe()` 가 unknown ticker 도 universe 영역에 포함하여 반환.

    검증 매트릭스:
    - volume_rank 5건 (KOSPI 1 + KOSDAQ 1 + 부재 3)
    - 사이클 95 시정 후 universe = 5 (모두 포함, unknown 3건도 chain 입력)
    - 다음 단계 `_universe_eager_refresh_loop` 가 5 ticker 모두 upsert 처리 가능
    - chicken-and-egg 자연 회복 첫 사이클 ON

    Red (사이클 95): production None continue → universe 2 → chain 입력 2 → FAIL.

    Green: unknown 합집합 → universe 5 → chain 입력 5 → PASS.
    """
    from src.engine import scanner

    tickers = ["005930", "035720", "999001", "999002", "999003"]
    raw_rows = [_make_volume_rank_row(t) for t in tickers]
    sm_map = {
        "005930": _make_stock_basics("005930", "02"),
        "035720": _make_stock_basics("035720", "03"),
        # 999001/2/3 부재
    }

    async def fake_get(ticker: str):
        return sm_map.get(ticker)

    with patch.object(scanner, "_fetch_volume_rank", new=AsyncMock(return_value=raw_rows)), \
         patch("src.db.stock_master.get", side_effect=fake_get):
        universe = await scanner.fetch_top_500_universe()

    universe_set = set(universe)
    absent_tickers = {"999001", "999002", "999003"}
    missing = absent_tickers - universe_set

    assert missing == set(), (
        f"\n사이클 95 M-2.a 위반 — chain 입력에 unknown ticker 누락:\n"
        f"  부재 ticker: {sorted(absent_tickers)}\n"
        f"  universe 누락: {sorted(missing)}\n"
        f"  결함 인과: _universe_eager_refresh_loop 입력 영역에서 unknown 자연 skip → 영구 lock-in\n"
        f"  시정: universe 영역에 unknown 합집합 진입 → chain 통해 upsert 자연 회복"
    )

    assert len(universe) == 5, (
        f"\n사이클 95 M-2.a 위반 — universe 카운트 결함:\n"
        f"  기대: 5 (KOSPI 1 + KOSDAQ 1 + unknown 3)\n"
        f"  실제: {len(universe)}"
    )


@pytest.mark.asyncio
async def test_m2_universe_eager_refresh_loop_signature_unchanged():
    """M-2.b: `_universe_eager_refresh_loop` 시그너처 + 본체 행위 변경 0 영속.

    검증 매트릭스:
    - 사이클 89 본체 행위 영속 (24h TTL fresh skip + 50ms Rate Limit + graceful)
    - unknown ticker 도 동일 패턴으로 처리 (분기 없음)
    - 사이클 93 chain 시그너처 영속 (`_universe_eager_refresh_loop(candidates)` 단일 인자)

    영속 의무:
    - 사이클 89/93 변경 0
    - unknown ticker 영역도 동일 chain 진입 (분기 없음)
    """
    import inspect
    from src.engine import scanner

    sig = inspect.signature(scanner._universe_eager_refresh_loop)
    params = list(sig.parameters.keys())

    assert params == ["candidates"], (
        f"\n사이클 95 M-2.b 위반 — `_universe_eager_refresh_loop` 시그너처 변경:\n"
        f"  기대: ['candidates'] (사이클 89/93 영속)\n"
        f"  실제: {params}\n"
        f"  영속 의무: 사이클 93 호출 chain 변경 0"
    )


@pytest.mark.asyncio
async def test_m2_unknown_ticker_enters_upsert_chain():
    """M-2.c: unknown ticker 가 `_universe_eager_refresh_loop` 진입 시 upsert 시도.

    검증 매트릭스:
    - unknown ticker 1건 (stock_master 부재)
    - is_stale=True (TTL 24h, 부재 = stale)
    - inquire_stock_basics 호출 + upsert_one 호출 영역 영속

    영속 의무:
    - 사이클 89 본체 변경 0 (graceful + 50ms sleep)
    - chicken-and-egg 회복 메커니즘 입증
    """
    from src.engine import scanner

    upsert_called_tickers = []

    async def fake_is_stale(ticker, max_age_hours=24):
        return True  # stock_master 부재 → 전수 stale

    async def fake_inquire(ticker):
        return _make_stock_basics(ticker, "02")

    async def fake_upsert(basics):
        upsert_called_tickers.append(basics.ticker)

    with patch("src.db.stock_master.is_stale", side_effect=fake_is_stale), \
         patch("src.api.condition.inquire_stock_basics", side_effect=fake_inquire), \
         patch("src.db.stock_master.upsert_one", side_effect=fake_upsert):
        # unknown ticker 만 chain 진입
        await scanner._universe_eager_refresh_loop(["999001"])

    assert "999001" in upsert_called_tickers, (
        f"\n사이클 95 M-2.c 위반 — unknown ticker upsert chain 진입 결함:\n"
        f"  기대: 999001 upsert 호출\n"
        f"  실제 upsert ticker: {upsert_called_tickers}\n"
        f"  결함 인과: unknown ticker chain 미진입 → chicken-and-egg 회복 메커니즘 결함"
    )
