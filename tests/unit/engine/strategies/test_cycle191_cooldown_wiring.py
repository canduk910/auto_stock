"""사이클 191 Red — BFB/VCP 재진입 쿨다운 고아 배선 (영업일 2단계 등록).

작업 지시서 `_workspace/red/cycle191_reentry_cooldown_wiring.md` §2 +
자문 `_workspace/domain_consult/cycle191_reentry_cooldown_wiring.md`.

**Red 단계 — 실패 테스트만. production 미변경.** Green = backend-dev.

결함: `register_cooldown_after_exit` (BFB days=3 / VCP days=7) production 호출처 0건 (고아).
매수 게이트(`check_buy_signal` `cd_until >= today: return NONE`) 는 살아있으나
등록이 없어 재진입 쿨다운 무력.

Green 계약 (2단계 등록):
- `register_cooldown_after_exit` = 즉시 근사 `today + timedelta(days=days + 2)` (재매수 공백 0).
- `async def _refine_cooldown_business_days(ticker)` = `add_business_days(today, days)` 정정.
- `on_position_closed(ticker)`:
  - BFB: 기존 override(`_partial_exit.pop` 보존) + register + create_task(refine, RuntimeError graceful).
  - VCP: override 신설 (register + create_task).

가드 → Red/Green:
- C-1/2/3/4/5/6/8 = Red. C-7(만료 후 매수) = 불변식 PASS.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import Signal, StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _make_bfb() -> BullFlagBreakoutStrategy:
    return BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="bfb", params={"exchange": "KRX"})
    )


def _make_vcp() -> VcpBreakoutStrategy:
    return VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="vcp", params={"exchange": "KRX"})
    )


# ===========================================================================
# C-1 / C-2 / C-3 — on_position_closed → 즉시 근사 쿨다운 등록 (sync, no-loop graceful)
# ===========================================================================
@freeze_time("2026-07-02 10:00:00")
def test_C1_bfb_on_position_closed_sets_approx_cooldown() -> None:
    """C-1 (HIGH, Red): BFB on_position_closed → `_cooldown_until` 즉시 세팅 (today + days+2).

    현재 FAIL = on_position_closed 가 register_cooldown_after_exit 미호출 → dict 비어있음.
    (sync 컨텍스트 = 이벤트 루프 없음 → refine create_task RuntimeError graceful → 근사값 유지)
    """
    bfb = _make_bfb()
    today = datetime.now(KST).date()

    bfb.on_position_closed("005930")

    assert "005930" in bfb._cooldown_until, (
        "BFB on_position_closed → register_cooldown_after_exit 배선 부재 (고아)"
    )
    assert bfb._cooldown_until["005930"] == today + timedelta(days=3 + 2), (
        "즉시 근사 = today + (days=3) + 2 달력일 (재매수 공백 0)"
    )


@freeze_time("2026-07-02 10:00:00")
def test_C2_vcp_on_position_closed_sets_approx_cooldown() -> None:
    """C-2 (HIGH, Red): VCP on_position_closed override 신설 → 근사 쿨다운 (today + 7 + 2).

    현재 FAIL = VCP on_position_closed override 부재 → base no-op → dict 비어있음.
    """
    vcp = _make_vcp()
    today = datetime.now(KST).date()

    vcp.on_position_closed("005930")

    assert "005930" in vcp._cooldown_until, (
        "VCP on_position_closed override 신설 부재 (base no-op 상속)"
    )
    assert vcp._cooldown_until["005930"] == today + timedelta(days=7 + 2), (
        "VCP 즉시 근사 = today + (days=7) + 2 달력일"
    )


@freeze_time("2026-07-02 10:00:00")
def test_C3_bfb_partial_exit_pop_preserved_with_cooldown() -> None:
    """C-3 (HIGH, Red): BFB on_position_closed 가 기존 `_partial_exit.pop` 보존 (사이클 185) + 쿨다운 등록.

    현재 FAIL = pop 은 되나 쿨다운 미등록 → 두 조건 동시 만족 실패.
    """
    bfb = _make_bfb()
    bfb._partial_exit["005930"] = True

    bfb.on_position_closed("005930")

    assert "005930" not in bfb._partial_exit, (
        "사이클 185 계약 — _partial_exit.pop 보존 의무"
    )
    assert "005930" in bfb._cooldown_until, (
        "사이클 191 배선 — pop 과 register 동시 (기존 계약 보존)"
    )


# ===========================================================================
# C-4 / C-5 — refine (영업일 정정) 성공/실패 graceful
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-07-02 10:00:00")
async def test_C4_refine_success_replaces_with_business_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C-4 (Red): refine 성공 → `_cooldown_until` 정확 영업일 date 로 교체.

    현재 FAIL = `_refine_cooldown_business_days` 메서드 부재 (AttributeError).
    """
    bfb = _make_bfb()
    today = datetime.now(KST).date()
    # 우선 근사 등록 (register 존재)
    bfb.register_cooldown_after_exit("005930")

    # add_business_days 정확값 = today + 4일 (임의 영업일 정정 결과)
    accurate = today + timedelta(days=4)
    fake_add = AsyncMock(return_value=accurate)
    import src.engine.strategies.bull_flag_breakout as _bfb_mod

    monkeypatch.setattr(_bfb_mod, "add_business_days", fake_add, raising=False)

    await bfb._refine_cooldown_business_days("005930")

    fake_add.assert_awaited_once()
    assert bfb._cooldown_until["005930"] == accurate, (
        "refine 성공 → 정확 영업일 date 로 교체 의무"
    )


