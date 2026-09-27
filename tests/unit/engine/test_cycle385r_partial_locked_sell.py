"""cycle385 부록 R-2 · R-3 — F-3 걸린 외부 매도 옆 잔여 매도 + (c) `_selling` 해제 (TR13~TR19).

명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md` 부록 R-2 · R-3 · R-7 · R-9
사용자 전제(2026-09-26) = 「잔여보유수량에 대한 추가매도가 가능하도록 실시간잔고의
매도상황을 추적관리」 → R-INV-2 **우리 주문 합 ≤ 추적 수량** · R-INV-3 **잔여는 팔 수 있어야 한다**.

## F-3 (B7 구현 위)

`[sell_qty_partial_locked]`(held ≥ 추적 ∧ 0 < sellable < 추적)은 보존 + `_selling` 유지 +
return 이다. 운영자가 MTS 로 3주 지정가를 걸어 둔 동안 안 잠긴 추적 7주의 손절이 그 주문이
끝날 때까지 멈춘다. 시정 = `fire = sellable − (held − 추적)` 이 1 이상이면 그만큼 판다
(추적은 그대로, 회차 상한 `sell_cap`). 0 이하 또는 `sellable == 0` 이면 현행 동결.
`held − sellable` 은 걸린 매도 **전부**(우리 것 포함)라, 우리 잠긴 주식을 두 번 팔지 않고
운영자 초과분도 건드리지 않는다.

부록 R2-8 — F-3 도 TTTC0081R 을 1건 조회해 아직 안 온 외부 체결 통보(`pending`)를 먼저 빼고
(`eff = 추적 − pending`) 초과분을 잰다. 조회를 못 믿으면 F-3 는 쏘지 않는다(현행 동결).

## (c) LOW #3 — 알려진 한계(부록 R2-1)

주문 축 종료가 **그 종목의 어느 주문이든** 끝나면 `_selling` 을 푼다. 우리 손절이 발사
중인데 MTS 주문 하나가 끝나면 풀리고, 다음 틱이 두 번째 손절을 1차에서 통과시켜 운영자
초과분을 팔 수 있다(R-3-2). 부록 R-3 의 주인 규칙은 수용 기준을 못 맞춰 부록 R2 가 **걷었다**
(B7 해제 의미로 복귀) — TR18 은 strict xfail 로 그 한계를 기록한다. 뒤를 잇는 수단은
「걸린 우리 매도 등록부」(F-385-5).

🔴 caplog 단언은 WARNING 이상 + prefix. INFO 마커는 레벨 정확히 INFO + 앞머리.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.base import KisApiError
from src.engine.strategy_base import Signal
from tests.unit.engine.test_cycle385_b7_partial_sell import (
    TICKER,
    _held,
    _install_place_order,
    _make_env,
    _sell_notice,
    _warn_lines,
)

pytestmark = pytest.mark.unit

_OE_LOGGER = "src.engine.order_engine"


@pytest.fixture
def drain():
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


def _patch_balance(monkeypatch, *, held: int, sellable: int) -> AsyncMock:
    import src.api.balance as bal

    h = SimpleNamespace(ticker=TICKER, quantity=held, sellable_quantity=sellable)
    spy = AsyncMock(return_value=([h], SimpleNamespace(net_asset=0)))
    monkeypatch.setattr(bal, "get_balance", spy)
    return spy


def _patch_orders(monkeypatch) -> AsyncMock:
    import src.api.balance as bal

    spy = AsyncMock(return_value=[])
    monkeypatch.setattr(bal, "get_daily_orders", spy)
    return spy


def _sent(env) -> list[int]:
    return [c["quantity"] for c in env.calls.place]


# ════════════════════════════════════════════════════════════════════════════
# TR13 ~ TR16 — F-3 발사 수량
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tr13_partial_lock_sells_the_unlocked_remainder(monkeypatch, caplog, drain):
    """🔴 TR13 (cycle236 입력) — held 3 · sellable 1 · 추적 3 → 발사 `[3, 1]`.
    추적은 3 그대로(하향 보정 금지 — 걸린 주문이 취소되면 잠긴 2주도 다시 손절 대상),
    `save_position` 0, `[sell_qty_partial_sellable] fire=1`, `_selling` 유지(우리 주문 걸림),
    동결 표식 없음, 주문 목록 조회 1건(`exchange="ALL", pdno=TICKER` — 부록 R2-8, F-3 도
    아직 안 온 외부 체결 통보를 빼려고 조회한다).

    B7: 발사 `[3]` + `[sell_qty_partial_locked]` 동결 → 안 잠긴 1주의 손절이 멈춘다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 3})
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    _patch_balance(monkeypatch, held=3, sellable=1)
    orders = _patch_orders(monkeypatch)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert _sent(env) == [3, 1], (
        f"발사 {_sent(env)} (기대 [3, 1]) — 걸린 외부 매도 옆의 안 잠긴 잔여를 팔지 않았다"
    )
    assert _held(env, "kojiro") == 3, "잠긴 주식까지 추적에서 뺐다(C236-F1 하향 보정 금지)"
    assert env.calls.save == []
    lines = _warn_lines(caplog, "[sell_qty_partial_sellable]")
    assert len(lines) == 1 and "fire=1" in lines[0], lines
    assert not _warn_lines(caplog, "[sell_qty_partial_locked]")
    assert TICKER in env.engine._selling, "우리 1주 주문이 걸렸는데 `_selling` 이 비었다"
    assert TICKER not in env.engine._selling_locked_wait
    assert orders.await_count == 1, (
        f"F-3 주문 조회 {orders.await_count}회 (기대 1 — 부록 R2-8 재대조와 같은 1건)"
    )
    assert orders.await_args.args == () and orders.await_args.kwargs == {
        "exchange": "ALL", "pdno": TICKER,
    }, f"주문 조회 인자 {orders.await_args} — `exchange=\"ALL\", pdno=ticker`(XT-K)"


