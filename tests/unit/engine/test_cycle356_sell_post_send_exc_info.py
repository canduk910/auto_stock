"""cycle356 — 매도 축 `[sell_post_send_error]` 는 traceback 을 싣는다.

## 닫는 구멍

cycle335 가 매수 축(`test_cycle335_buy_post_send_boundary.py` 의 `rec.exc_info is not None`)
을 닫으면서 "매도 축에도 같은 구멍" 이라고 남겼다. 매도 마커를 보는 기존 테스트
(`test_cycle327_sell_fill_during_insert.py::test_sell_does_not_refire_on_generic_insert_error`
· `test_order_engine_sell_fallback.py` 시나리오 I)는 **마커 문자열의 존재**만 본다.

`_persist_sell_pending_after_send` 의 `logger.exception` 이 `logger.error` 로 바뀌면
레벨(ERROR)도 메시지도 같고 **traceback 만 사라진다** — 그 테스트들은 전부 초록이다.
그런데 이 마커의 판독 절차(「하루 몇 건이면 RDS 가 아픈 것인가」)는 예외의 정체
(타임아웃인가·풀 고갈인가·UNIQUE 인가)가 있어야 성립하고, 그것을 나르는 수단은
`exc_info` 하나뿐이다.

## 판별력

- 주입 예외는 이 파일 전용 클래스 `_PostSendDbFailure` 라, traceback 에 그 이름이
  보이면 **이 주입이** 실렸다는 뜻이다(다른 경로의 예외와 섞이지 않는다).
- 돌연변이 `logger.exception` → `logger.error` 는 `exc_info is None` 으로 붉다.
- `logger.error(..., exc_info=True)` 는 traceback 이 보존되므로 초록이 맞다 —
  이 파일이 봉인하는 것은 함수 이름이 아니라 **traceback 이 실린다**는 사실이다.

주 경로·폴백 경로 둘 다 같은 래퍼를 지나지만, 매수 축(cycle335 6번)과 대칭으로
두 호출부를 모두 밟는다.
"""
from __future__ import annotations

import logging

import pytest

from src.api.base import KisApiError
from src.engine.strategy_base import Signal
from src.models.order import OrderResult

from tests.unit.engine.test_cycle327_sell_fill_during_insert import (
    PRICE,
    TICKER,
    _make_sell_env,
    _seed_position,
)

pytestmark = pytest.mark.unit

MARKER = "[sell_post_send_error]"
SENTINEL_MSG = "cycle356 주입 — RDS failover, 주문은 이미 나갔다"


class _PostSendDbFailure(Exception):
    """접수 후 PENDING INSERT 실패를 흉내 내는 이 파일 전용 예외."""


def _marker_records(caplog) -> list[logging.LogRecord]:
    """WARNING 이상 + 접두 토큰으로 한정(cycle252 T2 — CI 루트 로거는 DEBUG)."""
    return [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(MARKER)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["market", "fallback"])
async def test_sell_post_send_error_when_insert_fails_then_record_carries_traceback(
    monkeypatch, caplog, path,
):
    """🔴 접수 후 INSERT 실패의 마커는 ERROR 1행이고 **원 예외의 traceback 을 싣는다**."""
    env = _make_sell_env(monkeypatch)
    _seed_position(env.strategy)

    async def failing_insert(record):
        raise _PostSendDbFailure(SENTINEL_MSG)

    monkeypatch.setattr("src.engine.order_engine.insert_trade", failing_insert)

    if path == "fallback":
        from src.engine import scanner as _scanner

        # 폴백 가격 산출에는 dict 형식 현재가가 필요하다(cycle327 픽스처 기본은 정수).
        monkeypatch.setattr(_scanner, "ticker_prices",
                            {TICKER: {"current_price": PRICE}}, raising=False)
        calls = {"n": 0}

        async def market_rejected_then_fallback(ticker, side, quantity, price=0, **kwargs):
            calls["n"] += 1
            env.calls.place_order.append({"side": side, "quantity": quantity})
            if calls["n"] == 1:
                raise KisApiError(rt_cd="1", msg_cd="APBK1943",
                                  msg1="시장가호가불가로 주문이 불가합니다.")
            return OrderResult(order_no="SELL-FB-1", order_time="090501",
                               krx_org_no="00950")

        monkeypatch.setattr("src.engine.order_engine.place_order",
                            market_rejected_then_fallback)

    caplog.set_level(logging.INFO, logger="src.engine.order_engine")

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "momentum")

    recs = _marker_records(caplog)
    assert len(recs) == 1, f"마커가 {len(recs)}행: {[r.getMessage() for r in recs]}"
    rec = recs[0]
    assert f"path={path}" in rec.getMessage(), (
        f"다른 경로의 마커다(기대 path={path}): {rec.getMessage()}"
    )
    assert rec.levelno == logging.ERROR, (
        f"마커 레벨이 {rec.levelname} — ERROR 여야 한다(무cap ERROR 관측 채널)"
    )

    assert rec.exc_info is not None, (
        "`logger.exception` 이 아니라 `logger.error` 다 — traceback 이 사라져 "
        "「RDS 가 아픈 것인가」(타임아웃·풀 고갈·UNIQUE)를 판정할 근거가 없어진다"
    )
    trace = logging.Formatter().formatException(rec.exc_info)
    assert _PostSendDbFailure.__name__ in trace and SENTINEL_MSG in trace, (
        "traceback 에 주입한 원 예외가 없다 — 엉뚱한 예외가 실렸거나 원인이 잘렸다.\n"
        f"{trace}"
    )
