"""전략 레지스트리.

전략의 등록/조회/비중 관리/전략 간 중복 매수 방지를 담당한다.
"""

from __future__ import annotations

import logging

from src.engine.strategy_base import StrategyBase

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """전략 등록/조회/비중 관리."""

    def __init__(self):
        self._strategies: dict[str, StrategyBase] = {}

    def register(self, strategy: StrategyBase) -> None:
        self._strategies[strategy.strategy_id] = strategy
        logger.info("전략 등록: %s (%s) 비중=%.0f%%",
                     strategy.config.name, strategy.strategy_id,
                     strategy.config.weight * 100)

    def get(self, strategy_id: str) -> StrategyBase | None:
        return self._strategies.get(strategy_id)

    def all(self) -> list[StrategyBase]:
        return list(self._strategies.values())

    def enabled(self) -> list[StrategyBase]:
        return [s for s in self._strategies.values() if s.config.enabled]

    def allocate_funds(self, total_asset: int) -> None:
        """총 자산을 전략별 비중에 따라 분배한다."""
        enabled = self.enabled()
        total_weight = sum(s.config.weight for s in enabled)
        for s in enabled:
            ratio = s.config.weight / total_weight if total_weight > 0 else 0
            s.state.total_investment = int(total_asset * ratio)
            logger.info("자금 분배: %s → %s원 (%.0f%%)",
                         s.config.name, f"{s.state.total_investment:,}",
                         ratio * 100)

    def update_weights(self, weights: dict[str, float]) -> None:
        """전략별 비중을 업데이트한다. 비중 > 0이면 자동 활성화, 0이면 비활성화."""
        for sid, weight in weights.items():
            s = self._strategies.get(sid)
            if s:
                s.config.weight = weight
                was_enabled = s.config.enabled
                s.config.enabled = weight > 0
                if s.config.enabled != was_enabled:
                    logger.info("전략 %s: %s → %s",
                                s.config.name,
                                "활성" if was_enabled else "비활성",
                                "활성" if s.config.enabled else "비활성")
                logger.info("비중 변경: %s → %.0f%%", s.config.name, weight * 100)

    def find_strategy_for_ticker(self, ticker: str) -> StrategyBase | None:
        """특정 종목을 보유 중인 전략을 찾는다."""
        for s in self._strategies.values():
            if s.state.has_position(ticker):
                return s
        return None

    def is_ticker_held_by_any(self, ticker: str) -> bool:
        """어떤 전략이든 해당 종목을 보유 또는 주문 중인지 확인한다."""
        for s in self._strategies.values():
            if s.state.has_position(ticker) or s.state.is_buy_pending(ticker):
                return True
        return False

    def is_ticker_sold_today_by_any(self, ticker: str) -> bool:
        """어떤 전략이든 당일 해당 종목을 매도했는지 확인한다.

        한 전략이 매도한 종목을 다른 전략이 같은 날 재매수하는 것을 차단.
        """
        for s in self._strategies.values():
            if s.state.is_sold_today(ticker):
                return True
        return False

    def is_ticker_blocked_for_buy(self, ticker: str) -> bool:
        """매수 차단 통합 가드 — 모든 전략을 가로질러 검사한다.

        다음 중 하나라도 해당하면 매수 차단:
        - 어떤 전략이든 보유 중 (has_position)
        - 어떤 전략이든 매수 주문 진행 중 (is_buy_pending)
        - 어떤 전략이든 당일 매도 완료 (is_sold_today)
        """
        for s in self._strategies.values():
            st = s.state
            if st.has_position(ticker) or st.is_buy_pending(ticker) or st.is_sold_today(ticker):
                return True
        return False

    def get_strategies_status(self) -> dict:
        """전략별 상태를 반환한다."""
        from src.engine.scanner import ticker_names

        total_asset = sum(s.state.total_investment for s in self._strategies.values())

        result = {}
        for sid, s in self._strategies.items():
            positions_detail = {}
            for ticker, pos in s.state.positions.items():
                positions_detail[ticker] = {
                    "name": ticker_names.get(ticker, ""),
                    "buy_price": pos.buy_price,
                    "quantity": pos.quantity,
                    "high_since_buy": pos.high_since_buy,
                    "buy_date": pos.buy_date.isoformat(),
                    "is_next_day": pos.is_next_day,
                }

            # 전략별 스캔 종목 (있는 경우)
            scanned = []
            if hasattr(s, 'get_scanned_tickers'):
                scanned = s.get_scanned_tickers()

            # VB 타겟 데이터 (있는 경우)
            targets = {}
            if hasattr(s, 'get_targets_status'):
                targets = s.get_targets_status()

            # 단계별 스캔 통계 (있는 경우 — donchian_swing)
            scan_stats = None
            if hasattr(s, 'get_scan_stats'):
                scan_stats = s.get_scan_stats()

            # 사이클 18 (2026-05-19, C-1) — 전략별 `tradable_boards` 최상위 노출.
            # 프론트 ScanMonitor 가 활성 보드 ∩ tradable_boards = ∅ 시 "돌파 (대기 — 보드)" 라벨.
            # 우선순위: DB strategy_config.params["tradable_boards"] > 전략 클래스 DEFAULT_TRADABLE_BOARDS
            params_boards = s.config.params.get("tradable_boards")
            if isinstance(params_boards, (list, tuple)) and params_boards:
                tradable_boards = list(params_boards)
            elif hasattr(s, "DEFAULT_TRADABLE_BOARDS"):
                tradable_boards = list(s.DEFAULT_TRADABLE_BOARDS)
            else:
                tradable_boards = []

            result[sid] = {
                "name": s.config.name,
                "enabled": s.config.enabled,
                "weight": s.config.weight,
                "params": s.config.params,
                "tradable_boards": tradable_boards,
                "positions": len(s.state.positions),
                "pending_buys": len(s.state.pending_buys),
                "position_tickers": list(s.state.positions.keys()),
                "total_investment": s.state.total_investment,
                "daily_realized_pnl": s.state.daily_realized_pnl,
                "buy_disabled": s.state.buy_disabled,
                "buy_signals": s.state.buy_signals[-10:],
                "positions_detail": positions_detail,
                "pending_buy_tickers": list(s.state.pending_buys),
                "scanned_tickers": scanned,
                "scanned_count": len(scanned),
                "targets": targets,
                "scan_stats": scan_stats,
                "invested_amount": sum(
                    pos.buy_price * pos.quantity for pos in s.state.positions.values()
                ),
                "min_weight": round(
                    sum(pos.buy_price * pos.quantity for pos in s.state.positions.values())
                    / total_asset * 100
                ) if total_asset > 0 and s.state.positions else 0,
            }
        return result
