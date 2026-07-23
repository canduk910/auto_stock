"""Red 테스트 — NXT 프리 익일청산 지정가 미체결 → stale `_selling` 방치 시정.

근거 자문/스펙:
- `_workspace/domain_consult/nxt_prelimit_stale_selling_orderflow.md` (2026-07-21)
- 구현 스펙 `nxt_prelimit_fix_spec.md` (사용자 확정: Tier 1 + 공통 재대조 훅)

결함 재확인:
- Defect 1: 갭<임계 NXT 지정가 분기가 `_pending_next_day_clear` 미등록 → 09:00 KRX 드레인 폴백 부재.
- Defect 2 (HIGH): NXT 지정가 미체결 만료는 `order_engine._selling` 의 어느 discard 경로에도 안
  걸림 → `_selling` 영구 잔존 → `risk.py:128 if ticker in _selling: continue` 가 on_tick 의
  check_exit_signal(손절/트레일링)을 종일 억제.

이 파일은 아직 구현되지 않은 시정(변경 1 Tier 1 + 변경 2 공통 재대조)에 대한 **실패(Red)**
테스트다. 소스 구현 전이므로 모든 신규 테스트는 "의도한 assertion 미충족" 으로 실패해야 한다.

Red↔Green 매핑 (스펙 §"Red 테스트 요구"):
- T1-a  test_T1a_gap_below_threshold_defers_instead_of_limit_sell
- T2-a  test_T2a_underthreshold_deferred_then_drained_as_market
- T3-a  test_T3a_stale_selling_reconciled_and_discarded            (양성)
- T3-b  test_T3b_open_sell_order_keeps_selling                     (음성: 열린주문)
- T3-c  test_T3c_not_held_keeps_selling                            (음성: 미보유)
- T3-d  test_T3d_fresh_selling_kept_within_age_gate                (음성: fresh, freezegun)
- T3-e  test_T3e_after_reconcile_next_on_tick_reevaluates_exit     (통합: Defect 2 실효 회복)
- T4-a  test_T4a_reset_daily_clears_selling_since

T1-b(회귀 트레일링 분기 불변) / T1-c(회귀 nxt_not_tradable·nxt_open_missing 분기 불변) 은
기존 회귀 테스트가 이미 커버 →
  * 트레일링 불변: tests/integration/test_next_day_clear.py
      ::test_next_day_clear_when_gap_above_threshold_then_trailing_mode_no_sell
  * nxt_not_tradable/open_missing 불변: tests/integration/test_next_day_clear_stock_master.py
      + test_next_day_clear_observability.py (A/B 케이스)
Green 구현 시 이 신규 파일과 함께 초록 유지 여부를 backend-dev/tester 가 확인한다.

⚠️ 의미 전환 예고 (backend-dev): Tier 1 은 갭<임계 즉시 지정가 청산을 제거하므로,
기존에 "즉시 청산(execute_sell)" 을 단언하던 아래 두 테스트는 Green 구현 시 함께 갱신되어야 한다.
  - tests/integration/test_next_day_clear.py::test_next_day_clear_when_gap_below_threshold_then_immediate_clear
  - tests/integration/test_next_day_clear_stock_master.py::test_next_day_clear_uses_existing_path_when_stock_master_says_tradable
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.engine import scanner
from src.engine.strategy_base import Position, Signal
from src.models.balance import StockHolding

pytestmark = pytest.mark.integration

_KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _seed_next_day_pos(strategy, ticker, buy_price=80000, qty=10):
    """전일 매수(is_next_day=True) 포지션 시드 — `_execute_next_day_clear` 대상."""
    pos = Position(
        ticker=ticker,
        buy_price=buy_price,
        quantity=qty,
        order_no="ORIG-NEXT",
        strategy_id=strategy.strategy_id,
        buy_date=datetime.now(_KST).date() - timedelta(days=1),
        high_since_buy=buy_price,
    )
    strategy.state.positions[ticker] = pos
    return pos


def _seed_today_pos(strategy, ticker, buy_price=100000, qty=10):
    """당일 매수(is_next_day=False) 포지션 시드 — on_tick 손절 재평가 검증용."""
    pos = Position(
        ticker=ticker,
        buy_price=buy_price,
        quantity=qty,
        order_no="ORIG-TODAY",
        strategy_id=strategy.strategy_id,
        buy_date=datetime.now(_KST).date(),
        high_since_buy=buy_price,
    )
    strategy.state.positions[ticker] = pos
    return pos


def _holding(ticker, qty, avg_price=100000) -> StockHolding:
    return StockHolding(
        ticker=ticker,
        name="",
        quantity=qty,
        sellable_quantity=qty,
        avg_price=float(avg_price),
        purchase_amount=int(avg_price) * qty,
        current_price=int(avg_price),
        eval_amount=int(avg_price) * qty,
        eval_profit_loss=0,
        eval_profit_rate=0.0,
    )


def _stub_sync_deps(monkeypatch, *, holdings, daily_orders) -> AsyncMock:
    """`_sync_positions_from_balance` 외부 의존성 스텁.

    - `get_balance` (scheduler 모듈 전역) → (holdings, None)
    - `get_daily_orders` (재대조 훅이 `from src.api.balance import get_daily_orders` 로 사용
      또는 scheduler 모듈 전역 재사용 — 양쪽 patch) → daily_orders. **spy 반환** (호출 여부 검증용).
    - `mark_pending_buys_completed` / `get_recent_buy_strategy` (trade_history) → no-op AsyncMock.
    """

    async def _get_balance(*_a, **_k):
        return (holdings, None)

    gdo_spy = AsyncMock(return_value=daily_orders)

    monkeypatch.setattr("src.engine.scheduler.get_balance", _get_balance)
    monkeypatch.setattr("src.api.balance.get_daily_orders", gdo_spy)
    monkeypatch.setattr("src.engine.scheduler.get_daily_orders", gdo_spy, raising=False)
    monkeypatch.setattr(
        "src.db.trade_history.mark_pending_buys_completed", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        "src.db.trade_history.get_recent_buy_strategy", AsyncMock(return_value="momentum")
    )
    return gdo_spy


@pytest.fixture
def stub_stock_master_get(monkeypatch: pytest.MonkeyPatch):
    """`src.db.stock_master.get` 을 nxt_tradable 분기로 stub (기존 익일청산 테스트 패턴)."""

    def _setup(*, nxt_tradable: bool | None):
        from src.models.stock import StockBasics

        async def _get(ticker: str):
            if nxt_tradable is None:
                return None
            return StockBasics(
                ticker=ticker,
                name="",
                excg_dvsn_cd="02",
                nxt_tradable=nxt_tradable,
                krx_halted=False,
                admin_item=False,
                raw={},
            )

        import src.db.stock_master as _sm

        monkeypatch.setattr(_sm, "get", _get)
        return _get

    return _setup


def _messages(calls) -> list[str]:
    return [c["message"] for c in calls.write_log]


# ===========================================================================
# T1 — Tier 1 (변경 1): 갭<임계 → NXT 지정가 조기청산 제거, 09:00 KRX 드레인 예약
# ===========================================================================
@pytest.mark.asyncio
async def test_T1a_gap_below_threshold_defers_instead_of_limit_sell(
    scheduler_env, stub_stock_master_get, monkeypatch
):
    """T1-a: 갭 < gap_up_threshold(10%) → execute_sell(지정가) 호출 0건 + 보류 등록.

    Tier 1 은 08:00 NXT 프리 지정가를 아예 내지 않고 `_pending_next_day_clear` 로 보류
    (09:00 KRX 시장가 청산 예약) + `save_pending_ndc(reason="nxt_underthreshold")` +
    `[next_day_clear_deferred] ... reason=nxt_underthreshold` 구조화 로그.

    현재(구현 전): else 분기가 `step_down` 지정가로 `execute_sell(..., limit_price>0)` 즉시 호출
    → 아래 4 단언 모두 미충족 → Red.
    """
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "005930", buy_price=80000)

    # 시가 84,000 = 갭 +5% (< 10% 임계)
    scanner.ticker_prices["005930"] = {"open_price": 84000, "current_price": 84000}
    stub_stock_master_get(nxt_tradable=True)

    save_spy = AsyncMock()
    monkeypatch.setattr("src.db.pending_next_day_clear.save_pending_ndc", save_spy)

    await sched._execute_next_day_clear()

    # (1) NXT 지정가 조기청산 제거 — execute_sell 호출 0건
    assert scheduler_env.calls.execute_sell == [], (
        "갭<임계 분기가 여전히 지정가 execute_sell 을 호출함 (Tier 1 미적용). "
        f"실제 호출: {scheduler_env.calls.execute_sell}"
    )
    # (2) 09:00 KRX 드레인 예약 — 보류 set 등록
    assert ("005930", "momentum") in sched._pending_next_day_clear, (
        "갭<임계 종목이 `_pending_next_day_clear` 에 등록되지 않음 (Defect 1 미해소)."
    )
    # (3) DB 영속 — reason=nxt_underthreshold
    reasons: list = []
    for c in save_spy.await_args_list:
        reasons.extend(c.args)
        reasons.append(c.kwargs.get("reason"))
    assert "nxt_underthreshold" in reasons, (
        "save_pending_ndc 가 reason='nxt_underthreshold' 로 호출되지 않음. "
        f"실제 호출 인자: {[(c.args, c.kwargs) for c in save_spy.await_args_list]}"
    )
    # (4) 구조화 로그
    deferred = [
        m for m in _messages(scheduler_env.calls)
        if "[next_day_clear_deferred]" in m and "reason=nxt_underthreshold" in m
    ]
    assert len(deferred) >= 1, (
        "[next_day_clear_deferred] reason=nxt_underthreshold 구조화 로그 미발행. "
        f"messages={_messages(scheduler_env.calls)}"
    )


# ===========================================================================
# T2 — 드레인: nxt_underthreshold 보류가 09:00 KRX 시장가(지정가 없음)로 청산
# ===========================================================================
@pytest.mark.asyncio
async def test_T2a_underthreshold_deferred_then_drained_as_market(
    scheduler_env, stub_stock_master_get, monkeypatch
):
    """T2-a: 갭<임계 보류(T1-a) → `_drain_pending_next_day_clear` 가 KRX 시장가로 청산.

    검증: `_execute_next_day_clear` → `_drain` 순차 실행 결과 execute_sell 이 **정확히 1회**,
    **limit_price 없음(시장가=0)** + `[next_day_clear_drained] result=success` 로그.

    현재(구현 전): `_execute_next_day_clear` 가 즉시 지정가(limit_price>0) 매도 → 보류 미등록 →
    드레인 no-op. 최종 execute_sell 1건이지만 limit_price>0 (지정가) → 시장가 단언 미충족 +
    drained 로그 부재 → Red.
    """
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "005930", buy_price=80000)

    scanner.ticker_prices["005930"] = {"open_price": 84000, "current_price": 84000}  # +5%
    stub_stock_master_get(nxt_tradable=True)

    monkeypatch.setattr("src.db.pending_next_day_clear.save_pending_ndc", AsyncMock())
    monkeypatch.setattr("src.db.pending_next_day_clear.delete_pending_ndc", AsyncMock())

    await sched._execute_next_day_clear()
    await sched._drain_pending_next_day_clear()

    sells = scheduler_env.calls.execute_sell
    assert len(sells) == 1, f"청산 경로는 단일 경로여야 함 (드레인 1회). 실제: {sells}"
    assert sells[0]["ticker"] == "005930"
    assert sells[0]["signal"] == Signal.NEXT_DAY_CLEAR
    assert sells[0]["limit_price"] == 0, (
        "드레인 청산이 시장가(limit_price=0)여야 하는데 지정가로 나감 → "
        "08:00 지정가 조기청산이 아직 제거되지 않음 (Tier 1 미적용)."
    )
    drained = [
        m for m in _messages(scheduler_env.calls)
        if "[next_day_clear_drained]" in m and "result=success" in m
    ]
    assert len(drained) >= 1, (
        "[next_day_clear_drained] result=success 로그 미발행 — 드레인이 실행되지 않음."
    )


# ===========================================================================
# T3 — 공통 재대조 (변경 2c): stale `_selling` 재대조 (`_sync_positions_from_balance`)
# ===========================================================================
@pytest.mark.asyncio
async def test_T3a_stale_selling_reconciled_and_discarded(scheduler_env, monkeypatch):
    """T3-a (양성): 보유 잔존 + 열린 매도주문 없음 + aged(>180s) → `_selling.discard`.

    현재(구현 전): `_sync_positions_from_balance` 에 재대조 훅 부재 → get_daily_orders 미호출 +
    `_selling` 잔존 → Red.
    """
    sched = scheduler_env.scheduler
    tk = "005930"
    _seed_today_pos(sched.registry.get("momentum"), tk, buy_price=100000)  # 잔고 보유 매핑
    sched.order_engine._selling.add(tk)
    # 진입 시각 180s 초과 (aged)
    sched.order_engine._selling_since = {tk: datetime.now(_KST) - timedelta(seconds=300)}

    gdo = _stub_sync_deps(
        monkeypatch, holdings=[_holding(tk, 10, 100000)], daily_orders=[]  # 열린 매도주문 없음
    )

    await sched._sync_positions_from_balance()

    assert gdo.await_count >= 1, (
        "재대조 훅이 실행되지 않음 — `_sync_positions_from_balance` 가 get_daily_orders 를 "
        "조회하지 않았다 (공통 방어선 미구현)."
    )
    assert tk not in sched.order_engine._selling, (
        "stale `_selling` 이 해제되지 않음 → risk.on_tick 손절/트레일링 종일 억제 (Defect 2 잔존)."
    )
    assert any("[selling_reconcile]" in m for m in _messages(scheduler_env.calls)), (
        "[selling_reconcile] 해제 로그 미발행."
    )


@pytest.mark.asyncio
async def test_T3b_open_sell_order_keeps_selling(scheduler_env, monkeypatch):
    """T3-b (음성): 열린 매도주문(01/rmn>0) 존재 → `_selling` 유지 (double-sell 방지).

    현재(구현 전): 재대조 훅 부재 → get_daily_orders 미호출 → Red (훅 실행 자체를 단언).
    구현 후: 훅이 열린 주문을 확인하고 `_selling` 을 유지 → Green.
    """
    sched = scheduler_env.scheduler
    tk = "005930"
    _seed_today_pos(sched.registry.get("momentum"), tk, buy_price=100000)
    sched.order_engine._selling.add(tk)
    sched.order_engine._selling_since = {tk: datetime.now(_KST) - timedelta(seconds=300)}

    gdo = _stub_sync_deps(
        monkeypatch,
        holdings=[_holding(tk, 10, 100000)],
        daily_orders=[{"pdno": tk, "sll_buy_dvsn_cd": "01", "rmn_qty": "5"}],  # 살아있는 매도주문
    )

    await sched._sync_positions_from_balance()

    assert gdo.await_count >= 1, (
        "재대조 훅 미실행 — get_daily_orders 로 열린 매도주문을 조회해야 한다."
    )
    assert tk in sched.order_engine._selling, (
        "열린 매도주문이 존재하는데 `_selling` 을 해제하면 이중매도(double-sell) 위험."
    )


@pytest.mark.asyncio
async def test_T3c_not_held_keeps_selling(scheduler_env, monkeypatch):
    """T3-c (음성): 잔고 미보유 → `_selling` 유지 (정상 매도 완료/진행 가능성).

    현재(구현 전): 재대조 훅 부재 → get_daily_orders 미호출 → Red.
    """
    sched = scheduler_env.scheduler
    tk = "005930"
    sched.order_engine._selling.add(tk)
    sched.order_engine._selling_since = {tk: datetime.now(_KST) - timedelta(seconds=300)}

    gdo = _stub_sync_deps(monkeypatch, holdings=[], daily_orders=[])  # 잔고 미보유

    await sched._sync_positions_from_balance()

    assert gdo.await_count >= 1, "재대조 훅 미실행 (get_daily_orders 미호출)."
    assert tk in sched.order_engine._selling, (
        "잔고 미보유(이미 팔렸을 가능성)면 `_selling` 을 건드리지 않아야 한다."
    )


@pytest.mark.asyncio
async def test_T3d_fresh_selling_kept_within_age_gate(scheduler_env, monkeypatch):
    """T3-d (음성: fresh): `_selling_since` 가 180s 이내 → 유지 (KIS 전파지연 레이스 방지).

    freezegun 으로 시각을 동결해 age = 179s (< 180s 경계)로 제어.
    현재(구현 전): 재대조 훅 부재 → get_daily_orders 미호출 → Red.
    구현 후: 훅이 age gate 로 fresh 판정 → `_selling` 유지 → Green.
    """
    sched = scheduler_env.scheduler
    tk = "005930"

    with freeze_time("2026-07-23 06:00:00"):
        frozen_now = datetime.now(scanner.KST_TZ)
        _seed_today_pos(sched.registry.get("momentum"), tk, buy_price=100000)
        sched.order_engine._selling.add(tk)
        # 진입 179초 전 = age 179s < SELLING_RECONCILE_MIN_AGE_S(180)
        sched.order_engine._selling_since = {tk: frozen_now - timedelta(seconds=179)}

        gdo = _stub_sync_deps(
            monkeypatch, holdings=[_holding(tk, 10, 100000)], daily_orders=[]
        )

        await sched._sync_positions_from_balance()

    assert gdo.await_count >= 1, "재대조 훅 미실행 (get_daily_orders 미호출)."
    assert tk in sched.order_engine._selling, (
        "갓 접수된 매도(age<180s)는 KIS 전파 지연 레이스 방지를 위해 `_selling` 유지."
    )


@pytest.mark.asyncio
async def test_T3e_after_reconcile_next_on_tick_reevaluates_exit(scheduler_env, monkeypatch):
    """T3-e (통합): 재대조 discard 후 다음 on_tick 이 손절 신호를 재평가 (Defect 2 실효 회복).

    시나리오: momentum 당일 보유 100,000원, `_selling={tk}` stale(aged). 재대조가 discard 하면
    risk.py:128 게이트(`if ticker in _selling: continue`)를 통과 → -10% 틱에서 STOP_LOSS →
    execute_sell 발화.

    현재(구현 전): 재대조 미실행 → `_selling` 잔존 → on_tick 이 check_exit_signal 을 skip →
    execute_sell 미호출 → Red.
    """
    sched = scheduler_env.scheduler
    tk = "005930"
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_today_pos(momentum, tk, buy_price=100000)
    sched.order_engine._selling.add(tk)
    sched.order_engine._selling_since = {tk: datetime.now(_KST) - timedelta(seconds=300)}

    _stub_sync_deps(monkeypatch, holdings=[_holding(tk, 10, 100000)], daily_orders=[])

    # 1) 재대조: stale `_selling` 해제 기대
    await sched._sync_positions_from_balance()

    # 2) 다음 틱 -10% (< momentum stop_loss_rate=-7.5%) → STOP_LOSS 재평가 기대
    await sched.risk_manager.on_tick(tk, current_price=90000, open_price=100000, change_rate=-10.0)

    sells = scheduler_env.calls.execute_sell
    assert any(c["ticker"] == tk and c["signal"] == Signal.STOP_LOSS for c in sells), (
        "재대조 후에도 on_tick 이 손절을 발화하지 못함 → stale `_selling` 이 손절을 종일 억제 "
        f"(Defect 2 실효 미회복). execute_sell 기록: {sells}"
    )


# ===========================================================================
# T4 — 리셋 회귀 (변경 2b): `_reset_daily_state` 가 `_selling_since` 동행 clear
# ===========================================================================
def test_T4a_reset_daily_clears_selling_since(scheduler_env):
    """T4-a: `_reset_daily_state` 후 `_selling` 뿐 아니라 `_selling_since` 도 clear.

    현재(구현 전): `_reset_daily_state` 는 `_selling.clear()` 만 하고 `_selling_since` 는 손대지
    않음 → 시드한 timestamp 잔존 → Red.
    """
    sched = scheduler_env.scheduler
    sched.order_engine._selling.add("005930")
    sched.order_engine._selling_since = {"005930": datetime.now(_KST)}

    sched._reset_daily_state()

    # 기존 계약 — `_selling` clear (회귀 확인)
    assert sched.order_engine._selling == set()
    # 신규 — `_selling_since` 동행 clear
    assert sched.order_engine._selling_since == {}, (
        "`_reset_daily_state` 가 `_selling_since` 를 clear 하지 않아 orphan timestamp 가 "
        "다음 영업일까지 잔류 (사이클 간 age 오판 위험)."
    )
