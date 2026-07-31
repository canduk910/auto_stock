"""사이클 D Red — 레짐 가드 silent inert 가시화 (관찰성, 매매 행위 무변경).

배경 (2026-07-31 진단): dkstock.cloud Let's Encrypt 인증서 07-27 만료 →
`refresh_from_dkstock()` 가 `MarketRegime.empty()` 반환 → 07-27~31 4일간 매수
가드(mode=SOFT) 무력화됐으나 아무 경보 없이 대시보드는 "정상+평온"으로 표시.

근본 결함: `get_buy_block_state()` 가 두 상태를 동일 결과로 반환:
- (정상) 데이터 있음 + 임계 미발동 → blocked=False, reasons=[]
- (위험) 데이터 없음(empty regime)   → blocked=False, reasons=[]
운영자 구분 불가 = "false sense of protection".

시정 방침: **관찰성만 추가. 매매 행위(blocked/soft_multiplier) byte 동일 = fail-open 보존.**

행위 (D-1 ~ D-4):
- D-1 `MarketRegime.has_regime_data` 프로퍼티 신규 — 실제 매크로 데이터 보유 시 True,
      `empty()` 폴백 시 False. 판정 = regime/vix/fear_greed_score 중 1개라도 not None
      또는 bool(raw).
- D-2 `BuyBlockState` 에 `data_available: bool = True` 필드 추가 (default True — 기존 회귀 0).
- D-3 `get_buy_block_state()` 가 반환 state 의 `data_available = self.has_regime_data` 세팅.
      blocked/soft_multiplier/reasons 로직 완전 무변경.
- D-4 boot 매크로 경로: empty regime AND buy_block_mode != OFF →
      `[regime_guard_inert]` WARNING 발화. OFF 이거나 데이터 유입 시 미발화.
"""
from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 공통 DB 헬퍼 monkeypatch (기존 test_market_regime_buy_block_state 패턴 답습)
# ---------------------------------------------------------------------------
def _patch_mode_thresholds(
    monkeypatch, *, mode, vix=25.0, fg_high=85.0, fg_low=15.0, defensive_enabled=True
):
    """모드 + 임계 4종을 한 번에 monkeypatch (market_regime 내부 DB 위임 헬퍼)."""
    from src.db.system_config import BuyBlockThresholds
    from src.engine import market_regime as mr

    async def _m():
        return mode

    async def _t():
        return BuyBlockThresholds(
            vix_threshold=vix,
            fg_high_threshold=fg_high,
            fg_low_threshold=fg_low,
            defensive_enabled=defensive_enabled,
        )

    monkeypatch.setattr(mr, "_db_get_buy_block_mode", _m, raising=False)
    monkeypatch.setattr(mr, "_db_get_buy_block_thresholds", _t, raising=False)


def _normal_macro() -> dict:
    """dkstock.cloud `/api/macro/macro-cycle` 정상 응답 형태 (from_macro_cycle 입력)."""
    return {
        "regime": {
            "regime": "neutral",
            "regime_desc": "중립",
            "vix": 18.0,
            "fear_greed_score": 55.0,
            "params": {"cash_min": 50, "pbr_max": 1.2},
        },
        "cycle": {"phase": "expansion"},
    }


# ===========================================================================
# D-1 — MarketRegime.has_regime_data 프로퍼티
# ===========================================================================
def test_has_regime_data_when_empty_then_false():
    """empty() 폴백 = 모든 필드 None + raw={} → 데이터 미보유."""
    from src.engine.market_regime import MarketRegime

    assert MarketRegime.empty().has_regime_data is False


def test_has_regime_data_when_from_macro_cycle_then_true():
    """정상 매크로 응답 파싱 결과 = 데이터 보유."""
    from src.engine.market_regime import MarketRegime

    regime = MarketRegime.from_macro_cycle(_normal_macro())
    assert regime.has_regime_data is True


def test_has_regime_data_when_only_vix_present_then_true():
    """부분 응답 — vix 단독이라도 데이터 보유 (regime/vix/fg 중 1개 not None)."""
    from src.engine.market_regime import MarketRegime

    assert MarketRegime(vix=20.0).has_regime_data is True


