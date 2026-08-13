"""사이클 215 Red — `resubscribe_stale_priority` split-brain 재구독 결함 회귀 가드.

> **⚠️ 사이클 217 의미 전환 (2026-08-13) — 아래 GS-1/GS-4/GS-5/GS-6 명제 갱신**:
>   cycle215 가 이식한 무조건 `unsubscribe_in_pool` 이 **배포 후 OPSP0003 스팸 회귀**를
>   냈다 (미구독 stale 후보에 unsubscribe SEND → KIS "UNSUBSCRIBE ERROR not found!",
>   08-13 하루 59 건). cycle217 시정 = **구독 상태로 unsubscribe SEND 가드** —
>   실제 구독분만 `unsubscribe_in_pool`, 미구독분(split-brain/stale 후보) 은
>   `_ticker_to_session` 직접 pop (KIS SEND 없이 dedup 해제). 신규 케이스는
>   `test_cycle217_unsubscribe_guard.py`. 본 파일은 cycle215 명제를 cycle217 계약으로
>   전환 (GS-1 = 미구독 → unsubscribe_in_pool 미호출로 반전 / GS-4·GS-5 = 구독분 경로로
>   재정의 / GS-6 = 구독 스냅샷 + 직접 pop AST). GS-2 재SEND 복구 불변은 **유지**(핵심).

> **선행 실측 (cycle215)**: 2026-08-12 EC2 — 001450(donchian)·053800(kojiro) 09:05/09:07
>   매수 후 14:23 까지 tick 미구독. 개장러시 풀 포화 → 매수 HIGH 보유 종목 tick 구독이
>   OPSP0008(MAX SUBSCRIBE OVER) 거부 → 5분 주기 재구독이 온종일 실패 = 손절 사각.
> **근본원인 = split-brain**:
>   - 세션 계층 `KisWebSocket._subscriptions` 는 거부 시 discard (websocket.py).
>   - 풀 계층 `WebsocketPool._ticker_to_session[t] = main` 은 남는다.
>   - `resubscribe_stale_priority` 가 매핑을 팝하지 않고 `subscribe` 만 하면 dedup
>     가드(`existing is self._main → return "main"`)에 걸려 재SEND 가 안 나간다.
>   - cycle215 시정 = `unsubscribe_in_pool` 로 매핑 팝 후 재SEND. **단 이 팝이 KIS
>     unsubscribe SEND 도 동반**해 미구독 종목엔 OPSP0003 을 유발 → cycle217 이 분기.
> **8영역 diff 0 전제**: stale_watcher_core.py 는 realtime/ 미포함 = 8영역 아님.
>   본 시정은 stale_watcher_core.py 단독 — realtime/ 미접촉 (테스트가 realtime/ 수정 요구 금지).

회귀 가드 매트릭스:
- CLAUDE.md 절대 규칙: WebSocket 시세 보유·익일청산 우선 보장 (HIGH bypass_limit=True 사이클 32 R4)
- 사이클 25-B / 29-R3 HIGH/LOW 분리 정책 영속
- 사이클 66 priority 분리 *후* cap 영속 (본 시정과 병존 — cap 로직 무변경)
- 사이클 88 G-REJECT-1 4중 안전망 함수 4종 존재 영속 (본 시정은 함수 *내부* 보강, 존재 불변)

카테고리별 분포 (6 케이스, cycle217 갱신 후):
- HIGH 3: 미구독 직접 pop(GS-1) / 실경로 재SEND+OPSP0003 회피(GS-2) / 구독 LOW 순서(GS-4)
- MEDIUM 2: HIGH 절대 보장 불변(GS-3) / 구독 스냅샷+pop AST(GS-6)
- LOW 1: unsubscribe_in_pool 부작용 가드 + subscribe 인자 불변(GS-5, 구독분 한정)

Red 시점 결과 (현재 코드 = cycle215/216 배포 상태 기준 기대):
- GS-1: FAIL — 현재 코드는 미구독 종목에도 `unsubscribe_in_pool` 호출(await_count>=1).
- GS-2: FAIL — 현재 코드는 미구독 split-brain 에 세션 unsubscribe SEND(OPSP0003 유발).
- GS-6: FAIL — 본체에 `get_subscribed_tickers(` / `_ticker_to_session.pop(` 부재.
- GS-3: PASS(불변) — subscribe 는 HIGH/bypass=True 로 호출 (구독/미구독 무관 불변).
- GS-4: PASS(불변) — 구독 LOW 는 cycle215/217 모두 unsubscribe_in_pool 호출.
- GS-5: PASS(불변) — 구독분 unsubscribe_in_pool 시그니처 + subscribe 인자 불변.
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
TICK_TR_ID = "H0UNCNT0"  # scanner.TICK_TR_ID (사이클 26 이후 get_active_tick_tr_ids 폴백 리터럴)


# ===========================================================================
# fixture helpers (사이클 66 답습)
# ===========================================================================
def _make_scheduler_with_high_tickers(positions: list[str] = None, ndc: set = None):
    """`TradingScheduler.__new__` + positions / _pending_next_day_clear 주입.

    사이클 66 `_make_scheduler_with_high_tickers` 답습 — registry mock + StaleTrackerState.
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


