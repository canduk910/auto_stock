"""cycle361 — 일봉 보존 730 검토: S0 대리 진입 표본이 보존 깊이에 따라 어떻게 늘어나는가 (읽기 전용, 로컬).

입력 = cycle351 dump(`python cycle351_pyramid_s0_replay.py dump ...` 산출, 운영 DB SELECT 만).
대리 진입 정의 = cycle351 `proxy_entries` 를 **그대로 import** 해서 쓴다(재구현 0).

산출:
  1) 적격 종목-일(= 신호봉 i 가 60 ≤ i < n−1 인 칸) 당 대리 진입률 — 전체·월별
  2) 종목별 깊이 분포와 「구멍」(그 종목의 첫~마지막 날 사이 전역 거래일 수 − 보유 행 수)
  3) 깊이 D(영업일)로 모든 적격 종목이 이어진 이력을 가질 때의 기대 표본 = rate × U × (D − 61)
사용: python cycle361_retention_sample_estimate.py <dump.jsonl.gz>
"""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import cycle351_pyramid_s0_replay as s0  # noqa: E402


def main(dump_path: str) -> None:
    dump = s0.load_dump(dump_path)
    series = s0.build_series(dump)
    ded, raw_n = s0.proxy_entries(series)
    print(f"series(≥80봉)={len(series)}  entries(raw)={raw_n}  entries(dedup10)={len(ded)}")

    # 전역 거래일 달력 = 모든 종목 날짜 합집합
    cal = sorted({d for s in series.values() for d in s["dates"]})
    idx = {d: k for k, d in enumerate(cal)}
    print(f"전역 거래일 {len(cal)}일  {cal[0]} ~ {cal[-1]}")

    # 적격 종목-일 (신호봉 i 기준, 60 ≤ i < n−1)
    elig_by_date = Counter()
    for t, s in series.items():
        n = len(s["c"])
        for i in range(s0.WARM_I, n - 1):
            elig_by_date[s["dates"][i]] += 1
    ent_by_date = Counter()
    for t, i, _ in ded:
        ent_by_date[series[t]["dates"][i - 1]] += 1   # 신호봉 날짜
    tot_elig = sum(elig_by_date.values())
    rate = len(ded) / tot_elig
    print(f"적격 종목-일 {tot_elig:,}  → 진입률 {rate*1e4:.2f} / 1만 종목-일  (dedup 후)")

    by_m_e, by_m_n = Counter(), Counter()
    for d, k in elig_by_date.items():
        by_m_e[d.strftime("%Y-%m")] += k
    for d, k in ent_by_date.items():
        by_m_n[d.strftime("%Y-%m")] += k
    print("월별: 월 | 적격 종목-일 | 진입 | 1만당")
    rates = []
    for m in sorted(by_m_e):
        r = by_m_n[m] / by_m_e[m] if by_m_e[m] else 0
        rates.append((m, r, by_m_e[m]))
        print(f"  {m} | {by_m_e[m]:>7,} | {by_m_n[m]:>4} | {r*1e4:6.2f}")
    full = [r for m, r, e in rates if e > 20000]
    lo, hi = min(full), max(full)
    full_sorted = sorted(full)
    med = full_sorted[len(full_sorted)//2]
    print(f"월별 진입률(적격 2만 이상 월) 최소 {lo*1e4:.2f} · 중앙 {med*1e4:.2f} · 최대 {hi*1e4:.2f} (1만당)")

    # 깊이·구멍
    depth = Counter()
    holes = []
    for t, s in series.items():
        n = len(s["dates"])
        span = idx[s["dates"][-1]] - idx[s["dates"][0]] + 1
        holes.append(span - n)
        depth["<150" if n < 150 else ("150-224" if n < 225 else ">=225")] += 1
    hc = Counter("0" if h == 0 else ("1-5" if h <= 5 else ("6-20" if h <= 20 else ">20")) for h in holes)
    print("깊이:", dict(depth), " 구멍(거래일):", dict(hc))
    last = Counter(s["dates"][-1] for s in series.values())
    stale = sum(k for d, k in last.items() if d < cal[-1])
    print(f"마지막 봉이 전역 마지막 거래일보다 이른 종목 {stale} / {len(series)}")

    # 투영: 적격 종목 U 개가 모두 D 영업일 이어진 이력을 가질 때
    U_list = (970, 1244, 1900, 2318)
    print("\n투영 = rate × U × (D − 61)  (D=보유 영업일, 61=예열 60 + 마지막 봉)")
    for D in (233, 261, 480, 490):
        row = []
        for U in U_list:
            row.append(f"U={U}: {rate*U*(D-61):6.0f} [{lo*U*(D-61):5.0f}~{hi*U*(D-61):5.0f}]")
        print(f"  D={D}: " + " | ".join(row))


if __name__ == "__main__":
    main(sys.argv[1])
