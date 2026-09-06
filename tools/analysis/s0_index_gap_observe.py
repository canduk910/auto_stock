#!/usr/bin/env python3
"""S0 — 지수 갭 게이트 야간 재구성 관측 (읽기 전용, 주 1회).

사용자 결정 2026-09-06 카드 ③ "진행". 코드 0줄·SELECT 만·주 1회.

무엇을 재는가
-------------
2026-09-06 종합 검토가 유일하게 살려 둔 후보 = **"코스피200 09:00 지수 갭 ≥ 0 인
날에만 매수"** 게이트다. 그 추정치(VB 풀 개선 +47.8bp, p 0.0070)는 **표본 내**
값이고, 프록시 6종 가족 중앙값은 ≈+34bp(범위 +28~+48)였다. 배선 여부를 정하려면
**표본 밖 20 거래일**이 필요하다 — 이 스크립트가 그 20일을 모은다.

배선하지 않는다. 관측만 한다. 매수는 게이트와 무관하게 현행대로 나간다.

사전 등록 (2026-09-06, 관측 시작 전에 고정)
-------------------------------------------
- 표본 밖 창 시작 = 2026-09-07 (그 이전은 추정에 쓴 표본 내 구간이라 판정에서 제외)
- 판정 시점 = 표본 밖 거래일 20일 누적
- 1차 지표 = VB **실체결 왕복** 평균 gross bp 의 (갭≥0 일) − (갭<0 일) 차이
- 사전 등록 방향 = 양(+). 부호가 음이면 그 자체로 기각이다
- 주의: 이 지표는 검토 리포트의 +47.8bp 와 **척도가 다르다**. 그 값은 후보 *풀* 개선치이고
  이것은 실체결 왕복 차이다. 비교 기준은 같은 지표의 표본 내 값이고, 그 값은 이 스크립트가
  `in_sample` 행에 스스로 계산해 둔다 — 리터럴로 박지 않는다
- 보조 관측 = KOSDAQ150 프록시, LTV, 왕복 수·거래일 수

산출
----
  _workspace/analysis/s0_index_gap_observation/observations.csv   거래일 × 지수갭 × 전략성과
  _workspace/analysis/s0_index_gap_observation/roundtrips.csv     왕복 원자료 (매수일 귀속)
  _workspace/analysis/s0_index_gap_observation/summary.md         누적 판정표

실행
----
  python3 tools/analysis/s0_index_gap_observe.py          # 전 구간 재빌드 (멱등)
  python3 tools/analysis/s0_index_gap_observe.py --since 2026-08-01

전 구간을 매번 다시 읽어 덮어쓴다 — 이어붙이지 않으므로 재실행이 안전하다.
"""
from __future__ import annotations

import argparse
import collections
import csv
import os
import shlex
import statistics
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "_workspace", "analysis", "s0_index_gap_observation")
SEP = "\x1f"

IDX = {"k200": "069500", "kq150": "229200"}
STRATS = ("volatility_breakout", "long_tail_volatility")
LABEL = {"volatility_breakout": "VB", "long_tail_volatility": "LTV"}

# 사전 등록 상수 — 관측 시작 전에 고정했다. 사후 변경 금지.
OOS_START = "2026-09-07"      # 표본 밖 창 시작
TARGET_DAYS = 20              # 판정에 필요한 표본 밖 거래일
PREREG_DIRECTION = "+"        # 사전 등록 방향
POOL_ESTIMATE_BP = 47.8       # 참고용 — 리포트의 *풀* 개선치. 이 스크립트의 지표와 척도가 다르다


