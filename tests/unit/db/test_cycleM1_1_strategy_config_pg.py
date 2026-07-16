"""사이클 M1-1 (Red) — src/db/strategy_config.py asyncpg 전환 계약 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, 증분 1).

현행 strategy_config.py = supabase-py 체인. 이 증분 = `pg.*` 전환.

핵심 계약 (JSONB + NUMERIC):
- load_all → {strategy_id: {"enabled": bool, "weight": float, "params": dict}}
  - `params` 는 JSONB → **dict** (asyncpg codec 실증은 통합 테스트, mock 은 dict 반환 계약).
  - `weight` 는 NUMERIC → `float(row["weight"])`.
- save → INSERT ... ON CONFLICT (strategy_id) DO UPDATE. params JSONB 바인딩.
- save_weights → 기존 params 유지 + weight 갱신.
- save_params → 기존 enabled/weight 유지 + params 갱신.

Red 유효성: production 미변경 → pg mock 미발화 → 계약 단언 FAIL.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# load_all — JSONB params dict + NUMERIC weight float
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_load_all_maps_rows_via_pg_fetch():
    """load_all → pg.fetch(SELECT * strategy_config) → 매핑 dict.

    weight float 변환 + params dict 보존 (codec 이 dict 반환 가정).
    """
    from src.db import strategy_config

    rows = [
        {
            "strategy_id": "momentum",
            "enabled": True,
            "weight": 0.4,  # NUMERIC → Decimal/float, float() 캐스트 대상
            "params": {"k_value": 1.3, "stop_loss_rate": -3.0},  # JSONB → dict
        },
        {
            "strategy_id": "volatility_breakout",
            "enabled": False,
            "weight": 0.0,
            "params": {},
        },
    ]
    with patch.object(strategy_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await strategy_config.load_all()

    assert set(out.keys()) == {"momentum", "volatility_breakout"}
    m = out["momentum"]
    assert m["enabled"] is True
    assert isinstance(m["weight"], float) and m["weight"] == 0.4, (
        "weight 는 NUMERIC → float 캐스트 계약."
    )
    assert isinstance(m["params"], dict) and m["params"]["k_value"] == 1.3, (
        "params 는 JSONB → dict 계약 (호출부 dict 접근)."
    )
    sql = pg_mod.fetch.await_args.args[0]
    assert "strategy_config" in sql and "SELECT" in sql.upper()


@pytest.mark.asyncio
async def test_load_all_params_non_dict_falls_back_to_empty():
    """params 가 dict 아니면 {} 폴백 (기존 isinstance 가드 계약 보존)."""
    from src.db import strategy_config

    rows = [
        {"strategy_id": "donchian_swing", "enabled": True, "weight": 0.1, "params": None},
    ]
    with patch.object(strategy_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await strategy_config.load_all()

    assert out["donchian_swing"]["params"] == {}, "params non-dict → {} 폴백 계약."


# ---------------------------------------------------------------------------
# save — INSERT ... ON CONFLICT (strategy_id) DO UPDATE + params JSONB
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_save_uses_pg_upsert_sql():
    """save → pg.execute 로 INSERT ... ON CONFLICT (strategy_id) DO UPDATE."""
    from src.db import strategy_config

    with patch.object(strategy_config, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await strategy_config.save(
            "momentum", True, 0.4, {"k_value": 1.3}
        )

    assert out is None, "save 반환형 None 계약 보존."
    assert pg_mod.execute.await_count == 1
    sql = pg_mod.execute.await_args.args[0]
    assert "INSERT INTO strategy_config" in sql
    assert "ON CONFLICT (strategy_id) DO UPDATE" in sql
    passed_args = pg_mod.execute.await_args.args[1:]
    assert "momentum" in passed_args, "strategy_id 바인딩 누락."
    # params 는 JSONB 바인딩 — dict 로 전달되어야 함 (codec 이 json.dumps).
    assert any(a == {"k_value": 1.3} for a in passed_args), (
        "params dict JSONB 바인딩 누락 (codec 왕복 계약)."
    )


# ---------------------------------------------------------------------------
# save_weights — 기존 params 유지 + weight 갱신
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_save_weights_preserves_existing_params():
    """save_weights → 기존 params SELECT(pg.fetch) 후 유지 + weight 갱신."""
    from src.db import strategy_config

    with patch.object(strategy_config, "pg", create=True) as pg_mod:
        # 기존 params 조회 결과
        pg_mod.fetch = AsyncMock(return_value=[{"params": {"k_value": 1.5}}])
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await strategy_config.save_weights({"momentum": 0.6})

    # SELECT params (fetch) + upsert (execute) 최소 1회씩
    assert pg_mod.fetch.await_count >= 1, "기존 params 조회(pg.fetch) 누락."
    assert pg_mod.execute.await_count >= 1, "weight 갱신 upsert(pg.execute) 누락."
    # 기존 params 가 upsert 인자에 보존
    exec_args = pg_mod.execute.await_args.args[1:]
    assert any(a == {"k_value": 1.5} for a in exec_args), (
        "save_weights 가 기존 params 를 보존해야 함."
    )


# ---------------------------------------------------------------------------
# save_params — 기존 enabled/weight 유지 + params 갱신
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_save_params_preserves_existing_enabled_weight():
    """save_params → 기존 enabled/weight SELECT 후 유지 + params 갱신."""
    from src.db import strategy_config

    with patch.object(strategy_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"enabled": True, "weight": 0.3}])
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await strategy_config.save_params("volatility_breakout", {"k_value": 1.2})

    assert pg_mod.fetch.await_count >= 1
    exec_args = pg_mod.execute.await_args.args[1:]
    assert any(a == {"k_value": 1.2} for a in exec_args), "새 params 반영 누락."


@pytest.mark.asyncio
async def test_save_params_missing_row_defaults():
    """save_params 대상 미존재 → 기본 (enabled=True, weight=0.5) 저장 계약."""
    from src.db import strategy_config

    with patch.object(strategy_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])  # 미존재
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await strategy_config.save_params("new_strat", {"foo": 1})

    exec_args = pg_mod.execute.await_args.args[1:]
    assert "new_strat" in exec_args
    assert any(a == {"foo": 1} for a in exec_args)


# ---------------------------------------------------------------------------
# 계약 보존 불변식 — supabase 미참조
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_strategy_config_no_supabase_reference_after_transition():
    """전환 후 strategy_config.py 는 supabase 를 참조하지 않는다 (pg 단독)."""
    from src.db import strategy_config

    assert not hasattr(strategy_config, "supabase"), (
        "전환 후 strategy_config 모듈에 supabase 심볼이 남으면 안 됨."
    )
    assert hasattr(strategy_config, "pg"), "strategy_config 가 src.db.pg 를 import 해야 함."
