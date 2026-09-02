"""적대적 재검산 — 렌즈 5 analyze.py 의 simulate() 를 그대로 재사용하되 변형 4종을 추가.
V0  = 원문 pess (q0 추가, D0 추가 허용)                                    ← 보고서 헤드라인
V1  = 추가 유닛 수량 = 터틀 이론 수량 floor(budget×risk_pct/N) (0 이면 추가 없음), D0 허용
V2  = q0 추가, 추가는 D1 부터만 (D0 전일고가 '유령 추가' 제거)
V3  = V1 + V2 결합 (이론 수량 + D1 부터)
V4  = V3 + 예산 클램프 (실 시스템 _apply_budget_limit 상당)
각 변형에 대해 Σbase / Σpyr / Δ / 개선·악화 / 추가유닛당 Δ 를 출력. 1/2N 과 1N 둘 다.
"""
import json, math, sys
from collections import defaultdict
from datetime import date, datetime
sys.path.insert(0, '/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/823ca95c-aa00-4436-b4f5-5eac77e3c1db/scratchpad/pyramid')
HERE = "/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/823ca95c-aa00-4436-b4f5-5eac77e3c1db/scratchpad/pyramid"
raw = json.load(open(f"{HERE}/raw.json"))
STRATS=("donchian_swing","kojiro"); MAX_UNITS=4; STOP_N=2.0
daily=defaultdict(list)
for r in raw["daily"]:
    if r["h"]<=0 or r["l"]<=0 or r["c"]<=0: continue
    daily[r["ticker"]].append({"d":date.fromisoformat(r["bas_dd"]),"o":r["o"],"h":r["h"],"l":r["l"],"c":r["c"]})
for t in daily: daily[t].sort(key=lambda x:x["d"])
perf_total={date.fromisoformat(p["d"]):p["total_asset"] for p in raw["perf"] if p["strategy"]=="total"}
perf_days=sorted(perf_total)
cfg={c["strategy_id"]:c for c in raw["cfg"]}
w_sum=sum(c["weight"] for c in raw["cfg"] if c["enabled"])
weight={s:cfg[s]["weight"]/w_sum for s in STRATS}
risk_pct={s:float(cfg[s]["params"].get("risk_pct",0.005)) for s in STRATS}
def asset_at(d):
    prev=[x for x in perf_days if x<=d]; return perf_total[prev[-1]] if prev else float('nan')
def atr14(t,entry,period=14):
    bars=[b for b in daily[t] if b["d"]<entry]
    if len(bars)<period+1: return 0.0
    rev=list(reversed(bars)); trs=[]
    for i in range(period):
        h,l,pc=rev[i]["h"],rev[i]["l"],rev[i+1]["c"]; trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(trs)/period
def bars_between(t,d0,d1): return [b for b in daily[t] if d0<=b["d"]<=d1]

trades=[x for x in raw["trades_strat"] if x["status"]=="COMPLETED"]; trades.sort(key=lambda x:x["ts_kst"])
open_lots=defaultdict(list); rts=[]
for tr in trades:
    key=(tr["strategy"],tr["ticker"]); ts=datetime.strptime(tr["ts_kst"],"%Y-%m-%d %H:%M:%S")
    if tr["trade_type"]=="BUY": open_lots[key].append({"ts":ts,"px":tr["price"],"q":tr["quantity"],"name":tr["ticker_name"]})
    else:
        if not open_lots[key]: continue
        lot=open_lots[key].pop(0)
        rts.append({"strategy":tr["strategy"],"ticker":tr["ticker"],"name":lot["name"],"d0":lot["ts"].date(),"p0":lot["px"],"q0":lot["q"],"dx":ts.date(),"px":tr["price"]})

def simulate(t,p0,q0,qadd,n,d0,dx,px,step,first_add_day=0,budget_cap=None):
    """analyze.py simulate(pess) 동일 규약 + qadd(추가 수량)·first_add_day 매개변수화."""
    bars=bars_between(t,d0,dx)
    if not bars or n<=0: return None
    levels=[p0+k*step*n for k in range(1,MAX_UNITS)]
    units=[(p0,q0)]; stop=p0-STOP_N*n; add_days=[]
    exit_px=None; reason=None
    for i,b in enumerate(bars):
        is_exit=(b["d"]==dx)
        if i>0 and b["o"]<=stop: exit_px,reason=b["o"],"gap"; break
        if b["l"]<=stop and not (is_exit and px>stop and i==0):
            if is_exit: exit_px,reason=px,"actual(stop_touched)"; break
            exit_px,reason=stop,"pyr_stop"; break
        if qadd>0 and i>=first_add_day:
            while len(units)<MAX_UNITS and b["h"]>=levels[len(units)-1]:
                lvl=levels[len(units)-1]; fill=lvl if i==0 else max(lvl,b["o"])
                if budget_cap is not None and sum(p*q for p,q in units)+fill*qadd>budget_cap: break
                units.append((fill,qadd)); add_days.append(i); stop=fill-STOP_N*n
        if add_days and add_days[-1]==i and b["l"]<=stop and not is_exit:
            exit_px,reason=stop,"pyr_stop_same_day"; break
        if is_exit: exit_px,reason=px,"actual"; break
    if exit_px is None: exit_px,reason=bars[-1]["c"],"open"
    totq=sum(q for _,q in units); cost=sum(p*q for p,q in units)
    return {"pnl":exit_px*totq-cost,"units":len(units),"extra_qty":totq-q0,"n":n,"reason":reason}

