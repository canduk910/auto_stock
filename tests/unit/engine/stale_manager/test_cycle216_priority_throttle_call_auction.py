"""사이클 216 Red — `resubscribe_stale_priority` 동시호가 LOW-scoped skip + LOW-only throttle 회귀 가드.

> **선행 자문**: domain-consult (방금 확정) — 두 보강의 행위 계약 정본.
> **시정 대상**: `src/engine/stale_watcher_core.py::resubscribe_stale_priority` (376-509).
>   cycle215 로 `unsubscribe_in_pool`+`sleep(0.05)`+`subscribe` 재SEND 패턴이 이미 이식됨(현 코드).
>   본 사이클 보강 = high/low 분리(466-467) *후*, cap 조립(477) *전* 에 필터 2개 삽입.

## 보강 A) 동시호가 LOW-scoped skip
- `session_tracker.is_call_auction_now(now)` True 시 **low_targets 만 비우고(=[]) HIGH 는 그대로 처리**.
  `[stale_skip_call_auction_priority] low=N skip` WARNING 1행.
- 근거: 동시호가(08:30~09:00 / 15:20~15:30) 체결 부재 → LOW 재발사 낭비 + KIS LMS 위험.
  HIGH(보유/익일청산) 는 09:00 갭개장 손절 대비 유지 = `check_and_resubscribe_stale` cycle162
  전체 early-return 과 다른 **LOW-scoped** 스킵.

## 보강 B) LOW-only per-ticker throttle
- 신규 모듈 상수 `RESUBSCRIBE_THROTTLE_SECS = 180`(= 3 × STALE_FRESHNESS_SECS).
  **반드시 < 300s(함수 주기)** — 불변식(자기막힘, cycle215 원복 방지).
- low_targets 각 ticker: `scheduler._stale_last_resubscribe_at.get(t)` 가 datetime 이고
  `(now - last).total_seconds() < RESUBSCRIBE_THROTTLE_SECS` → **skip**(최근 재구독분 중복 차단).
- **HIGH 는 throttle 완전 면제**(300s 케이던스 자체가 LMS-safe + 손절 직결).

## 8영역 무접촉
- stale_watcher_core.py 는 realtime/ 미포함 = 8영역 아님. 본 시정은 stale_watcher_core.py 단독.
- cycle215 split-brain 재SEND(HIGH) 계약 훼손 0 — HIGH 는 두 보강 모두 면제.

## 삽입 위치 (backend-dev 인계)
- 정확한 위치 = **466-467 low_targets 계산 후, 477 targets 조립 전**.
  A(call_auction low 비우기) → B(low throttle 필터) 순, 둘 다 low_targets 만 변형.
- 상수 위치 권고 = 모듈 상단(로거 정의부 근처) `RESUBSCRIBE_THROTTLE_SECS = 3 * STALE_FRESHNESS_SECS`.
  `STALE_FRESHNESS_SECS` 는 이미 `from src.engine.stale_diagnostics import ...` 로 모듈에 존재.

## Red 시점 결과 (현 코드 기준 기대)
- T1 동시호가 LOW skip + HIGH 유지: FAIL — 현 코드는 session_tracker 미참조 → LOW 재구독.
- T2 동시호가 아닐 때 회귀 0: PASS(불변) — 현 코드도 HIGH+LOW 처리.
- T3 LOW throttle 180s내 skip: FAIL — 현 코드는 throttle 부재 → 무조건 재구독.
- T4 HIGH throttle 면제: PASS(불변) — 현 코드도 HIGH 재구독(throttle 부재이지만 결과 동일).
- T5 split-brain HIGH 복구 보존(cycle215): PASS(불변) — 현 코드에 재SEND 패턴 존재.
- T6 N<300 불변식 AST 가드: FAIL — 현 코드에 `RESUBSCRIBE_THROTTLE_SECS` 상수 부재.
- T7 cap/priority 분리 불변(throttle→cap 순서): FAIL — 현 코드는 throttle 부재 → cap 이 미필터 LOW 소비.
"""
from __future__ import annotations

import ast
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
TICK_TR_ID = "H0UNCNT0"  # scanner.TICK_TR_ID (사이클 26 이후 폴백 리터럴, cycle215 답습)


