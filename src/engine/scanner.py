"""종목 필터링 모듈.

등락률 순위 API 결과에서 당일 급등 종목(15%+ 상승)을 필터링하고,
시총/거래대금 조건을 추가 적용한 뒤 WebSocket 실시간 시세 구독을 등록한다.

매수 조건이 시가 대비 +29.5%이므로, 이미 15% 이상 상승 중인 종목을
후보군으로 잡아 29.5% 도달을 감시한다.
"""

from __future__ import annotations

import asyncio
import asyncio as _asyncio  # 사이클 101 — Rate Limit sleep patch 호환 (asyncio.sleep 직접 patch 지원)
import logging
import sys as _sys
import time as _monotonic_time
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from src.api.condition import MIN_CHANGE_RATE, fetch_rising_stocks
from src.db.system_config import get_price_filter, get_trade_amount_filter
from src.engine.daily_emit_cap import DailyEmitCap
from src.realtime.websocket import kis_ws
from src.realtime.websocket_pool import kis_ws_pool

if TYPE_CHECKING:
    from src.db.system_config import PriceFilter, TradeAmountFilter

logger = logging.getLogger(__name__)

# KST 타임존 (ticker_last_tick 갱신용 — 프로젝트 컨벤션상 각 모듈 로컬 정의)
KST_TZ = timezone(timedelta(hours=9))

# ---------------------------------------------------------------------------
# 사이클 64 (2026-06-06) — 가격 필터 (scanner 단계, Q4 옵션 A 단일 hook)
# ---------------------------------------------------------------------------
# 적용 위치: subscribe_filtered_stocks 진입 직전 (risk.on_tick 이전).
# Q1 옵션 D 3중 안전망: (1) 공통 헬퍼 (2) early-return (3) protected_tickers keyword 의무.
# Q7-1 자문: invalidate_price_filter_cache_scanner 는 unsubscribe 발화 0건 (캐시만 무효화).
#   → 다음 _scan_loop 5분 자연 delta 위임 (KIS LMS chain 차단, 사이클 17 OPSP0002 답습).

_price_filter_cache: "PriceFilter | None" = None
_price_filter_cache_expires_at: float = 0.0
PRICE_FILTER_CACHE_TTL: float = 60.0  # 사이클 56-E BUY_BLOCK_CACHE_TTL 답습

# DailyEmitCap — 1회/ticker/일 skip 로그 cap (매 스캔 폭주 차단)
_price_filter_scanner_skip_logged_today: DailyEmitCap[str] = DailyEmitCap()

# 일일 집계 카운터 (H 카테고리 — _settle() 직전 emit)
_price_filter_scanner_skip_count_today: dict[str, int] = {
    "total": 0, "below_min": 0, "above_max": 0,
}


def _collect_protected_tickers_for_scanner() -> set[str]:
    """Q1 옵션 D 공통 헬퍼 — 보유/익일청산 종목 집합 (early-return 대상).

    사이클 32 R4 universe guard 패턴 답습 (lazy import + try/except graceful).
    scheduler 미초기화 / 단위 테스트 환경 모두 안전.

    registry 접근: 모듈 네임스페이스에 `registry` 속성이 있으면 (tests monkeypatch) 그것을
    우선 사용, 없으면 sys.modules 경유 lazy 접근 (circular import 회피).
    """
    protected: set[str] = set()
    # 1) 보유 종목 (전 전략 합집합)
    try:
        # tests 에서 monkeypatch.setattr("src.engine.scanner.registry", ...) 로 주입 가능
        import sys as _sys_local
        _scanner_self = _sys_local.modules.get(__name__)
        _reg = getattr(_scanner_self, "registry", None)
        if _reg is None:
            # 운영 환경: scheduler 의 registry 인스턴스 경유
            _sched_mod2 = _sys_local.modules.get("src.engine.scheduler")
            if _sched_mod2 is not None:
                ts2 = getattr(_sched_mod2, "trading_scheduler", None)
                if ts2 is not None:
                    _reg = getattr(ts2, "registry", None)
        if _reg is not None:
            for s in _reg.all():
                protected |= set(s.state.positions.keys())
    except Exception:
        logger.debug("[protected_tickers] registry 조회 실패 graceful", exc_info=True)
    # 2) 익일청산 종목
    try:
        _sched = _sys.modules.get("src.engine.scheduler")
        if _sched is not None:
            ts = getattr(_sched, "trading_scheduler", None)
            if ts is not None:
                pending = getattr(ts, "_pending_next_day_clear", None)
                if pending:
                    for item in pending:
                        if isinstance(item, tuple) and item:
                            protected.add(item[0])
                        elif isinstance(item, str):
                            protected.add(item)
    except Exception:
        logger.debug("[protected_tickers] scheduler 조회 실패 graceful", exc_info=True)
    return protected


async def _get_price_filter_for_scanner() -> "PriceFilter":
    """60s TTL 캐시 (사이클 56-E BUY_BLOCK_CACHE_TTL 답습, time.monotonic)."""
    global _price_filter_cache, _price_filter_cache_expires_at
    now = _monotonic_time.monotonic()
    if _price_filter_cache is not None and now < _price_filter_cache_expires_at:
        return _price_filter_cache
    pf = await get_price_filter()
    _price_filter_cache = pf
    _price_filter_cache_expires_at = now + PRICE_FILTER_CACHE_TTL
    return pf


def invalidate_price_filter_cache_scanner() -> None:
    """즉시 무효화 — 캐시 + DailyEmitCap reset. unsubscribe 발화 0건 의무 (Q7-1).

    다음 _scan_loop 5분 자연 delta 로 차단 종목 자연 unsubscribe.
    KIS LMS chain 차단 (사이클 17 OPSP0002 답습).

    사이클 83 (2026-06-09): DailyEmitCap 동행 clear — 가격 필터 재평가 시
    이전 캡 상태 오염 차단 (테스트 격리 + 운영 PUT 직후 재평가 정확성 보장).
    """
    global _price_filter_cache, _price_filter_cache_expires_at
    _price_filter_cache = None
    _price_filter_cache_expires_at = 0.0
    _price_filter_scanner_skip_logged_today.clear()
    # ★ kis_ws_pool.unsubscribe 호출 0건 의무 (D-2 가드)


def reset_price_filter_daily_state() -> None:
    """매일 자정 reset — scheduler._reset_daily_state 가 호출 의무 (사이클 32 universe guard 패턴 답습)."""
    _price_filter_scanner_skip_logged_today.clear()
    for k in _price_filter_scanner_skip_count_today:
        _price_filter_scanner_skip_count_today[k] = 0


async def _apply_price_filter(
    candidates: list[str],
    *,
    protected_tickers: set[str],  # keyword-only 강제 (Q1 옵션 D + G-2 AST 가드)
) -> list[str]:
    """가격 필터 적용 — 후보 풀에서 임계 외 종목 제거.

    Q1 옵션 D 3중 안전망:
    (1) _collect_protected_tickers_for_scanner 공통 헬퍼 (호출자 제공)
    (2) 최상단 early-return — 보유/익일청산 절대 보호
    (3) protected_tickers= keyword 의무 (G-2 AST 가드)
    Q2: prdy_clpr 미확보 시 graceful 통과 (KIS pre-fetch 비채택).
    Q7-1: invalidate 시 unsubscribe 0건 — 5분 자연 delta 위임.
    """
    # 직접 조회 — tests 에서 `patch("src.engine.scanner.get_price_filter", ...)` 로 교체 가능
    # (TTL 캐시 bypass: subscribe_filtered_stocks 는 _get_price_filter_for_scanner 로 별도 최적화)
    pf = await get_price_filter()
    if not pf.is_active:
        return candidates  # 비활성 → 전체 통과

    from src.db import stock_master as _sm_mod

    survivors: list[str] = []
    excluded: list[tuple[str, int, str]] = []  # (ticker, prdy_clpr, reason)

    for ticker in candidates:
        # ★ early-return — 보유/익일청산 절대 보호 (Q1 옵션 D 핵심)
        if ticker in protected_tickers:
            survivors.append(ticker)
            continue

        # bfdy_clpr 조회 — stock_master.raw.bfdy_clpr 단독 (Q2 옵션 A)
        # 사이클 81 시정 — CTPF1002R 정본 키 (사이클 64 prdy_clpr 명명 오류)
        prdy_clpr = 0
        try:
            basics = await _sm_mod.get(ticker)
            if basics and basics.raw:
                raw_val = basics.raw.get("bfdy_clpr", 0)
                if raw_val:
                    prdy_clpr = int(raw_val)
        except Exception:
            logger.debug("[price_filter_scanner] stock_master 조회 실패 graceful: %s", ticker, exc_info=True)

        if prdy_clpr <= 0:
            # 미확보 graceful 통과 (Q2 + Q3 — 신규 상장 영구 차단 방지)
            survivors.append(ticker)
            continue

        # 임계 평가
        below_min = pf.min_price > 0 and prdy_clpr < pf.min_price
        above_max = pf.max_price > 0 and prdy_clpr > pf.max_price
        if below_min or above_max:
            reason = "below_min" if below_min else "above_max"
            excluded.append((ticker, prdy_clpr, reason))
            # DailyEmitCap 1회/ticker/일 (매 스캔 폭주 차단)
            if ticker not in _price_filter_scanner_skip_logged_today:
                _price_filter_scanner_skip_logged_today.add(ticker)
                logger.info(
                    "[price_filter_scanner_skip] ticker=%s bfdy_clpr=%d "
                    "reason=%s min=%d max=%d",
                    ticker, prdy_clpr, reason, pf.min_price, pf.max_price,
                )
                try:
                    from src.db.system_logs import write_log
                    await write_log(
                        "INFO",
                        f"[price_filter_scanner_skip] ticker={ticker} "
                        f"bfdy_clpr={prdy_clpr} reason={reason} "
                        f"min={pf.min_price} max={pf.max_price}",
                    )
                except Exception:
                    logger.debug("[price_filter_scanner_skip] write_log 실패", exc_info=True)
            # 일일 집계 카운터
            _price_filter_scanner_skip_count_today["total"] += 1
            _price_filter_scanner_skip_count_today[reason] = (
                _price_filter_scanner_skip_count_today.get(reason, 0) + 1
            )
        else:
            survivors.append(ticker)

    # Q7-4 funnel step_no=98 hook (graceful — 실패 시 매수 흐름 영향 0)
    if excluded:
        try:
            from src.db.strategy_funnel import insert_snapshot
            today_kst = datetime.now(KST_TZ).date().isoformat()
            await insert_snapshot(
                target_date=today_kst,
                strategy_id="ALL",
                step_no=98,
                step_name="price_filter_scanner",
                survived_count=len(survivors),
                survived_tickers=[{"ticker": t} for t in survivors[:200]],
                excluded_count=len(excluded),
                excluded_sample=[
                    {"ticker": t, "bfdy_clpr": p, "reason": r}
                    for (t, p, r) in excluded[:20]
                ],
            )
        except Exception:
            logger.debug("[price_filter_scanner_funnel] hook 실패 graceful", exc_info=True)

    return survivors


async def emit_price_filter_scanner_daily_summary() -> None:
    """일일 집계 emit — scheduler._settle() 진입 직전 호출 (H-1, Q6 옵션 B scanner 이전).

    포함 필드: active / min / max / daily_skip / reasons.
    사이클 41 funnel 진단 패턴 답습.
    """
    try:
        pf = await _get_price_filter_for_scanner()
        total = _price_filter_scanner_skip_count_today.get("total", 0)
        below = _price_filter_scanner_skip_count_today.get("below_min", 0)
        above = _price_filter_scanner_skip_count_today.get("above_max", 0)
        msg = (
            f"[price_filter_scanner_daily_summary] "
            f"active={pf.is_active} min={pf.min_price} max={pf.max_price} "
            f"daily_skip={total} "
            f"reasons={{below_min: {below}, above_max: {above}}}"
        )
        logger.info(msg)
        try:
            from src.db.system_logs import write_log
            await write_log("INFO", msg)
        except Exception:
            logger.debug("[price_filter_scanner_daily_summary] write_log 실패", exc_info=True)
    except Exception:
        logger.debug("[price_filter_scanner_daily_summary] emit 실패", exc_info=True)

# ---------------------------------------------------------------------------
# 사이클 65 (2026-06-06) — 거래대금 필터 (scanner 단계, Q3 순차 hook)
# ---------------------------------------------------------------------------
# 적용 위치: subscribe_filtered_stocks 진입 직후 _apply_price_filter 다음 (Q3 순차).
# Q1 옵션 D 3중 안전망: (1) 공통 헬퍼 (2) early-return (3) protected_tickers keyword 의무.
# Q7-1: invalidate_trade_amount_filter_cache_scanner 는 unsubscribe 발화 0건 의무.
# Q6-1: acml_tr_pbmn=0 (09:00 직후 race) → graceful 통과 영속.

_trade_amount_filter_cache: "TradeAmountFilter | None" = None
_trade_amount_filter_cache_expires_at: float = 0.0
_TRADE_AMOUNT_FILTER_CACHE_TTL: float = 60.0  # 사이클 56-E 답습

# DailyEmitCap — 1회/ticker/일 skip 로그 cap (매 스캔 폭주 차단, 사이클 64 답습)
_trade_amount_filter_scanner_skip_logged_today: DailyEmitCap[str] = DailyEmitCap()

# 일일 집계 카운터 (H 카테고리 — _settle() 직전 emit)
_trade_amount_filter_scanner_skip_count_today: dict[str, int] = {"total": 0}


