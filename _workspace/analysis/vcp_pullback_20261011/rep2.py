import json, collections
S = json.load(open('sim.json')); F = json.load(open('funnel.json')); names = F['names']
buys = {(t['ticker'], t['timestamp'][:10]) for t in F['trades'] if t['trade_type']=='BUY'}
print('buys', buys)
def band(lo, hi, rng):
    rows = []
    for D, v in S.items():
        if not rng(D): continue
        for t, x in v['res'].items():
            if x.get('fin0.15') and not x.get(f'fin{lo}'):
                rows.append((D, t, names.get(t, '?'), x['lp'], x['cnt'], x['bh'], x['pc'], x.get('brk'), x.get('d_high'), x.get('c5'), x.get('lock')))
    return rows
for lo in (0.12, 0.1):
  for lab, rng in (('POST', lambda D: '2026-09-21' <= D <= '2026-10-08'), ('ALL40', lambda D: D <= '2026-10-08'), ('1012', lambda D: D=='2026-10-12')):
    rows = band(lo, None, rng)
    u = collections.Counter(r[1] for r in rows)
    print(f'== drop at {lo} {lab}: rows {len(rows)} uniq {len(u)}')
    if lab != 'ALL40':
        for r in rows:
            D,t,n,lp,cnt,bh,pc,brk,dh,c5,lock = r
            dist = (bh/pc-1)*100
            ret5 = ((c5/bh-1)*100 if (brk and c5) else None)
            print(f'  {D} {t} {n} lp={lp*100:.1f}% cnt={cnt} 돌파선={bh} 전일종가={pc} 거리={dist:.1f}% 당일돌파={brk} D+5종가/돌파선={ret5 if ret5 is None else round(ret5,1)} lock={lock} bought={(t,D) in buys}')
    else:
        print('  uniq', [(t, names.get(t), c) for t, c in u.most_common()])
# whole-candidate breakout stats by band (post + all)
def stats(rng, pred):
    n=b=0; rets=[]
    for D, v in S.items():
        if not rng(D): continue
        for t, x in v['res'].items():
            if x.get('fin0.15') and pred(x['lp']):
                n+=1
                if x.get('brk'):
                    b+=1
                    if x.get('c5'): rets.append(x['c5']/x['bh']-1)
    import statistics
    return n, b, len(rets), (round(statistics.mean(rets)*100,2) if rets else None), (round(statistics.median(rets)*100,2) if rets else None)
for lab, rng in (('POST', lambda D: '2026-09-21' <= D <= '2026-10-08'), ('ALL40', lambda D: D <= '2026-10-08')):
    for bl, pred in (('<=0.10', lambda l: l<=0.10), ('0.10-0.12', lambda l: 0.10<l<=0.12), ('0.12-0.15', lambda l: 0.12<l<=0.15)):
        print(lab, bl, 'rows,breakouts,with_d5,mean_ret5,med_ret5 =', stats(rng, pred))
# bought tickers band check
for (t, d) in buys:
    for D, v in S.items():
        x = v['res'].get(t)
        if x and x.get('fin0.15') and D <= d:
            print('bought', t, names.get(t), 'buy', d, 'cand', D, 'lp', round(x['lp']*100,1), 'fin12', x['fin0.12'], 'fin10', x['fin0.1'])
