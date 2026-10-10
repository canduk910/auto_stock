"""cycle385 부록 R-1 — F-1 재대조(#1.5)와 늦은 체결통보의 **이중 차감** (TR1~TR12).

명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md` 부록 R-1 · R-7 · R-9
사용자 전제(2026-09-26) = 「잔여보유수량에 대한 추가매도가 가능하도록 실시간잔고의
매도상황을 추적관리」 → R-INV-1 **추적 밖 실보유 0**(과소 추적 금지, 과대는 허용).

## 결함 (B7 구현 위)

```
kojiro 추적 10 · 계좌 10.  MTS 3주 전량 체결(거래소) → 계좌 7, 통보는 아직 오는 중
손절 send 10 → APBK0400
  #1.5 get_balance → held 7 → [sell_qty_reconciled] pos.quantity = 7
  ◀ 늦은 MTS 통보 3 → B7 보유 축이 다시 뺀다: 7 → 4
  재발사 4 → 체결 → 추적 0, 계좌 3 = 손절 밖 3주
```

HEAD 는 그 통보를 momentum 폴백으로 흘려 우연히 7 을 쐈다(프로브 test_p1: HEAD `[10,7]`
/ B7 `[10,4]`). B7 이 소유자를 제대로 찾으면서 이중 차감이 드러났다.

## 시정 (R-1)

재대조 때 TTTC0081R(`get_daily_orders(pdno=ticker)`, **잔고 뒤**)로 **주문별로 「스냅샷에
이미 반영된 체결」** 을 크레딧으로 적고, 늦게 온 통보는 **자기 주문의** 크레딧을 먼저
소진한 뒤 초과분만 보유에서 뺀다. 조회를 못 믿으면(예외·불량 행·1쪽 가득) 종목 단위
크레딧 `pos − held` 로 간다(과대 방향). 손익은 흡수분도 그대로 센다.

## 부록 R2 (2차 검토) 뒤 — 재대조는 「오늘 주문으로 설명되지 않는 차이」 에만

분기 술어가 `held ≥ eff`(`eff = 추적 − 아직 안 온 외부 체결 통보`)로 바뀌어, 오늘 주문 행으로
설명되는 차이는 재대조가 아니라 F-3 로 간다(`test_cycle385r2_round2.py` TQ1·TQ20). 그래서 재대조
분기를 재는 TR1·TR4·TR9·TR10 은 추적을 **12(유령 2)** 로 둔다 — 행으로 설명되지 않는 2 가 있어야
재대조가 돈다. 종목 크레딧은 누적한다(R2-7).

🔴 잔고는 `src.api.balance.get_balance`, 주문 목록은 `src.api.balance.get_daily_orders` 를
**반드시** 패치한다(미패치면 실제 KIS 경로를 탄다 — 네트워크 차단 픽스처가 막지만 판정이 흐려진다).
🔴 caplog 단언은 WARNING 이상 + prefix(CI 루트 로거 DEBUG — cycle252 T2). INFO 마커는
레벨 **정확히 INFO** + 앞머리로 한정한다.
🔴 새 심볼은 모듈 최상단에서 import 하지 않는다 — 구현 전 수집 에러로 전 파일이 뭉개지면
어느 행위가 붉은지 가려지지 않는다(순수 함수 단위 테스트는 함수 안에서 import).
"""
from __future__ import annotations

import logging
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.base import KisApiError
from src.engine.strategy_base import Position, Signal
from tests.unit.engine.test_cycle385_b7_partial_sell import (
    BUY_PRICE,
    FILL_PRICE,
    TICKER,
    _held,
    _install_place_order,
    _make_env,
    _map_order,
    _sell_notice,
    _warn_lines,
)

pytestmark = pytest.mark.unit

_OE_LOGGER = "src.engine.order_engine"

#: 외부(MTS) 매도 주문번호. 0-패딩 정규화 키(`_odno_key`)는 앞 0 을 뗀 값이다.
MTS_NO = "0000031001"
MTS_KEY = "31001"
#: `_install_place_order` 가 두 번째 발사(첫 발사는 APBK0400)에 붙이는 번호.
OUR_RESEND_NO = "SELL-000002"


@pytest.fixture
def drain():
    """남은 30초 재주문 타이머 정리 — 'Task was destroyed' 경고 차단."""
    engines: list = []
    yield engines
    for eng in engines:
        for task in list(eng._pending_cancel_tasks.values()):
            task.cancel()
        eng._pending_cancel_tasks.clear()


def _env(monkeypatch, drain, holdings):
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "SELL_RETRY_DELAY", 0)
    env = _make_env(monkeypatch, holdings=holdings)
    drain.append(env.engine)
    return env


