"""사이클 193 (2026-07-04) Red — 재시작 immediate run 신선도 게이트.

`src/engine/task_loop_helper.py::run_periodic_task_loop` 에
`immediate_skip_if_fresh_hours: float | None = None` 파라미터 신설:
- 지정 시 immediate_first_run 블록에서 `src.db.system_config.get_task_last_success(task_label)`
  마커가 N시간 이내면 immediate once() **skip** (정기 while 루프는 무관 발화).
- once() 성공 직후(immediate + while 양쪽) `set_task_last_success(task_label, KST iso)` 기록
  (try/except graceful).
- **미지정(None) = 기존 행위 완전 동일** (마커 조회/기록 0건, 신규 DB 접근 0).

배경 = 7/3 15:40 재시작 실측 basics 풀런 17분 + master 4분 즉시 실행 → 16:00~16:30 정기분
이중 실행 + 아침 07:50 boot 프리마켓 Supabase burst (187 잔존 read 실패 33건/일 공통 뿌리).
사이클 188 정기 발화 복원 후엔 데이터 신선한데도 무조건 풀런.

설계 메모: `_workspace/red/cycle193_immediate_run_freshness_gate.md`.

Red 유효성 (현재 코드 = `immediate_skip_if_fresh_hours` 파라미터 미존재):
- F-1/2/3/4/5/7/8/9: 파라미터 전달 → TypeError → FAIL (Red).
- F-6: 파라미터 미전달 = 기존 행위 → 마커 호출 0건 (불변식, Red PASS).

테스트 격리 (지시서 — freezegun 금지, 사이클 187 asyncio 결합 교훈):
- fake scheduler (`_running` 토글 + `_wait_until` mock) + once mock.
- 마커는 `datetime.now(KST) - timedelta(hours=X)` 합성.
- task_loop_helper lazy import (`from src.db.system_config import ...`) → patch 대상 =
  `src.db.system_config.<함수>` (create=True, Green 후 존재).
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db._kst import KST
from src.engine.task_loop_helper import run_periodic_task_loop

pytestmark = pytest.mark.unit

_SCHED_LOGGER = "src.engine.scheduler"


# ──────────────────────────────────────────────────────────────────────
# fixtures / helpers
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _no_sleep():
    """task_loop_helper asyncio.sleep 무력화 — stagger/retry 실지연 0."""
    with patch("src.engine.task_loop_helper.asyncio.sleep", new_callable=AsyncMock):
        yield


class FakeScheduler:
    """`_running` 토글 + `_wait_until` mock 최소 scheduler (사이클 134/188 답습)."""

    def __init__(self, running: bool = False):
        self._running = running
        self.wait_calls = 0

    async def _wait_until(self, target_time, *, advance_if_passed: bool = False) -> None:
        self.wait_calls += 1
        return None


def _iso_hours_ago(hours: float) -> str:
    return (datetime.now(KST) - timedelta(hours=hours)).isoformat()


def _iso_hours_future(hours: float) -> str:
    return (datetime.now(KST) + timedelta(hours=hours)).isoformat()


async def _invoke_with_gate(
    scheduler: FakeScheduler,
    once_mock,
    *,
    get_mock,
    set_mock,
    hours: float,
    immediate: bool = True,
    label: str = "full_universe_load",
) -> None:
    """게이트 파라미터 명시 호출 (F-1..5/7/8/9 — Red 시 TypeError)."""
    with patch(
        "src.db.system_config.get_task_last_success", get_mock, create=True
    ), patch(
        "src.db.system_config.set_task_last_success", set_mock, create=True
    ):
        await run_periodic_task_loop(
            scheduler=scheduler,
            task_label=label,
            wait_time=time(16, 0),
            once_callable=once_mock,
            record_fn=MagicMock(),
            flush_fn=MagicMock(),
            summary_log_format="[test] total=%d",
            summary_keys=("total",),
            immediate_first_run=immediate,
            immediate_skip_if_fresh_hours=hours,
        )


# ──────────────────────────────────────────────────────────────────────
# F-1 (HIGH) — fresh 마커 (now-10h, hours=20) → immediate once() skip
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_F1_fresh_marker_skips_immediate_once(caplog):
    """fresh 마커 (10h < 20h) → immediate once() 미호출 + skip INFO + set 미호출.

    _running=False → while 루프 미발화 (immediate 블록 격리).
    """
    scheduler = FakeScheduler(running=False)
    once_mock = AsyncMock(return_value={"total": 0})
    get_mock = AsyncMock(return_value=_iso_hours_ago(10))
    set_mock = AsyncMock(return_value=None)

    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        await _invoke_with_gate(
            scheduler, once_mock, get_mock=get_mock, set_mock=set_mock, hours=20.0
        )

    assert once_mock.await_count == 0, "fresh 마커 → immediate once() skip 의무 (Red FAIL)"
    assert set_mock.await_count == 0, "skip 시 성공 마커 기록 없음 (once 미실행)"
    assert "skip" in caplog.text and "full_universe_load" in caplog.text, (
        "immediate run skip INFO 발화 의무 (fresh last_success)"
    )


# ──────────────────────────────────────────────────────────────────────
# F-2 (HIGH) — stale 마커 (now-30h, hours=20) → immediate once() 호출 (catch-up)
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_F2_stale_marker_runs_immediate_once():
    """stale 마커 (30h > 20h) → immediate once() 호출 (catch-up 보존) + set 기록."""
    scheduler = FakeScheduler(running=False)
    once_mock = AsyncMock(return_value={"total": 3})
    get_mock = AsyncMock(return_value=_iso_hours_ago(30))
    set_mock = AsyncMock(return_value=None)

    await _invoke_with_gate(
        scheduler, once_mock, get_mock=get_mock, set_mock=set_mock, hours=20.0
    )

    assert once_mock.await_count == 1, "stale 마커 → immediate once() 실행 의무 (catch-up)"
    assert set_mock.await_count == 1, "once 성공 → 성공 마커 기록 의무"


# ──────────────────────────────────────────────────────────────────────
# F-3 — 마커 None → 실행
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_F3_none_marker_runs_immediate():
    """마커 부재 (최초 배포/DB 초기화) → immediate once() 실행 (안전 방향)."""
    scheduler = FakeScheduler(running=False)
    once_mock = AsyncMock(return_value={"total": 0})
    get_mock = AsyncMock(return_value=None)
    set_mock = AsyncMock(return_value=None)

    await _invoke_with_gate(
        scheduler, once_mock, get_mock=get_mock, set_mock=set_mock, hours=20.0
    )

    assert once_mock.await_count == 1, "마커 None → immediate 실행 의무"


# ──────────────────────────────────────────────────────────────────────
# F-4 — 조회 예외 → 실행 (graceful)
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_F4_query_exception_runs_immediate():
    """마커 조회 예외 → graceful → immediate once() 실행 (catch-up 보존)."""
    scheduler = FakeScheduler(running=False)
    once_mock = AsyncMock(return_value={"total": 0})
    get_mock = AsyncMock(side_effect=RuntimeError("supabase down"))
    set_mock = AsyncMock(return_value=None)

    await _invoke_with_gate(
        scheduler, once_mock, get_mock=get_mock, set_mock=set_mock, hours=20.0
    )

    assert once_mock.await_count == 1, "조회 예외 → graceful 실행 의무 (예외 전파 금지)"


# ──────────────────────────────────────────────────────────────────────
# F-5 — 파싱 불가 문자열 → 실행
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_F5_unparseable_marker_runs_immediate():
    """파싱 불가 마커 문자열 → 실행 (안전 방향)."""
    scheduler = FakeScheduler(running=False)
    once_mock = AsyncMock(return_value={"total": 0})
    get_mock = AsyncMock(return_value="not-a-timestamp")
    set_mock = AsyncMock(return_value=None)

    await _invoke_with_gate(
        scheduler, once_mock, get_mock=get_mock, set_mock=set_mock, hours=20.0
    )

    assert once_mock.await_count == 1, "파싱 불가 마커 → immediate 실행 의무"


# ──────────────────────────────────────────────────────────────────────
# F-6 (HIGH, 회귀 보존) — 파라미터 미지정 → 마커 조회/기록 0건 + 기존 immediate 동작
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_F6_no_param_no_marker_access():
    """`immediate_skip_if_fresh_hours` 미지정 → get/set 마커 호출 0건 + 기존 immediate 실행.

    Red PASS (불변식) — 현재 코드도 마커 로직 부재 → 마커 접근 0.
    Green 후에도 None 경로는 신규 DB 접근 0 유지 의무.
    """
    scheduler = FakeScheduler(running=False)
    once_mock = AsyncMock(return_value={"total": 0})
    get_mock = AsyncMock(return_value=_iso_hours_ago(1))  # fresh 여도 무시 (미지정)
    set_mock = AsyncMock(return_value=None)

    with patch(
        "src.db.system_config.get_task_last_success", get_mock, create=True
    ), patch(
        "src.db.system_config.set_task_last_success", set_mock, create=True
    ):
        await run_periodic_task_loop(
            scheduler=scheduler,
            task_label="full_universe_load",
            wait_time=time(16, 0),
            once_callable=once_mock,
            record_fn=MagicMock(),
            flush_fn=MagicMock(),
            summary_log_format="[test] total=%d",
            summary_keys=("total",),
            immediate_first_run=True,
            # immediate_skip_if_fresh_hours 미지정 = 기존 행위
        )

    assert once_mock.await_count == 1, "미지정 → 기존 immediate 실행 (회귀 보존)"
    assert get_mock.await_count == 0, "미지정 → 마커 조회 0건 (신규 DB 접근 0)"
    assert set_mock.await_count == 0, "미지정 → 마커 기록 0건 (신규 DB 접근 0)"


# ──────────────────────────────────────────────────────────────────────
# F-7a — once() 성공 → set_task_last_success(label, KST iso) 호출
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_F7a_success_records_marker_with_kst_iso():
    """immediate once() 성공 → set_task_last_success(task_label, KST iso) 호출."""
    scheduler = FakeScheduler(running=False)
    once_mock = AsyncMock(return_value={"total": 5})
    get_mock = AsyncMock(return_value=None)  # 실행 유도
    set_mock = AsyncMock(return_value=None)

    await _invoke_with_gate(
        scheduler,
        once_mock,
        get_mock=get_mock,
        set_mock=set_mock,
        hours=20.0,
        label="stock_master_basics_refresh",
    )

    assert set_mock.await_count == 1, "once 성공 → 마커 기록 1회 의무"
    call = set_mock.await_args
    assert call.args[0] == "stock_master_basics_refresh", "task_label 전달 의무"
    iso = call.args[1]
    assert isinstance(iso, str) and "+09:00" in iso, (
        f"KST iso (+09:00 suffix) 기록 의무 (실측 {iso!r})"
    )


# ──────────────────────────────────────────────────────────────────────
# F-7b — 마커 기록 실패 → 루프 정상 지속 (graceful)
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_F7b_marker_record_failure_graceful():
    """set_task_last_success 예외 → graceful (예외 전파 금지, 다음 부팅 immediate 실행 안전)."""
    scheduler = FakeScheduler(running=False)
    once_mock = AsyncMock(return_value={"total": 0})
    get_mock = AsyncMock(return_value=None)
    set_mock = AsyncMock(side_effect=RuntimeError("upsert failed"))

    # 예외 전파 없이 완료되어야 함
    await _invoke_with_gate(
        scheduler, once_mock, get_mock=get_mock, set_mock=set_mock, hours=20.0
    )

    assert once_mock.await_count == 1, "once 실행 완료"
    assert set_mock.await_count == 1, "마커 기록 시도 (실패 graceful 흡수)"


# ──────────────────────────────────────────────────────────────────────
# F-8 (HIGH) — 정기 while 루프 발화는 fresh 마커여도 once() 실행 (skip 은 immediate 한정)
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_F8_periodic_loop_fires_despite_fresh_marker():
    """fresh 마커 → immediate skip 되나 정기 while 루프는 once() 발화 (skip 은 immediate 한정).

    사이클 188 복원한 정기 발화를 게이트가 다시 막으면 안 됨 — HIGH 가드.
    _running=True + once side_effect 로 while 1회 발화 후 종료.
    """
    scheduler = FakeScheduler(running=True)

    async def _once_side_effect():
        # while 루프 1회 발화 후 종료
        scheduler._running = False
        return {"total": 1}

    once_mock = AsyncMock(side_effect=_once_side_effect)
    get_mock = AsyncMock(return_value=_iso_hours_ago(1))  # fresh → immediate skip
    set_mock = AsyncMock(return_value=None)

    await _invoke_with_gate(
        scheduler, once_mock, get_mock=get_mock, set_mock=set_mock, hours=20.0
    )

    # immediate 는 fresh 로 skip → once() 는 while 루프에서만 1회 발화
    assert once_mock.await_count == 1, (
        "정기 while 루프는 fresh 마커여도 once() 발화 의무 (skip 은 immediate 한정, 사이클 188 영속)"
    )
    assert scheduler.wait_calls >= 1, "while 루프 _wait_until 발화 (정기 진입 확인)"


# ──────────────────────────────────────────────────────────────────────
# F-9 — 미래 시각 마커 → 실행 (음수 경과 방어)
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_F9_future_marker_runs_immediate():
    """미래 시각 마커 (시계 이상) → 음수 경과 = fresh 오판 금지 → 실행 (0 <= elapsed < hours)."""
    scheduler = FakeScheduler(running=False)
    once_mock = AsyncMock(return_value={"total": 0})
    get_mock = AsyncMock(return_value=_iso_hours_future(5))  # now + 5h
    set_mock = AsyncMock(return_value=None)

    await _invoke_with_gate(
        scheduler, once_mock, get_mock=get_mock, set_mock=set_mock, hours=20.0
    )

    assert once_mock.await_count == 1, (
        "미래 마커 → 음수 경과 방어 → immediate 실행 의무 (fresh 오판 금지)"
    )
