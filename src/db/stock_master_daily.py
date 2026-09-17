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

사이클 M2b (Supabase→RDS 이전, 매매 hot path): supabase-py → `src.db.pg`(asyncpg) 전환.
함수 시그니처·반환형·graceful 100% 보존 — 호출부(scanner/strategies) diff 0.

⚠️ `get_recent_daily_normalized` = prepare 일봉 소스 (락/신선도/부족 폴백, 사이클 172/173).
어댑터는 `get_recent_daily`/`max_bas_dd`/`fetch_daily_candles`(KIS, 미변경) 조합이라
pg 전환과 무관하게 계약 보존.

⚠️ `purge_old_rows` = 날짜 슬라이스 루프(사이클 192). SELECT/DELETE 양쪽 protected 제외
절대 보존(SELECT 누락 = never-drain 회귀, P-3 HIGH). `_with_retry` 미경유(G-187-A2).

read 헬퍼(`get_recent_daily`/`count_all`/`count_by_ticker`/`max_bas_dd`)는 `pg.fetch`/
`pg.fetchval`(내부 `_with_retry` 경유, 사이클 187 정책 계승), 쓰기(`upsert_daily`/
`upsert_batch`/`purge_old_rows`)는 `pg.execute`/`pg.executemany`(retry 미경유) 유지.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

import src.db.pg as pg
from src.db._kst import KST, now_kst_iso, to_date

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
    - DB 응답 = YYYY-MM-DD ISO (사이클 122 max_bas_dd)
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
        # ISO 형식 = YYYY-MM-DD (10자리)
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
        "bas_dd": bas_dd,
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
        "updated_at": datetime.fromisoformat(now_kst_iso()),
    }


_UPSERT_DAILY_SQL = """
    INSERT INTO stock_master_daily (
        ticker, bas_dd, open_price, high_price, low_price, close_price,
        volume, trade_value, change_rate, flng_cls_code, prtt_rate, raw, updated_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13)
    ON CONFLICT (ticker, bas_dd) DO UPDATE SET
        open_price = EXCLUDED.open_price,
        high_price = EXCLUDED.high_price,
        low_price = EXCLUDED.low_price,
        close_price = EXCLUDED.close_price,
        volume = EXCLUDED.volume,
        trade_value = EXCLUDED.trade_value,
        change_rate = EXCLUDED.change_rate,
        flng_cls_code = EXCLUDED.flng_cls_code,
        prtt_rate = EXCLUDED.prtt_rate,
        raw = EXCLUDED.raw,
        updated_at = EXCLUDED.updated_at
"""


def _row_to_args(row: dict) -> tuple:
    return (
        row["ticker"],
        row["bas_dd"],
        row["open_price"],
        row["high_price"],
        row["low_price"],
        row["close_price"],
        row["volume"],
        row["trade_value"],
        row["change_rate"],
        row["flng_cls_code"],
        row["prtt_rate"],
        row["raw"],
        row["updated_at"],
    )


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

    await pg.execute(_UPSERT_DAILY_SQL, *_row_to_args(row))
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
    - G-187-A2 — 쓰기 함수는 `_with_retry` 미경유 (멱등 보수 정책).
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
            await pg.executemany(_UPSERT_DAILY_SQL, [_row_to_args(r) for r in chunk])
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
        rows = await pg.fetch(
            "SELECT * FROM stock_master_daily WHERE ticker = $1 "
            "ORDER BY bas_dd DESC LIMIT $2",
            ticker, clamped,
        )
        return rows or []
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
        count = await pg.fetchval("SELECT count(*) FROM stock_master_daily")
        return int(count or 0)
    except Exception:
        logger.exception("[stock_master_daily] count_all 실패 graceful")
        return 0


async def count_by_ticker(ticker: str) -> int:
    """단일 ticker 행 카운트 (점진 적재 진단)."""
    try:
        count = await pg.fetchval(
            "SELECT count(*) FROM stock_master_daily WHERE ticker = $1", ticker,
        )
        return int(count or 0)
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
            result = await pg.fetchval("SELECT max(bas_dd) FROM stock_master_daily")
        else:
            result = await pg.fetchval(
                "SELECT max(bas_dd) FROM stock_master_daily WHERE ticker = $1", ticker,
            )
        if result is None:
            return None
        return _parse_bas_dd(result)
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


