"""사이클 M6 (라이브 핫픽스) — DATE 컬럼 바인딩 str-경로 회귀 가드 (전 모듈).

배경: `src/db/strategy_funnel.py::insert_snapshot` 가 `target_date`(DATE 컬럼)에
str 을 바인딩하면 asyncpg 가
``invalid input for query argument $2: '...' ('str' object has no attribute
'toordinal')`` 로 실패한다. 근본 원인 = `src/engine/scanner.py` 의
`datetime.now(KST_TZ).date().isoformat()` 호출부가 문자열을 `target_date=` 에
전달 — `insert_snapshot` 의 try/except 가 이를 삼켜 조용히 저장 누락됐다
(매매는 정상 — funnel 관찰성 데이터만 손실).

시정: `src/db/_kst.py::to_date()` 로 DATE 바인딩 지점 전수를 감싸 str/date
양쪽을 date 객체로 강제 변환. 기존 통합 테스트(date 객체만 사용)가 못 잡은
"문자열 입력" 경로를 여기서 mock pg 로 재현·실증한다.

대상 7 모듈: strategy_funnel / daily_log_reports(log_reports) /
parameter_recommendations / backtest_runs / pending_next_day_clear /
daily_performance / market_regime_snapshots (+ positions, 동일 패턴 부가 하드닝).

각 테스트 = str 인자 전달 → pg mock 이 실제 발화한 바인딩 인자 중 date 객체가
있음을 단언 (str 그대로 전달되면 FAIL — asyncpg 라면 여기서 예외 발생).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

_STR_DATE = "2026-07-17"
_DATE_OBJ = date(2026, 7, 17)


# ===========================================================================
# strategy_funnel.py — insert_snapshot / list_snapshots (버그 재현 핵심)
# ===========================================================================
@pytest.mark.asyncio
async def test_strategy_funnel_insert_snapshot_accepts_str_target_date():
    """str target_date 입력 → INSERT 바인딩에 date 객체가 실제 전달돼야 한다.

    사이클 M6 버그 재현: `scanner.py` 가 `.isoformat()` 을 호출해 str 을 넘기던
    실제 사고 경로. 시정 전에는 target_date=str 그대로 바인딩 → 이 단언 FAIL.
    """
    from src.db import strategy_funnel

    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        out = await strategy_funnel.insert_snapshot(
            target_date=_STR_DATE,  # type: ignore[arg-type]  — 버그 재현 (str 입력)
            strategy_id="ALL",
            step_no=97,
            step_name="trade_amount_filter_scanner",
            survived_tickers=["005930"],
            survived_count=1,
        )

    assert out is not None, "str target_date 도 정상 INSERT 되어야 한다 (silent 손실 차단)."
    bound_args = pg_mod.fetchrow.await_args.args[1:]
    assert _DATE_OBJ in bound_args, (
        "insert_snapshot 이 str target_date 를 date 객체로 변환해 바인딩해야 한다 "
        "(asyncpg DATE 컬럼 요구사항)."
    )
    assert _STR_DATE not in bound_args, "원본 str 이 그대로 바인딩되면 안 된다 (asyncpg 예외 유발)."


@pytest.mark.asyncio
async def test_strategy_funnel_list_snapshots_accepts_str_target_date():
    """list_snapshots 도 str target_date 를 date 로 변환해 조회해야 한다 (WHERE 바인딩)."""
    from src.db import strategy_funnel

    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await strategy_funnel.list_snapshots(
            target_date=_STR_DATE, strategy_id="donchian_swing"  # type: ignore[arg-type]
        )

    bound_args = pg_mod.fetch.await_args.args[1:]
    assert _DATE_OBJ in bound_args, "list_snapshots WHERE 바인딩도 str→date 변환 의무."


@pytest.mark.asyncio
async def test_strategy_funnel_list_snapshots_no_strategy_filter_str_date():
    """strategy_id=None 분기도 동일 str→date 변환 (두 SQL 분기 전부 커버)."""
    from src.db import strategy_funnel

    with patch.object(strategy_funnel, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await strategy_funnel.list_snapshots(target_date=_STR_DATE)  # type: ignore[arg-type]

    bound_args = pg_mod.fetch.await_args.args[1:]
    assert _DATE_OBJ in bound_args


# ===========================================================================
# daily_log_reports (log_reports.py)
# ===========================================================================
@pytest.mark.asyncio
async def test_log_reports_insert_accepts_str_target_date():
    from src.db import log_reports

    with patch.object(log_reports, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        await log_reports.insert_log_report(
            target_date=_STR_DATE,  # type: ignore[arg-type]
            summary="s", findings=[], metrics={}, model="gpt",
        )

    bound_args = pg_mod.fetchrow.await_args.args[1:]
    assert _DATE_OBJ in bound_args


@pytest.mark.asyncio
async def test_log_reports_get_accepts_str_target_date():
    from src.db import log_reports

    with patch.object(log_reports, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=None)
        await log_reports.get_log_report(_STR_DATE)  # type: ignore[arg-type]

    bound_args = pg_mod.fetchrow.await_args.args[1:]
    assert _DATE_OBJ in bound_args


# ===========================================================================
# parameter_recommendations.py — 4 DATE 바인딩 함수
# ===========================================================================
@pytest.mark.asyncio
async def test_parameter_recommendations_insert_accepts_str_target_date():
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        await pr.insert_recommendation(
            target_date=_STR_DATE,  # type: ignore[arg-type]
            strategy_id="momentum", current_params={}, recommended_params={},
            reasoning="r", metrics={},
        )

    bound_args = pg_mod.fetchrow.await_args.args
    assert _DATE_OBJ in bound_args


@pytest.mark.asyncio
async def test_parameter_recommendations_list_pending_backtest_str_date():
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await pr.list_recommendations_pending_backtest(_STR_DATE)  # type: ignore[arg-type]

    bound_args = pg_mod.fetch.await_args.args[1:]
    assert _DATE_OBJ in bound_args


@pytest.mark.asyncio
async def test_parameter_recommendations_list_pending_by_date_str_date():
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await pr.list_pending_by_date(_STR_DATE)  # type: ignore[arg-type]

    bound_args = pg_mod.fetch.await_args.args[1:]
    assert _DATE_OBJ in bound_args


@pytest.mark.asyncio
async def test_parameter_recommendations_expire_pending_before_str_date():
    from src.db import parameter_recommendations as pr

    with patch.object(pr, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="UPDATE 0")
        await pr.expire_pending_before(_STR_DATE)  # type: ignore[arg-type]

    bound_args = pg_mod.execute.await_args.args[1:]
    assert _DATE_OBJ in bound_args


# ===========================================================================
# backtest_runs.py — insert_run(dedupe SELECT + INSERT) / list_by_date
# ===========================================================================
@pytest.mark.asyncio
async def test_backtest_runs_insert_run_accepts_str_target_date():
    from src.db import backtest_runs

    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])  # dedupe SELECT: 미존재
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        await backtest_runs.insert_run(
            target_date=_STR_DATE,  # type: ignore[arg-type]
            strategy_id="momentum", params_kind="current", params_snapshot={},
        )

    dedupe_args = pg_mod.fetch.await_args.args[1:]
    insert_args = pg_mod.fetchrow.await_args.args
    assert _DATE_OBJ in dedupe_args, "dedupe SELECT WHERE 바인딩도 str→date 변환 의무."
    assert _DATE_OBJ in insert_args, "INSERT 바인딩 str→date 변환 의무."


@pytest.mark.asyncio
async def test_backtest_runs_list_by_date_accepts_str_target_date():
    from src.db import backtest_runs

    with patch.object(backtest_runs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await backtest_runs.list_by_date(_STR_DATE)  # type: ignore[arg-type]

    bound_args = pg_mod.fetch.await_args.args[1:]
    assert _DATE_OBJ in bound_args


# ===========================================================================
# pending_next_day_clear.py — 4 DATE 바인딩 함수 (매매 안전성 인접 — 익일청산큐)
# ===========================================================================
@pytest.mark.asyncio
async def test_pending_ndc_save_accepts_str_target_date():
    from src.db import pending_next_day_clear as ndc

    with patch.object(ndc, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await ndc.save_pending_ndc(_STR_DATE, "005930", "volatility_breakout")  # type: ignore[arg-type]

    bound_args = pg_mod.execute.await_args.args[1:]
    assert _DATE_OBJ in bound_args


@pytest.mark.asyncio
async def test_pending_ndc_delete_accepts_str_target_date():
    from src.db import pending_next_day_clear as ndc

    with patch.object(ndc, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="DELETE 1")
        await ndc.delete_pending_ndc(_STR_DATE, "005930", "volatility_breakout")  # type: ignore[arg-type]

    bound_args = pg_mod.execute.await_args.args[1:]
    assert _DATE_OBJ in bound_args


@pytest.mark.asyncio
async def test_pending_ndc_load_accepts_str_target_date():
    """load_pending_ndc 는 _boot() 복구 경로 — str 입력 시에도 정상 조회돼야 한다."""
    from src.db import pending_next_day_clear as ndc

    with patch.object(ndc, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await ndc.load_pending_ndc(_STR_DATE)  # type: ignore[arg-type]

    bound_args = pg_mod.fetch.await_args.args[1:]
    assert _DATE_OBJ in bound_args


@pytest.mark.asyncio
async def test_pending_ndc_purge_before_accepts_str_target_date():
    from src.db import pending_next_day_clear as ndc

    with patch.object(ndc, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="DELETE 0")
        await ndc.purge_pending_ndc_before(_STR_DATE)  # type: ignore[arg-type]

    bound_args = pg_mod.execute.await_args.args[1:]
    assert _DATE_OBJ in bound_args


# ===========================================================================
# daily_performance.py — upsert_daily_performance
# ===========================================================================
@pytest.mark.asyncio
async def test_daily_performance_upsert_accepts_str_target_date():
    from src.db import daily_performance

    with patch.object(daily_performance, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await daily_performance.upsert_daily_performance(
            _STR_DATE,  # type: ignore[arg-type]
            total_asset=1_000_000.0, daily_profit_rate=0.0, strategy="total",
        )

    bound_args = pg_mod.execute.await_args.args[1:]
    assert _DATE_OBJ in bound_args


# ===========================================================================
# market_regime_snapshots.py — insert_snapshot / get_by_date
# ===========================================================================
@pytest.mark.asyncio
async def test_market_regime_snapshots_insert_accepts_str_snapshot_date():
    from src.db import market_regime_snapshots as mrs

    with patch.object(mrs, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])  # 중복 확인 SELECT
        pg_mod.fetchrow = AsyncMock(return_value={"id": "x"})
        await mrs.insert_snapshot(
            snapshot_date=_STR_DATE,  # type: ignore[arg-type]
            regime="neutral", regime_desc=None, cycle_phase=None,
            vix=None, fear_greed_score=None, buffett_ratio=None,
            raw_response={}, computed_cash_usage_ratio=None,
            buy_blocked=False, block_reason=None,
        )

    dedupe_args = pg_mod.fetch.await_args.args[1:]
    insert_args = pg_mod.fetchrow.await_args.args
    assert _DATE_OBJ in dedupe_args
    assert _DATE_OBJ in insert_args


@pytest.mark.asyncio
async def test_market_regime_snapshots_get_by_date_accepts_str():
    from src.db import market_regime_snapshots as mrs

    with patch.object(mrs, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=None)
        await mrs.get_by_date(_STR_DATE)  # type: ignore[arg-type]

    bound_args = pg_mod.fetchrow.await_args.args[1:]
    assert _DATE_OBJ in bound_args


# ===========================================================================
# positions.py — save_position (매매 hot path 인접, buy_date DATE 컬럼)
# ===========================================================================
@pytest.mark.asyncio
async def test_positions_save_position_accepts_str_buy_date():
    from src.db import positions

    with patch.object(positions, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await positions.save_position(
            ticker="005930", ticker_name="삼성전자", buy_price=70000,
            quantity=10, order_no="ORD1", strategy_id="momentum",
            buy_date=_STR_DATE,  # type: ignore[arg-type]
        )

    bound_args = pg_mod.execute.await_args.args[1:]
    assert _DATE_OBJ in bound_args


# ===========================================================================
# stock_master_daily.py — purge_old_rows(cutoff_date) str 입력 hardening
# ===========================================================================
@pytest.mark.asyncio
async def test_stock_master_daily_purge_old_rows_accepts_str_cutoff():
    from src.db import stock_master_daily as smd

    with patch.object(smd, "pg", create=True) as pg_mod:
        # SELECT oldest → 없음 (즉시 drained) — cutoff 바인딩만 검증
        pg_mod.fetchrow = AsyncMock(return_value=None)
        result = await smd.purge_old_rows(_STR_DATE)  # type: ignore[arg-type]

    assert result["deleted"] == 0
    bound_args = pg_mod.fetchrow.await_args.args[1:]
    assert _DATE_OBJ in bound_args, "purge_old_rows cutoff_date str→date 변환 의무."


@pytest.mark.asyncio
async def test_stock_master_daily_purge_old_rows_str_cutoff_parse_failure_graceful():
    """cutoff_date 가 파싱 불가 str 이어도 (to_date→None) 예외 없이 graceful 반환.

    회귀 방지: except 블록 내부의 `cutoff_date.isoformat()` 이 None 에 대해
    AttributeError 를 재차 raise 하면 graceful 계약이 깨진다.
    """
    from src.db import stock_master_daily as smd

    with patch.object(smd, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(side_effect=Exception("boom"))
        result = await smd.purge_old_rows("garbage-not-a-date")  # type: ignore[arg-type]

    assert result["deleted"] == 0, "예외 발생 시 부분 누적(0) graceful 반환."
    assert "elapsed_ms" in result
