"""cycle367 — 청산 규약 자문(P2 = D9) 재현 스크립트 (읽기 전용).

두 단계로 쓴다.

1) 운영 DB 덤프 (EC2 backend 컨테이너 안에서, SELECT 만 — 세션을 read-only 로 연다)
     ssh ubuntu@3.38.228.74 'docker exec -i auto_stock-backend-1 python - dump' \
         < cycle367_exit_rules_probe.py > dump.json
   ⚠️ 20:00~21:35 KST 에는 돌리지 않는다(자문·정산 창).

2) 로컬 분석 (dump.json 이 있는 디렉터리에서)
     python cycle367_exit_rules_probe.py bfb      # BFB 진입 ATR·터틀 랏·손절선 (§1)
     python cycle367_exit_rules_probe.py bfbrisk  # BFB risk_pct × 비중별 랏·1회 손실 (§1)
     python cycle367_exit_rules_probe.py mfe      # BFB 왕복별 보유일·매수일 종가·MFE (§5)
     python cycle367_exit_rules_probe.py time     # BFB 시간 청산 달력일 vs 영업일 (§3)
     python cycle367_exit_rules_probe.py donchian # donchian 트레일링 ATR 반사실 (§2)

ATR 정의는 `StrategyBase._atr` 와 같다 — 기준일 **이전**(엄격) 봉 최신순 14개 True Range 단순평균.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import statistics as st
import sys
from collections import defaultdict

# ─────────────────────────────── 1) 덤프 (컨테이너 안) ───────────────────────────────
DUMP_SQL_TRADES = """SELECT timestamp, ticker, ticker_name, trade_type, price, quantity, profit_loss,
                            status, strategy, order_no
                     FROM trade_history
                     WHERE strategy IN ('bull_flag_breakout','donchian_swing','kojiro','vcp_breakout')
                     ORDER BY timestamp"""
DUMP_SQL_BARS = """SELECT ticker, bas_dd, open_price, high_price, low_price, close_price, volume
                   FROM stock_master_daily
                   WHERE ticker = ANY($1::text[]) AND bas_dd >= '2026-01-01'
                   ORDER BY ticker, bas_dd"""


def _dump() -> None:
    import asyncio
    import decimal
    import os

    import asyncpg

    def conv(o):
        if isinstance(o, (dt.date, dt.datetime)):
            return o.isoformat()
        if isinstance(o, decimal.Decimal):
            return float(o)
        return str(o)

    async def main():
        c = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql"))
        await c.execute("SET default_transaction_read_only = on")
        th = await c.fetch(DUMP_SQL_TRADES)
        tickers = sorted({r["ticker"] for r in th} | {"003160", "052710", "295310", "030530", "067310", "095340"})
        bars = await c.fetch(DUMP_SQL_BARS, tickers)
        print(json.dumps({"trades": [dict(r) for r in th], "bars": [dict(r) for r in bars]},
                         default=conv, ensure_ascii=False))
        await c.close()

    asyncio.run(main())


# ─────────────────────────────── 공통 ───────────────────────────────
KST = dt.timezone(dt.timedelta(hours=9))


def _load():
    d = json.load(open("dump.json"))
    bars = defaultdict(list)
    for b in d["bars"]:
        bars[b["ticker"]].append(dict(d=dt.date.fromisoformat(b["bas_dd"]), o=b["open_price"],
                                      h=b["high_price"], l=b["low_price"], c=b["close_price"]))
    for t in bars:
        bars[t].sort(key=lambda x: x["d"])
    return d, bars


D, BARS = (None, None)
ALLDAYS: list[dt.date] = []


def _init():
    global D, BARS, ALLDAYS
    D, BARS = _load()
    ALLDAYS = sorted({b["d"] for bs in BARS.values() for b in bs})


def kst(ts: str) -> dt.datetime:
    x = dt.datetime.fromisoformat(ts)
    if x.tzinfo is None:
        x = x.replace(tzinfo=dt.timezone.utc)
    return x.astimezone(KST)  # asyncpg 는 UTC 로 돌려준다 — 날짜는 반드시 KST 로 바꿔서 쓴다


def atr14_before(t: str, d: dt.date, period: int = 14) -> float:
    bs = [b for b in BARS[t] if b["d"] < d][::-1]
    if len(bs) <= period + 1:
        return 0.0
    trs = [max(bs[i]["h"] - bs[i]["l"], abs(bs[i]["h"] - bs[i + 1]["c"]), abs(bs[i]["l"] - bs[i + 1]["c"]))
           for i in range(period)]
    return sum(trs) / period


def pairs(strategy: str):
    buys = defaultdict(list)
    out = []
    for t in D["trades"]:
        if t["strategy"] != strategy or t["status"] != "COMPLETED":
            continue
        k = kst(t["timestamp"])
        if t["trade_type"] == "BUY":
            buys[t["ticker"]].append(dict(ticker=t["ticker"], name=t["ticker_name"], bdt=k, bd=k.date(),
                                          bp=int(t["price"]), q=t["quantity"]))
        else:
            b = buys[t["ticker"]].pop(0)  # FIFO
            b.update(sdt=k, sd=k.date(), sp=int(t["price"]))
            out.append(b)
    return out, [b for v in buys.values() for b in v]


# 순자산 ≈ 4,981,060 = 09-23 `[risk_silent_skip] total=249,053`(비중 0.05 전략) ÷ 0.05. Σweight = 1.00.
NET_ASSET = 4_981_060


def turtle_lot(budget, risk, a, p, K=2.0, PR=0.25):
    """BFB calc_buy_quantity(turtle) + K축 캡 근사. (수량, 스탬프 여부)."""
    unit = math.floor(budget * risk / a) if a > 0 else 0
    if a / p < 0.01:
        unit = 0
    unit = min(unit, int(budget * PR) // p)
    kcap = math.floor(budget * risk * K / a) if a > 0 else 0
    if unit > 0:
        return min(unit, kcap), True
    base = int(budget * PR) // p or 1
    return min(base, kcap), False


# ─────────────────────────────── §1 BFB ───────────────────────────────
def cmd_bfb():
    B = int(NET_ASSET * 0.15)
    cl, op = pairs("bull_flag_breakout")
    print(f"BFB 예산 {B:,} (비중 0.15) · risk_pct 0.005 · K 2.0 · position_ratio 0.25")
    for r in sorted(cl + op, key=lambda x: x["bdt"]):
        a = atr14_before(r["ticker"], r["bd"])
        p = r["bp"]
        qty, stamped = turtle_lot(B, 0.005, a, p)
        eff = max(min(p - 2 * a, p * 0.96), p * 0.93)  # 스탬프 랏 = min(2ATR, −4%) 과 −7% 받침선 중 높은 선
        print(f"{r['ticker']} {r['name'][:6]:6} {r['bd']} {p:>7} 실제{r['q']:>3}주 | ATR {a:6.0f} ({a / p * 100:4.1f}%)"
              f" | 비중랏 {int(B * 0.25) // p:>3} 터틀랏 {qty:>3} {'스탬프' if stamped else '폴백/무매수'}"
              f" | 스탬프 손절선 {eff:8.0f} ({(eff / p - 1) * 100:5.1f}%)")


def cmd_bfbrisk():
    cl, op = pairs("bull_flag_breakout")
    rows = cl + op
    for w in (0.15, 0.10):
        B = int(NET_ASSET * w)
        q = [int(B * 0.25) // r["bp"] or 1 for r in rows]
        risk = [qq * r["bp"] * 0.05 / B * 100 for qq, r in zip(q, rows)]
        print(f"== 비중 {w} 예산 {B:,} | 현행 비중랏 주수 중앙 {st.median(q)} · 1회 손절손실/예산 중앙 {st.median(risk):.2f}%")
        for rp in (0.005, 0.0075, 0.01):
            res = [turtle_lot(B, rp, atr14_before(r["ticker"], r["bd"]), r["bp"]) for r in rows]
            qs = [x[0] for x in res]
            rk = [x[0] * r["bp"] * 0.07 / B * 100 for x, r in zip(res, rows)]
            print(f"   터틀 risk_pct {rp}: 주수 중앙 {st.median(qs)} {sorted(qs)} · 폴백 "
                  f"{sum(1 for x in res if not x[1] and x[0] > 0)} · 무매수 {sum(1 for x in qs if x == 0)}"
                  f" · 1회 손절손실/예산 중앙 {st.median(rk):.2f}%")


def cmd_mfe():
    cl, _ = pairs("bull_flag_breakout")
    for r in sorted(cl, key=lambda x: x["bdt"]):
        t, bp = r["ticker"], r["bp"]
        bs = [b for b in BARS[t] if r["bd"] < b["d"] <= r["sd"]]
        b0 = [b for b in BARS[t] if b["d"] == r["bd"]]
        a = atr14_before(t, r["bd"])
        mfe = max([b["h"] for b in bs], default=bp)
        print(f"{t} {r['bdt']:%m-%d %H:%M} -> {r['sdt']:%m-%d %H:%M} 보유{len(bs)}영업일 "
              f"수익 {(r['sp'] / bp - 1) * 100:6.2f}% 매수일종가 {((b0[0]['c'] / bp - 1) * 100 if b0 else 0):6.2f}% "
              f"MFE(익일~) {(mfe / bp - 1) * 100:6.2f}% = {((mfe - bp) / a if a else 0):4.2f}ATR")
    rets = [(r["sp"] / r["bp"] - 1) * 100 for r in cl]
    print(f"실현 평균 {sum(rets) / len(rets):.2f}%/왕복 (n={len(rets)})")


# ─────────────────────────────── §3 시간 청산 ───────────────────────────────
# 09-24·25 추석 휴장은 로그 실측(「오늘 휴장 — 다음 영업일 2026-09-28」). 10-05(개천절 대체공휴일)·
# 10-09(한글날)는 **예상** — KIS 휴장일 조회로 확인하지 않았다.
HOL_AFTER = {dt.date(2026, 9, 24), dt.date(2026, 9, 25), dt.date(2026, 10, 5), dt.date(2026, 10, 9)}


def _is_td(d):
    if d <= dt.date(2026, 9, 23):
        return d in set(ALLDAYS)
    return d.weekday() < 5 and d not in HOL_AFTER


def cmd_time():
    def cal_exit(bd, mh=5):  # 현행: (today − buy_date).days > max_hold + 2, 첫 영업일 평가
        d = bd
        while True:
            d += dt.timedelta(days=1)
            if (d - bd).days > mh + 2 and _is_td(d):
                return d

    def biz_exit(bd, mh=5):  # 제안: (buy_date, today] 영업일 수 > max_hold
        d, n = bd, 0
        while True:
            d += dt.timedelta(days=1)
            if _is_td(d):
                n += 1
                if n > mh:
                    return d

    def biz_between(bd, d):
        return sum(1 for i in range(1, (d - bd).days + 1) if _is_td(bd + dt.timedelta(days=i)))

    cl, op = pairs("bull_flag_breakout")
    for r in sorted(cl + op, key=lambda x: x["bdt"]):
        c, b = cal_exit(r["bd"]), biz_exit(r["bd"])
        print(r["ticker"], r["bd"], "실제청산", r.get("sd", "보유중"), "| 달력 규칙", c, f"(영업일 {biz_between(r['bd'], c)})",
              "| 영업일 규칙", b, "| 같음" if c == b else "| 다름")


# ─────────────────────────────── §2 donchian ───────────────────────────────
K_TRAIL, N_DAYS, CH, STOP_ATR, BE, BACK = 1.8, 2, 10, 2.0, 1.5, -9.0  # 운영 DB 값(09-25 조회)


def dc_sim(r, variant):
    """일봉 근사 — 모든 청산선이 「가격 ≤ 선」 형태라 그날의 최고 선이 먼저 닿는다고 본다.
    시가가 선 아래면 시가 체결, 아니면 선 체결. 매수일은 평가하지 않는다. 한계는 메모 §2.4."""
    t, bp, bd = r["ticker"], r["bp"], r["bd"]
    ea = atr14_before(t, bd)
    prior = [b for b in BARS[t] if b["d"] < bd]
    bh = max(b["h"] for b in prior[-21:-1]) if len(prior) >= 21 else 0  # prepare prior_high = highs[1:21]
    hsb, held, floor = bp, 0, 0.0
    for b in [b for b in BARS[t] if b["d"] > bd]:
        held += 1
        ta = atr14_before(t, b["d"])
        chand = hsb - K_TRAIL * (ea if variant == "entry" else ta)
        if variant == "today_ratchet":
            chand = max(chand, floor)
            floor = chand
        base = bp - STOP_ATR * ea
        if hsb >= bp + BE * ea:
            base = max(base, bp)
        prev = [x for x in BARS[t] if x["d"] < b["d"]]
        lines = {"hard": base, "backstop": bp * (1 + BACK / 100), "trail": chand,
                 "channel": min(x["l"] for x in prev[-CH:]) if len(prev) >= CH else 0}
        if held >= N_DAYS and bh > 0:
            lines["time"] = bh
        name, line = max(lines.items(), key=lambda kv: kv[1])
        if b["o"] <= line:
            return b["d"], b["o"], name
        if b["l"] <= line:
            return b["d"], line, name
        hsb = max(hsb, b["h"])
    return None, None, "open"


def cmd_donchian():
    cl, op = pairs("donchian_swing")
    ratios, gaps = [], []
    for r in cl + op:
        ea = atr14_before(r["ticker"], r["bd"])
        for b in BARS[r["ticker"]]:
            if r["bd"] < b["d"] <= r.get("sd", dt.date(2026, 9, 28)):
                ta = atr14_before(r["ticker"], b["d"])
                if ea > 0 and ta > 0:
                    ratios.append(ta / ea)
                    gaps.append(K_TRAIL * (ta - ea) / b["o"] * 100)
    print(f"보유일 {len(ratios)}: 오늘ATR/매수ATR 중앙 {st.median(ratios):.2f} p10 {st.quantiles(ratios, n=10)[0]:.2f}"
          f" p90 {st.quantiles(ratios, n=10)[-1]:.2f} (>1 비율 {sum(x > 1 for x in ratios) / len(ratios) * 100:.0f}%)")
    print(f"샹들리에 선 차이(오늘−매수) 중앙 {st.median(gaps):.2f}%p p10 {st.quantiles(gaps, n=10)[0]:.2f}"
          f" p90 {st.quantiles(gaps, n=10)[-1]:.2f}")
    match, n, se, stt, better, worse = 0, 0, 0.0, 0.0, 0, 0
    for r in sorted(cl, key=lambda x: x["bdt"]):
        e, td = dc_sim(r, "entry"), dc_sim(r, "today")
        match += e[0] == r["sd"]
        if r["ticker"] == "036540":
            print("036540 (별도): 매수ATR 시뮬", e, "/ 오늘ATR 시뮬", td, "/ 실제", r["sd"], r["sp"])
            continue
        re_ = ((e[1] or r["sp"]) / r["bp"] - 1) * 100
        rt = ((td[1] or r["sp"]) / r["bp"] - 1) * 100
        se, stt, n = se + re_, stt + rt, n + 1
        if abs(re_ - rt) > 0.01:
            better += rt > re_
            worse += rt < re_
            print(f"  {r['ticker']} {r['bd']} 매수ATR {re_:6.2f}% ({e[0]},{e[2]}) → 오늘ATR {rt:6.2f}% ({td[0]},{td[2]})")
    print(f"시뮬(매수ATR) 청산일 = 실제 청산일 {match}/{len(cl)} · 036540 제외 n={n}: 매수ATR 평균 {se / n:.3f}%"
          f" 오늘ATR 평균 {stt / n:.3f}% · 오늘ATR 이 나은 건 {better} / 나쁜 건 {worse}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dump"
    if cmd == "dump":
        _dump()
    else:
        _init()
        {"bfb": cmd_bfb, "bfbrisk": cmd_bfbrisk, "mfe": cmd_mfe, "time": cmd_time,
         "donchian": cmd_donchian}[cmd]()
