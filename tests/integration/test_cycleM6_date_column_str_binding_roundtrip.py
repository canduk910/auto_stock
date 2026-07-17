"""사이클 M6 (라이브 핫픽스) — 실 Postgres str-date 바인딩 왕복 실증.

배경: `src/db/strategy_funnel.py::insert_snapshot` 가 `target_date`(DATE 컬럼)에
str(`.isoformat()` 오적용)을 바인딩해 asyncpg 가
``invalid input for query argument $2: '...' ('str' object has no attribute
'toordinal')`` 로 실패했다. 기존 통합 테스트(`test_cycleM1_3_daily_perf_funnel_roundtrip.py`
등)는 항상 `date(...)` 객체를 넘겨 이 경로를 검증하지 못했다.

본 파일 = **str 입력**으로 동일 함수를 호출 — mock 이 아닌 실 asyncpg 왕복으로
`to_date()` 강제 변환이 실제 DB 계층에서도 작동함을 실증한다. docker/
DATABASE_URL_TEST 없으면 pg_harness fixture 가 skip (기존 통합 스위트와 동일 정책).
"""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_STR_DATE = "2026-07-17"
_DATE_OBJ = date(2026, 7, 17)


# ===========================================================================
# strategy_funnel — 버그 재현 핵심 (scanner.py 사고 경로)
# ===========================================================================
@pytest.mark.asyncio
async def test_strategy_funnel_insert_snapshot_str_target_date_real_pg(clean_strategy_funnel):
    """⚠️ 버그 재현 실증: str target_date 로 insert_snapshot 호출 → 실 PG INSERT 성공.

    시정 전이었다면 asyncpg 가 여기서
    ``invalid input for query argument $2: '2026-07-17' ('str' object has no
    attribute 'toordinal')`` 를 raise 했을 것 (insert_snapshot 의 try/except 가
    삼켜 None 반환 + WARNING 로그만 남기고 데이터는 저장되지 않았을 것).
    """
    from src.db import strategy_funnel

    inserted = await strategy_funnel.insert_snapshot(
        target_date=_STR_DATE,  # type: ignore[arg-type] — 실제 사고 재현 (scanner.py 오류 형식)
        strategy_id="ALL",
        step_no=97,
        step_name="trade_amount_filter_scanner",
        survived_tickers=["005930"],
        survived_count=1,
    )
    assert inserted is not None, (
        "str target_date 입력이 asyncpg 예외로 삼켜지지 않고 정상 저장돼야 한다 "
        "(M6 라이브 핫픽스 실증)."
    )
    assert inserted["target_date"] == _DATE_OBJ, "저장된 target_date 가 date 객체로 정규화돼야 한다."

    # 조회 경로(list_snapshots)도 str 입력 허용 실증
    rows = await strategy_funnel.list_snapshots(
        target_date=_STR_DATE, strategy_id="ALL"  # type: ignore[arg-type]
    )
    assert len(rows) == 1, "str target_date 로 조회해도 방금 저장한 행을 찾아야 한다."
    assert rows[0]["step_no"] == 97


@pytest.mark.asyncio
async def test_strategy_funnel_str_and_date_target_date_same_row(clean_strategy_funnel):
    """str 입력과 date 객체 입력이 동일 행을 가리켜야 한다 (UNIQUE 정합).

    시정 전이라면 str 경로가 실패해 date 경로만 성공 → upsert 충돌 검증 불가능했다.
    """
    from src.db import strategy_funnel

    await strategy_funnel.insert_snapshot(
        target_date=_DATE_OBJ,
        strategy_id="donchian_swing",
        step_no=1,
        step_name="유니버스",
        survived_tickers=["005930"],
        survived_count=1,
    )
    # 동일 논리적 날짜를 str 로 재저장 (upsert 갱신 실증)
    await strategy_funnel.insert_snapshot(
        target_date=_STR_DATE,  # type: ignore[arg-type]
        strategy_id="donchian_swing",
        step_no=1,
        step_name="유니버스",
        survived_tickers=["005930", "000660"],
        survived_count=2,
    )

    rows = await strategy_funnel.list_snapshots(
        target_date=_DATE_OBJ, strategy_id="donchian_swing"
    )
    assert len(rows) == 1, "str/date 입력이 동일 (target_date, strategy_id, step_no) 로 UPSERT 돼야 한다."
    assert rows[0]["survived_count"] == 2, "str 입력 재저장이 최신 값으로 갱신돼야 한다."


# ===========================================================================
# daily_log_reports / parameter_recommendations / backtest_runs /
# market_regime_snapshots / pending_next_day_clear / daily_performance /
# positions — str-date 왕복 (각 모듈 대표 함수 1개)
# ===========================================================================
@pytest.mark.asyncio
async def test_log_reports_str_target_date_real_pg(clean_log_reports):
    from src.db import log_reports

    row = await log_reports.insert_log_report(
        target_date=_STR_DATE,  # type: ignore[arg-type]
        summary="M6 str-date 실증", findings=[], metrics={}, model="gpt-test",
    )
    assert row is not None
    assert row["target_date"] == _DATE_OBJ

    got = await log_reports.get_log_report(_STR_DATE)  # type: ignore[arg-type]
    assert got is not None
    assert got["target_date"] == _DATE_OBJ


