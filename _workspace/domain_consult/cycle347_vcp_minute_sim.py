"""cycle347 — 분봉(네이버 공개 차트, KRX)으로 VCP 매수 관문을 재생한다. 로컬 실행, 읽기 전용.

입력 = probe2 가 재현한 (날짜, 종목, base_high, base_low, vol_thr) — 운영 파라미터
base_max_days(40, 09-19 이전 75)·base_depth_pct 0.35·breakout_volume_mult 1.2 기준.
판정 근사: 분봉 OHLC 로 틱을 대신한다. 09:05~14:30 창 안에서
  crossed  = 분봉 고가 >= base_high 인 첫 분
  vol_ok   = 그 분까지 누적거래량 >= vol_thr
  in_cap   = 그 분의 [저가, 고가] 가 [base_high, base_high*1.075] 와 겹친다
  → 세 조건이 같은 분에 처음 동시에 서는 시각 = 코드상 매수 신호 시각(근사)
"""
import json, urllib.request, sys

CASES = json.load(open(sys.argv[1]))

def minutes(t, d):
    ds = d.replace("-", "")
    u = f"https://api.stock.naver.com/chart/domestic/item/{t}/minute?startDateTime={ds}0900&endDateTime={ds}1530"
    return json.loads(urllib.request.urlopen(u, timeout=20).read())

for c in CASES:
    bars = minutes(c["t"], c["date"])
    cum = 0; first_cross = None; sig = None; first_cross_any = None; maxh_win = 0
    for b in bars:
        hhmm = b["localDateTime"][8:12]
        cum += int(b["accumulatedTradingVolume"] or 0)
        h = int(b["highPrice"]); lo = int(b["lowPrice"])
        if h >= c["base_high"] and first_cross_any is None:
            first_cross_any = (hhmm, cum)
        if "0905" <= hhmm <= "1430":
            maxh_win = max(maxh_win, h)
            if h >= c["base_high"] and first_cross is None:
                first_cross = (hhmm, cum)
            if sig is None and h >= c["base_high"] and lo <= c["base_high"] * 1.075 and cum >= c["vol_thr"]:
                sig = (hhmm, cum, lo, h)
    print(json.dumps(dict(date=c["date"], t=c["t"], name=c["name"], base_high=c["base_high"], vol_thr=c["vol_thr"],
        day_high=c["h"], krx_min_cumvol=cum, first_cross_any=first_cross_any, first_cross_0905_1430=first_cross,
        max_high_0905_1430=maxh_win, simulated_buy=sig), ensure_ascii=False))
