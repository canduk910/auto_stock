"""cycle385 부록 R2 — 2차 검토(H1~H8)·테스트 공백(XT-*) 반영 (TQ1~TQ25).

명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md` 부록 R2 (R2-3 ~ R2-12)
사용자 전제(2026-09-26) = 「잔여보유수량에 대한 추가매도가 가능하도록 실시간잔고의
매도상황을 추적관리」 → R-INV-1 **과소 추적 금지** · R-INV-2 **운영자 몫을 팔지 않는다**.

## 부록 R2 가 바꾸는 것 (요지)

- **R-3 소유 규칙 제거** — 어느 주문의 종료든 `_selling` 을 푼다(B7 해제 의미). 판정할 값이
  없으니 await 전에 잡은 값을 읽을 수도 없다(H1·H4). LOW #3 은 알려진 한계(TQ22 xfail).
- **H3** — F-3 도 TTTC0081R 을 1건 조회하고, 아직 안 온 외부 체결 통보(`pending`)를 뺀
  `eff = 추적 − pending` 로 초과분을 잰다. 분기 술어 = `held ≥ eff`. 조회 실패 = F-3 발사 없음.
- **H2** — 종목 크레딧은 누적한다. **H5** — 원주문 취소 성공 + 재주문이 확정적으로 안
  걸렸으면(발사 전 종료·KIS 거부) 그 주문이 주인일 때 `_selling` 을 푼다.
- **H6** — 주문 조회 2초 상한(`SELL_ORDERS_QUERY_TIMEOUT`). **H7** — 쪽 크기는 환경별(실전
  100 · 모의 15). **R2-5** — 동결이 지키던 보유가 닫히면 동결을 푼다.

## 계좌 모형(`_Acct`)

보유 · 걸린 주문(잔량) · 주문별 누적 체결을 가진다. `place_order` 는 `수량 > 매도가능`
이면 APBK0400 을 던지고, `get_daily_orders` 는 누적 체결 행을 돌려준다(적대 프로브의
`Acct` 이식). 우리 주문은 `OUR-<n>`(접수 순번 — 거부는 번호를 받지 않는다).

🔴 `_make_env` 는 `kis_env="vts"` 로 고정한다 — 쪽 크기 15 가 이 파일의 전제다.
🔴 caplog 단언은 WARNING 이상 + prefix(CI 루트 로거 DEBUG — cycle252 T2). INFO 마커
`[selling_freeze_released]` 는 상태로 단언한다.
🔴 새 심볼(`SELL_ORDERS_QUERY_TIMEOUT` 등)은 함수 안에서 import 한다 — 구현 전 수집 에러로
파일 전체가 뭉개지면 어느 행위가 붉은지 가려지지 않는다.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.base import KisApiError
from src.engine.order_engine import CANCEL_AXIS_SELL
from src.engine.strategy_base import Signal
from src.models.trade import TradeStatus
from tests.unit.engine.test_cycle385_b7_partial_sell import (
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
KST = timezone(timedelta(hours=9))


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


def _row(odno: str, qty, *, pdno: str = TICKER) -> dict:
    return {"odno": odno, "pdno": pdno, "sll_buy_dvsn_cd": "01",
            "tot_ccld_qty": qty if isinstance(qty, str) else str(qty)}


class _Acct:
    """계좌 — 보유 · 걸린 주문 잔량 · 주문별 누적 체결(TTTC0081R `tot_ccld_qty`)."""

    def __init__(self, held: int) -> None:
        self.held = held
        self.rest: dict[str, int] = {}
        self.fills: dict[str, int] = {}
        self.n = 0
        self.placed: list[int] = []

    def sellable(self) -> int:
        return self.held - sum(self.rest.values())

    def rest_order(self, no: str, qty: int) -> None:
        self.rest[no] = qty
        self.fills.setdefault(no, 0)

    def fill(self, no: str, qty: int) -> None:
        self.held -= qty
        self.rest[no] -= qty
        if self.rest[no] == 0:
            self.rest.pop(no)
        self.fills[no] = self.fills.get(no, 0) + qty

    def ours_sold(self) -> int:
        return sum(q for no, q in self.fills.items() if no.startswith("OUR-"))


def _install_acct(monkeypatch, acct: _Acct, *, orders="ok", rows_extra=(), before_place=None):
    """`place_order`·`get_balance`·`get_daily_orders` 를 계좌 모형에 묶는다.

    `orders` = "ok" | "fail"(RuntimeError) | "slow"(0.5초 뒤 행) | 콜러블(호출 순번 → 행 또는 예외).
    `before_place(n)` = n 번째 발사 직전에 계좌를 움직인다(발사 창 밖, 거래소 쪽 사건).
    반환 = 주문 조회 호출 기록 `[(args, kwargs), ...]`.
    """
    import src.api.balance as bal
    import src.engine.order_engine as _oe
    from src.models.order import OrderResult

    calls: list = []

    async def place_order(ticker, side, quantity, price=0, **kw):
        acct.placed.append(quantity)
        if before_place is not None:
            before_place(len(acct.placed))
        if quantity > acct.sellable():
            raise _apbk0400()
        acct.n += 1
        no = f"OUR-{acct.n}"
        acct.rest_order(no, quantity)
        return OrderResult(order_no=no, order_time="100501", krx_org_no="00950")

    async def get_balance(*a, **k):
        h = SimpleNamespace(ticker=TICKER, quantity=acct.held, sellable_quantity=acct.sellable())
        return [h], SimpleNamespace(net_asset=0)

    def _rows():
        return [_row(no, q) for no, q in acct.fills.items()] + list(rows_extra)

    async def get_daily_orders(*a, **k):
        calls.append((a, k))
        if callable(orders):
            ans = orders(len(calls))
            if isinstance(ans, Exception):
                raise ans
            return _rows() if ans is None else ans
        if orders == "fail":
            raise RuntimeError("TTTC0081R down")
        if orders == "slow":
            await asyncio.sleep(0.5)
        return _rows()

    monkeypatch.setattr(_oe, "place_order", place_order)
    monkeypatch.setattr(bal, "get_balance", get_balance)
    monkeypatch.setattr(bal, "get_daily_orders", get_daily_orders)
    return calls


async def _await_sell_timer(env) -> None:
    task = env.engine._pending_cancel_tasks.get((TICKER, CANCEL_AXIS_SELL))
    assert task is not None, "부분 체결(map) 뒤 잔여 재주문 타이머가 없다"
    try:
        await task
    except asyncio.CancelledError:
        pass


def _reorder_env(monkeypatch, drain, holdings):
    import src.engine.order_engine as _oe

    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0)
    monkeypatch.setattr(_oe, "cancel_order", AsyncMock(return_value=None))
    return _env(monkeypatch, drain, holdings)


def _reorder_place(monkeypatch, outcomes):
    """재주문 `place_order` — 호출마다 `outcomes` 를 하나씩 쓴다.

    "rejected" = KIS 거부(APBK0400) · "timeout" = 전송 뒤 응답 유실 · 그 밖의 문자열 = 그 주문번호로 접수.
    """
    import src.engine.order_engine as _oe
    from src.models.order import OrderResult

    seq = list(outcomes)
    fired: list[dict] = []

    async def place(*a, **kw):
        fired.append(kw)
        out = seq.pop(0)
        if out == "rejected":
            raise _apbk0400()
        if out == "timeout":
            raise TimeoutError("read timeout after send")
        return OrderResult(order_no=out, order_time="100501", krx_org_no="00950")

    monkeypatch.setattr(_oe, "place_order", place)
    return fired


# ════════════════════════════════════════════════════════════════════════════
# TQ1 · TQ2 — H3: F-3 는 아직 안 온 외부 체결 통보를 먼저 빼고 초과분을 잰다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tq1_f3_subtracts_unseen_external_fills_before_surplus(monkeypatch, drain):
    """🔴 TQ1 (money A1 · XT-K) — 추적 10 · 계좌 15(운영자 5) · MTS-A 3 체결(통보 대기) ·
    MTS-B 4 걸림 → held 12 · sellable 8.

    기대: 발사 `[10, 3]`(pending 3 → eff 7 → surplus 5 → fire 3) · 주문 조회 1회, 인자는 정확히
    `exchange="ALL", pdno=TICKER` · 추적 10 그대로 · `save_position` 0. 뒤이은 통보들로 닫히고
    우리 매도 합 ≤ 3(전략 몫 10 − A 3 − B 4), 운영자 5주는 계좌에 남는다.

    지금: `surplus = 12 − 10 = 2` → `fire 6` → 운영자 3주를 판다(`[10, 6]`).
    조회를 KRX 로만 하면(XT-K) NXT/SOR 체결을 놓친다 — 인자를 핀한다.
    """
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(15)
    acct.rest_order("MTS-A", 3)
    acct.fill("MTS-A", 3)
    acct.rest_order("MTS-B", 4)
    calls = _install_acct(monkeypatch, acct)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [10, 3], (
        f"발사 {acct.placed} (기대 [10, 3]) — 통보 대기 중인 외부 체결을 빼지 않고 초과분을 쟀다"
    )
    assert calls == [((), {"exchange": "ALL", "pdno": TICKER})], (
        f"주문 조회 {calls} — F-3 도 TTTC0081R 을 정확히 1회, `exchange=\"ALL\", pdno=ticker` 로 부른다"
    )
    assert _held(env, "kojiro") == 10, "F-3 는 추적 수량을 바꾸지 않는다"
    assert env.calls.save == []

    await _sell_notice(env, "MTS-A", 3, payload=3)
    assert _held(env, "kojiro") == 7
    acct.fill("OUR-1", 3)
    await _sell_notice(env, "OUR-1", 3, payload=3)
    assert _held(env, "kojiro") == 4
    acct.fill("MTS-B", 4)
    await _sell_notice(env, "MTS-B", 4, payload=4)
    assert _held(env, "kojiro") is None
    assert acct.ours_sold() <= 3, f"우리 매도 {acct.ours_sold()} > 전략 몫 3 — 운영자 몫을 팔았다"
    assert acct.held == 5, f"계좌 {acct.held} — 운영자 5주가 남아야 한다"


@pytest.mark.asyncio
async def test_tq2_branch_predicate_is_eff_not_tracked(monkeypatch, drain):
    """🔴 TQ2 — 추적 10 · 계좌 15 · A 6 체결(대기) · B 2 걸림 → held 9 < 10 · sellable 7.

    기대: 발사 `[10, 2]`(pending 6 → eff 4 → held ≥ eff → F-3, surplus 5, fire 2) ·
    `save_position` 0(초과분을 전략 보유로 받아들이지 않는다).
    `held ≥ pos` 로 가르면 재대조가 추적을 9 로 내려 운영자 5주를 받아들이고 `[10, 9, 7]` 을 낸다.
    """
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(15)
    acct.rest_order("MTS-A", 6)
    acct.fill("MTS-A", 6)
    acct.rest_order("MTS-B", 2)
    _install_acct(monkeypatch, acct)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [10, 2], f"발사 {acct.placed} (기대 [10, 2])"
    assert env.calls.save == [], "오늘 주문으로 설명되는 차이를 재대조(절대 대입)로 받아들였다"
    assert _held(env, "kojiro") == 10


# ════════════════════════════════════════════════════════════════════════════
# TQ3 · TQ3b — H3·H6·H7: 조회를 못 믿으면 F-3 는 쏘지 않는다(현행 동결)
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tq3_order_query_failure_freezes_instead_of_firing(monkeypatch, caplog, drain):
    """🔴 TQ3 — 추적 10 · 계좌 10 · B 3 걸림(sellable 7) · 조회 `RuntimeError` → 발사 `[10]` ·
    `_selling`·동결 표식 유지 · `[sell_qty_partial_locked] ... fire=0 ... orders=error`.

    조회가 안 되면 「걸린 체결 통보」 와 「운영자 초과분」 을 가를 수 없다 — 쏘면 운영자 몫일 수 있다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(10)
    acct.rest_order("MTS-B", 3)
    _install_acct(monkeypatch, acct, orders="fail")

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [10], f"발사 {acct.placed} (기대 [10] — 조회 실패면 F-3 발사 없음)"
    assert TICKER in env.engine._selling
    assert TICKER in env.engine._selling_locked_wait
    lines = _warn_lines(caplog, "[sell_qty_partial_locked]")
    assert len(lines) == 1 and "fire=0" in lines[0] and "orders=error" in lines[0], lines


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["timeout", "bad_row"])
async def test_tq3b_untrusted_order_query_freezes_with_reason(monkeypatch, caplog, drain, reason):
    """🔴 TQ3b (cycle432 — `page_full` 사례 제거, timeout·bad_row 만 남는다) — 조회
    지연(상수 0.01초 · 가짜 조회 0.5초) / 불량 행 → 발사 `[10]` · `orders=<이유>`."""
    import src.engine.order_engine as _oe

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(10)
    acct.rest_order("MTS-B", 3)
    if reason == "timeout":
        monkeypatch.setattr(_oe, "SELL_ORDERS_QUERY_TIMEOUT", 0.01, raising=False)
        _install_acct(monkeypatch, acct, orders="slow")
    else:
        _install_acct(monkeypatch, acct, rows_extra=[_row("MTS-C", "")])

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [10], f"발사 {acct.placed} (기대 [10])"
    lines = _warn_lines(caplog, "[sell_qty_partial_locked]")
    assert len(lines) == 1 and f"orders={reason}" in lines[0], lines


