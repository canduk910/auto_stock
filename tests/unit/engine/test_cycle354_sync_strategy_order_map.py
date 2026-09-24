"""cycle354 카드 C — Red: `_sync_orders_to_db` 의 `strategy="momentum"` 하드코딩 폴백 시정.

배경 (`_workspace/domain_consult/cycle335_buy_post_send_boundary.md` §5 카드 C):
- `_sync_orders_to_db` 는 DB(당일 같은 티커 매수 기록, `db_strategy_map`)에서 전략을
  못 찾으면 곧바로 리터럴 `"momentum"` 으로 떨어진다. 당일 첫 매수(가장 흔한 sync
  경로)는 `db_strategy_map` 에 그 ticker 가 없어 전부 이 함정을 밟는다 — 성과 귀인
  (전략별 승률/손익)이 실제로 주문을 낸 전략이 아니라 momentum 으로 오염된다.
- `order_engine._order_strategy`(order_no → strategy_id, `place_order` 응답 직후
  동기 등록 · 전량 체결 시 pop, 루트 CLAUDE.md 「주문번호 매핑」 규약)는 **이 정확한
  주문**이 어느 전략인지 아는 살아있는 매핑이다. `_sync_orders_to_db` 는 boot 시점
  (`boot_manager.py` 유일 호출부)에만 불리므로, 재시작 전에 체결통보(WS)가 유실돼
  `_order_strategy` 엔트리가 아직 pop 되지 않은 주문이 이 창의 전형적 표적이다.

요구 행위 (이 사이클 시정):
- 출처 순서 = DB(`db_strategy_map`, 기존) → `order_engine._order_strategy`(신규,
  order_no 매핑) → 하드코딩 `"momentum"`(최종 폴백).
- 셋 다 실패해야만(= 두 출처 모두 미확보) `"momentum"` 폴백 + `[sync_strategy_unknown]`
  WARNING(ticker·order_no 포함) — 실제로 momentum 이 정답인 경우(DB/매핑이 momentum
  을 가리킴)까지 경보하지 않는다(과잉 경보는 그 자체로 리포트 오염이다).
- 매도는 기존처럼 registry 라이브 포지션 조회가 **최종 권위**로 남는다(정확한
  buy_price 기반 profit_loss 계산의 유일한 출처라 order_no 매핑보다 후순위로 두지
  않는다 — 순서를 바꾸면 안 된다).
- `order_engine` 속성이 아예 없는 구형 테스트 더블(스텁)에서도 AttributeError 없이
  기존과 동일하게 동작한다(fail-open, byte 호환).
- 매핑 값이 빈 문자열처럼 오염돼 있으면 "값이 있다"로 오판하지 않고 미확보로
  취급한다(경보 없이 momentum 으로 조용히 오염되는 것을 막는다).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.unit


def _make_scheduler(*, order_strategy_map: dict[str, str] | None = None, positions_by_strategy=None, with_order_engine: bool = True):
    """무거운 `__init__` 우회 — `_sync_orders_to_db` 호출에 필요한 최소 상태만 주입.

    `positions_by_strategy`: {strategy_id: {ticker: SimpleNamespace(buy_price=...)}}
    """
    from src.engine.scheduler import TradingScheduler

    scheduler = TradingScheduler.__new__(TradingScheduler)

    positions_by_strategy = positions_by_strategy or {}

    class _FakeStrategy:
        def __init__(self, strategy_id: str, positions: dict[str, Any]):
            self.strategy_id = strategy_id
            self.state = SimpleNamespace(positions=positions)

    strategies = [
        _FakeStrategy(sid, positions)
        for sid, positions in positions_by_strategy.items()
    ]

    class _Reg:
        def all(self):
            return strategies

    scheduler.registry = _Reg()

    if with_order_engine:
        scheduler.order_engine = SimpleNamespace(_order_strategy=order_strategy_map or {})

    return scheduler


@pytest.fixture
def patched_db(monkeypatch: pytest.MonkeyPatch):
    """`get_today_*_trades(_for_sync)` / `insert_trade` 를 인메모리로 패치."""
    from src.db import trade_history as th
    from src.engine import scanner

    inserted: list[dict[str, Any]] = []
    existing_buys: list[dict[str, Any]] = []
    existing_sells: list[dict[str, Any]] = []

    async def _fake_get_buys(strategy=None):
        return list(existing_buys)

    async def _fake_get_sells(strategy=None):
        return list(existing_sells)

    async def _fake_insert(record):
        inserted.append({
            "ticker": record.ticker,
            "trade_type": record.trade_type.value,
            "price": float(record.price),
            "quantity": record.quantity,
            "strategy": record.strategy,
            "order_no": record.order_no,
            "profit_loss": record.profit_loss,
        })

    async def _fake_get_buys_for_sync(ticker=None):
        return list(existing_buys)

    async def _fake_get_sells_for_sync(ticker=None):
        return list(existing_sells)

    monkeypatch.setattr(th, "get_today_buy_trades", _fake_get_buys)
    monkeypatch.setattr(th, "get_today_sell_trades", _fake_get_sells)
    monkeypatch.setattr(th, "insert_trade", _fake_insert)
    monkeypatch.setattr(th, "get_today_buy_trades_for_sync", _fake_get_buys_for_sync, raising=False)
    monkeypatch.setattr(th, "get_today_sell_trades_for_sync", _fake_get_sells_for_sync, raising=False)
    monkeypatch.setattr(scanner, "ticker_names", {}, raising=False)

    return SimpleNamespace(inserted=inserted, existing_buys=existing_buys, existing_sells=existing_sells)


def _buy_order(ticker: str, order_no: str, qty: str = "10", price: str = "70000") -> dict:
    return {
        "pdno": ticker,
        "tot_ccld_qty": qty,
        "sll_buy_dvsn_cd": "02",
        "avg_prvs": price,
        "odno": order_no,
        "prdt_name": ticker,
    }


def _sell_order(ticker: str, order_no: str, qty: str = "10", price: str = "70000") -> dict:
    return {
        "pdno": ticker,
        "tot_ccld_qty": qty,
        "sll_buy_dvsn_cd": "01",
        "avg_prvs": price,
        "odno": order_no,
        "prdt_name": ticker,
    }


@pytest.mark.asyncio
async def test_order_no_mapping_used_when_db_has_no_record_buy(patched_db):
    """DB 에 당일 매수 기록이 없는(가장 흔한) 매수는 order_no 매핑을 쓴다."""
    scheduler = _make_scheduler(order_strategy_map={"0000009999": "kojiro"})

    await scheduler._sync_orders_to_db([_buy_order("005930", "0000009999")])

    inserted = patched_db.inserted
    assert len(inserted) == 1
    assert inserted[0]["strategy"] == "kojiro", (
        f"DB 기록이 없으면 order_no 매핑을 써야 한다. 실제: {inserted[0]['strategy']}"
    )


@pytest.mark.asyncio
async def test_order_no_mapping_used_when_db_has_no_record_sell(patched_db):
    """DB 에 당일 매수 기록도, registry 보유도 없는 매도는 order_no 매핑을 쓴다."""
    scheduler = _make_scheduler(order_strategy_map={"0000008888": "donchian_swing"})

    await scheduler._sync_orders_to_db([_sell_order("005930", "0000008888")])

    inserted = patched_db.inserted
    assert len(inserted) == 1
    assert inserted[0]["strategy"] == "donchian_swing"


@pytest.mark.asyncio
async def test_db_record_has_priority_over_order_no_mapping(patched_db):
    """DB(당일 같은 티커 매수 기록)가 있으면 order_no 매핑보다 우선한다."""
    patched_db.existing_buys.append({
        "ticker": "005930", "order_no": "0000001111", "strategy": "vcp_breakout", "trade_type": "BUY",
    })
    scheduler = _make_scheduler(order_strategy_map={"0000009999": "kojiro"})

    await scheduler._sync_orders_to_db([_buy_order("005930", "0000009999")])

    inserted = patched_db.inserted
    assert len(inserted) == 1
    assert inserted[0]["strategy"] == "vcp_breakout", (
        f"DB 출처가 order_no 매핑보다 우선해야 한다. 실제: {inserted[0]['strategy']}"
    )


@pytest.mark.asyncio
async def test_registry_position_overrides_order_no_mapping_for_sell(patched_db):
    """매도는 registry 라이브 포지션(정확한 buy_price)이 order_no 매핑보다 최종 권위다."""
    scheduler = _make_scheduler(
        order_strategy_map={"0000007777": "momentum"},  # 매핑은 있지만 틀렸다고 가정
        positions_by_strategy={
            "kojiro": {"005930": SimpleNamespace(buy_price=65000)},
        },
    )

    await scheduler._sync_orders_to_db([_sell_order("005930", "0000007777", qty="10", price="70000")])

    inserted = patched_db.inserted
    assert len(inserted) == 1
    assert inserted[0]["strategy"] == "kojiro"
    assert inserted[0]["profit_loss"] == (70000 - 65000) * 10


@pytest.mark.asyncio
async def test_fallback_to_momentum_with_warning_when_no_source(patched_db, caplog):
    """DB·매핑 둘 다 없으면 momentum 폴백 + [sync_strategy_unknown] WARNING(ticker·order_no)."""
    import logging
    scheduler = _make_scheduler(order_strategy_map={})

    with caplog.at_level(logging.WARNING, logger="src.engine.scheduler"):
        await scheduler._sync_orders_to_db([_buy_order("005930", "0000005555")])

    inserted = patched_db.inserted
    assert len(inserted) == 1
    assert inserted[0]["strategy"] == "momentum"

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    matched = [r for r in warnings if "[sync_strategy_unknown]" in r.getMessage()]
    assert matched, f"매핑 출처 전부 미확보 시 WARNING 이 있어야 한다. 실제 로그: {[r.getMessage() for r in warnings]}"
    msg = matched[0].getMessage()
    assert "005930" in msg
    assert "0000005555" in msg


@pytest.mark.asyncio
async def test_no_warning_when_order_no_mapping_resolves(patched_db, caplog):
    """order_no 매핑으로 해결되면 [sync_strategy_unknown] 경보가 없다(과잉 경보 금지)."""
    import logging
    scheduler = _make_scheduler(order_strategy_map={"0000009999": "kojiro"})

    with caplog.at_level(logging.WARNING, logger="src.engine.scheduler"):
        await scheduler._sync_orders_to_db([_buy_order("005930", "0000009999")])

    matched = [r for r in caplog.records if "[sync_strategy_unknown]" in r.getMessage()]
    assert not matched, f"매핑이 해결됐는데 경보가 발화했다: {[r.getMessage() for r in matched]}"


@pytest.mark.asyncio
async def test_missing_order_engine_attribute_falls_back_gracefully(patched_db):
    """`order_engine` 속성 자체가 없는 구형 스텁도 AttributeError 없이 momentum 폴백."""
    scheduler = _make_scheduler(with_order_engine=False)
    assert not hasattr(scheduler, "order_engine")

    await scheduler._sync_orders_to_db([_buy_order("005930", "0000001234")])

    inserted = patched_db.inserted
    assert len(inserted) == 1
    assert inserted[0]["strategy"] == "momentum"


@pytest.mark.asyncio
async def test_corrupted_empty_string_mapping_treated_as_missing(patched_db, caplog):
    """매핑 값이 빈 문자열이면 '있다'로 오판하지 않고 미확보(경보 + momentum)로 취급."""
    import logging
    scheduler = _make_scheduler(order_strategy_map={"0000004444": ""})

    with caplog.at_level(logging.WARNING, logger="src.engine.scheduler"):
        await scheduler._sync_orders_to_db([_buy_order("005930", "0000004444")])

    inserted = patched_db.inserted
    assert len(inserted) == 1
    assert inserted[0]["strategy"] == "momentum"
    matched = [r for r in caplog.records if "[sync_strategy_unknown]" in r.getMessage()]
    assert matched, "빈 문자열 매핑은 미확보로 취급해 경보가 발화해야 한다"