@pytest.mark.asyncio
async def test_tr14_operator_surplus_is_not_sold(monkeypatch, caplog, drain):
    """🔴 TR14 — 추적 10 · held 15(운영자 초과 5) · sellable 8 → 발사 `[10, 3]`.

    걸린 매도 7 은 「운영자가 전략 몫부터 판다」로 보고 `fire = 8 − 5 = 3`. sellable 전부(8)를
    쏘면(MR16) 우리 주문 + 걸린 매도 = 15 > 추적 10 → 운영자 몫 5주를 우리가 판다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    _patch_balance(monkeypatch, held=15, sellable=8)
    _patch_orders(monkeypatch)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert _sent(env) == [10, 3], f"발사 {_sent(env)} (기대 [10, 3])"
    assert _held(env, "kojiro") == 10
    lines = _warn_lines(caplog, "[sell_qty_partial_sellable]")
    assert len(lines) == 1 and "surplus=5" in lines[0] and "fire=3" in lines[0], lines


@pytest.mark.asyncio
async def test_tr15_surplus_covering_the_locked_orders_freezes(monkeypatch, caplog, drain):
    """🔴 TR15 — 추적 10 · held 15 · sellable 5(재시작으로 매핑 잃은 우리 10 이 걸림) →
    `fire = 5 − 5 = 0` → 발사 `[10]` 뿐 · `[sell_qty_partial_locked] surplus=5 fire=0` ·
    `_selling` 유지 · 동결 표식.

    sellable 을 그대로 쏘거나(MR16) `min(sellable, 추적)` 을 쏘면(MR17) 우리 걸린 10 에
    5 를 더해 운영자 몫 5주를 판다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    _patch_balance(monkeypatch, held=15, sellable=5)
    _patch_orders(monkeypatch)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert _sent(env) == [10], f"발사 {_sent(env)} (기대 [10] — 초과분이 걸린 매도를 덮는다)"
    assert _held(env, "kojiro") == 10
    assert env.calls.save == []
    lines = _warn_lines(caplog, "[sell_qty_partial_locked]")
    assert len(lines) == 1 and "surplus=5" in lines[0] and "fire=0" in lines[0], lines
    assert TICKER in env.engine._selling
    assert TICKER in env.engine._selling_locked_wait, (
        "동결이 기다리는 것은 걸린 주문의 끝이다 — 표식이 없으면 그 외부 종료가 `_selling` 을 못 푼다"
    )


