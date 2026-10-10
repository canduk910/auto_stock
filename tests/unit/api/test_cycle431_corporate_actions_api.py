"""cycle431 — 예탁원정보 3종 + CTRGA011R 연속조회 회귀.

사용자 결정 2026-10-10(안1) — 예탁원 TR 은 `tr_cont` M→N(CTS 항상 공백),
CTRGA011R 은 `ctx_area_fk100`/`ctx_area_nk100` 되돌림(`get_daily_orders` 와
같은 모양). 진행 없음(같은 쪽 반복)은 예외.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from src.api import corporate_actions as ca

pytestmark = pytest.mark.unit

_TODAY = date(2026, 10, 10)


def _resp(output1=None, tr_cont=""):
    body = {"output1": output1 or [], "_response_headers": {"tr_cont": tr_cont}}
    return body


@pytest.mark.asyncio
async def test_fetch_face_value_change_single_page():
    with patch("src.api.base.kis_get", new=AsyncMock(return_value=_resp([{"sht_cd": "001390"}]))):
        with patch("src.api.corporate_actions.kis_get", new=AsyncMock(return_value=_resp([{"sht_cd": "001390"}]))):
            rows = await ca.fetch_face_value_change("001390", today=_TODAY)
    assert rows == [{"sht_cd": "001390"}]


@pytest.mark.asyncio
async def test_fetch_face_value_change_continues_pagination_on_m_flag():
    page1 = _resp([{"sht_cd": "a"}], tr_cont="M")
    page2 = _resp([{"sht_cd": "b"}], tr_cont="")
    mock = AsyncMock(side_effect=[page1, page2])
    with patch("src.api.corporate_actions.kis_get", new=mock):
        rows = await ca.fetch_face_value_change("001390", today=_TODAY)
    assert rows == [{"sht_cd": "a"}, {"sht_cd": "b"}]
    assert mock.call_count == 2
    # 둘째 호출의 tr_cont="N", CTS 는 항상 공백
    _, kwargs = mock.call_args_list[1]
    assert mock.call_args_list[1].kwargs.get("tr_cont") == "N"
    second_params = mock.call_args_list[1].args[2]
    assert second_params["CTS"] == ""


@pytest.mark.asyncio
async def test_fetch_face_value_change_stuck_pagination_raises():
    # tr_cont 는 계속 "M" 인데 새 행이 0개 — 진행 없음
    stuck = _resp([], tr_cont="M")
    mock = AsyncMock(return_value=stuck)
    with patch("src.api.corporate_actions.kis_get", new=mock):
        with pytest.raises(ca.CorporateActionPaginationStuckError):
            await ca.fetch_face_value_change("001390", today=_TODAY)


@pytest.mark.asyncio
async def test_fetch_capital_decrease_builds_date_window():
    mock = AsyncMock(return_value=_resp([]))
    with patch("src.api.corporate_actions.kis_get", new=mock):
        await ca.fetch_capital_decrease("001390", today=_TODAY)
    params = mock.call_args.args[2]
    assert params["F_DT"] < params["T_DT"] == "20261010"


@pytest.mark.asyncio
async def test_fetch_merger_split_detection_only():
    mock = AsyncMock(return_value=_resp([{"sht_cd": "001390", "cust_nm": "합병사"}]))
    with patch("src.api.corporate_actions.kis_get", new=mock):
        rows = await ca.fetch_merger_split("001390", today=_TODAY)
    assert rows == [{"sht_cd": "001390", "cust_nm": "합병사"}]


@pytest.mark.asyncio
async def test_fetch_period_rights_empty_on_vts():
    with patch("src.config.settings.kis_env", "vts"):
        rows = await ca.fetch_period_rights("005930", start_date="20261010", end_date="20261010")
    assert rows == []


@pytest.mark.asyncio
async def test_fetch_period_rights_uses_output_key_not_output1():
    body = {
        "output": [{"rght_type_cd": "15"}],
        "ctx_area_fk100": "", "ctx_area_nk100": "",
        "_response_headers": {"tr_cont": ""},
    }
    mock = AsyncMock(return_value=body)
    with (
        patch("src.config.settings.kis_env", "real"),
        patch("src.api.corporate_actions.kis_get", new=mock),
    ):
        rows = await ca.fetch_period_rights("005930", start_date="20261010", end_date="20261010")
    assert rows == [{"rght_type_cd": "15"}]


@pytest.mark.asyncio
async def test_fetch_period_rights_continuation_follows_ctx_area():
    page1 = {
        "output": [{"rght_type_cd": "15"}],
        "ctx_area_fk100": "FK1", "ctx_area_nk100": "NK1",
        "_response_headers": {"tr_cont": "M"},
    }
    page2 = {
        "output": [{"rght_type_cd": "11"}],
        "ctx_area_fk100": "", "ctx_area_nk100": "",
        "_response_headers": {"tr_cont": "D"},
    }
    mock = AsyncMock(side_effect=[page1, page2])
    with (
        patch("src.config.settings.kis_env", "real"),
        patch("src.api.corporate_actions.kis_get", new=mock),
    ):
        rows = await ca.fetch_period_rights("005930", start_date="20261010", end_date="20261010")
    assert len(rows) == 2
    second_params = mock.call_args_list[1].args[2]
    assert second_params["CTX_AREA_FK100"] == "FK1"
    assert second_params["CTX_AREA_NK100"] == "NK1"
    assert mock.call_args_list[1].kwargs.get("tr_cont") == "N"


@pytest.mark.asyncio
async def test_fetch_period_rights_stuck_pagination_raises():
    stuck = {
        "output": [],
        "ctx_area_fk100": "", "ctx_area_nk100": "",
        "_response_headers": {"tr_cont": "M"},
    }
    mock = AsyncMock(return_value=stuck)
    with (
        patch("src.config.settings.kis_env", "real"),
        patch("src.api.corporate_actions.kis_get", new=mock),
    ):
        with pytest.raises(ca.CorporateActionPaginationStuckError):
            await ca.fetch_period_rights("005930", start_date="20261010", end_date="20261010")
