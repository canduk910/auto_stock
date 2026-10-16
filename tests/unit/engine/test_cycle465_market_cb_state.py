"""cycle465 — 서킷브레이커·사이드카 인지 + CB 중 LOW 재구독 정지 (R3 C).

자문 `_workspace/domain_consult/2026-10-16_market_cb_sidecar_detect.md` §4 T1~T8.
가짜 프레임은 라이브 모양 원문(`[0]=종목코드`)을 `parse_market_op_payload` →
`record_market_op_event` 로 흘린다(실제 수신 경로와 같은 입구).
"""
from __future__ import annotations

import ast
import dataclasses
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from src.api.market_operation import parse_market_op_payload
from src.engine import market_cb_state as mcb
from src.engine import market_operation_monitor as mon

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
_REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _reset():
    mon.reset_market_op_state()
    mcb.reset_market_cb_state()
    yield
    mon.reset_market_op_state()
    mcb.reset_market_cb_state()


def _frame(ticker: str, code: str, at: datetime, *, trht: str = "N", iscd: str = "55", vi: str = "N"):
    ev = parse_market_op_payload(ticker, f"{ticker}^{trht}^(null)^{code}^^^^{iscd}^{vi}^N^")
    ev = dataclasses.replace(ev, received_at=at)
    mon.record_market_op_event(ev)
    return ev


def _t(h, m, s=0):
    return datetime(2026, 10, 15, h, m, s, tzinfo=KST)


# --------------------------------------------------------------------------- 상태 기계
def test_t1_st_code_174_enters_cb_and_suppresses_low(caplog):
    with caplog.at_level(logging.WARNING, logger="src.engine.market_cb_state"):
        _frame("196170", "174", _t(11, 0))
    assert mcb.is_low_resub_suppressed(_t(11, 1)) is True
    s = mcb.get_market_cb_summary(_t(11, 1))
    assert s["markets"]["KOSDAQ"]["state"] == "CB_ACTIVE"
    assert s["markets"]["KOSDAQ"]["stage"] == 1
    assert s["markets"]["KOSDAQ"]["source"] == "ST"
    assert s["markets"]["KOSPI"]["state"] == "NORMAL"
    assert any(r.getMessage().startswith("[market_cb_active] market=KOSDAQ") for r in caplog.records)


def test_t2_alpha_sequence_af8_af1_bf9_then_grace_180s():
    """10-15 실측 순서 — 005930 AF8(TRHT=Y) → AF1 → BF9 → 유예 180초 뒤 해제."""
    _frame("005930", "AF8", _t(12, 38, 11), trht="Y")
    s = mcb.get_market_cb_summary(_t(12, 40))
    assert s["markets"]["KOSPI"]["state"] == "CB_ACTIVE" and s["markets"]["KOSPI"]["stage"] == 1
    _frame("005930", "AF1", _t(12, 58, 12))
    assert mcb.get_market_cb_summary(_t(12, 59))["markets"]["KOSPI"]["stage"] == 1  # 단계 유지
    _frame("005930", "BF9", _t(13, 8, 0))
    assert mcb.is_low_resub_suppressed(_t(13, 11, 0)) is True  # 유예 안
    assert mcb.is_low_resub_suppressed(_t(13, 11, 1)) is False  # 유예 끝
    assert mcb.get_market_cb_summary(_t(13, 12))["markets"]["KOSPI"]["state"] == "NORMAL"


def test_t3_ttl_release_when_no_release_code(caplog):
    _frame("196170", "174", _t(11, 0))
    with caplog.at_level(logging.WARNING, logger="src.engine.market_cb_state"):
        assert mcb.is_low_resub_suppressed(_t(11, 40, 0)) is True  # 정확히 40분 = 아직
        mcb.is_low_resub_suppressed(_t(11, 40, 1))
    rel = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[market_cb_release]")]
    assert len(rel) == 1 and "reason=ttl" in rel[0]
    assert mcb.is_low_resub_suppressed(_t(11, 43, 2)) is False  # TTL 해제 + 유예 180초 뒤