# ---------------------------------------------------------------------------
# 사이클 226 D-3 (2026-08-25) — `_extract_raw` 폴백 **가시화** cap (관측 전용).
#
# 이 함수는 donchian 전용이 아니다 — kojiro·VCP·BFB·VB/LTV 의 prepare 가 전부
# `get_recent_daily_normalized` 를 거쳐 여기로 온다. row 당 1행이면 100일 창 ×
# 전 전략 × 전 종목으로 로그가 폭주하므로 **호출당 1행 + 같은 날 같은 ticker 1회**
# 로 두 겹 cap 을 건다. 모듈 전역인 이유 = 이 함수가 인스턴스 없는 순수 헬퍼이고,
# 소비 전략이 여럿이라 전략별 cap 이면 같은 종목이 전략 수만큼 찍힌다.
# 날짜 키 자기리셋 — 어떤 일일 정산 훅에도 의존하지 않는다.
# ---------------------------------------------------------------------------
# ⚠️ `DailyEmitCap`(src/engine/) 을 쓰지 않는다 — `src/db/` 가 `src/engine/` 을
# 모듈 레벨로 import 하면 문서화된 의존 방향(`db/ ← engine/`)이 뒤집힌다.
# 필요한 기능은 "날짜 키 + 본 집합" 두 줄이라 여기서 직접 든다.
_RAW_MISSING_LOGGED: set[str] = set()
_RAW_MISSING_DAY: str = ""


def _trace_daily_raw_missing(ticker: Optional[str], missing: int, total: int) -> None:
    """`[daily_raw_missing]` — raw JSONB 부재 폴백의 **흔적** (사이클 226 D-3).

    ## 왜

    `_extract_raw` 의 폴백은 지금 **완전 무음**이다. 그래서 이 경로가 살아나도
    (마이그레이션 033 이전 잔존 row, 다른 경로로 들어온 row 등) 아무도 모른다.
    그런 row 는 KIS 원본 키가 아니라 DB 정규화 컬럼(`high_price`/`bas_dd`/…)을
    들고 있어 donchian `prepare` 의 `int(c.get("stck_hgpr", "0"))` 가 0 을 내고,
    그 0 이 곧 돌파선 0(사이클 226 D-1 이 막은 사고)의 상류다.

    ## 무엇을 싣나

    부재 row 수와 전체 row 수를 함께 싣는다 — 비율이 곧 열화 정도이고, "1/100"
    (마이그레이션 경계의 꼬리)과 "100/100"(적재 경로 자체 파손)은 대응이 다르다.
    ticker 는 인자로 받되 없으면 row 에서 best-effort 로 건진다 — 종목을 모르면
    "부재 4/22" 만 남아 어느 종목의 일봉이 썩었는지 알 수 없어 대응이 안 된다.

    ## 행위 변경 0

    폴백 자체는 그대로다(graceful 이 옳다). 흔적만 남긴다. 관측 실패는 흡수하되
    무흔적 흡수는 금지 — `[daily_raw_missing_failed]` 로 남긴다(도입 이전 무음과
    구별되어야 한다).
    """
    global _RAW_MISSING_DAY
    key = str(ticker or "__unknown__")
    try:
        today_key = datetime.now(KST).date().isoformat()
        if _RAW_MISSING_DAY != today_key:
            _RAW_MISSING_DAY = today_key
            _RAW_MISSING_LOGGED.clear()
        if key in _RAW_MISSING_LOGGED:
            return
        # ⚠️ L-3 — cap 등록은 로그 **뒤**다. 앞에 두면 `logger.info` 가 던졌을 때
        #    그 종목이 그날 내내 봉인돼 정상 관측까지 사라진다(관측기 자기실패가
        #    관측 대상을 지우는 것 = 이 사이클이 없애려던 무음의 재생산).
        logger.info(
            "[daily_raw_missing] ticker=%s missing_rows=%d total_rows=%d"
            " note='raw JSONB 부재 row 를 DB 정규화 컬럼 그대로 graceful 반환했다"
            " — 소비 전략 prepare 가 KIS 원본 키를 못 읽어 고가/종가 0 이 될 수 있다.'",
            key, int(missing), int(total),
        )
        _RAW_MISSING_LOGGED.add(key)
    except Exception:
        # 흡수하되 흔적은 남긴다. debug 단독은 `_DbLogHandler`(INFO 이상만 적재)를
        # 통과하지 못해 `system_logs` 에 도달하지 않으므로 WARNING 1행을 병행한다.
        try:
            logger.debug("[daily_raw_missing_failed] ticker=%s", key, exc_info=True)
        except Exception:
            pass
        try:
            fail_key = key + "|__observer_failed__"
            if fail_key not in _RAW_MISSING_LOGGED:
                _RAW_MISSING_LOGGED.add(fail_key)
                logger.warning(
                    "[daily_raw_missing_failed] ticker=%s"
                    " note='관측기 내부 예외로 이 관측이 침묵한다 — 반환값·행위와 무관,"
                    " 스택트레이스는 동일 마커 debug 로그 참조'",
                    key,
                )
        except Exception:
            pass


