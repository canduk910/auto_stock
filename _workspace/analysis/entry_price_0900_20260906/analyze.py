#!/usr/bin/env python3
"""VB 09:00 진입 포렌식 — 목표가 기준 재구성 (읽기 전용)."""
import csv, statistics as st
from collections import defaultdict

def load(p):
    return [l.rstrip("\n").split("\x1f") for l in open(p, encoding="utf-8")]

# daily: ticker -> ordered list of (bas_dd, o,h,l,c,vol)
daily = defaultdict(list)
for r in load("data/daily.usv"):
    t, d, o, h, lo, c, v = r
    daily[t].append((d, int(o), int(h), int(lo), int(c), int(v)))
for t in daily:
    daily[t].sort()

idx = {t: {d: i for i, (d, *_) in enumerate(rows)} for t, rows in daily.items()}

def bp(a, b):
    """a 대비 b 의 bp 차 ( (b-a)/a*10000 )"""
    return (b - a) / a * 10000.0 if a else float("nan")

rows_out = []
for r in load("data/vb_buys_all.usv"):
    d, tm, tk, name, price, qty, status, ordno = r
    price = float(price); qty = int(qty)
    if tk not in idx or d not in idx[tk]:
        rows_out.append(dict(date=d, time=tm, ticker=tk, name=name, fill=price, qty=qty, err="no_daily"))
        continue
    i = idx[tk][d]
    if i < 22:
        rows_out.append(dict(date=d, time=tm, ticker=tk, name=name, fill=price, qty=qty, err="short_history"))
        continue
    today = daily[tk][i]
    prev = daily[tk][i-1]
    krx_open, dhigh, dlow, dclose = today[1], today[2], today[3], today[4]
    prev_close = prev[4]
    prev_range = prev[2] - prev[3]
    # k = mean noise over the 21 sessions before prev (candles[1:] of a 22-row fetch)
    noises = []
    for j in range(i-2, i-23, -1):
        _, o, h, lo, c, _v = daily[tk][j]
        rng = h - lo
        if rng > 0:
            noises.append(1 - abs(c - o) / rng)
    if not noises or prev_range <= 0:
        rows_out.append(dict(date=d, time=tm, ticker=tk, name=name, fill=price, qty=qty, err="no_k"))
        continue
    k = sum(noises) / len(noises)
    offset = int(prev_range * k)
    t_open = krx_open + offset      # ① KRX 시가 기준
    t_prevc = prev_close + offset   # ② 전일종가 기준
    rows_out.append(dict(
        date=d, time=tm, ticker=tk, name=name, fill=price, qty=qty, err="",
        krx_open=krx_open, prev_close=prev_close, prev_range=prev_range,
        k=round(k, 4), offset=offset,
        t_open=t_open, t_prevc=t_prevc,
        bp_vs_open=round(bp(t_open, price), 1),
        bp_vs_prevc=round(bp(t_prevc, price), 1),
        gap_bp=round(bp(prev_close, krx_open), 1),
        fill_vs_krxopen_bp=round(bp(krx_open, price), 1),
        day_low=dlow, day_high=dhigh, day_close=dclose,
        fill_below_open=int(price < krx_open),
    ))

with open("data/vb_targets_all.csv", "w", newline="", encoding="utf-8") as fh:
    cols = ["date","time","ticker","name","fill","qty","err","krx_open","prev_close","prev_range","k","offset",
            "t_open","t_prevc","bp_vs_open","bp_vs_prevc","gap_bp","fill_vs_krxopen_bp",
            "day_low","day_high","day_close","fill_below_open"]
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
    for r in rows_out: w.writerow({c: r.get(c, "") for c in cols})

ok = [r for r in rows_out if not r["err"]]
def cohort(rs, label):
    if not rs: return
    a = [r["bp_vs_open"] for r in rs]; b = [r["bp_vs_prevc"] for r in rs]
    print(f"\n== {label}  n={len(rs)}")
    print(f"  ① KRX시가+offset 대비 체결가 : median {st.median(a):+8.1f}bp  mean {st.mean(a):+8.1f}bp")
    print(f"  ② 전일종가+offset 대비 체결가 : median {st.median(b):+8.1f}bp  mean {st.mean(b):+8.1f}bp")
    print(f"  |②| < |①| 인 건수: {sum(1 for r in rs if abs(r['bp_vs_prevc'])<abs(r['bp_vs_open']))}/{len(rs)}")
    print(f"  체결가 < KRX시가 : {sum(r['fill_below_open'] for r in rs)}")
    print(f"  갭(전일종가→KRX시가) median {st.median([r['gap_bp'] for r in rs]):+.1f}bp")

early = [r for r in ok if "09:00:00" <= r["time"] <= "09:01:30"]
late  = [r for r in ok if r["time"] > "09:01:30"]
early16 = [r for r in early if r["date"] >= "2026-07-01"]
cohort(early, "조기진입 09:00:00~09:01:30 (전 기간)")
cohort(early16, "조기진입 (2026-07-01~, 선행 리뷰 코호트 n=16)")
cohort(late, "대조군 09:01:30 이후")
print(f"\nerrors: {[(r['date'],r['ticker'],r['err']) for r in rows_out if r['err']]}")