def _apbk0400() -> KisApiError:
    return KisApiError(rt_cd="1", msg_cd="APBK0400", msg1="주문 가능한 수량을 초과했습니다.")


def _row(odno: str, qty, *, pdno: str = TICKER, side: str = "01") -> dict:
    """TTTC0081R `output1` 한 행(쓰는 네 필드만)."""
    return {
        "odno": odno, "pdno": pdno, "sll_buy_dvsn_cd": side,
        "tot_ccld_qty": qty if isinstance(qty, str) else str(qty),
    }


def _patch_balance(monkeypatch, *, held: int, sellable: int) -> AsyncMock:
    import src.api.balance as bal

    h = SimpleNamespace(ticker=TICKER, quantity=held, sellable_quantity=sellable)
    spy = AsyncMock(return_value=([h], SimpleNamespace(net_asset=0)))
    monkeypatch.setattr(bal, "get_balance", spy)
    return spy


def _patch_orders(monkeypatch, rows=None, *, side_effect=None) -> AsyncMock:
    import src.api.balance as bal

    spy = AsyncMock(return_value=[] if rows is None else rows, side_effect=side_effect)
    monkeypatch.setattr(bal, "get_daily_orders", spy)
    return spy


def _inject_on_first_save(monkeypatch, make_coro) -> None:
    """재대조의 `save_position` await 안에서(= 재대조 **뒤**) 코루틴 하나를 먼저 돌린다.

    늦은 통보가 재대조 직후 착지하는 순서를 결정론적으로 만든다(프로브 test_p1 형태).
    """
    import src.db.positions as positions_mod

    orig = positions_mod.save_position
    fired = {"n": 0}

    async def save_then(*a, **k):
        await orig(*a, **k)
        if fired["n"] == 0:
            fired["n"] = 1
            await make_coro()

    monkeypatch.setattr(positions_mod, "save_position", save_then)


def _sent(env) -> list[int]:
    return [c["quantity"] for c in env.calls.place]


def _info_lines(caplog, prefix: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.name == _OE_LOGGER and r.levelno == logging.INFO
        and r.getMessage().startswith(prefix)
    ]


def _tracked_total(env) -> int:
    return sum(
        s.state.positions[TICKER].quantity for s in env.s.values()
        if TICKER in s.state.positions
    )