# ===========================================================================
# fixture helpers (사이클 66 / 215 답습)
# ===========================================================================
def _make_scheduler_with_high_tickers(positions: list[str] = None, ndc: set = None):
    """`TradingScheduler.__new__` + positions / _pending_next_day_clear 주입.

    사이클 66/215 `_make_scheduler_with_high_tickers` 답습 — registry mock + StaleTrackerState.
    `_stale_last_resubscribe_at` 는 property → `_stale_state.last_resubscribe_at` dict 로,
    throttle seed 는 `sched._stale_last_resubscribe_at[t] = dt` 로 주입 가능.
    """
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    object.__setattr__(sched, "_pending_next_day_clear", ndc or set())

    strategy_state = MagicMock()
    strategy_state.positions = {t: MagicMock() for t in (positions or [])}
    strategy = MagicMock(state=strategy_state)
    sched.registry = MagicMock(all=lambda: [strategy] if positions else [])
    return sched


def _make_spy_pool():
    """kis_ws_pool spy — unsubscribe_in_pool / subscribe 호출 순서 + 인자 추적 (cycle215 답습)."""
    call_log: list[tuple] = []

    def _unsub(tr_id, tr_key):
        call_log.append(("unsub", tr_id, tr_key))

    def _sub(tr_id, tr_key, *, priority="LOW", bypass_limit=False):
        call_log.append(("sub", tr_id, tr_key, priority, bypass_limit))
        return "main"

    pool = MagicMock()
    pool.unsubscribe_in_pool = AsyncMock(side_effect=_unsub)
    pool.subscribe = AsyncMock(side_effect=_sub)
    return pool, call_log


class _FakeSession:
    """KisWebSocket 최소 대역 — subscribe/unsubscribe 가 `_subscriptions` set 변이 (cycle215 답습)."""

    def __init__(self) -> None:
        self._subscriptions: set[tuple[str, str]] = set()
        self._subscriptions_acked: set[tuple[str, str]] = set()
        self.subscribe_calls: list[tuple] = []
        self.unsubscribe_calls: list[tuple] = []

    async def subscribe(self, tr_id, tr_key, *, bypass_limit=False):
        self.subscribe_calls.append((tr_id, tr_key, bypass_limit))
        self._subscriptions.add((tr_id, tr_key))
        self._subscriptions_acked.add((tr_id, tr_key))

    async def unsubscribe(self, tr_id, tr_key):
        self.unsubscribe_calls.append((tr_id, tr_key))
        self._subscriptions.discard((tr_id, tr_key))
        self._subscriptions_acked.discard((tr_id, tr_key))


def _session_tracker_mock(call_auction: bool) -> MagicMock:
    """`session_tracker` 대역 — `is_call_auction_now(now)` 가 지정 bool 을 반환.

    Green 구현은 `from src.engine.session import session_tracker` 함수-로컬 import 후
    `session_tracker.is_call_auction_now(now)` 를 호출한다 (check_and_resubscribe_stale
    cycle162 패턴). 따라서 patch 점은 `src.engine.session.session_tracker`.
    """
    m = MagicMock()
    m.is_call_auction_now = MagicMock(return_value=call_auction)
    return m


class _CapHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextmanager
def _capture_scheduler_warnings():
    """stale_watcher_core 는 `logging.getLogger("src.engine.scheduler")` 바인딩 (사이클 60 I1)."""
    logger = logging.getLogger("src.engine.scheduler")
    handler = _CapHandler()
    logger.addHandler(handler)
    prev_level = logger.level
    logger.setLevel(logging.WARNING)
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


def _order_index(call_log, kind: str, ticker: str) -> int | None:
    for i, e in enumerate(call_log):
        if e[0] == kind and e[2] == ticker:
            return i
    return None


