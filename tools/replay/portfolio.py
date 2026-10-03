"""재현 틀 — 자금 층 (예산·슬롯 제약 계좌 시뮬레이션).

지시서 §3.4 D7: 전략 예산 = 순자산 × cash_usage_ratio × 0.05 (500만 × 0.95 × 0.05 = 237,500원).
- 슬롯 S 개. 신호가 오면 빈 슬롯이 있을 때 (현금 ÷ 빈 슬롯) 로 정수 주 매수(원본 시가 기준).
- 1주도 못 사면 「자금 부족 미체결」 — 1주 폴백 없음.
- 같은 날 신호가 빈 슬롯보다 많으면 z 가 낮은 것부터.
- 비용은 진입·청산에 반씩 뗀다. 평가 = 수정 종가 비율 × 진입 원본 금액.

근사(보고서 명시): 후보 거래는 자금 제약 없는 종목별 시뮬레이션의 거래 목록이다. 슬롯이 차서
건너뛴 거래 때문에 그 종목의 다음 거래 시점이 달라지는 효과는 반영하지 않는다.
"""
from __future__ import annotations

import math

import numpy as np


def run_account(trades: "list[dict]", closes_adj: np.ndarray, n_days: int, *, budget: float,
                slots: int, cost: float) -> dict:
    """``trades`` 각 원소: tj(종목 열), ei, xi, entry_px(수정), exit_px(수정), entry_raw(원본 시가), z_entry."""
    by_day: dict = {}
    for k, tr in enumerate(trades):
        by_day.setdefault(tr["ei"], []).append(k)
    cash = budget
    open_pos: dict = {}       # k → (shares_value_at_entry_raw, tj, entry_px, xi, exit_px)
    equity = np.full(n_days, np.nan)
    n_sig = n_unaff = n_full = n_fill = 0
    turnover = 0.0
    filled = []
    def _exit_due(d):
        nonlocal cash, turnover
        for k in [k for k, p in open_pos.items() if p["xi"] <= d]:
            p = open_pos.pop(k)
            val = p["notional"] * (p["exit_px"] / p["entry_px"])
            cash += val * (1.0 - cost / 2.0)
            turnover += val

    for d in range(n_days):
        # 청산 (시가 또는 장중 — 그날 체결로 본다)
        _exit_due(d)
        # 진입
        cands = sorted(by_day.get(d, []), key=lambda k: trades[k]["z_entry"])
        for k in cands:
            tr = trades[k]
            n_sig += 1
            free = slots - len(open_pos)
            if free <= 0:
                n_full += 1
                continue
            alloc = cash / free
            px = tr["entry_raw"]
            if not (math.isfinite(px) and px > 0):
                continue
            shares = int(alloc // (px * (1.0 + cost / 2.0)))
            if shares < 1:
                n_unaff += 1
                continue
            notional = shares * px
            cash -= notional * (1.0 + cost / 2.0)
            turnover += notional
            n_fill += 1
            open_pos[k] = dict(notional=notional, tj=tr["tj"], entry_px=tr["entry_px"],
                               xi=tr["xi"], exit_px=tr["exit_px"], ei=d)
            filled.append(k)
        # 진입 당일 장중 손절로 끝난 거래 (xi == ei) — 진입 뒤에 정산한다
        _exit_due(d)
        # 종가 평가
        mtm = 0.0
        for p in open_pos.values():
            cl = closes_adj[d, p["tj"]]
            if not math.isfinite(cl):
                cl = p.get("last_cl", p["entry_px"])
            p["last_cl"] = cl
            mtm += p["notional"] * (cl / p["entry_px"])
        equity[d] = cash + mtm
    rets = np.diff(equity) / equity[:-1]
    peak = np.maximum.accumulate(equity)
    mdd = float(np.min(equity / peak - 1.0))
    eligible_sig = n_sig - n_full
    return dict(equity=equity, daily_ret=np.concatenate([[0.0], rets]), n_signal=n_sig,
                n_slot_full=n_full, n_unaffordable=n_unaff, n_filled=n_fill,
                unaffordable_ratio=(n_unaff / eligible_sig) if eligible_sig else float("nan"),
                unaffordable_ratio_all=(n_unaff / n_sig) if n_sig else float("nan"),
                net_return=float(equity[-1] / budget - 1.0), mdd=mdd,
                turnover=turnover / budget, filled=filled)


def sharpe_sortino(daily: np.ndarray) -> "tuple[float, float]":
    d = daily[np.isfinite(daily)]
    if len(d) < 2 or np.std(d) == 0:
        return float("nan"), float("nan")
    sh = float(np.mean(d) / np.std(d, ddof=1) * math.sqrt(252))
    neg = d[d < 0]
    so = float(np.mean(d) / np.sqrt(np.mean(neg ** 2)) * math.sqrt(252)) if len(neg) else float("nan")
    return sh, so
