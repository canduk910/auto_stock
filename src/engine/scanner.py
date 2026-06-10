"""종목 필터링 모듈.

등락률 순위 API 결과에서 당일 급등 종목(15%+ 상승)을 필터링하고,
시총/거래대금 조건을 추가 적용한 뒤 WebSocket 실시간 시세 구독을 등록한다.

매수 조건이 시가 대비 +29.5%이므로, 이미 15% 이상 상승 중인 종목을
후보군으로 잡아 29.5% 도달을 감시한다.
"""

from __future__ import annotations

import asyncio
import asyncio as _asyncio  # 사이클 97 — _fetch_fluctuation Rate Limit sleep patch 호환
import logging
import sys as _sys
import time as _monotonic_time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

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
# fluctuation 영역 = fid_input_cnt_1 사용자 제어 + tr_cont 페이징 영속
# ---------------------------------------------------------------------------
# 영속 의무:
# - 사이클 38 명문화: tradable_boards 매수 진입 전용 (매도 hot path 영향 0)
# - 사이클 64 protected_tickers: 영역 분리 (영향 0)
# - 사이클 81 bfdy_clpr: 영역 분리 (영향 0)
# - 사이클 83 scan_pool eager refresh: candidates=12 영역 영속 (영역 분리)
# - 사이클 89 ETF 제외 + 거래대금 정렬: fluctuation 영역으로 흡수
# - 사이클 91 페이징: fluctuation 영역 적용 (tr_cont "" → "N")
# - 사이클 96 KOSPI/KOSDAQ 분리 호출: fluctuation 영역으로 흡수
# ---------------------------------------------------------------------------

# 사이클 97 — KIS fluctuation API (FHPST01700000) 상수
_FLUCTUATION_URL = "/uapi/domestic-stock/v1/ranking/fluctuation"
_FLUCTUATION_TR_ID = "FHPST01700000"

# fid_input_iscd 매핑 (KIS 정본: "0001" = KOSPI 업종, "0002" = KOSDAQ 업종)
_FLUCTUATION_MARKET_INPUT_ISCD: dict[str, str] = {
    "kospi": "0001",
    "kosdaq": "0002",
}

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


