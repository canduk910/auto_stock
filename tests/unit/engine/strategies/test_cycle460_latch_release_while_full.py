"""cycle460 (RED) — BFB·VCP 「만석 중에도 거래량 래치 해제 규칙을 적용한다」.

## 결함 (cycle449 「알려진 한계 (a)」)

만석 **전에** 오늘자 거래량 래치가 무장된 종목은 만석 동안 하단(`flag_low`/`base_low`)
이탈이 해제로 이어지지 않는다. 만석 반환(`is_max_positions`)이 래치 재평가 블록보다 앞이라
하단 이탈 틱이 해제 판정에 닿지 않고, `_track_baseline_while_full` 은 오늘자 래치를
「불가침」으로 건너뛴다. 그래서 슬롯이 빈 뒤 돌파선 위 틱이 새 교차 없이 래치 경로로
거래량 게이트에 가서, 급락·반등 거래량으로 「오늘 이미 깨진 셋업」을 산다.

## 계약 (사용자 결정 2026-10-15 + 자문 A안 — `_workspace/domain_consult/2026-10-15_bfb_vcp_latch_full.md`)

`_track_baseline_while_full` 이 오늘자 래치를 만나면 비만석 래치 블록과 **같은 해제 규칙**을
적용한다 — `level_moved`(돌파선·하단이 래치 값과 다름) 먼저, 그다음 `stop_line`(하단 > 0
이고 현재가 < 하단, 엄격). 둘 다 아니면 지금처럼 래치·직전 가격 무접촉. 해제되면 그 틱부터
래치 없는 종목과 같고 만석 추적을 이어 `_prev_price = 현재가`.

마커 = 기존 `[bfb|vcp_latch_released] ticker= reason=` 에 만석 경로만 끝 ` where=full`.
cap 키는 그대로 `latch_released:<reason>`.

시계·픽스처는 cycle449 파일과 같다(`freeze_time` 10:00 — 두 전략 매수 창 안).
"""

from __future__ import annotations

import logging
from datetime import date, datetime

import pytest
from freezegun import freeze_time

from src.engine import tick_volume
from src.engine.strategy_base import Signal
from tests.unit.engine.strategies.test_cycle449_slot_full_baseline import (
    BFB,
    IN_WINDOW,
    VCP,
    Kit,
    _fill_slots,
    _free_one_slot,
    _marker_records,
    _tick,
)

pytestmark = pytest.mark.unit


@pytest.fixture(params=[BFB, VCP], ids=lambda k: k.name)
def kit(request) -> Kit:
    return request.param


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    tick_volume.reset_for_test()
    monkeypatch.setattr("src.engine.scanner.ticker_prices", {}, raising=False)
    yield
    tick_volume.reset_for_test()


def _low_key(kit: Kit) -> str:
    return kit.line_key.replace("high", "low")


def _release_marker(kit: Kit) -> str:
    return f"[{kit.name}_latch_released]"


def _release_records(caplog, kit: Kit) -> list[logging.LogRecord]:
    return [
        r for r in caplog.records
        if r.name == kit.logger_name
        and r.levelno == logging.INFO
        and r.getMessage().startswith(_release_marker(kit) + " ")
    ]


def _arm_latch_not_full(strat, kit: Kit) -> dict:
    """비만석에서 교차 + 거래량 미달 → 래치 무장(실제 경로)."""
    tick_volume.record_acml_vol(kit.ticker, kit.short_vol)
    strat._prev_price[kit.ticker] = kit.line - 100
    assert _tick(strat, kit, kit.line + 100) == Signal.NONE
    assert kit.ticker in strat._vol_latch, "픽스처 오류 — 래치가 무장되지 않았다"
    return dict(strat._vol_latch[kit.ticker])


def _seed_today_latch(strat, kit: Kit, *, low: int) -> None:
    """오늘자 래치를 직접 심는다(하단 0 처럼 실제 경로로 만들기 어려운 모양용)."""
    strat._vol_latch[kit.ticker] = {
        "armed_at": datetime(2026, 10, 12, 9, 30, 0),
        "armed_date": date(2026, 10, 12),
        kit.line_key: kit.line,
        _low_key(kit): low,
    }