# ════════════════════════════════════════════════════════════════════════════
# TQ4 · TQ5 · TQ5b — pending 은 주문별 크레딧은 빼고 종목 크레딧은 빼지 않는다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tq4_reconcile_credit_is_excluded_from_pending(monkeypatch, drain):
    """🔴 TQ4 (부록 R TR2 의 재대조 판) — 추적 12(유령 2) · 계좌 10 · A 3 체결(대기) · B 2 걸림.

    기대: `[12, 7, 5]` — 1차 재대조(eff 9 > held 7)가 추적 7 · 주문별 크레딧 A 3 을 적고,
    2차는 pending 0(크레딧으로 이미 뺐다) → eff 7 → F-3 fire 5. A 통보는 흡수돼 추적 7.
    pending 에서 주문별 크레딧을 안 빼면 A 를 두 번 빼 `[12, 7, 2]`.
    """
    env = _env(monkeypatch, drain, {"kojiro": 12})
    acct = _Acct(10)
    acct.rest_order("MTS-A", 3)
    acct.fill("MTS-A", 3)
    acct.rest_order("MTS-B", 2)
    _install_acct(monkeypatch, acct)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [12, 7, 5], f"발사 {acct.placed} (기대 [12, 7, 5])"
    assert env.engine._sell_reflected_credit == {"MTS-A": 3}
    await _sell_notice(env, "MTS-A", 3, payload=3)
    assert _held(env, "kojiro") == 7


