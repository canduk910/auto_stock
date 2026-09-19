"""`src/db/system_config.py::get/set_auto_regime_adjust`.

매크로 레짐 기반 cash_usage_ratio 자동 조정 토글.

요구 행위:
1. `get_auto_regime_adjust()` — 키 부재·판독 불가 시 기본 **False**(수동 모드).
2. `set_auto_regime_adjust(False)` → upsert + 재조회 False.
3. round-trip: True → False → True.

🔴 **기본값이 False 인 이유**(2026-09-19 `domain-consult` + 사용자 승인) — 이 함수가 True 를
돌려주면 레짐의 `cash_min` 이 그대로 `cash_usage_ratio` 로 **DB 에 영속**된다. 지금 우리 macro 는
`defensive`(`cash_min=75`)를 내므로 그 값이 **0.25** 이고, 예산이 4분의 1이 되면 터틀 유닛·ρ축
cutoff·K축 cap 이 함께 접혀 고가 종목은 1주 폴백까지 막힌다. 그런데 로그에는
`매수 수량 0 → 900s cooldown` 으로만 남아 일일 리포트에서 「투자금 부족」으로 오귀인된다.
**설정을 못 읽었다는 이유로 매수 자금의 4분의 3이 사라지면 안 된다** — 못 읽으면 운영자가
명시로 저장해 둔 마지막 값을 쓴다. 자동 조정은 사람이 켜는 기능이다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_get_default_false_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    """키가 없으면 **수동 모드**다 — 자동 조정은 사람이 켠다."""
    from src.db import system_config

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)

    enabled = await system_config.get_auto_regime_adjust()
    assert enabled is False


@pytest.mark.asyncio
async def test_set_false_then_get_false(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)

    await system_config.set_auto_regime_adjust(False)
    enabled = await system_config.get_auto_regime_adjust()
    assert enabled is False


@pytest.mark.asyncio
async def test_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    fake_pg_kv,
):
    from src.db import system_config

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)

    await system_config.set_auto_regime_adjust(False)
    assert await system_config.get_auto_regime_adjust() is False
    await system_config.set_auto_regime_adjust(True)
    assert await system_config.get_auto_regime_adjust() is True
