import json, statistics
from collections import defaultdict, deque
d=json.load(open('out3.json'))
C=defaultdict(list)
for c in d['candles']:
    C[c['ticker']].append((c['bas_dd'][:10],float(c['open_price']),float(c['high_price']),float(c['low_price']),float(c['close_price'])))
for t in C: C[t].sort()
def atr_at(t,date,per,wil):
    rr=[r for r in C[t] if r[0]<date]
    if len(rr)<per+1: return None
    trs=[max(rr[i][2]-rr[i][3],abs(rr[i][2]-rr[i-1][4]),abs(rr[i][3]-rr[i-1][4])) for i in range(1,len(rr))]
    if len(trs)<per: return None
    if not wil: return sum(trs[-per:])/per
    a=1/per; v=trs[0]
    for x in trs[1:]: v=v+a*(x-v)
    return v
trips=[]; ol=defaultdict(deque)
for t in d['trades']:
    k=(t['strategy'],t['ticker']); px=float(t['price']); q=int(t['quantity']); ts=t['timestamp'][:10]
    if t['trade_type']=='BUY': ol[k].append([ts,px,q])
    else:
        rem=q
        while rem>0 and ol[k]:
            lot=ol[k][0]; take=min(rem,lot[2]); rem-=take; lot[2]-=take
            trips.append(dict(strategy=t['strategy'],ticker=t['ticker'],bd=lot[0],bp=lot[1],sd=ts,sp=px))
            if lot[2]==0: ol[k].popleft()

def run(tr,N,step,maxu,trail=2.5,horizon=40):
    win=[r for r in C[tr['ticker']] if r[0]>=tr['bd']][:horizon]
    if len(win)<3: return None
    e=[tr['bp']]; stop=tr['bp']-2*N; nxt=tr['bp']+step*N; hi=tr['bp']
    for dt,o,h,l,c in win:
        if maxu>1:
            while len(e)<maxu and h>=nxt:
                e.append(nxt); stop=max(stop,nxt-2*N); nxt+=step*N
        hi=max(hi,h)
        eff=max(stop, hi-trail*N)
        if l<=eff: return sum(eff-x for x in e)/N, len(e)
    last=win[-1][4]
    return sum(last-x for x in e)/N, len(e)

for strat in ('donchian_swing','kojiro'):
    S=[t for t in trips if t['strategy']==strat]
    per,wil=(20,True) if strat=='kojiro' else (14,False)
    res=defaultdict(list)
    for tr in S:
        N=atr_at(tr['ticker'],tr['bd'],per,wil)
        if not N or N<=0: continue
        for lbl,(st,mx) in {'1유닛(피라미딩 없음)':(0.5,1),'1/2N 4유닛':(0.5,4),'1N 4유닛':(1.0,4),'1/2N 2유닛':(0.5,2)}.items():
            r=run(tr,N,st,mx)
            if r: res[lbl].append(r)
    print(f"===== {strat} — 이상적 청산 재시뮬(2N 손절 + 2.5N 샹들리에, 40영업일 지평) n={len(S)}")
    for lbl,v in res.items():
        pnl=[x[0] for x in v]; u=[x[1] for x in v]
        wins=sum(1 for p in pnl if p>0)
        print(f"  {lbl:22} Σ={sum(pnl):7.2f}N 평균={statistics.mean(pnl):6.2f}N 승률={wins/len(pnl)*100:4.0f}% 평균유닛={statistics.mean(u):4.2f} 유닛당={sum(pnl)/sum(u):6.2f}N")
    print()