@pytest.mark.asyncio
async def test_tq5_ticker_credit_is_not_netted_from_pending(monkeypatch, drain):
    """🔴 TQ5 — 추적 10 · 계좌 10 · A 3 체결(대기). 1차 조회 실패 → 종목 크레딧 3 · 추적 7.
    2차 발사 직전 B 2 가 걸리고 2차 조회는 성공 → 발사 `[10, 7, 2]`.

    종목 크레딧에는 유실 통보가 섞일 수 있어 빼면 eff 가 커져 운영자 몫을 팔 수 있다 — 빼지
    않고 덜 쏜다(나머지는 통보가 온 뒤 다음 틱). 빼면 `[10, 7, 5]`.
    """
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(10)
    acct.rest_order("MTS-A", 3)
    acct.fill("MTS-A", 3)

    def before(n):
        if n == 2:
            acct.rest_order("MTS-B", 2)

    _install_acct(monkeypatch, acct, before_place=before,
                  orders=lambda k: RuntimeError("down") if k == 1 else None)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [10, 7, 2], f"발사 {acct.placed} (기대 [10, 7, 2])"
    assert _held(env, "kojiro") == 7


@pytest.mark.asyncio
async def test_tq5b_accurate_reconcile_still_drops_an_earlier_ticker_credit(monkeypatch, drain):
    """🔴 TQ5b (부록 R TR7b 의 원래 성질 — R2-7 「조회 성공 재대조는 종목 크레딧을 버린다」 무변경)
    — TR7b 의 기대값이 R2 에서 F-3 경로(`[10, 7, 2]`)로 바뀌어 그 성질을 더는 재지 않으므로 여기서 잰다.

    추적 10 · 계좌 10 · A 3 체결(대기). 1차 조회 실패 → 종목 크레딧 3 · 추적 7. 2차 발사 직전
    계좌가 오늘 주문 목록으로 설명되지 않게 6 더 줄어(held 1) 2차는 조회 성공 재대조(eff 4 > 1)
    → 주문별 크레딧 A 3 · 종목 크레딧 폐기 · 추적 1 → 3차 1 접수. A 통보·우리 1 체결 뒤 추적 0.
    종목 크레딧을 남기면 우리 1 체결을 흡수해 실보유 0 인데 추적 1(유령).
    """
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(10)
    acct.rest_order("MTS-A", 3)
    acct.fill("MTS-A", 3)

    def before(n):
        if n == 2:
            acct.held -= 6

    _install_acct(monkeypatch, acct, before_place=before,
                  orders=lambda k: RuntimeError("down") if k == 1 else None)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [10, 7, 1], f"발사 {acct.placed} (기대 [10, 7, 1])"
    assert TICKER not in env.engine._sell_blind_credit, (
        f"조회 성공 재대조 뒤 종목 크레딧 {env.engine._sell_blind_credit.get(TICKER)} 이 남았다"
    )
    await _sell_notice(env, "MTS-A", 3, payload=3)
    acct.fill("OUR-1", 1)
    await _sell_notice(env, "OUR-1", 1, payload=1)
    assert _held(env, "kojiro") is None, (
        f"실보유 0 인데 추적 {_held(env, 'kojiro')} — 남은 종목 크레딧이 우리 체결을 흡수했다"
    )


# ════════════════════════════════════════════════════════════════════════════
# TQ6 — H8: 재시작 모양(원장 빈)에서도 F-3 는 과하게 쏘지 않는다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("rows_time", [None, "pre"], ids=["no_time", "pre"])
@pytest.mark.parametrize("surplus", [0, 5], ids=["no_surplus", "operator_surplus_5"])
async def test_tq6_post_restart_f3_never_overfires(monkeypatch, drain, surplus, rows_time):
    """🔵 TQ6 (R2-11 · 부록 R3 K1) — 새 엔진(`_sell_notice_seen` 빔) · 추적 10 · 계좌 10+s · MTS-X 가
    재시작 **전에** 4 체결(추적에 이미 반영, 행 tot 4) · 8 걸림.

    시각이 있으면(`pre` — 원장 시작 전 접수) 재시작 전 주문은 pending 에서 빠지고 F-3 가 전략 몫 −
    걸림 = 2 를 판다(R3-1): 발사 **`[10, 2]`**(초과분 0/5 둘 다). 시각이 없으면(`no_time`) 뒤로 읽어
    보류한다 — 첫 발사 10 뒤 발사는 전부 ≤ 2(전략 10 − 걸림 8), 실측 보류(R3-1-6).
    """
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(10 + surplus)
    acct.rest_order("MTS-X", 8)
    acct.fills["MTS-X"] = 4
    if rows_time is None:
        _install_acct(monkeypatch, acct)
    else:
        from tests.unit.engine.test_cycle385r3_round3 import PRE, _install_acct_t

        _install_acct_t(monkeypatch, env, acct, {"MTS-X": PRE})

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed[0] == 10
    assert all(q <= 2 for q in acct.placed[1:]), (
        f"발사 {acct.placed} — 재시작 뒤 원장이 빈 채로 초과분을 작게 봐 과하게 쐈다"
    )
    if rows_time == "pre":
        assert acct.placed == [10, 2], (
            f"발사 {acct.placed} (기대 [10, 2]) — 원장 시작 전 체결을 pending 에 세어 얼었다(K1)"
        )