@pytest.mark.asyncio
async def test_tr16_all_locked_keeps_todays_freeze(monkeypatch, caplog, drain):
    """🔵 TR16 — held 3 · sellable 0 → 현행 동결(사용자 지시) + 동결 표식."""
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 3})
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    _patch_balance(monkeypatch, held=3, sellable=0)
    _patch_orders(monkeypatch)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert _sent(env) == [3]
    assert _held(env, "kojiro") == 3
    assert _warn_lines(caplog, "[sell_qty_locked]")
    assert TICKER in env.engine._selling
    assert TICKER in env.engine._selling_locked_wait


# ════════════════════════════════════════════════════════════════════════════
# TR17 — 동결은 외부 종료가 푼다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tracked, held, sellable, ext_no, ext_qty",
    [(10, 15, 5, "0000061001", 10), (3, 3, 0, "0000061002", 3)],
    ids=["tr15_surplus_freeze", "tr16_all_locked"],
)
async def test_tr17_freeze_is_released_by_the_awaited_external_end(
    monkeypatch, drain, tracked, held, sellable, ext_no, ext_qty,
):
    """🔴 TR17 — 동결 뒤 매핑 없는 외부 주문(payload = 수량) 전량 종료 → `_selling`·동결 표식 해제.

    매핑 없는 종료를 절대 안 푸는 구현(MR23)·동결 표식을 안 세우는 구현(MR21)은 그 종료
    뒤에도 `_selling` 이 남아 180초 `selling_reconcile` 까지 손절이 멈춘다.
    """
    env = _env(monkeypatch, drain, {"kojiro": tracked})
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    _patch_balance(monkeypatch, held=held, sellable=sellable)
    _patch_orders(monkeypatch)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert TICKER in env.engine._selling

    await _sell_notice(env, ext_no, ext_qty, payload=ext_qty)

    assert TICKER not in env.engine._selling, "동결이 기다리던 외부 주문이 끝났는데 `_selling` 이 남았다"
    assert TICKER not in env.engine._selling_locked_wait


# ════════════════════════════════════════════════════════════════════════════
# TR18 (test_p3 이식) — 무관한 주문의 종료가 우리 발사 중 `_selling` 을 푼다 = LOW #3 (strict xfail)
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.xfail(
    strict=True,
    reason="LOW #3 알려진 한계 — 부록 R2-1(R-3 주인 규칙 제거), F-385-5 가 생기면 뒤집힌다",
)
@pytest.mark.asyncio
async def test_tr18_unrelated_end_during_our_send_keeps_selling(monkeypatch, drain):
    """🟡 TR18 (부록 R2-1 알려진 한계 — 아래는 한계가 풀렸을 때의 기대 · 부록 R3 K5 로 행위만 잰다) —
    kojiro 10. 우리 손절 `place_order` await 안에서 MTS-9 3 전량 종료.

    반환 뒤 추적 7 · `_selling` 유지 · 곧바로 다시 들어온 손절은 중복 차단(발사 수 불변) · 우리
    주문 10 체결(map) → 닫힘 · `_selling` 해제.

    마커는 단언하지 않는다 — 부록 R 의 `[selling_kept]` 는 AR2-2 가 금지했으므로, 마커를 재면
    LOW #3 이 고쳐져도 이 테스트가 영원히 xfail 로 남는다(XPASS 로 뒤집히는 신호가 죽는다).

    B7: MTS 종료가 `_selling` 을 풀어 두 번째 손절(7)이 우리 걸린 10 위에 1차로 통과한다 —
    운영자 초과분 ≥ 7 이면 그 몫을 판다(R-3-2).
    """
    env = _env(monkeypatch, drain, {"kojiro": 10})

    async def inject(order_no):
        await _sell_notice(env, "0000062009", 3, payload=3)

    _install_place_order(monkeypatch, env, inject=inject)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert _held(env, "kojiro") == 7
    assert TICKER in env.engine._selling, (
        "우리 손절 주문(10)이 걸려 있는데 무관한 MTS 주문의 종료가 `_selling` 을 풀었다"
    )

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert len(env.calls.place) == 1, (
        f"발사 {_sent(env)} — 우리 주문이 걸린 채로 두 번째 손절이 나갔다(우리 주문 합 > 추적)"
    )

    await _sell_notice(env, "SELL-000001", 10, payload=10)
    assert _held(env, "kojiro") is None
    assert TICKER not in env.engine._selling


