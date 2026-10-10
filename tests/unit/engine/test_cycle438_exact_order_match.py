"""cycle438 — J-4: 매수 두 번째 부분 체결의 정확 일치 귀속.

자문 = `_workspace/domain_consult/2026-10-10_j4_exact_fill_attribution.md`

cycle331 「발사 창 귀속」(pending 단)이 받지 못하는 통보 — 매핑·`trade_history`·
pending 단이 전부 miss 인 통보 중 「레지스트리에 그 `order_no` 로 이미 포지션을
가진 전략이 정확히 하나이고, 이 프로세스가 그 주문의 앞선 체결을 이미 세었다」
(E2·E3)면 B-2(`held_conflict`) 로 떨어뜨리지 않고 그 전략에 증분으로 귀속한다.

시나리오 번호(J4-1~J4-15)는 자문 §4(d) 표와 그대로 대응한다. J4-3(카드 E 키
갈아끼우기 — `_rekey_buy_reservation_after_send`)은 cycle436 커밋의
`tests/unit/engine/test_order_engine_buy.py::test_j4_3_*` 가 이미 덮는다(자문의
명시 권고).
"""
from __future__ import annotations

import logging
from datetime import date
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

TICKER = "161890"
PRICE = 171_700


def _make_env(monkeypatch):
    """발사 창 재현 — 매핑 5종은 비었고 (필요하면) `pending_buys` 만 차 있다."""
    from src.engine import scanner
    from src.engine.order_engine import OrderEngine
    from src.engine.session import MarketBoard, session_tracker
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategies.kojiro import KojiroStrategy
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
    from src.engine.strategies.momentum import MomentumStrategy
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
    donchian = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="돈키언", weight=0.1,
                       params={"exchange": "KRX"})
    )
    kojiro = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.1,
                       params={"exchange": "KRX"})
    )
    registry.register(ltv)
    registry.register(mom)
    registry.register(donchian)
    registry.register(kojiro)
    registry.allocate_funds(total_asset=20_000_000)
    engine = OrderEngine(registry)

    async def noop(*a, **k):
        return None

    async def fake_update_status(*a, **k):
        return 1

    async def no_strategy(*a, **k):
        return None  # trade_history 폴백도 miss (창 안에서는 원리상 행이 없다)

    monkeypatch.setattr("src.engine.order_engine.update_trade_status", fake_update_status)
    monkeypatch.setattr("src.engine.order_engine.insert_trade", noop)
    monkeypatch.setattr("src.engine.order_engine.write_log", noop)
    monkeypatch.setattr("src.engine.order_engine._lookup_strategy_from_trade_history",
                        no_strategy)
    import src.db.positions as positions_mod
    saved_calls: list[dict] = []

    async def fake_save_position(**kwargs):
        saved_calls.append(kwargs)

    monkeypatch.setattr(positions_mod, "save_position", fake_save_position, raising=False)
    monkeypatch.setattr(positions_mod, "delete_position", noop, raising=False)

    return SimpleNamespace(
        engine=engine, registry=registry, ltv=ltv, momentum=mom,
        donchian=donchian, kojiro=kojiro, saved_calls=saved_calls,
    )


def _held_order_no(pos_order_no: str) -> str:
    return pos_order_no


# ---------------------------------------------------------------------------
# J4-1 — C1 부분: pending 단 1차 등록 → 2차는 정확 일치로 증분
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j4_1_second_partial_fill_is_attributed_by_exact_match(monkeypatch, caplog):
    env = _make_env(monkeypatch)
    env.ltv.state.pending_buys.add(TICKER)
    caplog.set_level(logging.WARNING, logger="src.engine.order_engine")

    # 1차 3/10 → pending 단 등록
    await env.engine.handle_execution_notice(
        order_no="ORD-J4-1", ticker=TICKER, side="BUY",
        quantity=3, price=PRICE, ordered_qty_payload=10,
    )
    pos = env.ltv.state.positions[TICKER]
    assert pos.quantity == 3 and pos.order_no == "ORD-J4-1"

    # 2차 4/10 (발사 창 안 — 매핑 여전히 비었다) → 정확 일치로 증분
    await env.engine.handle_execution_notice(
        order_no="ORD-J4-1", ticker=TICKER, side="BUY",
        quantity=4, price=PRICE, ordered_qty_payload=10,
    )

    pos = env.ltv.state.positions[TICKER]
    assert pos.quantity == 7, f"증분 귀속이면 7인데 {pos.quantity}"
    assert pos.order_no == "ORD-J4-1"

    held_conflict = [r.getMessage() for r in caplog.records
                      if "[buy_fill_fallback_held_conflict]" in r.getMessage()]
    assert held_conflict == [], f"held_conflict 가 났다: {held_conflict}"

    exact_hits = [r.getMessage() for r in caplog.records
                  if "[buy_fill_exact_order_match]" in r.getMessage()]
    assert len(exact_hits) == 1, f"정확 일치 마커가 {len(exact_hits)}행: {exact_hits}"
    assert "long_tail_volatility" in exact_hits[0]

    assert (TICKER, "buy") not in env.engine._pending_cancel_tasks, (
        "정확 일치 귀속 랏에 취소 타이머가 걸렸다"
    )
    assert env.ltv.state.fill_count_today == 1, "두 번째 체결이 신규 등록으로 중복 집계됐다"