# ════════════════════════════════════════════════════════════════════════════
# TQ7 — H2 · XT-D: 종목 크레딧은 누적하고, 부분 소진이면 남긴다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tq7_ticker_credit_accumulates_and_partially_drains(monkeypatch, drain):
    """🔴 TQ7 (money A3 · p5 · XT-D) — 추적 10 · 계좌 10 · A 3 체결(대기) · B 2 걸림 · 조회 늘 실패.
    2차 발사 직전 B 2 체결(통보 대기).

    기대: 종목 크레딧 **5**(3 + 2 — 두 번째 재대조는 첫 재대조 뒤 새로 반영된 몫만 센다) ·
    추적 5 · A 통보 1(주문 3) 뒤 크레딧 **4**(통째 삭제 아님) · A 2·B 2 통보 뒤 추적 == 계좌 == 5.
    덮어쓰면(크레딧 2) A 의 뒤 통보가 보유를 다시 빼 추적 2 < 계좌 5(과소 추적).
    """
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(10)
    acct.rest_order("MTS-A", 3)
    acct.fill("MTS-A", 3)
    acct.rest_order("MTS-B", 2)

    def before(n):
        if n == 2:
            acct.fill("MTS-B", 2)

    _install_acct(monkeypatch, acct, orders="fail", before_place=before)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [10, 7, 5], f"발사 {acct.placed} (기대 [10, 7, 5])"
    assert env.engine._sell_blind_credit.get(TICKER) == 5, (
        f"종목 크레딧 {env.engine._sell_blind_credit.get(TICKER)} (기대 5 = 3 + 2 누적)"
    )
    assert _held(env, "kojiro") == 5

    await _sell_notice(env, "MTS-A", 1, payload=3)
    assert env.engine._sell_blind_credit.get(TICKER) == 4, (
        f"부분 소진 뒤 종목 크레딧 {env.engine._sell_blind_credit.get(TICKER)} (기대 4)"
    )
    assert _held(env, "kojiro") == 5
    await _sell_notice(env, "MTS-A", 2, payload=3)
    await _sell_notice(env, "MTS-B", 2, payload=2)
    assert _held(env, "kojiro") == acct.held == 5, (
        f"추적 {_held(env, 'kojiro')} · 계좌 {acct.held} — 둘이 같아야 한다(R-INV-1)"
    )


# ════════════════════════════════════════════════════════════════════════════
# TQ8 — H6: 주문 조회 2초 상한
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tq8_order_query_timeout_falls_back_to_ticker_credit(monkeypatch, caplog, drain):
    """🔴 TQ8 — 조회가 0.5초 잔다 · `SELL_ORDERS_QUERY_TIMEOUT` 0.01 · 추적 10 · 계좌 7 →
    발사 `[10, 7]` · 종목 크레딧 3 · `[sell_qty_reconcile_orders_unavailable] reason=timeout`.

    상한이 없으면 손절 경로가 조회를 끝까지 기다린다(0.5초 뒤 `reason=ok` 로 간다).
    """
    import src.engine.order_engine as _oe

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    monkeypatch.setattr(_oe, "SELL_ORDERS_QUERY_TIMEOUT", 0.01, raising=False)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(7)
    _install_acct(monkeypatch, acct, orders="slow")

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert acct.placed == [10, 7], f"발사 {acct.placed} (기대 [10, 7])"
    assert env.engine._sell_blind_credit.get(TICKER) == 3
    lines = _warn_lines(caplog, "[sell_qty_reconcile_orders_unavailable]")
    assert len(lines) == 1 and "reason=timeout" in lines[0], lines


def test_tq8b_query_timeout_constant_is_two_seconds():
    """🔴 TQ8b (R2-9) — 상한은 2.0초 모듈 상수(런타임 다이얼 아님)."""
    import src.engine.order_engine as _oe

    assert getattr(_oe, "SELL_ORDERS_QUERY_TIMEOUT", None) == 2.0


# ════════════════════════════════════════════════════════════════════════════
# TQ9 · TQ10 — cycle432 가 H7(쪽 크기 환경 분기 · `page_full`) 을 제거했다.
# 과거 기대(`page_full`)는 지금 거짓 양성이므로 새 기대로 뒤집는다(사용자 승인
# 2026-10-10 「100건 꽉 참 판정은 연속처리 넣었으니 제거하자」).
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("n", [14, 15, 16, 100, 150])
def test_tq9_parser_no_longer_rejects_by_row_count(n):
    """🔴 TQ9(뒤집음) — `_sell_fills_by_order(rows, ticker)` 는 행 수와 무관하게(모양이
    전부 정상이면) `None` 을 돌려주지 않는다 — 쪽 크기 상수·판정이 사라졌다."""
    from src.engine.order_engine import _sell_fills_by_order

    rows = [_row(f"X{i}", 0) for i in range(n)]
    got = _sell_fills_by_order(rows, TICKER)
    assert got is not None and len(got) == n, f"{n}행 → {got!r}"


def test_tq9b_parser_has_two_params_no_default():
    """🔴 TQ9b(뒤집음) — `page_size` 세 번째 인자가 없다. `(rows, ticker)` 둘 다 기본값 없음."""
    from src.engine.order_engine import _sell_fills_by_order

    params = list(inspect.signature(_sell_fills_by_order).parameters.values())
    assert [p.name for p in params] == ["rows", "ticker"], params
    assert all(p.default is inspect.Parameter.empty for p in params), params


def test_page_size_constants_are_gone():
    """🔴 cycle432 — `_DAILY_ORDERS_PAGE_REAL`/`_DAILY_ORDERS_PAGE_VTS` 상수가 없다."""
    import src.engine.order_engine as _oe

    assert not hasattr(_oe, "_DAILY_ORDERS_PAGE_REAL")
    assert not hasattr(_oe, "_DAILY_ORDERS_PAGE_VTS")


@pytest.mark.asyncio
async def test_tq10_vts_full_page_no_longer_distrusted(monkeypatch, caplog, drain):
    """🔴 TQ10(뒤집음) — 모의 환경에서 15행(옛 쪽 크기와 같은 건수)이 와도 더는
    `page_full` 로 불신하지 않는다 — `_sell_orders_snapshot` 이 `ok` 를 돌려줘
    정상 재대조(「orders」 경로)로 간다. 추적 10 · 계좌 7 → 7 로 보정."""
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(7)
    _install_acct(monkeypatch, acct, rows_extra=[_row(f"Z{i}", 0) for i in range(15)])

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert not _warn_lines(caplog, "[sell_qty_reconcile_orders_unavailable]"), (
        "cycle432 뒤에는 15행도 `ok` 라 이 마커가 나오면 안 된다"
    )
    reconciled = _warn_lines(caplog, "[sell_qty_reconciled]")
    assert len(reconciled) == 1 and "credit_src=orders" in reconciled[0], reconciled
    assert "page_full" not in "".join(r.getMessage() for r in caplog.records)
    assert env.engine._sell_blind_credit.get(TICKER) is None, (
        "ok 경로는 종목 크레딧(_sell_blind_credit) 을 쓰지 않는다"
    )


# ════════════════════════════════════════════════════════════════════════════
# TQ11 — XT-E: 원장은 추적 보유가 없어도 센다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tq11_notice_ledger_counts_without_a_tracked_holder(monkeypatch, drain):
    """🔵 TQ11 (XT-E) — 보유 전략 0 · 통보 `0000077` 4주(주문 9) → `_sell_notice_seen == {"77": 4}`.
    원장을 보유가 있을 때만 적으면 뒤 재대조가 그 체결을 「미확인」 으로 세어 크레딧·pending 이 틀린다."""
    env = _env(monkeypatch, drain, {})
    await _sell_notice(env, "0000077", 4, payload=9)
    assert env.engine._sell_notice_seen == {"77": 4}


