"""cycle411 2차 보완 Red — 순수 계산 leaf·어댑터 결함 고정 (메인 세션 결정 10-08 「2차 보완 결정」).

계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「2차 보완 결정」 절.

| # | 계약 |
|---|---|
| B4 | `compute_te_rr(..., costs_available=False)` → `realized_net_sum_krw`·`fee_sum`·`tax_sum` = None(세전 합을 세후 칸에 담지 않는다). 판정은 페어 값 그대로(net 이 없으니 세전) |
| F1 | `cost_overlay.stock_master_etf_flags(trades)` = `stock_master.get_etf_group_codes(고유 종목)` **1회**. `stock_master.get` 직렬 호출 0. 코드 없음·None 종목은 결과에서 빠진다(이름 폴백) · DB 함수는 `ticker = ANY($1::text[])` 1회 + 필요한 칸만(`SELECT *` 금지) |
| F5 | (a) 「매도 없음」 은 **체결 집합**으로 판정 — 정산 행에 매도금액이 있어도 그 (날짜, 종목) 체결에 SELL 이 없으면 세금은 미배분 + `[cost_overlay_tax_unallocated] ` (b) 짝 체결이 하나도 없는 정산 행 = `[cost_overlay_unmatched_cost] ` WARNING |
| F6 | 두 경고는 (trad_dt, pdno) 당 **프로세스 수명** 1회 — 같은 키는 날짜가 바뀌어도 다시 경고하지 않는다(3차 LOW 보완 — 「KST 오늘」 을 키에서 뺐다. 이전엔 하루 1회였다, `test_cycle411d_cost_overlay_warn_fixes.py`) |
| F8 | `today_window_rates()` = KST 하루 단위 메모리 캐시(같은 날 두 번째 호출은 DB 를 읽지 않는다, 다음 날 다시 읽는다). 실패는 캐시하지 않는다 |
| 위생 | `cost_overlay._reset_cache_for_tests()` 가 요율 캐시·경고 dedupe 를 비우고, `tests/conftest.py::_reset_cost_overlay_memo`(autouse)가 매 테스트 전·후에 부른다 |

경고 단언은 레벨·prefix 로 한정한다(CI 루트 로거 DEBUG — cycle252 T2). 경고 키는 다른 테스트와 겹치지
않는 종목코드(`2xxxx0`)를 쓴다.
"""

from __future__ import annotations

import ast
import importlib
import logging
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from freezegun import freeze_time

from src.engine import cost_overlay
from src.engine.te_metrics import compute_te_rr

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
D2 = date(2026, 10, 7)
KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 8, 20, 0, tzinfo=KST)
RATES = {"fee_rate": 0.00142, "tax_rate": 0.00199, "source": "default"}
DAY1 = "2026-10-07T03:00:00Z"  # 2026-10-07 12:00 KST
DAY2 = "2026-10-08T03:00:00Z"  # 2026-10-08 12:00 KST


def _cost(pdno, trad_dt, **over) -> dict:
    row = {
        "trad_dt": trad_dt, "pdno": pdno, "prdt_name": "",
        "buy_qty": Decimal(0), "buy_amt": Decimal(0), "sll_qty": Decimal(0),
        "sll_amt": Decimal(0), "rlzt_pfls": Decimal(0), "fee": Decimal(0),
        "tl_tax": Decimal(0), "row_count": 1, "raw": [],
    }
    row.update({k: Decimal(str(v)) for k, v in over.items()})
    return row


def _t(tid, strategy, tt, price, qty, *, ticker, name="가나", d=D2) -> dict:
    return {
        "id": tid, "trade_date": d, "ticker": ticker, "ticker_name": name, "trade_type": tt,
        "strategy": strategy, "price": Decimal(str(price)), "quantity": qty,
        "profit_loss": Decimal(0), "order_price": None, "status": "COMPLETED",
    }


def _warns(caplog, prefix: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records
            if r.levelno >= logging.WARNING and r.getMessage().startswith(prefix)]


# ── B4: compute_te_rr — 비용 모름 ──────────────────────────────────────────────