def psql(sql: str) -> list[list[str]]:
    """운영 DB SELECT (읽기 전용). ssh auto-stock 경유."""
    remote = (
        "cd ~/auto_stock && "
        "DSN=$(grep '^DATABASE_URL=' .env | cut -d= -f2- | tr -d '\"') && "
        "psql \"$DSN\" -X -q -At -F $'\\x1f' -c " + shlex.quote(sql)
    )
    proc = subprocess.run(["ssh", "auto-stock", "bash", "-s"],
                          input=remote, text=True, capture_output=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit("psql 실패 — DB 는 읽기만 했고 아무것도 바꾸지 않았다")
    return [ln.split(SEP) for ln in proc.stdout.splitlines() if ln.strip()]


def fetch_index_gaps(since: str) -> dict[str, dict[str, float]]:
    """거래일 → {k200: 갭bp, kq150: 갭bp}. 갭 = (시가 − 전일종가) / 전일종가."""
    rows = psql(
        "SELECT ticker, bas_dd::text, open_price, close_price FROM stock_master_daily "
        f"WHERE ticker IN ('{IDX['k200']}','{IDX['kq150']}') AND bas_dd >= '{since}' "
        "ORDER BY ticker, bas_dd"
    )
    by_ticker: dict[str, list[tuple[str, float, float]]] = collections.defaultdict(list)
    for tk, dd, op, cl in rows:
        try:
            o, c = float(op), float(cl)
        except (TypeError, ValueError):
            continue
        if o > 0 and c > 0:
            by_ticker[tk].append((dd, o, c))

    gaps: dict[str, dict[str, float]] = collections.defaultdict(dict)
    for name, tk in IDX.items():
        series = by_ticker.get(tk, [])
        for i in range(1, len(series)):
            dd, op, _ = series[i]
            prev_close = series[i - 1][2]
            gaps[dd][name] = (op - prev_close) / prev_close * 10_000.0
    return gaps


def fetch_roundtrips(since: str) -> list[dict]:
    """FIFO 왕복. 매수일에 귀속한다 — 게이트가 매수일 판정이기 때문이다."""
    rows = psql(
        "SELECT to_char(timestamp AT TIME ZONE 'Asia/Seoul','YYYY-MM-DD'), "
        "to_char(timestamp AT TIME ZONE 'Asia/Seoul','HH24:MI:SS'), "
        "strategy, ticker, trade_type, price, quantity, COALESCE(profit_loss,0), id "
        "FROM trade_history "
        f"WHERE strategy IN ({','.join(repr(s) for s in STRATS)}) "
        f"AND timestamp >= '{since} 00:00:00+09' "
        "AND status IN ('COMPLETED','PARTIAL') "
        "ORDER BY timestamp, id"
    )
    queues: dict[tuple[str, str], collections.deque] = collections.defaultdict(collections.deque)
    out: list[dict] = []
    for dd, hhmm, strat, ticker, ttype, price, qty, pl, tid in rows:
        try:
            px, q = float(price), int(float(qty))
        except (TypeError, ValueError):
            continue
        if q <= 0:
            continue
        key = (strat, ticker)
        if ttype == "BUY":
            queues[key].append({"date": dd, "time": hhmm, "price": px, "qty": q, "id": tid})
            continue
        if ttype != "SELL":
            continue
        try:
            sell_pl = float(pl)
        except (TypeError, ValueError):
            sell_pl = 0.0
        remaining, matched = q, []
        while remaining > 0 and queues[key]:
            buy = queues[key][0]
            take = min(remaining, buy["qty"])
            matched.append((buy, take))
            buy["qty"] -= take
            remaining -= take
            if buy["qty"] == 0:
                queues[key].popleft()
        if not matched:
            continue                      # 매수 기록이 창 밖 — 귀속 불가, 버린다
        filled = sum(t for _, t in matched)
        for buy, take in matched:
            share = take / filled
            notional = buy["price"] * take
            gross = sell_pl * share
            out.append({
                "buy_date": buy["date"], "buy_time": buy["time"], "sell_date": dd,
                "strategy": strat, "ticker": ticker, "qty": take,
                "buy_price": buy["price"], "sell_price": px,
                "notional": notional, "gross_pl": gross,
                "gross_bp": (gross / notional * 10_000.0) if notional > 0 else 0.0,
                "buy_trade_id": buy["id"], "sell_trade_id": tid,
            })
    return out


def build(since: str) -> None:
    os.makedirs(OUT, exist_ok=True)
    gaps = fetch_index_gaps(since)
    trips = fetch_roundtrips(since)

    with open(os.path.join(OUT, "roundtrips.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trips[0].keys()) if trips else
                           ["buy_date", "strategy", "ticker", "gross_bp"])
        w.writeheader()
        w.writerows(sorted(trips, key=lambda r: (r["buy_date"], r["strategy"], r["ticker"])))

    by_day: dict[str, dict[str, list[float]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for t in trips:
        by_day[t["buy_date"]][t["strategy"]].append(t["gross_bp"])

    days = sorted(set(gaps) | set(by_day))
    rows = []
    for dd in days:
        g = gaps.get(dd, {})
        row = {
            "date": dd,
            "window": "out_of_sample" if dd >= OOS_START else "in_sample",
            "k200_gap_bp": round(g["k200"], 2) if "k200" in g else "",
            "kq150_gap_bp": round(g["kq150"], 2) if "kq150" in g else "",
            "gate_k200": ("pass" if g["k200"] >= 0 else "block") if "k200" in g else "",
            "gate_kq150": ("pass" if g["kq150"] >= 0 else "block") if "kq150" in g else "",
        }
        for s in STRATS:
            v = by_day.get(dd, {}).get(s, [])
            row[f"{LABEL[s]}_n"] = len(v)
            row[f"{LABEL[s]}_mean_bp"] = round(statistics.fmean(v), 2) if v else ""
            row[f"{LABEL[s]}_sum_won"] = round(sum(
                t["gross_pl"] for t in trips if t["buy_date"] == dd and t["strategy"] == s), 1) if v else ""
        rows.append(row)

    with open(os.path.join(OUT, "observations.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["date"])
        w.writeheader()
        w.writerows(rows)

    write_summary(rows, trips)
    print(f"거래일 {len(rows)} · 왕복 {len(trips)} → {OUT}")


def _split(trips: list[dict], gaps_by_day: dict, strat: str, window: str) -> tuple[list[float], list[float]]:
    passed, blocked = [], []
    for t in trips:
        if t["strategy"] != strat:
            continue
        dd = t["buy_date"]
        if (window == "out_of_sample") != (dd >= OOS_START):
            continue
        verdict = gaps_by_day.get(dd, {}).get("gate_k200")
        if verdict == "pass":
            passed.append(t["gross_bp"])
        elif verdict == "block":
            blocked.append(t["gross_bp"])
    return passed, blocked


def write_summary(rows: list[dict], trips: list[dict]) -> None:
    gaps_by_day = {r["date"]: r for r in rows}
    oos_days = [r for r in rows if r["window"] == "out_of_sample" and r["gate_k200"]]
    n_oos = len(oos_days)

    L = ["# S0 — 지수 갭 게이트 관측 (표본 밖 누적)", ""]
    L.append(f"- 사전 등록: 표본 밖 시작 **{OOS_START}**, 판정 **{TARGET_DAYS} 거래일**, "
             f"사전 등록 방향 **{PREREG_DIRECTION}**")
    L.append("- 지표 = 실체결 왕복 평균 gross bp 차이. 비교 기준은 아래 표의 `in_sample` 행이다 "
             f"— 리포트의 풀 개선 +{POOL_ESTIMATE_BP}bp 와는 **척도가 달라 직접 비교하지 않는다**")
    L.append(f"- 표본 밖 누적 **{n_oos} / {TARGET_DAYS} 거래일**"
             + (f" — 남은 {TARGET_DAYS - n_oos}일" if n_oos < TARGET_DAYS else " — **판정 가능**"))
    if oos_days:
        p = sum(1 for r in oos_days if r["gate_k200"] == "pass")
        L.append(f"- 게이트 통과일 {p} / 차단일 {n_oos - p}")
    L += ["", "## 누적 비교 (매수일 귀속, gross bp)", "",
          "| 창 | 전략 | 갭≥0 일 n | 평균bp | 갭<0 일 n | 평균bp | 차이 |",
          "|---|---|---|---|---|---|---|"]
    for window in ("in_sample", "out_of_sample"):
        for s in STRATS:
            a, b = _split(trips, gaps_by_day, s, window)
            ma = statistics.fmean(a) if a else None
            mb = statistics.fmean(b) if b else None
            diff = f"{ma - mb:+.1f}" if (ma is not None and mb is not None) else "—"
            L.append(f"| {window} | {LABEL[s]} | {len(a)} | "
                     f"{f'{ma:+.1f}' if ma is not None else '—'} | {len(b)} | "
                     f"{f'{mb:+.1f}' if mb is not None else '—'} | **{diff}** |")
    L += ["", "## 읽는 법", "",
          f"- `out_of_sample` 행의 **차이** 열이 판정 대상이다. {TARGET_DAYS} 거래일이 차기 전의 값은 참고일 뿐이다.",
          "- 차이가 음수면 사전 등록 방향과 반대이므로 그 자체로 기각이다.",
          "- 차이가 양수여도 같은 표의 `in_sample` 값과 크게 어긋나면 크기 추정이 부정확했다는 뜻이다.",
          f"- 리포트의 풀 개선 +{POOL_ESTIMATE_BP}bp 는 후보 풀 기준이라 이 표의 값과 **직접 비교할 수 없다**.",
          "- 이 관측은 **배선이 아니다**. 매수는 게이트와 무관하게 현행대로 나간다.",
          "",
          "## 한계",
          "",
          "- 지수 프록시는 ETF(069500 / 229200) 일봉이다. 지수 자체가 아니다.",
          "- 왕복은 매수일에 귀속한다(게이트가 매수일 판정이라서). 매도일 귀속과 다르다.",
          "- gross 기준이다. 수수료·세금은 빠져 있다(왕복 약 28bp).",
          "- 실체결 표본이라 `max_positions` 슬롯 대체가 반영되지 않았다 — 게이트로 하루를 "
          "통째로 막으면 그날 자리가 다음 날로 밀리는 효과가 여기에는 없다.",
          "- 매수 기록이 조회 창 밖인 매도는 귀속 불가라 버린다.",
          ]
    with open(os.path.join(OUT, "summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="S0 지수 갭 게이트 관측 (읽기 전용)")
    ap.add_argument("--since", default="2026-07-01", help="조회 시작일 (기본 2026-07-01)")
    build(ap.parse_args().since)
