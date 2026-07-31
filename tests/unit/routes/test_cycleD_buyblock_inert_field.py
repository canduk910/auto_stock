"""사이클 D Red (D-5) — BuyBlockStatusResponse.data_available + guard_inert 필드.

`_build_buy_block_status()` 응답에 관찰성 필드 2종 추가:
- `data_available: bool`  — 현재 메모리 regime 의 has_regime_data.
- `guard_inert: bool`     — `mode != "OFF" and not data_available` (가드 설정됐으나 무력).

행위:
- empty regime + SOFT → data_available=False, guard_inert=True (프론트 degraded 배너 근거).
- 데이터 유입 regime + SOFT → data_available=True, guard_inert=False.
- empty regime + OFF → data_available=False, guard_inert=False (OFF 는 무력 아님).

**blocked/soft_multiplier/reasons/mode/thresholds 응답 필드는 무변경** — 신규 2 필드는 표시용.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _patch_state_deps(monkeypatch, *, mode: str, regime):
    """_build_buy_block_status 의 DB 위임 + 메모리 regime 을 결정론적으로 고정.

    - sc.get_buy_block_mode / sc.get_buy_block_thresholds : 상단 fetch 용.
    - mr._db_get_buy_block_mode / mr._db_get_buy_block_thresholds : regime.get_buy_block_state() 용.
    - set_current_regime(regime) : 평가 대상 메모리 regime.
    """
    from src.db import system_config as sc
    from src.db.system_config import BuyBlockThresholds
    from src.engine import market_regime as mr

    async def _mode():
        return mode

    async def _thr():
        return BuyBlockThresholds(
            vix_threshold=25.0,
            fg_high_threshold=85.0,
            fg_low_threshold=15.0,
            defensive_enabled=True,
        )

    monkeypatch.setattr(sc, "get_buy_block_mode", _mode, raising=False)
    monkeypatch.setattr(sc, "get_buy_block_thresholds", _thr, raising=False)
    monkeypatch.setattr(mr, "_db_get_buy_block_mode", _mode, raising=False)
    monkeypatch.setattr(mr, "_db_get_buy_block_thresholds", _thr, raising=False)
    mr.set_current_regime(regime)


@pytest.fixture(autouse=True)
def _restore_regime():
    """테스트 후 모듈 싱글톤 regime 복원 (다른 테스트 격리)."""
    from src.engine import market_regime as mr

    saved = mr.get_current_regime()
    yield
    mr.set_current_regime(saved)


@pytest.mark.asyncio
async def test_build_buy_block_status_empty_regime_soft_guard_inert_true(monkeypatch):
    """empty regime + SOFT → data_available=False, guard_inert=True."""
    from src.engine.market_regime import MarketRegime
    from src.routes.system_integrations import _build_buy_block_status

    _patch_state_deps(monkeypatch, mode="SOFT", regime=MarketRegime.empty())
    status = await _build_buy_block_status()

    assert hasattr(status, "data_available"), "BuyBlockStatusResponse.data_available 부재"
    assert hasattr(status, "guard_inert"), "BuyBlockStatusResponse.guard_inert 부재"
    assert status.data_available is False
    assert status.guard_inert is True
    # 기존 응답 필드 회귀 0 — SOFT empty 는 fail-open (매매 행위 diff 0)
    assert status.mode == "SOFT"
    assert status.blocked is False
    assert status.soft_multiplier == 1.0


@pytest.mark.asyncio
async def test_build_buy_block_status_data_regime_soft_guard_inert_false(monkeypatch):
    """데이터 유입 regime + SOFT → data_available=True, guard_inert=False."""
    from src.engine.market_regime import MarketRegime
    from src.routes.system_integrations import _build_buy_block_status

    regime = MarketRegime(regime="neutral", vix=18.0, fear_greed_score=55.0)
    _patch_state_deps(monkeypatch, mode="SOFT", regime=regime)
    status = await _build_buy_block_status()

    assert status.data_available is True
    assert status.guard_inert is False


@pytest.mark.asyncio
async def test_build_buy_block_status_empty_regime_off_guard_inert_false(monkeypatch):
    """empty regime + OFF → guard_inert=False (OFF 는 무력 아님 — 가드 자체 비활성)."""
    from src.engine.market_regime import MarketRegime
    from src.routes.system_integrations import _build_buy_block_status

    _patch_state_deps(monkeypatch, mode="OFF", regime=MarketRegime.empty())
    status = await _build_buy_block_status()

    assert status.data_available is False
    assert status.guard_inert is False
