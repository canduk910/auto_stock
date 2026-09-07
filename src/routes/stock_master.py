"""stock_master READ-ONLY 라우트 (사이클 84) + 수동 trigger (사이클 90/126/129) + 진행 폴링 (사이클 127) + 헬퍼 추출 (사이클 131).

7 GET 엔드포인트 (Q9=B 결정, L-2 AST 영구 가드):
- GET /api/stock-master/stats
- GET /api/stock-master/list
- GET /api/stock-master/scan-pool/summary
- GET /api/stock-master/refresh-progress  ← 사이클 127 신규 (5초 폴링)
- GET /api/stock-master/{ticker}/history
- GET /api/stock-master/{ticker}/daily  ← 사이클 124 신규
- GET /api/stock-master/{ticker}

4 POST 엔드포인트 (사이클 90/126/129 화이트리스트 + 사이클 127 fire-and-forget + 사이클 131 헬퍼 dispatch):
- POST /api/stock-master/refresh-universe  ← 사이클 90 (사이클 127 fire-and-forget 전환)
- POST /api/stock-master/basics/refresh    ← 사이클 126 (사이클 127 fire-and-forget 전환)
- POST /api/stock-master/daily/refresh     ← 사이클 126 (사이클 127 fire-and-forget 전환)
- POST /api/stock-master/master/refresh    ← 사이클 129 (KIS 종목 마스터 파일 적재)

사이클 131 (2026-06-15) — 카드 #22 헬퍼 추출 + dispatch 패턴 영속:
- `_TASK_REGISTRY`: TaskKey → 메타데이터 (once_callable + log_prefix + message_template) dispatch.
- `_make_background_runner(task_key, once_callable)`: 4 wrapper try/except + finish_progress("failed") 안전망 헬퍼.
- 4 POST 라우트 본체 = state 가드 + BackgroundTasks 등록 + 응답 envelope 동일 패턴 압축.

사이클 127 (2026-06-13) — fire-and-forget + 5초 폴링 패턴:
- 사용자 보고: 13분 39초 백엔드 정상 완료 후 axios 클라이언트 디폴트 timeout silent 결함.
- POST 4 라우트 즉시 202 status + status="started" 응답 (작업 시작) + 백그라운드 task 발화.
- GET /refresh-progress 5초 폴링으로 상단 배너 + 카운터 가시화.
- asyncio.Lock 폐기 → refresh_progress.is_running() state 기반 가드 (single source of truth).
- 백그라운드 task 예외 시 finish_progress("failed") 영속 호출 (UI error_message 표시).

라우트 순서 의무: 정적 경로 (stats / list / scan-pool / refresh-* / refresh-progress) 를
동적 ({ticker}) 보다 먼저 등록.
/{ticker}/history 와 /{ticker}/daily 는 /{ticker} 보다 먼저 등록 (FastAPI LIFO 정합).
"""

from __future__ import annotations

import decimal
import logging
from typing import Awaitable, Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from src.db import stock_master
from src.db import stock_master_daily
from src.engine import refresh_progress as _rp
from src.models.response import ApiResponse

logger = logging.getLogger("src.routes.stock_master")

router = APIRouter()


# =============================================================================
# 사이클 131 — 카드 #22 헬퍼 추출 + dispatch (행위 보존 영속)
# =============================================================================


def _make_background_runner(
    task_key: str,
    once_callable: Callable[..., Awaitable[dict]],
) -> Callable[[bool], Awaitable[None]]:
    """4 동일 wrapper 패턴 헬퍼 추출 (사이클 131 카드 #22).

    행위 보존 의무 영속:
    - once_callable 내부에서 start_progress/update_progress/finish_progress 호출 영속.
    - 여기서는 예외만 catch → is_running 시 finish_progress("failed") 안전망 (사이클 88 G-REJECT 답습).
    - log prefix = task_key 기반 통일 (`[refresh_{task_key}_background]`).

    영속 의무 매트릭스:
    - 사이클 88 G-REJECT graceful 영속 (예외 → finish_progress 안전망)
    - 사이클 127 fire-and-forget BackgroundTasks 영속
    - 사이클 129 4 task_key 영속 (universe/basics/daily/master)
    """

    async def _runner(force: bool) -> None:
        try:
            await once_callable(force=force)
        except Exception as exc:
            logger.exception(
                "[refresh_%s_background] 백그라운드 실패 graceful: %s",
                task_key,
                exc,
            )
            # once 함수 내부에서 이미 finish_progress("failed") 처리됨 (안전망).
            if _rp.is_running(task_key):
                _rp.finish_progress(task_key, "failed", error_message=str(exc))

    return _runner


