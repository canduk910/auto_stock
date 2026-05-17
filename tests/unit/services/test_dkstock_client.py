"""src/services/dkstock_client.py 단위 테스트 (사이클 2 — 시장 레짐 필터).

dkstock.cloud JWT Bearer 클라이언트 검증.

- DKSTOCK_REGIME_ENABLED=false → ConfigError (생성자/메서드 가드)
- 정상 login → access_token / refresh_token 추출
- 401 → ExternalAPIError
- 토큰 만료 401 → refresh 후 재시도 1회 → 정상 응답
- refresh_token 만료 → ExternalAPIError (운영자 SSH 갱신 안내)
- 외부 서버 다운(ConnectError) → ExternalAPIError
- get_macro_cycle 응답 파싱 (regime/cycle/params 추출)

운영 graceful degrade: ExternalAPIError 는 호출자(market_regime.refresh)가 흡수 후
매수 가드 비활성으로 기본값 복귀 — 자동매매 본 흐름 영향 0.
"""
from __future__ import annotations

import httpx
import pytest
import respx

pytestmark = pytest.mark.unit

DK_BASE = "https://dkstock.cloud"
LOGIN_URL = DK_BASE + "/api/auth/login"
REFRESH_URL = DK_BASE + "/api/auth/refresh"
MACRO_CYCLE_URL = DK_BASE + "/api/macro/macro-cycle"
SENTIMENT_URL = DK_BASE + "/api/macro/sentiment"


def _login_resp(access: str = "access-1", refresh: str = "refresh-1") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "user": {"username": "autostock", "role": "bot"},
        },
        headers={"content-type": "application/json"},
    )


def _macro_cycle_resp() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "cycle": {"phase": "expansion", "phase_label": "확장기", "scores": {}},
            "regime": {
                "regime": "defensive",
                "regime_desc": "방어 (공포 현금)",
                "params": {"margin": 999, "stock_max": 25, "cash_min": 75, "single_cap": 0, "per_max": 0, "pbr_max": 0, "roe_min": 0},
                "vix": 18.43,
                "fear_greed_score": 76.0,
                "buffett_level": "extreme",
                "fg_level": "greed",
            },
        },
        headers={"content-type": "application/json"},
    )


@pytest.fixture
def reset_dkstock_singleton():
    from src.services import dkstock_client as dc

    dc._client_instance = None
    yield
    inst = dc._client_instance
    if inst is not None:
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(inst.close())
        except Exception:
            pass
    dc._client_instance = None


# ---------------------------------------------------------------------------
# B1-G: DKSTOCK_REGIME_ENABLED=false → ConfigError
# ---------------------------------------------------------------------------
async def test_b1g_when_disabled_then_raises_config_error(reset_dkstock_singleton):
    from src.services.dkstock_client import DkstockClient
    from src.services.exceptions import ConfigError

    client = DkstockClient(
        base_url=DK_BASE,
        username="autostock",
        password="AUTOSTOCK1",
        enabled=False,
    )
    with pytest.raises(ConfigError):
        await client.get_macro_cycle()
    await client.close()


# ---------------------------------------------------------------------------
# B1-A: 정상 login
# ---------------------------------------------------------------------------
async def test_b1a_login_normal(reset_dkstock_singleton):
    from src.services.dkstock_client import DkstockClient

    client = DkstockClient(
        base_url=DK_BASE,
        username="autostock",
        password="AUTOSTOCK1",
        enabled=True,
    )
    with respx.mock(assert_all_called=True) as router:
        router.post(LOGIN_URL).mock(return_value=_login_resp("access-1", "refresh-1"))

        await client.login()

    assert client._access_token == "access-1"
    assert client._refresh_token == "refresh-1"
    await client.close()


# ---------------------------------------------------------------------------
# B1-B: 401 잘못된 자격증명 → ExternalAPIError
# ---------------------------------------------------------------------------
async def test_b1b_login_401_raises_external_api_error(reset_dkstock_singleton):
    from src.services.dkstock_client import DkstockClient
    from src.services.exceptions import ExternalAPIError

    client = DkstockClient(
        base_url=DK_BASE,
        username="autostock",
        password="WRONG_PASSWORD",
        enabled=True,
    )
    with respx.mock(assert_all_called=True) as router:
        router.post(LOGIN_URL).mock(
            return_value=httpx.Response(401, json={"detail": "Incorrect username or password"})
        )

        with pytest.raises(ExternalAPIError):
            await client.login()
    await client.close()