def _gross_pairs(n=20):
    return [{
        "status": "closed", "sell_date": "2026-10-01", "profit_rate": 0.1, "profit_loss": 700,
        "strategy": "momentum", "pair_key": f"momentum:005930:O{i}",
    } for i in range(n)]


def test_b4_compute_te_rr_costs_unavailable_marks_net_only_fields_none():
    d = asdict(compute_te_rr(_gross_pairs(), now=NOW, strategy_id="momentum",
                             costs_available=False))
    assert d["n"] == 20
    assert d["realized_sum_krw"] == pytest.approx(14_000)  # 세전 그대로
    for k in ("realized_net_sum_krw", "fee_sum", "tax_sum"):
        assert d[k] is None, (k, d)
    assert d["te_pct"] == pytest.approx(d["te_pct_gross"])


def test_b4b_default_costs_available_keeps_gross_fallback_for_legacy_pairs():
    """가드 — 기본값(costs_available 생략)은 기존 q4 폴백 그대로(net 없는 구 입력 = 세전 합)."""
    d = asdict(compute_te_rr(_gross_pairs(), now=NOW, strategy_id="momentum"))
    assert d["realized_net_sum_krw"] == pytest.approx(d["realized_sum_krw"])


# ── F1: ETF 판정 일괄 조회 ──────────────────────────────────────────────────────

async def test_f1_stock_master_etf_flags_uses_one_batch_query(monkeypatch):
    sm = importlib.import_module("src.db.stock_master")
    batch_calls: list[list[str]] = []
    get_calls: list[str] = []

    async def codes(tickers):
        batch_calls.append(sorted(tickers))
        return {"138930": "ST", "999999": "EF", "035720": None}

    async def single(ticker):
        get_calls.append(ticker)
        return None

    monkeypatch.setattr(sm, "get_etf_group_codes", codes, raising=False)
    monkeypatch.setattr(sm, "get", single)
    trades = [
        _t(1, "momentum", "SELL", 10_000, 1, ticker="138930", name="BNK금융지주"),
        _t(2, "etf_trend", "SELL", 10_000, 1, ticker="999999", name="KIWOOM 200"),
        _t(3, "momentum", "SELL", 10_000, 1, ticker="035720", name="카카오"),
        _t(4, "momentum", "BUY", 10_000, 1, ticker="035720", name="카카오"),
    ]
    flags = await cost_overlay.stock_master_etf_flags(trades)
    assert get_calls == []
    assert batch_calls == [["035720", "138930", "999999"]]
    # 코드 있는 종목만 판정(코드 > 이름) · 코드 없는 종목은 빠져 이름 폴백이 받는다
    assert flags == {"138930": False, "999999": True}


async def test_f1b_db_get_etf_group_codes_single_any_query(monkeypatch):
    pg = importlib.import_module("src.db.pg")
    sm = importlib.import_module("src.db.stock_master")
    seen: list[tuple[str, tuple]] = []

    async def fetch(sql, *args):
        seen.append((sql, args))
        return [{"ticker": "138930", "scty_grp_id_cd": "ST"},
                {"ticker": "999999", "scty_grp_id_cd": "EF"}]

    monkeypatch.setattr(pg, "fetch", fetch)
    out = await sm.get_etf_group_codes(["138930", "999999", "000000"])
    assert out == {"138930": "ST", "999999": "EF", "000000": None}
    assert len(seen) == 1
    sql, args = seen[0]
    flat = " ".join(sql.split())
    assert "ANY(" in flat.replace(" ", "") or "ANY (" in flat
    assert "scty_grp_id_cd" in flat
    assert "SELECT *" not in flat.upper()
    assert sorted(args[0]) == ["000000", "138930", "999999"]


async def test_f1c_db_get_etf_group_codes_empty_input_skips_query(monkeypatch):
    pg = importlib.import_module("src.db.pg")
    sm = importlib.import_module("src.db.stock_master")
    seen: list = []

    async def fetch(sql, *args):
        seen.append(sql)
        return []

    monkeypatch.setattr(pg, "fetch", fetch)
    assert await sm.get_etf_group_codes([]) == {}
    assert seen == []


