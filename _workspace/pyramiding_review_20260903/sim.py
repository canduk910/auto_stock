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
    trs=[]
    for i in range(1,len(rows)):
        h,l,pc=rows[i][2],rows[i][3],rows[i-1][4]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    if len(trs)<period: return None
    if not wilder: return sum(trs[-period:])/period
    a=1.0/period; v=trs[0]
    for x in trs[1:]: v = v + a*(x-v)
    return v

# FIFO 라운드트립
trips=[]
open_lots=defaultdict(deque)
for t in d['trades']:
    key=(t['strategy'], t['ticker'])
    px=float(t['price']); q=int(t['quantity']); ts=t['timestamp'][:10]
    if t['trade_type']=='BUY':
        open_lots[key].append([ts,px,q])
    else:
        rem=q
        while rem>0 and open_lots[key]:
            lot=open_lots[key][0]
            take=min(rem, lot[2]); rem-=take; lot[2]-=take
            trips.append(dict(strategy=t['strategy'], ticker=t['ticker'], name=t['ticker_name'],
                              bd=lot[0], bp=lot[1], sd=ts, sp=px, q=take))
            if lot[2]==0: open_lots[key].popleft()

print(f"라운드트립 {len(trips)}건 (donchian {sum(1 for x in trips if x['strategy']=='donchian_swing')}, kojiro {sum(1 for x in trips if x['strategy']=='kojiro')})")
print()
rows=[]
for tr in trips:
    wilder = tr['strategy']=='kojiro'
    per = 20 if wilder else 14
    N = atr_at(tr['ticker'], tr['bd'], per, wilder)
    if not N or N<=0: 
        rows.append({**tr,'N':None}); continue
    win=[r for r in C[tr['ticker']] if tr['bd'] <= r[0] <= tr['sd']]
    if not win: rows.append({**tr,'N':None}); continue
    mfe = max(r[2] for r in win) - tr['bp']
    mae = tr['bp'] - min(r[3] for r in win)
    rows.append({**tr,'N':N,'mfe_N':mfe/N,'mae_N':mae/N,'ret_N':(tr['sp']-tr['bp'])/N,
                 'ret_pct':(tr['sp']-tr['bp'])/tr['bp']*100,'days':len(win),'win':win})
ok=[r for r in rows if r.get('N')]
print(f"ATR 산출 가능 {len(ok)}/{len(rows)}")
print()
for strat in ('donchian_swing','kojiro'):
    s=[r for r in ok if r['strategy']==strat]
    if not s: continue
    mfes=sorted(r['mfe_N'] for r in s)
    print(f"== {strat}  n={len(s)}")
    print(f"   MFE(N배수) 중앙값={statistics.median(mfes):.2f}  평균={statistics.mean(mfes):.2f}  최대={max(mfes):.2f}")
    for thr in (0.5,1.0,1.5,2.0,3.0):
        c=sum(1 for m in mfes if m>=thr)
        print(f"   MFE >= {thr}N : {c}/{len(s)} = {c/len(s)*100:.0f}%")
    print(f"   실현 수익(N배수) 평균={statistics.mean([r['ret_N'] for r in s]):.2f}  중앙값={statistics.median([r['ret_N'] for r in s]):.2f}")
    print(f"   MAE(N배수) 중앙값={statistics.median([r['mae_N'] for r in s]):.2f}")
    print()
json.dump([{k:v for k,v in r.items() if k!='win'} for r in ok], open('trips.json','w'), default=str)
