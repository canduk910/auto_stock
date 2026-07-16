"""사이클 M2a (Red) — src/db/system_config.py asyncpg 전환 계약 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 2 — 매매 hot path, HIGH).

현행 system_config.py = supabase-py 체인 + `execute_with_retry`(사이클 189). 이 증분 = `pg.*` 전환.
**함수 계약(시그니처·반환형·graceful 폴백) 100% 보존** → 호출부(risk/order_engine/scheduler/boot) diff 0.

⚠️ 최대 위험 (계획 3대 리스크 1순위) — JSONB `{"value": x}` codec:
asyncpg 는 JSONB 를 기본 str 반환 → `_init_conn` codec 미작동 시 `isinstance(raw, dict)` False →
전 설정 silent 폴백 (cash_usage_ratio=1.0 강제 등 매매 파라미터 오작동). mock 은 codec 이 dict 로
복원한 계약을 재현 (dict 반환), 실 codec 실증은 통합 테스트.

핵심 계약:
- read 헬퍼: JSONB `{"value": x}` → dict → 실제 값 (bool/float/int/str 타입별). 키 부재/타입 불일치 → default.
- read 는 `pg._with_retry` 경유 (사이클 189 정책 = read 만 retry, 쓰기 미경유).
- upsert: INSERT ... ON CONFLICT (key) DO UPDATE. `{"value": v}` dict JSONB 바인딩 + updated_at datetime.
- set_*: 범위 밖 ValueError 보존 (매매 파라미터 안전 가드).

Red 유효성: production 미변경 → pg mock 미발화 → 계약 단언 FAIL.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# get_cash_usage_ratio — ⚠️ JSONB {"value": float} → dict → float (codec 1순위 가드)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_cash_usage_ratio_jsonb_dict_returns_value():
    """⚠️ {"value": 0.35} dict → 0.35 (codec 미작동 시 default 1.0 폴백 = FAIL로 잡는 1순위 가드)."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        # codec 이 JSONB 를 dict 로 복원한 상태를 재현 (raw = {"value": 0.35})
        pg_mod.fetch = AsyncMock(return_value=[{"value": {"value": 0.35}}])
        out = await system_config.get_cash_usage_ratio()

    assert out == 0.35, (
        "JSONB {\"value\": x} dict → 실제 값. 1.0 이면 codec 미작동 silent 폴백 (매매 파라미터 오작동)."
    )
    assert isinstance(out, float)
    sql = pg_mod.fetch.await_args.args[0]
    assert "system_config" in sql and "SELECT" in sql.upper()
    passed = pg_mod.fetch.await_args.args[1:]
    assert "cash_usage_ratio" in passed, "key 바인딩 누락."


@pytest.mark.asyncio
async def test_get_cash_usage_ratio_missing_key_default_1_0():
    """키 부재(0건) → 기본 1.0 (기존 폴백 계약 보존)."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await system_config.get_cash_usage_ratio()

    assert out == 1.0, "키 부재 → 기본 1.0."


@pytest.mark.asyncio
async def test_get_cash_usage_ratio_uses_with_retry():
    """read 는 pg._with_retry 경유 (사이클 189 정책 = read retry). 발화 여부 단언.

    구현 자유도: fetch 가 내부적으로 _with_retry 를 태우거나, 모듈이 _with_retry 를
    명시 호출한다. 최소한 fetch 발화 + system_config 모듈이 pg 의 _with_retry 를 노출.
    """
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"value": {"value": 0.5}}])
        pg_mod._with_retry = AsyncMock()
        await system_config.get_cash_usage_ratio()

    assert pg_mod.fetch.await_count >= 1, "read 경로 pg.fetch 발화 누락."


# ---------------------------------------------------------------------------
# get_auto_regime_adjust — JSONB {"value": bool} → bool
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_auto_regime_adjust_jsonb_dict_bool():
    """{"value": False} dict → False (bool 타입 계약)."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"value": {"value": False}}])
        out = await system_config.get_auto_regime_adjust()

    assert out is False, "JSONB bool → False (codec dict 복원)."


@pytest.mark.asyncio
async def test_get_auto_regime_adjust_missing_default_true():
    """키 부재 → 기본 True."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await system_config.get_auto_regime_adjust()

    assert out is True, "키 부재 → 기본 True."


# ---------------------------------------------------------------------------
# get_buy_block_mode — JSONB {"value": str} → str + 4모드 검증 + invalid 폴백
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_buy_block_mode_jsonb_dict_valid_mode():
    """{"value": "SOFT"} → 'SOFT' (str + 유효 모드)."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"value": {"value": "SOFT"}}])
        out = await system_config.get_buy_block_mode()

    assert out == "SOFT", "JSONB str → 유효 모드 그대로."


