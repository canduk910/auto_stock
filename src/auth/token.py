"""KIS OAuth 토큰 발급/갱신/폐기 관리."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_TOKEN_CACHE_PATH = Path(".token_cache.json")


class TokenManager:
    """접근토큰(access_token) 발급, 캐시, 만료 전 자동 갱신을 담당한다."""

    def __init__(self) -> None:
        self.access_token: str = ""
        self.token_expired: datetime | None = None
        self._load_cache()

    # -- public ---------------------------------------------------------

    async def get_token(self) -> str:
        """유효한 접근토큰을 반환한다. 만료 10분 전이면 자동 갱신."""
        if self._is_valid():
            return self.access_token
        await self.issue()
        return self.access_token

    async def issue(self) -> None:
        """POST /oauth2/tokenP 로 접근토큰을 발급받는다."""
        url = f"{settings.kis_base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
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
        logger.info("토큰 발급 완료, 만료: %s", self.token_expired)

    async def revoke(self) -> None:
        """POST /oauth2/revokeP 로 접근토큰을 폐기한다."""
        if not self.access_token:
            return
        url = f"{settings.kis_base_url}/oauth2/revokeP"
        body = {
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
            "token": self.access_token,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, timeout=10)
            resp.raise_for_status()

        self.access_token = ""
        self.token_expired = None
        self._delete_cache()
        logger.info("토큰 폐기 완료")

    async def get_approval_key(self) -> str:
        """POST /oauth2/Approval 로 WebSocket 접속키를 발급받는다."""
        url = f"{settings.kis_base_url}/oauth2/Approval"
        body = {
            "grant_type": "client_credentials",
            "appkey": settings.kis_app_key,
            "secretkey": settings.kis_app_secret,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, timeout=10)
            resp.raise_for_status()
            data = resp.json()

        logger.info("WebSocket 접속키 발급 완료")
        return data["approval_key"]

    def build_headers(self, tr_id: str, *, hashkey: str = "") -> dict[str, str]:
        """KIS REST API 공통 헤더를 구성한다."""
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
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
        _TOKEN_CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")

    def _load_cache(self) -> None:
        if not _TOKEN_CACHE_PATH.exists():
            return
        try:
            data = json.loads(_TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
            self.access_token = data.get("access_token", "")
            expired_str = data.get("token_expired")
            if expired_str:
                self.token_expired = datetime.fromisoformat(expired_str)
            if self._is_valid():
                logger.info("캐시 토큰 로드 완료, 만료: %s", self.token_expired)
            else:
                self.access_token = ""
                self.token_expired = None
        except (json.JSONDecodeError, KeyError):
            self.access_token = ""
            self.token_expired = None

    def _delete_cache(self) -> None:
        if _TOKEN_CACHE_PATH.exists():
            _TOKEN_CACHE_PATH.unlink()


token_manager = TokenManager()