def _extract_raw(db_rows: list[dict], *, ticker: Optional[str] = None) -> list[dict]:
    """DB row 들에서 raw JSONB (KIS 원본 키) 추출 — 부재 시 row 자체 graceful.

    사이클 226 D-3 — 폴백이 실제로 탄 경우 `[daily_raw_missing]` 흔적 1행
    (호출당 1행 + 1회/ticker/일). **반환값과 행위는 불변**이다.
    `ticker` 는 키워드 전용 + 기본값 — 기존 위치인자 1개 호출부 호환을 깨지 않는다.
    """
    normalized: list[dict] = []
    missing = 0
    for r in db_rows:
        raw = r.get("raw")
        if isinstance(raw, dict) and raw:
            normalized.append(raw)
        else:
            normalized.append(r)
            missing += 1
    if missing:
        known = ticker
        if not known:
            for r in db_rows:
                cand = r.get("ticker")
                if cand:
                    known = str(cand)
                    break
        _trace_daily_raw_missing(known, missing, len(db_rows))
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
        return _extract_raw(db_rows, ticker=ticker)


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
        return _extract_raw(db_rows, ticker=ticker)

    reason = "miss" if not db_rows else "insufficient"
    return await _kis_fallback(ticker, days, db_rows, reason=reason)


# ---------------------------------------------------------------------------
# 일봉 retention — 오래된 행을 날짜 단위로 잘라낸다.
# ---------------------------------------------------------------------------

import time as _time  # 사이클 150 — elapsed_ms 측정


# 사이클 299 — 230 → 390 (retention 390달력일 ≈ 261영업일 보유,
# 환산 앵커 = 사이클196 실측 230cal ⇄ 154영업일).
# VCP backfill target 225 (사이클 299) · prepare 실사용은 여전히 100일.
# 🔴 target 과 이 값은 함께 움직인다 — target > 보유 영업일이면 매일 밤
# 전량 재backfill churn(사이클 196 이 시정한 결함). 회귀 가드 =
# tests/unit/db/test_cycle299_retention_expansion.py
# purge_old_rows 로직 불변 (상수만, "390일 지난 것만 삭제").
DAILY_RETENTION_DAYS = 390

# 사이클 192 (2026-07-04) — 날짜 슬라이스 루프 런어웨이 가드.
# 잔여 backlog 는 다음 실행이 드레인 (일 1회 16:15 KST task).
PURGE_MAX_DATE_ITERATIONS = 500