# ════════════════════════════════════════════════════════════════════════════
# TR1 (test_p1 이식) — 재대조 뒤 늦은 외부 통보는 흡수된다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row_no, notice_no",
    [(MTS_NO, MTS_NO), (MTS_NO, MTS_KEY)],
    ids=["same_format", "zero_padding_differs"],
)
async def test_tr1_recount_then_late_external_notice_is_absorbed(
    monkeypatch, caplog, drain, row_no, notice_no,
):
    """🔴 TR1 — 추적 12(유령 2) · 실보유 7(MTS 3 체결, 통보 비행 중). 재대조 뒤 그 통보가 와도
    추적은 7 에 머물고, 재발사는 **7** 이다.

    B7: 7 → 4 로 한 번 더 빼서 재발사 4 → 체결 뒤 계좌 3주가 손절 밖에 남는다.
    두 번째 변형 = 통보 주문번호와 TTTC0081R `odno` 의 0-패딩이 달라도 같은 주문이다(R-1-2).
    부록 R2 — 유령 2 가 있어야 `held 7 < eff 9` 로 재대조가 돈다(추적 10 이면 F-3 경로 — TQ20).
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 12})
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    _patch_balance(monkeypatch, held=7, sellable=7)
    orders = _patch_orders(monkeypatch, [_row(row_no, 3)])
    _inject_on_first_save(monkeypatch, lambda: _sell_notice(env, notice_no, 3, payload=3))

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert _sent(env) == [12, 7], (
        f"발사 {_sent(env)} (기대 [12, 7]) — 재대조 스냅샷에 이미 반영된 MTS 3주를 늦은 "
        "통보가 다시 뺐다(이중 차감 → 손절 밖 실보유)"
    )
    assert _held(env, "kojiro") == 7
    assert orders.await_count == 1, "재대조가 주문 목록(TTTC0081R)을 조회하지 않았다"
    assert orders.await_args.kwargs.get("pdno") == TICKER, (
        f"주문 목록 조회 인자 {orders.await_args}: `pdno=ticker` 로 그 종목만 조회한다(R-1-7)"
    )
    absorbed = _warn_lines(caplog, "[sell_fill_credit_absorbed]")
    assert len(absorbed) == 1 and "absorbed_order=3" in absorbed[0], absorbed

    # 우리 재발사 7 체결(map) → 닫힘
    await _sell_notice(env, OUR_RESEND_NO, 7, payload=7)
    assert _held(env, "kojiro") is None, "실보유 0 인데 추적이 남았다"
    assert TICKER not in env.engine._selling
    assert env.s["kojiro"].state.daily_realized_pnl == 10 * (FILL_PRICE - BUY_PRICE), (
        "흡수분도 실제로 판 주식이다 — 손익은 체결 증분(quantity) 기준으로 10주분이어야 한다"
    )


# ════════════════════════════════════════════════════════════════════════════
# TR2 (repro 이식) — 재대조 → 부분 잠김 옆 잔여 발사 → 어느 순간도 과소 추적 없음
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tr2_recount_then_partial_lock_sells_remainder_never_under_tracks(
    monkeypatch, drain,
):
    """🔴 TR2 — 추적 10 · 거래소 보유 7(A 3 체결, 통보 비행 중) · 걸린 MTS B 2(잠김 2).

    기대: 발사 `[10, 5]` — 10 거부 → 부록 R2 F-3(pending A 3 → eff 7 → surplus 0 → fire 5).
    오늘 주문으로 설명되는 차이라 재대조 단계가 없다. 그 뒤 어느 통보 순서에서도
    `추적 ≥ 거래소 보유`, 끝에 둘 다 0.

    B7: A 통보가 7 → 4, B 가 4 → 2 로 만들어 거래소 5 · 추적 2 = 손절 밖 3주(repro).
    """
    from src.models.order import OrderResult
    import src.api.balance as bal
    import src.engine.order_engine as _oe

    env = _env(monkeypatch, drain, {"kojiro": 10})
    ex = SimpleNamespace(held=7, locked=2, b_filled=0, n=0)
    sent: list[int] = []

    async def place_order(ticker, side, quantity, price=0, **kw):
        sent.append(quantity)
        if quantity > ex.held - ex.locked:
            raise _apbk0400()
        ex.locked += quantity
        ex.n += 1
        return OrderResult(order_no=f"OUR-{ex.n}", order_time="100501", krx_org_no="00950")

    async def get_balance(*a, **k):
        h = SimpleNamespace(ticker=TICKER, quantity=ex.held, sellable_quantity=ex.held - ex.locked)
        return [h], SimpleNamespace(net_asset=0)

    async def get_daily_orders(*a, **k):
        return [_row("0000070001", 3), _row("0000070002", ex.b_filled)]

    monkeypatch.setattr(_oe, "place_order", place_order)
    monkeypatch.setattr(bal, "get_balance", get_balance)
    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert sent == [10, 5], (
        f"발사 {sent} (기대 [10, 5]) — 오늘 주문으로 설명되는 차이(A 3)를 재대조로 받거나 "
        "부분 잠김(sellable 5)에서 잔여를 팔지 않았다(부록 R2-8)"
    )
    assert _tracked_total(env) >= ex.held

    # A(3) 늦은 통보 — F-3 는 추적을 안 바꿨으므로 이 통보가 추적을 7 로 맞춘다
    await _sell_notice(env, "0000070001", 3, payload=3)
    assert _tracked_total(env) == 7 >= ex.held, (
        f"A 통보 뒤 추적 {_tracked_total(env)} · 거래소 {ex.held}"
    )
    # 우리 5 체결
    ex.held -= 5
    ex.locked -= 5
    await _sell_notice(env, "OUR-1", 5, payload=5)
    assert _tracked_total(env) >= ex.held == 2
    # B(2) 체결
    ex.held -= 2
    ex.locked -= 2
    ex.b_filled = 2
    await _sell_notice(env, "0000070002", 2, payload=2)
    assert _tracked_total(env) == ex.held == 0, (
        f"거래소 {ex.held} · 추적 {_tracked_total(env)} — 끝에 둘이 같아야 한다"
    )
    assert _held(env, "kojiro") is None
    assert TICKER not in env.engine._selling


# ════════════════════════════════════════════════════════════════════════════
# TR3 — 원장(`_sell_notice_seen`)이 크레딧을 줄인다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tr3_already_processed_fills_leave_no_credit(monkeypatch, drain):
    """🔴 TR3 — 추적 11 · 실보유 10(오염 1). MTS-A(5주) 중 2 체결·**통보 처리**(추적 9).
    재대조: held 8 · 행 A tot 2 → 크레딧 A = 2 − 2 = 0 → 추적 8. 그 뒤 A 가 3 더 체결 →
    통보 3 → 추적 **5** = 실보유 5.

    크레딧을 `tot_ccld_qty` 로만 적으면(원장 무시, MR3) 그 3 중 2 를 흡수해 추적 7(과대).
    """
    import src.engine.order_engine as _oe

    env = _env(monkeypatch, drain, {"kojiro": 11})
    a_no = "0000080001"
    await _sell_notice(env, a_no, 2, payload=5)
    assert _held(env, "kojiro") == 9

    sent: list[int] = []

    async def place_order(ticker, side, quantity, price=0, **kw):
        sent.append(quantity)
        raise _apbk0400()  # 재대조만 본다

    monkeypatch.setattr(_oe, "place_order", place_order)
    _patch_balance(monkeypatch, held=8, sellable=8)
    _patch_orders(monkeypatch, [_row(a_no, 2)])

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert sent[:2] == [9, 8], f"발사 {sent} — 재대조가 held 8 로 맞추지 않았다"
    assert _held(env, "kojiro") == 8

    await _sell_notice(env, a_no, 3, payload=5)
    assert _held(env, "kojiro") == 5, (
        f"추적 {_held(env, 'kojiro')} (기대 5 = 실보유) — 이미 처리한 통보분까지 크레딧으로 "
        "적어 뒤 체결을 흡수했다(원장 무시)"
    )


# ════════════════════════════════════════════════════════════════════════════
# TR4 — 크레딧은 주문별이지 종목별이 아니다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tr4_credit_is_per_order_not_per_ticker(monkeypatch, drain):
    """🔴 TR4 — TR1 에서 우리 재발사 체결 7(map)이 MTS 통보보다 **먼저** 온다.

    우리 7 이 MTS 의 크레딧 3 을 먹으면(MR4) 추적 3 이 남는다 = 실보유 0 인데 유령 3주.
    추적 12(유령 2) — 재대조 분기를 타게 한다(부록 R2).
    """
    env = _env(monkeypatch, drain, {"kojiro": 12})
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    _patch_balance(monkeypatch, held=7, sellable=7)
    _patch_orders(monkeypatch, [_row(MTS_NO, 3)])

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert _sent(env) == [12, 7]

    await _sell_notice(env, OUR_RESEND_NO, 7, payload=7)
    assert _held(env, "kojiro") is None, (
        f"우리 7 체결 뒤 추적 {_held(env, 'kojiro')} — 다른 주문(MTS)의 크레딧을 소진했다"
    )
    await _sell_notice(env, MTS_NO, 3, payload=3)  # 흡수만 — 예외 0
    assert _tracked_total(env) == 0


# ════════════════════════════════════════════════════════════════════════════
# TR5 — 호출 순서: 잔고 먼저, 주문 목록 나중
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tr5_balance_is_read_before_order_list(monkeypatch, drain):
    """🔴 TR5 — 두 조회가 한 거래소를 공유하고, **먼저 불린 쪽**이 스냅샷을 만든 **뒤**
    걸린 B(2)가 체결된다. 정상 순서(잔고 → 주문)면 크레딧이 모자랄 수 없어 과대만 생긴다
    (추적 7 · 실보유 5). 순서가 뒤집히면 B 크레딧 0 · held 5 → 통보 뒤 추적 3 < 5.
    """
    import src.api.balance as bal

    env = _env(monkeypatch, drain, {"kojiro": 10})
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    a_no, b_no = "0000090001", "0000090002"
    ex = SimpleNamespace(held=7, locked_b=2, b_filled=0, fired=False)

    def _fill_b_after_first_query():
        if not ex.fired:
            ex.fired = True
            ex.held -= 2
            ex.locked_b = 0
            ex.b_filled = 2

    async def get_balance(*a, **k):
        h = SimpleNamespace(ticker=TICKER, quantity=ex.held,
                            sellable_quantity=ex.held - ex.locked_b)
        _fill_b_after_first_query()
        return [h], SimpleNamespace(net_asset=0)

    async def get_daily_orders(*a, **k):
        rows = [_row(a_no, 3), _row(b_no, ex.b_filled)]
        _fill_b_after_first_query()
        return rows

    monkeypatch.setattr(bal, "get_balance", get_balance)
    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    await _sell_notice(env, a_no, 3, payload=3)
    await _sell_notice(env, b_no, 2, payload=2)

    assert ex.held == 5
    assert _tracked_total(env) >= ex.held, (
        f"추적 {_tracked_total(env)} < 실보유 {ex.held} — 주문 목록을 잔고보다 먼저 읽어 "
        "그 사이 체결의 크레딧이 모자랐다(R-1-6 순서 계약)"
    )


# ════════════════════════════════════════════════════════════════════════════
# TR6 — await 뒤 동일성 재검증 (닫힌 포지션을 되살리지 않는다)
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tr6_position_closed_during_order_query_is_not_resurrected(
    monkeypatch, caplog, drain,
):
    """🔴 TR6 — 주문 목록 조회 await 안에서 전량 매도 통보가 와 포지션이 닫혔다.
    재대조는 그 분리된 객체에 held 를 쓰지 않고(`save_position` 0 = DB 행 부활 없음)
    `[sell_qty_reconcile_skipped] reason=position_replaced` → 루프 상단 재조회가
    `[sell_position_gone]` 으로 끝낸다.
    """
    import src.api.balance as bal

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    _map_order(env, "S-OLD", 10, "kojiro")  # 앞서 나가 있던 우리 전량 매도
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    _patch_balance(monkeypatch, held=7, sellable=7)

    async def orders_while_closing(*a, **k):
        await _sell_notice(env, "S-OLD", 10, payload=10)
        return []

    monkeypatch.setattr(bal, "get_daily_orders", orders_while_closing)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert _held(env, "kojiro") is None
    assert env.calls.save == [], (
        f"닫힌 포지션의 분리된 객체로 `save_position` {len(env.calls.save)}회 — DB 행 부활"
    )
    assert _sent(env) == [10], f"발사 {_sent(env)} — 포지션이 사라졌는데 재발사했다"
    skipped = _info_lines(caplog, "[sell_qty_reconcile_skipped]")
    assert len(skipped) == 1 and "reason=position_replaced" in skipped[0], skipped
    assert _info_lines(caplog, "[sell_position_gone]"), "루프 상단 재조회가 소멸을 처리하지 않았다"
    assert TICKER not in env.engine._selling


# ════════════════════════════════════════════════════════════════════════════
# TR7 · TR8 — 주문 목록을 못 믿으면 종목 크레딧(과대 방향)으로 재대조는 진행
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tr7_order_query_error_falls_back_to_ticker_credit(monkeypatch, caplog, drain):
    """🔴 TR7 — TTTC0081R 예외 → `[sell_qty_reconcile_orders_unavailable] reason=error
    blind_credit=3` · 재대조는 진행(발사 `[10, 7]`) · 늦은 MTS 통보 흡수 → 7.

    크레딧 없이 재대조(= B7, MR7) → 4 로 이중 차감. 재대조 생략(MR8) → 오염된 10 을 계속 쏜다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    _patch_balance(monkeypatch, held=7, sellable=7)
    _patch_orders(monkeypatch, side_effect=RuntimeError("TTTC0081R down"))
    _inject_on_first_save(monkeypatch, lambda: _sell_notice(env, MTS_NO, 3, payload=3))

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert _sent(env) == [10, 7], f"발사 {_sent(env)} (기대 [10, 7])"
    assert _held(env, "kojiro") == 7
    lines = _warn_lines(caplog, "[sell_qty_reconcile_orders_unavailable]")
    assert len(lines) == 1, lines
    assert "reason=error" in lines[0] and "blind_credit=3" in lines[0], lines
    absorbed = _warn_lines(caplog, "[sell_fill_credit_absorbed]")
    assert len(absorbed) == 1 and "absorbed_blind=3" in absorbed[0], absorbed

    await _sell_notice(env, OUR_RESEND_NO, 7, payload=7)
    assert _held(env, "kojiro") is None
    assert TICKER not in env.engine._sell_blind_credit


