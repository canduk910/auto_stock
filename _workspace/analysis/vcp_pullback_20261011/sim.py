import json, sys, collections
sys.path.insert(0, '/Users/koscom/Projects/auto_stock')
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy as V
F = json.load(open('funnel.json')); B = json.load(open('bars.json'))
names = F['names']; etf = F['etf']
bars = collections.defaultdict(list)  # desc
for r in B:
    t,d,o,h,l,c,v,f,pr = r[:9]
    lock = (str(f).strip() not in ('', '00')) or abs(float(pr or 0)) > 1e-9
    bars[t].append({'stck_bsop_date': d, 'stck_oprc': str(o), 'stck_hgpr': str(h), 'stck_lwpr': str(l), 'stck_clpr': str(c), 'acml_vol': str(v), '_lock': lock})
LIVE = dict(base_min_days=25, base_max_days=40, base_depth_pct=0.35, pullback_count_min=1, pullback_count_max=4,
            last_pullback_max=0.15, min_swing_atr_mult=1.0, volume_contraction_ratio=1.0)
class Cfg:
    def __init__(s, p): s.params = p
class Shim:
    def __init__(s, p): s.config = Cfg(p)
XS = [0.15, 0.12, 0.10]
shims = {x: Shim({**LIVE, 'last_pullback_max': x}) for x in XS}
def tk(x): return x['ticker'] if isinstance(x, dict) else x
out = {}
for D in sorted(F['funnel']):
    if D == '2026-08-20': continue
    st = F['funnel'][D]; Dn = D.replace('-', '')
    s5 = [tk(x) for x in st['5']['t']]
    if len(s5) != st['5']['n']: print('WARN step5 truncated', D)
    res = {}
    for t in s5:
        if etf.get(t): continue
        c = [b for b in bars.get(t, []) if b['stck_bsop_date'] < Dn]
        if not c: res[t] = {'nobars': True}; continue
        lock = any(b['_lock'] for b in c[:250])
        base = V._detect_base(shims[0.15], c)
        if not base: res[t] = {'base': False, 'lock': lock}; continue
        row = {'base': True, 'lock': lock, 'bh': base['high'], 'len': base['length'], 'pc': int(c[0]['stck_clpr'])}
        for x in XS:
            b2 = dict(base)
            ok = V._check_pullback_sequence(shims[x], c, b2)
            row['lp'] = b2['last_pullback_pct']; row['cnt'] = b2['last_pullback_count']
            row[f'pb{x}'] = ok
            row[f'fin{x}'] = ok and V._check_volume_contraction(shims[x], c, b2)
        # forward: D bar and after
        fwd = sorted([b for b in bars.get(t, []) if b['stck_bsop_date'] >= Dn], key=lambda b: b['stck_bsop_date'])
        if fwd:
            row['d_high'] = int(fwd[0]['stck_hgpr']); row['d_date'] = fwd[0]['stck_bsop_date']
            row['brk'] = row['d_high'] > base['high']
            if len(fwd) > 5: row['c5'] = int(fwd[5]['stck_clpr'])
        res[t] = row
    out[D] = {'res': res, 'live': {k: [tk(x) for x in st[k]['t']] for k in ('6', '7', '8', '9')}, 'liven': {k: st[k]['n'] for k in ('5','6','7','8','9')}}
json.dump(out, open('sim.json', 'w'), ensure_ascii=False)
print('days', len(out))
