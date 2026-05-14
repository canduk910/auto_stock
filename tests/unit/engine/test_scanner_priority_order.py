"""LOW 우선순위 순서 재정렬: breakout → momentum → swing (2026-05-12).

배경: 일중 변동성 매매(volatility_breakout + long_tail_volatility)는 시세 무수신 시
매수 기회를 통째로 놓친다. 반면 donchian_swing 은 일봉 전략이라 1분 폴링으로 충분.
LOW 슬롯 부족 시 breakout 을 가장 마지막에 자르도록 우선순위를 재정렬.

검증 사항:
1. LOW 우선순위 순서가 breakout → momentum → swing 으로 처리된다 (drop 도 마지막)
2. drop>0 시 새 로그 형식 노출:
   `[priority_drop] breakout=X momentum=Y swing=Z total_subscribed=N max=41 high_count=H remaining=R`
3. drop>0 시 system_logs WARNING 영구 저장 (가설 A — 가시성)
4. HIGH 그룹(positions/next_day_clear) bypass_limit=True 절대 보장 회귀
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import scanner as scanner_module

pytestmark = pytest.mark.unit


@pytest.fixture
def _fresh_ws_subscriptions():
    """kis_ws._subscriptions 를 빈 set 으로 격리. subscribe 호출 시 실제 add 흉내."""
    real_subs: set[tuple[str, str]] = set()

    async def _fake_subscribe(tr_id: str, tr_key: str, *, bypass_limit: bool = False) -> None:
        # MAX_SUBSCRIPTIONS=41 한도 시뮬레이션 — bypass_limit=False 이고 한도 도달 시 add skip
        from src.realtime.websocket import MAX_SUBSCRIPTIONS

        if not bypass_limit and len(real_subs) >= MAX_SUBSCRIPTIONS:
            return
        real_subs.add((tr_id, tr_key))

    # _subscriptions 도 함께 노출해 scanner 내부 잔여 슬롯 계산이 동작하도록 한다
    with patch.object(scanner_module.kis_ws, "_subscriptions", real_subs), \
         patch.object(scanner_module.kis_ws, "subscribe", new=AsyncMock(side_effect=_fake_subscribe)) as mock:
        yield mock, real_subs


# ---------------------------------------------------------------------------
# Case 1: LOW 슬롯 부족 시 swing 이 가장 먼저 drop (breakout 살아남음)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_low_priority_drop_order_breakout_kept_swing_dropped(_fresh_ws_subscriptions, caplog):
    """LOW 슬롯 부족 시 breakout 우선, swing 가장 먼저 drop.

    작업 2 (2026-05-13) cap 25 도입 후 시나리오 조정 — 같은 의도(breakout 우선,
    swing drop) 유지하되 cap 영향 반영:
    - HIGH 11(bypass) → 잔여 30
    - breakout 38 → cap 25 (cap drop 13) → 25 add → 잔여 5
    - momentum 5 → 5 add (drop 0) → 잔여 0
    - swing 10 → 0 add → swing drop 10
    - low_remaining=0, breakout=13, momentum=0, swing=10
    """
    caplog.set_level(logging.INFO, logger="src.engine.scanner")
    mock_subscribe, _ = _fresh_ws_subscriptions

    positions = [f"H{i:03d}" for i in range(11)]
    breakout = [f"B{i:03d}" for i in range(38)]
    momentum = [f"M{i:03d}" for i in range(5)]
    swing = [f"S{i:03d}" for i in range(10)]

    priority_groups = {
        "positions": positions,
        "next_day_clear": [],
        "swing": swing,
        "momentum": momentum,
        "breakout": breakout,
    }

    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    called_tickers = [c.args[1] for c in mock_subscribe.call_args_list]

    # HIGH 11개 모두 add (bypass_limit=True)
    for h in positions:
        assert h in called_tickers, f"HIGH {h} bypass 보장"

    # breakout 은 cap 25 만 add (38 - 13 = 25)
    breakout_subscribed = [t for t in called_tickers if t.startswith("B")]
    assert len(breakout_subscribed) == 25, (
        f"breakout cap 25 적용, 실제={len(breakout_subscribed)}"
    )

    # momentum 5개 모두 add (LOW 잔여 5)
    momentum_subscribed = [t for t in called_tickers if t.startswith("M")]
    assert len(momentum_subscribed) == 5, f"momentum 5개 모두 add, 실제={len(momentum_subscribed)}"

    # swing 0개 add (한도 소진)
    swing_subscribed = [t for t in called_tickers if t.startswith("S")]
    assert len(swing_subscribed) == 0, f"swing 모두 drop 되어야 함, 실제={len(swing_subscribed)}"

    # 로그 검증
    log_text = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" in log_text
    assert "breakout=13" in log_text, f"breakout cap drop 13건, log={log_text}"
    assert "momentum=0" in log_text
    assert "swing=10" in log_text, "swing 10개 drop"
    assert "total_subscribed=" in log_text
    assert "max=41" in log_text
    assert "high_count=11" in log_text
    assert "low_remaining=0" in log_text
    assert "low_remaining=-" not in log_text


# ---------------------------------------------------------------------------
# Case 2: 기존 swing 우선 순서가 *아님* — breakout 이 swing 보다 먼저 처리됨
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_low_priority_breakout_before_swing(_fresh_ws_subscriptions):
    """breakout 5개 + swing 5개 + 한도 7 → breakout 5 + momentum 0 + swing 2 (5+0+2=7)."""
    mock_subscribe, real_subs = _fresh_ws_subscriptions

    # MAX=41 이지만, HIGH 그룹으로 34개 미리 채워 잔여 슬롯을 7로 만든다
    pre_filled_positions = [f"H{i:03d}" for i in range(34)]
    priority_groups = {
        "positions": pre_filled_positions,
        "next_day_clear": [],
        "swing": ["SW1", "SW2", "SW3", "SW4", "SW5"],
        "momentum": [],
        "breakout": ["BR1", "BR2", "BR3", "BR4", "BR5"],
    }

    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    called_tickers = [c.args[1] for c in mock_subscribe.call_args_list]

    # HIGH 34개 (bypass_limit=True)
    for h in pre_filled_positions:
        assert h in called_tickers
    # breakout 5개 (잔여 7 중 5 사용)
    for b in ["BR1", "BR2", "BR3", "BR4", "BR5"]:
        assert b in called_tickers, f"breakout {b} 가 swing 보다 우선이어야 함"
    # swing 2개만 (잔여 7-5=2 슬롯)
    swing_subscribed = [t for t in called_tickers if t.startswith("SW")]
    assert len(swing_subscribed) == 2, f"swing 은 잔여 2 슬롯만 add, 실제={len(swing_subscribed)}"


# ---------------------------------------------------------------------------
# Case 3: drop 발생 시 system_logs WARNING 영구 저장 (가설 A — 가시성)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_priority_drop_writes_warning_to_system_logs(_fresh_ws_subscriptions):
    """drop>0 시 write_log("WARNING", "[priority_drop] ...") fire-and-forget 호출.

    작업 2 (2026-05-13) cap 25 도입 후 시나리오 — HIGH 11 + breakout 38 + momentum 5
    + swing 10 → breakout cap drop 13 + swing 한도 drop 10.
    """
    with patch("src.db.system_logs.write_log", new=AsyncMock()) as mock_write:
        positions = [f"H{i:03d}" for i in range(11)]
        breakout = [f"B{i:03d}" for i in range(38)]
        momentum = [f"M{i:03d}" for i in range(5)]
        swing = [f"S{i:03d}" for i in range(10)]
        priority_groups = {
            "positions": positions,
            "next_day_clear": [],
            "swing": swing,
            "momentum": momentum,
            "breakout": breakout,
        }
        await scanner_module.subscribe_filtered_stocks(
            [], extra_tickers=[], priority_groups=priority_groups,
        )

    # write_log 가 drop>0 시 호출되었는지 + 메시지 형식 확인
    write_calls = mock_write.call_args_list
    drop_calls = [c for c in write_calls if "[priority_drop]" in str(c)]
    assert len(drop_calls) >= 1, "drop>0 시 write_log WARNING 호출되어야 함"
    drop_args = drop_calls[0].args
    assert drop_args[0] == "WARNING", f"WARNING 레벨이어야 함, 실제={drop_args[0]}"
    drop_msg = drop_args[1]
    assert "breakout=13" in drop_msg, f"breakout cap drop 13건, msg={drop_msg}"
    assert "momentum=0" in drop_msg
    assert "swing=10" in drop_msg
    assert "total_subscribed=" in drop_msg
    assert "max=41" in drop_msg
    assert "high_count=" in drop_msg
    assert "low_remaining=" in drop_msg
    assert "low_remaining=-" not in drop_msg, "low_remaining 음수 노출 금지"


# ---------------------------------------------------------------------------
# Case 4: drop=0 시에는 system_logs WARNING 호출 안 함
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_drop_no_warning_log(_fresh_ws_subscriptions):
    """slot 여유 충분하면 system_logs WARNING 호출 안 함."""
    with patch("src.db.system_logs.write_log", new=AsyncMock()) as mock_write:
        priority_groups = {
            "positions": [],
            "next_day_clear": [],
            "swing": ["SW1"],
            "momentum": ["M1"],
            "breakout": ["BR1"],
        }
        await scanner_module.subscribe_filtered_stocks(
            [], extra_tickers=[], priority_groups=priority_groups,
        )

    drop_calls = [c for c in mock_write.call_args_list if "[priority_drop]" in str(c)]
    assert len(drop_calls) == 0, "drop=0 일 때 priority_drop WARNING 로그 없어야 함"


# ---------------------------------------------------------------------------
# Case 5: HIGH 그룹(positions/next_day_clear) bypass_limit=True 절대 보장 회귀
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Case 6 (Copilot P2): HIGH bypass 시 low_remaining 음수 차단
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_priority_drop_log_low_remaining_never_negative_when_high_overflow(
    _fresh_ws_subscriptions, caplog,
):
    """HIGH 50개(MAX_SUBSCRIPTIONS=41 초과) + LOW drop 발생 시 low_remaining=0 노출.

    이전 `remaining = MAX - total_subscribed` 는 음수 노출 가능 → 대시보드 해석 혼동.
    Copilot 피드백: `max(0, ...)` 로 clamp + `low_remaining` 로 의미 명확화.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    positions = [f"P{i:03d}" for i in range(50)]  # HIGH 50개 (bypass_limit=True)
    # LOW 그룹에 drop 발생을 유도해 로그 노출
    swing = [f"S{i:03d}" for i in range(3)]
    priority_groups = {
        "positions": positions,
        "next_day_clear": [],
        "swing": swing,
        "momentum": [],
        "breakout": [],
    }

    with patch("src.db.system_logs.write_log", new=AsyncMock()) as mock_write:
        await scanner_module.subscribe_filtered_stocks(
            [], extra_tickers=[], priority_groups=priority_groups,
        )

    # 로그에서 low_remaining 값 검증 — 음수 불가, 0 으로 clamp
    log_text = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" in log_text, "drop 발생 → priority_drop 로그 노출"
    assert "low_remaining=0" in log_text, (
        f"HIGH overflow 시에도 low_remaining=0 으로 clamp 필요. log={log_text}"
    )
    assert "low_remaining=-" not in log_text, "음수 노출 금지"

    # system_logs 영구 저장 메시지도 동일 검증
    drop_calls = [c for c in mock_write.call_args_list if "[priority_drop]" in str(c)]
    assert len(drop_calls) >= 1
    persisted = drop_calls[0].args[1]
    assert "low_remaining=0" in persisted
    assert "low_remaining=-" not in persisted


