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
from datetime import date, datetime, time as _dtime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from src.api.condition import MIN_CHANGE_RATE, fetch_rising_stocks
from src.db.system_config import get_price_filter, get_trade_amount_filter
from src.engine.daily_emit_cap import DailyEmitCap, KstDailyEmitCap
from src.engine import no_feed_registry, tick_channel_clock, tick_channel_mode
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
    # 사이클 183 — 60s TTL 캐시 경유(_get_price_filter_for_scanner). PUT 즉시 반영은
    # invalidate_price_filter_cache_scanner() 가 담당 (사이클 64/148 PUT hook 영속).
    # tests 에서 `patch("src.engine.scanner.get_price_filter", ...)` 는 캐시 내부가
    # 여전히 get_price_filter 를 호출하므로 유효 (캐시 miss 시 실제 DB read 경유).
    pf = await _get_price_filter_for_scanner()
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
            today_kst = datetime.now(KST_TZ).date()
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
        today_kst = datetime.now(KST_TZ).date()
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

# ~~BREAKOUT_LOW_CAP = 25~~ 제거 (2026-08-08). cap 의 명분(09:30 momentum 발화
# 슬롯 보장)은 momentum 비활성으로 소멸했고, momentum 급등 스캔이 enabled 무관
# 리스트를 채워 cap 이 breakout(BFB/VCP) 슬롯을 죽은 momentum 으로 전용시키는
# 능동적 손해였다. subscribe pass-1 이 breakout 전체를 최우선 처리, 순서는
# `_collect_breakout_tickers`(BFB→VCP→VB→LTV, 2026-08-08 tail 편중 해소).

# ETF/ETN 제외 키워드
ETF_KEYWORDS = ("KODEX", "TIGER", "KBSTAR", "KOSEF", "ARIRANG", "SOL", "ACE",
                "RISE", "KoAct", "PLUS", "TIMEFOLIO", "WOORI", "FOCUS",
                "HANARO", "히어로즈", "마이티", "BNK", "MASTER", "WON",
                "ETN", "선물", "인버스", "레버리지", "채권", "혼합")

# 실시간 체결가 TR_ID — TICK_TR_ID = 현행 유일 활성 채널(통합). 시간대별 전환(사이클 26,
# 2026-05-20 f7f0766, 시간 경계 판정 함수 + 경계 상수 7 + 미사용 시간 alias import)은
# 108일간 배선된 적 없어 cycle257 에서 삭제 — 속성 기반 리졸버는 P1-7 B 로 별도 착수한다.
# TICK_TR_ID_KRX/NXT 2줄은 그 리졸버 `tick_tr_id_for(ticker)` 의 반환값 자리로 보존한다.
TICK_TR_ID = "H0UNCNT0"
TICK_TR_ID_KRX = "H0STCNT0"   # KRX 메인 전용 (09:00~15:39:59)
TICK_TR_ID_NXT = "H0NXCNT0"   # NXT 프리/애프터 전용 (08:00~08:59:59, 15:40~20:00)

# cycle293 (2026-09-14) — 세 시세 채널의 **단일 정본 집합**.
#
# 종전에는 `stale_diagnostics` 안에 같은 집합이 **함수 지역 변수**로 있어 아무도
# import 할 수 없었고, 나머지 9파일은 `tr_id == TICK_TR_ID` 등가 비교를 썼다. 그
# 등가 비교가 하나라도 남으면 전용 채널로 옮긴 종목이 `get_subscribed_tickers()`
# 에서 **조용히 사라져** (a) K stale watcher 가 영원히 못 보고 (b) 유니버스 이탈
# 종목이 영구 슬롯을 점유하고 (c) `already_in_pool` 미포함으로 매 5분 재SEND 하고
# (d) `[tick_coverage] subscribed=` 분모가 줄어 **숫자만 좋아진다**(cycle252
# 「은폐 금지」 계약 위반). 그래서 소비처는 전부 이 집합의 **멤버십**을 쓴다.
#
# ⚠️ 원소를 리터럴로 적는 것은 의도다 — 회귀 가드가 "세 채널을 담은 컬렉션
#    리터럴은 소스에 딱 하나" 를 세어 두 번째 정본이 생기는 것을 막는다. 값이
#    위 세 상수와 갈리지 않는 것은 `test_a7_tick_constants_unchanged` 가 그 세
#    상수를 리터럴로 핀해서 보장한다.
TICK_TR_IDS: frozenset[str] = frozenset({"H0UNCNT0", "H0STCNT0", "H0NXCNT0"})

# 통합(`TICK_TR_ID`)이 **아닌** 전용 채널. "이 종목은 전용 채널로 옮겨졌는가" 를
# 묻는 곳은 등가 비교가 아니라 이 집합의 멤버십으로 판정한다.
DEDICATED_TICK_TR_IDS: frozenset[str] = frozenset({TICK_TR_ID_KRX, TICK_TR_ID_NXT})

# ── cycle293 리졸버 관측 상태 ───────────────────────────────────────────────
#: ticker → 오늘 그 종목에 **적용된** 채널.
_channel_applied: dict[str, str] = {}
#: ticker → 오늘 이미 한 번 채널을 옮겼는가(§6-D 백스톱 = 같은 날 재전환 금지).
_channel_flipped_today: dict[str, bool] = {}
#: 위 두 dict 의 KST 날짜 키 (자기 리셋).
_channel_day: str = ""
#: cycle294 §6-C — ticker → 오늘 이 종목이 **통합 채널 무송출 코호트**인가.
#: 구독을 발사하는 시점에 확정하고, 매수 축 게이트는 이 스탬프만 읽는다.
#: `_sync_channel_day()` 가 KST 날짜 경계에서 `_channel_applied` 와 함께 비운다.
_channel_cohort: dict[str, bool] = {}
#: 출처 미확인 판정을 받은 종목 (그날 누적 — `[tick_channel_provenance_unknown]` 의 n=).
_channel_provenance_unknown: set[str] = set()
#: 관측 cap — 키는 복합 문자열. `KstDailyEmitCap` 이 KST 날짜 경계를 자기 리셋한다.
_channel_emit_cap: "KstDailyEmitCap[str]" = KstDailyEmitCap()


def reset_tick_channel_observation_caps() -> None:
    """관측 cap + 출처 미확인 집합 초기화 (모드 전환 시 `tick_channel_mode` 가 호출).

    채널 판정 이력(`_channel_applied` / `_channel_flipped_today`)은 **건드리지
    않는다** — 그것은 관측이 아니라 §6-D 플리커 백스톱의 상태다.
    """
    global _channel_emit_cap, _channel_provenance_unknown
    _channel_emit_cap = KstDailyEmitCap()
    _channel_provenance_unknown = set()


def reset_tick_channel_state_for_test() -> None:
    """채널 판정 이력까지 전부 초기화 (테스트 전용 seam)."""
    global _channel_applied, _channel_flipped_today, _channel_day, _channel_cohort
    _channel_applied = {}
    _channel_flipped_today = {}
    _channel_cohort = {}
    _channel_day = ""
    reset_tick_channel_observation_caps()
    try:
        from src.engine import tick_channel_clock

        tick_channel_clock.reset_state_for_test()
    except Exception:  # pragma: no cover — never-raise
        pass


def _channel_today() -> str:
    try:
        return datetime.now(KST_TZ).date().isoformat()
    except Exception:  # pragma: no cover — never-raise
        return ""


def _sync_channel_day() -> None:
    """KST 날짜가 바뀌면 판정 이력을 비운다 (날짜 키 자기 리셋)."""
    global _channel_day
    today = _channel_today()
    if not today:
        return
    if _channel_day == "":
        _channel_day = today
        return
    if _channel_day != today:
        _channel_day = today
        _channel_applied.clear()
        _channel_flipped_today.clear()
        # cycle294 §6-C — 코호트 스탬프는 **하루 수명**이다. 날짜 경계에서 비우지
        # 않으면 「닫힘 우세」 단방향 래치가 **영구 좌초**가 되어, NXT 에 재편입한
        # 종목(064550 계열)의 매수가 영원히 막힌다.
        _channel_cohort.clear()
        # cycle293 Green — `_channel_provenance_unknown` 도 날짜 경계에서 비운다.
        # 종전에는 `reset_tick_channel_observation_caps()`(모드 전환 시에만 호출)
        # 만이 이 집합을 비웠고 `_channel_emit_cap`(`KstDailyEmitCap`)은 스스로
        # 리셋되므로, 마커는 매일 다시 뜨는데 `n=`/`sample=` 은 **프로세스 수명
        # 누적**이었다 = 2일째부터 "그날 몇 건" 으로 읽으면 틀린 값이다.
        _channel_provenance_unknown.clear()


def _classify_channel(ticker: str) -> tuple[str, str, bool]:
    """이 종목이 어느 채널로 가야 하는가 — **순수 판정**(상태 변경 0).

    Returns: `(desired_tr_id, reason, decided)`.
    `decided=False` = 판정 불가 ⇒ 호출자는 현행(`TICK_TR_ID`)을 유지한다.

    ## 출처(provenance) 검사가 왜 필요한가 (§6-C)

    `_full_universe_load_krx_primary` 가 KRX raw 로 `nxt_tradable=False` 를 2,674
    종목에 **도장**하고 16:1x basics_refresh(부팅 날은 07:53~08:08)가 진실을
    복원한다. 그 창 안에 `TIME_PRESUBSCRIBE`(07:59)가 들어 있어 09-14 실측으로
    그 순간 **2,344/3,583(65.4%)** 이 도장 상태였고 그중 **420종목은 실제로
    `True`**(NXT 지정 유니버스 602 중 69.8%)였다. 값을 그대로 믿으면 진짜 NXT
    종목 420개를 NXT 체결을 실을 수 없는 채널로 보낸다 — 그래서 그 행의 raw 에
    KIS `cptt_trad_tr_psbl_yn` 키가 있을 때만 권위 있는 값으로 취급한다(도장에는
    그 키가 없다, 2,674/2,674 정확 일치).

    보유 종목 특례는 **불필요하다** — 07:45:45 eager refresh 가 보유·익일청산
    종목에 권위 있는 값을 도장 **전에** 주므로(그래서 `skipped_ttl=11`) 그들에게는
    출처 검사가 즉시 통과한다.
    """
    try:
        classified = bool(no_feed_registry.is_classified(ticker))
    except Exception:
        return TICK_TR_ID, "lookup_error", False
    if not classified:
        # cycle293 Green — **미지**(레지스트리 미적재)와 **송출 정상**을 갈랐다.
        # 종전에는 `is_no_feed()` 의 "모르면 False" 가 둘을 `decided=True,
        # reason="nxt_feed"` 로 접어 버려 INV-4("판정 실패 + 보유 = WARNING 으로
        # 노출")가 **구조적으로 성립하지 않았다** — 레지스트리가 차가운 07:59
        # 사전 구독 시점에 전 종목이 조용히 "판정 성공(통합 유지)" 으로 기록됐다.
        return TICK_TR_ID, "not_classified", False
    try:
        no_feed = bool(no_feed_registry.is_no_feed(ticker))
    except Exception:
        return TICK_TR_ID, "lookup_error", False
    if not no_feed:
        # 통합 채널이 이 종목의 프레임을 정상 송출한다 — 현행 유지(분류는 성공).
        # `nxt_tradable=True` 는 KRX 도장(항상 False)이 만들 수 없는 값이라
        # 출처 검사 없이도 신뢰할 수 있다.
        return TICK_TR_ID, "nxt_feed", True
    try:
        provenance_ok = bool(no_feed_registry.is_provenance_ok(ticker))
    except Exception:
        return TICK_TR_ID, "provenance_error", False
    if not provenance_ok:
        return TICK_TR_ID, "provenance_unknown", False
    return TICK_TR_ID_KRX, "no_feed", True


