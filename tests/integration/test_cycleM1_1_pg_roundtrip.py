"""사이클 M1-1 (Red) — positions + strategy_config 실 Postgres 왕복 통합 검증.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, 증분 1).

mock 단위 테스트로 못 잡는 **실 SQL·JSONB codec** 안전망. docker/DATABASE_URL_TEST
없으면 pg_harness fixture 가 pytest.skip.

⚠️ 핵심 = strategy_config `params` JSONB 왕복이 **dict 로 반환**(str 아님)되는지.
`src/db/pg.py::_init_conn` 의 jsonb codec 이 미작동하면 이 테스트가 실패 = 계획
3대 리스크 1순위(JSONB codec 누락 silent 폴백) 라이브 가드.

Red 유효성: production(positions/strategy_config)이 아직 pg 미사용 → 실 PG 왕복
경로 없음(supabase 미연결) → 이 테스트 전부 FAIL/에러.
"""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


# ---------------------------------------------------------------------------
# positions — save → load_all 왕복 / upsert 갱신 / delete / clear_all
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_positions_save_load_roundtrip(clean_positions):
    """save_position → load_all 왕복: dict 키 = 컬럼명 정합."""
    from src.db import positions

    await positions.save_position(
        ticker="005930",
        ticker_name="삼성전자",
        buy_price=70000,
        quantity=10,
        order_no="BUY-000001",
        strategy_id="momentum",
        buy_date=date(2026, 7, 16),
        high_since_buy=71000,
    )
    rows = await positions.load_all()

    assert len(rows) == 1
    r = rows[0]
    # order_engine 이 소비하는 컬럼 키 전부 정합
    assert r["ticker"] == "005930"
    assert r["ticker_name"] == "삼성전자"
    assert r["buy_price"] == 70000
    assert r["quantity"] == 10
    assert r["order_no"] == "BUY-000001"
    assert r["strategy_id"] == "momentum"
    assert r["high_since_buy"] == 71000
    # buy_date 는 DATE → date 객체 (str 아님)
    assert r["buy_date"] == date(2026, 7, 16)


@pytest.mark.asyncio
async def test_positions_upsert_same_ticker_single_row(clean_positions):
    """동일 ticker 2회 save → ON CONFLICT (ticker) 로 1행 갱신 (중복 없음)."""
    from src.db import positions

    await positions.save_position(
        "005930", "삼성전자", 70000, 10, "BUY-1", "momentum",
        date(2026, 7, 16), 70000,
    )
    await positions.save_position(
        "005930", "삼성전자", 72000, 15, "BUY-2", "momentum",
        date(2026, 7, 16), 73000,
    )
    rows = await positions.load_all()

    assert len(rows) == 1, "동일 ticker upsert → 1행."
    assert rows[0]["quantity"] == 15, "최신 값으로 갱신."
    assert rows[0]["buy_price"] == 72000


@pytest.mark.asyncio
async def test_positions_update_high(clean_positions):
    """update_high → high_since_buy 갱신."""
    from src.db import positions

    await positions.save_position(
        "000660", "SK하이닉스", 100000, 5, "BUY-3", "volatility_breakout",
        date(2026, 7, 16), 100000,
    )
    await positions.update_high("000660", 105000)
    rows = await positions.load_all()

    assert rows[0]["high_since_buy"] == 105000


@pytest.mark.asyncio
async def test_positions_delete(clean_positions):
    """delete_position → 해당 ticker 만 삭제."""
    from src.db import positions

    await positions.save_position(
        "005930", "삼성전자", 70000, 10, "BUY-1", "momentum",
        date(2026, 7, 16), 70000,
    )
    await positions.save_position(
        "000660", "SK하이닉스", 100000, 5, "BUY-2", "volatility_breakout",
        date(2026, 7, 16), 100000,
    )
    await positions.delete_position("005930")
    rows = await positions.load_all()

    assert len(rows) == 1
    assert rows[0]["ticker"] == "000660"


