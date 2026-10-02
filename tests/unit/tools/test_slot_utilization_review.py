"""전략별 예산 사용률·칸 수 측정 — 보유 재구성 순수 함수 단위 테스트 (2026-10-02).

대상 = `tools/slot_utilization_review.py` 의 순수 함수(`filter_trade_events` ·
`build_daily_timeline` · `reconcile_with_live_positions`). 이 파일은 `src/`·8영역·
DB·KIS 호출을 전혀 하지 않는다 — 전부 로컬 인메모리 데이터로만 돈다(READ-ONLY
분석 스크립트의 TDD 선행 — slot_handoff.md §2·§3.2).

핵심 계약:
- `status` 가 PENDING/CANCELLED 인 행은 재구성에서 완전히 제외된다.
- 부분 매도는 수량을 빼고(매입원가도 비례로 줄이고) 0 이 되면 포지션을 닫는다.
- 같은 날 사고팔기(인트라데이 왕복)는 장마감 스냅샷에서 닫힌 것으로, 장중 최대
  동시보유 집계에서는 보유 중이던 시점을 반영한다.
- 거래 없는 날도 직전 보유를 이월한다(조밀한 일자 타임라인).
- 보유보다 많은 매도는 경고로 기록하고 0 이하로 내려가지 않게 클램프한다(음수 보유 금지).
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "tools" / "slot_utilization_review.py"

KST = timezone(timedelta(hours=9))


def _load_module():
    spec = importlib.util.spec_from_file_location("slot_utilization_review_c399", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclass 의 `from __future__ import annotations` 지연평가가 모듈을
    # sys.modules 에서 찾으므로, exec 전에 등록해야 한다.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


def _ts(day: str, hms: str = "10:00:00") -> datetime:
    return datetime.fromisoformat(f"{day}T{hms}+09:00")


def _row(strategy, ticker, trade_type, price, qty, day, hms="10:00:00", status="COMPLETED"):
    return {
        "strategy": strategy,
        "ticker": ticker,
        "trade_type": trade_type,
        "price": price,
        "quantity": qty,
        "timestamp": _ts(day, hms),
        "status": status,
    }


# ── filter_trade_events ──────────────────────────────────────────────

def test_filter_excludes_pending_and_cancelled(mod):
    rows = [
        _row("kojiro", "005930", "BUY", 70000, 10, "2026-09-21", status="PENDING"),
        _row("kojiro", "005930", "BUY", 70000, 10, "2026-09-21", status="CANCELLED"),
        _row("kojiro", "005930", "BUY", 70000, 10, "2026-09-21", status="COMPLETED"),
        _row("kojiro", "005930", "SELL", 71000, 5, "2026-09-22", status="PARTIAL"),
    ]
    events = mod.filter_trade_events(rows)
    assert len(events) == 2
    assert {e.status for e in events} == {"COMPLETED", "PARTIAL"}


def test_filter_is_case_insensitive_on_status(mod):
    rows = [_row("kojiro", "005930", "BUY", 70000, 10, "2026-09-21", status="completed")]
    events = mod.filter_trade_events(rows)
    assert len(events) == 1


# ── build_daily_timeline — 기본 매수/매도 ────────────────────────────

def test_simple_buy_appears_in_eod_snapshot(mod):
    rows = [_row("kojiro", "005930", "BUY", 70000, 10, "2026-09-21")]
    events = mod.filter_trade_events(rows)
    tl = mod.build_daily_timeline(events, strategies=["kojiro"], trading_days=["2026-09-21"])
    snap = tl["eod"][("kojiro", "2026-09-21")]
    assert snap == [{"ticker": "005930", "quantity": 10, "cost_basis": 700000.0}]
    assert tl["eod_count"][("kojiro", "2026-09-21")] == 1
    assert tl["eod_cost_total"][("kojiro", "2026-09-21")] == 700000.0


def test_partial_sell_reduces_quantity_and_cost_proportionally(mod):
    rows = [
        _row("kojiro", "005930", "BUY", 70000, 10, "2026-09-21"),
        _row("kojiro", "005930", "SELL", 72000, 4, "2026-09-22"),
    ]
    events = mod.filter_trade_events(rows)
    tl = mod.build_daily_timeline(
        events, strategies=["kojiro"], trading_days=["2026-09-21", "2026-09-22"]
    )
    snap = tl["eod"][("kojiro", "2026-09-22")]
    assert len(snap) == 1
    row = snap[0]
    assert row["ticker"] == "005930"
    assert row["quantity"] == 6
    # 평단 70000 유지 — 비례 차감이므로 잔여원가 = 6 * 70000
    assert row["cost_basis"] == pytest.approx(420000.0)


def test_full_sell_closes_position_same_day(mod):
    rows = [
        _row("kojiro", "005930", "BUY", 70000, 10, "2026-09-21", hms="09:30:00"),
        _row("kojiro", "005930", "SELL", 72000, 10, "2026-09-21", hms="15:00:00"),
    ]
    events = mod.filter_trade_events(rows)
    tl = mod.build_daily_timeline(events, strategies=["kojiro"], trading_days=["2026-09-21"])
    assert tl["eod"][("kojiro", "2026-09-21")] == []
    assert tl["eod_count"][("kojiro", "2026-09-21")] == 0
    # 장중에는 들고 있었다
    assert tl["intraday_max_count"][("kojiro", "2026-09-21")] == 1


def test_carry_forward_across_days_without_trades(mod):
    rows = [_row("kojiro", "005930", "BUY", 70000, 10, "2026-09-21")]
    events = mod.filter_trade_events(rows)
    days = ["2026-09-21", "2026-09-22", "2026-09-23"]
    tl = mod.build_daily_timeline(events, strategies=["kojiro"], trading_days=days)
    # 09-22·09-23 에 거래가 없어도 09-21 매수분이 그대로 이월된다
    for d in ("2026-09-22", "2026-09-23"):
        snap = tl["eod"][("kojiro", d)]
        assert snap == [{"ticker": "005930", "quantity": 10, "cost_basis": 700000.0}]
    # 거래 없는 날도 strategies 파라미터 기준으로 조밀하게 채워진다
    assert set(k[1] for k in tl["eod"] if k[0] == "kojiro") == set(days)


def test_intraday_max_can_exceed_eod_count(mod):
    # 같은 날 A 매수 → B 매수 → A 전량 매도 : 장중 최대 2, 장마감 1(B 만 보유)
    rows = [
        _row("kojiro", "A1", "BUY", 10000, 10, "2026-09-21", hms="09:30:00"),
        _row("kojiro", "B2", "BUY", 20000, 5, "2026-09-21", hms="10:00:00"),
        _row("kojiro", "A1", "SELL", 10500, 10, "2026-09-21", hms="14:00:00"),
    ]
    events = mod.filter_trade_events(rows)
    tl = mod.build_daily_timeline(events, strategies=["kojiro"], trading_days=["2026-09-21"])
    assert tl["intraday_max_count"][("kojiro", "2026-09-21")] == 2
    assert tl["eod_count"][("kojiro", "2026-09-21")] == 1
    assert tl["eod"][("kojiro", "2026-09-21")] == [
        {"ticker": "B2", "quantity": 5, "cost_basis": 100000.0}
    ]


def test_oversell_is_clamped_and_warned_not_negative(mod):
    rows = [
        _row("kojiro", "005930", "BUY", 70000, 5, "2026-09-21"),
        # 보유 5인데 8주 매도 시도 — 외부(운영자) 매도 등으로 추적과 어긋난 경우
        _row("kojiro", "005930", "SELL", 72000, 8, "2026-09-22"),
    ]
    events = mod.filter_trade_events(rows)
    tl = mod.build_daily_timeline(
        events, strategies=["kojiro"], trading_days=["2026-09-21", "2026-09-22"]
    )
    snap = tl["eod"][("kojiro", "2026-09-22")]
    assert snap == []  # 0 으로 클램프, 음수 없음
    assert len(tl["oversell_warnings"]) == 1
    w = tl["oversell_warnings"][0]
    assert w["ticker"] == "005930"
    assert w["held"] == 5
    assert w["sell_qty"] == 8


def test_later_sell_does_not_retroactively_zero_earlier_snapshots(mod):
    # 실측 결함 재현 — 매수 후 며칠 뒤 매도하면, 그 사이 날짜의 장마감 스냅샷이
    # (가변 객체를 참조로 저장했을 때) 매도 시점의 0 으로 소급 오염됐었다.
    rows = [
        _row("kojiro", "003490", "BUY", 28050, 2, "2026-09-18"),
        _row("kojiro", "003490", "SELL", 29000, 2, "2026-09-26"),
    ]
    events = mod.filter_trade_events(rows)
    days = ["2026-09-18", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-26"]
    tl = mod.build_daily_timeline(events, strategies=["kojiro"], trading_days=days)
    for d in ("2026-09-18", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"):
        snap = tl["eod"][("kojiro", d)]
        assert snap == [{"ticker": "003490", "quantity": 2, "cost_basis": 56100.0}], d
    assert tl["eod"][("kojiro", "2026-09-26")] == []


def test_strategies_without_any_trade_get_zero_eod(mod):
    rows = [_row("kojiro", "005930", "BUY", 70000, 10, "2026-09-21")]
    events = mod.filter_trade_events(rows)
    tl = mod.build_daily_timeline(
        events, strategies=["kojiro", "momentum"], trading_days=["2026-09-21"]
    )
    assert tl["eod"][("momentum", "2026-09-21")] == []
    assert tl["eod_count"][("momentum", "2026-09-21")] == 0
    assert tl["eod_cost_total"][("momentum", "2026-09-21")] == 0.0


def test_lots_capture_each_buy_for_lot_shape_analysis(mod):
    rows = [
        _row("kojiro", "005930", "BUY", 70000, 10, "2026-09-21"),
        _row("kojiro", "005930", "BUY", 71000, 3, "2026-09-22"),
        _row("kojiro", "005930", "SELL", 72000, 13, "2026-09-23"),
    ]
    events = mod.filter_trade_events(rows)
    tl = mod.build_daily_timeline(
        events,
        strategies=["kojiro"],
        trading_days=["2026-09-21", "2026-09-22", "2026-09-23"],
    )
    assert len(tl["lots"]) == 2
    assert [l["quantity"] for l in tl["lots"]] == [10, 3]
    assert all(l["trade_type"] == "BUY" for l in tl["lots"])


# ── reconcile_with_live_positions ────────────────────────────────────

def test_reconcile_reports_only_mismatches(mod):
    reconstructed = {"005930": 10, "000660": 5}
    live = {"005930": 10, "000660": 7, "035420": 3}
    diffs = mod.reconcile_with_live_positions(reconstructed, live)
    tickers = {d["ticker"] for d in diffs}
    assert tickers == {"000660", "035420"}
    d660 = next(d for d in diffs if d["ticker"] == "000660")
    assert d660["reconstructed_qty"] == 5
    assert d660["live_qty"] == 7
    d035420 = next(d for d in diffs if d["ticker"] == "035420")
    assert d035420["reconstructed_qty"] == 0
    assert d035420["live_qty"] == 3


def test_reconcile_empty_when_matching(mod):
    assert mod.reconcile_with_live_positions({"005930": 10}, {"005930": 10}) == []
