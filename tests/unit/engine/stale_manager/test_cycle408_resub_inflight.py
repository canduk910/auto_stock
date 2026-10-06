"""cycle408-L4 — K stale watcher 와 5분 우선 재구독의 같은 종목 경합 차단.

> 명세: `_workspace/refactor/2026-10-04_eight_area_observability_fixes.md` L4 절, 안 A.

두 재등록 경로(`check_and_resubscribe_stale` 120초 · `resubscribe_stale_priority`
5분)는 서로 다른 task 라 공유 잠금이 없다. 한쪽이 종목 X 를 해제하고(풀 매핑 pop)
`subscribe` 를 기다리는 사이 다른 쪽이 같은 X 를 해제하면 매핑이 이미 비어 있어
`websocket_pool.unsubscribe_in_pool` 이 **메인 세션으로 폴백**한다 → 메인은 X 를
들고 있지 않은데 UNSUBSCRIBE 를 보낸다 → KIS `OPSP0003 not found` ERROR
(10-01 19:40:48 실측). 둘 다 매핑이 빈 동안 `subscribe` 의 LOW 갈래에 들어가면
서로 다른 세션을 고를 수 있다(이중 구독 — 이론, 미관측).

시정 = `stale_watcher_core` 모듈 전역 `_RESUB_INFLIGHT` 종목 단위 진행 표식.
세 해제 지점 바로 앞에서 claim, 실패하면 그 종목을 이번 회차에서 건너뛴다.
`finally` 로 완료·예외·취소 모두에서 푼다.

R1 경합 재현(K 먼저) · R2 거울상(우선 재구독 먼저 — K 의 1~5회 갈래·force_retry
갈래 각각) · R3 표식 해제 보장(예외·취소 — 남으면 그 종목 재등록 영구 정지) ·
R4 HIGH 인자 불변 · S 구조 가드(claim 과 해제 사이 await 0, finally 해제).

가짜 풀은 `unsubscribe_in_pool` 의 실제 의미(매핑 pop → 없으면 메인 폴백)와
`subscribe` 의 매핑 기록 시점(세션 subscribe await **뒤**)을 그대로 흉내 낸다.
"""
from __future__ import annotations

import ast
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
TR = "H0STCNT0"
X = "035420"
_REPO_ROOT = Path(__file__).resolve().parents[4]
_CORE = _REPO_ROOT / "src" / "engine" / "stale_watcher_core.py"


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _core():
    from src.engine import stale_watcher_core as core

    return core


def _inflight() -> set:
    core = _core()
    s = getattr(core, "_RESUB_INFLIGHT", None)
    assert isinstance(s, set), (
        "cycle408 — `stale_watcher_core._RESUB_INFLIGHT: set[str]` 모듈 전역 표식 부재"
    )
    return s


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    core = _core()
    s = getattr(core, "_RESUB_INFLIGHT", None)
    if isinstance(s, set):
        s.clear()
    # cycle252 패턴 — no_feed 레지스트리 무력화(이 사이클의 검증 대상 아님)
    from src.engine import no_feed_registry as reg

    async def _ensure_fresh(tickers, **kwargs):
        return None

    monkeypatch.setattr(reg, "ensure_fresh", _ensure_fresh)
    monkeypatch.setattr(reg, "is_no_feed", lambda t: False)
    from src.engine.daily_emit_cap import KstDailyEmitCap

    monkeypatch.setattr(core, "_no_feed_held_logged", KstDailyEmitCap())
    # 동시호가 아님
    st = MagicMock()
    st.is_call_auction_now = MagicMock(return_value=False)
    import src.engine.session as session_mod

    monkeypatch.setattr(session_mod, "session_tracker", st)
    # 채널 킬스위치 재조회·전환 사이클은 DB 를 부른다 — 이 사이클의 검증 대상 아님.
    from src.engine import tick_channel_mode as tcm
    from src.engine import tick_channel_switch as tcs

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(tcm, "refresh_mode", _noop)
    monkeypatch.setattr(tcm, "refresh_switch_params", _noop)
    monkeypatch.setattr(tcs, "run_switch_cycle", _noop)
    yield
    if isinstance(s, set):
        s.clear()


