"""트랙 C(실비용 산출) — KIS `TTTC8715R` 기간별매매손익현황조회 래퍼 + 메인 래퍼 연속조회.

명세 = `_workspace/design/2026-10-01_mean_reversion_handoff.md` §2-9 · §4.2-1 · §4.3
정본 스펙 = `docs/kis/domestic-stock-order.md` 「기간별매매손익현황조회」(실전 전용) +
KIS MCP `inquire_period_trade_profit` 공식 샘플(응답 헤더 `tr_cont` 가 `M`/`F` 면 다음 쪽,
다음 요청은 헤더 `tr_cont="N"` + 본문 `ctx_area_fk100`/`ctx_area_nk100` 을 그대로 되돌린다).

| # | 계약 |
|---|---|
| P1 | 한 쪽 응답 — URL·TR_ID(실전 값)·쿼리 9키가 정본 그대로, 행·합계를 돌려준다 |
| P2 | 연속조회 2쪽 — 2번째 요청은 헤더 `tr_cont=N` + 1쪽의 ctx 를 싣고, 행이 이어 붙는다 |
| P3 | 빈 응답(output1 `[]`) — 행 0 · 합계는 그대로 |
| P4 | `rt_cd != "0"` — `KisApiError` 가 그대로 올라온다(부분 결과를 돌려주지 않는다) |
| P5 | 모의(vts) 환경 — KIS 를 부르지 않고 `RealEnvRequired` |
| P6 | 다음 쪽이 끝없이 와도 `_MAX_PAGES` 에서 멈추고 `truncated=True` |
| B1 | `kis_get(..., tr_cont=None)` 기본은 `tr_cont` 헤더도 `_response_headers` 도 없다(기존 호출부 무변) |
| B2 | `kis_get(..., tr_cont="N")` 은 헤더를 싣고 응답 헤더 `tr_cont` 를 `_response_headers` 로 돌려준다 |

실제 KIS 에 닿지 않는다 — respx 가 httpx 전송 계층을 가로챈다.
"""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock

import httpx
import pytest

import src.auth.token as _token_module
from src.api import base
from src.config import settings

pytestmark = pytest.mark.unit

_PATH = "/uapi/domestic-stock/v1/trading/inquire-period-trade-profit"


def _mod():
    return importlib.import_module("src.api.trade_profit")


@pytest.fixture
def stub_token(monkeypatch: pytest.MonkeyPatch):
    async def _get_token() -> str:
        return "dummy-access-token"

    def _build_headers(tr_id: str, hashkey: str = "") -> dict[str, str]:
        return {"authorization": "Bearer dummy", "tr_id": tr_id, "custtype": "P"}

    monkeypatch.setattr(_token_module.token_manager, "get_token", _get_token)
    monkeypatch.setattr(_token_module.token_manager, "build_headers", _build_headers)


@pytest.fixture
def real_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "kis_env", "real")


