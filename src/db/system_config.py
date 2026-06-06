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


# ---------------------------------------------------------------------------
# 사이클 23 (2026-05-20) — AI 자문 자동 적용 토글
# ---------------------------------------------------------------------------
# 기본 False — 안전 우선. 운영자가 명시 활성화 후에만 P3 자동 적용 작동.
_AUTO_APPLY_ENABLED_KEY = "auto_apply_enabled"


async def get_auto_apply_enabled() -> bool:
    """AI 자문 자동 적용 토글. 기본 False — 안전 우선.

    사이클 23 P3-3. 키 부재 시 False (안전 우선, 기존 수동 흐름 보존).
    """
    v = await _get_bool_or_none(_AUTO_APPLY_ENABLED_KEY)
    return bool(v) if v is not None else False


async def set_auto_apply_enabled(value: bool) -> None:
    """AI 자문 자동 적용 토글 저장. bool 강제 변환.

    사이클 23 P3-3.
    """
    await _set_bool(_AUTO_APPLY_ENABLED_KEY, value)


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


# ---------------------------------------------------------------------------
# 사이클 62 (2026-06-05) → 사이클 64 (2026-06-06) 단순화 — 가격 필터 (scanner 단계 이동)
# ---------------------------------------------------------------------------
# 사이클 64 변경: mode 폐기 (HARD/WARN/OFF 제거), 단순 min/max 필터링만.
# 적용 위치: risk.on_tick → scanner.subscribe_filtered_stocks (Q4 옵션 A).
# 키 2종 (price_filter_mode 키는 DB row 잔존 허용, 코드 미참조):
_PRICE_FILTER_MIN_KEY = "price_filter_min"    # 정수(원). 0 = 비활성
_PRICE_FILTER_MAX_KEY = "price_filter_max"    # 정수(원). 0 = 비활성(무한대 의미)

# 디폴트 — 비활성 (운영 시작 안전성 우선)
_PRICE_FILTER_MIN_DEFAULT = 0
_PRICE_FILTER_MAX_DEFAULT = 0


class PriceFilter(BaseModel):
    """가격 필터 설정 (사이클 64, 2026-06-06 단순화).

    scanner.subscribe_filtered_stocks 진입 직전 적용 (사이클 38 명문화 보존 — 매수 후보 전용).
    보유/익일청산 종목은 절대 제외 안 됨 (사이클 32 R4 universe guard + 사이클 64 Q1 옵션 D).
    """

    min_price: int = 0   # 0 = 비활성
    max_price: int = 0   # 0 = 비활성 (무한대 의미)
    # mode 필드 제거 (사이클 64 — HARD/WARN/OFF 폐기)

    @property
    def is_active(self) -> bool:
        """min 또는 max 가 > 0 이면 활성."""
        return self.min_price > 0 or self.max_price > 0


async def get_price_filter() -> PriceFilter:
    """현재 가격 필터 설정 조회.

    2 키(price_filter_min / price_filter_max) 조회 후 PriceFilter 반환.
    키 부재 시 디폴트 PriceFilter(min=0, max=0) 반환.
    buy_block_mode 패턴 답습 — JSONB {"value": ...} 형태.
    """
    min_price = await _get_int_or_default(_PRICE_FILTER_MIN_KEY, _PRICE_FILTER_MIN_DEFAULT)
    max_price = await _get_int_or_default(_PRICE_FILTER_MAX_KEY, _PRICE_FILTER_MAX_DEFAULT)
    return PriceFilter(min_price=min_price, max_price=max_price)


async def set_price_filter(
    *,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
) -> None:
    """가격 필터 설정 부분 갱신. 생략된 키는 기존 값 보존.

    - min_price 음수 → ValueError
    - max_price 음수 → ValueError
    - min/max 둘 다 명시 + max < min (단 둘 다 > 0) → ValueError

    부분 갱신: set_price_filter(min_price=5000) — max 기존 값 보존.
    사이클 64 — mode 인자 자체 제거 (HARD/WARN/OFF 폐기).
    """
    if min_price is not None:
        if min_price < 0:
            raise ValueError(f"min_price 음수 불가: {min_price}")

    if max_price is not None:
        if max_price < 0:
            raise ValueError(f"max_price 음수 불가: {max_price}")

    # max < min 교차 검증 (둘 다 명시 + 둘 다 > 0)
    if min_price is not None and max_price is not None:
        if min_price > 0 and max_price > 0 and max_price < min_price:
            raise ValueError(
                f"max_price({max_price}) < min_price({min_price}) 불가"
            )

    if min_price is not None:
        await _set_int(_PRICE_FILTER_MIN_KEY, min_price)
    if max_price is not None:
        await _set_int(_PRICE_FILTER_MAX_KEY, max_price)


