"""KIS OAuth 토큰 발급/갱신/폐기 관리.

사이클 7-A (2026-05-17) — multi-account 지원:
- 기존 `token_manager` (메인 계좌) 흐름은 100% 보존. 매매/잔고/체결통보는 메인 단일.
- `get_token_manager(label)` 로 보조 계좌(`kis_quote_accounts`) 토큰 매니저 lazy 발급.
- 보조 매니저는 자체 캐시 파일(`.token_cache_quote_<label>.json`)과 격리된 토큰/만료시각 보유.
- 보조 매니저 예외는 메인 흐름에 영향 0 — try/except 로 분리 호출 권장.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_TOKEN_CACHE_PATH = Path(".token_cache.json")
# 사이클 7-A — 보조 계좌 캐시 파일 prefix. 라벨별로 격리.
_QUOTE_TOKEN_CACHE_PREFIX = ".token_cache_quote_"


class TokenManager:
    """접근토큰(access_token) 발급, 캐시, 만료 전 자동 갱신을 담당한다.

    사이클 7-A — 보조 계좌 지원을 위해 ``app_key`` / ``app_secret`` / ``base_url`` /
    ``cache_path`` 를 선택적으로 주입 가능. 인자 미지정 시 기존 동작(메인 계좌
    ``settings.kis_app_key`` / ``settings.kis_app_secret`` / ``settings.kis_base_url``)
    100% 보존.
    """

    def __init__(
        self,
        *,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        cache_path: Optional[Path] = None,
        label: Optional[str] = None,
    ) -> None:
        # label=None → 메인 매니저 (기존 동작). 인자 미지정 시 settings.* 폴백.
        self._label = label
        self._app_key_override = app_key
        self._app_secret_override = app_secret
        self._base_url_override = base_url
        self._cache_path = cache_path or _TOKEN_CACHE_PATH

        self.access_token: str = ""
        self.token_expired: datetime | None = None
        self._load_cache()

    # -- 자격증명 접근 (메인 기본값 / 보조 override 통합) ----------------
    @property
    def app_key(self) -> str:
        return self._app_key_override if self._app_key_override is not None else settings.kis_app_key

    @property
    def app_secret(self) -> str:
        return self._app_secret_override if self._app_secret_override is not None else settings.kis_app_secret

    @property
    def base_url(self) -> str:
        return self._base_url_override if self._base_url_override is not None else settings.kis_base_url

    @property
    def label(self) -> Optional[str]:
        return self._label

    # -- public ---------------------------------------------------------

    async def get_token(self) -> str:
        """유효한 접근토큰을 반환한다. 만료 10분 전이면 자동 갱신."""
        if self._is_valid():
            return self.access_token
        await self.issue()
        return self.access_token

    async def issue(self) -> None:
        """POST /oauth2/tokenP 로 접근토큰을 발급받는다."""
        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, timeout=10)
            resp.raise_for_status()
            data = resp.json()

        self.access_token = data["access_token"]
        self.token_expired = datetime.strptime(
            data["access_token_token_expired"], "%Y-%m-%d %H:%M:%S"
        )
        self._save_cache()
        logger.info(
            "토큰 발급 완료(label=%s), 만료: %s", self._label or "main", self.token_expired
        )

    async def revoke(self) -> None:
        """POST /oauth2/revokeP 로 접근토큰을 폐기한다."""
        if not self.access_token:
            return
        url = f"{self.base_url}/oauth2/revokeP"
        body = {
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "token": self.access_token,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, timeout=10)
            resp.raise_for_status()

        self.access_token = ""
        self.token_expired = None
        self._delete_cache()
        logger.info("토큰 폐기 완료(label=%s)", self._label or "main")

    async def get_approval_key(self) -> str:
        """POST /oauth2/Approval 로 WebSocket 접속키를 발급받는다."""
        url = f"{self.base_url}/oauth2/Approval"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.app_secret,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, timeout=10)
            resp.raise_for_status()
            data = resp.json()

        logger.info("WebSocket 접속키 발급 완료(label=%s)", self._label or "main")
        return data["approval_key"]

    def build_headers(self, tr_id: str, *, hashkey: str = "") -> dict[str, str]:
        """KIS REST API 공통 헤더를 구성한다.

        주의: 본 메서드는 메인 매니저 경로에서만 호출되어야 한다. 보조 매니저는
        시세 수신 전용이라 매매 헤더 구성에 사용 금지.
        """
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": settings.get_tr_id(tr_id),
            "custtype": "P",
        }
        if hashkey:
            headers["hashkey"] = hashkey
        return headers

    # -- private --------------------------------------------------------

    def _is_valid(self) -> bool:
        if not self.access_token or not self.token_expired:
            return False
        return datetime.now() < self.token_expired - timedelta(minutes=10)

    def _save_cache(self) -> None:
        data = {
            "access_token": self.access_token,
            "token_expired": self.token_expired.isoformat() if self.token_expired else None,
        }
        self._cache_path.write_text(json.dumps(data), encoding="utf-8")

    def _load_cache(self) -> None:
        if not self._cache_path.exists():
            return
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            self.access_token = data.get("access_token", "")
            expired_str = data.get("token_expired")
            if expired_str:
                self.token_expired = datetime.fromisoformat(expired_str)
            if self._is_valid():
                logger.info(
                    "캐시 토큰 로드 완료(label=%s), 만료: %s",
                    self._label or "main", self.token_expired,
                )
            else:
                self.access_token = ""
                self.token_expired = None
        except (json.JSONDecodeError, KeyError):
            self.access_token = ""
            self.token_expired = None

    def _delete_cache(self) -> None:
        if self._cache_path.exists():
            self._cache_path.unlink()


# ---------------------------------------------------------------------------
# 메인 매니저 (기존 인스턴스 — 변경 금지)
# ---------------------------------------------------------------------------
token_manager = TokenManager()


# ---------------------------------------------------------------------------
# 사이클 7-A — 보조 시세 수신 계좌 토큰 매니저 multi-account
# ---------------------------------------------------------------------------
# label 별 싱글톤. DB 에서 자격증명 lazy 로드 후 격리된 캐시 파일 사용.
_quote_token_managers: dict[str, TokenManager] = {}
_quote_lock = asyncio.Lock()


def _safe_cache_filename(label: str) -> Path:
    """label → 안전한 파일명 변환 (경로 문자/공백 차단)."""
    safe = "".join(ch if (ch.isalnum() or ch in ("-", "_")) else "_" for ch in label)
    return Path(f"{_QUOTE_TOKEN_CACHE_PREFIX}{safe}.json")


def _resolve_base_url(kis_env: str) -> str:
    """kis_env('real'/'vts') → 도메인 분기 (settings 모듈 상수 활용)."""
    if kis_env == "real":
        return "https://openapi.koreainvestment.com:9443"
    return "https://openapivts.koreainvestment.com:29443"


async def get_token_manager(label: Optional[str] = None) -> TokenManager:
    """label 별 토큰 매니저 조회 (lazy 초기화).

    - ``label=None`` → 메인 매니저 (기존 ``token_manager`` 인스턴스).
    - ``label="quote-1"`` → 보조 매니저. DB(``kis_quote_accounts``) 에서 자격증명 로드.
        - 미등록 label / active=False → ``ValueError``.
        - 같은 label 두 번째 호출 → 동일 인스턴스 (싱글톤).
    - 보조 매니저는 격리된 캐시 파일 사용 — 메인 캐시 영향 0.
    - 본 함수는 async 락으로 동시 호출 race 차단.
    """
    if label is None:
        return token_manager

    async with _quote_lock:
        existing = _quote_token_managers.get(label)
        if existing is not None:
            return existing

        # DB 에서 자격증명 lazy 로드 — import 지연(circular 방지)
        from src.db import kis_quote_accounts as kqa

        creds = await kqa.get_credentials_for_token_manager(label)
        if creds is None:
            raise ValueError(
                f"보조 시세 계좌 미등록 또는 비활성: label={label!r} "
                "(DB kis_quote_accounts 확인)"
            )

        manager = TokenManager(
            app_key=creds["app_key"],
            app_secret=creds["app_secret"],
            base_url=_resolve_base_url(creds["kis_env"]),
            cache_path=_safe_cache_filename(label),
            label=label,
        )
        _quote_token_managers[label] = manager
        logger.info("[token] 보조 매니저 초기화: label=%s env=%s", label, creds["kis_env"])
        return manager


def reset_quote_token_managers() -> None:
    """테스트/재기동용 — 보조 매니저 캐시 dict 초기화. 운영 코드에서 호출 금지."""
    _quote_token_managers.clear()
