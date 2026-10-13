"""RS 1단계 Red — `src/api/invest_opinion.py` (KIS 래퍼, 시세 풀 경유).

명세 = `_workspace/design/2026-10-13_rs_fundamental_phase1.md` §C.
KIS 정본 = `docs/kis/domestic-stock-info.md` 「국내주식 종목투자의견」(FHKST663300C0) ·
「국내주식 종목추정실적」(HHKST668300C0).

모킹 방식 = 기존 래퍼 테스트 관례(`test_cycle443_overseas_quote.py`)
— `monkeypatch.setattr(module, "kis_get_quote", AsyncMock(...))`. 실제 KIS/네트워크 0.

명세 해석 가정(구현이 따를 계약):
- 모듈 상수 `OPINION_PATH`·`OPINION_TR_ID`·`ESTIMATE_PATH`·`ESTIMATE_TR_ID` (실전 TR_ID).
- `inquire_invest_opinion(ticker, date_from: date, date_to: date) -> list[dict]` —
  요청 파라미터 FID_COND_MRKT_DIV_CODE="J" · FID_COND_SCR_DIV_CODE="16633" · FID_INPUT_ISCD=ticker ·
  FID_INPUT_DATE_1=date_from "YYYYMMDD" · FID_INPUT_DATE_2=date_to "YYYYMMDD"
  (문서 Request Example 이 8자리다). 응답 `output` 배열 → 정규화 dict:
  `bsop_date`(date) · `mbcr_name` · `invt_opnn` · `rgbf_invt_opnn` · `hts_goal_prc`(int|None) ·
  `stck_prdy_clpr`(int|None) · `dprt`(float|None) · `raw`(원본 행 dict 그대로).
  빈 문자열·숫자 아님 → None(0 은 0 그대로 — 0 제외는 순수 함수 몫). `output` 없음/빈 배열 → [].
  `rt_cd != "0"` 은 base 래퍼가 올리는 예외를 그대로 전파(여기서 삼키지 않는다).
- `inquire_estimate_perform(ticker) -> dict | None` — 요청 `SHT_CD=ticker`.
  **실전 전용**: `settings.is_production` 이 False 면 KIS 를 부르지 않고 None.
  반환 = `{"ticker": ticker, "raw": 응답 전체 dict, "settle_months": [output4 의 dt ...]}`.
  `output1` 한글명이 ELW 용으로 잘못 붙어 있어 그 칸은 해석하지 않는다 — raw 로만 보관.
"""
from __future__ import annotations

import copy
from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.api import base
from src.api import invest_opinion as io
from src.config import settings

pytestmark = pytest.mark.unit

OPINION_PATH = "/uapi/domestic-stock/v1/quotations/invest-opinion"
ESTIMATE_PATH = "/uapi/domestic-stock/v1/quotations/estimate-perform"


# KIS 문서 Response Example 기반(필드명·형식 그대로).
_OPINION_RESP = {
    "rt_cd": "0", "msg_cd": "MCA00000", "msg1": "정상처리 되었습니다.",
    "output": [
        {
            "stck_bsop_date": "20240527", "invt_opnn": "매수", "invt_opnn_cls_code": "2",
            "rgbf_invt_opnn": "매수", "rgbf_invt_opnn_cls_code": "3", "mbcr_name": "SK",
            "hts_goal_prc": "105000", "stck_prdy_clpr": "75900", "stck_nday_esdg": "-29100",
            "nday_dprt": "-27.71", "stft_esdg": "-27400", "dprt": "-26.10",
        },
        {
            "stck_bsop_date": "20240520", "invt_opnn": "BUY", "invt_opnn_cls_code": "2",
            "rgbf_invt_opnn": "BUY", "rgbf_invt_opnn_cls_code": "3", "mbcr_name": "하이투자",
            "hts_goal_prc": "", "stck_prdy_clpr": "77400", "stck_nday_esdg": "",
            "nday_dprt": "", "stft_esdg": "", "dprt": "",
        },
        {
            "stck_bsop_date": "20240516", "invt_opnn": "Not Rated", "invt_opnn_cls_code": "0",
            "rgbf_invt_opnn": "", "rgbf_invt_opnn_cls_code": "", "mbcr_name": "미래에셋",
            "hts_goal_prc": "0", "stck_prdy_clpr": "78300", "stck_nday_esdg": "0",
            "nday_dprt": "0.00", "stft_esdg": "0", "dprt": "0.00",
        },
    ],
}

