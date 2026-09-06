#!/usr/bin/env python3
"""직접 증거 2종 CSV 생성."""
import csv
from collections import defaultdict

d = defaultdict(dict)
for line in open("data/sample_daily.usv", encoding="utf-8"):
    t, dt, o, h, lo, c = line.rstrip("\n").split("\x1f")
    d[t][dt] = (int(o), int(h), int(lo), int(c))

# A. [breakout_open_confirm] 스탬프 시가 vs KRX 일봉 시가 (2026-09-03, 일봉 정상일)
stamps = [
    ("2026-09-03","volatility_breakout","000270",125500),("2026-09-03","volatility_breakout","000720",111600),
    ("2026-09-03","volatility_breakout","001820",114000),("2026-09-03","volatility_breakout","002990",17350),
    ("2026-09-03","volatility_breakout","003160",30200),
    ("2026-09-03","long_tail_volatility","000720",111600),("2026-09-03","long_tail_volatility","000880",123000),
    ("2026-09-03","long_tail_volatility","001450",52900),("2026-09-03","long_tail_volatility","001820",114000),
    ("2026-09-03","long_tail_volatility","003670",177400),
]
prevd = "2026-09-02"
rows = []
for dt, sid, tk, stamped in stamps:
    o, h, lo, c = d[tk][dt]; pc = d[tk][prevd][3]
    rows.append(dict(date=dt, strategy=sid, ticker=tk, stamped_open=stamped, krx_open=o,
        krx_low=lo, krx_high=h, prev_close=pc,
        matches_krx_open=int(stamped == o),
        stamped_vs_krxopen_bp=round((stamped-o)/o*10000,1),
        stamped_vs_prevclose_bp=round((stamped-pc)/pc*10000,1),
        stamped_below_krx_low=int(stamped < lo)))
with open("data/stamped_open_vs_krx.csv","w",newline="",encoding="utf-8") as fh:
    w=csv.DictWriter(fh,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print("A. [breakout_open_confirm] 스탬프 시가 vs KRX 일봉 시가 (2026-09-03)")
print(f"{'strat':6}{'tk':8}{'스탬프':>9}{'KRX시가':>9}{'KRX저가':>9}{'전일종가':>9}{'일치':>6}{'vs시가bp':>9}")
for r in rows:
    print(f"{r['strategy'][:2].upper():6}{r['ticker']:8}{r['stamped_open']:9d}{r['krx_open']:9d}"
          f"{r['krx_low']:9d}{r['prev_close']:9d}{'O' if r['matches_krx_open'] else 'X':>6}{r['stamped_vs_krxopen_bp']:9.0f}")
m=sum(r['matches_krx_open'] for r in rows)
print(f"  => KRX 시가와 일치: {m}/{len(rows)}, 불일치 {len(rows)-m}/{len(rows)}")

# B. 로그된 매수신호 목표가 역산 (K 4자리 일치로 검증된 재구성)
sig = [("2026-09-03","105560","KB금융",174146,0.5918,174000),
       ("2026-09-03","086790","하나금융지주",137799,0.5310,137700),
       ("2026-09-04","000270","기아",131019,0.4716,131200),
       ("2026-09-04","108490","로보티즈",270682,0.5398,None),
       ("2026-09-04","078930","GS",125081,0.5213,125100)]
prev_of = {"2026-09-03":"2026-09-02","2026-09-04":"2026-09-03"}
out=[]
print("\nB. 로그된 목표가 -> 사용된 '시가' 역산")
print(f"{'date':11}{'tk':8}{'name':13}{'목표가':>9}{'offset':>8}{'사용시가':>9}{'KRX시가':>9}{'KRX저가':>9}{'전일종가':>9}{'판정':>18}")
for dt,tk,nm,tgt,K,fill in sig:
    pd_=prev_of[dt]; po,ph,pl,pc = d[tk][pd_]
    rng=ph-pl; base=int(rng*K); off=int(base*1.3); implied=tgt-off
    cur = d[tk].get(dt)
    stub = (dt=="2026-09-04")
    ko,klo = (None,None) if stub else (cur[0],cur[2])
    verdict = "일봉스텁(비교불가)" if stub else ("KRX저가 미만!" if implied<klo else ("KRX시가 미만" if implied<ko else "KRX시가 이상"))
    print(f"{dt:11}{tk:8}{nm[:11]:13}{tgt:9d}{off:8d}{implied:9d}"
          f"{(ko if ko else 0):9d}{(klo if klo else 0):9d}{pc:9d}{verdict:>18}")
    out.append(dict(date=dt,ticker=tk,name=nm,logged_target=tgt,logged_k=K,prev_range=rng,
        offset=off,implied_open=implied,krx_open=ko or "",krx_low=klo or "",prev_close=pc,
        fill=fill or "",verdict=verdict))
with open("data/logged_signal_reconstruction.csv","w",newline="",encoding="utf-8") as fh:
    w=csv.DictWriter(fh,fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
