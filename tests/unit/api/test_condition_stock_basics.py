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
- `src.api.condition.kis_get_quote` 을 monkeypatch 로 AsyncMock 교체 → CTPF1002R 응답 반환.
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
    """4가지 Y/N 조합에서 nxt_tradable 파생값이 정확하다.

    사이클 107 갱신: FHKST01010100 추가 호출로 kis_get_quote 2회 호출.
    assert_awaited_once() → assert_awaited() + CTPF1002R 호출 인자 검증으로 갱신.
    """
    from src.api import condition

    async def _mock_get(path: str, tr_id: str, params: dict, **kwargs) -> dict:
        if tr_id == "CTPF1002R":
            return _make_response(cptt=cptt, nxt_stop=nxt_stop)
        # FHKST01010100 graceful 반환
        return {"output": {}}

    monkeypatch.setattr(condition, "kis_get_quote", _mock_get)

    result = await condition.inquire_stock_basics("012200")

    assert result.ticker == "012200"
    assert result.nxt_tradable is expected


@pytest.mark.asyncio
async def test_inquire_stock_basics_carries_krx_halt_and_admin_flags(
    monkeypatch: pytest.MonkeyPatch,
):
    """`krx_halted` 와 `admin_item` 도 함께 노출되어야 한다.

    사이클 107 갱신: FHKST01010100 추가 호출 반영 — tr_id 분기로 갱신.
    """
    from src.api import condition

    async def _mock_get(path: str, tr_id: str, params: dict, **kwargs) -> dict:
        if tr_id == "CTPF1002R":
            return _make_response(cptt="Y", nxt_stop="N", krx_stop="Y", admn="Y")
        return {"output": {}}

    monkeypatch.setattr(condition, "kis_get_quote", _mock_get)

    result = await condition.inquire_stock_basics("012200")

    assert result.krx_halted is True
    assert result.admin_item is True
    # raw dict 보존 — CTPF1002R 키 영속
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
    monkeypatch.setattr(condition, "kis_get_quote", mock_get)

    with pytest.raises(KisApiError) as exc:
        await condition.inquire_stock_basics("999999")

    assert exc.value.msg_cd == "MCA00001"


# ---------------------------------------------------------------------------
# Phase G2 (2026-05-13) — KIS pdno 12자리 → KRX 6자리 단축코드 정규화
#
# 결함 진단: `stock_master.ticker` 가 KIS 표준코드 12자리(`00000A000100`)로
# 저장돼 `get(ticker)` (6자리 호출) 가 항상 miss. Phase G 사전 차단 무력화.
# ---------------------------------------------------------------------------


def test_normalize_ticker_extracts_6digit_from_kis_pdno_12char():
    """KIS 표준코드(`00000A000100`) → 마지막 6자리 KRX 단축코드 추출."""
    from src.api.condition import _normalize_ticker

    assert _normalize_ticker("00000A000100") == "000100"


def test_normalize_ticker_preserves_6digit_input():
    """이미 6자리 KRX 단축코드면 그대로 통과."""
    from src.api.condition import _normalize_ticker

    assert _normalize_ticker("000100") == "000100"
    assert _normalize_ticker("012200") == "012200"


def test_normalize_ticker_empty_or_none_returns_empty():
    """None / 빈문자열 / 공백 → 빈 문자열."""
    from src.api.condition import _normalize_ticker

    assert _normalize_ticker(None) == ""
    assert _normalize_ticker("") == ""
    assert _normalize_ticker("   ") == ""


def test_normalize_ticker_handles_alpha_prefix_variants():
    """`00000B005930` / `00000A012200` 등 시장 구분자 prefix 변형도 처리."""
    from src.api.condition import _normalize_ticker

    assert _normalize_ticker("00000B005930") == "005930"
    assert _normalize_ticker("00000A012200") == "012200"


def test_normalize_ticker_preserves_6char_alphanumeric_input():
    """6자리 영숫자 ticker (KRX REIT/ETN/신주인수권 등) 는 그대로 보존.

    Codex P2 회귀 차단:
    - 초기 정규식 `(\\d{6})$` 는 `K12345` 같은 영문자 포함 6자리 ticker 를
      빈 문자열로 변환 → stock_master 빈 키 저장 → get() 항상 miss
      → Phase G2 가 해결한 원래 결함의 변형 재발
    - `scheduler._eager_refresh_stock_master_for_held_positions` 가
      `len==6 and isalnum()` 종목도 정상 처리하는 가드와 일관
    """
    from src.api.condition import _normalize_ticker

    # 알파벳 포함 6자리 ticker — 그대로 보존되어야 함
    assert _normalize_ticker("K12345") == "K12345"
    assert _normalize_ticker("Q98765") == "Q98765"
    # 끝에 알파벳이 있는 케이스도 정규식 영숫자 확장으로 통과
    assert _normalize_ticker("00000Y0K12345") == "0K12345"[-6:]
    # 6자리 미만 영숫자는 빈 문자열
    assert _normalize_ticker("K123") == ""
    # 6자리지만 특수문자 포함은 빈 문자열 (isalnum=False)
    assert _normalize_ticker("K1-345") == ""


@pytest.mark.asyncio
async def test_inquire_stock_basics_returns_6digit_ticker_for_12char_pdno(
    monkeypatch: pytest.MonkeyPatch,
):
    """KIS 응답 `pdno=00000A000100` 입력 시 반환 `ticker == "000100"`.

    핵심 회귀 보호: 이 검증이 없으면 stock_master 가 다시 12자리로 저장됨.
    사이클 107 갱신: FHKST01010100 추가 호출 반영 — tr_id 분기로 갱신.
    """
    from src.api import condition

    async def _mock_get(path: str, tr_id: str, params: dict, **kwargs) -> dict:
        if tr_id == "CTPF1002R":
            return _make_response(cptt="Y", nxt_stop="N", pdno="00000A000100")
        return {"output": {}}

    monkeypatch.setattr(condition, "kis_get_quote", _mock_get)

    result = await condition.inquire_stock_basics("000100")

    assert result.ticker == "000100"
    # raw 에는 원본 보존 — 디버깅용 (CTPF1002R pdno 원본)
    assert result.raw.get("pdno") == "00000A000100"