@pytest.mark.asyncio
async def test_tr7b_blind_credit_is_not_netted_by_a_later_f3(monkeypatch, drain):
    """🔴 TR7b (부록 R2-8 로 기대값 교체 — TQ5 와 같은 성질) — 1차 재대조는 주문 조회 실패로
    종목 크레딧 3(추적 10 → 7). 2차 거부 뒤 조회가 되살아나면 MTS-1 3 · MTS-2 2 가 pending 5 로
    잡혀 eff 2 → F-3 fire 2(`[10, 7, 2]`). 종목 크레딧은 pending 에서 빼지 않는다(보수 — 빼면 eff 가
    커져 초과분을 작게 본다). 뒤이은 통보: MTS-1 은 종목 크레딧이 흡수, MTS-2 는 보유에서 뺀다.

    원래 성질(「조회 성공 재대조는 앞선 종목 크레딧을 버린다」)은 `test_cycle385r2_round2.py`
    TQ5b 가 잰다.
    """
    import src.api.balance as bal
    import src.engine.order_engine as _oe
    from src.models.order import OrderResult

    env = _env(monkeypatch, drain, {"kojiro": 10})
    mts1, mts2 = "0000031001", "0000031002"

    async def place_order(ticker, side, quantity, price=0, **kw):
        env.calls.place.append({"quantity": quantity})
        if len(env.calls.place) < 3:
            raise _apbk0400()
        return OrderResult(order_no="SELL-000003", order_time="100501", krx_org_no="00950")

    snaps = iter([(7, 7), (5, 5)])

    async def get_balance(*a, **k):
        held, sellable = next(snaps)
        return [SimpleNamespace(ticker=TICKER, quantity=held, sellable_quantity=sellable)], \
            SimpleNamespace(net_asset=0)

    answers = iter([RuntimeError("TTTC0081R down"), [_row(mts1, 3), _row(mts2, 2)]])

    async def get_daily_orders(*a, **k):
        ans = next(answers)
        if isinstance(ans, Exception):
            raise ans
        return ans

    monkeypatch.setattr(_oe, "place_order", place_order)
    monkeypatch.setattr(bal, "get_balance", get_balance)
    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert _sent(env) == [10, 7, 2], f"발사 {_sent(env)} (기대 [10, 7, 2])"
    assert _held(env, "kojiro") == 7, "F-3 는 추적을 바꾸지 않는다"
    await _sell_notice(env, mts1, 3, payload=3)
    assert _held(env, "kojiro") == 7, "MTS-1 은 1차 재대조의 종목 크레딧이 흡수해야 한다"
    await _sell_notice(env, mts2, 2, payload=2)
    assert _held(env, "kojiro") == 5
    await _sell_notice(env, "SELL-000003", 2, payload=2)
    assert _held(env, "kojiro") == 3, (
        f"실보유 3(10 − 3 − 2 − 2) 인데 추적 {_held(env, 'kojiro')}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rows, reason",
    [
        ([_row(MTS_NO, "")], "bad_row"),
        ([_row("", 3)], "bad_row"),
        ([_row(MTS_NO, "3주")], "bad_row"),
    ],
    ids=["qty_blank", "odno_blank", "qty_not_int"],
)
async def test_tr8_untrusted_rows_fall_back_to_ticker_credit(
    monkeypatch, caplog, drain, rows, reason,
):
    """🔴 TR8 (cycle432 로 `page_full` 사례 제거 — 쪽 크기 판정 자체가 없다) — 행 불량
    (수량 공백·비정수, 주문번호 공백)은 **전체를 못 믿는다** → TR7 과 같은 결과 +
    `reason=`. 불량 행을 0 으로 읽으면(MR9) 그 주문 크레딧이 빠져 늦은 통보가
    이중 차감된다(부분 신뢰 금지 — R-1-4 4)."""
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    _patch_balance(monkeypatch, held=7, sellable=7)
    _patch_orders(monkeypatch, rows)
    _inject_on_first_save(monkeypatch, lambda: _sell_notice(env, MTS_NO, 3, payload=3))

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert _sent(env) == [10, 7], f"발사 {_sent(env)} (기대 [10, 7])"
    assert _held(env, "kojiro") == 7
    lines = _warn_lines(caplog, "[sell_qty_reconcile_orders_unavailable]")
    assert len(lines) == 1 and f"reason={reason}" in lines[0] and "blind_credit=3" in lines[0], lines


