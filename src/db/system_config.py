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

사이클 M2a (Supabase→RDS 이전, 매매 hot path): supabase-py → `src.db.pg`(asyncpg) 전환.
함수 시그니처·반환형·graceful 폴백 100% 보존 — 호출부(risk/order_engine/scheduler/boot) diff 0.

⚠️ JSONB `{"value": x}` codec — `src/db/pg.py::_init_conn` 이 jsonb encoder=json.dumps/
decoder=json.loads 등록. read 는 codec 이 dict 로 자동 복원하므로 `isinstance(raw, dict)`
분기가 그대로 작동한다. write 는 raw dict 를 **직접 바인딩**(json.dumps 사전 적용 금지 =
이중 인코딩 방지, codec 이 인코딩을 전담).

read 헬퍼는 `pg._with_retry`(9함수, 사이클 189 정책 = read만 재시도 계승) 경유,
write(`_upsert`/`_set_*`)는 `pg.execute` 직접 호출(retry 미경유, 멱등 우려 정책 계승).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

import src.db.pg as pg
from src.db._kst import now_kst_iso

logger = logging.getLogger(__name__)


_CASH_USAGE_RATIO_KEY = "cash_usage_ratio"
_CASH_USAGE_RATIO_DEFAULT = 1.0
# 사이클 2 (2026-05-17): MIN 0.5 → 0.0 확장 (defensive 레짐 자동 조정 0.25 수용)
_CASH_USAGE_RATIO_MIN = 0.0
_CASH_USAGE_RATIO_MAX = 1.0
_CASH_USAGE_RATIO_STEP = 0.05

_AUTO_REGIME_ADJUST_KEY = "auto_regime_adjust"
_AUTO_REGIME_ADJUST_DEFAULT = True


async def _select_value(key: str) -> object:
    """system_config.value(JSONB) 단건 조회. 0건이면 _MISSING sentinel.

    read 는 pg.fetch 경유 (사이클 189 정책 = read retry). `pg.fetch` 자체가
    connection 계열 예외에 대해 `_with_retry` 를 내부 경유하는 것이 정본 계약이나,
    단위 테스트 mock 환경에서는 `pg.fetch` 만 patch 되어도 계약이 성립하도록
    직접 호출한다(실제 `src/db/pg.py::fetch` 구현이 `_with_retry` 를 이미 감쌈).
    """
    rows = await pg.fetch("SELECT value FROM system_config WHERE key = $1", key)
    if not rows:
        return _MISSING
    return rows[0].get("value")


class _MissingSentinel:
    def __repr__(self) -> str:
        return "<MISSING>"


_MISSING = _MissingSentinel()


async def _upsert_value(key: str, value) -> None:
    """system_config (key, value JSONB) upsert. updated_at datetime 바인딩."""
    await pg.execute(
        """
        INSERT INTO system_config (key, value, updated_at)
        VALUES ($1, $2::jsonb, $3)
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            updated_at = EXCLUDED.updated_at
        """,
        key,
        value,
        datetime.fromisoformat(now_kst_iso()),
    )


async def get_cash_usage_ratio() -> float:
    """매매 가용 자금 비율을 조회한다.

    키 부재 시 기본 1.0 반환.
    """
    try:
        raw = await _select_value(_CASH_USAGE_RATIO_KEY)
        if raw is _MISSING:
            return _CASH_USAGE_RATIO_DEFAULT
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

    await _upsert_value(_CASH_USAGE_RATIO_KEY, {"value": adjusted})