# ###########################################################################
# R1 — 만석 중 하단 이탈 → 해제 → 슬롯 빔 → 선 위 틱은 BUY 아님
# ###########################################################################

def test_r1_stop_line_while_full_releases_and_no_stale_latch_buy(kit, caplog):
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _arm_latch_not_full(strat, kit)
        held = _fill_slots(strat)

        assert _tick(strat, kit, kit.low - 1) == Signal.NONE
        assert kit.ticker not in strat._vol_latch, (
            "만석 중 하단 이탈인데 래치가 그대로다 — 슬롯이 빈 뒤 낡은 래치로 산다"
        )
        assert strat._prev_price.get(kit.ticker) == kit.low - 1, (
            "해제 뒤 만석 추적이 이어지지 않았다(직전 가격 미갱신)"
        )
        recs = _release_records(caplog, kit)
        assert len(recs) == 1, [r.getMessage() for r in caplog.records]
        assert recs[0].getMessage() == (
            f"{_release_marker(kit)} ticker={kit.ticker} reason=stop_line where=full"
        )

        # 자문 시나리오 5단계 — 아직 만석인 동안 V자로 돌파선 위 복귀(급락·반등 거래량).
        assert _tick(strat, kit, kit.line + 50) == Signal.NONE

        _free_one_slot(strat, held)
        tick_volume.record_acml_vol(kit.ticker, kit.enough_vol)
        sig = _tick(strat, kit, kit.line + 100)

    assert sig == Signal.NONE, f"하단을 깬 셋업을 슬롯이 빈 뒤 {sig} 로 샀다(낡은 래치 경로)"
    assert kit.ticker not in strat._bought_today
    assert kit.ticker not in strat._vol_latch


def test_r1b_release_then_direct_jump_after_free_is_fresh_cross(kit):
    """해제 틱은 직전 가격을 그 틱 값(하단 아래)으로 둔다(자문 「경계」 표). 그래서 슬롯이
    빈 뒤 바로 돌파선 위로 온 틱은 「선 아래 → 위」 진짜 교차로 fresh 경로에서 평가된다
    (래치 경로가 아니다 — 새 교차 · retention · 거래량 게이트를 그대로 거친다).

    자문 R1 표의 「하단−1 → 슬롯 빔 → 선+100 = BUY 아님」 은 사이에 틱이 없을 때 이 규칙과
    어긋난다 — 실제 시세에서는 하단 아래에서 돌파선 위까지 가는 동안 틱이 있고, 그 틱이
    만석 중이면 R1·R6(BUY 아님), 슬롯이 빈 뒤면 R2(진짜 재교차 BUY)가 된다.
    """
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _arm_latch_not_full(strat, kit)
        held = _fill_slots(strat)
        _tick(strat, kit, kit.low - 1)
        _free_one_slot(strat, held)
        tick_volume.record_acml_vol(kit.ticker, kit.enough_vol)
        sig = _tick(strat, kit, kit.line + 100)

    assert sig == Signal.BUY
    assert kit.ticker not in strat._vol_latch


# ###########################################################################
# R2 — R1 뒤 진짜 재교차는 산다 (기회 상실 0)
# ###########################################################################

def test_r2_after_full_release_real_recross_buys(kit):
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _arm_latch_not_full(strat, kit)
        held = _fill_slots(strat)
        _tick(strat, kit, kit.low - 1)
        assert _tick(strat, kit, kit.line + 50) == Signal.NONE   # 만석 중 복귀 — 포기
        _free_one_slot(strat, held)
        tick_volume.record_acml_vol(kit.ticker, kit.enough_vol)

        assert _tick(strat, kit, kit.line + 100) == Signal.NONE
        assert _tick(strat, kit, kit.line - 100) == Signal.NONE
        sig = _tick(strat, kit, kit.line + 100)

    assert sig == Signal.BUY, "해제 뒤 진짜 재교차인데 사지 않았다(기회 상실)"
    assert kit.ticker in strat._bought_today


# ###########################################################################
# R3 — 동가(정확히 하단)는 해제하지 않는다 → 슬롯 빔 뒤 래치 경로 BUY
# ###########################################################################