# ---------------------------------------------------------------------------
# 내부 헬퍼 — int 조회/저장 (사이클 62 신규, 사이클 64: str 헬퍼 폐기)
# ---------------------------------------------------------------------------

async def _get_int_or_default(key: str, default: int) -> int:
    """JSONB {"value": int} 조회. 키 부재/타입 불일치 시 default."""

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
                return int(v)
        elif isinstance(raw, (int, float)):
            return int(raw)
        return default
    except Exception:
        logger.exception("[price_filter] get %s 실패 — 기본 %s 사용", key, default)
        return default


async def _get_str_or_default_UNUSED(key: str, default: str, valid: tuple) -> str:  # noqa: N802
    """JSONB {"value": str} 조회 (사이클 64 미사용 — price_filter_mode 폐기).

    참고: 하위 코드 잔재 방지용 더미 선언. 실제 호출처 없음.
    """

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
        candidate: Optional[str] = None
        if isinstance(raw, dict):
            v = raw.get("value")
            if isinstance(v, str):
                candidate = v
        elif isinstance(raw, str):
            candidate = raw
        if candidate in valid:
            return candidate
        logger.warning("[price_filter] invalid stored value=%r key=%s — 기본 %s 사용", candidate, key, default)
        return default
    except Exception:
        logger.exception("[price_filter] get %s 실패 — 기본 %s 사용", key, default)
        return default


async def _set_int(key: str, value: int) -> None:
    """JSONB {"value": int} upsert."""
    payload = {"key": key, "value": {"value": int(value)}}

    def _upsert():
        return (
            supabase.table("system_config")
            .upsert(payload, on_conflict="key")
            .execute()
        )

    await asyncio.to_thread(_upsert)


# _set_str 제거 (사이클 64 — price_filter_mode 폐기로 사용처 0)


# ---------------------------------------------------------------------------
# 사이클 65 (2026-06-06) — 거래대금 필터 (scanner 단계, Q1 옵션 A)
# ---------------------------------------------------------------------------
# 매수 후보 풀에서 누적 거래대금 임계 미만 종목 제거.
# 작전주/저유동성 차단 = 사이클 64 갭상승 회피 폐기의 *유일 보강 메커니즘*.
# 디폴트 0 (비활성) — 운영자 명시 활성화 없이 push 즉시 회귀 0.
# 보유/익일청산 종목은 절대 제외 안 됨 (Q1 옵션 D 3 중 안전망, 사이클 64 답습).
# 단위: 원(₩) — scanner.py MIN_TRADE_AMOUNT 패턴 답습.

_TRADE_AMOUNT_FILTER_MIN_KEY = "trade_amount_filter_min"
_TRADE_AMOUNT_FILTER_MIN_DEFAULT = 0


class TradeAmountFilter(BaseModel):
    """거래대금 필터 설정 (사이클 65, 2026-06-06).

    scanner.subscribe_filtered_stocks 진입 직전 적용 (사이클 38 명문화 보존 — 매수 후보 전용).
    보유/익일청산 종목은 절대 제외 안 됨 (사이클 32 R4 universe guard + 사이클 64 Q1 옵션 D).
    작전주/저유동성 차단 = 사이클 64 갭상승 회피 폐기의 *유일 보강 메커니즘*.
    """

    min_amount: int = 0  # 원 단위, 0 = 비활성

    @property
    def is_active(self) -> bool:
        """min_amount > 0 이면 활성 (0 = 비활성, 전체 통과)."""
        return self.min_amount > 0


async def get_trade_amount_filter() -> TradeAmountFilter:
    """거래대금 필터 설정 조회.

    사이클 65 (2026-06-06). 키 부재 시 TradeAmountFilter(min_amount=0) 반환 (비활성 디폴트).
    `get_price_filter` 패턴 답습 — `_get_int_or_default` 헬퍼 재사용.
    """
    min_amount = await _get_int_or_default(
        _TRADE_AMOUNT_FILTER_MIN_KEY, _TRADE_AMOUNT_FILTER_MIN_DEFAULT
    )
    return TradeAmountFilter(min_amount=min_amount)


async def set_trade_amount_filter(
    *,
    min_amount: Optional[int] = None,
) -> None:
    """거래대금 필터 설정 부분 갱신. 생략된 키는 기존 값 보존.

    사이클 65 (2026-06-06).
    - min_amount 음수 → ValueError (작동 방지 안전 가드)
    - None 인 키는 보존 (부분 갱신 패턴 — `set_price_filter` 답습)
    """
    if min_amount is not None:
        if min_amount < 0:
            raise ValueError(f"min_amount 음수 불가: {min_amount}")
        await _set_int(_TRADE_AMOUNT_FILTER_MIN_KEY, min_amount)
