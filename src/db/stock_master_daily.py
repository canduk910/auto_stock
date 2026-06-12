"""사이클 122 (2026-06-12) — stock_master_daily CRUD + 활용 헬퍼.

KIS FHKST03010100 (`inquire_daily_itemchartprice`) 응답 영속화 +
donchian (20일 신고가) / VCP (베이스 + Pullback) / VB (ATR) 전략 활용 함수.

사용자 결정:
- Q1=A 매일 16:00 KST 일괄 적재
- Q2=C T-100일 (KIS 1회 호출 한도)
- Q3=B 점진 적재 (사이클 122 백필 + 사이클 123+ 증분)
- Q4=B DB 적재만 (전략 전환은 사이클 123+ 별개)

영속 의무:
- 사이클 30 trade_history ON CONFLICT 답습 (PK 복합 키 패턴)
- 사이클 68 KST 영속 (`src/db/_kst.py` 헬퍼 의무)
- 사이클 81 G-AST1 raw JSONB 영속
- 사이클 88 G-REJECT graceful 단위 의무
- 매매 안전성 무영향 — scanner 단계 매수 진입 전 영역만

supabase 동기 SDK 호출은 모두 `asyncio.to_thread()` 위임.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from src.db._kst import KST, now_kst_iso
from src.db.supabase import supabase

logger = logging.getLogger(__name__)

TABLE_NAME = "stock_master_daily"

# 사이클 122 — KIS FHKST03010100 응답 키 (chk_inquire_daily_itemchartprice.py 정본)
_KIS_KEY_BAS_DD = "stck_bsop_date"
_KIS_KEY_OPEN = "stck_oprc"
_KIS_KEY_HIGH = "stck_hgpr"
_KIS_KEY_LOW = "stck_lwpr"
_KIS_KEY_CLOSE = "stck_clpr"
_KIS_KEY_VOLUME = "acml_vol"
_KIS_KEY_TRADE_VALUE = "acml_tr_pbmn"
_KIS_KEY_CHANGE_RATE = "prdy_ctrt"
_KIS_KEY_FLNG_CLS = "flng_cls_code"
_KIS_KEY_PRTT_RATE = "prtt_rate"

# Batch upsert 단위 — Supabase HTTP/2 stale connection 회피 (사이클 26 답습)
_BATCH_SIZE = 100


def _safe_int(value, default: int = 0) -> int:
    """문자열/숫자 → int 변환. 빈 값/예외 시 default 반환 (graceful)."""
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def _safe_float(value, default: float = 0.0) -> float:
    """문자열/숫자 → float 변환. 빈 값/예외 시 default 반환 (graceful)."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _parse_bas_dd(value: str | date) -> Optional[date]:
    """YYYYMMDD / YYYY-MM-DD 문자열 또는 date → date. 파싱 실패 시 None.

    영역:
    - KIS FHKST03010100 응답 = YYYYMMDD (사이클 14)
    - Supabase 응답 = YYYY-MM-DD ISO (사이클 122 max_bas_dd)
    - Python date → 그대로 반환
    """
    if isinstance(value, date):
        return value
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    try:
        # KIS stck_bsop_date 형식 = YYYYMMDD
        if len(s) == 8 and s.isdigit():
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        # Supabase ISO 형식 = YYYY-MM-DD (10자리)
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return date(int(s[:4]), int(s[5:7]), int(s[8:10]))
        # ISO timestamp = YYYY-MM-DDT... (앞 10자리만)
        if len(s) > 10 and s[4] == "-" and s[7] == "-":
            return date(int(s[:4]), int(s[5:7]), int(s[8:10]))
    except (ValueError, TypeError):
        return None
    return None


def _candle_to_row(ticker: str, candle: dict) -> Optional[dict]:
    """KIS FHKST03010100 output2 row → DB row dict.

    graceful: bas_dd 파싱 실패 시 None 반환 (호출자가 skip).
    사이클 81 G-AST1 raw JSONB 영속 — 전체 candle 원본 보존.
    """
    bas_dd = _parse_bas_dd(candle.get(_KIS_KEY_BAS_DD, ""))
    if bas_dd is None:
        return None

    return {
        "ticker": ticker,
        "bas_dd": bas_dd.isoformat(),
        "open_price": _safe_int(candle.get(_KIS_KEY_OPEN)),
        "high_price": _safe_int(candle.get(_KIS_KEY_HIGH)),
        "low_price": _safe_int(candle.get(_KIS_KEY_LOW)),
        "close_price": _safe_int(candle.get(_KIS_KEY_CLOSE)),
        "volume": _safe_int(candle.get(_KIS_KEY_VOLUME)),
        "trade_value": _safe_int(candle.get(_KIS_KEY_TRADE_VALUE)),
        "change_rate": _safe_float(candle.get(_KIS_KEY_CHANGE_RATE)),
        "flng_cls_code": str(candle.get(_KIS_KEY_FLNG_CLS) or ""),
        "prtt_rate": _safe_float(candle.get(_KIS_KEY_PRTT_RATE)),
        "raw": dict(candle),
        "updated_at": now_kst_iso(),
    }


