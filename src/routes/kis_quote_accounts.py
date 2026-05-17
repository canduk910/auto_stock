"""사이클 7-A (2026-05-17): 보조 KIS 시세 수신 계좌 관리 라우트.

`/api/integrations/quote-accounts/*`

자금 안전 원칙:
- 본 라우트는 시세 수신 계좌 등록/조회/관리만. 매매/잔고/체결통보는 메인 단일.
- app_secret 평문은 응답에 절대 노출 안 함 — `KisQuoteAccount.from_row()` 가 마스킹.
- 본 사이클은 인프라만 — 실제 시세 활용은 7-B (WebSocketPool) / 7-C (REST 라운드로빈).
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from src.db import kis_quote_accounts as kqa
from src.models.kis_quote_account import (
    KisQuoteAccountCreate,
    KisQuoteAccountUpdate,
)
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/integrations/quote-accounts",
    tags=["integrations", "quote-accounts"],
)


# ---------------------------------------------------------------------------
# GET 목록
# ---------------------------------------------------------------------------
@router.get("", response_model=ApiResponse)
async def list_quote_accounts(active_only: bool = False):
    """보조 시세 계좌 목록 조회.

    응답: ``{success, data: {accounts: [{id, label, app_key, app_secret_masked,
    kis_env, active, created_at, updated_at}]}}``. app_secret 평문 절대 노출 안 함.
    """
    accounts = await kqa.list_accounts(active_only=active_only)
    return ApiResponse(
        success=True,
        data={"accounts": [a.model_dump(mode="json") for a in accounts]},
    )


# ---------------------------------------------------------------------------
# POST 신규 등록
# ---------------------------------------------------------------------------
@router.post("", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_quote_account(req: KisQuoteAccountCreate):
    """신규 보조 시세 계좌 등록.

    응답 코드:
    - 201: 정상 등록 (app_secret 마스킹된 응답)
    - 409: label UNIQUE 충돌
    - 422: 빈 값 / kis_env 부적합 (Pydantic 검증 또는 ValueError)
    - 500: DB 장애
    """
    try:
        account = await kqa.insert_account(
            label=req.label,
            app_key=req.app_key,
            app_secret=req.app_secret,
            kis_env=req.kis_env,
        )
    except kqa.LabelConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("[quote-accounts] 등록 실패")
        raise HTTPException(status_code=500, detail=str(e))

    return ApiResponse(
        success=True,
        data=account.model_dump(mode="json"),
        message=f"보조 시세 계좌 등록 완료 (label={account.label}). 시세 활용은 7-B/7-C 사이클 적용 후 시작됩니다.",
    )


# ---------------------------------------------------------------------------
# PUT 부분 갱신 (active / label)
# ---------------------------------------------------------------------------
@router.put("/{account_id}", response_model=ApiResponse)
async def update_quote_account(account_id: UUID, req: KisQuoteAccountUpdate):
    """active / label 부분 갱신.

    응답 코드:
    - 200: 정상 갱신
    - 404: 미존재 ID
    - 409: label UNIQUE 충돌
    - 422: 빈 값
    """
    try:
        account = await kqa.update_account(
            account_id,
            active=req.active,
            label=req.label,
        )
    except kqa.LabelConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("[quote-accounts] 갱신 실패")
        raise HTTPException(status_code=500, detail=str(e))

    if account is None:
        raise HTTPException(status_code=404, detail=f"계좌 미존재: {account_id}")

    return ApiResponse(
        success=True,
        data=account.model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------
@router.delete("/{account_id}", response_model=ApiResponse)
async def delete_quote_account(account_id: UUID):
    """계좌 삭제.

    응답 코드:
    - 200: 정상 삭제
    - 404: 미존재 ID
    """
    deleted = await kqa.delete_account(account_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"계좌 미존재: {account_id}")
    return ApiResponse(
        success=True,
        data={"deleted": True, "id": str(account_id)},
        message="보조 시세 계좌가 삭제되었습니다.",
    )
