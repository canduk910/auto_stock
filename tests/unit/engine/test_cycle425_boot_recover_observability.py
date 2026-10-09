"""cycle425 — boot_manager 복구 경로 관측 (리팩토링 카드 #11 ⑦ 관측).

행위 0 — 폴백 소유 전략 판정(`FALLBACK_OWNER_ID`)·`except Exception: pass` 4자리의
흡수는 그대로다(`test_cycle425_boot_fallback_owner.py` 가 핀). 이 테스트는 두 가지만
새로 확인한다:

1. `except Exception: pass` 4자리가 조용히 넘어가지 않고 WARNING 로그를 남긴다.
2. 출처를 모르는 주문·보유가 `FALLBACK_OWNER_ID` 로 떨어질 때
   `[boot_recover_strategy_unknown] path=kis_supplement|unfilled_order` WARNING +
   `system_logs` 기록이 생긴다 — 출처를 **아는** 경우에는 생기지 않는다.

caplog 단언은 WARNING 이상 + 마커 접두로 한정한다(DEBUG 잡음·무관 WARNING 과
혼동되지 않게, 2026-09-18 CI 교훈).

이 파일은 `test_cycle425_boot_fallback_owner.py` 의 더블(`_FakeRegistry` 등)을
재사용하되 자체 `_run_boot` 를 둔다 — 그 파일은 카드 #11 1단계의 **동결된**
현행 고정 테스트라 이후 사이클이 손대지 않는다(해당 파일 머리말).
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import boot_manager
from tests.unit.engine.test_cycle425_boot_fallback_owner import (
    _FakeRegistry,
    _FakeStrategy,
    _holding,
    _make_scheduler,
    _summary,
    _unfilled_order,
)

pytestmark = pytest.mark.unit


async def _run_boot(
    scheduler,
    *,
    holdings,
    db_positions,
    recent_buy_strategy_map,
    all_orders,
    today_buys_rows,
    recent_buy_strategy_side_effect=None,
    get_daily_orders_side_effect=None,
    mark_pending_buys_completed_side_effect=None,
    get_today_buys_ticker_strategy_side_effect=None,
    write_log_mock: AsyncMock | None = None,
) -> None:
    """`boot_manager.boot()` 을 돌리되, 복구 경로 각 호출에 예외를 주입할 수 있다."""

    async def _get_recent_buy_strategy(ticker):
        if recent_buy_strategy_side_effect is not None:
            return await recent_buy_strategy_side_effect(ticker)
        return recent_buy_strategy_map.get(ticker)

    get_daily_orders_kwargs = (
        {"side_effect": get_daily_orders_side_effect}
        if get_daily_orders_side_effect is not None
        else {"return_value": all_orders}
    )
    mark_pending_kwargs = (
        {"side_effect": mark_pending_buys_completed_side_effect}
        if mark_pending_buys_completed_side_effect is not None
        else {}
    )
    today_buys_kwargs = (
        {"side_effect": get_today_buys_ticker_strategy_side_effect}
        if get_today_buys_ticker_strategy_side_effect is not None
        else {"return_value": today_buys_rows}
    )

    write_log_patch = (
        patch("src.engine.boot_manager.write_log", new=write_log_mock)
        if write_log_mock is not None
        else patch("src.engine.boot_manager.write_log", new=AsyncMock())
    )

    with (
        patch("src.engine.boot_manager.token_manager") as tm,
        patch(
            "src.engine.boot_manager.get_balance",
            new=AsyncMock(return_value=(holdings, _summary())),
        ),
        patch("src.engine.boot_manager.get_daily_orders", new=AsyncMock(**get_daily_orders_kwargs)),
        write_log_patch,
        patch("src.db.stock_master.count_active", new=AsyncMock(return_value=2768)),
        patch("src.db.positions.load_all", new=AsyncMock(return_value=db_positions)),
        patch("src.db.positions.delete_position", new=AsyncMock()),
        patch("src.db.positions.save_position", new=AsyncMock()),
        patch(
            "src.db.trade_history.get_recent_buy_strategy",
            new=AsyncMock(side_effect=_get_recent_buy_strategy),
        ),
        patch("src.db.trade_history.mark_pending_buys_completed", new=AsyncMock(**mark_pending_kwargs)),
        patch(
            "src.db.trade_history.get_today_buys_ticker_strategy",
            new=AsyncMock(**today_buys_kwargs),
        ),
    ):
        tm.get_token = AsyncMock()
        await boot_manager.boot(scheduler)


def _warning_messages(caplog: pytest.LogCaptureFixture, prefix: str) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "src.engine.boot_manager"
        and r.levelno >= logging.WARNING
        and prefix in r.getMessage()
    ]


# ---------------------------------------------------------------------------
# 1. 「except Exception: pass」 4자리 — WARNING 로그로
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_kis_supplement_trade_history_lookup_failure_logs_warning(caplog):
    """KIS 잔고 보완 복구 — trade_history 조회 예외가 조용히 넘어가지 않는다."""
    registry = _FakeRegistry({"momentum": _FakeStrategy("momentum")})
    scheduler = _make_scheduler(registry)

    async def _boom(ticker):
        raise RuntimeError("boom")

    caplog.set_level(logging.WARNING, logger="src.engine.boot_manager")
    await _run_boot(
        scheduler,
        holdings=[_holding("777777")],
        db_positions=[],
        recent_buy_strategy_map={},
        all_orders=[],
        today_buys_rows=[],
        recent_buy_strategy_side_effect=_boom,
    )

    msgs = _warning_messages(caplog, "[boot_recover_trade_history_lookup_failed]")
    assert any("777777" in m for m in msgs), f"기대한 WARNING 없음: {caplog.text}"


@pytest.mark.asyncio
async def test_kis_supplement_order_lookup_failure_logs_warning(caplog):
    """KIS 잔고 보완 복구 — 매수일 판정용 주문내역 조회 예외가 조용히 넘어가지 않는다."""
    registry = _FakeRegistry({"momentum": _FakeStrategy("momentum")})
    scheduler = _make_scheduler(registry)

    caplog.set_level(logging.WARNING, logger="src.engine.boot_manager")
    await _run_boot(
        scheduler,
        holdings=[_holding("888888")],
        db_positions=[],
        recent_buy_strategy_map={},
        all_orders=[],
        today_buys_rows=[],
        get_daily_orders_side_effect=RuntimeError("boom"),
    )

    msgs = _warning_messages(caplog, "[boot_recover_order_lookup_failed]")
    assert any("888888" in m for m in msgs), f"기대한 WARNING 없음: {caplog.text}"


@pytest.mark.asyncio
async def test_mark_pending_buys_completed_failure_logs_warning(caplog):
    """PENDING 매수 기록 일괄 COMPLETED 처리 예외가 조용히 넘어가지 않는다."""
    registry = _FakeRegistry({"momentum": _FakeStrategy("momentum")})
    scheduler = _make_scheduler(registry)

    caplog.set_level(logging.WARNING, logger="src.engine.boot_manager")
    await _run_boot(
        scheduler,
        holdings=[_holding("999999")],
        db_positions=[],
        recent_buy_strategy_map={},
        all_orders=[],
        today_buys_rows=[],
        mark_pending_buys_completed_side_effect=RuntimeError("boom"),
    )

    msgs = _warning_messages(caplog, "[boot_recover_mark_pending_completed_failed]")
    assert msgs, f"기대한 WARNING 없음: {caplog.text}"


@pytest.mark.asyncio
async def test_today_buys_lookup_failure_logs_warning(caplog):
    """오늘 BUY (ticker,strategy) 조회 예외가 조용히 넘어가지 않는다."""
    registry = _FakeRegistry({"momentum": _FakeStrategy("momentum")})
    scheduler = _make_scheduler(registry)

    caplog.set_level(logging.WARNING, logger="src.engine.boot_manager")
    await _run_boot(
        scheduler,
        holdings=[],
        db_positions=[],
        recent_buy_strategy_map={},
        all_orders=[],
        today_buys_rows=[],
        get_today_buys_ticker_strategy_side_effect=RuntimeError("boom"),
    )

    msgs = _warning_messages(caplog, "[boot_recover_today_buys_lookup_failed]")
    assert msgs, f"기대한 WARNING 없음: {caplog.text}"


# ---------------------------------------------------------------------------
# 2. `[boot_recover_strategy_unknown]` — 출처 모를 때만 발화
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_kis_supplement_unknown_owner_emits_marker(caplog):
    """trade_history 가 전략을 모르면 path=kis_supplement 마커가 뜬다."""
    registry = _FakeRegistry({"momentum": _FakeStrategy("momentum")})
    scheduler = _make_scheduler(registry)

    caplog.set_level(logging.WARNING, logger="src.engine.boot_manager")
    await _run_boot(
        scheduler,
        holdings=[_holding("111222")],
        db_positions=[],
        recent_buy_strategy_map={},  # 모름
        all_orders=[],
        today_buys_rows=[],
    )

    msgs = _warning_messages(caplog, "[boot_recover_strategy_unknown]")
    assert any("path=kis_supplement" in m and "ticker=111222" in m for m in msgs), (
        f"기대한 마커 없음: {caplog.text}"
    )


@pytest.mark.asyncio
async def test_kis_supplement_known_owner_does_not_emit_marker(caplog):
    """trade_history 가 전략을 알면 path=kis_supplement 마커가 뜨지 않는다."""
    registry = _FakeRegistry(
        {
            "momentum": _FakeStrategy("momentum"),
            "volatility_breakout": _FakeStrategy("volatility_breakout"),
        }
    )
    scheduler = _make_scheduler(registry)

    caplog.set_level(logging.WARNING, logger="src.engine.boot_manager")
    await _run_boot(
        scheduler,
        holdings=[_holding("333444")],
        db_positions=[],
        recent_buy_strategy_map={"333444": "volatility_breakout"},
        all_orders=[],
        today_buys_rows=[],
    )

    msgs = _warning_messages(caplog, "[boot_recover_strategy_unknown]")
    assert not any("333444" in m for m in msgs), f"알려진 출처인데 마커 발화: {caplog.text}"


@pytest.mark.asyncio
async def test_unfilled_order_unknown_owner_emits_marker_with_order_no(caplog):
    """db_strategy_map 미스면 path=unfilled_order 마커가 order_no 와 함께 뜬다."""
    registry = _FakeRegistry({"momentum": _FakeStrategy("momentum")})
    scheduler = _make_scheduler(registry)

    caplog.set_level(logging.WARNING, logger="src.engine.boot_manager")
    await _run_boot(
        scheduler,
        holdings=[],
        db_positions=[],
        recent_buy_strategy_map={},
        all_orders=[_unfilled_order("555666", "ORDERX", price=1_000, qty=3)],
        today_buys_rows=[],
    )

    msgs = _warning_messages(caplog, "[boot_recover_strategy_unknown]")
    assert any(
        "path=unfilled_order" in m and "ticker=555666" in m and "order_no=ORDERX" in m
        for m in msgs
    ), f"기대한 마커 없음: {caplog.text}"


@pytest.mark.asyncio
async def test_unfilled_order_known_owner_does_not_emit_marker(caplog):
    """db_strategy_map 히트면 path=unfilled_order 마커가 뜨지 않는다."""
    registry = _FakeRegistry(
        {
            "momentum": _FakeStrategy("momentum"),
            "volatility_breakout": _FakeStrategy("volatility_breakout"),
        }
    )
    scheduler = _make_scheduler(registry)

    caplog.set_level(logging.WARNING, logger="src.engine.boot_manager")
    await _run_boot(
        scheduler,
        holdings=[],
        db_positions=[],
        recent_buy_strategy_map={},
        all_orders=[_unfilled_order("777888", "ORDERY", price=1_000, qty=3)],
        today_buys_rows=[{"ticker": "777888", "strategy": "volatility_breakout"}],
    )

    msgs = _warning_messages(caplog, "[boot_recover_strategy_unknown]")
    assert not any("777888" in m for m in msgs), f"알려진 출처인데 마커 발화: {caplog.text}"


@pytest.mark.asyncio
async def test_strategy_unknown_marker_does_not_duplicate_write_log():
    """`[boot_recover_strategy_unknown]` 은 logger.* 단독이다 — write_log 중복 호출 0건.

    cycle72 G-6(「같은 메시지를 write_log 로 또 쓰지 않는다 — 사건당 두 줄 금지」)
    — logger.warning 이 루트 `_DbLogHandler` 로 system_logs 에 들어가므로 같은
    사건을 `write_log` 로 또 적으면 AST 가드(`test_cycle72_ast_no_logger_write_log_pair.py`)
    가 붉어진다.
    """
    registry = _FakeRegistry({"momentum": _FakeStrategy("momentum")})
    scheduler = _make_scheduler(registry)

    write_log_mock = AsyncMock()
    await _run_boot(
        scheduler,
        holdings=[_holding("121212")],
        db_positions=[],
        recent_buy_strategy_map={},
        all_orders=[],
        today_buys_rows=[],
        write_log_mock=write_log_mock,
    )

    calls = [
        c for c in write_log_mock.await_args_list
        if "boot_recover_strategy_unknown" in str(c)
    ]
    assert not calls, f"write_log 로 [boot_recover_strategy_unknown] 중복 기록: {calls}"
