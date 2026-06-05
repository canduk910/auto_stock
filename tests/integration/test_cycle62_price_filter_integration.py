"""사이클 62 (2026-06-05) Red — I 카테고리: 가격 필터 통합 시나리오 (5 케이스).

> **선행 명세**: `_workspace/red/cycle62_price_filter.md` (§I)
> **설계 카드**: §5.2 백엔드 integration 5 케이스

요구 행위 (Red 단계 모두 ImportError / AttributeError / 404 정답):

I-1: mode=HARD + 범위 외 매수 신호 → 매수 차단 + 로그 INSERT (E2E)
I-2: PUT /api/system/price-filter → 60s 내 다음 매수 신호 반영 (즉시 invalidate)
I-3: 보유 손절 정상 (필터 무관 — Q3 통합 검증, 사이클 38 명문화)
I-4: 익일청산 정상 (필터 무관)
I-5: mode 변경 race (HARD → OFF 도중 매수 신호)

MEDIUM 우선 케이스: I-2 / I-5 (race).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


def _make_risk_manager_with_strategy(strategy_id="momentum", has_position=False):
    from src.engine.order_engine import OrderEngine
    from src.engine.risk import RiskManager
    from src.engine.strategy_base import Position, Signal
    from src.engine.strategy_registry import StrategyRegistry

    registry = StrategyRegistry()
    order_engine = MagicMock(spec=OrderEngine)
    order_engine.execute_buy = AsyncMock()
    order_engine.execute_sell = AsyncMock()
    order_engine._selling = set()
    rm = RiskManager(registry=registry, order_engine=order_engine)

    strat = MagicMock()
    strat.strategy_id = strategy_id
    strat.config = MagicMock(params={})

    state = MagicMock()
    if has_position:
        pos = Position(
            ticker="005930", buy_price=50_000, quantity=10,
            order_no="A001", strategy_id=strategy_id, buy_date="2026-06-04",
        )
        state.has_position = MagicMock(return_value=True)
        state.positions = {"005930": pos}
    else:
        state.has_position = MagicMock(return_value=False)
        state.positions = {}
    state.buy_disabled = False
    state.is_low_funds_blocked = MagicMock(return_value=False)
    state.total_investment = 100_000_000
    state.signal_count_today = 0
    strat.state = state
    strat.is_daily_loss_exceeded = MagicMock(return_value=False)
    strat.check_buy_signal = MagicMock(return_value=Signal.BUY)
    strat.check_exit_signal = MagicMock(
        return_value=Signal.STOP_LOSS if has_position else Signal.NONE,
    )

    registry.enabled = MagicMock(return_value=[strat])
    registry.is_ticker_blocked_for_buy = MagicMock(return_value=False)
    return rm, registry, order_engine, strat


def _patch_common_guards(monkeypatch):
    from src.engine.market_regime import BuyBlockState

    monkeypatch.setattr(
        "src.engine.risk.session_tracker.is_tradable", MagicMock(return_value=True),
    )
    monkeypatch.setattr(
        "src.engine.risk.get_current_regime",
        lambda: MagicMock(
            get_buy_block_state=AsyncMock(
                return_value=BuyBlockState(
                    mode="OFF", blocked=False, soft_multiplier=1.0, reasons=[],
                ),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# I-1: E2E — HARD + 범위 외 매수 신호 → 차단 + 로그 INSERT
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_I1_hard_blocks_buy_with_db_log(monkeypatch):
    """I-1: momentum 매수 신호 + HARD 필터 + ref_price 범위 외 → 매수 차단 + system_logs INSERT.

    E2E — DB 헬퍼 → RiskManager 캐시 → on_tick → emit → write_log fire-and-forget.
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner

    rm, registry, order_engine, _strat = _make_risk_manager_with_strategy()
    _patch_common_guards(monkeypatch)

    pf = PriceFilter(min_price=5000, max_price=0, mode="HARD")
    monkeypatch.setattr(
        rm, "_get_price_filter_cached", AsyncMock(return_value=pf), raising=False,
    )
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 3000})

    write_log_mock = AsyncMock()
    with patch("src.db.system_logs.write_log", write_log_mock):
        await rm.on_tick("005930", current_price=3000, open_price=2900, change_rate=3.0)

    # 매수 차단 (E2E 검증)
    order_engine.execute_buy.assert_not_called()
    # DB 로그 INSERT 호출 (fire-and-forget, 최소 1회)
    # write_log mock 호출 검증 — `[price_filter_skip]` 메시지 포함
    skip_log_calls = [
        c for c in write_log_mock.call_args_list
        if any("[price_filter_skip]" in str(a) for a in c.args)
    ]
    assert len(skip_log_calls) >= 1, "[price_filter_skip] DB INSERT 누락"


