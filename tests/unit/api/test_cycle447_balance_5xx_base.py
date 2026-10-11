"""cycle447 제안 1·2·8 — 잔고조회(TTTC8434R) 5xx 대응(`src/api/base.py`).

정본 = `_workspace/analysis/balance_5xx_20261011/result.md`.

1. 5xx 응답 본문(msg_cd/msg1 또는 앞 200자)을 WARNING 한 줄에 싣는다(계좌번호 마스킹).
2. 잔고 조회 경로(`inquire-balance`)만 재시도 예산을 5회·1~2초 간격으로 늘린다.
   다른 경로는 기존(`MAX_RETRIES=3`, 지수 백오프) 그대로다.
8. 경로별 총 호출 수(`by_path_total`)를 메트릭에 추가한다.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock

import httpx
import pytest

from src.api import base
from src.api.base import get_request_metrics, kis_get, kis_post, reset_request_metrics
from src.auth import token as _token_module

pytestmark = pytest.mark.unit

_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
_BALANCE_TR_ID = "TTTC8434R"
_OTHER_PATH = "/uapi/domestic-stock/v1/trading/inquire-psbl-order"
_OTHER_TR_ID = "TTTC8908R"


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
    return None


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
    """재시도 백오프 sleep 을 기록만 하고 실제로는 기다리지 않는다."""
    sleeps: list[float] = []

    async def _no_sleep(sec: float) -> None:
        sleeps.append(sec)
        return None

    monkeypatch.setattr(base.asyncio, "sleep", _no_sleep)
    return sleeps


@pytest.fixture(autouse=True)
def reset_metrics_before():
    reset_request_metrics()
    yield
    reset_request_metrics()


# ===========================================================================
# 제안 1 — 5xx 본문 상세
# ===========================================================================
@pytest.mark.asyncio
async def test_5xx_body_with_msg_cd_is_logged_in_warning(
    mock_kis, stub_token, mock_write_log, no_backoff, caplog,
):
    """JSON 본문에 msg_cd/msg1 이 있으면 WARNING 에 그대로 싣는다."""
    import logging

    route = mock_kis.get(re.compile(rf".*{re.escape(_BALANCE_PATH)}"))
    route.respond(
        status_code=500,
        json={"rt_cd": "1", "msg_cd": "EGW00215", "msg1": "원장에서 허용 가능한 초당 거래건수를 초과하였습니다"},
    )

    with caplog.at_level(logging.WARNING):
        with pytest.raises(httpx.HTTPStatusError):
            await kis_get(_BALANCE_PATH, _BALANCE_TR_ID, {"PDNO": "005930"})

    joined = " | ".join(r.getMessage() for r in caplog.records)
    assert "EGW00215" in joined, f"msg_cd 누락: {joined}"
    assert "초당 거래건수" in joined, f"msg1 누락: {joined}"


@pytest.mark.asyncio
async def test_5xx_body_without_json_falls_back_to_raw_text(
    mock_kis, stub_token, mock_write_log, no_backoff, caplog,
):
    """JSON 이 아닌 본문(예: 게이트웨이 HTML 오류)은 앞 200자를 싣는다."""
    import logging

    route = mock_kis.get(re.compile(rf".*{re.escape(_BALANCE_PATH)}"))
    route.respond(status_code=502, content=b"<html>Bad Gateway</html>")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(httpx.HTTPStatusError):
            await kis_get(_BALANCE_PATH, _BALANCE_TR_ID, {"PDNO": "005930"})

    joined = " | ".join(r.getMessage() for r in caplog.records)
    assert "Bad Gateway" in joined, f"본문 폴백 누락: {joined}"


@pytest.mark.asyncio
async def test_5xx_body_detail_masks_account_number(
    mock_kis, stub_token, mock_write_log, no_backoff, caplog,
):
    """본문에 계좌번호가 섞여 있어도(방어적) 로그에 그대로 남지 않는다."""
    import logging

    route = mock_kis.get(re.compile(rf".*{re.escape(_BALANCE_PATH)}"))
    route.respond(status_code=500, content=b"CANO=12345678 internal error")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(httpx.HTTPStatusError):
            await kis_get(_BALANCE_PATH, _BALANCE_TR_ID, {"PDNO": "005930"})

    joined = " | ".join(r.getMessage() for r in caplog.records)
    assert "12345678" not in joined, f"계좌번호가 로그에 남았다: {joined}"


# ===========================================================================
# 제안 2 — 잔고 조회 경로만 재시도 5회·1~2초 간격
# ===========================================================================
@pytest.mark.asyncio
async def test_balance_path_retries_five_times_before_exhausted(
    mock_kis, stub_token, mock_write_log, no_backoff,
):
    route = mock_kis.get(re.compile(rf".*{re.escape(_BALANCE_PATH)}"))
    route.respond(status_code=503, json={"msg": "unavailable"})

    with pytest.raises(httpx.HTTPStatusError):
        await kis_get(_BALANCE_PATH, _BALANCE_TR_ID, {"PDNO": "005930"})

    assert route.call_count == 5, f"잔고 조회는 5회까지 재시도해야 한다 (실측 {route.call_count})"

    exhausted_calls = [
        c for c in mock_write_log.await_args_list
        if "[api_retry_exhausted]" in str(c)
    ]
    assert len(exhausted_calls) == 1
    assert "attempts=5" in str(exhausted_calls[0])


@pytest.mark.asyncio
async def test_balance_path_backoff_is_one_to_two_seconds(monkeypatch):
    """`_sleep_before_retry` 직접 단위 검증 — `_rate_limit()` 의 별개 sleep 과
    섞이지 않게 `_request()` 전체 경로가 아니라 헬퍼만 부른다."""
    recorded: list[float] = []

    async def _fake_sleep(sec: float) -> None:
        recorded.append(sec)

    monkeypatch.setattr(base.asyncio, "sleep", _fake_sleep)

    for _ in range(20):
        await base._sleep_before_retry(_BALANCE_PATH, 1)
    assert len(recorded) == 20
    for s in recorded:
        assert 1.0 <= s <= 2.0, f"잔고 조회 백오프는 1~2초 구간이어야 한다: {s}"


def test_other_path_backoff_is_unchanged_exponential(monkeypatch):
    """잔고 조회 밖은 기존 `BACKOFF_BASE × 2^(attempt-1) + jitter` 그대로다."""
    import asyncio as _asyncio

    recorded: list[float] = []

    async def _fake_sleep(sec: float) -> None:
        recorded.append(sec)

    monkeypatch.setattr(base.asyncio, "sleep", _fake_sleep)

    _asyncio.run(base._sleep_before_retry(_OTHER_PATH, 1))
    assert base.BACKOFF_BASE <= recorded[-1] <= base.BACKOFF_BASE + base.BACKOFF_JITTER

    _asyncio.run(base._sleep_before_retry(_OTHER_PATH, 2))
    lo = base.BACKOFF_BASE * 2
    assert lo <= recorded[-1] <= lo + base.BACKOFF_JITTER


@pytest.mark.asyncio
async def test_other_path_still_retries_only_three_times(
    mock_kis, stub_token, mock_write_log, no_backoff,
):
    """잔고 조회 밖의 조회 경로는 그대로 `MAX_RETRIES=3` 이다(cycle428 D2 영향 없음)."""
    route = mock_kis.get(re.compile(rf".*{re.escape(_OTHER_PATH)}"))
    route.respond(status_code=503, json={"msg": "unavailable"})

    with pytest.raises(httpx.HTTPStatusError):
        await kis_get(_OTHER_PATH, _OTHER_TR_ID, {"PDNO": "005930"})

    assert route.call_count == base.MAX_RETRIES == 3


@pytest.mark.asyncio
async def test_balance_path_recovers_within_five_attempts(
    mock_kis, stub_token, mock_write_log, no_backoff,
):
    route = mock_kis.get(re.compile(rf".*{re.escape(_BALANCE_PATH)}"))
    route.side_effect = [
        httpx.Response(503, json={"msg": "unavailable"}),
        httpx.Response(503, json={"msg": "unavailable"}),
        httpx.Response(503, json={"msg": "unavailable"}),
        httpx.Response(200, json={"rt_cd": "0", "msg_cd": "0000", "msg1": "OK", "output1": [], "output2": [{}]}),
    ]

    data = await kis_get(_BALANCE_PATH, _BALANCE_TR_ID, {"PDNO": "005930"})
    assert data["rt_cd"] == "0"
    assert route.call_count == 4


# ===========================================================================
# 제안 8 — 경로별 총 호출 수
# ===========================================================================
@pytest.mark.asyncio
async def test_by_path_total_counts_logical_calls_once_each(
    mock_kis, stub_token, mock_write_log, no_backoff,
):
    """재시도와 무관하게 호출 1건 = `by_path_total[path] += 1`(성공/실패 모두)."""
    ok_path = "/uapi/domestic-stock/v1/trading/order-cash"
    mock_kis.post(re.compile(rf".*{re.escape(ok_path)}$")).respond(
        json={"rt_cd": "0", "msg_cd": "0000", "msg1": "OK", "output": {}}
    )
    await kis_post(ok_path, "TTTC0012U", {"PDNO": "005930"})
    await kis_post(ok_path, "TTTC0012U", {"PDNO": "005930"})

    fail_route = mock_kis.get(re.compile(rf".*{re.escape(_OTHER_PATH)}"))
    fail_route.respond(status_code=503, json={"msg": "unavailable"})
    with pytest.raises(httpx.HTTPStatusError):
        await kis_get(_OTHER_PATH, _OTHER_TR_ID, {"PDNO": "005930"})

    metrics = get_request_metrics()
    assert metrics["by_path_total"][ok_path] == 2
    assert metrics["by_path_total"][_OTHER_PATH] == 1


def test_by_path_total_cleared_on_reset():
    base._request_metrics["by_path_total"]["/x"] = 7
    reset_request_metrics()
    assert get_request_metrics()["by_path_total"] == {}