# ── F5: 「매도 없음」 = 체결 집합 기준 · 짝 없는 정산 행 ────────────────────────

def test_f5a_settlement_has_sell_but_fills_have_no_sell_tax_is_unallocated(caplog):
    """정산 행에는 매도금액·세금이 있는데 체결 집합엔 매수만 — 세금을 매수 행에 몰지 않는다."""
    trades = [_t(1, "volatility_breakout", "BUY", 100_000, 5, ticker="200010"),
              _t(2, "kojiro", "BUY", 100_000, 3, ticker="200010")]
    rows = [_cost("200010", D2, buy_amt=800_000, sll_amt=510_000, fee=183, tl_tax=1015)]
    with caplog.at_level(logging.DEBUG):
        costs = cost_overlay.trade_costs(rows, trades, RATES)
    assert costs[1]["tax"] == pytest.approx(0) and costs[2]["tax"] == pytest.approx(0), costs
    warns = _warns(caplog, "[cost_overlay_tax_unallocated] ")
    assert len(warns) == 1, [r.getMessage() for r in caplog.records]
    assert "200010" in warns[0].getMessage()


def test_f5b_settlement_row_without_any_fill_warns(caplog):
    """정산 행이 있는데 그 (날짜, 종목) 체결이 하나도 없다 — 비용이 조용히 사라지지 않게 경고."""
    trades = [_t(1, "momentum", "BUY", 10_000, 10, ticker="200020")]
    rows = [_cost("200020", D2, buy_amt=100_000, fee=14),
            _cost("200030", D2, buy_amt=50_000, fee=7)]  # 짝 없음
    with caplog.at_level(logging.DEBUG):
        costs = cost_overlay.trade_costs(rows, trades, RATES)
    assert costs[1]["fee"] == pytest.approx(14)
    warns = _warns(caplog, "[cost_overlay_unmatched_cost] ")
    assert len(warns) == 1, [r.getMessage() for r in caplog.records]
    msg = warns[0].getMessage()
    assert "200030" in msg and "2026-10-07" in msg, msg


def test_f5c_matched_settlement_rows_do_not_warn(caplog):
    """가드 — 짝이 있고 매도 체결도 있는 정상 행은 두 경고 모두 없다."""
    trades = [_t(1, "momentum", "BUY", 10_000, 10, ticker="200040"),
              _t(2, "momentum", "SELL", 10_100, 10, ticker="200040")]
    rows = [_cost("200040", D2, buy_amt=100_000, sll_amt=101_000, fee=28, tl_tax=201)]
    with caplog.at_level(logging.DEBUG):
        cost_overlay.trade_costs(rows, trades, RATES)
    assert not _warns(caplog, "[cost_overlay_tax_unallocated] ")
    assert not _warns(caplog, "[cost_overlay_unmatched_cost] ")


# ── F6: 경고 (trad_dt, pdno) 당 프로세스 수명 1회 (3차 LOW 보완) ───────────────

def _tax_no_sell(pdno):
    return ([_t(1, "kojiro", "BUY", 100_000, 3, ticker=pdno)],
            [_cost(pdno, D2, buy_amt=300_000, fee=40, tl_tax=50)])


def test_f6a_tax_unallocated_same_key_same_day_warns_once(caplog):
    trades, rows = _tax_no_sell("200050")
    with freeze_time(DAY1), caplog.at_level(logging.DEBUG):
        cost_overlay.trade_costs(rows, trades, RATES)
        cost_overlay.trade_costs(rows, trades, RATES)
    assert len(_warns(caplog, "[cost_overlay_tax_unallocated] ")) == 1


