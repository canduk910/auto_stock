"""cycle422-net — 매도 함수 `execute_sell` B4-3·B4-5 착수 전 선행 그물(테스트만).

리팩토링 카드 #12 1단계(사용자 결정 2026-10-09 「리팩토링 권고대로」). 이 파일은 `src/` 를
바꾸지 않는다. 다음 두 덩어리를 **행위로** 핀한다 — 분리 리팩토링(B4-3 `_handle_sell_market_disallowed`
· B4-5 마지막 실패 뒤처리 추출)이 행위를 바꾸면 여기가 붉어진다.

- ⑰ 시장가 거부 → 지정가 폴백 블록(`order_engine.py` `if order_division == primary_div and (...)`
  부터 폴백 거부 `return` 까지) — 진입 관문 · ETP 관측 · 현재가 미확보 · 발사 · 매핑 · 접수 후
  영속화 · 성공 TTL · 거부 후처리(익일청산·포기 래치) 전 분기.
- ⑲ 마지막 실패 뒤처리(재시도 루프 다음 ~ 함수 끝) — 최종 실패 CRITICAL(cycle429 D1 안A 이후
  잔고부족/수량부족 정리 분기는 `_handle_sell_insufficient_quantity` 로 이동, P 절 참조).
- 부록 B4-4 대비 — `test_cycle236_sell_qty_exceeded.py` 가 APBK0400 5분기에서 빠뜨린
  `_selling` 유지·해제와 continue/return/break 핀만 더한다(G 절).

기준선 문서 = `_workspace/refactor/2026-10-09_execute_sell_baseline.md`(블록 번호·줄 앵커·CC).
규약 = `_workspace/refactor/2026-09-20_execute_sell_plan.md` §4 「절대 건드리지 않는 것」.

핀하는 것(분기마다): 주문 호출 인자·횟수 · `_selling`(그리고 `_selling_since`) 상태 · 매핑 5종 ·
PENDING 행 · TTL 등록 인자 · 익일청산 큐 · 로그 마커 · return/continue/전파 · 재시도 backoff.

🔄 cycle428(F-422-1, 사용자 승인 2026-10-10) — `test_f07_*` 는 뒤집힌 핀이다: 폴백 `place_order`
가 `KisApiError` 가 **아닌** 예외(전송 오류·타임아웃)를 내면 더 이상 `execute_sell` 밖으로 전파되지
않는다. `_handle_sell_market_disallowed` 안의 새 `except Exception` 이 `SellFallbackOutcome.UNKNOWN`
을 돌려주고, 호출부는 `_selling`·`_selling_since` 를 유지한 채 `return` 한다(재발사 0). 상세 =
`src/engine/CLAUDE.md` `order_engine.py` 절 「매도 결과 모름(UNKNOWN)」.

결정성 — 벽시계 의존 차단: 정규장 절은 `settings.kis_env="vts"`(애프터 변환 불가) + `is_nxt_session_hours`
주입, 애프터 절은 `freeze_time` + 실전(`real`). `asyncio.sleep` 은 order_engine 모듈 안에서만
즉시 반환으로 바꾸고 지연 값을 기록한다(freezegun 동결 monotonic 에서 실제 sleep 은 영구 hang).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from freezegun import freeze_time

from src.api.base import KisApiError
from src.engine.order_engine import SELL_MAX_RETRIES, SELL_RETRY_DELAY, OrderEngine
from src.engine.session import boards_at
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.engine.util.tick_size import step_down
from src.models.order import OrderDivision, OrderResult, OrderSide
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.unit

_OE = "src.engine.order_engine"
_T = "012200"
_SID = "momentum"
_QTY = 10
_BUY = 4500
_CUR = 4600
_FB = step_down(_CUR, steps=5)  # 정규장 폴백 지정가 = 애프터 41 지정가
_F_1605 = "2026-09-14 07:05:00"  # KST 2026-09-14 16:05:00 — KRX 애프터마켓(K6) · NXT 시간대
_AFTER_DAY = date(2026, 9, 14)
_KST = timezone(timedelta(hours=9))


# ===========================================================================
# 리그
# ===========================================================================
class _Strat(StrategyBase):
    def __init__(self, **params) -> None:
        merged = {"exchange": "KRX"}
        merged.update(params)
        super().__init__(
            StrategyConfig(
                strategy_id=_SID, name="net-dummy", enabled=True, weight=1.0,
                params=merged,
            )
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


class _AsyncioProxy:
    """order_engine 모듈의 `asyncio` 만 바꾼다 — sleep 은 즉시 반환 + 지연 기록.

    `create_task_fails=True` 면 `create_task` 가 「이벤트 루프 없음」 RuntimeError 를 낸다(ETP
    관측 등록 실패 분기). 넘겨받은 코루틴은 닫아 「never awaited」 경고를 남기지 않는다.
    """

    def __init__(self) -> None:
        self.sleeps: list[float] = []
        self.create_task_fails = False

    def __getattr__(self, name):
        return getattr(asyncio, name)

    async def sleep(self, delay, *_a, **_k):
        self.sleeps.append(delay)

    def create_task(self, coro, **kw):
        if self.create_task_fails:
            coro.close()
            raise RuntimeError("no running event loop")
        return asyncio.create_task(coro, **kw)


def _build(monkeypatch: pytest.MonkeyPatch, *, production: bool = False,
           patch_nxt: bool = True, prices: dict | None = None, **params):
    """정규장(기본) 또는 애프터(production=True + freeze_time) 리그."""
    import src.api.balance as _balance
    import src.db.positions as _positions
    import src.db.stock_master as _sm
    import src.engine.order_engine as _oe
    from src.config import settings
    from src.engine import scanner

    r = SimpleNamespace()
    r.events: list[str] = []
    reg = StrategyRegistry()
    strat = _Strat(**params)
    strat.state.positions[_T] = Position(
        ticker=_T, buy_price=_BUY, quantity=_QTY, order_no="ORDER-PRE",
        strategy_id=_SID, buy_date=date(2026, 9, 10),
    )
    reg.register(strat)
    eng = OrderEngine(reg)
    r.strat, r.eng = strat, eng

    r.pending: set = set()
    eng._pending_next_day_clear_provider = lambda: r.pending

    r.nxt = False
    if patch_nxt:
        monkeypatch.setattr(_oe, "is_nxt_session_hours", lambda _now: r.nxt)

    r.aio = _AsyncioProxy()
    monkeypatch.setattr(_oe, "asyncio", r.aio)

    r.place = AsyncMock()

    async def _place(**kw):
        r.events.append("place")
        return await r.place(**kw)

    monkeypatch.setattr(_oe, "place_order", _place)

    r.insert = AsyncMock(return_value=None)

    async def _insert(record):
        r.events.append("insert")
        # 매핑 동기 영역 — PENDING INSERT(최초 양보점) 앞에서 매핑 5종이 이미 서 있어야 한다.
        r.mapped_at_insert = {
            "qty": eng._order_qty.get(record.order_no),
            "strategy": eng._order_strategy.get(record.order_no),
            "ticker": eng._order_ticker.get(record.order_no),
            "exchange": eng._order_exchange.get(record.order_no),
            "division": eng._order_division.get(record.order_no),
        }
        return await r.insert(record)

    monkeypatch.setattr(_oe, "insert_trade", _insert)

    r.write_log = AsyncMock(return_value=None)

    async def _write_log(level, msg, *a, **k):
        r.events.append(f"write_log:{level}")
        r.selling_at_write_log = _T in eng._selling
        return await r.write_log(level, msg, *a, **k)

    monkeypatch.setattr(_oe, "write_log", _write_log)

    r.safe_write_log = AsyncMock(return_value=None)

    async def _safe_write_log(level, msg, *a, **k):
        r.events.append(f"safe_write_log:{level}")
        return await r.safe_write_log(level, msg, *a, **k)

    monkeypatch.setattr(_oe, "safe_write_log", _safe_write_log)

    r.delete_position = AsyncMock(return_value=None)

    async def _delete(ticker):
        r.events.append("delete_position")
        r.selling_at_delete = _T in eng._selling
        return await r.delete_position(ticker)

    monkeypatch.setattr(_positions, "delete_position", _delete)
    r.save_position = AsyncMock(return_value=None)
    monkeypatch.setattr(_positions, "save_position", r.save_position)

    r.get_balance = AsyncMock(return_value=([], SimpleNamespace(net_asset=0)))

    async def _get_balance(*a, **k):
        r.events.append("get_balance")
        return await r.get_balance(*a, **k)

    monkeypatch.setattr(_balance, "get_balance", _get_balance)
    r.get_daily_orders = AsyncMock(return_value=[])
    monkeypatch.setattr(_balance, "get_daily_orders", r.get_daily_orders)

    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "upsert_one", AsyncMock(return_value=None))
    monkeypatch.setattr(_sm, "is_stale", AsyncMock(return_value=False))
    monkeypatch.setattr(OrderEngine, "_strategy_exchange_async", AsyncMock(return_value="KRX"))
    monkeypatch.setattr(
        scanner, "ticker_prices",
        {_T: {"current_price": _CUR}} if prices is None else prices,
    )
    monkeypatch.setattr(settings, "kis_env", "real" if production else "vts")

    # TTL 등록(30초) 스파이 — 실제 tracker 를 감싼다(상태는 그대로 쌓인다).
    real_ttl = eng._sell_rejection.register_market_order_disallowed

    def _ttl(*a, **k):
        r.events.append("ttl")
        return real_ttl(*a, **k)

    r.ttl = MagicMock(side_effect=_ttl)
    monkeypatch.setattr(eng._sell_rejection, "register_market_order_disallowed", r.ttl)

    real_bump = eng._bump_after_exit_fails_and_maybe_giveup

    def _bump(*a, **k):
        r.events.append("bump")
        return real_bump(*a, **k)

    r.bump = MagicMock(side_effect=_bump)
    monkeypatch.setattr(eng, "_bump_after_exit_fails_and_maybe_giveup", r.bump)

    r.etp = AsyncMock(return_value=None)
    monkeypatch.setattr(eng, "_observe_after_exit_etp", r.etp)

    real_closed = strat.on_position_closed

    def _closed(ticker):
        r.events.append("on_position_closed")
        r.held_at_closed = ticker in strat.state.positions
        return real_closed(ticker)

    r.on_closed = MagicMock(side_effect=_closed)
    monkeypatch.setattr(strat, "on_position_closed", r.on_closed)
    return r


def _pin_boards(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.engine.session import session_tracker

    monkeypatch.setattr(session_tracker, "_active", boards_at(datetime.now(_KST).time()))


def _recs(caplog, level: int, prefix: str = "") -> list[str]:
    """order_engine 로거 · 정확히 그 레벨 · 접두 일치(CI 루트 로거 DEBUG 대비)."""
    return [
        r.getMessage() for r in caplog.records
        if r.name == _OE and r.levelno == level and r.getMessage().startswith(prefix)
    ]


def _ok(no: str) -> OrderResult:
    return OrderResult(order_no=no, order_time="100001", krx_org_no="")


def _disallowed() -> KisApiError:
    return KisApiError(rt_cd="1", msg_cd="APBK1943", msg1="시장가호가불가로 주문이 불가합니다.")


def _unclassified(msg1: str = "초당 거래건수를 초과하였습니다.") -> KisApiError:
    return KisApiError(rt_cd="1", msg_cd="EGW00201", msg1=msg1)


def _after_unclassified(msg1: str = "주문구분코드 오류입니다.") -> KisApiError:
    return KisApiError(rt_cd="1", msg_cd="APBK9999", msg1=msg1)


def _limit_rejected() -> KisApiError:
    return KisApiError(rt_cd="1", msg_cd="APBK0919", msg1="가격 범위 오류입니다.")


def _insufficient() -> KisApiError:
    return KisApiError(rt_cd="1", msg_cd="APBK1234", msg1="매도가능수량이 부족합니다.")


def _qty_exceeded() -> KisApiError:
    return KisApiError(rt_cd="1", msg_cd="APBK0400", msg1="주문 가능한 수량을 초과했습니다.")


async def _sell(r, signal: Signal = Signal.STOP_LOSS, **kw) -> None:
    await r.eng.execute_sell(_T, signal, _SID, **kw)


def _assert_final_critical(r, caplog, err: BaseException, signal: Signal = Signal.STOP_LOSS) -> None:
    msg = f"매도 주문 최종 실패: {_T} {signal.value} — {err}"
    assert _recs(caplog, logging.CRITICAL) == [msg]
    r.write_log.assert_any_await("CRITICAL", msg)


# ===========================================================================
# F — ⑰ 폴백 블록 · 정규장(primary = 시장가)
# ===========================================================================
@pytest.mark.asyncio
async def test_f01_gate_false_when_unclassified_market_rejection_then_plain_retries(monkeypatch, caplog):
    """관문 거짓① — 시장가인데 거부가 「시장가 불가」 가 아니다 → 폴백 없이 3회 재시도 → ⑲ CRITICAL."""
    caplog.set_level(logging.DEBUG, logger=_OE)
    r = _build(monkeypatch)
    errs = [_unclassified("첫째"), _unclassified("둘째"), _unclassified("셋째")]
    r.place.side_effect = errs
    await _sell(r)

    assert r.place.await_count == SELL_MAX_RETRIES
    for c in r.place.await_args_list:
        assert c.kwargs["order_division"] is OrderDivision.MARKET
        assert c.kwargs["price"] == 0
        assert c.kwargs["quantity"] == _QTY
    r.ttl.assert_not_called()
    r.bump.assert_not_called()
    r.etp.assert_not_called()
    assert r.aio.sleeps == [SELL_RETRY_DELAY, SELL_RETRY_DELAY * 2]
    assert len(_recs(caplog, logging.WARNING, "매도 주문 실패 (시도 ")) == SELL_MAX_RETRIES
    assert _recs(caplog, logging.WARNING, "매도 시장가 거부 → 지정가") == []
    _assert_final_critical(r, caplog, errs[-1])  # last_error = 마지막 거부
    assert _T not in r.eng._selling
    assert r.strat.state.positions[_T].quantity == _QTY
    assert r.pending == set()


@pytest.mark.asyncio
async def test_f02_gate_false_when_limit_order_then_no_fallback_even_if_disallowed(monkeypatch, caplog):
    """관문 거짓② — `order_division != primary_div`(지정가 매도) → 「시장가 불가」 라도 폴백 없음."""
    r = _build(monkeypatch)
    monkeypatch.setattr(OrderEngine, "_apply_clock", MagicMock(return_value="NXT"))
    r.place.side_effect = [_disallowed()] * SELL_MAX_RETRIES
    await _sell(r, Signal.NEXT_DAY_CLEAR, limit_price=4495)

    assert r.place.await_count == SELL_MAX_RETRIES
    for c in r.place.await_args_list:
        assert c.kwargs["order_division"] is OrderDivision.LIMIT
        assert c.kwargs["price"] == 4495
        assert c.kwargs["exchange"] == "NXT"
    r.ttl.assert_not_called()
    assert r.aio.sleeps == [SELL_RETRY_DELAY, SELL_RETRY_DELAY * 2]
    assert _T not in r.eng._selling


@pytest.mark.asyncio
@pytest.mark.parametrize("nxt", [False, True], ids=["krx_hours", "nxt_hours"])
async def test_f03_fallback_success_pins_order_mapping_pending_ttl_and_return(monkeypatch, caplog, nxt):
    """폴백 성공 — 발사 인자 · 매핑 5종(INSERT 전) · PENDING 행 · TTL(성공) · return(재시도 0)."""
    caplog.set_level(logging.DEBUG, logger=_OE)
    r = _build(monkeypatch)
    r.nxt = nxt
    r.place.side_effect = [_disallowed(), _ok("FB-1")]
    await _sell(r)

    assert r.place.await_count == 2
    first, second = r.place.await_args_list
    assert first.kwargs["order_division"] is OrderDivision.MARKET and first.kwargs["price"] == 0
    assert second.kwargs == {
        "ticker": _T, "side": OrderSide.SELL, "quantity": _QTY, "price": _FB,
        "order_division": OrderDivision.LIMIT, "exchange": "KRX",
    }
    # 매핑 5종 — 폴백 주문번호로, INSERT(최초 await) **전**에 이미 서 있다.
    expected_map = {"qty": _QTY, "strategy": _SID, "ticker": _T, "exchange": "KRX", "division": "00"}
    assert r.mapped_at_insert == expected_map
    assert r.eng._order_division["FB-1"] == OrderDivision.LIMIT.value
    # PENDING 행 — 폴백 지정가 · 송신 수량 · 주문가 = 폴백 지정가.
    assert r.insert.await_count == 1
    rec = r.insert.await_args.args[0]
    assert (rec.order_no, rec.ticker, rec.trade_type, rec.status) == ("FB-1", _T, TradeType.SELL, TradeStatus.PENDING)
    assert (rec.price, rec.quantity, rec.strategy, rec.order_price) == (_FB, _QTY, _SID, _FB)
    # TTL 30초 — 성공으로 등록, NXT 여부는 그 시각 판정 그대로.
    assert r.ttl.call_count == 1
    assert r.ttl.call_args.args[0] == _T
    assert r.ttl.call_args.kwargs == {"is_nxt_session": nxt, "fallback_succeeded": True}
    assert r.eng._sell_rejection._blocked_reason[_T] == "market_order_disallowed"
    assert r.events == ["place", "place", "insert", "ttl"]
    # return — 재시도·backoff·뒤처리 없음. `_selling` 은 체결통보가 푼다.
    assert r.aio.sleeps == []
    assert _T in r.eng._selling
    assert r.pending == set()
    assert r.write_log.await_count == 0
    assert _recs(caplog, logging.CRITICAL) == []
    assert _recs(caplog, logging.INFO, "[after_exit_") == []
    r.etp.assert_not_called()
    r.bump.assert_not_called()
    warn = _recs(caplog, logging.WARNING, "매도 시장가 거부 → 지정가 5호가 폴백: ")
    assert len(warn) == 1
    assert f"@ {_FB} (원인 [APBK1943] 시장가호가불가로 주문이 불가합니다., 주문번호: FB-1, 전략: {_SID})" in warn[0]
    assert r.strat.state.positions[_T].quantity == _QTY


@pytest.mark.asyncio
async def test_f03b_fallback_quantity_is_this_attempts_send_qty_not_position(monkeypatch):
    """폴백 수량 = 그 회차 `send_qty`(부분 잠김 판매 `sell_cap` 반영) — `pos.quantity` 가 아니다."""
    r = _build(monkeypatch)
    # APBK0400 → 잔고 held 10 · sellable 3 → fire 3(continue) → 2회차 3주 시장가 거부 → 폴백 3주.
    r.get_balance.return_value = (
        [SimpleNamespace(ticker=_T, quantity=_QTY, sellable_quantity=3)],
        SimpleNamespace(net_asset=0),
    )
    r.place.side_effect = [_qty_exceeded(), _disallowed(), _ok("FB-3")]
    await _sell(r)

    qtys = [c.kwargs["quantity"] for c in r.place.await_args_list]
    assert qtys == [_QTY, 3, 3]
    assert r.place.await_args_list[2].kwargs["price"] == _FB
    assert r.eng._order_qty["FB-3"] == 3
    assert r.insert.await_args.args[0].quantity == 3
    assert r.strat.state.positions[_T].quantity == _QTY  # 추적 수량 불변(C236-F1)
    assert r.aio.sleeps == []  # 부분 잠김 판매 continue 는 backoff 를 건너뛴다


@pytest.mark.asyncio
@pytest.mark.parametrize("nxt", [False, True], ids=["krx_hours", "nxt_hours"])
async def test_f04_fallback_rejected_releases_selling_preserves_position_and_returns(monkeypatch, caplog, nxt):
    """폴백 거부 — `_selling` 해제(await 전) · 포지션 보존 · TTL(실패) · 장부 WARNING · return.

    NXT 시간대면 익일청산 큐 등록 + `[next_day_clear_deferred]`(F05 와 짝).
    """
    caplog.set_level(logging.DEBUG, logger=_OE)
    r = _build(monkeypatch)
    r.nxt = nxt
    fb_err = _limit_rejected()
    r.place.side_effect = [_disallowed(), fb_err]
    await _sell(r)

    assert r.place.await_count == 2
    assert r.place.await_args_list[1].kwargs["order_division"] is OrderDivision.LIMIT
    assert _T not in r.eng._selling
    assert r.selling_at_write_log is False  # discard 가 첫 await(write_log) 앞
    assert _T in r.eng._selling_since  # 현행 — 폴백 거부는 `_selling_since` 를 지우지 않는다
    assert r.strat.state.positions[_T].quantity == _QTY
    r.delete_position.assert_not_awaited()
    assert r.insert.await_count == 0
    assert len(r.eng._order_qty) == 0  # 폴백 주문번호가 없다 — 매핑 0
    assert r.ttl.call_count == 1
    assert r.ttl.call_args.kwargs == {"is_nxt_session": nxt, "fallback_succeeded": False}
    err = _recs(caplog, logging.ERROR, "매도 지정가 폴백도 거부 — 재시도 중단, 포지션 보존: ")
    assert len(err) == 1
    assert "([APBK1943] 시장가호가불가로 주문이 불가합니다. → [APBK0919] 가격 범위 오류입니다.)" in err[0]
    first_log = r.write_log.await_args_list[0]
    assert first_log.args[0] == "WARNING"
    assert first_log.args[1].startswith("매도 시장가+지정가 폴백 모두 거부 — 포지션 보존: ")
    assert first_log.args[1].endswith(f"(전략: {_SID}, [APBK0919] 가격 범위 오류입니다.)")
    if nxt:
        assert r.pending == {(_T, _SID)}
        assert r.write_log.await_count == 2
        r.write_log.assert_awaited_with(
            "WARNING",
            f"[next_day_clear_deferred] ticker={_T} strategy={_SID} "
            f"reason=market_order_disallowed_nxt_fallback_fail",
        )
        assert r.events == ["place", "place", "write_log:WARNING", "ttl", "write_log:WARNING"]
    else:
        assert r.pending == set()
        assert r.write_log.await_count == 1
        assert r.events == ["place", "place", "write_log:WARNING", "ttl"]
    assert r.aio.sleeps == []
    assert _recs(caplog, logging.CRITICAL) == []
    assert _recs(caplog, logging.WARNING, "매도 주문 실패 (시도 ") == []
    r.bump.assert_not_called()


@pytest.mark.asyncio
async def test_f05b_fallback_rejected_nxt_when_provider_returns_none_then_no_queue_no_log(monkeypatch, caplog):
    """익일청산 공급자가 None — 등록·로그 없이 return(분기 `_pending is not None` 거짓)."""
    r = _build(monkeypatch)
    r.nxt = True
    r.eng._pending_next_day_clear_provider = lambda: None
    r.place.side_effect = [_disallowed(), _limit_rejected()]
    await _sell(r)

    assert r.write_log.await_count == 1  # 「모두 거부」 1줄뿐
    assert _T not in r.eng._selling
    assert r.place.await_count == 2


@pytest.mark.asyncio
async def test_f05c_fallback_rejected_nxt_when_provider_raises_then_debug_and_return(monkeypatch, caplog):
    """익일청산 공급자 예외 — DEBUG 흔적만, 전파 없음, return."""
    caplog.set_level(logging.DEBUG, logger=_OE)
    r = _build(monkeypatch)
    r.nxt = True

    def _boom():
        raise RuntimeError("provider down")

    r.eng._pending_next_day_clear_provider = _boom
    r.place.side_effect = [_disallowed(), _limit_rejected()]
    await _sell(r)

    assert _recs(caplog, logging.DEBUG, "[next_day_clear_deferred] _pending_next_day_clear 등록 실패: ") == [
        f"[next_day_clear_deferred] _pending_next_day_clear 등록 실패: {_T}"
    ]
    assert r.write_log.await_count == 1
    assert _T not in r.eng._selling
    assert r.place.await_count == 2
    assert r.aio.sleeps == []


@pytest.mark.asyncio
async def test_f06_no_current_price_then_no_fallback_and_plain_retry(monkeypatch, caplog):
    """현재가 미확보(정규장) — 폴백 불가 WARNING → 일반 재시도 흐름(backoff) → ⑲ CRITICAL. TTL·포기 래치 없음."""
    r = _build(monkeypatch, prices={})
    errs = [_disallowed(), _disallowed(), _disallowed()]
    r.place.side_effect = errs
    await _sell(r)

    assert r.place.await_count == SELL_MAX_RETRIES
    assert all(c.kwargs["order_division"] is OrderDivision.MARKET for c in r.place.await_args_list)
    warn = _recs(caplog, logging.WARNING, "매도 시장가 호가 불가 — 현재가 캐시 미확보로 폴백 불가, 재시도 진행: ")
    assert len(warn) == SELL_MAX_RETRIES
    assert len(_recs(caplog, logging.WARNING, "매도 주문 실패 (시도 ")) == SELL_MAX_RETRIES
    r.ttl.assert_not_called()
    r.bump.assert_not_called()
    assert r.aio.sleeps == [SELL_RETRY_DELAY, SELL_RETRY_DELAY * 2]
    _assert_final_critical(r, caplog, errs[-1])
    assert _T not in r.eng._selling


@pytest.mark.asyncio
async def test_f07_fallback_place_order_transport_error_becomes_unknown_kept_selling(monkeypatch, caplog):
    """🔄 cycle428(F-422-1) — 폴백 `place_order` 의 비-`KisApiError` 예외는 더 이상 `execute_sell`
    밖으로 전파되지 않는다. `_handle_sell_market_disallowed` 의 새 `except Exception` 이 받아
    `SellFallbackOutcome.UNKNOWN` 을 돌려주고, 호출부는 `return` 한다(재발사 0).

    결과: `_selling`·`_selling_since` 는 유지된다(해제는 180초 확인 조회 또는 15분
    `selling_reconcile` 이 한다) — 예외는 올라오지 않고 `risk.on_tick` 의 그 틱은 끊기지 않는다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE)
    r = _build(monkeypatch)
    r.place.side_effect = [_disallowed(), httpx.ReadTimeout("read timed out")]
    await _sell(r)  # 예외 없이 반환

    assert r.place.await_count == 2
    assert _T in r.eng._selling, "UNKNOWN 은 `_selling` 을 유지한다 — 해제하면 stale 좀비 위험"
    assert _T in r.eng._selling_since
    assert r.insert.await_count == 0, "주문번호가 없으니 PENDING 은 쓰지 않는다"
    assert len(r.eng._order_qty) == 0, "매핑도 쓰지 않는다"
    r.ttl.assert_not_called(), "TTL·포기 래치는 거부의 증거가 있을 때만"
    assert r.pending == set(), "익일청산 큐도 등록하지 않는다"
    assert r.write_log.await_count == 0
    assert r.aio.sleeps == [], "재시도·backoff 0"
    assert r.strat.state.positions[_T].quantity == _QTY
    err = _recs(caplog, logging.ERROR, "[sell_send_unknown] ")
    assert len(err) == 1
    assert err[0] == (
        f"[sell_send_unknown] ticker={_T} strategy={_SID} path=fallback exc=ReadTimeout"
    )


