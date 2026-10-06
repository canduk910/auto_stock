"""판정 층 — 동결본 §1.3 P1~P6 · L1 과 그 재료.

- ``cluster_bootstrap`` — 군집 다항 부트스트랩. 가중(m 가중 평균 비)도 된다. 군집 순서는
  「처음 나온 순서」(cycle391 ``boot_ci`` 와 같은 난수 소비) 또는 정렬 순서를 고른다.
- ``p1``..``p6``·``l1`` — 기준값을 config 에서 읽어 (값, 통과 여부, 라벨) 을 돌려준다.
- ``r_sleeve`` — cycle391 T5 판정판 슬리브(중복 제거된 거래 목록 위 슬롯 4 · 같은 날 무작위 40회,
  손익 = Rnet·f·m·2·risk_pct 합). 관문 대조(391b)용으로만 쓴다 — P3 은 ``book`` 의 정수 주 계좌다.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

import numpy as np

from . import config as C


def cluster_bootstrap(values, keys, weights=None, *, n_boot: int = C.N_BOOT, seed: int = C.BOOT_SEED,
                      q: float = C.BOOT_Q, order: str = "first") -> "tuple[float, float, float]":
    """(점추정, 하한 q 분위, 상한 1−q 분위). 점추정 = Σw·v/Σw (가중 없으면 평균)."""
    v = np.asarray(values, dtype=float)
    w = np.ones(len(v)) if weights is None else np.asarray(weights, dtype=float)
    if len(v) == 0 or w.sum() <= 0:
        return float("nan"), float("nan"), float("nan")
    est = float((w * v).sum() / w.sum())
    cl: dict = {}
    if order == "first":
        for k in keys:
            if k not in cl:
                cl[k] = len(cl)
    elif order == "sorted":
        for k in sorted(set(keys)):
            cl[k] = len(cl)
    else:
        raise ValueError(order)
    if len(cl) < 2:
        return est, float("nan"), float("nan")
    idx = np.fromiter((cl[k] for k in keys), dtype=np.int64, count=len(v))
    K = len(cl)
    s1 = np.bincount(idx, weights=w * v, minlength=K)
    s0 = np.bincount(idx, weights=w, minlength=K)
    rng = np.random.default_rng(seed)
    cnt = rng.multinomial(K, np.full(K, 1.0 / K), size=n_boot).astype(float)
    stat = np.einsum("ij,j->i", cnt, s1) / np.einsum("ij,j->i", cnt, s0)
    return est, float(np.percentile(stat, 100 * q)), float(np.percentile(stat, 100 * (1 - q)))


def iso_week_key(ticker: str, d) -> str:
    dd = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
    y, wk, _ = dd.isocalendar()
    return f"{ticker}|{y}-W{wk:02d}"


# ── P1 ~ P6 ─────────────────────────────────────────────────────────────

def p1(net_returns, tickers, entry_dates) -> dict:
    keys = [iso_week_key(t, d) for t, d in zip(tickers, entry_dates)]
    est, lo, hi = cluster_bootstrap(net_returns, keys, order="sorted")
    ok = bool(est > 0 and lo > C.P1_LO)
    return {"n": len(keys), "mean": est, "lo90": lo, "hi90": hi, "pass": ok,
            "label": "통과" if ok else "실패"}


def p2(h_net_returns, full_mean: float) -> dict:
    n = len(h_net_returns)
    if n < C.P2_MIN_N:
        return {"n": n, "label": "판정 불가", "pass": None}
    m = float(np.mean(h_net_returns))
    ok = bool(np.sign(m) == np.sign(full_mean))
    return {"n": n, "mean": m, "full_mean": full_mean, "pass": ok, "label": "통과" if ok else "실패"}


def p3(summary: dict) -> dict:
    ok = bool(summary["cagr_median"] > 0 and summary["mdd_median"] >= C.P3_MDD)
    return {"cagr_median": summary["cagr_median"], "mdd_median": summary["mdd_median"], "pass": ok,
            "label": "통과" if ok else "실패"}


def p4(summary: dict) -> dict:
    fy, ua = summary["fills_per_year_median"], summary["unaffordable_ratio_median"]
    ok = bool(fy >= C.P4_FILLS_PER_YEAR and not (ua == ua and ua >= C.P4_UNAFF))
    return {"fills_per_year": fy, "unaffordable_ratio": ua, "pass": ok, "label": "통과" if ok else "실패"}


def p5(mean_color: float, mean_adverse: float) -> dict:
    flip = bool(np.sign(mean_color) != np.sign(mean_adverse))
    return {"mean_color": mean_color, "mean_adverse": mean_adverse, "flip": flip,
            "label": "판정 보류(일봉 해상도 부족)" if flip else "유지"}


def p6(live_buys: "list[tuple[str, str]]", replay_signals: "set[tuple[str, str]]") -> dict:
    """live_buys = [(ticker, KST 매수일)] · replay_signals = {(ticker, 진입일)} — 같은 날 같은 종목 비율."""
    n = len(live_buys)
    if n < C.P6_MIN_N:
        return {"n": n, "label": "관문 판정 불가", "pass": None}
    hit = sum(1 for k in live_buys if k in replay_signals)
    r = hit / n
    ok = r >= C.P6_MATCH
    return {"n": n, "hit": hit, "rate": r, "pass": ok, "label": "통과" if ok else "재현 신뢰 불가"}


def l1(net_returns, buy_dates) -> dict:
    n = len(net_returns)
    if n < C.L1_MIN_N:
        return {"n": n, "label": "판정 불가", "pass": None,
                "mean": float(np.mean(net_returns)) if n else float("nan")}
    est, lo, hi = cluster_bootstrap(net_returns, [str(d) for d in buy_dates], order="sorted")
    ok = bool(est > 0 and lo > C.L1_LO)
    return {"n": n, "mean": est, "lo90": lo, "hi90": hi, "pass": ok, "label": "통과" if ok else "실패"}


# ── cycle391 T5 판정판 슬리브 (관문 대조 전용) ─────────────────────────────

def _approx_mdd(taken, pnl) -> float:
    ex_order = sorted(range(len(taken)), key=lambda i: (taken[i]["exit_ci"], taken[i]["entry_ci"]))
    cum = np.concatenate([[0.0], np.cumsum(pnl[ex_order])]) * 100
    return float((cum - np.maximum.accumulate(cum)).min())


def r_sleeve(ts: list, seed_base: int, *, years: float, slots: int = 4, n_runs: int = 40,
             risk_pct: float = 0.01) -> dict:
    runs = []
    for r in range(n_runs):
        rng = np.random.default_rng(seed_base + r)
        keys = rng.random(len(ts))
        order = sorted(range(len(ts)), key=lambda i: (ts[i]["entry_ci"], keys[i]))
        open_exit, taken = [], []
        for i in order:
            t = ts[i]
            open_exit = [x for x in open_exit if x >= t["entry_ci"]]
            if len(open_exit) < slots:
                open_exit.append(t["exit_ci"])
                taken.append(t)
        pnl = np.array([t["Rnet"] * t["f"] * t["m"] * 2 * risk_pct for t in taken])
        runs.append((pnl.sum() / years * 100, _approx_mdd(taken, pnl), len(taken)))
    ann = float(np.mean([x[0] for x in runs]))
    md = float(np.median([x[1] for x in runs]))
    return {"ann_mean": ann, "mdd_median": md, "ret_over_mdd": ann / abs(md) if md < 0 else math.inf,
            "trades_per_run_mean": float(np.mean([x[2] for x in runs]))}


def m_weighted_R(ts: list) -> float:
    w = np.array([t["m"] for t in ts])
    r = np.array([t["Rnet"] for t in ts])
    return float((w * r).sum() / w.sum()) if len(ts) and w.sum() > 0 else float("nan")


def by_key(ts: list, keyf) -> dict:
    out = defaultdict(list)
    for t in ts:
        out[keyf(t)].append(t)
    return out
