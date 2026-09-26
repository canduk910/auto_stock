"""cycle379 Red — `get_daily_orders` 에 keyword-only `odno` 추가 (TTTC0081R `ODNO` 필터).

명세 = `_workspace/red/cycle379_buying_reconcile_spec.md` §2.1
실측 = cycle373 §2 — `ODNO=<주문번호>`, `PDNO=""` 로 조회하면 output1 에 그 주문 1행만 온다
(output2 는 필터가 안 걸린 그날 합계). 주문별 조회는 첫 쪽 잘림 위험을 없앤다.

| # | 계약 | HEAD |
|---|---|---|
| D1 | 기본 호출의 params 15키가 **순서까지** 현행과 같다(`ODNO==""`) | GREEN(특성 고정) |
| D2 | `odno=` 는 keyword-only · 기본 `""` | RED |
| D3 | `odno="0000454500"` 는 `ODNO` 한 칸만 바꾼다 | RED |
| D4 | 위치 인자 3개째로는 넘길 수 없다 | RED(현행은 TypeError 가 아니라 인자 수 초과로 같은 결과 — D2 가 본 판정) |
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock

import pytest

import src.api.balance as bal
from src.config import settings

pytestmark = pytest.mark.unit

_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"


def _expected(target_date: str, exchange: str = "ALL", odno: str = "") -> list[tuple[str, str]]:
    return [
        ("CANO", settings.kis_account_no),
        ("ACNT_PRDT_CD", settings.kis_account_product),
        ("INQR_STRT_DT", target_date),
        ("INQR_END_DT", target_date),
        ("SLL_BUY_DVSN_CD", "00"),
        ("INQR_DVSN", "00"),
        ("PDNO", ""),
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
    spy = AsyncMock(return_value={"output1": [{"odno": "0000454500"}]})
    monkeypatch.setattr(bal, "kis_get", spy)
    return spy


def _params(spy: AsyncMock) -> dict:
    args = spy.await_args.args
    assert args[0] == _PATH
    assert args[1] == settings.get_tr_id("TTTC0081R")
    return args[2]


async def test_d1_default_params_are_byte_identical(kis_get: AsyncMock) -> None:
    out = await bal.get_daily_orders(target_date="20260915")
    assert out == [{"odno": "0000454500"}]
    assert list(_params(kis_get).items()) == _expected("20260915")


async def test_d1b_exchange_positional_still_works(kis_get: AsyncMock) -> None:
    await bal.get_daily_orders("20260915", "KRX")
    assert list(_params(kis_get).items()) == _expected("20260915", "KRX")


def test_d2_odno_is_keyword_only_with_empty_default() -> None:
    params = inspect.signature(bal.get_daily_orders).parameters
    assert "odno" in params, "[Red] get_daily_orders(..., *, odno: str = \"\") 미구현"
    p = params["odno"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY, "odno 는 keyword-only (기존 위치 인자 호출부 보호)"
    assert p.default == ""
    assert list(params)[:2] == ["target_date", "exchange"]
    assert params["target_date"].default == "" and params["exchange"].default == "ALL"


async def test_d3_odno_only_changes_the_ODNO_slot(kis_get: AsyncMock) -> None:
    await bal.get_daily_orders(target_date="20260915", odno="0000454500")
    assert list(_params(kis_get).items()) == _expected("20260915", odno="0000454500")


async def test_d4_odno_cannot_be_passed_positionally(kis_get: AsyncMock) -> None:
    assert "odno" in inspect.signature(bal.get_daily_orders).parameters, "[Red] odno 미구현"
    with pytest.raises(TypeError):
        await bal.get_daily_orders("20260915", "ALL", "0000454500")  # type: ignore[call-arg]
