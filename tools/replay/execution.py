"""재현 틀 — 집행 층 (종목 하나의 거래 시뮬레이션, 자금 제약 없음).

규약(지시서 §3.3-4 · §3.4):
- t 일 종가로 신호 → t+1 일 시가 체결. 청산 신호도 같다.
- 가격 재난 손절: 장중 저가가 손절가를 건드리면 그 가격, 시가가 이미 아래면 시가.
- ±30% 가격제한: 시가가 전일 종가 대비 +29% 이상이면 매수 불가 · 시가가 −29% 이하이고
  고가 = 저가(하한가 잠김)면 매도를 다음 날로 미룬다 — 대기 청산과 가격 손절 모두(2차 M7).
- 물타기 금지(보유 중 추가 매수 없음). 청산 당일 재진입은 구조상 없다 — 청산 체결은 그날 시가·장중,
  진입 체결은 신호 다음 날 시가다(청산일 종가 신호 → 다음 날 진입은 허용).
- 회귀 깨짐 청산은 그날 재추정 사유로 두 갈래를 기록한다(``rb_kind`` 1 = 통계 탈락 · 2 = 측정 불가, 2차 R3).
- 시장 유닛: 체결일 d 의 판정 = ``classify(기준 종가[:d])`` (직전 영업일 봉까지). 0 이면 진입 없음.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from replay.strategies.mean_reversion.signals import (REASON_CODES, SignalSeries, entry_leung, entry_z,
                                                      manage)

LIMIT_UP = 1.29
LIMIT_DOWN = 0.71
_RB_STAT = {REASON_CODES[k] for k in ("adf", "half_life", "b_range", "sigma")}


def _rb_kind(sig: SignalSeries, t: int) -> int:
    """회귀 깨짐 갈래 — 1 = 통계 탈락(ADF·반감기·b 범위·σ) · 2 = 측정 불가(정지·결측·β 결측·계산 실패)."""
    return 1 if int(sig.est_reason[t]) in _RB_STAT else 2


def _locked_limit_down(o, h, l, c, t: int) -> bool:
    return (t > 0 and math.isfinite(o[t]) and math.isfinite(c[t - 1]) and o[t] <= c[t - 1] * LIMIT_DOWN
            and h[t] == l[t])


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
                    rule: Rule, leung_bounds_by_day=None, stats: "dict | None" = None) -> "list[dict]":
    """거래 목록. ``mu_exec[d]`` = 체결일 d 의 시장 유닛(NaN = 결측).

    ``leung_bounds_by_day[t]`` = 그날 적용 중인 추정의 (a, d, b) 또는 None.
    ``stats`` 를 주면 ``cost_blocked``(z 는 경계 아래인데 비용 조건이 거른 신호 수)를 센다(2차 M9).
    """
    n = len(c)
    trades = []
    pos = None
    pending_exit = None
    stop_mult = 1.0 - rule.stop_pct / 100.0
    if stats is not None:
        stats.setdefault("cost_blocked", 0)
    for t in range(n):
        # ── 1) 시가: 대기 중 청산 체결 ──
        if pos is not None and pending_exit is not None:
            op = o[t]
            if math.isfinite(op) and not _locked_limit_down(o, h, l, c, t):
                _close(trades, pos, t, op, pending_exit, h, l)
                pos, pending_exit = None, None
        # ── 2) 장중: 가격 재난 손절 (하한가 잠긴 날은 못 판다 → 다음 날 시가 대기 청산) ──
        if pos is not None and math.isfinite(l[t]):
            stop_px = pos["entry_px"] * stop_mult
            if l[t] <= stop_px:
                if _locked_limit_down(o, h, l, c, t):
                    if pending_exit is None:
                        pending_exit = "disaster_pct"
                        pos["rb_kind"] = 0
                    continue
                fill = o[t] if (t > pos["ei"] and math.isfinite(o[t]) and o[t] <= stop_px) else stop_px
                _close(trades, pos, t, fill, "disaster_pct", h, l)
                pos, pending_exit = None, None
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
                pos["rb_kind"] = _rb_kind(sig, t) if why == "regime_break" else 0
            continue
        if pos is not None:
            continue
        # ── 4) 종가: 진입 판정 (다음 날 시가 체결) ──
        if t + 1 < n and sig.valid[t] and eligible[t]:
            if rule.kind == "z":
                ok = entry_z(sig.z[t], sig.sigma_stat[t], rule.entry_z, rule.exit_z, rule.cost)
                if (not ok and stats is not None and math.isfinite(sig.z[t])
                        and sig.z[t] <= rule.entry_z):
                    stats["cost_blocked"] += 1
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
                       held=t - ei, mae=mae, mfe=mfe, mu=pos["mu"], rb_kind=pos.get("rb_kind", 0)))
