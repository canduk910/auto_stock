"""cycle379 Red — ⑨A 해제의 장부 표기를 **실 Postgres** 로 왕복시킨다 (명세 §8-2).

단위 쌍 = `tests/unit/engine/test_cycle379_buying_reconcile.py::test_t1_*` (호출 인자만 본다).
여기서는 그 호출이 실제 SQL 로 **자기 주문의 PENDING 한 행만** 바꾸는지 본다.

| # | 시드(같은 종목 437730 · BUY · momentum) | 기대 |
|---|---|---|
| PG1 | A=PENDING(해제 대상) · B=PARTIAL · C=COMPLETED · D=PENDING(80일 전 좌초 행, cycle373 의 07-06 101730 형) | A 만 CANCELLED, B·C·D 불변, 마커 `db=1` |
| PG2 | A=PARTIAL (메모리는 pending · KIS 는 ccld0/rmn0 — 모순 상태) | 메모리는 풀리되 행은 PARTIAL 그대로(`match_partial` 미전달의 실물 증거), 마커 `db=0` |

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""
from __future__ import annotations

import importlib
import logging
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_LEAF = "src.engine.buying_reconcile"
KST = timezone(timedelta(hours=9))
TICKER = "437730"
SID = "momentum"
A, B, C, D = "0000454500", "0000454600", "0000454700", "0000011100"


def _leaf():
    try:
        return importlib.import_module(_LEAF)
    except ModuleNotFoundError as exc:
        pytest.fail(f"[Red] leaf `{_LEAF}` 미구현 — {exc}")


@pytest.fixture(autouse=True)
def _reset_leaf_state():
    def _r() -> None:
        try:
            mod = importlib.import_module(_LEAF)
        except ModuleNotFoundError:
            return
        fn = getattr(mod, "reset_buying_reconcile_state", None)
        if callable(fn):
            fn()

    _r()
    yield
    _r()


def _world():
    from src.engine.order_engine import OrderEngine
    from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    class _Strat(StrategyBase):
        def __init__(self) -> None:
            super().__init__(StrategyConfig(strategy_id=SID, name=SID, params={"exchange": "KRX"}))

        async def prepare(self, *, as_of=None) -> None:  # pragma: no cover
            return None

        def check_buy_signal(self, *a):  # pragma: no cover
            return Signal.NONE

        def check_exit_signal(self, *a):  # pragma: no cover
            return Signal.NONE

        def calc_buy_quantity(self, current_price, ticker=None):  # pragma: no cover
            return 0

    reg = StrategyRegistry()
    s = _Strat()
    reg.register(s)
    eng = OrderEngine(reg)
    s.state.pending_buys.add(TICKER)
    s.state.pending_buy_amounts[TICKER] = 52_400
    eng._order_qty[A] = 1
    eng._order_strategy[A] = SID
    eng._order_ticker[A] = TICKER
    eng._pending_buy_orders[A] = {"ticker": TICKER, "price": 52_400, "quantity": 1, "strategy_id": SID}
    return SimpleNamespace(reg=reg, eng=eng, s=s)


def _patch_kis(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.balance as _bal

    row = {
        "odno": A, "sll_buy_dvsn_cd": "02", "sll_buy_dvsn_cd_name": "현금매수", "pdno": TICKER,
        "ord_qty": "1", "tot_ccld_qty": "0", "rmn_qty": "0", "cncl_cfrm_qty": "0",
        "rjct_qty": "1", "ord_tmd": "094829",
    }

    async def _gdo(target_date: str = "", exchange: str = "ALL", *, odno: str = ""):
        return [dict(row)] if odno in ("", A) else []

    monkeypatch.setattr(_bal, "get_daily_orders", _gdo)
    mod = _leaf()
    if hasattr(mod, "get_daily_orders"):
        monkeypatch.setattr(mod, "get_daily_orders", _gdo)


async def _seed(pg, rows) -> None:
    from src.db import trade_history
    from src.models.trade import TradeRecord, TradeStatus, TradeType

    for order_no, status in rows:
        await trade_history.insert_trade(TradeRecord(
            ticker=TICKER, ticker_name="삼현", trade_type=TradeType.BUY, price=52_400,
            quantity=1, profit_loss=0, status=TradeStatus(status), strategy=SID, order_no=order_no,
        ))


async def _statuses(pg) -> dict[str, str]:
    rows = await pg.fetch(
        "SELECT order_no, status FROM trade_history WHERE ticker = $1 AND trade_type = 'BUY'", TICKER,
    )
    return {r["order_no"]: r["status"] for r in rows}


def _marker(caplog) -> dict[str, str]:
    lines = [
        r.getMessage() for r in caplog.records
        if r.name == _LEAF and r.getMessage().startswith("[buying_reconcile] ")
    ]
    assert len(lines) == 1, lines
    return dict(re.findall(r"(\w+)=(\S+)", lines[0]))


@pytest.mark.asyncio
async def test_pg1_cancelled_touches_only_the_released_orders_pending_row(
    clean_trade_history, monkeypatch, caplog,
) -> None:
    pg = clean_trade_history
    await _seed(pg, [(A, "PENDING"), (B, "PARTIAL"), (C, "COMPLETED"), (D, "PENDING")])
    await pg.execute(
        "UPDATE trade_history SET timestamp = timestamp - interval '80 days' WHERE order_no = $1", D,
    )
    _patch_kis(monkeypatch)
    w = _world()
    caplog.set_level(logging.INFO, logger=_LEAF)

    await _leaf().reconcile_stale_buying(
        w.reg, w.eng, [], now=datetime(2026, 9, 15, 10, 0, 0, tzinfo=KST),
    )

    assert TICKER not in w.s.state.pending_buys
    assert await _statuses(pg) == {
        A: "CANCELLED", B: "PARTIAL", C: "COMPLETED", D: "PENDING",
    }, "자기 주문의 PENDING 한 행만 바뀌어야 한다"
    assert _marker(caplog).get("db") == "1"


@pytest.mark.asyncio
async def test_pg2_partial_row_is_never_flipped_to_cancelled(
    clean_trade_history, monkeypatch, caplog,
) -> None:
    pg = clean_trade_history
    await _seed(pg, [(A, "PARTIAL")])
    _patch_kis(monkeypatch)
    w = _world()
    caplog.set_level(logging.INFO, logger=_LEAF)

    await _leaf().reconcile_stale_buying(
        w.reg, w.eng, [], now=datetime(2026, 9, 15, 10, 0, 0, tzinfo=KST),
    )

    assert await _statuses(pg) == {A: "PARTIAL"}, "match_partial 미전달 — PARTIAL 은 절대 안 뒤집는다"
    assert _marker(caplog).get("db") == "0"