# ---------------------------------------------------------------------------
# N — 폴백 접수 **뒤** 실패(1단계 tester 관문 N2·N3·N4 재현) — 재발사·오귀인 금지
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc, nxt",
    [
        (RuntimeError("DB 드라이버 내부 오류"), False),                       # N2
        (KisApiError("1", "EGW00201", "초당 거래건수를 초과하였습니다."), False),  # N3
        (KisApiError("1", "EGW00201", "초당 거래건수를 초과하였습니다."), True),   # N4
    ],
    ids=["N2_runtime", "N3_kisapi", "N4_kisapi_nxt"],
)
async def test_n_fallback_post_send_error_is_absorbed_not_reported_as_rejection(monkeypatch, caplog, exc, nxt):
    """폴백 주문이 접수된 뒤 PENDING 영속화가 실패해도 — 전파 0 · 재발사 0 · `_selling` 유지 ·
    「폴백 모두 거부」 오기록 0 · 익일청산 오등록 0 · `[sell_post_send_error] path=fallback` ERROR 1행.

    경계(`_persist_sell_pending_after_send` 의 `except Exception`)가 폴백 호출부에서 빠지면
    N2 = 전파(`risk.on_tick` 사망) · N3·N4 = 형제 `except KisApiError as fb_err` 가 받아
    접수된 주문을 「거부」로 적고 `_selling` 을 풀고 (N4) 익일 09:00 에 또 판다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE)
    r = _build(monkeypatch)
    r.nxt = nxt
    r.insert.side_effect = exc
    r.place.side_effect = [_disallowed(), _ok("FB-N")]
    await _sell(r)  # 전파 없음

    assert r.place.await_count == 2
    assert _T in r.eng._selling
    assert r.pending == set()
    assert r.eng._order_qty["FB-N"] == _QTY
    err = _recs(caplog, logging.ERROR, "[sell_post_send_error] ")
    assert len(err) == 1
    assert err[0].startswith(f"[sell_post_send_error] ticker={_T} order_no=FB-N strategy={_SID} path=fallback")
    assert _recs(caplog, logging.ERROR, "매도 지정가 폴백도 거부") == []
    assert all("모두 거부" not in c.args[1] for c in r.write_log.await_args_list)
    assert r.ttl.call_count == 1
    assert r.ttl.call_args.kwargs["fallback_succeeded"] is True
    assert r.aio.sleeps == []
    assert _recs(caplog, logging.CRITICAL) == []
    assert r.strat.state.positions[_T].quantity == _QTY


# ===========================================================================
# A — ⑰ 폴백 블록 · KRX 애프터마켓(primary = 44/41, 구조적 폴백)
# ===========================================================================
@pytest.mark.asyncio
async def test_a01_after_44_rejected_falls_back_to_41_with_etp_observe_and_markers(monkeypatch, caplog):
    """애프터 1차(44) 거부 → ETP 관측 등록 · `[after_exit_rejected]` · 41 지정가 폴백 · 매핑 `41` ·
    `[after_exit_division] div=41` · TTL(성공) · return. 분류는 폴백 게이트에 쓰이지 않는다(미분류도 폴백)."""
    caplog.set_level(logging.DEBUG, logger=_OE)
    with freeze_time(_F_1605):
        r = _build(monkeypatch, production=True, patch_nxt=False)
        _pin_boards(monkeypatch)
        r.place.side_effect = [_after_unclassified(), _ok("FB-41")]
        await _sell(r)
        await asyncio.sleep(0)

    first, second = r.place.await_args_list
    assert first.kwargs["order_division"] is OrderDivision.KRX_AFTER_BEST and first.kwargs["price"] == 0
    assert second.kwargs == {
        "ticker": _T, "side": OrderSide.SELL, "quantity": _QTY, "price": _FB,
        "order_division": OrderDivision.KRX_AFTER_LIMIT, "exchange": "KRX",
    }
    assert r.mapped_at_insert["division"] == "41"
    r.etp.assert_called_once_with(_T)
    assert _recs(caplog, logging.INFO, "[after_exit_rejected] ") == [
        f"[after_exit_rejected] ticker={_T} div=44 msg_cd=APBK9999 classified=unclassified "
        f"ttl_registered=1 msg1=주문구분코드 오류입니다."
    ]
    div = _recs(caplog, logging.INFO, "[after_exit_division] ")
    assert div == [
        f"[after_exit_division] ticker={_T} div=44 unpr=0 cur={_CUR} exchange=KRX dial=44",
        f"[after_exit_division] ticker={_T} div=41 unpr={_FB} cur={_CUR} exchange=KRX dial=44",
    ]
    assert r.ttl.call_args.kwargs == {"is_nxt_session": True, "fallback_succeeded": True}
    r.bump.assert_not_called()
    assert _T in r.eng._selling
    assert r.pending == set()
    assert r.aio.sleeps == []


@pytest.mark.asyncio
async def test_a01b_after_dial_41_falls_back_to_41_again(monkeypatch, caplog):
    """dial 41 — primary=fallback=41. 1차 41 거부 → 같은 41 을 같은 가격으로 1회."""
    with freeze_time(_F_1605):
        r = _build(monkeypatch, production=True, patch_nxt=False, after_market_exit_division="41")
        _pin_boards(monkeypatch)
        r.place.side_effect = [_after_unclassified(), _ok("FB-41b")]
        await _sell(r)
        await asyncio.sleep(0)

    first, second = r.place.await_args_list
    for c in (first, second):
        assert c.kwargs["order_division"] is OrderDivision.KRX_AFTER_LIMIT
        assert c.kwargs["price"] == _FB
    assert r.eng._order_division["FB-41b"] == "41"


@pytest.mark.asyncio
async def test_a02_after_fallback_rejected_queues_next_day_then_bumps_giveup(monkeypatch, caplog):
    """애프터 41 폴백도 거부 → `[after_exit_rejected] div=41` · TTL(실패) · NXT 시간대 익일청산 ·
    포기 래치 카운트 1 · `_selling` 해제 · return."""
    caplog.set_level(logging.DEBUG, logger=_OE)
    with freeze_time(_F_1605):
        r = _build(monkeypatch, production=True, patch_nxt=False)
        _pin_boards(monkeypatch)
        r.place.side_effect = [_after_unclassified(), _after_unclassified("호가 가격 오류입니다.")]
        await _sell(r)
        await asyncio.sleep(0)

    assert r.place.await_count == 2
    rej = _recs(caplog, logging.INFO, "[after_exit_rejected] ")
    assert rej[-1] == (
        f"[after_exit_rejected] ticker={_T} div=41 msg_cd=APBK9999 classified=unclassified "
        f"ttl_registered=1 msg1=호가 가격 오류입니다."
    )
    assert r.ttl.call_args.kwargs == {"is_nxt_session": True, "fallback_succeeded": False}
    assert r.pending == {(_T, _SID)}
    assert r.bump.call_count == 1
    assert r.bump.call_args.args[:2] == (_T, _SID)
    assert r.eng._after_exit_fails[(_T, _AFTER_DAY)] == 1
    assert r.events[-3:] == ["ttl", "write_log:WARNING", "bump"]  # 포기 래치는 TTL·익일청산 **뒤**
    assert _T not in r.eng._selling
    assert r.aio.sleeps == []


@pytest.mark.asyncio
async def test_a02b_giveup_latch_overrides_30s_ttl_because_it_runs_after(monkeypatch, caplog):
    """포기 래치(5회째) — 30초 TTL 등록 **뒤**에서 덮어써야 다음 09:00 래치가 이긴다(K9 봉인②)."""
    with freeze_time(_F_1605):
        r = _build(monkeypatch, production=True, patch_nxt=False)
        _pin_boards(monkeypatch)
        r.eng._after_exit_fails[(_T, _AFTER_DAY)] = 4
        r.place.side_effect = [_after_unclassified(), _after_unclassified()]
        await _sell(r)
        await asyncio.sleep(0)

    assert r.eng._after_exit_fails[(_T, _AFTER_DAY)] == 5
    assert r.eng._sell_rejection._blocked_reason[_T] == "market_closed"
    assert _recs(caplog, logging.CRITICAL, "[after_exit_giveup] ") == [
        f"[after_exit_giveup] ticker={_T} fails=5 next_day_clear=1"
    ]
    assert r.pending == {(_T, _SID)}


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl_ok", [True, False], ids=["ttl_registered", "ttl_failed"])
async def test_a03_after_no_current_price_registers_ttl_bumps_and_retries(monkeypatch, caplog, ttl_ok):
    """애프터 + 현재가 미확보 — 폴백은 못 하지만 봉인①(TTL)·봉인②(포기 래치)는 매 회차 적용,
    `ttl_registered=` 는 실제 등록 결과. 그 뒤 일반 재시도(backoff) → ⑲ CRITICAL."""
    caplog.set_level(logging.DEBUG, logger=_OE)
    with freeze_time(_F_1605):
        r = _build(monkeypatch, production=True, patch_nxt=False, prices={})
        _pin_boards(monkeypatch)
        if not ttl_ok:
            r.ttl.side_effect = RuntimeError("tracker down")
        errs = [_after_unclassified(), _after_unclassified(), _after_unclassified()]
        r.place.side_effect = errs
        await _sell(r)
        await asyncio.sleep(0)

    assert r.place.await_count == SELL_MAX_RETRIES
    for c in r.place.await_args_list:
        assert c.kwargs["order_division"] is OrderDivision.KRX_AFTER_BEST and c.kwargs["price"] == 0
    assert r.etp.call_count == SELL_MAX_RETRIES
    assert r.ttl.call_count == SELL_MAX_RETRIES
    for c in r.ttl.call_args_list:
        assert c.kwargs == {"is_nxt_session": True, "fallback_succeeded": False}
    assert r.bump.call_count == SELL_MAX_RETRIES
    no_price = _recs(caplog, logging.INFO, "[after_exit_rejected] ")
    no_price = [m for m in no_price if m.endswith("msg1=no_price_for_fallback")]
    assert no_price == [
        f"[after_exit_rejected] ticker={_T} div=44 msg_cd=APBK9999 classified=unclassified "
        f"ttl_registered={int(ttl_ok)} msg1=no_price_for_fallback"
    ] * SELL_MAX_RETRIES
    assert r.aio.sleeps == [SELL_RETRY_DELAY, SELL_RETRY_DELAY * 2]
    _assert_final_critical(r, caplog, errs[-1])
    assert _T not in r.eng._selling
    assert r.eng._after_exit_fails[(_T, _AFTER_DAY)] == SELL_MAX_RETRIES


@pytest.mark.asyncio
async def test_a04_etp_observe_task_registration_failure_does_not_block_fallback(monkeypatch, caplog):
    """ETP 관측 태스크 등록 실패(이벤트 루프 없음) — DEBUG 흔적만, 41 폴백은 그대로 나간다."""
    caplog.set_level(logging.DEBUG, logger=_OE)
    with freeze_time(_F_1605):
        r = _build(monkeypatch, production=True, patch_nxt=False)
        _pin_boards(monkeypatch)
        r.aio.create_task_fails = True
        r.place.side_effect = [_after_unclassified(), _ok("FB-41c")]
        await _sell(r)

    assert _recs(caplog, logging.DEBUG, "[after_etp_exit_observe] task 등록 실패") == [
        "[after_etp_exit_observe] task 등록 실패 — 이벤트 루프 없음"
    ]
    assert r.place.await_count == 2
    assert r.place.await_args_list[1].kwargs["order_division"] is OrderDivision.KRX_AFTER_LIMIT
    assert len(_recs(caplog, logging.INFO, "[after_exit_rejected] ")) == 1


# ===========================================================================
# P — ⑲ 마지막 실패 뒤처리
# ===========================================================================
@pytest.mark.asyncio
async def test_p01_insufficient_cleanup_order_and_effects(monkeypatch, caplog):
    """cycle429(D1 안A, 사용자 승인 2026-10-10) 재조준 — 자동 삭제 경로 폐지.

    수량 부족(APBK1234, 설명 안 됨 — `get_daily_orders` 기본 `[]`) → `_selling`·
    `_selling_locked_wait` 해제 → 5분 진입 차단 등록 → 잔고 1회 관측 조회 →
    `[sell_insufficient_unexplained]` ERROR 1행 → return(CRITICAL 없음, 삭제 없음).
    """
    caplog.set_level(logging.DEBUG, logger=_OE)
    r = _build(monkeypatch)
    r.place.side_effect = [_insufficient()]
    await _sell(r)

    assert r.place.await_count == 1  # 통합 판정 위임 — 재시도 없음
    assert r.aio.sleeps == []
    assert _T in r.strat.state.positions  # D1 안A — 자동 삭제 없음
    r.on_closed.assert_not_called()
    r.delete_position.assert_not_awaited()
    assert r.write_log.await_count == 1
    lvl, msg = r.write_log.await_args.args[:2]
    assert lvl == "ERROR"
    assert msg.startswith("[sell_insufficient_unexplained] ")
    assert f"ticker={_T}" in msg and f"strategy={_SID}" in msg and "held=0" in msg
    assert r.events == ["place", "get_balance", "write_log:ERROR"]
    assert _recs(caplog, logging.CRITICAL) == []
    assert _T not in r.eng._selling
    assert _T not in r.eng._selling_locked_wait
    assert _T in r.eng._sell_rejection._blocked_until


@pytest.mark.asyncio
async def test_p02_on_position_closed_is_never_called_for_insufficient(monkeypatch, caplog):
    """cycle429(D1 안A) 재조준 — 포지션을 보존하므로 `on_position_closed` 훅을 안 부른다."""
    r = _build(monkeypatch)
    r.on_closed.side_effect = ValueError("boom")
    r.place.side_effect = [_insufficient()]
    await _sell(r)  # on_closed 가 raise 해도 호출 자체가 없어 전파되지 않는다

    r.on_closed.assert_not_called()
    r.delete_position.assert_not_awaited()
    assert r.events == ["place", "get_balance", "write_log:ERROR"]


@pytest.mark.asyncio
async def test_p03_delete_position_is_never_called_for_insufficient(monkeypatch, caplog):
    """cycle429(D1 안A) 재조준 — DB `delete_position` 자체가 호출되지 않는다."""
    r = _build(monkeypatch)
    r.delete_position.side_effect = OSError("db down")
    r.place.side_effect = [_insufficient()]
    await _sell(r)  # delete_position 이 raise 해도 호출 자체가 없어 전파되지 않는다

    r.delete_position.assert_not_awaited()
    assert _T in r.strat.state.positions
    assert r.events == ["place", "get_balance", "write_log:ERROR"]
    assert _recs(caplog, logging.CRITICAL) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("actual", [3, 0], ids=["residual_3", "residual_0"])
async def test_p04_held_value_is_observational_only_in_unexplained_message(monkeypatch, caplog, actual):
    """cycle429(D1 안A) 재조준 — 잔고 조회값은 판정에 안 쓰이고 `held=` 로만 로그에 남는다.

    옛 `[positions_reconciliation] 실제 잔량 확인` 조건부 로그는 사라졌다 — 단일
    ERROR 메시지의 `held=` 필드가 항상(0 이든 양수든) 실린다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE)
    r = _build(monkeypatch)
    r.get_balance.return_value = ([SimpleNamespace(ticker=_T, quantity=actual)], None)
    r.place.side_effect = [_insufficient()]
    await _sell(r)

    lvl, msg = r.write_log.await_args.args[:2]
    assert lvl == "ERROR"
    assert f"held={actual}" in msg
    assert _T in r.strat.state.positions  # D1 안A — 잔량과 무관하게 보존