def _make_spy_pool(subscribed=None, ticker_to_session=None):
    """kis_ws_pool spy — unsubscribe_in_pool / subscribe 호출 순서 + 인자 추적.

    두 AsyncMock 의 side_effect 가 공유 `call_log` 에 append → cross-mock 호출 순서 단언.
    subscribe 는 "main" 반환 (resubscribed.append 정상 동작).

    사이클 217 확장 — 구독 가드 3 seam:
      - `get_subscribed_tickers()` → 지정 set (구독 상태 스냅샷 소스).
      - `_ticker_to_session` → 실제 dict (미구독 종목 직접 pop 검증 대상).
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
    """

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


def _order_index(call_log, kind: str, ticker: str) -> int | None:
    """call_log 에서 (kind, *, ticker) 첫 등장 인덱스 (부재 시 None)."""
    for i, e in enumerate(call_log):
        if e[0] == kind and e[2] == ticker:
            return i
    return None


# ===========================================================================
# GS-1 (HIGH) — 핵심 회귀 (cycle217 반전): split-brain 미구독 HIGH 종목 재구독 시
#               unsubscribe_in_pool 미호출 + 매핑 직접 pop + subscribe 재SEND
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-13 10:00:00", tz_offset=-9)
async def test_GS1_split_brain_high_direct_pop_no_unsubscribe_in_pool():
    """GS-1 (핵심 Red, cycle217 반전): HIGH 보유 종목이 split-brain(풀 매핑 잔존, 세션
    미구독)일 때 `resubscribe_stale_priority` 는 `unsubscribe_in_pool` 을 **미호출**하고
    `_ticker_to_session` 직접 pop 후 `subscribe(...HIGH...)` 로 재SEND 해야 한다.

    cycle215 는 무조건 `unsubscribe_in_pool` 로 매핑을 팝했는데, 이 팝이 KIS
    unsubscribe SEND 를 동반해 **미구독** 종목엔 OPSP0003(not found!) 을 유발했다
    (배포 후 08-13 회귀). cycle217 = 미구독분은 매핑만 직접 pop(KIS SEND 없이 dedup 해제).

    Red 단계 (현재 코드): 미구독에도 unsubscribe_in_pool 호출 → await_count>=1 → FAIL.
    Green 단계 (시정 후): await_count==0 + 매핑 pop + subscribe 재SEND → PASS.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 13, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers(positions=["001450"])  # HIGH 보유
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"001450": stale_dt}

    # split-brain: 매핑 잔존(_ticker_to_session) + 미구독(get_subscribed_tickers 부재)
    pool, call_log = _make_spy_pool(
        subscribed=set(),
        ticker_to_session={"001450": object()},
    )

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["001450"], f"HIGH 보유 종목 재구독 대상 포함 의무. 실제: {result}"

    # (핵심 Red) 미구독 → unsubscribe_in_pool 미호출 (KIS unsubscribe SEND 없음 = OPSP0003 회피)
    assert pool.unsubscribe_in_pool.await_count == 0, (
        "split-brain 미구독 종목에 unsubscribe_in_pool 호출 금지 — KIS 에 unsubscribe "
        "SEND 를 보내면 OPSP0003(not found!) ERROR 스팸(08-13 회귀). 미구독분은 매핑 직접 "
        "pop 으로 dedup 만 해제. 현재 코드는 무분별 호출 → FAIL."
    )
    # 매핑 직접 pop 으로 dedup 가드 해제
    assert "001450" not in pool._ticker_to_session, (
        f"미구독 종목 `_ticker_to_session.pop` 직접 pop 의무. 실제 매핑: {pool._ticker_to_session}"
    )
    # subscribe 재SEND (pop 덕에 dedup 가드 우회) — HIGH/bypass=True
    sub_idx = _order_index(call_log, "sub", "001450")
    assert sub_idx is not None, "재SEND(subscribe) 호출 기록 부재"
    sub_entry = call_log[sub_idx]
    assert sub_entry[3] == "HIGH" and sub_entry[4] is True, (
        f"HIGH 보유 종목 subscribe 는 priority=HIGH + bypass_limit=True 의무. 실제: {sub_entry}"
    )


# ===========================================================================
# GS-2 (HIGH) — 핵심 회귀 (실경로): 실제 WebsocketPool + 가짜 세션으로 재SEND 검증
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-13 10:00:00", tz_offset=-9)
async def test_GS2_split_brain_high_real_pool_resends_without_unsubscribe_send():
    """GS-2 (핵심 Red, 실경로): 진짜 `WebsocketPool` + 가짜 메인 세션으로 dedup 가드를
    실제 통과시켜, split-brain HIGH 종목이 **재SEND(cycle215 핵심 불변)** 되면서도
    **KIS unsubscribe SEND 는 발생하지 않아야**(cycle217 OPSP0003 회피) 한다.

    split-brain 재현:
      - `pool._main = fake` (세션 `_subscriptions` 비어 있음 = 거부 후 discard 상태)
      - `pool._ticker_to_session["001450"] = fake` (풀 매핑 잔존)

    cycle217 코드: 미구독 → 매핑 직접 pop → subscribe 가 branch 3 (HIGH 절대 보장) 진입
              → fake.subscribe 실호출(재SEND) + fake.unsubscribe 미호출(KIS SEND 없음).

    Red 단계 (현재 코드): unsubscribe_in_pool → 세션 unsubscribe SEND 호출(OPSP0003 유발)
                        → `fake.unsubscribe_calls` != [] → FAIL.
    Green 단계 (시정 후): fake.subscribe 1회 재SEND + fake.unsubscribe 0회 → PASS.
    """
    from src.engine import stale_manager
    from src.realtime.websocket_pool import WebsocketPool

    base = datetime(2026, 8, 13, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers(positions=["001450"])
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"001450": stale_dt}

    fake = _FakeSession()
    pool = WebsocketPool()
    pool._main = fake
    pool._quotes = []
    # split-brain: 풀 매핑 잔존 + 세션 _subscriptions 공집합 (거부 후 discard 상태)
    pool._ticker_to_session = {"001450": fake}

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["001450"], f"재구독 대상 포함 의무. 실제: {result}"

    # (cycle215 핵심 불변) 실제 세션 재SEND — dedup 가드를 뚫고 subscribe 실호출
    assert len(fake.subscribe_calls) == 1, (
        "split-brain HIGH 종목은 dedup 가드를 뚫고 세션 subscribe 가 실호출되어야 함. "
        f"실제 세션 subscribe 호출: {fake.subscribe_calls}"
    )
    assert (TICK_TR_ID, "001450") in fake._subscriptions, (
        "재SEND 후 세션 `_subscriptions` 에 (H0UNCNT0, 001450) 복원 의무 "
        f"(split-brain 해소). 실제: {fake._subscriptions}"
    )
    # 세션 subscribe 는 bypass_limit=True (HIGH 절대 보장)
    assert fake.subscribe_calls[0][2] is True, (
        f"HIGH 종목 세션 subscribe 는 bypass_limit=True 의무. 실제: {fake.subscribe_calls[0]}"
    )
    # 매핑 복원 (subscribe branch 3 이 재설정)
    assert pool._ticker_to_session.get("001450") is fake, (
        "재SEND 후 `_ticker_to_session` 매핑 복원 의무"
    )
    # (핵심 Red, cycle217) KIS unsubscribe SEND 미발생 — 미구독 종목 OPSP0003 회피
    assert fake.unsubscribe_calls == [], (
        "미구독 split-brain 종목 재구독 시 세션 unsubscribe(=KIS SEND) 미호출 의무 "
        "(OPSP0003 not found! 회피). 현재 코드는 unsubscribe_in_pool 로 SEND → FAIL. "
        f"실제 세션 unsubscribe 호출: {fake.unsubscribe_calls}"
    )


# ===========================================================================
# GS-3 (MEDIUM) — HIGH 절대 보장 불변: 시정 후에도 priority=HIGH + bypass_limit=True
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-13 10:00:00", tz_offset=-9)
async def test_GS3_high_priority_and_bypass_preserved_after_fix():
    """GS-3 (불변 가드, 사이클 32 R4): HIGH 보유 종목은 시정 후에도 subscribe 가
    `priority="HIGH", bypass_limit=True` 로 호출됨 — 구독 가드 분기를 끼워도 HIGH 절대
    보장 semantics 는 불변 (구독분/미구독분 무관).

    현재/시정 코드 모두 subscribe 인자는 HIGH/True → PASS(불변). cycle217 이 HIGH 계약을
    훼손하지 않음을 영구 고정한다 (구독 중 HIGH → 실제 해지 후 재SEND 경로).
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 13, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers(positions=["001450", "053800"])
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"001450": stale_dt, "053800": stale_dt}

    # 둘 다 구독 중 (실제 해지 경로) — HIGH subscribe 인자 불변 확인
    pool, _call_log = _make_spy_pool(
        subscribed={"001450", "053800"},
        ticker_to_session={"001450": object(), "053800": object()},
    )

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert set(result) == {"001450", "053800"}
    for call in pool.subscribe.await_args_list:
        assert call.kwargs.get("priority") == "HIGH", (
            f"HIGH 보유 종목 subscribe priority='HIGH' 의무. 실제: {call.kwargs.get('priority')}"
        )
        assert call.kwargs.get("bypass_limit") is True, (
            f"HIGH 보유 종목 subscribe bypass_limit=True 의무. 실제: {call.kwargs.get('bypass_limit')}"
        )


