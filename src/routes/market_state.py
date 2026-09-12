"""장운영상태 라우트 — `GET /api/market-state` (사이클 282).

**표와 커서를 한 응답에 담는다.** 둘이 갈라지면 화면이 "정규장" 이라고 말하면서
정규장 행이 없는 표를 그린다. 그래서 이 라우트는 현재시각을 **정확히 한 번** 읽고
(`as_of`), 그 하나를 두 시장의 커서 판정과 표 날짜 해석에 **같이** 넘긴다.
자정을 넘기는 순간 표와 커서가 다른 날짜를 보는 일이 구조적으로 생길 수 없다.

책임 분리 — 시각·표 판정은 순수 leaf(`src/engine/market_state.py`)가 하고,
외부 조회(휴장일)는 **여기서만** 한다. leaf 는 I/O 를 하지 않는다.

휴장일은 `condition.is_trading_day` 의 **3상태**(True/False/None)를 그대로 싣는다.
기존 `is_market_open()` 의 fail-open **True** 를 쓰지 않는 이유 = 그 함수는 매매
경로의 계약이고, 화면은 "모른다" 를 "개장" 으로 보여주면 안 되기 때문이다.
조회 실패·타임아웃·행 없음은 전부 `is_trading_day=null` +
`trading_day_source="unknown"` 이며 응답 자체는 **200** 이다(표는 코드 상수라 살아 있다).

상태 코드 —
    200  정상 / 휴장일 조회 실패(`is_trading_day=null`)
    422  `on_date` 형식 오류 · 허용 범위(±365일) 밖
    404  **다른 날짜** 미리보기인데 그 날짜에 유효한 행이 0
    500  **오늘** 표가 비었거나 leaf 가 예외를 냈다
표는 코드 상수라 "오늘 행 0" 은 사용자 입력 문제가 아니라 **데이터 결함**이다.
빈 표를 200 빈 화면으로 흡수하지 않는다 — cycle266 의 `except Exception: rows=[]`
가 진짜 장애를 404 로 3개월 은폐한 그 실패를 되풀이하지 않기 위해서다.
"""

from __future__ import annotations

import asyncio
import logging
import time as _time
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from src.api import condition as condition_api
from src.engine.market_state import (
    BOARD_VS_MARKET_NOTE,
    CONFIDENCE_LEVELS,
    DIVISION_CONFIDENCE,
    EXCHANGE_ORDER,
    FINDINGS,
    MARKET_ORDER,
    ORDER_DIVISIONS,
    PHASE_LABELS_KO,
    PHASE_TONES,
    RELS,
    SUPPORT_LEVELS,
    TABLE_VERSION,
    TONES,
    UNCONFIRMED_NOTE,
    MarketPhase,
    get_market_state,
    get_market_table,
    support_level,
)
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market-state", tags=["market-state"])

_KST = timezone(timedelta(hours=9))

#: `on_date` 미리보기 허용 범위(오늘 기준 ±일). 밖은 422.
_PREVIEW_RANGE_DAYS = 365

#: 휴장일 캐시 — `date -> (만료 monotonic | None, 값)`.
#: 성공(True/False)은 **만료 없이** 캐시한다(어떤 날짜가 거래일인지는 바뀌지 않는다).
_TRADING_DAY_CACHE: dict[date, tuple[float | None, "bool | None"]] = {}
#: 실패(None)는 짧게만 캐시한다. 영구 캐시하면 KIS 가 5분 만에 살아나도 화면은 하루 종일
#: "확인 불가" 이고, 캐시가 아예 없으면 KIS 장애 중 30초 폴링이 매번 타임아웃을 기다린다.
_TRADING_DAY_NEG_TTL = 60.0
_TRADING_DAY_MAX = 64
#: 화면 폴링이 KIS 지연에 물리지 않게 하는 상한.
_TRADING_DAY_TIMEOUT = 5.0

_SOURCE_KIS = "kis"
_SOURCE_CACHE = "cache"
_SOURCE_UNKNOWN = "unknown"

_REL_CURRENT = "current"
_REL_CONCURRENT = "concurrent"
_REL_PAST = "past"
_REL_UPCOMING = "upcoming"
_REL_UNKNOWN = "unknown"