async def upsert_daily(ticker: str, bas_dd: date, ohlcv: dict) -> None:
    """단건 upsert — ON CONFLICT (ticker, bas_dd) UPDATE.

    Args:
        ticker: KRX 6자리 단축코드.
        bas_dd: 영업일 기준일.
        ohlcv: KIS output2 row dict (또는 호출자 자체 dict).

    사이클 30 ON CONFLICT 답습 + 사이클 68 KST 영속.
    """
    candle = dict(ohlcv)
    # 호출자가 bas_dd 를 ohlcv 에 없이 별도 전달한 경우 보강
    candle.setdefault(_KIS_KEY_BAS_DD, bas_dd.strftime("%Y%m%d"))
    row = _candle_to_row(ticker, candle)
    if row is None:
        logger.warning(
            "[stock_master_daily] upsert skip — bas_dd 파싱 실패 ticker=%s bas_dd=%s",
            ticker, bas_dd,
        )
        return

    await asyncio.to_thread(
        lambda: supabase.table(TABLE_NAME)
        .upsert(row, on_conflict="ticker,bas_dd")
        .execute()
    )
    logger.debug(
        "[stock_master_daily] upsert ticker=%s bas_dd=%s close=%d",
        ticker, bas_dd, row["close_price"],
    )


async def upsert_batch(ticker: str, candles: list[dict]) -> int:
    """T-100일 batch upsert — 100건 단위 분할 + 사이클 88 G-REJECT graceful.

    Args:
        ticker: KRX 6자리 단축코드.
        candles: KIS output2 list (최신순 또는 임의 순서).

    Returns:
        upsert 성공 건수 (graceful skip 행 제외).

    영속 의무:
    - 사이클 26 Supabase HTTP/2 stale connection 회피 (batch 100건)
    - 사이클 88 G-REJECT graceful (개별 batch 실패 시 다음 batch 진행)
    """
    if not candles:
        return 0

    # KIS output2 → DB rows 변환 + bas_dd 파싱 실패 graceful skip
    rows: list[dict] = []
    skipped = 0
    for candle in candles:
        row = _candle_to_row(ticker, candle)
        if row is None:
            skipped += 1
            continue
        rows.append(row)

    if skipped > 0:
        logger.debug(
            "[stock_master_daily] upsert_batch ticker=%s skipped=%d (bas_dd 파싱 실패)",
            ticker, skipped,
        )

    if not rows:
        return 0

    total_upserted = 0
    # 100건 단위 batch (사이클 26 답습)
    for i in range(0, len(rows), _BATCH_SIZE):
        chunk = rows[i:i + _BATCH_SIZE]
        try:
            await asyncio.to_thread(
                lambda c=chunk: supabase.table(TABLE_NAME)
                .upsert(c, on_conflict="ticker,bas_dd")
                .execute()
            )
            total_upserted += len(chunk)
        except Exception:
            # 사이클 88 G-REJECT graceful — 개별 batch 실패 시 다음 batch 진행
            logger.exception(
                "[stock_master_daily] upsert_batch ticker=%s chunk_start=%d 실패 graceful",
                ticker, i,
            )

    return total_upserted


async def get_recent_daily(ticker: str, days: int = 20) -> list[dict]:
    """최근 N영업일 일봉 조회 — bas_dd DESC.

    Args:
        ticker: KRX 6자리 단축코드.
        days: 조회 일수 (1~100, KIS 호출 한도와 정합).

    Returns:
        list[dict] — raw row 그대로. 미존재 시 빈 list (graceful).
        [{"ticker", "bas_dd", "open_price", "high_price", "low_price",
          "close_price", "volume", "trade_value", "change_rate", "raw"}, ...]
    """
    # KIS 호출 한도 100일과 정합 + 최소 1일 가드
    clamped = max(1, min(days, 100))

    try:
        result = await asyncio.to_thread(
            lambda: supabase.table(TABLE_NAME)
            .select("*")
            .eq("ticker", ticker)
            .order("bas_dd", desc=True)
            .limit(clamped)
            .execute()
        )
        return result.data or []
    except Exception:
        # 사이클 88 G-REJECT graceful — DB 실패 시 빈 list 반환 (호출자 KIS fallback)
        logger.exception(
            "[stock_master_daily] get_recent_daily 실패 graceful ticker=%s",
            ticker,
        )
        return []


async def get_donchian_high(ticker: str, days: int = 20) -> Optional[int]:
    """donchian N일 신고가 — MAX(close_price) 또는 MAX(high_price) over last N rows.

    donchian 표준 = high_price (장중 최고가) 기준 N일 신고가.

    Args:
        ticker: KRX 6자리 단축코드.
        days: 신고가 기간 (donchian 기본 20일).

    Returns:
        int — N일 신고가. 데이터 부재 시 None (graceful, 호출자 KIS fallback).
    """
    rows = await get_recent_daily(ticker, days)
    if not rows:
        return None

    highs = [_safe_int(r.get("high_price")) for r in rows]
    highs = [h for h in highs if h > 0]
    if not highs:
        return None

    return max(highs)