# ---------------------------------------------------------------------------
# I-2: Settings PUT → 60s 내 다음 매수 신호 반영 (즉시 invalidate)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_I2_settings_put_invalidates_cache_immediately(monkeypatch):
    """I-2: Settings PUT 후 `invalidate_price_filter_cache()` 호출 → 다음 on_tick 즉시 새 값 반영.

    Q5 자문 — 즉시 + 60s TTL + 5분 grace 금지.
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner

    rm, registry, order_engine, _strat = _make_risk_manager_with_strategy()
    _patch_common_guards(monkeypatch)

    # 초기: HARD min=5000 차단 → 다음 PUT 후 OFF 즉시 반영
    pf1 = PriceFilter(min_price=5000, max_price=0, mode="HARD")
    pf2 = PriceFilter(min_price=0, max_price=0, mode="OFF")

    db_get = AsyncMock(side_effect=[pf1, pf2])

    with patch("src.engine.risk.get_price_filter", db_get):
        # 1차 호출 (HARD)
        monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 3000})
        await rm.on_tick("005930", current_price=3000, open_price=2900, change_rate=3.0)
        assert order_engine.execute_buy.call_count == 0  # HARD 차단

        # Settings PUT 시뮬레이션 — invalidate
        rm.invalidate_price_filter_cache()

        # 2차 호출 (OFF) — 즉시 반영
        await rm.on_tick("005930", current_price=3000, open_price=2900, change_rate=3.0)
        # OFF → 매수 진행
        assert order_engine.execute_buy.call_count == 1, (
            "Settings PUT 직후 OFF 즉시 반영 실패 — Q5 자문 위반 (5분 grace 금지)"
        )


# ---------------------------------------------------------------------------
# I-3: 보유 손절 정상 (필터 무관)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_I3_stop_loss_works_with_active_filter(monkeypatch):
    """I-3: 보유 종목 + HARD 필터 활성 + 가격 폭락 → 손절 정상 (필터 영향 0).

    사이클 38 명문화 통합 검증.
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner
    from src.engine.strategy_base import Signal

    rm, registry, order_engine, _strat = _make_risk_manager_with_strategy(
        has_position=True,
    )
    _patch_common_guards(monkeypatch)

    pf = PriceFilter(min_price=10_000, max_price=0, mode="HARD")
    monkeypatch.setattr(
        rm, "_get_price_filter_cached", AsyncMock(return_value=pf), raising=False,
    )
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 50_000})

    await rm.on_tick("005930", current_price=3000, open_price=49_000, change_rate=-90.0)

    # 손절 발화
    order_engine.execute_sell.assert_called_once()
    args = order_engine.execute_sell.call_args.args
    assert args[1] == Signal.STOP_LOSS


# ---------------------------------------------------------------------------
# I-4: 익일청산 정상 (필터 무관)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_I4_next_day_clear_independent_of_filter():
    """I-4: scheduler 의 `_drain_pending_next_day_clear` 와 `_execute_next_day_clear` 가
    가격 필터 메서드를 호출하지 않음을 정적으로 검증.

    사이클 38 명문화 통합 검증 (scheduler 영역).
    """
    import inspect

    from src.engine import scheduler

    src_drain = inspect.getsource(scheduler.TradingScheduler._drain_pending_next_day_clear)
    src_exec = inspect.getsource(scheduler.TradingScheduler._execute_next_day_clear)

    # 가격 필터 4종 메서드 미참조
    for src in (src_drain, src_exec):
        for forbidden in (
            "_get_price_filter_cached",
            "invalidate_price_filter_cache",
            "_emit_price_filter_skip",
            "_emit_price_filter_warn",
        ):
            assert forbidden not in src, (
                f"scheduler next_day_clear 흐름에서 {forbidden} 참조 — "
                "사이클 38 명문화 위반 (익일청산 영향 0 의무)"
            )


# ---------------------------------------------------------------------------
# I-5: mode 변경 race (HARD → OFF 즉시 전환)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_I5_mode_change_race_immediate_apply(monkeypatch):
    """I-5: HARD 운영 중 OFF 전환 invalidate 직후 즉시 반영 (5분 grace 금지).

    동일 sync 흐름에서 차단 → invalidate → 즉시 허용 검증.
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner

    rm, registry, order_engine, _strat = _make_risk_manager_with_strategy()
    _patch_common_guards(monkeypatch)

    pf_hard = PriceFilter(min_price=10_000, max_price=0, mode="HARD")
    pf_off = PriceFilter(min_price=0, max_price=0, mode="OFF")

    # 시퀀스: HARD → invalidate → OFF
    db_get = AsyncMock(side_effect=[pf_hard, pf_off])
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 3000})

    with patch("src.engine.risk.get_price_filter", db_get):
        # 1차: HARD → 차단
        await rm.on_tick("005930", current_price=3000, open_price=2900, change_rate=3.0)
        assert order_engine.execute_buy.call_count == 0

        # Settings 토글 race — 동일 1초 내 invalidate
        rm.invalidate_price_filter_cache()

        # 2차: OFF 즉시 반영
        await rm.on_tick("005930", current_price=3000, open_price=2900, change_rate=3.0)
        assert order_engine.execute_buy.call_count == 1
