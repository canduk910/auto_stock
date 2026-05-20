"""KIS OAuth 토큰 발급/갱신/폐기 관리.

사이클 7-A (2026-05-17) — multi-account 지원:
- 기존 `token_manager` (메인 계좌) 흐름은 100% 보존. 매매/잔고/체결통보는 메인 단일.
- `get_token_manager(label)` 로 보조 계좌(`kis_quote_accounts`) 토큰 매니저 lazy 발급.
- 보조 매니저는 자체 캐시 파일(`.token_cache/quote_<label>.json`)과 격리된 토큰/만료시각 보유.
- 보조 매니저 예외는 메인 흐름에 영향 0 — try/except 로 분리 호출 권장.

사이클 20 (2026-05-20) — 분당 1개 한도 위반 차단:
- KIS `/oauth2/tokenP` 는 분당 1개 / 전역 한도. 4 매니저 동시 발급 시 일부 403.
- 모듈 전역 `_GLOBAL_ISSUE_LOCK` + `_LAST_ISSUE_AT` + `_ISSUE_GAP_SECS=61.0` 으로 직렬화.
- `issue()` 진입 시 lock 획득 + gap 미달이면 sleep. 캐시 hit 시 `_is_valid()`→`issue()` skip → sleep 0.
- 캐시 영속화: `_TOKEN_CACHE_DIR=.token_cache/` 디렉토리 단위 (Docker 볼륨 마운트 친화).
  구 경로 `.token_cache.json` / `.token_cache_quote_<label>.json` 자동 마이그레이션 + 호환 fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# 사이클 20 (2026-05-20) — 디렉토리 단위 캐시 (Docker 볼륨 영속화)
_TOKEN_CACHE_DIR = Path(".token_cache")
_TOKEN_CACHE_PATH = _TOKEN_CACHE_DIR / "main.json"
# 구 경로 호환 fallback — 마이그레이션 시 1회 읽고 새 경로로 이동
_LEGACY_MAIN_CACHE_PATH = Path(".token_cache.json")
# 사이클 7-A — 보조 계좌 캐시 파일 prefix. 라벨별로 격리.
# 사이클 20 — 디렉토리 내 prefix 로 변경. 구 prefix `.token_cache_quote_` 는 fallback.
_QUOTE_TOKEN_CACHE_PREFIX = "quote_"
_LEGACY_QUOTE_CACHE_PREFIX = ".token_cache_quote_"


# ---------------------------------------------------------------------------
# 사이클 20 (2026-05-20) — 모듈 전역 발급 직렬화
# ---------------------------------------------------------------------------
# KIS `/oauth2/tokenP` 분당 1개 / 전역 한도. 모든 매니저(메인 + 보조) 가 공유.
# `issue()` 진입 시 lock 획득 → gap 미달이면 sleep → KIS POST → `_LAST_ISSUE_AT` 갱신.
# 캐시 hit (`_is_valid()=True`) 경로는 `get_token()` 이 `issue()` 호출 안 함 → lock/sleep 0.
_GLOBAL_ISSUE_LOCK: asyncio.Lock | None = None
_LAST_ISSUE_AT: float = 0.0  # time.monotonic()
_ISSUE_GAP_SECS: float = 61.0  # 분당 1개 보장 (1초 마진)


def _get_global_issue_lock() -> asyncio.Lock:
    """모듈 전역 lock — lazy create (이벤트루프 존재 후 안전 생성)."""
    global _GLOBAL_ISSUE_LOCK
    if _GLOBAL_ISSUE_LOCK is None:
        _GLOBAL_ISSUE_LOCK = asyncio.Lock()
    return _GLOBAL_ISSUE_LOCK


def reset_global_issue_state() -> None:
    """테스트 전용 — 모듈 전역 lock + 마지막 발급 시각 초기화."""
    global _GLOBAL_ISSUE_LOCK, _LAST_ISSUE_AT
    _GLOBAL_ISSUE_LOCK = None
    _LAST_ISSUE_AT = 0.0


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
        """POST /oauth2/tokenP 로 접근토큰을 발급받는다.

        사이클 20 (2026-05-20) — 모듈 전역 직렬화 + 60s gap (KIS 분당 1개 한도).
        Lock 안에서 sleep 이므로 다음 매니저는 자연 대기. KIS 부담 0.
        `_LAST_ISSUE_AT` 는 HTTP POST 성공 *후* 갱신 — 실패 시 재발급 시도 가능.
        """
        global _LAST_ISSUE_AT
        async with _get_global_issue_lock():
            elapsed = time.monotonic() - _LAST_ISSUE_AT
            if _LAST_ISSUE_AT > 0 and elapsed < _ISSUE_GAP_SECS:
                wait_secs = _ISSUE_GAP_SECS - elapsed
                logger.info(
                    "[token] 분당 한도 대기: label=%s wait=%.1fs",
                    self._label or "main", wait_secs,
                )
                await asyncio.sleep(wait_secs)

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
            _LAST_ISSUE_AT = time.monotonic()
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
        # 사이클 20 — 디렉토리 단위. 부모 디렉토리 자동 생성.
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.exception("토큰 캐시 디렉토리 생성 실패: %s", self._cache_path.parent)
        self._cache_path.write_text(json.dumps(data), encoding="utf-8")

    def _load_cache(self) -> None:
        """캐시 파일에서 토큰 로드 — 사이클 20 신경로 우선 + 구경로 마이그레이션.

        1) 새 경로 (`/app/.token_cache/main.json` 또는 `.../quote_<label>.json`) 존재 → 로드
        2) 미존재 + 구 경로 (`.token_cache.json` 또는 `.token_cache_quote_<label>.json`)
           존재 → 구 경로에서 로드 + 새 경로로 즉시 마이그레이션 + 구 경로 unlink
        """
        legacy_path = self._resolve_legacy_path()
        source_path: Optional[Path] = None

        if self._cache_path.exists():
            source_path = self._cache_path
        elif legacy_path is not None and legacy_path.exists():
            source_path = legacy_path

        if source_path is None:
            return

        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
            self.access_token = data.get("access_token", "")
            expired_str = data.get("token_expired")
            if expired_str:
                self.token_expired = datetime.fromisoformat(expired_str)
            if self._is_valid():
                logger.info(
                    "캐시 토큰 로드 완료(label=%s), 만료: %s",
                    self._label or "main", self.token_expired,
                )
                # 마이그레이션: 구 경로에서 읽었으면 새 경로로 이동
                if source_path != self._cache_path:
                    self._save_cache()
                    try:
                        source_path.unlink()
                        logger.info(
                            "[token] 캐시 마이그레이션: %s → %s",
                            source_path, self._cache_path,
                        )
                    except OSError:
                        logger.exception("구 캐시 파일 삭제 실패: %s", source_path)
            else:
                self.access_token = ""
                self.token_expired = None
        except (json.JSONDecodeError, KeyError):
            self.access_token = ""
            self.token_expired = None

    def _resolve_legacy_path(self) -> Optional[Path]:
        """현재 매니저의 구 경로(`.token_cache.json` 또는 `.token_cache_quote_<label>.json`)."""
        # 메인 매니저는 기본 경로 사용 시에만 구 경로 후보 결정
        if self._cache_path == _TOKEN_CACHE_PATH:
            return _LEGACY_MAIN_CACHE_PATH
        # 보조 매니저: 새 경로가 `.token_cache/quote_<label>.json` 패턴이면 구 경로 추정
        try:
            name = self._cache_path.name
            if name.startswith(_QUOTE_TOKEN_CACHE_PREFIX):
                label_part = name[len(_QUOTE_TOKEN_CACHE_PREFIX):].removesuffix(".json")
                return Path(f"{_LEGACY_QUOTE_CACHE_PREFIX}{label_part}.json")
        except Exception:
            pass
        return None

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
    """label → 안전한 파일명 변환 (경로 문자/공백 차단).

    사이클 20 — `.token_cache/quote_<safe>.json` 디렉토리 단위 경로 반환.
    """
    safe = "".join(ch if (ch.isalnum() or ch in ("-", "_")) else "_" for ch in label)
    return _TOKEN_CACHE_DIR / f"{_QUOTE_TOKEN_CACHE_PREFIX}{safe}.json"


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
