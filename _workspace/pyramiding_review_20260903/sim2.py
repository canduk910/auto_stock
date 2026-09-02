import json, statistics
from collections import defaultdict, deque
d=json.load(open('out3.json'))
C=defaultdict(list)
for c in d['candles']:
    C[c['ticker']].append((c['bas_dd'][:10], float(c['open_price']), float(c['high_price']), float(c['low_price']), float(c['close_price'])))
for t in C: C[t].sort()
def atr_at(ticker, date, period, wilder):
    rows=[r for r in C[ticker] if r[0] < date]
    if len(rows) < period+1: return None
    trs=[max(rows[i][2]-rows[i][3], abs(rows[i][2]-rows[i-1][4]), abs(rows[i][3]-rows[i-1][4])) for i in range(1,len(rows))]
    if len(trs)<period: return None
    if not wilder: return sum(trs[-period:])/period
    a=1.0/period; v=trs[0]
    for x in trs[1:]: v=v+a*(x-v)
    return v
trips=[]; open_lots=defaultdict(deque)
for t in d['trades']:
    key=(t['strategy'],t['ticker']); px=float(t['price']); q=int(t['quantity']); ts=t['timestamp'][:10]
    if t['trade_type']=='BUY': open_lots[key].append([ts,px,q])
    else:
        rem=q
        while rem>0 and open_lots[key]:
            lot=open_lots[key][0]; take=min(rem,lot[2]); rem-=take; lot[2]-=take
            trips.append(dict(strategy=t['strategy'],ticker=t['ticker'],name=t['ticker_name'],bd=lot[0],bp=lot[1],sd=ts,sp=px,q=take))
            if lot[2]==0: open_lots[key].popleft()

def sim(tr, N, step, maxu, stop_mult=2.0, adds_first=True):
    """1유닛=1 리스크단위. 반환 = 총 손익(N배수, 유닛수 가중)"""
    win=[r for r in C[tr['ticker']] if tr['bd'] <= r[0] <= tr['sd']]
    if not win: return None
    entries=[tr['bp']]; stop = tr['bp'] - stop_mult*N
    next_add = tr['bp'] + step*N
    for i,(dt,o,h,l,c) in enumerate(win):
        if i==0:
            # 진입 당일: 진입 후 고가/저가 (근사 — 당일 전체 사용)
            pass
        if adds_first:
            while len(entries)<maxu and h>=next_add:
                entries.append(next_add); stop = next_add - stop_mult*N; next_add += step*N
            if l<=stop:
                return sum(stop-e for e in entries)/N, len(entries), 'stopped', dt
        else:
            if l<=stop:
                return sum(stop-e for e in entries)/N, len(entries), 'stopped', dt
            while len(entries)<maxu and h>=next_add:
                entries.append(next_add); stop = next_add - stop_mult*N; next_add += step*N
    return sum(tr['sp']-e for e in entries)/N, len(entries), 'exit', tr['sd']

results={}
for strat in ('donchian_swing','kojiro'):
    S=[t for t in trips if t['strategy']==strat]
    per,wil = (20,True) if strat=='kojiro' else (14,False)
    base=[]; rows=[]
    for tr in S:
        N=atr_at(tr['ticker'],tr['bd'],per,wil)
        if not N or N<=0: continue
        actual=(tr['sp']-tr['bp'])/N
        r={'tr':tr,'N':N,'actual':actual}
        for label,(step,mx) in {'half_4u':(0.5,4),'half_2u':(0.5,2),'half_3u':(0.5,3),'one_4u':(1.0,4),'one_2u':(1.0,2)}.items():
            for order in (True,False):
                out=sim(tr,N,step,mx,adds_first=order)
                r[f'{label}_{"AF" if order else "SF"}']=out
        # 1유닛 + 터틀 2N 스탑만 (피라미딩 없음)
        r['base_2Nstop']=sim(tr,N,0.5,1,adds_first=False)
        rows.append(r)
    results[strat]=rows
    print(f"===== {strat}  n={len(rows)}")
    print(f"  실측(1유닛, 시스템 청산)          Σ={sum(r['actual'] for r in rows):7.2f}N  평균={statistics.mean([r['actual'] for r in rows]):6.2f}N")
    b=[r['base_2Nstop'][0] for r in rows]
    print(f"  1유닛 + 2N 스탑만                Σ={sum(b):7.2f}N  평균={statistics.mean(b):6.2f}N")
    for label in ('half_2u','half_3u','half_4u','one_2u','one_4u'):
        for order,tag in ((True,'추가우선'),(False,'스탑우선')):
            k=f'{label}_{"AF" if order else "SF"}'
            v=[r[k][0] for r in rows]; u=[r[k][1] for r in rows]
            st=sum(1 for r in rows if r[k][2]=='stopped')
            print(f"  {label:8} {tag}  Σ={sum(v):7.2f}N 평균={statistics.mean(v):6.2f}N  평균유닛={statistics.mean(u):4.2f}  스탑청산={st}/{len(rows)}")
    print()
json.dump({k:[{'ticker':r['tr']['ticker'],'name':r['tr']['name'],'bd':r['tr']['bd'],'bp':r['tr']['bp'],'N':r['N'],'actual':r['actual'],
               'half4_AF':r['half_4u_AF'],'half4_SF':r['half_4u_SF'],'one4_AF':r['one_4u_AF']} for r in v] for k,v in results.items()},
          open('sim2.json','w'), default=str)
