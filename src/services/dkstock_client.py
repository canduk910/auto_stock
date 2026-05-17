"""dkstock.cloud JWT Bearer 클라이언트 (사이클 2 — 시장 레짐 필터).

외부 매크로 서버(`https://dkstock.cloud`) 와 JWT Bearer 인증으로 통신한다.

특징:
- ``httpx.AsyncClient`` 기반 async 환경 일관성 (auto_stock 의 KIS REST / MCP 와 동일)
- 모듈 레벨 싱글톤(`_client_instance`) — 토큰 + 커넥션 풀 재사용
- 401 (access_token 만료) → ``/api/auth/refresh`` 1회 자동 재시도
- refresh_token 만료 시 운영자 SSH 재로그인 안내 메시지 동봉
- ``DKSTOCK_REGIME_ENABLED=false`` 면 모든 메서드가 ``ConfigError`` 즉시 raise
  (자동매매 핵심 흐름 영향 0, 호출자 graceful degrade)
- 24h 메모리 캐시 (`get_macro_cycle / get_sentiment / get_indices`) — _boot 1회 호출
  이후 같은 영업일 중복 호출 시 캐시 hit

참조 패턴: ``src/services/mcp_client.py`` (JSON-RPC → 단순 REST 로 단순화)

운영 graceful 정책:
- ``ExternalAPIError`` 발생 시 호출자 ``MarketRegime.refresh()`` 가 흡수 → 매수 가드
  비활성 + ``cash_usage_ratio`` 운영자 수동값 보존 → 자동매매 본 흐름 영향 0
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from src.config import settings
from src.services.exceptions import ConfigError, ExternalAPIError

logger = logging.getLogger(__name__)


# 캐시 TTL — _boot 1회 fetch 후 같은 영업일 (24h) 동안 같은 응답 재사용
_CACHE_TTL_SECS = 24 * 60 * 60

# 운영자 안내 — refresh_token 만료 시 단일 명시 메시지 (system_logs 영구 저장됨)
_REFRESH_EXPIRED_HINT = (
    "dkstock.cloud refresh_token 이 만료되었습니다. "
    "EC2 SSH 접속 후 운영자가 자격증명 재로그인 또는 새 토큰 발급이 필요합니다."
)


class DkstockClient:
    """dkstock.cloud REST 클라이언트 (async, JWT Bearer).

    인증 흐름:
    1. ``POST /api/auth/login`` → ``{access_token, refresh_token, token_type, user}``
    2. 이후 ``Authorization: Bearer {access_token}`` 헤더로 보호 endpoint 호출
    3. 401 (access 만료) → ``POST /api/auth/refresh`` (refresh_token 전송) → 새 access
    4. refresh_token 만료 → ``ExternalAPIError`` (운영자 SSH 재로그인 안내)
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        enabled: bool,
        timeout: dict | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._enabled = enabled
        t = timeout or {}
        self._timeout = httpx.Timeout(
            connect=t.get("connect", 5.0),
            read=t.get("read", 30.0),
            write=t.get("write", 10.0),
            pool=t.get("pool", 10.0),
        )
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None
        # 24h 메모리 캐시: {endpoint_key: (fetched_at, data)}
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------
    def _check_enabled(self) -> None:
        if not self._enabled:
            raise ConfigError(
                "dkstock.cloud 매크로 클라이언트가 비활성화되어 있습니다. "
                "DKSTOCK_REGIME_ENABLED=true 로 설정하세요."
            )

    def _get_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    def _auth_headers(self) -> dict[str, str]:
        if not self._access_token:
            return {}
        return {"Authorization": f"Bearer {self._access_token}"}

    async def close(self) -> None:
        if self._http is not None:
            try:
                await self._http.aclose()
            except Exception:
                pass
            self._http = None

    # ------------------------------------------------------------------
    # 인증
    # ------------------------------------------------------------------
    async def login(self) -> None:
        """``POST /api/auth/login`` 으로 access/refresh 토큰 발급.

        실패 시 ``ExternalAPIError`` raise. 호출자가 graceful degrade.
        """
        self._check_enabled()

        url = f"{self._base_url}/api/auth/login"
        payload = {"username": self._username, "password": self._password}
        try:
            resp = await self._get_client().post(url, json=payload)
        except httpx.HTTPError as e:
            raise ExternalAPIError(f"dkstock.cloud login 통신 실패: {e}") from e

        if resp.status_code == 401:
            raise ExternalAPIError(
                f"dkstock.cloud login 401 — 잘못된 자격증명 (username={self._username}). "
                f"사용자명/비밀번호 (대문자 필수) 확인 필요."
            )
        if resp.status_code >= 400:
            raise ExternalAPIError(
                f"dkstock.cloud login HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            body = resp.json()
        except Exception as e:
            raise ExternalAPIError(f"dkstock.cloud login JSON 파싱 실패: {e}") from e

        access = body.get("access_token")
        refresh = body.get("refresh_token")
        if not access:
            raise ExternalAPIError(
                f"dkstock.cloud login 응답에 access_token 누락: {body}"
            )
        self._access_token = access
        # refresh_token 은 응답에 없을 수도 있음 (서버 정책) — 기존 값 유지
        if refresh:
            self._refresh_token = refresh
        logger.info("[dkstock] login 성공 username=%s", self._username)

    async def refresh(self) -> None:
        """``POST /api/auth/refresh`` 로 access_token 갱신.

        실패 시 ``ExternalAPIError`` (운영자 SSH 재로그인 안내 포함).
        """
        self._check_enabled()
        if not self._refresh_token:
            raise ExternalAPIError(_REFRESH_EXPIRED_HINT)

        url = f"{self._base_url}/api/auth/refresh"
        # 서버 정책에 따라 body 또는 헤더 — 본 구현은 body
        payload = {"refresh_token": self._refresh_token}
        try:
            resp = await self._get_client().post(url, json=payload)
        except httpx.HTTPError as e:
            raise ExternalAPIError(f"dkstock.cloud refresh 통신 실패: {e}") from e

        if resp.status_code == 401:
            raise ExternalAPIError(_REFRESH_EXPIRED_HINT)
        if resp.status_code >= 400:
            raise ExternalAPIError(
                f"dkstock.cloud refresh HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            body = resp.json()
        except Exception as e:
            raise ExternalAPIError(f"dkstock.cloud refresh JSON 파싱 실패: {e}") from e

        new_access = body.get("access_token")
        if not new_access:
            raise ExternalAPIError(
                f"dkstock.cloud refresh 응답에 access_token 누락: {body}"
            )
        self._access_token = new_access
        # refresh_token rotation 지원 (응답에 있으면 갱신)
        new_refresh = body.get("refresh_token")
        if new_refresh:
            self._refresh_token = new_refresh
        logger.info("[dkstock] refresh 성공")

    # ------------------------------------------------------------------
    # 보호 GET (자동 토큰 갱신 1회 재시도)
    # ------------------------------------------------------------------
    async def _get(self, path: str) -> dict[str, Any]:
        """``GET {base_url}{path}`` + Bearer 헤더. 401 시 refresh 후 1회 재시도."""
        self._check_enabled()

        async with self._lock:
            if not self._access_token:
                await self.login()

        url = f"{self._base_url}{path}"

        async def _attempt() -> httpx.Response:
            try:
                return await self._get_client().get(url, headers=self._auth_headers())
            except httpx.HTTPError as e:
                raise ExternalAPIError(f"dkstock.cloud GET {path} 통신 실패: {e}") from e

        resp = await _attempt()

        # 401 → refresh 후 1회 재시도
        if resp.status_code == 401:
            logger.info("[dkstock] %s 401 — refresh 후 재시도", path)
            async with self._lock:
                await self.refresh()
            resp = await _attempt()

        if resp.status_code >= 400:
            raise ExternalAPIError(
                f"dkstock.cloud GET {path} HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            return resp.json()
        except Exception as e:
            raise ExternalAPIError(
                f"dkstock.cloud GET {path} JSON 파싱 실패: {e}"
            ) from e

    # ------------------------------------------------------------------
    # 캐시 헬퍼
    # ------------------------------------------------------------------
    def _cache_get(self, key: str) -> dict[str, Any] | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        fetched_at, data = entry
        if time.time() - fetched_at > _CACHE_TTL_SECS:
            self._cache.pop(key, None)
            return None
        return data

    def _cache_put(self, key: str, data: dict[str, Any]) -> None:
        self._cache[key] = (time.time(), data)

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------
    async def get_macro_cycle(self) -> dict[str, Any]:
        """``/api/macro/macro-cycle`` 응답 dict.

        형식: ``{cycle: {phase, phase_label, scores}, regime: {regime, regime_desc, params, vix, fear_greed_score, buffett_level, fg_level}}``
        """
        cached = self._cache_get("macro_cycle")
        if cached is not None:
            return cached
        data = await self._get("/api/macro/macro-cycle")
        self._cache_put("macro_cycle", data)
        return data

    async def get_sentiment(self) -> dict[str, Any]:
        """``/api/macro/sentiment`` 응답 dict (VIX/FearGreed/Buffett 상세)."""
        cached = self._cache_get("sentiment")
        if cached is not None:
            return cached
        data = await self._get("/api/macro/sentiment")
        self._cache_put("sentiment", data)
        return data

    async def get_indices(self) -> dict[str, Any]:
        """``/api/macro/indices`` 응답 dict (코스피/코스닥/VIX/S&P/NASDAQ sparkline)."""
        cached = self._cache_get("indices")
        if cached is not None:
            return cached
        data = await self._get("/api/macro/indices")
        self._cache_put("indices", data)
        return data

    def clear_cache(self) -> None:
        """캐시 강제 클리어 (테스트/디버깅용)."""
        self._cache.clear()


# ---------------------------------------------------------------------------
# 싱글톤 헬퍼
# ---------------------------------------------------------------------------
_client_instance: DkstockClient | None = None


def get_dkstock_client() -> DkstockClient:
    """모듈 레벨 싱글톤 — 첫 호출 시 settings 기반 인스턴스 생성."""
    global _client_instance
    if _client_instance is None:
        _client_instance = DkstockClient(
            base_url=settings.dkstock_api_url,
            username=settings.dkstock_username,
            password=settings.dkstock_password,
            enabled=settings.dkstock_regime_enabled,
        )
    return _client_instance