def _resolve_once_callable(task_key: str) -> Callable[..., Awaitable[dict]]:
    """task_key → scanner once 함수 lazy resolve (순환 import 차단)."""
    from src.engine import scanner as _scanner

    if task_key == "universe":
        return _scanner._full_universe_load_once
    if task_key == "basics":
        return _scanner._stock_master_basics_refresh_once
    if task_key == "daily":
        return _scanner._stock_master_daily_load_once
    if task_key == "master":
        return _scanner._stock_master_master_load_once
    raise ValueError(f"unknown task_key={task_key!r}")


# 4 task_key dispatch registry — 사이클 131 카드 #22 영속.
# refresh_progress.TASK_KEYS 와 정합 의무 (AST 가드 G-22-A-2 영속).
_TASK_REGISTRY: dict[str, dict] = {
    "universe": {
        "message": "universe refresh 시작 — 진행 상황은 /api/stock-master/refresh-progress 폴링",
        "conflict_detail": "universe refresh 진행 중 — 잠시 후 재시도",
    },
    "basics": {
        "message": "basics refresh 시작 — 진행 상황은 /api/stock-master/refresh-progress 폴링",
        "conflict_detail": "basics refresh 진행 중 — 잠시 후 재시도",
    },
    "daily": {
        "message": "daily refresh 시작 — 진행 상황은 /api/stock-master/refresh-progress 폴링",
        "conflict_detail": "daily refresh 진행 중 — 잠시 후 재시도",
    },
    "master": {
        "message": "master refresh 시작 — 진행 상황은 /api/stock-master/refresh-progress 폴링",
        "conflict_detail": "master refresh 진행 중 — 잠시 후 재시도",
    },
}


def _dispatch_refresh(
    task_key: str,
    background_tasks: BackgroundTasks,
    force: bool,
) -> ApiResponse:
    """4 POST 라우트 공통 dispatch (사이클 131 카드 #22 영속).

    동작 (행위 보존 의무):
    1. is_running(task_key) 시 HTTPException(409) (사이클 90 → 사이클 127 state 가드 영속).
    2. BackgroundTasks 에 runner 등록 (사이클 127 fire-and-forget — response 전송 *후* schedule).
    3. 응답 envelope `{status: "started", task_key}` 반환 (사이클 128 영속).

    사이클 84 L-2 영속: POST 4 화이트리스트 영속.
    사이클 127 G-AST4 영속: `asyncio.create_task == 0` + `background_tasks.add_task ≥ 4`.
    """
    meta = _TASK_REGISTRY[task_key]

    if _rp.is_running(task_key):
        raise HTTPException(
            status_code=409,
            detail=meta["conflict_detail"],
        )

    once_callable = _resolve_once_callable(task_key)
    runner = _make_background_runner(task_key, once_callable)
    background_tasks.add_task(runner, force=force)

    return ApiResponse(
        success=True,
        data={
            "status": "started",
            "task_key": task_key,
        },
        message=meta["message"],
    )


# =============================================================================
# POST 라우트 (4) — 사이클 131 헬퍼 dispatch (행위 보존 영속)
# =============================================================================


@router.post("/refresh-universe", response_model=ApiResponse)
async def refresh_universe_now(background_tasks: BackgroundTasks, force: bool = True):
    """사이클 90 (2026-06-09) + 사이클 127 + 사이클 131 — fire-and-forget dispatch.

    사이클 120 force 인자 영속 (UI "지금 새로고침" 디폴트 True = 즉시 검증).
    """
    return _dispatch_refresh("universe", background_tasks, force)


@router.post("/basics/refresh", response_model=ApiResponse)
async def refresh_basics_now(background_tasks: BackgroundTasks, force: bool = True):
    """사이클 126 + 사이클 127 + 사이클 131 — fire-and-forget dispatch.

    KRX 1차 폴백 시 NXT/정지/관리종목 하드코딩 False 결함을 즉시 시정.
    """
    return _dispatch_refresh("basics", background_tasks, force)


