"""사이클 217 Red — `resubscribe_stale_priority` OPSP0003 스팸 회귀 가드.

> **선행 실측 (배포 후 발견, 2026-08-13 EC2)**:
>   cycle215 가 `resubscribe_stale_priority`(stale_watcher_core.py:509-533) 에 이식한
>   `unsubscribe_in_pool(TICK_TR_ID, ticker)` 가 KIS 에 unsubscribe SEND 를 보내는데,
>   이 함수 stale 소스(`scanner.ticker_last_tick`) 에는 **실제 미구독 종목**(stale 후보 /
>   split-brain) 이 섞여 있다. 미구독 종목에 unsubscribe SEND 를 보내면 KIS 가
>   `OPSP0003 "UNSUBSCRIBE ERROR(not found!)"` 를 반환 → 08-13 하루 59 건 ERROR 스팸
>   (08-11/12 는 0). 거부 전부 LOW 후보(보유 아님, 손절 무해)나 ERROR 스팸 + 잠재 LMS.
> **K watcher 무발생 근거**: `check_and_resubscribe_stale` 의 stale 소스는
>   `kis_ws_pool.get_subscribed_tickers()`(=`_subscriptions`, 항상 실제 구독) 라 미구독
>   종목이 섞이지 않는다. 결함은 `resubscribe_stale_priority`(소스=`ticker_last_tick`) 한정.

> **시정 방향 (backend-dev 구현 — 본 파일은 그 행위의 Red)**:
>   재구독 루프에서 **구독 상태로 unsubscribe SEND 를 가드**한다.
>   1) 루프 진입 *전* `subscribed = kis_ws_pool.get_subscribed_tickers()` 스냅샷 1회.
>   2) 각 ticker:
>      - `ticker in subscribed`(실제 구독 중) → 기존대로 `unsubscribe_in_pool` +
>        `sleep(0.05)` (실제 해지 = KIS "신규 등록" 패턴, 재등록 회피).
>      - `ticker not in subscribed`(미구독 = split-brain / stale 후보) →
>        **`kis_ws_pool._ticker_to_session.pop(ticker, None)` 직접 pop 만**
>        (KIS unsubscribe 미발송 → OPSP0003 회피). try/except graceful.
>      - 이후 `subscribe(...)` 무변경 (dedup 가드가 pop 덕에 재SEND).

> **8영역 diff 0 전제**: stale_watcher_core.py 는 realtime/ 미포함 = 8영역 아님.
>   `_ticker_to_session` 직접 접근은 *런타임* — realtime/ 파일 미편집.
>   사이클 88 G-REJECT-1 4중 안전망 AST(`def resubscribe_stale_priority` 존재)와 무충돌.

회귀 가드 매트릭스:
- cycle215 split-brain 재SEND 복구 (HIGH bypass_limit=True) — 핵심 불변 (재SEND 유지).
- cycle216 동시호가 LOW skip + LOW throttle — 병존 (구독 가드는 그 필터 *후* 루프 내).
- CLAUDE.md WebSocket 시세 보유·익일청산 우선 보장 (HIGH bypass=True 사이클 32 R4).

카테고리별 분포 (7 케이스):
- HIGH 5: 미구독 직접 pop(G217-1) / 구독 vs 미구독 게이트(G217-2) / 실경로 HIGH 재SEND+
          OPSP0003 회피(G217-3) / OPSP0003 회피 실증 대비(G217-4) / 동시호가 병존(G217-5)
- MEDIUM 2: throttle 병존(G217-6) / AST 정적 가드(G217-7)

Red 시점 결과 (현재 코드 = cycle215/216 배포 상태 기준 기대):
- G217-1: FAIL — 현재 코드는 미구독 종목에도 `unsubscribe_in_pool` 호출 (await_count>=1).
- G217-2: FAIL — 현재 코드는 미구독 종목에도 `unsubscribe_in_pool` 호출 (구독/미구독 무분별).
- G217-3: FAIL — 현재 코드는 미구독 split-brain 에 세션 unsubscribe SEND (OPSP0003 유발).
- G217-4: FAIL — 현재 코드는 미구독 종목 재구독 시 세션 unsubscribe(KIS SEND) 호출.
- G217-5: FAIL — 현재 코드는 동시호가 HIGH split-brain 에 `unsubscribe_in_pool` 호출.
- G217-6: FAIL — 현재 코드는 throttle 통과 split-brain LOW 에 `unsubscribe_in_pool` 호출.
- G217-7: FAIL — 현재 코드 함수 본체에 `get_subscribed_tickers(` / `_ticker_to_session.pop(` 부재.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
TICK_TR_ID = "H0UNCNT0"  # scanner.TICK_TR_ID (사이클 26 이후 폴백 리터럴, cycle215/216 답습)


# ===========================================================================
# fixture helpers (cycle215/216 답습)
# ===========================================================================
def _make_scheduler_with_high_tickers(positions: list[str] = None, ndc: set = None):
    """`TradingScheduler.__new__` + positions / _pending_next_day_clear 주입.

    cycle216 답습 — `_stale_last_resubscribe_at` 는 property → `_stale_state`
    dict 로, throttle seed 는 `sched._stale_last_resubscribe_at[t] = dt` 로 주입 가능.
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


