"""cycle363 Red — 부팅 즉시 실행 「영업일 슬롯」 신선도 게이트 (①).

지시서(정본) = `_workspace/red/cycle363_business_day_freshness_spec.md` §2.2 · §2.3 · §3.1 (1)~(12).
설계 = `_workspace/domain_consult/cycle360_boot_reprepare_4a_proposal.md` §1.1 · §1.2 · §3 표 ① · §8.

판정 기준을 「몇 시간 지났나」에서 「**직전 영업일 정기 슬롯(`wait_time`) 이후** 성공 마커가
있나」로 바꾼다. 월요일·연휴 뒤 아침에 목요일(또는 그 전) KRX 값이 금요일 값을 덮는 것을 막는다.

2026-09 달력(고정 시나리오): 09-18(금) 개장 · 09-21(월)~09-23(수) 개장 ·
**09-24(목)·09-25(금) 휴장(추석)** · 09-26(토)·09-27(일) 주말 · 09-28(월) 개장.

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 계약 (이 파일이 고정한다)
────────────────────────────────────────────────────────────────────────────
1) `task_loop_helper.run_periodic_task_loop` 신규 키워드 3개
   - `immediate_skip_if_fresh_since_trading_slot: bool = False` — 슬롯 = `wait_time`
   - `immediate_force_run_check: Callable[[], Awaitable[bool]] | None = None`
   - `immediate_skip_if_marker_absent: bool = False`
   `immediate_skip_if_fresh_hours` 와 슬롯 모드 동시 지정 → 함수 진입 즉시 `ValueError`.
2) 🔴 시각 seam = `src.engine.task_loop_helper._now_kst() -> datetime` (KST aware, 모듈 전역).
   슬롯 모드의 `now` 는 **이 함수로만** 얻는다(future_marker 판정 포함). 이 파일은 그 이름을
   monkeypatch 해 시각을 고정한다 — 벽시계 독립(로컬 23:5x / CI 00:0x 같은 결과).
3) 휴장일 = `src.engine.trading_calendar.latest_passed_trading_slot(now, wait_time)`.
   헬퍼는 leaf 함수를 **호출 시점에 모듈 속성으로** 찾는다(기존 `system_config` 처럼 함수 안
   지연 import) — H7 이 그 이름을 패치한다. 이 파일은 leaf 의 조회 seam
   `src.engine.trading_calendar._lookup_open` 을 가짜 달력으로 바꿔 leaf 실로직까지 통과시킨다.
4) 슬롯 모드 판정 순서 (stagger sleep 뒤 · once 앞):
   ① force check True/예외 → RUN `below_floor`/`force_check_error`
   ② 마커 조회 예외 → RUN `marker_error`
   ③ 마커 None → `immediate_skip_if_marker_absent` 면 SKIP `no_marker`, 아니면 RUN `no_marker`
   ④ 파싱 실패 → RUN `marker_unparseable`
   ⑤ 마커 > now → RUN `future_marker`
   ⑥ 슬롯 None(또는 leaf 예외) → RUN `calendar_unknown`
   ⑦ 마커 ≥ 슬롯 → SKIP `fresh`, 아니면 RUN `stale`
5) 관측 로그 — 로거 `src.engine.scheduler`, INFO, 판정마다 정확히 1행:
   `[immediate_gate] task=<label> decision=run|skip reason=<④ 어휘> marker=<iso|None> slot=<iso|None>`
   `slot=` 은 fresh/stale 판정에서 `latest_passed_trading_slot(...).isoformat()` 이다.
   SKIP 이면 추가로 `[<label>] immediate run skip — <reason> last_success=<iso|None>` 1행
   (`reason=fresh` 일 때 cycle193 문자열과 동일).
6) 마커 기록 = 시간 모드 **또는 슬롯 모드**면 once 성공 직후(immediate + while) 기록, 실패 graceful.
7) `data_load_tasks` 배선: daily·basics = 슬롯 kw(시간 kw 제거) · full_universe = 슬롯 kw +
   `immediate_force_run_check` + `immediate_skip_if_marker_absent=True` · master·financial = 시간 kw
   유지 · purge·evening_funnel = 게이트 없음. 모듈 상수 `FULL_UNIVERSE_IMMEDIATE_MIN_ROWS = 2000`,
   force check = `stock_master.count_active() < 2000`(`count_active` 는 호출 시점에
   `src.db.stock_master` 모듈 속성으로 찾는다 — 이 파일이 그 이름을 패치한다).
8) (F-2) `_evaluate_slot_gate` 는 never-raise — 오프셋 없는(naive) 마커 = RUN `marker_unparseable`
   (④ 등급, 달력 조회 0) · leaf 슬롯이 tz-aware datetime 이 아니면 = RUN `calendar_unknown`
   (slot=None). 시간 모드의 naive 마커(= 실행)는 불변. 상세 = 파일 끝 N 절.

Red 유효성(현재 소스): 신규 kw → TypeError · leaf 부재 → ModuleNotFoundError ·
wrapper 가 시간 kw 를 넘김 → 배선 단언 AssertionError. 수집 단계에서 leaf 를 import 하지
않는다(스위트 전체가 죽지 않게 — leaf 는 테스트 안에서만 문자열 경로로 패치한다).
"""

from __future__ import annotations

import importlib
import logging
import re
from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db._kst import KST
from src.engine import data_load_tasks, task_loop_helper
from src.engine.scheduler import (
    TIME_EVENING_FUNNEL_CAPTURE,
    TIME_FULL_UNIVERSE_LOAD,
    TIME_STOCK_MASTER_BASICS_REFRESH,
    TIME_STOCK_MASTER_DAILY_LOAD,
    TIME_STOCK_MASTER_DAILY_PURGE,
    TIME_STOCK_MASTER_FINANCIAL_LOAD,
    TIME_STOCK_MASTER_MASTER_LOAD,
)
from src.engine.task_loop_helper import IMMEDIATE_FRESH_SKIP_HOURS, run_periodic_task_loop

pytestmark = pytest.mark.unit

_SCHED_LOGGER = "src.engine.scheduler"
_GATE_PREFIX = "[immediate_gate] "
_SLOT_KW = "immediate_skip_if_fresh_since_trading_slot"
_FORCE_KW = "immediate_force_run_check"
_ABSENT_KW = "immediate_skip_if_marker_absent"
_HOURS_KW = "immediate_skip_if_fresh_hours"
_HOLIDAYS = frozenset({date(2026, 9, 24), date(2026, 9, 25)})
_OPS_ROWS = 3583  # 운영 stock_master 행 수 (cycle360 §1.1 실측)


# ══════════════════════════════════════════════════════════════════════
# 공용 헬퍼
# ══════════════════════════════════════════════════════════════════════
@pytest.fixture(autouse=True)
def _no_sleep():
    """stagger(240/480초)·retry sleep 무력화."""
    with patch("src.engine.task_loop_helper.asyncio.sleep", new_callable=AsyncMock):
        yield


def _kst(y, m, d, hh=0, mm=0, ss=0) -> datetime:
    return datetime(y, m, d, hh, mm, ss, tzinfo=KST)


def _iso(y, m, d, hh=0, mm=0, ss=0) -> str:
    return _kst(y, m, d, hh, mm, ss).isoformat()


def _slot_iso(d: date, wait: time) -> str:
    return datetime.combine(d, wait, tzinfo=KST).isoformat()


class _FakeCalendar:
    """`trading_calendar._lookup_open` 대역. mode = normal | unknown | raise."""

    def __init__(self, mode: str = "normal") -> None:
        self.mode = mode
        self.calls: list[date] = []

    async def __call__(self, d):
        self.calls.append(d)
        if self.mode == "unknown":
            return None
        if self.mode == "raise":
            raise RuntimeError("KIS CTCA0903R down")
        return d.weekday() < 5 and d not in _HOLIDAYS


