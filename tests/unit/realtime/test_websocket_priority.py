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
