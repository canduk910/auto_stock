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


async def get_stats() -> dict:
    """집계 — 8 키 반환.

    사이클 85 4 키 → 사이클 124 8 키 확장:
    - count_all / bfdy_clpr_present / nxt_tradable_count / top_10_recent (기존)
    - with_hts_avls / with_acml_tr_pbmn (사이클 107/108 raw 보강 비율 가시화)
    - total_daily_rows / last_daily_load_at (stock_master_daily 연동)

    전체 rows 1회 조회 후 Python-side JSONB 집계.
    stock_master_daily 집계는 별도 2회 호출 (graceful — None/0 fallback).
    """
    from src.db import stock_master_daily as _smd  # 순환 임포트 방지 local import

    result = await asyncio.to_thread(
        lambda: (
            supabase.table(TABLE_NAME)
            .select("ticker, name, nxt_tradable, raw, refreshed_at")
            .order("refreshed_at", desc=True)
            .execute()
        )
    )
    rows = result.data or []

    count_all = len(rows)
    bfdy_clpr_present = sum(
        1 for r in rows
        if r.get("raw") and r["raw"].get("bfdy_clpr") not in (None, "", "0", 0)
    )
    nxt_tradable_count = sum(1 for r in rows if r.get("nxt_tradable"))

    # 사이클 107/108 raw 보강 비율 — hts_avls/acml_tr_pbmn 적재 현황 가시화
    with_hts_avls = sum(
        1 for r in rows
        if r.get("raw") and r["raw"].get("hts_avls") not in (None, "", "0", 0)
    )
    with_acml_tr_pbmn = sum(
        1 for r in rows
        if r.get("raw") and r["raw"].get("acml_tr_pbmn") not in (None, "", "0", 0)
    )

    top_10_recent = [
        {
            "ticker": r.get("ticker", ""),
            "name": r.get("name", ""),
            "refreshed_at": r.get("refreshed_at", ""),
        }
        for r in rows[:10]
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
