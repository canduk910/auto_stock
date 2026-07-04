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
from src.db.supabase import supabase, execute_with_retry

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
        result = await execute_with_retry(
            lambda: supabase.table(TABLE_NAME)
            .select("*")
            .eq("ticker", ticker)
            .order("bas_dd", desc=True)
            .limit(clamped)
            .execute(),
            op="get_recent_daily",
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
        result = await execute_with_retry(
            lambda: supabase.table(TABLE_NAME)
            .select("ticker", count="exact")
            .limit(1)
            .execute(),
            op="count_all",
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
        result = await execute_with_retry(
            lambda: supabase.table(TABLE_NAME)
            .select("bas_dd", count="exact")
            .eq("ticker", ticker)
            .limit(1)
            .execute(),
            op="count_by_ticker",
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


async def max_bas_dd(ticker: str | None = None) -> Optional[date]:
    """최신 bas_dd 조회 — ticker 지정 시 해당 종목, None 시 전체 MAX(bas_dd).

    Args:
        ticker: 종목코드. None 이면 전체 stock_master_daily 의 MAX(bas_dd) 반환.

    Returns:
        date — 최신 bas_dd. 미존재 시 None.

    사이클 124 확장: ticker=None 지원 (전체 마지막 적재일 조회, 사이클 85 stats 카드용).
    """
    try:
        if ticker is None:
            build = lambda: supabase.table(TABLE_NAME).select("bas_dd").order("bas_dd", desc=True).limit(1).execute()
        else:
            build = lambda: supabase.table(TABLE_NAME).select("bas_dd").eq("ticker", ticker).order("bas_dd", desc=True).limit(1).execute()
        result = await execute_with_retry(build, op="max_bas_dd")
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


# ---------------------------------------------------------------------------
# 사이클 173 (2026-06-22) — 락/신선도 게이트 (수정주가 divergence silent 결함 방어)
#
# 어댑터 (사이클 172) 에 2 게이트 추가:
#  - 락 게이트 (G-EQ-3, 최우선 HIGH): DB 윈도우 내 1 row 라도 락 발생
#    (flng_cls_code not in ("","00") OR prtt_rate 비-0) → KIS 강제 폴백.
#    근거: 수정주가는 조회 시점 의존값 → DB 박제 과거봉(락 전) vs KIS 재조정(락 후) 어긋남.
#    KIS 호출은 조회 시점 재조정이라 일관성 보장 → 락 종목만 KIS 폴백이 유일한 silent 방어.
#  - 신선도 게이트 (G-EQ-4): DB 최신봉(max_bas_dd)이 today - DAILY_STALENESS_DAYS(=4)
#    보다 오래 → KIS 폴백 (D-1 미적재 race 차단).
#
# ★ team-leader 운영 DB 실측 확정 (자문 보정):
#  - flng_cls_code 기본 = "" / "00" (실측 99.6% "00"). 비기본 (01/02/03/05) = 락.
#  - prtt_rate 기본 = 0 / "" / None (실측 99.7% "0.0000"). 자문의 != 1.0 은 틀림 (전 종목 폴백).
#    비-0 = 분할/병합/배당락 조정.
#  - 검사 = DB row top-level flng_cls_code / prtt_rate 컬럼 (raw 와 별개, migration 033).
#    KIS 추가 호출 0건 탐지.
# ---------------------------------------------------------------------------

# 신선도 게이트 임계 — DB 최신봉이 today 보다 이 일수 초과로 오래되면 KIS 폴백.
# 주말 2 + 공휴일 마진 1 + 1 = 4 보수적 (휴장일/연휴 거짓 폴백 차단).
DAILY_STALENESS_DAYS = 4


def _row_has_lock(row: dict) -> bool:
    """단일 일봉 row 가 락(액면분할/병합/배당락 등) 표시인지.

    flng_cls_code not in ("", "00") OR abs(float(prtt_rate)) > 0.
    기본값 ("" / "00" / 0 / None) 은 정상 (락 아님).
    """
    flng = row.get("flng_cls_code")
    if flng is not None and str(flng).strip() not in ("", "00"):
        return True
    prtt = row.get("prtt_rate")
    if prtt is not None and str(prtt).strip() not in ("", "0", "0.0", "0.00", "0.0000"):
        try:
            if abs(float(prtt)) > 1e-9:
                return True
        except (TypeError, ValueError):
            # 파싱 불가 비기본 값 → 보수적으로 락 의심
            return True
    return False


def _extract_raw(db_rows: list[dict]) -> list[dict]:
    """DB row 들에서 raw JSONB (KIS 원본 키) 추출 — 부재 시 row 자체 graceful."""
    normalized: list[dict] = []
    for r in db_rows:
        raw = r.get("raw")
        normalized.append(raw if isinstance(raw, dict) and raw else r)
    return normalized


async def _kis_fallback(ticker: str, days: int, db_rows: list[dict], *, reason: str) -> list[dict]:
    """KIS fetch_daily_candles 폴백 (락/신선도/부족 공통). 실패 시 DB raw graceful."""
    try:
        from src.api.condition import fetch_daily_candles
        kis_rows = await fetch_daily_candles(ticker, days=days)
        logger.debug(
            "[prepare_db_fallback] ticker=%s reason=%s db=%d kis=%d",
            ticker, reason, len(db_rows), len(kis_rows),
        )
        return kis_rows
    except Exception:
        logger.exception(
            "[stock_master_daily] get_recent_daily_normalized KIS 폴백 실패 graceful "
            "ticker=%s reason=%s",
            ticker, reason,
        )
        return _extract_raw(db_rows)


# ---------------------------------------------------------------------------
# 사이클 172 (2026-06-22) — DB일봉 어댑터 (raw JSONB = KIS 원본 키 보존)
# 사이클 173 (2026-06-22) — 락/신선도 게이트 추가 (위 헬퍼)
#
# 사이클 173 prepare DB일봉 전환의 공통 어댑터. DB row 의 raw JSONB (KIS 원본 키
# stck_clpr / stck_oprc 등 보존) 를 그대로 반환 → 173 prepare 의 c.get("stck_clpr")
# 무변경 사용. 락/신선도/부족 시 KIS fetch_daily_candles 폴백.
# ---------------------------------------------------------------------------
async def get_recent_daily_normalized(
    ticker: str, days: int, *, min_required: int | None = None
) -> list[dict]:
    """DB raw JSONB (KIS 원본 키 보존) 반환 + 락/신선도/부족 시 KIS 폴백.

    DB 충분 + 락 없음 + 신선 시 각 row 의 raw JSONB (stck_clpr 등 KIS 원본 키) 를
    그대로 반환 — 173 prepare 의 `c.get("stck_clpr")` 무변경 사용 보장.

    폴백 우선순위 (DB 사용 전 검사):
      1. 락 게이트 (최우선): 윈도우 내 1 row 라도 락 → KIS 폴백.
      2. 신선도 게이트: max_bas_dd 가 today-DAILY_STALENESS_DAYS 초과 오래 → KIS 폴백.
      3. min_required 게이트: len < min_required → KIS 폴백.

    Args:
        ticker: KRX 6자리 단축코드.
        days: 조회 일수.
        min_required: 최소 행 수 (이하 시 KIS 폴백). 기본 None = max(days // 2, 10).

    Returns:
        list[dict] — DB raw JSONB 또는 KIS fetch_daily_candles 응답 (KIS 원본 키).
        raw 키 부재 row 는 row 자체 반환 (graceful).
    """
    if min_required is None:
        min_required = max(days // 2, 10)

    db_rows = await get_recent_daily(ticker, days)

    # 1. 락 게이트 (최우선 HIGH) — 윈도우 내 1 row 라도 락이면 KIS 강제 폴백.
    #    검사는 DB top-level flng_cls_code / prtt_rate 컬럼 (KIS 추가 호출 0건).
    try:
        if db_rows and any(_row_has_lock(r) for r in db_rows):
            return await _kis_fallback(ticker, days, db_rows, reason="lock")
    except Exception:
        # 락 검사 자체 예외 → 보수적으로 KIS 폴백 시도 (안전 우선)
        logger.exception(
            "[stock_master_daily] 락 검사 예외 graceful → KIS 폴백 시도 ticker=%s", ticker,
        )
        return await _kis_fallback(ticker, days, db_rows, reason="lock")

    # 2. 신선도 게이트 — DB 최신봉이 today-staleness 보다 오래되면 KIS 폴백.
    #    max_bas_dd None (판정 불가) 은 graceful 통과 (db_rows 충분이면 사용).
    if db_rows:
        try:
            latest = await max_bas_dd(ticker)
            if latest is not None:
                from datetime import datetime as _dt
                today = _dt.now(KST).date()
                if (today - latest).days > DAILY_STALENESS_DAYS:
                    return await _kis_fallback(ticker, days, db_rows, reason="stale")
        except Exception:
            logger.exception(
                "[stock_master_daily] 신선도 검사 예외 graceful ticker=%s", ticker,
            )

    # 3. min_required 게이트 — DB 부족 시 KIS 폴백.
    if len(db_rows) >= min_required:
        return _extract_raw(db_rows)

    reason = "miss" if not db_rows else "insufficient"
    return await _kis_fallback(ticker, days, db_rows, reason=reason)


# ---------------------------------------------------------------------------
# 사이클 150 — T-150일 retention (SUPABASE 용량초과 시정)
# 사이클 172 — 150 → 230 (VCP 220일 + 10일 마진, 상수만 변경)
# ---------------------------------------------------------------------------

import time as _time  # 사이클 150 — elapsed_ms 측정


# 사이클 172 (2026-06-22) — 150 → 230 (VCP 220일 + 10일 안전 마진).
# 사이클 173 prepare DB일봉 전환 시 VCP 220일 lookback DB 충족 보장.
# purge_old_rows 로직 불변 (상수만, "230일 지난 것만 삭제").
# 사이클 150 영역 (사이클 48 VCP EMA effective_long T-120일 + 30일 마진) → 사이클 172 확장.
DAILY_RETENTION_DAYS = 230

# 사이클 192 (2026-07-04) — 날짜 슬라이스 루프 런어웨이 가드.
# 잔여 backlog 는 다음 실행이 드레인 (일 1회 16:15 KST task).
PURGE_MAX_DATE_ITERATIONS = 500


async def purge_old_rows(
    cutoff_date: date,
    *,
    protected_tickers: set[str] | None = None,
) -> dict[str, int]:
    """T-230일 retention. cutoff_date 이전 row DELETE.

    사용자 결정 Q3=C — VCP T-120일 + 30일 안전 마진 영구 영속.

    사이클 192 (2026-07-04) — PostgREST returning=representation 응답 비대로
    매 실행 실패 (6/16 도입 이래 515건 누적, 47,924행 × raw JSONB 응답 시도).
    사이클 175 루프 배치 패턴 답습 + 복합 PK (ticker, bas_dd) 적응:
    날짜 슬라이스 루프로 재구성:
      (1) SELECT oldest bas_dd (lt cutoff, protected 제외) → 없으면 drained break
      (2) 그 날짜 전체 DELETE (returning="minimal" + count="exact", protected 제외)
      (3) deleted 누적 → PURGE_MAX_DATE_ITERATIONS cap (런어웨이 가드)
    핵심: SELECT/DELETE 양쪽 protected 제외 필수 (SELECT 누락 = never-drain 회귀).

    Args:
        cutoff_date: ``bas_dd < cutoff_date`` 인 row DELETE.
        protected_tickers: 보유/익일청산 ticker (사이클 32 R4 답습) — 절대 보호.
            None 이면 미적용 (전체 영역 cutoff).

    Returns:
        ``{"deleted": int, "protected_count": int, "elapsed_ms": int}``

    Side effects:
        - INFO 로그 1행 ``[stock_master_daily_purge] deleted=N protected=M elapsed_ms=K``

    영속 의무:
    - 사이클 32 R4 universe guard 보유/익일청산 절대 보호
    - 사이클 38 명문화 (scanner 매수 진입 전 영역 한정)
    - 사이클 81 G-AST1 raw 영역 보호 (raw 폐기 미진행)
    - 사이클 88 graceful (예외 시 부분 누적 deleted 반환)
    - G-187-A2 execute_with_retry 미경유 (쓰기 함수)
    """
    started = _time.perf_counter()
    cutoff_iso = cutoff_date.isoformat()
    protected_count = len(protected_tickers) if protected_tickers else 0
    deleted = 0

    try:
        for _ in range(PURGE_MAX_DATE_ITERATIONS):
            # (1) 가장 오래된 삭제 대상 날짜 1건 조회 — SELECT 쪽 protected 제외 필수.
            #     누락 시: protected 만 남은 날짜를 SELECT 가 계속 반환 → never-drain 회귀.
            def _select(cutoff=cutoff_iso, pt=protected_tickers):
                q = (
                    supabase.table(TABLE_NAME)
                    .select("bas_dd")
                    .lt("bas_dd", cutoff)
                )
                if pt:
                    q = q.not_.in_("ticker", list(pt))
                return q.order("bas_dd").limit(1).execute()

            sel_result = await asyncio.to_thread(_select)
            rows = (sel_result.data or []) if sel_result else []
            if not rows:
                break  # drained

            oldest = rows[0]["bas_dd"]

            # (2) 그 날짜 전체 DELETE — returning="minimal" (응답 비대 근본 차단).
            #     사이클 32 R4 영속 — 보유/익일청산 절대 보호 (DELETE 쪽도 동일 적용).
            def _delete(oldest_dd=oldest, pt=protected_tickers):
                chain = (
                    supabase.table(TABLE_NAME)
                    .delete(count="exact", returning="minimal")
                    .eq("bas_dd", oldest_dd)
                )
                if pt:
                    chain = chain.not_.in_("ticker", list(pt))
                return chain.execute()

            del_result = await asyncio.to_thread(_delete)
            deleted += int(getattr(del_result, "count", None) or 0)

    except Exception as exc:
        # 사이클 190 예외 타입 계측 + 부분 누적 deleted 반환 (graceful)
        logger.exception(
            "[stock_master_daily_purge] 루프 실패 graceful cutoff=%s protected=%d "
            "%s: %s",
            cutoff_iso, protected_count, type(exc).__name__, str(exc)[:150],
        )
        elapsed_ms = int((_time.perf_counter() - started) * 1000)
        return {"deleted": deleted, "protected_count": protected_count, "elapsed_ms": elapsed_ms}

    elapsed_ms = int((_time.perf_counter() - started) * 1000)

    logger.info(
        "[stock_master_daily_purge] deleted=%d protected=%d elapsed_ms=%d cutoff=%s",
        deleted, protected_count, elapsed_ms, cutoff_iso,
    )

    return {
        "deleted": deleted,
        "protected_count": protected_count,
        "elapsed_ms": elapsed_ms,
    }
