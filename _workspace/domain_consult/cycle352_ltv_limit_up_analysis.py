"""cycle352 — LTV 상한가 모드 당일 청산 대안 비교 (로컬 분석, 운영 쓰기 0).

입력 (C352_DATA 디렉터리, 기본 = 현재 디렉터리):
  p2.json         cycle352_ltv_probe2.py 출력 (LTV 체결 전수 + 해당 종목 일봉 + 로그)
  smd.csv.gz      cycle352_ltv_probe3.py 출력 (stock_master_daily 전수)
  minute.json / minute_d1.json   네이버 1분봉 캐시 (없으면 --fetch 로 받는다; 약 6영업일만 제공)

세 갈래:
  [1] 실체결 — LTV 79왕복 중 상한가(+29%) 터치·밤 보유 분해
  [2] 모집단(일봉) — LTV 진입 조건을 일봉으로 흉내 낸 날 중 +29% 터치 사건, 대안별 기대값
  [3] 분봉 경로(최근 6영업일) — 상한가 터치 종목의 장중 흔들림 깊이 + 대안 정확 시뮬

운영 DB 값 (2026-09-25 SELECT): overnight_stop_loss -3.5 · gap_up_threshold 7 · trailing_stop_rate -2 ·
limit_up_threshold 29 · min_prdy_rate 5 · tradable_boards ["main"].
"""
from __future__ import annotations

import bisect
import collections
import csv
import gzip
import json
import os
import statistics as st
import sys
import time
import urllib.request

DATA = os.environ.get("C352_DATA", ".")
STOP = -3.5       # overnight_stop_loss (운영 DB)
GAP = 7.0         # gap_up_threshold (운영 DB)
TRAIL = 2.0       # |trailing_stop_rate| (운영 DB)
LIMIT_UP_THR = 29.0
MIN_PRDY = 5.0


def p(name):
    return os.path.join(DATA, name)


def q(xs, ps=(10, 25, 50, 75, 90)):
    xs = sorted(xs)
    if not xs:
        return {}
    return {k: round(xs[min(len(xs) - 1, int(k / 100 * len(xs)))], 2) for k in ps}


def tick(price):
    for bound, t in ((2000, 1), (5000, 5), (20000, 10), (50000, 50), (200000, 100), (500000, 500)):
        if price < bound:
            return t
    return 1000


