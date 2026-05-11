"""Phase A Red — KIS 거부 응답을 system_logs 에 영구 저장한다.

2026-05-11 계양전기(012200) "시장가매매불가" 거부의 정확한 msg_cd/msg1/요청 컨텍스트를
컨테이너 로그(휘발) 가 아닌 DB 에 남겨 다음 거부부터 즉시 추적 가능하도록 한다.

요구 행위 (`src/api/base.py::_request` 의 `rt_cd != "0"` 분기):

1. KIS 가 거부 응답을 돌려보내면 `KisApiError` raise *전* 에
   `src/db/system_logs.py::write_log` 를 호출해 영구 저장한다.
2. 저장 메시지/컨텍스트에는 다음이 포함된다:
   - `path`        (요청 URL path)
   - `tr_id`
   - `msg_cd` / `msg1`
   - body 주요 키 값: `PDNO`, `ORD_DVSN`, `ORD_UNPR`, `ORD_QTY`,
     `EXCG_ID_DVSN_CD`, `SLL_BUY_DVSN_CD`
3. **민감 키 마스킹**: 계좌 식별자(`CANO`, `ACNT_PRDT_CD`) 는 저장 메시지에 포함되지 않는다.
4. 저장 호출이 실패해도 `KisApiError` raise 흐름은 보존된다 (fire-and-forget).
5. 거부 응답은 호출자에게 여전히 `KisApiError` 로 전달된다.

테스트 더블:
- KIS REST 는 respx 로 거부 응답 모킹.
- `token_manager.get_token` 은 monkeypatch 로 더미 토큰 반환.
- `write_log` 은 AsyncMock 으로 가로채 호출 인자 검증.

write_log 시그니처(`(log_level, message)`) 는 현재 단순 2-인자라 메타데이터를
어떻게 직렬화할지(JSON in message, 또는 신규 키워드 인자) 는 backend-dev 결정.
이 테스트는 **호출 발생 + 핵심 정보가 어떤 인자에서든 등장하는지** 만 검증해
구현 자유도를 남긴다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.api import base
from src.api.base import KisApiError, kis_post
from src.auth import token as _token_module

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 공용 헬퍼
# ---------------------------------------------------------------------------
def _join_call_args(call) -> str:
    """write_log 호출의 모든 positional/keyword 인자를 한 줄 문자열로 합쳐
    "어떤 인자에서든 키워드가 등장하는지" 검사할 수 있게 한다.
    """
    parts: list[str] = []
    for a in call.args:
        parts.append(str(a))
    for v in call.kwargs.values():
        parts.append(str(v))
    return " | ".join(parts)


@pytest.fixture
def stub_token(monkeypatch: pytest.MonkeyPatch):
    """token_manager 가 KIS 호출 없이 더미 헤더를 돌려보내도록 stub."""

    async def _get_token() -> str:
        return "dummy-access-token"

    def _build_headers(tr_id: str, hashkey: str = "") -> dict[str, str]:
        return {
            "authorization": "Bearer dummy",
            "appkey": "test-key",
            "appsecret": "test-secret",
            "tr_id": tr_id,
            "custtype": "P",
        }

    monkeypatch.setattr(_token_module.token_manager, "get_token", _get_token)
    monkeypatch.setattr(_token_module.token_manager, "build_headers", _build_headers)
    return None


@pytest.fixture
def mock_write_log(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """`src.api.base` 가 참조하는 write_log 를 AsyncMock 으로 교체.

    base.py 가 어느 경로(`from src.db.system_logs import write_log`,
    `import src.db.system_logs as _sl; _sl.write_log`, 또는 lazy import 등)로
    호출하든 가로채도록 원본 모듈 경로 + base 모듈 attribute 둘 다 패치.
    """
    mock = AsyncMock(return_value=None)

    # 원본 위치
    import src.db.system_logs as _system_logs_mod

    monkeypatch.setattr(_system_logs_mod, "write_log", mock)

    # base 모듈에서 이미 from-import 되어 있다면 동일 attribute 교체
    if hasattr(base, "write_log"):
        monkeypatch.setattr(base, "write_log", mock, raising=False)
    return mock


_ORDER_CASH_PATH = "/uapi/domestic-stock/v1/trading/order-cash"

_REJECTION_RESPONSE = {
    "rt_cd": "1",
    "msg_cd": "APBK0123",
    "msg1": "시장가매매불가 종목입니다.",
    "output": {},
}

# 주문 body 샘플 — 계양전기 시장가 매수 요청 재현
_REQUEST_BODY = {
    "CANO": "12345678",
    "ACNT_PRDT_CD": "01",
    "PDNO": "012200",
    "ORD_DVSN": "01",
    "ORD_QTY": "10",
    "ORD_UNPR": "0",
    "EXCG_ID_DVSN_CD": "SOR",
    "SLL_BUY_DVSN_CD": "02",
}


# ---------------------------------------------------------------------------
# 1. 거부 응답 시 write_log 가 호출된다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_request_when_kis_rejects_then_writes_log(
    mock_kis,
    stub_token,
    mock_write_log,
):
    """KIS 가 rt_cd=1 거부 응답을 돌려보내면 write_log 가 정확히 1회 호출된다."""
    mock_kis.post(f"https://example.test{_ORDER_CASH_PATH}").respond(
        json=_REJECTION_RESPONSE
    )

    # base.py 는 settings.kis_base_url 을 사용하므로 monkeypatch 하지 말고
    # respx 가 host-agnostic 으로 path 매칭하도록 정규식을 한 번 더 등록한다.
    import re

    mock_kis.post(re.compile(rf".*{re.escape(_ORDER_CASH_PATH)}$")).respond(
        json=_REJECTION_RESPONSE
    )

    with pytest.raises(KisApiError):
        await kis_post(_ORDER_CASH_PATH, "TTTC0012U", _REQUEST_BODY)

    assert mock_write_log.await_count >= 1, "거부 응답 시 write_log 가 호출되어야 한다"


# ---------------------------------------------------------------------------
# 2. 로그 페이로드에 핵심 컨텍스트가 포함된다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_request_when_kis_rejects_then_log_includes_context(
    mock_kis,
    stub_token,
    mock_write_log,
):
    """저장 메시지에 path/tr_id/msg_cd/msg1/주요 body 키 값이 포함된다."""
    import re

    mock_kis.post(re.compile(rf".*{re.escape(_ORDER_CASH_PATH)}$")).respond(
        json=_REJECTION_RESPONSE
    )

    with pytest.raises(KisApiError):
        await kis_post(_ORDER_CASH_PATH, "TTTC0012U", _REQUEST_BODY)

    assert mock_write_log.await_count >= 1
    # 마지막(또는 유일한) 호출의 모든 인자를 한 덩어리 문자열로 검사
    joined = _join_call_args(mock_write_log.await_args)

    # 필수 컨텍스트
    assert _ORDER_CASH_PATH in joined, f"path 누락: {joined}"
    assert "TTTC0012U" in joined, f"tr_id 누락: {joined}"
    assert "APBK0123" in joined, f"msg_cd 누락: {joined}"
    assert "시장가매매불가" in joined, f"msg1 누락: {joined}"

    # 요청 body 주요 키 (값으로 비교 — 어느 직렬화 방식이든 포함되어야 함)
    assert "012200" in joined, f"PDNO 누락: {joined}"     # 계양전기 종목코드
    assert "SOR" in joined, f"EXCG_ID_DVSN_CD 누락: {joined}"
    # ORD_DVSN/ORD_QTY/ORD_UNPR/SLL_BUY_DVSN_CD 는 키 이름 또는 값 어느 쪽으로든 등장해야 함
    # 값은 "01"/"10"/"0"/"02" 처럼 짧아 다른 토큰과 충돌 가능 → 키 이름 기준 검사
    for required_key in (
        "ORD_DVSN",
        "ORD_QTY",
        "ORD_UNPR",
        "SLL_BUY_DVSN_CD",
    ):
        assert required_key in joined, f"{required_key} 누락: {joined}"


# ---------------------------------------------------------------------------
# 3. 민감 키 마스킹
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_request_when_kis_rejects_then_log_masks_account_identifiers(
    mock_kis,
    stub_token,
    mock_write_log,
):
    """CANO / ACNT_PRDT_CD 는 로그 메시지에 포함되지 않는다 (계좌번호 노출 방지)."""
    import re

    mock_kis.post(re.compile(rf".*{re.escape(_ORDER_CASH_PATH)}$")).respond(
        json=_REJECTION_RESPONSE
    )

    with pytest.raises(KisApiError):
        await kis_post(_ORDER_CASH_PATH, "TTTC0012U", _REQUEST_BODY)

    assert mock_write_log.await_count >= 1
    joined = _join_call_args(mock_write_log.await_args)

    # 계좌번호 자체가 메시지에 노출되면 안 됨
    assert "12345678" not in joined, f"CANO 값이 로그에 노출됨: {joined}"
    # 키 이름도 마스킹 (운영 trace 회수자가 의도적으로 본 키를 추가하지 않도록)
    assert "CANO" not in joined, f"CANO 키 이름이 로그에 노출됨: {joined}"
    assert "ACNT_PRDT_CD" not in joined, f"ACNT_PRDT_CD 키 이름이 로그에 노출됨: {joined}"


# ---------------------------------------------------------------------------
# 4. write_log 가 예외를 던져도 KisApiError 흐름이 보존된다 (fire-and-forget)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_request_when_write_log_raises_then_kis_api_error_still_propagates(
    mock_kis,
    stub_token,
    monkeypatch: pytest.MonkeyPatch,
):
    """write_log 가 Supabase 장애 등으로 예외를 던져도 호출자는 KisApiError 를 받는다."""

    async def _exploding_write_log(*_args, **_kwargs):
        raise RuntimeError("supabase down")

    import src.db.system_logs as _system_logs_mod

    monkeypatch.setattr(_system_logs_mod, "write_log", _exploding_write_log)
    if hasattr(base, "write_log"):
        monkeypatch.setattr(base, "write_log", _exploding_write_log, raising=False)

    import re

    mock_kis.post(re.compile(rf".*{re.escape(_ORDER_CASH_PATH)}$")).respond(
        json=_REJECTION_RESPONSE
    )

    # write_log 실패가 KisApiError 를 가리지 않아야 한다
    with pytest.raises(KisApiError) as exc_info:
        await kis_post(_ORDER_CASH_PATH, "TTTC0012U", _REQUEST_BODY)

    assert exc_info.value.msg_cd == "APBK0123"
    assert "시장가매매불가" in exc_info.value.msg1


# ---------------------------------------------------------------------------
# 5. 회귀 — 정상 응답(rt_cd=0) 에서는 write_log 가 호출되지 않는다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_request_when_kis_succeeds_then_no_log_written(
    mock_kis,
    stub_token,
    mock_write_log,
):
    """rt_cd=0 정상 응답 시 system_logs 호출이 발생하지 않는다 (노이즈 차단)."""
    import re

    mock_kis.post(re.compile(rf".*{re.escape(_ORDER_CASH_PATH)}$")).respond(
        json={
            "rt_cd": "0",
            "msg_cd": "0000",
            "msg1": "정상처리되었습니다.",
            "output": {"ODNO": "0000123456", "ORD_TMD": "093045"},
        }
    )

    data = await kis_post(_ORDER_CASH_PATH, "TTTC0012U", _REQUEST_BODY)
    assert data["rt_cd"] == "0"
    assert mock_write_log.await_count == 0, "정상 응답에서는 write_log 호출 없어야 함"
