"""FastAPI 앱 엔트리포인트."""

from __future__ import annotations

import logging
import logging.handlers
import os
import time
import tracemalloc
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

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
# logger.info() 호출이 동기 supabase INSERT를 직접 트리거하면 호출자가 블로킹된다.
# 단일 워커 ThreadPoolExecutor에 fire-and-forget으로 위임 → logger 호출은 즉시 반환.
_LOG_DB_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="db-log")

# 사이클 72 hotfix — 500ms TTL dedupe 캐시 (옵션 D).
# 동일 메시지가 logger.* 경로로 500ms 내 중복 emit 되면 두 번째 INSERT skip.
# 옵션 A' (write_log 호출 제거) 와 함께 이중 INSERT 안전망 역할.
_DEDUPE_TTL_SECS = 0.5  # 500ms 동일 메시지 dedupe


def _insert_log_to_db(level: str, message: str) -> None:
    try:
        from src.db.supabase import supabase
        supabase.table("system_logs").insert({
            "log_level": level,
            "message": message,
            "timestamp": datetime.now(KST).isoformat(),  # 사이클 65 hotfix H2-bis — KST 강제 (사이클 53 패턴)
        }).execute()
    except Exception:
        pass  # DB 기록 실패는 무시 (무한 재귀 방지)


class _DbLogHandler(logging.Handler):
    """로그를 Supabase system_logs 테이블에 비동기로 기록한다(executor 위임).

    사이클 72 hotfix — 500ms TTL dedupe 캐시 (옵션 D):
    동일 메시지가 500ms 내 중복 emit 되면 두 번째는 INSERT skip.
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
            # 500ms TTL dedupe — 동일 메시지 중복 INSERT 차단
            last = self._dedupe_cache.get(message)
            now = time.monotonic()
            if last is not None and (now - last) < _DEDUPE_TTL_SECS:
                return  # 중복 INSERT 차단
            # 캐시 저장 — 현재 시각 재측정 (dedupe 비교 후 시점 기록)
            self._dedupe_cache[message] = time.monotonic()
            # lazy evict — TTL 경과 항목 정리 (~100 항목 cap, 메모리 폭주 차단)
            if len(self._dedupe_cache) > 100:
                evict_now = time.monotonic()
                self._dedupe_cache = {
                    k: v for k, v in self._dedupe_cache.items()
                    if (evict_now - v) < _DEDUPE_TTL_SECS
                }
            _LOG_DB_EXECUTOR.submit(_insert_log_to_db, record.levelname, message)
        except RuntimeError:
            pass  # 인터프리터 셧다운 중 등 executor 사용 불가 시 무시

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

    # 자동 매매 시작 (DB 설정 기준)
    try:
        from src.db.supabase import supabase as _sb
        _auto = _sb.table("system_config").select("value").eq("key", "auto_start").execute()
        raw = _auto.data[0]["value"] if _auto.data else False
        auto_start = raw is True or raw == "true"
    except Exception:
        auto_start = settings.auto_start  # DB 조회 실패 시 .env 폴백

    if auto_start:
        import asyncio
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
