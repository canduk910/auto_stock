"""cycle236 (N2) — 매도 수량 초과(APBK0400) 분류 + 잔고 재대조 수량 보정.

257720 실사고(08-28): APBK0400 "주문 가능한 수량을 초과했습니다" 가 어떤 분류기에도
안 걸려 3회 재시도 낭비 + CRITICAL + 같은 수량으로 영구 실패 루프. 기존 insufficient
경로(positions 통째 삭제)에 흡수하면 부분 보유가 손절 감시 밖으로 떨어지므로,
**잔고 재대조(sellable_quantity) → 수량 보정 → 재시도** 경로를 신설한다.

명세 = `_workspace/red/cycle236_sell_qty_exceeded_spec.md`.
"""

from __future__ import annotations

import logging
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.order import OrderResult

pytestmark = pytest.mark.unit


def _qty_exceeded_error() -> KisApiError:
    return KisApiError(
        rt_cd="1", msg_cd="APBK0400",
        msg1="주문 가능한 수량을 초과했습니다.",
    )


def _insufficient_error() -> KisApiError:
    return KisApiError(
        rt_cd="1", msg_cd="APBK1234",
        msg1="매도가능수량이 부족합니다.",
    )


class _DummyStrategy(StrategyBase):
    def __init__(self, strategy_id: str = "volatility_breakout") -> None:
        super().__init__(StrategyConfig(
            strategy_id=strategy_id, name=strategy_id, enabled=True,
            weight=1.0, params={"exchange": "KRX"},
        ))
        self.state.total_investment = 10_000_000

    async def prepare(self):
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
    strat = _DummyStrategy()
    strat.state.positions["257720"] = Position(
        ticker="257720", buy_price=51_000, quantity=3,
        order_no="0000411400", strategy_id="volatility_breakout",
        buy_date=date.today(),
    )
    reg.register(strat)
    return reg


@pytest.fixture
def engine(registry: StrategyRegistry) -> OrderEngine:
    return OrderEngine(registry)


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch):
    """DB/로그/거래소 라우팅 격리."""
    import src.engine.order_engine as _oe
    import src.db.positions as _positions

    mocks = SimpleNamespace(
        insert_trade=AsyncMock(return_value=None),
        write_log=AsyncMock(return_value=None),
        update_trade_status=AsyncMock(return_value=1),
        delete_position=AsyncMock(return_value=None),
        save_position=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(_oe, "insert_trade", mocks.insert_trade)
    monkeypatch.setattr(_oe, "write_log", mocks.write_log)
    monkeypatch.setattr(_oe, "safe_write_log", mocks.write_log)
    monkeypatch.setattr(_oe, "update_trade_status", mocks.update_trade_status)
    monkeypatch.setattr(_positions, "delete_position", mocks.delete_position)
    monkeypatch.setattr(_positions, "save_position", mocks.save_position)
    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._strategy_exchange_async",
        AsyncMock(return_value="KRX"),
    )
    return mocks


def _patch_balance(monkeypatch, *, quantity: int, sellable: int):
    holding = SimpleNamespace(
        ticker="257720", quantity=quantity, sellable_quantity=sellable,
    )
    from src.api import balance as balance_mod

    async def _fake(afhr_flpr="N"):
        return ([holding] if quantity or sellable else []), SimpleNamespace(net_asset=0)

    monkeypatch.setattr(balance_mod, "get_balance", _fake)


class TestR1Classifier:
    def test_apbk0400_with_qty_exceeded_phrase(self):
        from src.api.balance import is_sell_qty_exceeded
        assert is_sell_qty_exceeded(_qty_exceeded_error()) is True

    def test_apbk0400_other_phrase_false(self):
        from src.api.balance import is_sell_qty_exceeded
        err = KisApiError(rt_cd="1", msg_cd="APBK0400", msg1="기타 오류입니다.")
        assert is_sell_qty_exceeded(err) is False

    def test_other_code_with_phrase_false(self):
        from src.api.balance import is_sell_qty_exceeded
        err = KisApiError(rt_cd="1", msg_cd="APBK9999",
                          msg1="주문 가능한 수량을 초과했습니다.")
        assert is_sell_qty_exceeded(err) is False

    def test_insufficient_classifier_untouched(self):
        from src.api.balance import is_insufficient_quantity
        assert is_insufficient_quantity(_insufficient_error()) is True
        assert is_insufficient_quantity(_qty_exceeded_error()) is False


