#!/usr/bin/env python3
"""etf_trend 예산별 「0주」 비율 — extract_etf_universe.py 결과(JSON)로 로컬 계산(DB·KIS 무접촉).

수량식 = 코드 그대로(`turtle_sizing.compute_unit_qty_guarded`, min_vol_floor_pct=0):
    qty = min( floor(B × risk_pct ÷ N), B ÷ P, floor(B × position_ratio) ÷ P )
N = TR 14일 단순평균(`etf_trend_core.n14`). 최소 예산 = max(N ÷ risk_pct, P ÷ position_ratio).
실행: python etf_budget_floor.py etf_univ_bars.json
"""
import json, math, statistics as st, sys
from collections import defaultdict

RISK, PR = 0.01, 0.25
NET, CUR = 4_946_632, 0.95          # 10-08 순자산(total 행) · cash_usage_ratio
BUDGETS = {"0.02 (10-07 아침, 94,848)": 94_848, "0.05 (지금, 235,786)": 235_786}


def n14(rows, upto):
    rs = [r for r in rows if r["d"] <= upto]
    if len(rs) < 15:
        return None, None
    tr = []
    for i in range(1, len(rs)):
        h, l, pc = rs[i]["h"], rs[i]["l"], rs[i - 1]["c"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(tr[-14:]) / 14, rs[-1]["c"]


def qty(B, N, P):
    return max(0, min(math.floor(B * RISK / N), B // P, int(B * PR) // P))


def main(path):
    by = defaultdict(list)
    names = {}
    for r in json.load(open(path)):
        by[r["ticker"]].append(r); names[r["ticker"]] = r.get("name") or ""
    for asof in ("2026-10-06", "2026-10-08"):
        recs = []
        for t, rows in by.items():
            N, P = n14(rows, asof)
            if N:
                recs.append((t, names[t], N, P, max(N / RISK, P / PR)))
        print(f"\n== 기준 봉 {asof} — 밴드 통과 ETF {len(recs)}종목")
        for lab, B in BUDGETS.items():
            z = sum(1 for _t, _n, N, P, _m in recs if qty(B, N, P) == 0)
            one = sum(1 for _t, _n, N, P, _m in recs if qty(B, N, P) == 1)
            print(f"  비중 {lab}: 0주 {z}/{len(recs)} ({100*z/len(recs):.0f}%) · 1주 {one}")
        mins = sorted(m for *_x, m in recs)
        for pct in (50, 75, 90, 100):
            k = min(len(mins) - 1, math.ceil(len(mins) * pct / 100) - 1)
            print(f"  {pct}% 종목이 1주 이상 되는 최소 예산 {mins[k]:,.0f}원 = 비중 {mins[k]/(NET*CUR):.3f}")
        # 2주(=유닛 2) 이상 되는 예산 — 1주 문제(C) 해소선 참고
        mins2 = sorted(max(2 * N / RISK, 2 * P / PR) for _t, _n, N, P, _m in recs)
        k = math.ceil(len(mins2) * 0.5) - 1
        print(f"  중앙 종목이 2주 이상 되는 예산 {mins2[k]:,.0f}원 = 비중 {mins2[k]/(NET*CUR):.3f}")
        bind = sum(1 for _t, _n, N, P, _m in recs if N / RISK >= P / PR)
        print(f"  최소 예산을 정하는 쪽: 위험 유닛(N÷risk_pct) {bind}종목 · 명목 상한(P÷position_ratio) {len(recs)-bind}종목")


if __name__ == "__main__":
    main(sys.argv[1])
