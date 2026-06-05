"""사이클 62 (2026-06-05) Red — E 카테고리: 매도 무영향 (4 케이스, 사이클 38 명문화 영속).

> **선행 명세**: `_workspace/red/cycle62_price_filter.md` (§E)
> **설계 카드**: §2.4 Q3 시장가 폴백 회귀 가드
> **CLAUDE.md 절대 규칙**: "**`tradable_boards` 는 매수 진입 전용** (사이클 38, 2026-05-22 명문화)"

요구 행위:

E-1: 보유 종목 가격 변동 + 필터 범위 외 → 손절/Trailing 등 매도 가드 정상 작동
E-2: 익일청산 (`_pending_next_day_clear`) 작동 (필터 무관 — scheduler 별도 경로)
E-3: 매도 분기 진입 — execute_sell 호출 검증 (가격 필터 미평가)
E-4: **시장가 거부 5호가 폴백 시 가격 필터 재평가 금지** (Q3 자문, AST 정적 검증)

E-4 의 의미: `order_engine.py` 의 매수/매도 시장가 폴백 흐름 (L411 step_up / L676 step_down)
에서 `risk_manager._get_price_filter_cached` / `get_price_filter` 호출이 정적으로 0건.
폴백은 *체결 가격 변경* — 필터 재평가 시 매도 차단 위험 (사이클 38 명문화 위반).

회귀 가드:
- 사이클 38 명문화 영속 검증
- order_engine 폴백 흐름이 RiskManager 의 가격 필터 메서드를 import/호출하지 않음
"""
from __future__ import annotations

import ast
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_risk_manager():
    from src.engine.order_engine import OrderEngine
    from src.engine.risk import RiskManager
    from src.engine.strategy_registry import StrategyRegistry

    registry = StrategyRegistry()
    order_engine = MagicMock(spec=OrderEngine)
    order_engine.execute_buy = AsyncMock()
    order_engine.execute_sell = AsyncMock()
    order_engine._selling = set()
    rm = RiskManager(registry=registry, order_engine=order_engine)
    return rm, registry, order_engine


def _make_strategy_with_position(ticker="005930", strategy_id="momentum"):
    from src.engine.strategy_base import Position, Signal

    strat = MagicMock()
    strat.strategy_id = strategy_id
    strat.config = MagicMock(params={})
    pos = Position(
        ticker=ticker, buy_price=50_000, quantity=10,
        order_no="A001", strategy_id=strategy_id, buy_date="2026-06-04",
    )
    state = MagicMock()
    state.has_position = MagicMock(return_value=True)
    state.positions = {ticker: pos}
    state.buy_disabled = False
    state.total_investment = 100_000_000
    state.is_low_funds_blocked = MagicMock(return_value=False)
    state.signal_count_today = 0
    strat.state = state
    strat.is_daily_loss_exceeded = MagicMock(return_value=False)
    strat.check_buy_signal = MagicMock(return_value=Signal.NONE)
    strat.check_exit_signal = MagicMock(return_value=Signal.STOP_LOSS)
    return strat