@router.post("/daily/refresh", response_model=ApiResponse)
async def refresh_daily_now(background_tasks: BackgroundTasks, force: bool = True):
    """사이클 126 + 사이클 127 + 사이클 131 — fire-and-forget dispatch.

    사이클 122 `_stock_master_daily_load_task_loop` 자동 task 와 동일 함수 호출.
    """
    return _dispatch_refresh("daily", background_tasks, force)


@router.post("/master/refresh", response_model=ApiResponse)
async def refresh_master_now(background_tasks: BackgroundTasks, force: bool = True):
    """사이클 129 + 사이클 131 — KIS 종목 마스터 파일 fire-and-forget dispatch.

    KIS 정본 (kis-mcp-query 검증):
    - KOSPI: https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip
    - KOSDAQ: https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip

    자동 task = scheduler `TIME_STOCK_MASTER_MASTER_LOAD=16:30 KST` + start() 직후 1회.
    """
    return _dispatch_refresh("master", background_tasks, force)


# =============================================================================
# GET 라우트 — READ-ONLY (사이클 84 L-2 영속)
# =============================================================================


@router.get("/refresh-progress")
async def get_refresh_progress():
    """사이클 127 + 사이클 129 — 4 작업 진행 state 통합 조회 (5초 폴링)."""
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
    """stock_master 페이징 + 4 필터 list (사이클 128)."""
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


def _daily_row_for_json(row: dict) -> dict:
    """사이클 266 A-1 — Decimal→float 새 dict 사영(원본 불변, A-1-6). 필드명 열거 금지
    (값 타입 판정, A-1-3), `raw` 재귀 변환 금지(G-AST1, A-1b), `float()` 실패는 fail-open(A-1d)."""
    def _cast(key: str, value: object) -> object:
        try:
            return float(value) if key != "raw" and isinstance(value, decimal.Decimal) else value
        except Exception:
            return value
    return {key: _cast(key, value) for key, value in row.items()}


@router.get("/{ticker}/daily")
async def get_stock_master_daily(
    ticker: str,
    days: int = Query(30, ge=1, le=100),
):
    """사이클 124 — ticker 일봉(최근 days일). 등록 순서: history→daily→{ticker} 의무.
    사이클 266 A-2 — DB 예외는 500(404 위장 금지). ⚠️F-1(지우지 말 것): `get_recent_daily`
    자신이 내부에서 이미 삼켜(db 모듈=6전략 prepare+터틀 ATR 공유, 별도승인 대상) 이 500 은
    오늘 실질 도달 불가한 계약 가드다 — db 모듈이 바뀌면 실동한다."""
    _POST_ONLY_PATHS = {"refresh-universe", "basics", "daily", "refresh-progress", "master"}
    if ticker in _POST_ONLY_PATHS:
        raise HTTPException(status_code=405, detail=f"Method Not Allowed — {ticker} 은 POST only")

    try:
        rows = await stock_master_daily.get_recent_daily(ticker=ticker, days=days)
    except Exception:
        logger.exception("[stock_master_daily_route_error] ticker=%s days=%s", ticker, days)
        raise HTTPException(500, detail=f"ticker={ticker} 일봉 조회 실패 (days={days})")

    if not rows:
        raise HTTPException(404, detail=f"ticker={ticker} 일봉 미적재 — 전략 유니버스 대상만 적재됩니다 (days={days}). 단, 서버 조회 실패도 같은 404 로 보일 수 있으니(cycle266 D-1) 로그에서 stock_master_daily 를 확인하세요")

    data = [_daily_row_for_json(row) for row in rows]
    return ApiResponse(success=True, data=data, message=f"{len(rows)}일 일봉")


@router.get("/{ticker}")
async def get_stock_master_detail(ticker: str):
    """단건 조회. 미존재 시 404.

    사이클 90 라우팅 가드: POST only 경로는 GET 요청 시 405 (사이클 127 refresh-progress + 사이클 129 master 추가).
    """
    _POST_ONLY_PATHS = {"refresh-universe", "basics", "daily", "refresh-progress", "master"}
    if ticker in _POST_ONLY_PATHS:
        raise HTTPException(status_code=405, detail=f"Method Not Allowed — {ticker} 은 POST only")

    data = await stock_master.get(ticker)
    if data is None:
        raise HTTPException(status_code=404, detail=f"ticker={ticker} not found")
    if hasattr(data, "model_dump"):
        return ApiResponse(success=True, data=data.model_dump(), message="")
    return ApiResponse(success=True, data=dict(data), message="")