class FakeScheduler:
    """`_running` 토글 + `_wait_until` mock (cycle134/193 답습)."""

    def __init__(self, running: bool = False) -> None:
        self._running = running
        self.wait_calls = 0
        self._evening_funnel_capture_once = AsyncMock(return_value={})
        self.registry = MagicMock()
        self._pending_next_day_clear = set()

    async def _wait_until(self, target_time, *, advance_if_passed: bool = False) -> None:
        self.wait_calls += 1
        return None


def _use_clock(monkeypatch, now: datetime) -> None:
    monkeypatch.setattr(task_loop_helper, "_now_kst", lambda: now, raising=False)


def _use_calendar(monkeypatch, cal: _FakeCalendar) -> _FakeCalendar:
    """leaf seam 교체 + 메모 초기화. leaf 부재(Red)면 ModuleNotFoundError."""
    monkeypatch.setattr("src.engine.trading_calendar._lookup_open", cal)
    importlib.import_module("src.engine.trading_calendar")._reset_cache_for_tests()
    return cal


def _field(line: str, key: str) -> str | None:
    m = re.search(rf"\b{re.escape(key)}=([^\s]+)", line)
    return m.group(1) if m else None


def _gate_lines(caplog, label: str) -> list[str]:
    """`[immediate_gate]` 행 — 로거·레벨·prefix·task 4중 한정 (CI DEBUG 루트 로거 내성)."""
    out = []
    for r in caplog.records:
        msg = r.getMessage()
        if (
            r.name == _SCHED_LOGGER
            and r.levelno >= logging.INFO
            and msg.startswith(_GATE_PREFIX)
            and _field(msg, "task") == label
        ):
            out.append(msg)
    return out


def _legacy_skip_lines(caplog, label: str) -> list[str]:
    prefix = f"[{label}] immediate run skip"
    return [
        r.getMessage() for r in caplog.records
        if r.name == _SCHED_LOGGER
        and r.levelno >= logging.INFO
        and r.getMessage().startswith(prefix)
    ]


def _one_gate(caplog, label: str) -> str:
    lines = _gate_lines(caplog, label)
    assert len(lines) == 1, (
        f"`[immediate_gate] task={label}` INFO 는 판정당 정확히 1행 (실측 {lines})"
    )
    return lines[0]


# ── 헬퍼 직접 구동 ─────────────────────────────────────────────────────
async def _run_helper(
    monkeypatch,
    *,
    now: datetime,
    marker,
    label: str = "stock_master_daily_load",
    wait_time: time = TIME_STOCK_MASTER_DAILY_LOAD,
    calendar: _FakeCalendar | None = None,
    running: bool = False,
    sched: "FakeScheduler | None" = None,
    once=None,
    get_mock=None,
    set_mock=None,
    **gate_kwargs,
):
    _use_clock(monkeypatch, now)
    cal = _use_calendar(monkeypatch, calendar or _FakeCalendar())
    sched = sched or FakeScheduler(running=running)
    once = once or AsyncMock(return_value={"total": 1})
    get_mock = get_mock or AsyncMock(return_value=marker)
    set_mock = set_mock or AsyncMock(return_value=None)
    if not gate_kwargs:
        gate_kwargs = {_SLOT_KW: True}
    with patch(
        "src.db.system_config.get_task_last_success", get_mock, create=True
    ), patch(
        "src.db.system_config.set_task_last_success", set_mock, create=True
    ):
        await run_periodic_task_loop(
            scheduler=sched,
            task_label=label,
            wait_time=wait_time,
            once_callable=once,
            record_fn=MagicMock(),
            flush_fn=MagicMock(),
            summary_log_format="[test] total=%d",
            summary_keys=("total",),
            immediate_first_run=True,
            **gate_kwargs,
        )
    return once, get_mock, set_mock, sched, cal


# ── 실 wrapper 구동 (data_load_tasks → 실 헬퍼 → 실 leaf) ────────────────
_KINDS = {
    "daily": dict(
        fn="stock_master_daily_load_task_loop",
        label="stock_master_daily_load",
        wait=TIME_STOCK_MASTER_DAILY_LOAD,
        once="src.engine.scanner._stock_master_daily_load_once",
        record="src.engine.stock_master_daily_metrics.record_stock_master_daily_load",
        flush="src.engine.stock_master_daily_metrics.flush_stock_master_daily_load_collector",
    ),
    "basics": dict(
        fn="stock_master_basics_refresh_task_loop",
        label="stock_master_basics_refresh",
        wait=TIME_STOCK_MASTER_BASICS_REFRESH,
        once="src.engine.scanner._stock_master_basics_refresh_once",
        record="src.engine.stock_master_basics_metrics.record_stock_master_basics_refresh",
        flush="src.engine.stock_master_basics_metrics.flush_stock_master_basics_refresh_collector",
    ),
    "full_universe": dict(
        fn="full_universe_load_task_loop",
        label="full_universe_load",
        wait=TIME_FULL_UNIVERSE_LOAD,
        once="src.engine.scanner._full_universe_load_once",
        record="src.engine.stock_master_metrics.record_full_universe_load_summary",
        flush="src.engine.stock_master_metrics.flush_full_universe_load_collector",
    ),
}


async def _run_wrapper(
    monkeypatch,
    kind: str,
    *,
    now: datetime,
    marker,
    rows=_OPS_ROWS,
    missing_kis_keys=0,
    calendar: _FakeCalendar | None = None,
    running: bool = False,
):
    k = _KINDS[kind]
    _use_clock(monkeypatch, now)
    cal = _use_calendar(monkeypatch, calendar or _FakeCalendar())
    once = AsyncMock(return_value={})
    get_mock = AsyncMock(return_value=marker)
    set_mock = AsyncMock(return_value=None)
    if isinstance(rows, BaseException):
        count_mock = AsyncMock(side_effect=rows)
    else:
        count_mock = AsyncMock(return_value=rows)
    # F-4 — basics 의 강제 실행 콜백이 부르는 count. 기본 0(임계 이하 = 강제실행 없음)
    # 이라 다른 kind 도 무해하게 patch 된다(basics 밖에서는 호출되지 않는다).
    missing_mock = AsyncMock(return_value=missing_kis_keys)
    with patch(k["once"], once), patch(k["record"], MagicMock()), patch(
        k["flush"], MagicMock()
    ), patch(
        "src.db.system_config.get_task_last_success", get_mock, create=True
    ), patch(
        "src.db.system_config.set_task_last_success", set_mock, create=True
    ), patch("src.db.stock_master.count_active", count_mock), patch(
        "src.db.stock_master.count_missing_kis_provenance_key", missing_mock
    ):
        await getattr(data_load_tasks, k["fn"])(
            FakeScheduler(running=running), wait_time=k["wait"]
        )
    return once, set_mock, count_mock, cal


# 시나리오 (1)(2) 의 정상 마커 — 각 정기 슬롯 직후 성공 (EC2 실측 종료 시각대)
def _normal_marker(kind: str, d: date) -> str:
    hhmmss = {"daily": (20, 32, 0), "basics": (16, 24, 0), "full_universe": (20, 0, 40)}[kind]
    return _iso(d.year, d.month, d.day, *hhmmss)


