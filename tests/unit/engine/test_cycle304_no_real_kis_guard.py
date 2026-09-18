"""cycle304 — `no_real_kis` 가드의 **양성 대조군**.

가드 자체는 부정 단언("실 KIS 를 때리지 않는다")이라, 가드가 조용히 무력화돼도
아무것도 붉어지지 않는다. 무력화 경로는 둘이다:

1. `src/api/condition.py` 가 `kis_get_quote` 를 모듈 전역이 아닌 다른 이름으로
   부르게 바뀐다(예: 함수 내부 import) → monkeypatch 가 안 걸린다.
2. 던지는 예외가 `Exception` 파생으로 바뀐다 → 일봉 fetch 경로의 이중 graceful
   (`fetch_daily_candles_backfill` 윈도우별 + `_stock_master_daily_load_once`
   ticker 별)이 **조용히 흡수**해 `failed++` 로 끝난다.

여기서는 모킹을 일부러 빠뜨린 채 backfill 분기를 태워, 가드가 그 두 겹을 **통과해**
테스트를 실패시키는지 확인한다. 이것이 2026-09-18 CI red(=모킹 누락이 실 KIS 호출로
새어 `httpx.HTTPStatusError: 500` 만 남긴 사고)의 재발을 구조적으로 막는 근거다.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.engine import scanner
from tests.unit.engine.conftest import RealKisCallEscaped

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("no_real_kis")]


@pytest.mark.asyncio
async def test_guard_fires_through_double_graceful():
    """`fetch_daily_candles_backfill` 모킹을 빠뜨리면 즉시 실패한다 (흡수 금지)."""
    rows = [{
        "ticker": "005930",
        "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"},
        "is_kospi200": False, "is_kosdaq150": False,
    }]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=0),  # < 225 → 분할 backfill 분기
    ), patch(
        # 🔴 `fetch_daily_candles_backfill` 은 **일부러** 모킹하지 않는다.
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=[]),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch(
        "asyncio.sleep", new=AsyncMock(),
    ):
        with pytest.raises(RealKisCallEscaped):
            await scanner._stock_master_daily_load_once()
