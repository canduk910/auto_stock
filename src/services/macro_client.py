"""매크로 레짐 클라이언트 — 우리 `macro` 컨테이너(`http://macro:8000`).

매크로 지표(경기사이클 + 투자체제)는 `macro/` 컨테이너가 계산한다. 같은 코드
(`macro_lite`)를 우리 인프라 안에서 돌리므로 `/api/macro/macro-cycle` 응답 shape 는
`MarketRegime.from_macro_cycle` 이 파싱하던 것과 동일하다.

특징:
- ``httpx.AsyncClient`` 기반 async 일관성 (KIS REST / 백테스트 MCP 와 동일)
- 모듈 레벨 싱글톤(`_client_instance`) — 커넥션 풀 재사용
- 🔴 **인증 없음** — 컨테이너 내부 네트워크 전용이라 로그인 절차가 없다. 토큰·헤더
  주입 코드를 되살리지 않는다(평문 자격을 코드에 두는 것 자체가 결함이다)
- 활성 여부는 DB(`system_config.dkstock_regime_enabled`) 우선 / `.env`
  (`DKSTOCK_REGIME_ENABLED`) fallback. 🔴 **키 네이밍은 유지한다** — 운영 DB 에 이미
  `true` 행이 있고, 개명하면 그 행이 고아가 된다
- 비활성이면 모든 메서드가 ``ConfigError`` 즉시 raise (호출자 graceful degrade)
- 24h 메모리 캐시 — `_boot` 1회 호출 이후 같은 영업일 중복 호출은 캐시 hit

운영 graceful 정책:
- ``ExternalAPIError`` 는 호출자 ``market_regime.refresh_from_dkstock()`` 이 흡수한다
  → 레짐 관찰 비활성 + ``cash_usage_ratio`` 운영자 수동값 보존 → 매매 본 흐름 영향 0
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from src.config import settings
from src.services.exceptions import ConfigError, ExternalAPIError

logger = logging.getLogger(__name__)


# 캐시 TTL — _boot 1회 fetch 후 같은 영업일 (24h) 동안 같은 응답 재사용
_CACHE_TTL_SECS = 24 * 60 * 60

_DISABLED_MSG = (
    "매크로 레짐 클라이언트가 비활성화되어 있습니다. "
    "DKSTOCK_REGIME_ENABLED=true 또는 system_config.dkstock_regime_enabled=true 로 설정하세요."
)


class MacroClient:
    """우리 macro 컨테이너 REST 클라이언트 (async, 무인증)."""

    def __init__(
        self,
        base_url: str,
        enabled: bool,
        timeout: dict | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._enabled = enabled
        t = timeout or {}
        self._timeout = httpx.Timeout(
            connect=t.get("connect", 5.0),
            # 🔴 read 기본값은 `settings` 에서 읽는다 — 리터럴을 여기 또 박으면 설정을 올렸을 때
            #    팩토리를 거치지 않는 테스트만 옛 값으로 돌아 조용히 갈린다.
            read=t.get("read", settings.macro_api_read_timeout_secs),
            write=t.get("write", 10.0),
            pool=t.get("pool", 10.0),
        )
        self._http: httpx.AsyncClient | None = None
        # 24h 메모리 캐시: {endpoint_key: (fetched_at, data)}
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------
    async def _check_enabled_async(self) -> bool:
        """DB 우선 / `.env` fallback 활성 여부 평가.

        결정 순서:
        1. `system_config.get_dkstock_regime_enabled()` 가 True/False → DB 값 채택.
        2. None (키 부재) 또는 예외 → 생성자 주입 `self._enabled` (= .env) fallback.

        예외 흡수 — DB 다운 / 네트워크 단절 시에도 `.env` fallback 으로 graceful.
        반환값은 호출자가 활성 분기 결정에 쓴다 (raise 는 호출자 책임).
        """
        try:
            from src.db.system_config import get_dkstock_regime_enabled

            db_value = await get_dkstock_regime_enabled()
            if db_value is not None:
                return bool(db_value)
        except Exception:
            logger.exception(
                "[macro] DB toggle 조회 실패 — .env fallback 사용 (enabled=%s)",
                self._enabled,
            )
        return bool(self._enabled)

    def _get_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            try:
                await self._http.aclose()
            except Exception:
                pass
            self._http = None

    # ------------------------------------------------------------------
    # GET (무인증)
    # ------------------------------------------------------------------
    async def _get(self, path: str) -> dict[str, Any]:
        """``GET {base_url}{path}``. 비활성이면 ConfigError, 그 밖 실패는 ExternalAPIError."""
        if not await self._check_enabled_async():
            raise ConfigError(_DISABLED_MSG)

        url = f"{self._base_url}{path}"
        try:
            resp = await self._get_client().get(url)
        except httpx.HTTPError as e:
            # ReadTimeout / ConnectError 모두 httpx.HTTPError 하위다.
            raise ExternalAPIError(f"macro GET {path} 통신 실패: {e}") from e

        if resp.status_code >= 400:
            raise ExternalAPIError(
                f"macro GET {path} HTTP {resp.status_code}: {resp.text[:200]}"
            )
        try:
            return resp.json()
        except Exception as e:
            raise ExternalAPIError(f"macro GET {path} JSON 파싱 실패: {e}") from e

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

        형식: ``{cycle: {phase, phase_label, scores, ...},
        regime: {regime, regime_desc, params{cash_min, ...}, vix, buffett_ratio,
        fear_greed_score, ...}, updated_at, errors}``.
        """
        cached = self._cache_get("macro_cycle")
        if cached is not None:
            return cached
        data = await self._get("/api/macro/macro-cycle")
        self._cache_put("macro_cycle", data)
        return data

    def clear_cache(self) -> None:
        """캐시 강제 클리어 (테스트/디버깅용)."""
        self._cache.clear()


# ---------------------------------------------------------------------------
# 싱글톤 헬퍼
# ---------------------------------------------------------------------------
_client_instance: MacroClient | None = None


def get_macro_client() -> MacroClient:
    """모듈 레벨 싱글톤 — 첫 호출 시 settings 기반 인스턴스 생성."""
    global _client_instance
    if _client_instance is None:
        _client_instance = MacroClient(
            base_url=settings.macro_api_url,
            enabled=settings.dkstock_regime_enabled,
            timeout={"read": settings.macro_api_read_timeout_secs},
        )
    return _client_instance
