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
- **사이클 8 (2026-05-18) 매수 가드 4 모드 + 4 임계값**:
  - `buy_block_mode` `{"value": "OFF"|"WARN"|"SOFT"|"HARD"}` — 기본 HARD(현재 동작 회귀)
  - `buy_block_vix_threshold` `{"value": float}` — 기본 25.0 (사이클 2 하드코딩 동일)
  - `buy_block_fg_high_threshold` `{"value": float}` — 기본 85.0
  - `buy_block_fg_low_threshold` `{"value": float}` — 기본 15.0
  - `buy_block_regime_defensive_enabled` `{"value": bool}` — 기본 True
  - 4 모드 외 값은 `set_buy_block_mode` 가 ValueError.
  - 본 키들은 .env fallback 없음 (운영 가변 설정 — DB 미설정 시 코드 디폴트).

supabase 동기 SDK 호출은 모두 `asyncio.to_thread` 위임 (이벤트 루프 블로킹 차단).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from pydantic import BaseModel, Field

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


# ---------------------------------------------------------------------------
# 사이클 8 (2026-05-18) — 매수 가드 4 모드 + 4 임계값 조정
# ---------------------------------------------------------------------------
# 운영자가 시장 상황에 맞춰 즉시 전환/조정. 본 키들은 .env fallback 없음 —
# 운영 가변 설정이라 DB 미설정 시 코드 디폴트(기본 HARD + 사이클 2 하드코딩 임계).
#
# 기본값 = 현재 동작 회귀 보존 (사이클 2 까지 적용된 단일 HARD 분기 + 25/85/15/true).
# 운영자가 명시적으로 IntegrationToggleCard 에서 완화 선택 시에만 변경된다.

_BUY_BLOCK_MODE_KEY = "buy_block_mode"
_BUY_BLOCK_MODE_DEFAULT = "HARD"
_BUY_BLOCK_VALID_MODES = ("OFF", "WARN", "SOFT", "HARD")

_BUY_BLOCK_VIX_KEY = "buy_block_vix_threshold"
_BUY_BLOCK_VIX_DEFAULT = 25.0
_BUY_BLOCK_FG_HIGH_KEY = "buy_block_fg_high_threshold"
_BUY_BLOCK_FG_HIGH_DEFAULT = 85.0
_BUY_BLOCK_FG_LOW_KEY = "buy_block_fg_low_threshold"
_BUY_BLOCK_FG_LOW_DEFAULT = 15.0
_BUY_BLOCK_DEFENSIVE_KEY = "buy_block_regime_defensive_enabled"
_BUY_BLOCK_DEFENSIVE_DEFAULT = True


class BuyBlockThresholds(BaseModel):
    """매수 가드 4 임계값.

    - vix_threshold: VIX > 임계값 시 발동 (기본 25.0)
    - fg_high_threshold: fear_greed_score > 임계값 시 발동 (기본 85.0)
    - fg_low_threshold: fear_greed_score < 임계값 시 발동 (기본 15.0)
    - defensive_enabled: regime=defensive 차단 ON/OFF (기본 True)
    """

    vix_threshold: float = Field(default=_BUY_BLOCK_VIX_DEFAULT)
    fg_high_threshold: float = Field(default=_BUY_BLOCK_FG_HIGH_DEFAULT)
    fg_low_threshold: float = Field(default=_BUY_BLOCK_FG_LOW_DEFAULT)
    defensive_enabled: bool = Field(default=_BUY_BLOCK_DEFENSIVE_DEFAULT)


async def get_buy_block_mode() -> str:
    """매수 가드 모드 조회. 키 부재 시 기본 'HARD' (현재 동작 회귀)."""

    def _query():
        return (
            supabase.table("system_config")
            .select("value")
            .eq("key", _BUY_BLOCK_MODE_KEY)
            .execute()
        )

    try:
        result = await asyncio.to_thread(_query)
        rows = result.data or []
        if not rows:
            return _BUY_BLOCK_MODE_DEFAULT
        raw = rows[0].get("value")
        candidate: Optional[str] = None
        if isinstance(raw, dict):
            v = raw.get("value")
            if isinstance(v, str):
                candidate = v
        elif isinstance(raw, str):
            candidate = raw
        if candidate in _BUY_BLOCK_VALID_MODES:
            return candidate
        logger.warning(
            "[buy_block_mode] invalid stored mode=%r — 기본 %s 사용",
            candidate, _BUY_BLOCK_MODE_DEFAULT,
        )
        return _BUY_BLOCK_MODE_DEFAULT
    except Exception:
        logger.exception("[buy_block_mode] get 실패 — 기본 HARD 사용")
        return _BUY_BLOCK_MODE_DEFAULT