async def _get_trade_amount_filter_for_scanner() -> "TradeAmountFilter":
    """60s TTL 캐시 (사이클 56-E 답습, time.monotonic).

    Q4 별도 캐시: 사이클 64 가격 필터와 무효화 시점 다름 + 단일 책임 분리.
    """
    global _trade_amount_filter_cache, _trade_amount_filter_cache_expires_at
    now = _monotonic_time.monotonic()
    if _trade_amount_filter_cache is not None and now < _trade_amount_filter_cache_expires_at:
        return _trade_amount_filter_cache
    taf = await get_trade_amount_filter()
    _trade_amount_filter_cache = taf
    _trade_amount_filter_cache_expires_at = now + _TRADE_AMOUNT_FILTER_CACHE_TTL
    return taf


def invalidate_trade_amount_filter_cache_scanner() -> None:
    """즉시 무효화 — 캐시만, unsubscribe 발화 0건 의무 (Q7-1).

    Settings PUT 직후 즉시 반영. 다음 _scan_loop 5분 자연 delta 로 처리.
    KIS LMS chain 차단 (사이클 17 OPSP0002 + 사이클 64 D-2 답습).
    """
    global _trade_amount_filter_cache, _trade_amount_filter_cache_expires_at
    _trade_amount_filter_cache = None
    _trade_amount_filter_cache_expires_at = 0.0
    # ★ kis_ws_pool.unsubscribe 호출 0건 의무 (D-2 가드)


def reset_trade_amount_filter_daily_state() -> None:
    """매일 자정 reset — scheduler._reset_daily_state 가 호출 의무 (사이클 56-D 답습)."""
    _trade_amount_filter_scanner_skip_logged_today.clear()
    for k in _trade_amount_filter_scanner_skip_count_today:
        _trade_amount_filter_scanner_skip_count_today[k] = 0


async def _get_acml_tr_pbmn(ticker: str) -> int:
    """누적 거래대금 조회 — Q2 옵션 C 통합 폴백 (사이클 65, 2026-06-06).

    1순위: ticker_market_info["trade_amount_raw"] (scanner 가 이미 fetch_rising_stocks + acml_tr_pbmn 보강)
    2순위: stock_master.raw.acml_tr_pbmn (24h TTL 캐시 — CTPF1002R 응답)
    둘 다 miss: 0 반환 → _apply_trade_amount_filter 가 graceful 통과 처리

    단위: 원(₩) — scanner.py MIN_TRADE_AMOUNT 패턴 답습.
    Q6-1 09:00 race 영속: scanner 1순위 0 (장 시작 직후 누적 미반영) → graceful 통과 보장.
    사이클 81 시정 — 2순위 stock_master.raw.acml_tr_pbmn 폴백 폐기 (CTPF1002R 응답에 acml_tr_pbmn 키 없음).
    """
    # 1순위 단독: scanner.ticker_market_info["trade_amount_raw"] (사이클 65 등락률 15%+ 보강)
    # 사이클 81 시정 — 2순위 stock_master.raw.acml_tr_pbmn 폴백 폐기 (CTPF1002R 응답에 acml_tr_pbmn 키 없음).
    # 사이클 65 Q6-1 09:00 race graceful 영속 (miss = 0 반환).
    info = ticker_market_info.get(ticker, {})
    if isinstance(info, dict):
        raw = info.get("trade_amount_raw", 0)
        if isinstance(raw, (int, float)):
            raw_int = int(raw)
            if raw_int > 0:
                return raw_int

    # miss → 0 반환 (Q6-1 graceful 통과 위임)
    return 0


async def _apply_trade_amount_filter(
    candidates: list[str],
    *,
    protected_tickers: set[str],  # keyword-only 강제 (Q1 옵션 D + G-1 AST 가드)
) -> list[str]:
    """거래대금 필터 적용 — 후보 풀에서 임계 미만 종목 제거.

    사이클 65 (2026-06-06) — 작전주 차단 유일 메커니즘 (사이클 64 갭상승 폐기 보강).
    Q1 옵션 D 3중 안전망:
    (1) _collect_protected_tickers_for_scanner 공통 헬퍼 (호출자 제공)
    (2) 최상단 early-return — 보유/익일청산 절대 보호
    (3) protected_tickers= keyword 의무 (G-1 AST 가드)
    Q2 옵션 C: ticker_market_info["trade_amount_raw"] 1순위 + stock_master 2순위 + miss=graceful.
    Q6-1: acml_tr_pbmn=0 (09:00 race) → graceful 통과 영속.
    """
    taf = await _get_trade_amount_filter_for_scanner()
    if not taf.is_active:
        return candidates  # 비활성 (min_amount=0) → 전체 통과

    survivors: list[str] = []
    excluded: list[tuple[str, int]] = []  # (ticker, acml_tr_pbmn)

    for ticker in candidates:
        # ★ early-return — 보유/익일청산 절대 보호 (Q1 옵션 D 핵심)
        if ticker in protected_tickers:
            survivors.append(ticker)
            continue

        # Q2 옵션 C 통합 폴백
        acml_tr_pbmn = await _get_acml_tr_pbmn(ticker)

        # Q6-1: 미확보 (0) → graceful 통과 (09:00 race 영속)
        if acml_tr_pbmn <= 0:
            survivors.append(ticker)
            continue

        # 임계 평가
        if acml_tr_pbmn < taf.min_amount:
            excluded.append((ticker, acml_tr_pbmn))
            # DailyEmitCap 1회/ticker/일 (매 스캔 폭주 차단)
            if _trade_amount_filter_scanner_skip_logged_today.should_emit(ticker):
                _trade_amount_filter_scanner_skip_logged_today.mark_emitted(ticker)
                logger.info(
                    "[trade_amount_filter_scanner_skip] ticker=%s "
                    "acml_tr_pbmn=%d reason=below_min min=%d",
                    ticker, acml_tr_pbmn, taf.min_amount,
                )
                try:
                    from src.db.system_logs import write_log
                    await write_log(
                        "INFO",
                        f"[trade_amount_filter_scanner_skip] ticker={ticker} "
                        f"acml_tr_pbmn={acml_tr_pbmn} reason=below_min "
                        f"min={taf.min_amount}",
                    )
                except Exception:
                    logger.debug("[trade_amount_filter_scanner_skip] write_log 실패", exc_info=True)
            _trade_amount_filter_scanner_skip_count_today["total"] += 1
        else:
            survivors.append(ticker)

    # Q7-4 funnel step_no=97 hook (graceful — 실패 시 매수 흐름 영향 0)
    try:
        from src.db.strategy_funnel import insert_snapshot
        today_kst = datetime.now(KST_TZ).date().isoformat()
        await insert_snapshot(
            target_date=today_kst,
            strategy_id="ALL",
            step_no=97,
            step_name="trade_amount_filter_scanner",
            survived_count=len(survivors),
            survived_tickers=[{"ticker": t} for t in survivors[:200]],
            excluded_count=len(excluded),
            excluded_sample=[
                {"ticker": t, "acml_tr_pbmn": a, "reason": "below_min"}
                for (t, a) in excluded[:20]
            ],
        )
    except Exception:
        logger.debug("[trade_amount_filter_scanner_funnel] hook 실패 graceful", exc_info=True)

    return survivors


async def emit_trade_amount_filter_scanner_daily_summary() -> None:
    """일일 집계 emit — scheduler._settle() 진입 직전 호출 (사이클 65, Q5 별도 prefix).

    H-2 NO_TRY: scheduler 가 try/except 없이 직접 호출 — AttributeError 가 silent skip 되면
    운영 가시화 무력화 (사이클 64 hotfix 영구 패턴 답습).
    """
    from src.db.system_logs import write_log
    total = _trade_amount_filter_scanner_skip_count_today.get("total", 0)
    msg = f"[trade_amount_filter_scanner_daily_summary] block_count={total}"
    logger.info(msg)
    await write_log("INFO", msg)


# 스캔 결과 캐시
_last_scan_result: list[str] = []
_last_scan_time: str | None = None

# 종목코드 → 종목명 매핑 (스캔 시 갱신)
ticker_names: dict[str, str] = {}

# 종목코드 → 최신 시세 (on_tick에서 갱신)
ticker_prices: dict[str, dict] = {}
# { "current_price": int, "open_price": int, "change_rate": float, "prev_close": int }

# 종목코드 → 전일종가 (스캔 시 개별시세 API에서 저장)
ticker_prev_close: dict[str, int] = {}

# 종목코드 → 시총/거래대금 (스캔 시 저장, 억 단위)
ticker_market_info: dict[str, dict] = {}
# { "market_cap": int(억), "trade_amount": int(억) }

# 종목코드 → 마지막 tick 수신 KST datetime (on_tick에서 갱신, Phase D 가시성 보강)
# scheduler._report_tick_coverage 가 5분 주기로 미수신 종목 카운트를 노출한다.
# 2026-05-11 운영 사고(VB/LTV 종일 시세 무수신) 후속 가시성 결함 보완.
ticker_last_tick: dict[str, datetime] = {}

# 사이클 21 — 모멘텀 단계별 깔때기 카운트 dict (7 키).
# MomentumStrategy 는 prepare() 가 비어 있고 실시간 scan_stocks() 기반.
# scan_stocks() 가 각 단계별로 본 dict 를 누적 → MomentumStrategy.get_scan_stats() 가
# 사본 반환 → ScanMonitor 깔때기 시각화.
scan_filter_stats: dict = {
    "universe_candidates": 0,    # fetch_rising_stocks() raw 응답 수
    "rate_pass": 0,              # 등락률 15%+ 통과
    "mcap_pass": 0,              # 시총 1000억+ 통과
    "trade_amount_pass": 0,      # 거래대금 200억+ 통과
    "limit_up_excluded": 0,      # 상한가 (+30%) 제외 카운트
    "final_prepared": 0,         # 최종 _last_scan_result 길이
    "last_run_at": None,
}

# 추가 필터 조건
MIN_MARKET_CAP = 100_000_000_000      # 시총 1000억 이상
MIN_TRADE_AMOUNT = 20_000_000_000     # 거래대금 200억 이상
MAX_STOCKS = 40                        # 최대 구독 종목 수

# Breakout(VB/LTV) 후순위 슬롯 cap (2026-05-13 작업 2 — momentum 보호).
# 2026-05-13 08:57:39 운영 로그에서 vb=30+ltv=30 → dedup 28 breakout 점유 후
# 09:30 momentum 발화 시 41 한도 초과 → momentum drop 위험 노출. breakout 을
# 25개로 cap 해 잔여 슬롯을 momentum 에 보장한다.
# 명세: `_workspace/00_leader_trading_rules.md` (2026-05-13) 작업 2.
BREAKOUT_LOW_CAP = 25

# ETF/ETN 제외 키워드
ETF_KEYWORDS = ("KODEX", "TIGER", "KBSTAR", "KOSEF", "ARIRANG", "SOL", "ACE",
                "RISE", "KoAct", "PLUS", "TIMEFOLIO", "WOORI", "FOCUS",
                "HANARO", "히어로즈", "마이티", "BNK", "MASTER", "WON",
                "ETN", "선물", "인버스", "레버리지", "채권", "혼합")

# 실시간 체결가 TR_ID — 사이클 26 (2026-05-20): 시간대별 채널 분리
# - PRE/POST NXT 시간대: H0NXCNT0 (NXT 전용 체결가)
# - KRX MAIN 시간대: H0STCNT0 (KRX 전용 체결가)
# 기존 H0UNCNT0 (통합) 상수는 하위 호환용으로 보존 (scheduler._execute_next_day_clear 등 직접 참조)
TICK_TR_ID = "H0UNCNT0"  # (deprecated: 사이클 26 이후 get_active_tick_tr_ids() 사용)
TICK_TR_ID_KRX = "H0STCNT0"   # KRX 메인 전용 (09:00~15:39:59)
TICK_TR_ID_NXT = "H0NXCNT0"   # NXT 프리/애프터 전용 (08:00~08:59:59, 15:40~20:00)

# 시간 경계 상수 (사이클 26 — get_active_tick_tr_ids 내부 사용)
from datetime import time as _time

_TIME_PRE_NXT_START = _time(8, 0)
_TIME_KRX_PRESUBSCRIBE = _time(8, 59, 10)   # KRX 채널 사전 구독 시작 마진
_TIME_KRX_MAIN_START = _time(9, 0)
_TIME_KRX_MAIN_END = _time(15, 30)
_TIME_NXT_PRESUBSCRIBE = _time(15, 39, 10)  # NXT 채널 사전 구독 시작 마진
_TIME_POST_NXT_START = _time(15, 40)
_TIME_POST_NXT_END = _time(20, 0)