# ════════════════════════════════════════════════════════════════════════════
# TQ12 ~ TQ14 — H5: 원주문 취소 뒤 우리 것이 하나도 안 걸렸으면 `_selling` 을 푼다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["auto", "own_manual"])
async def test_tq12_reorder_rejected_after_cancel_releases_selling(monkeypatch, caplog, drain, owner):
    """🔴 TQ12 (seed 1068) — S1 10(매핑, `_selling` 주인) · 통보 4 → 타이머 → 취소 성공 →
    재주문 APBK0400 → `_selling`·`_selling_since` 비움 · `[reorder_selling_released] ...
    place=rejected` · 이어서 손절이 잔여 6 을 낸다(막히지 않는다).

    지금: 바깥 `except` 가 로그만 남기고 끝나 우리 것이 하나도 안 걸렸는데 `_selling` 이 남는다
    → `selling_reconcile`(180초 + 15분 주기)까지 잔여 6주 손절 정지.
    `own_manual` = 라우트가 세운 manual(`_added` 참) 주문도 주인이다(`_manual_sell_orders` True).
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _reorder_env(monkeypatch, drain, {"kojiro": 10})
    fired = _reorder_place(monkeypatch, ["rejected"])
    _map_order(env, "S1", 10, "kojiro")
    if owner == "own_manual":
        env.engine._manual_sell_orders["S1"] = True
    env.engine._selling.add(TICKER)
    env.engine._selling_since[TICKER] = datetime(2026, 9, 28, 10, 0, tzinfo=KST)

    await _sell_notice(env, "S1", 4, payload=10)
    await _await_sell_timer(env)

    assert [k["quantity"] for k in fired] == [6]
    assert TICKER not in env.engine._selling, (
        "원주문을 취소했고 재주문은 거부됐다 — 우리 주문이 하나도 없는데 `_selling` 이 남았다"
    )
    assert TICKER not in env.engine._selling_since
    lines = _warn_lines(caplog, "[reorder_selling_released]")
    assert len(lines) == 1 and "order_no=S1" in lines[0] and "place=rejected" in lines[0], lines

    _install_place_order(monkeypatch, env)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert [c["quantity"] for c in env.calls.place] == [6], (
        f"잔여 6주 손절 발사 {[c['quantity'] for c in env.calls.place]} (기대 [6])"
    )


@pytest.mark.asyncio
async def test_tq13_reorder_outcome_unknown_keeps_selling(monkeypatch, caplog, drain):
    """🔴 TQ13 — 같은 입력, 재주문이 `TimeoutError`(전송 뒤 응답 유실) → `_selling` **유지**.
    거래소에 나갔을 수 있다 — 풀면 다음 틱이 한 번 더 낸다(「주문이 나간 뒤의 실패」 원리)."""
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _reorder_env(monkeypatch, drain, {"kojiro": 10})
    _reorder_place(monkeypatch, ["timeout"])
    _map_order(env, "S1", 10, "kojiro")
    env.engine._selling.add(TICKER)

    await _sell_notice(env, "S1", 4, payload=10)
    await _await_sell_timer(env)

    assert TICKER in env.engine._selling, "재주문 결과를 모르는데 `_selling` 을 풀었다"
    assert not _warn_lines(caplog, "[reorder_selling_released]")


@pytest.mark.asyncio
@pytest.mark.parametrize("where", ["before_place", "during_place"])
async def test_tq14_replaced_task_after_cancel(monkeypatch, caplog, drain, where):
    """🔴 TQ14 — 취소 성공 뒤 태스크가 `cancel()` 로 교체된다.

    (a) `before_place` — CANCELLED 장부 await 에서 멈춘 채 취소 → 우리 것이 안 걸렸다 → 해제
        · `place=none`.
    (b) `during_place` — `place_order` await 에서 취소 → 나갔는지 모른다 → **유지**.
    """
    import src.engine.order_engine as _oe

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _reorder_env(monkeypatch, drain, {"kojiro": 10})
    reached = asyncio.Event()
    gate = asyncio.Event()
    if where == "before_place":
        async def gated_update(*a, **k):
            if len(a) >= 3 and a[2] == TradeStatus.CANCELLED:
                reached.set()
                await gate.wait()
            return 1

        monkeypatch.setattr(_oe, "update_trade_status", gated_update)
        _reorder_place(monkeypatch, ["REORDER-1"])
    else:
        async def gated_place(*a, **k):
            reached.set()
            await gate.wait()

        monkeypatch.setattr(_oe, "place_order", gated_place)
    _map_order(env, "S1", 10, "kojiro")
    env.engine._selling.add(TICKER)

    await _sell_notice(env, "S1", 4, payload=10)
    task = env.engine._pending_cancel_tasks.get((TICKER, CANCEL_AXIS_SELL))
    assert task is not None
    await asyncio.wait_for(reached.wait(), 2.0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    released = _warn_lines(caplog, "[reorder_selling_released]")
    if where == "before_place":
        assert TICKER not in env.engine._selling, "원주문 취소 뒤 재주문을 못 냈는데 `_selling` 이 남았다"
        assert len(released) == 1 and "place=none" in released[0], released
    else:
        assert TICKER in env.engine._selling, "재주문 전송 중 교체 — 나갔을 수 있는데 `_selling` 을 풀었다"
        assert not released


# ════════════════════════════════════════════════════════════════════════════
# TQ15 · TQ16 — XT-A · XT-I · XT-J: 손님 manual 의 재주문
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("gen", [1, 2], ids=["guest_gen1", "guest_gen2_inherited"])
async def test_tq15_guest_manual_rejected_reorder_keeps_owner_selling(monkeypatch, caplog, drain, gen):
    """🔴 TQ15 (XT-A · XT-I) — 자동 매도 S1(10)이 `_selling` 주인. 손님 manual `MAN-1`(표식 False,
    3주) 1주 부분 → 재주문 거부 → S1 이 아직 걸려 있으므로 `_selling` **유지**.
    `gen2` = 첫 재주문 `MAN-2` 접수(표식 False 상속) → MAN-2 1주 부분 → 재주문 거부 → 유지.

    주인 판정을 빼면(XT-A) 손님의 거부가 S1 의 표식을 풀고, 상속을 `True` 로 하면(XT-I) 2세대가 푼다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _reorder_env(monkeypatch, drain, {"kojiro": 10})
    _map_order(env, "S1", 10, "kojiro")
    env.engine._selling.add(TICKER)
    _map_order(env, "MAN-1", 3, "kojiro")
    env.engine._manual_sell_orders["MAN-1"] = False
    fired = _reorder_place(monkeypatch, ["rejected"] if gen == 1 else ["MAN-2", "rejected"])

    await _sell_notice(env, "MAN-1", 1, payload=3)
    await _await_sell_timer(env)
    if gen == 2:
        assert env.engine._manual_sell_orders.get("MAN-2") is False, (
            "재주문 번호가 손님 manual 표식(False)을 물려받지 않았다"
        )
        await _sell_notice(env, "MAN-2", 1, payload=2)
        await _await_sell_timer(env)

    assert [k["quantity"] for k in fired] == ([2] if gen == 1 else [2, 1])
    assert TICKER in env.engine._selling, (
        "손님 manual 의 재주문 거부가 자동 손절(S1)의 `_selling` 을 풀었다 — S1 이 걸린 채 손절이 또 나간다"
    )
    assert not _warn_lines(caplog, "[reorder_selling_released]")


