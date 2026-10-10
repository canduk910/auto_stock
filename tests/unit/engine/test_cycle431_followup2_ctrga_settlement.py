"""cycle431 follow-up Fix2 — CTRGA011R 사후 대사(21:30)가 「오늘 하루」에서
최근 창(45 달력일)으로 넓어진다.

검토 지적: `emit_settlement_detection` 이 `start_date=end_date=오늘` 만 보면,
권리의 `bass_dt`(기준일)가 매매정지·변경상장일보다 며칠 앞서는 액면교체 같은
사건을 "영원히" 못 잡는다(그날이 정확히 bass_dt 와 같을 때만 걸린다). 고친
것 = 보유 종목마다 최근 `CTRGA_LOOKBACK_CALENDAR_DAYS`(45) 달력일 창으로 조회
하고, 수량 변경 권리(14·15·17)만 비율을 계산해 추적 수량 vs KIS 보유수량을
match/mismatch 로 로그한다. 합병·회사분할(11·12)은 존재만 ERROR. `holdings`
는 `scheduler._settle()` 이 이미 조회한 잔고를 그대로 받는다(KIS 추가 호출 0).
"""
from __future__ import annotations

from datetime import date, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import corporate_action_reconcile as car
from src.engine.strategy_base import Position, StrategyState
from src.models.balance import StockHolding

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_TODAY = date(2026, 10, 10)


class _FakeStrategy:
    def __init__(self, strategy_id: str, positions: dict[str, Position] | None = None):
        self.strategy_id = strategy_id
        self.state = StrategyState(strategy_id=strategy_id)
        if positions:
            self.state.positions.update(positions)


class _FakeRegistry:
    def __init__(self, strategies: list[_FakeStrategy]):
        self._strategies = strategies

    def all(self):
        return list(self._strategies)


def _pos(ticker: str, qty: int) -> Position:
    return Position(
        ticker=ticker, buy_price=10_000, quantity=qty, order_no="O1",
        strategy_id="kojiro", buy_date=_TODAY - timedelta(days=5),
    )


def _holding(ticker: str, quantity: int) -> StockHolding:
    return StockHolding(
        ticker=ticker, name=f"종목{ticker}", quantity=quantity, sellable_quantity=quantity,
        avg_price=10_000.0, purchase_amount=10_000 * quantity,
        current_price=10_000, eval_amount=10_000 * quantity,
        eval_profit_loss=0, eval_profit_rate=0.0,
    )


@pytest.fixture(autouse=True)
def _reset_state():
    car.reset_state_for_test()
    yield
    car.reset_state_for_test()


async def _run(registry, holdings, rows_by_ticker: dict[str, list[dict]]):
    async def _fake_fetch(ticker, *, start_date, end_date, right_type_cd=""):
        return rows_by_ticker.get(ticker, [])

    with (
        patch("src.api.corporate_actions.fetch_period_rights", new=AsyncMock(side_effect=_fake_fetch)),
        patch("src.db._kst.today_kst", return_value=_TODAY),
    ):
        await car.emit_settlement_detection(registry, holdings)


def _right_row(*, bass_dt: str, rght_type_cd: str, cblc_qty: str, tot_alct_qty: str) -> dict:
    return {
        "bass_dt": bass_dt, "rght_type_cd": rght_type_cd,
        "cblc_qty": cblc_qty, "tot_alct_qty": tot_alct_qty,
    }


def test_e1_d5_right_row_already_reconciled_is_match(caplog):
    """E1 — D-5 액면병합(15) 행 + 반영 완료(추적==KIS) → match INFO."""
    strat = _FakeStrategy("kojiro", {"001390": _pos("001390", 10)})
    registry = _FakeRegistry([strat])
    holdings = [_holding("001390", 10)]
    rows = {"001390": [_right_row(bass_dt="20261005", rght_type_cd="15", cblc_qty="1", tot_alct_qty="10")]}

    with caplog.at_level("INFO", logger="src.engine.scheduler"):
        _run_sync(_run(registry, holdings, rows))

    matches = [r for r in caplog.records if "[corporate_action_ctrga_reconciled]" in r.message]
    assert len(matches) == 1
    assert matches[0].levelname == "INFO"
    assert "result=match" in matches[0].message
    assert "bass_dt=20261005" in matches[0].message


def test_e2_not_yet_reconciled_is_mismatch_error(caplog):
    """E2 — 같은 행인데 반영 안 됨(추적 10, KIS 1) → mismatch ERROR."""
    strat = _FakeStrategy("kojiro", {"001390": _pos("001390", 10)})
    registry = _FakeRegistry([strat])
    holdings = [_holding("001390", 1)]  # KIS 는 이미 1:10 병합됐는데 추적은 그대로
    rows = {"001390": [_right_row(bass_dt="20261005", rght_type_cd="15", cblc_qty="1", tot_alct_qty="10")]}

    with caplog.at_level("INFO", logger="src.engine.scheduler"):
        _run_sync(_run(registry, holdings, rows))

    mismatches = [r for r in caplog.records if "[corporate_action_ctrga_reconciled]" in r.message]
    assert len(mismatches) == 1
    assert mismatches[0].levelname == "ERROR"
    assert "result=mismatch" in mismatches[0].message
    assert "tracked=10" in mismatches[0].message
    assert "kis=1" in mismatches[0].message


def test_e3_no_rows_emits_nothing(caplog):
    """E3 — 행 없음 → 어떤 CTRGA 로그도 안 남는다."""
    strat = _FakeStrategy("kojiro", {"001390": _pos("001390", 10)})
    registry = _FakeRegistry([strat])
    holdings = [_holding("001390", 10)]

    with caplog.at_level("INFO", logger="src.engine.scheduler"):
        _run_sync(_run(registry, holdings, {}))

    assert not [r for r in caplog.records if "corporate_action_ctrga" in r.message]


