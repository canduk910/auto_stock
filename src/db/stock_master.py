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


async def upsert_master_raw(
    ticker: str,
    master_raw: dict,
    *,
    is_kospi200: bool = False,
    is_kosdaq150: bool = False,
) -> None:
    """KIS 마스터 파일 record 영역 upsert (master_raw 컬럼 단독 영역).

    사이클 81 G-AST1 영속 보호 영역 = raw 영역 변경 0 영구 영속.
    KST timestamp 영속 의무 (사이클 68 G-10b 답습).

    사이클 153 (2026-06-16) — is_kospi200 / is_kosdaq150 컬럼 동행 명시 영구 영속:
    KIS 공식 마스터 source 영역 (Q1=A 사용자 결정 영속) 영구 영속.
    - is_kospi200: KOSPI 마스터 영역 record["kospi200_apnt_cls_code"].strip() != "" 영구 영속
    - is_kosdaq150: KOSDAQ 마스터 영역 record["ksq150_nmix_yn"] == "Y" 영구 영속
    사이클 146 nxt_tradable 명시 영속 답습 = ON CONFLICT DO UPDATE 영역 영구 영속이
    payload 키 영역만 SET → 신규/기존 ticker 영역 영구 영속 갱신 보장.

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
        # 사이클 146 — 신규 ticker 영역 NOT NULL 위반 영구 차단 (DB DEFAULT 영역 이중 안전망).
        # 기존 ticker 영역 = on_conflict="ticker" UPDATE 시 nxt_tradable=False 덮어쓰기
        # → 사이클 144 16:10 task `_stock_master_basics_refresh_once` 다음 발화 시
        # KIS CTPF1002R `inquire_stock_basics()` 호출로 정확한 nxt_tradable 복구 (사이클 107 영속).
        "nxt_tradable": False,
        # 사이클 153 — KOSPI200 / KOSDAQ150 지수 편입 여부 동행 명시 영구 영속 (Q1=A).
        # 사이클 146 nxt_tradable 패턴 답습 영구 영속 = ON CONFLICT DO UPDATE 영역 영구 영속이
        # payload 키 영역만 SET → 기존 ticker 신규 갱신 시 명시 의무.
        "is_kospi200": bool(is_kospi200),
        "is_kosdaq150": bool(is_kosdaq150),
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


async def count_active() -> int:
    """stock_master 활성 row 카운트 (사이클 163, _boot prepare 가드용).

    `_boot()` 영역 prepare 호출 *전* count 가드 hook 의 진입점.
    사이클 158 VB 자동 재시도 hook (90초) 한계 보완 (사이클 134
    task_loop_helper stagger 영속 = full_universe 0초 / basics 240초 /
    daily 480초 / master 720초). 적재 본체 완료까지 5분 cap polling.

    사이클 128 count="exact" 패턴 답습 (PostgREST 1000행 silent cap 회피).
    사이클 88 G-REJECT graceful 영속 — supabase 예외 시 0 폴백.

    Returns:
        활성 row 카운트 (count="exact"). 예외 시 0.
    """
    def _query():
        return (
            supabase.table(TABLE_NAME)
            .select("ticker", count="exact")
            .limit(0)
            .execute()
        )

    try:
        result = await asyncio.to_thread(_query)
        return int(getattr(result, "count", 0) or 0)
    except Exception as exc:
        logger.warning("[stock_master_count_active_failed] err=%r", exc)
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
    - min_market_cap: int (원 단위). 생성 컬럼 hts_avls_eok(억원) ≥ min_market_cap // 100_000_000 (사이클 166/168)
    - min_trade_amount: int (원 단위). 생성 컬럼 acml_tr_pbmn_won(원) ≥ min_trade_amount 직접 비교 (사이클 168)
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

    # 시총/거래대금 단위 환산 (사이클 166 정정 + 사이클 168 생성 컬럼 전환)
    # raw.hts_avls 단위 = 억원 → min_market_cap (원) / 100_000_000 의 ceil 비교.
    # KIS FHKST01010100 hts_avls = "HTS 시가총액" (억원). 사이클 108/128 "백만원" 가정은
    # silent 결함 (100배 어긋남). UI 페이징 경로도 동일 결함 전파 → 억원으로 통일.
    # 임계 환산 로직은 사이클 166 그대로 — 생성 컬럼 hts_avls_eok 도 억원 단위라 정합.
    hts_avls_threshold: int = 0
    if min_market_cap and min_market_cap > 0:
        # 억원 단위 환산 (정수 ceil)
        hts_avls_threshold = (min_market_cap + 99_999_999) // 100_000_000

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
        # 사이클 168 — 생성 컬럼 numeric 비교 (jsonb string 결함 영구 시정):
        # - 사이클 128 가정 ("raw 가 jsonb *number* 2,696/2,697")이 운영 DB 에서 회귀:
        #   적재부 condition.py merge 가 KIS 응답 문자열("1503" 등)을 그대로 저장 →
        #   raw.hts_avls / raw.acml_tr_pbmn 가 전부 jsonb *string* (운영 DB 실측 number=0).
        # - 종전 jsonb operator path numeric gte 는 PostgreSQL jsonb 정렬에서
        #   number > string 이라 항상 false → 0건 (필터 무력화). 실측: 종전 0 vs 신규 1,734.
        # - migration 039 생성 컬럼 (STORED bigint) 으로 정확한 numeric 비교 + 인덱스 활용:
        #   hts_avls_eok (억원) / acml_tr_pbmn_won (원). 비숫자/null 은 ~ '^[0-9]+$' 가드로
        #   NULL → .gte 에서 자동 제외 (graceful). raw 읽기만(GENERATED) → 사이클 81 G-AST1 영속.
        if hts_avls_threshold > 0:
            q = q.gte("hts_avls_eok", hts_avls_threshold)
        if acml_tr_pbmn_threshold > 0:
            q = q.gte("acml_tr_pbmn_won", acml_tr_pbmn_threshold)

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
    is_kospi200: bool | None = None,
    is_kosdaq150: bool | None = None,
    limit: int = 500,
    return_stage_counts: bool = False,
    sort_by: str | None = None,
) -> list[dict] | tuple[list[dict], dict[str, list[str]]]:
    """시총·거래대금·시장·NXT/KOSPI200/KOSDAQ150 필터로 stock_master 를 조회 (사이클 108 + 153 + 205).

    KIS volume-rank API 없이 DB 기반으로 유니버스를 구성한다 (KIS API 호출 0건).

    사이클 205 (2026-07-09, phase 1) — DB-side 필터 전환 (selection bias 시정):
    시총/거래대금 컷을 Python-side raw JSONB 파싱 대신 생성 컬럼(migration 039,
    `hts_avls_eok`/`acml_tr_pbmn_won`) 의 `.gte()` DB-side 필터로 수행한다 (list_paged_by_filter
    사이클 168 패턴 답습). 종전 `.order("refreshed_at", desc=True).limit(max(limit*2, 1000))`
    오버페치 + Python-side 컷은 PostgREST 1000행 cap 에 걸려 refreshed_at 최신 버퍼에 든
    일부만 필터 통과 — refreshed_at 은 종목 품질과 무관한 축이라 자의적 부분집합만 스캔되는
    selection bias 였다. DB-side 필터는 자격 종목만 반환(예: 821<1000)하므로 cap 과 편향을
    동시에 해소한다. `.limit(limit)` 직접 사용 (오버페치 폐지).

    사이클 153 (2026-06-16) — KOSPI200 / KOSDAQ150 영역 인자 추가 영구 영속 (사이클 108 nxt_tradable 답습):
    - is_kospi200=True 단독: KOSPI200 종목만
    - is_kosdaq150=True 단독: KOSDAQ150 종목만
    - **둘 다 True: OR 합집합** (donchian_swing 영구 영속 의무, FUNNEL_STAGES[0] "코스피200+코스닥150 합집합")
    - 둘 다 None: 무필터 (회귀 보존)

    Args:
        market: "kospi" (excg_dvsn_cd=02) / "kosdaq" (excg_dvsn_cd=03) / None (전체)
        min_market_cap: 시가총액 최소값 (원 단위). 생성 컬럼 hts_avls_eok(억원) gte
            ceil(min_market_cap/1e8) 임계로 DB-side 비교 (사이클 166 억원 정합 + 사이클 205).
        min_trade_amount: 거래대금 최소값 (원 단위). 생성 컬럼 acml_tr_pbmn_won(원) gte 직접 비교.
        exclude_tickers: 제외 종목 리스트.
        nxt_tradable: None=전체 / True=NXT 거래가능만 / False=NXT 불가만.
        is_kospi200: None=전체 / True=KOSPI200만 (is_kosdaq150 와 OR 합집합).
        is_kosdaq150: None=전체 / True=KOSDAQ150만 (is_kospi200 와 OR 합집합).
        limit: 결과 최대 건수 (default 500). DB fetch limit == 요청 limit (오버페치 폐지, 사이클 205).
        return_stage_counts: 사이클 170 카드 A — True 시 단계별 생존 ticker 누적
            (관찰성 전용, 필터 로직/임계 불변 = 매수 풀 불변). False (기본) = 현행 list.
            사이클 205 — DB-side 전환으로 3쿼리(union/mcap/trade) 구조 (phase 1).
        sort_by: 사이클 205 phase 2 훅. None (기본) = 현행 `refreshed_at DESC` 정렬 유지
            (phase 1 은 정렬 무변경). phase 2 실사용은 별도 사이클 인계.

    Returns:
        return_stage_counts=False (기본): 기존 호출자 회귀 보존.
            [{"ticker": str, "name": str, "excg_dvsn_cd": str, "nxt_tradable": bool,
              "is_kospi200": bool, "is_kosdaq150": bool, "raw": dict}, ...]
        return_stage_counts=True: (filtered, stage) 튜플 (사이클 170 카드 A).
            stage = {"union_tickers": [...], "mcap_tickers": [...], "trade_tickers": [...]}
            - union: index/형식/exclude 통과, 시총·거래대금 gte *전* 쿼리
            - mcap: union + 시총 gte 쿼리
            - trade: mcap + 거래대금 gte 쿼리 (= 최종 filtered ticker 순서 정합)
            attrition (예: union 348 → mcap 348 → trade 321) funnel 관찰성 노출용.
            사이클 205 — 각 단계가 별도 DB 쿼리 (3쿼리, DB-side 필터 전환에 따른 구조 변경).
    """
    exclude_set: set[str] = set(exclude_tickers or [])

    # 사이클 205 — 임계 환산 (list_paged_by_filter 사이클 168 패턴 답습).
    # hts_avls_eok(억원) gte 임계: min_market_cap(원) / 1e8 의 ceil.
    # 동치 근거: Python-side `hts_avls*1e8 >= min_market_cap` ⟺ `hts_avls >= ceil(min_market_cap/1e8)`.
    hts_avls_threshold = 0
    if min_market_cap and min_market_cap > 0:
        hts_avls_threshold = (min_market_cap + 99_999_999) // 100_000_000

    acml_tr_pbmn_threshold = 0
    if min_trade_amount and min_trade_amount > 0:
        acml_tr_pbmn_threshold = int(min_trade_amount)

    def _build_query(*, with_mcap: bool, with_trade: bool):
        """공통 쿼리 빌더 — index/market/nxt 필터 공통 + 시총/거래대금 gte 단계별 결합.

        사이클 205 — DB-side 생성 컬럼(hts_avls_eok/acml_tr_pbmn_won) numeric gte 비교
        (list_paged_by_filter 사이클 168 패턴 답습). raw JSONB Python-side 파싱 폐지.
        """
        q = (
            supabase.table(TABLE_NAME)
            .select("ticker, name, excg_dvsn_cd, nxt_tradable, is_kospi200, is_kosdaq150, raw")
            .order("refreshed_at", desc=True)
        )
        if market == "kospi":
            q = q.eq("excg_dvsn_cd", "02")
        elif market == "kosdaq":
            q = q.eq("excg_dvsn_cd", "03")
        if nxt_tradable is not None:
            q = q.eq("nxt_tradable", nxt_tradable)

        # 사이클 153 — KOSPI200/KOSDAQ150 영역 필터 (Q1=A 영구 영속 + Q2=A OR 합집합 의무).
        if is_kospi200 is True and is_kosdaq150 is True:
            q = q.or_("is_kospi200.eq.true,is_kosdaq150.eq.true")
        elif is_kospi200 is not None and is_kosdaq150 is None:
            q = q.eq("is_kospi200", is_kospi200)
        elif is_kosdaq150 is not None and is_kospi200 is None:
            q = q.eq("is_kosdaq150", is_kosdaq150)
        elif is_kospi200 is not None and is_kosdaq150 is not None:
            q = q.eq("is_kospi200", is_kospi200).eq("is_kosdaq150", is_kosdaq150)

        if with_mcap and hts_avls_threshold > 0:
            q = q.gte("hts_avls_eok", hts_avls_threshold)
        if with_trade and acml_tr_pbmn_threshold > 0:
            q = q.gte("acml_tr_pbmn_won", acml_tr_pbmn_threshold)

        return q.limit(limit)

    def _filter_rows(rows: list[dict]) -> list[dict]:
        """index OR/AND(Python-side 폴백) + exclude + limit break — DB 미이관 로직만."""
        out: list[dict] = []
        for row in rows:
            if len(out) >= limit:
                break
            ticker = row.get("ticker", "")
            if not ticker:
                continue
            if ticker in exclude_set:
                continue

            # 사이클 153 — Python-side OR/AND 필터 (mock 환경 + DB-side .or_() 폴백 영역).
            if is_kospi200 is True and is_kosdaq150 is True:
                if not (row.get("is_kospi200") or row.get("is_kosdaq150")):
                    continue
            elif is_kospi200 is True and is_kosdaq150 is None:
                if not row.get("is_kospi200"):
                    continue
            elif is_kosdaq150 is True and is_kospi200 is None:
                if not row.get("is_kosdaq150"):
                    continue
            elif is_kospi200 is False and is_kosdaq150 is None:
                if row.get("is_kospi200"):
                    continue
            elif is_kosdaq150 is False and is_kospi200 is None:
                if row.get("is_kosdaq150"):
                    continue
            elif is_kospi200 is not None and is_kosdaq150 is not None:
                if row.get("is_kospi200") != is_kospi200:
                    continue
                if row.get("is_kosdaq150") != is_kosdaq150:
                    continue

            out.append(row)
        return out

    if return_stage_counts:
        # 사이클 205 — 3쿼리 (union/mcap/trade). 각 쿼리 동일 정렬+limit, gte 단계별 추가.
        union_result = await asyncio.to_thread(
            lambda: _build_query(with_mcap=False, with_trade=False).execute()
        )
        union_filtered = _filter_rows(union_result.data or [])
        union_tickers = [r["ticker"] for r in union_filtered]

        mcap_result = await asyncio.to_thread(
            lambda: _build_query(with_mcap=True, with_trade=False).execute()
        )
        mcap_filtered = _filter_rows(mcap_result.data or [])
        mcap_tickers = [r["ticker"] for r in mcap_filtered]

        trade_result = await asyncio.to_thread(
            lambda: _build_query(with_mcap=True, with_trade=True).execute()
        )
        trade_filtered = _filter_rows(trade_result.data or [])
        trade_tickers = [r["ticker"] for r in trade_filtered]

        return trade_filtered, {
            "union_tickers": union_tickers,
            "mcap_tickers": mcap_tickers,
            "trade_tickers": trade_tickers,
        }

    result = await asyncio.to_thread(
        lambda: _build_query(with_mcap=True, with_trade=True).execute()
    )
    rows = result.data or []
    return _filter_rows(rows)


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