# ---------------------------------------------------------------------------
# B1-E: get_macro_cycle 정상 파싱
# ---------------------------------------------------------------------------
async def test_b1e_get_macro_cycle_parses_response(reset_dkstock_singleton):
    from src.services.dkstock_client import DkstockClient

    client = DkstockClient(
        base_url=DK_BASE,
        username="autostock",
        password="AUTOSTOCK1",
        enabled=True,
    )
    with respx.mock(assert_all_called=True) as router:
        router.post(LOGIN_URL).mock(return_value=_login_resp())
        router.get(MACRO_CYCLE_URL).mock(return_value=_macro_cycle_resp())

        data = await client.get_macro_cycle()

    assert data["regime"]["regime"] == "defensive"
    assert data["regime"]["params"]["cash_min"] == 75
    assert data["cycle"]["phase"] == "expansion"
    assert data["regime"]["vix"] == 18.43
    await client.close()


# ---------------------------------------------------------------------------
# B1-C: 만료 토큰(첫 401 → refresh 후 200) → 자동 재시도
# ---------------------------------------------------------------------------
async def test_b1c_expired_token_then_refresh_and_retry(reset_dkstock_singleton):
    from src.services.dkstock_client import DkstockClient

    client = DkstockClient(
        base_url=DK_BASE,
        username="autostock",
        password="AUTOSTOCK1",
        enabled=True,
    )
    # 사전 access_token 설정 (login 우회 — 이미 로그인된 상태 모킹)
    client._access_token = "stale-access"
    client._refresh_token = "valid-refresh"

    with respx.mock(assert_all_called=True) as router:
        # 1차 macro-cycle 호출 → 401 (access 만료)
        # refresh 호출 → 새 access
        # 2차 macro-cycle 재시도 → 200
        macro_route = router.get(MACRO_CYCLE_URL).mock(
            side_effect=[
                httpx.Response(401, json={"detail": "Token expired"}),
                _macro_cycle_resp(),
            ]
        )
        refresh_route = router.post(REFRESH_URL).mock(
            return_value=httpx.Response(
                200,
                json={"access_token": "new-access", "token_type": "bearer"},
            )
        )

        data = await client.get_macro_cycle()

    assert macro_route.call_count == 2
    assert refresh_route.call_count == 1
    assert client._access_token == "new-access"
    assert data["regime"]["regime"] == "defensive"
    await client.close()


# ---------------------------------------------------------------------------
# B1-D: refresh_token 만료 → ExternalAPIError (운영자 안내 메시지)
# ---------------------------------------------------------------------------
async def test_b1d_refresh_token_expired_raises_with_operator_hint(reset_dkstock_singleton):
    from src.services.dkstock_client import DkstockClient
    from src.services.exceptions import ExternalAPIError

    client = DkstockClient(
        base_url=DK_BASE,
        username="autostock",
        password="AUTOSTOCK1",
        enabled=True,
    )
    client._access_token = "stale-access"
    client._refresh_token = "expired-refresh"

    with respx.mock(assert_all_called=True) as router:
        router.get(MACRO_CYCLE_URL).mock(
            return_value=httpx.Response(401, json={"detail": "Token expired"})
        )
        router.post(REFRESH_URL).mock(
            return_value=httpx.Response(401, json={"detail": "Refresh token expired"})
        )

        with pytest.raises(ExternalAPIError) as exc_info:
            await client.get_macro_cycle()

    # 운영자 SSH 갱신 안내 (한국어/EC2 키워드)
    msg = str(exc_info.value)
    assert "refresh" in msg.lower() or "갱신" in msg or "재로그인" in msg
    await client.close()


# ---------------------------------------------------------------------------
# B1-F: 외부 서버 다운 (ConnectError) → ExternalAPIError
# ---------------------------------------------------------------------------
async def test_b1f_connect_error_raises_external_api_error(reset_dkstock_singleton):
    from src.services.dkstock_client import DkstockClient
    from src.services.exceptions import ExternalAPIError

    client = DkstockClient(
        base_url=DK_BASE,
        username="autostock",
        password="AUTOSTOCK1",
        enabled=True,
    )
    with respx.mock(assert_all_called=True) as router:
        router.post(LOGIN_URL).mock(side_effect=httpx.ConnectError("server down"))

        with pytest.raises(ExternalAPIError):
            await client.get_macro_cycle()
    await client.close()


# ---------------------------------------------------------------------------
# 싱글톤 헬퍼
# ---------------------------------------------------------------------------
async def test_get_dkstock_client_returns_same_instance(reset_dkstock_singleton):
    from src.services.dkstock_client import get_dkstock_client

    c1 = get_dkstock_client()
    c2 = get_dkstock_client()
    assert c1 is c2
    await c1.close()