def _make_guard_spy_pool(subscribed=None, ticker_to_session=None):
    """kis_ws_pool spy — 구독 가드 3 seam 추적.

    - `get_subscribed_tickers()` → 지정 set (구독 상태 스냅샷 소스).
    - `_ticker_to_session` → 실제 dict (직접 pop 검증 대상).
    - `unsubscribe_in_pool` / `subscribe` → AsyncMock (호출 추적).

    cycle215 `_make_spy_pool` 을 cycle217 가드 3 seam 으로 확장.
    """
    call_log: list[tuple] = []

    def _unsub(tr_id, tr_key):
        call_log.append(("unsub", tr_id, tr_key))

    def _sub(tr_id, tr_key, *, priority="LOW", bypass_limit=False):
        call_log.append(("sub", tr_id, tr_key, priority, bypass_limit))
        return "main"

    pool = MagicMock()
    pool.unsubscribe_in_pool = AsyncMock(side_effect=_unsub)
    pool.subscribe = AsyncMock(side_effect=_sub)
    pool.get_subscribed_tickers = MagicMock(return_value=set(subscribed or set()))
    pool._ticker_to_session = dict(ticker_to_session or {})
    return pool, call_log


class _FakeSession:
    """KisWebSocket 최소 대역 — subscribe/unsubscribe 가 `_subscriptions` set 변이.

    실제 WebsocketPool + 가짜 세션 조합으로 split-brain dedup 가드를 실경로로 재현.
    `unsubscribe_calls` 추적 = KIS unsubscribe SEND 발생 여부 (OPSP0003 유발 실증).
    """

    def __init__(self, subscriptions=None) -> None:
        self._subscriptions: set[tuple[str, str]] = set(subscriptions or set())
        self._subscriptions_acked: set[tuple[str, str]] = set(subscriptions or set())
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
    """`session_tracker` 대역 — `is_call_auction_now(now)` 가 지정 bool 반환 (cycle216 답습)."""
    m = MagicMock()
    m.is_call_auction_now = MagicMock(return_value=call_auction)
    return m


def _order_index(call_log, kind: str, ticker: str) -> int | None:
    for i, e in enumerate(call_log):
        if e[0] == kind and e[2] == ticker:
            return i
    return None


