"""strategy_config CRUD — 전략 설정(비중/파라미터) 영속화.

사이클 M1-1 (Supabase→RDS 이전 단계1): supabase-py → `src.db.pg`(asyncpg) 전환.
함수 시그니처·반환형 100% 보존 — 호출부(order_engine 등) diff 0.
params(JSONB) 는 pg._init_conn 의 codec 등록으로 dict 왕복 보장.
"""

from __future__ import annotations

import logging
from datetime import datetime

import src.db.pg as pg
from src.db._kst import now_kst_iso

logger = logging.getLogger(__name__)


async def load_all() -> dict[str, dict]:
    """모든 전략 설정을 DB에서 로드한다.

    Returns:
        {strategy_id: {"enabled": bool, "weight": float, "params": dict}}
    """
    rows = await pg.fetch("SELECT * FROM strategy_config")
    configs = {}
    for row in rows:
        configs[row["strategy_id"]] = {
            "enabled": row["enabled"],
            "weight": float(row["weight"]),
            "params": row["params"] if isinstance(row["params"], dict) else {},
        }
    return configs


async def save(strategy_id: str, enabled: bool, weight: float, params: dict) -> None:
    """전략 설정을 DB에 저장(upsert)한다."""
    sql = """
        INSERT INTO strategy_config (
            strategy_id, enabled, weight, params, updated_at
        ) VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (strategy_id) DO UPDATE SET
            enabled = EXCLUDED.enabled,
            weight = EXCLUDED.weight,
            params = EXCLUDED.params,
            updated_at = EXCLUDED.updated_at
    """
    # asyncpg 는 timestamptz 파라미터에 datetime 객체를 요구 (str 바인딩 불가).
    # now_kst_iso() 문자열 계약(KST +09:00 ISO, 사이클 68)은 보존하고 로컬 변환만 수행.
    await pg.execute(
        sql,
        strategy_id,
        enabled,
        float(weight),
        params,
        datetime.fromisoformat(now_kst_iso()),
    )
    logger.info("전략 설정 저장: %s (enabled=%s, weight=%.0f%%)", strategy_id, enabled, weight * 100)


async def save_weights(weights: dict[str, float]) -> None:
    """전략별 비중만 업데이트한다."""
    for sid, weight in weights.items():
        enabled = weight > 0
        # 기존 params 유지
        existing = await pg.fetch(
            "SELECT params FROM strategy_config WHERE strategy_id = $1", sid
        )
        params = existing[0]["params"] if existing else {}
        if not isinstance(params, dict):
            params = {}
        await save(sid, enabled, weight, params)


async def save_params(strategy_id: str, params: dict) -> None:
    """전략 파라미터만 업데이트한다."""
    existing = await pg.fetch(
        "SELECT enabled, weight FROM strategy_config WHERE strategy_id = $1",
        strategy_id,
    )
    if existing:
        row = existing[0]
        await save(strategy_id, row["enabled"], float(row["weight"]), params)
    else:
        await save(strategy_id, True, 0.5, params)
