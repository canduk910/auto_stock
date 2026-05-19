"""사이클 18 Red — 보조 라벨 fast 윈도우 5xx 80%+ 즉시 메인 fallback (A-3).

배경:
- ISA 같은 보조 라벨이 영구 5xx (80%+) 면 매 호출 3회 재시도 backoff 누적 (1+2+4=7s)
- health_monitor 자동 비활성 임계 도달 전 (fast 10회 또는 5분 50%) 까지 응답 지연 폭주

해결책 (A-3):
- `_request_via_quote_pool` 의 라벨 선택 직후 health_monitor `get_recent_5xx_ratio(label)` 조회
- 80%+ + total>=10 → label=None 강제 (메인 fallback)
- INFO 로그 `[quote_pool] 보조 라벨 fast window 5xx ...% — 메인 fallback`
- 메트릭 카운터 `_quote_request_metrics["fast_fallback"]` += 1

검증 사양 (5 케이스):
1. fast 80% + total>=10 → actual_label="main" (라벨 skip)
2. fast 50% → 보조 라벨 그대로 사용 (기존 동작)
3. fast total<10 → 보조 사용 (premature decision 차단)
4. `_disabled_labels` 라벨 → 메인 fallback (sanity guard)
5. fast_fallback 메트릭 카운터 1 증가
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest

from src.api import base as base_module
from src.auth import token as token_module

pytestmark = pytest.mark.unit

_INQUIRE_PRICE = "/uapi/domestic-stock/v1/quotations/inquire-price"


# ---------------------------------------------------------------------------
# 헬퍼 — 풀 상태 + health_monitor 격리 reset
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_pool_and_health(monkeypatch):
    """quote_pool 메트릭/dedupe + health_monitor 격리 reset."""
    from src.api import base as _b
    from src.services import quote_session_health as qsh

    _b.reset_quote_request_metrics()
    _b._quote_5xx_dedupe.clear() if hasattr(_b, "_quote_5xx_dedupe") else None
    qsh.health_monitor.reset()
    yield
    _b.reset_quote_request_metrics()
    if hasattr(_b, "_quote_5xx_dedupe"):
        _b._quote_5xx_dedupe.clear()
    qsh.health_monitor.reset()


async def _ok_response_factory(label_holder: list[str]):
    """KIS rt_cd=0 응답 mock factory."""
    async def _mock_request(*args, **kwargs):
        return {"rt_cd": "0", "msg_cd": "MCA00000", "output": {}}

    return _mock_request


def _mock_active_labels(labels: list[str]):
    """`_select_quote_label` 이 첫 라벨을 반환하도록 mock."""
    async def _fake_select():
        return labels[0] if labels else None
    return _fake_select


def _fake_token_manager(label: str):
    """get_token_manager mock — base_url + get_token + build_headers."""
    mgr = AsyncMock()
    mgr.base_url = "https://openapi.koreainvestment.com:9443"
    mgr.get_token = AsyncMock(return_value="dummy-token")
    mgr.build_headers = lambda tr_id, hashkey="": {
        "authorization": "Bearer dummy",
        "appkey": "ak", "appsecret": "as", "tr_id": tr_id, "custtype": "P",
    }
    return mgr


# ---------------------------------------------------------------------------
# 사양 1 — fast 80% + total>=10 → actual_label="main"
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_label_5xx_80pct_skips_to_main_fallback(monkeypatch):
    """fast 윈도우 12회 호출 중 10회 실패 (rate=0.83) → 메인 fallback 강제."""
    from src.api import base as _b
    from src.services.quote_session_health import health_monitor

    # health_monitor fast 윈도우에 80%+ 상태 세팅
    health_monitor._fast_window_total["ISA"] = 12
    health_monitor._fast_window_failures["ISA"] = 10

    monkeypatch.setattr(_b, "_select_quote_label", _mock_active_labels(["ISA"]))
    # 메인 token_manager 의 토큰 발급만 stub — base_url 은 property 라 그대로 두기
    monkeypatch.setattr(_b.token_manager, "get_token", AsyncMock(return_value="main-token"))

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__aenter__.return_value
        mock_response = AsyncMock()
        mock_response.json = lambda: {"rt_cd": "0", "output": {}}
        mock_response.raise_for_status = lambda: None
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await _b._request_via_quote_pool(
            "GET", _INQUIRE_PRICE, "FHKST01010100", params={"a": "b"},
        )

    assert result["rt_cd"] == "0"
    metrics = _b.get_quote_request_metrics()
    assert metrics["by_label"].get("main", 0) >= 1, (
        f"메인 fallback 사용해야 함, by_label={metrics['by_label']}"
    )
    assert metrics["by_label"].get("ISA", 0) == 0, (
        f"ISA 라벨 사용 안 해야 함, by_label={metrics['by_label']}"
    )


# ---------------------------------------------------------------------------
# 사양 2 — fast 50% → 보조 라벨 사용 유지
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_label_5xx_below_threshold_uses_secondary(monkeypatch):
    """fast 윈도우 50% (임계 80% 미만) → 보조 라벨 그대로 사용."""
    from src.api import base as _b
    from src.services.quote_session_health import health_monitor

    # 50% — 임계 미만
    health_monitor._fast_window_total["ISA"] = 12
    health_monitor._fast_window_failures["ISA"] = 6

    monkeypatch.setattr(_b, "_select_quote_label", _mock_active_labels(["ISA"]))
    monkeypatch.setattr(_b, "get_token_manager",
                        AsyncMock(return_value=_fake_token_manager("ISA")))

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__aenter__.return_value
        mock_response = AsyncMock()
        mock_response.json = lambda: {"rt_cd": "0", "output": {}}
        mock_response.raise_for_status = lambda: None
        mock_client.get = AsyncMock(return_value=mock_response)

        await _b._request_via_quote_pool(
            "GET", _INQUIRE_PRICE, "FHKST01010100", params={"a": "b"},
        )

    metrics = _b.get_quote_request_metrics()
    assert metrics["by_label"].get("ISA", 0) >= 1, (
        f"50% 비율은 임계 미만 → ISA 사용, by_label={metrics['by_label']}"
    )


# ---------------------------------------------------------------------------
# 사양 3 — fast total<10 → 보조 사용 (premature decision 차단)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_label_with_insufficient_calls_uses_secondary(monkeypatch):
    """fast 윈도우 total=5, failures=5 (rate=1.0) 이지만 min_calls 미달 → 보조 사용."""
    from src.api import base as _b
    from src.services.quote_session_health import health_monitor

    # rate=1.0 이지만 total<10
    health_monitor._fast_window_total["ISA"] = 5
    health_monitor._fast_window_failures["ISA"] = 5

    monkeypatch.setattr(_b, "_select_quote_label", _mock_active_labels(["ISA"]))
    monkeypatch.setattr(_b, "get_token_manager",
                        AsyncMock(return_value=_fake_token_manager("ISA")))

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__aenter__.return_value
        mock_response = AsyncMock()
        mock_response.json = lambda: {"rt_cd": "0", "output": {}}
        mock_response.raise_for_status = lambda: None
        mock_client.get = AsyncMock(return_value=mock_response)

        await _b._request_via_quote_pool(
            "GET", _INQUIRE_PRICE, "FHKST01010100", params={"a": "b"},
        )

    metrics = _b.get_quote_request_metrics()
    assert metrics["by_label"].get("ISA", 0) >= 1, (
        f"min_calls 미달 → ISA 보조 사용, by_label={metrics['by_label']}"
    )


# ---------------------------------------------------------------------------
# 사양 4 — disabled 라벨 → 메인 fallback
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disabled_label_always_skipped(monkeypatch):
    """`_disabled_labels` 에 등록된 라벨은 메인 fallback (sanity, race 대비)."""
    from src.api import base as _b
    from src.services.quote_session_health import health_monitor

    health_monitor._disabled_labels.add("ISA")

    monkeypatch.setattr(_b, "_select_quote_label", _mock_active_labels(["ISA"]))
    monkeypatch.setattr(_b.token_manager, "get_token", AsyncMock(return_value="main-token"))

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__aenter__.return_value
        mock_response = AsyncMock()
        mock_response.json = lambda: {"rt_cd": "0", "output": {}}
        mock_response.raise_for_status = lambda: None
        mock_client.get = AsyncMock(return_value=mock_response)

        await _b._request_via_quote_pool(
            "GET", _INQUIRE_PRICE, "FHKST01010100", params={"a": "b"},
        )

    metrics = _b.get_quote_request_metrics()
    assert metrics["by_label"].get("main", 0) >= 1, (
        f"비활성 라벨은 메인 fallback, by_label={metrics['by_label']}"
    )
    assert metrics["by_label"].get("ISA", 0) == 0


# ---------------------------------------------------------------------------
# 사양 5 — fast_fallback 메트릭 카운터 1 증가
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_label_skip_metric_recorded(monkeypatch):
    """fast 80%+ 메인 fallback 진입 시 `_quote_request_metrics['fast_fallback']` += 1."""
    from src.api import base as _b
    from src.services.quote_session_health import health_monitor

    health_monitor._fast_window_total["ISA"] = 12
    health_monitor._fast_window_failures["ISA"] = 11

    monkeypatch.setattr(_b, "_select_quote_label", _mock_active_labels(["ISA"]))
    monkeypatch.setattr(_b.token_manager, "get_token", AsyncMock(return_value="main-token"))

    before = _b.get_quote_request_metrics().get("fast_fallback", 0)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__aenter__.return_value
        mock_response = AsyncMock()
        mock_response.json = lambda: {"rt_cd": "0", "output": {}}
        mock_response.raise_for_status = lambda: None
        mock_client.get = AsyncMock(return_value=mock_response)

        await _b._request_via_quote_pool(
            "GET", _INQUIRE_PRICE, "FHKST01010100", params={"a": "b"},
        )

    after = _b.get_quote_request_metrics().get("fast_fallback", 0)
    assert after == before + 1, (
        f"fast_fallback 카운터 1 증가해야 함, before={before} after={after}"
    )
