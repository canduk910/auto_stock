"""cycle429 — D1 안A (사용자 승인 2026-10-10): 수량 부족 거부(APBK1234·APBK0400
실보유 0) 자동 삭제 경로 폐지 + 통보 대기/보존 통합 판정.

자문 = `_workspace/domain_consult/2026-10-10_d1_insufficient_qty_position_delete.md`.
회귀 시나리오(Q4) S1~S12 를 고정한다. 명세 요지:

1. `_sell_orders_snapshot`(TTTC0081R) 로 「거래소는 체결, 통보는 아직」 수량
   (`pending`)을 센다.
2. `pending > 0`(전부·일부 설명됨) 이면 지우지 않고 `_selling_locked_wait` 로
   통보를 기다린다(`_selling` 유지, TTL 등록 없음).
3. 설명 안 됨(`pending == 0`) 또는 조회 실패(`fills is None`) 면 포지션을
   **보존**하고 `_selling` 을 풀고 5분 진입 차단(`SellRejectionTracker
   .register_insufficient_quantity`)을 건 뒤 `[sell_insufficient_unexplained]`
   를 남긴다(그날 같은 종목 3회째부터 CRITICAL). 잔고 1회 조회는 관측 전용.
4. 자동 삭제 경로는 없다 — 포지션을 지우는 길은 체결통보 보유 축
   (`_handle_sell_fill`) · 재기동 복구 · 사람 셋뿐이다.

🔴 벽시계 금지 — 전부 freezegun 으로 고정한다(장중 10:30 · 15:20:05 · 애프터
16:05). caplog 단언은 WARNING 이상 + 마커 prefix 로 한정한다.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.api.base import KisApiError
from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.order import OrderResult

pytestmark = pytest.mark.unit

TICKER = "257720"
_OE_LOGGER = "src.engine.order_engine"


def _insufficient_error(msg_cd: str = "APBK1234") -> KisApiError:
    """APBK1234(진짜 보유 부족) — `is_sell_qty_exceeded` 에 안 걸리는 코드."""
    return KisApiError(rt_cd="1", msg_cd=msg_cd, msg1="매도가능수량이 부족합니다.")


def _qty_exceeded_error() -> KisApiError:
    """APBK0400 "수량 초과" — `elif sellable == 0 and held_qty == 0` 분기 유도용."""
    return KisApiError(rt_cd="1", msg_cd="APBK0400", msg1="주문 가능한 수량을 초과했습니다.")


def _row(odno: str, qty: int, *, pdno: str = TICKER, dvsn: str = "01") -> dict:
    return {
        "odno": odno, "pdno": pdno, "sll_buy_dvsn_cd": dvsn,
        "tot_ccld_qty": str(qty),
    }


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
    strat.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=51_000, quantity=3,
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
    """DB/로그/거래소 라우팅 격리 (cycle236 패턴과 동일)."""
    import src.engine.order_engine as _oe
    import src.db.positions as _positions

    mocks = SimpleNamespace(
        insert_trade=AsyncMock(return_value=None),
        write_log=AsyncMock(return_value=None),
        update_trade_status=AsyncMock(return_value=1),
        delete_position=AsyncMock(return_value=None),
        save_position=AsyncMock(return_value=None),
        unsubscribe=AsyncMock(return_value=None),
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
    monkeypatch.setattr(
        "src.engine.order_engine.OrderEngine._unsubscribe_if_no_other_strategy",
        mocks.unsubscribe,
    )
    from src.api import balance as _balance_mod
    mocks.get_daily_orders = AsyncMock(return_value=[])
    monkeypatch.setattr(_balance_mod, "get_daily_orders", mocks.get_daily_orders)
    mocks.get_balance = AsyncMock(return_value=([], SimpleNamespace(net_asset=0)))
    monkeypatch.setattr(_balance_mod, "get_balance", mocks.get_balance)
    return mocks


def _warn_or_error_lines(caplog) -> list[str]:
    return [
        r.message for r in caplog.records
        if r.levelno >= logging.WARNING and r.name == _OE_LOGGER
    ]


# ═══════════════════════════════════════════════════════════════════════════
# S1 — 사람 MTS 전량 매도 체결 → 통보 처리 후 우리 손절 (거부 자체가 안 남)
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@freeze_time("2026-10-13 10:30:00", tz_offset=-9)
async def test_s1_normal_fill_notice_closes_without_any_rejection(
    engine, registry, mock_env,
):
    """보유 축이 통보로 이미 닫히면 수량 부족 거부 분기는 아예 안 탄다.

    `_handle_sell_insufficient_quantity` 가 호출되지 않으므로 tracker 에
    아무것도 등록되지 않는다 — D1 분기의 전제(「체결통보가 먼저 닫으면
    거부가 안 남는다」)를 확인하는 양성 대조군.
    """
    await engine.handle_execution_notice(TICKER, "0000411400", "SELL", 51_500, 3)

    strat = registry.get("volatility_breakout")
    assert TICKER not in strat.state.positions
    assert TICKER not in engine._sell_rejection._blocked_until
    assert TICKER not in engine._selling_locked_wait


# ═══════════════════════════════════════════════════════════════════════════
# S2 — 사람 MTS 매도 체결, 통보 유실 → 우리 손절이 수량 부족(APBK1234)
# 기대: TTTC0081R pending_dec=전량 → 통보 대기, 삭제 0
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@freeze_time("2026-10-13 10:30:00", tz_offset=-9)
async def test_s2_fully_explained_fill_waits_for_notice_no_delete(
    engine, registry, mock_env, monkeypatch, caplog,
):
    engine._sell_ledger_since = engine._sell_ledger_since - timedelta(hours=1)
    mock_env.get_daily_orders.return_value = [_row("MTS-1", 3)]
    place = AsyncMock(side_effect=_insufficient_error())
    monkeypatch.setattr("src.engine.order_engine.place_order", place)

    with caplog.at_level(logging.WARNING, logger=_OE_LOGGER):
        await engine.execute_sell(TICKER, Signal.STOP_LOSS, "volatility_breakout")

    strat = registry.get("volatility_breakout")
    assert place.await_count == 1
    assert TICKER in strat.state.positions, "통보 대기 — 삭제 금지"
    assert strat.state.positions[TICKER].quantity == 3, "pos.quantity 직접 감산 금지"
    assert TICKER in engine._selling_locked_wait
    assert TICKER in engine._selling, "통보 대기 중엔 _selling 유지"
    assert TICKER not in engine._sell_rejection._blocked_until, "대기는 거부가 아니라 TTL 없음"
    assert mock_env.delete_position.await_count == 0
    assert any("[sell_qty_unnoticed_fills]" in m for m in _warn_or_error_lines(caplog))


# ═══════════════════════════════════════════════════════════════════════════
# S3 — 우리 직전 매도 체결, 통보 5초 지연 (15:20 강제청산)
# 기대: 통보 대기 → 늦은 통보가 손익 포함 닫힘·sold_today·구독 해제
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@freeze_time("2026-10-13 15:20:05", tz_offset=-9)
async def test_s3_late_notice_closes_with_pnl_and_unsubscribe(
    engine, registry, mock_env, monkeypatch,
):
    engine._sell_ledger_since = engine._sell_ledger_since - timedelta(hours=1)
    mock_env.get_daily_orders.return_value = [_row("OUR-1", 3)]
    place = AsyncMock(side_effect=_insufficient_error())
    monkeypatch.setattr("src.engine.order_engine.place_order", place)

    await engine.execute_sell(TICKER, Signal.FORCE_CLEAR, "volatility_breakout")

    strat = registry.get("volatility_breakout")
    assert TICKER in strat.state.positions
    assert TICKER in engine._selling_locked_wait

    # 5초 뒤 늦은 체결통보 도착 — 보유 축이 정확히 닫힌다.
    await engine.handle_execution_notice(TICKER, "OUR-1", "SELL", 51_200, 3)

    assert TICKER not in strat.state.positions, "늦은 통보가 보유를 정확히 닫아야 한다"
    assert TICKER in strat.state.sold_today
    assert mock_env.unsubscribe.await_count == 1
    # 손익 포함 — (51200-51000)*3 = 600
    assert strat.state.daily_realized_pnl == 600


# ═══════════════════════════════════════════════════════════════════════════
# S4 — S3 인데 주문 조회 timeout (15:20)
# 기대: 보존 + _selling 해제 + 5분 TTL + ERROR, 삭제 0
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@freeze_time("2026-10-13 15:20:05", tz_offset=-9)
async def test_s4_orders_query_timeout_preserves_and_blocks(
    engine, registry, mock_env, monkeypatch, caplog,
):
    async def _boom(*a, **k):
        raise TimeoutError("KIS down")

    monkeypatch.setattr("src.api.balance.get_daily_orders", _boom)
    place = AsyncMock(side_effect=_insufficient_error())
    monkeypatch.setattr("src.engine.order_engine.place_order", place)

    with caplog.at_level(logging.WARNING, logger=_OE_LOGGER):
        await engine.execute_sell(TICKER, Signal.FORCE_CLEAR, "volatility_breakout")

    strat = registry.get("volatility_breakout")
    assert TICKER in strat.state.positions, "D1 안A — 자동 삭제 없음"
    assert mock_env.delete_position.await_count == 0
    assert TICKER not in engine._selling
    assert TICKER in engine._sell_rejection._blocked_until
    expiry = engine._sell_rejection._blocked_until[TICKER]
    from datetime import datetime, timezone
    now_kst = datetime(2026, 10, 13, 15, 20, 5, tzinfo=timezone(timedelta(hours=9)))
    assert expiry == now_kst + timedelta(minutes=5)
    lines = _warn_or_error_lines(caplog)
    assert any("[sell_insufficient_unexplained]" in m for m in lines)
    error_lines = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("[sell_insufficient_unexplained]" in r.message for r in error_lines)


# ═══════════════════════════════════════════════════════════════════════════
# S5 — 부분 체결 1/3, 통보 전 남은 수량 매도가 거부
# 기대: 통보 대기, pos.quantity 직접 감산 0 (이중 차감 금지)
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@freeze_time("2026-10-13 10:30:00", tz_offset=-9)
async def test_s5_partially_explained_still_waits_no_partial_decrement(
    engine, registry, mock_env, monkeypatch,
):
    engine._sell_ledger_since = engine._sell_ledger_since - timedelta(hours=1)
    # 보유 3주 중 1주만 거래소 체결 확인(통보 미착) — 나머지 2주는 설명 안 됨.
    mock_env.get_daily_orders.return_value = [_row("MTS-1", 1)]
    place = AsyncMock(side_effect=_insufficient_error())
    monkeypatch.setattr("src.engine.order_engine.place_order", place)

    await engine.execute_sell(TICKER, Signal.STOP_LOSS, "volatility_breakout")

    strat = registry.get("volatility_breakout")
    assert TICKER in strat.state.positions
    assert strat.state.positions[TICKER].quantity == 3, "일부 설명도 직접 차감하지 않는다"
    assert TICKER in engine._selling_locked_wait
    assert TICKER not in engine._sell_rejection._blocked_until


# ═══════════════════════════════════════════════════════════════════════════
# S6 — KIS 일시 오판(수량 부족, 실보유 전량·주문내역 0)
# 기대: 보존 + TTL, 잔고 held 를 관측 로그로만 남김
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@freeze_time("2026-10-13 10:30:00", tz_offset=-9)
async def test_s6_kis_false_rejection_preserves_and_logs_held_observationally(
    engine, registry, mock_env, monkeypatch, caplog,
):
    mock_env.get_balance.return_value = (
        [SimpleNamespace(ticker=TICKER, quantity=3, sellable_quantity=3)],
        SimpleNamespace(net_asset=0),
    )
    place = AsyncMock(side_effect=_insufficient_error())
    monkeypatch.setattr("src.engine.order_engine.place_order", place)

    with caplog.at_level(logging.WARNING, logger=_OE_LOGGER):
        await engine.execute_sell(TICKER, Signal.STOP_LOSS, "volatility_breakout")

    strat = registry.get("volatility_breakout")
    assert TICKER in strat.state.positions
    assert mock_env.get_balance.await_count == 1, "관측 전용 1회 조회"
    lines = _warn_or_error_lines(caplog)
    assert any("[sell_insufficient_unexplained]" in m and "held=3" in m for m in lines), lines


# ═══════════════════════════════════════════════════════════════════════════
# S7 — S6 이 TTL 만료 뒤 재발 3회
# 기대: 3회째 CRITICAL, 여전히 삭제 0
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_s7_third_occurrence_same_day_escalates_to_critical(
    engine, registry, mock_env, monkeypatch, caplog,
):
    place = AsyncMock(side_effect=_insufficient_error())
    monkeypatch.setattr("src.engine.order_engine.place_order", place)
    strat = registry.get("volatility_breakout")

    with freeze_time("2026-10-13 10:30:00", tz_offset=-9) as frozen, caplog.at_level(
        logging.WARNING, logger=_OE_LOGGER,
    ):
        for _ in range(3):
            engine._selling.discard(TICKER)
            await engine.execute_sell(TICKER, Signal.STOP_LOSS, "volatility_breakout")
            frozen.tick(delta=timedelta(minutes=6))  # 5분 TTL 만료 뒤 재발(같은 날)

    assert TICKER in strat.state.positions, "3회째도 자동 삭제 없음"
    assert mock_env.delete_position.await_count == 0
    critical_lines = [
        c for c in mock_env.write_log.await_args_list
        if len(c.args) >= 2 and c.args[0] == "CRITICAL"
        and "[sell_insufficient_unexplained]" in str(c.args[1])
    ]
    assert len(critical_lines) == 1, (
        f"3회째만 CRITICAL 이어야 한다(1~2회는 ERROR): {critical_lines}"
    )
    assert "count=3" in str(critical_lines[0].args[1])


# ═══════════════════════════════════════════════════════════════════════════
# S8 — 액면병합으로 수량 변경, 주문내역 0 (개장 직후)
# 기대: 보존 + ERROR(사람 정리), 자동 삭제 0
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@freeze_time("2026-10-13 09:01:00", tz_offset=-9)
async def test_s8_corporate_action_no_order_evidence_preserves_for_human(
    engine, registry, mock_env, monkeypatch, caplog,
):
    """액면병합처럼 주문내역에 흔적이 없는 사건 — 영구 「설명 안 됨」 이 되고
    자동으로 지워지지 않는다(사람이 정리할 때까지)."""
    mock_env.get_daily_orders.return_value = []  # 주문내역 0
    place = AsyncMock(side_effect=_insufficient_error())
    monkeypatch.setattr("src.engine.order_engine.place_order", place)

    with caplog.at_level(logging.WARNING, logger=_OE_LOGGER):
        await engine.execute_sell(TICKER, Signal.STOP_LOSS, "volatility_breakout")

    strat = registry.get("volatility_breakout")
    assert TICKER in strat.state.positions
    assert mock_env.delete_position.await_count == 0
    assert any(
        "[sell_insufficient_unexplained]" in r.message
        for r in caplog.records if r.levelno >= logging.ERROR
    )


# ═══════════════════════════════════════════════════════════════════════════
# S9 — 애프터 44/41 매도가 수량 부족 (16:00~20:00)
# 기대: S2/S4 와 같은 판정(시각 무관), 애프터 TTL 래치와 충돌 없음
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@freeze_time("2026-10-13 16:05:00", tz_offset=-9)
async def test_s9_after_hours_rejection_same_verdict_as_main_hours(
    engine, registry, mock_env, monkeypatch, caplog,
):
    place = AsyncMock(side_effect=_insufficient_error())
    monkeypatch.setattr("src.engine.order_engine.place_order", place)

    with caplog.at_level(logging.WARNING, logger=_OE_LOGGER):
        await engine.execute_sell(TICKER, Signal.FORCE_CLEAR, "volatility_breakout")

    strat = registry.get("volatility_breakout")
    # 시각 무관 — 설명 안 됨(get_daily_orders 기본 []) 판정은 동일하다.
    assert TICKER in strat.state.positions
    assert TICKER not in engine._selling
    assert TICKER in engine._sell_rejection._blocked_until
    # 애프터 전용 TTL 래치(market_closed/market_order_disallowed) 와는 분리된 값 —
    # insufficient_quantity 는 항상 5분이다(NXT 다음 09:00 TTL 과 섞이지 않는다).
    expiry = engine._sell_rejection._blocked_until[TICKER]
    reason = engine._sell_rejection._blocked_reason[TICKER]
    assert reason == "insufficient_quantity"
    assert (expiry - expiry.replace(second=0, microsecond=0)).total_seconds() < 60


# ═══════════════════════════════════════════════════════════════════════════
# S10 — VB 보유가 15:20 에 수량 부족, 실보유 남음
# 기대: 보존 — 오버나잇 시 VB 당일청산 위반이 로그로 드러난다(현행처럼 조용히
# 넘어가지 않는다 — 15분 뒤 `buy_date=오늘` 재채택이 없어졌기 때문).
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@freeze_time("2026-10-13 15:20:05", tz_offset=-9)
async def test_s10_vb_insufficient_at_1520_preserves_position(
    engine, registry, mock_env, monkeypatch,
):
    place = AsyncMock(side_effect=_insufficient_error())
    monkeypatch.setattr("src.engine.order_engine.place_order", place)
    strat = registry.get("volatility_breakout")
    original_buy_date = strat.state.positions[TICKER].buy_date

    await engine.execute_sell(TICKER, Signal.FORCE_CLEAR, "volatility_breakout")

    # D1 이전에는 15분 안에 `_sync_positions_from_balance` 가 `buy_date=오늘` 로
    # 조용히 재채택했다(손절 규약 느슨화가 안 보임, `order_no=""`). 이제는
    # 포지션이 처음부터 지워지지 않으므로 원래 `buy_date`·손절 스탬프가
    # 전혀 손상되지 않고 그대로 보존된다.
    assert TICKER in strat.state.positions
    assert strat.state.positions[TICKER].buy_date == original_buy_date
    assert strat.state.positions[TICKER].order_no == "0000411400"


# ═══════════════════════════════════════════════════════════════════════════
# S11 — 보존 분기에서 구독 해제 호출 0
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@freeze_time("2026-10-13 10:30:00", tz_offset=-9)
async def test_s11_preserve_branch_never_unsubscribes(
    engine, registry, mock_env, monkeypatch,
):
    place = AsyncMock(side_effect=_insufficient_error())
    monkeypatch.setattr("src.engine.order_engine.place_order", place)

    await engine.execute_sell(TICKER, Signal.STOP_LOSS, "volatility_breakout")

    assert mock_env.unsubscribe.await_count == 0, (
        "보존 분기는 구독을 끊지 않는다 — 루트 금기(보유 종목 구독 유지)와 같은 이유"
    )


# ═══════════════════════════════════════════════════════════════════════════
# S12 — 통보 대기 중 180초 안에 통보 없음 → selling_reconcile 이 _selling 해제
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@freeze_time("2026-10-13 10:30:00", tz_offset=-9)
async def test_s12_selling_reconcile_frees_stale_wait_after_180s(
    engine, registry, mock_env, monkeypatch,
):
    engine._sell_ledger_since = engine._sell_ledger_since - timedelta(hours=1)
    mock_env.get_daily_orders.return_value = [_row("MTS-1", 3)]
    place = AsyncMock(side_effect=_insufficient_error())
    monkeypatch.setattr("src.engine.order_engine.place_order", place)

    await engine.execute_sell(TICKER, Signal.STOP_LOSS, "volatility_breakout")
    assert TICKER in engine._selling_locked_wait
    assert TICKER in engine._selling

    # 180초(+ 여유) 지나도 통보가 안 왔다 — `selling_reconcile.reconcile_stale_selling`
    # (15분 재대조와 같은 판정)이 보유 잔존(`held_qty>0`) ∧ 열린 매도주문 없음
    # ∧ aged 조건으로 `_selling` 을 해제한다. 🔴 `held_qty==0`(`held_zero`)은
    # 오히려 유지 사유다(모호성 — #1.5 와 같은 의존, `_stale_selling_verdict`).
    from src.engine.selling_reconcile import reconcile_stale_selling
    engine._selling_since[TICKER] = (
        engine._selling_since[TICKER] - timedelta(seconds=200)
    )
    holdings = [SimpleNamespace(ticker=TICKER, quantity=1)]
    mock_env.get_daily_orders.return_value = []  # 열린 매도주문 없음(no-arg 재조회)
    await reconcile_stale_selling(engine, holdings, min_age_s=180)

    assert TICKER not in engine._selling, "180초 age gate 가 _selling 을 풀어야 한다"