def test_e4_merger_row_present_is_merger_error(caplog):
    """E4 — 합병(11) 행 존재 → merger_held ERROR(자동 반영 없음)."""
    strat = _FakeStrategy("kojiro", {"222222": _pos("222222", 5)})
    registry = _FakeRegistry([strat])
    holdings = [_holding("222222", 5)]
    rows = {"222222": [_right_row(bass_dt="20261001", rght_type_cd="11", cblc_qty="0", tot_alct_qty="0")]}

    with caplog.at_level("INFO", logger="src.engine.scheduler"):
        _run_sync(_run(registry, holdings, rows))

    merger_logs = [r for r in caplog.records if "[corporate_action_ctrga_merger_held]" in r.message]
    assert len(merger_logs) == 1
    assert merger_logs[0].levelname == "ERROR"
    # 수량 비교 로그는 나지 않는다(합병은 비율 계산 대상이 아니다)
    assert not [r for r in caplog.records if "[corporate_action_ctrga_reconciled]" in r.message]


def test_e5_leading_zero_code_is_robust(caplog):
    """E5 — `rght_type_cd="15"`(앞 0 없는 문자열)도 정수 비교로 정상 인식."""
    strat = _FakeStrategy("kojiro", {"333333": _pos("333333", 10)})
    registry = _FakeRegistry([strat])
    holdings = [_holding("333333", 10)]
    rows = {"333333": [_right_row(bass_dt="20261003", rght_type_cd="15", cblc_qty="1", tot_alct_qty="10")]}

    with caplog.at_level("INFO", logger="src.engine.scheduler"):
        _run_sync(_run(registry, holdings, rows))

    matches = [r for r in caplog.records if "[corporate_action_ctrga_reconciled]" in r.message]
    assert len(matches) == 1
    assert "result=match" in matches[0].message


def test_e6_dedup_same_ticker_bass_dt_once_per_run(caplog):
    """E6 — 같은 (ticker, bass_dt) 가 창이 겹쳐 두 번 와도 이번 실행에서는 1회만 로그."""
    strat = _FakeStrategy("kojiro", {"001390": _pos("001390", 10)})
    registry = _FakeRegistry([strat])
    holdings = [_holding("001390", 10)]
    row = _right_row(bass_dt="20261005", rght_type_cd="15", cblc_qty="1", tot_alct_qty="10")
    rows = {"001390": [row, dict(row)]}  # 중복 행(창 겹침 시뮬레이션)

    with caplog.at_level("INFO", logger="src.engine.scheduler"):
        _run_sync(_run(registry, holdings, rows))

    matches = [r for r in caplog.records if "[corporate_action_ctrga_reconciled]" in r.message]
    assert len(matches) == 1


def test_e7_query_failure_is_warning_and_does_not_block(caplog):
    """E7 — 조회 실패(예외) → WARNING 1행, 다른 종목 대사를 막지 않는다."""
    strat1 = _FakeStrategy("kojiro", {"001390": _pos("001390", 10)})
    strat2 = _FakeStrategy("donchian_swing", {"222222": _pos("222222", 5)})
    registry = _FakeRegistry([strat1, strat2])
    holdings = [_holding("001390", 10), _holding("222222", 5)]

    async def _fake_fetch(ticker, *, start_date, end_date, right_type_cd=""):
        if ticker == "001390":
            raise RuntimeError("boom")
        return [_right_row(bass_dt="20261001", rght_type_cd="14", cblc_qty="1", tot_alct_qty="1")]

    with (
        patch("src.api.corporate_actions.fetch_period_rights", new=AsyncMock(side_effect=_fake_fetch)),
        patch("src.db._kst.today_kst", return_value=_TODAY),
        caplog.at_level("INFO", logger="src.engine.scheduler"),
    ):
        _run_sync(car.emit_settlement_detection(registry, holdings))

    failed = [r for r in caplog.records if "[corporate_action_ctrga_check_failed]" in r.message]
    assert len(failed) == 1
    assert failed[0].levelname == "WARNING"
    matches = [r for r in caplog.records if "[corporate_action_ctrga_reconciled]" in r.message]
    assert len(matches) == 1  # 종목2는 정상 대사


def test_e8_no_held_tickers_returns_without_any_kis_call():
    """E8 — 보유 0 → fetch_period_rights 호출 없이 즉시 반환."""
    registry = _FakeRegistry([])
    with patch("src.api.corporate_actions.fetch_period_rights", new=AsyncMock()) as fetch_mock:
        _run_sync(car.emit_settlement_detection(registry, []))
    fetch_mock.assert_not_awaited()


def test_e9_window_is_45_calendar_days_not_today_only():
    """E9 — 조회 창이 (오늘-45일)~오늘 로 넓다(1일 창이 아니다)."""
    strat = _FakeStrategy("kojiro", {"001390": _pos("001390", 10)})
    registry = _FakeRegistry([strat])
    holdings = [_holding("001390", 10)]

    captured: dict = {}

    async def _fake_fetch(ticker, *, start_date, end_date, right_type_cd=""):
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        return []

    with (
        patch("src.api.corporate_actions.fetch_period_rights", new=AsyncMock(side_effect=_fake_fetch)),
        patch("src.db._kst.today_kst", return_value=_TODAY),
    ):
        _run_sync(car.emit_settlement_detection(registry, holdings))

    assert captured["end_date"] == _TODAY.strftime("%Y%m%d")
    expected_start = (_TODAY - timedelta(days=car.CTRGA_LOOKBACK_CALENDAR_DAYS)).strftime("%Y%m%d")
    assert captured["start_date"] == expected_start


def _run_sync(coro):
    import asyncio
    return asyncio.run(coro)
