"""cycle451 — 실비용 추정 요율 = 「가장 최근 정산일 하루」 의 요율 (Red).

사용자 결정 2026-10-13 — 주계좌가 수수료 우대 계좌로 바뀌었는데(약 0.14% → 약 0.014%)
추정 요율이 30일 창 전체의 가중 평균이라 옛 요율이 30일 동안 섞인다. 「추정요율은 가장 최근의
율로」.

계약(명세 = `_workspace/red/cycle451_latest_day_rates_spec.md`):

| # | 규칙 |
|---|---|
| 1 | 수수료율 = 거래금액(`buy_amt+sll_amt`) > 0 인 정산 행이 있는 **가장 최근 `trad_dt` 하루**의 Σfee ÷ Σ(buy_amt+sll_amt) |
| 2 | 세율 = 매도금액(`sll_amt`) > 0 인 정산 행이 있는 **가장 최근 `trad_dt` 하루**의 Σtl_tax ÷ Σsll_amt (수수료율 기준일과 다를 수 있다) |
| 3 | 조회 창은 그대로 `[today − window_days, today]`. 창 안에 근거가 없으면 그 요율만 기본값 |
| 4 | 반환 키 = `{fee_rate, tax_rate, source}` 그대로. `source` = 둘 중 하나라도 정산 행에서 나왔으면 `measured`, 둘 다 기본값이면 `default` |

테스트는 내부 함수 이름에 묶이지 않는다 — 공개 진입점 `cost_overlay.today_window_rates()` 와
그것을 쓰는 라우트(`GET /api/costs/today`)만 겨냥한다.

격리: `src.db.trade_cost.get_daily_range`·`get_trades_by_status` · `src.db.stock_master.get_etf_group_codes`
를 monkeypatch 한다(DB 실접속 0). 시계 = freezegun **2026-10-13 12:00 KST** 고정.
`trad_dt` 는 `date` 객체만 쓴다 — `get_daily_range` 가 DATE 열을 그대로 SELECT 해 asyncpg 가
`datetime.date` 로 돌려주기 때문이다(ISO 문자열로는 오지 않는다).
"""

from __future__ import annotations

import importlib
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from freezegun import freeze_time

from src.engine import cost_overlay

pytestmark = pytest.mark.unit

TODAY = date(2026, 10, 13)
FROZEN = "2026-10-13T03:00:00Z"  # = 2026-10-13 12:00 KST

OLD_FEE_RATE = 0.0014     # 옛 계좌 — 0.14%
NEW_FEE_RATE = 0.00014    # 우대 계좌 — 0.014%


def _cost(pdno, trad_dt, **over) -> dict:
    row = {
        "trad_dt": trad_dt, "pdno": pdno, "prdt_name": "",
        "buy_qty": Decimal(0), "buy_amt": Decimal(0), "sll_qty": Decimal(0),
        "sll_amt": Decimal(0), "rlzt_pfls": Decimal(0), "fee": Decimal(0),
        "tl_tax": Decimal(0), "row_count": 1, "raw": [],
    }
    row.update({k: Decimal(str(v)) for k, v in over.items()})
    return row


def _patch_rows(monkeypatch, rows: list[dict]) -> None:
    """`get_daily_range` 를 창 필터가 있는 메모리 스텁으로 바꾼다(실 DB 와 같은 정렬)."""
    tcdb = importlib.import_module("src.db.trade_cost")

    async def get_daily_range(start, end):
        hit = [r for r in rows if start <= r["trad_dt"] <= end]
        return sorted(hit, key=lambda r: (r["trad_dt"], r["pdno"]))

    monkeypatch.setattr(tcdb, "get_daily_range", get_daily_range)


async def _rates(monkeypatch, rows: list[dict]) -> dict:
    _patch_rows(monkeypatch, rows)
    with freeze_time(FROZEN):
        return await cost_overlay.today_window_rates()


def _old_days() -> list[dict]:
    """창 안 옛 요율 10일(09-21 ~ 09-30) — 매일 매수 100만·매도 100만, 수수료 0.14%·세금 0.20%."""
    return [
        _cost("005930", date(2026, 9, 21 + i), buy_amt=1_000_000, sll_amt=1_000_000,
              fee=2_800, tl_tax=2_000)
        for i in range(10)
    ]


# ── T1: 가장 최근 정산일 하루만 새 요율 ─────────────────────────────────────────