def _resolve_channel(
    ticker: str, now=None, *, offset_secs: int | None = None, priority: str = "LOW",
) -> tuple[str, str, bool]:
    """cycle294 §1-E — **시각축 × 속성축** 합성. `(tr_id, reason)`.

    시각축이 KRX 창을 돌려주면 속성축을 **보지 않는다**(그 창에는 L2 층이 존재
    하지 않는다). 프리 창 **과 NXT 단독 연속 구간**(CRITICAL-1, HIGH 한정)에서만
    `_classify_channel` 로 `nxt_false` 를 KRX 로 내린다 — 그 종목은 프리장에 **시장이 없어** 어느 채널이든 프레임이 0 이고
    (NXT 미거래 + KRX 시가 단일가), KRX 에 두면 정규장 개장 첫 체결을 **전환
    없이** 받는다(§2-C). 부수 효과로 전환 폭이 ~40% 줄어든다.

    🔴 `_classify_channel` 의 통합 반환은 여기서 **전부 NXT 로 흡수된다** — 그것이
    절대 규칙 1(통합 반환 0)의 구조적 보증이다. 속성축 본문은 byte 동일로 남긴다
    (cycle293 의 출처 검사·극성·fail-open 근거를 재작성하지 않는다).

    ## 프리 창 미판정의 폴백이 NXT 인 이유 (§3-B L2 — 비대칭)

    모르는 종목을 KRX 로 보내면 진짜 `nxt_true` 의 프리장 체결을 **새로 잃는다**
    (오늘은 통합 채널이 그것을 준다 ⇒ INV-1 위반). NXT 로 보내면 진짜
    `nxt_false` 가 프레임 0 이 되는데 그 구간엔 그 종목의 시장이 없어 **잃을 것이
    0** 이다. 잃을 수 있는 쪽을 보존한다.

    ⚠️ 부수 발견(§3-D) — 그 방향 때문에 cycle293 이 출처 검사로 막던 **W2 도장
    오염**(사전 구독 시각에 65.4%, 그중 420종목이 실제로는 `nxt_true`)의 **실패
    비용이 3단계에서 0** 이 된다. 오염된 420종목이 정답인 NXT 로 간다. 출처
    검사를 없애지는 않는다 — 프리 창에서 `nxt_false` 를 KRX 로 **내리는** 판단에는
    여전히 권위가 필요하고, §2-C 의 전환 폭 축소 이득이 거기서 나온다.
    """
    if offset_secs is None:
        offset_secs = tick_channel_mode.switch_offset_secs()
    if now is None:
        now = datetime.now(KST_TZ)
    chan, why = tick_channel_clock.clock_channel(
        now, offset_secs=offset_secs, priority=priority,
    )
    if chan == TICK_TR_ID_KRX:
        # KRX 창에는 **L2 층이 존재하지 않는다** — 속성축을 보지 않으므로 판정
        # 불가라는 상태 자체가 없다(09-14 16:39 실측이 그 채널의 종목 속성 무관
        # 수신을 확정했다). 세 번째 원소를 `True` 로 돌려 INV-4 관측을 침묵시키는
        # 것이 옳다 — 그 창에서 "모른다" 는 채널 선택을 하나도 바꾸지 않는다.
        return TICK_TR_ID_KRX, why, True
    desired, attr_reason, decided = _classify_channel(ticker)
    if decided and desired == TICK_TR_ID_KRX:
        return TICK_TR_ID_KRX, f"{why}|{attr_reason}", True
    return TICK_TR_ID_NXT, f"{why}|{attr_reason}", bool(decided)


def _stamp_cohort(ticker: str) -> None:
    """cycle294 §6-C — 구독 발사 시점에 코호트를 **확신할 때만** 심는다.

    🔴 심지 않는 경우(= 스탬프 부재)는 게이트에서 **열린다**(fail-open). 그
    방향의 근거는 §6-D 비대칭이다 — 닫힘 오류는 **레지스트리 전체 실패 한 번**
    으로 전 종목에 동시에 일어나고(상관된 실패 = 5전략 매수 0), 열림 오류는
    종목별로 독립이다. 절대 규칙 5 가 이 사이클 최대 위험으로 지목한 것이
    전자다.

    스탬프 부재가 구조적으로 0 에 가까운 근거 = cycle293 이
    `subscribe_filtered_stocks` 안에서 리졸버보다 **먼저**
    `no_feed_registry.ensure_fresh(_channel_probe)` 를 부르게 한 덕이다
    (`test_a22_registry_is_warmed_before_the_resolver_runs` 가 AST 로 잠갔다).
    그 가드가 붉어지면 이 fail-open 의 전제가 무너진다 — **두 가드는 서로를
    인용한다**.
    """
    try:
        if not no_feed_registry.is_classified(ticker):
            return                                  # 미분류 → 스탬프 없음
        nf = bool(no_feed_registry.is_no_feed(ticker))
        if nf and not no_feed_registry.is_provenance_ok(ticker):
            return                                  # 출처 미확인 → 스탬프 없음
        _sync_channel_day()
        # 🔴 하루 단방향(닫힘 우세) 래치 — 매수를 **여는** 방향의 하루 중 변화는
        #    다음 날로 미룬다. 매일 리셋되므로 cycle293 §6-D 가 금지한 '영구 좌초
        #    래치' 와 다르다(그건 채널 축이고 이건 매수 축이며 수명이 하루다).
        _channel_cohort[ticker] = bool(_channel_cohort.get(ticker, False) or nf)
    except Exception:  # pragma: no cover — never-raise
        return


def clock_desired_tick_tr_id(ticker: str, *, priority: str = "LOW", now=None) -> str:
    """모드를 **보지 않는** 시각축×속성축 희망 채널 — 순수·관측 전용.

    `desired_tick_tr_id` 는 모드 스코프를 거치므로 `off`/`observe` 에서 통합을
    돌려준다. 그러면 "전환 창을 지나쳤는데 몇 종목이 안 옮겨졌나" 를 세는 관측이
    모드에 따라 **항상 0** 이 된다(적대 검증 MEDIUM-3(부팅) — `off` 를 창 안에
    누르면 상태가 갈린 채 고정되는데 그 사실이 로그에 안 남았다).
    """
    try:
        chan, _reason, _decided = _resolve_channel(ticker, now, priority=priority)
        return chan
    except Exception:  # pragma: no cover — never-raise
        return TICK_TR_ID


def restamp_cohorts(tickers) -> int:
    """🔴 적대 검증 CRITICAL-1(부팅)/F-2(매수축) 시정 — 코호트 스탬프 **재시도**.

    종전에는 스탬프를 심는 유일한 자리가 `tick_tr_id_for` 였고, LOW 종목은
    `subscribe_filtered_stocks` 의 `already_in_pool` skip 이 그 호출보다 **앞**에
    있어 그날 **07:59 단 한 번만** 스탬프 기회를 가졌다. 그런데 07:59 는
    `_full_universe_load_krx_primary` 의 `nxt_tradable=False` 도장이 마스터의
    65.4% 를 덮고 있는 시각이라(cycle293 §6-C 실측), 그 순간 출처 검사가 실패한
    종목은 **영영 미스탬프**로 남았다 — 08:08 에 진실이 복원돼도 다시 심지
    않았다. 그 종목이 실제로 `nxt_false` 면 09:00 부터 KRX 프레임을 받으면서
    매수 게이트는 열린 채가 된다 = **승인 없는 B-2(매수 개방) 부분 발생**.

    이 함수는 구독 여부와 무관하게 주어진 집합 전체를 다시 스탬프한다. 스탬프는
    **닫힘 우세 단방향 래치**라 재호출이 매수를 더 열 수 없고(여는 방향의 변화는
    다음 날로 미뤄진다), 순수 메모리 연산이라 부작용이 없다. 배선 = 5분
    `subscribe_filtered_stocks` + 120초 `stale_watcher_core` 둘 다 `ensure_fresh`
    **직후**(레지스트리가 더워진 뒤라야 판정이 성립한다).

    Returns: 이번 호출로 새로 스탬프된 종목 수(관측용).
    """
    before = len(_channel_cohort)
    try:
        for ticker in dict.fromkeys(tickers or ()):
            _stamp_cohort(ticker)
    except Exception:  # pragma: no cover — never-raise
        return 0
    return max(0, len(_channel_cohort) - before)


def tick_buy_cohort_blocked(ticker: str) -> bool:
    """오늘 이 종목이 **무송출 코호트**로 확정됐는가 — 읽기 전용·순수.

    `risk._tick_buy_eval_blocked_by_channel` 이 틱마다 부르는 유일한 공개 술어다.
    상태를 변이하지 않는다(`_sync_channel_day` 의 날짜 경계 자기 정리는 관측이
    아니라 자기 정리라 예외다). 모드를 **보지 않는다** — `off` 는 이미 전용
    채널에 올라간 구독을 되돌리지 않으므로(§9-B), 모드를 보면 사고 중에 누르는
    안전 조치가 5전략의 매수를 그 코호트에 열어 준다.
    """
    try:
        _sync_channel_day()
        return bool(_channel_cohort.get(ticker, False))
    except Exception:  # pragma: no cover — never-raise
        return False


def note_channel_switched(ticker: str, tr_id: str) -> None:
    """cycle294 §4-C S6 — **성공한** 전환만 적용 이력·전환 예산에 기록한다.

    실패가 예산(`_channel_flipped_today`)을 먹으면 그날 재시도가 막힌다.
    """
    try:
        _sync_channel_day()
        _channel_applied[ticker] = tr_id
        _channel_flipped_today[ticker] = True
    except Exception:  # pragma: no cover — never-raise
        pass


def _mode_scoped_desired(ticker: str, priority: str, now=None) -> tuple[str, str]:
    """모드 스코프를 적용한 판정 — `(desired, reason)`.

    모드가 통합을 강제하는 경우(`off`/`observe`/`enforce_low`×HIGH)만 통합이
    나온다. 그 밖에는 §1-E 합성 결과 = **전용 2채널 중 하나**다(절대 규칙 1).
    """
    mode = tick_channel_mode.current_mode()
    if mode == tick_channel_mode.MODE_OFF:
        return TICK_TR_ID, "kill_switch_off"
    resolved, reason, _decided = _resolve_channel(ticker, now, priority=priority)
    if mode == tick_channel_mode.MODE_OBSERVE:
        return TICK_TR_ID, reason
    if mode == tick_channel_mode.MODE_ENFORCE_LOW and str(priority).upper() == "HIGH":
        return TICK_TR_ID, reason
    return resolved, reason


def desired_tick_tr_id(ticker: str, *, priority: str = "LOW", now=None) -> str:
    """**순수** 판정 — 상태 변경 0 · 로그 0.

    `tick_tr_id_for` 는 순수 함수가 **아니다**(아래 docstring). 판정만 알고 싶은
    호출자 — 해제 경로 · 카나리아 집계 · 읽기 전용 진단 · 전환 목표 산출 — 는 이
    함수를 쓴다. 해제에 판정 이력을 심으면 그 종목의 하루 전환 예산을 **사라지는
    종목**이 먹어 버려서, 같은 날 재구독이 분류와 반대 채널로 나간다.

    ⚠️ `now` 기본값은 상수 `None` 이다 — `def f(now=datetime.now())` 로 쓰면 기본
    인자가 **모듈 로드 시각에 한 번** 평가돼 부팅 프로세스가 종일 그 시각을 본다
    (= 전 종목이 프리 창에 영구 고착).
    """
    desired, _reason = _mode_scoped_desired(ticker, priority, now)
    return desired


def applied_tick_channel(ticker: str) -> str | None:
    """오늘 이 종목에 **적용된** 채널 (없으면 `None`) — 읽기 전용 접근자.

    `_channel_applied` 를 외부에서 직접 읽지 않게 한다. 이 값은 모드를 내려도
    (`off`) 지워지지 않는다 — 구독이 되돌아가지 않으므로 "무엇이 적용돼 있는가"
    도 되돌아가면 안 된다(§9-B: 이미 전용 채널에 올라간 종목은 다음 `_boot`
    까지 그 채널에 남는다).
    """
    try:
        _sync_channel_day()
        return _channel_applied.get(ticker)
    except Exception:  # pragma: no cover — never-raise
        return None


def subscribed_tick_tr_id(ticker: str, *, priority: str = "LOW", now=None) -> str:
    """그 종목이 **실제로 구독된** TICK 채널, 모르면 순수 판정 (해제 경로 전용).

    해제(UNSUBSCRIBE)는 판정이 아니라 **사실**을 따라야 한다 — 틀린 채널로
    해제하면 KIS 가 `OPSP0003 UNSUBSCRIBE ERROR not found!` 를 돌려주고(cycle215~218
    이 잡은 그 ERROR) 구 채널 튜플이 **영구 고아**로 41 슬롯을 잠식한다. 그래서
    풀의 병행 dict `_ticker_to_tr_id` 를 1순위로 읽고, 없을 때만 순수 판정으로
    폴백한다(풀 미사용 환경·부팅 전 구독).
    """
    try:
        from src.realtime.websocket_pool import kis_ws_pool as _pool

        mapping = getattr(_pool, "_ticker_to_tr_id", None)
        if isinstance(mapping, dict):
            current = mapping.get(ticker)
            if isinstance(current, str) and current in TICK_TR_IDS:
                return current
    except Exception:  # pragma: no cover — never-raise
        pass
    return desired_tick_tr_id(ticker, priority=priority, now=now)


