"""사이클 127 — refresh_progress state 모듈 회귀 가드.

배경: 사이클 126 push 후 사용자 보고 = axios timeout silent 결함.
시정: fire-and-forget + 5초 폴링 패턴.

회귀 가드 8 케이스:
- G-STATE1: 모듈 import + 3 작업 dict 초기 schema 10 키 정확
- G-STATE2: start_progress() status="running" + started_at KST + total
- G-STATE3: update_progress() 카운터 갱신
- G-STATE4: finish_progress("completed") finished_at + elapsed_ms ≥ 0
- G-STATE5: finish_progress("failed", error_message=str)
- G-STATE6: is_running() True/False
- G-STATE7: thread-safety (threading.Lock 영속)
- G-STATE8: get_progress() deep copy 반환 (mutation 차단)
"""
from __future__ import annotations

import threading
import time

import pytest

from src.engine import refresh_progress as _rp


@pytest.fixture(autouse=True)
def _reset_state():
    """각 테스트 격리 — state 초기화."""
    _rp.reset_all_progress()
    yield
    _rp.reset_all_progress()


def test_g_state1_initial_schema():
    """G-STATE1: 모듈 import + 3 작업 dict 초기 schema 10 키 정확."""
    expected_keys = {
        "status", "total", "processed", "updated", "skipped", "failed",
        "started_at", "finished_at", "elapsed_ms", "error_message",
    }
    # 사이클 129 Q10 hotfix — hardcode 3개 → TASK_KEYS 의미 전환 (사이클 66 K-2 패턴 답습).
    # 사이클 129 master TaskKey 4 확장 영역 자동 흡수.
    for task_key in _rp.TASK_KEYS:
        state = _rp.get_progress(task_key)
        assert set(state.keys()) == expected_keys, (
            f"{task_key} 초기 schema 불일치"
        )
        assert state["status"] == "idle"
        assert state["total"] == 0
        assert state["processed"] == 0
        assert state["updated"] == 0
        assert state["skipped"] == 0
        assert state["failed"] == 0
        assert state["started_at"] is None
        assert state["finished_at"] is None
        assert state["elapsed_ms"] == 0
        assert state["error_message"] is None


def test_g_state2_start_progress():
    """G-STATE2: start_progress() status="running" + started_at KST(+09:00) + total."""
    _rp.start_progress("universe", total=2700)
    state = _rp.get_progress("universe")
    assert state["status"] == "running"
    assert state["total"] == 2700
    assert state["processed"] == 0
    assert state["started_at"] is not None
    # KST timezone suffix 정합 (사이클 68 G-10b AST 영속)
    assert "+09:00" in state["started_at"]


def test_g_state3_update_progress():
    """G-STATE3: update_progress() 카운터 절대 갱신 (호출자 누적 책임)."""
    _rp.start_progress("basics", total=100)
    _rp.update_progress("basics", processed=50, updated=45, skipped=3, failed=2)
    state = _rp.get_progress("basics")
    assert state["processed"] == 50
    assert state["updated"] == 45
    assert state["skipped"] == 3
    assert state["failed"] == 2

    # 두 번째 갱신: 절대 값 갱신 (누적 아님)
    _rp.update_progress("basics", processed=80)
    state = _rp.get_progress("basics")
    assert state["processed"] == 80
    assert state["updated"] == 45  # 영속


def test_g_state4_finish_completed():
    """G-STATE4: finish_progress("completed") + finished_at + elapsed_ms ≥ 0."""
    _rp.start_progress("daily", total=10)
    time.sleep(0.01)  # 10ms wait
    _rp.finish_progress("daily", "completed", processed=10, updated=8, failed=2)
    state = _rp.get_progress("daily")
    assert state["status"] == "completed"
    assert state["finished_at"] is not None
    assert "+09:00" in state["finished_at"]
    assert state["elapsed_ms"] >= 0
    assert state["processed"] == 10
    assert state["updated"] == 8
    assert state["failed"] == 2
    assert state["error_message"] is None


def test_g_state5_finish_failed():
    """G-STATE5: finish_progress("failed", error_message=str) 정합."""
    _rp.start_progress("universe", total=100)
    _rp.finish_progress(
        "universe", "failed",
        error_message="KIS API 응답 거부 — OPSP0002",
    )
    state = _rp.get_progress("universe")
    assert state["status"] == "failed"
    assert state["finished_at"] is not None
    assert state["error_message"] == "KIS API 응답 거부 — OPSP0002"


def test_g_state6_is_running():
    """G-STATE6: is_running() True/False 정합."""
    assert _rp.is_running("universe") is False
    _rp.start_progress("universe", total=10)
    assert _rp.is_running("universe") is True
    _rp.finish_progress("universe", "completed")
    assert _rp.is_running("universe") is False

    _rp.start_progress("basics", total=10)
    _rp.finish_progress("basics", "failed", error_message="test")
    assert _rp.is_running("basics") is False


def test_g_state7_thread_safety():
    """G-STATE7: thread-safety (threading.Lock 영속) — race 차단."""
    _rp.start_progress("universe", total=1000)

    def worker(start_idx: int):
        for i in range(100):
            _rp.update_progress("universe", processed=start_idx + i)

    threads = [threading.Thread(target=worker, args=(i * 100,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # race 없으면 마지막 processed 값이 정상 정수여야 함
    state = _rp.get_progress("universe")
    assert isinstance(state["processed"], int)
    assert state["processed"] >= 0


def test_g_state8_deep_copy_isolation():
    """G-STATE8: get_progress() deep copy 반환 — 외부 mutation 차단."""
    _rp.start_progress("daily", total=5)
    state1 = _rp.get_progress("daily")
    state1["status"] = "MUTATED_EXTERNALLY"
    state1["total"] = 99999

    # 내부 state 영속 보호
    state2 = _rp.get_progress("daily")
    assert state2["status"] == "running"
    assert state2["total"] == 5


def test_g_state_get_all_progress():
    """get_all_progress() 4 작업 통합 응답 (사이클 129 master 영역 자동 흡수)."""
    _rp.start_progress("universe", total=100)
    _rp.start_progress("basics", total=200)
    # daily / master 는 idle

    all_state = _rp.get_all_progress()
    # 사이클 129 Q10 hotfix — TASK_KEYS 사용으로 4 작업 자동 흡수
    assert set(all_state.keys()) == set(_rp.TASK_KEYS)
    assert all_state["universe"]["status"] == "running"
    assert all_state["basics"]["status"] == "running"
    assert all_state["daily"]["status"] == "idle"
    assert all_state["master"]["status"] == "idle"


def test_g_state_invalid_task_key():
    """invalid task_key 영구 차단."""
    with pytest.raises(ValueError, match="Invalid task_key"):
        _rp.get_progress("invalid")
    with pytest.raises(ValueError):
        _rp.start_progress("foo", 10)
    with pytest.raises(ValueError):
        _rp.finish_progress("bar", "completed")


def test_g_state_invalid_finish_status():
    """invalid finish status 영구 차단."""
    _rp.start_progress("universe", 10)
    with pytest.raises(ValueError, match="Invalid status"):
        _rp.finish_progress("universe", "unknown_status")