# ===========================================================================
# G217-1 (HIGH) — 미구독 종목: unsubscribe_in_pool 미호출 + 매핑 직접 pop + 재SEND
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-13 10:00:00", tz_offset=-9)
async def test_G217_1_unsubscribed_ticker_direct_pop_no_unsubscribe_in_pool():
    """G217-1 (핵심 Red): 미구독(split-brain / stale 후보) 종목 재구독 시
    `unsubscribe_in_pool` 을 **미호출**(await_count==0)하고 `_ticker_to_session` 에서
    직접 pop 한 뒤 `subscribe(...)` 재SEND 해야 한다.

    미구독 종목에 unsubscribe SEND 를 보내면 KIS 가 OPSP0003(UNSUBSCRIBE ERROR
    not found!) 을 반환 = ERROR 스팸. 매핑 직접 pop 은 KIS SEND 없이 dedup 가드만 해제.

    Red 단계 (현재 코드): 미구독에도 `unsubscribe_in_pool` 호출 → await_count>=1 → FAIL.
    Green 단계 (시정 후): await_count==0 + 매핑 pop + subscribe 재SEND → PASS.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 13, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers(positions=["001450"])  # HIGH 보유
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"001450": stale_dt}

    # split-brain: 풀 매핑 잔존 + get_subscribed_tickers 부재 (거부 후 discard 상태)
    pool, call_log = _make_guard_spy_pool(
        subscribed=set(),
        ticker_to_session={"001450": object()},
    )

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["001450"], f"재구독 대상 포함 의무. 실제: {result}"

    # (핵심 Red) 미구독 종목 → unsubscribe_in_pool 미호출 (KIS unsubscribe SEND 없음)
    assert pool.unsubscribe_in_pool.await_count == 0, (
        "미구독(split-brain) 종목에 unsubscribe_in_pool 호출 금지 — KIS 에 unsubscribe "
        "SEND 를 보내면 OPSP0003(not found!) ERROR 스팸. 현재 코드는 무분별 호출 → FAIL."
    )
    # 매핑 직접 pop 으로 dedup 가드 해제
    assert "001450" not in pool._ticker_to_session, (
        "미구독 종목은 `_ticker_to_session.pop(ticker)` 직접 pop 으로 dedup 가드 해제 의무. "
        f"실제 매핑: {pool._ticker_to_session}"
    )
    # subscribe 재SEND (pop 덕에 dedup 가드 우회)
    sub_idx = _order_index(call_log, "sub", "001450")
    assert sub_idx is not None, "재SEND(subscribe) 호출 기록 부재"
    sub_entry = call_log[sub_idx]
    assert sub_entry[3] == "HIGH" and sub_entry[4] is True, (
        f"HIGH 보유 종목 subscribe 는 priority=HIGH + bypass_limit=True 의무. 실제: {sub_entry}"
    )


# ===========================================================================
# G217-2 (HIGH) — 구독 vs 미구독 게이트: 구독분만 unsubscribe_in_pool 호출
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-13 10:00:00", tz_offset=-9)
async def test_G217_2_subscribed_calls_unsubscribe_unsubscribed_does_not():
    """G217-2 (핵심 Red, 게이트): 실제 구독 중(`get_subscribed_tickers` 포함) stale 종목은
    기존대로 `unsubscribe_in_pool` 호출(실제 해지 = 재등록 회피), 미구독 종목은 미호출.

    시나리오: LOW 2 stale — "035000"(구독 중) + "035420"(미구독 split-brain).

    Red 단계 (현재 코드): 구독 상태 무관 둘 다 unsubscribe_in_pool 호출 →
                        "035420" 도 호출됨 → FAIL.
    Green 단계 (시정 후): "035000" 만 unsubscribe_in_pool, "035420" 은 직접 pop → PASS.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 13, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers()  # HIGH 0 → 모두 LOW
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"035000": stale_dt, "035420": stale_dt}

    # "035000" 구독 중, "035420" 미구독 (둘 다 매핑 잔존)
    pool, _call_log = _make_guard_spy_pool(
        subscribed={"035000"},
        ticker_to_session={"035000": object(), "035420": object()},
    )

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["035000", "035420"], f"둘 다 재구독 대상 (sorted). 실제: {result}"

    unsub_keys = {c.args[1] for c in pool.unsubscribe_in_pool.await_args_list}
    # 구독 중 종목만 unsubscribe_in_pool 호출 (실제 해지)
    assert "035000" in unsub_keys, (
        "구독 중 stale 종목은 기존대로 unsubscribe_in_pool 호출 의무 (실제 해지 = 재등록 회피)."
    )
    # (핵심 Red) 미구독 종목은 unsubscribe_in_pool 미호출 (OPSP0003 회피)
    assert "035420" not in unsub_keys, (
        "미구독 종목에 unsubscribe_in_pool 호출 금지 (OPSP0003 회피). 현재 코드는 구독/미구독 "
        f"무분별 호출 → FAIL. 실제 unsubscribe_in_pool 호출 키: {unsub_keys}"
    )
    # 미구독 종목은 매핑 직접 pop
    assert "035420" not in pool._ticker_to_session, "미구독 종목 매핑 직접 pop 의무"


