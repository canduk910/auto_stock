import json, sys, collections, statistics as st
sys.path.insert(0, '/Users/koscom/Projects/auto_stock')
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy as V
F = json.load(open('funnel.json')); B = json.load(open('bars.json'))
names = F['names']; etf = F['etf']
bars = collections.defaultdict(list)
for r in B:
    t,d,o,h,l,c,v,f,pr = r[:9]
    bars[t].append({'stck_bsop_date': d, 'stck_hgpr': str(h), 'stck_lwpr': str(l), 'stck_clpr': str(c), 'acml_vol': str(v)})
LIVE = dict(base_min_days=25, base_max_days=40, base_depth_pct=0.35, pullback_count_min=1, pullback_count_max=4,
            last_pullback_max=0.15, min_swing_atr_mult=1.0, volume_contraction_ratio=1.0)
class Cfg:
    def __init__(s, p): s.params = p
class Shim:
    def __init__(s, p): s.config = Cfg(p)
COMBOS = [(m, x) for m in (1, 2) for x in (0.15, 0.12, 0.10)]
sh = {k: Shim({**LIVE, 'pullback_count_min': k[0], 'last_pullback_max': k[1]}) for k in COMBOS}
tk = lambda x: x['ticker'] if isinstance(x, dict) else x
buys = {(t['ticker'], t['timestamp'][:10]) for t in F['trades'] if t['trade_type']=='BUY'}
res = {}  # D -> t -> info
for D in sorted(F['funnel']):
    if D == '2026-08-20': continue
    st5 = [tk(x) for x in F['funnel'][D]['5']['t']]; Dn = D.replace('-', '')
    res[D] = {}
    for t in st5:
        if etf.get(t): continue
        c = [b for b in bars.get(t, []) if b['stck_bsop_date'] < Dn]
        if not c: continue
        base = V._detect_base(sh[COMBOS[0]], c)
        if not base: continue
        info = {'bh': base['high'], 'pc': int(c[0]['stck_clpr'])}
        for k in COMBOS:
            b2 = dict(base)
            ok = V._check_pullback_sequence(sh[k], c, b2) and V._check_volume_contraction(sh[k], c, b2)
            info[k] = ok; info['lp'] = b2['last_pullback_pct']; info['cnt'] = b2['last_pullback_count']
        fwd = sorted([b for b in bars.get(t, []) if b['stck_bsop_date'] >= Dn], key=lambda b: b['stck_bsop_date'])
        info['brk0'] = (int(fwd[0]['stck_hgpr']) > base['high']) if fwd else None
        info['brk5'] = (any(int(b['stck_hgpr']) > base['high'] for b in fwd[:5])) if fwd else None
        info['nfwd'] = len(fwd[:5])
        if any(info[k] for k in COMBOS): res[D][t] = info
# validation: min1/0.15 vs live final
post = [D for D in res if '2026-09-21' <= D <= '2026-10-08']
allD = [D for D in res if D <= '2026-10-08']
val = []
for D in post + ['2026-10-12']:
    live = {tk(x) for x in F['funnel'][D]['9']['t']}
    sim = {t for t, i in res[D].items() if i[(1, 0.15)]}
    val.append((D, len(sim), len(live), len(sim ^ live)))
print('VALID', val)
print('| 조합 | 11일 평균(최소~최대) | 11일 합 | 고유 | 감소율(합) | 39일 평균 | 39일 감소율 |')
L0 = sum(sum(1 for i in res[D].values() if i[(1,0.15)]) for D in post); A0 = sum(sum(1 for i in res[D].values() if i[(1,0.15)]) for D in allD)
for k in COMBOS:
    c = [sum(1 for i in res[D].values() if i[k]) for D in post]; ca = [sum(1 for i in res[D].values() if i[k]) for D in allD]
    u = {t for D in post for t, i in res[D].items() if i[k]}
    print(f'| min{k[0]}·{k[1]:.2f} | {st.mean(c):.1f} ({min(c)}~{max(c)}) | {sum(c)} | {len(u)} | {(sum(c)/L0-1)*100:+.0f}% | {st.mean(ca):.1f} | {(sum(ca)/A0-1)*100:+.0f}% |')
# daily table post
print('DAILY')
for D in post + ['2026-10-12']:
    print(D, [sum(1 for i in res[D].values() if i[k]) for k in COMBOS])
# dropped by min2 (vs min1 same max=0.15) post
print('DROP min2@0.15 (post)')
dr = collections.defaultdict(list)
for D in post:
    for t, i in res[D].items():
        if i[(1,0.15)] and not i[(2,0.15)]:
            dr[t].append((D, i['cnt'], round(i['lp']*100,1), round((i['bh']/i['pc']-1)*100,1), i['brk0'], i['brk5'], i['nfwd'], (t, D) in buys))
for t, rows in sorted(dr.items(), key=lambda x: -len(x[1])):
    print(t, names.get(t), len(rows), rows)
n=sum(len(v) for v in dr.values()); b0=sum(r[4] is True for v in dr.values() for r in v); b5=sum(r[5] is True for v in dr.values() for r in v)
print('drop rows', n, 'uniq', len(dr), 'brk0', b0, 'brk5', b5)
# kept (min2) rows breakout stats for comparison
for k in [(1,0.15),(2,0.15),(2,0.12),(2,0.10)]:
    rows=[i for D in post for i in res[D].values() if i[k]]
    print('brk', k, len(rows), sum(i['brk0'] is True for i in rows), sum(i['brk5'] is True for i in rows))
print('cnt dist post live', collections.Counter(i['cnt'] for D in post for i in res[D].values() if i[(1,0.15)]))
# trades
for (t, d) in sorted(buys, key=lambda x: x[1]):
    D = d
    i = res.get(D, {}).get(t)
    print('BUY', t, names.get(t), d, None if not i else {f'min{k[0]}·{k[1]}': i[k] for k in COMBOS}, None if not i else (i['cnt'], round(i['lp']*100,1)))
# 09-10 claim recheck: min2, among pullback-pass with lp<=? , does 0.15 add over 0.12?
for lab, Ds in (('post', post), ('all39', allD), ('pre-G 08-10~09-18', [D for D in allD if D < '2026-09-21'])):
    a = sum(sum(1 for i in res[D].values() if i[(2,0.15)]) for D in Ds); b = sum(sum(1 for i in res[D].values() if i[(2,0.12)]) for D in Ds); c = sum(sum(1 for i in res[D].values() if i[(2,0.10)]) for D in Ds)
    print('min2 recheck', lab, '0.15', a, '0.12', b, '0.10', c)
json.dump({D: {t: {str(k): v for k, v in i.items()} for t, i in res[D].items()} for D in res}, open('sim2.json', 'w'), ensure_ascii=False)
