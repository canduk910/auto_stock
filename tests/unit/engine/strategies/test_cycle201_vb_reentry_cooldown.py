"""사이클 201 Red — VB(volatility_breakout) 재진입 쿨다운 2영업일 신설.

작업 지시서 = `_workspace/red/cycle201_vb_reentry_cooldown.md` +
재진단 정본 `_workspace/domain_consult/cycle201_vb_weight_derisk.md` §재진단.

**Red 단계 — 실패 테스트만. production 미변경.** Green = backend-dev.

결함: VB 는 크로스데이 재진입 무방비. `is_sold_today`(당일 재매수만 차단)뿐 —
BFB(3영업일)/VCP(7영업일) 가 사이클 185/191 에서 받은 크로스데이 쿨다운이 VB 미배선.
LS ELECTRIC 4일 재진입 -26,000 (총손실 45%) = 막을 장치 부재.

Green 계약 (BFB 사이클 191 패턴 100% 미러링, 쿨다운=2영업일):
- `DEFAULT_PARAMS["reentry_cooldown_days"] = 2` (BFB 3 / VCP 7 과 구분).
- `__init__` 에 `self._cooldown_until: dict[str, date] = {}`.
- `register_cooldown_after_exit(ticker)` = 즉시 근사 `today + timedelta(days=days + 2)`.
- `async def _refine_cooldown_business_days(ticker)` = `add_business_days(today, days)` 정정 graceful.
- `on_position_closed(ticker)` = register + create_task(refine, RuntimeError graceful).
- 매수 게이트 = `check_buy_signal` `is_sold_today` 가드 직후 `cd_until >= today: return NONE`.

이 파일 가드 (1)(2)(3)(4)(5)(8):
- (1) 쿨다운 활성 → 매수 차단 = Red (게이트 부재).
- (2) 쿨다운 만료 → 매수 허용 = 불변식 (게이트가 정상 종목 미차단).
- (3) 즉시 근사 등록 (today + 2+2=4) = Red (메서드 부재).
- (4) 영업일 정정 성공/실패 graceful = Red (메서드 부재).
- (5) on_position_closed 배선 = Red (override 부재).
- (8) DEFAULT_PARAMS 값 == 2 = Red (키 부재).

(6 NO-DAILY-RESET / 7 다른 전략 값 불변) = `tests/unit/ast/test_cycle201_vb_cooldown_ast.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Signal, StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 헬퍼 — 기존 test_volatility_breakout.py 픽스처 패턴 답습
# ---------------------------------------------------------------------------
def _make_vb(monkeypatch) -> VolatilityBreakoutStrategy:
    """scanner 격리 + session_tracker active 초기화한 VB 인스턴스."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {"005930": "삼성전자"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    return VolatilityBreakoutStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="변동성 돌파", weight=0.3)
    )


def _activate(board: str) -> None:
    session_tracker._active = frozenset({MarketBoard(board)})


def _seed_target(strategy, ticker, *, prev_range=1000, k=0.5) -> None:
    """prepare() 결과 모사 — _targets dict 직접 시드 (base = prev_range × k)."""
    target_offset_base = int(prev_range * k)
    strategy._targets[ticker] = {
        "k": k,
        "prev_range": prev_range,
        "target_offset_base": target_offset_base,
        "target_offset": target_offset_base,
        "target_price": 0,
        "open_price": 0,
        "boards": {},
    }
    strategy._open_confirmed[ticker] = {}


# ===========================================================================
# (1) [핵심, Red] 쿨다운 활성 시 매수 차단 — 돌파 조건 완비여도 NONE
# ===========================================================================
@freeze_time("2026-07-10 10:00:00")
def test_1_active_cooldown_blocks_buy(monkeypatch) -> None:
    """(1) HIGH Red: `_cooldown_until[ticker] = today+2` 활성 → 돌파 틱도 NONE.

    현재 FAIL = 게이트 부재 → 돌파 순간 BUY 발화.
    base = 1000×0.5 = 500 / open 80000 / target 80500.
    tick1=80200(기록) → tick2=80500(돌파). 쿨다운 없으면 BUY, 있으면 NONE.
    """
    vb = _make_vb(monkeypatch)
    _seed_target(vb, "005930", prev_range=1000, k=0.5)  # base 500
    vb.on_open_price_confirmed("005930", open_price=80000, board="main")  # target 80500
    _activate("main")

    today = datetime.now(KST).date()
    # 쿨다운 활성 (오늘 이후 만료 — 재진입 금지). Green 전엔 dict 부재라 방어적으로 주입:
    # 현행(게이트 부재) = 이 dict 무시 → 돌파 BUY → assert NONE FAIL (올바른 Red).
    # Green(게이트 신설) = _cooldown_until 소비 → NONE → PASS.
    if not hasattr(vb, "_cooldown_until"):
        vb._cooldown_until = {}
    vb._cooldown_until["005930"] = today + timedelta(days=2)

    # tick1 = 기록만 (prev 0), tick2 = 돌파 순간
    assert vb.check_buy_signal("005930", 80200, 80000) == Signal.NONE  # 첫 틱 기록
    sig = vb.check_buy_signal("005930", 80500, 80000)  # 돌파 (prev 80200 < 80500 == target)
    assert sig == Signal.NONE, (
        "쿨다운 활성 종목 재돌파 → check_buy_signal NONE (매수 게이트 최초 실효). "
        "현재 코드(게이트 부재)에선 BUY = Red"
    )


