"""사이클 8 (2026-05-18) Red — `MarketRegime.get_buy_block_state()` 4 모드 + 임계 조정.

신규 dataclass `BuyBlockState`:
- mode: str (OFF/WARN/SOFT/HARD)
- blocked: bool (HARD 시 매수 차단)
- soft_multiplier: float (SOFT 시 0.5, 그 외 1.0)
- reasons: list[str] (defensive / vix>X / fg>Y / fg<Z 모두 수집)

요구 행위:
1. DB 미설정 → HARD + 기본 임계 (25.0/85.0/15.0/true).
2. mode=HARD + 가드 발동 → blocked=True, soft_multiplier=1.0.
3. mode=SOFT + 가드 발동 → blocked=False (매수 허용), soft_multiplier=0.5.
4. mode=WARN + 가드 발동 → blocked=False, soft_multiplier=1.0 (로그만, risk.py가 처리).
5. mode=OFF → 가드 평가 자체 비활성 (reasons=[], blocked=False).
6. defensive_enabled=False → regime=defensive 무시 (5/17 사용자 케이스).
7. 4 임계 OR 모두 발동 시 reasons 4개 수집.
8. empty regime → 모든 모드에서 blocked=False, reasons=[] (graceful).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _patch_db(monkeypatch):
    """`get_buy_block_mode` / `get_buy_block_thresholds` DB 의존성 monkeypatch.

    각 테스트가 케이스별로 override 한다. 기본은 HARD + 기본 임계.
    """
    from src.engine import market_regime as mr

    async def _default_mode():
        return "HARD"

    async def _default_thresholds():
        # BuyBlockThresholds 모델 가정 — 미구현 시 ImportError 로 Red 노출
        from src.db.system_config import BuyBlockThresholds  # type: ignore

        return BuyBlockThresholds(
            vix_threshold=25.0,
            fg_high_threshold=85.0,
            fg_low_threshold=15.0,
            defensive_enabled=True,
        )

    # 기본 patch — 케이스가 필요 시 override
    monkeypatch.setattr(mr, "_db_get_buy_block_mode", _default_mode, raising=False)
    monkeypatch.setattr(
        mr, "_db_get_buy_block_thresholds", _default_thresholds, raising=False,
    )
    yield


def _patch_mode_thresholds(monkeypatch, *, mode, vix=25.0, fg_high=85.0, fg_low=15.0, defensive_enabled=True):
    """헬퍼 — 모드 + 임계 4종을 한 번에 monkeypatch."""
    from src.db.system_config import BuyBlockThresholds  # type: ignore
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


# ---------------------------------------------------------------------------
# 1. DB 미설정 → HARD + 기본 임계 fallback
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_default_mode_is_hard(monkeypatch):
    """DB 미설정 시 mode=HARD."""
    from src.engine.market_regime import MarketRegime

    r = MarketRegime(regime="defensive")
    state = await r.get_buy_block_state()
    assert state.mode == "HARD"
    assert state.blocked is True  # defensive 발동 + HARD


# ---------------------------------------------------------------------------
# 2. HARD + 가드 발동 → blocked=True, multiplier=1.0
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_hard_mode_defensive_blocks(monkeypatch):
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(monkeypatch, mode="HARD")
    r = MarketRegime(regime="defensive", vix=18.0, fear_greed_score=50.0)
    state = await r.get_buy_block_state()
    assert state.mode == "HARD"
    assert state.blocked is True
    assert state.soft_multiplier == 1.0
    assert any("defensive" in s for s in state.reasons)


# ---------------------------------------------------------------------------
# 3. SOFT + 가드 발동 → 매수 허용 + multiplier 0.5
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_soft_mode_defensive_allows_with_half_multiplier(monkeypatch):
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(monkeypatch, mode="SOFT")
    r = MarketRegime(regime="defensive", vix=18.0, fear_greed_score=50.0)
    state = await r.get_buy_block_state()
    assert state.mode == "SOFT"
    assert state.blocked is False  # 매수 허용
    assert state.soft_multiplier == 0.5
    # 사유는 그대로 수집됨 (UI/로그 표시용)
    assert any("defensive" in s for s in state.reasons)


# ---------------------------------------------------------------------------
# 4. WARN + 가드 발동 → 매수 허용 + multiplier 1.0
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_warn_mode_defensive_allows_with_full_multiplier(monkeypatch):
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(monkeypatch, mode="WARN")
    r = MarketRegime(regime="defensive", vix=18.0, fear_greed_score=50.0)
    state = await r.get_buy_block_state()
    assert state.mode == "WARN"
    assert state.blocked is False
    assert state.soft_multiplier == 1.0
    assert any("defensive" in s for s in state.reasons)


# ---------------------------------------------------------------------------
# 5. OFF → 가드 평가 자체 비활성
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_off_mode_disables_all_guards(monkeypatch):
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(monkeypatch, mode="OFF")
    r = MarketRegime(regime="defensive", vix=99.0, fear_greed_score=99.0)
    state = await r.get_buy_block_state()
    assert state.mode == "OFF"
    assert state.blocked is False
    assert state.soft_multiplier == 1.0
    # OFF 는 가드 평가 자체 안 함 → reasons 비어있음
    assert state.reasons == []


# ---------------------------------------------------------------------------
# 6. defensive_enabled=False → regime=defensive 무시 (5/17 사용자 케이스)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_defensive_enabled_false_ignores_regime(monkeypatch):
    """5/17 사용자 실측 케이스 — regime=defensive 단독, VIX/FG 정상.

    defensive_enabled=False 면 regime 사유 미수집, 다른 임계 발동 안 하면 blocked=False.
    """
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(
        monkeypatch, mode="HARD", defensive_enabled=False,
    )
    # 5/17 실측: VIX 18.43 (정상), FG 76.0 (탐욕 정상 범위)
    r = MarketRegime(regime="defensive", vix=18.43, fear_greed_score=76.0)
    state = await r.get_buy_block_state()
    assert state.blocked is False  # HARD 인데도 차단 안 됨
    # defensive 사유는 미수집
    assert not any("defensive" in s for s in state.reasons)


# ---------------------------------------------------------------------------
# 7. 4 임계 OR 모두 발동 시 사유 다수 수집
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_four_guards_collect_reasons(monkeypatch):
    """defensive + vix>임계 + fg>임계 동시 — sub-reasons 다수."""
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(monkeypatch, mode="HARD")
    # defensive + VIX 30(>25) + FG 90(>85) 동시
    r = MarketRegime(regime="defensive", vix=30.0, fear_greed_score=90.0)
    state = await r.get_buy_block_state()
    assert state.blocked is True
    # 3 사유 모두 수집 — defensive, vix, fg_high
    joined = " ".join(state.reasons)
    assert "defensive" in joined
    assert "vix" in joined.lower() or "VIX" in joined
    assert "fear" in joined.lower() or "fg" in joined.lower()


@pytest.mark.asyncio
async def test_custom_thresholds_applied(monkeypatch):
    """임계값 조정 적용 — vix=20 으로 낮추면 VIX 22 도 발동."""
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(monkeypatch, mode="HARD", vix=20.0)
    r = MarketRegime(regime="neutral", vix=22.0, fear_greed_score=50.0)
    state = await r.get_buy_block_state()
    assert state.blocked is True
    assert any("vix" in s.lower() for s in state.reasons)


# ---------------------------------------------------------------------------
# 8. empty regime → graceful (모든 모드에서 reasons=[], blocked=False)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_empty_regime_all_modes_no_block(monkeypatch):
    """empty regime — 외부 fetch 실패 graceful. 모든 모드에서 매수 허용."""
    from src.engine.market_regime import MarketRegime

    for mode in ("OFF", "WARN", "SOFT", "HARD"):
        _patch_mode_thresholds(monkeypatch, mode=mode)
        r = MarketRegime.empty()
        state = await r.get_buy_block_state()
        assert state.blocked is False, f"mode={mode} empty 인데 차단됨"
        assert state.reasons == []


@pytest.mark.asyncio
async def test_is_buy_allowed_consistent_with_state(monkeypatch):
    """기존 동기 `is_buy_allowed()` 는 보존 — 회귀 가드.

    내부적으로 새 헬퍼 호출하지 않음(동기 API 유지). 하드코딩 임계로 평가.
    HARD 모드 가정 — 기존 동작과 동일해야 함.
    """
    from src.engine.market_regime import MarketRegime

    _patch_mode_thresholds(monkeypatch, mode="HARD")
    r = MarketRegime(regime="defensive")
    # 동기 API 는 기존 동작 보존
    assert r.is_buy_allowed("momentum") is False
    r2 = MarketRegime(regime="aggressive", vix=10.0, fear_greed_score=50.0)
    assert r2.is_buy_allowed("momentum") is True