# ══════════════════════════════════════════════════════════════════════
# S. 시나리오 표 §3.1 — 실 wrapper → 실 헬퍼 → 실 leaf (가짜 달력)
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("kind", ["daily", "basics", "full_universe"])
async def test_S1_monday_morning_friday_marker_skips(monkeypatch, caplog, kind):
    """(1) 월 09-21 07:45 · 마커 금 09-18(정기 슬롯 뒤) → 셋 다 SKIP `reason=fresh`.

    주말 63.9h 를 「낡았다」고 세던 시간 게이트가 월요일 보충 적재(목요일 KRX 값 덮어쓰기)를
    일으켰다(cycle360 §1.1·§1.2). 슬롯 게이트에서 금요일 정기 실행은 직전 영업일 실행이다.
    """
    k = _KINDS[kind]
    marker = _normal_marker(kind, date(2026, 9, 18))
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, set_mock, _c, _cal = await _run_wrapper(
            monkeypatch, kind, now=_kst(2026, 9, 21, 7, 45), marker=marker,
        )

    assert once.await_count == 0, f"{kind}: 월요일 immediate 실행 금지 (금요일 마커 fresh)"
    assert set_mock.await_count == 0
    line = _one_gate(caplog, k["label"])
    assert _field(line, "decision") == "skip" and _field(line, "reason") == "fresh", line
    assert _field(line, "slot") == _slot_iso(date(2026, 9, 18), k["wait"]), (
        f"슬롯 = 직전 영업일(금 09-18) × wait_time (실측 {line})"
    )
    assert _field(line, "marker") == marker, line
    assert _legacy_skip_lines(caplog, k["label"]) == [
        f"[{k['label']}] immediate run skip — fresh last_success={marker}"
    ], "SKIP 은 cycle193 grep 문자열 1행을 그대로 남긴다"


@pytest.mark.parametrize("kind", ["daily", "basics", "full_universe"])
async def test_S2_tuesday_morning_monday_marker_skips(monkeypatch, caplog, kind):
    """(2) 화 09-22 07:45 · 마커 월 09-21 → SKIP (평일 아침은 현행과 같은 결과)."""
    k = _KINDS[kind]
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_wrapper(
            monkeypatch, kind, now=_kst(2026, 9, 22, 7, 45),
            marker=_normal_marker(kind, date(2026, 9, 21)),
        )
    assert once.await_count == 0
    line = _one_gate(caplog, k["label"])
    assert (_field(line, "decision"), _field(line, "reason")) == ("skip", "fresh"), line
    assert _field(line, "slot") == _slot_iso(date(2026, 9, 21), k["wait"]), line


@pytest.mark.parametrize("kind", ["daily", "basics"])
async def test_S3a_after_chuseok_wednesday_marker_skips(monkeypatch, caplog, kind):
    """(3) **09-28 07:45** · 마커 09-23(수) → daily·basics SKIP — 연휴 5일을 건너뛴다."""
    k = _KINDS[kind]
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_wrapper(
            monkeypatch, kind, now=_kst(2026, 9, 28, 7, 45),
            marker=_normal_marker(kind, date(2026, 9, 23)),
        )
    assert once.await_count == 0, f"{kind}: 09-28 immediate 실행 금지 (직전 영업일 09-23 마커)"
    line = _one_gate(caplog, k["label"])
    assert (_field(line, "decision"), _field(line, "reason")) == ("skip", "fresh"), line
    assert _field(line, "slot") == _slot_iso(date(2026, 9, 23), k["wait"]), line


async def test_S3b_full_universe_bootstrap_no_marker_skips(monkeypatch, caplog):
    """(3) 09-28 07:45 · full_universe 마커 없음 · 행 수 3,583 → SKIP `reason=no_marker`.

    부트스트랩(M6): full_universe 는 지금까지 마커를 남긴 적이 없다. 「마커 없음 = 실행」이면
    09-28 에 09-22 KRX 값 덮어쓰기가 그대로 일어난다. 자가 치유는 행 수 하한이 맡는다.
    """
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, set_mock, count_mock, _cal = await _run_wrapper(
            monkeypatch, "full_universe", now=_kst(2026, 9, 28, 7, 45), marker=None,
        )
    assert once.await_count == 0, "마커 없음 + 행 수 ≥ 하한 → full_universe immediate 금지"
    assert count_mock.await_count >= 1, "행 수 하한 판정(count_active)이 먼저 돌아야 한다"
    line = _one_gate(caplog, "full_universe_load")
    assert (_field(line, "decision"), _field(line, "reason")) == ("skip", "no_marker"), line
    assert _legacy_skip_lines(caplog, "full_universe_load") == [
        "[full_universe_load] immediate run skip — no_marker last_success=None"
    ]


async def test_S4_friday_load_failed_monday_runs_stale(monkeypatch, caplog):
    """(4) 월 09-21 07:45 · daily 마커 목 09-17 20:32(금 적재 실패) → RUN `reason=stale`."""
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, set_mock, *_ = await _run_wrapper(
            monkeypatch, "daily", now=_kst(2026, 9, 21, 7, 45),
            marker=_iso(2026, 9, 17, 20, 32),
        )
    assert once.await_count == 1, "금요일 정기 실패 → 월요일 immediate 자가 치유 의무"
    assert set_mock.await_count == 1, "슬롯 모드도 성공 마커를 기록한다"
    assert set_mock.await_args.args[0] == "stock_master_daily_load"
    line = _one_gate(caplog, "stock_master_daily_load")
    assert (_field(line, "decision"), _field(line, "reason")) == ("run", "stale"), line
    assert _field(line, "slot") == _slot_iso(date(2026, 9, 18), TIME_STOCK_MASTER_DAILY_LOAD)
    assert _legacy_skip_lines(caplog, "stock_master_daily_load") == [], "RUN 은 skip 행 금지"


@pytest.mark.parametrize("mode", ["unknown", "raise"])
@pytest.mark.parametrize("kind", ["daily", "basics", "full_universe"])
async def test_S5_calendar_unknown_runs(monkeypatch, caplog, kind, mode):
    """(5) 휴장일 조회 None / 예외 → RUN `reason=calendar_unknown` (M3 — 사용자 지시: 실패 = 실행)."""
    k = _KINDS[kind]
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_wrapper(
            monkeypatch, kind, now=_kst(2026, 9, 21, 7, 45),
            marker=_normal_marker(kind, date(2026, 9, 18)),
            calendar=_FakeCalendar(mode),
        )
    assert once.await_count == 1, f"{kind}/{mode}: 달력 모름 → 실행 의무 (SKIP 으로 바꾸면 붉어진다)"
    line = _one_gate(caplog, k["label"])
    assert (_field(line, "decision"), _field(line, "reason")) == ("run", "calendar_unknown"), line


@pytest.mark.parametrize("rows", [1999, 0], ids=["rows_1999", "count_active_failed_0"])
async def test_S6_full_universe_below_floor_runs_even_if_fresh(monkeypatch, caplog, rows):
    """(6) 행 수 1,999 · `count_active` 예외(→0) → 마커 fresh 여도 RUN `reason=below_floor` (M2).

    cycle193 이 full_universe 게이트를 뺀 이유(자가 치유)를 행 수 하한이 보존한다.
    2026-08-08 degrade 사고 = 60행, 운영 = 3,583행.
    """
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_wrapper(
            monkeypatch, "full_universe", now=_kst(2026, 9, 21, 7, 45),
            marker=_normal_marker("full_universe", date(2026, 9, 18)), rows=rows,
        )
    assert once.await_count == 1, f"행 수 {rows} < 2000 → full_universe immediate 실행 의무"
    line = _one_gate(caplog, "full_universe_load")
    assert (_field(line, "decision"), _field(line, "reason")) == ("run", "below_floor"), line


async def test_S6b_full_universe_floor_boundary_2000_skips(monkeypatch, caplog):
    """하한 경계 — `count_active() < 2000` 일 때만 실행. 정확히 2,000 은 SKIP."""
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_wrapper(
            monkeypatch, "full_universe", now=_kst(2026, 9, 21, 7, 45),
            marker=_normal_marker("full_universe", date(2026, 9, 18)), rows=2000,
        )
    assert once.await_count == 0
    line = _one_gate(caplog, "full_universe_load")
    assert (_field(line, "decision"), _field(line, "reason")) == ("skip", "fresh"), line


