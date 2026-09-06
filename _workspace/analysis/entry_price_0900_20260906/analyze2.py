#!/usr/bin/env python3
"""VB 09:00 진입 포렌식 — 운영 파라미터(k_period=15, k_value_krx_main=1.3) 재구성."""
import csv, statistics as st
from collections import defaultdict

def load(p): return [l.rstrip("\n").split("\x1f") for l in open(p, encoding="utf-8")]

daily = defaultdict(list)
for t, d, o, h, lo, c, v in load("data/daily.usv"):
    daily[t].append((d, int(o), int(h), int(lo), int(c), int(v)))
for t in daily: daily[t].sort()
idx = {t: {r[0]: i for i, r in enumerate(rs)} for t, rs in daily.items()}
DEGENERATE_DATES = {"2026-09-04"}   # stock_master_daily 스텁(O=H=L=C=전일종가)

def bp(base, x): return (x - base) / base * 10000.0 if base else float("nan")

def build(k_period=15, k_mult=1.3):
    out = []
    for d, tm, tk, name, price, qty, status, ordno in load("data/vb_buys_all.usv"):
        price = float(price)
        if tk not in idx or d not in idx[tk]: continue
        i = idx[tk][d]
        if i < k_period + 3: continue
        today, prev = daily[tk][i], daily[tk][i-1]
        krx_open, prev_close = today[1], prev[4]
        prev_range = prev[2] - prev[3]
        ns = []
        for j in range(i-2, i-2-k_period, -1):
            _, o, h, lo, c, _v = daily[tk][j]
            if h - lo > 0: ns.append(1 - abs(c - o) / (h - lo))
        if len(ns) < k_period or prev_range <= 0: continue
        k = sum(ns) / len(ns)
        base = int(prev_range * k)
        offset = max(int(base * k_mult), 0)
        if offset <= 0: continue
        implied_cap = price - offset          # target<=fill ⇒ 사용된 시가 상한
        out.append(dict(
            date=d, time=tm, ticker=tk, name=name, fill=price, qty=int(qty),
            k=round(k,4), prev_range=prev_range, offset=offset,
            krx_open=krx_open, prev_close=prev_close,
            t_open=krx_open+offset, t_prevc=prev_close+offset,
            bp_vs_open=round(bp(krx_open+offset, price),1),
            bp_vs_prevc=round(bp(prev_close+offset, price),1),
            implied_open_cap=implied_cap,
            cap_minus_krxopen_bp=round(bp(krx_open, implied_cap),1),
            cap_minus_prevc_bp=round(bp(prev_close, implied_cap),1),
            viol_open=int(implied_cap < krx_open),     # KRX시가 기준이면 물리적 모순
            viol_prevc=int(implied_cap < prev_close),
            gap_bp=round(bp(prev_close, krx_open),1),
            stub=int(d in DEGENERATE_DATES),
        ))
    return out

def report(rs, label):
    rs = [r for r in rs if not r["stub"]]
    if not rs: return
    print(f"\n== {label}   n={len(rs)}")
    print(f"   ① KRX시가+offset 대비 체결가  median {st.median([r['bp_vs_open'] for r in rs]):+8.1f}bp")
    print(f"   ② 전일종가+offset 대비 체결가  median {st.median([r['bp_vs_prevc'] for r in rs]):+8.1f}bp")
    print(f"   ①이 물리적으로 불가(체결가<목표가): {sum(r['viol_open'] for r in rs)}/{len(rs)}"
          f"   ②가 불가: {sum(r['viol_prevc'] for r in rs)}/{len(rs)}")
    print(f"   갭(전일종가→KRX시가) median {st.median([r['gap_bp'] for r in rs]):+.1f}bp")

for km in (1.3, 1.0):
    rows = build(15, km)
    early = [r for r in rows if "09:00:00" <= r["time"] <= "09:01:30"]
    late  = [r for r in rows if r["time"] > "09:01:30"]
    print(f"\n############ k_period=15, k_value_krx_main={km} ############")
    report(early, "조기진입 09:00:00~09:01:30")
    report([r for r in early if r["date"] >= "2026-07-01"], "조기진입 (2026-07-01~, 선행리뷰 n=16)")
    report(late, "대조군 09:01:30 이후")
    if km == 1.3:
        cols = list(rows[0].keys())
        with open("data/vb_targets_prod.csv","w",newline="",encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