_ESTIMATE_RESP = {
    "rt_cd": "0", "msg_cd": "MCA00000", "msg1": "정상처리 되었습니다.",
    "output1": {
        "sht_cd": "A005930", "item_kor_nm": "삼성전자", "name1": "김한국", "name2": "",
        "estdate": "20240109", "rcmd_name": "매수", "capital": "8975.0",
        "forn_item_lmtrt": "0.00",
    },
    "output2": [
        {"data1": "2796048.0", "data2": "3022314.0", "data3": "2581509.0",
         "data4": "3048945.0", "data5": "3295675.0"},
        {"data1": "181.0", "data2": "81.0", "data3": "-146.0", "data4": "181.0", "data5": "81.0"},
    ],
    "output3": [
        {"data1": "858812.0", "data2": "824843.0", "data3": "483199.0",
         "data4": "792602.0", "data5": "1043367.0"},
    ],
    "output4": [
        {"dt": "202112"}, {"dt": "202212"}, {"dt": "202312"}, {"dt": "202412"}, {"dt": "202512"},
    ],
}


@pytest.fixture(autouse=True)
def _real_env(monkeypatch):
    """두 TR 모두 실전 전용 — 기본은 실전 환경(모의 케이스는 각 테스트가 vts 로 덮는다)."""
    monkeypatch.setattr(settings, "kis_env", "real")


# ── 화이트리스트 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [OPINION_PATH, ESTIMATE_PATH])
def test_quote_allowed_paths_include_new_paths(path):
    """누락 시 `_request_via_quote_pool` 이 QuotePoolPathError (사이클 109·C1·VI 선례)."""
    assert path in base._QUOTE_ALLOWED_PATHS


def test_module_constants_are_real_tr_ids_and_paths():
    assert io.OPINION_PATH == OPINION_PATH
    assert io.OPINION_TR_ID == "FHKST663300C0"
    assert io.ESTIMATE_PATH == ESTIMATE_PATH
    assert io.ESTIMATE_TR_ID == "HHKST668300C0"


# ── inquire_invest_opinion ───────────────────────────────────────────────────

async def test_invest_opinion_calls_quote_pool_with_expected_params(monkeypatch):
    mock_get = AsyncMock(return_value=copy.deepcopy(_OPINION_RESP))
    monkeypatch.setattr(io, "kis_get_quote", mock_get)

    await io.inquire_invest_opinion("005930", date(2024, 1, 1), date(2024, 5, 28))

    assert mock_get.await_count == 1
    args, kwargs = mock_get.await_args
    assert args[0] == OPINION_PATH
    assert args[1] == "FHKST663300C0"
    assert kwargs["params"] == {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_COND_SCR_DIV_CODE": "16633",
        "FID_INPUT_ISCD": "005930",
        "FID_INPUT_DATE_1": "20240101",
        "FID_INPUT_DATE_2": "20240528",
    }


async def test_invest_opinion_normalizes_rows(monkeypatch):
    monkeypatch.setattr(io, "kis_get_quote", AsyncMock(return_value=copy.deepcopy(_OPINION_RESP)))

    rows = await io.inquire_invest_opinion("005930", date(2024, 1, 1), date(2024, 5, 28))

    assert len(rows) == 3
    r0 = rows[0]
    assert r0["bsop_date"] == date(2024, 5, 27)
    assert r0["mbcr_name"] == "SK"
    assert r0["invt_opnn"] == "매수"
    assert r0["rgbf_invt_opnn"] == "매수"
    assert r0["hts_goal_prc"] == 105000 and isinstance(r0["hts_goal_prc"], int)
    assert r0["stck_prdy_clpr"] == 75900
    assert r0["dprt"] == pytest.approx(-26.10)
    assert r0["raw"] == _OPINION_RESP["output"][0]


async def test_invest_opinion_blank_numbers_become_none_and_zero_stays_zero(monkeypatch):
    monkeypatch.setattr(io, "kis_get_quote", AsyncMock(return_value=copy.deepcopy(_OPINION_RESP)))

    rows = await io.inquire_invest_opinion("005930", date(2024, 1, 1), date(2024, 5, 28))

    assert rows[1]["hts_goal_prc"] is None
    assert rows[1]["dprt"] is None
    assert rows[2]["hts_goal_prc"] == 0  # 0 제외는 순수 함수(target_revision_breadth) 몫


@pytest.mark.parametrize("resp", [
    {"rt_cd": "0", "output": []},
    {"rt_cd": "0"},
])
async def test_invest_opinion_empty_output_returns_empty_list(monkeypatch, resp):
    monkeypatch.setattr(io, "kis_get_quote", AsyncMock(return_value=resp))
    assert await io.inquire_invest_opinion("005930", date(2024, 1, 1), date(2024, 5, 28)) == []


async def test_invest_opinion_kis_error_propagates(monkeypatch):
    err = base.KisApiError("1", "EGW00123", "조회 오류")
    monkeypatch.setattr(io, "kis_get_quote", AsyncMock(side_effect=err))
    with pytest.raises(base.KisApiError):
        await io.inquire_invest_opinion("005930", date(2024, 1, 1), date(2024, 5, 28))