def get_active_tick_tr_ids(now_t: "_time | None" = None) -> "set[str]":
    """현재 KST 시각 기준 활성 시세 채널 TR_ID set 반환.

    사이클 26 (2026-05-20) — 시세 채널 시간대별 분리:

    | 구간                      | TR_ID                        | 설명           |
    |---------------------------|------------------------------|----------------|
    | 08:00~08:59:09            | {H0NXCNT0}                   | NXT 프리       |
    | 08:59:10~08:59:59         | {H0NXCNT0, H0STCNT0}         | KRX 사전 마진  |
    | 09:00:00~15:29:59         | {H0STCNT0}                   | KRX 메인       |
    | 15:30:00~15:39:09         | {H0STCNT0}                   | 종가 흡수 마진 |
    | 15:39:10~15:39:59         | {H0STCNT0, H0NXCNT0}         | NXT 사전 마진  |
    | 15:40:00~19:59:59         | {H0NXCNT0}                   | NXT 애프터     |

    사전 마진 50초 구간에서는 두 채널 동시 활성 — 종목별 원자 전환 진행 중
    (_board_transition_loop) + on_tick 중복 호출 안전 (scanner.ticker_prices 마지막 값 채택).

    Returns:
        set[str]: 활성 TR_ID 집합. 장 외 시간이면 빈 집합.
    """
    from datetime import datetime, timezone, timedelta

    if now_t is None:
        kst = timezone(timedelta(hours=9))
        now_t = datetime.now(kst).time()

    # PRE_NXT 구간: 08:00~08:59:09
    if _TIME_PRE_NXT_START <= now_t < _TIME_KRX_PRESUBSCRIBE:
        return {TICK_TR_ID_NXT}

    # KRX 사전 마진: 08:59:10~08:59:59
    if _TIME_KRX_PRESUBSCRIBE <= now_t < _TIME_KRX_MAIN_START:
        return {TICK_TR_ID_NXT, TICK_TR_ID_KRX}

    # KRX 메인 + 종가 흡수 마진: 09:00~15:39:09
    if _TIME_KRX_MAIN_START <= now_t < _TIME_NXT_PRESUBSCRIBE:
        return {TICK_TR_ID_KRX}

    # NXT 사전 마진: 15:39:10~15:39:59
    if _TIME_NXT_PRESUBSCRIBE <= now_t < _TIME_POST_NXT_START:
        return {TICK_TR_ID_KRX, TICK_TR_ID_NXT}

    # POST_NXT: 15:40~19:59:59
    if _TIME_POST_NXT_START <= now_t < _TIME_POST_NXT_END:
        return {TICK_TR_ID_NXT}

    # 장 외 (08:00 이전, 20:00 이후)
    return set()


async def scan_stocks() -> list[str]:
    """당일 급등 종목을 스캔하여 매수 후보를 반환한다.

    1. 등락률 순위 API로 15%+ 상승 종목 조회
    2. ETF/ETN 제외
    3. 시총 1,000억 이상, 거래대금 200억 이상 필터
    4. 등락률 30%+ (상한가) 제외 — momentum 매수 신호 차단과 일관 (사이클 21)
    5. 최대 40종목 제한

    사이클 21 — 단계별 카운트는 `scan_filter_stats` 모듈 전역 dict 에 누적.
    MomentumStrategy.get_scan_stats() 가 그 사본을 반환 → ScanMonitor 깔때기.
    """
    raw_list = await fetch_rising_stocks()
    filtered: list[str] = []

    # 사이클 21 — 카운트 초기화
    scan_filter_stats["universe_candidates"] = len(raw_list)
    scan_filter_stats["rate_pass"] = 0
    scan_filter_stats["mcap_pass"] = 0
    scan_filter_stats["trade_amount_pass"] = 0
    scan_filter_stats["limit_up_excluded"] = 0
    scan_filter_stats["final_prepared"] = 0

    for item in raw_list:
        # 등락률 순위 API 필드명: stck_shrn_iscd (거래량 순위는 mksc_shrn_iscd)
        ticker = item.get("stck_shrn_iscd") or item.get("mksc_shrn_iscd", "")
        name = item.get("hts_kor_isnm", "")
        change_rate = float(item.get("prdy_ctrt", "0"))
        price = int(item.get("stck_prpr", "0"))
        listed_shares = int(item.get("lstn_stcn", "0"))
        trade_amount = int(item.get("acml_tr_pbmn", "0"))

        # 시총/거래대금 계산 (ticker format 검증 전 — market data cache Q2 옵션 C 1순위)
        market_cap = price * listed_shares

        # 사이클 65 — ticker_market_info 는 raw market data cache (진입 가드 X).
        # isdigit() 검증 전에 저장하여 _get_acml_tr_pbmn Q2 옵션 C 1순위 폴백 보장.
        # 진입(filtered 추가/구독)은 아래 isdigit() 가드가 별도 통제.
        if ticker:
            ticker_market_info[ticker] = {
                "market_cap": round(market_cap / 1e8),
                "trade_amount": round(trade_amount / 1e8),       # 억 단위 반올림 (기존 호환)
                "trade_amount_raw": trade_amount,                # 사이클 65 신규 — 원 단위 정밀값 (Q2 옵션 C 1순위)
            }

        # 종목코드 형식 검증 — 6자리 숫자만 허용 (ETF·ETN·신주인수권 등 알파벳 포함 코드 차단)
        # ★ "진입은 6자리 숫자만 (isdigit())" 안전 규칙 — CLAUDE.md 절대 규칙
        if not (len(ticker) == 6 and ticker.isdigit()):
            continue

        # 등락률 15% 미만 제외
        if change_rate < MIN_CHANGE_RATE:
            continue
        # 사이클 21 — 등락률 통과 단독 카운트
        scan_filter_stats["rate_pass"] += 1

        # ETF/ETN 제외
        if any(kw in name for kw in ETF_KEYWORDS):
            continue

        # 시총/거래대금 필터 (데이터 없으면 = 거래량 순위에 미포함 = 소형주 → 제외)
        mcap_ok = market_cap >= MIN_MARKET_CAP
        trade_ok = trade_amount >= MIN_TRADE_AMOUNT
        # 사이클 21 — 시총/거래대금 단독 통과 카운트 (분리)
        if mcap_ok:
            scan_filter_stats["mcap_pass"] += 1
        if trade_ok:
            scan_filter_stats["trade_amount_pass"] += 1

        if not mcap_ok:
            continue
        if not trade_ok:
            continue

        # 사이클 21 — 상한가 (등락률 30%+) 제외. momentum 매수 신호 차단(check_buy_signal:73)과 일관.
        if change_rate >= 30.0:
            scan_filter_stats["limit_up_excluded"] += 1
            continue

        filtered.append(ticker)
        if name:
            ticker_names[ticker] = name

        logger.debug(
            "스캔 통과: %s 등락률=+%.1f%% 시총=%.0f억 거래대금=%.0f억",
            name or ticker, change_rate, market_cap / 1e8, trade_amount / 1e8,
        )

        if len(filtered) >= MAX_STOCKS:
            break

    global _last_scan_result, _last_scan_time
    _last_scan_result = filtered
    _last_scan_time = datetime.now().strftime("%H:%M:%S")

    # 사이클 21 — 최종 카운트 + last_run_at
    scan_filter_stats["final_prepared"] = len(filtered)
    scan_filter_stats["last_run_at"] = datetime.now(KST_TZ).isoformat()

    logger.info(
        "급등종목 스캔: %d종목 통과 (전체 %d종목, 15%%+ 상승 기준)",
        len(filtered), len(raw_list),
    )
    return filtered


def get_scan_status() -> dict:
    """스캔 현황을 반환한다. 모멘텀 + 구독 중인 모든 종목의 데이터를 포함.

    **사이클 11 (2026-05-18) — 풀 전체 카운트**: 메인 세션(`kis_ws._subscriptions`)
    단독이 아니라 `kis_ws_pool.get_subscribed_tickers()` / `get_acked_tickers()` 합집합
    으로 카운트한다. 보조 세션(quote-N) 에 분배된 종목도 가시화 — 운영자가 ScanMonitor
    에서 "subscribed_count=0 / tick_coverage_total=0" 표시를 보던 결함 (2026-05-18
    09:00 KRX 진입 시 31 종목 보조 세션 구독에도 0 표시) 차단.
    """
    subscribed_set = kis_ws_pool.get_subscribed_tickers()
    subscribed = sorted(subscribed_set)
    # 모멘텀 스캔 + 구독 종목 합집합 (VB 종목도 포함)
    all_relevant = set(_last_scan_result) | subscribed_set

    # G3 (2026-05-12) — tick_coverage 4종 카운트 노출.
    # 운영자가 status 단일 호출로 SEND/ACK/fresh/stale 격차 즉시 인지.
    acked_set = kis_ws_pool.get_acked_tickers()
    # G3: 60s 임계는 Phase D `_report_tick_coverage` 와 동일 — 운영 일관성
    now = datetime.now(KST_TZ)
    threshold = timedelta(seconds=60)
    _min_dt = datetime.min.replace(tzinfo=KST_TZ)
    fresh_count = sum(
        1 for t in subscribed_set
        if (now - ticker_last_tick.get(t, _min_dt)) <= threshold
    )
    stale_count = len(subscribed_set) - fresh_count

    return {
        "filtered_tickers": _last_scan_result,
        "filtered_count": len(_last_scan_result),
        "subscribed_tickers": subscribed,
        "subscribed_count": len(subscribed),
        "last_scan_time": _last_scan_time,
        "ticker_names": {k: v for k, v in ticker_names.items() if k in all_relevant},
        "ticker_prices": {k: v for k, v in ticker_prices.items() if k in all_relevant},
        "ticker_market_info": {k: v for k, v in ticker_market_info.items() if k in all_relevant},
        # G3 — 운영자 가시화용 보조 카운트
        "tick_coverage_total": len(subscribed_set),
        "tick_coverage_acked": len(acked_set),
        "tick_coverage_fresh": fresh_count,
        "tick_coverage_stale": stale_count,
    }


def t(ticker: str) -> str:
    """종목코드를 '종목명(코드)' 형태로 반환한다."""
    name = ticker_names.get(ticker)
    return f"{name}({ticker})" if name else ticker


def resolve_ticker_name(ticker: str | None) -> str:
    """종목명 단일 lookup — 사이클 44 (2026-05-22, refactor-review 카드 #7).

    기존 4 경로 (ticker_names / STATIC_TICKER_NAMES / strategy_base._resolve_ticker_name / t())
    통합. 단일 진입점 — 폴백 순서 고정:

    1. `ticker_names` (동적, WS 시세 수신 시 갱신) — 1순위
    2. `STATIC_TICKER_NAMES` (정적, scanner.py 자기 파일 정규식 파싱) — 2순위
    3. `""` (빈 문자열, lookup miss — 예외 전파 금지, graceful)

    Args:
        ticker: 6자리 종목코드 (또는 None/빈 문자열 — graceful).

    Returns:
        종목명 또는 빈 문자열 (lookup miss).

    Note:
        본 함수는 lookup only — `ticker_names` 갱신은 WebSocket `_handle_raw` 또는
        `subscribe_filtered_stocks` 가 담당. 호출 시 dict snapshot 보장 안 됨
        (동시성 무해 — 빈 문자열 폴백).
    """
    if not ticker:
        return ""
    try:
        # 1차: 동적 매핑 (WS 시세 수신 시 갱신)
        name = ticker_names.get(ticker)
        if name:
            return name
        # 2차: 정적 매핑 (scanner.py 모듈 시드)
        return STATIC_TICKER_NAMES.get(ticker, "") or ""
    except (AttributeError, TypeError):
        # graceful — dict 접근 예외 (모듈 import 순서 / mock 등)
        return ""


# KOSPI 200 대표 종목 (하드코딩, 향후 API 조회로 변경 가능) — 시총 상위 위주
KOSPI_200_TICKERS = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "373220",  # LG에너지솔루션
    "207940",  # 삼성바이오로직스
    "005380",  # 현대차
    "000270",  # 기아
    "005935",  # 삼성전자우
    "068270",  # 셀트리온
    "005490",  # POSCO홀딩스
    "035420",  # NAVER
    "006400",  # 삼성SDI
    "051910",  # LG화학
    "105560",  # KB금융
    "055550",  # 신한지주
    "012330",  # 현대모비스
    "028260",  # 삼성물산
    "035720",  # 카카오
    "086790",  # 하나금융지주
    "032830",  # 삼성생명
    "138040",  # 메리츠금융지주
    "066570",  # LG전자
    "017670",  # SK텔레콤
    "316140",  # 우리금융지주
    "015760",  # 한국전력
    "003670",  # 포스코퓨처엠
    "010130",  # 고려아연
    "024110",  # 기업은행
    "034730",  # SK
    "030200",  # KT
    "009150",  # 삼성전기
    "011200",  # HMM
    "018260",  # 삼성에스디에스
    "033780",  # KT&G
    "010950",  # S-Oil
    "096770",  # SK이노베이션
    "267260",  # HD현대일렉트릭
    "267250",  # HD현대
    "329180",  # HD현대중공업
    "010140",  # 삼성중공업
    "042660",  # 한화오션
    "004020",  # 현대제철
    "086280",  # 현대글로비스
    "000810",  # 삼성화재
    "402340",  # SK스퀘어
    "012450",  # 한화에어로스페이스
    "079550",  # LIG넥스원
    "047810",  # 한국항공우주
    "272210",  # 한화시스템
    "352820",  # 하이브
    "041510",  # 에스엠
    "035900",  # JYP Ent.
    "377300",  # 카카오페이
    "323410",  # 카카오뱅크
    "259960",  # 크래프톤
    "036570",  # 엔씨소프트
    "251270",  # 넷마블
    "180640",  # 한진칼
    "003490",  # 대한항공
    "002350",  # 넥센타이어
    "161390",  # 한국타이어앤테크놀로지
    "271560",  # 오리온
    "097950",  # CJ제일제당
    "271940",  # 일동홀딩스
    "139480",  # 이마트
    "069960",  # 현대백화점
    "023530",  # 롯데쇼핑
    "282330",  # BGF리테일
    "007310",  # 오뚜기
    "004990",  # 롯데지주
    "001040",  # CJ
    "078930",  # GS
    "000720",  # 현대건설
    "375500",  # DL이앤씨
    "047040",  # 대우건설
    "028050",  # 삼성엔지니어링
    "302440",  # SK바이오사이언스
    "326030",  # SK바이오팜
    "003550",  # LG
    "034220",  # LG디스플레이
    "011070",  # LG이노텍
]

