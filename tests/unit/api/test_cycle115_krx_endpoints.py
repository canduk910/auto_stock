"""사이클 115 (2026-06-12) — KRX OPEN API 4 endpoint 함수 회귀 가드.

Red 명세: `_workspace/red/cycle115_krx_endpoint_integration.md`

HIGH-2 (4 sub) — 4 endpoint 함수 정상 응답:
- fetch_stk_bydd_trd / fetch_ksq_bydd_trd / fetch_stk_isu_base_info / fetch_ksq_isu_base_info
- 응답: OutBlock_1 배열 반환

영속 의무:
- 사이클 88 G-REJECT (graceful 폴백 의무)
- 사이클 109 KIS market-cap 영역 폴백 대안
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _mock_krx_response(outblock_data: list[dict]):
    """KRX 응답 mock 헬퍼 (사이클 115 GET method 시정 영속).

    Returns:
        (mock_client, mock_response) — 호출자가 mock_response 직접 참조 가능.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"OutBlock_1": outblock_data})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_client, mock_response


def _patch_enabled_config(monkeypatch):
    """사이클 115 — KRX OPEN API 활성화 mock (테스트 fixture)."""
    from src.models.krx_open_api import KrxOpenApiConfig

    async def _fake_get():
        return KrxOpenApiConfig(
            enabled=True,
            base_url="https://data-dbg.krx.co.kr/svc/apis",
            key="test_key_1234567890",
        )

    monkeypatch.setattr(
        "src.db.system_config.get_krx_open_api_config", _fake_get
    )


@pytest.mark.asyncio
async def test_h2_1_fetch_stk_bydd_trd_returns_outblock1(monkeypatch):
    """HIGH-2.1: fetch_stk_bydd_trd 정상 응답 OutBlock_1 배열 반환."""
    from src.api import krx as krx_mod

    _patch_enabled_config(monkeypatch)
    sample = [
        {
            "BAS_DD": "2026/06/12",
            "ISU_CD": "005930",
            "ISU_NM": "삼성전자",
            "MKT_NM": "KOSPI",
            "TDD_CLSPRC": "70000",
            "MKTCAP": "418000000000000",
            "ACC_TRDVAL": "500000000000",
            "LIST_SHRS": "5969782550",
        }
    ]
    mock_client, mock_response = _mock_krx_response(sample)

    captured_url = []

    async def _capture_get(url, params=None):
        captured_url.append((url, params))
        return mock_response

    mock_client.get = _capture_get

    with patch("src.api.krx.httpx.AsyncClient", return_value=mock_client):
        result = await krx_mod.fetch_stk_bydd_trd("20260612")

    # OutBlock_1 배열 반환 정합
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["ISU_CD"] == "005930"
    assert result[0]["MKTCAP"] == "418000000000000"

    # KRX endpoint URL 정합 (사이클 115 정본)
    assert len(captured_url) == 1
    url, params = captured_url[0]
    assert url.endswith("/sto/stk_bydd_trd")
    assert params["basDd"] == "20260612"
    # AUTH_KEY 자동 추가 (호출자 명시 0)
    assert params["AUTH_KEY"] == "test_key_1234567890"


@pytest.mark.asyncio
async def test_h2_2_fetch_ksq_bydd_trd_returns_outblock1(monkeypatch):
    """HIGH-2.2: fetch_ksq_bydd_trd 정상 응답 OutBlock_1 배열 반환."""
    from src.api import krx as krx_mod

    _patch_enabled_config(monkeypatch)
    sample = [
        {
            "BAS_DD": "2026/06/12",
            "ISU_CD": "035720",
            "ISU_NM": "카카오",
            "MKT_NM": "KOSDAQ GLOBAL",
            "TDD_CLSPRC": "50000",
            "MKTCAP": "10000000000000",
        }
    ]
    mock_client, mock_response = _mock_krx_response(sample)

    captured_url = []

    async def _capture_get(url, params=None):
        captured_url.append((url, params))
        return mock_response

    mock_client.get = _capture_get

    with patch("src.api.krx.httpx.AsyncClient", return_value=mock_client):
        result = await krx_mod.fetch_ksq_bydd_trd("20260612")

    assert len(result) == 1
    assert result[0]["ISU_CD"] == "035720"

    # KOSDAQ endpoint URL 정합
    assert captured_url[0][0].endswith("/sto/ksq_bydd_trd")


