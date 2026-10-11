"""cycle443 — `overseas_quote.fetch_daily_chartprice` (FHKST03030100) 회귀 가드.

ndx2x_riskoff 전략의 유일한 KIS 신호 원천. `src.api.condition` 류 기존 회귀 가드와
같은 패턴(`monkeypatch.setattr(module, "kis_get_quote", AsyncMock(...))`) — 실제
KIS/네트워크에 닿지 않는다.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.api import overseas_quote as oq

pytestmark = pytest.mark.unit


def _row(bsop: str, close: str) -> dict:
    return {"stck_bsop_date": bsop, "ovrs_nmix_prpr": close, "mod_yn": "N"}


@pytest.mark.asyncio
async def test_fetch_daily_chartprice_calls_quote_pool_with_expected_params(monkeypatch):
    mock_get = AsyncMock(return_value={
        "rt_cd": "0",
        "output2": [_row("20261009", "25000.12"), _row("20261008", "24900.00")],
    })
    monkeypatch.setattr(oq, "kis_get_quote", mock_get)

    rows = await oq.fetch_daily_chartprice(date(2026, 10, 1), date(2026, 10, 9))

    assert mock_get.await_count == 1
    _, kwargs = mock_get.await_args
    sent_path_tr = mock_get.await_args.args
    assert sent_path_tr[0] == oq.PATH
    assert sent_path_tr[1] == oq.TR_ID
    params = kwargs["params"]
    assert params["FID_COND_MRKT_DIV_CODE"] == "N"
    assert params["FID_INPUT_ISCD"] == "NDX"
    assert params["FID_INPUT_DATE_1"] == "20261001"
    assert params["FID_INPUT_DATE_2"] == "20261009"
    assert params["FID_PERIOD_DIV_CODE"] == "D"
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_fetch_daily_chartprice_zero_rows_is_error_even_when_rt_cd_ok(monkeypatch):
    """운영 실측 — `.NDX`·`IXIC` 등 잘못된 코드는 `rt_cd=0` 인데 0행으로 온다. 0행=오류로 취급."""
    mock_get = AsyncMock(return_value={"rt_cd": "0", "output2": []})
    monkeypatch.setattr(oq, "kis_get_quote", mock_get)

    with pytest.raises(oq.OverseasIndexEmptyResponseError):
        await oq.fetch_daily_chartprice(date(2026, 10, 1), date(2026, 10, 9), iscd=".NDX")


@pytest.mark.asyncio
async def test_fetch_daily_chartprice_missing_output2_key_is_also_error(monkeypatch):
    mock_get = AsyncMock(return_value={"rt_cd": "0"})
    monkeypatch.setattr(oq, "kis_get_quote", mock_get)

    with pytest.raises(oq.OverseasIndexEmptyResponseError):
        await oq.fetch_daily_chartprice(date(2026, 10, 1), date(2026, 10, 9))


@pytest.mark.asyncio
async def test_fetch_daily_chartprice_custom_iscd_passthrough(monkeypatch):
    mock_get = AsyncMock(return_value={"rt_cd": "0", "output2": [_row("20261009", "1.0")]})
    monkeypatch.setattr(oq, "kis_get_quote", mock_get)

    await oq.fetch_daily_chartprice(date(2026, 10, 1), date(2026, 10, 9), iscd="SPX")

    _, kwargs = mock_get.await_args
    assert kwargs["params"]["FID_INPUT_ISCD"] == "SPX"