# ===========================================================================
# G217-3 (HIGH) — 실경로: split-brain HIGH 재SEND 복구 + KIS unsubscribe SEND 미발생
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-13 10:00:00", tz_offset=-9)
async def test_G217_3_real_pool_split_brain_high_resends_without_unsubscribe_send():
    """G217-3 (핵심 Red, 실경로): 진짜 `WebsocketPool` + 가짜 세션으로,
    미구독 split-brain HIGH 종목이 **재SEND 복구(cycle215 핵심 불변)** 되면서도
    **KIS unsubscribe SEND 는 발생하지 않아야**(OPSP0003 미유발) 한다.

    split-brain 재현:
      - `pool._main = fake` (세션 `_subscriptions` 공집합 = 거부 후 discard 상태)
      - `pool._ticker_to_session["001450"] = fake` (풀 매핑 잔존)

    Red 단계 (현재 코드): unsubscribe_in_pool → 세션 unsubscribe SEND 호출(OPSP0003 유발)
                        → `fake.unsubscribe_calls` != [] → FAIL.
    Green 단계 (시정 후): 매핑 직접 pop → subscribe 재SEND(복구) + 세션 unsubscribe 미호출 → PASS.
    """
    from src.engine import stale_manager
    from src.realtime.websocket_pool import WebsocketPool

    base = datetime(2026, 8, 13, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers(positions=["001450"])
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"001450": stale_dt}

    fake = _FakeSession()  # _subscriptions 공집합 = split-brain
    pool = WebsocketPool()
    pool._main = fake
    pool._quotes = []
    pool._ticker_to_session = {"001450": fake}

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["001450"], f"재구독 대상 포함 의무. 실제: {result}"

    # (cycle215 핵심 불변) 재SEND 복구 — 세션 subscribe 1회 + _subscriptions 복원
    assert len(fake.subscribe_calls) == 1, (
        "split-brain HIGH 종목은 dedup 가드를 뚫고 세션 subscribe 재SEND 의무 (cycle215 불변). "
        f"실제 세션 subscribe 호출: {fake.subscribe_calls}"
    )
    assert (TICK_TR_ID, "001450") in fake._subscriptions, (
        f"재SEND 후 세션 `_subscriptions` 복원 의무 (split-brain 해소). 실제: {fake._subscriptions}"
    )
    assert fake.subscribe_calls[0][2] is True, (
        f"HIGH 종목 세션 subscribe 는 bypass_limit=True 의무. 실제: {fake.subscribe_calls[0]}"
    )
    # (핵심 Red) KIS unsubscribe SEND 미발생 — OPSP0003 미유발
    assert fake.unsubscribe_calls == [], (
        "미구독 split-brain 종목 재구독 시 세션 unsubscribe(=KIS SEND) 미호출 의무 "
        "(OPSP0003 not found! 회피). 현재 코드는 unsubscribe_in_pool 로 SEND → FAIL. "
        f"실제 세션 unsubscribe 호출: {fake.unsubscribe_calls}"
    )


