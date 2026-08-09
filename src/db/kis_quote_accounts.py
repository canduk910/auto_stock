"""kis_quote_accounts CRUD — 보조 KIS 시세 수신 계좌 풀.

사이클 7-A (2026-05-17).

자금 안전 원칙:
- 본 모듈은 시세 수신 전용 계좌 관리. 매매/잔고/체결통보 함수에서 호출 금지.
- 응답에 `app_secret` 평문 노출 금지 — 호출자는 KisQuoteAccount.from_row() 마스킹 변환 사용.
- 단, 토큰 매니저(`src/auth/token.py`)는 평문 app_secret 이 필요 — 별도 함수 `get_credentials_for_token_manager` 노출.

사이클 M3a (Supabase→RDS 이전 단계3, 분석·관찰 비 hot-path): supabase-py → `src.db.pg`
(asyncpg) 전환. 함수 시그니처·반환형·graceful·캐시 100% 보존 — 호출부 diff 0.

- read 4함수(list_accounts/get_account/get_account_by_label/get_credentials_for_token_manager)
  = `pg._with_retry` 경유(사이클 189 정책 = read 만 retry).
- 쓰기(insert/update/delete) = `pg.execute`/`pg.fetchrow` 직접(retry 미경유, 멱등 우려).
- `list_accounts` 60s TTL 메모리 캐시 로직 절대 보존(hit/만료/DB예외 stale 반환/invalidate).
"""
from __future__ import annotations

import asyncio  # noqa: F401 — Red autouse fixture 호환(monkeypatch.setattr(kqa.asyncio, ...))
import logging
import time
from datetime import datetime
from typing import Optional
from uuid import UUID

import src.db.pg as pg
from src.db._kst import now_kst_iso
from src.models.kis_quote_account import KisQuoteAccount

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

    read 는 `pg.fetch` 경유 — `pg.fetch` 자체가 내부에서 `pg._with_retry` 를
    태우므로(사이클 189 read retry 정책 계승) 본 함수가 별도로 `_with_retry` 를
    다시 호출하지 않는다(이중 retry 방지).
    """
    now = time.monotonic()
    expires_at = _list_cache_expires_at.get(active_only)
    if expires_at is not None and now < expires_at:
        return _list_cache[active_only]

    try:
        if active_only:
            rows = await pg.fetch(
                f"SELECT * FROM {TABLE_NAME} WHERE active = $1 ORDER BY created_at",
                True,
            )
        else:
            rows = await pg.fetch(f"SELECT * FROM {TABLE_NAME} ORDER BY created_at")
        rows = rows or []
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

    try:
        row = await pg.fetchrow(f"SELECT * FROM {TABLE_NAME} WHERE id = $1", aid)
        if row is None:
            return None
        return KisQuoteAccount.from_row(row)
    except Exception:
        logger.exception("[kis_quote_accounts] get(%s) 실패", aid)
        return None


async def get_account_by_label(label: str) -> Optional[KisQuoteAccount]:
    """label 로 단건 조회. 미존재 → None."""

    try:
        row = await pg.fetchrow(f"SELECT * FROM {TABLE_NAME} WHERE label = $1", label)
        if row is None:
            return None
        return KisQuoteAccount.from_row(row)
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

    try:
        rows = await pg.fetch(
            f"SELECT * FROM {TABLE_NAME} WHERE label = $1 AND active = $2",
            label, True,
        )
        rows = rows or []
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

    now_dt = datetime.fromisoformat(now_kst_iso())

    try:
        await pg.execute(
            f"""
            INSERT INTO {TABLE_NAME} (
                label, app_key, app_secret, kis_env, active, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            label, app_key, app_secret, kis_env, True, now_dt, now_dt,
        )
    except Exception as e:
        # Postgres race 충돌(UNIQUE) 메시지 검출
        msg = str(e)
        if "duplicate" in msg.lower() or "unique" in msg.lower():
            raise LabelConflictError(f"이미 등록된 label: {label}") from e
        raise

    invalidate_list_cache()  # 사이클 14-D: 다음 list_accounts 즉시 fresh
    # INSERT 는 RETURNING 없이 실행 → 재조회로 최신 row 획득 (fallback 겸용)
    fetched = await get_account_by_label(label)
    if fetched is None:
        raise RuntimeError("INSERT 후 row 조회 실패")
    return fetched


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

    set_clauses = ["updated_at = $2"]
    args: list = [aid, datetime.fromisoformat(now_kst_iso())]
    idx = 3
    if active is not None:
        set_clauses.append(f"active = ${idx}")
        args.append(bool(active))
        idx += 1
    if label is not None:
        new_label = label.strip()
        if not new_label:
            raise ValueError("label 이 비어있습니다.")
        if new_label != current.label:
            # 다른 계좌와 충돌 검사
            conflict = await get_account_by_label(new_label)
            if conflict is not None and str(conflict.id) != aid:
                raise LabelConflictError(f"이미 등록된 label: {new_label}")
            set_clauses.append(f"label = ${idx}")
            args.append(new_label)
            idx += 1

    if len(set_clauses) == 1:  # updated_at 만 있는 경우 (변경 없음)
        return current

    sql = f"UPDATE {TABLE_NAME} SET {', '.join(set_clauses)} WHERE id = $1"

    try:
        await pg.execute(sql, *args)
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

    try:
        await pg.execute(f"DELETE FROM {TABLE_NAME} WHERE id = $1", aid)
        invalidate_list_cache()  # 사이클 14-D: 다음 list_accounts 즉시 fresh
        return True
    except Exception:
        logger.exception("[kis_quote_accounts] delete(%s) 실패", aid)
        return False