# ---------------------------------------------------------------------------
# J4-2 — C1 전량: 1차 3/10, 2차 7/10(전량)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j4_2_second_fill_completes_the_order(monkeypatch):
    env = _make_env(monkeypatch)
    env.ltv.state.pending_buys.add(TICKER)

    await env.engine.handle_execution_notice(
        order_no="ORD-J4-2", ticker=TICKER, side="BUY",
        quantity=3, price=PRICE, ordered_qty_payload=10,
    )
    await env.engine.handle_execution_notice(
        order_no="ORD-J4-2", ticker=TICKER, side="BUY",
        quantity=7, price=PRICE, ordered_qty_payload=10,
    )

    pos = env.ltv.state.positions[TICKER]
    assert pos.quantity == 10
    assert "ORD-J4-2" in env.engine._completed_buy_orders, (
        "전량 체결인데 _completed_buy_orders 에 등록되지 않았다"
    )
    assert env.saved_calls, "save_position 이 호출되지 않았다"
    assert env.saved_calls[-1]["quantity"] == 10
    assert env.saved_calls[-1]["buy_price"] == PRICE


# ---------------------------------------------------------------------------
# J4-4 — J4-1 뒤 매핑이 서고 3차 3/10 이 src=map 으로 도착
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j4_4_third_fill_arrives_with_map_after_mapping_lands(monkeypatch):
    env = _make_env(monkeypatch)
    env.ltv.state.pending_buys.add(TICKER)

    await env.engine.handle_execution_notice(
        order_no="ORD-J4-4", ticker=TICKER, side="BUY",
        quantity=3, price=PRICE, ordered_qty_payload=10,
    )
    await env.engine.handle_execution_notice(
        order_no="ORD-J4-4", ticker=TICKER, side="BUY",
        quantity=4, price=PRICE, ordered_qty_payload=10,
    )
    # 응답이 늦게 도착해 매핑이 선다 (execute_buy 가 정상적으로 했을 일을 흉내).
    env.engine._order_qty["ORD-J4-4"] = 10
    env.engine._order_strategy["ORD-J4-4"] = "long_tail_volatility"

    await env.engine.handle_execution_notice(
        order_no="ORD-J4-4", ticker=TICKER, side="BUY",
        quantity=3, price=PRICE, ordered_qty_payload=10,
    )

    pos = env.ltv.state.positions[TICKER]
    assert pos.quantity == 10
    assert "ORD-J4-4" in env.engine._completed_buy_orders


# ---------------------------------------------------------------------------
# J4-5 — C2: 부팅 뒤 미상 주문 1차 2/5 → momentum 고아 등록(CRITICAL) → 2차 3/5
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j4_5_orphan_fallback_second_fill_attributed_by_exact_match(
    monkeypatch, caplog,
):
    import asyncio

    env = _make_env(monkeypatch)
    caplog.set_level(logging.WARNING, logger="src.engine.order_engine")
    critical_calls: list[tuple] = []

    async def fake_write_log(level, msg):
        critical_calls.append((level, msg))

    monkeypatch.setattr("src.engine.order_engine.write_log", fake_write_log)

    await env.engine.handle_execution_notice(
        order_no="ORD-J4-5", ticker=TICKER, side="BUY",
        quantity=2, price=PRICE, ordered_qty_payload=5,
    )
    await asyncio.sleep(0)  # orphan CRITICAL 은 asyncio.create_task 로 fire-and-forget
    pos = env.momentum.state.positions[TICKER]
    assert pos.quantity == 2 and pos.strategy_id == "momentum"
    assert len(critical_calls) == 1, f"고아 CRITICAL 이 {len(critical_calls)}건: {critical_calls}"

    await env.engine.handle_execution_notice(
        order_no="ORD-J4-5", ticker=TICKER, side="BUY",
        quantity=3, price=PRICE, ordered_qty_payload=5,
    )
    await asyncio.sleep(0)

    pos = env.momentum.state.positions[TICKER]
    assert pos.quantity == 5, f"증분 귀속이면 5인데 {pos.quantity}"
    assert len(critical_calls) == 1, "두 번째 체결에서 고아 CRITICAL 이 다시 났다"
    assert (TICKER, "buy") not in env.engine._pending_cancel_tasks
    assert TICKER not in env.ltv.state.positions