def run(variant,step):
    out=defaultdict(lambda: {"n":0,"base":0.0,"pyr":0.0,"imp":0,"wor":0,"extra_units_N":0.0,"eligible":0,"stopped":0,"base_N":0.0,"pyr_N":0.0})
    for rt in rts:
        s,t=rt["strategy"],rt["ticker"]; n=atr14(t,rt["d0"])
        if n<=0: continue
        asset=asset_at(rt["d0"]); budget=asset*weight[s]; unit_risk=budget*risk_pct[s]
        theory=math.floor(unit_risk/n)
        q0=rt["q0"]
        if variant=="V0": qadd,fad,cap=q0,0,None
        elif variant=="V1": qadd,fad,cap=theory,0,None
        elif variant=="V2": qadd,fad,cap=q0,1,None
        elif variant=="V3": qadd,fad,cap=theory,1,None
        elif variant=="V4": qadd,fad,cap=theory,1,budget
        elif variant=="V0b": qadd,fad,cap=q0,0,budget
        r=simulate(t,rt["p0"],q0,qadd,n,rt["d0"],rt["dx"],rt["px"],step,fad,cap)
        if not r: continue
        base=(rt["px"]-rt["p0"])*q0
        for key in (s,"ALL"):
            o=out[key]; o["n"]+=1; o["base"]+=base; o["pyr"]+=r["pnl"]
            d=r["pnl"]-base
            if d>0.5: o["imp"]+=1
            if d<-0.5: o["wor"]+=1
            o["extra_units_N"]+=r["extra_qty"]*n/unit_risk   # 추가된 리스크 유닛 수(터틀 유닛 환산)
            if qadd>0: o["eligible"]+=1
            if r["reason"].startswith("pyr_stop") or r["reason"]=="gap": o["stopped"]+=1
            o["base_N"]+=base/unit_risk; o["pyr_N"]+=r["pnl"]/unit_risk
    return out

print(f"roundtrips={len(rts)}  (theory qty ≥1: donchian {sum(1 for r in rts if r['strategy']=='donchian_swing' and math.floor(asset_at(r['d0'])*weight['donchian_swing']*risk_pct['donchian_swing']/max(atr14(r['ticker'],r['d0']),1e-9))>=1)}/24, kojiro {sum(1 for r in rts if r['strategy']=='kojiro' and math.floor(asset_at(r['d0'])*weight['kojiro']*risk_pct['kojiro']/max(atr14(r['ticker'],r['d0']),1e-9))>=1)}/14)")
desc={"V0":"원문 pess: q0 추가, D0 허용 (보고서 헤드라인)","V0b":"원문 pess_budget: q0 추가 + 예산클램프","V1":"이론수량 추가(0이면 추가 없음), D0 허용","V2":"q0 추가, D1 부터만(유령 D0 제거)","V3":"이론수량 + D1 부터","V4":"이론수량 + D1 부터 + 예산클램프 (실 시스템 최근사)"}
for step,lab in ((0.5,"1/2N"),(1.0,"1N")):
    print(f"\n################ step={lab}")
    for v in ("V0","V0b","V1","V2","V3","V4"):
        o=run(v,step)
        print(f"-- {v}: {desc[v]}")
        for k in ("donchian_swing","kojiro","ALL"):
            a=o[k]; d=a["pyr"]-a["base"]
            per=(d/a["extra_units_N"]) if a["extra_units_N"]>0 else float('nan')
            print(f"   {k:15s} n={a['n']:2d} elig={a['eligible']:2d} baseΣ={a['base']:>9,.0f} pyrΣ={a['pyr']:>9,.0f} Δ={d:>9,.0f}  imp/wor={a['imp']}/{a['wor']} stopped={a['stopped']:2d} 추가유닛(터틀환산)Σ={a['extra_units_N']:6.1f} Δ/추가유닛={per:>8,.0f}원  | N단위: base {a['base_N']:6.2f} → pyr {a['pyr_N']:6.2f}")