def test_t3b_third_entry_is_stage3_and_never_expires():
    _frame("005930", "174", _t(10, 0))
    _frame("005930", "175", _t(10, 30))
    _frame("005930", "174", _t(11, 0))   # 2단계(해제 뒤 5분 넘음)
    _frame("005930", "175", _t(11, 30))
    _frame("005930", "174", _t(13, 0))   # 3단계
    s = mcb.get_market_cb_summary(_t(13, 1))
    assert s["markets"]["KOSPI"]["stage"] == 3
    _frame("005930", "175", _t(13, 5))   # 3단계는 해제 코드로도 안 풀린다(장 종료)
    assert mcb.is_low_resub_suppressed(_t(15, 0)) is True


def test_reentry_within_5min_of_release_keeps_stage():
    _frame("196170", "AF8", _t(12, 23))
    _frame("196170", "BF9", _t(12, 53))
    _frame("196170", "174", _t(12, 55))  # 해제 뒤 2분 — 오차 프레임, 같은 단계
    assert mcb.get_market_cb_summary(_t(12, 56))["markets"]["KOSDAQ"]["stage"] == 1


def test_t4_sidecar_recorded_but_does_not_suppress(caplog):
    with caplog.at_level(logging.WARNING, logger="src.engine.market_cb_state"):
        _frame("005930", "387", _t(10, 0))
    s = mcb.get_market_cb_summary(_t(10, 1))
    assert s["sidecar"]["KOSPI"]["side"] == "sell"
    assert s["low_skip_active"] is False
    assert mcb.is_low_resub_suppressed(_t(10, 1)) is False
    assert any("[market_sidecar] market=KOSPI side=sell transition=on" in r.getMessage() for r in caplog.records)
    assert mcb.get_market_cb_summary(_t(10, 6, 1))["sidecar"]["KOSPI"] is None  # 6분 TTL


def test_t5_non_rep_ticker_and_stock_level_events_ignored(caplog):
    _frame("053450", "AF8", _t(12, 23))                       # 대표 아님
    with caplog.at_level(logging.INFO, logger="src.engine.market_cb_state"):
        _frame("005930", "AB1", _t(12, 24), trht="Y", iscd="58", vi="Y")  # 대표의 종목 사건
        assert mcb.suppressing_markets(_t(12, 25)) == []
        _frame("005930", "ZZ9", _t(12, 26))
        _frame("005930", "ZZ9", _t(12, 27))
    unk = [r for r in caplog.records if "[market_status_unknown_code]" in r.getMessage()]
    assert [r.getMessage() for r in unk] == ["[market_status_unknown_code] market=KOSPI code=ZZ9"]


def test_t5b_normal_codes_are_silent(caplog):
    with caplog.at_level(logging.INFO, logger="src.engine.market_cb_state"):
        for code in ("110", "112", "121", "129", "F06", "P11"):
            _frame("005930", code, _t(9, 0))
    assert not [r for r in caplog.records if r.name == "src.engine.market_cb_state"]


def test_t6_window_outside_0900_1530_does_not_suppress(caplog):
    _frame("005930", "174", _t(8, 40))
    assert mcb.is_low_resub_suppressed(_t(8, 41)) is False
    assert mcb.get_market_cb_summary(_t(8, 41))["markets"]["KOSPI"]["state"] == "CB_ACTIVE"
    mcb.reset_market_cb_state()
    _frame("005930", "174", _t(15, 20))
    assert mcb.is_low_resub_suppressed(_t(15, 31)) is False
    mcb.reset_market_cb_state()
    with caplog.at_level(logging.WARNING, logger="src.engine.market_cb_state"):
        _frame("005930", "174", _t(14, 55))
    assert any("[market_cb_unexpected]" in r.getMessage() for r in caplog.records)
    assert mcb.is_low_resub_suppressed(_t(14, 56)) is True


def test_halt_164_suppresses_and_releases_on_112():
    _frame("196170", "164", _t(10, 0))
    assert mcb.is_low_resub_suppressed(_t(10, 1)) is True
    _frame("196170", "112", _t(10, 20))
    assert mcb.is_low_resub_suppressed(_t(10, 23, 1)) is False


def test_new_day_self_resets_state():
    _frame("005930", "174", _t(11, 0))
    nxt = datetime(2026, 10, 16, 10, 0, tzinfo=KST)
    assert mcb.is_low_resub_suppressed(nxt) is False
    assert mcb.get_market_cb_summary(nxt)["markets"]["KOSPI"]["stage"] == 0


def test_daily_reset_through_monitor_reset():
    _frame("005930", "174", _t(11, 0))
    mon.reset_market_op_state()
    assert mcb.suppressing_markets(_t(11, 1)) == []