# ===========================================================================
# GS-4 (불변) — 구독 LOW 경로: 구독 중 LOW 후보는 unsubscribe_in_pool 선행 후 재구독
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-13 10:00:00", tz_offset=-9)
async def test_GS4_subscribed_low_candidate_unsubscribe_in_pool_before_subscribe():
    """GS-4 (불변, cycle217 재정의): **구독 중** LOW 후보 stale 재구독은 cycle215/217
    공통으로 subscribe 앞에 unsubscribe_in_pool 을 선행한다 (실제 해지 = 재등록 회피).

    cycle217 은 구독 상태로 분기 — *구독 중* 종목은 실제 해지 경로가 유지되고,
    미구독 종목만 직접 pop 으로 갈라진다(미구독 케이스는 test_cycle217 이 담당).
    본 테스트는 구독 LOW 경로의 unsubscribe_in_pool 선행 계약을 고정한다.

    Red/Green 모두 PASS(불변) — cycle215/217 공통으로 구독분은 unsubscribe_in_pool 호출.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 13, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers()  # HIGH 0 → 모두 LOW 후보
    stale_dt = base - timedelta(seconds=120)
    low_ticker = "035420"
    ticker_last_tick = {low_ticker: stale_dt}

    # 구독 중 LOW — unsubscribe_in_pool 선행 경로
    pool, call_log = _make_spy_pool(
        subscribed={low_ticker},
        ticker_to_session={low_ticker: object()},
    )

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == [low_ticker]

    assert pool.unsubscribe_in_pool.await_count >= 1, (
        "구독 중 LOW 후보는 subscribe 앞에 unsubscribe_in_pool 선행 의무 (실제 해지). "
        "현재/시정 코드 모두 호출 → 불변."
    )
    unsub_idx = _order_index(call_log, "unsub", low_ticker)
    sub_idx = _order_index(call_log, "sub", low_ticker)
    assert unsub_idx is not None and sub_idx is not None
    assert unsub_idx < sub_idx, (
        f"구독 LOW 후보 unsubscribe_in_pool 은 subscribe *앞*. 실제 call_log={call_log}"
    )
    # LOW subscribe 는 priority=LOW + bypass_limit=False (사이클 25-B 영속)
    low_sub = next(c for c in pool.subscribe.await_args_list if c.args[1] == low_ticker)
    assert low_sub.kwargs.get("priority") == "LOW"
    assert low_sub.kwargs.get("bypass_limit") is False


# ===========================================================================
# GS-5 (LOW) — 부작용 가드: 구독분 unsubscribe_in_pool 은 pop+세션 unsubscribe 만,
#              subscribe 인자(priority/bypass) 불변
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-13 10:00:00", tz_offset=-9)
async def test_GS5_unsubscribe_in_pool_signature_and_subscribe_args_invariant():
    """GS-5 (부작용 가드, 구독분 한정): **구독 중** 종목의 unsubscribe_in_pool 은
    `(TICK_TR_ID, ticker)` 2 위치인자만 — priority/bypass 등 subscribe semantics 를
    실어 나르지 않는다. subscribe 인자는 종목 우선순위대로 불변(HIGH→HIGH/True,
    LOW→LOW/False).

    Red/Green 모두 PASS(불변) — 구독분은 cycle215/217 공통 unsubscribe_in_pool 호출.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 13, 10, 0, 0, tzinfo=KST)
    # HIGH 1 (001450) + LOW 1 (035420) 혼재, 둘 다 구독 중
    sched = _make_scheduler_with_high_tickers(positions=["001450"])
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"001450": stale_dt, "035420": stale_dt}

    pool, _call_log = _make_spy_pool(
        subscribed={"001450", "035420"},
        ticker_to_session={"001450": object(), "035420": object()},
    )

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert pool.unsubscribe_in_pool.await_count >= 1, (
        "unsubscribe_in_pool 호출 필요 (부작용 가드 전제) — 현재 코드는 미호출 → FAIL."
    )
    # unsubscribe_in_pool 은 (tr_id, ticker) 2 위치인자만, kwargs 없음
    for call in pool.unsubscribe_in_pool.await_args_list:
        assert call.args[0] == TICK_TR_ID, (
            f"unsubscribe_in_pool 첫 인자는 TICK_TR_ID 의무. 실제: {call.args}"
        )
        assert len(call.args) == 2, (
            f"unsubscribe_in_pool 은 (tr_id, ticker) 2 위치인자만. 실제: {call.args}"
        )
        assert call.kwargs == {}, (
            f"unsubscribe_in_pool 에 priority/bypass 등 kwargs 금지 (pop+세션 unsubscribe 만). "
            f"실제 kwargs: {call.kwargs}"
        )
    # subscribe 인자 불변 — 종목별 우선순위 정합
    for call in pool.subscribe.await_args_list:
        ticker = call.args[1]
        if ticker == "001450":
            assert call.kwargs.get("priority") == "HIGH"
            assert call.kwargs.get("bypass_limit") is True
        else:
            assert call.kwargs.get("priority") == "LOW"
            assert call.kwargs.get("bypass_limit") is False


