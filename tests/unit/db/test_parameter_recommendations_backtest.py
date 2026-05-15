"""Phase 3 Red — `src/db/parameter_recommendations.py` 백테스트 동봉 CRUD.

요구 행위:

1. ``update_backtest_summary(rec_id, summary)`` — 단일 row 의 ``backtest_summary`` JSONB 갱신.
   - 정상 갱신 시 갱신된 row dict 반환.
   - 적용 row 0건이면 빈 dict 반환.
2. ``list_recommendations_pending_backtest(target_date)`` — 폴 루프 진입 가드용.
   - 해당 영업일의 ``backtest_summary IS NULL`` 인 row 만 반환.

supabase 동기 SDK 호출은 모두 ``asyncio.to_thread`` 위임 — ``src/db/CLAUDE.md`` 규약.
테스트는 ``src.db.parameter_recommendations.supabase`` 를 ``FakeSupabase`` 로 monkeypatch.
"""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_update_backtest_summary_persists_jsonb(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """A: update_backtest_summary — 신규 컬럼 영속화 + 반환 dict 확인."""
    from src.db import parameter_recommendations as pr_mod

    monkeypatch.setattr(pr_mod, "supabase", fake_supabase)

    # 사전 INSERT — id 기반 갱신 대상
    row = await pr_mod.insert_recommendation(
        target_date=date(2026, 5, 16),
        strategy_id="momentum",
        current_params={"buy_threshold": 29.0},
        recommended_params={"buy_threshold": 27.0},
        reasoning="test",
        metrics={},
    )
    assert row is not None
    rec_id = row["id"]

    summary = {
        "current": {"momentum": {"total_return_pct": 12.3, "sharpe_ratio": 1.4}},
        "recommended": {"momentum": {"total_return_pct": 18.7, "sharpe_ratio": 1.9}},
        "diff": {"momentum": {"total_return_pct": 6.4, "sharpe_ratio": 0.5}},
    }
    updated = await pr_mod.update_backtest_summary(rec_id, summary)

    assert updated, "갱신된 row 가 반환되어야 한다"
    assert updated["backtest_summary"]["current"]["momentum"]["total_return_pct"] == 12.3
    assert updated["backtest_summary"]["diff"]["momentum"]["sharpe_ratio"] == 0.5

    # 다시 조회해도 동일
    again = await pr_mod.get_recommendation(rec_id)
    assert again is not None
    assert again["backtest_summary"]["recommended"]["momentum"]["sharpe_ratio"] == 1.9


@pytest.mark.asyncio
async def test_update_backtest_summary_no_match_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """A-2: 미존재 ID 호출 시 빈 dict 반환 (예외 발생 금지)."""
    from src.db import parameter_recommendations as pr_mod

    monkeypatch.setattr(pr_mod, "supabase", fake_supabase)

    result = await pr_mod.update_backtest_summary(
        "00000000-0000-0000-0000-000000000000",
        {"current": {}, "recommended": {}, "diff": {}},
    )
    assert result == {}


@pytest.mark.asyncio
async def test_list_recommendations_pending_backtest_filters(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """B: list_recommendations_pending_backtest — backtest_summary IS NULL 만 반환."""
    from src.db import parameter_recommendations as pr_mod

    monkeypatch.setattr(pr_mod, "supabase", fake_supabase)

    # 3 행: 1 행은 summary 동봉, 2 행은 pending
    target = date(2026, 5, 16)
    r1 = await pr_mod.insert_recommendation(
        target_date=target,
        strategy_id="momentum",
        current_params={},
        recommended_params={},
        reasoning="",
        metrics={},
    )
    r2 = await pr_mod.insert_recommendation(
        target_date=target,
        strategy_id="volatility_breakout",
        current_params={},
        recommended_params={},
        reasoning="",
        metrics={},
    )
    r3 = await pr_mod.insert_recommendation(
        target_date=target,
        strategy_id="donchian_swing",
        current_params={},
        recommended_params={},
        reasoning="",
        metrics={},
    )
    assert r1 and r2 and r3

    # r1 만 summary 동봉
    await pr_mod.update_backtest_summary(
        r1["id"], {"current": {}, "recommended": {}, "diff": {}}
    )

    pending = await pr_mod.list_recommendations_pending_backtest(target)
    pending_ids = {p["id"] for p in pending}
    assert pending_ids == {r2["id"], r3["id"]}


@pytest.mark.asyncio
async def test_metric_diff_helper_basic(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """C: 비교 메트릭 diff 헬퍼 — recommended - current."""
    from src.models.backtest import COMPARE_METRIC_KEYS, compute_metric_diff

    current = {
        "total_return_pct": 10.0,
        "sharpe_ratio": 1.0,
        "max_drawdown": -10.0,
        "total_trades": 20,
        "win_rate": 0.5,
    }
    recommended = {
        "total_return_pct": 15.0,
        "sharpe_ratio": 1.5,
        "max_drawdown": -7.0,
        "total_trades": 22,
        "win_rate": 0.6,
    }
    diff = compute_metric_diff(current, recommended)
    assert diff["total_return_pct"] == pytest.approx(5.0)
    assert diff["sharpe_ratio"] == pytest.approx(0.5)
    # max_drawdown 도 단순 산술 차이 — UI 에서 절댓값 해석 책임
    assert diff["max_drawdown"] == pytest.approx(3.0)
    assert diff["total_trades"] == pytest.approx(2.0)
    assert diff["win_rate"] == pytest.approx(0.1)
    # COMPARE_METRIC_KEYS 에만 있고 입력엔 없는 키는 결과에도 없음
    assert "cagr" not in diff
    # COMPARE_METRIC_KEYS 가 실제로 8개 핵심 메트릭을 커버
    assert set(COMPARE_METRIC_KEYS) >= {
        "total_return_pct", "sharpe_ratio", "max_drawdown", "win_rate", "total_trades",
    }


@pytest.mark.asyncio
async def test_metric_diff_helper_handles_none(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """C-2: current/recommended 둘 중 하나가 None 이면 빈 dict."""
    from src.models.backtest import compute_metric_diff

    assert compute_metric_diff(None, {"total_return_pct": 1.0}) == {}
    assert compute_metric_diff({"total_return_pct": 1.0}, None) == {}
    # 양쪽 모두 None
    assert compute_metric_diff(None, None) == {}