# ── inquire_estimate_perform ─────────────────────────────────────────────────

async def test_estimate_perform_calls_quote_pool_with_real_tr(monkeypatch):
    monkeypatch.setattr(settings, "kis_env", "real")
    mock_get = AsyncMock(return_value=copy.deepcopy(_ESTIMATE_RESP))
    monkeypatch.setattr(io, "kis_get_quote", mock_get)

    await io.inquire_estimate_perform("005930")

    args, kwargs = mock_get.await_args
    assert args[0] == ESTIMATE_PATH
    assert args[1] == "HHKST668300C0"
    assert kwargs["params"] == {"SHT_CD": "005930"}


async def test_estimate_perform_keeps_raw_whole_and_extracts_settle_months(monkeypatch):
    monkeypatch.setattr(settings, "kis_env", "real")
    monkeypatch.setattr(io, "kis_get_quote", AsyncMock(return_value=copy.deepcopy(_ESTIMATE_RESP)))

    got = await io.inquire_estimate_perform("005930")

    assert got["ticker"] == "005930"
    assert got["raw"] == _ESTIMATE_RESP
    assert got["settle_months"] == ["202112", "202212", "202312", "202412", "202512"]


async def test_estimate_perform_when_vts_then_no_call_and_none(monkeypatch):
    """모의투자 미지원 TR — 모의 환경에서는 호출 자체를 하지 않는다."""
    monkeypatch.setattr(settings, "kis_env", "vts")
    mock_get = AsyncMock(return_value=copy.deepcopy(_ESTIMATE_RESP))
    monkeypatch.setattr(io, "kis_get_quote", mock_get)

    assert await io.inquire_estimate_perform("005930") is None
    mock_get.assert_not_awaited()


async def test_estimate_perform_missing_output4_gives_empty_settle_months(monkeypatch):
    monkeypatch.setattr(settings, "kis_env", "real")
    resp = copy.deepcopy(_ESTIMATE_RESP)
    del resp["output4"]
    monkeypatch.setattr(io, "kis_get_quote", AsyncMock(return_value=resp))

    got = await io.inquire_estimate_perform("005930")
    assert got["settle_months"] == []
    assert got["raw"] == resp


async def test_invest_opinion_when_vts_then_no_call_and_empty(monkeypatch):
    """FHKST663300C0 도 모의 미지원 — 모의 환경에서는 호출하지 않는다."""
    monkeypatch.setattr(settings, "kis_env", "vts")
    mock_get = AsyncMock(return_value=copy.deepcopy(_OPINION_RESP))
    monkeypatch.setattr(io, "kis_get_quote", mock_get)
    assert await io.inquire_invest_opinion("005930", date(2024, 1, 1), date(2024, 5, 28)) == []
    mock_get.assert_not_awaited()


async def test_invest_opinion_truncated_100_rows_warns(monkeypatch, caplog):
    monkeypatch.setattr(settings, "kis_env", "real")
    row = copy.deepcopy(_OPINION_RESP["output"][0])
    monkeypatch.setattr(io, "kis_get_quote", AsyncMock(return_value={"rt_cd": "0", "output": [row] * 100}))
    with caplog.at_level("WARNING"):
        await io.inquire_invest_opinion("005930", date(2024, 1, 1), date(2024, 5, 28))
    msgs = [r.getMessage() for r in caplog.records]
    assert any("[invest_opinion_truncated]" in m and "005930" in m and "20240101" in m for m in msgs)


async def test_invest_opinion_under_100_rows_no_truncation_warning(monkeypatch, caplog):
    monkeypatch.setattr(settings, "kis_env", "real")
    monkeypatch.setattr(io, "kis_get_quote", AsyncMock(return_value=copy.deepcopy(_OPINION_RESP)))
    with caplog.at_level("WARNING"):
        await io.inquire_invest_opinion("005930", date(2024, 1, 1), date(2024, 5, 28))
    assert not any("[invest_opinion_truncated]" in r.getMessage() for r in caplog.records)


async def test_estimate_perform_strips_response_headers_from_raw(monkeypatch):
    monkeypatch.setattr(settings, "kis_env", "real")
    resp = copy.deepcopy(_ESTIMATE_RESP)
    resp["_response_headers"] = {"tr_cont": "N", "gt_uid": "x"}
    monkeypatch.setattr(io, "kis_get_quote", AsyncMock(return_value=resp))
    got = await io.inquire_estimate_perform("005930")
    assert "_response_headers" not in got["raw"]
    assert got["raw"] == _ESTIMATE_RESP
