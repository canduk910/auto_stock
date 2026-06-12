"""stock_master READ-ONLY 라우트 (사이클 84) + 수동 trigger (사이클 90).

6 GET 엔드포인트 (Q9=B 결정, L-2 AST 영구 가드):
- GET /api/stock-master/stats
- GET /api/stock-master/list
- GET /api/stock-master/scan-pool/summary
- GET /api/stock-master/{ticker}/history
- GET /api/stock-master/{ticker}/daily  ← 사이클 124 신규
- GET /api/stock-master/{ticker}

1 POST 엔드포인트 (사이클 90 Q24=B 예외 허용, L-2 화이트리스트):
- POST /api/stock-master/refresh-universe

라우트 순서 의무: 정적 경로 (stats / list / scan-pool / refresh-universe) 를 동적 ({ticker}) 보다 먼저 등록.
/{ticker}/history 와 /{ticker}/daily 는 /{ticker} 보다 먼저 등록 (FastAPI LIFO 정합).
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException, Query

from src.db import stock_master
from src.db import stock_master_daily
from src.models.response import ApiResponse

router = APIRouter()

# Q25=A in-flight 가드 — 동시 호출 시 두 번째 호출 즉시 409 Conflict.
# KIS Rate Limit 폭주 차단 + 25초 작업 중복 차단 (사이클 90 사용자 결정).
_refresh_universe_lock = asyncio.Lock()


@router.post("/refresh-universe", response_model=ApiResponse)
async def refresh_universe_now(force: bool = True):
    """사이클 90 — universe 500+ 즉시 trigger (수동 발화).

    장 종료 후 또는 scheduler idle 상태에서 사용자 즉시 실행.
    Q25=A 단일 in-flight 가드 = 동시 호출 시 두 번째 호출 즉시 409 Conflict.
    Q27=A 사이클 89 [stock_master_bulk_refresh] 영속 활용 (자동/수동 구분 0).

    사이클 84 L-2 AST 영구 가드 영역 = POST 1개 예외 허용 (refresh-universe 단독).
    라우트 본문에서 logger.* 직접 emit 0건 — fetch 함수 내부 emit 만 활용 (L-3 영속).
    """
    if _refresh_universe_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="universe refresh 진행 중 — 잠시 후 재시도",
        )

    async with _refresh_universe_lock:
        # 사이클 110 (2026-06-11) — silent 결함 영역 영구 영속이 영구 시정.
        # 사이클 101 (Q68=A+Q69=B) 영역에서 fetch_top_500_universe + _universe_eager_refresh_loop
        # 영구 폐기 완료. 본 라우트 import 영역 동행 시정 누락 silent 결함 (사이클 101~108 발견 0건).
        # 단일 대체 영역 영구 영속이 = _full_universe_load_once() (사이클 101 영역 영구 영속이
        # market_cap FHPST01740000 페이징 + CTPF1002R + stock_master upsert 영역 내장).
        # 사이클 106 lifecycle race 차단 영속 + 사이클 107 raw 보강 영속 + 사이클 109 화이트리스트 영속.
        from src.engine.scanner import _full_universe_load_once

        start_time = time.monotonic()
        try:
            # 사이클 120 — force 인자 영속 (UI "지금 새로고침" 디폴트 True = 즉시 검증).
            # 사이클 116/118/119 매핑 영역 영구 영속이 매번 적용 의무 (TTL 우회).
            # 자동 발화 (사이클 106 영역 매일 20:00:05) = force=False 영속 (TTL 영구 영속이 적용).
            summary = await _full_universe_load_once(force=force)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # 사이클 110 응답 영역 영구 영속이 — _full_universe_load_once summary 9 키 중
        # 운영자 관심 7 키 노출. universe ≡ summary["total"] (사이클 89 응답 영속 호환).
        # 사이클 117 (2026-06-12) — source 키 추가 (사이클 110 영역 누락 보강).
        # 사이클 115 _full_universe_load_once summary["source"] = "krx" 또는 "kis_fallback".
        source = summary.get("source", "unknown")
        return ApiResponse(
            success=True,
            data={
                "universe": summary.get("total", 0),
                "elapsed_ms": elapsed_ms,
                "fetched": summary.get("fetched", 0),
                "skipped_ttl": summary.get("skipped_ttl", 0),
                "failed": summary.get("failed", 0),
                "kospi": summary.get("kospi", 0),
                "kosdaq": summary.get("kosdaq", 0),
                "source": source,
            },
            message=(
                f"universe {summary.get('total', 0)} ticker 즉시 적재 완료 "
                f"(source={source}, fetched={summary.get('fetched', 0)}, "
                f"skipped_ttl={summary.get('skipped_ttl', 0)}, "
                f"failed={summary.get('failed', 0)})"
            ),
        )


@router.get("/stats")
async def get_stock_master_stats():
    """stock_master 집계 — count_all / bfdy_clpr_present / nxt_tradable_count / top_10_recent."""
    data = await stock_master.get_stats()
    return ApiResponse(success=True, data=data, message="")


@router.get("/list")
async def list_stock_master(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """stock_master 페이징 list. limit ∈ [1, 1000], offset ≥ 0."""
    data = await stock_master.list_all(limit=limit, offset=offset)
    return ApiResponse(success=True, data=data, message="")


@router.get("/scan-pool/summary")
async def get_scan_pool_summary():
    """사이클 83 [scan_pool_eager_refresh] 오늘 KST 발생 카운트."""
    count = await stock_master.count_eager_refresh_today()
    return ApiResponse(
        success=True,
        data={"eager_refresh_today": count},
        message="",
    )


@router.get("/{ticker}/history")
async def get_stock_master_history(
    ticker: str,
    limit: int = Query(100, ge=1, le=1000),
):
    """ticker 별 변경 이력 (changed_at DESC). migration 032 stock_master_history 조회."""
    data = await stock_master.list_history(ticker=ticker, limit=limit)
    return ApiResponse(success=True, data=data, message="")


@router.get("/{ticker}/daily")
async def get_stock_master_daily(
    ticker: str,
    days: int = Query(30, ge=1, le=100),
):
    """사이클 124 — ticker 일봉 데이터 (최근 days일, stock_master_daily 조회).

    라우트 등록 순서: /{ticker}/history ← /{ticker}/daily ← /{ticker} 순서 의무.
    FastAPI LIFO 정합 — /daily 가 동적 {ticker} 보다 먼저 등록되어야 /daily 캡처 차단.

    404: ticker 미존재 또는 일봉 데이터 없음.
    graceful: stock_master_daily 조회 예외 → 500 대신 빈 list 반환 (사이클 88 G-REJECT 패턴).
    """
    # 사이클 90 — POST only 경로 보호 (GET 요청이 동적 {ticker} 로 라우팅되는 경우 차단)
    _POST_ONLY_PATHS = {"refresh-universe"}
    if ticker in _POST_ONLY_PATHS:
        raise HTTPException(status_code=405, detail=f"Method Not Allowed — {ticker} 은 POST only")

    try:
        rows = await stock_master_daily.get_recent_daily(ticker=ticker, days=days)
    except Exception:
        rows = []

    if not rows:
        # ticker 존재 여부와 무관하게 일봉 데이터 없으면 404
        raise HTTPException(
            status_code=404,
            detail=f"ticker={ticker} 일봉 데이터 없음 (days={days})",
        )

    return ApiResponse(success=True, data=rows, message=f"{len(rows)}일 일봉")


@router.get("/{ticker}")
async def get_stock_master_detail(ticker: str):
    """단건 조회. 미존재 시 404.

    사이클 90 라우팅 가드: `refresh-universe` 는 POST only 경로 — GET 요청 시 405.
    동적 {ticker} 가 POST only 경로를 잡아버리는 FastAPI 라우팅 특성 영구 차단.
    """
    # 사이클 90 — POST only 경로 보호: GET 요청이 동적 {ticker} 로 라우팅되는 경우 차단
    _POST_ONLY_PATHS = {"refresh-universe"}
    if ticker in _POST_ONLY_PATHS:
        raise HTTPException(status_code=405, detail=f"Method Not Allowed — {ticker} 은 POST only")

    data = await stock_master.get(ticker)
    if data is None:
        raise HTTPException(status_code=404, detail=f"ticker={ticker} not found")
    # StockBasics → dict 변환 (model_dump 사용)
    if hasattr(data, "model_dump"):
        return ApiResponse(success=True, data=data.model_dump(), message="")
    return ApiResponse(success=True, data=dict(data), message="")
