#!/usr/bin/env python3
"""칸 수·예산 사용률 분석 (2026-10-11) — extract.py 가 만든 JSON 을 읽어 표를 만든다.

로컬 실행(DB·KIS 무접촉):
    python analyze.py <raw_20261011.json>  > analysis_out.txt
보유 재구성은 리포의 순수 함수 `tools/slot_utilization_review.build_daily_timeline`
(단위 테스트 13개, 10-02 소급 오염 결함 수정본)을 그대로 쓴다.

판정 규칙 = 지시서 `_workspace/design/2026-10-02_slot_utilization_handoff.md` §4 그대로(측정 전 고정).
"""
from __future__ import annotations

import csv
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
from slot_utilization_review import build_daily_timeline, filter_trade_events  # noqa: E402

KST = timezone(timedelta(hours=9))
OUT_DIR = Path(__file__).resolve().parent

PRIMARY = ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-28", "2026-09-29",
           "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-06", "2026-10-07", "2026-10-08"]

# 전략별 평가일 — 매수를 멈춘 날·전략이 실매매가 아니던 날을 뺀다(지시서 §3.3).
#   10-08 = 다섯 전략 buy_paused(07:08) · momentum/VB/LTV 는 그날 예산 0 또는 퇴출
EXCLUDE = {
    "kojiro": {"2026-10-08"},
    "vcp_breakout": {"2026-10-08"},
    # BFB entry_end 09:04 (09-25 21:52 ~ 09-29 16:05) → 09-28·29 제외
    "bull_flag_breakout": {"2026-09-28", "2026-09-29", "2026-10-08"},
    # donchian buy_paused 09-27 16:14 ~ 10-06 21:35 → 09-28~10-06 제외, 10-08 제외
    "donchian_swing": {"2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01",
                       "2026-10-02", "2026-10-06", "2026-10-08"},
    # momentum 비중 0 — 10-07 10:58 (아침 매매는 0.03 으로 돌았다) → 10-08 제외
    "momentum": {"2026-10-08"},
    # VB 섀도 전환 10-06 21:35 → 10-07·08 제외
    "volatility_breakout": {"2026-10-07", "2026-10-08"},
    # LTV 퇴출 09-28 21:42 → 09-29~ 제외 (판정 안 함, 참고만)
    "long_tail_volatility": {d for d in PRIMARY if d >= "2026-09-29"},
    # etf_trend 실매수 = 10-07 하루 (10-06 21:35 섀도 해제, 10-08 buy_paused)
    "etf_trend": {d for d in PRIMARY if d != "2026-10-07"},
}
SWING = ("kojiro", "donchian_swing", "bull_flag_breakout", "vcp_breakout", "etf_trend")
INTRADAY_STYLE = ("volatility_breakout", "momentum", "long_tail_volatility")  # 당일·익일 청산형


def max_pos_for(s: str, day: str, cfg: dict) -> int:
    if s == "donchian_swing" and day < "2026-10-07":
        return 5  # 10-06 21:35 PUT 이전 값(10-02 측정·워크리스트)
    return int(cfg[s]["params"]["max_positions"])


def pos_ratio_for(s: str, day: str, cfg: dict) -> float:
    if s == "donchian_swing" and day < "2026-10-07":
        return 0.20
    return float(cfg[s]["params"]["position_ratio"])


