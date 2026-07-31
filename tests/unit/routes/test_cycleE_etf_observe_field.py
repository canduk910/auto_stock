"""사이클 E-1 Red (E-6) — buy-block 응답에 지수ETF 관찰 필드 노출.

명세: `_workspace/red/_behaviors_cycleE_etf_regime_20260731.md` (E-6)

`_build_buy_block_status()` → `BuyBlockStatusResponse` 에 관찰 필드 4종 추가:
- `etf_kospi_stage: int | None`   — KODEX200(069500) 현재 스테이지 (신호 부재 시 None)
- `etf_kosdaq_stage: int | None`  — KODEX 코스닥150(229200) 현재 스테이지
- `etf_defensive: bool | None`    — 2일 방어 OR (양쪽 stale 시 None)
- `etf_enabled: bool`             — etf_regime_enabled 토글 (다크런치 = False)

소스 = boot 부착 싱글톤 `market_regime.get_current_etf_signal()` (요청마다 재계산 X) +
`system_config.get_etf_regime_enabled()`. **mode/blocked/reasons/soft_multiplier/
data_available/guard_inert 응답 필드는 무변경** — 신규 4 필드는 관찰(curl) 전용, 배제 0.

RED = BuyBlockStatusResponse 에 etf_* 필드 부재.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def _patch_state_deps(monkeypatch, *, mode: str, regime):
    """_build_buy_block_status 의 DB 위임 + 메모리 regime 고정 (test_cycleD_buyblock 답습)."""
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


def _patch_etf(monkeypatch, *, signal, enabled: bool):
    """etf 관찰 소스 고정 — get_current_etf_signal + get_etf_regime_enabled."""
    from src.db import system_config as sc
    from src.engine import market_regime as mr

    monkeypatch.setattr(mr, "get_current_etf_signal", lambda: signal, raising=False)

    async def _enabled():
        return enabled

    monkeypatch.setattr(sc, "get_etf_regime_enabled", _enabled, raising=False)


def _etf_signal(**kw) -> SimpleNamespace:
    base = dict(
        kospi_stage=4, kosdaq_stage=4,
        kospi_defensive_2d=True, kosdaq_defensive_2d=True,
        etf_defensive=True, stale_kospi=False, stale_kosdaq=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _restore_singletons():
    """모듈 싱글톤 regime + etf signal 복원."""
    from src.engine import market_regime as mr

    saved_regime = mr.get_current_regime()
    saved_etf = getattr(mr, "get_current_etf_signal", lambda: None)()
    yield
    mr.set_current_regime(saved_regime)
    setter = getattr(mr, "set_current_etf_signal", None)
    if setter is not None:
        setter(saved_etf)


@pytest.mark.asyncio
async def test_buy_block_status_exposes_etf_observe_fields(monkeypatch):
    """etf 신호 존재 + 다크런치(enabled=False) → 관찰 4 필드 노출."""
    from src.engine.market_regime import MarketRegime
    from src.routes.system_integrations import _build_buy_block_status

    _patch_state_deps(monkeypatch, mode="SOFT", regime=MarketRegime.empty())
    _patch_etf(
        monkeypatch,
        signal=_etf_signal(kospi_stage=4, kosdaq_stage=4, etf_defensive=True),
        enabled=False,
    )

    status = await _build_buy_block_status()

    assert hasattr(status, "etf_kospi_stage"), "BuyBlockStatusResponse.etf_kospi_stage 부재"
    assert hasattr(status, "etf_kosdaq_stage"), "etf_kosdaq_stage 부재"
    assert hasattr(status, "etf_defensive"), "etf_defensive 부재"
    assert hasattr(status, "etf_enabled"), "etf_enabled 부재"

    assert status.etf_kospi_stage == 4
    assert status.etf_kosdaq_stage == 4
    assert status.etf_defensive is True
    assert status.etf_enabled is False


@pytest.mark.asyncio
async def test_buy_block_status_etf_fields_none_when_signal_absent(monkeypatch):
    """부착 신호 부재(None) → 스테이지/방어 None, enabled 는 여전히 조회 가능."""
    from src.engine.market_regime import MarketRegime
    from src.routes.system_integrations import _build_buy_block_status

    _patch_state_deps(monkeypatch, mode="SOFT", regime=MarketRegime.empty())
    _patch_etf(monkeypatch, signal=None, enabled=False)

    status = await _build_buy_block_status()

    assert status.etf_kospi_stage is None
    assert status.etf_kosdaq_stage is None
    assert status.etf_defensive is None
    assert status.etf_enabled is False


@pytest.mark.asyncio
async def test_buy_block_status_etf_enabled_passthrough_true(monkeypatch):
    """etf_regime_enabled=True 도 응답에 그대로 반영 (표시 전용, 매수 가드 미연계)."""
    from src.engine.market_regime import MarketRegime
    from src.routes.system_integrations import _build_buy_block_status

    _patch_state_deps(monkeypatch, mode="SOFT", regime=MarketRegime.empty())
    _patch_etf(monkeypatch, signal=_etf_signal(), enabled=True)

    status = await _build_buy_block_status()

    assert status.etf_enabled is True


@pytest.mark.asyncio
async def test_buy_block_status_existing_fields_unchanged(monkeypatch):
    """E-1 배제 0 회귀 — mode/blocked/soft_multiplier/data_available 기존 동일."""
    from src.engine.market_regime import MarketRegime
    from src.routes.system_integrations import _build_buy_block_status

    _patch_state_deps(monkeypatch, mode="SOFT", regime=MarketRegime.empty())
    _patch_etf(monkeypatch, signal=_etf_signal(), enabled=False)

    status = await _build_buy_block_status()

    # empty regime + SOFT 는 fail-open (매매 행위 diff 0)
    assert status.mode == "SOFT"
    assert status.blocked is False
    assert status.soft_multiplier == 1.0
    assert status.data_available is False