def test_has_regime_data_when_only_raw_present_then_true():
    """모든 정량 필드 None 이라도 raw 가 비어있지 않으면 데이터 보유 (bool(raw) 절)."""
    from src.engine.market_regime import MarketRegime

    assert MarketRegime(raw={"regime": {"regime": "neutral"}}).has_regime_data is True


def test_has_regime_data_when_all_none_and_empty_raw_then_false():
    """전부 None + raw={} → 데이터 미보유 (persist_snapshot 의 regime is None 판정과 정합)."""
    from src.engine.market_regime import MarketRegime

    assert MarketRegime().has_regime_data is False


# ===========================================================================
# D-2 — BuyBlockState.data_available 필드 (default True, 기존 회귀 0)
# ===========================================================================
def test_buy_block_state_data_available_defaults_true():
    """기존 3-인자 생성 = data_available 자동 True (기존 생성/테스트 회귀 0)."""
    from src.engine.market_regime import BuyBlockState

    state = BuyBlockState(mode="SOFT", blocked=False, soft_multiplier=1.0)
    assert hasattr(state, "data_available"), "BuyBlockState.data_available 필드 부재"
    assert state.data_available is True


def test_buy_block_state_data_available_explicit_false():
    """명시 False 설정 가능 (get_buy_block_state 가 empty regime 시 세팅)."""
    from src.engine.market_regime import BuyBlockState

    state = BuyBlockState(
        mode="SOFT", blocked=False, soft_multiplier=1.0, data_available=False
    )
    assert state.data_available is False


# ===========================================================================
# D-3 — get_buy_block_state() 가 data_available = has_regime_data 세팅
#       (blocked/soft_multiplier/reasons 완전 무변경 = fail-open 보존 회귀 단언 동봉)
# ===========================================================================
@pytest.mark.asyncio
async def test_get_buy_block_state_empty_regime_soft_data_available_false(monkeypatch):
    """empty regime + SOFT → data_available=False.

    **회귀 단언**: blocked/soft_multiplier/reasons 는 기존과 동일 (SOFT empty →
    blocked=False, multiplier=1.0, reasons=[] 불변).
    """
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(monkeypatch, mode="SOFT")
    state = await MarketRegime.empty().get_buy_block_state()

    assert state.data_available is False
    # fail-open 매매 행위 불변 (신규 필드는 관찰성 전용)
    assert state.blocked is False
    assert state.soft_multiplier == 1.0
    assert state.reasons == []


@pytest.mark.asyncio
async def test_get_buy_block_state_data_regime_soft_data_available_true(monkeypatch):
    """데이터 유입 regime + SOFT (임계 미발동) → data_available=True + 매매 행위 불변."""
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(monkeypatch, mode="SOFT")
    regime = MarketRegime(regime="neutral", vix=18.0, fear_greed_score=55.0)
    state = await regime.get_buy_block_state()

    assert state.data_available is True
    # 임계 미발동 → 기존 동작 그대로
    assert state.blocked is False
    assert state.soft_multiplier == 1.0
    assert state.reasons == []


@pytest.mark.asyncio
async def test_get_buy_block_state_empty_regime_hard_fail_open_preserved(monkeypatch):
    """empty regime + HARD → data_available=False 이나 fail-open 보존 (blocked=False).

    데이터 없음 시 HARD 여도 매수 차단 전환 금지 (fail-safe 는 범위 외 인계).
    """
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(monkeypatch, mode="HARD")
    state = await MarketRegime.empty().get_buy_block_state()

    assert state.data_available is False
    assert state.blocked is False  # fail-open 보존 (매매 행위 diff 0)
    assert state.reasons == []


@pytest.mark.asyncio
async def test_get_buy_block_state_data_available_survives_cache(monkeypatch):
    """60s TTL 캐시 상호작용 보존 — 캐시 hit(2번째 호출)에도 data_available 동일."""
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(monkeypatch, mode="SOFT")
    regime = MarketRegime.empty()

    first = await regime.get_buy_block_state()
    second = await regime.get_buy_block_state()  # 캐시 hit

    assert first.data_available is False
    assert second.data_available is False