@pytest.mark.asyncio
async def test_p05_reconciliation_balance_failure_is_swallowed(monkeypatch, caplog):
    """cycle429(D1 안A) 재조준 — 관측 조회 실패는 `held=?` 로 흡수된다(전파 없음)."""
    caplog.set_level(logging.DEBUG, logger=_OE)
    r = _build(monkeypatch)
    r.get_balance.side_effect = RuntimeError("KIS down")
    r.place.side_effect = [_insufficient()]
    await _sell(r)  # 전파 없음

    lvl, msg = r.write_log.await_args.args[:2]
    assert lvl == "ERROR"
    assert "held=?" in msg
    assert _recs(caplog, logging.CRITICAL) == []


@pytest.mark.asyncio
async def test_p06_generic_failure_becomes_unknown_single_attempt_keeps_selling(monkeypatch, caplog):
    """🔄 cycle428(F-422-1, 항목 5) — 1차 주문의 비-`KisApiError` 예외는 더 이상 3회
    재시도 + CRITICAL 로 끝나지 않는다. 결과 모름(UNKNOWN) — 발사 1회 · backoff 0 ·
    `_selling` 유지 · ERROR `[sell_send_unknown] path=primary` · 포지션 보존 ·
    잔고부족 정리 경로 미진입."""
    caplog.set_level(logging.DEBUG, logger=_OE)
    r = _build(monkeypatch)
    errs = [RuntimeError("하나"), RuntimeError("둘"), RuntimeError("셋")]
    r.place.side_effect = errs
    await _sell(r, Signal.TRAILING_STOP)

    assert r.place.await_count == 1, "결과 모름은 재발사하지 않는다 — 발사 1회뿐"
    assert r.aio.sleeps == [], "backoff 없이 즉시 멈춘다"
    assert _recs(caplog, logging.CRITICAL) == []
    err = _recs(caplog, logging.ERROR, "[sell_send_unknown] ")
    assert err == [
        f"[sell_send_unknown] ticker={_T} strategy={_SID} path=primary exc=RuntimeError"
    ]
    assert _T in r.eng._selling, "`_selling` 은 유지한다 — 해제는 확인 조회·15분 재대조 몫"
    assert _T in r.eng._selling_since
    assert r.strat.state.positions[_T].quantity == _QTY
    r.delete_position.assert_not_awaited()
    r.on_closed.assert_not_called()
    assert r.write_log.await_count == 0