@pytest.mark.asyncio
async def test_tq16_guest_manual_remainder_is_replaced_without_holder(monkeypatch, drain):
    """🔵 TQ16 (XT-J) — 보유 전략 0 · 손님 manual `MAN-1` 5주(표식 False) 2주 부분 → 타이머 →
    재주문 3(`verdict=manual`). manual 분기를 `.get(order_no)`(값) 으로 가르면 False 표식이
    manual 이 아닌 것으로 읽혀 `gone` → 운영자 잔여 3주가 취소된 채 끝난다."""
    env = _reorder_env(monkeypatch, drain, {})
    _install_place_order(monkeypatch, env)
    _map_order(env, "MAN-1", 5, "momentum")
    env.engine._manual_sell_orders["MAN-1"] = False

    await _sell_notice(env, "MAN-1", 2, payload=5)
    await _await_sell_timer(env)

    assert [c["quantity"] for c in env.calls.place] == [3]


# ════════════════════════════════════════════════════════════════════════════
# TQ17 · TQ18 — R2-5 · H4: 동결은 지키던 보유가 닫히거나 어느 주문이 끝나면 풀린다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tq17_freeze_released_when_guarded_holding_closes(monkeypatch, drain):
    """🔴 TQ17 (R2-5) — 추적 3 · 계좌 3 · MTS-9 3 걸림(sellable 0) → `[sell_qty_locked]` 동결.
    그 뒤 MTS-9(주문 9주)의 3주 **부분** 통보가 추적을 0 으로 만든다 → 닫힘 · `_selling`·
    `_selling_since`·동결 표식 비움.

    주문 종료가 끝내 안 오면(운영자가 나머지를 취소) `_selling` 이 보유 0 으로 하루 끝까지
    남는다 — `selling_reconcile` 은 `held_zero` 를 건드리지 않는다.
    """
    env = _env(monkeypatch, drain, {"kojiro": 3})
    acct = _Acct(3)
    acct.rest_order("MTS-9", 3)
    _install_acct(monkeypatch, acct)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert acct.placed == [3]
    assert TICKER in env.engine._selling and TICKER in env.engine._selling_locked_wait

    acct.fill("MTS-9", 3)
    await _sell_notice(env, "MTS-9", 3, payload=9)

    assert _held(env, "kojiro") is None
    assert TICKER not in env.engine._selling, "동결이 지키던 보유가 닫혔는데 `_selling` 이 남았다"
    assert TICKER not in env.engine._selling_since
    assert TICKER not in env.engine._selling_locked_wait


@pytest.mark.asyncio
async def test_tq18_mapped_guest_manual_end_releases_a_freeze(monkeypatch, drain):
    """🔴 TQ18 (H4) — 추적 10 · 계좌 10 · MTS-9 10 걸림 → 동결. 운영자가 MTS-9 를 앱에서 취소(통보
    없음)하고 라우트로 3주를 낸다(`_selling` 이 서 있어 손님 manual, 표식 False). 그 주문이 map
    으로 전량 체결 → `_selling`·동결 표식 비움 → 다음 손절이 잔여 7 을 낸다.

    지금: 손님 manual 종료는 `_selling` 을 안 풀어(부록 R-3) 동결이 잔여 7 의 손절을 막는다.
    """
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(10)
    acct.rest_order("MTS-9", 10)
    _install_acct(monkeypatch, acct)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert TICKER in env.engine._selling_locked_wait

    acct.rest.pop("MTS-9")
    acct.rest_order("MAN-1", 3)
    _map_order(env, "MAN-1", 3, "kojiro")
    env.engine._manual_sell_orders["MAN-1"] = False
    acct.fill("MAN-1", 3)
    await _sell_notice(env, "MAN-1", 3, payload=3)

    assert _held(env, "kojiro") == 7
    assert TICKER not in env.engine._selling, "manual 주문이 끝났는데 동결 `_selling` 이 남았다"
    assert TICKER not in env.engine._selling_locked_wait
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert acct.placed[-1] == 7, f"발사 {acct.placed} — 잔여 7 손절이 나가지 않았다"


# ════════════════════════════════════════════════════════════════════════════
# TQ19 — H1: 발사 창에서 시작해 DB await 에서 멈춘 통보가 REST 응답 뒤 재개돼도 종료는 푼다
# ════════════════════════════════════════════════════════════════════════════
def _gate_lookup(monkeypatch) -> asyncio.Event:
    """`_lookup_strategy_from_trade_history`(매핑 miss 시 첫 DB await)를 게이트로 멈춘다."""
    import src.engine.order_engine as _oe

    gate = asyncio.Event()

    async def slow_lookup(*a, **k):
        await gate.wait()
        return None

    monkeypatch.setattr(_oe, "_lookup_strategy_from_trade_history", slow_lookup)
    return gate


@pytest.mark.asyncio
async def test_tq19a_own_full_fill_notice_suspended_across_rest_response(monkeypatch, drain):
    """🔴 TQ19 p4a — 우리 손절 10 의 전량 통보가 REST 응답 **전**에 시작(매핑 부재 → payload)해
    장부 조회 await 에서 멈추고, REST 응답·매핑 등록 뒤 재개 → 닫힘 · `_selling` 비움.

    지금: 통보 **시작** 시점 출처(`payload`)로 주인 판정 → 「무관한 종료」 → `[selling_kept]` → 좀비.
    """
    env = _env(monkeypatch, drain, {"kojiro": 10})
    gate = _gate_lookup(monkeypatch)
    tasks: list = []

    async def inject(order_no):
        tasks.append(asyncio.create_task(_sell_notice(env, order_no, 10, payload=10)))
        for _ in range(5):
            await asyncio.sleep(0)

    _install_place_order(monkeypatch, env, inject=inject)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    gate.set()
    await asyncio.gather(*tasks)

    assert _held(env, "kojiro") is None
    assert TICKER not in env.engine._selling, "열린 주문이 없는데 `_selling` 이 남았다(좀비)"