# KOSDAQ 150 대표 종목 (하드코딩, 향후 API 조회로 변경 가능)
KOSDAQ_150_TICKERS = [
    "247540",  # 에코프로비엠
    "091990",  # 셀트리온헬스케어
    "086520",  # 에코프로
    "263750",  # 펄어비스
    "293490",  # 카카오게임즈
    "328130",  # 루닛
    "145020",  # 휴젤
    "196170",  # 알테오젠
    "067160",  # 아프리카TV
    "041510",  # 에스엠
    "112040",  # 위메이드
    "068270",  # 셀트리온제약
    "035720",  # 카카오
    "035420",  # NAVER
    "051910",  # LG화학
    "253450",  # 스튜디오드래곤
    "357780",  # 솔브레인
    "058470",  # 리노공업
    "214150",  # 클래시스
    "277810",  # 레인보우로보틱스
    "039030",  # 이오테크닉스
    "078600",  # 대주전자재료
    "095340",  # ISC
    "240810",  # 원익IPS
    "141080",  # 레고켐바이오
    "131970",  # 테스나
    "137310",  # 에스디바이오센서
    "140410",  # 메지온
    "060310",  # 3S
    "383220",  # F&F
    "403870",  # HPSP
    "041190",  # 우리기술투자
    "336260",  # 두산테스나
    "108860",  # 셀바스AI
    "222080",  # 씨아이에스
    "089030",  # 테크윙
    "009520",  # 포스코엠텍
    "234080",  # JW생명과학
    "036930",  # 주성엔지니어링
    "330860",  # 네이처셀
]


def scan_kosdaq150() -> list[str]:
    """KOSDAQ 150 종목 리스트를 반환한다."""
    return list(KOSDAQ_150_TICKERS)


def scan_kospi200() -> list[str]:
    """KOSPI 200 종목 리스트를 반환한다."""
    return list(KOSPI_200_TICKERS)


# 정적 종목명 dict — KOSPI_200_TICKERS / KOSDAQ_150_TICKERS의 인라인 코멘트(`# 종목명`)를
# 모듈 import 시 1회 정규식으로 추출. KIS API가 hts_kor_isnm을 빈 문자열로 응답하는 케이스
# (예: 일부 종목, 모의/실전 차이)에서 프론트가 "KOSPI200(005930)" 같은 시장명 표시로
# 떨어지지 않도록 ticker_names의 fallback으로 사용.
import os as _os
import re as _re

_STATIC_TICKER_NAME_RE = _re.compile(r'"(\d{6})",\s*#\s*([^\n]+)')


def _parse_static_ticker_names() -> dict[str, str]:
    try:
        with open(_os.path.abspath(__file__), encoding="utf-8") as f:
            src = f.read()
        return {m.group(1): m.group(2).strip() for m in _STATIC_TICKER_NAME_RE.finditer(src)}
    except Exception:
        return {}


STATIC_TICKER_NAMES: dict[str, str] = _parse_static_ticker_names()
# ticker_names의 시드 — KIS 응답이 비면 이 값이 그대로 노출됨. KIS 정상 응답 시 덮어씀.
ticker_names.update(STATIC_TICKER_NAMES)


async def subscribe_filtered_stocks(
    tickers: list[str],
    extra_tickers: list[str] | None = None,
    source_counts: dict[str, int] | None = None,
    *,
    priority_groups: dict[str, list[str]] | None = None,
) -> None:
    """필터링된 종목들에 대해 WebSocket 실시간 시세 구독을 등록한다.

    모멘텀 후보 + 추가 종목(변동성돌파 등)의 합집합을 구독한다.

    `source_counts` 가 주어지면 출처별 카운터를 로그에 노출한다 (Phase B, 2026-05-12):
        [scanner] 실시간 시세 구독 완료: total=N (vb=A, ltv=B, swing=C, momentum=D, positions=E)
    - 출처별 카운트는 합집합 *전* 원본 개수 (중복 가능)
    - total 은 합집합(dedupe) 후 실제 구독 종목 수
    - 영문 라벨 유지 (Grafana/Loki 쿼리 안정성)
    - dict 가 None 이면 기존 "(모멘텀: X, 기타: Y)" fallback (외부 호출자 호환)
    - 누락 키는 0 으로 처리

    `priority_groups` 가 주어지면 우선순위 큐로 변환해 구독한다 (E1, 2026-05-12 + G안 2026-05-12):
        positions → next_day_clear → breakout → momentum → swing (HIGH → LOW)
    - positions / next_day_clear 는 `bypass_limit=True` 로 한도(MAX_SUBSCRIPTIONS=41) 무시 — 절대 보장
    - LOW 순서 재정렬 (G안, 2026-05-12): 슬롯 부족 시 swing 이 가장 먼저 잘려도 안전.
      donchian_swing 은 Pull 폴링(_swing_buy_poll_loop)으로 매수 평가하므로 LOW 슬롯 잃어도 OK.
      변동성 돌파(VB/LTV) 후보를 우선 보장해 일중 매매 기회 확보.
    - 후순위(breakout/momentum/swing)는 잔여 슬롯만큼만 add
    - 중복 종목은 HIGH 순위로 1회만 subscribe (후순위에서는 skip, drop 카운트에도 미포함)
    - drop>0 발생 시 INFO 로그 1행 + WARNING system_logs 영구 저장 (가설 A — 가시성):
      `[priority_drop] breakout=X momentum=Y swing=Z total_subscribed=N max=41 high_count=H low_remaining=R`
    - HIGH 단독 합계가 한도 초과 시 ERROR 로그 + system_logs 기록 (운영자 경보)
    - `priority_groups=None` 이면 기존 평탄 처리 (외부 호환). `source_counts` 로그는 priority_groups 와 무관하게 보존
    - 어제·오늘 donchian_swing 조기 손절 사건(보유 종목 시세 누락) 루트 원인 차단

    사이클 64 (2026-06-06) — 진입 직후 가격 필터 단일 hook (Q4 옵션 A).
    사이클 65 (2026-06-06) — 가격 필터 직후 거래대금 필터 순차 hook (Q3 옵션 A).
    Q1 옵션 D: `_apply_price_filter` / `_apply_trade_amount_filter` 양쪽 `protected_tickers=` keyword 의무.
    """
    # ★ 사이클 83 — 후보 풀 ticker stock_master eager refresh hook (Q1=B)
    # 비동기 큐 등록만 (본체 차단 0) — 실제 refresh 는 5분 주기 task 가 담당 (Q2=C)
    _all_candidates: list[str] = list(tickers)
    if extra_tickers:
        _all_candidates.extend(extra_tickers)
    if priority_groups:
        for _pg_val in priority_groups.values():
            if _pg_val:
                _all_candidates.extend(_pg_val)
    _record_scan_pool_candidates(_all_candidates)

    # ★ 사이클 64 — 가격 필터 단일 hook (Q4 옵션 A)
    _protected = _collect_protected_tickers_for_scanner()
    tickers = await _apply_price_filter(tickers, protected_tickers=_protected)
    if extra_tickers:
        extra_tickers = await _apply_price_filter(extra_tickers, protected_tickers=_protected)
    if priority_groups:
        for _pkey in list(priority_groups.keys()):
            if priority_groups[_pkey]:
                priority_groups[_pkey] = await _apply_price_filter(
                    priority_groups[_pkey], protected_tickers=_protected,
                )

    # ★ 사이클 65 — 거래대금 필터 순차 hook (Q3 옵션 A, AND 결합)
    # G-1 AST 가드: 4 호출 의무 = tickers(1) + extra_tickers(1) + priority_groups 3 키 명시(2)
    # (priority_groups 3 key 중 breakout/swing 쌍을 for loop 대신 직접 2 호출로 카운팅)
    tickers = await _apply_trade_amount_filter(tickers, protected_tickers=_protected)  # (1)
    if extra_tickers:
        extra_tickers = await _apply_trade_amount_filter(extra_tickers, protected_tickers=_protected)  # (2)
    if priority_groups:
        for _taf_pkey in ("breakout", "momentum"):
            if priority_groups.get(_taf_pkey):
                priority_groups[_taf_pkey] = await _apply_trade_amount_filter(
                    priority_groups[_taf_pkey], protected_tickers=_protected,
                )  # (3) — for loop 1 AST node (breakout + momentum)
        if priority_groups.get("swing"):
            priority_groups["swing"] = await _apply_trade_amount_filter(
                priority_groups["swing"], protected_tickers=_protected,
            )  # (4) — swing 명시 분리

    extra = extra_tickers or []
    all_tickers = list(dict.fromkeys(tickers + extra))  # 순서 유지 중복 제거

    if priority_groups is not None:
        # 우선순위 큐: HIGH → LOW
        positions = list(dict.fromkeys(priority_groups.get("positions") or []))
        next_day_clear = list(dict.fromkeys(priority_groups.get("next_day_clear") or []))
        swing = list(dict.fromkeys(priority_groups.get("swing") or []))
        momentum = list(dict.fromkeys(priority_groups.get("momentum") or []))
        breakout = list(dict.fromkeys(priority_groups.get("breakout") or []))

        from src.realtime.websocket import MAX_SUBSCRIPTIONS

        # HIGH 단독 한도 초과 — 이상 케이스 (운영자 경보)
        high_total = len(positions) + len(next_day_clear)
        if high_total > MAX_SUBSCRIPTIONS:
            logger.error(
                "HIGH 우선순위 구독 한도 초과: positions=%d next_day_clear=%d limit=%d",
                len(positions), len(next_day_clear), MAX_SUBSCRIPTIONS,
            )
            try:
                from src.db.system_logs import write_log
                await write_log(
                    "ERROR",
                    f"[priority] HIGH 구독 한도 초과: positions={len(positions)} "
                    f"next_day_clear={len(next_day_clear)} limit={MAX_SUBSCRIPTIONS}",
                )
            except Exception:
                # DB 로깅 실패는 흡수 — 실제 구독 흐름은 계속
                logger.debug("HIGH 한도 초과 system_logs 기록 실패", exc_info=True)

        already: set[str] = set()
        # 사이클 15-A (2026-05-19) — 이미 풀에 구독 중인 LOW 종목은 SEND skip (KIS 정상 패턴).
        # HIGH 종목 (positions / next_day_clear) 은 always 호출 — 풀의 _select_session 이
        # promote (보조→메인 이동) 또는 noop 판단. 사전에 skip 하면 promote 차단됨.
        already_in_pool: set[str] = set(kis_ws_pool.get_subscribed_tickers())
        # 사이클 7-C — 풀로 위임. priority="HIGH"/"LOW" + bypass_limit 명시 전달.
        # 보조 세션 0개 시 풀이 메인으로 fallback (회귀 0).
        # 1) positions — priority='HIGH', bypass_limit=True (절대 보장, promote 보존)
        for t in positions:
            if t in already:
                continue
            already.add(t)
            await kis_ws_pool.subscribe(
                TICK_TR_ID, t, priority="HIGH", bypass_limit=True,
            )
        # 2) next_day_clear — priority='HIGH', bypass_limit=True (절대 보장)
        for t in next_day_clear:
            if t in already:
                continue
            already.add(t)
            await kis_ws_pool.subscribe(
                TICK_TR_ID, t, priority="HIGH", bypass_limit=True,
            )

        # 3~5) 후순위 — 2-pass 슬롯 흡수 (PR-E P1, 2026-05-15)
        # LOW 순서 (G안, 2026-05-12): breakout → momentum → swing.
        # donchian_swing 은 Pull 폴링으로 매수 평가하므로 슬롯 손실 안전.
        #
        # PR-E (P1, 2026-05-15) — 2-pass 슬롯 흡수:
        #   1차: positions(bypass) → next_day_clear(bypass) → breakout[:cap] → momentum → swing
        #   2차: 잔여 슬롯 (MAX - len(_subscriptions)) > 0 이면
        #        breakout cap 초과분(overflow) 에서 추가 add
        #   최종 drop = max(0, len(overflow) - actually_added_in_2nd_pass)
        # 결함 (운영 로그 2026-05-15 07:55:08):
        #   [priority_drop] breakout=3 ... total_subscribed=30 max=41 ... low_remaining=11
        #   → 11 슬롯 미사용인데도 breakout overflow 3 종목이 silently drop 되어 운영 슬롯 낭비.
        # 2-pass 로 잔여 슬롯에 overflow 를 흡수해 슬롯 낭비 + 부당 drop 동시 차단.
        drop_counts: dict[str, int] = {"breakout": 0, "momentum": 0, "swing": 0}

        # 작업 2 (2026-05-13): breakout cap 25 — momentum 슬롯 보호.
        # 1차에서는 cap 만 add, overflow 는 2차에서 잔여 슬롯에 흡수.
        breakout_primary: list[str]
        breakout_overflow: list[str]
        if len(breakout) > BREAKOUT_LOW_CAP:
            breakout_primary = breakout[:BREAKOUT_LOW_CAP]
            breakout_overflow = breakout[BREAKOUT_LOW_CAP:]
        else:
            breakout_primary = breakout
            breakout_overflow = []

        # 1-pass: cap 적용된 breakout + momentum + swing 순서로 add
        # 사이클 7-C — 풀로 위임. priority='LOW' (보조 세션 라운드로빈 우선, 메인 fallback).
        # 사이클 15-A — 이미 풀에 있는 LOW 종목은 SEND skip (KIS 정상 패턴 준수).
        for label, candidates in (
            ("breakout", breakout_primary),
            ("momentum", momentum),
            ("swing", swing),
        ):
            for t in candidates:
                if t in already:
                    # 중복 제거 — drop 카운트에 포함하지 않음 (이미 구독했으므로)
                    continue
                if t in already_in_pool:
                    # 사이클 15-A: 이미 풀에 LOW 로 구독 중 — KIS SEND skip
                    already.add(t)
                    continue
                remaining = MAX_SUBSCRIPTIONS - len(kis_ws._subscriptions)
                if remaining <= 0:
                    drop_counts[label] += 1
                    continue
                already.add(t)
                await kis_ws_pool.subscribe(
                    TICK_TR_ID, t, priority="LOW", bypass_limit=False,
                )

        # 2-pass: breakout overflow 잔여 슬롯 흡수
        # 흡수에 성공한 만큼 drop 에서 차감. 흡수 실패분만 최종 drop["breakout"] 에 합산.
        # Codex P2 / Copilot (2026-05-15) — 중복(이미 구독된 종목) skip 분리 카운트:
        # `t in already` 로 skip 된 ticker 는 실제로 다른 그룹에 의해 이미 구독 중이라
        # drop 아님. `skipped_already` 카운터로 분리해 최종 drop 계산에서 차감.
        # 미차감 시 false `[priority_drop] breakout=...` 영구 WARNING 발생.
        absorbed_overflow = 0
        skipped_already = 0
        for t in breakout_overflow:
            if t in already:
                # 다른 그룹(positions/next_day_clear/breakout_primary/momentum/swing)
                # 이 이미 구독한 종목 — drop 아닌 중복
                skipped_already += 1
                continue
            if t in already_in_pool:
                # 사이클 15-A: 이미 풀에 LOW 로 구독 중 — KIS SEND skip (drop 아님)
                already.add(t)
                skipped_already += 1
                continue
            remaining = MAX_SUBSCRIPTIONS - len(kis_ws._subscriptions)
            if remaining <= 0:
                # 잔여 0 — 더 이상 흡수 불가
                break
            already.add(t)
            absorbed_overflow += 1
            # 사이클 7-C — overflow 도 LOW priority 로 풀에 위임
            await kis_ws_pool.subscribe(
                TICK_TR_ID, t, priority="LOW", bypass_limit=False,
            )
        # 흡수 못 한 overflow 만 최종 drop 에 합산 (중복 skip 차감).
        drop_counts["breakout"] += max(
            0, len(breakout_overflow) - absorbed_overflow - skipped_already
        )

        total_dropped = sum(drop_counts.values())
        if total_dropped > 0:
            # 확장 형식 (가설 A 가시성): total_subscribed/max/high_count/low_remaining 추가.
            # Copilot P2 (2026-05-12): `low_remaining` 으로 의미 명확화(LOW 그룹 잔여 슬롯) +
            # HIGH bypass 시 음수 노출 차단(`max(0, ...)`) — 대시보드 해석 혼동 방지.
            total_subscribed = len(kis_ws._subscriptions)
            high_count = len(set(positions) | set(next_day_clear))
            low_remaining = max(0, MAX_SUBSCRIPTIONS - total_subscribed)
            drop_log = (
                f"[priority_drop] breakout={drop_counts['breakout']} "
                f"momentum={drop_counts['momentum']} swing={drop_counts['swing']} "
                f"total_subscribed={total_subscribed} max={MAX_SUBSCRIPTIONS} "
                f"high_count={high_count} low_remaining={low_remaining}"
            )
            logger.warning(drop_log)
            # 사이클 72 hotfix A11: write_log 제거 — logger.warning → _DbLogHandler 위임 단일 INSERT
            # (drop 발생은 WARNING 레벨로 격상 — 운영 가시화 보존)
    else:
        # 기존 평탄 처리 (외부 호환 fallback)
        for ticker in all_tickers:
            await kis_ws.subscribe(TICK_TR_ID, ticker)

    if source_counts is not None:
        vb = int(source_counts.get("vb", 0))
        ltv = int(source_counts.get("ltv", 0))
        bfb = int(source_counts.get("bfb", 0))
        vcp = int(source_counts.get("vcp", 0))
        swing_c = int(source_counts.get("swing", 0))
        momentum_c = int(source_counts.get("momentum", 0))
        positions_c = int(source_counts.get("positions", 0))
        logger.info(
            "실시간 시세 구독 완료: total=%d "
            "(vb=%d, ltv=%d, bfb=%d, vcp=%d, swing=%d, momentum=%d, positions=%d)",
            len(all_tickers), vb, ltv, bfb, vcp, swing_c, momentum_c, positions_c,
        )
    else:
        logger.info("실시간 시세 구독 완료: %d종목 (모멘텀: %d, 기타: %d)",
                    len(all_tickers), len(tickers), len(extra))