@pytest.mark.asyncio
async def test_high_group_bypass_limit_preserved(_fresh_ws_subscriptions):
    """positions 50개 + next_day_clear 10개 → 모두 add (한도 41 무시)."""
    mock_subscribe, real_subs = _fresh_ws_subscriptions

    positions = [f"P{i:03d}" for i in range(50)]
    next_day_clear = [f"N{i:03d}" for i in range(10)]
    priority_groups = {
        "positions": positions,
        "next_day_clear": next_day_clear,
        "swing": [],
        "momentum": [],
        "breakout": [],
    }
    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    # 모든 HIGH 종목 호출 검증 (bypass_limit=True)
    high_calls = [c for c in mock_subscribe.call_args_list if c.kwargs.get("bypass_limit") is True]
    assert len(high_calls) == 60, f"HIGH 60개 모두 bypass_limit=True 로 호출, 실제={len(high_calls)}"


# ---------------------------------------------------------------------------
# 작업 2 (2026-05-13): breakout LOW 슬롯 cap 25 (momentum 보호)
# ---------------------------------------------------------------------------
#
# 배경: 2026-05-13 08:57:39 로그 — `사전 구독: total=33 (vb=30, ltv=30, swing=2,
# momentum=0, positions=3)`. BLNG 다중 호출로 VB/LTV 각 30 → dedup 28 breakout
# 슬롯 점유. 09:30 momentum 발화 시 추가 ~10~30 → 41 초과 → momentum drop 위험.
# 모멘텀 매수 기회 통째로 상실 차단 위해 breakout 후순위 cap 25.
# ---------------------------------------------------------------------------

