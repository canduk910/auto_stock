"""PR-D (2026-05-14) — strategy_funnel cross-check against trade_history.

2026-05-14 운영 사고: LTV 매수 1건 정상 체결됐으나 EC2 4회 재시작으로
state.signal_count_today/order_attempt_today/fill_count_today in-memory
카운터가 휘발 → 20:10 log_analysis 시점 funnel=모두 0 으로 기록됨.

수정: `_collect_strategy_funnel()` 이 trade_history 당일 KST BUY 행으로
cross-check.
- fills = max(in_memory, COMPLETED count)
- orders = max(in_memory, all-status count: PENDING+COMPLETED+PARTIAL+CANCELLED)
- signals = max(in_memory, orders)   # 단조성 signals ≥ orders ≥ fills

핫패스 무관. 분석 경로(20:10)만 수정. _reset_daily_state 순서 변경 없음.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.engine import log_analysis_engine as lae

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures — minimal scheduler/registry/state stub
# ---------------------------------------------------------------------------
@dataclass
class _FakeState:
    signal_count_today: int = 0
    order_attempt_today: int = 0
    fill_count_today: int = 0


@dataclass
class _FakeStrategy:
    strategy_id: str
    state: _FakeState = field(default_factory=_FakeState)


class _FakeRegistry:
    def __init__(self, strategies: list[_FakeStrategy]):
        self._strategies = strategies

    def all(self) -> list[_FakeStrategy]:
        return list(self._strategies)


class _FakeScheduler:
    def __init__(self, strategies: list[_FakeStrategy]):
        self.registry = _FakeRegistry(strategies)


def _install_scheduler(monkeypatch, strategies: list[_FakeStrategy]) -> _FakeScheduler:
    """src.engine.scheduler.trading_scheduler 를 stub 으로 교체.

    _collect_strategy_funnel 은 `from src.engine.scheduler import trading_scheduler`
    를 함수 내부에서 import 하므로 module attr 만 갈아끼우면 충분.
    """
    sched = _FakeScheduler(strategies)
    from src.engine import scheduler as real_sched

    monkeypatch.setattr(real_sched, "trading_scheduler", sched, raising=True)
    return sched


def _trade(ticker: str, strategy: str, status: str, trade_type: str = "BUY") -> dict:
    """trade_history row 의 최소 키만 포함."""
    return {
        "ticker": ticker,
        "strategy": strategy,
        "status": status,
        "trade_type": trade_type,
        "timestamp": "2026-05-14T09:00:19+09:00",
    }


# ---------------------------------------------------------------------------
# 1. async signature
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_funnel_async_callable(monkeypatch):
    """`_collect_strategy_funnel` 가 awaitable (async def) 인지 검증."""
    import inspect

    assert inspect.iscoroutinefunction(lae._collect_strategy_funnel), (
        "PR-D: _collect_strategy_funnel 는 async def 여야 한다"
    )

    # 실제 호출도 정상 (registry 비어있어도 빈 dict)
    _install_scheduler(monkeypatch, [])

    async def _empty(*_a, **_kw):
        return []

    monkeypatch.setattr(lae, "get_today_buy_trades", _empty, raising=False)
    result = await lae._collect_strategy_funnel()
    assert result == {}


# ---------------------------------------------------------------------------
# 2. in-memory 우선 — 재시작 없이 정상 수집된 케이스
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_funnel_uses_in_memory_when_higher(monkeypatch):
    """in-memory 값이 DB 보다 크면 in-memory 사용."""
    strat = _FakeStrategy(
        strategy_id="momentum",
        state=_FakeState(signal_count_today=5, order_attempt_today=3, fill_count_today=2),
    )
    _install_scheduler(monkeypatch, [strat])

    # DB 에는 momentum 1건만 — in-memory 가 더 큼
    async def _trades(*_a, **_kw):
        return [_trade("005930", "momentum", "COMPLETED")]

    monkeypatch.setattr(lae, "get_today_buy_trades", _trades, raising=False)

    funnel = await lae._collect_strategy_funnel()
    assert funnel["momentum"] == {"signals": 5, "orders": 3, "fills": 2}


# ---------------------------------------------------------------------------
# 3. DB 보강 — EC2 재시작 시나리오 (in-memory=0, DB 거래 1건)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_funnel_uses_db_when_in_memory_zero(monkeypatch):
    """2026-05-14 LTV 사고 재현 — in-memory 휘발 + DB BUY COMPLETED 1건."""
    strat = _FakeStrategy(
        strategy_id="long_tail_volatility",
        state=_FakeState(),  # 모두 0 — 재시작 후 상태
    )
    _install_scheduler(monkeypatch, [strat])

    async def _trades(*_a, **_kw):
        return [_trade("066570", "long_tail_volatility", "COMPLETED")]

    monkeypatch.setattr(lae, "get_today_buy_trades", _trades, raising=False)

    funnel = await lae._collect_strategy_funnel()
    # DB 보강: fills=1, orders=1, signals≥orders=1
    assert funnel["long_tail_volatility"]["fills"] == 1
    assert funnel["long_tail_volatility"]["orders"] == 1
    assert funnel["long_tail_volatility"]["signals"] >= 1


# ---------------------------------------------------------------------------
# 4. PENDING 은 orders 에만 — fills 에 미포함
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_funnel_handles_pending_in_orders_not_fills(monkeypatch):
    """PENDING/CANCELLED/PARTIAL 모두 orders 에 포함, COMPLETED 만 fills."""
    strat = _FakeStrategy(strategy_id="volatility_breakout", state=_FakeState())
    _install_scheduler(monkeypatch, [strat])

    async def _trades(*_a, **_kw):
        return [
            _trade("000001", "volatility_breakout", "PENDING"),
            _trade("000002", "volatility_breakout", "COMPLETED"),
            _trade("000003", "volatility_breakout", "CANCELLED"),
            _trade("000004", "volatility_breakout", "PARTIAL"),
        ]

    monkeypatch.setattr(lae, "get_today_buy_trades", _trades, raising=False)

    funnel = await lae._collect_strategy_funnel()
    assert funnel["volatility_breakout"]["orders"] == 4  # 모든 상태
    assert funnel["volatility_breakout"]["fills"] == 1   # COMPLETED 만
    assert funnel["volatility_breakout"]["signals"] >= 4  # signals ≥ orders


# ---------------------------------------------------------------------------
# 5. signal 단조성 — signals ≥ orders 보장
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_funnel_signal_monotonic_ge_orders(monkeypatch):
    """signals < orders 시나리오에서도 funnel.signals 가 orders 이상."""
    # in-memory signals=1 인데 DB orders 3 → signals 최소 3
    strat = _FakeStrategy(
        strategy_id="momentum",
        state=_FakeState(signal_count_today=1, order_attempt_today=0, fill_count_today=0),
    )
    _install_scheduler(monkeypatch, [strat])

    async def _trades(*_a, **_kw):
        return [
            _trade("000001", "momentum", "COMPLETED"),
            _trade("000002", "momentum", "COMPLETED"),
            _trade("000003", "momentum", "PENDING"),
        ]

    monkeypatch.setattr(lae, "get_today_buy_trades", _trades, raising=False)

    funnel = await lae._collect_strategy_funnel()
    assert funnel["momentum"]["orders"] == 3
    assert funnel["momentum"]["signals"] >= 3, (
        "signals 는 orders 이상이어야 한다 (단조성)"
    )


# ---------------------------------------------------------------------------
# 6. strategy NULL/unknown 은 funnel 안 깨고 무시
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_funnel_unknown_strategy_skipped_or_grouped(monkeypatch):
    """trade_history.strategy 가 NULL 또는 등록 안 된 전략이면 funnel 영향 없음."""
    strat = _FakeStrategy(strategy_id="momentum", state=_FakeState())
    _install_scheduler(monkeypatch, [strat])

    async def _trades(*_a, **_kw):
        return [
            _trade("000001", "momentum", "COMPLETED"),
            {"ticker": "000002", "strategy": None, "status": "COMPLETED", "trade_type": "BUY"},
            _trade("000003", "ghost_strategy", "COMPLETED"),
        ]

    monkeypatch.setattr(lae, "get_today_buy_trades", _trades, raising=False)

    funnel = await lae._collect_strategy_funnel()
    # momentum 만 등록 → momentum=1, ghost/null 은 funnel 키로 노출 안 됨
    assert funnel["momentum"]["fills"] == 1
    assert "ghost_strategy" not in funnel
    assert None not in funnel


# ---------------------------------------------------------------------------
# 7. DB 조회 실패 → in-memory fallback
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_funnel_db_failure_falls_back_to_in_memory(monkeypatch):
    """get_today_buy_trades 가 raise 해도 in-memory 카운터로 funnel 산출."""
    strat = _FakeStrategy(
        strategy_id="donchian_swing",
        state=_FakeState(signal_count_today=2, order_attempt_today=1, fill_count_today=1),
    )
    _install_scheduler(monkeypatch, [strat])

    async def _raise(*_a, **_kw):
        raise RuntimeError("supabase connection lost")

    monkeypatch.setattr(lae, "get_today_buy_trades", _raise, raising=False)

    funnel = await lae._collect_strategy_funnel()
    assert funnel["donchian_swing"] == {"signals": 2, "orders": 1, "fills": 1}


# ---------------------------------------------------------------------------
# 8. 여러 전략 동시 — 각 전략 격리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_funnel_multiple_strategies_isolated(monkeypatch):
    """전략별 카운트가 서로 섞이지 않는다."""
    strategies = [
        _FakeStrategy("momentum", _FakeState(signal_count_today=10, order_attempt_today=5, fill_count_today=2)),
        _FakeStrategy("long_tail_volatility", _FakeState()),  # 재시작 휘발
        _FakeStrategy("volatility_breakout", _FakeState()),
        _FakeStrategy("donchian_swing", _FakeState()),
    ]
    _install_scheduler(monkeypatch, strategies)

    async def _trades(*_a, **_kw):
        return [
            _trade("066570", "long_tail_volatility", "COMPLETED"),
            _trade("005930", "momentum", "COMPLETED"),  # in-memory 가 더 큼
        ]

    monkeypatch.setattr(lae, "get_today_buy_trades", _trades, raising=False)

    funnel = await lae._collect_strategy_funnel()
    # momentum: in-memory 우선
    assert funnel["momentum"]["signals"] == 10
    assert funnel["momentum"]["fills"] == 2
    # LTV: DB 보강
    assert funnel["long_tail_volatility"]["fills"] == 1
    assert funnel["long_tail_volatility"]["orders"] == 1
    # 거래 없는 전략은 모두 0
    assert funnel["volatility_breakout"] == {"signals": 0, "orders": 0, "fills": 0}
    assert funnel["donchian_swing"] == {"signals": 0, "orders": 0, "fills": 0}


# ---------------------------------------------------------------------------
# 9. generate_daily_log_report 와의 통합 — async funnel 호출 회귀
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_daily_log_report_awaits_funnel(monkeypatch):
    """호출자 generate_daily_log_report 가 await 로 funnel 수집 (sync 호출 결함 회귀)."""
    captured: dict = {}

    async def _fake_fetch_logs(*_a, **_kw):
        return []

    async def _fake_trades(*_a, **_kw):
        return []

    async def _fake_call(metrics):
        captured["metrics"] = metrics
        return {"summary": "ok", "findings": []}

    async def _fake_insert(*_a, **_kw):
        return {"id": "row-x"}

    monkeypatch.setattr(lae, "_fetch_logs_in_range", _fake_fetch_logs)
    monkeypatch.setattr(lae, "get_trades_in_range", _fake_trades)
    monkeypatch.setattr(lae, "_call_openai", _fake_call)
    monkeypatch.setattr(lae, "insert_log_report", _fake_insert)
    monkeypatch.setattr(lae.settings, "openai_api_key", "dummy")

    strat = _FakeStrategy(
        strategy_id="long_tail_volatility",
        state=_FakeState(),
    )
    _install_scheduler(monkeypatch, [strat])

    # log_analysis 가 사용하는 get_today_buy_trades 보강용 — 모듈 attr 로 추가
    async def _today_buys(*_a, **_kw):
        return [_trade("066570", "long_tail_volatility", "COMPLETED")]

    monkeypatch.setattr(lae, "get_today_buy_trades", _today_buys, raising=False)

    row = await lae.generate_daily_log_report()
    assert row == {"id": "row-x"}

    metrics = captured["metrics"]
    assert "strategy_funnel" in metrics
    assert metrics["strategy_funnel"]["long_tail_volatility"]["fills"] == 1
