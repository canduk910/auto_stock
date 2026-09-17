"""cycle298 (재기동 시 시세 구독 공백) — `_scan_loop` 첫 회차 지연을 호출부가 정한다.

명세 정본 = `_workspace/red/cycle298_scan_loop_subscribe_first_spec.md` §2·§3.
배경 정본 = `_workspace/00_URGENT_WORKLIST.md` 「재기동 시 시세 구독 공백」.

실측(2026-09-17 16:11 배포): 프로세스 부재 56초인데 시세 구독 공백은 5분 16초였다.
원인 = 15:20 이후 기동 경로에 사전 구독이 없고, 유일한 구독 경로 `_scan_loop` 이
`while` 진입 직후 `await asyncio.sleep(SCAN_INTERVAL)`(300초)을 **먼저** 한다.

이 파일이 봉인하는 행위(§3):

- **B1** `_scan_loop()`(인자 없음) = 첫 구독 전에 `SCAN_INTERVAL` 을 잔다 (현행 보존).
- **B2** `_scan_loop(first_delay=0)` = 첫 sleep 없이 즉시 구독한다.
- **B3** 첫 회차 뒤 주기는 항상 `SCAN_INTERVAL` 로 복귀한다.
- **B4** 음수·비수치 `first_delay` 는 루프를 죽이지 않는다.
- **B5** 기동 시각(창 안·밖 4종)은 첫 회차 지연을 바꾸지 않는다 — 지연은 **인자**가 정한다.
       (어느 호출부가 어떤 인자를 주는지는 `tests/unit/ast/test_cycle298_ast_scan_loop_callsites.py`)
- **B6** `sync_counter % 3` 의 `_sync_positions_from_balance` 는 **회차 기준**이라 주기가 불변이다.
- **§6** 첫 회차 구독 직후 `[scan_loop_first_subscribe]` INFO 1행(never-raise, 첫 회차에만).

테스트 설계 제약(프로젝트 규약):
- `asyncio.sleep` 은 **scheduler 모듈 네임스페이스의 `asyncio` 만** shim 으로 갈아끼운다
  (전역 `asyncio.sleep` 을 건드리면 pytest-asyncio / freezegun 과 얽힌다). 실제 300초 대기 0.
- 루프 탈출은 `self._running = False` 로만 만든다(`sleep` 직후의 `if not self._running: break`).
- 시각 창 게이트는 freezegun 으로 **창 안·밖 두 시각을 모두** 실행한다.
- `[scan_loop_first_subscribe]` 는 INFO 라 `caplog.set_level(logging.INFO, logger="src.engine.scheduler")`
  를 명시한다. 그 밖의 단언은 전부 **행위**(sleep 인자·구독 순서·회차)를 본다.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from freezegun import freeze_time

from src.engine import scheduler as scheduler_mod
from src.engine.scheduler import SCAN_INTERVAL, TradingScheduler
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 하네스
# ---------------------------------------------------------------------------
class _AsyncioShim:
    """`scheduler.asyncio` 자리에 끼우는 프록시 — `sleep` 만 가짜, 나머지는 진짜."""

    def __init__(self, sleep_fn):
        self.sleep = sleep_fn

    def __getattr__(self, name):  # pragma: no cover - 위임
        return getattr(asyncio, name)


class _Harness:
    """`_scan_loop` 1개를 구동하며 sleep/구독/동기화 이벤트를 시간순으로 기록한다."""

    def __init__(self, monkeypatch, *, max_sleeps: int):
        self.events: list[tuple[str, object]] = []
        self.sleeps: list[float] = []
        self.subscribe_calls: int = 0
        self.sync_at_round: list[int] = []
        self._max_sleeps = max_sleeps

        sched = TradingScheduler.__new__(TradingScheduler)
        sched._running = True
        sched.registry = StrategyRegistry()
        sched._auto_funnel_snapshot_done_today = True
        self.sched = sched

        async def fake_sleep(delay, *a, **k):
            self.sleeps.append(delay)
            self.events.append(("sleep", delay))
            if len(self.sleeps) >= self._max_sleeps:
                sched._running = False
            return None

        monkeypatch.setattr(scheduler_mod, "asyncio", _AsyncioShim(fake_sleep))

        async def fake_scan_stocks():
            return []

        async def fake_subscribe(tickers, **kwargs):
            self.subscribe_calls += 1
            self.events.append(("subscribe", self.subscribe_calls))
            return None

        monkeypatch.setattr(scheduler_mod, "scan_stocks", fake_scan_stocks)
        monkeypatch.setattr(scheduler_mod, "subscribe_filtered_stocks", fake_subscribe)

        async def _anoop(*a, **k):
            return None

        sched._collect_breakout_tickers = lambda *a, **k: []
        sched._build_subscription_source_counts = lambda *a, **k: {}
        sched._build_priority_groups = lambda *a, **k: {}
        for name in (
            "_delta_unsubscribe_dropped",
            "_reprepare_breakout_if_empty",
            "_confirm_breakout_open_prices_if_pending",
            "_resubscribe_stale_priority",
            "_evaluate_universe_guard",
            "_subscribe_market_operation_tickers",
            "_refresh_stale_ccnl_cache",
            "_auto_capture_funnel_snapshots",
            "_report_tick_coverage",
        ):
            setattr(sched, name, _anoop)

        async def fake_sync(*a, **k):
            self.sync_at_round.append(self.subscribe_calls)
            self.events.append(("sync", self.subscribe_calls))
            return None

        sched._sync_positions_from_balance = fake_sync

    async def run(self, **kwargs):
        await self.sched._scan_loop(**kwargs)

    @property
    def delay_before_first_subscribe(self) -> float:
        """첫 구독 이전에 잔 시간의 합 — "구독이 얼마나 늦는가" 의 유일한 측정치."""
        total = 0.0
        for kind, value in self.events:
            if kind == "subscribe":
                return total
            if kind == "sleep":
                total += float(value)
        raise AssertionError(f"구독이 한 번도 일어나지 않았다 — events={self.events}")


# ---------------------------------------------------------------------------
# B1 — 인자 없는 호출은 현행 보존 (첫 구독 전 SCAN_INTERVAL)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b1_no_arg_when_loop_started_then_first_subscribe_waits_scan_interval(monkeypatch):
    h = _Harness(monkeypatch, max_sleeps=2)
    await h.run()

    assert h.subscribe_calls >= 1, f"구독이 일어나지 않았다 — events={h.events}"
    assert h.delay_before_first_subscribe == SCAN_INTERVAL, (
        "B1 위반 — `_scan_loop()`(인자 없음)의 첫 구독 전 대기가 SCAN_INTERVAL 이 아니다. "
        f"실측 {h.delay_before_first_subscribe}s / 기대 {SCAN_INTERVAL}s. "
        "기본값이 현행값이어야 09:30 진입 경로(선행 인라인 구독 직후)가 이중 스캔을 하지 않는다."
    )


# ---------------------------------------------------------------------------
# B2 — first_delay=0 은 첫 sleep 없이 즉시 구독
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b2_first_delay_zero_when_loop_started_then_subscribes_immediately(monkeypatch):
    h = _Harness(monkeypatch, max_sleeps=2)
    await h.run(first_delay=0)

    assert h.subscribe_calls >= 1, f"구독이 일어나지 않았다 — events={h.events}"
    assert h.delay_before_first_subscribe == 0, (
        "B2 위반 — `_scan_loop(first_delay=0)` 이 첫 구독 전에 잤다. "
        f"실측 {h.delay_before_first_subscribe}s / 기대 0s. "
        "15:30 POST_NXT 전환 경로에는 선행 구독이 하나도 없어, 이 대기가 곧 손절 사각(5분)이다."
    )


# ---------------------------------------------------------------------------
# B2b — first_delay 는 키워드 전용이다 (위치 인자 오배선 차단)
# ---------------------------------------------------------------------------
def test_b2b_first_delay_when_passed_positionally_then_rejected():
    """`first_delay` 는 **키워드 전용**이다 — 위치 인자 오배선을 호출 시점에 거부한다.

    `_scan_loop(0)` 이 조용히 통과하면 "0 을 줬는데 300 이었다" 류의 무증상 오배선이
    호출부 2곳 중 한쪽에서 살아남는다(= 5분 공백 부활이 테스트를 통과한다).
    """
    sched = TradingScheduler.__new__(TradingScheduler)
    coro = None
    try:
        coro = sched._scan_loop(0)
    except TypeError:
        return
    finally:
        if coro is not None:
            coro.close()
    raise AssertionError(
        "`_scan_loop(0)` 이 TypeError 를 내지 않았다 — `first_delay` 가 키워드 전용이 아니다."
    )


# ---------------------------------------------------------------------------
# B3 — 2회차부터는 언제나 SCAN_INTERVAL
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{}, {"first_delay": 0}], ids=["no_arg", "first_delay_0"])
async def test_b3_second_round_when_loop_continues_then_sleeps_scan_interval(monkeypatch, kwargs):
    h = _Harness(monkeypatch, max_sleeps=3)
    await h.run(**kwargs)

    assert len(h.sleeps) >= 2, f"2회차에 도달하지 못했다 — sleeps={h.sleeps}"
    assert h.sleeps[1] == SCAN_INTERVAL, (
        "B3 위반 — 2회차 sleep 이 SCAN_INTERVAL 이 아니다. "
        f"실측 {h.sleeps[1]}s / 기대 {SCAN_INTERVAL}s (kwargs={kwargs}). "
        "첫 회차 지연은 1회성이고 주기는 불변이어야 한다."
    )
    assert h.sleeps[2:] == [] or all(s == SCAN_INTERVAL for s in h.sleeps[1:]), (
        f"B3 위반 — 2회차 이후 sleep 이 SCAN_INTERVAL 로 고정되지 않았다: {h.sleeps}"
    )


# ---------------------------------------------------------------------------
# B4 — 음수·비수치 first_delay 가 루프를 죽이지 않는다
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b4_negative_first_delay_when_given_then_clamped_to_zero(monkeypatch):
    h = _Harness(monkeypatch, max_sleeps=2)
    await h.run(first_delay=-5)

    assert h.subscribe_calls >= 1, f"음수 first_delay 가 루프를 죽였다 — events={h.events}"
    assert h.delay_before_first_subscribe == 0, (
        "B4 위반 — 음수 `first_delay` 는 0 으로 클램프돼야 한다. "
        f"실측 {h.delay_before_first_subscribe}s."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["abc", object(), [1]], ids=["str", "object", "list"])
async def test_b4_non_numeric_first_delay_when_given_then_loop_survives(monkeypatch, bad):
    """비수치 입력은 **예외로 루프를 죽이지 않는다** — 구독은 계속 일어나야 한다.

    폴백 값이 0 인지 SCAN_INTERVAL 인지는 이 테스트가 정하지 않는다(둘 다 안전 방향).
    금지하는 것은 단 하나 — 예외 전파로 `_scan_task` 가 즉사해 그날 재구독 경로가 사라지는 것.
    """
    h = _Harness(monkeypatch, max_sleeps=2)
    await h.run(first_delay=bad)

    assert h.subscribe_calls >= 1, (
        f"B4 위반 — 비수치 first_delay={bad!r} 가 루프를 죽였다. events={h.events}"
    )
    assert 0 <= h.delay_before_first_subscribe <= SCAN_INTERVAL, (
        f"B4 위반 — 폴백 지연이 [0, {SCAN_INTERVAL}] 밖이다: {h.delay_before_first_subscribe}"
    )


# ---------------------------------------------------------------------------
# B4b — 거대값 first_delay 는 상한에 걸린다 (무음 영구 blind 차단)
#
#   `_scan_loop` 은 이 시스템의 **유일한 WS 재구독 경로**다. `asyncio.sleep(inf)` 은
#   예외도 로그도 남기지 않으므로, 상한이 없으면 그 루프가 조용히 영원히 자고
#   손절·트레일링이 전면 정지한다. 지금 호출부 2곳은 안전하지만(AST 가 인자를 핀한다)
#   docstring 이 주장하는 계약 "[0, SCAN_INTERVAL] 안의 안전값" 은 구현되어 있지 않다.
#
#   ⚠️ 단언 대상은 "테스트가 멈추지 않았다" 가 **아니다** — 하네스의 `fake_sleep` 은
#   실제로 자지 않아 `inf` 를 넘겨도 테스트는 끝난다. 봉인하는 것은 **sleep 에 넘어간 값**,
#   즉 첫 구독 전 누적 지연이 `SCAN_INTERVAL` 이하라는 사실 하나뿐이다.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "huge",
    [float("inf"), 1e9],
    ids=["inf", "1e9"],
)
async def test_b4b_huge_first_delay_when_given_then_capped_at_scan_interval(monkeypatch, huge):
    h = _Harness(monkeypatch, max_sleeps=2)
    await h.run(first_delay=huge)

    assert h.subscribe_calls >= 1, (
        f"B4b 위반 — 거대 first_delay={huge!r} 로 구독이 한 번도 일어나지 않았다. events={h.events}"
    )
    assert h.delay_before_first_subscribe <= SCAN_INTERVAL, (
        f"B4b 위반 — `first_delay={huge!r}` 가 상한에 걸리지 않았다. "
        f"첫 구독 전 누적 지연 {h.delay_before_first_subscribe}s / 상한 {SCAN_INTERVAL}s. "
        "상한이 없으면 `asyncio.sleep(inf)` 이 예외도 로그도 없이 `_scan_loop` 을 영구 blind 로 "
        "만든다 — 유일한 WS 재구독 경로가 죽으면 그대로 손절·트레일링 전면 정지다. "
        "계약 = delay = min(float(SCAN_INTERVAL), max(0.0, float(first_delay)))."
    )


@pytest.mark.asyncio
async def test_b4b_first_delay_equal_scan_interval_when_given_then_not_reduced(monkeypatch):
    """(경계) 정상값 `SCAN_INTERVAL` 은 상한이 **깎지 않는다**.

    상한을 `min(SCAN_INTERVAL, ...)` 이 아니라 더 조인 값으로 넣는 과잉 시정을 차단한다 —
    이 값은 09:30 진입 경로의 기본값(=300초)과 같은 수라, 여기가 줄면 그 경로의 첫 회차가
    앞당겨져 선행 인라인 구독과 이중 스캔이 된다.
    """
    h = _Harness(monkeypatch, max_sleeps=2)
    await h.run(first_delay=SCAN_INTERVAL)

    assert h.subscribe_calls >= 1, f"구독이 일어나지 않았다 — events={h.events}"
    assert h.delay_before_first_subscribe == SCAN_INTERVAL, (
        f"B4b 위반 — 경계값 `first_delay={SCAN_INTERVAL}` 이 그대로 유지되지 않았다. "
        f"실측 {h.delay_before_first_subscribe}s / 기대 {SCAN_INTERVAL}s. "
        "상한은 `min()` 이라 정상값을 깎지 않아야 한다."
    )


# ---------------------------------------------------------------------------
# B5 — 첫 회차 지연은 벽시계가 아니라 인자가 정한다
#
#   명세 §3 B5 의 시각대별 첫 구독 시점은 (a) 호출부가 주는 인자 + (b) 그 호출부에
#   도달하는 시각의 곱이다. (b)는 AST 가드가 `_wait_until(TIME_KRX_MAIN_CLOSE)` 순서로
#   봉인하고, 여기서는 (a)가 **벽시계와 무관하다**는 사실을 창 안·밖 4시각으로 못박는다.
#   로컬 23:5x 초록 / CI 00:04 실패 유형을 구조적으로 배제한다.
# ---------------------------------------------------------------------------
_BOOT_CLOCKS = [
    ("2026-09-17 15:25:00", "15:20<=T<15:30"),
    ("2026-09-17 15:35:00", "15:30<=T<19:50"),
    ("2026-09-17 16:11:00", "15:30<=T<19:50 (실측 사고 시각)"),
    ("2026-09-17 10:00:00", "09:30<T<15:20"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("clock,label", _BOOT_CLOCKS, ids=[c[0][-8:] for c in _BOOT_CLOCKS])
async def test_b5_first_delay_zero_when_any_boot_clock_then_immediate(monkeypatch, clock, label):
    with freeze_time(clock):
        h = _Harness(monkeypatch, max_sleeps=2)
        await h.run(first_delay=0)

    assert h.delay_before_first_subscribe == 0, (
        f"B5 위반 — 기동 시각 {clock}({label}) 에서 `first_delay=0` 이 즉시 구독하지 않았다. "
        f"실측 {h.delay_before_first_subscribe}s. 첫 회차 지연은 벽시계가 아니라 인자가 정한다."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("clock,label", _BOOT_CLOCKS, ids=[c[0][-8:] for c in _BOOT_CLOCKS])
async def test_b5_no_arg_when_any_boot_clock_then_scan_interval(monkeypatch, clock, label):
    with freeze_time(clock):
        h = _Harness(monkeypatch, max_sleeps=2)
        await h.run()

    assert h.delay_before_first_subscribe == SCAN_INTERVAL, (
        f"B5 위반 — 기동 시각 {clock}({label}) 에서 인자 없는 호출이 현행(300초)을 벗어났다. "
        f"실측 {h.delay_before_first_subscribe}s."
    )


# ---------------------------------------------------------------------------
# B6 — sync_counter % 3 은 회차 기준 (위상만 당겨지고 주기는 불변)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{}, {"first_delay": 0}], ids=["no_arg", "first_delay_0"])
async def test_b6_position_sync_when_six_rounds_then_fires_on_round_3_and_6(monkeypatch, kwargs):
    h = _Harness(monkeypatch, max_sleeps=7)
    await h.run(**kwargs)

    assert h.subscribe_calls >= 6, f"6회차에 도달하지 못했다 — subscribe={h.subscribe_calls}"
    assert h.sync_at_round[:2] == [3, 6], (
        "B6 위반 — `_sync_positions_from_balance` 발화 회차가 3·6 이 아니다. "
        f"실측 {h.sync_at_round} (kwargs={kwargs}). "
        "첫 회차를 당겨도 주기(3회차)는 불변이어야 한다 — 위상만 5분 당겨진다."
    )


# ---------------------------------------------------------------------------
# §6 — 첫 회차 구독 직후 관측 1행 (INFO, 첫 회차에만)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_s6_observation_when_first_round_then_emits_marker_once(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    h = _Harness(monkeypatch, max_sleeps=4)
    await h.run(first_delay=0)

    rows = [
        r for r in caplog.records
        if r.levelno >= logging.INFO and r.getMessage().startswith("[scan_loop_first_subscribe]")
    ]
    assert len(rows) == 1, (
        "§6 위반 — `[scan_loop_first_subscribe]` INFO 가 첫 회차에 정확히 1행이어야 한다. "
        f"실측 {len(rows)}행 (구독 {h.subscribe_calls}회). "
        f"관측된 마커: {[r.getMessage() for r in rows]}"
    )
    msg = rows[0].getMessage()
    for field in ("first_delay=", "elapsed_s=", "n="):
        assert field in msg, f"§6 위반 — 마커에 `{field}` 필드 누락: {msg}"
