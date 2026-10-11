"""청산 AI 섀도 워커 상수(cycle446 설계 §1~§4). `lw/` 안에서 이 모듈 하나만 숫자·경로 리터럴을 쥔다."""
from __future__ import annotations

BASE_URL = "http://backend:8000"
G0_PATH = "/api/trading/status?include=system,holdings,strategies"
G1_PATH = "/api/balance/exit-lines"
ALLOWED_PATHS = frozenset({G0_PATH, G1_PATH})

# 설계 §2.1 — 멀티데이 보유 전략 5개. 명시 목록(명부 칸으로 판정하지 않는 이유 = 설계 §2.1).
EXIT_AI_STRATEGIES = frozenset({
    "donchian_swing", "kojiro", "vcp_breakout", "bull_flag_breakout", "etf_trend",
})

# 하루 세 번(KST) — 08:15 1차, 08:35·08:55 재시도(provisional_bar·failed 행만).
RUN_TIMES_KST = ("08:15:00", "08:35:00", "08:55:00")
MAX_ATTEMPTS_PER_DAY = 3
DAILY_CALL_CAP = 40

# 확정 판정 — 헤드 봉은 오늘 06:00 KST, 그 전 봉은 (bas_dd+1일) 06:00 KST(daily_bar_finalize 와 같은 규칙).
FINAL_BOUNDARY_HOUR_KST = 6

BAR_FETCH_DAYS = 60
PROMPT_BAR_COUNT = 30

EXIT_AI_MODEL_DEFAULT = "gpt-6-luna"
MAX_COMPLETION_TOKENS = 2000
CALL_TIMEOUT_SECS = 30

MARKET_PROXY_TICKER = "069500"
