"""cycle385 §g-3 — manual-sell 의 `_selling` 은 **발사 앞**에서 선다 (T27~T29).

명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md` §g-3 (필수 동반 ②)

## 결함 (HEAD — B7 이 실효로 만든다)

`routes/trading.py::manual_sell` 은 `await place_order` **뒤**에 `_selling.add` 를 한다.
시장가가 REST 응답보다 먼저 체결되면 순서가 뒤집힌다 —

```
await place_order ◀ 체결통보(3주) → 주문 종료 → _selling.discard(없음) · 보유 10→7
route             _selling.add(ticker)      ← 열린 주문도 없는데 표식이 선다
                  → 잔여 7주 손절 평가 정지(risk.on_tick 은 `ticker in _selling` 이면 건너뛴다)
```

B7 이전엔 그 체결이 포지션을 통째로 지워 무해했던 순서다. B7 뒤로는 잔여 보유가
남으므로 이 좀비가 그대로 손절 마비가 된다.

## 규칙

- 발사 **앞**에서 `_selling.add` + `_selling_since` (이미 있던 종목이면 건드리지 않는다)
- 발사 **전** 실패만 되돌린다 — 발사 **뒤** 실패는 주문이 이미 거래소에 있다(그 통보가 해제)
- 부록 R3 K2 — 발사 전 실패 중에서도 **발사 안 됨이 확정된** 것(APBK0400)만 되돌린다. 그 밖의
  예외는 `_request` 재시도의 앞 시도가 접수됐을 수 있어 표식을 둔다(`[manual_sell_selling_kept]`,
  TK11a·TK11b — T28 교체)
- 부록 R4 D2 — 「확정」 판정은 `order_engine._sell_not_placed_reason` 하나다: APBK0400 · 시장가 불가
  (APBK1943·APBK3013 계열) · 장운영시간 외(APBK0918 + 장운영시간 문구). 첫 시도도 똑같이 거부됐을
  주문 자체의 결정적 거부라 아무것도 안 걸렸다. EGW00201·전송 예외·모르는 코드·보유 부족 문구는 유지.
  분류는 실패 줄 `수동 매도 실패: … selling_released=<이유|->` 에 남는다(TR4-R1 · TR4-R2 · TK11a/b)
- 부록 R4 D5 — 손님 manual(`_added` 거짓)의 어떤 실패도 주인의 `_selling` 을 풀지 않는다(TR4-R2 — MX7)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
TICKER = "005930"
NEW_NO = "MAN-0000385"


class _Strat(StrategyBase):
    def __init__(self, sid: str) -> None:
        super().__init__(
            StrategyConfig(strategy_id=sid, name=f"{sid}-dummy", enabled=True,
                           weight=0.5, params={"exchange": "KRX"})
        )
        self.state.total_investment = 10_000_000

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 0


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch):
    import src.api.order as _api_order
    import src.db.positions as _positions
    import src.db.trade_history as _th
    import src.engine.order_engine as _oe
    import src.engine.scanner as _scanner
    import src.routes.trading as _tr

    monkeypatch.setattr(_scanner, "ticker_names", {TICKER: "테스트종목"}, raising=False)
    monkeypatch.setattr(_oe, "update_trade_status", AsyncMock(return_value=1))
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "_lookup_strategy_from_trade_history",
                        AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "_update_trade_status_by_order_no", AsyncMock(return_value=1))
    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "safe_write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_positions, "save_position", AsyncMock(return_value=None))
    monkeypatch.setattr(_positions, "delete_position", AsyncMock(return_value=None))

    reg = StrategyRegistry()
    strats = {sid: _Strat(sid) for sid in ("momentum", "kojiro")}
    for s in strats.values():
        reg.register(s)
    strats["kojiro"].state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=10_000, quantity=10, order_no="BUY-1",
        strategy_id="kojiro", buy_date=date(2026, 9, 21),
    )
    engine = OrderEngine(reg)
    engine._unsubscribe_if_no_other_strategy = AsyncMock(return_value=None)

    monkeypatch.setattr(_tr, "trading_scheduler",
                        SimpleNamespace(registry=reg, order_engine=engine))

    route_insert = AsyncMock(return_value=None)
    monkeypatch.setattr(_th, "insert_trade", route_insert)

    state = SimpleNamespace(engine=engine, s=strats, route_insert=route_insert,
                            seen_selling_at_send=None, place_calls=0)

    def install_place(*, notice_qty: int = 0, raises: Exception | None = None):
        from src.models.order import OrderResult

        async def fake_place_order(ticker, side, quantity, price=0, **kwargs):
            state.place_calls += 1
            state.seen_selling_at_send = ticker in engine._selling
            if raises is not None:
                raise raises
            if notice_qty:
                # 시장가 즉시 체결 — REST 응답보다 체결통보가 먼저 온다(매핑 부재 창)
                await engine.handle_execution_notice(
                    ticker=TICKER, order_no=NEW_NO, side="SELL", price=11_000,
                    quantity=notice_qty, ordered_qty_payload=quantity,
                )
            return OrderResult(order_no=NEW_NO, order_time="100000", krx_org_no="00950")

        monkeypatch.setattr(_api_order, "place_order", fake_place_order)

    state.install_place = install_place
    return state


async def _call(qty: int):
    from src.routes.trading import ManualSellRequest, manual_sell

    return await manual_sell(ManualSellRequest(ticker=TICKER, quantity=qty))


@pytest.mark.asyncio
async def test_t27_fill_before_rest_response_leaves_no_selling_zombie(env):
    """🔴 T27 — 10주 중 3주 manual 시장가가 REST 응답 전에 체결 → 반환 뒤
    `_selling` 은 비어 있고 보유는 7 이다.

    HEAD: 체결통보가 포지션을 지우고(또는 momentum 오귀속), 그 뒤 라우트가 `_selling.add`
    → 열린 주문이 없는 좀비. B7 뒤라면 그 좀비가 잔여 7주의 손절을 막는다.
    """
    env.install_place(notice_qty=3)

    resp = await _call(3)

    assert resp.success is True, resp.message
    assert TICKER not in env.engine._selling, (
        "manual 주문이 이미 전량 체결됐는데 `_selling` 이 남았다 — 잔여 보유 손절 마비"
    )
    pos = env.s["kojiro"].state.positions.get(TICKER)
    assert pos is not None and pos.quantity == 7, (
        f"manual 3주 매도 뒤 보유 {getattr(pos, 'quantity', None)} (기대 7)"
    )


_ROUTE_LOGGER = "src.routes.trading"


def _route_warn(caplog, prefix: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.name == _ROUTE_LOGGER and r.levelno >= logging.WARNING
        and r.getMessage().startswith(prefix)
    ]


def _route_fail_lines(caplog) -> list[str]:
    """라우트 실패 줄(`수동 매도 실패: …`, ERROR) — 부록 R4 D2 의 분류 칸 `selling_released=` 를 싣는다."""
    return [
        r.getMessage() for r in caplog.records
        if r.name == _ROUTE_LOGGER and r.levelno >= logging.ERROR
        and r.getMessage().startswith("수동 매도 실패:")
    ]


@pytest.mark.asyncio
async def test_tk11a_quantity_rejection_rolls_back_selling_it_added(env, caplog):
    """🔴 TK11a (부록 R3 K2 — T28 교체) — 발사가 **확정적으로 안 된** 실패(APBK0400 수량 초과)면
    라우트가 세운 `_selling`·`_selling_since` 를 되돌린다 · `[manual_sell_selling_kept]` 0."""
    from src.api.base import KisApiError

    caplog.set_level(logging.DEBUG)
    env.install_place(raises=KisApiError(rt_cd="1", msg_cd="APBK0400",
                                         msg1="주문 가능한 수량을 초과했습니다."))

    resp = await _call(30)

    assert resp.success is False
    assert TICKER not in env.engine._selling, "수량 초과로 거부됐는데 `_selling` 이 남았다(좀비)"
    assert TICKER not in env.engine._selling_since
    assert not _route_warn(caplog, "[manual_sell_selling_kept]")
    fails = _route_fail_lines(caplog)                       # 부록 R4 D2 — 분류 칸
    assert len(fails) == 1 and "selling_released=qty_exceeded" in fails[0], fails


def _unproven_send_errors():
    """부록 R4 D2 — 「시장가 주문 불가」(APBK3013)는 시장가 불가 분류기에 걸리는 결정적 거부라 이
    목록에서 빠져 TR4-R1(되돌림)로 옮겼다. 대신 **앞 시도의 접수가 만들 수 있는** 보유 부족 문구 ·
    모르는 코드 · 전송 타임아웃을 넣는다."""
    import httpx

    from src.api.base import KisApiError

    return [
        RuntimeError("KIS down"),
        KisApiError(rt_cd="1", msg_cd="EGW00201", msg1="초당 거래건수를 초과하였습니다."),
        KisApiError(rt_cd="1", msg_cd="APBK0918", msg1="매도가능수량이 부족합니다."),
        KisApiError(rt_cd="1", msg_cd="APBK9999", msg1="처리 중 오류가 발생했습니다."),
        httpx.ReadTimeout("read timeout"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc", _unproven_send_errors(),
    ids=["runtime", "egw00201", "apbk0918_holding_short", "unknown_code", "read_timeout"],
)
async def test_tk11b_unproven_send_failure_keeps_selling(env, caplog, exc):
    """🔴 TK11b (부록 R3 K2 — T28 교체) — APBK0400 밖의 발사 실패(전송 예외·다른 거부 코드)는
    **되돌리지 않는다**. `src/api/base.py::_request` 는 주문 POST 도 전송 실패·5xx 에 재시도하므로
    앞 시도가 접수됐는데 응답만 잃었을 수 있다 — 되돌리면 걸린 manual 주문 옆에서 다음 틱 손절이
    또 나간다(N1 의 라우트 판).

    기대: `success=False` · `_selling`·`_selling_since` **유지** · `src.routes.trading` WARNING
    `[manual_sell_selling_kept]` 1행(`ticker=005930`). 해제는 그 주문의 종료 통보 또는
    `selling_reconcile`(열린 매도 0 · 180초)이 한다.
    """
    caplog.set_level(logging.DEBUG)
    env.install_place(raises=exc)

    resp = await _call(3)

    assert resp.success is False
    assert TICKER in env.engine._selling, "발사 여부를 모르는데 `_selling` 을 풀었다"
    assert TICKER in env.engine._selling_since
    lines = _route_warn(caplog, "[manual_sell_selling_kept]")
    assert len(lines) == 1 and f"ticker={TICKER}" in lines[0], lines
    fails = _route_fail_lines(caplog)                       # 부록 R4 D2 — 분류 칸
    assert len(fails) == 1 and "selling_released=-" in fails[0], fails


def _deterministic_rejections():
    from src.api.base import KisApiError

    def k(code, msg):
        return KisApiError(rt_cd="1", msg_cd=code, msg1=msg)

    return [
        (k("APBK0918", "장운영시간이 아닙니다."), "market_closed"),
        (k("APBK0918", "장운영시간이 아닙니다.([프리마켓] 시장가 매매 불가 시간)"), "market_closed"),
        (k("APBK1943", "시장가호가불가 종목입니다."), "market_order_disallowed"),
        (k("APBK3013", "[애프터마켓]지정가 및 최유리/최우선지정가 주문만 가능합니다."),
         "market_order_disallowed"),
        (k("APBK3013", "시장가 주문 불가"), "market_order_disallowed"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc,cls", _deterministic_rejections(),
    ids=["apbk0918_closed", "apbk0918_premarket", "apbk1943", "apbk3013_after", "apbk3013_tk11b_old"],
)
async def test_tr4_r1_deterministic_rejection_rolls_back_selling_it_added(env, caplog, exc, cls):
    """🔴 TR4-R1 (부록 R4 D2 · 라우트) — 라우트가 세운 `_selling` 은 **주문 자체의 결정적 거부**(시장가
    불가 · 장운영시간 외)에도 되돌린다 — 같은 본문의 첫 시도도 똑같이 거부됐을 것이라 아무것도 안
    걸렸다(루트 규칙 「APBK0918 거부는 `_selling` 을 해제한다 — 보존하면 좀비 = 손절 마비」).

    기대: `success=False` · `_selling`·`_selling_since` 비움 · `[manual_sell_selling_kept]` 0 ·
    실패 줄 `selling_released=<cls>`.
    R3(APBK0400 만): 애프터마켓에 이 버튼을 한 번 누르면(APBK3013 — docstring 의 알려진 별건) 그 종목
    자동 손절이 `selling_reconcile`(15분 sync + 180초, 09:30 전에는 안 돈다)까지 멈췄다.
    `apbk3013_tk11b_old` = R3 TK11b 의 옛 「유지」 행 — 문구가 시장가 불가 분류기에 걸려 뒤집힌다.
    """
    caplog.set_level(logging.DEBUG)
    env.install_place(raises=exc)

    resp = await _call(3)

    assert resp.success is False
    assert TICKER not in env.engine._selling, f"{exc!r} 는 안 걸린 게 확정인데 `_selling` 이 남았다(좀비)"
    assert TICKER not in env.engine._selling_since
    assert not _route_warn(caplog, "[manual_sell_selling_kept]")
    fails = _route_fail_lines(caplog)
    assert len(fails) == 1 and f"selling_released={cls}" in fails[0], fails


def _guest_failures():
    from src.api.base import KisApiError

    return [
        KisApiError(rt_cd="1", msg_cd="APBK0400", msg1="주문 가능한 수량을 초과했습니다."),
        KisApiError(rt_cd="1", msg_cd="APBK0918", msg1="장운영시간이 아닙니다."),
        KisApiError(rt_cd="1", msg_cd="APBK3013",
                    msg1="[애프터마켓]지정가 및 최유리/최우선지정가 주문만 가능합니다."),
        RuntimeError("KIS down"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", _guest_failures(),
                         ids=["apbk0400", "apbk0918_closed", "apbk3013_after", "runtime"])
async def test_tr4_r2_guest_send_failure_never_touches_owner_selling(env, caplog, exc):
    """🔴 TR4-R2 (부록 R4 D5 · MX7 킬러) — 자동 손절이 이미 `_selling` 의 주인이다(표식 · 시각 선재) →
    운영자가 수동 매도(손님, `_added` 거짓) → 발사 실패(결정적 거부 포함).

    기대: `_selling`·`_selling_since` **그대로** · `[manual_sell_selling_kept]` 0 · 실패 줄
    `selling_released=-`. 손님의 실패는 주인의 걸린 주문에 대해 아무것도 말해 주지 않는다 — `_added`
    조건을 빼면(MX7) 손님의 APBK0400 이 걸린 자동 손절 옆에서 표식을 풀어 다음 틱 손절이 또 나간다.
    """
    caplog.set_level(logging.DEBUG)
    since = datetime(2026, 9, 28, 10, 0, tzinfo=KST)
    env.engine._selling.add(TICKER)
    env.engine._selling_since[TICKER] = since
    env.install_place(raises=exc)

    resp = await _call(3)

    assert resp.success is False
    assert TICKER in env.engine._selling, f"손님 manual 의 {exc!r} 가 주인의 `_selling` 을 풀었다"
    assert env.engine._selling_since.get(TICKER) == since
    assert not _route_warn(caplog, "[manual_sell_selling_kept]")
    fails = _route_fail_lines(caplog)
    assert len(fails) == 1 and "selling_released=-" in fails[0], fails


@pytest.mark.asyncio
async def test_t28b_send_failure_keeps_preexisting_selling(env):
    """🔴 T28b — 자동 매도가 이미 진행 중(`_selling` 선재)이면 라우트는 건드리지 않는다."""
    since = datetime(2026, 9, 28, 10, 0, tzinfo=KST)
    env.engine._selling.add(TICKER)
    env.engine._selling_since[TICKER] = since
    env.install_place(raises=RuntimeError("KIS down"))

    resp = await _call(3)

    assert resp.success is False
    assert TICKER in env.engine._selling, (
        "자동 매도 진행 중 표식을 manual 실패가 지웠다 — 열린 매도 위에 매도가 또 나간다"
    )
    assert env.engine._selling_since.get(TICKER) == since


@pytest.mark.asyncio
async def test_t28c_failure_after_send_does_not_release_selling(env):
    """🔴 T28c — 발사 **뒤** 실패(장부 INSERT 예외)는 되돌리지 않는다 — 주문은 이미
    거래소에 있고, 그 주문의 종료 통보가 해제한다(루트 금기 「주문이 나간 뒤의 실패」)."""
    env.install_place()
    env.route_insert.side_effect = RuntimeError("unique violation")

    await _call(3)

    assert TICKER in env.engine._selling, (
        "주문이 이미 나갔는데 `_selling` 을 풀었다 — 열린 manual 매도 위에 손절이 또 나간다"
    )


@pytest.mark.asyncio
async def test_t29_selling_is_set_before_send(env):
    """🔴 T29 — 정상 접수: `_selling` 은 `place_order` **호출 시점에 이미** 서 있고
    `_selling_since` 도 기록된다(selling_reconcile 의 age 게이트가 쓴다)."""
    env.install_place()

    resp = await _call(3)

    assert resp.success is True
    assert env.seen_selling_at_send is True, (
        "`place_order` 호출 시점에 `_selling` 이 없었다 — 발사 뒤에 세우면 선행 체결이 "
        "해제한 뒤 다시 세워 좀비가 된다"
    )
    assert TICKER in env.engine._selling
    assert isinstance(env.engine._selling_since.get(TICKER), datetime)


# ════════════════════════════════════════════════════════════════════════════
# 부록 R-3 · R-4 · R2 — manual 표식(`_manual_sell_orders`)과 `_selling` (TR20 · TR23 · TQ15 · TQ25)
#
# 라우트는 매핑 3종과 **같은 동기 구간**에서 `engine._manual_sell_orders[order_no] = _added`
# 를 적는다(`strategy_id` 로 추론하지 않는다). 값 = 그 주문이 `_selling` 을 **세웠는가**.
# manual 주문의 잔여는 보유자와 무관하게 재주문한다(R-4).
# 부록 R2 — 주문 종료의 `_selling` 해제는 조건이 없다(R-3 주인 규칙 제거). 손님 manual 의 종료가
# 자동 손절의 표식을 푸는 것은 LOW #3 알려진 한계(TR20·TR20b strict xfail). 표식이 여전히 가르는
# 것 = J-2 의 manual 분기(R-4)와, 재주문이 안 걸렸을 때 `_selling` 을 풀어도 되는 주인인가(H5 · TQ15).
# ════════════════════════════════════════════════════════════════════════════
_OE_LOGGER = "src.engine.order_engine"


async def _notice(engine, order_no: str, qty: int, payload: int) -> None:
    await engine.handle_execution_notice(
        ticker=TICKER, order_no=order_no, side="SELL", price=11_000, quantity=qty,
        ordered_qty_payload=payload,
    )


@pytest.mark.xfail(
    strict=True,
    reason="LOW #3 알려진 한계(손님 manual 변형) — 부록 R2-1, F-385-5 가 생기면 뒤집힌다",
)
@pytest.mark.asyncio
async def test_tr20_guest_manual_end_does_not_release_the_owner_selling(env):
    """🟡 TR20 (부록 R2-1 알려진 한계 — 아래는 한계가 풀렸을 때의 기대 · 부록 R3 K5 로 행위만 잰다) —
    자동 매도 S1(10주, 매핑) 이 걸려 `_selling` 선재. 라우트로 3주(손님 manual, `_added` 거짓) →
    그 주문 전량 체결(map) → `_selling` **유지**. 이어 S1 전량 체결(map) → 해제.

    마커는 단언하지 않는다 — 부록 R 의 `[selling_kept]` 는 AR2-2 가 금지했으므로, 마커를 재면
    LOW #3 이 고쳐져도 이 테스트가 영원히 xfail 로 남는다(XPASS 로 뒤집히는 신호가 죽는다).

    B7: 손님 manual 의 종료가 `_selling` 을 풀어, 자동 손절 S1 이 걸린 채로 다음 틱 손절이
    한 번 더 나간다(우리 주문 합 > 추적 — R-INV-2).
    """
    eng = env.engine
    eng._selling.add(TICKER)
    eng._selling_since[TICKER] = datetime(2026, 9, 28, 10, 0, tzinfo=KST)
    eng._order_qty["S1"] = 10
    eng._order_strategy["S1"] = "kojiro"
    eng._order_ticker["S1"] = TICKER
    env.install_place()

    resp = await _call(3)
    assert resp.success is True, resp.message
    assert eng._manual_sell_orders.get(NEW_NO) is False, "손님 manual 표식(`_added` 거짓)이 없다"

    await _notice(eng, NEW_NO, 3, 3)
    assert TICKER in eng._selling, "손님 manual 의 종료가 자동 손절(S1)의 `_selling` 을 풀었다"

    await _notice(eng, "S1", 10, 10)
    assert TICKER not in eng._selling, "주인(S1)이 끝났는데 `_selling` 이 남았다"


@pytest.mark.asyncio
async def test_tr23_route_manual_remainder_is_replaced_and_mark_inherited(env, monkeypatch):
    """🔴 TR23 — 보유 전략 없음(→ 라우트는 momentum 으로 적는다). 라우트 manual 5주 → map 2
    체결 → 30초 타이머 → 잔여 **3** 재주문 · 재주문 번호가 manual 표식을 물려받는다.

    라우트가 표식을 적지 않으면(MR28) J-2 가 `gone` → 운영자 주문 3주가 취소된 채 끝난다
    (프로브 test_p2: B7 0 / HEAD 3).
    """
    import src.engine.order_engine as _oe
    from src.config import settings
    from src.engine.order_engine import CANCEL_AXIS_SELL

    monkeypatch.setattr(settings, "kis_env", "vts")
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0)
    monkeypatch.setattr(_oe, "cancel_order", AsyncMock(return_value=None))
    reorder = AsyncMock(return_value=SimpleNamespace(order_no="MAN-RE-1", order_time="",
                                                     krx_org_no=""))
    monkeypatch.setattr(_oe, "place_order", reorder)
    eng = env.engine
    del env.s["kojiro"].state.positions[TICKER]
    env.install_place()

    resp = await _call(5)
    assert resp.success is True, resp.message
    assert eng._manual_sell_orders.get(NEW_NO) is True

    await _notice(eng, NEW_NO, 2, 5)
    task = eng._pending_cancel_tasks.get((TICKER, CANCEL_AXIS_SELL))
    assert task is not None
    try:
        await task
    finally:
        for t in list(eng._pending_cancel_tasks.values()):
            t.cancel()

    fired = [c.kwargs.get("quantity") for c in reorder.await_args_list]
    assert fired == [3], f"재주문 {fired} (기대 [3]) — 운영자 manual 잔여를 버렸다"
    assert eng._manual_sell_orders.get("MAN-RE-1") is True, "재주문 번호가 manual 표식을 물려받지 않았다"


@pytest.mark.xfail(
    strict=True,
    reason="LOW #3 알려진 한계(손님 manual 변형) — 부록 R2-1, F-385-5 가 생기면 뒤집힌다",
)
@pytest.mark.asyncio
async def test_tr20b_guest_manual_ending_inside_send_window_keeps_owner_selling(env):
    """🟡 TR20b (부록 R2-1 알려진 한계 — 부록 R 의 `_sell_placed` 는 R2 가 지웠다) — TR20 과 같지만 손님 manual 이 **REST 응답보다
    먼저** 전량 체결된다(매핑 부재 창, payload). 발사 직후 `_sell_placed` 는 주인이 아닌 주문이라
    `_selling` 을 풀지 않는다 — 자동 손절 S1 이 아직 걸려 있다.

    `_sell_placed` 가 `owns_selling` 을 무시하면 손님의 빠른 체결이 주인 표식을 풀어 LOW #3 이
    라우트 경로로 되살아난다(돌연변이 XR1 이 기존 표본에서 살아남았다).
    """
    eng = env.engine
    eng._selling.add(TICKER)
    eng._selling_since[TICKER] = datetime(2026, 9, 28, 10, 0, tzinfo=KST)
    eng._order_qty["S1"] = 10
    eng._order_strategy["S1"] = "kojiro"
    eng._order_ticker["S1"] = TICKER
    env.install_place(notice_qty=3)

    resp = await _call(3)

    assert resp.success is True, resp.message
    assert eng._manual_sell_orders.get(NEW_NO) is False
    assert TICKER in eng._selling, (
        "손님 manual 이 발사 창에서 끝나자 자동 손절(S1)의 `_selling` 이 풀렸다 — S1 이 걸린 채로 "
        "다음 틱 손절이 또 나간다"
    )
    await _notice(eng, "S1", 10, 10)
    assert TICKER not in eng._selling


@pytest.mark.asyncio
async def test_tq25_route_entry_clears_stale_freeze_mark_so_close_release_keeps_new_owner(env):
    """🔴 TQ25 라우트 판 (부록 R2-5 안전 — 부록 R TR21b 교체) — 동결 표식만 남은 상태(`_selling` 은
    이미 풀렸다)에서 manual 5주가 접수돼 걸렸다. 외부 주문(20주)의 10주 **부분** 체결이 추적을
    0 으로 만든다 → `_selling` **유지**(manual 주문이 걸려 있다).

    라우트가 표식을 청소하지 않으면 보유 닫힘 해제(R2-5)가 「동결이 지키던 보유가 닫혔다」 로
    오판해 걸린 manual 주문의 `_selling` 을 푼다.
    """
    eng = env.engine
    eng._selling_locked_wait.add(TICKER)
    env.install_place()

    resp = await _call(5)
    assert resp.success is True, resp.message
    assert TICKER in eng._selling
    assert TICKER not in eng._selling_locked_wait, "라우트 진입이 낡은 동결 표식을 지우지 않았다"

    await _notice(eng, "0000064001", 10, 20)  # 매핑 없는 외부 주문의 부분 체결

    assert env.s["kojiro"].state.positions.get(TICKER) is None
    assert TICKER in eng._selling, (
        "manual 주문이 걸려 있는데 보유 닫힘이 `_selling` 을 풀었다"
    )


@pytest.mark.asyncio
async def test_tq15_route_guest_manual_rejected_reorder_keeps_owner_selling(env, monkeypatch, caplog):
    """🔴 TQ15 라우트 판 (XT-M · 부록 R2-6 주인 판정) — 자동 매도 S1(10)이 걸려 `_selling` 선재.
    라우트 manual 3주(손님, `_added` 거짓) → 1주 부분(map) → 30초 타이머 → 원주문 취소 성공 →
    재주문 KIS 거부 → `_selling` **유지**(S1 이 아직 걸려 있다) · `[reorder_selling_released]` 없음.

    주인 판정 없이 풀면 손님의 재주문 거부가 자동 손절 S1 의 표식을 풀어, S1 이 걸린 채로 다음
    틱 손절이 또 나간다.
    """
    import src.engine.order_engine as _oe
    from src.api.base import KisApiError
    from src.config import settings
    from src.engine.order_engine import CANCEL_AXIS_SELL

    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    monkeypatch.setattr(settings, "kis_env", "vts")
    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0)
    monkeypatch.setattr(_oe, "cancel_order", AsyncMock(return_value=None))
    reorder = AsyncMock(side_effect=KisApiError(
        rt_cd="1", msg_cd="APBK0400", msg1="주문 가능한 수량을 초과했습니다."))
    monkeypatch.setattr(_oe, "place_order", reorder)
    eng = env.engine
    eng._selling.add(TICKER)
    eng._selling_since[TICKER] = datetime(2026, 9, 28, 10, 0, tzinfo=KST)
    eng._order_qty["S1"] = 10
    eng._order_strategy["S1"] = "kojiro"
    eng._order_ticker["S1"] = TICKER
    env.install_place()

    resp = await _call(3)
    assert resp.success is True, resp.message
    assert eng._manual_sell_orders.get(NEW_NO) is False

    await _notice(eng, NEW_NO, 1, 3)
    task = eng._pending_cancel_tasks.get((TICKER, CANCEL_AXIS_SELL))
    assert task is not None
    try:
        await task
    finally:
        for t in list(eng._pending_cancel_tasks.values()):
            t.cancel()

    assert [c.kwargs.get("quantity") for c in reorder.await_args_list] == [2]
    assert TICKER in eng._selling, (
        "손님 manual 의 재주문 거부가 자동 손절(S1)의 `_selling` 을 풀었다"
    )
    released = [
        r.getMessage() for r in caplog.records
        if r.name == _OE_LOGGER and r.levelno >= logging.WARNING
        and r.getMessage().startswith("[reorder_selling_released]")
    ]
    assert not released, released
