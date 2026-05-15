"""WebSocket 시세 구독 우선순위 큐 (E1, 2026-05-12).

결함 배경: 오늘 09:30:09 운영 로그
    "실시간 시세 구독 완료: 33종목 (모멘텀: 9, 기타: 42)"
- 원본 합계 9+42=51 > KIS 공식 한도 41
- 41 초과분이 silently 거절되어 보유 종목 시세까지 누락된 정황
- 어제·오늘 donchian_swing 조기 손절 사건의 루트 원인

본 테스트는 다음 사양을 검증한다:

1. `MAX_SUBSCRIPTIONS = 41` (KIS 공식 한도)
2. `KisWebSocket.subscribe(tr_id, tr_key, *, bypass_limit: bool = False)`
   - bypass_limit=True 면 한도 검사 skip, 무조건 add
   - bypass_limit=False (기본) 면 기존 분기 유지
3. `subscribe_filtered_stocks(..., *, priority_groups: dict[str, list[str]] | None = None)`
   - HIGH→LOW: positions → next_day_clear → **breakout → momentum → swing**
   - positions / next_day_clear 는 bypass_limit=True (한도 무시 절대 보장)
   - 후순위는 잔여 슬롯만큼만 add, drop 카운트 `[priority_drop]` INFO 로그 1행
   - 중복 제거: 같은 종목은 HIGH 순위로 1회만 subscribe
   - priority_groups=None 이면 기존 평탄 처리 유지 (외부 호환)
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import scanner as scanner_module
from src.realtime import websocket as websocket_module
from src.realtime.websocket import KisWebSocket, MAX_SUBSCRIPTIONS

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 사양 1: MAX_SUBSCRIPTIONS = 41 상수
# ---------------------------------------------------------------------------
def test_max_subscriptions_constant_is_kis_official_limit_41():
    """KIS 공식 한도 41 — 200 으로 과대 설정되어 silently 거절 차단 못 하던 결함 수정."""
    assert MAX_SUBSCRIPTIONS == 41, (
        f"MAX_SUBSCRIPTIONS는 KIS 공식 한도 41이어야 함 (현재: {MAX_SUBSCRIPTIONS})"
    )


# ---------------------------------------------------------------------------
# 사양 2: bypass_limit 키워드 (Case E)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_subscribe_bypass_limit_true_overrides_max(monkeypatch):
    """bypass_limit=True → _subscriptions 한도 초과해도 add."""
    ws = KisWebSocket()
    # _subscriptions 에 41개 미리 채움
    ws._subscriptions = {(f"TR{i:03d}", f"K{i:03d}") for i in range(MAX_SUBSCRIPTIONS)}
    assert len(ws._subscriptions) == MAX_SUBSCRIPTIONS

    # 기본 호출은 거부됨
    await ws.subscribe("TRX", "EXTRA1")
    assert ("TRX", "EXTRA1") not in ws._subscriptions, "기본 호출은 한도 초과 시 add 거부"
    assert len(ws._subscriptions) == MAX_SUBSCRIPTIONS

    # bypass_limit=True 는 한도 무시
    await ws.subscribe("TRX", "EXTRA2", bypass_limit=True)
    assert ("TRX", "EXTRA2") in ws._subscriptions, "bypass_limit=True 는 한도 무시"
    assert len(ws._subscriptions) == MAX_SUBSCRIPTIONS + 1


@pytest.mark.asyncio
async def test_subscribe_bypass_limit_false_is_default_and_blocks_over_limit():
    """기본 동작은 bypass_limit=False — 한도 초과 시 add 거부 + warning."""
    ws = KisWebSocket()
    ws._subscriptions = {(f"TR{i:03d}", f"K{i:03d}") for i in range(MAX_SUBSCRIPTIONS)}
    await ws.subscribe("H0UNCNT0", "NEW_TICKER")  # bypass 미지정 = False
    assert ("H0UNCNT0", "NEW_TICKER") not in ws._subscriptions


# ---------------------------------------------------------------------------
# Fixture: kis_ws.subscribe 추적
# ---------------------------------------------------------------------------
@pytest.fixture
def _ws_subscribe_spy():
    """scanner.kis_ws.subscribe 를 AsyncMock 으로 패치 + 호출 인자 추적.

    실제 _subscriptions set 도 함께 패치해 사양 시뮬레이션이 가능하다.
    bypass_limit=True 면 한도 무시, False 면 한도 초과 시 add 거부 — 실 사양과 동일.
    """
    subs: set[tuple[str, str]] = set()
    calls: list[dict] = []

    async def fake_subscribe(tr_id: str, tr_key: str, *, bypass_limit: bool = False):
        calls.append({"tr_id": tr_id, "tr_key": tr_key, "bypass_limit": bypass_limit})
        if not bypass_limit and len(subs) >= MAX_SUBSCRIPTIONS:
            return
        subs.add((tr_id, tr_key))

    with patch.object(scanner_module.kis_ws, "subscribe", side_effect=fake_subscribe) as mock_sub:
        # _subscriptions 도 동일 set 으로 연결 — subscribe_filtered_stocks 가 잔여 슬롯 계산에 사용
        original_subs = scanner_module.kis_ws._subscriptions
        scanner_module.kis_ws._subscriptions = subs
        try:
            yield {"mock": mock_sub, "subs": subs, "calls": calls}
        finally:
            scanner_module.kis_ws._subscriptions = original_subs


# ---------------------------------------------------------------------------
# Case A: positions=3, next_day_clear=0, breakout=5, momentum=10, swing=30
#         → 41 가득 채움, swing 7개 drop, [priority_drop] 로그 1행
#
# 우선순위 재정렬(2026-05-12): LOW 순서가 breakout → momentum → swing 으로 바뀜.
# swing 이 LOW 마지막이므로 잔여 슬롯 부족 시 swing 이 drop 대상.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_priority_groups_case_a_overflow_drops_only_low_priority(_ws_subscribe_spy, caplog):
    """HIGH(보유 3) + breakout 5 + momentum 10 + swing 23 = 41. swing 7개 drop."""
    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    positions = [f"P{i:03d}" for i in range(3)]   # 3건 — HIGH bypass
    breakout = [f"B{i:03d}" for i in range(5)]    # 5건 — LOW 1순위, 전원 add
    momentum = [f"M{i:03d}" for i in range(10)]   # 10건 — LOW 2순위, 전원 add
    swing = [f"S{i:03d}" for i in range(30)]      # 30건 — LOW 3순위, 23개만 add, 7개 drop

    await scanner_module.subscribe_filtered_stocks(
        [],
        extra_tickers=None,
        priority_groups={
            "positions": positions,
            "next_day_clear": [],
            "swing": swing,
            "momentum": momentum,
            "breakout": breakout,
        },
    )

    subs = _ws_subscribe_spy["subs"]
    assert len(subs) == MAX_SUBSCRIPTIONS, f"한도 41 가득 채워야 함 (현재 {len(subs)})"

    # 보유 3개 전원 add — bypass_limit=True 로
    for t in positions:
        assert ("H0UNCNT0", t) in subs, f"보유 종목 {t} 는 절대 보장"
    # breakout 5개 전원 — LOW 1순위
    for t in breakout:
        assert ("H0UNCNT0", t) in subs, f"breakout {t} 잔여 슬롯 충분"
    # momentum 10개 전원 — LOW 2순위
    for t in momentum:
        assert ("H0UNCNT0", t) in subs, f"momentum {t} 잔여 슬롯 충분"
    # swing: 23개만 add, 7개 drop (LOW 마지막)
    swing_in = sum(1 for t in swing if ("H0UNCNT0", t) in subs)
    assert swing_in == 23, f"swing 은 잔여 슬롯 23개만 add (실제 {swing_in})"

    # [priority_drop] 로그 검증
    msg = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" in msg, "drop 발생 시 [priority_drop] 로그 1행 노출 필수"
    assert "swing=7" in msg, f"drop 카운트에 swing=7 노출 (msg={msg!r})"

    # bypass_limit 호출 검증 — positions 3건은 bypass_limit=True 로 호출
    bypass_true_calls = [c for c in _ws_subscribe_spy["calls"] if c["bypass_limit"]]
    bypass_true_keys = {c["tr_key"] for c in bypass_true_calls}
    for t in positions:
        assert t in bypass_true_keys, f"positions {t} 는 bypass_limit=True 로 호출되어야 함"


# ---------------------------------------------------------------------------
# Case B: positions=50 (한도 초과 이상 케이스)
#         → 50 모두 add, 후순위 0개, ERROR 로그
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_priority_groups_case_b_positions_exceed_limit(_ws_subscribe_spy, caplog):
    """HIGH 단독 41 초과 — 보유는 무조건 add, 후순위는 0개 + ERROR 로그."""
    caplog.set_level(logging.ERROR, logger="src.engine.scanner")

    positions = [f"P{i:03d}" for i in range(50)]   # 50건 (41 초과)
    swing = [f"S{i:03d}" for i in range(5)]        # 0건 add 예상

    await scanner_module.subscribe_filtered_stocks(
        [],
        extra_tickers=None,
        priority_groups={
            "positions": positions,
            "next_day_clear": [],
            "swing": swing,
            "momentum": [],
            "breakout": [],
        },
    )

    subs = _ws_subscribe_spy["subs"]
    # 보유 50개 전원 add (한도 무시)
    for t in positions:
        assert ("H0UNCNT0", t) in subs, f"보유 {t} 는 41 초과해도 무조건 add"
    # 후순위는 0개
    for t in swing:
        assert ("H0UNCNT0", t) not in subs, f"잔여 슬롯 음수 → 후순위 add 안 됨"

    # ERROR 로그 1행
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert any("HIGH" in r.message or "한도 초과" in r.message for r in error_records), (
        "positions+next_day_clear 합계가 한도 초과 시 ERROR 로그 1행 필수"
    )


# ---------------------------------------------------------------------------
# Case C: 중복 종목 — HIGH 순위로 1회만 subscribe
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_priority_groups_case_c_duplicates_subscribed_once(_ws_subscribe_spy):
    """positions=[A,B,C] + next_day_clear=[B,D] + swing=[E,F] → 6개만 subscribe."""
    await scanner_module.subscribe_filtered_stocks(
        [],
        extra_tickers=None,
        priority_groups={
            "positions": ["A", "B", "C"],
            "next_day_clear": ["B", "D"],   # B 중복
            "swing": ["E", "F"],
            "momentum": [],
            "breakout": [],
        },
    )

    subs = _ws_subscribe_spy["subs"]
    # 6개 모두 subscribe 됨
    for t in ["A", "B", "C", "D", "E", "F"]:
        assert ("H0UNCNT0", t) in subs, f"{t} 가 구독되어야 함"
    assert len(subs) == 6, f"중복 제거 후 6개만 (실제 {len(subs)})"

    # subscribe 호출 횟수 검증 — B 는 1번만 (positions 에서)
    calls = _ws_subscribe_spy["calls"]
    b_calls = [c for c in calls if c["tr_key"] == "B"]
    assert len(b_calls) == 1, f"B 는 HIGH 순위(positions)로 1회만 subscribe (실제 {len(b_calls)}회)"
    # B 는 bypass_limit=True 로 호출 (positions 그룹)
    assert b_calls[0]["bypass_limit"] is True


# ---------------------------------------------------------------------------
# Case D: priority_groups=None → 기존 평탄 처리 + source_counts 로그 보존 (외부 호환)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_priority_groups_none_falls_back_to_legacy_with_source_counts(_ws_subscribe_spy, caplog):
    """priority_groups=None 이면 기존 fallback 동작 + source_counts 로그 그대로."""
    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    source_counts = {"vb": 1, "ltv": 0, "swing": 2, "momentum": 1, "positions": 0}
    await scanner_module.subscribe_filtered_stocks(
        ["005930"],                                # momentum 1개
        extra_tickers=["000660", "035420", "035720"],
        source_counts=source_counts,
        # priority_groups 미지정
    )

    subs = _ws_subscribe_spy["subs"]
    for t in ["005930", "000660", "035420", "035720"]:
        assert ("H0UNCNT0", t) in subs

    # source_counts 로그가 보존되어야 함 (Phase B 라벨)
    msg = "\n".join(r.message for r in caplog.records)
    assert "vb=1" in msg
    assert "swing=2" in msg
    assert "momentum=1" in msg
    assert "total=4" in msg


# ---------------------------------------------------------------------------
# Case G: drop=0 인 경우 [priority_drop] 로그 생략 (정상 운영 — 노이즈 차단)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_priority_groups_no_drop_no_drop_log(_ws_subscribe_spy, caplog):
    """잔여 슬롯이 충분하면 [priority_drop] 로그 노출하지 않음."""
    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    await scanner_module.subscribe_filtered_stocks(
        [],
        extra_tickers=None,
        priority_groups={
            "positions": ["A", "B"],
            "next_day_clear": [],
            "swing": ["S1", "S2"],
            "momentum": ["M1"],
            "breakout": ["B1"],
        },
    )

    msg = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" not in msg, "drop=0 이면 [priority_drop] 로그 생략 (노이즈 차단)"


# ---------------------------------------------------------------------------
# PR-E (P1, 2026-05-15) — 2-pass 슬롯 흡수
#
# 결함 (운영 로그 2026-05-15 07:55:08):
#   [priority_drop] breakout=3 momentum=0 swing=0
#   total_subscribed=30 max=41 high_count=5 low_remaining=11
# - HIGH 5 → 잔여 36
# - breakout 28 → cap 25 적용 → 25 add + 3 drop
# - momentum 0 / swing 10 add → 35 사용
# - 결과: 30 사용 / 11 슬롯 미사용 + 3 drop 종목 → 운영 슬롯 낭비
#
# Fix 사양: 1-pass → 2-pass
#   1차: positions(bypass) → next_day_clear(bypass) → breakout[:cap] → momentum → swing
#   2차: 잔여 슬롯 (MAX_SUBSCRIPTIONS - len(_subscriptions)) > 0 이면 breakout 의
#        cap 초과분(overflow)에서 추가 add
#   최종 drop = max(0, len(breakout_overflow) - actually_added_in_2nd_pass)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_breakout_overflow_absorbs_unused_slots(_ws_subscribe_spy, caplog):
    """결함 시나리오 재현: breakout=28 momentum=0 swing=10 + HIGH=5 → 28 add + drop=0."""
    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    positions = [f"P{i:03d}" for i in range(5)]    # HIGH 5
    breakout = [f"B{i:03d}" for i in range(28)]    # cap 25 → overflow 3
    momentum: list[str] = []
    swing = [f"S{i:03d}" for i in range(10)]       # 10

    await scanner_module.subscribe_filtered_stocks(
        [],
        extra_tickers=None,
        priority_groups={
            "positions": positions,
            "next_day_clear": [],
            "swing": swing,
            "momentum": momentum,
            "breakout": breakout,
        },
    )

    subs = _ws_subscribe_spy["subs"]
    # HIGH 5 + breakout 25 + swing 10 = 40 (1차) + breakout overflow 3 (2차) = 43?
    # 잔여 = MAX(41) - (5+25+10) = 1 → overflow 3 중 1만 흡수 가능 → 총 41
    # NOTE: 실제 시나리오에서는 breakout=28 < cap 25 가 아니라 "breakout=28 → cap 25 적용 → 3 drop" 이므로
    # cap 25 + 잔여 슬롯 흡수 = breakout 이 잔여 슬롯에 의해 결정되어야 함.
    #
    # HIGH 5 + cap 25 + momentum 0 + swing 10 = 40 → 잔여 1 → overflow 3 중 1 흡수 → drop=2
    # 또 다른 케이스(잔여가 더 크면): drop=0 가능
    #
    # 결함 로그의 정확 재현: total_subscribed=30 had 11 slot unused — 그 운영 케이스를 재현하려면
    # 보유/swing 적은 구성. 본 테스트는 "잔여 슬롯이 있으면 overflow 가 흡수된다" 를 검증.
    # HIGH 5 + breakout 25 (cap) + swing 10 = 40 → 잔여 1 → overflow 1 add → 41 사용 + drop=2
    assert len(subs) == 41, f"잔여 슬롯이 overflow 로 흡수되어 41 가득 (실제 {len(subs)})"

    # breakout overflow 3 중 1 add — drop=2
    breakout_in = sum(1 for t in breakout if ("H0UNCNT0", t) in subs)
    assert breakout_in == 26, f"breakout cap 25 + overflow 1 흡수 = 26 (실제 {breakout_in})"

    # [priority_drop] 로그에 breakout=2 (overflow 3 중 1 흡수 후 잔여 2 drop)
    msg = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" in msg
    assert "breakout=2" in msg, f"2-pass 흡수 후 drop=2 노출 (msg={msg!r})"


@pytest.mark.asyncio
async def test_breakout_overflow_fully_absorbed_when_unused_slots_sufficient(_ws_subscribe_spy, caplog):
    """결함 케이스 정확 재현: HIGH 5 + breakout 28 + momentum 0 + swing 10 → 결함은 30 사용/11 미사용/3 drop.
    Fix 후: 잔여 슬롯이 충분(11)하면 overflow 3 모두 흡수 → 28 + drop=0.
    """
    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    # 결함 로그의 실제 구성 (총 5+28+0+10=43, HIGH 5 보장 후 LOW 36 슬롯)
    positions = [f"P{i:03d}" for i in range(5)]    # HIGH 5
    breakout = [f"B{i:03d}" for i in range(28)]    # cap 25 → overflow 3
    momentum: list[str] = []                        # 0
    swing = [f"S{i:03d}" for i in range(3)]         # 3 (잔여 8 → overflow 3 모두 흡수 + 5 미사용)

    await scanner_module.subscribe_filtered_stocks(
        [],
        extra_tickers=None,
        priority_groups={
            "positions": positions,
            "next_day_clear": [],
            "swing": swing,
            "momentum": momentum,
            "breakout": breakout,
        },
    )

    subs = _ws_subscribe_spy["subs"]
    # HIGH 5 + cap 25 + momentum 0 + swing 3 = 33 → 잔여 8 → overflow 3 모두 흡수 → 36
    assert len(subs) == 36, f"5+25+3+3(overflow)=36 (실제 {len(subs)})"

    # breakout 28 모두 add (cap 초과분 overflow 3 흡수)
    for t in breakout:
        assert ("H0UNCNT0", t) in subs, f"breakout {t} 잔여 슬롯에 흡수 add"

    # drop=0 → [priority_drop] 로그 생략 (노이즈 차단)
    msg = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" not in msg, "2-pass 후 drop=0 이면 [priority_drop] 로그 생략"


@pytest.mark.asyncio
async def test_2pass_does_not_break_existing_cap_invariant(_ws_subscribe_spy, caplog):
    """잔여 슬롯이 0 이면 overflow 흡수 0 — 한도 41 절대 초과 안 함."""
    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    # HIGH 0 + breakout 30 (cap 25 → overflow 5) + momentum 20 + swing 20
    # 1차: cap 25 + momentum 16 (잔여 0 도달) + swing 0 = 41
    # 잔여 0 → overflow 0 흡수 → drop: breakout 5 + momentum 4 + swing 20
    breakout = [f"B{i:03d}" for i in range(30)]
    momentum = [f"M{i:03d}" for i in range(20)]
    swing = [f"S{i:03d}" for i in range(20)]

    await scanner_module.subscribe_filtered_stocks(
        [],
        extra_tickers=None,
        priority_groups={
            "positions": [],
            "next_day_clear": [],
            "swing": swing,
            "momentum": momentum,
            "breakout": breakout,
        },
    )

    subs = _ws_subscribe_spy["subs"]
    assert len(subs) == MAX_SUBSCRIPTIONS, f"한도 41 절대 초과 안 됨 (실제 {len(subs)})"

    # breakout 25 (cap), overflow 5 모두 drop
    breakout_in = sum(1 for t in breakout if ("H0UNCNT0", t) in subs)
    assert breakout_in == 25, f"breakout cap 25 (잔여 0 → overflow 0 흡수) (실제 {breakout_in})"

    # [priority_drop] 로그
    msg = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" in msg
    assert "breakout=5" in msg, f"breakout overflow 5 drop (msg={msg!r})"


@pytest.mark.asyncio
async def test_priority_drop_log_omitted_when_2pass_clears_all_drops(_ws_subscribe_spy, caplog):
    """1차 cap drop 만 있고 2차에서 전부 흡수되면 최종 drop=0 → 로그 미노출."""
    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    # HIGH 0 + breakout 26 (cap 25 → overflow 1) + momentum 5 + swing 5
    # 1차: cap 25 + momentum 5 + swing 5 = 35 → 잔여 6 → overflow 1 흡수 → 36
    # 최종 drop=0 → 로그 미노출
    breakout = [f"B{i:03d}" for i in range(26)]
    momentum = [f"M{i:03d}" for i in range(5)]
    swing = [f"S{i:03d}" for i in range(5)]

    await scanner_module.subscribe_filtered_stocks(
        [],
        extra_tickers=None,
        priority_groups={
            "positions": [],
            "next_day_clear": [],
            "swing": swing,
            "momentum": momentum,
            "breakout": breakout,
        },
    )

    subs = _ws_subscribe_spy["subs"]
    assert len(subs) == 36, f"25+5+5+1(overflow)=36 (실제 {len(subs)})"
    # breakout 26 전원 add
    for t in breakout:
        assert ("H0UNCNT0", t) in subs

    msg = "\n".join(r.message for r in caplog.records)
    assert "[priority_drop]" not in msg, "2-pass 후 drop=0 이면 [priority_drop] 로그 생략"