class _YieldSleep:
    """`stale_watcher_core.asyncio` 대역 — 시간 대기 없이 이벤트 루프에 양보만."""

    async def sleep(self, secs: float) -> None:
        await asyncio.sleep(0)


class _FakeSession:
    def __init__(self, name: str) -> None:
        self.name = name
        self._subscriptions: set[tuple[str, str]] = set()
        self.subscribe_calls: list[tuple[str, str]] = []
        self.unsubscribe_calls: list[tuple[str, str]] = []

    async def subscribe(self, tr_id: str, tr_key: str) -> None:
        self.subscribe_calls.append((tr_id, tr_key))
        self._subscriptions.add((tr_id, tr_key))

    async def unsubscribe(self, tr_id: str, tr_key: str) -> None:
        # 실제 KisWebSocket 은 집합에 없어도 SEND 한다(`if self._ws:`) — 그 SEND 가 OPSP0003.
        self.unsubscribe_calls.append((tr_id, tr_key))
        self._subscriptions.discard((tr_id, tr_key))


class _FakePool:
    """`WebsocketPool` 의 해제·구독 의미만 흉내 낸 대역.

    - `unsubscribe_in_pool`: 매핑 pop → 없으면 **메인 폴백**(websocket_pool.py:741-745).
    - `subscribe`: 게이트(Event) 대기 → 매핑이 이미 있으면 중복 noop → 세션 subscribe
      **뒤**에 매핑 기록(websocket_pool.py:457 와 같은 순서).
    """

    def __init__(self) -> None:
        self._main = _FakeSession("main")
        self._quote = _FakeSession("quote")
        self._ticker_to_session: dict[str, _FakeSession] = {}
        self._ticker_to_tr_id: dict[str, str] = {}
        self._subscribed_at: dict = {}
        self.gates: dict[str, asyncio.Event] = {}
        self.entered: dict[str, asyncio.Event] = {}
        self.raise_on_subscribe: set[str] = set()
        self.snapshot_override: set[str] | None = None
        self.subscribe_calls: list[tuple[str, str, str, bool]] = []
        self.unsubscribe_in_pool_calls: list[tuple[str, str]] = []

    def seed(self, ticker: str, session: _FakeSession) -> None:
        session._subscriptions.add((TR, ticker))
        self._ticker_to_session[ticker] = session
        self._ticker_to_tr_id[ticker] = TR

    def get_subscribed_tickers(self) -> set[str]:
        if self.snapshot_override is not None:
            snap = set(self.snapshot_override)
            self.snapshot_override = None  # 한 번만 낡은 스냅샷
            return snap
        return {k for s in (self._main, self._quote) for (_tr, k) in s._subscriptions}

    def get_subscriptions_by_session(self) -> dict:
        return {}

    async def unsubscribe_in_pool(self, tr_id: str, tr_key: str) -> None:
        self.unsubscribe_in_pool_calls.append((tr_id, tr_key))
        sess = self._ticker_to_session.pop(tr_key, None)
        self._ticker_to_tr_id.pop(tr_key, None)
        if sess is None:
            sess = self._main  # 메인 폴백 — 결함의 출구
        await sess.unsubscribe(tr_id, tr_key)

    async def subscribe(self, tr_id, tr_key, *, priority="LOW", bypass_limit=False):
        self.subscribe_calls.append((tr_id, tr_key, priority, bypass_limit))
        ev = self.entered.get(tr_key)
        if ev is not None:
            ev.set()
        gate = self.gates.get(tr_key)
        if gate is not None:
            await gate.wait()
        if tr_key in self.raise_on_subscribe:
            raise RuntimeError("subscribe 실패(테스트)")
        if tr_key in self._ticker_to_session:
            return self._ticker_to_session[tr_key].name  # 중복 noop
        chosen = self._main if priority == "HIGH" else self._quote
        await chosen.subscribe(tr_id, tr_key)
        self._ticker_to_session[tr_key] = chosen
        self._ticker_to_tr_id[tr_key] = tr_id
        return chosen.name

    def total_unsubscribe_sends(self, ticker: str) -> int:
        return sum(
            1 for s in (self._main, self._quote) for (_t, k) in s.unsubscribe_calls if k == ticker
        )

    def holders(self, ticker: str) -> list[str]:
        return [s.name for s in (self._main, self._quote) if (TR, ticker) in s._subscriptions]


