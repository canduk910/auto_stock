"""사이클 34 (2026-05-21) — 조건검색 단계별 후보 추적 API.

배경:
- 사용자 5/21 15:26 funnel 결함 진단 시 단계별 살아남은/탈락 종목을 알 수 없어 디버깅 곤란.
- 사이클 33 결함 시정 (BFB acml_vol / VCP fetch_days 100 한도) 후에도 운영 중 단계별 추이를
  영구 추적해야 회귀 검증 + 매매 결정 추적 가능.

엔드포인트:
- GET /api/strategy-funnel?strategy_id=...&target_date=YYYY-MM-DD — 단일 영업일 단계별 후보
- GET /api/strategy-funnel/recent?strategy_id=...&days=7 — 최근 N일 추이
- POST /api/strategy-funnel/snapshot — 수동 trigger (모든 전략 prepare 결과 1회 캡처)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.db.strategy_funnel import (
    insert_snapshot,
    list_recent_by_strategy,
    list_snapshots,
)
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strategy-funnel", tags=["strategy-funnel"])

_KST_TZ = timezone(timedelta(hours=9))


def _parse_date(date_str: str | None) -> date:
    """YYYY-MM-DD → date. None 이면 오늘 (KST)."""
    if not date_str:
        return datetime.now(_KST_TZ).date()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"target_date 형식 YYYY-MM-DD: {exc}")


@router.get("", response_model=ApiResponse)
async def get_funnel(
    target_date: Optional[str] = Query(None, description="YYYY-MM-DD (기본: 오늘 KST)"),
    strategy_id: Optional[str] = Query(None, description="전략 ID (None: 전체)"),
) -> ApiResponse:
    """단일 영업일 단계별 후보 종목 조회.

    응답 data:
        {
          "target_date": "2026-05-21",
          "strategy_id": "donchian_swing" | null,
          "snapshots": [
            {
              "id": "...",
              "step_no": 1, "step_name": "...",
              "survived_count": ..., "excluded_count": ...,
              "survived_tickers": [...], "excluded_sample": [...]
            }, ...
          ]
        }
    """
    target = _parse_date(target_date)
    snapshots = await list_snapshots(target_date=target, strategy_id=strategy_id)

    return ApiResponse(
        success=True,
        data={
            "target_date": target.isoformat(),
            "strategy_id": strategy_id,
            "snapshots": snapshots,
        },
        message="",
    )


@router.get("/recent", response_model=ApiResponse)
async def get_recent_funnel(
    strategy_id: str = Query(..., description="전략 ID (필수)"),
    days: int = Query(7, ge=1, le=30, description="최근 N일 (1~30)"),
) -> ApiResponse:
    """특정 전략의 최근 N일 단계별 추이 (시계열 분석용)."""
    snapshots = await list_recent_by_strategy(strategy_id=strategy_id, days=days)
    return ApiResponse(
        success=True,
        data={"strategy_id": strategy_id, "days": days, "snapshots": snapshots},
        message="",
    )


@router.post("/snapshot", response_model=ApiResponse)
async def trigger_snapshot() -> ApiResponse:
    """모든 활성 전략의 prepare 단계 결과를 즉시 snapshot 으로 기록.

    각 전략의 `get_scan_stats()` 응답을 기반으로 단계별 row INSERT.
    실제 prepare() 재실행은 하지 않음 — 최근 prepare 결과만 캡처.
    """
    from src.engine.scheduler import trading_scheduler

    today = datetime.now(_KST_TZ).date()
    saved: list[dict] = []

    try:
        strategies = trading_scheduler.registry.all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"strategy registry 접근 실패: {exc}")

    for strategy in strategies:
        sid = getattr(strategy, "strategy_id", "")
        # get_scan_stats 가 있는 전략만 (donchian/BFB/VCP/momentum/VB/LTV 모두 보유)
        get_scan_stats = getattr(strategy, "get_scan_stats", None)
        get_scanned = getattr(strategy, "get_scanned_tickers", None)
        if not callable(get_scan_stats):
            continue
        try:
            stats = get_scan_stats() or {}
        except Exception:
            logger.exception("get_scan_stats 실패: %s", sid)
            continue
        scanned = []
        if callable(get_scanned):
            try:
                scanned = list(get_scanned())
            except Exception:
                scanned = []

        # 마지막 단계 = 최종 prepared (현재 운영 카운트)
        survived_count = len(scanned)
        row = await insert_snapshot(
            target_date=today,
            strategy_id=sid,
            step_no=99,  # 99 = 최종 단계 (수동 trigger 식별자)
            step_name="최종 prepared (수동 trigger)",
            survived_tickers=scanned,
            survived_count=survived_count,
            excluded_count=0,
            excluded_sample=[],
        )
        if row:
            saved.append({"strategy_id": sid, "id": row.get("id")})

    return ApiResponse(
        success=True,
        data={"target_date": today.isoformat(), "saved": saved, "count": len(saved)},
        message=f"{len(saved)}개 전략 snapshot 저장",
    )