def _patch_common(monkeypatch):
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
# E-1: 보유 종목 범위 외 가격 변동 → 손절 정상
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_E1_stop_loss_works_with_active_price_filter(monkeypatch):
    """E-1: 보유 종목 + 필터 HARD min=10_000 + 가격 폭락 3,000원 → 손절 정상 발화.

    사이클 38 명문화 — 매도 가드는 필터 무관.
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner
    from src.engine.strategy_base import Signal

    rm, registry, order_engine = _make_risk_manager()
    strat = _make_strategy_with_position("005930", "momentum")
    monkeypatch.setattr(registry, "enabled", MagicMock(return_value=[strat]))
    _patch_common(monkeypatch)

    pf_hard = PriceFilter(min_price=10_000, max_price=0, mode="HARD")
    monkeypatch.setattr(
        rm, "_get_price_filter_cached", AsyncMock(return_value=pf_hard), raising=False,
    )
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 50_000})

    # 가격 3,000원 (필터 범위 외) + 손절 신호
    await rm.on_tick("005930", current_price=3000, open_price=49_000, change_rate=-90.0)

    # 손절 정상 발화 (필터 무관)
    order_engine.execute_sell.assert_called_once()
    args = order_engine.execute_sell.call_args.args
    assert args[1] == Signal.STOP_LOSS


# ---------------------------------------------------------------------------
# E-2: 익일청산 흐름 무영향
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_E2_next_day_clear_unaffected_by_price_filter(monkeypatch):
    """E-2: 익일청산 흐름은 scheduler 별도 경로 (`_execute_next_day_clear`) — risk.on_tick
    의 가격 필터 분기 무관.

    `_pending_next_day_clear` 종목은 scheduler `_drain_pending_next_day_clear` 가 KRX
    시장가 일괄 청산 — risk_manager 미경유.
    """
    # scheduler 의 next_day_clear 흐름에 risk_manager 참조가 정적으로 없음을 검증
    from src.engine import scheduler

    source = inspect.getsource(scheduler.TradingScheduler._drain_pending_next_day_clear)
    # 가격 필터 헬퍼 명 4 종 모두 미참조
    assert "_get_price_filter_cached" not in source, (
        "_drain_pending_next_day_clear 에서 가격 필터 평가 — 사이클 38 명문화 위반"
    )
    assert "get_price_filter" not in source, (
        "_drain_pending_next_day_clear 에서 DB 필터 조회 — 사이클 38 명문화 위반"
    )

    source_exec = inspect.getsource(scheduler.TradingScheduler._execute_next_day_clear)
    assert "_get_price_filter_cached" not in source_exec
    assert "get_price_filter" not in source_exec


# ---------------------------------------------------------------------------
# E-3: 매도 분기 진입 시 execute_sell 호출 (가격 필터 미평가)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_E3_execute_sell_called_without_filter_evaluation(monkeypatch):
    """E-3: 매도 분기 진입 시 `_get_price_filter_cached` 호출 0건 (`check_exit_signal`
    분기 *후* 진입 보존).

    구현 분기 위치 의무: 가격 필터 가드는 `if state.has_position` *아래* 또는 *후* 가 아니라
    `for strategy:` 루프 안쪽의 매수 평가 *직전* 위치에 진입해야 한다. 보유 종목은 매수
    분기 도달 *전* `continue` 또는 매도 후 break 되어야 한다.
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner

    rm, registry, order_engine = _make_risk_manager()
    strat = _make_strategy_with_position("005930", "momentum")
    monkeypatch.setattr(registry, "enabled", MagicMock(return_value=[strat]))
    _patch_common(monkeypatch)

    pf_hard = PriceFilter(min_price=10_000, max_price=0, mode="HARD")
    cache_mock = AsyncMock(return_value=pf_hard)
    monkeypatch.setattr(rm, "_get_price_filter_cached", cache_mock, raising=False)
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 50_000})

    await rm.on_tick("005930", current_price=3000, open_price=49_000, change_rate=-90.0)

    # 매도 발화 + 매수 차단
    order_engine.execute_sell.assert_called_once()
    order_engine.execute_buy.assert_not_called()
    # 가격 필터 캐시 호출 0건 (매도 분기에서 진입 안 함, 매수 분기 진입 전 continue)
    # 또는 1건 (매수 분기 진입 시도 후 보유 가드로 차단) — 허용
    assert cache_mock.call_count <= 1, (
        f"매도 발화 시점에 가격 필터 캐시 과다 호출 ({cache_mock.call_count}회) "
        "— 사이클 38 매도 흐름 영향 0 보호"
    )


# ---------------------------------------------------------------------------
# E-4: Q3 시장가 거부 5호가 폴백 시 가격 필터 재평가 금지 (AST 정적 검증)
# ---------------------------------------------------------------------------
def test_E4_order_engine_market_fallback_no_price_filter_recheck():
    """E-4 (Q3 자문 +1): `order_engine.py` 의 매수/매도 시장가 거부 폴백 흐름에서
    `risk_manager._get_price_filter_cached` / `get_price_filter` 호출이 정적으로 0건.

    근거: 폴백은 *체결 가격 변경* — 가격 필터 재평가 시 매도 차단 위험 (사이클 38 명문화 위반).
    원 매수 진입 시점에 통과했으면 폴백도 통과 (트레이더 의도 연장).

    AST 검증 — `order_engine.py` 의 import 와 Attribute 접근 모두 가격 필터 메서드 미참조.
    """
    from src.engine import order_engine

    source = inspect.getsource(order_engine)
    tree = ast.parse(source)

    # 1) `from src.db.system_config import get_price_filter` 또는 `set_price_filter` 미존재
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "src.db.system_config":
                imported = [n.name for n in node.names]
                assert "get_price_filter" not in imported, (
                    "order_engine.py 가 get_price_filter import — Q3 자문 위반 "
                    "(폴백 시 가격 필터 재평가 금지)"
                )
                assert "set_price_filter" not in imported

        # 2) `xxx._get_price_filter_cached` / `xxx.invalidate_price_filter_cache` 호출 0건
        if isinstance(node, ast.Attribute):
            assert node.attr != "_get_price_filter_cached", (
                "order_engine.py 가 _get_price_filter_cached 호출 — Q3 자문 위반"
            )
            assert node.attr != "invalidate_price_filter_cache"
            assert node.attr != "_emit_price_filter_skip"
            assert node.attr != "_emit_price_filter_warn"

    # 3) 문자열 기반 추가 안전망 — 어떤 형태로도 import / 호출 0건
    assert "_get_price_filter_cached" not in source, (
        "order_engine.py 에 _get_price_filter_cached 문자열 등장 — Q3 자문 위반"
    )
    assert "get_price_filter" not in source or "get_price_filter_cached" in source, (
        # `_get_price_filter_cached` 단어 안에 포함되는 경우만 허용 (`is in` 미허용)
        "order_engine.py 에 get_price_filter (헬퍼) 단독 등장 — Q3 자문 위반"
    )
