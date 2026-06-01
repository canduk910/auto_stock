"""사이클 50 (2026-06-01) — BFB 폴/플래그 4 sub-condition 조건별 실측 계측 스크립트.

[목적]
근본 원인 2 (구조적 모순) 데이터 확정: 사이클 48 이 BFB 유니버스를 거래량순위
(거래량 폭발 종목)로 교체했는데, 플래그 검출은 거래량 *수축* (플래그 평균 < 폴 평균 × 0.6)
을 요구 → 거래량 폭발 ⊥ 수축. 거래량 수축이 진짜 바인딩 조건인지 실제 일봉으로 확정/반증.

[환경 제약]
이 스크립트는 KIS OpenAPI 실호출이 필요 (APP_KEY/SECRET + 외부 네트워크).
클라우드 샌드박스에서는 KIS 도달 불가 → **EC2 운영 환경에서 실행**.

[실행 — EC2]
    cd ~/auto_stock
    # 운영과 동일한 .env (KIS_ENV / KIS_APP_KEY_* / KIS_APP_SECRET_*) 로드된 상태
    python -m tools.measure_bfb_pole_flag

    # 또는 종목 커스텀:
    python -m tools.measure_bfb_pole_flag 009150 011070 242040

[출력]
종목별로 `_detect_pole_and_flag_detailed` 의 (result, fail_stage, detail) 을 출력 +
4 sub-condition 전체 조합 스윕 통계 (어느 단계에서 가장 많이 탈락하는지) 를 집계.

[주의]
- DEFAULT_PARAMS / 운영 DB params 어느 쪽으로 평가할지 선택 가능 (--db 플래그).
  기본은 코드 DEFAULT_PARAMS (사이클 48 완화값 15%/0.45). 운영 DB 오버라이드
  (pole_min_return:20 / exchange:SOR 등) 효과를 보려면 --db.
- 이 스크립트는 **계측 전용** — 주문/DB 쓰기 일절 없음. 가치중립.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

# 06/01 funnel 탈락 종목 중 best_return 이 임계를 크게 초과한 5종목 (진단 확정)
DEFAULT_TICKERS = [
    ("009150", "삼성전기"),
    ("011070", "LG이노텍"),
    ("242040", "나무기술"),
    ("000660", "SK하이닉스"),
    ("005930", "삼성전자"),
]

STAGE_KR = {
    "": "통과 (PASS)",
    "no_candle": "일봉 파싱/길이 실패",
    "pole_return": "폴 상승률 미달",
    "pole_red_ratio": "폴 음봉 비율 초과",
    "flag_retracement": "플래그 조정 폭 초과",
    "volume_contraction": "거래량 수축 미달  ← 가설 핵심",
}


async def _measure(tickers: list[tuple[str, str]], use_db: bool) -> None:
    from src.api.condition import fetch_daily_candles
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig

    params: dict = {}
    if use_db:
        try:
            from src.db.strategy_config import load_all

            all_cfg = await load_all()
            cfg = (all_cfg or {}).get("bull_flag_breakout", {}) or {}
            params = cfg.get("params", {}) or {}
            print(f"[params] 운영 DB strategy_config 사용: {params}\n")
        except Exception as e:  # noqa: BLE001
            print(f"[params] DB 로드 실패 ({e}) → 코드 DEFAULT_PARAMS 사용\n")
            params = {}
    else:
        print("[params] 코드 DEFAULT_PARAMS 사용 (사이클 48 완화값)\n")

    strat = BullFlagBreakoutStrategy(
        StrategyConfig(
            strategy_id="bull_flag_breakout", name="눌림목 돌파", weight=0.0,
            params=params,
        )
    )
    p = strat.config.params
    print(
        "[적용 임계] "
        f"pole_min_return={p['pole_min_return']} / "
        f"pole_max_red_ratio={p['pole_max_red_ratio']} / "
        f"flag_retracement_max={p['flag_retracement_max']} / "
        f"flag_volume_ratio={p['flag_volume_ratio']}\n"
    )

    pole_max = p["pole_lookback_max"]
    flag_max = p["flag_lookback_max"]
    atr_period = p["atr_period"]
    fetch_days = pole_max + flag_max + atr_period + 10

    stage_counter: dict[str, int] = {}

    for ticker, name in tickers:
        try:
            candles = await fetch_daily_candles(ticker, days=fetch_days)
        except Exception as e:  # noqa: BLE001
            print(f"  {ticker} {name}: 일봉 fetch 실패 — {e}")
            continue
        if not candles:
            print(f"  {ticker} {name}: 일봉 응답 빈/None")
            continue

        result, fail_stage, detail = strat._detect_pole_and_flag_detailed(candles)
        stage_counter[fail_stage] = stage_counter.get(fail_stage, 0) + 1
        verdict = STAGE_KR.get(fail_stage, fail_stage)
        print(f"  {ticker} {name}: {verdict}")
        print(f"      detail={detail}")
        print(f"      candles={len(candles)}일")

    print("\n[집계] 바인딩 단계 분포 (가장 멀리 도달한 실패 단계):")
    for stage, cnt in sorted(stage_counter.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {STAGE_KR.get(stage, stage)}: {cnt}종목")

    vc = stage_counter.get("volume_contraction", 0)
    total = sum(stage_counter.values())
    if total:
        print(
            f"\n[결론 힌트] 거래량 수축 바인딩 비율 = {vc}/{total} "
            f"({vc/total*100:.0f}%). "
            "이 비율이 높으면 '거래량순위 유니버스 ⊥ 거래량 수축' 가설 확정."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="BFB 폴/플래그 sub-condition 실측 계측")
    parser.add_argument("tickers", nargs="*", help="종목코드 (생략 시 기본 5종목)")
    parser.add_argument(
        "--db", action="store_true",
        help="운영 DB strategy_config.params 로 평가 (기본은 코드 DEFAULT_PARAMS)",
    )
    args = parser.parse_args()

    if args.tickers:
        tickers = [(t, t) for t in args.tickers]
    else:
        tickers = DEFAULT_TICKERS

    try:
        asyncio.run(_measure(tickers, use_db=args.db))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