async def test_S7_full_universe_no_marker_below_floor_runs(monkeypatch, caplog):
    """(7) full_universe · 마커 없음 · 행 수 < 하한 → RUN (하한이 부트스트랩보다 먼저)."""
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_wrapper(
            monkeypatch, "full_universe", now=_kst(2026, 9, 28, 7, 45), marker=None, rows=1999,
        )
    assert once.await_count == 1
    line = _one_gate(caplog, "full_universe_load")
    assert (_field(line, "decision"), _field(line, "reason")) == ("run", "below_floor"), line


async def test_S7b_full_universe_no_marker_decided_before_calendar(monkeypatch, caplog):
    """판정 순서 ③ < ⑥ — 마커 없음(부트스트랩)은 달력 조회 결과와 무관하게 SKIP."""
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_wrapper(
            monkeypatch, "full_universe", now=_kst(2026, 9, 28, 7, 45), marker=None,
            calendar=_FakeCalendar("unknown"),
        )
    assert once.await_count == 0
    line = _one_gate(caplog, "full_universe_load")
    assert (_field(line, "decision"), _field(line, "reason")) == ("skip", "no_marker"), line


@pytest.mark.parametrize("kind", ["daily", "basics"])
async def test_S7c_daily_basics_no_marker_still_runs(monkeypatch, caplog, kind):
    """daily·basics 는 「마커 없음 = 실행」 현행 유지 (부트스트랩 skip 은 full_universe 전용)."""
    k = _KINDS[kind]
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_wrapper(
            monkeypatch, kind, now=_kst(2026, 9, 28, 7, 45), marker=None,
        )
    assert once.await_count == 1
    line = _one_gate(caplog, k["label"])
    assert (_field(line, "decision"), _field(line, "reason")) == ("run", "no_marker"), line


@pytest.mark.parametrize(
    "marker, expect_run",
    [(_iso(2026, 9, 22, 16, 24), False), (_iso(2026, 9, 21, 16, 24), True)],
    ids=["marker_today_1624_skip", "marker_yesterday_1624_run"],
)
async def test_S8_same_day_restart_after_slot(monkeypatch, caplog, marker, expect_run):
    """(8) 같은 날 재기동: 화 09-22 17:00 · basics 마커 화 16:24 → SKIP / 월 16:24 → RUN."""
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_wrapper(
            monkeypatch, "basics", now=_kst(2026, 9, 22, 17, 0), marker=marker,
        )
    assert once.await_count == (1 if expect_run else 0)
    line = _one_gate(caplog, "stock_master_basics_refresh")
    assert _field(line, "reason") == ("stale" if expect_run else "fresh"), line
    assert _field(line, "slot") == _slot_iso(date(2026, 9, 22), TIME_STOCK_MASTER_BASICS_REFRESH)


async def test_S8b_slot_is_wait_time_per_task(monkeypatch, caplog):
    """슬롯 = 그 task 의 `wait_time` — 화 21:00 · 마커 화 16:24: basics SKIP · daily RUN.

    basics 슬롯은 오늘 16:10 (마커가 뒤), daily 슬롯은 오늘 20:30 (마커가 앞).
    모든 task 에 같은 슬롯을 쓰거나 시각 리터럴을 박으면 둘 중 하나가 붉어진다.
    """
    marker = _iso(2026, 9, 22, 16, 24)
    now = _kst(2026, 9, 22, 21, 0)
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        basics_once, *_ = await _run_wrapper(monkeypatch, "basics", now=now, marker=marker)
        daily_once, *_ = await _run_wrapper(monkeypatch, "daily", now=now, marker=marker)
    assert basics_once.await_count == 0, "basics: 마커 16:24 ≥ 슬롯 16:10 → SKIP"
    assert daily_once.await_count == 1, "daily: 마커 16:24 < 슬롯 20:30 → RUN"
    d_line = _one_gate(caplog, "stock_master_daily_load")
    assert _field(d_line, "slot") == _slot_iso(date(2026, 9, 22), TIME_STOCK_MASTER_DAILY_LOAD)


# ══════════════════════════════════════════════════════════════════════
# H. 헬퍼 계약 — 판정 순서 · ValueError · 마커 기록 · 정기 발화 불변
# ══════════════════════════════════════════════════════════════════════
async def test_H1_time_and_slot_mode_together_raise_value_error(monkeypatch):
    """(10) 시간 게이트 + 슬롯 게이트 동시 지정 = 프로그래밍 오류 → 진입 즉시 ValueError."""
    _use_clock(monkeypatch, _kst(2026, 9, 21, 7, 45))
    once = AsyncMock(return_value={"total": 0})
    sleep_mock = AsyncMock()
    with patch("src.engine.task_loop_helper.asyncio.sleep", sleep_mock):
        with pytest.raises(ValueError):
            await run_periodic_task_loop(
                scheduler=FakeScheduler(),
                task_label="x",
                wait_time=time(16, 10),
                once_callable=once,
                record_fn=MagicMock(),
                flush_fn=MagicMock(),
                summary_log_format="[test] total=%d",
                summary_keys=("total",),
                initial_delay_secs=480,
                **{_HOURS_KW: IMMEDIATE_FRESH_SKIP_HOURS, _SLOT_KW: True},
            )
    assert once.await_count == 0
    assert sleep_mock.await_count == 0, "stagger sleep 보다 먼저(함수 진입 즉시) 검사한다"


async def test_H2_future_marker_runs(monkeypatch, caplog):
    """(9) 미래 마커(시계 이상) → RUN `reason=future_marker` (cycle193 F9 와 같은 정신)."""
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_helper(
            monkeypatch, now=_kst(2026, 9, 22, 7, 45), marker=_iso(2026, 9, 22, 9, 0),
        )
    assert once.await_count == 1
    line = _one_gate(caplog, "stock_master_daily_load")
    assert (_field(line, "decision"), _field(line, "reason")) == ("run", "future_marker"), line


async def test_H3_marker_query_exception_runs(monkeypatch, caplog):
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_helper(
            monkeypatch, now=_kst(2026, 9, 22, 7, 45), marker=None,
            get_mock=AsyncMock(side_effect=RuntimeError("pg down")),
        )
    assert once.await_count == 1, "마커 조회 예외 → 실행 (fail-closed 금지)"
    line = _one_gate(caplog, "stock_master_daily_load")
    assert (_field(line, "decision"), _field(line, "reason")) == ("run", "marker_error"), line


async def test_H3b_real_get_task_last_success_swallows_pg_failure_as_no_marker(monkeypatch):
    """cycle363 F-5 — 실 `get_task_last_success` 는 pg 예외를 삼켜 None 을 준다.

    `_get_string_or_none`(`src/db/system_config.py`) 이 broad `except Exception: return None`
    이라, 운영에서 `_evaluate_slot_gate` 의 `reason=marker_error` 분기(②의 try/except)는
    **도달 불가**다 — 이 test 는 mock 이 아니라 실 함수 경로(pg.fetch 예외 → None)로 그 사실을
    실측한다. 명세 정정 = 「조회 실패 = no_marker 와 동급」. full_universe(skip_if_absent=True)
    에서는 이 경로가 부트스트랩과 구분되지 않는 SKIP 이 된다 — 그 한계는 명세·`src/engine/
    CLAUDE.md` 「정기 task 루프」 절에 명시한다(코드 시정 대상이 아니다).
    """
    from src.db import pg as _pg

    _use_calendar(monkeypatch, _FakeCalendar())
    _use_clock(monkeypatch, _kst(2026, 9, 21, 7, 45))
    monkeypatch.setattr(_pg, "fetch", AsyncMock(side_effect=RuntimeError("pg down")))

    got_daily = await task_loop_helper._evaluate_slot_gate(
        "stock_master_daily_load", TIME_STOCK_MASTER_DAILY_LOAD, None, False,
    )
    assert got_daily == (True, "no_marker", None, None), (
        f"실 get_task_last_success 는 pg 예외를 삼켜 None — `marker_error` 는 도달 불가 "
        f"(실측 {got_daily!r})"
    )

    got_full_universe = await task_loop_helper._evaluate_slot_gate(
        "full_universe_load", TIME_FULL_UNIVERSE_LOAD, None, True,
    )
    assert got_full_universe == (False, "no_marker", None, None), (
        f"full_universe(skip_if_absent=True) 에서는 같은 pg 장애가 부트스트랩과 구분되지 "
        f"않는 SKIP 이 된다 — 명세 한계(실측 {got_full_universe!r})"
    )


