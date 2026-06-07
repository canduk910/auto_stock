"""PR-B (2026-05-14) — NXT 익일 청산 구조화 로그 관찰성.

scheduler 의 `_execute_next_day_clear` / `_drain_pending_next_day_clear` 가
다음 4 케이스의 `[next_day_clear_*]` prefix 로그를 영문/구조화 형식으로 1행씩 발행한다:

A. deferred + reason=nxt_not_tradable  (stock_master 사전 판별로 즉시 보류)
B. deferred + reason=nxt_open_missing  (시가 미수신으로 보류)
C. drained + result=success            (KRX 시장가 청산 성공)
D. drained + result=fail               (청산 시도 중 예외)

Loki 검색용 prefix 행은 한국어 자유 텍스트 로그와 **별도로** 추가됨(기존 사람 로그는 보존).
"""

from __future__ import annotations

from datetime import date, timedelta, timezone, datetime

_KST_TEST = timezone(timedelta(hours=9))  # 사이클 68 hotfix

import pytest

from src.engine.strategy_base import Position, Signal

pytestmark = pytest.mark.integration


def _seed_next_day_pos(strategy, ticker, buy_price=15000, qty=6):
    pos = Position(
        ticker=ticker,
        buy_price=buy_price,
        quantity=qty,
        order_no="ORIG-NEXT",
        strategy_id=strategy.strategy_id,
        buy_date=datetime.now(_KST_TEST).date() - timedelta(days=1),
        high_since_buy=buy_price,
    )
    strategy.state.positions[ticker] = pos
    return pos


@pytest.fixture
def stub_stock_master_get(monkeypatch: pytest.MonkeyPatch):
    def _setup(*, nxt_tradable: bool | None):
        from src.models.stock import StockBasics

        async def _get(_ticker: str):
            if nxt_tradable is None:
                return None
            return StockBasics(
                ticker=_ticker,
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


# ---------------------------------------------------------------------------
# A. nxt_not_tradable — stock_master 사전 차단
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deferred_log_emitted_when_stock_master_blocks(
    scheduler_env,
    stub_stock_master_get,
):
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "012200")

    stub_stock_master_get(nxt_tradable=False)

    await sched._execute_next_day_clear()

    msgs = _messages(scheduler_env.calls)
    deferred = [m for m in msgs if "[next_day_clear_deferred]" in m]
    assert len(deferred) == 1, f"deferred prefix 1행 발행: {msgs}"
    assert "ticker=012200" in deferred[0]
    assert "strategy=momentum" in deferred[0]
    assert "reason=nxt_not_tradable" in deferred[0]


# ---------------------------------------------------------------------------
# B. nxt_open_missing — 시가 미수신으로 보류
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deferred_log_emitted_when_open_price_missing(
    scheduler_env,
    stub_stock_master_get,
    monkeypatch,
):
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "012200")

    # stock_master miss → fallback 분기 진입
    stub_stock_master_get(nxt_tradable=None)

    # 시가 미수신 (ticker_prices 에 open_price 없음)
    # `_resolve_open_price` 도 0 반환하도록 stub
    async def _resolve_zero(_ticker, *, max_wait_s: float = 2.0):
        return 0

    monkeypatch.setattr(sched, "_resolve_open_price", _resolve_zero)

    await sched._execute_next_day_clear()

    msgs = _messages(scheduler_env.calls)
    deferred = [m for m in msgs if "[next_day_clear_deferred]" in m]
    assert len(deferred) == 1, f"deferred prefix 1행 발행: {msgs}"
    assert "ticker=012200" in deferred[0]
    assert "strategy=momentum" in deferred[0]
    assert "reason=nxt_open_missing" in deferred[0]


# ---------------------------------------------------------------------------
# C. drained success — KRX 시장가 청산 성공
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_drained_success_log_emitted_on_clear_success(scheduler_env):
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "012200")

    # 보류 상태 직접 시드
    sched._pending_next_day_clear.add(("012200", "momentum"))

    await sched._drain_pending_next_day_clear()

    msgs = _messages(scheduler_env.calls)
    drained = [m for m in msgs if "[next_day_clear_drained]" in m]
    assert len(drained) == 1, f"drained prefix 1행: {msgs}"
    assert "ticker=012200" in drained[0]
    assert "strategy=momentum" in drained[0]
    assert "result=success" in drained[0]
    assert "elapsed_ms=" in drained[0]
    # 보류 set 비워짐
    assert ("012200", "momentum") not in sched._pending_next_day_clear


# ---------------------------------------------------------------------------
# D. drained fail — 청산 예외
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_drained_fail_log_emitted_on_clear_exception(scheduler_env):
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    momentum.config.enabled = True
    _seed_next_day_pos(momentum, "012200")
    sched._pending_next_day_clear.add(("012200", "momentum"))

    # execute_sell 이 예외 발생하도록 교체
    async def _raise(_ticker, _signal, _strategy_id, *, limit_price: int = 0):
        raise RuntimeError("simulated KIS down")

    sched.order_engine.execute_sell = _raise

    await sched._drain_pending_next_day_clear()

    msgs = _messages(scheduler_env.calls)
    drained = [m for m in msgs if "[next_day_clear_drained]" in m]
    assert len(drained) == 1, f"drained prefix 1행: {msgs}"
    assert "ticker=012200" in drained[0]
    assert "result=fail" in drained[0]
    assert "elapsed_ms=" in drained[0]
    # 보류 set 은 finally 에서 비움 — 다음 사이클 재시도 위임
    assert ("012200", "momentum") not in sched._pending_next_day_clear