@pytest.mark.asyncio
async def test_tq19b_f3_partial_fire_notice_suspended_then_remainder_fires(monkeypatch, drain):
    """🔴 TQ19 p4b — 추적 10 = 계좌 10 · 운영자 MTS-3 3 걸림(sellable 7). F-3 가 7 을 낸다. 그 7 의
    통보가 발사 창에서 시작해 멈췄다가 REST 뒤 재개 → 추적 3 · `_selling` 비움. 운영자가 MTS-3 을
    앱에서 취소(통보 없음) → 다음 손절이 3 을 낸다."""
    env = _env(monkeypatch, drain, {"kojiro": 10})
    gate = _gate_lookup(monkeypatch)
    import src.api.balance as bal
    import src.engine.order_engine as _oe
    from src.models.order import OrderResult

    acct = _Acct(10)
    acct.rest_order("MTS-3", 3)
    tasks: list = []

    async def place_order(ticker, side, quantity, price=0, **kw):
        acct.placed.append(quantity)
        if quantity > acct.sellable():
            raise _apbk0400()
        acct.n += 1
        no = f"OUR-{acct.n}"
        if acct.n == 1:  # 시장가 즉시 체결 — 통보가 REST 응답과 경합
            acct.held -= quantity
            tasks.append(asyncio.create_task(_sell_notice(env, no, quantity, payload=quantity)))
            for _ in range(5):
                await asyncio.sleep(0)
        else:
            acct.rest_order(no, quantity)
        return OrderResult(order_no=no, order_time="100501", krx_org_no="00950")

    async def get_balance(*a, **k):
        return [SimpleNamespace(ticker=TICKER, quantity=acct.held,
                                sellable_quantity=acct.sellable())], None

    monkeypatch.setattr(_oe, "place_order", place_order)
    monkeypatch.setattr(bal, "get_balance", get_balance)
    monkeypatch.setattr(bal, "get_daily_orders", AsyncMock(return_value=[]))

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    gate.set()
    await asyncio.gather(*tasks)
    assert _held(env, "kojiro") == 3
    assert TICKER not in env.engine._selling

    acct.rest.pop("MTS-3")
    n = len(acct.placed)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert acct.placed[n:] == [3], f"잔여 3 손절 발사 {acct.placed[n:]} (기대 [3])"


@pytest.mark.asyncio
@pytest.mark.parametrize("yields", [5, 3], ids=["p4c", "money_A2"])
async def test_tq19c_manual_partial_notice_suspended_then_remainder_fires(monkeypatch, drain, yields):
    """🔴 TQ19 p4c · money A2 (사용자 전제 그대로) — kojiro 10, 운영자가 라우트로 4주 매도. 체결
    통보가 REST 응답 전에 시작해 장부 await 에서 멈추고, 라우트가 매핑·manual 표식을 적은 뒤 재개 →
    추적 6 · `_selling` 비움 → 손절이 `[6]` 을 낸다."""
    env = _env(monkeypatch, drain, {"kojiro": 10})
    gate = _gate_lookup(monkeypatch)
    import src.api.order as _api_order
    import src.db.trade_history as _th
    import src.routes.trading as _tr
    from src.models.order import OrderResult

    monkeypatch.setattr(_tr, "trading_scheduler",
                        SimpleNamespace(registry=env.registry, order_engine=env.engine))
    monkeypatch.setattr(_th, "insert_trade", AsyncMock(return_value=None))
    tasks: list = []

    async def route_place(ticker, side, quantity, price=0, **kw):
        tasks.append(asyncio.create_task(_sell_notice(env, "MAN-1", quantity, payload=quantity)))
        for _ in range(yields):
            await asyncio.sleep(0)
        return OrderResult(order_no="MAN-1", order_time="100000", krx_org_no="00950")

    monkeypatch.setattr(_api_order, "place_order", route_place)
    from src.routes.trading import ManualSellRequest, manual_sell

    resp = await manual_sell(ManualSellRequest(ticker=TICKER, quantity=4))
    assert resp.success, resp.message
    gate.set()
    await asyncio.gather(*tasks)
    assert _held(env, "kojiro") == 6
    assert TICKER not in env.engine._selling, "manual 주문이 끝났는데 `_selling` 이 남았다"

    _install_place_order(monkeypatch, env)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert [c["quantity"] for c in env.calls.place] == [6]


# ════════════════════════════════════════════════════════════════════════════
# TQ20 · TQ21 — 적대 프로브 p1 · rp 를 R2 규칙에 맞춘 판
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["ok", "fail", "unpatched"])
async def test_tq20_recount_or_f3_then_late_external_notice(monkeypatch, drain, mode):
    """🔴 TQ20 (p1) — 추적 10 · 1차 APBK0400 · 계좌 7/7 · 행 MTS-1 tot 3 · MTS-1 통보는 `execute_sell`
    **반환 뒤**. 셋 다 발사 `[10, 7]`.

    - `ok`: 오늘 주문으로 설명되는 차이 → F-3(pending 3 → eff 7) · 추적 10 그대로 · 저장 0 →
      MTS-1 통보 → 7.
    - `fail`·`unpatched`(`src.api.base._request` 차단): 재대조(종목 크레딧 3) → 추적 7 →
      MTS-1 통보 흡수 → 7.
    이어서 우리 7 체결 → 닫힘 · `_selling` 비움.
    """
    import src.api.balance as bal

    env = _env(monkeypatch, drain, {"kojiro": 10})
    _install_place_order(monkeypatch, env, first_error=_apbk0400())
    h = SimpleNamespace(ticker=TICKER, quantity=7, sellable_quantity=7)
    monkeypatch.setattr(bal, "get_balance", AsyncMock(return_value=([h], None)))
    rows = [_row("MTS-1", 3)]
    if mode == "ok":
        monkeypatch.setattr(bal, "get_daily_orders", AsyncMock(return_value=rows))
    elif mode == "fail":
        monkeypatch.setattr(bal, "get_daily_orders", AsyncMock(side_effect=RuntimeError("down")))
    else:
        async def _net(*a, **k):
            raise RuntimeError("probe: network blocked")

        monkeypatch.setattr("src.api.base._request", _net, raising=False)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert [c["quantity"] for c in env.calls.place] == [10, 7]
    if mode == "ok":
        assert _held(env, "kojiro") == 10, "오늘 주문으로 설명되는 차이는 재대조가 아니라 F-3 로 간다"
        assert env.calls.save == []
    else:
        assert _held(env, "kojiro") == 7
    await _sell_notice(env, "MTS-1", 3, payload=3)
    assert _held(env, "kojiro") == 7
    await _sell_notice(env, "SELL-000002", 7, payload=7)
    assert _held(env, "kojiro") is None
    assert TICKER not in env.engine._selling


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["ok", "fail"])
async def test_tq21_inflight_notice_never_under_tracks(monkeypatch, drain, mode):
    """🔴 TQ21 (rp) — 추적 10 · 계좌 7(A 3 체결, 통보 대기) · B 2 걸림(sellable 5).

    - `ok`: 발사 `[10, 5]`(재대조 없이 F-3). 매 단계 추적 ≥ 계좌 · 끝에 둘 다 0.
    - `fail`: 발사 `[10, 7]`(1차 종목 크레딧 재대조 → 2차는 조회 실패라 동결) · 매 단계 추적 ≥
      계좌 · B 종료 통보 뒤 `_selling` 비움 · 다음 손절이 5 를 내고 끝에 둘 다 0.
    """
    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(10)
    acct.rest_order("MTS-A", 3)
    acct.fill("MTS-A", 3)
    acct.rest_order("MTS-B", 2)
    _install_acct(monkeypatch, acct, orders="ok" if mode == "ok" else "fail")
    trail: list = []

    def snap(tag):
        trail.append((tag, _held(env, "kojiro") or 0, acct.held))

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    sent = list(acct.placed)
    snap("after_exec")
    await _sell_notice(env, "MTS-A", 3, payload=3)
    snap("after_A")
    for no, q in [(k, v) for k, v in acct.rest.items() if k.startswith("OUR-")]:
        acct.fill(no, q)
        await _sell_notice(env, no, q, payload=q)
        snap(f"after_{no}")
    acct.fill("MTS-B", 2)
    await _sell_notice(env, "MTS-B", 2, payload=2)
    snap("after_B")
    if mode == "fail":
        assert TICKER not in env.engine._selling, "B 종료 뒤에도 동결 `_selling` 이 남았다"
        await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
        for no, q in [(k, v) for k, v in acct.rest.items() if k.startswith("OUR-")]:
            acct.fill(no, q)
            await _sell_notice(env, no, q, payload=q)
            snap(f"after_{no}")

    assert sent == ([10, 5] if mode == "ok" else [10, 7]), f"발사 {sent}"
    for tag, tracked, held in trail:
        assert tracked >= held, f"과소 추적 {tag}: 추적 {tracked} < 계좌 {held} — {trail}"
    assert _held(env, "kojiro") is None and acct.held == 0, trail
    assert TICKER not in env.engine._selling