async def test_t1_fee_rate_when_only_latest_day_has_new_rate_then_latest_day_rate(monkeypatch):
    rows = _old_days() + [
        _cost("005930", date(2026, 10, 12), buy_amt=1_000_000, sll_amt=1_000_000,
              fee=280, tl_tax=1_500),
    ]
    r = await _rates(monkeypatch, rows)
    # 30일 평균이면 (10×2,800 + 280) ÷ 22,000,000 ≈ 0.001285 — 옛 요율이 섞인다
    assert r["fee_rate"] == pytest.approx(NEW_FEE_RATE), r
    assert r["tax_rate"] == pytest.approx(0.0015), r
    assert r["source"] == "measured"


# ── T2: 가장 최근 정산일이 매수만 있던 날 ───────────────────────────────────────

async def test_t2_tax_rate_when_latest_day_is_buy_only_then_from_latest_sell_day(monkeypatch):
    rows = [
        _cost("005930", date(2026, 10, 2), sll_amt=1_000_000, fee=1_400, tl_tax=2_300),
        _cost("005930", date(2026, 10, 8), sll_amt=1_000_000, fee=1_400, tl_tax=1_500),
        _cost("005930", date(2026, 10, 12), buy_amt=1_000_000, fee=140),
    ]
    r = await _rates(monkeypatch, rows)
    assert r["fee_rate"] == pytest.approx(NEW_FEE_RATE), r   # 10-12 하루
    assert r["tax_rate"] == pytest.approx(0.0015), r         # 10-08 하루(10-02 와 섞지 않는다)
    assert r["source"] == "measured"


# ── T3: 같은 날 여러 종목 행 = 그날 전체 합 ─────────────────────────────────────

async def test_t3_latest_day_with_many_rows_then_whole_day_sum(monkeypatch):
    rows = _old_days() + [
        _cost("000660", date(2026, 10, 12), buy_amt=1_000_000, fee=100),
        _cost("035720", date(2026, 10, 12), sll_amt=3_000_000, fee=500, tl_tax=6_000),
        _cost("373220", date(2026, 10, 12), buy_amt=2_000_000, sll_amt=2_000_000,
              fee=600, tl_tax=3_000),
    ]
    r = await _rates(monkeypatch, rows)
    # 행 하나만 보면 100/1,000,000 · 500/3,000,000 · 600/4,000,000 중 하나가 된다
    assert r["fee_rate"] == pytest.approx(1_200 / 8_000_000), r
    assert r["tax_rate"] == pytest.approx(9_000 / 5_000_000), r


# ── T4: 근거 없음 = 그 요율만 기본값 ────────────────────────────────────────────

async def test_t4a_no_rows_in_window_then_both_default(monkeypatch):
    # 창 밖(오늘−48일) 행만 있다 — 스텁이 창 필터를 건다
    rows = [_cost("005930", date(2026, 8, 26), buy_amt=1_000_000, sll_amt=1_000_000,
                  fee=280, tl_tax=1_500)]
    r = await _rates(monkeypatch, rows)
    assert r == {"fee_rate": cost_overlay.DEFAULT_FEE_RATE,
                 "tax_rate": cost_overlay.DEFAULT_TAX_RATE, "source": "default"}


async def test_t4b_never_sold_in_window_then_only_tax_is_default(monkeypatch):
    rows = [
        _cost("005930", date(2026, 9, 30), buy_amt=1_000_000, fee=1_400),
        _cost("005930", date(2026, 10, 12), buy_amt=1_000_000, fee=140),
    ]
    r = await _rates(monkeypatch, rows)
    assert r["fee_rate"] == pytest.approx(NEW_FEE_RATE), r
    assert r["tax_rate"] == pytest.approx(cost_overlay.DEFAULT_TAX_RATE), r
    assert r["source"] == "measured"


# ── T5: 거래금액 0 인 날은 기준일이 될 수 없다 ──────────────────────────────────

async def test_t5a_zero_amount_latest_day_is_skipped_for_previous_day(monkeypatch):
    rows = _old_days() + [
        _cost("005930", date(2026, 10, 8), buy_amt=1_000_000, sll_amt=1_000_000,
              fee=280, tl_tax=1_500),
        # 금액 없이 비용만 잡힌 날 — 기준일로 잡으면 0 나눗셈/기본값, 평균에 섞으면 요율이 튄다
        _cost("005930", date(2026, 10, 12), fee=50, tl_tax=70),
    ]
    r = await _rates(monkeypatch, rows)
    assert r["fee_rate"] == pytest.approx(NEW_FEE_RATE), r
    assert r["tax_rate"] == pytest.approx(0.0015), r
    assert r["source"] == "measured"


async def test_t5b_only_zero_amount_rows_then_both_default_and_source_default(monkeypatch):
    rows = [_cost("005930", date(2026, 10, 12), fee=50, tl_tax=70)]
    r = await _rates(monkeypatch, rows)
    assert r == {"fee_rate": cost_overlay.DEFAULT_FEE_RATE,
                 "tax_rate": cost_overlay.DEFAULT_TAX_RATE, "source": "default"}