# ===========================================================================
# T1 (HIGH, Red) — 동시호가 LOW skip + HIGH 유지
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 10:00:00", tz_offset=-9)
async def test_T1_call_auction_low_skipped_high_preserved():
    """T1 (핵심 Red): `is_call_auction_now`=True 시 LOW 후보는 재구독 미발사,
    HIGH 보유 종목은 여전히 subscribe(priority=HIGH, bypass_limit=True).

    근거(도메인): 동시호가 체결 부재 → LOW 재발사 낭비 + LMS 위험. HIGH 는 09:00
    갭개장 손절 대비 유지(cycle162 전체 early-return 과 다른 LOW-scoped).
    `[stale_skip_call_auction_priority] low=N skip` WARNING 1행.

    Red 단계 (현 코드): session_tracker 미참조 → LOW 도 재구독 + WARNING 부재 → FAIL.
    Green 단계 (시정 후): LOW skip + HIGH 유지 + WARNING 발화 → PASS.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 12, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers(positions=["005930"])  # HIGH 1
    stale_dt = base - timedelta(seconds=120)
    # HIGH 1 + LOW 2 stale
    ticker_last_tick = {"005930": stale_dt, "035420": stale_dt, "035720": stale_dt}

    pool, _call_log = _make_spy_pool()

    with _capture_scheduler_warnings() as records, \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(True)), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    # 동시호가 → HIGH 만 재구독, LOW 전량 skip
    assert result == ["005930"], (
        "동시호가 시 LOW 후보는 재구독 미대상, HIGH 만 남아야 함 (LOW-scoped skip). "
        f"현 코드는 LOW 도 재구독 → FAIL. 실제: {result}"
    )

    # HIGH 종목만 subscribe — priority=HIGH + bypass_limit=True
    high_calls = [c for c in pool.subscribe.await_args_list if c.args[1] == "005930"]
    assert len(high_calls) == 1, f"HIGH 005930 subscribe 1회 의무. 실제: {pool.subscribe.await_args_list}"
    assert high_calls[0].kwargs.get("priority") == "HIGH"
    assert high_calls[0].kwargs.get("bypass_limit") is True

    # LOW 후보는 subscribe 미호출
    low_calls = [c for c in pool.subscribe.await_args_list if c.args[1] in ("035420", "035720")]
    assert low_calls == [], (
        f"동시호가 LOW skip — LOW 후보 subscribe 금지. 현 코드는 재구독 → FAIL. 실제: {low_calls}"
    )

    # `[stale_skip_call_auction_priority] low=2 skip` WARNING 1행
    warns = [
        r for r in records
        if "[stale_skip_call_auction_priority]" in r.getMessage()
    ]
    assert len(warns) == 1, (
        "동시호가 LOW skip WARNING `[stale_skip_call_auction_priority]` 1행 발화 의무. "
        f"현 코드는 미발화 → FAIL. 실제 records: {[r.getMessage() for r in records]}"
    )
    msg = warns[0].getMessage()
    assert "low=" in msg and "2" in msg, (
        f"WARNING 메시지에 skip 된 LOW 수(low=2) 노출 의무. 실제: {msg}"
    )


# ===========================================================================
# T2 (불변, Red 시 PASS) — 동시호가 아닐 때 회귀 0
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 10:00:00", tz_offset=-9)
async def test_T2_not_call_auction_no_regression():
    """T2 (회귀 가드): `is_call_auction_now`=False → 기존대로 HIGH+LOW 모두 재구독.

    동시호가 skip 은 True 일 때만 — False 는 cycle215 이후 현 행위 완전 보존.
    `[stale_skip_call_auction_priority]` WARNING 미발화.

    Red/Green 모두 PASS (LOW-scoped skip 이 비-동시호가 경로를 훼손하지 않음을 고정).
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 12, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers(positions=["005930"])
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"005930": stale_dt, "035420": stale_dt, "035720": stale_dt}

    pool, _call_log = _make_spy_pool()

    with _capture_scheduler_warnings() as records, \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert set(result) == {"005930", "035420", "035720"}, (
        f"비-동시호가: HIGH+LOW 모두 재구독 (회귀 0). 실제: {result}"
    )
    # HIGH 는 HIGH, LOW 는 LOW priority
    for call in pool.subscribe.await_args_list:
        ticker = call.args[1]
        if ticker == "005930":
            assert call.kwargs.get("priority") == "HIGH"
            assert call.kwargs.get("bypass_limit") is True
        else:
            assert call.kwargs.get("priority") == "LOW"
            assert call.kwargs.get("bypass_limit") is False
    # 동시호가 WARNING 미발화
    assert not [r for r in records if "[stale_skip_call_auction_priority]" in r.getMessage()], (
        "비-동시호가 경로에서 동시호가 skip WARNING 발화 금지"
    )


