"""strategy_config CRUD — 전략 설정(비중/파라미터) 영속화."""

import json
import logging

from src.db.supabase import supabase

logger = logging.getLogger(__name__)


async def load_all() -> dict[str, dict]:
    """모든 전략 설정을 DB에서 로드한다.

    Returns:
        {strategy_id: {"enabled": bool, "weight": float, "params": dict}}
    """
    result = supabase.table("strategy_config").select("*").execute()
    configs = {}
    for row in result.data:
        configs[row["strategy_id"]] = {
            "enabled": row["enabled"],
            "weight": float(row["weight"]),
            "params": row["params"] if isinstance(row["params"], dict) else {},
        }
    return configs


async def save(strategy_id: str, enabled: bool, weight: float, params: dict) -> None:
    """전략 설정을 DB에 저장(upsert)한다."""
    data = {
        "strategy_id": strategy_id,
        "enabled": enabled,
        "weight": float(weight),
        "params": params,
    }
    supabase.table("strategy_config").upsert(data, on_conflict="strategy_id").execute()
    logger.info("전략 설정 저장: %s (enabled=%s, weight=%.0f%%)", strategy_id, enabled, weight * 100)


async def save_weights(weights: dict[str, float]) -> None:
    """전략별 비중만 업데이트한다."""
    for sid, weight in weights.items():
        enabled = weight > 0
        # 기존 params 유지
        existing = supabase.table("strategy_config").select("params").eq("strategy_id", sid).execute()
        params = existing.data[0]["params"] if existing.data else {}
        await save(sid, enabled, weight, params)


async def save_params(strategy_id: str, params: dict) -> None:
    """전략 파라미터만 업데이트한다."""
    existing = supabase.table("strategy_config").select("enabled, weight").eq("strategy_id", strategy_id).execute()
    if existing.data:
        row = existing.data[0]
        await save(strategy_id, row["enabled"], float(row["weight"]), params)
    else:
        await save(strategy_id, True, 0.5, params)