# ════════════════════════════════════════════════════════════════════════════
# TR19 — 발사 창 안에서 끝난 우리 주문도 그 종료가 푼다(반환 뒤 `_selling` 없음)
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["main", "fallback"])
async def test_tr19_our_order_ended_inside_send_window_releases_after_send(
    monkeypatch, caplog, drain, path,
):
    """🔴 TR19 — 우리 `place_order` await 안에서 **같은 주문번호**의 전량 통보(payload 10,
    매핑 부재 창). 부록 R2 — 주문 축 종료가 조건 없이 `_selling` 을 풀므로 반환 뒤 비어 있다.
    폴백 변형 = 1차 APBK1943 → 지정가 폴백 안에서 전량.

    남으면 열린 주문도 없는데 표식만 남아 `selling_reconcile`(180초)까지 손절이 멈춘다.
    (부록 R 의 `[selling_released_after_window]` 마커는 R2 가 지웠다 — 단언하지 않는다.)
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 10})

    async def inject(order_no):
        await _sell_notice(env, order_no, 10, payload=10)

    first_error = None
    if path == "fallback":
        first_error = KisApiError(rt_cd="1", msg_cd="APBK1943", msg1="시장가호가불가 종목입니다.")
    _install_place_order(monkeypatch, env, inject=inject, first_error=first_error)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert len(env.calls.place) == (1 if path == "main" else 2)
    assert _held(env, "kojiro") is None
    assert TICKER not in env.engine._selling, "발사 창에서 끝난 우리 주문의 `_selling` 이 남았다(좀비)"


# ════════════════════════════════════════════════════════════════════════════
# TR21 — 진입 시 동결 표식 청소 → 부록 R2 에서 `test_cycle385r2_round2.py::test_tq25_*` 로 교체
# (무관 종료는 이제 조건 없이 `_selling` 을 풀므로, 청소의 뜻은 「보유 닫힘 해제가 새 주인을
# 풀지 않는다」 로 옮겨 갔다 — 부록 R2-5).
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tr13b_recount_drops_the_previous_attempt_cap(monkeypatch, caplog, drain):
    """🔴 TR13b (R-2-2 「재대조 분기는 `sell_cap = None`」) — 1차 거부 → F-3 상한 2(held 10 ·
    sellable 2) → 2차 거부 → 그새 외부 주문이 4 체결되고 나머지는 취소돼 held 6 · sellable 6 →
    #1.5 재대조(추적 10 → 6)가 **새 절대 상태**다. 3차는 6 을 판다.

    이전 회차 상한을 남기면 3차가 `min(6, 2) = 2` 만 팔고 4주를 이번 손절에서 흘린다.
    """
    import src.api.balance as bal

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    from src.models.order import OrderResult
    import src.engine.order_engine as _oe

    async def place_order(ticker, side, quantity, price=0, **kw):
        env.calls.place.append({"quantity": quantity})
        if len(env.calls.place) < 3:
            raise _apbk0400()
        return OrderResult(order_no="SELL-3", order_time="100501", krx_org_no="00950")

    monkeypatch.setattr(_oe, "place_order", place_order)
    snaps = iter([(10, 2), (6, 6)])

    async def get_balance(*a, **k):
        held, sellable = next(snaps)
        return [SimpleNamespace(ticker=TICKER, quantity=held, sellable_quantity=sellable)], \
            SimpleNamespace(net_asset=0)

    monkeypatch.setattr(bal, "get_balance", get_balance)
    _patch_orders(monkeypatch)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert _sent(env) == [10, 2, 6], (
        f"발사 {_sent(env)} (기대 [10, 2, 6]) — 재대조 뒤에도 이전 회차 F-3 상한이 남았다"
    )
    assert _held(env, "kojiro") == 6