# ════════════════════════════════════════════════════════════════════════════
# TR9 — SOR: 같은 주문번호 여러 행은 합
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tr9_same_order_rows_are_summed(monkeypatch, drain):
    """🔴 TR9 — 같은 `odno` 두 행 tot 1·2 → 크레딧 3 → 통보 1·2 모두 흡수 → 7.

    마지막 행만 읽으면(MR10) 크레딧 2 → 1주 이중 차감 → 재발사 6. 추적 12(유령 2 — 부록 R2).
    """
    env = _env(monkeypatch, drain, {"kojiro": 12})
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    _patch_balance(monkeypatch, held=7, sellable=7)
    _patch_orders(monkeypatch, [_row(MTS_NO, 1), _row(MTS_NO, 2)])

    async def two_notices():
        await _sell_notice(env, MTS_NO, 1, payload=3)
        await _sell_notice(env, MTS_NO, 2, payload=3)

    _inject_on_first_save(monkeypatch, two_notices)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert _sent(env) == [12, 7], f"발사 {_sent(env)} (기대 [12, 7])"
    assert _held(env, "kojiro") == 7


# ════════════════════════════════════════════════════════════════════════════
# TR10 — 클라이언트 필터: 그 종목의 매도 행만
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tr10_other_ticker_and_buy_rows_do_not_become_credit(monkeypatch, drain):
    """🔴 TR10 — 서버가 `PDNO` 를 무시해 다른 종목 Y 의 매도 Z(tot 3, 통보 미처리)와 이
    종목의 **매수** 행이 섞여 와도 크레딧은 이 종목 매도 주문에만 적힌다. 뒤이은 Y 통보
    Z 3 → momentum 의 Y 5 → **2**.

    필터를 빼면(MR11) Z 가 크레딧이 돼 Y 통보를 흡수 → Y 추적 5 인데 실보유 2 = 과대가 아니라
    **다른 종목 장부 오염**이다. 추적 12(유령 2 — 재대조 분기, 부록 R2).
    """
    env = _env(monkeypatch, drain, {"kojiro": 12})
    y = "000660"
    env.s["momentum"].state.positions[y] = Position(
        ticker=y, buy_price=BUY_PRICE, quantity=5, order_no="BUY-Y",
        strategy_id="momentum", buy_date=date(2026, 9, 21),
    )
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    _patch_balance(monkeypatch, held=7, sellable=7)
    _patch_orders(monkeypatch, [
        _row(MTS_NO, 3),
        _row("0000049001", 3, pdno=y),
        _row("0000050001", 4, side="02"),
    ])

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    credit = env.engine._sell_reflected_credit
    assert "49001" not in credit, f"다른 종목 주문이 크레딧으로 적혔다: {credit}"
    assert "50001" not in credit, f"매수 주문이 매도 크레딧으로 적혔다: {credit}"
    assert credit.get(MTS_KEY) == 3, credit

    await env.engine.handle_execution_notice(
        ticker=y, order_no="0000049001", side="SELL", price=FILL_PRICE, quantity=3,
        ordered_qty_payload=3,
    )
    assert env.s["momentum"].state.positions[y].quantity == 2, (
        "다른 종목의 매도 통보가 이 종목 재대조 크레딧에 흡수됐다"
    )