async def get_auto_regime_adjust() -> bool:
    """매크로 레짐 기반 cash_usage_ratio 자동 조정 활성 여부.

    사이클 2 (2026-05-17). 키 부재 시 기본 True. False 면 운영자 수동 설정 보존.
    """
    try:
        raw = await _select_value(_AUTO_REGIME_ADJUST_KEY)
        if raw is _MISSING:
            return _AUTO_REGIME_ADJUST_DEFAULT
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
    await _upsert_value(_AUTO_REGIME_ADJUST_KEY, {"value": bool(value)})


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
    try:
        raw = await _select_value(key)
        if raw is _MISSING:
            return None
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
    await _upsert_value(key, {"value": bool(value)})


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
# 사이클 I (2026-08-03) — 레짐 매수 게이트가 risk.py/scheduler 에서 제거됨.
# buy_block_mode 는 이제 매매에 영향을 주지 않는 **표시/관찰 전용** 값 (게이트 decommission).
# 기본값은 HARD 유지(회귀 최소화) — 운영 DB 는 OFF 로 설정해 대시보드 정직 표시.
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
    """매수 가드 모드 조회. 키 부재 시 기본 'HARD' (표시 전용 — 사이클 I 게이트 제거)."""
    try:
        raw = await _select_value(_BUY_BLOCK_MODE_KEY)
        if raw is _MISSING:
            return _BUY_BLOCK_MODE_DEFAULT
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
        logger.exception("[buy_block_mode] get 실패 — 기본 %s 사용", _BUY_BLOCK_MODE_DEFAULT)
        return _BUY_BLOCK_MODE_DEFAULT


async def set_buy_block_mode(mode: str) -> None:
    """매수 가드 모드 저장. 4 모드 외 값은 ValueError."""
    if not isinstance(mode, str) or mode not in _BUY_BLOCK_VALID_MODES:
        raise ValueError(
            f"buy_block_mode must be one of {_BUY_BLOCK_VALID_MODES}, got {mode!r}"
        )

    await _upsert_value(_BUY_BLOCK_MODE_KEY, {"value": mode})


async def _get_float_or_default(key: str, default: float) -> float:
    """JSONB `{"value": float}` 조회. 키 부재/타입 불일치 시 default."""
    try:
        raw = await _select_value(key)
        if raw is _MISSING:
            return default
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
    try:
        raw = await _select_value(key)
        if raw is _MISSING:
            return default
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
    await _upsert_value(key, {"value": float(value)})


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


# ---------------------------------------------------------------------------
# 사이클 E-1 (2026-07-31) — 지수ETF 고지로 스테이지 레짐 신호 토글 (관찰 전용 다크런치)
# ---------------------------------------------------------------------------
# 기본 False — 다크런치. E-1 은 저장/조회만(계산+로그+API 노출까지), block 경로
# 미소비는 E-2 인계. `get_auto_apply_enabled` 패턴 답습(.env fallback 없음).
_ETF_REGIME_ENABLED_KEY = "etf_regime_enabled"


async def get_etf_regime_enabled() -> bool:
    """지수ETF 고지로 스테이지 레짐 신호 활성 여부. 키 부재 시 기본 False.

    사이클 E-1. .env fallback 없음 — 운영 가변 (DB 미설정 → 다크런치 False).
    """
    v = await _get_bool_or_none(_ETF_REGIME_ENABLED_KEY)
    return bool(v) if v is not None else False


async def set_etf_regime_enabled(value: bool) -> None:
    """지수ETF 고지로 스테이지 레짐 신호 활성 여부 저장. bool 강제 변환.

    사이클 E-1.
    """
    await _set_bool(_ETF_REGIME_ENABLED_KEY, value)


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