_CURSOR_DISABLED_PREVIEW = "preview_other_date"
_EMPTY_TODAY = "market_table_empty"
_EMPTY_PREVIEW = "no_effective_rows"


def invalidate_market_state_cache() -> None:
    """휴장일 캐시를 비운다(리포 관례 `invalidate_*`). 표 자체는 코드 상수라 캐시가 없다."""
    _TRADING_DAY_CACHE.clear()


def _trim_cache() -> None:
    while len(_TRADING_DAY_CACHE) > _TRADING_DAY_MAX:
        oldest = next(iter(_TRADING_DAY_CACHE))
        _TRADING_DAY_CACHE.pop(oldest, None)


async def _resolve_trading_day(target: date) -> tuple["bool | None", str]:
    """(값, 출처) — 실패는 **임의로 True/False 로 메우지 않고** `None` 이다."""
    cached = _TRADING_DAY_CACHE.get(target)
    if cached is not None:
        expires_at, value = cached
        if expires_at is None or _time.monotonic() < expires_at:
            return value, (_SOURCE_UNKNOWN if value is None else _SOURCE_CACHE)
        _TRADING_DAY_CACHE.pop(target, None)

    value = None
    try:
        value = await asyncio.wait_for(
            condition_api.is_trading_day(target), timeout=_TRADING_DAY_TIMEOUT
        )
    except Exception:
        logger.warning("[market_state] 휴장일 조회 실패 %s — 확인 불가로 응답한다", target)
        value = None

    if value is None:
        _TRADING_DAY_CACHE[target] = (_time.monotonic() + _TRADING_DAY_NEG_TTL, None)
    else:
        value = bool(value)
        _TRADING_DAY_CACHE[target] = (None, value)
    _trim_cache()
    return value, (_SOURCE_UNKNOWN if value is None else _SOURCE_KIS)


def _iso_date(value: "date | None") -> "str | None":
    return value.isoformat() if value is not None else None


def _phase_value(value) -> "str | None":
    if value is None:
        return None
    return value.value if isinstance(value, MarketPhase) else str(value)


def _state_payload(state) -> dict:
    window = None
    if state.window is not None:
        window = {"start": state.window[0].isoformat(), "end": state.window[1].isoformat()}
    return {
        "market": state.market,
        "market_label_ko": state.market_label_ko,
        "row_id": state.row_id,
        "phase": _phase_value(state.phase),
        "name_ko": state.name_ko,
        "tone": state.tone,
        "window": window,
        "match_kind": state.match_kind,
        "match_ko": state.match_ko,
        "is_open": state.is_open,
        "can_order": state.can_order,
        "market_order_ok": state.market_order_ok,
        "order_divisions": list(state.order_divisions),
        "order_divisions_by_row": [
            {"row_id": row_id, "codes": list(codes)}
            for row_id, codes in state.order_divisions_by_row
        ],
        "concurrent_row_ids": list(state.concurrent_row_ids),
        "quote_channel": state.quote_channel,
        "quote_channel_evidence": state.quote_channel_evidence,
        "decided_by": state.decided_by,
        "code_seen": state.code_seen,
        "confidence": state.confidence,
        "confidence_notes": list(state.confidence_notes),
        "seconds_to_next": state.seconds_to_next,
        "next_boundary": (
            state.next_boundary.isoformat() if state.next_boundary is not None else None
        ),
        "next_row_id": state.next_row_id,
        "next_phase": _phase_value(state.next_phase),
    }


def _row_payload(row, rel: str) -> dict:
    return {
        "row_id": row.row_id,
        "market": row.market,
        "start": row.start.isoformat(),
        "end": row.end.isoformat(),
        "phase": _phase_value(row.phase),
        "name_ko": row.name_ko,
        "tone": row.tone,
        "match_kind": row.match_kind,
        "match_ko": row.match_ko,
        "order_divisions": list(row.order_divisions),
        "order_divisions_pending": list(row.order_divisions_pending),
        "order_divisions_expired": list(row.order_divisions_expired),
        "can_order": row.can_order,
        "market_order_ok": row.market_order_ok,
        "quote_channel": row.quote_channel,
        "quote_channel_evidence": row.quote_channel_evidence,
        "overlap_ok": row.overlap_ok,
        "priority": row.priority,
        "effective_from": _iso_date(row.effective_from),
        "effective_to": _iso_date(row.effective_to),
        "confidence": row.confidence,
        "note": row.note,
        "rel": rel,
    }