async def test_H4_unparseable_marker_runs(monkeypatch, caplog):
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_helper(
            monkeypatch, now=_kst(2026, 9, 22, 7, 45), marker="not-a-timestamp",
        )
    assert once.await_count == 1
    line = _one_gate(caplog, "stock_master_daily_load")
    assert (_field(line, "decision"), _field(line, "reason")) == ("run", "marker_unparseable"), line


@pytest.mark.parametrize(
    "make_check, expect",
    [
        (lambda: AsyncMock(return_value=True), ("run", "below_floor", 1)),
        (lambda: AsyncMock(side_effect=RuntimeError("count failed")), ("run", "force_check_error", 1)),
        (lambda: AsyncMock(return_value=False), ("skip", "fresh", 0)),
    ],
    ids=["force_true", "force_raises", "force_false"],
)
async def test_H5_force_run_check_is_first(monkeypatch, caplog, make_check, expect):
    """판정 ① — force check True/예외면 마커가 fresh 여도 실행. False 면 다음 단계로."""
    decision, reason, runs = expect
    check = make_check()
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_helper(
            monkeypatch, now=_kst(2026, 9, 21, 7, 45), marker=_iso(2026, 9, 18, 20, 32),
            **{_SLOT_KW: True, _FORCE_KW: check},
        )
    assert check.await_count == 1, "force check 는 immediate 판정마다 1회 await"
    assert once.await_count == runs
    line = _one_gate(caplog, "stock_master_daily_load")
    assert (_field(line, "decision"), _field(line, "reason")) == (decision, reason), line


async def test_H5b_force_run_reason_defaults_to_below_floor(monkeypatch):
    """F-4 — `force_run_reason` 미지정 = 기존 `below_floor` byte 동일(회귀 0)."""
    got = await task_loop_helper._evaluate_slot_gate(
        "full_universe_load", TIME_FULL_UNIVERSE_LOAD,
        AsyncMock(return_value=True), True,
    )
    assert got == (True, "below_floor", None, None), f"실측 {got!r}"


async def test_H5c_force_run_reason_is_threaded_through_when_triggered(monkeypatch):
    """F-4 — force check 가 True 면 `force_run_reason` 문구가 그대로 reason 이 된다."""
    got = await task_loop_helper._evaluate_slot_gate(
        "stock_master_basics_refresh", TIME_STOCK_MASTER_BASICS_REFRESH,
        AsyncMock(return_value=True), False, force_run_reason="kis_keys_missing",
    )
    assert got == (True, "kis_keys_missing", None, None), f"실측 {got!r}"


async def test_H5d_force_run_reason_ignored_when_check_raises(monkeypatch):
    """F-4 — force check 가 예외를 던지면 `force_run_reason` 과 무관하게 `force_check_error`."""
    got = await task_loop_helper._evaluate_slot_gate(
        "stock_master_basics_refresh", TIME_STOCK_MASTER_BASICS_REFRESH,
        AsyncMock(side_effect=RuntimeError("pg down")), False,
        force_run_reason="kis_keys_missing",
    )
    assert got == (True, "force_check_error", None, None), f"실측 {got!r}"


@pytest.mark.parametrize(
    "absent_flag, expect",
    [(False, ("run", 1)), (True, ("skip", 0))],
    ids=["absent_runs_default", "absent_skips_when_flagged"],
)
async def test_H6_marker_absent_behavior_is_flag_driven(monkeypatch, caplog, absent_flag, expect):
    decision, runs = expect
    kwargs = {_SLOT_KW: True}
    if absent_flag:
        kwargs[_ABSENT_KW] = True
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_helper(
            monkeypatch, now=_kst(2026, 9, 28, 7, 45), marker=None, **kwargs,
        )
    assert once.await_count == runs
    line = _one_gate(caplog, "stock_master_daily_load")
    assert (_field(line, "decision"), _field(line, "reason")) == (decision, "no_marker"), line


async def test_H7_leaf_exception_is_calendar_unknown_run(monkeypatch, caplog):
    """leaf 가 (never-raise 계약을 어기고) 던져도 헬퍼는 RUN `calendar_unknown`."""
    _use_calendar(monkeypatch, _FakeCalendar())

    async def _boom(*_a, **_k):
        raise RuntimeError("leaf bug")

    monkeypatch.setattr("src.engine.trading_calendar.latest_passed_trading_slot", _boom)
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_helper(
            monkeypatch, now=_kst(2026, 9, 21, 7, 45), marker=_iso(2026, 9, 18, 20, 32),
        )
    assert once.await_count == 1
    line = _one_gate(caplog, "stock_master_daily_load")
    assert (_field(line, "decision"), _field(line, "reason")) == ("run", "calendar_unknown"), line


async def test_H8_slot_mode_records_marker_after_immediate_success(monkeypatch):
    """(11) 슬롯 모드 immediate 성공 → `set_task_last_success(label, KST iso)`."""
    once, _g, set_mock, *_ = await _run_helper(
        monkeypatch, now=_kst(2026, 9, 21, 7, 45), marker=_iso(2026, 9, 17, 20, 32),
    )
    assert once.await_count == 1
    assert set_mock.await_count == 1, "슬롯 모드도 성공 마커 기록 의무 (없으면 다음 부팅 판정 불가)"
    label, iso = set_mock.await_args.args[:2]
    assert label == "stock_master_daily_load"
    assert isinstance(iso, str) and "+09:00" in iso, f"KST iso 의무 (실측 {iso!r})"


async def test_H9_slot_mode_marker_record_failure_is_graceful(monkeypatch):
    once, _g, set_mock, *_ = await _run_helper(
        monkeypatch, now=_kst(2026, 9, 21, 7, 45), marker=_iso(2026, 9, 17, 20, 32),
        set_mock=AsyncMock(side_effect=RuntimeError("upsert failed")),
    )
    assert once.await_count == 1
    assert set_mock.await_count == 1, "기록 시도 후 예외는 흡수 (전파 금지)"


async def test_H10_slot_mode_once_failure_does_not_record_marker(monkeypatch):
    """once 예외 → 마커 기록 금지 (기록하면 다음 부팅 자가 치유가 죽는다)."""
    once, _g, set_mock, *_ = await _run_helper(
        monkeypatch, now=_kst(2026, 9, 21, 7, 45), marker=_iso(2026, 9, 17, 20, 32),
        once=AsyncMock(side_effect=RuntimeError("KIS 장애")),
    )
    assert once.await_count == 1
    assert set_mock.await_count == 0


async def test_H11_periodic_loop_fires_despite_fresh_marker_and_records(monkeypatch):
    """(12) 정기 while 발화는 게이트와 무관 (cycle193 F-8 동형) + while 성공도 마커 기록."""
    sched = FakeScheduler(running=True)

    async def _once():
        sched._running = False
        return {"total": 1}

    once, _g, set_mock, sched, _cal = await _run_helper(
        monkeypatch, now=_kst(2026, 9, 21, 7, 45), marker=_iso(2026, 9, 18, 20, 32),
        sched=sched, once=AsyncMock(side_effect=_once),
    )
    assert once.await_count == 1, "fresh → immediate skip, 정기 while 에서만 1회 발화"
    assert sched.wait_calls >= 1, "while 루프 `_wait_until` 진입 증거"
    assert set_mock.await_count == 1, "while 성공 → 마커 기록 의무 (슬롯 모드)"


