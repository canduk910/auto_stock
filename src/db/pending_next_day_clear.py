"""사이클 162 (2026-06-17) — 익일청산큐 DB 영속화 CRUD.

사용자 보고: 알테오젠 (196170, VB) + 알지노믹스 (476830, LTV) 6/17 15:20 강제청산 누락.
근본 원인 후보 = `_pending_next_day_clear: set[tuple[ticker, strategy_id]]` 메모리 휘발
(EC2 재기동 시) → drain 시 0건 → 강제청산 영구 누락.

domain-expert 자문 산출물:
    `_workspace/domain_consult/cycle162_pending_persist_and_call_auction.md` (옵션 A 채택)

핵심 책임:
1. `save_pending_ndc(target_date, ticker, strategy_id, reason)` — 등록 4 사이트 동기 호출
2. `delete_pending_ndc(target_date, ticker, strategy_id)` — drain finally 영역 호출
3. `load_pending_ndc(target_date) -> set[tuple[ticker, strategy_id]]` — `boot()` 영역 복구
4. `purge_pending_ndc_before(target_date)` — 일일 정리 (오래된 영역 영구 폐기)

영속 의무 매트릭스:
- 사이클 32 R4 보유/익일청산 절대 보호 영속
- 사이클 38 명문화 (매도/익일청산 hot path 무관 = DB 저장 영역만)
- 사이클 53 KST `+09:00` timezone 명시
- 사이클 68 `_kst.now_kst_iso()` 의무 (CLAUDE.md G-10b AST)
- 사이클 88 G-REJECT graceful (DB 실패 시 메모리 set 보존)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from src.db._kst import now_kst_iso
from src.db.supabase import supabase

logger = logging.getLogger(__name__)


_TABLE = "pending_next_day_clear"


async def save_pending_ndc(
    target_date: date,
    ticker: str,
    strategy_id: str,
    reason: str = "unknown",
) -> None:
    """익일청산 큐 1행 UPSERT (target_date, ticker, strategy_id) PK.

    등록 사이트 4 영역 동기 호출:
    - `_execute_next_day_clear` stock_master nxt_tradable=False 분기
    - `_execute_next_day_clear` NXT 시가 미수신 분기
    - sell_rejection NXT 익일 전환 (market_order_disallowed_fallback 시)
    - order_engine 매도 거부 NXT 폴백

    graceful (사이클 88 G-REJECT 답습) — 호출자가 try/except 흡수 + WARNING.
    """
    data = {
        "target_date": target_date.isoformat(),
        "ticker": ticker,
        "strategy_id": strategy_id,
        "reason": reason,
        "created_at": now_kst_iso(),
    }
    await asyncio.to_thread(
        lambda: supabase.table(_TABLE).upsert(
            data, on_conflict="target_date,ticker,strategy_id"
        ).execute()
    )
    logger.debug(
        "[pending_ndc_save] target_date=%s ticker=%s strategy=%s reason=%s",
        target_date, ticker, strategy_id, reason,
    )


async def delete_pending_ndc(
    target_date: date, ticker: str, strategy_id: str,
) -> None:
    """익일청산 큐 1행 DELETE.

    drain finally 영역 호출 = `_drain_pending_next_day_clear` finally 블록.
    idempotent (미존재 행 DELETE = no-op).
    """
    await asyncio.to_thread(
        lambda: supabase.table(_TABLE).delete().eq(
            "target_date", target_date.isoformat()
        ).eq("ticker", ticker).eq("strategy_id", strategy_id).execute()
    )
    logger.debug(
        "[pending_ndc_delete] target_date=%s ticker=%s strategy=%s",
        target_date, ticker, strategy_id,
    )


async def load_pending_ndc(target_date: date) -> set[tuple[str, str]]:
    """target_date 영역 익일청산 큐 전수 조회.

    `boot()` 마지막 단계 (사이클 149 VI seed 답습 위치) 호출.
    반환값 = `{(ticker, strategy_id), ...}` set = scheduler._pending_next_day_clear 직접 update.

    실패 시 빈 set 반환 (graceful, 호출자 메모리 set 보존).
    """
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table(_TABLE).select(
                "ticker, strategy_id"
            ).eq("target_date", target_date.isoformat()).execute()
        )
    except Exception:
        logger.exception("[pending_ndc_load] 실패 graceful — 메모리 set 보존")
        return set()

    rows = getattr(result, "data", None) or []
    return {(row["ticker"], row["strategy_id"]) for row in rows if row.get("ticker") and row.get("strategy_id")}


async def purge_pending_ndc_before(target_date: date) -> int:
    """target_date *이전* 영역 익일청산 큐 일괄 DELETE.

    `_reset_daily_state` 동행 호출 = 다음 영업일 _boot 영역 진입 전 정리.
    반환값 = 삭제된 행 수 (진단용, 실패 시 -1).
    """
    try:
        result = await asyncio.to_thread(
            lambda: supabase.table(_TABLE).delete().lt(
                "target_date", target_date.isoformat()
            ).execute()
        )
    except Exception:
        logger.exception("[pending_ndc_purge] 실패 graceful")
        return -1

    rows = getattr(result, "data", None) or []
    count = len(rows)
    if count:
        logger.info("[pending_ndc_purge] deleted=%d cutoff=%s", count, target_date)
    return count