# ===========================================================================
# (2) [불변식 PASS] 쿨다운 만료 후 재매수 허용 — 게이트 대조군
# ===========================================================================
@freeze_time("2026-07-10 10:00:00")
def test_2_normal_breakout_allows_buy(monkeypatch) -> None:
    """(2) 불변식 PASS: 쿨다운 무관 정상 돌파 → BUY (게이트가 정상 종목 미차단, 회귀 0).

    현재 코드(게이트 부재)에서 BUY. Green 후에도 쿨다운 미등록 종목은 게이트 통과 → BUY 유지.
    `_cooldown_until` 직접 시드 안 함 (Green 산물이라 현행 AttributeError 회피) — 게이트가
    쿨다운 *없는* 종목을 막지 않음을 검증. 게이트 over-block 회귀 영구 차단.
    """
    vb = _make_vb(monkeypatch)
    _seed_target(vb, "005930", prev_range=1000, k=0.5)
    vb.on_open_price_confirmed("005930", open_price=80000, board="main")
    _activate("main")

    assert vb.check_buy_signal("005930", 80200, 80000) == Signal.NONE  # 첫 틱 기록
    sig = vb.check_buy_signal("005930", 80500, 80000)  # 돌파
    assert sig == Signal.BUY, "쿨다운 없는 정상 종목 돌파 → BUY (게이트 불변식, over-block 0)"


# ===========================================================================
# (3) [Red] register_cooldown_after_exit → 즉시 근사 (today + days+2)
# ===========================================================================
@freeze_time("2026-07-10 10:00:00")
def test_3_register_cooldown_after_exit_approx(monkeypatch) -> None:
    """(3) Red: `register_cooldown_after_exit` → `_cooldown_until[t] == today + (2+2)`.

    days=2 근사 = today + timedelta(days=4). 재매수 공백 0 (즉시 근사).
    현재 FAIL = 메서드 부재 (AttributeError).
    """
    vb = _make_vb(monkeypatch)
    today = datetime.now(KST).date()

    vb.register_cooldown_after_exit("005930")

    assert "005930" in vb._cooldown_until, "register 후 _cooldown_until 세팅 의무"
    assert vb._cooldown_until["005930"] == today + timedelta(days=2 + 2), (
        "즉시 근사 = today + (days=2) + 2 달력일 (재매수 공백 0)"
    )


# ===========================================================================
# (4) [Red] _refine_cooldown_business_days — 성공/실패 graceful
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-07-10 10:00:00")
async def test_4a_refine_success_replaces_with_business_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(4a) Red: refine 성공 → `_cooldown_until` 정확 영업일 date 로 교체.

    현재 FAIL = `_refine_cooldown_business_days` 메서드 부재 (AttributeError).
    add_business_days 는 mock (KIS 호출 회피).
    """
    vb = _make_vb(monkeypatch)
    today = datetime.now(KST).date()
    vb.register_cooldown_after_exit("005930")  # 우선 근사 등록

    accurate = today + timedelta(days=2)  # 임의 영업일 정정 결과
    fake_add = AsyncMock(return_value=accurate)
    import src.engine.strategies.volatility_breakout as _vb_mod

    monkeypatch.setattr(_vb_mod, "add_business_days", fake_add, raising=False)

    await vb._refine_cooldown_business_days("005930")

    fake_add.assert_awaited_once()
    assert vb._cooldown_until["005930"] == accurate, "refine 성공 → 정확 영업일 date 로 교체 의무"


@pytest.mark.asyncio
@freeze_time("2026-07-10 10:00:00")
async def test_4b_refine_failure_keeps_approx_graceful(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(4b) Red: refine 예외 → 근사값 유지 graceful (예외 전파 0).

    현재 FAIL = 메서드 부재 (AttributeError).
    """
    vb = _make_vb(monkeypatch)
    today = datetime.now(KST).date()
    vb.register_cooldown_after_exit("005930")
    approx = vb._cooldown_until["005930"]
    assert approx == today + timedelta(days=2 + 2), "근사값 = today + days + 2 선결"

    fake_add = AsyncMock(side_effect=RuntimeError("boom"))
    import src.engine.strategies.volatility_breakout as _vb_mod

    monkeypatch.setattr(_vb_mod, "add_business_days", fake_add, raising=False)

    # 예외 전파 없이 완료 (try/except graceful)
    await vb._refine_cooldown_business_days("005930")

    assert vb._cooldown_until["005930"] == approx, (
        "refine 예외 → 근사값 유지 (graceful, 재매수 공백 0 보존)"
    )


