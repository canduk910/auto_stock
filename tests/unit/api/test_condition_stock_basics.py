"""Phase G Red — `condition.inquire_stock_basics(pdno)` (CTPF1002R).

KIS MCP 4질의 결과(2026-05-11) `CTPF1002R` 응답의 두 필드로 종목별 NXT 등록
여부를 사전 조회할 수 있음이 확정됨:

- `cptt_trad_tr_psbl_yn` — NXT 거래종목여부 (Y/N)
- `nxt_tr_stop_yn`        — NXT 거래정지여부 (Y/N)
- **파생값**: `nxt_tradable = (cptt_trad_tr_psbl_yn == "Y") AND (nxt_tr_stop_yn == "N")`

요구 행위:

1. `inquire_stock_basics(pdno)` 가 `StockBasics` Pydantic 모델을 반환한다.
2. `nxt_tradable` 은 위 파생식대로 4가지 Y/N 조합 모두에서 정확히 계산된다.
3. `krx_halted = (tr_stop_yn == "Y")`, `admin_item = (admn_item_yn == "Y")` 도 함께 노출.
4. KIS 호출은 `kis_request()` 경유 — `kis_get` AsyncMock 으로 가로채면 충분.
5. `raw` 필드에 원본 dict 보존 (디버깅용).

테스트 더블:
- `src.api.condition.kis_get` 을 monkeypatch 로 AsyncMock 교체 → CTPF1002R 응답 반환.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


def _make_response(
    *,
    cptt: str,
    nxt_stop: str,
    krx_stop: str = "N",
    admn: str = "N",
    pdno: str = "012200",
    name: str = "계양전기",
    excg: str = "02",  # 02=KOSPI, 03=KOSDAQ (KIS code)
    mket: str = "STK",
) -> dict:
    """CTPF1002R 정상 응답 골격 (rt_cd=0). 검증에 필요한 6개 키만 채운다."""
    return {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "msg1": "정상처리되었습니다.",
        "output": {
            "pdno": pdno,
            "prdt_abrv_name": name,
            "excg_dvsn_cd": excg,
            "mket_id_cd": mket,
            "cptt_trad_tr_psbl_yn": cptt,
            "nxt_tr_stop_yn": nxt_stop,
            "tr_stop_yn": krx_stop,
            "admn_item_yn": admn,
        },
    }


@pytest.mark.parametrize(
    "cptt,nxt_stop,expected",
    [
        ("Y", "N", True),   # 등록 + 미정지 → NXT 거래 가능
        ("Y", "Y", False),  # 등록 + 정지 → 거래 불가
        ("N", "N", False),  # 미등록 → 거래 불가
        ("N", "Y", False),  # 미등록 + 정지 → 거래 불가
    ],
)
@pytest.mark.asyncio
async def test_inquire_stock_basics_parses_nxt_fields(
    monkeypatch: pytest.MonkeyPatch,
    cptt: str,
    nxt_stop: str,
    expected: bool,
):
    """4가지 Y/N 조합에서 nxt_tradable 파생값이 정확하다."""
    from src.api import condition

    mock_get = AsyncMock(return_value=_make_response(cptt=cptt, nxt_stop=nxt_stop))
    monkeypatch.setattr(condition, "kis_get", mock_get)

    result = await condition.inquire_stock_basics("012200")

    assert result.ticker == "012200"
    assert result.nxt_tradable is expected
    # 호출 인자 검증 — CTPF1002R + PDNO
    mock_get.assert_awaited_once()
    args, kwargs = mock_get.call_args
    # kis_get(path, tr_id, params)
    assert "CTPF1002R" in (args[1] if len(args) > 1 else kwargs.get("tr_id", ""))
    params = args[2] if len(args) > 2 else kwargs.get("params", {})
    assert params.get("PDNO") == "012200"


@pytest.mark.asyncio
async def test_inquire_stock_basics_carries_krx_halt_and_admin_flags(
    monkeypatch: pytest.MonkeyPatch,
):
    """`krx_halted` 와 `admin_item` 도 함께 노출되어야 한다."""
    from src.api import condition

    mock_get = AsyncMock(
        return_value=_make_response(
            cptt="Y", nxt_stop="N", krx_stop="Y", admn="Y"
        )
    )
    monkeypatch.setattr(condition, "kis_get", mock_get)

    result = await condition.inquire_stock_basics("012200")

    assert result.krx_halted is True
    assert result.admin_item is True
    # raw dict 보존
    assert result.raw.get("cptt_trad_tr_psbl_yn") == "Y"
    assert result.raw.get("nxt_tr_stop_yn") == "N"


@pytest.mark.asyncio
async def test_inquire_stock_basics_propagates_kis_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """KIS 거부 응답(`KisApiError`) 은 그대로 전파한다 — 호출자가 처리."""
    from src.api import condition
    from src.api.base import KisApiError

    mock_get = AsyncMock(side_effect=KisApiError("1", "MCA00001", "조회 실패"))
    monkeypatch.setattr(condition, "kis_get", mock_get)

    with pytest.raises(KisApiError) as exc:
        await condition.inquire_stock_basics("999999")

    assert exc.value.msg_cd == "MCA00001"