# ===========================================================================
# G — B4-4 대비: `test_cycle236` 이 빠뜨린 APBK0400 분기의 `_selling` · 흐름 핀
# ===========================================================================
def _holding(qty: int, sellable: int):
    return ([SimpleNamespace(ticker=_T, quantity=qty, sellable_quantity=sellable)], SimpleNamespace(net_asset=0))


@pytest.mark.asyncio
async def test_g1_qty_exceeded_balance_unavailable_falls_to_plain_retry_and_releases(monkeypatch, caplog):
    """분기 ①(재대조 불가) — 일반 재시도 3회(backoff) → ⑲ CRITICAL · `_selling` 해제 · 보존."""
    r = _build(monkeypatch)
    r.get_balance.side_effect = RuntimeError("KIS down")
    r.place.side_effect = [_qty_exceeded()] * SELL_MAX_RETRIES
    await _sell(r)

    assert r.place.await_count == SELL_MAX_RETRIES
    assert r.aio.sleeps == [SELL_RETRY_DELAY, SELL_RETRY_DELAY * 2]
    assert _T not in r.eng._selling
    assert _T not in r.eng._selling_locked_wait
    assert r.strat.state.positions[_T].quantity == _QTY
    assert len(_recs(caplog, logging.CRITICAL)) == 1


