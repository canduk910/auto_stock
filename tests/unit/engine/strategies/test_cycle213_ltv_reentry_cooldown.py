"""사이클 213 Red — LTV(long_tail_volatility) 재진입 쿨다운 2영업일 신설.

작업 지시서 = `_workspace/red/cycle213_ltv_reentry_cooldown.md` +
설계 자문 `_workspace/domain_consult/cycle213_ltv_reentry_cooldown.md`.

**Red 단계 — 실패 테스트만. production 미변경.** Green = backend-dev.

결함: 테스(095610) LTV 이틀 whipsaw -20,000 (당일 모드 손절→익일 재매수→손절).
LTV 만 재진입 쿨다운 무방비 — BFB(3)/VCP(7)/VB(2, 사이클 201) 배선됨, LTV 미배선.

LTV 특유: 두 모드가 한 클래스. `on_position_closed` 훅 시점 `_limit_up_reached`
멤버십으로 "당일 모드 손절만" 근사 발동 (상한가 익일보유 종목 = 정상 재진입 면제).

Green 계약 (VB 사이클 201 패턴 복사 + 상한가 게이트 한 겹):
- `DEFAULT_PARAMS["reentry_cooldown_days"] = 2` (BFB 3 / VCP 7 과 구분).
- `__init__` `self._cooldown_until: dict[str, date] = {}`.
- `register_cooldown_after_exit(ticker)` = 즉시 근사 `today + timedelta(days=days + 2)`.
- `async def _refine_cooldown_business_days(ticker)` = `add_business_days(today, days)` graceful.
- `on_position_closed(ticker)` override 수정: `was_limit_up = ticker in _limit_up_reached`
  (discard *전*) → discard(185 보존) → `if not was_limit_up:` register + create_task.
- 매수 게이트 = `check_buy_signal` `is_sold_today` 가드 직후 `cd_until >= today: NONE`.

이 파일 가드 (G-213-1/2/3/4-행위/5) + register/refine 부가:
- G-213-1: DEFAULT_PARAMS 값 == 2 = Red (키 부재).
- G-213-2 (HIGH): 당일 모드 → on_position_closed → 쿨다운 등록 → 재돌파 NONE = Red.
- G-213-3 (HIGH): 상한가 모드 → on_position_closed → 쿨다운 미등록 (면제) = Red.
- G-213-4 (HIGH): DISCARD-ORDER 행위 — 상한가 멤버 청산 시 discard AND 미등록 동시.
- G-213-5: SET-185-PRESERVE — 양쪽 모드 discard 보존.

(G-213-4 AST 시퀀스 / G-213-6 NO-DAILY-RESET) = `tests/unit/ast/test_cycle213_ltv_cooldown_ast.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategy_base import Signal, StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 헬퍼 — 기존 LTV / VB 사이클 201 픽스처 패턴 답습
# ---------------------------------------------------------------------------
def _make_ltv(monkeypatch) -> LongTailVolatilityStrategy:
    """scanner 격리 + session_tracker active 초기화한 LTV 인스턴스.

    ticker_prev_close 는 비움 → check_buy_signal 의 min_prdy_rate 필터 스킵
    (prev_close=0 → 필터 미진입). 순수 돌파 게이트만 검증.
    """
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {"095610": "테스"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    return LongTailVolatilityStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="롱테일 변동성 돌파", weight=0.15)
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
# G-213-1 [Red] DEFAULT_PARAMS reentry_cooldown_days == 2
# ===========================================================================
def test_g213_1_default_params_reentry_cooldown_is_2() -> None:
    """G-213-1 (Red): LTV `DEFAULT_PARAMS["reentry_cooldown_days"] == 2`.

    현재 FAIL = 키 부재 (KeyError). LTV 당일 모드 = VB 동형 → 2영업일
    (BFB 3 / VCP 7 이 아님, VB 2 와 같은 값이나 별도 키).
    """
    p = LongTailVolatilityStrategy.DEFAULT_PARAMS
    assert "reentry_cooldown_days" in p, (
        "LTV DEFAULT_PARAMS 에 reentry_cooldown_days 키 신설 의무"
    )
    assert p["reentry_cooldown_days"] == 2, (
        "LTV 재진입 쿨다운 = 2영업일 (당일 모드 = VB 동형, BFB 3 / VCP 7 과 구분)"
    )


# ===========================================================================
# G-213-2 [핵심 HIGH, Red] 당일 모드 손절 → 쿨다운 등록 → 재돌파 차단 (테스 재현)
# ===========================================================================
@freeze_time("2026-07-14 01:00:00")
def test_g213_2_today_mode_close_registers_cooldown_blocks_rebuy(monkeypatch) -> None:
    """G-213-2 (HIGH Red, whipsaw): 당일 모드 종목 청산 → 쿨다운 등록 → 재돌파 NONE.

    테스(095610) 7/13→7/14 whipsaw 재현. ticker ∉ `_limit_up_reached` (당일 모드).
    on_position_closed → `_cooldown_until` 등록 → 며칠 뒤(쿨다운 내) 재돌파 틱 NONE.

    현재 FAIL = on_position_closed 가 base no-op(사이클 185 discard 만) → 쿨다운 미등록
    → 게이트 부재 → 재돌파 BUY.
    """
    ltv = _make_ltv(monkeypatch)
    _seed_target(ltv, "095610", prev_range=1000, k=0.5)  # base 500
    ltv.on_open_price_confirmed("095610", open_price=80000, board="main", source="rest")  # target 80500
    _activate("main")

    # 당일 모드 = 상한가 미도달 (_limit_up_reached 비멤버)
    assert "095610" not in ltv._limit_up_reached

    # 당일 손절 청산 → on_position_closed 훅 (sync = 이벤트 루프 없음 → refine graceful)
    ltv.on_position_closed("095610")

    assert "095610" in ltv._cooldown_until, (
        "당일 모드 종목 청산 → 재진입 쿨다운 등록 의무 (테스 whipsaw 차단)"
    )

    # 쿨다운 내 재돌파 — tick1 기록(prev 0) → tick2 돌파
    assert ltv.check_buy_signal("095610", 80200, 80000) == Signal.NONE  # 첫 틱 기록
    sig = ltv.check_buy_signal("095610", 80500, 80000)  # 돌파 (prev 80200 < 80500 == target)
    assert sig == Signal.NONE, (
        "당일 모드 청산 종목 쿨다운 내 재돌파 → NONE (테스 7/14 -9,900 재매수 차단)"
    )


# ===========================================================================
# G-213-3 [HIGH, Red] 상한가 모드 종목 청산 → 쿨다운 면제 (정상 재진입 보존)
# ===========================================================================
@freeze_time("2026-07-14 01:00:00")
def test_g213_3_limit_up_mode_close_exempts_cooldown(monkeypatch) -> None:
    """G-213-3 (HIGH Red, 면제): 상한가 모드 종목(멤버) 청산 → `_cooldown_until` 미등록.

    상한가 모드 = 익일 NXT 프리 청산 = 정상 재진입 사이클 (롱테일 = 급등주 여러 번).
    on_position_closed 진입 시점 `_limit_up_reached` 멤버 → 쿨다운 면제.

    현재 FAIL 방식 주의: 현행 on_position_closed 는 base no-op override(discard 만).
    Green 후 게이트가 상한가 멤버를 *면제* 하는지 검증 = 등록 절대 0.
    현행에선 discard 만 하고 register 자체가 없어 미등록 → 이 단언은 현행 PASS 가능.
    → G-213-3 은 "면제 계약" 불변식 (over-register 회귀 영구 차단). Green 후에도
    상한가 멤버는 절대 등록 안 됨을 보장. (Red 성격은 G-213-2/4 가 담당.)
    """
    ltv = _make_ltv(monkeypatch)

    # 상한가 모드 = _limit_up_reached 멤버
    ltv._limit_up_reached.add("095610")

    ltv.on_position_closed("095610")

    # _cooldown_until 은 Green 산물 — 현행 부재 시 getattr 로 방어
    cooldown = getattr(ltv, "_cooldown_until", {})
    assert "095610" not in cooldown, (
        "상한가 모드 종목 청산 → 쿨다운 미등록 (정상 익일 재진입 면제, over-block 0)"
    )


# ===========================================================================
# G-213-4 [HIGH, Red] DISCARD-ORDER 행위 — 상한가 멤버 청산 시 discard AND 미등록 동시
# ===========================================================================
@freeze_time("2026-07-14 01:00:00")
def test_g213_4_discard_order_limit_up_discarded_and_not_registered(monkeypatch) -> None:
    """G-213-4 (HIGH Red, DISCARD-ORDER): 상한가 멤버 청산 → discard 됨 AND 쿨다운 미등록 동시.

    was_limit_up 을 discard *전* 판정해야 상한가 면제가 성립. discard 먼저면
    was_limit_up=False → 쿨다운 등록 = 면제 붕괴 (위험 시나리오 1 재발).

    이 테스트는 순서를 *행위* 로 증명: 상한가 멤버 종목이 (a) discard 되고 (b) 등록 안 됨.
    discard-먼저 구현이었다면 (b) 위반 (등록됨). 현행(base no-op discard 만) = discard O + 미등록 O
    → 현행 PASS 가능이나, Green 의 register 추가가 순서 뒤집으면 즉시 FAIL 되는 회귀 가드.
    AST 시퀀스 가드는 `test_cycle213_ltv_cooldown_ast.py` (정적 이중).
    """
    ltv = _make_ltv(monkeypatch)
    ltv._limit_up_reached.add("095610")

    ltv.on_position_closed("095610")

    assert "095610" not in ltv._limit_up_reached, (
        "상한가 멤버 청산 → _limit_up_reached discard (사이클 185 보존)"
    )
    cooldown = getattr(ltv, "_cooldown_until", {})
    assert "095610" not in cooldown, (
        "discard 전 was_limit_up 판정 → 상한가 멤버는 쿨다운 미등록 (순서 역전 시 등록 = 면제 붕괴)"
    )


# ===========================================================================
# G-213-5 [SET-185-PRESERVE] on_position_closed 후 discard (양쪽 모드)
# ===========================================================================
@freeze_time("2026-07-14 01:00:00")
@pytest.mark.parametrize("is_limit_up", [True, False], ids=["limit_up", "today_mode"])
def test_g213_5_set_185_discard_preserved(monkeypatch, is_limit_up) -> None:
    """G-213-5 (SET-185-PRESERVE): on_position_closed 후 `_limit_up_reached` discard.

    사이클 185 계약 = 전량 청산 시 상한가 flag discard (재매수 누설 차단) — 양쪽 모드 불변.
    당일 모드(비멤버) 도 discard 는 no-op (안전). 상한가 모드(멤버) 는 discard 됨.
    현행 PASS (사이클 185 override 존재) — Green 이 discard 를 유지하는지 영구 가드.
    """
    ltv = _make_ltv(monkeypatch)
    if is_limit_up:
        ltv._limit_up_reached.add("095610")

    ltv.on_position_closed("095610")

    assert "095610" not in ltv._limit_up_reached, (
        "on_position_closed 후 _limit_up_reached 에서 ticker discard (사이클 185 계약 불변)"
    )


# ===========================================================================
# [Red] register_cooldown_after_exit — 즉시 근사 (today + days+2)  (VB 201 답습)
# ===========================================================================
@freeze_time("2026-07-14 01:00:00")
def test_register_cooldown_after_exit_approx(monkeypatch) -> None:
    """(Red): `register_cooldown_after_exit` → `_cooldown_until[t] == today + (2+2)`.

    days=2 근사 = today + timedelta(days=4). 재매수 공백 0 (즉시 근사).
    현재 FAIL = 메서드 부재 (AttributeError).
    """
    ltv = _make_ltv(monkeypatch)
    today = datetime.now(KST).date()

    ltv.register_cooldown_after_exit("095610")

    assert "095610" in ltv._cooldown_until, "register 후 _cooldown_until 세팅 의무"
    assert ltv._cooldown_until["095610"] == today + timedelta(days=2 + 2), (
        "즉시 근사 = today + (days=2) + 2 달력일 (재매수 공백 0)"
    )


# ===========================================================================
# [Red] _refine_cooldown_business_days — 성공/실패 graceful  (VB 201 답습)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-07-14 01:00:00")
async def test_refine_success_replaces_with_business_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(Red): refine 성공 → `_cooldown_until` 정확 영업일 date 로 교체.

    현재 FAIL = `_refine_cooldown_business_days` 메서드 부재 (AttributeError).
    add_business_days 는 mock (KIS 호출 회피).
    """
    ltv = _make_ltv(monkeypatch)
    today = datetime.now(KST).date()
    ltv.register_cooldown_after_exit("095610")  # 우선 근사 등록

    accurate = today + timedelta(days=2)  # 임의 영업일 정정 결과
    fake_add = AsyncMock(return_value=accurate)
    import src.engine.strategies.long_tail_volatility as _ltv_mod

    monkeypatch.setattr(_ltv_mod, "add_business_days", fake_add, raising=False)

    await ltv._refine_cooldown_business_days("095610")

    fake_add.assert_awaited_once()
    assert ltv._cooldown_until["095610"] == accurate, (
        "refine 성공 → 정확 영업일 date 로 교체 의무"
    )