# ---------------------------------------------------------------------------
# J4-6 — B-2 유지: momentum 이 주문 A 로 보유, 미상 주문 B 통보
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j4_6_different_order_no_falls_to_held_conflict(monkeypatch, caplog):
    from src.engine.strategy_base import Position

    env = _make_env(monkeypatch)
    env.momentum.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=100_000, quantity=5, order_no="ORD-A",
        strategy_id="momentum", buy_date=date(2026, 9, 19),
    )
    caplog.set_level(logging.ERROR, logger="src.engine.order_engine")

    await env.engine.handle_execution_notice(
        order_no="ORD-B", ticker=TICKER, side="BUY",
        quantity=3, price=PRICE, ordered_qty_payload=3,
    )

    pos = env.momentum.state.positions[TICKER]
    assert pos.quantity == 5 and pos.order_no == "ORD-A", "다른 주문번호 체결이 기존 포지션을 바꿨다"
    held_conflict = [r.getMessage() for r in caplog.records
                      if "[buy_fill_fallback_held_conflict]" in r.getMessage()]
    assert len(held_conflict) == 1


# ---------------------------------------------------------------------------
# J4-7 — B-2 유지: kojiro DB 복구 스윙 포지션(며칠 전 주문번호) + 오늘 같은 번호 통보
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j4_7_same_order_no_but_never_counted_falls_to_held_conflict(
    monkeypatch, caplog,
):
    from src.engine.strategy_base import Position

    env = _make_env(monkeypatch)
    # DB 복구 — 며칠 전 주문번호, 이 프로세스는 그 체결을 센 적이 없다(_filled_qty 비었음).
    env.kojiro.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=100_000, quantity=4, order_no="0000338400",
        strategy_id="kojiro", buy_date=date(2026, 9, 10),
    )
    caplog.set_level(logging.ERROR, logger="src.engine.order_engine")

    # 오늘 같은 종목·같은 주문번호의(우연) 새 통보 — 이 프로세스에선 "처음" 본다.
    await env.engine.handle_execution_notice(
        order_no="0000338400", ticker=TICKER, side="BUY",
        quantity=2, price=PRICE, ordered_qty_payload=2,
    )

    pos = env.kojiro.state.positions[TICKER]
    assert pos.quantity == 4, "E3 불성립인데 귀속돼 수량이 바뀌었다"
    held_conflict = [r.getMessage() for r in caplog.records
                      if "[buy_fill_fallback_held_conflict]" in r.getMessage()]
    assert len(held_conflict) == 1


# ---------------------------------------------------------------------------
# J4-8 — B-2 유지: 재시작 직후 오늘 전량 체결된 주문의 중복 통보
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j4_8_duplicate_notice_after_restart_falls_to_held_conflict(
    monkeypatch, caplog,
):
    from src.engine.strategy_base import Position

    env = _make_env(monkeypatch)
    env.ltv.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=100_000, quantity=10, order_no="ORD-J4-8",
        strategy_id="long_tail_volatility", buy_date=date(2026, 10, 10),
    )
    caplog.set_level(logging.ERROR, logger="src.engine.order_engine")

    # _filled_qty 는 재시작으로 비었다 — 이 통보가 "처음" 이다(prev_total==0).
    await env.engine.handle_execution_notice(
        order_no="ORD-J4-8", ticker=TICKER, side="BUY",
        quantity=10, price=PRICE, ordered_qty_payload=10,
    )

    pos = env.ltv.state.positions[TICKER]
    assert pos.quantity == 10, "중복 통보로 수량이 덮어씌워지지 않아야 한다(덮어쓰기였다면 10 그대로가 아니라 오염)"
    held_conflict = [r.getMessage() for r in caplog.records
                      if "[buy_fill_fallback_held_conflict]" in r.getMessage()]
    assert len(held_conflict) == 1