def test_breakout_cap_constant_value_is_25():
    """`scanner.BREAKOUT_LOW_CAP` 상수가 25 로 정의되어 있어야 한다."""
    assert hasattr(scanner_module, "BREAKOUT_LOW_CAP"), (
        "scanner 에 BREAKOUT_LOW_CAP 상수가 정의되어야 함"
    )
    assert scanner_module.BREAKOUT_LOW_CAP == 25, (
        f"BREAKOUT_LOW_CAP=25 가 명세값, 실제={scanner_module.BREAKOUT_LOW_CAP}"
    )


@pytest.mark.asyncio
async def test_breakout_cap_25_applied_when_breakout_exceeds(_fresh_ws_subscriptions, caplog):
    """breakout 30개 → cap 25 → 25 add + 5 drop (slot 충분해도 cap 우선)."""
    caplog.set_level(logging.INFO, logger="src.engine.scanner")
    mock_subscribe, _ = _fresh_ws_subscriptions

    breakout = [f"B{i:03d}" for i in range(30)]
    priority_groups = {
        "positions": [],
        "next_day_clear": [],
        "swing": [],
        "momentum": [],
        "breakout": breakout,
    }
    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    called = [c.args[1] for c in mock_subscribe.call_args_list]
    breakout_subscribed = [t for t in called if t.startswith("B")]
    assert len(breakout_subscribed) == 25, (
        f"breakout 25개만 add (cap 25 적용), 실제={len(breakout_subscribed)}"
    )

    # drop 카운트 = 5 (30 - 25)
    log_text = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" in log_text
    assert "breakout=5" in log_text, f"breakout=5 drop 필요, log={log_text}"


