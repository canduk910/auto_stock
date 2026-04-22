"""FastAPI 앱 엔트리포인트."""

import logging
import logging.handlers
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.routes import trading, balance, history, performance, logs
from src.auth.token import token_manager

# --- 로깅 설정 ---
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 루트 로거 설정
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

# 콘솔 핸들러 (INFO 이상)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
root_logger.addHandler(console_handler)

# 파일 핸들러 — 일별 로테이션, 30일 보관
file_handler = logging.handlers.TimedRotatingFileHandler(
    filename=os.path.join(LOG_DIR, "auto_stock.log"),
    when="midnight",
    interval=1,
    backupCount=30,
    encoding="utf-8",
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
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
error_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
error_handler.suffix = "%Y-%m-%d"
root_logger.addHandler(error_handler)

# DB 로그 핸들러 — src.* 모듈의 INFO 이상 로그를 system_logs 테이블에 기록
class _DbLogHandler(logging.Handler):
    """로그를 Supabase system_logs 테이블에 비동기로 기록한다."""

    def emit(self, record: logging.LogRecord) -> None:
        if not record.name.startswith("src."):
            return
        try:
            from src.db.supabase import supabase
            supabase.table("system_logs").insert({
                "log_level": record.levelname,
                "message": f"[{record.name}] {record.getMessage()}"[:500],
            }).execute()
        except Exception:
            pass  # DB 기록 실패는 무시 (무한 재귀 방지)

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
    logger.info("=== 서버 시작 (env=%s, port=%s) ===", settings.kis_env, settings.port)
    try:
        await token_manager.get_token()
        logger.info("KIS 토큰 발급 완료")
    except Exception:
        logger.exception("KIS 토큰 발급 실패")
    yield
    logger.info("=== 서버 종료 ===")
    try:
        await token_manager.revoke()
    except Exception:
        logger.exception("토큰 폐기 실패")


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


app.include_router(trading.router)
app.include_router(balance.router)
app.include_router(history.router)
app.include_router(performance.router)
app.include_router(logs.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.kis_env}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host=settings.host, port=settings.port, reload=True)
