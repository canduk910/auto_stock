"""사이클 34 (2026-05-21) — 조건검색 단계별 후보 추적 API + 사이클 132 휴장일 UI 안내.

배경:
- 사용자 5/21 15:26 funnel 결함 진단 시 단계별 살아남은/탈락 종목을 알 수 없어 디버깅 곤란.
- 사이클 33 결함 시정 (BFB acml_vol / VCP fetch_days 100 한도) 후에도 운영 중 단계별 추이를
  영구 추적해야 회귀 검증 + 매매 결정 추적 가능.

사이클 132 (2026-06-15) — 휴장일 UI 안내 영역 추가 (사용자 결정 Q3=A 영속):
- GET 응답 data 영역에 `is_business_day: bool` + `holiday_note: str | None` 영역 추가.
- KIS `chk-holiday` API (CTCA0903R) `is_market_open(date)` 영구 영속 재사용 (사이클 17 영속).
- 휴장일 (주말/공휴일) 운영자 UI 접속 시 "데이터 미수신" 영구 영속 오인 차단.
- 호출 실패 시 graceful 영업일 가정 영속 (사이클 88 G-REJECT 영속).

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

from src.api.condition import is_market_open  # 사이클 132 — KIS chk-holiday 재사용 (사이클 17 영속)
from src.db.strategy_funnel import (
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


async def _resolve_business_day(target: date) -> tuple[bool, str | None]:
    """사이클 132 — 영업일 판정 + holiday_note 한글 안내 (graceful).

    Returns:
        (is_business_day, holiday_note):
        - 영업일: (True, None)
        - 휴장일: (False, "오늘은 휴장일 — 영업일 데이터 미수신")
        - 조회 실패 (graceful, 사이클 88 G-REJECT): (True, None) — 영업일 가정

    영속 의무:
    - 사이클 17 KIS chk-holiday 재사용 (신규 KIS 호출 0건)
    - 사이클 88 G-REJECT graceful (예외 → 영업일 가정 + holiday_note=None)
    - 사이클 89 한글 친숙 용어 (휴장일 안내 메시지)
    """
    try:
        is_open = await is_market_open(target)
    except Exception as exc:
        logger.warning(
            "[funnel_holiday_check_skip] target=%s reason=%s — graceful 영업일 가정",
            target.isoformat(),
            exc,
        )
        return True, None

    if is_open:
        return True, None
    # 휴장일 한글 안내 (사이클 89 한글 친숙 용어 영속)
    return False, "오늘은 휴장일 — 영업일 데이터 미수신"


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
    # 사이클 132 — 휴장일 UI 안내 영역 영구 영속 (Q3=A)
    is_business_day, holiday_note = await _resolve_business_day(target)

    return ApiResponse(
        success=True,
        data={
            "target_date": target.isoformat(),
            "strategy_id": strategy_id,
            "snapshots": snapshots,
            # 사이클 132 신규 영구 영속 (운영자 휴장일 오인 차단)
            "is_business_day": is_business_day,
            "holiday_note": holiday_note,
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

    사이클 171 (2026-06-22) — 단계별 전체 캡처로 전환 (자문 의제 6 (a)).
    종전 step_no=99 (최종) 단독 → `capture_funnel_snapshots(registry, is_provisional=False)`
    공통 헬퍼 위임 (09:30 자동 hook 과 동일 단계별 + step_no=99 캡처). 운영자가 "지금 각
    단계 후보를 보고 싶다" 니즈 충족. is_provisional=False (확정 — 잠정은 16:20 저녁 task).

    실제 prepare() 재실행은 하지 않음 — 최근 prepare 결과(`_funnel_steps`)만 캡처.
    """
    from src.engine.scheduler import trading_scheduler, capture_funnel_snapshots

    today = datetime.now(_KST_TZ).date()

    try:
        registry = trading_scheduler.registry
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"strategy registry 접근 실패: {exc}")

    # 사이클 171 — 09:30 자동 hook 과 동일 헬퍼 (단계별 + step_no=99, is_provisional=False)
    saved_count = await capture_funnel_snapshots(registry, is_provisional=False)

    return ApiResponse(
        success=True,
        data={"target_date": today.isoformat(), "saved_count": saved_count, "count": saved_count},
        message=f"{saved_count}개 snapshot 저장",
    )