# ===========================================================================
# G217-4 (HIGH) — OPSP0003 회피 실증: 구독분만 세션 unsubscribe(=KIS SEND) 호출
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-13 10:00:00", tz_offset=-9)
async def test_G217_4_real_pool_only_subscribed_triggers_session_unsubscribe():
    """G217-4 (핵심 Red, 실경로 대비): 진짜 `WebsocketPool` + 가짜 세션으로,
    구독 중 종목은 세션 unsubscribe(=KIS SEND) 호출(실제 해지), 미구독 종목은 미호출
    (OPSP0003 회피) 임을 실증한다.

    시나리오: LOW 2 stale — "035000"(세션 `_subscriptions` 포함 = 구독) +
             "035420"(매핑만 잔존 = 미구독).

    Red 단계 (현재 코드): 둘 다 unsubscribe_in_pool → 세션 unsubscribe SEND 2회 →
                        "035420" 도 SEND → FAIL.
    Green 단계 (시정 후): "035000" 만 세션 unsubscribe SEND, "035420" 은 직접 pop → PASS.
    """
    from src.engine import stale_manager
    from src.realtime.websocket_pool import WebsocketPool

    base = datetime(2026, 8, 13, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers()  # HIGH 0 → 모두 LOW
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"035000": stale_dt, "035420": stale_dt}

    # "035000" 은 세션 구독 중, "035420" 은 매핑만 잔존(미구독)
    fake = _FakeSession(subscriptions={(TICK_TR_ID, "035000")})
    pool = WebsocketPool()
    pool._main = fake
    pool._quotes = []
    pool._ticker_to_session = {"035000": fake, "035420": fake}

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["035000", "035420"], f"둘 다 재구독 대상 (sorted). 실제: {result}"

    # 구독분 → 세션 unsubscribe SEND (실제 해지)
    assert (TICK_TR_ID, "035000") in fake.unsubscribe_calls, (
        "구독 중 종목은 세션 unsubscribe(=KIS SEND) 호출 의무 (실제 해지 = 재등록 회피)."
    )
    # (핵심 Red) 미구독분 → 세션 unsubscribe SEND 미발생 (OPSP0003 회피)
    assert (TICK_TR_ID, "035420") not in fake.unsubscribe_calls, (
        "미구독 종목 재구독 시 세션 unsubscribe(=KIS SEND) 미호출 의무 (OPSP0003 회피). "
        f"현재 코드는 무분별 SEND → FAIL. 실제 세션 unsubscribe 호출: {fake.unsubscribe_calls}"
    )
    # 둘 다 재SEND 복구 (구독 가드가 재SEND 자체를 막지 않음)
    assert (TICK_TR_ID, "035000") in fake._subscriptions
    assert (TICK_TR_ID, "035420") in fake._subscriptions