def tick_tr_id_for(ticker: str, *, priority: str = "LOW", now=None) -> str:
    """이 종목의 체결 시세를 받을 TICK 채널 TR_ID 를 고른다 (cycle294 §1-E).

    🔴 **순수 함수가 아니다** — `await`/DB/HTTP 는 없지만(그 성질은 AST 가드가
    강제한다) `_stamp_cohort`(매수 축 코호트)와 `_apply_channel_decision`(하루
    1회 전환 예산)을 통해 상태를 변이하고 관측 마커를 낸다. 그래서 **구독을
    실제로 발사하는 자리에서만** 부른다. 판정만 필요한 곳(해제·집계·게이트)은
    `desired_tick_tr_id`(순수) 또는 `subscribed_tick_tr_id`(구독 사실 우선)를 쓴다.

    🔴 **정상 경로에서 통합 채널을 반환하지 않는다**(절대 규칙 1). 판정 실패의
    폴백은 통합이 아니라 **시각 기반 기본값**이다 — 프리 창은 NXT, 그 밖은 KRX
    (§3-B). 통합이 나오는 유일한 자리는 아래 모드 분기 셋(`off` 롤백 ·
    `observe` 다크런치 · `enforce_low`×HIGH)뿐이다.

    `priority` 는 `enforce_low` 단계(HIGH = 보유·익일청산 제외)를 위해 필요하다 —
    가설이 어떤 보유 종목에 대해 틀렸을 때 잃는 것이 손절 커버리지다.
    """
    mode = tick_channel_mode.current_mode()
    if mode == tick_channel_mode.MODE_OFF:
        # 롤백 위치 — 판정도 관측도 하지 않는다(배포 전과 동일).
        return TICK_TR_ID
    resolved, reason, decided = _resolve_channel(ticker, now, priority=priority)
    if not decided:
        # INV-4 — 판정 불가를 **사람에게 올린다**. 3단계의 L2 fail-open 은 프리
        # 창에서 NXT 로 떨어지는데(§3-B), 그 선택이 옳았는지는 아무도 모른다.
        # 보유(HIGH) 종목이면 종목별 WARNING 으로 따로 남는다 — 그 종목의 손절이
        # REST 폴에만 의존하게 되고 REST 폴은 donchian·kojiro 두 전략만 덮는다.
        _emit_channel_undecided(ticker, priority, reason)
    if mode == tick_channel_mode.MODE_OBSERVE:
        # 다크런치 — 판정만 남기고 채널은 바꾸지 않는다(행위 0). 적용 이력도
        # 기록하지 않는다(기록하면 `enforce` 로 올리는 순간이 '재전환' 이 되어
        # 백스톱이 첫 적용을 막는다).
        _emit_channel_resolve(ticker, mode, resolved, TICK_TR_ID, reason)
        return TICK_TR_ID
    if mode == tick_channel_mode.MODE_ENFORCE_LOW and str(priority).upper() == "HIGH":
        # S1 은 HIGH(보유·익일청산)를 스코프 **밖**에 둔다 — 적용 이력도 건드리지
        # 않는다(HIGH 호출이 LOW 의 전환 예산을 먹으면 안 된다).
        return TICK_TR_ID
    # 🔴 코호트 스탬프는 적용 **앞**이다 — 적용이 예외로 빠져도 구독이 나간
    #    종목에는 스탬프가 남아야 한다(§6-C · A13).
    _stamp_cohort(ticker)
    applied = _apply_channel_decision(ticker, resolved, reason)
    _emit_channel_resolve(ticker, mode, resolved, applied, reason)
    return applied


def _apply_channel_decision(ticker: str, desired: str, reason: str) -> str:
    """§6-D 백스톱 — **같은 종목은 하루에 한 번만 채널을 옮긴다.**

    래치는 두지 않는다(양방향) — "한 번 no_feed 면 영구 전용 채널" 로 만들면
    064550 처럼 NXT 에 재편입한 종목을 NXT 체결을 못 받는 채널에 영구 좌초시킨다
    (09-02 16:06 `False` → 09-14 07:59:09 `True` 실측이 전환의 양방향성을 증명한다).
    대신 그날 두 번째 전환만 막는다 — 채널 왕복(KIS 공지 「비정상 케이스 2:
    무한 등록/해제」)을 값싸게 차단한다. **시간 창 리터럴은 두지 않는다**(C-2) —
    오염 창의 양끝이 일정 파생값이고 그 일정은 이미 두 번 움직였다.
    """
    try:
        _sync_channel_day()
        current = _channel_applied.get(ticker)
        if current is None:
            _channel_applied[ticker] = desired
            return desired
        if desired == current:
            return current
        if _channel_flipped_today.get(ticker):
            _emit_channel_flip(ticker, current, desired, reason, blocked=True)
            return current
        _channel_flipped_today[ticker] = True
        _channel_applied[ticker] = desired
        _emit_channel_flip(ticker, current, desired, reason, blocked=False)
        return desired
    except Exception:  # pragma: no cover — never-raise (관측 실패가 판정을 막지 않는다)
        _trace_channel_observer_failure("[tick_channel_flip]", ticker)
        return desired


def _trace_channel_observer_failure(marker: str, key: str) -> None:
    try:
        from src.engine.observer_trace import trace_observer_failure

        trace_observer_failure(marker, key, None, dest_logger=logger)
    except Exception:  # pragma: no cover — 2차 예외도 흡수
        pass


def _emit_channel_resolve(
    ticker: str, mode: str, desired: str, applied: str, reason: str,
) -> None:
    """`[tick_channel_resolve]` — 1회/(ticker, 채널)/일.

    통합 유지 판정(`desired == TICK_TR_ID`)은 남기지 않는다 — 하루 ~3,000행이
    되고 판독 가치가 0이다. 카운트는 `[tick_channel_config]` 가 담당한다.

    ⚠️ **`applied=` 는 리졸버가 고른 값이지 풀이 수락한 값이 아니다.** 이미
    구독 중인 종목에 다른 채널을 요청하면 풀이 §3-C(장중 전환 금지)에 따라
    요청을 버리고 현행 채널을 유지한다 — 그 사실은 같은 (ticker)/일의
    `[tick_channel_request_denied]` 로 읽는다(그 행이 없으면 수락된 것이다).
    그리고 "정말로 두 채널에 동시 구독돼 있는가" 는 세 번째 마커
    `[tick_channel_dual_detected]`(전 세션 전수 대조)가 따로 답한다.
    """
    if desired not in DEDICATED_TICK_TR_IDS:
        return
    # ⚠️ cycle293 마커 5종은 **완성된 문자열**로 남긴다(lazy %-args 금지) —
    #   회귀 가드가 `record.args` 가 빈 것을 전제로 `record.message` 를 직접 읽고,
    #   운영 grep 도 최종 문자열만 본다. 인자를 남기면 `message % args` 가 깨진다.
    _channel_emit_cap.emit_once(
        f"resolve|{ticker}|{desired}",
        logger.info,
        f"[tick_channel_resolve] ticker={ticker} mode={mode} would={desired} "
        f"applied={applied} reason={reason} provenance=cptt_key",
    )


def _emit_channel_undecided(ticker: str, priority: str, reason: str) -> None:
    """`[tick_channel_provenance_unknown]` — 판정 불가를 사람에게 올린다 (INV-4).

    fail-open 은 "모르면 blind 유지" 라서 보수적이지 않다 — 보유 종목에서 판정이
    실패하면 그 종목은 계속 blind 이고, 그 사실이 로그에 없으면 아무도 모른다.
    그래서 cap 키에 `priority` 를 넣어 **보유(HIGH) 종목의 판정 실패는 따로**
    남는다. 그 종목의 손절은 REST 폴에만 의존하고, REST 폴은 donchian·kojiro 두
    전략만 덮는다(BFB/VCP 가 잡으면 종일 손절 평가 0).
    """
    try:
        _sync_channel_day()
        _channel_provenance_unknown.add(ticker)
        is_high = str(priority).upper() == "HIGH"
        # cycle293 Green — cap 키를 **먼저** 만들고 `emit_once` 가 억제하는지
        # 판정한 뒤에만 `sorted(...)` 를 돈다. 그 집합은 W2 도장 창에서 수천
        # 개까지 커질 수 있고 이 함수는 `risk.on_tick`(틱 경로)에서도 도달
        # 가능하다 — 관측이 cap 밖에서 일하면 안 된다.
        #
        # 그리고 **보유(HIGH)만 종목별로** WARNING 을 낸다. INV-4 가 요구하는
        # 것은 "판정 실패 + 보유 = 사람에게 올린다" 이고, LOW 미지까지 종목별로
        # 내면 레지스트리가 차가운 첫 사이클에 수천 행이 된다. LOW 는 그날 1행
        # 요약(n=/sample=)으로 규모만 남긴다.
        key = f"undecided|{ticker}|{priority}" if is_high else "undecided|low_summary"
        if not _channel_emit_cap.should_emit(key):
            return
        sample = sorted(_channel_provenance_unknown)[:5]
        msg = (
            f"[tick_channel_provenance_unknown] ticker={ticker} priority={priority} "
            f"reason={reason} n={len(_channel_provenance_unknown)} sample={sample}"
        ) if is_high else (
            f"[tick_channel_provenance_unknown] ticker=- priority=LOW "
            f"reason={reason} n={len(_channel_provenance_unknown)} sample={sample}"
        )
        # peek→로그→mark (cycle226 D-3) — 로그 자기실패가 그날 관측을 지우지 않는다.
        logger.warning(msg)
        _channel_emit_cap.mark_emitted(key)
    except Exception:  # pragma: no cover — never-raise
        _trace_channel_observer_failure("[tick_channel_provenance_unknown]", ticker)


def _emit_channel_flip(
    ticker: str, from_tr_id: str, to_tr_id: str, reason: str, *, blocked: bool,
) -> None:
    """`[tick_channel_flip]` — 채널 전환 시도(성공·차단 모두), 1회/(ticker,전환,차단)/일.

    🔴 **cap 이 반드시 있어야 한다.** `same_day_blocked=1` 분기는 일시적
    이벤트가 아니라 **지속 상태**다 — `_apply_channel_decision` 이 차단 시
    `_channel_applied` 를 바꾸지 않으므로 판정이 계속 어긋나 있으면 **모든 후속
    호출**이 그 분기를 다시 밟는다. 무cap 이면 `risk.on_tick` 계열에서 도달할 때
    틱당 1행이 되고(실측 200틱 → 200행) `_DbLogHandler` 가 `system_logs` 로
    적재해 cycle237(donchian 청산 로그 하루 1만 행)과 같은 폭주가 된다.
    """
    try:
        _channel_emit_cap.emit_once(
            f"flip|{ticker}|{from_tr_id}|{to_tr_id}|{1 if blocked else 0}",
            logger.warning,
            f"[tick_channel_flip] ticker={ticker} from={from_tr_id} to={to_tr_id} "
            f"reason={reason} same_day_blocked={1 if blocked else 0}",
        )
    except Exception:  # pragma: no cover — never-raise
        _trace_channel_observer_failure("[tick_channel_flip]", ticker)


def emit_tick_channel_config(tickers) -> None:
    """`[tick_channel_config]` — 하루 1행 **배포 카나리아** (§9-A).

    이 행이 없으면 배포가 실제로 반영됐는지, `resolved_krx` 가 0이 아닌지(= S0
    다크런치의 진행 게이트)를 알 수 없다. 판정은 `_classify_channel` 순수 호출만
    쓴다 — 관측이 전환 이력(`_channel_flipped_today`)을 소모하면 안 된다.

    🔴 **레벨이 WARNING 인 것은 의도다.** `log_metrics_collector` 의
    `pattern_by_level` 은 `{WARNING, ERROR, CRITICAL}` 만 21:30 일일 리포트
    `top_patterns` 에 넣는다 — INFO 로 두면 **배포 반영 여부가 리포트에 한 글자도
    안 뜬다**(cycle245 가 `[ratio_cap_config]` 로 겪은 그 함정). 하루 1행이라
    비용은 0 이다.

    `unclassified=` 는 H1(사전 구독 코호트 누락)의 판독 축이다 — 레지스트리가
    차가운 순간에 이 값이 크면 `resolved_krx` 가 작은 이유가 "옮길 게 없다" 가
    아니라 "아직 분류를 못 했다" 다.
    """
    try:
        now = datetime.now(KST_TZ)
        # cycle294 §11-A — 표 파생 경계 3개를 하루 1행으로 남긴다. 이 호출이
        # `subscribe_filtered_stocks` 를 타므로 사실상 그날 **첫 구독 시점**의
        # 카나리아다(07:59 사전 구독). 실패해도 never-raise 다.
        tick_channel_clock.emit_clock_config(
            now, offset_secs=tick_channel_mode.switch_offset_secs(),
        )
        # cycle294 §2-D — 프리 창이 닫힌 뒤 그날 프리 창 프레임 실측을 남긴다
        # (창 안에서는 건수가 확정되지 않아 발화하지 않는다). 기대값 = 0행.
        tick_channel_clock.emit_pre_window_frame_summary(now)

        mode = tick_channel_mode.current_mode()
        resolved_krx = 0
        resolved_unified = 0
        provenance_ok = 0
        provenance_unknown = 0
        unclassified = 0
        # cycle294 §11-B — 라벨 3분할. `resolved_*` 는 **속성축**(cycle293) 집계라
        # 3단계에서는 "채널이 어디로 갔나" 를 더 이상 답하지 못한다. 실제 적용
        # 채널은 시각축이 정하므로 `clock_krx`/`clock_nxt` 를 따로 센다. 구 라벨을
        # **지우지 않는** 이유 = cycle293 D+1 판독 사슬(`resolved_unified=0` 이
        # 3단계 성공 서명)이 그 이름에 걸려 있다. ⚠️ 배포 전후 grep 합산 금지.
        clock_krx = 0
        clock_nxt = 0
        cohort_no_feed = 0
        for ticker in dict.fromkeys(tickers or ()):
            desired, _reason, _decided = _classify_channel(ticker)
            if desired in DEDICATED_TICK_TR_IDS:
                resolved_krx += 1
            else:
                resolved_unified += 1
            try:
                chan, _why, _decided = _resolve_channel(ticker, now)
                if chan == TICK_TR_ID_NXT:
                    clock_nxt += 1
                elif chan == TICK_TR_ID_KRX:
                    clock_krx += 1
            except Exception:
                pass
            try:
                if tick_buy_cohort_blocked(ticker):
                    cohort_no_feed += 1
            except Exception:
                pass
            try:
                if not no_feed_registry.is_classified(ticker):
                    unclassified += 1
            except Exception:
                unclassified += 1
            try:
                if no_feed_registry.is_provenance_ok(ticker):
                    provenance_ok += 1
                else:
                    provenance_unknown += 1
            except Exception:
                provenance_unknown += 1
        _channel_emit_cap.emit_once(
            f"config|{mode}|{_clock_phase(now)}",
            logger.warning,
            f"[tick_channel_config] mode={mode} resolved_krx={resolved_krx} "
            f"resolved_unified={resolved_unified} clock_krx={clock_krx} "
            f"clock_nxt={clock_nxt} cohort_no_feed={cohort_no_feed} "
            f"provenance_ok={provenance_ok} "
            f"provenance_unknown={provenance_unknown} unclassified={unclassified}",
        )
        _emit_tick_buy_gate(tickers)
    except Exception:  # pragma: no cover — never-raise
        _trace_channel_observer_failure("[tick_channel_config]", "-")