class TestR2SelfHeal257720:
    @pytest.mark.asyncio
    async def test_qty_corrected_and_retry_succeeds(
        self, engine, registry, mock_env, monkeypatch, caplog,
    ):
        """1차 APBK0400 → sellable=2 재대조 → 수량 보정 → 2차 2주 성공."""
        import src.engine.order_engine as _oe
        _patch_balance(monkeypatch, quantity=2, sellable=2)
        calls: list[int] = []

        async def _place(*, ticker, side, quantity, price, order_division, exchange):
            calls.append(quantity)
            if len(calls) == 1:
                raise _qty_exceeded_error()
            return OrderResult(order_no="S001", org_no="1", order_time="150001")

        monkeypatch.setattr(_oe, "place_order", _place)
        strat = registry.get("volatility_breakout")
        with caplog.at_level(logging.WARNING):
            await engine.execute_sell("257720", Signal.FORCE_CLEAR,
                                      "volatility_breakout")
        assert calls == [3, 2], f"보정 재시도 수량 오류: {calls}"
        assert strat.state.positions["257720"].quantity == 2
        assert any("[sell_qty_reconciled]" in r.message for r in caplog.records)
        assert mock_env.save_position.await_count >= 1  # DB 수량 보정 동행

    @pytest.mark.asyncio
    async def test_partial_lock_with_accurate_position_not_downgraded(
        self, engine, registry, mock_env, monkeypatch, caplog,
    ):
        """C236-F1 — held == positions(정확)인데 sellable 만 작으면 **잠김이지 오염이 아니다**.

        하향 보정하면 외부 주문 취소 시 잠겼던 주식이 손절 감시 밖에 남는다.
        보정 금지 + 보존 + 중단(place 1회) + `_selling` 유지가 계약.
        """
        import src.engine.order_engine as _oe
        _patch_balance(monkeypatch, quantity=3, sellable=1)
        place = AsyncMock(side_effect=_qty_exceeded_error())
        monkeypatch.setattr(_oe, "place_order", place)
        strat = registry.get("volatility_breakout")
        with caplog.at_level(logging.WARNING):
            await engine.execute_sell("257720", Signal.FORCE_CLEAR,
                                      "volatility_breakout")
        assert place.await_count == 1
        assert strat.state.positions["257720"].quantity == 3  # 하향 보정 금지
        assert mock_env.save_position.await_count == 0
        assert any("[sell_qty_partial_locked]" in r.message for r in caplog.records)
        assert "257720" in engine._selling  # (b) 와 동일 유지 계약

    @pytest.mark.asyncio
    async def test_contamination_corrects_to_held_not_sellable(
        self, engine, registry, mock_env, monkeypatch, caplog,
    ):
        """C236-V1 비축퇴 — 오염(held<positions)의 보정 목표는 **held(보유 실체)**.

        held=2·sellable=1·positions=3: sellable 로 보정하는 뮤테이션이면 1이 되어
        잠긴 1주가 감시 밖으로 — held 기준 2가 계약(손절 감시 수량 = 보유 실체).
        """
        import src.engine.order_engine as _oe
        _patch_balance(monkeypatch, quantity=2, sellable=1)
        calls: list[int] = []

        async def _place(*, ticker, side, quantity, price, order_division, exchange):
            calls.append(quantity)
            if len(calls) == 1:
                raise _qty_exceeded_error()
            return OrderResult(order_no="S002", org_no="1", order_time="150001")

        monkeypatch.setattr(_oe, "place_order", _place)
        strat = registry.get("volatility_breakout")
        with caplog.at_level(logging.WARNING):
            await engine.execute_sell("257720", Signal.FORCE_CLEAR,
                                      "volatility_breakout")
        assert calls == [3, 2], f"보정 재발사 수량은 held(2)여야 한다: {calls}"
        assert strat.state.positions["257720"].quantity == 2
        assert mock_env.save_position.await_count >= 1
        assert mock_env.save_position.await_args.kwargs["quantity"] == 2, (
            "DB 보정 수량이 held 가 아니다 — sellable 대입 뮤테이션"
        )

    @pytest.mark.asyncio
    async def test_locked_all_quantity_preserves_position(
        self, engine, registry, mock_env, monkeypatch, caplog,
    ):
        """sellable=0 ∧ 보유>0 = 전량 기주문 잠김 → 보존 + 중단 (보정 무의미)."""
        import src.engine.order_engine as _oe
        _patch_balance(monkeypatch, quantity=3, sellable=0)
        place = AsyncMock(side_effect=_qty_exceeded_error())
        monkeypatch.setattr(_oe, "place_order", place)
        strat = registry.get("volatility_breakout")
        with caplog.at_level(logging.WARNING):
            await engine.execute_sell("257720", Signal.FORCE_CLEAR,
                                      "volatility_breakout")
        assert place.await_count == 1  # 재시도 낭비 금지
        assert "257720" in strat.state.positions  # 삭제 금지
        assert strat.state.positions["257720"].quantity == 3
        assert any("[sell_qty_locked]" in r.message for r in caplog.records)
        # `_selling` **의도적 유지** — 열린 기주문 실재 = 진행 중 표식 참.
        # 유지가 on_tick 재진입 폭주를 막고, stale 은 [selling_reconcile] 180s
        # 재대조(열린주문 존재 검사)가 수습한다. discard 로 바꾸는 뮤테이션 검출.
        assert "257720" in engine._selling

    @pytest.mark.asyncio
    async def test_zero_holding_falls_to_insufficient_path(
        self, engine, registry, mock_env, monkeypatch,
    ):
        """실보유 0 → 기존 insufficient 경로(삭제 + reconciliation) 재사용."""
        import src.engine.order_engine as _oe
        _patch_balance(monkeypatch, quantity=0, sellable=0)
        place = AsyncMock(side_effect=_qty_exceeded_error())
        monkeypatch.setattr(_oe, "place_order", place)
        strat = registry.get("volatility_breakout")
        await engine.execute_sell("257720", Signal.FORCE_CLEAR,
                                  "volatility_breakout")
        assert place.await_count == 1
        assert "257720" not in strat.state.positions  # 삭제 (기존 계약)
        assert mock_env.delete_position.await_count == 1

    @pytest.mark.asyncio
    async def test_balance_failure_falls_back_to_retries(
        self, engine, registry, mock_env, monkeypatch,
    ):
        """잔고 조회 실패 = graceful → 현행 일반 재시도(3회) 보존."""
        import src.engine.order_engine as _oe
        from src.api import balance as balance_mod

        async def _boom(afhr_flpr="N"):
            raise RuntimeError("KIS down")

        monkeypatch.setattr(balance_mod, "get_balance", _boom)
        place = AsyncMock(side_effect=_qty_exceeded_error())
        monkeypatch.setattr(_oe, "place_order", place)
        strat = registry.get("volatility_breakout")
        await engine.execute_sell("257720", Signal.FORCE_CLEAR,
                                  "volatility_breakout")
        assert place.await_count == 3  # 현행 재시도 한도
        assert "257720" in strat.state.positions  # 보존 (현행)

    @pytest.mark.asyncio
    async def test_apbk1234_path_unchanged(
        self, engine, registry, mock_env, monkeypatch,
    ):
        """R6 — 기존 insufficient(APBK1234) 경로 불변 (즉시 break + 삭제)."""
        import src.engine.order_engine as _oe
        _patch_balance(monkeypatch, quantity=0, sellable=0)
        place = AsyncMock(side_effect=_insufficient_error())
        monkeypatch.setattr(_oe, "place_order", place)
        strat = registry.get("volatility_breakout")
        await engine.execute_sell("257720", Signal.FORCE_CLEAR,
                                  "volatility_breakout")
        assert place.await_count == 1
        assert "257720" not in strat.state.positions
