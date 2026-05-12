"""system_config 키-값 헬퍼.

`system_config` 테이블의 (key, value JSONB) 행을 키별 헬퍼로 노출한다.

현재 정의된 키:
- `cash_usage_ratio` (J3, 2026-05-12): `{"value": float}` — 매매 가용 자금 비율.
  scheduler `_boot()` 에서 `summary.net_asset × ratio` 로 `allocate_funds()` 호출.
  범위: [0.5, 1.0], 5% 단위 (운영자 실수 방지). 기본 1.0.

supabase 동기 SDK 호출은 모두 `asyncio.to_thread` 위임 (이벤트 루프 블로킹 차단).
"""

from __future__ import annotations

import asyncio
import logging

from src.db.supabase import supabase

logger = logging.getLogger(__name__)


_CASH_USAGE_RATIO_KEY = "cash_usage_ratio"
_CASH_USAGE_RATIO_DEFAULT = 1.0
_CASH_USAGE_RATIO_MIN = 0.5
_CASH_USAGE_RATIO_MAX = 1.0
_CASH_USAGE_RATIO_STEP = 0.05


async def get_cash_usage_ratio() -> float:
    """매매 가용 자금 비율을 조회한다.

    키 부재 시 기본 1.0 반환.
    """

    def _query():
        return (
            supabase.table("system_config")
            .select("value")
            .eq("key", _CASH_USAGE_RATIO_KEY)
            .execute()
        )

    try:
        result = await asyncio.to_thread(_query)
        rows = result.data or []
        if not rows:
            return _CASH_USAGE_RATIO_DEFAULT
        raw = rows[0].get("value")
        # JSONB 가 {"value": x} 형태로 저장되어 있음. 과거 호환을 위해 float 직저장도 허용.
        if isinstance(raw, dict):
            v = raw.get("value")
            if v is None:
                return _CASH_USAGE_RATIO_DEFAULT
            return float(v)
        if isinstance(raw, (int, float)):
            return float(raw)
        return _CASH_USAGE_RATIO_DEFAULT
    except Exception:
        logger.exception("[cash_usage_ratio] get 실패 — 기본 1.0 사용")
        return _CASH_USAGE_RATIO_DEFAULT


async def set_cash_usage_ratio(ratio: float) -> None:
    """매매 가용 자금 비율을 저장한다.

    범위: [0.5, 1.0]. 5% 단위 자동 보정 (운영자 실수 방지).
    범위 외 입력은 ValueError.
    """
    if ratio < _CASH_USAGE_RATIO_MIN or ratio > _CASH_USAGE_RATIO_MAX:
        raise ValueError(
            f"cash_usage_ratio out of range "
            f"[{_CASH_USAGE_RATIO_MIN}, {_CASH_USAGE_RATIO_MAX}]: {ratio}"
        )

    adjusted = round(ratio / _CASH_USAGE_RATIO_STEP) * _CASH_USAGE_RATIO_STEP
    # 부동소수 표현 안정화 (5% 단위라 소수 둘째 자리까지 충분)
    adjusted = round(adjusted, 2)

    payload = {
        "key": _CASH_USAGE_RATIO_KEY,
        "value": {"value": adjusted},
    }

    def _upsert():
        return (
            supabase.table("system_config")
            .upsert(payload, on_conflict="key")
            .execute()
        )

    await asyncio.to_thread(_upsert)
