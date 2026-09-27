"""cycle385 부록 R-1-7 — `get_daily_orders` 에 keyword-only `pdno` 추가 (TR28).

명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md` 부록 R-1-7
선례 = `tests/unit/api/test_cycle379_daily_orders_odno.py` (cycle379 `odno=` · D1 byte 동일 가드)

#1.5 재대조가 그 종목 매도 주문의 누적 체결(`tot_ccld_qty`)을 읽을 때 `PDNO=<종목>` 으로 좁힌다.
**기본값 호출의 params 는 순서까지 직전과 같다**(`PDNO == ""`) — `buying_reconcile`·동기화 등
기존 호출부의 요청이 바뀌면 안 된다.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

import pytest

import src.api.balance as bal
from src.config import settings

pytestmark = pytest.mark.unit

_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"


def _expected(target_date: str, exchange: str = "ALL", odno: str = "", pdno: str = "") -> list:
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
        ("CTX_AREA_FK100", ""),
        ("CTX_AREA_NK100", ""),
    ]


@pytest.fixture
def kis_get(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    spy = AsyncMock(return_value={"output1": [{"odno": "0000031001"}]})
    monkeypatch.setattr(bal, "kis_get", spy)
    return spy


def _params(spy: AsyncMock) -> dict:
    args = spy.await_args.args
    assert args[0] == _PATH
    assert args[1] == settings.get_tr_id("TTTC0081R")
    return args[2]


def test_tr28_pdno_is_keyword_only_with_empty_default() -> None:
    """🔴 TR28 — `pdno` 는 keyword-only · 기본 `""` · 앞 두 위치 인자 무변경."""
    params = inspect.signature(bal.get_daily_orders).parameters
    assert "pdno" in params, "[Red] get_daily_orders(..., *, odno=\"\", pdno=\"\") 미구현"
    p = params["pdno"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY
    assert p.default == ""
    assert list(params)[:2] == ["target_date", "exchange"]
    assert params["odno"].kind is inspect.Parameter.KEYWORD_ONLY


async def test_tr28b_default_call_params_are_byte_identical(kis_get: AsyncMock) -> None:
    """🔵 TR28b — 기본 호출은 직전과 byte 동일(`PDNO: ""`, 키 순서 포함)."""
    await bal.get_daily_orders(target_date="20260928")
    assert list(_params(kis_get).items()) == _expected("20260928")


async def test_tr28c_pdno_only_changes_the_PDNO_slot(kis_get: AsyncMock) -> None:
    """🔴 TR28c — `pdno="005930"` 은 `PDNO` 한 칸만 바꾼다(매도 필터는 클라이언트 — `SLL_BUY_DVSN_CD="00"` 유지)."""
    await bal.get_daily_orders(target_date="20260928", exchange="ALL", pdno="005930")
    assert list(_params(kis_get).items()) == _expected("20260928", pdno="005930")
