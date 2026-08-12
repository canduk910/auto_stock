"""사이클 215 Red — `resubscribe_stale_priority` split-brain 재구독 결함 회귀 가드.

> **선행 실측**: 2026-08-12 EC2 — 001450(donchian)·053800(kojiro) 09:05/09:07 매수 후
>   14:23 까지 tick 미구독. 개장러시 풀 포화 → 매수 HIGH 보유 종목 tick 구독이
>   OPSP0008(MAX SUBSCRIBE OVER) 거부 → 5분 주기 재구독이 온종일 실패 = 손절 사각.
> **근본원인 = split-brain**:
>   - 세션 계층 `KisWebSocket._subscriptions` 는 거부 시 discard (websocket.py:716).
>   - 풀 계층 `WebsocketPool._ticker_to_session[t] = main` 은 남는다.
>   - 이후 `resubscribe_stale_priority`(stale_watcher_core.py:489-493) 가
>     `unsubscribe_in_pool` 없이 `kis_ws_pool.subscribe(HIGH)` 를 직접 호출 →
>     풀 dedup 가드(websocket_pool.py:309-313 `existing is self._main → return "main"`)에
>     걸려 **재SEND 가 나가지 않음**.
>   - 반면 K watcher `check_and_resubscribe_stale`(stale_watcher_core.py:342-347) 는
>     `unsubscribe_in_pool(TICK_TR_ID, ticker)` → `sleep(0.05)` → `subscribe(...)` 로
>     매핑을 팝하고 재SEND 한다.
> **시정 방향 (backend-dev)**: `resubscribe_stale_priority` 의 `subscribe`(:489) *앞*에
>   `await kis_ws_pool.unsubscribe_in_pool(TICK_TR_ID, ticker)` + `await asyncio.sleep(0.05)`
>   추가(K watcher 342-347 패턴 이식). HIGH/LOW 공통 적용.
> **위험 등급**: HIGH (KIS 손절 사각 직결 + 사이클 29 005935 사고 패턴 동일 클래스).
> **8영역 diff 0 전제**: stale_watcher_core.py 는 realtime/ 미포함 = 8영역 아님.
>   본 시정은 stale_watcher_core.py 단독 — realtime/ 미접촉 (테스트가 realtime/ 수정 요구 금지).

회귀 가드 매트릭스:
- CLAUDE.md 절대 규칙: WebSocket 시세 보유·익일청산 우선 보장 (HIGH bypass_limit=True 사이클 32 R4)
- 사이클 25-B / 29-R3 HIGH/LOW 분리 정책 영속
- 사이클 66 priority 분리 *후* cap 영속 (본 시정과 병존 — cap 로직 무변경)
- 사이클 88 G-REJECT-1 4중 안전망 함수 4종 존재 영속 (본 시정은 함수 *내부* 보강, 존재 불변)

카테고리별 분포 (6 케이스):
- HIGH 3: 핵심 spy 호출순서(GS-1) / 핵심 real-pool 재SEND(GS-2) / LOW 공통 순서(GS-4)
- MEDIUM 2: HIGH 절대 보장 불변(GS-3) / AST 정적 가드(GS-6)
- LOW 1: unsubscribe_in_pool 부작용 가드 + subscribe 인자 불변(GS-5)

Red 시점 결과 (현재 코드 기준 기대):
- GS-1: FAIL — 현재 코드는 `unsubscribe_in_pool` 미호출.
- GS-2: FAIL — 현재 코드는 dedup 가드에 걸려 세션 재SEND 0건.
- GS-4: FAIL — LOW 후보도 현재 `unsubscribe_in_pool` 미호출.
- GS-5: FAIL(부분) — unsubscribe_in_pool 호출 자체가 없어 시그니처 단언 미충족.
- GS-6: FAIL — `resubscribe_stale_priority` 본체에 `unsubscribe_in_pool` 부재.
- GS-3: PASS(불변) — 현재도 subscribe 는 HIGH/bypass=True 로 호출 (시정 후 불변 가드).
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


def _make_spy_pool():
    """kis_ws_pool spy — unsubscribe_in_pool / subscribe 호출 순서 + 인자 추적.

    두 AsyncMock 의 side_effect 가 공유 `call_log` 에 append → cross-mock 호출 순서 단언.
    subscribe 는 "main" 반환 (resubscribed.append 정상 동작).
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
# GS-1 (HIGH) — 핵심 회귀: split-brain HIGH 보유 종목 재구독 시
#               unsubscribe_in_pool 이 subscribe(...HIGH...) 보다 먼저 호출
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 10:00:00", tz_offset=-9)
async def test_GS1_split_brain_high_unsubscribe_in_pool_before_subscribe():
    """GS-1 (핵심 Red): HIGH 보유 종목이 split-brain(풀 매핑 잔존, 세션 미구독)일 때
    `resubscribe_stale_priority` 가 `unsubscribe_in_pool(TICK_TR_ID, t)` 를
    `subscribe(...HIGH...)` *앞*에 호출해 실제 재SEND 를 일으켜야 한다.

    실측 001450(donchian) 재현 — 09:05 매수 후 OPSP0008 거부로 세션 `_subscriptions`
    에서 discard 됐으나 풀 `_ticker_to_session["001450"]=main` 잔존. 현재 코드는
    unsubscribe_in_pool 없이 subscribe 만 호출 → dedup 가드(`existing is self._main
    → return "main"`)에 걸려 재SEND 0건 = 손절 사각.

    Red 단계 (현재 코드): unsubscribe_in_pool 미호출 → FAIL.
    Green 단계 (시정 후): unsubscribe_in_pool → sleep(0.05) → subscribe 순서 → PASS.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 12, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers(positions=["001450"])  # HIGH 보유
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"001450": stale_dt}

    pool, call_log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["001450"], f"HIGH 보유 종목 재구독 대상 포함 의무. 실제: {result}"

    # (핵심 Red) unsubscribe_in_pool 이 최소 1회 호출되어야 함 — 현재 코드는 0회 → FAIL
    assert pool.unsubscribe_in_pool.await_count >= 1, (
        "split-brain 재구독은 subscribe *앞*에 unsubscribe_in_pool 로 풀 매핑을 팝해야 "
        "재SEND 가 나간다 (K watcher 342-347 패턴). 현재 코드는 unsubscribe_in_pool "
        "미호출 → dedup 가드에 걸려 재SEND 0건 = 손절 사각."
    )
    # unsubscribe_in_pool 은 (TICK_TR_ID, ticker) 로 호출
    pool.unsubscribe_in_pool.assert_any_await(TICK_TR_ID, "001450")

    # 호출 순서: unsubscribe_in_pool("001450") < subscribe("001450")
    unsub_idx = _order_index(call_log, "unsub", "001450")
    sub_idx = _order_index(call_log, "sub", "001450")
    assert unsub_idx is not None, "unsubscribe_in_pool 호출 기록 부재 (핵심 Red)"
    assert sub_idx is not None, "subscribe 호출 기록 부재"
    assert unsub_idx < sub_idx, (
        f"unsubscribe_in_pool 은 subscribe *앞*이어야 함 (팝→재SEND). "
        f"실제 순서 unsub={unsub_idx} sub={sub_idx} call_log={call_log}"
    )


# ===========================================================================
# GS-2 (HIGH) — 핵심 회귀 (실경로): 실제 WebsocketPool + 가짜 세션으로 재SEND 검증
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 10:00:00", tz_offset=-9)
async def test_GS2_split_brain_high_real_pool_actually_resends():
    """GS-2 (핵심 Red, 실경로): 진짜 `WebsocketPool` + 가짜 메인 세션으로 dedup 가드를
    실제 통과시켜, split-brain HIGH 종목이 재SEND(세션 subscribe 실호출)되는지 검증.

    split-brain 재현:
      - `pool._main = fake` (세션 `_subscriptions` 비어 있음 = 거부 후 discard 상태)
      - `pool._ticker_to_session["001450"] = fake` (풀 매핑 잔존)

    현재 코드: subscribe 직접 호출 → `existing is self._main → return "main"` 조기 반환
              → fake.subscribe 미호출 → `_subscriptions` 여전히 공집합 = 재SEND 0건.
    시정 코드: unsubscribe_in_pool 이 `_ticker_to_session` 팝 → subscribe 가 branch 3
              (HIGH 메인 절대 보장) 진입 → fake.subscribe 실호출 → 재SEND 발생.

    Red 단계 (현재 코드): fake.subscribe 미호출 + `_subscriptions` 공집합 → FAIL.
    Green 단계 (시정 후): fake.subscribe 1회 + `("H0UNCNT0","001450") in _subscriptions` → PASS.
    """
    from src.engine import stale_manager
    from src.realtime.websocket_pool import WebsocketPool

    base = datetime(2026, 8, 12, 10, 0, 0, tzinfo=KST)
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

    # (핵심 Red) 실제 세션 재SEND — 현재 코드는 dedup 가드로 subscribe 미호출 → FAIL
    assert len(fake.subscribe_calls) == 1, (
        "split-brain HIGH 종목은 dedup 가드를 뚫고 세션 subscribe 가 실호출되어야 함. "
        f"현재 코드는 재SEND 0건(손절 사각). 실제 세션 subscribe 호출: {fake.subscribe_calls}"
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


# ===========================================================================
# GS-3 (MEDIUM) — HIGH 절대 보장 불변: 시정 후에도 priority=HIGH + bypass_limit=True
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 10:00:00", tz_offset=-9)
async def test_GS3_high_priority_and_bypass_preserved_after_fix():
    """GS-3 (불변 가드, 사이클 32 R4): HIGH 보유 종목은 시정 후에도 subscribe 가
    `priority="HIGH", bypass_limit=True` 로 호출됨 — 재구독 앞단에 unsubscribe_in_pool
    을 끼워도 HIGH 절대 보장 semantics 는 불변.

    현재/시정 코드 모두 subscribe 인자는 HIGH/True → PASS(불변). 시정이 HIGH 계약을
    훼손하지 않음을 영구 고정한다.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 12, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers(positions=["001450", "053800"])
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"001450": stale_dt, "053800": stale_dt}

    pool, _call_log = _make_spy_pool()

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
# GS-4 (HIGH) — LOW 경로 회귀 0: LOW 후보도 unsubscribe_in_pool 선행 후 재구독
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 10:00:00", tz_offset=-9)
async def test_GS4_low_candidate_also_unsubscribe_in_pool_before_subscribe():
    """GS-4 (LOW 공통 적용, Red): 시정은 HIGH/LOW 공통 — LOW 후보 stale 재구독도
    subscribe 앞에 unsubscribe_in_pool 을 선행해야 한다 (같은 split-brain 병리).

    LOW 후보는 보조 세션 라운드로빈이라 매핑 팝 후 재분배가 오히려 정상 경로 —
    HIGH/LOW 를 갈라 한쪽만 고치면 LOW 후보가 여전히 재SEND 사각으로 남는다.

    Red 단계 (현재 코드): LOW 후보 unsubscribe_in_pool 미호출 → FAIL.
    Green 단계 (시정 후): LOW 후보도 unsubscribe_in_pool → subscribe 순서 → PASS.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 12, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler_with_high_tickers()  # HIGH 0 → 모두 LOW 후보
    stale_dt = base - timedelta(seconds=120)
    low_ticker = "035420"
    ticker_last_tick = {low_ticker: stale_dt}

    pool, call_log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == [low_ticker]

    assert pool.unsubscribe_in_pool.await_count >= 1, (
        "LOW 후보도 subscribe 앞에 unsubscribe_in_pool 선행 의무 (HIGH/LOW 공통 적용). "
        "현재 코드는 미호출 → FAIL."
    )
    unsub_idx = _order_index(call_log, "unsub", low_ticker)
    sub_idx = _order_index(call_log, "sub", low_ticker)
    assert unsub_idx is not None and sub_idx is not None
    assert unsub_idx < sub_idx, (
        f"LOW 후보 unsubscribe_in_pool 은 subscribe *앞*. 실제 call_log={call_log}"
    )
    # LOW subscribe 는 priority=LOW + bypass_limit=False (사이클 25-B 영속)
    low_sub = next(c for c in pool.subscribe.await_args_list if c.args[1] == low_ticker)
    assert low_sub.kwargs.get("priority") == "LOW"
    assert low_sub.kwargs.get("bypass_limit") is False


# ===========================================================================
# GS-5 (LOW) — 부작용 가드: unsubscribe_in_pool 은 pop+세션 unsubscribe 만,
#              subscribe 인자(priority/bypass) 불변
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-08-12 10:00:00", tz_offset=-9)
async def test_GS5_unsubscribe_in_pool_signature_and_subscribe_args_invariant():
    """GS-5 (부작용 가드): unsubscribe_in_pool 은 `(TICK_TR_ID, ticker)` 2 위치인자만 —
    priority/bypass 등 subscribe semantics 를 실어 나르지 않는다. subscribe 인자는
    종목 우선순위대로 불변(HIGH→HIGH/True, LOW→LOW/False).

    Red 단계 (현재 코드): unsubscribe_in_pool 호출 자체가 없어 시그니처 단언 미충족 → FAIL.
    Green 단계 (시정 후): 2 위치인자 + kwargs 없음 + subscribe 인자 불변 → PASS.
    """
    from src.engine import stale_manager

    base = datetime(2026, 8, 12, 10, 0, 0, tzinfo=KST)
    # HIGH 1 (001450) + LOW 1 (035420) 혼재
    sched = _make_scheduler_with_high_tickers(positions=["001450"])
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"001450": stale_dt, "035420": stale_dt}

    pool, _call_log = _make_spy_pool()

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
# GS-6 (MEDIUM) — AST 정적 가드: resubscribe_stale_priority 본체에서
#                 unsubscribe_in_pool 이 subscribe *앞*에 위치
# ===========================================================================
def test_GS6_unsubscribe_in_pool_precedes_subscribe_static_guard():
    """GS-6 (AST 정적 가드): `resubscribe_stale_priority` 본체에 `unsubscribe_in_pool`
    호출이 존재하고, `subscribe(...)` 호출보다 텍스트상 *먼저* 등장한다 (K watcher
    `check_and_resubscribe_stale` 342-347 패턴 이식 영구 검증).

    사이클 67 분해 후 stale_watcher_core.py 가 진실의 원천 (fallback: stale_manager.py) —
    사이클 66 AST 가드 candidate_paths 패턴 답습.

    Red 단계 (현재 코드): 본체에 `unsubscribe_in_pool` 부재 → FAIL.
    Green 단계 (시정 후): 부재 해소 + subscribe 앞 위치 → PASS.
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

    # (핵심 Red) unsubscribe_in_pool 호출 존재 의무 — 현재 코드는 부재 → FAIL
    assert ".unsubscribe_in_pool(" in func_source, (
        "시정 의무: `resubscribe_stale_priority` 재구독 루프에 "
        "`await kis_ws_pool.unsubscribe_in_pool(TICK_TR_ID, ticker)` 추가 "
        "(K watcher 342-347 패턴). 현재 부재 → 재SEND 사각 = 손절 사각."
    )
    # subscribe 는 dedup 가드를 뚫기 위해 unsubscribe_in_pool *뒤*에 위치
    assert func_source.index(".unsubscribe_in_pool(") < func_source.index(".subscribe("), (
        "unsubscribe_in_pool 은 subscribe *앞*(팝→재SEND). K watcher 순서 이식 의무."
    )
    # 사이클 66 priority 분리 *후* cap 로직 병존 검증 (본 시정이 cap 로직 훼손 금지)
    assert "high_targets" in func_source and "low_targets" in func_source, (
        "사이클 66 priority 분리 (`high_targets`/`low_targets`) 병존 의무 — 본 시정과 독립"
    )