@pytest.fixture
def mock_write_log(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.db.system_logs as _sl

    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(_sl, "write_log", mock)
    return mock


def _row(trad_dt="20260930", pdno="035760", **over) -> dict:
    row = {
        "trad_dt": trad_dt, "pdno": pdno, "prdt_name": "CJ ENM", "trad_dvsn_name": "현금",
        "loan_dt": "", "hldg_qty": "0", "pchs_unpr": "39400", "buy_qty": "0", "buy_amt": "0",
        "sll_pric": "36110", "sll_qty": "5", "sll_amt": "180550", "rlzt_pfls": "-16980",
        "pfls_rt": "-8.62", "fee": "27", "tl_tax": "270", "loan_int": "0",
    }
    row.update(over)
    return row


_SUMMARY = {
    "sll_qty_smtl": "5", "sll_tr_amt_smtl": "180550", "sll_fee_smtl": "27",
    "sll_tltx_smtl": "270", "sll_excc_amt_smtl": "180253", "buyqty_smtl": "0",
    "buy_tr_amt_smtl": "0", "buy_fee_smtl": "0", "buy_tax_smtl": "0",
    "buy_excc_amt_smtl": "0", "tot_qty": "5", "tot_tr_amt": "180550", "tot_fee": "27",
    "tot_tltx": "270", "tot_excc_amt": "180253", "tot_rlzt_pfls": "-16980",
    "loan_int": "0", "tot_pftrt": "-8.62",
}


def _body(rows, *, nk="", fk="", summary=None, rt_cd="0") -> dict:
    return {
        "rt_cd": rt_cd, "msg_cd": "KIOK0510" if rt_cd == "0" else "OPSQ0002",
        "msg1": "조회가 완료되었습니다" if rt_cd == "0" else "없는 서비스 코드 입니다",
        "ctx_area_nk100": nk, "ctx_area_fk100": fk,
        "output1": rows, "output2": _SUMMARY if summary is None else summary,
    }


async def test_p1_single_page_params_and_parse(mock_kis, stub_token, real_env):
    route = mock_kis.get(path=_PATH).mock(
        return_value=httpx.Response(200, json=_body([_row()]), headers={"tr_cont": "D"})
    )
    out = await _mod().fetch_period_trade_profit("20260901", "20260930")

    assert route.call_count == 1
    req = route.calls[0].request
    assert req.headers["tr_id"] == "TTTC8715R"
    assert "tr_cont" not in req.headers  # 첫 쪽은 헤더 공란
    q = dict(req.url.params)
    assert q == {
        "CANO": settings.kis_account_no,
        "ACNT_PRDT_CD": settings.kis_account_product,
        "SORT_DVSN": "01",
        "PDNO": "",
        "INQR_STRT_DT": "20260901",
        "INQR_END_DT": "20260930",
        "CTX_AREA_NK100": "",
        "CBLC_DVSN": "00",
        "CTX_AREA_FK100": "",
    }
    assert out.rows == [_row()]
    assert out.summary == _SUMMARY
    assert out.pages == 1
    assert out.truncated is False


async def test_p2_two_pages_carry_ctx_and_tr_cont(mock_kis, stub_token, real_env):
    page1 = httpx.Response(
        200, json=_body([_row(pdno="035760")], nk="NK-1", fk="FK-1"), headers={"tr_cont": "M"}
    )
    page2 = httpx.Response(
        200, json=_body([_row(pdno="149950")], nk="", fk=""), headers={"tr_cont": "D"}
    )
    route = mock_kis.get(path=_PATH).mock(side_effect=[page1, page2])

    out = await _mod().fetch_period_trade_profit("20260901", "20260930")

    assert route.call_count == 2
    second = route.calls[1].request
    assert second.headers["tr_cont"] == "N"
    q2 = dict(second.url.params)
    assert q2["CTX_AREA_NK100"] == "NK-1"
    assert q2["CTX_AREA_FK100"] == "FK-1"
    assert [r["pdno"] for r in out.rows] == ["035760", "149950"]
    assert out.pages == 2
    assert out.truncated is False


async def test_p2b_tr_cont_F_also_means_next_page(mock_kis, stub_token, real_env):
    page1 = httpx.Response(200, json=_body([_row()], nk="A", fk="B"), headers={"tr_cont": "F"})
    page2 = httpx.Response(200, json=_body([_row(pdno="000660")]), headers={"tr_cont": "E"})
    route = mock_kis.get(path=_PATH).mock(side_effect=[page1, page2])
    out = await _mod().fetch_period_trade_profit("20260901", "20260930")
    assert route.call_count == 2
    assert len(out.rows) == 2


async def test_p3_empty_rows(mock_kis, stub_token, real_env):
    mock_kis.get(path=_PATH).mock(
        return_value=httpx.Response(200, json=_body([], summary={}), headers={"tr_cont": "D"})
    )
    out = await _mod().fetch_period_trade_profit("20261003", "20261003")
    assert out.rows == []
    assert out.summary == {}
    assert out.pages == 1


async def test_p3b_output2_as_list_is_normalized(mock_kis, stub_token, real_env):
    """정본은 output2 = object 지만 일부 TR 은 1원소 배열로 온다 — 둘 다 dict 로 읽는다."""
    mock_kis.get(path=_PATH).mock(
        return_value=httpx.Response(200, json=_body([_row()], summary=[_SUMMARY]))
    )
    out = await _mod().fetch_period_trade_profit("20260901", "20260930")
    assert out.summary == _SUMMARY


async def test_p4_rt_cd_error_raises(mock_kis, stub_token, real_env, mock_write_log):
    mock_kis.get(path=_PATH).mock(return_value=httpx.Response(200, json=_body([], rt_cd="1")))
    with pytest.raises(base.KisApiError) as ei:
        await _mod().fetch_period_trade_profit("20260901", "20260930")
    assert ei.value.msg_cd == "OPSQ0002"


async def test_p4b_error_on_second_page_raises_not_partial(
    mock_kis, stub_token, real_env, mock_write_log
):
    page1 = httpx.Response(200, json=_body([_row()], nk="A", fk="B"), headers={"tr_cont": "M"})
    page2 = httpx.Response(200, json=_body([], rt_cd="1"))
    mock_kis.get(path=_PATH).mock(side_effect=[page1, page2])
    with pytest.raises(base.KisApiError):
        await _mod().fetch_period_trade_profit("20260901", "20260930")


async def test_p5_vts_refuses_without_calling(mock_kis, stub_token, monkeypatch):
    monkeypatch.setattr(settings, "kis_env", "vts")
    route = mock_kis.get(path=_PATH).mock(return_value=httpx.Response(200, json=_body([])))
    m = _mod()
    with pytest.raises(m.RealEnvRequired):
        await m.fetch_period_trade_profit("20260901", "20260930")
    assert route.call_count == 0


async def test_p6_page_cap_sets_truncated(mock_kis, stub_token, real_env, monkeypatch):
    m = _mod()
    monkeypatch.setattr(m, "_MAX_PAGES", 3)
    route = mock_kis.get(path=_PATH).mock(
        side_effect=lambda req: httpx.Response(
            200, json=_body([_row()], nk="K", fk="F"), headers={"tr_cont": "M"}
        )
    )
    out = await m.fetch_period_trade_profit("20260901", "20260930")
    assert route.call_count == 3
    assert out.pages == 3
    assert out.truncated is True
    assert len(out.rows) == 3


async def test_b1_kis_get_default_has_no_tr_cont(mock_kis, stub_token):
    route = mock_kis.get(path=_PATH).mock(
        return_value=httpx.Response(200, json=_body([]), headers={"tr_cont": "M"})
    )
    data = await base.kis_get(_PATH, "TTTC8715R", {"CANO": "1"})
    assert "tr_cont" not in route.calls[0].request.headers
    assert "_response_headers" not in data


async def test_b2_kis_get_with_tr_cont_returns_response_header(mock_kis, stub_token):
    route = mock_kis.get(path=_PATH).mock(
        return_value=httpx.Response(200, json=_body([]), headers={"tr_cont": "M"})
    )
    data = await base.kis_get(_PATH, "TTTC8715R", {"CANO": "1"}, tr_cont="N")
    assert route.calls[0].request.headers["tr_cont"] == "N"
    assert data["_response_headers"] == {"tr_cont": "M"}


async def test_b2b_first_page_empty_tr_cont_still_reports_header(mock_kis, stub_token):
    route = mock_kis.get(path=_PATH).mock(
        return_value=httpx.Response(200, json=_body([]), headers={"tr_cont": "D"})
    )
    data = await base.kis_get(_PATH, "TTTC8715R", {}, tr_cont="")
    assert "tr_cont" not in route.calls[0].request.headers
    assert data["_response_headers"] == {"tr_cont": "D"}