# ===========================================================================
# GS-6 (MEDIUM) — AST 정적 가드 (cycle217): 구독 스냅샷 + 미구독 직접 pop 분기
# ===========================================================================
def test_GS6_subscribed_snapshot_and_direct_pop_static_guard():
    """GS-6 (AST 정적 가드, cycle217 재정의): `resubscribe_stale_priority` 본체가
    (1) `get_subscribed_tickers(` 구독 스냅샷을 확보하고 (2) 미구독 분기에서
    `_ticker_to_session.pop(` 직접 pop 을 수행하며 (3) 구독 분기의 `unsubscribe_in_pool(`
    가 잔존한다 (구독 가드 3 seam). 셋 다 재SEND `subscribe(` 보다 텍스트상 *먼저*.

    사이클 67 분해 후 stale_watcher_core.py 가 진실의 원천 (fallback: stale_manager.py) —
    사이클 66 AST 가드 candidate_paths 패턴 답습.

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

    # (1) 구독 스냅샷 존재 의무 — 현재 코드는 부재 → FAIL
    assert ".get_subscribed_tickers(" in func_source, (
        "시정 의무: 재구독 루프 *전* `subscribed = kis_ws_pool.get_subscribed_tickers()` "
        "스냅샷 확보. 현재 부재 → 미구독 종목 무분별 unsubscribe SEND = OPSP0003 스팸."
    )
    # (2) 미구독 분기 직접 pop 존재 의무 — 현재 코드는 부재 → FAIL
    assert "._ticker_to_session.pop(" in func_source, (
        "시정 의무: 미구독 종목은 `kis_ws_pool._ticker_to_session.pop(ticker, None)` 직접 pop "
        "(KIS unsubscribe SEND 없이 dedup 가드 해제). 현재 부재 → FAIL."
    )
    # (3) 구독 분기 unsubscribe_in_pool 잔존 의무 (실제 해지, cycle215 계약 보존)
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
    # 사이클 66 priority 분리 *후* cap 로직 병존 검증 (본 시정이 cap 로직 훼손 금지)
    assert "high_targets" in func_source and "low_targets" in func_source, (
        "사이클 66 priority 분리 (`high_targets`/`low_targets`) 병존 의무 — 본 시정과 독립"
    )
