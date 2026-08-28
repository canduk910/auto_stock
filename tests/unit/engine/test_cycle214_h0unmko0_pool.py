"""사이클 214 (2026-07-15) → **cycle221 (2026-08-20) 의미 전환**.

## 원래 계약 (cycle214)

- G-214-1: HIGH(보유+익일청산) = `kis_ws.subscribe(bypass_limit=True)` 메인 직접 **유지**
  (cycle 32 R4 절대보호).
- G-214-2: LOW 후보 = `kis_ws_pool.subscribe(priority="LOW")` 풀 경유.

## 왜 뒤집는가 (cycle221)

08-19 OPSP0008 117건 중 **시세(H0UNCNT0) 7건**이 섞였고 대상 4종목이 전부 매수 직후
보유 종목이었다(095340/005180 각 ~58분 tick blind). 메인은 이미 45/41 = KIS **서버**
한도 초과 상태였고, `[ws_action_summary] label=main tr_id=H0UNMKO0 SUBSCRIBE=10~11`
= main 41 중 ~25% 를 VI 관찰 채널이 선점하고 있었다.

cycle 32 R4 "HIGH 절대 보장"의 원래 대상은 **시세(tick)** 다 — 손절·트레일링·익일청산이
전부 tick 에 매달려 있기 때문이다. H0UNMKO0 는 VI/거래정지 **관찰** 채널이고 소비처는
`is_ticker_stale_excluded` + 서킷브레이커 UI 둘뿐(매수/매도 게이트 미연계). cycle214 는
"보유 종목이니까 HIGH" 라벨만 보고 tick 규칙을 기계적으로 미러했고, 그 결과 관찰 채널이
생명선 채널과 같은 41 슬롯을 놓고 경쟁하게 됐다. → **오적용 판정, 반전.**

풀 경유(G-214-2)도 폐기한다: `websocket_pool._ticker_to_session` 이 `tr_key` 단일 키라
VI 가 경유하면 TICK drop 종목이 quote-N 으로 기록돼 **TICK 이 영구히 안 붙는다**(F-P).

## cycle221 정정 — 후보(LOW) VI 는 **배치하지 않는다** (F2)

바로 그 `tr_key` 단일 키 때문에, `_scan_loop` 가 TICK 을 **먼저** 돌리는 현행 순서에서
기존 `kis_ws_pool.subscribe(H0UNMKO0, 후보, "LOW")` 는 중복 분기에서 SEND 없이 반환됐다
= **후보 VI 는 실질 noop** 이었다. 이를 보조 세션 직접 호출로 "이동"시키면 이동이 아니라
죽어 있던 경로의 **7배 활성화**(보유 10건 → 최대 70건)이고, scanner 의
`remaining = _pool_total_slots - len(pool._subscriptions)` 가 VI 를 합집합으로 세므로
**tick 후보 슬롯이 48~60 줄어든다**(잘리는 tail = VB/LTV, VB 는 REST 폴 보강 0 = 완전 사각).
→ 후보 VI 는 되살리지 않는다. **행위 보존**이다.

## 전환 후 계약

- VI 대상 = **보유 + 익일청산(HIGH) 뿐**. 후보(LOW)는 SEND 0건.
- 전량 **보조 세션 직접 배치**(풀 API 미경유, `bypass_limit` 미사용, 예약 슬롯 **없음**).
- cap 기본값 60 은 **불변**(G-214-4 무수정 통과) — 단 **vestigial** 로 남는다.

행위 상세는 `tests/unit/engine/test_cycle221_market_op_off_main.py` 가 정본.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.market_operation import MARKET_OP_TR_ID
from src.engine.scheduler import TradingScheduler


def _make_scheduler(*, positions: set[str], pending: set[str]):
    """최소 스케줄러 인스턴스 (subscribe 함수만 태우기 위해 __new__ + 필드 주입)."""
    sched = TradingScheduler.__new__(TradingScheduler)

    strat = SimpleNamespace(
        state=SimpleNamespace(positions={t: object() for t in positions})
    )
    registry = MagicMock()
    registry.all.return_value = [strat]

    sched.registry = registry
    sched._pending_next_day_clear = {(t, "some_strategy") for t in pending}
    # cycle221 — `__init__` 이 선언하는 VI 구독 추적 맵 (델타 해제 + 중복 SEND 억제)
    sched._market_op_subs = {}
    return sched


def _make_quote_session(label: str):
    ws = MagicMock()
    ws._label = label
    ws._subscriptions = set()

    async def _sub(tr_id, tr_key, *, bypass_limit=False):
        ws._subscriptions.add((tr_id, tr_key))

    async def _unsub(tr_id, tr_key):
        ws._subscriptions.discard((tr_id, tr_key))

    ws.subscribe = AsyncMock(side_effect=_sub)
    ws.unsubscribe = AsyncMock(side_effect=_unsub)
    return ws


def _patch_ws(monkeypatch, *, main_ws_present: bool = True, quote_count: int = 2):
    """`kis_ws`(메인) + `kis_ws_pool`(보조 세션 보유자) 을 mock 으로 격리.

    cycle221 — 풀은 이제 `subscribe` 경유가 아니라 `_quotes` **읽기** 대상이다.
    """
    from websockets.protocol import State as _State
    fake_ws = MagicMock()
    fake_ws._ws = SimpleNamespace(state=_State.OPEN) if main_ws_present else None
    fake_ws.subscribe = AsyncMock(return_value=None)
    fake_ws._subscriptions = set()
    fake_ws.get_subscribed_tickers = MagicMock(return_value=set())

    fake_pool = MagicMock()
    fake_pool.subscribe = AsyncMock(return_value="quote-1")
    fake_pool.unsubscribe = AsyncMock(return_value=None)
    fake_pool._quotes = [_make_quote_session(f"quote-{i+1}") for i in range(quote_count)]

    monkeypatch.setattr("src.realtime.websocket.kis_ws", fake_ws, raising=False)
    monkeypatch.setattr(
        "src.realtime.websocket_pool.kis_ws_pool", fake_pool, raising=False
    )
    return fake_ws, fake_pool


def _session_calls(fake_pool):
    return [c for q in fake_pool._quotes for c in q.subscribe.await_args_list]


@pytest.mark.asyncio
async def test_low_candidates_are_not_subscribed_at_all(monkeypatch) -> None:
    """[의미 전환 G-214-2] cycle221 정정 — 후보 VI 는 **실질 noop 이었으므로 배치하지 않는다**(F2).

    원래 계약: LOW 후보 = `kis_ws_pool.subscribe(priority="LOW")` 풀 경유.
    중간 계약(폐기): LOW 후보 = 보조 세션 직접 배치.
    **현재 계약: LOW 후보 = 구독 0건.**

    `_ticker_to_session` 이 `tr_key` 단일 키이고 `_scan_loop` 가 TICK 을 먼저 돌리므로
    풀 경유 후보 VI 는 중복 분기에서 SEND 없이 반환됐다 = 애초에 나간 적이 없다.
    직접 호출로 되살리면 최대 70건이 **처음으로 진짜 SEND** 되고 pool `_subscriptions`
    합집합을 통해 tick 후보 슬롯을 48~60 잠식한다(VB/LTV tail 절단 = REST 폴 보강 0).
    """
    fake_ws, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions=set(), pending=set())

    candidates = {"111111", "222222", "333333"}
    n = await sched._subscribe_market_operation_tickers(candidates)

    assert _session_calls(fake_pool) == [], "후보(비HIGH) VI 는 SEND 0건"
    assert n == 0
    assert fake_pool.subscribe.await_count == 0, "풀 API 경유 금지 (라우팅 맵 오염)"
    assert fake_ws.subscribe.await_count == 0, "메인 직접 금지 (tick 슬롯 보호)"


@pytest.mark.asyncio
async def test_high_vi_never_touches_main(monkeypatch) -> None:
    """[의미 전환 G-214-1] HIGH VI 도 메인 미접촉 — cycle 32 R4 오적용 시정.

    R4 의 보호 대상은 tick 이지 VI 관찰 채널이 아니다. 08-19 는 관찰이 경쟁에서
    이겨 생명선이 밀린 사건이다.
    """
    fake_ws, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions={"005930"}, pending={"000660"})

    await sched._subscribe_market_operation_tickers(set())

    assert fake_ws.subscribe.await_count == 0, "HIGH VI 메인 직접 구독 금지"
    calls = _session_calls(fake_pool)
    assert {c.args[1] for c in calls} == {"005930", "000660"}, "HIGH 는 보조 세션에 배치된다"
    for c in calls:
        assert c.args[0] == MARKET_OP_TR_ID
        assert c.kwargs.get("bypass_limit", False) is False


@pytest.mark.asyncio
async def test_only_high_is_placed_candidates_dropped(monkeypatch) -> None:
    """[의미 전환 G-214-1b] cycle221 정정 — 후보 VI 는 실질 noop 이었으므로 배치하지 않는다(F2).

    원래 계약은 "HIGH/LOW 는 세션 구분이 아니라 배치 **순서**" 였다. 후보 배치가 통째로
    사라지면서 순서 개념도 소멸 — 대상 자체가 HIGH 뿐이다. 보유 종목이 후보 집합에
    동시에 들어와도 **정확히 1회**만 SEND 된다(중복 금지 계약 승계).
    """
    fake_ws, fake_pool = _patch_ws(monkeypatch, quote_count=1)
    sched = _make_scheduler(positions={"005930"}, pending=set())

    await sched._subscribe_market_operation_tickers({"005930", "111111"})

    ordered = [c.args[1] for c in _session_calls(fake_pool)]
    assert ordered == ["005930"], "HIGH 만 배치 + 후보 111111 은 SEND 0건"


def test_G_214_4_cap_default_is_60() -> None:
    """G-214-4 (무수정 통과) — cap 기본값 60 불변. 시그니처 계약 보존.

    cycle221 정정 이후 cap 은 **vestigial**(후보 배치가 사라져 아무것도 제한하지 않음)
    이지만, 이 시그니처 가드를 살려두기 위해 파라미터는 **제거하지 않는다**.
    """
    sig = inspect.signature(
        TradingScheduler._subscribe_market_operation_tickers
    )
    assert sig.parameters["cap"].default == 60


@pytest.mark.asyncio
async def test_cap_is_vestigial_no_candidate_placement(monkeypatch) -> None:
    """[의미 전환 G-214-2b] cycle221 정정 — 후보 VI 는 실질 noop 이었으므로 배치하지 않는다(F2).

    원래 계약: cap=60 이 80개 후보를 60개로 절단해 60건 SEND.
    현재 계약: 후보는 cap 과 무관하게 **0건**. cap 은 시그니처에만 남은 vestigial 이다.
    """
    fake_ws, fake_pool = _patch_ws(monkeypatch, quote_count=4)
    sched = _make_scheduler(positions=set(), pending=set())

    candidates = {f"{i:06d}" for i in range(80)}
    n = await sched._subscribe_market_operation_tickers(candidates, cap=60)

    assert _session_calls(fake_pool) == [], "cap 값과 무관하게 후보 VI SEND 0건"
    assert n == 0