# ════════════════════════════════════════════════════════════════════════════
# TR11 — 보유 축이 닫힐 때 종목 크레딧 정리
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tr11_ticker_credit_is_dropped_when_the_holding_closes(monkeypatch, drain):
    """🔴 TR11 → cycle429(D1 안A, 사용자 승인 2026-10-10) 로 재조준.

    종목 크레딧(조회 실패)이 남은 채 실보유 0 거부가 뜨면, D1 이전엔 insufficient
    삭제 경로가 포지션을 지웠다. 이제는 자동 삭제가 없다 — 포지션이 **보존**된
    채로 뒤늦은 외부 통보가 그 주문을 **닫으면**(보유 축이 0 이 되면) 남은 종목
    크레딧도 지운다는 것만 확인한다.

    지우지 않으면(MR12) 하루 안에 같은 종목의 다음 매도 통보를 조용히 흡수한다.
    ⚠️ 보유가 있는 채로 닫히면 흡수 규칙상 종목 크레딧은 이미 0 이다(`hold_dec>0` ⇒ 전부
    소진) — 닫기 묶음의 정리가 의미를 갖는 것은 이 「보유 없는 종료」 경로다.
    """
    import src.api.balance as bal

    env = _env(monkeypatch, drain, {"kojiro": 10})

    async def always_reject(*a, **k):
        env.calls.place.append({"quantity": k.get("quantity")})
        raise _apbk0400()

    import src.engine.order_engine as _oe
    monkeypatch.setattr(_oe, "place_order", always_reject)
    snapshots = iter([(7, 7)])

    async def get_balance(*a, **k):
        held, sellable = next(snapshots, (0, 0))
        hs = [SimpleNamespace(ticker=TICKER, quantity=held, sellable_quantity=sellable)]
        return (hs if held else []), SimpleNamespace(net_asset=0)

    monkeypatch.setattr(bal, "get_balance", get_balance)
    _patch_orders(monkeypatch, side_effect=RuntimeError("TTTC0081R down"))

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    # D1 안A — 자동 삭제 경로가 없다. 실보유 0(설명 안 됨)은 포지션을 보존하고
    # 5분 진입 차단만 건다(첫 재시도의 재대조가 pos.quantity 를 7 로, 종목
    # 크레딧(`_sell_blind_credit`)을 3 으로 남긴 뒤).
    held = _held(env, "kojiro")
    assert held == 7, "D1 안A — 자동 삭제 없음, 재대조된 수량 7 이 보존돼야 한다"
    assert TICKER in env.engine._sell_rejection._blocked_until
    assert env.engine._sell_blind_credit.get(TICKER) == 3

    # 종목 크레딧 3 을 흡수하고 남은 보유(7)를 정확히 닫으려면 통보 수량 10
    # (= hold_dec 7 + 흡수 3)이 필요하다 — `hold_dec = quantity - min(quantity, blind_credit)`.
    await _sell_notice(env, MTS_NO, 10, payload=10)
    assert _held(env, "kojiro") is None, "전량 통보가 보유 축을 닫아야 한다"
    assert TICKER not in env.engine._sell_blind_credit, (
        f"닫힘 뒤 종목 크레딧 {env.engine._sell_blind_credit.get(TICKER)} 이 남았다"
    )


