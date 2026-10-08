"""거래일지 워커 상수(cycle412 계약 3.1절). jw/ 안에서 이 모듈 하나만 숫자·경로 리터럴을 쥔다."""
from __future__ import annotations

BASE_URL = "http://backend:8000"
G0_PATH = "/api/trading/status?include=system,holdings,strategies"
G1_PATH = "/api/balance/exit-lines"
ALLOWED_PATHS = frozenset({G0_PATH, G1_PATH})

CYCLE_SECONDS = 15
IDLE_CYCLE_SECONDS = 300
BACKOFF_MAX_SECONDS = 300

MAX_READ_BYTES = 4 * 1024 * 1024

SIGNAL_RING_TTL_SECONDS = 600
REASON_WINDOW_SECONDS = 10
BUY_SIGNAL_LOG_WINDOW_SECONDS = 5

LOG_DIR = "/app/logs"
LOG_FILE = "auto_stock.log"

RECONCILE_MIN_AGE_SECONDS = 120

BACKFILL_MAX_BYTES_PER_SEC = 5 * 1024 * 1024