def test_summary_exposes_confirmed_axis_in_market_op_summary():
    _frame("005930", "174", datetime.now(KST))
    cb = mon.get_market_op_state_summary()["circuit_breaker"]
    assert "suspected" in cb  # 기존 휴리스틱 축 그대로
    assert cb["confirmed"]["markets"]["KOSPI"]["state"] == "CB_ACTIVE"


def test_on_event_failure_does_not_break_monitor(monkeypatch):
    monkeypatch.setattr(mcb, "on_event", MagicMock(side_effect=RuntimeError("boom")))
    _frame("005930", "174", _t(11, 0), trht="Y")  # raise 하지 않는다
    assert "005930" in mon.get_halt_active_tickers()


def test_grace_equals_resubscribe_throttle():
    from src.engine.stale_watcher_core import RESUBSCRIBE_THROTTLE_SECS

    assert mcb.RELEASE_GRACE_SECS == RESUBSCRIBE_THROTTLE_SECS


# --------------------------------------------------------------------------- 구독
@pytest.mark.asyncio
async def test_t7_subscribe_reps_uses_bypass_false_and_survives_failure(caplog):
    calls = []

    class _WS:
        async def subscribe(self, tr_id, tr_key, *, bypass_limit=False):
            calls.append((tr_id, tr_key, bypass_limit))
            if tr_id == "H0UNMKO0":
                raise RuntimeError("slot full")

    with caplog.at_level(logging.INFO, logger="src.engine.market_cb_state"):
        ok = await mcb.subscribe_market_status_reps(_WS())
    assert ok == 2
    assert calls == [
        ("H0STMKO0", "005930", False), ("H0STMKO0", "196170", False), ("H0UNMKO0", "196170", False),
    ]
    assert any(r.levelno == logging.WARNING and "[market_status_rep_subscribed]" in r.getMessage()
               for r in caplog.records)


def test_t7b_reps_are_restored_on_reconnect():
    """재연결 복원은 `_subscriptions` 전체(비-시세 포함)를 다시 보낸다 — 대표 구독도 포함."""
    src = (_REPO / "src/realtime/websocket.py").read_text()
    fn = src[src.index("async def _restore_subscriptions_after_reconnect"):]
    fn = fn[: fn.index("\n    async def ", 10) if "\n    async def " in fn[10:] else len(fn)]
    assert "for tr_id, tr_key in list(self._subscriptions)" in fn