# ════════════════════════════════════════════════════════════════════════════
# TR12 — 일일 정리
# ════════════════════════════════════════════════════════════════════════════
_R_STRUCTS = (
    ("_sell_notice_seen", lambda o: o.__setitem__("31001", 3)),
    ("_sell_reflected_credit", lambda o: o.__setitem__("31001", 3)),
    ("_sell_blind_credit", lambda o: o.__setitem__(TICKER, 3)),
    ("_manual_sell_orders", lambda o: o.__setitem__("31001", True)),
    ("_selling_locked_wait", lambda o: o.add(TICKER)),
)


@pytest.mark.parametrize("name, fill", _R_STRUCTS, ids=[n for n, _ in _R_STRUCTS])
def test_tr12_reset_daily_state_clears_r_structures(name, fill):
    """🔴 TR12 — 주문번호는 하루 단위로만 유일하다(`_order_division` 선례). 정산 뒤 남으면
    다음 날 같은 번호의 통보를 흡수하거나 manual 표식·동결 표식을 오판한다.
    (`_sell_orders_done` 은 부록 R2 가 소유 규칙과 함께 지웠다.)"""
    from src.engine.order_engine import OrderEngine
    from src.engine.strategy_registry import StrategyRegistry

    eng = OrderEngine(StrategyRegistry())
    obj = getattr(eng, name)
    fill(obj)
    assert obj
    eng.reset_daily_state()
    assert not getattr(eng, name), f"`reset_daily_state()` 뒤 `{name}` 이 비지 않았다"