def _install(monkeypatch, pool: _FakePool, *, stale=(X,)):
    import src.engine.scanner as scanner_mod
    import src.realtime.websocket_pool as wp_mod

    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool)
    base = datetime.now(KST)
    monkeypatch.setattr(
        scanner_mod, "ticker_last_tick", {t: base - timedelta(seconds=120) for t in stale}
    )
    monkeypatch.setattr(_core(), "asyncio", _YieldSleep())


def _make_sched(*, positions=(), retry=None, last_at=None):
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = dict(retry or {})
    sched._stale_last_resubscribe_at = dict(last_at or {})
    sched._stale_force_retry_history = {}
    sched._pending_next_day_clear = set()
    sched._running = True
    sched._STALE_DETAIL_TICKER_CAP = 20
    fake_state = MagicMock()
    fake_state.positions = {t: MagicMock() for t in positions}
    fake_strategy = MagicMock()
    fake_strategy.state = fake_state
    sched.registry = MagicMock(all=MagicMock(return_value=[fake_strategy]))
    return sched


async def _wait(ev: asyncio.Event) -> None:
    await asyncio.wait_for(ev.wait(), timeout=2.0)


async def _bounded(coro, gate: asyncio.Event):
    """두 번째 경로를 돌린다. 시정 전 코드는 같은 종목 subscribe 게이트에 같이 묶여
    멈추므로(그 자체가 결함의 증거) 1초 뒤 게이트를 열어 결과를 받아 단언으로 붉게 만든다."""
    t = asyncio.create_task(coro)
    done, _ = await asyncio.wait({t}, timeout=1.0)
    if not done:
        gate.set()
    return await asyncio.wait_for(t, timeout=2.0)


# ===========================================================================
# R1 — K watcher 가 X 를 재등록 중일 때 우선 재구독(낡은 스냅샷에 X 포함)이 온다
# ===========================================================================
async def test_r1_priority_skips_ticker_while_k_watcher_inflight_no_main_fallback(monkeypatch):
    core = _core()
    pool = _FakePool()
    pool.seed(X, pool._quote)
    _install(monkeypatch, pool)
    sched = _make_sched()

    gate = asyncio.Event()
    pool.gates[X] = gate
    pool.entered[X] = asyncio.Event()

    k_task = asyncio.create_task(core.check_and_resubscribe_stale(sched))
    await _wait(pool.entered[X])
    # K watcher 는 X 를 이미 해제(매핑 pop)하고 subscribe 대기 중.
    assert X not in pool._ticker_to_session

    # 우선 재구독은 K 가 pop 하기 전에 찍힌 스냅샷을 쓴다(경로 ①).
    pool.snapshot_override = {X}
    del pool.entered[X]
    result = await _bounded(core.resubscribe_stale_priority(sched, cap=10), gate)

    assert pool._main.unsubscribe_calls == [], (
        "메인 폴백 헛 UNSUBSCRIBE(OPSP0003) 금지 — 다른 경로가 X 를 재등록 중이면 건너뛴다. "
        f"main.unsubscribe_calls={pool._main.unsubscribe_calls}"
    )
    assert pool.total_unsubscribe_sends(X) == 1, "UNSUBSCRIBE 는 K watcher 의 1회(보조 세션)뿐"
    assert X not in result, f"건너뛴 종목은 재구독 결과에 넣지 않는다 — result={result}"
    assert len([c for c in pool.subscribe_calls if c[1] == X]) == 1, (
        "우선 재구독은 X 의 subscribe 도 내지 않는다"
    )

    gate.set()
    await asyncio.wait_for(k_task, timeout=2.0)
    assert pool.holders(X) == ["quote"], f"최종 구독 1곳 — holders={pool.holders(X)}"
    assert pool._ticker_to_session[X] is pool._quote
    assert _inflight() == set(), "K watcher 완료 뒤 표식은 비어야 한다"


