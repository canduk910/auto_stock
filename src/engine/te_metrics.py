"""TE(트레이딩 예지치) + RR비율(손익비) 순수 계산 — 사이클 F.

관찰 전용. `get_trade_pairs`(진입가 기준 profit_rate) 출력을 입력받아
전략별 최근 N일 성과 지표를 계산하는 순수 함수. 매매 hot path 무접촉.

명세: `_workspace/red/_behaviors_cycleF_te_rr_20260802.md` (F-B1~F-B9)
자문: `_workspace/domain_consult/cycle_te_expectancy_dashboard_20260802.md`

**소스·기준(F-B2, HIGH)**: TE% = 모집단 `profit_rate`(진입가 기준) 단순평균.
`recommendation_metrics.compute_metrics`(매도가 기준 pnl/gross) 재사용 금지.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass
class TeRrMetrics:
    strategy_id: str
    n: int
    win: int
    loss: int
    even: int
    win_rate: float
    avg_win_pct: float | None
    avg_loss_pct: float | None
    te_pct: float
    te_krw_avg: float
    realized_sum_krw: float
    rr: float | None
    required_rr: float | None
    rr_margin: float | None
    rr_available: bool
    sample_tier: str
    verdict: str
    structure_tag: str | None
    single_trade_dominant: bool


def _empty_metrics(strategy_id: str) -> TeRrMetrics:
    return TeRrMetrics(
        strategy_id=strategy_id,
        n=0,
        win=0,
        loss=0,
        even=0,
        win_rate=0.0,
        avg_win_pct=None,
        avg_loss_pct=None,
        te_pct=0.0,
        te_krw_avg=0.0,
        realized_sum_krw=0.0,
        rr=None,
        required_rr=None,
        rr_margin=None,
        rr_available=False,
        sample_tier="insufficient",
        verdict="undecided",
        structure_tag=None,
        single_trade_dominant=False,
    )


def _sample_tier(n: int) -> str:
    if n < 20:
        return "insufficient"
    if n < 50:
        return "low"
    return "normal"


def compute_te_rr(
    pairs: list[dict],
    *,
    now: datetime,
    window_days: int = 90,
    strategy_id: str = "",
) -> TeRrMetrics:
    """전략별 TE(예지치)/RR(손익비) 지표를 계산한다 (F-B1~F-B9).

    모집단: `status=='closed'` ∧ `sell_date`(청산일) >= now−window_days (경계 inclusive).
    open(미실현) 페어는 제외. 부분체결은 get_trade_pairs 가 왕복 1건으로 접은 전제.
    """
    cutoff = (now - timedelta(days=window_days)).date()

    population: list[dict] = []
    for p in pairs:
        if p.get("status") != "closed":
            continue
        sell_date_raw = p.get("sell_date")
        if not sell_date_raw:
            continue
        try:
            sell_date = date.fromisoformat(str(sell_date_raw))
        except (TypeError, ValueError):
            continue
        if sell_date < cutoff:
            continue
        population.append(p)

    if not population:
        return _empty_metrics(strategy_id)

    n = len(population)
    wins: list[dict] = []
    losses: list[dict] = []
    even_count = 0

    for p in population:
        rate = float(p.get("profit_rate") or 0.0)
        if rate > 0:
            wins.append(p)
        elif rate < 0:
            losses.append(p)
        else:
            even_count += 1

    win = len(wins)
    loss = len(losses)
    even = even_count

    profit_rates = [float(p.get("profit_rate") or 0.0) for p in population]
    profit_losses = [float(p.get("profit_loss") or 0.0) for p in population]

    win_rate = win / n
    te_pct = sum(profit_rates) / n
    te_krw_avg = sum(profit_losses) / n
    realized_sum_krw = sum(profit_losses)

    avg_win_pct = (
        sum(float(p.get("profit_rate") or 0.0) for p in wins) / win if win > 0 else None
    )
    avg_loss_pct = (
        sum(float(p.get("profit_rate") or 0.0) for p in losses) / loss if loss > 0 else None
    )

    required_rr = (loss / win) if win > 0 else None

    rr_available = min(win, loss) >= 5 and bool(avg_loss_pct)
    rr: float | None = None
    if rr_available and avg_win_pct is not None and avg_loss_pct:
        rr = avg_win_pct / abs(avg_loss_pct)

    rr_margin = (rr - required_rr) if (rr is not None and required_rr is not None) else None

    win_profit_losses = [float(p.get("profit_loss") or 0.0) for p in wins]
    total_win_krw = sum(win_profit_losses)
    single_trade_dominant = (
        bool(win_profit_losses)
        and total_win_krw > 0
        and max(win_profit_losses) > total_win_krw * 0.5
    )

    sample_tier = _sample_tier(n)

    if n < 20:
        verdict = "undecided"
    elif te_pct > 0:
        verdict = "superior"
    elif te_pct < 0:
        verdict = "inferior"
    else:
        verdict = "flat"

    structure_tag: str | None = None
    if n >= 20 and rr_available and rr is not None:
        if win_rate < 0.5 and rr >= 1.0:
            structure_tag = "robust"
        elif win_rate >= 0.5 and rr < 1.0:
            structure_tag = "fragile"
        else:
            structure_tag = "balanced"

    return TeRrMetrics(
        strategy_id=strategy_id,
        n=n,
        win=win,
        loss=loss,
        even=even,
        win_rate=win_rate,
        avg_win_pct=avg_win_pct,
        avg_loss_pct=avg_loss_pct,
        te_pct=te_pct,
        te_krw_avg=te_krw_avg,
        realized_sum_krw=realized_sum_krw,
        rr=rr,
        required_rr=required_rr,
        rr_margin=rr_margin,
        rr_available=rr_available,
        sample_tier=sample_tier,
        verdict=verdict,
        structure_tag=structure_tag,
        single_trade_dominant=single_trade_dominant,
    )