def _division_payload(spec) -> dict:
    return {
        "code": spec.code,
        "name_ko": spec.name_ko,
        "group_ko": spec.group_ko,
        "exchange_support": {
            exchange: support_level(spec, exchange) for exchange in EXCHANGE_ORDER
        },
        "effective_from": _iso_date(spec.effective_from),
        "effective_to": _iso_date(spec.effective_to),
        "confidence": spec.confidence,
        "note": spec.note,
    }


def _rel_for(row, markets: "dict | None", moment) -> str:
    """지난/현재/동시/다음 판정은 **서버**가 한다(프론트는 이 값으로 칠하기만 한다).

    브라우저 로컬 시각으로 다시 계산하면 KST 강제 규약이 그 자리에서 깨지고,
    표와 커서가 서로 다른 순간을 가리킬 수 있다.
    """
    if markets is None:
        return _REL_UNKNOWN
    state = markets.get(row.market)
    if state is None:
        return _REL_UNKNOWN
    if row.row_id == state.row_id:
        return _REL_CURRENT
    if row.row_id in state.concurrent_row_ids:
        return _REL_CONCURRENT
    if row.end <= moment:
        return _REL_PAST
    if row.start > moment:
        return _REL_UPCOMING
    return _REL_UNKNOWN


@router.get("", response_model=ApiResponse)
async def read_market_state(on_date: "date | None" = None):
    """거래소 장 운영 상태 — 표 전체 + 두 시장의 커서 + 주문유형 카탈로그."""
    # 현재시각은 **여기 한 번**만 읽는다. 커서 2개와 표가 이 하나를 공유한다.
    as_of = datetime.now(_KST)
    today = as_of.date()
    target = on_date if on_date is not None else today

    if abs((target - today).days) > _PREVIEW_RANGE_DAYS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"on_date 허용 범위를 벗어났다 — 오늘 기준 ±{_PREVIEW_RANGE_DAYS}일 안이어야 한다"
                f" (요청 {target.isoformat()})"
            ),
        )

    preview = target != today
    table = get_market_table(target)
    if not table:
        # 표는 코드 상수다. 오늘 행이 0 이면 입력 문제가 아니라 데이터 결함이다.
        if preview:
            raise HTTPException(status_code=404, detail=_EMPTY_PREVIEW)
        logger.error("[market_state] 오늘 유효 행 0 — 표 데이터 결함")
        raise HTTPException(status_code=500, detail=_EMPTY_TODAY)

    markets = None
    if not preview:
        markets = {name: get_market_state(as_of, market=name) for name in MARKET_ORDER}

    moment = as_of.time()
    trading_day, trading_day_source = await _resolve_trading_day(target)

    data = {
        "table_version": TABLE_VERSION,
        "as_of_kst": as_of.isoformat(),
        "on_date": target.isoformat(),
        "preview": preview,
        "cursor_disabled_reason": _CURSOR_DISABLED_PREVIEW if preview else None,
        "is_trading_day": trading_day,
        "trading_day_source": trading_day_source,
        "market_order": list(MARKET_ORDER),
        "exchange_order": list(EXCHANGE_ORDER),
        "markets": (
            {name: _state_payload(state) for name, state in markets.items()}
            if markets is not None
            else None
        ),
        "table": [_row_payload(row, _rel_for(row, markets, moment)) for row in table],
        "order_divisions": [_division_payload(spec) for spec in ORDER_DIVISIONS],
        "phases": [
            {
                "id": phase.value,
                "label_ko": PHASE_LABELS_KO[phase],
                "tone": PHASE_TONES[phase],
            }
            for phase in MarketPhase
        ],
        "vocab": {
            "tones": list(TONES),
            "rels": list(RELS),
            "support_levels": list(SUPPORT_LEVELS),
            "confidences": list(CONFIDENCE_LEVELS),
            "division_confidences": list(DIVISION_CONFIDENCE),
        },
        "findings": list(FINDINGS),
        "board_note": BOARD_VS_MARKET_NOTE,
        "unconfirmed_note": UNCONFIRMED_NOTE,
    }
    return ApiResponse(success=True, data=data)
