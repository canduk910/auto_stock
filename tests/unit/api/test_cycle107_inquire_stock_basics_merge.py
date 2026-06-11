"""사이클 107 — inquire_stock_basics CTPF1002R + FHKST01010100 merge 회귀 가드.

HIGH-1: 두 API 양쪽 모두 호출 영속 확인 (mock 양쪽 검증)
HIGH-2: raw 에 3 키 (acml_tr_pbmn / lstn_stcn / acml_vol) 포함 영속 확인
HIGH-3: FHKST01010100 실패 시 graceful — CTPF1002R 단독 raw 반환 영속 확인

KIS 정본 인용 (chk_inquire_price.py main 호출 영역):
- TR_ID: FHKST01010100 (모의/실전 동일)
- URL: /uapi/domestic-stock/v1/quotations/inquire-price
- FID_COND_MRKT_DIV_CODE: "J"
- FID_INPUT_ISCD: 종목코드

사이클 81 G-AST1 영속 의무:
- CTPF1002R bfdy_clpr 는 ctpf_output 에서 merged_raw 로 영속 통과
- FHKST01010100 키가 CTPF1002R 기존 키 덮어쓰기 금지
"""

from __future__ import annotations

from unittest.mock import AsyncMock, call, patch

import pytest

pytestmark = pytest.mark.unit


def _ctpf_response(pdno: str = "005930") -> dict:
    """CTPF1002R 정상 응답 골격 — NXT 거래가능 + bfdy_clpr 포함."""
    return {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "msg1": "정상처리되었습니다.",
        "output": {
            "pdno": pdno,
            "prdt_abrv_name": "삼성전자",
            "excg_dvsn_cd": "02",
            "cptt_trad_tr_psbl_yn": "Y",
            "nxt_tr_stop_yn": "N",
            "tr_stop_yn": "N",
            "admn_item_yn": "N",
            # 사이클 81 G-AST1 영속: bfdy_clpr 는 CTPF1002R 에서 반드시 보존
            "bfdy_clpr": "85000",
        },
    }


def _price_response(pdno: str = "005930") -> dict:
    """FHKST01010100 정상 응답 골격 — 3 키 포함."""
    return {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "msg1": "정상처리되었습니다.",
        "output": {
            "stck_prpr": "85200",
            "acml_tr_pbmn": "1234567890000",
            "lstn_stcn": "5969782550",
            "acml_vol": "23456789",
            "prdy_vrss": "200",
        },
    }


# ---------------------------------------------------------------------------
# HIGH-1: 양쪽 API 호출 영속 확인
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_high1_both_apis_called(monkeypatch: pytest.MonkeyPatch) -> None:
    """HIGH-1: CTPF1002R + FHKST01010100 양쪽 모두 호출되어야 한다."""
    from src.api import condition

    call_log: list[tuple] = []

    async def _mock_get_quote(path: str, tr_id: str, params: dict, **kwargs) -> dict:
        call_log.append((path, tr_id))
        if tr_id == "CTPF1002R":
            return _ctpf_response()
        if tr_id == "FHKST01010100":
            return _price_response()
        return {}

    monkeypatch.setattr(condition, "kis_get_quote", _mock_get_quote)

    result = await condition.inquire_stock_basics("005930")

    tr_ids = [t for _, t in call_log]
    assert "CTPF1002R" in tr_ids, "CTPF1002R 호출 누락"
    assert "FHKST01010100" in tr_ids, "FHKST01010100 호출 누락"
    assert result.ticker == "005930"


@pytest.mark.asyncio
async def test_high1_ctpf_called_before_price(monkeypatch: pytest.MonkeyPatch) -> None:
    """HIGH-1: CTPF1002R 가 FHKST01010100 보다 먼저 호출되어야 한다 (순서 영속)."""
    from src.api import condition

    call_order: list[str] = []

    async def _mock_get_quote(path: str, tr_id: str, params: dict, **kwargs) -> dict:
        call_order.append(tr_id)
        if tr_id == "CTPF1002R":
            return _ctpf_response()
        return _price_response()

    monkeypatch.setattr(condition, "kis_get_quote", _mock_get_quote)

    await condition.inquire_stock_basics("005930")

    assert call_order.index("CTPF1002R") < call_order.index("FHKST01010100"), (
        "CTPF1002R 가 FHKST01010100 보다 먼저 호출되어야 한다"
    )


# ---------------------------------------------------------------------------
# HIGH-2: raw 3 키 포함 영속 확인
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_high2_three_keys_in_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    """HIGH-2: raw 에 acml_tr_pbmn / lstn_stcn / acml_vol 포함 영속."""
    from src.api import condition

    async def _mock_get_quote(path: str, tr_id: str, params: dict, **kwargs) -> dict:
        if tr_id == "CTPF1002R":
            return _ctpf_response()
        return _price_response()

    monkeypatch.setattr(condition, "kis_get_quote", _mock_get_quote)

    result = await condition.inquire_stock_basics("005930")

    assert "acml_tr_pbmn" in result.raw, "raw 에 acml_tr_pbmn 누락"
    assert "lstn_stcn" in result.raw, "raw 에 lstn_stcn 누락"
    assert "acml_vol" in result.raw, "raw 에 acml_vol 누락"
    assert result.raw["acml_tr_pbmn"] == "1234567890000"
    assert result.raw["lstn_stcn"] == "5969782550"
    assert result.raw["acml_vol"] == "23456789"