# ===========================================================================
# G217-5 (HIGH) — cycle216 병존: 동시호가 LOW skip + 구독 가드 (필터 후 루프 내)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-13 10:00:00", tz_offset=-9)
async def test_G217_5_call_auction_low_skip_coexists_with_unsubscribe_guard():
    """G217-5 (병존 Red): 동시호가(cycle216 보강 A) LOW skip 이 유지되면서, skip 을
    통과한 HIGH split-brain 종목엔 구독 가드가 적용(미구독 → unsubscribe_in_pool 미호출)
    되어야 한다. 구독 가드는 동시호가/throttle 필터 *후* 루프 내에서 동작.

    시나리오: `is_call_auction_now`=True + HIGH 1 split-brain(미구독) + LOW 2 stale.

    Red 단계 (현재 코드): 동시호가 LOW skip 은 작동(cycle216)하나 HIGH split-brain 에
                        unsubscribe_in_pool 호출 → await_count>=1 → FAIL.
    Green 단계 (시정 후): LOW skip 유지 + HIGH 는 직접 pop → await_count==0 → PASS.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 13, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers(positions=["005930"])  # HIGH 1
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"005930": stale_dt, "035420": stale_dt, "035720": stale_dt}

    # HIGH 005930 split-brain (미구독) — LOW 는 동시호가로 skip 되어 매핑 불요
    pool, call_log = _make_guard_spy_pool(
        subscribed=set(),
        ticker_to_session={"005930": object()},
    )

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(True)), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    # 동시호가 → HIGH 만 재구독, LOW 전량 skip (cycle216 보강 A 병존)
    assert result == ["005930"], (
        f"동시호가 시 LOW skip + HIGH 유지 (cycle216 병존). 실제: {result}"
    )
    # LOW 후보 subscribe 미호출 (동시호가 skip)
    assert not [c for c in call_log if c[0] == "sub" and c[2] in ("035420", "035720")], (
        "동시호가 LOW skip — LOW 후보는 구독 가드 루프 이전 필터에서 제거"
    )
    # (핵심 Red) HIGH split-brain → unsubscribe_in_pool 미호출 (구독 가드 적용)
    assert pool.unsubscribe_in_pool.await_count == 0, (
        "동시호가 skip 을 통과한 HIGH split-brain(미구독) 에 unsubscribe_in_pool 호출 금지 "
        "(OPSP0003 회피, 구독 가드는 필터 후 루프 내 동작). 현재 코드는 호출 → FAIL."
    )
    assert "005930" not in pool._ticker_to_session, "HIGH split-brain 매핑 직접 pop 의무"
    # HIGH 재SEND (bypass_limit=True)
    sub_entry = call_log[_order_index(call_log, "sub", "005930")]
    assert sub_entry[3] == "HIGH" and sub_entry[4] is True


# ===========================================================================
# G217-6 (MEDIUM) — cycle216 병존: LOW throttle skip + 구독 가드 (throttle → 가드 순서)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-13 10:00:00", tz_offset=-9)
async def test_G217_6_low_throttle_skip_coexists_with_unsubscribe_guard():
    """G217-6 (병존 Red): LOW throttle(cycle216 보강 B) skip 이 유지되면서, throttle 을
    통과한 split-brain LOW 종목엔 구독 가드가 적용(미구독 → unsubscribe_in_pool 미호출)
    되어야 한다. 구독 가드는 throttle 필터 *후* 루프 내에서 동작.

    시나리오: HIGH 0, LOW 2 — "035000"(throttle seed now-100s → skip) +
             "035420"(throttle 미기록 통과, split-brain 미구독).

    Red 단계 (현재 코드): throttle skip 은 작동(cycle216)하나 통과분 "035420" 에
                        unsubscribe_in_pool 호출 → await_count>=1 → FAIL.
    Green 단계 (시정 후): throttle skip 유지 + 통과분 직접 pop → await_count==0 → PASS.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 13, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers()  # HIGH 0 → 모두 LOW
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"035000": stale_dt, "035420": stale_dt}

    # "035000" throttle 이내(now-100s < 180) → skip
    sched._stale_last_resubscribe_at["035000"] = base - timedelta(seconds=100)

    # "035420" 만 매핑 잔존 (throttle 통과분, split-brain 미구독)
    pool, call_log = _make_guard_spy_pool(
        subscribed=set(),
        ticker_to_session={"035420": object()},
    )

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    # throttle skip 병존 (cycle216 보강 B)
    assert "035000" not in result, "throttle 이내 LOW 는 재구독 skip (cycle216 병존)"
    assert result == ["035420"], f"throttle 통과분만 재구독. 실제: {result}"
    assert not [c for c in call_log if c[0] == "sub" and c[2] == "035000"], (
        "throttle skip 종목은 subscribe 미호출 — 구독 가드 루프 이전 필터에서 제거"
    )
    # (핵심 Red) throttle 통과 split-brain → unsubscribe_in_pool 미호출 (구독 가드 적용)
    assert pool.unsubscribe_in_pool.await_count == 0, (
        "throttle 을 통과한 split-brain LOW(미구독) 에 unsubscribe_in_pool 호출 금지 "
        "(OPSP0003 회피, 구독 가드는 throttle 후 루프 내 동작). 현재 코드는 호출 → FAIL."
    )
    assert "035420" not in pool._ticker_to_session, "throttle 통과 split-brain 매핑 직접 pop 의무"