def test_f6b_tax_unallocated_stays_silent_on_next_kst_day(caplog):
    """3차 LOW 보완 — dedupe 는 프로세스 수명 동안이다(날짜가 바뀌어도 다시 경고하지
    않는다). 날짜 포함 재경고가 필요하면 `_reset_cache_for_tests()` 로 직접 비운다
    (`test_cycle411d_cost_overlay_warn_fixes.py::test_l8b/l8c` 가 그 둘을 각각 지킨다)."""
    trades, rows = _tax_no_sell("200060")
    with freeze_time(DAY1) as fr, caplog.at_level(logging.DEBUG):
        cost_overlay.trade_costs(rows, trades, RATES)
        fr.move_to(DAY2)
        cost_overlay.trade_costs(rows, trades, RATES)
    assert len(_warns(caplog, "[cost_overlay_tax_unallocated] ")) == 1


def test_f6c_unmatched_cost_same_key_same_day_warns_once(caplog):
    trades = [_t(1, "momentum", "BUY", 10_000, 10, ticker="200070")]
    rows = [_cost("200080", D2, buy_amt=50_000, fee=7)]
    with freeze_time(DAY1), caplog.at_level(logging.DEBUG):
        cost_overlay.trade_costs(rows, trades, RATES)
        cost_overlay.trade_costs(rows, trades, RATES)
    assert len(_warns(caplog, "[cost_overlay_unmatched_cost] ")) == 1


# ── F8: 서버 오늘 기준 30일 요율 = 하루 단위 메모리 캐시 ────────────────────────

_WINDOW_ROW = _cost("111111", date(2026, 9, 20), buy_amt=1_000_000, sll_amt=1_000_000,
                    fee=6_000, tl_tax=4_000)


async def test_f8a_today_window_rates_cached_per_kst_day(monkeypatch):
    tcdb = importlib.import_module("src.db.trade_cost")
    calls: list[tuple[date, date]] = []

    async def get_daily_range(start, end):
        calls.append((start, end))
        return [_WINDOW_ROW]

    monkeypatch.setattr(tcdb, "get_daily_range", get_daily_range)
    with freeze_time(DAY1) as fr:
        a = await cost_overlay.today_window_rates()
        b = await cost_overlay.today_window_rates()
        assert a["fee_rate"] == pytest.approx(0.003) and b == a
        assert len(calls) == 1, calls  # 같은 날 두 번째는 DB 를 읽지 않는다
        fr.move_to(DAY2)
        await cost_overlay.today_window_rates()
    assert len(calls) == 2, calls  # 다음 날은 다시 읽는다
    assert calls[1] == (date(2026, 10, 8) - timedelta(days=30), date(2026, 10, 8))


async def test_f8b_failed_window_read_is_not_cached(monkeypatch):
    """가드 — 실패는 캐시하지 않는다(다음 요청이 다시 시도한다)."""
    tcdb = importlib.import_module("src.db.trade_cost")
    state = {"n": 0}

    async def get_daily_range(start, end):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("db down")
        return [_WINDOW_ROW]

    monkeypatch.setattr(tcdb, "get_daily_range", get_daily_range)
    with freeze_time(DAY1):
        with pytest.raises(RuntimeError):
            await cost_overlay.today_window_rates()
        r = await cost_overlay.today_window_rates()
    assert r["fee_rate"] == pytest.approx(0.003)
    assert state["n"] == 2


# ── 위생: 메모 초기화 훅 + conftest autouse ─────────────────────────────────────

def test_hygiene_reset_hook_exists_and_conftest_calls_it_autouse():
    assert callable(getattr(cost_overlay, "_reset_cache_for_tests", None)), \
        "cost_overlay._reset_cache_for_tests() 가 없다 — 요율 캐시·경고 dedupe 를 비울 훅"
    tree = ast.parse((ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"))
    fixtures = {
        n.name: n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_reset_cost_overlay_memo"
    }
    assert "_reset_cost_overlay_memo" in fixtures, "tests/conftest.py::_reset_cost_overlay_memo 부재"
    fn = fixtures["_reset_cost_overlay_memo"]
    deco = ast.unparse(fn.decorator_list[0]) if fn.decorator_list else ""
    assert "fixture" in deco and "autouse=True" in deco, deco
    src = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "_reset_cache_for_tests" in src