# ---------------------------------------------------------------------------
# J4-9 — B-2 유지: 다른 전략이 보유, order_no 는 그 전략 것
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j4_9_different_strategy_holds_falls_to_held_conflict(monkeypatch, caplog):
    from src.engine.strategy_base import Position

    env = _make_env(monkeypatch)
    env.donchian.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=100_000, quantity=6, order_no="ORD-DONCHIAN",
        strategy_id="donchian_swing", buy_date=date(2026, 10, 9),
    )
    caplog.set_level(logging.ERROR, logger="src.engine.order_engine")

    await env.engine.handle_execution_notice(
        order_no="ORD-DONCHIAN", ticker=TICKER, side="BUY",
        quantity=1, price=PRICE, ordered_qty_payload=1,
    )
    # prev_total==0 (이 주문의 체결을 이 프로세스가 처음 본다) 이므로 E3 도 불성립 —
    # E2/E3 둘 다 B-2 로 떨어뜨리는 이 시나리오의 일부다.

    pos = env.donchian.state.positions[TICKER]
    assert pos.quantity == 6
    held_conflict = [r.getMessage() for r in caplog.records
                      if "[buy_fill_fallback_held_conflict]" in r.getMessage()]
    assert len(held_conflict) == 1


# ---------------------------------------------------------------------------
# J4-10 — E2 0개: order_no="" KIS 잔고 복구 포지션 + 잔량 통보(C3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j4_10_empty_order_no_position_never_matched(monkeypatch, caplog):
    from src.engine.strategy_base import Position

    env = _make_env(monkeypatch)
    env.donchian.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=100_000, quantity=6, order_no="",
        strategy_id="donchian_swing", buy_date=date(2026, 10, 9),
    )
    caplog.set_level(logging.ERROR, logger="src.engine.order_engine")

    await env.engine.handle_execution_notice(
        order_no="ORD-REMAIN", ticker=TICKER, side="BUY",
        quantity=2, price=PRICE, ordered_qty_payload=2,
    )

    pos = env.donchian.state.positions[TICKER]
    assert pos.quantity == 6, "order_no='' 포지션에 잔량이 귀속됐다"
    held_conflict = [r.getMessage() for r in caplog.records
                      if "[buy_fill_fallback_held_conflict]" in r.getMessage()]
    assert len(held_conflict) == 1


# ---------------------------------------------------------------------------
# J4-11 — C4: trade_history PARTIAL 적중 + pos.order_no=="" (기존 결함 재현,
# J-4 범위 밖 — 손대지 않는다)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j4_11_trade_history_hit_with_empty_order_no_overwrite_persists(
    monkeypatch,
):
    """§(b) 기존 결함 — trade_history 가 전략을 복구하면(이 경로는 pending/exact
    단과 무관하다) `pos.quantity = total_filled` 덮어쓰기가 그대로 남는다.
    J-4 가 만든 결함도, J-4 가 고치는 결함도 아니다 — 손대지 않았음을 고정한다.
    """
    from src.engine.strategy_base import Position

    env = _make_env(monkeypatch)
    env.donchian.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=100_000, quantity=3, order_no="",
        strategy_id="donchian_swing", buy_date=date(2026, 10, 9),
    )

    async def found_strategy(*a, **k):
        return "donchian_swing"

    monkeypatch.setattr(
        "src.engine.order_engine._lookup_strategy_from_trade_history", found_strategy,
    )

    await env.engine.handle_execution_notice(
        order_no="ORD-PARTIAL", ticker=TICKER, side="BUY",
        quantity=1, price=PRICE, ordered_qty_payload=4,
    )

    pos = env.donchian.state.positions[TICKER]
    assert pos.quantity == 1, (
        f"기존 결함(덮어쓰기)이 사라졌다 — quantity={pos.quantity} (기대 1, 즉 3→1 로 줄어드는 결함 그대로)"
    )