async def get_atr(ticker: str, days: int = 14) -> Optional[float]:
    """ATR (Average True Range) — Wilder 공식 영역.

    True Range = max(high - low, |high - prev_close|, |low - prev_close|)
    ATR = mean(True Range) over last N days (simple mean approximation,
    Wilder smoothing 은 호출자 책임 — 본 헬퍼는 baseline 영역).

    Args:
        ticker: KRX 6자리 단축코드.
        days: ATR 기간 (VB 표준 14일).

    Returns:
        float — ATR 값. 데이터 부재 시 None (graceful).
    """
    # ATR 계산은 prev_close 가 필요하므로 days+1 일치 조회
    rows = await get_recent_daily(ticker, days + 1)
    if len(rows) < 2:
        return None

    # rows 는 DESC 정렬 — chronological 순서로 뒤집기
    rows_asc = list(reversed(rows))
    tr_values: list[float] = []

    for i in range(1, len(rows_asc)):
        prev = rows_asc[i - 1]
        curr = rows_asc[i]
        high = _safe_float(curr.get("high_price"))
        low = _safe_float(curr.get("low_price"))
        prev_close = _safe_float(prev.get("close_price"))

        if high <= 0 or low <= 0 or prev_close <= 0:
            continue

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        tr_values.append(tr)

    if not tr_values:
        return None

    # 최근 days 개만 평균
    recent_tr = tr_values[-days:]
    return sum(recent_tr) / len(recent_tr)


async def count_all() -> int:
    """전체 행 카운트 (UI 진단 + 운영 모니터링)."""
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table(TABLE_NAME)
            .select("ticker", count="exact")
            .limit(1)
            .execute()
        )
        if hasattr(result, "count") and result.count is not None:
            return int(result.count)
        return len(result.data or [])
    except Exception:
        logger.exception("[stock_master_daily] count_all 실패 graceful")
        return 0


async def count_by_ticker(ticker: str) -> int:
    """단일 ticker 행 카운트 (점진 적재 진단)."""
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table(TABLE_NAME)
            .select("bas_dd", count="exact")
            .eq("ticker", ticker)
            .limit(1)
            .execute()
        )
        if hasattr(result, "count") and result.count is not None:
            return int(result.count)
        return len(result.data or [])
    except Exception:
        logger.exception(
            "[stock_master_daily] count_by_ticker 실패 graceful ticker=%s",
            ticker,
        )
        return 0


async def max_bas_dd(ticker: str) -> Optional[date]:
    """ticker 의 최신 bas_dd — 점진 적재 시 신규 행 영역 결정.

    Returns:
        date — 최신 bas_dd. 미존재 시 None (백필 의무 신호).
    """
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table(TABLE_NAME)
            .select("bas_dd")
            .eq("ticker", ticker)
            .order("bas_dd", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        return _parse_bas_dd(rows[0].get("bas_dd"))
    except Exception:
        logger.exception(
            "[stock_master_daily] max_bas_dd 실패 graceful ticker=%s",
            ticker,
        )
        return None


async def get_recent_daily_with_fallback(
    ticker: str, days: int = 100, *, min_required: int | None = None
) -> list[dict]:
    """DB 조회 우선 + 미존재/부족 시 KIS 호출 fallback (사이클 122 A5 영속).

    domain-expert 자문 A5 영속 의무 — 적재 실패 시 KIS 호출 fallback 으로
    5 전략 prepare 영역 무중단 보장. 사이클 81 G-AST1 graceful 답습.

    Args:
        ticker: KRX 6자리 단축코드.
        days: 조회 일수.
        min_required: 최소 행 수 (이하 시 KIS fallback). 기본 = max(days // 2, 10).

    Returns:
        list[dict] — DB raw row 또는 KIS fetch_daily_candles 응답.
        호출자가 키 차이 (`open_price` vs `stck_oprc`) 흡수 의무.
    """
    if min_required is None:
        min_required = max(days // 2, 10)

    db_rows = await get_recent_daily(ticker, days)
    if len(db_rows) >= min_required:
        return db_rows

    # graceful fallback — KIS 호출 (기존 5분 TTL 캐시 영역 활용)
    try:
        from src.api.condition import fetch_daily_candles
        kis_rows = await fetch_daily_candles(ticker, days=days)
        logger.debug(
            "[stock_master_daily] fallback to KIS ticker=%s db_count=%d kis_count=%d",
            ticker, len(db_rows), len(kis_rows),
        )
        return kis_rows
    except Exception:
        logger.exception(
            "[stock_master_daily] KIS fallback 실패 graceful ticker=%s",
            ticker,
        )
        return db_rows  # 부족하더라도 DB 결과 반환 (호출자 graceful 통과)