async def test_r1b_priority_skip_does_not_stamp_last_resubscribe(monkeypatch):
    core = _core()
    pool = _FakePool()
    pool.seed(X, pool._quote)
    _install(monkeypatch, pool)
    sched = _make_sched()

    gate = asyncio.Event()
    pool.gates[X] = gate
    pool.entered[X] = asyncio.Event()
    k_task = asyncio.create_task(core.check_and_resubscribe_stale(sched))
    await _wait(pool.entered[X])
    pool.snapshot_override = {X}
    del pool.entered[X]
    await _bounded(core.resubscribe_stale_priority(sched, cap=10), gate)
    assert X not in sched._stale_last_resubscribe_at, (
        "건너뛴 쪽은 한 일이 없으므로 `_stale_last_resubscribe_at` 을 찍지 않는다"
    )
    gate.set()
    await asyncio.wait_for(k_task, timeout=2.0)
    assert X in sched._stale_last_resubscribe_at, "K watcher 완료 쪽은 그대로 찍는다"


# ===========================================================================
# R2 — 거울상: 우선 재구독이 X 를 재등록 중일 때 K watcher(1~5회 · force_retry)가 온다
# ===========================================================================
@pytest.mark.parametrize("branch", ["one_to_five", "force_retry"])
async def test_r2_k_watcher_skips_ticker_while_priority_inflight(monkeypatch, branch):
    from src.engine.stale_diagnostics import MAX_STALE_RETRIES

    core = _core()
    pool = _FakePool()
    pool.seed(X, pool._quote)
    _install(monkeypatch, pool)
    retry = {X: MAX_STALE_RETRIES + 2} if branch == "force_retry" else None
    sched = _make_sched(retry=retry)

    gate = asyncio.Event()
    pool.gates[X] = gate
    pool.entered[X] = asyncio.Event()
    p_task = asyncio.create_task(core.resubscribe_stale_priority(sched, cap=10))
    await _wait(pool.entered[X])
    del pool.entered[X]

    # K watcher 의 stale 소스는 `get_subscribed_tickers()` — 해제 직후라 X 가 빠졌으므로
    # 경로 ② 의 「K 가 대상 선정 시점엔 X 를 봤다」를 낡은 스냅샷으로 고정한다.
    pool.snapshot_override = {X}
    await _bounded(core.check_and_resubscribe_stale(sched), gate)

    assert pool._main.unsubscribe_calls == [], (
        f"[{branch}] 메인 폴백 헛 UNSUBSCRIBE 금지 — main={pool._main.unsubscribe_calls}"
    )
    assert pool.total_unsubscribe_sends(X) == 1
    assert len([c for c in pool.subscribe_calls if c[1] == X]) == 1
    if branch == "force_retry":
        assert sched._stale_force_retry_history.get(X, []) == [], (
            "건너뛴 force_retry 는 시간당 cap 이력을 소모하지 않는다"
        )

    gate.set()
    result = await asyncio.wait_for(p_task, timeout=2.0)
    assert result == [X]
    assert pool.holders(X) == ["quote"]
    assert _inflight() == set()