# ════════════════════════════════════════════════════════════════════════════
# TQ22 — LOW #3 알려진 한계 (p3 · p3b) — R-3 소유 규칙 제거의 대가
# ════════════════════════════════════════════════════════════════════════════
_LOW3 = pytest.mark.xfail(
    strict=True,
    reason="LOW #3 알려진 한계 — 부록 R2-1, F-385-5(걸린 우리 매도 등록부)가 생기면 뒤집힌다",
)


@_LOW3
@pytest.mark.asyncio
async def test_tq22_p3_unrelated_end_during_our_send_keeps_selling(monkeypatch, drain):
    """🟡 TQ22 p3 — 우리 손절 발사 창에서 무관한 MTS-9 3 이 끝나면 `_selling` 이 풀리고 다음 손절이
    우리 걸린 10 위에 또 나간다. B7 과 같은 성질(부록 R2-1)이라 strict xfail 로 둔다."""
    env = _env(monkeypatch, drain, {"kojiro": 10})

    async def inject(order_no):
        await _sell_notice(env, "MTS-9", 3, payload=3)

    _install_place_order(monkeypatch, env, inject=inject)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert TICKER in env.engine._selling
    n = len(env.calls.place)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert len(env.calls.place) == n, "우리 주문이 걸린 채로 두 번째 손절이 나갔다"


@_LOW3
@pytest.mark.asyncio
@pytest.mark.parametrize("mts_notice_when", ["in_send_window", "after_rest"])
async def test_tq22_p3b_operator_surplus_not_sold(monkeypatch, drain, mts_notice_when):
    """🟡 TQ22 p3b (부록 R-3-2) — 추적 10 · 운영자 초과 10 · 계좌 20. 우리 손절이 걸린 동안 운영자
    MTS 3 이 끝난다 → 다음 틱들이 우리 걸린 10 위에 주문을 더 얹어 운영자 몫을 판다."""
    import src.api.balance as bal
    import src.engine.order_engine as _oe
    from src.models.order import OrderResult

    env = _env(monkeypatch, drain, {"kojiro": 10})
    acct = _Acct(20)
    acct.rest_order("MTS-3", 3)

    async def place_order(ticker, side, quantity, price=0, **kw):
        acct.placed.append(quantity)
        if quantity > acct.sellable():
            raise _apbk0400()
        acct.n += 1
        no = f"OUR-{acct.n}"
        if mts_notice_when == "in_send_window" and acct.n == 1:
            acct.fill("MTS-3", 3)
            await _sell_notice(env, "MTS-3", 3, payload=3)
        acct.rest_order(no, quantity)
        return OrderResult(order_no=no, order_time="100000", krx_org_no="00950")

    async def get_balance(*a, **k):
        return [SimpleNamespace(ticker=TICKER, quantity=acct.held,
                                sellable_quantity=acct.sellable())], None

    monkeypatch.setattr(_oe, "place_order", place_order)
    monkeypatch.setattr(bal, "get_balance", get_balance)
    monkeypatch.setattr(bal, "get_daily_orders", AsyncMock(return_value=[]))

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    if mts_notice_when == "after_rest":
        acct.fill("MTS-3", 3)
        await _sell_notice(env, "MTS-3", 3, payload=3)
    for _ in range(3):
        await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    for no, q in list(acct.rest.items()):
        acct.fill(no, q)
        await _sell_notice(env, no, q, payload=q)
    ours = acct.ours_sold()
    assert ours <= 10, f"우리 매도 {ours} > 추적 10 — 운영자 몫을 팔았다"
    assert acct.held == 7


# ════════════════════════════════════════════════════════════════════════════
# TQ25 — 진입이 낡은 동결 표식을 지운다(닫힘 해제가 새 주인을 풀지 않는다)
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_tq25_entry_clears_stale_freeze_mark_so_close_release_keeps_new_owner(monkeypatch, drain):
    """🔴 TQ25 (R2-5 안전) — 동결 표식만 남은 상태(`_selling` 은 이미 풀렸다)에서 `execute_sell` 이
    접수돼 우리 10 이 걸렸다. 외부 주문(20주)의 10주 **부분** 체결이 추적을 0 으로 만든다 →
    `_selling` **유지**(우리 주문이 걸려 있다).

    진입이 표식을 지우지 않으면 닫힘 해제가 「동결이 지키던 보유가 닫혔다」 로 오판해 우리 걸린
    주문의 `_selling` 을 푼다.
    """
    env = _env(monkeypatch, drain, {"kojiro": 10})
    env.engine._selling_locked_wait.add(TICKER)
    _install_place_order(monkeypatch, env)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")
    assert TICKER in env.engine._selling
    assert TICKER not in env.engine._selling_locked_wait, "진입이 낡은 동결 표식을 지우지 않았다"

    await _sell_notice(env, "0000065001", 10, payload=20)

    assert _held(env, "kojiro") is None
    assert TICKER in env.engine._selling, (
        "우리 손절 주문이 걸려 있는데 보유 닫힘이 `_selling` 을 풀었다"
    )