def test_r3_equal_to_low_keeps_latch_then_latch_path_buys(kit, caplog):
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        latch_before = _arm_latch_not_full(strat, kit)
        held = _fill_slots(strat)

        assert _tick(strat, kit, kit.low) == Signal.NONE
        assert strat._vol_latch.get(kit.ticker) == latch_before, "동가에서 래치가 풀렸다"
        assert _release_records(caplog, kit) == []

        _free_one_slot(strat, held)
        tick_volume.record_acml_vol(kit.ticker, kit.enough_vol)
        sig = _tick(strat, kit, kit.line + 100)

    assert sig == Signal.BUY, "동가로 유지된 래치가 래치 경로로 사지 않았다"


# ###########################################################################
# R4 — 하단 위 틱들(깃발 안·선 위)은 래치·직전 가격 무접촉
# ###########################################################################

def test_r4_ticks_above_low_while_full_touch_nothing(kit, caplog):
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        latch_before = _arm_latch_not_full(strat, kit)
        prev_before = strat._prev_price[kit.ticker]
        _fill_slots(strat)
        for price in (kit.low + 1, kit.line - 1, kit.line + 200, kit.line + 50):
            assert _tick(strat, kit, price) == Signal.NONE

    assert strat._vol_latch.get(kit.ticker) == latch_before
    assert strat._prev_price[kit.ticker] == prev_before
    assert _release_records(caplog, kit) == []
    assert _marker_records(caplog, kit) == []


# ###########################################################################
# R5 — 레벨 이동은 만석 중에도 level_moved 해제
# ###########################################################################

@pytest.mark.parametrize("which", ["line", "low"])
def test_r5_level_moved_while_full_releases(kit, caplog, which):
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _arm_latch_not_full(strat, kit)
        _fill_slots(strat)
        key = kit.line_key if which == "line" else _low_key(kit)
        strat._candidates[kit.ticker][key] = strat._candidates[kit.ticker][key] + 10

        price = kit.line - 300
        assert _tick(strat, kit, price) == Signal.NONE

    assert kit.ticker not in strat._vol_latch
    assert strat._prev_price.get(kit.ticker) == price
    msgs = [r.getMessage() for r in _release_records(caplog, kit)]
    assert msgs == [
        f"{_release_marker(kit)} ticker={kit.ticker} reason=level_moved where=full"
    ]


def test_r5b_level_moved_takes_precedence_over_stop_line(kit, caplog):
    """레벨 이동과 하단 이탈이 같은 틱이면 사유는 level_moved(비만석과 같은 순서)."""
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _arm_latch_not_full(strat, kit)
        _fill_slots(strat)
        strat._candidates[kit.ticker][kit.line_key] += 10
        _tick(strat, kit, kit.low - 1)

    msgs = [r.getMessage() for r in _release_records(caplog, kit)]
    assert msgs == [
        f"{_release_marker(kit)} ticker={kit.ticker} reason=level_moved where=full"
    ]


# ###########################################################################
# R6 — 해제 뒤 만석 중 선 위 → full_cross 1회, 슬롯 빈 뒤 선 위는 BUY 아님
# ###########################################################################

def test_r6_after_release_cross_while_full_is_skipped_cycle449_semantics(kit, caplog):
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _arm_latch_not_full(strat, kit)
        held = _fill_slots(strat)
        _tick(strat, kit, kit.low - 1)
        assert _marker_records(caplog, kit) == [], "해제 틱에 교차 스킵 로그가 찍혔다"
        _tick(strat, kit, kit.line + 100)
        assert len(_marker_records(caplog, kit)) == 1

        _free_one_slot(strat, held)
        tick_volume.record_acml_vol(kit.ticker, kit.enough_vol)
        sig = _tick(strat, kit, kit.line + 100)

    assert sig == Signal.NONE
    assert kit.ticker not in strat._bought_today


# ###########################################################################
# R7 — 하단 0 이하이면 하단 이탈은 보지 않는다
# ###########################################################################

def test_r7_zero_low_never_stop_line_while_full(kit, caplog):
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        strat._candidates[kit.ticker][_low_key(kit)] = 0
        _seed_today_latch(strat, kit, low=0)
        latch_before = dict(strat._vol_latch[kit.ticker])
        _fill_slots(strat)
        assert _tick(strat, kit, 1) == Signal.NONE

    assert strat._vol_latch.get(kit.ticker) == latch_before
    assert _release_records(caplog, kit) == []