# ===========================================================================
# T3 (HIGH, Red) — LOW throttle 180s내 skip / 초과 재구독
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 10:00:00", tz_offset=-9)
async def test_T3_low_throttle_skips_recent_resubscribe():
    """T3 (핵심 Red): LOW 후보의 `_stale_last_resubscribe_at` 가 throttle 이내(180s)면 skip,
    초과(또는 미기록)면 재구독.

    시나리오:
      - "035000": seed 없음 → 재구독 (미기록 = 최근 재구독 아님).
      - "035420": last = now-100s (< 180) → **skip**.
      - "035720": last = now-200s (>= 180) → 재구독.

    Red 단계 (현 코드): throttle 부재 → 3 종목 전부 재구독 → "035420" 포함 → FAIL.
    Green 단계 (시정 후): "035420" skip → result = ["035000","035720"] → PASS.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 12, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers()  # HIGH 0 → 모두 LOW 후보
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"035000": stale_dt, "035420": stale_dt, "035720": stale_dt}

    # throttle seed 주입 (property → _stale_state.last_resubscribe_at dict)
    sched._stale_last_resubscribe_at["035420"] = base - timedelta(seconds=100)  # 이내 → skip
    sched._stale_last_resubscribe_at["035720"] = base - timedelta(seconds=200)  # 초과 → 재구독

    pool, _call_log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert "035420" not in result, (
        "throttle 이내(now-100s < 180) LOW 는 재구독 skip 의무. "
        "현 코드는 throttle 부재 → 무조건 재구독 → FAIL. "
        f"실제: {result}"
    )
    assert result == ["035000", "035720"], (
        f"throttle: 미기록/초과 LOW 만 재구독 (sorted). 기대: ['035000','035720'], 실제: {result}"
    )
    # skip 된 035420 은 subscribe 미호출
    assert not [c for c in pool.subscribe.await_args_list if c.args[1] == "035420"], (
        "throttle skip 종목은 subscribe 미호출 의무"
    )
    # 재구독분은 LOW priority
    for call in pool.subscribe.await_args_list:
        assert call.kwargs.get("priority") == "LOW"
        assert call.kwargs.get("bypass_limit") is False


# ===========================================================================
# T4 (불변, Red 시 PASS) — HIGH throttle 완전 면제
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 10:00:00", tz_offset=-9)
async def test_T4_high_exempt_from_throttle():
    """T4 (불변 가드): HIGH 보유 종목은 `_stale_last_resubscribe_at` 가 throttle 훨씬 이내
    (now-10s)여도 **반드시 재구독** (priority=HIGH, bypass_limit=True).

    HIGH throttle 면제 근거: 300s 케이던스 자체가 LMS-safe + 손절 직결.
    현 코드는 throttle 자체가 없어 HIGH 재구독 → PASS. 시정 후에도 HIGH 면제로 재구독 →
    PASS. throttle 도입 후 HIGH 를 실수로 조이는 회귀를 고정하는 게이트.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 12, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers(positions=["005930"])  # HIGH 1
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"005930": stale_dt}

    # HIGH 를 throttle 훨씬 이내로 seed — 그럼에도 재구독 의무
    sched._stale_last_resubscribe_at["005930"] = base - timedelta(seconds=10)

    pool, _call_log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["005930"], (
        f"HIGH 는 throttle seed(now-10s) 무관 재구독 의무 (throttle 면제). 실제: {result}"
    )
    high_calls = [c for c in pool.subscribe.await_args_list if c.args[1] == "005930"]
    assert len(high_calls) == 1
    assert high_calls[0].kwargs.get("priority") == "HIGH"
    assert high_calls[0].kwargs.get("bypass_limit") is True