@pytest.mark.asyncio
async def test_get_buy_block_mode_invalid_falls_back_hard():
    """저장값이 4모드 밖 → 기본 HARD 폴백 (기존 검증 계약 보존)."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"value": {"value": "WEIRD"}}])
        out = await system_config.get_buy_block_mode()

    assert out == "HARD", "4모드 밖 → HARD 폴백 (매수 가드 안전 회귀)."


@pytest.mark.asyncio
async def test_get_buy_block_mode_missing_default_hard():
    """키 부재 → 기본 HARD (사이클 2 회귀 보존)."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await system_config.get_buy_block_mode()

    assert out == "HARD"


# ---------------------------------------------------------------------------
# _get_float_or_default / _get_int_or_default — JSONB numeric
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_float_or_default_jsonb_dict():
    """{"value": 30.0} dict → 30.0 (float 캐스트)."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"value": {"value": 30.0}}])
        out = await system_config._get_float_or_default("buy_block_vix_threshold", 25.0)

    assert out == 30.0 and isinstance(out, float)


@pytest.mark.asyncio
async def test_get_float_or_default_missing_returns_default():
    """키 부재 → default."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await system_config._get_float_or_default("k", 25.0)

    assert out == 25.0


@pytest.mark.asyncio
async def test_get_int_or_default_jsonb_dict():
    """{"value": 5000} dict → 5000 (int 캐스트)."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"value": {"value": 5000}}])
        out = await system_config._get_int_or_default("price_filter_min", 0)

    assert out == 5000 and isinstance(out, int)


# ---------------------------------------------------------------------------
# _get_bool_or_default / _get_bool_or_none / _get_string_or_none
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_bool_or_default_jsonb_dict():
    """{"value": True} dict → True (bool)."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"value": {"value": True}}])
        out = await system_config._get_bool_or_default("k", False)

    assert out is True


@pytest.mark.asyncio
async def test_get_bool_or_none_missing_returns_none():
    """키 부재 → None (호출자 .env fallback 계약 보존)."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await system_config._get_bool_or_none("dkstock_regime_enabled")

    assert out is None, "키 부재 → None (bool_or_none 계약)."


@pytest.mark.asyncio
async def test_get_string_or_none_jsonb_dict():
    """{"value": "abc"} dict → 'abc' (str)."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"value": {"value": "abc"}}])
        out = await system_config._get_string_or_none("krx_open_api_key")

    assert out == "abc"


@pytest.mark.asyncio
async def test_get_string_or_none_missing_returns_none():
    """키 부재 → None."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await system_config._get_string_or_none("k")

    assert out is None


# ---------------------------------------------------------------------------
# read graceful — 예외 시 default 폴백 (매매 파라미터 안전)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_cash_usage_ratio_exception_graceful_default():
    """pg.fetch 예외 → 기본 1.0 graceful (기존 try/except 계약 보존)."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=Exception("boom"))
        out = await system_config.get_cash_usage_ratio()

    assert out == 1.0, "read 예외 → 기본 1.0 graceful (매매 파라미터 안전)."


# ---------------------------------------------------------------------------
# set_cash_usage_ratio — upsert key PK + 범위/step 검증
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_set_cash_usage_ratio_uses_pg_upsert_key():
    """set → pg.execute INSERT ... ON CONFLICT (key) DO UPDATE + {"value": v} dict 바인딩."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetchrow = AsyncMock(return_value=None)
        out = await system_config.set_cash_usage_ratio(0.35)

    assert out is None, "set_cash_usage_ratio 반환형 None 계약 보존."
    all_sql = _collect_sql(pg_mod)
    assert any("INSERT INTO system_config" in s for s in all_sql), "INSERT INTO system_config 누락."
    assert any("ON CONFLICT (key) DO UPDATE" in s for s in all_sql), (
        "key PK upsert = ON CONFLICT (key) DO UPDATE 누락."
    )
    args = _insert_args(pg_mod)
    assert "cash_usage_ratio" in args, "key 바인딩 누락."
    # JSONB {"value": 0.35} dict 바인딩 (codec 이 json.dumps — dict 직접 전달)
    assert any(a == {"value": 0.35} for a in args), (
        "value JSONB dict 바인딩 누락 ({\"value\": adjusted}, codec 왕복 계약)."
    )
    # updated_at datetime 바인딩 (M1 패턴 2 — asyncpg TIMESTAMPTZ str 금지)
    assert any(isinstance(a, datetime) for a in args), (
        "updated_at 은 datetime 바인딩 (fromisoformat(now_kst_iso())) — str 금지."
    )


@pytest.mark.asyncio
async def test_set_cash_usage_ratio_step_rounding():
    """step 0.05 보정 — 0.37 → 0.35 (기존 보정 계약 보존)."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetchrow = AsyncMock(return_value=None)
        await system_config.set_cash_usage_ratio(0.37)

    args = _insert_args(pg_mod)
    assert any(a == {"value": 0.35} for a in args), "step 0.05 보정 계약 (0.37 → 0.35)."


