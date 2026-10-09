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
    # cycle385 부록 R-1-3 — #1.5 재대조가 TTTC0081R(주문 목록)을 한 번 더 읽는다. 패치하지
    # 않으면 실제 KIS 경로를 탄다. 빈 목록 = 크레딧 0 → 이 파일의 기대값(`[3, 2]`)은 불변.
    from src.api import balance as _balance_mod
    mocks.get_daily_orders = AsyncMock(return_value=[])
    monkeypatch.setattr(_balance_mod, "get_daily_orders", mocks.get_daily_orders)
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
    async def test_partial_lock_with_accurate_position_sells_unlocked_remainder(
        self, engine, registry, mock_env, monkeypatch, caplog,
    ):
        """C236-F1 + cycle385 부록 R-2(F-3) — held == positions(정확)인데 sellable 만 작으면
        **잠김이지 오염이 아니다** → 하향 보정 금지는 그대로.

        기대값 변경(R-10, 사유 = 사용자 전제 「잔여보유수량에 대한 추가매도가 가능하도록」):
        예전 계약은 「보존 + 중단(place 1회)」 이었다 — 그 동안 안 잠긴 1주의 손절이 걸린 외부
        주문이 끝날 때까지 멈췄다. 이제 `fire = sellable − (held − positions) = 1` 을 판다
        (place `[3, 1]`). 추적은 3 그대로 · DB 보정 0 · `_selling` 유지(우리 1주 주문이 걸림).
        """
        import src.engine.order_engine as _oe
        _patch_balance(monkeypatch, quantity=3, sellable=1)
        calls: list[int] = []

        async def _place(*, ticker, side, quantity, price, order_division, exchange):
            calls.append(quantity)
            if len(calls) == 1:
                raise _qty_exceeded_error()
            return OrderResult(order_no="S003", org_no="1", order_time="150001")

        monkeypatch.setattr(_oe, "place_order", _place)
        strat = registry.get("volatility_breakout")
        with caplog.at_level(logging.WARNING):
            await engine.execute_sell("257720", Signal.FORCE_CLEAR,
                                      "volatility_breakout")
        assert calls == [3, 1], f"안 잠긴 잔여 1주를 팔지 않았다: {calls}"
        assert strat.state.positions["257720"].quantity == 3  # 하향 보정 금지
        assert mock_env.save_position.await_count == 0
        assert any("[sell_qty_partial_sellable]" in r.message for r in caplog.records)
        assert "257720" in engine._selling  # 우리 주문이 걸렸다
        assert "257720" not in engine._selling_locked_wait

    @pytest.mark.asyncio
    async def test_partial_lock_covered_by_surplus_is_preserved_and_frozen(
        self, engine, registry, mock_env, monkeypatch, caplog,
    ):
        """C236-F1 원 계약(cycle385 부록 R-2 뒤) — held 5 · sellable 1 · positions 3 →
        `fire = 1 − (5 − 3) = −1` = 걸린 매도를 운영자 초과분이 덮는다 → 보정 없이 보존 + 중단
        (place 1회) + `_selling` 유지 + 동결 표식. 운영자 몫을 우리가 팔지 않는다(R-INV-2).
        """
        import src.engine.order_engine as _oe
        _patch_balance(monkeypatch, quantity=5, sellable=1)
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
        assert "257720" in engine._selling_locked_wait

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
        # cycle385 부록 R2-5 · R3 K3 — 동결 표식 = 우리 `execute_sell` 이 주문 없이 멈춰 세운
        # `_selling` 이라는 표시. 주문 종료는 표식과 무관하게 `_selling` 을 풀고(R2-2), 표식은
        # 지키던 보유가 닫힐 때(R2-5)와 원주문 취소 뒤 재주문이 안 걸렸을 때(R3 K3 — 손님 manual
        # 포함) 푸는 근거다.
        assert "257720" in engine._selling_locked_wait

    @pytest.mark.asyncio
    async def test_zero_holding_falls_to_insufficient_path(
        self, engine, registry, mock_env, monkeypatch,
    ):
        """실보유 0 → D1 안A(cycle429, 사용자 승인 2026-10-10) 통합 판정 위임.

        D1 이전에는 자동 삭제(기존 insufficient 경로) 였다. 이제는 자동
        삭제 경로가 없다 — `get_daily_orders` 가 빈 목록(설명 안 됨)이라
        포지션 보존 + `_selling` 해제 + 5분 진입 차단으로 끝난다.
        """
        import src.engine.order_engine as _oe
        _patch_balance(monkeypatch, quantity=0, sellable=0)
        place = AsyncMock(side_effect=_qty_exceeded_error())
        monkeypatch.setattr(_oe, "place_order", place)
        strat = registry.get("volatility_breakout")
        await engine.execute_sell("257720", Signal.FORCE_CLEAR,
                                  "volatility_breakout")
        assert place.await_count == 1
        assert "257720" in strat.state.positions  # D1 안A — 자동 삭제 없음
        assert mock_env.delete_position.await_count == 0
        assert "257720" not in engine._selling
        assert "257720" in engine._sell_rejection._blocked_until

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
        """R6 → cycle429(D1 안A, 사용자 승인 2026-10-10) 로 재조준.

        APBK1234 는 여전히 즉시 재시도 중단(place 1회)이지만, 삭제 대신
        보존 + 통합 판정(설명 안 됨 → `_selling` 해제 + 5분 진입 차단)으로
        끝난다. `mock_env` 가 `get_daily_orders` 를 빈 목록으로 패치한다.
        """
        import src.engine.order_engine as _oe
        _patch_balance(monkeypatch, quantity=0, sellable=0)
        place = AsyncMock(side_effect=_insufficient_error())
        monkeypatch.setattr(_oe, "place_order", place)
        strat = registry.get("volatility_breakout")
        await engine.execute_sell("257720", Signal.FORCE_CLEAR,
                                  "volatility_breakout")
        assert place.await_count == 1
        assert "257720" in strat.state.positions  # D1 안A — 자동 삭제 없음
        assert "257720" not in engine._selling
        assert "257720" in engine._sell_rejection._blocked_until