@pytest.mark.asyncio
async def test_g2_qty_exceeded_zero_holding_breaks_into_cleanup_and_releases(monkeypatch, caplog):
    """분기 ④(실보유 0) → cycle429(D1 안A) 재조준 — 통합 판정 위임(재시도·backoff 0) →
    보존 + `_selling` 해제 + 5분 진입 차단 · CRITICAL 없음(자동 삭제 없음)."""
    r = _build(monkeypatch)
    r.get_balance.return_value = ([], SimpleNamespace(net_asset=0))
    r.place.side_effect = [_qty_exceeded()]
    await _sell(r)

    assert r.place.await_count == 1
    assert r.aio.sleeps == []
    assert _T not in r.eng._selling
    assert _T in r.strat.state.positions  # D1 안A — 자동 삭제 없음
    r.delete_position.assert_not_awaited()
    assert _recs(caplog, logging.CRITICAL) == []
    assert _T in r.eng._sell_rejection._blocked_until
    # 이 경로는 외부(`is_sell_qty_exceeded`) 재대조용 get_balance 1회 +
    # 통합 판정 내부 관측용 1회 = 총 2회.
    assert r.events.count("get_balance") == 2


@pytest.mark.asyncio
async def test_g3_qty_exceeded_anomaly_sellable_covers_position_then_plain_retry(monkeypatch, caplog):
    """분기 ⑤(이상 — sellable ≥ 추적) — 보정 없이 일반 재시도 지속 · 매 회차 재대조 · 끝에 해제.
    (`test_cycle236` 에 이 분기 테스트가 없다.)"""
    r = _build(monkeypatch)
    r.get_balance.return_value = _holding(_QTY, _QTY)
    r.place.side_effect = [_qty_exceeded()] * SELL_MAX_RETRIES
    await _sell(r)

    assert [c.kwargs["quantity"] for c in r.place.await_args_list] == [_QTY] * SELL_MAX_RETRIES
    assert r.get_balance.await_count == SELL_MAX_RETRIES
    warn = _recs(caplog, logging.WARNING, "[sell_qty_exceeded] ")
    assert warn == [
        f"[sell_qty_exceeded] ticker={_T} sellable={_QTY} >= positions={_QTY} 인데 APBK0400 — 이상 상태, 일반 재시도 지속"
    ] * SELL_MAX_RETRIES
    assert r.aio.sleeps == [SELL_RETRY_DELAY, SELL_RETRY_DELAY * 2]
    r.save_position.assert_not_awaited()
    assert r.strat.state.positions[_T].quantity == _QTY
    assert _T not in r.eng._selling
    assert _T not in r.eng._selling_locked_wait
    assert len(_recs(caplog, logging.CRITICAL)) == 1


