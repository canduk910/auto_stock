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
    """kis_ws._subscriptions 를 빈 set 으로 격리. subscribe 호출 시 실제 add 흉내.

    사이클 7-C — 풀의 `_ticker_to_session` 도 매 테스트마다 초기화. 풀이
    `kis_ws_pool.subscribe` 진입 시 추적 dict 에 ticker 가 있으면 dedup 으로
    `_main.subscribe` 재호출 안 함 → mock 호출 누락 결함.
    """
    from src.realtime.websocket_pool import kis_ws_pool

    real_subs: set[tuple[str, str]] = set()

    async def _fake_subscribe(tr_id: str, tr_key: str, *, bypass_limit: bool = False) -> None:
        # MAX_SUBSCRIPTIONS=41 한도 시뮬레이션 — bypass_limit=False 이고 한도 도달 시 add skip
        from src.realtime.websocket import MAX_SUBSCRIPTIONS

        if not bypass_limit and len(real_subs) >= MAX_SUBSCRIPTIONS:
            return
        real_subs.add((tr_id, tr_key))

    # 풀의 분배 추적 dict 초기화 (이전 테스트 잔재 차단)
    kis_ws_pool._ticker_to_session.clear()

    # _subscriptions 도 함께 노출해 scanner 내부 잔여 슬롯 계산이 동작하도록 한다
    with patch.object(scanner_module.kis_ws, "_subscriptions", real_subs), \
         patch.object(scanner_module.kis_ws, "subscribe", new=AsyncMock(side_effect=_fake_subscribe)) as mock:
        yield mock, real_subs

    # 테스트 종료 후에도 정리
    kis_ws_pool._ticker_to_session.clear()


# ---------------------------------------------------------------------------
# Case 1: LOW 슬롯 부족 시 swing 이 가장 먼저 drop (breakout 살아남음)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_low_priority_drop_order_breakout_kept_swing_dropped(_fresh_ws_subscriptions, caplog):
    """LOW 슬롯 부족 시 breakout 우선, swing·momentum 이 drop.

    [의미 전환 2026-08-08] cap 25 제거 → breakout 전체 pass-1 최우선.
    momentum 명분(발화 슬롯 보장)이 비활성으로 소멸했으므로 breakout 이
    잔여 슬롯을 다 먹고 momentum·swing 이 밀린다(사용자 결정):
    - HIGH 11(bypass) → 잔여 30
    - breakout 38 → 30 add (한도 소진) → 8 drop → 잔여 0
    - momentum 5 → 0 add (drop 5)
    - swing 10 → 0 add (drop 10)
    - low_remaining=0, breakout=8, momentum=5, swing=10
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

    # breakout 은 잔여 30 을 다 먹는다 (cap 없음, 38 중 30 add / 8 drop)
    breakout_subscribed = [t for t in called_tickers if t.startswith("B")]
    assert len(breakout_subscribed) == 30, (
        f"breakout 전체 pass-1 우선, 잔여 30 소진, 실제={len(breakout_subscribed)}"
    )

    # momentum 0개 add (breakout 이 한도 소진 — 명분 소멸)
    momentum_subscribed = [t for t in called_tickers if t.startswith("M")]
    assert len(momentum_subscribed) == 0, f"momentum 도 밀린다, 실제={len(momentum_subscribed)}"

    # swing 0개 add (한도 소진)
    swing_subscribed = [t for t in called_tickers if t.startswith("S")]
    assert len(swing_subscribed) == 0, f"swing 모두 drop 되어야 함, 실제={len(swing_subscribed)}"

    # 로그 검증
    log_text = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" in log_text
    assert "breakout=8" in log_text, f"breakout 한도 drop 8건, log={log_text}"
    assert "momentum=5" in log_text, "momentum 5개 drop"
    assert "swing=10" in log_text, "swing 10개 drop"
    assert "total_subscribed=" in log_text
    assert "max=41" in log_text
    assert "high_count=11" in log_text
    assert "low_remaining=0" in log_text
    assert "low_remaining=-" not in log_text
    # 2026-08-10 — pool 실제 구독량/잔여 병기 (drop 이 세션 미활용인지 실제 만석인지 판별)
    assert "pool_subscribed=" in log_text, "pool 실제 구독량 계측 병기 의무"
    assert "pool_remaining=" in log_text, "pool 잔여(실제 drop 판정 기준) 계측 병기 의무"


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
async def test_priority_drop_writes_warning_to_system_logs(
    _fresh_ws_subscriptions, caplog,
):
    """drop>0 시 logger.warning("[priority_drop] ...") 호출 + caplog 검증.

    [의미 전환 2026-08-08] cap 25 제거 — HIGH 11 + breakout 38 + momentum 5 +
    swing 10 → breakout 30 add(한도 소진) → breakout 8 + momentum 5 + swing 10 drop.

    사이클 72 hotfix: write_log → logger.warning 변경 → caplog 검증으로 전환.
    """
    caplog.set_level(logging.WARNING, logger="src.engine.scanner")
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

    # caplog 에서 [priority_drop] WARNING 검증 (사이클 72: write_log 제거 → logger.warning 단독)
    drop_records = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and "[priority_drop]" in r.message
    ]
    assert len(drop_records) >= 1, "drop>0 시 [priority_drop] WARNING 로그 없음"
    drop_msg = drop_records[0].message
    assert "breakout=8" in drop_msg, f"breakout 한도 drop 8건, msg={drop_msg}"
    assert "momentum=5" in drop_msg
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

    사이클 72 hotfix: write_log → logger.warning 변경 → caplog 검증으로 전환.
    """
    caplog.set_level(logging.WARNING, logger="src.engine.scanner")

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

    await scanner_module.subscribe_filtered_stocks(
        [], extra_tickers=[], priority_groups=priority_groups,
    )

    # caplog 에서 low_remaining 값 검증 — 음수 불가, 0 으로 clamp
    log_text = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" in log_text, "drop 발생 → priority_drop 로그 노출"
    assert "low_remaining=0" in log_text, (
        f"HIGH overflow 시에도 low_remaining=0 으로 clamp 필요. log={log_text}"
    )
    assert "low_remaining=-" not in log_text, "음수 노출 금지"


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