# ===========================================================================
# T5 (불변, Red 시 PASS) — split-brain HIGH 복구 보존 (cycle215)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 10:00:00", tz_offset=-9)
async def test_T5_split_brain_high_recovery_preserved_under_new_gates():
    """T5 (cycle215 회귀 가드): split-brain(`_ticker_to_session[high]=main` 잔존 +
    `_subscriptions` 부재) HIGH 종목이 **동시호가/throttle 과 무관하게**
    `unsubscribe_in_pool` → `subscribe` 로 재SEND 되어야 한다 (cycle215 계약 훼손 0).

    본 사이클 두 보강(동시호가 LOW skip + LOW throttle)은 HIGH 를 전부 면제 —
    call_auction=True + HIGH throttle seed(now-5s) 를 동시에 걸어도 HIGH 재SEND 보존.

    실경로: 진짜 `WebsocketPool` + 가짜 메인 세션으로 dedup 가드를 실제 통과.
    현 코드(cycle215 이식됨): HIGH 재SEND → PASS. 시정 후에도 HIGH 면제 → PASS.
    """
    from src.engine import stale_manager
    from src.realtime.websocket_pool import WebsocketPool

    base = datetime(2026, 8, 12, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers(positions=["001450"])  # HIGH 보유
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"001450": stale_dt}

    # HIGH throttle seed(면제 확인) — now-5s 로 매우 최근
    sched._stale_last_resubscribe_at["001450"] = base - timedelta(seconds=5)

    fake = _FakeSession()
    pool = WebsocketPool()
    pool._main = fake
    pool._quotes = []
    # split-brain: 풀 매핑 잔존 + 세션 _subscriptions 공집합 (거부 후 discard 상태)
    pool._ticker_to_session = {"001450": fake}

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(True)), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["001450"], (
        f"동시호가+throttle seed 무관 HIGH 재구독 대상 포함 의무. 실제: {result}"
    )
    assert len(fake.subscribe_calls) == 1, (
        "split-brain HIGH 종목은 dedup 가드를 뚫고 세션 subscribe 실호출(재SEND) 의무 "
        "(cycle215 계약, 동시호가/throttle 면제). "
        f"실제 세션 subscribe 호출: {fake.subscribe_calls}"
    )
    assert (TICK_TR_ID, "001450") in fake._subscriptions, (
        f"재SEND 후 세션 `_subscriptions` 복원 의무 (split-brain 해소). 실제: {fake._subscriptions}"
    )
    assert fake.subscribe_calls[0][2] is True, (
        f"HIGH 종목 세션 subscribe 는 bypass_limit=True 의무. 실제: {fake.subscribe_calls[0]}"
    )


