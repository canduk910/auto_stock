"""cycle252 Red — K stale watcher 의 무송출(no_feed) 종목 churn 중단.

> 정본 명세: `spec_cycle252_no_feed_churn.md` §2(stale_watcher_core) / §3 W1~W9
> 포렌식 근거: `_workspace/forensics/stale_candidates_0904.md` ① · ②-5 · ③ · ⑤A

## 사실

`nxt_tradable=False` 종목은 `H0UNCNT0` 로 ACK 까지 정상이지만 체결 프레임이 하루 0건이다
(나흘 × ~200종목, 예외 0). K stale watcher 는 그 종목들을 r=1..5 즉시 unsub/sub +
r>5 600s cooldown force_retry 로 **종목당 하루 ~134회** 재등록해 SEND ≈14,600 ·
`[ws_ack_orphan]` 7,120 을 만든다. 나흘간 회복 사례 0.

## 이 사이클이 바꾸는 것 / 바꾸지 않는 것

바꾸는 것은 **LOW no_feed 종목의 SEND(unsubscribe/subscribe) · `_stale_last_resubscribe_at`
스탬프 · force_retry history 등록** 셋뿐이다.

바꾸지 않는 것(=회귀 표적):
- **HIGH(보유·익일청산)는 byte 동일**(§1 D1). 가설이 어떤 보유 종목에 틀렸을 때 잃는 것이
  손절 커버리지다. HIGH no_feed 는 하루 2종목 × 134 SEND = 무시 가능.
- **`_stale_retry_count` 는 계속 증가**(§1 D2, r>5 는 `MAX+1` 홀드). `stale_universe_guard`
  가 `retries > MAX_STALE_RETRIES ∧ 거래량<1만` 으로 저유동 종목을 축출하는 경로를 보존한다.
- **registry 가 비면 현행 byte 동일**(§1 D3 fail-open) — W5 차분 테스트가 봉인.
  W5 의 기준은 `HEAD` 가 아니라 **cycle252 직전 sha 핀**(`_BASELINE_SHA`)이다 —
  HEAD 기준이면 cycle252 를 커밋하는 순간 자기 대조(공허 PASS)가 된다(tester F-4).
  기준 sha 객체가 없는 환경(CI shallow clone)에서는 SKIP 이고, fail-open 자체는
  git 무관 테스트(W1b·W4·W6·W8c + registry R4/R5b/R7)가 별도로 봉인한다.
- 동시호가/grace/market_op skip 은 no_feed 판정보다 **앞**(W9).

| ID | 검사 |
|----|------|
| W1 | LOW no_feed stale → SEND 0 · 스탬프 0 · sleep 0 · retry 는 +1 |
| W2 | 같은 종목 r>5 → `MAX+1` 홀드 · SEND 0 · force_retry history 미등록 |
| W3 | HIGH(positions/익일청산) no_feed → 현행 동일(HIGH·bypass=True·스탬프) |
| W4 | no_feed 아닌 LOW stale → 현행 동일(LOW·bypass=False·스탬프) |
| W5 | registry 공집합 = 기준 sha(`_BASELINE_SHA`, cycle252 직전) 구현과 **차분 0** (fail-open 봉인, ≥200 조합) |
| W6 | `ensure_fresh` 예외 → 사이클 완주(전파 0) |
| W7 | `[no_feed_held]` WARNING 1회/일 · 날짜 키 리셋 · HIGH∩no_feed 공집합이면 0 |
| W8 | `[stale_watcher_summary]` 끝에 ` no_feed_skipped=%d` (기존 prefix byte 보존) |
| W9 | 동시호가 skip 이 no_feed 판정보다 앞 (`is_no_feed` 호출 0) |
"""
from __future__ import annotations

import importlib.util
import logging
import random
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
_REPO_ROOT = Path(__file__).resolve().parents[3]

_HELD_MARKER = "[no_feed_held]"
_SUMMARY_PREFIX = (
    "[stale_watcher_summary] checks=%d stale_total=%d retried=%d "
    "cap_blocked=%d force_retried=%d"
)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _core():
    from src.engine import stale_watcher_core as core

    return core


def _registry():
    """모듈 부재는 SKIP 이 아니라 FAIL (Red 는 붉어야 한다)."""
    try:
        from src.engine import no_feed_registry  # type: ignore[attr-defined]
    except ImportError as exc:  # pragma: no cover - Red 단계 경로
        pytest.fail(
            "cycle252 §2 — 신규 leaf `src/engine/no_feed_registry.py` 미존재. "
            f"import 실패: {exc}"
        )
    return no_feed_registry