@pytest.mark.asyncio
async def test_set_cash_usage_ratio_out_of_range_raises():
    """범위 밖 → ValueError (매매 파라미터 안전 가드 보존). pg 미발화."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        with pytest.raises(ValueError):
            await system_config.set_cash_usage_ratio(1.5)

    assert pg_mod.execute.await_count == 0, "범위 밖은 DB 미기록 (ValueError 선행)."


@pytest.mark.asyncio
async def test_set_buy_block_mode_invalid_raises():
    """4모드 밖 → ValueError. pg 미발화."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        with pytest.raises(ValueError):
            await system_config.set_buy_block_mode("NOPE")

    assert pg_mod.execute.await_count == 0


@pytest.mark.asyncio
async def test_set_buy_block_mode_valid_upsert():
    """유효 모드 → upsert (key) + {"value": mode} 바인딩."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetchrow = AsyncMock(return_value=None)
        await system_config.set_buy_block_mode("WARN")

    args = _insert_args(pg_mod)
    assert "buy_block_mode" in args
    assert any(a == {"value": "WARN"} for a in args), "value JSONB {\"value\": mode} 바인딩 누락."


# ---------------------------------------------------------------------------
# 쓰기는 _with_retry 미경유 (사이클 189 정책 = 멱등 우려로 쓰기 미적용)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_set_does_not_use_with_retry():
    """set_* 쓰기는 pg.execute 직접 (retry 미경유). _with_retry 미발화 단언."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod._with_retry = AsyncMock()
        await system_config.set_cash_usage_ratio(0.5)

    assert pg_mod._with_retry.await_count == 0, (
        "쓰기(set_*)는 _with_retry 미경유 (사이클 189 정책 = 멱등 우려)."
    )


# ---------------------------------------------------------------------------
# task 신선도 마커 (사이클 193) — get/set task_last_success
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_task_last_success_jsonb_str():
    """get_task_last_success → _get_string_or_none 경유 str 반환."""
    from src.db import system_config

    with patch.object(system_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"value": {"value": "2026-07-16T16:10:00+09:00"}}])
        out = await system_config.get_task_last_success("basics")

    assert out == "2026-07-16T16:10:00+09:00"
    passed = pg_mod.fetch.await_args.args[1:]
    assert "task_last_success_basics" in passed, "task 마커 key prefix 정합 누락."


# ---------------------------------------------------------------------------
# 계약 보존 불변식 — supabase / execute_with_retry 미참조 (pg 단독)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_system_config_no_supabase_reference_after_transition():
    """전환 후 system_config.py 는 supabase / execute_with_retry 를 참조하지 않는다 (pg 단독)."""
    from src.db import system_config

    assert not hasattr(system_config, "supabase"), (
        "전환 후 system_config 모듈에 supabase 심볼이 남으면 안 됨 (pg 단독)."
    )
    assert not hasattr(system_config, "execute_with_retry"), (
        "전환 후 supabase execute_with_retry 심볼 잔존 금지 (pg._with_retry 로 대체)."
    )
    assert hasattr(system_config, "pg"), "system_config 가 src.db.pg 를 import 해야 함."


# ---------------------------------------------------------------------------
# 헬퍼 — 발화 경로 SQL·인자 수집 (Green 자유도)
# ---------------------------------------------------------------------------
def _collect_sql(pg_mod) -> list[str]:
    sqls: list[str] = []
    for name in ("execute", "fetchrow", "fetch", "fetchval"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            sqls.append(m.await_args.args[0])
    return sqls


def _insert_args(pg_mod) -> tuple:
    """INSERT 를 실제 발화한 mock(execute 우선, 없으면 fetchrow)의 바인딩 인자."""
    for name in ("execute", "fetchrow"):
        m = getattr(pg_mod, name, None)
        if m is not None and getattr(m, "await_args", None) is not None:
            sql = m.await_args.args[0]
            if "INSERT" in sql.upper():
                return m.await_args.args[1:]
    return ()
