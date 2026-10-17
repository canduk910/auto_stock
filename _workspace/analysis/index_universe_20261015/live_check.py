"""운영 실측 — 퍼널 최종 후보·실체결의 지수 안/밖 비중. 입력 = EC2 SELECT 덤프(live2.txt·live3.txt) + 앞 자문 live_final.json."""
import json, sys, collections
S, OUT = sys.argv[1], sys.argv[2]
def sect(path, name):
    rows, on = [], False
    for ln in open(path, encoding="utf-8"):
        ln = ln.rstrip("\n")
        if ln.startswith("##"):
            on = (ln == "##" + name); continue
        if on and ln and "|" in ln: rows.append(ln.split("|"))
    return rows
mem = {r[0]: ("K200" if r[1] == "true" else "Q150") for r in sect(f"{S}/live2.txt", "MEM")}
fills = sect(f"{S}/live3.txt", "FILLS")
fun = sect(f"{S}/live3.txt", "FUN")
lf = json.load(open("/Users/koscom/Projects/auto_stock/_workspace/analysis/donchian_universe_20261015/live_final.json"))
R = {"n_members": len(mem), "members_by": dict(collections.Counter(mem.values()))}
TURTLE = ("donchian_swing", "bull_flag_breakout", "vcp_breakout", "kojiro")
fr = {}
for s in TURTLE:
    f = [r for r in fills if r[0] == s]
    ins = [r for r in f if r[1] in mem]
    fr[s] = {"n": len(f), "in_index": len(ins), "share_in": len(ins) / len(f) if f else None,
             "first": f[0][2] if f else None, "last": f[-1][2] if f else None,
             "out_list": sorted({(r[1], r[4]) for r in f if r[1] not in mem})}
allf = [r for r in fills if r[0] in TURTLE]
fr["turtle_all"] = {"n": len(allf), "in_index": sum(r[1] in mem for r in allf)}
R["fills"] = fr
fc = {}
for s in TURTLE:
    days = lf.get(s, {})
    tot = sum(len(v) for v in days.values()); ins = sum(sum(t in mem for t in v) for v in days.values())
    fc[s] = {"days": len(days), "cand_total": tot, "cand_in_index": ins, "share_in": ins / tot if tot else None,
             "per_day_mean": tot / len(days), "per_day_in_mean": ins / len(days)}
R["final_candidates_0916_1015"] = fc
st = collections.defaultdict(lambda: collections.defaultdict(list))
for d, s, k, n in fun:
    st[s][int(k)].append(int(n))
R["funnel_step_mean"] = {s: {k: sum(v) / len(v) for k, v in sorted(st[s].items())} for s in st}
R["funnel_days"] = sorted({r[0] for r in fun})
json.dump(R, open(f"{OUT}/live_check.json", "w"), ensure_ascii=False, indent=1)
for s in TURTLE: print(s, fr[s]["n"], fr[s]["in_index"], fc[s])
print(fr["turtle_all"]); print(json.dumps(R["funnel_step_mean"], ensure_ascii=False))