# ════════════════════════════════════════════════════════════════════════════
# 순수 함수 — 파서 · 주문번호 정규화 (R-1-2 · R-1-4)
# ════════════════════════════════════════════════════════════════════════════
def test_tr_parser_filters_sums_and_refuses_partial_trust():
    """🔴 R-1-4 (cycle432 — `page_size` 인자·쪽 가득 판정 제거) — 이 종목 매도만 ·
    같은 주문 합 · 필터를 통과한 행 하나라도 불량(주문번호 공백 · 수량
    공백/비정수)이면 전체 None · list 아님이면 None · 예외를 던지지 않는다.
    행 수 자체는 더는 못 믿을 이유가 아니다(연속조회가 전 쪽을 이어 붙인다)."""
    from src.engine.order_engine import _sell_fills_by_order as parse

    rows = [
        _row("0000031001", 1), _row("31001", 2),          # 같은 주문(패딩 차이) — 합
        _row("0000031002", 0),                             # 정정·취소 — 0 은 무해
        _row("0000049001", 3, pdno="000660"),              # 다른 종목 — 무시
        _row("0000050001", 4, side="02"),                  # 매수 — 무시
        _row("0000050002", "", pdno="000660"),             # 다른 종목의 불량 행 — 무시(필터 뒤 검사)
    ]
    assert parse(rows, TICKER) == {"31001": 3, "31002": 0}
    assert parse([], TICKER) == {}
    assert parse(None, TICKER) is None
    assert parse({"output1": []}, TICKER) is None
    assert parse([_row("0000031001", "")], TICKER) is None
    assert parse([_row("", 1)], TICKER) is None
    # cycle432(뒤집음) — 100행이어도(옛 page_full 임계) 전부 다른 종목이면 그냥 빈 dict.
    assert parse([_row(f"{i:010d}", 1, pdno="000660") for i in range(100)], TICKER) == {}
    # 150행(실전 쪽 크기 초과)이 이 종목 매도면 150건 전부 돌려준다 — 더는 불신하지 않는다.
    assert len(parse([_row(f"{i:010d}", 1) for i in range(150)], TICKER)) == 150
    assert parse(["garbage"], TICKER) in (None, {})  # never-raise(모양 불량 행)


def test_tr_odno_key_absorbs_zero_padding_only():
    """🔴 R-1-2 — 앞 0 · 공백 차이만 흡수하고, 서로 다른 주문번호는 여전히 다르다."""
    from src.engine.order_engine import _odno_key

    assert _odno_key("0000031001") == _odno_key("31001") == _odno_key(" 0000031001 ")
    assert _odno_key("0000031001") != _odno_key("0000031010")
    assert _odno_key("0000000000") == _odno_key("0")