# ===========================================================================
# G217-7 (MEDIUM) — AST 정적 가드: 구독 스냅샷 + 분기 구조
# ===========================================================================
def test_G217_7_subscribed_snapshot_and_branch_static_guard():
    """G217-7 (AST 정적 가드): `resubscribe_stale_priority` 본체가
    (1) `get_subscribed_tickers(` 스냅샷을 확보하고 (2) 미구독 분기에서
    `_ticker_to_session.pop(` 직접 pop 을 수행하며 (3) 구독 분기의 `unsubscribe_in_pool(`
    가 잔존해야 한다 (구독 가드 3 seam 영구 검증).

    스냅샷은 재구독 `subscribe(` 보다, pop / unsubscribe_in_pool 도 subscribe 보다 먼저.

    Red 단계 (현재 코드): 본체에 `get_subscribed_tickers(` / `_ticker_to_session.pop(` 부재 → FAIL.
    Green 단계 (시정 후): 3 seam 존재 + subscribe 앞 위치 → PASS.
    """
    engine_root = Path(__file__).parent.parent.parent.parent.parent / "src/engine"
    candidate_paths = [
        engine_root / "stale_watcher_core.py",
        engine_root / "stale_manager.py",
    ]
    source = None
    chosen_path = None
    for p in candidate_paths:
        if p.exists():
            source = p.read_text()
            chosen_path = p
            break

    assert source is not None, "stale_watcher_core.py / stale_manager.py 모두 미존재"

    tree = ast.parse(source)
    target_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "resubscribe_stale_priority":
            target_func = node
            break

    assert target_func is not None, (
        f"{chosen_path}: `resubscribe_stale_priority` async 함수 발견 의무"
    )

    func_source = ast.unparse(target_func)

    # (1) 구독 상태 스냅샷 — get_subscribed_tickers() 호출 존재 의무
    assert ".get_subscribed_tickers(" in func_source, (
        "시정 의무: 재구독 루프 *전* `subscribed = kis_ws_pool.get_subscribed_tickers()` "
        "스냅샷 확보. 현재 부재 → 미구독 종목 무분별 unsubscribe SEND = OPSP0003 스팸."
    )
    # (2) 미구독 분기 — `_ticker_to_session.pop(` 직접 pop 존재 의무
    assert "._ticker_to_session.pop(" in func_source, (
        "시정 의무: 미구독 종목은 `kis_ws_pool._ticker_to_session.pop(ticker, None)` 직접 pop "
        "(KIS unsubscribe SEND 없이 dedup 가드 해제). 현재 부재 → FAIL."
    )
    # (3) 구독 분기 — unsubscribe_in_pool 잔존 (실제 해지 = 재등록 회피, cycle215 계약)
    assert ".unsubscribe_in_pool(" in func_source, (
        "구독 중 종목 실제 해지 경로 `unsubscribe_in_pool` 잔존 의무 (cycle215 계약 보존)."
    )

    # 순서: 스냅샷 / pop / unsubscribe_in_pool 모두 subscribe *앞*
    sub_idx = func_source.index(".subscribe(")
    assert func_source.index(".get_subscribed_tickers(") < sub_idx, (
        "구독 스냅샷은 재구독 subscribe *앞* 확보 의무 (루프 진입 전 1회)."
    )
    assert func_source.index("._ticker_to_session.pop(") < sub_idx, (
        "미구독 직접 pop 은 재SEND subscribe *앞*(dedup 가드 해제 → 재SEND)."
    )
    assert func_source.index(".unsubscribe_in_pool(") < sub_idx, (
        "구독분 unsubscribe_in_pool 은 재SEND subscribe *앞*."
    )
    # 사이클 66 priority 분리 병존 (본 시정이 cap/priority 로직 훼손 금지)
    assert "high_targets" in func_source and "low_targets" in func_source, (
        "사이클 66 priority 분리 (`high_targets`/`low_targets`) 병존 의무 — 본 시정과 독립"
    )