# ---------------------------------------------------------------------------
# J4-12 — 사이 매도: 1차 등록 뒤 사람이 일부를 팔고(보유 축 감소) 2차 체결
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j4_12_intervening_sell_is_not_revived_by_overwrite(monkeypatch):
    env = _make_env(monkeypatch)

    await env.engine.handle_execution_notice(
        order_no="ORD-J4-12", ticker=TICKER, side="BUY",
        quantity=2, price=PRICE, ordered_qty_payload=5,
    )
    pos = env.momentum.state.positions[TICKER]
    assert pos.quantity == 2

    # 사이에 사람이 1주를 팔았다 (cycle385 보유 축 차감을 흉내).
    pos.quantity = 1

    await env.engine.handle_execution_notice(
        order_no="ORD-J4-12", ticker=TICKER, side="BUY",
        quantity=3, price=PRICE, ordered_qty_payload=5,
    )

    pos = env.momentum.state.positions[TICKER]
    assert pos.quantity == 4, (
        f"증분(1+3=4) 이어야 하는데 {pos.quantity} — 덮어쓰기였다면 5(total_filled) 로 "
        "판 것을 되살린다"
    )


# ---------------------------------------------------------------------------
# J4-13 — 판정 예외: 레지스트리 순회 중 예외 주입
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j4_13_registry_exception_falls_to_held_conflict_without_raising(
    monkeypatch, caplog,
):
    from src.engine.strategy_base import Position

    env = _make_env(monkeypatch)
    env.momentum.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=100_000, quantity=5, order_no="ORD-HELD",
        strategy_id="momentum", buy_date=date(2026, 10, 9),
    )

    def boom():
        raise RuntimeError("registry.all() 판정 실패 주입")

    monkeypatch.setattr(env.registry, "all", boom)
    caplog.set_level(logging.ERROR, logger="src.engine.order_engine")

    # 예외가 handle_execution_notice 밖으로 전파되지 않아야 한다.
    await env.engine.handle_execution_notice(
        order_no="ORD-OTHER", ticker=TICKER, side="BUY",
        quantity=1, price=PRICE, ordered_qty_payload=1,
    )

    pos = env.momentum.state.positions[TICKER]
    assert pos.quantity == 5
    held_conflict = [r.getMessage() for r in caplog.records
                      if "[buy_fill_fallback_held_conflict]" in r.getMessage()]
    assert len(held_conflict) == 1


# ---------------------------------------------------------------------------
# J4-14 — E2 2개(인위): 두 전략이 같은 order_no 포지션
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_j4_14_two_strategies_share_order_no_falls_to_held_conflict(
    monkeypatch, caplog,
):
    from src.engine.strategy_base import Position

    env = _make_env(monkeypatch)
    env.momentum.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=100_000, quantity=5, order_no="ORD-SHARED",
        strategy_id="momentum", buy_date=date(2026, 10, 9),
    )
    env.ltv.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=100_000, quantity=2, order_no="ORD-SHARED",
        strategy_id="long_tail_volatility", buy_date=date(2026, 10, 9),
    )
    caplog.set_level(logging.ERROR, logger="src.engine.order_engine")

    await env.engine.handle_execution_notice(
        order_no="ORD-SHARED", ticker=TICKER, side="BUY",
        quantity=1, price=PRICE, ordered_qty_payload=1,
    )

    assert env.momentum.state.positions[TICKER].quantity == 5
    assert env.ltv.state.positions[TICKER].quantity == 2
    held_conflict = [r.getMessage() for r in caplog.records
                      if "[buy_fill_fallback_held_conflict]" in r.getMessage()]
    assert len(held_conflict) == 1


# ---------------------------------------------------------------------------
# J4-15 — 구조 검사: elif 가 pending 단 뒤 · B-2 앞, 타이머 조건에 strategy_from_exact
# ---------------------------------------------------------------------------


def test_j4_15_structure_elif_between_pending_and_b2():
    import inspect

    from src.engine.order_engine import OrderEngine

    src = inspect.getsource(OrderEngine._handle_buy_fill)
    pending_idx = src.index("buy_fill_strategy_from_pending")
    exact_idx = src.index("_resolve_exact_order_match(")
    b2_idx = src.index("buy_fill_fallback_held_conflict")
    assert pending_idx < exact_idx < b2_idx, (
        "정확 일치 elif 가 pending 단 뒤·B-2 앞에 있어야 한다"
    )
    # B-2 의 return 이 그대로 남아 있다.
    b2_block = src[b2_idx:b2_idx + 400]
    assert "return" in b2_block, "B-2 가드의 return 이 사라졌다"

    timer_src = inspect.getsource(OrderEngine._handle_buy_fill)
    timer_idx = timer_src.index('qty_src == "map" and not strategy_from_pending')
    timer_line = timer_src[timer_idx:timer_idx + 120]
    assert "strategy_from_exact" in timer_line, (
        "잔량 취소 타이머 조건에 strategy_from_exact 가 들어있지 않다"
    )
