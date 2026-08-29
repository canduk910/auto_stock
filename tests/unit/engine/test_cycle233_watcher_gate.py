"""cycle233 M4·M5·M6 — 감시자 순간 게이트 + 전략 배선 (R5·R6·R7).

핵심 계약 (자문 §2.5-γ + D1·D2 사용자 결정):
- Σ상한 = **순간 게이트** — 감시자가 평가마다 재계산. `buy_disabled` **절대 미접촉**
  (D1 이원화 — risk.py 일일손실 세팅을 지우는 회귀를 구조적으로 차단).
- 실패 = **fail-open**: 게이트 False + `[account_risk_watch_failed]` WARNING (LOUD).
  조용히 닫히는 구현은 "도입 이전 무음과 구별 불가"라 최악의 결함 (D2).
- 다크런치: block 임계 DB 부재(None) → 게이트 항상 False.
- 전략 배선: gate True → `check_buy_signal` 즉시 NONE (AST 가드가 7전략 전수 강제,
  본 파일은 대표 3전략 실호출).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from src.engine import account_risk_watcher as watcher
from src.engine.strategy_base import Signal, StrategyConfig


def _fake_scheduler(strategies, *, buy_disabled=False):
    for s in strategies:
        if not hasattr(s.state, "buy_disabled"):
            s.state.buy_disabled = buy_disabled
    return SimpleNamespace(registry=SimpleNamespace(all=lambda: list(strategies)))


def _fake_strat(sid, positions, *, hard_stop=-8.0, stop_of=None):
    s = SimpleNamespace(
        strategy_id=sid,
        config=SimpleNamespace(params={"hard_stop_pct": hard_stop}),
        state=SimpleNamespace(positions=positions, total_investment=0,
                              buy_disabled=False),
    )
    if stop_of is not None:
        s.get_effective_stop_price = stop_of
    return s


def _patch_balance(monkeypatch, net_asset=1_000_000):
    async def _fake(afhr_flpr="N"):
        return [], SimpleNamespace(net_asset=net_asset)

    from src.api import balance as balance_mod
    monkeypatch.setattr(balance_mod, "get_balance", _fake)


def _patch_thresholds(monkeypatch, *, warn=4.0, block=None):
    from src.db import system_config as sc

    async def _warn():
        return warn

    async def _block():
        return block

    monkeypatch.setattr(sc, "get_account_risk_warn_pct", _warn)
    monkeypatch.setattr(sc, "get_account_risk_block_pct", _block)


@pytest.fixture(autouse=True)
def _reset_watcher_state():
    watcher.reset_state_for_test()
    yield
    watcher.reset_state_for_test()


class TestR6WatcherGate:
    @pytest.mark.asyncio
    async def test_dark_launch_never_gates(self, monkeypatch):
        """block 임계 부재(None) = 다크런치 — 큰 리스크에도 게이트 False."""
        pos = {"A": SimpleNamespace(buy_price=50_000, quantity=10)}
        sched = _fake_scheduler([
            _fake_strat("kojiro", pos, stop_of=lambda t: 40_000),  # 10만원 = 10%
        ])
        _patch_balance(monkeypatch, net_asset=1_000_000)
        _patch_thresholds(monkeypatch, warn=4.0, block=None)
        await watcher.run_account_risk_watch_once(sched)
        assert watcher.is_soft_gated() is False

    @pytest.mark.asyncio
    async def test_block_threshold_gates_and_warns(self, monkeypatch, caplog):
        pos = {"A": SimpleNamespace(buy_price=50_000, quantity=10)}
        sched = _fake_scheduler([
            _fake_strat("kojiro", pos, stop_of=lambda t: 40_000),
        ])
        _patch_balance(monkeypatch, net_asset=1_000_000)
        _patch_thresholds(monkeypatch, warn=4.0, block=6.0)  # 실효 10% ≥ 6%
        with caplog.at_level(logging.INFO, logger="src.engine.scheduler"):
            await watcher.run_account_risk_watch_once(sched)
        assert watcher.is_soft_gated() is True
        hits = [r for r in caplog.records if "[account_risk_gate]" in r.message]
        assert hits
        # F5·F10 — 전이 로그는 entered 명시 + WARNING 레벨(INFO 강등 뮤테이션 검출)
        assert any("transition=entered" in r.message for r in hits)
        assert any(r.levelno == logging.WARNING for r in hits)

    @pytest.mark.asyncio
    async def test_failure_releases_active_gate_loudly(self, monkeypatch, caplog):
        """F5 — 활성 게이트가 평가 실패로 풀릴 때 무음 해제 금지."""
        pos = {"A": SimpleNamespace(buy_price=50_000, quantity=10)}
        sched = _fake_scheduler([
            _fake_strat("kojiro", pos, stop_of=lambda t: 40_000),
        ])
        _patch_balance(monkeypatch, net_asset=1_000_000)
        _patch_thresholds(monkeypatch, warn=4.0, block=6.0)
        await watcher.run_account_risk_watch_once(sched)
        assert watcher.is_soft_gated() is True

        from src.api import balance as balance_mod

        async def _boom(afhr_flpr="N"):
            raise RuntimeError("KIS down")

        monkeypatch.setattr(balance_mod, "get_balance", _boom)
        with caplog.at_level(logging.WARNING, logger="src.engine.scheduler"):
            await watcher.run_account_risk_watch_once(sched)
        assert watcher.is_soft_gated() is False
        assert any("released reason=eval_failure" in r.message
                   for r in caplog.records)

    @pytest.mark.asyncio
    async def test_momentary_gate_releases_on_recovery(self, monkeypatch):
        """순간 게이트 — 리스크가 임계 아래로 내려오면 다음 평가에서 해제."""
        pos = {"A": SimpleNamespace(buy_price=50_000, quantity=10)}
        sched = _fake_scheduler([
            _fake_strat("kojiro", pos, stop_of=lambda t: 40_000),
        ])
        _patch_balance(monkeypatch, net_asset=1_000_000)
        _patch_thresholds(monkeypatch, warn=4.0, block=6.0)
        await watcher.run_account_risk_watch_once(sched)
        assert watcher.is_soft_gated() is True
        # 회복: 손절선이 올라와 실효 리스크 1%
        sched2 = _fake_scheduler([
            _fake_strat("kojiro", pos, stop_of=lambda t: 49_000),
        ])
        await watcher.run_account_risk_watch_once(sched2)
        assert watcher.is_soft_gated() is False

    @pytest.mark.asyncio
    async def test_fail_open_on_balance_error(self, monkeypatch, caplog):
        """R6 — get_balance 예외 → 게이트 False + LOUD WARNING."""
        from src.api import balance as balance_mod

        async def _boom(afhr_flpr="N"):
            raise RuntimeError("KIS down")

        monkeypatch.setattr(balance_mod, "get_balance", _boom)
        _patch_thresholds(monkeypatch, warn=4.0, block=6.0)
        sched = _fake_scheduler([_fake_strat("kojiro", {})])
        with caplog.at_level(logging.WARNING, logger="src.engine.scheduler"):
            await watcher.run_account_risk_watch_once(sched)
        assert watcher.is_soft_gated() is False
        assert any("[account_risk_watch_failed]" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_r5_buy_disabled_untouched(self, monkeypatch):
        """R5 이원화 — risk.py 가 세운 buy_disabled 를 감시자가 지우지 않는다."""
        pos = {"A": SimpleNamespace(buy_price=50_000, quantity=1)}
        strat = _fake_strat("kojiro", pos, stop_of=lambda t: 49_500)
        strat.state.buy_disabled = True  # 일일손실 한도 발동 상황 재현
        sched = _fake_scheduler([strat])
        _patch_balance(monkeypatch, net_asset=10_000_000)
        _patch_thresholds(monkeypatch, warn=4.0, block=6.0)
        await watcher.run_account_risk_watch_once(sched)  # 판정 = ok
        assert strat.state.buy_disabled is True  # 절대 미접촉


class TestWatchLoopLifecycle:
    """자기 종료 루프 — cancel 불요 설계의 두 계약."""

    @pytest.mark.asyncio
    async def test_loop_exits_immediately_when_not_running(self):
        sched = SimpleNamespace(_running=False,
                                registry=SimpleNamespace(all=lambda: []))
        # _running=False → 평가 0회 즉시 반환 (hang 하면 timeout FAIL)
        import asyncio
        await asyncio.wait_for(watcher.watch_loop(sched), timeout=1.0)

    @pytest.mark.asyncio
    async def test_watch_loop_repeats_until_stopped(self, monkeypatch):
        """F2 — 주기 **반복** 봉인: 순간 게이트(회복 시 해제)의 전달 기제.

        `while → if` 뮤테이션(1회 평가 후 종료 = 5분 재평가 소멸)이 이 테스트에서
        FAIL 해야 한다 — 종료만 검사하던 기존 2케이스는 그 뮤테이션에 무력했다.
        """
        import asyncio
        calls = {"n": 0}
        sched = SimpleNamespace(_running=True,
                                registry=SimpleNamespace(all=lambda: []))

        async def fake_once(s):
            calls["n"] += 1
            if calls["n"] >= 2:
                sched._running = False

        monkeypatch.setattr(watcher, "run_account_risk_watch_once", fake_once)

        async def fast_sleep(_secs):
            return None

        monkeypatch.setattr(watcher.asyncio, "sleep", fast_sleep)
        await asyncio.wait_for(watcher.watch_loop(sched), timeout=2.0)
        assert calls["n"] >= 2, "루프가 반복하지 않음 — 주기 재평가 소멸"

    @pytest.mark.asyncio
    async def test_ensure_watch_loop_idempotent(self):
        import asyncio
        sched = SimpleNamespace(_running=False,
                                registry=SimpleNamespace(all=lambda: []))
        watcher._watch_task = None
        watcher.ensure_watch_loop(sched)
        first = watcher._watch_task
        assert first is not None
        # 살아있는(또는 방금 만든) 태스크가 있으면 재스폰 금지
        watcher.ensure_watch_loop(sched)
        if not first.done():
            assert watcher._watch_task is first
        await asyncio.sleep(0)  # 루프 즉시 종료 소화
        watcher._watch_task = None


_ALL_STRATEGIES = [
    ("src.engine.strategies.momentum", "MomentumStrategy", "momentum"),
    ("src.engine.strategies.volatility_breakout", "VolatilityBreakoutStrategy",
     "volatility_breakout"),
    ("src.engine.strategies.long_tail_volatility", "LongTailVolatilityStrategy",
     "long_tail_volatility"),
    ("src.engine.strategies.donchian_swing", "DonchianSwingStrategy",
     "donchian_swing"),
    ("src.engine.strategies.bull_flag_breakout", "BullFlagBreakoutStrategy",
     "bull_flag_breakout"),
    ("src.engine.strategies.vcp_breakout", "VcpBreakoutStrategy", "vcp_breakout"),
    ("src.engine.strategies.kojiro", "KojiroStrategy", "kojiro"),
]


class TestR7StrategyWiring:
    """gate True → 7전략 전수 check_buy_signal NONE (F3 — AST 가드와 이중 봉인)."""

    def _gate_on(self, monkeypatch):
        monkeypatch.setattr(watcher, "is_soft_gated", lambda: True)

    @pytest.mark.parametrize("mod,cls,sid", _ALL_STRATEGIES)
    def test_all_strategies_return_none_when_gated(self, monkeypatch, mod, cls, sid):
        import importlib
        strategy_cls = getattr(importlib.import_module(mod), cls)
        s = strategy_cls(StrategyConfig(
            strategy_id=sid, name=sid, params={"exchange": "KRX"}))
        self._gate_on(monkeypatch)
        assert s.check_buy_signal("005930", 70_000, 69_000) == Signal.NONE

    def test_gate_helper_fail_open(self, monkeypatch):
        """is_soft_gated 예외 → False (fail-open) — 매수 경로가 죽지 않는다."""
        from src.engine.strategies.momentum import MomentumStrategy

        def _boom():
            raise RuntimeError("watcher import broken")

        monkeypatch.setattr(watcher, "is_soft_gated", _boom)
        s = MomentumStrategy(StrategyConfig(
            strategy_id="momentum", name="momentum", params={"exchange": "KRX"}))
        assert s._account_soft_gate_blocked("005930") is False

    def test_gate_skip_log_capped_once_per_day(self, monkeypatch, caplog):
        # donchian = 게이트 최상단 전략(시각 무관) — momentum 은 15:20 컷이 선행해
        # 장 마감 후 실행 시 게이트 도달 전에 반환된다(스위트 시간 독립성).
        from src.engine.strategies.donchian_swing import DonchianSwingStrategy
        s = DonchianSwingStrategy(StrategyConfig(
            strategy_id="donchian_swing", name="d", params={"exchange": "KRX"}))
        self._gate_on(monkeypatch)
        with caplog.at_level(logging.INFO):
            s.check_buy_signal("005930", 70_000, 69_000)
            s.check_buy_signal("005930", 70_100, 69_000)
        hits = [r for r in caplog.records if "[account_gate_skip]" in r.message]
        assert len(hits) == 1
