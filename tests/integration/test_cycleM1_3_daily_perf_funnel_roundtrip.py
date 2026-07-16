"""사이클 M1-3 (Red) — daily_performance(RPC) / strategy_funnel 실 Postgres 왕복 검증.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, M1 마무리).

mock 단위 테스트로 못 잡는 **실 SQL · JSONB codec · plpgsql RPC · NUMERIC→Decimal ·
복합 키 upsert · UNIQUE upsert** 안전망. docker/DATABASE_URL_TEST 없으면 pg_harness
fixture 가 pytest.skip.

⚠️ 핵심:
1. **RPC 실증** — `recompute_daily_performance()` (migration 010/012 plpgsql) 가 하네스에
   존재 → trade_history SELL seed → daily_performance 행 UPDATE 실증. RPC 는 기존 행을
   **UPDATE 만** 하므로 upsert 로 행 선생성 필수.
2. **NUMERIC→Decimal** — asyncpg 는 NUMERIC 을 Decimal 로 반환 → get_* 반환 dict 의
   total_asset/daily_realized_pnl/cumulative_return_rate 가 Decimal 이어도 값 정합 단언.
3. **JSONB dict/list 왕복** — strategy_funnel survived_tickers/excluded_sample.
4. **UNIQUE upsert** — 동일 (target_date, strategy_id, step_no) 재저장 = 1행 + is_provisional 보존.

Red 유효성: production(2 모듈) 이 아직 pg 미사용 → 실 PG 왕복 경로 없음 → 전부 FAIL/에러.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


# ===========================================================================
# daily_performance — upsert 복합 키 + NUMERIC→Decimal + get_latest/get_performance
# ===========================================================================
@pytest.mark.asyncio
async def test_daily_performance_upsert_composite_and_numeric_decimal(clean_daily_performance):
    """upsert (date, strategy) 복합 키 + NUMERIC 컬럼 Decimal 반환 실증."""
    from src.db import daily_performance

    await daily_performance.upsert_daily_performance(
        date(2026, 7, 16),
        total_asset=10_000_000.0,
        daily_profit_rate=1.25,
        strategy="momentum",
        daily_realized_pnl=125_000.0,
        cumulative_return_rate=8.5,
    )
    # 동일 복합 키 재저장 → upsert (1행, 값 갱신)
    await daily_performance.upsert_daily_performance(
        date(2026, 7, 16),
        total_asset=11_000_000.0,
        daily_profit_rate=2.0,
        strategy="momentum",
        daily_realized_pnl=200_000.0,
        cumulative_return_rate=9.0,
    )

    latest = await daily_performance.get_latest_performance(strategy="momentum")
    assert latest is not None, "get_latest_performance → dict."
    assert latest["date"] == date(2026, 7, 16), "date DATE → date 객체."
    # ⚠️ NUMERIC → Decimal (asyncpg). 값 정합 (upsert 최종값).
    assert abs(float(latest["total_asset"]) - 11_000_000.0) < 1e-6, (
        "복합 키 upsert 최종 total_asset 반영 + NUMERIC 왕복."
    )
    assert abs(float(latest["cumulative_return_rate"]) - 9.0) < 1e-6, "NUMERIC 왕복."

    rows = await daily_performance.get_performance(days=30, strategy="momentum")
    assert len(rows) == 1, "복합 키 upsert → 1행 (중복 없음)."


@pytest.mark.asyncio
async def test_daily_performance_get_performance_date_asc(clean_daily_performance):
    """get_performance → date 오름차순 반환 (client-side sorted 계약)."""
    from src.db import daily_performance

    for d, ta in (
        (date(2026, 7, 14), 1_000_000.0),
        (date(2026, 7, 16), 3_000_000.0),
        (date(2026, 7, 15), 2_000_000.0),
    ):
        await daily_performance.upsert_daily_performance(
            d, total_asset=ta, daily_profit_rate=0.0, strategy="total"
        )

    rows = await daily_performance.get_performance(days=30, strategy="total")
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates), "get_performance date 오름차순 정렬 계약."


# ===========================================================================
# daily_performance — ⚠️ RPC recompute_daily_performance() plpgsql 실증
# ===========================================================================
@pytest.mark.asyncio
async def test_recompute_from_trades_rpc_updates_realized_pnl(clean_daily_performance):
    """⚠️ RPC 실증: trade_history SELL seed → recompute → daily_realized_pnl UPDATE.

    migration 010/012 plpgsql 함수가 하네스에 존재. RPC 는 기존 daily_performance 행을
    UPDATE 만 하므로 (INSERT 안 함) 전략 행 + 'total' 행 + 전일 baseline 행 선생성 필수.
    """
    import src.db.pg as pg
    from src.db import daily_performance

    # 1) 전일 baseline (분모 total_asset>0) — daily_profit_rate 계산용
    await daily_performance.upsert_daily_performance(
        date(2026, 7, 15), total_asset=10_000_000.0, daily_profit_rate=0.0,
        strategy="momentum",
    )
    await daily_performance.upsert_daily_performance(
        date(2026, 7, 15), total_asset=10_000_000.0, daily_profit_rate=0.0,
        strategy="total",
    )
    # 2) 당일 행 (RPC 가 realized_pnl / rate 를 채울 대상, 초기 pnl=0)
    await daily_performance.upsert_daily_performance(
        date(2026, 7, 16), total_asset=10_500_000.0, daily_profit_rate=0.0,
        strategy="momentum", daily_realized_pnl=0.0,
    )
    await daily_performance.upsert_daily_performance(
        date(2026, 7, 16), total_asset=10_500_000.0, daily_profit_rate=0.0,
        strategy="total", daily_realized_pnl=0.0,
    )

    # 3) trade_history SELL seed — 7/16 KST 매도 실현손익 500,000 (momentum)
    #    RPC 가 date(timestamp at time zone 'Asia/Seoul') 로 그룹핑 → +09:00 명시.
    await pg.execute(
        """
        INSERT INTO trade_history (timestamp, ticker, trade_type, price, quantity,
                                   profit_loss, status, strategy)
        VALUES ($1, $2, 'SELL', $3, $4, $5, 'COMPLETED', $6)
        """,
        __import__("datetime").datetime.fromisoformat("2026-07-16T10:00:00+09:00"),
        "005930", 70000.0, 10, 500_000.0, "momentum",
    )

    # 4) RPC 실행 (멱등)
    ok = await daily_performance.recompute_from_trades()
    assert ok is True, "recompute_from_trades → True (plpgsql RPC 성공)."

    # 5) daily_realized_pnl UPDATE 실증 (momentum + total 둘 다 500,000)
    got = await daily_performance.get_latest_performance(strategy="momentum")
    assert got is not None
    assert abs(float(got["daily_realized_pnl"]) - 500_000.0) < 1e-6, (
        "RPC 가 SELL profit_loss 합을 daily_realized_pnl 로 UPDATE (momentum)."
    )
    # ⚠️ NUMERIC → Decimal 반환 단언 (계획 3대 리스크 3 = NUMERIC 계약)
    assert isinstance(got["daily_realized_pnl"], Decimal), (
        "asyncpg NUMERIC → Decimal 반환 계약 (라우트 float 캐스트 안전성 근거)."
    )
    # daily_profit_rate = 500,000 / 10,000,000(전일) * 100 = 5.0
    assert abs(float(got["daily_profit_rate"]) - 5.0) < 1e-6, (
        "RPC daily_profit_rate = realized / 전일 total_asset * 100 = 5.0."
    )

    total_row = await daily_performance.get_latest_performance(strategy="total")
    assert abs(float(total_row["daily_realized_pnl"]) - 500_000.0) < 1e-6, (
        "RPC total 집계 = 전략별 realized 합 (500,000)."
    )


@pytest.mark.asyncio
async def test_recompute_from_trades_idempotent(clean_daily_performance):
    """RPC 멱등 — 2회 연속 호출 결과 동일 (매일 정산 후 재호출 안전)."""
    from src.db import daily_performance
    import src.db.pg as pg

    await daily_performance.upsert_daily_performance(
        date(2026, 7, 15), total_asset=10_000_000.0, daily_profit_rate=0.0, strategy="total"
    )
    await daily_performance.upsert_daily_performance(
        date(2026, 7, 16), total_asset=10_000_000.0, daily_profit_rate=0.0, strategy="total"
    )
    await pg.execute(
        """
        INSERT INTO trade_history (timestamp, ticker, trade_type, price, quantity,
                                   profit_loss, status, strategy)
        VALUES ($1, $2, 'SELL', $3, $4, $5, 'COMPLETED', 'total')
        """,
        __import__("datetime").datetime.fromisoformat("2026-07-16T10:00:00+09:00"),
        "005930", 70000.0, 10, 300_000.0,
    )

    assert await daily_performance.recompute_from_trades() is True
    first = await daily_performance.get_latest_performance(strategy="total")
    assert await daily_performance.recompute_from_trades() is True
    second = await daily_performance.get_latest_performance(strategy="total")

    assert float(first["daily_realized_pnl"]) == float(second["daily_realized_pnl"]), (
        "RPC 멱등 — 재호출 시 realized_pnl 불변."
    )


# ===========================================================================
# strategy_funnel — JSONB dict/list 왕복 + UNIQUE upsert + is_provisional
# ===========================================================================
@pytest.mark.asyncio
async def test_strategy_funnel_jsonb_roundtrip_returns_list(clean_strategy_funnel):
    """⚠️ insert → list 후 survived_tickers=list / excluded_sample=list[dict] = JSONB codec."""
    from src.db import strategy_funnel

    survived = [{"ticker": "005930", "name": "삼성전자"}, {"ticker": "000660", "name": "SK하이닉스"}]
    excluded = [{"ticker": "035420", "name": "NAVER", "reason": "음봉 비율 35% > 30%"}]
    inserted = await strategy_funnel.insert_snapshot(
        target_date=date(2026, 7, 16),
        strategy_id="donchian_swing",
        step_no=1,
        step_name="원천 유니버스 후보",
        survived_tickers=survived,
        excluded_sample=excluded,
        survived_count=2,
        excluded_count=1,
        is_provisional=True,
    )
    assert inserted is not None, "insert_snapshot → upsert row dict."

    rows = await strategy_funnel.list_snapshots(
        target_date=date(2026, 7, 16), strategy_id="donchian_swing"
    )
    assert len(rows) == 1, "1단계 = 1행."
    row = rows[0]
    assert isinstance(row["survived_tickers"], list), (
        "survived_tickers 가 list 아님 → JSONB codec 미작동 (계획 최대 위험 실현)."
    )
    assert isinstance(row["excluded_sample"], list), "excluded_sample 가 list 아님 → JSONB codec 미작동."
    assert row["survived_tickers"] == survived, "survived_tickers JSONB 왕복 무손실 (중첩 dict)."
    assert row["excluded_sample"][0]["reason"] == "음봉 비율 35% > 30%", "excluded 중첩 dict 보존."
    assert row["is_provisional"] is True, "is_provisional BOOLEAN → bool (사이클 171 보존)."
    assert row["target_date"] == date(2026, 7, 16), "target_date DATE → date 객체."


@pytest.mark.asyncio
async def test_strategy_funnel_unique_upsert_one_row(clean_strategy_funnel):
    """동일 (target_date, strategy_id, step_no) 재저장 → UPSERT 1행 (사이클 145)."""
    from src.db import strategy_funnel

    await strategy_funnel.insert_snapshot(
        target_date=date(2026, 7, 16),
        strategy_id="bull_flag_breakout",
        step_no=1,
        step_name="유니버스",
        survived_tickers=["005930"],
        survived_count=1,
    )
    # 동일 키 재저장 (값 갱신)
    await strategy_funnel.insert_snapshot(
        target_date=date(2026, 7, 16),
        strategy_id="bull_flag_breakout",
        step_no=1,
        step_name="유니버스",
        survived_tickers=["005930", "000660", "035420"],
        survived_count=3,
        is_provisional=False,
    )

    rows = await strategy_funnel.list_snapshots(
        target_date=date(2026, 7, 16), strategy_id="bull_flag_breakout"
    )
    assert len(rows) == 1, "UNIQUE (target_date, strategy_id, step_no) → 1행 (중복 없음)."
    assert rows[0]["survived_count"] == 3, "UPSERT = 최신 값으로 갱신."
    assert len(rows[0]["survived_tickers"]) == 3, "survived_tickers 최신 값 반영."


@pytest.mark.asyncio
async def test_strategy_funnel_list_order_step_no_asc(clean_strategy_funnel):
    """list_snapshots → step_no ASC 정렬."""
    from src.db import strategy_funnel

    for step in (3, 1, 2):
        await strategy_funnel.insert_snapshot(
            target_date=date(2026, 7, 16),
            strategy_id="vcp_breakout",
            step_no=step,
            step_name=f"step{step}",
            survived_tickers=[],
            survived_count=0,
        )

    rows = await strategy_funnel.list_snapshots(
        target_date=date(2026, 7, 16), strategy_id="vcp_breakout"
    )
    steps = [r["step_no"] for r in rows]
    assert steps == [1, 2, 3], "step_no ASC 정렬 계약."


@pytest.mark.asyncio
async def test_strategy_funnel_cap_applied_roundtrip(clean_strategy_funnel):
    """survived 200 / excluded 20 cap 실 DB 왕복 후에도 유지."""
    from src.db import strategy_funnel

    survived = [f"{i:06d}" for i in range(500)]
    excluded = [{"ticker": f"{i:06d}", "reason": "x"} for i in range(50)]
    await strategy_funnel.insert_snapshot(
        target_date=date(2026, 7, 16),
        strategy_id="momentum",
        step_no=1,
        step_name="cap",
        survived_tickers=survived,
        excluded_sample=excluded,
    )

    rows = await strategy_funnel.list_snapshots(
        target_date=date(2026, 7, 16), strategy_id="momentum"
    )
    assert len(rows[0]["survived_tickers"]) == strategy_funnel.SURVIVED_TICKERS_CAP, (
        "survived cap 200 실 DB 왕복 유지."
    )
    assert len(rows[0]["excluded_sample"]) == strategy_funnel.EXCLUDED_SAMPLE_CAP, (
        "excluded cap 20 실 DB 왕복 유지."
    )
