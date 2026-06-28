"""사이클 184 (2026-06-28) Red — stale-2: 2-pass 슬롯 계산 풀 총용량 정합.

> **선행 명세**: `_workspace/red/cycle184_pool_union_slots.md`
> 대상: `src/engine/scanner.py::subscribe_filtered_stocks` 단독. realtime/ 변경 0.
> production 미변경 (Green = backend-dev).

## 결함 (stale-2, MEDIUM — 보조 세션 존재 시 슬롯 오산)

`subscribe_filtered_stocks` 의 LOW 후보 2-pass 슬롯 계산 2곳:
- L1118 (1차 LOW 루프): `remaining = MAX_SUBSCRIPTIONS - len(kis_ws._subscriptions)`
- L1146 (2차 overflow 흡수 루프): `remaining = MAX_SUBSCRIPTIONS - len(kis_ws._subscriptions)`

`kis_ws._subscriptions` = **메인 세션 단독** 구독 set. 풀(`kis_ws_pool`)이 LOW 후보를
보조 세션에 라운드로빈 분배(`subscribe(bypass_limit=False)`)하면 메인 카운트는 안 늘어
`remaining = 41 - len(main)` 과대/과소 → 메인 full + 보조 여유 시 `remaining=0` → 과다 drop
(보조 슬롯 41×N 유휴인데도 LOW 후보 silent drop). 풀 총용량 = `MAX_SUBSCRIPTIONS × (1+보조수)`.

## 확정 시정 설계 (Green 목표 — scanner.py 단독, realtime/ 미변경)

```python
# 2-pass 루프 진입 *전* 1회 계산 (세션 수 루프 중 불변):
_pool_session_count = len(kis_ws_pool.get_session_status())   # main + 보조 N = 1+N
_pool_total_slots = MAX_SUBSCRIPTIONS * _pool_session_count
# 각 사이트(L1118/L1146):
remaining = _pool_total_slots - len(kis_ws_pool._subscriptions)   # 풀 union(전 tr_id)
```

`kis_ws_pool._subscriptions` = 메인+보조 전 세션 합집합 property (websocket_pool.py:564, 모든 tr_id).
**보조 0개(n=1) 시 `_pool_total_slots=41` + `kis_ws_pool._subscriptions`==메인 단독 → 현 동작 완전 동일 (회귀 0)**.

## 가드 구성 (7 케이스 = FAIL 2 + PASS 보존 5)

- REGRESS-1/2/3 (보조 0/0/1 + ample): drop/absorb 결과가 현재(메인 단독)와 동일 → **PASS 보존**
  (Green 전후 불변 = 회귀 0 입증)
- ACCURACY-1/2 (보조 ≥1 + 메인 full): 현재 `remaining=0` 과다 drop → Green 풀 총용량 흡수 → **FAIL (Red)**
- SAFETY-HIGH-1/2: positions/next_day_clear `bypass_limit=True` → 슬롯 계산 무관 절대 보장 → **PASS 보존**
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 합성 환경 — MockPool(get_session_status 1+N + _subscriptions union) + MockWs(main solo)
# ---------------------------------------------------------------------------
def _pair(i: int) -> tuple[str, str]:
    """더미 TICK 구독 페어 (tr_id, tr_key). 슬롯 계산은 len 만 사용."""
    from src.engine.scanner import TICK_TR_ID
    return (TICK_TR_ID, f"DUMMY{i:05d}")


def _build_env(
    *,
    main_count: int,
    aux_counts: list[int],
    already_in_pool: set[str] | None = None,
):
    """메인 단독/풀 union 양쪽 정합 합성 환경.

    - main_ws._subscriptions = main_count 더미 페어 (현재 코드 읽음)
    - pool._subscriptions = 메인 ∪ 보조 합집합 set (Green 코드 읽음)
    - pool.get_session_status() = [main] + 보조 N = len 1+N (Green 총용량 산정)
    - pool.subscribe = 호출 기록 fake (메인/보조 분배 무관 — 슬롯 계산만 검증)

    합성 정합 의무 (사이클 184 명세): get_session_status len(1+N) ↔ _subscriptions union ↔
    main_ws._subscriptions(메인 단독) 세 값 모순 없게 구성.
    """
    main_set = {_pair(i) for i in range(main_count)}
    main_ws = types.SimpleNamespace(_subscriptions=set(main_set))

    union: set[tuple[str, str]] = set(main_set)
    aux_sessions = []
    cursor = main_count
    for cnt in aux_counts:
        s = {_pair(cursor + j) for j in range(cnt)}
        cursor += cnt
        union |= s
        aux_sessions.append(types.SimpleNamespace(_subscriptions=set(s)))

    calls: list[dict] = []

    async def fake_subscribe(tr_id, tr_key, *, priority="LOW", bypass_limit=False):
        calls.append({
            "tr_id": tr_id, "tr_key": tr_key,
            "priority": priority, "bypass_limit": bypass_limit,
        })
        return "main" if priority == "HIGH" else "quote-1"

    session_status = [{"label": "main"}] + [
        {"label": f"quote-{i + 1}"} for i in range(len(aux_counts))
    ]

    pool = types.SimpleNamespace(
        _main=main_ws,
        _quotes=aux_sessions,
        _subscriptions=union,
        subscribe=fake_subscribe,
        get_subscribed_tickers=lambda: set(already_in_pool or set()),
        get_session_status=lambda: list(session_status),
    )
    return main_ws, pool, calls


async def _passthrough(candidates, **kwargs):
    """가격/거래대금 필터 passthrough — 슬롯 계산만 격리."""
    return list(candidates)


async def _run(priority_groups: dict, *, main_count: int, aux_counts: list[int]):
    """subscribe_filtered_stocks 를 합성 환경에서 실행하고 subscribe 호출 목록 반환."""
    from src.engine import scanner

    main_ws, pool, calls = _build_env(main_count=main_count, aux_counts=aux_counts)

    with patch("src.engine.scanner.kis_ws", main_ws), \
         patch("src.engine.scanner.kis_ws_pool", pool), \
         patch("src.engine.scanner._collect_protected_tickers_for_scanner",
               MagicMock(return_value=set())), \
         patch("src.engine.scanner._record_scan_pool_candidates", MagicMock()), \
         patch("src.engine.scanner._apply_price_filter", new=_passthrough), \
         patch("src.engine.scanner._apply_trade_amount_filter", new=_passthrough), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        await scanner.subscribe_filtered_stocks(
            tickers=[], extra_tickers=[], priority_groups=priority_groups,
        )
    return calls


def _low_subs(calls: list[dict], tickers: set[str]) -> list[dict]:
    return [c for c in calls if c["priority"] == "LOW" and c["tr_key"] in tickers]


def _high_subs(calls: list[dict]) -> list[dict]:
    return [c for c in calls if c["priority"] == "HIGH"]


def _pg(**kw) -> dict:
    base = {"positions": [], "next_day_clear": [], "breakout": [],
            "momentum": [], "swing": []}
    base.update(kw)
    return base


# ===========================================================================
# REGRESS-1 (보조 0개, 메인 full → 전량 drop) — PASS 보존 (현재 ≡ Green)
# ===========================================================================
@pytest.mark.asyncio
async def test_REGRESS1_aux0_main_full_drops_all_identical():
    """보조 0개 + 메인 full(41) → LOW 후보 전량 drop. 현재 = Green 동일.

    현재: `remaining = 41 - 41 = 0` → 전량 drop.
    Green(보조 0): `_pool_total_slots = 41×1 = 41`, union=41 → `remaining = 0` → 전량 drop.
    → 회귀 0 핵심 가드 (Green 전후 불변, 현재 코드도 PASS).
    """
    breakout = [f"B{i:04d}" for i in range(5)]
    calls = await _run(_pg(breakout=breakout), main_count=41, aux_counts=[])

    assert len(_low_subs(calls, set(breakout))) == 0, (
        "REGRESS-1 회귀 — 보조 0 + 메인 full 에서 LOW 후보는 전량 drop 이어야 함 "
        f"(현재 ≡ Green). 실제 구독 {len(_low_subs(calls, set(breakout)))}건."
    )


# ===========================================================================
# REGRESS-2 (보조 0개, 메인 여유 → 전량 흡수) — PASS 보존
# ===========================================================================
@pytest.mark.asyncio
async def test_REGRESS2_aux0_main_room_absorbs_all_identical():
    """보조 0개 + 메인 여유(10/41) → LOW 후보 전량 흡수. 현재 = Green 동일.

    현재: `remaining = 41 - 10 = 31 > 0` → 전량 add.
    Green: `_pool_total_slots = 41`, union=10 → `remaining = 31` → 전량 add. 동일.
    """
    breakout = [f"B{i:04d}" for i in range(5)]
    calls = await _run(_pg(breakout=breakout), main_count=10, aux_counts=[])

    subs = _low_subs(calls, set(breakout))
    assert len(subs) == 5, (
        "REGRESS-2 회귀 — 보조 0 + 메인 여유 에서 LOW 후보 5건 전량 구독 의무 "
        f"(현재 ≡ Green). 실제 {len(subs)}건."
    )
    for c in subs:
        assert c["bypass_limit"] is False, (
            f"LOW 후보는 bypass_limit=False (실제 {c})."
        )


# ===========================================================================
# REGRESS-3 (보조 1개, 메인·풀 모두 여유 → 전량 흡수) — PASS 보존
# ===========================================================================
@pytest.mark.asyncio
async def test_REGRESS3_aux1_ample_room_absorbs_all_identical():
    """보조 1개 + 메인 여유(20/41) + 풀 여유 → LOW 후보 전량 흡수. 현재 = Green 동일.

    슬롯 여유가 충분하면 보조 세션 존재 자체가 결과를 바꾸지 않음 (결함은 메인 full 경계에서만 발현).
    현재: `remaining = 41 - 20 = 21 > 0` → 전량 add.
    Green: `_pool_total_slots = 41×2 = 82`, union=20 → `remaining = 62` → 전량 add. 동일.
    """
    breakout = [f"B{i:04d}" for i in range(5)]
    calls = await _run(_pg(breakout=breakout), main_count=20, aux_counts=[0])

    subs = _low_subs(calls, set(breakout))
    assert len(subs) == 5, (
        "REGRESS-3 회귀 — 보조 1 + 풀 여유 에서 LOW 후보 5건 전량 구독 의무 "
        f"(현재 ≡ Green, 여유 충분 시 보조 존재 무영향). 실제 {len(subs)}건."
    )


# ===========================================================================
# ACCURACY-1 (보조 1개, 메인 full + 보조 유휴) → FAIL (Red)
# ===========================================================================
@pytest.mark.asyncio
async def test_ACCURACY1_aux1_main_full_absorbs_into_aux_slots():
    """보조 1개 + 메인 full(41) + 보조 유휴 → LOW 후보를 풀 잔여 슬롯에 흡수해야 함.

    풀 총용량 = 41×2 = 82, union = 41 → 잔여 41 슬롯.
    - 현재(메인 단독): `remaining = 41 - 41 = 0` → 10건 전량 **과다 drop** → 구독 0건 → FAIL.
    - Green(풀 총용량): `remaining = 82 - 41 = 41 > 0` → 10건 전량 흡수 → 구독 10건 → PASS.
    """
    breakout = [f"B{i:04d}" for i in range(10)]
    calls = await _run(_pg(breakout=breakout), main_count=41, aux_counts=[0])

    subs = _low_subs(calls, set(breakout))
    assert len(subs) == 10, (
        "ACCURACY-1 (Red) — 메인 full + 보조 41슬롯 유휴인데 LOW 후보 과다 drop. "
        f"풀 총용량(82) 기준 잔여 41 슬롯에 10건 전량 흡수 의무 (실제 구독 {len(subs)}건). "
        "현재 `remaining = 41 - len(kis_ws._subscriptions)`(메인 단독) → remaining=0 과다 drop."
    )


# ===========================================================================
# ACCURACY-2 (보조 2개, 1개 full + 1개 유휴, 메인 full) → FAIL (Red)
# ===========================================================================
@pytest.mark.asyncio
async def test_ACCURACY2_aux2_one_full_one_idle_uses_pool_union_total():
    """보조 2개(1 full + 1 유휴) + 메인 full → 풀 union/총용량으로 유휴 슬롯 인식.

    풀 총용량 = 41×3 = 123, union = 41(main) + 41(aux1) = 82 → 잔여 41.
    - 현재: `remaining = 41 - 41 = 0` → 8건 전량 drop → FAIL.
    - Green: `remaining = 123 - 82 = 41 > 0` → 8건 전량 흡수 → PASS.
    (union=82 > 메인 단독 41 → 풀 union property(`_subscriptions`) 사용 입증.)
    """
    breakout = [f"B{i:04d}" for i in range(8)]
    calls = await _run(_pg(breakout=breakout), main_count=41, aux_counts=[41, 0])

    subs = _low_subs(calls, set(breakout))
    assert len(subs) == 8, (
        "ACCURACY-2 (Red) — 보조 2개(1 full + 1 유휴) 풀 총용량 123/union 82 기준 "
        f"잔여 41 슬롯에 8건 전량 흡수 의무 (실제 구독 {len(subs)}건). "
        "현재 메인 단독 41 → remaining=0 과다 drop."
    )


# ===========================================================================
# SAFETY-HIGH-1 (HIGH bypass 불변) — PASS 보존 (사이클 32 R4)
# ===========================================================================
@pytest.mark.asyncio
async def test_SAFETY_HIGH1_positions_ndc_always_subscribed_bypass():
    """메인 full(41) + 보조 0 이어도 positions/next_day_clear 는 `bypass_limit=True` 절대 구독.

    HIGH 경로(L1060~1074)는 슬롯 계산(`remaining`) *전* 무조건 subscribe → 시정 전후 불변.
    슬롯 계산 변경이 HIGH 경로에 영향 0 (사이클 32 R4 보유/익일청산 절대 보호).
    """
    calls = await _run(
        _pg(positions=["253840", "142280"], next_day_clear=["066430"]),
        main_count=41, aux_counts=[],
    )

    high = _high_subs(calls)
    high_keys = {c["tr_key"] for c in high}
    assert high_keys == {"253840", "142280", "066430"}, (
        f"SAFETY-HIGH-1 — HIGH(positions+next_day_clear) 3건 모두 구독 의무 (실제 {high_keys})."
    )
    for c in high:
        assert c["bypass_limit"] is True, (
            f"SAFETY-HIGH-1 — HIGH 는 bypass_limit=True 절대 보장 (실제 {c})."
        )


# ===========================================================================
# SAFETY-HIGH-2 (슬롯 압박 무관 HIGH 보장) — PASS 보존
# ===========================================================================
@pytest.mark.asyncio
async def test_SAFETY_HIGH2_high_independent_of_low_slot_calc():
    """메인 full + positions(2) + breakout(5) 혼재 → HIGH 2건은 슬롯 계산 결과와 무관하게 보장.

    breakout drop/absorb 결과(현재 vs Green)는 달라져도 HIGH 2건은 항상 bypass=True 구독.
    슬롯 계산이 HIGH 경로를 침범하지 않음을 단언 (현재/Green 모두 PASS).
    """
    breakout = [f"B{i:04d}" for i in range(5)]
    calls = await _run(
        _pg(positions=["005930", "000660"], breakout=breakout),
        main_count=41, aux_counts=[0],
    )

    high = _high_subs(calls)
    assert {c["tr_key"] for c in high} == {"005930", "000660"}, (
        f"SAFETY-HIGH-2 — positions 2건 항상 HIGH 구독 (실제 {[c['tr_key'] for c in high]})."
    )
    for c in high:
        assert c["bypass_limit"] is True, (
            f"SAFETY-HIGH-2 — HIGH bypass_limit=True 불변 (실제 {c})."
        )