async def test_H12_no_gate_kwargs_never_touch_calendar_or_marker(monkeypatch):
    """게이트 미지정 = 기존 행위 (마커 0 · 달력 조회 0) — purge·evening_funnel 경로."""
    _use_clock(monkeypatch, _kst(2026, 9, 21, 7, 45))
    cal = _use_calendar(monkeypatch, _FakeCalendar())
    get_mock, set_mock = AsyncMock(return_value=None), AsyncMock()
    once = AsyncMock(return_value={"total": 0})
    with patch("src.db.system_config.get_task_last_success", get_mock, create=True), patch(
        "src.db.system_config.set_task_last_success", set_mock, create=True
    ):
        await run_periodic_task_loop(
            scheduler=FakeScheduler(),
            task_label="stock_master_daily_purge",
            wait_time=TIME_STOCK_MASTER_DAILY_PURGE,
            once_callable=once,
            record_fn=MagicMock(),
            flush_fn=MagicMock(),
            summary_log_format="[test] total=%d",
            summary_keys=("total",),
        )
    assert once.await_count == 1
    assert get_mock.await_count == 0 and set_mock.await_count == 0
    assert cal.calls == [], "게이트 미지정 경로는 휴장일 조회 0"


async def test_H13_time_mode_does_not_consult_calendar(monkeypatch):
    """master·financial 의 시간 게이트는 달력과 무관 (슬롯 게이트로 새지 않는다)."""
    cal = _use_calendar(monkeypatch, _FakeCalendar("raise"))
    fresh = (datetime.now(KST) - timedelta(hours=1)).isoformat()
    get_mock, set_mock = AsyncMock(return_value=fresh), AsyncMock()
    once = AsyncMock(return_value={"total": 0})
    with patch("src.db.system_config.get_task_last_success", get_mock, create=True), patch(
        "src.db.system_config.set_task_last_success", set_mock, create=True
    ):
        await run_periodic_task_loop(
            scheduler=FakeScheduler(),
            task_label="stock_master_master_load",
            wait_time=TIME_STOCK_MASTER_MASTER_LOAD,
            once_callable=once,
            record_fn=MagicMock(),
            flush_fn=MagicMock(),
            summary_log_format="[test] total=%d",
            summary_keys=("total",),
            **{_HOURS_KW: IMMEDIATE_FRESH_SKIP_HOURS},
        )
    assert once.await_count == 0, "1h 전 마커 → 시간 게이트 skip (현행)"
    assert cal.calls == [], "시간 모드는 휴장일 조회 0"


# ══════════════════════════════════════════════════════════════════════
# W. data_load_tasks 배선 — 캡처 kwargs
# ══════════════════════════════════════════════════════════════════════
async def _capture_wrapper_kwargs(fn_name: str, wait_time: time) -> dict:
    captured: dict = {}

    async def _capture(**kwargs):
        captured.update(kwargs)

    with patch("src.engine.task_loop_helper.run_periodic_task_loop", _capture):
        await getattr(data_load_tasks, fn_name)(FakeScheduler(), wait_time=wait_time)
    return captured


@pytest.mark.parametrize("kind", ["daily", "basics"])
async def test_W1_daily_basics_use_slot_gate_not_hours(kind):
    """M1 — daily·basics 를 시간 게이트로 되돌리면 붉어진다."""
    k = _KINDS[kind]
    got = await _capture_wrapper_kwargs(k["fn"], k["wait"])
    assert got.get("task_label") == k["label"]
    assert got.get(_SLOT_KW) is True, f"{kind}: 슬롯 게이트 kw 의무 (전달 {sorted(got)})"
    assert got.get(_HOURS_KW) is None, f"{kind}: 시간 게이트 kw 제거 의무 (실측 {got.get(_HOURS_KW)!r})"
    assert not got.get(_ABSENT_KW), "마커 없음 skip 은 full_universe 전용"
    if kind == "daily":
        assert got.get(_FORCE_KW) is None, "daily: 행 수 하한은 범위 밖(강제 실행 콜백 없음)"
    else:
        # cycle363 F-4(사용자 승인) — basics 는 KIS 출처 키 결측 강제 실행 콜백을 갖는다.
        # 전용 검증은 test_W2b 가 한다(콜백 대상·reason 리터럴·행위).
        assert callable(got.get(_FORCE_KW)), "basics: F-4 강제 실행 콜백 의무"
    assert got.get("wait_time") == k["wait"], "슬롯 = scheduler TIME_* 정본 그대로 전달"


async def test_W2_full_universe_slot_gate_with_floor_and_bootstrap():
    """M2·M6 — full_universe = 슬롯 kw + 행 수 하한 콜백 + 마커 없음 skip."""
    k = _KINDS["full_universe"]
    got = await _capture_wrapper_kwargs(k["fn"], k["wait"])
    assert got.get("task_label") == "full_universe_load"
    assert got.get(_SLOT_KW) is True, f"슬롯 게이트 kw 의무 (전달 {sorted(got)})"
    assert got.get(_HOURS_KW) is None
    assert callable(got.get(_FORCE_KW)), "행 수 하한 콜백(immediate_force_run_check) 의무"
    assert got.get(_ABSENT_KW) is True, "부트스트랩 — 마커 없음 + 하한 이상 → skip"
    assert got.get("wait_time") == TIME_FULL_UNIVERSE_LOAD


_REASON_KW = "immediate_force_run_reason"


async def test_W2b_basics_force_run_check_wiring():
    """F-4(사용자 승인) — basics = KIS 출처 키 결측 콜백 + `reason=kis_keys_missing`."""
    k = _KINDS["basics"]
    got = await _capture_wrapper_kwargs(k["fn"], k["wait"])
    assert callable(got.get(_FORCE_KW)), "F-4 강제 실행 콜백 의무"
    assert got.get(_REASON_KW) == "kis_keys_missing", f"실측 {got.get(_REASON_KW)!r}"
    assert not got.get(_ABSENT_KW), "마커 없음 skip 은 여전히 full_universe 전용"


@pytest.mark.parametrize(
    "missing, expect",
    [(0, False), (100, False), (101, True), (2674, True)],
    ids=["zero", "boundary_100", "just_over", "monday_incident_scale"],
)
async def test_W2c_basics_force_check_threshold(missing, expect):
    """F-4 — `count_missing_kis_provenance_key() > 100` 일 때만 강제 실행.

    경계 100 은 SKIP(하한 이상 아님) — 운영 실측 결측 0행과 월요일 KRX 전량 덮어쓰기
    사고 규모(2,670~2,674행) 사이 어디든 안전하게 걸리도록 넉넉히 잡은 값이다.
    """
    k = _KINDS["basics"]
    got = await _capture_wrapper_kwargs(k["fn"], k["wait"])
    check = got.get(_FORCE_KW)
    assert callable(check)
    count_mock = AsyncMock(return_value=missing)
    with patch("src.db.stock_master.count_missing_kis_provenance_key", count_mock):
        result = await check()
    assert count_mock.await_count == 1
    assert result is expect, f"missing={missing} → 강제실행={expect} (실측 {result!r})"


async def test_W2d_basics_force_check_query_failure_propagates_to_run():
    """F-4 — 쿼리 실패는 콜백에서 삼키지 않고 전파(전파돼야 force_check_error=RUN 이 된다).

    사용자 결정: 「쿼리 실패는 RUN 쪽(fail-safe)」. `_evaluate_slot_gate` 의 force_check
    예외 처리(`reason=force_check_error`)가 이 전파에 기대므로, 콜백이 여기서 0 등으로
    삼키면 반대 방향(SKIP)으로 조용히 뒤집힌다.
    """
    k = _KINDS["basics"]
    got = await _capture_wrapper_kwargs(k["fn"], k["wait"])
    check = got.get(_FORCE_KW)
    with patch(
        "src.db.stock_master.count_missing_kis_provenance_key",
        AsyncMock(side_effect=RuntimeError("pg down")),
    ):
        with pytest.raises(RuntimeError):
            await check()


