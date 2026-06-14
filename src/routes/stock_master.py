"""stock_master READ-ONLY 라우트 (사이클 84) + 수동 trigger (사이클 90/126) + 진행 폴링 (사이클 127).

7 GET 엔드포인트 (Q9=B 결정, L-2 AST 영구 가드):
- GET /api/stock-master/stats
- GET /api/stock-master/list
- GET /api/stock-master/scan-pool/summary
- GET /api/stock-master/refresh-progress  ← 사이클 127 신규 (5초 폴링)
- GET /api/stock-master/{ticker}/history
- GET /api/stock-master/{ticker}/daily  ← 사이클 124 신규
- GET /api/stock-master/{ticker}

3 POST 엔드포인트 (사이클 90/126 화이트리스트 + 사이클 127 fire-and-forget):
- POST /api/stock-master/refresh-universe  ← 사이클 90 (사이클 127 fire-and-forget 전환)
- POST /api/stock-master/basics/refresh    ← 사이클 126 (사이클 127 fire-and-forget 전환)
- POST /api/stock-master/daily/refresh     ← 사이클 126 (사이클 127 fire-and-forget 전환)

사이클 127 (2026-06-13) — fire-and-forget + 5초 폴링 패턴:
- 사용자 보고: 13분 39초 백엔드 정상 완료 후 axios 클라이언트 디폴트 timeout silent 결함.
- POST 3 라우트 즉시 202 status + status="started" 응답 (작업 시작) + 백그라운드 task 발화.
- GET /refresh-progress 5초 폴링으로 상단 배너 + 카운터 가시화.
- asyncio.Lock 폐기 → refresh_progress.is_running() state 기반 가드 (single source of truth).
- 백그라운드 task 예외 시 finish_progress("failed") 영속 호출 (UI error_message 표시).

라우트 순서 의무: 정적 경로 (stats / list / scan-pool / refresh-* / refresh-progress) 를
동적 ({ticker}) 보다 먼저 등록.
/{ticker}/history 와 /{ticker}/daily 는 /{ticker} 보다 먼저 등록 (FastAPI LIFO 정합).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from src.db import stock_master
from src.db import stock_master_daily
from src.engine import refresh_progress as _rp
from src.models.response import ApiResponse

logger = logging.getLogger("src.routes.stock_master")

router = APIRouter()


async def _run_universe_background(force: bool) -> None:
    """사이클 127 — universe 백그라운드 task.

    once 함수 내부에서 start_progress/update_progress/finish_progress 호출 영속.
    여기서는 예외만 catch → finish_progress("failed") 안전망.
    """
    from src.engine.scanner import _full_universe_load_once

    try:
        await _full_universe_load_once(force=force)
    except Exception as exc:
        logger.exception("[refresh_universe_background] 백그라운드 실패 graceful: %s", exc)
        # once 함수 내부에서 이미 finish_progress("failed") 처리됨 (안전망).
        if _rp.is_running("universe"):
            _rp.finish_progress("universe", "failed", error_message=str(exc))


async def _run_basics_background(force: bool) -> None:
    """사이클 127 — basics 백그라운드 task."""
    from src.engine.scanner import _stock_master_basics_refresh_once

    try:
        await _stock_master_basics_refresh_once(force=force)
    except Exception as exc:
        logger.exception("[refresh_basics_background] 백그라운드 실패 graceful: %s", exc)
        if _rp.is_running("basics"):
            _rp.finish_progress("basics", "failed", error_message=str(exc))


async def _run_daily_background(force: bool) -> None:
    """사이클 127 — daily 백그라운드 task."""
    from src.engine.scanner import _stock_master_daily_load_once

    try:
        await _stock_master_daily_load_once(force=force)
    except Exception as exc:
        logger.exception("[refresh_daily_background] 백그라운드 실패 graceful: %s", exc)
        if _rp.is_running("daily"):
            _rp.finish_progress("daily", "failed", error_message=str(exc))


async def _run_master_background(force: bool) -> None:
    """사이클 129 — master 백그라운드 task (KIS 종목 마스터 파일 적재).

    once 함수 내부에서 start_progress/update_progress/finish_progress 호출 영속.
    예외만 catch → finish_progress("failed") 안전망 (사이클 127 패턴 답습).
    """
    from src.engine.scanner import _stock_master_master_load_once

    try:
        await _stock_master_master_load_once(force=force)
    except Exception as exc:
        logger.exception("[refresh_master_background] 백그라운드 실패 graceful: %s", exc)
        if _rp.is_running("master"):
            _rp.finish_progress("master", "failed", error_message=str(exc))


@router.post("/refresh-universe", response_model=ApiResponse)
async def refresh_universe_now(background_tasks: BackgroundTasks, force: bool = True):
    """사이클 90 (2026-06-09) + 사이클 127 (2026-06-13) — fire-and-forget.

    fire-and-forget 패턴 (사이클 127):
    - 백그라운드 task 발화 + 즉시 응답 (axios timeout silent 결함 영구 차단).
    - is_running("universe") 가드 = state 기반 single source of truth.
    - 진행 상황은 GET /refresh-progress 폴링으로 조회.
    - FastAPI BackgroundTasks 사용 = response 전송 *후* schedule (TestClient 호환 + asyncio.create_task race 영구 차단).

    사이클 84 L-2 AST 영구 가드 영역 = POST 1개 예외 허용 (refresh-universe 단독).
    라우트 본문에서 logger.* 직접 emit 0건 — fetch 함수 내부 emit 만 활용 (L-3 영속).
    """
    if _rp.is_running("universe"):
        raise HTTPException(
            status_code=409,
            detail="universe refresh 진행 중 — 잠시 후 재시도",
        )

    # 사이클 127 — FastAPI BackgroundTasks. response 전송 후 schedule.
    # 사이클 120 force 인자 영속 (UI "지금 새로고침" 디폴트 True = 즉시 검증).
    background_tasks.add_task(_run_universe_background, force=force)

    return ApiResponse(
        success=True,
        data={
            "status": "started",
            "task_key": "universe",
        },
        message="universe refresh 시작 — 진행 상황은 /api/stock-master/refresh-progress 폴링",
    )


@router.post("/basics/refresh", response_model=ApiResponse)
async def refresh_basics_now(background_tasks: BackgroundTasks, force: bool = True):
    """사이클 126 영역 3-C + 사이클 127 — fire-and-forget.

    KRX 1차 폴백 시 NXT/정지/관리종목 하드코딩 False 결함을 즉시 시정.
    fire-and-forget = axios timeout silent 결함 영구 차단 (사이클 126 사용자 보고 사유).

    사이클 84 L-2 영속: POST 1개 추가 예외 허용 (화이트리스트 갱신).
    사이클 90 패턴 100% 답습 + 사이클 127 fire-and-forget 전환 (BackgroundTasks).
    """
    if _rp.is_running("basics"):
        raise HTTPException(
            status_code=409,
            detail="basics refresh 진행 중 — 잠시 후 재시도",
        )

    background_tasks.add_task(_run_basics_background, force=force)

    return ApiResponse(
        success=True,
        data={
            "status": "started",
            "task_key": "basics",
        },
        message="basics refresh 시작 — 진행 상황은 /api/stock-master/refresh-progress 폴링",
    )


@router.post("/daily/refresh", response_model=ApiResponse)
async def refresh_daily_now(background_tasks: BackgroundTasks, force: bool = True):
    """사이클 126 영역 4-B + 사이클 127 — fire-and-forget.

    사이클 122 `_stock_master_daily_load_task_loop` 자동 task 와 동일 함수 호출.
    fire-and-forget = axios timeout silent 결함 영구 차단.

    사이클 84 L-2 영속: POST 1개 추가 예외 허용 (화이트리스트 갱신).
    사이클 90 패턴 100% 답습 + 사이클 127 fire-and-forget 전환 (BackgroundTasks).
    """
    if _rp.is_running("daily"):
        raise HTTPException(
            status_code=409,
            detail="daily refresh 진행 중 — 잠시 후 재시도",
        )

    background_tasks.add_task(_run_daily_background, force=force)

    return ApiResponse(
        success=True,
        data={
            "status": "started",
            "task_key": "daily",
        },
        message="daily refresh 시작 — 진행 상황은 /api/stock-master/refresh-progress 폴링",
    )


@router.post("/master/refresh", response_model=ApiResponse)
async def refresh_master_now(background_tasks: BackgroundTasks, force: bool = True):
    """사이클 129 (2026-06-13) — KIS 종목 마스터 파일 (kospi_code.mst / kosdaq_code.mst) 적재 fire-and-forget.

    사용자 결정 영구 영속:
    - Q4=A 마스터 우선 + Q5=C 전수 보존 + Q6=C master_raw 별도 컬럼
    - Q12 시정: 시총 환산 × 100 (사용자 verbatim 정합)

    KIS 정본 (kis-mcp-query 검증):
    - KOSPI: https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip
    - KOSDAQ: https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip

    자동 task = scheduler `TIME_STOCK_MASTER_MASTER_LOAD=16:30 KST` + start() 직후 1회.
    사이클 127 fire-and-forget BackgroundTasks 패턴 100% 답습.
    사이클 84 L-2 영속: POST 1개 추가 예외 허용 (화이트리스트 갱신).
    """
    if _rp.is_running("master"):
        raise HTTPException(
            status_code=409,
            detail="master refresh 진행 중 — 잠시 후 재시도",
        )

    background_tasks.add_task(_run_master_background, force=force)

    return ApiResponse(
        success=True,
        data={
            "status": "started",
            "task_key": "master",
        },
        message="master refresh 시작 — 진행 상황은 /api/stock-master/refresh-progress 폴링",
    )


@router.get("/refresh-progress")
async def get_refresh_progress():
    """사이클 127 (2026-06-13) — 3 작업 진행 state 통합 조회.

    5초 주기 폴링 영역 (Q1=A 사용자 결정).
    프론트 RefreshProgressBanner 컴포넌트가 useQuery refetchInterval: 5000 폴링.

    응답 schema:
    {
      "universe": {status, total, processed, updated, skipped, failed,
                   started_at, finished_at, elapsed_ms, error_message},
      "basics": {...같은 schema...},
      "daily": {...같은 schema...}
    }

    사이클 84 L-2 READ-ONLY GET 정합 (POST 가 아니므로 화이트리스트 무관).
    """
    return ApiResponse(
        success=True,
        data=_rp.get_all_progress(),
        message="",
    )


@router.get("/stats")
async def get_stock_master_stats():
    """stock_master 집계 — count_all / bfdy_clpr_present / nxt_tradable_count / top_10_recent."""
    data = await stock_master.get_stats()
    return ApiResponse(success=True, data=data, message="")


# 사이클 128 — 억원 단위 → 원 단위 변환 헬퍼 (T-2 단위 변환 캡슐화 의무)
# 프론트 input 은 억원 단위 (운영자 친숙) / 백엔드 list_paged_by_filter 는 원 단위.
_HUNDRED_MILLION = 100_000_000  # 1억 원


def _eok_to_won(eok: int | None) -> int:
    """억원 → 원 변환. None 또는 0 이면 0 (무필터)."""
    if not eok or eok <= 0:
        return 0
    return int(eok) * _HUNDRED_MILLION


@router.get("/list")
async def list_stock_master(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    market: str | None = Query(None, description="KOSPI | KOSDAQ | None (전체)"),
    min_market_cap: int = Query(0, ge=0, description="최소 시가총액 (억원). 0=무필터"),
    min_trade_amount: int = Query(0, ge=0, description="최소 거래대금 (억원). 0=무필터"),
    name_substr: str | None = Query(None, description="종목명 부분 문자열 (대소문자 무시)"),
):
    """stock_master 페이징 + 4 필터 list (사이클 128).

    limit ∈ [1, 1000], offset ≥ 0.

    4 필터 (모두 optional, 사이클 128 신규 — T-1 빈 필터 = 전체 영속):
    - market: "KOSPI" | "KOSDAQ" | None
    - min_market_cap: 억원 단위 (운영자 친숙 — T-2 캡슐화 헬퍼로 원 변환)
    - min_trade_amount: 억원 단위
    - name_substr: 종목명 부분 문자열 (ilike 대소문자 무시)

    응답 schema: {items, total, limit, offset} (사이클 128 — 페이지네이션 정확도).
    """
    data = await stock_master.list_paged_by_filter(
        limit=limit,
        offset=offset,
        market=market,
        min_market_cap=_eok_to_won(min_market_cap),
        min_trade_amount=_eok_to_won(min_trade_amount),
        name_substr=name_substr,
    )
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
    # 사이클 90/126/127 — POST only 경로 보호 (GET 요청이 동적 {ticker} 로 라우팅되는 경우 차단)
    _POST_ONLY_PATHS = {"refresh-universe", "basics", "daily", "refresh-progress"}
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

    사이클 90 라우팅 가드: POST only 경로는 GET 요청 시 405 (사이클 127 refresh-progress 추가).
    동적 {ticker} 가 POST only 경로 또는 정적 경로를 잡아버리는 FastAPI 라우팅 특성 영구 차단.
    """
    _POST_ONLY_PATHS = {"refresh-universe", "basics", "daily", "refresh-progress"}
    if ticker in _POST_ONLY_PATHS:
        raise HTTPException(status_code=405, detail=f"Method Not Allowed — {ticker} 은 POST only")

    data = await stock_master.get(ticker)
    if data is None:
        raise HTTPException(status_code=404, detail=f"ticker={ticker} not found")
    # StockBasics → dict 변환 (model_dump 사용)
    if hasattr(data, "model_dump"):
        return ApiResponse(success=True, data=data.model_dump(), message="")
    return ApiResponse(success=True, data=dict(data), message="")
