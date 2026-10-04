"""계좌 층 — 동결본 C7 · P3 · P4. 전략 하나가 예산 풀 하나를 단독으로 쓴다.

하루 순서(cycle405 ``run_book`` 과 같다 — 관문 대조 대상):
1. 보유 랏의 시가 단계(갭 청산 · 전날 정해 둔 시가 청산) → 판 종목은 그날 재매수 금지
2. 그날 신호를 씨앗으로 섞은 순서대로 매수. 이미 보유 · 그날 판 종목은 건너뜀.
   슬롯(``max_pos``)이 차거나 하루 신규 상한에 닿으면 그날 매수 끝.
   수량 = ``size_fn(신호, 예산 B, 보유 원가 합)`` — 예산 B = **전날 종가 평가액**(자기 평가액 복리).
3. 보유 랏(그날 산 것 포함)의 장중·종가 단계
4. 종가 평가액 = 현금 + Σ 랏 평가액

정수 주(``size_fn`` 이 정수를 돌려준다) · 비용은 체결 금액에 한쪽씩(``cost_side``).
P4 집계: 신호 · 슬롯 참 · 하루 상한 · 수량 0(사유별) · 체결.
"""
from __future__ import annotations

from collections import Counter
from typing import Callable

import numpy as np
import pandas as pd


def run_book(signals_by_gd: dict, open_pos: Callable, size_fn: Callable, cal: pd.DatetimeIndex,
             start: str, end: str, seed: int, *, start_equity: float, cost_side: float,
             max_pos: int, daily_cap: "int | None" = None) -> dict:
    """``open_pos(sig, qty)`` → 포지션 객체(``cur_ti``·``open_phase``·``intraday_phase``·``data_ended``·
    ``value``·``k``·``exit_px``·``last_px``·``cost_basis``·``_exit``). ``size_fn(sig, B, used)`` → (qty, 사유)."""
    rng = np.random.default_rng(seed)
    g0 = int(cal.searchsorted(pd.Timestamp(start)))
    g1 = int(cal.searchsorted(pd.Timestamp(end), side="right")) - 1
    cash = float(start_equity)
    pos: dict = {}
    eq_prev = float(start_equity)
    equity, trades = [], []
    cnt = Counter()
    for gd in range(g0, g1 + 1):
        B = eq_prev
        sold_today = set()
        for t in list(pos):
            ps = pos[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                continue
            if ps.open_phase(ti, gd):
                cash += ps.k * ps.exit_px * (1 - cost_side)
                trades.append(ps)
                sold_today.add(t)
                del pos[t]
        todays = list(signals_by_gd.get(gd, []))
        rng.shuffle(todays)
        n_new = 0
        stop_why = None
        for s in todays:
            if s.ticker in pos or s.ticker in sold_today:
                continue
            cnt["signal"] += 1
            if stop_why is None and len(pos) >= max_pos:
                stop_why = "slot_full"
            if stop_why is None and daily_cap is not None and n_new >= daily_cap:
                stop_why = "daily_cap"
            if stop_why is not None:
                cnt[stop_why] += 1
                continue
            used = sum(x.cost_basis for x in pos.values())
            q, why = size_fn(s, B, used)
            if q <= 0:
                cnt["zero_" + why] += 1
                continue
            ps = open_pos(s, q)
            cash -= q * s.E_raw * (1 + cost_side)
            pos[s.ticker] = ps
            n_new += 1
            cnt["fill"] += 1
        for t in list(pos):
            ps = pos[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                if ps.data_ended(gd):
                    ps._exit(ps.last_px, "END", gd)
                    cash += ps.k * ps.exit_px * (1 - cost_side)
                    trades.append(ps)
                    del pos[t]
                continue
            if ps.intraday_phase(ti, gd, ti == ps.s.ti):
                cash += ps.k * ps.exit_px * (1 - cost_side)
                trades.append(ps)
                del pos[t]
        eq = cash + sum(x.value() for x in pos.values())
        equity.append(eq)
        eq_prev = eq
    for ps in pos.values():
        ps._exit(ps.last_px, "OPEN", None)
        trades.append(ps)
    eq = np.array(equity)
    return {"equity": eq, "trades": trades, "dates": cal[g0:g1 + 1], "counts": dict(cnt),
            "recon": reconcile(eq, trades, start_equity, cost_side)}


def reconcile(eq: np.ndarray, trades: list, start_equity: float, cost_side: float) -> float:
    """대사 — 마지막 평가액 − (시작 + Σ 거래 손익). 0 이어야 한다(cycle405 ``recon``)."""
    tot = 0.0
    for ps in trades:
        buy = ps.qty * ps.s.E_raw * (1 + cost_side)
        if ps.exit_reason == "OPEN":
            tot += ps.k * ps.last_px - buy
        else:
            tot += ps.k * ps.exit_px * (1 - cost_side) - buy
    return float(eq[-1] - (start_equity + tot)) if len(eq) else 0.0


def cagr(eq: np.ndarray, start_equity: float) -> float:
    """연 복리 — 거래일 252일 = 1년(cycle405 와 같다)."""
    if len(eq) < 2:
        return float("nan")
    return float((eq[-1] / start_equity) ** (252.0 / len(eq)) - 1)


def mdd(eq: np.ndarray, start_equity: float) -> float:
    e = np.concatenate([[start_equity], eq])
    peak = np.maximum.accumulate(e)
    return float((e / peak - 1).min())


def book_summary(runs: "list[dict]", start_equity: float, years: "float | None" = None) -> dict:
    """씨앗별 결과 → 중앙값 판정 재료(P3·P4)."""
    cg = [cagr(r["equity"], start_equity) for r in runs]
    md = [mdd(r["equity"], start_equity) for r in runs]
    nt = [len(r["trades"]) for r in runs]
    yrs = years if years is not None else (len(runs[0]["equity"]) / 252.0 if runs else float("nan"))
    fills = [r["counts"].get("fill", 0) for r in runs]
    unaff = []
    for r in runs:
        c = r["counts"]
        free = c.get("signal", 0) - c.get("slot_full", 0) - c.get("daily_cap", 0)
        unaff.append(c.get("zero_funds", 0) / free if free > 0 else float("nan"))
    return {
        "cagr_median": float(np.median(cg)), "cagr_min": float(np.min(cg)), "cagr_max": float(np.max(cg)),
        "mdd_median": float(np.median(md)), "trades_median": float(np.median(nt)),
        "fills_per_year_median": float(np.median(fills) / yrs),
        "unaffordable_ratio_median": float(np.nanmedian(unaff)) if any(u == u for u in unaff) else float("nan"),
        "recon_max_abs": float(max(abs(r["recon"]) for r in runs)),
        "counts_seed0": runs[0]["counts"] if runs else {},
        "per_seed": [{"cagr": a, "mdd": b, "n_trades": c} for a, b, c in zip(cg, md, nt)],
    }