async def _fetch_fluctuation(
    market: str = "kospi",
    top_n: int = 250,
    max_pages: int = 17,
) -> list[dict]:
    """KIS fluctuation API (FHPST01700000) 페이징 누적 호출 (사이클 97 영역 신규).

    사이클 97 (2026-06-10) — KIS volume_rank (사이클 89/91/94/96) 영역 전수 폐기 영구 시정.
    fluctuation 영역 = fid_input_cnt_1 사용자 제어 + tr_cont 페이징 영속.

    Args:
        market: "kospi" or "kosdaq" (사이클 96 명명 영속)
        top_n: 각 업종 최대 ticker (기본 250, 사이클 89 영속)
        max_pages: 페이지 안전 마진 (기본 17, 사이클 91 영속)

    Returns:
        KIS output list (dict). API 실패 시 누적분 graceful 반환. 빈 경우 [].

    영속 의무:
    - 사이클 89 거래대금 정렬 (_trade_amount_key) + ETF 제외 (_universe_filter_securities_only) 영속
    - 사이클 91 페이징 누적 (tr_cont "" → "N") 영속
    - 사이클 95 unknown=0 graceful 영속 (KIS API 분류 자체)
    - 사이클 83 Rate Limit 50ms sleep
    - KIS 정본 페이징 패턴 (open-trading-api/examples_llm/.../fluctuation.py)

    KIS fluctuation 파라미터 (정본 FHPST01700000):
        FID_COND_MRKT_DIV_CODE = "J"     (KRX 전체)
        FID_COND_SCR_DIV_CODE  = "20170" (강제 검증 — KIS ValueError 방지)
        FID_INPUT_ISCD         = "0001" (KOSPI) / "0002" (KOSDAQ)
        FID_RANK_SORT_CLS_CODE = "0000"  (등락률순)
        FID_INPUT_CNT_1        = str(top_n)  (사용자 제어 영역 — 핵심)
        FID_PRC_CLS_CODE       = "0"     (전체)
        FID_INPUT_PRICE_1/2    = ""      (전체 가격대)
        FID_VOL_CNT            = ""      (전체 거래량)
        FID_TRGT_CLS_CODE      = "0"     (대상 구분)
        FID_TRGT_EXLS_CLS_CODE = "0"     (대상 제외)
        FID_DIV_CLS_CODE       = "0"     (전체)
        FID_RSFL_RATE1/2       = ""      (전체 등락률)

    응답 키 (KIS chk_fluctuation.py COLUMN_MAPPING 정본):
        stck_shrn_iscd  — 주식 단축 종목코드 (volume_rank mksc_shrn_iscd 와 영역 차별)
        stck_prpr / prdy_vrss / prdy_ctrt / acml_vol / prdy_vol / ...
    """
    from src.api.base import KisApiError, kis_get_quote

    # "kospi" → "0001", "kosdaq" → "0002" (fallback = "0001" KOSPI 보수적)
    input_iscd = _FLUCTUATION_MARKET_INPUT_ISCD.get(market)
    if not input_iscd:
        logger.warning(
            "[_fetch_fluctuation] unknown market: %s, fallback to kospi", market
        )
        input_iscd = _FLUCTUATION_MARKET_INPUT_ISCD["kospi"]

    accumulated: list[dict] = []
    tr_cont = ""  # 초기 호출 (KIS 표준 — 빈 문자열 = 첫 페이지)

    for page in range(max_pages):
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20170",   # KIS 정본 강제 검증 영역
            "FID_INPUT_ISCD": input_iscd,
            "FID_RANK_SORT_CLS_CODE": "0000",   # 등락률순
            "FID_INPUT_CNT_1": str(top_n),       # 사이클 97 핵심: 사용자 영구 제어
            "FID_PRC_CLS_CODE": "0",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_TRGT_CLS_CODE": "0",
            "FID_TRGT_EXLS_CLS_CODE": "0",
            "FID_DIV_CLS_CODE": "0",
            "FID_RSFL_RATE1": "",
            "FID_RSFL_RATE2": "",
        }
        try:
            data = await kis_get_quote(
                _FLUCTUATION_URL,
                _FLUCTUATION_TR_ID,
                params=params,
                tr_cont=tr_cont,
            )
            output = data.get("output", []) or []
            accumulated.extend(output)

            # 누적 건수가 top_n 이상이면 조기 종료 (효율)
            if len(accumulated) >= top_n:
                break

            # 응답 헤더 tr_cont 추출 (다음 페이지 존재 여부)
            next_tr_cont = data.get("_response_headers", {}).get("tr_cont", "")
            if next_tr_cont != "M":
                break  # 마지막 페이지

            tr_cont = "N"  # 다음 페이지 호출 (KIS 표준 — "N" = Next)
            await _asyncio.sleep(0.05)  # 사이클 83 Rate Limit 50ms sleep 영속
        except KisApiError as e:
            logger.warning(
                "[fetch_fluctuation] KIS API 실패 market=%s page=%d error=%s (graceful 누적분 반환)",
                market, page, e,
            )
            break
        except Exception as e:
            logger.warning(
                "[fetch_fluctuation] 예외 market=%s page=%d error=%s (graceful 누적분 반환)",
                market, page, e,
            )
            break

    return list(accumulated[:top_n])


