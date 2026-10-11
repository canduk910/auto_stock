"""cycle444 — 섀도 전략 후보의 WS 구독 우선순위 최후순위화 (scanner.py 쪽).

사용자 지시(2026-10-11) 「섀도전략들은 웹소켓 시세구독 우선순위를 낮춰야해」.

`subscribe_filtered_stocks(priority_groups=...)` 가 새 `shadow` 키를 받아
LOW 안에서 breakout → momentum → swing → shadow 순으로 처리하는지, 슬롯 부족 시
`shadow` 가 가장 먼저 drop 되는지, `[priority_drop]` 로그에 `shadow=` 가 노출되는지
검증한다. 레거시 호출자(5키, `shadow` 키 부재)도 KeyError 없이 동작해야 한다
(하위 호환 — `priority_groups.get("shadow")`).

픽스처 `_fresh_ws_subscriptions` 는 `test_scanner_priority_order.py` 의 것을
그대로 재사용한다(중복 정의 금지).
"""
from __future__ import annotations

import logging

import pytest

from src.engine import scanner as scanner_module

# 픽스처 재사용 (cycle240 선례 — 동일 디렉토리 테스트 모듈의 fixture 를 import 로 공유)
from tests.unit.engine.test_scanner_priority_order import _fresh_ws_subscriptions  # noqa: F401

pytestmark = pytest.mark.unit


# ===========================================================================
# 1) 슬롯 부족 — 섀도가 실전(breakout/momentum/swing)보다 먼저 drop 된다
# ===========================================================================
@pytest.mark.asyncio
async def test_shadow_dropped_before_live_groups_when_slots_scarce(
    _fresh_ws_subscriptions, caplog,
):
    """HIGH 11 + breakout 20 + momentum 5 + swing 3 + shadow 10, 잔여 30.

    breakout(20) + momentum(5) + swing(3) = 28 로 잔여 30 을 거의 다 채우고
    shadow 는 남은 2 슬롯만 받아 8개 drop 된다 — 실전은 전량 생존.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scanner")
    mock_subscribe, _ = _fresh_ws_subscriptions

    positions = [f"H{i:03d}" for i in range(11)]
    breakout = [f"B{i:03d}" for i in range(20)]
    momentum = [f"M{i:03d}" for i in range(5)]
    swing = [f"S{i:03d}" for i in range(3)]
    shadow = [f"SH{i:03d}" for i in range(10)]

    priority_groups = {
        "positions": positions,
        "next_day_clear": [],
        "swing": swing,
        "momentum": momentum,
        "breakout": breakout,
        "shadow": shadow,
    }

    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    called = [c.args[1] for c in mock_subscribe.call_args_list]

    breakout_subscribed = [t for t in called if t.startswith("B0")]
    momentum_subscribed = [t for t in called if t.startswith("M0")]
    swing_subscribed = [t for t in called if t.startswith("S0")]
    shadow_subscribed = [t for t in called if t.startswith("SH")]

    assert len(breakout_subscribed) == 20, f"실전 breakout 전량 생존 의무, 실제={len(breakout_subscribed)}"
    assert len(momentum_subscribed) == 5, f"실전 momentum 전량 생존 의무, 실제={len(momentum_subscribed)}"
    assert len(swing_subscribed) == 3, f"실전 swing 전량 생존 의무, 실제={len(swing_subscribed)}"
    assert len(shadow_subscribed) == 2, (
        f"섀도는 잔여 2 슬롯만 받아야 한다(30-28=2), 실제={len(shadow_subscribed)}"
    )

    log_text = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" in log_text
    assert "breakout=0" in log_text
    assert "momentum=0" in log_text
    assert "swing=0" in log_text
    assert "shadow=8" in log_text, f"섀도 8개 drop 이 로그에 노출돼야 한다: {log_text}"


# ===========================================================================
# 2) 섀도 momentum 전체가 맨 뒤로 간다 (momentum 그룹이 비고 shadow 로 이동)
# ===========================================================================
@pytest.mark.asyncio
async def test_shadow_momentum_tier_subscribed_last(_fresh_ws_subscriptions, caplog):
    """momentum 키가 비어 있고 그 몫이 shadow 에 전부 있는 시나리오(섀도 momentum).

    HIGH 0 + breakout 5 + swing 0 + momentum(실전 몫) 0 + shadow(섀도 momentum) 20,
    잔여 41 — 슬롯이 넉넉해 섀도도 전부 구독되지만, 처리 순서는 breakout 먼저다.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scanner")
    mock_subscribe, _ = _fresh_ws_subscriptions

    breakout = [f"B{i:03d}" for i in range(5)]
    shadow_momentum = [f"SHM{i:03d}" for i in range(20)]

    priority_groups = {
        "positions": [],
        "next_day_clear": [],
        "swing": [],
        "momentum": [],
        "breakout": breakout,
        "shadow": shadow_momentum,
    }

    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    called = [c.args[1] for c in mock_subscribe.call_args_list]
    assert set(t for t in called if t.startswith("B")) == set(breakout)
    assert set(t for t in called if t.startswith("SHM")) == set(shadow_momentum), (
        "슬롯이 넉넉하면 섀도 momentum 도 전부 구독돼야 한다(구독 자체를 막지 않는다)"
    )
    # breakout 이 shadow 보다 먼저 subscribe 호출된다(처리 순서)
    first_shadow_idx = called.index(shadow_momentum[0])
    last_breakout_idx = max(called.index(b) for b in breakout)
    assert last_breakout_idx < first_shadow_idx, (
        f"breakout 이 shadow 보다 먼저 subscribe 돼야 한다. called={called}"
    )

    log_text = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" not in log_text, "슬롯 충분 시 drop 로그 없어야 함"


