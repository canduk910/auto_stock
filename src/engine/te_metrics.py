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
    # cycle411 — 사용자 결정 10-08 Q2: 판정(win/loss·te_pct·te_krw_avg·rr·verdict, 위 필드들)은
    # 순손익(net) 기준이 기본. 세전 값은 `*_gross` 로 남긴다(판정이 바뀐 이유를 비교하는 용도).
    te_pct_gross: float = 0.0
    te_krw_avg_gross: float = 0.0
    win_rate_gross: float = 0.0
    rr_gross: float | None = None
    verdict_gross: str = "undecided"
    # realized_sum_krw(위)는 기존 의미(세전) 그대로 — net 합·수수료·세금 합은 별도 칸.
    realized_net_sum_krw: float = 0.0
    fee_sum: float = 0.0
    tax_sum: float = 0.0
    # cycle411 보완 M5 — 세전 승/패 수(세전 화면의 승률·승/패 표시용). 빈 모집단 = 0.
    win_gross: int = 0
    loss_gross: int = 0


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


def _net_rate(p: dict) -> float:
    v = p.get("net_profit_rate")
    return float(v) if v is not None else float(p.get("profit_rate") or 0.0)


def _net_pl(p: dict) -> float:
    v = p.get("net_profit_loss")
    return float(v) if v is not None else float(p.get("profit_loss") or 0.0)


def _gross_rate(p: dict) -> float:
    return float(p.get("profit_rate") or 0.0)


def _gross_pl(p: dict) -> float:
    return float(p.get("profit_loss") or 0.0)


def _core(population: list[dict], rate_fn, pl_fn) -> dict:
    """win/loss 판정·TE·RR·verdict — `rate_fn`/`pl_fn` 이 가리키는 값 기준(net 또는 gross, cycle411)."""
    n = len(population)
    wins: list[dict] = []
    losses: list[dict] = []
    even_count = 0
    for p in population:
        rate = rate_fn(p)
        if rate > 0:
            wins.append(p)
        elif rate < 0:
            losses.append(p)
        else:
            even_count += 1

    win = len(wins)
    loss = len(losses)

    rates = [rate_fn(p) for p in population]
    pls = [pl_fn(p) for p in population]

    win_rate = win / n if n else 0.0
    te_pct = sum(rates) / n if n else 0.0
    te_krw_avg = sum(pls) / n if n else 0.0

    avg_win_pct = sum(rate_fn(p) for p in wins) / win if win > 0 else None
    avg_loss_pct = sum(rate_fn(p) for p in losses) / loss if loss > 0 else None

    required_rr = (loss / win) if win > 0 else None

    rr_available = min(win, loss) >= 5 and bool(avg_loss_pct)
    rr: float | None = None
    if rr_available and avg_win_pct is not None and avg_loss_pct:
        rr = avg_win_pct / abs(avg_loss_pct)

    rr_margin = (rr - required_rr) if (rr is not None and required_rr is not None) else None

    win_pls = [pl_fn(p) for p in wins]
    total_win_krw = sum(win_pls)
    single_trade_dominant = (
        bool(win_pls) and total_win_krw > 0 and max(win_pls) > total_win_krw * 0.5
    )

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

    return {
        "n": n, "win": win, "loss": loss, "even": even_count, "win_rate": win_rate,
        "avg_win_pct": avg_win_pct, "avg_loss_pct": avg_loss_pct, "te_pct": te_pct,
        "te_krw_avg": te_krw_avg, "rr": rr, "required_rr": required_rr,
        "rr_margin": rr_margin, "rr_available": rr_available, "verdict": verdict,
        "structure_tag": structure_tag, "single_trade_dominant": single_trade_dominant,
    }


def compute_te_rr(
    pairs: list[dict],
    *,
    now: datetime,
    window_days: int = 90,
    strategy_id: str = "",
) -> TeRrMetrics:
    """전략별 TE(예지치)/RR(손익비) 지표를 계산한다 (F-B1~F-B9, cycle411 — net 판정 + gross 병기).

    모집단: `status=='closed'` ∧ `sell_date`(청산일) >= now−window_days (경계 inclusive).
    open(미실현) 페어는 제외. 부분체결은 get_trade_pairs 가 왕복 1건으로 접은 전제.

    사용자 결정 10-08 Q2 — 판정(win/loss·te_pct·te_krw_avg·rr·verdict)은 페어의
    `net_profit_rate`/`net_profit_loss`(순손익, 비용 차감)가 있으면 그 값 기준이고, 없는
    페어(구 입력)는 세전 값으로 폴백한다(`test_cycleF_te_rr_metrics.py` 무수정 통과). 세전
    값은 항상 `*_gross` 로 별도 남는다.
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

    net_core = _core(population, _net_rate, _net_pl)
    gross_core = _core(population, _gross_rate, _gross_pl)

    realized_sum_krw = sum(_gross_pl(p) for p in population)
    realized_net_sum_krw = sum(_net_pl(p) for p in population)
    fee_sum = sum(float(p.get("fee") or 0.0) for p in population)
    tax_sum = sum(float(p.get("tax") or 0.0) for p in population)

    sample_tier = _sample_tier(net_core["n"])

    return TeRrMetrics(
        strategy_id=strategy_id,
        n=net_core["n"],
        win=net_core["win"],
        loss=net_core["loss"],
        even=net_core["even"],
        win_rate=net_core["win_rate"],
        avg_win_pct=net_core["avg_win_pct"],
        avg_loss_pct=net_core["avg_loss_pct"],
        te_pct=net_core["te_pct"],
        te_krw_avg=net_core["te_krw_avg"],
        realized_sum_krw=realized_sum_krw,
        rr=net_core["rr"],
        required_rr=net_core["required_rr"],
        rr_margin=net_core["rr_margin"],
        rr_available=net_core["rr_available"],
        sample_tier=sample_tier,
        verdict=net_core["verdict"],
        structure_tag=net_core["structure_tag"],
        single_trade_dominant=net_core["single_trade_dominant"],
        te_pct_gross=gross_core["te_pct"],
        te_krw_avg_gross=gross_core["te_krw_avg"],
        win_rate_gross=gross_core["win_rate"],
        rr_gross=gross_core["rr"],
        verdict_gross=gross_core["verdict"],
        realized_net_sum_krw=realized_net_sum_krw,
        fee_sum=fee_sum,
        tax_sum=tax_sum,
        win_gross=gross_core["win"],
        loss_gross=gross_core["loss"],
    )
