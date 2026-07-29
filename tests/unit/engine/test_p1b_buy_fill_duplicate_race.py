"""P1-B Red — 체결통보 중복 수신 race (`_handle_buy_fill` 멱등 가드).

명세: `_workspace/red/_behaviors_p1_20260729.md` 사이클 B / 자문:
`_workspace/domain_consult/cycle_weekly_review_20260729.md`.

## 사고 (07-27 377450 실사고)

전량 체결 완료 시 `_handle_buy_fill` 이 `_order_strategy.pop(order_no)` 등 매핑 4종을 제거.
동일 order_no 2차 체결통보 도착 → 매핑 miss → `_lookup_strategy_from_trade_history` 는
PENDING row 탐색인데 이미 COMPLETED → miss → `"momentum"` 하드코딩 폴백 →
`state.positions[ticker]` 신규 등록 + DB positions PK(ticker) 덮어쓰기 → 원래 kojiro
포지션이 비활성 momentum 명의로 실명 → 손절/익일청산 사각.

## 행위 (RED — 신규 구현 필요)

- B-1 (멱등 가드, HIGH): 전량 체결 완료된 order_no 후속 통보 무시 —
  positions/trade_history/pending 무변경 + `[buy_fill_duplicate_ignored]` INFO.
- B-2 (폴백 안전, HIGH): 매핑 miss 폴백에서 ticker 가 이미 타 전략 보유 중이면
  덮어쓰기 대신 skip + `[buy_fill_fallback_held_conflict]` ERROR.
- B-4 (회귀 0): 부분 체결 → 잔여 체결 정상 흐름(total_filled < ordered_qty 동안) 무변경.
- B-5 (회귀 0): `_completed_orders` 보정 INSERT race 가드 무회귀 (기존 스위트 확인).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.unit


class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id: str = "momentum") -> None:
        super().__init__(
            StrategyConfig(
                strategy_id=strategy_id,
                name=f"{strategy_id}-dummy",
                enabled=True,
                weight=1.0,
                params={"exchange": "KRX"},
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


@pytest.fixture
def registry() -> StrategyRegistry:
    reg = StrategyRegistry()
    reg.register(_DummyStrategy(strategy_id="momentum"))
    reg.register(_DummyStrategy(strategy_id="kojiro"))
    reg.register(_DummyStrategy(strategy_id="donchian_swing"))
    return reg


@pytest.fixture
def engine(registry: StrategyRegistry) -> OrderEngine:
    return OrderEngine(registry)


@pytest.fixture
def mock_db(monkeypatch: pytest.MonkeyPatch):
    """DB 부작용 격리 — update/insert/save/lookup 모두 스텁."""
    import src.engine.order_engine as _oe
    import src.db.positions as _positions

    monkeypatch.setattr(_oe, "update_trade_status", AsyncMock(return_value=1))
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_positions, "save_position", AsyncMock(return_value=None))
    # 2차 통보 시점엔 PENDING row 부재(이미 COMPLETED) → lookup miss 재현
    monkeypatch.setattr(_oe, "_lookup_strategy_from_trade_history", AsyncMock(return_value=None))
    return _oe


# ─────────────────────────────────────────────────────────────────────────
# B-1 (HIGH) — 전량 체결 완료 order_no 의 후속 통보는 멱등 무시
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_B1_duplicate_notice_after_full_fill_is_ignored(
    engine: OrderEngine, registry: StrategyRegistry, mock_db, caplog,
) -> None:
    """377450 실사고 재현: kojiro 매수 전량 체결 후 동일 order_no 2차 통보.

    현행: 매핑 pop 후 momentum 폴백 → momentum Position 신규 등록 (결함).
    기대: 후속 통보 멱등 무시 → kojiro 포지션 무변경 + momentum 미등록.
    """
    kojiro = registry.get("kojiro")
    momentum = registry.get("momentum")
    order_no = "0000377450"
    engine._order_qty[order_no] = 3
    engine._order_strategy[order_no] = "kojiro"
    engine._order_ticker[order_no] = "377450"

    # 1차 통보 @11,850 전량(3주) 체결 → kojiro 포지션 등록 + 매핑 pop
    await engine.handle_execution_notice(
        ticker="377450", order_no=order_no, side="BUY", price=11_850, quantity=3,
    )
    assert "377450" in kojiro.state.positions
    assert kojiro.state.positions["377450"].buy_price == 11_850
    assert kojiro.state.positions["377450"].quantity == 3

    # 2차 통보 @11,860 (중복 수신)
    await engine.handle_execution_notice(
        ticker="377450", order_no=order_no, side="BUY", price=11_860, quantity=3,
    )

    # 멱등: momentum 에 신규 포지션 없음 (결함이면 여기 생김)
    assert "377450" not in momentum.state.positions, (
        "B-1: 중복 통보로 momentum Position 신규 등록됨 (멱등 가드 부재)"
    )
    # kojiro 포지션 전략/가격/수량 무변경
    pos = kojiro.state.positions["377450"]
    assert pos.strategy_id == "kojiro"
    assert pos.buy_price == 11_850, f"B-1: 중복 통보로 가격 오염 ({pos.buy_price})"
    assert pos.quantity == 3


@pytest.mark.asyncio
async def test_B1_duplicate_notice_no_second_registration_log(
    engine: OrderEngine, registry: StrategyRegistry, mock_db, caplog,
) -> None:
    """2차 통보 시 '포지션 등록' 로그 0건 + 멱등 무시 로그 1건."""
    import logging
    caplog.set_level(logging.INFO)
    order_no = "0000377451"
    engine._order_qty[order_no] = 2
    engine._order_strategy[order_no] = "kojiro"
    engine._order_ticker[order_no] = "377450"
    await engine.handle_execution_notice(
        ticker="377450", order_no=order_no, side="BUY", price=11_850, quantity=2,
    )
    caplog.clear()
    await engine.handle_execution_notice(
        ticker="377450", order_no=order_no, side="BUY", price=11_860, quantity=2,
    )
    text = caplog.text
    assert "포지션 등록" not in text, "B-1: 중복 통보가 신규 포지션 등록 로그 발생"
    assert "buy_fill_duplicate_ignored" in text, (
        "B-1: 멱등 무시 로그 [buy_fill_duplicate_ignored] 부재"
    )


# ─────────────────────────────────────────────────────────────────────────
# B-2 (HIGH) — 매핑 miss 폴백에서 ticker 가 타 전략 보유 중이면 skip + ERROR
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_B2_fallback_skips_when_ticker_held_by_other_strategy(
    engine: OrderEngine, registry: StrategyRegistry, mock_db, caplog,
) -> None:
    """매핑 miss + ticker 가 이미 donchian 보유 중 → momentum 덮어쓰기 대신 skip + ERROR.

    현행: momentum 폴백 → momentum Position 신규 등록 → 실명 (결함).
    기대: 기존 donchian 포지션 보존 + momentum 미등록 + [buy_fill_fallback_held_conflict] ERROR.
    """
    import logging
    caplog.set_level(logging.ERROR)
    donchian = registry.get("donchian_swing")
    momentum = registry.get("momentum")
    # 이미 donchian 이 000660 보유 중
    donchian.state.positions["000660"] = Position(
        ticker="000660", buy_price=180_000, quantity=5, order_no="PRE",
        strategy_id="donchian_swing", buy_date=None,
    )
    order_no = "0000660999"  # 매핑 dict 에 없음 (miss)
    engine._order_ticker[order_no] = "000660"  # ticker 매핑만 존재(전략 매핑 miss)

    await engine.handle_execution_notice(
        ticker="000660", order_no=order_no, side="BUY", price=181_000, quantity=5,
    )

    # 기존 donchian 포지션 보존
    assert donchian.state.positions["000660"].strategy_id == "donchian_swing"
    assert donchian.state.positions["000660"].buy_price == 180_000
    # momentum 미등록
    assert "000660" not in momentum.state.positions, (
        "B-2: 타 전략 보유 종목을 momentum 폴백이 덮어씀 (skip 가드 부재)"
    )
    assert "buy_fill_fallback_held_conflict" in caplog.text, (
        "B-2: [buy_fill_fallback_held_conflict] ERROR 로그 부재"
    )


# ─────────────────────────────────────────────────────────────────────────
# B-4 (회귀 0) — 부분 체결 → 잔여 체결 정상 흐름 무변경
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_B4_partial_then_full_fill_unchanged(
    engine: OrderEngine, registry: StrategyRegistry, mock_db, monkeypatch,
) -> None:
    """1차 total_filled=1/ordered=3 PARTIAL → 2차 total_filled=3 전량. 정상 처리 (회귀 0).

    같은 order_no 복수 통보가 합법인 경우(전량 미달 동안) 멱등 가드가 개입하면 안 됨.
    """
    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._schedule_cancel", lambda *a, **kw: None,
    )
    kojiro = registry.get("kojiro")
    momentum = registry.get("momentum")
    order_no = "0000112610"
    engine._order_qty[order_no] = 3
    engine._order_strategy[order_no] = "kojiro"
    engine._order_ticker[order_no] = "112610"

    # 1차 부분 체결 (1/3)
    await engine.handle_execution_notice(
        ticker="112610", order_no=order_no, side="BUY", price=11_850, quantity=1,
    )
    assert kojiro.state.positions["112610"].quantity == 1
    # 2차 잔여 체결 (누적 3/3 전량)
    await engine.handle_execution_notice(
        ticker="112610", order_no=order_no, side="BUY", price=11_860, quantity=2,
    )
    # 전량 체결 → 수량 갱신, 여전히 kojiro (momentum 미등록)
    assert kojiro.state.positions["112610"].quantity == 3
    assert "112610" not in momentum.state.positions
    assert kojiro.state.positions["112610"].strategy_id == "kojiro"


# ─────────────────────────────────────────────────────────────────────────
# B-3 (가시화) — 진짜 고아 체결 (B-1/B-2 미해당) → momentum 등록 + CRITICAL 알림
# tester 추가 (2026-07-29) — B-3 CRITICAL 경로 미커버 영역 회귀 가드.
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_B3_genuine_orphan_fires_critical_write_log(
    engine: OrderEngine, registry: StrategyRegistry, mock_db, monkeypatch,
) -> None:
    """매핑 miss + trade_history miss + 미보유 (진짜 고아) → momentum 신규 등록 +
    `[buy_fill_fallback_orphan]` CRITICAL write_log fire-and-forget 발화.

    B-1(멱등)·B-2(held-conflict skip) 모두 미해당인 진짜 고아 체결만 여기 도달.
    fire-and-forget `asyncio.create_task` 가 이벤트 루프 컨텍스트에서 실제 실행되는지
    (사이클 57 V-1 알람 패턴 정합) 검증 — await sleep(0) 로 예약 task drain.
    """
    import asyncio

    write_log_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(mock_db, "write_log", write_log_mock)
    momentum = registry.get("momentum")

    order_no = "0009999999"  # _order_strategy 매핑 없음 (miss)
    engine._order_ticker[order_no] = "900900"  # ticker 매핑만 존재
    # is_ticker_held_by_any=False (어느 전략도 900900 미보유) → B-2 skip 미해당

    await engine.handle_execution_notice(
        ticker="900900", order_no=order_no, side="BUY", price=5_000, quantity=10,
    )
    # fire-and-forget task 실행 기회 부여
    await asyncio.sleep(0)

    # 진짜 고아 → momentum 폴백으로 신규 등록됨 (B-3 은 차단이 아닌 가시화)
    assert "900900" in momentum.state.positions
    assert momentum.state.positions["900900"].strategy_id == "momentum"
    # CRITICAL 알림 발화 (운영자 즉시 인지)
    assert write_log_mock.await_count == 1, "B-3: 고아 체결 CRITICAL write_log 미발화"
    level_arg = write_log_mock.await_args.args[0]
    msg_arg = write_log_mock.await_args.args[1]
    assert level_arg == "CRITICAL"
    assert "buy_fill_fallback_orphan" in msg_arg
