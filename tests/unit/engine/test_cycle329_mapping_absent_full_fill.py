"""cycle329 — `await place_order` 도중 착지한 부분 체결이 **전량으로 오판된다**.

자문 = `_workspace/domain_consult/cycle329_mapping_absent_full_fill.md`
발견 = `_workspace/refactor/2026-09-20_step1_gate_domain.md` 5절 (cycle328 관문 리뷰)

## 사슬

`order_no` 는 KIS 응답이 와야 알 수 있다 — 구조적으로 앞당길 수 없다. 그래서
`await place_order` 가 걸려 있는 동안 주문번호 매핑 5종이 **전부 비어 있다**.

```
execute_sell   pos = state.positions.get(ticker)        (보유 10주)
               result = await place_order(quantity=10)
                 ◀ 이 창에 부분 체결통보(3주) 착지
handle_execution_notice   known_ordered = order_no in _order_qty        → False
                          ordered_qty = _order_qty.get(order_no, quantity) → 🔴 3
                          total_filled = 3
_handle_sell_fill         if total_filled >= ordered_qty:  3 >= 3       → 🔴 전량 판정
               _order_qty[result.order_no] = 10           ← 뒤늦게(무의미)
```

`ordered_qty` 가 「주문 수량」이 아니라 **「이번 통보의 증분 체결량」**으로 폴백되므로,
첫 부분 체결은 **항상** `total_filled == ordered_qty` 가 되어 전량으로 읽힌다.

## 피해 — 축마다 다르고 매수가 더 나쁘다

**매도** = `del state.positions[ticker]` + `delete_position` + `sold_today.add`.
미체결 잔량이 **손절 감시 밖으로 사라진다**(`risk.on_tick` 은 `positions` 만 순회).
`_sync_positions_from_balance`(15분)가 되살리지만 그동안 손절이 없다.

**매수** = `Position(quantity=3)` 으로 등록 + `_completed_buy_orders` 무장 →
잔여 7주 통보가 `[buy_fill_duplicate_ignored]` 로 **조용히 버려진다**. 그리고
`_sync_positions_from_balance` 는 `is_ticker_held_by_any` → `continue` 라
**기보유 수량을 영원히 고치지 않는다**. 10주를 갖고 3주로 믿는 상태가 익일 부팅까지 간다.

## 실측 (2026-09-20)

`system_logs` 의 `"종목 매핑 없음"` WARNING = 보존 구간(08-19~09-20) **2건**,
KST **14:44(KRX 정규장)** · **08:13(NXT 프리장)** — 둘 다 **장중**이다.
⚠️ 초판 측정은 psql 세션 TimeZone 이 UTC 인데 `to_char(ts,'…+09:00')` 이 변환 없이
문자열만 붙여 「엔진 창 밖」으로 잘못 읽었다. 두 건은 `[buy_fill_fallback_held_conflict]`
조기 return 에 먹혀 **수량 판정에 도달 전**이라, 「0건 관측」이 아니라 **미관측**이다.

## 시정 = KIS 가 이미 실어 보내는 주문수량을 쓴다 (사용자 결정 2026-09-20)

체결통보 payload `fields[16] ODER_QTY` 가 **주문수량**이다. `handler.py` 가 그것을
꺼내 `ordered_qty_payload` 로 넘기면 매핑 부재 창에서도 정확한 값을 얻는다.

우선순위 3단 — `map`(우리 주문·매핑 확정) → `payload`(KIS 가 준 값) → `increment`(둘 다
없을 때의 **현행 폴백 그대로**).

🔴 **전량 판정에 출처 게이트를 걸지 않는다.** 「`increment` 면 전량으로 확정하지 않는다」를
한 번 넣었다가 뺐다 — payload 가 있으면 수동 주문도 정확해지므로 그 게이트는 불필요하고,
payload 가 없는 퇴화 상황에서 그것을 걸면 **수동 전량 매도가 유보되어 포지션 유령 잔존 +
`_selling` 좀비**(= 손절 마비)가 된다. 자문이 B′안을 배제한 이유가 그것이다.

🔴 **재주문 타이머는 `qty_src == "map"` 일 때만 건다.** 이 시정으로 매핑 부재 창의 통보가
처음으로 **부분 분기에 도달**하는데, `_cancel_and_reorder` 에는 포지션 재조회가 한 줄도
없어 30초 뒤 신규 매도를 발사한다. `payload` 에는 수동 주문도 포함되므로 게이트가 없으면
**사람이 낸 주문을 우리가 취소하고 다시 낸다.**

🔴 **`fields[16]` 은 cycle235 가 한 번 오독해 사고(257720)를 낸 자리다.** 그래서 매핑이 선
정상 통보마다 `[ordered_qty_mismatch]` 로 교차검증한다 — 배정이 틀리면 매핑 부재 창을
기다리지 않고 즉시 드러난다.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

TICKER = "005930"
PRICE = 70_000
HELD_QTY = 10
PARTIAL_QTY = 3


def _make_env(monkeypatch):
    """매도 발사 도중 부분 체결통보가 끼어드는 환경."""
    from src.models.order import OrderResult
    from src.engine import scanner
    from src.engine.order_engine import OrderEngine
    from src.engine.session import MarketBoard, session_tracker
    from src.engine.strategies.momentum import MomentumStrategy
    from src.engine.strategy_base import Position, StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    monkeypatch.setattr(scanner, "ticker_names", {TICKER: "테스트종목"}, raising=False)
    monkeypatch.setattr(scanner, "ticker_prev_close", {TICKER: PRICE}, raising=False)
    monkeypatch.setattr(scanner, "ticker_prices", {TICKER: {"current_price": PRICE}},
                        raising=False)
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))

    registry = StrategyRegistry()
    strat = MomentumStrategy(
        StrategyConfig(strategy_id="momentum", name="모멘텀", weight=1.0,
                       params={"exchange": "KRX"})
    )
    registry.register(strat)
    registry.allocate_funds(total_asset=100_000_000)
    engine = OrderEngine(registry)

    strat.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=PRICE, quantity=HELD_QTY,
        order_no="BUY-1", strategy_id="momentum", buy_date=date(2026, 9, 19),
    )

    calls = SimpleNamespace(place_order=[], notices=[])

    async def fake_place_order(ticker, side, quantity, price=0, **kwargs):
        calls.place_order.append({"side": str(side), "quantity": quantity})
        order_no = f"SELL-{len(calls.place_order):06d}"
        # 🔴 이 `await` 가 걸려 있는 동안 체결통보가 착지한다 —
        #    그 순간 `_order_qty[order_no]` 는 아직 비어 있다(아래 return 뒤에 등록된다).
        await engine.handle_execution_notice(
            order_no=order_no, ticker=TICKER, side="SELL",
            quantity=PARTIAL_QTY, price=PRICE,
            # KIS 가 실어 보내는 ODER_QTY(주문수량). `handler.py` 가 fields[16] 에서
            # 꺼내 넘긴다 — 매핑 부재 창에서 주문수량을 아는 유일한 경로다.
            ordered_qty_payload=HELD_QTY,
        )
        calls.notices.append(order_no)
        return OrderResult(order_no=order_no, order_time="090501", krx_org_no="00950")

    async def noop(*a, **k):
        return None

    async def fake_update_status(*a, **k):
        return 1

    monkeypatch.setattr("src.engine.order_engine.place_order", fake_place_order)
    monkeypatch.setattr("src.engine.order_engine.insert_trade", noop)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", fake_update_status)
    monkeypatch.setattr("src.engine.order_engine.write_log", noop)

    import src.db.positions as positions_mod
    monkeypatch.setattr(positions_mod, "delete_position", noop, raising=False)
    monkeypatch.setattr(positions_mod, "save_position", noop, raising=False)

    return SimpleNamespace(engine=engine, registry=registry, strategy=strat, calls=calls)


@pytest.mark.asyncio
async def test_partial_fill_during_place_order_does_not_delete_position(monkeypatch):
    """🔴 발사 창에 착지한 **부분** 체결이 포지션을 지우지 않는다.

    이것이 이 사이클의 계약이다. 지금은 깨져 있다 — `ordered_qty` 가 증분값(3)으로
    폴백돼 `3 >= 3` 이 참이 되고 전량 분기가 `del state.positions[ticker]` 한다.

    잃는 것은 **미체결 잔량 7주의 손절 커버리지**다(`risk.on_tick` 은 `positions` 만 순회).
    """
    from src.engine.strategy_base import Signal

    env = _make_env(monkeypatch)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "momentum")

    pos = env.strategy.state.positions.get(TICKER)
    assert pos is not None, (
        f"부분 체결({PARTIAL_QTY}주)인데 포지션이 삭제됐다 — 전량으로 오판했다.\n"
        f"  미체결 잔량 {HELD_QTY - PARTIAL_QTY}주가 손절 감시 밖으로 사라진다.\n"
        f"  원인: `_order_qty` 가 아직 비어 있어 ordered_qty 가 증분값 {PARTIAL_QTY} 로 폴백."
    )


@pytest.mark.asyncio
async def test_manual_order_notice_keeps_current_fallback(monkeypatch):
    """🔴 수동 매매·외부 주문의 전량 통보는 **현행대로 포지션을 정리한다**.

    이 테스트가 없으면 「우리 주문 보호」가 조용히 「모든 주문 유보」로 번져도 아무도
    모른다. 유보되면 포지션 유령 잔존 + `_selling` 좀비 = **손절 마비**다
    (`selling_reconcile` 의 `held_zero` 는 해제가 아니라 **유지** 분기다).

    자문이 B′안(「`known_ordered == False` 면 부분으로만 처리」)을 배제한 이유가
    정확히 이것이고, 그 계약을 여기서 봉한다.
    """
    env = _make_env(monkeypatch)

    # 우리가 발사한 적 없는 주문번호 — `_order_qty` miss, payload 는 KIS 가 준다
    await env.engine.handle_execution_notice(
        order_no="MANUAL-999999", ticker=TICKER, side="SELL",
        quantity=HELD_QTY, price=PRICE,
        ordered_qty_payload=HELD_QTY,   # 수동 주문도 KIS 는 주문수량을 실어 준다
    )

    # 현행 계약 = 전량 폴백으로 처리돼 포지션이 정리된다(수동 전량 매도의 정상 동작)
    assert TICKER not in env.strategy.state.positions, (
        "수동 매매 전량 통보인데 포지션이 남았다 — 「우리 주문 보호」가 "
        "수동 주문까지 유보시켰다. 그러면 포지션 유령 잔존 + _selling 좀비가 된다"
    )


@pytest.mark.asyncio
async def test_missing_payload_qty_keeps_legacy_fallback(monkeypatch):
    """🔴 payload 주문수량이 **없을 때**는 현행 폴백(`increment`)을 그대로 탄다.

    `fields[16]` 이 비거나 파싱에 실패하는 퇴화 상황이다. 그때 행위를 바꾸면
    (예: 전량 판정 유보) 수동 전량 매도가 유보돼 손절이 마비된다. 그래서
    **퇴화는 옛 행위로 떨어지고**, 그 사실은 `[fill_qty_src] src=increment`
    WARNING 이 남긴다 — 조용히 떨어지지 않는다.

    ⚠️ 이 경로에서는 발사 창 결함이 **그대로 남는다**(payload 가 없으면 매핑 부재
    창에서 주문수량을 알 길이 없다). 그것이 이 설계가 감수한 유일한 사각이고,
    빈도는 `[fill_qty_src_summary] increment=` 가 센다.
    """
    import logging

    env = _make_env(monkeypatch)

    with pytest.MonkeyPatch.context():
        await env.engine.handle_execution_notice(
            order_no="NOPAYLOAD-1", ticker=TICKER, side="SELL",
            quantity=HELD_QTY, price=PRICE,
            # ordered_qty_payload 미전달 = 0 (필드 부재·파싱 실패)
        )

    assert TICKER not in env.strategy.state.positions, (
        "payload 부재 퇴화 경로인데 전량 판정이 막혔다 — 옛 행위와 달라졌다"
    )


@pytest.mark.asyncio
async def test_payload_mismatch_is_observed_but_does_not_change_verdict(monkeypatch, caplog):
    """🔴 payload 가 우리 기록과 다르면 **관측만** 하고 판정은 `map` 값을 쓴다.

    `fields[16]` 배정이 틀렸을 때(cycle235 가 겪었다) 이 마커가 유일한 조기 경보다.
    그 사고는 부분/분할 체결에서만 드러나 오래 잠복했는데, 이 대조는 매핑이 선
    **정상 통보마다** 돌므로 창을 기다리지 않는다.
    """
    import logging

    env = _make_env(monkeypatch)
    caplog.set_level(logging.WARNING, logger="src.engine.order_engine")

    env.engine._order_qty["MISMATCH-1"] = HELD_QTY
    env.engine._order_ticker["MISMATCH-1"] = TICKER
    env.engine._order_strategy["MISMATCH-1"] = "momentum"

    await env.engine.handle_execution_notice(
        order_no="MISMATCH-1", ticker=TICKER, side="SELL",
        quantity=HELD_QTY, price=PRICE,
        ordered_qty_payload=HELD_QTY + 7,   # KIS 값이 우리 기록과 다르다
    )

    hits = [r.getMessage() for r in caplog.records
            if "[ordered_qty_mismatch]" in r.getMessage()]
    assert len(hits) == 1, f"불일치 마커가 {len(hits)}행 (기대 1행): {hits}"
    assert "mapped=10" in hits[0] and "payload=17" in hits[0]

    # 판정은 map(10) 기준 — payload(17) 를 썼다면 전량이 아니라 부분으로 갈렸을 것이다
    assert TICKER not in env.strategy.state.positions, (
        "불일치 시 payload 를 판정에 썼다 — map 이 우선이어야 한다"
    )


@pytest.mark.asyncio
async def test_partial_in_window_does_not_schedule_cancel_and_reorder(monkeypatch, caplog):
    """🔴 매핑 확정 전 통보는 **취소·재주문 타이머를 걸지 않는다** (자문 필수 동반 조항).

    이 시정이 만드는 새 결함을 막는 유일한 방어다. 시정 전에는 창 안의 통보가
    **전량 분기**로 갔으므로 타이머에 닿지 않았는데, 시정 후 처음으로 **부분 분기**에
    도달한다. 그리고 `_cancel_and_reorder` 에는 포지션 재조회가 **한 줄도 없다**(실측).

    `qty_src="payload"` 에는 **수동 매매(MTS/HTS) 주문도 포함**되므로 게이트가 없으면
    30초 뒤 **사람이 낸 주문을 우리가 취소하고 다시 낸다** — cycle327 이 봉한
    「주문이 나간 뒤의 재발사」와 같은 계열의 사고다.

    잃는 것은 없다 — 우리 주문의 잔여는 ms 뒤 다음 통보가 `src=map` 으로 와서
    정상적으로 타이머를 건다.
    """
    import logging

    from src.engine.strategy_base import Signal

    env = _make_env(monkeypatch)
    caplog.set_level(logging.WARNING, logger="src.engine.order_engine")

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "momentum")

    assert TICKER not in env.engine._pending_cancel_tasks, (
        "매핑 확정 전 통보인데 취소·재주문 타이머가 걸렸다 — "
        "30초 뒤 포지션 확인 없이 신규 매도가 발사된다"
    )
    assert TICKER not in env.engine._pending_cancel_order_no

    hits = [r.getMessage() for r in caplog.records
            if "[fill_partial_no_reorder]" in r.getMessage()]
    assert hits, "재주문을 보류했는데 아무 말도 남기지 않았다 — 조용한 보류는 은폐다"
    assert "src=payload" in hits[0]
