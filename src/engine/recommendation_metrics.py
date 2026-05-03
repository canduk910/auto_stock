"""파라미터 추천을 위한 전략별 통계 계산 모듈.

trade_history + daily_performance 데이터를 받아
LLM에 넘기기 위한 결정적 통계 dict를 생성한다.
"""

from __future__ import annotations

import logging
import statistics
from typing import Any

logger = logging.getLogger(__name__)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def compute_metrics(
    trades: list[dict],
    performance: list[dict],
    current_params: dict,
) -> dict:
    """전략별 통계 계산.

    반환:
      trades_count, buy_count, sell_count,
      win_count, loss_count, win_rate (0~1),
      avg_profit_pct, avg_loss_pct, max_profit_pct, max_loss_pct,
      stop_loss_hits (params['stop_loss_rate']에 도달한 매도 수),
      total_realized_pnl,
      daily_avg_return, daily_return_std,
      cumulative_return,
      analyzed_days

    Args:
      trades: trade_history rows (ticker, ticker_name, trade_type, price,
              quantity, profit_loss, status, strategy 등)
      performance: daily_performance rows (date, strategy, total_asset,
                   daily_profit_rate)
      current_params: 전략 현재 파라미터 (stop_loss_rate 등 참조)
    """
    buy_count = 0
    sell_count = 0
    closed_sells: list[dict] = []  # COMPLETED|PARTIAL 매도

    for tr in trades:
        ttype = (tr.get("trade_type") or "").upper()
        status = (tr.get("status") or "").upper()
        if ttype == "BUY":
            buy_count += 1
        elif ttype == "SELL":
            sell_count += 1
            if status in ("COMPLETED", "PARTIAL"):
                closed_sells.append(tr)

    # 승/패/평균 손익률 계산 — profit_loss(원)와 매도가x수량으로 % 환산
    win_count = 0
    loss_count = 0
    profit_pcts: list[float] = []
    loss_pcts: list[float] = []

    for tr in closed_sells:
        pnl = _safe_float(tr.get("profit_loss"))
        price = _safe_float(tr.get("price"))
        qty = _safe_float(tr.get("quantity"))
        gross = price * qty
        pct: float | None = None
        if gross > 0:
            # 매도 시 profit_loss = (sell_price - buy_price) * quantity
            # 수익률 ≈ pnl / (sell_price * qty - pnl) ≈ pnl / 매수금액
            # 단순화: pnl / gross * 100 (sell 기준)
            pct = pnl / gross * 100

        if pnl > 0:
            win_count += 1
            if pct is not None:
                profit_pcts.append(pct)
        elif pnl < 0:
            loss_count += 1
            if pct is not None:
                loss_pcts.append(pct)

    decided = win_count + loss_count
    win_rate = (win_count / decided) if decided > 0 else 0.0

    avg_profit_pct = sum(profit_pcts) / len(profit_pcts) if profit_pcts else 0.0
    avg_loss_pct = sum(loss_pcts) / len(loss_pcts) if loss_pcts else 0.0
    max_profit_pct = max(profit_pcts) if profit_pcts else 0.0
    max_loss_pct = min(loss_pcts) if loss_pcts else 0.0

    # 손절 도달 건수 — 손실률(%)이 stop_loss_rate에 근접/도달한 매도
    stop_loss_rate = _safe_float(current_params.get("stop_loss_rate"))
    stop_loss_hits = 0
    if stop_loss_rate < 0 and loss_pcts:
        # stop_loss_rate(예: -7.5)보다 손실이 더 큰 (= 더 음수) 케이스
        # 허용 오차 0.5%p
        threshold = stop_loss_rate + 0.5
        for p in loss_pcts:
            if p <= threshold:
                stop_loss_hits += 1

    total_realized_pnl = sum(_safe_float(tr.get("profit_loss")) for tr in closed_sells)

    # daily_performance 통계
    daily_rates = [_safe_float(p.get("daily_profit_rate")) for p in performance]
    if daily_rates:
        daily_avg_return = sum(daily_rates) / len(daily_rates)
        daily_return_std = statistics.pstdev(daily_rates) if len(daily_rates) > 1 else 0.0
        # 누적수익률(%) — (1+r/100) 곱셈 누적
        acc = 1.0
        for r in daily_rates:
            acc *= (1.0 + r / 100.0)
        cumulative_return = (acc - 1.0) * 100.0
    else:
        daily_avg_return = 0.0
        daily_return_std = 0.0
        cumulative_return = 0.0

    return {
        "trades_count": buy_count + sell_count,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_rate, 4),
        "avg_profit_pct": round(avg_profit_pct, 3),
        "avg_loss_pct": round(avg_loss_pct, 3),
        "max_profit_pct": round(max_profit_pct, 3),
        "max_loss_pct": round(max_loss_pct, 3),
        "stop_loss_hits": stop_loss_hits,
        "total_realized_pnl": round(total_realized_pnl, 2),
        "daily_avg_return": round(daily_avg_return, 4),
        "daily_return_std": round(daily_return_std, 4),
        "cumulative_return": round(cumulative_return, 4),
        "analyzed_days": len(performance),
    }
