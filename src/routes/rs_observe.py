"""RS·재무 관찰 화면 — `GET /api/rs-observe` (읽기 전용, 매매 경로 무접촉).

`candidate_score_snapshots`(migration 052, 부팅 때 `rs_fundamental_observe` 가 쓴다)를 날짜·전략별로 읽어 보인다.
- `date` 없음 = 기록이 있는 가장 최근 날짜. 기록이 하나도 없으면 `target_date=None` · 행 0.
- `strategy` 없음 = 4전략 전부. 모르는 전략 이름 = 422.
- 점수 칸 NULL(「모름」)은 null 그대로 보낸다 — 0 으로 채우지 않는다.
- DB 조회 실패 = HTTP 200 + `success=false`(화면이 사유를 보인다) + `[rs_observe_read_error]` WARNING.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

import src.db.candidate_scores as cs_db
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rs-observe", tags=["rs-observe"])

# 관찰 대상 = `rs_fundamental_observe.TARGET_STRATEGIES` 와 같은 넷(엔진 모듈을 import 하지 않으려 여기 둔다 —
# 같은 값인지는 테스트가 대조한다).
STRATEGIES = ("donchian_swing", "vcp_breakout", "kojiro", "etf_trend")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _clean(row: dict) -> dict:
    """NaN·inf 는 JSON 이 못 싣는다 — 「모름」(null)으로."""
    return {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in row.items()}


@router.get("")
async def get_rs_observe(
    date: Optional[str] = Query(None, description="YYYY-MM-DD (없으면 가장 최근 기록일)"),
    strategy: Optional[str] = Query(None, description="donchian_swing|vcp_breakout|kojiro|etf_trend (없으면 전부)"),
):
    if date is not None and not _DATE_RE.match(date):
        raise HTTPException(status_code=422, detail="date 형식은 YYYY-MM-DD")
    if strategy is not None and strategy not in STRATEGIES:
        raise HTTPException(status_code=422, detail=f"strategy 는 {', '.join(STRATEGIES)} 중 하나")
    try:
        dates = await cs_db.list_dates(60)
        target = date or (dates[0] if dates else None)
        rows = [_clean(r) for r in await cs_db.list_snapshot(target, strategy)] if target else []
    except Exception as exc:  # 관찰 화면 — 조회 실패를 사유와 함께 돌려준다
        logger.warning("[rs_observe_read_error] date=%s strategy=%s err=%r", date, strategy, exc)
        return ApiResponse(success=False, data=None, message=f"RS·재무 관찰 기록 조회 실패: {type(exc).__name__}")
    return ApiResponse(
        success=True,
        data={"target_date": target, "dates": dates, "strategies": list(STRATEGIES), "rows": rows},
        message="",
    )
