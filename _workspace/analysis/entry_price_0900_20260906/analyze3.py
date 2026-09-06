#!/usr/bin/env python3
"""VB 09:00 포렌식 — 최종. implied_open 이 KRX 세션 안에서 도달 가능한 값인가."""
import csv, statistics as st
from collections import defaultdict

def load(p): return [l.rstrip("\n").split("\x1f") for l in open(p, encoding="utf-8")]
daily = defaultdict(list)
for t,d,o,h,lo,c,v in load("data/daily.usv"): daily[t].append((d,int(o),int(h),int(lo),int(c)))
for t in daily: daily[t].sort()
idx = {t:{r[0]:i for i,r in enumerate(rs)} for t,rs in daily.items()}
STUB = {"2026-09-04"}
def bp(b,x): return (x-b)/b*10000.0 if b else float("nan")

def build(kp=15, km=1.3):
    out=[]
    for d,tm,tk,name,price,qty,status,ordno in load("data/vb_buys_all.usv"):
        price=float(price)
        if tk not in idx or d not in idx[tk] or d in STUB: continue
        i=idx[tk][d]
        if i < kp+3: continue
        today,prev = daily[tk][i], daily[tk][i-1]
        ko,dh,dl,dc = today[1],today[2],today[3],today[4]
        pc = prev[4]; pr = prev[2]-prev[3]
        ns=[]
        for j in range(i-2,i-2-kp,-1):
            _,o,h,lo,c = daily[tk][j]
            if h-lo>0: ns.append(1-abs(c-o)/(h-lo))
        if len(ns)<kp or pr<=0: continue
        k=sum(ns)/len(ns); off=max(int(int(pr*k)*km),0)
        if off<=0: continue
        cap = price-off       # 사용된 시가의 상한
        out.append(dict(date=d,time=tm,ticker=tk,name=name,fill=price,offset=off,k=round(k,4),
            krx_open=ko,day_low=dl,day_high=dh,prev_close=pc,
            t_open=ko+off,t_prevc=pc+off,
            bp_vs_open=round(bp(ko+off,price),1), bp_vs_prevc=round(bp(pc+off,price),1),
            implied_open_cap=cap,
            cap_below_krxopen=int(cap<ko), cap_below_daylow=int(cap<dl),
            cap_vs_daylow_bp=round(bp(dl,cap),1), gap_bp=round(bp(pc,ko),1),
            early=int("09:00:00"<=tm<="09:01:30")))
    return out

for km in (1.3,1.0):
    rows=build(15,km)
    e=[r for r in rows if r["early"]]; l=[r for r in rows if not r["early"]]
    print(f"\n##### k_value_krx_main={km} #####")
    for rs,lab in ((e,"조기 09:00:00~09:01:30"),(l,"대조군 09:01:30 이후")):
        print(f"  {lab:26} n={len(rs):3d} | ①median {st.median([r['bp_vs_open'] for r in rs]):+8.1f}bp"
              f" | ②median {st.median([r['bp_vs_prevc'] for r in rs]):+7.1f}bp"
              f" | 사용시가<KRX시가 {sum(r['cap_below_krxopen'] for r in rs):3d}"
              f" | **사용시가<당일저가(KRX세션 도달불가) {sum(r['cap_below_daylow'] for r in rs):3d}**")
rows=build(15,1.3)
with open("data/vb_forensic_final.csv","w",newline="",encoding="utf-8") as fh:
    w=csv.DictWriter(fh,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print("\n--- 조기 코호트 상세 (k_mult=1.3) ---")
print(f"{'date':11}{'time':9}{'tk':7}{'name':13}{'fill':>8}{'off':>6}{'KRXop':>8}{'저가':>8}{'전일종':>8}{'사용시가≤':>9}{'<저가':>6}{'bp①':>7}{'bp②':>7}")
for r in rows:
    if r["early"]:
        print(f"{r['date']:11}{r['time']:9}{r['ticker']:7}{r['name'][:11]:13}{r['fill']:8.0f}{r['offset']:6d}"
              f"{r['krx_open']:8d}{r['day_low']:8d}{r['prev_close']:8d}{r['implied_open_cap']:9.0f}"
              f"{'YES' if r['cap_below_daylow'] else '-':>6}{r['bp_vs_open']:7.0f}{r['bp_vs_prevc']:7.0f}")
