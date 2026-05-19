"""임박(near-signal) 후보 모니터 (사이클 15-B-1, 2026-05-19).

REST 폴링 worker — 5 전략의 매수 후보군 중 "돌파 직전" 종목을 식별해
`StreamPoolManager.mark_promoted` 요청. 실제 WS 풀 subscribe 는 호출자(scheduler) 위임.

임박 기준 (사용자 설계서 제5장):
- **momentum**: `change_rate >= 28.5%` (실제 매수는 +29% 돌파 — 0.5% 이내)
- **volatility_breakout**: `distance_pct = (target - current) / target <= 0.3%`
  (보드별 K값 분리 — `get_targets_status()` 의 top-level target_price 사용)
- **long_tail_volatility**: VB 동일 + `prdy_rate >= min_prdy_rate`
- **donchian_swing**: 시간 임박 (09:05~09:30) AND `_candidates` 포함
- **bull_flag_breakout**: `distance_pct <= 0.4%` (`flag_high` 기준, 09:05~13:00)
- **vcp_breakout**: `distance_pct <= 0.4%` (`base_high` 기준, 09:05~14:30)

본 모듈은 단독 사용 가능 (scheduler 통합 X 단계). 사이클 15-B-2 에서 통합.
"""
from __future__ import annotations

import logging
from datetime import datetime, time as dtime, timezone, timedelta
from typing import Any, Optional

from src.engine.stream_pool_manager import StreamPoolManager

logger = logging.getLogger(__name__)

KST_TZ = timezone(timedelta(hours=9))

# 임박 임계 (설계서 제5장)
THRESHOLD_DISTANCE_PCT = {
    "volatility_breakout": 0.3,
    "long_tail_volatility": 0.3,
    "bull_flag_breakout": 0.4,
    "vcp_breakout": 0.4,
}
THRESHOLD_MOMENTUM_CHANGE_PCT = 28.5  # change_rate >= 28.5% 임박

# 시간 가드 (KRX 메인 시간대 기준)
DONCHIAN_WINDOW = (dtime(9, 5), dtime(9, 30))
BFB_WINDOW = (dtime(9, 5), dtime(13, 0))
VCP_WINDOW = (dtime(9, 5), dtime(14, 30))


def _now_kst() -> datetime:
    return datetime.now(KST_TZ)


def _in_window(now: datetime, window: tuple[dtime, dtime]) -> bool:
    start, end = window
    return start <= now.time() <= end


def calc_distance_pct(target_price: float, current_price: float) -> float:
    """`distance_pct = (target - current) / target * 100`.

    음수면 이미 돌파. 양수면 미돌파 (target 까지 거리).
    """
    if target_price <= 0:
        return float("inf")
    return (target_price - current_price) / target_price * 100.0


def extract_target_price(strategy_id: str, info: dict[str, Any]) -> float:
    """전략별 `get_targets_status()` 응답에서 target_price 추출.

    - VB/LTV: `info["boards"]["main"]["target_price"]` 우선, fallback `info["target_price"]`
    - BFB: `info["flag_high"]`
    - VCP: `info["target_price"]` (base_high)
    - donchian: `info["target_price"]` (donchian_high)
    """
    if strategy_id in ("volatility_breakout", "long_tail_volatility"):
        # 보드별 분리 — 우선 활성 보드(main) 의 target
        boards = info.get("boards") or {}
        main_board = boards.get("main") or {}
        tp = main_board.get("target_price")
        if tp and tp > 0:
            return float(tp)
        # fallback: top-level (활성 보드 미확정 등)
        return float(info.get("target_price") or 0)
    if strategy_id == "bull_flag_breakout":
        return float(info.get("flag_high") or info.get("target_price") or 0)
    # donchian / vcp / others
    return float(info.get("target_price") or 0)