async def unsubscribe_all() -> None:
    """모든 종목 구독을 해제한다 (메인 + 보조 세션 전체)."""
    # 사이클 13-E-1 리뷰 ③ — 실패 카운터 + 조건부 로그 레벨.
    # 일부 구독 해제 실패 시 INFO "완료" 로그가 운영자에게 잘못된 신호를 보내지 않도록
    # 실패 개수를 집계해 WARNING 으로 격상 + 성공은 무실패 시에만 INFO.
    pool_failures = 0
    main_failures = 0

    # WebsocketPool 위임 — _ticker_to_session 추적까지 일괄 정리
    try:
        await kis_ws_pool.unsubscribe_all()
    except Exception:
        logger.warning("[scanner_unsubscribe_all] pool.unsubscribe_all 실패", exc_info=True)
        pool_failures = 1

    # 보강: pool 분배 추적에 없는 메인 직접 구독 (체결통보 제외 TICK) 잔존 정리
    for tr_id, tr_key in list(kis_ws._subscriptions):
        if tr_id == TICK_TR_ID:
            try:
                await kis_ws.unsubscribe(tr_id, tr_key)
            except Exception:
                logger.debug("[scanner_unsubscribe_all] main 잔여 해제 실패", exc_info=True)
                main_failures += 1

    total_failures = pool_failures + main_failures
    if total_failures > 0:
        logger.warning(
            "[scanner_unsubscribe_all] 일부 구독 해제 실패 — pool=%d, main=%d",
            pool_failures, main_failures,
        )
    else:
        logger.info("모든 시세 구독 해제 완료")


# ---------------------------------------------------------------------------
# 사이클 83 (2026-06-09) — _scan_loop 후보 풀 ticker stock_master eager refresh
# ---------------------------------------------------------------------------
# 위치: subscribe_filtered_stocks 진입점 hook (Q1=B) + 5분 백그라운드 task (Q2=C).
# 사이클 13-D `_eager_refresh_stock_master_for_held_positions` 패턴 100% 답습.
# Q3=B: 24h TTL fresh skip + ticker 간 50ms sleep (KIS Rate Limit 20/s 보호).
# 사이클 74/78 sampling/aggregation 패턴 답습 (5분 윈도우 1행 emit).
# 사이클 38 명문화 영속: tradable_boards 참조 0건 (매수 진입 전용 영역 외부).

_SCAN_POOL_EAGER_REFRESH_WINDOW_SECS: float = 300.0  # 5분 (사이클 42/74/78 답습)
_SCAN_POOL_RATE_LIMIT_SLEEP_SECS: float = 0.05       # 50ms (Q3=B)

# 5분 윈도우 누적 collector (사이클 74 패턴 답습)
_scan_pool_eager_refresh_collector: list[dict] = []

# subscribe_filtered_stocks 진입점 hook 용 후보 ticker 누적 (배치 처리)
_scan_pool_candidates_collector: list[str] = []
_scan_pool_eager_refresh_window_start: float = 0.0


def _collect_scan_pool_tickers_for_eager_refresh(tickers: list[str]) -> None:
    """subscribe_filtered_stocks 진입점 hook (Q1=B) — Red 명세 명명 답습.

    후보 풀 ticker 를 5분 윈도우 누적 collector 에 적재한다.
    비동기 큐 등록만 (본체 차단 0).
    """
    global _scan_pool_eager_refresh_window_start
    if not _scan_pool_eager_refresh_window_start:
        _scan_pool_eager_refresh_window_start = _monotonic_time.monotonic()
    _scan_pool_candidates_collector.extend(tickers)


# 내부 alias (subscribe_filtered_stocks 진입점 hook 사용)
_record_scan_pool_candidates = _collect_scan_pool_tickers_for_eager_refresh


def record_scan_pool_eager_refresh(stats: dict) -> None:
    """5분 윈도우 eager refresh 통계 1건 collector 적재 (사이클 74 패턴 답습)."""
    _scan_pool_eager_refresh_collector.append(stats)


def flush_scan_pool_eager_refresh_collector() -> None:
    """5분 윈도우 통계 collector → 1행 emit + clear (사이클 74/78 패턴 답습).

    빈 윈도우는 skip (사이클 76 Q2 답습).
    """
    global _scan_pool_eager_refresh_collector
    if not _scan_pool_eager_refresh_collector:
        return

    total_candidates = sum(s.get("candidates", 0) for s in _scan_pool_eager_refresh_collector)
    total_refreshed = sum(s.get("refreshed", 0) for s in _scan_pool_eager_refresh_collector)
    total_skipped = sum(s.get("skipped", 0) for s in _scan_pool_eager_refresh_collector)
    total_failed = sum(s.get("failed", 0) for s in _scan_pool_eager_refresh_collector)
    total_elapsed_ms = sum(s.get("elapsed_ms", 0) for s in _scan_pool_eager_refresh_collector)

    logger.info(
        "[scan_pool_eager_refresh] window=300s candidates=%d refreshed=%d "
        "skipped=%d failed=%d elapsed_ms=%d",
        total_candidates, total_refreshed, total_skipped, total_failed, total_elapsed_ms,
    )

    _scan_pool_eager_refresh_collector.clear()


async def _scan_pool_eager_refresh_loop(
    candidates: list[str] | None = None,
) -> None:
    """후보 풀 ticker stock_master eager refresh 실행 본체.

    scheduler 의 `_scan_pool_eager_refresh_loop` 메서드 (5분 주기 무한 loop) 와
    단일 실행 (candidates 인자 직접 전달, 테스트 용) 양쪽 지원.

    사이클 13-D `_eager_refresh_stock_master_for_held_positions` 패턴 답습:
    - sequential await
    - 24h TTL fresh skip (Q3=B)
    - ticker 간 50ms sleep (KIS Rate Limit 보호)
    - graceful 예외 처리

    인자:
        candidates: None 이면 `_scan_pool_candidates_collector` 를 소비 (scheduler 호출),
                    list 이면 해당 list 직접 사용 (단일 실행 / 테스트 용).
    """
    import time as _t
    from src.api.condition import inquire_stock_basics
    from src.db import stock_master

    global _scan_pool_candidates_collector

    if candidates is not None:
        # 단일 실행 모드 (테스트 / subscribe_filtered_stocks hook 직접 호출)
        unique_tickers = list(dict.fromkeys(candidates))
    else:
        # scheduler 5분 주기 소비 모드
        unique_tickers = list(dict.fromkeys(_scan_pool_candidates_collector))
        _scan_pool_candidates_collector = []

    if not unique_tickers:
        return

    start_ms = _t.monotonic() * 1000
    refreshed = 0
    skipped_fresh = 0
    failed = 0

    for ticker in unique_tickers:
        # 24h TTL fresh skip (Q3=B + 사이클 68 KST 답습)
        try:
            is_stale = await stock_master.is_stale(ticker, max_age_hours=24)
        except Exception:
            is_stale = True  # graceful — 조회 실패 시 refresh 시도

        if not is_stale:
            skipped_fresh += 1
            await asyncio.sleep(_SCAN_POOL_RATE_LIMIT_SLEEP_SECS)
            continue

        try:
            basics = await inquire_stock_basics(ticker)
            if basics is not None:
                await stock_master.upsert_one(basics)
            refreshed += 1
        except Exception as e:
            logger.warning("[scan_pool_eager_refresh] ticker=%s error=%s", ticker, e)
            failed += 1

        await asyncio.sleep(_SCAN_POOL_RATE_LIMIT_SLEEP_SECS)  # 50ms (Q3=B)

    elapsed_ms = int(_t.monotonic() * 1000 - start_ms)
    record_scan_pool_eager_refresh({
        "candidates": len(unique_tickers),
        "refreshed": refreshed,
        "skipped": skipped_fresh,
        "failed": failed,
        "elapsed_ms": elapsed_ms,
    })