def test_ast_reps_capped_at_three_and_no_bypass_true():
    assert len(mcb.MARKET_STATUS_REPS) <= 3
    tree = ast.parse((_REPO / "src/engine/market_cb_state.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "bypass_limit":
            assert isinstance(node.value, ast.Constant) and node.value.value is False


def test_ast_leaf_imports_stdlib_only():
    tree = ast.parse((_REPO / "src/engine/market_cb_state.py").read_text())
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
            assert not (mod or "").startswith("src"), mod


def test_ast_market_op_subscribe_untouched_by_cycle465():
    assert "market_cb_state" not in (_REPO / "src/engine/market_op_subscribe.py").read_text()


# --------------------------------------------------------------------------- stale 경로 (C)
def _sched(positions):
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._stale_retry_count = {}
    sched._stale_last_resubscribe_at = {}
    sched._stale_force_retry_history = {}
    sched._pending_next_day_clear = set()
    sched._running = True
    sched._STALE_DETAIL_TICKER_CAP = 20
    st = MagicMock()
    st.positions = {t: MagicMock() for t in positions}
    strat = MagicMock(state=st)
    sched.registry = MagicMock(all=MagicMock(return_value=[strat]))
    return sched


def _capture():
    logger = logging.getLogger("src.engine.scheduler")
    records: list[logging.LogRecord] = []
    h = logging.Handler(level=logging.WARNING)
    h.emit = records.append  # type: ignore[assignment]
    return logger, h, records


@pytest.mark.asyncio
@freeze_time("2026-10-15 03:00:00")  # KST 12:00
async def test_c1_k_watcher_cb_skips_low_keeps_high(monkeypatch):
    import src.engine.scanner as scanner_mod
    import src.realtime.websocket_pool as wp_mod
    from src.engine import no_feed_registry as reg
    from src.engine import stale_watcher_core as core

    now = datetime.now(KST)
    _frame("005930", "AF8", now - timedelta(minutes=5), trht="Y")
    subscribed = ["005930", "035420", "035720"]
    pool = MagicMock()
    pool.get_subscribed_tickers = lambda: set(subscribed)
    pool.unsubscribe_in_pool = AsyncMock()
    pool.subscribe = AsyncMock()
    pool.get_subscriptions_by_session = MagicMock(return_value={})
    pool._subscribed_at = {}
    monkeypatch.setattr(wp_mod, "kis_ws_pool", pool)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {t: now - timedelta(seconds=120) for t in subscribed})
    monkeypatch.setattr(reg, "ensure_fresh", AsyncMock(return_value=None))
    monkeypatch.setattr(reg, "is_no_feed", lambda t: False)
    monkeypatch.setattr(mon, "is_ticker_stale_excluded", lambda t: False)

    class _NoSleep:
        async def sleep(self, s):
            return None

    monkeypatch.setattr(core, "asyncio", _NoSleep())
    sched = _sched(["005930"])
    logger, h, records = _capture()
    logger.addHandler(h)
    try:
        await core.check_and_resubscribe_stale(sched)
    finally:
        logger.removeHandler(h)

    subs = [c.args[1] for c in pool.subscribe.await_args_list]
    assert subs == ["005930"]
    assert pool.subscribe.await_args_list[0].kwargs.get("bypass_limit") is True
    assert "035420" not in sched._stale_retry_count
    msgs = [r.getMessage() for r in records]
    assert any(m.startswith("[stale_skip_market_cb]") and "low=2" in m and "high=1" in m for m in msgs)
    assert not any("[stale_skip_call_auction]" in m for m in msgs)


@pytest.mark.asyncio
@freeze_time("2026-10-15 03:00:00")  # KST 12:00
async def test_c2_priority_resubscribe_cb_empties_low():
    from src.engine import stale_manager
    from src.engine.stale_tracker import StaleTrackerState
    from src.engine.scheduler import TradingScheduler

    now = datetime.now(KST)
    _frame("196170", "174", now - timedelta(minutes=1))
    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    object.__setattr__(sched, "_pending_next_day_clear", set())
    st = MagicMock()
    st.positions = {"005930": MagicMock()}
    sched.registry = MagicMock(all=lambda: [MagicMock(state=st)])
    stale = now - timedelta(seconds=120)
    pool = MagicMock()
    pool.unsubscribe_in_pool = AsyncMock()
    pool.subscribe = AsyncMock(return_value="main")
    sess = MagicMock()
    sess.is_call_auction_now = MagicMock(return_value=False)
    logger, h, records = _capture()
    logger.addHandler(h)
    try:
        with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
             patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
             patch("src.engine.session.session_tracker", sess), \
             patch("src.engine.scanner.ticker_last_tick",
                   new={"005930": stale, "035420": stale, "035720": stale}):
            result = await stale_manager.resubscribe_stale_priority(sched, cap=10)
    finally:
        logger.removeHandler(h)
    assert result == ["005930"]
    assert any(r.getMessage().startswith("[stale_skip_market_cb_priority] low=2") for r in records)


@pytest.mark.asyncio
@freeze_time("2026-10-15 03:00:00")
async def test_c3_sidecar_does_not_skip_low():
    from src.engine import stale_manager
    from src.engine.stale_tracker import StaleTrackerState
    from src.engine.scheduler import TradingScheduler

    now = datetime.now(KST)
    _frame("005930", "387", now - timedelta(minutes=1))
    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    object.__setattr__(sched, "_pending_next_day_clear", set())
    sched.registry = MagicMock(all=lambda: [])
    stale = now - timedelta(seconds=120)
    pool = MagicMock()
    pool.unsubscribe_in_pool = AsyncMock()
    pool.subscribe = AsyncMock(return_value="main")
    sess = MagicMock()
    sess.is_call_auction_now = MagicMock(return_value=False)
    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", sess), \
         patch("src.engine.scanner.ticker_last_tick", new={"035420": stale}):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)
    assert result == ["035420"]


# --------------------------------------------------------------------------- T8 동시호가 회귀 0
@pytest.mark.asyncio
async def test_t8_st_open_close_codes_do_not_change_call_auction_outside_window():
    from src.engine.session import SessionTracker

    tr = SessionTracker()
    await tr.on_h0nxmko0("005930", "110", "")
    assert tr.is_call_auction_now(datetime(2026, 10, 15, 14, 0, tzinfo=KST)) is False