# ===========================================================================
# (5) [Red] on_position_closed 배선 — register 등록 + refine create_task graceful
# ===========================================================================
@freeze_time("2026-07-10 10:00:00")
def test_5_on_position_closed_registers_cooldown(monkeypatch) -> None:
    """(5) HIGH Red: `on_position_closed(ticker)` → `_cooldown_until` 등록 (근사값).

    현재 FAIL = VB on_position_closed override 부재 → base no-op → dict 비어있음.
    sync 컨텍스트 = 이벤트 루프 없음 → refine create_task RuntimeError graceful → 근사값 유지.
    """
    vb = _make_vb(monkeypatch)
    today = datetime.now(KST).date()

    # 예외 전파 없이 완료 (sync = 이벤트 루프 없음)
    vb.on_position_closed("005930")

    assert "005930" in vb._cooldown_until, (
        "VB on_position_closed override 신설 부재 (base no-op 상속) — 고아 배선"
    )
    assert vb._cooldown_until["005930"] == today + timedelta(days=2 + 2), (
        "근사값 = today + days + 2 (create_task 실패 무관 graceful)"
    )


# ===========================================================================
# (5b) [Red] LS ELECTRIC end-to-end 시나리오 — 청산 → 재돌파 → 쿨다운 차단
# ===========================================================================
@freeze_time("2026-07-10 10:00:00")
def test_5b_ls_electric_reentry_blocked_via_hook(monkeypatch) -> None:
    """(5b) HIGH Red: 재진단 정본 LS ELECTRIC 재현 — 청산(on_position_closed) → 재돌파 → NONE.

    on_position_closed 로 쿨다운 등록 → 며칠 뒤(쿨다운 내) 재돌파 틱도 check_buy = NONE.
    현재 FAIL = on_position_closed register 부재 → 미등록 → 돌파 틱 BUY.
    """
    vb = _make_vb(monkeypatch)
    _seed_target(vb, "005930", prev_range=1000, k=0.5)
    vb.on_open_price_confirmed("005930", open_price=80000, board="main")  # target 80500
    _activate("main")

    # 청산 → on_position_closed 훅 (매도 set 은 미설정 = 게이트 격리, 크로스데이 시뮬)
    vb.on_position_closed("005930")

    assert vb.check_buy_signal("005930", 80200, 80000) == Signal.NONE  # 첫 틱
    sig = vb.check_buy_signal("005930", 80500, 80000)  # 재돌파
    assert sig == Signal.NONE, (
        "청산 종목 쿨다운 내 재돌파 → NONE (LS ELECTRIC 4일 재진입 -26,000 직격 차단)"
    )


# ===========================================================================
# (8) [Red] DEFAULT_PARAMS 값 == 2 (BFB 3 / VCP 7 과 구분)
# ===========================================================================
def test_8_default_params_reentry_cooldown_is_2() -> None:
    """(8) Red: VB `DEFAULT_PARAMS["reentry_cooldown_days"] == 2`.

    현재 FAIL = 키 부재 (KeyError). VB 당일청산 특성 → 짧은 쿨다운 (BFB 3 / VCP 7 이 아님).
    """
    p = VolatilityBreakoutStrategy.DEFAULT_PARAMS
    assert "reentry_cooldown_days" in p, "VB DEFAULT_PARAMS 에 reentry_cooldown_days 키 신설 의무"
    assert p["reentry_cooldown_days"] == 2, (
        "VB 재진입 쿨다운 = 2영업일 (당일청산 특성, BFB 3 / VCP 7 과 구분)"
    )
