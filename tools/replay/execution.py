"""재현 틀 — 집행 층 (종목 하나의 거래 시뮬레이션, 자금 제약 없음).

규약(지시서 §3.3-4 · §3.4):
- t 일 종가로 신호 → t+1 일 시가 체결. 청산 신호도 같다.
- 가격 재난 손절: 장중 저가가 손절가를 건드리면 그 가격, 시가가 이미 아래면 시가.
- ±30% 가격제한: 시가가 전일 종가 대비 +29% 이상이면 매수 불가 · 시가가 −29% 이하이고
  고가 = 저가(하한가 잠김)면 매도를 다음 날로 미룬다.
- 물타기 금지(보유 중 추가 매수 없음). 청산 체결일에는 같은 종목 신규 체결 없음.
- 시장 유닛: 체결일 d 의 판정 = ``classify(기준 종가[:d])`` (직전 영업일 봉까지). 0 이면 진입 없음.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from replay.strategies.mean_reversion.signals import SignalSeries, entry_leung, entry_z, manage

LIMIT_UP = 1.29
LIMIT_DOWN = 0.71


@dataclass
class Rule:
    kind: str                    # "z" | "leung"
    entry_z: float = -2.0
    exit_z: float = 0.0
    cost: float = 0.0038
    stop_pct: float = 7.0
    k_stop: float = 1.5
    leung_L: float = -2.0
    mu_block: bool = True        # 시장 유닛 0 인 날 진입 차단 (D5)
    mu_missing_enter: bool = False  # 시장 유닛 결측(워밍업)일 때 진입하나


def simulate_ticker(o, h, l, c, sig: SignalSeries, eligible: np.ndarray, mu_exec: np.ndarray,
                    rule: Rule, leung_bounds_by_day=None) -> "list[dict]":
    """거래 목록. ``mu_exec[d]`` = 체결일 d 의 시장 유닛(NaN = 결측).

    ``leung_bounds_by_day[t]`` = 그날 적용 중인 추정의 (a, d, b) 또는 None.
    """
    n = len(c)
    trades = []
    pos = None
    pending_exit = None
    last_exit_day = -1
    stop_mult = 1.0 - rule.stop_pct / 100.0
    for t in range(n):
        # ── 1) 시가: 대기 중 청산 체결 ──
        if pos is not None and pending_exit is not None:
            op = o[t]
            if math.isfinite(op):
                locked = (math.isfinite(c[t - 1]) and op <= c[t - 1] * LIMIT_DOWN
                          and h[t] == l[t])
                if not locked:
                    _close(trades, pos, t, op, pending_exit, h, l)
                    pos, pending_exit, last_exit_day = None, None, t
        # ── 2) 장중: 가격 재난 손절 ──
        if pos is not None and math.isfinite(l[t]):
            stop_px = pos["entry_px"] * stop_mult
            if l[t] <= stop_px:
                fill = o[t] if (t > pos["ei"] and math.isfinite(o[t]) and o[t] <= stop_px) else stop_px
                _close(trades, pos, t, fill, "disaster_pct", h, l)
                pos, pending_exit, last_exit_day = None, None, t
        # ── 3) 종가: 청산 판정 ──
        if pos is not None and pending_exit is None:
            lb = leung_bounds_by_day[t] if (rule.kind == "leung" and leung_bounds_by_day is not None) else None
            why = manage(z=sig.z[t], valid_today=bool(sig.valid[t]), is_est_today=bool(sig.is_est[t]),
                         held_days=t - pos["ei"], hl_entry=pos["hl"], z_entry=pos["z_entry"],
                         k_stop=rule.k_stop, exit_z=rule.exit_z, leung_bounds=lb,
                         leung_L=rule.leung_L if rule.kind == "leung" else None)
            if why is not None:
                pending_exit = why
                pos["z_exit_sig"] = sig.z[t]
            continue
        # ── 4) 종가: 진입 판정 (다음 날 시가 체결) ──
        if pos is None and t + 1 < n and last_exit_day != t + 1 and sig.valid[t] and eligible[t]:
            if rule.kind == "z":
                ok = entry_z(sig.z[t], sig.sigma_stat[t], rule.entry_z, rule.exit_z, rule.cost)
            else:
                lb = leung_bounds_by_day[t] if leung_bounds_by_day is not None else None
                ok = entry_leung(sig.z[t], lb, sig.z[t - 1] if t > 0 else float("nan"), rule.leung_L)
            if not ok:
                continue
            m = mu_exec[t + 1]
            if not math.isfinite(m):
                if not rule.mu_missing_enter:
                    continue
            elif rule.mu_block and m == 0.0:
                continue
            op = o[t + 1]
            if not math.isfinite(op) or (math.isfinite(c[t]) and op >= c[t] * LIMIT_UP):
                continue
            pos = dict(ei=t + 1, sig_day=t, entry_px=op, z_entry=sig.z[t], hl=sig.hl[t],
                       sigma_stat=sig.sigma_stat[t], theta=sig.theta[t], mu=m)
            pending_exit = None
    if pos is not None:
        pos["open_at_end"] = True
    return trades


def _close(trades, pos, t, px, reason, h, l):
    ei = pos["ei"]
    seg_l = l[ei:t + 1]
    seg_h = h[ei:t + 1]
    mae = float(np.nanmin(seg_l) / pos["entry_px"] - 1.0) if np.isfinite(seg_l).any() else float("nan")
    mfe = float(np.nanmax(seg_h) / pos["entry_px"] - 1.0) if np.isfinite(seg_h).any() else float("nan")
    trades.append(dict(ei=ei, xi=t, sig_day=pos["sig_day"], entry_px=pos["entry_px"], exit_px=px,
                       gross=px / pos["entry_px"] - 1.0, reason=reason, z_entry=pos["z_entry"],
                       z_exit=pos.get("z_exit_sig", float("nan")), hl=pos["hl"],
                       held=t - ei, mae=mae, mfe=mfe, mu=pos["mu"]))