def main(path: str) -> None:
    d = json.load(open(path))
    cfg = {r["strategy_id"]: r for r in d["strategy_config"]}
    strategies = [s for s in cfg if s not in ("ndx2x_riskoff",)]

    rows = []
    for r in d["trades"]:
        r = dict(r)
        r["timestamp"] = datetime.fromisoformat(r.pop("ts_kst")).replace(tzinfo=KST)
        rows.append(r)
    events = filter_trade_events(rows)
    ev_strats = sorted({e.strategy for e in events})
    all_strats = sorted(set(strategies) | set(ev_strats))

    total_days = sorted({r["date"][:10] for r in d["daily_performance"] if r["strategy"] == "total"})
    trade_days = sorted({e.timestamp.date().isoformat() for e in events})
    days = sorted(set(total_days) | set(trade_days))
    tl = build_daily_timeline(events, strategies=all_strats, trading_days=days)

    # 장중 최대 매입원가(전략·날) — 이벤트 순회로 직접
    intraday_cost: dict[tuple[str, str], float] = {}
    lots_cost: dict[tuple[str, str], list] = {}
    by_day = defaultdict(list)
    for e in events:
        by_day[e.timestamp.date().isoformat()].append(e)
    for day in days:
        for s in all_strats:
            snap = tl["eod"].get((s, prev_day(days, day)), [])
            for x in snap:
                lots_cost[(s, x["ticker"])] = [x["quantity"], x["cost_basis"]]
        cur = defaultdict(float)
        for s in all_strats:
            cur[s] = sum(v[1] for (ss, _t), v in lots_cost.items() if ss == s and v[0] > 0)
            intraday_cost[(s, day)] = cur[s]
        for e in sorted(by_day.get(day, []), key=lambda e: e.timestamp):
            k = (e.strategy, e.ticker)
            q, c = lots_cost.get(k, [0, 0.0])
            if e.trade_type == "BUY":
                q += e.quantity; c += e.price * e.quantity
            else:
                sq = min(e.quantity, q)
                c -= (c / q * sq) if q else 0.0
                q -= sq
                if q <= 0:
                    q, c = 0, 0.0
            lots_cost[k] = [q, c]
            tot = sum(v[1] for (ss, _t), v in lots_cost.items() if ss == e.strategy and v[0] > 0)
            intraday_cost[(e.strategy, day)] = max(intraday_cost[(e.strategy, day)], tot)
        lots_cost = {}  # 다음 날은 장마감 스냅샷에서 다시 시작

    # 예산 — daily_performance: 예산 ≈ total_asset − daily_realized_pnl (지시서 §1-5)
    budget, net_asset, deposit = {}, {}, {}
    for r in d["daily_performance"]:
        dd = r["date"][:10]
        if r["strategy"] == "total":
            net_asset[dd] = float(r["total_asset"] or 0)
            deposit[dd] = float(r.get("deposit") or 0)
        else:
            budget[(r["strategy"], dd)] = float(r["total_asset"] or 0) - float(r["daily_realized_pnl"] or 0)
    # 10-07 은 장중(10:58)에 비중이 바뀌었다 — 아침 매수 창의 예산을 로그 값으로 덮는다
    #   (부팅 07:45 `자금 분배` 로그: momentum 142,272 · etf_trend 94,848 — 그 밖은 같음)
    budget_morning_1007 = {"momentum": 142272.0, "etf_trend": 94848.0}

    out = []
    p = out.append
    p(f"보유 재구성 일수 {len(days)} ({days[0]}~{days[-1]}) · 보유 초과 매도 경고 {len(tl['oversell_warnings'])}건")
    for w in tl["oversell_warnings"]:
        p(f"  oversell {w}")

    # 교차 검증 — 마지막 날 재구성 vs positions
    last = days[-1]
    recon = defaultdict(int)
    for s in all_strats:
        for x in tl["eod"].get((s, last), []):
            recon[(s, x["ticker"])] += x["quantity"]
    live = {(r["strategy_id"], r["ticker"]): r["quantity"] for r in d["positions"]}
    diffs = [(k, recon.get(k, 0), live.get(k, 0)) for k in sorted(set(recon) | set(live)) if recon.get(k, 0) != live.get(k, 0)]
    p(f"\n[교차검증] {last} 재구성 vs positions 테이블: 불일치 {len(diffs)}건")
    for x in diffs:
        p(f"  {x}")

    summary = []
    daily_rows = []
    p("\n[전략별 일자 표] 날짜 | 예산 | 장마감 보유수/정원 | 장중최대 | 장마감 매입원가 | 장중최대 매입원가")
    for s in all_strats:
        if s not in cfg:
            continue
        evd = [x for x in PRIMARY if x not in EXCLUDE.get(s, set())]
        if not evd:
            continue
        p(f"\n== {s} (평가일 {len(evd)}: {', '.join(x[5:] for x in evd)})")
        eodc, intc, use_eod, use_int, bud_eod, bud_int = [], [], [], [], [], []
        full_eod = full_int = zero = 0
        for day in evd:
            mp = max_pos_for(s, day, cfg)
            ce = tl["eod_count"].get((s, day), 0)
            ci = tl["intraday_max_count"].get((s, day), 0)
            cost_e = tl["eod_cost_total"].get((s, day), 0.0)
            cost_i = intraday_cost.get((s, day), 0.0)
            b = budget.get((s, day))
            if day == "2026-10-07" and s in budget_morning_1007:
                b = budget_morning_1007[s]
            eodc.append(ce); intc.append(ci)
            use_eod.append(ce / mp); use_int.append(ci / mp)
            full_eod += ce >= mp; full_int += ci >= mp; zero += ce == 0
            if b:
                bud_eod.append(cost_e / b); bud_int.append(cost_i / b)
            p(f"  {day} | {b and round(b):>9,} | {ce}/{mp} | {ci} | {round(cost_e):>9,} | {round(cost_i):>9,}")
            daily_rows.append({"strategy": s, "date": day, "budget": round(b or 0), "max_positions": mp,
                               "eod_count": ce, "intraday_max_count": ci, "eod_cost": round(cost_e),
                               "intraday_max_cost": round(cost_i),
                               "budget_use_eod": round(cost_e / b, 4) if b else None,
                               "budget_use_intraday": round(cost_i / b, 4) if b else None})
        n = len(evd)
        # 랏 모양 — 주 기간 평가일 매수
        lots = [l for l in tl["lots"] if l["strategy"] == s and l["date"] in evd]
        qtys = [l["quantity"] for l in lots]
        qlist = []
        for l in lots:
            b = budget.get((s, l["date"]))
            if l["date"] == "2026-10-07" and s in budget_morning_1007:
                b = budget_morning_1007[s]
            if b and l["price"]:
                qlist.append(b * pos_ratio_for(s, l["date"], cfg) / l["price"])
        one = sum(1 for q in qtys if q == 1)
        rec = {
            "strategy": s, "eval_days": n,
            "max_positions_now": cfg[s]["params"].get("max_positions"),
            "position_ratio_now": cfg[s]["params"].get("position_ratio"),
            "sizing_mode_now": cfg[s]["params"].get("sizing_mode"),
            "full_days_eod": full_eod, "full_days_eod_pct": round(100 * full_eod / n),
            "full_days_intraday": full_int, "full_days_intraday_pct": round(100 * full_int / n),
            "avg_slot_use_eod_pct": round(100 * st.mean(use_eod)),
            "avg_slot_use_intraday_pct": round(100 * st.mean(use_int)),
            "zero_days_eod": zero,
            "budget_use_eod_mean_pct": round(100 * st.mean(bud_eod)) if bud_eod else None,
            "budget_use_eod_median_pct": round(100 * st.median(bud_eod)) if bud_eod else None,
            "budget_use_intraday_mean_pct": round(100 * st.mean(bud_int)) if bud_int else None,
            "buys": len(qtys), "one_share_pct": round(100 * one / len(qtys)) if qtys else None,
            "median_qty": st.median(qtys) if qtys else None,
            "median_q": round(st.median(qlist), 2) if qlist else None,
        }
        summary.append(rec)
        p(f"  → {rec}")

    # 스윙 — funnel 최종 생존 중 미매수 수, 칸 찬 날 vs 아닌 날
    fin: dict[tuple[str, str], tuple[int, set]] = {}
    for r in d["funnel"]:
        if r.get("is_provisional"):
            continue
        k = (r["strategy_id"], r["target_date"][:10])
        if k not in fin or r["step_no"] >= fin[k][0]:
            t = r["survived_tickers"] or []
            fin[k] = (r["step_no"], {str(x.get("ticker", x)) if isinstance(x, dict) else str(x) for x in t})
    p("\n[스윙 funnel] 날짜별 최종 단계 생존 수 · 그날 장마감 보유 · 미매수 생존 · 칸 찬 날 여부")
    funnel_cmp = {}
    for s in SWING:
        evd = [x for x in PRIMARY if x not in EXCLUDE.get(s, set())]
        fulls, others = [], []
        for day in evd:
            f = fin.get((s, day))
            if f is None:
                p(f"  {s} {day} funnel 없음")
                continue
            held = {x["ticker"] for x in tl["eod"].get((s, day), [])}
            bought_today = {l["ticker"] for l in tl["lots"] if l["strategy"] == s and l["date"] == day}
            missed = len(f[1] - held - bought_today)
            mp = max_pos_for(s, day, cfg)
            isfull = tl["intraday_max_count"].get((s, day), 0) >= mp or tl["eod_count"].get((s, day), 0) >= mp
            (fulls if isfull else others).append(missed)
            p(f"  {s} {day} step{f[0]} 생존 {len(f[1])} · 보유 {len(held)} · 미매수 {missed} · 칸찬날={isfull}")
        funnel_cmp[s] = (fulls, others)
        p(f"  → {s}: 칸찬날 n={len(fulls)} 평균 {st.mean(fulls) if fulls else '-'} · 아닌날 n={len(others)} 평균 {st.mean(others) if others else '-'}")

    # 계좌 전체 현금
    p("\n[계좌 전체] 날짜 | 순자산(total 행) | 전 전략 장마감 매입원가 | 주식 비중 | 현금 비중 | 의도 현금 | 의도 밖 현금")
    acct = []
    for day in PRIMARY:
        na = net_asset.get(day)
        if not na:
            continue
        inv = sum(tl["eod_cost_total"].get((s, day), 0.0) for s in all_strats)
        intended = 0.05 if day >= "2026-09-28" else 0.0  # cash_usage_ratio 0.95 = 09-28 21:42~ (09-29 부팅부터)
        if day == "2026-09-28":
            intended = 0.0
        cash = 1 - inv / na
        acct.append((day, na, inv, cash, intended))
        p(f"  {day} | {round(na):>10,} | {round(inv):>10,} | {100*inv/na:5.1f}% | {100*cash:5.1f}% | {100*intended:.0f}% | {100*(cash-intended):5.1f}%")

    # 성과 — 주 기간 청산(매도) 실현손익 개수
    p("\n[표본] 주 기간 평가일 중 매도 체결 건수(청산 표본)")
    for s in all_strats:
        evd = [x for x in PRIMARY if x not in EXCLUDE.get(s, set())]
        n_sell = sum(1 for e in events if e.strategy == s and e.trade_type == "SELL" and e.timestamp.date().isoformat() in evd)
        p(f"  {s}: {n_sell}")

    # 비교 기간 — 09-21 이전 60 거래일(입금 전)
    cmp_days = [x for x in total_days if x < "2026-09-21"][-60:]
    p(f"\n[비교 기간] {cmp_days[0]}~{cmp_days[-1]} ({len(cmp_days)}거래일, 입금 전 — 주 기간과 섞지 않음)")
    for s in all_strats:
        if s not in cfg or s == "etf_trend":
            continue
        cs = [tl["eod_count"].get((s, x), 0) for x in cmp_days]
        ci = [tl["intraday_max_count"].get((s, x), 0) for x in cmp_days]
        mp = int(cfg[s]["params"]["max_positions"]) if s != "donchian_swing" else 5
        bu = [tl["eod_cost_total"].get((s, x), 0) / budget[(s, x)] for x in cmp_days if budget.get((s, x))]
        lots = [l["quantity"] for l in tl["lots"] if l["strategy"] == s and l["date"] in cmp_days]
        p(f"  {s}: 장마감 칸찬날 {sum(c>=mp for c in cs)}/{len(cs)} · 장중 칸찬날 {sum(c>=mp for c in ci)} · 평균보유 {st.mean(cs):.2f}/{mp}"
          f" · 예산사용 평균 {100*st.mean(bu) if bu else 0:.0f}% · 매수 {len(lots)}건 1주 {100*sum(q==1 for q in lots)/len(lots) if lots else 0:.0f}%"
          f"  (※ 정원은 현재값 가정 — 비교 기간 중 변경 이력 미보존)")

    print("\n".join(out))
    with open(OUT_DIR / "strategy_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader(); w.writerows(summary)
    with open(OUT_DIR / "daily_by_strategy.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(daily_rows[0].keys()))
        w.writeheader(); w.writerows(daily_rows)


def prev_day(days: list[str], day: str) -> str:
    i = days.index(day)
    return days[i - 1] if i > 0 else ""


if __name__ == "__main__":
    main(sys.argv[1])
