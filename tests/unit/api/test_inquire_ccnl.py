"""사이클 32 (R4, 2026-05-21) — KIS 주식현재가 체결 (`inquire-ccnl`) API.

배경:
- 사이클 29-R3 적용 후 메인 편중 73% → 30% 해소됐으나 stale 종목 자체는 분산만 됨.
- 거래량 빈약한 중소형주 (주성엔지니어링/BHI/디알젬 등 20여 종목) 가 영구 stale 로
  41 슬롯 점유 + R1 force_retry 매 5분 KIS Rate Limit 부담 누적.
- universe 제외 판단을 위해 KIS 당일 최근체결시각 + 누적 거래량 조회 필요.

KIS API 스펙 (사용자가 KIS MCP 로 조회 완료):
- URL: `/uapi/domestic-stock/v1/quotations/inquire-ccnl`
- TR_ID: `FHKST01010300` (실전/모의 동일)
- 파라미터: `FID_COND_MRKT_DIV_CODE=J`, `FID_INPUT_ISCD={ticker}`
- 응답 output 배열 (최근순): `stck_cntg_hour`(HHMMSS), `stck_prpr`, `cntg_vol`, `tday_rltv`, `prdy_ctrt`

본 모듈 (`src/api/quotation.py`) 신규 함수:
- `inquire_ccnl(ticker, market="J") -> dict | None`
- 정상: `{"last_cntg_hour": "HHMMSS", "last_price": int, "last_volume": int, "last_relative_strength": float, "today_volume": int, "raw_count": int}`
- 빈 응답 (오프장 / 거래 없음) / KIS 오류 → None (graceful)

사양 (S1~S8):
- S-1: 정상 응답 → 첫 row 추출 (최근순)
- S-2: 빈 output 배열 → None (graceful)
- S-3: KIS rt_cd 오류 → None (graceful)
- S-4: 6자리 ticker 검증 (5자리 또는 비숫자 ValueError)
- S-5: 호출 path + TR_ID 정확성
- S-6: market 파라미터 (J/NX/UN) 적용
- S-7: today_volume = output 배열 cntg_vol 합산
- S-8: kis_get_quote 경유 (보조 풀 라우팅)
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — kis_get_quote mock
# ---------------------------------------------------------------------------
def _make_response(output_rows: list[dict], rt_cd: str = "0", msg1: str = "정상") -> dict:
    """KIS inquire-ccnl 응답 형식."""
    return {
        "rt_cd": rt_cd,
        "msg_cd": "OK" if rt_cd == "0" else "ERR",
        "msg1": msg1,
        "output": output_rows,
    }


@pytest.fixture
def spy_quote_get(monkeypatch):
    """`kis_get_quote` 를 AsyncMock 으로 교체."""
    from src.api import base as base_mod

    spy = AsyncMock()
    monkeypatch.setattr(base_mod, "kis_get_quote", spy, raising=False)
    # quotation 모듈도 동일 spy 사용 (import 시점에 따라 한쪽만 패치되는 결함 차단)
    try:
        from src.api import quotation as quot_mod
        monkeypatch.setattr(quot_mod, "kis_get_quote", spy, raising=False)
    except ImportError:
        pass
    return spy


# ===========================================================================
# S-1: 정상 응답 → 첫 row 추출 (최근순)
# ===========================================================================
@pytest.mark.asyncio
async def test_inquire_ccnl_parses_first_output_row(spy_quote_get):
    """`output` 배열 첫 row (최근 체결) 를 dict 로 추출."""
    spy_quote_get.return_value = _make_response([
        {
            "stck_cntg_hour": "091342",  # 09:13:42
            "stck_prpr": "75000",
            "cntg_vol": "120",
            "tday_rltv": "82.5",
            "prdy_ctrt": "-0.25",
        },
        {
            "stck_cntg_hour": "091330",
            "stck_prpr": "75100",
            "cntg_vol": "50",
            "tday_rltv": "85.0",
            "prdy_ctrt": "-0.13",
        },
    ])

    from src.api.quotation import inquire_ccnl
    result = await inquire_ccnl("005930")

    assert result is not None
    assert result["last_cntg_hour"] == "091342"
    assert result["last_price"] == 75000
    assert result["last_volume"] == 120
    assert result["last_relative_strength"] == 82.5


# ===========================================================================
# S-2: 빈 output 배열 → None (오프장 / 거래 없음)
# ===========================================================================
@pytest.mark.asyncio
async def test_inquire_ccnl_returns_none_for_empty_output(spy_quote_get):
    """`output` 빈 배열 → None (graceful)."""
    spy_quote_get.return_value = _make_response([])

    from src.api.quotation import inquire_ccnl
    result = await inquire_ccnl("005930")

    assert result is None


# ===========================================================================
# S-3: KIS rt_cd 오류 → None (graceful)
# ===========================================================================
@pytest.mark.asyncio
async def test_inquire_ccnl_returns_none_for_kis_error(spy_quote_get):
    """`rt_cd != "0"` 또는 응답 자체 None → None (graceful)."""
    # kis_get_quote 가 None 반환 (예외 흡수 후)
    spy_quote_get.return_value = None

    from src.api.quotation import inquire_ccnl
    result = await inquire_ccnl("005930")

    assert result is None


@pytest.mark.asyncio
async def test_inquire_ccnl_returns_none_when_exception_raised(spy_quote_get):
    """`kis_get_quote` 가 예외 → None (graceful, 외부 호출자 보호)."""
    spy_quote_get.side_effect = RuntimeError("KIS API timeout")

    from src.api.quotation import inquire_ccnl
    result = await inquire_ccnl("005930")

    assert result is None


# ===========================================================================
# S-4: ticker 형식 검증 (6자리 숫자/영숫자)
# ===========================================================================
@pytest.mark.asyncio
async def test_inquire_ccnl_rejects_invalid_ticker_format(spy_quote_get):
    """5자리 ticker → ValueError."""
    from src.api.quotation import inquire_ccnl
    with pytest.raises(ValueError, match="ticker"):
        await inquire_ccnl("12345")  # 5자리

    # spy 호출 없어야 함 (사전 가드)
    spy_quote_get.assert_not_called()


@pytest.mark.asyncio
async def test_inquire_ccnl_rejects_empty_ticker(spy_quote_get):
    """빈 ticker → ValueError."""
    from src.api.quotation import inquire_ccnl
    with pytest.raises(ValueError, match="ticker"):
        await inquire_ccnl("")
    spy_quote_get.assert_not_called()


# ===========================================================================
# S-5: 호출 path + TR_ID 정확성
# ===========================================================================
@pytest.mark.asyncio
async def test_inquire_ccnl_calls_correct_path_and_tr_id(spy_quote_get):
    """`/uapi/domestic-stock/v1/quotations/inquire-ccnl` + TR_ID `FHKST01010300`."""
    spy_quote_get.return_value = _make_response([
        {"stck_cntg_hour": "091342", "stck_prpr": "75000", "cntg_vol": "100",
         "tday_rltv": "80.0", "prdy_ctrt": "-0.1"},
    ])

    from src.api.quotation import inquire_ccnl
    await inquire_ccnl("005930")

    # call_args: (path, tr_id, params)
    args = spy_quote_get.await_args.args
    assert args[0] == "/uapi/domestic-stock/v1/quotations/inquire-ccnl", (
        f"path 오류 — 실제={args[0]}"
    )
    # TR_ID FHKST01010300 (모의/실전 동일)
    assert args[1] == "FHKST01010300", f"TR_ID 오류 — 실제={args[1]}"


# ===========================================================================
# S-6: market 파라미터 (J=KRX 기본 / NX=NXT / UN=통합)
# ===========================================================================
@pytest.mark.asyncio
async def test_inquire_ccnl_default_market_is_J_krx(spy_quote_get):
    """기본 market=J (KRX)."""
    spy_quote_get.return_value = _make_response([
        {"stck_cntg_hour": "091342", "stck_prpr": "75000", "cntg_vol": "100",
         "tday_rltv": "80.0", "prdy_ctrt": "-0.1"},
    ])

    from src.api.quotation import inquire_ccnl
    await inquire_ccnl("005930")

    params = spy_quote_get.await_args.args[2]
    assert params.get("fid_cond_mrkt_div_code") == "J"
    assert params.get("fid_input_iscd") == "005930"


@pytest.mark.asyncio
async def test_inquire_ccnl_custom_market_nxt(spy_quote_get):
    """market='NX' 시 NXT 시장 조회."""
    spy_quote_get.return_value = _make_response([
        {"stck_cntg_hour": "091342", "stck_prpr": "75000", "cntg_vol": "100",
         "tday_rltv": "80.0", "prdy_ctrt": "-0.1"},
    ])

    from src.api.quotation import inquire_ccnl
    await inquire_ccnl("005930", market="NX")

    params = spy_quote_get.await_args.args[2]
    assert params.get("fid_cond_mrkt_div_code") == "NX"


# ===========================================================================
# S-7: today_volume = output 배열 cntg_vol 합산
# ===========================================================================
@pytest.mark.asyncio
async def test_inquire_ccnl_sums_today_volume(spy_quote_get):
    """`today_volume` 은 응답 output 배열 모든 row 의 `cntg_vol` 합산."""
    spy_quote_get.return_value = _make_response([
        {"stck_cntg_hour": "091342", "stck_prpr": "75000", "cntg_vol": "120",
         "tday_rltv": "80.0", "prdy_ctrt": "-0.1"},
        {"stck_cntg_hour": "091330", "stck_prpr": "75100", "cntg_vol": "50",
         "tday_rltv": "85.0", "prdy_ctrt": "-0.13"},
        {"stck_cntg_hour": "091000", "stck_prpr": "75200", "cntg_vol": "300",
         "tday_rltv": "90.0", "prdy_ctrt": "0.0"},
    ])

    from src.api.quotation import inquire_ccnl
    result = await inquire_ccnl("005930")

    assert result is not None
    assert result["today_volume"] == 470, (
        f"today_volume = 120 + 50 + 300 = 470. 실제={result['today_volume']}"
    )
    assert result["raw_count"] == 3


# ===========================================================================
# S-8: kis_get_quote 경유 (보조 풀 라우팅) + path 화이트리스트 등록
# ===========================================================================
def test_inquire_ccnl_path_in_quote_pool_whitelist():
    """`_QUOTE_ALLOWED_PATHS` 에 `/uapi/domestic-stock/v1/quotations/inquire-ccnl` 등록."""
    from src.api.base import _QUOTE_ALLOWED_PATHS
    assert "/uapi/domestic-stock/v1/quotations/inquire-ccnl" in _QUOTE_ALLOWED_PATHS, (
        "inquire-ccnl path 가 시세 풀 화이트리스트 미등록 — QuotePoolPathError 발생"
    )
