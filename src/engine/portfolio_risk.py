"""포트폴리오 리스크 관찰 순수함수 (사이클 H, 관찰 전용 Phase 1).

전 전략 합산 오픈 리스크 + 섹터/전략별 노출을 집계하는 순수함수. DB/HTTP/시계/
registry/kojiro 미접촉 (quant_score / te_metrics / ta_indicators 선례 — 매매 안전성
8영역 미접촉). 호출자가 strategies·net_asset·hard_stop_pcts·sector_of 를 주입(pull)하며,
이 모듈은 어떤 매매 상태도 읽거나 변경하지 않는다 (**배제 0**).

배경 = 「터틀 자금관리」 서적 대조 감사(2026-08-02)에서 도출한 최대 구조적 갭 2건의
Phase 1 가시화:
  (1) 포트폴리오 단위 총리스크 상한 부재 (전략별 daily_loss 는 격리)
  (2) 전략 간 섹터 집중 무통제 (is_ticker_blocked_for_buy 는 동일 종목코드만)
매수 차단·SOFT 상한·entry_atr 정밀화는 2주 관찰 후 Phase 2 인계.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

# 하드손절% 후보 키 — 음수만 채택하여 min (최대 계획 손실).
# recommendation_metrics._normalize_stop_loss_rate 선례(5키) 확장 = 7키
# (turtle_backstop_pct / hard_stop_pct 추가로 donchian 터틀·kojiro 커버).
_HARD_STOP_CANDIDATE_KEYS: tuple[str, ...] = (
    "stop_loss_rate",
    "intraday_stop_loss",
    "overnight_stop_loss",
    "stop_loss_main",
    "stop_loss_pre_nxt",
    "turtle_backstop_pct",
    "hard_stop_pct",
)

_DEFAULT_HARD_STOP_PCT = -7.0


def extract_hard_stop_pct(
    params: Optional[dict], *, default: float = _DEFAULT_HARD_STOP_PCT
) -> float:
    """전략 params 에서 하드손절% 추출 — 후보 7키 中 **음수만** → min (최대 계획 손실).

    후보 0건(양수만 / 결측 / None) → default (기본 -7.0). **0.0 반환 금지** —
    손절 없음을 리스크 0 으로 오인하면 관찰 노출이 과소평가되므로 보수적 기본 적용.
    """
    if not isinstance(params, dict):
        return default
    negatives: list[float] = []
    for key in _HARD_STOP_CANDIDATE_KEYS:
        val = params.get(key)
        if val is None:
            continue
        try:
            fv = float(val)
        except (TypeError, ValueError):
            continue
        if fv < 0:
            negatives.append(fv)
    if not negatives:
        return default
    return min(negatives)


def compute_portfolio_risk_snapshot(
    strategies: Iterable[Any],
    *,
    net_asset: int,
    hard_stop_pcts: dict[str, float],
    sector_of: dict[str, str],
) -> dict:
    """전 전략 합산 오픈 리스크 + 섹터/전략별 노출 스냅샷 (관찰 전용, 배제 0).

    포지션 리스크 프록시 = ``buy_price × quantity × |hard_stop_pct| / 100``
    (계획 손실금액, int). turtle entry_atr 정밀화는 Phase 2 인계 — 지금은 손절%
    프록시로 통일(단순·견고, 전 전략 동일 척도).

    Args:
        strategies: registry.all() 로 얻은 전략 리스트 (호출자 주입 — 모듈이 registry 미참조).
        net_asset: 순자산 (open_risk_pct_of_net 계산용).
        hard_stop_pcts: ``{strategy_id: 하드손절%}``. 결측 전략은 -7.0 fail-open.
        sector_of: ``{ticker: 섹터명}``. 결측 ticker 는 ``미분류-{ticker}`` 독립 취급.

    Returns:
        스냅샷 dict — total_notional_won / total_open_risk_won / open_risk_pct_of_net /
        concurrent_positions / by_strategy(0 포지션 전략 포함) / by_sector(포지션有만) /
        top_sector(risk_won 최대, 포지션 0 → None).

    입력(strategies / positions / sector_of / hard_stop_pcts) 은 무변경 (관찰 전용 계약).
    """
    total_notional = 0
    total_risk = 0
    concurrent = 0
    by_strategy: dict[str, dict] = {}
    by_sector: dict[str, dict] = {}

    for strat in strategies:
        sid = getattr(strat, "strategy_id", None) or "unknown"
        s_notional = 0
        s_risk = 0
        s_positions = 0

        pct = hard_stop_pcts.get(sid, _DEFAULT_HARD_STOP_PCT)
        try:
            abs_pct = abs(float(pct))
        except (TypeError, ValueError):
            abs_pct = abs(_DEFAULT_HARD_STOP_PCT)

        state = getattr(strat, "state", None)
        positions = getattr(state, "positions", None) if state is not None else None
        if isinstance(positions, dict):
            for ticker, pos in positions.items():
                buy_price = getattr(pos, "buy_price", None)
                quantity = getattr(pos, "quantity", None)
                if buy_price is None or quantity is None:
                    continue
                try:
                    notional = int(buy_price) * int(quantity)
                    risk = int(notional * abs_pct / 100)
                except (TypeError, ValueError):
                    continue
                s_notional += notional
                s_risk += risk
                s_positions += 1

                sector = sector_of.get(ticker) or f"미분류-{ticker}"
                bucket = by_sector.setdefault(
                    sector, {"positions": 0, "notional_won": 0, "risk_won": 0}
                )
                bucket["positions"] += 1
                bucket["notional_won"] += notional
                bucket["risk_won"] += risk

        by_strategy[sid] = {
            "positions": s_positions,
            "notional_won": s_notional,
            "risk_won": s_risk,
        }
        total_notional += s_notional
        total_risk += s_risk
        concurrent += s_positions

    open_risk_pct = (
        round(total_risk / net_asset * 100, 2)
        if net_asset and net_asset > 0
        else 0.0
    )

    top_sector = None
    if by_sector:
        top_name = max(by_sector, key=lambda k: by_sector[k]["risk_won"])
        top_risk = by_sector[top_name]["risk_won"]
        share = round(top_risk / total_risk * 100, 2) if total_risk > 0 else 0.0
        top_sector = {
            "sector": top_name,
            "risk_won": top_risk,
            "risk_share_pct": share,
        }

    return {
        "total_notional_won": total_notional,
        "total_open_risk_won": total_risk,
        "open_risk_pct_of_net": open_risk_pct,
        "concurrent_positions": concurrent,
        "by_strategy": by_strategy,
        "by_sector": by_sector,
        "top_sector": top_sector,
    }
