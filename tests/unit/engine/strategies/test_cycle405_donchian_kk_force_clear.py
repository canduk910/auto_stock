"""cycle405 Red — donchian 15:20 시간 청산: `check_force_clear` · `force_clear_signal` · 명부 (명세 §3).

명세 정본 = `_workspace/red/cycle405_donchian_kkangto_spec.md` §3 · §9-5 · §9-6

계약 요약
- 보유 종목마다 (a) `days_held ≥ kk_time_exit_bars − 1`(기본 19) ∧ `H < E + kk_time_exit_min_r × R`
  또는 (b) `days_held ≥ kk_max_hold_bars − 1`(기본 249) 이면 그날 15:20 정리 목록에 넣는다.
  전량 반환 금지. `buy_date` 없음 = 넣지 않는다.
- 가격 시세를 읽지 않는다(고점·보유일·스탬프만). never-raise — 종목 예외는 그 종목만 건너뛰고
  WARNING, 전체 예외는 `[]` + WARNING.
- 마커: `[donchian_time_exit] ticker=… reason=no_1r|max_hold …`(INFO, 1회/종목/일) ·
  `[donchian_1520_check] held=… due=…`(INFO).
- `force_clear_signal(t)` → `Signal.TIME_EXIT`.
- `strategy_manifest` donchian 행 `close_at_1520=True` → `CLOSE_AT_1520_IDS` 에 들어간다.

보유일(`_business_days_held`)은 거래일 캐시 `_trading_days` 로 결정적으로 만든다 — 캐시 = 매수일 ~
어제까지의 평일, 오늘은 캐시 밖(장중 정상 상태) → `days_held` = 매수일 뒤 평일 수.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
DC_LOGGER = "src.engine.strategies.donchian_swing"
E = 100_000
N = 4_000                       # → R = 8,000 · +1R 목표 = 108,000
TODAY = date(2026, 10, 30)      # 금
NEXT = date(2026, 11, 2)        # 월(다음 거래일)


def _at(d: date, h: int = 15, m: int = 20) -> str:
    return datetime(d.year, d.month, d.day, h, m, 5, tzinfo=KST).isoformat()


def _weekday_back(d: date, k: int) -> date:
    """`d` 에서 평일 k 개 뒤로(d 자신 제외)."""
    cur = d
    while k > 0:
        cur -= timedelta(days=1)
        if cur.weekday() < 5:
            k -= 1
    return cur


def _mk(**params) -> DonchianSwingStrategy:
    s = DonchianSwingStrategy(StrategyConfig(
        strategy_id="donchian_swing", name="도치안", weight=0.2,
        params={"market_unit_mode": "off", **params},
    ))
    s.state.total_investment = 743_000
    return s


def _cache(s, today: date, held: int) -> date:
    """매수일 = 오늘에서 평일 `held` 개 전. 캐시 = 매수일 5평일 전 ~ 어제."""
    buy = _weekday_back(today, held)
    d = _weekday_back(today, held + 5)
    y = _weekday_back(today, 1)
    while d <= y:
        if d.weekday() < 5:
            s._trading_days.add(d)
        d += timedelta(days=1)
    return buy


def _hold(s, ticker: str, *, buy_date, high: int, n: float | None = N) -> Position:
    pos = Position(ticker=ticker, buy_price=E, quantity=1, order_no="O405",
                   strategy_id="donchian_swing", buy_date=buy_date or TODAY)
    if buy_date is None:
        pos.buy_date = None
    pos.high_since_buy = high
    s.state.positions[ticker] = pos
    if n is not None:
        s._entry_atr[ticker] = n
    return pos


def _info(caplog, marker: str) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.levelno >= logging.INFO and r.getMessage().startswith(marker + " ")]


@pytest.fixture(autouse=True)
def _no_quotes(monkeypatch):
    """시세를 읽지 않는다 — 시세 저장소를 비워 두고, 읽으면 붉게 만든다."""
    class _Boom(dict):
        def get(self, *a, **k):  # noqa: D401
            raise AssertionError("check_force_clear 가 시세(ticker_prices/ticker_last_tick)를 읽었다")
        __getitem__ = get
    monkeypatch.setattr("src.engine.scanner.ticker_prices", _Boom(), raising=False)
    monkeypatch.setattr("src.engine.scanner.ticker_last_tick", _Boom(), raising=False)


# ===========================================================================
# 5. 15:20 시간 청산 (명세 §9-5)
# ===========================================================================
@pytest.mark.parametrize(
    "held, high, due",
    [
        (19, 107_999, True),    # 20번째 봉 · +1R 미도달
        (19, 108_000, False),   # +1R 에 닿았다 = 면제
        (18, 100_000, False),   # 19번째 봉 = 아직
        (25, 107_999, True),    # 놓쳐도 계속 참
        (249, 300_000, True),   # 250번째 봉 = 고점 무관
        (248, 300_000, False),
    ],
)
def test_r5_force_clear_due_by_days_held_and_1r(caplog, held, high, due):
    caplog.set_level(logging.INFO, logger=DC_LOGGER)
    s = _mk()
    buy = _cache(s, TODAY, held)
    _hold(s, "990001", buy_date=buy, high=high)
    with freeze_time(_at(TODAY)):
        assert s._business_days_held(buy, TODAY)[0] == held, "픽스처 전제 — 보유일 계상"
        got = s.check_force_clear()
    assert got == (["990001"] if due else []), f"held={held} high={high}"


def test_r5_returns_only_due_tickers_not_all(caplog):
    caplog.set_level(logging.INFO, logger=DC_LOGGER)
    s = _mk()
    due = _cache(s, TODAY, 19)
    fresh = _weekday_back(TODAY, 3)
    _hold(s, "990001", buy_date=due, high=101_000)
    _hold(s, "990002", buy_date=fresh, high=101_000)
    _hold(s, "990003", buy_date=due, high=120_000)
    with freeze_time(_at(TODAY)):
        assert s.check_force_clear() == ["990001"], "전량 반환 금지(멀티데이 소멸)"


def test_r5_no_buy_date_is_never_due():
    s = _mk()
    _cache(s, TODAY, 249)
    _hold(s, "990001", buy_date=None, high=100_000)
    with freeze_time(_at(TODAY)):
        assert s.check_force_clear() == []


def test_r5_unstamped_uses_8pct_r_for_1r_target():
    """스탬프 없음 → R=8,000 → 목표 108,000. 큰 N 이 들어간 경우와 구분: N=6,000 → R=9,000 → 109,000."""
    s = _mk()
    buy = _cache(s, TODAY, 19)
    _hold(s, "990001", buy_date=buy, high=108_500, n=None)
    _hold(s, "990002", buy_date=buy, high=108_500, n=6_000)
    with freeze_time(_at(TODAY)):
        assert s.check_force_clear() == ["990002"]


def test_r5_missed_1520_is_caught_next_day():
    s = _mk()
    buy = _cache(s, TODAY, 19)
    _hold(s, "990001", buy_date=buy, high=101_000)
    with freeze_time(_at(TODAY)):
        assert s.check_force_clear() == ["990001"]
    s._trading_days.add(TODAY)                 # 다음 날 부팅이 오늘 봉을 캐시에 넣었다
    with freeze_time(_at(NEXT)):
        assert s._business_days_held(buy, NEXT)[0] == 20
        assert s.check_force_clear() == ["990001"], "재시작·매도 거부로 놓치면 다음 날 15:20 이 다시 잡는다"


def test_r5_kk_time_exit_params_are_read():
    s = _mk(kk_time_exit_bars=10, kk_time_exit_min_r=2.0)
    buy = _cache(s, TODAY, 9)
    _hold(s, "990001", buy_date=buy, high=115_999)   # +2R = 116,000 미도달
    _hold(s, "990002", buy_date=buy, high=116_000)
    with freeze_time(_at(TODAY)):
        assert s.check_force_clear() == ["990001"]


def test_r5_one_ticker_error_does_not_block_others(caplog):
    caplog.set_level(logging.INFO, logger=DC_LOGGER)
    s = _mk()
    buy = _cache(s, TODAY, 19)
    bad = _hold(s, "990001", buy_date=buy, high=101_000)
    bad.high_since_buy = "broken"               # 비교·변환 어디서든 터진다
    _hold(s, "990002", buy_date=buy, high=101_000)
    with freeze_time(_at(TODAY)):
        got = s.check_force_clear()
    assert got == ["990002"]
    warns = [r for r in caplog.records
             if r.name == DC_LOGGER and r.levelno >= logging.WARNING and "990001" in r.getMessage()]
    assert warns, "종목 예외는 WARNING 을 남긴다"


def test_r5_whole_error_returns_empty_and_warns(caplog):
    caplog.set_level(logging.INFO, logger=DC_LOGGER)
    s = _mk()

    class _Exploding(dict):
        def _boom(self, *a, **k):
            raise RuntimeError("positions 붕괴")
        keys = items = values = __iter__ = __len__ = get = _boom

    s.state.positions = _Exploding()
    with freeze_time(_at(TODAY)):
        assert s.check_force_clear() == []
    assert [r for r in caplog.records if r.name == DC_LOGGER and r.levelno >= logging.WARNING]


def test_r5_markers_time_exit_once_per_ticker_day_and_check_summary(caplog):
    caplog.set_level(logging.INFO, logger=DC_LOGGER)
    s = _mk()
    buy = _cache(s, TODAY, 19)
    old = _cache(s, TODAY, 249)
    _hold(s, "990001", buy_date=buy, high=101_000)
    _hold(s, "990002", buy_date=old, high=300_000)
    _hold(s, "990003", buy_date=buy, high=120_000)
    with freeze_time(_at(TODAY)):
        first = s.check_force_clear()
        second = s.check_force_clear()
    assert first == second == ["990001", "990002"], "마커 cap 은 로그 전용 — 목록(청산 재시도)을 삼키지 않는다"
    tex = _info(caplog, "[donchian_time_exit]")
    assert len(tex) == 2, f"1회/종목/일 — {tex}"
    by = {l.split("ticker=")[1].split()[0]: l for l in tex}
    assert "reason=no_1r" in by["990001"] and "days_held=19" in by["990001"]
    assert "reason=max_hold" in by["990002"] and "days_held=249" in by["990002"]
    chk = _info(caplog, "[donchian_1520_check]")
    assert chk and "held=3" in chk[0] and "due=2" in chk[0], chk


def test_r5_force_clear_signal_is_time_exit():
    assert _mk().force_clear_signal("990001") == Signal.TIME_EXIT


def test_r5_resolve_force_clear_signal_reads_time_exit():
    """스케줄러가 실제로 읽는 경로(never-raise 래퍼)도 TIME_EXIT 다."""
    from src.engine.strategy_base import resolve_force_clear_signal

    assert resolve_force_clear_signal(_mk(), "990001") == Signal.TIME_EXIT


# ===========================================================================
# 6. 명부 (명세 §9-6) — donchian 만 close_at_1520 이 켜진다
# ===========================================================================
def test_r6_manifest_donchian_close_at_1520_and_ids():
    from src.engine import strategy_manifest as sm

    row = {e.strategy_id: e for e in sm.STRATEGY_MANIFEST}["donchian_swing"]
    assert row.close_at_1520 is True
    assert (row.eval_driver, row.breakout_rank, row.open_price_target, row.market_unit_policy) == (
        "swing_poll", None, False, "scale"), "다른 칸은 그대로"
    assert sm.CLOSE_AT_1520_IDS == (
        "volatility_breakout", "long_tail_volatility", "donchian_swing", "etf_trend",
    )
