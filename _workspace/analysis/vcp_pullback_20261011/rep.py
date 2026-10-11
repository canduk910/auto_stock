import json
S = json.load(open('sim.json')); F = json.load(open('funnel.json')); names = F['names']
print('date  live(5/6/7/9) | sim base | pb15 pb12 pb10 | fin15 fin12 fin10 | fidelity(post-G: base/pb/fin match)')
tot = {x: 0 for x in ('fin0.15', 'fin0.12', 'fin0.1', 'pb0.15', 'pb0.12', 'pb0.1')}
post = {x: 0 for x in tot}; npost = 0
fid = []
for D, v in S.items():
    r = v['res']
    base = {t for t, x in r.items() if x.get('base')}
    def S_(k): return {t for t, x in r.items() if x.get(k)}
    pb = {x: S_(f'pb{x}') for x in (0.15, 0.12, 0.1)}; fin = {x: S_(f'fin{x}') for x in (0.15, 0.12, 0.1)}
    ln = v['liven']
    line = f"{D} {ln['5']:>3}/{ln['6']:>2}/{ln['7']:>2}/{ln['9']:>2} | {len(base):>3} | {len(pb[0.15]):>2} {len(pb[0.12]):>2} {len(pb[0.1]):>2} | {len(fin[0.15]):>2} {len(fin[0.12]):>2} {len(fin[0.1]):>2}"
    for x in (0.15, 0.12, 0.1):
        tot[f'fin{x}'] += len(fin[x]); tot[f'pb{x}'] += len(pb[x])
    if D >= '2026-09-21':
        L6, L7, L9 = set(v['live']['6']), set(v['live']['7']), set(v['live']['9'])
        line += f" | base {len(base & L6)}/{len(L6)} sym{len(base ^ L6)} pb {len(pb[0.15] & L7)}/{len(L7)} sym{len(pb[0.15] ^ L7)} fin {len(fin[0.15] & L9)}/{len(L9)} sym{len(fin[0.15] ^ L9)}"
        fid.append((D, sorted(base ^ L6), sorted(pb[0.15] ^ L7), sorted(fin[0.15] ^ L9)))
        if D != '2026-10-12':
            npost += 1
            for x in (0.15, 0.12, 0.1):
                post[f'fin{x}'] += len(fin[x]); post[f'pb{x}'] += len(pb[x])
    print(line)
print('TOTAL', tot, 'days', len(S)); print('POST-G (09-21..10-08)', post, 'days', npost)
for D, a, b, c in fid:
    if a or b or c:
        print('MISMATCH', D, 'base', [(t, S[D]['res'].get(t, {}).get('lock'), t in S[D]['live']['6']) for t in a], 'pb', [(t, round(S[D]['res'].get(t, {}).get('lp', -1), 4), S[D]['res'].get(t, {}).get('lock'), t in S[D]['live']['7']) for t in b], 'fin', c)
