"""사이클 127 — 종목마스터 3 작업 (universe/basics/daily) 진행 state 메모리 dict.

fire-and-forget POST 라우트 + 5초 폴링 GET 라우트 패턴.
3 작업 모두 동일 schema 영속 (Q3=A 통일).

배경:
- 사이클 126 push 후 사용자 보고 = "기본정보 새로고침" 클릭 → 13분 39초 후
  토스트 "KIS API 일시 결함 — 잠시 후 재시도". 운영 로그 = 백엔드 정상 완료
  (updated=2697/2697). 진짜 결함 = axios 클라이언트 디폴트 timeout silent 결함.
- 사용자 결정 Q1=A 5초 폴링 + Q2=A 상단 배너+카운터 + Q3=A 3 작업 통일.

매매 안전성 무영향:
- scanner 단계 매수 진입 *전* 영역만 변경.
- src/engine/risk.py / src/engine/order_engine.py / src/realtime/ / src/auth/ 변경 0.
- 매도/익일청산/15:20 강제청산/손절 hot path 무관.
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속.

영속 의무:
- uvicorn 단일 워커 필수 (CLAUDE.md "절대 깨지 말 것") — process-local in-memory state 영속.
- KST timestamp `_kst.now_kst_iso()` 사용 (사이클 68 G-10b AST 영속).
- thread-safety: threading.Lock 영속 (FastAPI 동시 요청 + asyncio.create_task race 차단).
"""

from __future__ import annotations

import copy
import threading
import time
from typing import Literal

from src.db._kst import now_kst_iso

ProgressStatus = Literal["idle", "running", "completed", "failed"]
TaskKey = Literal["universe", "basics", "daily"]

# 작업 키 영속 (사이클 90 universe + 사이클 126 basics/daily 통일).
TASK_KEYS: tuple[TaskKey, ...] = ("universe", "basics", "daily")

# 진행 state schema 영속 (10 키, deep copy 보호).
_INITIAL_STATE: dict = {
    "status": "idle",
    "total": 0,
    "processed": 0,
    "updated": 0,
    "skipped": 0,
    "failed": 0,
    "started_at": None,
    "finished_at": None,
    "elapsed_ms": 0,
    "error_message": None,
}

# Thread-safety: FastAPI 동시 요청 + asyncio.create_task race 차단.
_state_lock = threading.Lock()

# Process-local in-memory state (uvicorn 단일 워커 필수).
_progress: dict[str, dict] = {key: copy.deepcopy(_INITIAL_STATE) for key in TASK_KEYS}

# elapsed_ms 계산용 — start_progress 시 monotonic 기록.
_started_at_monotonic: dict[str, float] = {key: 0.0 for key in TASK_KEYS}


def _validate_task_key(task_key: str) -> None:
    """task_key 검증 (TASK_KEYS 외 ValueError)."""
    if task_key not in TASK_KEYS:
        raise ValueError(
            f"Invalid task_key={task_key!r}. Must be one of {TASK_KEYS}"
        )


def start_progress(task_key: str, total: int = 0) -> None:
    """작업 시작 시 호출. 기존 state 초기화 + status=running.

    Args:
        task_key: "universe" | "basics" | "daily"
        total: 처리할 총 ticker 개수 (페이징 후 갱신 가능, 디폴트 0)
    """
    _validate_task_key(task_key)
    now_iso = now_kst_iso()
    now_mono = time.monotonic()
    with _state_lock:
        _progress[task_key] = {
            "status": "running",
            "total": int(total),
            "processed": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "started_at": now_iso,
            "finished_at": None,
            "elapsed_ms": 0,
            "error_message": None,
        }
        _started_at_monotonic[task_key] = now_mono


def update_progress(task_key: str, **kwargs) -> None:
    """페이징/배치 중간 호출. 카운터 갱신 (누적 또는 절대 갱신).

    절대 갱신 키: total / processed / updated / skipped / failed.
    호출자가 누적값을 직접 전달 의무 (race 차단 — race-safe 누적은 호출자 책임).

    Args:
        task_key: "universe" | "basics" | "daily"
        **kwargs: total / processed / updated / skipped / failed 중 일부
    """
    _validate_task_key(task_key)
    allowed = {"total", "processed", "updated", "skipped", "failed"}
    with _state_lock:
        state = _progress[task_key]
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            try:
                state[key] = int(value)
            except (TypeError, ValueError):
                continue


def finish_progress(
    task_key: str,
    status: ProgressStatus,
    *,
    error_message: str | None = None,
    **kwargs,
) -> None:
    """완료/실패 시 호출. finished_at + elapsed_ms 자동 계산.

    Args:
        task_key: "universe" | "basics" | "daily"
        status: "completed" | "failed"
        error_message: status="failed" 시 사유 메시지 (옵션)
        **kwargs: 최종 카운터 갱신 (total/processed/updated/skipped/failed)
    """
    _validate_task_key(task_key)
    if status not in ("completed", "failed"):
        raise ValueError(
            f"Invalid status={status!r}. Must be 'completed' or 'failed'"
        )
    now_iso = now_kst_iso()
    now_mono = time.monotonic()
    allowed = {"total", "processed", "updated", "skipped", "failed"}
    with _state_lock:
        state = _progress[task_key]
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            try:
                state[key] = int(value)
            except (TypeError, ValueError):
                continue
        state["status"] = status
        state["finished_at"] = now_iso
        started_mono = _started_at_monotonic.get(task_key, 0.0)
        if started_mono > 0.0:
            state["elapsed_ms"] = max(0, int((now_mono - started_mono) * 1000))
        if error_message is not None:
            state["error_message"] = str(error_message)[:500]  # cap


def get_progress(task_key: str) -> dict:
    """단일 작업 state 조회 (deep copy 반환, 외부 mutation 차단)."""
    _validate_task_key(task_key)
    with _state_lock:
        return copy.deepcopy(_progress[task_key])


def get_all_progress() -> dict[str, dict]:
    """3 작업 통합 state 조회 (GET /refresh-progress 응답)."""
    with _state_lock:
        return {key: copy.deepcopy(_progress[key]) for key in TASK_KEYS}


def is_running(task_key: str) -> bool:
    """409 Conflict 판정용 — running 상태 여부."""
    _validate_task_key(task_key)
    with _state_lock:
        return _progress[task_key]["status"] == "running"


def reset_progress(task_key: str) -> None:
    """테스트 전용 — state 초기화 (production 호출 금지)."""
    _validate_task_key(task_key)
    with _state_lock:
        _progress[task_key] = copy.deepcopy(_INITIAL_STATE)
        _started_at_monotonic[task_key] = 0.0


def reset_all_progress() -> None:
    """테스트 전용 — 3 작업 모두 초기화."""
    with _state_lock:
        for key in TASK_KEYS:
            _progress[key] = copy.deepcopy(_INITIAL_STATE)
            _started_at_monotonic[key] = 0.0
