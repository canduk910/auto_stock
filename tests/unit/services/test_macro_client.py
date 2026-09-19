"""cycle315 Red — `src/services/macro_client.py` (우리 macro 컨테이너 매크로 클라이언트).

외부 `dkstock.cloud` 는 2026-08-18 철거됐고, 같은 코드(macro_lite)를 우리 컨테이너
(`http://macro:8000`)에서 돌린다. 응답 shape 가 같으므로 파싱 계약은 그대로다.

여기서 고정하는 계약:
- (a) `/api/macro/macro-cycle` 200 → 실물 payload 를 그대로 반환
- (b) 🔴 **인증 없음** — macro 컨테이너에는 로그인이 없다. respx 에 macro-cycle 하나만
      등록하고 `assert_all_called=True` 로 두면, 클라이언트가 `/api/auth/login` 을 치는
      순간 미등록 요청으로 즉시 붉어진다
- (c) 활성 판정은 DB 우선 / `.env` fallback (`dkstock_regime_enabled` 네이밍 유지 —
      운영 DB 의 `true` 행이 고아가 되지 않도록 키는 그대로 둔다)
- (d) 비활성 → `ConfigError`
- (e) 4xx/5xx · JSON 파싱 실패 → `ExternalAPIError`
- (f) 24h 메모리 캐시 hit 시 HTTP 0회
- (g) `httpx.ReadTimeout` → `ExternalAPIError`
- (h) read 타임아웃은 `settings.macro_api_read_timeout_secs`(기본 90.0)에서 주입
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

pytestmark = pytest.mark.unit

MACRO_BASE = "http://macro:8000"
MACRO_CYCLE_URL = MACRO_BASE + "/api/macro/macro-cycle"

# 2026-09-19 우리 macro 컨테이너 실물 응답 스냅샷
_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "macro_cycle_live.json"
LIVE_MACRO_CYCLE = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _live_resp() -> httpx.Response:
    return httpx.Response(
        200,
        json=LIVE_MACRO_CYCLE,
        headers={"content-type": "application/json"},
    )


def _make_client(enabled: bool = True):
    from src.services.macro_client import MacroClient

    return MacroClient(base_url=MACRO_BASE, enabled=enabled)


@pytest.fixture
def db_toggle_absent(monkeypatch: pytest.MonkeyPatch):
    """DB 토글 키 부재(None) — `.env` fallback 경로로 고정."""
    from src.db import system_config

    async def _none():
        return None

    monkeypatch.setattr(system_config, "get_dkstock_regime_enabled", _none)


@pytest.fixture
def reset_macro_singleton():
    from src.services import macro_client as mc

    mc._client_instance = None
    yield
    mc._client_instance = None


# ---------------------------------------------------------------------------
# (a) + (b) 실물 payload 반환 + 인증 없음 계약
# ---------------------------------------------------------------------------
async def test_a_get_macro_cycle_returns_live_payload(db_toggle_absent):
    client = _make_client(enabled=True)
    # assert_all_called=True + macro-cycle 단일 등록 = 로그인 호출이 있으면 즉시 실패
    with respx.mock(assert_all_called=True) as router:
        route = router.get(MACRO_CYCLE_URL).mock(return_value=_live_resp())

        data = await client.get_macro_cycle()

    assert route.call_count == 1
    assert data == LIVE_MACRO_CYCLE
    assert data["regime"]["regime"] == "defensive"
    assert data["regime"]["params"]["cash_min"] == 75
    assert data["regime"]["vix"] == 14.81
    assert data["regime"]["buffett_ratio"] == 2.626
    assert data["regime"]["fear_greed_score"] == 69.0
    assert data["regime"]["credit_adjustment"] == "greed_one_step"
    assert data["cycle"]["phase"] == "expansion"
    await client.close()


async def test_b_no_auth_endpoints_are_called(db_toggle_absent):
    """🔴 인증 없음을 계약으로 고정 — 어떤 auth 경로도 치지 않는다."""
    client = _make_client(enabled=True)
    with respx.mock(assert_all_called=True) as router:
        router.get(MACRO_CYCLE_URL).mock(return_value=_live_resp())

        await client.get_macro_cycle()

        called_paths = [call.request.url.path for call in router.calls]

    assert called_paths == ["/api/macro/macro-cycle"]
    # 모듈 소스에도 JWT 잔재가 없어야 한다 (복붙 회귀 차단)
    import inspect

    from src.services import macro_client as mc

    src = inspect.getsource(mc)
    for forbidden in ("/api/auth/login", "/api/auth/refresh", "Authorization", "Bearer"):
        assert forbidden not in src, f"macro_client 에 인증 잔재: {forbidden}"
    await client.close()


# ---------------------------------------------------------------------------
# (c) DB 우선 / .env fallback — 기존 dkstock_client_db_toggle 케이스 이식
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c1_db_true_overrides_env_false(monkeypatch: pytest.MonkeyPatch):
    from src.db import system_config

    async def _true():
        return True

    monkeypatch.setattr(system_config, "get_dkstock_regime_enabled", _true)
    client = _make_client(enabled=False)
    assert await client._check_enabled_async() is True


@pytest.mark.asyncio
async def test_c2_db_false_overrides_env_true(monkeypatch: pytest.MonkeyPatch):
    from src.db import system_config

    async def _false():
        return False

    monkeypatch.setattr(system_config, "get_dkstock_regime_enabled", _false)
    client = _make_client(enabled=True)
    assert await client._check_enabled_async() is False


@pytest.mark.asyncio
async def test_c3_db_none_falls_back_to_env(monkeypatch: pytest.MonkeyPatch):
    from src.db import system_config

    async def _none():
        return None

    monkeypatch.setattr(system_config, "get_dkstock_regime_enabled", _none)
    assert await _make_client(enabled=True)._check_enabled_async() is True
    assert await _make_client(enabled=False)._check_enabled_async() is False


@pytest.mark.asyncio
async def test_c4_db_value_change_is_reflected_immediately(monkeypatch: pytest.MonkeyPatch):
    """캐시 없이 매 호출 조회 — 운영자 즉시 ON/OFF 보장."""
    from src.db import system_config

    state = {"value": False}

    async def _dynamic():
        return state["value"]

    monkeypatch.setattr(system_config, "get_dkstock_regime_enabled", _dynamic)
    client = _make_client(enabled=False)

    assert await client._check_enabled_async() is False
    state["value"] = True
    assert await client._check_enabled_async() is True
    state["value"] = False
    assert await client._check_enabled_async() is False


@pytest.mark.asyncio
async def test_c5_db_exception_falls_back_to_env(monkeypatch: pytest.MonkeyPatch):
    """DB 조회 예외 → .env fallback (graceful)."""
    from src.db import system_config

    async def _boom():
        raise RuntimeError("DB connection failed")

    monkeypatch.setattr(system_config, "get_dkstock_regime_enabled", _boom)
    client = _make_client(enabled=True)
    assert await client._check_enabled_async() is True


# ---------------------------------------------------------------------------
# (d) 비활성 → ConfigError
# ---------------------------------------------------------------------------
async def test_d_disabled_raises_config_error(db_toggle_absent):
    from src.services.exceptions import ConfigError

    client = _make_client(enabled=False)
    with pytest.raises(ConfigError):
        await client.get_macro_cycle()
    await client.close()


# ---------------------------------------------------------------------------
# (e) 4xx/5xx · JSON 파싱 실패 → ExternalAPIError
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status", [400, 404, 500, 503])
async def test_e1_http_error_raises_external_api_error(db_toggle_absent, status: int):
    from src.services.exceptions import ExternalAPIError

    client = _make_client(enabled=True)
    with respx.mock(assert_all_called=True) as router:
        router.get(MACRO_CYCLE_URL).mock(
            return_value=httpx.Response(status, text="boom")
        )
        with pytest.raises(ExternalAPIError):
            await client.get_macro_cycle()
    await client.close()


async def test_e2_json_parse_failure_raises_external_api_error(db_toggle_absent):
    from src.services.exceptions import ExternalAPIError

    client = _make_client(enabled=True)
    with respx.mock(assert_all_called=True) as router:
        router.get(MACRO_CYCLE_URL).mock(
            return_value=httpx.Response(
                200, text="<html>not json</html>",
                headers={"content-type": "text/html"},
            )
        )
        with pytest.raises(ExternalAPIError):
            await client.get_macro_cycle()
    await client.close()


# ---------------------------------------------------------------------------
# (f) 24h 메모리 캐시 — 2회차는 HTTP 0회
# ---------------------------------------------------------------------------
async def test_f_cache_hit_skips_http(db_toggle_absent):
    client = _make_client(enabled=True)
    with respx.mock(assert_all_called=True) as router:
        route = router.get(MACRO_CYCLE_URL).mock(return_value=_live_resp())

        first = await client.get_macro_cycle()
        second = await client.get_macro_cycle()

    assert route.call_count == 1
    assert first == second == LIVE_MACRO_CYCLE

    client.clear_cache()
    with respx.mock(assert_all_called=True) as router:
        route2 = router.get(MACRO_CYCLE_URL).mock(return_value=_live_resp())
        await client.get_macro_cycle()
    assert route2.call_count == 1
    await client.close()


# ---------------------------------------------------------------------------
# (g) ReadTimeout → ExternalAPIError
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "exc",
    [
        httpx.ReadTimeout("read timed out"),
        # macro 컨테이너가 아직 안 떴거나 죽었을 때. 같은 `except httpx.HTTPError` 분기지만
        # 구 dkstock 클라이언트가 이 케이스를 따로 지키고 있었으므로 계약을 그대로 가져온다.
        httpx.ConnectError("macro down"),
    ],
    ids=["read_timeout", "connect_error"],
)
async def test_g_transport_failures_raise_external_api_error(db_toggle_absent, exc):
    from src.services.exceptions import ExternalAPIError

    client = _make_client(enabled=True)
    with respx.mock(assert_all_called=True) as router:
        router.get(MACRO_CYCLE_URL).mock(side_effect=exc)
        with pytest.raises(ExternalAPIError):
            await client.get_macro_cycle()
    await client.close()


# ---------------------------------------------------------------------------
# (h) read 타임아웃 = settings.macro_api_read_timeout_secs (기본 90.0)
# ---------------------------------------------------------------------------
def test_h1_settings_defaults():
    from src.config import Settings

    s = Settings()
    assert s.macro_api_url == "http://macro:8000"
    assert s.macro_api_read_timeout_secs == pytest.approx(90.0)


def test_h2_factory_injects_read_timeout(reset_macro_singleton, monkeypatch):
    """`get_macro_client()` 는 settings 값을 read 타임아웃으로 주입한다.

    macro 의 첫 macro-cycle 호출은 실측 107초까지 걸린 적이 있어(prewarm 이전)
    30초 기본값으로는 매번 타임아웃이다.
    """
    from src.config import settings
    from src.services.macro_client import get_macro_client

    monkeypatch.setattr(settings, "macro_api_read_timeout_secs", 90.0, raising=False)
    monkeypatch.setattr(settings, "macro_api_url", MACRO_BASE, raising=False)

    c1 = get_macro_client()
    c2 = get_macro_client()
    assert c1 is c2  # 모듈 레벨 싱글톤
    assert c1._timeout.read == pytest.approx(90.0)
    assert c1._base_url == MACRO_BASE


def test_h3_dkstock_settings_fields_are_gone():
    """평문 자격 3필드는 삭제됐다 (macro 에는 인증이 없다)."""
    from src.config import Settings

    fields = set(Settings.model_fields)
    assert "dkstock_api_url" not in fields
    assert "dkstock_username" not in fields
    assert "dkstock_password" not in fields
    # 🔴 토글 키 네이밍은 유지 — 운영 DB 의 `dkstock_regime_enabled` 행과 짝이다
    assert "dkstock_regime_enabled" in fields


def test_h4_config_ignores_extra_env_keys():
    """운영 `.env` 에 DKSTOCK_* 잔존 줄이 있어도 기동이 실패하면 안 된다."""
    from src.config import Settings

    assert Settings.model_config.get("extra") == "ignore"


def test_h5_old_dkstock_client_module_is_gone():
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.services.dkstock_client")
