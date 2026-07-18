"""터틀 유닛 sizing 오프라인 검증 — 리스크 정규화 실증 (Phase 2A-1 검증).

터틀 sizing 의 핵심 주장 = "유닛당 리스크가 변동성(ATR) 무관하게 균등"이다.
kojiro 는 손절이 2ATR 이라, sizing 을 turtle 로 바꾸면 유닛당 리스크가 정확히
`stop_atr × risk_pct × 예산` (변동성 무관 상수) 이 되어야 한다. 반면 position_ratio 는
유닛당 리스크가 `stop_atr × position_ratio × (ATR/종가) × 예산` 으로 변동성에 비례해 흩어진다.

본 도구는 유니버스(합성 현실 분포 or 실 데이터 CSV)에 대해 두 sizing 을 계산하고
유닛당 리스크 분포(평균/표준편차/변동계수 CV/최소/최대)를 비교해 정규화를 실증한다.

사용:
    python -m tools.validate_turtle_sizing                       # 합성 현실 유니버스
    python -m tools.validate_turtle_sizing --csv universe.csv    # 실 데이터 (ticker,price,atr)
    python -m tools.validate_turtle_sizing --budget 100000000 --risk-pct 0.005 --n 200

실 데이터(RDS): DATABASE_URL 있는 환경(EC2)에서 stock_master_daily 로 종목별 ATR 산출 →
CSV(ticker,price,atr) 로 export 후 --csv 로 투입. 로컬(DB 없음)은 합성 유니버스로 속성 실증.
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
from dataclasses import dataclass

from src.engine.turtle_sizing import compute_unit_qty

# kojiro 정체성 상수
KOJIRO_STOP_ATR = 2.0          # 2ATR 하드손절
KOJIRO_POSITION_RATIO = 0.20   # position_ratio 기본
KOJIRO_ATR_BAND = (0.01, 0.045)  # ATR/종가 밴드 (유니버스 게이트)


@dataclass
class Row:
    ticker: str
    price: int
    atr: float


def _synthetic_universe(n: int, seed: int = 42) -> list[Row]:
    """KR 시장 현실 분포 근사 — 가격 5천~50만(로그균등), ATR/종가 kojiro 밴드 1.0~4.5% 균등."""
    rng = random.Random(seed)
    rows: list[Row] = []
    lo, hi = KOJIRO_ATR_BAND
    for i in range(n):
        # 로그균등 가격 (저가주~고가주 현실 분포)
        price = int(round(10 ** rng.uniform(3.7, 5.7)))  # ≈5,000 ~ 500,000
        atr_ratio = rng.uniform(lo, hi)  # 밴드 내 균등 (게이트 통과 종목)
        atr = price * atr_ratio
        rows.append(Row(f"S{i:04d}", price, atr))
    return rows


def _load_csv(path: str) -> list[Row]:
    rows: list[Row] = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(Row(r["ticker"], int(float(r["price"])), float(r["atr"])))
    return rows


async def _load_db(limit: int, band_only: bool) -> list[Row]:
    """실 RDS(stock_master_daily)에서 kojiro 유니버스 종목별 ATR(Wilder20)+종가 산출.

    DATABASE_URL 필요 (EC2 환경). kojiro `_scan_universe`/`get_recent_daily_normalized`
    와 동일 소스·동일 ATR 정의(kojiro_indicators Wilder ewm20). READ-ONLY (SELECT).
    """
    import pandas as pd
    from src.db import pg
    from src.db import stock_master as sm
    from src.db import stock_master_daily as smd
    from src.engine.kojiro_indicators import atr as k_atr, KojiroIndicatorConfig

    cfg = KojiroIndicatorConfig()
    await pg.init_pool()
    try:
        result = await sm.list_by_filter(
            min_market_cap=50_000_000_000, min_trade_amount=1_000_000_000,
            is_kospi200=True, is_kosdaq150=True, limit=limit,
        )
        rows_meta = result[0] if isinstance(result, tuple) else result
        out: list[Row] = []
        for r in rows_meta:
            t = r.get("ticker") if isinstance(r, dict) else None
            if not (t and len(t) == 6 and t.isdigit()):
                continue
            try:
                candles = await smd.get_recent_daily(t, days=40)  # DESC 정규화
            except Exception:
                continue
            if len(candles) < cfg.atr_period + 2:
                continue
            asc = list(reversed(candles))  # DESC→ASC
            df = pd.DataFrame({
                "high": [int(c.get("high_price") or 0) for c in asc],
                "low": [int(c.get("low_price") or 0) for c in asc],
                "close": [int(c.get("close_price") or 0) for c in asc],
            })
            try:
                atr_val = float(k_atr(df, cfg.atr_period).iloc[-1])
            except Exception:
                continue
            close = int(asc[-1].get("close_price") or 0)
            if atr_val <= 0 or close <= 0:
                continue
            if band_only and not (KOJIRO_ATR_BAND[0] <= atr_val / close <= KOJIRO_ATR_BAND[1]):
                continue
            out.append(Row(t, close, atr_val))
        return out
    finally:
        await pg.close_pool()


def _stats(values: list[float]) -> dict:
    m = statistics.fmean(values)
    sd = statistics.pstdev(values)
    return {
        "mean": m, "std": sd, "cv": (sd / m if m else 0.0),
        "min": min(values), "max": max(values),
        "spread": (max(values) / min(values) if min(values) > 0 else float("inf")),
    }


def run(rows: list[Row], budget: int, risk_pct: float) -> None:
    turtle_risk: list[float] = []
    pr_risk: list[float] = []
    turtle_notional: list[float] = []
    pr_notional: list[float] = []
    examples: list[tuple] = []

    pr_amount = int(budget * KOJIRO_POSITION_RATIO)
    for row in rows:
        t_qty = compute_unit_qty(budget, row.atr, risk_pct)
        p_qty = pr_amount // row.price
        if t_qty <= 0 or p_qty <= 0:
            continue
        # 유닛당 리스크 = 수량 × 손절폭(2ATR). kojiro 손절은 sizing 무관 항상 2ATR.
        t_r = t_qty * KOJIRO_STOP_ATR * row.atr
        p_r = p_qty * KOJIRO_STOP_ATR * row.atr
        turtle_risk.append(t_r)
        pr_risk.append(p_r)
        turtle_notional.append(t_qty * row.price)
        pr_notional.append(p_qty * row.price)
        if len(examples) < 6:
            examples.append((row.ticker, row.price, round(row.atr), round(row.atr / row.price * 100, 2),
                             t_qty, round(t_r), p_qty, round(p_r)))

    ts, ps = _stats(turtle_risk), _stats(pr_risk)
    tn, pn = _stats(turtle_notional), _stats(pr_notional)
    ideal = budget * KOJIRO_STOP_ATR * risk_pct  # 이상적 유닛당 리스크 (상수)

    print(f"\n{'='*78}")
    print(f"터틀 유닛 sizing 리스크 정규화 검증 — 종목 {len(turtle_risk)} / 예산 {budget:,} / risk_pct {risk_pct:.3%}")
    print(f"{'='*78}")
    print(f"이상적 유닛당 리스크(상수) = 예산 × stop_atr({KOJIRO_STOP_ATR}) × risk_pct = {ideal:,.0f} (예산의 {ideal/budget:.2%})\n")

    print("── 유닛당 리스크 (수량 × 2ATR 손절폭) ──")
    print(f"{'':20}{'평균':>14}{'표준편차':>14}{'변동계수CV':>12}{'최소':>14}{'최대':>14}{'최대/최소':>10}")
    print(f"{'터틀(turtle)':20}{ts['mean']:>14,.0f}{ts['std']:>14,.0f}{ts['cv']:>12.3f}{ts['min']:>14,.0f}{ts['max']:>14,.0f}{ts['spread']:>10.2f}")
    print(f"{'포지션비중(pr)':20}{ps['mean']:>14,.0f}{ps['std']:>14,.0f}{ps['cv']:>12.3f}{ps['min']:>14,.0f}{ps['max']:>14,.0f}{ps['spread']:>10.2f}")

    print("\n── 유닛당 명목금액 (수량 × 가격) ──")
    print(f"{'터틀(turtle)':20}{tn['mean']:>14,.0f}{tn['std']:>14,.0f}{tn['cv']:>12.3f}{tn['min']:>14,.0f}{tn['max']:>14,.0f}{tn['spread']:>10.2f}")
    print(f"{'포지션비중(pr)':20}{pn['mean']:>14,.0f}{pn['std']:>14,.0f}{pn['cv']:>12.3f}{pn['min']:>14,.0f}{pn['max']:>14,.0f}{pn['spread']:>10.2f}")

    print("\n── 예시 (ticker / 가격 / ATR / ATR%종가 / 터틀수량 / 터틀리스크 / pr수량 / pr리스크) ──")
    for e in examples:
        print(f"  {e[0]:8} price={e[1]:>8,} atr={e[2]:>6,} ({e[3]:>4}%)  turtle: {e[4]:>5}주 리스크={e[5]:>10,}  pr: {e[6]:>5}주 리스크={e[7]:>10,}")

    print(f"\n{'='*78}")
    print("판정:")
    tv = "✓" if ts["cv"] < 0.05 else "✗"
    print(f"  {tv} 터틀 유닛당 리스크 정규화: CV={ts['cv']:.3f} (< 0.05 = 변동성 무관 균등, floor 절삭 오차만)")
    print(f"  · 포지션비중 유닛당 리스크: CV={ps['cv']:.3f}, 최대/최소 {ps['spread']:.1f}배 (변동성 비례 흩어짐)")
    print(f"  → 터틀은 고변동 종목을 적게(명목 최대/최소 {tn['spread']:.1f}배) 사서 유닛당 리스크를 {ps['spread']/max(ts['spread'],1e-9):.0f}배 더 균등화")
    print(f"{'='*78}\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="store_true", help="실 RDS 데이터 (EC2, DATABASE_URL 필요)")
    ap.add_argument("--csv", help="실 데이터 CSV (컬럼: ticker,price,atr)")
    ap.add_argument("--budget", type=int, default=100_000_000, help="전략 할당 예산 (기본 1억)")
    ap.add_argument("--risk-pct", type=float, default=0.005, help="유닛 리스크 비율 (기본 0.5%)")
    ap.add_argument("--n", type=int, default=200, help="합성 유니버스 종목 수 (기본 200)")
    ap.add_argument("--limit", type=int, default=250, help="--db 유니버스 조회 상한")
    ap.add_argument("--no-band", action="store_true", help="--db 에서 ATR 밴드(1~4.5%) 필터 미적용")
    args = ap.parse_args()

    if args.db:
        import asyncio
        rows = asyncio.run(_load_db(args.limit, band_only=not args.no_band))
        src = f"실 RDS 유니버스(KOSPI200∪KOSDAQ150, {len(rows)}종목, 밴드필터={'off' if args.no_band else 'on'})"
    elif args.csv:
        rows = _load_csv(args.csv)
        src = args.csv
    else:
        rows = _synthetic_universe(args.n)
        src = f"합성 현실 유니버스(n={args.n}, ATR/종가 1.0~4.5% 밴드)"
    print(f"데이터: {src}")
    if not rows:
        print("⚠️ 유니버스 0종목 — 데이터/필터 확인")
        return
    run(rows, args.budget, args.risk_pct)


if __name__ == "__main__":
    main()
