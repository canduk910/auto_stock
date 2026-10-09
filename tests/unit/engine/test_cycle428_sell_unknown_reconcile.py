"""cycle428(F-422-1) — 매도 결과 모름(UNKNOWN) 단일 종목 확인 조회.

두 층을 나눠 잰다:

1. `selling_reconcile.reconcile_selling_unknown_one` 자체(leaf 단위) — S2~S5
   (closed/open_order/not_accepted/lookup_failed) 판정이 15분 재대조와 같은
   규칙(`_stale_selling_verdict`)을 쓰는지.
2. `OrderEngine._schedule_sell_unknown_reconcile` 가 UNKNOWN 이 나올 때마다
   정확한 (ticker, strategy_id) 로 예약되는지(스파이, 실제 180초 대기는 타지
   않는다) + 예약된 콜을 직접 실행했을 때 끝까지 이어지는 통합 확인 1건.

시나리오 번호는 `_workspace/domain_consult/2026-10-10_f422_1_fallback_network_error.md`
「회귀 시나리오」 S2·S3·S4·S5 를 따른다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.order_engine import SELL_UNKNOWN_RECONCILE_DELAY_S, OrderEngine
from src.engine.selling_reconcile import reconcile_selling_unknown_one

from tests.unit.engine.test_cycle422_sell_fallback_net import (
    _QTY,
    _SID,
    _T,
    _build,
    _sell,
)

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_NOW = datetime(2026, 10, 10, 10, 33, 0, tzinfo=_KST)


def _recs(caplog, level: int, prefix: str) -> list[str]:
    """WARNING 이상 + 접두 — `selling_reconcile.py` 는 `src.engine.scheduler` 로거를
    쓴다(system_logs grep 연속성 영속, `_OE` 로 좁힌 상위 `_recs` 와 다르다)."""
    return [
        r.getMessage() for r in caplog.records
        if r.levelno == level and r.getMessage().startswith(prefix)
    ]


def _engine(selling_since: datetime | None = None) -> SimpleNamespace:
    eng = SimpleNamespace()
    eng._selling = {_T}
    eng._selling_since = {}
    if selling_since is not None:
        eng._selling_since[_T] = selling_since
    return eng


def _open_sell(ticker: str = _T, rmn: int = 3) -> dict:
    return {"pdno": ticker, "sll_buy_dvsn_cd": "01", "rmn_qty": str(rmn)}


# ===========================================================================
# leaf 단위 — reconcile_selling_unknown_one
# ===========================================================================
@pytest.mark.asyncio
async def test_s2_held_zero_keeps_selling_and_returns_closed(monkeypatch, caplog):
    """S2 — 보유 0(이미 팔렸다고 볼 근거) → 유지(`closed`), `_selling` 그대로."""
    caplog.set_level(logging.DEBUG, logger="src.engine.scheduler")
    import src.api.balance as _balance

    monkeypatch.setattr(_balance, "get_balance", AsyncMock(return_value=([], SimpleNamespace(net_asset=0))))
    monkeypatch.setattr(_balance, "get_daily_orders", AsyncMock(return_value=[]))
    eng = _engine(selling_since=_NOW - timedelta(seconds=SELL_UNKNOWN_RECONCILE_DELAY_S))

    result = await reconcile_selling_unknown_one(
        eng, _T, _SID, min_age_s=SELL_UNKNOWN_RECONCILE_DELAY_S, now=_NOW,
    )

    assert result == "closed"
    assert _T in eng._selling, "보유 0 은 유지 — 15분 sync 가 포지션을 정리한다"
    rows = _recs(caplog, logging.WARNING, "[sell_send_unknown_resolved] ")
    assert rows == [f"[sell_send_unknown_resolved] ticker={_T} strategy={_SID} result=closed"]


@pytest.mark.asyncio
async def test_s3_open_order_keeps_selling_and_returns_open_order(monkeypatch, caplog):
    """S3 — 열린 매도주문이 그 종목에 있다 → 유지(`open_order`)."""
    import src.api.balance as _balance

    monkeypatch.setattr(
        _balance, "get_balance",
        AsyncMock(return_value=([SimpleNamespace(ticker=_T, quantity=_QTY)], SimpleNamespace(net_asset=0))),
    )
    monkeypatch.setattr(_balance, "get_daily_orders", AsyncMock(return_value=[_open_sell()]))
    eng = _engine(selling_since=_NOW - timedelta(seconds=SELL_UNKNOWN_RECONCILE_DELAY_S))

    result = await reconcile_selling_unknown_one(
        eng, _T, _SID, min_age_s=SELL_UNKNOWN_RECONCILE_DELAY_S, now=_NOW,
    )

    assert result == "open_order"
    assert _T in eng._selling


@pytest.mark.asyncio
async def test_s4_not_accepted_releases_selling(monkeypatch, caplog):
    """S4 — 보유>0 · 열린 주문 0 · 180초 경과 → 해제(`not_accepted`),
    다음 틱 손절이 새로 발사할 수 있게 `_selling`·`_selling_since` 를 비운다."""
    caplog.set_level(logging.DEBUG, logger="src.engine.scheduler")
    import src.api.balance as _balance

    monkeypatch.setattr(
        _balance, "get_balance",
        AsyncMock(return_value=([SimpleNamespace(ticker=_T, quantity=_QTY)], SimpleNamespace(net_asset=0))),
    )
    monkeypatch.setattr(_balance, "get_daily_orders", AsyncMock(return_value=[]))
    eng = _engine(selling_since=_NOW - timedelta(seconds=SELL_UNKNOWN_RECONCILE_DELAY_S))

    result = await reconcile_selling_unknown_one(
        eng, _T, _SID, min_age_s=SELL_UNKNOWN_RECONCILE_DELAY_S, now=_NOW,
    )

    assert result == "not_accepted"
    assert _T not in eng._selling, "접수 안 됨 — 해제해야 다음 틱이 손절을 새로 낸다"
    assert _T not in eng._selling_since
    rows = _recs(caplog, logging.WARNING, "[sell_send_unknown_resolved] ")
    assert rows == [f"[sell_send_unknown_resolved] ticker={_T} strategy={_SID} result=not_accepted"]


@pytest.mark.asyncio
async def test_s5_lookup_failure_defaults_to_kept(monkeypatch, caplog):
    """S5 — 확인 조회 자체가 실패 → 기본값 = 유지(`lookup_failed`), 15분
    `reconcile_stale_selling` 에 넘긴다(재발사보다 지연이 낫다)."""
    caplog.set_level(logging.DEBUG, logger="src.engine.scheduler")
    import src.api.balance as _balance

    monkeypatch.setattr(_balance, "get_balance", AsyncMock(side_effect=RuntimeError("KIS down")))
    monkeypatch.setattr(_balance, "get_daily_orders", AsyncMock(return_value=[]))
    eng = _engine(selling_since=_NOW - timedelta(seconds=SELL_UNKNOWN_RECONCILE_DELAY_S))

    result = await reconcile_selling_unknown_one(
        eng, _T, _SID, min_age_s=SELL_UNKNOWN_RECONCILE_DELAY_S, now=_NOW,
    )

    assert result == "lookup_failed"
    assert _T in eng._selling, "조회 실패의 기본값 = 유지"
    rows = _recs(caplog, logging.WARNING, "[sell_send_unknown_resolved] ")
    assert rows == [f"[sell_send_unknown_resolved] ticker={_T} strategy={_SID} result=lookup_failed"]


@pytest.mark.asyncio
async def test_too_young_degenerate_case_keeps_selling(monkeypatch):
    """대조 — 아직 180초가 안 지났으면(이례적) 유지(`too_young`), 해제하지 않는다."""
    import src.api.balance as _balance

    monkeypatch.setattr(
        _balance, "get_balance",
        AsyncMock(return_value=([SimpleNamespace(ticker=_T, quantity=_QTY)], SimpleNamespace(net_asset=0))),
    )
    monkeypatch.setattr(_balance, "get_daily_orders", AsyncMock(return_value=[]))
    eng = _engine(selling_since=_NOW - timedelta(seconds=5))

    result = await reconcile_selling_unknown_one(
        eng, _T, _SID, min_age_s=SELL_UNKNOWN_RECONCILE_DELAY_S, now=_NOW,
    )

    assert result == "too_young"
    assert _T in eng._selling


# ===========================================================================
# OrderEngine 배선 — 예약 스파이 + 통합 확인 1건
# ===========================================================================
@pytest.mark.asyncio
async def test_primary_unknown_schedules_reconcile_with_correct_args(monkeypatch):
    r = _build(monkeypatch)
    spy = MagicMock()
    monkeypatch.setattr(r.eng, "_schedule_sell_unknown_reconcile", spy)
    r.place.side_effect = [RuntimeError("전송 오류")]

    await _sell(r)

    spy.assert_called_once_with(_T, _SID)


@pytest.mark.asyncio
async def test_fallback_unknown_schedules_reconcile_with_correct_args(monkeypatch):
    from tests.unit.engine.test_cycle422_sell_fallback_net import _disallowed
    import httpx

    r = _build(monkeypatch)
    spy = MagicMock()
    monkeypatch.setattr(r.eng, "_schedule_sell_unknown_reconcile", spy)
    r.place.side_effect = [_disallowed(), httpx.ReadTimeout("read timed out")]

    await _sell(r)

    spy.assert_called_once_with(_T, _SID)


@pytest.mark.asyncio
async def test_end_to_end_unknown_schedules_task_that_calls_the_leaf(monkeypatch):
    """통합 — UNKNOWN 뒤 예약된 task 가 실제로 돌면 leaf 를 그 종목·전략으로 부른다.

    harness 의 `asyncio` 패치(즉시 반환 sleep) 때문에 `_selling_since` 와 확인
    시각 사이의 실제 경과가 0 에 가까워 `too_young` 로 떨어진다(실제 운영은
    `asyncio.sleep(180)` 이 진짜 180초를 기다린다) — 그래서 최종 판정값을
    다시 재는 S2~S5 단위 테스트와 분리해, 이 테스트는 **배선**(예약된 task 가
    끝까지 돌아 leaf 를 올바른 인자로 부르는지)만 확인한다.
    """
    import asyncio as _real_asyncio

    from src.engine import selling_reconcile as _sr

    r = _build(monkeypatch)
    leaf_spy = AsyncMock(return_value="not_accepted")
    monkeypatch.setattr(_sr, "reconcile_selling_unknown_one", leaf_spy)
    r.place.side_effect = [RuntimeError("전송 오류")]

    await _sell(r)
    assert _T in r.eng._selling, "UNKNOWN 직후에는 아직 유지돼야 한다"

    await _real_asyncio.sleep(0)  # 예약된 확인 조회 task 를 한 턴 더 돌린다

    leaf_spy.assert_called_once()
    call = leaf_spy.await_args
    assert call.args[:3] == (r.eng, _T, _SID)
    assert call.kwargs["min_age_s"] == SELL_UNKNOWN_RECONCILE_DELAY_S
