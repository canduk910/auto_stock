"""실거래(K4) 판정·보고 층 — VB(S5) · momentum(S6) · LTV(S8, 사후 기록).

입력 = 단계 1 왕복 표(``audit/live_trips.json`` — D-1·D-2·D-4·D-7 적용 뒤). 동결본 §1.3:
- L1 = n ≥ 30 일 때 순수익(체결가, 0.38% 차감) 평균 > 0 ∧ 매수일 군집 부트스트랩 90% 하한 > −1.0%
- L2(보고만) = 금액 가중 평균 · 1주 랏 비율 · 청산 사유 비율 · 상위 5건 제외 평균

청산 사유는 ``trade_history`` 에 열이 없어 **체결가·날짜로 추정**한다(결과 md 에 추정이라고 적는다).
"""
from __future__ import annotations

from datetime import date

import numpy as np

from replay.audit import config as C
from replay.audit import judge as J


def select(trips: list, strategy: str, start: str, end: "str | None" = None) -> list:
    """판정 표본 — D-4 창 안(``in_window``) ∧ D-1 표시 없음 ∧ 매수일 ∈ [start, end]."""
    out = []
    for t in trips:
        if t["strategy"] != strategy or not t["in_window"] or t["ca_flag"]:
            continue
        if t["buy_date"] < start or (end is not None and t["buy_date"] > end):
            continue
        out.append(t)
    return out


def _net(t, cost_rt=C.COST_RT_JUDGE):
    return t["gross"] - cost_rt


def l1_block(trips: list, cost_rt: float = C.COST_RT_JUDGE) -> dict:
    r = np.array([_net(t, cost_rt) for t in trips])
    res = {"l1": J.l1(r, [t["buy_date"] for t in trips]), "n": len(r)}
    if len(r):
        res.update(mean_net=float(r.mean()), median_net=float(np.median(r)), win=float((r > 0).mean()),
                   mean_gross=float(np.mean([t["gross"] for t in trips])),
                   sens={f"{c:.4f}": float(np.mean([_net(t, c) for t in trips])) for c in C.COST_RT_SENS},
                   first_buy=min(t["buy_date"] for t in trips), last_buy=max(t["buy_date"] for t in trips))
        if len(r) >= 2:
            est, lo, hi = J.cluster_bootstrap(r, [t["buy_date"] for t in trips], order="sorted")
            res["boot90"] = [lo, hi]
    return res


def l2_block(trips: list, cost_rt: float = C.COST_RT_JUDGE) -> dict:
    if not trips:
        return {"n": 0}
    r = np.array([_net(t, cost_rt) for t in trips])
    w = np.array([t["buy_amt"] for t in trips], dtype=float)
    srt = np.sort(r)
    return {"n": len(r), "amount_weighted_net": float((r * w).sum() / w.sum()),
            "one_share_share": float(np.mean([t["one_share"] for t in trips])),
            "mean_net_ex_top5": float(srt[:-5].mean()) if len(r) > 5 else None,
            "notional_median": float(np.median(w)), "notional_sum": float(w.sum()),
            "pnl_net_sum_won": float((r * w).sum())}


def vb_exit_reason(t: dict) -> str:
    """VB 청산 사유 추정 — 다음 날 매도 = 15:20 청산 누락(익일 안전망) · 총수익 ≤ −4.9% = 손절(−5) · 나머지 = 15:20."""
    if t["sell_date"] > t["buy_date"]:
        return "OVERNIGHT"
    if t["gross"] <= -0.049:
        return "STOP_LOSS(≈−5%)"
    return "FORCE_CLEAR_1520"


def momentum_bucket(t: dict, opens: dict, trading_days: list) -> str:
    """momentum — 당일 청산(손절) / 다음 거래일 시가 갭 ≥ +10%(트레일링) / < +10%(09:00 청산). 시가는 DB 원본."""
    if t["sell_date"] == t["buy_date"]:
        return "same_day"
    nxt = next((d for d in trading_days if d > t["buy_date"]), None)
    o = opens.get((t["ticker"], nxt)) if nxt else None
    if not o:
        return "gap_unknown"
    return "gap_ge_10" if (o / t["buy_px"] - 1) * 100 >= 10.0 else "gap_lt_10"


def ltv_mode(t: dict) -> str:
    """LTV 모드 근사 — 당일 매도 = 당일 모드 · 다음 날 이후 매도 = 상한가 하룻밤 모드."""
    return "intraday" if t["sell_date"] == t["buy_date"] else "overnight"


def bucket_table(trips: list, keyf, cost_rt: float = C.COST_RT_JUDGE) -> dict:
    out: dict = {}
    for t in trips:
        out.setdefault(keyf(t), []).append(_net(t, cost_rt))
    return {k: {"n": len(v), "share": len(v) / len(trips), "mean_net": float(np.mean(v))}
            for k, v in sorted(out.items())}


def month_key(t: dict) -> str:
    return t["buy_date"][:7]


def is_iso(d: str) -> bool:
    try:
        date.fromisoformat(d)
        return True
    except ValueError:
        return False
