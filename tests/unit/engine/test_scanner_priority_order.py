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
    """41 슬롯 한도에서 breakout 38개 + momentum 5개 + swing 10개 → swing 모두 drop, breakout 우선 add."""
    caplog.set_level(logging.INFO, logger="src.engine.scanner")
    mock_subscribe, _ = _fresh_ws_subscriptions

    breakout = [f"B{i:03d}" for i in range(38)]
    momentum = [f"M{i:03d}" for i in range(5)]
    swing = [f"S{i:03d}" for i in range(10)]

    priority_groups = {
        "positions": [],
        "next_day_clear": [],
        "swing": swing,
        "momentum": momentum,
        "breakout": breakout,
    }

    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    # 호출된 ticker 순서 추출 — breakout 38 → momentum 3 슬롯만 남음 → momentum 일부 + swing 0
    called_tickers = [c.args[1] for c in mock_subscribe.call_args_list]

    # breakout 38개 모두 add (제일 먼저)
    for b in breakout:
        assert b in called_tickers, f"breakout {b} 가 우선 add 되어야 함"

    # momentum 은 잔여 3 슬롯만 add (38 + 3 = 41)
    momentum_subscribed = [t for t in called_tickers if t.startswith("M")]
    assert len(momentum_subscribed) == 3, f"momentum 3개만 add, 실제={len(momentum_subscribed)}"

    # swing 은 0개 add (한도 소진)
    swing_subscribed = [t for t in called_tickers if t.startswith("S")]
    assert len(swing_subscribed) == 0, f"swing 모두 drop 되어야 함, 실제={len(swing_subscribed)}"

    # 로그 검증: 새 형식
    log_text = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" in log_text
    assert "breakout=0" in log_text, "breakout drop 0건"
    assert "momentum=2" in log_text, "momentum 2개 drop (5-3=2)"
    assert "swing=10" in log_text, "swing 10개 drop"
    # 새 추가 필드
    assert "total_subscribed=" in log_text
    assert "max=41" in log_text
    assert "high_count=0" in log_text
    assert "remaining=" in log_text


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
    """drop>0 시 write_log("WARNING", "[priority_drop] ...") fire-and-forget 호출."""
    with patch("src.db.system_logs.write_log", new=AsyncMock()) as mock_write:
        breakout = [f"B{i:03d}" for i in range(38)]
        momentum = [f"M{i:03d}" for i in range(5)]
        swing = [f"S{i:03d}" for i in range(10)]
        priority_groups = {
            "positions": [],
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
    # 첫 인자 level == "WARNING"
    drop_args = drop_calls[0].args
    assert drop_args[0] == "WARNING", f"WARNING 레벨이어야 함, 실제={drop_args[0]}"
    # 메시지에 새 형식 4개 추가 필드 포함
    drop_msg = drop_args[1]
    assert "breakout=0" in drop_msg
    assert "momentum=2" in drop_msg
    assert "swing=10" in drop_msg
    assert "total_subscribed=" in drop_msg
    assert "max=41" in drop_msg
    assert "high_count=" in drop_msg


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