@pytest.mark.asyncio
async def test_positions_clear_all(clean_positions):
    """clear_all → 전체 삭제."""
    from src.db import positions

    await positions.save_position(
        "005930", "삼성전자", 70000, 10, "BUY-1", "momentum",
        date(2026, 7, 16), 70000,
    )
    await positions.save_position(
        "000660", "SK하이닉스", 100000, 5, "BUY-2", "volatility_breakout",
        date(2026, 7, 16), 100000,
    )
    await positions.clear_all()
    rows = await positions.load_all()

    assert rows == [], "clear_all 후 0건."


# ---------------------------------------------------------------------------
# strategy_config — ⚠️ JSONB codec 실증 (계획 3대 리스크 1순위)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_strategy_config_jsonb_params_returns_dict(clean_strategy_config):
    """⚠️ save → load_all 후 params 가 **dict** (str 아님) = JSONB codec 실증.

    codec 미등록 시 asyncpg 는 JSONB 를 str 로 반환 → 이 단언 FAIL →
    매매 파라미터 silent 폴백 라이브 가드.
    """
    from src.db import strategy_config

    params = {"k_value": 1.3, "stop_loss_rate": -3.0, "nested": {"a": [1, 2, 3]}}
    await strategy_config.save("momentum", True, 0.4, params)

    configs = await strategy_config.load_all()
    m = configs["momentum"]

    assert isinstance(m["params"], dict), (
        "params 가 dict 아님 → JSONB codec 미작동 (계획 최대 위험 실현)."
    )
    assert m["params"] == params, "JSONB 왕복 무손실 (중첩 dict/list 보존)."
    assert m["params"]["nested"]["a"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_strategy_config_weight_is_float(clean_strategy_config):
    """weight NUMERIC → float (호출부 float 계약)."""
    from src.db import strategy_config

    await strategy_config.save("volatility_breakout", True, 0.35, {})
    configs = await strategy_config.load_all()

    w = configs["volatility_breakout"]["weight"]
    assert isinstance(w, float), "weight 는 float 캐스트."
    assert abs(w - 0.35) < 1e-9


@pytest.mark.asyncio
async def test_strategy_config_upsert_same_id_single_row(clean_strategy_config):
    """동일 strategy_id 2회 save → ON CONFLICT (strategy_id) 1행 갱신."""
    from src.db import strategy_config

    await strategy_config.save("momentum", True, 0.4, {"k_value": 1.3})
    await strategy_config.save("momentum", False, 0.0, {"k_value": 1.5})
    configs = await strategy_config.load_all()

    assert len(configs) == 1
    assert configs["momentum"]["enabled"] is False
    assert configs["momentum"]["weight"] == 0.0
    assert configs["momentum"]["params"]["k_value"] == 1.5


@pytest.mark.asyncio
async def test_save_weights_preserves_params_roundtrip(clean_strategy_config):
    """save_weights → 기존 params JSONB 유지 + weight 갱신 (실 PG)."""
    from src.db import strategy_config

    await strategy_config.save("momentum", True, 0.4, {"k_value": 1.7})
    await strategy_config.save_weights({"momentum": 0.6})
    configs = await strategy_config.load_all()

    assert configs["momentum"]["weight"] == 0.6
    assert configs["momentum"]["params"] == {"k_value": 1.7}, (
        "save_weights 가 기존 params JSONB 를 보존해야 함."
    )


@pytest.mark.asyncio
async def test_save_params_preserves_weight_roundtrip(clean_strategy_config):
    """save_params → 기존 enabled/weight 유지 + params 갱신 (실 PG)."""
    from src.db import strategy_config

    await strategy_config.save("donchian_swing", True, 0.25, {"old": 1})
    await strategy_config.save_params("donchian_swing", {"new": 2})
    configs = await strategy_config.load_all()

    assert configs["donchian_swing"]["weight"] == 0.25
    assert configs["donchian_swing"]["enabled"] is True
    assert configs["donchian_swing"]["params"] == {"new": 2}