# ── T7: 반환 키 집합 불변 ───────────────────────────────────────────────────────

@pytest.mark.parametrize("rows", [
    [],
    [_cost("005930", date(2026, 10, 12), buy_amt=1_000_000, sll_amt=1_000_000,
           fee=280, tl_tax=1_500)],
], ids=["default", "measured"])
async def test_t7_return_keys_are_exactly_fee_rate_tax_rate_source(monkeypatch, rows):
    r = await _rates(monkeypatch, rows)
    assert set(r) == {"fee_rate", "tax_rate", "source"}
    assert isinstance(r["fee_rate"], float) and isinstance(r["tax_rate"], float)


# ── T9: 순수 함수 estimate_rates ────────────────────────────────────────────────

def test_t9a_same_day_rows_are_summed_before_dividing():
    rows = [
        _cost("000660", date(2026, 10, 12), buy_amt=1_000_000, fee=100),
        _cost("035720", date(2026, 10, 12), sll_amt=3_000_000, fee=500, tl_tax=6_000),
    ]
    r = cost_overlay.estimate_rates(rows)
    assert r["fee_rate"] == pytest.approx(600 / 4_000_000)
    assert r["tax_rate"] == pytest.approx(6_000 / 3_000_000)


def test_t9b_row_order_does_not_change_result():
    rows = _old_days() + [
        _cost("005930", date(2026, 10, 12), buy_amt=1_000_000, sll_amt=1_000_000,
              fee=280, tl_tax=1_500),
    ]
    forward = cost_overlay.estimate_rates(rows)
    assert cost_overlay.estimate_rates(list(reversed(rows))) == forward
    assert forward["fee_rate"] == pytest.approx(NEW_FEE_RATE)


def test_t9c_fee_and_tax_reference_days_can_differ():
    rows = [
        _cost("005930", date(2026, 10, 8), sll_amt=1_000_000, fee=1_400, tl_tax=1_500),
        _cost("005930", date(2026, 10, 12), buy_amt=1_000_000, fee=140),
    ]
    r = cost_overlay.estimate_rates(rows)
    assert r["fee_rate"] == pytest.approx(NEW_FEE_RATE)
    assert r["tax_rate"] == pytest.approx(0.0015)
    assert r["source"] == "measured"


# ── T8: 라우트가 실제로 쓰는 추정 요율 ──────────────────────────────────────────

def _t(tid, tt, price, qty) -> dict:
    return {
        "id": tid, "trade_date": TODAY, "ticker": "035720", "ticker_name": "카카오",
        "trade_type": tt, "strategy": "momentum", "price": Decimal(str(price)), "quantity": qty,
        "profit_loss": Decimal(100 if tt == "SELL" else 0), "order_no": f"O{tid}",
        "order_price": None, "status": "COMPLETED",
    }


def test_t8_costs_today_estimates_unsettled_fills_with_latest_day_rate(monkeypatch):
    """오늘 체결(정산 전) × 추정 요율 — 창 안 옛 요율 10일이 섞이지 않는다."""
    rows = _old_days() + [
        _cost("005930", date(2026, 10, 12), buy_amt=1_000_000, sll_amt=1_000_000,
              fee=280, tl_tax=1_500),
    ]
    trades = [_t(1, "BUY", 9_990, 10), _t(2, "SELL", 10_000, 10)]
    _patch_rows(monkeypatch, rows)
    tcdb = importlib.import_module("src.db.trade_cost")
    monkeypatch.setattr(tcdb, "get_trades_by_status",
                        AsyncMock(return_value=[dict(t) for t in trades]))
    sm = importlib.import_module("src.db.stock_master")
    monkeypatch.setattr(sm, "get_etf_group_codes",
                        AsyncMock(return_value={"035720": "ST"}), raising=False)

    app = FastAPI()
    app.include_router(importlib.import_module("src.routes.costs").router)
    with freeze_time(FROZEN):
        resp = TestClient(app, raise_server_exceptions=False).get("/api/costs/today")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True, body
    data = body["data"]

    assert data["rate_source"] == "measured"
    assert data["fee_rate"] == pytest.approx(NEW_FEE_RATE), data
    assert data["tax_rate"] == pytest.approx(0.0015), data
    assert data["total"]["fee"] == pytest.approx((99_900 + 100_000) * NEW_FEE_RATE, abs=1e-6), data
    assert data["total"]["tax"] == pytest.approx(100_000 * 0.0015, abs=1e-6), data