# ---------------------------------------------------------------------------
# 사이클 97 (2026-06-10) — KIS fluctuation API (FHPST01700000) 영역 신규 도입
# 사이클 89/91/94/96 volume_rank 영역 전수 폐기 (KIS 단일 페이지 30 한도 + 페이징 미지원)
# 사이클 99 (2026-06-10) — 페이징 영역 영구 폐기 + 60 ticker 영구 영속 명문화
#   KIS API 전체 영역 = 페이징 미지원 영구 확정 (운영 실증 사이클 96 + 98 누적)
#   tr_cont "M" 영구 비반환 → 단일 호출 영구 영속 (top_n=30, max_pages 인자 폐기)
# ---------------------------------------------------------------------------
# 영속 의무:
# - 사이클 38 명문화: tradable_boards 매수 진입 전용 (매도 hot path 영향 0)
# - 사이클 64 protected_tickers: 영역 분리 (영향 0)
# - 사이클 81 bfdy_clpr: 영역 분리 (영향 0)
# - 사이클 83 scan_pool eager refresh: candidates=12 영역 영속 (영역 분리)
# - 사이클 88 G-REJECT: 외부 LLM 영구 차단 AST 가드 3 영속
# - 사이클 89 ETF 제외 + 거래대금 정렬: fluctuation 영역 (Q68=A 사이클 101 영구 폐기)
# - 사이클 91 페이징: 영구 폐기 (KIS API 본질 한계 영구 수용)
# - 사이클 96 KOSPI/KOSDAQ 분리 호출: fluctuation 영역 (Q68=A 사이클 101 영구 폐기)
# - 사이클 98 G-DOC1: chk_fluctuation.py 정본 인용 의무 (Q68=A 폐기로 해제)
# - 사이클 101 (2026-06-11): market_cap (FHPST01740000) 신규 + fluctuation 영구 폐기 (Q68=A)
#   + universe_eager_refresh_loop 영구 폐기 (Q69=B) + 매일 20:00:05 일괄 적재
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 사이클 101 (2026-06-11) — KIS market_cap API (FHPST01740000) 상수
# KIS 정본 인용 (chk_market_cap.py main 호출 영역 정본):
#   URL = /uapi/domestic-stock/v1/ranking/market-cap
#   fid_cond_mrkt_div_code = "J" (KRX 전체, ValueError if not)
#   fid_cond_scr_div_code  = "20174" (정본 강제 검증)
#   fid_input_iscd: "0001" = 거래소(KOSPI) / "1001" = 코스닥(KOSDAQ) / "0000" = 전체
#   tr_cont "M" → 재귀 호출 + "N" 영속 (정본 L107~120)
# ---------------------------------------------------------------------------
_MARKET_CAP_URL = "/uapi/domestic-stock/v1/ranking/market-cap"
_MARKET_CAP_TR_ID = "FHPST01740000"

# KIS 정본 fid_input_iscd 매핑 (chk_market_cap.py 정본)
# 주의: fluctuation "0002"(KOSDAQ 업종) 와 완전 다름 — "1001" 이 코스닥 정본 (KIS MCP 확인)
_MARKET_CAP_INPUT_ISCD: dict[str, str] = {
    "kospi": "0001",   # 거래소 (KOSPI)
    "kosdaq": "1001",  # 코스닥 (KOSDAQ) — fluctuation "0002" 와 차별
}

# 환경 분리 Rate Limit (domain-expert A3 영속)
# 실전: KIS 20건/s = 50ms sleep → 2,800 / 20 = 140s (2분 20초, 20:00:05~20:02:25)
# 모의: KIS 5건/s = 200ms sleep → 2,800 / 5 = 560s → 20:09:25 종료, 20:10 정산 race 차단
_FULL_UNIVERSE_SLEEP_REAL: float = 0.050  # 50ms = 1/20s (실전 20건/s)
_FULL_UNIVERSE_SLEEP_VTS: float = 0.200   # 200ms = 1/5s (모의 5건/s)
_FULL_UNIVERSE_MAX_LOAD_SECONDS_REAL: int = 300   # 5분 (실전 안전 마진)
_FULL_UNIVERSE_MAX_LOAD_SECONDS_VTS: int = 600    # 10분 (모의, 정산 직전 차단)

# A2: ETF/리츠/SPAC 제외 — `prdt_type_cd` 기반
# "300" = 보통주 (통과), "301" = ETF (제외), "302" = 리츠 (제외), "309" = SPAC (제외)
# 기타 코드(ETN=310 등)도 제외 (보통주 "300" 만 통과)
_ALLOWED_PRODUCT_TYPE_CD = {"300"}  # 보통주만 통과


def _universe_filter_securities_only(rows: list[dict]) -> list[dict]:
    """ETF/리츠/우선주/SPAC 자동 제외 헬퍼 (A2 권고).

    사이클 89 (2026-06-09) 신규. KIS `volume_rank` 응답 rows 에서
    `prdt_type_cd` 기반으로 보통주("300") 만 통과시킨다.

    종목코드 형식 검증 병행: 6자리 숫자가 아닌 코드 차단 (ETF/ETN 알파벳 코드).
    prdt_type_cd 키가 없거나 빈 경우 → 종목코드 패턴으로 fallback (6자리 숫자 = 통과).

    Args:
        rows: KIS volume_rank output list (각 item 은 dict)

    Returns:
        보통주만 필터링된 rows 리스트
    """
    result: list[dict] = []
    for row in rows:
        # 사이클 97 — fluctuation 응답 키: stck_shrn_iscd (volume_rank mksc_shrn_iscd 와 영역 차별)
        # KIS chk_fluctuation.py COLUMN_MAPPING 정본 영속
        ticker = row.get("stck_shrn_iscd") or row.get("mksc_shrn_iscd", "")
        # 종목코드 형식 검증 — ETF·ETN·신주인수권 알파벳 코드 차단 (사이클 64 패턴 답습)
        if not (len(ticker) == 6 and ticker.isdigit()):
            continue

        # prdt_type_cd 기반 제외 (KIS CTPF1002R 호환 키)
        prdt_type = row.get("prdt_type_cd", "")
        if prdt_type:
            # prdt_type_cd 존재 시 보통주("300") 만 통과
            if prdt_type not in _ALLOWED_PRODUCT_TYPE_CD:
                continue
        # prdt_type_cd 없을 때는 종목코드 6자리 숫자 패턴 통과 (graceful)

        result.append(row)
    return result


def _classify_market(sm_data: object) -> "str | None":
    """KIS CTPF1002R excg_dvsn_cd 기반 KOSPI/KOSDAQ 분류 (사이클 94 Q42=A 옵션 A).

    "02" = KOSPI / "03" = KOSDAQ / 기타 = None (graceful)

    추가 KIS 호출 0건 — stock_master 캐시 활용 (Q42=A 채택).
    stock_master 부재 종목 = None (사이클 88 G-REJECT 영속 + 사이클 32 R4 universe guard 답습).

    Args:
        sm_data: StockBasics 인스턴스 (또는 None)

    Returns:
        "KOSPI" / "KOSDAQ" / None (graceful — 분류 불가)
    """
    if not sm_data:
        return None
    code = getattr(sm_data, "excg_dvsn_cd", None)
    if not code:
        return None
    code = code.strip()
    if code == "02":
        return "KOSPI"
    if code == "03":
        return "KOSDAQ"
    return None


def _trade_amount_key(row: dict) -> float:
    """거래대금 재정렬 key — `prdy_vol × (stck_prpr - prdy_vrss)`.

    사이클 48 BFB `trade_amt = prdy_vol × (stck_prpr - prdy_vrss)` 패턴 직답습.
    시간 의존 제거 (당일 acml_vol 금지, 전일 확정치 기반).

    Args:
        row: KIS volume_rank output 1건

    Returns:
        전일 거래대금 추정값 (float). 계산 실패 시 0.0 반환 (graceful).
    """
    try:
        prdy_vol = int(row.get("prdy_vol", 0))
        stck_prpr = int(row.get("stck_prpr", 0))
        prdy_vrss = int(row.get("prdy_vrss", 0))
        prdy_close = stck_prpr - prdy_vrss
        if prdy_close <= 0:
            return 0.0
        return float(prdy_vol * prdy_close)
    except (ValueError, TypeError):
        return 0.0


async def _fetch_market_cap_page(
    market: str = "kospi",
    max_pages: int = 100,
) -> list[dict]:
    """KIS market_cap API (FHPST01740000) tr_cont M/N 페이징 누적 (사이클 101).

    KIS 156 API 중 유일 페이징 지원 (사이클 100 Phase 1 영속).
    KIS 정본 인용 (chk_market_cap.py main 호출 영역 정본 L107~120):
      - tr_cont "M" → 재귀 호출 with tr_cont="N"
      - tr_cont "N" or 기타 → 종료

    사이클 38 명문화 영속: tradable_boards 매수 진입 전용 — scanner 단계 영역 한정.
    사이클 88 G-REJECT 영속: rt_cd != "0" → graceful continue (로그만).
    사이클 91 max_pages 무한 루프 차단 패턴 답습.

    KIS market_cap 파라미터 (정본 FHPST01740000):
        fid_cond_mrkt_div_code = "J" (정본 강제 검증 — ValueError if not)
        fid_cond_scr_div_code  = "20174" (정본 강제 검증)
        fid_input_iscd: "0001" = KOSPI(거래소) / "1001" = KOSDAQ
        응답 키: mksc_shrn_iscd (종목코드), data_rank, hts_kor_isnm, stck_avls ...

    Args:
        market: "kospi" 또는 "kosdaq"
        max_pages: 최대 페이지 수 (무한 루프 차단 — 사이클 91 답습). 기본 100.

    Returns:
        누적 ticker 행 list (dict). API 실패 시 [] (graceful, 사이클 88 G-REJECT).
    """
    from src.api.base import kis_get_quote

    input_iscd = _MARKET_CAP_INPUT_ISCD.get(market)
    if not input_iscd:
        logger.warning(
            "[_fetch_market_cap_page] unknown market: %s, fallback to kospi", market
        )
        input_iscd = _MARKET_CAP_INPUT_ISCD["kospi"]

    params = {
        "fid_cond_mrkt_div_code": "J",      # 정본 강제 검증
        "fid_cond_scr_div_code": "20174",   # 정본 강제 검증
        "fid_input_iscd": input_iscd,
        "fid_div_cls_code": "0",
        "fid_blng_cls_code": "0",
        "fid_trgt_cls_code": "0",
        "fid_trgt_exls_cls_code": "0",
        "fid_input_price_1": "",
        "fid_input_price_2": "",
        "fid_vol_cnt": "",
        "fid_input_date_1": "",
    }

    accumulated: list[dict] = []
    tr_cont = ""
    try:
        for _page in range(max_pages):
            data = await kis_get_quote(
                _MARKET_CAP_URL,
                _MARKET_CAP_TR_ID,
                params=params,
                tr_cont=tr_cont,
            )
            if data.get("rt_cd") != "0":
                logger.warning(
                    "[_fetch_market_cap_page] KIS 거부 market=%s rt_cd=%s msg=%s (graceful)",
                    market, data.get("rt_cd"), data.get("msg1"),
                )
                break

            output = data.get("output", []) or []
            accumulated.extend(output)

            # KIS 정본 L107~120: tr_cont "M" → 재호출 with tr_cont="N" / 그 외 → 종료
            next_tr_cont = data.get("tr_cont", "N")
            if next_tr_cont != "M":
                break
            tr_cont = "N"
            # max_pages 도달 시 break (사이클 91 답습)
            # — 루프 상단 range(max_pages) 가드로 자동 차단

    except Exception as e:
        logger.warning(
            "[_fetch_market_cap_page] 예외 market=%s error=%s (graceful)",
            market, e,
        )

    return accumulated


async def _full_universe_load_once(force: bool = False) -> dict:
    """사이클 115 (2026-06-12) — KRX 1차 + KIS 자동 폴백 (Q3=C 영속).

    사용자 결정 영속: Q3=C (KRX OPEN API 1차 우선 + KrxApiError 시 KIS 자동 폴백).

    Q3=C 폴백 패턴 (사이클 88 G-REJECT 영속):
    - KRX 정식 OPEN API (openapi.krx.co.kr) 1차 우선 호출
    - KrxApiError (비활성/401/4xx/5xx/네트워크) 시 KIS market-cap 영역 자동 폴백
    - 양쪽 모두 실패 시 raise (사이클 110 graceful 패턴 영속)

    KRX 1차 영역 (사이클 115 신규):
    - 4 호출 (KOSPI/KOSDAQ × bydd_trd/isu_base_info) + 50ms sleep (KIS LMS chain 안전 답습)
    - bydd_trd: MKTCAP (원 단위, 사이클 108 min_market_cap 직접 정합)
                + ACC_TRDVAL (원 단위, 사이클 108 min_trade_amount 직접 정합)
    - isu_base_info: LIST_DD / SECUGRP_NM / KIND_STKCERT_TP_NM 추가 보강
    - 사이클 81 G-AST1 영속: KIS bfdy_clpr / hts_avls 덮어쓰기 0 (raw JSONB merge)

    KIS 폴백 영역 (사이클 101+109+110 영속):
    - market_cap FHPST01740000 페이징 누적 + CTPF1002R 67컬럼

    Returns:
        summary dict (KRX 성공 시 source="krx", KIS 폴백 시 source="kis_fallback").

    영속 의무 매트릭스:
    - 사이클 38 명문화 (tradable_boards 매수 진입 전용 — scanner 단계 영역만)
    - 사이클 81 G-AST1 (KIS bfdy_clpr / hts_avls 덮어쓰기 0)
    - 사이클 88 G-REJECT (KrxApiError graceful 폴백 의무)
    - 사이클 101 idempotency (24h TTL fresh skip)
    - 사이클 107/108 raw 보강 의존성
    - 사이클 109 KIS market-cap 화이트리스트
    - 사이클 110 graceful 시정 패턴
    """
    from src.api.krx import KrxApiError

    try:
        summary = await _full_universe_load_krx_primary(force=force)
        summary["source"] = "krx"
        return summary
    except KrxApiError as exc:
        logger.warning(
            "[krx_open_api_fallback] KRX 실패 → KIS market-cap 폴백 (graceful): %s",
            exc,
        )
        summary = await _full_universe_load_kis_fallback(force=force)
        summary["source"] = "kis_fallback"
        return summary