async def test_W2e_basics_force_run_end_to_end_via_real_helper(monkeypatch, caplog):
    """F-4 — 실 wrapper → 실 헬퍼: 결측 임계 초과 시 `reason=kis_keys_missing` 로 RUN.

    fresh 마커(SKIP 조건)여도 강제 실행이 이겨야 한다(판정 순서 ① 이 ⑦ 보다 먼저).
    """
    k = _KINDS["basics"]
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, *_ = await _run_wrapper(
            monkeypatch, "basics", now=_kst(2026, 9, 21, 7, 45),
            marker=_normal_marker("basics", date(2026, 9, 18)),
            missing_kis_keys=2674,
        )
    assert once.await_count == 1, "결측 2,674행(월요일 사고 규모) → fresh 마커도 강제 실행"
    line = _one_gate(caplog, k["label"])
    assert (_field(line, "decision"), _field(line, "reason")) == ("run", "kis_keys_missing"), line


@pytest.mark.parametrize(
    "fn, wait, hours",
    [
        ("stock_master_master_load_task_loop", TIME_STOCK_MASTER_MASTER_LOAD, IMMEDIATE_FRESH_SKIP_HOURS),
        ("stock_master_financial_load_task_loop", TIME_STOCK_MASTER_FINANCIAL_LOAD, 168),
    ],
    ids=["master", "financial"],
)
async def test_W3_master_financial_keep_time_gate(fn, wait, hours):
    """master(16:30)·financial(16:40)은 범위 밖 — 시간 게이트 그대로."""
    got = await _capture_wrapper_kwargs(fn, wait)
    assert got.get(_HOURS_KW) == hours
    assert not got.get(_SLOT_KW), "범위 밖 task 에 슬롯 게이트 금지"


@pytest.mark.parametrize(
    "fn, wait",
    [
        ("stock_master_daily_purge_task_loop", TIME_STOCK_MASTER_DAILY_PURGE),
        ("evening_funnel_capture_task_loop", TIME_EVENING_FUNNEL_CAPTURE),
    ],
    ids=["purge", "evening_funnel"],
)
async def test_W4_purge_and_evening_funnel_stay_ungated(fn, wait):
    """+600초 재준비(evening_funnel)·purge 는 게이트 없음 유지 (단계 3·카드3 전 금지)."""
    got = await _capture_wrapper_kwargs(fn, wait)
    for kw in (_HOURS_KW, _SLOT_KW, _FORCE_KW, _ABSENT_KW):
        assert kw not in got, f"{fn}: 게이트 kw `{kw}` 금지 (실측 {got.get(kw)!r})"


def test_W5_full_universe_floor_constant_is_2000():
    """운영 3,583행 · 2026-08-08 degrade 60행 — 정상보다 한참 아래, degrade 보다 한참 위."""
    assert getattr(data_load_tasks, "FULL_UNIVERSE_IMMEDIATE_MIN_ROWS", None) == 2000


@pytest.mark.parametrize(
    "rows, expect",
    [(1999, True), (2000, False), (_OPS_ROWS, False), (0, True)],
    ids=["1999_below", "2000_boundary", "ops_3583", "count_failed_0"],
)
async def test_W6_force_check_is_count_active_below_floor(rows, expect):
    k = _KINDS["full_universe"]
    got = await _capture_wrapper_kwargs(k["fn"], k["wait"])
    check = got.get(_FORCE_KW)
    assert callable(check), "force check 콜백 부재"
    count_mock = AsyncMock(return_value=rows)
    with patch("src.db.stock_master.count_active", count_mock):
        result = await check()
    assert count_mock.await_count == 1, "행 수는 `stock_master.count_active()` 로 잰다"
    assert result is expect, f"rows={rows} → below_floor={expect} (실측 {result!r})"


# ══════════════════════════════════════════════════════════════════════
# C. 전역 중립화 픽스처 self-test (옵트아웃 없음)
# ══════════════════════════════════════════════════════════════════════
async def test_C1_conftest_neutralizes_calendar_to_unknown(monkeypatch):
    """`tests/conftest.py::_neutralize_trading_calendar` — 기본 seam = None(모름), KIS 0회.

    이 픽스처가 없으면 슬롯 게이트·prepare 를 타는 기존 테스트가 실 KIS 로 나가려 하고,
    메모가 테스트 간에 새어 판정이 순서 의존이 된다.
    """
    tc = importlib.import_module("src.engine.trading_calendar")
    kis = AsyncMock(side_effect=AssertionError("KIS 조회가 새어 나갔다"))
    monkeypatch.setattr("src.api.condition.is_trading_day", kis)
    assert await tc.is_open_day(date(2026, 9, 23)) is None
    assert await tc.is_open_day(date(2026, 9, 26)) is False, "주말 규칙은 seam 보다 먼저"
    assert await tc.previous_trading_day(date(2026, 9, 28)) is None
    assert await tc.latest_passed_trading_slot(_kst(2026, 9, 28, 7, 45), time(20, 30)) is None
    assert kis.await_count == 0


async def test_C2_neutralized_default_makes_slot_gate_run(monkeypatch, caplog):
    """중립화 아래 기존 테스트가 보는 세계 = 슬롯 게이트 `calendar_unknown → RUN`."""
    _use_clock(monkeypatch, _kst(2026, 9, 21, 7, 45))
    importlib.import_module("src.engine.trading_calendar")
    once = AsyncMock(return_value={"total": 0})
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER), patch(
        "src.db.system_config.get_task_last_success",
        AsyncMock(return_value=_iso(2026, 9, 18, 20, 32)), create=True,
    ), patch("src.db.system_config.set_task_last_success", AsyncMock(), create=True):
        await run_periodic_task_loop(
            scheduler=FakeScheduler(),
            task_label="stock_master_daily_load",
            wait_time=TIME_STOCK_MASTER_DAILY_LOAD,
            once_callable=once,
            record_fn=MagicMock(),
            flush_fn=MagicMock(),
            summary_log_format="[test] total=%d",
            summary_keys=("total",),
            **{_SLOT_KW: True},
        )
    assert once.await_count == 1
    line = _one_gate(caplog, "stock_master_daily_load")
    assert _field(line, "reason") == "calendar_unknown", line


# ══════════════════════════════════════════════════════════════════════
# N. F-2 — 슬롯 게이트 never-raise (tester 발견·재현, 2026-09-25)
# ══════════════════════════════════════════════════════════════════════
# 결함: ⑤(`last_dt > now`)·⑦(`last_dt >= slot_dt`) 비교에 예외 처리가 없다. 마커가 오프셋 없는
# naive ISO 면 aware 와의 비교에서 `TypeError` 가 나고 `run_periodic_task_loop` 밖으로 전파돼
# **task 루프 전체(정기 while 포함)가 죽는다** — 그날 20:30 일봉 적재가 통째로 사라진다.
# 옛 시간 게이트는 try 로 감싸 「실행」으로 처리했다(N4 가 그 현행을 잠근다).
#
# Green 계약 (이 절이 고정한다):
#  - naive 마커 = 파싱 실패와 같은 등급 → RUN `marker_unparseable`, marker=<원본 문자열>,
#    slot=None, 달력 조회 0. naive 를 KST 로 「가정」해 fresh/stale/future 로 읽지 않는다
#    (N1b 의 세 형태가 각각 SKIP fresh · RUN stale · RUN future_marker 로 갈라 그 가정을 잡는다).
#  - leaf `latest_passed_trading_slot` 반환값이 tz-aware datetime 이 아니면 = 휴장일 모름과
#    같은 등급 → RUN `calendar_unknown`, marker=<원본>, slot=None. `marker_unparseable` 이 아닌
#    이유 = 마커는 멀쩡하고 쓸 수 없는 것은 슬롯이다(운영자가 로그를 보고 볼 곳이 달력 leaf 다).
#  - `_evaluate_slot_gate` 는 어떤 입력에도 raise 하지 않는다(TypeError 만 잡으면 str 슬롯의
#    AttributeError 가 샌다 — N3 `str`).
_NAIVE_REPRO = "2026-09-23T20:32:00"  # tester 재현 스크립트의 마커(오프셋 없음)


