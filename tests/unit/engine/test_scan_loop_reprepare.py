"""_scan_loop 빈 _targets 자동 재 prepare 가드 (KIS 5xx 회복).

결함 배경: 2026-05-11 운영. 07:45/08:32 KIS HTTP 500 일시장애로 VB/LTV `prepare()` 실패
→ `_scanned_tickers` 빈 채 종일 운영 → 변동성 돌파 전략 휴면.
재구독은 5분 주기로 돌지만 재 prepare 호출은 없어 회복 경로가 없었다.

본 테스트는 `_scan_loop` 가 통합 구독(`subscribe_filtered_stocks`) 호출 *후* 다음 가드를 수행함을 검증한다:

    for sid in ("volatility_breakout", "long_tail_volatility"):
        strategy = self.registry.get(sid)
        if not strategy or not strategy.config.enabled:
            continue
        if hasattr(strategy, "get_scanned_tickers") and not strategy.get_scanned_tickers():
            try:
                await strategy.prepare()
            except Exception:
                logger.exception(...)
                await write_log("ERROR", ...)

- donchian_swing 은 대상 아님 (고정 유니버스이므로 prepare 실패해도 KOSPI200/KOSDAQ150 사용)
- 매 사이클 1회만 발화 (성공/실패 무관하게 다음 사이클에 자연 재시도)
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 더블: 호출 카운트와 raise 옵션을 가진 전략 스텁
# ---------------------------------------------------------------------------
class _SpyStrategy(StrategyBase):
    """`prepare()` 호출/실패를 추적하는 스파이.

    `get_scanned_tickers()` 는 `_scanned_tickers` 를 그대로 반환한다 (실전 VB/LTV 와 동일 시그니처).
    """

    def __init__(self, config: StrategyConfig, scanned: list[str] | None = None, raise_on_prepare: bool = False):
        super().__init__(config)
        self._scanned_tickers: list[str] = list(scanned or [])
        self._raise_on_prepare = raise_on_prepare
        self.prepare_calls: int = 0

    async def prepare(self) -> None:
        self.prepare_calls += 1
        if self._raise_on_prepare:
            raise RuntimeError("KIS 5xx 시뮬레이션")

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0

    def get_scanned_tickers(self) -> list[str]:
        return list(self._scanned_tickers)


class _NoScannedAttrStrategy(StrategyBase):
    """`get_scanned_tickers()` 메서드 자체가 없는 전략 — 가드는 해당 전략을 건드리지 않아야 한다.

    현재 사양상 VB/LTV/donchian 모두 메서드를 보유하지만, hasattr 분기가 깨지지 않음을 회귀로 확인.
    """

    async def prepare(self) -> None:
        self.prepare_calls = getattr(self, "prepare_calls", 0) + 1

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0


# ---------------------------------------------------------------------------
# Test driver: scheduler 인스턴스 없이 가드 로직만 절단 실행
# ---------------------------------------------------------------------------
async def _run_guard(registry: StrategyRegistry, write_log_calls: list[dict]) -> None:
    """`_scan_loop` 내부 가드 동작과 동일한 의미체계를 실행한다.

    구현 시점에는 `scheduler._scan_loop` 가 직접 호출하지만, 단위 테스트에서는
    동일 분기 의미를 갖는 별도 헬퍼를 통해 검증한다. 이 헬퍼의 분기 그 자체를 테스트하는 것이 아니라,
    scheduler 가 동일한 의미체계를 구현하도록 명세를 고정한다.

    실제 구현은 `src/engine/scheduler.py::TradingScheduler._reprepare_breakout_if_empty()` 또는
    `_scan_loop` 인라인으로 들어가야 한다.
    """
    from src.engine.scheduler import TradingScheduler

    # scheduler 인스턴스 없이도 가드 로직만 호출 가능해야 한다.
    # 구현 위치 후보: TradingScheduler 인스턴스 메서드. registry 만 주입된 스텁 인스턴스로 호출한다.
    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = registry

    # write_log 가짜를 가드가 사용하는 모듈에 주입
    from src.engine import scheduler as scheduler_module

    original_write_log = scheduler_module.write_log

    async def fake_write_log(level: str, message: str) -> None:
        write_log_calls.append({"level": level, "message": message})

    scheduler_module.write_log = fake_write_log
    try:
        await sched._reprepare_breakout_if_empty()
    finally:
        scheduler_module.write_log = original_write_log


# ---------------------------------------------------------------------------
# Case A: VB scanned=[], enabled=True → prepare() 호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_vb_empty_scanned_triggers_reprepare():
    registry = StrategyRegistry()
    vb = _SpyStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.5, enabled=True),
        scanned=[],
    )
    registry.register(vb)

    write_log_calls: list[dict] = []
    await _run_guard(registry, write_log_calls)

    assert vb.prepare_calls == 1, "빈 scanned 시 prepare()가 정확히 1회 호출되어야 함"
    # WARNING 로그가 사전에 남는다
    assert any(call["level"] == "WARNING" and "volatility_breakout" in call["message"] for call in write_log_calls)


# ---------------------------------------------------------------------------
# Case B: VB scanned=["A","B"], enabled=True → prepare() 미호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_vb_populated_scanned_skips_reprepare():
    registry = StrategyRegistry()
    vb = _SpyStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.5, enabled=True),
        scanned=["005930", "000660"],
    )
    registry.register(vb)

    write_log_calls: list[dict] = []
    await _run_guard(registry, write_log_calls)

    assert vb.prepare_calls == 0, "scanned가 비어있지 않으면 prepare()를 호출하지 않아야 함"


# ---------------------------------------------------------------------------
# Case C: VB enabled=False → prepare() 미호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_vb_disabled_skips_reprepare():
    registry = StrategyRegistry()
    vb = _SpyStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.5, enabled=False),
        scanned=[],
    )
    registry.register(vb)

    write_log_calls: list[dict] = []
    await _run_guard(registry, write_log_calls)

    assert vb.prepare_calls == 0, "disabled 전략은 빈 scanned여도 prepare()를 호출하지 않아야 함"


# ---------------------------------------------------------------------------
# Case D: VB prepare() raise → ERROR 로그 + 가드 본체는 예외 없이 종료
#         (다음 사이클에서 자연 재시도되는 의미체계를 명세화)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_vb_prepare_raises_is_swallowed_with_error_log():
    registry = StrategyRegistry()
    vb = _SpyStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.5, enabled=True),
        scanned=[],
        raise_on_prepare=True,
    )
    registry.register(vb)

    write_log_calls: list[dict] = []
    # 예외가 가드 밖으로 전파되면 _scan_loop 의 except Exception 으로 흘러 5분 sleep 흐름이 깨질 수 있다.
    # 가드 자체가 try/except 로 흡수하여 다음 사이클에 자연 재시도되도록 한다.
    await _run_guard(registry, write_log_calls)

    assert vb.prepare_calls == 1, "raise 발생도 prepare() 호출 자체는 1회 카운트됨"
    assert any(
        call["level"] == "ERROR" and "volatility_breakout" in call["message"]
        for call in write_log_calls
    ), "prepare() 실패 시 ERROR 로그가 system_logs에 기록되어야 함"


# ---------------------------------------------------------------------------
# Case E: donchian_swing scanned=[] → prepare() 미호출 (대상 아님)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_donchian_swing_empty_is_not_reprepared():
    registry = StrategyRegistry()
    ds = _SpyStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="Donchian", weight=0.5, enabled=True),
        scanned=[],
    )
    registry.register(ds)

    write_log_calls: list[dict] = []
    await _run_guard(registry, write_log_calls)

    assert ds.prepare_calls == 0, "donchian_swing은 고정 유니버스라 빈 scanned여도 가드 대상 아님"


# ---------------------------------------------------------------------------
# Case F: VB + LTV 둘 다 빈 상태 → 두 전략 모두 prepare() 호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_vb_and_ltv_both_empty_both_reprepared():
    registry = StrategyRegistry()
    vb = _SpyStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.3, enabled=True),
        scanned=[],
    )
    ltv = _SpyStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="LTV", weight=0.3, enabled=True),
        scanned=[],
    )
    registry.register(vb)
    registry.register(ltv)

    write_log_calls: list[dict] = []
    await _run_guard(registry, write_log_calls)

    assert vb.prepare_calls == 1
    assert ltv.prepare_calls == 1
    # 두 전략 모두 WARNING 로그를 남긴다
    vb_warned = any(c["level"] == "WARNING" and "volatility_breakout" in c["message"] for c in write_log_calls)
    ltv_warned = any(c["level"] == "WARNING" and "long_tail_volatility" in c["message"] for c in write_log_calls)
    assert vb_warned and ltv_warned


# ---------------------------------------------------------------------------
# 회귀: 미등록 전략 안전성 (registry.get 이 None 반환해도 가드가 crash 하지 않음)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unregistered_strategies_do_not_crash_guard():
    """VB/LTV 가 registry 에 없어도 가드는 조용히 통과해야 한다."""
    registry = StrategyRegistry()  # 빈 레지스트리

    write_log_calls: list[dict] = []
    # 예외가 전파되면 _scan_loop 가 깨진다.
    await _run_guard(registry, write_log_calls)

    # WARNING/ERROR 어느 것도 남기지 않는다 (호출 자체가 없음)
    assert all("volatility_breakout" not in c["message"] for c in write_log_calls)
    assert all("long_tail_volatility" not in c["message"] for c in write_log_calls)
