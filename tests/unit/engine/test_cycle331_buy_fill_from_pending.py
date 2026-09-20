"""cycle331 — 발사 창에 착지한 **매수** 체결통보가 포지션을 남기지 않는다.

자문 = `_workspace/domain_consult/cycle331_buy_fill_dropped.md`
발견 = cycle329 자문 3절("매수 축이 더 위험하다") → 다음 작업 식별 워크플로 B2

## 사슬 (전부 실측 파일:행)

```
execute_buy:1138  state.pending_buys.add(ticker)     ← 여기서 is_ticker_held_by_any = True
          :1262  result = await place_order(...)     ← 매핑 5종은 이 뒤(:1270~)
                 ◀ 이 창에 체결통보가 착지하면 매핑 0 / pending 1
handle_execution_notice:2211  _order_ticker miss → payload ticker 로 계속
_handle_buy_fill:2406  _order_strategy miss
                :2409  trade_history miss (PENDING INSERT 도 place_order 뒤라 원리상 없다)
                :2415  is_ticker_held_by_any → 🔴 **참** (자기 pending 이 세운 조건)
                :2421  return                        ← Position 이 **아예 등록되지 않는다**
```

🔴 **매수 당사자 자신이 그 조건을 세운다.** `is_ticker_held_by_any` 는
`_strategies.values()` **전수**를 보고 `has_position OR is_buy_pending` 이다
(`strategy_registry.py:69-74`). 확률적 사건이 아니라 **창에 들어오면 예외 없이** 걸린다.

## 피해 — 그날 하루 손절이 꺼진다

`risk.on_tick` 은 `state.positions` 를 보므로 포지션이 없으면 **손절·트레일링·15:20
일괄청산이 성립하지 않는다**. 익일청산만 다음 날 `_boot` 의 KIS 잔고 복구가 되살린다.
`trade_history` 는 `mark_pending_buys_completed` 가 장부만 뒤늦게 맞추므로
**대시보드·DB 어느 쪽을 봐도 정상으로 보인다**.

### 실측 (운영 DB, 2026-08-20~09-18 보존 구간)

| 종목 | 매수 | 결과 |
|---|---|---|
| 161890 콜마 | 08-31 08:13 NXT 프리 171,700 ×1 | 그날 KRX 시가 162,200(−5.5%) · 저가 155,400(−9.5%). LTV 당일 손절선 163,115 → **09:00 손절돼야 했다**. 실제는 **09-01 익일청산 160,200, −11,200(−6.5%)** |
| 078930 GS | 08-26 14:44 129,100 ×1 | 15:20 일괄청산 대상에 못 올라 밤을 넘김 → 갭업 익일청산 **+2,000** |

🔴 **손익 결함이 아니라 통제 결함이다.** 표본 2건의 기대값은 거의 상쇄되고
(+2,000 / −1,700) 바뀌는 것은 **분산**이다 — 손절이 꺼진 랏은 양쪽으로 꼬리가 열린다.
실적표에는 드러나지 않는다.

빈도 = BUY COMPLETED 96건 중 **2건(2.1%, 월 2회)**. 🔴 **1주 랏에 집중**된다 —
단일 통보로 전량 체결되므로 **두 번째 통보가 없어 자기 치유 경로가 구조적으로 없다**.
다주 랏은 잔여 통보가 `src=map` 으로 와서 포지션을 만들어 준다.

## 시정 (자문 A안)

폴백 체인에 **`pending` 단독 소유자** 단을 하나 끼운다.

```
현행:  map → trade_history → [held/pending 이면 return] → momentum
시정:  map → trade_history → pending 단독 소유자 → [held/pending 이면 return] → momentum
```

채택 조건(전부 in-memory, `await` 0) = `ticker in s.state.pending_buys` 인 전략이
**정확히 1개**이고 그 전략이 그 ticker 를 **보유하고 있지 않을** 때만.
0개·2개 이상은 **채택하지 않고 현행 그대로**(fail-open, 결과 집합 ⊆ 현행).

🔴 **조기 return 가드는 없애지 않는다** — 그 가드(P1-B B-2)가 막는 것은
**출처를 모르는 매수 체결이 `momentum` 을 우겨 남의 포지션을 덮는 것**(377450 사고)이고,
수동 매매·외부 주문에서는 여전히 유효하다. 좁히는 것이지 없애는 것이 아니다.
수동/외부 매수는 우리 `pending_buys` 에 없으므로 **한 글자도 안 바뀐다**.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

TICKER = "161890"
PRICE = 171_700
QTY = 1


def _make_env(monkeypatch):
    """발사 창 = 매핑 5종은 비었고 `pending_buys` 만 차 있는 상태."""
    from src.engine import scanner
    from src.engine.order_engine import OrderEngine
    from src.engine.session import MarketBoard, session_tracker
    from src.engine.strategies.momentum import MomentumStrategy
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
    from src.engine.strategy_base import StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    monkeypatch.setattr(scanner, "ticker_names", {TICKER: "콜마비앤에이치"}, raising=False)
    monkeypatch.setattr(scanner, "ticker_prev_close", {TICKER: PRICE}, raising=False)
    monkeypatch.setattr(scanner, "ticker_prices", {TICKER: {"current_price": PRICE}},
                        raising=False)
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))

    registry = StrategyRegistry()
    ltv = LongTailVolatilityStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="롱테일", weight=0.05,
                       params={"exchange": "KRX"})
    )
    mom = MomentumStrategy(
        StrategyConfig(strategy_id="momentum", name="모멘텀", weight=0.1,
                       params={"exchange": "KRX"})
    )
    registry.register(ltv)
    registry.register(mom)
    registry.allocate_funds(total_asset=5_000_000)
    engine = OrderEngine(registry)

    async def noop(*a, **k):
        return None

    async def fake_update_status(*a, **k):
        return 1

    async def no_strategy(*a, **k):
        return None   # trade_history 폴백도 miss (창 안에서는 원리상 행이 없다)

    monkeypatch.setattr("src.engine.order_engine.update_trade_status", fake_update_status)
    monkeypatch.setattr("src.engine.order_engine.insert_trade", noop)
    monkeypatch.setattr("src.engine.order_engine.write_log", noop)
    monkeypatch.setattr("src.engine.order_engine._lookup_strategy_from_trade_history",
                        no_strategy)

    import src.db.positions as positions_mod
    monkeypatch.setattr(positions_mod, "save_position", noop, raising=False)
    monkeypatch.setattr(positions_mod, "delete_position", noop, raising=False)

    return SimpleNamespace(engine=engine, registry=registry, ltv=ltv, momentum=mom)


@pytest.mark.asyncio
async def test_buy_fill_in_window_registers_position_on_pending_owner(monkeypatch):
    """🔴 발사 창에 착지한 매수 체결이 **주문을 낸 그 전략에** 포지션을 만든다.

    이것이 이 사이클의 계약이다. 지금은 `is_ticker_held_by_any` 가 **자기 pending**
    때문에 참이 되어 조기 return 하고, 그날 하루 **손절·트레일링·15:20 청산이
    성립하지 않는다**(`risk.on_tick` 은 `state.positions` 를 본다).
    """
    env = _make_env(monkeypatch)
    # 발사 창 재현 — LTV 가 매수를 발사했고(pending) 매핑은 아직 비었다
    env.ltv.state.pending_buys.add(TICKER)

    await env.engine.handle_execution_notice(
        order_no="0000042100", ticker=TICKER, side="BUY",
        quantity=QTY, price=PRICE, ordered_qty_payload=QTY,
    )

    pos = env.ltv.state.positions.get(TICKER)
    assert pos is not None, (
        "발사 창의 매수 체결인데 포지션이 등록되지 않았다 — 그날 하루 손절이 꺼진다.\n"
        "  원인: 매수 당사자 자신의 pending_buys 가 is_ticker_held_by_any 를 참으로 만든다."
    )
    assert pos.strategy_id == "long_tail_volatility", (
        f"포지션이 엉뚱한 전략({pos.strategy_id})에 붙었다 — momentum 폴백으로 샜다"
    )
    assert pos.quantity == QTY
    assert TICKER not in env.momentum.state.positions, "momentum 에 유령 포지션이 생겼다"


@pytest.mark.asyncio
async def test_manual_order_still_hits_the_conflict_guard(monkeypatch):
    """🔴 수동 매매·외부 주문은 **한 글자도 바뀌지 않는다**.

    우리 `pending_buys` 에 없는 주문은 `pending` 단을 통과하지 못하고 기존
    조기 return 가드(P1-B B-2)로 간다. 그 가드가 막는 것은 **출처를 모르는 매수가
    `momentum` 을 우겨 남의 포지션을 덮는 것**(377450 사고)이라 살아 있어야 한다.
    """
    env = _make_env(monkeypatch)
    # 다른 전략이 이미 보유 — pending 은 아무도 없다
    from datetime import date

    from src.engine.strategy_base import Position
    env.momentum.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=100_000, quantity=5, order_no="OLD-1",
        strategy_id="momentum", buy_date=date(2026, 9, 19),
    )

    await env.engine.handle_execution_notice(
        order_no="MANUAL-1", ticker=TICKER, side="BUY",
        quantity=3, price=PRICE, ordered_qty_payload=3,
    )

    pos = env.momentum.state.positions[TICKER]
    assert pos.quantity == 5 and pos.order_no == "OLD-1", (
        "수동 매수 통보가 기존 포지션을 덮었다 — P1-B(B-2) 가드가 무력화됐다"
    )
    assert TICKER not in env.ltv.state.positions


@pytest.mark.asyncio
async def test_two_pending_owners_fall_back_to_current_behavior(monkeypatch):
    """🔴 `pending` 소유자가 **둘 이상**이면 채택하지 않는다 (fail-open).

    귀속을 확신할 수 없으면 물러선다 — 결과 집합이 현행의 부분집합이어야
    이 시정이 「좁히는 것」이지 「넓히는 것」이 아니다.
    """
    env = _make_env(monkeypatch)
    env.ltv.state.pending_buys.add(TICKER)
    env.momentum.state.pending_buys.add(TICKER)   # race — 둘이 동시에 주문 중

    await env.engine.handle_execution_notice(
        order_no="0000042100", ticker=TICKER, side="BUY",
        quantity=QTY, price=PRICE, ordered_qty_payload=QTY,
    )

    assert TICKER not in env.ltv.state.positions
    assert TICKER not in env.momentum.state.positions, (
        "pending 소유자가 둘인데 한쪽에 포지션을 만들었다 — 귀속이 추측이 됐다"
    )


@pytest.mark.asyncio
async def test_pending_owner_that_already_holds_is_not_adopted(monkeypatch):
    """`pending` 이면서 **이미 그 종목을 보유 중**이면 채택하지 않는다.

    그 경우는 추가 매수(피라미딩·재진입)라 기존 포지션 병합 규약이 따로 있어야 한다.
    이 단은 **신규 등록만** 담당하고, 애매하면 현행으로 물러선다.
    """
    from datetime import date

    from src.engine.strategy_base import Position

    env = _make_env(monkeypatch)
    env.ltv.state.pending_buys.add(TICKER)
    env.ltv.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=150_000, quantity=2, order_no="OLD-2",
        strategy_id="long_tail_volatility", buy_date=date(2026, 9, 19),
    )

    await env.engine.handle_execution_notice(
        order_no="0000042100", ticker=TICKER, side="BUY",
        quantity=QTY, price=PRICE, ordered_qty_payload=QTY,
    )

    pos = env.ltv.state.positions[TICKER]
    assert pos.quantity == 2 and pos.order_no == "OLD-2", (
        "보유 중인 포지션을 새 체결이 덮었다 — 이 단은 신규 등록만 해야 한다"
    )


@pytest.mark.asyncio
async def test_adoption_emits_success_marker(monkeypatch, caplog):
    """🔴 귀속이 성립하면 **말을 남긴다** — 이것이 시정의 성공 서명이다.

    무cap WARNING 이다(자문 8절). 빈도가 96건 중 2건이라 **한 건 한 건이 조사 단위**이고,
    `(ticker, strategy)` 로 묶으면 같은 날 두 번째 사건이 사라진다.
    WARNING 이상만 21:30 `top_patterns` 에 오르므로 리포트에도 자연히 실린다.
    """
    import logging

    env = _make_env(monkeypatch)
    env.ltv.state.pending_buys.add(TICKER)
    caplog.set_level(logging.WARNING, logger="src.engine.order_engine")

    await env.engine.handle_execution_notice(
        order_no="0000042100", ticker=TICKER, side="BUY",
        quantity=QTY, price=PRICE, ordered_qty_payload=QTY,
    )

    hits = [r.getMessage() for r in caplog.records
            if "[buy_fill_strategy_from_pending]" in r.getMessage()]
    assert len(hits) == 1, f"성공 서명 마커가 {len(hits)}행 (기대 1행): {hits}"
    assert "long_tail_volatility" in hits[0]
    assert "0000042100" in hits[0]


@pytest.mark.asyncio
async def test_partial_fill_via_pending_does_not_schedule_cancel(monkeypatch, caplog):
    """🔴 `pending` 단으로 건진 랏에는 **잔량 취소 타이머를 걸지 않는다** (자문 7절).

    이 시정이 만드는 새 결함을 막는 방어다. 귀속이 열리면 창의 통보가 **처음으로**
    부분 체결 분기에 도달하고, 거기서 30초 뒤 `_cancel_after_wait` 가 **잔량을 취소**한다.
    귀속이 틀린 랏(특히 `boot_manager` 가 KIS 미체결로 seed 한 `pending_buys` 잔존)에서
    그 타이머가 걸리면 **사람이 낸 주문을 우리가 취소한다** —
    cycle327·cycle329 가 봉한 것과 같은 계열이다.

    잃는 것은 없다 — 우리 주문이면 매핑이 곧 서고 잔여 통보가 `src=map` 으로 와서
    정상적으로 타이머를 건다.
    """
    import logging

    env = _make_env(monkeypatch)
    env.ltv.state.pending_buys.add(TICKER)
    caplog.set_level(logging.WARNING, logger="src.engine.order_engine")

    # 10주 주문 중 3주만 체결 = 부분 체결 분기
    await env.engine.handle_execution_notice(
        order_no="0000042100", ticker=TICKER, side="BUY",
        quantity=3, price=PRICE, ordered_qty_payload=10,
    )

    assert (TICKER, "buy") not in env.engine._pending_cancel_tasks, (
        "pending 단으로 건진 랏에 취소 타이머가 걸렸다 — "
        "30초 뒤 포지션 확인 없이 잔량 취소가 나간다"
    )
    hits = [r.getMessage() for r in caplog.records
            if "[buy_partial_no_cancel_timer]" in r.getMessage()]
    assert hits, "타이머를 보류했는데 아무 말도 남기지 않았다 — 조용한 보류는 은폐다"