@pytest.mark.asyncio
@freeze_time("2026-07-14 01:00:00")
async def test_refine_failure_keeps_approx_graceful(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(Red): refine 예외 → 근사값 유지 graceful (예외 전파 0).

    현재 FAIL = 메서드 부재 (AttributeError).
    """
    ltv = _make_ltv(monkeypatch)
    today = datetime.now(KST).date()
    ltv.register_cooldown_after_exit("095610")
    approx = ltv._cooldown_until["095610"]
    assert approx == today + timedelta(days=2 + 2), "근사값 = today + days + 2 선결"

    fake_add = AsyncMock(side_effect=RuntimeError("boom"))
    import src.engine.strategies.long_tail_volatility as _ltv_mod

    monkeypatch.setattr(_ltv_mod, "add_business_days", fake_add, raising=False)

    await ltv._refine_cooldown_business_days("095610")  # 예외 전파 없이 완료

    assert ltv._cooldown_until["095610"] == approx, (
        "refine 예외 → 근사값 유지 (graceful, 재매수 공백 0 보존)"
    )


# ===========================================================================
# [불변식 PASS] 쿨다운 없는 정상 종목 돌파 → BUY (게이트 over-block 차단)
# ===========================================================================
@freeze_time("2026-07-14 01:00:00")
def test_normal_breakout_allows_buy(monkeypatch) -> None:
    """(불변식 PASS): 쿨다운 미등록 종목 정상 돌파 → BUY (게이트가 정상 종목 미차단).

    현재 코드(게이트 부재)에서 BUY. Green 후에도 쿨다운 없는 종목은 게이트 통과 → BUY 유지.
    `_cooldown_until` 직접 시드 안 함 (Green 산물 AttributeError 회피). over-block 회귀 영구 차단.
    """
    ltv = _make_ltv(monkeypatch)
    _seed_target(ltv, "095610", prev_range=1000, k=0.5)
    ltv.on_open_price_confirmed("095610", open_price=80000, board="main", source="rest")
    _activate("main")

    assert ltv.check_buy_signal("095610", 80200, 80000) == Signal.NONE  # 첫 틱 기록
    sig = ltv.check_buy_signal("095610", 80500, 80000)  # 돌파
    assert sig == Signal.BUY, (
        "쿨다운 없는 정상 종목 돌파 → BUY (게이트 불변식, over-block 0)"
    )


# ===========================================================================
# G-213-7 [SAFETY 대리] check_exit_signal 본체 불변 (당일 -3% / 상한가 -5% 분기 보존)
# ===========================================================================
@freeze_time("2026-07-14 01:00:00")
def test_g213_7_check_exit_signal_body_unchanged(monkeypatch) -> None:
    """G-213-7 (SAFETY 대리): check_exit_signal 당일/상한가 청산 분기 불변.

    쿨다운 배선이 청산 hot path 를 건드리지 않음을 대리 검증
    (매매 안전성 8영역 diff 0 은 메인 세션 git diff 로 별도 확인).
    """
    from src.engine.strategy_base import Position

    ltv = _make_ltv(monkeypatch)

    # 당일 모드 -3.5% → STOP_LOSS (intraday_stop_loss -3%)
    ltv.state.positions["095610"] = Position(
        ticker="095610", buy_price=10_000, quantity=1, order_no="O1",
        strategy_id="long_tail_volatility",
    )
    sig = ltv.check_exit_signal("095610", 9_650, 9_650)  # -3.5%
    assert sig == Signal.STOP_LOSS, "당일 모드 -3% 손절 분기 불변"

    # 상한가 모드 -3.5% → NONE (overnight -5% 미달, 당일 -3% 강등 아님)
    ltv._limit_up_reached.add("095610")
    sig2 = ltv.check_exit_signal("095610", 9_650, 9_650)  # -3.5%
    assert sig2 == Signal.NONE, "상한가 모드 overnight -5% 미달 → NONE (당일 -3% 강등 아님)"
