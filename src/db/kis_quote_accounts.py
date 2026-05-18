"""kis_quote_accounts CRUD — 보조 KIS 시세 수신 계좌 풀.

사이클 7-A (2026-05-17).

자금 안전 원칙:
- 본 모듈은 시세 수신 전용 계좌 관리. 매매/잔고/체결통보 함수에서 호출 금지.
- 응답에 `app_secret` 평문 노출 금지 — 호출자는 KisQuoteAccount.from_row() 마스킹 변환 사용.
- 단, 토큰 매니저(`src/auth/token.py`)는 평문 app_secret 이 필요 — 별도 함수 `get_credentials_for_token_manager` 노출.

supabase 동기 SDK 호출은 모두 `asyncio.to_thread()` 위임 — 이벤트 루프 블로킹 차단.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from src.db.supabase import supabase
from src.models.kis_quote_account import KisQuoteAccount, mask_secret

logger = logging.getLogger(__name__)

TABLE_NAME = "kis_quote_accounts"

# 사이클 14-D (2026-05-18) — list_accounts 60s TTL 메모리 캐시.
# Settings/Dashboard 폴링(30s) + boot pool_start 호출 race + supabase HTTP/2
# stale connection 결함으로 list 실패 28회/시간 누적되던 결함 차단.
# active_only=True/False 키 분리. INSERT/UPDATE/DELETE 직후 invalidate.
_LIST_CACHE_TTL = 60.0
_list_cache: dict[bool, list[KisQuoteAccount]] = {}
_list_cache_expires_at: dict[bool, float] = {}


def invalidate_list_cache() -> None:
    """INSERT/UPDATE/DELETE 직후 호출 — 다음 list_accounts 가 fresh fetch."""
    _list_cache.clear()
    _list_cache_expires_at.clear()


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------
async def list_accounts(active_only: bool = False) -> list[KisQuoteAccount]:
    """전체 또는 활성 계좌 목록 조회 (created_at ASC). 60s TTL 캐시.

    active_only=True 면 active=true 만 반환.
    """
    now = time.monotonic()
    expires_at = _list_cache_expires_at.get(active_only)
    if expires_at is not None and now < expires_at:
        return _list_cache[active_only]

    def _query():
        q = supabase.table(TABLE_NAME).select("*")
        if active_only:
            q = q.eq("active", True)
        return q.order("created_at").execute()

    try:
        result = await asyncio.to_thread(_query)
        rows = result.data or []
        accounts = [KisQuoteAccount.from_row(r) for r in rows]
        _list_cache[active_only] = accounts
        _list_cache_expires_at[active_only] = now + _LIST_CACHE_TTL
        return accounts
    except Exception:
        logger.exception("[kis_quote_accounts] list 실패")
        # 사이클 14-D: stale 캐시가 있으면 반환 (graceful). 없으면 빈 리스트.
        if active_only in _list_cache:
            return _list_cache[active_only]
        return []


async def get_account(account_id: UUID | str) -> Optional[KisQuoteAccount]:
    """ID 로 단건 조회. 미존재 → None."""
    aid = str(account_id)

    def _query():
        return supabase.table(TABLE_NAME).select("*").eq("id", aid).execute()

    try:
        result = await asyncio.to_thread(_query)
        rows = result.data or []
        if not rows:
            return None
        return KisQuoteAccount.from_row(rows[0])
    except Exception:
        logger.exception("[kis_quote_accounts] get(%s) 실패", aid)
        return None


async def get_account_by_label(label: str) -> Optional[KisQuoteAccount]:
    """label 로 단건 조회. 미존재 → None."""

    def _query():
        return supabase.table(TABLE_NAME).select("*").eq("label", label).execute()

    try:
        result = await asyncio.to_thread(_query)
        rows = result.data or []
        if not rows:
            return None
        return KisQuoteAccount.from_row(rows[0])
    except Exception:
        logger.exception("[kis_quote_accounts] get_by_label(%s) 실패", label)
        return None


async def get_credentials_for_token_manager(label: str) -> Optional[dict[str, str]]:
    """**토큰 매니저 전용** — app_secret 평문 반환.

    `src/auth/token.py::get_token_manager(label)` 의 lazy 초기화에서만 호출.
    응답: ``{"app_key": ..., "app_secret": ..., "kis_env": "real"|"vts"}`` 또는 None.

    **API 응답/로그에 절대 노출 금지** — 본 함수는 내부 호출 전용이며 호출 경로
    추적성 확보를 위해 별도 함수로 분리.
    """

    def _query():
        return (
            supabase.table(TABLE_NAME)
            .select("*")
            .eq("label", label)
            .eq("active", True)
            .execute()
        )

    try:
        result = await asyncio.to_thread(_query)
        rows = result.data or []
        if not rows:
            return None
        row = rows[0]
        return {
            "app_key": row["app_key"],
            "app_secret": row["app_secret"],
            "kis_env": row["kis_env"],
        }
    except Exception:
        logger.exception("[kis_quote_accounts] get_credentials(%s) 실패", label)
        return None


# ---------------------------------------------------------------------------
# 변경 — Insert / Update / Delete
# ---------------------------------------------------------------------------
class LabelConflictError(Exception):
    """label UNIQUE 충돌."""


async def insert_account(
    label: str,
    app_key: str,
    app_secret: str,
    kis_env: str,
) -> KisQuoteAccount:
    """신규 계좌 INSERT.

    label UNIQUE 충돌 시 `LabelConflictError` raise.
    빈 문자열 / kis_env CHECK 위반은 ValueError raise (DB 제약 의존).
    """
    label = (label or "").strip()
    app_key = (app_key or "").strip()
    app_secret = (app_secret or "").strip()
    if not label or not app_key or not app_secret:
        raise ValueError("label / app_key / app_secret 모두 비어있을 수 없습니다.")
    if kis_env not in ("real", "vts"):
        raise ValueError(f"kis_env 는 'real' 또는 'vts' 만 허용: {kis_env!r}")

    # 사전 label 충돌 검사 (race 여지 있으나 사용자 메시지 가독성 우선)
    existing = await get_account_by_label(label)
    if existing is not None:
        raise LabelConflictError(f"이미 등록된 label: {label}")

    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "label": label,
        "app_key": app_key,
        "app_secret": app_secret,
        "kis_env": kis_env,
        "active": True,
        # 운영 DB 는 DEFAULT NOW() 로 자동 채워지지만 응답 직후 RETURNING 일관성
        # + 인메모리 fake 호환을 위해 명시 세팅.
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    def _insert():
        return supabase.table(TABLE_NAME).insert(payload).execute()

    try:
        result = await asyncio.to_thread(_insert)
    except Exception as e:
        # Supabase race 충돌(UNIQUE) 메시지 검출
        msg = str(e)
        if "duplicate" in msg.lower() or "unique" in msg.lower():
            raise LabelConflictError(f"이미 등록된 label: {label}") from e
        raise

    rows = result.data or []
    invalidate_list_cache()  # 사이클 14-D: 다음 list_accounts 즉시 fresh
    if not rows:
        # supabase-py INSERT 가 빈 응답을 주는 경우 fallback 재조회
        fetched = await get_account_by_label(label)
        if fetched is None:
            raise RuntimeError("INSERT 후 row 조회 실패")
        return fetched
    return KisQuoteAccount.from_row(rows[0])


async def update_account(
    account_id: UUID | str,
    *,
    active: Optional[bool] = None,
    label: Optional[str] = None,
) -> Optional[KisQuoteAccount]:
    """active / label 부분 갱신.

    둘 다 None 이면 변경 없이 현재 row 반환.
    label 충돌 시 `LabelConflictError`.
    미존재 ID → None.
    """
    aid = str(account_id)
    current = await get_account(aid)
    if current is None:
        return None

    patch: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if active is not None:
        patch["active"] = bool(active)
    if label is not None:
        new_label = label.strip()
        if not new_label:
            raise ValueError("label 이 비어있습니다.")
        if new_label != current.label:
            # 다른 계좌와 충돌 검사
            conflict = await get_account_by_label(new_label)
            if conflict is not None and str(conflict.id) != aid:
                raise LabelConflictError(f"이미 등록된 label: {new_label}")
            patch["label"] = new_label

    if len(patch) == 1:  # updated_at 만 있는 경우 (변경 없음)
        return current

    def _update():
        return supabase.table(TABLE_NAME).update(patch).eq("id", aid).execute()

    try:
        await asyncio.to_thread(_update)
    except Exception as e:
        msg = str(e)
        if "duplicate" in msg.lower() or "unique" in msg.lower():
            raise LabelConflictError(f"이미 등록된 label: {label}") from e
        raise

    invalidate_list_cache()  # 사이클 14-D: 다음 list_accounts 즉시 fresh
    # 갱신 직후 재조회 (응답 최신화)
    refreshed = await get_account(aid)
    return refreshed


async def delete_account(account_id: UUID | str) -> bool:
    """계좌 삭제. 존재했으면 True, 미존재 False."""
    aid = str(account_id)
    current = await get_account(aid)
    if current is None:
        return False

    def _delete():
        return supabase.table(TABLE_NAME).delete().eq("id", aid).execute()

    try:
        await asyncio.to_thread(_delete)
        invalidate_list_cache()  # 사이클 14-D: 다음 list_accounts 즉시 fresh
        return True
    except Exception:
        logger.exception("[kis_quote_accounts] delete(%s) 실패", aid)
        return False