@pytest.mark.asyncio
async def test_parameter_recommendations_str_target_date_real_pg(clean_parameter_recommendations):
    from src.db import parameter_recommendations as pr

    row = await pr.insert_recommendation(
        target_date=_STR_DATE,  # type: ignore[arg-type]
        strategy_id="momentum", current_params={"a": 1}, recommended_params={"a": 2},
        reasoning="test", metrics={},
    )
    assert row is not None
    assert row["target_date"] == _DATE_OBJ

    pending = await pr.list_pending_by_date(_STR_DATE)  # type: ignore[arg-type]
    assert len(pending) == 1


@pytest.mark.asyncio
async def test_backtest_runs_str_target_date_real_pg(clean_backtest_runs):
    from src.db import backtest_runs

    row = await backtest_runs.insert_run(
        target_date=_STR_DATE,  # type: ignore[arg-type]
        strategy_id="momentum", params_kind="current", params_snapshot={"k": "v"},
    )
    assert row is not None
    assert row["target_date"] == _DATE_OBJ

    rows = await backtest_runs.list_by_date(_STR_DATE)  # type: ignore[arg-type]
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_market_regime_snapshots_str_date_real_pg(clean_market_regime):
    from src.db import market_regime_snapshots as mrs

    row = await mrs.insert_snapshot(
        snapshot_date=_STR_DATE,  # type: ignore[arg-type]
        regime="neutral", regime_desc=None, cycle_phase=None,
        vix=18.5, fear_greed_score=50.0, buffett_ratio=None,
        raw_response={"src": "test"}, computed_cash_usage_ratio=0.8,
        buy_blocked=False, block_reason=None,
    )
    assert row is not None
    assert row["snapshot_date"] == _DATE_OBJ

    got = await mrs.get_by_date(_STR_DATE)  # type: ignore[arg-type]
    assert got is not None
    assert got["snapshot_date"] == _DATE_OBJ


@pytest.mark.asyncio
async def test_pending_next_day_clear_str_target_date_real_pg(clean_pending_ndc):
    from src.db import pending_next_day_clear as ndc

    await ndc.save_pending_ndc(
        _STR_DATE, "005930", "volatility_breakout", reason="nxt_not_tradable",  # type: ignore[arg-type]
    )

    restored = await ndc.load_pending_ndc(_STR_DATE)  # type: ignore[arg-type]
    assert ("005930", "volatility_breakout") in restored, (
        "str target_date 로 저장한 익일청산큐가 str target_date 조회에서 복구돼야 한다 "
        "(_boot() 복구 경로 실증, 매매 안전성 인접)."
    )

    await ndc.delete_pending_ndc(_STR_DATE, "005930", "volatility_breakout")  # type: ignore[arg-type]
    after_delete = await ndc.load_pending_ndc(_DATE_OBJ)
    assert after_delete == set(), "str target_date 로 DELETE 해도 실제 삭제돼야 한다."


@pytest.mark.asyncio
async def test_daily_performance_str_target_date_real_pg(clean_daily_performance):
    from src.db import daily_performance

    await daily_performance.upsert_daily_performance(
        _STR_DATE,  # type: ignore[arg-type]
        total_asset=5_000_000.0, daily_profit_rate=1.0, strategy="total",
    )
    rows = await daily_performance.get_performance(days=30, strategy="total")
    assert len(rows) == 1
    assert rows[0]["date"] == _DATE_OBJ


@pytest.mark.asyncio
async def test_positions_str_buy_date_real_pg(clean_positions):
    from src.db import positions

    await positions.save_position(
        ticker="005930", ticker_name="삼성전자", buy_price=70000, quantity=10,
        order_no="ORD-M6-1", strategy_id="momentum",
        buy_date=_STR_DATE,  # type: ignore[arg-type]
    )
    rows = await positions.load_all()
    assert len(rows) == 1
    assert rows[0]["buy_date"] == _DATE_OBJ, "str buy_date 입력이 date 컬럼에 정상 저장돼야 한다."


@pytest.mark.asyncio
async def test_stock_master_daily_purge_str_cutoff_real_pg(clean_stock_master_daily):
    """purge_old_rows(cutoff_date) str 입력 — 실 DELETE 슬라이스 루프 정상 동작."""
    from src.db import stock_master_daily as smd

    # 컷오프보다 오래된 1건 + 이후 1건 seed
    await smd.upsert_daily("005930", date(2026, 1, 1), {
        "stck_bsop_date": "20260101", "stck_oprc": "1000", "stck_hgpr": "1100",
        "stck_lwpr": "900", "stck_clpr": "1050", "acml_vol": "100", "acml_tr_pbmn": "1000000",
    })
    await smd.upsert_daily("005930", date(2026, 7, 1), {
        "stck_bsop_date": "20260701", "stck_oprc": "2000", "stck_hgpr": "2100",
        "stck_lwpr": "1900", "stck_clpr": "2050", "acml_vol": "200", "acml_tr_pbmn": "2000000",
    })

    result = await smd.purge_old_rows("2026-07-01")  # type: ignore[arg-type] — str cutoff
    assert result["deleted"] == 1, "str cutoff_date 로도 오래된 1건만 정확히 삭제돼야 한다."

    remaining = await smd.get_recent_daily("005930", days=10)
    assert len(remaining) == 1
    assert remaining[0]["bas_dd"] == date(2026, 7, 1)