async def fetch_current_price(ticker: str) -> int:
    """KIS REST 시세 호출 — 사이클 15-B-1 은 단독 모듈이라 lazy import."""
    try:
        from src.api.condition import fetch_stock_detail
        detail = await fetch_stock_detail(ticker)
        if detail is None:
            return 0
        return int(detail.get("stck_prpr") or 0)
    except Exception:
        logger.debug("[near_signal] fetch_current_price 실패: %s", ticker, exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# 전략별 임박 판단 (호출자가 strategy 인스턴스 + state 주입)
# ---------------------------------------------------------------------------


async def check_breakout_strategy(
    strategy_id: str,
    targets_status: dict[str, dict],
    *,
    threshold_pct: float,
    time_window: Optional[tuple[dtime, dtime]] = None,
    now: Optional[datetime] = None,
) -> list[tuple[str, str]]:
    """VB/LTV/BFB/VCP 4종 임박 판단.

    각 타겟 종목의 current_price 를 REST 로 fetch + distance_pct 계산.
    임박 만족 → `(ticker, reason)` list 반환. 호출자가 pool_manager.mark_promoted 호출.

    `time_window` 가 주어지면 KST 현재 시각이 그 범위 안일 때만 평가.
    """
    if now is None:
        now = _now_kst()
    if time_window is not None and not _in_window(now, time_window):
        return []

    candidates: list[tuple[str, str]] = []
    for ticker, info in targets_status.items():
        if not isinstance(info, dict):
            continue
        target = extract_target_price(strategy_id, info)
        if target <= 0:
            continue
        current = await fetch_current_price(ticker)
        if current <= 0:
            continue
        distance = calc_distance_pct(target, current)
        # 음수 (이미 돌파) — 임박 아닌 즉시 매수 후보. 호출자가 별도 처리.
        # 양수 + threshold 이내 → 임박
        if 0 <= distance <= threshold_pct:
            reason = f"distance_pct={distance:.2f}% (target={target:.0f}, current={current})"
            candidates.append((ticker, reason))
    return candidates


async def check_momentum_strategy(
    candidate_tickers: list[str],
    *,
    threshold_change_pct: float = THRESHOLD_MOMENTUM_CHANGE_PCT,
) -> list[tuple[str, str]]:
    """momentum 전략 임박 판단 — change_rate >= 28.5%.

    candidate_tickers: scan_stocks() 또는 모멘텀 후보 합집합.
    각 종목 fetch_stock_detail → `prdy_ctrt` (전일대비율) 추출.
    """
    candidates: list[tuple[str, str]] = []
    from src.api.condition import fetch_stock_detail

    for ticker in candidate_tickers:
        try:
            detail = await fetch_stock_detail(ticker)
        except Exception:
            continue
        if detail is None:
            continue
        try:
            change_rate = float(detail.get("prdy_ctrt") or 0.0)
        except (ValueError, TypeError):
            continue
        if change_rate >= threshold_change_pct:
            reason = f"change_rate={change_rate:.2f}% (>= {threshold_change_pct}%)"
            candidates.append((ticker, reason))
    return candidates


def check_donchian_strategy(
    scanned_tickers: list[str],
    *,
    now: Optional[datetime] = None,
) -> list[tuple[str, str]]:
    """donchian_swing 임박 판단 — 시간 기반 (09:05~09:30 KST AND _candidates 포함).

    가격 임박 X — donchian 은 prepare() 아침 1회 고정이라 _candidates 자체가 임박 신호.
    `_swing_buy_poll_loop` 가 별도 REST 폴링 매수 평가 (기존). 본 함수는 WS 승격 의도만.
    """
    if now is None:
        now = _now_kst()
    if not _in_window(now, DONCHIAN_WINDOW):
        return []
    return [(t, "time_window+candidate") for t in scanned_tickers]


# ---------------------------------------------------------------------------
# 통합 worker — 5 전략 합산
# ---------------------------------------------------------------------------


async def collect_near_signals(
    registry,  # StrategyRegistry — duck typing
    *,
    momentum_candidate_tickers: Optional[list[str]] = None,
    now: Optional[datetime] = None,
) -> dict[str, list[tuple[str, str, str]]]:
    """전체 전략 임박 후보 수집 — `{strategy_id: [(ticker, reason, target_or_change), ...]}`.

    호출자는 결과로 `stream_pool_manager.mark_promoted` 일괄 호출.
    """
    if now is None:
        now = _now_kst()

    out: dict[str, list[tuple[str, str, str]]] = {}

    # VB / LTV / BFB / VCP — get_targets_status() 보유
    for sid, time_window in (
        ("volatility_breakout", None),  # 보드 가드는 get_targets_status() 내부에서 처리
        ("long_tail_volatility", None),
        ("bull_flag_breakout", BFB_WINDOW),
        ("vcp_breakout", VCP_WINDOW),
    ):
        try:
            strategy = registry.get(sid)
        except (AttributeError, KeyError):
            continue
        if strategy is None or not getattr(strategy.config, "enabled", False):
            continue
        try:
            targets = strategy.get_targets_status() or {}
        except Exception:
            logger.debug("[near_signal] %s get_targets_status 실패", sid, exc_info=True)
            continue
        threshold = THRESHOLD_DISTANCE_PCT.get(sid, 0.3)
        results = await check_breakout_strategy(
            sid, targets,
            threshold_pct=threshold,
            time_window=time_window,
            now=now,
        )
        if results:
            out[sid] = [(t, r, "near_breakout") for t, r in results]

    # momentum
    if momentum_candidate_tickers:
        results = await check_momentum_strategy(momentum_candidate_tickers)
        if results:
            out["momentum"] = [(t, r, "near_threshold") for t, r in results]

    # donchian — 시간 기반 (가격 polling X)
    try:
        donchian = registry.get("donchian_swing")
    except (AttributeError, KeyError):
        donchian = None
    if donchian is not None and getattr(donchian.config, "enabled", False):
        try:
            scanned = donchian.get_scanned_tickers() or []
        except Exception:
            scanned = []
        results = check_donchian_strategy(scanned, now=now)
        if results:
            out["donchian_swing"] = [(t, r, "time_window") for t, r in results]

    return out