def _clock_phase(now) -> str:
    """관측 cap 을 가르는 **시각 구간 라벨** — 리터럴 0건(시각축 leaf 파생).

    🔴 적대 검증 CRITICAL-2(부팅)/F-3(매수축) 시정 — 종전에는 cap 키가
    `config|{mode}` · `"buy_gate"` 라 **하루 1행**이었고, 그 1행은 07:59 사전
    구독의 `subscribe_filtered_stocks` 에서 나왔다. 그 시각은 W2 도장 오염이
    최악이라 `[tick_buy_gate]` 가 매일 `unstamped=거의 전부` 를 찍었고,
    `cohort_no_feed` 도 늘 0 이었다 — fail-open 을 재는 **유일한 계측기**가
    결함과 무관하게 항상 같은 값을 내니 아무것도 못 잡는다. 구간 라벨을 키에
    넣어 프리 창 1행 + 정규장 창 1행(= 스탬프가 다 심긴 뒤)을 남긴다.
    """
    try:
        _chan, reason = tick_channel_clock.clock_channel(
            now, offset_secs=tick_channel_mode.switch_offset_secs(),
        )
        return str(reason).split("|")[0]
    except Exception:  # pragma: no cover — never-raise
        return "unknown"


def _emit_tick_buy_gate(tickers) -> None:
    """`[tick_buy_gate] stamped_no_feed= stamped_feed= unstamped=` — 하루 1행 WARNING.

    §6-D 의 fail-open(스탬프 부재 = 매수를 **열어 둔다**)이 조용하지 않게 만드는
    유일한 장치다. `unstamped` 가 크면 스탬프 배선이 깨진 것이고, 그러면 매수 축이
    통제 없이 열려 있다는 뜻이다 — 그 상태가 리포트에 뜨지 않으면 아무도 모른다.

    🔴 **판독 규칙(적대 검증 CRITICAL-2 시정 이후)** — 이 마커는 하루 **두 행**이다.
    cap 키가 `buy_gate|<시각 구간>` 이라 프리 창에서 1행, 정규장 창에서 1행 나온다.
    **판단은 정규장 창 행으로 한다** — 프리 창 행의 `unstamped` 는 W2 도장 오염
    (사전 구독 시각에 마스터의 65.4%)을 재는 값이라 크게 나오는 것이 정상이고,
    그 값으로 배선을 판정하면 매일 거짓 경보다. 정규장 창 행에서도 `unstamped`
    가 크면 그때가 진짜 결함이다(`restamp_cohorts` 가 5분·120초 두 배선에서
    돌기 때문에 08:10 이후에는 0 에 수렴해야 한다).

    `unstamped` 가 구조적으로 0 에 가까운 근거 = cycle293
    `test_a22_registry_is_warmed_before_the_resolver_runs` 가 "리졸버 호출 **전에**
    `ensure_fresh`" 를 AST 로 잠갔다. 그 가드가 붉어지면 이 fail-open 의 전제가
    무너진다 — **두 가드를 서로 인용한다**.
    """
    try:
        stamped_no_feed = 0
        stamped_feed = 0
        unstamped = 0
        for ticker in dict.fromkeys(tickers or ()):
            if ticker in _channel_cohort:
                if _channel_cohort.get(ticker):
                    stamped_no_feed += 1
                else:
                    stamped_feed += 1
            else:
                unstamped += 1
        _channel_emit_cap.emit_once(
            f"buy_gate|{_clock_phase(datetime.now(KST_TZ))}",
            logger.warning,
            f"[tick_buy_gate] stamped_no_feed={stamped_no_feed} "
            f"stamped_feed={stamped_feed} unstamped={unstamped}",
        )
    except Exception:  # pragma: no cover — never-raise
        _trace_channel_observer_failure("[tick_buy_gate]", "-")


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

        # 사이클 157 Q2 — 1단계 진입 차단 hook (momentum 영역, 사이클 132 funnel 미적재 영속).
        # _is_master_blocked_for_entry 11건 (master_raw 7 + raw 4) — 거래정지/관리종목/단기과열 등.
        # graceful: stock_master.get / get_master_raw 예외 시 통과 (사이클 88 G-REJECT 답습).
        try:
            from src.db import stock_master as _sm_mod
            basics = await _sm_mod.get(ticker)
            master_raw_mom: dict = {}
            raw_mom: dict = dict(basics.raw) if basics and basics.raw else {}
            try:
                m_resp = await _sm_mod.get_master_raw(ticker)
                if m_resp:
                    master_raw_mom = dict(m_resp)
            except Exception:
                pass
            blocked_mom, _reason_mom = _is_master_blocked_for_entry(master_raw_mom, raw_mom)
            if blocked_mom:
                continue
        except Exception:
            # graceful — stock_master 미캐시 시 통과 (실시간 본질 영역 영속)
            pass

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
    _last_scan_time = datetime.now(KST_TZ).strftime("%H:%M:%S")  # 사이클 183 — KST 강제 (stale-3)

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

    # cycle293 — 킬스위치 재조회(5분 `_scan_loop` 주기) + 배포 카나리아 1행.
    # `scheduler.py` 는 무접촉이라 재조회 배선을 여기와 `stale_watcher_core`
    # (120초)에 둔다 — 둘 중 어느 쪽이든 ≤5분 안에 `off` 가 닿는다. 둘 다
    # never-raise: 킬스위치 조회 실패가 구독 사이클을 끊으면 안 된다.
    try:
        await tick_channel_mode.refresh_mode()
    except Exception:
        logger.debug("[tick_channel_mode] refresh 실패 — 현재 모드 유지", exc_info=True)
    _channel_probe = list(
        dict.fromkeys(
            all_tickers
            + list((priority_groups or {}).get("positions") or [])
            + list((priority_groups or {}).get("next_day_clear") or [])
        )
    )
    # 🔴 cycle293 Green (적대 검증 H1) — 리졸버를 부르기 **전에** 이 사이클이
    # 구독할 종목 전부를 분류해 둔다.
    #
    # 종전에는 `no_feed_registry.ensure_fresh` 의 유일한 호출자가
    # `stale_watcher_core`(120초 루프, 첫 호출 07:47:47)였고 그 인자는
    # `subscribed ∪ 보유·익일청산` 이었다 — **아직 구독하지 않은 후보는 원리상
    # 그 집합에 들어갈 수 없다**. 그래서 07:59 `TIME_PRESUBSCRIBE` 의 LOW 후보
    # ~134종목은 전부 `is_classified()=False` 로 판정 불가 ⇒ 통합 채널로 확정되고,
    # 다음 5분 사이클부터는 `already_in_pool` skip 이 리졸버 호출보다 **앞**에
    # 있어 그날 다시 판정되지 않는다. 실효 전환 대상이 "레지스트리가 더워진 뒤
    # 새로 등장하는 후보" 뿐으로 쪼그라들어, 09-14 실측 stale 64종목의 대부분
    # (= 07:59 코호트)에 대해 리졸버가 **아무것도 하지 않는다**.
    #
    # never-raise — 분류 실패는 fail-open(전원 통합 = 오늘과 동일)이고, 그것이
    # 구독 사이클을 끊으면 4중 안전망의 한 축이 사라진다.
    try:
        await no_feed_registry.ensure_fresh(_channel_probe)
    except Exception:
        logger.debug(
            "[no_feed_registry] 구독 전 ensure_fresh 실패 — 이번 사이클 전원 통합 유지",
            exc_info=True,
        )
    # 🔴 cycle294 적대 검증 CRITICAL-1(부팅) — 코호트 스탬프를 **매 사이클 재시도**
    #    한다. `tick_tr_id_for` 안의 스탬프는 LOW 종목에 대해 그날 07:59 한 번뿐이고
    #    (그 뒤로는 `already_in_pool` skip 이 리졸버 호출보다 앞에 있다), 07:59 는
    #    W2 도장 오염이 최악인 시각이라 그때 출처 검사가 실패한 종목이 영영
    #    미스탬프로 남아 매수 축 게이트가 열린 채 방치됐다. 순수 메모리 연산 ·
    #    닫힘 우세 단방향 래치라 재호출이 매수를 더 열 수 없다.
    #    `emit_tick_channel_config` **앞**이어야 카나리아가 진짜 스탬프 상태를 센다.
    restamp_cohorts(_channel_probe)
    emit_tick_channel_config(_channel_probe)
    # 적대 검증 F3/CRITICAL — 이중 채널 검출은 `WebsocketPool.subscribe` 의 중복
    # 분기가 아니라 **전 세션 `_subscriptions` 전수 대조**여야 한다. 그 분기는
    # 풀을 경유한 요청만 보므로 §4-C 가 드러내려던 두 줄
    # (`scheduler.py:1382`·`:2728` = `kis_ws.subscribe` 직접 호출)을 **구조적으로
    # 볼 수 없었다**. 여기(5분 `_scan_loop`)에서 사실을 직접 센다.
    try:
        kis_ws_pool.detect_dual_tick_channels()
    except Exception:
        logger.debug("[tick_channel_dual_detected] 전수 대조 실패", exc_info=True)

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
            # cycle293 — 채널은 리졸버가 고른다. `priority`/`bypass_limit` 은
            # 글자 그대로 불변(INV-2 — 보유 시세는 절대 보장이다).
            await kis_ws_pool.subscribe(
                tick_tr_id_for(t, priority="HIGH"), t, priority="HIGH", bypass_limit=True,
            )
        # 2) next_day_clear — priority='HIGH', bypass_limit=True (절대 보장)
        for t in next_day_clear:
            if t in already:
                continue
            already.add(t)
            await kis_ws_pool.subscribe(
                tick_tr_id_for(t, priority="HIGH"), t, priority="HIGH", bypass_limit=True,
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

        # 사이클 184 (stale-2) — 풀 총용량 기준 잔여 슬롯 (메인 단독 카운트 → 풀 union)
        # 세션 수는 2-pass 루프 중 불변이라 HIGH 처리 후 LOW 루프 진입 전 1회만 계산.
        # 보조 0개(n=1) 시 _pool_total_slots=41 + kis_ws_pool._subscriptions==메인 → 현 동작 동일(회귀 0).
        _pool_session_count = len(kis_ws_pool.get_session_status())   # main + 보조 N = 1+N
        _pool_total_slots = MAX_SUBSCRIPTIONS * _pool_session_count

        # ~~작업 2 (2026-05-13): breakout cap 25~~ → **제거 (2026-08-08)**.
        # cap 25 의 명분은 "09:30 momentum 발화 슬롯 보장" 이었으나 momentum 은
        # 현재 비활성(enabled=False, weight 0)이라 지킬 대상이 사라졌다. 그런데
        # momentum 급등 스캔(`scan_stocks`)은 registry.enabled 를 참조하지 않아
        # 비활성이어도 리스트가 채워지므로, cap 은 살아있는 breakout(특히 BFB/VCP)
        # 슬롯을 매수신호 0 인 죽은 momentum 스캔으로 전용시키는 **능동적 손해**였다.
        # breakout 전체를 pass-1 최우선으로 둔다 — pool 압박 시엔
        # `_collect_breakout_tickers` 순서(BFB→VCP→VB→LTV)의 tail(VB/LTV)부터 잘려
        # BFB/VCP 가 우선 구독된다(사용자 결정 2026-08-08).
        breakout_primary = breakout
        breakout_overflow: list[str] = []

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
                remaining = _pool_total_slots - len(kis_ws_pool._subscriptions)
                if remaining <= 0:
                    drop_counts[label] += 1
                    continue
                already.add(t)
                await kis_ws_pool.subscribe(
                    tick_tr_id_for(t, priority="LOW"), t, priority="LOW", bypass_limit=False,
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
            remaining = _pool_total_slots - len(kis_ws_pool._subscriptions)
            if remaining <= 0:
                # 잔여 0 — 더 이상 흡수 불가
                break
            already.add(t)
            absorbed_overflow += 1
            # 사이클 7-C — overflow 도 LOW priority 로 풀에 위임
            await kis_ws_pool.subscribe(
                tick_tr_id_for(t, priority="LOW"), t, priority="LOW", bypass_limit=False,
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
            # 미구독 진단 계측 (2026-08-08 pool_sessions/pool_slots + 2026-08-10 pool_subscribed).
            # ⚠️ total_subscribed·max·low_remaining 은 **메인 세션 단독** 뷰다. 실제 drop 은
            # `_pool_total_slots - len(kis_ws_pool._subscriptions)` 로 판정하므로, 풀 전체
            # 실제 구독량(pool_subscribed)·잔여(pool_remaining)를 병기해야 drop 이
            # **세션 미활용(pool_remaining>0인데 drop = 구독 상태 드리프트/보조세션 불안정)**
            # 인지 **실제 풀 만석(pool_remaining≈0)** 인지 판별된다. (BFB/VCP 확대 미구독 근본 진단)
            pool_subscribed = len(kis_ws_pool._subscriptions)
            pool_remaining = max(0, _pool_total_slots - pool_subscribed)
            drop_log = (
                f"[priority_drop] breakout={drop_counts['breakout']} "
                f"momentum={drop_counts['momentum']} swing={drop_counts['swing']} "
                f"total_subscribed={total_subscribed} max={MAX_SUBSCRIPTIONS} "
                f"high_count={high_count} low_remaining={low_remaining} "
                f"pool_sessions={_pool_session_count} pool_slots={_pool_total_slots} "
                f"pool_subscribed={pool_subscribed} pool_remaining={pool_remaining}"
            )
            logger.warning(drop_log)
            # 사이클 72 hotfix A11: write_log 제거 — logger.warning → _DbLogHandler 위임 단일 INSERT
            # (drop 발생은 WARNING 레벨로 격상 — 운영 가시화 보존)
    else:
        # 기존 평탄 처리 (외부 호환 fallback)
        for ticker in all_tickers:
            await kis_ws.subscribe(tick_tr_id_for(ticker), ticker)

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
        # cycle293 — 등가 비교 금지. 전용 채널로 옮긴 종목이 이 정리에서 빠지면
        # 그 튜플이 영구 고아로 41 슬롯을 잠식한다(§5-B).
        if tr_id in TICK_TR_IDS:
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

    # 사이클 127 — 진행 state hook (fire-and-forget + 5초 폴링)
    from src.engine import refresh_progress as _rp

    _rp.start_progress("universe", total=0)

    try:
        try:
            summary = await _full_universe_load_krx_primary(force=force)
            summary["source"] = "krx"
        except KrxApiError as exc:
            logger.warning(
                "[krx_open_api_fallback] KRX 실패 → KIS market-cap 폴백 (graceful): %s",
                exc,
            )
            summary = await _full_universe_load_kis_fallback(force=force)
            summary["source"] = "kis_fallback"

        # 사이클 127 — 완료 시 finish_progress (정상 종료)
        _rp.finish_progress(
            "universe", "completed",
            total=summary.get("total", 0),
            processed=summary.get("total", 0),
            updated=summary.get("fetched", 0),
            skipped=summary.get("skipped_ttl", 0),
            failed=summary.get("failed", 0),
        )
        return summary
    except Exception as exc:
        # 사이클 127 — 실패 시 finish_progress (예외 전파 유지)
        _rp.finish_progress(
            "universe", "failed",
            error_message=str(exc),
        )
        raise


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
        # 사이클 116 → 사이클 166 — KRX MKTCAP (원 단위) → KIS hts_avls (억원 단위) 환산.
        # 사이클 166 정정: KIS 경로 hts_avls 가 억원 단위로 확정 (운영 DB 실측 + KIS 정본)
        # → KRX 폴백도 억원으로 통일 (단위 혼재 silent 결함 제거). 사이클 108
        # list_by_filter (`hts_avls × 100_000_000 ≥ min_market_cap`) 정합 영속.
        # 사이클 81 G-AST1 영속: KIS market-cap 호출 시점은 KRX 폴백 분기 = 동일 ticker
        # 양쪽 키 충돌 0 (KRX 1차 성공 시 KIS 호출 부재).
        if "MKTCAP" in trd_row:
            try:
                mktcap_won = int(str(trd_row["MKTCAP"]).replace(",", "") or 0)
                if mktcap_won > 0:
                    krx_raw["hts_avls"] = mktcap_won // 100_000_000  # 원 → 억원
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
# 사이클 299 — retention 390cal≈261영업일 보유 → target 225(36영업일 마진). 225 인 이유 =
# 실효 장기선이 정확히 200 이 되는 깊이다(effective_ema_long = min(ema_long, 보유 − 20 − 5)).
# DB 깊이 < 225 이면 분할 backfill. VCP 가 실제로 읽는 깊이는 전략 파라미터
# `daily_fetch_depth_mode` 가 정한다(`vcp_breakout.py:309-314` — `"cap100"`=100봉 /
# `"full"`=`ema_long + base_max + 10`, cycle300). 운영은 `"full"` 이다.
#
# 🔴 사이클 302 — **이 상수는 VCP 전용이 아니다.** 일봉 적재 대상(index ∪ 시총·거래대금
# 자격 ∪ 보유·익일청산 보호) **전부**의 목표 깊이다. 이름의 `VCP` 는 이 깊이를 처음 요구한
# 전략의 흔적일 뿐이고, 읽는 쪽은 "적재 대상이면 누구나 이 깊이까지 채운다" 로 읽는다.
# (이름 정정은 `src/api/condition.py` 의 호출자 주석까지 같이 움직여야 해서 후속으로 둔다.)
_DAILY_LOAD_VCP_BACKFILL_DAYS = 225

# 사이클 206 — 일봉 적재를 유니버스(index ∪ 시총/거래대금 자격) 로 한정 (당시 Supabase 용량).
# 2026-07 — kojiro 전체 상장 전환(지수 제거, 시총500억/거래10억)에 맞춰 trade 임계 20억→10억.
# kojiro 유니버스(전체상장 ∩ 500억/10억 ≈ 979) 전량 일봉 커버. RDS 라 용량 여유(사이클 206
# Supabase 제약 해소). non-index 저거래 종목 ~123 추가 적재 (16:00 daily task 가 backfill).
_DAILY_LOAD_MIN_MCAP_EOK = 500  # 억원 (raw.hts_avls 는 억원 단위, 사이클 166/108)
_DAILY_LOAD_MIN_TRADE_WON = 1_000_000_000  # 10억원 (kojiro 500억/10억 정합, raw.acml_tr_pbmn 원 단위)

# 사이클 263 → cycle283 (2026-09-11, 사용자 결정 D1) — 오늘봉(확정 전 잠정봉) 커트오프.
# 근거 = **그날 거래가 끝나는 시각**이다. 2026-09-14 부터 KRX 애프터마켓(16:00~20:00
# 실시간 체결)이 신설되고 시간외 단일가(16:00~18:00)가 폐지돼 거래가 20:00 에 끝난다.
# 종전 15:40(= 마감 동시호가 흡수 마진)은 **그 뒤의 모든 적재 실행**(정기·재기동
# immediate·`force=True`)이 부분 거래량 봉을 확정봉으로 받아들이게 했다 — 09-11(금)
# 사고의 직접 원인(16:14 재기동이 1,005종목 부분봉 저장 → 18:10 정기가 908종목 skip;
# 40종목 대조 중앙값 +0.51%, 최대 +13.97%). 일봉 OHLC 는 15:30 에 확정되지만
# 거래량·거래대금은 시간외 거래 동안 계속 증가한다(6종목 전수 실측).
# ⚠️ "KIS 일봉이 20:00 직후 확정되는가" 는 아직 **미실측 가설**이다
# (`docs/market-changes-2026-09-14.md` §2/§4-1). 어긋나면 이 상수와 scheduler 의 일봉
# 적재 시각을 함께 뒤로 민다 — 부등식 `커트오프 ≤ 적재 < 정산` 만 지키면 상수 2개 조정이다.
# scanner **전용** 상수다 — 값이 같아 보여도 scheduler 의 매매/보드 시각 상수를 재사용하지
# 않는다: 매수 보드 시각 변경이 적재 규약을 딸려 바꾸는 커플링을 끊는다(tradable_boards ↔
# 청산 규약 커플링을 끊어 둔 기존 원칙과 같은 이유).
_DAILY_LOAD_TODAY_BAR_CUTOFF = _dtime(20, 0)

# 사이클 273 D5 — 보유/익일청산 강제 포함 관측 마커 (실행당 1행, 사이클 237 교훈 — 종목당 emit 금지)
_DAILY_LOAD_PROTECTED_FORCED_MARKER = "[daily_load_protected_forced]"


def _drop_today_bars(
    candles: list[dict], *, now_kst: datetime, today: date
) -> list[dict]:
    """확정 전 오늘봉을 걸러낸다 (사이클 263 · 커트오프 cycle283, 순수 함수 — 입력 비파괴).

    규칙 (`now_kst` 는 호출부가 **루프 밖에서 1회** 계산한다 — 19:59 에 시작해 20:02 에
    끝나는 실행이 종목마다 다른 기준을 쓰면 안 된다):
    - `now_kst` < 20:00 → `bas_dd >= today` 폐기 (장 전 껍데기 봉 · 장중/시간외 부분봉)
    - `now_kst` >= 20:00 → `bas_dd > today` 만 폐기 (시계 왜곡 방어)
    - `bas_dd` 파싱 불가/부재 → **보존** (fail-open — 판정 실패가 곧 데이터 유실이 되면 안 된다)

    ⚠️ 판정 기준은 **시각 단독**이다. "거래량 0 ∧ OHLC 평탄"(데이터 기준)으로 바꾸지 말 것.
    반증 2건 — (1) 장중 재시작이 만드는 부분봉은 거래량>0·비평탄이라 데이터 기준을 확정봉인
    척 통과한다(껍데기보다 나쁘다: 평탄하지 않아 눈에 안 띈다) (2) 거래정지 종목의 *진짜*
    평탄 확정봉(하루 1~8건)을 저녁 적재에서 죽여 그 날짜 행을 영영 못 갖게 한다. 시각 기준은 둘
    다 자동 처리하고 진짜 무거래봉을 정의상 100% 보존한다.
    """
    today_ymd = today.strftime("%Y%m%d")
    drop_from_today = now_kst.time() < _DAILY_LOAD_TODAY_BAR_CUTOFF
    kept: list[dict] = []
    for candle in candles:
        raw_dd = candle.get("stck_bsop_date") if isinstance(candle, dict) else None
        bas_dd = str(raw_dd or "")
        if len(bas_dd) == 8 and bas_dd.isdigit():
            drop = bas_dd >= today_ymd if drop_from_today else bas_dd > today_ymd
            if drop:
                continue
        kept.append(candle)
    return kept


def _is_daily_load_universe(row: dict) -> bool:
    """일봉 적재 유니버스 자격 판정 — mcap>=500억(억원) & trade>=20억(원).

    index(is_kospi200/is_kosdaq150) 는 호출부에서 별도 OR 처리 — 여기선
    시총/거래대금 자격만 판정. raw 부재/비숫자 → graceful False
    (list_by_filter 패턴 답습, 사이클 108).
    """
    raw = row.get("raw") or {}
    try:
        mcap_ok = int(raw.get("hts_avls") or 0) >= _DAILY_LOAD_MIN_MCAP_EOK
        trade_ok = int(raw.get("acml_tr_pbmn") or 0) >= _DAILY_LOAD_MIN_TRADE_WON
    except (ValueError, TypeError):
        return False
    return mcap_ok and trade_ok


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
    # 사이클 263 — 오늘봉 필터 판정 시각은 **함수 진입 시 1회**(stock_master 페이징 *앞*).
    # 루프 중 시계가 커트오프를 넘어도 규칙을 유지한다 — 15:39 에 진입해 15:42 에 끝나는
    # 실행이 종목마다 다른 기준을 쓰면 안 되고, list_all 페이징 지연이 판정을 뒤집어서도
    # 안 된다(계약 C2 "함수 진입 시각").
    load_now_kst = datetime.now(KST_TZ)
    summary: dict = {
        "total": 0,
        "fetched": 0,
        "upserted_rows": 0,
        "skipped_fresh": 0,
        "failed": 0,
        "db_write_failures": 0,  # 사이클 126 영역 4 — upsert_batch 실패 카운터 분리
        "elapsed_ms": 0,
        "mode": "mixed",  # 백필/증분 혼합
    }

    # 사이클 127 — 진행 state hook (fire-and-forget + 5초 폴링)
    from src.engine import refresh_progress as _rp

    _rp.start_progress("daily", total=0)

    # stock_master 전체 ticker 조회 (사이클 106 lifecycle 의존성)
    # offset 페이징 — limit=1000 단위 (Supabase 기본 한도)
    all_tickers: list[str] = []

    # 사이클 273 D5 — 보유/익일청산 종목 강제 포함 (spec §3). "지우는 쪽(16:15 purge)은
    # 보호하는데 채우는 쪽(16:00 load)은 보호하지 않는다" 비대칭 시정 — 자격을 못 넘긴
    # 날마다 그날 봉을 잃던 004690(삼천리) 실사례. C2 fail-open: 판정 실패는 현행
    # (is_index or is_qualifier) 집합 그대로 진행한다. C4: 6자리 숫자 ticker 만 보호 대상
    # (진입 게이트 비대칭 규약 — ETF/신주인수권/오염 문자열은 제외).
    try:
        _protected_raw = _collect_protected_tickers_for_scanner()
    except Exception:
        logger.debug(
            "[daily_load_protected_forced] 보호 집합 조회 실패 graceful", exc_info=True,
        )
        _protected_raw = set()
    protected_tickers: set[str] = {
        t for t in _protected_raw
        if isinstance(t, str) and len(t) == 6 and t.isdigit()
    }
    forced_in_universe_count = 0

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
            if not (ticker and len(ticker) == 6 and ticker.isdigit()):
                continue
            # 지수 편입 = is_kospi200 OR is_kosdaq150 (플래그 키 부재 mock/legacy row 는
            # falsy → 비지수 취급). 사이클 153 의 list_all `.select("*")` 가 두 컬럼을
            # 이미 실어 오므로 별도 쿼리 0건이다. 🔴 사이클 302 이후 이 판정은 **적재
            # 대상 여부**에만 쓴다 — backfill 깊이는 지수 소속과 무관하다.
            is_index = bool(row.get("is_kospi200") or row.get("is_kosdaq150"))
            # 사이클 206 — 유니버스 한정 적재: index(donchian/VCP) ∪
            # mcap500억&trade20억(VB/LTV/BFB 자격, BFB 최저 정합). 비유니버스는
            # 전략 스캔 대상이 아니므로 일봉 캐시 불요 (Supabase 용량 낭비 차단).
            # 재진입(유니버스 편입) 시 다음 load 가 backfill 로 자동 채움.
            is_qualifier = _is_daily_load_universe(row)
            # 사이클 273 D5 — 보호 종목은 자격과 무관하게 강제 포함.
            is_protected = ticker in protected_tickers
            if is_index or is_qualifier or is_protected:
                all_tickers.append(ticker)
                if is_protected and not (is_index or is_qualifier):
                    forced_in_universe_count += 1
        if len(rows) < PAGE_SIZE:
            break
        page += 1

    # 사이클 273 D5 — list_all 페이징이 통째로 실패(G-273D-2)하거나 보호 종목이 어느
    # 페이지에도 실리지 않은 경우까지 대비한 합집합. C5b: 이미 유니버스 안인 보호 종목은
    # 중복 append 되지 않는다(집합 차집합으로만 추가).
    forced_extra_tickers = protected_tickers - set(all_tickers)
    if forced_extra_tickers:
        all_tickers.extend(sorted(forced_extra_tickers))

    _protected_marker_tickers = ",".join(sorted(protected_tickers)[:20]) or "-"
    logger.info(
        "%s protected=%d forced_in_universe=%d forced_extra=%d tickers=%s",
        _DAILY_LOAD_PROTECTED_FORCED_MARKER,
        len(protected_tickers), forced_in_universe_count, len(forced_extra_tickers),
        _protected_marker_tickers,
    )

    summary["total"] = len(all_tickers)
    _rp.update_progress("daily", total=len(all_tickers))

    # 사이클 126 영역 4 — 진단 강화: 함수 진입 시 candidates 가시화
    logger.info(
        "[stock_master_daily_load_begin] candidates=%d force=%s",
        len(all_tickers), force,
    )

    if not all_tickers:
        summary["elapsed_ms"] = int((time.monotonic() - start) * 1000)
        logger.warning("[stock_master_daily_load] stock_master 빈 영역 — 적재 skip")
        _rp.finish_progress(
            "daily", "completed",
            total=summary["total"],
            processed=0,
            updated=summary["upserted_rows"],
            skipped=summary["skipped_fresh"],
            failed=summary["failed"],
        )
        return summary

    # 오늘 KST 날짜 (점진 적재 fresh skip 기준 + 사이클 263 오늘봉 필터 비교자).
    # ⚠️ `load_now_kst` 를 **먼저** 읽는 순서가 계약이다 — 두 읽기 사이 KST 자정이 지나도
    # 판정은 keep 쪽으로만 기운다(역순이면 drop 쪽으로 기울어 확정봉을 잃는다).
    from src.db._kst import today_kst
    today = today_kst()

    filter_dropped_rows = 0
    filter_dropped_tickers = 0
    filter_errors = 0

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

        # 사이클 302 — **적재 대상이면 누구나** DB < 225 일 때 225일 분할 backfill(날짜
        # 윈도우 ×3)을 탄다. 종전에는 지수(KOSPI200 ∪ KOSDAQ150) 종목만 이 분기에 들어
        # 비지수 1,526 종목이 전부 125행 안팎에 머물렀고, 그 깊이에서는
        # `effective_ema_long = min(ema_long, 보유 − 20 − 5)` 가 74~121 로 잡혀 VCP 의
        # 중기↔장기 간격이 10 안팎이 된다(정배열 판정이 동전던지기, 2026-09-18 실측).
        #
        # 🔴 **비용은 1회성이다.** `existing_count >= 225` 가 되면 아래 증분(7일·1콜)
        # 분기로 넘어가고 retention 390 달력일(≈261 영업일)이 225 아래로 떨어뜨리지
        # 않으므로 수렴 상태가 유지된다 — 정상 운영의 KIS 호출량은 종목당 1콜 그대로다
        # (가드 `test_cycle302_backfill_scope_expansion.py::G-302-3`). 첫 채움만
        # 종목당 3콜이라 20:30 정기 실행이 아니라 수동 trigger 로 돌린다
        # (`TIME_QUOTE_TOKEN_REFRESH`(20:45) 불변식 창이 20:35 부터다).
        #
        # ⚠️ 아래 `< _DAILY_LOAD_INCREMENTAL_THRESHOLD(50)` 분기는 225 > 50 인 한
        # **도달 불가**한 구조적 폴백이다(신규 상장도 첫 밤에 225일을 탄다). 목표 깊이를
        # 50 아래로 되돌리면 되살아난다 — 가드 G-302-8b 가 그 관계를 핀한다.
        use_deep_backfill = existing_count < _DAILY_LOAD_VCP_BACKFILL_DAYS

        if use_deep_backfill:
            fetch_days = _DAILY_LOAD_VCP_BACKFILL_DAYS  # 목표 깊이 225일 분할 backfill
            backfill_count += 1
        elif existing_count < _DAILY_LOAD_INCREMENTAL_THRESHOLD:
            fetch_days = _DAILY_LOAD_FETCH_DAYS  # 백필 모드 (T-100일)
            backfill_count += 1
        else:
            fetch_days = 7  # 증분 모드 (T-7일, 영업일 마진)
            incremental_count += 1

        # 3) KIS 호출 — 목표 깊이 backfill 은 분할 fetch (사이클 172),
        #    그 외 fetch_daily_candles (사이클 14)
        try:
            from src.api import condition as _cond
            if use_deep_backfill:
                candles = await _cond.fetch_daily_candles_backfill(
                    ticker, total_days=_DAILY_LOAD_VCP_BACKFILL_DAYS
                )
            else:
                candles = await _cond.fetch_daily_candles(ticker, days=fetch_days)
        except Exception:
            # 사이클 88 G-REJECT graceful — 다음 ticker 진행
            logger.exception(
                "[stock_master_daily_load] KIS 일봉 호출 실패 graceful ticker=%s deep=%s",
                ticker, use_deep_backfill,
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

        # 3-b) 사이클 263 — 확정 전 오늘봉 폐기. 두 fetch 분기의 합류점이자 `fetched` 증가
        # *뒤* · upsert *앞* 이라, `fetched`("KIS 응답을 받았다") 와 `failed`(KIS 실패 전용)
        # 카운터 의미가 보존된다. 판정 예외는 fail-open — 원본 전량 upsert 유지
        # (fail-closed 는 P0-1 유령 키가 두 전략을 전 기간 체결 0건으로 만든 그 방향이다).
        try:
            kept = _drop_today_bars(candles, now_kst=load_now_kst, today=today)
            if len(kept) != len(candles):
                filter_dropped_rows += len(candles) - len(kept)
                filter_dropped_tickers += 1
            candles = kept
        except Exception:
            if filter_errors == 0:  # WARNING 은 실행당 1행 (종목당 폭주 차단)
                logger.warning(
                    "[daily_load_today_filter_skipped] ticker=%s reason=filter_error",
                    ticker, exc_info=True,
                )
            filter_errors += 1  # 건수는 계속 센다 — 요약 마커가 fail-open 규모를 노출

        # 4) DB batch upsert (사이클 88 G-REJECT graceful 내장)
        # 필터가 전량 제거했으면 upsert 를 부르지 않는다 (fetched 는 증가한 채로 유지 —
        # 그 종목을 실제로 fetch 한 것은 사실이다).
        if candles:
            try:
                upserted = await stock_master_daily.upsert_batch(ticker, candles)
                summary["upserted_rows"] += upserted
            except Exception:
                # 사이클 126 영역 4 — db_write_failures 분리 카운터 (KIS fetch 실패와 구분)
                logger.warning(
                    "[stock_master_daily_load_skip] ticker=%s reason=upsert_batch_failed",
                    ticker,
                )
                summary["db_write_failures"] += 1

        # 5) Rate Limit sleep (사이클 17/83/91/97/107 답습)
        await asyncio.sleep(_DAILY_LOAD_RATE_LIMIT_SLEEP_SECS)

        # 사이클 127 — 진행 state 갱신 (매 ticker 처리 후)
        _rp.update_progress(
            "daily",
            processed=idx + 1,
            updated=summary["upserted_rows"],
            skipped=summary["skipped_fresh"],
            failed=summary["failed"] + summary["db_write_failures"],
        )

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

    # 사이클 263 — 오늘봉 필터 관측: **실행당 1행**. 종목당 emit 은 하루 1,000행 폭주다
    # (사이클 237 donchian 청산 로그 폭주 시정의 교훈).
    # ⚠️ 이 마커의 의미는 **3세대** 다 — 원본 / cycle263 / cycle283. 세대 간 합산 금지:
    #   · cycle263 — 16:00 실행의 `skipped_fresh` 가 ~1,000 → ~0 으로 반전
    #   · cycle283 — 커트오프 15:40 → 20:00 이라 **15:40~20:00 구간 실행의 `mode` 가
    #     keep → drop 으로 뒤집힌다**. `dropped_rows`·`tickers_affected` 도 같은 이유로
    #     세대 간 합산 불가다.
    logger.info(
        "[daily_load_today_bar_filter] mode=%s cutoff=%s now=%s today=%s "
        "dropped_rows=%d tickers_affected=%d filter_errors=%d",
        "drop" if load_now_kst.time() < _DAILY_LOAD_TODAY_BAR_CUTOFF else "keep",
        _DAILY_LOAD_TODAY_BAR_CUTOFF.strftime("%H:%M"),
        load_now_kst.strftime("%H:%M"),
        today.isoformat(),
        filter_dropped_rows,
        filter_dropped_tickers,
        filter_errors,  # >0 = fail-open 발생 (dropped_rows=0 과 "버릴 봉 없음" 을 구분)
    )

    summary["elapsed_ms"] = int((time.monotonic() - start) * 1000)
    # mode 결정: 백필 우세 → "full" / 증분 우세 → "incremental" / 혼합 → "mixed"
    if backfill_count > 0 and incremental_count == 0:
        summary["mode"] = "full"
    elif incremental_count > 0 and backfill_count == 0:
        summary["mode"] = "incremental"
    else:
        summary["mode"] = "mixed"

    # 사이클 127 — 완료 시 finish_progress (정상 종료)
    _rp.finish_progress(
        "daily", "completed",
        total=summary["total"],
        processed=len(all_tickers),
        updated=summary["upserted_rows"],
        skipped=summary["skipped_fresh"],
        failed=summary["failed"] + summary["db_write_failures"],
    )

    return summary


# ---------------------------------------------------------------------------
# 사이클 C3 (2026-07-15) — 퀀트 재무필터 관찰 전용 배포 (Phase 1)
# 산출물 (a): 주1회 재무 적재 (`_stock_master_financial_load_once`)
# _stock_master_daily_load_once 답습 — 순수 추가 함수, scan_stocks/subscribe
# _filtered_stocks 본체 diff 0 (momentum 발사 경로 byte-identical, G-3 SAFETY).
# ---------------------------------------------------------------------------
_FINANCIAL_LOAD_RATE_LIMIT_SLEEP_SECS = 0.05  # 50ms (사이클 17 KIS LMS chain 답습)


async def _stock_master_financial_load_once(force: bool = False) -> dict:
    """사이클 C3 — 재무 데이터 (마법공식/F-Score-7) 주1회 적재.

    유니버스 = `stock_master.list_by_filter` (index ∪ 시총500억&거래대금20억,
    사이클 206 `_is_daily_load_universe` 자격과 동일 856종목 규모) — daily load
    와 동일 유니버스 재사용.

    ticker 별 `max_stac_yymm` 신선도 skip (당분기 이미 적재 시) → 미신선 시
    `fetch_all_financials` → `upsert_financial_batch`. graceful (사이클 88
    G-REJECT — 개별 ticker 실패 시 failed++ 후 다음 ticker 진행).

    Returns:
        summary dict: {total, updated, skipped, failed, elapsed_ms}
    """
    import time

    from src.api import finance as _finance
    from src.db import stock_master as _sm_mod
    from src.db import stock_master_financial as _smf_mod
    from src.engine import refresh_progress as _rp

    start = time.monotonic()
    summary: dict = {
        "total": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "elapsed_ms": 0,
    }

    _rp.start_progress("financial", total=0)

    # 유니버스 = index ∪ 시총500억&거래대금20억 자격 (사이클 206 daily load 자격 답습)
    try:
        rows = await _sm_mod.list_by_filter(
            min_market_cap=_DAILY_LOAD_MIN_MCAP_EOK * 100_000_000,
            min_trade_amount=_DAILY_LOAD_MIN_TRADE_WON,
            is_kospi200=True,
            is_kosdaq150=True,
            limit=1000,
        )
    except Exception:
        logger.exception(
            "[stock_master_financial_load] list_by_filter 실패 graceful"
        )
        rows = []

    tickers: list[str] = []
    for row in rows:
        ticker = row.get("ticker", "")
        if ticker and len(ticker) == 6 and ticker.isdigit():
            tickers.append(ticker)

    summary["total"] = len(tickers)
    _rp.update_progress("financial", total=len(tickers))

    logger.info(
        "[stock_master_financial_load_begin] candidates=%d force=%s",
        len(tickers), force,
    )

    if not tickers:
        summary["elapsed_ms"] = int((time.monotonic() - start) * 1000)
        logger.warning("[stock_master_financial_load] 유니버스 빈 영역 — 적재 skip")
        _rp.finish_progress(
            "financial", "completed",
            total=0, processed=0, updated=0, skipped=0, failed=0,
        )
        return summary

    for idx, ticker in enumerate(tickers):
        if not force:
            # 신선도 게이트 — max_stac_yymm 존재(=이미 적재된 재무 데이터 有) 시
            # 당분기 이미 적재된 것으로 간주해 skip. 재무제표는 분기/연 단위로만
            # 갱신되므로(주1회 task) 존재 여부 게이트가 주1회 정합에 충분하다.
            try:
                latest = await _smf_mod.max_stac_yymm(ticker)
            except Exception:
                latest = None
            if latest is not None:
                summary["skipped"] += 1
                continue

        try:
            fin_rows = await _finance.fetch_all_financials(ticker)
        except Exception:
            logger.warning(
                "[stock_master_financial_load_skip] ticker=%s reason=fetch_failed",
                ticker,
            )
            summary["failed"] += 1
            await asyncio.sleep(_FINANCIAL_LOAD_RATE_LIMIT_SLEEP_SECS)
            continue

        if not fin_rows:
            summary["failed"] += 1
            await asyncio.sleep(_FINANCIAL_LOAD_RATE_LIMIT_SLEEP_SECS)
            continue

        try:
            upserted = await _smf_mod.upsert_financial_batch(ticker, fin_rows)
            summary["updated"] += upserted
        except Exception:
            logger.warning(
                "[stock_master_financial_load_skip] ticker=%s reason=upsert_failed",
                ticker,
            )
            summary["failed"] += 1

        await asyncio.sleep(_FINANCIAL_LOAD_RATE_LIMIT_SLEEP_SECS)

        _rp.update_progress(
            "financial",
            processed=idx + 1,
            updated=summary["updated"],
            skipped=summary["skipped"],
            failed=summary["failed"],
        )

        if (idx + 1) % 500 == 0:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.info(
                "[stock_master_financial_load] 진행 %d/%d updated=%d "
                "skipped=%d failed=%d elapsed_ms=%d",
                idx + 1, len(tickers),
                summary["updated"], summary["skipped"], summary["failed"], elapsed,
            )

    summary["elapsed_ms"] = int((time.monotonic() - start) * 1000)

    logger.info(
        "[stock_master_financial_load_summary] total=%d updated=%d skipped=%d failed=%d",
        summary["total"], summary["updated"], summary["skipped"], summary["failed"],
    )

    _rp.finish_progress(
        "financial", "completed",
        total=summary["total"],
        processed=len(tickers),
        updated=summary["updated"],
        skipped=summary["skipped"],
        failed=summary["failed"],
    )

    return summary


# 사이클 126 영역 3 — basics refresh 상수 (사이클 122 일봉 task 답습)
_BASICS_REFRESH_RATE_LIMIT_SLEEP_SECS = 0.05  # 50ms (사이클 17 KIS LMS chain 답습)


async def _stock_master_basics_refresh_once(force: bool = False) -> dict:
    """사이클 126 영역 3 — KIS CTPF1002R 매스 보강 자동 task.

    KRX 1차 폴백 (`_full_universe_load_krx_primary`) 의 nxt_tradable/krx_halted/admin_item
    하드코딩 False 결함을 KIS CTPF1002R 호출로 실제 값 보강.

    매매 hot path lazy 호출 (`_strategy_exchange_async` / `_execute_next_day_clear`)
    만으론 매매 0 영역 ticker 영원히 False 영속 — 일일 1회 매스 보강 의무.

    Returns:
        summary dict: {total, updated, skipped, failed, elapsed_ms}

    영속 의무:
    - 사이클 17 KIS LMS chain 안전 (50ms sleep)
    - 사이클 38 명문화 (scanner 단계 = 매수 진입 전, 매도 hot path 무관)
    - 사이클 88 G-REJECT graceful (개별 ticker 실패 → continue + failed++)
    - 사이클 107 CTPF1002R + FHKST01010100 merge (raw JSONB 5 키 자동 포함)
    """
    import time
    from src.db import stock_master

    # 사이클 127 — 진행 state hook (fire-and-forget + 5초 폴링)
    from src.engine import refresh_progress as _rp

    # 사이클 144 — graceful_failed 카운터 영역 영구 영속 reset (카드 #27 LOW)
    # 단일 task 영역 영구 영속 측정 의무 영구 영속.
    from src.api.condition import (
        get_graceful_failed_counts,
        reset_graceful_failed_counts,
    )
    reset_graceful_failed_counts()

    _rp.start_progress("basics", total=0)

    start = time.monotonic()
    summary: dict = {
        "total": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "graceful_failed": {"fhkst01010100_failed": 0},  # 사이클 144 — 카드 #27
        "elapsed_ms": 0,
    }

    # stock_master 전체 ticker 페이징 조회 (사이클 122 답습)
    all_tickers: list[str] = []
    # 사이클 176 — 기존 raw 보관 (거래대금 결손 시정). upsert 전 머지로
    # cycle 145 _ZERO_VALUE_SKIP_KEYS (개장 전 0 skip = 거래대금/거래량 등) 보존.
    existing_raw_by_ticker: dict[str, dict] = {}
    page = 0
    PAGE_SIZE = 1000
    while True:
        try:
            rows = await stock_master.list_all(limit=PAGE_SIZE, offset=page * PAGE_SIZE)
        except Exception:
            logger.exception(
                "[stock_master_basics_refresh] stock_master.list_all 실패 graceful page=%d",
                page,
            )
            break
        if not rows:
            break
        for row in rows:
            ticker = row.get("ticker", "")
            if ticker and len(ticker) == 6 and ticker.isdigit():
                all_tickers.append(ticker)
                existing_raw_by_ticker[ticker] = row.get("raw") or {}
        if len(rows) < PAGE_SIZE:
            break
        page += 1

    summary["total"] = len(all_tickers)
    _rp.update_progress("basics", total=len(all_tickers))
    logger.info(
        "[stock_master_basics_refresh_begin] candidates=%d force=%s",
        len(all_tickers), force,
    )

    if not all_tickers:
        summary["elapsed_ms"] = int((time.monotonic() - start) * 1000)
        logger.warning("[stock_master_basics_refresh] stock_master 빈 영역 — 보강 skip")
        _rp.finish_progress(
            "basics", "completed",
            total=0, processed=0, updated=0, skipped=0, failed=0,
        )
        return summary

    for idx, ticker in enumerate(all_tickers):
        # KIS CTPF1002R + FHKST01010100 merge (사이클 107 raw 보강 영속)
        try:
            from src.api.condition import inquire_stock_basics
            basics = await inquire_stock_basics(ticker)
        except Exception:
            logger.warning(
                "[stock_master_basics_refresh_skip] ticker=%s reason=kis_fetch_failed",
                ticker,
            )
            summary["failed"] += 1
            # Rate Limit sleep 보장 (실패 시도 자체로 KIS 호출 발생)
            await _asyncio.sleep(_BASICS_REFRESH_RATE_LIMIT_SLEEP_SECS)
            continue

        if not basics:
            summary["skipped"] += 1
            await _asyncio.sleep(_BASICS_REFRESH_RATE_LIMIT_SLEEP_SECS)
            continue

        # 사이클 176 — 기존 raw 머지 보존 (거래대금 결손 시정).
        # 개장 전 FHKST acml_tr_pbmn=0 → inquire_stock_basics 가 cycle 145
        # _ZERO_VALUE_SKIP_KEYS 를 merged_raw 에서 skip → basics.raw 거래대금 부재.
        # upsert_one 이 raw 통째 교체하므로, 기존 DB raw 와 머지하여 skip 된 키
        # (거래대금/거래량 등) 를 기존 값에서 보존. 새 키 우선 ({**기존, **신규}).
        # bare-object (model_copy/raw 부재) graceful — 머지 skip (기존 테스트 회귀 0).
        _new_raw = getattr(basics, "raw", None)
        if isinstance(_new_raw, dict):
            _prev_raw = existing_raw_by_ticker.get(ticker)
            if isinstance(_prev_raw, dict) and _prev_raw:
                basics = basics.model_copy(
                    update={"raw": {**_prev_raw, **_new_raw}}
                )

        # DB upsert (사이클 88 G-REJECT graceful)
        try:
            from src.db import stock_master as _sm
            await _sm.upsert_one(basics)
            summary["updated"] += 1
        except Exception:
            logger.warning(
                "[stock_master_basics_refresh_skip] ticker=%s reason=upsert_failed",
                ticker,
            )
            summary["failed"] += 1

        # Rate Limit sleep (사이클 17 KIS LMS chain 답습)
        await _asyncio.sleep(_BASICS_REFRESH_RATE_LIMIT_SLEEP_SECS)

        # 사이클 127 — 진행 state 갱신 (매 ticker 처리 후)
        _rp.update_progress(
            "basics",
            processed=idx + 1,
            updated=summary["updated"],
            skipped=summary["skipped"],
            failed=summary["failed"],
        )

        # 진행 상황 emit — 500건마다 (운영 가시화)
        if (idx + 1) % 500 == 0:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.info(
                "[stock_master_basics_refresh] 진행 %d/%d updated=%d "
                "skipped=%d failed=%d elapsed_ms=%d",
                idx + 1, len(all_tickers),
                summary["updated"], summary["skipped"],
                summary["failed"], elapsed,
            )

    summary["elapsed_ms"] = int((time.monotonic() - start) * 1000)

    # 사이클 144 — graceful_failed 카운터 영역 영구 영속 수집 (카드 #27 LOW)
    graceful_failed_counts = get_graceful_failed_counts()
    fhkst_failed = graceful_failed_counts.get("fhkst01010100_failed", 0)
    summary["graceful_failed"] = {"fhkst01010100_failed": fhkst_failed}

    logger.info(
        "[stock_master_basics_refresh_summary] total=%d updated=%d "
        "skipped=%d failed=%d graceful_failed_fhkst=%d elapsed_ms=%d",
        summary["total"], summary["updated"],
        summary["skipped"], summary["failed"],
        fhkst_failed,
        summary["elapsed_ms"],
    )

    # 사이클 127 — 완료 시 finish_progress (정상 종료)
    _rp.finish_progress(
        "basics", "completed",
        total=summary["total"],
        processed=len(all_tickers),
        updated=summary["updated"],
        skipped=summary["skipped"],
        failed=summary["failed"],
    )

    return summary


# ============================================================
# 사이클 129 — KIS 종목 마스터 파일 (kospi_code.mst / kosdaq_code.mst)
# Q4=A 마스터 우선 + Q5=C 전수 보존 + Q6=C master_raw 별도 컬럼
#
# 사이클 167 — 시총 헬퍼 3개 (market_cap_master_to_millions /
# validate_market_cap_consistency / get_market_cap_millions) dead code 폐기.
# 사이클 129 도입 이후 production 호출 0건 (서로만 호출하는 폐쇄 그래프). 실제
# 시총 필터는 list_by_filter / list_paged_by_filter 가 직접 수행 (사이클 166 억원
# 정합 완료). AST 영구 가드 = tests/unit/ast/test_cycle167_ast_no_dead_market_cap_funcs.py.
# ============================================================


def _is_master_blocked_for_entry(
    master_raw: dict, raw: dict | None = None
) -> tuple[bool, str]:
    """1단계 차단 — 11건 매수 진입 차단 (사이클 129 7 + 사이클 155 4).

    master_raw + raw OR — 어느 한쪽이라도 매칭되면 차단. 부재 측은 평가 생략.

    사이클 129 (master_raw, 7건):
    - trht_yn / sltr_yn / mang_issu_yn / ssts_hot_yn / stange_runup_yn
    - mrkt_alrm_cls_code >= "02" / invt_alrm_yn (KOSDAQ)

    사이클 155 (raw=FHKST01010100, 4건):
    - mrkt_warn_cls_code >= "02" / short_over_yn
    - sltr_yn (FHKST) / temp_stop_yn

    사이클 203 — 종목상태 코드 기반 차단 완전 제거. 운영 DB 실측 결과
    "55만 정상" 가정이 틀림 (57=정상/그외 91%, 58=신선도 잔재, 51=정상
    ETF/스팩/우선주). KIS 가 코드값 의미를 공식 배포하지 않아 하드코딩
    블록리스트는 회귀 위험. 위험 종목은 전용 플래그(시장경고/단기과열/
    정리매매/임시정지)가 실측 100% 커버. merge/적재는 불변
    (raw 에 해당 코드값은 계속 저장, 차단 기준으로만 미사용).

    사이클 204 — 투자주의(시장경고 01) 차단 해제. KIS 삼각검증
    00=정상/01=투자주의/02=투자경고/03=투자위험 확인 결과, 차단 대상
    index 9종목 전부 우량 대형주 실증 (급등 → 투자주의 지정 → 돌파전략
    후보에서 제거되는 역설). 투자경고(02)/투자위험(03) 는 계속 차단.
    """
    if master_raw and isinstance(master_raw, dict):
        if master_raw.get("trht_yn") == "Y":
            return True, "거래정지 (trht_yn=Y)"
        if master_raw.get("sltr_yn") == "Y":
            return True, "정리매매 (sltr_yn=Y)"
        if master_raw.get("mang_issu_yn") == "Y":
            return True, "관리종목 (mang_issu_yn=Y)"
        if master_raw.get("ssts_hot_yn") == "Y":
            return True, "공매도과열 (ssts_hot_yn=Y)"
        if master_raw.get("stange_runup_yn") == "Y":
            return True, "이상급등 (stange_runup_yn=Y)"

        # 시장경고 02:경고 / 03:위험 영역 차단
        mrkt_alrm = master_raw.get("mrkt_alrm_cls_code", "00")
        if isinstance(mrkt_alrm, str) and mrkt_alrm >= "02":
            return True, f"시장경고 ({mrkt_alrm})"

        # KOSDAQ 전용 — 투자주의환기
        if master_raw.get("invt_alrm_yn") == "Y":
            return True, "투자주의환기 (invt_alrm_yn=Y, KOSDAQ)"

    # 사이클 155 — FHKST01010100 raw 분기 (4 키, 사이클 204 투자주의 해제).
    if raw and isinstance(raw, dict):
        mrkt_warn = raw.get("mrkt_warn_cls_code", "00")
        if isinstance(mrkt_warn, str) and mrkt_warn >= "02":
            return True, f"FHKST 시장경고 ({mrkt_warn})"
        if (raw.get("short_over_yn") or "").strip().upper() == "Y":
            return True, "단기과열 (short_over_yn=Y, FHKST)"
        if (raw.get("sltr_yn") or "").strip().upper() == "Y":
            return True, "정리매매 (sltr_yn=Y, FHKST)"
        if (raw.get("temp_stop_yn") or "").strip().upper() == "Y":
            return True, "임시 정지 (temp_stop_yn=Y, FHKST)"

    return False, ""


async def apply_master_block_filter(
    tickers: list[str],
    *,
    protected_tickers: set[str] | None = None,
) -> tuple[list[str], list[dict]]:
    """1단계 진입 차단 11건 hook 공통 헬퍼 (사이클 157, 사이클 203 iscd 제거, 사이클 204 투자주의 해제).

    5 전략 (VB/LTV/donchian/BFB/VCP) 의 `_apply_master_block_filter_in_prepare`
    위임 대상. `_is_master_blocked_for_entry` 11건 (master_raw 7 + raw 4) 차단.

    영속 의무 매트릭스:
    - 사이클 32 R4 — 보유/익일청산 절대 보호 (protected_tickers 무조건 통과)
    - 사이클 38 명문화 — 매수 진입 *전* 영역 한정 (check_exit_signal 호출 0)
    - 사이클 41 — excluded = [{ticker, name, reason}] 한글 사유 영속
    - 사이클 81 G-AST1 — raw 영역 read-only 영속
    - 사이클 88 G-REJECT — stock_master.get 예외 graceful 통과
    - 사이클 129 master_raw 7건 + 사이클 155 raw 4건 = 11건 차단 (사이클 203 iscd 제거, 사이클 204 투자주의 해제)

    Args:
        tickers: 평가 대상 ticker 리스트.
        protected_tickers: 보유/익일청산 보호 set. None 시 빈 set (보호 없음).

    Returns:
        (survived, excluded). survived = list[str]. excluded = list[{ticker, name, reason}].
    """
    from src.db import stock_master as _sm_mod

    protected: set[str] = protected_tickers or set()
    survived: list[str] = []
    excluded: list[dict] = []

    for ticker in tickers:
        # 사이클 32 R4 — 보유/익일청산 절대 보호 (사이클 30 005935 매매 안전성 영속)
        if ticker in protected:
            survived.append(ticker)
            continue
        # stock_master 조회 — 예외 graceful 통과 (사이클 88 G-REJECT 답습)
        master_raw: dict = {}
        raw_dict: dict = {}
        try:
            basics = await _sm_mod.get(ticker)
            if basics and basics.raw:
                raw_dict = dict(basics.raw)
        except Exception:
            survived.append(ticker)
            continue
        try:
            master_raw_resp = await _sm_mod.get_master_raw(ticker)
            if master_raw_resp:
                master_raw = dict(master_raw_resp)
        except Exception:
            # graceful — master_raw 부재 시 raw 단독 평가
            pass

        blocked, reason = _is_master_blocked_for_entry(master_raw, raw_dict)
        if blocked:
            name = ""
            try:
                name = ticker_names.get(ticker, "") or ""
            except Exception:
                pass
            excluded.append({"ticker": ticker, "name": name, "reason": reason})
            continue
        survived.append(ticker)

    return survived, excluded


async def _stock_master_master_load_once(force: bool = True) -> dict:
    """사이클 129 — KIS 종목 마스터 파일 (KOSPI + KOSDAQ) 일괄 적재.

    16:30 KST cron task 영역 영구 영속:
    - KOSPI master 다운로드 → cp949 fixed-width 파싱 → master_raw upsert
    - KOSDAQ master 다운로드 → cp949 fixed-width 파싱 → master_raw upsert
    - raw 영역 변경 0 영속 (사이클 81 G-AST1 보호)
    - 사이클 127 refresh_progress hook + fire-and-forget 영속

    Args:
        force: 디폴트 True (사이클 120 force 영속 답습)

    Returns:
        summary dict: {kospi_count, kosdaq_count, total, updated, failed, elapsed_ms}
    """
    import time

    from src.api import kis_master as _kis_master
    from src.db import stock_master as _sm
    from src.engine import refresh_progress as _rp

    _rp.start_progress("master", total=0)

    start = time.monotonic()
    summary: dict = {
        "kospi_count": 0,
        "kosdaq_count": 0,
        "total": 0,
        "updated": 0,
        "failed": 0,
        "elapsed_ms": 0,
    }

    # KOSPI 다운로드 (graceful)
    kospi_records: list[dict] = []
    try:
        kospi_records = await _kis_master.download_kospi_master()
        summary["kospi_count"] = len(kospi_records)
    except Exception as exc:
        logger.warning(
            "[stock_master_master_load] KOSPI 다운로드 실패 graceful: %s", exc
        )

    # KOSDAQ 다운로드 (graceful)
    kosdaq_records: list[dict] = []
    try:
        kosdaq_records = await _kis_master.download_kosdaq_master()
        summary["kosdaq_count"] = len(kosdaq_records)
    except Exception as exc:
        logger.warning(
            "[stock_master_master_load] KOSDAQ 다운로드 실패 graceful: %s", exc
        )

    # 사이클 153 — KOSPI/KOSDAQ source 영역 영구 영속 분리
    # 각 record 영역에 source 키 명시 → upsert_master_raw 영역에서 분기 (사용자 결정 Q1=A 영구 영속)
    tagged_records: list[tuple[str, dict]] = (
        [("kospi", r) for r in kospi_records]
        + [("kosdaq", r) for r in kosdaq_records]
    )
    summary["total"] = len(tagged_records)
    _rp.update_progress("master", total=len(tagged_records))

    logger.info(
        "[stock_master_master_load_begin] kospi=%d kosdaq=%d total=%d force=%s",
        summary["kospi_count"], summary["kosdaq_count"], summary["total"], force,
    )

    if not tagged_records:
        summary["elapsed_ms"] = int((time.monotonic() - start) * 1000)
        logger.warning("[stock_master_master_load] 마스터 record 0건 — skip")
        _rp.finish_progress(
            "master", "completed",
            total=0, processed=0, updated=0, skipped=0, failed=0,
        )
        return summary

    # master_raw 일괄 upsert (사이클 81 G-AST1 영속 보호 = raw 변경 0)
    for idx, (source, record) in enumerate(tagged_records):
        ticker = (record.get("mksc_shrn_iscd") or "").strip()
        if not ticker or len(ticker) != 6 or not ticker.isdigit():
            summary["failed"] += 1
            continue

        # 사이클 153 — KOSPI200 / KOSDAQ150 지수 편입 판정 영역 영구 영속
        # 사이클 154 hotfix (2026-06-16) — kospi200_apnt_cls_code 정본 코드값 시정
        # 운영 DB 실측: "0"=1,597 미편입 / "1"~"9","A","B"=199 편입 ≈ KOSPI200 정합
        # 결함: bool("0")=True → 사이클 153 영역 1,596 종목 잘못 편입 (1,796 과대)
        is_kospi200 = False
        is_kosdaq150 = False
        if source == "kospi":
            code_val = (record.get("kospi200_apnt_cls_code") or "").strip()
            is_kospi200 = code_val not in ("", "0")
        elif source == "kosdaq":
            is_kosdaq150 = (record.get("ksq150_nmix_yn") or "").strip() == "Y"

        try:
            await _sm.upsert_master_raw(
                ticker, record,
                is_kospi200=is_kospi200,
                is_kosdaq150=is_kosdaq150,
            )
            summary["updated"] += 1
        except Exception as exc:
            logger.warning(
                "[stock_master_master_load_skip] ticker=%s reason=upsert_failed err=%s",
                ticker, exc,
            )
            summary["failed"] += 1

        # 사이클 127 — 진행 state 갱신 (500건마다)
        if (idx + 1) % 500 == 0:
            _rp.update_progress(
                "master",
                processed=idx + 1,
                updated=summary["updated"],
                failed=summary["failed"],
            )
            elapsed = int((time.monotonic() - start) * 1000)
            logger.info(
                "[stock_master_master_load] 진행 %d/%d updated=%d failed=%d elapsed_ms=%d",
                idx + 1, len(tagged_records),
                summary["updated"], summary["failed"], elapsed,
            )

    summary["elapsed_ms"] = int((time.monotonic() - start) * 1000)
    logger.info(
        "[stock_master_master_load_summary] kospi=%d kosdaq=%d total=%d "
        "updated=%d failed=%d elapsed_ms=%d",
        summary["kospi_count"], summary["kosdaq_count"], summary["total"],
        summary["updated"], summary["failed"], summary["elapsed_ms"],
    )

    _rp.finish_progress(
        "master", "completed",
        total=summary["total"],
        processed=len(tagged_records),
        updated=summary["updated"],
        failed=summary["failed"],
    )

    return summary
