"""cycle430 — `get_daily_orders`(TTTC0081R) 연속조회 (사용자 지시 2026-10-10).

명세 = 작업 지시서 "cycle430 — 주문내역 조회(TTTC0081R) `get_daily_orders` 연속조회"
선례 = `src/api/trade_profit.py::fetch_period_trade_profit` (트랙 C) + 그 테스트
`tests/unit/api/test_trackc_period_trade_profit.py`.

| # | 계약 |
|---|---|
| G1 | 한 쪽 — 첫 요청 params 15키가 기존과 byte 동일(`tr_cont` 헤더 없음) |
| G2 | 세 쪽 연결(`M`/`F` → `D`) — 다음 요청은 헤더 `tr_cont="N"` + 직전 쪽 ctx 두 값을 되돌리고 행이 이어 붙는다 |
| G3a | 쪽수 상한이 없다 — 60쪽(실전 100건/쪽 상정의 1쪽 50 초과)도 전부 이어 붙인다 |
| G3b | `tr_cont` 가 `M`/`F` 인데 ctx 가 직전 요청과 똑같다 — `DailyOrdersPaginationStuckError` + WARNING `[daily_orders_pagination_stuck]`(부분 목록 반환 없음) |
| G3c | `tr_cont` 가 `M`/`F` 인데 ctx 둘 다 빈 값이다 — 같은 예외 + 마커 |
| G4 | 중간 쪽 `rt_cd != "0"` — `KisApiError` 가 그대로 올라온다(부분 결과 없음) |
| G6 | `odno`/`pdno` 필터는 모든 쪽에서 유지된다 |
| G7 | 모의(vts) 15행 쪽에서도 같은 연결 동작 |

가짜 응답은 전부 `side_effect=[...]` 유한 리스트다 — 무한 루프 버그가 있어도 리스트
소진 뒤 respx 가 바로 실패해 테스트가 멈추지 않고 fail 한다(사용자 지시 2026-10-10).

실제 KIS 에 닿지 않는다 — respx 가 httpx 전송 계층을 가로챈다.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import httpx
import pytest

import src.auth.token as _token_module
import src.api.balance as bal
from src.api import base
from src.config import settings

pytestmark = pytest.mark.unit

_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"


def _mod():
    return bal


@pytest.fixture
def stub_token(monkeypatch: pytest.MonkeyPatch):
    async def _get_token() -> str:
        return "dummy-access-token"

    def _build_headers(tr_id: str, hashkey: str = "") -> dict[str, str]:
        return {"authorization": "Bearer dummy", "tr_id": tr_id, "custtype": "P"}

    monkeypatch.setattr(_token_module.token_manager, "get_token", _get_token)
    monkeypatch.setattr(_token_module.token_manager, "build_headers", _build_headers)


@pytest.fixture
def mock_write_log(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    import src.db.system_logs as _sl

    mock = AsyncMock(return_value=None)
    monkeypatch.setattr(_sl, "write_log", mock)
    return mock


def _expected_params(
    target_date: str, exchange: str = "ALL", odno: str = "", pdno: str = "",
    fk: str = "", nk: str = "",
) -> list[tuple[str, str]]:
    return [
        ("CANO", settings.kis_account_no),
        ("ACNT_PRDT_CD", settings.kis_account_product),
        ("INQR_STRT_DT", target_date),
        ("INQR_END_DT", target_date),
        ("SLL_BUY_DVSN_CD", "00"),
        ("INQR_DVSN", "00"),
        ("PDNO", pdno),
        ("CCLD_DVSN", "00"),
        ("ORD_GNO_BRNO", ""),
        ("ODNO", odno),
        ("INQR_DVSN_3", "00"),
        ("INQR_DVSN_1", ""),
        ("EXCG_ID_DVSN_CD", exchange),
        ("CTX_AREA_FK100", fk),
        ("CTX_AREA_NK100", nk),
    ]


def _order_row(odno: str = "0000454500", pdno: str = "005930") -> dict:
    return {
        "ord_dt": "20261010", "ord_gno_brno": "06010", "odno": odno, "orgn_odno": "",
        "ord_dvsn_name": "시장가", "sll_buy_dvsn_cd": "02", "sll_buy_dvsn_cd_name": "매수",
        "pdno": pdno, "prdt_name": "삼성전자", "ord_qty": "10", "ord_unpr": "0",
        "ord_tmd": "090030", "tot_ccld_qty": "10", "avg_prvs": "75000",
        "cncl_yn": "", "tot_ccld_amt": "750000", "rmn_qty": "0",
    }


def _body(rows, *, nk: str = "", fk: str = "", rt_cd: str = "0") -> dict:
    msg_cd = "KIOK0510" if rt_cd == "0" else "OPSQ0002"
    msg1 = "조회가 완료되었습니다" if rt_cd == "0" else "없는 서비스 코드 입니다"
    return {
        "rt_cd": rt_cd, "msg_cd": msg_cd, "msg1": msg1,
        "ctx_area_fk100": fk, "ctx_area_nk100": nk,
        "output1": rows,
        "output2": {
            "tot_ord_qty": str(len(rows)), "tot_ccld_qty": "0",
            "tot_ccld_amt": "0", "prsm_tlex_smtl": "0", "pchs_avg_pric": "0",
        },
    }


# ---------------------------------------------------------------------------
# G1 — 한 쪽, params byte 동일
# ---------------------------------------------------------------------------
async def test_g1_single_page_default_params_byte_identical(mock_kis, stub_token):
    route = mock_kis.get(path=_PATH).mock(
        return_value=httpx.Response(200, json=_body([_order_row()]), headers={"tr_cont": "D"})
    )
    out = await bal.get_daily_orders(target_date="20261010")

    assert route.call_count == 1
    req = route.calls[0].request
    assert req.headers["tr_id"] == settings.get_tr_id("TTTC0081R")
    assert "tr_cont" not in req.headers  # 첫 쪽은 헤더 공란
    assert list(dict(req.url.params).items()) == _expected_params("20261010")
    assert out == [_order_row()]


async def test_g1b_exchange_positional_still_works(mock_kis, stub_token):
    route = mock_kis.get(path=_PATH).mock(
        return_value=httpx.Response(200, json=_body([]), headers={"tr_cont": "D"})
    )
    await bal.get_daily_orders("20261010", "KRX")
    assert list(dict(route.calls[0].request.url.params).items()) == _expected_params(
        "20261010", "KRX"
    )


# ---------------------------------------------------------------------------
# G2 — 세 쪽 연결(M/F → D), ctx·tr_cont 왕복
# ---------------------------------------------------------------------------
async def test_g2_three_pages_chain_and_ctx_round_trip(mock_kis, stub_token):
    p1 = httpx.Response(
        200, json=_body([_order_row(odno="1")], nk="NK1", fk="FK1"), headers={"tr_cont": "M"}
    )
    p2 = httpx.Response(
        200, json=_body([_order_row(odno="2")], nk="NK2", fk="FK2"), headers={"tr_cont": "F"}
    )
    p3 = httpx.Response(200, json=_body([_order_row(odno="3")]), headers={"tr_cont": "D"})
    route = mock_kis.get(path=_PATH).mock(side_effect=[p1, p2, p3])

    out = await bal.get_daily_orders(target_date="20261010")

    assert route.call_count == 3
    second = route.calls[1].request
    assert second.headers["tr_cont"] == "N"
    q2 = dict(second.url.params)
    assert q2["CTX_AREA_NK100"] == "NK1"
    assert q2["CTX_AREA_FK100"] == "FK1"

    third = route.calls[2].request
    assert third.headers["tr_cont"] == "N"
    q3 = dict(third.url.params)
    assert q3["CTX_AREA_NK100"] == "NK2"
    assert q3["CTX_AREA_FK100"] == "FK2"

    assert [r["odno"] for r in out] == ["1", "2", "3"]


# ---------------------------------------------------------------------------
# G3a — 쪽수 상한 없음: 50 을 넘는 60쪽도 전부 이어 붙인다
# ---------------------------------------------------------------------------
def _paged_responses(n: int) -> list[httpx.Response]:
    out = []
    for i in range(1, n + 1):
        rows = [_order_row(odno=str(i))]
        if i < n:
            out.append(httpx.Response(
                200, json=_body(rows, nk=f"NK{i}", fk=f"FK{i}"), headers={"tr_cont": "M"}
            ))
        else:
            out.append(httpx.Response(200, json=_body(rows), headers={"tr_cont": "D"}))
    return out


async def test_g3a_many_pages_all_appended_no_cap(mock_kis, stub_token):
    n = 60
    route = mock_kis.get(path=_PATH).mock(side_effect=_paged_responses(n))

    out = await bal.get_daily_orders(target_date="20261010")

    assert route.call_count == n
    assert [r["odno"] for r in out] == [str(i) for i in range(1, n + 1)]


# ---------------------------------------------------------------------------
# G3b — tr_cont=M/F 인데 ctx 가 직전 요청과 똑같다 → 진행 없음 → 예외 + 마커
# ---------------------------------------------------------------------------
async def test_g3b_same_ctx_as_previous_raises_stuck(mock_kis, stub_token, caplog):
    p1 = httpx.Response(
        200, json=_body([_order_row(odno="1")], nk="SAME", fk="SAME"), headers={"tr_cont": "M"}
    )
    p2 = httpx.Response(
        200, json=_body([_order_row(odno="2")], nk="SAME", fk="SAME"), headers={"tr_cont": "M"}
    )
    # 쪽수를 리스트로 제한 — 진행-없음 가드가 없어도 무한 루프 대신 리스트 소진으로 fail.
    route = mock_kis.get(path=_PATH).mock(side_effect=[p1, p2, p2, p2])

    with caplog.at_level(logging.WARNING):
        with pytest.raises(bal.DailyOrdersPaginationStuckError):
            await bal.get_daily_orders(target_date="20261010")

    assert route.call_count == 2  # p1 → p2 까지만, p2 가 cur 과 같아 거기서 멈춘다
    assert "[daily_orders_pagination_stuck]" in caplog.text
    assert "pages=2" in caplog.text


# ---------------------------------------------------------------------------
# G3c — tr_cont=M/F 인데 ctx 둘 다 빈 값 → 진행 없음 → 예외 + 마커
# ---------------------------------------------------------------------------
async def test_g3c_next_flag_but_empty_ctx_raises_stuck(mock_kis, stub_token, caplog):
    p1 = httpx.Response(
        200, json=_body([_order_row(odno="1")], nk="", fk=""), headers={"tr_cont": "M"}
    )
    route = mock_kis.get(path=_PATH).mock(side_effect=[p1, p1, p1])

    with caplog.at_level(logging.WARNING):
        with pytest.raises(bal.DailyOrdersPaginationStuckError):
            await bal.get_daily_orders(target_date="20261010")

    assert route.call_count == 1
    assert "[daily_orders_pagination_stuck]" in caplog.text
    assert "pages=1" in caplog.text


# ---------------------------------------------------------------------------
# G4 — 중간 쪽 rt_cd!=0 → KisApiError 그대로 (부분 결과 없음)
# ---------------------------------------------------------------------------
async def test_g4_error_on_second_page_propagates_not_partial(
    mock_kis, stub_token, mock_write_log
):
    p1 = httpx.Response(200, json=_body([_order_row()], nk="K", fk="F"), headers={"tr_cont": "M"})
    p2 = httpx.Response(200, json=_body([], rt_cd="1"))
    mock_kis.get(path=_PATH).mock(side_effect=[p1, p2])

    with pytest.raises(base.KisApiError) as ei:
        await bal.get_daily_orders(target_date="20261010")
    assert ei.value.msg_cd == "OPSQ0002"


# ---------------------------------------------------------------------------
# G6 — odno/pdno 필터는 모든 쪽에서 유지된다
# ---------------------------------------------------------------------------
async def test_g6_filters_preserved_across_pages(mock_kis, stub_token):
    p1 = httpx.Response(200, json=_body([_order_row()], nk="K", fk="F"), headers={"tr_cont": "M"})
    p2 = httpx.Response(200, json=_body([_order_row()]), headers={"tr_cont": "D"})
    route = mock_kis.get(path=_PATH).mock(side_effect=[p1, p2])

    await bal.get_daily_orders(target_date="20261010", odno="0000454500", pdno="005930")

    assert route.call_count == 2
    for call in route.calls:
        q = dict(call.request.url.params)
        assert q["ODNO"] == "0000454500"
        assert q["PDNO"] == "005930"


# ---------------------------------------------------------------------------
# G7 — 모의(vts) 15행 쪽에서도 같은 연결 동작
# ---------------------------------------------------------------------------
async def test_g7_vts_small_page_pagination(mock_kis, stub_token, monkeypatch):
    monkeypatch.setattr(settings, "kis_env", "vts")
    rows_p1 = [_order_row(odno=str(i)) for i in range(15)]
    rows_p2 = [_order_row(odno="99")]
    p1 = httpx.Response(200, json=_body(rows_p1, nk="K", fk="F"), headers={"tr_cont": "M"})
    p2 = httpx.Response(200, json=_body(rows_p2), headers={"tr_cont": "D"})
    route = mock_kis.get(path=_PATH).mock(side_effect=[p1, p2])

    out = await bal.get_daily_orders(target_date="20261010")

    assert route.call_count == 2
    assert len(out) == 16