class _SleepSpy:
    """`stale_watcher_core.asyncio` 대역 — sleep 호출 계측 + 즉시 반환."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []

    async def sleep(self, secs: float) -> None:
        self.sleeps.append(secs)


def _patch_no_sleep(monkeypatch, mod) -> _SleepSpy:
    spy = _SleepSpy()
    monkeypatch.setattr(mod, "asyncio", spy)
    return spy


def _make_pool(monkeypatch, subscribed) -> MagicMock:
    import src.realtime.websocket_pool as wp_mod

    pool = MagicMock()
    pool.get_subscribed_tickers = lambda: set(subscribed)
    pool.unsubscribe_in_pool = AsyncMock()
    pool.subscribe = AsyncMock()
    # `emit_stale_session_detail` 조기 return (세션 뷰는 이 사이클의 검증 대상 아님)
    pool.get_subscriptions_by_session = MagicMock(return_value={})
    pool._subscribed_at = {}
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool)
    return pool


def _setup_ticks(monkeypatch, *, stale=(), fresh=(), now=None):
    """`scanner.ticker_last_tick` 주입. stale=120s 전 / fresh=5s 전."""
    import src.engine.scanner as scanner_mod

    base = now or datetime.now(KST)
    last_tick = {}
    for t in stale:
        last_tick[t] = base - timedelta(seconds=120)
    for t in fresh:
        last_tick[t] = base - timedelta(seconds=5)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", last_tick)
    return last_tick


def _make_sched(*, positions=(), next_day_clear=(), retry=None, last_at=None,
                history=None):
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = dict(retry or {})
    sched._stale_last_resubscribe_at = dict(last_at or {})
    sched._stale_force_retry_history = {k: list(v) for k, v in (history or {}).items()}
    sched._pending_next_day_clear = set(next_day_clear)
    sched._running = True
    sched._STALE_DETAIL_TICKER_CAP = 20

    fake_state = MagicMock()
    fake_state.positions = {t: MagicMock() for t in positions}
    fake_strategy = MagicMock()
    fake_strategy.state = fake_state
    fake_registry = MagicMock()
    fake_registry.all = MagicMock(return_value=[fake_strategy])
    sched.registry = fake_registry
    return sched


class _RegistrySpy:
    def __init__(self, no_feed, *, ensure_raises=None):
        self.no_feed = set(no_feed)
        self.ensure_raises = ensure_raises
        self.ensure_calls: list[list[str]] = []
        self.is_no_feed_calls: list[str] = []

    async def ensure_fresh(self, tickers, **kwargs):
        self.ensure_calls.append(sorted(tickers))
        if self.ensure_raises is not None:
            raise self.ensure_raises

    def is_no_feed(self, ticker: str) -> bool:
        self.is_no_feed_calls.append(ticker)
        return ticker in self.no_feed


def _patch_registry(monkeypatch, no_feed=(), *, ensure_raises=None) -> _RegistrySpy:
    reg = _registry()
    reset = getattr(reg, "reset_state_for_test", None)
    if callable(reset):
        reset()
    spy = _RegistrySpy(no_feed, ensure_raises=ensure_raises)
    monkeypatch.setattr(reg, "ensure_fresh", spy.ensure_fresh)
    monkeypatch.setattr(reg, "is_no_feed", spy.is_no_feed)
    return spy


# ===========================================================================
# W1 — LOW no_feed stale: SEND 0 · 스탬프 0 · sleep 0 · retry +1
# ===========================================================================
async def test_w1_low_no_feed_ticker_is_not_resubscribed(monkeypatch, caplog):
    """무송출 종목 재등록은 나흘간 회복 0 — SEND 를 아예 내지 않는다.

    단 `_stale_retry_count` 는 정직하게 +1 한다(§1 D2) — `stale_universe_guard` 의
    저유동 축출 경로(`retries > MAX_STALE_RETRIES`)를 보존해야 하기 때문이다.
    """
    core = _core()
    pool = _make_pool(monkeypatch, ["005935"])
    _setup_ticks(monkeypatch, stale=["005935"])
    sleeps = _patch_no_sleep(monkeypatch, core)
    _patch_registry(monkeypatch, no_feed={"005935"})
    sched = _make_sched()
    caplog.set_level(logging.DEBUG)

    await core.check_and_resubscribe_stale(sched)

    pool.unsubscribe_in_pool.assert_not_awaited()
    pool.subscribe.assert_not_awaited()
    assert "005935" not in sched._stale_last_resubscribe_at, (
        "no_feed skip 은 `_stale_last_resubscribe_at` 를 스탬프하지 않는다 — "
        "스탬프하면 5분 우선 재구독 throttle/force_retry cooldown 게이트가 "
        "실제로 일어나지 않은 SEND 를 기준으로 움직인다"
    )
    assert sched._stale_retry_count.get("005935") == 1, (
        "retry 카운터는 계속 증가(§1 D2) — universe guard 축출 경로 보존. "
        f"actual={sched._stale_retry_count!r}"
    )
    assert sleeps.sleeps == [], (
        f"skip 경로에 Rate Limit sleep 불필요 — actual={sleeps.sleeps!r}"
    )


async def test_w1b_mixed_cycle_only_no_feed_is_skipped(monkeypatch):
    """같은 사이클에 no_feed 와 정상 종목이 섞이면 정상 종목만 재등록된다."""
    core = _core()
    pool = _make_pool(monkeypatch, ["005935", "006340"])
    _setup_ticks(monkeypatch, stale=["005935", "006340"])
    _patch_no_sleep(monkeypatch, core)
    _patch_registry(monkeypatch, no_feed={"005935"})
    sched = _make_sched()

    await core.check_and_resubscribe_stale(sched)

    subscribed_args = [c.args for c in pool.subscribe.await_args_list]
    assert len(subscribed_args) == 1, (
        f"정상 종목 1개만 재등록 — actual={subscribed_args!r}"
    )
    assert subscribed_args[0][1] == "006340"
    assert sched._stale_retry_count == {"005935": 1, "006340": 1}


# ===========================================================================
# W2 — r>5 홀드: MAX+1 · SEND 0 · force_retry history 미등록
# ===========================================================================
async def test_w2_no_feed_retry_holds_at_max_plus_one(monkeypatch):
    """r 이 6 이상이면 `MAX_STALE_RETRIES+1` 로 홀드 (7 로 오르지 않는다).

    기존 cooldown skip 분기(cycle218)와 **같은 정직화**다 — r>5 는 모두 동일 경로라
    무한 climb 숫자가 실제 부하와 무관한 오해를 만든다. 홀드 값이 `MAX+1`(=6)이어야
    `stale_universe_guard` 의 `retries > MAX_STALE_RETRIES` 축출이 계속 성립한다.
    """
    from src.engine.stale_diagnostics import MAX_STALE_RETRIES

    core = _core()
    pool = _make_pool(monkeypatch, ["005935"])
    _setup_ticks(monkeypatch, stale=["005935"])
    _patch_no_sleep(monkeypatch, core)
    _patch_registry(monkeypatch, no_feed={"005935"})
    # r=6 진입 (직전 6 → +1 = 7 → 홀드 6)
    sched = _make_sched(retry={"005935": MAX_STALE_RETRIES + 1})

    await core.check_and_resubscribe_stale(sched)

    assert sched._stale_retry_count["005935"] == MAX_STALE_RETRIES + 1, (
        f"MAX+1(={MAX_STALE_RETRIES + 1}) 홀드 — actual="
        f"{sched._stale_retry_count['005935']}"
    )
    assert sched._stale_retry_count["005935"] > MAX_STALE_RETRIES, (
        "홀드 값은 universe guard 축출 임계(`> MAX_STALE_RETRIES`)를 계속 넘겨야 한다"
    )
    pool.unsubscribe_in_pool.assert_not_awaited()
    pool.subscribe.assert_not_awaited()
    assert sched._stale_force_retry_history.get("005935", []) == [], (
        "SEND 가 없었으므로 force_retry history 등록도 없어야 한다 — "
        f"actual={sched._stale_force_retry_history!r}"
    )
    assert "005935" not in sched._stale_last_resubscribe_at


async def test_w2b_no_feed_hold_is_idempotent_across_cycles(monkeypatch):
    """여러 사이클 반복해도 6 에서 고정 — 로그·진단의 r 값이 정직해진다."""
    from src.engine.stale_diagnostics import MAX_STALE_RETRIES

    core = _core()
    pool = _make_pool(monkeypatch, ["005935"])
    _setup_ticks(monkeypatch, stale=["005935"])
    _patch_no_sleep(monkeypatch, core)
    _patch_registry(monkeypatch, no_feed={"005935"})
    sched = _make_sched(retry={"005935": MAX_STALE_RETRIES + 1})

    for _ in range(5):
        await core.check_and_resubscribe_stale(sched)

    assert sched._stale_retry_count["005935"] == MAX_STALE_RETRIES + 1
    assert pool.subscribe.await_count == 0


# ===========================================================================
# W3 — HIGH(보유/익일청산) no_feed = 현행 byte 동일
# ===========================================================================
@pytest.mark.parametrize("kind", ["positions", "next_day_clear"])
async def test_w3_high_no_feed_still_resubscribed(monkeypatch, kind):
    """§1 D1 — HIGH 는 제외하지 않는다.

    "무송출" 은 확신도 ≈90% 의 가설이다. 그 가설이 어떤 보유 종목에 대해 틀렸을 때
    잃는 것이 손절 커버리지이므로, 비용(하루 2종목 × 134 SEND)을 지불하고 재등록을
    유지한다.
    """
    core = _core()
    pool = _make_pool(monkeypatch, ["003490"])
    _setup_ticks(monkeypatch, stale=["003490"])
    _patch_no_sleep(monkeypatch, core)
    _patch_registry(monkeypatch, no_feed={"003490"})
    if kind == "positions":
        sched = _make_sched(positions=["003490"])
    else:
        sched = _make_sched(next_day_clear={("003490", "kojiro")})

    await core.check_and_resubscribe_stale(sched)

    pool.unsubscribe_in_pool.assert_awaited_once()
    pool.subscribe.assert_awaited_once()
    kwargs = pool.subscribe.await_args.kwargs
    assert kwargs.get("priority") == "HIGH", (
        f"보유/익일청산은 HIGH 유지 — actual={kwargs!r}"
    )
    assert kwargs.get("bypass_limit") is True
    assert "003490" in sched._stale_last_resubscribe_at, (
        "HIGH 경로는 스탬프까지 현행 동일"
    )
    assert sched._stale_retry_count["003490"] == 1


async def test_w3b_high_no_feed_force_retry_branch_unchanged(monkeypatch):
    """r>5 force_retry 분기도 HIGH 는 그대로 발화 + 카운터 0 리셋."""
    from src.engine.stale_diagnostics import (
        MAX_STALE_RETRIES,
        STALE_FORCE_RETRY_AFTER_SECS,
    )

    core = _core()
    pool = _make_pool(monkeypatch, ["003490"])
    _setup_ticks(monkeypatch, stale=["003490"])
    _patch_no_sleep(monkeypatch, core)
    _patch_registry(monkeypatch, no_feed={"003490"})
    sched = _make_sched(
        positions=["003490"],
        retry={"003490": MAX_STALE_RETRIES + 2},
        last_at={
            "003490": datetime.now(KST)
            - timedelta(seconds=STALE_FORCE_RETRY_AFTER_SECS + 60)
        },
    )

    await core.check_and_resubscribe_stale(sched)

    pool.subscribe.assert_awaited_once()
    assert pool.subscribe.await_args.kwargs.get("priority") == "HIGH"
    assert sched._stale_retry_count["003490"] == 0, (
        "force_retry 발화 시 카운터 0 리셋 = 현행 계약 (HIGH 는 무접촉)"
    )
    assert len(sched._stale_force_retry_history.get("003490", [])) == 1


# ===========================================================================
# W4 — no_feed 아닌 LOW stale = 현행 동일
# ===========================================================================
async def test_w4_low_normal_ticker_unchanged(monkeypatch):
    core = _core()
    pool = _make_pool(monkeypatch, ["006340"])
    _setup_ticks(monkeypatch, stale=["006340"])
    _patch_no_sleep(monkeypatch, core)
    _patch_registry(monkeypatch, no_feed=set())
    sched = _make_sched()

    await core.check_and_resubscribe_stale(sched)

    pool.unsubscribe_in_pool.assert_awaited_once()
    pool.subscribe.assert_awaited_once()
    kwargs = pool.subscribe.await_args.kwargs
    assert kwargs.get("priority") == "LOW"
    assert kwargs.get("bypass_limit") is False
    assert "006340" in sched._stale_last_resubscribe_at
    assert sched._stale_retry_count["006340"] == 1


async def test_w4b_ensure_fresh_receives_subscribed_set(monkeypatch):
    """`ensure_fresh` 는 `if not subscribed: return` **뒤**에 구독 전체로 1회 호출."""
    core = _core()
    _make_pool(monkeypatch, ["006340", "005935"])
    _setup_ticks(monkeypatch, stale=["006340", "005935"])
    _patch_no_sleep(monkeypatch, core)
    spy = _patch_registry(monkeypatch, no_feed=set())
    sched = _make_sched()

    await core.check_and_resubscribe_stale(sched)

    assert spy.ensure_calls == [["005935", "006340"]], (
        f"ensure_fresh 는 구독 전체로 사이클당 1회 — actual={spy.ensure_calls!r}"
    )


async def test_w4c_empty_subscription_does_not_touch_registry(monkeypatch):
    """구독 0 = 조기 return — DB 조회 트리거조차 하지 않는다."""
    core = _core()
    _make_pool(monkeypatch, [])
    _setup_ticks(monkeypatch)
    _patch_no_sleep(monkeypatch, core)
    spy = _patch_registry(monkeypatch, no_feed=set())
    sched = _make_sched()

    await core.check_and_resubscribe_stale(sched)

    assert spy.ensure_calls == [], (
        f"구독 0 이면 ensure_fresh 호출 0 — actual={spy.ensure_calls!r}"
    )


# ===========================================================================
# W5 — fail-open 차분 봉인: registry 공집합 = 기준 sha 구현과 완전 동일
# ===========================================================================
_HEAD_MOD_NAME = "_cycle252_head_stale_watcher_core"

# cycle252 직전 커밋(8b146ff — "docs: KRX 단독 채널(H0STCNT0) 프로브·채널 리졸버 설계
# 메모"). `HEAD:` 를 기준으로 삼으면 cycle252 커밋 직후 HEAD == 워킹트리가 되어 이
# 테스트가 자기 대조(공허 PASS)로 전락한다(tester F-4). cycle235/238 "sha 핀 가드
# 재핀" 관례 — 후속 사이클이 K watcher 의 공유 경로 행위를 **의도적으로** 바꿀 때만
# 그 승인 sha 로 재핀한다. 핀을 먼저 재산출하지 마라 — FAIL 이 나면 그 diff 가 실제
# 행위 변경인지 먼저 확인한다.
_BASELINE_SHA = "8b146ffb9ab9a1104e9054bca31cf18835fe8743"


def _load_head_module(tmp_path: Path):
    """`git show {_BASELINE_SHA}:src/engine/stale_watcher_core.py` 를 임시 모듈로 로드.

    기준 객체가 없는 환경(CI `actions/checkout` 기본 depth=1 shallow clone 등)은
    SKIP — 이 차분은 전체 이력이 있는 로컬/`test-impact`(fetch-depth 0) 에서 돈다.
    git 자체 부재·기타 오류도 SKIP 사유에 포함하되 stderr 를 그대로 남긴다.
    """
    res = subprocess.run(
        ["git", "show", f"{_BASELINE_SHA}:src/engine/stale_watcher_core.py"],
        cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    if res.returncode != 0:
        pytest.skip(
            f"기준 sha {_BASELINE_SHA[:7]} 소스 조회 불가 (rc={res.returncode}, "
            f"shallow clone 등) — W5 차분 생략. stderr={(res.stderr or '').strip()!r}"
        )
    path = tmp_path / "head_stale_watcher_core.py"
    path.write_text(res.stdout, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(_HEAD_MOD_NAME, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_HEAD_MOD_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


def _record_pool_calls(pool: MagicMock) -> list[tuple]:
    seq: list[tuple] = []
    for call in pool.unsubscribe_in_pool.await_args_list:
        seq.append(("unsub", tuple(call.args), dict(call.kwargs)))
    for call in pool.subscribe.await_args_list:
        seq.append(("sub", tuple(call.args), dict(call.kwargs)))
    return seq


def _sched_snapshot(sched) -> dict:
    return {
        "retry": dict(sched._stale_retry_count),
        "last_at": dict(sched._stale_last_resubscribe_at),
        "history": {k: len(v) for k, v in sched._stale_force_retry_history.items()},
    }


@pytest.mark.slow
async def test_w5_fail_open_matches_head_implementation(monkeypatch, tmp_path):
    """no_feed 집합이 비면 **모든** 종목이 기준 sha(cycle252 직전) 구현과 byte 동일하게
    처리된다.

    §1 D3 fail-open 의 차분 실증. 부팅 직후 마스터 미적재·DB 실패 시 이 성질이
    무너지면 "잘못 분류돼도 무해" 라는 설계 근거가 통째로 사라진다.

    ≥200 무작위 조합에서 (a) pool 호출 시퀀스 (b) `_stale_retry_count`
    (c) `_stale_last_resubscribe_at` (d) force_retry history 길이 (e) collector 통계
    5축을 `_BASELINE_SHA` 구현과 대조한다. 기준 객체가 없는 환경은 SKIP(로더 참조).
    """
    from src.engine.stale_diagnostics import STALE_FORCE_RETRY_HOURLY_CAP

    core = _core()
    head = _load_head_module(tmp_path)
    _patch_registry(monkeypatch, no_feed=set())  # 공집합 = fail-open

    frozen = "2026-09-07 11:00:00+09:00"
    now = datetime(2026, 9, 7, 11, 0, 0, tzinfo=KST)
    pool_universe = ["000815", "003490", "005935", "006340",
                     "035720", "047040", "079650", "403870"]
    rnd = random.Random(20260907)
    combos = 220
    mismatches: list[str] = []

    with freeze_time(frozen):
        for i in range(combos):
            n = rnd.randint(2, 6)
            tickers = rnd.sample(pool_universe, n)
            stale = [t for t in tickers if rnd.random() < 0.75]
            fresh = [t for t in tickers if t not in stale]
            positions = [t for t in tickers if rnd.random() < 0.2]
            ndc = {(t, "kojiro") for t in tickers if rnd.random() < 0.1}
            retry = {t: rnd.choice([0, 1, 4, 5, 6, 8]) for t in tickers}
            last_at = {}
            for t in tickers:
                age = rnd.choice([None, 10, 300, 700, 4000])
                if age is not None:
                    last_at[t] = now - timedelta(seconds=age)
            history = {
                t: [now - timedelta(seconds=60 * k + 5)
                    for k in range(rnd.choice([0, 0, 1, STALE_FORCE_RETRY_HOURLY_CAP]))]
                for t in tickers
            }

            results = []
            for mod in (head, core):
                pool = _make_pool(monkeypatch, tickers)
                _setup_ticks(monkeypatch, stale=stale, fresh=fresh, now=now)
                _patch_no_sleep(monkeypatch, mod)
                mod._stale_watcher_collector.clear()
                sched = _make_sched(
                    positions=positions, next_day_clear=ndc,
                    retry=retry, last_at=last_at, history=history,
                )
                await mod.check_and_resubscribe_stale(sched)
                stats = [
                    {k: s.get(k) for k in (
                        "subscribed", "stale", "force_reregistered",
                        "skipped_giveup", "force_retried", "cap_blocked")}
                    for s in mod._stale_watcher_collector
                ]
                mod._stale_watcher_collector.clear()
                results.append((_record_pool_calls(pool), _sched_snapshot(sched), stats))

            if results[0] != results[1]:
                mismatches.append(
                    f"combo#{i} tickers={sorted(tickers)} stale={sorted(stale)} "
                    f"positions={sorted(positions)} retry={retry}\n"
                    f"  HEAD={results[0]}\n  CURR={results[1]}"
                )
                if len(mismatches) >= 3:
                    break

    assert mismatches == [], (
        f"fail-open 위반 — no_feed 공집합인데 기준 sha {_BASELINE_SHA[:7]} 와 행위가 다르다 "
        f"({len(mismatches)} 건):\n" + "\n".join(mismatches)
    )


# ===========================================================================
# W6 — ensure_fresh 예외는 사이클을 죽이지 않는다
# ===========================================================================
async def test_w6_ensure_fresh_exception_does_not_break_cycle(monkeypatch, caplog):
    """DB 가 죽어도 K watcher 는 계속 돌아야 한다(4중 안전망의 한 축).

    예외가 전파되면 `_stale_watcher_loop` 이 그 사이클을 통째로 잃고 stale 감지가
    멈춘다 — 관측 개선이 손절 사각을 만드는 최악의 교환.
    """
    core = _core()
    pool = _make_pool(monkeypatch, ["006340"])
    _setup_ticks(monkeypatch, stale=["006340"])
    _patch_no_sleep(monkeypatch, core)
    _patch_registry(monkeypatch, no_feed=set(), ensure_raises=RuntimeError("pg down"))
    sched = _make_sched()
    caplog.set_level(logging.DEBUG)

    await core.check_and_resubscribe_stale(sched)  # raise 하면 즉시 FAIL

    pool.subscribe.assert_awaited_once(), "예외 흡수 후에도 정상 종목 재등록 계속"
    assert sched._stale_retry_count["006340"] == 1


# ===========================================================================
# W7 — [no_feed_held] WARNING 1회/일
# ===========================================================================
async def test_w7_no_feed_held_warns_once_per_day(monkeypatch, caplog):
    """보유 종목이 WS blind 라는 사실을 **매일 1행** 남긴다.

    - HIGH∩no_feed 판정은 stale 여부와 무관(포렌식 ①: 보유 003490·000815 는 종일
      프레임 0 이고, 그 사실 자체가 기록 대상이다).
    - 120s 주기 × 종일 = 360행이 되지 않도록 cap 1회/일.
    - 날짜 키 자기 리셋 — 다음 영업일에 다시 1행.
    """
    core = _core()
    caplog.set_level(logging.DEBUG)

    def _run_cycle(day_iso: str):
        return day_iso

    # --- day 1, cycle 1 ---
    with freeze_time("2026-09-07 10:00:00+09:00"):
        now = datetime(2026, 9, 7, 10, 0, tzinfo=KST)
        _make_pool(monkeypatch, ["003490", "000815", "006340"])
        _setup_ticks(monkeypatch, stale=["006340"],
                     fresh=["003490", "000815"], now=now)
        _patch_no_sleep(monkeypatch, core)
        _patch_registry(monkeypatch, no_feed={"003490", "000815"})
        sched = _make_sched(positions=["003490"],
                            next_day_clear={("000815", "kojiro")})
        await core.check_and_resubscribe_stale(sched)

        held = [r for r in caplog.records if _HELD_MARKER in r.getMessage()]
        assert len(held) == 1, (
            f"{_HELD_MARKER} 1행 — actual={[r.getMessage() for r in held]}"
        )
        assert held[0].levelno >= logging.WARNING, (
            f"{_HELD_MARKER} 는 WARNING (INFO 는 2일 retention 이라 사후 추적 불가). "
            f"actual level={held[0].levelname}"
        )
        msg = held[0].getMessage()
        assert "tickers=" in msg, f"tickers= 필드 부재 — {msg!r}"
        assert "003490" in msg and "000815" in msg, (
            f"보유·익일청산 both 가 나열돼야 한다 — {msg!r}"
        )

        # --- day 1, cycle 2 → 무로그 ---
        caplog.clear()
        await core.check_and_resubscribe_stale(sched)
        assert [r for r in caplog.records if _HELD_MARKER in r.getMessage()] == [], (
            "같은 날 두 번째 사이클은 무로그 (cap 1회/일)"
        )

    # --- day 2 → 다시 1행 ---
    caplog.clear()
    with freeze_time("2026-09-08 09:30:00+09:00"):
        now2 = datetime(2026, 9, 8, 9, 30, tzinfo=KST)
        _make_pool(monkeypatch, ["003490", "000815", "006340"])
        _setup_ticks(monkeypatch, stale=["006340"],
                     fresh=["003490", "000815"], now=now2)
        _patch_no_sleep(monkeypatch, core)
        _patch_registry(monkeypatch, no_feed={"003490", "000815"})
        sched2 = _make_sched(positions=["003490"],
                             next_day_clear={("000815", "kojiro")})
        await core.check_and_resubscribe_stale(sched2)

        held2 = [r for r in caplog.records if _HELD_MARKER in r.getMessage()]
        assert len(held2) == 1, (
            f"날짜 키 자기 리셋 후 다시 1행 — actual={len(held2)}"
        )


async def test_w7b_no_feed_held_silent_when_no_high_overlap(monkeypatch, caplog):
    """보유·익일청산에 no_feed 가 없으면 0행 — 잡음 금지."""
    core = _core()
    _make_pool(monkeypatch, ["005935", "003490"])
    _setup_ticks(monkeypatch, stale=["005935", "003490"])
    _patch_no_sleep(monkeypatch, core)
    _patch_registry(monkeypatch, no_feed={"005935"})  # 보유 아님
    sched = _make_sched(positions=["003490"])  # 보유는 no_feed 아님
    caplog.set_level(logging.DEBUG)

    await core.check_and_resubscribe_stale(sched)

    assert [r for r in caplog.records if _HELD_MARKER in r.getMessage()] == [], (
        "HIGH ∩ no_feed = ∅ 이면 로그 0행"
    )


# ===========================================================================
# W8 — [stale_watcher_summary] 에 no_feed_skipped 합계
# ===========================================================================
def test_w8_summary_appends_no_feed_skipped_preserving_prefix(caplog):
    """기존 5필드 prefix 는 **byte 보존**하고 끝에만 붙인다.

    운영 grep·리포터 파서가 그 prefix 를 읽는다. 중간 삽입은 D+1 판독을 깨뜨린다.
    """
    core = _core()
    core._stale_watcher_collector.clear()
    caplog.set_level(logging.INFO)

    core.record_stale_watcher_check({
        "subscribed": 100, "stale": 40, "force_reregistered": 3,
        "skipped_giveup": 1, "force_retried": 2, "cap_blocked": 0,
        "no_feed_skipped": 35,
    })
    core.record_stale_watcher_check({
        "subscribed": 100, "stale": 38, "force_reregistered": 1,
        "skipped_giveup": 0, "force_retried": 1, "cap_blocked": 1,
        "no_feed_skipped": 33,
    })
    core.flush_stale_watcher_collector()

    lines = [r.message for r in caplog.records
             if "[stale_watcher_summary]" in r.message]
    assert len(lines) == 1, f"summary 1행 — actual={lines!r}"
    msg = lines[0]

    expected_prefix = _SUMMARY_PREFIX % (2, 78, 4, 1, 3)
    assert msg.startswith(expected_prefix), (
        "기존 5필드 prefix byte 보존 의무 (신규 필드는 **끝**에만). "
        f"expected prefix={expected_prefix!r} actual={msg!r}"
    )
    assert msg == expected_prefix + " no_feed_skipped=68", (
        f"` no_feed_skipped=%d`(합계 35+33=68) 를 끝에 붙인다 — actual={msg!r}"
    )
    core._stale_watcher_collector.clear()


def test_w8b_summary_missing_key_defaults_to_zero(caplog):
    """구 형태 stats(키 없음)도 0 으로 흡수 — 부팅 중 혼재 사이클 보호."""
    core = _core()
    core._stale_watcher_collector.clear()
    caplog.set_level(logging.INFO)

    core.record_stale_watcher_check({
        "subscribed": 10, "stale": 2, "force_reregistered": 1,
        "skipped_giveup": 0, "force_retried": 0, "cap_blocked": 0,
    })
    core.flush_stale_watcher_collector()

    msg = [r.message for r in caplog.records
           if "[stale_watcher_summary]" in r.message][0]
    assert msg.endswith(" no_feed_skipped=0"), (
        f"키 부재 = 0 (KeyError 금지) — actual={msg!r}"
    )
    core._stale_watcher_collector.clear()


async def test_w8c_skipped_count_reaches_collector(monkeypatch):
    """스킵 수가 실제로 collector 로 흘러간다(로그만 고쳐놓고 값이 0 인 회귀 차단)."""
    core = _core()
    _make_pool(monkeypatch, ["005935", "047040", "006340"])
    _setup_ticks(monkeypatch, stale=["005935", "047040", "006340"])
    _patch_no_sleep(monkeypatch, core)
    _patch_registry(monkeypatch, no_feed={"005935", "047040"})
    sched = _make_sched()
    core._stale_watcher_collector.clear()

    await core.check_and_resubscribe_stale(sched)

    assert len(core._stale_watcher_collector) == 1
    stats = core._stale_watcher_collector[0]
    assert stats.get("no_feed_skipped") == 2, (
        f"LOW no_feed 2종목 skip — actual={stats!r}"
    )
    assert stats.get("stale") == 3, (
        "stale 집계는 은폐하지 않는다 — no_feed 종목도 stale 로 센다 "
        f"(§6 D+1 판독 계약). actual={stats!r}"
    )
    core._stale_watcher_collector.clear()


# ===========================================================================
# W9 — 동시호가 skip 은 no_feed 판정보다 앞
# ===========================================================================
async def test_w9_call_auction_skip_precedes_no_feed_branch(monkeypatch, caplog):
    """동시호가 게이트는 stale 판정 자체를 지연시킨다 — 루프 진입 전이므로
    `is_no_feed` 는 한 번도 불리지 않고 retry 카운터도 그대로다.
    """
    from src.engine.session import session_tracker

    core = _core()
    pool = _make_pool(monkeypatch, ["005935", "006340"])
    _setup_ticks(monkeypatch, stale=["005935", "006340"])
    _patch_no_sleep(monkeypatch, core)
    spy = _patch_registry(monkeypatch, no_feed={"005935"})
    # autouse `_neutralize_call_auction_gate` 를 이 테스트에서만 되돌린다
    monkeypatch.setattr(
        session_tracker, "is_call_auction_now", lambda now=None: True, raising=False,
    )
    sched = _make_sched(retry={"005935": 3})
    caplog.set_level(logging.DEBUG)

    await core.check_and_resubscribe_stale(sched)

    assert any("[stale_skip_call_auction]" in r.getMessage() for r in caplog.records), (
        "동시호가 skip 로그 부재 — 게이트가 no_feed 분기 뒤로 밀렸을 수 있다"
    )
    assert spy.is_no_feed_calls == [], (
        f"동시호가 사이클에서 `is_no_feed` 호출 0 — actual={spy.is_no_feed_calls!r}"
    )
    assert sched._stale_retry_count == {"005935": 3}, (
        f"누적 retry 카운터 보존 (현행 계약) — actual={sched._stale_retry_count!r}"
    )
    pool.subscribe.assert_not_awaited()
    assert [r for r in caplog.records if _HELD_MARKER in r.getMessage()] == [], (
        "동시호가 조기 return 구간에서는 `[no_feed_held]` 도 발화하지 않는다 "
        "(cap 을 조용히 태워 장중 진짜 표본을 잃는 회귀 차단)"
    )