# ###########################################################################
# R8 — 해제 중 예외는 삼키고 NONE
# ###########################################################################

def test_r8_release_exception_is_swallowed(kit, monkeypatch):
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _arm_latch_not_full(strat, kit)
        _fill_slots(strat)

        def _boom(*args, **kwargs):
            raise RuntimeError("release down")

        monkeypatch.setattr(strat, "_release_latch", _boom)
        assert _tick(strat, kit, kit.low - 1) == Signal.NONE


# ###########################################################################
# R9 — 해제 뒤 만석 중 다시 하단 이탈 → 해제 로그는 1줄
# ###########################################################################

def test_r9_second_stop_line_while_full_logs_once(kit, caplog):
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _arm_latch_not_full(strat, kit)
        _fill_slots(strat)
        _tick(strat, kit, kit.low - 1)
        _tick(strat, kit, kit.low + 100)
        _tick(strat, kit, kit.low - 2)

    assert len(_release_records(caplog, kit)) == 1


# ###########################################################################
# R10 — 비만석 래치 블록과 만석 해제 판정의 일치
# ###########################################################################

_PARITY_CASES = {
    "equal_low": dict(price=lambda k: k.low, low=None, shift=None),
    "zero_low": dict(price=lambda k: 1, low=0, shift=None),
    "level_moved": dict(price=lambda k: k.line - 300, low=None, shift="line"),
    "below_low": dict(price=lambda k: k.low - 1, low=None, shift=None),
    "inside_flag": dict(price=lambda k: k.line - 1, low=None, shift=None),
    "above_line": dict(price=lambda k: k.line + 100, low=None, shift=None),
}


def _parity_outcome(kit: Kit, case: dict, *, full: bool) -> tuple[bool, frozenset]:
    strat = kit.make()
    low = kit.low if case["low"] is None else case["low"]
    strat._candidates[kit.ticker][_low_key(kit)] = low
    _seed_today_latch(strat, kit, low=low)
    if case["shift"] == "line":
        strat._candidates[kit.ticker][kit.line_key] += 10
    tick_volume.record_acml_vol(kit.ticker, kit.short_vol)
    if full:
        _fill_slots(strat)
    _tick(strat, kit, case["price"](kit))
    reasons = frozenset(
        k for (t, k) in strat._gate_emit_capped
        if t == kit.ticker and k.startswith("latch_released:")
    )
    return kit.ticker in strat._vol_latch, reasons


@pytest.mark.parametrize("case_id", list(_PARITY_CASES))
def test_r10_full_and_not_full_release_decisions_match(kit, case_id):
    case = _PARITY_CASES[case_id]
    with freeze_time(IN_WINDOW):
        not_full = _parity_outcome(kit, case, full=False)
        tick_volume.reset_for_test()
        full = _parity_outcome(kit, case, full=True)
    assert full == not_full, f"{case_id}: 만석 {full} != 비만석 {not_full}"


# ###########################################################################
# R11 — 비만석 경로 해제 로그 줄은 바이트 그대로(where 없음)
# ###########################################################################

def test_r11_not_full_release_line_has_no_where(kit, caplog):
    caplog.set_level(logging.INFO, logger=kit.logger_name)
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _arm_latch_not_full(strat, kit)
        _tick(strat, kit, kit.low - 1)

    msgs = [r.getMessage() for r in _release_records(caplog, kit)]
    assert msgs == [f"{_release_marker(kit)} ticker={kit.ticker} reason=stop_line"]


# ###########################################################################
# R12 — 모니터가 읽는 cap 키는 그대로 `latch_released:<reason>`
# ###########################################################################

def test_r12_full_release_uses_same_cap_key(kit):
    strat = kit.make()
    with freeze_time(IN_WINDOW):
        _arm_latch_not_full(strat, kit)
        _fill_slots(strat)
        _tick(strat, kit, kit.low - 1)

    assert (kit.ticker, "latch_released:stop_line") in strat._gate_emit_capped
    assert not any(
        k.startswith("latch_released:") and k != "latch_released:stop_line"
        for (t, k) in strat._gate_emit_capped if t == kit.ticker
    )