# ===========================================================================
# R3 — 표식 해제 보장 (남으면 그 종목 재등록 영구 정지 — 가장 비싼 실패)
# ===========================================================================
@pytest.mark.parametrize("path", ["k_one_to_five", "k_force_retry", "priority"])
async def test_r3_inflight_released_when_subscribe_raises(monkeypatch, path):
    from src.engine.stale_diagnostics import MAX_STALE_RETRIES

    core = _core()
    pool = _FakePool()
    pool.seed(X, pool._quote)
    _install(monkeypatch, pool)
    pool.raise_on_subscribe.add(X)
    retry = {X: MAX_STALE_RETRIES + 2} if path == "k_force_retry" else None
    sched = _make_sched(retry=retry)

    if path == "priority":
        await core.resubscribe_stale_priority(sched, cap=10)
    else:
        await core.check_and_resubscribe_stale(sched)
    assert pool.unsubscribe_in_pool_calls, "전제: 해제 지점을 지났다"
    assert _inflight() == set(), f"[{path}] subscribe 예외 뒤 표식이 남았다 = 재등록 영구 정지"

    # 다음 회차는 정상으로 그 종목을 다시 다룬다(건너뛰지 않는다).
    pool.raise_on_subscribe.clear()
    pool.seed(X, pool._quote)
    before = len(pool.unsubscribe_in_pool_calls)
    await core.resubscribe_stale_priority(sched, cap=10)
    assert len(pool.unsubscribe_in_pool_calls) == before + 1


@pytest.mark.parametrize("path", ["k_one_to_five", "k_force_retry", "priority"])
async def test_r3b_inflight_released_when_task_cancelled(monkeypatch, path):
    """15:20·20:00 `_scan_task.cancel()` / watcher 종료 = CancelledError 는 except Exception 밖."""
    from src.engine.stale_diagnostics import MAX_STALE_RETRIES

    core = _core()
    pool = _FakePool()
    pool.seed(X, pool._quote)
    _install(monkeypatch, pool)
    retry = {X: MAX_STALE_RETRIES + 2} if path == "k_force_retry" else None
    sched = _make_sched(retry=retry)
    pool.gates[X] = asyncio.Event()  # 영원히 안 열린다
    pool.entered[X] = asyncio.Event()

    if path == "priority":
        task = asyncio.create_task(core.resubscribe_stale_priority(sched, cap=10))
    else:
        task = asyncio.create_task(core.check_and_resubscribe_stale(sched))
    await _wait(pool.entered[X])
    assert X in _inflight()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _inflight() == set(), f"[{path}] 취소 뒤 표식이 남았다 = 재등록 영구 정지"


# ===========================================================================
# R4 — HIGH(보유) 인자 불변 + 경합 시에도 HIGH 인자로 재등록된다
# ===========================================================================
async def test_r4_high_args_unchanged_without_contention(monkeypatch):
    core = _core()
    pool = _FakePool()
    pool.seed(X, pool._main)
    _install(monkeypatch, pool)
    sched = _make_sched(positions=[X])

    await core.check_and_resubscribe_stale(sched)
    pool.seed(X, pool._main)
    await core.resubscribe_stale_priority(sched, cap=10)

    x_calls = [c for c in pool.subscribe_calls if c[1] == X]
    assert len(x_calls) == 2
    assert all(c[2] == "HIGH" and c[3] is True for c in x_calls), x_calls
    assert _inflight() == set()


async def test_r4b_high_contention_reregistered_once_with_high_args(monkeypatch):
    core = _core()
    pool = _FakePool()
    pool.seed(X, pool._main)
    _install(monkeypatch, pool)
    sched = _make_sched(positions=[X])

    gate = asyncio.Event()
    pool.gates[X] = gate
    pool.entered[X] = asyncio.Event()
    k_task = asyncio.create_task(core.check_and_resubscribe_stale(sched))
    await _wait(pool.entered[X])
    pool.snapshot_override = {X}
    del pool.entered[X]
    result = await _bounded(core.resubscribe_stale_priority(sched, cap=10), gate)
    assert X not in result
    assert pool._main.unsubscribe_calls == [(TR, X)], "HIGH 도 UNSUBSCRIBE 는 1회뿐"
    gate.set()
    await asyncio.wait_for(k_task, timeout=2.0)
    x_calls = [c for c in pool.subscribe_calls if c[1] == X]
    assert x_calls == [(TR, X, "HIGH", True)], x_calls
    assert pool.holders(X) == ["main"]