@pytest.mark.asyncio
async def test_h2_3_fetch_stk_isu_base_info_returns_outblock1(monkeypatch):
    """HIGH-2.3: fetch_stk_isu_base_info 정상 응답 OutBlock_1 배열 반환.

    ticker 정합: ISU_SRT_CD 단축코드 6자리 (KRX 종목코드 정합).
    ISU_CD (12자리 표준) 와 차별 영구 영속.
    """
    from src.api import krx as krx_mod

    _patch_enabled_config(monkeypatch)
    sample = [
        {
            "ISU_CD": "KR7005930003",  # 표준코드 12자리
            "ISU_SRT_CD": "005930",  # 단축코드 6자리 (KRX 정합)
            "ISU_NM": "삼성전자보통주",
            "ISU_ABBRV": "삼성전자",
            "LIST_DD": "1975/06/11",
            "MKT_TP_NM": "유가증권시장",
            "SECUGRP_NM": "주권",
            "KIND_STKCERT_TP_NM": "보통주",
            "PARVAL": "100",
            "LIST_SHRS": "5969782550",
        }
    ]
    mock_client, mock_response = _mock_krx_response(sample)

    captured_url = []

    async def _capture_get(url, params=None):
        captured_url.append((url, params))
        return mock_response

    mock_client.get = _capture_get

    with patch("src.api.krx.httpx.AsyncClient", return_value=mock_client):
        result = await krx_mod.fetch_stk_isu_base_info("20260612")

    assert len(result) == 1
    # ISU_SRT_CD 단축코드 정합 영속
    assert result[0]["ISU_SRT_CD"] == "005930"
    assert result[0]["LIST_DD"] == "1975/06/11"
    assert result[0]["KIND_STKCERT_TP_NM"] == "보통주"

    assert captured_url[0][0].endswith("/sto/stk_isu_base_info")


@pytest.mark.asyncio
async def test_h2_4_fetch_ksq_isu_base_info_returns_outblock1(monkeypatch):
    """HIGH-2.4: fetch_ksq_isu_base_info 정상 응답 OutBlock_1 배열 반환."""
    from src.api import krx as krx_mod

    _patch_enabled_config(monkeypatch)
    sample = [
        {
            "ISU_SRT_CD": "035720",
            "ISU_NM": "카카오보통주",
            "MKT_TP_NM": "코스닥글로벌",
        }
    ]
    mock_client, mock_response = _mock_krx_response(sample)

    captured_url = []

    async def _capture_get(url, params=None):
        captured_url.append((url, params))
        return mock_response

    mock_client.get = _capture_get

    with patch("src.api.krx.httpx.AsyncClient", return_value=mock_client):
        result = await krx_mod.fetch_ksq_isu_base_info("20260612")

    assert len(result) == 1
    assert result[0]["ISU_SRT_CD"] == "035720"
    assert captured_url[0][0].endswith("/sto/ksq_isu_base_info")


@pytest.mark.asyncio
async def test_h2_5_endpoint_returns_empty_list_on_missing_outblock(monkeypatch):
    """HIGH-2.5: OutBlock_1 키 누락 시 빈 리스트 graceful 반환 (사이클 88 G-REJECT 영속)."""
    from src.api import krx as krx_mod

    _patch_enabled_config(monkeypatch)
    # OutBlock_1 키 자체 부재 → graceful 빈 리스트
    mock_client, mock_response = _mock_krx_response([])
    mock_response.json = MagicMock(return_value={})

    with patch("src.api.krx.httpx.AsyncClient", return_value=mock_client):
        result = await krx_mod.fetch_stk_bydd_trd("20260612")

    assert result == []


@pytest.mark.asyncio
async def test_h2_6_krx_api_error_propagates_to_endpoint(monkeypatch):
    """HIGH-2.6: KrxApiError 가 4 endpoint 함수로 전파 (호출자 graceful 폴백 의무)."""
    from src.api import krx as krx_mod
    from src.api.krx import KrxApiError
    from src.models.krx_open_api import KrxOpenApiConfig

    # enabled=False → KrxApiError 즉시 전파
    async def _fake_disabled():
        return KrxOpenApiConfig(enabled=False, key="anykey")

    monkeypatch.setattr(
        "src.db.system_config.get_krx_open_api_config", _fake_disabled
    )

    # 4 endpoint 모두 전파 영속
    with pytest.raises(KrxApiError, match="비활성"):
        await krx_mod.fetch_stk_bydd_trd("20260612")
    with pytest.raises(KrxApiError, match="비활성"):
        await krx_mod.fetch_ksq_bydd_trd("20260612")
    with pytest.raises(KrxApiError, match="비활성"):
        await krx_mod.fetch_stk_isu_base_info("20260612")
    with pytest.raises(KrxApiError, match="비활성"):
        await krx_mod.fetch_ksq_isu_base_info("20260612")
