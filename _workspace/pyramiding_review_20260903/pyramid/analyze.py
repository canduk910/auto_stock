"""렌즈 5 — donchian_swing·kojiro 완결 왕복 전수에 대한 피라미딩(1/2N × 4유닛) 기계 적용 모형.

입력: raw.json (EC2 운영 DB read-only 추출: trade_history / positions / stock_master_daily / daily_performance / strategy_config)
출력: roundtrips.csv (왕복별 지표) · open_positions.csv · summary.json · summary.txt

모형 규약 (문서 본문과 동일하게 기술할 것):
- N = ATR(14) 단순평균, 진입일 **이전** 14봉 (strategy_base._atr 과 동일 창: highs[0]=D-1). kojiro 는 참고로 Wilder ATR(20) 도 병기.
- 유닛 수량 = 실제 최초 체결 수량 q0 (1주 폴백이면 1주). 추가 유닛도 q0.
- 추가 레벨 L_k = P0 + k×0.5N (k=1..3, 최대 4유닛). 일봉 high ≥ L_k 이면 그날 체결. 체결가 = D0 는 L_k, 이후 날은 max(L_k, open) (갭업 시 시가).
- 손절선 = 마지막 진입가 − 2N (전 유닛 공통). 초기 = P0 − 2N.
- 하루 안 순서(불가지) → 두 변형 병기:
    pess(비관): ① 전일 손절선으로 open/low 검사 → ② 추가 체결 → ③ **당일 low 로 새 손절선 재검사**(추가 후 급락 가정)
    opt (낙관): ① 전일 손절선 검사 → ② 추가 체결. 새 손절선은 익일부터.
- 실제 청산일 Dx 에는 실제 청산가 Px 로 전 유닛 청산 (전략 자신의 청산이 그날 발화했으므로). Dx 이전에 피라미드 손절이 먼저 닿으면 손절가 청산.
- 손익은 총액(수수료·세금 제외). 자본 = 진입일 daily_performance(total).total_asset.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta

HERE = "/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/823ca95c-aa00-4436-b4f5-5eac77e3c1db/scratchpad/pyramid"
raw = json.load(open(f"{HERE}/raw.json"))

STRATS = ("donchian_swing", "kojiro")
MAX_UNITS = 4
STEP_N = 0.5
STOP_N = 2.0
ASOF = date(2026, 9, 2)

# ── 일봉 인덱스 ──────────────────────────────────────────────
daily: dict[str, list[dict]] = defaultdict(list)
for r in raw["daily"]:
    d = date.fromisoformat(r["bas_dd"])
    if r["h"] <= 0 or r["l"] <= 0 or r["c"] <= 0:
        continue
    daily[r["ticker"]].append({"d": d, "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r["v"]})
for t in daily:
    daily[t].sort(key=lambda x: x["d"])

perf_total = {date.fromisoformat(p["d"]): p["total_asset"] for p in raw["perf"] if p["strategy"] == "total"}
perf_days = sorted(perf_total)

cfg = {c["strategy_id"]: c for c in raw["cfg"]}
w_sum = sum(c["weight"] for c in raw["cfg"] if c["enabled"])
weight = {s: cfg[s]["weight"] / w_sum for s in STRATS}
pos_ratio = {s: float(cfg[s]["params"].get("position_ratio", 0.2)) for s in STRATS}
risk_pct = {s: float(cfg[s]["params"].get("risk_pct", 0.005)) for s in STRATS}


def asset_at(d: date) -> float:
    prev = [x for x in perf_days if x <= d]
    return perf_total[prev[-1]] if prev else float("nan")


def atr14_sma(t: str, entry: date, period: int = 14) -> float:
    """strategy_base._atr 동일: 진입일 이전 봉만, highs[0]=D-1, TR 3항, 단순평균."""
    bars = [b for b in daily[t] if b["d"] < entry]
    if len(bars) < period + 1:
        return 0.0
    rev = list(reversed(bars))  # idx0 = D-1
    trs = []
    for i in range(period):
        h, l, pc = rev[i]["h"], rev[i]["l"], rev[i + 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / period


def atr_wilder(t: str, entry: date, period: int = 20) -> float:
    """kojiro_indicators.atr 동일: ewm(alpha=1/period, adjust=False), 진입일 이전 봉 전체."""
    bars = [b for b in daily[t] if b["d"] < entry]
    if len(bars) < period + 5:
        return 0.0
    a = 1.0 / period
    val = None
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        val = tr if val is None else (a * tr + (1 - a) * val)
    return float(val or 0.0)


def bars_between(t: str, d0: date, d1: date) -> list[dict]:
    return [b for b in daily[t] if d0 <= b["d"] <= d1]


# ── 왕복 페어링 (FIFO, 전략·종목 단위) ─────────────────────────
trades = [x for x in raw["trades_strat"] if x["status"] == "COMPLETED"]
trades.sort(key=lambda x: x["ts_kst"])
open_lots: dict[tuple, list[dict]] = defaultdict(list)
roundtrips: list[dict] = []
for tr in trades:
    key = (tr["strategy"], tr["ticker"])
    ts = datetime.strptime(tr["ts_kst"], "%Y-%m-%d %H:%M:%S")
    if tr["trade_type"] == "BUY":
        open_lots[key].append({"ts": ts, "px": tr["price"], "q": tr["quantity"], "name": tr["ticker_name"], "order_no": tr["order_no"]})
    else:
        if not open_lots[key]:
            print("WARN sell without buy", tr)
            continue
        lot = open_lots[key].pop(0)
        roundtrips.append({
            "strategy": tr["strategy"], "ticker": tr["ticker"], "name": lot["name"],
            "buy_ts": lot["ts"], "buy_px": lot["px"], "qty": lot["q"],
            "sell_ts": ts, "sell_px": tr["price"], "sell_qty": tr["quantity"],
            "pl_recorded": tr["profit_loss"],
        })
open_positions = [(k, lots) for k, lots in open_lots.items() if lots]


def simulate(t: str, p0: float, q0: int, n: float, d0: date, dx: date | None, px: float | None, mode: str, step: float = STEP_N, budget_cap: float | None = None) -> dict:
    """1/2N × 4유닛 피라미딩 기계 적용. dx=None 이면 ASOF 까지 미청산(오픈 포지션 관찰)."""
    end = dx or ASOF
    bars = bars_between(t, d0, end)
    if not bars or n <= 0:
        return {"ok": False}
    levels = [p0 + k * step * n for k in range(1, MAX_UNITS)]
    pess = mode.startswith("pess")
    units = [(p0, q0)]  # (entry_px, qty)
    stop = p0 - STOP_N * n
    add_days: list[int] = []
    exit_px, exit_reason, exit_day = None, None, None
    for i, b in enumerate(bars):
        is_exit_day = dx is not None and b["d"] == dx
        # ① 전일 손절선 검사 (D0 는 진입 후라 low 검사만; 시가 갭은 D0 미적용)
        if i > 0 and b["o"] <= stop:
            exit_px, exit_reason, exit_day = b["o"], "pyr_stop_gap", i
            break
        if b["l"] <= stop and not (is_exit_day and px is not None and px > stop and i == 0):
            # 청산일에는 실제 청산가가 지배 — 단 실제 청산가가 손절선 아래면 손절과 동치
            if is_exit_day:
                exit_px, exit_reason, exit_day = px, "actual_exit(stop_touched_same_day)", i
                break
            exit_px, exit_reason, exit_day = stop, "pyr_stop", i
            break
        # ② 추가 체결
        while len(units) < MAX_UNITS and b["h"] >= levels[len(units) - 1]:
            lvl = levels[len(units) - 1]
            fill = lvl if i == 0 else max(lvl, b["o"])
            if budget_cap is not None and sum(p * q for p, q in units) + fill * q0 > budget_cap:
                break  # 전략 예산(total_investment) 초과 → _apply_budget_limit 이 0주로 클램프
            units.append((fill, q0))
            add_days.append(i)
            stop = fill - STOP_N * n
        # ③ 비관: 추가 후 새 손절선을 당일 low 로 재검사
        if pess and add_days and add_days[-1] == i and b["l"] <= stop and not is_exit_day:
            exit_px, exit_reason, exit_day = stop, "pyr_stop_same_day_after_add", i
            break
        if is_exit_day:
            exit_px, exit_reason, exit_day = px, "actual_exit", i
            break
    if exit_px is None:
        # 미청산(오픈) — 마지막 종가로 평가
        exit_px, exit_reason, exit_day = bars[-1]["c"], "open_mark", len(bars) - 1
    tot_q = sum(q for _, q in units)
    cost = sum(p * q for p, q in units)
    pnl = exit_px * tot_q - cost
    avg = cost / tot_q
    risk_at_final_stop = sum((p - stop) * q for p, q in units)  # 마지막 손절선 기준 리스크(원)
    return {
        "ok": True, "units": len(units), "add_days": add_days, "unit_px": [round(p) for p, _ in units],
        "avg_px": avg, "final_stop": stop, "exit_px": exit_px, "exit_reason": exit_reason, "exit_day": exit_day,
        "pnl": pnl, "notional": cost, "tot_qty": tot_q, "risk_won": risk_at_final_stop,
    }


rows = []
for rt in roundtrips:
    t, s = rt["ticker"], rt["strategy"]
    d0, dx = rt["buy_ts"].date(), rt["sell_ts"].date()
    p0, q0, px = rt["buy_px"], rt["qty"], rt["sell_px"]
    n14 = atr14_sma(t, d0)
    nw20 = atr_wilder(t, d0)
    n = n14
    bars = bars_between(t, d0, dx)
    asset = asset_at(d0)
    budget = asset * weight[s]
    cap_notional = budget * pos_ratio[s]
    row = {
        "strategy": s, "ticker": t, "name": rt["name"], "buy_date": d0.isoformat(), "sell_date": dx.isoformat(),
        "hold_bdays": max(len(bars) - 1, 0), "buy_px": p0, "qty": q0, "sell_px": px,
        "pl_recorded": rt["pl_recorded"], "pl_gross_1unit": (px - p0) * q0, "ret_pct_1unit": (px - p0) / p0 * 100,
        "asset_at_entry": asset, "strategy_budget": budget, "notional_cap_pos_ratio": cap_notional,
        "notional_1unit": p0 * q0, "notional_1unit_over_cap_x": (p0 * q0) / cap_notional if cap_notional else float("nan"),
        "N_atr14": n14, "N_pct_of_price": n14 / p0 * 100 if p0 else float("nan"), "N_wilder20": nw20,
        "turtle_unit_qty_theory": math.floor(budget * risk_pct[s] / n14) if n14 > 0 else None,
        # 실제 랏이 터틀 유닛 몇 개분인가 = q0×N ÷ (예산×risk_pct). 1.0 = 정확히 1유닛, 3.0 = 1주가 이미 3유닛 리스크
        "lot_in_turtle_units": (q0 * n14) / (budget * risk_pct[s]) if (n14 > 0 and budget > 0) else float("nan"),
    }
    if bars and n > 0:
        highs = [b["h"] for b in bars]
        lows = [b["l"] for b in bars]
        mfe = max(highs) - p0
        mae = p0 - min(lows)
        row.update({
            "MFE_won": mfe, "MFE_N": mfe / n, "MFE_pct": mfe / p0 * 100,
            "MAE_won": mae, "MAE_N": mae / n, "MAE_pct": mae / p0 * 100,
            "mae_hit_2N": mae >= 2 * n,
        })
        for k, lab in ((0.5, "0.5N"), (1.0, "1N"), (1.5, "1.5N"), (2.0, "2N")):
            hit = next((i for i, h in enumerate(highs) if h >= p0 + k * n), None)
            row[f"reach_{lab}"] = hit is not None
            row[f"days_to_{lab}"] = hit
        # 진입 후 20영업일 MFE (실제 청산과 무관 — 청산 규약이 추세를 자르는지 맥락)
        b20 = [b for b in daily[t] if b["d"] >= d0][:21]
        if b20:
            row["MFE20_N"] = (max(b["h"] for b in b20) - p0) / n
            row["MFE20_pct"] = (max(b["h"] for b in b20) - p0) / p0 * 100
            row["bars_after_entry_avail"] = len(b20) - 1
        for mode in ("pess", "opt", "pess_1N", "pess_budget"):
            if mode == "pess_1N":
                sim = simulate(t, p0, q0, n, d0, dx, px, "pess", step=1.0)
            elif mode == "pess_budget":
                sim = simulate(t, p0, q0, n, d0, dx, px, "pess", budget_cap=budget)
            else:
                sim = simulate(t, p0, q0, n, d0, dx, px, mode)
            if sim["ok"]:
                row.update({
                    f"{mode}_units": sim["units"], f"{mode}_add_days": "|".join(map(str, sim["add_days"])),
                    f"{mode}_unit_px": "|".join(map(str, sim["unit_px"])), f"{mode}_avg_px": round(sim["avg_px"]),
                    f"{mode}_final_stop": round(sim["final_stop"]), f"{mode}_exit_px": sim["exit_px"],
                    f"{mode}_exit_reason": sim["exit_reason"], f"{mode}_exit_day": sim["exit_day"],
                    f"{mode}_pnl": sim["pnl"], f"{mode}_pnl_delta_vs_1unit": sim["pnl"] - (px - p0) * q0,
                    f"{mode}_notional": sim["notional"], f"{mode}_notional_pct_asset": sim["notional"] / asset * 100,
                    f"{mode}_notional_over_budget_x": sim["notional"] / budget,
                    f"{mode}_risk_won_at_final_stop": sim["risk_won"], f"{mode}_risk_pct_asset": sim["risk_won"] / asset * 100,
                    f"{mode}_pnl_pct_asset": sim["pnl"] / asset * 100,
                })
    else:
        row["note"] = "no_bars_or_N0"
    rows.append(row)

# ── 오픈 포지션 (관찰 전용: would_add 마커 상당) ─────────────────
open_rows = []
for (s, t), lots in open_positions:
    for lot in lots:
        d0, p0, q0 = lot["ts"].date(), lot["px"], lot["q"]
        n = atr14_sma(t, d0)
        bars = bars_between(t, d0, ASOF)
        if not bars or n <= 0:
            continue
        highs = [b["h"] for b in bars]
        mfe = max(highs) - p0
        asset = asset_at(d0)
        sim = simulate(t, p0, q0, n, d0, None, None, "pess")
        open_rows.append({
            "strategy": s, "ticker": t, "name": lot["name"], "buy_date": d0.isoformat(), "buy_px": p0, "qty": q0,
            "last_close": bars[-1]["c"], "hold_bdays": len(bars) - 1, "N_atr14": n, "N_pct": n / p0 * 100,
            "MFE_N": mfe / n, "MFE_pct": mfe / p0 * 100,
            "reach_0.5N": any(h >= p0 + 0.5 * n for h in highs), "reach_1N": any(h >= p0 + n for h in highs),
            "reach_1.5N": any(h >= p0 + 1.5 * n for h in highs),
            "pess_units_would_hold": sim.get("units"), "pess_add_days": "|".join(map(str, sim.get("add_days", []))),
            "pess_final_stop": round(sim["final_stop"]) if sim.get("ok") else None,
            "pess_exit_reason": sim.get("exit_reason"), "pess_mark_pnl": sim.get("pnl"),
            "pess_notional": sim.get("notional"), "notional_pct_asset": (sim.get("notional") or 0) / asset * 100,
            "risk_pct_asset_at_final_stop": (sim.get("risk_won") or 0) / asset * 100,
            "unit_notional_1": p0 * q0, "notional_cap_pos_ratio": asset * weight[s] * pos_ratio[s],
        })

# ── CSV ──────────────────────────────────────────────────────────
def write_csv(path, rs):
    keys = []
    for r in rs:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rs:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})

write_csv(f"{HERE}/roundtrips.csv", rows)
write_csv(f"{HERE}/open_positions.csv", open_rows)


# ── 요약 ─────────────────────────────────────────────────────────
def agg(rs, mode):
    rs = [r for r in rs if f"{mode}_pnl" in r]
    if not rs:
        return {}
    base = [r["pl_gross_1unit"] for r in rs]
    pyr = [r[f"{mode}_pnl"] for r in rs]
    base_pct = [r["pl_gross_1unit"] / r["asset_at_entry"] * 100 for r in rs]
    pyr_pct = [r[f"{mode}_pnl_pct_asset"] for r in rs]
    units = [r[f"{mode}_units"] for r in rs]
    return {
        "N": len(rs),
        "base_win_rate": sum(1 for x in base if x > 0) / len(rs),
        "base_pnl_sum": sum(base), "base_pnl_avg": sum(base) / len(rs), "base_pnl_min": min(base), "base_pnl_max": max(base),
        "base_pnl_pct_asset_sum": sum(base_pct), "base_pnl_pct_asset_avg": sum(base_pct) / len(rs),
        "pyr_win_rate": sum(1 for x in pyr if x > 0) / len(rs),
        "pyr_pnl_sum": sum(pyr), "pyr_pnl_avg": sum(pyr) / len(rs), "pyr_pnl_min": min(pyr), "pyr_pnl_max": max(pyr),
        "pyr_pnl_pct_asset_sum": sum(pyr_pct), "pyr_pnl_pct_asset_avg": sum(pyr_pct) / len(rs),
        "pyr_pnl_pct_asset_min": min(pyr_pct), "pyr_pnl_pct_asset_max": max(pyr_pct),
        "delta_sum": sum(pyr) - sum(base),
        "trades_changed": sum(1 for r in rs if abs(r[f"{mode}_pnl_delta_vs_1unit"]) > 0.5),
        "trades_improved": sum(1 for r in rs if r[f"{mode}_pnl_delta_vs_1unit"] > 0.5),
        "trades_worsened": sum(1 for r in rs if r[f"{mode}_pnl_delta_vs_1unit"] < -0.5),
        "units_dist": {str(u): units.count(u) for u in sorted(set(units))},
        "reached_2units": sum(1 for u in units if u >= 2), "reached_4units": sum(1 for u in units if u >= 4),
        "pyr_stop_exits": sum(1 for r in rs if str(r[f"{mode}_exit_reason"]).startswith("pyr_stop")),
        "max_notional_pct_asset": max(r[f"{mode}_notional_pct_asset"] for r in rs),
        "max_risk_pct_asset_at_final_stop": max(r[f"{mode}_risk_pct_asset"] for r in rs),
        "avg_risk_pct_asset_at_final_stop": sum(r[f"{mode}_risk_pct_asset"] for r in rs) / len(rs),
        "notional_over_budget_cases": sum(1 for r in rs if r[f"{mode}_notional_over_budget_x"] > 1.0),
    }


def reach_stats(rs):
    rs = [r for r in rs if "MFE_N" in r]
    if not rs:
        return {}
    out = {"N": len(rs), "MFE_N_avg": sum(r["MFE_N"] for r in rs) / len(rs),
           "MFE_N_median": sorted(r["MFE_N"] for r in rs)[len(rs) // 2],
           "MFE_N_max": max(r["MFE_N"] for r in rs),
           "MAE_N_avg": sum(r["MAE_N"] for r in rs) / len(rs),
           "mae_hit_2N_count": sum(1 for r in rs if r["mae_hit_2N"]),
           "hold_bdays_avg": sum(r["hold_bdays"] for r in rs) / len(rs),
           "hold_bdays_max": max(r["hold_bdays"] for r in rs),
           "N_pct_of_price_avg": sum(r["N_pct_of_price"] for r in rs) / len(rs),
           "one_share_lots": sum(1 for r in rs if r["qty"] == 1),
           "notional_1unit_over_cap_count": sum(1 for r in rs if r["notional_1unit_over_cap_x"] > 1.0),
           "notional_1unit_over_cap_avg_x": sum(r["notional_1unit_over_cap_x"] for r in rs) / len(rs),
           "turtle_unit_qty_theory_ge1": sum(1 for r in rs if (r["turtle_unit_qty_theory"] or 0) >= 1),
           "lot_in_turtle_units_avg": sum(r["lot_in_turtle_units"] for r in rs) / len(rs),
           "lot_in_turtle_units_median": sorted(r["lot_in_turtle_units"] for r in rs)[len(rs) // 2],
           "lot_in_turtle_units_max": max(r["lot_in_turtle_units"] for r in rs),
           "lot_gt_1unit_count": sum(1 for r in rs if r["lot_in_turtle_units"] > 1.0),
           "lot_gt_2unit_count": sum(1 for r in rs if r["lot_in_turtle_units"] > 2.0),
           }
    for lab in ("0.5N", "1N", "1.5N", "2N"):
        hits = [r[f"days_to_{lab}"] for r in rs if r[f"reach_{lab}"]]
        out[f"reach_{lab}_count"] = len(hits)
        out[f"reach_{lab}_rate"] = len(hits) / len(rs)
        out[f"days_to_{lab}_avg"] = (sum(hits) / len(hits)) if hits else None
        out[f"days_to_{lab}_dist"] = {str(d): hits.count(d) for d in sorted(set(hits))} if hits else {}
    m20 = [r["MFE20_N"] for r in rs if "MFE20_N" in r]
    out["MFE20_N_avg"] = sum(m20) / len(m20) if m20 else None
    out["MFE20_reach_1.5N_count"] = sum(1 for r in rs if r.get("MFE20_N", 0) >= 1.5)
    out["MFE20_reach_3N_count"] = sum(1 for r in rs if r.get("MFE20_N", 0) >= 3.0)
    return out


def window(rs, days):
    cut = ASOF - timedelta(days=days)
    return [r for r in rs if date.fromisoformat(r["buy_date"]) >= cut]


MODES = ("pess", "opt", "pess_1N", "pess_budget")
summary = {"asof": ASOF.isoformat(), "weights": weight, "pos_ratio": pos_ratio, "risk_pct": risk_pct,
           "roundtrips_total": len(rows), "open_positions": len(open_rows)}
for s in STRATS + ("ALL",):
    rs = rows if s == "ALL" else [r for r in rows if r["strategy"] == s]
    summary[s] = {
        "all_time": {"reach": reach_stats(rs), **{m: agg(rs, m) for m in MODES}},
        "last_60d": {"reach": reach_stats(window(rs, 60)), **{m: agg(window(rs, 60), m) for m in MODES}},
    }
summary["open_positions_rows"] = open_rows
json.dump(summary, open(f"{HERE}/summary.json", "w"), indent=1, default=str, ensure_ascii=False)

# ── 가독 텍스트 ───────────────────────────────────────────────────
lines = []
P = lines.append
P(f"asof={ASOF} roundtrips={len(rows)} open={len(open_rows)} weights={weight} pos_ratio={pos_ratio}")
for s in STRATS + ("ALL",):
    for win in ("all_time", "last_60d"):
        r = summary[s][win]["reach"]
        if not r:
            P(f"\n## {s} / {win}: N=0"); continue
        P(f"\n## {s} / {win}: N={r['N']} 1주랏={r['one_share_lots']} 보유영업일 avg={r['hold_bdays_avg']:.1f} max={r['hold_bdays_max']} N%가격 avg={r['N_pct_of_price_avg']:.2f}%")
        P(f"  MFE_N avg={r['MFE_N_avg']:.2f} med={r['MFE_N_median']:.2f} max={r['MFE_N_max']:.2f} | MAE_N avg={r['MAE_N_avg']:.2f} (2N 관통 {r['mae_hit_2N_count']}) | MFE20_N avg={r['MFE20_N_avg']:.2f} (≥1.5N {r['MFE20_reach_1.5N_count']}, ≥3N {r['MFE20_reach_3N_count']})")
        P(f"  도달: 0.5N {r['reach_0.5N_count']}/{r['N']} ({r['reach_0.5N_rate']*100:.0f}%, d={r['days_to_0.5N_dist']}) | 1N {r['reach_1N_count']} ({r['reach_1N_rate']*100:.0f}%, d={r['days_to_1N_dist']}) | 1.5N {r['reach_1.5N_count']} ({r['reach_1.5N_rate']*100:.0f}%, d={r['days_to_1.5N_dist']}) | 2N {r['reach_2N_count']}")
        P(f"  1유닛 명목이 position_ratio 상한 초과: {r['notional_1unit_over_cap_count']}/{r['N']} (avg {r['notional_1unit_over_cap_avg_x']:.2f}×) | 터틀 이론 유닛수량 ≥1주: {r['turtle_unit_qty_theory_ge1']}/{r['N']} | 실제 랏=터틀유닛 avg {r['lot_in_turtle_units_avg']:.2f} med {r['lot_in_turtle_units_median']:.2f} max {r['lot_in_turtle_units_max']:.2f} (>1유닛 {r['lot_gt_1unit_count']}, >2유닛 {r['lot_gt_2unit_count']})")
        for mode in MODES:
            a = summary[s][win][mode]
            P(f"  [{mode}] base: win {a['base_win_rate']*100:.0f}% Σ{a['base_pnl_sum']:,.0f} avg {a['base_pnl_avg']:,.0f} min {a['base_pnl_min']:,.0f} max {a['base_pnl_max']:,.0f} (Σ자본% {a['base_pnl_pct_asset_sum']:.2f})")
            P(f"         pyr : win {a['pyr_win_rate']*100:.0f}% Σ{a['pyr_pnl_sum']:,.0f} avg {a['pyr_pnl_avg']:,.0f} min {a['pyr_pnl_min']:,.0f} max {a['pyr_pnl_max']:,.0f} (Σ자본% {a['pyr_pnl_pct_asset_sum']:.2f}, 최악 1건 {a['pyr_pnl_pct_asset_min']:.2f}%) Δ={a['delta_sum']:,.0f} 변화 {a['trades_changed']} (개선 {a['trades_improved']}/악화 {a['trades_worsened']}) 유닛분포 {a['units_dist']} 피라미드손절청산 {a['pyr_stop_exits']} 명목max {a['max_notional_pct_asset']:.1f}%자산 예산초과 {a['notional_over_budget_cases']} 최종손절리스크 avg {a['avg_risk_pct_asset_at_final_stop']:.2f}% max {a['max_risk_pct_asset_at_final_stop']:.2f}%")
P("\n## 왕복 상세 (pess)")
for r in rows:
    if "MFE_N" not in r:
        P(f"  {r['strategy'][:8]} {r['ticker']} {r['name'][:6]} {r['buy_date']}→{r['sell_date']} NO BARS/N0"); continue
    P(f"  {r['strategy'][:8]} {r['ticker']} {r['name'][:7]:7s} {r['buy_date']}→{r['sell_date']} hold={r['hold_bdays']} q={r['qty']} px={r['buy_px']:.0f}→{r['sell_px']:.0f} N={r['N_atr14']:.0f}({r['N_pct_of_price']:.1f}%) MFE={r['MFE_N']:.2f}N MAE={r['MAE_N']:.2f}N MFE20={r.get('MFE20_N',float('nan')):.2f}N 0.5N@{r['days_to_0.5N']} 1N@{r['days_to_1N']} 1.5N@{r['days_to_1.5N']} | base {r['pl_gross_1unit']:,.0f} → pyr {r['pess_pnl']:,.0f} units={r['pess_units']} exit={r['pess_exit_reason']} stop={r['pess_final_stop']} notional={r['pess_notional_pct_asset']:.1f}%자산 risk={r['pess_risk_pct_asset']:.2f}% cap×={r['notional_1unit_over_cap_x']:.2f}")
P("\n## 오픈 포지션 (pess, 09-02 종가 평가)")
for r in open_rows:
    P(f"  {r['strategy'][:8]} {r['ticker']} {r['name'][:7]:7s} {r['buy_date']} hold={r['hold_bdays']} q={r['qty']} px={r['buy_px']:.0f} last={r['last_close']} N={r['N_atr14']:.0f}({r['N_pct']:.1f}%) MFE={r['MFE_N']:.2f}N 0.5N={r['reach_0.5N']} 1N={r['reach_1N']} 1.5N={r['reach_1.5N']} units={r['pess_units_would_hold']} adds@{r['pess_add_days']} stop={r['pess_final_stop']} exit={r['pess_exit_reason']} markpnl={r['pess_mark_pnl']:,.0f} notional={r['notional_pct_asset']:.1f}%자산 risk={r['risk_pct_asset_at_final_stop']:.2f}% cap={r['notional_cap_pos_ratio']:,.0f} unit1={r['unit_notional_1']:,.0f}")
open(f"{HERE}/summary.txt", "w").write("\n".join(lines))
print("\n".join(lines))