# ===========================================================================
# 3) 레거시 호출자 — priority_groups 에 shadow 키가 없어도 KeyError 없이 동작
# ===========================================================================
@pytest.mark.asyncio
async def test_legacy_priority_groups_without_shadow_key_still_works(_fresh_ws_subscriptions):
    mock_subscribe, _ = _fresh_ws_subscriptions

    priority_groups = {
        "positions": ["H1"],
        "next_day_clear": [],
        "swing": ["S1"],
        "momentum": ["M1"],
        "breakout": ["B1"],
        # "shadow" 키 없음 — 옛 호출자 호환
    }

    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    called = [c.args[1] for c in mock_subscribe.call_args_list]
    assert set(called) == {"H1", "S1", "M1", "B1"}


# ===========================================================================
# 4) overflow 순서 — shadow 는 breakout overflow 흡수보다 뒤에 처리된다
# ===========================================================================
@pytest.mark.asyncio
async def test_shadow_does_not_precede_breakout_overflow_absorption(
    _fresh_ws_subscriptions, caplog,
):
    """breakout 이 1-pass 에서 잔여를 다 쓰면(overflow 없음, cap 폐지 이후 구조),
    shadow 는 2-pass(흡수 패스)가 끝난 뒤에만 남은 슬롯을 받는다.

    cap 이 없는 현재 구조에서는 breakout_overflow 가 항상 비므로, 이 테스트는
    "shadow 가 breakout 1-pass 전체 소진보다 앞서 슬롯을 가져가지 않는다" 를
    고정한다(처리 순서 계약).
    """
    caplog.set_level(logging.INFO, logger="src.engine.scanner")
    mock_subscribe, _ = _fresh_ws_subscriptions

    positions = [f"H{i:03d}" for i in range(35)]  # 잔여 6
    breakout = [f"B{i:03d}" for i in range(5)]
    shadow = [f"SH{i:03d}" for i in range(5)]

    priority_groups = {
        "positions": positions,
        "next_day_clear": [],
        "swing": [],
        "momentum": [],
        "breakout": breakout,
        "shadow": shadow,
    }

    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    called = [c.args[1] for c in mock_subscribe.call_args_list]
    breakout_subscribed = [t for t in called if t.startswith("B")]
    shadow_subscribed = [t for t in called if t.startswith("SH")]

    assert len(breakout_subscribed) == 5, f"breakout 전량 생존(잔여 6 중 5), 실제={len(breakout_subscribed)}"
    assert len(shadow_subscribed) == 1, f"shadow 는 남은 1 슬롯만, 실제={len(shadow_subscribed)}"

    log_text = "\n".join(r.message for r in caplog.records)
    assert "shadow=4" in log_text


# ===========================================================================
# 5) [priority_drop] shadow= 집계 — drop=0 이면 shadow=0 도 함께 생략
# ===========================================================================
@pytest.mark.asyncio
async def test_priority_drop_log_omitted_when_shadow_has_no_drop(
    _fresh_ws_subscriptions, caplog,
):
    caplog.set_level(logging.INFO, logger="src.engine.scanner")
    mock_subscribe, _ = _fresh_ws_subscriptions

    priority_groups = {
        "positions": [],
        "next_day_clear": [],
        "swing": [],
        "momentum": [],
        "breakout": ["B1"],
        "shadow": ["SH1"],
    }
    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    called = [c.args[1] for c in mock_subscribe.call_args_list]
    assert set(called) == {"B1", "SH1"}

    log_text = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" not in log_text, "모두 구독되면 drop 로그가 없어야 한다"
