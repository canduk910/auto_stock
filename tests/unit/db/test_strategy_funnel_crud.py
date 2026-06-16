"""사이클 34 (2026-05-21) — strategy_funnel_snapshots CRUD 테스트.

배경:
- 사용자 5/21 15:26 funnel 결함 (donchian 111→0 / BFB 30→0 / VCP 113→0) 시 단계별 살아남은
  종목을 알 수 없어 디버깅 곤란. 영구 추적 영역 신설.

본 사이클 (34) 변경:
- `strategy_funnel_snapshots` 테이블 신규 (migration 030)
- `src/db/strategy_funnel.py` CRUD 모듈 신규
  - `insert_snapshot(target_date, strategy_id, step_no, step_name, survived_tickers, excluded_sample, ...)`
  - `list_snapshots(target_date, strategy_id=None)` — 단일 영업일 모든 단계 조회
  - `list_recent_by_strategy(strategy_id, days=7)` — 추이 분석

사양 (F-1 ~ F-5):
- F-1: insert_snapshot 정상 INSERT (UUID PK 자동)
- F-2: survived_tickers cap 200 자동 적용 (insert 시점)
- F-3: excluded_sample cap 20 자동 적용
- F-4: list_snapshots — target_date + (선택) strategy_id 필터
- F-5: list_recent_by_strategy — 최근 N일 추이
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


def _patch_supabase(monkeypatch, rows_to_return: list[dict] | None = None,
                    insert_response_data: list[dict] | None = None):
    """supabase mock — table().insert/select/eq/order/execute 체인."""
    from src.db import strategy_funnel as sf_mod

    fluent = MagicMock()
    fluent.select.return_value = fluent
    fluent.insert.return_value = fluent
    fluent.eq.return_value = fluent
    fluent.gte.return_value = fluent
    fluent.lte.return_value = fluent
    fluent.order.return_value = fluent
    fluent.limit.return_value = fluent
    # SELECT execute → rows_to_return
    # INSERT/UPSERT execute → insert_response_data (사이클 145 UPSERT 의미 전환 영역 영구 영속)
    insert_call_count = [0]

    def _exec():
        if insert_call_count[0] > 0:
            return SimpleNamespace(data=insert_response_data or [])
        return SimpleNamespace(data=rows_to_return or [])

    def _insert_wrapper(*args, **kwargs):
        insert_call_count[0] += 1
        return fluent

    fluent.insert = MagicMock(side_effect=_insert_wrapper, return_value=fluent)
    # 사이클 145 — UPSERT 영역 영구 영속 의미 전환 (사이클 66 K-2 패턴 답습).
    fluent.upsert = MagicMock(side_effect=_insert_wrapper, return_value=fluent)
    fluent.execute = MagicMock(side_effect=_exec)

    supabase_mock = MagicMock()
    supabase_mock.table.return_value = fluent

    monkeypatch.setattr(sf_mod, "supabase", supabase_mock, raising=False)
    return fluent, supabase_mock


# ===========================================================================
# F-1: insert_snapshot 정상 INSERT
# ===========================================================================
@pytest.mark.asyncio
async def test_insert_snapshot_returns_row_with_uuid(monkeypatch):
    """insert_snapshot 정상 INSERT — UUID PK + 입력 필드 보존."""
    inserted_row = {
        "id": "00000000-0000-0000-0000-000000000001",
        "target_date": "2026-05-21",
        "strategy_id": "donchian_swing",
        "step_no": 4,
        "step_name": "20일 신고가 돌파",
        "survived_count": 0,
        "excluded_count": 111,
        "survived_tickers": [],
        "excluded_sample": [],
    }
    _patch_supabase(monkeypatch, insert_response_data=[inserted_row])

    from src.db.strategy_funnel import insert_snapshot
    result = await insert_snapshot(
        target_date=date(2026, 5, 21),
        strategy_id="donchian_swing",
        step_no=4,
        step_name="20일 신고가 돌파",
        survived_tickers=[],
        excluded_sample=[],
        survived_count=0,
        excluded_count=111,
    )

    assert result is not None
    assert result["id"] == inserted_row["id"]
    assert result["strategy_id"] == "donchian_swing"
    assert result["step_no"] == 4


# ===========================================================================
# F-2: survived_tickers cap 200
# ===========================================================================
@pytest.mark.asyncio
async def test_insert_snapshot_caps_survived_tickers_at_200(monkeypatch):
    """survived_tickers cap 200 — 입력 300개여도 200개만 저장."""
    fluent, _ = _patch_supabase(monkeypatch, insert_response_data=[{"id": "test"}])

    from src.db.strategy_funnel import insert_snapshot
    many = [f"{i:06d}" for i in range(300)]
    await insert_snapshot(
        target_date=date(2026, 5, 21),
        strategy_id="vcp_breakout",
        step_no=1,
        step_name="유니버스",
        survived_tickers=many,
        excluded_sample=[],
        survived_count=300,
        excluded_count=0,
    )

    # insert 호출 args 검증
    insert_args = fluent.upsert.call_args.args[0]
    assert len(insert_args["survived_tickers"]) == 200, (
        f"cap 200 미적용 — {len(insert_args['survived_tickers'])}건 저장"
    )


# ===========================================================================
# F-3: excluded_sample cap 20
# ===========================================================================
@pytest.mark.asyncio
async def test_insert_snapshot_caps_excluded_sample_at_20(monkeypatch):
    """excluded_sample cap 20 — 입력 50개여도 20개만 저장."""
    fluent, _ = _patch_supabase(monkeypatch, insert_response_data=[{"id": "test"}])

    from src.db.strategy_funnel import insert_snapshot
    many_excluded = [{"ticker": f"{i:06d}", "reason": "low_volume"} for i in range(50)]
    await insert_snapshot(
        target_date=date(2026, 5, 21),
        strategy_id="bull_flag_breakout",
        step_no=2,
        step_name="유니버스 필터",
        survived_tickers=[],
        excluded_sample=many_excluded,
        survived_count=0,
        excluded_count=30,
    )

    insert_args = fluent.upsert.call_args.args[0]
    assert len(insert_args["excluded_sample"]) == 20


# ===========================================================================
# F-4: list_snapshots 필터
# ===========================================================================
@pytest.mark.asyncio
async def test_list_snapshots_filters_by_date_and_strategy(monkeypatch):
    """list_snapshots(target_date, strategy_id=...) — eq 호출 검증."""
    rows = [
        {"id": "1", "target_date": "2026-05-21", "strategy_id": "donchian_swing",
         "step_no": 4, "step_name": "20일 신고가", "survived_count": 0, "excluded_count": 111,
         "survived_tickers": [], "excluded_sample": []},
    ]
    fluent, _ = _patch_supabase(monkeypatch, rows_to_return=rows)

    from src.db.strategy_funnel import list_snapshots
    result = await list_snapshots(target_date=date(2026, 5, 21), strategy_id="donchian_swing")

    assert len(result) == 1
    # eq 호출 인자 검증 — target_date + strategy_id 필터
    eq_args = [call.args for call in fluent.eq.call_args_list]
    assert ("target_date", "2026-05-21") in eq_args
    assert ("strategy_id", "donchian_swing") in eq_args


@pytest.mark.asyncio
async def test_list_snapshots_no_strategy_filter_returns_all(monkeypatch):
    """strategy_id=None 시 target_date 만 필터."""
    rows = [
        {"id": "1", "strategy_id": "donchian_swing", "step_no": 1, "step_name": "X",
         "survived_count": 0, "excluded_count": 0, "target_date": "2026-05-21",
         "survived_tickers": [], "excluded_sample": []},
        {"id": "2", "strategy_id": "vcp_breakout", "step_no": 1, "step_name": "X",
         "survived_count": 0, "excluded_count": 0, "target_date": "2026-05-21",
         "survived_tickers": [], "excluded_sample": []},
    ]
    fluent, _ = _patch_supabase(monkeypatch, rows_to_return=rows)

    from src.db.strategy_funnel import list_snapshots
    result = await list_snapshots(target_date=date(2026, 5, 21))
    assert len(result) == 2
    # strategy_id 필터 호출 없어야
    eq_args = [call.args for call in fluent.eq.call_args_list]
    strategy_filtered = any(a[0] == "strategy_id" for a in eq_args)
    assert not strategy_filtered


# ===========================================================================
# F-5: list_recent_by_strategy 최근 N일
# ===========================================================================
@pytest.mark.asyncio
async def test_list_recent_by_strategy_returns_n_days(monkeypatch):
    """list_recent_by_strategy(strategy_id, days=7) — gte 호출 검증."""
    rows = [{"id": "1", "target_date": "2026-05-21", "strategy_id": "vcp_breakout",
             "step_no": 8, "step_name": "최종", "survived_count": 5, "excluded_count": 0,
             "survived_tickers": [], "excluded_sample": []}]
    fluent, _ = _patch_supabase(monkeypatch, rows_to_return=rows)

    from src.db.strategy_funnel import list_recent_by_strategy
    result = await list_recent_by_strategy("vcp_breakout", days=7)
    assert len(result) >= 1
    # gte 호출 (날짜 범위)
    assert fluent.gte.called