async def fetch_top_500_universe() -> list[str]:
    """KOSPI 250 + KOSDAQ 250 = 500 ticker 적재 (사이클 97 fluctuation 영역 신규 도입).

    사이클 97 (2026-06-10) — KIS fluctuation API (FHPST01700000) 영역 신규 도입.
    사이클 89/91/94/96 volume_rank 영역 전수 폐기 (단일 페이지 30 한도 + 페이징 미지원).

    사용자 결정 영속:
    - Q52=A: KIS fluctuation API (FHPST01700000) 신규 도입
    - Q53=A: 사이클 89/91/94/96 전수 폐기
    - KOSPI 250 + KOSDAQ 250 분리 호출 (사이클 96 영속, fluctuation 영역으로 흡수)

    개장 전 1회 적재 (Q20=D + 사이클 83 5분 주기 결합).
    ETF/리츠/SPAC 자동 제외 (`_universe_filter_securities_only`).

    Returns:
        종목코드 list (최대 500건, 보통주만). API 실패 시 [] (graceful).

    영속 의무:
    - 사이클 38 명문화 (tradable_boards 매수 진입 전용 — 영향 0)
    - 사이클 48 BFB 거래대금 재정렬 패턴 답습 (_trade_amount_key)
    - 사이클 64 protected_tickers (영역 분리, 영향 0)
    - 사이클 83 scan_pool eager refresh 영속 (영역 분리)
    - 사이클 88 G-REJECT 영속 (외부 LLM 영구 차단 AST 가드 3)
    - 사이클 89 ETF 제외 + 거래대금 정렬 (fluctuation 영역으로 흡수)
    - 사이클 91 페이징 영속 (fluctuation 영역 적용, tr_cont)
    - 사이클 93 chain 영속 (호출 chain 변경 0)
    - 사이클 95 unknown=0 영속 (2회 분리 호출 = unknown 불필요)
    - 사이클 96 KOSPI/KOSDAQ 분리 호출 (fluctuation 영역으로 흡수)
    """
    import time as _t
    from src.engine.stock_master_metrics import record_universe_refresh, flush_universe_collector

    start_ms = _t.monotonic() * 1000

    # 사이클 97 — fluctuation API 2회 분리 호출 (KOSPI + KOSDAQ)
    # 사이클 89/91/94/96 volume_rank 영역 전수 폐기
    kospi_raw = await _fetch_fluctuation(market="kospi", top_n=250)
    kosdaq_raw = await _fetch_fluctuation(market="kosdaq", top_n=250)

    # 사이클 89 ETF 제외 영속 — fluctuation 영역으로 흡수
    kospi_filtered = _universe_filter_securities_only(kospi_raw)
    kosdaq_filtered = _universe_filter_securities_only(kosdaq_raw)

    # 사이클 89 거래대금 desc 재정렬 영속 (사이클 48 BFB 패턴 답습)
    kospi_sorted = sorted(kospi_filtered, key=_trade_amount_key, reverse=True)[:250]
    kosdaq_sorted = sorted(kosdaq_filtered, key=_trade_amount_key, reverse=True)[:250]

    etf_excluded_total = (
        (len(kospi_raw) - len(kospi_filtered)) +
        (len(kosdaq_raw) - len(kosdaq_filtered))
    )

    # 사이클 95 unknown=0 영속 — 2회 분리 호출 = unknown 분류 불필요
    universe_rows = kospi_sorted + kosdaq_sorted

    # 사이클 97 — 응답 ticker 키: stck_shrn_iscd (KIS chk_fluctuation.py 정본)
    # volume_rank mksc_shrn_iscd 와 영역 차별 — 영구 시정
    tickers = [row["stck_shrn_iscd"] for row in universe_rows if row.get("stck_shrn_iscd")]
    tickers = tickers[:500]

    elapsed_ms = int(_t.monotonic() * 1000 - start_ms)
    securities_count = len(tickers)
    universe_size = len(tickers)

    # [stock_master_bulk_refresh] 개장 전 1회 emit (사이클 95 unknown=0 영속)
    logger.info(
        "[stock_master_bulk_refresh] universe=%d kospi=%d kosdaq=%d unknown=0 "
        "securities=%d etf_excluded=%d elapsed_ms=%d",
        universe_size,
        len(kospi_sorted),
        len(kosdaq_sorted),
        securities_count,
        etf_excluded_total,
        elapsed_ms,
    )

    # collector 적재 (5분 윈도우 통계용, 사이클 95 키 호환)
    record_universe_refresh({
        "universe": universe_size,
        "kospi": len(kospi_sorted),
        "kosdaq": len(kosdaq_sorted),
        "unknown": 0,  # 사이클 97 — 2회 분리 호출 = unknown 불필요 (사이클 95 영속)
        "securities": securities_count,
        "etf_excluded": etf_excluded_total,
        "fetched": 0,
        "skipped_fresh": 0,
        "failed": 0,
        "elapsed_ms": elapsed_ms,
    })

    # 개장 전 1회 즉시 flush (사이클 78 답습)
    flush_universe_collector()

    return tickers


async def _universe_eager_refresh_loop(candidates: list[str]) -> None:
    """사이클 89 (2026-06-09) — universe 500 ticker stock_master 순차 upsert 루프.

    사이클 83 `_scan_pool_eager_refresh_loop` + 사이클 13-D `_eager_refresh_stock_master_for_held_positions`
    패턴 직답습.

    - 24h TTL fresh skip (사이클 83 Q3=B): `stock_master.is_stale(ticker, max_age_hours=24)` False → skip
    - ticker 간 50ms sleep (사이클 83 Q3=B): Rate Limit 20/s 보호
    - graceful: `inquire_stock_basics` 실패 시 continue (로그 없음, 사이클 83 답습)

    Args:
        candidates: universe ticker list (최대 500건). `fetch_top_500_universe()` 반환값.
    """
    import asyncio as _asyncio
    from src.db.stock_master import is_stale as _sm_is_stale, upsert_one as _sm_upsert
    from src.api.condition import inquire_stock_basics as _inquire_basics

    for ticker in candidates:
        # 24h TTL fresh skip (사이클 83 Q3=B + 사이클 13-D 패턴 답습)
        stale = await _sm_is_stale(ticker, max_age_hours=24)
        if not stale:
            continue

        # KIS CTPF1002R 호출 + upsert (graceful — 실패 시 continue)
        try:
            basics = await _inquire_basics(ticker)
            await _sm_upsert(basics)
        except Exception:
            pass  # graceful (사이클 83 답습 — stale 종목 쉐도우 skip)

        # 50ms Rate Limit 보호 (사이클 83 Q3=B 답습, KIS Rate Limit 20/s)
        await _asyncio.sleep(0.05)