async def set_buy_block_mode(mode: str) -> None:
    """매수 가드 모드 저장. 4 모드 외 값은 ValueError."""
    if not isinstance(mode, str) or mode not in _BUY_BLOCK_VALID_MODES:
        raise ValueError(
            f"buy_block_mode must be one of {_BUY_BLOCK_VALID_MODES}, got {mode!r}"
        )

    payload = {
        "key": _BUY_BLOCK_MODE_KEY,
        "value": {"value": mode},
    }

    def _upsert():
        return (
            supabase.table("system_config")
            .upsert(payload, on_conflict="key")
            .execute()
        )

    await asyncio.to_thread(_upsert)


async def _get_float_or_default(key: str, default: float) -> float:
    """JSONB `{"value": float}` 조회. 키 부재/타입 불일치 시 default."""

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
            return default
        raw = rows[0].get("value")
        if isinstance(raw, dict):
            v = raw.get("value")
            if isinstance(v, (int, float)):
                return float(v)
        elif isinstance(raw, (int, float)):
            return float(raw)
        return default
    except Exception:
        logger.exception("[buy_block_thresholds] get %s 실패 — 기본 %s 사용", key, default)
        return default


async def _get_bool_or_default(key: str, default: bool) -> bool:
    """JSONB `{"value": bool}` 조회. 키 부재/타입 불일치 시 default."""

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
            return default
        raw = rows[0].get("value")
        if isinstance(raw, dict):
            v = raw.get("value")
            if isinstance(v, bool):
                return v
        elif isinstance(raw, bool):
            return raw
        return default
    except Exception:
        logger.exception("[buy_block_thresholds] get %s 실패 — 기본 %s 사용", key, default)
        return default


async def get_buy_block_thresholds() -> BuyBlockThresholds:
    """매수 가드 4 임계값 조회. 키 부재 시 기본 25.0/85.0/15.0/True."""
    vix = await _get_float_or_default(_BUY_BLOCK_VIX_KEY, _BUY_BLOCK_VIX_DEFAULT)
    fg_high = await _get_float_or_default(_BUY_BLOCK_FG_HIGH_KEY, _BUY_BLOCK_FG_HIGH_DEFAULT)
    fg_low = await _get_float_or_default(_BUY_BLOCK_FG_LOW_KEY, _BUY_BLOCK_FG_LOW_DEFAULT)
    defensive = await _get_bool_or_default(
        _BUY_BLOCK_DEFENSIVE_KEY, _BUY_BLOCK_DEFENSIVE_DEFAULT,
    )
    return BuyBlockThresholds(
        vix_threshold=vix,
        fg_high_threshold=fg_high,
        fg_low_threshold=fg_low,
        defensive_enabled=defensive,
    )


async def _set_float(key: str, value: float) -> None:
    payload = {"key": key, "value": {"value": float(value)}}

    def _upsert():
        return (
            supabase.table("system_config")
            .upsert(payload, on_conflict="key")
            .execute()
        )

    await asyncio.to_thread(_upsert)


async def set_buy_block_thresholds(
    vix_threshold: Optional[float] = None,
    fg_high_threshold: Optional[float] = None,
    fg_low_threshold: Optional[float] = None,
    defensive_enabled: Optional[bool] = None,
) -> BuyBlockThresholds:
    """매수 가드 임계값 부분 갱신. None 인자는 기존 값 보존.

    범위 검증은 라우트 계층(Pydantic) 책임 — 본 헬퍼는 DB 저장만.
    반환값은 갱신 후 전체 상태.
    """
    if vix_threshold is not None:
        await _set_float(_BUY_BLOCK_VIX_KEY, vix_threshold)
    if fg_high_threshold is not None:
        await _set_float(_BUY_BLOCK_FG_HIGH_KEY, fg_high_threshold)
    if fg_low_threshold is not None:
        await _set_float(_BUY_BLOCK_FG_LOW_KEY, fg_low_threshold)
    if defensive_enabled is not None:
        await _set_bool(_BUY_BLOCK_DEFENSIVE_KEY, defensive_enabled)
    return await get_buy_block_thresholds()
