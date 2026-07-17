"""간이 백테스터 — 전략 규칙 검증용 스텁.

CSV(date,open,high,low,close,volume) 하나를 받아 단일 종목 시뮬레이션.
    python -m kojiro.backtest data/005930.csv --capital 10000000
거래비용: 매수 수수료 0.015% / 매도 수수료+거래세 0.165% / 슬리피지 0.1% 가정.
"""
import argparse

import pandas as pd

from .config import StrategyConfig
from .indicators import enrich
from .money import unit_size
from .strategy import (Action, Position, evaluate_entry, evaluate_exit,
                       evaluate_pyramid, update_position_after_close)

BUY_COST = 0.00015 + 0.001    # 수수료 + 슬리피지
SELL_COST = 0.00165 + 0.001   # 수수료 + 거래세 + 슬리피지


def run(df: pd.DataFrame, cfg: StrategyConfig, capital: float) -> dict:
    df = enrich(df, cfg)
    warmup = cfg.ema_long + cfg.macd_signal
    pos: Position | None = None
    cash = capital
    trades: list[dict] = []

    for i in range(warmup, len(df) - 1):
        window = df.iloc[: i + 1]
        last = window.iloc[-1]
        next_open = df["open"].iloc[i + 1]  # 신호 다음날 시가 체결 가정

        if pos:
            update_position_after_close(pos, last["close"], last["atr"], cfg)
            sig = evaluate_exit(window, pos, cfg)
            if sig.action == Action.SELL_ALL:
                proceeds = pos.qty * next_open * (1 - SELL_COST)
                trades.append({"exit": df.index[i + 1], "pnl": proceeds - pos.qty * pos.avg_price,
                               "reason": sig.reason})
                cash += proceeds
                pos = None
                continue
            pyr = evaluate_pyramid(window, pos, cfg)
            if pyr.action == Action.PYRAMID:
                plan = unit_size(capital, last["atr"], cfg)
                cost = plan.qty * next_open * (1 + BUY_COST)
                if plan.qty > 0 and cost <= cash:
                    pos.avg_price = (pos.avg_price * pos.qty + next_open * plan.qty) / (pos.qty + plan.qty)
                    pos.qty += plan.qty
                    pos.units += 1
                    cash -= cost
        else:
            sig = evaluate_entry(window, cfg)
            if sig.action in (Action.BUY, Action.BUY_EARLY):
                frac = 0.5 if sig.action == Action.BUY_EARLY else 1.0
                plan = unit_size(capital, last["atr"], cfg, fraction=frac)
                cost = plan.qty * next_open * (1 + BUY_COST)
                if plan.qty > 0 and cost <= cash:
                    pos = Position(code="BT", qty=plan.qty, avg_price=next_open,
                                   units=frac, entry_atr=float(last["atr"]),
                                   highest_close=next_open)
                    pos.stop_price = next_open - cfg.stop_atr * pos.entry_atr
                    cash -= cost

    if pos:  # 잔여 포지션 마지막 종가 청산
        cash += pos.qty * df["close"].iloc[-1] * (1 - SELL_COST)
        trades.append({"exit": df.index[-1],
                       "pnl": pos.qty * (df["close"].iloc[-1] - pos.avg_price),
                       "reason": "기간 종료 청산"})

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    return {
        "trades": len(trades),
        "win_rate": len(wins) / len(trades) if trades else 0,
        "avg_win": sum(t["pnl"] for t in wins) / len(wins) if wins else 0,
        "avg_loss": sum(t["pnl"] for t in losses) / len(losses) if losses else 0,
        "total_return_pct": (cash - capital) / capital * 100,
        "final_equity": cash,
        "log": trades,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--capital", type=float, default=10_000_000)
    ap.add_argument("--early", action="store_true", help="조기 진입 활성화")
    args = ap.parse_args()

    cfg = StrategyConfig(allow_early_entry=args.early)
    data = pd.read_csv(args.csv, parse_dates=["date"]).set_index("date")
    result = run(data, cfg, args.capital)
    for k, v in result.items():
        if k != "log":
            print(f"{k}: {v}")
