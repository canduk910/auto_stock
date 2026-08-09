"""사이클 149 (2026-06-16) — 종목별 장운영정보 (H0UNMKO0) state monitor.

VI 활성 / 거래정지 / 종목상태 이상 ticker 영역 추적 + stale 회피 hook 제공.

domain-expert 자문 산출물:
    `_workspace/domain_consult/cycle149_h0unmko0_per_ticker_subscription.md`

핵심 책임 (의제 5 자문 채택):
1. `_vi_active_tickers` — VI 활성 ticker set (정적/동적/시간외 통합)
2. `_halt_active_tickers` — 거래정지 + 종목상태 이상 ticker set
3. `_market_op_last_event` — ticker → 마지막 MarketOpEvent dict (진단 + UI 응답용)

사이클 88 G-REJECT-3 영구 영속 답습:
- 4 dict (`_subscriptions` / `_subscriptions_acked` / `_ticker_to_session` / `ticker_last_tick`)
- 사이클 135 `_subscribed_at` 추가 → 5 dict
- **사이클 149 추가 3 dict → 8 dict 분리 영속** (`_vi_active_tickers` + `_halt_active_tickers` + `_market_op_last_event`)
- 통합 단일 dict 영구 차단 (책임 분리 + AST 영구 가드)

매매 안전성 무영향 (사이클 38 명문화 영속):
- stale 회피 = stale 판정 *지연*만 (`check_and_resubscribe_stale` 의 `_is_within_grace` 패턴 답습)
- `risk.on_tick` / `order_engine` / `auth` 변경 0
- 메인 WebSocket 단일 (보조 세션 변경 0)
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from src.api.market_operation import MarketOpEvent
from src.engine.daily_emit_cap import DailyEmitCap

logger = logging.getLogger(__name__)


# 사이클 149 신규 3 dict (사이클 88 G-REJECT-3 영속 답습 = 통합 단일 dict 영구 차단)
_vi_active_tickers: set[str] = set()
_halt_active_tickers: set[str] = set()
_market_op_last_event: dict[str, MarketOpEvent] = {}

# 사이클 186 — 서킷브레이커 휴리스틱 상수 + 1회/일 cap
_CB_REASON_KEYWORDS = ("서킷", "매매거래중단", "circuit")
_CB_HALT_RATIO: float = 0.8
_CB_MIN_HALTED: int = 5
_cb_suspected_logged_today: DailyEmitCap = DailyEmitCap()


def record_market_op_event(event: MarketOpEvent) -> None:
    """H0UNMKO0 단일 이벤트 수신 시 state 갱신.

    의제 1 (자문 채택) — truthy 매핑:
    - VI/거래정지/종목상태 활성 → 해당 set add
    - 비활성 ("0"/""/None) → 해당 set discard
    VI/거래정지/종목상태 판정은 _is_code_active 인라인으로 처리 (is_event_blocking 미사용).
    """
    ticker = event.ticker
    if not ticker:
        return

    # 마지막 이벤트 보존 (UI 진단 + 디버깅용)
    _market_op_last_event[ticker] = event

    # VI 활성/해제 (정적 + 동적 + 시간외 통합)
    from src.api.market_operation import _is_code_active

    vi_active = _is_code_active(event.vi_cls_code) or _is_code_active(event.ovtm_vi_cls_code)
    if vi_active:
        if ticker not in _vi_active_tickers:
            _vi_active_tickers.add(ticker)
            logger.info(
                "[market_op_vi_active] ticker=%s vi_code=%s ovtm_vi_code=%s",
                ticker, event.vi_cls_code, event.ovtm_vi_cls_code,
            )
    else:
        if ticker in _vi_active_tickers:
            _vi_active_tickers.discard(ticker)
            logger.info("[market_op_vi_release] ticker=%s", ticker)

    # 거래정지 + 종목상태 이상 통합 (의제 5 자문)
    halt_active = (
        (event.trht_yn and event.trht_yn.upper() == "Y")
        or _is_code_active(event.iscd_stat_cls_code)
    )
    if halt_active:
        if ticker not in _halt_active_tickers:
            _halt_active_tickers.add(ticker)
            logger.info(
                "[market_op_halt_active] ticker=%s trht_yn=%s iscd_stat=%s reason=%s",
                ticker, event.trht_yn, event.iscd_stat_cls_code,
                event.tr_susp_reas_cntt[:50],
            )
    else:
        if ticker in _halt_active_tickers:
            _halt_active_tickers.discard(ticker)
            logger.info("[market_op_halt_release] ticker=%s", ticker)

    # 사이클 186 — 서킷브레이커 휴리스틱 체크 + 1회/일 cap 로그
    cb_state = get_circuit_breaker_state()
    if cb_state["suspected"] and _cb_suspected_logged_today.should_emit("cb"):
        _cb_suspected_logged_today.mark_emitted("cb")
        logger.info(
            "[market_op_cb_suspected] mkop_code=%s halted=%d/%d reason=%s",
            cb_state["representative_mkop_cls_code"],
            cb_state["halted"],
            cb_state["observed"],
            cb_state["reasons"],
        )


def is_ticker_stale_excluded(ticker: str) -> bool:
    """stale 판정 회피 hook (`check_and_resubscribe_stale` 영역).

    VI 활성 ∪ 거래정지 활성 ticker = stale 판정 *지연* 의무.
    True 반환 시 stale 종목 set 에서 제외 → 강제 재구독 발화 차단.
    """
    return ticker in _vi_active_tickers or ticker in _halt_active_tickers


def get_market_op_active_tickers() -> set[str]:
    """VI ∪ 거래정지 합집합 (외부 호출자용 read-only view).

    `_subscribe_market_operation_tickers` 영역 delta 계산 + UI 진단 응답.
    """
    return _vi_active_tickers | _halt_active_tickers


def get_vi_active_tickers() -> set[str]:
    """VI 활성 ticker set 복사본 (read-only view)."""
    return set(_vi_active_tickers)


def get_halt_active_tickers() -> set[str]:
    """거래정지 활성 ticker set 복사본 (read-only view)."""
    return set(_halt_active_tickers)


def get_last_event(ticker: str) -> Optional[MarketOpEvent]:
    """ticker 마지막 이벤트 (UI 진단 + 디버깅용)."""
    return _market_op_last_event.get(ticker)


def seed_vi_active_from_rest(tickers: Iterable[str]) -> None:
    """의제 4 (자문 채택) — 부팅 시점 REST 폴백 시드.

    `inquire_vi_status_today()` 반환 set 으로 `_vi_active_tickers` 사전 등록.
    WebSocket 구독 시점 *이전* VI 활성 종목 stale 회피 보장.
    """
    for ticker in tickers:
        if ticker:
            _vi_active_tickers.add(ticker)
    if tickers:
        logger.info(
            "[market_op_vi_seed] count=%d sample=%s",
            len(_vi_active_tickers),
            sorted(_vi_active_tickers)[:5],
        )


def reset_market_op_state() -> None:
    """일일 상태 초기화 (`_reset_daily_state` 동행 clear).

    사이클 88 G-REJECT 영속 답습 = 모든 dict 일일 0 초기화 의무.
    """
    _vi_active_tickers.clear()
    _halt_active_tickers.clear()
    _market_op_last_event.clear()
    _cb_suspected_logged_today.reset_daily()  # 사이클 186


def get_circuit_breaker_state() -> dict:
    """서킷브레이커 휴리스틱 state snapshot (사이클 186).

    (R) 거래정지 종목의 tr_susp_reas_cntt 에 키워드 포함 OR
    (W) 거래정지 비율 ≥ _CB_HALT_RATIO + 절대 수 ≥ _CB_MIN_HALTED.
    """
    halted = len(_halt_active_tickers)
    observed = len(_market_op_last_event)
    halt_ratio = halted / max(1, observed)

    # (R) keyword path
    keyword_match = False
    for ticker in _halt_active_tickers:
        event = _market_op_last_event.get(ticker)
        if event and event.tr_susp_reas_cntt:
            for kw in _CB_REASON_KEYWORDS:
                if kw in event.tr_susp_reas_cntt:
                    keyword_match = True
                    break
        if keyword_match:
            break

    # (W) ratio path
    ratio_triggered = halted >= _CB_MIN_HALTED and halt_ratio >= _CB_HALT_RATIO

    suspected = keyword_match or ratio_triggered

    reasons: list[str] = []
    if keyword_match:
        reasons.append("거래정지 사유 키워드 포함 (서킷/매매거래중단)")
    if ratio_triggered:
        reasons.append(
            f"전 시장 거래정지 {halted}/{observed} ({int(halt_ratio * 100)}%)"
        )

    # representative: 005930 last event
    rep_event = _market_op_last_event.get("005930")
    representative_mkop_cls_code = rep_event.mkop_cls_code if rep_event else ""

    # halt_reasons_sample: distinct non-empty tr_susp_reas_cntt (최대 5)
    seen: set[str] = set()
    sample: list[str] = []
    for ticker in _halt_active_tickers:
        event = _market_op_last_event.get(ticker)
        if event and event.tr_susp_reas_cntt:
            reason = event.tr_susp_reas_cntt
            if reason not in seen:
                seen.add(reason)
                sample.append(reason)
                if len(sample) >= 5:
                    break

    return {
        "suspected": suspected,
        "reasons": reasons,
        "halt_ratio": halt_ratio,
        "halted": halted,
        "observed": observed,
        "representative_mkop_cls_code": representative_mkop_cls_code,
        "halt_reasons_sample": sample,
    }


def get_market_op_state_summary() -> dict:
    """진단/UI 응답용 state snapshot (사이클 186 확장 = circuit_breaker + iscd_stat_active_count)."""
    from src.api.market_operation import _is_code_active

    iscd_stat_active_count = sum(
        1 for event in _market_op_last_event.values()
        if _is_code_active(event.iscd_stat_cls_code)
    )
    return {
        "vi_active_count": len(_vi_active_tickers),
        "halt_active_count": len(_halt_active_tickers),
        "last_event_count": len(_market_op_last_event),
        "vi_active_sample": sorted(_vi_active_tickers)[:10],
        "halt_active_sample": sorted(_halt_active_tickers)[:10],
        "circuit_breaker": get_circuit_breaker_state(),
        "iscd_stat_active_count": iscd_stat_active_count,
    }