@pytest.mark.asyncio
@freeze_time("2026-07-02 10:00:00")
async def test_C5_refine_failure_keeps_approx_graceful(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C-5 (Red): refine 예외 → 근사값 유지 graceful (예외 전파 0).

    현재 FAIL = `_refine_cooldown_business_days` 메서드 부재 (AttributeError).
    """
    bfb = _make_bfb()
    today = datetime.now(KST).date()
    bfb.register_cooldown_after_exit("005930")
    approx = bfb._cooldown_until["005930"]
    assert approx == today + timedelta(days=3 + 2), "근사값 = today + days + 2 선결"

    fake_add = AsyncMock(side_effect=RuntimeError("boom"))
    import src.engine.strategies.bull_flag_breakout as _bfb_mod

    monkeypatch.setattr(_bfb_mod, "add_business_days", fake_add, raising=False)

    # 예외 전파 없이 완료 (try/except graceful)
    await bfb._refine_cooldown_business_days("005930")

    assert bfb._cooldown_until["005930"] == approx, (
        "refine 예외 → 근사값 유지 (graceful, 재매수 공백 0 보존)"
    )


# ===========================================================================
# C-6 — 등록 후 check_buy_signal 게이트 실효 (end-to-end, on_position_closed 경유)
# ===========================================================================
@freeze_time("2026-07-02 10:00:00")
def test_C6_cooldown_via_hook_blocks_buy_signal() -> None:
    """C-6 (HIGH, Red): on_position_closed 로 쿨다운 등록 → 재돌파 틱도 check_buy = NONE.

    현재 FAIL = on_position_closed register 부재 → 쿨다운 미등록 → 돌파 틱 BUY 발화.
    """
    bfb = _make_bfb()
    bfb.config.params["entry_start"] = "09:00"
    bfb.config.params["entry_end"] = "15:00"
    bfb.config.params["breakout_retention_minutes"] = 0
    # 돌파 조건 충족 후보 (쿨다운 없으면 BUY 가능)
    bfb._candidates["005930"] = {
        "flag_high": 12_000,
        "flag_avg_volume": 1_000,
        "pole_high": 12_000,
        "pole_start": 10_000,
        "atr14": 100,
    }
    from src.engine import scanner as _scanner

    _scanner.ticker_prices["005930"] = {"acml_vol": 5_000}  # 거래량 컷 통과

    try:
        # 쿨다운 등록 (신규 배선 = register 경유). 매도 set 은 미설정 (게이트 격리).
        bfb.on_position_closed("005930")

        sig = bfb.check_buy_signal("005930", 12_500, 12_500)  # prev 0 < 12000 <= 12500 돌파
        assert sig == Signal.NONE, (
            "쿨다운 등록 종목 재돌파 → check_buy_signal NONE (게이트 최초 실효)"
        )
    finally:
        _scanner.ticker_prices.pop("005930", None)


# ===========================================================================
# C-7 — 쿨다운 만료 후 매수 정상 (불변식 PASS, 게이트 대조)
# ===========================================================================
@freeze_time("2026-07-02 10:00:00")
def test_C7_expired_cooldown_allows_buy() -> None:
    """C-7 (불변식 PASS): 쿨다운 만료(cd_until < today) → 돌파 틱 BUY 정상 재개.

    게이트 로직 불변 검증 (C-6 대조군).
    """
    bfb = _make_bfb()
    bfb.config.params["entry_start"] = "09:00"
    bfb.config.params["entry_end"] = "15:00"
    bfb.config.params["breakout_retention_minutes"] = 0
    bfb._candidates["005930"] = {
        "flag_high": 12_000,
        "flag_avg_volume": 1_000,
        "pole_high": 12_000,
        "pole_start": 10_000,
        "atr14": 100,
    }
    today = datetime.now(KST).date()
    bfb._cooldown_until["005930"] = today - timedelta(days=1)  # 어제 만료

    # cycle228 (A7) — 거래량은 tick_volume 실측 주입 (구 ticker_prices 손주입 폐기).
    from src.engine import tick_volume

    tick_volume.reset_for_test()
    tick_volume.record_acml_vol("005930", 5_000)  # threshold 1_000 × 2.0 = 2_000 초과
    try:
        sig = bfb.check_buy_signal("005930", 12_500, 12_500)
        assert sig == Signal.BUY, "쿨다운 만료 → 정상 매수 재개 (게이트 불변)"
    finally:
        tick_volume.reset_for_test()


# ===========================================================================
# C-8 — 이벤트 루프 없는 환경 graceful (근사값 세팅됨)
# ===========================================================================
@freeze_time("2026-07-02 10:00:00")
def test_C8_no_event_loop_graceful_keeps_approx() -> None:
    """C-8 (Red): 루프 없는 sync 환경에서 on_position_closed 예외 전파 0 + 근사값 세팅.

    create_task(refine) 는 RuntimeError(no running loop) → try/except 흡수 → 근사값 유지.
    현재 FAIL = register 미배선 → 근사값 미세팅.
    """
    vcp = _make_vcp()
    today = datetime.now(KST).date()

    # 예외 전파 없이 완료 (sync = 이벤트 루프 없음)
    vcp.on_position_closed("005930")

    assert "005930" in vcp._cooldown_until, "루프 없어도 근사값 세팅 (create_task 실패 무관)"
    assert vcp._cooldown_until["005930"] == today + timedelta(days=7 + 2), (
        "근사값 = today + days + 2 (refine 미발화 graceful)"
    )