async def _full_universe_load_krx_primary(force: bool = False) -> dict:
    """KRX 정식 OPEN API 1차 우선 영역 (사이클 115 신규).

    사용자 결정 영속: Q1=A 양쪽 endpoint 통합 (bydd_trd + isu_base_info).

    호출 영역 (4 호출 + 50ms sleep × 3건):
    1. fetch_stk_bydd_trd(today) — KOSPI 일별 매매정보
    2. fetch_ksq_bydd_trd(today) — KOSDAQ 일별 매매정보
    3. fetch_stk_isu_base_info(today) — KOSPI 종목 기본정보
    4. fetch_ksq_isu_base_info(today) — KOSDAQ 종목 기본정보

    Rate Limit: 50ms sleep × 3건 (KIS LMS chain 안전 마진 답습, 사이클 17 영속).

    stock_master upsert 영역 (raw JSONB merge):
    - bydd_trd → ticker(ISU_CD) / name(ISU_NM) / market(MKT_NM)
                  raw 추가: MKTCAP(원 단위) + ACC_TRDVAL(원 단위) + LIST_SHRS + TDD_CLSPRC
    - isu_base_info → 동일 ticker(ISU_SRT_CD) 매핑
                  raw 추가: LIST_DD + SECUGRP_NM + KIND_STKCERT_TP_NM
    - 사이클 81 G-AST1 영속: KIS bfdy_clpr / hts_avls 덮어쓰기 0

    Returns:
        summary dict 9 키 (사이클 89/108 collector 패턴 답습):
        total / kospi / kosdaq / securities / etf / fetched / skipped_ttl / failed / elapsed_ms

    Raises:
        KrxApiError: 호출자 (_full_universe_load_once) 가 KIS 폴백 의무.
    """
    import time as _t

    from src.api.krx import (
        fetch_stk_bydd_trd,
        fetch_ksq_bydd_trd,
        fetch_stk_isu_base_info,
        fetch_ksq_isu_base_info,
    )
    from src.db._kst import today_kst
    from src.db.stock_master import is_stale as _sm_is_stale, upsert_one as _sm_upsert
    from src.models.stock import StockBasics

    from datetime import timedelta

    from src.api.krx import KrxApiError as _KrxApiError

    start_ts = _t.monotonic()

    # 사이클 117 (2026-06-12) — basDd 전일 영업일 영역 + 빈 응답 시 최대 7일 재시도.
    # 근본 원인: KRX 일별 매매정보 = 영업일 종료 후 (~16:00 KST) 가용. 금일 영역 호출 시 빈 list.
    # 시정: today - 1 day 시작 + 빈 응답 시 -1 day 재시도 (공휴일/주말 자동 회피).
    # max_attempts=7 후 모두 0건 → KrxApiError raise → 호출자 _full_universe_load_once 가 KIS 폴백.
    base_date = today_kst() - timedelta(days=1)
    max_attempts = 7
    basdd = ""
    kospi_trd: list[dict] = []
    kosdaq_trd: list[dict] = []
    for _attempt in range(max_attempts):
        basdd = base_date.strftime("%Y%m%d")
        kospi_trd = await fetch_stk_bydd_trd(basdd)
        await _asyncio.sleep(0.05)
        kosdaq_trd = await fetch_ksq_bydd_trd(basdd)
        if kospi_trd or kosdaq_trd:
            break  # 데이터 확보
        # 빈 응답 → 직전 영업일 영역 재시도 (사이클 117 사용자 결정 영속)
        logger.info(
            "[krx_empty_response] basDd=%s 빈 응답 → 직전 영업일 재시도 (attempt=%d/%d)",
            basdd, _attempt + 1, max_attempts,
        )
        base_date -= timedelta(days=1)
        await _asyncio.sleep(0.05)
    else:
        # 7일 모두 0건 → KIS 폴백 trigger
        raise _KrxApiError(
            f"KRX 7일 영역 빈 응답 (최후 basDd={basdd}) — KIS 폴백 의무"
        )

    await _asyncio.sleep(0.05)
    kospi_info = await fetch_stk_isu_base_info(basdd)
    await _asyncio.sleep(0.05)
    kosdaq_info = await fetch_ksq_isu_base_info(basdd)

    # isu_base_info → ticker 매핑 dict (KOSPI + KOSDAQ 통합)
    # ISU_SRT_CD = 단축코드 6자리 (KRX 종목코드 정합)
    info_map: dict[str, dict] = {}
    for info_row in kospi_info + kosdaq_info:
        ticker = info_row.get("ISU_SRT_CD", "")
        if len(ticker) == 6 and ticker.isdigit():
            info_map[ticker] = info_row

    # bydd_trd 통합 (KOSPI + KOSDAQ) + 6자리 ticker 가드
    all_trd_rows = kospi_trd + kosdaq_trd
    total = len(all_trd_rows)
    kospi_count = len(kospi_trd)
    kosdaq_count = len(kosdaq_trd)
    fetched = 0
    skipped_ttl = 0
    failed = 0

    for trd_row in all_trd_rows:
        # ISU_CD = bydd_trd 의 단축코드 6자리 (KRX 종목코드 정합)
        ticker = trd_row.get("ISU_CD", "")
        if not (len(ticker) == 6 and ticker.isdigit()):
            continue

        # 24h TTL fresh skip (사이클 83 + 사이클 101 영속).
        # 사이클 120: force=True 시 TTL 우회 (사용자 강제 새로고침, 사이클 116/118/119 매핑 영역 즉시 검증).
        if not force:
            try:
                stale = await _sm_is_stale(ticker, max_age_hours=24)
            except Exception:
                stale = True  # graceful — 판별 실패 시 갱신 시도

            if not stale:
                skipped_ttl += 1
                await _asyncio.sleep(0)  # yield
                continue

        # KRX bydd_trd + isu_base_info merge → raw JSONB
        # 사이클 81 G-AST1 영속: KIS bfdy_clpr / hts_avls 덮어쓰기 금지 (KRX 키는 신규 영역)
        krx_raw: dict[str, Any] = {}
        # bydd_trd 추가 (사이클 108 min_market_cap / min_trade_amount 직접 정합 영역)
        for key in ("MKTCAP", "ACC_TRDVAL", "LIST_SHRS", "TDD_CLSPRC", "TDD_OPNPRC",
                    "TDD_HGPRC", "TDD_LWPRC", "ACC_TRDVOL", "FLUC_RT", "MKT_NM",
                    "SECT_TP_NM"):
            if key in trd_row:
                krx_raw[key] = trd_row[key]
        # 사이클 116 — KRX MKTCAP (원 단위) → KIS hts_avls (백만원 단위) 환산 매핑.
        # 사이클 108 list_by_filter (`hts_avls × 1_000_000 ≥ min_market_cap`) 정합 영속.
        # 사이클 81 G-AST1 영속: KIS market-cap 호출 시점은 KRX 폴백 분기 = 동일 ticker
        # 양쪽 키 충돌 0 (KRX 1차 성공 시 KIS 호출 부재).
        if "MKTCAP" in trd_row:
            try:
                mktcap_won = int(str(trd_row["MKTCAP"]).replace(",", "") or 0)
                if mktcap_won > 0:
                    krx_raw["hts_avls"] = mktcap_won // 1_000_000  # 원 → 백만원
            except (ValueError, TypeError):
                pass  # graceful, MKTCAP raw 만 유지
        # 사이클 118 — KRX ACC_TRDVAL (원 단위) → KIS acml_tr_pbmn (원 단위, 동일) 매핑.
        # 사이클 108 list_by_filter (`acml_tr_pbmn ≥ min_trade_amount`) 정합 영속.
        # 사이클 107 raw 보강 (CTPF1002R + FHKST01010100 merge) 영역의 acml_tr_pbmn 키와 정합.
        # 사이클 116 답습 패턴 (KRX → KIS 정합 키 매핑).
        # 운영 실측 (2026-06-12 cycle118 진단): acml_tr_pbmn_present 2.85% → 99%+ 정상화 의무.
        if "ACC_TRDVAL" in trd_row:
            try:
                trdval_won = int(str(trd_row["ACC_TRDVAL"]).replace(",", "") or 0)
                if trdval_won > 0:
                    krx_raw["acml_tr_pbmn"] = trdval_won  # 원 단위 동일
            except (ValueError, TypeError):
                pass  # graceful, ACC_TRDVAL raw 만 유지
        # 사이클 119 — KRX → KIS 정합 키 전수 매핑 확장 (4 키 추가).
        # 사용자 보고 (2026-06-12 정밀 진단): bfdy_clpr / lstn_stcn / acml_vol / prdy_vrss 영역
        # KRX 1차 적재 종목 (97%) 부재 → UI / 필터 / 매수 신호 영역 "내용 안 채워짐" 결함.
        # basDd=어제 (사이클 117) → KRX TDD_CLSPRC = 어제 종가 = 오늘 기준 KIS bfdy_clpr (전일 종가) 정합.
        # 사이클 116/118 답습 패턴. 사이클 81 G-AST1 영속: KRX 1차 시 KIS 호출 부재 → 충돌 0.
        if "TDD_CLSPRC" in trd_row:
            try:
                clpr_won = int(str(trd_row["TDD_CLSPRC"]).replace(",", "") or 0)
                if clpr_won > 0:
                    krx_raw["bfdy_clpr"] = clpr_won  # 원 단위 동일
            except (ValueError, TypeError):
                pass  # graceful
        if "LIST_SHRS" in trd_row:
            try:
                shrs = int(str(trd_row["LIST_SHRS"]).replace(",", "") or 0)
                if shrs > 0:
                    krx_raw["lstn_stcn"] = shrs  # 정수 동일 (상장 주식수)
            except (ValueError, TypeError):
                pass
        if "ACC_TRDVOL" in trd_row:
            try:
                vol = int(str(trd_row["ACC_TRDVOL"]).replace(",", "") or 0)
                if vol > 0:
                    krx_raw["acml_vol"] = vol  # 정수 동일 (누적 거래량)
            except (ValueError, TypeError):
                pass
        if "CMPPREVDD_PRC" in trd_row:
            try:
                # 사이클 119 — prdy_vrss 영역 = 전일 대비 (음수 허용) — > 0 가드 제외.
                vrss = int(str(trd_row["CMPPREVDD_PRC"]).replace(",", "") or 0)
                krx_raw["prdy_vrss"] = vrss  # 원 단위 동일 (음수 가능)
            except (ValueError, TypeError):
                pass
        # isu_base_info 보강 (LIST_DD / SECUGRP_NM / KIND_STKCERT_TP_NM)
        info_row = info_map.get(ticker, {})
        for key in ("LIST_DD", "SECUGRP_NM", "KIND_STKCERT_TP_NM",
                    "ISU_ABBRV", "ISU_ENG_NM", "PARVAL", "MKT_TP_NM"):
            if key in info_row:
                krx_raw[key] = info_row[key]

        # stock_master upsert (사이클 84 history trigger 영속)
        # 사이클 88 G-REJECT 영속: 개별 ticker 실패 → continue + failed++
        try:
            name = trd_row.get("ISU_NM") or info_row.get("ISU_NM") or ticker
            # MKT_NM → excg_dvsn_cd 매핑 ("KOSPI" → "02", "KOSDAQ" → "03")
            mkt_nm = trd_row.get("MKT_NM", "")
            if "KOSDAQ" in mkt_nm:
                excg = "03"
            elif "KOSPI" in mkt_nm or "유가증권" in mkt_nm:
                excg = "02"
            else:
                excg = ""

            basics = StockBasics(
                ticker=ticker,
                name=name,
                excg_dvsn_cd=excg,
                nxt_tradable=False,  # KRX 영역은 NXT 정보 부재 — 보수적 False (lazy upsert 시 KIS CTPF1002R 보강)
                krx_halted=False,
                admin_item=False,
                raw=krx_raw,
            )
            await _sm_upsert(basics)
            fetched += 1
        except Exception as e:
            logger.warning(
                "[_full_universe_load_krx_primary] upsert 실패 ticker=%s error=%s (graceful)",
                ticker, e,
            )
            failed += 1

    elapsed_ms = int((_t.monotonic() - start_ts) * 1000)

    summary = {
        "total": total,
        "kospi": kospi_count,
        "kosdaq": kosdaq_count,
        "securities": total,  # KRX bydd_trd 는 prdt_type_cd 부재 — total 영역
        "etf": 0,  # KRX 영역 ETF 분류 부재 (사이클 116+ isu_base_info SECUGRP_NM 활용 가능)
        "fetched": fetched,
        "skipped_ttl": skipped_ttl,
        "failed": failed,
        "elapsed_ms": elapsed_ms,
    }
    return summary