async def _await_no_raise(coro, what: str):
    """예외 전파를 Red 메시지로 바꾼다 — F-2 의 실패 모양은 「단언 불일치」가 아니라 「전파」다."""
    try:
        return await coro
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"F-2: {what} 가 예외를 전파했다 → task 루프 사망 — {type(e).__name__}: {e}")


async def _call_gate(monkeypatch, *, marker, now: datetime) -> tuple:
    _use_clock(monkeypatch, now)
    with patch(
        "src.db.system_config.get_task_last_success", AsyncMock(return_value=marker), create=True
    ):
        return await _await_no_raise(
            task_loop_helper._evaluate_slot_gate(
                "stock_master_daily_load", TIME_STOCK_MASTER_DAILY_LOAD, None, False
            ),
            "_evaluate_slot_gate",
        )


@pytest.mark.parametrize("kind", ["daily", "basics", "full_universe"])
async def test_N1_naive_marker_runs_as_unparseable(monkeypatch, caplog, kind):
    """실 wrapper → 실 헬퍼: naive 마커 → 전파 없음 · RUN `marker_unparseable` · once 1회.

    성공 뒤 기록되는 마커는 aware KST iso 다 — naive 마커는 첫 성공에서 스스로 치유된다.
    """
    k = _KINDS[kind]
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, set_mock, _count, cal = await _await_no_raise(
            _run_wrapper(
                monkeypatch, kind, now=_kst(2026, 9, 28, 7, 45), marker=_NAIVE_REPRO,
            ),
            f"{kind} wrapper(naive 마커)",
        )
    assert once.await_count == 1, f"{kind}: 비교 불가 마커 → 실행 의무 (파싱 실패와 같은 등급)"
    line = _one_gate(caplog, k["label"])
    assert (_field(line, "decision"), _field(line, "reason")) == ("run", "marker_unparseable"), line
    assert _field(line, "marker") == _NAIVE_REPRO, f"marker= 는 원본 문자열 그대로 (실측 {line})"
    assert _field(line, "slot") == "None", line
    assert _legacy_skip_lines(caplog, k["label"]) == [], "RUN 은 skip 행 금지"
    assert cal.calls == [], "④ 단계 판정 — naive 마커는 달력을 조회하기 전에 결정된다"
    assert set_mock.await_count == 1
    assert "+09:00" in set_mock.await_args.args[1], "성공 마커는 aware KST iso (자기 치유)"


@pytest.mark.parametrize(
    "naive",
    [_NAIVE_REPRO, "2026-09-23", "2026-09-28T09:00:00"],
    ids=["after_slot_kst_would_skip", "date_only_kst_would_stale", "kst_would_be_future"],
)
async def test_N1b_evaluate_slot_gate_naive_marker_is_unparseable(monkeypatch, naive):
    """반환 튜플 고정 — naive 를 KST 로 가정하는 Green 은 세 형태 중 하나 이상에서 붉어진다."""
    cal = _use_calendar(monkeypatch, _FakeCalendar())
    got = await _call_gate(monkeypatch, marker=naive, now=_kst(2026, 9, 28, 7, 45))
    assert got == (True, "marker_unparseable", naive, None), f"실측 {got!r}"
    assert cal.calls == []


async def test_N2_naive_marker_does_not_kill_periodic_loop(monkeypatch, caplog):
    """naive 마커가 있어도 정기 while 루프가 산다 — immediate 1회 + while 1회 발화 + 마커 2회 기록."""
    sched = FakeScheduler(running=True)
    calls = {"n": 0}

    async def _once():
        calls["n"] += 1
        # while 안(= `_wait_until` 을 한 번 이상 지난 뒤) 첫 발화에서 멈춘다. 안전 상한 5.
        if sched.wait_calls >= 1 or calls["n"] >= 5:
            sched._running = False
        return {"total": 1}

    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, _g, set_mock, sched, _cal = await _await_no_raise(
            _run_helper(
                monkeypatch, now=_kst(2026, 9, 28, 7, 45), marker=_NAIVE_REPRO,
                sched=sched, once=AsyncMock(side_effect=_once),
            ),
            "run_periodic_task_loop(naive 마커, 정기 루프 가동 중)",
        )
    assert sched.wait_calls >= 1, "while 루프 `_wait_until` 진입 증거 — 루프가 살아 있다"
    assert once.await_count == 2, "immediate 1 (marker_unparseable → RUN) + 정기 while 1"
    assert set_mock.await_count == 2, "immediate·while 성공 모두 마커 기록 (슬롯 모드)"
    line = _one_gate(caplog, "stock_master_daily_load")
    assert (_field(line, "decision"), _field(line, "reason")) == ("run", "marker_unparseable"), line


@pytest.mark.parametrize(
    "bad_slot",
    [datetime(2026, 9, 23, 20, 30), date(2026, 9, 23), "2026-09-23T20:30:00+09:00"],
    ids=["naive_datetime", "date_object", "str"],
)
async def test_N3_unusable_slot_is_calendar_unknown_never_raise(monkeypatch, bad_slot):
    """never-raise — leaf 가 계약을 어기고 aware datetime 이 아닌 슬롯을 내도 RUN `calendar_unknown`.

    현행: naive·date 는 ⑦ 비교 TypeError, str 은 `slot_dt.isoformat()` AttributeError 로 샌다.
    """
    _use_calendar(monkeypatch, _FakeCalendar())

    async def _bad_slot(*_a, **_k):
        return bad_slot

    monkeypatch.setattr("src.engine.trading_calendar.latest_passed_trading_slot", _bad_slot)
    marker = _iso(2026, 9, 23, 20, 32)
    got = await _call_gate(monkeypatch, marker=marker, now=_kst(2026, 9, 28, 7, 45))
    assert got == (True, "calendar_unknown", marker, None), f"실측 {got!r}"


async def test_N4_time_mode_naive_marker_still_runs(monkeypatch, caplog):
    """회귀 가드 — 시간 모드(master·financial)의 naive 마커는 지금처럼 try 흡수 → 실행.

    시간 모드는 벽시계 `datetime.now(KST)` 를 읽지만 aware − naive 뺄셈은 시각과 무관하게
    TypeError 라 결과가 결정적이다. 슬롯 게이트 로그·달력 조회로 새지 않는다.
    """
    label = "stock_master_master_load"
    with caplog.at_level(logging.INFO, logger=_SCHED_LOGGER):
        once, _g, set_mock, _s, cal = await _run_helper(
            monkeypatch, now=_kst(2026, 9, 28, 7, 45), marker=_NAIVE_REPRO,
            label=label, wait_time=TIME_STOCK_MASTER_MASTER_LOAD,
            **{_HOURS_KW: IMMEDIATE_FRESH_SKIP_HOURS},
        )
    assert once.await_count == 1, "시간 모드 naive 마커 → 실행 (현행 불변)"
    assert set_mock.await_count == 1, "시간 모드 성공 마커 기록 (현행 불변)"
    assert _gate_lines(caplog, label) == [], "시간 모드는 `[immediate_gate]` 를 남기지 않는다"
    assert _legacy_skip_lines(caplog, label) == []
    assert cal.calls == [], "시간 모드는 휴장일 조회 0"