# ===========================================================================
# D-4 — boot 매크로 경로 [regime_guard_inert] WARNING
#       (scheduler._refresh_market_regime_and_persist 직접 단위 호출)
# ===========================================================================
def _patch_refresh_and_persist(monkeypatch, regime):
    """refresh_from_dkstock → 주어진 regime, persist_snapshot → no-op."""
    from src.engine import market_regime as mr

    async def _fake_refresh():
        return regime

    async def _fake_persist(_regime, _target_date):
        return None

    monkeypatch.setattr(mr, "refresh_from_dkstock", _fake_refresh)
    monkeypatch.setattr(mr, "persist_snapshot", _fake_persist)


def _patch_buy_block_mode(monkeypatch, mode: str):
    """boot 경로가 조회하는 buy_block_mode 를 고정 (src.db.system_config.get_buy_block_mode)."""
    from src.db import system_config as sc

    async def _fake_mode():
        return mode

    monkeypatch.setattr(sc, "get_buy_block_mode", _fake_mode, raising=False)


@pytest.mark.asyncio
async def test_boot_macro_empty_regime_soft_mode_emits_inert_warning(monkeypatch, caplog):
    """empty regime + mode=SOFT(≠OFF) → [regime_guard_inert] WARNING 발화.

    현행 코드는 경보 부재 → RED. dkstock 인증서 만료로 4일간 silent 무력화되던
    운영 결함의 가시화.
    """
    from src.engine.market_regime import MarketRegime
    from src.engine.scheduler import TradingScheduler

    _patch_refresh_and_persist(monkeypatch, MarketRegime.empty())
    _patch_buy_block_mode(monkeypatch, "SOFT")

    caplog.set_level(logging.WARNING, logger="src.engine.scheduler")
    sched = TradingScheduler()
    await sched._refresh_market_regime_and_persist()

    inert = [r.getMessage() for r in caplog.records if "[regime_guard_inert]" in r.getMessage()]
    assert len(inert) == 1, "empty regime + SOFT 인데 [regime_guard_inert] 경보 미발화"
    assert "SOFT" in inert[0]


@pytest.mark.asyncio
async def test_boot_macro_empty_regime_off_mode_no_inert_warning(monkeypatch, caplog):
    """empty regime + mode=OFF → 경보 미발화 (OFF 는 무력 아님 — 가드 자체 비활성)."""
    from src.engine.market_regime import MarketRegime
    from src.engine.scheduler import TradingScheduler

    _patch_refresh_and_persist(monkeypatch, MarketRegime.empty())
    _patch_buy_block_mode(monkeypatch, "OFF")

    caplog.set_level(logging.WARNING, logger="src.engine.scheduler")
    sched = TradingScheduler()
    await sched._refresh_market_regime_and_persist()

    inert = [r.getMessage() for r in caplog.records if "[regime_guard_inert]" in r.getMessage()]
    assert inert == [], "OFF 모드인데 [regime_guard_inert] 경보 발화됨"


@pytest.mark.asyncio
async def test_boot_macro_data_regime_soft_mode_no_inert_warning(monkeypatch, caplog):
    """데이터 유입 regime + mode=SOFT → 경보 미발화 (정상 = 가드 유효)."""
    from src.engine.market_regime import MarketRegime
    from src.engine.scheduler import TradingScheduler

    data_regime = MarketRegime.from_macro_cycle(_normal_macro())
    _patch_refresh_and_persist(monkeypatch, data_regime)
    _patch_buy_block_mode(monkeypatch, "SOFT")

    caplog.set_level(logging.WARNING, logger="src.engine.scheduler")
    sched = TradingScheduler()
    await sched._refresh_market_regime_and_persist()

    inert = [r.getMessage() for r in caplog.records if "[regime_guard_inert]" in r.getMessage()]
    assert inert == [], "데이터 유입 regime 인데 [regime_guard_inert] 경보 발화됨"