# ===========================================================================
# S — 구조 가드: 해제 지점 3곳 모두 claim 뒤 · claim 과 해제 사이 await 0 · finally 해제
# ===========================================================================
def _funcs():
    tree = ast.parse(_CORE.read_text(encoding="utf-8"))
    return {
        n.name: n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _is_call(node, name: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    return (isinstance(f, ast.Name) and f.id == name) or (
        isinstance(f, ast.Attribute) and f.attr == name
    )


def test_s1_every_unsubscribe_in_pool_is_inside_claimed_try_with_finally_release():
    funcs = _funcs()
    found = 0
    for fname in ("check_and_resubscribe_stale", "resubscribe_stale_priority"):
        fn = funcs[fname]
        for tr in ast.walk(fn):
            if not isinstance(tr, ast.Try):
                continue
            body_calls = [
                n for stmt in tr.body for n in ast.walk(stmt)
                if _is_call(n, "unsubscribe_in_pool")
            ]
            if not body_calls:
                continue
            found += len(body_calls)
            fin_calls = [n for stmt in tr.finalbody for n in ast.walk(stmt)]
            assert any(_is_call(n, "_release_resub") for n in fin_calls), (
                f"{fname}: unsubscribe_in_pool 을 감싼 try 에 finally `_release_resub` 가 없다"
            )
    assert found == 3, f"해제 지점은 3곳이어야 한다(829·863·1104) — 실제 {found}"


def test_s2_claim_precedes_each_guarded_try_with_no_await_between():
    """claim 문장 → (await 없는 문장들) → 해제 try. claim 과 pop 사이 await 0 이 원자성 근거."""
    funcs = _funcs()
    for fname in ("check_and_resubscribe_stale", "resubscribe_stale_priority"):
        fn = funcs[fname]
        for parent in ast.walk(fn):
            for field in ("body", "orelse", "finalbody"):
                stmts = getattr(parent, field, None)
                if not isinstance(stmts, list):
                    continue
                for i, stmt in enumerate(stmts):
                    if not isinstance(stmt, ast.Try):
                        continue
                    if not any(
                        _is_call(n, "unsubscribe_in_pool")
                        for s in stmt.body for n in ast.walk(s)
                    ):
                        continue
                    prev = stmts[i - 1] if i > 0 else None
                    assert prev is not None and any(
                        _is_call(n, "_claim_resub") for n in ast.walk(prev)
                    ), f"{fname}: 해제 try 바로 앞 문장에 `_claim_resub` 가 없다"
                    assert not any(isinstance(n, ast.Await) for n in ast.walk(prev)), (
                        f"{fname}: claim 문장 안에 await 가 있다"
                    )
                    # try 본문 첫 await 까지(= unsubscribe_in_pool 또는 pop 뒤 subscribe) 사이
                    # claim 이 무효화될 await 이 없어야 한다: 첫 await 대상은 해제 또는 subscribe.
                    first_await = next(
                        (n for s in stmt.body for n in ast.walk(s) if isinstance(n, ast.Await)),
                        None,
                    )
                    assert first_await is not None and (
                        _is_call(first_await.value, "unsubscribe_in_pool")
                        or _is_call(first_await.value, "subscribe")
                    ), f"{fname}: claim 뒤 첫 await 가 해제·구독이 아니다"


def test_s3_claim_helpers_are_sync():
    funcs = _funcs()
    for name in ("_claim_resub", "_release_resub"):
        assert name in funcs, f"헬퍼 `{name}` 부재"
        assert isinstance(funcs[name], ast.FunctionDef), f"`{name}` 는 동기 함수여야 한다"
        assert not any(isinstance(n, ast.Await) for n in ast.walk(funcs[name]))
