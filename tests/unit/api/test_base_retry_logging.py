"""PR-B (2026-05-14) — KIS REST 재시도 최종 결과 관찰성.

`src/api/base.py::_request` 의 재시도 루프가 끝난 직후 다음 두 케이스를 영구 로그 +
`_request_metrics` 카운터로 노출해야 한다:

1. attempt > 1 에서 rt_cd=0 성공 → `[api_retry_recovered]` INFO + `retry_recovered += 1`
2. MAX_RETRIES 모두 5xx/network 실패 → `[api_retry_exhausted]` ERROR + `retry_exhausted += 1`

기존 `kis_error` 카운터(rt_cd != 0 매 응답마다 +1) 와는 별도 — 재시도 *최종* 결과만 카운트.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from src.api import base
from src.api.base import (
    KisApiError,
    get_request_metrics,
    kis_post,
    reset_request_metrics,
)
from src.auth import token as _token_module

pytestmark = pytest.mark.unit


def _join_call_args(call) -> str:
    parts: list[str] = []
    for a in call.args:
        parts.append(str(a))
    for v in call.kwargs.values():
        parts.append(str(v))
    return " | ".join(parts)


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
    """재시도 백오프 sleep 제거 — 테스트 가속."""

    async def _no_sleep(_sec: float) -> None:
        return None

    monkeypatch.setattr(base.asyncio, "sleep", _no_sleep)
    return None


@pytest.fixture(autouse=True)
def reset_metrics_before():
    reset_request_metrics()
    yield
    reset_request_metrics()


_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
_TR_ID = "TTTC0012U"


# ---------------------------------------------------------------------------
# 1. recovered — 재시도 후 성공
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_when_first_attempt_5xx_then_second_success_emits_recovered(
    mock_kis,
    stub_token,
    mock_write_log,
    no_backoff,
):
    """5xx → 200(rt_cd=0) 순서로 응답 시 `[api_retry_recovered]` INFO 로그 + 카운터 +1."""
    import re

    route = mock_kis.post(re.compile(rf".*{re.escape(_PATH)}$"))
    route.side_effect = [
        httpx.Response(503, json={"msg": "service unavailable"}),
        httpx.Response(200, json={"rt_cd": "0", "msg_cd": "0000", "msg1": "OK", "output": {}}),
    ]

    data = await kis_post(_PATH, _TR_ID, {"PDNO": "005930"})
    assert data["rt_cd"] == "0"

    # write_log 호출 중 [api_retry_recovered] prefix 메시지가 정확히 1회 등장
    recovered_calls = [
        c for c in mock_write_log.await_args_list
        if "[api_retry_recovered]" in _join_call_args(c)
    ]
    assert len(recovered_calls) == 1, f"recovered 로그 누락: {mock_write_log.await_args_list}"
    joined = _join_call_args(recovered_calls[0])
    assert _PATH in joined
    assert _TR_ID in joined
    assert "attempts=2" in joined

    # 메트릭 카운터
    metrics = get_request_metrics()
    assert metrics["retry_recovered"] == 1
    assert metrics["retry_exhausted"] == 0


# ---------------------------------------------------------------------------
# 2. exhausted — MAX_RETRIES 후에도 5xx 지속
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_when_all_attempts_5xx_then_emits_exhausted_and_raises(
    mock_kis,
    stub_token,
    mock_write_log,
    no_backoff,
):
    """3회 모두 5xx → `[api_retry_exhausted]` ERROR + 카운터 +1 + HTTPStatusError raise."""
    import re

    mock_kis.post(re.compile(rf".*{re.escape(_PATH)}$")).respond(
        status_code=503,
        json={"msg": "unavailable"},
    )

    with pytest.raises(httpx.HTTPStatusError):
        await kis_post(_PATH, _TR_ID, {"PDNO": "005930"})

    exhausted_calls = [
        c for c in mock_write_log.await_args_list
        if "[api_retry_exhausted]" in _join_call_args(c)
    ]
    assert len(exhausted_calls) == 1, f"exhausted 로그 누락: {mock_write_log.await_args_list}"
    joined = _join_call_args(exhausted_calls[0])
    assert _PATH in joined
    assert _TR_ID in joined
    assert "attempts=3" in joined
    assert "503" in joined

    metrics = get_request_metrics()
    assert metrics["retry_exhausted"] == 1
    assert metrics["retry_recovered"] == 0


# ---------------------------------------------------------------------------
# 3. 첫 번째 시도부터 성공 — recovered 로그 없음 (회귀)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_when_first_attempt_succeeds_then_no_recovered_log(
    mock_kis,
    stub_token,
    mock_write_log,
):
    import re

    mock_kis.post(re.compile(rf".*{re.escape(_PATH)}$")).respond(
        json={"rt_cd": "0", "msg_cd": "0000", "msg1": "OK", "output": {}}
    )

    data = await kis_post(_PATH, _TR_ID, {"PDNO": "005930"})
    assert data["rt_cd"] == "0"

    recovered_calls = [
        c for c in mock_write_log.await_args_list
        if "[api_retry_recovered]" in _join_call_args(c)
    ]
    assert len(recovered_calls) == 0
    metrics = get_request_metrics()
    assert metrics["retry_recovered"] == 0
    assert metrics["retry_exhausted"] == 0


# ---------------------------------------------------------------------------
# 4. reset_request_metrics 가 신규 키도 0 으로 초기화
# ---------------------------------------------------------------------------
def test_reset_request_metrics_clears_new_keys():
    base._request_metrics["retry_recovered"] = 7
    base._request_metrics["retry_exhausted"] = 3
    reset_request_metrics()
    metrics = get_request_metrics()
    assert metrics["retry_recovered"] == 0
    assert metrics["retry_exhausted"] == 0