@pytest.mark.asyncio
async def test_high2_ctpf_keys_preserved_in_merged_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HIGH-2: CTPF1002R 67 컬럼 영속 — bfdy_clpr 가 merged_raw 에 보존되어야 한다.

    사이클 81 G-AST1 영속 의무: bfdy_clpr 는 CTPF1002R 에서 온 키.
    FHKST01010100 merge 후에도 손실 없이 raw 에 남아야 한다.
    """
    from src.api import condition

    async def _mock_get_quote(path: str, tr_id: str, params: dict, **kwargs) -> dict:
        if tr_id == "CTPF1002R":
            return _ctpf_response()
        return _price_response()

    monkeypatch.setattr(condition, "kis_get_quote", _mock_get_quote)

    result = await condition.inquire_stock_basics("005930")

    # 사이클 81 G-AST1 영속: bfdy_clpr 가 raw 에 남아야 한다
    assert "bfdy_clpr" in result.raw, "raw 에 bfdy_clpr 누락 (사이클 81 G-AST1 위반)"
    assert result.raw["bfdy_clpr"] == "85000"


@pytest.mark.asyncio
async def test_high2_fhkst_does_not_overwrite_ctpf_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HIGH-2: FHKST01010100 키가 CTPF1002R 기존 키를 덮어쓰지 않는다."""
    from src.api import condition

    # CTPF1002R 에 이미 bfdy_clpr = "85000" 존재
    # FHKST01010100 에도 bfdy_clpr 를 다른 값으로 설정 (덮어쓰기 테스트)
    ctpf_resp = _ctpf_response()
    price_resp = _price_response()
    price_resp["output"]["bfdy_clpr"] = "99999"  # CTPF 값과 다름

    async def _mock_get_quote(path: str, tr_id: str, params: dict, **kwargs) -> dict:
        if tr_id == "CTPF1002R":
            return ctpf_resp
        return price_resp

    monkeypatch.setattr(condition, "kis_get_quote", _mock_get_quote)

    result = await condition.inquire_stock_basics("005930")

    # CTPF1002R 의 bfdy_clpr 가 보존되어야 함 (FHKST 값으로 덮어쓰기 금지)
    assert result.raw.get("bfdy_clpr") == "85000", (
        "FHKST01010100 키가 CTPF1002R 기존 키를 덮어써서는 안 된다"
    )


# ---------------------------------------------------------------------------
# HIGH-3: FHKST01010100 실패 시 graceful
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_high3_graceful_on_price_api_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HIGH-3: FHKST01010100 실패 시 CTPF1002R 단독 raw 반환 영속.

    매매 안전성: FHKST 일시 장애 시에도 inquire_stock_basics 는 정상 반환.
    nxt_tradable / krx_halted / admin_item 은 CTPF1002R 에서 판별 — 영향 없음.
    """
    from src.api import condition

    async def _mock_get_quote(path: str, tr_id: str, params: dict, **kwargs) -> dict:
        if tr_id == "CTPF1002R":
            return _ctpf_response()
        raise RuntimeError("FHKST01010100 네트워크 실패 시뮬레이션")

    monkeypatch.setattr(condition, "kis_get_quote", _mock_get_quote)

    # 예외 전파 없이 정상 반환되어야 함
    result = await condition.inquire_stock_basics("005930")

    assert result is not None, "FHKST 실패 시 None 반환 금지 (graceful)"
    assert result.ticker == "005930"
    # CTPF1002R 키는 보존
    assert "bfdy_clpr" in result.raw
    # FHKST 3 키는 없어도 무방 (graceful fallback)
    assert result.nxt_tradable is True  # CTPF1002R 판별 영속


@pytest.mark.asyncio
async def test_high3_graceful_on_price_api_kis_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HIGH-3: FHKST01010100 KisApiError 시에도 graceful 반환 영속."""
    from src.api import condition
    from src.api.base import KisApiError

    async def _mock_get_quote(path: str, tr_id: str, params: dict, **kwargs) -> dict:
        if tr_id == "CTPF1002R":
            return _ctpf_response()
        raise KisApiError("1", "EGW00001", "시세 조회 실패")

    monkeypatch.setattr(condition, "kis_get_quote", _mock_get_quote)

    result = await condition.inquire_stock_basics("005930")

    assert result is not None, "KisApiError 시 None 반환 금지 (graceful)"
    assert result.ticker == "005930"
    assert result.nxt_tradable is True


@pytest.mark.asyncio
async def test_high3_ctpf_error_still_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HIGH-3 경계: CTPF1002R 실패는 여전히 예외 전파 (graceful 대상 아님)."""
    from src.api import condition
    from src.api.base import KisApiError

    async def _mock_get_quote(path: str, tr_id: str, params: dict, **kwargs) -> dict:
        if tr_id == "CTPF1002R":
            raise KisApiError("1", "MCA00001", "종목 조회 실패")
        return _price_response()

    monkeypatch.setattr(condition, "kis_get_quote", _mock_get_quote)

    with pytest.raises(KisApiError) as exc:
        await condition.inquire_stock_basics("005930")

    assert exc.value.msg_cd == "MCA00001"