# ===========================================================================
# T6 (MEDIUM, Red) — N<300s 불변식 (AST + 런타임 가드)
# ===========================================================================
def test_T6_throttle_constant_under_300_invariant():
    """T6 (불변식 AST 가드): `RESUBSCRIBE_THROTTLE_SECS` 상수가 stale_watcher_core.py 모듈
    레벨에 정의되고, **< 300s**(함수 주기) + `== 3 × STALE_FRESHNESS_SECS`(=180) 여야 한다.

    자기막힘 = cycle215 원복(throttle >= 함수 주기) 방지. throttle >= 300 이면 재구독
    skip 이 5분 케이던스를 넘겨 LOW stale 이 다음 사이클에도 재구독 안 되는 위험 → 금지.

    Red 단계 (현 코드): 상수 부재 → AST 미발견 + import 실패 → FAIL.
    Green 단계 (시정 후): 모듈 레벨 정의 + <300 + ==180 → PASS.
    """
    from src.engine.stale_diagnostics import STALE_FRESHNESS_SECS

    engine_root = Path(__file__).parent.parent.parent.parent.parent / "src/engine"
    core_path = engine_root / "stale_watcher_core.py"
    assert core_path.exists(), "stale_watcher_core.py 미존재"

    tree = ast.parse(core_path.read_text())

    # 모듈 레벨 assignment `RESUBSCRIBE_THROTTLE_SECS = ...` 존재 의무 (함수-로컬 금지)
    module_level_names: set[str] = set()
    for node in tree.body:  # 모듈 top-level 만 순회 (함수 내부 제외)
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    module_level_names.add(tgt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            module_level_names.add(node.target.id)

    assert "RESUBSCRIBE_THROTTLE_SECS" in module_level_names, (
        "시정 의무: `RESUBSCRIBE_THROTTLE_SECS` 를 stale_watcher_core.py 모듈 레벨에 신설. "
        "현 코드는 부재 → FAIL. (권고: `RESUBSCRIBE_THROTTLE_SECS = 3 * STALE_FRESHNESS_SECS`)"
    )

    # 런타임 값 불변식
    try:
        from src.engine.stale_watcher_core import RESUBSCRIBE_THROTTLE_SECS
    except ImportError:  # pragma: no cover - Red 단계 방어
        pytest.fail("RESUBSCRIBE_THROTTLE_SECS import 실패 (Red) — backend-dev 신설 의무")

    assert RESUBSCRIBE_THROTTLE_SECS < 300, (
        f"불변식 위반: throttle({RESUBSCRIBE_THROTTLE_SECS}) 는 함수 주기 300s 미만이어야 함 "
        "(>= 300 이면 재구독 skip 이 케이던스를 넘겨 LOW stale 재구독 사각 = cycle215 원복)."
    )
    assert RESUBSCRIBE_THROTTLE_SECS == 3 * STALE_FRESHNESS_SECS, (
        f"throttle 은 3 × STALE_FRESHNESS_SECS(=180) 정합 의무. "
        f"실제: {RESUBSCRIBE_THROTTLE_SECS} (STALE_FRESHNESS_SECS={STALE_FRESHNESS_SECS})"
    )


# ===========================================================================
# T7 (HIGH, Red) — throttle → cap 순서 (cap/priority 분리 계약 훼손 0)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 10:00:00", tz_offset=-9)
async def test_T7_throttle_applied_before_cap_contract_preserved():
    """T7 (순서 불변): throttle 필터는 high/low 분리(466-467) *후*, cap 조립(477) *전* 에
    들어가야 한다 — cap 은 **throttle 통과분** LOW 에 적용되어야 하며 cap 계약
    `high + low[:cap-len(high)]` 은 훼손 0.

    시나리오: HIGH 3 + LOW 12, LOW 앞 4종목("000001"~"000004") throttle seed(now-100s).
      - throttle 후 eligible LOW = "000005"~"000012" (8).
      - cap=10 → LOW slots = 10-3 = 7 → result LOW = "000005"~"000011".
      - result = HIGH 3 + LOW 7 = 10.

    throttle 을 cap *뒤* 에 넣으면(잘못된 위치) cap 이 미필터 LOW["000001"~"000007"] 를
    먼저 소비 → throttle 종목 포함 = 계약 위반. 본 테스트가 순서를 고정한다.

    Red 단계 (현 코드): throttle 부재 → cap 이 LOW[:7]=["000001".."000007"] 소비 →
                       "000001" 포함 → FAIL.
    Green 단계 (시정 후): throttle→cap 순서 → "000001".."000004" 제외 → PASS.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 12, 10, 0, 0, tzinfo=KST)
    high_tickers = ["005001", "005002", "005003"]  # HIGH 3
    low_tickers = [f"{i:06d}" for i in range(1, 13)]  # 000001~000012 (LOW 12)
    sched = _make_scheduler_with_high_tickers(positions=high_tickers)

    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {t: stale_dt for t in (high_tickers + low_tickers)}

    # LOW 앞 4종목 throttle seed (이내) → skip 대상
    throttled = ["000001", "000002", "000003", "000004"]
    for t in throttled:
        sched._stale_last_resubscribe_at[t] = base - timedelta(seconds=100)

    pool, _call_log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert len(result) == 10, f"cap=10 정확 적용 (HIGH 3 + eligible LOW 7). 실제: {len(result)} — {result}"

    # HIGH 3 절대 보장 (cap/priority 분리 계약)
    high_in_result = [t for t in result if t in high_tickers]
    assert set(high_in_result) == set(high_tickers), (
        f"HIGH 3 모두 보장 의무 (cap 계약 훼손 0). 실제 HIGH: {high_in_result}"
    )

    # throttle 종목은 cap 소비 *전* 제거 → result 부재
    for t in throttled:
        assert t not in result, (
            f"throttle 종목 {t} 는 cap 조립 *전* 제거 의무. 현 코드는 throttle 부재 → "
            f"cap 이 미필터 LOW 먼저 소비 → 포함 = FAIL. 실제 result: {result}"
        )

    # cap 은 throttle 통과분에만 적용 → LOW = 000005~000011 (sorted 7)
    low_in_result = [t for t in result if t in low_tickers]
    assert low_in_result == [f"{i:06d}" for i in range(5, 12)], (
        f"throttle→cap 순서: eligible LOW['000005'..'000012'][:7] = ['000005'..'000011']. "
        f"실제 LOW: {low_in_result}"
    )