def limit_up(pc):
    raw = pc * 1.3
    t = tick(raw)
    return int(raw // t * t)


# ───────────────────────── [1] 실체결 ─────────────────────────
def part1():
    d = json.load(open(p("p2.json")))
    bars = collections.defaultdict(list)
    for b in d["bars"]:
        bars[b["ticker"]].append(b)
    for t in bars:
        bars[t].sort(key=lambda x: x["d"])
    q_open = collections.defaultdict(list)
    pairs = []
    for r in d["trades"]:
        if r["trade_type"] == "BUY":
            q_open[r["ticker"]].append(r)
        elif q_open[r["ticker"]]:
            pairs.append((q_open[r["ticker"]].pop(0), r))
    rows = []
    for b, s in pairs:
        t = b["ticker"]
        ds = [x["d"] for x in bars[t]]
        i = bisect.bisect_left(ds, b["ts_kst"][:10])
        rec = dict(t=t, bts=b["ts_kst"], sts=s["ts_kst"], bp=b["price"], sp=s["price"], q=b["quantity"],
                   pl=s["pl"], hold=b["ts_kst"][:10] != s["ts_kst"][:10])
        if i < len(ds) and ds[i] == b["ts_kst"][:10] and i > 0:
            pc = bars[t][i - 1]["close_price"]
            rec["buy_prdy"] = (b["price"] / pc - 1) * 100
            rec["Dh_prdy"] = (bars[t][i]["high_price"] / pc - 1) * 100
        rows.append(rec)
    same = [r for r in rows if not r["hold"]]
    over = [r for r in rows if r["hold"]]
    print(f"[1] 왕복 {len(rows)} | 당일 {len(same)} 합 {sum(r['pl'] for r in same):+,.0f}원 | "
          f"밤 보유 {len(over)} 합 {sum(r['pl'] for r in over):+,.0f}원")
    print("    일봉 고가 +29% 터치:", [(r["t"], r["bts"][:10], r["hold"], r["pl"]) for r in rows if r.get("Dh_prdy", 0) >= 29])
    print("    밤 보유인데 터치 없음:", [(r["t"], r["bts"][:10], round(r.get("Dh_prdy", 0), 1), r["pl"]) for r in over if r.get("Dh_prdy", 0) < 29])
    bp = sorted(r["buy_prdy"] for r in rows if "buy_prdy" in r)
    print(f"    매수 시점 전일대비 중앙 {st.median(bp):+.1f}% · 90분위 {bp[int(len(bp) * .9)]:+.1f}% · "
          f"랏 중앙 {st.median(r['bp'] * r['q'] for r in rows):,.0f}원")


# ───────────────────────── [2] 모집단(일봉) ─────────────────────────
def load_events():
    rows = collections.defaultdict(list)
    mcap = {}
    with gzip.open(p("smd.csv.gz"), "rt") as f:
        for x in csv.DictReader(f):
            rows[x["ticker"]].append((x["d"], int(x["o"]), int(x["h"]), int(x["l"]), int(x["c"]), int(x["v"]), int(x["tv"] or 0)))
            mcap[x["ticker"]] = float(x["mcap_eok_now"]) if x["mcap_eok_now"] else None
    events, n_entry = [], 0
    for t, bs in rows.items():
        bs.sort()
        if not t.isdigit() or (mcap[t] is not None and mcap[t] < 500):   # min_market_cap 500억(현재값 근사)
            continue
        for i in range(23, len(bs)):
            d, o, h, l, c, _, _ = bs[i]
            _, _, ph, pl_, pcl, _, ptv = bs[i - 1]
            if o <= 0 or pcl <= 0 or ptv < 2e10:                           # min_trade_amount 200억(전일)
                continue
            c2, c3 = bs[i - 2][4], bs[i - 3][4]
            if c2 > 0 and c3 > 0 and pcl / c2 - 1 >= .25 and c2 / c3 - 1 >= .25:   # 연속 상한가 2일 제외
                continue
            rng = ph - pl_
            if rng <= 0:
                continue
            noise = [1 - abs(bs[j][4] - bs[j][1]) / (bs[j][2] - bs[j][3]) for j in range(i - 22, i - 1) if bs[j][2] > bs[j][3]]
            if not noise:
                continue
            target = o + int(rng * sum(noise) / len(noise))
            # 돌파 판정의 prev 는 등락률 필터(>=5%) 통과 틱에서만 갱신된다 → target 이 +5% 미만이면 진입 불가
            if target < pcl * (1 + MIN_PRDY / 100) or h < target:
                continue
            n_entry += 1
            if h < pcl * (1 + LIMIT_UP_THR / 100):
                continue
            nxt = bs[i + 1] if i + 1 < len(bs) else None
            if nxt is None or h > pcl * 1.305 or target / pcl - 1 >= .29 or nxt[1] > c * 1.305:  # 기준가 조정·데이터 이상 제외
                continue
            events.append(dict(t=t, d=d, pc=pcl, h=h, l=l, c=c, buy=target, locked=c >= limit_up(pcl),
                               c_prdy=(c / pcl - 1) * 100, buy_prdy=(target / pcl - 1) * 100, n=nxt))
    return events, n_entry


def a_overnight(e, pos):
    """익일 규칙. pos = 갭업 트레일링 청산가를 [시가×0.98, 고가×0.98] 구간 어디로 볼지 (0=하단)."""
    _, no, nh, _, _, _, _ = e["n"]
    buy = e["buy"]
    if no <= buy * (1 + STOP / 100) or (no / buy - 1) * 100 < GAP:
        return no
    lo, hi = no * (1 - TRAIL / 100), max(no, nh) * (1 - TRAIL / 100)
    return lo + pos * (hi - lo)


def a_exit(e, pos):
    stop = e["buy"] * (1 + STOP / 100)
    return stop if e["c"] <= stop else a_overnight(e, pos)


def b_exit(e, pos, thr=LIMIT_UP_THR):
    stop = e["buy"] * (1 + STOP / 100)
    if e["c"] <= stop:
        return stop
    return a_overnight(e, pos) if e["c_prdy"] >= thr else e["c"]


def part2(pos_real):
    ev, n_entry = load_events()
    lk = [e for e in ev if e["locked"]]
    fd = [e for e in ev if not e["locked"]]
    print(f"\n[2] 모집단 진입 {n_entry} · +29% 터치 {len(ev)} (잠김 마감 {len(lk)} / 풀림 마감 {len(fd)})")
    print("    풀림 마감 종가 전일대비", q([e["c_prdy"] for e in fd]))
    print("    익일 시가 vs 당일 종가 — 풀림", q([(e["n"][1] / e["c"] - 1) * 100 for e in fd]),
          "/ 잠김", q([(e["n"][1] / e["c"] - 1) * 100 for e in lk]))
    gb = [(1 - a_exit(e, 0) / e["h"]) * 100 for e in ev]
    print("    현행 고점 대비 청산가 반납", q(gb, (50, 75, 90, 95, 99)), f"max {max(gb):.1f} · 15%↑ {sum(g >= 15 for g in gb) / len(gb) * 100:.1f}%")
    ra = [(a_exit(e, 0) / e["buy"] - 1) * 100 for e in ev]
    print(f"    현행 손실 비율 {sum(r < 0 for r in ra) / len(ra) * 100:.1f}% · -5% 이하 {sum(r <= -5 for r in ra)}건 · 최악 {min(ra):+.1f}%")
    # 분봉 표본에서 잰 보정치: 잠김 마감 종목이 X% 흔들린 비율 / 일봉상 모호한 풀림 종목의 실제 발동 비율
    pshake = {7: 7 / 25, 10: 3 / 25, 12: 2 / 25, 15: 1 / 25}
    pamb = {7: 3 / 7, 10: 3 / 11, 12: 6 / 15, 15: 2 / 16}
    for pos in (0.0, pos_real, 0.5):
        tag = {0.0: "하단", 0.5: "중간"}.get(pos, f"실측 {pos:.2f}")
        d_b = [(b_exit(e, pos) - a_exit(e, pos)) / e["buy"] * 100 for e in ev]
        rb = [(b_exit(e, pos) / e["buy"] - 1) * 100 for e in ev]
        line = f"    익일트레일={tag}: B-A {st.mean(d_b):+.2f}%p (B -5%↓ {sum(r <= -5 for r in rb)}건)"
        for x in (7, 10, 12, 15):
            dd = []
            for e in ev:
                a = a_exit(e, pos)
                fl = max(e["h"] * (1 - x / 100), e["buy"] * (1 + STOP / 100))
                if e["locked"]:
                    dd.append(pshake[x] * (fl - a) / e["buy"] * 100)
                elif e["c"] <= fl:
                    dd.append((fl - a) / e["buy"] * 100)
                elif e["l"] <= fl:
                    dd.append(pamb[x] * (fl - a) / e["buy"] * 100)
                else:
                    dd.append(0.0)
            line += f" | C{x} {st.mean(dd):+.2f}"
        print(line)
    for thr in (20, 25, 27, 29):
        d_b = [(b_exit(e, pos_real, thr) - a_exit(e, pos_real)) / e["buy"] * 100 for e in ev]
        print(f"    B 보유 임계 {thr}%: B-A {st.mean(d_b):+.2f}%p")


# ───────────────────────── [3] 분봉 경로 ─────────────────────────
def fetch_minutes():
    ev = json.load(open(p("recent_events.json")))
    days = ["2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-28"]

    def get(t, d):
        url = (f"https://api.stock.naver.com/chart/domestic/item/{t}/minute?"
               f"startDateTime={d.replace('-', '')}0800&endDateTime={d.replace('-', '')}2000")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
            return json.load(r)
    m0, m1 = {}, {}
    for e in ev:
        k = f"{e['t']}_{e['d']}"
        m0[k] = get(e["t"], e["d"])
        nd = days[days.index(e["d"]) + 1]
        if nd != "2026-09-28":
            m1[k] = dict(nd=nd, bars=get(e["t"], nd))
        time.sleep(0.3)
    json.dump(m0, open(p("minute.json"), "w"))
    json.dump(m1, open(p("minute_d1.json"), "w"))


def hm(b):
    return b["localDateTime"][8:12]


def d1_exit(bars, buy):
    main = [b for b in bars if "0900" <= hm(b) < "1520"]
    if not main:
        return None, "nodata"
    o = main[0]["openPrice"]
    if o <= buy * (1 + STOP / 100):
        return o, "stop_open"
    if (o / buy - 1) * 100 < GAP:
        return o, "open_sell"
    rh = o
    for b in main:
        if b["lowPrice"] <= buy * (1 + STOP / 100):
            return buy * (1 + STOP / 100), "stop"
        if b["lowPrice"] <= rh * (1 - TRAIL / 100):
            return rh * (1 - TRAIL / 100), "trail"
        rh = max(rh, b["highPrice"])
        if b["lowPrice"] <= rh * (1 - TRAIL / 100):
            return rh * (1 - TRAIL / 100), "trail"
    return main[-1]["currentPrice"], "carry"


def part3():
    ev = json.load(open(p("recent_events.json")))
    m0 = json.load(open(p("minute.json")))
    m1 = json.load(open(p("minute_d1.json")))
    # (a) 흔들림 깊이
    locked_dd, faded, pos_real = [], [], []
    for e in ev:
        bars = m0.get(f"{e['t']}_{e['d']}") or []
        main = [b for b in bars if "0900" <= hm(b) < "1520"]
        ft = next((k for k, b in enumerate(main) if b["highPrice"] >= e["pc"] * 1.29), None)
        if ft is None:
            continue
        rh, dd, trig = 0, 0.0, {}
        for b in main[ft:]:
            rh = max(rh, b["highPrice"])
            dd = max(dd, (1 - b["lowPrice"] / rh) * 100)
            for x in (3, 5, 7, 10, 12, 15):
                if x not in trig and b["lowPrice"] <= rh * (1 - x / 100):
                    trig[x] = True
        (locked_dd if e["c"] >= limit_up(e["pc"]) else faded).append((dd, trig))
    print(f"\n[3] 분봉 표본 {len(locked_dd) + len(faded)} (잠김 마감 {len(locked_dd)} / 풀림 {len(faded)})")
    print("    잠김 마감 종목의 첫 터치 뒤 최대 되밀림", q([x[0] for x in locked_dd]))
    for x in (3, 5, 7, 10, 12, 15):
        print(f"    폭 {x:2}%: 잠김 종목을 털어냄 {sum(x in t for _, t in locked_dd)}/{len(locked_dd)} · "
              f"풀림 종목을 잡음 {sum(x in t for _, t in faded)}/{len(faded)}")
    # (b) 익일 트레일링 실제 청산 위치 (일봉 가정 보정용)
    for e in ev:
        k = f"{e['t']}_{e['d']}"
        if k not in m1:
            continue
        main = [b for b in m1[k]["bars"] if "0900" <= hm(b) < "1520"]
        if not main:
            continue
        x, tag = d1_exit(m1[k]["bars"], e["pc"] * 1.08)
        if tag != "trail":
            continue
        o, h = main[0]["openPrice"], max(b["highPrice"] for b in main)
        lo, hi = o * .98, max(o, h) * .98
        pos_real.append((x - lo) / (hi - lo) if hi > lo else 0.0)
    pr = st.mean(pos_real)
    print(f"    익일 갭업 트레일링 실제 청산 위치 N={len(pos_real)} 평균 {pr:.2f} (0=시가×0.98, 1=고가×0.98) · 하단 비율 "
          f"{sum(v < .05 for v in pos_real) / len(pos_real):.0%}")
    # (c) 경로 정확 시뮬
    for bp in (8, 14, 20):
        out = collections.defaultdict(list)
        for e in ev:
            k = f"{e['t']}_{e['d']}"
            if k not in m1:
                continue
            bars = m0[k]
            pc, thr, buy = e["pc"], e["pc"] * 1.29, e["pc"] * (1 + bp / 100)
            stop = buy * (1 + STOP / 100)
            main = [b for b in bars if "0900" <= hm(b) < "1520"]
            ft = next((i for i, b in enumerate(main) if b["highPrice"] >= thr), None)
            if ft is None:
                continue
            post = [b for b in bars if hm(b) >= hm(main[ft])]
            a = stop if any(b["lowPrice"] <= stop for b in post) else d1_exit(m1[k]["bars"], buy)[0]
            if any(b["lowPrice"] <= stop for b in main[ft:]):
                b_ = stop
            elif main[-1]["currentPrice"] < thr:
                b_ = e["c"]
            else:
                b_ = a
            res = {"A": a, "B": b_}
            for x in (7, 10, 12, 15):
                rh, hit = 0, None
                for b in main[ft:]:
                    rh = max(rh, b["highPrice"])
                    fl = rh * (1 - x / 100)
                    if b["lowPrice"] <= stop and stop >= fl:
                        hit = stop
                        break
                    if b["lowPrice"] <= fl:
                        hit = fl
                        break
                res[f"C{x}"] = hit if hit else a
                res[f"C{x}+B"] = hit if hit else b_
            for kk, v in res.items():
                out[kk].append(((v / buy - 1) * 100, (v - a) / buy * 100))
        line = f"    매수가 전일+{bp}% N={len(out['A'])}:"
        for kk in ("A", "B", "C7", "C10", "C12", "C15", "C15+B"):
            rets = [r for r, _ in out[kk]]
            line += f" {kk} {st.mean(rets):+.2f}(최악 {min(rets):+.1f})"
        print(line)
    return pr


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch_minutes()
    part1()
    pos = part3()
    part2(pos)
