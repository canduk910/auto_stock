"""system_config 키-값 헬퍼.

`system_config` 테이블의 (key, value JSONB) 행을 키별 헬퍼로 노출한다.

현재 정의된 키:
- `cash_usage_ratio` (J3, 2026-05-12): `{"value": float}` — 매매 가용 자금 비율.
  scheduler `_boot()` 에서 `summary.net_asset × ratio` 로 `allocate_funds()` 호출.
  **사이클 2 (2026-05-17) 범위 확장**: [0.5, 1.0] → **[0.0, 1.0]**. step 0.05 유지.
  레짐 자동 조정(`auto_regime_adjust=true`) 시 defensive(cash_min=75) → 0.25 같은
  0.5 미만 값이 정상 입력될 수 있어 범위 확장.
- `auto_regime_adjust` (사이클 2, 2026-05-17): `{"value": bool}` — 매크로 레짐 기반
  cash_usage_ratio 자동 조정 활성 여부. 기본 True. False 면 운영자 수동 설정 보존.
- `dkstock_regime_enabled` (사이클 5, 2026-05-17): `{"value": bool}` — 외부 매크로
  서버(dkstock.cloud) 활성 여부. **키 부재 시 `None` 반환** — 호출자가 settings.* 환경
  변수로 fallback. .env 의존도 최소화 + 운영자 즉시 ON/OFF 보장.
- `kis_mcp_enabled` (사이클 5, 2026-05-17): `{"value": bool}` — 외부 백테스트 서버
  활성 여부. dkstock_regime_enabled 와 동일 패턴(DB 우선, .env fallback).

supabase 동기 SDK 호출은 모두 `asyncio.to_thread` 위임 (이벤트 루프 블로킹 차단).
"""

from __future__ import annotations

import asyncio
import logging

from src.db.supabase import supabase

logger = logging.getLogger(__name__)


_CASH_USAGE_RATIO_KEY = "cash_usage_ratio"
_CASH_USAGE_RATIO_DEFAULT = 1.0
# 사이클 2 (2026-05-17): MIN 0.5 → 0.0 확장 (defensive 레짐 자동 조정 0.25 수용)
_CASH_USAGE_RATIO_MIN = 0.0
_CASH_USAGE_RATIO_MAX = 1.0
_CASH_USAGE_RATIO_STEP = 0.05

_AUTO_REGIME_ADJUST_KEY = "auto_regime_adjust"
_AUTO_REGIME_ADJUST_DEFAULT = True


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

    **사이클 2 (2026-05-17)**: 범위 [0.5, 1.0] → **[0.0, 1.0]** 확장. step 0.05 유지.
    레짐 자동 조정으로 defensive cash_min=75 → 0.25 같은 값 정상 수용.
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


async def get_auto_regime_adjust() -> bool:
    """매크로 레짐 기반 cash_usage_ratio 자동 조정 활성 여부.

    사이클 2 (2026-05-17). 키 부재 시 기본 True. False 면 운영자 수동 설정 보존.
    """

    def _query():
        return (
            supabase.table("system_config")
            .select("value")
            .eq("key", _AUTO_REGIME_ADJUST_KEY)
            .execute()
        )

    try:
        result = await asyncio.to_thread(_query)
        rows = result.data or []
        if not rows:
            return _AUTO_REGIME_ADJUST_DEFAULT
        raw = rows[0].get("value")
        if isinstance(raw, dict):
            v = raw.get("value")
            if v is None:
                return _AUTO_REGIME_ADJUST_DEFAULT
            return bool(v)
        if isinstance(raw, bool):
            return raw
        return _AUTO_REGIME_ADJUST_DEFAULT
    except Exception:
        logger.exception("[auto_regime_adjust] get 실패 — 기본 True 사용")
        return _AUTO_REGIME_ADJUST_DEFAULT


async def set_auto_regime_adjust(value: bool) -> None:
    """매크로 레짐 기반 cash_usage_ratio 자동 조정 활성 여부를 저장한다.

    사이클 2 (2026-05-17). 값은 bool 강제 변환.
    """
    payload = {
        "key": _AUTO_REGIME_ADJUST_KEY,
        "value": {"value": bool(value)},
    }

    def _upsert():
        return (
            supabase.table("system_config")
            .upsert(payload, on_conflict="key")
            .execute()
        )

    await asyncio.to_thread(_upsert)


# ---------------------------------------------------------------------------
# 사이클 5 (2026-05-17) — 외부 통합 토글 헬퍼
# ---------------------------------------------------------------------------
# 기존 패턴(cash_usage_ratio / auto_regime_adjust) 과 다른 점:
# **키 부재 시 `None` 반환** — 호출자가 .env 환경변수로 fallback 결정.
# 이로써 운영 환경에서 DB 갱신 안 하면 기존 .env 동작 100% 보존(하위 호환).
_DKSTOCK_REGIME_ENABLED_KEY = "dkstock_regime_enabled"
_KIS_MCP_ENABLED_KEY = "kis_mcp_enabled"


async def _get_bool_or_none(key: str) -> bool | None:
    """system_config 의 bool JSONB 값을 안전하게 조회. 키 부재 → None."""

    def _query():
        return (
            supabase.table("system_config")
            .select("value")
            .eq("key", key)
            .execute()
        )

    try:
        result = await asyncio.to_thread(_query)
        rows = result.data or []
        if not rows:
            return None
        raw = rows[0].get("value")
        if isinstance(raw, dict):
            v = raw.get("value")
            if v is None:
                return None
            return bool(v)
        if isinstance(raw, bool):
            return raw
        # 문자열 'true'/'false' 호환 (마이그레이션 텍스트 INSERT 대비)
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if normalized == "true":
                return True
            if normalized == "false":
                return False
        return None
    except Exception:
        logger.exception("[system_config] get %s 실패 — None 반환 (호출자 fallback)", key)
        return None


async def _set_bool(key: str, value: bool) -> None:
    """system_config bool 값 upsert. JSONB 표준 형태 `{"value": bool}`."""
    payload = {
        "key": key,
        "value": {"value": bool(value)},
    }

    def _upsert():
        return (
            supabase.table("system_config")
            .upsert(payload, on_conflict="key")
            .execute()
        )

    await asyncio.to_thread(_upsert)


async def get_dkstock_regime_enabled() -> bool | None:
    """외부 매크로 서버 활성 여부 조회. 키 부재 → None (호출자 .env fallback)."""
    return await _get_bool_or_none(_DKSTOCK_REGIME_ENABLED_KEY)


async def set_dkstock_regime_enabled(value: bool) -> None:
    """외부 매크로 서버 활성 여부 저장. bool 강제 변환."""
    await _set_bool(_DKSTOCK_REGIME_ENABLED_KEY, value)


async def get_kis_mcp_enabled() -> bool | None:
    """외부 백테스트 서버 활성 여부 조회. 키 부재 → None (호출자 .env fallback)."""
    return await _get_bool_or_none(_KIS_MCP_ENABLED_KEY)


async def set_kis_mcp_enabled(value: bool) -> None:
    """외부 백테스트 서버 활성 여부 저장. bool 강제 변환."""
    await _set_bool(_KIS_MCP_ENABLED_KEY, value)