async def _full_universe_load_kis_fallback(force: bool = False) -> dict:
    """KIS market-cap 폴백 영역 (사이클 101+109+110 영속, 함수 본체 추출).

    사이클 115 (2026-06-12) — 사이클 101+109+110 영역 영구 영속 추출 (행위 변경 0).
    Q3=C 폴백 영역 — KRX 실패 시 _full_universe_load_once 가 자동 호출.

    매일 20:00:05 scheduler 에서 1회 호출 (Q67=B). KOSPI + KOSDAQ market_cap 페이징
    누적 → 종목별 CTPF1002R 67컬럼 조회 → stock_master upsert. 사이클 97/99
    fluctuation 영구 폐기 (Q68=A) + _universe_eager_refresh_loop 영구 폐기 (Q69=B)
    이후 단일 대체 영역.

    KIS 정본 인용 (chk_market_cap.py + chk_search_stock_info.py / CTPF1002R):
    - FHPST01740000: tr_cont "M"→"N" 페이징 누적 (_fetch_market_cap_page 참조)
    - CTPF1002R: 67컬럼 응답 dict (단일 종목, output은 dict not list)
      bfdy_clpr (전일종가, 사이클 81 정본 키 영속)

    사이클 38 명문화 영속: tradable_boards 매수 진입 전용.
    사이클 88 G-REJECT 영속: 개별 ticker 실패 → continue + failed++.
    사이클 84 history trigger 영속: upsert_one 호출 → DB trigger 자동.
    사이클 83 24h TTL fresh skip (is_stale 호출).

    환경 분리 Rate Limit (domain-expert A3):
    - 실전(real): _FULL_UNIVERSE_SLEEP_REAL(50ms) + max _FULL_UNIVERSE_MAX_LOAD_SECONDS_REAL(300s)
    - 모의(vts): _FULL_UNIVERSE_SLEEP_VTS(200ms) + max _FULL_UNIVERSE_MAX_LOAD_SECONDS_VTS(600s)

    Returns:
        summary dict 9 키 (사이클 74/89 collector 패턴 답습):
        total / kospi / kosdaq / securities / etf / fetched / skipped_ttl / failed / elapsed_ms

    영속 의무:
    - 사이클 38 명문화 (tradable_boards 매수 진입 전용 — scanner 단계 영역만)
    - 사이클 83 24h TTL fresh skip 영속 (is_stale 호출)
    - 사이클 84 history trigger 영속 (upsert_one 호출)
    - 사이클 88 G-REJECT 영속 (개별 실패 graceful continue)
    - 사이클 101 KIS 정본 인용 (chk_market_cap.py + CTPF1002R)
    """
    import time as _t
    from src.config import settings as _settings

    # 환경 분리 Rate Limit (domain-expert A3)
    is_real = getattr(_settings, "kis_env", "vts").lower() == "real"
    _sleep_secs = _FULL_UNIVERSE_SLEEP_REAL if is_real else _FULL_UNIVERSE_SLEEP_VTS
    _max_secs = _FULL_UNIVERSE_MAX_LOAD_SECONDS_REAL if is_real else _FULL_UNIVERSE_MAX_LOAD_SECONDS_VTS

    start_ts = _t.monotonic()

    # --- Phase 1: market_cap 페이징 누적 (KOSPI + KOSDAQ) ---
    kospi_rows = await _fetch_market_cap_page(market="kospi", max_pages=100)
    kosdaq_rows = await _fetch_market_cap_page(market="kosdaq", max_pages=100)
    all_rows = kospi_rows + kosdaq_rows

    # ETF/리츠/SPAC 분류 (prdt_type_cd 기반 보통주 "300" 만 통과)
    # CTPF1002R 조회 전 단계 — market_cap 응답은 prdt_type_cd 없을 수 있으므로 graceful
    securities_rows = _universe_filter_securities_only(all_rows)
    etf_count = len(all_rows) - len(securities_rows)

    total = len(all_rows)
    kospi_count = len(kospi_rows)
    kosdaq_count = len(kosdaq_rows)
    securities_count = len(securities_rows)
    fetched = 0
    skipped_ttl = 0
    failed = 0

    # --- Phase 2: 종목별 CTPF1002R + stock_master upsert ---
    from src.db.stock_master import is_stale as _sm_is_stale, upsert_one as _sm_upsert
    from src.api.condition import inquire_stock_basics as _inquire_basics

    for row in all_rows:
        # 시간 초과 가드 (정산 race 차단)
        if _t.monotonic() - start_ts > _max_secs:
            logger.warning(
                "[_full_universe_load_once] max_load_seconds=%d 초과 — 중단 (fetched=%d, remaining=%d)",
                _max_secs, fetched, len(all_rows) - fetched - skipped_ttl - failed,
            )
            break

        ticker = row.get("mksc_shrn_iscd", "")
        if not (len(ticker) == 6 and ticker.isdigit()):
            continue

        # 24h TTL fresh skip (사이클 83 Q3=B 답습).
        # 사이클 120: force=True 시 TTL 우회 (사용자 강제 새로고침 영역).
        if not force:
            try:
                stale = await _sm_is_stale(ticker, max_age_hours=24)
            except Exception:
                stale = True  # graceful — 판별 실패 시 갱신 시도

            if not stale:
                skipped_ttl += 1
                await _asyncio.sleep(0)  # yield
                continue

        # KIS CTPF1002R 호출 → upsert (사이클 88 G-REJECT 영속)
        try:
            basics = await _inquire_basics(ticker)
            await _sm_upsert(basics)
            fetched += 1
        except Exception as e:
            logger.warning(
                "[_full_universe_load_once] CTPF1002R 실패 ticker=%s error=%s (graceful)",
                ticker, e,
            )
            failed += 1

        # 환경 분리 Rate Limit sleep (domain-expert A3)
        await _asyncio.sleep(_sleep_secs)

    elapsed_ms = int((_t.monotonic() - start_ts) * 1000)

    summary = {
        "total": total,
        "kospi": kospi_count,
        "kosdaq": kosdaq_count,
        "securities": securities_count,
        "etf": etf_count,
        "fetched": fetched,
        "skipped_ttl": skipped_ttl,
        "failed": failed,
        "elapsed_ms": elapsed_ms,
    }
    return summary


def _emit_stock_master_age_warning(ticker: str, age_days: int) -> None:
    """사이클 101 domain-expert A5 — 7일 이상 stale WARNING emit.

    사이클 89 적시성 손실 보강: 매일 20:00:05 단독 적재 영역 = 신규 IPO 영역 부재 위험.
    7일 이상 stock_master 미갱신 종목 → 운영자 알림.

    Args:
        ticker: 종목코드
        age_days: stock_master 마지막 적재 이후 경과 일수

    emit prefix: [stock_master_age_warning] ticker=X age_days=Z
    """
    if age_days < 7:
        return
    logger.warning(
        "[stock_master_age_warning] ticker=%s age_days=%d (사이클 101 domain-expert A5 영속)",
        ticker, age_days,
    )


# ---------------------------------------------------------------------------
# Q68=A (사이클 101) 영구 폐기: fetch_top_500_universe + _universe_eager_refresh_loop
# KIS fluctuation API (FHPST01700000) 영역 전수 폐기 — 사이클 97/99 이전 영역.
# 사이클 97~99 테스트 = xfail 의미 전환 (과거 영속 보존, 사이클 66 K-2 패턴 답습).
# ---------------------------------------------------------------------------
# NOTE: fetch_top_500_universe() 와 _universe_eager_refresh_loop() 는
# 사이클 101 Q68=A/Q69=B 에 의해 영구 폐기. 해당 테스트는 xfail 마킹.
# ---------------------------------------------------------------------------

# (아래 영역은 사이클 101 이전 fetch_top_500_universe() 과 _universe_eager_refresh_loop()
# 가 위치했던 자리. Q68=A + Q69=B 폐기 완료.)


# ---------------------------------------------------------------------------
# 사이클 89 이하: _universe_filter_securities_only (사이클 95 영속) 이하 기존 영역
# ---------------------------------------------------------------------------

# (사이클 101 Q68=A+Q69=B 에 의해 fetch_top_500_universe/
# _universe_eager_refresh_loop 영구 폐기 완료.)


# ---------------------------------------------------------------------------
# 사이클 122 (2026-06-12) — KIS 일봉 (FHKST03010100) stock_master_daily 적재
# 사용자 결정 영속:
#   Q1=A 매일 16:00 KST 일괄 적재
#   Q2=C T-100일 (KIS 1회 호출 한도 활용)
#   Q3=B 점진 적재 (사이클 122 백필 + 사이클 123+ 증분)
#   Q4=B DB 적재만 (전략 전환은 사이클 123+ 별개)
#
# 영속 의무:
# - 사이클 14 fetch_daily_candles 재사용 (신규 KIS API 도입 0건)
# - 사이클 17 OPSP0002 backoff + Rate Limit 50ms sleep
# - 사이클 38 명문화 (scanner 매수 진입 전 영역)
# - 사이클 81 G-AST1 raw JSONB 보존
# - 사이클 88 G-REJECT graceful (개별 ticker 실패 시 다음 ticker 진행)
# - 사이클 101 lifecycle 의존성 (stock_master 적재 *후* 일봉 적재)
# - 사이클 106 lifecycle race 차단 패턴
# ---------------------------------------------------------------------------
_DAILY_LOAD_FETCH_DAYS = 100   # KIS 1회 호출 한도 (Q2=C, 사이클 33 KIS_DAILY_CANDLES_MAX)
_DAILY_LOAD_RATE_LIMIT_SLEEP_SECS = 0.05  # 50ms (사이클 83/91/97/107 답습)
_DAILY_LOAD_INCREMENTAL_THRESHOLD = 50  # 50일 이상 적재된 ticker 는 증분 적재 (Q3=B)


async def _stock_master_daily_load_once(force: bool = False) -> dict:
    """사이클 122 — stock_master 전체 ticker 의 일봉을 stock_master_daily 에 적재.

    사용자 결정 Q3=B 점진 적재:
    - max_bas_dd 가 오늘이면 skip (idempotency)
    - count_by_ticker(ticker) < 50 → 백필 모드 (T-100일 전수, KIS 1회)
    - count_by_ticker(ticker) >= 50 → 증분 모드 (T-7일만 fetch, 영업일 마진)

    Returns:
        summary dict: {total, fetched, upserted_rows, skipped_fresh, failed,
                       elapsed_ms, mode}
    """
    import time
    from src.db import stock_master, stock_master_daily

    start = time.monotonic()
    summary: dict = {
        "total": 0,
        "fetched": 0,
        "upserted_rows": 0,
        "skipped_fresh": 0,
        "failed": 0,
        "elapsed_ms": 0,
        "mode": "mixed",  # 백필/증분 혼합
    }

    # stock_master 전체 ticker 조회 (사이클 106 lifecycle 의존성)
    # offset 페이징 — limit=1000 단위 (Supabase 기본 한도)
    all_tickers: list[str] = []
    page = 0
    PAGE_SIZE = 1000
    while True:
        try:
            rows = await stock_master.list_all(limit=PAGE_SIZE, offset=page * PAGE_SIZE)
        except Exception:
            logger.exception(
                "[stock_master_daily_load] stock_master.list_all 실패 graceful page=%d",
                page,
            )
            break
        if not rows:
            break
        for row in rows:
            ticker = row.get("ticker", "")
            if ticker and len(ticker) == 6 and ticker.isdigit():
                all_tickers.append(ticker)
        if len(rows) < PAGE_SIZE:
            break
        page += 1

    summary["total"] = len(all_tickers)
    if not all_tickers:
        summary["elapsed_ms"] = int((time.monotonic() - start) * 1000)
        logger.warning("[stock_master_daily_load] stock_master 빈 영역 — 적재 skip")
        return summary

    # 오늘 KST 날짜 (점진 적재 fresh skip 기준)
    from src.db._kst import today_kst
    today = today_kst()

    backfill_count = 0
    incremental_count = 0

    for idx, ticker in enumerate(all_tickers):
        # 1) 점진 적재 idempotency — max_bas_dd 가 오늘이면 skip (force 시 무시)
        try:
            latest = await stock_master_daily.max_bas_dd(ticker)
        except Exception:
            latest = None

        if not force and latest is not None and latest >= today:
            summary["skipped_fresh"] += 1
            continue

        # 2) 백필 vs 증분 결정 (Q3=B 사용자 결정 영속)
        try:
            existing_count = await stock_master_daily.count_by_ticker(ticker)
        except Exception:
            existing_count = 0

        if existing_count < _DAILY_LOAD_INCREMENTAL_THRESHOLD:
            fetch_days = _DAILY_LOAD_FETCH_DAYS  # 백필 모드 (T-100일)
            backfill_count += 1
        else:
            fetch_days = 7  # 증분 모드 (T-7일, 영업일 마진)
            incremental_count += 1

        # 3) KIS fetch_daily_candles 호출 (사이클 14 재사용)
        try:
            from src.api.condition import fetch_daily_candles
            candles = await fetch_daily_candles(ticker, days=fetch_days)
        except Exception:
            # 사이클 88 G-REJECT graceful — 다음 ticker 진행
            logger.exception(
                "[stock_master_daily_load] KIS fetch_daily_candles 실패 graceful ticker=%s",
                ticker,
            )
            summary["failed"] += 1
            # Rate Limit sleep 보장 (실패 시도 자체로 KIS 호출 발생)
            await asyncio.sleep(_DAILY_LOAD_RATE_LIMIT_SLEEP_SECS)
            continue

        if not candles:
            summary["failed"] += 1
            await asyncio.sleep(_DAILY_LOAD_RATE_LIMIT_SLEEP_SECS)
            continue

        summary["fetched"] += 1

        # 4) DB batch upsert (사이클 88 G-REJECT graceful 내장)
        try:
            upserted = await stock_master_daily.upsert_batch(ticker, candles)
            summary["upserted_rows"] += upserted
        except Exception:
            logger.exception(
                "[stock_master_daily_load] upsert_batch 실패 graceful ticker=%s",
                ticker,
            )
            summary["failed"] += 1

        # 5) Rate Limit sleep (사이클 17/83/91/97/107 답습)
        await asyncio.sleep(_DAILY_LOAD_RATE_LIMIT_SLEEP_SECS)

        # 진행 상황 emit — 500건마다 (운영 가시화)
        if (idx + 1) % 500 == 0:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.info(
                "[stock_master_daily_load] 진행 %d/%d fetched=%d upserted=%d "
                "skipped_fresh=%d failed=%d elapsed_ms=%d",
                idx + 1, len(all_tickers),
                summary["fetched"], summary["upserted_rows"],
                summary["skipped_fresh"], summary["failed"], elapsed,
            )

    summary["elapsed_ms"] = int((time.monotonic() - start) * 1000)
    # mode 결정: 백필 우세 → "full" / 증분 우세 → "incremental" / 혼합 → "mixed"
    if backfill_count > 0 and incremental_count == 0:
        summary["mode"] = "full"
    elif incremental_count > 0 and backfill_count == 0:
        summary["mode"] = "incremental"
    else:
        summary["mode"] = "mixed"

    return summary
