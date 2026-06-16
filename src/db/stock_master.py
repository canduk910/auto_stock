"""stock_master CRUD — KIS CTPF1002R 응답 캐시 + 24h TTL.

NXT 거래가능 여부 사전 판별 (Phase G, 2026-05-11):
- 매수 진입/익일 청산 직전 `get(ticker)` → miss/stale 이면 `inquire_stock_basics` 호출 후 `upsert_one`.
- `is_stale(ticker)` 로 24h 초과 행 판정.

supabase 동기 SDK 호출은 모두 `asyncio.to_thread()` 위임.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.db._kst import KST, now_kst_iso
from src.db.supabase import supabase
from src.models.stock import StockBasics

logger = logging.getLogger(__name__)

TABLE_NAME = "stock_master"


def _to_row(basics: StockBasics, *, refreshed_at: datetime | None = None) -> dict:
    """StockBasics → Supabase row dict 변환."""
    return {
        "ticker": basics.ticker,
        "name": basics.name or "",
        "excg_dvsn_cd": basics.excg_dvsn_cd or "",
        "nxt_tradable": bool(basics.nxt_tradable),
        "krx_halted": bool(basics.krx_halted),
        "admin_item": bool(basics.admin_item),
        "raw": dict(basics.raw or {}),
        "refreshed_at": refreshed_at.isoformat() if refreshed_at is not None else now_kst_iso(),
    }


def _from_row(row: dict) -> StockBasics:
    """Supabase row → StockBasics 변환 (refreshed_at 은 모델에 노출 안 함)."""
    return StockBasics(
        ticker=row.get("ticker", ""),
        name=row.get("name", "") or "",
        excg_dvsn_cd=row.get("excg_dvsn_cd", "") or "",
        nxt_tradable=bool(row.get("nxt_tradable", False)),
        krx_halted=bool(row.get("krx_halted", False)),
        admin_item=bool(row.get("admin_item", False)),
        raw=row.get("raw") or {},
    )


async def upsert_one(basics: StockBasics) -> None:
    """단건 upsert — refreshed_at 은 현재 KST 시각으로 자동 세팅.

    Phase G2 (2026-05-13) 이중 안전망: 호출자가 KIS pdno 12자리 형식 (`00000A000100`)
    을 넘기더라도 6자리 KRX 단축코드로 정규화 후 저장한다. `inquire_stock_basics`
    경로 외 마이그레이션 스크립트/수동 보강 등에서 잘못된 형식이 들어와도 PK
    정합성 (positions.ticker = 6자리) 을 보장.
    """
    # 6자리 숫자가 아니면 정규화 시도 (defense in depth — 호출자 경로 무관)
    if basics.ticker and not (len(basics.ticker) == 6 and basics.ticker.isdigit()):
        from src.api.condition import _normalize_ticker

        normalized = _normalize_ticker(basics.ticker)
        if normalized and normalized != basics.ticker:
            logger.warning(
                "stock_master.upsert: ticker 정규화 %s → %s (KIS pdno 형식 결함 차단)",
                basics.ticker, normalized,
            )
            basics = basics.model_copy(update={"ticker": normalized})

    row = {
        **_to_row(basics),
        "refreshed_at": now_kst_iso(),
    }
    await asyncio.to_thread(
        lambda: supabase.table(TABLE_NAME).upsert(row, on_conflict="ticker").execute()
    )
    logger.debug(
        "stock_master upsert: %s (nxt_tradable=%s)", basics.ticker, basics.nxt_tradable
    )


async def get(ticker: str) -> Optional[StockBasics]:
    """단건 조회. 미존재 시 None."""
    result = await asyncio.to_thread(
        lambda: supabase.table(TABLE_NAME).select("*").eq("ticker", ticker).execute()
    )
    rows = result.data or []
    if not rows:
        return None
    return _from_row(rows[0])


# ============================================================
# 사이클 129 — master_raw 영역 영구 영속
#
# Q6=C 별도 컬럼 영역 영속 (사이클 81 G-AST1 영속 보호).
# raw 영역 절대 변경 0 영속 의무.
# ============================================================


async def upsert_master_raw(ticker: str, master_raw: dict) -> None:
    """KIS 마스터 파일 record 영역 upsert (master_raw 컬럼 단독 영역).

    사이클 81 G-AST1 영속 보호 영역 = raw 영역 변경 0 영구 영속.
    KST timestamp 영속 의무 (사이클 68 G-10b 답습).

    사이클 146 (2026-06-16) — 결함 #2 시정 영구 영속:
    운영 사례 = 2026-06-16 09:09:04~09:09:49 KST 45초간 623건 폭주 = 신규 ticker
    (900xxx ETN / 950xxx 외국기업 / 490xxx 신규 상장) 영역 영구 영속에서 NOT NULL 위반:
    `null value in column "nxt_tradable" of relation "stock_master"`.
    근본 원인 = `master_raw` 영역 영구 영속 단독 upsert payload 영역 영구 영속에 `nxt_tradable`
    부재 → 신규 ticker 영역 영구 영속 INSERT 시 NULL 시도 → NOT NULL 위반.
    메인 세션 영역 영구 영속 hotfix `ALTER COLUMN nxt_tradable SET DEFAULT FALSE` 적용 완료
    + 사이클 146 코드 영역 영구 영속 이중 안전망 = 신규 ticker INSERT 시 `nxt_tradable=False`
    명시 영역 영구 영속 (사이클 81 G-AST1 보수적 폴백 영구 영속 + 사이클 32 R4 universe guard 답습).

    UPSERT 영역 영구 영속 분기 영역 영구 영속:
    - 신규 ticker (DB 미존재) = INSERT with master_raw + master_raw_updated_at + nxt_tradable=False
      (보수적 영역 영구 영속 = NXT 매수 차단, 사이클 81 G-AST1 안전 영구 영속)
    - 기존 ticker (DB 존재) = UPSERT on_conflict="ticker" → master_raw + master_raw_updated_at 만 갱신
      (PostgreSQL ON CONFLICT DO UPDATE 영역 영구 영속이 payload 키 영역만 SET → nxt_tradable
       영역 영구 영속 = 기존 값 영구 영속 보존, raw / krx_halted / admin_item 영역 영속 보존)

    Args:
        ticker: 6자리 KRX 단축코드 영역
        master_raw: KIS 마스터 record (mksc_shrn_iscd + part1 + part2 영역)
    """
    payload = {
        "ticker": ticker,
        "master_raw": dict(master_raw or {}),
        "master_raw_updated_at": now_kst_iso(),
        # 사이클 146 — 신규 ticker 영역 영구 영속 NOT NULL 위반 영구 차단 (DB DEFAULT 영역 이중 안전망).
        # 기존 ticker 영역 영구 영속 = on_conflict="ticker" UPDATE 시 nxt_tradable=False 영역 영구 영속이
        # 덮어쓰기 발생 영역 영구 영속 → 사이클 144 영역 영구 영속 16:10 task `_stock_master_basics_refresh_once`
        # 영역 영구 영속이 다음 발화 시 KIS CTPF1002R 영역 영구 영속 `inquire_stock_basics()` 호출로
        # 정확한 nxt_tradable 영역 영구 영속 복구 영구 영속 (사이클 107 영속).
        "nxt_tradable": False,
    }
    await asyncio.to_thread(
        lambda: (
            supabase.table(TABLE_NAME)
            .upsert(payload, on_conflict="ticker")
            .execute()
        )
    )


async def get_master_raw(ticker: str) -> Optional[dict]:
    """master_raw 영역 단건 조회 (NULL/{} 영역 회피)."""
    result = await asyncio.to_thread(
        lambda: (
            supabase.table(TABLE_NAME)
            .select("master_raw")
            .eq("ticker", ticker)
            .limit(1)
            .execute()
        )
    )
    rows = result.data or []
    if not rows:
        return None
    return rows[0].get("master_raw") or None


async def count_master_raw_today() -> int:
    """오늘 (KST) 갱신된 master_raw 영역 카운트 진단 (16:30 task 영역)."""
    today_kst_iso = now_kst_iso().split("T")[0]  # YYYY-MM-DD 영역
    today_start = f"{today_kst_iso}T00:00:00+09:00"
    try:
        result = await asyncio.to_thread(
            lambda: (
                supabase.table(TABLE_NAME)
                .select("ticker", count="exact")
                .gte("master_raw_updated_at", today_start)
                .limit(0)
                .execute()
            )
        )
        return int(getattr(result, "count", 0) or 0)
    except Exception as exc:
        logger.warning("[stock_master] count_master_raw_today 실패 graceful: %s", exc)
        return 0


async def list_all(limit: int = 100, offset: int = 0) -> list[dict]:
    """페이징 list (UI list 영역). limit ∈ [1, 1000], offset ≥ 0.

    refreshed_at DESC 정렬. raw row dict 그대로 반환 (StockBasics 변환 없음 — UI 직접 표시용).
    """
    result = await asyncio.to_thread(
        lambda: (
            supabase.table(TABLE_NAME)
            .select("*")
            .order("refreshed_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    )
    return result.data or []


async def _count_exact(query_builder) -> int:
    """count="exact" 쿼리 graceful 실행 헬퍼 — 사이클 128.

    Supabase PostgREST `count="exact"` + `.limit(0)` 패턴으로 row 미반환 + count int 만 추출.
    예외 시 0 반환 (graceful — 사이클 126 패턴 답습).
    """
    try:
        result = await asyncio.to_thread(lambda: query_builder().limit(0).execute())
        return int(getattr(result, "count", 0) or 0)
    except Exception as exc:
        logger.warning("[stock_master] count='exact' 쿼리 실패 graceful: %s", exc)
        return 0


async def get_stats() -> dict:
    """집계 — 8 키 반환.

    사이클 85 4 키 → 사이클 124 8 키 확장 → 사이클 126 count_all 정확도 시정
    → 사이클 128 4 카운트 silent cap 완전 시정:
    - count_all / bfdy_clpr_present / nxt_tradable_count / top_10_recent (기존)
    - with_hts_avls / with_acml_tr_pbmn (사이클 107/108 raw 보강 비율 가시화)
    - total_daily_rows / last_daily_load_at (stock_master_daily 연동)

    사이클 128 (2026-06-13) — 4 카운트 silent cap 영구 폐기:
    - bfdy_clpr_present / nxt_tradable_count / with_hts_avls / with_acml_tr_pbmn
      모두 count="exact" 별도 쿼리로 전환 (사이클 126 count_all 패턴 100% 답습)
    - `.range(0, 9999)` Python-side sum 영역 영구 폐기 (PostgREST 1000행 silent cap)
    - top_10_recent 는 별도 작은 limit(10) fetch (전체 raw 의존 폐기)
    - 운영 실측 사이클 126: nxt=400 → UI ~150 잠재 결함 영역 영구 차단
    """
    from src.db import stock_master_daily as _smd  # 순환 임포트 방지 local import

    # 사이클 128 — 5 카운트 모두 count="exact" 별도 쿼리 (사이클 126 패턴 답습)
    # count_all (필터 없음)
    count_all = await _count_exact(
        lambda: supabase.table(TABLE_NAME).select("ticker", count="exact")
    )

    # nxt_tradable_count — nxt_tradable=True eq 필터
    nxt_tradable_count = await _count_exact(
        lambda: (
            supabase.table(TABLE_NAME)
            .select("ticker", count="exact")
            .eq("nxt_tradable", True)
        )
    )

    # bfdy_clpr_present — raw->>bfdy_clpr 키 존재 + 0/'0'/'' 제외
    # PostgREST JSONB text 비교: raw->>bfdy_clpr (text) → null/0/'' 제외
    bfdy_clpr_present = await _count_exact(
        lambda: (
            supabase.table(TABLE_NAME)
            .select("ticker", count="exact")
            .not_.is_("raw->>bfdy_clpr", "null")
            .neq("raw->>bfdy_clpr", "0")
            .neq("raw->>bfdy_clpr", "")
        )
    )

    # with_hts_avls — raw->>hts_avls 비-0
    with_hts_avls = await _count_exact(
        lambda: (
            supabase.table(TABLE_NAME)
            .select("ticker", count="exact")
            .not_.is_("raw->>hts_avls", "null")
            .neq("raw->>hts_avls", "0")
            .neq("raw->>hts_avls", "")
        )
    )

    # with_acml_tr_pbmn — raw->>acml_tr_pbmn 비-0
    with_acml_tr_pbmn = await _count_exact(
        lambda: (
            supabase.table(TABLE_NAME)
            .select("ticker", count="exact")
            .not_.is_("raw->>acml_tr_pbmn", "null")
            .neq("raw->>acml_tr_pbmn", "0")
            .neq("raw->>acml_tr_pbmn", "")
        )
    )

    # top_10_recent — 별도 작은 limit(10) fetch (사이클 128: 전체 raw 의존 폐기)
    try:
        top_result = await asyncio.to_thread(
            lambda: (
                supabase.table(TABLE_NAME)
                .select("ticker, name, refreshed_at")
                .order("refreshed_at", desc=True)
                .limit(10)
                .execute()
            )
        )
        top_rows = top_result.data or []
    except Exception:
        logger.warning("[stock_master] get_stats top_10_recent 조회 실패 graceful")
        top_rows = []

    top_10_recent = [
        {
            "ticker": r.get("ticker", ""),
            "name": r.get("name", ""),
            "refreshed_at": r.get("refreshed_at", ""),
        }
        for r in top_rows
    ]

    # stock_master_daily 연동 집계 (graceful — 테이블 미존재·네트워크 장애 대응)
    try:
        total_daily_rows = await _smd.count_all()
    except Exception:
        logger.warning("[stock_master] get_stats total_daily_rows 조회 실패 graceful")
        total_daily_rows = 0

    try:
        last_daily_date = await _smd.max_bas_dd()  # ticker=None → 전체 MAX
        last_daily_load_at = str(last_daily_date) if last_daily_date is not None else None
    except Exception:
        logger.warning("[stock_master] get_stats last_daily_load_at 조회 실패 graceful")
        last_daily_load_at = None

    return {
        "count_all": count_all,
        "bfdy_clpr_present": bfdy_clpr_present,
        "nxt_tradable_count": nxt_tradable_count,
        "top_10_recent": top_10_recent,
        "with_hts_avls": with_hts_avls,
        "with_acml_tr_pbmn": with_acml_tr_pbmn,
        "total_daily_rows": total_daily_rows,
        "last_daily_load_at": last_daily_load_at,
    }


async def list_paged_by_filter(
    *,
    market: str | None = None,
    min_market_cap: int = 0,
    min_trade_amount: int = 0,
    name_substr: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """사이클 128 신규 — UI 종목목록 4 필터 + 페이징 + total count.

    필터 (모두 optional, 빈 필터 = list_all 동등 — T-1 영속):
    - market: "KOSPI" → excg_dvsn_cd="02" / "KOSDAQ" → "03" / None → 전체
    - min_market_cap: int (원 단위). hts_avls(백만원) × 1_000_000 비교
    - min_trade_amount: int (원 단위). acml_tr_pbmn 직접 비교
    - name_substr: str (대소문자 무시 substring, ilike("name", "%substr%"))

    응답:
        {"items": list[dict], "total": int, "limit": int, "offset": int}

    정렬: refreshed_at DESC 영속 (기존 list_all 답습).
    total: count="exact" 별도 쿼리 (사이클 126/128 패턴 답습 — PostgREST 1000 cap 회피).

    영속 의무:
    - 사이클 108 list_by_filter (scanner 전용) 와 분리 — UI list 별개 신규 함수
    - 사이클 38 명문화 (scanner 단계 매수 진입 전용 무관 — UI READ-ONLY 영역)
    """
    # 필터 정규화
    market_norm = (market or "").upper() if market else None
    market_eq: tuple[str, str] | None = None
    if market_norm == "KOSPI":
        market_eq = ("excg_dvsn_cd", "02")
    elif market_norm == "KOSDAQ":
        market_eq = ("excg_dvsn_cd", "03")

    name_pat: str | None = None
    if name_substr:
        # ilike 대소문자 무시 substring
        cleaned = name_substr.strip()
        if cleaned:
            name_pat = f"%{cleaned}%"

    # 시총/거래대금 단위 환산
    # raw.hts_avls 단위 = 백만원 → min_market_cap (원) / 1_000_000 의 ceil 비교
    hts_avls_threshold: int = 0
    if min_market_cap and min_market_cap > 0:
        # 백만원 단위 환산 (정수 ceil)
        hts_avls_threshold = (min_market_cap + 999_999) // 1_000_000

    acml_tr_pbmn_threshold: int = 0
    if min_trade_amount and min_trade_amount > 0:
        acml_tr_pbmn_threshold = int(min_trade_amount)

    def _build_query(*, with_count: bool):
        """공통 쿼리 빌더 — count 쿼리/데이터 쿼리 양쪽에서 동일 필터 체인 적용."""
        if with_count:
            q = supabase.table(TABLE_NAME).select("ticker", count="exact")
        else:
            q = (
                supabase.table(TABLE_NAME)
                .select("*")
                .order("refreshed_at", desc=True)
            )

        if market_eq is not None:
            q = q.eq(market_eq[0], market_eq[1])
        if name_pat is not None:
            q = q.ilike("name", name_pat)
        # JSONB numeric 비교 — 사이클 128 Supabase MCP READ-ONLY 검증 확정:
        # - raw->'hts_avls' (jsonb operator, NOT raw->>'hts_avls' text) numeric gte 정확
        # - raw->>'hts_avls' text gte 는 자릿수 비교 결함 ('999' < '1000' false → 332 vs 2696 부정확)
        # - KIS 응답 99.96% (2,696/2,697) jsonb number 타입 영속 → 안전
        # - jsonb string 잔존 1건 영역은 PostgREST 비교 silent skip (graceful)
        if hts_avls_threshold > 0:
            q = q.gte("raw->hts_avls", hts_avls_threshold)
        if acml_tr_pbmn_threshold > 0:
            q = q.gte("raw->acml_tr_pbmn", acml_tr_pbmn_threshold)

        return q

    # total count 쿼리
    try:
        count_result = await asyncio.to_thread(
            lambda: _build_query(with_count=True).limit(0).execute()
        )
        total = int(getattr(count_result, "count", 0) or 0)
    except Exception as exc:
        logger.warning("[stock_master] list_paged_by_filter count 쿼리 실패 graceful: %s", exc)
        total = 0

    # 데이터 쿼리 (range 페이징)
    try:
        data_result = await asyncio.to_thread(
            lambda: (
                _build_query(with_count=False)
                .range(offset, offset + limit - 1)
                .execute()
            )
        )
        items = data_result.data or []
    except Exception as exc:
        logger.warning("[stock_master] list_paged_by_filter data 쿼리 실패 graceful: %s", exc)
        items = []

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


async def list_history(ticker: str, limit: int = 100) -> list[dict]:
    """ticker 별 변경 이력 (changed_at DESC). stock_master_history 테이블 조회.

    migration 032 적용 의무 — 테이블 미존재 시 Supabase 400 에러.
    """
    result = await asyncio.to_thread(
        lambda: (
            supabase.table("stock_master_history")
            .select("*")
            .eq("ticker", ticker)
            .order("changed_at", desc=True)
            .limit(limit)
            .execute()
        )
    )
    return result.data or []


async def count_eager_refresh_today() -> int:
    """사이클 100 — 3 prefix OR 통합 카운트.

    사이클 89 [universe_eager_refresh] (244건 영속) + 사이클 83 [scan_pool_eager_refresh]
    (230건 영속) + 사이클 95 [stock_master_bulk_refresh] (140건 영속) 통합.

    사용자 결정 Q65=C-1 (3 prefix OR 합산).
    사이클 68 KST 영속 (`today_kst()` 사용).
    """
    from src.db._kst import today_kst

    today = today_kst()
    start = f"{today}T00:00:00+09:00"
    end = f"{today}T23:59:59.999999+09:00"

    PREFIXES = (
        "%[universe_eager_refresh]%",     # 사이클 89, 244건 영속
        "%[scan_pool_eager_refresh]%",    # 사이클 83, 230건 영속 (기존 유지)
        "%[stock_master_bulk_refresh]%",  # 사이클 95, 140건 영속
    )

    total = 0
    for pattern in PREFIXES:
        result = await asyncio.to_thread(
            lambda p=pattern: (
                supabase.table("system_logs")
                .select("id", count="exact")
                .ilike("message", p)
                .gte("timestamp", start)
                .lte("timestamp", end)
                .execute()
            )
        )
        # supabase-py count 응답은 result.count 또는 len(result.data)
        if hasattr(result, "count") and result.count is not None:
            total += int(result.count)
        else:
            total += len(result.data or [])
    return total


async def list_by_filter(
    *,
    market: str | None = None,
    min_market_cap: int = 0,
    min_trade_amount: int = 0,
    exclude_tickers: list[str] | None = None,
    nxt_tradable: bool | None = None,
    limit: int = 500,
) -> list[dict]:
    """시총·거래대금·시장·NXT 거래가능 필터로 stock_master 를 조회한다 (사이클 108).

    KIS volume-rank API 없이 DB 기반으로 VB/LTV/BFB 유니버스를 구성한다 (KIS API 호출 0건).

    NOTE: Supabase PostgREST 는 JSONB 숫자 값 직접 비교를 지원하지 않는다.
    따라서 DB 에서 limit*2 버퍼 조회 후 Python-side 에서 JSONB raw 키 필터링을 수행한다.

    Args:
        market: "kospi" (excg_dvsn_cd=02) / "kosdaq" (excg_dvsn_cd=03) / None (전체)
        min_market_cap: 시가총액 최소값 (원 단위). hts_avls(백만원) × 1_000_000 비교.
        min_trade_amount: 거래대금 최소값 (원 단위). acml_tr_pbmn 직접 비교.
        exclude_tickers: 제외 종목 리스트.
        nxt_tradable: None=전체 / True=NXT 거래가능만 / False=NXT 불가만.
        limit: 결과 최대 건수 (default 500).

    Returns:
        [{"ticker": str, "name": str, "excg_dvsn_cd": str, "nxt_tradable": bool, "raw": dict}, ...]
    """
    exclude_set: set[str] = set(exclude_tickers or [])
    # 2× 버퍼 조회 — JSONB Python-side 필터 후 limit 를 충족하도록 여유분 확보
    fetch_limit = max(limit * 2, 1000)

    query = (
        supabase.table(TABLE_NAME)
        .select("ticker, name, excg_dvsn_cd, nxt_tradable, raw")
        .order("refreshed_at", desc=True)
        .limit(fetch_limit)
    )
    if market == "kospi":
        query = query.eq("excg_dvsn_cd", "02")
    elif market == "kosdaq":
        query = query.eq("excg_dvsn_cd", "03")
    if nxt_tradable is not None:
        query = query.eq("nxt_tradable", nxt_tradable)

    result = await asyncio.to_thread(lambda: query.execute())
    rows = result.data or []

    filtered: list[dict] = []
    for row in rows:
        if len(filtered) >= limit:
            break
        ticker = row.get("ticker", "")
        if not ticker:
            continue
        if ticker in exclude_set:
            continue

        raw: dict = row.get("raw") or {}

        # 시가총액 필터 — hts_avls 단위: 백만원 → 원 변환 후 비교
        if min_market_cap > 0:
            try:
                hts_avls = int(raw.get("hts_avls") or 0)
            except (ValueError, TypeError):
                hts_avls = 0
            if hts_avls * 1_000_000 < min_market_cap:
                continue

        # 거래대금 필터 — acml_tr_pbmn 단위: 원
        if min_trade_amount > 0:
            try:
                acml_tr = int(raw.get("acml_tr_pbmn") or 0)
            except (ValueError, TypeError):
                acml_tr = 0
            if acml_tr < min_trade_amount:
                continue

        filtered.append(row)

    return filtered


async def is_stale(ticker: str, max_age_hours: int = 24) -> bool:
    """24h 초과 또는 미존재 시 True — KIS 재조회 필요."""
    result = await asyncio.to_thread(
        lambda: supabase.table(TABLE_NAME)
        .select("refreshed_at")
        .eq("ticker", ticker)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return True
    refreshed_at_raw = rows[0].get("refreshed_at")
    if not refreshed_at_raw:
        return True
    try:
        if isinstance(refreshed_at_raw, datetime):
            refreshed_at = refreshed_at_raw
        else:
            # ISO 8601 (timezone-aware 가정 — fromisoformat 은 'Z' 미지원이라 보정)
            iso = refreshed_at_raw.replace("Z", "+00:00")
            refreshed_at = datetime.fromisoformat(iso)
        if refreshed_at.tzinfo is None:
            refreshed_at = refreshed_at.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        logger.warning(
            "stock_master.refreshed_at 파싱 실패: %s (%r) — stale 로 간주",
            ticker, refreshed_at_raw,
        )
        return True
    age = datetime.now(KST) - refreshed_at
    return age > timedelta(hours=max_age_hours)