async def purge_old_rows(
    cutoff_date: date,
    *,
    protected_tickers: set[str] | None = None,
) -> dict[str, int]:
    """T-390일 retention. cutoff_date 이전 row DELETE.

    보유 기간의 근거는 `DAILY_RETENTION_DAYS` 정의부 주석이다 — VCP backfill
    target(225 영업일) 위로 마진을 남기는 값이고, 그 둘은 함께 움직인다.

    사이클 192 (2026-07-04) — PostgREST returning=representation 응답 비대로
    매 실행 실패 (6/16 도입 이래 515건 누적, 47,924행 × raw JSONB 응답 시도).
    사이클 175 루프 배치 패턴 답습 + 복합 PK (ticker, bas_dd) 적응:
    날짜 슬라이스 루프로 재구성:
      (1) SELECT oldest bas_dd (lt cutoff, protected 제외) → 없으면 drained break
      (2) 그 날짜 전체 DELETE (protected 제외)
      (3) deleted 누적 → PURGE_MAX_DATE_ITERATIONS cap (런어웨이 가드)
    핵심: SELECT/DELETE 양쪽 protected 제외 필수 (SELECT 누락 = never-drain 회귀).

    사이클 M2b — asyncpg 전환. protected_tickers 는 `ticker <> ALL($::text[])` SQL 절
    양쪽(SELECT/DELETE)에 필수 동행 (P-3 HIGH 가드 계승).

    Note (사이클 193 리뷰): 루프 내 SELECT(oldest bas_dd)는 멱등 read 지만
    `_with_retry` 를 **의도적으로 미경유** — G-187-A2 AST 가드가
    `purge_old_rows` 함수 전체의 `_with_retry` Call==0 을 불변식으로 강제
    (쓰기 함수 멱등 보수 분류). SELECT 가 connection 계열 예외를 맞으면 그날 purge 는
    부분 누적 후 graceful 종료 → 다음날 16:15 task 가 잔여 드레인 (일 1회 멱등,
    적체 위험 무 = 데이터/안전성 영향 0). retry 회복력이 필요해지면 가드를
    call-level 로 세분화(SELECT 허용 / DELETE 금지)하는 별도 사이클로 처리.

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
    - G-187-A2 `_with_retry` 미경유 (쓰기 함수)
    """
    started = _time.perf_counter()
    protected_count = len(protected_tickers) if protected_tickers else 0
    protected_list = list(protected_tickers) if protected_tickers else None
    deleted = 0
    # M6 — cutoff_date DATE 컬럼 바인딩. str 입력도 date 로 강제 변환.
    cutoff_date = to_date(cutoff_date)

    try:
        for _ in range(PURGE_MAX_DATE_ITERATIONS):
            # (1) 가장 오래된 삭제 대상 날짜 1건 조회 — SELECT 쪽 protected 제외 필수.
            #     누락 시: protected 만 남은 날짜를 SELECT 가 계속 반환 → never-drain 회귀.
            if protected_list:
                sel_row = await pg.fetchrow(
                    "SELECT bas_dd FROM stock_master_daily "
                    "WHERE bas_dd < $1 AND ticker <> ALL($2::text[]) "
                    "ORDER BY bas_dd LIMIT 1",
                    cutoff_date, protected_list,
                )
            else:
                sel_row = await pg.fetchrow(
                    "SELECT bas_dd FROM stock_master_daily "
                    "WHERE bas_dd < $1 "
                    "ORDER BY bas_dd LIMIT 1",
                    cutoff_date,
                )
            if sel_row is None:
                break  # drained

            oldest = _parse_bas_dd(sel_row["bas_dd"]) or sel_row["bas_dd"]

            # (2) 그 날짜 전체 DELETE — 사이클 32 R4 영속(보유/익일청산 절대 보호,
            #     DELETE 쪽도 동일 적용).
            if protected_list:
                del_result = await pg.execute(
                    "DELETE FROM stock_master_daily "
                    "WHERE bas_dd = $1 AND ticker <> ALL($2::text[])",
                    oldest, protected_list,
                )
            else:
                del_result = await pg.execute(
                    "DELETE FROM stock_master_daily WHERE bas_dd = $1",
                    oldest,
                )
            deleted += _parse_delete_count(del_result)

    except Exception as exc:
        # 사이클 190 예외 타입 계측 + 부분 누적 deleted 반환 (graceful).
        # M6 — cutoff_date 가 to_date() 로 None 변환됐을 가능성(파싱 실패) 방어:
        # .isoformat() 이 except 블록 내부에서 재차 raise 하면 graceful 계약이
        # 깨진다(예외가 이 함수 밖으로 전파) → getattr 폴백으로 무조건 문자열화.
        cutoff_repr = cutoff_date.isoformat() if cutoff_date is not None else "None"
        logger.exception(
            "[stock_master_daily_purge] 루프 실패 graceful cutoff=%s protected=%d "
            "%s: %s",
            cutoff_repr, protected_count, type(exc).__name__, str(exc)[:150],
        )
        elapsed_ms = int((_time.perf_counter() - started) * 1000)
        return {"deleted": deleted, "protected_count": protected_count, "elapsed_ms": elapsed_ms}

    elapsed_ms = int((_time.perf_counter() - started) * 1000)

    logger.info(
        "[stock_master_daily_purge] deleted=%d protected=%d elapsed_ms=%d cutoff=%s",
        deleted, protected_count, elapsed_ms, cutoff_date.isoformat(),
    )

    return {
        "deleted": deleted,
        "protected_count": protected_count,
        "elapsed_ms": elapsed_ms,
    }


def _parse_delete_count(status_str) -> int:
    """asyncpg execute() 상태 문자열("DELETE N") → affected int."""
    try:
        return int(str(status_str).strip().split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0