@pytest.mark.asyncio
async def test_g4_qty_exceeded_contamination_reconciles_continues_without_backoff_and_keeps_selling(monkeypatch):
    """분기 ②-재대조(오염 held<추적) — `continue`(backoff 0) → 보정 수량 재발사 성공 → `_selling` 유지."""
    r = _build(monkeypatch)
    r.get_balance.return_value = _holding(7, 7)
    r.place.side_effect = [_qty_exceeded(), _ok("S-7")]
    await _sell(r)

    assert [c.kwargs["quantity"] for c in r.place.await_args_list] == [_QTY, 7]
    assert r.aio.sleeps == []
    assert r.strat.state.positions[_T].quantity == 7
    assert _T in r.eng._selling
    assert _T not in r.eng._selling_locked_wait


@pytest.mark.asyncio
async def test_g5_qty_exceeded_partial_lock_holds_without_order_and_freezes(monkeypatch, caplog):
    """분기 ②-보류(걸린 매도를 운영자 몫이 덮음) — return(발사 1회) · `_selling` 유지 + 동결 표식 · backoff 0."""
    r = _build(monkeypatch)
    r.get_balance.return_value = _holding(15, 2)  # surplus 5 > sellable 2 → fire < 1
    r.place.side_effect = [_qty_exceeded()]
    await _sell(r)

    assert r.place.await_count == 1
    assert r.aio.sleeps == []
    assert _T in r.eng._selling
    assert _T in r.eng._selling_locked_wait
    assert len(_recs(caplog, logging.WARNING, "[sell_qty_partial_locked] ")) == 1
    assert _recs(caplog, logging.CRITICAL) == []
