"""parameter_recommendations CRUD — OpenAI 기반 파라미터 추천 영속화."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone, timedelta

from src.db.supabase import supabase

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


async def insert_recommendation(
    target_date: date,
    strategy_id: str,
    current_params: dict,
    recommended_params: dict,
    reasoning: str,
    metrics: dict,
    recommended_weight: float | None = None,
    code_review_notes: str | None = None,
    weight_reasoning: str | None = None,
) -> dict | None:
    """파라미터 추천을 INSERT한다.

    Phase J4 (2026-05-12) — 신규 컬럼 3종 지원:
      - recommended_weight: AI 추천 전략 weight (0.0~1.0), null = 변경 권고 없음
      - code_review_notes: 로직/파라미터 자유 텍스트 자문, null = 변경 권고 없음
      - applied_weight: INSERT 시점은 항상 None (apply 시점에 채워짐)

    사이클 1 (2026-05-17) — weight_reasoning 추가:
      - weight_reasoning: 비중 변경 권고 사유 (별도 필드, 최대 1000자).
        recommended_weight 가 null 이면 weight_reasoning 도 null.
        J4 의 통합 `reasoning` 에 묻혀 있던 비중 사유를 UI 자산 배정 카드에서
        amber 배경 영역으로 분리 강조하기 위함.

    동일 (target_date, strategy_id) 조합이 unique index에 의해 거부되면 None 반환.
    """
    data = {
        "target_date": target_date.isoformat(),
        "strategy_id": strategy_id,
        "current_params": current_params,
        "recommended_params": recommended_params,
        "reasoning": reasoning,
        "metrics": metrics,
        "status": "pending",
        "recommended_weight": recommended_weight,
        "code_review_notes": code_review_notes,
        "weight_reasoning": weight_reasoning,
        "applied_weight": None,
    }
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table("parameter_recommendations").insert(data).execute()
        )
        if result.data:
            logger.info(
                "파라미터 추천 INSERT: %s (%s, 추천 %d개)",
                strategy_id, target_date, len(recommended_params),
            )
            return result.data[0]
        return None
    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg or "23505" in msg:
            logger.warning(
                "파라미터 추천 중복 — 이미 존재함: %s (%s)", strategy_id, target_date,
            )
            return None
        logger.exception("파라미터 추천 INSERT 실패: %s", strategy_id)
        return None


async def list_recommendations(days: int = 30) -> list[dict]:
    """최근 N일의 추천 목록을 created_at 내림차순으로 반환."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = await asyncio.to_thread(
        lambda: supabase.table("parameter_recommendations")
        .select("*")
        .gte("target_date", cutoff)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


async def get_recommendation(rec_id: str) -> dict | None:
    """단일 추천 레코드를 조회한다."""
    result = await asyncio.to_thread(
        lambda: supabase.table("parameter_recommendations")
        .select("*")
        .eq("id", rec_id)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]
    return None


async def update_recommendation_status(
    rec_id: str,
    status: str,
    applied_params: dict | None = None,
    applied_weight: float | None = None,
) -> dict:
    """추천 레코드의 status를 갱신한다.

    Phase J4 (2026-05-12): `applied_weight` 키워드로 실제 적용된 weight 트래킹.

    applied/partial 셋 시 applied_at, rejected 셋 시 rejected_at 자동 기록.
    """
    update_data: dict = {"status": status}
    now_iso = datetime.now(KST).isoformat()
    if status in ("applied", "partial"):
        update_data["applied_at"] = now_iso
        if applied_params is not None:
            update_data["applied_params"] = applied_params
        if applied_weight is not None:
            update_data["applied_weight"] = applied_weight
    elif status == "rejected":
        update_data["rejected_at"] = now_iso

    result = await asyncio.to_thread(
        lambda: supabase.table("parameter_recommendations")
        .update(update_data)
        .eq("id", rec_id)
        .execute()
    )
    logger.info("파라미터 추천 상태 갱신: %s -> %s", rec_id, status)
    return result.data[0] if result.data else {}


async def update_backtest_summary(
    rec_id: str,
    summary: dict,
) -> dict:
    """Phase 3 (2026-05-16) — `backtest_summary` JSONB 컬럼 단일 row 갱신.

    `summary` 구조:
        {
          "current":     { "<strategy_id>": { 8 metrics } | None, ... },
          "recommended": { "<strategy_id>": { 8 metrics } | None, ... },
          "diff":        { "<strategy_id>": { "<key>": <delta>, ... }, ... }
        }

    적용 row 0건 (미존재 ID) 이면 빈 dict 반환 — 예외 전파 안 함.
    """
    update_data = {"backtest_summary": dict(summary or {})}
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table("parameter_recommendations")
            .update(update_data)
            .eq("id", rec_id)
            .execute()
        )
    except Exception:
        logger.exception("backtest_summary 갱신 실패: %s", rec_id)
        return {}
    if not result.data:
        logger.warning("backtest_summary 갱신 대상 미존재: rec_id=%s", rec_id)
        return {}
    logger.info("backtest_summary 갱신: rec_id=%s", rec_id)
    return result.data[0]


async def list_recommendations_pending_backtest(target_date: date) -> list[dict]:
    """Phase 3 폴 루프 진입 가드 — `target_date` 의 `backtest_summary IS NULL` row 만 반환.

    `idx_param_recommendations_backtest_pending` 부분 인덱스(마이그 020) 가
    매칭되어 EXPLAIN 상 인덱스 스캔이 일어난다.
    """
    result = await asyncio.to_thread(
        lambda: supabase.table("parameter_recommendations")
        .select("*")
        .eq("target_date", target_date.isoformat())
        .is_("backtest_summary", "null")
        .execute()
    )
    return result.data or []


async def expire_pending_before(target_date: date) -> int:
    """target_date 이전의 pending 레코드를 expired로 일괄 마킹한다.

    Returns:
        만료 처리된 레코드 수.
    """
    result = await asyncio.to_thread(
        lambda: supabase.table("parameter_recommendations")
        .update({"status": "expired"})
        .eq("status", "pending")
        .lt("target_date", target_date.isoformat())
        .execute()
    )
    expired_count = len(result.data or [])
    if expired_count > 0:
        logger.info("이전 pending 추천 %d건 expired로 마킹", expired_count)
    return expired_count
