"""사이클 67 = stale_manager.py 1,099L sub-module 분해 (Q1=A facade) — universe stale 가드.

사이클 32 R4 (2026-05-21): stale universe 가드 (보유/익일청산 절대 보호 영역).
사이클 61 Phase 2-A2 (2026-06-05): stale_manager.py 로 이전.
사이클 67 (2026-06-06): stale_manager.py 1,099L → 4 sub-module 분해 (카드 #14 MEDIUM).

절대 깨지 말 것:
- 함수 본체 변경 0 (라인 단위 동일, self.* → scheduler.* 치환만)
- 보유 종목 / 익일청산 종목 절대 제외 금지 (사전 가드 순서 보존)
- 상수 값 변경 0 (SoT: 이 파일이 UNIVERSE_LOW_VOLUME_THRESHOLD 의 단일 정의처)
- Q1 옵션 A 단방향: 이 파일은 stale_watcher_core 를 import 금지
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("src.engine.scheduler")  # 사이클 60 I1 영속 (caplog 호환)

# ── 상수 (SoT: 이 파일이 단일 정의처) ───────────────────────────────────────────
# 사이클 32 (R4, 2026-05-21) — universe stale 가드
UNIVERSE_LOW_VOLUME_THRESHOLD = 10_000      # 당일 누적 체결량 임계 (운영 1주 후 조정)

# MAX_STALE_RETRIES 는 stale_diagnostics.py 가 SoT.
# evaluate_universe_guard 에서 직접 사용하므로 여기서 import.
from src.engine.stale_diagnostics import MAX_STALE_RETRIES  # noqa: E402


# ── A2 1 함수 (사이클 61 Phase 2-A2 이주) ────────────────────────────────────────

async def evaluate_universe_guard(
    scheduler: Any, candidate_tickers: list[str]
) -> None:
    """사이클 32 (R4) — universe stale 가드 평가 + KIS 최근체결시각 기록. L2964 본체 그대로 이주.

    절대 깨지 말 것:
    - 보유 종목 / 익일청산 종목 절대 제외 금지 (사전 가드 순서 보존)
    - `_universe_excluded_today.add()` + `kis_ws_pool.unsubscribe()` 순서 보존
    - 50ms sleep Rate Limit 보호
    - `_reset_daily_state` 동행 clear (`_stale_state.reset_daily()` 통합 — A2 추가 없음)

    stale > MAX_STALE_RETRIES (=5) + KIS 당일 누적 거래량 < UNIVERSE_LOW_VOLUME_THRESHOLD
    → universe 에서 자동 제외 + WebSocket unsubscribe + INFO 로그 영구 보존.

    안전 가드:
    - 보유 종목 (`registry.is_ticker_held_by_any`) 절대 제외 금지 (손절·트레일링 우선)
    - 익일청산 종목 (`_pending_next_day_clear`) 절대 제외 금지 (시가 race 차단)
    - 이미 제외된 종목 재평가 skip (KIS Rate Limit 절약)
    - KIS `inquire_ccnl` 응답 None → 제외 보류 (다음 사이클 자연 재시도, graceful)
    - 종목 간 50ms sleep (Rate Limit 보호)
    - 본체 예외는 호출자(`_scan_loop`) 가 try/except 흡수 — 다음 사이클 자연 재시도

    Args:
        scheduler: TradingScheduler 인스턴스.
        candidate_tickers: 평가 대상 후보 리스트 (보통 `_collect_breakout_tickers` 결과 + extras)

    Note:
        매일 `_reset_daily_state` 가 `_universe_excluded_today.clear()` — 영구 블랙리스트 금지.
        제외된 종목은 다음 영업일 자동 재진입 가능.
    """
    from src.api.quotation import inquire_ccnl
    from src.db.system_logs import write_log as _write_log
    from src.engine.scanner import TICK_TR_ID
    from src.realtime.websocket_pool import kis_ws_pool

    # 사전 가드 — 보유 / 익일청산 / 이미 제외된 종목 사전 차단 (KIS 호출 절약)
    ndc_tickers = {t for (t, _sid) in getattr(scheduler, "_pending_next_day_clear", set())}
    excluded = getattr(scheduler, "_universe_excluded_today", set())

    # 평가 대상 결정 — stale > MAX_STALE_RETRIES + 보유/익일청산/이미 제외 아님
    targets: list[str] = []
    for ticker in candidate_tickers:
        if ticker in excluded:
            continue
        try:
            if scheduler.registry.is_ticker_held_by_any(ticker):
                continue
        except Exception:
            # registry 미주입 보호 (테스트 __new__)
            pass
        if ticker in ndc_tickers:
            continue
        retries = scheduler._stale_retry_count.get(ticker, 0)
        if retries <= MAX_STALE_RETRIES:
            continue
        targets.append(ticker)

    if not targets:
        return

    for ticker in targets:
        # KIS 호출 — graceful (실패 시 제외 보류, 다음 사이클 자연 재시도)
        try:
            ccnl = await inquire_ccnl(ticker)
        except Exception:
            logger.exception(
                "[universe_guard] inquire_ccnl 예외 ticker=%s — 제외 보류", ticker
            )
            continue

        if ccnl is None:
            # 빈 응답 (오프장 / 거래 없음) → 제외 보류
            logger.debug(
                "[universe_guard] inquire_ccnl None ticker=%s — 제외 보류",
                ticker,
            )
            await asyncio.sleep(0.05)
            continue

        today_volume = ccnl.get("today_volume", 0)
        if today_volume >= UNIVERSE_LOW_VOLUME_THRESHOLD:
            # 거래량 충분 → 제외 안 함 (가드 미발화)
            await asyncio.sleep(0.05)
            continue

        # 제외 결정 — 카운터 + last_resub_age 계산
        retries = scheduler._stale_retry_count.get(ticker, 0)
        last_at = scheduler._stale_last_resubscribe_at.get(ticker)
        if last_at is not None:
            from src.engine.scanner import KST_TZ as _KST_TZ
            age_secs = (datetime.now(_KST_TZ) - last_at).total_seconds()
            age_disp = f"{age_secs:.0f}s"
        else:
            age_disp = "-"

        # 제외 set 등록 + WebSocket unsubscribe
        scheduler._universe_excluded_today.add(ticker)
        try:
            await kis_ws_pool.unsubscribe(TICK_TR_ID, ticker)
        except Exception:
            logger.exception(
                "[universe_excluded] unsubscribe 실패 ticker=%s", ticker
            )

        # INFO 로그 + system_logs 영구 보존
        logger.info(
            "[universe_excluded] ticker=%s reason=stale_6plus_low_volume "
            "retries=%d last_resub_age=%s last_cntg_hour=%s today_volume=%d",
            ticker, retries, age_disp,
            ccnl.get("last_cntg_hour", ""),
            today_volume,
        )
        try:
            await _write_log(
                "INFO",
                f"[universe_excluded] ticker={ticker} "
                f"reason=stale_6plus_low_volume retries={retries} "
                f"last_resub_age={age_disp} "
                f"last_cntg_hour={ccnl.get('last_cntg_hour', '')} "
                f"today_volume={today_volume}",
            )
        except Exception:
            logger.debug("[universe_excluded] write_log 실패", exc_info=True)

        await asyncio.sleep(0.05)  # Rate Limit 보호
