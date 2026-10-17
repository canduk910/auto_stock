"""21:30 정산 외부입출금 추정 leaf (cycle469 — 사용자 결정 2026-10-16).

사용자 원문: 「21:30 정산 외부입출금은 D+2 기준보다 늘어날 때만 인지.
현재 예수금 + 전일/당일 매도대금 - 전일/당일 매수대금」.

KIS 예수금(`dnca_tot_amt`)은 결제된 돈(D+0)이라, 매매대금은 이틀 뒤에야 들어오고 나간다.
옛 식 `Δ예수금 − 당일 매매대금` 은 그 시차 때문에 D-2 체결의 결제분을 매일 외부입출금으로 셌다.

  기준(X)  = X 의 예수금 + 매매대금(X) + 매매대금(X 의 직전 영업일)      매매대금 = 매도 − 매수
  raw      = 기준(오늘) − 기준(직전 정산일) − Σ 매매대금(직전 정산일 뒤 ~ 오늘)
  인지     = raw ≥ INFLOW_MIN_WON 이면 raw, 아니면 0

- 줄어드는 쪽은 인지하지 않는다(사용자 결정) — 수수료·세금이 늘 음의 잔차를 만든다.
- 양의 작은 잔차(체결가 원 단위 절사 등)는 `INFLOW_MIN_WON` 아래면 버린다.
- 매매대금 = `trade_history` COMPLETED·PARTIAL 의 가격 × 수량(정산이 쓰던 출처 그대로).
- 기록 전용 — `daily_performance.net_external_cashflow` 는 TWR·수익률 계산에 쓰이지 않는다.
- never-raise. 달력·조회 실패 = 0 + 사유.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger(__name__)

#: 이보다 작은 양의 잔차는 입금으로 보지 않는다.
INFLOW_MIN_WON = 10_000
_SETTLED_STATUSES = frozenset({"COMPLETED", "PARTIAL"})


@dataclass(frozen=True)
class InflowEstimate:
    recognized: float
    raw: float | None
    reason: str
    basis_today: float | None = None
    basis_prev: float | None = None
    trade_flow_between: float | None = None


async def _get_trades_in_range(start: date, end: date) -> list[dict]:
    from src.db.trade_history import get_trades_in_range
    return await get_trades_in_range(start, end)


async def _previous_trading_day(d: date) -> date | None:
    from src.engine.trading_calendar import previous_trading_day
    return await previous_trading_day(d)


def _as_date(v) -> date | None:
    """`_kst.to_date` 위임 — datetime·KST ISO 문자열·date 를 KST 날짜로(실패 = None)."""
    from src.db._kst import to_date
    return to_date(v)


def _flows_by_day(rows: list[dict]) -> dict[date, float]:
    out: dict[date, float] = {}
    for t in rows:
        if t.get("status") not in _SETTLED_STATUSES:
            continue
        d = _as_date(t.get("timestamp"))
        if d is None:
            continue
        amt = float(t.get("price") or 0) * int(t.get("quantity") or 0)
        side = t.get("trade_type")
        if side == "SELL":
            out[d] = out.get(d, 0.0) + amt
        elif side == "BUY":
            out[d] = out.get(d, 0.0) - amt
    return out


def _emit(est: InflowEstimate, prev_date) -> InflowEstimate:
    fmt = (
        "[settle_ext_cashflow] recognized=%.0f raw=%s reason=%s basis_today=%s "
        "basis_prev=%s trade_flow_between=%s prev_date=%s"
    )
    args = (
        est.recognized,
        "-" if est.raw is None else f"{est.raw:.0f}",
        est.reason,
        "-" if est.basis_today is None else f"{est.basis_today:.0f}",
        "-" if est.basis_prev is None else f"{est.basis_prev:.0f}",
        "-" if est.trade_flow_between is None else f"{est.trade_flow_between:.0f}",
        prev_date or "-",
    )
    (logger.info if est.reason in ("ok", "no_prev_row") else logger.warning)(fmt, *args)
    return est


async def estimate_external_inflow(*, today: date, deposit: float, prev_row: dict | None) -> InflowEstimate:
    """오늘 정산의 외부 입금 추정. never-raise."""
    prev_date = None
    try:
        if not prev_row:
            return _emit(InflowEstimate(0.0, None, "no_prev_row"), None)
        prev_date = _as_date(prev_row.get("date"))
        prev_deposit = float(prev_row.get("deposit") or 0)
        if prev_date is None or prev_date >= today:
            return _emit(InflowEstimate(0.0, None, "prev_row_not_before_today"), prev_date)

        d1 = await _previous_trading_day(today)
        p1 = await _previous_trading_day(prev_date)
        if d1 is None or p1 is None:
            return _emit(InflowEstimate(0.0, None, "calendar_unknown"), prev_date)

        try:
            rows = await _get_trades_in_range(min(d1, p1), today)
        except Exception:
            logger.debug("[settle_ext_cashflow] 거래 조회 실패", exc_info=True)
            return _emit(InflowEstimate(0.0, None, "lookup_failed"), prev_date)

        flows = _flows_by_day(rows)
        f = lambda d: flows.get(d, 0.0)  # noqa: E731
        basis_today = float(deposit) + f(today) + f(d1)
        basis_prev = prev_deposit + f(prev_date) + f(p1)
        between = sum(v for d, v in flows.items() if prev_date < d <= today)
        raw = basis_today - basis_prev - between
        recognized = raw if raw >= INFLOW_MIN_WON else 0.0
        return _emit(InflowEstimate(recognized, raw, "ok", basis_today, basis_prev, between), prev_date)
    except Exception:
        logger.debug("[settle_ext_cashflow] 추정 실패", exc_info=True)
        return _emit(InflowEstimate(0.0, None, "error"), prev_date)
