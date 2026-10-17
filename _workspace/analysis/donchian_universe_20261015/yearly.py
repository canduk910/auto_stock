import os, pickle, sys, json
from collections import defaultdict
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,"/Users/koscom/Projects/auto_stock/tools")
from replay.strategies import donchian_kk as DK, donchian_kk_audit as DA, donchian_y30 as Y
st,M,info=pickle.load(open(os.path.join(HERE,"store_full.pkl"),"rb")); cal=st.cal; bars=st.bars; Y._CAL["cal"]=cal
kk=Y.kk_of(Y.EXIT0); era=Y.Costs(cal)
feats={}
for t,b in bars.items():
    bb=dict(b); bb["mem"]=b["common"]; feats[t]=Y.features_y30(bb,tv_mode="pct")
fv={}
for t,f in feats.items():
    g=dict(f); g["cond"]=f["cond"]&bars[t]["common"]; fv[t]=g
sg=DK.build_signals(bars,fv,M["kospi"])
for s in sg:
    if bars[s.ticker]["kq"][s.ti-1]:
        v=M["kosdaq"][s.gd]; s.m=1.0 if not np.isfinite(v) else float(v)
    s.mem=bool(bars[s.ticker]["mem"][s.ti-1])
sg=[s for s in sg if not DA.r_half_blocked(s.E,s.N,kk)]
g0=int(cal.searchsorted(pd.Timestamp("1997-01-02"))); g1=len(cal)-1
pop=Y.population(sg,bars,feats,g0,g1,kk=kk)
by=defaultdict(lambda:{True:[],False:[]})
for p in pop:
    cr=era.rt(p.s.gd,p.exit_gd if p.exit_gd is not None else g1)+(0 if p.s.mem else 0.005)
    by[cal[p.s.gd].year][p.s.mem].append(p.exit_px/p.E-1-cr)
res={y:{"idx":[len(v[True]),float(np.mean(v[True])) if v[True] else None],"add":[len(v[False]),float(np.mean(v[False])) if v[False] else None]} for y,v in sorted(by.items())}
pos=sum(1 for y,v in res.items() if v["add"][1] is not None and v["add"][1]>0)
better=sum(1 for y,v in res.items() if v["add"][1] is not None and v["idx"][1] is not None and v["add"][1]>v["idx"][1])
print("added>0 years",pos,"/",len(res),"added>index years",better)
for y,v in res.items(): print(y, v["idx"][0], None if v["idx"][1] is None else round(v["idx"][1]*100,2), v["add"][0], None if v["add"][1] is None else round(v["add"][1]*100,2))
json.dump(res,open(os.path.join(HERE,"yearly.json"),"w"))