@pytest.mark.asyncio
async def test_breakout_cap_preserves_momentum_slot(_fresh_ws_subscriptions, caplog):
    """HIGH 4 + breakout 30 + momentum 10 → breakout 25 / momentum 10, drop=(b=5,m=0,s=0).

    명세 slot 분배 시뮬레이션:
    - HIGH: positions 3 + next_day_clear 1 = 4 (bypass)
    - LOW 잔여: 41-4 = 37
    - breakout 30 → cap 25 → 25 add + 5 drop
    - momentum 10 → 잔여 12 → 10 add (drop 0)
    - swing 0
    - total_subscribed = 4+25+10 = 39 (≤ 41), low_remaining = 2
    """
    caplog.set_level(logging.INFO, logger="src.engine.scanner")
    mock_subscribe, _ = _fresh_ws_subscriptions

    positions = ["P001", "P002", "P003"]
    next_day_clear = ["N001"]
    breakout = [f"B{i:03d}" for i in range(30)]
    momentum = [f"M{i:03d}" for i in range(10)]

    priority_groups = {
        "positions": positions,
        "next_day_clear": next_day_clear,
        "swing": [],
        "momentum": momentum,
        "breakout": breakout,
    }
    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    called = [c.args[1] for c in mock_subscribe.call_args_list]
    high_subscribed = [t for t in called if t.startswith("P") or t.startswith("N")]
    breakout_subscribed = [t for t in called if t.startswith("B")]
    momentum_subscribed = [t for t in called if t.startswith("M")]

    assert len(high_subscribed) == 4, f"HIGH 4개 모두 add, 실제={len(high_subscribed)}"
    assert len(breakout_subscribed) == 25, f"breakout cap 25 적용, 실제={len(breakout_subscribed)}"
    assert len(momentum_subscribed) == 10, f"momentum 10개 모두 add 보호, 실제={len(momentum_subscribed)}"

    log_text = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" in log_text
    assert "breakout=5" in log_text
    assert "momentum=0" in log_text
    assert "swing=0" in log_text


@pytest.mark.asyncio
async def test_breakout_cap_no_effect_when_under_cap(_fresh_ws_subscriptions, caplog):
    """breakout 20개 (cap 25 미만) → 20개 add + drop 0 → priority_drop 로그 없음."""
    caplog.set_level(logging.INFO, logger="src.engine.scanner")
    mock_subscribe, _ = _fresh_ws_subscriptions

    breakout = [f"B{i:03d}" for i in range(20)]
    priority_groups = {
        "positions": [],
        "next_day_clear": [],
        "swing": [],
        "momentum": [],
        "breakout": breakout,
    }
    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    called = [c.args[1] for c in mock_subscribe.call_args_list]
    breakout_subscribed = [t for t in called if t.startswith("B")]
    assert len(breakout_subscribed) == 20, f"breakout 20개 모두 add, 실제={len(breakout_subscribed)}"

    # cap 미적용 + slot 여유 → drop 0 → priority_drop 로그 없음
    log_text = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" not in log_text, "drop 0 시 priority_drop 로그 없어야 함"
