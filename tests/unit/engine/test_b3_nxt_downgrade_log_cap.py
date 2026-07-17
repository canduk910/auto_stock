"""사이클 B-3 Red — `[nxt_downgrade]` 로그 emit cap (ticker별 일일 1회).

배경 (운영 실측, 2026-06-01):
    분석 메모는 stock_master 사후 보강 누락 가설을 제시했지만, 064400 row 의
    `refreshed_at=2026-05-31T23:19:59` + `nxt_tradable=False` 이미 정상 저장됨.
    사이클 32 NXT 사전 차단 메커니즘은 정상 작동. 실질 결함은 B-1 매도 좀비
    폭주(`execute_sell` 100+회 재진입) 부작용으로 동일 호출 시점 발생한
    `_strategy_exchange_async` 가 매번 `[nxt_downgrade] WARNING` 1행 발화하여
    115건 로그 폭주. *다운그레이드 결정* (반환값 KRX) 은 정확하나 *로그 cap* 부재.

결정:
    `OrderEngine._nxt_downgrade_logged_today: set[str]` (ticker only) 신규 필드.
    사이클 52 `_market_closed_blocked_logged_today` 동형 패턴.
    `_strategy_exchange_async` 의 `[nxt_downgrade]` 발화 직전 cap 검사 —
    set 에 있으면 로그 skip, 없으면 발화 + 등록.
    *다운그레이드 결정* (반환값 KRX) 은 cap 검사 *밖* — 로직 무변경.
    `OrderEngine.reset_daily_state()` (사이클 52 도입) 에 clear() 추가.

회귀 가드 시나리오 (총 4):
    S1: 100회 연속 호출 (동일 ticker, nxt_tradable=False)
        → `[nxt_downgrade]` 발화 정확히 1회, 반환값 100회 모두 "KRX".
    S2: ticker별 격리 — A 100회 + B 100회 → 발화 정확히 2회 (각 ticker 1회).
    S3: `reset_daily_state()` 후 동일 ticker 재발화 — 1회 → reset → 1회 → 총 2회.
    S4: 회귀 가드 — nxt_tradable=True 종목은 다운그레이드 안 함 + 발화 0회 +
        cap set 미등록. 사이클 32 회귀 보존.

테스트 더블:
    - stock_master.get: AsyncMock(return_value=StockBasics(nxt_tradable=...))
    - stock_master.is_stale: AsyncMock(return_value=False) — `_log_stale_async` 무영향
    - write_log: AsyncMock — `[nxt_downgrade]` prefix 카운트 검증

Red 상태 검증 (Green 구현 전):
    - S1 → 100회 모두 발화 (cap 부재) → FAIL
    - S2 → 200회 발화 (cap 부재) → FAIL
    - S3 → `reset_daily_state` 헬퍼는 이미 존재하나 `_nxt_downgrade_logged_today`
      clear 누락 + set 자체 부재 → FAIL
    - S4 → 이미 PASS (`nxt_tradable=True` 분기는 기존 코드가 다운그레이드 안 함).
      cap set 부재 검증은 attribute 부재 → PASS (set 자체가 없어서 미등록).
      회귀 가드 목적으로 명시 — Green 후에도 통과 유지.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import (
    Signal,
    StrategyBase,
    StrategyConfig,
)
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 더미 전략 — exchange 파라미터로 NXT/SOR 진입 분기 검증
# ---------------------------------------------------------------------------
class _DummyStrategy(StrategyBase):
    def __init__(
        self,
        strategy_id: str = "momentum",
        exchange: str = "SOR",
    ) -> None:
        super().__init__(
            StrategyConfig(
                strategy_id=strategy_id,
                name=f"{strategy_id}-dummy",
                enabled=True,
                weight=1.0,
                params={"exchange": exchange},
            )
        )
        self.state.total_investment = 10_000_000

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 0


# ---------------------------------------------------------------------------
# StockBasics 더블 — stock_master.get 반환형 (실제 모델 import 회피 — 단위 격리)
# ---------------------------------------------------------------------------
@dataclass
class _FakeBasics:
    ticker: str
    nxt_tradable: bool


@pytest.fixture
def registry() -> StrategyRegistry:
    reg = StrategyRegistry()
    # exchange=SOR — `_strategy_exchange_async` 가 base != KRX 분기 진입
    strat = _DummyStrategy(strategy_id="momentum", exchange="SOR")
    reg.register(strat)
    return reg


@pytest.fixture
def engine(registry: StrategyRegistry) -> OrderEngine:
    return OrderEngine(registry)


@pytest.fixture
def mock_write_log(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """write_log AsyncMock — `[nxt_downgrade]` prefix 카운트 검증."""
    mock = AsyncMock(return_value=None)
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "write_log", mock)
    return mock


def _make_stock_master_mock(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ticker_to_nxt: dict[str, bool],
) -> AsyncMock:
    """ticker → nxt_tradable 매핑 mock.

    `_strategy_exchange_async` 가 lazy import (`from src.db import stock_master`)
    하므로 모듈 attribute 를 직접 패치.
    """
    import src.db.stock_master as _sm

    async def _fake_get(ticker: str):
        if ticker not in ticker_to_nxt:
            return None
        return _FakeBasics(ticker=ticker, nxt_tradable=ticker_to_nxt[ticker])

    async def _fake_is_stale(ticker: str) -> bool:  # noqa: ARG001
        return False

    monkeypatch.setattr(_sm, "get", AsyncMock(side_effect=_fake_get))
    monkeypatch.setattr(_sm, "is_stale", AsyncMock(side_effect=_fake_is_stale))
    return _sm.get


def _count_nxt_downgrade_logs(mock_write_log: AsyncMock) -> int:
    """write_log 호출 중 `[nxt_downgrade]` prefix 카운트."""
    return sum(
        1
        for call in mock_write_log.await_args_list
        if len(call.args) >= 2 and "[nxt_downgrade]" in str(call.args[1])
    )


def _count_nxt_downgrade_logs_for(mock_write_log: AsyncMock, ticker: str) -> int:
    """ticker 포함 `[nxt_downgrade]` 로그 카운트 (S2 검증용)."""
    return sum(
        1
        for call in mock_write_log.await_args_list
        if len(call.args) >= 2
        and "[nxt_downgrade]" in str(call.args[1])
        and ticker in str(call.args[1])
    )


# ===========================================================================
# S1 — 동일 ticker 100회 호출 → `[nxt_downgrade]` 발화 1회 + 100회 모두 KRX 반환
# ===========================================================================
@pytest.mark.asyncio
async def test_s1_when_same_ticker_called_100_times_then_log_emitted_only_once(
    engine: OrderEngine,
    mock_write_log: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    """결함 차단: ticker별 일일 1회 cap. 100회 호출 시 발화 1회, 반환값 100회 모두 KRX."""
    _make_stock_master_mock(monkeypatch, ticker_to_nxt={"064400": False})

    return_values: list[str] = []
    for _ in range(100):
        result = await engine._strategy_exchange_async("momentum", ticker="064400")
        return_values.append(result)

    # 핵심 검증 1: 100회 모두 KRX 반환 (다운그레이드 결정 무영향)
    assert all(r == "KRX" for r in return_values), (
        f"다운그레이드 결정 회귀: 반환값 분포 {set(return_values)} != {{KRX}}"
    )
    assert len(return_values) == 100, "호출 횟수 정합 깨짐"

    # 핵심 검증 2: `[nxt_downgrade]` 발화 정확히 1회 (cap)
    actual_count = _count_nxt_downgrade_logs(mock_write_log)
    assert actual_count == 1, (
        f"`[nxt_downgrade]` emit cap 위반: {actual_count}회 발화 (기대 1회). "
        f"_nxt_downgrade_logged_today set 미구현."
    )

    # cap set 등록 검증 (Green 인터페이스)
    assert hasattr(engine, "_nxt_downgrade_logged_today"), (
        "OrderEngine._nxt_downgrade_logged_today 필드 미정의 — Green 구현 필요"
    )
    assert "064400" in engine._nxt_downgrade_logged_today, (
        "cap set 에 064400 등록 안 됨"
    )


# ===========================================================================
# S2 — ticker별 격리 (A 100회 + B 100회 → 발화 2회)
# ===========================================================================
@pytest.mark.asyncio
async def test_s2_when_two_tickers_each_called_100_times_then_log_emitted_per_ticker(
    engine: OrderEngine,
    mock_write_log: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    """결함 차단: cap 은 ticker 별. A 100회 + B 100회 → 발화 정확히 2회."""
    _make_stock_master_mock(
        monkeypatch,
        ticker_to_nxt={"064400": False, "035420": False},
    )

    # ticker A — 100회
    for _ in range(100):
        await engine._strategy_exchange_async("momentum", ticker="064400")
    # ticker B — 100회
    for _ in range(100):
        await engine._strategy_exchange_async("momentum", ticker="035420")

    # 총 발화 == 2 (각 ticker 1회)
    total_count = _count_nxt_downgrade_logs(mock_write_log)
    assert total_count == 2, (
        f"ticker별 격리 위반: 총 발화 {total_count}회 (기대 2회). "
        f"per-ticker cap 미구현 또는 set 격리 안 됨."
    )

    # ticker별 발화 검증 — 각 정확히 1회
    a_count = _count_nxt_downgrade_logs_for(mock_write_log, "064400")
    b_count = _count_nxt_downgrade_logs_for(mock_write_log, "035420")
    assert a_count == 1, f"064400 발화 {a_count}회 (기대 1회)"
    assert b_count == 1, f"035420 발화 {b_count}회 (기대 1회)"

    # cap set 양쪽 등록 확인
    assert hasattr(engine, "_nxt_downgrade_logged_today")
    assert "064400" in engine._nxt_downgrade_logged_today
    assert "035420" in engine._nxt_downgrade_logged_today


# ===========================================================================
# S3 — reset_daily_state() 후 재발화 (1회 → reset → 1회 = 총 2회)
# ===========================================================================
@pytest.mark.asyncio
async def test_s3_when_reset_daily_state_then_log_re_emits_for_same_ticker(
    engine: OrderEngine,
    mock_write_log: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    """결함 차단: `reset_daily_state` 동행 clear — 다음 영업일 재발화 정상.

    Green 명세: 사이클 52 `OrderEngine.reset_daily_state()` 에
    `self._nxt_downgrade_logged_today.clear()` 추가.
    """
    _make_stock_master_mock(monkeypatch, ticker_to_nxt={"064400": False})

    # 1회차: 100회 호출 → 발화 1회
    for _ in range(100):
        await engine._strategy_exchange_async("momentum", ticker="064400")

    first_count = _count_nxt_downgrade_logs(mock_write_log)
    assert first_count == 1, (
        f"1회차 cap 위반: {first_count}회 (기대 1회) — S1 와 동일 결함"
    )

    # reset_daily_state() 호출 (사이클 52 헬퍼 — 이미 존재)
    assert hasattr(engine, "reset_daily_state"), (
        "OrderEngine.reset_daily_state() 헬퍼 미정의 — 사이클 52 도입 의존"
    )
    engine.reset_daily_state()

    # reset 후 cap set 비워짐
    assert engine._nxt_downgrade_logged_today == set(), (
        "reset_daily_state 후 _nxt_downgrade_logged_today 비어있지 않음 — clear 누락"
    )

    # 2회차: 1회 호출 → 발화 1회 추가 (총 2회)
    await engine._strategy_exchange_async("momentum", ticker="064400")

    total_count = _count_nxt_downgrade_logs(mock_write_log)
    assert total_count == 2, (
        f"reset 후 재발화 안 됨: 총 발화 {total_count}회 (기대 2회 — 1회차 1 + 2회차 1)"
    )


# ===========================================================================
# S4 — 회귀 가드: nxt_tradable=True 종목은 다운그레이드/발화 모두 안 함
# ===========================================================================
@pytest.mark.asyncio
async def test_s4_when_nxt_tradable_true_then_no_downgrade_and_no_log(
    engine: OrderEngine,
    mock_write_log: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    """회귀 가드 (사이클 32): nxt_tradable=True 종목은 다운그레이드 안 함 + 발화 0회.

    이 테스트는 *현재* 이미 PASS — 기존 코드 (`if basics.nxt_tradable: return base`)
    가 다운그레이드 분기 자체 진입 안 함. Green 구현 후에도 통과 유지 가드.
    """
    _make_stock_master_mock(monkeypatch, ticker_to_nxt={"005930": True})

    return_values: list[str] = []
    for _ in range(100):
        result = await engine._strategy_exchange_async("momentum", ticker="005930")
        return_values.append(result)

    # 핵심 검증 1: 다운그레이드 안 함 — 전략 base exchange (SOR) 반환
    assert all(r == "SOR" for r in return_values), (
        f"nxt_tradable=True 종목 다운그레이드 회귀: 반환값 분포 {set(return_values)} != {{SOR}}"
    )

    # 핵심 검증 2: `[nxt_downgrade]` 발화 0회
    log_count = _count_nxt_downgrade_logs(mock_write_log)
    assert log_count == 0, (
        f"nxt_tradable=True 종목에 `[nxt_downgrade]` {log_count}회 발화 — 회귀 위반"
    )

    # cap set 미등록 (선택 검증 — Green 구현 후 회귀 가드)
    logged = getattr(engine, "_nxt_downgrade_logged_today", set())
    assert "005930" not in logged, (
        "nxt_tradable=True 종목이 cap set 에 잘못 등록됨 — Green 구현 시 분기 위치 점검"
    )


# ===========================================================================
# G-3 — 사이클 56-C 마이그레이션 회귀 가드: DailyEmitCap[str] 인스턴스 검증
# ===========================================================================
def test_g3_nxt_downgrade_logged_today_is_daily_emit_cap_instance(
    engine: OrderEngine,
):
    """사이클 56-C 마이그레이션 회귀 가드 — DailyEmitCap[str] 인스턴스.

    _nxt_downgrade_logged_today 가 set[str] 이 아닌 DailyEmitCap[str] 인스턴스여야 함.
    사이클 54 → 56-C 마이그레이션 후 타입 드리프트 차단.
    """
    from src.engine.daily_emit_cap import DailyEmitCap

    assert isinstance(engine._nxt_downgrade_logged_today, DailyEmitCap), (
        f"_nxt_downgrade_logged_today 가 DailyEmitCap 인스턴스가 아님: "
        f"{type(engine._nxt_downgrade_logged_today)!r} — 사이클 56-C 마이그레이션 미완료"
    )
