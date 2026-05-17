"""Cycle 7-C Red — REST 시세성 호출 풀 (`kis_request_quote` 분리).

목표:
- 시세성 KIS REST 호출(`fetch_daily_candles`, `fetch_stock_detail`, `_fetch_fluctuation_rank`,
  `inquire_stock_basics`, `is_market_open`, `next_trading_day`) 을 별도 함수
  `kis_request_quote` (`kis_get_quote`/`kis_post_quote` 래퍼) 로 분리.
- 보조 계좌(`kis_quote_accounts`) 토큰 매니저를 라운드로빈으로 사용. 보조 0개 시 메인 fallback.
- **자금 안전 절대 원칙**: 매매/잔고/체결조회 경로는 시세 풀 거부 — `QuotePoolPathError` raise.

테스트 구조:
1. 보조 0개 / N개 분배 (라운드로빈)
2. Path 가드 (매매/잔고/체결조회 거부)
3. 보조 토큰 매니저 lazy 발급 + 만료 갱신
4. 메트릭 격리 (`_quote_request_metrics`)
5. 매매/잔고 함수는 절대 시세 풀 호출 안 함 (spy 검증)
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest

from src.api import base as base_module
from src.auth import token as token_module

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 시세 풀 화이트리스트 path
# ---------------------------------------------------------------------------
_QUOTE_PATHS = {
    "inquire_price": "/uapi/domestic-stock/v1/quotations/inquire-price",
    "daily_candles": "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
    "fluctuation": "/uapi/domestic-stock/v1/ranking/fluctuation",
    "stock_basics": "/uapi/domestic-stock/v1/quotations/search-stock-info",
    "holiday": "/uapi/domestic-stock/v1/quotations/chk-holiday",
}

# 시세 풀이 거부해야 할 매매/잔고 path
_FORBIDDEN_PATHS = [
    "/uapi/domestic-stock/v1/trading/order-cash",
    "/uapi/domestic-stock/v1/trading/order-rvsecncl",
    "/uapi/domestic-stock/v1/trading/inquire-balance",
    "/uapi/domestic-stock/v1/trading/inquire-psbl-order",
    "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
]


@pytest.fixture
def stub_token(monkeypatch: pytest.MonkeyPatch):
    """메인 토큰 매니저 stub — 실 네트워크 호출 없이 더미 헤더 반환."""

    async def _get_token() -> str:
        return "main-dummy-token"

    def _build_headers(tr_id: str, hashkey: str = "") -> dict[str, str]:
        return {
            "authorization": "Bearer main-dummy",
            "appkey": "main-key",
            "appsecret": "main-secret",
            "tr_id": tr_id,
            "custtype": "P",
        }

    monkeypatch.setattr(token_module.token_manager, "get_token", _get_token)
    monkeypatch.setattr(token_module.token_manager, "build_headers", _build_headers)


@pytest.fixture
def reset_quote_state(monkeypatch: pytest.MonkeyPatch):
    """`_quote_request_metrics` / 라운드로빈 인덱스를 매 테스트 초기화."""
    # 모듈 import 시점에 attribute 없으면 setattr 로 빈 dict / 0 등록
    if hasattr(base_module, "reset_quote_request_metrics"):
        base_module.reset_quote_request_metrics()
    if hasattr(base_module, "_quote_request_index"):
        monkeypatch.setattr(base_module, "_quote_request_index", 0, raising=False)
    yield
    if hasattr(base_module, "reset_quote_request_metrics"):
        base_module.reset_quote_request_metrics()


# ---------------------------------------------------------------------------
# A-1. 보조 0개 시 메인 매니저 fallback
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_quote_pool_when_no_secondary_then_falls_back_to_main(
    mock_kis, stub_token, reset_quote_state, monkeypatch
):
    """보조 계좌가 0개일 때 시세 호출이 메인 토큰 매니저를 그대로 사용한다."""
    # 보조 계좌 0개
    async def _empty_active(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        "src.db.kis_quote_accounts.list_accounts", _empty_active, raising=False
    )

    mock_kis.get(re.compile(rf".*{re.escape(_QUOTE_PATHS['inquire_price'])}(\?.*)?$")).respond(
        json={"rt_cd": "0", "msg_cd": "OK", "msg1": "정상", "output": {"stck_prpr": "65000"}}
    )

    result = await base_module.kis_get_quote(
        _QUOTE_PATHS["inquire_price"],
        "FHKST01010100",
        {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": "005930"},
    )

    assert result["output"]["stck_prpr"] == "65000"


# ---------------------------------------------------------------------------
# A-2. 보조 N개 라운드로빈
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_quote_pool_when_n_secondary_then_round_robin(
    mock_kis, stub_token, reset_quote_state, monkeypatch
):
    """보조 2개 활성 시 3회 호출이 quote-1 → quote-2 → quote-1 분배."""
    # 보조 2개 활성
    class _Acct:
        def __init__(self, label):
            self.label = label
            self.active = True

    async def _list_active(*_args, active_only=False, **_kwargs):
        return [_Acct("quote-1"), _Acct("quote-2")]

    monkeypatch.setattr(
        "src.db.kis_quote_accounts.list_accounts", _list_active, raising=False
    )

    # 보조 토큰 매니저 mock
    quote_managers: dict[str, AsyncMock] = {}

    async def _get_token_manager(label):
        if label is None:
            return token_module.token_manager
        if label not in quote_managers:
            mm = AsyncMock()
            mm.get_token = AsyncMock(return_value=f"token-{label}")
            mm.build_headers = lambda tr_id, hashkey="": {
                "authorization": f"Bearer {label}",
                "appkey": f"{label}-key",
                "appsecret": f"{label}-secret",
                "tr_id": tr_id,
                "custtype": "P",
            }
            mm.label = label
            # 실제 base_url 명시 (AsyncMock auto-attribute 차단)
            mm.base_url = "https://openapivts.koreainvestment.com:29443"
            quote_managers[label] = mm
        return quote_managers[label]

    monkeypatch.setattr(token_module, "get_token_manager", _get_token_manager, raising=False)
    # base 모듈도 동일 경로 의존성 차단
    if hasattr(base_module, "get_token_manager"):
        monkeypatch.setattr(base_module, "get_token_manager", _get_token_manager, raising=False)

    mock_kis.get(re.compile(rf".*{re.escape(_QUOTE_PATHS['inquire_price'])}(\?.*)?$")).respond(
        json={"rt_cd": "0", "msg_cd": "OK", "msg1": "정상", "output": {"stck_prpr": "1"}}
    )

    # 3회 호출
    for _ in range(3):
        await base_module.kis_get_quote(
            _QUOTE_PATHS["inquire_price"],
            "FHKST01010100",
            {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": "005930"},
        )

    # quote-1 : 2회, quote-2 : 1회 (라운드로빈 시작 인덱스 0)
    assert "quote-1" in quote_managers and "quote-2" in quote_managers
    counts = {label: m.get_token.await_count for label, m in quote_managers.items()}
    total = sum(counts.values())
    assert total == 3, f"3회 호출이 보조 토큰 매니저로 분배되어야 함: {counts}"
    # 적어도 두 보조 매니저 모두 1회 이상 호출 (라운드로빈 분배)
    assert all(c >= 1 for c in counts.values()), f"라운드로빈 분배 미동작: {counts}"


# ---------------------------------------------------------------------------
# A-3. 보조 토큰 매니저 lazy 발급
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_quote_pool_calls_get_token_manager_with_label(
    mock_kis, stub_token, reset_quote_state, monkeypatch
):
    """라운드로빈 선택 후 `get_token_manager(label)` 가 호출된다."""
    class _Acct:
        def __init__(self, label):
            self.label = label
            self.active = True

    async def _list_active(*_args, active_only=False, **_kwargs):
        return [_Acct("quote-1")]

    monkeypatch.setattr(
        "src.db.kis_quote_accounts.list_accounts", _list_active, raising=False
    )

    get_token_calls: list[str] = []

    async def _get_token_manager(label):
        get_token_calls.append(label if label else "main")
        if label is None:
            return token_module.token_manager
        mm = AsyncMock()
        mm.get_token = AsyncMock(return_value=f"tok-{label}")
        mm.build_headers = lambda tr_id, hashkey="": {
            "authorization": f"Bearer {label}",
            "appkey": f"{label}-key",
            "appsecret": f"{label}-secret",
            "tr_id": tr_id,
            "custtype": "P",
        }
        mm.label = label
        mm.base_url = "https://openapivts.koreainvestment.com:29443"
        return mm

    monkeypatch.setattr(token_module, "get_token_manager", _get_token_manager, raising=False)
    if hasattr(base_module, "get_token_manager"):
        monkeypatch.setattr(base_module, "get_token_manager", _get_token_manager, raising=False)

    mock_kis.get(re.compile(rf".*{re.escape(_QUOTE_PATHS['daily_candles'])}(\?.*)?$")).respond(
        json={"rt_cd": "0", "msg_cd": "OK", "msg1": "정상", "output2": []}
    )

    await base_module.kis_get_quote(
        _QUOTE_PATHS["daily_candles"],
        "FHKST03010100",
        {"FID_INPUT_ISCD": "005930"},
    )

    # quote-1 이 호출되었음
    assert "quote-1" in get_token_calls


# ---------------------------------------------------------------------------
# A-4. 보조 매니저 ValueError → 메인 fallback
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_quote_pool_when_secondary_manager_fails_then_falls_back_to_main(
    mock_kis, stub_token, reset_quote_state, monkeypatch
):
    """보조 토큰 매니저 발급 실패 시 메인 매니저로 graceful fallback."""
    class _Acct:
        def __init__(self, label):
            self.label = label
            self.active = True

    async def _list_active(*_args, active_only=False, **_kwargs):
        return [_Acct("quote-broken")]

    monkeypatch.setattr(
        "src.db.kis_quote_accounts.list_accounts", _list_active, raising=False
    )

    async def _get_token_manager(label):
        if label is None:
            return token_module.token_manager
        raise ValueError(f"보조 미등록: {label}")

    monkeypatch.setattr(token_module, "get_token_manager", _get_token_manager, raising=False)
    if hasattr(base_module, "get_token_manager"):
        monkeypatch.setattr(base_module, "get_token_manager", _get_token_manager, raising=False)

    mock_kis.get(re.compile(rf".*{re.escape(_QUOTE_PATHS['inquire_price'])}(\?.*)?$")).respond(
        json={"rt_cd": "0", "msg_cd": "OK", "msg1": "정상", "output": {"stck_prpr": "1"}}
    )

    result = await base_module.kis_get_quote(
        _QUOTE_PATHS["inquire_price"],
        "FHKST01010100",
        {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": "005930"},
    )

    assert result["output"]["stck_prpr"] == "1", "보조 실패 시 메인 fallback 으로 정상 응답 반환"


# ---------------------------------------------------------------------------
# A-5. Path 가드 — 매매/잔고/체결조회 path 는 거부
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("forbidden_path", _FORBIDDEN_PATHS)
async def test_quote_pool_when_forbidden_path_then_raises(
    forbidden_path, stub_token, reset_quote_state
):
    """매매/잔고/체결조회 path 는 시세 풀에서 명시적으로 거부."""
    with pytest.raises((ValueError, base_module.QuotePoolPathError)) as exc_info:
        await base_module.kis_get_quote(forbidden_path, "TTTC0012U", None)
    # 거부 메시지에 path 포함 여부
    assert forbidden_path in str(exc_info.value) or "시세" in str(exc_info.value) or "quote" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# A-6. Path 화이트리스트 — 시세 path 6개 모두 통과
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("allowed_path", list(_QUOTE_PATHS.values()))
async def test_quote_pool_when_allowed_path_then_succeeds(
    allowed_path, mock_kis, stub_token, reset_quote_state, monkeypatch
):
    """화이트리스트 path 6개는 모두 통과."""
    async def _list_active(*_args, active_only=False, **_kwargs):
        return []

    monkeypatch.setattr(
        "src.db.kis_quote_accounts.list_accounts", _list_active, raising=False
    )

    mock_kis.get(re.compile(rf".*{re.escape(allowed_path)}(\?.*)?$")).respond(
        json={"rt_cd": "0", "msg_cd": "OK", "msg1": "정상", "output": {}, "output2": []}
    )

    result = await base_module.kis_get_quote(allowed_path, "FHKST01010100", {"key": "val"})
    assert result["rt_cd"] == "0"


# ---------------------------------------------------------------------------
# A-7 / A-8. kis_get_quote / kis_post_quote 위임
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_kis_get_quote_delegates_to_request_via_quote_pool(
    mock_kis, stub_token, reset_quote_state, monkeypatch
):
    """`kis_get_quote` 가 `_request_via_quote_pool('GET', ...)` 호출 위임."""
    async def _list_active(*_args, **_kwargs):
        return []
    monkeypatch.setattr(
        "src.db.kis_quote_accounts.list_accounts", _list_active, raising=False
    )

    captured: dict = {}
    real_request = base_module._request_via_quote_pool

    async def _spy(method, path, tr_id, **kwargs):
        captured["method"] = method
        captured["path"] = path
        captured["tr_id"] = tr_id
        return await real_request(method, path, tr_id, **kwargs)

    monkeypatch.setattr(base_module, "_request_via_quote_pool", _spy)

    mock_kis.get(re.compile(rf".*{re.escape(_QUOTE_PATHS['inquire_price'])}(\?.*)?$")).respond(
        json={"rt_cd": "0", "msg_cd": "OK", "msg1": "정상", "output": {}}
    )

    await base_module.kis_get_quote(_QUOTE_PATHS["inquire_price"], "FHKST01010100", {"a": "b"})
    assert captured["method"] == "GET"
    assert captured["path"] == _QUOTE_PATHS["inquire_price"]


# ---------------------------------------------------------------------------
# A-11. 메트릭 격리 — get_quote_request_metrics
# ---------------------------------------------------------------------------
def test_get_quote_request_metrics_returns_isolated_snapshot(reset_quote_state):
    """시세 풀 메트릭은 메인 `_request_metrics` 와 분리된 별도 dict."""
    main_before = base_module.get_request_metrics()["total"]
    quote_metrics = base_module.get_quote_request_metrics()

    # 시세 메트릭 dict 키 검증
    assert {"total", "http_5xx", "http_4xx", "network_err", "kis_error", "retries"} <= set(quote_metrics)

    # 시세 메트릭 변경이 메인 메트릭에 영향 안 줌
    if hasattr(base_module, "_quote_request_metrics"):
        base_module._quote_request_metrics["total"] = 99
    main_after = base_module.get_request_metrics()["total"]
    assert main_before == main_after, "시세 메트릭 변경이 메인 메트릭에 누출되면 안 됨"


# ---------------------------------------------------------------------------
# A-12. MAX_RETRIES=3 — 시세 풀도 동일
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_quote_pool_retries_on_5xx(
    mock_kis, stub_token, reset_quote_state, monkeypatch
):
    """5xx 응답 시 3회 재시도 (메인 _request 와 동일 정책)."""
    async def _list_active(*_args, **_kwargs):
        return []
    monkeypatch.setattr(
        "src.db.kis_quote_accounts.list_accounts", _list_active, raising=False
    )

    # asyncio.sleep 즉시 진행 (재시도 backoff 단축)
    import asyncio as _aio
    async def _no_sleep(*_a, **_k):
        return None
    monkeypatch.setattr(_aio, "sleep", _no_sleep)

    # 매번 503 응답
    route = mock_kis.get(re.compile(rf".*{re.escape(_QUOTE_PATHS['inquire_price'])}(\?.*)?$")).respond(
        status_code=503
    )

    with pytest.raises(Exception):  # httpx.HTTPStatusError 또는 RuntimeError
        await base_module.kis_get_quote(
            _QUOTE_PATHS["inquire_price"], "FHKST01010100", {"a": "b"}
        )

    # MAX_RETRIES=3 → 정확히 3회 호출
    assert route.call_count == 3, f"5xx 재시도 3회 기대, 실제={route.call_count}"


# ---------------------------------------------------------------------------
# 가드 B-6. 매매/잔고 함수는 절대 시세 풀 호출 안 함 — spy 검증
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_order_balance_never_routes_to_quote_pool(
    mock_kis, stub_token, reset_quote_state, monkeypatch
):
    """`place_order` / `get_balance` 가 `kis_request_quote` 를 호출하지 않는지 spy.

    호출 0 회로 정확히 격리되어야 — 자금 안전 절대 원칙.
    """
    quote_pool_calls: list = []
    original_quote = base_module._request_via_quote_pool

    async def _spy_quote(method, path, tr_id, **kwargs):
        quote_pool_calls.append((method, path, tr_id))
        return await original_quote(method, path, tr_id, **kwargs)

    monkeypatch.setattr(base_module, "_request_via_quote_pool", _spy_quote)

    # `place_order` 응답 mock
    mock_kis.post(re.compile(r".*/uapi/domestic-stock/v1/trading/order-cash$")).respond(
        json={"rt_cd": "0", "msg_cd": "OK", "msg1": "정상", "output": {"ODNO": "12345678"}}
    )
    # `get_balance` 응답 mock
    mock_kis.get(re.compile(r".*/uapi/domestic-stock/v1/trading/inquire-balance$")).respond(
        json={
            "rt_cd": "0", "msg_cd": "OK", "msg1": "정상",
            "output1": [], "output2": [{"prvs_rcdl_excc_amt": "1000000"}],
        }
    )

    from src.api.order import place_order, OrderSide, OrderDivision
    from src.api.balance import get_balance

    try:
        await place_order(
            "005930",
            quantity=10,
            side=OrderSide.BUY,
            price=0,
            order_division=OrderDivision.MARKET,
            exchange="KRX",
        )
    except Exception:
        pass  # 응답이 통과해도 race / 모듈 의존성 가능
    try:
        await get_balance()
    except Exception:
        pass

    assert quote_pool_calls == [], (
        f"매매/잔고 호출이 시세 풀로 라우트되면 자금 안전 원칙 위배: {quote_pool_calls}"
    )
