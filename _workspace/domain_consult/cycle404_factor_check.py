"""cycle404 — 요인 ETF 목록 검산 + 명세 §2 배정 규칙 재현 (DB 무접촉, 픽스처만 읽는다).

사용:
    python _workspace/domain_consult/cycle404_factor_check.py \
        [tests/fixtures/cycle404_cluster_closes.json]

하는 일:
  1. 요인 ETF 끼리 120일 수익률 상관 행렬 → 0.9 초과 쌍은 목록 앞의 것만 남긴다.
  2. 보유 13종목에 명세 §2 규칙(CORR_MIN 0.60 · MARKET_MARGIN 0.03 · MIN_OVERLAP 100)
     을 적용해 배정표를 찍고, 자문 cycle400 §3 기대표와 대조한다.

이 스크립트는 명세를 *재현*할 뿐 정본이 아니다 — 정본은 `src/engine/account_cluster.py`.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

WINDOW_RETURNS = 120
MIN_OVERLAP = 100
CORR_MIN = 0.60
MARKET_MARGIN = 0.03
MARKET_TICKER = "069500"
DEDUP_CORR = 0.90

# 확정 목록 = cycle404_factor_etf_list.md 표와 같은 순서(동률 판정 순서).
# 픽스처 추출 후 표가 바뀌면 여기도 같이 바꾼다.
FACTORS: list[tuple[str, str]] = [
    ("091160", "semi"),
    ("305720", "battery"),
    ("244580", "bio"),
    ("091180", "auto"),
    ("139230", "heavy"),
    ("449450", "defense"),
    ("117460", "chem"),
    ("117680", "steel"),
    ("117700", "constr"),
    ("091170", "bank"),
    ("102970", "broker"),
    ("266370", "it"),
    ("228810", "media"),
]

HOLDINGS = [
    "232140", "101160", "083450", "046890", "011790", "425040", "005930",
    "417200", "126340", "217590", "121600", "003490", "006120",
]

# 자문 cycle400 §3 (2요인 비교 시점). 요인이 늘면 바뀔 수 있다 — 결과로 갱신한다.
EXPECTED_2FACTOR = {
    "232140": "semi", "101160": "semi", "083450": "semi", "046890": "semi",
    "011790": "semi", "425040": "semi", "005930": "market",
    "417200": "independent", "126340": "independent", "217590": "independent",
    "121600": "independent", "003490": "independent", "006120": "independent",
}


def returns_by_date(series: list[list], prev_day: dict[str, str] | None = None) -> dict[str, float]:
    """[[bas_dd, close], ...](오래된→최근) → {bas_dd: 전일 대비 수익률}.

    `prev_day` = 시장(069500) 시계열 기준 {영업일: 직전 영업일}. 주어지면 앞 행이
    그 직전 영업일일 때만 수익률을 만든다 — 거래정지 등으로 하루가 빠진 종목의
    「2일치 수익률」 이 요인의 1일 수익률과 짝지어지지 않게 한다(명세 §2 「날짜가 빠진
    날은 그 쌍의 수익률을 만들지 않는다」 의 해석. 명세 검토 지적 2).
    """
    rows = sorted(((str(d), float(c)) for d, c in series), key=lambda x: x[0])
    out: dict[str, float] = {}
    for (d0, c0), (d1, c1) in zip(rows, rows[1:]):
        if prev_day is not None and prev_day.get(d1) != d0:
            continue
        if c0 > 0 and c1 > 0:
            out[d1] = c1 / c0 - 1.0
    return out


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def corr_on(dates: list[str], a: dict, b: dict) -> float | None:
    return pearson([a[d] for d in dates], [b[d] for d in dates])


def assign_one(stock: dict, market: dict, factors: list[tuple[str, dict]]):
    """명세 §2 판정 순서 그대로. 반환 (label, m, best_name, b)."""
    base = sorted(set(stock) & set(market))[-WINDOW_RETURNS:]
    if len(base) < MIN_OVERLAP:
        return "missing", None, None, None
    m = corr_on(base, stock, market)
    if m is None:
        return "missing", None, None, None
    best_name, b = None, None
    for name, f in factors:
        dates = [d for d in base if d in f]
        if len(dates) < MIN_OVERLAP:
            continue
        c = corr_on(dates, stock, f)
        if c is None:
            continue
        if b is None or c > b:  # 동률은 앞의 것 유지
            best_name, b = name, c
    if m >= CORR_MIN and (b is None or m >= b):
        return "market", m, best_name, b
    if b is not None and b >= CORR_MIN and b - m >= MARKET_MARGIN:
        return best_name, m, best_name, b
    return "independent", m, best_name, b


def main(path: str) -> int:
    fx = json.loads(Path(path).read_text())
    series = fx["series"]
    mdates = sorted(str(d) for d, _ in series.get(MARKET_TICKER, []))
    prev_day = dict(zip(mdates[1:], mdates))
    rets = {t: returns_by_date(s, prev_day) for t, s in series.items()}
    market = rets.get(MARKET_TICKER)
    if not market or len(market) < MIN_OVERLAP:
        print("[unavailable] market series short")
        return 1

    # 1) 요인 자체 결측 · 중복 제거
    usable: list[tuple[str, str]] = []
    for t, name in FACTORS:
        n = len(rets.get(t, {}))
        if n < MIN_OVERLAP:
            print(f"factor_missing {name}({t}) returns={n}")
            continue
        usable.append((t, name))
    kept: list[tuple[str, str]] = []
    print("\n# 요인 쌍 상관 (> 0.80 만 표시)")
    for t, name in usable:
        dup = None
        for kt, kn in kept:
            dates = sorted(set(rets[t]) & set(rets[kt]))[-WINDOW_RETURNS:]
            c = corr_on(dates, rets[t], rets[kt])
            if c is not None and c > 0.80:
                print(f"  {name}~{kn} = {c:.2f}")
            if c is not None and c > DEDUP_CORR and dup is None:
                dup = (kn, c)
        if dup:
            print(f"  DROP {name}({t}) — {dup[0]} 와 {dup[1]:.2f}")
        else:
            kept.append((t, name))
    print("\n# 확정 요인:", ", ".join(f"{n}({t})" for t, n in kept))

    # 2) 보유 배정
    factors = [(n, rets[t]) for t, n in kept]
    print("\n# 보유 배정")
    print("ticker  label        m     best        b     expected(2요인)")
    diff = 0
    for t in HOLDINGS:
        if t not in rets:
            print(f"{t}  missing(series 없음)")
            continue
        label, m, bn, b = assign_one(rets[t], market, factors)
        exp = EXPECTED_2FACTOR[t]
        mark = "" if label == exp else "  <-- 달라짐"
        diff += bool(mark)
        fm = f"{m:.2f}" if m is not None else "-"
        fb = f"{b:.2f}" if b is not None else "-"
        print(f"{t}  {label:<11} {fm:>5}  {str(bn):<10} {fb:>5}  {exp}{mark}")
    print(f"\n달라진 종목 {diff}개 (as_of={fx.get('as_of')})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/cycle404_cluster_closes.json"))
