"""cycle428(F-422-1) D2 — 주문 경로(`order-cash`·`order-rvsecncl`)는 「보냈을 수
있는」 실패를 재시도하지 않는다.

사용자 승인(2026-10-10): "1차 시장가 주문 실패도 연결오류일 때는 결과모름으로
할 것." — `_request` 재시도 루프에서 주문 경로에 한해:
- `httpx.ConnectError`·`ConnectTimeout`·`PoolTimeout`(서버에 닿지 않음) 만 재시도.
- `ReadTimeout`·`ReadError`·`WriteError`·`RemoteProtocolError`·5xx 는 첫 회에
  바로 올린다(서버가 이미 받았을 수 있다).

조회 경로(화이트리스트 밖 아무 path)는 **무변경** — `test_base_retry_logging.py`
가 그 계약을 지킨다(cycle428 에서 `_PATH` 를 주문 경로 밖으로 옮겼다).

시나리오 번호는 `_workspace/domain_consult/2026-10-10_f422_1_fallback_network_error.md`
「회귀 시나리오」 S11·S12 를 따른다.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock

import httpx
import pytest

from src.api import base
from src.api.base import get_request_metrics, kis_post, reset_request_metrics
from src.auth import token as _token_module

pytestmark = pytest.mark.unit

_ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
_ORDER_RVSECNCL_PATH = "/uapi/domestic-stock/v1/trading/order-rvsecncl"
_NON_ORDER_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
_TR_ID = "TTTC0012U"


@pytest.fixture
def stub_token(monkeypatch: pytest.MonkeyPatch):
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


@pytest.fixture
def mock_write_log(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    import src.db.system_logs as _system_logs_mod

    monkeypatch.setattr(_system_logs_mod, "write_log", mock)
    if hasattr(base, "write_log"):
        monkeypatch.setattr(base, "write_log", mock, raising=False)
    return mock


@pytest.fixture
def no_backoff(monkeypatch: pytest.MonkeyPatch):
    async def _no_sleep(_sec: float) -> None:
        return None

    monkeypatch.setattr(base.asyncio, "sleep", _no_sleep)


@pytest.fixture(autouse=True)
def reset_metrics_before():
    reset_request_metrics()
    yield
    reset_request_metrics()


# ===========================================================================
# S12 — 주문 경로 5xx: 첫 회에 바로 올린다(재시도 0)
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("path", [_ORDER_PATH, _ORDER_RVSECNCL_PATH], ids=["order-cash", "order-rvsecncl"])
async def test_s12_order_path_5xx_raises_on_first_attempt_no_retry(
    mock_kis, stub_token, mock_write_log, no_backoff, path,
):
    route = mock_kis.post(re.compile(rf".*{re.escape(path)}$"))
    route.respond(status_code=503, json={"msg": "unavailable"})

    with pytest.raises(httpx.HTTPStatusError):
        await kis_post(path, _TR_ID, {"PDNO": "005930"})

    assert route.call_count == 1, "주문 경로 5xx 는 재시도하지 않는다 — 1회만 발사"
    metrics = get_request_metrics()
    assert metrics["retry_exhausted"] == 1
    assert metrics["retries"] == 0


# ===========================================================================
# S11 — 주문 경로 ReadTimeout: 첫 회에 바로 올린다(재시도 0)
# ===========================================================================
@pytest.mark.asyncio
async def test_s11_order_path_read_timeout_raises_on_first_attempt_no_retry(
    mock_kis, stub_token, mock_write_log, no_backoff,
):
    route = mock_kis.post(re.compile(rf".*{re.escape(_ORDER_PATH)}$"))
    route.side_effect = httpx.ReadTimeout("read timed out")

    with pytest.raises(httpx.ReadTimeout):
        await kis_post(_ORDER_PATH, _TR_ID, {"PDNO": "005930"})

    assert route.call_count == 1, "ReadTimeout 은 서버가 이미 받았을 수 있다 — 재시도하지 않는다"
    metrics = get_request_metrics()
    assert metrics["retries"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc", [httpx.ReadError("read error"), httpx.WriteError("write error"),
            httpx.RemoteProtocolError("protocol error")],
    ids=["read_error", "write_error", "remote_protocol_error"],
)
async def test_order_path_other_transport_errors_also_block_retry(
    mock_kis, stub_token, mock_write_log, no_backoff, exc,
):
    route = mock_kis.post(re.compile(rf".*{re.escape(_ORDER_PATH)}$"))
    route.side_effect = exc

    with pytest.raises(type(exc)):
        await kis_post(_ORDER_PATH, _TR_ID, {"PDNO": "005930"})

    assert route.call_count == 1


# ===========================================================================
# 대조 — ConnectError/ConnectTimeout/PoolTimeout 은 주문 경로에서도 재시도한다
# (서버에 닿지 않은 것이 보장되는 전송 예외만)
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc", [httpx.ConnectError("connect error"), httpx.ConnectTimeout("connect timeout"),
            httpx.PoolTimeout("pool timeout")],
    ids=["connect_error", "connect_timeout", "pool_timeout"],
)
async def test_order_path_connect_class_errors_still_retry_then_succeed(
    mock_kis, stub_token, mock_write_log, no_backoff, exc,
):
    route = mock_kis.post(re.compile(rf".*{re.escape(_ORDER_PATH)}$"))
    route.side_effect = [
        exc,
        httpx.Response(200, json={"rt_cd": "0", "msg_cd": "0000", "msg1": "OK", "output": {}}),
    ]

    data = await kis_post(_ORDER_PATH, _TR_ID, {"PDNO": "005930"})

    assert data["rt_cd"] == "0"
    assert route.call_count == 2, "ConnectError 계열은 서버에 닿지 않은 것이 보장 — 재시도한다"
    metrics = get_request_metrics()
    assert metrics["retry_recovered"] == 1


@pytest.mark.asyncio
async def test_order_path_connect_error_exhausts_after_max_retries(
    mock_kis, stub_token, mock_write_log, no_backoff,
):
    route = mock_kis.post(re.compile(rf".*{re.escape(_ORDER_PATH)}$"))
    route.side_effect = httpx.ConnectError("connect error")

    with pytest.raises(httpx.ConnectError):
        await kis_post(_ORDER_PATH, _TR_ID, {"PDNO": "005930"})

    assert route.call_count == base.MAX_RETRIES
    metrics = get_request_metrics()
    assert metrics["retry_exhausted"] == 1


# ===========================================================================
# 대조 — 조회성(비주문) 경로는 무변경: ReadTimeout 도 그대로 재시도한다
# ===========================================================================
@pytest.mark.asyncio
async def test_non_order_path_read_timeout_still_retries_unchanged(
    mock_kis, stub_token, mock_write_log, no_backoff,
):
    route = mock_kis.post(re.compile(rf".*{re.escape(_NON_ORDER_PATH)}$"))
    route.side_effect = [
        httpx.ReadTimeout("read timed out"),
        httpx.Response(200, json={"rt_cd": "0", "msg_cd": "0000", "msg1": "OK", "output": {}}),
    ]

    data = await kis_post(_NON_ORDER_PATH, "TTTC8434R", {"PDNO": "005930"})

    assert data["rt_cd"] == "0"
    assert route.call_count == 2, "조회 경로는 D2 의 영향을 받지 않는다 — 기존처럼 재시도"


@pytest.mark.asyncio
async def test_non_order_path_5xx_still_retries_unchanged(
    mock_kis, stub_token, mock_write_log, no_backoff,
):
    route = mock_kis.post(re.compile(rf".*{re.escape(_NON_ORDER_PATH)}$"))
    route.side_effect = [
        httpx.Response(503, json={"msg": "unavailable"}),
        httpx.Response(200, json={"rt_cd": "0", "msg_cd": "0000", "msg1": "OK", "output": {}}),
    ]

    data = await kis_post(_NON_ORDER_PATH, "TTTC8434R", {"PDNO": "005930"})

    assert data["rt_cd"] == "0"
    assert route.call_count == 2, "조회 경로 5xx 는 여전히 재시도한다"