def test_breakout_cap_constant_removed():
    """[의미 전환 2026-08-08] BREAKOUT_LOW_CAP 제거 — momentum 명분 소멸.

    cap 은 살아있는 breakout(BFB/VCP) 슬롯을 죽은 momentum 급등 스캔으로
    전용시키는 능동적 손해였다. breakout 전체가 pass-1 최우선.
    """
    assert not hasattr(scanner_module, "BREAKOUT_LOW_CAP"), (
        "BREAKOUT_LOW_CAP 은 제거됐다 — breakout 전체 pass-1 우선"
    )


@pytest.mark.asyncio
async def test_breakout_cap_25_applied_when_breakout_exceeds(_fresh_ws_subscriptions, caplog):
    """breakout 30개 (cap 25 → overflow 5) — slot 충분하면 PR-E 2-pass 가 overflow 흡수.

    PR-E (2026-05-15): cap 만 add 하고 잔여 슬롯이 있으면 overflow 를 흡수.
    HIGH 0 + breakout 30 + 다른 그룹 0 → 1차 25 + 2차 5(overflow) = 30, drop=0.
    """
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
    assert len(breakout_subscribed) == 30, (
        f"PR-E 2-pass: 잔여 슬롯에 overflow 5 흡수 → 30 add, 실제={len(breakout_subscribed)}"
    )

    # drop=0 → priority_drop 로그 미노출
    log_text = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" not in log_text, (
        f"PR-E 2-pass 흡수 후 drop=0 → 로그 미노출, log={log_text}"
    )


@pytest.mark.asyncio
async def test_breakout_takes_priority_over_momentum(_fresh_ws_subscriptions, caplog):
    """[의미 전환 2026-08-08] momentum 슬롯 보호 폐기 — breakout 최우선.

    cap 25 의 핵심 의도였던 "momentum 슬롯 보호"는 momentum 비활성으로 명분이
    소멸했다. 이제 breakout 이 잔여 슬롯을 먼저 먹고 momentum 이 밀린다(사용자 결정).
    HIGH 4 + breakout 30 + momentum 10:
      - 잔여 = 41 - 4 = 37
      - breakout 30 → 30 add (잔여 7, drop 0)
      - momentum 10 → 7 add (drop 3)
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
    # breakout 최우선 — 전체 30 add (cap 없음)
    assert len(breakout_subscribed) == 30, (
        f"breakout 전체 pass-1 우선, 실제={len(breakout_subscribed)}"
    )
    # momentum 은 잔여 7 만 (명분 소멸, breakout 이 먼저 먹음)
    assert len(momentum_subscribed) == 7, (
        f"momentum 은 잔여 7 슬롯만, 실제={len(momentum_subscribed)}"
    )

    log_text = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" in log_text
    assert "breakout=0" in log_text, f"breakout 전체 add, drop 0, log={log_text}"
    assert "momentum=3" in log_text, "momentum 3 drop (10 - 잔여 7)"
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


# ---------------------------------------------------------------------------
# 2026-08-08 — breakout 병합 순서 BFB→VCP→VB→LTV (tail 편중 해소)
# ---------------------------------------------------------------------------
def test_collect_breakout_order_bfb_vcp_first():
    """`_collect_breakout_tickers` 가 BFB→VCP→VB→LTV 순으로 병합한다.

    dedup 순서 보존 → pool 압박 시 tail(VB/LTV)부터 잘려 BFB/VCP 우선 구독.
    종전 VB→LTV→BFB→VCP 는 BFB/VCP 를 tail 로 밀었다(60% 미구독 실측).
    """
    import inspect
    from src.engine.scheduler import TradingScheduler

    src = inspect.getsource(TradingScheduler._collect_breakout_tickers)
    i_bfb = src.find('"bull_flag_breakout"')
    i_vcp = src.find('"vcp_breakout"')
    i_vb = src.find('"volatility_breakout"')
    i_ltv = src.find('"long_tail_volatility"')
    assert 0 < i_bfb < i_vcp < i_vb < i_ltv, (
        f"BFB→VCP→VB→LTV 순이어야 함 (bfb={i_bfb} vcp={i_vcp} vb={i_vb} ltv={i_ltv})"
    )