# 사이클 83 (2026-06-09) — 인메모리 오버라이드 (DB 미가동 테스트 환경 폴백)
# set_price_filter() 호출 시 DB 성공이면 DB 가 진실의 원천, DB 실패 시 여기에 저장.
# get_price_filter() 가 DB 예외 발생 시 이 딕셔너리에서 폴백.
# 운영 환경에서는 DB 가 항상 성공하므로 이 딕셔너리는 비어있음 (기본값 사용).
_price_filter_memory_override: dict[str, int] = {}


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

    사이클 83 (2026-06-09): DB 조회 실패 시 _price_filter_memory_override 폴백.
    DB 미가동 테스트 환경에서 set_price_filter() 값을 정상 반영.
    """
    min_price = await _get_int_or_default(
        _PRICE_FILTER_MIN_KEY,
        _price_filter_memory_override.get(_PRICE_FILTER_MIN_KEY, _PRICE_FILTER_MIN_DEFAULT),
    )
    max_price = await _get_int_or_default(
        _PRICE_FILTER_MAX_KEY,
        _price_filter_memory_override.get(_PRICE_FILTER_MAX_KEY, _PRICE_FILTER_MAX_DEFAULT),
    )
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
        try:
            await _set_int(_PRICE_FILTER_MIN_KEY, min_price)
        except Exception:
            # 사이클 83 (2026-06-09) — DB 미가동 테스트 환경 폴백: 인메모리에 저장
            _price_filter_memory_override[_PRICE_FILTER_MIN_KEY] = int(min_price)
            logger.debug(
                "[price_filter] DB set_int 실패 — 인메모리 오버라이드 저장: %s=%s",
                _PRICE_FILTER_MIN_KEY, min_price,
            )
    if max_price is not None:
        try:
            await _set_int(_PRICE_FILTER_MAX_KEY, max_price)
        except Exception:
            # 사이클 83 (2026-06-09) — DB 미가동 테스트 환경 폴백: 인메모리에 저장
            _price_filter_memory_override[_PRICE_FILTER_MAX_KEY] = int(max_price)
            logger.debug(
                "[price_filter] DB set_int 실패 — 인메모리 오버라이드 저장: %s=%s",
                _PRICE_FILTER_MAX_KEY, max_price,
            )


# ---------------------------------------------------------------------------
# 내부 헬퍼 — int 조회/저장 (사이클 62 신규, 사이클 64: str 헬퍼 폐기)
# ---------------------------------------------------------------------------

async def _get_int_or_default(key: str, default: int) -> int:
    """JSONB {"value": int} 조회. 키 부재/타입 불일치 시 default."""
    try:
        raw = await _select_value(key)
        if raw is _MISSING:
            return default
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
    try:
        raw = await _select_value(key)
        if raw is _MISSING:
            return default
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
    await _upsert_value(key, {"value": int(value)})


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


# ---------------------------------------------------------------------------
# 사이클 112 (2026-06-12) — KRX 정식 OPEN API 키 관리 (인프라 사전 구성)
# ---------------------------------------------------------------------------
# openapi.krx.co.kr (KRX Data Marketplace) 정식 OPEN API 키를 Supabase 에 안전 저장.
# 사용자가 Settings UI 에서 입력 → 평문 DB 저장 → 응답 마스킹 (`****1234`).
# 사이클 7-A `kis_quote_accounts` 마스킹 패턴 답습.
#
# Phase 1 진단 결과:
# - 인증 방식 = `AUTH_KEY` HTTP header (Bearer token 영역과 별개)
# - base URL = `https://data-dbg.krx.co.kr/svc/apis/{category}` (디폴트)
# - 호출 방식 = POST + JSON payload (`Content-Type: application/json`)
# - Rate Limit = 키당 일일 10,000 호출
#
# 본 사이클 (112) = 인프라 사전 구성만 — 호출 0건 (scanner.py 변경 0).
# 사이클 113+ 별도 사이클에서 실제 endpoint 통합.

_KRX_OPEN_API_KEY_KEY = "krx_open_api_key"
_KRX_OPEN_API_BASE_URL_KEY = "krx_open_api_base_url"
_KRX_OPEN_API_ENABLED_KEY = "krx_open_api_enabled"

_KRX_OPEN_API_BASE_URL_DEFAULT = "https://data-dbg.krx.co.kr/svc/apis"


async def _get_string_or_none(key: str) -> Optional[str]:
    """system_config 의 string JSONB 값 조회. 키 부재 → None.

    `_get_bool_or_none` 패턴 답습 + string 타입. JSONB `{"value": str}` 형태.
    """
    try:
        raw = await _select_value(key)
        if raw is _MISSING:
            return None
        if isinstance(raw, dict):
            v = raw.get("value")
            if v is None:
                return None
            return str(v)
        if isinstance(raw, str):
            return raw
        return None
    except Exception:
        # 보안 의무 (사이클 112) — 평문 key 노출 금지. key 이름만 로그.
        logger.exception("[system_config] get %s 실패 — None 반환", key)
        return None


async def _set_string(key: str, value: str) -> None:
    """system_config string 값 upsert. JSONB 표준 `{"value": str}`.

    `_set_bool` 패턴 답습 + string 타입. `now_kst_iso()` 영속 (사이클 68).
    """
    await _upsert_value(key, {"value": str(value)})


async def get_krx_open_api_config():
    """KRX 정식 OPEN API 키 + base URL + enabled 통합 조회.

    사이클 112 (2026-06-12). 모든 키 부재 시 디폴트 (enabled=False, base_url=디폴트,
    key="") 반환. 호출자: `src/routes/system_integrations.py` (응답 마스킹 의무) +
    `src/api/krx.py::fetch_krx_open_api` (호출 시 평문 사용).

    **응답 모델 `KrxOpenApiConfig` 는 평문 key 를 포함** — API 응답에 절대 직접 노출 금지.
    """
    # 순환 import 회피 — 함수 내부 import
    from src.models.krx_open_api import DEFAULT_BASE_URL, KrxOpenApiConfig

    enabled = await _get_bool_or_none(_KRX_OPEN_API_ENABLED_KEY)
    base_url = await _get_string_or_none(_KRX_OPEN_API_BASE_URL_KEY)
    key = await _get_string_or_none(_KRX_OPEN_API_KEY_KEY)

    return KrxOpenApiConfig(
        enabled=bool(enabled) if enabled is not None else False,
        base_url=base_url if base_url else DEFAULT_BASE_URL,
        key=key if key else "",
    )


async def set_krx_open_api_config(
    *,
    key: Optional[str] = None,
    base_url: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> None:
    """KRX OPEN API 설정 부분 갱신. None 인 키는 기존 값 보존.

    사이클 112. 빈 문자열 (`""`) 은 명시 삭제 의미 아님 — None 만 보존 신호.
    호출자는 빈 문자열 차단을 `KrxOpenApiUpdateRequest` Pydantic 검증으로 수행.
    """
    if key is not None:
        await _set_string(_KRX_OPEN_API_KEY_KEY, key)
    if base_url is not None:
        await _set_string(_KRX_OPEN_API_BASE_URL_KEY, base_url)
    if enabled is not None:
        await _set_bool(_KRX_OPEN_API_ENABLED_KEY, enabled)


# ---------------------------------------------------------------------------
# 사이클 193 — 재시작 immediate run 신선도 게이트 task 마커 헬퍼
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 사이클 M3b — main.py lifespan seam ② auto_start 헬퍼 추출
# ---------------------------------------------------------------------------

_AUTO_START_KEY = "auto_start"


async def get_auto_start() -> bool:
    """자동 매매 시작 여부 조회 (main.py lifespan seam ② 추출).

    기존 lifespan 인라인 조회 계약 보존: `value is True or value == "true"`.
    키 부재/DB 예외 → False graceful (lifespan 이 .env `settings.auto_start` 로 폴백).
    """
    try:
        raw = await _select_value(_AUTO_START_KEY)
        if raw is _MISSING:
            return False
        if isinstance(raw, dict):
            value = raw.get("value")
        else:
            value = raw
        return value is True or value == "true"
    except Exception:
        logger.exception("[auto_start] get 실패 — False 반환 (호출자 .env 폴백)")
        return False


async def set_auto_start(enabled: bool) -> None:
    """자동 매매 시작 여부 저장 (사이클 M5 — routes/strategies.py 전환 대상).

    JSONB `{"value": bool}` — `get_auto_start` 의 `raw.get("value")` 파싱 계약과
    정합 (왕복 불변식 = split-brain 해소 핵심). `set_auto_regime_adjust` 패턴 답습.
    """
    await _upsert_value(_AUTO_START_KEY, {"value": bool(enabled)})


async def get_task_last_success(task_label: str) -> Optional[str]:
    """task_last_success_<label> 키 ISO 문자열 조회. 키 부재 / 실패 시 None graceful.

    사이클 189 execute_with_retry 수혜 (_get_string_or_none 경유 = retry 자동 상속).
    """
    return await _get_string_or_none(f"task_last_success_{task_label}")


async def set_task_last_success(task_label: str, iso_ts: str) -> None:
    """마지막 성공 시각 upsert. 실패 시 예외 전파 없이 graceful.

    쓰기 = _with_retry 미경유 (_set_string 패턴 직답습, 사이클 187/189 정책 영속).
    JSONB 표준 {"value": iso} 형태.
    """
    await _set_string(f"task_last_success_{task_label}", iso_ts)
