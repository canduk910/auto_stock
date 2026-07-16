"""FastAPI 앱 엔트리포인트."""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import queue
import time
import tracemalloc
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

import src.db.pg as pg

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

# KST 타임존
KST = timezone(timedelta(hours=9))
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.routes import (
    trading,
    balance,
    history,
    performance,
    logs,
    strategies,
    recommendations,
    log_reports,
    system,
    realtime,
    backtest,
    market_regime,
    strategy_funnel,
    system_integrations,
    kis_quote_accounts,
)
from src.routes.stock_master import router as stock_master_router
from src.auth.token import token_manager

# endpoint별 응답시간 샘플 (ms) — 최근 1024개. /api/system/metrics에서 p50/p95/p99 산출
_endpoint_metrics: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=1024))


class MetricsMiddleware(BaseHTTPMiddleware):
    """엔드포인트별 응답시간을 누적 측정 (PR2 측정 인프라)."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        # path templates(/api/foo/{id})로 정규화하지 않고 raw path 사용 (단순)
        path = request.url.path
        _endpoint_metrics[path].append(elapsed_ms)
        return response

# --- 로깅 설정 ---
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _KSTFormatter(logging.Formatter):
    """로그 타임스탬프를 KST(UTC+9)로 출력한다."""
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=KST)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime(DATE_FORMAT)


_formatter = _KSTFormatter(LOG_FORMAT, DATE_FORMAT)

# 루트 로거 설정
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

# 콘솔 핸들러 (INFO 이상)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(_formatter)
root_logger.addHandler(console_handler)

# 파일 핸들러 — 일별 로테이션, 30일 보관
file_handler = logging.handlers.TimedRotatingFileHandler(
    filename=os.path.join(LOG_DIR, "auto_stock.log"),
    when="midnight",
    interval=1,
    backupCount=30,
    encoding="utf-8",
    atTime=datetime.strptime("00:00", "%H:%M").time(),  # KST 자정 기준
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(_formatter)
file_handler.suffix = "%Y-%m-%d"
root_logger.addHandler(file_handler)

# 에러 전용 파일 (WARNING 이상)
error_handler = logging.handlers.TimedRotatingFileHandler(
    filename=os.path.join(LOG_DIR, "error.log"),
    when="midnight",
    interval=1,
    backupCount=30,
    encoding="utf-8",
)
error_handler.setLevel(logging.WARNING)
error_handler.setFormatter(_formatter)
error_handler.suffix = "%Y-%m-%d"
root_logger.addHandler(error_handler)

# DB 로그 핸들러 — src.* 모듈의 INFO 이상 로그를 system_logs 테이블에 기록
# 사이클 M3b — asyncpg 전환. 동기 logging.Handler.emit 은 async pg.execute 를 직접
# await 할 수 없으므로 큐 producer(non-blocking put_nowait) + lifespan 기동 async
# consumer task(큐 drain → pg.execute INSERT) 구조로 전환. ThreadPoolExecutor 폐기.
_LOG_QUEUE: "queue.Queue[tuple[str, str]]" = queue.Queue(maxsize=10_000)

# 사이클 72 hotfix — 500ms TTL dedupe 캐시 (옵션 D).
# 동일 메시지가 logger.* 경로로 500ms 내 중복 emit 되면 두 번째 INSERT skip.
# 옵션 A' (write_log 호출 제거) 와 함께 이중 INSERT 안전망 역할.
_DEDUPE_TTL_SECS = 0.5  # 500ms 동일 메시지 dedupe


async def _insert_log_to_db(level: str, message: str) -> None:
    """system_logs INSERT (pg.execute, KST datetime). never-raise — 무한 재귀 방지."""
    try:
        await pg.execute(
            "INSERT INTO system_logs (log_level, message, timestamp) VALUES ($1, $2, $3)",
            level,
            message,
            datetime.now(KST),  # 사이클 65 hotfix H2-bis — KST 강제 (사이클 53 패턴)
        )
    except Exception:
        pass  # DB 기록 실패는 무시 (무한 재귀 방지)


async def _log_queue_consumer() -> None:
    """큐 drain → `_insert_log_to_db` INSERT (lifespan 기동 백그라운드 task).

    큐가 비면 짧게 대기 후 재확인 — 폴링형 drain(단순성 우선, 로그 지연 허용).
    """
    while True:
        try:
            level, message = _LOG_QUEUE.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.1)
            continue
        try:
            await _insert_log_to_db(level, message)
        except Exception:
            pass  # never-raise — consumer 루프 보존 (사이클190)


class _DbLogHandler(logging.Handler):
    """로그를 system_logs 테이블에 큐 경유로 비동기 기록한다 (사이클 M3b — asyncpg 큐 전환).

    emit() 은 동기 non-blocking 큐 producer(`_LOG_QUEUE.put_nowait`) 역할만 수행하고,
    실제 INSERT 는 lifespan 이 기동하는 `_log_queue_consumer` async task 가 처리한다.

    사이클 72 hotfix — 500ms TTL dedupe 캐시 (옵션 D):
    동일 메시지가 500ms 내 중복 emit 되면 두 번째는 큐 적재 skip.
    옵션 A' (write_log 직접 호출 제거) 의 안전망으로 추가.
    """

    def __init__(self) -> None:
        super().__init__()
        self._dedupe_cache: dict[str, float] = {}  # message → last_emit_monotonic

    def emit(self, record: logging.LogRecord) -> None:
        if not record.name.startswith("src."):
            return
        try:
            message = f"[{record.name}] {record.getMessage()}"[:500]
            # 500ms TTL dedupe — 동일 메시지 중복 큐 적재 차단
            last = self._dedupe_cache.get(message)
            now = time.monotonic()
            if last is not None and (now - last) < _DEDUPE_TTL_SECS:
                return  # 중복 적재 차단
            # 캐시 저장 — 현재 시각 재측정 (dedupe 비교 후 시점 기록)
            self._dedupe_cache[message] = time.monotonic()
            # lazy evict — TTL 경과 항목 정리 (~100 항목 cap, 메모리 폭주 차단)
            if len(self._dedupe_cache) > 100:
                evict_now = time.monotonic()
                self._dedupe_cache = {
                    k: v for k, v in self._dedupe_cache.items()
                    if (evict_now - v) < _DEDUPE_TTL_SECS
                }
            _LOG_QUEUE.put_nowait((record.levelname, message))
        except Exception:
            pass  # never-raise (사이클190) — 큐 full/기타 예외 삼킴, WARNING 이상 미발화


_db_handler = _DbLogHandler()
_db_handler.setLevel(logging.INFO)
root_logger.addHandler(_db_handler)

# 외부 라이브러리 로그 레벨 조정
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # MEMORY_PROFILE=true이면 tracemalloc 시작 — 운영 평소엔 끔(CPU 5~10% 오버헤드)
    if os.environ.get("MEMORY_PROFILE", "").lower() in ("true", "1", "yes"):
        tracemalloc.start(25)
        logger.info("tracemalloc 활성화 (depth=25)")

    logger.info("=== 서버 시작 (env=%s, port=%s) ===", settings.kis_env, settings.port)

    # RDS(PostgreSQL) 연결 풀 — 사이클 M0. database_url 미설정 시 graceful skip.
    _log_consumer_task: "asyncio.Task | None" = None
    if settings.database_url:
        try:
            from src.db.pg import init_pool
            await init_pool()
            logger.info("RDS 연결 풀 초기화 완료")
        except Exception:
            logger.exception("RDS 연결 풀 초기화 실패")

        # 사이클 M3b — DB 로그 큐 consumer 기동 (pool 초기화 이후, pg.execute 가능 시점).
        try:
            _log_consumer_task = asyncio.create_task(_log_queue_consumer())
        except Exception:
            logger.exception("DB 로그 큐 consumer 기동 실패")

    try:
        await token_manager.get_token()
        logger.info("KIS 토큰 발급 완료")
    except Exception:
        logger.exception("KIS 토큰 발급 실패")

    # 서버 기동 시 DB에서 전략 설정 로드 (프론트에서 올바른 설정 표시)
    try:
        from src.engine.scheduler import trading_scheduler
        await trading_scheduler._load_strategy_config()
    except Exception:
        logger.warning("전략 설정 초기 로드 실패")

    # 자동 매매 시작 (DB 설정 기준) — 사이클 M3b seam ② system_config.get_auto_start() 경유.
    try:
        from src.db import system_config as _sc
        auto_start = await _sc.get_auto_start()
    except Exception:
        auto_start = settings.auto_start  # DB 조회 실패 시 .env 폴백

    if auto_start:
        from src.engine.scheduler import trading_scheduler
        logger.info("AUTO_START 활성화 — 매일 자동 매매 스케줄링")
        asyncio.create_task(trading_scheduler.run_daily())

    yield
    logger.info("=== 서버 종료 ===")
    try:
        await token_manager.revoke()
    except Exception:
        logger.exception("토큰 폐기 실패")
    # Phase 2 — MCP 클라이언트(외부 백테스트 서버) 정리. 인스턴스 미생성 시 NoOp.
    try:
        from src.services import mcp_client as _mc
        if _mc._client_instance is not None:
            await _mc._client_instance.close()
    except Exception:
        logger.exception("MCP 클라이언트 정리 실패")

    # 사이클 M3b — DB 로그 큐 consumer 정리.
    if _log_consumer_task is not None:
        _log_consumer_task.cancel()
        try:
            await _log_consumer_task
        except (asyncio.CancelledError, Exception):
            pass

    # RDS(PostgreSQL) 연결 풀 종료 — 사이클 M0.
    try:
        from src.db.pg import close_pool
        await close_pool()
    except Exception:
        logger.exception("RDS 연결 풀 종료 실패")


app = FastAPI(
    title="Auto Stock Trading System",
    description="KIS OpenAPI 기반 주식 자동매매시스템",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 응답시간 측정 미들웨어 — /api/system/metrics에서 p50/p95/p99 노출
app.add_middleware(MetricsMiddleware)


app.include_router(trading.router)
app.include_router(balance.router)
app.include_router(history.router)
app.include_router(performance.router)
app.include_router(logs.router)
app.include_router(strategies.router)
app.include_router(recommendations.router)
app.include_router(log_reports.router)
app.include_router(system.router)
app.include_router(realtime.router)
app.include_router(backtest.router)
app.include_router(market_regime.router)
app.include_router(strategy_funnel.router)
app.include_router(system_integrations.router)
app.include_router(kis_quote_accounts.router)
app.include_router(stock_master_router, prefix="/api/stock-master", tags=["stock-master"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.kis_env}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host=settings.host, port=settings.port, reload=True)
