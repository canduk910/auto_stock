"""daily_performance CRUD.

사이클 M1-3 (Supabase→RDS 이전 단계1 증분3, M1 마무리): supabase-py → `src.db.pg`
(asyncpg) 전환. 함수 시그니처·반환형·graceful 100% 보존 → 호출부(scheduler `_settle`
등) diff 0.

⚠️ RPC 전환: `.rpc("recompute_daily_performance", {})` → `pg.execute("SELECT
recompute_daily_performance()")`. plpgsql 함수는 migration 010/012 정의 — 기존
daily_performance 행을 UPDATE 만 한다(INSERT 안 함).
"""

from __future__ import annotations

import logging
from datetime import date

import src.db.pg as pg

logger = logging.getLogger(__name__)


async def upsert_daily_performance(
    target_date: date,
    total_asset: float,
    daily_profit_rate: float,
    strategy: str = "total",
    *,
    net_external_cashflow: float = 0.0,
    daily_realized_pnl: float = 0.0,
    deposit: float = 0.0,
    cumulative_return_rate: float = 0.0,
) -> None:
    """일일 실적을 저장(upsert)한다.

    daily_realized_pnl: **실현손익 기준** — `SUM(trade_history.SELL.profit_loss)` 매도 실현분만.
        매도가 없는 날은 0 (보유 평가손익은 포함하지 않음). 운영 보고도 동일 기준.
    daily_profit_rate: **실현손익 기준** — `daily_realized_pnl / 직전 영업일 total_asset * 100`.
        매도 0건이면 0% 정상 동작 (평가손익 변동은 반영되지 않음). 컬럼명에 "평가"가
        들어가지 않은 이유는 실제 RPC `recompute_daily_performance()`가 실현분만 산출하기
        때문 (2026-05-15 정책 결정 — 컬럼 의미 명시화).
    cumulative_return_rate: TWR 복리 누적 수익률 (실현손익 기반, daily_profit_rate 사용).
    """
    await pg.execute(
        """
        INSERT INTO daily_performance (
            date, strategy, total_asset, daily_profit_rate,
            net_external_cashflow, daily_realized_pnl, deposit, cumulative_return_rate
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (date, strategy) DO UPDATE SET
            total_asset = EXCLUDED.total_asset,
            daily_profit_rate = EXCLUDED.daily_profit_rate,
            net_external_cashflow = EXCLUDED.net_external_cashflow,
            daily_realized_pnl = EXCLUDED.daily_realized_pnl,
            deposit = EXCLUDED.deposit,
            cumulative_return_rate = EXCLUDED.cumulative_return_rate
        """,
        target_date,
        strategy,
        total_asset,
        daily_profit_rate,
        net_external_cashflow,
        daily_realized_pnl,
        deposit,
        cumulative_return_rate,
    )
    logger.info(
        "일일 실적 저장: %s 전략=%s (실현 %.2f%%, 누적 %.2f%%, 외부입출금 %.0f)",
        target_date, strategy, daily_profit_rate, cumulative_return_rate, net_external_cashflow,
    )


async def get_performance(days: int = 30, strategy: str = "total") -> list[dict]:
    """최근 N일 실적을 조회한다."""
    rows = await pg.fetch(
        """
        SELECT * FROM daily_performance
        WHERE strategy = $1
        ORDER BY date DESC
        LIMIT $2
        """,
        strategy,
        days,
    )
    return sorted(rows, key=lambda r: r["date"])


async def get_latest_performance(strategy: str = "total") -> dict | None:
    """가장 최근 영업일의 실적 1행을 반환한다.

    TWR 누적 baseline + Δ예수금 계산용.
    """
    return await pg.fetchrow(
        """
        SELECT * FROM daily_performance
        WHERE strategy = $1
        ORDER BY date DESC
        LIMIT 1
        """,
        strategy,
    )


async def recompute_from_trades() -> bool:
    """trade_history 기반 daily_performance 일괄 재계산 (소급 정산).

    PostgreSQL 함수 `recompute_daily_performance()`를 SELECT 호출 (RPC 전환, 사이클
    M1-3). 멱등이므로 매일 정산 후 호출해도 안전.

    수행 단계 (DB 함수 내부):
    1) SELL profit_loss 합 → daily_realized_pnl (전략별 + total)
    2) daily_profit_rate = daily_realized_pnl / 전일 total_asset * 100
    3) cumulative_return_rate = TWR 복리 누적
    """
    try:
        await pg.execute("SELECT recompute_daily_performance()")
        logger.info("daily_performance 일괄 재계산 완료 (recompute_daily_performance)")
        return True
    except Exception:
        logger.exception("daily_performance 재계산 실패")
        return False
